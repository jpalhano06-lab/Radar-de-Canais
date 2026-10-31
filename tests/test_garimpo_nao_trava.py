"""O garimpo gasta a cota nas buscas e não fica preso no Groq (sem rede).

Caso real (2026-10-30): o garimpo começou com 11.989 unidades e 20 horas depois tinha gastado 1.207, sem nenhuma busca.
149 canais do Radar tinham capas que não existem mais (404): o Groq recusava, o canal ficava sem a resposta do rosto, e
cada canal medido de novo perguntava outra vez, esperando até 90 s pelo limite do minuto."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, garimpo, ia, medir, youtube  # noqa: E402

CANAL = "UC" + "r" * 22


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    yield
    banco._CON.close()
    banco._CON = None


class _Resposta:
    def __init__(self, status, texto=""):
        self.status_code, self.text = status, texto


def test_pedido_recusado_nao_tenta_de_novo(monkeypatch):
    """400 (capa que não existe mais) é o mesmo em toda chave: perguntar de novo só gasta o limite do minuto."""
    pedidos = []
    monkeypatch.setattr(ia, "_chave", lambda: "chave")
    monkeypatch.setattr(ia._CLIENTE, "post", lambda *a, **k: pedidos.append(1) or _Resposta(400, "failed to retrieve media"))
    assert ia._perguntar("modelo", "sistema", "conteudo", esperar=90) is None
    assert len(pedidos) == 1


def test_medir_de_novo_nao_pergunta_ao_groq(db, monkeypatch):
    banco.gravar("canais", "id", {"id": CANAL, "titulo": "Canal", "no_radar": 1, "nicho": "Finanças",
                                  "subnicho": "Bancos", "medido": "2026-01-01"})
    monkeypatch.setattr(youtube, "cota_hoje", lambda: {"usado": 0, "livre": 10000})
    monkeypatch.setattr(medir, "medir_canais", lambda ids, forcar=False: {CANAL: banco.um("SELECT * FROM canais WHERE id=?", CANAL)})
    monkeypatch.setattr(ia, "sem_rosto", lambda capas: pytest.fail("o medir de novo perguntou ao Groq"))
    monkeypatch.setattr(ia, "nicho", lambda *a: pytest.fail("o medir de novo perguntou ao Groq"))
    assert garimpo.remedir(print, 1000) == 1


def test_as_buscas_vem_antes_de_completar_os_pendentes(db, monkeypatch):
    ordem = []
    monkeypatch.setattr(youtube, "cota_hoje", lambda: {"usado": 0, "livre": 10000})
    monkeypatch.setattr(garimpo, "completar_pendentes", lambda *a, **k: ordem.append("pendentes"))
    monkeypatch.setattr(garimpo, "remedir", lambda *a, **k: 0)
    monkeypatch.setattr(garimpo, "_proximos_termos", lambda: [("Finanças", "credit card")])
    monkeypatch.setattr(youtube, "buscar", lambda *a, **k: ordem.append("busca") or [])
    monkeypatch.setattr(garimpo, "achar_parecidos_dos_salvos", lambda *a, **k: None)
    monkeypatch.setattr(garimpo, "aprender_termos", lambda *a, **k: 0)
    garimpo.rodar(print)
    assert ordem == ["busca", "pendentes"]
