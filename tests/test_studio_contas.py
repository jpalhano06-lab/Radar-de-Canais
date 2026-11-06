"""As conexões com o YouTube Studio: o que está valendo, o que venceu e o login que deixa trocar de conta."""
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, studio  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    banco.um("SELECT 1")
    yield
    banco._CON.close()
    banco._CON = None


def _conta(canal, titulo):
    banco.executar("INSERT INTO studio (usuario_id, canal_id, titulo, refresh_token, access_token, expira, conectado) "
                   "VALUES (1,?,?,'r','a',0,'')", canal, titulo)


def test_diz_qual_venceu(db, monkeypatch):
    _conta("A", "Vale")
    _conta("B", "Venceu")

    def token(_u, canal):
        if canal == "B":
            raise PermissionError("venceu")
        return "t"

    monkeypatch.setattr(studio, "_token", token)
    assert studio.contas(1) == [{"canal_id": "A", "titulo": "Vale", "valida": True},
                                {"canal_id": "B", "titulo": "Venceu", "valida": False}]


def test_excluir_tira_so_aquela_conta(db):
    _conta("A", "Um")
    _conta("B", "Dois")
    studio.desconectar(1, "A")
    assert studio.conectados(1) == ["B"]


def test_o_login_deixa_escolher_outra_conta():
    prompt = parse_qs(urlparse(studio.url_login(1, "http://x")).query)["prompt"][0]
    assert "select_account" in prompt and "consent" in prompt
