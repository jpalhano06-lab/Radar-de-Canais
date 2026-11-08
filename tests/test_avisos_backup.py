"""O backup não leva segredo, e cada aviso aparece só quando deve."""
import gzip
import json
import shutil
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest

from radar import avisos, backup, banco


@pytest.fixture
def base(tmp_path, monkeypatch):
    arquivo = tmp_path / "radar.db"
    c = sqlite3.connect(arquivo)
    c.executescript("""CREATE TABLE studio (canal_id TEXT, refresh_token TEXT, access_token TEXT);
        INSERT INTO studio VALUES ('UC1', 'segredo-r', 'segredo-a');
        CREATE TABLE sessoes (token_hash TEXT); INSERT INTO sessoes VALUES ('h');
        CREATE TABLE videos (id TEXT); INSERT INTO videos VALUES ('v1');""")
    c.commit()
    c.close()
    monkeypatch.setattr(banco, "ARQUIVO", arquivo)
    return tmp_path


def test_o_banco_copiado_nao_leva_segredo(base):
    destino = base / "radar-2026-11-06.db.gz"
    backup._copiar_banco(destino)
    aberto = base / "aberto.db"
    with gzip.open(destino) as f, open(aberto, "wb") as saida:
        shutil.copyfileobj(f, saida)
    assert not (base / "radar-2026-11-06.db").exists()
    c = sqlite3.connect(aberto)
    assert c.execute("select refresh_token, access_token from studio").fetchone() == ("", "")
    assert c.execute("select count(*) from sessoes").fetchone()[0] == 0
    assert c.execute("select count(*) from videos").fetchone()[0] == 1
    c.close()
    original = sqlite3.connect(banco.ARQUIVO)
    assert original.execute("select refresh_token from studio").fetchone()[0] == "segredo-r"
    original.close()


def test_guarda_so_as_ultimas(tmp_path):
    for i in range(1, 10):
        (tmp_path / f"radar-2026-11-0{i}.db.gz").write_bytes(b"x")
    backup._limpar(tmp_path)
    sobrou = sorted(p.name for p in tmp_path.glob("radar-*"))
    assert len(sobrou) == backup.MANTER and sobrou[0] == "radar-2026-11-03.db.gz"


def falso_ultimo(monkeypatch, **dados):
    monkeypatch.setattr(backup, "ultimo", lambda: dados)


def test_na_hora(monkeypatch):
    falso_ultimo(monkeypatch)
    assert backup.na_hora()
    agora = datetime.now(timezone.utc)
    falso_ultimo(monkeypatch, quando=agora.isoformat())
    assert not backup.na_hora()
    falso_ultimo(monkeypatch, quando=(agora - timedelta(days=8)).isoformat())
    assert backup.na_hora()
    falso_ultimo(monkeypatch, quando=agora.isoformat(), erro="disco")
    assert backup.na_hora()


def test_aviso_de_copia(monkeypatch):
    falso_ultimo(monkeypatch, quando=datetime.now(timezone.utc).isoformat())
    assert avisos.copia() == []
    falso_ultimo(monkeypatch, quando=datetime.now(timezone.utc).isoformat(), erro="sem espaço")
    assert avisos.copia()[0]["nivel"] == "erro"
    falso_ultimo(monkeypatch)
    assert avisos.copia()[0]["chave"] == "backup-velho"


def test_fila_parada_e_demorada(monkeypatch):
    velho = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
    novo = datetime.now(timezone.utc).isoformat()

    def todos(sql, *_a):
        if "estado='erro'" in sql:
            return [{"id": 76, "projeto": "p", "erro": "sem imagem"}]
        return [{"id": 77, "criado": velho}, {"id": 78, "criado": novo}]
    monkeypatch.setattr(avisos.banco, "todos", todos)
    achados = avisos.fila()
    assert [a["chave"] for a in achados] == ["fila-erro-76", "fila-lenta-77"]


def test_assinatura_so_avisa_acima_do_limite_e_antes_de_voltar(tmp_path, monkeypatch):
    monkeypatch.setattr(avisos.config, "FABRICA", tmp_path)
    futuro = time.time() + 3600
    (tmp_path / "chatgpt_limites.json").write_text(json.dumps({"janelas": {"janela": {"usado_pct": 95, "volta_em": futuro},
                                                                         "semana": {"usado_pct": 10, "volta_em": futuro}}}))
    assert [a["chave"] for a in avisos.assinatura()] == ["assinatura-janela"]
    (tmp_path / "chatgpt_limites.json").write_text(json.dumps({"janelas": {"janela": {"usado_pct": 95, "volta_em": time.time() - 10}}}))
    assert avisos.assinatura() == []


def test_uma_verificacao_quebrada_nao_cala_as_outras(monkeypatch):
    def quebra():
        raise RuntimeError("fora do ar")
    monkeypatch.setattr(avisos, "fila", quebra)
    monkeypatch.setattr(avisos, "qualidade", lambda: [])
    monkeypatch.setattr(avisos, "fabrica", lambda: [])
    monkeypatch.setattr(avisos, "travados", lambda: [])
    monkeypatch.setattr(avisos, "voz", lambda: [])
    monkeypatch.setattr(avisos, "openrouter", lambda: [])
    monkeypatch.setattr(avisos, "assinatura", lambda: [])
    monkeypatch.setattr(avisos, "conexoes", lambda _u: [])
    monkeypatch.setattr(avisos, "copia", lambda: [])
    monkeypatch.setattr(avisos, "disco", lambda: [avisos._aviso("disco", "atencao", "t", "x")])
    assert [a["chave"] for a in avisos.verificar(1)] == ["disco"]


def test_erro_vem_antes_da_atencao(monkeypatch):
    for nome in ("fila", "travados", "qualidade", "fabrica", "voz", "openrouter", "assinatura", "disco"):
        monkeypatch.setattr(avisos, nome, lambda: [])
    monkeypatch.setattr(avisos, "conexoes", lambda _u: [avisos._aviso("a", "atencao", "t", "x")])
    monkeypatch.setattr(avisos, "copia", lambda: [avisos._aviso("b", "erro", "t", "x")])
    assert [a["chave"] for a in avisos.verificar(1)] == ["b", "a"]


def test_celular_nao_repete_o_mesmo_erro(monkeypatch):
    enviados = []
    monkeypatch.setattr(avisos.backup, "na_hora", lambda: False)
    monkeypatch.setattr(avisos, "verificar", lambda _u: [avisos._aviso("x", "erro", "t", "y"), avisos._aviso("z", "atencao", "t", "y")])
    monkeypatch.setattr(avisos, "_no_celular", enviados.append)
    monkeypatch.setattr(avisos, "_enviados", {})
    avisos._uma_volta(1)
    avisos._uma_volta(1)
    assert [a["chave"] for a in enviados] == ["x"]


def test_qualidade_so_avisa_video_ruim_de_verdade(tmp_path, monkeypatch):
    monkeypatch.setattr(avisos.config, "FABRICA", tmp_path)
    monkeypatch.setattr(avisos.banco, "todos", lambda *_a: [{"id": 1, "projeto": "ruim"}, {"id": 2, "projeto": "normal"}, {"id": 3, "projeto": "sem-nota"}])
    for nome, q in (("ruim", {"cenas": 100, "boas_pct": 40, "erradas": list(range(5))}), ("normal", {"cenas": 100, "boas_pct": 54, "erradas": list(range(10))})):
        (tmp_path / "projetos" / nome).mkdir(parents=True)
        (tmp_path / "projetos" / nome / "qualidade.json").write_text(json.dumps({"atual": q}))
    assert [a["chave"] for a in avisos.qualidade()] == ["qualidade-1"]
    assert "1 (40%)" in avisos.qualidade()[0]["texto"]


def test_o_celular_recebe_pelo_ntfy(monkeypatch):
    enviados = []
    monkeypatch.setattr(avisos.config, "AMBIENTE", {"RADAR_NTFY_TOPICO": "radar-x"})
    monkeypatch.setattr(avisos.httpx, "post", lambda url, **k: enviados.append((url, k["json"])))
    avisos._no_celular(avisos._aviso("a", "erro", "Título", "Texto"))
    assert enviados == [("https://ntfy.sh/", {"topic": "radar-x", "title": "Título", "message": "Texto", "priority": 4})]
