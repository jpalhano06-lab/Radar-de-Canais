"""O roteiro em passos e o limite do Claude (2026-10-25), sem rede: o Claude é de mentira."""
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, diagnostico, fila, roteiro_claude, tempo  # noqa: E402

RASCUNHO = " ".join(["palavra"] * 300) + "."
REVISADO = " ".join(["revisada"] * 300) + "."
PESQUISA = "FATOS:\n- O valor é 241,30 por semana (https://www.gov.uk)\nÂNGULO: x\nGANCHO: y\nLACUNAS:\n- a data do reajuste"


@pytest.fixture
def pastas(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    monkeypatch.setattr(roteiro_claude, "PASTA", tmp_path / "roteiros")
    monkeypatch.setattr(roteiro_claude, "ANDAMENTO", tmp_path / "andamento")
    monkeypatch.setattr(tempo, "ritmo", lambda *a: {"ppm": 150})
    yield tmp_path
    if banco._CON:
        banco._CON.close()
    banco._CON = None


class Claude:
    """Responde cada passo pelo começo das instruções; `falhar` = {passo: exceção} para um passo dar errado."""
    def __init__(self, falhar=None, revisao=None):
        self.chamadas, self.falhar = [], dict(falhar or {})
        self.revisao = revisao if revisao is not None else f"<<<ROTEIRO\n{REVISADO}\nROTEIRO>>>\nNOTAS:\n- encurtei o gancho"

    def __call__(self, sistema, pedido, modelo="", ferramentas=()):
        passo = ("pesquisa" if sistema.startswith("Você levanta") else "esboco" if sistema.startswith("Você planeja")
                 else "revisao" if sistema.startswith("Você é o editor") else "escrita")
        self.chamadas.append((passo, ferramentas, pedido))
        if passo in self.falhar:
            raise self.falhar.pop(passo)
        return {"pesquisa": PESQUISA, "esboco": "PARTE 1 | gancho | 241,30 | 300", "escrita": RASCUNHO,
                "revisao": self.revisao}[passo]


def _gerar(chave="fila-1"):
    return roteiro_claude.gerar(usuario_id=1, titulo="Pensão no inverno", link="", minutos=2, lingua="inglês",
                                projeto_id=None, observacoes="", chave=chave)


def test_quatro_passos_em_ordem_e_so_a_pesquisa_com_a_web(pastas, monkeypatch):
    claude = Claude()
    monkeypatch.setattr(roteiro_claude, "_claude", claude)
    r = _gerar()
    assert [c[0] for c in claude.chamadas] == ["pesquisa", "esboco", "escrita", "revisao"]
    assert claude.chamadas[0][1] == ("WebSearch", "WebFetch")
    assert all(c[1] == () for c in claude.chamadas[1:])
    # a escrita recebe a pesquisa e o esboço; a pesquisa não recebe as observações nem o canal
    assert "241,30" in claude.chamadas[2][2] and "PARTE 1" in claude.chamadas[2][2]
    assert r["roteiro"].startswith("revisada") and r["pulados"] == []
    assert [p["passo"] for p in r["passos"]] == ["pesquisa", "esboco", "escrita", "revisao"]
    assert r["lacunas"] == "- a data do reajuste" and "encurtei" in r["notas_revisao"]
    assert "gov.uk" in r["pesquisa"]
    assert not (pastas / "andamento" / "fila-1").exists()        # o rascunho some quando o roteiro fica pronto


def test_pesquisa_que_falha_e_pulada_e_dita(pastas, monkeypatch):
    claude = Claude(falhar={"pesquisa": RuntimeError("sem busca")})
    monkeypatch.setattr(roteiro_claude, "_claude", claude)
    r = _gerar()
    assert r["pulados"] == ["Pesquisa na web"]
    assert r["passos"][0]["estado"] == "pulado" and "sem busca" in r["passos"][0]["nota"]
    assert "Sem pesquisa" in claude.chamadas[1][2]


def test_revisao_fora_do_formato_fica_o_rascunho(pastas, monkeypatch):
    monkeypatch.setattr(roteiro_claude, "_claude", Claude(revisao="Achei ótimo, sem mudanças."))
    r = _gerar()
    assert r["roteiro"].startswith("palavra") and r["pulados"] == ["Revisão"]


def test_revisao_cortada_no_meio_nao_troca_o_roteiro(pastas, monkeypatch):
    monkeypatch.setattr(roteiro_claude, "_claude", Claude(revisao="<<<ROTEIRO\nsó o começo.\nROTEIRO>>>\nNOTAS:"))
    assert _gerar()["roteiro"].startswith("palavra")


def test_revisao_que_corta_o_rascunho_comprido_vale(pastas, monkeypatch):
    # pedido de 2 minutos (300 palavras), rascunho de 600: o corte para 300 é a revisão fazendo o trabalho
    claude = Claude()
    comprido = " ".join(["palavra"] * 600) + "."
    monkeypatch.setattr(roteiro_claude, "_claude",
                        lambda s, p, **k: comprido if s.startswith("Você é roteirista") else claude(s, p, **k))
    assert _gerar()["roteiro"].startswith("revisada")


def test_limite_no_meio_e_a_volta_segue_do_passo_que_faltou(pastas, monkeypatch):
    claude = Claude(falhar={"revisao": roteiro_claude.LimiteDoClaude("limite", time.time() + 600)})
    monkeypatch.setattr(roteiro_claude, "_claude", claude)
    with pytest.raises(roteiro_claude.LimiteDoClaude):
        _gerar()
    assert (pastas / "andamento" / "fila-1" / "escrita.txt").exists()
    claude.chamadas.clear()
    r = _gerar()
    assert [c[0] for c in claude.chamadas] == ["revisao"]
    assert r["roteiro"].startswith("revisada") and len(r["passos"]) == 4


def test_limite_na_pesquisa_nao_vira_pulado(pastas, monkeypatch):
    monkeypatch.setattr(roteiro_claude, "_claude",
                        Claude(falhar={"pesquisa": roteiro_claude.LimiteDoClaude("limite", time.time() + 600)}))
    with pytest.raises(roteiro_claude.LimiteDoClaude):
        _gerar()


# ---------------------------------------------------------------- a hora em que o limite volta

BRT = timezone(timedelta(hours=-3))


def test_volta_do_limite_pela_hora_do_aviso():
    agora = datetime(2026, 10, 25, 2, 0, tzinfo=BRT)
    texto = "You've hit your session limit · resets 4:10am (America/Sao_Paulo)"
    assert roteiro_claude.volta_do_limite(texto, agora) == datetime(2026, 10, 25, 4, 12, tzinfo=BRT).timestamp()
    # passou da hora hoje: é amanhã
    depois = datetime(2026, 10, 25, 5, 0, tzinfo=BRT)
    assert roteiro_claude.volta_do_limite(texto, depois) == datetime(2026, 10, 26, 4, 12, tzinfo=BRT).timestamp()
    assert roteiro_claude.volta_do_limite("resets 3pm", agora) == datetime(2026, 10, 25, 15, 2, tzinfo=BRT).timestamp()


def test_volta_do_limite_semanal_com_data_e_o_formato_antigo():
    agora = datetime(2026, 10, 25, 2, 0, tzinfo=BRT)
    semanal = "You've hit your weekly limit · resets Oct 28, 4am (America/Sao_Paulo)"
    assert roteiro_claude.volta_do_limite(semanal, agora) == datetime(2026, 10, 28, 4, 2, tzinfo=BRT).timestamp()
    assert roteiro_claude.volta_do_limite("Claude AI usage limit reached|1761364800", agora) == 1761364800 + 120
    assert roteiro_claude.volta_do_limite("limit reached", agora) == agora.timestamp() + 30 * 60


class Rodou:
    def __init__(self, saida):
        self.stdout, self.stderr = saida, ""


def test_claude_reconhece_o_limite(monkeypatch, tmp_path):
    monkeypatch.setattr(roteiro_claude, "VAZIA", tmp_path)
    monkeypatch.setattr(roteiro_claude.shutil, "which", lambda _n: "claude")
    resposta = {"is_error": True, "result": "You've hit your session limit · resets 4:10am (America/Sao_Paulo)"}
    monkeypatch.setattr(roteiro_claude.subprocess, "run", lambda *a, **k: Rodou(json.dumps(resposta)))
    with pytest.raises(roteiro_claude.LimiteDoClaude) as erro:
        roteiro_claude._claude("s", "p")
    assert erro.value.volta > time.time()


def test_claude_com_ferramentas_libera_so_elas(monkeypatch, tmp_path):
    monkeypatch.setattr(roteiro_claude, "VAZIA", tmp_path)
    monkeypatch.setattr(roteiro_claude.shutil, "which", lambda _n: "claude")
    comandos = []

    def rodar(comando, **_k):
        comandos.append(comando)
        return Rodou(json.dumps({"is_error": False, "result": "ok"}))
    monkeypatch.setattr(roteiro_claude.subprocess, "run", rodar)
    roteiro_claude._claude("s", "p")
    roteiro_claude._claude("s", "p", ferramentas=("WebSearch", "WebFetch"))
    assert comandos[0][comandos[0].index("--tools") + 1] == "" and "--allowedTools" not in comandos[0]
    assert comandos[1][comandos[1].index("--tools") + 1] == "WebSearch,WebFetch"
    assert comandos[1][comandos[1].index("--allowedTools") + 1] == "WebSearch,WebFetch"


# ---------------------------------------------------------------- a fila esperando o limite

class Limite(RuntimeError):
    def __init__(self, volta):
        super().__init__("limite")
        self.volta = volta


class Roteirista:
    def __init__(self, volta=None):
        self.volta, self.pedidos = volta, []

    def gerar(self, **pedido):
        self.pedidos.append(pedido)
        if self.volta:
            raise Limite(self.volta)
        return {"nome": "r-" + pedido["titulo"]}


class Fabrica:
    def producoes(self):
        return {"andamento": [], "prontos": []}

    def produzir(self, nome, confirmar):
        pass


def _volta(rot):
    return fila.passo(fabrica=Fabrica(), roteirista=rot, em_thread=False,
                      config_canal=lambda uid, cid: {}, ritmo=lambda uid, perfil, lingua: {"ppm": 150})


def test_fila_espera_o_limite_e_nao_pede_mais_roteiro(pastas):
    fila.definir_limite(1)
    a = fila.criar(1, {"titulo": "A", "caracteres": 5000, "revisar": True}, True)
    b = fila.criar(1, {"titulo": "B", "caracteres": 5000, "revisar": True}, True)
    rot = Roteirista(volta=time.time() + 600)
    _volta(rot)
    assert fila.item(1, a["id"])["estado"] == "limite" and "Esperando o limite" in fila.item(1, a["id"])["passo"]
    assert fila.item(1, b["id"])["estado"] == "na_fila"        # o segundo nem foi pedido: bateria no mesmo limite
    assert [p["titulo"] for p in rot.pedidos] == ["A"] and rot.pedidos[0]["chave"] == f"fila-{a['id']}"
    _volta(Roteirista())
    assert fila.item(1, b["id"])["estado"] == "na_fila"        # ainda dentro do limite


def test_fila_volta_sozinha_quando_o_limite_passa(pastas):
    a = fila.criar(1, {"titulo": "A", "caracteres": 5000, "revisar": True}, True)
    _volta(Roteirista(volta=time.time() + 600))
    fila.pausar(time.time() - 1)
    _volta(Roteirista())
    assert fila.item(1, a["id"])["estado"] == "sua_vez"


def test_tentar_agora_tira_a_pausa(pastas):
    a = fila.criar(1, {"titulo": "A", "caracteres": 5000, "revisar": True}, True)
    _volta(Roteirista(volta=time.time() + 600))
    fila.tentar(1, a["id"])
    assert fila.pausado_ate() == 0 and fila.item(1, a["id"])["estado"] == "na_fila"
    _volta(Roteirista())
    assert fila.item(1, a["id"])["estado"] == "sua_vez"


def test_quem_espera_o_limite_fica_no_bloco_na_fila(pastas):
    item = {"id": 1, "estado": "limite", "projeto": "", "pedido": {"titulo": "A"}, "passo": "Esperando", "criado": ""}
    b = diagnostico.blocos([item], {"andamento": [], "prontos": []})
    assert [x["id"] for x in b["na_fila"]] == [1] and b["precisa_voce"] == []
