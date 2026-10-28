"""A descrição do vídeo escrita junto com o roteiro, antes de o vídeo existir.

Pedido do usuário em 2026-10-28: "quando gerar o roteiro no Claude quero que já gere uma descrição... a descrição
será criada enquanto o vídeo está sendo feito". Antes disso o texto só aparecia no fim: quem escrevia era a fábrica,
no publicacao.json, e ele só existia depois de narrar e montar o vídeo inteiro. Quem chegava ao Studio com o .mp4
na mão e a fábrica a meio caminho via "título e descrição ficam com você".

Agora o Claude escreve a sinopse, as tags e as hashtags no mesmo minuto do roteiro — ele acabou de ler o texto todo,
que é a melhor fonte que existe para isso — e o resultado fica em descricao.json, ao lado do roteiro. Quando o
roteiro vai para a fábrica, o arquivo vai junto como publicacao_radar.json, e é ele que a extensão lê no Studio:
vale mais que o da fábrica, porque chega antes e foi escrito com o projeto de descrição do canal.

O "projeto de descrição" é um agente da tela de Agentes, do tipo `descricao`: as instruções de estilo que o usuário
cola do claude.ai, do mesmo jeito que o agente de roteiro. Sem nenhum agente desses, valem as regras daqui.
"""
import json
import re
from pathlib import Path

from . import banco, publicar

ARQUIVO = "descricao.json"           # ao lado do roteiro
NA_FABRICA = "publicacao_radar.json"  # a cópia que a extensão lê no Studio

INSTRUCOES = """Você escreve o que acompanha um vídeo de canal dark do YouTube (narrado, sem rosto): a sinopse da
descrição, as tags da busca e as hashtags. Você recebe o título e o roteiro inteiro do vídeo.

Responda SÓ com um JSON, sem nada antes nem depois, sem markdown e sem cercas de código, neste formato:
{"sinopse": "...", "tags": ["...", "..."], "hashtags": ["#...", "#..."]}

sinopse: de 2 a 4 frases dizendo o que a pessoa vai ver, na mesma língua do roteiro, em tom direto. Nada de "neste
vídeo você vai descobrir", nada de emoji, nada de link, nada de pedir inscrição (o canal já tem um rodapé fixo para
isso) e nada de entregar o fim. Só o que o roteiro de fato diz: não invente fato, número, data nem fala de pessoa
real.

tags: de 12 a 20 palavras que as pessoas digitam na busca para achar um vídeo desse assunto, na mesma língua do
roteiro, das mais buscadas para as mais específicas, sem repetir a mesma ideia, sem hashtag e sem número na frente.

hashtags: de 3 a 5, começando com #, sem espaço dentro, as mais ligadas ao assunto."""


# ---------------------------------------------------------------- o agente de descrição

def agente(usuario_id: int, projeto_id: int | None = None) -> dict | None:
    """As instruções de estilo da descrição: o agente escolhido ou, sem escolha, o único do tipo `descricao`.

    Com mais de um e nenhum escolhido, não adivinha: fica sem agente e valem as regras daqui."""
    if projeto_id:
        return banco.um("SELECT * FROM projetos_roteiro WHERE id=? AND usuario_id=? AND tipo='descricao'",
                        projeto_id, usuario_id)
    achados = banco.todos("SELECT * FROM projetos_roteiro WHERE usuario_id=? AND tipo='descricao' ORDER BY id",
                          usuario_id)
    return achados[0] if len(achados) == 1 else None


# ---------------------------------------------------------------- escrever

def _json_do_claude(texto: str) -> dict:
    """O JSON que o Claude respondeu, mesmo que ele tenha posto cerca de código ou uma frase em volta."""
    texto = re.sub(r"^```(?:json)?|```$", "", texto.strip(), flags=re.M).strip()
    try:
        dados = json.loads(texto)
    except ValueError:
        inicio, fim = texto.find("{"), texto.rfind("}")
        if inicio < 0 or fim <= inicio:
            raise RuntimeError("O Claude não devolveu a descrição em JSON.")
        try:
            dados = json.loads(texto[inicio:fim + 1])
        except ValueError:
            raise RuntimeError("O Claude não devolveu a descrição em JSON.")
    if not isinstance(dados, dict):
        raise RuntimeError("O Claude não devolveu a descrição em JSON.")
    return dados


def _hashtag(texto: str) -> str:
    texto = re.sub(r"[^\w#]+", "", str(texto).strip())
    texto = "#" + texto.lstrip("#")
    return texto[:40] if len(texto) > 2 else ""


def escrever(titulo: str, roteiro: str, lingua: str = "", instrucoes: str = "") -> dict:
    """A sinopse, as tags e as hashtags do roteiro. Quem escreve é o Claude Code deste computador (o mesmo do
    roteiro: sem chave de API, sem cota do YouTube)."""
    from . import roteiro_claude
    sistema = INSTRUCOES + (f"\n\nInstruções do projeto de descrição do canal (valem por cima das regras acima "
                            f"quando conflitarem):\n{instrucoes}" if instrucoes.strip() else "")
    pedido = f"Título do vídeo: {' '.join(str(titulo).split())[:300]}\n"
    if lingua:
        pedido += f"Língua: {lingua}\n"
    # o roteiro inteiro passa fácil de 9 mil palavras num vídeo de 1 hora: o começo e o fim dizem o bastante
    texto = (roteiro or "").strip()
    if len(texto) > 24000:
        texto = texto[:16000] + "\n\n[…]\n\n" + texto[-8000:]
    pedido += f"\nRoteiro do vídeo:\n{texto}\n\nEscreva a sinopse, as tags e as hashtags."
    dados = _json_do_claude(roteiro_claude._claude(sistema, pedido))
    sinopse = " ".join(str(dados.get("sinopse") or "").split())[:1500]
    if not sinopse:
        raise RuntimeError("O Claude não devolveu nenhuma sinopse.")
    tags = publicar.tags_que_cabem([t for t in (dados.get("tags") or []) if 2 <= len(str(t).strip()) <= 60])
    hashtags = [h for h in (_hashtag(x) for x in (dados.get("hashtags") or [])) if h][:5]
    return {"sinopse": sinopse, "tags": tags, "hashtags": hashtags}


def gerar(usuario_id: int, pasta: Path, projeto_id: int | None = None) -> dict:
    """Escreve a descrição do roteiro dessa pasta e guarda em descricao.json, ao lado dele."""
    meta = json.loads((pasta / "roteiro.json").read_text(encoding="utf-8"))
    roteiro = (pasta / "roteiro.txt").read_text(encoding="utf-8")
    proj = agente(usuario_id, projeto_id)
    dados = escrever(meta.get("titulo", ""), roteiro, meta.get("lingua", ""),
                     str(proj["instrucoes"]) if proj else "")
    dados |= {"projeto": proj["nome"] if proj else "", "criado": banco.agora()}
    (pasta / ARQUIVO).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return dados


def ler(pasta: Path) -> dict:
    try:
        dados = json.loads((pasta / ARQUIVO).read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def salvar(pasta: Path, sinopse: str = "", tags: list | None = None, hashtags: list | None = None) -> dict:
    """A correção da pessoa antes de mandar para a fábrica."""
    dados = ler(pasta)
    if sinopse.strip():
        dados["sinopse"] = " ".join(sinopse.split())[:1500]
    if tags is not None:
        dados["tags"] = publicar.tags_que_cabem([str(t).strip() for t in tags if str(t).strip()])
    if hashtags is not None:
        dados["hashtags"] = [h for h in (_hashtag(x) for x in hashtags) if h][:5]
    if not dados.get("sinopse"):
        raise RuntimeError("A descrição precisa de uma sinopse.")
    (pasta / ARQUIVO).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return dados


# ---------------------------------------------------------------- levar para a fábrica

def montar(dados: dict, rodape: str = "") -> str:
    """O texto que vai no campo de descrição do Studio: a sinopse deste vídeo e o rodapé fixo do canal."""
    partes = [str(dados.get("sinopse") or "").strip()]
    if rodape.strip():
        partes.append(rodape.strip())
    hashtags = " ".join(dados.get("hashtags") or [])
    if hashtags:
        partes.append(hashtags)
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(p for p in partes if p)).strip()[:5000]


def levar(pasta: Path, destino: Path, titulo: str = "", perfil: str = "") -> bool:
    """Põe a descrição do Radar na pasta do projeto da fábrica, como publicacao_radar.json.

    É esse arquivo que a extensão lê no Studio, e ele chega no minuto do envio: o vídeo ainda está sendo feito e a
    descrição já está pronta. O rodapé sai do perfil do canal na fábrica, como na descrição que ela mesma escreve."""
    dados = ler(pasta)
    if not dados.get("sinopse"):
        return False
    from . import producao
    try:
        rodape = producao.rodape_do_perfil(perfil) if perfil else ""
    except Exception:
        rodape = ""
    kit = {"titulo": titulo or "", "sinopse": dados["sinopse"], "descricao": montar(dados, rodape),
           "tags": dados.get("tags") or [], "hashtags": dados.get("hashtags") or [],
           "sintetico": True,        # todo vídeo da fábrica é feito com IA
           "origem": "radar", "criado": dados.get("criado", ""), "projeto": dados.get("projeto", "")}
    try:
        destino.mkdir(parents=True, exist_ok=True)
        (destino / NA_FABRICA).write_text(json.dumps(kit, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        return False
    return True
