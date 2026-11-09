"""O andamento dos vídeos na barra do canto, no ícone da extensão e no celular (pedido do usuário em 2026-11-09)."""
from radar import avisos


def test_barra_de_texto():
    assert avisos.barra_de_texto(0) == "░" * 10
    assert avisos.barra_de_texto(50) == "▓" * 5 + "░" * 5
    assert avisos.barra_de_texto(100) == "▓" * 10


def test_celular_recebe_um_aviso_por_marco(monkeypatch):
    monkeypatch.setattr(avisos, "_marcos", {})
    monkeypatch.setattr(avisos, "_marcos_prontos", False)
    v = {"id": 85, "titulo": "Vídeo", "estado": "produzindo", "pct": 30, "mensagem": "Imagens de IA"}
    assert avisos.progresso_no_celular([v]) == []                 # primeira volta: o que já passou não vai
    assert avisos.progresso_no_celular([{**v, "pct": 40}]) == []  # ainda no mesmo marco
    saiu = avisos.progresso_no_celular([{**v, "pct": 52}])
    assert len(saiu) == 1 and "52%" in saiu[0]["titulo"] and "▓▓▓▓▓" in saiu[0]["texto"] and saiu[0]["prioridade"] == 2
    assert avisos.progresso_no_celular([{**v, "pct": 60}]) == []  # 50 já foi
    parado = {**v, "id": 86, "estado": "precisa_voce", "pct": 90}
    assert avisos.progresso_no_celular([parado]) == []            # parado vai pelo aviso de problema, não por aqui
