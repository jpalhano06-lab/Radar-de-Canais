"""O roteiro que não é roteiro: o Claude perguntando em vez de escrever.

O vídeo japonês do cobre (2026-11-03) saiu com 1 min e 56 narrando oito perguntas numeradas. As instruções do agente
do canal ("JAPÃO AGENTE") mandam "SEMPRE perguntar a duração do vídeo antes de escrever", o `_limpar` apagou o roteiro
japonês (ver test_roteiro_japones.py), e o laço do tamanho pediu "continue de onde parou" com o começo vazio: a lista de perguntas que voltou virou o
roteiro, a conferência disse que faltavam 13,5 minutos e ninguém barrou nada. Aconteceu duas vezes na mesma noite.

Aqui o Claude é falso (nenhuma chamada de verdade), para o teste rodar sem rede e sem assinatura."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import roteiro_claude, tempo  # noqa: E402

LINK = "https://www.youtube.com/watch?v=o53UMHcHv34"

PERGUNTAS = """Não escrevi a continuação porque o começo do roteiro veio vazio: depois de "Você já escreveu este
começo" não há nenhum texto. Preciso que você me diga:

1. Começo do roteiro: pode colar o texto aqui?
2. Ângulo do título: a transcrição não cita nenhuma invenção japonesa. Qual destes caminhos prefere?
3. Formato do vídeo: confirma o formato D?
4. Duração: são 15 minutos só nesta continuação?
"""


def _mundo(monkeypatch, tmp_path, respostas, projeto=None):
    """A pasta dos roteiros e um Claude falso que responde a lista `respostas`, uma por chamada."""
    roteiros = tmp_path / "roteiros"
    roteiros.mkdir()
    monkeypatch.setattr(roteiro_claude, "PASTA", roteiros)
    monkeypatch.setattr(tempo, "_da_api", lambda: {})
    monkeypatch.setattr(roteiro_claude, "copiar_thumbnail", lambda *a: False)
    monkeypatch.setattr(roteiro_claude, "_escrever_descricao", lambda *a, **k: None)
    monkeypatch.setattr(roteiro_claude.banco, "um", lambda *a: projeto)
    monkeypatch.setattr(roteiro_claude, "por_que_estourou", lambda *a, **k: {})
    monkeypatch.setattr(roteiro_claude, "transcricao", lambda v: ("a fala do vídeo " * 50, "en"))
    vistos = []

    def falso(sistema, pedido, modelo=""):
        vistos.append({"sistema": sistema, "pedido": pedido})
        return respostas.pop(0) if respostas else ""

    monkeypatch.setattr(roteiro_claude, "_claude", falso)
    return roteiros, vistos


def _gerar(**extra):
    return dict(usuario_id=1, titulo="日本の新発明が銅を永久に置き換える", link=LINK, minutos=15, lingua="japonês",
                projeto_id=7, observacoes="") | extra


# ------------------------------------------------- 1. o agente do canal não pode mandar perguntar antes de escrever

def test_o_sistema_proibe_perguntar_depois_das_instrucoes_do_canal(monkeypatch, tmp_path):
    """A regra do Radar vai no FIM do sistema, depois das instruções do canal: é a última palavra e vale sobre elas."""
    projeto = {"id": 7, "nome": "JAPÃO AGENTE", "instrucoes": "Regra fixa: SEMPRE perguntar a duração antes de escrever."}
    _, vistos = _mundo(monkeypatch, tmp_path, ["A primeira frase do roteiro. " * 400], projeto=projeto)
    roteiro_claude.gerar(**_gerar())
    sistema = vistos[0]["sistema"]
    assert "Nunca pergunte" in sistema and "ninguém vai ler nem responder" in sistema.lower()
    assert sistema.index("SEMPRE perguntar") < sistema.index("Nunca pergunte")


# ------------------------------------------------------- 2. a resposta que não é roteiro ganha outra chance, e para

def test_a_resposta_sem_roteiro_e_pedida_de_novo(monkeypatch, tmp_path):
    """Primeira resposta vazia (o Claude tentou perguntar): o Radar insiste, e o roteiro da segunda é o que vale."""
    _, vistos = _mundo(monkeypatch, tmp_path, ["", "A primeira frase do roteiro. " * 400])
    r = roteiro_claude.gerar(**_gerar())
    assert r["rascunhos"] == 2 and r["palavras"] > 1000
    assert "não foi um roteiro" in vistos[1]["pedido"]


def test_duas_respostas_sem_roteiro_param_o_pedido_com_erro(monkeypatch, tmp_path):
    """O que não pode mais acontecer: sem roteiro, o pedido para com erro em vez de descer para a fábrica."""
    _mundo(monkeypatch, tmp_path, ["", PERGUNTAS])
    with pytest.raises(RuntimeError, match="não escreveu o roteiro"):
        roteiro_claude.gerar(**_gerar())


def test_o_laco_do_tamanho_nunca_continua_de_um_comeco_vazio(monkeypatch, tmp_path):
    """A continuação de um começo vazio era a lista de perguntas que virou vídeo. Agora não entra em roteiro nenhum."""
    monkeypatch.setattr(roteiro_claude, "_claude", lambda s, p, modelo="": PERGUNTAS)
    roteiro, conf = roteiro_claude._conferir_tamanho("", "sis", "ped", 15, {"ppm": 150, "de": "voz"})
    assert roteiro == "" and conf["voltas"] == []


# ------------------------------------------------------------------- 3. o portão antes da fábrica

def test_o_portao_barra_as_perguntas(monkeypatch):
    motivo = roteiro_claude.conferir_roteiro(PERGUNTAS, {"minutos": 15, "lingua": "japonês", "ritmo": {"ppm": 150}})
    assert "não é um roteiro: são perguntas" in motivo


def test_o_portao_barra_o_roteiro_curto_demais():
    """O caso real: 224 palavras onde a voz do canal pede 2.250 (1,5 min de 15)."""
    motivo = roteiro_claude.conferir_roteiro("palavra " * 224, {"minutos": 15, "ritmo": {"ppm": 150},
                                                                "conferencia": {"alvo_palavras": 2250}})
    assert "1.5 min e você pediu 15" in motivo and "224 das 2250" in motivo


def test_o_portao_barra_o_roteiro_no_alfabeto_errado():
    motivo = roteiro_claude.conferir_roteiro("Uma frase em português. " * 200, {"minutos": 15, "lingua": "japonês",
                                                                               "ritmo": {"ppm": 150}})
    assert "não está escrito em japonês" in motivo


def test_o_portao_deixa_passar_o_roteiro_bom():
    """Um roteiro coreano de verdade (1.746 palavras para 15 min numa voz de 119) continua passando."""
    texto = "한국의 기술이 세계를 또 한 번 놀라게 했습니다. " * 250
    assert roteiro_claude.conferir_roteiro(texto, {"minutos": 15, "lingua": "coreano", "ritmo": {"ppm": 119},
                                                   "conferencia": {"alvo_palavras": 1785}}) == ""


def test_o_portao_deixa_passar_o_japones_sem_espacos():
    """Japonês não separa palavras com espaço: o piso do tamanho conta as letras também, senão nenhum roteiro
    japonês passaria."""
    texto = "日本の技術がまた世界を驚かせました。" * 30
    assert roteiro_claude.conferir_roteiro(texto, {"minutos": 0, "lingua": "japonês", "ritmo": {"ppm": 116}}) == ""
