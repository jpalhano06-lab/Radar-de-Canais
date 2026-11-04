"""O japonês não separa palavras com espaço, e o Radar contava palavras por espaço.

Pedido do usuário em 2026-11-04 ("confira por que o Claude não escreve o roteiro para o Japão"): o Claude escrevia, e
o `_limpar` apagava tudo. Cada parágrafo japonês parecia "uma palavra só, sem ponto no fim" (o ponto é 。), a regra de
título tirava a linha, e o roteiro chegava vazio. O tempo sofria do mesmo mal: 4.500 letras contavam como 30 palavras."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import roteiro_claude, tempo  # noqa: E402

PARAGRAFO = "皆さんは、銅がいつか別の素材に置き換わると思いますか。日本の研究チームが新しい素材を発表しました。"
ROTEIRO = "\n\n".join([PARAGRAFO] * 3)


def test_o_limpar_nao_apaga_o_japones():
    assert roteiro_claude._limpar(ROTEIRO) == ROTEIRO


def test_o_limpar_ainda_tira_o_titulo_japones_e_o_portugues():
    assert roteiro_claude._limpar(f"日本の未来\n\n{PARAGRAFO}") == PARAGRAFO
    assert roteiro_claude._limpar("A fuga\n\nEla correu até a porta.") == "Ela correu até a porta."


def test_cada_pontuacao_do_fim_de_frase_segura_a_linha():
    for fim in ("。", "！", "？", "」", "』", "）"):
        assert roteiro_claude._limpar("短い文" + fim) == "短い文" + fim


def test_a_conta_de_palavras_de_duas_letras_por_palavra():
    assert roteiro_claude.contar_palavras("日本語" * 100) == 150
    assert roteiro_claude.contar_palavras("uma frase comum aqui.") == 4
    assert roteiro_claude.contar_palavras("한국의 기술이 세계를") == 3
    assert roteiro_claude.contar_palavras("日本のAI技術。") == 3        # 5 letras viram 2, mais o AI


def test_quinze_minutos_em_japones_sao_4500_letras_e_o_pedido_diz_letras():
    assert roteiro_claude.contar_palavras("あ" * 4500) == 2250
    assert tempo.conferir(roteiro_claude.contar_palavras("あ" * 4500), 15, 150)["dentro"]
    assert roteiro_claude._tamanho(2250, "japonês") == "4500 caracteres"
    assert roteiro_claude._tamanho(2250, "coreano") == "2250 palavras"
    assert roteiro_claude._tamanho(2250, "") == "2250 palavras"


def test_o_roteiro_japones_pronto_nao_ganha_volta_de_tamanho(monkeypatch):
    def nao_chamar(*_a, **_k):
        raise AssertionError("o roteiro já estava no tempo")
    monkeypatch.setattr(roteiro_claude, "_claude", nao_chamar)
    texto = "\n\n".join(["あ" * 150 + "。"] * 30)
    roteiro, conf = roteiro_claude._conferir_tamanho(texto, "s", "p", 15, {"ppm": 150, "de": "padrao"})
    assert roteiro == texto and conf["dentro"] and conf["voltas"] == []


def test_o_portao_barra_o_portugues_que_cita_o_titulo_japones():
    """O caso real: as perguntas em português citavam o título, e duas letras japonesas não fazem um roteiro japonês."""
    texto = "日本の新発明 é o título que veio. " + "Uma frase em português para o roteiro. " * 200
    motivo = roteiro_claude.conferir_roteiro(texto, {"minutos": 15, "lingua": "japonês", "ritmo": {"ppm": 150}})
    assert "não está escrito em japonês" in motivo


def test_o_roteiro_colado_em_japones_entra():
    assert roteiro_claude.contar_palavras("あ" * 100) >= 30


def test_o_video_de_perguntas_nao_ensina_o_ritmo_da_voz(monkeypatch, tmp_path):
    """Os dois vídeos do cobre narraram perguntas em português e o ritmo do canal japonês saiu deles (116 por minuto)."""
    monkeypatch.setattr(roteiro_claude, "PASTA", tmp_path)
    monkeypatch.setattr(tempo, "_da_api", lambda: {})
    for nome, texto in (("errado", "Preciso que você me diga algumas coisas. " * 40), ("certo", "あ" * 900)):
        pasta = tmp_path / nome
        pasta.mkdir()
        (pasta / "roteiro.txt").write_text(texto, encoding="utf-8")
        (pasta / "roteiro.json").write_text(json.dumps({
            "usuario_id": 1, "lingua": "japonês", "minutos": 3, "titulo": nome,
            "fabrica": {"perfil": "p", "palavras": roteiro_claude.contar_palavras(texto)},
            "medido": {"segundos": 180}}), encoding="utf-8")
    assert [m["titulo"] for m in tempo.medicoes(1)] == ["certo"]
