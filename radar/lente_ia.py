"""As leituras de IA do painel do vídeo: por que estourou, títulos no molde, levar para outra língua e a receita da capa.

O texto é do Claude Code deste computador, a capa é da visão que o Radar já usa. Cada resposta fica guardada: abrir o
mesmo vídeo de novo não gasta outra chamada. Nada aqui sai do Radar sem a pessoa pedir pelo botão.
"""
import json

from . import banco, descricao, ia, roteiro_claude
from .config import MODELO_VISAO

SISTEMA_POR_QUE = """Você analisa por que um vídeo do YouTube passou muito do normal do canal dele.
Olhe o título e, se vier, o começo da fala. Não elogie: aponte o mecanismo. Responda só JSON, em português do Brasil:
{"quebra": "o que no título foge do que o público espera", "prova": "o dado específico que dá credibilidade (número, nome, data), ou vazio",
"loop": "a pergunta que o título abre e só o vídeo fecha", "comeco": "o que os primeiros segundos fazem para segurar quem clicou, ou vazio se não vier a fala",
"resumo": "uma frase: por que clicaram"}"""

SISTEMA_TITULOS = """Você escreve títulos de YouTube a partir do molde de um título que funcionou.
Mantenha a estrutura e a sensação, troque o assunto pelo da pessoa. Nunca copie palavras do assunto original.
Escreva na língua do título de exemplo. Responda só JSON:
{"sensacao": "a sensação que o título deixa, em uma frase em português", "titulos": ["10 títulos"]}"""

SISTEMA_ADAPTAR = """Você adapta um título de YouTube para o público de outra língua e país.
Não traduza palavra por palavra: troque referências locais pelas de lá e use a expressão que as pessoas de lá procuram.
Responda só JSON: {"titulo": "o título adaptado, na língua pedida", "em_portugues": "o que ele diz, em português",
"mudou": "o que mudou e por quê, em uma frase em português", "procura": "o que o público de lá procura sobre isso, em português"}"""

SISTEMA_CAPA = """Você descreve a capa de um vídeo do YouTube como uma receita para fazer outra no mesmo estilo.
Responda só JSON, os campos em português, e a instrução em inglês:
{"mostra": "o que aparece", "composicao": "onde cada coisa está", "cores": "a paleta e o contraste", "texto": "o texto escrito e o peso dele, ou vazio",
"emocao": "a emoção que ela passa", "gancho": "o que faz clicar",
"instrucao": "instrução pronta em inglês para gerar uma capa nesse estilo, com [SUBJECT] e [TEXT] no lugar do assunto e do texto"}"""


def _guardado(chave: str) -> dict | None:
    linha = banco.um("SELECT dados FROM traducoes WHERE chave=?", chave)
    return json.loads(linha["dados"]) if linha else None


def _guardar(chave: str, dados: dict) -> dict:
    banco.executar("INSERT OR REPLACE INTO traducoes (chave, dados, criado) VALUES (?,?,?)",
                   chave, json.dumps(dados, ensure_ascii=False), banco.agora())
    return dados


def _do_claude(sistema: str, pedido: str) -> dict:
    dados = descricao._json_do_claude(roteiro_claude._claude(sistema, pedido))
    if not dados:
        raise RuntimeError("O Claude não devolveu a resposta no formato certo. Tente de novo.")
    return dados


def por_que(video_id: str, titulo: str, fala: str = "", nota: float | None = None, novo: bool = False) -> dict:
    chave = f"lente:por-que:{video_id}"
    if not novo and (guardado := _guardado(chave)):
        return guardado
    pedido = f"Título: {titulo}\n"
    if nota:
        pedido += f"Este vídeo fez {nota}x o normal do canal.\n"
    if fala:
        pedido += f"\nComeço da fala:\n{fala[:2500]}\n"
    return _guardar(chave, _do_claude(SISTEMA_POR_QUE, pedido))


def titulos(titulo: str, assunto: str) -> dict:
    dados = _do_claude(SISTEMA_TITULOS, f"Título que funcionou: {titulo}\nAssunto da pessoa: {assunto}")
    dados["titulos"] = [str(t).strip() for t in dados.get("titulos") or [] if str(t).strip()][:10]
    if not dados["titulos"]:
        raise RuntimeError("O Claude não devolveu nenhum título. Tente de novo.")
    return dados


def adaptar(video_id: str, titulo: str, lingua: str) -> dict:
    chave = f"lente:adaptar:{video_id}:{lingua}"
    if guardado := _guardado(chave):
        return guardado
    return _guardar(chave, _do_claude(SISTEMA_ADAPTAR, f"Título: {titulo}\nLíngua e país de destino: {lingua}"))


def receita_da_capa(video_id: str, titulo: str = "") -> dict:
    chave = f"lente:capa:{video_id}"
    if guardado := _guardado(chave):
        return guardado
    conteudo = [{"type": "text", "text": f"O título do vídeo é: {titulo}"},
                {"type": "image_url", "image_url": {"url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"}}]
    dados = ia._perguntar(MODELO_VISAO, SISTEMA_CAPA, conteudo, saida=900)
    if not dados or not dados.get("instrucao"):
        raise RuntimeError("A visão não respondeu agora. Tente de novo em instantes.")
    return _guardar(chave, dados)
