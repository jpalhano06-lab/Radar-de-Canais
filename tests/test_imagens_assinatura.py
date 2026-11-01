"""Quem gera as imagens de IA do canal: a assinatura do ChatGPT ou a chave de API (pedido do usuário em 2026-11-01).

A escolha mora no perfil do canal na fábrica (imagens.provedor), porque é a fábrica que gera. Aqui se prova que o
Radar escreve isso sem estragar o resto do arquivo, e que voltar para a chave de API devolve o provedor de antes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from radar import producao  # noqa: E402

SEM_IMAGENS = """# Canal criado no editor.
base: documentario.yaml
nome: UK MARKET
voz:
  provedor: genaipro
  voice_id: abc123
  idioma_da_voz: en

publicacao:
  rodape: |
    O rodapé do canal.
"""

COM_IMAGENS = """base: documentario.yaml
nome: UK MARKET

imagens:
  provedor: kie
  qualidade: high
  estilo: >-
    Cinematic still, photorealistic.
"""


def _perfil(tmp_path, monkeypatch, texto):
    (tmp_path / "perfis").mkdir(exist_ok=True)
    arquivo = tmp_path / "perfis" / "canal-teste.yaml"
    arquivo.write_text(texto, encoding="utf-8")
    monkeypatch.setattr(producao.roteiro_claude, "FABRICA", tmp_path)
    return arquivo


def test_canal_sem_bloco_de_imagens_esta_na_chave_de_api(tmp_path, monkeypatch):
    _perfil(tmp_path, monkeypatch, SEM_IMAGENS)
    assert producao.imagens_do_perfil("canal-teste") == {"quem": "api", "reserva": "openrouter", "provedor": ""}


def test_virar_para_a_assinatura_escreve_o_bloco_e_guarda_a_reserva(tmp_path, monkeypatch):
    arquivo = _perfil(tmp_path, monkeypatch, SEM_IMAGENS)
    assert producao.salvar_imagens_quem("canal-teste", "assinatura")["quem"] == "assinatura"
    texto = arquivo.read_text(encoding="utf-8")
    assert "  provedor: assinatura" in texto
    assert "  provedor_reserva: openrouter" in texto
    assert "rodape: |" in texto and "nome: UK MARKET" in texto     # o resto do perfil fica igual


def test_a_reserva_e_o_provedor_que_estava_valendo(tmp_path, monkeypatch):
    """O canal estava na Kie: ao virar para a assinatura, é a Kie que atende as imagens que faltarem."""
    arquivo = _perfil(tmp_path, monkeypatch, COM_IMAGENS)
    producao.salvar_imagens_quem("canal-teste", "assinatura")
    assert producao.imagens_do_perfil("canal-teste") == {"quem": "assinatura", "reserva": "kie",
                                                         "provedor": "assinatura"}
    assert "qualidade: high" in arquivo.read_text(encoding="utf-8")  # o resto do bloco imagens fica igual


def test_voltar_para_a_chave_devolve_o_provedor_de_antes(tmp_path, monkeypatch):
    arquivo = _perfil(tmp_path, monkeypatch, COM_IMAGENS)
    producao.salvar_imagens_quem("canal-teste", "assinatura")
    assert producao.salvar_imagens_quem("canal-teste", "api") == {"quem": "api", "reserva": "openrouter",
                                                                  "provedor": "kie"}
    texto = arquivo.read_text(encoding="utf-8")
    assert "  provedor: kie" in texto and "provedor_reserva" not in texto


def test_so_aceita_as_duas_escolhas(tmp_path, monkeypatch):
    _perfil(tmp_path, monkeypatch, SEM_IMAGENS)
    with pytest.raises(ValueError):
        producao.salvar_imagens_quem("canal-teste", "openrouter")


def test_canal_sem_perfil_na_fabrica_avisa(tmp_path, monkeypatch):
    _perfil(tmp_path, monkeypatch, SEM_IMAGENS)
    with pytest.raises(ValueError):
        producao.salvar_imagens_quem("canal-que-nao-existe", "assinatura")
