"""O que pede um modelo: o título em outras línguas, o nicho do canal e se o canal mostra rosto.

O Groq (gratuito), revezando as GROQ_API_KEY. Quando todas gastam a cota do dia, o mesmo pedido vai para o Gemini
(plano grátis, revezando as GEMINI_API_KEY). Sem chave ou fora do ar, cada função devolve vazio e o Radar segue."""
import base64
import itertools
import json
import re
import threading
import time

import httpx

from .config import MODELO_GEMINI, MODELO_TEXTO, MODELO_VISAO, chaves_gemini, chaves_groq

URL = "https://api.groq.com/openai/v1/chat/completions"
_CLIENTE = httpx.Client(timeout=httpx.Timeout(60, connect=10))
_RODA = None
_TRAVA = threading.Lock()
_RECUSADAS = set()   # chaves que o Groq disse serem inválidas
# (modelo, chave) -> o time.monotonic() em que a cota de tokens do dia volta. O limite do Groq de tokens por dia é por
# organização e por modelo e só volta em horas: esperar nele é esperar à toa (2026-11-01, o fim do garimpo gastava os
# 45 minutos inteiros dormindo 15 segundos por vez contra uma cota que só voltava no dia seguinte).
_ESGOTADAS: dict[tuple[str, str], float] = {}


def _espera_pedida(texto: str, cabecalhos=None) -> float | None:
    """Quantos segundos o Groq pede para esperar: o cabeçalho retry-after ou o "try again in 31m41.6s" da mensagem.

    A conta antiga procurava só um número seguido de "s" e não enxergava as horas nem os minutos: 31m41s virava 15
    segundos, e o garimpo dormia de 15 em 15 segundos contra uma cota que só voltava horas depois."""
    if cabecalhos is not None:
        try:
            return float(cabecalhos["retry-after"])
        except (KeyError, TypeError, ValueError):
            pass
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", texto)
    if not m:
        return None
    horas, minutos, segundos = m.groups()
    return int(horas or 0) * 3600 + int(minutos or 0) * 60 + float(segundos)


def esgotado(modelo: str) -> bool:
    """True quando toda chave do Groq já estourou a cota de tokens do dia desse modelo e o Gemini também está fora:
    nem vale perguntar."""
    return _groq_esgotado(modelo) and not _gemini_livre()


def _groq_esgotado(modelo: str) -> bool:
    chaves = [c for c in chaves_groq() if c not in _RECUSADAS]
    if not chaves:
        return True
    if not _ESGOTADAS:
        return False        # nenhuma chave estourou nada: nem olha o relógio
    agora = time.monotonic()
    return all(_ESGOTADAS.get((modelo, c), 0) > agora for c in chaves)


# ---------------------------------------------------------------- o Gemini, a reserva do Groq (2026-11-03)
# Pedido do usuário: "tem alguma outra IA que possa fazer esse papel do Groq?", "só o Gemini grátis". As 11 chaves do
# Groq gastavam a cota de tokens do dia e os canais novos ficavam sem nicho e sem rosto até o outro dia (264 numa
# tarde). O Gemini entende o mesmo pedido do Groq (o jeito da OpenAI); só a capa vai junto em base64, não pelo link.

URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
_GEMINI_FORA: dict[str, float] = {}     # chave -> o time.monotonic() em que o limite dela volta
_VEZ_GEMINI = itertools.count()


def _gemini_livre() -> bool:
    agora = time.monotonic()
    return any(_GEMINI_FORA.get(c, 0) <= agora for c in chaves_gemini() if c not in _RECUSADAS)


def _espera_gemini(texto: str) -> float:
    """O Gemini diz quanto esperar no retryDelay ("37s"); o limite do dia (PerDay) só volta à meia-noite do Pacífico."""
    m = re.search(r'"retryDelay":\s*"([\d.]+)s"', texto)
    return 3600 if "PerDay" in texto or not m else float(m.group(1)) + 1


def _capas_embutidas(conteudo):
    if not isinstance(conteudo, list):
        return conteudo
    saida = []
    for parte in conteudo:
        url = (parte.get("image_url") or {}).get("url", "") if parte.get("type") == "image_url" else ""
        if url.startswith("http"):
            try:
                r = _CLIENTE.get(url, timeout=15)
            except httpx.HTTPError:
                continue
            if r.status_code != 200:
                continue        # capa que não existe mais fica de fora, em vez de o pedido inteiro ser recusado
            tipo = r.headers.get("content-type", "image/jpeg").split(";")[0]
            parte = {"type": "image_url",
                     "image_url": {"url": f"data:{tipo};base64," + base64.b64encode(r.content).decode()}}
        saida.append(parte)
    return saida


def _gemini(sistema: str, conteudo, saida: int, temperatura: float) -> dict | None:
    chaves = [c for c in chaves_gemini() if c not in _RECUSADAS]
    if not chaves or not _gemini_livre():
        return None
    conteudo = _capas_embutidas(conteudo)
    inicio = next(_VEZ_GEMINI)
    for chave in chaves[inicio % len(chaves):] + chaves[:inicio % len(chaves)]:
        if _GEMINI_FORA.get(chave, 0) > time.monotonic():
            continue
        corpo = {"model": MODELO_GEMINI, "temperature": temperatura, "max_tokens": saida,
                 "response_format": {"type": "json_object"},
                 "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": conteudo}]}
        try:
            r = _CLIENTE.post(URL_GEMINI, json=corpo, headers={"Authorization": f"Bearer {chave}"}, timeout=40)
        except httpx.HTTPError:
            continue
        if r.status_code == 200:
            try:
                resposta = json.loads(r.json()["choices"][0]["message"]["content"])
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            return resposta if isinstance(resposta, dict) else None
        if r.status_code in (401, 403):
            _RECUSADAS.add(chave)
            continue
        if r.status_code == 400:
            return None
        if r.status_code == 429:
            _GEMINI_FORA[chave] = time.monotonic() + _espera_gemini(r.text)
        # 429 e 5xx (o Gemini dá 503 quando está cheio): a próxima chave
    return None


LINGUAS = {
    "en": "inglês", "es": "espanhol", "pt": "português", "fr": "francês", "de": "alemão",
    "it": "italiano", "ja": "japonês", "ko": "coreano", "hi": "hindi", "nl": "holandês", "pl": "polonês",
    "tr": "turco",
}

NICHOS = [
    "Animais", "Vida Selvagem", "História", "Ciência", "Espaço", "Mistério", "Crimes Reais", "Curiosidades",
    "Finanças", "Negócios", "Tecnologia", "Saúde", "Psicologia", "Religião", "Mitologia", "Geografia", "Guerra",
    "Esportes", "Boxe e Luta", "Futebol", "Carros", "Comida", "Viagem", "Natureza", "Desenho Animado",
    "Ficção e Contos", "Música", "Games", "Infantil", "Motivação", "Direito", "Imóveis", "Economia", "Bilionários",
    "Geopolítica", "Outro",
]


def _chave(modelo: str = "") -> str | None:
    global _RODA
    chaves = chaves_groq()
    if not chaves:
        return None
    agora = time.monotonic()
    with _TRAVA:
        if _RODA is None:
            _RODA = itertools.cycle(chaves)
        for _ in range(len(chaves)):
            chave = next(_RODA)
            if chave in _RECUSADAS or _ESGOTADAS.get((modelo, chave), 0) > agora:
                continue
            return chave
    return None


def _perguntar(modelo: str, sistema: str, conteudo, tentativas: int = 4, esperar: float = 0,
               saida: int = 600, temperatura: float = 0.2) -> dict | None:
    """esperar: quantos segundos, no total, vale esperar quando todas as chaves batem no limite do minuto (o garimpo
    roda sozinho e pode esperar; a extensão, não)."""
    restantes = tentativas
    while restantes > 0:
        restantes -= 1
        chave = _chave(modelo)
        if not chave:
            return _gemini(sistema, conteudo, saida, temperatura)
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
        if r.status_code == 400:
            return None     # pedido recusado (capa que não existe mais): é o mesmo em toda chave
        if r.status_code == 429:
            espera = _espera_pedida(r.text, r.headers)
            # cota de tokens do dia, ou uma pausa mais longa do que vale esperar: a chave sai da roda até voltar
            if "per day" in r.text or (espera or 0) > esperar:
                _ESGOTADAS[(modelo, chave)] = time.monotonic() + (espera or 3600)
                restantes += 1      # a chave saiu da roda sem responder: não gasta tentativa
                continue
            if esperar > 0:     # o limite do minuto: vale esperar o que o Groq pediu
                pausa = min(esperar, (espera or 15) + 1)
                esperar -= pausa
                time.sleep(pausa)
        # 5xx: a próxima chave da roda
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
        "próprios de um vídeo só. Escreva todas em inglês, mesmo que os títulos estejam em outra língua. Responda só "
        "JSON: {\"buscas\": [\"...\"]}.",
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


def _existe(url: str) -> bool:
    try:
        return _CLIENTE.head(url, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


def sem_rosto(capas: list[str]) -> bool | None:
    """True se as capas não mostram um apresentador que se repete. None quando não deu para saber."""
    # capa de vídeo apagado dá 404 e o Groq recusa o pedido inteiro: o canal ficava sem resposta para sempre
    capas = [url for url in capas if _existe(url)][:3]
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


def regionalizar(titulo: str, alvos: dict[str, tuple[str, str]], acrescentar: bool = False) -> dict | None:
    """O título reescrito para cada país, com o lugar trocado pelo país (pedido do usuário em 2026-11-03: "mercados
    do Canadá e dos EUA são diferentes", "invenções do Japão e invenções da China"). `alvos` = {código: (país,
    língua)}. `acrescentar`: título que não fala de lugar ganha o país mesmo assim ("Animais bizarros" vira "Animais
    bizarros do Brasil"). Devolve {"lugar": "Canadá", "titulos": {código: título}, "marcas": {código: ["Brasil",
    "brasileiro", ...]}}: as marcas são os jeitos de escrever o país naquela língua, para conferir se o vídeo achado
    fala dele. Lugar "" = o título não fala de lugar. None = o Groq falhou."""
    pedido = {c: {"pais": p, "lingua": LINGUAS.get(l, l)} for c, (p, l) in alvos.items()}
    sem_lugar = ("Se o título não fala de lugar nenhum, devolva lugar vazio e, para cada país pedido, o título "
                 "traduzido com o país acrescentado do jeito mais natural (\"Animais bizarros que parecem de outro "
                 "mundo\" para Brasil vira \"Animais bizarros do Brasil que parecem de outro mundo\"). "
                 if acrescentar else "Se o título não fala de lugar nenhum, devolva lugar vazio e nenhum título. ")
    resposta = _perguntar(
        MODELO_TEXTO,
        "O título de um vídeo do YouTube fala de um lugar específico (país, cidade, região ou povo/nacionalidade)? "
        "Se fala, reescreva o título para cada país pedido, na língua pedida, trocando esse lugar pelo país pedido e "
        "mantendo todo o resto fiel ao original (as mesmas palavras e a mesma ordem, sem números). Exemplo: "
        "\"Supermercados do Canadá que faliram\" para Estados Unidos em inglês vira \"Supermarkets in the USA that went "
        "bankrupt\"; \"Invenções japonesas que mudaram o mundo\" para Brasil em português vira \"Invenções brasileiras "
        "que mudaram o mundo\". Troque também o povo, o adjetivo, as cidades e os estados do lugar pelos do país pedido, "
        "com o artigo certo: \"Why Americans Are Leaving California\" para Reino Unido vira \"Why Brits Are Leaving "
        "Britain\". Não inclua o país do lugar do título (o Japão no exemplo das invenções; os EUA no da Califórnia). "
        + sem_lugar +
        "Para cada título, dê também as marcas: os jeitos de escrever aquele país na língua do título (nome, sigla, "
        "adjetivo e povo, ex.: [\"USA\", \"United States\", \"America\", \"American\", \"Americans\"]), sem códigos de "
        "duas letras como BR ou ES. "
        "Responda só JSON: {\"lugar\": \"o lugar do título ou vazio\", \"titulos\": {\"codigo\": \"título\"}, "
        "\"marcas\": {\"codigo\": [\"...\"]}}.",
        f"Título: {titulo}\nPaíses: {json.dumps(pedido, ensure_ascii=False)}", esperar=30, saida=2000)
    if not isinstance(resposta, dict):
        return None
    lugar = str(resposta.get("lugar") or "").strip()[:60]
    titulos = resposta.get("titulos") if (lugar or acrescentar) and isinstance(resposta.get("titulos"), dict) else {}
    titulos = {c: str(t).strip()[:150] for c, t in titulos.items() if c in alvos and isinstance(t, str) and t.strip()}
    marcas = resposta.get("marcas") if isinstance(resposta.get("marcas"), dict) else {}
    return {"lugar": lugar, "titulos": titulos,
            # sigla de duas letras, só UK, US e NZ: "es", "fr" e "br" aparecem em qualquer título
            "marcas": {c: [str(m).strip()[:40] for m in ms
                           if isinstance(m, str) and (len(m.strip()) > 2 or m.strip() in ("UK", "US", "NZ"))][:8]
                       for c, ms in marcas.items() if c in titulos and isinstance(ms, list)}}
