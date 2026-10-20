"""O Diagnóstico do Acompanhar: de onde vieram as cenas, as etapas e o log, sem rede."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import diagnostico  # noqa: E402


def test_origem_da_cena():
    assert diagnostico.origem_da_cena({"midia": {"fonte": "pexels"}}) == "real"
    assert diagnostico.origem_da_cena({"midia": {"fonte": "animation_ai"}}) == "animacao"
    assert diagnostico.origem_da_cena({"tipo": "video_real", "sem_midia_real": True}) == "imagem_ia"
    assert diagnostico.origem_da_cena({"tipo": "ia"}) == "imagem_ia"
    assert diagnostico.origem_da_cena({"tipo": "video_real"}) == "pendente"


def test_banco_desconhecido_conta_como_real():
    # os projetos reais têm "smithsonian", que não estava na lista: material com fonte é sempre filmagem/foto real
    assert diagnostico.origem_da_cena({"midia": {"fonte": "smithsonian"}, "tipo": "video_real"}) == "real"


def test_contagem(tmp_path):
    cenas = [{"midia": {"fonte": "pexels"}}] * 6 + [{"tipo": "ia"}] * 3 + [{"midia": {"fonte": "animation_ai"}}] \
        + [{"tipo": "video_real"}] * 2
    (tmp_path / "cenas.json").write_text(json.dumps({"cenas": cenas}), encoding="utf-8")
    assert diagnostico.contagem(tmp_path) == {"total": 12, "real": 6, "imagem_ia": 3, "animacao": 1, "pendente": 2, "pct_ia": 40.0}


def test_arquivos_ausentes_ou_quebrados(tmp_path):
    assert diagnostico.contagem(tmp_path)["total"] == 0
    (tmp_path / "criacao.json").write_text('{"logs": ["a"', encoding="utf-8")
    assert diagnostico.log(tmp_path) == []
    assert [e["estado"] for e in diagnostico.etapas(tmp_path, {})["lista"]] == ["falta"] * 6


def test_log_filtra(tmp_path):
    logs = ["narração pronta", "aviso: cota", "erro ao baixar", "lendo"]
    (tmp_path / "criacao.json").write_text(json.dumps({"logs": logs}), encoding="utf-8")
    assert [l["tipo"] for l in diagnostico.log(tmp_path)] == ["concluido", "aviso", "erro", "info"]
    assert len(diagnostico.log(tmp_path, "erro")) == 1


def test_erro_contornado_e_aviso(tmp_path):
    # a fábrica escreve "(erro 429)" quando tenta outro caminho e segue: isso é aviso, não parada
    logs = ["o Gemini não descreveu (erro 429): seguindo com a cadeia de visão", "falhou ao renderizar a cena 12"]
    (tmp_path / "criacao.json").write_text(json.dumps({"logs": logs}), encoding="utf-8")
    assert [l["tipo"] for l in diagnostico.log(tmp_path)] == ["aviso", "erro"]


def test_etapas_feitas_agora_e_tempos(tmp_path):
    criacao = {"feitas": ["mapa", "narracao", "cenas"], "etapa": "midia",
               "logs": ["  Tempo por etapa: JSON de cenas 18min14s; Narração 3min18s; Mapa do roteiro 2min40s; Divisão de cenas 10s"]}
    (tmp_path / "criacao.json").write_text(json.dumps(criacao), encoding="utf-8")
    e = diagnostico.etapas(tmp_path, {"etapa": "midia", "passo_atual": 4, "total_passos": 6, "mensagem": "buscando"})
    assert [x["estado"] for x in e["lista"]] == ["feita", "feita", "feita", "agora", "falta", "falta"]
    assert [x["tempo"] for x in e["lista"][:3]] == ["2min40s", "3min18s", "18min24s"]
    assert (e["mensagem"], e["passo"], e["total"]) == ("buscando", 4, 6)


def test_blocos_cada_video_num_bloco_so():
    fila_itens = [{"id": 1, "estado": "produzindo", "projeto": "p1", "pedido": {"titulo": "A"}},
                  {"id": 2, "estado": "sua_vez", "projeto": "", "pedido": {"titulo": "B"}},
                  {"id": 3, "estado": "na_fila", "projeto": "", "pedido": {"titulo": "C"}},
                  {"id": 4, "estado": "entrada", "projeto": "", "pedido": {"titulo": "D"}},
                  {"id": 5, "estado": "erro", "projeto": "", "pedido": {"titulo": "E"}},
                  {"id": 6, "estado": "escrevendo", "projeto": "", "pedido": {"titulo": "F"}},
                  {"id": 7, "estado": "entregue", "projeto": "p8", "pedido": {"titulo": "G"}}]
    prod = {"andamento": [{"nome": "p1", "rodando": True, "progresso": 40, "titulo": "A"},
                          {"nome": "p9", "precisa_voce": True, "titulo": "Z"},
                          {"nome": "p7", "titulo": "Y"}], "prontos": [{"nome": "p8"}]}
    b = diagnostico.blocos(fila_itens, prod)
    ids = {k: [x["chave"] for x in b[k]] for k in ("precisa_voce", "produzindo", "na_fila", "entrada", "parados")}
    assert ids == {"precisa_voce": ["fila-2", "fila-5", "p9"], "produzindo": ["fila-1", "fila-6"], "na_fila": ["fila-3"],
                   "entrada": ["fila-4"], "parados": ["p7"]}
    assert b["numeros"] == {"produzindo": 2, "na_fila": 1, "precisa_voce": 3}
    assert b["produzindo"][0]["progresso"] == 40            # o pedido da fila leva o andamento da fábrica
