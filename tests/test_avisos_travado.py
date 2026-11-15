"""O pedido que a fábrica tenta de novo sem sair do lugar, e o saldo da voz acabando, chegam como aviso."""
import json

from radar import avisos, banco, config, fabrica_api


def _fila(monkeypatch, tmp_path, logs, mensagem=""):
    projeto = tmp_path / "projetos" / "p1"
    projeto.mkdir(parents=True)
    (projeto / "criacao.json").write_text(json.dumps({"logs": logs, "mensagem": mensagem, "concluido": False}), encoding="utf-8")
    monkeypatch.setattr(config, "FABRICA", tmp_path)
    monkeypatch.setattr(banco, "todos", lambda sql, *a: [{"id": 83, "projeto": "p1"}])


def test_sem_saldo_avisa_na_hora(monkeypatch, tmp_path):
    _fila(monkeypatch, tmp_path, ["Narração: A GenAIPro recusou o pedido (400). Not enough credit",
                                  "tentando de novo em 300s, de onde parou (tentativa 2)"])
    [a] = avisos.travados()
    assert a["nivel"] == "erro" and "saldo da GenAIPro" in a["titulo"] and "segue sozinho" in a["texto"]


def test_mesma_falha_que_volta_avisa(monkeypatch, tmp_path):
    _fila(monkeypatch, tmp_path, ["Imagens: o provedor falhou", "tentando de novo em 300s (tentativa 4)"])
    [a] = avisos.travados()
    assert "tentando de novo" in a["titulo"] and "tentativa 4" in a["texto"]


def test_uma_tentativa_so_nao_avisa(monkeypatch, tmp_path):
    _fila(monkeypatch, tmp_path, ["Imagens: o provedor falhou", "tentando de novo em 30s (tentativa 1)"])
    assert avisos.travados() == []


def test_voz_acabando(monkeypatch):
    monkeypatch.setattr(banco, "um", lambda sql, *a: {"x": 1})
    monkeypatch.setattr(fabrica_api, "_pedir", lambda *a, **k: {"configurada": True, "creditos": 671, "minutos_de_narracao": 11})
    [a] = avisos.voz()
    assert a["nivel"] == "atencao" and "671 créditos, uns 11 min" in a["texto"]
    monkeypatch.setattr(fabrica_api, "_pedir", lambda *a, **k: {"configurada": True, "creditos": 90000, "minutos_de_narracao": 70})
    assert avisos.voz() == []


def test_fabrica_parada_esperando_alguem_avisa(monkeypatch, tmp_path):
    projeto = tmp_path / "projetos" / "p1"
    projeto.mkdir(parents=True)
    (projeto / "criacao.json").write_text(json.dumps({"logs": [], "precisa_voce": True, "concluido": False,
                                                      "mensagem": "Nem os bancos nem a imagem de IA entregaram a cena 5"}), encoding="utf-8")
    monkeypatch.setattr(config, "FABRICA", tmp_path)
    monkeypatch.setattr(banco, "todos", lambda sql, *a: [{"id": 9, "projeto": "p1"}])
    [a] = avisos.travados()
    assert a["chave"] == "parado-9" and "cena 5" in a["texto"]


def test_celular_so_recebe_video_parado():
    for chave in ("fila-erro-3", "parado-9", "travado-9", "travado-saldo-9"):
        assert avisos.vai_ao_celular(avisos._aviso(chave, "erro", "t", "x"))
    for chave, nivel in (("qualidade-80", "atencao"), ("genaipro-saldo", "erro"), ("fila-lenta-3", "atencao"),
                         ("fabrica-fora", "erro"), ("backup-erro", "erro"), ("openrouter-limite", "erro"), ("disco", "atencao")):
        assert not avisos.vai_ao_celular(avisos._aviso(chave, nivel, "t", "x"))


def _na_etapa(monkeypatch, tmp_path, etapa, relogio, pct=88, logs=(), certas=0):
    projeto = tmp_path / "projetos" / "p1"
    projeto.mkdir(parents=True, exist_ok=True)
    (projeto / "criacao.json").write_text(json.dumps({"logs": list(logs), "concluido": False, "etapa": etapa,
                                                      "progresso_pct": pct, "mensagem": "Gerando as imagens de IA"}),
                                          encoding="utf-8")
    (projeto / "chamadas.jsonl").write_text("".join('{"tipo": "imagem", "ok": true}\n' for _ in range(certas)),
                                            encoding="utf-8")
    monkeypatch.setattr(config, "FABRICA", tmp_path)
    monkeypatch.setattr(banco, "todos", lambda sql, *a: [{"id": 7, "projeto": "p1"}])
    monkeypatch.setattr(avisos.time, "time", lambda: relogio)
    return avisos.travados()


def test_vinte_minutos_sem_andar_avisa_no_celular(monkeypatch, tmp_path):
    monkeypatch.setattr(avisos, "_etapas", {})
    assert _na_etapa(monkeypatch, tmp_path, "imagens", 0) == []
    assert _na_etapa(monkeypatch, tmp_path, "imagens", 19 * 60) == []
    [a] = _na_etapa(monkeypatch, tmp_path, "imagens", 25 * 60)
    assert a["chave"] == "travado-etapa-7-imagens" and "25 min parado na etapa imagens" in a["titulo"]
    assert "Gerando as imagens" in a["texto"] and avisos.vai_ao_celular(a)


def test_etapa_nova_zera_o_relogio(monkeypatch, tmp_path):
    monkeypatch.setattr(avisos, "_etapas", {})
    _na_etapa(monkeypatch, tmp_path, "narracao", 0)
    assert _na_etapa(monkeypatch, tmp_path, "imagens", 50 * 60) == []
    assert _na_etapa(monkeypatch, tmp_path, "imagens", 65 * 60) == []
    [a] = _na_etapa(monkeypatch, tmp_path, "imagens", 71 * 60)
    assert a["chave"] == "travado-etapa-7-imagens"


def test_imagem_saindo_na_mesma_etapa_nao_e_parado(monkeypatch, tmp_path):
    """Etapa longa (200 imagens em 40 min) com a porcentagem parada: cada imagem certa zera o relógio."""
    monkeypatch.setattr(avisos, "_etapas", {})
    for minuto in range(0, 60, 10):
        assert _na_etapa(monkeypatch, tmp_path, "imagens", minuto * 60, certas=minuto) == []


def test_tentando_de_novo_nao_conta_como_andar(monkeypatch, tmp_path):
    monkeypatch.setattr(avisos, "_etapas", {})
    _na_etapa(monkeypatch, tmp_path, "imagens", 0, logs=["Imagens: falhou", "tentando de novo em 300s (tentativa 1)"])
    [a] = _na_etapa(monkeypatch, tmp_path, "imagens", 21 * 60,
                    logs=["Imagens: falhou", "tentando de novo em 300s (tentativa 2)"])
    assert a["chave"] == "travado-etapa-7-imagens"


def test_video_parado_repete_de_10_em_10_min(monkeypatch):
    aviso = avisos._aviso("travado-etapa-7-imagens", "erro", "t", "x")
    mandados = []
    monkeypatch.setattr(avisos, "verificar", lambda u: [aviso])
    monkeypatch.setattr(avisos, "_no_celular", lambda a: mandados.append(relogio[0]))
    monkeypatch.setattr(avisos.backup, "na_hora", lambda: False)
    from radar import producao
    monkeypatch.setattr(producao, "aplicar_regra", lambda: [])   # nunca mexer nos perfis de verdade num teste
    monkeypatch.setattr(avisos, "_enviados", {})
    relogio = [0.0]
    monkeypatch.setattr(avisos.time, "time", lambda: relogio[0])
    for minuto in range(1000, 1041, 5):    # uma volta a cada 5 min
        relogio[0] = minuto * 60.0
        avisos._uma_volta(1)
    assert [m / 60 for m in mandados] == [1000, 1010, 1020, 1030, 1040]


def test_pedido_com_erro_na_fila_nao_repete_de_10_em_10():
    assert avisos._intervalo(avisos._aviso("fila-erro-3", "erro", "t", "x")) == 12 * 3600


def test_pedido_que_saiu_da_fila_some_do_relogio(monkeypatch, tmp_path):
    monkeypatch.setattr(avisos, "_etapas", {99: ("imagens", 0)})
    _na_etapa(monkeypatch, tmp_path, "imagens", 0)
    assert 99 not in avisos._etapas and 7 in avisos._etapas
