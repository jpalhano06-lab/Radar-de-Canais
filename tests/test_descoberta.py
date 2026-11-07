"""De onde vêm os canais e as ideias: origem, palavras-chave, subtemas, nichos com espaço, categoria e repescagem."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, descoberta, garimpo, medir, metricas, youtube  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    yield
    banco._CON.close()
    banco._CON = None


def _dias(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def test_palavras_compostas_entre_aspas():
    p = descoberta.palavras('history "ancient rome" documentary "lost cities" history')
    assert [x["termo"] for x in p] == ["history", "ancient rome", "documentary", "lost cities"]
    assert [x["composto"] for x in p] == [False, True, False, True]


def test_topicos_viram_o_nome_do_fim_do_link():
    assert descoberta.topicos(json.dumps(["https://en.wikipedia.org/wiki/Military_history"])) == ["Military history"]
    assert descoberta.topicos("quebrado") == []


def test_origem_fica_a_primeira(db):
    banco.gravar("canais", "id", {"id": "UC1", "titulo": "a"})
    descoberta.marcar_origem(["UC1"], "categoria")
    descoberta.marcar_origem(["UC1"], "lente")
    assert banco.um("SELECT origem FROM canais WHERE id='UC1'")["origem"] == "categoria"


def test_subtemas_so_dos_que_estouraram_e_guardados(db):
    banco.gravar("canais", "id", {"id": "UC1", "titulo": "a", "base_longos": 10000})
    banco.gravar("videos", "id", {"id": "v1", "canal_id": "UC1", "titulo": "Golpe famoso", "views": 90000, "duracao_s": 600})
    banco.gravar("videos", "id", {"id": "v2", "canal_id": "UC1", "titulo": "Vídeo comum", "views": 12000, "duracao_s": 600})
    perguntas = []

    def modelo(_m, _s, lista, **_k):
        perguntas.append(lista)
        return {"subtemas": [{"n": 1, "subtema": "golpes famosos"}]}

    d = descoberta.subtemas("UC1", perguntar=modelo)
    assert [(v["id"], v["subtema"]) for v in d["videos"]] == [("v1", "Golpes famosos")]
    descoberta.subtemas("UC1", perguntar=modelo)
    assert len(perguntas) == 1   # a segunda vez vem do banco


def test_nicho_com_espaco_tem_estouro_e_pouca_gente(db):
    for i in range(2):
        banco.gravar("canais", "id", {"id": f"UCa{i}", "titulo": "a", "no_radar": 1, "subnicho": "Cidades abandonadas", "nicho": "História"})
    for i in range(5):
        banco.gravar("canais", "id", {"id": f"UCb{i}", "titulo": "b", "no_radar": 1, "subnicho": "Crimes reais", "nicho": "Crimes Reais"})
    banco.executar("INSERT INTO outliers (video_id, canal_id, nota, achado) VALUES ('v1','UCa0',8,?)", _dias(2))
    banco.executar("INSERT INTO outliers (video_id, canal_id, nota, achado) VALUES ('v2','UCb0',9,?)", _dias(2))
    lista = descoberta.com_espaco()
    assert [l["subnicho"] for l in lista] == ["Cidades abandonadas"]    # o outro tem 5 canais
    assert lista[0]["exemplo"]["video_id"] == "v1"


def test_categoria_em_alta_marca_a_origem(db, monkeypatch):
    monkeypatch.setattr(youtube, "populares", lambda cat, reg: [{"video_id": "x", "canal_id": "UCnovo", "titulo": "t"}])
    vistos = []

    def avaliar(ids, log, contagem, rapido=False, origem="busca"):
        vistos.append((tuple(ids), origem))
        return []
    monkeypatch.setattr(garimpo, "_avaliar", avaliar)
    monkeypatch.setattr(youtube, "cota_hoje", lambda: {"usado": 0})
    garimpo.varrer_categorias(lambda *_: None, 10_000, {"novos": 0})
    assert vistos and all(o == "categoria" for _, o in vistos)
    # no mesmo dia não olha a mesma lista de novo
    antes = len(vistos)
    garimpo.varrer_categorias(lambda *_: None, 10_000, {"novos": 0})
    assert len(vistos) == antes


def test_repescagem_traz_de_volta_quem_passou_a_passar(db, monkeypatch):
    banco.gravar("canais", "id", {"id": "UCr", "titulo": "r", "no_radar": 0, "base_longos": 4000,
                                  "medido": _dias(30), "primeiro_video": _dias(120), "origem": "busca"})
    monkeypatch.setattr(youtube, "cota_hoje", lambda: {"usado": 0})
    monkeypatch.setattr(medir, "medir_canais", lambda ids, forcar=False: {i: banco.um("SELECT * FROM canais WHERE id=?", i) for i in ids})
    monkeypatch.setattr(garimpo, "_passa", lambda cid, c: True)

    def completar(c, rapido=False):
        banco.executar("UPDATE canais SET no_radar=1 WHERE id=?", c["id"])
        return True
    monkeypatch.setattr(garimpo, "_completar", completar)
    contagem = {"novos": 0}
    assert garimpo.repescagem(lambda *_: None, 10_000, contagem) == 1
    c = banco.um("SELECT origem, repescado FROM canais WHERE id='UCr'")
    assert c["origem"] == "repescagem" and c["repescado"]
    assert [x["id"] for x in descoberta.repescados()] == ["UCr"]


def test_canal_publico_leva_origem_e_palavras():
    c = {k: None for k in ("id", "titulo", "handle", "foto", "pais", "inscritos", "videos_total", "views_total",
                           "criado_em", "primeiro_video", "primeiro_exato", "ultimo_video", "base_longos", "base_curtos",
                           "media_longos", "fase", "raridade", "nicho", "sem_rosto")}
    c |= {"primeiro_video": "", "primeiro_exato": 0, "origem": "lente", "keywords": '"true crime" mystery'}
    p = medir._canal_publico(c)
    assert p["origem"] == "lente" and p["palavras"][0] == {"termo": "true crime", "composto": True}


def test_canal_da_api_traz_keywords():
    item = {"id": "UC1", "snippet": {"title": "a"}, "statistics": {},
            "brandingSettings": {"channel": {"keywords": '"a b" c'}},
            "topicDetails": {"topicCategories": ["https://en.wikipedia.org/wiki/Knowledge"]}}
    c = youtube._canal(item)
    assert c["keywords"] == '"a b" c' and c["topicos"] == ["https://en.wikipedia.org/wiki/Knowledge"]
    assert metricas.CURTO_ATE_S > 0
