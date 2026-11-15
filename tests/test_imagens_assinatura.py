"""Quem gera as imagens de IA do canal: a assinatura do ChatGPT ou a chave de API (pedido do usuário em 2026-11-01).

A escolha mora no perfil do canal na fábrica (imagens.provedor), porque é a fábrica que gera. Aqui se prova que o
Radar escreve isso sem estragar o resto do arquivo, e que voltar para a chave de API devolve o provedor de antes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from radar import banco, producao  # noqa: E402


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    """A regra Todos pela conexão mora no banco: cada teste com um banco seu, nunca o de verdade."""
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    yield
    if banco._CON:
        banco._CON.close()
    banco._CON = None

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


COM_BLOCO_DEPOIS = """base: documentario.yaml
nome: 한국의 미래

imagens:
  provedor: assinatura
  provedor_reserva: openrouter

# País do público
lugar:
  pais: South Korea
  moeda: "₩ (Korean won)"
"""


def test_trocar_nao_leva_o_provedor_para_o_bloco_de_baixo(tmp_path, monkeypatch):
    """O bug de 2026-11-15: o regex com flag s pegava até o fim do arquivo, e imagens.provedor ia parar em lugar:."""
    arquivo = _perfil(tmp_path, monkeypatch, COM_BLOCO_DEPOIS)
    producao.salvar_imagens_quem("canal-teste", "api")
    texto = arquivo.read_text(encoding="utf-8")
    assert texto.endswith('lugar:\n  pais: South Korea\n  moeda: "₩ (Korean won)"\n')
    assert "imagens:\n  provedor: openrouter\n" in texto
    producao.salvar_imagens_quem("canal-teste", "assinatura")
    assert producao.imagens_do_perfil("canal-teste")["provedor"] == "assinatura"
    assert arquivo.read_text(encoding="utf-8").endswith('lugar:\n  pais: South Korea\n  moeda: "₩ (Korean won)"\n')


def _canais(tmp_path, monkeypatch, **perfis):
    (tmp_path / "perfis").mkdir(exist_ok=True)
    for nome, texto in perfis.items():
        (tmp_path / "perfis" / f"{nome}.yaml").write_text(texto, encoding="utf-8")
    monkeypatch.setattr(producao.roteiro_claude, "FABRICA", tmp_path)
    monkeypatch.setattr(producao.roteiro_claude, "perfis_da_fabrica", lambda: list(perfis))


def test_regra_todos_pela_conexao_devolve_quem_saiu_da_assinatura(tmp_path, monkeypatch):
    """O UK Market voltou para a chave de API por fora (2026-11-15): com a regra ligada, ele volta para a assinatura."""
    _canais(tmp_path, monkeypatch, **{"canal-uk-market": COM_IMAGENS, "canal-joao": COM_BLOCO_DEPOIS,
                                      "documentario": "nome: modelo\n"})
    assert producao.aplicar_regra() == []                 # sem a regra, nada muda
    producao.definir_regra_imagens("assinatura")
    assert producao.aplicar_regra() == ["canal-uk-market"]
    assert producao.imagens_do_perfil("canal-uk-market") == {"quem": "assinatura", "reserva": "kie", "provedor": "assinatura"}
    assert producao.imagens_do_perfil("documentario")["quem"] == "api"   # modelo da fábrica não é canal: fica
    assert producao.aplicar_regra() == []


def test_regra_ligada_recusa_trocar_um_canal_para_a_chave(tmp_path, monkeypatch):
    _canais(tmp_path, monkeypatch, **{"canal-teste": COM_BLOCO_DEPOIS})
    producao.definir_regra_imagens("assinatura")
    with pytest.raises(ValueError, match="Todos pela conexão"):
        producao.salvar_imagens_quem("canal-teste", "api")
    producao.definir_regra_imagens("api")                 # Todos pela chave de API desliga a regra
    assert producao.salvar_imagens_quem("canal-teste", "api")["quem"] == "api"


def test_botoes_todos_ligam_e_desligam_a_regra(tmp_path, monkeypatch):
    import asyncio
    from radar import servidor
    _canais(tmp_path, monkeypatch, **{"canal-teste": COM_BLOCO_DEPOIS})
    asyncio.run(servidor.chatgpt_canais_salvar({"quem": "assinatura"}, u={"id": 1}))
    assert producao.regra_imagens() == "assinatura"
    asyncio.run(servidor.chatgpt_canais_salvar({"quem": "api"}, u={"id": 1}))
    assert producao.regra_imagens() == "" and producao.imagens_do_perfil("canal-teste")["quem"] == "api"


def test_salvar_o_rodape_nao_apaga_o_que_vem_depois(tmp_path, monkeypatch):
    arquivo = _perfil(tmp_path, monkeypatch, SEM_IMAGENS + "\nlugar:\n  pais: Canada\n")
    producao.salvar_rodape("canal-teste", "Rodapé novo.")
    texto = arquivo.read_text(encoding="utf-8")
    assert "lugar:\n  pais: Canada" in texto and "Rodapé novo." in texto and "O rodapé do canal." not in texto


def test_so_aceita_as_duas_escolhas(tmp_path, monkeypatch):
    _perfil(tmp_path, monkeypatch, SEM_IMAGENS)
    with pytest.raises(ValueError):
        producao.salvar_imagens_quem("canal-teste", "openrouter")


def test_canal_sem_perfil_na_fabrica_avisa(tmp_path, monkeypatch):
    _perfil(tmp_path, monkeypatch, SEM_IMAGENS)
    with pytest.raises(ValueError):
        producao.salvar_imagens_quem("canal-que-nao-existe", "assinatura")


def test_integracoes_lista_cada_canal_com_quem_gera(tmp_path, monkeypatch):
    """Integrações troca os canais pela conexão do ChatGPT: a lista traz o nome do canal e a escolha de cada um."""
    _perfil(tmp_path, monkeypatch, SEM_IMAGENS)
    monkeypatch.setattr(producao.roteiro_claude, "perfis_da_fabrica", lambda: ["canal-teste"])
    producao.salvar_imagens_quem("canal-teste", "assinatura")
    assert producao.imagens_dos_perfis() == [{"perfil": "canal-teste", "canal": "UK MARKET", "e_canal": True,
                                              "quem": "assinatura", "reserva": "openrouter", "provedor": "assinatura"}]
