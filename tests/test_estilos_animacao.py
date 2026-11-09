"""Os estilos de animação guardados na página Animações, sem rede."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, estilos_animacao as e  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    yield
    banco._CON.close()
    banco._CON = None


def test_guardar_trocar_e_apagar(db):
    e.salvar(1, "Escuro", {"tema": "noite"})
    e.salvar(1, "Claro", {"tema": "apple"})
    assert [x["nome"] for x in e.salvar(1, "escuro", {"tema": "neon"})] == ["escuro", "Claro"]   # mesmo nome troca
    assert e.listar(1)[0]["ajustes"] == {"tema": "neon"}
    assert [x["nome"] for x in e.apagar(1, "Claro")] == ["escuro"]


def test_cada_pessoa_ve_so_os_seus(db):
    e.salvar(1, "Meu", {"tema": "noite"})
    assert e.listar(2) == []


def test_recusa_sem_nome_e_acima_do_limite(db):
    with pytest.raises(ValueError):
        e.salvar(1, "   ", {})
    for i in range(e.LIMITE):
        e.salvar(1, f"E{i}", {})
    with pytest.raises(ValueError):
        e.salvar(1, "mais um", {})
    e.salvar(1, "E0", {"tema": "neon"})   # trocar um que já existe não conta como novo
