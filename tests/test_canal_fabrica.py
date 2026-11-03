"""Escolher a voz do canal numa fábrica sem a rota /api/canais: o Radar escreve o perfil (sem rede).

Desde 2026-10-28 as vozes são as grátis da fábrica (VoiceStudio e voicebox, provedor local), não a GenAI Pro."""
import pytest

from radar import fabrica_api, roteiro_claude
from radar.producao import _perfil, salvar_rodape, rodape_do_perfil


@pytest.fixture
def fabrica(tmp_path, monkeypatch):
    (tmp_path / "perfis").mkdir()
    monkeypatch.setattr(roteiro_claude, "FABRICA", tmp_path)

    def sem_rota(*a, **k):
        raise fabrica_api.SemFabrica("Method Not Allowed", 405)
    monkeypatch.setattr(fabrica_api, "_pedir", sem_rota)
    return tmp_path


VOZ = {"voice_id": "omnivoice:community_pt_br_lucas", "nome": "Lucas", "idioma": "pt"}


def test_cria_o_perfil_herdando_do_documentario(fabrica):
    perfil = fabrica_api.criar_canal("Canal do Márcos", VOZ)
    assert perfil == "canal-canal-do-marcos"
    texto = (fabrica / "perfis" / f"{perfil}.yaml").read_text(encoding="utf-8")
    assert "base: documentario.yaml" in texto and "provedor: local" in texto
    assert 'voz_local: "omnivoice:community_pt_br_lucas"' in texto
    assert "\n  idioma: pt\n" in texto  # a fábrica narra e confere a voz por este campo
    lido = _perfil(perfil)
    assert (lido["canal"], lido["voz"], lido["idioma_da_voz"], lido["provedor"]) == ("Canal do Márcos", "Lucas", "pt", "local")


def test_voz_com_virgula_e_espaco(fabrica):
    # as vozes desenhadas do OmniVoice têm vírgula e espaço no código: vão entre aspas no yaml
    perfil = fabrica_api.criar_canal("Canal Y", {"voice_id": "omnivoice:male, middle-aged, low pitch",
                                                 "nome": "male, middle-aged, low pitch", "idioma": "en"})
    texto = (fabrica / "perfis" / f"{perfil}.yaml").read_text(encoding="utf-8")
    assert 'voz_local: "omnivoice:male, middle-aged, low pitch"' in texto and "\n  idioma: en\n" in texto


def test_trocar_a_voz_mantem_o_rodape(fabrica):
    perfil = fabrica_api.criar_canal("Canal X", VOZ)
    salvar_rodape(perfil, "Inscreva-se!")
    fabrica_api.criar_canal("Canal X", VOZ | {"voice_id": "kokoro:pm_santa", "nome": "Santa"})
    texto = (fabrica / "perfis" / f"{perfil}.yaml").read_text(encoding="utf-8")
    assert texto.count("\nvoz:") == 1 and "kokoro:pm_santa" in texto and "community_pt_br_lucas" not in texto
    assert rodape_do_perfil(perfil) == "Inscreva-se!"


def test_codigo_invalido_e_recusado(fabrica):
    for codigo in ("", "abc123XYZ", 'kokoro:pm_alex"\nbase: outro.yaml'):
        with pytest.raises(fabrica_api.SemFabrica):
            fabrica_api.criar_canal("Canal X", VOZ | {"voice_id": codigo})


def test_outro_erro_da_fabrica_continua_aparecendo(fabrica, monkeypatch):
    def quebrada(*a, **k):
        raise fabrica_api.SemFabrica("Erro 500 da fábrica.", 500)
    monkeypatch.setattr(fabrica_api, "_pedir", quebrada)
    with pytest.raises(fabrica_api.SemFabrica):
        fabrica_api.criar_canal("Canal X", VOZ)


def test_lista_poe_as_nativas_da_lingua_primeiro(monkeypatch):
    catalogo = [
        {"id": "omnivoice:male, elderly", "motor": "omnivoice", "origem": "VoiceStudio", "tipo": "desenhada", "idioma": ""},
        {"id": "qwen:Ryan", "motor": "qwen", "origem": "voicebox", "tipo": "pronta", "idioma": ""},
        {"id": "kokoro:pm_alex", "motor": "kokoro", "origem": "voicebox", "tipo": "pronta", "idioma": "pt"},
        {"id": "omnivoice:community_pt_br_lucas", "motor": "omnivoice", "origem": "VoiceStudio", "tipo": "gravada", "idioma": "pt"},
    ]
    pedidos = []

    def fabrica_falsa(metodo, caminho, *a, **k):
        pedidos.append(caminho)
        return {"vozes": catalogo, "total": len(catalogo)}
    monkeypatch.setattr(fabrica_api, "_pedir", fabrica_falsa)
    r = fabrica_api.vozes("português")
    assert pedidos[0].startswith("/api/vozes/local?") and "idioma=pt" in pedidos[0]
    assert [v["voice_id"] for v in r["vozes"]] == ["omnivoice:community_pt_br_lucas", "kokoro:pm_alex", "qwen:Ryan",
                                                   "omnivoice:male, elderly"]
    assert r["vozes"][0]["previa"].startswith("/api/fabrica/vozes/previa?voz=omnivoice%3Acommunity_pt_br_lucas")
