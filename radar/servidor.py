"""O servidor do Radar: contas, a API da extensão, o painel dos canais e a administração.

Rodar: python -m radar servidor (porta 8400) ou LIGAR-RADAR.bat."""
import base64
import binascii
import httpx
import json
import os
import secrets
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

from starlette.concurrency import run_in_threadpool
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import alvos, banco, canal_painel, custos, descricao, diagnostico, fabrica_api, fila, funcoes, garimpo, gosto, horarios, ia, integracoes, medir, mercado, metricas, nichos, pagina, perfil, producao, publicar, radar_paises, roteiro_claude, studio, tempo, thumb, trabalho, treinamento, youtube
from .config import DADOS, NOME, PLANOS, RAIZ, pode

WEB = RAIZ / "radar" / "web"
COOKIE = "radar_sessao"

app = FastAPI(title=NOME, docs_url=None, redoc_url=None)


# ---------------------------------------------------------------- contas

def _usuario_do_pedido(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    cabecalho = request.headers.get("authorization", "")
    if cabecalho.lower().startswith("bearer "):
        token = cabecalho[7:].strip()
    sessao = banco.um("SELECT usuario_id FROM sessoes WHERE token_hash=?", banco.hash_token(token)) if token else None
    if sessao:
        return banco.um("SELECT * FROM usuarios WHERE id=?", sessao["usuario_id"])
    return _usuario_livre(request)


def aberto() -> bool:
    """Acesso livre, sem e-mail e senha (pedido do usuário em 2026-10-14). Só vale com o servidor neste computador:
    com `--publico` (ou RADAR_ABERTO=0) a senha volta."""
    return os.environ.get("RADAR_ABERTO", "1") == "1"


def _usuario_livre(request: Request) -> dict | None:
    """Sem login, tudo é da conta da administração (a primeira); sem nenhuma conta, cria uma local. Pedido de fora deste
    computador nunca entra livre, nem com o acesso livre ligado (o túnel chega como localhost, mas traz o cabeçalho
    do endereço de verdade)."""
    if not aberto():
        return None
    origem = request.client.host if request.client else ""
    if origem not in ("127.0.0.1", "::1", "localhost") or request.headers.get("cf-connecting-ip") \
            or request.headers.get("x-forwarded-for"):
        return None
    u = banco.um("SELECT * FROM usuarios WHERE admin=1 ORDER BY id LIMIT 1")
    if not u:
        uid = banco.executar("INSERT INTO usuarios (email, nome, senha_hash, admin, plano, criado) VALUES (?,?,?,?,?,?)",
                             "local@radar", "Radar", banco.hash_senha(banco.novo_token()), 1, "pro", banco.agora())
        u = banco.um("SELECT * FROM usuarios WHERE id=?", uid)
    return u


def usuario(request: Request) -> dict:
    u = _usuario_do_pedido(request)
    if not u:
        raise HTTPException(401, "Entre na sua conta.")
    return u


def _plano(u: dict) -> str:
    if u["admin"]:
        return "pro"
    if u["plano"] != "gratis" and u["vence"] and u["vence"] < datetime.now(banco.BRASILIA).date().isoformat():
        return "gratis"
    return u["plano"] or "gratis"


def exigir(recurso: str):
    def checar(u: dict = Depends(usuario)) -> dict:
        if not pode(_plano(u), recurso):
            precisa = next(k for k, v in PLANOS.items() if recurso in v["recursos"])
            raise HTTPException(402, f"Isso é do plano {PLANOS[precisa]['nome']}.")
        return u
    return checar


def admin(u: dict = Depends(usuario)) -> dict:
    if not u["admin"]:
        raise HTTPException(403, "Só a administração.")
    return u


def dono_da_fabrica(u: dict = Depends(usuario)) -> dict:
    """O que gasta dinheiro ou mexe na fábrica (produzir, enviar, trocar a voz, gravar no perfil) é só da
    administração: os sócios que entram pela internet olham e pesquisam, mas não gastam (2026-10-15)."""
    if not u["admin"]:
        raise HTTPException(403, "Só a administração pode produzir ou mexer na fábrica. Você pode ver e pesquisar à vontade.")
    return u


def _de_fora(request: Request) -> bool:
    """Pedido que veio pela internet (o túnel da Cloudflare manda o endereço de verdade no cabeçalho)."""
    origem = request.client.host if request.client else ""
    return origem not in ("127.0.0.1", "::1", "localhost") or bool(request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for"))


def _sessao(usuario_id: int, tipo: str) -> str:
    token = banco.novo_token()
    banco.executar("INSERT INTO sessoes (token_hash, usuario_id, tipo, criado) VALUES (?,?,?,?)",
                   banco.hash_token(token), usuario_id, tipo, banco.agora())
    return token


def _https(request: Request) -> bool:
    """Só importa se um dia o site for posto na internet atrás de um proxy com https. Rodando no próprio computador
    (o normal), é sempre http e nada aqui precisa ser configurado."""
    return request.url.scheme == "https" or os.environ.get("RADAR_HTTPS") == "1"


def _com_cookie(request: Request, dados: dict, usuario_id: int) -> JSONResponse:
    resposta = JSONResponse(dados)
    resposta.set_cookie(COOKIE, _sessao(usuario_id, "site"), httponly=True, samesite="lax",
                        max_age=60 * 60 * 24 * 60, secure=_https(request))
    return resposta


# ---------------------------------------------------------------- senha errada demais: espera

ERROS_PERMITIDOS = 8          # por endereço, em 15 minutos
_ERROS: dict[str, list[float]] = {}
_TRAVA_ERROS = threading.Lock()


def _ip(request: Request) -> str:
    """O endereço de quem pede, para a espera depois de muitas senhas erradas. Atrás de um proxy na internet, o
    endereço de verdade vem num cabeçalho; no próprio computador, não precisa de nada."""
    origem = request.client.host if request.client else ""
    if origem in ("127.0.0.1", "::1") and request.headers.get("cf-connecting-ip"):
        return request.headers["cf-connecting-ip"]
    return origem


def _conferir_tentativas(request: Request) -> None:
    agora = time.time()
    with _TRAVA_ERROS:
        recentes = [t for t in _ERROS.get(_ip(request), []) if agora - t < 900]
        _ERROS[_ip(request)] = recentes
    if len(recentes) >= ERROS_PERMITIDOS:
        raise HTTPException(429, "Muitas tentativas erradas. Espere 15 minutos.")


def _anotar_erro(request: Request) -> None:
    with _TRAVA_ERROS:
        _ERROS.setdefault(_ip(request), []).append(time.time())


def _publico(u: dict) -> dict:
    plano = _plano(u)
    return {"id": u["id"], "email": u["email"], "nome": u["nome"], "admin": bool(u["admin"]), "plano": plano,
            "plano_nome": PLANOS[plano]["nome"], "vence": u["vence"], "recursos": PLANOS[plano]["recursos"]}


@app.post("/api/cadastro")
async def cadastro(request: Request):
    d = await request.json()
    email = str(d.get("email", "")).strip().lower()
    senha = str(d.get("senha", ""))
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "E-mail inválido.")
    if len(senha) < 8:
        raise HTTPException(400, "A senha precisa de pelo menos 8 caracteres.")
    if banco.um("SELECT id FROM usuarios WHERE email=?", email):
        raise HTTPException(400, "Já existe uma conta com esse e-mail.")
    primeira = banco.um("SELECT COUNT(*) AS n FROM usuarios")["n"] == 0   # a primeira conta é a administração
    # a primeira conta entra direto; as outras só com um convite gerado na Administração
    convite = None
    if not primeira:
        _conferir_tentativas(request)
        codigo = str(d.get("convite", "")).strip()
        convite = banco.um("SELECT * FROM convites WHERE codigo_hash=? AND usado_por IS NULL",
                           banco.hash_token(codigo)) if codigo else None
        if not convite:
            _anotar_erro(request)
            raise HTTPException(403, "Para criar conta você precisa do link de convite. Peça para a administração.")
    uid = banco.executar("INSERT INTO usuarios (email, nome, senha_hash, admin, plano, criado) VALUES (?,?,?,?,?,?)",
                         email, str(d.get("nome", "")).strip()[:80], banco.hash_senha(senha), int(primeira),
                         "pro", banco.agora())   # ainda não é para vender: toda conta abre tudo
    if convite:
        banco.executar("UPDATE convites SET usado_por=?, usado_em=? WHERE codigo_hash=?", uid, banco.agora(),
                       convite["codigo_hash"])
    return _com_cookie(request, {"ok": True, "admin": primeira}, uid)


def _conferir_senha(request: Request, d: dict) -> dict:
    _conferir_tentativas(request)
    u = banco.um("SELECT * FROM usuarios WHERE email=?", str(d.get("email", "")).strip().lower())
    if not u or not banco.senha_confere(str(d.get("senha", "")), u["senha_hash"]):
        _anotar_erro(request)
        raise HTTPException(401, "E-mail ou senha não conferem.")
    return u


@app.post("/api/entrar")
async def entrar(request: Request):
    u = _conferir_senha(request, await request.json())
    return _com_cookie(request, {"ok": True}, u["id"])


@app.post("/api/sair")
def sair(request: Request):
    token = request.cookies.get(COOKIE)
    if token:
        banco.executar("DELETE FROM sessoes WHERE token_hash=?", banco.hash_token(token))
    resposta = JSONResponse({"ok": True})
    resposta.delete_cookie(COOKIE)
    return resposta


@app.get("/api/eu")
def eu(u: dict = Depends(usuario)):
    return _publico(u) | {"livre": aberto()}


@app.get("/api/planos")
def planos(u: dict = Depends(usuario)):
    """Os planos e o preço de cada um. Pede conta de propósito: o preço aparece depois do cadastro, quando a
    pessoa já viu o Radar funcionando, e não antes de ela saber o que é."""
    return {"nome": NOME, "planos": PLANOS, "meu": _plano(u)}


# ---------------------------------------------------------------- depoimentos: quem usou, com o print do Studio
# Guardados aqui para a vitrine mostrar. Entram só pela administração, com o print que a pessoa mandou: o Radar
# não inventa depoimento nenhum, e enquanto ninguém gravar um a vitrine simplesmente não tem essa parte.

DEPOIMENTOS_PASTA = DADOS / "depoimentos"
PRINT_MAXIMO = 4 * 1024 * 1024
PRINT_TIPOS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _depoimento_publico(d: dict) -> dict:
    return {"id": d["id"], "nome": d["nome"], "canal": d["canal"], "resultado": d["resultado"],
            "texto": d["texto"], "quando": d["quando"],
            "print": f"/api/depoimentos/{d['id']}/print" if d["print"] else ""}


@app.get("/api/depoimentos")
def depoimentos():
    """Os depoimentos que a administração marcou para mostrar. Público: é o que a vitrine exibe."""
    linhas = banco.todos("SELECT * FROM depoimentos WHERE mostrar=1 ORDER BY quando DESC LIMIT 24")
    return {"depoimentos": [_depoimento_publico(d) for d in linhas]}


@app.get("/api/depoimentos/{dep_id}/print")
def depoimento_print(dep_id: int):
    d = banco.um("SELECT print, mostrar FROM depoimentos WHERE id=?", dep_id)
    if not d or not d["print"] or not d["mostrar"]:
        raise HTTPException(404, "Sem print.")
    arquivo = DEPOIMENTOS_PASTA / d["print"]          # o nome é gerado aqui, nunca vem de fora
    if not arquivo.is_file():
        raise HTTPException(404, "Sem print.")
    return FileResponse(arquivo)


@app.get("/api/admin/depoimentos")
def depoimentos_todos(u: dict = Depends(admin)):
    return {"depoimentos": [_depoimento_publico(d) | {"mostrar": bool(d["mostrar"])}
                            for d in banco.todos("SELECT * FROM depoimentos ORDER BY quando DESC")]}


@app.post("/api/admin/depoimentos")
async def depoimento_novo(request: Request, u: dict = Depends(admin)):
    """Um depoimento de verdade, com o print do Studio em base64 (data URL), se houver."""
    d = await request.json()
    nome = str(d.get("nome", "")).strip()[:80]
    if not nome:
        raise HTTPException(400, "Diga o nome de quem está falando.")
    dep_id = banco.executar(
        "INSERT INTO depoimentos (nome, canal, resultado, texto, print, quando, mostrar) VALUES (?,?,?,?,'',?,1)",
        nome, str(d.get("canal", "")).strip()[:80], str(d.get("resultado", "")).strip()[:120],
        str(d.get("texto", "")).strip()[:1200], banco.agora())
    nome_arquivo = _guardar_print(dep_id, str(d.get("print", "")))
    if nome_arquivo:
        banco.executar("UPDATE depoimentos SET print=? WHERE id=?", nome_arquivo, dep_id)
    _VITRINE["dados"] = None
    return {"ok": True, "id": dep_id}


def _guardar_print(dep_id: int, data_url: str) -> str:
    """A imagem que veio como data URL. Só os tipos da lista e até 4 MiB; o nome do arquivo é nosso."""
    if not data_url.startswith("data:"):
        return ""
    cabeca, _, corpo = data_url.partition(",")
    tipo = cabeca[5:].split(";")[0].strip().lower()
    if tipo not in PRINT_TIPOS or ";base64" not in cabeca:
        raise HTTPException(400, "O print precisa ser uma imagem JPEG, PNG ou WebP.")
    try:
        bytes_ = base64.b64decode(corpo, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(400, "Não consegui ler a imagem do print.") from None
    if len(bytes_) > PRINT_MAXIMO:
        raise HTTPException(400, f"O print passa de {PRINT_MAXIMO // (1024 * 1024)} MB.")
    DEPOIMENTOS_PASTA.mkdir(parents=True, exist_ok=True)
    nome = f"{dep_id}.{PRINT_TIPOS[tipo]}"
    (DEPOIMENTOS_PASTA / nome).write_bytes(bytes_)
    return nome


@app.post("/api/admin/depoimentos/{dep_id}")
async def depoimento_mostrar(dep_id: int, request: Request, u: dict = Depends(admin)):
    mostrar = 1 if (await request.json()).get("mostrar") else 0
    if not banco.mudou("UPDATE depoimentos SET mostrar=? WHERE id=?", mostrar, dep_id):
        raise HTTPException(404, "Depoimento não encontrado.")
    _VITRINE["dados"] = None
    return {"ok": True, "mostrar": bool(mostrar)}


@app.delete("/api/admin/depoimentos/{dep_id}")
def depoimento_apagar(dep_id: int, u: dict = Depends(admin)):
    d = banco.um("SELECT print FROM depoimentos WHERE id=?", dep_id)
    if not d:
        raise HTTPException(404, "Depoimento não encontrado.")
    banco.executar("DELETE FROM depoimentos WHERE id=?", dep_id)
    if d["print"]:
        (DEPOIMENTOS_PASTA / d["print"]).unlink(missing_ok=True)
    _VITRINE["dados"] = None
    return {"ok": True}


@app.get("/api/abertura")
def abertura(request: Request):
    """Tudo o que a primeira tela precisa, numa chamada só, em vez das oito que o painel fazia ao abrir.

    Cada chave é o caminho que o painel pediria: o `api()` do front serve a resposta daqui na primeira vez que
    aquele caminho for pedido e depois volta a falar com o servidor. Sem sessão vem só o que é público — a tela
    de entrar não precisa de mais nada —, e o que o plano não abre fica de fora em vez de dar erro."""
    pacote = {"resumo": resumo()}
    u = _usuario_do_pedido(request)
    if not u:
        pacote["vitrine"] = vitrine_publica()   # a tela de entrar é a única que ele vai ver: já vai com ela
        return {"pacote": pacote}
    plano = _plano(u)
    pacote["eu"] = _publico(u) | {"livre": aberto()}
    pacote["prefs"] = ver_prefs(u)
    pacote["painel"] = ver_painel(u)
    pacote["alvos"] = alvos_lista(u)
    if pode(plano, "radar"):
        pacote["filtros"] = filtros(u)
        pacote["visoes"] = visoes(u)
    if pode(plano, "salvar"):
        pacote["pastas"] = pastas(u)
    return {"pacote": pacote}


# ---------------------------------------------------------------- extensão

@app.post("/api/ext/entrar")
async def ext_entrar(request: Request):
    """A extensão entra com e-mail e senha e guarda um token próprio (o cookie do site não serve para ela)."""
    u = _conferir_senha(request, await request.json())
    return {"token": _sessao(u["id"], "extensao"), "eu": _publico(u)}


@app.post("/api/ext/sair")
def ext_sair(request: Request):
    cabecalho = request.headers.get("authorization", "")
    if cabecalho.lower().startswith("bearer "):
        banco.executar("DELETE FROM sessoes WHERE token_hash=?", banco.hash_token(cabecalho[7:].strip()))
    return {"ok": True}


def _sem_cota(erro: youtube.SemCota):
    raise HTTPException(503, str(erro))


@app.post("/api/ext/videos")
async def ext_videos(request: Request, u: dict = Depends(exigir("extensao"))):
    ids = [str(i) for i in (await request.json()).get("ids", [])][:120]
    try:
        return {"videos": medir.medir_videos(ids)}
    except youtube.SemCota as erro:
        _sem_cota(erro)


@app.post("/api/ext/vistos")
async def ext_vistos(request: Request, u: dict = Depends(exigir("extensao"))):
    """Os vídeos que o YouTube mostrou na tela, lidos da própria página pela extensão (não gasta cota)."""
    d = await request.json()
    return pagina.vistos(d.get("videos") or [], d.get("canal"))


@app.post("/api/ext/canal-lido")
async def ext_canal_lido(request: Request, u: dict = Depends(exigir("extensao"))):
    """A página de vídeos de um canal novo, baixada pela extensão: o normal dele e, se passar, o Radar (sem cota)."""
    d = await request.json()
    return pagina.canal_lido(d.get("canal") or {}, d.get("videos") or [])


@app.get("/api/ext/painel/{video_id}")
def ext_painel(video_id: str, canal: str = "", u: dict = Depends(exigir("extensao"))):
    """O painel do vídeo aberto com o que o banco já tem: o canal, a curva de views e se está salvo (sem cota)."""
    return {**pagina.painel(video_id, canal, u["id"]), "plano": _plano(u)}


@app.get("/api/ext/canal-dados/{canal_id}")
def ext_canal_dados(canal_id: str, u: dict = Depends(exigir("extensao"))):
    """A página do canal no YouTube: o que o banco já tem (sem cota). 404 = a extensão lê a página do canal antes."""
    d = pagina.canal_dados(canal_id, u["id"])
    if not d:
        raise HTTPException(404, "O Radar ainda não leu este canal.")
    return d


@app.get("/api/ext/horarios/{canal_id}")
def ext_horarios(canal_id: str, fuso: int = horarios.FUSO_PADRAO, u: dict = Depends(exigir("extensao"))):
    """O melhor horário para postar neste canal, das curvas que o Radar já guarda (sem cota, sem rede).

    Vai no plano grátis de propósito: é a conta que a vidIQ cobra no Pro e, sem dado do canal, inventa. O `fuso` são
    os minutos de diferença do UTC; a extensão manda o do navegador. Sem curva suficiente a resposta vem com
    `suficiente` falso e sem pico, e a tela não desenha faixa nenhuma."""
    return horarios.do_canal(canal_id, max(-840, min(840, fuso)))


@app.get("/api/ext/em-alta")
def ext_em_alta(u: dict = Depends(exigir("extensao"))):
    return {"canais": pagina.em_alta()}


@app.get("/api/ext/hoje")
def ext_hoje(u: dict = Depends(exigir("extensao"))):
    return pagina.hoje()


@app.get("/api/ext/funcoes")
def ext_funcoes(u: dict = Depends(exigir("extensao"))):
    """As funções da extensão, numa fonte só: a tela de ajuda, a tela de planos e a extensão leem daqui.

    Cada função já vem com o plano que a abre e, para quem está pedindo, se está liberada."""
    return {"funcoes": funcoes.lista(_plano(u)), "onde": funcoes.ONDE, "contagem": funcoes.contagem()}


@app.get("/api/ext/video/{video_id}")
def ext_video(video_id: str, u: dict = Depends(exigir("extensao"))):
    try:
        dados = medir.medir_videos([video_id]).get(video_id)
    except youtube.SemCota as erro:
        _sem_cota(erro)
    if not dados:
        raise HTTPException(404, "Vídeo não encontrado.")
    v = banco.um("SELECT titulo, tags FROM videos WHERE id=?", video_id) or {}
    salvo = bool(dados["canal"] and banco.um("SELECT 1 AS x FROM salvos WHERE usuario_id=? AND canal_id=?",
                                            u["id"], dados["canal"]["id"]))
    return {**dados, "titulo": v.get("titulo", ""), "tags": json.loads(v.get("tags") or "[]"),
            "curva": medir.curva(video_id), "salvo": salvo, "plano": _plano(u),
            "capa": f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"}


@app.get("/api/ext/canal/{ref}")
def ext_canal(ref: str, u: dict = Depends(exigir("extensao"))):
    try:
        if ref.startswith("@"):
            with youtube.gastando("medir"):
                achado = youtube.canal_por_handle(ref)
            if not achado:
                raise HTTPException(404, "Canal não encontrado.")
            ref = achado["id"]
        c = medir.canal_completo(ref)
    except youtube.SemCota as erro:
        _sem_cota(erro)
    if not c:
        raise HTTPException(404, "Canal não encontrado.")
    c["salvo"] = bool(banco.um("SELECT 1 AS x FROM salvos WHERE usuario_id=? AND canal_id=?", u["id"], c["id"]))
    return c


@app.post("/api/ext/salvar/{canal_id}")
def salvar(canal_id: str, u: dict = Depends(exigir("salvar"))):
    banco.executar("INSERT OR IGNORE INTO salvos (usuario_id, canal_id, criado) VALUES (?,?,?)",
                   u["id"], canal_id, banco.agora())
    banco.executar("DELETE FROM achados WHERE usuario_id=? AND canal_id=?", u["id"], canal_id)
    return {"ok": True, "salvo": True}


@app.delete("/api/ext/salvar/{canal_id}")
def tirar(canal_id: str, u: dict = Depends(exigir("salvar"))):
    banco.executar("DELETE FROM salvos WHERE usuario_id=? AND canal_id=?", u["id"], canal_id)
    return {"ok": True, "salvo": False}


# ---------------------------------------------------------------- pastas: a base organizada por projeto
# Uma pasta por canal salvo. O nome é a pasta: não há tabela de pastas, a lista delas sai de quem está guardado,
# então renomear é só trocar o nome nos canais e a pasta vazia some sozinha.

PASTA_MAX = 40


@app.get("/api/pastas")
def pastas(u: dict = Depends(exigir("salvar"))):
    """As pastas da pessoa, com quantos canais tem cada uma, e quantos salvos ainda estão fora de pasta."""
    linhas = banco.todos("SELECT pasta AS nome, COUNT(*) AS canais FROM salvos WHERE usuario_id=? AND pasta<>'' "
                         "GROUP BY pasta ORDER BY pasta COLLATE NOCASE", u["id"])
    soltos = banco.um("SELECT COUNT(*) AS n FROM salvos WHERE usuario_id=? AND pasta=''", u["id"])["n"]
    return {"pastas": linhas, "sem_pasta": soltos}


@app.post("/api/salvos/{canal_id}/pasta")
async def pasta_do_canal(canal_id: str, request: Request, u: dict = Depends(exigir("salvar"))):
    """Põe o canal numa pasta. Pasta em branco tira ele da pasta, sem tirar da base."""
    nome = str((await request.json()).get("pasta", "")).strip()[:PASTA_MAX]
    mudou = banco.mudou("UPDATE salvos SET pasta=? WHERE usuario_id=? AND canal_id=?", nome, u["id"], canal_id)
    if not mudou:
        raise HTTPException(404, "Este canal não está na sua base: salve ele antes de pôr numa pasta.")
    return {"ok": True, "pasta": nome}


@app.post("/api/pastas/renomear")
async def renomear_pasta(request: Request, u: dict = Depends(exigir("salvar"))):
    d = await request.json()
    de, para = str(d.get("de", "")).strip(), str(d.get("para", "")).strip()[:PASTA_MAX]
    if not de:
        raise HTTPException(400, "Diga qual pasta renomear.")
    n = banco.mudou("UPDATE salvos SET pasta=? WHERE usuario_id=? AND pasta=?", para, u["id"], de)
    return {"ok": True, "canais": n}


# ---------------------------------------------------------------- a esteira: o que eu vou modelar e o que já modelei

ESTEIRA = ("fila", "feito")


@app.get("/api/modelar")
def esteira(u: dict = Depends(exigir("outliers"))):
    contas = {e: 0 for e in ESTEIRA}
    for l in banco.todos("SELECT estado, COUNT(*) AS n FROM modelar WHERE usuario_id=? GROUP BY estado", u["id"]):
        if l["estado"] in contas:
            contas[l["estado"]] = l["n"]
    return {"contas": contas}


@app.post("/api/modelar/{video_id}")
async def marcar_modelar(video_id: str, request: Request, u: dict = Depends(exigir("outliers"))):
    """`fila` = vou modelar, `feito` = já modelei, vazio = tira o marcador."""
    estado = str((await request.json()).get("estado", ""))
    if estado and estado not in ESTEIRA:
        raise HTTPException(400, "Estado desconhecido para a esteira.")
    if estado:
        banco.executar("INSERT INTO modelar (usuario_id, video_id, estado, quando) VALUES (?,?,?,?) "
                       "ON CONFLICT(usuario_id, video_id) DO UPDATE SET estado=excluded.estado, quando=excluded.quando",
                       u["id"], video_id, estado, banco.agora())
    else:
        banco.executar("DELETE FROM modelar WHERE usuario_id=? AND video_id=?", u["id"], video_id)
    return {"ok": True, "estado": estado}


@app.get("/api/ext/parecidos/{canal_id}")
def ext_parecidos(canal_id: str, u: dict = Depends(exigir("parecidos"))):
    try:
        # cada parecido com os vídeos mais novos dele (do banco): a aba Canais Parecidos mostra lado a lado
        return {"canais": [{**c, "videos": garimpo.ultimos_videos(c["id"], 5)} for c in garimpo.parecidos(canal_id)]}
    except youtube.SemCota as erro:
        _sem_cota(erro)


@app.get("/api/ext/concorrentes/{canal_id}")
def ext_concorrentes(canal_id: str, medir: int = 0, u: dict = Depends(exigir("parecidos"))):
    """Os concorrentes do nicho e a nota (Analisar nicho). medir=1 procura os parecidos se ainda não tiver (cota)."""
    try:
        return garimpo.concorrentes(canal_id, medir_agora=bool(medir))
    except youtube.SemCota as erro:
        _sem_cota(erro)


@app.get("/api/ext/nicho-videos/{canal_id}")
def ext_nicho_videos(canal_id: str, u: dict = Depends(exigir("parecidos"))):
    """A aba Vídeos do Nicho da página do canal: o que estourou nos canais parecidos (do banco)."""
    try:
        return {"videos": garimpo.videos_do_nicho(canal_id)}
    except youtube.SemCota as erro:
        _sem_cota(erro)


@app.post("/api/ext/radar/preparar")
async def ext_radar_preparar(request: Request, u: dict = Depends(usuario)):
    """A busca de cada país para a extensão (o radar de países saiu do site: sem gastar a cota da API)."""
    titulo = str((await request.json()).get("titulo", "")).strip()[:300]
    if not titulo:
        raise HTTPException(400, "Falta o título do vídeo.")
    return radar_paises.preparar(titulo)


@app.post("/api/ext/radar/julgar")
async def ext_radar_julgar(request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    return radar_paises.julgar(d.get("preparo") or {}, d.get("resultados") or {}, str(d.get("video_id", "")))


def _kit_com_modelo(usuario_id: int, pasta) -> dict:
    """O kit do vídeo como a fábrica escreveu, mais o padrão de publicação do canal.

    A descrição NÃO é remontada aqui (mudança de 2026-10-24): quem escreve é a fábrica, que já põe o resumo, os
    capítulos e o rodapé do canal no publicacao.json. Remontar aqui jogava fora os capítulos do vídeo e deixava
    duas descrições diferentes para o mesmo projeto."""
    k = publicar.kit(pasta)
    perfil = publicar.perfil_do_projeto(pasta)
    canal_id, canal = producao.canal_do_perfil(usuario_id, perfil)
    cfg = producao.config(usuario_id, canal_id) if canal_id else {}
    k["canal"] = canal
    k["modelo"] = "rodape" if producao.rodape_do_perfil(perfil) else "fabrica"
    # o padrão de publicação do canal: a extensão não precisa perguntar nada no Studio, já vem decidido daqui
    k["padrao"] = {"anuncio_cada": cfg.get("anuncio_cada") or 1,
                   "tela_final": cfg.get("tela_final") or "melhor",
                   "tela_final_nome": producao.TELAS_FINAIS.get(cfg.get("tela_final") or "melhor", "")}
    return k


@app.get("/api/ext/publicar")
def ext_publicar(arquivo: str = "", u: dict = Depends(exigir("extensao"))):
    """O painel de ajuda do upload no YouTube Studio: o kit do vídeo achado pelo nome do arquivo e, se não achar, a
    lista para escolher. Lê o publicacao.json da pasta do projeto (não precisa da fábrica ligada)."""
    raiz = roteiro_claude.FABRICA / "projetos"
    nome = publicar.achar(raiz, arquivo[:300])
    return {"kit": _kit_com_modelo(u["id"], raiz / nome) if nome else None, "opcoes": publicar.opcoes(raiz)}


@app.get("/api/ext/publicar/{nome}")
def ext_publicar_projeto(nome: str, u: dict = Depends(exigir("extensao"))):
    pasta = _projeto_fabrica(nome)
    if not (pasta / "publicacao.json").exists():
        raise HTTPException(404, "A fábrica ainda não montou o título, a descrição e as tags deste vídeo.")
    return _kit_com_modelo(u["id"], pasta)


@app.get("/api/ext/publicar/{nome}/legenda")
def ext_publicar_legenda(nome: str, u: dict = Depends(exigir("extensao"))):
    pasta = _projeto_fabrica(nome)
    arquivo = next((pasta / f for f in ("legendas_final.srt", "legendas.srt") if (pasta / f).exists()), None)
    if not arquivo:
        raise HTTPException(404, "Este vídeo não tem legenda.")
    return FileResponse(arquivo, media_type="application/x-subrip", filename=f"{nome}.srt")


@app.post("/api/ext/escrever")
async def ext_escrever(request: Request, u: dict = Depends(exigir("extensao"))):
    """Um rascunho de descrição ou as tags para o vídeo que NÃO saiu da fábrica, pedido pelo painel do Studio.

    O vídeo da fábrica já vem com tudo no publicacao.json e nem oferece este botão. Quem escreve é o Claude Code
    instalado neste computador; se houver legenda do vídeo, ela entra no pedido. Nada é publicado: o texto volta
    para o campo do Studio, para a pessoa ler e mudar."""
    d = await request.json()
    o_que = str(d.get("o_que") or "descricao")
    if o_que not in ("descricao", "tags"):
        raise HTTPException(400, "Só sei escrever a descrição ou as tags.")
    titulo = str(d.get("titulo") or "").strip()
    if len(titulo) < 5:
        raise HTTPException(400, "Escreva o título do vídeo primeiro: é dele que sai o resto.")
    fala = ""
    video = str(d.get("video") or "")
    if re.fullmatch(r"[\w-]{11}", video):
        # vídeo recém-enviado ainda não tem legenda, e isso não é erro: segue só com o título
        try:
            fala = roteiro_claude.transcricao(video)[0]
        except Exception:
            fala = ""
    try:
        return await run_in_threadpool(publicar.escrever, o_que, titulo, fala)
    except RuntimeError as erro:
        raise HTTPException(502, str(erro))


@app.get("/api/ext/linguas/{video_id}")
def ext_linguas(video_id: str, linguas: str = "", u: dict = Depends(exigir("linguas"))):
    """O título do vídeo como se busca em cada língua, com o link da busca no YouTube já filtrada pelos mais vistos.

    Não gasta cota do YouTube: quem abre a busca é a pessoa, no navegador dela."""
    pedidas = [l for l in (linguas.split(",") if linguas else list(ia.LINGUAS)) if re.fullmatch(r"[a-z]{2}", l)][:12]
    v = banco.um("SELECT titulo FROM videos WHERE id=?", video_id)
    if not v:
        medir.medir_videos([video_id])
        v = banco.um("SELECT titulo FROM videos WHERE id=?", video_id)
    if not v:
        raise HTTPException(404, "Vídeo não encontrado.")
    chave = f"linguas:{video_id}:{','.join(sorted(pedidas))}"
    cache = banco.um("SELECT dados FROM traducoes WHERE chave=?", chave)
    buscas = json.loads(cache["dados"]) if cache else ia.traduzir_titulo(v["titulo"], pedidas)
    if buscas and not cache:
        banco.executar("INSERT OR REPLACE INTO traducoes (chave, dados, criado) VALUES (?,?,?)",
                       chave, json.dumps(buscas, ensure_ascii=False), banco.agora())
    return {"titulo": v["titulo"], "linguas": [
        {"codigo": c, "nome": ia.LINGUAS.get(c, c), "busca": buscas[c],
         "link": f"https://www.youtube.com/results?search_query={quote_plus(buscas[c])}&sp=CAM%253D"}
        for c in pedidas if c in buscas]}


# ---------------------------------------------------------------- painel

# A ordem da lista de canais: a conta, e para que lado ela vai quando a pessoa não escolhe. O sentido é da tela
# (toda ordem pode ser virada), como no painel que serviu de referência.
ORDENS = {
    "media": ("c.base_longos", "desc"),                 # mais views por vídeo
    "alta": ("c.velocidade", "desc"),                   # em alta: views por dia dos vídeos do último mês
    "ganho": ("c.ganho_7d", "desc"),                    # mais inscritos ganhos na semana
    "novos": ("c.descoberto", "desc"),                  # achados mais recentes
    "jovens": ("c.primeiro_video", "desc"),             # começaram a postar há menos tempo
    "inscritos": ("c.inscritos", "desc"),
    "estourando": ("c.base_longos * 1.0 / MAX(c.inscritos, 100)", "desc"),   # muita view para o tamanho
    "recente": ("c.ultimo_video", "desc"),              # postaram por último
    # a hora de copiar: views por vídeo, com peso para canal novo e crescendo. É a conta do
    # metricas.pontos_do_ranking escrita em SQL, para a lista inteira poder ser ordenada por ela.
    "pontos": ("c.base_longos / sqrt(MAX(1.0, (julianday('now') - julianday(c.primeiro_video)) / 30.44)) * "
               "CASE c.fase WHEN 'crescendo' THEN 1.4 WHEN 'nascendo' THEN 1.2 WHEN 'estavel' THEN 1.0 "
               "WHEN 'caindo' THEN 0.5 WHEN 'parado' THEN 0.2 ELSE 0.8 END", "desc"),
    "aleatorio": ("RANDOM()", ""),                      # o botão Aleatório de todas as telas
}


def _ordem_sql(chave: str, sentido: str = "") -> str:
    """A ordem pedida, no sentido pedido. Sentido em branco: o natural daquela ordem."""
    conta, padrao = ORDENS.get(chave) or ORDENS["media"]
    if not padrao:
        return conta                                     # o aleatório não tem lado
    lado = sentido if sentido in ("asc", "desc") else padrao
    return f"{conta} {lado.upper()}"


# As visões: as perguntas prontas da lista de canais (2026-10-22). Em vez de a pessoa montar o filtro, cada visão é
# uma pergunta já feita. A regra mora aqui, no servidor: o painel só manda o nome dela. A `ordem` vai junto para a
# tela acender o select certo — depois de escolher a visão, a pessoa pode trocar a ordem e apertar os filtros, que
# o que ela pedir vale por cima da visão.
VISOES = {
    "novo_crescendo": {
        "rotulo": "Novo e crescendo",
        "dica": "Começou a postar há até 6 meses e os vídeos do último mês fazem 10 mil views por dia ou mais.",
        "filtros": {"idade_max": "6", "alta_min": "10000"},
        "ordem": "alta",
    },
    "entraram_hoje": {
        "rotulo": "Entraram hoje",
        "dica": "Canais que o garimpo achou nas últimas 24 horas, os mais novos em cima.",
        "filtros": {"achado_dias": "1"},
        "ordem": "novos",
    },
    "media_alta": {
        "rotulo": "Média alta",
        "dica": "O vídeo típico do canal passa de 100 mil views.",
        "filtros": {"media_min": "100000"},
        "ordem": "media",
    },
    "virou_a_chave": {
        "rotulo": "Virou a chave",
        "dica": "Os 10 últimos vídeos fazem pelo menos 1,5 vez o que os 20 anteriores faziam (a fase crescendo).",
        "filtros": {"fase": "crescendo"},
        "ordem": "alta",
    },
    "views_poucos_subs": {
        "rotulo": "Muita view, poucos inscritos",
        "dica": "O vídeo típico faz 5 vezes o número de inscritos do canal.",
        "filtros": {"estourando_min": "5", "media_min": "10000"},
        "ordem": "estourando",
    },
    "outliers": {
        "rotulo": "Com vídeo que estourou",
        "dica": "Tem pelo menos um vídeo com 10 vezes o normal do próprio canal.",
        "filtros": {"com_outlier": "10"},
        "ordem": "media",
    },
    "sem_concorrencia": {
        "rotulo": "Sem concorrência",
        "dica": "O subnicho dele tem no máximo 2 canais no Radar: ninguém disputando ainda.",
        "filtros": {"subnicho_ate": "2"},
        "ordem": "media",
    },
}


def _com_a_visao(q: dict) -> dict:
    """Os filtros da visão escolhida, com o que a pessoa pediu por cima."""
    visao = VISOES.get(str(q.get("visao", "")))
    if not visao:
        return q
    pedido = {k: v for k, v in q.items() if v not in ("", None)}
    return {**visao["filtros"], **pedido}


def _corte(dias: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%S")


def _numero(q: dict, nome: str) -> float | None:
    try:
        valor = q.get(nome, "")
        return float(valor) if valor not in ("", None) else None
    except ValueError:
        return None


def _data(q: dict, nome: str) -> str:
    valor = str(q.get(nome, ""))
    return valor if re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor) else ""


def _filtro_canais(q: dict) -> tuple[list[str], list]:
    """Os filtros de canal do painel. Cada um vira um pedaço do WHERE."""
    onde, args = ["c.no_radar=1"], []
    for campo in ("nicho", "subnicho", "raridade", "fase", "pais"):
        if q.get(campo):
            onde.append(f"c.{campo}=?"); args.append(q[campo])
    if q.get("busca"):
        # procura de nicho: nome do canal, nicho, subnicho ou o título de algum vídeo dele
        onde.append("(c.titulo LIKE ? OR c.subnicho LIKE ? OR c.nicho LIKE ? OR c.handle LIKE ? OR c.id IN "
                    "(SELECT canal_id FROM videos WHERE titulo LIKE ?))")
        args += [f"%{q['busca']}%"] * 5
    if q.get("rosto") == "sem":
        onde.append("c.sem_rosto=1")
    elif q.get("rosto") == "com":
        onde.append("c.sem_rosto=0")
    for nome, coluna, fator in (("inscritos_min", "c.inscritos", 1), ("media_min", "c.base_longos", 1),
                                ("videos_min", "c.videos_total", 1), ("alta_min", "c.velocidade", 1)):
        valor = _numero(q, nome)
        if valor is not None:
            onde.append(f"{coluna} >= ?"); args.append(valor * fator)
    for nome, coluna in (("inscritos_max", "c.inscritos"), ("media_max", "c.base_longos"), ("videos_max", "c.videos_total")):
        valor = _numero(q, nome)
        if valor is not None:
            onde.append(f"{coluna} <= ?"); args.append(valor)
    # datas: quando começou a postar, quando postou por último e quando o Radar achou
    meses_max, meses_min = _numero(q, "idade_max"), _numero(q, "idade_min")
    if meses_max is not None:
        onde.append("c.primeiro_video >= ?"); args.append(_corte(meses_max * 30.44))
    if meses_min is not None:
        onde.append("c.primeiro_video <= ?"); args.append(_corte(meses_min * 30.44))
    for nome, coluna in (("postou_dias", "c.ultimo_video"), ("achado_dias", "c.descoberto")):
        dias = _numero(q, nome)
        if dias is not None:
            onde.append(f"{coluna} >= ?"); args.append(_corte(dias))
    # quantas vezes o vídeo típico rende o tamanho do canal (a mesma conta da ordem "estourando")
    razao = _numero(q, "estourando_min")
    if razao is not None:
        onde.append("c.base_longos * 1.0 / MAX(c.inscritos, 100) >= ?"); args.append(razao)
    # canal que tem vídeo com pelo menos esta nota de outlier
    nota = _numero(q, "com_outlier")
    if nota is not None:
        onde.append("c.id IN (SELECT canal_id FROM outliers WHERE nota >= ?)"); args.append(nota)
    # canal de subnicho com até tantos canais no Radar: o grupo que ainda não tem fila
    quantos = _numero(q, "subnicho_ate")
    if quantos is not None:
        onde.append("c.subnicho <> '' AND c.subnicho IN (SELECT subnicho FROM canais WHERE no_radar=1 "
                    "AND subnicho <> '' GROUP BY subnicho HAVING COUNT(*) <= ?)")
        args.append(quantos)
    for nome, coluna, operador, sufixo in (("inicio_de", "c.primeiro_video", ">=", ""),
                                           ("inicio_ate", "c.primeiro_video", "<=", "T23:59:59"),
                                           ("achado_de", "c.descoberto", ">=", ""),
                                           ("achado_ate", "c.descoberto", "<=", "T23:59:59")):
        data = _data(q, nome)
        if data:
            onde.append(f"{coluna} {operador} ?"); args.append(data + sufixo)
    return onde, args


VIDEOS_DO_CARTAO = 5   # capas por canal: com três não dá para ver o padrão do canal, que é para o que se olha


def _vitrine(c: dict, usuario_id: int | None = None, com_videos: bool = True) -> dict:
    """O canal com as capas dos VIDEOS_DO_CARTAO vídeos longos que mais renderam, para o cartão do painel."""
    publico = medir._canal_publico(c) | {"descoberto": c.get("descoberto", "")}
    if com_videos:
        videos = banco.todos("SELECT id, titulo, views, publicado, duracao_s FROM videos WHERE canal_id=? AND duracao_s>? "
                             "ORDER BY views DESC LIMIT ?", c["id"], metricas.CURTO_ATE_S, VIDEOS_DO_CARTAO)
        publico["videos"] = [v | {"nota": metricas.nota_outlier(v["views"], c["base_longos"])} for v in videos]
    if usuario_id is not None:
        meu = banco.um("SELECT pasta FROM salvos WHERE usuario_id=? AND canal_id=?", usuario_id, c["id"])
        publico["salvo"] = meu is not None
        publico["pasta"] = (meu or {}).get("pasta", "")
    return publico


def _lista_de_canais(onde: str, args: list, ordem: str, limite: int, pagina: int = 0,
                     usuario_id: int | None = None) -> list[dict]:
    linhas = banco.todos(f"SELECT c.* FROM canais c WHERE {onde} ORDER BY {ordem}, c.base_longos DESC "
                         f"LIMIT ? OFFSET ?", *args, limite, pagina * limite)
    return [_vitrine(c, usuario_id) for c in linhas]


@app.get("/api/resumo")
def resumo():
    return {"nome": NOME, **_numeros()}


# ---------------------------------------------------------------- a vitrine: a porta do Radar, sem conta
# Os números e alguns canais de exemplo para quem ainda não entrou. Nada daqui é de ninguém: são canais públicos
# do YouTube, escolhidos pela mesma régua do "na hora de copiar" — não a dedo —, e nenhum dado de usuário entra
# (sem salvos, sem pastas, sem contagem de gente). As contas são caras para refazer a cada visita, então ficam
# guardadas alguns minutos.

VITRINE_QUANTOS = 8
VITRINE_CAPAS = 4
VITRINE_MINUTOS = 10
_VITRINE: dict = {"quando": 0.0, "dados": None}


def _canais_da_vitrine() -> list[dict]:
    linhas = banco.todos(
        f"SELECT c.id, c.titulo, c.foto, c.handle, c.nicho, c.subnicho, c.inscritos, c.base_longos, c.primeiro_video, "
        f"c.raridade FROM canais c WHERE c.no_radar=1 AND c.base_longos >= ? AND c.foto <> '' "
        f"AND c.nicho NOT IN ({','.join('?' * len(mercado.IRRELEVANTES))}) "
        f"ORDER BY {_ordem_sql('pontos', '')} LIMIT ?",
        garimpo.MINIMO_POR_VIDEO, *sorted(mercado.IRRELEVANTES), VITRINE_QUANTOS * 2)
    saida = []
    for c in linhas:
        if mercado.irrelevante(c["nicho"], c["subnicho"]) or len(saida) >= VITRINE_QUANTOS:
            continue
        capas = banco.todos("SELECT id FROM videos WHERE canal_id=? AND duracao_s>? ORDER BY views DESC LIMIT ?",
                            c["id"], metricas.CURTO_ATE_S, VITRINE_CAPAS)
        if len(capas) < VITRINE_CAPAS:
            continue                      # sem capa para mostrar, o cartão fica torto: melhor o próximo da régua
        saida.append({
            "nome": c["titulo"], "foto": c["foto"], "nicho": c["subnicho"] or c["nicho"],
            "inscritos": c["inscritos"], "media": c["base_longos"], "raridade": c["raridade"],
            "dias": round((metricas.meses_postando(c["primeiro_video"]) or 0) * 30.44) or None,
            "capas": [v["id"] for v in capas],
        })
    return saida


@app.get("/api/vitrine")
def vitrine_publica():
    """A porta do Radar: os números e alguns canais de exemplo, sem precisar de conta."""
    agora = time.time()
    if _VITRINE["dados"] and agora - _VITRINE["quando"] < VITRINE_MINUTOS * 60:
        return _VITRINE["dados"]
    n = _numeros()
    _VITRINE["dados"] = {
        "nome": NOME,
        "canais": n["no_radar"], "analisados": n["canais_analisados"], "videos": n["videos_lidos"],
        "nichos": n["nichos"], "subnichos": n["subnichos"],
        "novos_semana": n["novos_semana"], "estouraram": n["outliers"],
        "exemplos": _canais_da_vitrine(),
        "depoimentos": depoimentos()["depoimentos"],
    }
    _VITRINE["quando"] = agora
    return _VITRINE["dados"]


def _numeros() -> dict:
    um = lambda sql, *a: banco.um(sql, *a)["n"]  # noqa: E731
    return {
        "canais_analisados": um("SELECT COUNT(*) AS n FROM canais"),
        "no_radar": um("SELECT COUNT(*) AS n FROM canais WHERE no_radar=1"),
        "videos_lidos": um("SELECT COUNT(*) AS n FROM videos"),
        "nichos": um("SELECT COUNT(DISTINCT nicho) AS n FROM canais WHERE no_radar=1 AND nicho<>''"),
        "subnichos": um("SELECT COUNT(DISTINCT subnicho) AS n FROM canais WHERE no_radar=1 AND subnicho<>''"),
        "novos_semana": um("SELECT COUNT(*) AS n FROM canais WHERE no_radar=1 AND descoberto>=?", _corte(7)),
        "novos_hoje": um("SELECT COUNT(*) AS n FROM canais WHERE no_radar=1 AND descoberto>=?", _corte(1)),
        "outliers": um("SELECT COUNT(*) AS n FROM outliers WHERE nota>=5"),
        "termos": um("SELECT COUNT(*) AS n FROM buscas_feitas"),
        "termos_aprendidos": um("SELECT COUNT(*) AS n FROM termos_auto"),
    }


@app.get("/api/visao")
def visao(u: dict = Depends(exigir("radar"))):
    def linhas(sql, *a):
        return [_vitrine(c, com_videos=False) for c in banco.todos(sql, *a)]
    destaques = banco.todos(
        "SELECT o.nota, v.id, v.titulo, v.views, v.publicado, v.duracao_s, c.id AS canal_id, c.titulo AS canal, "
        "c.foto FROM outliers o JOIN videos v ON v.id=o.video_id JOIN canais c ON c.id=o.canal_id "
        "WHERE v.publicado >= ? AND o.nota >= 5 ORDER BY o.nota DESC LIMIT 8", _corte(45))
    return {
        "numeros": _numeros(), "cota": youtube.cota_hoje(),
        "em_alta": linhas("SELECT * FROM canais WHERE no_radar=1 AND velocidade IS NOT NULL "
                          "ORDER BY velocidade DESC LIMIT 8"),
        "entraram": linhas("SELECT * FROM canais WHERE no_radar=1 ORDER BY descoberto DESC LIMIT 8"),
        "outliers": destaques,
        "nichos": banco.todos("SELECT nicho, COUNT(*) AS canais FROM canais WHERE no_radar=1 AND nicho<>'' "
                              "GROUP BY nicho ORDER BY canais DESC LIMIT 12"),
        "ultimo_garimpo": banco.um("SELECT inicio, fim, canais_novos, estado FROM garimpos ORDER BY id DESC LIMIT 1"),
    }


@app.get("/api/radar")
def radar(request: Request, u: dict = Depends(exigir("radar"))):
    """A lista de canais do Radar: uma tela só, com a visão, os filtros, a ordem e o lado dela.

    `salvos` e `acharam` recortam a lista para a base da pessoa; `tudo=1` desliga o corte de qualidade, que por
    padrão tira os nichos que pagam pouco (eles só davam tela cheia de canal que não serve)."""
    q = _com_a_visao(dict(request.query_params))
    # o mesmo piso do garimpo: abaixo de 10 mil views por vídeo o canal nem teria entrado no Radar, então pedir
    # menos que isso não traz nada de novo — traz canal cujo "normal" ainda não foi medido direito
    piso = garimpo.MINIMO_POR_VIDEO
    q["media_min"] = str(max(_numero(q, "media_min") or 0, piso))
    onde, args = _filtro_canais(q)
    if q.get("salvos") == "1":
        onde.append("c.id IN (SELECT canal_id FROM salvos WHERE usuario_id=?)"); args.append(u["id"])
    if q.get("acharam") == "1":
        onde.append("c.id IN (SELECT canal_id FROM achados WHERE usuario_id=?)"); args.append(u["id"])
    if q.get("pasta"):      # `sem_pasta` é o nome reservado para os salvos que ainda não foram guardados em nenhuma
        pedida = "" if q["pasta"] == "sem_pasta" else q["pasta"]
        onde.append("c.id IN (SELECT canal_id FROM salvos WHERE usuario_id=? AND pasta=?)")
        args += [u["id"], pedida]
    if q.get("tudo") != "1" and not q.get("nicho"):
        onde.append(f"c.nicho NOT IN ({','.join('?' * len(mercado.IRRELEVANTES))})")
        args += sorted(mercado.IRRELEVANTES)
    por = min(60, max(1, int(_numero(q, "por") or 30)))
    pagina = int(_numero(q, "pagina") or 0)
    juntos = " AND ".join(onde)
    total = banco.um(f"SELECT COUNT(*) AS n FROM canais c WHERE {juntos}", *args)["n"]
    lista = _lista_de_canais(juntos, args, _ordem_sql(q.get("ordem", ""), q.get("sentido", "")), por, pagina, u["id"])
    # o subnicho de histórias narradas não dá para pedir em SQL (é regex): sai da página, e a tela diz quantos saíram
    dentro = [c for c in lista if q.get("tudo") == "1" or not mercado.irrelevante(c.get("nicho"), c.get("subnicho"))]
    return {"total": total, "canais": dentro, "cortados": len(lista) - len(dentro),
            "piso": piso, "media_min": float(q["media_min"])}


@app.get("/api/visoes")
def visoes(u: dict = Depends(exigir("radar"))):
    """As perguntas prontas da lista de canais, com quantos canais cada uma tem agora.

    A conta é a da visão sozinha: ela diz o que existe no Radar, não o que sobra depois dos filtros da tela."""
    saida = []
    for chave, v in VISOES.items():
        onde, args = _filtro_canais(dict(v["filtros"]))
        n = banco.um(f"SELECT COUNT(*) AS n FROM canais c WHERE {' AND '.join(onde)}", *args)["n"]
        saida.append({"chave": chave, "rotulo": v["rotulo"], "dica": v["dica"], "ordem": v["ordem"], "canais": n})
    return {"visoes": saida}


@app.get("/api/filtros")
def filtros(u: dict = Depends(exigir("radar"))):
    """As opções dos filtros, com quantos canais tem cada uma."""
    contar = lambda campo: banco.todos(  # noqa: E731
        f"SELECT {campo} AS valor, COUNT(*) AS canais FROM canais WHERE no_radar=1 AND {campo}<>'' "
        f"GROUP BY {campo} ORDER BY canais DESC")
    # nicho que paga pouco não aparece em nenhuma lista: na escolha ele só dava tela vazia
    nichos = [n for n in contar("nicho") if not mercado.irrelevante(n["valor"])]
    return {"nichos": nichos, "subnichos": contar("subnicho"), "paises": contar("pais"),
            "fases": contar("fase")}


@app.get("/api/nichos")
def nichos_da_base(u: dict = Depends(exigir("radar"))):
    return {"nichos": banco.todos("SELECT nicho, COUNT(*) AS canais FROM canais WHERE no_radar=1 AND nicho<>'' "
                                  "GROUP BY nicho ORDER BY canais DESC")}


@app.get("/api/grupos")
def grupos(nicho: str = "", u: dict = Depends(exigir("radar"))):
    """Os subnichos como grupos de canais que fazem o mesmo tipo de vídeo, com o tamanho e a força de cada um."""
    onde, args = "no_radar=1 AND subnicho<>''", []
    if nicho:
        onde += " AND nicho=?"; args.append(nicho)
    por_grupo: dict[str, list] = {}
    for c in banco.todos(f"SELECT * FROM canais WHERE {onde} ORDER BY base_longos DESC", *args):
        if mercado.irrelevante(c["nicho"], c["subnicho"]):
            continue
        por_grupo.setdefault(c["subnicho"], []).append(c)
    saida = []
    for nome, canais in por_grupo.items():
        medias = sorted(c["base_longos"] or 0 for c in canais)
        meses = [m for m in (metricas.meses_postando(c["primeiro_video"]) for c in canais) if m is not None]
        crescendo = sum(1 for c in canais if c["fase"] in ("crescendo", "nascendo"))
        saida.append({
            "subnicho": nome, "nicho": canais[0]["nicho"], "canais": len(canais),
            "mediana": medias[len(medias) // 2], "maior": medias[-1],
            "meses_medio": round(sum(meses) / len(meses), 1) if meses else None,
            "crescendo": crescendo, "sem_rosto": sum(1 for c in canais if c["sem_rosto"]),
            "novos_semana": sum(1 for c in canais if (c["descoberto"] or "") >= _corte(7)),
            "fotos": [{"foto": c["foto"], "titulo": c["titulo"]} for c in canais[:5]],
            "capas": [v["id"] for v in banco.todos(
                f"SELECT id FROM videos WHERE canal_id IN ({','.join('?' * len(canais[:6]))}) AND duracao_s>? "
                "ORDER BY views DESC LIMIT 4", *[c["id"] for c in canais[:6]], metricas.CURTO_ATE_S)],
        })
    saida.sort(key=lambda g: (-g["canais"], -g["mediana"]))
    return {"grupos": saida}


@app.get("/api/nichos/vida")
def nichos_vida(nicho: str = "", idioma: str = "", u: dict = Depends(exigir("radar"))):
    """A faixa das cinco etapas da vida de um canal, somando os canais da mesma lista que a tela Canais mostra."""
    return nichos.linha_da_vida(nicho, idioma, garimpo.MINIMO_POR_VIDEO)


@app.get("/api/nichos/tabela")
def nichos_tabela(nicho: str = "", idioma: str = "", minimo: int = 1, u: dict = Depends(exigir("radar"))):
    """Um nicho por linha: canais, tráfego típico, parados e público."""
    return nichos.tabela(nicho, idioma, max(1, min(minimo, 50)), garimpo.MINIMO_POR_VIDEO)


@app.get("/api/ranking")
def ranking(nicho: str = "", u: dict = Depends(exigir("ranking"))):
    onde, args = "no_radar=1 AND fase NOT IN ('parado','caindo')", []
    if nicho:
        onde += " AND nicho=?"; args.append(nicho)
    candidatos = [c for c in banco.todos(f"SELECT * FROM canais WHERE {onde} ORDER BY base_longos DESC LIMIT 400", *args)
                  if not mercado.irrelevante(c["nicho"], c["subnicho"])]
    pontos = sorted(candidatos, key=lambda c: -metricas.pontos_do_ranking(
        c["base_longos"], metricas.meses_postando(c["primeiro_video"]), c["fase"]))
    return {"canais": [_vitrine(c, u["id"]) for c in pontos[:30]]}


# A nota é recalculada na hora, não lida da tabela: a `outliers.nota` foi gravada com o normal que o canal tinha no
# dia em que o vídeo foi achado, e quando o normal do canal é corrigido depois ela fica mentindo. Dava lista encabeçada
# por vídeo de 137 views com "18.291x o normal". A tabela continua valendo como índice de quem já foi marcado; a conta
# é sempre a de agora, a mesma do metricas.nota_outlier: views ÷ o normal do canal (Shorts contra Shorts).
_NORMAL = f"CASE WHEN v.duracao_s <= {metricas.CURTO_ATE_S} THEN c.base_curtos ELSE c.base_longos END"
_NOTA_VIVA = f"v.views * 1.0 / NULLIF({_NORMAL}, 0)"
# e um normal de 19 views não é base para razão nenhuma: abaixo disto o canal ainda não foi medido o bastante
NORMAL_MINIMO = 1000

ORDENS_OUTLIERS = {"nota": (_NOTA_VIVA, "desc"), "recentes": ("v.publicado", "desc"), "views": ("v.views", "desc"),
                   "achados": ("o.achado", "desc"), "inscritos": ("c.inscritos", "desc"),
                   "por_hora": ("v.views * 1.0 / MAX(1.0, (julianday('now') - julianday(v.publicado)) * 24)", "desc"),
                   "aleatorio": ("RANDOM()", "")}


def piso_de_views(nota_min: float, normal_min: float) -> int:
    """O mínimo de views que as outras regras já impõem, para a tela poder dizer o número.

    Não é escolha nossa: pedir 10x o normal do canal, com o normal medido em pelo menos mil views, é pedir vídeos
    de 10 mil views para cima. Dizer isso evita a pessoa arrastar um filtro que já está decidido; ela pode subir
    dali, nunca descer abaixo do que as regras impõem."""
    return max(0, int(nota_min * normal_min))


def _ordem_videos(chave: str, sentido: str = "") -> str:
    conta, padrao = ORDENS_OUTLIERS.get(chave) or ORDENS_OUTLIERS["nota"]
    if not padrao:
        return conta
    return f"{conta} {(sentido if sentido in ('asc', 'desc') else padrao).upper()}"


@app.get("/api/videos")        # o nome novo da lista única de vídeos; /api/outliers continua para a extensão
@app.get("/api/outliers")
def outliers(request: Request, u: dict = Depends(exigir("outliers"))):
    q = dict(request.query_params)
    nota_min = _numero(q, "nota_min") or 5
    onde, args = [f"{_NOTA_VIVA} >= ?"], [nota_min]
    normal_min = _numero(q, "normal_min")
    normal_min = NORMAL_MINIMO if normal_min is None else normal_min
    if normal_min > 0:
        onde.append(f"{_NORMAL} >= ?"); args.append(normal_min)
    piso = piso_de_views(nota_min, normal_min)
    views_min = max(_numero(q, "views_min") or 0, piso)
    if views_min > 0:
        onde.append("v.views >= ?"); args.append(views_min)
    for campo in ("nicho", "subnicho"):
        if q.get(campo):
            onde.append(f"c.{campo}=?"); args.append(q[campo])
    if q.get("busca"):
        onde.append("(v.titulo LIKE ? OR c.titulo LIKE ?)"); args += [f"%{q['busca']}%"] * 2
    # a etapa da curva da vida: a idade de QUEM POSTA, não a do vídeo. É o que faz o clique numa etapa abrir os
    # vídeos dos canais dela sem mudar de tela, com o mesmo corte que a faixa contou (radar/nichos.py).
    faixa = nichos.limites(q.get("etapa", ""))
    if faixa:
        de, ate = faixa
        onde.append("c.primeiro_video IS NOT NULL AND c.primeiro_video != '' AND c.primeiro_video <= ?")
        args.append(_corte(de))
        if ate is not None:
            onde.append("c.primeiro_video > ?"); args.append(_corte(ate))
    if q.get("tipo") == "longo":
        onde.append("v.duracao_s > ?"); args.append(metricas.CURTO_ATE_S)
    elif q.get("tipo") == "curto":
        onde.append("v.duracao_s <= ?"); args.append(metricas.CURTO_ATE_S)
    if q.get("rosto") == "sem":
        onde.append("c.sem_rosto=1")
    if q.get("meus") == "1" or q.get("salvos") == "1":
        onde.append("c.id IN (SELECT canal_id FROM salvos WHERE usuario_id=?)"); args.append(u["id"])
    if q.get("acharam") == "1":
        onde.append("c.id IN (SELECT canal_id FROM achados WHERE usuario_id=?)"); args.append(u["id"])
    if q.get("pasta"):
        pedida = "" if q["pasta"] == "sem_pasta" else q["pasta"]
        onde.append("c.id IN (SELECT canal_id FROM salvos WHERE usuario_id=? AND pasta=?)")
        args += [u["id"], pedida]
    if q.get("so_novos") == "1":            # saiu nos últimos 7 dias
        onde.append("v.publicado >= ?"); args.append(_corte(7))
    if q.get("so_crescendo") == "1":        # o canal está acelerando agora, não é um acerto antigo
        onde.append("c.fase IN ('crescendo','nascendo')")
    if q.get("modelar_estado") in ESTEIRA:  # a esteira: só o que eu marquei para modelar, ou o que já modelei
        onde.append("v.id IN (SELECT video_id FROM modelar WHERE usuario_id=? AND estado=?)")
        args += [u["id"], q["modelar_estado"]]
    inscritos_max = _numero(q, "inscritos_max")   # o views_min já entrou acima, junto com o piso
    if inscritos_max is not None:
        onde.append("c.inscritos <= ?"); args.append(inscritos_max)
    inscritos_min = _numero(q, "inscritos_min")
    if inscritos_min is not None:
        onde.append("c.inscritos >= ?"); args.append(inscritos_min)
    dias = _numero(q, "publicado_dias")
    if dias is not None:
        onde.append("v.publicado >= ?"); args.append(_corte(dias))
    for nome, operador, sufixo in (("publicado_de", ">=", ""), ("publicado_ate", "<=", "T23:59:59")):
        data = _data(q, nome)
        if data:
            onde.append(f"v.publicado {operador} ?"); args.append(data + sufixo)
    base = (f"FROM outliers o JOIN videos v ON v.id=o.video_id JOIN canais c ON c.id=o.canal_id "
            f"WHERE c.no_radar=1 AND {' AND '.join(onde)}")
    pagina = int(_numero(q, "pagina") or 0)
    # o marcador da esteira vem junto com o vídeo: o cartão precisa saber se já está na fila ou já foi modelado
    linhas = banco.todos(
        f"SELECT ROUND({_NOTA_VIVA}, 1) AS nota, (SELECT estado FROM modelar m WHERE m.usuario_id=? AND m.video_id=v.id) "
        f"AS modelar, v.id, v.titulo, v.views, v.publicado, v.duracao_s, c.id AS canal_id, c.titulo AS canal, "
        f"c.foto, c.handle, c.inscritos, c.nicho, c.subnicho, c.sem_rosto, c.fase, c.base_longos AS normal {base} "
        f"ORDER BY {_ordem_videos(q.get('ordem', ''), q.get('sentido', ''))}", u["id"], *args)
    for l in linhas:
        l["por_hora"] = metricas.views_por_hora(l["views"], l["publicado"])
    # os bloqueios e as respostas da primeira vez (língua, rosto, o que nunca mostrar) valem aqui também
    filtro = gosto.Filtro(u)
    # o formato é o da tela: "Longos e Shorts" (vazio) mostra os dois, mesmo que a pergunta da primeira vez diga "só longos"
    filtro.sem_shorts = q.get("tipo") == "longo"
    filtro.p = filtro.p | {"formato": "curto" if q.get("tipo") == "curto" else "todos"}
    filtro.linguas = {"outras"}
    # a língua é escolha da tela, não corte escondido: ela vale para os dois lados da conta, e `cortados` fica
    # sendo só o que as respostas da primeira vez e os bloqueios tiraram — o que a tela diz e abre com um clique
    na_lingua = gosto.por_lingua(linhas, q.get("lingua", ""))
    dentro = [l for l in na_lingua if filtro.aceita(l)]
    cortados = len(na_lingua) - len(dentro)
    if q.get("com_cortados") == "1":
        dentro = na_lingua
    por = min(60, max(1, int(_numero(q, "por") or 60)))   # Vídeos que estouraram pede de 10 em 10
    return {"total": len(dentro), "cortados": cortados, "piso": piso, "views_min": views_min,
            "videos": dentro[pagina * por:(pagina + 1) * por]}


@app.get("/api/salvos")
def salvos(u: dict = Depends(exigir("salvar"))):
    return {"canais": _lista_de_canais("c.id IN (SELECT canal_id FROM salvos WHERE usuario_id=?)", [u["id"]],
                                       "c.base_longos DESC", 500, usuario_id=u["id"])}


@app.get("/api/novidades")
def novidades(dias: int = 14, u: dict = Depends(exigir("salvar"))):
    """Os vídeos novos dos canais que você salvou, com a nota de cada um."""
    linhas = banco.todos(
        "SELECT v.id, v.titulo, v.views, v.publicado, v.duracao_s, c.id AS canal_id, c.titulo AS canal, c.foto, "
        "c.handle, c.base_longos, c.base_curtos FROM videos v JOIN canais c ON c.id=v.canal_id "
        "WHERE c.id IN (SELECT canal_id FROM salvos WHERE usuario_id=?) AND v.publicado >= ? "
        "ORDER BY v.publicado DESC LIMIT 200", u["id"], _corte(max(1, min(dias, 90))))
    for v in linhas:
        normal = v.pop("base_curtos") if metricas.curto(v["duracao_s"]) else v["base_longos"]
        v.pop("base_curtos", None)
        v["nota"] = metricas.nota_outlier(v["views"], normal)
        v["por_hora"] = metricas.views_por_hora(v["views"], v["publicado"])
    return {"videos": linhas}


@app.get("/api/achados")
def achados(u: dict = Depends(exigir("achados"))):
    linhas = banco.todos("SELECT a.canal_id, a.por_causa_de, a.criado, o.titulo AS origem FROM achados a "
                         "LEFT JOIN canais o ON o.id=a.por_causa_de WHERE a.usuario_id=? ORDER BY a.criado DESC "
                         "LIMIT 300", u["id"])
    canais = {c["id"]: c for c in medir._canais_do_banco([l["canal_id"] for l in linhas])}
    return {"canais": [_vitrine(canais[l["canal_id"]], u["id"]) | {"por_causa_de": l["origem"], "achado": l["criado"]}
                       for l in linhas if l["canal_id"] in canais]}


# ---------------------------------------------------------------- meu perfil e a procura de nicho

@app.get("/api/perfil")
def meu_perfil(u: dict = Depends(usuario)):
    canais = banco.todos("SELECT c.* FROM meus_canais m JOIN canais c ON c.id=m.canal_id WHERE m.usuario_id=? "
                         "ORDER BY c.inscritos DESC", u["id"])
    no_studio = set(studio.conectados(u["id"]))
    lista = [_vitrine(c, com_videos=False) | {"ultimos": perfil.ultimos_videos(c, 3), "studio": c["id"] in no_studio} for c in canais]
    soma = lambda campo: sum(c[campo] or 0 for c in canais)  # noqa: E731
    return {"eu": _publico(u), "canais": lista, "totais": {
        "inscritos": soma("inscritos"), "views": soma("views_total"), "videos": soma("videos_total"),
        "ganho_7d": soma("ganho_7d"), "salvos": banco.um("SELECT COUNT(*) AS n FROM salvos WHERE usuario_id=?", u["id"])["n"]}}


def _resolver(texto: str) -> str:
    ref = _ref_do_canal(texto)
    if ref and ref.startswith("@"):
        with youtube.gastando("medir"):
            achado = youtube.canal_por_handle(ref)
        ref = achado["id"] if achado else None
    if not ref:
        raise HTTPException(404, "Não achei esse canal. Cole o @ do canal, o link dele ou o link de um vídeo.")
    return ref


@app.post("/api/perfil/canais")
async def conectar_canal(request: Request, u: dict = Depends(usuario)):
    try:
        c = perfil.conectar(u["id"], _resolver(str((await request.json()).get("ref", ""))))
    except youtube.SemCota as erro:
        _sem_cota(erro)
    return {"canal": _vitrine(c, com_videos=False)}


@app.delete("/api/perfil/canais/{canal_id}")
def desconectar_canal(canal_id: str, u: dict = Depends(usuario)):
    banco.executar("DELETE FROM meus_canais WHERE usuario_id=? AND canal_id=?", u["id"], canal_id)
    return {"ok": True}


@app.get("/api/perfil/canal/{canal_id}")
def meu_canal(canal_id: str, u: dict = Depends(usuario)):
    c = banco.um("SELECT * FROM canais WHERE id=?", canal_id)
    if not c:
        raise HTTPException(404, "Canal não encontrado.")
    return {"canal": _vitrine(c, u["id"], com_videos=False), "ultimos": perfil.ultimos_videos(c, 12),
            "historico": perfil.historico(canal_id), "horarios": horarios.do_canal(canal_id),
            "ideias": gosto.ideias_para(u, c),
            "parecidos": [_vitrine(p, com_videos=False) for p in perfil.parecidos_da_base(c)],
            "meu": bool(banco.um("SELECT 1 AS x FROM meus_canais WHERE usuario_id=? AND canal_id=?", u["id"], canal_id))}


@app.post("/api/perfil/canal/{canal_id}/ideias")
async def mais_ideias(canal_id: str, request: Request, u: dict = Depends(usuario)):
    c = banco.um("SELECT * FROM canais WHERE id=?", canal_id)
    if not c:
        raise HTTPException(404, "Canal não encontrado.")
    tentativa = int((await request.json()).get("tentativa", 0) or 0)
    try:
        return perfil.mais_ideias(c, tentativa, u["id"])
    except youtube.SemCota as erro:
        _sem_cota(erro)


@app.post("/api/procurar")
async def procurar_nicho(request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    termo = re.sub(r"\s+", " ", str(d.get("termo", ""))).strip()[:80]
    if len(termo) < 2:
        raise HTTPException(400, "Escreva o nicho que você quer procurar.")
    try:
        r = perfil.procurar(termo, int(d.get("tentativa", 0) or 0))
    except youtube.SemCota as erro:
        _sem_cota(erro)
    canais = {c["id"]: c for c in medir._canais_do_banco(r["no_radar"])}
    r["canais"] = [_vitrine(canais[i], u["id"]) | {"novo": i in r["novos"]} for i in r["no_radar"] if i in canais]
    r["canais"].sort(key=lambda c: (not c["novo"], -(c["normal_longos"] or 0)))
    return r


# ---------------------------------------------------------------- gosto: perguntas da primeira vez, bloqueios, explorar

# ---------------------------------------------------------------- o menu de cada pessoa
# A ordem das abas e as que ela escondeu. Fica na conta, não no navegador: o menu é o mesmo em qualquer máquina.
# O servidor não sabe que abas existem (isso é da tela), então ele guarda os nomes como vieram, só limpos e limitados.

ABAS_FIXAS = ("base",)            # a lista de canais não some: sem ela não sobra por onde começar
PAINEL_MAX = 40


def _painel(u: dict) -> dict:
    try:
        d = json.loads(u.get("painel") or "{}")
    except ValueError:
        d = {}
    nomes = lambda k: [str(x)[:40] for x in d.get(k, []) if isinstance(x, str)][:PAINEL_MAX]  # noqa: E731
    return {"abas_ordem": nomes("abas_ordem"),
            "abas_ocultas": [a for a in nomes("abas_ocultas") if a not in ABAS_FIXAS]}


@app.get("/api/painel")
def ver_painel(u: dict = Depends(usuario)):
    return _painel(u) | {"fixas": list(ABAS_FIXAS)}


@app.post("/api/painel")
async def salvar_painel(request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    limpo = _painel({"painel": json.dumps({"abas_ordem": d.get("abas_ordem", []),
                                           "abas_ocultas": d.get("abas_ocultas", [])}, ensure_ascii=False)})
    banco.executar("UPDATE usuarios SET painel=? WHERE id=?", json.dumps(limpo, ensure_ascii=False), u["id"])
    return limpo | {"fixas": list(ABAS_FIXAS)}


@app.get("/api/prefs")
def ver_prefs(u: dict = Depends(usuario)):
    return {"prefs": gosto.prefs(u), "tipos": {k: v["rotulo"] for k, v in gosto.TIPOS.items()}, "nichos": ia.NICHOS}


def _medir_referencias(usuario_id: int, refs: list[str]) -> None:
    """Os canais de referência das perguntas: mede, classifica e procura os parecidos (vão para os Achados)."""
    ids = []
    for ref in refs:
        try:
            cid = _resolver(ref)
            perfil.conectar(usuario_id, cid, meu=False)
            ids.append(cid)
            for c in garimpo.parecidos(cid)[:15]:
                banco.executar("INSERT OR IGNORE INTO achados (usuario_id, canal_id, por_causa_de, criado) VALUES (?,?,?,?)",
                               usuario_id, c["id"], cid, banco.agora())
        except Exception as erro:
            print("referência", ref, "falhou:", erro)
    u = banco.um("SELECT * FROM usuarios WHERE id=?", usuario_id)
    p = gosto.prefs(u) | {"referencias_ids": ids}
    banco.executar("UPDATE usuarios SET prefs=? WHERE id=?", json.dumps(p, ensure_ascii=False), usuario_id)


@app.post("/api/prefs")
async def salvar_prefs(request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    p = gosto.salvar_prefs(u["id"], d)
    if p["referencias"]:
        threading.Thread(target=_medir_referencias, args=(u["id"], p["referencias"]), daemon=True).start()
    return {"prefs": p}


@app.get("/api/bloqueios")
def ver_bloqueios(u: dict = Depends(usuario)):
    return {"bloqueios": gosto.bloqueios(u["id"])}


@app.post("/api/bloqueios")
async def bloquear(request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    try:
        gosto.bloquear(u["id"], str(d.get("tipo", "")), str(d.get("valor", "")), str(d.get("rotulo", "")))
    except ValueError as erro:
        raise HTTPException(400, str(erro))
    return {"ok": True}


@app.delete("/api/bloqueios")
async def desbloquear(request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    gosto.desbloquear(u["id"], str(d.get("tipo", "")), str(d.get("valor", "")))
    return {"ok": True}


@app.get("/api/explorar")
def explorar(request: Request, u: dict = Depends(usuario)):
    q = dict(request.query_params)
    return {"videos": gosto.explorar(u, q.get("nicho", ""), semente=int(q.get("semente") or 0) or None,
                                     lingua=q.get("lingua", ""), filtros=q)}


@app.post("/api/explorar/mais")
def explorar_mais(u: dict = Depends(usuario)):
    """Busca no YouTube um termo sorteado dos nichos da pessoa, para encher o Explorar com vídeos novos."""
    import random
    p = gosto.prefs(u)
    termos = garimpo.termos()
    nichos = [n for n in p["nichos"] if termos.get(n)] or list(termos)
    nicho = random.choice(nichos)
    termo = random.choice(termos[nicho])
    try:
        r = perfil.procurar(termo, random.randrange(len(perfil.JEITOS)))
    except youtube.SemCota as erro:
        _sem_cota(erro)
    return {"termo": termo, "nicho": nicho, "novos": len(r["novos"]), "vistos": r["vistos"]}


# ---------------------------------------------------------------- ideias de cada canal, painel da direita e treino

def _meu_canal(usuario_id: int, canal_id: str) -> dict:
    c = banco.um("SELECT c.* FROM meus_canais m JOIN canais c ON c.id=m.canal_id WHERE m.usuario_id=? AND c.id=?",
                 usuario_id, canal_id)
    if not c:
        raise HTTPException(404, "Esse canal não está em Meus canais.")
    return c


@app.get("/api/meus-canais")
def meus_canais(u: dict = Depends(usuario)):
    return {"canais": banco.todos("SELECT c.id, c.titulo, c.foto, c.nicho, c.subnicho FROM meus_canais m "
                                  "JOIN canais c ON c.id=m.canal_id WHERE m.usuario_id=? ORDER BY c.inscritos DESC", u["id"])}


@app.get("/api/meus-canais/{canal_id}/ideias")
def ideias_do_canal(canal_id: str, request: Request, u: dict = Depends(usuario)):
    c = _meu_canal(u["id"], canal_id)
    lista = trabalho.ideias(u, c, dict(request.query_params))
    pagina = int(_numero(dict(request.query_params), "pagina") or 0)
    return {"total": len(lista), "videos": lista[pagina * 36:(pagina + 1) * 36], "canal": _vitrine(c, com_videos=False)}


@app.get("/api/ideias-salvas")
def ver_ideias_salvas(u: dict = Depends(usuario)):
    return trabalho.ideias_salvas(u["id"])


@app.post("/api/ideias-salvas")
async def salvar_ideia(request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    vid = str(d.get("video_id", ""))
    if not re.fullmatch(r"[\w-]{11}", vid):
        raise HTTPException(400, "Vídeo inválido.")
    canal_id = str(d.get("canal_id", ""))
    if canal_id:
        _meu_canal(u["id"], canal_id)
    trabalho.salvar_ideia(u["id"], canal_id, vid, str(d.get("titulo", "")))
    return {"ok": True}


@app.delete("/api/ideias-salvas/{ideia_id}")
def tirar_ideia(ideia_id: int, u: dict = Depends(usuario)):
    trabalho.tirar_ideia(u["id"], ideia_id)
    return {"ok": True}


@app.get("/api/thumb-projetos")
def thumb_projetos(u: dict = Depends(usuario)):
    return {"projetos": thumb.projetos(u["id"]), "padrao": thumb.PADRAO, "campos": thumb.CAMPOS}


@app.post("/api/thumb-projetos")
async def thumb_salvar(request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    if d.get("canal_id"):
        _meu_canal(u["id"], str(d["canal_id"]))
    try:
        return {"id": thumb.salvar(u["id"], d)}
    except ValueError as erro:
        raise HTTPException(400, str(erro))


@app.delete("/api/thumb-projetos/{pid}")
def thumb_apagar(pid: int, u: dict = Depends(usuario)):
    thumb.apagar(u["id"], pid)
    return {"ok": True}


@app.post("/api/thumb/prompt")
async def thumb_prompt(request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    vid = roteiro_claude.id_do_video(str(d.get("link") or d.get("video_id") or "")) or ""
    return thumb.montar(u["id"], int(d["projeto_id"]) if d.get("projeto_id") else None, str(d.get("titulo", "")), vid)


@app.get("/api/radar-paises")
def radar_paises_lista(u: dict = Depends(usuario)):
    return {"projetos": radar_paises.projetos(u["id"]),
            "paises": [{"codigo": c, "nome": n, "lingua": l} for c, (n, l) in radar_paises.PAISES.items()],
            "linguas": radar_paises.LINGUAS}


@app.post("/api/radar-paises")
async def radar_paises_salvar(request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    if d.get("canal_id"):
        _meu_canal(u["id"], str(d["canal_id"]))
    try:
        return {"id": radar_paises.salvar(u["id"], d)}
    except ValueError as erro:
        raise HTTPException(400, str(erro))


@app.delete("/api/radar-paises/{pid}")
def radar_paises_apagar(pid: int, u: dict = Depends(usuario)):
    radar_paises.apagar(u["id"], pid)
    return {"ok": True}


@app.post("/api/radar-paises/{pid}/conferir")
async def radar_paises_conferir(pid: int, request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    titulo = str(d.get("titulo", "")).strip()
    if not titulo:
        raise HTTPException(400, "Falta o título do vídeo.")
    try:
        return radar_paises.conferir(u["id"], pid, str(d.get("video_id", "")), titulo)
    except ValueError as erro:
        raise HTTPException(404, str(erro))
    except youtube.SemCota as erro:
        _sem_cota(erro)


@app.get("/api/alvos")
def alvos_lista(u: dict = Depends(usuario)):
    return {"canais": alvos.tudo(u["id"])}


@app.post("/api/alvos")
async def alvos_marcar(request: Request, u: dict = Depends(usuario)):
    """O 🎯 de um vídeo: ensina o algoritmo de um canal da pessoa ("quero ideias assim"). ligar=false desfaz."""
    d = await request.json()
    canal_id = str(d.get("canal_id", ""))
    _meu_canal(u["id"], canal_id)
    total = alvos.marcar(u["id"], canal_id, str(d.get("video_id", "")), str(d.get("titulo", "")), bool(d.get("ligar", True)))
    return {"total": total} | alvos.contagem(u["id"], canal_id)


@app.post("/api/alvos/canal")
async def alvos_inscrever(request: Request, u: dict = Depends(usuario)):
    """Inscreve um canal no algoritmo de um canal da pessoa: os assuntos dele pesam nas ideias."""
    d = await request.json()
    canal_id, ref = str(d.get("canal_id", "")), str(d.get("ref_canal_id", ""))
    _meu_canal(u["id"], canal_id)
    if not ref or ref == canal_id:
        raise HTTPException(400, "Escolha outro canal.")
    alvos.inscrever(u["id"], canal_id, ref, bool(d.get("ligar", True)))
    return alvos.contagem(u["id"], canal_id)


@app.get("/api/inicio")
def inicio_dados(u: dict = Depends(usuario)):
    """A primeira página: os canais da pessoa com o que falta em cada um, e os números do mapa do app."""
    no_studio = set(studio.conectados(u["id"]))
    canais = []
    for c in banco.todos("SELECT c.* FROM meus_canais m JOIN canais c ON c.id=m.canal_id WHERE m.usuario_id=? "
                         "ORDER BY c.inscritos DESC", u["id"]):
        t = treinamento.estado(u["id"], c["id"]) or {}
        cfg = producao.config(u["id"], c["id"])         # o cartão grande do Início mostra a língua e a voz do canal
        canais.append(_vitrine(c, com_videos=False) | {"lingua": cfg.get("lingua", ""), "voz": cfg.get("voz", ""),
                                                      "configurado": bool(cfg.get("perfil")),
                                                      "studio": c["id"] in no_studio, "treinado": bool(t.get("feito")),
                                                      "radar": bool(banco.um("SELECT 1 AS x FROM radar_projetos WHERE usuario_id=? AND canal_id=?", u["id"], c["id"]))})
    um = lambda sql, *a: banco.um(sql, *a)["n"]  # noqa: E731
    return {"eu": _publico(u), "canais": canais, "numeros": {
        "ideias_salvas": um("SELECT COUNT(*) AS n FROM ideias_salvas WHERE usuario_id=?", u["id"]),
        "roteiros": len(roteiro_claude.lista(u["id"])),
        "radares": um("SELECT COUNT(*) AS n FROM radar_projetos WHERE usuario_id=?", u["id"]),
        "canais_radar": um("SELECT COUNT(*) AS n FROM canais WHERE no_radar=1"),
        "ideias_base": um("SELECT COUNT(*) AS n FROM outliers WHERE nota>=3")}}


@app.get("/api/treinamento/{canal_id}")
def treinamento_estado(canal_id: str, u: dict = Depends(usuario)):
    _meu_canal(u["id"], canal_id)
    t = treinamento.estado(u["id"], canal_id) or {}
    refs = medir._canais_do_banco(t.get("referencias", []))
    return {"feito": bool(t.get("feito")), "quando": t.get("feito", ""), "termos": t.get("termos", []),
            "escolhidos": len(t.get("positivos", [])), "referencias": [medir._canal_publico(c) for c in refs],
            "minimo": treinamento.MINIMO, "maximo": treinamento.MAXIMO}


@app.post("/api/treinamento/{canal_id}/referencias")
async def treinamento_referencias(canal_id: str, request: Request, u: dict = Depends(usuario)):
    _meu_canal(u["id"], canal_id)
    refs = [str(r) for r in (await request.json()).get("refs", []) if str(r).strip()][:3]
    if not refs:
        raise HTTPException(400, "Cole pelo menos um canal de referência.")
    try:
        ids = [_resolver(r) for r in refs]
        return {"referencias": treinamento.referencias(u["id"], canal_id, ids)}
    except youtube.SemCota as erro:
        _sem_cota(erro)


@app.post("/api/treinamento/{canal_id}/candidatos")
async def treinamento_candidatos(canal_id: str, request: Request, u: dict = Depends(usuario)):
    _meu_canal(u["id"], canal_id)
    excluir = set((await request.json()).get("excluir", []))
    return {"videos": treinamento.candidatos(u, canal_id, excluir)}


@app.post("/api/treinamento/{canal_id}/concluir")
async def treinamento_concluir(canal_id: str, request: Request, u: dict = Depends(usuario)):
    _meu_canal(u["id"], canal_id)
    d = await request.json()
    positivos = [str(v) for v in d.get("positivos", [])][:treinamento.MAXIMO * 2]
    if len(positivos) < treinamento.MINIMO:
        raise HTTPException(400, f"Escolha pelo menos {treinamento.MINIMO} vídeos que você faria.")
    return {"tarefa": treinamento.comecar(u, canal_id, positivos, [str(v) for v in d.get("negativos", [])][:200])}


@app.get("/api/treinamento/tarefa/{tid}")
def treinamento_tarefa(tid: str, u: dict = Depends(usuario)):
    t = treinamento.tarefa(u["id"], tid)
    if not t:
        raise HTTPException(404)
    return {k: t[k] for k in ("estado", "passo", "resultado", "erro")}


@app.delete("/api/treinamento/{canal_id}")
def treinamento_recomecar(canal_id: str, u: dict = Depends(usuario)):
    _meu_canal(u["id"], canal_id)
    treinamento.recomecar(u["id"], canal_id)
    return {"ok": True}


@app.get("/api/ext/assunto/{canal_id}")
def ext_assunto(canal_id: str, u: dict = Depends(usuario)):
    """Para a extensão: as palavras do assunto do canal, do treino feito no site (o selo 🎯)."""
    c = _meu_canal(u["id"], canal_id)
    return {"palavras": sorted(trabalho.assunto(c, u["id"])), "titulo": c["titulo"]}


# ---------------------------------------------------------------- trabalho: roteiro para a fábrica

@app.get("/api/canal-painel/{canal_id}")
def canal_painel_ver(canal_id: str, u: dict = Depends(usuario)):
    """A página do canal: números, os que mais renderam, gasto na fábrica, agenda e concorrentes."""
    _meu_canal(u["id"], canal_id)
    return canal_painel.painel(u["id"], canal_id)


@app.get("/api/canal-painel/{canal_id}/ultimo")
def canal_painel_ultimo(canal_id: str, u: dict = Depends(usuario)):
    """O desempenho do último vídeo do canal (o card do canto direito da página do canal)."""
    _meu_canal(u["id"], canal_id)
    try:
        return studio.ultimo_video(u["id"], canal_id)
    except youtube.SemCota as erro:
        _sem_cota(erro)
    except RuntimeError as erro:
        raise HTTPException(404, str(erro))


@app.post("/api/canal-painel/{canal_id}/agenda")
async def canal_painel_agenda(canal_id: str, request: Request, u: dict = Depends(usuario)):
    _meu_canal(u["id"], canal_id)
    canal_painel.salvar_agenda(u["id"], canal_id, await request.json())
    return canal_painel.painel(u["id"], canal_id)


@app.post("/api/canal-painel/{canal_id}/concorrentes")
async def canal_painel_concorrente(canal_id: str, request: Request, u: dict = Depends(usuario)):
    """Acompanha um canal concorrente (pelo @): ele é medido (uns 3 de cota) e o Radar avisa quando um vídeo dele estoura."""
    _meu_canal(u["id"], canal_id)
    try:
        ref = _resolver(str((await request.json()).get("ref", "")))
        perfil.conectar(u["id"], ref, meu=False)
        canal_painel.concorrente(u["id"], canal_id, ref, True)
    except youtube.SemCota as erro:
        _sem_cota(erro)
    except ValueError as erro:
        raise HTTPException(400, str(erro))
    return canal_painel.painel(u["id"], canal_id)


@app.delete("/api/canal-painel/{canal_id}/concorrentes/{ref_id}")
def canal_painel_tirar(canal_id: str, ref_id: str, u: dict = Depends(usuario)):
    _meu_canal(u["id"], canal_id)
    canal_painel.concorrente(u["id"], canal_id, ref_id, False)
    return canal_painel.painel(u["id"], canal_id)


@app.get("/api/canal-painel/{canal_id}/fabrica")
def canal_painel_fabrica(canal_id: str, u: dict = Depends(usuario)):
    _meu_canal(u["id"], canal_id)
    try:
        return canal_painel.perfil_fabrica(u["id"], canal_id)
    except ValueError as erro:
        raise HTTPException(400, str(erro))


@app.post("/api/canal-painel/{canal_id}/fabrica")
async def canal_painel_fabrica_salvar(canal_id: str, request: Request, u: dict = Depends(dono_da_fabrica)):
    """Grava no perfil da fábrica do canal o texto fixo da descrição e os shorts (vale para os próximos vídeos)."""
    _meu_canal(u["id"], canal_id)
    try:
        return canal_painel.perfil_fabrica(u["id"], canal_id, await request.json())
    except ValueError as erro:
        raise HTTPException(400, str(erro))


@app.get("/api/producao/{canal_id}")
def producao_config(canal_id: str, u: dict = Depends(usuario)):
    """O que o Roteiro e a Thumbnail puxam ao escolher o canal: perfil da fábrica (a voz), estilos, tempo, língua."""
    _meu_canal(u["id"], canal_id)
    cfg = producao.config(u["id"], canal_id)
    perfil = cfg.get("perfil") or ""
    return cfg | {"perfis": producao.perfis(), "ias": {k: n for k, (n, _) in producao.IAS_IMAGEM.items()},
                  "telas_finais": producao.TELAS_FINAIS,
                  # o rodapé mora no perfil da fábrica, que é quem escreve a descrição
                  "rodape": producao.rodape_do_perfil(perfil),
                  "rodapes_padrao": {t: publicar.rodape_padrao(cfg.get("lingua") or "", t, cfg.get("canal") or "",
                                                               cfg.get("marcas") or "") for t in publicar.TIPOS},
                  "tipos_de_modelo": publicar.TIPOS}


@app.post("/api/producao/{canal_id}")
async def producao_salvar(canal_id: str, request: Request, u: dict = Depends(usuario)):
    _meu_canal(u["id"], canal_id)
    dados = await request.json()
    cfg = producao.salvar(u["id"], canal_id, dados)
    # o rodapé não é do Radar: vai para o perfil da fábrica, que é quem escreve a descrição de cada vídeo
    if "rodape" in dados and cfg.get("perfil"):
        try:
            cfg["rodape"] = producao.salvar_rodape(cfg["perfil"], str(dados.get("rodape") or ""))
        except ValueError as erro:
            raise HTTPException(400, str(erro))
    return cfg


@app.get("/api/thumb/imagem/{video_id}")
def thumb_imagem(video_id: str, u: dict = Depends(usuario)):
    """A thumbnail de um vídeo pelo próprio site, para o navegador poder copiar a imagem (o i.ytimg.com não deixa)."""
    if not re.fullmatch(r"[\w-]{11}", video_id):
        raise HTTPException(400, "Vídeo inválido.")
    for nome in ("maxresdefault", "hqdefault"):
        r = httpx.get(f"https://i.ytimg.com/vi/{video_id}/{nome}.jpg", timeout=15)
        if r.status_code == 200:
            return Response(r.content, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})
    raise HTTPException(404, "Thumbnail não encontrada.")


_ENVIOS: dict[str, dict] = {}     # id -> {prompt, video_id, quando}: o que a extensão cola no ChatGPT ou no Gemini


@app.post("/api/envios")
async def envio_criar(request: Request, u: dict = Depends(usuario)):
    """Guarda o prompt e a thumbnail de referência para a extensão colar sozinha no ChatGPT ou no Gemini (a página
    deles abre com #radar-envio=ID). Vale 10 minutos."""
    d = await request.json()
    agora = time.time()
    for velho in [k for k, v in _ENVIOS.items() if agora - v["quando"] > 600]:
        _ENVIOS.pop(velho, None)
    eid = secrets.token_urlsafe(9)
    vid = str(d.get("video_id", ""))
    _ENVIOS[eid] = {"prompt": str(d.get("prompt", ""))[:8000], "video_id": vid if re.fullmatch(r"[\w-]{11}", vid) else "",
                    "quando": agora, "usuario_id": u["id"]}
    return {"id": eid}


@app.get("/api/ext/envio/{eid}")
def envio_ler(eid: str, u: dict = Depends(usuario)):
    e = _ENVIOS.pop(eid, None)      # uma vez só: colou, acabou
    if not e or e["usuario_id"] != u["id"]:
        raise HTTPException(404, "Envio não encontrado (passou de 10 minutos?).")
    return {"prompt": e["prompt"], "imagem": f"/api/thumb/imagem/{e['video_id']}" if e["video_id"] else ""}


@app.post("/api/thumb/claude")
async def thumb_claude(request: Request, u: dict = Depends(usuario)):
    """O Claude escreve o prompt da thumbnail: o estilo do canal, o pedido da pessoa e a referência."""
    d = await request.json()
    vid = roteiro_claude.id_do_video(str(d.get("link") or "")) or ""
    try:
        return await run_in_threadpool(producao.prompt_da_thumb, u["id"], int(d["projeto_id"]) if d.get("projeto_id") else None,
                                       str(d.get("pedido", ""))[:2000], str(d.get("titulo", ""))[:200], vid, str(d.get("ia", "gemini")))
    except RuntimeError as erro:
        raise HTTPException(503, str(erro))


@app.post("/api/assistente")
async def assistente(request: Request, u: dict = Depends(usuario)):
    """A janela de IA ao lado do Roteiro e da Thumbnail e o painel do Claude no YouTube (o Claude, pela assinatura)."""
    d = await request.json()
    canal_id = str(d.get("canal_id", ""))
    if canal_id:
        _meu_canal(u["id"], canal_id)
    mensagens = [m for m in d.get("mensagens", []) if isinstance(m, dict)][-12:]
    if not mensagens:
        raise HTTPException(400, "Escreva uma mensagem.")
    try:
        pagina = d.get("pagina") if isinstance(d.get("pagina"), dict) else None
        projeto_id = str(d.get("projeto_id", ""))
        return {"resposta": await run_in_threadpool(producao.assistente, u["id"], canal_id, mensagens, pagina,
                                                    projeto_id)}
    except RuntimeError as erro:
        raise HTTPException(503, str(erro))


def _projeto_fabrica(nome: str):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", nome or ""):
        raise HTTPException(400, "Projeto inválido.")
    pasta = roteiro_claude.FABRICA / "projetos" / nome
    if not pasta.is_dir():
        raise HTTPException(404, "Projeto não encontrado na fábrica.")
    return pasta


@app.get("/api/fabrica/vozes")
def fabrica_vozes(lingua: str = "português", busca: str = "", genero: str = "", u: dict = Depends(usuario)):
    """As vozes da fábrica (GenAI Pro), com a prévia, para escolher a voz do canal. Não gasta crédito."""
    try:
        return fabrica_api.vozes(lingua, busca, genero)
    except fabrica_api.SemFabrica as erro:
        raise HTTPException(503, str(erro))


@app.post("/api/producao/{canal_id}/voz")
async def producao_voz(canal_id: str, request: Request, u: dict = Depends(dono_da_fabrica)):
    """A voz escolhida vira o canal na fábrica (perfil canal-NOME) e fica como a voz deste canal no Radar."""
    c = _meu_canal(u["id"], canal_id)
    d = await request.json()
    if not str(d.get("voice_id", "")).strip():
        raise HTTPException(400, "Escolha uma voz.")
    try:
        perfil_novo = fabrica_api.criar_canal(c["titulo"], d)
    except fabrica_api.SemFabrica as erro:
        raise HTTPException(503, str(erro))
    return producao.salvar(u["id"], canal_id, producao.config(u["id"], canal_id) | {"perfil": perfil_novo})


@app.get("/api/producoes")
def producoes_lista(u: dict = Depends(usuario)):
    """Acompanhar e Resultados: os projetos da fábrica, em andamento e prontos."""
    try:
        return fabrica_api.producoes()
    except fabrica_api.SemFabrica as erro:
        raise HTTPException(503, str(erro))


@app.get("/api/resultados/canais")
def resultados_canais(u: dict = Depends(usuario)):
    """Para qual canal a pessoa arrastou cada vídeo pronto (vale por cima do canal que vem do perfil da fábrica)."""
    return {"canais": {l["projeto"]: l["canal"] for l in banco.todos(
        "SELECT projeto, canal FROM resultado_canal WHERE usuario_id=?", u["id"])}}


@app.post("/api/resultados/{nome}/canal")
async def resultado_mover(nome: str, request: Request, u: dict = Depends(usuario)):
    _projeto_fabrica(nome)
    canal = str((await request.json()).get("canal", "")).strip()[:100]
    if not canal:
        raise HTTPException(400, "Escolha o canal.")
    banco.executar("INSERT OR REPLACE INTO resultado_canal (usuario_id, projeto, canal) VALUES (?,?,?)", u["id"], nome, canal)
    return {"ok": True}


@app.get("/api/resultados/publicados")
def resultados_publicados(u: dict = Depends(usuario)):
    """Os vídeos marcados como publicados à mão (o link que a pessoa colou)."""
    return {"publicados": {l["projeto"]: l["video_id"] for l in banco.todos(
        "SELECT projeto, video_id FROM resultado_publicado WHERE usuario_id=?", u["id"])}}


@app.post("/api/resultados/{nome}/publicado")
async def resultado_publicado(nome: str, request: Request, u: dict = Depends(usuario)):
    """Marca o vídeo como publicado com o link do YouTube (vazio desmarca)."""
    _projeto_fabrica(nome)
    d = await request.json()
    if d.get("postado"):     # "Postei tudo": marca o vídeo e os shorts como postados, sem pedir o link
        banco.executar("INSERT OR REPLACE INTO resultado_publicado (usuario_id, projeto, video_id) VALUES (?,?,?)", u["id"], nome, "-")
        itens = ["video"] + [s["id"] for s in fabrica_api._shorts(nome)]
        banco.varios("INSERT OR REPLACE INTO resultado_postado (usuario_id, projeto, item, quando) VALUES (?,?,?,?)",
                     [(u["id"], nome, i, banco.agora()) for i in itens])
        return {"ok": True}
    link = str(d.get("link", "")).strip()
    if not link:
        banco.executar("DELETE FROM resultado_publicado WHERE usuario_id=? AND projeto=?", u["id"], nome)
        return {"ok": True}
    vid = roteiro_claude.id_do_video(link)
    if not vid:
        raise HTTPException(400, "Não reconheci o link do YouTube.")
    banco.executar("INSERT OR REPLACE INTO resultado_publicado (usuario_id, projeto, video_id) VALUES (?,?,?)", u["id"], nome, vid)
    return {"ok": True, "video_id": vid}


@app.post("/api/resultados/{nome}/postado")
async def resultado_postado(nome: str, request: Request, u: dict = Depends(usuario)):
    """Marca (ou desmarca) um item como postado: o vídeo ("video") ou um short ("S01"...). O vídeo postado conta
    como publicado nos Resultados."""
    _projeto_fabrica(nome)
    d = await request.json()
    item = str(d.get("item", ""))
    if item != "video" and not re.fullmatch(r"S\d{2}", item):
        raise HTTPException(400, "Item inválido.")
    if d.get("postado", True):
        banco.executar("INSERT OR REPLACE INTO resultado_postado (usuario_id, projeto, item, quando) VALUES (?,?,?,?)", u["id"], nome, item, banco.agora())
        if item == "video" and not banco.um("SELECT 1 AS x FROM resultado_publicado WHERE usuario_id=? AND projeto=?", u["id"], nome):
            banco.executar("INSERT INTO resultado_publicado (usuario_id, projeto, video_id) VALUES (?,?,?)", u["id"], nome, "-")
    else:
        banco.executar("DELETE FROM resultado_postado WHERE usuario_id=? AND projeto=? AND item=?", u["id"], nome, item)
        if item == "video":
            banco.executar("DELETE FROM resultado_publicado WHERE usuario_id=? AND projeto=? AND video_id='-'", u["id"], nome)
    return {"ok": True}


@app.post("/api/resultados/views")
async def resultados_views(request: Request, u: dict = Depends(usuario)):
    """As views dos vídeos publicados (1 unidade da cota a cada 50 vídeos)."""
    ids = [i for i in (await request.json()).get("ids", []) if re.fullmatch(r"[\w-]{11}", str(i))][:200]
    try:
        with youtube.gastando("studio"):   # as views dos meus vídeos publicados, não do garimpo
            return {"videos": {v["id"]: {"views": v["views"], "curtidas": v.get("curtidas"), "comentarios": v.get("comentarios"),
                                         "publicado": v.get("publicado")} for v in youtube.videos(ids)}}
    except youtube.SemCota as erro:
        _sem_cota(erro)


@app.get("/api/producoes/{nome}/shorts/{sid}")
def producao_short(nome: str, sid: str, u: dict = Depends(usuario)):
    if not re.fullmatch(r"S\d{2}", sid):
        raise HTTPException(400, "Short inválido.")
    arquivo = _projeto_fabrica(nome) / "shorts" / f"{sid}.mp4"
    if not arquivo.exists():
        raise HTTPException(404, "Short não encontrado.")
    return FileResponse(arquivo, media_type="video/mp4")


@app.get("/api/producoes/{nome}/custo")
def producao_custo(nome: str, u: dict = Depends(usuario)):
    _projeto_fabrica(nome)
    try:
        return fabrica_api.custo(nome)
    except fabrica_api.SemFabrica as erro:
        raise HTTPException(503, str(erro))


@app.post("/api/producoes/{nome}/produzir")
async def producao_produzir(nome: str, request: Request, u: dict = Depends(dono_da_fabrica)):
    """Sem confirmar: só a estimativa. Com confirmar: a fábrica produz (gasta, por isso pede a confirmação)."""
    _projeto_fabrica(nome)
    d = await request.json()
    try:
        return fabrica_api.produzir(nome, bool(d.get("confirmar")))
    except fabrica_api.SemFabrica as erro:
        raise HTTPException(503, str(erro))


@app.get("/api/producoes/{nome}/capa")
def producao_capa(nome: str, u: dict = Depends(usuario)):
    pasta = _projeto_fabrica(nome)
    for arquivo in ("thumbnail.jpg", "thumb_1.jpg", "thumbnail_referencia.jpg"):   # a da referência enquanto não tem a própria
        if (pasta / arquivo).exists():
            return FileResponse(pasta / arquivo, headers={"Cache-Control": "max-age=300"})
    raise HTTPException(404, "Sem capa.")


@app.get("/api/producoes/{nome}/video")
def producao_video(nome: str, u: dict = Depends(usuario)):
    """O vídeo pronto, para assistir no Radar (o FileResponse responde aos pedaços que o player pede)."""
    final = _projeto_fabrica(nome) / "final.mp4"
    if not final.exists():
        raise HTTPException(404, "O vídeo ainda não está pronto.")
    return FileResponse(final, media_type="video/mp4")


@app.post("/api/producoes/{nome}/pasta")
def producao_pasta(nome: str, request: Request, u: dict = Depends(usuario)):
    """Abre a pasta da entrega (ou do projeto) no Explorador. Só neste computador."""
    if _de_fora(request):
        raise HTTPException(403, "A pasta abre no computador da fábrica: por aqui, use o ▶ Assistir.")
    pasta = _projeto_fabrica(nome)
    try:
        entrega = json.loads((pasta / "entrega_pc.json").read_text(encoding="utf-8")).get("pasta")
    except (OSError, ValueError):
        entrega = ""
    alvo = entrega if entrega and os.path.isdir(entrega) else str(pasta)
    os.startfile(alvo)  # noqa: S606 (abre o Explorador do Windows na pasta)
    return {"pasta": alvo}


# ---------------------------------------------------------------- a fila da Nova produção, 2026-10-18

def _na_fila(funcao, *args):
    try:
        return funcao(*args)
    except ValueError as erro:
        raise HTTPException(400, str(erro))


@app.get("/api/fila")
def fila_lista(u: dict = Depends(usuario)):
    return {"itens": fila.listar(u["id"]), "limite": fila.limite()}


@app.post("/api/fila")
def fila_criar(corpo: dict, u: dict = Depends(dono_da_fabrica)):
    return _na_fila(fila.criar, u["id"], corpo.get("pedido") or {}, bool(corpo.get("comecar")))


@app.post("/api/fila/ajustes")
def fila_ajustes(corpo: dict, u: dict = Depends(dono_da_fabrica)):
    return {"limite": _na_fila(fila.definir_limite, int(corpo.get("limite") or 0))}


@app.get("/api/fila/estimativa")
def fila_estimativa(canal: str = "", minutos: float = 0, u: dict = Depends(usuario)):
    """O custo provável do vídeo na prévia da Nova produção (canal = o perfil da fábrica do canal)."""
    try:
        return fila.estimativa(fila.entregues(), canal, minutos)
    except fabrica_api.SemFabrica:
        return {"usd": None, "base": None}


@app.get("/api/fila/ajustes")
def fila_ajustes_ver(u: dict = Depends(usuario)):
    return {"limite": fila.limite(), "opcoes": list(fila.LIMITES)}


@app.get("/api/fila/{fid}/roteiro")
def fila_roteiro(fid: int, u: dict = Depends(usuario)):
    """O roteiro do pedido, para revisar antes de aprovar (salvar é pelo /api/roteiros/{nome}/texto)."""
    item = fila.item(u["id"], fid)
    if not item or not item["roteiro"]:
        raise HTTPException(404, "Este pedido ainda não tem roteiro.")
    try:
        pasta, meta = roteiro_claude._do_usuario(u["id"], item["roteiro"])
    except RuntimeError as erro:
        raise HTTPException(404, str(erro))
    texto = (pasta / "roteiro.txt").read_text(encoding="utf-8")
    return {"nome": item["roteiro"], "titulo": meta.get("titulo", ""), "roteiro": texto, "palavras": len(texto.split())}


@app.post("/api/fila/{fid}/comecar")
def fila_comecar(fid: int, u: dict = Depends(dono_da_fabrica)):
    return _na_fila(fila.comecar, u["id"], fid)


@app.post("/api/fila/{fid}/aprovar")
def fila_aprovar(fid: int, u: dict = Depends(dono_da_fabrica)):
    return _na_fila(fila.aprovar, u["id"], fid)


@app.post("/api/fila/{fid}/tentar")
def fila_tentar(fid: int, u: dict = Depends(dono_da_fabrica)):
    return _na_fila(fila.tentar, u["id"], fid)


@app.delete("/api/fila/{fid}")
def fila_excluir(fid: int, u: dict = Depends(dono_da_fabrica)):
    projeto = _na_fila(fila.excluir, u["id"], fid)
    if projeto:
        try:
            fabrica_api.apagar(projeto)
        except fabrica_api.SemFabrica as erro:
            raise HTTPException(503, f"O pedido saiu da fila, mas o vídeo continua na fábrica: {erro}")
    return {"ok": True}


# ---------------------------------------------------------------- o Acompanhar novo, 2026-10-18

@app.get("/api/acompanhar")
async def acompanhar_lista(u: dict = Depends(usuario)):
    """Os blocos da esquerda (precisa de você, produzindo, na fila, entrada, parados) e os números do topo."""
    try:
        prod, ligada = await run_in_threadpool(fabrica_api.producoes), True
    except fabrica_api.SemFabrica:
        prod, ligada = {"andamento": [], "prontos": []}, False
    nomes = {c["id"]: c["titulo"] for c in banco.todos("SELECT c.id, c.titulo FROM meus_canais m JOIN canais c ON c.id=m.canal_id WHERE m.usuario_id=?", u["id"])}
    b = diagnostico.blocos(fila.listar(u["id"]), prod)
    for chave in ("precisa_voce", "produzindo", "na_fila", "entrada"):
        for item in b[chave]:
            item["canal"] = item.get("canal") or nomes.get(item.get("canal_id", ""), "")
    return b | {"limite": fila.limite(), "fabrica_ligada": ligada, "prontos_hoje": sum(
        1 for p in prod["prontos"] if (p.get("criado") or "")[:10] == datetime.now(banco.BRASILIA).date().isoformat())}


@app.get("/api/acompanhar/{nome}")
async def acompanhar_video(nome: str, u: dict = Depends(usuario)):
    """O vídeo escolhido: o andamento ao vivo e as etapas com o tempo de cada uma."""
    pasta = _projeto_fabrica(nome)
    try:
        st = await run_in_threadpool(fabrica_api.status, nome)
    except fabrica_api.SemFabrica:
        st = {}
    return {"nome": nome, "titulo": fabrica_api._titulo(nome), "status": st, "etapas": diagnostico.etapas(pasta, st),
            "tem_final": (pasta / "final.mp4").exists(), "pago_pendente": st.get("pago_pendente"),
            "legenda": next((f for f in ("legendas_final.srt", "legendas.srt") if (pasta / f).exists()), "")}


@app.get("/api/acompanhar/{nome}/diagnostico")
def acompanhar_diagnostico(nome: str, tipo: str = "todos", u: dict = Depends(usuario)):
    pasta = _projeto_fabrica(nome)
    return {"contagem": diagnostico.contagem(pasta), "log": diagnostico.log(pasta, tipo)[-400:]}


@app.get("/api/acompanhar/{nome}/log.txt")
def acompanhar_log(nome: str, u: dict = Depends(usuario)):
    texto = "\n".join(l["texto"] for l in diagnostico.log(_projeto_fabrica(nome)))
    return Response(texto, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="log-{nome}.txt"'})


@app.get("/api/acompanhar/{nome}/legenda")
def acompanhar_legenda(nome: str, u: dict = Depends(usuario)):
    pasta = _projeto_fabrica(nome)
    arquivo = next((pasta / f for f in ("legendas_final.srt", "legendas.srt") if (pasta / f).exists()), None)
    if not arquivo:
        raise HTTPException(404, "A legenda fica pronta quando a produção terminar.")
    return FileResponse(arquivo, media_type="application/x-subrip", filename=f"{nome}.srt")


@app.get("/api/acompanhar/{nome}/publicacao")
async def acompanhar_publicacao(nome: str, u: dict = Depends(usuario)):
    _projeto_fabrica(nome)
    try:
        return await run_in_threadpool(fabrica_api.publicacao, nome)
    except fabrica_api.SemFabrica as erro:
        raise HTTPException(503, str(erro))


@app.post("/api/acompanhar/{nome}/publicacao")
async def acompanhar_gerar_publicacao(nome: str, u: dict = Depends(dono_da_fabrica)):
    _projeto_fabrica(nome)
    try:
        return await run_in_threadpool(fabrica_api.gerar_publicacao, nome)
    except fabrica_api.SemFabrica as erro:
        raise HTTPException(400, str(erro))


@app.post("/api/acompanhar/{nome}/pago")
async def acompanhar_pago(nome: str, u: dict = Depends(dono_da_fabrica)):
    _projeto_fabrica(nome)
    try:
        return await run_in_threadpool(fabrica_api.liberar_pago, nome)
    except fabrica_api.SemFabrica as erro:
        raise HTTPException(503, str(erro))


@app.delete("/api/acompanhar/{nome}")
async def acompanhar_apagar(nome: str, u: dict = Depends(dono_da_fabrica)):
    """Parar e apagar: o projeto sai da fábrica e o pedido da fila (se houver) fica cancelado."""
    _projeto_fabrica(nome)
    try:
        await run_in_threadpool(fabrica_api.apagar, nome)
    except fabrica_api.SemFabrica as erro:
        raise HTTPException(503, str(erro))
    banco.executar("UPDATE producoes_fila SET estado='cancelado', atualizado=? WHERE projeto=? AND usuario_id=?",
                   banco.agora(), nome, u["id"])
    return {"ok": True}


# ---------------------------------------------------------------- Custos, 2026-10-18

@app.get("/api/custos")
async def custos_pagina(dias: int = 30, canal: str = "", provedor: str = "", u: dict = Depends(usuario)):
    """O resumo do período (os filtros de canal e provedor valem só na lista de vídeos)."""
    try:
        prod = await run_in_threadpool(fabrica_api.producoes)
    except fabrica_api.SemFabrica as erro:
        raise HTTPException(503, str(erro))
    trocados = {l["projeto"]: l["canal"] for l in banco.todos("SELECT projeto, canal FROM resultado_canal WHERE usuario_id=?", u["id"])}
    rodando = {p["nome"] for p in prod["andamento"] if p.get("rodando")}
    projetos = prod["prontos"] + prod["andamento"]

    def gasto(nome):
        # o total da fábrica (o mesmo dos Resultados), com o provedor de cada parte (custos.combinar)
        try:
            fabrica = fabrica_api.custo(nome)
        except fabrica_api.SemFabrica:
            fabrica = None
        return custos.combinar(fabrica, custos.linhas(_projeto_fabrica(nome)))
    with ThreadPoolExecutor(max_workers=8) as grupo:
        gastos = await run_in_threadpool(lambda: list(grupo.map(gasto, [p["nome"] for p in projetos])))
    videos = [{"nome": p["nome"], "titulo": p["titulo"], "canal": trocados.get(p["nome"]) or p.get("canal") or "",
               "criado": p.get("criado") or "", "minutos": round((p.get("duracao") or 0) / 60, 1), "linhas": g}
              for p, g in zip(projetos, gastos)]
    r = custos.resumo([v for v in videos if v["linhas"]], dias or None)
    provedores = {v["nome"]: {l["provedor"] for l in v["linhas"]} for v in videos}
    r["lista"] = [v | {"produzindo": v["nome"] in rodando} for v in r["lista"]
                  if (not canal or v["canal"] == canal) and (not provedor or provedor in provedores.get(v["nome"], set()))]
    r["canais"] = sorted({v["canal"] for v in videos if v["canal"]})
    r["provedores"] = sorted({l["provedor"] for v in videos for l in v["linhas"]})
    return r


@app.get("/api/custos/{nome}")
def custos_video(nome: str, u: dict = Depends(usuario)):
    pasta = _projeto_fabrica(nome)
    try:
        fabrica = fabrica_api.custo(nome)
    except fabrica_api.SemFabrica:
        fabrica = None
    return custos.detalhe(pasta, fabrica)


# ---------------------------------------------------------------- Integrações (as chaves de API), 2026-10-18

def _chaves_aqui(request: Request, u: dict = Depends(dono_da_fabrica)) -> dict:
    """As chaves só se veem e se trocam neste computador, pela administração."""
    if _de_fora(request):
        raise HTTPException(403, "As chaves de API só aparecem no computador da fábrica.")
    return u


def _integracao(funcao, *args):
    try:
        return funcao(*args)
    except ValueError as erro:
        raise HTTPException(400, str(erro))
    except fabrica_api.SemFabrica as erro:
        raise HTTPException(503, str(erro))


@app.get("/api/integracoes")
async def integracoes_estado(u: dict = Depends(_chaves_aqui)):
    return await run_in_threadpool(integracoes.estado)


@app.post("/api/integracoes/{servico}/testar")
async def integracoes_testar(servico: str, corpo: dict, u: dict = Depends(_chaves_aqui)):
    return await run_in_threadpool(_integracao, integracoes.testar, servico, int(corpo.get("indice") or 0))


@app.post("/api/integracoes/{servico}/saldo")
async def integracoes_saldo(servico: str, corpo: dict, u: dict = Depends(_chaves_aqui)):
    try:
        valor = float(str(corpo.get("valor", "")).replace(",", "."))
    except ValueError:
        raise HTTPException(400, "Escreva o saldo em número, como 25,40.")
    return await run_in_threadpool(_integracao, integracoes.informar_saldo, servico, valor)


@app.post("/api/integracoes/{servico}")
async def integracoes_gravar(servico: str, corpo: dict, u: dict = Depends(_chaves_aqui)):
    indice = corpo.get("indice")
    return await run_in_threadpool(_integracao, integracoes.gravar, servico, corpo.get("valor", ""),
                                   None if indice is None else int(indice))


@app.delete("/api/integracoes/{servico}/{indice}")
async def integracoes_remover(servico: str, indice: int, u: dict = Depends(_chaves_aqui)):
    return await run_in_threadpool(_integracao, integracoes.remover, servico, indice)


@app.get("/api/fabrica")
def fabrica_status(u: dict = Depends(usuario)):
    return {"conectada": roteiro_claude.fabrica_conectada(), "perfis": roteiro_claude.perfis_da_fabrica(),
            "pasta": str(roteiro_claude.FABRICA)}


@app.post("/api/roteiros/{nome}/texto")
async def roteiro_texto(nome: str, request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    try:
        return roteiro_claude.salvar_texto(u["id"], nome, str(d.get("roteiro", "")), str(d.get("titulo", "")))
    except RuntimeError as erro:
        raise HTTPException(404, str(erro))


@app.post("/api/roteiros/{nome}/fabrica")
async def roteiro_para_fabrica(nome: str, request: Request, u: dict = Depends(dono_da_fabrica)):
    d = await request.json()
    try:
        return roteiro_claude.enviar(u["id"], nome, str(d.get("perfil", "")))
    except RuntimeError as erro:
        raise HTTPException(400, str(erro))


@app.get("/api/titulo-do-video")
def titulo_do_video(link: str, u: dict = Depends(usuario)):
    """O título, a capa e se o vídeo tem legenda, para a pessoa ver o que colou (1 unidade de cota).

    A legenda entra aqui (pedido do usuário em 2026-10-28) para a confirmação da Nova produção poder dizer, ANTES de
    criar, que esse vídeo não tem legenda e o roteiro vai sair só do título."""
    vid = roteiro_claude.id_do_video(link)
    if not vid:
        raise HTTPException(400, "Link de vídeo inválido.")
    with youtube.gastando("canal"):
        v = youtube.videos([vid])
    if not v:
        raise HTTPException(404, "Vídeo não encontrado.")
    return {"id": vid, "titulo": v[0]["titulo"], "views": v[0]["views"], "publicado": v[0]["publicado"],
            "legenda": roteiro_claude.tem_legenda(vid)}


# ---------------------------------------------------------------- YouTube Studio

@app.get("/api/youtube/conectar")
def studio_conectar(request: Request, u: dict = Depends(usuario)):
    if not studio.configurado():
        raise HTTPException(400, "Falta o GOOGLE_CLIENT_ID e o GOOGLE_CLIENT_SECRET no .env.")
    return {"url": studio.url_login(u["id"], _endereco(request))}


@app.get("/api/youtube/retorno")
def studio_retorno(code: str = "", state: str = "", error: str = ""):
    from fastapi.responses import HTMLResponse, RedirectResponse
    if error or not code:
        return HTMLResponse(f"<p>O Google não autorizou ({error or 'sem código'}). Feche esta aba e tente de novo.</p>")
    try:
        usuario_id, voltar, canais = studio.concluir(code, state)
    except Exception as erro:
        return HTMLResponse(f"<p>{erro}</p><p>Feche esta aba e tente de novo.</p>", status_code=400)
    for c in canais:           # o canal do Studio também entra em "Meus canais"
        try:
            perfil.conectar(usuario_id, c["id"])
        except Exception:
            pass
    return RedirectResponse(f"{voltar}/#/perfil?studio=ok")


@app.get("/api/youtube/status")
def studio_status(u: dict = Depends(usuario)):
    return {"configurado": studio.configurado(), "conectados": studio.conectados(u["id"]), "retorno": studio.REDIRECT}


@app.get("/api/youtube/metricas/{canal_id}")
def studio_metricas(canal_id: str, dias: int = 28, u: dict = Depends(usuario)):
    try:
        return studio.metricas(u["id"], canal_id, max(7, min(dias, 365)))
    except PermissionError as erro:
        raise HTTPException(403, str(erro))
    except RuntimeError as erro:
        raise HTTPException(502, str(erro))


@app.delete("/api/youtube/{canal_id}")
def studio_desconectar(canal_id: str, u: dict = Depends(usuario)):
    studio.desconectar(u["id"], canal_id)
    return {"ok": True}


# ---------------------------------------------------------------- roteiro pelo Claude e projetos

@app.post("/api/roteiros")
async def roteiro_comecar(request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    titulo = re.sub(r"\s+", " ", str(d.get("titulo", ""))).strip()[:150]
    if not titulo:
        raise HTTPException(400, "Escreva o título que você escolheu.")
    perfil = ""
    if d.get("enviar_direto"):
        # mandar direto para a fábrica mexe nela: só a administração, como o "Enviar para a fábrica"
        dono_da_fabrica(u)
        perfil = str(d.get("perfil") or "")
        if not roteiro_claude.fabrica_conectada():
            raise HTTPException(400, "A fábrica não está ligada a este Radar: escolha revisar antes de enviar.")
        if perfil not in roteiro_claude.perfis_da_fabrica():
            raise HTTPException(400, "Escolha a voz (perfil da fábrica) do canal antes de mandar direto.")
    tid = roteiro_claude.comecar(u["id"], enviar_perfil=perfil, titulo=titulo, link=str(d.get("link", "")).strip(),
                                 minutos=max(1, min(60, int(d.get("minutos") or 8))), lingua=str(d.get("lingua") or "português"),
                                 projeto_id=int(d["projeto_id"]) if d.get("projeto_id") else None,
                                 projeto_descricao_id=int(d["projeto_descricao_id"]) if d.get("projeto_descricao_id") else None,
                                 observacoes=str(d.get("observacoes", "")).strip()[:1000], perfil=str(d.get("perfil") or ""),
                                 canal=_canal_do_pedido(d))
    return {"tarefa": tid}


def _canal_do_pedido(d: dict) -> dict:
    """O canal do vídeo, guardado no roteiro para identificar cada vídeo feito."""
    return {"id": str(d.get("canal_id") or "")[:40], "titulo": str(d.get("canal_titulo") or "").strip()[:80]}


@app.post("/api/roteiros/manual")
async def roteiro_manual(request: Request, u: dict = Depends(usuario)):
    """O roteiro escrito pela pessoa: só o título e o texto (o link é opcional)."""
    d = await request.json()
    titulo = re.sub(r"\s+", " ", str(d.get("titulo", ""))).strip()[:150]
    if not titulo:
        raise HTTPException(400, "Escreva o título do vídeo.")
    try:
        return roteiro_claude.manual(u["id"], titulo, str(d.get("roteiro", ""))[:200000], str(d.get("link", "")).strip(),
                                     max(0, min(120, int(d.get("minutos") or 0))), str(d.get("lingua") or ""), _canal_do_pedido(d))
    except RuntimeError as erro:
        raise HTTPException(400, str(erro))


@app.get("/api/roteiros/ritmo")
def roteiro_ritmo(perfil: str = "", lingua: str = "", u: dict = Depends(usuario)):
    """Quantas palavras por minuto a voz fala de verdade, medido nos vídeos entregues (o ajuste do tempo)."""
    return tempo.ritmo(u["id"], perfil, lingua)


@app.get("/api/roteiros/tarefa/{tid}")
def roteiro_tarefa(tid: str, u: dict = Depends(usuario)):
    t = roteiro_claude.tarefa(u["id"], tid)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    return {k: t[k] for k in ("estado", "passo", "resultado", "erro", "titulo", "direto", "fabrica", "erro_envio")}


@app.get("/api/roteiros/tarefas")
def roteiro_tarefas(u: dict = Depends(usuario)):
    """Os roteiros sendo escritos (para o aviso no computador e o Acompanhar)."""
    return {"tarefas": roteiro_claude.tarefas(u["id"])}


@app.get("/api/roteiros")
def roteiros(u: dict = Depends(usuario)):
    return {"roteiros": roteiro_claude.lista(u["id"])}


@app.get("/api/roteiros/{nome}/thumbnail.jpg")
def roteiro_thumbnail(nome: str, baixar: int = 0, u: dict = Depends(usuario)):
    arquivo = roteiro_claude.PASTA / nome / "thumbnail.jpg"
    if not re.fullmatch(r"[\w.-]+", nome) or not arquivo.exists():
        raise HTTPException(404)
    return FileResponse(arquivo, media_type="image/jpeg", filename=f"{nome}.jpg" if baixar else None)


@app.post("/api/roteiros/{nome}/descricao")
async def roteiro_descricao(nome: str, request: Request, u: dict = Depends(usuario)):
    """A descrição do vídeo: refazer com o Claude ou guardar a correção da pessoa.

    Ela já foi escrita junto com o roteiro; isto é para quando o Claude falhou, para trocar o agente de descrição
    ou para a pessoa mexer no texto antes de mandar para a fábrica."""
    d = await request.json()
    pasta, _meta = roteiro_claude._do_usuario(u["id"], nome)
    try:
        if d.get("refazer"):
            return {"descricao": descricao.gerar(u["id"], pasta,
                                                 int(d["projeto_id"]) if d.get("projeto_id") else None)}
        return {"descricao": descricao.salvar(pasta, str(d.get("sinopse") or ""),
                                              d.get("tags") if isinstance(d.get("tags"), list) else None,
                                              d.get("hashtags") if isinstance(d.get("hashtags"), list) else None)}
    except RuntimeError as erro:
        raise HTTPException(400, str(erro))


@app.get("/api/projetos")
def projetos(u: dict = Depends(usuario)):
    return {"projetos": banco.todos("""SELECT id, nome, instrucoes, ideal_para, tipo FROM projetos_roteiro
                                       WHERE usuario_id=? ORDER BY tipo, nome""", u["id"])}


@app.post("/api/projetos")
async def salvar_projeto(request: Request, u: dict = Depends(usuario)):
    d = await request.json()
    nome = str(d.get("nome", "")).strip()[:60]
    if not nome:
        raise HTTPException(400, "Dê um nome ao projeto.")
    # instruções de projeto do claude.ai passam fácil de 8 mil letras: o projeto AUSTRALIA AGENTE foi cortado
    instrucoes = str(d.get("instrucoes", "")).strip()[:100000]
    # "Ideal para…" aparece embaixo do estilo na Nova produção; sem o campo no pedido, fica o que já estava
    ideal = str(d["ideal_para"]).strip()[:300] if "ideal_para" in d else None
    # "roteiro" escreve o roteiro; "descricao" escreve a sinopse, as tags e as hashtags junto com ele
    tipo = str(d.get("tipo") or "roteiro")
    if tipo not in ("roteiro", "descricao"):
        raise HTTPException(400, "O agente é de roteiro ou de descrição.")
    if d.get("id"):
        banco.executar("""UPDATE projetos_roteiro SET nome=?, instrucoes=?, ideal_para=COALESCE(?, ideal_para), tipo=?
                           WHERE id=? AND usuario_id=?""", nome, instrucoes, ideal, tipo, int(d["id"]), u["id"])
        return {"id": int(d["id"])}
    return {"id": banco.executar("""INSERT INTO projetos_roteiro (usuario_id, nome, instrucoes, ideal_para, tipo, criado)
                                    VALUES (?,?,?,?,?,?)""", u["id"], nome, instrucoes, ideal or "", tipo, banco.agora())}


@app.delete("/api/projetos/{pid}")
def apagar_projeto(pid: int, u: dict = Depends(usuario)):
    banco.executar("DELETE FROM projetos_roteiro WHERE id=? AND usuario_id=?", pid, u["id"])
    return {"ok": True}


# ---------------------------------------------------------------- medir qualquer canal

def _ref_do_canal(texto: str) -> str | None:
    """Aceita @nome, UC..., o link do canal ou o link de um vídeo dele."""
    texto = texto.strip()
    m = re.search(r"(?:youtube\.com/)?(@[\w.\-]+)", texto)
    if m:
        return m.group(1)
    m = re.search(r"(UC[\w-]{22})", texto)
    if m:
        return m.group(1)
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([\w-]{11})", texto)
    if m:
        with youtube.gastando("medir"):
            v = youtube.videos([m.group(1)])
        return v[0]["canal_id"] if v else None
    return None


@app.post("/api/medir")
async def medir_canal(request: Request, u: dict = Depends(exigir("extensao"))):
    texto = str((await request.json()).get("ref", ""))
    try:
        ref = _ref_do_canal(texto)
        if ref and ref.startswith("@"):
            with youtube.gastando("medir"):
                achado = youtube.canal_por_handle(ref)
            ref = achado["id"] if achado else None
        if not ref:
            raise HTTPException(404, "Não achei esse canal. Cole o @ do canal, o link dele ou o link de um vídeo.")
        medir.medir_canais([ref])
    except youtube.SemCota as erro:
        _sem_cota(erro)
    c = banco.um("SELECT * FROM canais WHERE id=?", ref)
    return {"canal": _vitrine(c, u["id"])}


@app.post("/api/radar/adicionar/{canal_id}")
def adicionar_ao_radar(canal_id: str, u: dict = Depends(exigir("extensao"))):
    c = banco.um("SELECT * FROM canais WHERE id=?", canal_id)
    if not c:
        raise HTTPException(404, "Meça o canal primeiro.")
    if not c["descoberto"]:
        banco.executar("UPDATE canais SET descoberto=? WHERE id=?", banco.agora(), canal_id)
    garimpo._completar(c)
    return {"canal": _vitrine(banco.um("SELECT * FROM canais WHERE id=?", canal_id), u["id"])}


# ---------------------------------------------------------------- produzir: títulos e pauta para a fábrica

def _exemplos(nicho: str = "", subnicho: str = "", limite: int = 25) -> list[str]:
    """Os títulos que de fato estouraram, pela nota de agora: exemplo com nota velha ensinaria o estilo errado."""
    onde, args = [f"{_NOTA_VIVA} >= 3", f"{_NORMAL} >= {NORMAL_MINIMO}", "c.no_radar=1"], []
    if not nicho and not subnicho:
        onde.append(f"c.nicho NOT IN ({','.join('?' * len(mercado.IRRELEVANTES))})")
        args += sorted(mercado.IRRELEVANTES)
    if subnicho:
        onde.append("c.subnicho=?"); args.append(subnicho)
    elif nicho:
        onde.append("c.nicho=?"); args.append(nicho)
    return [l["titulo"] for l in banco.todos(
        "SELECT v.titulo FROM outliers o JOIN videos v ON v.id=o.video_id JOIN canais c ON c.id=o.canal_id "
        f"WHERE {' AND '.join(onde)} ORDER BY {_NOTA_VIVA} DESC LIMIT ?", *args, limite)]


@app.get("/api/titulos")
def titulos(request: Request, u: dict = Depends(exigir("outliers"))):
    """O banco de títulos que estouraram: os vídeos dos canais do Radar com 3 vezes ou mais o normal."""
    q = dict(request.query_params)
    # a nota é refeita aqui, como na lista de vídeos: a gravada na tabela envelhece quando o normal do canal é
    # corrigido, e punha no topo do banco um "846.313x" de canal que ainda não tinha base nenhuma
    # c.no_radar=1 como em toda lista: sem isso o banco lia canal medido de passagem e nunca classificado (sem
    # nicho, portanto sem o corte dos nichos que pagam pouco), e o topo virava clipe de pagode
    onde = [f"{_NOTA_VIVA} >= ?", f"{_NORMAL} >= {NORMAL_MINIMO}", "c.no_radar=1"]
    args = [_numero(q, "nota_min") or 3]
    for campo in ("nicho", "subnicho"):
        if q.get(campo):
            onde.append(f"c.{campo}=?"); args.append(q[campo])
    if q.get("busca"):
        onde.append("v.titulo LIKE ?"); args.append(f"%{q['busca']}%")
    # "recomendados": só os nichos em que a pessoa de fato publica (os canais dela), que é a única recomendação
    # que o Radar pode fazer sem inventar — título que estourou no nicho dela, não no nicho de ninguém
    if q.get("meus") == "1":
        onde.append("c.nicho IN (SELECT nicho FROM canais WHERE nicho<>'' AND id IN "
                    "(SELECT canal_id FROM meus_canais WHERE usuario_id=?))")
        args.append(u["id"])
    dias = _numero(q, "publicado_dias")
    if dias is not None:
        onde.append("v.publicado >= ?"); args.append(_corte(dias))
    # a mesma regra das outras listas: nicho que paga pouco (Música, Games, Infantil...) não serve de exemplo de
    # título para canal sem rosto, e sem isto o topo do banco era clipe e desenho
    if not q.get("nicho"):
        onde.append(f"c.nicho NOT IN ({','.join('?' * len(mercado.IRRELEVANTES))})")
        args += sorted(mercado.IRRELEVANTES)
    return {"titulos": banco.todos(
        f"SELECT v.id, v.titulo, v.views, v.publicado, ROUND({_NOTA_VIVA}, 1) AS nota, "
        "c.titulo AS canal, c.nicho, c.subnicho "
        "FROM outliers o JOIN videos v ON v.id=o.video_id JOIN canais c ON c.id=o.canal_id "
        f"WHERE {' AND '.join(onde)} ORDER BY {_NOTA_VIVA} DESC LIMIT 300", *args)}


@app.post("/api/titulos/gerar")
async def gerar_titulos(request: Request, u: dict = Depends(exigir("outliers"))):
    d = await request.json()
    tema = str(d.get("tema", "")).strip()[:300]
    if not tema:
        raise HTTPException(400, "Escreva o tema do vídeo.")
    exemplos = _exemplos(d.get("nicho", ""), d.get("subnicho", ""))
    lista = ia.gerar_titulos(tema, exemplos, str(d.get("lingua") or "português"), int(d.get("quantos") or 10))
    if not lista:
        raise HTTPException(503, "O Groq não respondeu agora. Tente de novo em um minuto.")
    return {"titulos": lista, "exemplos": len(exemplos)}


PAUTAS = RAIZ / "dados" / "pautas"


def _slug(texto: str) -> str:
    import unicodedata
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")[:50] or "pauta"


@app.post("/api/pauta")
async def pauta(request: Request, u: dict = Depends(exigir("outliers"))):
    """Rascunho de roteiro (Groq, grátis), salvo num .txt, com o comando para virar projeto na fábrica."""
    d = await request.json()
    tema = str(d.get("tema", "")).strip()[:300]
    titulo = str(d.get("titulo", "")).strip()[:150]
    nicho, subnicho = d.get("nicho", ""), d.get("subnicho", "")
    if d.get("video_id"):
        v = banco.um("SELECT v.titulo, c.nicho, c.subnicho FROM videos v JOIN canais c ON c.id=v.canal_id WHERE v.id=?",
                     d["video_id"])
        if v:
            titulo, nicho, subnicho = titulo or v["titulo"], nicho or v["nicho"], subnicho or v["subnicho"]
            tema = tema or v["titulo"]
    if not tema:
        raise HTTPException(400, "Escreva o tema do vídeo.")
    minutos = max(2, min(20, int(d.get("minutos") or 8)))
    feito = ia.escrever_pauta(tema, titulo or tema, _exemplos(nicho, subnicho, 12), minutos,
                              str(d.get("lingua") or "português"))
    if not feito:
        raise HTTPException(503, "O Groq não respondeu agora. Tente de novo em um minuto.")
    PAUTAS.mkdir(parents=True, exist_ok=True)
    nome = f"{datetime.now(banco.BRASILIA).strftime('%Y-%m-%d')}-{_slug(feito['titulo'])}"
    arquivo = PAUTAS / f"{nome}.txt"
    arquivo.write_text(feito["roteiro"], encoding="utf-8")
    (PAUTAS / f"{nome}.json").write_text(json.dumps({"titulo": feito["titulo"], "tema": tema, "nicho": nicho,
                                                     "subnicho": subnicho, "minutos": minutos, "criado": banco.agora()},
                                                    ensure_ascii=False), encoding="utf-8")
    return {"titulo": feito["titulo"], "roteiro": feito["roteiro"], "arquivo": str(arquivo),
            "palavras": len(feito["roteiro"].split()), "comando": _comando(nome, arquivo)}


def _comando(nome: str, arquivo) -> str:
    return f'uv run fabrica novo {nome} --roteiro "{arquivo}" --perfil perfis/documentario.yaml'


@app.get("/api/pautas")
def pautas(u: dict = Depends(exigir("outliers"))):
    saida = []
    for meta in sorted(PAUTAS.glob("*.json"), reverse=True)[:100] if PAUTAS.exists() else []:
        try:
            d = json.loads(meta.read_text(encoding="utf-8"))
        except ValueError:
            continue
        txt = meta.with_suffix(".txt")
        if txt.exists():
            roteiro = txt.read_text(encoding="utf-8")
            saida.append(d | {"nome": meta.stem, "arquivo": str(txt), "roteiro": roteiro,
                              "palavras": len(roteiro.split()), "comando": _comando(meta.stem, txt)})
    return {"pautas": saida}


# ---------------------------------------------------------------- administração

@app.get("/api/admin/usuarios")
def admin_usuarios(u: dict = Depends(admin)):
    return {"usuarios": banco.todos("SELECT id, email, nome, admin, plano, vence, criado FROM usuarios ORDER BY id")}


@app.post("/api/admin/usuarios/{uid}")
async def admin_mudar(uid: int, request: Request, u: dict = Depends(admin)):
    d = await request.json()
    if "plano" in d and d["plano"] in PLANOS:
        banco.executar("UPDATE usuarios SET plano=? WHERE id=?", d["plano"], uid)
    if "vence" in d and (d["vence"] == "" or re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d["vence"]))):
        banco.executar("UPDATE usuarios SET vence=? WHERE id=?", d["vence"], uid)
    return {"ok": True}


@app.delete("/api/admin/usuarios/{uid}")
def admin_tirar(uid: int, u: dict = Depends(admin)):
    if uid == u["id"]:
        raise HTTPException(400, "Você não pode tirar a sua própria conta.")
    for tabela in ("sessoes", "salvos", "achados"):
        banco.executar(f"DELETE FROM {tabela} WHERE usuario_id=?", uid)
    banco.executar("DELETE FROM usuarios WHERE id=?", uid)
    return {"ok": True}


def _endereco(request: Request) -> str:
    """O endereço do site como quem pediu vê (no próprio computador, http://127.0.0.1:8400)."""
    return f"{'https' if _https(request) else request.url.scheme}://{request.headers.get('host', request.url.netloc)}"


@app.post("/api/admin/convites")
async def novo_convite(request: Request, u: dict = Depends(admin)):
    """Um link de convite que cria uma conta só. O código não fica guardado: só o resumo dele."""
    d = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    codigo = banco.novo_token()
    banco.executar("INSERT INTO convites (codigo_hash, nota, criado) VALUES (?,?,?)",
                   banco.hash_token(codigo), str(d.get("nota", "")).strip()[:80], banco.agora())
    return {"link": f"{_endereco(request)}/#/criar?convite={codigo}"}


@app.get("/api/admin/convites")
def convites(u: dict = Depends(admin)):
    return {"convites": banco.todos(
        "SELECT c.codigo_hash AS id, c.nota, c.criado, c.usado_em, u.email AS usado_por FROM convites c "
        "LEFT JOIN usuarios u ON u.id=c.usado_por ORDER BY c.criado DESC LIMIT 100")}


@app.delete("/api/admin/convites/{cid}")
def tirar_convite(cid: str, u: dict = Depends(admin)):
    banco.executar("DELETE FROM convites WHERE codigo_hash=? AND usado_por IS NULL", cid)
    return {"ok": True}


@app.get("/api/extensao.zip")
def extensao_zip(request: Request, u: dict = Depends(usuario)):
    """A pasta da extensão num zip, já apontando para o endereço deste site."""
    import io
    import zipfile
    pasta = RAIZ / "extensao"
    endereco = _endereco(request)
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        for arquivo in pasta.rglob("*"):
            if arquivo.is_file():
                caminho = "radar-extensao/" + arquivo.relative_to(pasta).as_posix()
                if arquivo.name in ("background.js", "popup.js"):
                    texto = arquivo.read_text(encoding="utf-8").replace('"http://127.0.0.1:8400"', json.dumps(endereco))
                    z.writestr(caminho, texto)
                else:
                    z.write(arquivo, caminho)
    from fastapi.responses import Response
    return Response(memoria.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="radar-extensao.zip"'})


@app.get("/api/cota")
def cota(u: dict = Depends(usuario)):
    """A cota do YouTube de hoje (painel do Descobrir e o quadro do menu) e se o garimpo está rodando."""
    return garimpo.estado_gasto()


@app.post("/api/cota/gastar")
def cota_gastar(u: dict = Depends(admin)):
    """O botão "Gastar tudo agora": o garimpo com toda a cota livre de hoje, em segundo plano."""
    if garimpo.estado_gasto()["garimpando"]:
        return {"ok": False, "motivo": "O garimpo já está rodando."}
    threading.Thread(target=garimpo.gastar_tudo, daemon=True).start()
    return {"ok": True}


@app.get("/api/admin/cota")
def admin_cota(u: dict = Depends(admin)):
    return {"cota": youtube.cota_hoje(),
            "motivos": [{**m, "rotulo": youtube.MOTIVOS.get(m["motivo"], m["motivo"])}
                        for m in youtube.gasto_por_motivo()],
            "garimpos": banco.todos("SELECT id, inicio, fim, unidades, buscas, canais_novos, estado FROM garimpos "
                                    "ORDER BY id DESC LIMIT 15")}


@app.get("/api/admin/garimpos/{gid}")
def admin_garimpo(gid: int, u: dict = Depends(admin)):
    g = banco.um("SELECT * FROM garimpos WHERE id=?", gid)
    if not g:
        raise HTTPException(404)
    return {**g, "linhas": json.loads(g["linhas"])}


@app.post("/api/admin/garimpar")
async def admin_garimpar(request: Request, u: dict = Depends(admin)):
    d = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    unidades = d.get("unidades")
    threading.Thread(target=garimpo.rodar, kwargs={"unidades": int(unidades) if unidades else None},
                     daemon=True).start()
    return {"ok": True}


# ---------------------------------------------------------------- garimpo de todo dia

def _relogio():
    """Uma vez por hora confere se o último garimpo tem mais de 23 horas, e roda se tiver."""
    time.sleep(30)
    while True:
        try:
            ultimo = banco.um("SELECT inicio FROM garimpos ORDER BY id DESC LIMIT 1")
            if os.environ.get("RADAR_GARIMPO_AUTOMATICO", "1") == "1" and (
                    not ultimo or metricas.dias_desde(ultimo["inicio"]) > 23 / 24):
                garimpo.rodar()
        except Exception as erro:
            print("garimpo automático falhou:", erro)
        time.sleep(3600)


def _acordado():
    """O Windows não pode dormir com o Radar ligado, senão o garimpo para (a tela pode apagar). O aviso vale para a
    linha que chamou, então esta linha fica viva enquanto o servidor roda."""
    import sys
    if sys.platform != "win32" or os.environ.get("RADAR_ACORDADO", "1") != "1":
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # CONTINUOUS | SYSTEM_REQUIRED
    while True:
        time.sleep(3600)


@app.on_event("startup")
def _ligar():
    banco.con()
    threading.Thread(target=_relogio, daemon=True).start()
    threading.Thread(target=_acordado, daemon=True, name="acordado").start()
    fila.iniciar_vigia()


# ---------------------------------------------------------------- site

app.mount("/web", StaticFiles(directory=WEB), name="web")


@app.get("/")
def inicio():
    """O index com a versão dos arquivos do painel colada na hora.

    O `?v=` do `app.js` e do `estilo.css` existe para o navegador buscar o arquivo novo em vez do guardado.
    Escrito à mão, ele fica para trás: mexer no painel e esquecer de subir o número faz a pessoa continuar
    vendo a tela velha, sem erro nenhum na cara — e o `/web` não manda `Cache-Control`, então o navegador
    decide sozinho e nem pergunta. Aqui o número é o minuto em que o arquivo mudou, então ele nunca atrasa.
    """
    pagina = (WEB / "index.html").read_text(encoding="utf-8")
    versao = int(max((WEB / n).stat().st_mtime for n in ("app.js", "estilo.css")))
    pagina = re.sub(r"(/web/(?:app\.js|estilo\.css)\?v=)[^\"']*", rf"\g<1>{versao}", pagina)
    return HTMLResponse(pagina, headers={"Cache-Control": "no-store"})
