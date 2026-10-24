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


def normalizar(texto: str) -> str:
    """Sem acento, sem extensão, só letras e números separados por espaço: 'Desextinção: Os...mp4' -> 'desextincao os'."""
    texto = re.sub(r"\.(mp4|mov|mkv|webm|avi|m4v|wmv|flv|mpe?g)$", "", (texto or "").strip(), flags=re.I)
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", texto))


def _nomes(pasta: Path) -> list[str]:
    """Os nomes que o arquivo do vídeo pode ter: o da entrega, o título do kit, o da entrega no Radar e o da pasta."""
    pub, proj, entrega = _ler(pasta / "publicacao.json"), _ler(pasta / "projeto.json"), _ler(pasta / "entrega_pc.json")
    nomes = [Path(str(entrega.get("video") or "").replace("\\", "/")).name, pub.get("titulo"),
             (pub.get("textos") or {}).get("titulo"), proj.get("titulo_entrega"), pasta.name]
    return [n for n in (normalizar(str(x)) for x in nomes if x) if n]


def perfil_do_projeto(pasta: Path) -> str:
    """O perfil da fábrica do projeto ("...perfis/canal-uk-market.yaml" -> "canal-uk-market"), que diz de que canal
    é o vídeo: é por ele que o Radar acha o modelo de descrição do canal."""
    caminho = str(_ler(pasta / "projeto.json").get("perfil") or "").replace(chr(92), "/")
    return Path(caminho).stem if caminho else ""


def _projetos(raiz: Path) -> list[Path]:
    """Os projetos com kit de publicação, os mais recentes primeiro."""
    try:
        pastas = [p for p in raiz.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "publicacao.json").exists()]
    except OSError:
        return []
    return sorted(pastas, key=lambda p: (p / "publicacao.json").stat().st_mtime, reverse=True)


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
    pub = _ler(pasta / "publicacao.json")
    return str(pub.get("titulo") or (pub.get("textos") or {}).get("titulo") or pasta.name)


def kit(pasta: Path) -> dict:
    """O que vai nos campos do Studio, já no formato de colar (as tags separadas por vírgula, como o Studio aceita)."""
    pub = _ler(pasta / "publicacao.json")
    textos = pub.get("textos") or {}
    tags = [str(t).strip() for t in (pub.get("tags") or textos.get("tags") or []) if str(t).strip()]
    descricao = str(pub.get("descricao") or textos.get("resumo") or "")
    capitulos = [c for c in pub.get("capitulos") or [] if isinstance(c, dict)]
    return {
        "nome": pasta.name,
        "titulo": _titulo(pasta),
        "titulos_alt": [str(t) for t in pub.get("titulos_alt") or textos.get("titulos_alt") or []],
        "descricao": descricao,
        # a sinopse é o resumo que abre a descrição da fábrica: 2 ou 3 frases do que o vídeo mostra
        "sinopse": str(textos.get("resumo") or "").strip() or descricao.split("\n\n")[0].strip(),
        "tags": tags,
        "hashtags": [str(h) for h in pub.get("hashtags") or textos.get("hashtags") or []],
        "comentario_fixado": str(pub.get("comentario_fixado") or textos.get("comentario_fixado") or ""),
        # a descrição já traz os capítulos; o mid-roll fica melhor entre eles
        "capitulos": [{"tempo": str(c.get("tempo", "")), "nome": str(c.get("nome", "")), "inicio": c.get("inicio")} for c in capitulos],
        "sintetico": bool(pub.get("sintetico")),
        "legenda": str(pub.get("legenda") or ""),
        "duracao": _duracao(pasta),
    }


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
