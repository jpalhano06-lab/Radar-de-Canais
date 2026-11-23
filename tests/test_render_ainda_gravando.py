"""O render ainda gravando não é entregue: o final.mp4 aparece antes de ele terminar (o oxfam-uk em 2026-11-21)."""
from radar import fabrica_api


def _listar(monkeypatch, renderizando):
    projeto = {"nome": "video-x", "perfil": "", "criado": "2026-11-21", "duracao": 600, "cenas_count": 100,
               "tem_final": True, "renderizando": renderizando, "criacao": {"rodando": False, "status": "concluido"}}
    monkeypatch.setattr(fabrica_api, "_pedir", lambda *a, **k: {"projetos": [projeto]})
    monkeypatch.setattr(fabrica_api, "_do_radar", lambda: {})
    monkeypatch.setattr(fabrica_api, "_titulo", lambda nome: nome)
    monkeypatch.setattr(fabrica_api, "_capa", lambda nome: "")
    monkeypatch.setattr(fabrica_api, "_shorts", lambda nome: [])
    monkeypatch.setattr(fabrica_api, "_publicado", lambda nome: None)
    return fabrica_api.producoes()


def test_render_gravando_fica_em_andamento(monkeypatch):
    r = _listar(monkeypatch, renderizando=True)
    assert [p["nome"] for p in r["andamento"]] == ["video-x"]
    assert r["prontos"] == []


def test_render_terminado_vai_para_prontos(monkeypatch):
    r = _listar(monkeypatch, renderizando=False)
    assert [p["nome"] for p in r["prontos"]] == ["video-x"]
