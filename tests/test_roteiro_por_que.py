"""O roteiro leva em conta por que o vídeo de referência estourou, além da transcrição."""
from radar import lente_ia, roteiro_claude as r


def test_o_texto_leva_so_o_que_veio():
    texto = r.texto_do_por_que({"resumo": "curiosidade", "quebra": "o preço caiu", "prova": "", "loop": None})
    assert "curiosidade" in texto and "o preço caiu" in texto
    assert "Prova específica" not in texto and "Pergunta que fica aberta" not in texto


def test_leitura_vazia_nao_entra_no_pedido():
    assert r.texto_do_por_que({}) == ""


def test_usa_o_titulo_da_referencia(monkeypatch):
    visto = {}
    monkeypatch.setattr(r, "titulo_do_video", lambda _v: "Título da referência")
    monkeypatch.setattr(lente_ia, "por_que", lambda v, t, f: visto.update(titulo=t, fala=f) or {"resumo": "x"})
    assert r.por_que_estourou("abcdefghijk", "Título pedido", "a fala") == {"resumo": "x"}
    assert visto == {"titulo": "Título da referência", "fala": "a fala"}


def test_sem_o_titulo_da_referencia_vale_o_pedido(monkeypatch):
    visto = {}

    def fora(_v):
        raise r.httpx.ConnectError("fora")
    monkeypatch.setattr(r, "titulo_do_video", fora)
    monkeypatch.setattr(lente_ia, "por_que", lambda v, t, f: visto.update(titulo=t) or {"resumo": "x"})
    r.por_que_estourou("abcdefghijk", "Título pedido", "a fala")
    assert visto["titulo"] == "Título pedido"


def test_falha_na_leitura_nao_para_o_roteiro(monkeypatch):
    def quebra(*_a):
        raise RuntimeError("o Claude não respondeu")
    monkeypatch.setattr(r, "titulo_do_video", lambda _v: "t")
    monkeypatch.setattr(lente_ia, "por_que", quebra)
    avisos = []
    assert r.por_que_estourou("abcdefghijk", "t", "fala", avisos.append) == {}
    assert any("seguindo com a transcrição" in a for a in avisos)
