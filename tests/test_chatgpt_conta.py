"""Trocar a conta do ChatGPT em Integrações (pedido do usuário em 2026-11-02). Nada de rede: os logins são falsos, só
com o e-mail dentro do id_token, e a pasta do Codex é temporária."""
import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import chatgpt_conta, config  # noqa: E402


def _login(email):
    corpo = base64.urlsafe_b64encode(json.dumps({"email": email, "https://api.openai.com/auth": {
        "chatgpt_plan_type": "plus"}}).encode()).decode().rstrip("=")
    return {"auth_mode": "chatgpt", "tokens": {"id_token": f"x.{corpo}.y", "access_token": "a", "refresh_token": "r"}}


@pytest.fixture
def codex(tmp_path, monkeypatch):
    monkeypatch.setattr(chatgpt_conta, "PASTA", tmp_path / "codex")
    monkeypatch.setattr(chatgpt_conta, "GUARDADAS", tmp_path / "codex" / "contas-radar")
    monkeypatch.setattr(config, "FABRICA", tmp_path / "fabrica")
    (tmp_path / "fabrica").mkdir()
    chatgpt_conta._gravar(tmp_path / "codex" / "auth.json", _login("a@x.com"))
    (tmp_path / "fabrica" / "chatgpt_limites.json").write_text('{"janelas": {"janela": {"usado_pct": 73}}}')
    return tmp_path


def test_conta_nova_guarda_a_de_antes_com_o_limite_dela(codex):
    chatgpt_conta._guardar_a_atual()
    chatgpt_conta._ligar(_login("b@x.com"), None)
    c = chatgpt_conta.contas()
    assert c["atual"] == "b@x.com" and [g["email"] for g in c["guardadas"]] == ["a@x.com"]
    assert not (codex / "fabrica" / "chatgpt_limites.json").exists()   # o limite da A não vale para a B


def test_usar_a_guardada_troca_as_duas_de_lugar(codex):
    chatgpt_conta._guardar_a_atual()
    chatgpt_conta._ligar(_login("b@x.com"), None)
    c = chatgpt_conta.usar("a@x.com")
    assert c["atual"] == "a@x.com" and [g["email"] for g in c["guardadas"]] == ["b@x.com"]
    assert json.loads((codex / "fabrica" / "chatgpt_limites.json").read_text())["janelas"]["janela"]["usado_pct"] == 73


def test_nao_esquece_a_conta_ligada(codex):
    with pytest.raises(ValueError):
        chatgpt_conta.esquecer("a@x.com")


def test_o_login_aberto_manda_para_a_openai_com_a_volta_do_codex(codex):
    url = chatgpt_conta.comecar_login()["url"]
    try:
        assert url.startswith("https://auth.openai.com/oauth/authorize?")
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback" in url
        assert chatgpt_conta.contas()["login"]["estado"] == "aguardando"
    finally:
        chatgpt_conta.cancelar_login()
    assert chatgpt_conta.contas()["login"]["estado"] == "parado"


def test_a_volta_da_openai_liga_a_conta_nova_e_guarda_a_antiga(codex, monkeypatch):
    """A OpenAI devolve para localhost:1455 com o código; o Radar troca pelo login e a conta B entra no lugar."""
    import httpx
    monkeypatch.setattr(chatgpt_conta, "_trocar_codigo", lambda codigo, verificador: _login("b@x.com"))
    chatgpt_conta.comecar_login()
    try:
        errado = httpx.get("http://127.0.0.1:1455/auth/callback?code=c&state=outro", timeout=10)
        assert errado.status_code == 400 and chatgpt_conta.contas()["atual"] == "a@x.com"
        chatgpt_conta.comecar_login()
        state = chatgpt_conta._LOGIN["state"]
        certo = httpx.get(f"http://127.0.0.1:1455/auth/callback?code=c&state={state}", timeout=10)
        assert certo.status_code == 200
        c = chatgpt_conta.contas()
        assert c["atual"] == "b@x.com" and c["login"]["estado"] == "pronto"
        assert [g["email"] for g in c["guardadas"]] == ["a@x.com"]
    finally:
        chatgpt_conta.cancelar_login()
