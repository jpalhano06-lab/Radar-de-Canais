"""A reação do público: curtidas e comentários por view, medidos contra o normal do nicho (sem rede)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import metricas  # noqa: E402


def test_a_taxa_e_curtidas_mais_comentarios_por_view():
    assert metricas.engajamento(10000, 400, 100) == 0.05


def test_sem_os_numeros_nao_ha_taxa():
    """Não ter curtidas medidas não é o mesmo que o vídeo não ter sido curtido."""
    assert metricas.engajamento(10000, None, 100) is None
    assert metricas.engajamento(10000, 400, None) is None
    assert metricas.engajamento(None, 400, 100) is None
    assert metricas.engajamento(0, 400, 100) is None


def test_zero_curtidas_e_zero_de_verdade():
    assert metricas.engajamento(10000, 0, 0) == 0.0


def test_a_reacao_compara_com_o_nicho():
    # 4,5% num nicho cujo vídeo típico faz 1,5%: reagiu 3 vezes mais
    assert metricas.reacao(0.045, 0.015) == 3.0
    assert metricas.reacao(0.015, 0.015) == 1.0


def test_sem_normal_do_nicho_nao_da_para_comparar():
    assert metricas.reacao(0.045, None) is None
    assert metricas.reacao(0.045, 0) is None
    assert metricas.reacao(None, 0.015) is None


def test_o_mesmo_video_tem_reacoes_diferentes_em_nichos_diferentes():
    """É por isso que o normal é do nicho: Animais vive com 0,8% e Religião com 2,7%."""
    taxa = metricas.engajamento(100000, 2000, 700)      # 2,7%
    assert metricas.reacao(taxa, 0.0079) == 3.4         # muito acima do normal de Animais
    assert metricas.reacao(taxa, 0.0271) == 1.0         # dentro do normal de Religião


def test_o_corte_de_reacao_alta_e_o_dobro_do_normal():
    assert metricas.REACAO_ALTA == 2.0
