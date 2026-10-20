"""O gosto de cada pessoa: as respostas da primeira vez, o que ela bloqueou e o quanto um vídeo parece com o que ela
faz. É o que deixa as sugestões com direção (pedido do usuário em 2026-10-14: "a procura de vídeos de sugestão está
ruim, a ideia é que procure semelhantes"; "bloquear certos tipos de vídeos"; "perguntas só para a primeira vez").

Canal dark: o padrão é só canal sem rosto."""
import json
import random
import re
import unicodedata

from . import banco, metricas

# ---------------------------------------------------------------- preferências

PADRAO = {"feito": False, "nichos": [], "linguas": ["pt", "en", "es"], "formato": "longo", "sem_rosto": True,
          "evitar": [], "referencias": []}

# o que dá para bloquear de uma vez nas perguntas: cada tipo vira nicho, palavras do título ou "tem rosto"
TIPOS = {
    "rosto": {"rotulo": "Canais com apresentador (rosto)", "rosto": True},
    "infantil": {"rotulo": "Infantil e desenho para criança", "nichos": ["Infantil"],
                 "palavras": ["kids", "nursery", "cocomelon", "infantil", "para niños", "cartoon for kids"]},
    "musica": {"rotulo": "Música e clipes", "nichos": ["Música"], "palavras": ["official video", "lyrics", "letra", "remix", "music video"]},
    "games": {"rotulo": "Games e gameplay", "nichos": ["Games"], "palavras": ["gameplay", "minecraft", "fortnite", "roblox", "gta", "free fire"]},
    "react": {"rotulo": "Reação (react)", "palavras": ["react", "reação", "reagindo", "reacting", "reaccion"]},
    "politica": {"rotulo": "Política e notícias do dia", "palavras": ["bolsonaro", "lula", "trump", "biden", "eleição", "election", "breaking news"]},
    "religiao": {"rotulo": "Religião", "nichos": ["Religião"]},
    "filmes": {"rotulo": "Resumo de filme e série", "palavras": ["movie explained", "recap", "filme explicado", "resumo do filme", "movie recap"]},
    "shorts": {"rotulo": "Shorts", "shorts": True},
}


def prefs(usuario: dict) -> dict:
    try:
        salvas = json.loads(usuario.get("prefs") or "{}")
    except ValueError:
        salvas = {}
    return PADRAO | salvas


def salvar_prefs(usuario_id: int, dados: dict) -> dict:
    limpo = {
        "feito": True,
        "nichos": [str(n)[:40] for n in dados.get("nichos", [])][:20],
        "linguas": [l for l in dados.get("linguas", []) if l in ("pt", "en", "es", "outras")] or ["pt", "en", "es"],
        "formato": dados.get("formato") if dados.get("formato") in ("longo", "curto", "todos") else "longo",
        "sem_rosto": bool(dados.get("sem_rosto", True)),
        "evitar": [t for t in dados.get("evitar", []) if t in TIPOS],
        "referencias": [str(r)[:30] for r in dados.get("referencias", [])][:5],
    }
    banco.executar("UPDATE usuarios SET prefs=? WHERE id=?", json.dumps(limpo, ensure_ascii=False), usuario_id)
    return limpo


# ---------------------------------------------------------------- bloqueios

def bloquear(usuario_id: int, tipo: str, valor: str, rotulo: str = "") -> None:
    if tipo not in ("video", "canal", "nicho", "subnicho", "palavra"):
        raise ValueError("tipo de bloqueio desconhecido")
    banco.executar("INSERT OR REPLACE INTO bloqueios (usuario_id, tipo, valor, rotulo, criado) VALUES (?,?,?,?,?)",
                   usuario_id, tipo, valor.strip()[:200], rotulo[:200], banco.agora())


def desbloquear(usuario_id: int, tipo: str, valor: str) -> None:
    banco.executar("DELETE FROM bloqueios WHERE usuario_id=? AND tipo=? AND valor=?", usuario_id, tipo, valor)


def bloqueios(usuario_id: int) -> list[dict]:
    return banco.todos("SELECT tipo, valor, rotulo, criado FROM bloqueios WHERE usuario_id=? ORDER BY criado DESC", usuario_id)


class Filtro:
    """Decide se um vídeo (com os dados do canal) aparece para a pessoa."""

    def __init__(self, usuario: dict):
        self.p = prefs(usuario)
        self.videos, self.canais, self.nichos, self.palavras = set(), set(), set(), []
        for b in bloqueios(usuario["id"]):
            if b["tipo"] == "video":
                self.videos.add(b["valor"])
            elif b["tipo"] == "canal":
                self.canais.add(b["valor"])
            elif b["tipo"] in ("nicho", "subnicho"):
                self.nichos.add(b["valor"].lower())
            elif b["tipo"] == "palavra":
                self.palavras.append(_simples(b["valor"]))
        self.sem_rosto = self.p["sem_rosto"]
        self.sem_shorts = self.p["formato"] == "longo"     # "longo": só vídeos longos; "todos": os dois
        for t in self.p["evitar"]:
            regra = TIPOS[t]
            self.sem_rosto = self.sem_rosto or regra.get("rosto", False)
            self.nichos |= {n.lower() for n in regra.get("nichos", [])}
            self.palavras += [_simples(x) for x in regra.get("palavras", [])]
            if regra.get("shorts"):
                self.sem_shorts = True
        self.linguas = set(self.p["linguas"])

    def aceita(self, v: dict) -> bool:
        if v.get("id") in self.videos or v.get("canal_id") in self.canais:
            return False
        if (v.get("nicho") or "").lower() in self.nichos or (v.get("subnicho") or "").lower() in self.nichos:
            return False
        if self.sem_rosto and v.get("sem_rosto") == 0:
            return False
        curto = metricas.curto(v.get("duracao_s"))
        if curto and self.sem_shorts:
            return False
        if self.p["formato"] == "curto" and not curto:
            return False
        from .mercado import irrelevante
        if irrelevante(v.get("nicho"), v.get("subnicho")):
            return False      # nicho que paga pouco ou de histórias narradas não aparece em nenhuma lista
        titulo = _simples(v.get("titulo") or "")
        if any(p and p in titulo for p in self.palavras):
            return False
        if "outras" not in self.linguas and lingua(v.get("titulo") or "") not in self.linguas | {"?"}:
            return False
        return True


# ---------------------------------------------------------------- língua do título e parecença

_PALAVRAS = {
    "pt": {"o", "a", "os", "as", "de", "do", "da", "dos", "das", "que", "e", "um", "uma", "não", "com", "para", "por", "como",
           "mais", "você", "isso", "foi", "são", "quando", "porque", "seu", "sua", "este", "esta", "mundo", "história"},
    "es": {"el", "la", "los", "las", "de", "del", "que", "y", "un", "una", "no", "con", "para", "por", "como", "más", "es",
           "qué", "cuando", "porque", "su", "este", "esta", "mundo", "historia", "lo"},
    "en": {"the", "a", "of", "to", "and", "in", "is", "it", "you", "that", "what", "how", "why", "this", "with", "for",
           "on", "was", "are", "from", "world", "history", "they", "his", "her", "vs", "into", "across", "years",
           "ago", "through", "first", "after", "before", "inside", "their", "turns", "explained", "documentary"},
}
# hindi e urdu escritos com letras latinas ("Maut Ke Baad Narak Mein..."): o canal é de outra língua
_HINGLISH = {"ke", "ki", "ka", "hai", "mein", "ye", "yeh", "aur", "ek", "kya", "nahi", "ho", "gaya", "gayi", "wo",
             "kaise", "kyun", "sirf", "balki", "usne", "unki", "saal", "puri", "jitna", "bada", "hota"}


def lingua(titulo: str) -> str:
    """pt, es, en, outras (outro alfabeto) ou ? (não deu para saber)."""
    if not titulo:
        return "?"
    letras = [c for c in titulo if c.isalpha()]
    # 3 letras de outro alfabeto já bastam: "দুই বোনের ভাগ্য | Bangla Animated Moral Story" passava como inglês
    if letras and sum(1 for c in letras if ord(c) > 0x024F) >= 3:
        return "outras"          # hindi, árabe, russo, chinês...
    baixo = titulo.lower()
    if sum(1 for p in re.findall(r"[a-z]+", baixo) if p in _HINGLISH) >= 2:
        return "outras"
    if re.search(r"[ãõç]", baixo):
        return "pt"
    if re.search(r"[ñ¿¡]", baixo):
        return "es"
    palavras = re.findall(r"[a-záéíóúâêôàü]+", baixo)
    contas = {l: sum(1 for p in palavras if p in conj) for l, conj in _PALAVRAS.items()}
    melhor = max(contas, key=contas.get)
    if contas[melhor] == 0:
        return "?"
    empate = [l for l, n in contas.items() if n == contas[melhor]]
    return melhor if len(empate) == 1 else "?"


def _simples(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


_VAZIAS = set().union(*_PALAVRAS.values()) | {"video", "documentary", "documentario", "documental", "full", "completo",
                                              "top", "most", "mais", "best", "melhores", "you", "voce", "never", "nunca"}


def chaves(texto: str) -> set[str]:
    """As palavras que dizem o assunto (sem acento, sem as palavras de ligação)."""
    return {p for p in re.findall(r"[a-z0-9]{4,}", _simples(texto)) if p not in _VAZIAS}


def parecenca(titulo: str, alvo: set[str]) -> float:
    """Quanto o título fala do mesmo assunto que o alvo (as palavras dos vídeos da pessoa): 0 a 1."""
    p = chaves(titulo)
    if not p or not alvo:
        return 0.0
    return len(p & alvo) / len(p)


def assunto_da_pessoa(usuario_id: int, prefs_: dict) -> tuple[set[str], set[str], set[str]]:
    """As palavras, os nichos e os subnichos dos canais da pessoa e dos canais de referência que ela deu."""
    ids = [l["canal_id"] for l in banco.todos("SELECT canal_id FROM meus_canais WHERE usuario_id=?", usuario_id)]
    ids += [l["canal_id"] for l in banco.todos("SELECT canal_id FROM salvos WHERE usuario_id=?", usuario_id)]
    ids += prefs_.get("referencias_ids", [])
    palavras, nichos, subs = set(), set(prefs_.get("nichos", [])), set()
    if ids:
        marcas = ",".join("?" * len(ids))
        for c in banco.todos(f"SELECT nicho, subnicho FROM canais WHERE id IN ({marcas})", *ids):
            nichos.add(c["nicho"]); subs.add(c["subnicho"])
        for v in banco.todos(f"SELECT titulo FROM videos WHERE canal_id IN ({marcas}) ORDER BY views DESC LIMIT 200", *ids):
            palavras |= chaves(v["titulo"])
    return palavras, {n for n in nichos if n}, {s for s in subs if s}


SELECT_VIDEO = ("SELECT o.nota, v.id, v.titulo, v.views, v.publicado, v.duracao_s, c.id AS canal_id, c.titulo AS canal, "
                "c.foto, c.handle, c.inscritos, c.nicho, c.subnicho, c.sem_rosto, c.base_longos AS normal "
                "FROM outliers o JOIN videos v ON v.id=o.video_id JOIN canais c ON c.id=o.canal_id ")


def explorar(usuario: dict, nicho: str = "", quantos: int = 24, semente: int | None = None, lingua: str = "",
             filtros: dict | None = None) -> list[dict]:
    """Vídeos que estouraram, sorteados: a cada "Mostrar outros" vem outra leva. Os filtros são os da tela
    (as respostas antigas das perguntas não valem mais: limitavam o Explorar a um nicho sem a pessoa ver)."""
    from datetime import datetime, timedelta, timezone
    f = filtros or {}
    filtro = Filtro(usuario)
    filtro.linguas = {"outras"}       # a língua é a do filtro da tela
    filtro.sem_rosto = f.get("rosto", "sem") != "todos"
    formato = f.get("formato") or "longo"
    filtro.sem_shorts = formato == "longo"
    filtro.p = filtro.p | {"formato": "curto" if formato == "curto" else "todos"}
    onde, args = ["o.nota >= ?"], [float(f.get("nota_min") or 3)]
    if nicho:
        onde.append("c.nicho=?"); args.append(nicho)
    if f.get("publicado_dias"):
        onde.append("v.publicado >= ?")
        args.append((datetime.now(timezone.utc) - timedelta(days=int(f["publicado_dias"]))).isoformat())
    if f.get("inscritos_max"):
        onde.append("c.inscritos <= ?"); args.append(int(f["inscritos_max"]))
    linhas = banco.todos(SELECT_VIDEO + f"WHERE {' AND '.join(onde)}", *args)
    aceitos = por_lingua([l for l in linhas if filtro.aceita(l)], lingua)
    sorteio = random.Random(semente)
    # sorteio com peso: nota maior aparece mais, mas a leva muda toda vez
    aceitos.sort(key=lambda l: -sorteio.random() ** (1 / max(1.0, min(l["nota"], 50) ** 0.5)))
    return aceitos[:quantos]


def ideias_para(usuario: dict, canal: dict, limite: int = 24, formato: str | None = None) -> list[dict]:
    """Ideias para um canal: vídeos que estouraram e falam do mesmo assunto que os vídeos dele.

    Antes era só "mesmo subnicho", e canal sem subnicho certo ganhava ideias de qualquer coisa.
    Com `formato` (o filtro da tela: "longo", "curto" ou "todos"), ele manda no lugar da pergunta da primeira vez."""
    filtro = Filtro(usuario)
    filtro.linguas = {"outras"}           # a língua é a do filtro da tela (trabalho.ideias)
    if formato is not None:
        filtro.sem_shorts = formato == "longo"
        filtro.p = filtro.p | {"formato": "curto" if formato == "curto" else "todos"}
    alvo = set()
    for v in banco.todos("SELECT titulo FROM videos WHERE canal_id=? ORDER BY views DESC LIMIT 30", canal["id"]):
        alvo |= chaves(v["titulo"])
    # o treino do canal (os vídeos que a pessoa marcou como "faria") manda mais que os títulos do próprio canal
    from .treinamento import pesos as pesos_do_treino
    pesos = pesos_do_treino(usuario["id"], canal["id"])
    maior = max([w for w in pesos.values() if w > 0] or [1])
    from .alvos import BONUS_INSCRITO, inscritos as inscritos_do_canal
    inscritos = inscritos_do_canal(usuario["id"], canal["id"])
    pontos = []
    for l in banco.todos(SELECT_VIDEO + "WHERE o.nota >= 3 AND c.id<>?", canal["id"]):
        if not filtro.aceita(l):
            continue
        p = parecenca(l["titulo"], alvo) * (1.5 if pesos else 3)
        if pesos:
            treino = sum(pesos.get(w, 0) for w in chaves(l["titulo"])) / maior
            if treino < 0:
                continue          # fala de um assunto que a pessoa recusou no treino
            p += treino * 2.5
        p += 1.5 if canal.get("subnicho") and l["subnicho"] == canal["subnicho"] else 0
        p += 0.8 if canal.get("nicho") and l["nicho"] == canal["nicho"] else 0
        p += BONUS_INSCRITO if l["canal_id"] in inscritos else 0
        if p <= 0:
            continue
        pontos.append((p + min(l["nota"], 30) / 60, l))
    pontos.sort(key=lambda x: -x[0])
    return [l | {"origem": "parecido"} for _, l in pontos[:limite]]


LINGUAS_ESCOLHA = {"ptenes": {"pt", "en", "es", "?"}, "pt": {"pt"}, "en": {"en"}, "es": {"es"}, "todas": None}


def por_lingua(lista: list[dict], escolha: str) -> list[dict]:
    """O filtro de língua das telas (sem as perguntas, é ele que decide). Padrão: português, inglês e espanhol."""
    aceitas = LINGUAS_ESCOLHA.get(escolha or "ptenes", LINGUAS_ESCOLHA["ptenes"])
    if aceitas is None:
        return lista
    return [v for v in lista if lingua(v.get("titulo") or "") in aceitas]
