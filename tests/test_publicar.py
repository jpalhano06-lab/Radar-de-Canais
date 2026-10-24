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


def test_modelo_do_canal_troca_so_o_que_e_do_video_e_nao_poe_capitulos():
    kit = {"titulo": "15 Poundland Items", "sinopse": "Uma lista do que vale a pena.", "hashtags": ["#a", "#b"],
           "descricao": "A da fábrica", "capitulos": [{"tempo": "0:00", "nome": "Começo"}]}
    texto = publicar.montar_descricao("{titulo}\n\n{sinopse}\n\nSobre o {canal}.\n\n{hashtags}", kit, "UK MARKET")
    assert texto == "15 Poundland Items\n\nUma lista do que vale a pena.\n\nSobre o UK MARKET.\n\n#a #b"
    assert "0:00" not in texto


def test_modelo_vazio_mantem_a_descricao_da_fabrica():
    assert publicar.montar_descricao("", {"descricao": "A da fábrica"}) == "A da fábrica"


def test_campo_que_o_video_nao_tem_nao_deixa_buraco():
    texto = publicar.montar_descricao("{titulo}\n\n{sinopse}\n\nFim", {"titulo": "T"})
    assert texto == "T\n\nFim"


def test_perfil_do_projeto_sai_do_caminho_do_yaml(tmp_path):
    pasta = _projeto(tmp_path, "uk-video", "Um título")
    (pasta / "projeto.json").write_text(json.dumps(
        {"perfil": r"C:\Users\x\fabrica-videos\perfis\canal-uk-market.yaml"}), encoding="utf-8")
    assert publicar.perfil_do_projeto(pasta) == "canal-uk-market"


# ---------------------------------------------------------------- os modelos padrão (2026-10-23)

def test_a_linha_so_de_campo_vazio_sai_inteira():
    """Sem marcas, "incluindo {marcas}." viraria "incluindo ." — a frase pela metade é pior que a falta dela."""
    modelo = "Olá.\nFalamos de marcas como {marcas}.\nFim."
    assert publicar.montar_descricao(modelo, {}, "C", "Aldi, Lidl") == "Olá.\nFalamos de marcas como Aldi, Lidl.\nFim."
    assert publicar.montar_descricao(modelo, {}, "C", "") == "Olá.\nFim."


def test_toda_lingua_tem_os_dois_padroes_e_eles_se_montam():
    kit = {"sinopse": "O resumo.", "hashtags": ["#x"]}
    for lingua, tipos in publicar.MODELOS.items():
        assert set(tipos) == set(publicar.TIPOS), lingua
        for tipo in tipos:
            texto = publicar.montar_descricao(publicar.modelo_padrao(lingua, tipo), kit, "Canal X", "Aldi")
            assert "{" not in texto, (lingua, tipo)     # nenhum campo sobrou sem troca
            assert "Canal X" in texto and "O resumo." in texto
            assert len(texto) <= 5000


def test_o_padrao_do_consumo_leva_o_aviso_inteiro():
    """É o texto que o usuário usa de verdade: o aviso legal não pode encolher sem alguém pedir."""
    texto = publicar.modelo_padrao("inglês", "consumo")
    for pedaco in ("educational and informational purposes only", "does not allege illegal or unlawful conduct",
                   "medical, legal or professional advice", "may change over time"):
        assert pedaco in texto, pedaco


def test_lingua_que_nao_existe_cai_no_ingles():
    assert publicar.modelo_padrao("alemão", "geral") == publicar.MODELOS["inglês"]["geral"]
    assert publicar.modelo_padrao("", "geral") == publicar.MODELOS["inglês"]["geral"]


def test_tipo_que_nao_existe_cai_no_geral():
    assert publicar.modelo_padrao("português", "inventado") == publicar.MODELOS["português"]["geral"]
