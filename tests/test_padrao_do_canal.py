"""O "Tornar padrão" da Nova produção (2026-11-15): agente, idioma e tempo viram o padrão do canal, e o resto da
configuração do canal (anúncios, tela final, descrição) continua como estava."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, producao, servidor  # noqa: E402


class _Pedido:
    def __init__(self, dados):
        self._dados = dados

    async def json(self):
        return self._dados


@pytest.fixture
def canal(monkeypatch, tmp_path):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    monkeypatch.setattr(servidor, "_meu_canal", lambda *_a: {"id": "UCx", "titulo": "Canal X"})
    monkeypatch.setattr(producao, "_perfil", lambda _nome: {})
    producao.salvar(1, "UCx", producao.config(1, "UCx") | {"minutos": 20, "lingua": "coreano", "projeto_roteiro_id": "3",
                                                             "anuncio_cada": 2, "tela_final": "ultimo", "marcas": "@x"})
    return "UCx"


def _padrao(dados):
    return asyncio.run(servidor.producao_padrao("UCx", _Pedido(dados), {"id": 1}))


def test_muda_so_agente_idioma_e_tempo(canal):
    cfg = _padrao({"projeto_roteiro_id": "7", "lingua": "inglês", "minutos": 30})
    assert (cfg["projeto_roteiro_id"], cfg["lingua"], cfg["minutos"]) == ("7", "inglês", 30)
    assert (cfg["anuncio_cada"], cfg["tela_final"], cfg["marcas"]) == (2, "ultimo", "@x")
    assert producao.config(1, "UCx")["minutos"] == 30


def test_sem_agente_e_tempo_fora_do_limite(canal):
    cfg = _padrao({"projeto_roteiro_id": "", "minutos": 999})
    assert cfg["projeto_roteiro_id"] == "" and cfg["minutos"] == 60 and cfg["lingua"] == "coreano"
