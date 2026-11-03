"""O que pede um modelo: o título em outras línguas, o nicho do canal e se o canal mostra rosto.

Só o Groq (gratuito), revezando as GROQ_API_KEY. Sem chave ou fora do ar, cada função devolve vazio e o Radar segue."""
import itertools
import json
import re
import threading
import time

import httpx

from .config import MODELO_TEXTO, MODELO_VISAO, chaves_groq

URL = "https://api.groq.com/openai/v1/chat/completions"
_CLIENTE = httpx.Client(timeout=httpx.Timeout(60, connect=10))
_RODA = None
_TRAVA = threading.Lock()
_RECUSADAS = set()   # chaves que o Groq disse serem inválidas

LINGUAS = {
    "en": "inglês", "es": "espanhol", "pt": "português", "fr": "francês", "de": "alemão",
    "it": "italiano", "ja": "japonês", "ko": "coreano", "hi": "hindi",
}

NICHOS = [
    "Animais", "Vida Selvagem", "História", "Ciência", "Espaço", "Mistério", "Crimes Reais", "Curiosidades",
    "Finanças", "Negócios", "Tecnologia", "Saúde", "Psicologia", "Religião", "Mitologia", "Geografia", "Guerra",
    "Esportes", "Boxe e Luta", "Futebol", "Carros", "Comida", "Viagem", "Natureza", "Desenho Animado",
    "Ficção e Contos", "Música", "Games", "Infantil", "Motivação", "Direito", "Imóveis", "Economia", "Bilionários",
    "Geopolítica", "Outro",
]


def _chave() -> str | None:
    global _RODA
    chaves = chaves_groq()
    if not chaves:
        return None
    with _TRAVA:
        if _RODA is None:
            _RODA = itertools.cycle(chaves)
        for _ in range(len(chaves)):
            chave = next(_RODA)
            if chave not in _RECUSADAS:
                return chave
    return None


def _perguntar(modelo: str, sistema: str, conteudo, tentativas: int = 4, esperar: float = 0,
               saida: int = 600, temperatura: float = 0.2) -> dict | None:
    """esperar: quantos segundos, no total, vale esperar quando todas as chaves batem no limite do minuto (o garimpo
    roda sozinho e pode esperar; a extensão, não)."""
    for _ in range(tentativas):
        chave = _chave()
        if not chave:
            return None
        corpo = {"model": modelo, "temperature": temperatura, "max_completion_tokens": saida,
                 "response_format": {"type": "json_object"},
                 "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": conteudo}]}
        if "qwen" in modelo:
            corpo["reasoning_effort"] = "none"
        elif "gpt-oss" in modelo:
            corpo["reasoning_effort"] = "low"
        try:
            r = _CLIENTE.post(URL, json=corpo, headers={"Authorization": f"Bearer {chave}"})
        except httpx.HTTPError:
            continue
        if r.status_code == 200:
            try:
                return json.loads(r.json()["choices"][0]["message"]["content"])
            except (KeyError, ValueError, IndexError):
                continue
        if r.status_code in (401, 403):
            _RECUSADAS.add(chave)
            continue
        if r.status_code == 429 and esperar > 0:
            # o Groq diz em quantos segundos o minuto da chave volta
            m = re.search(r"try again in ([\d.]+)s", r.text)
            pausa = min(esperar, float(m.group(1)) + 1 if m else 15)
            esperar -= pausa
            time.sleep(pausa)
        # 429 e 5xx: a próxima chave da roda
    return None


def traduzir_titulo(titulo: str, linguas: list[str]) -> dict[str, str]:
    """O título como alguém daquela língua buscaria no YouTube (não palavra por palavra)."""
    pedido = {c: LINGUAS.get(c, c) for c in linguas}
    resposta = _perguntar(
        MODELO_TEXTO,
        "Você traduz títulos de vídeos do YouTube para buscar o mesmo assunto em outras línguas. Para cada código "
        "de língua, escreva a busca curta (3 a 8 palavras) que uma pessoa daquele país digitaria para achar um "
        "vídeo sobre o mesmo assunto. Sem aspas, sem emoji, sem hashtags. Responda só JSON: {\"codigo\": \"busca\"}.",
        f"Título: {titulo}\nLínguas: {json.dumps(pedido, ensure_ascii=False)}")
    if not resposta:
        return {}
    return {c: str(resposta[c]).strip()[:120] for c in linguas if isinstance(resposta.get(c), str) and resposta[c].strip()}


def _lista(cabecalho: str, itens: list[str]) -> str:
    return cabecalho + ":\n" + "\n".join(f"- {t}" for t in itens)


def nicho(titulo_canal: str, titulos: list[str], existentes: list[str] = ()) -> tuple[str, str]:
    """O nicho (um da lista) e o subnicho (2 a 4 palavras em português, o tipo exato de vídeo).

    existentes: os subnichos que já existem no Radar. Reaproveitar um deles é o que forma os Grupos de canais;
    sem isso cada canal ganhava um subnicho só dele ("Viagem Histórica", "História Documentada"...)."""
    ja = ("\n" + _lista("Subnichos que já existem (use exatamente um destes se o canal fizer o mesmo tipo de vídeo; "
                        "só crie um novo se nenhum servir)", list(existentes)[:80])) if existentes else ""
    resposta = _perguntar(
        MODELO_TEXTO,
        "Classifique um canal do YouTube pelos títulos dos vídeos. 'nicho': exatamente um da lista: "
        + ", ".join(NICHOS) + ". 'subnicho': o tipo exato de vídeo, de 2 a 4 palavras em português, do jeito que "
        "um produtor de canal sem rosto falaria (exemplos: 'Crime e Detetive', 'Animais Perigosos', 'Bíblia "
        "Explicada', 'Civilizações Antigas', 'Custo de Vida', 'Histórias de Terror'). Prefira um subnicho amplo o "
        "bastante para caber outros canais parecidos. Responda só JSON: "
        "{\"nicho\": \"...\", \"subnicho\": \"...\"}.",
        f"Canal: {titulo_canal}\n" + _lista("Títulos", titulos[:15]) + ja, esperar=60)
    escolhido = str((resposta or {}).get("nicho", "")).strip()
    sub = re.sub(r"\s+", " ", str((resposta or {}).get("subnicho", ""))).strip(" .")[:40]
    return (escolhido if escolhido in NICHOS else ""), (sub[:1].upper() + sub[1:] if sub else "")


def sugerir_termos(nicho_nome: str, titulos: list[str], quantos: int = 4) -> list[str]:
    """Buscas novas para o garimpo, tiradas dos títulos que estouraram: o garimpo aprende sozinho onde procurar."""
    resposta = _perguntar(
        MODELO_TEXTO,
        "Você ajuda a achar canais novos do YouTube. A partir dos títulos de vídeos que fizeram muito sucesso, "
        f"escreva {quantos} buscas curtas (2 a 5 palavras) que achariam OUTROS vídeos do mesmo tipo, sem nomes "
        "próprios de um vídeo só. Misture inglês, português e espanhol. Responda só JSON: {\"buscas\": [\"...\"]}.",
        f"Nicho: {nicho_nome}\n" + _lista("Títulos que estouraram", titulos[:20]), esperar=60)
    buscas = (resposta or {}).get("buscas", [])
    return [re.sub(r"\s+", " ", str(b)).strip()[:60] for b in buscas if isinstance(b, str) and 2 <= len(b.split()) <= 7][:quantos]


def gerar_titulos(tema: str, exemplos: list[str], lingua: str = "português", quantos: int = 10) -> list[str]:
    resposta = _perguntar(
        MODELO_TEXTO,
        "Você escreve títulos de vídeos do YouTube para canais sem rosto. Siga o estilo dos títulos que "
        "estouraram (tamanho, curiosidade, números, contraste), sem copiar nenhum. Até 70 letras cada, sem "
        "emoji, sem hashtag, sem clickbait mentiroso. Responda só JSON: {\"titulos\": [\"...\"]}.",
        f"Tema do vídeo: {tema}\nLíngua: {lingua}\nQuantos: {quantos}\n"
        + _lista("Títulos que estouraram neste nicho", exemplos[:25]), saida=1500, temperatura=0.8)
    return [str(t).strip()[:100] for t in (resposta or {}).get("titulos", []) if isinstance(t, str) and t.strip()][:quantos]


def escrever_pauta(tema: str, titulo: str, exemplos: list[str], minutos: int = 8, lingua: str = "português") -> dict:
    """Um rascunho de roteiro para a fábrica: texto corrido para narrar, com [TITULO] nas partes."""
    palavras = minutos * 150
    resposta = _perguntar(
        MODELO_TEXTO,
        "Você escreve roteiros narrados para canais sem rosto do YouTube. Texto corrido para ser lido por uma voz, "
        "sem indicações de cena, sem colchetes de câmera, sem emoji. Comece com um gancho forte nos primeiros 15 "
        "segundos. Divida em 3 a 6 partes, cada uma começando numa linha própria com '[TITULO] Nome da parte'. "
        "Use só fatos que você tem certeza; nada inventado sobre pessoas reais. Termine com um fechamento curto. "
        "Responda só JSON: {\"titulo\": \"...\", \"roteiro\": \"...\"}.",
        f"Tema: {tema}\nTítulo de referência: {titulo}\nLíngua: {lingua}\n"
        f"Tamanho: cerca de {palavras} palavras ({minutos} minutos narrados)\n"
        + _lista("Títulos que estouraram neste nicho", exemplos[:12]),
        saida=min(6000, int(palavras * 2.2) + 400), temperatura=0.7, esperar=60)
    if not resposta or not isinstance(resposta.get("roteiro"), str):
        return {}
    return {"titulo": str(resposta.get("titulo") or titulo).strip(), "roteiro": resposta["roteiro"].strip()}


def sem_rosto(capas: list[str]) -> bool | None:
    """True se as capas não mostram um apresentador que se repete. None quando não deu para saber."""
    if not capas:
        return None
    conteudo = [{"type": "text", "text":
                 "Estas são capas de vídeos do mesmo canal do YouTube. O canal é 'sem rosto' quando nenhuma pessoa "
                 "real aparece como apresentador recorrente (a mesma pessoa em várias capas, olhando para a câmera). "
                 "Fotos de figuras históricas, celebridades citadas, desenhos, animais ou pessoas diferentes em cada "
                 "capa não contam como apresentador. Responda só JSON: {\"apresentador\": true ou false}."}]
    conteudo += [{"type": "image_url", "image_url": {"url": url}} for url in capas[:3]]  # o Qwen do Groq aceita até 3 imagens
    resposta = _perguntar(MODELO_VISAO, "Você analisa capas de vídeos do YouTube. Responda só JSON.", conteudo,
                          esperar=90)
    if not resposta or not isinstance(resposta.get("apresentador"), bool):
        return None
    return not resposta["apresentador"]


def traduzir_exato(titulo: str, linguas: list[str]) -> dict[str, str]:
    """A tradução fiel do título, palavra por palavra no sentido, sem adaptar nada (pedido do usuário em 2026-10-14:
    "buscar o título exato no outro país, só sem os números")."""
    if not linguas:
        return {}
    pedido = {c: LINGUAS.get(c, c) for c in linguas}
    resposta = _perguntar(
        MODELO_TEXTO,
        "Traduza o título de um vídeo do YouTube para cada língua pedida, do jeito mais fiel possível: o mesmo título, "
        "com as mesmas palavras e a mesma ordem, sem resumir, sem adaptar lugares, sem acrescentar nada. Sem aspas. "
        "Responda só JSON: {\"codigo\": \"título traduzido\"}.",
        f"Título: {titulo}\nLínguas: {json.dumps(pedido, ensure_ascii=False)}", esperar=30)
    if not resposta:
        return {}
    return {c: str(resposta[c]).strip()[:150] for c in linguas if isinstance(resposta.get(c), str) and resposta[c].strip()}


def estruturas(titulos: list[str], lacunas: tuple[str, ...]) -> list[str]:
    """Os títulos que estouraram virados em estruturas genéricas (pedido do usuário em 2026-10-27): o gancho fica,
    o assunto vira lacuna, e nada de nome de lugar, marca ou número."""
    if not titulos:
        return []
    marcas = ", ".join("{" + l + "}" for l in lacunas)
    resposta = _perguntar(
        MODELO_TEXTO,
        "Você transforma títulos de vídeos do YouTube que fizeram sucesso em ESTRUTURAS genéricas, que sirvam para "
        f"qualquer nicho. Troque o assunto específico (nomes próprios, marcas, lugares, produtos, pessoas) por uma "
        f"destas lacunas: {marcas}. {{assunto}} é a coisa de que se fala; {{itens}}, coisas no plural; {{lugares}}, "
        "lugares ou empresas no plural; {publico}, quem assiste; {momento}, uma situação. Mantenha as palavras do "
        "gancho exatamente como estão, em inglês. Tire TODOS os números, anos e preços. Sem emoji. Títulos com o "
        "mesmo gancho viram uma estrutura só. Pule o título que não tem gancho (só um nome, só um assunto). "
        "Exemplo: 'Why 7 Walmart Stores Are Closing in 2026' vira '{lugares} Are Closing'. "
        "Responda só JSON: {\"estruturas\": [\"...\"]}.",
        _lista("Títulos", titulos[:30]), saida=1500, esperar=60)
    return [re.sub(r"\s+", " ", str(e)).strip()[:110]
            for e in (resposta or {}).get("estruturas", []) if isinstance(e, str) and e.strip()]


def vocabulario(tema: str, descricao: str = "", lacunas: tuple[str, ...] = ()) -> dict[str, list[str]]:
    """As palavras do nicho da pessoa para preencher as estruturas, em inglês (a busca vai para o YouTube dos EUA)."""
    resposta = _perguntar(
        MODELO_TEXTO,
        "Você ajuda um canal sem rosto do YouTube a buscar vídeos do mesmo nicho. Pelo tema do canal, escreva, EM "
        "INGLÊS, de 4 a 6 opções curtas (1 a 4 palavras) para cada lacuna, do jeito que aparecem em títulos de vídeos "
        "que estouram nesse nicho: 'assunto' (a coisa de que o canal fala: setores, marcas, mercados), 'itens' "
        "(coisas no plural), 'lugares' (lugares ou empresas no plural), 'publico' (quem assiste, no plural), "
        "'momento' (situações, como 'the economy crashes'). Prefira o concreto que aparece em títulos que "
        "estouram (marcas, redes, produtos, cargos: 'Walmart', 'Costco Members', 'Frozen Foods') ao abstrato "
        "('Consumer Behavior'). E 'palavras': de 20 a 30 palavras soltas, concretas, que aparecem nos títulos dos "
        "vídeos desse nicho e em nenhum outro (para animais: shark, lion, snake, predator, wildlife, dog...; para "
        "supermercado: walmart, costco, grocery, aldi, kroger...). Sem números. Nada fora do nicho. "
        "Responda só JSON: {\"assunto\": [...], \"itens\": [...], \"lugares\": [...], \"publico\": [...], "
        "\"momento\": [...], \"palavras\": [...]}.",
        f"Tema do canal: {tema}\nO que o canal faz: {descricao or '(não disse)'}", saida=1200, esperar=30)
    # o modelo às vezes devolve a chave em inglês ("items" no lugar de "itens")
    apelidos = {"itens": "items", "lugares": "places", "publico": "audience", "momento": "moments", "assunto": "subject"}
    saida = {}
    for l in lacunas:
        opcoes = (resposta or {}).get(l) or (resposta or {}).get(apelidos.get(l, l)) or []
        saida[l] = [re.sub(r"\s+", " ", str(o)).strip()[:40] for o in opcoes
                    if isinstance(o, str) and o.strip() and not re.search(r"\d", o)][:30 if l == "palavras" else 8]
    return saida


def buscas_das_estruturas(tema: str, descricao: str, vocab: dict, estruturas: list[str],
                          exemplos: list[str] = ()) -> dict:
    """As buscas do nicho da pessoa: cada estrutura de título adaptada ao nicho, e os ganchos típicos do nicho.

    Colar as palavras nas lacunas dava "Essential Horns Conservationists Will Stockpile" para quem escolheu animais
    (2026-10-27): a estrutura é de nicho de consumo. O que se aproveita dela é o TIPO de gancho (colapso, boicote,
    regra nova, pior e melhor), e o título tem de ser um que existe naquele nicho. Volta {"estruturas": {estrutura:
    [buscas]}, "ganchos": [buscas]}; estrutura que não dá para adaptar volta com a lista vazia."""
    if not estruturas:
        return {"estruturas": {}, "ganchos": []}
    numeradas = {str(i): e for i, e in enumerate(estruturas[:40])}
    resposta = _perguntar(
        MODELO_TEXTO,
        "Você escreve buscas para achar no YouTube os canais de sucesso de um nicho. Recebe estruturas de título "
        "(o gancho de vídeos que estouraram, com lacunas entre chaves), que podem ter vindo de OUTRO nicho.\n"
        "1) 'estruturas': para cada estrutura, escreva de 1 a 2 títulos EM INGLÊS que um vídeo de sucesso DESTE "
        "nicho teria, usando o MESMO TIPO de gancho (colapso, ninguém consegue salvar, boicote, regras mudando, pior "
        "e melhor, ganância, algo que fica valioso). Adapte as palavras do gancho para soar natural no nicho; o "
        "título tem de ser algo que existe de verdade nesse nicho, não uma colagem. Se o gancho não existe nesse "
        "nicho, devolva lista vazia.\n"
        "2) 'ganchos': 8 títulos EM INGLÊS no estilo dos que mais estouram NESTE nicho em canais sem rosto (os "
        "ganchos típicos dele), cada um com um gancho diferente.\n"
        "Sem números, sem nomes de canais. Responda só JSON: {\"estruturas\": {\"0\": [\"...\"], \"1\": []}, "
        "\"ganchos\": [\"...\"]}.",
        f"Tema do canal: {tema}\nO que o canal faz: {descricao or '(não disse)'}\n"
        f"Palavras do nicho: {json.dumps(vocab, ensure_ascii=False)}\n"
        # os títulos que mais renderam nos canais de referência da pessoa: o melhor retrato do estilo do nicho
        + (_lista("Títulos que estouraram nos canais que são o modelo da pessoa (escreva no mesmo estilo)",
                  list(exemplos)[:25]) + "\n" if exemplos else "")
        + _lista("Estruturas", [f"{i}: {e}" for i, e in numeradas.items()]),
        saida=4000, temperatura=0.5, esperar=60)
    limpar = lambda lista, ate: [re.sub(r"\s+", " ", str(t)).strip()[:100] for t in (lista or [])  # noqa: E731
                                 if isinstance(t, str) and t.strip() and "{" not in t and not re.search(r"\d", t)][:ate]
    por_numero = (resposta or {}).get("estruturas") or {}
    saida = {e: limpar(por_numero.get(i), 2) for i, e in numeradas.items()
             if isinstance(por_numero, dict) and isinstance(por_numero.get(i), list)}
    return {"estruturas": saida, "ganchos": limpar((resposta or {}).get("ganchos"), 10)}
