"""O pacote de abertura: o que a primeira tela precisa, numa chamada só (sem rede)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from radar import servidor  # noqa: E402

# sem o `with`: o TestClient em contexto roda os eventos de start/stop do app (threads e banco de verdade), e isso
# vazava para os outros testes — a fila passava a ver o mundo que o servidor montou em vez do tmp_path dela
cliente = TestClient(servidor.app)

CAMINHOS_DA_ABERTURA = {"resumo", "vitrine", "eu", "prefs", "painel", "alvos", "filtros", "visoes", "pastas"}


def test_sem_sessao_vem_so_o_que_e_publico():
    """A tela de entrar não precisa de mais nada, e nada da conta de ninguém pode vazar aqui."""
    d = cliente.get("/api/abertura").json()
    # a vitrine vai junto porque entrar é a única tela que ele vai ver; o resto é da conta de alguém
    assert set(d["pacote"]) == {"resumo", "vitrine"}
    for chave in ("eu", "prefs", "painel", "alvos", "pastas"):
        assert chave not in d["pacote"], chave


def test_a_abertura_responde_sem_login():
    r = cliente.get("/api/abertura")
    assert r.status_code == 200
    assert "resumo" in r.json()["pacote"]


def test_as_chaves_sao_caminhos_que_o_painel_pediria():
    """Cada chave vira /api/<chave> no front: um nome fora da lista não seria servido a ninguém."""
    d = cliente.get("/api/abertura").json()
    assert set(d["pacote"]) <= CAMINHOS_DA_ABERTURA
    caminhos = {r.path for r in servidor.app.routes}
    for chave in d["pacote"]:
        assert f"/api/{chave}" in caminhos, chave


def test_a_vitrine_nao_leva_dado_de_ninguem():
    """Ela é pública: só canal do YouTube e contagem. Nada de salvos, pastas, e-mail ou quantidade de gente."""
    d = cliente.get("/api/vitrine").json()
    assert set(d) == {"nome", "canais", "analisados", "videos", "nichos", "subnichos", "novos_semana",
                      "estouraram", "exemplos", "depoimentos"}
    for c in d["exemplos"]:
        assert set(c) == {"nome", "foto", "nicho", "inscritos", "media", "raridade", "dias", "capas"}
        assert len(c["capas"]) == servidor.VITRINE_CAPAS


def test_a_vitrine_responde_sem_conta():
    r = cliente.get("/api/vitrine")
    assert r.status_code == 200
    assert r.json()["canais"] >= 0


def test_a_vitrine_fica_guardada_alguns_minutos():
    """As contagens varrem a tabela inteira: refazer a cada visita abriria a porta para derrubar o Radar."""
    assert servidor.VITRINE_MINUTOS >= 1
    primeira = cliente.get("/api/vitrine").json()
    assert cliente.get("/api/vitrine").json() is not None
    assert servidor._VITRINE["dados"] == primeira


def test_o_depoimento_que_vai_para_a_vitrine_nao_leva_arquivo_nem_estado():
    """O caminho do print no disco e o `mostrar` são de dentro: para fora vai uma URL e o texto."""
    guardado = {"id": 7, "nome": "Alguém", "canal": "", "resultado": "", "texto": "", "quando": "2026-10-23",
                "print": "7.jpg", "mostrar": 1}
    publico = servidor._depoimento_publico(guardado)
    assert set(publico) == {"id", "nome", "canal", "resultado", "texto", "quando", "print"}
    assert publico["print"] == "/api/depoimentos/7/print"
    assert "7.jpg" not in str(publico)


def test_depoimento_sem_print_nao_promete_imagem():
    publico = servidor._depoimento_publico({"id": 9, "nome": "Alguém", "canal": "", "resultado": "", "texto": "",
                                            "quando": "2026-10-23", "print": "", "mostrar": 1})
    assert publico["print"] == ""


def test_o_print_so_aceita_imagem():
    """Um data URL de qualquer outro tipo (ou sem base64) é recusado antes de virar arquivo no disco."""
    import pytest
    from fastapi import HTTPException
    assert servidor._guardar_print(1, "") == ""
    assert servidor._guardar_print(1, "https://exemplo/x.jpg") == ""
    for ruim in ("data:text/html;base64,PGI+", "data:image/svg+xml;base64,PHN2Zz4=", "data:image/jpeg,naoebase64"):
        with pytest.raises(HTTPException):
            servidor._guardar_print(1, ruim)


def test_a_vitrine_comeca_sem_depoimento_nenhum():
    """O Radar não inventa depoimento: eles entram um a um pela Administração."""
    d = cliente.get("/api/vitrine").json()
    assert isinstance(d["depoimentos"], list)


def test_o_preco_so_aparece_para_quem_tem_conta():
    assert cliente.get("/api/planos").status_code == 401


# ---------------------------------------------------------------- a versão dos arquivos do painel

def test_o_index_pede_a_versao_do_arquivo_que_esta_no_disco():
    """O `?v=` escrito à mão ficou em 104 enquanto o `app.js` mudou três vezes: o navegador guardou a tela velha
    e a pessoa viu o Radar de ontem, sem erro nenhum. Agora o número é a hora do arquivo, e este teste cobra isso."""
    import re

    html = cliente.get("/").text
    pedidos = re.findall(r"/web/(app\.js|estilo\.css)\?v=(\d+)", html)
    assert len(pedidos) == 2, f"o index tem de pedir os dois arquivos com versão: {pedidos}"
    for nome, versao in pedidos:
        hora = int((servidor.WEB / nome).stat().st_mtime)
        assert int(versao) >= hora, f"{nome} pede v={versao}, mais velho que o arquivo ({hora})"


def test_o_index_nao_fica_guardado_no_navegador():
    """Se o próprio index ficasse no cache, subir a versão dos arquivos não chegaria a ninguém."""
    assert cliente.get("/").headers["cache-control"] == "no-store"
