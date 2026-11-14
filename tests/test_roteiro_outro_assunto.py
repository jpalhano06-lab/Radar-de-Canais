"""O título pedido troca o assunto da referência: o roteiro é do assunto do título (2026-11-14, Lidl x Sainsbury's)."""

from radar import roteiro_claude as rc

REF = "Sainsbury’s £33 Billion Empire Is Collapsing — And Nobody Can Save It IN THE UK"
PEDIDO = "Lidl’s $30 Billion Empire Is Collapsing — And Nobody Can Save It!"


def test_titulos_diferentes_vao_lado_a_lado_no_pedido():
    texto = rc.aviso_de_outro_assunto(PEDIDO, REF)
    assert REF in texto and PEDIDO in texto
    assert "PEDIDO" in texto and "não entram" in texto


def test_mesmo_titulo_ou_sem_referencia_nao_muda_nada():
    assert rc.aviso_de_outro_assunto(REF, REF) == ""
    assert rc.aviso_de_outro_assunto(PEDIDO, "") == ""


def test_titulo_da_referencia_vem_do_banco_sem_rede(monkeypatch):
    monkeypatch.setattr(rc.banco, "um", lambda sql, *a: {"titulo": REF})
    monkeypatch.setattr(rc, "titulo_do_video", lambda v: (_ for _ in ()).throw(AssertionError("não devia ir à rede")))
    assert rc.titulo_da_referencia("3naZ3gy2zyY") == REF


def test_sem_o_banco_usa_o_youtube_e_sem_nada_fica_vazio(monkeypatch):
    monkeypatch.setattr(rc.banco, "um", lambda sql, *a: None)
    monkeypatch.setattr(rc, "titulo_do_video", lambda v: REF)
    assert rc.titulo_da_referencia("x") == REF

    def falha(v):
        raise ValueError("sem título")

    monkeypatch.setattr(rc, "titulo_do_video", falha)
    assert rc.titulo_da_referencia("x") == ""
