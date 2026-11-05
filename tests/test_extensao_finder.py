"""O que veio do Dotti Finder para a extensão: o que o servidor entrega para cada função nova."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, cracha, garimpo, medir, pagina  # noqa: E402


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


def test_leituras_de_semanas_atras_nao_sao_a_velocidade_de_agora(base):
    _leitura("v4", 500, 1000)
    _leitura("v4", 1, 9000)
    assert medir.velocidades(["v4"]) == {}


def test_sem_nenhum_video_nao_pergunta_ao_banco(base):
    assert medir.velocidades([]) == {}


def test_painel_diz_se_o_video_esta_na_fila(base):
    banco.executar("INSERT INTO modelar (usuario_id, video_id, estado, quando) VALUES (?,?,?,?)", 1, "abcdefghijk", "fila", banco.agora())
    assert pagina.painel("abcdefghijk", "", 1)["modelar"] == "fila"
    assert pagina.painel("abcdefghijk", "", 2)["modelar"] == ""


AGORA = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)


def _video(dias, views, duracao=600, nota=None):
    return {"views": views, "publicado": (AGORA - timedelta(days=dias)).isoformat(), "duracao_s": duracao, "nota": nota}


def _canal(dias_de_vida):
    return {"primeiro_video": (AGORA - timedelta(days=dias_de_vida)).isoformat(), "criado_em": ""}


def test_sem_video_suficiente_nao_julga():
    x = cracha.julgar(_canal(500), [_video(1, 100), _video(2, 100)], AGORA)
    assert x["tipo"] == "sem_dados" and "2 vídeo" in x["motivos"][0]["texto"]


def test_short_nao_conta_como_video():
    x = cracha.julgar(_canal(500), [_video(i, 9_000_000, duracao=40) for i in range(1, 9)], AGORA)
    assert x["tipo"] == "sem_dados"


def test_canal_novo_com_volume_e_explosao():
    x = cracha.julgar(_canal(40), [_video(d, 300_000) for d in (2, 6, 10, 14)], AGORA)
    assert x["tipo"] == "novo_explodindo" and x["saude"] == "alta"
    assert any("40 dias de vida" in m["texto"] for m in x["motivos"])


def test_canal_antigo_com_volume_e_alta():
    assert cracha.julgar(_canal(900), [_video(d, 300_000) for d in (2, 6, 10, 14)], AGORA)["tipo"] == "alta"


def test_silencio_vale_mais_que_o_volume_e_respeita_o_ritmo_do_canal():
    """Quem posta toda semana e sumiu há 60 dias parou; quem posta por mês e sumiu há 60 dias, não."""
    semanal = cracha.julgar(_canal(900), [_video(60 + 7 * i, 50_000) for i in range(8)], AGORA)
    mensal = cracha.julgar(_canal(900), [_video(60 + 30 * i, 50_000) for i in range(8)], AGORA)
    assert semanal["tipo"] == "queda" and semanal["ritmo_dias"] == 7 and "parou de postar há 60 dias" in semanal["motivos"][0]["texto"]
    assert mensal["tipo"] != "queda" and mensal["ritmo_dias"] == 30


def test_video_de_menos_de_7_dias_nao_derruba_o_momento():
    """Vídeo recém-saído tem poucas views por ser novo, não por o canal cair."""
    videos = [_video(1, 10), _video(2, 10), _video(3, 10)] + [_video(10 + 4 * i, 40_000) for i in range(10)]
    assert cracha.julgar(_canal(900), videos, AGORA)["queda"] == 1.0


def test_videos_novos_bem_abaixo_dos_anteriores_e_queda():
    videos = [_video(10 + 4 * i, 5_000) for i in range(5)] + [_video(30 + 4 * i, 40_000) for i in range(5)]
    x = cracha.julgar(_canal(900), videos, AGORA)
    assert x["tipo"] == "queda" and x["queda"] == 0.12


def test_um_acerto_no_meio_de_videos_fracos_e_fonte_de_titulos():
    videos = [_video(5 + 5 * i, 2_000) for i in range(9)] + [_video(60, 900_000)]
    assert cracha.julgar(_canal(900), videos, AGORA)["tipo"] == "fonte"


def test_video_grande_na_media_do_canal_nao_e_acerto():
    """O típico já faz 175 mil: um de 144 mil não é acerto nenhum, mesmo com o campeão lá em cima."""
    videos = [_video(16, 144_000)] + [_video(200 + 5 * i, 175_000) for i in range(8)] + [_video(400, 2_000_000)]
    assert cracha.julgar(_canal(900), videos, AGORA)["tipo"] != "fonte"


def test_o_motivo_tem_milhar_com_ponto_e_a_frase_fica_inteira():
    videos = [_video(5 + 5 * i, 2_000) for i in range(9)] + [_video(60, 900_000)]
    motivo = next(m["texto"] for m in cracha.julgar(_canal(900), videos, AGORA)["motivos"] if m["voto"] == "fonte")
    assert motivo == "o vídeo típico faz 2.000 views, mas um acertou 900.000 há 60 dias"


def test_canal_sem_sinal_nenhum_e_fraco_e_diz_o_motivo():
    x = cracha.julgar(_canal(900), [_video(5 + 5 * i, 900) for i in range(10)], AGORA)
    assert x["tipo"] == "fraco" and x["motivos"]


def _salvo_com_outlier(nota, achado):
    banco.executar("INSERT INTO canais (id, titulo) VALUES ('UC1', 'Canal') ON CONFLICT DO NOTHING")
    banco.executar("INSERT INTO salvos (usuario_id, canal_id, criado) VALUES (1, 'UC1', '') ON CONFLICT DO NOTHING")
    video = f"v{nota}"
    banco.executar("INSERT INTO videos (id, canal_id, titulo, views) VALUES (?, 'UC1', 'Título', 900)", video)
    banco.executar("INSERT INTO outliers (video_id, canal_id, nota, achado) VALUES (?, 'UC1', ?, ?)", video, nota, achado)


def test_aviso_dos_salvos_so_traz_o_que_passou_do_corte_nas_ultimas_24_horas(base):
    agora = datetime.now(timezone.utc)
    _salvo_com_outlier(8, agora.isoformat())
    _salvo_com_outlier(3, agora.isoformat())
    _salvo_com_outlier(9, (agora - timedelta(days=3)).isoformat())
    assert [v["nota"] for v in pagina.salvos_estouraram(1)] == [8]
    assert pagina.salvos_estouraram(2) == []
