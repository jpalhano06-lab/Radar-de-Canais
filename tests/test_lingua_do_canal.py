"""A língua do canal é a da voz dele, e nenhum canal escreve de novo em outra língua sem querer.

Pedido do usuário em 2026-11-17 ("pq os videos que pedi em japones foram feitos em ingles???"): o canal
日本の革新 estava com `lingua: inglês` gravada na configuração, e o pedido copia a língua do canal e manda nela por
cima das instruções do agente — os dois primeiros vídeos saíram com o roteiro em inglês e o título japonês traduzido
para inglês. O perfil da fábrica do canal dizia `idioma_da_voz: ja` o tempo todo.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, fila, producao  # noqa: E402

JAPONES = {"idioma_da_voz": "ja", "voz": "Ren - Calm Business Narrator"}


@pytest.fixture
def canal(monkeypatch, tmp_path):
    """Um canal cujo perfil da fábrica tem a voz em japonês."""
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    monkeypatch.setattr(producao, "_perfil", lambda nome: JAPONES if nome == "canal-nihon" else {})
    producao.salvar(1, "UCja", {"perfil": "canal-nihon", "minutos": 15})
    yield "UCja"
    banco._CON.close()
    banco._CON = None


def test_a_lingua_vem_da_voz_do_perfil(canal):
    assert producao.lingua_da_voz("canal-nihon") == "japonês"
    assert producao.lingua_da_voz("canal-sem-voz") == ""
    assert producao.config(1, canal)["lingua"] == "japonês"


def test_nao_grava_no_canal_uma_lingua_que_a_voz_nao_fala(canal):
    with pytest.raises(ValueError) as erro:
        producao.salvar(1, canal, producao.config(1, canal) | {"lingua": "inglês"})
    assert "japonês" in str(erro.value) and "inglês" in str(erro.value)
    assert producao.config(1, canal)["lingua"] == "japonês"     # continua como estava


def test_a_lingua_da_voz_entra_e_o_perfil_sem_idioma_aceita_qualquer_uma(canal):
    assert producao.salvar(1, canal, producao.config(1, canal) | {"lingua": "japonês"})["lingua"] == "japonês"
    producao.salvar(1, "UCoutro", {"perfil": "canal-sem-voz", "lingua": "inglês"})
    assert producao.config(1, "UCoutro")["lingua"] == "inglês"


def test_o_pedido_de_video_do_canal_nao_sai_em_outra_lingua(canal):
    with pytest.raises(ValueError) as erro:
        fila.criar(1, {"titulo": "日本の新発明", "canal_id": canal, "lingua": "inglês", "caracteres": 12120}, comecar=False)
    assert "japonês" in str(erro.value)
    pedido = fila.criar(1, {"titulo": "日本の新発明", "canal_id": canal, "lingua": "japonês", "caracteres": 12120},
                        comecar=False)
    assert pedido["pedido"]["lingua"] == "japonês"


def test_o_video_de_teste_sem_canal_escolhe_a_lingua_que_quiser(canal):
    """O Canal de teste não é canal nenhum (não tem canal_id): a língua dele é só dos textos na tela."""
    pedido = fila.criar(1, {"titulo": "The Day the Sun Will Die", "lingua": "inglês", "caracteres": 7000,
                            "sem_narracao": True}, comecar=False)
    assert pedido["pedido"]["lingua"] == "inglês"
