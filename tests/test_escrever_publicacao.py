"""A descrição e as tags do vídeo que não é da fábrica: o teto do campo de tags e a limpeza do que o Claude manda."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import publicar, roteiro_claude  # noqa: E402


@pytest.fixture
def claude(monkeypatch):
    """Troca o Claude Code por um dublê: guarda o pedido e devolve o texto combinado."""
    chamadas = []

    def falso(sistema, pedido, modelo=""):
        chamadas.append({"sistema": sistema, "pedido": pedido})
        return falso.resposta

    falso.resposta = ""
    falso.chamadas = chamadas
    monkeypatch.setattr(roteiro_claude, "_claude", falso)
    return falso


def test_as_tags_param_no_teto_do_campo_do_youtube():
    tags = [f"tag numero {i:02d}" for i in range(60)]          # 14 letras cada: muito mais que 500
    cabem = publicar.tags_que_cabem(tags)
    assert cabem == tags[:len(cabem)]                          # a ordem é a que veio
    assert len(", ".join(cabem)) <= publicar.TAGS_TETO
    assert len(", ".join(cabem + [tags[len(cabem)]])) > publicar.TAGS_TETO   # cortou no lugar certo


def test_tag_repetida_entra_uma_vez_e_sem_espaco_sobrando():
    assert publicar.tags_que_cabem(["Preço  do pão", "preço do pão", " PREÇO DO PÃO ", "outra"]) \
        == ["Preço do pão", "outra"]


def test_a_lista_do_claude_vem_limpa_de_numero_de_marcador_e_de_aspas(claude):
    claude.resposta = '1. preço do pão\n- "pão de forma"\n• #inflação\n\nmercado\nx\n'
    assert publicar.escrever("tags", "O pão subiu de novo")["tags"] == ["preço do pão", "pão de forma", "inflação", "mercado"]
    assert "O pão subiu de novo" in claude.chamadas[0]["pedido"]              # o título é o que guia


def test_sem_tag_nenhuma_o_radar_diz_que_nao_deu(claude):
    claude.resposta = "a\nb\n"                                 # tudo curto demais para ser tag
    with pytest.raises(RuntimeError):
        publicar.escrever("tags", "Um título qualquer")


def _json(sinopse):
    import json
    return json.dumps({"sinopse": sinopse, "tags": ["pão"], "hashtags": ["#pao"]}, ensure_ascii=False)


def test_a_descricao_sai_do_escritor_completo_e_cabe_no_campo(claude):
    # 2026-11-08: o rascunho usa o mesmo escritor da descrição completa (descricao.escrever), com o mínimo da escrita
    claude.resposta = _json("O vídeo mostra o preço do pão. " * 30)
    assert publicar.escrever("descricao", "O pão subiu")["descricao"].startswith("O vídeo mostra o preço do pão.")
    assert "pelo menos 800" in claude.chamadas[0]["pedido"]
    claude.resposta = _json("palavra " * 1000)
    assert len(publicar.escrever("descricao", "O pão subiu")["descricao"]) <= 4000


def test_coreano_pede_o_minimo_do_coreano(claude):
    claude.resposta = _json("가" * 700)
    publicar.escrever("descricao", "한국 자동차는 경쟁국보다 몇 년이나 앞서 있다")
    assert "pelo menos 650" in claude.chamadas[0]["pedido"]


def test_a_fala_do_video_entra_no_pedido_quando_existe(claude):
    claude.resposta = _json("Uma descrição. " * 60)
    publicar.escrever("descricao", "O pão subiu", fala="hoje o pão de forma passou de dois reais")
    assert "hoje o pão de forma passou de dois reais" in claude.chamadas[0]["pedido"]
    claude.chamadas.clear()
    publicar.escrever("descricao", "O pão subiu")
    assert "dois reais" not in claude.chamadas[0]["pedido"]   # sem legenda, nada de fala inventada no pedido
