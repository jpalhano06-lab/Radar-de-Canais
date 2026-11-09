"""A retenção do canal vira lição para o próximo roteiro, e a falta dela nunca para o pedido."""
import json

from radar import retencao, roteiro_claude, studio


def test_um_minuto_pega_o_ponto_mais_perto():
    assert retencao._em_um_minuto({0.1: 0.8, 0.2: 0.6, 0.5: 0.3}, 300) == 0.6
    assert retencao._em_um_minuto({}, 300) is None


def test_mede_so_video_longo_com_views_e_ordena_pelo_primeiro_minuto(monkeypatch):
    def relatorio(_t, _c, _i, _f, metricas, **extra):
        if "views" in metricas:
            return {"linhas": [{"video": "a", "views": 900, "averageViewDuration": 200, "averageViewPercentage": 40},
                               {"video": "b", "views": 900, "averageViewDuration": 300, "averageViewPercentage": 30},
                               {"video": "curto", "views": 900, "averageViewDuration": 50, "averageViewPercentage": 50},
                               {"video": "pouca", "views": 10, "averageViewDuration": 300, "averageViewPercentage": 30}]}
        valor = 0.5 if "video==a" in extra["filters"] else 0.7
        return {"linhas": [{"elapsedVideoTimeRatio": 0.1, "audienceWatchRatio": valor}]}
    monkeypatch.setattr(studio, "_relatorio", relatorio)
    assert [v["video"] for v in retencao.medir("t", "UC")] == ["b", "a"]


def test_poucos_videos_nao_viram_licao(monkeypatch):
    monkeypatch.setattr(studio, "_token", lambda *_: "t")
    monkeypatch.setattr(retencao, "medir", lambda *_: [{"video": "a", "um_minuto": 0.5}])
    assert retencao.aprender(1, "UC") == {}


def test_compara_os_extremos(monkeypatch):
    pedidos = []
    monkeypatch.setattr(studio, "_token", lambda *_: "t")
    monkeypatch.setattr(retencao, "medir", lambda *_: [{"video": str(i), "um_minuto": 0.9 - i / 10} for i in range(7)])
    monkeypatch.setattr(retencao, "_comeco_da_fala", lambda v: f"fala {v}")
    monkeypatch.setattr(roteiro_claude, "_claude", lambda s, p: pedidos.append(p) or json.dumps({"fazer": ["a"], "evitar": ["b"]}))
    achado = retencao.aprender(1, "UC")
    assert achado == {"fazer": ["a"], "evitar": ["b"], "videos": 7}
    assert "fala 0" in pedidos[0] and "fala 6" in pedidos[0] and "fala 3" not in pedidos[0]


def test_sem_studio_conectado_fica_vazio(monkeypatch):
    monkeypatch.setattr(retencao.banco, "um", lambda *_: None)
    assert retencao.licoes(1, "UC") == {}


def test_erro_na_leitura_nao_para_o_roteiro(monkeypatch):
    monkeypatch.setattr(retencao.banco, "um", lambda sql, *_: {"x": 1} if "studio" in sql else None)

    def quebra(*_):
        raise RuntimeError("Analytics fora")
    monkeypatch.setattr(retencao, "aprender", quebra)
    assert retencao.licoes(1, "UC") == {}


def test_o_texto_do_pedido():
    assert "Faça: abrir com o caso" in retencao.texto({"fazer": ["abrir com o caso"], "evitar": [], "videos": 9})
    assert retencao.texto({}) == ""
