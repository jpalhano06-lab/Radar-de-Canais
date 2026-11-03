"""As estruturas de título: o esqueleto do gancho que faz um vídeo estourar, sem o assunto dele.

Pedido do usuário em 2026-10-27: a busca no YouTube precisa ser certeira, não a de um perfil "virgem" que digita
uma palavra solta. A API do YouTube não tem perfil (a mesma busca dá o mesmo resultado para qualquer chave), então o
que deixa a busca certeira é o que vai nela. E o que vai nela são estruturas como as que ele trouxe:

    "Millions of People Are Now Boycotting ___", "___ That Got Too Greedy and Are Already Closing"

Sem nome de lugar, sem marca e **sem número** ("retire os números também"). E genéricas: a estrutura é a mesma para
qualquer nicho; o que muda são as lacunas, que o nicho da pessoa preenche (o formulário do "Meu nicho"). Buscar a
estrutura preenchida acha vídeos com o mesmo gancho no assunto da pessoa, e os canais deles são os que interessam.

As lacunas são sempre estas cinco (o Groq preenche e a pessoa corrige):
- {assunto}: a coisa de que o canal fala (uma marca, um setor, um mercado, um lugar inteiro)
- {itens}: coisas no plural (produtos, ações, carros, comidas)
- {lugares}: lugares ou empresas no plural (lojas, restaurantes, bancos, cidades)
- {publico}: quem assiste (aposentados, famílias, investidores)
- {momento}: uma situação ("the economy crashes", "winter arrives")

As da lista abaixo são a partida. O garimpo aprende outras com os títulos que estouraram (`aprender`).
"""
import random
import re

from . import banco, ia

LACUNAS = ("assunto", "itens", "lugares", "publico", "momento")

# a partida: as estruturas da imagem do usuário, já sem nomes e sem números, com as lacunas no lugar do assunto
PARTIDA = [
    "{assunto} Is Collapsing And Nobody Can Save It",
    "{itens} That Destroy Premium Brands",
    "When {momento}, These {itens} Become Priceless",
    "Worst and Best {lugares}",
    "Essential {itens} {publico} Will Stockpile (Buy Now or Regret It)",
    "Millions of People Are Now Boycotting {assunto}",
    "Big Changes Coming That {publico} Should Know First",
    "New Rules Coming (Don't Lose Your {assunto})",
    "{lugares} That Got Too Greedy and Are Already Closing",
]

MAX_APRENDIDAS = 300
NOTA_PARA_APRENDER = 5.0    # só o título que fez 5x o normal do canal vira estrutura


# ---------------------------------------------------------------- o esqueleto de um título

_NUMERO = re.compile(r"[$€£R]*\d[\d.,:%]*(?:st|nd|rd|th|k|m|x|s)?\b", re.I)
_SOBRA = re.compile(r"[^\w\s'(){}\-—,!?]")


def sem_numeros(texto: str) -> str:
    """Tira números, anos, preços e porcentagens, e o que fica solto depois ("( )", "— —", espaço duplo)."""
    t = _NUMERO.sub(" ", texto)
    t = _SOBRA.sub(" ", t)                         # emoji, aspas, barras
    t = re.sub(r"\(\s*\)", " ", t)
    t = re.sub(r"\s*[—-]\s*(?=[—-]|$)", " ", t)    # travessão que ficou sem nada do lado
    t = re.sub(r"\s+([,!?)])", r"\1", t)
    t = re.sub(r"\(\s+", "(", t)
    return re.sub(r"\s+", " ", t).strip(" -—,")


def lacunas_de(estrutura: str) -> list[str]:
    return [l for l in re.findall(r"\{(\w+)\}", estrutura) if l in LACUNAS]


def fixas(estrutura: str) -> list[str]:
    """As palavras do gancho (o que não é lacuna), minúsculas: é o que um título precisa ter para casar."""
    return re.findall(r"[a-z']{2,}", re.sub(r"\{\w+\}", " ", estrutura.lower()))


def valida(estrutura: str) -> bool:
    """Estrutura que serve: tem lacuna, não tem número e tem gancho de verdade (3 palavras fixas ou mais)."""
    return (bool(lacunas_de(estrutura)) and not re.search(r"\d", estrutura)
            and not re.search(r"\{(?!(?:" + "|".join(LACUNAS) + r")\})", estrutura)
            and len(fixas(estrutura)) >= 3 and len(estrutura) <= 110)


def casa(titulo: str, estrutura: str) -> float:
    """Quanto do gancho da estrutura o título tem, de 0 a 1 (as palavras fixas que aparecem nele)."""
    palavras = fixas(estrutura)
    if not palavras:
        return 0.0
    do_titulo = set(re.findall(r"[a-z']{2,}", titulo.lower()))
    return sum(1 for p in palavras if p in do_titulo) / len(palavras)


# ---------------------------------------------------------------- preencher

def preencher(estrutura: str, vocab: dict, sorteio: random.Random | None = None) -> str:
    """A estrutura com cada lacuna trocada por uma palavra do nicho. Lacuna sem palavra: devolve "" (não dá para
    buscar "Worst and Best {lugares}")."""
    s = sorteio or random.Random()
    texto = estrutura
    for lacuna in lacunas_de(estrutura):
        opcoes = [o for o in vocab.get(lacuna, []) if o]
        if not opcoes:
            return ""
        texto = texto.replace("{" + lacuna + "}", s.choice(opcoes), 1)
    return texto


def busca(texto: str) -> str:
    """A estrutura preenchida como vai para o YouTube: sem parênteses e pontuação (a busca não precisa deles)."""
    t = re.sub(r"[()!?,—\"]", " ", texto)
    return re.sub(r"\s+", " ", t).strip()[:100]


# ---------------------------------------------------------------- o banco de estruturas

def todas() -> list[dict]:
    """As da partida e as aprendidas, com quanto cada uma já rendeu (canais que entraram por busca)."""
    feitas = {l["texto"]: l for l in banco.todos("SELECT * FROM estruturas")}
    saida = []
    for texto in PARTIDA:
        saida.append({"texto": texto, "origem": "partida", "vezes": 0, "canais": 0} | feitas.pop(texto, {}))
    saida += [l for l in feitas.values()]
    return saida


def _rendeu(e: dict) -> float:
    return (e.get("canais") or 0) / max(1, e.get("vezes") or 0)


def escolher(vocab: dict, quantas: int, desligadas: list[str] = (), tentativa: int = 0,
             prontas: dict | None = None) -> list[tuple[str, str]]:
    """As próximas estruturas para buscar, já preenchidas: (estrutura, busca).

    As nunca buscadas primeiro, depois as que mais renderam. A cada tentativa a lista anda, para o "procurar de
    novo" não repetir a mesma busca. Com `prontas` (as buscas que o Groq escreveu para o nicho), só entram as
    estruturas que têm busca pronta, e a busca é uma delas; sem, as lacunas são sorteadas do vocabulário."""
    if prontas:
        usaveis = [e for e in todas() if e["texto"] not in desligadas and prontas.get(e["texto"])]
        usaveis.sort(key=lambda e: ((e.get("vezes") or 0) > 0, -_rendeu(e)))
        if not usaveis:
            return []
        inicio = (tentativa * quantas) % len(usaveis)
        volta = tentativa * quantas // len(usaveis)          # cada volta inteira na lista usa a próxima busca pronta
        roda = (usaveis[inicio:] + usaveis[:inicio])[:quantas]
        return [(e["texto"], busca(prontas[e["texto"]][volta % len(prontas[e["texto"]])])) for e in roda]
    usaveis = [e for e in todas() if e["texto"] not in desligadas
               and all(vocab.get(l) for l in lacunas_de(e["texto"]))]
    usaveis.sort(key=lambda e: ((e.get("vezes") or 0) > 0, -_rendeu(e)))
    if not usaveis:
        return []
    inicio = (tentativa * quantas) % len(usaveis)
    roda = usaveis[inicio:] + usaveis[:inicio]
    sorteio = random.Random(tentativa)
    saida = []
    for e in roda[:quantas]:
        cheia = preencher(e["texto"], vocab, sorteio)
        if cheia:
            saida.append((e["texto"], busca(cheia)))
    return saida


def registrar(estrutura: str, canais: int, origem: str = "partida") -> None:
    """Quanto a estrutura rendeu: o próximo "procurar" gasta nas que trazem canal."""
    antes = banco.um("SELECT vezes, canais FROM estruturas WHERE texto=?", estrutura)
    if antes:
        banco.executar("UPDATE estruturas SET vezes=?, canais=?, usada=? WHERE texto=?",
                       antes["vezes"] + 1, antes["canais"] + canais, banco.agora(), estrutura)
    else:
        banco.executar("INSERT INTO estruturas (texto, origem, vezes, canais, criado, usada) VALUES (?,?,?,?,?,?)",
                       estrutura, origem, 1, canais, banco.agora(), banco.agora())


def aprender(log=print, quantos: int = 30) -> int:
    """Os títulos que estouraram (5x o normal) viram estruturas novas: o Groq tira o assunto, a conta tira os
    números, e só fica a que tem gancho. Não gasta cota do YouTube."""
    if banco.um("SELECT COUNT(*) AS n FROM estruturas WHERE origem='aprendida'")["n"] >= MAX_APRENDIDAS:
        return 0
    titulos = [l["titulo"] for l in banco.todos(
        "SELECT v.titulo FROM outliers o JOIN videos v ON v.id=o.video_id WHERE o.nota >= ? "
        "ORDER BY o.achado DESC LIMIT ?", NOTA_PARA_APRENDER, quantos)]
    if not titulos:
        return 0
    existentes = {e["texto"].lower() for e in todas()}
    novas = 0
    for e in ia.estruturas([sem_numeros(t) for t in titulos], LACUNAS):
        e = sem_numeros(e)
        if valida(e) and e.lower() not in existentes:
            banco.executar("INSERT OR IGNORE INTO estruturas (texto, origem, vezes, canais, criado, usada) "
                           "VALUES (?,?,?,?,?,?)", e, "aprendida", 0, 0, banco.agora(), "")
            existentes.add(e.lower())
            novas += 1
    if novas:
        log(f"{novas} estruturas de título novas aprendidas com os vídeos que estouraram")
    return novas
