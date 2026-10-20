"""A fila da Nova produção e o vigia, sem rede (fábrica e roteirista de mentira)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, fila  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    yield
    banco._CON.close()
    banco._CON = None


def test_conta_de_tamanho():
    assert fila.minutos_de(10620, 150) == pytest.approx(12.0, abs=0.1)
    assert fila.caracteres_de(12, 150) == 10620


def test_criar_comecar_e_entrada(db):
    a = fila.criar(1, {"titulo": "T", "caracteres": 10620}, comecar=True)
    b = fila.criar(1, {"titulo": "U", "caracteres": 10620}, comecar=False)
    assert (a["estado"], b["estado"]) == ("na_fila", "entrada")
    fila.comecar(1, b["id"])
    assert fila.item(1, b["id"])["estado"] == "na_fila"


def test_recusa_titulo_vazio_e_tamanho_fora(db):
    with pytest.raises(ValueError):
        fila.criar(1, {"titulo": " ", "caracteres": 5000}, True)
    with pytest.raises(ValueError):
        fila.criar(1, {"titulo": "T", "caracteres": 500}, True)
    assert fila.criar(1, {"titulo": "T", "caracteres": 0, "roteiro_manual": "texto"}, True)["estado"] == "na_fila"


def test_limite(db):
    assert fila.limite() == 2
    assert fila.definir_limite(4) == 4
    with pytest.raises(ValueError):
        fila.definir_limite(5)


def test_outro_usuario_nao_mexe(db):
    a = fila.criar(1, {"titulo": "T", "caracteres": 5000}, False)
    assert fila.item(2, a["id"]) is None


class Fabrica:
    """A fábrica de mentira: andamento (rodando), prontos e o que mandaram produzir."""
    def __init__(self, andamento=(), prontos=(), desligada=False):
        self.a, self.p, self.desligada, self.produzidos = list(andamento), list(prontos), desligada, []

    def producoes(self):
        if self.desligada:
            raise fila.fabrica_api.SemFabrica("desligada")
        return {"andamento": [{"nome": n, "rodando": True} for n in self.a], "prontos": [{"nome": n} for n in self.p]}

    def produzir(self, nome, confirmar):
        assert confirmar is True
        self.produzidos.append(nome)
        self.a.append(nome)


class Roteirista:
    def __init__(self, erro_ao_enviar=None):
        self.erro, self.pedidos = erro_ao_enviar, []

    def gerar(self, **pedido):
        self.pedidos.append(pedido)
        return {"nome": "r-" + pedido["titulo"]}

    def manual(self, **pedido):
        return {"nome": "m-" + pedido["titulo"]}

    def enviar(self, usuario_id, nome, perfil):
        if self.erro:
            raise RuntimeError(self.erro)
        return {"projeto": "p-" + nome}


def _volta(fab, rot=None):
    return fila.passo(fabrica=fab, roteirista=rot or Roteirista(), em_thread=False,
                      config_canal=lambda uid, cid: {"perfil": "canal-x", "lingua": "inglês", "projeto_roteiro_id": "", "canal": "X"},
                      ritmo=lambda uid, perfil, lingua: {"ppm": 150})


def test_vigia_respeita_o_limite(db):
    fila.definir_limite(1)
    ids = [fila.criar(1, {"titulo": f"T{i}", "roteiro_manual": "x"}, True)["id"] for i in range(3)]
    fab = Fabrica()
    _volta(fab)
    estados = [fila.item(1, i)["estado"] for i in ids]
    assert estados.count("produzindo") == 1 and estados.count("na_fila") == 2
    assert fab.produzidos == ["p-m-T0"]


def test_video_da_fabrica_fora_da_fila_ocupa_vaga(db):
    fila.definir_limite(1)
    a = fila.criar(1, {"titulo": "T", "roteiro_manual": "x"}, True)
    _volta(Fabrica(andamento=["outro"]))
    assert fila.item(1, a["id"])["estado"] == "na_fila"
    assert fila.item(1, a["id"])["roteiro"] == "m-T"          # o roteiro já fica pronto enquanto espera


def test_revisao_para_em_sua_vez_e_aprovar_segue(db):
    a = fila.criar(1, {"titulo": "T", "caracteres": 5000, "revisar": True}, True)
    _volta(Fabrica())
    assert fila.item(1, a["id"])["estado"] == "sua_vez"
    fila.aprovar(1, a["id"])
    _volta(Fabrica())
    assert fila.item(1, a["id"])["estado"] == "produzindo"


def test_pedido_ao_claude_leva_minutos_pelo_ritmo_e_o_nicho(db):
    rot = Roteirista()
    fila.criar(1, {"titulo": "T", "caracteres": 10620, "nicho": "carros", "observacao": "sem gírias"}, True)
    _volta(Fabrica(), rot)
    assert rot.pedidos[0]["minutos"] == 12
    assert "carros" in rot.pedidos[0]["observacoes"] and "sem gírias" in rot.pedidos[0]["observacoes"]


def test_entregue_quando_fica_pronto(db):
    a = fila.criar(1, {"titulo": "T", "roteiro_manual": "x"}, True)
    fab = Fabrica()
    _volta(fab)
    fab.a.remove("p-m-T")
    fab.p.append("p-m-T")
    _volta(fab)
    assert fila.item(1, a["id"])["estado"] == "entregue"


def test_fabrica_desligada_nao_vira_erro(db):
    a = fila.criar(1, {"titulo": "T", "roteiro_manual": "x"}, True)
    _volta(Fabrica(desligada=True))
    assert fila.item(1, a["id"])["estado"] == "na_fila"


def test_erro_e_tentar_de_novo(db):
    a = fila.criar(1, {"titulo": "T", "roteiro_manual": "x"}, True)
    _volta(Fabrica(), Roteirista(erro_ao_enviar="perfil sumiu"))
    atual = fila.item(1, a["id"])
    assert (atual["estado"], atual["erro"]) == ("erro", "perfil sumiu")
    fila.tentar(1, a["id"])
    _volta(Fabrica())
    assert fila.item(1, a["id"])["estado"] == "produzindo"


def test_reparar_depois_de_reiniciar(db):
    a = fila.criar(1, {"titulo": "T", "caracteres": 5000}, True)
    fila.mudar(a["id"], "enviando")
    fila.reparar()
    assert fila.item(1, a["id"])["estado"] == "na_fila"


def test_estimativa_pela_media_do_canal():
    entregues = [{"canal": "A", "minutos": 30, "usd": 3.0}, {"canal": "A", "minutos": 10, "usd": 1.0},
                 {"canal": "B", "minutos": 10, "usd": 5.0}]
    assert fila.estimativa(entregues, "A", 12) == {"usd": 1.2, "base": "canal"}
    assert fila.estimativa(entregues, "C", 10) == {"usd": round(9 / 50 * 10, 2), "base": "geral"}
    assert fila.estimativa([], "A", 10) == {"usd": None, "base": None}


# ---- achados da revisão final (2026-10-18)

class FabricaFalha(Fabrica):
    """Aceita o envio mas a primeira produção falha."""
    def __init__(self):
        super().__init__()
        self.falhas = 1

    def produzir(self, nome, confirmar):
        if self.falhas:
            self.falhas -= 1
            raise RuntimeError("caiu no meio")
        super().produzir(nome, confirmar)


class RoteiristaContado(Roteirista):
    def __init__(self, ao_gerar=None, ao_enviar=None):
        super().__init__()
        self.envios, self.ao_gerar, self.ao_enviar = 0, ao_gerar, ao_enviar

    def gerar(self, **pedido):
        if self.ao_gerar:
            self.ao_gerar()
        return super().gerar(**pedido)

    def enviar(self, usuario_id, nome, perfil):
        self.envios += 1
        if self.ao_enviar:
            self.ao_enviar()
        return super().enviar(usuario_id, nome, perfil)


def test_excluir_durante_a_escrita_nao_ressuscita(db):
    a = fila.criar(1, {"titulo": "T", "caracteres": 5000}, True)
    fab = Fabrica()
    _volta(fab, RoteiristaContado(ao_gerar=lambda: fila.excluir(1, a["id"])))
    _volta(fab)
    assert fila.item(1, a["id"])["estado"] == "cancelado"
    assert fab.produzidos == []


def test_excluir_durante_o_envio_nao_produz(db):
    a = fila.criar(1, {"titulo": "T", "roteiro_manual": "x"}, True)
    fab = Fabrica()
    _volta(fab, RoteiristaContado(ao_enviar=lambda: fila.excluir(1, a["id"])))
    assert fila.item(1, a["id"])["estado"] == "cancelado"
    assert fab.produzidos == []


def test_tentar_de_novo_reaproveita_o_projeto(db):
    a = fila.criar(1, {"titulo": "T", "roteiro_manual": "x"}, True)
    fab, rot = FabricaFalha(), RoteiristaContado()
    _volta(fab, rot)
    atual = fila.item(1, a["id"])
    assert (atual["estado"], atual["projeto"]) == ("erro", "p-m-T")      # o projeto criado fica guardado
    fila.tentar(1, a["id"])
    _volta(fab, rot)
    assert rot.envios == 1 and fab.produzidos == ["p-m-T"]                # sem projeto novo, sem gasto duplicado


def test_reparar_enviando_com_projeto_nao_cria_outro(db):
    a = fila.criar(1, {"titulo": "T", "roteiro_manual": "x"}, True)
    fila.mudar(a["id"], "enviando", roteiro="m-T", projeto="p-m-T")
    fila.reparar()
    fab, rot = Fabrica(), RoteiristaContado()
    _volta(fab, rot)
    assert rot.envios == 0 and fab.produzidos == ["p-m-T"]


def test_no_maximo_duas_escritas_ao_mesmo_tempo(db):
    import threading
    solta = threading.Event()
    ids = [fila.criar(1, {"titulo": f"T{i}", "caracteres": 5000}, True)["id"] for i in range(5)]
    fila.passo(fabrica=Fabrica(), roteirista=RoteiristaContado(ao_gerar=solta.wait), em_thread=True,
               config_canal=lambda uid, cid: {}, ritmo=lambda uid, perfil, lingua: {"ppm": 150})
    estados = [fila.item(1, i)["estado"] for i in ids]
    solta.set()
    for _ in range(100):           # as threads terminam antes de o banco do teste fechar
        if not any(fila.item(1, i)["estado"] == "escrevendo" for i in ids):
            break
        threading.Event().wait(0.02)
    assert estados.count("escrevendo") == fila.ESCRITAS_AO_MESMO_TEMPO == 2
