"""Canais parecidos: a busca sai das palavras do assunto e só fica quem fala do mesmo assunto nos títulos (sem cota).

Caso real (2026-10-27): no Canada Insight (marcas de supermercado no Canadá) 20 dos 24 parecidos eram audiolivro,
cabelo crespo, academia e novela chinesa."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, garimpo  # noqa: E402

CANAL = "UC" + "c" * 22
CANADA = ["10 Butter Brands Canadians Should AVOID (And 5 Worth Buying)",
          "6 marcas de manteiga para evitar e 4 que são realmente manteiga de verdade no Canadá.",
          "7 marcas de sorvete para evitar e 3 que são feitas com creme de verdade no Canadá.",
          "Canadians Should AVOID These Yogurt Brands",
          "13 Costco Canada Rules Coming This Fall"]


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    yield
    banco._CON.close()
    banco._CON = None


def _videos(canal_id, titulos):
    for n, t in enumerate(titulos):
        banco.gravar("videos", "id", {"id": f"{canal_id[-4:]}{n:03d}", "canal_id": canal_id, "titulo": t,
                                      "duracao_s": 900, "views": 1000 - n, "publicado": "2026-10-01"})


def test_busca_sao_as_palavras_do_assunto_por_lingua(db):
    _videos(CANAL, CANADA)
    assunto = garimpo._assunto_do_canal(CANAL)
    assert {"brands", "avoid", "canadians", "marcas", "evitar"} <= assunto and "2026" not in assunto
    buscas = garimpo._busca_do_canal(CANAL, assunto)
    assert buscas[0] == ("Brands Canadians Should AVOID", "en")
    assert all("(" not in b and not any(c.isdigit() for c in b) for b, _ in buscas)
    assert len(buscas) <= garimpo.BUSCAS_PARECIDOS


def test_so_fica_quem_fala_do_mesmo_assunto(db):
    _videos(CANAL, CANADA)
    assunto = garimpo._assunto_do_canal(CANAL)
    audiolivro = "UC" + "d" * 22
    _videos(audiolivro, ["Footprints by Kay Cleaver Strahan | Full Audiobook", "Carmen by Prosper Mérimée | Novella"])
    marcas = "UC" + "e" * 22
    _videos(marcas, ["8 Coffee Brands Canadians Should AVOID", "Worst Canadian Grocery Brands to Avoid", "My vlog"])
    assert garimpo.parecenca_do_canal(audiolivro, assunto) == 0
    assert garimpo.parecenca_do_canal(marcas, assunto) >= garimpo.MINIMO_PARECENCA
