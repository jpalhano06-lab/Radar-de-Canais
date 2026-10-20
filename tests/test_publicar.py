"""A ajuda para publicar no Studio: achar o projeto da fábrica pelo nome do arquivo e montar o kit, sem rede."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import publicar  # noqa: E402


def _projeto(raiz: Path, nome: str, titulo: str, entrega: str = "", **extra) -> Path:
    pasta = raiz / nome
    pasta.mkdir(parents=True)
    (pasta / "publicacao.json").write_text(json.dumps({"titulo": titulo, "descricao": "Texto\n\nCapítulos\n0:00 A",
                                                       "tags": ["um", "dois"], **extra}), encoding="utf-8")
    if entrega:
        (pasta / "entrega_pc.json").write_text(json.dumps({"video": f"C:\\Users\\x\\Downloads\\{entrega}"}), encoding="utf-8")
    return pasta


def test_normalizar_tira_acento_extensao_e_pontuacao():
    assert publicar.normalizar("Desextinção: Os Animais que Estão Voltando.MP4") == "desextincao os animais que estao voltando"
    assert publicar.normalizar("10-maiores-animais") == "10 maiores animais"


def test_acha_pelo_arquivo_da_entrega_pela_pasta_e_pelo_titulo(tmp_path):
    _projeto(tmp_path, "10-animais-extintos", "Desextinção: Os Animais", entrega="Desextinção Os Animais.mp4")
    _projeto(tmp_path, "gatos-incomuns-do-planeta", "Os 10 gatos mais incomuns")
    assert publicar.achar(tmp_path, "Desextinção Os Animais.mp4") == "10-animais-extintos"
    assert publicar.achar(tmp_path, "gatos-incomuns-do-planeta.mp4") == "gatos-incomuns-do-planeta"
    assert publicar.achar(tmp_path, "Os 10 gatos mais incomuns.mov") == "gatos-incomuns-do-planeta"
    # o nome cortado pelo Windows ou com algo a mais ainda acha
    assert publicar.achar(tmp_path, "Os 10 gatos mais incomuns (1).mp4") == "gatos-incomuns-do-planeta"


def test_nao_chuta_quando_o_nome_nao_diz(tmp_path):
    _projeto(tmp_path, "um-video-qualquer", "Um vídeo qualquer")
    assert publicar.achar(tmp_path, "final.mp4") is None
    assert publicar.achar(tmp_path, "outra coisa sem relacao.mp4") is None
    assert publicar.achar(tmp_path / "nao-existe", "Um vídeo qualquer.mp4") is None
    assert [o["nome"] for o in publicar.opcoes(tmp_path)] == ["um-video-qualquer"]


def test_kit_com_sintetico_legenda_e_duracao(tmp_path):
    pasta = _projeto(tmp_path, "p", "T", sintetico=True, legenda="legendas_final.srt", comentario_fixado="Qual?",
                     capitulos=[{"inicio": 0, "tempo": "0:00", "nome": "A"}, {"inicio": 64.6, "tempo": "1:04", "nome": "B"}])
    (pasta / "alinhamento.json").write_text(json.dumps({"duracao": 612.5}), encoding="utf-8")
    k = publicar.kit(pasta)
    assert (k["titulo"], k["tags"], k["sintetico"], k["legenda"], k["duracao"]) == ("T", ["um", "dois"], True, "legendas_final.srt", 612.5)
    assert k["capitulos"][1] == {"tempo": "1:04", "nome": "B", "inicio": 64.6}
    assert k["comentario_fixado"] == "Qual?"


def test_kit_antigo_so_com_textos(tmp_path):
    pasta = tmp_path / "velho"
    pasta.mkdir()
    (pasta / "publicacao.json").write_text(json.dumps({"textos": {"titulo": "Velho", "resumo": "R", "tags": ["a"]}}), encoding="utf-8")
    k = publicar.kit(pasta)
    assert (k["titulo"], k["descricao"], k["tags"], k["sintetico"], k["duracao"]) == ("Velho", "R", ["a"], False, None)
