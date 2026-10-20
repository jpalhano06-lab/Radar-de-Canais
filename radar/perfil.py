"""Meu perfil (os canais da pessoa e as ideias para cada um) e a procura de nicho na hora.

Pedido do usuário em 2026-10-13: a primeira página é o perfil, com os canais dele conectados; clicando num canal, os
vídeos que estouraram em canais parecidos ("ideias para copiar"). E a procura de nicho busca no YouTube na hora, com
um botão para procurar de novo de outro jeito quando não acha."""
import json
from datetime import datetime, timedelta, timezone

from . import banco, garimpo, gosto, ia, medir, mercado, metricas, youtube

# ---------------------------------------------------------------- meus canais


def conectar(usuario_id: int, canal_id: str, meu: bool = True) -> dict:
    """Mede o canal da pessoa e descobre o nicho dele (para achar ideias). Não entra no Radar: é dela.
    meu=False: canal de referência das perguntas da primeira vez (só mede e classifica)."""
    c = medir.medir_canais([canal_id], forcar=True)[canal_id]
    if not c["nicho"] or not c["subnicho"]:
        titulos = [v["titulo"] for v in banco.todos(
            "SELECT titulo FROM videos WHERE canal_id=? ORDER BY views DESC LIMIT 15", canal_id)]
        existentes = [l["subnicho"] for l in banco.todos(
            "SELECT subnicho, COUNT(*) AS n FROM canais WHERE no_radar=1 AND subnicho<>'' GROUP BY subnicho "
            "ORDER BY n DESC LIMIT 80")]
        nicho, subnicho = ia.nicho(c["titulo"], titulos, existentes)
        banco.executar("UPDATE canais SET nicho=COALESCE(NULLIF(nicho,''), ?), subnicho=COALESCE(NULLIF(subnicho,''), ?) "
                       "WHERE id=?", nicho, subnicho, canal_id)
    if meu:
        banco.executar("INSERT OR IGNORE INTO meus_canais (usuario_id, canal_id, criado) VALUES (?,?,?)",
                       usuario_id, canal_id, banco.agora())
    return banco.um("SELECT * FROM canais WHERE id=?", canal_id)


def ultimos_videos(canal: dict, quantos: int = 12) -> list[dict]:
    linhas = banco.todos("SELECT id, titulo, views, publicado, duracao_s FROM videos WHERE canal_id=? "
                         "ORDER BY publicado DESC LIMIT ?", canal["id"], quantos)
    for v in linhas:
        normal = canal["base_curtos"] if metricas.curto(v["duracao_s"]) else canal["base_longos"]
        v["nota"] = metricas.nota_outlier(v["views"], normal)
        v["por_hora"] = metricas.views_por_hora(v["views"], v["publicado"])
    return linhas


def historico(canal_id: str) -> list[dict]:
    return banco.todos("SELECT dia, inscritos, views_total FROM historico WHERE canal_id=? ORDER BY dia", canal_id)


def ideias_da_base(canal: dict, limite: int = 24) -> list[dict]:
    """Vídeos que estouraram em outros canais do mesmo subnicho, depois do mesmo nicho. Sem cota: só o banco."""
    saida, vistos = [], set()
    for campo in ("subnicho", "nicho"):
        if not canal.get(campo):
            continue
        for l in banco.todos(
                "SELECT o.nota, v.id, v.titulo, v.views, v.publicado, v.duracao_s, c.id AS canal_id, "
                "c.titulo AS canal, c.foto, c.handle, c.inscritos, c.subnicho FROM outliers o "
                "JOIN videos v ON v.id=o.video_id JOIN canais c ON c.id=o.canal_id "
                f"WHERE c.{campo}=? AND c.id<>? AND o.nota>=3 AND v.duracao_s>? ORDER BY o.nota DESC LIMIT ?",
                canal[campo], canal["id"], metricas.CURTO_ATE_S, limite):
            if l["id"] not in vistos:
                vistos.add(l["id"])
                saida.append(l | {"origem": "mesmo subnicho" if campo == "subnicho" else "mesmo nicho"})
    return saida[:limite]


def parecidos_da_base(canal: dict, limite: int = 8) -> list[dict]:
    if not canal.get("subnicho") and not canal.get("nicho"):
        return []
    campo = "subnicho" if canal.get("subnicho") else "nicho"
    return banco.todos(f"SELECT * FROM canais WHERE no_radar=1 AND {campo}=? AND id<>? ORDER BY base_longos DESC LIMIT ?",
                       canal[campo], canal["id"], limite)


# o "procurar de novo": cada tentativa busca de um jeito diferente
JEITOS = [
    {"duracao": "medium", "dias": 30, "ordem": "viewCount", "texto": "vídeos médios do último mês, mais vistos"},
    {"duracao": "long", "dias": 30, "ordem": "viewCount", "texto": "vídeos longos do último mês, mais vistos"},
    {"duracao": "any", "dias": 90, "ordem": "viewCount", "ingles": True, "texto": "a busca em inglês, últimos 3 meses"},
    {"duracao": "medium", "dias": 90, "ordem": "relevance", "texto": "os mais relevantes dos últimos 3 meses"},
    {"duracao": "long", "dias": 180, "ordem": "viewCount", "ingles": True, "texto": "em inglês, vídeos longos de 6 meses"},
    {"duracao": "any", "dias": 365, "ordem": "relevance", "texto": "os mais relevantes do último ano"},
]


def _termo(termo: str, jeito: dict) -> str:
    if jeito.get("ingles"):
        traduzido = ia.traduzir_titulo(termo, ["en"]).get("en")
        if traduzido:
            return traduzido
    return termo


def _videos_com_nota(ids_videos: list[str], canais: dict) -> list[dict]:
    saida = []
    for v in youtube.videos(ids_videos):
        c = canais.get(v["canal_id"])
        if not c or metricas.curto(v["duracao_s"]):
            continue
        nota = metricas.nota_outlier(v["views"], c["base_longos"])
        saida.append({"id": v["id"], "titulo": v["titulo"], "views": v["views"], "publicado": v["publicado"],
                      "duracao_s": v["duracao_s"], "nota": nota, "canal_id": c["id"], "canal": c["titulo"],
                      "foto": c["foto"], "handle": c["handle"], "inscritos": c["inscritos"]})
        if nota and nota >= garimpo.NOTA_OUTLIER:
            banco.executar("INSERT OR REPLACE INTO outliers (video_id, canal_id, nota, achado) VALUES (?,?,?,?)",
                           v["id"], c["id"], nota, banco.agora())
    return saida


def _sementes(usuario_id: int, canal_id: str) -> list[str]:
    """Os títulos que dizem o que a pessoa quer: os 🎯 mais recentes, os escolhidos no treino e os vídeos dos canais
    inscritos no algoritmo, nessa ordem."""
    from . import treinamento
    titulos = [l["titulo"] for l in banco.todos(
        "SELECT titulo FROM alvos WHERE usuario_id=? AND canal_id=? ORDER BY criado DESC LIMIT 10", usuario_id, canal_id)]
    t = treinamento.estado(usuario_id, canal_id) or {}
    if t.get("positivos"):
        ids = t["positivos"][-10:]
        titulos += [v["titulo"] for v in banco.todos(f"SELECT titulo FROM videos WHERE id IN ({','.join('?' * len(ids))})", *ids)]
    titulos += [v["titulo"] for v in banco.todos(
        "SELECT v.titulo FROM canais_inscritos i JOIN videos v ON v.canal_id=i.ref_canal_id "
        "WHERE i.usuario_id=? AND i.canal_id=? ORDER BY v.views DESC LIMIT 8", usuario_id, canal_id)]
    return titulos


def mais_ideias(canal: dict, tentativa: int = 0, usuario_id: int | None = None) -> dict:
    """Ideias tiradas do YouTube na hora (o botão "Buscar ideias novas"): busca o assunto do que a pessoa ensinou ao
    algoritmo (🎯, treino, canais inscritos) ou, sem isso, dos vídeos que mais renderam no canal dela, e devolve os que
    fizeram bem mais que o normal do próprio canal. Cada vez busca de um jeito (JEITOS). Uns 200 a 250 de cota."""
    jeito = JEITOS[tentativa % len(JEITOS)]
    melhores = [v["titulo"] for v in banco.todos(
        "SELECT titulo FROM videos WHERE canal_id=? AND duracao_s>? ORDER BY views DESC LIMIT 12",
        canal["id"], metricas.CURTO_ATE_S)]
    sementes = _sementes(usuario_id, canal["id"]) if usuario_id else []
    base = (sementes + melhores)[:16]
    buscas = ia.sugerir_termos(canal.get("subnicho") or canal.get("nicho") or canal["titulo"], base, 4) or base[:4]
    buscas = (buscas[tentativa % 2 * 2:] + buscas)[:2]      # alterna os pares de buscas a cada clique
    depois = (datetime.now(timezone.utc) - timedelta(days=jeito["dias"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    achados = []
    for b in buscas[:2]:
        achados += youtube.buscar(_termo(b, jeito), publicado_depois=depois, duracao=jeito["duracao"],
                                  ordem=jeito["ordem"], quantos=25)
    achados = [a for a in achados if a["canal_id"] != canal["id"]]
    canais = medir.medir_canais(list(dict.fromkeys(a["canal_id"] for a in achados))[:20])
    videos = [v for v in _videos_com_nota([a["video_id"] for a in achados], canais) if (v["nota"] or 0) >= 1.5]
    videos.sort(key=lambda v: -(v["nota"] or 0))
    return {"videos": videos[:24], "buscas": buscas, "jeito": jeito["texto"], "proxima": tentativa + 1}


# ---------------------------------------------------------------- procurar nicho na hora

def procurar(termo: str, tentativa: int = 0) -> dict:
    """Busca o nicho no YouTube agora, mede os canais e põe no Radar os novos que vão bem (uns 100 a 250 unidades).
    O termo fica para o garimpo de todo dia continuar procurando."""
    jeito = JEITOS[tentativa % len(JEITOS)]
    busca = _termo(termo, jeito)
    depois = (datetime.now(timezone.utc) - timedelta(days=jeito["dias"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    # como todas as procuras do app: em inglês, nos países de língua inglesa, os EUA de preferência
    if gosto.lingua(busca) in ("pt", "es"):
        busca = ia.traduzir_titulo(busca, ["en"]).get("en") or busca
    achados = youtube.buscar(busca, publicado_depois=depois, duracao=jeito["duracao"], ordem=jeito["ordem"],
                             regiao=mercado.regiao(tentativa), idioma="en")
    ids = list(dict.fromkeys(a["canal_id"] for a in achados))
    contagem = {"novos": 0}
    entraram = garimpo._avaliar(ids, lambda _t: None, contagem, rapido=True)
    no_radar = [c["id"] for c in medir._canais_do_banco(ids) if c["no_radar"]]
    if not banco.um("SELECT 1 AS x FROM termos_auto WHERE lower(termo)=lower(?)", termo):
        banco.executar("INSERT OR IGNORE INTO termos_auto (termo, nicho, origem, criado) VALUES (?,?,?,?)",
                       termo, "Procurados", "procura", banco.agora())
    return {"busca": busca, "jeito": jeito["texto"], "vistos": len(ids), "novos": entraram,
            "no_radar": no_radar, "proxima": tentativa + 1}
