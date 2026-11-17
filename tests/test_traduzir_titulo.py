"""O botão Traduzir da extensão: o título em português, e o mesmo título nunca vai duas vezes ao modelo."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, ia  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    yield
    banco._CON.close()
    banco._CON = None


def test_traduz_e_guarda(db, monkeypatch):
    pedidos = []

    def modelo(_m, _s, conteudo, **_k):
        pedidos.append(conteudo)
        return {"traducoes": [f"pt {i}" for i, _ in enumerate(conteudo.splitlines())]}
    monkeypatch.setattr(ia, "_perguntar", modelo)
    assert ia.para_portugues(["한국 열차", "日本の列車"]) == ["pt 0", "pt 1"]
    assert ia.para_portugues(["日本の列車", "한국 열차"]) == ["pt 1", "pt 0"]
    assert len(pedidos) == 1


def test_modelo_fora_do_ar_devolve_vazio(db, monkeypatch):
    monkeypatch.setattr(ia, "_perguntar", lambda *a, **k: None)
    assert ia.para_portugues(["한국 열차"]) == [""]


def test_tira_o_numero_da_linha_mas_nao_o_do_titulo(db, monkeypatch):
    """O pedido vai numerado; quando o modelo devolve o número junto ele sai, mas o título que é mesmo
    "10) ..." continua inteiro."""
    monkeypatch.setattr(ia, "_perguntar", lambda *a, **k: {"traducoes": ["1. O trem sumiu", "2) Dez pontes", "10) Os segredos"]})
    assert ia.para_portugues(["列車", "橋", "10) 秘密"]) == ["O trem sumiu", "Dez pontes", "10) Os segredos"]
