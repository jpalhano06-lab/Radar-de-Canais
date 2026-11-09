"""O Gemini responde quando as chaves do Groq gastam a cota do dia (sem rede).

Caso real (2026-11-03): as 11 chaves do Groq estouraram a cota de tokens do dia e 264 canais ficaram sem nicho e sem
rosto até o outro dia."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import ia  # noqa: E402


class _Resposta:
    def __init__(self, status, corpo=None, texto="", cabecalhos=None, conteudo=b""):
        self.status_code, self._corpo, self.text = status, corpo, texto
        self.headers, self.content = cabecalhos or {}, conteudo

    def json(self):
        return self._corpo


def _resposta_ok(conteudo):
    return _Resposta(200, {"choices": [{"message": {"content": conteudo}}]})


@pytest.fixture
def sem_groq(monkeypatch):
    monkeypatch.setattr(ia, "chaves_groq", lambda: [])
    monkeypatch.setattr(ia, "chaves_gemini", lambda: ["g1", "g2"])
    monkeypatch.setattr(ia, "_GEMINI_FORA", {})
    monkeypatch.setattr(ia, "_RECUSADAS", set())


def test_sem_groq_pergunta_ao_gemini(sem_groq, monkeypatch):
    pedidos = []
    monkeypatch.setattr(ia._CLIENTE, "post", lambda url, **k: pedidos.append((url, k["json"])) or _resposta_ok('{"nicho": "História"}'))
    assert ia._perguntar(ia.MODELO_TEXTO, "sistema", "conteudo") == {"nicho": "História"}
    assert pedidos[0][0] == ia.URL_GEMINI and pedidos[0][1]["model"] == ia.MODELO_GEMINI


def test_a_capa_vai_junto_em_base64(sem_groq, monkeypatch):
    enviado = []
    monkeypatch.setattr(ia._CLIENTE, "get", lambda url, **k: _Resposta(200, cabecalhos={"content-type": "image/jpeg"}, conteudo=b"jpg") if "boa" in url else _Resposta(404))
    monkeypatch.setattr(ia._CLIENTE, "post", lambda url, **k: enviado.append(k["json"]) or _resposta_ok('{"apresentador": false}'))
    conteudo = [{"type": "text", "text": "capas"}, {"type": "image_url", "image_url": {"url": "https://i.ytimg.com/boa.jpg"}},
                {"type": "image_url", "image_url": {"url": "https://i.ytimg.com/apagada.jpg"}}]
    assert ia._perguntar(ia.MODELO_VISAO, "sistema", conteudo) == {"apresentador": False}
    partes = enviado[0]["messages"][1]["content"]
    assert [p["type"] for p in partes] == ["text", "image_url"]     # a capa apagada ficou de fora
    assert partes[1]["image_url"]["url"] == "data:image/jpeg;base64,anBn"


def test_chave_do_gemini_no_limite_passa_a_vez(sem_groq, monkeypatch):
    usadas = []

    def post(url, **k):
        usadas.append(k["headers"]["Authorization"])
        if len(usadas) == 1:
            return _Resposta(429, texto='{"error": {"details": [{"retryDelay": "37s"}]}}')
        return _resposta_ok('{"ok": true}')
    monkeypatch.setattr(ia._CLIENTE, "post", post)
    assert ia._perguntar(ia.MODELO_TEXTO, "s", "c") == {"ok": True}
    assert len(set(usadas)) == 2 and len(ia._GEMINI_FORA) == 1


def test_esgotado_so_quando_o_gemini_tambem_acabou(sem_groq, monkeypatch):
    assert ia.esgotado(ia.MODELO_VISAO) is False
    monkeypatch.setattr(ia, "_GEMINI_FORA", {"g1": float("inf"), "g2": float("inf")})
    assert ia.esgotado(ia.MODELO_VISAO) is True


def test_espera_do_gemini():
    assert ia._espera_gemini('"retryDelay": "37s"') == 38
    assert ia._espera_gemini('GenerateRequestsPerDayPerProjectPerModel "retryDelay": "37s"') == 3600
