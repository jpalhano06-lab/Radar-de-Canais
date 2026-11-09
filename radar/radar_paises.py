"""Radar de países: a ideia de um vídeo já foi feita em cada país e língua?

Pedido do usuário em 2026-10-14. Cada canal da pessoa tem um projeto de radar com os países e as línguas que ela
quer conferir (ex.: o canal de mercado olha Canadá, Austrália e Reino Unido, em inglês). No 📡 de um vídeo, a ideia é
procurada pelo **título exato, sem nenhuma numeração** ("10 supermercados que faliram" vira "supermercados que
faliram"; em outra língua, a tradução fiel do título, sem adaptar nada), buscada no YouTube daquele país (regionCode + relevanceLanguage), e os resultados com título
parecido dizem se a ideia já existe lá. Cada país custa uns 101 de cota (a busca e as views); fica guardado 7 dias."""
import json
import re
from datetime import datetime, timedelta, timezone

from . import banco, gosto, ia, youtube

# país: (nome, língua padrão). A pessoa pode trocar a língua de cada um no projeto
PAISES = {
    "BR": ("Brasil", "pt"), "PT": ("Portugal", "pt"), "US": ("Estados Unidos", "en"), "CA": ("Canadá", "en"),
    "GB": ("Reino Unido", "en"), "AU": ("Austrália", "en"), "NZ": ("Nova Zelândia", "en"), "IE": ("Irlanda", "en"),
    "IN": ("Índia", "en"), "ZA": ("África do Sul", "en"), "ES": ("Espanha", "es"), "MX": ("México", "es"),
    "AR": ("Argentina", "es"), "CO": ("Colômbia", "es"), "CL": ("Chile", "es"), "PE": ("Peru", "es"),
    "FR": ("França", "fr"), "DE": ("Alemanha", "de"), "IT": ("Itália", "it"), "NL": ("Holanda", "nl"),
    "PL": ("Polônia", "pl"), "TR": ("Turquia", "tr"), "JP": ("Japão", "ja"), "KR": ("Coreia do Sul", "ko"),
    "PH": ("Filipinas", "en"), "ID": ("Indonésia", "id"), "RU": ("Rússia", "ru"), "SA": ("Arábia Saudita", "ar"),
}
LINGUAS = {"pt": "português", "en": "inglês", "es": "espanhol", "fr": "francês", "de": "alemão", "it": "italiano",
           "nl": "holandês", "pl": "polonês", "tr": "turco", "ja": "japonês", "ko": "coreano", "id": "indonésio",
           "ru": "russo", "ar": "árabe"}
GUARDA_DIAS = 7
PARECIDO = 0.6          # 60% das palavras da ideia no título achado: é a mesma ideia
QUASE = 0.4             # 40%: parece, mas não é a mesma ideia (só conta)
# canal sem radar próprio confere nestas 11 línguas (o botão Radar funciona desde o primeiro clique); Holanda, Japão e
# Coreia do Sul entraram em 2026-11-03
PADRAO = [("US", "en"), ("BR", "pt"), ("ES", "es"), ("FR", "fr"), ("DE", "de"), ("IT", "it"), ("PL", "pl"), ("TR", "tr"),
          ("NL", "nl"), ("JP", "ja"), ("KR", "ko")]


def forca(views: int | None) -> str:
    """Quem já fez foi bem? Forte com 100 mil views ou mais, médio com 20 mil, fraco abaixo: ideia feita fraca
    num país ainda pode valer a pena lá."""
    v = views or 0
    return "forte" if v >= 100_000 else "medio" if v >= 20_000 else "fraco"


# ---------------------------------------------------------------- projetos

def projetos(usuario_id: int) -> list[dict]:
    linhas = banco.todos("SELECT p.*, c.titulo AS canal, c.foto FROM radar_projetos p LEFT JOIN canais c ON c.id=p.canal_id "
                         "WHERE p.usuario_id=? ORDER BY p.id", usuario_id)
    for l in linhas:
        l["paises"] = json.loads(l["paises"])
    return linhas


def salvar(usuario_id: int, dados: dict) -> int:
    paises = []
    for p in dados.get("paises", [])[:12]:
        codigo = str(p.get("codigo", "")).upper()
        if codigo in PAISES:
            lingua = p.get("lingua") if p.get("lingua") in LINGUAS else PAISES[codigo][1]
            paises.append({"codigo": codigo, "nome": PAISES[codigo][0], "lingua": lingua})
    if not paises:
        raise ValueError("Escolha pelo menos um país.")
    nome = str(dados.get("nome", "")).strip()[:60] or "Radar"
    canal_id = str(dados.get("canal_id", ""))
    if dados.get("id"):
        banco.executar("UPDATE radar_projetos SET nome=?, canal_id=?, paises=? WHERE id=? AND usuario_id=?",
                       nome, canal_id, json.dumps(paises, ensure_ascii=False), int(dados["id"]), usuario_id)
        return int(dados["id"])
    return banco.executar("INSERT INTO radar_projetos (usuario_id, canal_id, nome, paises, criado) VALUES (?,?,?,?,?)",
                          usuario_id, canal_id, nome, json.dumps(paises, ensure_ascii=False), banco.agora())


def apagar(usuario_id: int, projeto_id: int) -> None:
    banco.executar("DELETE FROM radar_projetos WHERE id=? AND usuario_id=?", projeto_id, usuario_id)


# ---------------------------------------------------------------- a ideia sem números

_NUMEROS = re.compile(r"(?<!\w)(#?\d+[\d.,]*(º|ª|°|st|nd|rd|th|x|%|k|mil|mi)?|top)(?!\w)", re.I)


def sem_numeros(titulo: str) -> str:
    """A ideia, nunca a numeração: "Top 10 supermercados que faliram em 2024" vira "supermercados que faliram em".
    Os números mudam de um vídeo para o outro; a ideia é a mesma."""
    texto = _NUMEROS.sub(" ", titulo)
    texto = re.sub(r"[|#\[\]()]+", " ", texto)
    return re.sub(r"\s{2,}", " ", texto).strip(" -–—:,.")


def palavras_da_busca(titulo: str) -> str:
    """O que vai para o YouTube: as palavras do assunto, na ordem do título, sem números nem palavras de ligação.

    A frase inteira traduzida se perdia: "Animais Bizarros de Papua Que Parecem Vir de Outro Mundo!" trazia jacaré e
    tribo canibal, e os dois vídeos brasileiros dessa ideia só apareciam buscando "animais bizarros Papua outro mundo"."""
    texto = sem_numeros(titulo)
    vistas, saida = set(), []
    for palavra in re.findall(r"[^\W\d_][\w'’-]*", texto):
        chave = next(iter(palavras(palavra)), "")
        if chave and chave not in vistas:
            vistas.add(chave)
            saida.append(palavra)
    return " ".join(saida[:8]) or texto


def _raiz(palavra: str) -> str:
    """Sem plural e sem o final de gênero, até 5 letras: "gato" e "gatos", "raras" e "raros", "bizarro" e "bizarros",
    "parecem" e "parecer" contam como a mesma palavra."""
    palavra = re.sub(r"(es|s)$", "", palavra) if len(palavra) > 4 else palavra
    palavra = re.sub(r"[aoe]$", "", palavra) if len(palavra) > 3 else palavra
    return palavra[:5]


def numeros(titulo: str) -> set[str]:
    return set(re.findall(r"(?<![\d.,])\d{1,3}(?![\d.,])", titulo))


BONUS_NUMERO = 0.2      # o mesmo número do título ("15") no vídeo achado é uma pista forte da mesma ideia
PESO_ISCA = 0.5         # palavra de isca vale metade: "Rare Birds... You Won't Believe They're Real" não é a ideia dos gatos

# palavras de isca de título (pt, en, es): dizem o tom, não o assunto
ISCA = {_r for _r in """acreditar acredita acreditaria believe believed creer creeras creerias reais real reales realmente
    mundo world mundial outro outra another otro otra parecem parece parecer look looks like parecen
    incriveis incrivel incredible increible amazing surpreendente surpreender surprising shocking chocante
    ninguem nobody nadie existem existe exist exists existen nunca never jamais visto vistos seen viu vio
    bizarre bizarro bizarra estranho estranha strange weird extrano rare rarest raros raras raro rara
    bonitos bonitas bonito bonita lindos lindas beautiful hermosos hermosas cute fofos fofas
    secret secreto secreta segredo segredos verdade truth verdad historia history story""".split()}

_VAZIAS3 = {"the", "and", "you", "are", "for", "was", "que", "dos", "das", "com", "una", "uno", "los", "las", "del",
            "por", "nao", "sao", "vai", "his", "her", "its", "how", "why", "who", "not", "but", "can", "has", "had",
            "mas", "sus", "sem", "ter", "ser", "vir", "won", "they", "top", "mais", "more", "most"}


# japonês e coreano: kanji, katakana e hangul. O hiragana (partículas e finais de verbo) só separa
_CJK = re.compile(r"[一-鿿゠-ヿ가-힣]+")
_KANA = re.compile(r"[぀-ヿ]")
_HANGUL = re.compile(r"[가-힣]")


def _pedacos_cjk(texto: str) -> set[str]:
    """Japonês não tem espaço e o coreano gruda a partícula na palavra ("고양이가", "고양이는"): os pares de letras
    vizinhas fazem as vezes das palavras ("고양", "양이"). Um kanji sozinho ("猫") já é uma palavra."""
    saida = set()
    for trecho in _CJK.findall(texto):
        saida |= {trecho} if len(trecho) == 1 else {trecho[i:i + 2] for i in range(len(trecho) - 1)}
    return saida


def palavras(texto: str) -> set[str]:
    """As palavras do título para comparar ideias: como `gosto.chaves`, mas com as de 3 letras ("cat", "dog", "mar")
    e os pedaços do japonês e do coreano (sem eles, nada batia lá e o Japão saía sempre "ninguém fez")."""
    return gosto.chaves(texto) | {p for p in re.findall(r"\b[a-z]{3}\b", gosto._simples(texto))
                                  if p not in _VAZIAS3 and p not in gosto._VAZIAS} | _pedacos_cjk(texto)


def mesma_ideia(titulo: str, alvo: set[str], numero: set[str] | None = None) -> float:
    """Quanto da ideia aparece no título achado (0 a 1): as palavras da ideia que estão nele, pela raiz, mais um
    reforço se ele tem o mesmo número do título original. A busca vai sem números; a comparação usa.

    Antes era o contrário (quanto do título achado estava na ideia), e "15 Animais Bizarros da Papua Que Parecem Ter
    Vindo de Outro Mundo!" tirava 0,5 contra a ideia em três palavras. Depois, "As 15 Raças de Gatos Mais Raras e
    Lindas do Mundo" tirava 0,5 porque "gatos" e "gato", "raros" e "raras" contavam como palavras diferentes."""
    if not alvo:
        return 0.0
    achadas = {_raiz(p) for p in palavras(titulo)}
    assunto = {_raiz(x) for x in alvo if x not in ISCA}
    isca = {_raiz(x) for x in alvo if x in ISCA} - assunto
    if not assunto:                  # título só de isca: todas valem igual
        assunto, isca = assunto | isca, set()
    bate = sum(1 for p in assunto if p in achadas)
    nota = (bate + PESO_ISCA * sum(1 for p in isca if p in achadas)) / (len(assunto) + PESO_ISCA * len(isca))
    # o mesmo número só reforça quando o assunto já bate pela metade
    if numero and numero & numeros(titulo) and bate >= len(assunto) / 2:
        nota += BONUS_NUMERO
    return min(1.0, nota)


_LATINAS = {"pt", "en", "es"}


def na_lingua(titulo: str, lingua: str) -> bool:
    """O vídeo achado está na língua do país? Um reupload em inglês achado no Brasil não diz que o Brasil já fez."""
    achada = gosto.lingua(titulo)
    if achada in _LATINAS:
        return achada == lingua
    if achada == "outras":
        # um vídeo coreano achado no Japão não diz que o Japão já fez (nem o contrário)
        if lingua == "ja":
            return bool(_KANA.search(titulo))
        if lingua == "ko":
            return bool(_HANGUL.search(titulo))
        return lingua in {"ru", "ar"}
    return True


# ---------------------------------------------------------------- conferir uma ideia

@youtube.por("paises")
def conferir(usuario_id: int, projeto_id: int, video_id: str, titulo: str) -> dict:
    if projeto_id == 0:
        p = {"nome": "Radar de línguas", "paises": json.dumps(
            [{"codigo": c, "nome": PAISES[c][0], "lingua": l} for c, l in PADRAO], ensure_ascii=False)}
    else:
        p = banco.um("SELECT * FROM radar_projetos WHERE id=? AND usuario_id=?", projeto_id, usuario_id)
    if not p:
        raise ValueError("Projeto de radar não encontrado.")
    paises = json.loads(p["paises"])
    ideia = sem_numeros(titulo)
    chave = f"paises9:{projeto_id}:{video_id or ideia.lower()}:{p['paises']}"
    cache = banco.um("SELECT dados, criado FROM traducoes WHERE chave=?", chave)
    limite = (datetime.now(timezone.utc) - timedelta(days=GUARDA_DIAS)).isoformat()
    if cache and cache["criado"] >= limite:
        return json.loads(cache["dados"]) | {"guardado": True}
    # a mesma ideia adaptada a cada país (o lugar da ideia vira o país da busca); sem resposta, só a tradução
    # o título exato, sem os números: na mesma língua do título vai ele mesmo; em outra língua, a tradução fiel
    lingua_titulo = gosto.lingua(titulo)
    outras = sorted({x["lingua"] for x in paises if x["lingua"] != lingua_titulo})
    traducoes = ia.traduzir_exato(titulo, outras)
    resultado = []
    for x in paises:
        traduzido = sem_numeros(traducoes.get(x["lingua"]) or titulo) if x["lingua"] != lingua_titulo else ideia
        alvo = palavras(traduzido)
        busca = palavras_da_busca(traduzido)
        achados = youtube.buscar(busca, ordem="relevance", quantos=50, regiao=x["codigo"], idioma=x["lingua"])
        dados = {v["id"]: v for v in youtube.videos([a["video_id"] for a in achados])}
        parecidos, quase = [], 0
        for a in achados:
            if a["video_id"] == video_id or not na_lingua(a["titulo"], x["lingua"]):
                continue
            nota = mesma_ideia(a["titulo"], alvo, numeros(titulo))
            if nota >= PARECIDO:
                v = dados.get(a["video_id"], {})
                parecidos.append({"id": a["video_id"], "titulo": a["titulo"], "canal": a["canal"], "views": v.get("views"),
                                  "publicado": v.get("publicado", ""), "parecenca": round(nota, 2)})
            elif nota >= QUASE:
                quase += 1
        parecidos.sort(key=lambda v: -(v["views"] or 0))
        resultado.append({"codigo": x["codigo"], "pais": x["nome"], "lingua": x["lingua"], "busca": busca,
                          "feito": bool(parecidos), "parecidos": parecidos[:4], "quase": quase,
                          "forca": forca(parecidos[0]["views"]) if parecidos else "",
                          "link": f"https://www.youtube.com/results?search_query={busca.replace(' ', '+')}"})
    saida = {"ideia": ideia, "projeto": p["nome"], "paises": resultado, "quando": banco.agora(),
             "livres": sum(1 for r in resultado if not r["feito"])}
    banco.executar("INSERT OR REPLACE INTO traducoes (chave, dados, criado) VALUES (?,?,?)",
                   chave, json.dumps(saida, ensure_ascii=False), banco.agora())
    return saida


# ---------------------------------------------------------------- pela extensão: o YouTube de verdade, sem cota

# Os três modos do Método Fantasma (pedido do usuário em 2026-11-03, no jeito do "Método Malandro" de outra extensão):
#   raiz      - o título traduzido para cada língua, o lugar do título continua nele;
#   adaptado  - o lugar do título trocado pelo país de cada língua ("supermercados do Canadá" vira "supermarkets in
#               the USA"); título sem lugar ganha o país ("animais bizarros do Brasil");
#   premium   - só os países de língua inglesa, onde o RPM é mais alto: o título em inglês, com o país trocado.
MODOS = ("raiz", "adaptado", "premium")
PREMIUM = ["US", "GB", "CA", "AU", "NZ", "IE"]
VIEWS_FRACO = 0.05      # o achado com menos de 5% das views do vídeo aberto é fraco: ainda vale fazer lá
# vídeo de mais de um ano não conta: a ideia esfriou e o lugar abriu de novo (em cada língua que o YouTube mostra)
_VELHO = re.compile(r"\d+\s*(?:(?:anos?|years?|años?|ans?|année|jahre?n?|ann[oi]|rok|lata?|yıl|jaar)(?!\w)|年|년)", re.I)


def velho(publicado: str) -> bool:
    return bool(_VELHO.search(str(publicado or "")))


def preparar(titulo: str, modo: str = "raiz") -> dict:
    """O que a extensão busca em cada país (pedido do usuário em 2026-10-14: o radar saiu do site e foi para a
    extensão). A tradução e a troca do lugar saem do Groq (grátis, guardadas); quem abre a busca de cada país é a
    extensão, na página do YouTube, sem gastar a cota da API."""
    modo = modo if modo in MODOS else "raiz"
    ideia = sem_numeros(titulo)
    lingua_titulo = gosto.lingua(titulo)
    alvos = [(c, "en") for c in PREMIUM] if modo == "premium" else PADRAO
    traducoes = _traducoes(titulo, sorted({l for _, l in alvos if l != lingua_titulo}))
    troca = {"lugar": "", "titulos": {}, "marcas": {}}
    if modo != "raiz":
        troca = _troca(titulo, modo, {c: (PAISES[c][0], l) for c, l in alvos})
    paises = []
    for codigo, lingua in alvos:
        traduzido = sem_numeros(traducoes.get(lingua) or titulo) if lingua != lingua_titulo else ideia
        trocado = sem_numeros(troca["titulos"].get(codigo, ""))
        # o título já fala deste país ("Why Americans Are Leaving California" e os EUA): não há o que trocar, mesmo
        # que o Groq tenha trocado
        if trocado and tem_marca(titulo, troca["marcas"].get(codigo, [])):
            trocado = ""
        # premium com lugar: o país do próprio título fica fora
        if modo == "premium" and troca["lugar"] and not trocado:
            continue
        pais = {"codigo": codigo, "pais": PAISES[codigo][0], "lingua": lingua, "traduzido": trocado or traduzido,
                "trocado": bool(trocado), "marcas": troca["marcas"].get(codigo, []) if trocado else []}
        pais["busca"] = palavras_da_busca(pais["traduzido"])
        paises.append(pais)
    return {"titulo": titulo, "ideia": ideia, "modo": modo, "lugar": troca["lugar"], "paises": paises}


def _traducoes(titulo: str, linguas: list[str]) -> dict:
    chave = f"traducao-radar:{titulo}"
    linha = banco.um("SELECT dados FROM traducoes WHERE chave=?", chave)
    traducoes = json.loads(linha["dados"]) if linha else {}
    # a guardada de antes não tem as línguas que entraram depois (holandês, japonês, coreano): só elas vão ao Groq
    faltam = [l for l in linguas if l not in traducoes]
    novas = ia.traduzir_exato(titulo, faltam) if faltam else {}
    traducoes |= novas
    if novas:
        banco.executar("INSERT OR REPLACE INTO traducoes (chave, dados, criado) VALUES (?,?,?)",
                       chave, json.dumps(traducoes, ensure_ascii=False), banco.agora())
    return traducoes


def _troca(titulo: str, modo: str, alvos: dict) -> dict:
    """O lugar do título trocado pelo de cada país, guardado. No adaptado o título sem lugar ganha o país; no
    premium fica o título em inglês, igual para os seis. O Groq falhou: fica a tradução, e tenta de novo da próxima."""
    chave = f"troca-radar:{modo}:{titulo}"
    linha = banco.um("SELECT dados FROM traducoes WHERE chave=?", chave)
    if linha:
        return json.loads(linha["dados"])
    r = ia.regionalizar(titulo, alvos, acrescentar=modo == "adaptado")
    if r is None:
        return {"lugar": "", "titulos": {}, "marcas": {}}
    banco.executar("INSERT OR REPLACE INTO traducoes (chave, dados, criado) VALUES (?,?,?)",
                   chave, json.dumps(r, ensure_ascii=False), banco.agora())
    return r


def _views(texto) -> int | None:
    """ "1.234.567 visualizações", "1,234,567 views": só os dígitos (a extensão manda o número completo)."""
    if isinstance(texto, (int, float)):
        return int(texto)
    digitos = re.sub(r"\D", "", str(texto or ""))
    return int(digitos) if digitos else None


def forca_relativa(views: int | None, base: int | None) -> str:
    """Com as views do vídeo aberto, fraco é relativo a ele (menos de 5%); sem elas, o corte fixo de `forca`."""
    if base and (views or 0) < base * VIEWS_FRACO:
        return "fraco"
    return forca(views)


def tem_marca(titulo: str, marcas: list[str]) -> bool:
    """O vídeo achado fala do país? Pela raiz ("brasileiras" e "Brasil" batem) ou pela sigla ("USA", "UK")."""
    achadas = {_raiz(p) for p in palavras(titulo)} | {p.lower() for p in re.findall(r"\w+", titulo)}
    for m in marcas:
        partes = {_raiz(p) for p in palavras(m)} or {p.lower() for p in re.findall(r"\w+", m)}
        if partes and partes <= achadas:
            return True
    return False


def _placar(x: dict, achados: list, titulo: str, video_id: str, canal_id: str, base: int | None) -> dict:
    """Os vídeos achados num país viram o placar: já fizeram (forte, médio, fraco) ou ninguém fez. Não contam o
    próprio vídeo, os do mesmo canal, os de mais de um ano e os de outra língua; com o país trocado, o achado
    precisa falar do país (um vídeo dos EUA achado na Austrália não diz que a Austrália já fez)."""
    alvo = palavras(str(x.get("traduzido", "")))
    marcas = x.get("marcas") or []
    parecidos, quase, velhos, vistos = [], 0, 0, set()
    for a in (achados or [])[:80]:
        t, vid = str(a.get("titulo", "")), str(a.get("id", ""))
        if not t or vid == video_id or vid in vistos or (canal_id and a.get("canal_id") == canal_id) \
                or not na_lingua(t, x["lingua"]):
            continue
        vistos.add(vid)
        nota = mesma_ideia(t, alvo, numeros(titulo))
        if nota >= PARECIDO and velho(a.get("publicado", "")):
            velhos += 1
        elif nota >= PARECIDO and (not marcas or tem_marca(t, marcas)):
            parecidos.append({"id": vid, "titulo": t, "canal": str(a.get("canal", "")),
                              "views": _views(a.get("views")), "publicado": str(a.get("publicado", "")),
                              "parecenca": round(nota, 2)})
        elif nota >= QUASE:
            quase += 1
    parecidos.sort(key=lambda v: -(v["views"] or 0))
    busca = x["busca"]
    return {"codigo": x["codigo"], "pais": x["pais"], "lingua": x["lingua"], "busca": busca,
            "traduzido": x.get("traduzido", ""), "trocado": bool(x.get("trocado")),
            "feito": bool(parecidos), "parecidos": parecidos[:4], "quase": quase, "velhos": velhos,
            "forca": forca_relativa(parecidos[0]["views"], base) if parecidos else "",
            "link": f"https://www.youtube.com/results?search_query={busca.replace(' ', '+')}"}


def julgar(preparo: dict, resultados: dict, video_id: str = "", canal_id: str = "", views=None) -> dict:
    titulo = str(preparo.get("titulo", ""))
    base = _views(views)
    saida = [_placar(x, resultados.get(x["codigo"]), titulo, video_id, canal_id, base) for x in preparo.get("paises", [])]
    return {"ideia": preparo.get("ideia", ""), "modo": preparo.get("modo", "raiz"), "lugar": preparo.get("lugar", ""),
            "paises": saida, "livres": sum(1 for r in saida if not r["feito"])}
