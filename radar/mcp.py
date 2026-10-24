"""O Radar dentro do Claude e do ChatGPT: um servidor MCP de leitura.

O Dotti vende isso desde outubro de 2026 (cota de perguntas por plano) e é a única porta que o Radar não tinha: os
dados estão todos aqui, com 237 rotas, mas só o painel e a extensão sabiam pedir. Com o MCP, a pessoa conversa com
os próprios canais — "quais canais novos de documentário estão crescendo?" — sem abrir o site.

Como funciona: um servidor **stdio** (uma linha de JSON por mensagem) que fala com o Radar deste computador pela
própria API HTTP. Falar pela API, e não pelo banco, é de propósito: as regras de filtro, de plano e de cota moram
no servidor, e o MCP não pode ter uma segunda versão delas para desencontrar.

**Só lê.** Nenhuma ferramenta mede canal, garimpa ou grava: o que gasta a cota do YouTube continua sendo escolha
da pessoa, no painel. Ligar:

    claude mcp add radar -- uv run python -m radar mcp

Com o Radar aberto para a rede (`--publico`), o MCP precisa de uma sessão: `RADAR_MCP_COOKIE` leva o cookie.
`RADAR_MCP_BASE` troca o endereço do Radar (o padrão é o deste computador).
"""
import json
import os
import sys

from .config import NOME, PORTA

PROTOCOLO = "2025-06-18"
VERSAO = "1.0.0"
BASE = (os.environ.get("RADAR_MCP_BASE") or f"http://127.0.0.1:{PORTA}").rstrip("/")
LIMITE = 25                  # quantos itens cada resposta leva, para não estourar o contexto de quem perguntou

# os campos que valem para quem está decidindo que canal copiar — o resto da linha do banco só gastaria contexto
# `videos` fica de fora de propósito: na linha do canal ele vem com a lista inteira de vídeos, e 25 canais viravam
# 22 KB de resposta. Quem quer os vídeos de um canal chama o radar_canal, que traz os últimos com a nota de cada um.
CAMPOS_CANAL = ("id", "titulo", "handle", "nicho", "subnicho", "pais", "inscritos", "normal_longos",
                "normal_curtos", "meses_postando", "fase", "raridade", "videos_total", "sem_rosto", "anuncios",
                "velocidade", "salvo", "por_causa_de", "achado")
CAMPOS_VIDEO = ("id", "titulo", "canal", "canal_id", "handle", "nicho", "subnicho", "views", "nota",
                "por_hora", "publicado", "inscritos")

VISOES = ("novo_crescendo", "entraram_hoje", "media_alta", "virou_a_chave", "views_poucos_subs",
          "outliers", "sem_concorrencia")


def _enxugar(valor, campos: tuple[str, ...]):
    """Deixa em cada item só os campos que interessam, e no máximo LIMITE itens."""
    if isinstance(valor, list):
        return [_enxugar(v, campos) for v in valor[:LIMITE]]
    if isinstance(valor, dict):
        magro = {k: v for k, v in valor.items() if k in campos and v not in (None, "")}
        return magro or valor
    return valor


def _so_o_que_tem(d: dict, chaves: tuple[str, ...]) -> dict:
    return {k: d[k] for k in chaves if d.get(k) is not None}


def _canais(d: dict) -> dict:
    return {**_so_o_que_tem(d, ("total", "cortados", "piso", "media_min")),
            "canais": _enxugar(d.get("canais") or [], CAMPOS_CANAL)}


def _videos(d: dict) -> dict:
    return {**_so_o_que_tem(d, ("total", "cortados", "views_min")),
            "videos": _enxugar(d.get("videos") or d.get("titulos") or [], CAMPOS_VIDEO)}


# nome, o que faz, o que recebe, para onde vai e como enxuga a resposta
FERRAMENTAS: list[dict] = [
    {
        "nome": "radar_resumo",
        "desc": "Os números do Radar agora: quantos canais na base, os nichos, os que entraram hoje e o último garimpo. "
                "Comece por aqui quando a pergunta for ampla.",
        "entrada": {},
        "caminho": lambda a: ("/api/resumo", {}),
        "enxugar": lambda d: d,      # já vem pequeno: são as contagens da base, uma linha cada
    },
    {
        "nome": "radar_visoes",
        "desc": "As perguntas prontas da lista de canais (as visões), com o rótulo e a dica de cada uma. "
                "Use para saber que recorte pedir em radar_canais.",
        "entrada": {},
        "caminho": lambda a: ("/api/visoes", {}),
        "enxugar": lambda d: d,
    },
    {
        "nome": "radar_canais",
        "desc": "A lista de canais do Radar, com filtro. Sem nada, traz a lista padrão; "
                f"`visao` aceita: {', '.join(VISOES)}.",
        "entrada": {
            "visao": {"type": "string", "enum": list(VISOES), "description": "uma pergunta pronta"},
            "nicho": {"type": "string", "description": "só este nicho"},
            "pais": {"type": "string", "description": "só este país (sigla de duas letras)"},
            "media_min": {"type": "integer", "description": "views por vídeo, no mínimo"},
            "inscritos_max": {"type": "integer", "description": "inscritos, no máximo"},
            "meses_max": {"type": "integer", "description": "postando há no máximo tantos meses"},
            "ordem": {"type": "string", "description": "alta, pontos, novos, media, inscritos"},
            "tudo": {"type": "boolean", "description": "desliga o corte de qualidade (nichos que pagam pouco)"},
        },
        "caminho": lambda a: ("/api/radar", a),
        "enxugar": _canais,
    },
    {
        "nome": "radar_salvos",
        "desc": "Os canais que a pessoa salvou, a base dela, com os números de cada um.",
        "entrada": {},
        "caminho": lambda a: ("/api/salvos", {}),
        "enxugar": _canais,
    },
    {
        "nome": "radar_acharam",
        "desc": "O que os canais salvos acharam sozinhos: os parecidos que cada um trouxe, já medidos, com o "
                "canal que puxou cada um. É a colheita da semana.",
        "entrada": {},
        "caminho": lambda a: ("/api/achados", {}),
        "enxugar": _canais,
    },
    {
        "nome": "radar_canal",
        "desc": "Um canal por dentro: o normal por vídeo, a fase, o nicho, a raridade, os últimos vídeos com a "
                "nota de cada um, o histórico de inscritos e os canais parecidos. Recebe o id (UC...), que vem "
                "nas outras ferramentas.",
        "entrada": {"canal_id": {"type": "string", "description": "o id do canal, UC..."}},
        "exige": ["canal_id"],
        "caminho": lambda a: (f"/api/perfil/canal/{a.get('canal_id', '')}", {}),
        "enxugar": lambda d: {"canal": _enxugar(d.get("canal") or {}, CAMPOS_CANAL),
                              "ultimos": _enxugar(d.get("ultimos") or [], CAMPOS_VIDEO),
                              "historico": (d.get("historico") or [])[-LIMITE:],
                              "parecidos": _enxugar(d.get("parecidos") or [], CAMPOS_CANAL)},
    },
    {
        "nome": "radar_outliers",
        "desc": "Os vídeos que estouraram: quantas vezes cada um passou do normal do canal dele.",
        "entrada": {"nicho": {"type": "string"}, "nota_min": {"type": "number", "description": "quantas vezes o normal"}},
        "caminho": lambda a: ("/api/outliers", a),
        "enxugar": _videos,
    },
    {
        "nome": "radar_titulos",
        "desc": "Os títulos que mais trazem views na base, para modelar.",
        "entrada": {"nicho": {"type": "string"}},
        "caminho": lambda a: ("/api/titulos", a),
        "enxugar": _videos,
    },
]

POR_NOME = {f["nome"]: f for f in FERRAMENTAS}


def _esquema(f: dict) -> dict:
    return {"type": "object", "properties": f["entrada"], "required": f.get("exige", []),
            "additionalProperties": False}


def catalogo() -> list[dict]:
    """O que o tools/list responde."""
    return [{"name": f["nome"], "description": f["desc"], "inputSchema": _esquema(f)} for f in FERRAMENTAS]


def _query(args: dict) -> dict:
    """Só o que a pessoa mandou, como texto, do jeito que a API espera (booleano vira 1)."""
    saida = {}
    for k, v in (args or {}).items():
        if v is None or v == "" or k == "canal_id":
            continue
        saida[k] = "1" if v is True else ("" if v is False else str(v))
    return saida


def _porque(erro: Exception) -> str:
    """O erro em português, com a saída — o mesmo espírito do `porque` do painel."""
    import httpx
    if isinstance(erro, httpx.HTTPStatusError):
        codigo = erro.response.status_code
        detalhe = ""
        try:
            detalhe = erro.response.json().get("detail", "")
        except Exception:
            pass
        if codigo == 401:
            return f"Entre na sua conta no {NOME} ({BASE}) e tente de novo."
        if codigo == 402:
            return detalhe or "Isso é de um plano acima."
        if codigo == 404:
            return detalhe or "O Radar ainda não tem esse item."
        return f"O {NOME} respondeu {codigo}. {detalhe}".strip()
    if isinstance(erro, (httpx.ConnectError, httpx.ConnectTimeout)):
        return (f"O {NOME} não respondeu em {BASE}. Ligue ele (dois cliques em LIGAR-RADAR.bat, "
                "ou `uv run python -m radar servidor`) e tente de novo.")
    return f"Não deu para falar com o {NOME}: {erro}"


def chamar(nome: str, args: dict) -> tuple[str, bool]:
    """Roda uma ferramenta. Devolve o texto da resposta e se foi erro."""
    import httpx
    f = POR_NOME.get(nome)
    if not f:
        return f"Não existe a ferramenta {nome}.", True
    for obrigatorio in f.get("exige", []):
        if not (args or {}).get(obrigatorio):
            return f"Falta {obrigatorio}.", True
    caminho, cru = f["caminho"](args or {})
    cabecalhos = {}
    if os.environ.get("RADAR_MCP_COOKIE"):
        cabecalhos["Cookie"] = os.environ["RADAR_MCP_COOKIE"]
    try:
        r = httpx.get(BASE + caminho, params=_query(cru), headers=cabecalhos, timeout=30)
        r.raise_for_status()
        magro = f["enxugar"](r.json())
    except Exception as e:  # a resposta de erro é para quem perguntou ler, não para derrubar o servidor
        return _porque(e), True
    return json.dumps(magro, ensure_ascii=False), False


def responder(pedido: dict) -> dict | None:
    """Uma mensagem JSON-RPC entra, a resposta sai (ou None, quando é aviso e não pergunta)."""
    metodo, pid = pedido.get("method"), pedido.get("id")

    def ok(resultado):
        return {"jsonrpc": "2.0", "id": pid, "result": resultado}

    if metodo == "initialize":
        return ok({"protocolVersion": PROTOCOLO, "capabilities": {"tools": {}},
                   "serverInfo": {"name": NOME, "version": VERSAO}})
    if metodo in ("notifications/initialized", "notifications/cancelled"):
        return None
    if metodo == "ping":
        return ok({})
    if metodo == "tools/list":
        return ok({"tools": catalogo()})
    if metodo == "tools/call":
        p = pedido.get("params") or {}
        texto, erro = chamar(p.get("name", ""), p.get("arguments") or {})
        return ok({"content": [{"type": "text", "text": texto}], "isError": erro})
    if pid is None:
        return None
    return {"jsonrpc": "2.0", "id": pid, "error": {"code": -32601, "message": f"Método {metodo} não existe aqui."}}


def rodar(entrada=None, saida=None) -> None:
    """O laço do stdio: uma linha de JSON por mensagem, até a entrada fechar."""
    entrada = entrada or sys.stdin
    saida = saida or sys.stdout
    # no Windows a saída do console sai na página de código do DOS: "história" chegava quebrado no Claude. O MCP
    # fala UTF-8, então a entrada e a saída são reajustadas aqui (no teste são StringIO, que não tem reconfigure).
    for fluxo in (entrada, saida):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    for linha in entrada:
        linha = linha.strip()
        if not linha:
            continue
        try:
            pedido = json.loads(linha)
        except json.JSONDecodeError:
            continue                      # lixo na entrada não derruba o servidor
        resposta = responder(pedido)
        if resposta is not None:
            saida.write(json.dumps(resposta, ensure_ascii=False) + "\n")
            saida.flush()
