"""O Radar é só de canal dark: a lista de vídeos não mostra canal que nunca entrou, e canal com rosto não entra.

O usuário viu pagode e clipe de música no Faceless Outliers (2026-10-25). Os canais vinham da extensão, que guarda
todo canal que a pessoa vê enquanto navega no YouTube — eles ficam no banco com `no_radar=0`, sem nicho e sem rosto
sabido. Sem nicho, o corte dos nichos que pagam pouco (`mercado.irrelevante`) não pegava nada, e eles subiam ao topo
porque a nota é views ÷ o normal do canal, e o normal de quem foi visto de passagem é minúsculo.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, garimpo, servidor  # noqa: E402

LONGO = 900          # segundos: não é Short
NORMAL = 100_000     # o normal do canal, bem acima do servidor.NORMAL_MINIMO


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    banco.con()
    yield
    banco._CON.close()
    banco._CON = None


def canal(cid, *, no_radar, nicho="História", sem_rosto=1, normal=NORMAL):
    banco.gravar("canais", "id", {"id": cid, "titulo": cid, "nicho": nicho, "no_radar": no_radar,
                                  "sem_rosto": sem_rosto, "base_longos": normal, "base_curtos": normal,
                                  "fase": "crescendo", "inscritos": 50_000, "primeiro_video": "2026-01-01T00:00:00Z"})


def video(vid, cid, views):
    banco.gravar("videos", "id", {"id": vid, "canal_id": cid, "titulo": vid, "views": views,
                                  "duracao_s": LONGO, "publicado": "2026-10-01T00:00:00Z"})
    banco.executar("INSERT OR REPLACE INTO outliers (video_id, canal_id, nota, achado) VALUES (?,?,?,?)",
                   vid, cid, views / NORMAL, banco.agora())


def lista(usuario_id=1, **q):
    """A consulta da tela, sem o FastAPI: o mesmo SQL que o /api/outliers monta."""
    onde = [f"{servidor._NOTA_VIVA} >= 5", f"{servidor._NORMAL} >= {servidor.NORMAL_MINIMO}"]
    base = (f"FROM outliers o JOIN videos v ON v.id=o.video_id JOIN canais c ON c.id=o.canal_id "
            f"WHERE c.no_radar=1 AND {' AND '.join(onde)}")
    return [l["id"] for l in banco.todos(f"SELECT v.id {base}")]


# ---------------------------------------------------------------- a lista de vídeos

def test_canal_que_a_extensao_leu_de_passagem_nao_aparece_na_lista(db):
    """O caso de verdade: 'pagodepontocom' entrou no banco porque a pessoa passou por ele no YouTube."""
    canal("dark", no_radar=1)
    canal("pagodepontocom", no_radar=0, nicho="", sem_rosto=None, normal=1_200)
    video("v-dark", "dark", 1_000_000)          # 10x o normal
    video("v-pagode", "pagodepontocom", 21_000_000)   # 17.500x: ia encabeçar a tela
    assert lista() == ["v-dark"], "o canal fora do Radar não pode aparecer na lista de vídeos"


def test_o_corte_vale_para_todas_as_listas_de_video():
    """Títulos já tinha o `c.no_radar=1`; a lista de vídeos e o banco de títulos não podiam ficar sem."""
    fonte = Path(servidor.__file__).read_text(encoding="utf-8")
    juncoes = [l for l in fonte.splitlines() if "FROM outliers o JOIN videos v" in l]
    assert len(juncoes) >= 3, "mudou o número de listas que leem outliers: confira o corte em cada uma"
    # cada consulta que lê outliers tem de cortar por no_radar, aqui ou na lista de condições logo acima
    assert fonte.count("c.no_radar=1") >= 4


def test_sem_o_corte_o_pagode_voltaria(db):
    """Guarda o motivo: é o `c.no_radar=1` que segura, não a sorte dos outros filtros."""
    canal("pagodepontocom", no_radar=0, nicho="", sem_rosto=None, normal=1_200)
    video("v-pagode", "pagodepontocom", 21_000_000)
    sem_corte = banco.todos(
        f"SELECT v.id FROM outliers o JOIN videos v ON v.id=o.video_id JOIN canais c ON c.id=o.canal_id "
        f"WHERE {servidor._NOTA_VIVA} >= 5 AND {servidor._NORMAL} >= {servidor.NORMAL_MINIMO}")
    assert [l["id"] for l in sem_corte] == ["v-pagode"], "sem o corte ele passa por todo o resto"
    assert lista() == []


# ---------------------------------------------------------------- quem entra no Radar

def _completar(cid, sem_rosto, nicho="História"):
    """Roda o garimpo._completar sem Groq: o rosto e o nicho já vêm decididos."""
    canal(cid, no_radar=0, nicho=nicho, sem_rosto=sem_rosto)
    c = banco.um("SELECT * FROM canais WHERE id=?", cid)
    return garimpo._completar(c, rapido=True)


def test_canal_com_rosto_nao_entra_no_radar(db):
    assert _completar("tem-rosto", sem_rosto=0) is False
    assert banco.um("SELECT no_radar FROM canais WHERE id=?", "tem-rosto")["no_radar"] == 0


def test_canal_sem_rosto_entra(db):
    assert _completar("dark", sem_rosto=1) is True
    assert banco.um("SELECT no_radar FROM canais WHERE id=?", "dark")["no_radar"] == 1


def test_rosto_nao_sabido_nao_e_o_mesmo_que_tem_rosto(db):
    """O Groq fora do ar não pode barrar canal: `None` entra e o completar_pendentes resolve depois."""
    assert _completar("ainda-nao-sei", sem_rosto=None) is True


def test_nicho_que_paga_pouco_continua_de_fora(db):
    assert _completar("clipe", sem_rosto=1, nicho="Música") is False


# ---------------------------------------------------------------- as capas do cartão

def test_o_cartao_do_canal_leva_cinco_videos(db):
    canal("dark", no_radar=1)
    for i in range(8):
        video(f"v{i}", "dark", 1_000_000 - i * 1000)
    c = banco.um("SELECT * FROM canais WHERE id=?", "dark")
    assert servidor.VIDEOS_DO_CARTAO == 5
    assert len(servidor._vitrine(c)["videos"]) == 5, "cinco capas: com três não dá para ver o padrão do canal"
