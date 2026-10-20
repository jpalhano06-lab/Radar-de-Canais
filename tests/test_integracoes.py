"""A aba Integrações: chaves, .env e máscara, sem rede."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import integracoes  # noqa: E402


def test_mascarar():
    assert integracoes.mascarar("sk-or-123456789") == "••••6789"
    assert integracoes.mascarar("") == ""


def test_mesclar_troca_acrescenta_remove_e_mantem_comentarios():
    texto = "# chaves\nA=1\nB=2\nA=velho\n\n# fim\n"
    saida = integracoes.mesclar_env(texto, {"A": "novo", "C": "3", "B": None})
    assert saida.splitlines() == ["# chaves", "A=novo", "", "# fim", "C=3"]


def test_nomes_numerados():
    amb = {"YOUTUBE_API_KEY": "a", "YOUTUBE_API_KEY3": "c", "YOUTUBE_API_KEY2": "b", "GROQ_API_KEY": "g"}
    assert integracoes.nomes_numerados("YOUTUBE_API_KEY", amb) == ["YOUTUBE_API_KEY", "YOUTUBE_API_KEY2", "YOUTUBE_API_KEY3"]
    amb = {"PEXELS_API_KEY10": "x", "PEXELS_API_KEY1": "y", "PEXELS_API_KEY": "z", "PEXELS_API_KEY2": ""}
    assert integracoes.nomes_numerados("PEXELS_API_KEY", amb) == ["PEXELS_API_KEY", "PEXELS_API_KEY1", "PEXELS_API_KEY10"]


def test_gravar_radar_escreve_e_recarrega(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# x\nYOUTUBE_API_KEY=velha\n", encoding="utf-8")
    chamado = []
    monkeypatch.setattr(integracoes.config, "recarregar", lambda: chamado.append(1))
    integracoes.gravar_radar("YOUTUBE_API_KEY2", "nova", arquivo=env)
    assert env.read_text(encoding="utf-8").splitlines() == ["# x", "YOUTUBE_API_KEY=velha", "YOUTUBE_API_KEY2=nova"]
    assert chamado == [1]


def test_estado_sem_fabrica_nao_quebra(monkeypatch):
    def sem(*a, **k):
        raise integracoes.fabrica_api.SemFabrica("desligada")
    monkeypatch.setattr(integracoes.fabrica_api, "_pedir", sem)
    monkeypatch.setattr(integracoes, "_saldo_externo", lambda s: None)
    e = integracoes.estado()
    assert e["fabrica_ligada"] is False
    assert any(s["id"] == "youtube" for s in e["servicos"])


def test_estado_nunca_devolve_a_chave_inteira(monkeypatch):
    monkeypatch.setitem(integracoes.config.AMBIENTE, "YOUTUBE_API_KEY", "AIzaSEGREDO1234")
    monkeypatch.setattr(integracoes.fabrica_api, "_pedir", lambda *a, **k: {"chaves": []})
    monkeypatch.setattr(integracoes, "_saldo_externo", lambda s: None)
    texto = json.dumps(integracoes.estado(), ensure_ascii=False)
    assert "SEGREDO" not in texto and "••••1234" in texto


def test_rota_recusa_quem_vem_pelo_tunel():
    from fastapi.testclient import TestClient
    from radar import servidor
    r = TestClient(servidor.app).get("/api/integracoes", headers={"cf-connecting-ip": "1.2.3.4"})
    assert r.status_code in (401, 403)


def test_gravar_env_mantem_o_fim_de_linha(tmp_path):
    lf, crlf = tmp_path / "lf.env", tmp_path / "crlf.env"
    lf.write_bytes(b"# x\nA=1\n")
    crlf.write_bytes(b"# x\r\nA=1\r\n")
    integracoes.gravar_env(lf, "B", "2")
    integracoes.gravar_env(crlf, "B", "2")
    assert lf.read_bytes() == b"# x\nA=1\nB=2\n"
    assert crlf.read_bytes() == b"# x\r\nA=1\r\nB=2\r\n"
