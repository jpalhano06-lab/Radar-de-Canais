"""O botão Postar do Meu dia (2026-11-15): o Radar acha o vídeo pronto da fábrica pelo título."""
import json

from radar import roteiro_claude, servidor

# um mp4 inteiro de verdade, só com as caixas (o Radar não chama de pronto um arquivo cortado no meio)
MP4 = (16).to_bytes(4, "big") + b"ftypisom" + bytes(4) + (8).to_bytes(4, "big") + b"moov"


def _projeto(raiz, nome, titulo, com_video=True, entrega=None):
    pasta = raiz / "projetos" / nome
    pasta.mkdir(parents=True)
    (pasta / "publicacao_radar.json").write_text(json.dumps({"titulo": titulo}), encoding="utf-8")
    if com_video:
        (pasta / "final.mp4").write_bytes(MP4)
    if entrega:
        (pasta / "entrega_pc.json").write_text(json.dumps({"video": str(entrega)}), encoding="utf-8")
    return pasta


def test_acha_o_video_pronto_pelo_titulo(tmp_path, monkeypatch):
    monkeypatch.setattr(roteiro_claude, "FABRICA", tmp_path)
    _projeto(tmp_path, "uk-retail", "12 Huge UK Retailers Are Closing Stores")
    r = servidor.ext_postar(titulo="12 Huge UK Retailers Are Closing Stores", u={})
    assert r["nome"] == "uk-retail" and r["pronto"] and r["tamanho"] == len(MP4)


def test_sem_video_ainda_nao_esta_pronto(tmp_path, monkeypatch):
    monkeypatch.setattr(roteiro_claude, "FABRICA", tmp_path)
    _projeto(tmp_path, "kr-earbuds", "한국의 45,000원짜리 이어폰이 애플 에어팟의 제국을 무너뜨렸다!", com_video=False)
    r = servidor.ext_postar(titulo="한국의 45,000원짜리 이어폰이 애플 에어팟의 제국을 무너뜨렸다!", u={})
    assert r["nome"] == "kr-earbuds" and not r["pronto"]


def test_titulo_desconhecido_nao_acha_nada(tmp_path, monkeypatch):
    monkeypatch.setattr(roteiro_claude, "FABRICA", tmp_path)
    assert servidor.ext_postar(titulo="um vídeo que não existe na fábrica", u={}) == {"nome": None, "pronto": False}


def test_a_entrega_no_pc_ganha_do_final(tmp_path):
    entrega = tmp_path / "entrega" / "Titulo.mp4"
    entrega.parent.mkdir()
    entrega.write_bytes(MP4)
    pasta = _projeto(tmp_path, "com-entrega", "Um título qualquer comprido", entrega=entrega)
    assert servidor._video_final(pasta) == entrega
    entrega.unlink()                                    # a entrega sumiu: volta ao final.mp4 da pasta
    assert servidor._video_final(pasta) == pasta / "final.mp4"


def test_pedidos_recentes_para_pegar_de_volta(monkeypatch):
    """O Meu dia pega de volta um vídeo tirado sem querer (2026-11-16): a lista dos pedidos recentes da fila."""
    linhas = [{"id": 123, "criado": "2026-11-16T15:00:00+00:00", "estado": "produzindo", "projeto": "as-8-criaturas",
               "pedido": json.dumps({"titulo": "As 8 Criaturas", "canal_id": "UCx", "link": "https://youtu.be/abc"})},
              {"id": 124, "criado": "2026-11-16T16:00:00+00:00", "estado": "na_fila", "projeto": "", "pedido": "{}"}]
    pedidos = []
    monkeypatch.setattr(servidor.banco, "todos", lambda sql, *a: pedidos.append(a) or linhas)
    r = servidor.ext_pedidos_recentes(horas=36, u={"id": 7})
    assert r == {"pedidos": [{"id": 123, "criado": "2026-11-16T15:00:00+00:00", "estado": "produzindo", "projeto": "as-8-criaturas",
                              "titulo": "As 8 Criaturas", "canal_id": "UCx", "link": "https://youtu.be/abc"}]}
    assert pedidos[0][0] == 7
