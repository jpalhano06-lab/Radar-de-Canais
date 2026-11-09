"""Nenhum teste manda aviso de verdade ao celular (ntfy ou Telegram)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import avisos  # noqa: E402

# o envio de verdade, para o teste que confere o próprio envio (com o httpx de mentira)
NO_CELULAR_DE_VERDADE = avisos._no_celular


@pytest.fixture(autouse=True)
def celular_de_mentira(monkeypatch):
    enviados = []
    monkeypatch.setattr(avisos, "_no_celular", lambda aviso: enviados.append(aviso))
    avisos._prontos_avisados.clear()
    return enviados
