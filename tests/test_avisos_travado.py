"""O pedido que a fábrica tenta de novo sem sair do lugar, e o saldo da voz acabando, chegam como aviso."""
import json

from radar import avisos, banco, config, fabrica_api


def _fila(monkeypatch, tmp_path, logs, mensagem=""):
    projeto = tmp_path / "projetos" / "p1"
    projeto.mkdir(parents=True)
    (projeto / "criacao.json").write_text(json.dumps({"logs": logs, "mensagem": mensagem, "concluido": False}), encoding="utf-8")
    monkeypatch.setattr(config, "FABRICA", tmp_path)
    monkeypatch.setattr(banco, "todos", lambda sql, *a: [{"id": 83, "projeto": "p1"}])


def test_sem_saldo_avisa_na_hora(monkeypatch, tmp_path):
    _fila(monkeypatch, tmp_path, ["Narração: A GenAIPro recusou o pedido (400). Not enough credit",
                                  "tentando de novo em 300s, de onde parou (tentativa 2)"])
    [a] = avisos.travados()
    assert a["nivel"] == "erro" and "saldo da GenAIPro" in a["titulo"] and "segue sozinho" in a["texto"]


def test_mesma_falha_que_volta_avisa(monkeypatch, tmp_path):
    _fila(monkeypatch, tmp_path, ["Imagens: o provedor falhou", "tentando de novo em 300s (tentativa 4)"])
    [a] = avisos.travados()
    assert "tentando de novo" in a["titulo"] and "tentativa 4" in a["texto"]


def test_uma_tentativa_so_nao_avisa(monkeypatch, tmp_path):
    _fila(monkeypatch, tmp_path, ["Imagens: o provedor falhou", "tentando de novo em 30s (tentativa 1)"])
    assert avisos.travados() == []


def test_voz_acabando(monkeypatch):
    monkeypatch.setattr(banco, "um", lambda sql, *a: {"x": 1})
    monkeypatch.setattr(fabrica_api, "_pedir", lambda *a, **k: {"configurada": True, "creditos": 671, "minutos_de_narracao": 11})
    [a] = avisos.voz()
    assert a["nivel"] == "atencao" and "671 créditos, uns 11 min" in a["texto"]
    monkeypatch.setattr(fabrica_api, "_pedir", lambda *a, **k: {"configurada": True, "creditos": 90000, "minutos_de_narracao": 70})
    assert avisos.voz() == []
