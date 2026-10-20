"""YouTube Studio: as métricas que só o dono do canal vê (YouTube Analytics API), pelo login do Google.

Pedido do usuário em 2026-10-14: no perfil, conectar ao YouTube Studio para ter todas as métricas do canal. Usa o
mesmo cliente OAuth da fábrica (GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET do .env). O endereço de volta
(REDIRECT) precisa estar cadastrado nesse cliente no Google Cloud, e a YouTube Analytics API ativada no projeto."""
import json
import secrets
import threading
import time
from datetime import date, timedelta

import httpx

from . import banco
from .config import AMBIENTE

URL_AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
URL_DADOS = "https://www.googleapis.com/youtube/v3/"
REDIRECT = AMBIENTE.get("RADAR_GOOGLE_REDIRECT", "http://localhost:8400/api/youtube/retorno")
ESCOPOS = " ".join([
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",   # receita, só em canal monetizado
])
_CLIENTE = httpx.Client(timeout=httpx.Timeout(30, connect=10))

# login próprio do Radar (RADAR_GOOGLE_CLIENT_ID e RADAR_GOOGLE_CLIENT_SECRET no finder/.env) vale por cima do da
# fábrica: o projeto do Google da fábrica pode ser de outra conta, sem acesso para cadastrar o endereço de volta
ID = AMBIENTE.get("RADAR_GOOGLE_CLIENT_ID") or AMBIENTE.get("GOOGLE_CLIENT_ID", "")
SEGREDO = AMBIENTE.get("RADAR_GOOGLE_CLIENT_SECRET") or AMBIENTE.get("GOOGLE_CLIENT_SECRET", "")

# o "state" do login liga a volta do Google à pessoa: o site pode estar aberto em 127.0.0.1 e a volta chega em
# localhost, onde o cookie não vale
_ESPERANDO: dict[str, tuple[int, str, float]] = {}
_TRAVA = threading.Lock()


def configurado() -> bool:
    return bool(ID and SEGREDO)


def url_login(usuario_id: int, voltar_para: str) -> str:
    estado = secrets.token_urlsafe(24)
    with _TRAVA:
        _ESPERANDO[estado] = (usuario_id, voltar_para, time.time())
    from urllib.parse import urlencode
    return URL_AUTORIZAR + "?" + urlencode({
        "client_id": ID, "redirect_uri": REDIRECT, "response_type": "code",
        "scope": ESCOPOS, "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
        "state": estado})


def concluir(code: str, estado: str) -> tuple[int, str, list[dict]]:
    """Troca o código pelos tokens e guarda um por canal da conta. Devolve quem era, para onde voltar e os canais."""
    with _TRAVA:
        quem = _ESPERANDO.pop(estado, None)
    if not quem or time.time() - quem[2] > 900:
        raise RuntimeError("O login demorou demais ou não começou aqui. Clique em Conectar de novo.")
    usuario_id, voltar_para, _ = quem
    r = _CLIENTE.post(URL_TOKEN, data={"code": code, "client_id": ID,
                                       "client_secret": SEGREDO, "redirect_uri": REDIRECT,
                                       "grant_type": "authorization_code"})
    if r.status_code != 200:
        raise RuntimeError(f"O Google recusou o login ({r.status_code}).")
    tokens = r.json()
    canais = _CLIENTE.get(URL_DADOS + "channels", params={"part": "snippet", "mine": "true"},
                          headers={"Authorization": f"Bearer {tokens['access_token']}"}).json().get("items", [])
    if not canais:
        raise RuntimeError("Essa conta do Google não tem canal no YouTube. Entre com a conta do canal.")
    for c in canais:
        banco.executar(
            "INSERT OR REPLACE INTO studio (usuario_id, canal_id, titulo, refresh_token, access_token, expira, conectado) "
            "VALUES (?,?,?,?,?,?,?)", usuario_id, c["id"], c["snippet"]["title"], tokens.get("refresh_token", ""),
            tokens["access_token"], time.time() + tokens.get("expires_in", 3600) - 60, banco.agora())
    return usuario_id, voltar_para, [{"id": c["id"], "titulo": c["snippet"]["title"]} for c in canais]


def _token(usuario_id: int, canal_id: str) -> str:
    s = banco.um("SELECT * FROM studio WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id)
    if not s:
        raise PermissionError("Este canal não está conectado ao YouTube Studio.")
    if s["access_token"] and s["expira"] > time.time():
        return s["access_token"]
    r = _CLIENTE.post(URL_TOKEN, data={"client_id": ID, "client_secret": SEGREDO,
                                       "refresh_token": s["refresh_token"], "grant_type": "refresh_token"})
    if r.status_code != 200:
        raise PermissionError("O acesso ao YouTube Studio venceu. Conecte de novo.")
    t = r.json()
    banco.executar("UPDATE studio SET access_token=?, expira=? WHERE usuario_id=? AND canal_id=?",
                   t["access_token"], time.time() + t.get("expires_in", 3600) - 60, usuario_id, canal_id)
    return t["access_token"]


def conectados(usuario_id: int) -> list[str]:
    return [l["canal_id"] for l in banco.todos("SELECT canal_id FROM studio WHERE usuario_id=?", usuario_id)]


def desconectar(usuario_id: int, canal_id: str) -> None:
    banco.executar("DELETE FROM studio WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id)


def _relatorio(token: str, canal_id: str, inicio: str, fim: str, metricas: str, **extra) -> dict | None:
    params = {"ids": f"channel=={canal_id}", "startDate": inicio, "endDate": fim, "metrics": metricas, **extra}
    r = _CLIENTE.get(URL_ANALYTICS, params=params, headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        _ULTIMO_ERRO[0] = r.text
        return None      # métrica que o canal não tem (receita sem monetização) não derruba o resto
    d = r.json()
    nomes = [c["name"] for c in d.get("columnHeaders", [])]
    return {"linhas": [dict(zip(nomes, l)) for l in d.get("rows", [])]}


_ULTIMO_ERRO = [""]


def _explicar(texto: str) -> str:
    """O erro do Google em português, com o que fazer."""
    import re
    if "has not been used in project" in texto or "is disabled" in texto:
        projeto = re.search(r"project[= ](\d+)", texto)
        link = f"https://console.cloud.google.com/apis/library/youtubeanalytics.googleapis.com?project={projeto.group(1)}" if projeto else ""
        return ("A YouTube Analytics API não está ativada no projeto do Google. Ative em " + link +
                " e espere uns 2 minutos.") if link else "A YouTube Analytics API não está ativada no projeto do Google."
    if "insufficient" in texto.lower() or "forbidden" in texto.lower():
        return "O Google não deu permissão para as métricas. Conecte de novo e marque todas as permissões."
    return "O YouTube Analytics recusou o pedido. Tente de novo em alguns minutos."


PRINCIPAIS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost,likes,comments,shares"


def metricas(usuario_id: int, canal_id: str, dias: int = 28) -> dict:
    """As métricas do Studio de um período, comparadas com o período anterior. Guardado 1 hora."""
    chave = f"studio:{usuario_id}:{canal_id}:{dias}"
    cache = banco.um("SELECT dados, criado FROM traducoes WHERE chave=?", chave)
    if cache and time.time() - _segundos(cache["criado"]) < 3600:
        return json.loads(cache["dados"])
    token = _token(usuario_id, canal_id)
    fim = date.today() - timedelta(days=1)            # o dia de hoje ainda não fechou no Studio
    inicio = fim - timedelta(days=dias - 1)
    antes_fim, antes_inicio = inicio - timedelta(days=1), inicio - timedelta(days=dias)
    i, f, ai, af = (d.isoformat() for d in (inicio, fim, antes_inicio, antes_fim))
    total = _relatorio(token, canal_id, i, f, PRINCIPAIS)
    if total is None:
        raise RuntimeError(_explicar(_ULTIMO_ERRO[0]))
    anterior = _relatorio(token, canal_id, ai, af, PRINCIPAIS)
    receita = _relatorio(token, canal_id, i, f, "estimatedRevenue,cpm,playbackBasedCpm")
    impressoes = _relatorio(token, canal_id, i, f, "videoThumbnailImpressions,videoThumbnailImpressionsClickRate")
    por_dia = _relatorio(token, canal_id, i, f, "views,estimatedMinutesWatched,subscribersGained,subscribersLost",
                         dimensions="day", sort="day")
    videos = _relatorio(token, canal_id, i, f, "views,estimatedMinutesWatched,averageViewPercentage,subscribersGained",
                        dimensions="video", sort="-views", maxResults=10)
    fontes = _relatorio(token, canal_id, i, f, "views", dimensions="insightTrafficSourceType", sort="-views")
    paises = _relatorio(token, canal_id, i, f, "views", dimensions="country", sort="-views", maxResults=8)
    titulos = {}
    ids = [v["video"] for v in (videos or {}).get("linhas", [])]
    if ids:
        dados = _CLIENTE.get(URL_DADOS + "videos", params={"part": "snippet", "id": ",".join(ids)},
                             headers={"Authorization": f"Bearer {token}"}).json()
        titulos = {v["id"]: v["snippet"]["title"] for v in dados.get("items", [])}
    um = lambda r: (r or {}).get("linhas", [{}])[0] if (r or {}).get("linhas") else {}  # noqa: E731
    saida = {
        "periodo": {"inicio": i, "fim": f, "dias": dias},
        "total": um(total), "anterior": um(anterior), "receita": um(receita) or None, "impressoes": um(impressoes) or None,
        "por_dia": (por_dia or {}).get("linhas", []),
        "videos": [v | {"titulo": titulos.get(v["video"], "")} for v in (videos or {}).get("linhas", [])],
        "fontes": (fontes or {}).get("linhas", []), "paises": (paises or {}).get("linhas", []),
    }
    banco.executar("INSERT OR REPLACE INTO traducoes (chave, dados, criado) VALUES (?,?,?)",
                   chave, json.dumps(saida), banco.agora())
    return saida


def _segundos(iso: str) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return 0


def ultimo_video(usuario_id: int, canal_id: str) -> dict:
    """O desempenho do último vídeo, no modelo do card do YouTube Studio (pedido do usuário em 2026-10-15): views,
    comentários, curtidas, a posição dele entre os últimos 10, e do Studio as impressões, a taxa de cliques da
    thumbnail e a duração média. Sem o canal conectado, só os números públicos. Guardado 15 minutos."""
    from datetime import datetime, timezone
    from . import youtube
    chave = f"ultimo-video:{usuario_id}:{canal_id}"
    cache = banco.um("SELECT dados, criado FROM traducoes WHERE chave=?", chave)
    if cache and time.time() - _segundos(cache["criado"]) < 900:
        return json.loads(cache["dados"])
    ids = youtube.envios(canal_id, 10)      # 1 de cota, e mais 1 para os números dos 10 vídeos
    videos = sorted(youtube.videos(ids), key=lambda v: v.get("publicado") or "", reverse=True) if ids else []
    if not videos:
        raise RuntimeError("Este canal ainda não tem vídeo publicado.")
    v = videos[0]
    ranking = sorted(videos, key=lambda x: -(x["views"] or 0)).index(v) + 1
    publicado = datetime.fromisoformat(v["publicado"].replace("Z", "+00:00"))
    horas = (datetime.now(timezone.utc) - publicado).total_seconds() / 3600
    saida = {"id": v["id"], "titulo": v["titulo"], "publicado": v["publicado"], "horas": round(horas, 1),
             "views": v["views"], "curtidas": v.get("curtidas"), "comentarios": v.get("comentarios"),
             "ranking": ranking, "de": len(videos), "studio": None}
    if canal_id in conectados(usuario_id):
        try:
            token = _token(usuario_id, canal_id)
            inicio, fim = publicado.date().isoformat(), date.today().isoformat()
            base = _relatorio(token, canal_id, inicio, fim, "views,averageViewDuration,averageViewPercentage", filters=f"video=={v['id']}")
            alcance = _relatorio(token, canal_id, inicio, fim, "videoThumbnailImpressions,videoThumbnailImpressionsClickRate",
                                 filters=f"video=={v['id']}")
            um = lambda r: (r or {}).get("linhas", [{}])[0] if (r or {}).get("linhas") else {}  # noqa: E731
            b, a = um(base), um(alcance)
            saida["studio"] = {"duracao_media": b.get("averageViewDuration"), "porcentagem_media": b.get("averageViewPercentage"),
                               "impressoes": a.get("videoThumbnailImpressions"), "ctr": a.get("videoThumbnailImpressionsClickRate"),
                               "erro": "" if (base is not None) else _explicar(_ULTIMO_ERRO[0])}
        except Exception as erro:   # sem o Studio, o card segue com os números públicos
            saida["studio"] = {"erro": str(erro)[:200]}
    banco.executar("INSERT OR REPLACE INTO traducoes (chave, dados, criado) VALUES (?,?,?)", chave, json.dumps(saida), banco.agora())
    return saida
