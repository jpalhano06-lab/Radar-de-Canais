"""Os três modos do Niche Finder: Cartões, Gráfico e Mapa (pedido do usuário, 2026-10-25, com o print do Dotti).

O Gráfico conta os canais pelas cinco etapas de vida (pelo tempo que o canal está postando); o Mapa junta por nicho.
Os dois saem do mesmo filtro da lista — o do Dotti ignora o filtro, o nosso não — e clicar numa etapa vira o filtro
`etapa` da lista de cartões.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, metricas, servidor  # noqa: E402

AGORA = datetime.now(timezone.utc)


def quando(dias: float) -> str:
    return (AGORA - timedelta(days=dias)).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- as etapas

@pytest.mark.parametrize("dias, etapa", [
    (0, "teste"), (14, "teste"), (15, "decolagem"), (60, "decolagem"), (61, "corrida"), (120, "corrida"),
    (121, "maturidade"), (420, "maturidade"), (421, "saturacao"), (3000, "saturacao"), (None, None)])
def test_a_etapa_pelo_tempo_postando(dias, etapa):
    assert metricas.etapa(dias) == etapa


def test_as_etapas_do_painel_sao_as_do_servidor():
    """O painel desenha o select de etapa antes do resumo chegar: a lista dele tem de ser a mesma daqui."""
    fonte = (Path(servidor.__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
    for chave, rotulo, *_ in metricas.ETAPAS:
        assert f'["{chave}", "{rotulo}"' in fonte, f"a etapa {chave} sumiu do app.js"


# ---------------------------------------------------------------- o filtro e o resumo

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    banco.con()
    yield
    banco._CON.close()
    banco._CON = None


EU = {"id": 1}


def canal(cid, dias, *, nicho="História", normal=20_000, fase="crescendo", inscritos=10_000, velocidade=1_000):
    banco.gravar("canais", "id", {"id": cid, "titulo": cid, "nicho": nicho, "no_radar": 1, "sem_rosto": 1,
                                  "base_longos": normal, "fase": fase, "inscritos": inscritos,
                                  "velocidade": velocidade, "primeiro_video": quando(dias)})


def ids(q):
    juntos, args = servidor._onde_radar(q, EU)
    return sorted(c["id"] for c in banco.todos(f"SELECT c.id FROM canais c WHERE {juntos}", *args))


def test_o_filtro_etapa_pega_so_os_canais_dela(db):
    canal("bebe", 10)
    canal("decolando", 30)
    canal("maduro", 200)
    assert ids({"etapa": "decolagem"}) == ["decolando"]
    assert ids({"etapa": "teste"}) == ["bebe"]
    assert ids({"etapa": "nao-existe"}) == ["bebe", "decolando", "maduro"], "etapa desconhecida não filtra"


def test_o_resumo_conta_as_etapas(db):
    canal("a", 10, normal=30_000, velocidade=2_000)
    canal("b", 12, normal=50_000, velocidade=4_000)
    canal("c", 200, normal=20_000)
    r = servidor._resumo(banco.todos("SELECT * FROM canais"))
    etapas = {e["chave"]: e for e in r["etapas"]}
    assert [e["chave"] for e in r["etapas"]] == ["teste", "decolagem", "corrida", "maturidade", "saturacao"]
    assert etapas["teste"]["canais"] == 2
    assert etapas["teste"]["media"] == 40_000             # a mediana do vídeo típico
    assert etapas["teste"]["mes"] == 90_000               # views por dia × 30, em média
    assert etapas["maturidade"]["canais"] == 1
    assert etapas["corrida"]["canais"] == 0 and etapas["corrida"]["media"] is None
    assert r["canais"] == 3


def test_o_mapa_junta_por_nicho(db):
    canal("h1", 30, nicho="História", normal=10_000, inscritos=1_000, fase="parado")
    canal("h2", 30, nicho="História", normal=30_000, inscritos=2_000, fase="crescendo")
    canal("h3", 30, nicho="História", normal=20_000, inscritos=3_000, fase="estavel")
    canal("f1", 30, nicho="Finanças", normal=90_000, inscritos=5_000, fase="nascendo")
    nichos = {n["nicho"]: n for n in servidor._resumo(banco.todos("SELECT * FROM canais"))["nichos"]}
    assert nichos["História"] == {"nicho": "História", "canais": 3, "normal": 20_000, "parados": 1,
                                  "crescendo": 1, "publico": 6_000}
    assert nichos["Finanças"]["crescendo"] == 1, "nascendo também é crescer"
    primeiro = servidor._resumo(banco.todos("SELECT * FROM canais"))["nichos"][0]
    assert primeiro["nicho"] == "Finanças", "o mapa abre pelo normal típico, do maior para o menor"


def test_o_resumo_respeita_o_filtro_da_tela(db):
    """O do Dotti mostra o mesmo mapa em todas as visões. O nosso conta só o que a lista mostra."""
    canal("h", 30, nicho="História")
    canal("f", 30, nicho="Finanças")
    juntos, args = servidor._onde_radar({"nicho": "Finanças"}, EU)
    r = servidor._resumo(banco.todos(f"SELECT c.* FROM canais c WHERE {juntos}", *args))
    assert [n["nicho"] for n in r["nichos"]] == ["Finanças"]
