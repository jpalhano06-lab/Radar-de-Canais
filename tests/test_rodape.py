"""O rodapé da descrição: ele mora no perfil da fábrica, e é a fábrica que escreve a descrição (sem rede)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from radar import producao, publicar  # noqa: E402

PERFIL = """# Canal criado no editor.
base: documentario.yaml
nome: UK MARKET
voz:
  provedor: genaipro
  voice_id: abc123
  idioma_da_voz: en
"""


@pytest.fixture
def fabrica(tmp_path, monkeypatch):
    (tmp_path / "perfis").mkdir()
    (tmp_path / "perfis" / "canal-teste.yaml").write_text(PERFIL, encoding="utf-8")
    monkeypatch.setattr(producao.roteiro_claude, "FABRICA", tmp_path)
    return tmp_path / "perfis" / "canal-teste.yaml"


def test_canal_sem_rodape_devolve_vazio(fabrica):
    assert producao.rodape_do_perfil("canal-teste") == ""


def test_escreve_e_le_de_volta(fabrica):
    texto = "Sobre o canal\n\nAviso:\n\nEste canal é informativo."
    assert producao.salvar_rodape("canal-teste", texto) == texto
    assert producao.rodape_do_perfil("canal-teste") == texto


def test_o_resto_do_perfil_fica_intacto(fabrica):
    """A voz e o nome do canal estão no mesmo arquivo: salvar o rodapé não pode levar a voz junto."""
    producao.salvar_rodape("canal-teste", "Um rodapé qualquer.")
    texto = fabrica.read_text(encoding="utf-8")
    for pedaco in ("base: documentario.yaml", "nome: UK MARKET", "voice_id: abc123", "idioma_da_voz: en"):
        assert pedaco in texto, pedaco


def test_salvar_de_novo_troca_e_nao_empilha(fabrica):
    producao.salvar_rodape("canal-teste", "Primeiro.")
    producao.salvar_rodape("canal-teste", "Segundo.")
    texto = fabrica.read_text(encoding="utf-8")
    assert texto.count("publicacao:") == 1 and "Primeiro." not in texto
    assert producao.rodape_do_perfil("canal-teste") == "Segundo."


def test_rodape_vazio_tira_o_bloco(fabrica):
    producao.salvar_rodape("canal-teste", "Alguma coisa.")
    assert producao.salvar_rodape("canal-teste", "") == ""
    assert "publicacao:" not in fabrica.read_text(encoding="utf-8")


def test_rodape_gigante_e_cortado(fabrica):
    producao.salvar_rodape("canal-teste", "x" * 9000)
    assert len(producao.rodape_do_perfil("canal-teste")) == producao.RODAPE_MAXIMO


def test_perfil_que_nao_existe_nao_cria_arquivo(fabrica, tmp_path):
    with pytest.raises(ValueError):
        producao.salvar_rodape("canal-inventado", "x")
    with pytest.raises(ValueError):          # nome com caminho não escapa da pasta de perfis
        producao.salvar_rodape("../../fora", "x")
    assert sorted(p.name for p in (tmp_path / "perfis").iterdir()) == ["canal-teste.yaml"]


def test_o_rodape_padrao_nao_leva_o_que_e_do_video():
    """O resumo e as hashtags são da fábrica: se viessem no rodapé, sairiam duas vezes na descrição."""
    r = publicar.rodape_padrao("inglês", "consumo", "UK MARKET", "Tesco, Aldi")
    assert "{" not in r and "#" not in r
    assert r.startswith("UK MARKET breaks down") and "Tesco, Aldi" in r
    assert "Disclaimer:" in r


def test_o_rodape_padrao_existe_em_toda_lingua_e_tipo():
    for lingua in publicar.MODELOS:
        for tipo in publicar.TIPOS:
            r = publicar.rodape_padrao(lingua, tipo, "Canal X", "Loja Y")
            assert r and "{" not in r, (lingua, tipo)
            assert len(r) <= producao.RODAPE_MAXIMO, (lingua, tipo)
