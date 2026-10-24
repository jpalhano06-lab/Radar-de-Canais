"""O MCP do Radar: o catálogo, o JSON-RPC, a tradução dos pedidos e os erros em português (sem rede)."""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from radar import mcp  # noqa: E402
from radar.config import NOME  # noqa: E402


class Resposta:
    """O que o httpx devolveria, sem rede."""

    def __init__(self, dados, codigo=200):
        self._dados, self.status_code = dados, codigo

    def json(self):
        return self._dados

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("ruim", request=None, response=self)


def fingir(monkeypatch, dados, codigo=200):
    """Troca o httpx.get e guarda o que o MCP pediu."""
    pedidos = []

    def get(url, params=None, headers=None, timeout=None):
        pedidos.append({"url": url, "params": params or {}, "headers": headers or {}})
        return Resposta(dados, codigo)

    monkeypatch.setattr(httpx, "get", get)
    return pedidos


# ---------------------------------------------------------------- o catálogo

def test_o_catalogo_esta_no_formato_que_o_claude_le():
    for f in mcp.catalogo():
        assert f["name"].startswith("radar_"), f["name"]
        assert f["description"].endswith("."), f["name"]
        e = f["inputSchema"]
        assert e["type"] == "object" and e["additionalProperties"] is False
        assert set(e["required"]) <= set(e["properties"]), f["name"]
        for campo, regra in e["properties"].items():
            assert regra.get("type"), f'{f["name"]}.{campo}'


def test_o_nome_de_cada_ferramenta_nao_repete():
    nomes = [f["nome"] for f in mcp.FERRAMENTAS]
    assert len(nomes) == len(set(nomes))
    assert "radar_resumo" in nomes and "radar_canais" in nomes


def test_nenhuma_ferramenta_escreve():
    """O MCP é só de leitura: nada aqui pode gastar cota do YouTube nem gravar na base."""
    for f in mcp.FERRAMENTAS:
        caminho, _ = f["caminho"]({"canal_id": "UC1"})
        assert caminho.startswith("/api/"), caminho
        assert not any(p in caminho for p in ("adicionar", "garimpar", "medir", "salvar")), caminho


# ---------------------------------------------------------------- o JSON-RPC

def pedir(metodo, params=None, pid=1):
    return mcp.responder({"jsonrpc": "2.0", "id": pid, "method": metodo, "params": params or {}})


def test_o_aperto_de_mao():
    r = pedir("initialize")
    assert r["result"]["protocolVersion"] == mcp.PROTOCOLO
    assert r["result"]["serverInfo"]["name"] == NOME
    assert "tools" in r["result"]["capabilities"]


def test_aviso_nao_tem_resposta():
    assert mcp.responder({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list_devolve_todas():
    r = pedir("tools/list")
    assert len(r["result"]["tools"]) == len(mcp.FERRAMENTAS)


def test_metodo_que_nao_existe_volta_erro_de_jsonrpc():
    r = pedir("coisa/estranha")
    assert r["error"]["code"] == -32601


def test_ferramenta_que_nao_existe_volta_erro_da_ferramenta():
    r = pedir("tools/call", {"name": "radar_inventado", "arguments": {}})
    assert r["result"]["isError"] is True
    assert "radar_inventado" in r["result"]["content"][0]["text"]


def test_o_que_falta_e_dito_antes_de_sair_pedindo():
    texto, erro = mcp.chamar("radar_canal", {})
    assert erro is True and texto == "Falta canal_id."


# ---------------------------------------------------------------- o pedido que sai

def test_a_base_e_a_colheita_usam_as_rotas_do_plano_lite(monkeypatch):
    """`/api/radar?salvos=1` daria 402 para quem é Lite: a base da pessoa tem rota própria, com o gate certo."""
    pedidos = fingir(monkeypatch, {"canais": [{"id": "UC1", "titulo": "um"}]})
    texto, erro = mcp.chamar("radar_salvos", {})
    assert erro is False and pedidos[0]["url"].endswith("/api/salvos")
    assert json.loads(texto)["canais"] == [{"id": "UC1", "titulo": "um"}]

    pedidos = fingir(monkeypatch, {"canais": [{"id": "UC2", "titulo": "dois", "por_causa_de": "um"}]})
    mcp.chamar("radar_acharam", {})
    assert pedidos[0]["url"].endswith("/api/achados")


def test_booleano_vira_1_e_o_id_nao_vaza_para_a_query(monkeypatch):
    pedidos = fingir(monkeypatch, {"canais": []})
    mcp.chamar("radar_canais", {"tudo": True, "nicho": "história", "media_min": 50000})
    assert pedidos[0]["params"] == {"tudo": "1", "nicho": "história", "media_min": "50000"}

    pedidos = fingir(monkeypatch, {"titulo": "um canal"})
    mcp.chamar("radar_canal", {"canal_id": "UC123"})
    assert pedidos[0]["url"].endswith("/api/perfil/canal/UC123")
    assert pedidos[0]["params"] == {}


def test_o_cookie_vai_quando_o_radar_esta_com_senha(monkeypatch):
    monkeypatch.setenv("RADAR_MCP_COOKIE", "sessao=abc")
    pedidos = fingir(monkeypatch, {"canais": []})
    mcp.chamar("radar_canais", {})
    assert pedidos[0]["headers"]["Cookie"] == "sessao=abc"


# ---------------------------------------------------------------- a resposta que volta

def test_a_resposta_leva_so_os_campos_que_interessam_e_cabe_no_contexto(monkeypatch):
    canais = [{"id": f"UC{i}", "titulo": f"canal {i}", "nicho": "história", "inscritos": 1000 + i,
               "normal_longos": 50000, "fase": "crescendo", "foto": "https://…", "descoberto": "2026-10-01",
               "velocidade": 1.2, "bloqueado": 0} for i in range(60)]
    fingir(monkeypatch, {"total": 60, "canais": canais})
    d = json.loads(mcp.chamar("radar_canais", {})[0])
    assert d["total"] == 60, "o total da base continua aparecendo"
    assert len(d["canais"]) == mcp.LIMITE, "a lista vem cortada, para não estourar o contexto"
    assert set(d["canais"][0]) <= set(mcp.CAMPOS_CANAL)
    assert "foto" not in d["canais"][0] and "descoberto" not in d["canais"][0]


def test_a_lista_de_videos_do_canal_nao_vem_na_lista_de_canais(monkeypatch):
    """A linha do canal traz todos os vídeos dele: 25 canais viravam 22 KB de resposta."""
    canal = {"id": "UC1", "titulo": "um", "videos_total": 40,
             "videos": [{"id": f"v{i}", "titulo": "x" * 60, "views": 10} for i in range(40)]}
    fingir(monkeypatch, {"canais": [canal]})
    texto = mcp.chamar("radar_canais", {})[0]
    c = json.loads(texto)["canais"][0]
    assert "videos" not in c and c["videos_total"] == 40
    assert len(texto) < 300, "a resposta tem de caber no contexto de quem perguntou"


def test_campo_vazio_nao_ocupa_lugar(monkeypatch):
    fingir(monkeypatch, {"canais": [{"id": "UC1", "titulo": "um", "nicho": "", "raridade": None}]})
    c = json.loads(mcp.chamar("radar_canais", {})[0])["canais"][0]
    assert c == {"id": "UC1", "titulo": "um"}


# ---------------------------------------------------------------- os erros, em português

def test_radar_desligado_diz_como_ligar(monkeypatch):
    def get(*a, **k):
        raise httpx.ConnectError("recusado")

    monkeypatch.setattr(httpx, "get", get)
    texto, erro = mcp.chamar("radar_resumo", {})
    assert erro is True
    assert "LIGAR-RADAR.bat" in texto and mcp.BASE in texto


def test_plano_de_cima_repete_o_que_o_servidor_disse(monkeypatch):
    fingir(monkeypatch, {"detail": "Isso é do plano Pro."}, codigo=402)
    texto, erro = mcp.chamar("radar_canais", {})
    assert erro is True and texto == "Isso é do plano Pro."


def test_sem_conta_manda_entrar(monkeypatch):
    fingir(monkeypatch, {"detail": "Entre na sua conta."}, codigo=401)
    texto, erro = mcp.chamar("radar_canais", {})
    assert erro is True and "Entre na sua conta" in texto


# ---------------------------------------------------------------- o laço do stdio

def test_o_laco_responde_linha_por_linha_e_ignora_lixo():
    entrada = io.StringIO(
        '{"jsonrpc":"2.0","id":1,"method":"initialize"}\n'
        "\n"
        "isso aqui não é json\n"
        '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n')
    saida = io.StringIO()
    mcp.rodar(entrada, saida)
    linhas = [json.loads(l) for l in saida.getvalue().splitlines()]
    assert [r["id"] for r in linhas] == [1, 2], "o aviso e o lixo não geram resposta"
    assert linhas[1]["result"]["tools"][0]["name"].startswith("radar_")
