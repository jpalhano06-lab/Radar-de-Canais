"""De que canal é o perfil da fábrica: é por aí que a extensão acha o modelo da descrição (sem rede)."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from radar import banco, producao  # noqa: E402


@pytest.fixture
def banco_limpo(monkeypatch):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(banco.ESQUEMA)
    banco._migrar(con)        # as colunas que o Radar foi acrescentando depois (subnicho, pasta, painel...)
    monkeypatch.setattr(banco, "_CON", con)
    return con


def _meu_canal(canal_id, titulo, perfil=""):
    banco.executar("INSERT INTO canais (id, titulo) VALUES (?,?)", canal_id, titulo)
    banco.executar("INSERT INTO meus_canais (usuario_id, canal_id, criado) VALUES (?,?,?)", 1, canal_id, banco.agora())
    if perfil:
        banco.executar("INSERT OR REPLACE INTO canais_config (usuario_id, canal_id, dados, criado) VALUES (?,?,?,?)",
                       1, canal_id, json.dumps({"perfil": perfil}), banco.agora())


def test_acha_pelo_perfil_salvo_na_configuracao(banco_limpo):
    _meu_canal("UC1", "UK MARKET", "canal-uk-market")
    assert producao.canal_do_perfil(1, "canal-uk-market") == ("UC1", "UK MARKET")


def test_perfil_de_ninguem_nao_vira_canal_de_outro(banco_limpo):
    _meu_canal("UC1", "UK MARKET", "canal-uk-market")
    assert producao.canal_do_perfil(1, "canal-que-nao-existe") == ("", "")
    assert producao.canal_do_perfil(1, "") == ("", "")


def test_canal_que_saiu_de_meus_canais_nao_volta_pelo_perfil(banco_limpo):
    """A configuração de um canal apagado fica para trás na tabela. Se o perfil a achasse, a fábrica publicaria
    com o modelo e as marcas de um canal que não existe mais — e, pior, se o perfil fosse reaproveitado num canal
    novo, o novo nasceria com os ajustes do antigo sem ninguém ter pedido."""
    banco.executar("INSERT INTO canais (id, titulo) VALUES (?,?)", "UC9", "Apagado")
    banco.executar("INSERT OR REPLACE INTO canais_config (usuario_id, canal_id, dados, criado) VALUES (?,?,?,?)",
                   1, "UC9", json.dumps({"perfil": "canal-apagado", "marcas": "Loja X"}), banco.agora())
    assert producao.canal_do_perfil(1, "canal-apagado") == ("", "")


def test_a_configuracao_de_outra_conta_nao_vale(banco_limpo):
    """O nome do perfil é o mesmo para todo mundo: a busca é sempre dentro da conta de quem pergunta."""
    banco.executar("INSERT INTO canais (id, titulo) VALUES (?,?)", "UC4", "De outro")
    banco.executar("INSERT INTO meus_canais (usuario_id, canal_id, criado) VALUES (?,?,?)", 2, "UC4", banco.agora())
    banco.executar("INSERT OR REPLACE INTO canais_config (usuario_id, canal_id, dados, criado) VALUES (?,?,?,?)",
                   2, "UC4", json.dumps({"perfil": "canal-uk-market"}), banco.agora())
    assert producao.canal_do_perfil(1, "canal-uk-market") == ("", "")


# ---------------------------------------------------------------- o padrão de publicação do canal (2026-10-23)

def test_o_padrao_de_publicacao_vem_preenchido(banco_limpo):
    """A extensão lê isto para não perguntar nada no Studio: sem valor, ela não saberia o que fazer."""
    _meu_canal("UC1", "João o Lobo", "canal-joao-o-lobo")
    cfg = producao.config(1, "UC1")
    assert cfg["anuncio_cada"] == 1
    assert cfg["tela_final"] == "melhor" and cfg["tela_final"] in producao.TELAS_FINAIS


def test_minuto_de_anuncio_fora_do_pe_volta_para_dentro(banco_limpo):
    _meu_canal("UC1", "João o Lobo", "canal-joao-o-lobo")
    assert producao.salvar(1, "UC1", {"anuncio_cada": 0})["anuncio_cada"] == 1
    assert producao.salvar(1, "UC1", {"anuncio_cada": 999})["anuncio_cada"] == 60
    assert producao.salvar(1, "UC1", {"anuncio_cada": 3})["anuncio_cada"] == 3


def test_tela_final_que_nao_existe_volta_para_a_padrao(banco_limpo):
    """O nome vai direto para a extensão decidir o que fazer: um valor inventado a deixaria sem saída."""
    _meu_canal("UC1", "João o Lobo", "canal-joao-o-lobo")
    assert producao.salvar(1, "UC1", {"tela_final": "inventada"})["tela_final"] == "melhor"
    assert producao.salvar(1, "UC1", {"tela_final": "nenhuma"})["tela_final"] == "nenhuma"
