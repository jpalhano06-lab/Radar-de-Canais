"""A sinopse tem tamanho mínimo por escrita: "de 2 a 4 frases" dava 255 caracteres em coreano e 550 em português."""
import json

from radar import descricao, roteiro_claude


def resposta(sinopse):
    return json.dumps({"sinopse": sinopse, "tags": ["a b"], "hashtags": ["#a"]}, ensure_ascii=False)


def test_o_minimo_vem_da_escrita():
    assert descricao.minimo_da_sinopse("한국의 미래를 이야기합니다 " * 20) == 650
    assert descricao.minimo_da_sinopse("日本の新発明について話します " * 20) == 600
    assert descricao.minimo_da_sinopse("Um vídeo sobre o mercado " * 20) == 800


def test_a_curta_e_pedida_de_novo(monkeypatch):
    pedidos = []
    respostas = [resposta("가" * 200), resposta("나" * 480)]
    monkeypatch.setattr(roteiro_claude, "_claude", lambda s, p, modelo="": pedidos.append(p) or respostas.pop(0))
    dados = descricao.escrever("제목", "한국의 미래를 이야기합니다 " * 20, "coreano")
    assert len(dados["sinopse"]) == 480 and len(pedidos) == 2
    assert "pelo menos 650" in pedidos[0] and "200 caracteres" in pedidos[1]


def test_a_que_ja_serve_nao_gasta_outra_chamada(monkeypatch):
    pedidos = []
    monkeypatch.setattr(roteiro_claude, "_claude", lambda s, p, modelo="": pedidos.append(p) or resposta("a" * 900))
    descricao.escrever("Título", "Um vídeo sobre o mercado", "português")
    assert len(pedidos) == 1


def test_a_nova_nunca_fica_pior(monkeypatch):
    respostas = [resposta("a" * 300), resposta("b" * 100)]
    monkeypatch.setattr(roteiro_claude, "_claude", lambda s, p, modelo="": respostas.pop(0))
    assert descricao.escrever("Título", "Um vídeo", "português")["sinopse"] == "a" * 300


def test_falha_na_segunda_volta_fica_com_a_primeira(monkeypatch):
    respostas = [resposta("a" * 300)]

    def falso(_s, _p, modelo=""):
        if respostas:
            return respostas.pop(0)
        raise RuntimeError("o Claude não respondeu")
    monkeypatch.setattr(roteiro_claude, "_claude", falso)
    assert descricao.escrever("Título", "Um vídeo", "português")["sinopse"] == "a" * 300


def test_fora_do_portugues_vem_a_traducao_e_os_paragrafos_ficam(monkeypatch):
    texto = "가" * 400 + "\n\n" + "나" * 400
    r = json.dumps({"sinopse": texto, "tags": ["a b"], "hashtags": ["#a"], "titulo_pt": "O futuro da Coreia",
                    "sinopse_pt": "Primeiro.\n\nSegundo."}, ensure_ascii=False)
    monkeypatch.setattr(roteiro_claude, "_claude", lambda s, p, modelo="": r)
    dados = descricao.escrever("제목", "한국의 미래를 이야기합니다 " * 20, "coreano")
    assert dados["sinopse"] == texto                      # a linha em branco entre os parágrafos não some
    assert dados["traducao"] == {"titulo": "O futuro da Coreia", "sinopse": "Primeiro.\n\nSegundo."}


def test_o_titulo_do_radar_ganha_do_da_fabrica(tmp_path):
    from radar import publicar
    (tmp_path / "publicacao.json").write_text(json.dumps({"titulo": "韓国の列車 (한국의 열차)"}), encoding="utf-8")
    (tmp_path / "publicacao_radar.json").write_text(json.dumps({"titulo": "韓国の列車"}), encoding="utf-8")
    assert publicar._titulo(tmp_path) == "韓国の列車"


def test_coreano_e_japones_tem_modelo_na_lingua():
    from radar import publicar
    assert "안내" in publicar.rodape_padrao("coreano", "geral", "Canal")
    assert "ご案内" in publicar.rodape_padrao("japonês", "geral", "Canal")
