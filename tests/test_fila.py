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
    fila._PARADOS.clear()                     # a conta de voltas paradas do vigia não passa de um teste para o outro
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
    def __init__(self, andamento=(), prontos=(), desligada=False, parados=()):
        self.a, self.p, self.desligada, self.produzidos = list(andamento), list(prontos), desligada, []
        self.parados = list(parados)          # projetos que a fábrica mostra parados (não rodando, sem erro)

    def producoes(self):
        if self.desligada:
            raise fila.fabrica_api.SemFabrica("desligada")
        return {"andamento": [{"nome": n, "rodando": n not in self.parados,
                               "status": "parado" if n in self.parados else "processando"} for n in self.a],
                "prontos": [{"nome": n} for n in self.p]}

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


def test_retomado_na_fabrica_volta_a_produzindo(db):
    """12-animais (2026-10-27): a fábrica parou sem crédito, foi retomada por fora do Radar e o pedido seguia em erro."""
    a = fila.criar(1, {"titulo": "T", "roteiro_manual": "x"}, True)
    fab = Fabrica()
    _volta(fab)
    fila.mudar(a["id"], "erro", erro="OpenRouter: acabou o crédito.")
    _volta(fab)                                         # a fábrica já está rodando de novo
    atual = fila.item(1, a["id"])
    assert (atual["estado"], atual["erro"]) == ("produzindo", "")


def test_erro_sem_projeto_ou_parado_na_fabrica_fica_em_erro(db):
    a = fila.criar(1, {"titulo": "T", "roteiro_manual": "x"}, True)
    fab = Fabrica()
    _volta(fab)
    fila.mudar(a["id"], "erro", erro="parou")
    fab.a.clear()
    _volta(fab)
    assert fila.item(1, a["id"])["estado"] == "erro"


def test_fabrica_morta_no_meio_vira_erro_e_libera_a_vaga(db):
    """João o Lobo (2026-11-04): a fábrica foi morta no meio e religou sem o andamento (ele mora na memória dela).
    O projeto voltou parado, sem erro, e o pedido ficava "produzindo" para sempre, segurando uma vaga."""
    fila.definir_limite(1)
    a = fila.criar(1, {"titulo": "T", "roteiro_manual": "x"}, True)
    fab = Fabrica()
    _volta(fab)
    assert fila.item(1, a["id"])["estado"] == "produzindo"
    fab.parados.append("p-m-T")                         # a fábrica religou: o projeto está lá, parado
    _volta(fab)
    assert fila.item(1, a["id"])["estado"] == "produzindo", "uma volta parada só não é erro"
    b = fila.criar(1, {"titulo": "U", "roteiro_manual": "x"}, True)
    _volta(fab)
    atual = fila.item(1, a["id"])
    assert atual["estado"] == "erro" and "parou no meio" in atual["erro"]
    assert fila.item(1, b["id"])["estado"] == "produzindo", "a vaga do pedido morto foi liberada"


def test_parada_de_um_instante_nao_vira_erro(db):
    """O instante entre o "produzir" e a fábrica começar de verdade não pode virar erro."""
    a = fila.criar(1, {"titulo": "T", "roteiro_manual": "x"}, True)
    fab = Fabrica()
    _volta(fab)
    fab.parados.append("p-m-T")
    _volta(fab)
    fab.parados.clear()                                 # a fábrica começou
    _volta(fab)
    fab.parados.append("p-m-T")                         # e parou nesta volta: a conta recomeçou do zero
    _volta(fab)
    assert fila.item(1, a["id"])["estado"] == "produzindo"


def test_reparar_depois_de_reiniciar(db):
    a = fila.criar(1, {"titulo": "T", "caracteres": 5000}, True)
    fila.mudar(a["id"], "enviando")
    fila.reparar()
    assert fila.item(1, a["id"])["estado"] == "na_fila"


def test_estimativa_pela_parte_de_ia():
    entregues = [{"canal": "A", "minutos": 10, "usd": 1.0, "imagem": 0.2, "conferencia": 0.3}]
    sem_ia = fila.estimativa(entregues, "A", 10, 0)
    assert sem_ia == {"usd": 0.9, "base": "canal", "imagens": 0, "usd_limite": 0.9}
    muita = fila.estimativa(entregues, "A", 10, 75)
    assert muita["usd"] == 0.6 and muita["imagens"] == 128 and muita["usd_limite"] == 1.24
    assert fila.estimativa(entregues, "A", 10) == {"usd": 1.0, "base": "canal"}


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


def test_canal_de_teste_leva_o_perfil_da_lingua_escolhida(db):
    """O Canal de teste (2026-10-29) não é canal do Radar: o pedido vai sem canal, com o agente CANAL DE TESTE, a
    língua escolhida e o perfil da fábrica que fala essa língua, que vale para o roteiro e para a fábrica."""
    enviados = []

    class R(Roteirista):
        def enviar(self, usuario_id, nome, perfil):
            enviados.append(perfil)
            return super().enviar(usuario_id, nome, perfil)
    rot = R()
    fila.criar(1, {"titulo": "Por que o mar é salgado?", "caracteres": 2650, "agente_id": "8", "lingua": "holandês",
                   "perfil": "canal-jan-de-wolf", "canal_id": ""}, True)
    fila.passo(fabrica=Fabrica(), roteirista=rot, em_thread=False, config_canal=lambda uid, cid: pytest.fail("sem canal"),
               ritmo=lambda uid, perfil, lingua: {"ppm": 150})
    assert rot.pedidos[0]["perfil"] == "canal-jan-de-wolf" and rot.pedidos[0]["projeto_id"] == 8
    assert rot.pedidos[0]["lingua"] == "holandês" and rot.pedidos[0]["minutos"] == 3
    assert enviados == ["canal-jan-de-wolf"]


def test_a_rota_do_canal_de_teste(db, monkeypatch):
    from fastapi.testclient import TestClient
    from radar import producao, servidor
    banco.executar("INSERT INTO projetos_roteiro (usuario_id, nome, instrucoes, criado) VALUES (1, 'CANAL DE TESTE', 'x', '')")
    monkeypatch.setattr(producao, "perfis", lambda: [
        {"perfil": "canal-jan-de-wolf", "canal": "Jan de WOLF", "voz": "Ido", "idioma_da_voz": "nl"},
        {"perfil": "canal-joao-o-lobo", "canal": "João o Lobo", "voz": "Davi", "idioma_da_voz": "pt"},
        {"perfil": "documentario", "canal": "Documentário", "voz": "", "idioma_da_voz": ""}])
    servidor.app.dependency_overrides[servidor.usuario] = lambda: {"id": 1}
    try:
        r = TestClient(servidor.app).get("/api/fila/teste").json()
    finally:
        servidor.app.dependency_overrides.clear()
    assert r["agente_id"] == 1
    assert [l["lingua"] for l in r["linguas"]] == ["holandês", "português"]     # sem voz, o perfil não entra
    assert r["linguas"][0]["perfis"][0]["perfil"] == "canal-jan-de-wolf"


def test_canal_de_teste_sempre_de_2_a_3_minutos():
    teste = {"perfil": "canal-jan-de-wolf", "canal_id": ""}
    assert fila.minutos_do(teste | {"caracteres": fila.caracteres_de(15, 150)}, 150) == 3
    assert fila.minutos_do(teste | {"caracteres": fila.caracteres_de(1, 150)}, 150) == 2
    assert fila.minutos_do({"canal_id": "UC1", "caracteres": fila.caracteres_de(15, 150)}, 150) == 15


# ---- a fábrica ligada na pasta errada (2026-10-30)

class FabricaRecusa(Fabrica):
    """Aceita o envio, mas a produção dá o erro dado (de um projeto só, ou de todos)."""
    def __init__(self, erro, so=None):
        super().__init__()
        self.erro, self.so = erro, so

    def produzir(self, nome, confirmar):
        if self.so in (None, nome):
            raise self.erro
        super().produzir(nome, confirmar)


def test_erro_da_fabrica_num_pedido_nao_trava_a_fila(db):
    """A fábrica estava ligada na pasta errada e não achava o projeto do primeiro da fila: o pedido ficava voltando
    para a fila a cada 20 s e os de trás nem o roteiro começavam. Agora só ele para, em erro."""
    a = fila.criar(1, {"titulo": "A", "roteiro_manual": "x"}, True)
    b = fila.criar(1, {"titulo": "B", "roteiro_manual": "x"}, True)
    _volta(FabricaRecusa(fila.fabrica_api.SemFabrica("Projeto 'p-m-A' não encontrado."), so="p-m-A"))
    primeiro, segundo = fila.item(1, a["id"]), fila.item(1, b["id"])
    assert (primeiro["estado"], primeiro["erro"]) == ("erro", "Projeto 'p-m-A' não encontrado.")
    assert segundo["estado"] == "produzindo"


def test_fabrica_que_cai_no_envio_nao_vira_erro(db):
    """Desligada de verdade (porta muda ou chave recusada): o pedido espera na fila, sem erro."""
    a = fila.criar(1, {"titulo": "A", "roteiro_manual": "x"}, True)
    b = fila.criar(1, {"titulo": "B", "roteiro_manual": "x"}, True)
    _volta(FabricaRecusa(fila.fabrica_api.FabricaDesligada("desligada")))
    for pedido in (a, b):
        atual = fila.item(1, pedido["id"])
        assert (atual["estado"], atual["erro"]) == ("na_fila", "")


def test_o_estilo_das_animacoes_vai_antes_de_produzir(db):
    """O estilo escolhido na Nova produção chega à fábrica antes de ela começar: depois já seria tarde."""
    class ComEstilo(Fabrica):
        def __init__(self):
            super().__init__()
            self.ordem = []

        def definir_animacoes(self, projeto, ajustes):
            self.ordem.append(("estilo", projeto, ajustes))

        def produzir(self, nome, confirmar):
            self.ordem.append(("produzir", nome))
            super().produzir(nome, confirmar)

    fila.criar(1, {"titulo": "T", "roteiro_manual": "x", "animacoes": {"tema": "neon"}}, True)
    fab = ComEstilo()
    _volta(fab)
    assert fab.ordem == [("estilo", "p-m-T", {"tema": "neon"}), ("produzir", "p-m-T")]


def test_sem_estilo_escolhido_a_fabrica_nao_recebe_nada(db):
    fila.criar(1, {"titulo": "T", "roteiro_manual": "x"}, True)
    fab = Fabrica()              # esta fábrica de mentira nem tem definir_animacoes
    _volta(fab)
    assert fab.produzidos == ["p-m-T"]


def _enviados_com_footage(pedido):
    """Roda a fila de verdade até o envio e devolve o que o roteirista recebeu."""
    enviados = []

    class R(Roteirista):
        def enviar(self, usuario_id, nome, perfil, opcoes=None):
            enviados.append(opcoes)
            return super().enviar(usuario_id, nome, perfil)

    rot = R()
    fila.criar(1, {"titulo": "Mercados do Canadá", "caracteres": 2650, "agente_id": "8", "lingua": "inglês",
                   "perfil": "canal-jan-de-wolf", "canal_id": "", **pedido}, True)
    for _ in range(3):
        fila.passo(fabrica=Fabrica(), roteirista=rot, em_thread=False, config_canal=lambda uid, cid: {},
                   ritmo=lambda uid, perfil, lingua: {"ppm": 150})
    return enviados


def test_footage_real_chega_ao_envio_para_a_fabrica(db):
    assert _enviados_com_footage({"footage_real": 25}) == [{"footage_real": 25}]


def test_opcoes_do_video_viram_ajustes_do_projeto():
    from radar import roteiro_claude

    config, perfil = roteiro_claude.ajustes_do_video(
        {"footage_real": 15, "tema": "hacker", "ritmo": "5-8", "ia": "sem", "acervo": "sempre", "musica": "sem", "avatar": "sem",
         "edicao": "cinema", "transicao": "preto", "camada": "poeira", "som_textos": "sim"})
    assert config["garimpo"]["alvo"] == 0.15 and config["cenas"] == {"segundos_minimo": 5.0, "segundos_maximo": 8.0}
    assert config["ia"] == {"ativa": False} and config["midia"] == {"acervo": "sempre"} and config["trilha"] == {"ativo": False}
    assert config["animacoes"] == {"estilo": {"tema": "hacker"}, "som": True} and config["animation_ai"] == {"tema": "neon"}
    assert perfil == {"musica": None, "avatar": {"ativo": False}, "visual": "cinema", "transicao": "preto", "camada": "poeira"}


def _agente(tema):
    return banco.executar("INSERT INTO projetos_roteiro (usuario_id, nome, instrucoes, tema, criado) VALUES (1,'A','',?,'')", tema)


def test_o_tema_do_agente_vale_quando_o_pedido_nao_escolhe(db):
    banco.um("SELECT 1")
    agente = _agente("hacker")
    assert fila.opcoes_do(1, {"agente_id": str(agente)}) == {"tema": "hacker"}
    assert fila.opcoes_do(1, {}, {"projeto_roteiro_id": str(agente)}) == {"tema": "hacker"}     # o agente do canal
    assert fila.opcoes_do(2, {"agente_id": str(agente)}) == {}                                   # agente de outra pessoa


def test_a_escolha_do_video_vale_por_cima_do_agente(db):
    banco.um("SELECT 1")
    agente = _agente("hacker")
    assert fila.opcoes_do(1, {"agente_id": agente, "tema": "terror"}) == {"tema": "terror"}
    assert fila.opcoes_do(1, {"agente_id": agente, "escolhido_na_tela": True}) == {}


def test_agente_sem_tema_nao_muda_nada(db):
    banco.um("SELECT 1")
    assert fila.opcoes_do(1, {"agente_id": _agente(""), "footage_real": 15}) == {"footage_real": 15}


def test_o_que_foi_escolhido_na_tela_fica_guardado_no_pedido(db):
    linha = fila.criar(1, {"titulo": "T", "caracteres": 10620, "escolhido_na_tela": True, "ia_pct": 0}, True)
    pedido = fila.item(1, linha["id"])["pedido"]
    assert pedido["escolhido_na_tela"] is True and pedido["ia_pct"] == 0


def test_as_partes_de_ia_e_youtube_vem_do_agente(db):
    agente = _agente("")
    banco.executar("UPDATE projetos_roteiro SET ia_pct=75, footage_real=25 WHERE id=?", agente)
    assert fila.opcoes_do(1, {"agente_id": agente}) == {"ia_pct": 75, "footage_real": 25}
    assert fila.opcoes_do(1, {"agente_id": agente, "ia_pct": 10, "footage_real": 0}) == {"ia_pct": 10}
    assert fila.opcoes_do(1, {"agente_id": agente, "escolhido_na_tela": True}) == {}


def test_recusa_parte_de_ia_que_nao_existe_ou_que_passa_de_100(db):
    banco.um("SELECT 1")
    with pytest.raises(ValueError):
        fila.criar(1, {"titulo": "T", "caracteres": 10620, "ia_pct": 33}, True)
    with pytest.raises(ValueError):
        fila.criar(1, {"titulo": "T", "caracteres": 10620, "ia_pct": 75, "footage_real": 40}, True)


def test_parte_de_ia_vira_alvo_e_teto_na_fabrica():
    from radar import roteiro_claude

    assert roteiro_claude.ajustes_do_video({"ia_pct": 75})[0]["ia"] == {"fracao": 0.75, "teto": 0.75}
    assert roteiro_claude.ajustes_do_video({"ia_pct": 0})[0]["ia"] == {"ativa": False}


def test_sem_opcao_nada_e_gravado_no_projeto():
    from radar import roteiro_claude

    assert roteiro_claude.ajustes_do_video({}) == ({}, {}) and roteiro_claude.ajustes_do_video(None) == ({}, {})


def test_todo_tema_tem_tema_de_cena_animada():
    from radar import roteiro_claude

    assert set(fila.ESCOLHAS["tema"]) == set(roteiro_claude.TEMA_DAS_CENAS_ANIMADAS)


def test_sem_footage_real_o_envio_fica_como_sempre_foi(db):
    assert _enviados_com_footage({}) == [None]


def test_footage_real_fora_da_lista_e_recusado(db):
    fila.criar(1, {"titulo": "ok", "caracteres": 2000, "footage_real": 25}, False)
    with pytest.raises(ValueError, match="footage"):
        fila.criar(1, {"titulo": "x", "caracteres": 2000, "footage_real": 90}, False)


def test_tema_chega_ao_envio_para_a_fabrica(db):
    assert _enviados_com_footage({"tema": "dossie", "footage_real": 15}) == [{"footage_real": 15, "tema": "dossie"}]


def test_escolha_que_nao_existe_e_recusada(db):
    fila.criar(1, {"titulo": "ok", "caracteres": 2000, "edicao": "cinema"}, False)
    with pytest.raises(ValueError, match="transicao"):
        fila.criar(1, {"titulo": "x", "caracteres": 2000, "transicao": "inventada"}, False)


def test_tema_que_nao_existe_e_recusado(db):
    fila.criar(1, {"titulo": "ok", "caracteres": 2000, "tema": "cinema"}, False)
    with pytest.raises(ValueError, match="tema"):
        fila.criar(1, {"titulo": "x", "caracteres": 2000, "tema": "inventado"}, False)
