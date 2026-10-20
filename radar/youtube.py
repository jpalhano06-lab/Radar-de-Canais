"""A API de dados do YouTube (v3), revezando as chaves e contando a cota de cada uma.

Custos (unidades): search.list 100; videos.list, channels.list e playlistItems.list 1 por página de até 50."""
import re
import threading

import httpx

from . import banco
from .config import COTA_POR_CHAVE, chaves_youtube

URL = "https://www.googleapis.com/youtube/v3/"
_CLIENTE = httpx.Client(timeout=httpx.Timeout(20, connect=10))
_TRAVA = threading.Lock()


class SemCota(RuntimeError):
    """Todas as chaves gastaram a cota do dia (ela volta à meia-noite do Pacífico, 5 h no horário de Brasília)."""


def _final(chave: str) -> str:
    return chave[-6:]


def _usado(chave: str) -> dict:
    return banco.um("SELECT unidades, esgotada FROM cota WHERE dia=? AND chave=?",
                    banco.hoje_pacifico(), _final(chave)) or {"unidades": 0, "esgotada": 0}


def _somar(chave: str, unidades: int, esgotada: bool = False) -> None:
    banco.executar(
        "INSERT INTO cota (dia, chave, unidades, esgotada) VALUES (?,?,?,?) ON CONFLICT(dia, chave) DO UPDATE SET "
        "unidades=unidades+excluded.unidades, esgotada=MAX(esgotada, excluded.esgotada)",
        banco.hoje_pacifico(), _final(chave), unidades, int(esgotada))


def cota_hoje() -> dict:
    chaves = chaves_youtube()
    usado = sum(_usado(c)["unidades"] for c in chaves)
    return {"chaves": len(chaves), "usado": usado, "total": len(chaves) * COTA_POR_CHAVE,
            "livre": max(0, len(chaves) * COTA_POR_CHAVE - usado)}


def _escolher(custo: int) -> str | None:
    """A chave com mais cota livre que ainda aguenta o pedido."""
    melhor, livre_melhor = None, -1
    for chave in chaves_youtube():
        u = _usado(chave)
        livre = COTA_POR_CHAVE - u["unidades"]
        if not u["esgotada"] and livre >= custo and livre > livre_melhor:
            melhor, livre_melhor = chave, livre
    return melhor


def _pedir(recurso: str, params: dict, custo: int) -> dict:
    if not chaves_youtube():
        raise RuntimeError("Falta a YOUTUBE_API_KEY no finder/.env.")
    for _ in range(len(chaves_youtube()) + 1):
        with _TRAVA:
            chave = _escolher(custo)
            if not chave:
                raise SemCota("A cota do YouTube de hoje acabou em todas as chaves. Volta às 5 h (Brasília).")
            _somar(chave, custo)
        r = _CLIENTE.get(URL + recurso, params={**params, "key": chave})
        if r.status_code == 200:
            return r.json()
        motivo = ""
        try:
            motivo = r.json()["error"]["errors"][0]["reason"]
        except Exception:
            pass
        if r.status_code == 403 and motivo in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            _somar(chave, 0, esgotada=True)
            continue
        if r.status_code in (400, 403) and motivo in ("keyInvalid", "accessNotConfigured", "forbidden"):
            _somar(chave, 0, esgotada=True)
            continue
        raise RuntimeError(f"YouTube {recurso} respondeu {r.status_code}: {r.text[:200]}")
    raise SemCota("Nenhuma chave do YouTube atendeu.")


def duracao(texto: str) -> int:
    """PT1H2M3S em segundos. P0D (estreia, ao vivo) vira 0."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", texto or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _int(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _melhor_capa(capas: dict) -> str:
    for nome in ("high", "medium", "default"):
        if capas.get(nome, {}).get("url"):
            return capas[nome]["url"]
    return ""


def videos(ids: list[str]) -> list[dict]:
    saida = []
    ids = [i for i in dict.fromkeys(ids) if re.fullmatch(r"[\w-]{11}", i or "")]
    for i in range(0, len(ids), 50):
        dados = _pedir("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i + 50]),
                                  "maxResults": 50}, 1)
        for item in dados.get("items", []):
            sn, st, cd = item.get("snippet", {}), item.get("statistics", {}), item.get("contentDetails", {})
            saida.append({
                "id": item["id"], "canal_id": sn.get("channelId", ""), "titulo": sn.get("title", ""),
                "publicado": sn.get("publishedAt", ""), "duracao_s": duracao(cd.get("duration", "")),
                "views": _int(st.get("viewCount")), "curtidas": _int(st.get("likeCount")),
                "comentarios": _int(st.get("commentCount")), "tags": sn.get("tags", [])[:30],
                "ao_vivo": sn.get("liveBroadcastContent", "none") != "none",
            })
    return saida


def canais(ids: list[str]) -> list[dict]:
    saida = []
    ids = [i for i in dict.fromkeys(ids) if i and i.startswith("UC")]
    for i in range(0, len(ids), 50):
        dados = _pedir("channels", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i + 50]),
                                    "maxResults": 50}, 1)
        saida += [_canal(item) for item in dados.get("items", [])]
    return saida


def canal_por_handle(handle: str) -> dict | None:
    dados = _pedir("channels", {"part": "snippet,statistics,contentDetails", "forHandle": handle.lstrip("@")}, 1)
    itens = dados.get("items", [])
    return _canal(itens[0]) if itens else None


def _canal(item: dict) -> dict:
    sn, st = item.get("snippet", {}), item.get("statistics", {})
    return {
        "id": item["id"], "titulo": sn.get("title", ""), "handle": sn.get("customUrl", ""),
        "foto": _melhor_capa(sn.get("thumbnails", {})), "pais": sn.get("country", ""),
        "idioma": sn.get("defaultLanguage", ""), "criado_em": sn.get("publishedAt", ""),
        "inscritos": None if st.get("hiddenSubscriberCount") else _int(st.get("subscriberCount")),
        "videos_total": _int(st.get("videoCount")), "views_total": _int(st.get("viewCount")),
        "uploads": item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", ""),
    }


def envios(canal_id: str, quantos: int = 50) -> list[str]:
    """Os vídeos mais novos do canal, pela lista de envios (UC... vira UU...)."""
    lista = "UU" + canal_id[2:]
    try:
        dados = _pedir("playlistItems", {"part": "contentDetails", "playlistId": lista,
                                         "maxResults": min(50, quantos)}, 1)
    except RuntimeError as erro:
        if "404" in str(erro):
            return []
        raise
    return [i["contentDetails"]["videoId"] for i in dados.get("items", [])]


def primeiro_envio(canal_id: str, max_paginas: int = 40) -> str:
    """A data do primeiro vídeo do canal: anda a lista de envios inteira (1 unidade por 50 vídeos, até 2.000 vídeos).
    Canal antigo que só agora começou a postar parecia velho pela data de criação. "" = não deu para saber."""
    lista, pagina, primeiro = "UU" + canal_id[2:], "", ""
    for _ in range(max_paginas):
        params = {"part": "contentDetails", "playlistId": lista, "maxResults": 50}
        if pagina:
            params["pageToken"] = pagina
        try:
            dados = _pedir("playlistItems", params, 1)
        except RuntimeError as erro:
            if "404" in str(erro):
                return ""
            raise
        datas = [i["contentDetails"].get("videoPublishedAt", "") for i in dados.get("items", [])]
        primeiro = min([d for d in datas if d] + ([primeiro] if primeiro else []), default=primeiro)
        pagina = dados.get("nextPageToken", "")
        if not pagina:
            return primeiro
    return ""   # mais vídeos que o limite: o primeiro não foi visto


def buscar(termo: str, publicado_depois: str = "", duracao: str = "any", idioma: str = "",
           ordem: str = "viewCount", quantos: int = 50, regiao: str = "") -> list[dict]:
    """search.list de vídeos (100 unidades). Devolve id do vídeo, id do canal e título."""
    params = {"part": "snippet", "q": termo, "type": "video", "order": ordem, "maxResults": min(50, quantos),
              "videoDuration": duracao, "safeSearch": "none"}
    if publicado_depois:
        params["publishedAfter"] = publicado_depois
    if idioma:
        params["relevanceLanguage"] = idioma
    if regiao:
        params["regionCode"] = regiao
    dados = _pedir("search", params, 100)
    return [{"video_id": i["id"]["videoId"], "canal_id": i["snippet"]["channelId"], "titulo": i["snippet"]["title"],
             "canal": i["snippet"].get("channelTitle", "")}
            for i in dados.get("items", []) if i.get("id", {}).get("videoId")]
