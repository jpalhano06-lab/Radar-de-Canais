"""O garimpo: procura canais novos que estão indo bem, mede, separa por nicho e marca os sem rosto.

Roda uma vez por dia sozinho (servidor) ou com `python -m radar garimpar`. Gasta só a parte da cota de hoje que
config.COTA_DO_GARIMPO deixa, e para quando ela acaba: o resto fica para a extensão."""
import json
import threading
from datetime import datetime, timedelta, timezone

from . import banco, gosto, ia, medir, mercado, metricas, risco, youtube
from .config import COTA_DO_GARIMPO, DADOS

# termos de partida por nicho. Um arquivo dados/termos.json ({"Nicho": ["termo", ...]}) soma ou troca estes.
# Os nichos e as buscas do garimpo (refeito em 2026-10-14, pedido do usuário: "buscas melhores e mais alinhadas, para
# que não gaste tantos créditos em lixo"; e depois: "carros, religioso... além do CPM, assuntos que engajam"). Só nichos
# que dão para fazer sem rosto, em inglês e no YouTube dos EUA, onde o CPM é maior e onde o Alerta procura. Saíram
# desenho animado, contos, boxe, futebol, mitologia e curiosidades (CPM baixo e nenhum canal para o Alerta nos 1.687
# vistos) e os termos em português e espanhol.
#
# NICHOS: nicho -> (CPM mínimo, CPM máximo em US$, engajamento de 1 a 3). O CPM é a faixa das pesquisas públicas de
# 2026 (vidIQ, upGrowth, OutlierKit, StreamerCalculator; estimativas, não dados do YouTube). O engajamento é a retenção
# e o tempo assistido que as mesmas fontes apontam: crimes reais, mistério, história e documentário seguram o
# espectador até o fim (3); finanças paga muito mas segura menos (2). Religião tem CPM baixo (US$ 3 a 8; o Google trata
# religião como categoria sensível para anúncio), mas audiência fiel e enorme: entra pelo engajamento.
NICHOS = {
    "Finanças": (15, 50, 2), "Direito": (10, 35, 2), "Imóveis": (8, 30, 2), "Economia": (10, 30, 2),
    "Negócios": (10, 30, 2), "Tecnologia": (8, 25, 2), "Ciência": (5, 25, 3), "Carros": (4, 25, 2),
    "Saúde": (6, 22, 2), "Bilionários": (7, 16, 2), "Geopolítica": (6, 14, 3), "História": (6, 14, 3),
    "Espaço": (5, 12, 3), "Crimes Reais": (4, 10, 3), "Mistério": (4, 10, 3), "Psicologia": (4, 9, 3),
    "Animais": (5, 9, 3), "Vida Selvagem": (5, 9, 3), "Religião": (3, 8, 3),
}


def prioridade(nicho: str) -> float:
    """CPM médio do nicho, com até 50% a mais pelo engajamento: o que paga bem E segura o espectador vem primeiro."""
    if nicho not in NICHOS:
        return 0.0 if mercado.irrelevante(nicho) else 8.0     # nicho novo, fora da lista: entra, depois dos da lista
    minimo, maximo, engaja = NICHOS[nicho]
    return (minimo + maximo) / 2 * (1 + 0.25 * (engaja - 1))


CPM = {n: ("alto" if (a + b) / 2 >= 15 else "medio") for n, (a, b, _) in NICHOS.items()}

TERMOS = {
    "Finanças": ["personal finance explained", "money mistakes to avoid", "how the rich avoid taxes",
                 "retirement planning explained", "credit score explained", "stock market explained"],
    "Direito": ["court cases explained", "lawsuit explained", "scams exposed documentary"],
    "Imóveis": ["real estate explained", "housing crisis explained", "why houses are so expensive"],
    "Economia": ["economy explained", "why everything is getting more expensive", "recession explained"],
    "Negócios": ["business documentary", "how companies make money", "rise and fall of a company",
                 "why this company failed"],
    "Tecnologia": ["artificial intelligence explained", "tech documentary", "how it works engineering"],
    "Ciência": ["science explained", "what if scenarios science", "engineering explained", "how things are made"],
    "Carros": ["car buying mistakes", "why this car failed", "car brands explained", "luxury cars explained"],
    "Saúde": ["what happens to your body if", "medical mysteries explained", "how the human body works"],
    "Bilionários": ["billionaire lifestyle documentary", "how billionaires spend their money", "most expensive things"],
    "Geopolítica": ["geopolitics explained", "why this country is so rich", "countries explained"],
    "História": ["history documentary", "ancient civilizations explained", "history of everyday things"],
    "Espaço": ["space documentary", "black hole explained"],
    "Crimes Reais": ["true crime documentary", "unsolved cases documentary"],
    "Mistério": ["unsolved mysteries", "mysteries explained", "strange disappearances"],
    "Psicologia": ["psychology explained", "dark psychology"],
    "Animais": ["strangest animals", "deadliest animals"],
    "Vida Selvagem": ["wildlife documentary", "predators of africa"],
    "Religião": ["bible stories explained", "bible mysteries explained", "christian documentary", "jesus history"],
}

LINGUA = "en"
PAISES_ACEITOS = mercado.ACEITOS   # canal de fora dos países de língua inglesa nem é medido
LIXO_DEPOIS = 2            # termo que rendeu 0 canais em 2 buscas seguidas fica de lado por LIXO_DIAS
LIXO_DIAS = 30

DIAS_DO_VIDEO = 30         # a busca olha vídeos publicados no último mês
REBUSCAR_DIAS = 3          # o mesmo termo só é buscado de novo depois de 3 dias
CANAL_ATE_MESES = 18       # canal novo: começou a postar há até 18 meses
MINIMO_POR_VIDEO = 10_000  # views por vídeo (mediana dos longos) para entrar no Radar
NOTA_OUTLIER = 3.0         # vídeo com 3 vezes o normal entra no banco (a tela de Outliers mostra 5x ou mais por padrão)

_RODANDO = threading.Lock()


def termos() -> dict[str, list[str]]:
    lista = {k: list(v) for k, v in TERMOS.items()}
    extra = DADOS / "termos.json"
    if extra.exists():
        try:
            for nicho, ts in json.loads(extra.read_text(encoding="utf-8")).items():
                lista.setdefault(nicho, [])
                lista[nicho] += [t for t in ts if t not in lista[nicho]]
        except ValueError:
            pass
    # os termos que o garimpo aprendeu com os títulos que estouraram
    for a in banco.todos("SELECT termo, nicho FROM termos_auto"):
        lista.setdefault(a["nicho"] or "Outro", [])
        if a["termo"] not in lista[a["nicho"] or "Outro"]:
            lista[a["nicho"] or "Outro"].append(a["termo"])
    return lista


def _rendeu(b: dict) -> float:
    """Canais por busca que o termo já trouxe (o que não rendeu nada vai para o fim)."""
    return (b.get("total") or 0) / max(1, b.get("vezes") or 0)


def _proximos_termos() -> list[tuple[str, str]]:
    """Um termo de cada nicho por vez, os de CPM alto primeiro. Dentro do nicho: os nunca buscados, depois os que mais
    renderam. Termo que rendeu 0 canais nas últimas LIXO_DEPOIS buscas fica de lado por LIXO_DIAS (era lixo)."""
    feitos = {b["termo"]: b for b in banco.todos("SELECT * FROM buscas_feitas")}
    agora = datetime.now(timezone.utc)
    limite = (agora - timedelta(days=REBUSCAR_DIAS)).isoformat()
    limite_lixo = (agora - timedelta(days=LIXO_DIAS)).isoformat()

    def livre(t):
        b = feitos.get(t)
        if not b:
            return True
        if (b.get("zeros") or 0) >= LIXO_DEPOIS and b["quando"] >= limite_lixo:
            return False
        return b["quando"] < limite
    por_nicho = []
    nichos = sorted(termos().items(), key=lambda kv: -prioridade(kv[0]) if kv[0] != "Procurados" else -100)
    for nicho, ts in nichos:
        if mercado.irrelevante(nicho):
            continue        # nicho que paga pouco ou de histórias narradas não gasta busca (mercado.IRRELEVANTES)
        # termo aprendido em português ou espanhol não vai para o YouTube dos EUA
        livres = sorted((t for t in ts if livre(t) and (nicho == "Procurados" or gosto.lingua(t) not in ("pt", "es"))), key=lambda t: (t in feitos, -_rendeu(feitos.get(t, {}))))
        por_nicho.append([(nicho, t) for t in livres])
    # cada rodada dá mais buscas a quem paga mais e engaja mais: finanças 3, direito 2, religião 1
    ordem = []
    while any(por_nicho):
        for fila in por_nicho:
            vezes = max(1, round(prioridade(fila[0][0]) / 14)) if fila else 0
            for _ in range(vezes):
                if fila:
                    ordem.append(fila.pop(0))
    return ordem


def _avaliar(ids: list[str], log, contagem: dict, rapido: bool = False) -> list[str]:
    """Mede os canais novos e põe no Radar os que passam. Devolve os que entraram."""
    conhecidos = {c["id"]: c for c in medir._canais_do_banco(ids)}
    # canal já medido nesta semana não é lido de novo
    semana = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    novos = [i for i in ids if i not in conhecidos or conhecidos[i]["medido"] < semana]
    if not novos:
        return []
    # filtro barato primeiro (1 unidade a cada 50): canal criado há pouco e com poucos vídeos
    candidatos = []
    limite = (datetime.now(timezone.utc) - timedelta(days=CANAL_ATE_MESES * 31)).isoformat()
    for c in youtube.canais(novos):
        if (c["criado_em"] or "") >= limite and 3 <= (c["videos_total"] or 0) <= 400 and (c.get("pais") or "") in PAISES_ACEITOS:
            candidatos.append(c["id"])
        else:
            banco.gravar("canais", "id", {"id": c["id"], "titulo": c["titulo"], "medido": banco.agora()})
    entraram = [cid for cid, c in medir.medir_canais(candidatos, forcar=True, origem="garimpo").items()
                if _passa(c) and _entrar(c, rapido=rapido)]
    contagem["novos"] += len(entraram)
    if entraram:
        log(f"{len(entraram)} canais novos no Radar")
    return entraram


def _passa(c: dict) -> bool:
    """A porta do Radar, com o canal já medido: até 18 meses postando, e o normal de 10 mil OU ter explodido agora.

    A segunda porta é de 2026-10-25: o canal dark que estourou tem dois ou três vídeos enormes e o resto pequeno, a
    mediana fica baixa e ele era mandado embora (146 assim no banco do usuário). A régua está em metricas.explodiu."""
    if not (3 <= (c["videos_total"] or 0) <= 400 and (c.get("pais") or "") in PAISES_ACEITOS):
        return False
    meses = metricas.meses_postando(c["primeiro_video"])
    if meses is None or meses > CANAL_ATE_MESES:
        return False
    if (c["base_longos"] or 0) >= MINIMO_POR_VIDEO:
        return True
    videos = banco.todos("SELECT views, duracao_s, publicado FROM videos WHERE canal_id=?", c["id"])
    return metricas.explodiu(videos, c["primeiro_video"], c["base_longos"])


def _entrar(c: dict, rapido: bool = False) -> bool:
    """O corte do risco e depois o nicho e o rosto (_completar). Devolve se o canal ficou no Radar."""
    titulos = [v["titulo"] for v in banco.todos(
        "SELECT titulo FROM videos WHERE canal_id=? ORDER BY publicado DESC LIMIT 20", c["id"])]
    if risco.avaliar(titulos):
        return False      # canal com risco de desmonetização (reaproveitado, em série...) não entra no Radar
    return _completar(c, rapido=rapido)


def _completar(c: dict, rapido: bool = False) -> None:
    """Nicho, sem rosto e outliers de um canal que entrou.

    rapido: a procura que a pessoa espera na tela não pergunta ao Groq (que pode levar um minuto esperando o limite);
    o nicho e o rosto ficam para o próximo garimpo (completar_pendentes)."""
    videos = banco.todos("SELECT id, titulo, views, duracao_s, publicado FROM videos WHERE canal_id=? "
                         "ORDER BY views DESC LIMIT 15", c["id"])
    dados = {"id": c["id"], "no_radar": 1}
    if not rapido and (not c["nicho"] or not c.get("subnicho")):
        existentes = [l["subnicho"] for l in banco.todos(
            "SELECT subnicho, COUNT(*) AS n FROM canais WHERE no_radar=1 AND subnicho<>'' AND id<>? "
            "GROUP BY subnicho ORDER BY n DESC LIMIT 80", c["id"])]
        nicho, subnicho = ia.nicho(c["titulo"], [v["titulo"] for v in videos], existentes)
        if nicho and not c["nicho"]:
            dados["nicho"] = nicho
        if subnicho:
            dados["subnicho"] = subnicho
    if not rapido and c["sem_rosto"] is None:
        resposta = ia.sem_rosto([f"https://i.ytimg.com/vi/{v['id']}/default.jpg" for v in videos[:3]])
        if resposta is not None:
            dados["sem_rosto"] = int(resposta)
    nicho_final, sub_final = dados.get("nicho") or c["nicho"], dados.get("subnicho") or c.get("subnicho")
    if mercado.irrelevante(nicho_final, sub_final):
        dados["no_radar"] = 0       # paga pouco ou é de histórias narradas: medido, mas fora do Radar
    # canal com rosto fica de fora: o Radar é de canal dark (pedido do usuário, 2026-10-25). O rosto não é sabido
    # antes de medir, então o canal é medido e só depois cai fora — a medida não se perde, ele fica no banco.
    # `None` (o Groq não respondeu) continua entrando: não sabido não é o mesmo que tem rosto.
    rosto_final = dados.get("sem_rosto", c["sem_rosto"])
    if rosto_final == 0:
        dados["no_radar"] = 0
    banco.gravar("canais", "id", dados)
    for v in videos:
        normal = c["base_curtos"] if metricas.curto(v["duracao_s"]) else c["base_longos"]
        nota = metricas.nota_outlier(v["views"], normal)
        if nota and nota >= NOTA_OUTLIER:
            banco.executar("INSERT OR REPLACE INTO outliers (video_id, canal_id, nota, achado) VALUES (?,?,?,?)",
                           v["id"], c["id"], nota, banco.agora())
    return dados["no_radar"] == 1


@youtube.por("garimpo")
def completar_pendentes(log=print, quantos: int = 80) -> int:
    """Canais do Radar sem nicho ou sem a resposta do rosto (o Groq estava fora, por exemplo). Não gasta cota."""
    pendentes = banco.todos("SELECT * FROM canais WHERE no_radar=1 AND (sem_rosto IS NULL OR nicho='' OR subnicho='') "
                            "LIMIT ?", quantos)
    for c in pendentes:
        _completar(c)
    if pendentes:
        log(f"{len(pendentes)} canais do Radar completados (nicho e rosto)")
    return len(pendentes)


REMEDIR_HORAS = 20         # canal do Radar ou salvo é medido de novo uma vez por dia
FRACAO_REMEDIR = 0.35      # até 35% da cota do garimpo vai para medir de novo (em alta, novidades)


@youtube.por("garimpo")
def remedir(log, orcamento: int) -> int:
    """Mede de novo os canais do Radar e os salvos: é o que mostra quem está em alta e os vídeos novos da sua base.
    Cada canal custa umas 3 unidades. Os salvos vão primeiro."""
    limite = (datetime.now(timezone.utc) - timedelta(hours=REMEDIR_HORAS)).isoformat()
    ids = [c["canal_id"] for c in banco.todos(
        "SELECT DISTINCT m.canal_id FROM meus_canais m JOIN canais c ON c.id=m.canal_id WHERE c.medido < ?", limite)]
    ids += [c["canal_id"] for c in banco.todos(
        "SELECT DISTINCT s.canal_id FROM salvos s JOIN canais c ON c.id=s.canal_id WHERE c.medido < ?", limite)
        if c["canal_id"] not in ids]
    ids += [c["id"] for c in banco.todos("SELECT id FROM canais WHERE no_radar=1 AND medido < ? ORDER BY medido",
                                         limite) if c["id"] not in ids]
    inicio, feitos = youtube.cota_hoje()["usado"], 0
    for i in range(0, len(ids), 20):
        if youtube.cota_hoje()["usado"] - inicio + 70 > orcamento:
            break
        lote = ids[i:i + 20]
        for c in medir.medir_canais(lote, forcar=True).values():
            if c["no_radar"]:
                _completar(c)
        feitos += len(lote)
    if feitos:
        log(f"{feitos} canais medidos de novo (em alta e novidades)")
    return feitos


REPESCAR_POR_VEZ = 40      # por garimpo: cada um é uma pergunta de rosto e uma de nicho ao Groq, que tem limite por minuto
REPESCAR_DE_NOVO_DIAS = 7  # repescado e barrado (risco, Groq fora...), o canal espera a semana
FRACAO_REPESCAR = 0.15     # até 15% da cota do garimpo (uns 3 unidades por canal)


@youtube.por("garimpo")
def repescar(log, orcamento: int) -> int:
    """Os canais que já estão no banco e explodiram, mas nunca foram julgados: a extensão guardou o canal enquanto a
    pessoa navegava, ou o garimpo mediu antes da porta do "explodiu" existir. Não gasta busca.

    Nunca julgado é `sem_rosto` nulo: quem o Groq já viu com rosto não volta. Criado há até 18 meses pelo `criado_em`,
    porque o primeiro vídeo de quem passou pela extensão é o mais velho que ela viu (Felipe Neto passava por canal de
    outubro). Os que mais somaram nos 30 dias primeiro; cada um é medido de novo e passa pela mesma porta do garimpo."""
    agora = datetime.now(timezone.utc)
    criado = (agora - timedelta(days=CANAL_ATE_MESES * 31)).isoformat()
    de_novo = (agora - timedelta(days=REPESCAR_DE_NOVO_DIAS)).isoformat()
    recentes = (agora - timedelta(days=metricas.EXPLODIU_DIAS)).isoformat()
    fila = []
    for c in banco.todos("SELECT * FROM canais WHERE no_radar=0 AND sem_rosto IS NULL AND criado_em<>'' "
                         "AND criado_em >= ? AND repescado < ?", criado, de_novo):
        if mercado.irrelevante(c["nicho"], c.get("subnicho")):
            continue
        if not (3 <= (c["videos_total"] or 0) <= 400 and (c.get("pais") or "") in PAISES_ACEITOS):
            continue      # o país e a contagem já estão no banco: medir de novo só para cair no _passa gastava cota
        videos = banco.todos("SELECT views, duracao_s, publicado FROM videos WHERE canal_id=?", c["id"])
        if metricas.explodiu(videos, c["primeiro_video"], c["base_longos"]):
            soma = sum(v["views"] or 0 for v in videos
                       if not metricas.curto(v["duracao_s"]) and (v["publicado"] or "") >= recentes)
            fila.append((soma, c["id"]))
    fila.sort(reverse=True)
    inicio, entraram, medidos = youtube.cota_hoje()["usado"], 0, 0
    for _, cid in fila[:REPESCAR_POR_VEZ]:
        if youtube.cota_hoje()["usado"] - inicio + 10 > orcamento:
            break
        c = medir.medir_canais([cid], forcar=True).get(cid)
        banco.gravar("canais", "id", {"id": cid, "repescado": banco.agora()})
        medidos += 1
        if c and _passa(c) and _entrar(c):
            entraram += 1
    if medidos:
        log(f"{medidos} canais repescados do banco (explodiram), {entraram} entraram no Radar")
    return entraram


MAX_TERMOS_AUTO = 400


@youtube.por("garimpo")
def aprender_termos(log, nichos_por_vez: int = 5) -> int:
    """Os títulos que estouraram viram buscas novas: o garimpo vai achando sozinho onde mais procurar."""
    if banco.um("SELECT COUNT(*) AS n FROM termos_auto")["n"] >= MAX_TERMOS_AUTO:
        return 0
    semana = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    nichos = banco.todos(
        "SELECT c.nicho, COUNT(*) AS n FROM outliers o JOIN canais c ON c.id=o.canal_id WHERE o.achado >= ? "
        f"AND c.nicho NOT IN ({','.join('?' * len(mercado.IRRELEVANTES))}) GROUP BY c.nicho ORDER BY n DESC LIMIT ?",
        semana, *mercado.IRRELEVANTES, nichos_por_vez)
    novos = 0
    for n in nichos:
        titulos = [v["titulo"] for v in banco.todos(
            "SELECT v.titulo FROM outliers o JOIN videos v ON v.id=o.video_id JOIN canais c ON c.id=o.canal_id "
            "WHERE c.nicho=? ORDER BY o.achado DESC, o.nota DESC LIMIT 20", n["nicho"])]
        for termo in ia.sugerir_termos(n["nicho"], titulos):
            if not banco.um("SELECT 1 AS x FROM termos_auto WHERE lower(termo)=lower(?)", termo):
                banco.executar("INSERT OR IGNORE INTO termos_auto (termo, nicho, origem, criado) VALUES (?,?,?,?)",
                               termo, n["nicho"], "outliers", banco.agora())
                novos += 1
    if novos:
        log(f"{novos} buscas novas aprendidas com os vídeos que estouraram")
    return novos


@youtube.por("garimpo")
def rodar(log=print, unidades: int | None = None) -> dict:
    if not _RODANDO.acquire(blocking=False):
        return {"ok": False, "motivo": "Já tem um garimpo rodando."}
    gid = banco.executar("INSERT INTO garimpos (inicio) VALUES (?)", banco.agora())
    linhas = []

    def anotar(texto):
        linhas.append(f"{datetime.now().strftime('%H:%M:%S')} {texto}")
        banco.executar("UPDATE garimpos SET linhas=? WHERE id=?", json.dumps(linhas[-200:], ensure_ascii=False), gid)
        log(texto)

    contagem = {"novos": 0, "buscas": 0}
    inicio = youtube.cota_hoje()["usado"]
    orcamento = unidades if unidades is not None else int(youtube.cota_hoje()["livre"] * COTA_DO_GARIMPO)
    estado = "pronto"
    try:
        anotar(f"Garimpo começou com {orcamento} unidades de cota.")
        completar_pendentes(anotar)
        remedir(anotar, int(orcamento * FRACAO_REMEDIR))
        repescar(anotar, int(orcamento * FRACAO_REPESCAR))
        depois = (datetime.now(timezone.utc) - timedelta(days=DIAS_DO_VIDEO)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for n, (nicho, termo) in enumerate(_proximos_termos()):
            if youtube.cota_hoje()["usado"] - inicio + 110 > orcamento:
                anotar("A parte da cota do garimpo acabou por hoje.")
                break
            # em inglês, nos países de língua inglesa (os EUA em duas de cada três buscas): o CPM é maior lá
            busca = termo if gosto.lingua(termo) not in ("pt", "es") else (ia.traduzir_titulo(termo, ["en"]).get("en") or termo)
            achados = youtube.buscar(busca, publicado_depois=depois, duracao="medium" if n % 2 else "long",
                                     regiao=mercado.regiao(n), idioma=LINGUA)
            contagem["buscas"] += 1
            ids = list(dict.fromkeys(a["canal_id"] for a in achados))
            entraram = _avaliar(ids, anotar, contagem)
            # quanto cada termo rende, para o próximo garimpo gastar nos que trazem canal e largar o lixo
            antes = banco.um("SELECT vezes, total, zeros FROM buscas_feitas WHERE termo=?", termo) or {}
            banco.executar("INSERT OR REPLACE INTO buscas_feitas (termo, nicho, quando, canais, vezes, total, zeros) "
                           "VALUES (?,?,?,?,?,?,?)", termo, nicho, banco.agora(), len(entraram),
                           (antes.get("vezes") or 0) + 1, (antes.get("total") or 0) + len(entraram),
                           0 if entraram else (antes.get("zeros") or 0) + 1)
            # "Procurados" é a lista das procuras da pessoa, não um nicho: o nicho desses fica com o Groq
            for cid in entraram if nicho != "Procurados" else []:
                banco.executar("UPDATE canais SET nicho=COALESCE(NULLIF(nicho,''), ?) WHERE id=?", nicho, cid)
            anotar(f"[{nicho}] \"{termo}\": {len(ids)} canais vistos, {len(entraram)} entraram")
        achar_parecidos_dos_salvos(anotar, orcamento - (youtube.cota_hoje()["usado"] - inicio), contagem)
        aprender_termos(anotar)
    except youtube.SemCota as erro:
        anotar(str(erro))
    except Exception as erro:  # o garimpo nunca derruba o servidor
        estado = "erro"
        anotar(f"Erro: {erro}")
    finally:
        gasto = youtube.cota_hoje()["usado"] - inicio
        banco.executar("UPDATE garimpos SET fim=?, unidades=?, buscas=?, canais_novos=?, estado=? WHERE id=?",
                       banco.agora(), gasto, contagem["buscas"], contagem["novos"], estado, gid)
        _RODANDO.release()
    anotar(f"Fim: {contagem['buscas']} buscas, {contagem['novos']} canais novos, {gasto} unidades.")
    return {"ok": True, "id": gid, **contagem, "unidades": gasto}


# ---------------------------------------------------------------- gastar tudo (o botão do menu, antes de desligar o PC)

GASTANDO = {"rodando": False, "inicio": 0, "orcamento": 0}


@youtube.por("garimpo")
def gastar_tudo(log=print) -> None:
    """Usa toda a cota livre de hoje: o garimpo com 100% e, se os termos acabarem antes (cada um só volta depois de
    3 dias), procuras com termos sorteados dos nichos, de jeitos diferentes, até sobrar menos que uma busca."""
    import random
    from . import perfil
    if GASTANDO["rodando"]:
        return
    cota = youtube.cota_hoje()
    GASTANDO.update(rodando=True, inicio=cota["usado"], orcamento=cota["livre"])
    try:
        rodar(log, unidades=cota["livre"])
        lista = [t for ts in termos().values() for t in ts]
        for _ in range(200):
            if youtube.cota_hoje()["livre"] < 260 or not lista:
                break
            try:
                perfil.procurar(random.choice(lista), random.randrange(len(perfil.JEITOS)))
            except youtube.SemCota:
                break
            except Exception as erro:   # um termo ruim não para o resto
                log(f"procura extra falhou: {erro}")
        completar_pendentes(log)
    finally:
        GASTANDO["rodando"] = False


def estado_gasto() -> dict:
    cota = youtube.cota_hoje()
    rodando = GASTANDO["rodando"] or _RODANDO.locked()
    ultimo = banco.um("SELECT inicio FROM garimpos ORDER BY id DESC LIMIT 1")
    return {**cota, "garimpando": rodando, "ultimo_garimpo": ultimo["inicio"] if ultimo else "",
            # em que a cota de hoje foi gasta, para a tela não só dizer quanto sobrou mas onde foi
            "motivos": [{**m, "rotulo": youtube.MOTIVOS.get(m["motivo"], m["motivo"])}
                        for m in youtube.gasto_por_motivo()],
            "gasto": max(0, cota["usado"] - GASTANDO["inicio"]) if GASTANDO["rodando"] else 0,
            "orcamento": GASTANDO["orcamento"] if GASTANDO["rodando"] else 0}


# ---------------------------------------------------------------- canais parecidos

def _busca_do_canal(canal_id: str) -> list[str]:
    """Os títulos dos vídeos que mais renderam: são a melhor busca para achar quem faz o mesmo."""
    return [v["titulo"] for v in banco.todos(
        "SELECT titulo FROM videos WHERE canal_id=? AND duracao_s>180 ORDER BY views DESC LIMIT 2", canal_id)]


@youtube.por("garimpo")
def parecidos(canal_id: str, guardar_no_radar: bool = True) -> list[dict]:
    """Canais que fazem o mesmo tipo de vídeo, do mais parecido para o menos (100 a 200 unidades, guardado 7 dias)."""
    cache = banco.um("SELECT dados, criado FROM traducoes WHERE chave=?", f"parecidos:{canal_id}")
    semana = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    if cache and cache["criado"] >= semana:
        ids = json.loads(cache["dados"])
    else:
        medir.medir_canais([canal_id])
        vistos = {}
        for titulo in _busca_do_canal(canal_id):
            for posicao, a in enumerate(youtube.buscar(titulo, ordem="relevance")):
                if a["canal_id"] != canal_id:
                    vistos[a["canal_id"]] = vistos.get(a["canal_id"], 0) + (50 - posicao)
        ids = [c for c, _ in sorted(vistos.items(), key=lambda x: -x[1])][:25]
        banco.executar("INSERT OR REPLACE INTO traducoes (chave, dados, criado) VALUES (?,?,?)",
                       f"parecidos:{canal_id}", json.dumps(ids), banco.agora())
    canais = medir.medir_canais(ids)
    saida = []
    for cid in ids:
        if cid in canais:
            saida.append(medir._canal_publico(canais[cid]))
    return saida


def _parecidos_guardados(canal_id: str) -> bool:
    """A lista de parecidos deste canal já foi procurada nos últimos 7 dias (ler de novo não gasta cota)."""
    cache = banco.um("SELECT criado FROM traducoes WHERE chave=?", f"parecidos:{canal_id}")
    return bool(cache and cache["criado"] >= (datetime.now(timezone.utc) - timedelta(days=7)).isoformat())


@youtube.por("garimpo")
def concorrentes(canal_id: str, medir_agora: bool = False) -> dict:
    """Os concorrentes do nicho (os canais parecidos) e a nota do nicho, de 0 (lotado) a 10 (fácil de entrar).

    A nota soma três coisas que se explicam sozinhas: quantos concorrentes estão crescendo (há procura, até 5 pontos),
    quantos canais novos (até 6 meses) já fazem 10 mil por vídeo (dá para entrar, até 3) e quantos postaram no último
    mês (quanto menos, mais espaço, até 2). Procurar os parecidos gasta cota: sem a lista guardada, só se pedido."""
    if not medir_agora and not _parecidos_guardados(canal_id):
        return {"medido": False}
    canais = medir._canais_do_banco([c["id"] for c in parecidos(canal_id)])
    dias = lambda d: metricas.dias_desde(d or "")   # noqa: E731
    ativos = [c for c in canais if (dias(c["ultimo_video"]) or 1e9) <= 30]
    crescendo = [c for c in canais if c["fase"] in ("crescendo", "nascendo")]
    novos_ok = [c for c in canais if (dias(c["primeiro_video"]) or 1e9) <= 180 and (c["base_longos"] or 0) >= 10_000]
    total = len(canais)
    nota = (5 * (len(crescendo) / total if total else 0) + 3 * min(1, len(novos_ok) / 3)
            + 2 * (1 - min(1, len(ativos) / 20)))
    nota = round(nota, 1)
    rotulo = "fácil de entrar" if nota >= 7 else "dá para entrar com um bom título" if nota >= 4 else "nicho lotado"
    lista = sorted(canais, key=lambda c: -(c["base_longos"] or 0))[:6]
    return {"medido": True, "total": total, "ativos": len(ativos), "crescendo": len(crescendo),
            "novos_que_deram_certo": len(novos_ok), "nota": nota, "rotulo": rotulo,
            "canais": [medir._canal_publico(c) for c in lista]}


@youtube.por("canal")
def ultimos_videos(canal_id: str, quantos: int = 6) -> list[dict]:
    """Os vídeos longos mais novos do canal com a nota (do banco, sem cota): ao lado de cada canal parecido."""
    achado = medir._canais_do_banco([canal_id])
    normal = achado[0]["base_longos"] if achado else None
    videos = banco.todos("SELECT id, titulo, views, publicado, duracao_s FROM videos WHERE canal_id=? AND publicado<>'' "
                         "ORDER BY publicado DESC LIMIT ?", canal_id, quantos * 3)
    saida = [v for v in videos if not metricas.curto(v["duracao_s"])][:quantos]
    for v in saida:
        v["nota"] = metricas.nota_outlier(v["views"], normal) if normal else None
    return saida


@youtube.por("canal")
def videos_do_nicho(canal_id: str, quantos: int = 24, dias: int = 365) -> list[dict]:
    """A aba Vídeos do Nicho da extensão: os vídeos longos que passaram do normal (2x ou mais) nos canais parecidos,
    do maior estouro para o menor. Os vídeos vêm do banco; só os parecidos podem gastar cota (guardados 7 dias)."""
    ids = [c["id"] for c in parecidos(canal_id)]
    canais = {c["id"]: c for c in medir._canais_do_banco(ids)}
    if not canais:
        return []
    corte = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    videos = banco.todos(f"SELECT id, titulo, views, publicado, duracao_s, canal_id FROM videos WHERE canal_id IN "
                         f"({','.join('?' * len(canais))}) AND publicado>=?", *canais, corte)
    saida = []
    for v in videos:
        c = canais[v["canal_id"]]
        if metricas.curto(v["duracao_s"]) or not c["base_longos"]:
            continue
        v["nota"] = metricas.nota_outlier(v["views"], c["base_longos"])
        if v["nota"] and v["nota"] >= 2:
            saida.append({**v, "canal": c["titulo"], "foto": c["foto"], "inscritos": c["inscritos"]})
    return sorted(saida, key=lambda v: -v["nota"])[:quantos]


def achar_parecidos_dos_salvos(log, orcamento: int, contagem: dict) -> None:
    """Cada canal salvo procura os parecidos uma vez por semana, e os bons vão para os Achados de quem salvou."""
    semana = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    salvos = banco.todos("SELECT usuario_id, canal_id FROM salvos WHERE procurado < ? ORDER BY procurado LIMIT 50",
                         semana)
    gasto_inicio = youtube.cota_hoje()["usado"]
    for s in salvos:
        if youtube.cota_hoje()["usado"] - gasto_inicio + 220 > orcamento:
            break
        novos = 0
        for c in parecidos(s["canal_id"]):
            if (c["normal_longos"] or 0) >= MINIMO_POR_VIDEO:
                ja = banco.um("SELECT 1 AS x FROM salvos WHERE usuario_id=? AND canal_id=?", s["usuario_id"], c["id"])
                if not ja:
                    banco.executar("INSERT OR IGNORE INTO achados (usuario_id, canal_id, por_causa_de, criado) "
                                   "VALUES (?,?,?,?)", s["usuario_id"], c["id"], s["canal_id"], banco.agora())
                    novos += 1
        banco.executar("UPDATE salvos SET procurado=? WHERE usuario_id=? AND canal_id=?",
                       banco.agora(), s["usuario_id"], s["canal_id"])
        if novos:
            log(f"Um canal salvo achou {novos} parecidos")
