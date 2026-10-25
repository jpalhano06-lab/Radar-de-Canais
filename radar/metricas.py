"""As contas do Radar, sem rede: o normal do canal, a nota de outlier, views por hora, a fase do canal e o selo.

Tudo aqui é função pura, testada em tests/test_metricas.py."""
from datetime import datetime, timezone
from statistics import median

CURTO_ATE_S = 180          # Shorts vão até 3 minutos
MADURO_DIAS = 3            # vídeo com menos de 3 dias ainda não mostra o que vai fazer
BASE_QUANTOS = 30          # o normal do canal sai dos 30 vídeos maduros mais novos


def data(texto: str) -> datetime | None:
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None


def dias_desde(texto: str, agora: datetime | None = None) -> float | None:
    quando = data(texto)
    if not quando:
        return None
    return ((agora or datetime.now(timezone.utc)) - quando).total_seconds() / 86400


def curto(duracao_s: int | None) -> bool:
    return bool(duracao_s) and duracao_s <= CURTO_ATE_S


def _validos(videos: list[dict]) -> list[dict]:
    return [v for v in videos if v.get("views") is not None and v.get("duracao_s") and not v.get("ao_vivo")]


def base(videos: list[dict], agora: datetime | None = None) -> dict:
    """A mediana de views dos vídeos maduros, separada entre longos e Shorts.

    Mediana, não média: um vídeo que estourou não pode virar o "normal" do canal."""
    longos, curtos = [], []
    for v in sorted(_validos(videos), key=lambda v: v.get("publicado", ""), reverse=True):
        idade = dias_desde(v.get("publicado", ""), agora)
        if idade is None or idade < MADURO_DIAS:
            continue
        (curtos if curto(v["duracao_s"]) else longos).append(v["views"])
    longos, curtos = longos[:BASE_QUANTOS], curtos[:BASE_QUANTOS]
    return {
        "base_longos": float(median(longos)) if longos else None,
        "base_curtos": float(median(curtos)) if curtos else None,
        "media_longos": sum(longos) / len(longos) if longos else None,
        "longos_medidos": len(longos),
    }


def nota_outlier(views: int | None, normal: float | None) -> float | None:
    """Quantas vezes o vídeo fez o normal do canal. Normal zero ou desconhecido: sem nota."""
    if views is None or not normal or normal <= 0:
        return None
    return round(views / normal, 1)


EXPLODIU_VIEWS = 500_000   # views dos vídeos longos publicados nos últimos 30 dias
EXPLODIU_DIAS = 30
TRACAO_ATE_DIAS = 60       # canal novo de até 60 dias...
TRACAO_VIDEOS = 3          # ...com 3 vídeos longos de 6x o normal...
TRACAO_NOTA = 6.0
TRACAO_VIEWS = 6_000       # ...e 6 mil views ou mais cada: com normal de 76, qualquer vídeo é 6x


def explodiu(videos: list[dict], primeiro_video: str, normal: float | None, agora: datetime | None = None) -> bool:
    """O canal que estourou agora, mesmo com o normal baixo (a régua de "explodiu" do Dotti Finder, 2026-10-25).

    A porta de sempre do garimpo pede normal de 10 mil: é consistência. Esta é a outra: 500 mil views nos vídeos longos
    dos últimos 30 dias, ou um canal de até 60 dias com 3 vídeos longos de 6x o normal. Shorts não contam."""
    longos = [v for v in _validos(videos) if not curto(v["duracao_s"])]
    recentes = 0
    for v in longos:
        dias = dias_desde(v.get("publicado", ""), agora)
        if dias is not None and dias <= EXPLODIU_DIAS:
            recentes += v["views"]
    if recentes >= EXPLODIU_VIEWS:
        return True
    postando = dias_desde(primeiro_video, agora)
    if postando is None or postando > TRACAO_ATE_DIAS:
        return False
    fortes = [v for v in longos if v["views"] >= TRACAO_VIEWS and (nota_outlier(v["views"], normal) or 0) >= TRACAO_NOTA]
    return len(fortes) >= TRACAO_VIDEOS


def engajamento(views: int | None, curtidas: int | None, comentarios: int | None) -> float | None:
    """Quanto o público reagiu: curtidas e comentários por view. Sem os três números não há taxa — e não ter
    não é o mesmo que ser zero, então volta None."""
    if not views or views <= 0 or curtidas is None or comentarios is None:
        return None
    return (curtidas + comentarios) / views


REACAO_ALTA = 2.0          # o dobro do normal do nicho: daí para cima a reação sai do comum (p90 das medições)


def reacao(taxa: float | None, normal_do_nicho: float | None) -> float | None:
    """Quantas vezes o vídeo foi mais curtido e comentado que o vídeo típico do nicho dele.

    Do nicho, não do canal nem do YouTube inteiro: Animais vive com 0,8% de reação e Religião com 2,7%, então
    um número só mediria o assunto em vez do vídeo."""
    if taxa is None or not normal_do_nicho or normal_do_nicho <= 0:
        return None
    return round(taxa / normal_do_nicho, 1)


def views_por_hora(views: int | None, publicado: str, agora: datetime | None = None) -> float | None:
    dias = dias_desde(publicado, agora)
    if views is None or dias is None:
        return None
    return views / max(1.0, dias * 24)


def fase(videos: list[dict], primeiro_video: str, agora: datetime | None = None) -> str:
    """nascendo, crescendo, estavel, caindo ou parado. Compara os 10 vídeos longos maduros mais novos com os 20
    anteriores."""
    validos = sorted(_validos(videos), key=lambda v: v.get("publicado", ""), reverse=True)
    if not validos:
        return ""
    ultimo = dias_desde(validos[0].get("publicado", ""), agora)
    if ultimo is not None and ultimo > 60:
        return "parado"
    postando = dias_desde(primeiro_video, agora)
    if postando is not None and postando < 90:
        return "nascendo"
    maduros = [v["views"] for v in validos
               if not curto(v["duracao_s"]) and (dias_desde(v.get("publicado", ""), agora) or 0) >= MADURO_DIAS]
    if len(maduros) < 8:
        return "nascendo" if postando is not None and postando < 180 else ""
    novos, antigos = median(maduros[:10]), median(maduros[10:30] or maduros[5:])
    if antigos <= 0:
        return "crescendo"
    razao = novos / antigos
    if razao >= 1.5:
        return "crescendo"
    if razao <= 0.6:
        return "caindo"
    return "estavel"


def meses_postando(primeiro_video: str, agora: datetime | None = None) -> float | None:
    dias = dias_desde(primeiro_video, agora)
    return None if dias is None else dias / 30.44


def raridade(media_por_video: float | None, meses: float | None) -> str:
    """O selo do achado: muita view por vídeo em pouco tempo de canal.

    lendario: 300 mil por vídeo em até 6 meses; epico: 100 mil em até 9; raro: 30 mil em até 12."""
    if not media_por_video or meses is None:
        return ""
    for selo, minimo, ate in (("lendario", 300_000, 6), ("epico", 100_000, 9), ("raro", 30_000, 12)):
        if media_por_video >= minimo and meses <= ate:
            return selo
    return ""


def pontos_do_ranking(media_por_video: float | None, meses: float | None, fase_canal: str) -> float:
    """A ordem do Top 30: views por vídeo, com peso para canal novo e que está crescendo."""
    if not media_por_video or meses is None:
        return 0.0
    juventude = 1.0 / max(1.0, meses) ** 0.5
    bonus = {"crescendo": 1.4, "nascendo": 1.2, "estavel": 1.0, "caindo": 0.5, "parado": 0.2}.get(fase_canal, 0.8)
    return media_por_video * juventude * bonus


def velocidade(videos: list[dict], agora: datetime | None = None, dias: int = 30) -> float | None:
    """Views por dia que os vídeos dos últimos 30 dias estão fazendo: é o que mostra o canal em alta agora.

    Cada vídeo conta pelas views que fez dividido pelos dias que tem de vida (no mínimo 1)."""
    total, achou = 0.0, False
    for v in _validos(videos):
        idade = dias_desde(v.get("publicado", ""), agora)
        if idade is not None and idade <= dias:
            total += v["views"] / max(1.0, idade)
            achou = True
    return round(total, 1) if achou else None


def ganho(antes: int | None, depois: int | None) -> int | None:
    if antes is None or depois is None:
        return None
    return depois - antes
