"""O menu de cada pessoa, as pastas da base e a esteira de modelagem (sem banco e sem rede)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import servidor  # noqa: E402


def painel_de(d: dict) -> dict:
    return servidor._painel({"painel": json.dumps(d)})


def test_menu_em_branco_nao_esconde_nada():
    assert servidor._painel({}) == {"abas_ordem": [], "abas_ocultas": []}
    assert servidor._painel({"painel": "isto nao e json"}) == {"abas_ordem": [], "abas_ocultas": []}


def test_a_lista_de_canais_nao_pode_ser_escondida():
    """Sem ela não sobra por onde começar: o servidor tira `base` dos ocultos, venha de onde vier."""
    assert painel_de({"abas_ocultas": ["base", "custos"]})["abas_ocultas"] == ["custos"]
    assert "base" in servidor.ABAS_FIXAS


def test_o_menu_guarda_so_nome_de_aba():
    sujo = painel_de({"abas_ordem": ["videos", 123, None, "base"], "abas_ocultas": [{"x": 1}, "custos"]})
    assert sujo == {"abas_ordem": ["videos", "base"], "abas_ocultas": ["custos"]}


def test_o_menu_tem_tamanho_maximo():
    muitas = painel_de({"abas_ordem": [f"aba{i}" for i in range(200)]})
    assert len(muitas["abas_ordem"]) == servidor.PAINEL_MAX


def test_nome_de_aba_nao_cresce_sem_limite():
    comprida = painel_de({"abas_ordem": ["a" * 300]})
    assert comprida["abas_ordem"] == ["a" * 40]


def test_a_esteira_tem_dois_estados():
    assert servidor.ESTEIRA == ("fila", "feito")


def test_as_rotas_novas_existem():
    caminhos = {r.path for r in servidor.app.routes}
    assert {"/api/pastas", "/api/pastas/renomear", "/api/salvos/{canal_id}/pasta",
            "/api/modelar", "/api/modelar/{video_id}", "/api/painel"} <= caminhos


def test_a_pasta_tem_tamanho_maximo():
    assert servidor.PASTA_MAX == 40
