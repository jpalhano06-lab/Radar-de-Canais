"""Vídeo pronto avisa no celular, uma vez por pedido (pedido do usuário em 2026-11-08)."""
import time

import pytest

from radar import banco, fila


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    yield
    banco._CON.close()
    banco._CON = None


def _espera(enviados, n):
    for _ in range(50):
        if len(enviados) >= n:
            return
        time.sleep(0.02)


def test_entregue_avisa_uma_vez(db, celular_de_mentira):
    p = fila.criar(1, {"titulo": "15 Animais da Amazônia", "caracteres": 10620}, comecar=True)
    fila.mudar(p["id"], "produzindo")
    assert fila.mudar(p["id"], "entregue", de=("produzindo",))
    _espera(celular_de_mentira, 1)
    assert len(celular_de_mentira) == 1
    aviso = celular_de_mentira[0]
    assert "Vídeo pronto" in aviso["titulo"] and "15 Animais da Amazônia" in aviso["texto"]
    assert not fila.mudar(p["id"], "entregue", de=("produzindo",))     # já entregue: não muda nem avisa de novo
    time.sleep(0.1)
    assert len(celular_de_mentira) == 1


def test_outro_estado_nao_avisa(db, celular_de_mentira):
    p = fila.criar(1, {"titulo": "T", "caracteres": 10620}, comecar=True)
    fila.mudar(p["id"], "erro", erro="x")
    time.sleep(0.1)
    assert celular_de_mentira == []
