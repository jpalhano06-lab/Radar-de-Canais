"""O que o público pede: pedidos e perguntas nos comentários dos vídeos mais vistos de um canal.

Lê os 100 comentários mais relevantes de cada um dos 10 vídeos pela API (1 unidade de cota por vídeo), separa os que
pedem ou perguntam alguma coisa e ordena pelas curtidas. Curtida é voto: quem concorda com o pedido curte em vez de
repetir. A resposta fica guardada por uma semana, então abrir o mesmo canal de novo não gasta cota.
"""
import json
import re
from datetime import datetime, timedelta, timezone

from . import banco, ia, youtube
from .config import MODELO_TEXTO

VIDEOS = 10
QUANTOS = 30
CANDIDATOS = 80
GUARDA_DIAS = 7
TEXTO_MAXIMO = 400

# as formas de pedir nas línguas em que o Radar procura. "?" sozinho é pergunta, mas sobra muito "né?" e "first?":
# a pergunta precisa de pelo menos quatro palavras
_PEDIDO = re.compile(
    r"\b(faz|fa[cç]a|fazer|fala|falem?|mostra|mostrem?|explica|explique|podia|poderia|poderiam|queria|quero|gostaria|"
    r"pr[oó]ximo v[ií]deo|parte 2|parte dois|"
    r"please|pls|plz|can you|could you|would you|do a video|make a video|next video|part 2|i wish|you should|"
    r"por favor|podr[ií]as|haz|hagan|quisiera|me gustar[ií]a|"
    r"s'il vous pla[iî]t|pourriez|pourrais|bitte|k[oö]nntest|k[oö]nnten|per favore|potresti|prosz[eę]|l[uü]tfen)\b", re.I)


SISTEMA = """Você separa, nos comentários de um canal do YouTube, os que pedem algo ao canal ou fazem uma pergunta de verdade
sobre o assunto. Conta: pedido de vídeo, de tema, de continuação, de fonte, dúvida que o público quer ver respondida.
Não conta: pergunta retórica, piada, desabafo, elogio, opinião, "eu queria que o mundo fosse diferente", propaganda.
Responda só JSON: {"pedidos": [os números dos comentários que contam]}."""


def _so_os_de_verdade(achados: list[dict]) -> list[dict]:
    """A IA tira a pergunta retórica e o desabafo que a busca por palavras deixa passar. Sem IA, fica a busca por palavras."""
    lista = chr(10).join(f"{i}. {p['texto'][:220]}" for i, p in enumerate(achados))
    try:
        resposta = ia._perguntar(MODELO_TEXTO, SISTEMA, lista, esperar=30)
    except Exception:
        return achados
    numeros = (resposta or {}).get("pedidos")
    if not isinstance(numeros, list):
        return achados
    return [achados[i] for i in numeros if isinstance(i, int) and 0 <= i < len(achados)]


def e_pedido(texto: str) -> bool:
    return bool(_PEDIDO.search(texto)) or ("?" in texto and len(texto.split()) >= 4)


def mais_vistos(canal_id: str, quantos: int = 20) -> list[dict]:
    """Os vídeos mais vistos do canal, com os longos antes dos Shorts."""
    return banco.todos("SELECT id, titulo, views FROM videos WHERE canal_id=? AND views IS NOT NULL ORDER BY "
                       "(COALESCE(duracao_s, 999) > 180) DESC, views DESC LIMIT ?", canal_id, quantos)


def _guardado(chave: str) -> dict | None:
    linha = banco.um("SELECT dados, criado FROM traducoes WHERE chave=?", chave)
    if not linha:
        return None
    limite = datetime.now(timezone.utc) - timedelta(days=GUARDA_DIAS)
    return json.loads(linha["dados"]) if datetime.fromisoformat(linha["criado"]) > limite else None


def do_canal(canal_id: str, ler=None, filtrar=_so_os_de_verdade) -> dict:
    """Os pedidos do canal, dos mais curtidos para os menos, e de quantos vídeos eles saíram."""
    chave = f"pedidos:{canal_id}"
    guardado = _guardado(chave)
    if guardado is not None:
        return guardado
    ler = ler or youtube.comentarios
    achados, lidos, vistos = [], 0, set()
    for video in mais_vistos(canal_id, VIDEOS):
        comentarios = ler(video["id"])
        if comentarios is None:     # comentários desligados neste vídeo
            continue
        lidos += 1
        for c in comentarios:
            texto = " ".join(str(c.get("texto", "")).split())
            marca = texto.lower()
            if texto and c.get("autor") != canal_id and marca not in vistos and e_pedido(texto):
                vistos.add(marca)
                achados.append({"texto": texto[:TEXTO_MAXIMO], "curtidas": int(c.get("curtidas") or 0),
                                "video_id": video["id"], "video_titulo": video["titulo"]})
    achados.sort(key=lambda p: -p["curtidas"])
    escolhidos = filtrar(achados[:CANDIDATOS]) if achados else []
    escolhidos.sort(key=lambda p: -p["curtidas"])
    dados = {"pedidos": escolhidos[:QUANTOS], "videos": lidos}
    if lidos:
        banco.executar("INSERT OR REPLACE INTO traducoes (chave, dados, criado) VALUES (?,?,?)",
                       chave, json.dumps(dados, ensure_ascii=False), banco.agora())
    return dados
