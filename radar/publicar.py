"""A ajuda para publicar no YouTube Studio (pedido do usuário em 2026-10-20: "adicionar a extensão na hora de postar o
vídeo com anúncios e tudo"). A extensão mostra um painel na tela de upload com o título, a descrição e as tags que a
fábrica montou, e a lista do que marcar (anúncios, questionário de anunciantes, público e visibilidade). Ela não
clica nem publica nada: a pessoa copia e marca (escolha do usuário: "só um painel de ajuda").

O vídeo é achado pelo nome do arquivo que está subindo: a entrega no PC usa o título como nome do .mp4
(entrega_pc.json), mas pode ser também o nome da pasta do projeto ou o título do kit. Tudo sai do publicacao.json da
pasta do projeto, então funciona com a fábrica desligada."""
import json
import re
import unicodedata
from pathlib import Path


def _ler(arquivo: Path) -> dict:
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


# A descrição que o Radar escreveu junto com o roteiro (descricao.py), copiada para a pasta do projeto na hora do
# envio. Ela existe antes de a fábrica terminar o vídeo: é por isso que o projeto já aparece no Studio sem o
# publicacao.json dela, e é por isso que o texto dela ganha do texto da fábrica no kit.
RADAR = "publicacao_radar.json"


def _quando(pasta: Path) -> float:
    """Quando este projeto ficou pronto para publicar (0 quando não tem nem o kit da fábrica nem o do Radar)."""
    quando = 0.0
    for nome in ("publicacao.json", RADAR):
        try:
            quando = max(quando, (pasta / nome).stat().st_mtime)
        except OSError:
            continue
    return quando


def normalizar(texto: str) -> str:
    """Sem acento, sem extensão, só letras e números separados por espaço: 'Desextinção: Os...mp4' -> 'desextincao os'.

    Letras de qualquer escrita ficam (2026-11-08): só com a-z, o título coreano "한국 자동차는 … 7대!" virava "7", curto
    demais para casar, e a extensão nunca achava os vídeos da Coreia e do Japão: a descrição completa do Radar não
    entrava e o Studio ficava com a curta."""
    texto = re.sub(r"\.(mp4|mov|mkv|webm|avi|m4v|wmv|flv|mpe?g)$", "", (texto or "").strip(), flags=re.I)
    sem_acento = "".join(ch for ch in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(ch))
    texto = unicodedata.normalize("NFC", sem_acento).casefold()
    return " ".join(re.findall(r"[^\W_]+", texto))


def _nomes(pasta: Path) -> list[str]:
    """Os nomes que o arquivo do vídeo pode ter: o da entrega, o título do kit, o da entrega no Radar e o da pasta."""
    pub, proj, entrega = _ler(pasta / "publicacao.json"), _ler(pasta / "projeto.json"), _ler(pasta / "entrega_pc.json")
    nomes = [Path(str(entrega.get("video") or "").replace("\\", "/")).name, pub.get("titulo"),
             (pub.get("textos") or {}).get("titulo"), _ler(pasta / RADAR).get("titulo"),
             proj.get("titulo_entrega"), pasta.name]
    return [n for n in (normalizar(str(x)) for x in nomes if x) if n]


def perfil_do_projeto(pasta: Path) -> str:
    """O perfil da fábrica do projeto ("...perfis/canal-uk-market.yaml" -> "canal-uk-market"), que diz de que canal
    é o vídeo: é por ele que o Radar acha o modelo de descrição do canal."""
    caminho = str(_ler(pasta / "projeto.json").get("perfil") or "").replace(chr(92), "/")
    return Path(caminho).stem if caminho else ""


def _projetos(raiz: Path) -> list[Path]:
    """Os projetos com kit de publicação, os mais recentes primeiro."""
    try:
        pastas = [p for p in raiz.iterdir() if p.is_dir() and not p.name.startswith("_") and _quando(p)]
    except OSError:
        return []
    return sorted(pastas, key=_quando, reverse=True)


def achar(raiz: Path, arquivo: str) -> str | None:
    """O nome do projeto cujo vídeo tem esse nome de arquivo (igual primeiro; depois um contendo o outro)."""
    alvo = normalizar(arquivo)
    if len(alvo) < 6 or alvo in ("final", "video", "final video"):
        return None
    projetos = [(p.name, _nomes(p)) for p in _projetos(raiz)]
    for nome, nomes in projetos:
        if alvo in nomes:
            return nome
    for nome, nomes in projetos:
        if any(len(n) >= 12 and (n in alvo or alvo in n) for n in nomes):
            return nome
    return None


def opcoes(raiz: Path, limite: int = 40) -> list[dict]:
    """Para escolher na mão quando o nome do arquivo não diz qual é."""
    return [{"nome": p.name, "titulo": _titulo(p)} for p in _projetos(raiz)[:limite]]


def _titulo(pasta: Path) -> str:
    # o do Radar primeiro: é o título pedido, limpo. O da fábrica no vídeo japonês veio com o original coreano entre
    # parênteses ("韓国の… (한국의…)") e ia assim para o YouTube (2026-11-07)
    pub = _ler(pasta / "publicacao.json")
    return str(_ler(pasta / RADAR).get("titulo") or pub.get("titulo") or (pub.get("textos") or {}).get("titulo")
               or pasta.name)


def kit(pasta: Path) -> dict:
    """O que vai nos campos do Studio, já no formato de colar (as tags separadas por vírgula, como o Studio aceita)."""
    pub = _ler(pasta / "publicacao.json")
    # a descrição escrita no Radar junto com o roteiro ganha da da fábrica: chega no minuto do envio (o vídeo ainda
    # está sendo feito) e saiu do projeto de descrição do canal, não do molde da fábrica
    radar = _ler(pasta / RADAR)
    textos = pub.get("textos") or {}
    tags = [str(t).strip() for t in (radar.get("tags") or pub.get("tags") or textos.get("tags") or []) if str(t).strip()]
    descricao = str(radar.get("descricao") or pub.get("descricao") or textos.get("resumo") or "")
    capitulos = [c for c in pub.get("capitulos") or [] if isinstance(c, dict)]
    return {
        "nome": pasta.name,
        "titulo": _titulo(pasta),
        "titulos_alt": [str(t) for t in pub.get("titulos_alt") or textos.get("titulos_alt") or []],
        "descricao": descricao,
        # a sinopse é o resumo que abre a descrição da fábrica: 2 ou 3 frases do que o vídeo mostra
        "sinopse": str(radar.get("sinopse") or textos.get("resumo") or "").strip() or descricao.split("\n\n")[0].strip(),
        "tags": tags,
        "hashtags": [str(h) for h in radar.get("hashtags") or pub.get("hashtags") or textos.get("hashtags") or []],
        "comentario_fixado": str(pub.get("comentario_fixado") or textos.get("comentario_fixado") or ""),
        # a descrição já traz os capítulos; o mid-roll fica melhor entre eles
        "capitulos": [{"tempo": str(c.get("tempo", "")), "nome": str(c.get("nome", "")), "inicio": c.get("inicio")} for c in capitulos],
        "sintetico": bool(pub.get("sintetico") or radar.get("sintetico")),
        # de onde veio o texto do kit: "radar" (escrito junto com o roteiro) ou "fabrica"
        "origem": "radar" if radar.get("descricao") else "fabrica",
        "legenda": str(pub.get("legenda") or ""),
        "duracao": _duracao(pasta),
        # o título e a sinopse em português, só para quem publica entender (nunca vão para o YouTube)
        "traducao": radar.get("traducao") or _ler(pasta / TRADUCAO) or {},
    }


TRADUCAO = "traducao_radar.json"   # a tradução feita depois, para os vídeos de antes desta função


def traduzir(pasta: Path, k: dict) -> dict:
    """O título e a sinopse em português, para o kit que ainda não trouxe. Fica guardado na pasta do projeto."""
    if (k.get("traducao") or {}).get("titulo"):
        return k["traducao"]
    from . import ia
    from .config import MODELO_TEXTO
    titulo = (ia.traduzir_exato(k.get("titulo") or "", ["pt"]) or {}).get("pt", "")
    sinopse = ""
    if (k.get("sinopse") or "").strip():
        r = ia._perguntar(MODELO_TEXTO, "Traduza para o português do Brasil, fiel, sem resumir. Responda só JSON: "
                          "{\"texto\": \"...\"}.", k["sinopse"][:3000], esperar=20) or {}
        sinopse = str(r.get("texto") or "").strip()
    feito = {"titulo": titulo, "sinopse": sinopse}
    if titulo or sinopse:
        try:
            (pasta / TRADUCAO).write_text(json.dumps(feito, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    return feito


# ---------------------------------------------------------------- os modelos de descrição
# Escritos a partir da descrição que o usuário mandou em 2026-10-23 ("a descrição está vindo ruim... quero que você
# padronize para os canais"), que é a que ele de fato usa: a apresentação do canal, o objetivo e o aviso legal
# inteiro. O que muda de canal para canal ({canal}, {marcas}) é campo; o resto é igual em todo vídeo.
#
# "consumo" é o texto dele, para os canais de mercado e preço; "geral" é o mesmo esqueleto sem a parte de
# supermercado, para um canal de outro assunto não sair falando de rótulo de produto.

MODELOS = {
    "inglês": {
        "consumo": """{sinopse}

{canal} breaks down everyday supermarket products, grocery prices and consumer trends using publicly available information and official sources to help shoppers make more informed decisions.
We cover popular brands and major retailers, including {marcas}.
From food and drinks to household essentials, our videos explore product ingredients, changing prices, value for money and important developments affecting shoppers.

Our goal is to help consumers understand what they are buying, spend their money wisely and make smarter shopping decisions through clear, straightforward and consumer-focused analysis. New videos are published regularly.

Disclaimer:

This channel is intended for educational and informational purposes only. Our videos present commentary, analysis and opinions based on publicly available information, including ingredient lists, nutrition labels, product packaging, company statements, official regulatory publications, pricing information and independent reporting.

The content does not allege illegal or unlawful conduct by any individual, brand, retailer or organisation. References to products, companies and supermarkets are made solely for consumer education, commentary and public-interest discussion. Viewers are encouraged to consult official sources and form their own independent conclusions.

Information may be obtained from publicly accessible company websites, product labels, regulatory bodies, consumer reports and other reliable sources. Product formulations, prices, availability and policies may change over time.

Nothing on this channel constitutes medical, legal or professional advice. Viewers should verify relevant information with appropriate official sources before making decisions.

{hashtags}""",
        "geral": """{sinopse}

{canal} explains this subject using publicly available information and official sources, so viewers can make more informed decisions. New videos are published regularly.

Disclaimer:

This channel is intended for educational and informational purposes only. Our videos present commentary, analysis and opinions based on publicly available information, including official publications, company statements, independent reporting and other public records.

The content does not allege illegal or unlawful conduct by any individual, brand, company or organisation. References to people, products and companies are made solely for education, commentary and public-interest discussion. Viewers are encouraged to consult official sources and form their own independent conclusions.

Information may change over time. Nothing on this channel constitutes medical, legal or professional advice. Viewers should verify relevant information with appropriate official sources before making decisions.

{hashtags}""",
    },
    "português": {
        "consumo": """{sinopse}

O {canal} explica produtos de supermercado, preços e o que muda no mercado usando informação de acesso público e fontes oficiais, para ajudar quem faz compras a decidir melhor.
Falamos de marcas conhecidas e das grandes redes, como {marcas}.
De comida e bebida ao que não pode faltar em casa, os vídeos olham os ingredientes, os preços que mudam, se vale o que custa e o que de fato afeta quem compra.

A ideia é ajudar o consumidor a entender o que está levando e a gastar melhor, com uma análise clara, direta e do lado de quem compra. Vídeos novos toda semana.

Aviso:

Este canal é feito para fins informativos e educativos. Os vídeos trazem comentário, análise e opinião a partir de informações de acesso público: lista de ingredientes, informação nutricional, embalagem, comunicados das empresas, publicações oficiais de órgãos reguladores, preços e reportagens independentes.

O conteúdo não acusa nenhuma pessoa, marca, rede ou empresa de conduta ilegal. Produtos, empresas e supermercados são citados apenas para informar o consumidor, comentar e discutir assunto de interesse público. Procure as fontes oficiais e tire as suas próprias conclusões.

As informações podem vir dos sites das empresas, de rótulos, de órgãos reguladores, de relatórios de defesa do consumidor e de outras fontes confiáveis. Fórmulas, preços, disponibilidade e políticas mudam com o tempo.

Nada aqui é orientação médica, jurídica ou profissional. Confira o que for decidir nas fontes oficiais.

{hashtags}""",
        "geral": """{sinopse}

O {canal} explica este assunto usando informação de acesso público e fontes oficiais, para quem assiste decidir melhor. Vídeos novos toda semana.

Aviso:

Este canal é feito para fins informativos e educativos. Os vídeos trazem comentário, análise e opinião a partir de informações de acesso público: publicações oficiais, comunicados das empresas, reportagens independentes e outros registros públicos.

O conteúdo não acusa nenhuma pessoa, marca ou empresa de conduta ilegal. Pessoas, produtos e empresas são citados apenas para informar, comentar e discutir assunto de interesse público. Procure as fontes oficiais e tire as suas próprias conclusões.

As informações mudam com o tempo. Nada aqui é orientação médica, jurídica ou profissional. Confira o que for decidir nas fontes oficiais.

{hashtags}""",
    },
    "espanhol": {
        "consumo": """{sinopse}

{canal} explica los productos del supermercado, los precios y lo que cambia en el mercado con información de acceso público y fuentes oficiales, para ayudar a quien hace la compra a decidir mejor.
Hablamos de marcas conocidas y de las grandes cadenas, como {marcas}.
De la comida y la bebida a lo que no puede faltar en casa, los videos miran los ingredientes, los precios que cambian, si vale lo que cuesta y lo que de verdad afecta a quien compra.

La idea es ayudar al consumidor a entender lo que está comprando y a gastar mejor, con un análisis claro, directo y del lado de quien compra. Videos nuevos cada semana.

Aviso:

Este canal se hace con fines informativos y educativos. Los videos presentan comentario, análisis y opinión a partir de información de acceso público: lista de ingredientes, información nutricional, envases, comunicados de las empresas, publicaciones oficiales de organismos reguladores, precios y reportajes independientes.

El contenido no acusa a ninguna persona, marca, cadena o empresa de conducta ilegal. Los productos, las empresas y los supermercados se citan solo para informar al consumidor, comentar y discutir un asunto de interés público. Consulte las fuentes oficiales y saque sus propias conclusiones.

La información puede venir de los sitios de las empresas, de etiquetas, de organismos reguladores, de informes de consumo y de otras fuentes confiables. Fórmulas, precios, disponibilidad y políticas cambian con el tiempo.

Nada de esto es consejo médico, jurídico o profesional. Verifique en las fuentes oficiales antes de decidir.

{hashtags}""",
        "geral": """{sinopse}

{canal} explica este tema con información de acceso público y fuentes oficiales, para que quien mira decida mejor. Videos nuevos cada semana.

Aviso:

Este canal se hace con fines informativos y educativos. Los videos presentan comentario, análisis y opinión a partir de información de acceso público: publicaciones oficiales, comunicados de las empresas, reportajes independientes y otros registros públicos.

El contenido no acusa a ninguna persona, marca o empresa de conducta ilegal. Las personas, los productos y las empresas se citan solo para informar, comentar y discutir un asunto de interés público. Consulte las fuentes oficiales y saque sus propias conclusiones.

La información cambia con el tiempo. Nada de esto es consejo médico, jurídico o profesional. Verifique en las fuentes oficiales antes de decidir.

{hashtags}""",
    },
    # coreano e japonês (pedido do usuário em 2026-11-07): sem eles, o vídeo coreano saía com a sinopse em coreano e
    # todo o texto fixo do canal em inglês logo embaixo
    "coreano": {
        "consumo": """{sinopse}

{canal}은(는) 공개된 정보와 공식 자료를 바탕으로 마트 상품, 가격, 소비 트렌드를 알기 쉽게 풀어 드립니다. {marcas} 같은 잘 알려진 브랜드와 대형 유통업체도 다룹니다.
식품과 음료부터 생활필수품까지, 원재료와 가격 변화, 가격 대비 가치, 그리고 소비자에게 실제로 영향을 주는 내용을 살펴봅니다. 새 영상은 매주 올라옵니다.

안내:

이 채널은 정보 제공과 교육을 목적으로 합니다. 영상은 원재료 표시, 영양 정보, 포장, 기업 발표, 규제 기관의 공식 자료, 가격과 독립 보도 등 공개된 정보를 바탕으로 한 해설과 분석, 의견입니다.

특정 개인, 브랜드, 유통업체, 기업이 불법 행위를 했다고 주장하지 않습니다. 상품과 기업은 소비자 정보 제공과 공익적 논의를 위해서만 언급됩니다. 공식 자료를 확인하고 스스로 판단해 주세요.

제품 구성, 가격, 판매 여부와 정책은 바뀔 수 있습니다. 이 채널의 내용은 의학적, 법률적, 전문적 조언이 아닙니다.

{hashtags}""",
        "geral": """{sinopse}

{canal}은(는) 공개된 정보와 공식 자료를 바탕으로 이 주제를 알기 쉽게 풀어 드립니다. 새 영상은 매주 올라옵니다.

안내:

이 채널은 정보 제공과 교육을 목적으로 합니다. 영상은 공식 발표, 기업 자료, 독립 보도와 그 밖의 공개 기록을 바탕으로 한 해설과 분석, 의견입니다.

특정 개인, 브랜드, 기업이 불법 행위를 했다고 주장하지 않습니다. 사람과 상품, 기업은 정보 제공과 공익적 논의를 위해서만 언급됩니다. 공식 자료를 확인하고 스스로 판단해 주세요.

정보는 시간이 지나며 바뀔 수 있습니다. 이 채널의 내용은 의학적, 법률적, 전문적 조언이 아닙니다.

{hashtags}""",
    },
    "japonês": {
        "consumo": """{sinopse}

{canal}では、公開されている情報と公式の資料をもとに、スーパーの商品や価格、消費の動きをわかりやすく解説しています。{marcas}など、よく知られたブランドや大手チェーンも取り上げます。
食品や飲み物から日用品まで、原材料、価格の変化、値段に見合う価値、そして買う人に本当に関わることを見ていきます。新しい動画は毎週公開しています。

ご案内:

このチャンネルは情報提供と学習を目的としています。動画は、原材料表示、栄養成分、パッケージ、企業の発表、行政機関の公式資料、価格、独立した報道など、公開された情報にもとづく解説・分析・意見です。

特定の個人、ブランド、チェーン、企業が違法な行為をしたと主張するものではありません。商品や企業は、消費者への情報提供と公共の関心にもとづく議論のためにのみ取り上げています。公式の情報源を確認し、ご自身で判断してください。

商品の内容、価格、販売状況や方針は変わることがあります。このチャンネルの内容は医療・法律・専門的な助言ではありません。

{hashtags}""",
        "geral": """{sinopse}

{canal}では、公開されている情報と公式の資料をもとに、このテーマをわかりやすく解説しています。新しい動画は毎週公開しています。

ご案内:

このチャンネルは情報提供と学習を目的としています。動画は、公式の発表、企業の資料、独立した報道、その他の公開記録にもとづく解説・分析・意見です。

特定の個人、ブランド、企業が違法な行為をしたと主張するものではありません。人物や商品、企業は、情報提供と公共の関心にもとづく議論のためにのみ取り上げています。公式の情報源を確認し、ご自身で判断してください。

情報は時間とともに変わることがあります。このチャンネルの内容は医療・法律・専門的な助言ではありません。

{hashtags}""",
    },
}

TIPOS = {"consumo": "Mercado e consumo", "geral": "Geral"}


def rodape_padrao(lingua: str = "", tipo: str = "geral", canal: str = "", marcas: str = "") -> str:
    """O modelo pronto virado em rodapé: sem o resumo e sem as hashtags, que a fábrica já põe sozinha.

    É o texto fixo do canal (apresentação e aviso legal) que fecha a descrição de todo vídeo. Vai para o
    perfil da fábrica, não para o banco do Radar: quem escreve a descrição é ela."""
    modelo = modelo_padrao(lingua, tipo)
    linhas = [l for l in modelo.split("\n") if "{sinopse}" not in l and "{hashtags}" not in l]
    return montar_descricao("\n".join(linhas), {}, canal, marcas).strip()


def modelo_padrao(lingua: str = "", tipo: str = "geral") -> str:
    """O modelo pronto da língua do canal. Língua que não temos cai no inglês, que é a língua da maioria deles."""
    por_lingua = MODELOS.get(lingua or "") or MODELOS["inglês"]
    return por_lingua.get(tipo) or por_lingua["geral"]


# o que a pessoa pode usar no modelo (o resto do texto vai como está escrito)
CAMPOS = ("titulo", "sinopse", "canal", "hashtags", "tags", "capitulos", "marcas")


def montar_descricao(modelo: str, kit_do_video: dict, canal: str = "", marcas: str = "") -> str:
    """A descrição do modelo do canal: o mesmo texto sempre, trocando só o que é deste vídeo.

    Nada de lista de capítulos por padrão (pedido do usuário em 2026-10-22: "sem spoilers, apenas uma sinopse"): os
    capítulos só entram se o modelo pedir {capitulos}.

    A linha cujos campos estão todos vazios sai inteira. Sem isso, um canal que não lista marcas publicaria
    "We cover popular brands and major retailers, including ." — a frase pela metade é pior que a falta dela."""
    modelo = (modelo or "").strip()
    if not modelo:
        return str(kit_do_video.get("descricao") or "")
    valores = {
        "titulo": str(kit_do_video.get("titulo") or ""),
        "sinopse": str(kit_do_video.get("sinopse") or ""),
        "canal": canal or "",
        "hashtags": " ".join(kit_do_video.get("hashtags") or []),
        "tags": ", ".join(kit_do_video.get("tags") or []),
        "capitulos": "\n".join(f"{c.get('tempo', '')} {c.get('nome', '')}".strip()
                               for c in kit_do_video.get("capitulos") or []),
        "marcas": marcas or "",
    }
    linhas = []
    for linha in modelo.split("\n"):
        pedidos = [c for c in re.findall(r"\{(\w+)\}", linha) if c in valores]
        if pedidos and not any(valores[c].strip() for c in pedidos):
            continue
        for campo in CAMPOS:
            linha = linha.replace("{" + campo + "}", valores[campo])
        linhas.append(linha)
    texto = re.sub(r"[ \t]+\n", "\n", "\n".join(linhas))
    return re.sub(r"\n{3,}", "\n\n", texto).strip()[:5000]


def _duracao(pasta: Path) -> float | None:
    """Os segundos do vídeo (anúncio no meio só a partir de 8 minutos), pela narração alinhada da fábrica."""
    valor = _ler(pasta / "alinhamento.json").get("duracao")
    return float(valor) if isinstance(valor, (int, float)) and valor > 0 else None


# ---------------------------------------------------------------- escrever quando o vídeo não é da fábrica
# Pedido do usuário em 2026-10-25, depois de olhar a ajuda de postagem do Dotti Finder (studio_ia.js): lá a extensão
# escreve um rascunho da descrição a partir do título e sugere as tags que as pessoas buscam. O vídeo que sai da
# fábrica já vem com título, descrição, tags e capítulos no publicacao.json — para esse, isto não serve e nem é
# oferecido. Serve para o vídeo gravado fora da fábrica, em que o painel do Studio dizia só "título e descrição
# ficam com você".
#
# Quem escreve é o Claude Code que já está instalado (roteiro_claude._claude), o mesmo do Roteiro: nada de chave nova
# nem de cota do YouTube. O que volta é rascunho e vai para o campo do Studio, onde a pessoa lê e muda antes de
# publicar — quem aperta Publicar continua sendo ela.

TAGS_TETO = 500            # o teto do campo de tags do YouTube, contando as vírgulas

SISTEMA_DESCRICAO = """Você escreve a descrição de vídeos de canais dark do YouTube (narrados, sem rosto).
Escreva de 2 a 4 frases dizendo o que a pessoa vai ver, na mesma língua do título, em tom direto e sem prometer o que
o vídeo não cumpre. Nada de "neste vídeo você vai descobrir", nada de emoji, nada de hashtag, nada de link e nada de
pedir inscrição (o canal já tem um rodapé fixo para isso). Não invente fato, número, data nem fala de pessoa real: se
o título não diz, não afirme. Responda SÓ com o texto da descrição, sem título e sem aspas."""

SISTEMA_TAGS = """Você escolhe as tags de vídeos do YouTube: as palavras que as pessoas realmente digitam na busca
para achar um vídeo desse assunto. Escreva de 12 a 20 tags na mesma língua do título, das mais buscadas para as mais
específicas, sem repetir a mesma ideia, sem hashtag, sem aspas e sem número na frente. Nada de marca ou de nome de
pessoa que o título não cite. Responda SÓ com a lista, uma tag por linha."""

_SUJEIRA = re.compile(r"^[\s\-–—•*\d.)]+")


def tags_que_cabem(tags: list[str], teto: int = TAGS_TETO) -> list[str]:
    """As tags que cabem no campo do YouTube, na ordem em que vieram: o que passa do teto é cortado aqui, em vez de
    o Studio recusar o campo inteiro."""
    saida: list[str] = []
    soma = 0
    vistas: set[str] = set()
    for t in tags:
        t = " ".join(str(t).split())
        chave = t.lower()
        if not t or chave in vistas:
            continue
        custo = len(t) + (2 if saida else 0)      # a ", " entre uma tag e a seguinte conta no teto
        if soma + custo > teto:
            continue
        saida.append(t)
        soma += custo
        vistas.add(chave)
    return saida


def escrever(o_que: str, titulo: str, fala: str = "") -> dict:
    """Um rascunho de descrição ou a lista de tags, do título e da fala do vídeo (quando já existe legenda)."""
    from . import roteiro_claude
    titulo = " ".join(str(titulo).split())[:300]
    pedido = f"Título do vídeo: {titulo}\n\n"
    if fala:
        pedido += f"Começo da fala do vídeo (transcrição):\n{fala[:4000]}\n\n"
    if o_que == "tags":
        texto = roteiro_claude._claude(SISTEMA_TAGS, pedido + "Escreva as tags.")
        cruas = [_SUJEIRA.sub("", l).strip().strip('"#') for l in texto.split("\n")]
        tags = tags_que_cabem([t for t in cruas if 2 <= len(t) <= 60])
        if not tags:
            raise RuntimeError("O Claude não devolveu nenhuma tag que sirva.")
        return {"tags": tags}
    # a descrição sai pelo mesmo escritor da descrição completa (descricao.escrever): dois parágrafos, com o mínimo de
    # caracteres de cada escrita. O SISTEMA_DESCRICAO antigo ("de 2 a 4 frases") dava uns 150 caracteres em coreano
    # (pedido do usuário em 2026-11-08: "canal da Coreia sempre está com uma descrição muito curta")
    from . import descricao
    dados = descricao.escrever(titulo, fala or titulo)
    texto = (dados.get("sinopse") or "").strip()
    if not texto:
        raise RuntimeError("O Claude não devolveu nenhuma descrição.")
    return {"descricao": texto[:4000], **({"traducao": dados["traducao"]} if dados.get("traducao") else {})}
