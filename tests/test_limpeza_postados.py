"""Limpeza depois da postagem: 48 h depois de postado saem os pesados, fica o registro."""
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, limpeza_postados, roteiro_claude  # noqa: E402

HORA = 3600


@pytest.fixture
def amb(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    monkeypatch.setattr(roteiro_claude, "FABRICA", tmp_path / "fabrica")
    monkeypatch.setattr(limpeza_postados, "_downloads", lambda: tmp_path / "Downloads")
    (tmp_path / "fabrica" / "projetos").mkdir(parents=True)
    (tmp_path / "Downloads").mkdir()
    yield tmp_path
    banco._CON.close()
    banco._CON = None


def _envelhecer(pasta: Path, segundos: float):
    t = time.time() - segundos
    for f in pasta.rglob("*"):
        os.utime(f, (t, t))


def _projeto(tmp: Path, nome: str, idade_h: float = 100) -> Path:
    p = tmp / "fabrica" / "projetos" / nome
    for sub in ("imagens", "render", "shorts", "thumbs"):
        (p / sub).mkdir(parents=True)
        (p / sub / "a.bin").write_bytes(b"x" * 1000)
    (p / "final.mp4").write_bytes(b"v" * 5000)
    (p / "narracao.wav").write_bytes(b"w" * 2000)
    (p / "roteiro.txt").write_text("roteiro", encoding="utf-8")
    (p / "criacao.json").write_text(json.dumps({"status": "concluido"}), encoding="utf-8")
    entrega = tmp / "Downloads" / "Canal" / f"Titulo__{nome}_ENTREGA"
    entrega.mkdir(parents=True)
    (entrega / "Titulo.mp4").write_bytes(b"v" * 5000)
    (p / "entrega_pc.json").write_text(json.dumps({"pasta": str(entrega)}), encoding="utf-8")
    _envelhecer(p, idade_h * HORA)
    return p


def _postar(nome: str, ha_h: float):
    quando = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - ha_h * HORA))
    banco.executar("INSERT INTO resultado_postado (usuario_id, projeto, item, quando) VALUES (1,?,?,?)", nome, "video", quando)


def test_limpa_postado_ha_mais_de_48h_e_guarda_o_registro(amb):
    p = _projeto(amb, "velho")
    _postar("velho", 50)
    entrega = Path(json.loads((p / "entrega_pc.json").read_text(encoding="utf-8"))["pasta"])
    assert limpeza_postados.limpar(log=lambda *_: None) > 0
    assert not (p / "final.mp4").exists() and not (p / "narracao.wav").exists()
    assert not (p / "imagens").exists() and not (p / "render").exists() and not (p / "shorts").exists()
    assert not entrega.exists() and entrega.parent.exists()
    assert (p / "roteiro.txt").exists() and (p / "thumbs").exists() and (p / "criacao.json").exists()
    assert limpeza_postados.limpo("velho")
    assert limpeza_postados.candidatos() == []


def test_espera_as_48h(amb):
    _projeto(amb, "novo")
    _postar("novo", 10)
    assert limpeza_postados.candidatos() == []


def test_nao_postado_fica(amb):
    _projeto(amb, "solto")
    assert limpeza_postados.candidatos() == []


def test_renderizado_de_novo_depois_de_postado_fica(amb):
    p = _projeto(amb, "refeito")
    _postar("refeito", 50)
    t = time.time() - 5 * HORA
    os.utime(p / "final.mp4", (t, t))
    assert limpeza_postados.candidatos() == []


def test_render_em_andamento_fica(amb):
    p = _projeto(amb, "rendendo")
    _postar("rendendo", 50)
    (p / "render_andamento.json").write_text("{}", encoding="utf-8")
    _envelhecer(p, 100 * HORA)
    assert limpeza_postados.candidatos() == []


def test_entrega_fora_de_downloads_nao_sai(amb, tmp_path):
    p = _projeto(amb, "fora")
    _postar("fora", 50)
    outra = tmp_path / "Outro" / "x_ENTREGA"
    outra.mkdir(parents=True)
    (p / "entrega_pc.json").write_text(json.dumps({"pasta": str(outra)}), encoding="utf-8")
    _envelhecer(p, 100 * HORA)
    limpeza_postados.limpar(log=lambda *_: None)
    assert outra.exists()


def test_link_colado_sem_hora_usa_o_final(amb):
    _projeto(amb, "link", idade_h=100)
    banco.executar("INSERT INTO resultado_publicado (usuario_id, projeto, video_id) VALUES (1,'link','abcdefghijk')")
    assert [p.name for p in limpeza_postados.candidatos()] == ["link"]


def test_simular_nao_apaga(amb):
    p = _projeto(amb, "sim")
    _postar("sim", 50)
    assert limpeza_postados.limpar(log=lambda *_: None, simular=True) > 0
    assert (p / "final.mp4").exists()
