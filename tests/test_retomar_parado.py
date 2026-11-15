"""O Acompanhar mostra o motivo e o botão Retomar quando a criação para (pedido do usuário em 2026-11-08)."""
from radar import avisos


def test_saldo_acabado_e_parada():
    d = {"logs": ["  Narração: A GenAIPro recusou o pedido (400). Not enough credit",
                  "  tentando de novo em 300s, de onde parou (tentativa 292)"], "mensagem": "Narração: um serviço falhou"}
    p = avisos.parada(d)
    assert p["tipo"] == "saldo" and p["servico"] == "GenAIPro" and p["tentativas"] == 292


def test_cota_do_google_acabada_e_parada_de_saldo():
    """O pedido 116 (2026-11-15): 7 h repetindo a falta de cota do Google, e o celular não soube o motivo."""
    d = {"logs": ["  Imagens de IA: O Google recusou as imagens por falta de cota. Ative o faturamento do projeto da sua "
                  "chave no Google AI Studio e rode o mesmo comando de novo.",
                  "  tentando de novo em 300s, de onde parou (tentativa 1)"]}
    p = avisos.parada(d)
    assert p["tipo"] == "saldo" and p["servico"] == "Google" and "falta de cota" in p["motivo"]


def test_precisa_de_voce_e_parada():
    assert avisos.parada({"precisa_voce": True, "mensagem": "Chave inválida"})["tipo"] == "parou"


def test_andando_ou_pronto_nao_e_parada():
    assert avisos.parada({"logs": ["  tentando de novo em 5s, de onde parou (tentativa 1)"]}) is None
    assert avisos.parada({"concluido": True, "erro": "x"}) is None
    assert avisos.parada(None) is None


def test_retomar_chama_a_fabrica_confirmado(monkeypatch):
    import asyncio
    from radar import fabrica_api, servidor
    chamadas = []
    monkeypatch.setattr(servidor, "_projeto_fabrica", lambda nome: None)
    monkeypatch.setattr(fabrica_api, "produzir", lambda nome, confirmar: chamadas.append((nome, confirmar)) or {"status": "retomando"})
    r = asyncio.run(servidor.acompanhar_retomar("video-x", u={"id": 1}))
    assert r == {"status": "retomando"} and chamadas == [("video-x", True)]
