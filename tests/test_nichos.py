"""A curva da vida e a tabela por nicho, sem banco e sem rede."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import nichos  # noqa: E402

HOJE = datetime(2026, 10, 25, tzinfo=timezone.utc)


def _canal(dias_postando, **extra):
    """Um canal que começou a postar há tantos dias."""
    return {"id": extra.pop("id", f"UC{dias_postando}"), "nicho": extra.pop("nicho", "Animais"),
            "primeiro_video": (HOJE - timedelta(days=dias_postando)).isoformat().replace("+00:00", "Z"),
            "base_longos": extra.pop("base_longos", 10000), "fase": extra.pop("fase", "estavel"),
            "views_total": extra.pop("views_total", 1000), **extra}


@pytest.fixture
def sem_banco(monkeypatch):
    """Troca as duas únicas portas de banco do módulo: o resto da conta é pura."""
    def pendurar(canais, do_mes=None):
        monkeypatch.setattr(nichos, "_canais", lambda nicho="", idioma="", piso=0: canais)
        monkeypatch.setattr(nichos, "_views_do_mes", lambda ids: do_mes or {})
    return pendurar


def test_cada_idade_cai_na_etapa_dela():
    def etapa(dias):
        return nichos.etapa_do_canal((HOJE - timedelta(days=dias)).isoformat().replace("+00:00", "Z"), HOJE)
    assert etapa(0) == "testando"
    assert etapa(29.9) == "testando"
    assert etapa(30) == "decolando"          # o fim de uma etapa é o começo da outra, sem buraco
    assert etapa(30.5) == "decolando"        # a idade vem em dias quebrados: este caía fora com 0-30 e 31-90
    assert etapa(89.9) == "decolando"
    assert etapa(90) == "disputando"
    assert etapa(180) == "firme"
    assert etapa(729) == "firme"
    assert etapa(730) == "veterano"
    assert etapa(5000) == "veterano"


def test_canal_sem_data_de_estreia_nao_entra_em_etapa_nenhuma():
    assert nichos.etapa_do_canal("", HOJE) == ""
    assert nichos.etapa_do_canal("sei lá quando", HOJE) == ""


def test_a_faixa_conta_todo_mundo_uma_vez_so(sem_banco):
    sem_banco([_canal(5), _canal(40), _canal(100), _canal(300), _canal(900), dict(_canal(1), primeiro_video="")])
    d = nichos.linha_da_vida()
    assert [e["canais"] for e in d["etapas"]] == [1, 1, 1, 1, 1]
    assert d["canais"] == 6 and d["sem_data"] == 1       # o sem data fica de fora, e a tela diz quantos são
    assert sum(e["canais"] for e in d["etapas"]) + d["sem_data"] == d["canais"]


def test_a_media_do_mes_e_so_de_quem_publicou(sem_banco):
    # três canais na mesma etapa; um não publicou nada no mês
    sem_banco([_canal(5, id="a"), _canal(6, id="b"), _canal(7, id="c")], {"a": 1000, "b": 3000})
    etapa = nichos.linha_da_vida()["etapas"][0]
    assert etapa["canais"] == 3 and etapa["postando"] == 2
    assert etapa["views_mes"] == 2000                     # (1000+3000)/2, e não /3


def test_etapa_sem_ninguem_publicando_nao_divide_por_zero(sem_banco):
    sem_banco([_canal(5)], {})
    assert nichos.linha_da_vida()["etapas"][0]["views_mes"] == 0


def test_o_trafego_tipico_e_a_mediana_e_nao_a_media(sem_banco):
    # quatro canais pequenos e um gigante: a média diria 2 milhões, a mediana diz o que o nicho é
    sem_banco([_canal(100, id=f"p{i}", base_longos=10000) for i in range(4)]
              + [_canal(100, id="gigante", base_longos=10_000_000)])
    linha = nichos.tabela()["nichos"][0]
    assert linha["tipico"] == 10000
    assert linha["canais"] == 5


def test_a_tabela_separa_por_nicho_e_conta_parado_e_crescendo(sem_banco):
    sem_banco([_canal(100, id="a", nicho="Animais", fase="crescendo", views_total=100),
               _canal(100, id="b", nicho="Animais", fase="parado", views_total=200),
               _canal(20, id="c", nicho="Espaço", fase="nascendo", views_total=50)],
              {"a": 10, "b": 0, "c": 5})
    por_nome = {l["nicho"]: l for l in nichos.tabela()["nichos"]}
    assert por_nome["Animais"]["canais"] == 2
    assert por_nome["Animais"]["crescendo"] == 1 and por_nome["Animais"]["parados"] == 1
    assert por_nome["Animais"]["publico"] == 300
    assert por_nome["Animais"]["views_mes"] == 10 and por_nome["Animais"]["postando"] == 1
    assert por_nome["Espaço"]["novos"] == 1               # menos de 3 meses postando


def test_o_minimo_de_canais_tira_o_nicho_pequeno_da_tabela(sem_banco):
    sem_banco([_canal(100, id="a", nicho="Animais"), _canal(100, id="b", nicho="Animais"),
               _canal(100, id="c", nicho="Espaço")])
    assert [l["nicho"] for l in nichos.tabela(minimo=2)["nichos"]] == ["Animais"]


def test_sem_canal_nenhum_a_tela_nao_quebra(sem_banco):
    sem_banco([])
    d = nichos.linha_da_vida()
    assert d["canais"] == 0 and d["topo"] == 0
    assert all(e["canais"] == 0 and e["views_mes"] == 0 for e in d["etapas"])
    assert nichos.tabela()["nichos"] == []


def test_os_limites_da_etapa_batem_com_a_faixa_que_a_tela_conta():
    """O clique numa etapa abre os vídeos dela: o filtro do servidor tem de pedir a MESMA faixa de dias."""
    assert nichos.limites("testando") == (0, 30)
    assert nichos.limites("veterano") == (730, None)        # a última não tem fim
    for chave, _nome, de, ate, _v, _o in nichos.ETAPAS:
        assert nichos.limites(chave) == (de, ate)


def test_etapa_que_nao_existe_nao_vira_filtro():
    """Endereço velho ou chave torta não pode virar lista vazia: sem faixa, o servidor não filtra nada."""
    assert nichos.limites("") is None
    assert nichos.limites("bananas") is None
