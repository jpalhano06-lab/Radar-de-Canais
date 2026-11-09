"""A senha só se cria no computador do Radar: de fora, nem quem está logado troca."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from radar import servidor


def pedido(host="127.0.0.1", **cabecalhos):
    return SimpleNamespace(client=SimpleNamespace(host=host), headers={k.replace("_", "-"): v for k, v in cabecalhos.items()})


def test_no_computador_vale():
    assert servidor._so_neste_computador(pedido(), {"id": 1}) == {"id": 1}


@pytest.mark.parametrize("de_fora", [pedido(x_forwarded_for="100.94.27.80"), pedido(host="192.168.0.9"), pedido(cf_connecting_ip="1.2.3.4")])
def test_de_fora_nao_vale(de_fora):
    with pytest.raises(HTTPException) as erro:
        servidor._so_neste_computador(de_fora, {"id": 1})
    assert erro.value.status_code == 403
