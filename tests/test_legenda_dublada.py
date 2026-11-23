"""Vídeo dublado tem uma legenda automática por dublagem: a transcrição é a da língua do áudio original
(2026-11-22: "Salvos Has Been Caught" saía em árabe na extensão e em português no roteiro)."""
from types import SimpleNamespace as T

from radar.roteiro_claude import escolher_legenda


def _faixas(*codigos, gerada=True):
    return [T(language_code=c, is_generated=gerada) for c in codigos]


def test_dublado_usa_a_lingua_do_audio():
    faixas = _faixas("ar", "pt", "en", "es")
    assert escolher_legenda(faixas, "en").language_code == "en"
    assert escolher_legenda(faixas, "en-US").language_code == "en"


def test_sem_saber_a_lingua_nao_prefere_a_dublagem_em_portugues():
    assert escolher_legenda(_faixas("ar", "pt", "en")).language_code == "en"


def test_feita_a_mao_na_lingua_do_audio_vence():
    faixas = _faixas("pt", "es") + _faixas("pt", "es", gerada=False)
    escolhida = escolher_legenda(faixas, "es")
    assert (escolhida.language_code, escolhida.is_generated) == ("es", False)


def test_video_em_portugues():
    assert escolher_legenda(_faixas("en", "pt"), "pt-BR").language_code == "pt"
