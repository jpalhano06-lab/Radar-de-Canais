"""O país que mais assiste o canal sai do último relatório guardado do Studio."""
import json

from radar import studio


def test_pega_o_primeiro_pais_do_relatorio(monkeypatch):
    linhas = [{"dados": json.dumps({"paises": []})}, {"dados": json.dumps({"paises": [{"country": "CA", "views": 9}, {"country": "US", "views": 3}]})}]
    monkeypatch.setattr(studio.banco, "todos", lambda *_a: linhas)
    assert studio.pais_do_publico(1, "UCx") == "CA"


def test_sem_relatorio_fica_vazio(monkeypatch):
    monkeypatch.setattr(studio.banco, "todos", lambda *_a: [])
    assert studio.pais_do_publico(1, "UCx") == ""
