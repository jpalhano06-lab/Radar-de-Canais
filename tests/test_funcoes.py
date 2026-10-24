"""As funções da extensão numa fonte só: a lista, o plano de cada uma e a rota que serve as telas."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from radar import funcoes, servidor  # noqa: E402
from radar.config import PLANOS  # noqa: E402

# sem o `with`, como no test_abertura: o TestClient em contexto roda os eventos de start/stop do app
cliente = TestClient(servidor.app)


def test_cada_funcao_esta_inteira_e_a_chave_nao_repete():
    chaves = [f["chave"] for f in funcoes.FUNCOES]
    assert len(chaves) == len(set(chaves)), "chave repetida na lista de funções"
    for f in funcoes.FUNCOES:
        assert f["chave"] and f["nome"] and f["desc"], f
        assert f["onde"] in funcoes.ONDE, f["chave"]
        assert f["desc"].endswith("."), f["chave"]       # a tela mostra a frase inteira


def test_o_recurso_de_cada_funcao_existe_em_algum_plano():
    # se um recurso não estiver em nenhum plano, a função ficaria trancada para todo mundo para sempre
    todos = {r for p in PLANOS.values() for r in p["recursos"]}
    for f in funcoes.FUNCOES:
        assert f["recurso"] in todos, f["chave"]


def test_o_plano_de_cada_funcao_e_o_mais_barato_que_abre_o_recurso():
    assert funcoes.plano_de("extensao") == "gratis"
    assert funcoes.plano_de("salvar") == "lite"
    assert funcoes.plano_de("radar") == "pro"
    # a mesma conta que o servidor usa para o 402
    for f in funcoes.lista():
        precisa = next(k for k, v in PLANOS.items() if f["recurso"] in v["recursos"])
        assert f["plano"] == precisa, f["chave"]
        assert f["plano_nome"] == PLANOS[precisa]["nome"]


def test_sem_plano_a_lista_nao_diz_nada_sobre_liberada():
    assert all(f["liberada"] is None for f in funcoes.lista())


def test_cada_plano_abre_o_que_deve_e_tranca_o_resto():
    por = {f["chave"]: f["liberada"] for f in funcoes.lista("gratis")}
    assert por["nota"] is True and por["transcricao"] is True
    assert por["salvar"] is False and por["linguas"] is False and por["alta"] is False

    por = {f["chave"]: f["liberada"] for f in funcoes.lista("lite")}
    assert por["salvar"] is True and por["parecidos"] is True and por["linguas"] is True
    assert por["alta"] is False, "a faixa de canais em alta vem do garimpo, que é do Pro"

    assert all(f["liberada"] for f in funcoes.lista("pro")), "o Pro abre tudo"


def test_plano_desconhecido_vale_como_gratis():
    # uma conta com o plano escrito errado não pode abrir o Pro por acidente
    por = {f["chave"]: f["liberada"] for f in funcoes.lista("plano-que-nao-existe")}
    assert por["nota"] is True and por["salvar"] is False


def test_os_planos_sao_cumulativos():
    nomes = funcoes.por_plano()
    assert set(nomes["gratis"]) <= set(nomes["lite"]) <= set(nomes["pro"])
    assert len(nomes["pro"]) == len(funcoes.FUNCOES)


def test_a_contagem_e_a_que_a_tela_mostra():
    c = funcoes.contagem()
    assert c["total"] == len(funcoes.FUNCOES)
    assert 0 < c["gratis"] < c["total"], "a extensão é a isca: a maior parte é grátis, mas não tudo"
    assert c["gratis"] == sum(1 for f in funcoes.FUNCOES if funcoes.plano_de(f["recurso"]) == "gratis")


def test_a_rota_que_serve_as_telas_existe():
    caminhos = {r.path for r in servidor.app.routes}
    assert "/api/ext/funcoes" in caminhos


def test_a_rota_pede_conta():
    """A lista sai com o plano de quem pediu, então sem saber quem é não há o que responder."""
    assert cliente.get("/api/ext/funcoes").status_code == 401


def conta(plano: str) -> dict:
    return {"id": 1, "email": "eu@exemplo.com", "admin": 0, "plano": plano, "vence": None}


def pedir_como(plano: str) -> dict:
    servidor.app.dependency_overrides[servidor.usuario] = lambda: conta(plano)
    try:
        r = cliente.get("/api/ext/funcoes")
        assert r.status_code == 200, r.text
        return r.json()
    finally:
        servidor.app.dependency_overrides.clear()


def test_a_rota_devolve_o_que_as_telas_montam():
    d = pedir_como("gratis")
    assert set(d) == {"funcoes", "onde", "contagem"}
    assert d["contagem"] == funcoes.contagem()
    assert d["onde"] == funcoes.ONDE
    assert len(d["funcoes"]) == len(funcoes.FUNCOES)
    for f in d["funcoes"]:
        assert {"chave", "nome", "desc", "onde", "plano", "plano_nome", "liberada"} <= set(f)


def test_a_rota_responde_com_o_plano_de_quem_pediu():
    trancadas = lambda d: {f["chave"] for f in d["funcoes"] if f["liberada"] is False}  # noqa: E731
    assert "salvar" in trancadas(pedir_como("gratis"))
    assert trancadas(pedir_como("lite")) == {"alta"}
    assert trancadas(pedir_como("pro")) == set()


def test_cada_grupo_de_tela_tem_pelo_menos_uma_funcao():
    # a tela de ajuda monta um título por grupo: grupo vazio seria um título solto
    usados = {f["onde"] for f in funcoes.FUNCOES}
    assert usados == set(funcoes.ONDE), f"grupo sem função: {set(funcoes.ONDE) - usados}"
