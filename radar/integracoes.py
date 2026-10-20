"""A aba Integrações (pedido do usuário em 2026-10-18): o saldo de cada serviço e as chaves de API, para ver, testar,
trocar e remover sem abrir o .env. A chave inteira nunca sai daqui: a tela só recebe os 4 últimos caracteres.

As chaves do Radar (YouTube, Groq) ficam no .env onde já estão; uma chave nova vai para o .env do Radar. As da
fábrica vão pela rota dela (POST /api/config/chaves), que só aceita os nomes que conhece; o resto (o OpenRouter, as
chaves extras numeradas, remover) é gravado direto no .env da fábrica e vale quando ela reinicia."""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from dotenv import dotenv_values

from . import banco, config, fabrica_api, youtube

SERVICOS = [
    {"id": "youtube", "nome": "YouTube Data API", "dono": "radar", "env": "YOUTUBE_API_KEY", "varias": True,
     "obrigatoria": True, "para_que": "Garimpo, Procurar nicho, Alerta, medir canais e as views dos publicados.",
     "limite": "10.000 unidades por dia por chave (volta às 5 h de Brasília). Busca custa 100; ler 50 vídeos custa 1. "
               "Mais chaves, de outros projetos do Google Cloud, somam.",
     "onde": "https://console.cloud.google.com/apis/library/youtube.googleapis.com"},
    {"id": "groq", "nome": "Groq", "dono": "radar", "env": "GROQ_API_KEY", "varias": True, "obrigatoria": True,
     "para_que": "Nicho e rosto dos canais, traduções e as buscas em outras línguas (grátis).",
     "limite": "Limite por minuto e por dia de cada chave; com várias, o Radar reveza.",
     "onde": "https://console.groq.com/keys"},
    {"id": "openrouter", "nome": "OpenRouter", "dono": "fabrica", "env": "OpenRouter_key", "varias": False,
     "obrigatoria": True, "para_que": "Roteiro em cenas, escolha do material e as imagens de IA da fábrica.",
     "limite": "Gasta o saldo da conta OpenRouter; uma chave atende tudo.",
     "onde": "https://openrouter.ai/settings/keys"},
    {"id": "genaipro", "nome": "GenAI Pro", "dono": "fabrica", "env": "GENAIPRO_API", "varias": False,
     "obrigatoria": True, "para_que": "A narração com as vozes da ElevenLabs.",
     "limite": "Gasta créditos por caractere narrado; refazer a voz gasta de novo.",
     "onde": "https://genaipro.vn"},
    {"id": "gemini", "nome": "Gemini (Google)", "dono": "fabrica", "env": "GEMINI_API_KEY", "varias": True,
     "obrigatoria": False, "para_que": "Planejamento das cenas, visão e imagens do Nano Banana.",
     "limite": "Cota por minuto e por dia de cada chave; com várias, a fábrica reveza.",
     "onde": "https://aistudio.google.com/apikey"},
    {"id": "kie", "nome": "Kie.ai", "dono": "fabrica", "env": "KIE_API_KEY", "varias": False, "obrigatoria": False,
     "para_que": "Imagens de IA pelo Grok Imagine, quando escolhido como provedor.",
     "limite": "Gasta os créditos da conta Kie.", "onde": "https://kie.ai/api-key"},
    {"id": "pexels", "nome": "Pexels", "dono": "fabrica", "env": "PEXELS_API_KEY", "varias": True,
     "obrigatoria": False, "para_que": "Fotos e vídeos reais grátis para as cenas.",
     "limite": "200 pedidos por hora por chave; com várias, a fábrica reveza.",
     "onde": "https://www.pexels.com/api/"},
    {"id": "pixabay", "nome": "Pixabay", "dono": "fabrica", "env": "PIXABAY_API_KEY", "varias": False,
     "obrigatoria": False, "para_que": "Fotos e vídeos reais grátis para as cenas.",
     "limite": "100 pedidos por minuto.", "onde": "https://pixabay.com/api/docs/"},
]


def mascarar(valor: str) -> str:
    return "••••" + valor[-4:] if valor else ""


def mesclar_env(texto: str, novas: dict[str, str | None]) -> str:
    """O .env com as chaves trocadas no lugar, as novas no fim e as de valor None tiradas. Comentários e o resto ficam;
    uma chave repetida fica só na primeira linha."""
    restantes = dict(novas)
    vistas = set()
    saida = []
    for linha in texto.splitlines():
        crua = linha.strip()
        if crua and not crua.startswith("#") and "=" in crua:
            nome = crua.split("=", 1)[0].strip()
            if nome in novas:
                if nome not in vistas and novas[nome] is not None:
                    saida.append(f"{nome}={novas[nome]}")
                vistas.add(nome)
                restantes.pop(nome, None)
                continue
        saida.append(linha)
    saida += [f"{nome}={valor}" for nome, valor in restantes.items() if valor is not None]
    return "\n".join(saida) + "\n"


def nomes_numerados(prefixo: str, ambiente: dict) -> list[str]:
    """PREFIXO, PREFIXO1, PREFIXO2... que têm valor, na ordem: o sem número primeiro."""
    nomes = [n for n, v in ambiente.items() if v and re.fullmatch(re.escape(prefixo) + r"\d*", n)]
    return sorted(nomes, key=lambda n: int(n[len(prefixo):] or -1))


def gravar_env(arquivo: Path, env: str, valor: str | None) -> None:
    """Grava mantendo o fim de linha do arquivo (o write_text do Windows trocava \\n por \\r\\n)."""
    cru = arquivo.read_bytes().decode("utf-8") if arquivo.exists() else ""
    fim = "\r\n" if "\r\n" in cru else "\n"
    novo = mesclar_env(cru.replace("\r\n", "\n"), {env: valor})
    arquivo.write_bytes(novo.replace("\n", fim).encode("utf-8"))


def gravar_radar(env: str, valor: str | None, arquivo: Path | None = None) -> None:
    gravar_env(arquivo or config.RAIZ / ".env", env, valor)
    config.recarregar()


def arquivo_da_chave(env: str) -> Path | None:
    """Em qual .env a chave está (o do Radar vale por cima do da fábrica), ou None."""
    for arquivo in (config.RAIZ / ".env", config.FABRICA / ".env"):
        if arquivo.exists() and env in dotenv_values(arquivo):
            return arquivo
    return None


# ---------------------------------------------------------------- estado, saldos e testes

_TESTES: dict[str, dict] = {}       # env -> {"ok", "erro", "quando", "t"}; vale 1 hora
_SALDOS: dict[str, tuple] = {}      # servico -> (t, saldo); vale 10 minutos
UMA_HORA = 3600


def _servico(sid: str) -> dict:
    s = next((s for s in SERVICOS if s["id"] == sid), None)
    if not s:
        raise ValueError("Serviço desconhecido.")
    return s


def _chaves(s: dict) -> list[str]:
    if s["varias"]:
        return nomes_numerados(s["env"], config.AMBIENTE)
    return [s["env"]] if config.AMBIENTE.get(s["env"]) else []


def _saldo_externo(s: dict) -> dict | None:
    """O saldo pelas APIs que informam (OpenRouter, Kie). Guardado 10 minutos."""
    guardado = _SALDOS.get(s["id"])
    if guardado and time.time() - guardado[0] < 600:
        return guardado[1]
    chave = config.AMBIENTE.get(s["env"], "")
    saldo = None
    try:
        if s["id"] == "openrouter" and chave:
            d = httpx.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {chave}"},
                          timeout=15).json()["data"]
            valor = float(d["total_credits"]) - float(d["total_usage"])
            saldo = {"valor": round(valor, 2), "unidade": "US$", "texto": f"US$ {valor:.2f}".replace(".", ",")}
        elif s["id"] == "kie" and chave:
            d = httpx.get("https://api.kie.ai/api/v1/chat/credit", headers={"Authorization": f"Bearer {chave}"},
                          timeout=15).json()
            valor = float(d["data"])
            saldo = {"valor": valor, "unidade": "créditos", "texto": f"{valor:,.0f} créditos".replace(",", ".")}
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        saldo = {"valor": None, "unidade": "", "texto": "não consegui ler o saldo"}
    _SALDOS[s["id"]] = (time.time(), saldo)
    return saldo


def _saldo(s: dict, fabrica_ligada: bool) -> dict:
    if s["id"] == "youtube":
        c = youtube.cota_hoje()
        return {"valor": c["livre"], "unidade": "unidades", "informado": False,
                "texto": f"{c['livre']:,} de {c['total']:,} livres hoje".replace(",", ".")}
    if s["id"] == "genaipro":
        if not fabrica_ligada:
            return {"valor": None, "unidade": "", "informado": False, "texto": "fábrica desligada"}
        try:
            d = fabrica_api._pedir("GET", "/api/genaipro/creditos", tempo=20)
        except fabrica_api.SemFabrica as erro:
            return {"valor": None, "unidade": "", "informado": False, "texto": str(erro)}
        return {"valor": d.get("creditos"), "unidade": "créditos", "informado": False,
                "texto": f"{d.get('creditos', 0):,.0f} créditos · ~{d.get('minutos_de_narracao', 0)} min de narração".replace(",", ".")}
    if s["id"] in ("groq", "pexels", "pixabay"):
        return {"valor": None, "unidade": "", "informado": False, "texto": "Gratuito"}
    externo = _saldo_externo(s)
    if externo:
        return externo | {"informado": False}
    informado = banco.um("SELECT valor, quando FROM saldos_informados WHERE servico=?", s["id"])
    if informado:
        return {"valor": informado["valor"], "unidade": "US$", "informado": True,
                "texto": f"US$ {informado['valor']:.2f} (informado em {informado['quando'][:10]})".replace(".", ",", 1)}
    return {"valor": None, "unidade": "", "informado": True, "texto": "sem saldo pela API"}


def estado() -> dict:
    try:
        fabrica_api._pedir("GET", "/api/config/chaves", tempo=5)
        ligada = True
    except fabrica_api.SemFabrica:
        ligada = False
    with ThreadPoolExecutor(max_workers=len(SERVICOS)) as grupo:     # os saldos ao mesmo tempo: um por um levava 8 s
        saldos = list(grupo.map(lambda s: _saldo(s, ligada), SERVICOS))
    servicos = []
    for s, saldo in zip(SERVICOS, saldos):
        chaves = []
        for env in _chaves(s):
            arquivo = arquivo_da_chave(env)
            teste = _TESTES.get(env)
            valido = teste and time.time() - teste["t"] < UMA_HORA
            chaves.append({"env": env, "previa": mascarar(config.AMBIENTE.get(env, "")),
                           "arquivo": "radar" if arquivo == config.RAIZ / ".env" else "fabrica",
                           "teste": {k: teste[k] for k in ("ok", "erro", "quando")} if valido else None})
        servicos.append({k: s[k] for k in ("id", "nome", "dono", "varias", "obrigatoria", "para_que", "limite", "onde")}
                        | {"chaves": chaves, "saldo": saldo})
    return {"servicos": servicos, "fabrica_ligada": ligada}


def _chamar_teste(sid: str, chave: str) -> None:
    """Uma chamada barata que só passa com a chave certa. Levanta RuntimeError com o motivo."""
    if sid == "genaipro":
        if not fabrica_api._pedir("GET", "/api/genaipro/creditos", tempo=20).get("configurada"):
            raise RuntimeError("a fábrica não achou a chave da GenAI Pro")
        return
    bearer = {"Authorization": f"Bearer {chave}"}
    pedidos = {
        "youtube": ("https://www.googleapis.com/youtube/v3/videos", {"part": "id", "id": "dQw4w9WgXcQ", "key": chave}, {}),
        "groq": ("https://api.groq.com/openai/v1/models", {}, bearer),
        "openrouter": ("https://openrouter.ai/api/v1/credits", {}, bearer),
        "gemini": ("https://generativelanguage.googleapis.com/v1beta/models", {"key": chave, "pageSize": 1}, {}),
        "kie": ("https://api.kie.ai/api/v1/chat/credit", {}, bearer),
        "pexels": ("https://api.pexels.com/v1/curated", {"per_page": 1}, {"Authorization": chave}),
        "pixabay": ("https://pixabay.com/api/", {"key": chave, "q": "cat", "per_page": 3}, {}),
    }
    url, params, cabecalhos = pedidos[sid]
    r = httpx.get(url, params=params, headers=cabecalhos, timeout=15)
    if r.status_code >= 400:
        raise RuntimeError(f"recusada ({r.status_code})")
    if sid == "kie" and r.json().get("code") not in (200, None):
        raise RuntimeError(r.json().get("msg") or "recusada")


def testar(sid: str, indice: int = 0) -> dict:
    s = _servico(sid)
    chaves = _chaves(s)
    if not 0 <= indice < len(chaves):
        raise ValueError("Essa chave não existe.")
    env = chaves[indice]
    try:
        _chamar_teste(sid, config.AMBIENTE[env])
        resultado = {"ok": True, "erro": ""}
    except (httpx.HTTPError, RuntimeError, fabrica_api.SemFabrica, ValueError, KeyError) as erro:
        resultado = {"ok": False, "erro": str(erro) or "falhou"}
    _TESTES[env] = resultado | {"quando": banco.agora(), "t": time.time()}
    return resultado


def _proximo_nome(s: dict) -> str:
    existentes = _chaves(s)
    if not existentes:
        return s["env"]
    return f"{s['env']}{max(int(n[len(s['env']):] or 1) for n in existentes) + 1}"


def _limpo(valor: str) -> str:
    valor = (valor or "").strip()
    if not valor or any(c.isspace() for c in valor) or "#" in valor:
        raise ValueError("Cole só a chave, sem espaços.")
    return valor


def gravar(sid: str, valor: str, indice: int | None = None) -> dict:
    """Troca a chave de número `indice` ou acrescenta uma (None). Devolve o estado e um aviso, quando precisa."""
    s = _servico(sid)
    valor = _limpo(valor)
    chaves = _chaves(s)
    if indice is None and chaves and not s["varias"]:
        indice = 0
    env = chaves[indice] if indice is not None and 0 <= indice < len(chaves) else _proximo_nome(s)
    aviso = ""
    arquivo = arquivo_da_chave(env)
    if s["dono"] == "radar" or arquivo == config.RAIZ / ".env":
        gravar_env(arquivo or config.RAIZ / ".env", env, valor)
    else:
        conhecidas = {c["env"] for c in fabrica_api._pedir("GET", "/api/config/chaves").get("chaves", [])}
        if env in conhecidas:
            fabrica_api._pedir("POST", "/api/config/chaves", {"chaves": {env: valor}})
        else:
            gravar_env(config.FABRICA / ".env", env, valor)
            aviso = "Gravada no .env da fábrica: vale depois de reiniciar a fábrica."
    config.recarregar()
    _TESTES.pop(env, None)
    _SALDOS.pop(sid, None)
    return estado() | {"aviso": aviso}


def remover(sid: str, indice: int) -> dict:
    s = _servico(sid)
    chaves = _chaves(s)
    if not 0 <= indice < len(chaves):
        raise ValueError("Essa chave não existe.")
    env = chaves[indice]
    arquivo = arquivo_da_chave(env)
    if arquivo:
        gravar_env(arquivo, env, None)
    config.recarregar()
    _TESTES.pop(env, None)
    _SALDOS.pop(sid, None)
    aviso = "Tirada do .env da fábrica: vale depois de reiniciar a fábrica." if arquivo == config.FABRICA / ".env" else ""
    return estado() | {"aviso": aviso}


def informar_saldo(sid: str, valor: float) -> dict:
    _servico(sid)
    banco.executar("INSERT OR REPLACE INTO saldos_informados (servico, valor, quando) VALUES (?,?,?)",
                   sid, float(valor), banco.agora())
    return estado()
