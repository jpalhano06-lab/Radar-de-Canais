"""Canal com menos de 1000 inscritos: o pedido do roteiro leva a observação de no mínimo 2 CTAs (2026-11-15)."""
from radar import roteiro_claude


def _inscritos(monkeypatch, valor):
    linha = None if valor == "sem canal" else {"inscritos": valor}
    monkeypatch.setattr(roteiro_claude.banco, "um", lambda *_a: linha)


def test_canal_pequeno_pede_dois_ctas(monkeypatch):
    _inscritos(monkeypatch, 357)
    texto = roteiro_claude.pedido_de_ctas("UCx")
    assert "mínimo 2 CTAs" in texto and "menos de 1000 inscritos" in texto


def test_canal_zerado_tambem_pede(monkeypatch):
    _inscritos(monkeypatch, 0)
    assert "mínimo 2 CTAs" in roteiro_claude.pedido_de_ctas("UCx")


def test_canal_com_mil_ou_mais_nao_pede(monkeypatch):
    _inscritos(monkeypatch, 1000)
    assert roteiro_claude.pedido_de_ctas("UCx") == ""


def test_sem_numero_ou_sem_canal_nao_pede(monkeypatch):
    _inscritos(monkeypatch, None)
    assert roteiro_claude.pedido_de_ctas("UCx") == ""
    _inscritos(monkeypatch, "sem canal")
    assert roteiro_claude.pedido_de_ctas("UCx") == ""
    assert roteiro_claude.pedido_de_ctas("") == ""
