"""O crachá do canal: que tipo de canal é, com o motivo de cada voto.

A ideia veio do Dotti Finder: juízes independentes olham o canal e votam com um peso, vence o maior peso e a tela mostra
os motivos, para quem lê poder discordar. As regras e os cortes daqui são do Radar, sobre o que o banco tem, e são ponto
de partida: nenhum foi medido contra o resultado de canal nenhum.
"""
from datetime import datetime
from statistics import median

from . import metricas

VOLUME_QUENTE = 500_000     # views em 30 dias para o canal contar como quente
NOVO_ATE_DIAS = 90
VIDEO_GRANDE = 100_000
NOTA_FORTE = 6              # outlier que conta como tração
SILENCIO_MIN, SILENCIO_MAX = 21, 120

ROTULOS = {"novo_explodindo": "Canal novo explodindo", "novo_forte": "Canal novo começando forte",
           "alta": "Canal antigo bombando agora", "fonte": "Bom para tirar ideias de títulos", "queda": "Perdendo força",
           "fraco": "Fraco agora", "de_olho": "Sem sinal ainda", "sem_dados": "Tipo a definir"}
SAUDE = {"novo_explodindo": "alta", "novo_forte": "alta", "alta": "alta", "fonte": "neutra", "queda": "queda", "fraco": "queda",
         "de_olho": "neutra", "sem_dados": "neutra"}


def _mil(n: float) -> str:
    return f"{round(n):,}".replace(",", ".")


def _longos(videos: list[dict], agora: datetime | None) -> list[dict]:
    """Só vídeos longos com data, do mais novo para o mais velho: Short não diz nada sobre o ritmo do canal."""
    saida = []
    for v in videos:
        dias = metricas.dias_desde(v.get("publicado") or "", agora)
        if dias is not None and not metricas.curto(v.get("duracao_s")):
            saida.append({**v, "dias": dias, "views": v.get("views") or 0})
    return sorted(saida, key=lambda v: v["dias"])


def _ritmo(longos: list[dict]) -> float | None:
    """De quantos em quantos dias o canal posta, pelos 11 vídeos mais novos."""
    datas = [v["dias"] for v in longos[:11]]
    return max(1.0, median(b - a for a, b in zip(datas, datas[1:]))) if len(datas) >= 2 else None


def _queda(longos: list[dict]) -> float | None:
    """Os 5 vídeos mais novos contra os 5 anteriores. Vídeo de menos de 7 dias fica de fora: ainda não juntou views."""
    maduros = [v for v in longos if v["dias"] >= 7]
    if len(maduros) < 10:
        return None
    antes = median(v["views"] for v in maduros[5:10])
    return round(median(v["views"] for v in maduros[:5]) / antes, 2) if antes else None


def julgar(canal: dict, videos: list[dict], agora: datetime | None = None, views_30d_canal: int | None = None) -> dict:
    longos = _longos(videos, agora)
    n = len(longos)
    idade = metricas.dias_desde(canal.get("primeiro_video") or canal.get("criado_em") or "", agora)
    if n < 3 or idade is None:
        return {"tipo": "sem_dados", "rotulo": ROTULOS["sem_dados"], "saude": SAUDE["sem_dados"], "projecao_30d": None,
                "ritmo_dias": None, "dias_parado": None, "views_30d": None, "queda": None,
                "motivos": [{"juiz": "amostra", "voto": None, "peso": 0, "texto": f"só {n} vídeo(s) longo(s) no Radar: ainda não dá para julgar"}]}
    idade = round(idade)
    votos: list[dict] = []

    def votar(juiz: str, tipo: str | None, peso: int, texto: str) -> None:
        votos.append({"juiz": juiz, "voto": tipo, "peso": peso, "texto": texto})

    ritmo, parado = _ritmo(longos), round(longos[0]["dias"])
    limite = round(min(max(ritmo * 3, SILENCIO_MIN), SILENCIO_MAX)) if ritmo else SILENCIO_MIN
    if parado > limite:
        votar("atividade", "queda", 100, f"parou de postar há {parado} dias (costumava postar a cada {round(ritmo or 0)})")

    do_mes = sum(v["views"] for v in longos if v["dias"] <= 30)
    views_30 = max(views_30d_canal or 0, do_mes)
    if views_30 >= VOLUME_QUENTE:
        novo = idade <= NOVO_ATE_DIAS
        votar("volume", "novo_explodindo" if novo else "alta", 80,
              f"{_mil(views_30)} views em 30 dias" + (f", com só {idade} dias de vida" if novo else ""))

    projecao = None
    if idade < 60:
        projecao = round(sum(v["views"] for v in longos) / max(idade, 1) * 30)
        if projecao >= VOLUME_QUENTE and views_30 < VOLUME_QUENTE:
            votar("projeção", "novo_forte", 75, f"no ritmo de agora, chega a {_mil(projecao)} views em 30 dias")

    vistas = sorted(v["views"] for v in longos)
    tipico, topo = median(vistas), vistas[-1]
    if n >= 8 and topo and tipico / topo < 0.1:
        # acerto é o que passa de longe do típico: um vídeo na média do canal não conta só por ser grande
        acerto = next((v for v in longos if v["views"] >= max(VIDEO_GRANDE, tipico * 3) and v["dias"] <= 180), None)
        if acerto:
            votar("consistência", "fonte", 70, f"o vídeo típico faz {_mil(tipico)} views, mas um acertou {_mil(acerto['views'])} há "
                                               f"{round(acerto['dias'])} dias")

    fortes = sum(1 for v in longos if (v.get("nota") or 0) >= NOTA_FORTE)
    if idade <= NOVO_ATE_DIAS and fortes >= 2:
        votar("tração", "novo_forte", 60, f"{fortes} vídeos acima de {NOTA_FORTE}x o normal, com só {idade} dias de vida")

    queda = _queda(longos)
    if queda is not None and queda < 0.5:
        votar("momento", "queda", 55, f"os vídeos novos fazem {str(queda).replace('.', ',')}x o que os anteriores faziam")

    if n < 8 and views_30 < VOLUME_QUENTE and idade > NOVO_ATE_DIAS and topo < VIDEO_GRANDE:
        votar("de olho", "de_olho", 50, f"só {n} vídeos: ainda não dá para dizer se cresce ou cai")
    if topo < VIDEO_GRANDE and tipico < 5000 and fortes < 2:
        votar("piso", "fraco", 30, "vídeos com poucas views e nenhum destaque")

    decisivos = sorted((v for v in votos if v["voto"]), key=lambda v: -v["peso"])
    tipo = decisivos[0]["voto"] if decisivos else "fraco"
    if not decisivos:
        votar("resto", None, 0, "nenhum sinal forte: sem volume, sem queda e sem destaque")
    return {"tipo": tipo, "rotulo": ROTULOS[tipo], "saude": SAUDE[tipo], "motivos": votos, "projecao_30d": projecao,
            "ritmo_dias": round(ritmo) if ritmo else None, "dias_parado": parado, "views_30d": views_30, "queda": queda}
