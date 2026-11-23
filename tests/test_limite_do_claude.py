"""O Claude no limite da assinatura (do estudo da Dotti, 2026-11-22): não insiste, o roteiro que já existe fica com a
melhor volta, o pedido volta para a fila e a fila só pede roteiro de novo quando o limite renova. Sem rede."""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, fila, roteiro_claude  # noqa: E402


@pytest.fixture
def sem_pausa(tmp_path, monkeypatch):
    monkeypatch.setattr(roteiro_claude, "VAZIA", tmp_path / "claude")
    monkeypatch.setattr(roteiro_claude, "_PAUSA_ATE", {"ate": 0.0})
    monkeypatch.setattr(roteiro_claude.shutil, "which", lambda _n: "claude")
    return tmp_path


def _responde(monkeypatch, stdout, stderr=""):
    chamadas = []

    def rodar(comando, **_k):
        chamadas.append(comando)
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=1)
    monkeypatch.setattr(roteiro_claude.subprocess, "run", rodar)
    return chamadas


@pytest.mark.parametrize("resultado", ["Claude AI usage limit reached|{epoca}",
                                       "You've hit your limit · resets 7pm (America/Sao_Paulo)",
                                       "5-hour limit reached ∙ resets 3am"])
def test_limite_pausa_e_nao_chama_de_novo(sem_pausa, monkeypatch, resultado):
    epoca = int(time.time()) + 3600
    chamadas = _responde(monkeypatch, json.dumps({"is_error": True, "result": resultado.format(epoca=epoca)}))
    with pytest.raises(roteiro_claude.LimiteDoClaude):
        roteiro_claude._claude("s", "p")
    assert roteiro_claude.pausa_do_claude() > 0
    with pytest.raises(roteiro_claude.LimiteDoClaude, match="volta a pedir roteiro"):
        roteiro_claude._claude("s", "p")
    assert len(chamadas) == 1                       # na pausa, nem chama
    # vale depois de religar: a pausa está no arquivo
    roteiro_claude._PAUSA_ATE["ate"] = 0.0
    assert roteiro_claude.pausa_do_claude() > 0


def test_erro_que_nao_e_limite_continua_erro_comum(sem_pausa, monkeypatch):
    _responde(monkeypatch, json.dumps({"is_error": True, "result": "Invalid model"}))
    with pytest.raises(RuntimeError) as erro:
        roteiro_claude._claude("s", "p")
    assert not isinstance(erro.value, roteiro_claude.LimiteDoClaude)
    assert roteiro_claude.pausa_do_claude() == 0


def test_titulo_que_fala_de_limite_nao_para_a_fila(sem_pausa, monkeypatch):
    _responde(monkeypatch, json.dumps({"is_error": False, "result": "Why the rate limit reached every API"}))
    assert roteiro_claude._claude("s", "p").startswith("Why")
    assert roteiro_claude.pausa_do_claude() == 0


def test_quando_renova():
    agora = datetime(2026, 11, 22, 14, 0).timestamp()
    assert roteiro_claude._quando_renova("resets 7pm", agora) == datetime(2026, 11, 22, 19, 0).timestamp()
    assert roteiro_claude._quando_renova("resets at 13:30", agora) == datetime(2026, 11, 23, 13, 30).timestamp()
    assert roteiro_claude._quando_renova(f"usage limit reached|{int(agora) + 600}", agora) == agora + 600
    assert roteiro_claude._quando_renova("weekly limit reached", agora) == agora + roteiro_claude.PAUSA_PADRAO


def test_limite_no_meio_do_tamanho_fica_com_a_melhor_volta(monkeypatch):
    def no_limite(*_a, **_k):
        raise roteiro_claude.LimiteDoClaude("limite")
    monkeypatch.setattr(roteiro_claude, "_claude", no_limite)
    avisos = []
    roteiro = "palavra " * 300
    final, conf = roteiro_claude._conferir_tamanho(roteiro, "s", "p", 10, {"ppm": 150}, avisos.append, "português")
    assert final == roteiro and conf["voltas"][-1]["o_que"] == "limite do Claude"
    assert any("limite" in a for a in avisos)


# ------------------------------------------------------------------ a fila


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    fila._PARADOS.clear()
    yield
    banco._CON.close()
    banco._CON = None


class Fabrica:
    def producoes(self):
        return {"andamento": [], "prontos": []}

    def produzir(self, nome, confirmar):
        pass


class Roteirista:
    def __init__(self, pausa=0.0, limite=False):
        self.pausa, self.limite, self.pedidos = pausa, limite, []

    def pausa_do_claude(self):
        return self.pausa

    def gerar(self, **pedido):
        self.pedidos.append(pedido)
        if self.limite:
            raise roteiro_claude.LimiteDoClaude("O Claude bateu no limite da assinatura. A fila volta a pedir "
                                                "roteiro às 19:00.")
        return {"nome": "r-" + pedido["titulo"]}

    def manual(self, **pedido):
        return {"nome": "m-" + pedido["titulo"]}

    def enviar(self, usuario_id, nome, perfil):
        return {"projeto": "p-" + nome}


def _volta(rot):
    return fila.passo(fabrica=Fabrica(), roteirista=rot, em_thread=False,
                      config_canal=lambda uid, cid: {"perfil": "canal-x", "lingua": "inglês", "canal": "X"},
                      ritmo=lambda uid, perfil, lingua: {"ppm": 150})


def test_limite_no_roteiro_volta_para_a_fila_sem_erro(db):
    fid = fila.criar(1, {"titulo": "T", "caracteres": 10620}, comecar=True)["id"]
    _volta(Roteirista(limite=True))
    item = fila.item(1, fid)
    assert item["estado"] == "na_fila" and not item["erro"] and "limite" in item["passo"]


def test_na_pausa_a_fila_nao_pede_roteiro_mas_o_colado_anda(db):
    a = fila.criar(1, {"titulo": "T", "caracteres": 10620}, comecar=True)["id"]
    b = fila.criar(1, {"titulo": "U", "caracteres": 0, "roteiro_manual": "texto colado"}, comecar=True)["id"]
    rot = Roteirista(pausa=600)
    _volta(rot)
    assert rot.pedidos == [] and fila.item(1, a)["estado"] == "na_fila"
    assert fila.item(1, b)["roteiro"] == "m-U"
    rot.pausa = 0
    _volta(rot)
    assert [p["titulo"] for p in rot.pedidos] == ["T"]
