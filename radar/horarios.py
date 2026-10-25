"""O melhor horário para postar, tirado das curvas do próprio canal.

Pedido do usuário em 2026-10-25, depois de abrir a vidIQ 3.233.0 com o REA. Lá, quando o servidor não tem dado do
canal, a curva do "Melhor Horário para Publicar" não é do canal: é uma matriz 7 x 24 escrita no código
(`TAt.activity`) com um ruído de ±15% semeado pelo id do vídeo (`B6t`), guardada três dias para parecer estável, e
cobrada no plano Pro. Aqui não se inventa nada — sem leitura suficiente o Radar responde que não sabe (`suficiente`
falso, `pico` nulo) e a tela não mostra faixa nenhuma.

A medida sai do que o Radar já guarda de graça: o `medir.py` grava em `leituras` as views acumuladas de cada vídeo,
no máximo uma linha por hora. A diferença entre duas leituras é o quanto aquele vídeo rendeu naquelas horas, ou seja,
quando o público daquele canal aparece. Somando os vídeos sai o histograma 7 x 24 (dia da semana x hora), que o site
e a extensão mostram em 8 faixas de 3 horas — o mesmo agrupamento da vidIQ, para o número ser comparável.

**O limite desta fonte, medido no banco em 2026-10-25** (127.834 pares de leituras vizinhas): só **3%** dos pares
estão a 6 horas ou menos um do outro. 73% estão a 13-36 horas e 23% a mais de 36. É o esperado: o vídeo só é lido de
hora em hora enquanto alguém passa por ele (`VIDEO_VALE`), e o canal inteiro é relido uma vez por dia
(`CANAL_VALE`). Par de 24 horas diz o total do dia, não a hora, então é descartado — e por isso o histograma só
fecha nos canais que a extensão visitou muito. Fonte bem melhor para o canal da própria pessoa: o `extensao/studio.js`
já busca as views **hora a hora das últimas 48 h** na análise do Studio, com o login dela e sem cota; guardando esses
pontos a cada passagem, em algumas semanas sai um 7 x 24 denso e real. Fica anotado como o próximo passo.

Três cuidados, cada um para o número não mentir:

- **As primeiras 24 horas do vídeo não contam** (`IGNORAR_H`). O pico de estreia mostra a hora em que o canal
  publicou, não a hora em que o público assiste; contando a estreia o histograma recomendaria de volta o horário que
  o canal já usa, e pareceria certíssimo sem nunca ter medido nada.
- **Cada vídeo pesa igual**: a parte de cada faixa é dividida pelo total daquele vídeo antes de somar. Sem isso um
  vídeo que estourou viraria sozinho o "melhor horário" do canal.
- **Buraco grande entre leituras é jogado fora** (`BURACO_MAX_H`). Se o Radar ficou muitas horas sem medir, não há
  como saber em qual delas as views entraram. Até 6 horas a diferença é espalhada igualmente pelas horas cobertas.

O fuso chega em minutos somados ao UTC (-180 é Brasília), porque a pessoa pensa em "sete da noite" na hora dela e o
`leituras.quando` está em UTC.
"""
from datetime import datetime, timedelta, timezone

from . import banco, metricas

DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")   # na ordem do weekday(): 0 é segunda
FAIXAS = ((0, 2), (3, 5), (6, 8), (9, 11), (12, 14), (15, 17), (18, 20), (21, 23))
IGNORAR_H = 24             # o pico de estreia diz a hora da publicação, não a do público
BURACO_MAX_H = 6           # diferença entre leituras mais larga que isso não dá para atribuir a uma hora
MIN_VIDEOS = 8             # menos que isto é curva de um canal só, não hábito de público
MIN_HORAS = 200            # horas de curva somadas: abaixo disso o histograma é ruído
FUSO_PADRAO = -180         # Brasília, o mesmo do banco.BRASILIA


def _hora_utc(quando: str) -> datetime | None:
    """A `leituras.quando` é a hora UTC cortada em 13 caracteres ("2026-10-25T14"), sem fuso escrito."""
    marca = metricas.data(quando)
    if marca and marca.tzinfo is None:
        return marca.replace(tzinfo=timezone.utc)
    return marca


def _do_video(leituras: list[dict], publicado: str, fuso_min: int) -> tuple[dict, float, int]:
    """Quanto este vídeo rendeu em cada (dia da semana, hora) local, pelas diferenças entre leituras vizinhas.

    Devolve as fatias, o total contado e quantas horas de curva entraram."""
    estreia = metricas.data(publicado)
    corte = estreia + timedelta(hours=IGNORAR_H) if estreia else None
    fuso = timezone(timedelta(minutes=fuso_min))
    fatias: dict[tuple[int, int], float] = {}
    total, horas = 0.0, 0
    pares = [(_hora_utc(l["quando"]), l["views"]) for l in leituras]
    pares = [(q, v) for q, v in pares if q and v is not None]
    for (antes, views_antes), (depois, views_depois) in zip(pares, pares[1:]):
        vao = round((depois - antes).total_seconds() / 3600)
        rendeu = views_depois - views_antes
        if vao < 1 or vao > BURACO_MAX_H or rendeu <= 0:
            continue                     # buraco largo, leitura repetida ou correção de views para baixo
        por_hora = rendeu / vao
        for passo in range(vao):
            hora = antes + timedelta(hours=passo)
            if corte and hora < corte:
                continue                 # ainda é estreia
            local = hora.astimezone(fuso)
            fatias[(local.weekday(), local.hour)] = fatias.get((local.weekday(), local.hour), 0.0) + por_hora
            total += por_hora
            horas += 1
    return fatias, total, horas


def matriz(videos: list[dict], fuso_min: int = FUSO_PADRAO) -> dict:
    """O histograma 7 x 24 das curvas. Função pura: cada vídeo é {"publicado", "leituras"}.

    Cada vídeo entra com peso 1 (a fatia dividida pelo total dele), para o que estourou não definir o canal."""
    somas = [[0.0] * 24 for _ in range(7)]
    contados, horas = 0, 0
    for v in videos:
        fatias, total, horas_do_video = _do_video(v.get("leituras") or [], v.get("publicado") or "", fuso_min)
        if total <= 0:
            continue
        for (dia, hora), valor in fatias.items():
            somas[dia][hora] += valor / total
        contados += 1
        horas += horas_do_video
    return {"matriz": somas, "videos": contados, "horas": horas}


def _faixas_do_dia(linha: list[float]) -> list[float]:
    return [sum(linha[inicio:fim + 1]) for inicio, fim in FAIXAS]


def faixas(somas: list[list[float]]) -> dict[str, list[float]]:
    """As 24 horas de cada dia viram 8 faixas de 3 horas, mais o "geral" somando a semana inteira."""
    por_dia = {DIAS[dia]: _faixas_do_dia(linha) for dia, linha in enumerate(somas)}
    por_dia["geral"] = [sum(por_dia[DIAS[dia]][i] for dia in range(7)) for i in range(len(FAIXAS))]
    return por_dia


def _em_parte(valores: list[float]) -> list[float]:
    """De soma crua para a parte de cada faixa, que é o que a barra desenha e o que compara entre canais."""
    total = sum(valores)
    return [round(v / total, 4) for v in valores] if total > 0 else [0.0] * len(valores)


def resumo(videos: list[dict], fuso_min: int = FUSO_PADRAO) -> dict:
    """O que o site e a extensão recebem. Sem curva suficiente, `suficiente` é falso e não há pico."""
    bruto = matriz(videos, fuso_min)
    por_dia = faixas(bruto["matriz"])
    partes = {dia: _em_parte(valores) for dia, valores in por_dia.items()}
    basta = bruto["videos"] >= MIN_VIDEOS and bruto["horas"] >= MIN_HORAS and sum(por_dia["geral"]) > 0
    ranking = sorted(
        [{"faixa": i, "inicio": FAIXAS[i][0], "fim": FAIXAS[i][1], "parte": parte}
         for i, parte in enumerate(partes["geral"])],
        key=lambda f: f["parte"], reverse=True)
    return {
        "suficiente": basta,
        "fuso_min": fuso_min,
        "videos": bruto["videos"],
        "horas": bruto["horas"],
        "minimo": {"videos": MIN_VIDEOS, "horas": MIN_HORAS},
        "dias": list(DIAS),
        "faixas": [list(f) for f in FAIXAS],
        "matriz": [[round(v, 5) for v in linha] for linha in bruto["matriz"]],
        "por_dia": partes,
        "pico": ranking[0] if basta else None,
        "ranking": ranking if basta else [],
        "ignorado_h": IGNORAR_H,
    }


def do_canal(canal_id: str, fuso_min: int = FUSO_PADRAO) -> dict:
    """O melhor horário deste canal, só do banco: nenhuma leitura nova da API do YouTube."""
    linhas = banco.todos(
        "SELECT l.video_id, v.publicado, l.quando, l.views FROM leituras l JOIN videos v ON v.id=l.video_id "
        "WHERE v.canal_id=? ORDER BY l.video_id, l.quando", canal_id)
    videos: dict[str, dict] = {}
    for l in linhas:
        v = videos.setdefault(l["video_id"], {"publicado": l["publicado"], "leituras": []})
        v["leituras"].append({"quando": l["quando"], "views": l["views"]})
    return resumo(list(videos.values()), fuso_min)
