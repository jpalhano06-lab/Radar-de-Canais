"""Trocar a conta do ChatGPT que gera as imagens, direto em Integrações (pedido do usuário em 2026-11-02: "poder
integrar outra conta de chatgpt").

A fábrica lê o login em ~/.codex-fabrica/auth.json a cada imagem (fabrica/chatgpt_assinatura.py). O Radar faz o
mesmo login que o `codex login`: abre a página da OpenAI no navegador, a pessoa entra com a conta que quiser, a OpenAI
devolve para http://localhost:1455/auth/callback (o endereço que o Codex registrou, por isso a porta fixa) e o Radar
grava o login novo no auth.json da fábrica.

A pasta é só da fábrica desde 2026-11-02: antes era o ~/.codex, o mesmo do Robô do Dotti, e trocar a conta aqui
trocava a dele junto; os dois renovando o mesmo login fizeram a OpenAI revogá-lo (token_revoked) e o Dotti parou.

A conta que estava ligada não se perde: vai para ~/.codex-fabrica/contas-radar/<e-mail>.json, junto com o quanto ela
já tinha usado do limite, e volta com um clique ("Usar esta")."""
import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from . import config

PASTA = Path(os.environ.get("FABRICA_CODEX_HOME") or (Path.home() / ".codex-fabrica"))   # a mesma da fábrica
GUARDADAS = PASTA / "contas-radar"
EMISSOR = "https://auth.openai.com"
CLIENTE_CODEX = "app_EMoamEEZ73f0CkXaXp7hrann"   # o client_id publicado do Codex CLI, o mesmo da fábrica
PORTA = 1455
VOLTA = f"http://localhost:{PORTA}/auth/callback"
ESPERA = 10 * 60                                  # o login aberto e não terminado vence em 10 minutos

_trava = threading.Lock()
_LOGIN: dict = {"estado": "parado"}              # parado | aguardando | pronto | erro
_servidor: HTTPServer | None = None


def _login() -> Path:
    return PASTA / "auth.json"


def _limites() -> Path:
    """O quanto já foi usado do limite, que a fábrica guarda. É da conta ligada, então viaja junto com ela."""
    return config.FABRICA / "chatgpt_limites.json"


def _jwt(token: str) -> dict:
    partes = (token or "").split(".")
    if len(partes) < 2:
        return {}
    try:
        return json.loads(base64.urlsafe_b64decode(partes[1] + "=" * (-len(partes[1]) % 4)))
    except (ValueError, TypeError):
        return {}


def _quem(dados: dict) -> dict:
    """E-mail e plano de um login, lidos do id_token (sem conferir assinatura: é só para mostrar)."""
    claims = _jwt(((dados or {}).get("tokens") or {}).get("id_token") or "")
    plano = str((claims.get("https://api.openai.com/auth") or {}).get("chatgpt_plan_type") or "")
    return {"email": claims.get("email") or "", "plano": plano}


def _ler(arquivo: Path) -> dict:
    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar(arquivo: Path, dados: dict) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    temporario = arquivo.with_suffix(".gravando")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(arquivo)


def _nome_guardado(email: str) -> Path:
    return GUARDADAS / (re.sub(r"[^\w.@-]", "_", email.lower()) + ".json")


def _guardar_a_atual() -> None:
    """Põe a conta ligada agora (e o limite usado dela) na gaveta, antes de outra entrar no lugar."""
    atual = _ler(_login())
    email = _quem(atual)["email"]
    if not email:
        return
    limites = _ler(_limites())
    _gravar(_nome_guardado(email), {"login": atual, "limites": limites, "guardada": time.time()})


def _ligar(login: dict, limites: dict | None) -> None:
    _gravar(_login(), login)
    try:
        if limites:
            _gravar(_limites(), limites)
        else:
            _limites().unlink(missing_ok=True)   # o limite da conta anterior não vale para esta
    except OSError:
        pass


def contas() -> dict:
    """A conta ligada e as guardadas, para a tela."""
    atual = _quem(_ler(_login()))["email"]
    guardadas = []
    for arquivo in sorted(GUARDADAS.glob("*.json")) if GUARDADAS.exists() else []:
        q = _quem(_ler(arquivo).get("login") or {})
        if q["email"] and q["email"] != atual:
            guardadas.append(q)
    with _trava:
        login = {k: v for k, v in _LOGIN.items() if k in ("estado", "erro", "email", "url")}
    return {"atual": atual, "guardadas": guardadas, "login": login}


def usar(email: str) -> dict:
    """Liga de novo uma conta guardada; a que estava ligada vai para a gaveta."""
    guardada = _ler(_nome_guardado(email))
    if not guardada.get("login"):
        raise ValueError("Essa conta não está guardada. Conecte de novo pelo botão.")
    _guardar_a_atual()
    _ligar(guardada["login"], guardada.get("limites"))
    _nome_guardado(email).unlink(missing_ok=True)
    return contas()


def esquecer(email: str) -> dict:
    """Tira uma conta guardada da gaveta (a ligada não sai por aqui)."""
    if email and email == contas()["atual"]:
        raise ValueError("Essa é a conta ligada agora. Ligue outra antes de esquecer esta.")
    _nome_guardado(email).unlink(missing_ok=True)
    return contas()


# ---------------------------------------------------------------- o login novo, pelo navegador


def _base64url(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def _trocar_codigo(codigo: str, verificador: str) -> dict:
    r = httpx.post(f"{EMISSOR}/oauth/token", timeout=30,
                   headers={"Content-Type": "application/x-www-form-urlencoded"},
                   data={"grant_type": "authorization_code", "code": codigo, "redirect_uri": VOLTA,
                         "client_id": CLIENTE_CODEX, "code_verifier": verificador})
    if r.status_code != 200:
        raise RuntimeError(f"A OpenAI recusou o login ({r.status_code}): {r.text[:200]}")
    t = r.json()
    conta = (_jwt(t.get("id_token") or "").get("https://api.openai.com/auth") or {}).get("chatgpt_account_id") or ""
    return {"auth_mode": "chatgpt", "OPENAI_API_KEY": None,
            "tokens": {"id_token": t.get("id_token"), "access_token": t.get("access_token"),
                       "refresh_token": t.get("refresh_token"), "account_id": conta},
            "last_refresh": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")}


def _pagina(titulo: str, texto: str) -> bytes:
    return (f"<!doctype html><meta charset=utf-8><title>{titulo}</title><body style='font:16px system-ui;"
            f"max-width:520px;margin:80px auto;padding:0 16px'><h2>{titulo}</h2><p>{texto}</p>").encode()


class _Volta(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/auth/callback":
            self.send_response(404)
            self.end_headers()
            return
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        with _trava:
            esperado = dict(_LOGIN)
        try:
            if q.get("error"):
                raise RuntimeError(q.get("error_description") or q["error"])
            if not esperado.get("state") or q.get("state") != esperado["state"]:
                raise RuntimeError("Este login não foi aberto pelo Radar (o código de conferência não bate).")
            novo = _trocar_codigo(q.get("code") or "", esperado["verificador"])
            email = _quem(novo)["email"]
            guardada = _ler(_nome_guardado(email)) if email else {}
            if email != _quem(_ler(_login()))["email"]:
                _guardar_a_atual()
                _ligar(novo, guardada.get("limites"))
                _nome_guardado(email).unlink(missing_ok=True)
            else:
                _gravar(_login(), novo)          # a mesma conta: só renova o login
            with _trava:
                _LOGIN.update(estado="pronto", email=email, state="")
            corpo, codigo = _pagina("Conta do ChatGPT ligada", f"{email} já gera as imagens da fábrica. "
                                    "Pode fechar esta aba e voltar ao Radar."), 200
        except (RuntimeError, httpx.HTTPError) as erro:
            with _trava:
                _LOGIN.update(estado="erro", erro=str(erro)[:300], state="")
            corpo, codigo = _pagina("Não deu para ligar a conta", str(erro)[:300]), 400
        self.send_response(codigo)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corpo)
        threading.Thread(target=_parar, daemon=True).start()


def _parar() -> None:
    global _servidor
    with _trava:
        servidor, _servidor = _servidor, None
    if servidor:
        servidor.shutdown()
        servidor.server_close()


def comecar_login() -> dict:
    """Abre a porta 1455 para a volta da OpenAI e devolve o endereço do login para a tela abrir numa aba nova."""
    global _servidor
    _parar()
    verificador = _base64url(secrets.token_bytes(64))
    desafio = _base64url(hashlib.sha256(verificador.encode()).digest())
    state = _base64url(secrets.token_bytes(32))
    try:
        servidor = HTTPServer(("127.0.0.1", PORTA), _Volta)
    except OSError:
        raise ValueError(f"A porta {PORTA} está ocupada (talvez um `codex login` aberto). Feche e tente de novo.")
    url = f"{EMISSOR}/oauth/authorize?" + urlencode({
        "response_type": "code", "client_id": CLIENTE_CODEX, "redirect_uri": VOLTA,
        "scope": "openid profile email offline_access", "code_challenge": desafio, "code_challenge_method": "S256",
        "id_token_add_organizations": "true", "codex_cli_simplified_flow": "true", "state": state,
        "originator": "codex_cli_rs", "prompt": "login"})
    with _trava:
        _servidor = servidor
        _LOGIN.clear()
        _LOGIN.update(estado="aguardando", state=state, verificador=verificador, url=url, desde=time.time())
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    vencer = threading.Timer(ESPERA, _vencer, args=(state,))
    vencer.daemon = True                         # não segura o Radar aberto ao desligar
    vencer.start()
    return {"url": url}


def _vencer(state: str) -> None:
    with _trava:
        if _LOGIN.get("state") != state or _LOGIN.get("estado") != "aguardando":
            return
        _LOGIN.update(estado="erro", erro="O login ficou aberto mais de 10 minutos e venceu. Tente de novo.", state="")
    _parar()


def cancelar_login() -> dict:
    with _trava:
        _LOGIN.clear()
        _LOGIN["estado"] = "parado"
    _parar()
    return contas()
