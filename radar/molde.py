"""O molde de um título: a estrutura dele, sem o assunto.

"Why Nobody Talks About Tesla Anymore" e "Why Nobody Talks About Rome Anymore" são o mesmo molde. Ficam as palavras de
ligação e os números viram #; o resto (o assunto) vira _. Com o molde guardado em cada vídeo, dá para ver quem mais
escreve assim e quanto rende: a mediana de quantas vezes o normal do canal.

O molde dos vídeos antigos é preenchido aos poucos, por `iniciar`. A coluna vazia só quer dizer que ainda não chegou lá.
"""
import re
import threading
import time
from statistics import median

from . import banco, metricas

LOTE = 4000
PAUSA = 4
AMOSTRA = 2000
MINIMO_DE_PALAVRAS_FIXAS = 2

FIXAS = set("""
a an the of in on at to for from by with without about into over under after before then than as and or but not no so
this that these those there here it its is are was were be been being am do does did doing done have has had having will would
can could should shall may might must i you he she we they me him her us them my your his our their mine yours what why how
who whom whose when where which while if because until till all any each every both few more most other some such own same
very just only also ever never always nobody everyone everybody anyone someone nothing everything something anything
top best worst real true truth secret secrets inside behind finally really actually still again once first last next new old
one two three four five six seven eight nine ten
o os as um uma uns umas de do da dos das em no na nos nas por pelo pela pelos pelas para pra com sem e ou mas nao não que
se como quem quando onde qual quais porque porquê isso isto esse essa este esta aquele aquela aquilo ele ela eles elas você
vocês voce voces seu sua seus suas meu minha meus minhas nosso nossa foi foram era eram é são sao está estão esta estao tem têm
vai vão ser ter fazer mais menos muito muita muitos muitas melhor melhores pior piores verdade segredo segredos nunca sempre
ninguém ninguem todo toda todos todas tudo nada algo alguém alguem cada agora hoje ainda já ja só so depois antes
el la los las un una unos unas del al en con sin por para y o pero que qué cómo cuándo dónde quién quien nadie nunca siempre
todo todos toda todas este esta estos estas ese esa tu tus su sus mi mis es son fue fueron era eran hay más menos mejor peor
""".split())

TOKEN = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?|\d+", re.UNICODE)
RABO = re.compile(r"\s+[|•·]\s+|\s+[-–—]\s+(?=[^-–—]{0,40}$)")   # " | Nome do canal" e " - Parte 2" no fim não são estrutura


def de(titulo: str) -> str:
    """O molde, ou vazio quando o título quase não tem estrutura (poucas palavras fixas não dizem nada)."""
    corpo = RABO.split(str(titulo or ""), maxsplit=1)[0]
    pedacos, fixas = [], 0
    for token in TOKEN.findall(corpo.lower()):
        if token.isdigit():
            pedaco = "#"
        elif token in FIXAS:
            pedaco = token
            fixas += 1
        else:
            pedaco = "_"
        if pedaco != "_" or (pedacos and pedacos[-1] != "_") or not pedacos:
            pedacos.append(pedaco)
    if fixas < MINIMO_DE_PALAVRAS_FIXAS or "_" not in pedacos or len(pedacos) < 4:
        return ""
    return " ".join(pedacos)


def _legivel(molde: str) -> str:
    return molde.replace("_", "…").capitalize()


def parecidos(titulo: str, video_id: str = "", quantos: int = 12) -> dict:
    """Quem escreve no mesmo molde: os vídeos do que mais passou do normal para o menos, os canais e a mediana."""
    molde = de(titulo)
    vazio = {"molde": "", "total": 0, "canais": 0, "lift": None, "videos": []}
    if not molde:
        return vazio
    linhas = banco.todos("SELECT v.id, v.titulo, v.views, v.duracao_s, c.id AS canal_id, c.titulo AS canal, c.base_longos, c.base_curtos "
                         "FROM videos v JOIN canais c ON c.id=v.canal_id WHERE v.molde=? AND v.views IS NOT NULL "
                         "ORDER BY v.views DESC LIMIT ?", molde, AMOSTRA)
    videos = []
    for v in linhas:
        if v["id"] == video_id:
            continue
        normal = v.pop("base_curtos") if metricas.curto(v["duracao_s"]) else v["base_longos"]
        v.pop("base_curtos", None)
        v.pop("base_longos", None)
        v["nota"] = metricas.nota_outlier(v["views"], normal)
        videos.append(v)
    if not videos:
        return {**vazio, "molde": _legivel(molde)}
    notas = [v["nota"] for v in videos if v["nota"] is not None]
    videos.sort(key=lambda v: -(v["nota"] or 0))
    return {"molde": _legivel(molde), "total": len(videos), "canais": len({v["canal_id"] for v in videos}),
            "lift": round(median(notas), 1) if notas else None, "videos": videos[:quantos]}


def preencher(lote: int = LOTE) -> int:
    """Um pedaço dos vídeos sem molde. Devolve quantos preencheu: zero quer dizer que acabou."""
    linhas = banco.todos("SELECT id, titulo FROM videos WHERE molde IS NULL LIMIT ?", lote)
    if linhas:
        banco.varios("UPDATE videos SET molde=? WHERE id=?", [(de(l["titulo"]), l["id"]) for l in linhas])
    return len(linhas)


def iniciar() -> None:
    def rodar():
        while True:
            try:
                time.sleep(PAUSA if preencher() else 600)   # vídeo novo vai chegando: olha de novo de tempos em tempos
            except Exception:
                time.sleep(60)
    threading.Thread(target=rodar, daemon=True, name="moldes").start()
