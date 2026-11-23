"""A língua do roteiro conferida em toda língua, e o prompt padrão com a opção de outro (2026-11-20).

Pedido do usuário: "você tem que conferir se realmente os vídeos, as narrações e o roteiro caíram na língua certa"; "o
prompt é padrão, e dê a opção de criar outro, porém esse é o padrão, deixe pra todos"."""
import pytest

from radar import roteiro_claude, tempo

PT = "O rei mandou construir o templo e ninguém ouviu um martelo. Isso foi muito antes de tudo, quando os homens que " \
     "trabalhavam para ele também cortavam as pedras. " * 6
FR = "Le roi a fait construire le temple et personne n'a entendu un marteau. C'est une histoire qui est dans la Bible, " \
     "avec des pierres pour les murs. " * 6
DE = "Der König ließ den Tempel bauen, und niemand hörte einen Hammer. Das ist eine Geschichte, die nicht in jedem Buch " \
     "steht, und sie ist auch für uns wichtig. " * 6


@pytest.mark.parametrize("texto,lingua,errada", [
    (PT, "português", ""), (FR, "francês", ""), (DE, "alemão", ""),
    (PT, "francês", "português"), (FR, "inglês", "francês"), (DE, "italiano", "alemão"),
    (PT, "japonês", "outro alfabeto"), ("日本の新しい発明は銅を置き換える。" * 30, "japonês", ""),
])
def test_a_lingua_do_roteiro_e_conferida(texto, lingua, errada):
    assert roteiro_claude.lingua_errada(texto, lingua) == errada


def test_o_roteiro_na_lingua_errada_e_reescrito(monkeypatch):
    pedidos = []
    monkeypatch.setattr(roteiro_claude, "_claude", lambda s, p, modelo="", pesquisa=False: pedidos.append(p) or FR)
    assert roteiro_claude.garantir_lingua(PT, "francês") == FR.strip()
    assert "francês" in pedidos[0]


def test_reescrito_e_ainda_errado_para_o_pedido(monkeypatch):
    monkeypatch.setattr(roteiro_claude, "_claude", lambda s, p, modelo="", pesquisa=False: PT)
    with pytest.raises(RuntimeError, match="língua errada"):
        roteiro_claude.garantir_lingua(PT, "francês")


def test_o_portao_da_fabrica_barra_a_lingua_errada():
    motivo = roteiro_claude.conferir_roteiro(PT * 3, {"lingua": "francês", "minutos": 0})
    assert "francês" in motivo and "português" in motivo


def _mundo(monkeypatch, tmp_path, prompt_do_banco=None):
    roteiros = tmp_path / "roteiros"
    roteiros.mkdir()
    monkeypatch.setattr(roteiro_claude, "PASTA", roteiros)
    monkeypatch.setattr(tempo, "_da_api", lambda: {})
    monkeypatch.setattr(roteiro_claude, "_escrever_descricao", lambda *a, **k: None)
    monkeypatch.setattr(roteiro_claude, "traduzir_titulo", lambda t, l: t)
    monkeypatch.setattr(roteiro_claude.banco, "um", lambda sql, *a: prompt_do_banco if "tipo='prompt'" in sql else None)
    vistos = []

    def falso(sistema, pedido, modelo="", pesquisa=False):
        vistos.append(sistema)
        return PT * 10
    monkeypatch.setattr(roteiro_claude, "_claude", falso)
    return vistos


def test_sem_escolha_vale_o_prompt_padrao(monkeypatch, tmp_path):
    vistos = _mundo(monkeypatch, tmp_path)
    r = roteiro_claude.gerar(1, "O templo", "", 3, "português", None, "")
    assert vistos[0].startswith(roteiro_claude.PROMPT) and r["prompt"] == "Prompt padrão do Radar"


def test_o_prompt_criado_entra_no_lugar_do_padrao(monkeypatch, tmp_path):
    vistos = _mundo(monkeypatch, tmp_path, {"nome": "Listas curtas", "instrucoes": "MEU PROMPT: escreva listas curtas."})
    r = roteiro_claude.gerar(1, "O templo", "", 3, "português", None, "", prompt_id=5)
    assert vistos[0].startswith("MEU PROMPT") and roteiro_claude.PROMPT not in vistos[0]
    assert r["prompt"] == "Listas curtas"
