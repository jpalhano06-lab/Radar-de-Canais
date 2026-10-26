"""A vida de um nicho: em que etapa cada canal está e como cada nicho se comporta inteiro.

Pedido do usuário em 2026-10-25, com duas telas do Dotti Finder na mão: a faixa "como um nicho nasce e morre" e a
lista de nichos em tabela. A ideia é a deles; a conta, os cortes e os nomes são nossos, feitos com o que o Radar
mede de verdade — a regra da casa continua valendo: nada de copiar código, texto ou visual de concorrente.

**A etapa é do canal, não do nicho.** O que se mede é há quanto tempo o canal publica (o `primeiro_video`), porque é
isso que diz se ainda dá para entrar: um canal de 3 semanas que já faz view mostra que o formato pega e que quase
ninguém está nele; um de dois anos mostra um lugar com fila. Somando os canais de um recorte sai a faixa da tela.

Os cortes saem do que o próprio Radar vê nos canais dele (o `metricas.fase` já trabalha com 90 e 180 dias, e o
garimpo chama de "novo" o canal com menos de um ano):

- **Testando** (até 30 dias): o canal ainda está descobrindo o formato. Quase nenhum vive.
- **Decolando** (1 a 3 meses): passou do teste e o YouTube ainda está distribuindo.
- **Disputando** (3 a 6 meses): já apareceu gente fazendo igual.
- **Firme** (6 meses a 2 anos): o nicho tem dono, e entrar agora é brigar com quem tem acervo.
- **Veterano** (mais de 2 anos): o canal é um monumento; o nicho está saturado ou vive de marca.

O veredito de cada etapa (`entrar`, `apertado`, `tarde`) é **da etapa**, não do canal: diz o que significa, para quem
está procurando onde entrar, achar muitos canais ali. E a média de views do mês é a conta honesta do que aqueles
canais estão de fato colhendo agora — soma das views dos vídeos que eles publicaram nos últimos 30 dias, dividida
pelos canais que publicaram. Canal que não publicou não entra na média (senão a média viraria uma conta sobre
quem parou).
"""
from datetime import datetime, timedelta, timezone

from . import banco, mercado, metricas

# chave, nome, de (dias, entra), até (dias, NÃO entra; None = sem fim), veredito, o que significa.
# As faixas são coladas de propósito: a idade vem em dias quebrados, e com 0-30 e 31-90 o canal de 30 dias e meio
# não caía em etapa nenhuma — some da faixa e a conta não bate com a lista que ela abre.
ETAPAS = [
    ("testando", "Testando", 0, 30, "entrar", "O canal ainda está vendo se o formato pega. Muitos somem."),
    ("decolando", "Decolando", 30, 90, "entrar", "Passou do teste e o YouTube ainda distribui para quem chega."),
    ("disputando", "Disputando", 90, 180, "apertado", "Já tem gente fazendo igual. Dá para entrar com diferença."),
    ("firme", "Firme", 180, 730, "tarde", "O nicho tem dono e acervo. Entrar agora é brigar de igual para igual."),
    ("veterano", "Veterano", 730, None, "tarde", "Canal antigo, nicho maduro: vive de marca e de biblioteca."),
]
VEREDITOS = {"entrar": "Janela aberta", "apertado": "Já tem fila", "tarde": "Tarde para entrar"}
MES_DIAS = 30


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _corte(dias: float) -> str:
    return (_agora() - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%S")


def etapa_do_canal(primeiro_video: str, agora: datetime | None = None) -> str:
    """A etapa pela idade de quem posta. Canal sem data de primeiro vídeo fica de fora (não dá para dizer)."""
    dias = metricas.dias_desde(primeiro_video, agora)
    if dias is None:
        return ""
    for chave, _nome, de, ate, _v, _o in ETAPAS:
        if dias >= de and (ate is None or dias < ate):
            return chave
    return ""


def limites(chave: str) -> tuple[int, int | None] | None:
    """De quantos a quantos dias de vida a etapa vai, para quem precisa filtrar canais por ela (a lista de
    vídeos da curva da vida). Chave que não existe devolve None: filtro nenhum em vez de lista vazia."""
    for ch, _nome, de, ate, _v, _o in ETAPAS:
        if ch == chave:
            return de, ate
    return None


def _views_do_mes(ids: list[str]) -> dict[str, int]:
    """As views que cada canal colheu no último mês: a soma dos vídeos que ele publicou nos últimos 30 dias.

    É o número que diz se o canal está colhendo agora, e não no ano passado. Vídeo novo ainda está subindo, mas
    como a conta é a mesma para todos os canais, a comparação entre etapas continua valendo."""
    if not ids:
        return {}
    saida: dict[str, int] = {}
    for pedaco in range(0, len(ids), 400):          # o SQLite tem teto de variáveis por consulta
        lote = ids[pedaco:pedaco + 400]
        for l in banco.todos(
                f"SELECT canal_id, SUM(views) AS v FROM videos WHERE canal_id IN ({','.join('?' * len(lote))}) "
                "AND publicado >= ? GROUP BY canal_id", *lote, _corte(MES_DIAS)):
            saida[l["canal_id"]] = int(l["v"] or 0)
    return saida


def _canais(nicho: str = "", idioma: str = "", piso: float = 0) -> list[dict]:
    """Os mesmos canais que a tela Canais lista: os do Radar, acima do piso de views por vídeo e fora dos nichos
    que pagam pouco. Se a conta olhasse outro conjunto, a faixa diria um número e a lista embaixo, outro."""
    onde, args = ["no_radar=1"], []
    if nicho:
        onde.append("nicho=?"); args.append(nicho)
    if idioma:
        onde.append("idioma=?"); args.append(idioma)
    if piso:
        onde.append("base_longos >= ?"); args.append(piso)
    return [c for c in banco.todos(f"SELECT * FROM canais WHERE {' AND '.join(onde)}", *args)
            if not mercado.irrelevante(c["nicho"], "")]


def linha_da_vida(nicho: str = "", idioma: str = "", piso: float = 0) -> dict:
    """A faixa das cinco etapas: quantos canais estão em cada uma e quanto eles colheram no último mês."""
    canais = _canais(nicho, idioma, piso)
    do_mes = _views_do_mes([c["id"] for c in canais])
    por_etapa: dict[str, list[dict]] = {chave: [] for chave, *_ in ETAPAS}
    for c in canais:
        etapa = etapa_do_canal(c["primeiro_video"])
        if etapa:
            por_etapa[etapa].append(c)
    etapas = []
    for chave, nome, de, ate, veredito, o_que in ETAPAS:
        do_grupo = por_etapa[chave]
        colhendo = [do_mes.get(c["id"], 0) for c in do_grupo if do_mes.get(c["id"])]
        etapas.append({
            "chave": chave, "nome": nome, "de": de, "ate": ate, "veredito": veredito,
            "veredito_nome": VEREDITOS[veredito], "o_que": o_que,
            "canais": len(do_grupo),
            "postando": len(colhendo),
            "views_mes": round(sum(colhendo) / len(colhendo)) if colhendo else 0,
            "crescendo": sum(1 for c in do_grupo if c["fase"] in ("crescendo", "nascendo")),
        })
    sem_data = sum(1 for c in canais if not etapa_do_canal(c["primeiro_video"]))
    return {"etapas": etapas, "canais": len(canais), "sem_data": sem_data,
            "topo": max((e["canais"] for e in etapas), default=0)}


def tabela(nicho: str = "", idioma: str = "", minimo: int = 1, piso: float = 0) -> dict:
    """Um nicho por linha: quantos canais, o tráfego típico de um vídeo, quantos pararam e o público do nicho.

    "Tráfego típico" é a **mediana** do normal por vídeo dos canais, não a média: um canal gigante no meio de
    pequenos puxaria a média e faria o nicho parecer o que ele não é."""
    canais = _canais(nicho, idioma, piso)
    do_mes = _views_do_mes([c["id"] for c in canais])
    por_nicho: dict[str, list[dict]] = {}
    for c in canais:
        por_nicho.setdefault(c["nicho"] or "(sem nicho)", []).append(c)
    linhas = []
    for nome, lista in por_nicho.items():
        if len(lista) < minimo:
            continue
        normais = sorted(c["base_longos"] or 0 for c in lista)
        colhendo = [do_mes.get(c["id"], 0) for c in lista if do_mes.get(c["id"])]
        linhas.append({
            "nicho": nome,
            "canais": len(lista),
            "tipico": round(normais[len(normais) // 2]),
            "parados": sum(1 for c in lista if c["fase"] in ("parado", "caindo")),
            "crescendo": sum(1 for c in lista if c["fase"] in ("crescendo", "nascendo")),
            "publico": sum(c["views_total"] or 0 for c in lista),
            "views_mes": sum(colhendo),
            "postando": len(colhendo),
            "novos": sum(1 for c in lista if etapa_do_canal(c["primeiro_video"]) in ("testando", "decolando")),
        })
    linhas.sort(key=lambda l: -l["tipico"])
    return {"nichos": linhas, "mes_dias": MES_DIAS}
