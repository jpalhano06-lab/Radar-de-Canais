"""As visões: as perguntas prontas da lista de canais (regra no servidor, sem banco e sem rede)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import servidor  # noqa: E402


def onde_de(q: dict) -> str:
    onde, _ = servidor._filtro_canais(servidor._com_a_visao(q))
    return " AND ".join(onde)


def args_de(q: dict) -> list:
    _, args = servidor._filtro_canais(servidor._com_a_visao(q))
    return args


def test_as_visoes_existem_com_rotulo_dica_e_ordem():
    assert list(servidor.VISOES) == ["novo_crescendo", "entraram_hoje", "media_alta", "virou_a_chave",
                                     "views_poucos_subs", "outliers", "sem_concorrencia"]
    for chave, v in servidor.VISOES.items():
        assert v["rotulo"] and v["dica"], chave
        assert v["ordem"] in servidor.ORDENS, chave
        assert v["filtros"], chave


def test_cada_visao_vira_filtro_de_verdade():
    # nenhuma visão pode cair no "só no_radar=1": isso seria a lista inteira com outro nome
    for chave in servidor.VISOES:
        onde, args = servidor._filtro_canais(servidor._com_a_visao({"visao": chave}))
        assert len(onde) > 1, chave
        assert args or "fase" in " ".join(onde), chave


def test_novo_crescendo_corta_por_idade_e_velocidade():
    onde = onde_de({"visao": "novo_crescendo"})
    assert "c.velocidade >= ?" in onde and "c.primeiro_video >= ?" in onde
    assert 10000 in args_de({"visao": "novo_crescendo"})


def test_virou_a_chave_e_a_fase_crescendo():
    assert "c.fase=?" in onde_de({"visao": "virou_a_chave"})
    assert "crescendo" in args_de({"visao": "virou_a_chave"})


def test_views_poucos_subs_compara_views_com_inscritos():
    assert "c.base_longos * 1.0 / MAX(c.inscritos, 100) >= ?" in onde_de({"visao": "views_poucos_subs"})


def test_outliers_pede_video_que_estourou():
    onde = onde_de({"visao": "outliers"})
    assert "SELECT canal_id FROM outliers WHERE nota >= ?" in onde
    assert 10 in args_de({"visao": "outliers"})


def test_sem_concorrencia_olha_o_tamanho_do_subnicho():
    onde = onde_de({"visao": "sem_concorrencia"})
    assert "GROUP BY subnicho HAVING COUNT(*) <= ?" in onde
    assert 2 in args_de({"visao": "sem_concorrencia"})


def test_o_que_a_pessoa_pede_vale_por_cima_da_visao():
    # a visão pede canal de até 6 meses; a pessoa pediu até 1 mês: vale o dela
    q = {"visao": "novo_crescendo", "idade_max": "1"}
    assert servidor._com_a_visao(q)["idade_max"] == "1"
    # e o que ela deixou em branco não apaga o filtro da visão
    assert servidor._com_a_visao({"visao": "novo_crescendo", "idade_max": ""})["idade_max"] == "6"


def test_visao_que_nao_existe_nao_filtra_nada():
    assert onde_de({"visao": "inventada"}) == "c.no_radar=1"
    assert onde_de({}) == "c.no_radar=1"


def test_a_visao_nao_se_mistura_com_o_resto_da_busca():
    onde = onde_de({"visao": "media_alta", "busca": "cobras", "nicho": "Animais"})
    assert "c.nicho=?" in onde and "c.base_longos >= ?" in onde and "c.titulo LIKE ?" in onde


def test_entraram_hoje_e_o_que_o_garimpo_achou_nas_ultimas_24_horas():
    """A aba "Entraram hoje" do menu é esta visão: sem o corte por data ela seria a lista inteira."""
    onde = onde_de({"visao": "entraram_hoje"})
    assert "c.descoberto >= ?" in onde
    assert servidor.VISOES["entraram_hoje"]["ordem"] == "novos"
