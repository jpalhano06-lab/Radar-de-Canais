"""Postar no dia marcado (2026-11-17): o vídeo da fila sobe quando fica pronto, no dia que foi marcado.

Sem rede: a fábrica é de mentira."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import agendar, banco, fabrica_api, fila  # noqa: E402


KIT = {"titulo": "日本の新発明", "descricao": "A descrição do Claude.", "tags": ["銅 代替"]}


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    fila._PARADOS.clear()
    monkeypatch.setattr(fabrica_api, "youtube_do_projeto", lambda nome: None)
    # a descrição do Claude vai com o vídeo (2026-11-17): aqui ela já está escrita
    monkeypatch.setattr(agendar, "kit_do_video", lambda uid, item: dict(KIT))
    yield
    banco._CON.close()
    banco._CON = None


@pytest.fixture
def enviados(monkeypatch):
    feitos = []
    monkeypatch.setattr(fabrica_api, "youtube_publicar",
                        lambda nome, canal, quando="", com_thumbnail=True, titulo="", descricao=None, tags=None, **r:
                        feitos.append((nome, canal, quando, com_thumbnail, titulo, descricao, tags)) or {"sucesso": True})
    return feitos


def _pedido():
    return fila.criar(1, {"titulo": "日本の新発明", "caracteres": 12120}, comecar=True)["id"]


def _entregue(fid, projeto="meu-projeto"):
    banco.executar("UPDATE producoes_fila SET estado='entregue', projeto=? WHERE id=?", projeto, fid)


def test_so_sobe_quando_o_video_fica_pronto(db, enviados):
    fid = _pedido()
    agendar.marcar(1, fid, "UC1", "2026-11-18T18:00")
    assert agendar.andar() == [] and enviados == []      # ainda na fila: nada sobe
    _entregue(fid)
    assert agendar.andar() == [fid]
    assert enviados == [("meu-projeto", "UC1", "2026-11-18T18:00", True, KIT["titulo"], KIT["descricao"], KIT["tags"])]
    assert agendar.do_pedido(1, fid)["enviado"]
    agendar.andar()
    assert len(enviados) == 1                            # mandado uma vez só


def test_sem_dia_marcado_sobe_assim_que_fica_pronto(db, enviados):
    fid = _pedido()
    agendar.marcar(1, fid, "UC1", com_thumbnail=False)
    _entregue(fid)
    agendar.andar()
    assert enviados == [("meu-projeto", "UC1", "", False, KIT["titulo"], KIT["descricao"], KIT["tags"])]


def test_o_link_aparece_quando_a_fabrica_termina(db, enviados, monkeypatch):
    fid = _pedido()
    agendar.marcar(1, fid, "UC1")
    _entregue(fid)
    agendar.andar()
    monkeypatch.setattr(fabrica_api, "youtube_do_projeto", lambda nome: {"url": "https://youtu.be/abc"})
    agendar.andar()
    assert agendar.do_pedido(1, fid)["url"] == "https://youtu.be/abc"


def test_canal_nao_conectado_guarda_o_erro_e_tenta_de_novo(db, monkeypatch):
    def recusar(*a, **k):
        raise fabrica_api.SemFabrica("O canal não foi conectado no YouTube.", 400)
    monkeypatch.setattr(fabrica_api, "youtube_publicar", recusar)
    fid = _pedido()
    agendar.marcar(1, fid, "UC1")
    _entregue(fid)
    agendar.andar()
    assert "não foi conectado" in agendar.do_pedido(1, fid)["erro"]
    assert not agendar.do_pedido(1, fid)["enviado"]

    chamou = []
    monkeypatch.setattr(fabrica_api, "youtube_publicar", lambda *a, **k: chamou.append(a) or {"sucesso": True})
    agendar.andar()
    assert chamou == []                                  # espera ESPERA_NOVA_TENTATIVA antes de tentar
    monkeypatch.setattr(agendar, "ESPERA_NOVA_TENTATIVA", 0)
    agendar.andar()
    assert len(chamou) == 1 and not agendar.do_pedido(1, fid)["erro"]


def test_marcar_pede_pedido_e_canal_de_verdade(db):
    with pytest.raises(ValueError):
        agendar.marcar(1, 999, "UC1")
    fid = _pedido()
    with pytest.raises(ValueError):
        agendar.marcar(1, fid, "")
    with pytest.raises(ValueError):
        agendar.marcar(1, fid, "UC1", "amanhã de tarde")
    agendar.marcar(1, fid, "UC1", "2026-11-18T18:00")
    agendar.desmarcar(1, fid)
    assert agendar.do_pedido(1, fid) is None


def test_nenhum_video_sobe_sem_a_descricao_do_claude(db, enviados, monkeypatch):
    """Pedido do usuário em 2026-11-17: "coloque sempre descrição para o Claude criar e ir com o vídeo"."""
    monkeypatch.setattr(agendar, "kit_do_video", lambda uid, item: {})
    fid = _pedido()
    agendar.marcar(1, fid, "UC1")
    _entregue(fid)
    agendar.andar()
    assert enviados == [] and agendar.do_pedido(1, fid)["erro"] == agendar.SEM_DESCRICAO

    monkeypatch.setattr(agendar, "kit_do_video", lambda uid, item: dict(KIT))
    monkeypatch.setattr(agendar, "ESPERA_NOVA_TENTATIVA", 0)
    agendar.andar()
    assert len(enviados) == 1 and not agendar.do_pedido(1, fid)["erro"]
