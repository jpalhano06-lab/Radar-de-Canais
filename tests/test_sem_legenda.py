"""O vídeo de referência sem legenda: o roteiro sai assim mesmo, a partir do título.

Pedido do usuário em 2026-10-28: antes, um vídeo com as legendas desligadas pelo dono (TranscriptsDisabled) parava o
pedido inteiro em "Parou com erro". Nada de rede nem de Claude aqui."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import roteiro_claude, tempo  # noqa: E402

LINK = "https://www.youtube.com/watch?v=o53UMHcHv34"


def _mundo(monkeypatch, tmp_path, erro_da_legenda=None, base=""):
    """A pasta dos roteiros, o Claude de mentira e a legenda que dá certo ou falha. Devolve o que o Claude recebeu."""
    roteiros = tmp_path / "roteiros"
    roteiros.mkdir()
    monkeypatch.setattr(roteiro_claude, "PASTA", roteiros)
    monkeypatch.setattr(tempo, "_da_api", lambda: {})
    monkeypatch.setattr(roteiro_claude, "copiar_thumbnail", lambda *a: False)
    monkeypatch.setattr(roteiro_claude, "_escrever_descricao", lambda *a, **k: None)
    monkeypatch.setattr(roteiro_claude.banco, "um", lambda *a: None)

    def legenda(video_id):
        if erro_da_legenda:
            raise RuntimeError(erro_da_legenda)
        return base, "en"

    monkeypatch.setattr(roteiro_claude, "transcricao", legenda)
    visto = {}

    def falso(sistema, pedido, modelo=""):
        visto["pedido"] = pedido
        return "Primeira frase do roteiro. " * 200

    monkeypatch.setattr(roteiro_claude, "_claude", falso)
    return roteiros, visto


def test_sem_legenda_o_roteiro_sai_do_titulo(monkeypatch, tmp_path):
    roteiros, visto = _mundo(monkeypatch, tmp_path, erro_da_legenda="Subtitles are disabled for this video")
    avisos = []
    r = roteiro_claude.gerar(usuario_id=1, titulo="15 Animais Aterrorizantes que estão Extintos", link=LINK,
                             minutos=5, lingua="inglês", projeto_id=None, observacoes="", aviso=avisos.append)
    assert r["palavras"] > 100                       # o roteiro existe: o pedido não parou com erro
    assert r["palavras_base"] == 0
    assert "Subtitles are disabled" in r["base_erro"]
    assert "sem nenhuma base de transcrição" in visto["pedido"]
    assert any("não deu a legenda" in a for a in avisos)
    meta = json.loads((roteiros / r["nome"] / "roteiro.json").read_text(encoding="utf-8"))
    assert meta["base_erro"]
    assert not (roteiros / r["nome"] / "transcricao.txt").exists()


def test_com_legenda_continua_usando_a_transcricao(monkeypatch, tmp_path):
    roteiros, visto = _mundo(monkeypatch, tmp_path, base="A fala do vídeo de referência. " * 50)
    r = roteiro_claude.gerar(usuario_id=1, titulo="15 Animais Aterrorizantes que estão Extintos", link=LINK,
                             minutos=5, lingua="inglês", projeto_id=None, observacoes="")
    assert r["base_erro"] == ""
    assert r["palavras_base"] == 300
    assert "Transcrição do vídeo de referência" in visto["pedido"]
    assert (roteiros / r["nome"] / "transcricao.txt").exists()
