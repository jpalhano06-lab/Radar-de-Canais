"""A cota do YouTube por motivo: cada pedido entra na conta de quem mandou pedir (sem rede)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3  # noqa: E402

import pytest  # noqa: E402

from radar import banco, youtube  # noqa: E402


@pytest.fixture
def banco_limpo(monkeypatch):
    """Um banco só desta prova, na memória: a conta da cota de verdade não pode ser mexida por teste."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(banco.ESQUEMA)
    banco._migrar(con)        # as colunas que o Radar foi acrescentando depois (subnicho, pasta, painel...)
    monkeypatch.setattr(banco, "_CON", con)
    return con


def test_o_motivo_de_fora_manda(banco_limpo):
    """O garimpo que chama o medir continua sendo garimpo: senão a conta diria "medir" para quase tudo."""
    with youtube.gastando("garimpo"):
        with youtube.gastando("medir"):
            assert youtube._MOTIVO.get() == "garimpo"
    assert youtube._MOTIVO.get() == "outros"


def test_motivo_que_nao_existe_cai_em_outros(banco_limpo):
    with youtube.gastando("inventado"):
        assert youtube._MOTIVO.get() == "outros"


def test_cada_pedido_e_somado_no_motivo(banco_limpo):
    with youtube.gastando("procura"):
        youtube._somar("chave-de-teste", 100)
        youtube._somar("chave-de-teste", 100)
    with youtube.gastando("medir"):
        youtube._somar("chave-de-teste", 3)
    gasto = {m["motivo"]: m for m in youtube.gasto_por_motivo()}
    assert gasto["procura"]["unidades"] == 200 and gasto["procura"]["chamadas"] == 2
    assert gasto["medir"]["unidades"] == 3
    # do maior para o menor: a tela mostra em cima onde a cota foi
    assert [m["motivo"] for m in youtube.gasto_por_motivo()] == ["procura", "medir"]


def test_sem_pedido_nenhum_a_lista_vem_vazia(banco_limpo):
    assert youtube.gasto_por_motivo() == []


def test_a_chave_que_so_foi_marcada_como_esgotada_nao_vira_gasto(banco_limpo):
    """`_somar(chave, 0, esgotada=True)` só marca a chave: não é pedido, não entra em motivo nenhum."""
    with youtube.gastando("garimpo"):
        youtube._somar("chave-de-teste", 0, esgotada=True)
    assert youtube.gasto_por_motivo() == []


def test_todo_motivo_tem_nome_em_portugues():
    """A tela mostra o rótulo, não a chave: um motivo sem nome apareceria como "paises" para quem usa."""
    for chave, rotulo in youtube.MOTIVOS.items():
        assert rotulo and rotulo != chave, chave
