"""A descrição escrita junto com o roteiro: o JSON do Claude, o texto montado e a passagem para o Studio.

Nada de rede nem de Claude aqui: a chamada ao Claude Code é trocada por uma resposta de mentira."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import descricao, publicar  # noqa: E402

RESPOSTA = json.dumps({
    "sinopse": "Três  frases  sobre o vídeo. A segunda. A terceira.",
    "tags": ["gatos raros", "gatos raros", "felinos", "x" * 80, "animais"],
    "hashtags": ["gatos", "#felinos", "!!", "#animais", "#um", "#dois", "#tres"],
}, ensure_ascii=False)


@pytest.fixture
def responder(monkeypatch):
    """Troca o Claude Code por uma resposta pronta e guarda o que ele recebeu."""
    from radar import roteiro_claude
    visto = {}

    def preparar(texto):
        def falso(sistema, pedido, modelo=""):
            visto["sistema"], visto["pedido"] = sistema, pedido
            return texto
        monkeypatch.setattr(roteiro_claude, "_claude", falso)
        return visto

    return preparar


def test_escrever_limpa_o_que_o_claude_devolve(responder):
    visto = responder("```json\n" + RESPOSTA + "\n```")
    d = descricao.escrever("Os gatos mais raros", "Fala do vídeo.", "português", "Nunca use emoji.")
    assert d["sinopse"] == "Três frases sobre o vídeo. A segunda. A terceira."
    # tag repetida e tag grande demais saem; a ordem é a que veio
    assert d["tags"] == ["gatos raros", "felinos", "animais"]
    # a hashtag ganha o # que faltava, a que não tem letra sai e o teto é 5
    assert d["hashtags"] == ["#gatos", "#felinos", "#animais", "#um", "#dois"]
    assert "Nunca use emoji." in visto["sistema"]
    assert "Os gatos mais raros" in visto["pedido"] and "Fala do vídeo." in visto["pedido"]


def test_escrever_reclama_quando_nao_vem_json(responder):
    responder("Aqui está a descrição do seu vídeo!")
    with pytest.raises(RuntimeError, match="JSON"):
        descricao.escrever("T", "Fala.")


def test_escrever_reclama_sem_sinopse(responder):
    responder(json.dumps({"sinopse": "", "tags": ["a"]}))
    with pytest.raises(RuntimeError, match="sinopse"):
        descricao.escrever("T", "Fala.")


def test_montar_poe_sinopse_rodape_e_hashtags():
    dados = {"sinopse": "O que o vídeo mostra.", "hashtags": ["#gatos", "#felinos"]}
    assert descricao.montar(dados, "O canal X explica isto.\n\nAviso: nada aqui é conselho.") == (
        "O que o vídeo mostra.\n\nO canal X explica isto.\n\nAviso: nada aqui é conselho.\n\n#gatos #felinos")
    # sem rodapé do canal, a descrição não fica com buraco
    assert descricao.montar({"sinopse": "Só isto."}) == "Só isto."


def test_salvar_guarda_a_correcao_da_pessoa(tmp_path):
    (tmp_path / descricao.ARQUIVO).write_text(json.dumps({"sinopse": "Velha", "tags": ["a"]}), encoding="utf-8")
    d = descricao.salvar(tmp_path, "Nova  sinopse.", ["um", "um", "dois"], ["tres"])
    assert d == {"sinopse": "Nova sinopse.", "tags": ["um", "dois"], "hashtags": ["#tres"]}
    assert descricao.ler(tmp_path) == d
    with pytest.raises(RuntimeError, match="sinopse"):
        descricao.salvar(tmp_path / "vazia", "")


def test_levar_para_a_fabrica_e_a_extensao_usar(tmp_path):
    """O arquivo chega na pasta do projeto antes de a fábrica montar o vídeo: o Studio já acha e já preenche."""
    roteiro = tmp_path / "roteiro"
    roteiro.mkdir()
    (roteiro / descricao.ARQUIVO).write_text(json.dumps(
        {"sinopse": "O que o vídeo mostra.", "tags": ["gatos raros"], "hashtags": ["#gatos"]}), encoding="utf-8")
    projetos = tmp_path / "projetos"
    destino = projetos / "gatos-raros"
    assert descricao.levar(roteiro, destino, "Os gatos mais raros") is True

    # a pasta ainda não tem publicacao.json (a fábrica está fazendo o vídeo) e mesmo assim a extensão acha
    assert not (destino / "publicacao.json").exists()
    assert publicar.achar(projetos, "Os gatos mais raros.mp4") == "gatos-raros"
    kit = publicar.kit(destino)
    assert kit["titulo"] == "Os gatos mais raros"
    assert kit["descricao"] == "O que o vídeo mostra.\n\n#gatos"
    assert kit["tags"] == ["gatos raros"] and kit["hashtags"] == ["#gatos"]
    assert kit["origem"] == "radar"
    assert kit["sintetico"] is True      # todo vídeo da fábrica é feito com IA


def test_a_descricao_do_radar_ganha_da_da_fabrica(tmp_path):
    pasta = tmp_path / "p"
    pasta.mkdir()
    (pasta / "publicacao.json").write_text(json.dumps(
        {"titulo": "T", "descricao": "A da fábrica", "tags": ["velha"]}), encoding="utf-8")
    assert publicar.kit(pasta)["origem"] == "fabrica"
    (pasta / publicar.RADAR).write_text(json.dumps(
        {"titulo": "T", "sinopse": "A do Radar", "descricao": "A do Radar", "tags": ["nova"]}), encoding="utf-8")
    kit = publicar.kit(pasta)
    assert kit["descricao"] == "A do Radar" and kit["tags"] == ["nova"] and kit["origem"] == "radar"
    # os capítulos e a legenda continuam saindo da fábrica, que é quem os tem
    assert kit["titulo"] == "T"


def test_levar_nao_escreve_nada_sem_sinopse(tmp_path):
    destino = tmp_path / "destino"
    assert descricao.levar(tmp_path / "vazia", destino, "T") is False
    assert not destino.exists()


# ---------------------------------------------------------------- todo vídeo vai com descrição (2026-11-17)

def _pasta_de_roteiro(raiz, nome="2026-11-17-2106-roteiro", titulo="日本の新発明"):
    pasta = raiz / nome
    pasta.mkdir(parents=True)
    (pasta / "roteiro.txt").write_text("A fala do vídeo.", encoding="utf-8")
    (pasta / "roteiro.json").write_text(json.dumps({"titulo": titulo, "lingua": "japonês"}, ensure_ascii=False),
                                        encoding="utf-8")
    return pasta


def test_garantir_escreve_a_descricao_que_faltou_e_leva_para_a_fabrica(tmp_path, responder, monkeypatch):
    """Pedido do usuário em 2026-11-17: "coloque sempre descrição para o Claude criar e ir com o vídeo"."""
    from radar import roteiro_claude
    # o roteiro é japonês: a sinopse também (a em português agora é recusada)
    responder(json.dumps({"sinopse": "動画のあらすじ。" * 120, "tags": ["日本 発明"], "hashtags": ["#日本"]}, ensure_ascii=False))
    monkeypatch.setattr(roteiro_claude, "PASTA", tmp_path / "roteiros")
    monkeypatch.setattr(roteiro_claude, "FABRICA", tmp_path / "fabrica")
    monkeypatch.setattr(descricao, "agente", lambda *_a, **_k: None)
    _pasta_de_roteiro(tmp_path / "roteiros")
    (tmp_path / "fabrica" / "projetos" / "roteiro-16").mkdir(parents=True)

    kit = descricao.garantir(1, "roteiro-16", "2026-11-17-2106-roteiro", titulo="日本の新発明")
    assert kit["descricao"].startswith("動画のあらすじ。")
    assert kit["titulo"] == "日本の新発明" and kit["tags"]
    assert descricao.na_fabrica("roteiro-16")["descricao"] == kit["descricao"]   # ficou na pasta do projeto


def test_garantir_devolve_o_que_ja_esta_na_fabrica_sem_chamar_o_claude(tmp_path, monkeypatch):
    from radar import roteiro_claude
    monkeypatch.setattr(roteiro_claude, "FABRICA", tmp_path / "fabrica")
    pasta = tmp_path / "fabrica" / "projetos" / "roteiro-16"
    pasta.mkdir(parents=True)
    (pasta / descricao.NA_FABRICA).write_text(json.dumps({"descricao": "A que já foi"}), encoding="utf-8")
    monkeypatch.setattr(descricao, "gerar", lambda *_a, **_k: pytest.fail("não era para escrever de novo"))
    assert descricao.garantir(1, "roteiro-16", "qualquer")["descricao"] == "A que já foi"


def test_garantir_sem_roteiro_para_escrever_devolve_vazio(tmp_path, monkeypatch):
    from radar import roteiro_claude
    monkeypatch.setattr(roteiro_claude, "PASTA", tmp_path / "roteiros")
    monkeypatch.setattr(roteiro_claude, "FABRICA", tmp_path / "fabrica")
    assert descricao.garantir(1, "roteiro-16", "sumiu") == {}


def test_a_descricao_tenta_de_novo_quando_o_claude_falha(tmp_path, monkeypatch):
    from radar import roteiro_claude
    pasta = _pasta_de_roteiro(tmp_path)
    voltas = []

    def falhar_duas_vezes(usuario_id, p, projeto_id=None):
        voltas.append(1)
        if len(voltas) < 3:
            raise RuntimeError("o Claude caiu")
        (p / descricao.ARQUIVO).write_text(json.dumps({"sinopse": "Deu certo na terceira."}), encoding="utf-8")
        return {}
    monkeypatch.setattr(descricao, "gerar", falhar_duas_vezes)
    roteiro_claude._escrever_descricao(1, pasta, None)
    meta = json.loads((pasta / "roteiro.json").read_text(encoding="utf-8"))
    assert len(voltas) == roteiro_claude.TENTATIVAS_DESCRICAO == 3 and meta["descricao_erro"] == ""


def test_dois_roteiros_do_mesmo_minuto_nao_dividem_a_pasta(tmp_path, monkeypatch):
    """Em japonês o slug não sobra nada ("roteiro"): dois pedidos do mesmo minuto caíam na mesma pasta e o segundo
    escrevia por cima do primeiro (os dois vídeos do canal japonês, 2026-11-17 21:06)."""
    from radar import roteiro_claude
    monkeypatch.setattr(roteiro_claude, "PASTA", tmp_path)
    a = roteiro_claude._pasta_nova("日本の新発明が銅を永久に置き換える可能性")
    b = roteiro_claude._pasta_nova("日本の新たな石油発見が世界中に衝撃を与えた！")
    assert a != b and a.exists() and b.exists() and b.name.endswith("-2")
