"""As máquinas de fora: chave, lease, batida, prova da entrega e o que acontece quando uma some."""
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from radar import banco, fila, maquinas, roteiro_claude  # noqa: E402

PROVA = {"bytes": 1000, "duracao": 60.5, "sha256": "abc"}


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    pasta = tmp_path / "roteiro"
    pasta.mkdir()
    (pasta / "roteiro.txt").write_text("Texto do roteiro.", encoding="utf-8")
    monkeypatch.setattr(roteiro_claude, "_do_usuario", lambda u, n: (pasta, {"titulo": "T"}))
    monkeypatch.setattr(roteiro_claude, "titulo_de_entrega", lambda meta: meta["titulo"])
    banco.con()
    yield
    banco._CON.close()
    banco._CON = None


def _pedido(destino="robo", **extras):
    item = fila.criar(1, {"titulo": "Vídeo", "caracteres": 2650, "perfil": "canal-x", "destino": destino, **extras}, True)
    banco.executar("UPDATE producoes_fila SET roteiro='r1' WHERE id=?", item["id"])
    return item["id"]


def _maquina(nome="PC do sócio"):
    return maquinas.autenticar(maquinas.criar(nome)["chave"])


def _estado(fid):
    return banco.um("SELECT * FROM producoes_fila WHERE id=?", fid)


def test_chave_so_existe_em_hash(db):
    criada = maquinas.criar("PC")
    assert criada["chave"].startswith("rdm_")
    guardado = banco.um("SELECT chave_hash FROM maquinas WHERE id=?", criada["id"])["chave_hash"]
    assert criada["chave"] not in guardado
    assert "chave" not in json.dumps(maquinas.listar()) or criada["chave"] not in json.dumps(maquinas.listar())


def test_chave_errada_nao_entra(db):
    maquinas.criar("PC")
    assert maquinas.autenticar("rdm_inventada") is None and maquinas.autenticar("") is None


def test_reivindicar_entrega_tudo_para_produzir(db):
    fid = _pedido(footage_real=25, tema="dossie")
    t = maquinas.reivindicar(_maquina(), {"nucleos": 12})
    assert t["id"] == fid and t["roteiro"] == "Texto do roteiro." and t["perfil"] == "canal-x"
    assert t["config_override"]["garimpo"]["alvo"] == 0.25
    assert t["config_override"]["animacoes"]["estilo"]["tema"] == "dossie"
    assert t["config_override"]["animation_ai"]["tema"] == "misterio" and t["perfil_override"] == {}
    assert _estado(fid)["estado"] == "produzindo"


def test_pedido_local_nunca_vai_para_robo(db):
    _pedido(destino="")
    assert maquinas.reivindicar(_maquina()) is None


def test_pedido_sem_roteiro_espera(db):
    fid = _pedido()
    banco.executar("UPDATE producoes_fila SET roteiro='' WHERE id=?", fid)
    assert maquinas.reivindicar(_maquina()) is None


def test_duas_maquinas_nao_levam_o_mesmo_video(db):
    _pedido()
    a, b = _maquina("A"), _maquina("B")
    assert maquinas.reivindicar(a) is not None
    assert maquinas.reivindicar(b) is None


def test_bater_renova_o_lease_e_guarda_eventos(db):
    fid = _pedido()
    m = _maquina()
    t = maquinas.reivindicar(m)
    banco.executar("UPDATE producoes_fila SET lease_ate=? WHERE id=?", time.time() + 5, fid)
    maquinas.bater(m, fid, t["lease"], "Gerando imagens", ["linha 1"])
    linha = _estado(fid)
    assert linha["lease_ate"] > time.time() + 200 and linha["passo"] == "Gerando imagens"
    assert json.loads(linha["eventos"]) == ["linha 1"]


def test_maquina_que_some_devolve_o_video_e_o_lease_velho_e_recusado(db):
    fid = _pedido()
    a, b = _maquina("A"), _maquina("B")
    velho = maquinas.reivindicar(a)
    banco.executar("UPDATE producoes_fila SET lease_ate=? WHERE id=?", time.time() - 1, fid)
    assert maquinas.expirar() == [fid]
    assert _estado(fid)["estado"] == "na_fila"
    novo = maquinas.reivindicar(b)
    assert novo["id"] == fid
    with pytest.raises(maquinas.LeaseVelha):
        maquinas.bater(a, fid, velho["lease"])
    with pytest.raises(maquinas.LeaseVelha):
        maquinas.concluir(a, fid, velho["lease"], PROVA)
    assert _estado(fid)["estado"] == "produzindo"


def test_expirar_nao_toca_em_quem_esta_batendo_nem_nos_videos_locais(db):
    fid = _pedido()
    maquinas.reivindicar(_maquina())
    local = _pedido(destino="")
    banco.executar("UPDATE producoes_fila SET estado='produzindo' WHERE id=?", local)
    assert maquinas.expirar() == []
    assert _estado(fid)["estado"] == "produzindo" and _estado(local)["estado"] == "produzindo"


def test_concluir_guarda_a_prova(db):
    fid = _pedido()
    m = _maquina("PC 2")
    t = maquinas.reivindicar(m)
    assert maquinas.concluir(m, fid, t["lease"], PROVA)
    linha = _estado(fid)
    assert linha["estado"] == "entregue" and json.loads(linha["prova"])["maquina"] == "PC 2"


@pytest.mark.parametrize("prova", [{}, {"bytes": 0, "duracao": 60, "sha256": "x"}, {"bytes": 9, "duracao": 0, "sha256": "x"},
                                   {"bytes": 9, "duracao": 60}])
def test_sem_prova_de_verdade_nao_vira_entregue(db, prova):
    fid = _pedido()
    m = _maquina()
    t = maquinas.reivindicar(m)
    with pytest.raises(ValueError):
        maquinas.concluir(m, fid, t["lease"], prova)
    assert _estado(fid)["estado"] == "produzindo"


def test_falhar_vira_erro_e_tentar_de_novo_volta_para_a_fila(db):
    fid = _pedido()
    m = _maquina()
    t = maquinas.reivindicar(m)
    maquinas.falhar(m, fid, t["lease"], "sem disco")
    assert _estado(fid)["estado"] == "erro" and "sem disco" in _estado(fid)["erro"]
    fila.tentar(1, fid)
    assert maquinas.reivindicar(m)["id"] == fid


def test_revogar_tira_a_chave_e_devolve_o_video(db):
    fid = _pedido()
    criada = maquinas.criar("PC")
    m = maquinas.autenticar(criada["chave"])
    maquinas.reivindicar(m)
    assert maquinas.revogar(m["id"])
    assert maquinas.autenticar(criada["chave"]) is None
    assert _estado(fid)["estado"] == "na_fila"


def test_listar_diz_quem_esta_online_e_o_que_faz(db):
    fid = _pedido()
    m = _maquina("PC")
    maquinas.reivindicar(m, {"nucleos": 8})
    (uma,) = maquinas.listar()
    assert uma["online"] and uma["capacidades"] == {"nucleos": 8} and uma["fazendo"][0]["id"] == fid


class _Fabrica:
    def __init__(self):
        self.enviados = []

    def producoes(self):
        return {"prontos": [], "andamento": []}

    def produzir(self, projeto, confirmar):
        self.enviados.append(projeto)


class _Roteirista:
    def enviar(self, *a, **k):
        pytest.fail("pedido de robô não pode ir para a fábrica desta máquina")


def _volta():
    fila.passo(fabrica=_Fabrica(), roteirista=_Roteirista(), em_thread=False, config_canal=lambda u, c: {},
               ritmo=lambda u, p, l: {"ppm": 150})


def test_vigia_nao_manda_para_a_fabrica_local_e_nao_marca_como_sumido(db):
    fid = _pedido()
    _volta()
    assert _estado(fid)["estado"] == "na_fila"
    maquinas.reivindicar(_maquina())
    _volta()
    linha = _estado(fid)
    assert linha["estado"] == "produzindo" and linha["erro"] == ""


def test_video_em_outra_maquina_nao_ocupa_vaga_daqui(db):
    fid = _pedido()
    maquinas.reivindicar(_maquina())
    fila.definir_limite(1)
    _volta()
    assert fila.limite() == 1 and _estado(fid)["estado"] == "produzindo"
    assert banco.um("SELECT COUNT(*) n FROM producoes_fila WHERE estado IN ('enviando','produzindo') AND maquina_id IS NULL")["n"] == 0


def test_vigia_devolve_o_que_a_maquina_largou(db):
    fid = _pedido()
    maquinas.reivindicar(_maquina())
    banco.executar("UPDATE producoes_fila SET lease_ate=? WHERE id=?", time.time() - 1, fid)
    _volta()
    assert _estado(fid)["estado"] == "na_fila"


def test_lease_nao_aparece_para_a_tela(db):
    fid = _pedido()
    maquinas.reivindicar(_maquina())
    assert "lease" not in fila.item(1, fid)


def test_rotas_da_maquina(db, monkeypatch):
    from fastapi.testclient import TestClient

    from radar import servidor

    cliente = TestClient(servidor.app)
    assert cliente.post("/api/robo/reivindicar", json={}).status_code == 401
    assert cliente.post("/api/robo/reivindicar", json={}, headers={"x-robo-chave": "rdm_errada"}).status_code == 401
    fid = _pedido()
    chave = {"x-robo-chave": maquinas.criar("PC")["chave"]}
    t = cliente.post("/api/robo/reivindicar", json={"capacidades": {"nucleos": 4}}, headers=chave).json()["trabalho"]
    assert t["id"] == fid
    assert cliente.post("/api/robo/bater", json={"id": fid, "lease": t["lease"], "passo": "x"}, headers=chave).status_code == 200
    r = cliente.post("/api/robo/bater", json={"id": fid, "lease": "velha"}, headers=chave)
    assert r.status_code == 409 and r.json()["detail"] == "lease_velha"
    assert cliente.post("/api/robo/concluir", json={"id": fid, "lease": t["lease"], "prova": {}}, headers=chave).status_code == 400
    assert cliente.post("/api/robo/concluir", json={"id": fid, "lease": t["lease"], "prova": PROVA}, headers=chave).status_code == 200
    assert _estado(fid)["estado"] == "entregue"
    assert cliente.post("/api/robo/reivindicar", json={}, headers=chave).json()["trabalho"] is None


def _fabrica_de_mentira(raiz):
    for arquivo in ("fabrica/api.py", "fabrica/__pycache__/api.pyc", "fabrica/api.py.antes-token", "perfis/canal.yaml",
                    "perfis/canal.yaml.antes", "pyproject.toml", ".env", ".env.antes", ".env.exemplo", "config.yaml",
                    "palhano/painel/dados/segredo.key", "projetos/video/final.mp4", "contas_youtube/a.txt", "drive_conta.json",
                    "youtube_conta.json"):
        caminho = raiz / arquivo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text("x", encoding="utf-8")


def test_pacote_leva_so_o_que_esta_na_lista(tmp_path):
    import zipfile

    _fabrica_de_mentira(tmp_path)
    arquivo = maquinas.pacote(tmp_path, tmp_path / "p.zip")
    assert sorted(zipfile.ZipFile(arquivo).namelist()) == [".env.exemplo", "config.yaml", "fabrica/api.py", "perfis/canal.yaml",
                                                           "pyproject.toml"]


def test_pacote_exige_a_chave_da_maquina(db, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from radar import servidor

    _fabrica_de_mentira(tmp_path)
    monkeypatch.setattr(roteiro_claude, "FABRICA", tmp_path)
    cliente = TestClient(servidor.app)
    assert cliente.get("/api/robo/pacote").status_code == 401
    r = cliente.get("/api/robo/pacote", headers={"x-robo-chave": maquinas.criar("PC")["chave"]})
    assert r.status_code == 200 and r.content[:2] == b"PK"
