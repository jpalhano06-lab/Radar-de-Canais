"""Roteiro pelo Claude: o título escolhido, o tempo e o vídeo de referência (a transcrição dele vira a base e a
thumbnail é copiada).

Pedido do usuário em 2026-10-14. Quem escreve é o Claude Code deste computador (`claude -p`), pela assinatura do
claude.ai: sem chave de API, sem custo por uso (gasta o limite da assinatura). A chave ANTHROPIC_API_KEY é tirada do
ambiente antes de chamar, senão o Claude Code cobraria por ela. Os "projetos" são as instruções de estilo do canal,
guardadas aqui (o claude.ai não deixa ler os projetos de lá por fora), e vão junto em todo roteiro."""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import uuid
from datetime import datetime

import httpx

from . import banco, claude_projetos
from .config import DADOS, FABRICA as _FABRICA

PASTA = DADOS / "roteiros"
VAZIA = DADOS / "claude"          # o Claude roda numa pasta vazia, para não ler nenhum CLAUDE.md
PALAVRAS_POR_MINUTO = 150
LETRAS_POR_PALAVRA = 2  # japonês e chinês: 300 letras por minuto, a conta do agente do canal, são as 150 palavras
_SEM_ESPACO = re.compile("[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uff66-\uff9d]")   # kana e kanji
_PONTUACAO_SEM_ESPACO = re.compile("[\u3000-\u303f\uff00-\uff65]")                     # 。、！？「」 e companhia
_TAREFAS: dict[str, dict] = {}
_TRAVA = threading.Lock()


def id_do_video(link: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([\w-]{11})", link or "")
    if m:
        return m.group(1)
    return link.strip() if re.fullmatch(r"[\w-]{11}", (link or "").strip()) else None


def transcricao(video_id: str) -> tuple[str, str]:
    """O texto falado do vídeo e a língua. Prefere a legenda feita à mão; senão a automática; em qualquer língua."""
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    try:
        disponiveis = list(api.list(video_id))
    except Exception as erro:
        raise RuntimeError("Não consegui ler a legenda desse vídeo (ele pode não ter legenda, ou o YouTube bloqueou "
                           f"a leitura agora). Detalhe: {str(erro)[:120]}")
    if not disponiveis:
        raise RuntimeError("Esse vídeo não tem legenda, nem automática.")
    preferidas = ["pt", "pt-BR", "en", "es"]
    escolhida = sorted(disponiveis, key=lambda t: (t.is_generated,
                                                   preferidas.index(t.language_code) if t.language_code in preferidas else 9))[0]
    trechos = escolhida.fetch()
    texto = re.sub(r"\s+", " ", " ".join(s.text for s in trechos)).strip()
    return texto, escolhida.language_code


def tem_legenda(video_id: str) -> bool:
    """Se dá para ler a legenda desse vídeo. A Nova produção da extensão pergunta isso na confirmação, para a pessoa
    saber antes de criar que o roteiro vai sair só do título (pedido do usuário em 2026-10-28)."""
    from youtube_transcript_api import YouTubeTranscriptApi
    try:
        return bool(list(YouTubeTranscriptApi().list(video_id)))
    except Exception:
        return False


def copiar_thumbnail(video_id: str, destino) -> bool:
    for nome in ("maxresdefault", "sddefault", "hqdefault"):
        r = httpx.get(f"https://i.ytimg.com/vi/{video_id}/{nome}.jpg", timeout=20)
        if r.status_code == 200 and len(r.content) > 5000:
            destino.write_bytes(r.content)
            return True
    return False


def contar_palavras(texto: str) -> int:
    """O tamanho do texto em palavras faladas. Japonês e chinês não separam palavras com espaço: `split()` contava um
    parágrafo inteiro como uma palavra, então 4.500 letras (15 min) pareciam 30 palavras (2026-11-04)."""
    letras = len(_SEM_ESPACO.findall(texto))
    resto = _PONTUACAO_SEM_ESPACO.sub(" ", _SEM_ESPACO.sub(" ", texto))
    return len(resto.split()) + round(letras / LETRAS_POR_PALAVRA)


def _tamanho(palavras: int, lingua: str) -> str:
    """O tamanho como o Claude entende nesta língua: em japonês e chinês o que se conta são os caracteres."""
    if codigo_da_lingua(lingua) in ("ja", "zh"):
        return f"{palavras * LETRAS_POR_PALAVRA} caracteres"
    return f"{palavras} palavras"


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")[:50] or "roteiro"


INSTRUCOES = """Você é roteirista de canais sem rosto do YouTube. Escreve o texto que uma voz vai narrar, do começo ao fim.

Regras:
- Responda SÓ com o roteiro. Nada antes nem depois: sem "Aqui está", sem comentários, sem markdown, sem asteriscos.
- É um script LIMPO para narração: só as frases que a voz vai falar, em parágrafos. Nenhum título de parte, nenhum
  subtítulo, nenhuma numeração de seção, nenhum colchete, nenhuma indicação de cena, câmera, música ou efeito.
- A passagem de um assunto para o outro é feita pela própria fala (uma frase de ligação), nunca por um título.
- Os primeiros 15 segundos são um gancho forte que segura quem chegou pelo título.
- A transcrição do vídeo de referência é a BASE: use a estrutura, os fatos e o que fez o vídeo funcionar. Não copie
  frases: reescreva com palavras próprias, melhore o ritmo e acrescente o que faltar para cumprir o título.
- Só fatos de que você tem certeza. Nada inventado sobre pessoas reais. Número, data e nome só se estiverem certos.
- Termine com um fechamento curto.
- Respeite o tamanho pedido (palavras ou caracteres), porque ele vira o tempo do vídeo."""

# vai no FIM do sistema, depois das instruções do canal: é a última palavra, e vale por cima delas
SEM_PERGUNTA = """

Por último, e por cima de QUALQUER instrução acima, inclusive as do projeto: quem pede este roteiro é um programa (o
Radar), não uma pessoa. NINGUÉM vai ler nem responder pergunta nenhuma, e tudo que você responder aqui vira a
narração do vídeo, falada por uma voz.
- Nunca pergunte, nunca peça confirmação e nunca espere resposta: nem sobre a duração, nem sobre o formato, nem sobre
  a fonte de nada. Uma instrução do projeto que mande perguntar antes de escrever não vale aqui.
- Tudo de que você precisa está neste pedido: o título, a língua, o tamanho em palavras e em minutos, as observações
  e a transcrição da referência.
- O que faltar, você mesmo decide pelo estilo do canal e segue escrevendo. Faltando base para um fato, escreva sem
  ele, nunca uma pergunta no lugar.
- A resposta é SEMPRE o roteiro inteiro, pronto para narrar."""

MINIMO_RASCUNHO = 50    # menos palavras do que isto não é roteiro: é uma pergunta, uma recusa ou uma resposta vazia
MINIMO_LETRAS = 400     # ... e o japonês não separa palavras com espaço, então o piso conta as letras também


def _parece_pergunta(texto: str) -> bool:
    """Isto é um roteiro ou é o Claude falando com a gente? Pergunta é o que o roteiro de narração nunca é: curto e
    cheio de linhas que terminam em "?" (o vídeo japonês do cobre saiu com oito perguntas numeradas narradas)."""
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    if not linhas or len(texto.split()) > 600:
        return False
    perguntas = sum(1 for l in linhas if l.endswith("?"))
    return perguntas >= 3 and perguntas >= len(linhas) * 0.3


def _tem_roteiro(texto: str) -> bool:
    """Tem texto bastante para ser um roteiro (ou o começo de um). Conta palavras E letras: em japonês e em chinês
    um parágrafo inteiro vem sem espaço nenhum e `split()` o conta como uma palavra só."""
    return contar_palavras(texto) >= MINIMO_RASCUNHO or len(texto.strip()) >= MINIMO_LETRAS


def _claude(sistema: str, pedido: str, modelo: str = "") -> str:
    executavel = shutil.which("claude")
    if not executavel:
        raise RuntimeError("O Claude Code não está instalado neste computador (comando claude).")
    VAZIA.mkdir(parents=True, exist_ok=True)
    ambiente = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    # as instruções vão por arquivo, não na linha de comando: o Windows corta a linha em 32 mil letras e o agente
    # JAN DE WOLF sozinho tem 33 mil (com os arquivos do projeto do claude.ai, passa de 100 mil)
    arquivo = VAZIA / f"sistema-{uuid.uuid4().hex[:8]}.txt"
    arquivo.write_text(sistema, encoding="utf-8")
    comando = [executavel, "-p", "--output-format", "json", "--system-prompt-file", str(arquivo), "--tools", "",
               "--strict-mcp-config", "--no-session-persistence"]
    if modelo:
        comando += ["--model", modelo]
    try:
        r = subprocess.run(comando, input=pedido, capture_output=True, text=True, encoding="utf-8", cwd=VAZIA,
                           env=ambiente, timeout=900)
    finally:
        arquivo.unlink(missing_ok=True)
    try:
        dados = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError("O Claude Code não respondeu. Ele está logado? Rode `claude` no terminal e digite /login. "
                           + (r.stderr or "")[:200])
    if dados.get("is_error"):
        raise RuntimeError("O Claude Code recusou: " + str(dados.get("result", ""))[:300])
    return str(dados.get("result", "")).strip()


# linha que é título de parte e não fala: "[TITULO] A fuga", "## Parte 2", "Introdução", "1. O começo"
_TITULO = re.compile(r"^\s*(\[[^\]]*\].*|#+.*|(parte|cap[ií]tulo|se[cç][aã]o|bloco)\s*\d+.*|"
                     r"(introdu[cç][aã]o|conclus[aã]o|fechamento|gancho|abertura|encerramento)\s*:?)\s*$", re.I)


def _limpar(texto: str) -> str:
    """Deixa só o que a voz fala. Pedido do usuário em 2026-10-14: o roteiro vinha com "[TITULO] ..." no meio, e o
    script tem que ser limpo para narração."""
    texto = re.sub(r"^\s*(aqui está|segue)[^\n]*\n", "", texto, flags=re.I)
    texto = re.sub(r"\*\*|__|`", "", texto)
    linhas = []
    for linha in texto.splitlines():
        limpa = linha.strip()
        if _TITULO.match(limpa):
            continue
        # linha curta sem pontuação no fim, sozinha entre linhas vazias, é título ("A fuga", "Por que elas trapaceiam").
        # A conta e o fim de frase valem para o japonês também: com `split()` e sem o 。, todo parágrafo japonês virava
        # "título" e era apagado, e o roteiro inteiro chegava vazio (2026-11-04)
        if limpa and contar_palavras(limpa) <= 7 and not re.search(r"[.!?…:;,\"”)。！？」』）]$", limpa):
            continue
        linhas.append(limpa)
    texto = "\n".join(linhas)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


# o alfabeto de cada língua que não escreve em latim: é por ele que o Radar confere se o título voltou MESMO na
# língua pedida (2026-11-03: o título japonês do vídeo de referência voltava traduzido para o português, porque
# "Língua: japonês" dava para o modelo entender "a língua do título é japonês")
_ALFABETOS = {
    "ja": ((0x3040, 0x30FF), (0x4E00, 0x9FFF)), "zh": ((0x4E00, 0x9FFF),),
    "ko": ((0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7AF)),
    "ru": ((0x0400, 0x04FF),), "uk": ((0x0400, 0x04FF),), "bg": ((0x0400, 0x04FF),),
    "ar": ((0x0600, 0x06FF),), "hi": ((0x0900, 0x097F),), "ta": ((0x0B80, 0x0BFF),), "el": ((0x0370, 0x03FF),),
}


def codigo_da_lingua(lingua: str) -> str:
    """"japonês" -> "ja". "" quando o nome não é de nenhuma das línguas das vozes da fábrica."""
    from .fabrica_api import IDIOMA
    lingua = (lingua or "").strip().lower()
    return IDIOMA.get(lingua, lingua if lingua in IDIOMA.values() else "")


def _escrito_em(texto: str, codigo: str) -> bool:
    """A maior parte das letras do texto é do alfabeto desta língua? Para o roteiro inteiro, que pode citar o título
    em outro alfabeto. Língua de alfabeto latino sempre passa: aqui não dá para saber."""
    faixas = _ALFABETOS.get(codigo)
    letras = [c for c in texto if c.isalpha()]
    if not faixas or not letras:
        return True
    return sum(1 for c in letras if any(a <= ord(c) <= b for a, b in faixas)) >= len(letras) / 2


def _na_lingua(titulo: str, codigo: str) -> bool | None:
    """O título está escrito nesta língua? None quando não dá para saber (duas línguas do mesmo alfabeto latino)."""
    faixas = _ALFABETOS.get(codigo)
    if faixas:
        return sum(1 for c in titulo if any(a <= ord(c) <= b for a, b in faixas)) >= 2
    if codigo in ("pt", "en", "es"):
        from . import gosto
        vista = gosto.lingua(titulo)
        return None if vista in ("?", "outras") else vista == codigo
    # língua de alfabeto latino sem lista de palavras (holandês, polonês...): pelo menos não voltou em outro alfabeto
    if any(ord(c) > 0x024F for c in titulo if c.isalpha()):
        return False
    return None


_SISTEMA_TITULO = (
    "Você escreve o título de um vídeo do YouTube na língua de destino que o pedido indica. O título que chega pode "
    "estar em QUALQUER língua: isso não importa, e a língua dele nunca é a língua de destino da resposta. Responda só "
    "com o título escrito na língua de destino, no alfabeto dela (nada de transliterar para o nosso alfabeto), numa "
    "linha, sem aspas e sem explicação. Mantenha o tom chamativo, os números e os nomes próprios. Se o título já "
    "estiver escrito na língua de destino, devolva-o igual.")


def traduzir_titulo(titulo: str, lingua: str) -> str:
    """O título na língua falada no vídeo (pedido do usuário em 2026-10-29: "o título lá pode ser em português, porém
    sempre terá a tradução automática pra língua que vai ser falada"). Já na língua certa, nem chama o Claude.
    Tradução que falha, volta estranha (várias linhas, comprida demais) ou volta em OUTRA língua deixa o título como
    veio: o vídeo não para por causa disso."""
    titulo = " ".join(str(titulo).split())
    codigo = codigo_da_lingua(lingua)
    if not titulo or not lingua or (codigo and _na_lingua(titulo, codigo) is True):
        return titulo
    alvo = f"{lingua} ({codigo})" if codigo else lingua
    try:
        traduzido = _claude(_SISTEMA_TITULO, f"Língua de destino (escreva o título NESTA língua): {alvo}\n\n"
                                             f"Título que chegou (não é a língua de destino): {titulo}", modelo="haiku")
    except Exception:  # noqa: BLE001
        return titulo
    traduzido = traduzido.strip().strip("\"'“”«»").strip()
    if not traduzido or "\n" in traduzido or len(traduzido) > max(150, len(titulo) * 3):
        return titulo
    if codigo and _na_lingua(traduzido, codigo) is False:
        return titulo                 # voltou em outra língua: melhor o original do que o título errado
    return traduzido


def gerar(usuario_id: int, titulo: str, link: str, minutos: int, lingua: str, projeto_id: int | None,
          observacoes: str, perfil: str = "", canal: dict | None = None, projeto_descricao_id: int | None = None,
          aviso=lambda _t: None) -> dict:
    video_id = id_do_video(link)
    if link and not video_id:
        raise RuntimeError("Não reconheci o link do vídeo de referência.")
    pasta = PASTA / f"{datetime.now(banco.BRASILIA).strftime('%Y-%m-%d-%H%M')}-{_slug(titulo)}"
    pasta.mkdir(parents=True, exist_ok=True)
    base, lingua_base, thumb, base_erro = "", "", False, ""
    if video_id:
        aviso("Lendo a transcrição do vídeo de referência…")
        # sem legenda não derruba o pedido (pedido do usuário em 2026-10-28): o vídeo pode estar com as legendas
        # desligadas pelo dono, e antes disso o pedido inteiro parava com erro. Agora o roteiro sai do título, das
        # observações e do estilo do canal, e o motivo fica no roteiro.json para a Revisão poder dizer
        try:
            base, lingua_base = transcricao(video_id)
            (pasta / "transcricao.txt").write_text(base, encoding="utf-8")
        except Exception as erro:  # noqa: BLE001
            base, lingua_base, base_erro = "", "", str(erro)
            aviso("Esse vídeo não deu a legenda. Escrevendo o roteiro a partir do título…")
        aviso("Copiando a thumbnail…")
        thumb = copiar_thumbnail(video_id, pasta / "thumbnail.jpg")
    original = titulo
    if lingua:
        aviso(f"Traduzindo o título para {lingua}…")
        titulo = traduzir_titulo(titulo, lingua)
    projeto = banco.um("SELECT * FROM projetos_roteiro WHERE id=? AND usuario_id=?", projeto_id, usuario_id) if projeto_id else None
    # o ritmo real da voz, medido nos vídeos que a fábrica já entregou (tempo.py)
    from . import tempo
    ritmo = tempo.ritmo(usuario_id, perfil, lingua, minutos)
    # o ppm_alvo já desconta a mania do Claude de escrever mais do que se pede (tempo.py): é ele que dimensiona o
    # primeiro rascunho, para ele já nascer perto do tempo. Quem garante a margem é a conferência depois de escrever
    # (`_conferir_tamanho`), que mede o roteiro pronto no ritmo real da voz
    palavras = minutos * (ritmo.get("ppm_alvo") or ritmo["ppm"])
    sistema = INSTRUCOES + (f"\n\nInstruções do projeto \"{projeto['nome']}\" (estilo do canal, valem por cima das "
                            f"regras acima quando conflitarem):\n{projeto['instrucoes']}" if projeto and projeto["instrucoes"] else "")
    # os arquivos anexados ao projeto do claude.ai (roteiros de exemplo do canal), como o projeto de lá usa
    arquivos = claude_projetos.texto_dos_arquivos(projeto)
    if arquivos:
        sistema += ("\n\nArquivos do projeto (exemplos e referências do canal: siga o estilo, o ritmo e o formato "
                    f"deles, sem copiar o assunto):\n\n{arquivos}")
    pedido = (f"Título do vídeo: {titulo}\nLíngua do roteiro: {lingua}\nTamanho: cerca de {_tamanho(palavras, lingua)} "
              f"({minutos} minutos narrados)\n")
    if observacoes:
        pedido += f"Observações de quem pediu: {observacoes}\n"
    if base:
        # a transcrição muito longa é cortada: o começo e a estrutura importam mais
        pedido += f"\nTranscrição do vídeo de referência (língua: {lingua_base}):\n{base[:60000]}\n"
    elif base_erro:
        pedido += ("\nO vídeo de referência existe, mas não deu para ler a legenda dele: escreva a partir do título, "
                   "das observações e do estilo do canal, sem nenhuma base de transcrição.\n")
    else:
        pedido += "\nSem vídeo de referência: escreva a partir do título.\n"
    sistema += SEM_PERGUNTA
    aviso(f"O Claude está escrevendo (cerca de {_tamanho(palavras, lingua)})…")
    inicio = time.time()
    roteiro, rascunhos = _primeiro_rascunho(sistema, pedido, aviso)
    roteiro, conferencia = _conferir_tamanho(roteiro, sistema, pedido, minutos, ritmo, aviso, lingua)
    (pasta / "roteiro.txt").write_text(roteiro, encoding="utf-8")
    meta = {"titulo": titulo, "titulo_original": original, "link": link, "video_id": video_id, "minutos": minutos, "lingua": lingua,
            "projeto": projeto["nome"] if projeto else "", "palavras": contar_palavras(roteiro),
            "palavras_base": contar_palavras(base), "base_erro": base_erro[:300], "thumbnail": thumb,
            "segundos": round(time.time() - inicio), "criado": banco.agora(), "usuario_id": usuario_id, "ritmo": ritmo,
            "conferencia": conferencia, "canal": canal or {}, "rascunhos": rascunhos}
    (pasta / "roteiro.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    _escrever_descricao(usuario_id, pasta, projeto_descricao_id, aviso)
    return _publico(pasta)


VOLTAS_TAMANHO = 6      # quantas vezes o Radar manda o Claude corrigir o tamanho antes de ficar com a melhor volta

# o que o Radar pede ao Claude quando o roteiro conferido ficou curto ou comprido
CONTINUAR = """

Você já escreveu este começo (NÃO repita nada dele):
{comeco}

Continue o roteiro exatamente de onde ele parou, com mais cerca de {faltam}, até o fechamento. Responda só
com a continuação."""

CONDENSAR = """Este é o roteiro de um vídeo de {minutos} minutos narrados, mas ele está com {atual} e tem de
ficar com cerca de {alvo}.

{roteiro}

Reescreva o roteiro INTEIRO com cerca de {alvo}: corte o que se repete e condense as explicações longas,
mantendo o gancho do começo, todos os assuntos na mesma ordem e o fechamento. Responda só com o roteiro."""


INSISTIR = """

ATENÇÃO: a sua resposta anterior não foi um roteiro (veio vazia, ou veio pergunta e comentário no lugar do texto).
Não há ninguém para responder nada. Escreva AGORA o roteiro inteiro, só as frases que a voz vai falar, decidindo você
mesmo tudo o que não estiver no pedido."""


def _primeiro_rascunho(sistema: str, pedido: str, aviso=lambda _t: None) -> tuple[str, int]:
    """O rascunho que abre o roteiro, e a garantia de que ele é um roteiro.

    O vídeo japonês do cobre (2026-11-03) saiu com 1 minuto e 56: o `_limpar` apagava o roteiro japonês inteiro, o
    laço do tamanho pediu "continue de onde parou" com o começo vazio, e o agente do canal (que manda "SEMPRE perguntar
    a duração antes de escrever") respondeu com perguntas em português, as únicas linhas que o `_limpar` deixava
    passar. Elas viraram o roteiro, foram narradas e viraram vídeo. Agora o `SEM_PERGUNTA` tira o pedido de perguntar, uma resposta que não é roteiro ganha mais uma
    chance com o `INSISTIR`, e duas seguidas param o pedido com erro, em vez de descer para a fábrica."""
    texto = ""
    for volta in (1, 2):
        texto = _limpar(_claude(sistema, pedido if volta == 1 else pedido + INSISTIR))
        if _tem_roteiro(texto) and not _parece_pergunta(texto):
            return texto, volta
        if volta == 1:
            aviso("O Claude não devolveu roteiro (respondeu vazio ou com perguntas). Pedindo de novo…")
    raise RuntimeError("O Claude não escreveu o roteiro: respondeu duas vezes sem roteiro nenhum (vazio ou só "
                       "perguntas). Veja as instruções do agente deste canal — uma regra que manda perguntar antes "
                       "de escrever trava o Radar, porque aqui não há ninguém para responder. Começo do que ele "
                       f"respondeu: {' '.join(texto.split()[:40]) or '(nada)'}")


def _conferir_tamanho(roteiro: str, sistema: str, pedido: str, minutos: int, ritmo: dict,
                      aviso=lambda _t: None, lingua: str = "") -> tuple[str, dict]:
    """Confere o roteiro escrito contra o tempo pedido e corrige até ele caber na margem de 1 minuto.

    Pedido do usuário em 2026-11-01: "o radar tá entregando vídeos com a duração errada, tem que conferir e colocar
    algo que sempre confira o resultado e regule pra acertar cada vez mais; o vídeo de 30 min saiu com 17, o máximo de
    erro é 1 minuto". Antes o Radar só dimensionava o pedido ao Claude e mandava para a fábrica o que viesse:

    - **Faltando.** O laço antigo desistia depois de 4 voltas e parava de vez quando uma continuação voltava com menos
      de 50 palavras — um pedido de 30 min que parasse em 3.700 palavras saía como vídeo de 17 minutos, sem aviso.
    - **Sobrando.** Nada cortava: 15 min pedidos saíram com 23,2, 22,8 e 21,7 minutos.
    - **Sem conferência.** O número das palavras era uma aposta feita ANTES de escrever. Nenhuma conta olhava o
      roteiro pronto. Nos 32 vídeos medidos, 19 ficaram fora de 1 minuto, com erro médio de 2,2 min.

    Agora o tamanho é medido no ritmo real da voz (`tempo.conferir`) e corrigido volta a volta: falta, o Claude
    continua de onde parou; sobra, o Claude condensa o roteiro inteiro. Uma volta que piora não entra — fica sempre a
    melhor de todas, e o que aconteceu em cada uma vai para o `conferencia` do roteiro.json, para a tela de Revisão
    mostrar e para `tempo.medicoes` comparar depois com o vídeo que a fábrica entregou."""
    from . import tempo
    ppm = ritmo.get("ppm") or PALAVRAS_POR_MINUTO
    melhor = roteiro
    conf = tempo.conferir(contar_palavras(roteiro), minutos, ppm)
    voltas: list[dict] = []
    sem_jeito = 0
    if not minutos:
        return melhor, {**conf, "voltas": voltas, "de": ritmo.get("de", "padrao")}
    for _ in range(VOLTAS_TAMANHO):
        if conf["dentro"]:
            break
        faltam, atual, alvo = conf["faltam"], conf["palavras"], conf["alvo_palavras"]
        if faltam > 0:
            if not _tem_roteiro(melhor):
                # começo vazio não se continua: era assim que a resposta à continuação (uma lista de perguntas)
                # virava o roteiro inteiro. Sem roteiro para continuar, o laço para e quem chamou vê o erro
                break
            aviso(f"Conferindo o tempo: o roteiro dá {conf['previsto_min']} min e você pediu {minutos}. "
                  f"O Claude está continuando ({atual} de {alvo} palavras)…")
            resto = _limpar(_claude(sistema, pedido + CONTINUAR.format(comeco=melhor[-12000:], faltam=_tamanho(faltam, lingua))))
            tentativa = (melhor + "\n\n" + resto) if contar_palavras(resto) >= 30 else melhor
        else:
            aviso(f"Conferindo o tempo: o roteiro dá {conf['previsto_min']} min e você pediu {minutos}. "
                  f"O Claude está condensando ({atual} para {alvo} palavras)…")
            tentativa = _limpar(_claude(sistema, CONDENSAR.format(minutos=minutos, atual=_tamanho(atual, lingua),
                                                                  alvo=_tamanho(alvo, lingua), roteiro=melhor)))
        nova = tempo.conferir(contar_palavras(tentativa), minutos, ppm)
        voltas.append({"palavras": nova["palavras"], "previsto_min": nova["previsto_min"],
                       "erro_min": nova["erro_min"], "o_que": "continuar" if faltam > 0 else "condensar"})
        if tentativa is melhor or abs(nova["erro_min"]) >= abs(conf["erro_min"]):
            # a volta não melhorou. Uma volta fraca não desiste do roteiro (era o que fazia um pedido de 30 min sair
            # com 17): o Radar tenta de novo uma vez. Duas seguidas sem melhorar, fica com a melhor que tem e para
            # de gastar o limite da assinatura
            sem_jeito += 1
            if sem_jeito >= 2:
                break
            continue
        sem_jeito = 0
        melhor, conf = tentativa, nova
    return melhor, {**conf, "voltas": voltas, "de": ritmo.get("de", "padrao")}


def _escrever_descricao(usuario_id: int, pasta, projeto_descricao_id, aviso=lambda _t: None) -> None:
    """A descrição do vídeo, escrita logo depois do roteiro (pedido do usuário em 2026-10-28: ela fica pronta
    enquanto o vídeo está sendo feito, em vez de só existir no fim, quando a fábrica monta o publicacao.json).

    Falhar aqui não derruba o roteiro: o roteiro é o que a pessoa pediu, e a descrição se refaz com um botão.
    O que deu errado fica no roteiro.json, para a tela de Revisão poder dizer."""
    from . import descricao as _descricao
    aviso("Roteiro pronto. O Claude está escrevendo a descrição e as tags…")
    meta = json.loads((pasta / "roteiro.json").read_text(encoding="utf-8"))
    try:
        _descricao.gerar(usuario_id, pasta, projeto_descricao_id)
        meta["descricao_erro"] = ""
    except Exception as erro:
        meta["descricao_erro"] = str(erro)[:300]
    (pasta / "roteiro.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def manual(usuario_id: int, titulo: str, texto: str, link: str = "", minutos: int = 0, lingua: str = "",
           canal: dict | None = None) -> dict:
    """O roteiro que a pessoa escreveu (pedido do usuário em 2026-10-18): fica igual a um do Claude, para revisar e
    mandar para a fábrica. Com link, a thumbnail da referência é copiada também."""
    texto = re.sub(r"\n{3,}", "\n\n", texto.replace("\r\n", "\n")).strip()
    if contar_palavras(texto) < 30:
        raise RuntimeError("Cole o roteiro inteiro (tem menos de 30 palavras).")
    video_id = id_do_video(link) if link else None
    if link and not video_id:
        raise RuntimeError("Não reconheci o link do vídeo de referência.")
    pasta = PASTA / f"{datetime.now(banco.BRASILIA).strftime('%Y-%m-%d-%H%M')}-{_slug(titulo)}"
    pasta.mkdir(parents=True, exist_ok=True)
    thumb = copiar_thumbnail(video_id, pasta / "thumbnail.jpg") if video_id else False
    (pasta / "roteiro.txt").write_text(texto, encoding="utf-8")
    original, titulo = titulo, traduzir_titulo(titulo, lingua)
    # o roteiro colado é o texto da pessoa (o Radar não mexe nele), mas o tempo que ele vai dar é conferido do mesmo
    # jeito, para a tela de Revisão poder dizer antes de mandar para a fábrica
    from . import tempo
    ritmo = tempo.ritmo(usuario_id, "", lingua, minutos)
    conferencia = {**tempo.conferir(contar_palavras(texto), minutos, ritmo["ppm"]), "voltas": [], "de": ritmo["de"]}
    meta = {"titulo": titulo, "titulo_original": original, "link": link, "video_id": video_id, "minutos": minutos, "lingua": lingua, "projeto": "",
            "palavras": contar_palavras(texto), "palavras_base": 0, "thumbnail": thumb, "segundos": 0, "manual": True,
            "criado": banco.agora(), "usuario_id": usuario_id, "ritmo": ritmo, "conferencia": conferencia,
            "canal": canal or {}}
    (pasta / "roteiro.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return _publico(pasta)


def _nome_do_canal(meta: dict) -> str:
    """Para qual canal é o vídeo (pedido do usuário em 2026-10-18: identificar cada vídeo feito). Os roteiros novos
    guardam o canal; os antigos saem pela voz da fábrica (o perfil tem o nome do canal) ou pelo agente de roteiro."""
    if (meta.get("canal") or {}).get("titulo"):
        return meta["canal"]["titulo"]
    perfil = (meta.get("fabrica") or {}).get("perfil", "")
    if perfil:
        from . import producao
        nome = producao._perfil(perfil).get("canal", "")
        if nome and perfil != "documentario":
            return nome
    # o canal que usa o mesmo agente de roteiro
    agente = banco.um("SELECT id FROM projetos_roteiro WHERE nome=? AND usuario_id=?", meta.get("projeto") or "", meta.get("usuario_id"))
    if agente:
        for linha in banco.todos("SELECT c.dados, k.titulo FROM canais_config c JOIN canais k ON k.id=c.canal_id WHERE c.usuario_id=?",
                                 meta.get("usuario_id")):
            if str(json.loads(linha["dados"]).get("projeto_roteiro_id") or "") == str(agente["id"]):
                return linha["titulo"]
    return (meta.get("projeto") or "").title()


def _publico(pasta, leve: bool = False) -> dict:
    """O roteiro como a tela vê. Leve, sem o texto do roteiro e sem a descrição: o painel da direita só mostra a lista
    (título, link, canal, capa) e é pedido a cada troca de tela — com os textos eram 1,3 MB e 1 s toda vez."""
    meta = json.loads((pasta / "roteiro.json").read_text(encoding="utf-8"))
    meta["canal_nome"] = _nome_do_canal(meta)
    arquivo = pasta / "roteiro.txt"
    from . import descricao as _descricao
    return meta | {"nome": pasta.name, "arquivo": str(arquivo),
                   **({} if leve else {"roteiro": arquivo.read_text(encoding="utf-8"), "descricao": _descricao.ler(pasta)}),
                   "thumbnail_url": f"/api/roteiros/{pasta.name}/thumbnail.jpg" if (pasta / "thumbnail.jpg").exists() else "",
                   "comando": f'uv run fabrica novo {pasta.name} --roteiro "{arquivo}" --perfil perfis/documentario.yaml'}


def lista(usuario_id: int, leve: bool = False) -> list[dict]:
    if not PASTA.exists():
        return []
    saida = []
    for meta in sorted(PASTA.glob("*/roteiro.json"), reverse=True)[:60]:
        try:
            if json.loads(meta.read_text(encoding="utf-8")).get("usuario_id") == usuario_id:
                saida.append(_publico(meta.parent, leve))
        except (ValueError, OSError):
            continue
    return saida


# ---------------------------------------------------------------- tarefa em segundo plano (leva 1 a 3 minutos)

def comecar(usuario_id: int, enviar_perfil: str = "", **pedido) -> str:
    """Escreve o roteiro em segundo plano. Com enviar_perfil, assim que fica pronto ele já vai para a fábrica, sem
    esperar a revisão (pedido do usuário em 2026-10-18: escolher entre revisar antes ou mandar direto)."""
    tid = uuid.uuid4().hex[:12]
    with _TRAVA:
        _TAREFAS[tid] = {"usuario_id": usuario_id, "estado": "rodando", "passo": "Começando…", "resultado": None, "erro": "",
                         "titulo": pedido.get("titulo", ""), "link": pedido.get("link", ""), "direto": bool(enviar_perfil),
                         "criado": banco.agora(), "fabrica": None, "erro_envio": "",
                         "canal_nome": (pedido.get("canal") or {}).get("titulo", "")}

    def rodar():
        def aviso(texto):
            _TAREFAS[tid]["passo"] = texto
        try:
            resultado = gerar(usuario_id, aviso=aviso, **pedido)
        except Exception as erro:
            _TAREFAS[tid].update(estado="erro", erro=str(erro))
            return
        if enviar_perfil:
            aviso("Roteiro pronto. Enviando para a fábrica…")
            try:
                _TAREFAS[tid]["fabrica"] = enviar(usuario_id, resultado["nome"], enviar_perfil)
                resultado = _publico(PASTA / resultado["nome"])
            except Exception as erro:
                _TAREFAS[tid]["erro_envio"] = str(erro)
        _TAREFAS[tid].update(resultado=resultado, estado="pronto")
    threading.Thread(target=rodar, daemon=True).start()
    return tid


def tarefa(usuario_id: int, tid: str) -> dict | None:
    t = _TAREFAS.get(tid)
    return t if t and t["usuario_id"] == usuario_id else None


def tarefas(usuario_id: int) -> list[dict]:
    """Os roteiros pedidos desde que o servidor ligou, os mais novos primeiro (sem o texto, que é grande)."""
    saida = []
    for tid, t in list(_TAREFAS.items()):
        if t["usuario_id"] != usuario_id:
            continue
        r = t["resultado"] or {}
        saida.append({"tarefa": tid, "titulo": t["titulo"], "link": t["link"], "estado": t["estado"], "passo": t["passo"],
                      "erro": t["erro"], "direto": t["direto"], "criado": t["criado"], "fabrica": t["fabrica"],
                      "erro_envio": t["erro_envio"], "canal_nome": t.get("canal_nome", ""), "nome": r.get("nome", ""), "thumbnail_url": r.get("thumbnail_url", "")})
    return sorted(saida, key=lambda x: x["criado"], reverse=True)


# ---------------------------------------------------------------- enviar para a fábrica

FABRICA = _FABRICA      # a pasta de cima (o Radar dentro da fábrica) ou RADAR_FABRICA no .env do Radar


def fabrica_conectada() -> bool:
    return (FABRICA / "fabrica").is_dir() and (FABRICA / "perfis").is_dir() and bool(shutil.which("uv"))


def perfis_da_fabrica() -> list[str]:
    if not fabrica_conectada():
        return []
    return sorted(p.stem for p in (FABRICA / "perfis").glob("*.yaml") if not p.stem.startswith(("base-", "teste-")))


def _do_usuario(usuario_id: int, nome: str):
    pasta = PASTA / nome
    if not re.fullmatch(r"[\w.-]+", nome) or not (pasta / "roteiro.json").exists():
        raise RuntimeError("Roteiro não encontrado.")
    meta = json.loads((pasta / "roteiro.json").read_text(encoding="utf-8"))
    if meta.get("usuario_id") != usuario_id:
        raise RuntimeError("Roteiro não encontrado.")
    return pasta, meta


def salvar_texto(usuario_id: int, nome: str, texto: str, titulo: str = "") -> dict:
    """A pessoa pode corrigir o roteiro antes de mandar para a fábrica."""
    pasta, meta = _do_usuario(usuario_id, nome)
    (pasta / "roteiro.txt").write_text(texto.strip(), encoding="utf-8")
    meta["palavras"] = contar_palavras(texto)
    if titulo.strip():
        meta["titulo"] = titulo.strip()[:150]
    (pasta / "roteiro.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return _publico(pasta)


MINIMO_DO_TEMPO = 0.6       # roteiro que não chega a 60% do tempo pedido não desce para a fábrica


def conferir_roteiro(texto: str, meta: dict) -> str:
    """O motivo pelo qual este texto NÃO pode virar vídeo ("" quando pode).

    O último portão antes da fábrica (pedido do usuário em 2026-11-04, depois do vídeo japonês do cobre que saiu com
    1 min e 56 narrando as perguntas do Claude): a conferência do tempo já dizia `dentro: false` com 13,5 minutos
    faltando e ninguém barrava nada — o roteiro ia para a fábrica do mesmo jeito e virava vídeo publicável."""
    palavras = contar_palavras(texto)
    if not _tem_roteiro(texto):
        return f"ele tem só {palavras} palavras: não é um roteiro."
    if _parece_pergunta(texto):
        return ("ele não é um roteiro: são perguntas, do Claude pedindo informação em vez de escrever. Escreva o "
                "roteiro de novo (ou corrija o texto aqui) antes de mandar.")
    codigo = codigo_da_lingua(meta.get("lingua") or "")
    if not _escrito_em(texto, codigo):
        return (f"ele não está escrito em {meta['lingua']}: a voz do canal fala {meta['lingua']} e o texto veio em "
                "outro alfabeto.")
    # o tamanho é medido contra o ALVO da conferência, não contra uma conta nova: o alvo e o ppm da voz estão na
    # mesma unidade das palavras daqui (o `split()`), e é essa unidade que a fábrica já mediu em cada vídeo entregue
    minutos = meta.get("minutos") or 0
    ppm = (meta.get("ritmo") or {}).get("ppm") or PALAVRAS_POR_MINUTO
    alvo = (meta.get("conferencia") or {}).get("alvo_palavras") or round(minutos * ppm)
    if minutos and alvo and palavras < alvo * MINIMO_DO_TEMPO:
        previsto = round(palavras / ppm, 1)
        return (f"ele dá {previsto} min e você pediu {minutos}: só {palavras} das {alvo} palavras da voz do canal. "
                "Mande o Claude escrever de novo, ou complete o texto aqui, antes de gastar a fábrica com ele.")
    return ""


LIMITE_DO_NOME = 150    # o nome da entrega entra em caminho de arquivo do Windows: os dois títulos juntos cabem nisso


def titulo_de_entrega(meta: dict) -> str:
    """O nome com que o vídeo é entregue. Pedido do usuário em 2026-11-04: nos canais em outro alfabeto (japonês,
    coreano) a pasta entregue só tinha o título traduzido, e na lista de Downloads não dava para saber qual vídeo
    era qual. Agora o título traduzido vem com o título original entre parênteses, quando os dois são diferentes."""
    titulo = str(meta.get("titulo") or "").strip()
    original = str(meta.get("titulo_original") or "").strip()
    if not original or original == titulo:
        return titulo
    junto = f"{titulo} ({original})"
    return junto if len(junto) <= LIMITE_DO_NOME else junto[:LIMITE_DO_NOME - 1].rstrip() + ")"


def enviar(usuario_id: int, nome: str, perfil: str) -> dict:
    """Cria o projeto na fábrica com o roteiro e o título (`fabrica novo`, grátis: narrar e gerar imagens continuam
    pedindo confirmação lá). O título vai em titulo_entrega (o traduzido com o original entre parênteses), que a
    fábrica usa no nome do vídeo entregue."""
    if not fabrica_conectada():
        raise RuntimeError("A fábrica não está nesta pasta. O Radar precisa estar dentro da pasta da fábrica.")
    if perfil not in perfis_da_fabrica():
        raise RuntimeError("Escolha um perfil da fábrica.")
    pasta, meta = _do_usuario(usuario_id, nome)
    motivo = conferir_roteiro((pasta / "roteiro.txt").read_text(encoding="utf-8"), meta)
    if motivo:
        raise RuntimeError("Este roteiro não pode virar vídeo: " + motivo)
    projeto = re.sub(r"-+", "-", _slug(meta["titulo"]).replace(".", "-"))[:40].strip("-") or "roteiro"
    final, n = projeto, 2
    while (FABRICA / "projetos" / final).exists():
        final, n = f"{projeto}-{n}", n + 1
    # --no-sync: sem ele o uv reinstala a fábrica e tenta reescrever o Scripts/fabrica.exe, que o Windows trava
    # enquanto a fábrica está ligada; e o VIRTUAL_ENV do Radar sai do ambiente para o uv não avisar que o ignora
    ambiente = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    r = subprocess.run([shutil.which("uv"), "run", "--no-sync", "fabrica", "novo", final,
                        "--roteiro", str(pasta / "roteiro.txt"), "--perfil", f"perfis/{perfil}.yaml", "--sim"],
                       cwd=FABRICA, env=ambiente, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300)
    destino = FABRICA / "projetos" / final
    if not (destino / "projeto.json").exists():
        raise RuntimeError("A fábrica não criou o projeto: " + (r.stderr or r.stdout or "")[-400:])
    dados = json.loads((destino / "projeto.json").read_text(encoding="utf-8"))
    dados["titulo_entrega"] = titulo_de_entrega(meta)
    (destino / "projeto.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    if (pasta / "thumbnail.jpg").exists():
        shutil.copy2(pasta / "thumbnail.jpg", destino / "thumbnail_referencia.jpg")
    # a descrição escrita junto com o roteiro vai junto: a extensão já acha este vídeo no Studio com o vídeo
    # ainda sendo feito, em vez de esperar o publicacao.json da fábrica
    from . import descricao as _descricao
    levou = _descricao.levar(pasta, destino, meta["titulo"], perfil)
    meta["fabrica"] = {"projeto": final, "perfil": perfil, "enviado": banco.agora(), "descricao": levou,
                       "palavras": contar_palavras((pasta / "roteiro.txt").read_text(encoding="utf-8"))}
    (pasta / "roteiro.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    estimativa = "\n".join(l for l in (r.stdout or "").splitlines() if "US$" in l or "min" in l)[-600:]
    return {"projeto": final, "pasta": str(destino), "estimativa": estimativa,
            "proximo": f"uv run fabrica tudo {final}"}
