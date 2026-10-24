"""O ajuste do tempo do vídeo: medir o que o vídeo deu e dimensionar o próximo pedido, sem rede e sem fábrica."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import roteiro_claude, tempo  # noqa: E402


def _mundo(monkeypatch, tmp_path):
    """Uma pasta de roteiros e uma de projetos da fábrica, com a API da fábrica desligada."""
    roteiros, fabrica = tmp_path / "roteiros", tmp_path / "fabrica"
    (roteiros).mkdir()
    (fabrica / "projetos").mkdir(parents=True)
    monkeypatch.setattr(roteiro_claude, "PASTA", roteiros)
    monkeypatch.setattr(roteiro_claude, "FABRICA", fabrica)
    monkeypatch.setattr(tempo, "_da_api", lambda: {})
    return roteiros, fabrica


def _roteiro(roteiros, nome, *, minutos, palavras, ppm_usado, projeto, perfil="canal-x", lingua="inglês"):
    pasta = roteiros / nome
    pasta.mkdir()
    (pasta / "roteiro.json").write_text(json.dumps({
        "titulo": nome, "minutos": minutos, "palavras": palavras, "lingua": lingua, "usuario_id": 1,
        "ritmo": {"ppm": ppm_usado}, "fabrica": {"projeto": projeto, "perfil": perfil, "palavras": palavras},
    }), encoding="utf-8")
    return pasta


def _projeto(fabrica, nome, segundos, abertura=0.0):
    pasta = fabrica / "projetos" / nome
    (pasta / "render").mkdir(parents=True)
    (pasta / "alinhamento.json").write_text(json.dumps({"duracao": segundos}), encoding="utf-8")
    (pasta / "render" / "linha.json").write_text(json.dumps({"atraso": abertura}), encoding="utf-8")


def test_mede_do_disco_somando_a_abertura_mesmo_com_a_fabrica_desligada(monkeypatch, tmp_path):
    roteiros, fabrica = _mundo(monkeypatch, tmp_path)
    _roteiro(roteiros, "2026-10-20-a", minutos=15, palavras=3000, ppm_usado=200, projeto="p1")
    _projeto(fabrica, "p1", 900.0, abertura=60.0)   # 15 min de narração + 1 min de abertura = 16 min de vídeo
    (m,) = tempo.medicoes(1)
    assert (m["entregue_min"], m["erro_min"], m["dentro"]) == (16.0, 1.0, True)


def test_erro_acima_de_um_minuto_e_meio_conta_como_fora(monkeypatch, tmp_path):
    roteiros, fabrica = _mundo(monkeypatch, tmp_path)
    _roteiro(roteiros, "2026-10-20-a", minutos=15, palavras=3800, ppm_usado=200, projeto="p1")
    _projeto(fabrica, "p1", 1140.0)                 # 19 min: 4 a mais do que os 15 pedidos
    r = tempo.ritmo(1, "canal-x", "inglês")
    assert r["acerto"]["dentro"] == 0 and r["acerto"]["total"] == 1
    assert r["acerto"]["erro_medio"] == 4.0


def test_o_proximo_pedido_desconta_o_que_o_claude_escreveu_a_mais(monkeypatch, tmp_path):
    """Pediu 3.000 palavras, o Claude escreveu 3.600 e o vídeo saiu com 19 min: o ppm_alvo encolhe o próximo pedido."""
    roteiros, fabrica = _mundo(monkeypatch, tmp_path)
    _roteiro(roteiros, "2026-10-20-a", minutos=15, palavras=3600, ppm_usado=200, projeto="p1")
    _projeto(fabrica, "p1", 1140.0)
    r = tempo.ritmo(1, "canal-x", "inglês")
    assert r["ppm"] == 189          # o ritmo real da voz: 3.600 palavras em 19 min
    assert r["ppm_alvo"] == 158     # o que mandar pedir: as 3.000 pedidas em 19 min
    assert 15 * r["ppm_alvo"] < 15 * r["ppm"]


def test_o_que_deu_fica_guardado_no_roteiro(monkeypatch, tmp_path):
    roteiros, fabrica = _mundo(monkeypatch, tmp_path)
    pasta = _roteiro(roteiros, "2026-10-20-a", minutos=10, palavras=2000, ppm_usado=200, projeto="p1")
    _projeto(fabrica, "p1", 660.0)
    tempo.medicoes(1)
    guardado = json.loads((pasta / "roteiro.json").read_text(encoding="utf-8"))["medido"]
    assert (guardado["entregue_min"], guardado["erro_min"]) == (11.0, 1.0)


def test_sem_video_entregue_usa_o_padrao(monkeypatch, tmp_path):
    roteiros, _ = _mundo(monkeypatch, tmp_path)
    _roteiro(roteiros, "2026-10-20-a", minutos=10, palavras=2000, ppm_usado=200, projeto="")
    r = tempo.ritmo(1, "canal-x", "inglês")
    assert (r["ppm"], r["ppm_alvo"], r["medidos"]) == (tempo.PADRAO, tempo.PADRAO, 0)
