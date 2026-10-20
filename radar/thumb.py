"""A thumbnail no Roteiro: projetos de prompt por canal, como os estilos do roteiro (pedido do usuário em 2026-10-14).

O vídeo de referência leva a thumbnail dele para o Roteiro; o modelo de visão gratuito (Groq) descreve a capa e o
projeto escolhido monta o prompt pronto para o Gemini ou outra IA de imagem. Um dia, uma extensão cola o prompt lá."""
import json

import httpx

from . import banco, ia
from .config import MODELO_VISAO

PADRAO = """Crie uma thumbnail de YouTube em 16:9, 1280x720, para um canal dark (sem rosto de apresentador).
Título do vídeo: {titulo}
Use como referência de composição esta thumbnail que funcionou: {referencia}
Mantenha a mesma ideia visual (o que aparece, o enquadramento, as cores fortes e o contraste), mas com imagem nova e original.
Texto na imagem: no máximo 3 palavras grandes, legíveis no celular.
Estilo: fotográfico, alto contraste, cores saturadas, foco no assunto principal."""

CAMPOS = "{titulo}, {referencia} e {canal}"


def projetos(usuario_id: int) -> list[dict]:
    return banco.todos("SELECT p.*, c.titulo AS canal FROM thumb_projetos p LEFT JOIN canais c ON c.id=p.canal_id "
                       "WHERE p.usuario_id=? ORDER BY p.nome", usuario_id)


def salvar(usuario_id: int, dados: dict) -> int:
    nome = str(dados.get("nome", "")).strip()[:60]
    prompt = str(dados.get("prompt", "")).strip()[:6000]
    if not nome or not prompt:
        raise ValueError("Dê um nome e escreva o prompt.")
    canal_id = str(dados.get("canal_id", ""))
    if dados.get("id"):
        banco.executar("UPDATE thumb_projetos SET nome=?, prompt=?, canal_id=? WHERE id=? AND usuario_id=?",
                       nome, prompt, canal_id, int(dados["id"]), usuario_id)
        return int(dados["id"])
    return banco.executar("INSERT INTO thumb_projetos (usuario_id, canal_id, nome, prompt, criado) VALUES (?,?,?,?,?)",
                          usuario_id, canal_id, nome, prompt, banco.agora())


def apagar(usuario_id: int, pid: int) -> None:
    banco.executar("DELETE FROM thumb_projetos WHERE id=? AND usuario_id=?", pid, usuario_id)


def descrever(video_id: str) -> str:
    """O que a thumbnail de referência mostra, em uma frase longa (guardado para sempre: a capa quase nunca muda)."""
    chave = f"thumb-descricao:{video_id}"
    cache = banco.um("SELECT dados FROM traducoes WHERE chave=?", chave)
    if cache:
        return json.loads(cache["dados"])
    url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    if httpx.head(url, timeout=10).status_code != 200:
        return ""
    resposta = ia._perguntar(MODELO_VISAO, "Você descreve thumbnails de YouTube para outra IA recriar a ideia. Responda só JSON.", [
        {"type": "text", "text": "Descreva esta thumbnail em português, em 2 ou 3 frases: o que aparece, onde está cada coisa "
                                 "(primeiro plano e fundo), as cores, a emoção, e o texto escrito nela. Responda só JSON: "
                                 "{\"descricao\": \"...\"}."},
        {"type": "image_url", "image_url": {"url": url}}], esperar=40)
    descricao = str((resposta or {}).get("descricao", "")).strip()
    if descricao:
        banco.executar("INSERT OR REPLACE INTO traducoes (chave, dados, criado) VALUES (?,?,?)",
                       chave, json.dumps(descricao, ensure_ascii=False), banco.agora())
    return descricao


def montar(usuario_id: int, projeto_id: int | None, titulo: str, video_id: str) -> dict:
    p = banco.um("SELECT p.*, c.titulo AS canal FROM thumb_projetos p LEFT JOIN canais c ON c.id=p.canal_id "
                 "WHERE p.id=? AND p.usuario_id=?", projeto_id, usuario_id) if projeto_id else None
    modelo = p["prompt"] if p else PADRAO
    referencia = descrever(video_id) if video_id else ""
    prompt = (modelo.replace("{titulo}", titulo or "(sem título)")
              .replace("{referencia}", referencia or "(sem thumbnail de referência)")
              .replace("{canal}", (p or {}).get("canal") or ""))
    return {"prompt": prompt, "referencia": referencia, "projeto": p["nome"] if p else "Padrão"}
