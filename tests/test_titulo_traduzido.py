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
        if pedido.startswith("Língua de destino"):
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


# 2026-11-03: o título japonês do vídeo de referência voltava em PORTUGUÊS para o canal japonês ("Língua: japonês"
# dava para o modelo entender "a língua do título é japonês"). O pedido agora diz qual é a língua de DESTINO, e o
# Radar confere o alfabeto da resposta.

JAPONES = "日本の新発明が銅を永久に置き換える可能性 — 中国が警戒！"


def test_o_pedido_diz_a_lingua_de_destino(monkeypatch):
    pedidos = _claude_falso(monkeypatch, "석유를 영원히 대체할 한국의 발명")
    assert roteiro_claude.traduzir_titulo(JAPONES, "coreano") == "석유를 영원히 대체할 한국의 발명"
    assert pedidos[0].startswith("Língua de destino (escreva o título NESTA língua): coreano (ko)")


def test_titulo_ja_no_alfabeto_da_lingua_nem_chama_o_claude(monkeypatch):
    pedidos = _claude_falso(monkeypatch)
    assert roteiro_claude.traduzir_titulo(JAPONES, "japonês") == JAPONES
    assert pedidos == []


def test_traducao_em_outra_lingua_deixa_o_titulo(monkeypatch):
    # era isto que chegava ao Studio: o título do canal japonês em português
    _claude_falso(monkeypatch, "Nova invenção japonesa pode substituir o cobre — China em alerta!")
    assert roteiro_claude.traduzir_titulo(JAPONES, "japonês") == JAPONES
    _claude_falso(monkeypatch, "Nova invenção japonesa pode substituir o cobre")
    assert roteiro_claude.traduzir_titulo(JAPONES, "coreano") == JAPONES


def test_codigo_das_32_linguas_da_fabrica():
    assert roteiro_claude.codigo_da_lingua("japonês") == "ja"
    assert roteiro_claude.codigo_da_lingua("Holandês") == "nl"
    assert roteiro_claude.codigo_da_lingua("ko") == "ko"
    assert roteiro_claude.codigo_da_lingua("klingon") == ""


# 2026-11-04: nos canais japonês e coreano a pasta entregue só tinha o título traduzido, e na lista de Downloads
# um vídeo não dava para distinguir do outro. O nome da entrega leva os dois.


def test_o_nome_da_entrega_leva_a_traducao_e_o_titulo_original():
    meta = {"titulo": JAPONES, "titulo_original": TITULO}
    assert roteiro_claude.titulo_de_entrega(meta) == f"{JAPONES} ({TITULO})"


def test_sem_traducao_o_nome_da_entrega_nao_repete_o_titulo():
    assert roteiro_claude.titulo_de_entrega({"titulo": TITULO, "titulo_original": TITULO}) == TITULO
    assert roteiro_claude.titulo_de_entrega({"titulo": TITULO}) == TITULO       # roteiro antigo, sem o original


def test_o_nome_da_entrega_cabe_no_caminho_do_windows():
    meta = {"titulo": "A" * 200, "titulo_original": "B" * 200}
    nome = roteiro_claude.titulo_de_entrega(meta)
    assert len(nome) <= roteiro_claude.LIMITE_DO_NOME and nome.endswith(")")
