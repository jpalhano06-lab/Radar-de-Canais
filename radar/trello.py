"""Cada pedido de vídeo vira um cartão no quadro "youtube" do Trello, na lista do canal (pedido do usuário em
2026-11-03). A lista é a que tem o nome mais parecido com o do canal ("João o Lobo" -> "Joao O lobo - A fazer",
"UK MARKET" -> "UK mercado"); um canal sem lista ganha uma com o nome dele. Sem as chaves (TRELLO_KEY e TRELLO_TOKEN,
na aba Integrações) não faz nada, e um erro do Trello nunca atrapalha o pedido."""
import logging
import re
import threading
import unicodedata

import httpx

from . import config

API = "https://api.trello.com/1"
QUADRO_PADRAO = "7MAyqN4o"          # https://trello.com/b/7MAyqN4o/youtube
_TRAVA = threading.Lock()           # dois pedidos do mesmo canal novo ao mesmo tempo não criam duas listas
log = logging.getLogger(__name__)


def ligado() -> bool:
    return bool(config.AMBIENTE.get("TRELLO_KEY") and config.AMBIENTE.get("TRELLO_TOKEN"))


def _pedir(metodo: str, caminho: str, **params) -> dict | list:
    params |= {"key": config.AMBIENTE["TRELLO_KEY"], "token": config.AMBIENTE["TRELLO_TOKEN"]}
    r = httpx.request(metodo, API + caminho, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def _palavras(texto: str) -> list[str]:
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto.lower()) if not unicodedata.combining(c))
    return [p for p in re.findall(r"\w+", sem_acento) if len(p) > 1]


def _parecido(a: str, b: str) -> bool:
    """A mesma palavra ou uma começando a outra com 4 letras ou mais (insect/insecto)."""
    return a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)))


def lista_do_canal(canal: str, listas: list[dict]) -> dict | None:
    """A lista com mais palavras em comum com o canal; precisa bater pelo menos metade das palavras do canal."""
    do_canal = _palavras(canal)
    if not do_canal:
        return None
    melhor, nota = None, 0.0
    for lista in listas:
        da_lista = _palavras(lista["name"])
        n = sum(any(_parecido(p, q) for q in da_lista) for p in do_canal) / len(do_canal)
        if n > nota:
            melhor, nota = lista, n
    return melhor if nota >= 0.5 else None


def criar_cartao(canal: str, titulo: str, descricao: str = "") -> dict:
    quadro = config.AMBIENTE.get("TRELLO_QUADRO") or QUADRO_PADRAO
    with _TRAVA:
        listas = _pedir("GET", f"/boards/{quadro}/lists", filter="open")
        lista = lista_do_canal(canal, listas)
        if not lista:
            ultima = max((l.get("pos") or 0 for l in listas), default=0)
            lista = _pedir("POST", "/lists", name=canal, idBoard=listas[0]["idBoard"] if listas else quadro,
                           pos=ultima + 65536)
    cartao = _pedir("POST", "/cards", idList=lista["id"], name=titulo[:16384], desc=descricao[:16384], pos="top")
    return {"lista": lista["name"], "url": cartao.get("shortUrl") or cartao.get("url", "")}


def do_pedido(canal: str, pedido: dict) -> None:
    """O cartão do pedido, sem segurar quem pediu: roda em segundo plano e só registra o erro."""
    if not ligado() or not canal:
        return

    def rodar():
        partes = [pedido.get("link") or "", f"Nicho: {pedido['nicho']}" if pedido.get("nicho") else "",
                  pedido.get("observacao") or ""]
        try:
            criar_cartao(canal, pedido["titulo"], "\n\n".join(p for p in partes if p))
        except (httpx.HTTPError, KeyError, ValueError, IndexError) as erro:
            log.warning("Trello: o cartão de %r não foi criado: %s", pedido.get("titulo"), erro)
    threading.Thread(target=rodar, daemon=True).start()
