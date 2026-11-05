"""A ponte que lê o YouTube pela extensão: o Claude pede pelo MCP, uma aba aberta do YouTube lê e devolve, sem gastar cota.

A fila fica na memória do servidor. A extensão pergunta a cada poucos segundos se há pedido; quem pediu espera a resposta
até o prazo. Sem nenhuma aba do YouTube aberta, ninguém pega o pedido e a pergunta volta dizendo isso.
"""
import itertools
import threading
import time

PRAZO = 25
ABA_VIVA = 70       # o Chrome freia a aba escondida para uma pergunta por minuto
TIPOS = ("canal", "busca")

_trava = threading.Lock()
_contador = itertools.count(1)
_fila: list[dict] = []
_esperando: dict[int, dict] = {}
_ultima_olhada = 0.0


class SemAba(RuntimeError):
    pass


def aba_aberta() -> bool:
    return time.monotonic() - _ultima_olhada < ABA_VIVA


def pedir(tipo: str, alvo: str, prazo: float = PRAZO) -> dict:
    """Manda o pedido para a extensão e espera a resposta."""
    if tipo not in TIPOS:
        raise ValueError(f"Não sei ler {tipo}.")
    if not aba_aberta():
        raise SemAba("Abra uma aba do YouTube neste computador, com a extensão do Radar ligada, e peça de novo.")
    pedido = {"id": next(_contador), "tipo": tipo, "alvo": alvo}
    espera = {"pronto": threading.Event(), "dados": None}
    with _trava:
        _esperando[pedido["id"]] = espera
        _fila.append(pedido)
    try:
        if not espera["pronto"].wait(prazo):
            raise SemAba("A aba do YouTube não respondeu a tempo. Recarregue a aba e peça de novo.")
        return espera["dados"]
    finally:
        with _trava:
            _esperando.pop(pedido["id"], None)
            if pedido in _fila:
                _fila.remove(pedido)


def proximo() -> dict | None:
    """O que a extensão pega quando pergunta. Perguntar também diz que a aba está aberta."""
    global _ultima_olhada
    _ultima_olhada = time.monotonic()
    with _trava:
        return _fila.pop(0) if _fila else None


def responder(pedido_id: int, dados: dict) -> None:
    with _trava:
        espera = _esperando.get(pedido_id)
    if espera:
        espera["dados"] = dados
        espera["pronto"].set()
