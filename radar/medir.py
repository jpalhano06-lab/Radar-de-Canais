"""Mede vídeos e canais pela API e guarda no banco, para a extensão e o garimpo não pagarem a mesma leitura duas vezes.

Vídeo vale por 1 hora, canal por 24 horas."""
import json
from datetime import datetime, timedelta, timezone

from . import banco, metricas, youtube

NOTA_OUTLIER = 3.0   # a mesma do garimpo: 3 vezes o normal do canal

VIDEO_VALE = timedelta(hours=1)
CANAL_VALE = timedelta(hours=24)


def _velho(medido: str, prazo: timedelta) -> bool:
    quando = metricas.data(medido)
    return not quando or datetime.now(timezone.utc) - quando > prazo


def _guardar_videos(lista: list[dict]) -> None:
    agora = banco.agora()
    hora = agora[:13]
    banco.varios(
        "INSERT INTO videos (id, canal_id, titulo, publicado, duracao_s, views, curtidas, comentarios, tags, medido) "
        "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET canal_id=excluded.canal_id, "
        "titulo=excluded.titulo, publicado=excluded.publicado, duracao_s=excluded.duracao_s, views=excluded.views, "
        "curtidas=excluded.curtidas, comentarios=excluded.comentarios, tags=excluded.tags, medido=excluded.medido",
        [(v["id"], v["canal_id"], v["titulo"], v["publicado"], v["duracao_s"], v["views"], v["curtidas"],
          v["comentarios"], json.dumps(v["tags"], ensure_ascii=False), agora) for v in lista])
    # uma leitura por hora de cada vídeo: é a curva de views que o painel desenha
    banco.varios("INSERT OR IGNORE INTO leituras (video_id, quando, views) VALUES (?,?,?)",
                 [(v["id"], hora, v["views"]) for v in lista if v["views"] is not None])


def medir_canais(ids: list[str], forcar: bool = False, origem: str = "") -> dict[str, dict]:
    """Lê os canais que estão velhos no banco e devolve todos os pedidos."""
    ids = [i for i in dict.fromkeys(ids) if i]
    guardados = {c["id"]: c for c in _canais_do_banco(ids)}
    faltam = [i for i in ids if forcar or i not in guardados or _velho(guardados[i]["medido"], CANAL_VALE)]
    if faltam:
        for canal in youtube.canais(faltam):
            ids_videos = youtube.envios(canal["id"], 50)
            lista = youtube.videos(ids_videos) if ids_videos else []
            _guardar_videos(lista)
            b = metricas.base(lista)
            datas = sorted(v["publicado"] for v in lista if v["publicado"])
            exato = bool(canal["videos_total"] is not None and len(ids_videos) >= (canal["videos_total"] or 0))
            # canal com mais de 50 vídeos: o mais antigo dos 50 não é o primeiro. Vale a criação do canal, senão o
            # Kurzgesagt (2013) passava por canal de 7 meses e ganhava o selo épico
            primeiro = datas[0] if datas else ""
            antes = guardados.get(canal["id"])
            if not exato and antes and antes["primeiro_exato"]:   # a data exata já achada (lista de envios) vale
                primeiro, exato = antes["primeiro_video"], True
            elif not exato and canal["criado_em"]:
                primeiro = min(primeiro or canal["criado_em"], canal["criado_em"])
            fase = metricas.fase(lista, primeiro)
            meses = metricas.meses_postando(primeiro)
            dados = {
                "id": canal["id"], "titulo": canal["titulo"], "handle": canal["handle"], "foto": canal["foto"],
                "pais": canal["pais"], "idioma": canal["idioma"], "inscritos": canal["inscritos"],
                "videos_total": canal["videos_total"], "views_total": canal["views_total"],
                "criado_em": canal["criado_em"], "primeiro_video": primeiro, "primeiro_exato": int(exato),
                "ultimo_video": datas[-1] if datas else "", "fase": fase,
                "raridade": metricas.raridade(b["base_longos"], meses), "medido": banco.agora(), **b,
                "velocidade": metricas.velocidade(lista),
            }
            # uma foto por dia dos números do canal: é dela que sai o ganho de inscritos da semana
            dia = banco.agora()[:10]
            banco.executar("INSERT OR REPLACE INTO historico (canal_id, dia, inscritos, views_total, videos_total) "
                           "VALUES (?,?,?,?,?)", canal["id"], dia, canal["inscritos"], canal["views_total"],
                           canal["videos_total"])
            semana = banco.um("SELECT inscritos FROM historico WHERE canal_id=? AND dia<=date(?, '-6 day') "
                              "ORDER BY dia DESC LIMIT 1", canal["id"], dia)
            dados["ganho_7d"] = metricas.ganho(semana["inscritos"] if semana else None, canal["inscritos"])
            if origem and canal["id"] not in guardados:
                dados["descoberto"] = banco.agora()
            banco.gravar("canais", "id", dados)
        guardados = {c["id"]: c for c in _canais_do_banco(ids)}
    return guardados


def _canais_do_banco(ids: list[str]) -> list[dict]:
    if not ids:
        return []
    return banco.todos(f"SELECT * FROM canais WHERE id IN ({','.join('?' * len(ids))})", *ids)


def medir_videos(ids: list[str]) -> dict[str, dict]:
    """Vídeos com a nota de outlier, as views por hora e os números do canal."""
    ids = [i for i in dict.fromkeys(ids) if i][:200]
    guardados = {v["id"]: v for v in _videos_do_banco(ids)}
    faltam = [i for i in ids if i not in guardados or _velho(guardados[i]["medido"], VIDEO_VALE)]
    if faltam:
        _guardar_videos(youtube.videos(faltam))
        guardados = {v["id"]: v for v in _videos_do_banco(ids)}
    canais = medir_canais([v["canal_id"] for v in guardados.values()])
    saida = {}
    for vid, v in guardados.items():
        c = canais.get(v["canal_id"], {})
        normal = c.get("base_curtos") if metricas.curto(v["duracao_s"]) else c.get("base_longos")
        saida[vid] = {
            "id": vid, "views": v["views"], "publicado": v["publicado"], "duracao_s": v["duracao_s"],
            "curto": metricas.curto(v["duracao_s"]), "nota": metricas.nota_outlier(v["views"], normal),
            "por_hora": metricas.views_por_hora(v["views"], v["publicado"]), "normal": normal,
            "curtidas": v["curtidas"], "comentarios": v["comentarios"],
            "canal": _canal_publico(c) if c else None,
        }
        # o vídeo que estourou (visto pela extensão, por exemplo) entra no Vídeos que estouraram
        if saida[vid]["nota"] and saida[vid]["nota"] >= NOTA_OUTLIER and c:
            banco.executar("INSERT OR IGNORE INTO outliers (video_id, canal_id, nota, achado) VALUES (?,?,?,?)",
                           vid, v["canal_id"], saida[vid]["nota"], banco.agora())
            banco.executar("UPDATE outliers SET nota=? WHERE video_id=?", saida[vid]["nota"], vid)
    return saida


def _videos_do_banco(ids: list[str]) -> list[dict]:
    if not ids:
        return []
    return banco.todos(f"SELECT * FROM videos WHERE id IN ({','.join('?' * len(ids))})", *ids)


def _canal_publico(c: dict) -> dict:
    meses = metricas.meses_postando(c.get("primeiro_video", ""))
    return {
        "id": c["id"], "titulo": c["titulo"], "handle": c["handle"], "foto": c["foto"], "pais": c["pais"],
        "inscritos": c["inscritos"], "videos_total": c["videos_total"], "views_total": c["views_total"],
        "criado_em": c["criado_em"], "primeiro_video": c["primeiro_video"], "primeiro_exato": bool(c["primeiro_exato"]),
        "meses_postando": round(meses, 1) if meses is not None else None, "ultimo_video": c["ultimo_video"],
        "normal_longos": c["base_longos"], "normal_curtos": c["base_curtos"], "media_longos": c["media_longos"],
        "fase": c["fase"], "raridade": c["raridade"], "nicho": c["nicho"], "subnicho": c.get("subnicho", ""),
        "velocidade": c.get("velocidade"), "ganho_7d": c.get("ganho_7d"), "no_radar": bool(c.get("no_radar")),
        "sem_rosto": None if c["sem_rosto"] is None else bool(c["sem_rosto"]),
        "anuncios": c.get("anuncios"), "membros": c.get("membros"),
    }


def canal_completo(canal_id: str) -> dict | None:
    c = medir_canais([canal_id]).get(canal_id)
    if not c:
        return None
    videos = banco.todos("SELECT * FROM videos WHERE canal_id=? ORDER BY publicado DESC LIMIT 50", canal_id)
    lista = []
    for v in videos:
        normal = c["base_curtos"] if metricas.curto(v["duracao_s"]) else c["base_longos"]
        lista.append({"id": v["id"], "titulo": v["titulo"], "publicado": v["publicado"], "views": v["views"],
                      "curto": metricas.curto(v["duracao_s"]), "nota": metricas.nota_outlier(v["views"], normal),
                      "por_hora": metricas.views_por_hora(v["views"], v["publicado"])})
    return {**_canal_publico(c), "videos": lista}


def curva(video_id: str) -> list[dict]:
    return banco.todos("SELECT quando, views FROM leituras WHERE video_id=? ORDER BY quando", video_id)
