"""O servidor do Radar: contas, a API da extensão, o painel dos canais e a administração.

Rodar: python -m radar servidor (porta 8400) ou LIGAR-RADAR.bat."""
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
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import alertas, alvos, banco, canal_painel, custos, diagnostico, fabrica_api, fila, garimpo, gosto, ia, integracoes, medir, mercado, metricas, pagina, perfil, producao, publicar, radar_paises, roteiro_claude, studio, tempo, thumb, trabalho, treinamento, youtube
from .config import NOME, PLANOS, RAIZ, pode

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
def planos():
    return {"nome": NOME, "planos": PLANOS}


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


@app.get("/api/ext/em-alta")
def ext_em_alta(u: dict = Depends(exigir("extensao"))):
    return {"canais": pagina.em_alta()}


@app.get("/api/ext/hoje")
def ext_hoje(u: dict = Depends(exigir("extensao"))):
    return pagina.hoje()


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


@app.get("/api/ext/publicar")
def ext_publicar(arquivo: str = "", u: dict = Depends(exigir("extensao"))):
    """O painel de ajuda do upload no YouTube Studio: o kit do vídeo achado pelo nome do arquivo e, se não achar, a
    lista para escolher. Lê o publicacao.json da pasta do projeto (não precisa da fábrica ligada)."""
    raiz = roteiro_claude.FABRICA / "projetos"
    nome = publicar.achar(raiz, arquivo[:300])
    return {"kit": publicar.kit(raiz / nome) if nome else None, "opcoes": publicar.opcoes(raiz)}


@app.get("/api/ext/publicar/{nome}")
def ext_publicar_projeto(nome: str, u: dict = Depends(exigir("extensao"))):
    pasta = _projeto_fabrica(nome)
    if not (pasta / "publicacao.json").exists():
        raise HTTPException(404, "A fábrica ainda não montou o título, a descrição e as tags deste vídeo.")
    return publicar.kit(pasta)


@app.get("/api/ext/publicar/{nome}/legenda")
def ext_publicar_legenda(nome: str, u: dict = Depends(exigir("extensao"))):
    pasta = _projeto_fabrica(nome)
    arquivo = next((pasta / f for f in ("legendas_final.srt", "legendas.srt") if (pasta / f).exists()), None)
    if not arquivo:
        raise HTTPException(404, "Este vídeo não tem legenda.")
    return FileResponse(arquivo, media_type="application/x-subrip", filename=f"{nome}.srt")


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

ORDENS = {
    "media": "c.base_longos DESC",                 # mais views por vídeo
    "alta": "c.velocidade DESC",                   # em alta: views por dia dos vídeos do último mês
    "ganho": "c.ganho_7d DESC",                    # mais inscritos ganhos na semana
    "novos": "c.descoberto DESC",                  # achados mais recentes
    "jovens": "c.primeiro_video DESC",             # começaram a postar há menos tempo
    "inscritos": "c.inscritos DESC",
    "pequenos": "c.inscritos ASC",
    "estourando": "(c.base_longos * 1.0 / MAX(c.inscritos, 100)) DESC",   # muita view para o tamanho
    "recente": "c.ultimo_video DESC",              # postaram por último
    "aleatorio": "RANDOM()",                       # o botão Aleatório de todas as telas
}


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
    for nome, coluna, operador, sufixo in (("inicio_de", "c.primeiro_video", ">=", ""),
                                           ("inicio_ate", "c.primeiro_video", "<=", "T23:59:59"),
                                           ("achado_de", "c.descoberto", ">=", ""),
                                           ("achado_ate", "c.descoberto", "<=", "T23:59:59")):
        data = _data(q, nome)
        if data:
            onde.append(f"{coluna} {operador} ?"); args.append(data + sufixo)
    return onde, args


def _vitrine(c: dict, usuario_id: int | None = None, com_videos: bool = True) -> dict:
    """O canal com as capas dos 3 vídeos longos que mais renderam, para o cartão do painel."""
    publico = medir._canal_publico(c) | {"descoberto": c.get("descoberto", "")}
    if com_videos:
        videos = banco.todos("SELECT id, titulo, views, publicado, duracao_s FROM videos WHERE canal_id=? AND duracao_s>? "
                             "ORDER BY views DESC LIMIT 3", c["id"], metricas.CURTO_ATE_S)
        publico["videos"] = [v | {"nota": metricas.nota_outlier(v["views"], c["base_longos"])} for v in videos]
    if usuario_id is not None:
        publico["salvo"] = bool(banco.um("SELECT 1 AS x FROM salvos WHERE usuario_id=? AND canal_id=?",
                                         usuario_id, c["id"]))
    return publico


def _lista_de_canais(onde: str, args: list, ordem: str, limite: int, pagina: int = 0,
                     usuario_id: int | None = None) -> list[dict]:
    linhas = banco.todos(f"SELECT c.* FROM canais c WHERE {onde} ORDER BY {ordem}, c.base_longos DESC "
                         f"LIMIT ? OFFSET ?", *args, limite, pagina * limite)
    return [_vitrine(c, usuario_id) for c in linhas]


@app.get("/api/resumo")
def resumo():
    return {"nome": NOME, **_numeros()}


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
    q = dict(request.query_params)
    onde, args = _filtro_canais(q)
    pagina = int(_numero(q, "pagina") or 0)
    total = banco.um(f"SELECT COUNT(*) AS n FROM canais c WHERE {' AND '.join(onde)}", *args)["n"]
    return {"total": total, "canais": _lista_de_canais(" AND ".join(onde), args, ORDENS.get(q.get("ordem"), ORDENS["media"]),
                                                        30, pagina, u["id"])}


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
def nichos(u: dict = Depends(exigir("radar"))):
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


ORDENS_OUTLIERS = {"aleatorio": "RANDOM()", "nota": "o.nota DESC", "recentes": "v.publicado DESC", "views": "v.views DESC",
                   "achados": "o.achado DESC", "pequenos": "c.inscritos ASC"}


@app.get("/api/outliers")
def outliers(request: Request, u: dict = Depends(exigir("outliers"))):
    q = dict(request.query_params)
    onde, args = ["o.nota >= ?"], [_numero(q, "nota_min") or 5]
    for campo in ("nicho", "subnicho"):
        if q.get(campo):
            onde.append(f"c.{campo}=?"); args.append(q[campo])
    if q.get("busca"):
        onde.append("(v.titulo LIKE ? OR c.titulo LIKE ?)"); args += [f"%{q['busca']}%"] * 2
    if q.get("tipo") == "longo":
        onde.append("v.duracao_s > ?"); args.append(metricas.CURTO_ATE_S)
    elif q.get("tipo") == "curto":
        onde.append("v.duracao_s <= ?"); args.append(metricas.CURTO_ATE_S)
    if q.get("rosto") == "sem":
        onde.append("c.sem_rosto=1")
    if q.get("meus") == "1":
        onde.append("c.id IN (SELECT canal_id FROM salvos WHERE usuario_id=?)"); args.append(u["id"])
    for nome, coluna, operador in (("views_min", "v.views", ">="), ("inscritos_max", "c.inscritos", "<=")):
        valor = _numero(q, nome)
        if valor is not None:
            onde.append(f"{coluna} {operador} ?"); args.append(valor)
    dias = _numero(q, "publicado_dias")
    if dias is not None:
        onde.append("v.publicado >= ?"); args.append(_corte(dias))
    for nome, operador, sufixo in (("publicado_de", ">=", ""), ("publicado_ate", "<=", "T23:59:59")):
        data = _data(q, nome)
        if data:
            onde.append(f"v.publicado {operador} ?"); args.append(data + sufixo)
    base = (f"FROM outliers o JOIN videos v ON v.id=o.video_id JOIN canais c ON c.id=o.canal_id "
            f"WHERE {' AND '.join(onde)}")
    pagina = int(_numero(q, "pagina") or 0)
    linhas = banco.todos(
        "SELECT o.nota, v.id, v.titulo, v.views, v.publicado, v.duracao_s, c.id AS canal_id, c.titulo AS canal, "
        f"c.foto, c.handle, c.inscritos, c.nicho, c.subnicho, c.sem_rosto, c.base_longos AS normal {base} "
        f"ORDER BY {ORDENS_OUTLIERS.get(q.get('ordem'), ORDENS_OUTLIERS['nota'])}", *args)
    # os bloqueios e as respostas da primeira vez (língua, rosto, o que nunca mostrar) valem aqui também
    filtro = gosto.Filtro(u)
    # o formato é o da tela: "Longos e Shorts" (vazio) mostra os dois, mesmo que a pergunta da primeira vez diga "só longos"
    filtro.sem_shorts = q.get("tipo") == "longo"
    filtro.p = filtro.p | {"formato": "curto" if q.get("tipo") == "curto" else "todos"}
    filtro.linguas = {"outras"}
    linhas = gosto.por_lingua([l for l in linhas if filtro.aceita(l)], q.get("lingua", ""))
    por = min(60, max(1, int(_numero(q, "por") or 60)))   # Vídeos que estouraram pede de 10 em 10
    return {"total": len(linhas), "videos": linhas[pagina * por:(pagina + 1) * por]}


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
            "historico": perfil.historico(canal_id), "ideias": gosto.ideias_para(u, c),
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


@app.get("/api/alertas")
def ver_alertas(request: Request, u: dict = Depends(usuario)):
    lista = alertas.canais(u["id"], dict(request.query_params))
    saida = [_vitrine(c, u["id"]) | {"pico": c["pico"], "novo": c["visto"] is None} for c in lista[:60]]
    return {"canais": saida, "padrao": alertas.PADRAO}


@app.get("/api/alertas/novos")
def alertas_novos(u: dict = Depends(usuario)):
    return {"novos": alertas.novos(u["id"])}


@app.post("/api/alertas/vistos")
async def alertas_vistos(request: Request, u: dict = Depends(usuario)):
    alertas.marcar_vistos(u["id"], [str(i) for i in (await request.json()).get("ids", [])][:200])
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
    return producao.config(u["id"], canal_id) | {"perfis": producao.perfis(),
                                                  "ias": {k: n for k, (n, _) in producao.IAS_IMAGEM.items()}}


@app.post("/api/producao/{canal_id}")
async def producao_salvar(canal_id: str, request: Request, u: dict = Depends(usuario)):
    _meu_canal(u["id"], canal_id)
    return producao.salvar(u["id"], canal_id, await request.json())


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
        return {"resposta": await run_in_threadpool(producao.assistente, u["id"], canal_id, mensagens, pagina)}
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
    """O título e a capa do vídeo de referência, para a pessoa ver o que colou (1 unidade de cota)."""
    vid = roteiro_claude.id_do_video(link)
    if not vid:
        raise HTTPException(400, "Link de vídeo inválido.")
    v = youtube.videos([vid])
    if not v:
        raise HTTPException(404, "Vídeo não encontrado.")
    return {"id": vid, "titulo": v[0]["titulo"], "views": v[0]["views"], "publicado": v[0]["publicado"]}


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


@app.get("/api/projetos")
def projetos(u: dict = Depends(usuario)):
    return {"projetos": banco.todos("SELECT id, nome, instrucoes, ideal_para FROM projetos_roteiro WHERE usuario_id=? ORDER BY nome", u["id"])}


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
    if d.get("id"):
        banco.executar("UPDATE projetos_roteiro SET nome=?, instrucoes=?, ideal_para=COALESCE(?, ideal_para) WHERE id=? AND usuario_id=?",
                       nome, instrucoes, ideal, int(d["id"]), u["id"])
        return {"id": int(d["id"])}
    return {"id": banco.executar("INSERT INTO projetos_roteiro (usuario_id, nome, instrucoes, ideal_para, criado) VALUES (?,?,?,?,?)",
                                 u["id"], nome, instrucoes, ideal or "", banco.agora())}


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
        v = youtube.videos([m.group(1)])
        return v[0]["canal_id"] if v else None
    return None


@app.post("/api/medir")
async def medir_canal(request: Request, u: dict = Depends(exigir("extensao"))):
    texto = str((await request.json()).get("ref", ""))
    try:
        ref = _ref_do_canal(texto)
        if ref and ref.startswith("@"):
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
    onde, args = ["o.nota >= 3"], []
    if subnicho:
        onde.append("c.subnicho=?"); args.append(subnicho)
    elif nicho:
        onde.append("c.nicho=?"); args.append(nicho)
    return [l["titulo"] for l in banco.todos(
        "SELECT v.titulo FROM outliers o JOIN videos v ON v.id=o.video_id JOIN canais c ON c.id=o.canal_id "
        f"WHERE {' AND '.join(onde)} ORDER BY o.nota DESC LIMIT ?", *args, limite)]


@app.get("/api/titulos")
def titulos(request: Request, u: dict = Depends(exigir("outliers"))):
    """O banco de títulos que estouraram: os vídeos dos canais do Radar com 3 vezes ou mais o normal."""
    q = dict(request.query_params)
    onde, args = ["o.nota >= ?"], [_numero(q, "nota_min") or 3]
    for campo in ("nicho", "subnicho"):
        if q.get(campo):
            onde.append(f"c.{campo}=?"); args.append(q[campo])
    if q.get("busca"):
        onde.append("v.titulo LIKE ?"); args.append(f"%{q['busca']}%")
    dias = _numero(q, "publicado_dias")
    if dias is not None:
        onde.append("v.publicado >= ?"); args.append(_corte(dias))
    return {"titulos": banco.todos(
        "SELECT v.id, v.titulo, v.views, v.publicado, o.nota, c.titulo AS canal, c.nicho, c.subnicho "
        "FROM outliers o JOIN videos v ON v.id=o.video_id JOIN canais c ON c.id=o.canal_id "
        f"WHERE {' AND '.join(onde)} ORDER BY o.nota DESC LIMIT 300", *args)}


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
    return FileResponse(WEB / "index.html")
