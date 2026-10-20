"""A página Custos: as somas pelo custos_reais.json da fábrica, sem rede."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import custos  # noqa: E402


def test_linhas_toleram_campos_faltando(tmp_path):
    (tmp_path / "custos_reais.json").write_text(json.dumps([
        {"quando": "2026-10-18T00:00:00", "categoria": "narracao", "valor_usd": 0.3, "detalhes": {"provedor": "genaipro"}},
        {"quando": "2026-10-18T00:01:00", "categoria": "imagem", "detalhes": {}}]), encoding="utf-8")
    assert [(l["provedor"], l["usd"]) for l in custos.linhas(tmp_path)] == [("genaipro", 0.3), ("outros", 0)]
    assert custos.linhas(tmp_path / "nada") == []
    (tmp_path / "custos_reais.json").write_text("[{", encoding="utf-8")
    assert custos.linhas(tmp_path) == []


def _l(prov, cat, usd):
    return {"quando": "", "categoria": cat, "provedor": prov, "usd": usd}


VIDEOS = [{"nome": "a", "titulo": "A", "canal": "X", "criado": "2026-10-17T10:00:00", "minutos": 30,
           "linhas": [_l("genaipro", "narracao", 1.0), _l("openrouter", "imagem", 2.0)]},
          {"nome": "b", "titulo": "B", "canal": "Y", "criado": "2026-10-16T10:00:00", "minutos": 10,
           "linhas": [_l("openrouter", "imagem", 1.0)]}]


def test_resumo():
    r = custos.resumo(VIDEOS, None)
    assert (r["total"], r["videos"], r["media_video"], r["usd_por_minuto"]) == (4.0, 2, 2.0, 0.1)
    assert r["por_provedor"] == {"genaipro": 1.0, "openrouter": 3.0}
    assert r["por_categoria"] == {"imagem": 3.0, "narracao": 1.0}
    assert r["por_canal"][0] == {"canal": "X", "total": 3.0, "media": 3.0}
    assert [v["nome"] for v in r["lista"]] == ["a", "b"]
    assert r["lista"][0]["usd_por_minuto"] == 0.1


def test_resumo_so_do_periodo():
    r = custos.resumo(VIDEOS, 1, hoje="2026-10-17")
    assert (r["videos"], r["total"]) == (1, 3.0)


def test_combinar_soma_igual_a_da_fabrica():
    # o custos_reais.json só tem narração e imagem; texto, visão e juiz a fábrica soma pelos modelos_de_texto
    fabrica = {"total_usd": 0.9935, "por_categoria": {"narracao": 0.2977, "imagem": 0.3916, "visao": 0.2517, "juiz": 0.0482, "texto": 0.0043},
               "modelos_de_texto": [{"provedor": "OpenRouter", "custo_usd": 0.186742}, {"provedor": "Gemini", "custo_usd": 0.069236},
                                    {"provedor": "Jev", "custo_usd": 0.048196}, {"provedor": "Groq", "custo_usd": 0}]}
    reais = [_l("genaipro", "narracao", 0.2977), _l("openrouter", "imagem", 0.39)]
    ls = custos.combinar(fabrica, reais)
    assert round(sum(l["usd"] for l in ls), 4) == 0.9935
    por = {}
    for l in ls:
        por[l["provedor"]] = por.get(l["provedor"], 0) + l["usd"]
    assert por["genaipro"] == pytest.approx(0.2977)
    assert por["openrouter"] == pytest.approx(0.3916 + 0.3042 * 0.186742 / 0.304174, abs=0.0002)
    assert "groq" not in por                                   # custo 0 não vira linha
    assert {l["categoria"] for l in ls} == {"narracao", "imagem", "visao", "juiz", "texto"}


def test_combinar_sem_resposta_da_fabrica_usa_o_arquivo():
    reais = [_l("genaipro", "narracao", 0.3)]
    assert custos.combinar(None, reais) == reais


def test_detalhe(tmp_path):
    (tmp_path / "custos_reais.json").write_text(json.dumps([
        {"categoria": "imagem", "valor_usd": 0.005, "detalhes": {"provedor": "openrouter", "cena": 3}},
        {"categoria": "imagem", "valor_usd": 0.005, "detalhes": {"provedor": "openrouter", "cena": 4}},
        {"categoria": "narracao", "valor_usd": 0.3, "detalhes": {"provedor": "genaipro"}}]), encoding="utf-8")
    d = custos.detalhe(tmp_path)
    assert d == {"por_categoria": {"narracao": 0.3, "imagem": 0.01}, "por_provedor": {"genaipro": 0.3, "openrouter": 0.01},
                 "imagens_ia": 2, "total": 0.31}
