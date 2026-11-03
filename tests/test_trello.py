import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from radar import config, trello  # noqa: E402

# as listas do quadro youtube em 2026-11-03
LISTAS = [{"id": "l1", "name": "Joao O lobo - A fazer", "pos": 1, "idBoard": "b"},
          {"id": "l2", "name": "UK mercado", "pos": 2, "idBoard": "b"},
          {"id": "l3", "name": "한국의 미래 (Hangugui Mirae", "pos": 3, "idBoard": "b"},
          {"id": "l4", "name": "Australia mercado", "pos": 4, "idBoard": "b"}]


@pytest.mark.parametrize("canal, lista", [("João o Lobo", "l1"), ("UK MARKET", "l2"),
                                          ("한국의 미래 (Hangugui Mirae)", "l3"), ("Australia Market", "l4"),
                                          ("Documentário", None), ("PH MERKAT", None), ("Dr. Insecto", None)])
def test_lista_do_canal(canal, lista):
    achada = trello.lista_do_canal(canal, LISTAS)
    assert (achada or {}).get("id") == lista


def test_insect_e_insecto_batem():
    assert trello.lista_do_canal("Dr. Insecto", [{"id": "x", "name": "Dr. Insect"}])["id"] == "x"


@pytest.fixture
def chamadas(monkeypatch):
    feitas = []

    def pedir(metodo, caminho, **params):
        feitas.append((metodo, caminho, params))
        if caminho.endswith("/lists") and metodo == "GET":
            return LISTAS
        if caminho == "/lists":
            return {"id": "nova", "name": params["name"]}
        return {"shortUrl": "https://trello.com/c/abc"}
    monkeypatch.setattr(trello, "_pedir", pedir)
    return feitas


def test_cartao_vai_para_a_lista_do_canal(chamadas):
    r = trello.criar_cartao("João o Lobo", "10 Cobras", "https://youtu.be/x")
    assert r == {"lista": "Joao O lobo - A fazer", "url": "https://trello.com/c/abc"}
    assert chamadas[-1] == ("POST", "/cards", {"idList": "l1", "name": "10 Cobras", "desc": "https://youtu.be/x", "pos": "top"})


def test_canal_sem_lista_ganha_uma(chamadas):
    r = trello.criar_cartao("Documentário", "A história do café")
    assert r["lista"] == "Documentário"
    assert ("POST", "/lists", {"name": "Documentário", "idBoard": "b", "pos": 4 + 65536}) in chamadas
    assert chamadas[-1][2]["idList"] == "nova"


def test_sem_chaves_nao_faz_nada(monkeypatch, chamadas):
    monkeypatch.setattr(config, "AMBIENTE", {})
    trello.do_pedido("João o Lobo", {"titulo": "x"})
    assert chamadas == []
