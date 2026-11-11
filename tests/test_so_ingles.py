"""Só canal em inglês entra no Radar (pedido do usuário: "a pesquisa é sempre em inglês")."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, garimpo  # noqa: E402

PT = ["A história secreta do império que caiu", "Por que o Brasil não consegue sair da crise", "O mistério da ilha"]
EN = ["The secret history of the empire that fell", "Why the world is running out of water", "How this city vanished"]


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    yield
    banco._CON.close()
    banco._CON = None


def test_em_ingles():
    assert garimpo.em_ingles(EN)
    assert not garimpo.em_ingles(PT)               # o caso que vazava
    assert not garimpo.em_ingles(PT + EN[:1])      # inglês em minoria
    assert garimpo.em_ingles(["Top 10", "#1"])     # nenhum título de língua conhecida: não barra


def _canal(cid, pais, titulos, origem=""):
    banco.gravar("canais", "id", {"id": cid, "titulo": cid, "pais": pais, "no_radar": 1, "origem": origem})
    for i, t in enumerate(titulos):
        banco.gravar("videos", "id", {"id": f"{cid}{i}", "canal_id": cid, "titulo": t, "publicado": f"2026-11-0{i + 1}"})


def test_limpeza_tira_canal_portugues_e_deixa_o_manual(db):
    _canal("UCen", "US", EN)
    _canal("UCpt", "", PT)
    _canal("UCbr", "BR", EN)                       # canal do Brasil falando inglês fica
    _canal("UCmeu", "BR", PT, origem="manual")
    assert garimpo.tirar_fora_do_ingles(lambda *_: None) == 1
    ficaram = {c["id"] for c in banco.todos("SELECT id FROM canais WHERE no_radar=1")}
    assert ficaram == {"UCen", "UCbr", "UCmeu"}
