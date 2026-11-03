"""O título escrito em português sai na língua falada no vídeo.

Pedido do usuário em 2026-10-29: "o título lá pode ser em português, porém sempre terá a tradução automática pra
língua que vai ser falada". Nada de rede nem de Claude aqui."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import roteiro_claude, tempo  # noqa: E402

TITULO = "Por que os gatos dormem 16 horas por dia?"


def _claude_falso(monkeypatch, traducao="Why Do Cats Sleep 16 Hours a Day?"):
    pedidos = []

    def falso(sistema, pedido, modelo=""):
        pedidos.append(pedido)
        if pedido.startswith("Língua:"):
            return traducao
        return "Primeira frase do roteiro. " * 200

    monkeypatch.setattr(roteiro_claude, "_claude", falso)
    return pedidos


def test_traduz_para_a_lingua_do_video(monkeypatch):
    _claude_falso(monkeypatch, '"Why Do Cats Sleep 16 Hours a Day?"')
    assert roteiro_claude.traduzir_titulo(TITULO, "inglês") == "Why Do Cats Sleep 16 Hours a Day?"


def test_ja_na_lingua_certa_nem_chama_o_claude(monkeypatch):
    pedidos = _claude_falso(monkeypatch)
    assert roteiro_claude.traduzir_titulo("Por que os gatos dormem tanto? A explicação", "português").startswith("Por que")
    assert pedidos == []


def test_traducao_estranha_ou_falha_deixa_o_titulo(monkeypatch):
    _claude_falso(monkeypatch, "Aqui está:\nWhy Do Cats Sleep")
    assert roteiro_claude.traduzir_titulo(TITULO, "inglês") == TITULO

    def quebra(*a, **k):
        raise RuntimeError("sem Claude")
    monkeypatch.setattr(roteiro_claude, "_claude", quebra)
    assert roteiro_claude.traduzir_titulo(TITULO, "holandês") == TITULO


def _pasta(monkeypatch, tmp_path):
    roteiros = tmp_path / "roteiros"
    roteiros.mkdir()
    monkeypatch.setattr(roteiro_claude, "PASTA", roteiros)
    monkeypatch.setattr(tempo, "_da_api", lambda: {})
    monkeypatch.setattr(roteiro_claude, "_escrever_descricao", lambda *a, **k: None)
    monkeypatch.setattr(roteiro_claude.banco, "um", lambda *a: None)
    return roteiros


def test_o_roteiro_do_claude_guarda_o_titulo_traduzido(monkeypatch, tmp_path):
    roteiros = _pasta(monkeypatch, tmp_path)
    pedidos = _claude_falso(monkeypatch)
    r = roteiro_claude.gerar(usuario_id=1, titulo=TITULO, link="", minutos=3, lingua="inglês", projeto_id=None,
                             observacoes="")
    meta = json.loads((roteiros / r["nome"] / "roteiro.json").read_text(encoding="utf-8"))
    assert meta["titulo"] == "Why Do Cats Sleep 16 Hours a Day?"     # é ele que vira o titulo_entrega na fábrica
    assert meta["titulo_original"] == TITULO
    assert "Título do vídeo: Why Do Cats Sleep" in pedidos[1]       # o roteiro é escrito para o título traduzido


def test_o_roteiro_colado_tambem(monkeypatch, tmp_path):
    roteiros = _pasta(monkeypatch, tmp_path)
    _claude_falso(monkeypatch)
    r = roteiro_claude.manual(usuario_id=1, titulo=TITULO, texto="Cats sleep a lot. " * 20, lingua="inglês")
    meta = json.loads((roteiros / r["nome"] / "roteiro.json").read_text(encoding="utf-8"))
    assert meta["titulo"] == "Why Do Cats Sleep 16 Hours a Day?"
