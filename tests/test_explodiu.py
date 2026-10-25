"""A porta do canal que explodiu e a repescagem dos que já estão no banco (pedido do usuário, 2026-10-25).

O garimpo só deixava entrar canal com normal de 10 mil ou mais: é a mediana, é consistência. O canal dark que acabou de
estourar tem dois ou três vídeos enormes e o resto pequeno, e era medido e mandado embora. No banco do usuário, 146
canais criados há até 18 meses, com 500 mil views ou mais em vídeos longos dos últimos 30 dias, ficaram de fora só por
isso — Wiggle World, com normal de 1.386 e um vídeo de 13,8 milhões, é um deles.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, garimpo, medir, metricas  # noqa: E402

AGORA = datetime.now(timezone.utc)
LONGO = 900
SHORT = 40


def quando(dias: float) -> str:
    return (AGORA - timedelta(days=dias)).isoformat().replace("+00:00", "Z")


def _v(dias, views, duracao=LONGO):
    return {"publicado": quando(dias), "views": views, "duracao_s": duracao}


# ---------------------------------------------------------------- a régua

def test_wiggle_world_explodiu():
    """O caso de verdade: normal de 1.386 e um vídeo de 13,8 milhões nos últimos 30 dias."""
    videos = [_v(12, 13_810_000)] + [_v(40 + i, 1_386) for i in range(15)]
    assert metricas.explodiu(videos, quando(470), 1_386)


def test_quinhentos_mil_somados_nos_longos_dos_ultimos_trinta_dias():
    videos = [_v(5, 200_000), _v(15, 200_000), _v(25, 100_000), _v(60, 9_000_000)]
    assert metricas.explodiu(videos, quando(300), 2_000)
    videos[2] = _v(25, 99_999)
    assert not metricas.explodiu(videos, quando(300), 2_000), "o vídeo de 60 dias atrás não conta"


def test_shorts_nao_contam():
    """O Radar é de vídeo longo: 600 mil só em Shorts não fazem o canal ter explodido."""
    videos = [_v(3, 300_000, SHORT), _v(9, 300_000, SHORT), _v(20, 1_000)]
    assert not metricas.explodiu(videos, quando(300), 1_000)


def test_tres_de_seis_vezes_num_canal_de_ate_sessenta_dias():
    videos = [_v(10, 30_000), _v(20, 30_000), _v(30, 30_000)] + [_v(35 + i, 4_000) for i in range(5)]
    assert metricas.explodiu(videos, quando(50), 4_000)


def test_tres_de_seis_vezes_nao_vale_para_canal_mais_velho():
    videos = [_v(10, 30_000), _v(20, 30_000), _v(30, 30_000)] + [_v(35 + i, 4_000) for i in range(5)]
    assert not metricas.explodiu(videos, quando(200), 4_000)


def test_seis_vezes_de_um_normal_minusculo_nao_conta():
    """Normal de 76 (o ZeroCipher): qualquer vídeo é 6x. Cada um dos três precisa de 6 mil views."""
    videos = [_v(5, 5_000), _v(8, 5_000), _v(11, 5_000), _v(14, 76)]
    assert not metricas.explodiu(videos, quando(40), 76)


# ---------------------------------------------------------------- a porta do garimpo

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    banco.con()
    yield
    banco._CON.close()
    banco._CON = None


def canal(cid, *, normal, criado_dias=300, no_radar=0, sem_rosto=None, nicho="", pais="US", videos_total=40):
    banco.gravar("canais", "id", {"id": cid, "titulo": cid, "nicho": nicho, "no_radar": no_radar,
                                  "sem_rosto": sem_rosto, "base_longos": normal, "pais": pais,
                                  "videos_total": videos_total, "criado_em": quando(criado_dias),
                                  "primeiro_video": quando(criado_dias)})
    return banco.um("SELECT * FROM canais WHERE id=?", cid)


def video(vid, cid, views, dias, duracao=LONGO):
    banco.gravar("videos", "id", {"id": vid, "canal_id": cid, "titulo": vid, "views": views,
                                  "duracao_s": duracao, "publicado": quando(dias)})


def explodido(cid, **k):
    c = canal(cid, normal=1_386, **k)
    video(f"{cid}-hit", cid, 13_810_000, 12)
    for i in range(10):
        video(f"{cid}-{i}", cid, 1_386, 40 + i)
    return c


def test_o_que_explodiu_passa_na_porta(db):
    assert garimpo._passa(explodido("wiggle"))


def test_o_consistente_continua_passando(db):
    c = canal("consistente", normal=15_000)
    for i in range(10):
        video(f"c-{i}", "consistente", 15_000, 40 + i)
    assert garimpo._passa(c)


def test_o_pequeno_sem_explosao_continua_de_fora(db):
    c = canal("pequeno", normal=2_000)
    for i in range(10):
        video(f"p-{i}", "pequeno", 2_000, 5 + i)
    assert not garimpo._passa(c)


def test_explodiu_mas_e_velho_demais(db):
    assert not garimpo._passa(explodido("velho", criado_dias=700))


# ---------------------------------------------------------------- a repescagem

@pytest.fixture
def sem_rede(monkeypatch):
    """Medir de novo sem YouTube: devolve o que está no banco. Groq e risco também ficam de fora."""
    medidos = []

    def medir_canais(ids, forcar=False, origem=""):
        medidos.extend(ids)
        return {c["id"]: c for c in medir._canais_do_banco(ids)}
    monkeypatch.setattr(medir, "medir_canais", medir_canais)
    monkeypatch.setattr(garimpo.risco, "avaliar", lambda titulos: False)
    monkeypatch.setattr(garimpo.ia, "nicho", lambda *a: ("História", "Impérios"))
    monkeypatch.setattr(garimpo.ia, "sem_rosto", lambda capas: True)
    return medidos


def test_repesca_o_que_explodiu_e_poe_no_radar(db, sem_rede):
    explodido("wiggle")
    assert garimpo.repescar(lambda _t: None, orcamento=1_000) == 1
    assert sem_rede == ["wiggle"]
    assert banco.um("SELECT no_radar FROM canais WHERE id='wiggle'")["no_radar"] == 1


def test_nao_repesca_quem_ja_foi_cortado_pelo_rosto(db, sem_rede):
    explodido("tem-rosto", sem_rosto=0)
    assert garimpo.repescar(lambda _t: None, orcamento=1_000) == 0
    assert sem_rede == []


def test_nao_repesca_canal_criado_ha_mais_de_dezoito_meses(db, sem_rede):
    """Felipe Neto e NFL: a extensão só viu os vídeos novos, o primeiro vídeo parecia de outubro."""
    c = explodido("antigo")
    banco.gravar("canais", "id", {"id": c["id"], "criado_em": quando(4_000)})
    assert garimpo.repescar(lambda _t: None, orcamento=1_000) == 0


def test_nao_mede_de_novo_quem_o_banco_ja_diz_que_nao_passa(db, sem_rede):
    """No banco do usuário, 94 dos 392 da fila caíam no país ou na contagem de vídeos depois de gastar a medida."""
    explodido("de-fora", pais="IN")
    explodido("enorme", videos_total=900)
    assert garimpo.repescar(lambda _t: None, orcamento=1_000) == 0
    assert sem_rede == []


def test_nao_repesca_o_mesmo_canal_antes_de_sete_dias(db, sem_rede, monkeypatch):
    monkeypatch.setattr(garimpo.ia, "sem_rosto", lambda capas: None)    # o Groq não respondeu: segue sem saber
    monkeypatch.setattr(garimpo.risco, "avaliar", lambda titulos: True)  # e o risco barrou
    explodido("barrado")
    garimpo.repescar(lambda _t: None, orcamento=1_000)
    garimpo.repescar(lambda _t: None, orcamento=1_000)
    assert sem_rede == ["barrado"], "repescado e barrado, ele espera a semana"


def test_os_que_mais_explodiram_primeiro_e_no_maximo_o_limite(db, sem_rede, monkeypatch):
    monkeypatch.setattr(garimpo, "REPESCAR_POR_VEZ", 2)
    for cid, views in (("menor", 600_000), ("maior", 9_000_000), ("meio", 2_000_000)):
        canal(cid, normal=1_000)
        video(f"{cid}-hit", cid, views, 10)
        video(f"{cid}-x", cid, 1_000, 50)
    garimpo.repescar(lambda _t: None, orcamento=1_000)
    assert sem_rede == ["maior", "meio"]
