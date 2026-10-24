"""O que a extensão leu na página do YouTube (ler.js): vídeos, canais e números, sem a API e sem gastar cota.

A extensão manda o que o YouTube já mostrou na tela (vistos) e, quando um canal não está no banco, baixa a página
de vídeos dele e manda também (canal_lido). Daqui sai a nota de outlier, o Vídeos que estouraram e os canais novos
no Radar, com as mesmas regras do garimpo."""
import re
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import median

from . import banco, garimpo, gosto, medir, metricas, risco, youtube

RX_VIDEO = re.compile(r"^[\w-]{11}$")
RX_CANAL = re.compile(r"^UC[\w-]{22}$")
LER_POR_VEZ = 6            # canais novos que a extensão vai ler de cada vez (cada um é uma página baixada)
RELER_DIAS = 7             # canal lido pela página só é lido de novo depois de uma semana
INSCRITOS_SEM_IDADE = 100_000   # sem saber a idade do canal, só entra no Radar se for pequeno

HOJE = {"dia": "", "videos": 0, "estouraram": 0, "canais": 0}   # o contador do ícone da extensão

# ---------------------------------------------------------------- a reação do público, medida contra o nicho
REACAO_VIEWS_MIN = 1000    # vídeo com pouquíssima view dá taxa instável: não entra na conta do normal
REACAO_MINIMO = 30         # nicho com menos vídeos medidos que isto não tem normal de que falar
REACAO_HORAS = 6           # o normal de um nicho muda devagar: fica guardado algumas horas
_NORMAL_NICHO: dict[str, float] = {}
_NORMAL_QUANDO = 0.0


def normal_do_nicho() -> dict[str, float]:
    """A taxa de reação do vídeo típico de cada nicho (mediana), para dizer quem passou dela."""
    global _NORMAL_QUANDO
    agora = time.time()
    if _NORMAL_NICHO and agora - _NORMAL_QUANDO < REACAO_HORAS * 3600:
        return _NORMAL_NICHO
    por: dict[str, list[float]] = {}
    for l in banco.todos(
            "SELECT c.nicho, v.views, v.curtidas, v.comentarios FROM videos v JOIN canais c ON c.id=v.canal_id "
            "WHERE v.curtidas IS NOT NULL AND v.comentarios IS NOT NULL AND v.views > ? AND c.nicho <> ''",
            REACAO_VIEWS_MIN):
        taxa = metricas.engajamento(l["views"], l["curtidas"], l["comentarios"])
        if taxa is not None:
            por.setdefault(l["nicho"], []).append(taxa)
    _NORMAL_NICHO.clear()
    _NORMAL_NICHO.update({n: median(t) for n, t in por.items() if len(t) >= REACAO_MINIMO})
    _NORMAL_QUANDO = agora
    return _NORMAL_NICHO


def _contar(campo: str, n: int = 1) -> None:
    dia = banco.agora()[:10]
    if HOJE["dia"] != dia:
        HOJE.update(dia=dia, videos=0, estouraram=0, canais=0)
    HOJE[campo] += n


def _int(x) -> int | None:
    try:
        return None if x is None else max(0, int(x))
    except (TypeError, ValueError):
        return None


def _limpar_video(v: dict, canal_id: str = "") -> dict | None:
    vid, cid = str(v.get("id") or ""), str(v.get("canal_id") or canal_id or "")
    if not RX_VIDEO.match(vid):
        return None
    dias = v.get("dias")
    exato = metricas.data(str(v.get("publicado") or ""))   # o vídeo aberto traz a data exata (do player)
    if exato:
        if not exato.tzinfo:
            exato = exato.replace(tzinfo=timezone.utc)
        return {"id": vid, "canal_id": cid if RX_CANAL.match(cid) else "", "titulo": str(v.get("titulo") or "")[:300],
                "views": _int(v.get("views")), "duracao_s": _int(v.get("duracao_s")),
                "publicado": exato.astimezone(timezone.utc).isoformat(timespec="seconds"), "exato": True}
    try:
        publicado = (datetime.now(timezone.utc) - timedelta(days=float(dias))).isoformat(timespec="seconds") if dias is not None else ""
    except (TypeError, ValueError):
        publicado = ""
    return {"id": vid, "canal_id": cid if RX_CANAL.match(cid) else "", "titulo": str(v.get("titulo") or "")[:300],
            "views": _int(v.get("views")), "duracao_s": _int(v.get("duracao_s")), "publicado": publicado}


def _guardar(lista: list[dict]) -> None:
    """Vídeo novo entra; o que já existe só atualiza as views (a data e a duração exatas da API ficam)."""
    agora = banco.agora()
    banco.varios(
        "INSERT INTO videos (id, canal_id, titulo, publicado, duracao_s, views, medido) VALUES (?,?,?,?,?,?,'') "
        "ON CONFLICT(id) DO UPDATE SET views=COALESCE(excluded.views, views), "
        "titulo=CASE WHEN excluded.titulo<>'' THEN excluded.titulo ELSE titulo END, "
        "canal_id=CASE WHEN canal_id='' THEN excluded.canal_id ELSE canal_id END, "
        "duracao_s=COALESCE(duracao_s, excluded.duracao_s), "
        "publicado=CASE WHEN publicado='' THEN excluded.publicado ELSE publicado END",
        [(v["id"], v["canal_id"], v["titulo"], v["publicado"], v["duracao_s"], v["views"]) for v in lista])
    banco.varios("UPDATE videos SET publicado=? WHERE id=?", [(v["publicado"], v["id"]) for v in lista if v.get("exato")])
    banco.varios("INSERT OR IGNORE INTO leituras (video_id, quando, views) VALUES (?,?,?)",
                 [(v["id"], agora[:13], v["views"]) for v in lista if v["views"] is not None])


def _canal_basico(c: dict | None) -> None:
    """O canal que a página mostrou (cabeçalho do canal ou dono do vídeo aberto): nome, foto e inscritos."""
    if not c or not RX_CANAL.match(str(c.get("id") or "")):
        return
    dados = {"id": c["id"]}
    for campo in ("titulo", "foto", "handle"):
        if c.get(campo):
            dados[campo] = str(c[campo])[:300]
    for campo in ("inscritos", "videos_total"):
        if _int(c.get(campo)) is not None:
            dados[campo] = _int(c[campo])
    for campo in ("anuncios", "membros"):   # a monetização que a página mostrou (o player e o botão Seja membro)
        if isinstance(c.get(campo), bool):
            dados[campo] = int(c[campo])
    banco.gravar("canais", "id", dados)


def _outliers(lista: list[dict], canais: dict[str, dict]) -> int:
    """Os vídeos com 3x o normal do canal entram no Vídeos que estouraram. Devolve quantos entraram agora."""
    novos = 0
    for v in lista:
        c = canais.get(v["canal_id"])
        if not c or v["views"] is None or not v["duracao_s"]:
            continue
        normal = c["base_curtos"] if metricas.curto(v["duracao_s"]) else c["base_longos"]
        n = metricas.nota_outlier(v["views"], normal)
        v["nota"] = n
        if n and n >= medir.NOTA_OUTLIER:
            if banco.um("SELECT 1 AS x FROM outliers WHERE video_id=?", v["id"]):
                banco.executar("UPDATE outliers SET nota=? WHERE video_id=?", n, v["id"])
            else:
                banco.executar("INSERT INTO outliers (video_id, canal_id, nota, achado) VALUES (?,?,?,?)",
                               v["id"], v["canal_id"], n, banco.agora())
                novos += 1
    return novos


def vistos(videos: list, canal: dict | None = None) -> dict:
    """Os vídeos que apareceram na tela. Devolve a nota de cada um e os canais que a extensão deve ler."""
    lista = [x for x in (_limpar_video(v) for v in (videos or [])[:300] if isinstance(v, dict)) if x]
    _canal_basico(canal)
    _guardar(lista)
    ids = list(dict.fromkeys(v["canal_id"] for v in lista if v["canal_id"]))
    canais = {c["id"]: c for c in medir._canais_do_banco(ids)}
    estouraram = _outliers(lista, canais)
    _contar("videos", len(lista))
    _contar("estouraram", estouraram)
    corte = (datetime.now(timezone.utc) - timedelta(days=RELER_DIAS)).isoformat()
    ler = [i for i in ids if i not in canais or (canais[i]["base_longos"] is None and (canais[i]["medido"] or "") < corte)]
    # a reação sai das curtidas e dos comentários, que vêm da API e não da página: só tem para o que o Radar já mediu
    normais = normal_do_nicho()
    medidos = {v["id"]: v for v in medir._videos_do_banco([v["id"] for v in lista])}
    def reacao_de(v):  # noqa: E306
        guardado, canal = medidos.get(v["id"]), canais.get(v["canal_id"])
        if not guardado or not canal:
            return None
        taxa = metricas.engajamento(guardado.get("views"), guardado.get("curtidas"), guardado.get("comentarios"))
        return metricas.reacao(taxa, normais.get(canal.get("nicho") or ""))
    return {
        "videos": {v["id"]: {"nota": v.get("nota"), "canal_id": v["canal_id"],
                             "inscritos": (canais.get(v["canal_id"]) or {}).get("inscritos"),
                             "normal": (canais.get(v["canal_id"]) or {}).get("base_longos"),
                             "raridade": (canais.get(v["canal_id"]) or {}).get("raridade") or "",
                             "reacao": reacao_de(v)} for v in lista},
        "ler": ler[:LER_POR_VEZ],
        "reacao_alta": metricas.REACAO_ALTA,   # o corte de "reagiu muito" é do Radar, não da extensão
    }


def canal_lido(canal: dict, videos: list) -> dict:
    """A página de vídeos de um canal, baixada pela extensão: o normal do canal, as notas e, se passar nas regras
    do garimpo, o canal entra no Radar (o nicho e o rosto o Groq diz depois, sem cota)."""
    if not canal or not RX_CANAL.match(str(canal.get("id") or "")):
        return {"ok": False}
    cid = canal["id"]
    lista = [x for x in (_limpar_video(v, cid) for v in (videos or [])[:200] if isinstance(v, dict)) if x]
    for v in lista:
        v["canal_id"] = cid
    _guardar(lista)
    # o que vale para a conta é o que está no banco (a data exata da API, se o vídeo já tinha passado por ela)
    guardados = medir._videos_do_banco([v["id"] for v in lista])
    b = metricas.base(guardados)
    datas = sorted(v["publicado"] for v in guardados if v["publicado"])
    total = _int(canal.get("videos_total"))
    exato = bool(total is not None and len(lista) >= total)
    primeiro = datas[0] if datas else ""
    antes = banco.um("SELECT no_radar, descoberto, primeiro_video, primeiro_exato FROM canais WHERE id=?", cid)
    if not exato and antes and antes["primeiro_exato"]:   # a data exata já guardada vale mais que a da página
        primeiro, exato = antes["primeiro_video"], True
    meses = metricas.meses_postando(primeiro)
    dados = {"id": cid, "primeiro_video": primeiro, "primeiro_exato": int(exato), "ultimo_video": datas[-1] if datas else "",
             "fase": metricas.fase(guardados, primeiro), "medido": banco.agora(), **b,
             # sem saber o primeiro vídeo, o selo não é dado (um canal antigo passaria por novo)
             "raridade": metricas.raridade(b["base_longos"], meses) if exato else ""}
    if not antes:
        dados["descoberto"] = banco.agora()
    _canal_basico(canal)
    banco.gravar("canais", "id", dados)
    if _int(canal.get("inscritos")) is not None:
        banco.executar("INSERT OR IGNORE INTO historico (canal_id, dia, inscritos, views_total, videos_total) "
                       "VALUES (?,?,?,?,?)", cid, banco.agora()[:10], _int(canal["inscritos"]), None, total)
    c = medir._canais_do_banco([cid])[0]
    for v in lista:   # as notas com o normal que acabou de sair
        v["duracao_s"] = v["duracao_s"] or next((g["duracao_s"] for g in guardados if g["id"] == v["id"]), None)
    _contar("estouraram", _outliers(lista, {cid: c}))
    entrou = False
    if not (antes or {}).get("no_radar") and _passa(c, lista, exato, meses):
        entrou = True
        _contar("canais")
        threading.Thread(target=garimpo._completar, args=(c,), daemon=True).start()
    return {"ok": True, "normal": c["base_longos"], "entrou": entrou}


def _passa(c: dict, lista: list[dict], exato: bool, meses: float | None) -> bool:
    """As regras do garimpo (garimpo._avaliar), com o que a página mostra."""
    if (c["base_longos"] or 0) < garimpo.MINIMO_POR_VIDEO:
        return False
    if not 3 <= (c["videos_total"] or len(lista)) <= 400:
        return False
    if meses is None or meses > garimpo.CANAL_ATE_MESES:
        return False      # o mais antigo que a página mostrou já passa da idade: canal velho
    if not exato and (c["inscritos"] is None or c["inscritos"] > INSCRITOS_SEM_IDADE):
        return False      # mais vídeos do que a página mostrou: sem a idade certa, só canal pequeno
    titulos = [v["titulo"] for v in lista[:20]]
    linguas = Counter(l for l in (gosto.lingua(t) for t in titulos) if l != "?").most_common(1)
    if not linguas or linguas[0][0] not in ("en", "pt", "es"):
        return False
    return not risco.avaliar(titulos)


def painel(video_id: str, canal_id: str, usuario_id: int) -> dict:
    """O que o painel do vídeo aberto precisa e o banco já tem (não pede nada à API): o canal, a curva e se está salvo."""
    achados = medir._canais_do_banco([canal_id]) if RX_CANAL.match(canal_id or "") else []
    c = achados[0] if achados else None
    salvo = bool(c and banco.um("SELECT 1 AS x FROM salvos WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id))
    return {"canal": medir._canal_publico(c) if c and c.get("base_longos") is not None else None,
            "curva": medir.curva(video_id) if RX_VIDEO.match(video_id or "") else [], "salvo": salvo}


def _primeiro_exato(c: dict) -> dict:
    """O canal tem mais vídeos do que a página mostrou: o primeiro vídeo vinha da criação do canal (um canal de 2014
    que começou a postar há 10 meses parecia ter 12 anos). A lista de envios dá a data certa (1 unidade por 50
    vídeos), uma vez só: fica guardada como exata. A fase e o selo são refeitos com ela."""
    try:
        with youtube.gastando("canal"):
            primeiro = youtube.primeiro_envio(c["id"])
    except (youtube.SemCota, RuntimeError):
        return c
    if not primeiro:
        return c
    videos = banco.todos("SELECT * FROM videos WHERE canal_id=?", c["id"])
    banco.gravar("canais", "id", {"id": c["id"], "primeiro_video": primeiro, "primeiro_exato": 1,
                                  "fase": metricas.fase(videos, primeiro),
                                  "raridade": metricas.raridade(c["base_longos"], metricas.meses_postando(primeiro))})
    return medir._canais_do_banco([c["id"]])[0]


def canal_dados(canal_id: str, usuario_id: int) -> dict | None:
    """A faixa da página do canal no YouTube: os números do banco, os inscritos por dia e os últimos vídeos com a nota."""
    achados = medir._canais_do_banco([canal_id]) if RX_CANAL.match(canal_id or "") else []
    if not achados or achados[0]["base_longos"] is None:
        return None
    c = achados[0]
    if not c["primeiro_exato"] and (c["videos_total"] or 0) <= 2000:
        c = _primeiro_exato(c)
    videos = banco.todos("SELECT id, titulo, views, publicado, duracao_s FROM videos WHERE canal_id=? AND publicado<>'' "
                         "ORDER BY publicado DESC LIMIT 30", canal_id)
    for v in videos:
        normal = c["base_curtos"] if metricas.curto(v["duracao_s"]) else c["base_longos"]
        v["nota"] = metricas.nota_outlier(v["views"], normal)
    return {**medir._canal_publico(c), "anuncios": c.get("anuncios"), "membros": c.get("membros"),
            "salvo": bool(banco.um("SELECT 1 AS x FROM salvos WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id)),
            "inscritos_dias": banco.todos("SELECT dia, inscritos FROM historico WHERE canal_id=? AND inscritos IS NOT NULL "
                                          "ORDER BY dia DESC LIMIT 60", canal_id)[::-1],
            "videos": videos[::-1]}


def em_alta(dias: int = 90, quantos: int = 12) -> list[dict]:
    """Canais novos do Radar (começaram há até 90 dias) que mais fazem views por vídeo: a fileira do início do YouTube."""
    corte = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    linhas = banco.todos("SELECT * FROM canais WHERE no_radar=1 AND primeiro_video>=? AND base_longos IS NOT NULL "
                         "ORDER BY media_longos DESC LIMIT ?", corte, quantos)
    return [medir._canal_publico(c) for c in linhas]


def hoje() -> dict:
    _contar("videos", 0)
    return dict(HOJE)
