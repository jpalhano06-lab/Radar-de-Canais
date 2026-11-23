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
from pathlib import Path

import httpx

from . import banco, claude_projetos
from .config import DADOS, FABRICA as _FABRICA

PASTA = DADOS / "roteiros"
VAZIA = DADOS / "claude"          # o Claude roda numa pasta vazia, para não ler nenhum CLAUDE.md
PALAVRAS_POR_MINUTO = 150
TENTATIVAS_DESCRICAO = 3          # todo vídeo vai com descrição: o Claude tenta três vezes antes de desistir
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


def lingua_do_audio(video_id: str) -> str:
    """A língua do áudio original pela API do YouTube (1 unidade); "" se não deu para saber."""
    try:
        from . import youtube
        dados = youtube.videos([video_id])
        return (dados[0].get("lingua_audio") or "") if dados else ""
    except Exception:  # noqa: BLE001 (sem chave ou sem cota: segue sem a dica)
        return ""


def escolher_legenda(disponiveis: list, lingua_audio: str = ""):
    """Vídeo dublado (comum nos canais de IA) tem uma legenda automática por dublagem: preferir "pt" pegava a
    dublagem em português de vídeo em inglês, e a extensão chegou a mostrar a árabe (2026-11-22). Vale a feita à
    mão na língua do áudio, depois a automática dela; sem saber a língua, a feita à mão, depois a automática em
    inglês (a dublagem costuma sair de vídeo em inglês)."""
    base = lambda c: (c or "").split("-")[0].lower()  # noqa: E731
    alvo = base(lingua_audio)

    def nota(t):
        mesma = bool(alvo) and base(t.language_code) == alvo
        return (not mesma, t.is_generated, base(t.language_code) != "en")
    return sorted(disponiveis, key=nota)[0]


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
    escolhida = escolher_legenda(disponiveis, lingua_do_audio(video_id))
    trechos = escolhida.fetch()
    texto = re.sub(r"\s+", " ", " ".join(s.text for s in trechos)).strip()
    return texto, escolhida.language_code


def fala_com_tempos(video_id: str) -> list[dict]:
    """A fala do vídeo em trechos com o segundo em que cada um começa."""
    from youtube_transcript_api import YouTubeTranscriptApi
    try:
        disponiveis = list(YouTubeTranscriptApi().list(video_id))
    except Exception as erro:
        raise RuntimeError(f"Não consegui ler a legenda desse vídeo. Detalhe: {str(erro)[:120]}")
    if not disponiveis:
        raise RuntimeError("Esse vídeo não tem legenda, nem automática.")
    escolhida = escolher_legenda(disponiveis, lingua_do_audio(video_id))
    return [{"seg": round(s.start, 1), "texto": s.text} for s in escolhida.fetch()]


def tem_legenda(video_id: str) -> bool | None:
    """Se dá para ler a legenda desse vídeo. A Nova produção da extensão pergunta isso na confirmação, para a pessoa
    saber antes de criar que o roteiro vai sair só do título (pedido do usuário em 2026-10-28).

    None é "não deu para saber": o YouTube recusou a leitura deste computador ("Sign in to confirm you're not a
    bot", RequestBlocked). Antes isso virava False e a confirmação dizia "Sem legenda" de vídeos com legenda
    (2026-11-10); False fica só para o vídeo que de fato não tem legenda."""
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api import _errors as erros
    try:
        return bool(list(YouTubeTranscriptApi().list(video_id)))
    except (erros.TranscriptsDisabled, erros.NoTranscriptFound):
        return False
    except Exception:  # noqa: BLE001 (bloqueio, rede, mudança do YouTube: não dá para dizer que não tem)
        return None


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


PALAVRAS_POR_PARTE = 600   # cerca de 3 a 5 minutos de voz: um pedaço que o Claude consegue medir sozinho


def partes_do_roteiro(palavras: int) -> tuple[int, int]:
    """Em quantas partes o roteiro é pedido, e com quantas palavras cada uma.

    O Claude não sabe contar 6 mil palavras de uma vez: nos 25 roteiros de 2026-11-06 a 11-12 o primeiro rascunho
    saiu 15 a 50% fora do pedido (curto nos de 30 min, comprido nos de 15) e o laço do tamanho gastava até 6 voltas
    corrigindo. Uma parte de 600 palavras ele acerta, e partes iguais somam o tempo pedido."""
    partes = max(1, round(palavras / PALAVRAS_POR_PARTE))
    return partes, round(palavras / partes)


def tamanho_no_pedido(palavras: int, minutos: int, lingua: str) -> str:
    """A linha do tamanho no pedido: o total e, num roteiro maior que uma parte, a divisão em partes marcadas.
    A marca `[PARTE k/N]` fica sozinha na linha e o `_limpar` a tira antes da voz (linha entre colchetes)."""
    texto = f"Tamanho: cerca de {_tamanho(palavras, lingua)} ({minutos} minutos narrados)\n"
    partes, cada = partes_do_roteiro(palavras)
    if partes > 1:
        texto += (f"Escreva o roteiro em {partes} partes de cerca de {_tamanho(cada, lingua)} cada, em sequência, "
                  f"cada uma começando numa linha sozinha com a marca [PARTE 1/{partes}], [PARTE 2/{partes}] e assim "
                  f"por diante. Meça cada parte: nenhuma pode passar muito de {_tamanho(cada, lingua)} nem ficar "
                  f"curta. A última parte é o fechamento.\n")
    return texto


def aviso_da_base(palavras_base: int, palavras: int, lingua: str) -> str:
    """Vai logo depois da transcrição de referência. O Claude copiava o tamanho dela no lugar do pedido: 30 min
    pedidos (6.390 palavras) com uma referência de 10.255 saíram com mais de 10 mil palavras (2026-11-11)."""
    return (f"\nA transcrição acima tem cerca de {_tamanho(palavras_base, lingua)}. Ela é só fonte de assunto, "
            f"fatos e ordem das ideias: NÃO siga o tamanho dela. O seu roteiro tem cerca de "
            f"{_tamanho(palavras, lingua)}, nem mais nem menos.\n")


def _pasta_nova(titulo: str) -> Path:
    """A pasta deste roteiro, sempre uma só dele (2026-11-17): o nome é a hora e o título, e dois roteiros do mesmo
    minuto com o mesmo título ganham -2, -3… Em japonês, coreano e chinês o `_slug` não sobra nada e vira "roteiro",
    então dois pedidos do mesmo minuto caíam na MESMA pasta: o segundo escrevia por cima do primeiro e os dois
    viravam o mesmo vídeo (aconteceu com os dois vídeos do canal japonês, 21:06)."""
    base = f"{datetime.now(banco.BRASILIA).strftime('%Y-%m-%d-%H%M')}-{_slug(titulo)}"
    pasta, k = PASTA / base, 1
    while pasta.exists():
        k += 1
        pasta = PASTA / f"{base}-{k}"
    pasta.mkdir(parents=True)
    return pasta


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
- O roteiro é sempre sobre o assunto do TÍTULO pedido. Quando a referência fala de outra empresa, pessoa, lugar ou
  produto, dela vêm só a estrutura, o ritmo, os ganchos e o tipo de prova; os fatos, nomes e números são os do
  assunto do título.
- Só fatos de que você tem certeza. Nada inventado sobre pessoas reais. Número, data e nome só se estiverem certos.
- Termine com um fechamento curto.
- Respeite o tamanho pedido (palavras ou caracteres), porque ele vira o tempo do vídeo."""

# Vem da comparação com os 16 roteiros do Robô do Dotti (2026-11-05). No primeiro minuto, os nossos falavam "eu" 4 vezes
# mais (2,59 contra 0,65 por 100 palavras), se apresentavam 5 vezes mais e tinham 5 vezes mais ressalvas: o asdas abria
# com "I can't stand behind that one, so I'm not going to lean on it". Os deles abrem no fato e deixam uma promessa no ar.
# Vai depois das instruções do canal, que mandam o apresentador se apresentar logo no começo
ABERTURA = """

Sobre o primeiro minuto do vídeo, por cima das instruções do canal:
- Comece pelo fato: um número, uma cena ou uma decisão concreta, com o que quem assiste ganha ou perde com isso.
- Antes dos 30 segundos, prometa o ponto mais importante do vídeo e guarde a resposta para mais tarde.
- Nada de apresentação no primeiro minuto: sem nome, idade ou ofício do narrador, sem "neste vídeo", sem pedir inscrição.
  Se o canal tem apresentador, ele se apresenta depois, numa frase só, quando já tiver entregado o primeiro ponto.
- No primeiro minuto o assunto é o fato e quem assiste, não o narrador: quase nenhum "eu".
- Em nenhum ponto do vídeo avise o que você não vai afirmar nem duvide dos próprios números. Sem certeza, deixe de fora."""

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

# Pedido do usuário em 2026-11-20: "vamos mudar o Radar e retirar o agente, sempre será um prompt agora". Todo
# roteiro de canal é escrito por este prompt (o do usuário, palavra por palavra nas regras), no lugar das instruções
# do agente do canal. O formulário do Passo 1 é respondido pelo próprio Radar no pedido (título, minutos, idioma e a
# transcrição da referência), porque aqui não há ninguém para responder. Só o Canal de teste continua com o agente
# CANAL DE TESTE: ele é genérico, não tem referência e tem o modo de 5 min sem narração.
MESMO_ASSUNTO = "MESMO_ASSUNTO:"

PROMPT = """Você é um roteirista para YouTube. A pessoa que vai usar este prompt está começando agora e não tem
experiência nenhuma com roteiro — por isso, você faz TODO o trabalho técnico sozinho, sem pedir para ela validar
números, tabelas ou conceitos que ela não tem repertório para julgar. A única coisa que ela precisa fazer é te dar
informação sobre o vídeo; você decide e executa o resto.

═══════════════════════════════════
PASSO 1 — O FORMULÁRIO (já respondido)
═══════════════════════════════════
O formulário já foi respondido e vem no pedido: 1. o TÍTULO/TEMA do vídeo; 2. a DURAÇÃO e o IDIOMA DE SAÍDA
(o idioma importa para as adaptações culturais ao país de quem assiste: o roteiro inteiro é escrito nesse idioma);
3. o VÍDEO DE REFERÊNCIA/TRANSCRIÇÃO. Não apresente o formulário e não pergunte nada.

Assim que receber as respostas, VOCÊ MESMO faz a pesquisa completa sobre o tema — sempre, automaticamente. Use busca
na web se você tiver essa ferramenta disponível, ou seu próprio conhecimento se não tiver. Faça isso sem avisar que
está pesquisando. Organize: linha do tempo, pessoas envolvidas, o que estava em jogo, números específicos,
curiosidades pouco conhecidas, contexto histórico/cultural. NUNCA invente um fato específico (número, data, nome,
citação) que você não tenha razoável certeza — se não conseguir confirmar algo importante, deixe mais vago no roteiro
em vez de inventar, mas NÃO pare o fluxo por causa disso.

═══════════════════════════════════
PASSO 1.5 — VALIDAR A REFERÊNCIA (obrigatório, antes de qualquer cálculo)
═══════════════════════════════════
Compare o ASSUNTO da referência com o TEMA do vídeo (item 1).

Considere "o mesmo assunto" quando a referência trata da mesma pessoa, mesmo evento, mesmo objeto/monumento, ou mesmo
marco histórico específico do tema — mesmo que o título esteja escrito diferente ou em outra língua. Não considere
"mesmo assunto" apenas por estarem no mesmo nicho/categoria geral (ex: "história antiga" é a categoria; "Templo de
Salomão" e "Pirâmides do Egito" são assuntos diferentes dentro dela — isso é válido).

SE for o mesmo assunto específico: não calcule nada e não escreva nada do roteiro. Responda SÓ com uma linha que
começa exatamente com "MESMO_ASSUNTO:" seguida, em português, da explicação simples: "Essa referência é sobre o mesmo
assunto do seu vídeo — se eu usar a estrutura dela pra escrever sobre a mesma coisa, o resultado vai ficar muito
parecido com o original, quase uma cópia. Preciso de um vídeo de sucesso sobre OUTRO tema, no mesmo estilo/nicho. Por
exemplo, já que seu tema é '[tema]', tente algo como '[um tema análogo de sucesso conhecido, no mesmo nicho, mas
assunto diferente]'."

SE for um assunto diferente (mesmo que do mesmo nicho): prossiga normalmente para o Passo 2.

═══════════════════════════════════
PASSO 2 — FAZER TUDO SOZINHO (trabalho interno, nada disso aparece na resposta)
═══════════════════════════════════

REGRA MESTRA (vale pra tudo abaixo): a estrutura REAL da referência manda. Você NUNCA impõe uma organização dramática
(atos, clímax emocional, ordem por "peso") que a referência não tenha. Se a referência for uma lista simples e
crescente, o roteiro também é uma lista simples e crescente, na MESMA lógica de ordenação dela. A divisão fixa em
percentuais (letra B abaixo) só existe pra ser usada quando NÃO HÁ referência nenhuma — nunca por cima de uma
referência real. O objetivo é pegar uma estrutura que já funcionou e encaixar o tema novo nela, não criar uma
organização original por cima.

A) EXTRAIR A ESTRUTURA REAL DA REFERÊNCIA (faça isso PRIMEIRO, com rigor — é a parte que mais importa)
Leia a transcrição de referência inteira e extraia, com precisão:
1. Tipo de hook: pergunta / afirmação forte / contraintuitivo / abertura em cena / estatística / desafio / "e se" /
   endereçamento direto.
2. Texto do hook: as 1-3 frases EXATAS de abertura da referência (só pra você estudar o padrão, não vai pro roteiro).
3. Fórmula do hook, templatizada: troque os detalhes específicos por placeholders descritivos. Ex: "[GRUPO] faria
   intencionalmente [AÇÃO CONTRAINTUITIVA] porque [MOTIVO INESPERADO]."
4. Primeiros ~30 segundos: em que ordem a informação aparece, como a curiosidade é construída, o que impede a pessoa
   de sair.
5. Estrutura real de blocos: conte e nomeie CADA bloco/seção que a referência realmente tem — não invente uma
   quantidade ou lógica diferente. Se ela tem 20 itens numa lista simples e crescente, são 20 blocos, nessa ordem. Se
   ela tem 4 atos dramáticos de verdade, são 4 atos. Para cada bloco, anote: nome, proporção aproximada de
   palavras/tempo, e o PROPÓSITO dele na narrativa.
6. Tipo de narrativa: linear / in medias res / problema-solução / causa-efeito / comparação / escalada / catálogo
   sequencial / loop. Anote conectores-assinatura ("Você já parou pra pensar...", "Mas aqui está o detalhe...").
7. Re-hooks e retenção: liste TODOS os re-hooks, quebras de padrão, loops abertos e picos de especificidade.
8. Posicionamento do CTA: onde aparece, que tipo (inscrever/comentar/curtir/implícito), fraseado aproximado.

B) SÓ SE NÃO HOUVER REFERÊNCIA NENHUMA: use por padrão a estrutura documental — Hook 6% | Contexto 9% | Ato 1
   (Preparação) 18% | Ato 2 (Tensão Crescente) 27% | Ato 3 (Clímax) 18% | Ato 4 (Consequências) 13% | Resolução 9% —
   com re-hook a cada 2-3 min (vídeos até 25 min) ou 3-4 min (mais longos). Isso NUNCA se aplica quando há
   referência — nesse caso é a estrutura extraída em (A) que manda, sempre.

C) CALCULAR O TOTAL DE PALAVRAS E DISTRIBUIR
O total é o tamanho que vem no pedido (ele já é a duração pedida na velocidade da voz do canal).
- Com referência: distribua esse total pelos MESMOS blocos, na MESMA ordem e nas MESMAS proporções relativas
  identificadas em (A) — mesma quantidade de blocos, mesma lógica de escalada/ordenação. Só a duração total muda.
- Sem referência: distribua conforme os percentuais do item (B).

D) ORGANIZAR A PESQUISA
Use o que você mesmo pesquisou. Todo fato do roteiro final tem que vir daqui — nunca invente número, nome ou citação.
Se faltar algo importante, é melhor deixar mais vago do que inventar.

E) ESCREVER O ROTEIRO
Siga a estrutura extraída em (A) — ou o padrão de (B), só se não houve referência — preenchida com o material de (D),
respeitando a contagem de palavras por bloco calculada em (C). NUNCA troque a lógica de organização da referência por
uma lógica sua: nada de inventar "clímax emocional" se a referência não tinha; nada de reordenar itens por peso
dramático se a referência seguia uma ordem simples. Regras fixas de escrita:
- Frases curtas. Evite palavra vaga ("um carro", "muito tempo") — troque por algo específico ("um Fusca 1978", "três
  semanas").
- Bata o TIPO de hook extraído em (A.1), usando a fórmula templatizada de (A.3) como molde — nunca copiando as frases
  exatas da referência.
- Nunca repita a mesma informação duas vezes sem motivo.
- Cada bloco termina deixando curiosidade pra próxima, nunca "morre" no meio.
- Reproduza o posicionamento de CTA identificado em (A.8) — mesmo lugar, tipo parecido, fraseado natural.
- Adapte as referências culturais ao país de quem fala o idioma de saída.

F) REVISAR SOZINHO ANTES DE ENTREGAR — TESTE DE FIDELIDADE (não narre isso, só aplique)
"Se eu tirasse o assunto do roteiro que acabei de escrever e colocasse de volta o assunto original da referência, a
estrutura que eu usei bate com a estrutura REAL da referência — mesma quantidade de blocos, mesma lógica de ordenação,
mesmo tipo de hook, mesmo posicionamento de CTA?" Se não, REESCREVA a estrutura antes de entregar. Depois:
- Se o começo não prenderia atenção nos primeiros 10 segundos, reescreva.
- Se tiver frase genérica, troque por específica.
- Se tiver repetição sem função, corte.
- Confirme que a pergunta feita no início é respondida em algum momento do roteiro.

═══════════════════════════════════
O QUE VOCÊ ENTREGA (a única coisa da resposta)
═══════════════════════════════════
Entregue SOMENTE o roteiro. Nada antes, nada depois — sem preâmbulo, sem dica, sem observação, sem linha de contagem
de palavras/duração.
- Só as palavras que serão faladas — nada mais.
- Sem timestamps, sem [PAUSA], sem títulos de seção, sem "NARRADOR:", sem markdown.
- Sem preâmbulo nem fechamento seu.
- Números e datas escritos por extenso, no idioma do roteiro (ex: "mil novecentos e oitenta e quatro", não "1984").
- Não mostre tabelas, cálculos, nem a análise que você fez.
- Sem lista de fontes, sem links e sem "Sources:" no fim: a pesquisa não aparece na resposta."""

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


class LimiteDoClaude(RuntimeError):
    """A assinatura do Claude bateu no limite. Do estudo da Dotti (2026-11-22): quem bate no limite não insiste. As
    etapas que o roteiro dispensa (a leitura do porquê, a tradução do título, a lição do canal, as voltas do tamanho,
    a descrição) seguem sem ele, e a fila só volta a pedir roteiro quando o limite renova (`pausa_do_claude`)."""


PAUSA_PADRAO = 30 * 60        # segundos: sem a hora da renovação na mensagem, tenta de novo daqui a meia hora
PAUSA_MAXIMA = 24 * 3600
_LIMITE = re.compile(r"usage limit|limit reached|hit your limit|you've reached your|rate limit|limite de uso|"
                     r"out of extra usage|\b\d+-hour limit|weekly limit", re.I)
# uma resposta "certa" (sem is_error) só conta como limite se for a própria mensagem do Claude Code: um título que fale
# de "rate limit" não pode parar a fila
_LIMITE_NA_RESPOSTA = re.compile(r"^\W*(claude ai usage limit reached|you've hit your (usage )?limit|"
                                 r"\d+-hour limit reached|weekly limit reached)", re.I)
_PAUSA_ATE = {"ate": 0.0}


def _arquivo_da_pausa() -> Path:
    return VAZIA / "limite.json"


def pausa_do_claude() -> float:
    """Quantos segundos faltam para o limite do Claude renovar (0: sem pausa). Fica em arquivo, para valer depois de
    o Radar ser religado."""
    ate = _PAUSA_ATE["ate"]
    if not ate:
        try:
            ate = float(json.loads(_arquivo_da_pausa().read_text(encoding="utf-8")).get("ate") or 0)
        except (OSError, ValueError):
            ate = 0.0
        _PAUSA_ATE["ate"] = ate or -1.0
    return max(0.0, ate - time.time())


def _quando_renova(mensagem: str, agora: float | None = None) -> float:
    """A hora (epoch) em que o limite renova, lida da mensagem do Claude Code: "usage limit reached|1763650800" ou
    "resets 7pm" / "resets at 19:30". Sem hora legível, daqui a PAUSA_PADRAO."""
    agora = time.time() if agora is None else agora
    epoca = re.search(r"\|\s*(\d{10})\b", mensagem)
    if epoca and agora < int(epoca.group(1)) <= agora + PAUSA_MAXIMA:
        return float(epoca.group(1))
    hora = re.search(r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", mensagem, re.I)
    if hora:
        h, m, ampm = int(hora.group(1)), int(hora.group(2) or 0), (hora.group(3) or "").lower()
        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
        if h < 24 and m < 60:
            base = datetime.fromtimestamp(agora)
            alvo = base.replace(hour=h, minute=m, second=0, microsecond=0).timestamp()
            return alvo if alvo > agora else alvo + 86400
    return agora + PAUSA_PADRAO


def _pausar_claude(mensagem: str) -> float:
    ate = _quando_renova(mensagem)
    _PAUSA_ATE["ate"] = ate
    try:
        VAZIA.mkdir(parents=True, exist_ok=True)
        _arquivo_da_pausa().write_text(json.dumps({"ate": ate, "mensagem": mensagem[:300]}), encoding="utf-8")
    except OSError:
        pass
    return ate


def _texto_da_pausa(segundos: float) -> str:
    volta = datetime.fromtimestamp(time.time() + segundos).strftime("%H:%M")
    return f"O Claude bateu no limite da assinatura. A fila volta a pedir roteiro às {volta}."


def _claude(sistema: str, pedido: str, modelo: str = "", pesquisa: bool = False) -> str:
    """pesquisa: o Claude pode buscar na web (o prompt do roteiro manda pesquisar o tema antes de escrever)."""
    falta = pausa_do_claude()
    if falta:
        # o limite ainda não renovou: nem chama (cada chamada perdida demora e não traz nada)
        raise LimiteDoClaude(_texto_da_pausa(falta))
    executavel = shutil.which("claude")
    if not executavel:
        raise RuntimeError("O Claude Code não está instalado neste computador (comando claude).")
    VAZIA.mkdir(parents=True, exist_ok=True)
    ambiente = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    # as instruções vão por arquivo, não na linha de comando: o Windows corta a linha em 32 mil letras e o agente
    # JAN DE WOLF sozinho tem 33 mil (com os arquivos do projeto do claude.ai, passa de 100 mil)
    arquivo = VAZIA / f"sistema-{uuid.uuid4().hex[:8]}.txt"
    arquivo.write_text(sistema, encoding="utf-8")
    # --setting-sources "" e --disable-slash-commands: sem os plugins, hooks, skills e o CLAUDE.md pessoais de quem
    # usa o computador. A pasta vazia não bastava: o ~/.claude/CLAUDE.md e o plugin caveman ("respond terse") entravam
    # em todo roteiro, gastando o limite e puxando o texto para curto (conferido em 2026-11-12)
    ferramentas = ["--tools", "WebSearch", "--allowedTools", "WebSearch"] if pesquisa else ["--tools", ""]
    comando = [executavel, "-p", "--output-format", "json", "--system-prompt-file", str(arquivo), *ferramentas,
               "--strict-mcp-config", "--no-session-persistence", "--setting-sources", "", "--disable-slash-commands"]
    if modelo:
        # "opus:low" = o modelo e o esforço (o quanto ele pensa antes de escrever)
        nome, _, esforco = modelo.partition(":")
        comando += ["--model", nome] + (["--effort", esforco] if esforco else [])
    try:
        r = subprocess.run(comando, input=pedido, capture_output=True, text=True, encoding="utf-8", cwd=VAZIA,
                           env=ambiente, timeout=900)
    finally:
        arquivo.unlink(missing_ok=True)
    try:
        dados = json.loads(r.stdout)
    except ValueError:
        dados = None
    resposta = str((dados or {}).get("result", "")) if isinstance(dados, dict) else ""
    erro = (dados or {}).get("is_error") if isinstance(dados, dict) else True
    queixa = resposta if erro else (resposta if _LIMITE_NA_RESPOSTA.search(resposta[:200]) else "")
    if _LIMITE.search(queixa or "") or (dados is None and _LIMITE.search((r.stdout or "") + (r.stderr or ""))):
        _pausar_claude(queixa or (r.stdout or "") + (r.stderr or ""))
        raise LimiteDoClaude(_texto_da_pausa(pausa_do_claude()))
    if not isinstance(dados, dict):
        raise RuntimeError("O Claude Code não respondeu. Ele está logado? Rode `claude` no terminal e digite /login. "
                           + (r.stderr or "")[:200])
    if dados.get("is_error"):
        raise RuntimeError("O Claude Code recusou: " + str(dados.get("result", ""))[:300])
    return str(dados.get("result", "")).strip()


# linha que é título de parte e não fala: "[TITULO] A fuga", "## Parte 2", "Introdução", "1. O começo"
_TITULO = re.compile(r"^\s*(\[[^\]]*\].*|#+.*|(parte|cap[ií]tulo|se[cç][aã]o|bloco)\s*\d+.*|"
                     r"(introdu[cç][aã]o|conclus[aã]o|fechamento|gancho|abertura|encerramento)\s*:?)\s*$", re.I)


_FONTES = re.compile(r"^\s*[*#_]*\s*(sources|fontes|fuentes|quellen|sources consultées|references|referências|"
                     r"referencias)\s*[*_]*\s*:?\s*[*_]*\s*$", re.I | re.M)
_SO_LINK = re.compile(r"^\s*[-*•]?\s*(\[[^\]]*\]\(https?://[^)]*\)|<?https?://\S+>?)\s*$")


_MARCA_PARTE = re.compile(r"^\[\s*PARTE[^\]]*\]\s*[:.\-–—]?\s*", re.I)


def _limpar(texto: str) -> str:
    """Deixa só o que a voz fala. Pedido do usuário em 2026-10-14: o roteiro vinha com "[TITULO] ..." no meio, e o
    script tem que ser limpo para narração."""
    texto = re.sub(r"^\s*(aqui está|segue)[^\n]*\n", "", texto, flags=re.I)
    # com a busca na web (2026-11-20) o Claude Code fecha a resposta com "Sources:" e os links: nada disso é fala
    texto = _FONTES.split(texto)[0]
    texto = "\n".join(l for l in texto.splitlines() if not _SO_LINK.match(l))
    texto = re.sub(r"\[([^\]]+)\]\(https?://[^)]*\)", r"\1", texto)
    texto = re.sub(r"\*\*|__|`", "", texto)
    linhas = []
    for linha in texto.splitlines():
        # a marca das partes (`tamanho_no_pedido`) sai sozinha; se o Claude grudar a fala nela, a fala fica
        limpa = linha.strip()
        if _MARCA_PARTE.match(limpa):
            limpa = _MARCA_PARTE.sub("", limpa)
            if not limpa:
                continue
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


# as palavras mais comuns de cada língua de alfabeto latino (2026-11-20, pedido do usuário: "você tem que conferir se
# realmente os vídeos, as narrações e o roteiro caíram na língua certa"). Antes só se conferia o alfabeto, então um
# roteiro em português num canal francês passava. Línguas vizinhas que dividem as palavras contam como uma família.
_PALAVRAS = {
    "pt": "que não uma para com os do da das dos no na ao pelo pela você também mais ele ela são foi isso muito "
          "quando seu sua está mas já até",
    "en": "the and of to is was that with for you this they have what from which were their",
    "es": "el los las del que una por con pero muy está también porque hay fue cuando este",
    "fr": "le les des et est une dans pour pas qui sur avec ce il vous mais sont cette",
    "de": "der die das und ist nicht ein eine mit auf für sich den dem auch wir wird",
    "it": "il gli della che non una per con sono anche questo più nel alla del gli",
    "nl": "het een van niet dat met voor zijn ook maar wij worden wordt deze",
    "pl": "nie się jest że przez już czy oraz który jego jej są może",
    "sv": "och det att är som på för med inte av till har jag",
    "da": "og det at er som på til med ikke af har jeg",
    "no": "og det er som på til med ikke av har jeg",
    "fi": "ja on ei se että oli kun mutta myös tai hän",
    "tr": "bir ve bu için ile çok ne olarak gibi daha ama",
    "id": "yang dan di ini itu dengan untuk tidak ada dari akan",
    "ms": "yang dan di ini itu dengan untuk tidak ada dari akan",
    "ro": "și în că nu este cu pe la din mai sunt care",
    "cs": "že není jsou jako také který jsem byl jeho",
    "sk": "že nie sú ako aj ktorý som bol jeho",
    "hu": "az és hogy nem egy van meg ez volt",
    "hr": "što nije kao ali bio samo sve koji jer",
    "vi": "và của là có không những được một người cho",
    "fil": "ang ng mga ay hindi ito siya",
}
_PALAVRAS = {c: set(p.split()) for c, p in _PALAVRAS.items()}
_FAMILIA = {"da": "nordico", "no": "nordico", "sv": "nordico", "id": "malaio", "ms": "malaio",
            "cs": "tcheco", "sk": "tcheco"}


def _lingua_latina(texto: str) -> tuple[str, float]:
    """A língua latina mais provável do texto e quanto das palavras dela aparecem (0 a 1)."""
    palavras = re.findall(r"[^\W\d_]+", texto.lower())
    if len(palavras) < 40:
        return "", 0.0
    contagem = {c: sum(p in s for p in palavras) / len(palavras) for c, s in _PALAVRAS.items()}
    melhor = max(contagem, key=contagem.get)
    return melhor, contagem[melhor]


def lingua_errada(texto: str, lingua: str) -> str:
    """Em que língua o texto veio, quando NÃO é a pedida ("" quando está certo ou não dá para saber). Vale para o
    roteiro inteiro: alfabeto nas línguas que têm o seu, palavras comuns nas de alfabeto latino."""
    codigo = codigo_da_lingua(lingua)
    if not codigo or not texto.strip():
        return ""
    if codigo in _ALFABETOS:
        return "" if _escrito_em(texto, codigo) else "outro alfabeto"
    letras = [c for c in texto if c.isalpha()]
    if letras and sum(1 for c in letras if ord(c) > 0x024F) > len(letras) / 2:
        return "outro alfabeto"
    if codigo not in _PALAVRAS:
        return ""
    vista, parte = _lingua_latina(texto)
    if not vista or vista == codigo or _FAMILIA.get(vista, vista) == _FAMILIA.get(codigo, codigo):
        return ""
    propria = sum(p in _PALAVRAS[codigo] for p in re.findall(r"[^\W\d_]+", texto.lower()))
    propria /= max(1, len(re.findall(r"[^\W\d_]+", texto)))
    # errado só com certeza: a outra língua bem presente e a pedida bem menos
    if parte >= 0.08 and propria < parte * 0.5:
        from .fabrica_api import IDIOMA
        return {c: n for n, c in IDIOMA.items()}.get(vista, vista)
    return ""


TRADUZIR = """O roteiro abaixo tinha de estar todo em {lingua}, mas veio em {veio}. Reescreva o roteiro INTEIRO em
{lingua}, com as mesmas ideias, a mesma ordem e o mesmo tamanho, adaptando as referências culturais. Números por
extenso. Responda só com o roteiro.

{roteiro}"""


def garantir_lingua(roteiro: str, lingua: str, aviso=lambda _t: None) -> str:
    """O roteiro na língua pedida, ou erro: uma volta de reescrita e, se ainda vier errado, o pedido para (nunca vai
    para a fábrica um roteiro que a voz do canal não fala)."""
    veio = lingua_errada(roteiro, lingua)
    if not veio:
        return roteiro
    aviso(f"O roteiro veio em {veio}, não em {lingua}. O Claude está reescrevendo em {lingua}…")
    novo = _limpar(_claude("Você reescreve roteiros de YouTube em outra língua. Responda só com o roteiro.",
                           TRADUZIR.format(lingua=lingua, veio=veio, roteiro=roteiro), modelo=ROTEIRO))
    veio = lingua_errada(novo, lingua)
    if veio or not _tem_roteiro(novo):
        raise RuntimeError(f"O roteiro saiu em {veio or 'outra língua'}, não em {lingua}, mesmo depois de pedir de "
                           "novo. O pedido parou para não virar vídeo na língua errada.")
    return novo


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


def titulo_do_video(video_id: str) -> str:
    """O título do vídeo de referência, pelo oEmbed do YouTube: sem chave e sem gastar a cota."""
    r = httpx.get("https://www.youtube.com/oembed", params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}, timeout=8)
    r.raise_for_status()
    return str(r.json().get("title") or "")


def titulo_da_referencia(video_id: str) -> str:
    """O título que o Radar guardou do vídeo (sem rede); sem ele, o do YouTube. Vazio quando nenhum dos dois vem."""
    try:
        linha = banco.um("SELECT titulo FROM videos WHERE id=?", video_id)
        if linha and linha["titulo"]:
            return str(linha["titulo"])
    except Exception:  # noqa: BLE001 (o título da referência nunca derruba o roteiro)
        pass
    try:
        return titulo_do_video(video_id)
    except (httpx.HTTPError, ValueError):
        return ""


def aviso_de_outro_assunto(titulo: str, titulo_ref: str) -> str:
    """Os dois títulos lado a lado, para o Claude ver quando o pedido troca o assunto da referência (2026-11-14:
    "Lidl's $30 Billion Empire Is Collapsing" pedido sobre o vídeo do Sainsbury's saiu um roteiro inteiro do
    Sainsbury's, com Tesco, porque a transcrição era a BASE dos fatos e o Claude nem via o título da referência). Quem
    decide se o assunto mudou é o Claude: comparar palavras erra no título traduzido."""
    titulo_ref = " ".join(str(titulo_ref or "").split())
    if not titulo_ref or titulo_ref.casefold() == " ".join(str(titulo).split()).casefold():
        return ""
    return (f"\nTítulo do vídeo de referência: \"{titulo_ref}\". Título pedido: \"{titulo}\". Compare os dois. Se o "
            "título pedido fala de outra empresa, pessoa, lugar ou produto, o roteiro inteiro é sobre o do título "
            "PEDIDO, com fatos, nomes e números dele: da transcrição vêm só a estrutura, o ritmo, os ganchos e o tipo de "
            "prova, e os nomes e números da referência não entram, a não ser numa comparação curta.\n")


def por_que_estourou(video_id: str, titulo: str, base: str, aviso=lambda _t: None) -> dict:
    """A mesma leitura do botão "Por que este vídeo estourou" da extensão, e guardada junto com ela: quem já apertou o
    botão não gasta outra chamada. Falhou, o roteiro sai só com a transcrição, como antes."""
    from . import lente_ia  # lente_ia importa este arquivo

    aviso("Lendo por que o vídeo de referência estourou…")
    try:
        try:
            titulo = titulo_do_video(video_id) or titulo
        except (httpx.HTTPError, ValueError):
            pass  # sem o título da referência, vale o que foi pedido
        return lente_ia.por_que(video_id, titulo, base)
    except Exception as erro:  # noqa: BLE001
        aviso(f"Sem a leitura do que fez o vídeo estourar, seguindo com a transcrição: {str(erro)[:120]}")
        return {}


def texto_do_por_que(leitura: dict) -> str:
    """Pedido do usuário em 2026-11-06: além da transcrição, o roteiro leva em conta por que a referência estourou."""
    campos = (("Por que clicaram", "resumo"), ("Quebra de padrão", "quebra"), ("Prova específica", "prova"),
              ("Pergunta que fica aberta", "loop"), ("Os primeiros segundos", "comeco"))
    linhas = [f"- {rotulo}: {leitura[chave]}" for rotulo, chave in campos if str(leitura.get(chave) or "").strip()]
    if not linhas:
        return ""
    return ("\nPor que o vídeo de referência estourou (leitura do Radar). Use estes mecanismos no roteiro, principalmente no "
            "começo: a mesma quebra de padrão, um dado específico que dê a mesma credibilidade e uma pergunta aberta que só "
            "o fim fecha. Use só dados que estejam na transcrição, e nunca copie as frases:\n" + "\n".join(linhas) + "\n")


# Pedido do usuário em 2026-11-15: canal com menos de 1000 inscritos (ainda sem monetizar) tem de ter pelo menos 2
# CTAs no roteiro. Vai como observação no pedido ao Claude. Sem o número de inscritos guardado, não pede nada.
CTA_ATE_INSCRITOS = 1000
CTA_MINIMO = 2


def pedido_de_ctas(canal_id: str) -> str:
    if not canal_id:
        return ""
    linha = banco.um("SELECT inscritos FROM canais WHERE id=?", canal_id)
    inscritos = linha and linha["inscritos"]
    if inscritos is None or inscritos >= CTA_ATE_INSCRITOS:
        return ""
    return (f"Observação obrigatória: este canal tem menos de {CTA_ATE_INSCRITOS} inscritos. O roteiro tem de ter no "
            f"mínimo {CTA_MINIMO} CTAs (chamadas para a pessoa se inscrever no canal), em pontos diferentes do vídeo: "
            "um logo depois do gancho do começo e outro no meio ou no fim. Cada CTA é uma frase curta e natural, "
            "falada pela voz, ligada ao assunto, sem interromper a história.\n")


def gerar(usuario_id: int, titulo: str, link: str, minutos: int, lingua: str, projeto_id: int | None,
          observacoes: str, perfil: str = "", canal: dict | None = None, projeto_descricao_id: int | None = None,
          aviso=lambda _t: None, transcricao_pronta: str = "", prompt_id: int | None = None) -> dict:
    """transcricao_pronta: a fala do vídeo de referência lida pela extensão, no navegador da pessoa. O YouTube passou a
    recusar a leitura deste computador ("Sign in to confirm you're not a bot") e o roteiro saía só do título de
    vídeos com legenda (2026-11-10); a do navegador vale quando a daqui não vem."""
    video_id = id_do_video(link)
    if link and not video_id:
        raise RuntimeError("Não reconheci o link do vídeo de referência.")
    pasta = _pasta_nova(titulo)
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
            if transcricao_pronta.strip():
                base, lingua_base, base_erro = re.sub(r"\s+", " ", transcricao_pronta).strip(), "a do vídeo", ""
                (pasta / "transcricao.txt").write_text(base, encoding="utf-8")
                aviso("Usando a transcrição lida pela extensão no navegador…")
            else:
                aviso("Esse vídeo não deu a legenda. Escrevendo o roteiro a partir do título…")
        aviso("Copiando a thumbnail…")
        thumb = copiar_thumbnail(video_id, pasta / "thumbnail.jpg")
    original = titulo
    leitura = por_que_estourou(video_id, titulo, base, aviso) if base else {}
    if leitura:
        (pasta / "por_que.json").write_text(json.dumps(leitura, ensure_ascii=False, indent=1), encoding="utf-8")
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
    teste = bool(projeto) and str(projeto["nome"]).strip().upper() == "CANAL DE TESTE"
    nome_do_prompt = "" if teste else "Prompt padrão do Radar"
    if not teste:
        projeto = None      # o agente saiu (2026-11-20): todo canal usa o PROMPT
    base_do_prompt = PROMPT
    if not teste and prompt_id:
        # um prompt criado pela pessoa no lugar do padrão (2026-11-20: "o prompt é padrão, e dê a opção de criar outro")
        outro = banco.um("SELECT nome, instrucoes FROM projetos_roteiro WHERE id=? AND usuario_id=? AND tipo='prompt'",
                         prompt_id, usuario_id)
        if outro and str(outro["instrucoes"] or "").strip():
            base_do_prompt, nome_do_prompt = str(outro["instrucoes"]), str(outro["nome"])
    sistema = (INSTRUCOES if teste else base_do_prompt) + (f"\n\nInstruções do projeto \"{projeto['nome']}\" (estilo do canal, valem por cima das "
                            f"regras acima quando conflitarem):\n{projeto['instrucoes']}" if projeto and projeto["instrucoes"] else "")
    # os arquivos anexados ao projeto do claude.ai (roteiros de exemplo do canal), como o projeto de lá usa
    arquivos = claude_projetos.texto_dos_arquivos(projeto)
    if arquivos:
        sistema += ("\n\nArquivos do projeto (exemplos e referências do canal: siga o estilo, o ritmo e o formato "
                    f"deles, sem copiar o assunto):\n\n{arquivos}")
    palavras = round(palavras)
    pedido = (f"Título do vídeo: {titulo}\n" + (f"Título como foi pedido: {original}\n" if original != titulo else "")
              + f"Duração: {minutos} minutos\nIdioma de saída (o roteiro inteiro é escrito nele): {lingua}\n"
              + tamanho_no_pedido(palavras, minutos, lingua))
    if observacoes:
        pedido += f"Observações de quem pediu: {observacoes}\n"
    pedido += pedido_de_ctas((canal or {}).get("id", ""))
    # o que os vídeos anteriores deste canal ensinaram (retencao.py). Sem Studio conectado, fica vazio
    from . import retencao
    aviso("Vendo o que segurou o público neste canal…")
    licao = retencao.licoes(usuario_id, (canal or {}).get("id", ""))
    if licao:
        (pasta / "retencao.json").write_text(json.dumps(licao, ensure_ascii=False, indent=1), encoding="utf-8")
    pedido += retencao.texto(licao)
    if base:
        # a transcrição muito longa é cortada: o começo e a estrutura importam mais
        pedido += f"\nTranscrição do vídeo de referência (língua: {lingua_base}):\n{base[:60000]}\n"
        pedido += aviso_de_outro_assunto(titulo, titulo_da_referencia(video_id))
        pedido += texto_do_por_que(leitura)
        pedido += aviso_da_base(contar_palavras(base[:60000]), palavras, lingua)
        if partes_do_roteiro(palavras)[0] > 1:
            # a transcrição é longa e o tamanho estava lá em cima: repetido no fim, é a última coisa que o Claude lê
            pedido += "Lembre: " + tamanho_no_pedido(palavras, minutos, lingua)
    elif base_erro:
        pedido += ("\nO vídeo de referência existe, mas não deu para ler a legenda dele: escreva a partir do título, "
                   "das observações e do estilo do canal, sem nenhuma base de transcrição.\n")
    else:
        pedido += "\nSem vídeo de referência: escreva a partir do título.\n"
    sistema += (ABERTURA if teste else "") + SEM_PERGUNTA
    aviso(f"O Claude está {'escrevendo' if teste else 'pesquisando o tema e escrevendo'} "
          f"(cerca de {_tamanho(palavras, lingua)})…")
    inicio = time.time()
    roteiro, rascunhos = _primeiro_rascunho(sistema, pedido, aviso, pesquisa=not teste)
    roteiro, conferencia = _conferir_tamanho(roteiro, sistema, pedido, minutos, ritmo, aviso, lingua)
    roteiro = garantir_lingua(roteiro, lingua, aviso)
    roteiro = despedida_so_no_fim(roteiro, sistema, minutos, lingua, aviso)
    conferencia = {**conferencia, **tempo.conferir(contar_palavras(roteiro), minutos, ritmo.get("ppm") or PALAVRAS_POR_MINUTO)} \
        if minutos else conferencia
    (pasta / "roteiro.txt").write_text(roteiro, encoding="utf-8")
    meta = {"titulo": titulo, "titulo_original": original, "link": link, "video_id": video_id, "minutos": minutos, "lingua": lingua,
            "projeto": projeto["nome"] if projeto else "", "prompt": nome_do_prompt, "palavras": contar_palavras(roteiro),
            "palavras_base": contar_palavras(base), "base_erro": base_erro[:300], "thumbnail": thumb,
            "segundos": round(time.time() - inicio), "criado": banco.agora(), "usuario_id": usuario_id, "ritmo": ritmo,
            "conferencia": conferencia, "canal": canal or {}, "rascunhos": rascunhos, "por_que": bool(leitura), "retencao": bool(licao)}
    (pasta / "roteiro.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    _escrever_descricao(usuario_id, pasta, projeto_descricao_id, aviso)
    return _publico(pasta)


VOLTAS_TAMANHO = 6      # quantas vezes o Radar manda o Claude corrigir o tamanho antes de ficar com a melhor volta
# a volta que melhora menos que isto encerra o laço: cada volta de condensar reescreve o roteiro inteiro, e em
# 2026-11-11/12 metade dos roteiros gastou as 6 voltas tirando 0,1 a 0,5 min por volta (45,9 → 44,2 em 30 pedidos)
MELHORA_MINIMA_MIN = 0.5
# o modelo das tarefas pequenas (descrição, tags, prompt da thumbnail, leituras da Lente): o roteiro fica no padrão
LEVE = "sonnet"
# o texto do roteiro: Opus com esforço baixo, para gastar pouco do limite (pedido do usuário em 2026-11-12)
ROTEIRO = "opus:low"

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

SEM_FECHAMENTO = """
O fechamento do vídeo (o pedido de inscrição e a despedida) já está escrito e entra depois do que você escrever:
NÃO escreva fechamento, despedida nem pedido de inscrição. Termine num ponto que leve naturalmente ao fechamento."""

ALONGAR = """Este é o roteiro de um vídeo de {minutos} minutos narrados, mas ele está com só {atual} e tem de
ficar com cerca de {alvo}.

{roteiro}

Reescreva o roteiro INTEIRO com cerca de {alvo}: aprofunde cada assunto com mais fatos, exemplos, números e
histórias, mantendo o gancho do começo, todos os assuntos na mesma ordem e o fechamento só no fim. Responda só com
o roteiro."""


INSISTIR = """

ATENÇÃO: a sua resposta anterior não foi um roteiro (veio vazia, ou veio pergunta e comentário no lugar do texto).
Não há ninguém para responder nada. Escreva AGORA o roteiro inteiro, só as frases que a voz vai falar, decidindo você
mesmo tudo o que não estiver no pedido."""


def _primeiro_rascunho(sistema: str, pedido: str, aviso=lambda _t: None, pesquisa: bool = False) -> tuple[str, int]:
    """O rascunho que abre o roteiro, e a garantia de que ele é um roteiro.

    O vídeo japonês do cobre (2026-11-03) saiu com 1 minuto e 56: o `_limpar` apagava o roteiro japonês inteiro, o
    laço do tamanho pediu "continue de onde parou" com o começo vazio, e o agente do canal (que manda "SEMPRE perguntar
    a duração antes de escrever") respondeu com perguntas em português, as únicas linhas que o `_limpar` deixava
    passar. Elas viraram o roteiro, foram narradas e viraram vídeo. Agora o `SEM_PERGUNTA` tira o pedido de perguntar, uma resposta que não é roteiro ganha mais uma
    chance com o `INSISTIR`, e duas seguidas param o pedido com erro, em vez de descer para a fábrica."""
    texto = ""
    for volta in (1, 2):
        cru = _claude(sistema, pedido if volta == 1 else pedido + INSISTIR, modelo=ROTEIRO, pesquisa=pesquisa)
        if MESMO_ASSUNTO in cru[:400]:
            # o Passo 1.5 do prompt: a referência é do mesmo assunto do título, e o roteiro seria quase uma cópia
            explicacao = cru.split(MESMO_ASSUNTO, 1)[1].strip()
            raise RuntimeError("A referência é do mesmo assunto do vídeo. " + (explicacao[:600] or
                               "Use um vídeo de sucesso sobre OUTRO tema, no mesmo estilo/nicho."))
        texto = _limpar(cru)
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
        faltam = conf["faltam"]
        try:
            tentativa = _volta_do_tamanho(melhor, sistema, pedido, minutos, conf, aviso, lingua)
        except LimiteDoClaude:
            # o roteiro já existe: sem limite para mais voltas, fica a melhor que há, e a Revisão mostra o tempo
            aviso(f"O Claude bateu no limite: o roteiro fica com {conf['previsto_min']} min, sem mais voltas.")
            voltas.append({"palavras": conf["palavras"], "previsto_min": conf["previsto_min"],
                           "erro_min": conf["erro_min"], "o_que": "limite do Claude"})
            break
        if tentativa is None:
            break
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
        pouco = abs(conf["erro_min"]) - abs(nova["erro_min"]) < MELHORA_MINIMA_MIN
        melhor, conf = tentativa, nova
        if pouco:
            # melhorou, mas quase nada: outra volta gastaria mais um roteiro inteiro para o mesmo resultado
            break
    return melhor, {**conf, "voltas": voltas, "de": ritmo.get("de", "padrao")}


# a despedida do vídeo, nas línguas dos canais: "obrigado por assistir", "até o próximo vídeo", "inscreva-se"
_DESPEDIDA = re.compile(
    r"thanks? (you )?(so much )?for watching|see you (in the|next)|until next time|"
    r"obrigad[oa] por assistir|até o próximo|até a próxima|gracias por ver|nos vemos en el próximo|"
    r"merci d.avoir regardé|à la prochaine|danke fürs zuschauen|bis zum nächsten|grazie per (la )?visione|"
    r"ご視聴ありがとう|次の動画で(また)?(お会い|会い|お目にかか)|それでは、?また|시청해\s?주셔서|"
    r"다음 영상에서\s*(또\s*|다시\s*)?(만나|뵙)|감사합니다\.?\s*$|感谢观看|下期再见", re.I)


def ja_fechou(texto: str) -> bool:
    """O roteiro já termina com a despedida do vídeo (olha só o fim: a despedida no meio não é fechamento)."""
    return bool(_DESPEDIDA.search(texto.strip()[-800:]))


# o que abre o fechamento: o pedido de inscrição, de curtida, de comentário, ou a própria despedida
_FECHAMENTO = re.compile(_DESPEDIDA.pattern + r"|subscribe|hit the like|comment below|let me know in the comments|"
                         r"inscrev|deix[ae] (o seu|seu) like|coment[ae] aqui|suscr[ií]b|abonn|abonnier|"
                         r"チャンネル登録|高評価|コメントで|구독|좋아요|댓글|订阅|点赞", re.I)
_FIM_DE_FRASE = re.compile(r"[.!?。！？\n]")


def separar_fechamento(texto: str) -> tuple[str, str]:
    """O corpo e o fechamento (pedido de inscrição e despedida) de um roteiro que já se despediu. O fechamento começa na
    frase do primeiro pedido ou despedida do último quarto do texto. Sem despedida no fim: (texto, "")."""
    texto = texto.strip()
    if not ja_fechou(texto):
        return texto, ""
    janela = len(texto) * 3 // 4
    achou = _FECHAMENTO.search(texto, janela)
    if not achou:
        return texto, ""
    antes = [m.end() for m in _FIM_DE_FRASE.finditer(texto, janela, achou.start())]
    corte = antes[-1] if antes else janela
    return texto[:corte].rstrip(), texto[corte:].strip()


def despedida_no_meio(texto: str) -> str:
    """A despedida que aparece antes do fechamento ("" quando não há). A despedida é uma vez só, no fim do roteiro
    (pedido do usuário em 2026-11-23). O pedido de inscrição no meio do vídeo é do prompt e não conta: só a despedida."""
    corpo = separar_fechamento(texto)[0]
    achou = _DESPEDIDA.search(corpo)
    return achou.group(0) if achou else ""


CONSERTAR_DESPEDIDA = """Este é o roteiro de um vídeo de {minutos} minutos narrados, mas ele se despede do público no
meio ("{despedida}"), e o vídeo continua depois disso.

{roteiro}

Reescreva o roteiro INTEIRO, na mesma língua e com o mesmo tamanho (cerca de {tamanho}): tire do meio toda despedida,
todo "obrigado por assistir" e todo "até o próximo vídeo", ligando os trechos para que a história siga sem
interrupção. A despedida vem UMA vez só, no fim do roteiro. Mantenha todo o resto. Responda só com o roteiro."""


def despedida_so_no_fim(roteiro: str, sistema: str, minutos: int, lingua: str, aviso=lambda _t: None) -> str:
    """O roteiro que se despede no meio é reescrito pelo Claude com a despedida só no fim (até duas vezes). Se ainda
    assim ela ficar no meio, o portão (`conferir_roteiro`) não deixa ir para a fábrica."""
    for _ in range(2):
        despedida = despedida_no_meio(roteiro)
        if not despedida:
            break
        aviso("O roteiro se despedia no meio do vídeo. O Claude está reescrevendo com a despedida só no fim…")
        tamanho = contar_palavras(roteiro)
        try:
            novo = _limpar(_claude(sistema, CONSERTAR_DESPEDIDA.format(
                minutos=minutos, despedida=despedida, tamanho=_tamanho(tamanho, lingua), roteiro=roteiro), modelo=ROTEIRO))
        except LimiteDoClaude:
            break
        # a reescrita que encolheu muito não entra: trocaria um defeito por um vídeo curto
        if contar_palavras(novo) >= tamanho * 0.9:
            roteiro = novo
    return roteiro


def _volta_do_tamanho(melhor, sistema, pedido, minutos, conf, aviso, lingua):
    """Uma volta da conferência: o roteiro continuado (faltando) ou condensado (sobrando). None: não há o que
    continuar."""
    faltam, atual, alvo = conf["faltam"], conf["palavras"], conf["alvo_palavras"]
    if faltam > 0:
        if not _tem_roteiro(melhor):
            # começo vazio não se continua: era assim que a resposta à continuação (uma lista de perguntas)
            # virava o roteiro inteiro. Sem roteiro para continuar, o laço para e quem chamou vê o erro
            return None
        # o rascunho que já se despede: continuar depois dele colava texto novo DEPOIS do "obrigado por assistir" (o
        # coreano de 2026-11-23 se despedia aos 54% do vídeo), ou voltava vazio (o japonês de 30 min do mesmo dia,
        # parado em 13,4 min depois de duas continuações sem nada). O fechamento sai, o Claude continua o corpo, e o
        # fechamento volta para o fim
        corpo, fechamento = separar_fechamento(melhor)
        aviso(f"Conferindo o tempo: o roteiro dá {conf['previsto_min']} min e você pediu {minutos}. "
              f"O Claude está continuando ({atual} de {alvo} palavras)…")
        resto = _limpar(_claude(sistema, pedido + CONTINUAR.format(comeco=corpo[-12000:], faltam=_tamanho(faltam, lingua))
                                + (SEM_FECHAMENTO if fechamento else ""), modelo=ROTEIRO))
        if contar_palavras(resto) >= 30:
            return "\n\n".join(t for t in (corpo, resto, fechamento) if t)
        # a continuação voltou vazia: o Claude reescreve o roteiro inteiro, mais longo, com o fechamento só no fim
        aviso(f"Conferindo o tempo: o roteiro dá {conf['previsto_min']} min e você pediu {minutos}. "
              f"O Claude está reescrevendo mais longo ({atual} de {alvo} palavras)…")
        return _limpar(_claude(sistema, ALONGAR.format(minutos=minutos, atual=_tamanho(atual, lingua),
                                                       alvo=_tamanho(alvo, lingua), roteiro=melhor), modelo=ROTEIRO))
    aviso(f"Conferindo o tempo: o roteiro dá {conf['previsto_min']} min e você pediu {minutos}. "
          f"O Claude está condensando ({atual} para {alvo} palavras)…")
    return _limpar(_claude(sistema, CONDENSAR.format(minutos=minutos, atual=_tamanho(atual, lingua),
                                                     alvo=_tamanho(alvo, lingua), roteiro=melhor), modelo=ROTEIRO))


def _escrever_descricao(usuario_id: int, pasta, projeto_descricao_id, aviso=lambda _t: None) -> None:
    """A descrição do vídeo, escrita logo depois do roteiro (pedido do usuário em 2026-10-28: ela fica pronta
    enquanto o vídeo está sendo feito, em vez de só existir no fim, quando a fábrica monta o publicacao.json).

    Todo vídeo vai com descrição (pedido do usuário em 2026-11-17: "coloque sempre descrição para o Claude criar e
    ir com o vídeo"), então aqui são TENTATIVAS voltas antes de desistir. Falhar mesmo assim não derruba o roteiro:
    o roteiro é o que a pessoa pediu, o erro fica no roteiro.json para a tela de Revisão dizer, e quem for publicar
    escreve a descrição antes de subir (`descricao.garantir`)."""
    from . import descricao as _descricao
    aviso("Roteiro pronto. O Claude está escrevendo a descrição e as tags…")
    meta = json.loads((pasta / "roteiro.json").read_text(encoding="utf-8"))
    meta["descricao_erro"] = ""
    for volta in range(TENTATIVAS_DESCRICAO):
        try:
            _descricao.gerar(usuario_id, pasta, projeto_descricao_id)
            meta["descricao_erro"] = ""
            break
        except Exception as erro:
            meta["descricao_erro"] = str(erro)[:300]
            if volta + 1 < TENTATIVAS_DESCRICAO:
                aviso(f"A descrição falhou ({str(erro)[:80]}). Tentando de novo…")
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
    pasta = _pasta_nova(titulo)
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
    despedida = despedida_no_meio(texto)
    if despedida:
        return (f"ele se despede no meio do vídeo (\"{despedida}\") e continua depois: a despedida é só no fim. Mande o "
                "Claude escrever de novo, ou tire a despedida do meio aqui.")
    veio = lingua_errada(texto, meta.get("lingua") or "")
    if veio:
        return (f"ele não está escrito em {meta['lingua']}: a voz do canal fala {meta['lingua']} e o texto veio em "
                f"{veio}.")
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


# o tema da Nova produção vale para os textos na tela (animacoes.TEMAS) e para as cenas animadas (animation_ai.TEMAS),
# que têm os nomes deles
TEMA_DAS_CENAS_ANIMADAS = {"noticiario": "editorial", "dossie": "misterio", "cinema": "cinema", "jornal": "editorial",
                           "caderno": "apple", "planilha": "blueprint", "hacker": "neon", "terror": "noite", "colagem": "riso",
                           "cinetico": "impacto", "arquivo": "misterio", "reaberto": "noite",
                           "investigacao": "misterio"}
RITMOS = {"4-6": (4.0, 6.0), "5-8": (5.0, 8.0)}


def ajustes_do_video(opcoes: dict | None) -> tuple[dict, dict]:
    """(config_override, perfil_override) do pedido: o que muda só neste vídeo, sem tocar no perfil do canal.
    A folga de 5 pontos é o teto da cota da fábrica."""
    o = opcoes or {}
    config, perfil = {}, {}
    if o.get("footage_real"):
        alvo = int(o["footage_real"]) / 100
        config["garimpo"] = {"ligado": True, "alvo": alvo, "teto": round(alvo + 0.05, 2)}
    animacoes = {}
    if o.get("tema"):
        animacoes["estilo"] = {"tema": o["tema"]}
        config["animation_ai"] = {"tema": TEMA_DAS_CENAS_ANIMADAS[o["tema"]]}
    if o.get("som_textos"):
        animacoes["som"] = True
    if animacoes:
        config["animacoes"] = animacoes
    if o.get("ritmo") in RITMOS:
        minimo, maximo = RITMOS[o["ritmo"]]
        config["cenas"] = {"segundos_minimo": minimo, "segundos_maximo": maximo}
    if o.get("ia") == "sem" or o.get("ia_pct") == 0:
        config["ia"] = {"ativa": False}
    elif o.get("ia_pct"):
        # a mesma parte como alvo e como teto: a fábrica sobe até ela e não passa dela
        config["ia"] = {"fracao": int(o["ia_pct"]) / 100, "teto": int(o["ia_pct"]) / 100}
    if o.get("video_ia"):
        config["video_ia"] = {"fracao": int(o["video_ia"]) / 100}
    if o.get("acervo"):
        config["midia"] = {"acervo": o["acervo"]}
    if o.get("sem_narracao"):
        # o Canal de teste de 5 min (2026-11-12): voz muda no vídeo, nenhuma IA de imagem ou vídeo, nada do YouTube
        config.update({"ia": {"ativa": False}, "video_ia": {"fracao": 0}, "garimpo": {"ligado": False}})
        perfil.update({"narracao_no_video": False, "legenda_na_tela": False, "avatar": {"ativo": False}})
    if o.get("musica") == "sem":
        config["trilha"] = {"ativo": False}
        perfil["musica"] = None
    if o.get("avatar") == "sem":
        perfil["avatar"] = {"ativo": False}
    for campo, chave in (("edicao", "visual"), ("transicao", "transicao"), ("camada", "camada")):
        if o.get(campo):
            perfil[chave] = o[campo]
    return config, perfil


def enviar(usuario_id: int, nome: str, perfil: str, opcoes: dict | None = None) -> dict:
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
    # a narração: a voz do perfil tem de falar a língua do roteiro (2026-11-20). Sem narração não há voz para conferir
    codigo = codigo_da_lingua(meta.get("lingua") or "")
    if codigo and not (opcoes or {}).get("sem_narracao"):
        from . import producao
        da_voz = producao.lingua_da_voz(perfil)
        if da_voz and codigo_da_lingua(da_voz) != codigo:
            raise RuntimeError(f"A voz do perfil {perfil} fala {da_voz} e o roteiro é em {meta['lingua']}: a "
                               "narração sairia na língua errada. Escolha uma voz que fale a língua do roteiro.")
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
    if codigo:
        # a fábrica lê daqui a língua dos motions e de todo texto da tela (idioma.lingua): pelo texto ela só
        # reconhecia pt, en, es, ja e ko, e o resto caía em português
        dados["lingua"] = codigo
    config, do_perfil = ajustes_do_video(opcoes)
    if config:
        dados["config_override"] = {**(dados.get("config_override") or {}), **config}
    if do_perfil:
        dados["perfil_override"] = {**(dados.get("perfil_override") or {}), **do_perfil}
    (destino / "projeto.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    if (pasta / "thumbnail.jpg").exists():
        shutil.copy2(pasta / "thumbnail.jpg", destino / "thumbnail_referencia.jpg")
    # a descrição escrita junto com o roteiro vai junto: a extensão já acha este vídeo no Studio com o vídeo
    # ainda sendo feito, em vez de esperar o publicacao.json da fábrica
    from . import descricao as _descricao
    if not _descricao.ler(pasta).get("sinopse"):
        # falhou na hora do roteiro: última chance de escrever antes de a fábrica começar o vídeo
        try:
            _descricao.gerar(usuario_id, pasta)
            meta["descricao_erro"] = ""
        except Exception as erro:  # noqa: BLE001 (sem descrição o vídeo ainda é feito; quem publica escreve antes)
            meta["descricao_erro"] = str(erro)[:300]
    levou = _descricao.levar(pasta, destino, meta["titulo"], perfil)
    meta["fabrica"] = {"projeto": final, "perfil": perfil, "enviado": banco.agora(), "descricao": levou,
                       "palavras": contar_palavras((pasta / "roteiro.txt").read_text(encoding="utf-8"))}
    (pasta / "roteiro.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    estimativa = "\n".join(l for l in (r.stdout or "").splitlines() if "US$" in l or "min" in l)[-600:]
    return {"projeto": final, "pasta": str(destino), "estimativa": estimativa,
            "proximo": f"uv run fabrica tudo {final}"}
