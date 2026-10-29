"""Os projetos do claude.ai ligados aos agentes do Radar (pedido do usuário em 2026-10-29).

Os nomes e os tamanhos são os de verdade: no claude.ai o projeto se chama "AGENTE UK" e no Radar o agente se chama
"UK AGENTE"; "ANIMAIS HOLANDA" tem o mesmo texto do "JAN DE WOLF". Nada de rede nem de Claude aqui."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, claude_projetos, roteiro_claude, tempo  # noqa: E402

HOLANDA = "# AGENTE DE ROTEIROS — CANAL DE ANIMAIS (PAÍSES BAIXOS) — SAÍDA EM ROTEIRO CORRIDO\n" + "Regra do canal. " * 300
UK = "# AGENTE DE ROTEIROS — CANAL DE COMPARAÇÃO DE MARCAS (REINO UNIDO)\n" + "Outra regra. " * 300


@pytest.fixture
def agentes(monkeypatch, tmp_path):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    criar = lambda nome, texto: banco.executar(
        "INSERT INTO projetos_roteiro (usuario_id, nome, instrucoes, criado) VALUES (1,?,?,?)", nome, texto, banco.agora())
    return {"jan": criar("JAN DE WOLF", HOLANDA), "uk": criar("UK AGENTE", UK[:8000])}


def _projeto(uuid, nome, instrucoes, arquivos=()):
    return {"uuid": uuid, "nome": nome, "instrucoes": instrucoes, "arquivos": list(arquivos)}


def _agente(pid):
    return banco.um("SELECT * FROM projetos_roteiro WHERE id=?", pid)


def test_liga_pelo_texto_e_pelo_nome_sem_criar_repetido(agentes):
    r = claude_projetos.sincronizar(1, [
        _projeto("u-holanda", "ANIMAIS HOLANDA", HOLANDA + "\nUma regra nova escrita hoje."),
        _projeto("u-uk", "AGENTE UK", UK),                       # a cópia do Radar estava cortada em 8 mil letras
    ])
    assert r["criados"] == []
    jan, uk = _agente(agentes["jan"]), _agente(agentes["uk"])
    assert jan["claude_uuid"] == "u-holanda" and jan["instrucoes"].endswith("Uma regra nova escrita hoje.")
    assert jan["nome"] == "JAN DE WOLF"                          # o canal continua achando o agente pelo nome dele
    assert uk["claude_uuid"] == "u-uk" and len(uk["instrucoes"]) == len(UK.strip())


def test_depois_de_ligado_segue_o_uuid_mesmo_mudando_tudo(agentes):
    claude_projetos.sincronizar(1, [_projeto("u-holanda", "ANIMAIS HOLANDA", HOLANDA)])
    claude_projetos.sincronizar(1, [_projeto("u-holanda", "HOLANDA NOVO NOME", "Texto todo diferente. " * 30)])
    jan = _agente(agentes["jan"])
    assert jan["instrucoes"].startswith("Texto todo diferente.") and jan["claude_nome"] == "HOLANDA NOVO NOME"


def test_projeto_novo_vira_agente_e_o_quase_vazio_nao(agentes):
    r = claude_projetos.sincronizar(1, [_projeto("u-ca", "Canada agente", "Instruções do Canadá. " * 40),
                                        _projeto("u-guia", "Como usar o Claude", "Um guia curto.")])
    assert r["criados"] == ["Canada agente"] and r["ignorados"] == ["Como usar o Claude"]
    assert banco.um("SELECT * FROM projetos_roteiro WHERE claude_uuid='u-ca'")["tipo"] == "roteiro"


def test_os_arquivos_vao_no_roteiro_os_mais_novos_primeiro(agentes, monkeypatch, tmp_path):
    grande = "x" * (claude_projetos.ARQUIVOS_NO_ROTEIRO - 100)
    claude_projetos.sincronizar(1, [_projeto("u-holanda", "ANIMAIS HOLANDA", HOLANDA, [
        {"nome": "roteiros/velho.txt", "texto": grande, "criado": "2026-10-01"},
        {"nome": "roteiros/novo.txt", "texto": "Exemplo de roteiro novo.", "criado": "2026-10-28"},
    ])])
    jan = _agente(agentes["jan"])
    texto = claude_projetos.texto_dos_arquivos(jan)
    assert texto.startswith("=== roteiros/novo.txt ===") and "velho" in texto
    assert len(texto) < claude_projetos.ARQUIVOS_NO_ROTEIRO + 200

    roteiros = tmp_path / "roteiros"
    roteiros.mkdir()
    monkeypatch.setattr(roteiro_claude, "PASTA", roteiros)
    monkeypatch.setattr(tempo, "_da_api", lambda: {})
    monkeypatch.setattr(roteiro_claude, "_escrever_descricao", lambda *a, **k: None)
    visto = {}

    def falso(sistema, pedido, modelo=""):
        visto["sistema"] = sistema
        return "Frase do roteiro. " * 400

    monkeypatch.setattr(roteiro_claude, "_claude", falso)
    roteiro_claude.gerar(usuario_id=1, titulo="Dieren", link="", minutos=3, lingua="holandês",
                         projeto_id=agentes["jan"], observacoes="")
    assert "Regra do canal." in visto["sistema"]
    assert "=== roteiros/novo.txt ===" in visto["sistema"]


def test_a_tela_recebe_so_quantos_arquivos(agentes):
    from fastapi.testclient import TestClient
    from radar import servidor
    claude_projetos.sincronizar(1, [_projeto("u-holanda", "ANIMAIS HOLANDA", HOLANDA,
                                             [{"nome": "a.txt", "texto": "um exemplo", "criado": ""}])])
    servidor.app.dependency_overrides[servidor.usuario] = lambda: {"id": 1}
    try:
        lista = TestClient(servidor.app).get("/api/projetos").json()["projetos"]
    finally:
        servidor.app.dependency_overrides.clear()
    jan = next(p for p in lista if p["nome"] == "JAN DE WOLF")
    assert jan["arquivos"] == 1 and jan["claude_nome"] == "ANIMAIS HOLANDA"
    assert json.dumps(lista).count("um exemplo") == 0


def test_o_agente_apagado_nao_volta(agentes):
    claude_projetos.sincronizar(1, [_projeto("u-trad", "TRADUÇÃO", "Você é um agente de tradução. " * 20)])
    trad = banco.um("SELECT * FROM projetos_roteiro WHERE claude_uuid='u-trad'")
    claude_projetos.apagado(1, trad)
    banco.executar("DELETE FROM projetos_roteiro WHERE id=?", trad["id"])
    r = claude_projetos.sincronizar(1, [_projeto("u-trad", "TRADUÇÃO", "Você é um agente de tradução. " * 20)])
    assert r["ignorados"] == ["TRADUÇÃO"]
    assert banco.um("SELECT * FROM projetos_roteiro WHERE claude_uuid='u-trad'") is None
