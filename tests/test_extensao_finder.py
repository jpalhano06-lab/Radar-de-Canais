"""O que veio do Dotti Finder para a extensão: o que o servidor entrega para cada função nova."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, garimpo, medir, pagina  # noqa: E402


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "radar.db")
    monkeypatch.setattr(banco, "_CON", None)
    return banco


def _leitura(video, horas_atras, views):
    quando = (datetime.now(timezone.utc) - timedelta(hours=horas_atras)).isoformat()
    banco.executar("INSERT INTO leituras (video_id, quando, views) VALUES (?,?,?)", video, quando, views)


def test_rpm_e_a_faixa_do_nicho_menos_a_parte_do_youtube():
    assert garimpo.rpm("Finanças") == {"nicho": "Finanças", "minimo": 8.25, "maximo": 27.5}
    assert garimpo.rpm("Assunto que não está na lista") is None


def test_velocidade_e_medida_entre_duas_leituras(base):
    _leitura("v1", 3, 1000)
    _leitura("v1", 1, 1500)
    assert medir.velocidades(["v1"])["v1"] == {"vph": 250.0, "horas": 2.0}


def test_duas_leituras_coladas_nao_viram_velocidade(base):
    """Dez minutos entre leituras multiplicaria o arredondamento da página por seis."""
    _leitura("v2", 0.3, 1000)
    _leitura("v2", 0.1, 1100)
    assert medir.velocidades(["v2"]) == {}


def test_views_que_desceram_nao_viram_velocidade_negativa(base):
    _leitura("v3", 5, 2000)
    _leitura("v3", 1, 1900)
    assert medir.velocidades(["v3"])["v3"]["vph"] == 0


def test_sem_nenhum_video_nao_pergunta_ao_banco(base):
    assert medir.velocidades([]) == {}


def test_painel_diz_se_o_video_esta_na_fila(base):
    banco.executar("INSERT INTO modelar (usuario_id, video_id, estado, quando) VALUES (?,?,?,?)", 1, "abcdefghijk", "fila", banco.agora())
    assert pagina.painel("abcdefghijk", "", 1)["modelar"] == "fila"
    assert pagina.painel("abcdefghijk", "", 2)["modelar"] == ""
