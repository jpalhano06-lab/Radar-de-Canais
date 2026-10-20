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
# canal sem radar próprio confere nestas 8 línguas (o botão Radar funciona desde o primeiro clique)
PADRAO = [("US", "en"), ("BR", "pt"), ("ES", "es"), ("FR", "fr"), ("DE", "de"), ("IT", "it"), ("PL", "pl"), ("TR", "tr")]


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


def palavras(texto: str) -> set[str]:
    """As palavras do título para comparar ideias: como `gosto.chaves`, mas com as de 3 letras ("cat", "dog", "mar")."""
    return gosto.chaves(texto) | {p for p in re.findall(r"\b[a-z]{3}\b", gosto._simples(texto))
                                  if p not in _VAZIAS3 and p not in gosto._VAZIAS}


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
        return lingua in {"ja", "ko", "ru", "ar"}
    return True


# ---------------------------------------------------------------- conferir uma ideia

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

def preparar(titulo: str) -> dict:
    """O que a extensão busca em cada país (pedido do usuário em 2026-10-14: o radar saiu do site e foi para a
    extensão). A tradução fiel sai do Groq (grátis, guardada); quem abre a busca de cada país é a extensão, na página
    do YouTube, sem gastar a cota da API. A busca da API só via 50 resultados, numa ordem diferente da do site."""
    ideia = sem_numeros(titulo)
    lingua_titulo = gosto.lingua(titulo)
    outras = sorted({l for _, l in PADRAO if l != lingua_titulo})
    chave = f"traducao-radar:{titulo}"
    cache = banco.um("SELECT dados FROM traducoes WHERE chave=?", chave)
    traducoes = json.loads(cache["dados"]) if cache else ia.traduzir_exato(titulo, outras)
    if traducoes and not cache:
        banco.executar("INSERT OR REPLACE INTO traducoes (chave, dados, criado) VALUES (?,?,?)",
                       chave, json.dumps(traducoes, ensure_ascii=False), banco.agora())
    paises = []
    for codigo, lingua in PADRAO:
        traduzido = sem_numeros(traducoes.get(lingua) or titulo) if lingua != lingua_titulo else ideia
        paises.append({"codigo": codigo, "pais": PAISES[codigo][0], "lingua": lingua, "traduzido": traduzido,
                       "busca": palavras_da_busca(traduzido)})
    return {"titulo": titulo, "ideia": ideia, "paises": paises}


def _views(texto) -> int | None:
    """ "1.234.567 visualizações", "1,234,567 views": só os dígitos (a extensão manda o número completo)."""
    if isinstance(texto, (int, float)):
        return int(texto)
    digitos = re.sub(r"\D", "", str(texto or ""))
    return int(digitos) if digitos else None


def julgar(preparo: dict, resultados: dict, video_id: str = "") -> dict:
    """Os vídeos que a extensão achou em cada país viram o placar: já fizeram (forte, médio, fraco) ou ninguém fez."""
    titulo = str(preparo.get("titulo", ""))
    saida = []
    for x in preparo.get("paises", []):
        alvo = palavras(str(x.get("traduzido", "")))
        parecidos, quase = [], 0
        for a in (resultados.get(x["codigo"]) or [])[:60]:
            t = str(a.get("titulo", ""))
            if not t or a.get("id") == video_id or not na_lingua(t, x["lingua"]):
                continue
            nota = mesma_ideia(t, alvo, numeros(titulo))
            if nota >= PARECIDO:
                parecidos.append({"id": str(a.get("id", "")), "titulo": t, "canal": str(a.get("canal", "")),
                                  "views": _views(a.get("views")), "publicado": str(a.get("publicado", "")),
                                  "parecenca": round(nota, 2)})
            elif nota >= QUASE:
                quase += 1
        parecidos.sort(key=lambda v: -(v["views"] or 0))
        saida.append({"codigo": x["codigo"], "pais": x["pais"], "lingua": x["lingua"], "busca": x["busca"],
                      "feito": bool(parecidos), "parecidos": parecidos[:4], "quase": quase,
                      "forca": forca(parecidos[0]["views"]) if parecidos else "",
                      "link": f"https://www.youtube.com/results?search_query={x['busca'].replace(' ', '+')}"})
    return {"ideia": preparo.get("ideia", ""), "paises": saida, "livres": sum(1 for r in saida if not r["feito"])}
