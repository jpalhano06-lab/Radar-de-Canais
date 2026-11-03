"""O garimpo gasta a cota nas buscas e não fica preso no Groq (sem rede).

Caso real (2026-10-30): o garimpo começou com 11.989 unidades e 20 horas depois tinha gastado 1.207, sem nenhuma busca.
149 canais do Radar tinham capas que não existem mais (404): o Groq recusava, o canal ficava sem a resposta do rosto, e
cada canal medido de novo perguntava outra vez, esperando até 90 s pelo limite do minuto."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, garimpo, ia, medir, youtube  # noqa: E402

CANAL = "UC" + "r" * 22


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    yield
    banco._CON.close()
    banco._CON = None


class _Resposta:
    def __init__(self, status, texto="", cabecalhos=None):
        self.status_code, self.text, self.headers = status, texto, cabecalhos or {}


def test_pedido_recusado_nao_tenta_de_novo(monkeypatch):
    """400 (capa que não existe mais) é o mesmo em toda chave: perguntar de novo só gasta o limite do minuto."""
    pedidos = []
    monkeypatch.setattr(ia, "_chave", lambda modelo="": "chave")
    monkeypatch.setattr(ia._CLIENTE, "post", lambda *a, **k: pedidos.append(1) or _Resposta(400, "failed to retrieve media"))
    assert ia._perguntar("modelo", "sistema", "conteudo", esperar=90) is None
    assert len(pedidos) == 1


def test_medir_de_novo_nao_pergunta_ao_groq(db, monkeypatch):
    banco.gravar("canais", "id", {"id": CANAL, "titulo": "Canal", "no_radar": 1, "nicho": "Finanças",
                                  "subnicho": "Bancos", "medido": "2026-01-01"})
    monkeypatch.setattr(youtube, "cota_hoje", lambda: {"usado": 0, "livre": 10000})
    monkeypatch.setattr(medir, "medir_canais", lambda ids, forcar=False: {CANAL: banco.um("SELECT * FROM canais WHERE id=?", CANAL)})
    monkeypatch.setattr(ia, "sem_rosto", lambda capas: pytest.fail("o medir de novo perguntou ao Groq"))
    monkeypatch.setattr(ia, "nicho", lambda *a: pytest.fail("o medir de novo perguntou ao Groq"))
    assert garimpo.remedir(print, 1000) == 1


def test_as_buscas_vem_antes_de_completar_os_pendentes(db, monkeypatch):
    ordem = []
    monkeypatch.setattr(youtube, "cota_hoje", lambda: {"usado": 0, "livre": 10000, "total": 10000, "chaves": 1})
    monkeypatch.setattr(garimpo, "completar_pendentes", lambda *a, **k: ordem.append("pendentes"))
    monkeypatch.setattr(garimpo, "remedir", lambda *a, **k: 0)
    monkeypatch.setattr(garimpo, "_proximos_termos", lambda: [("Finanças", "credit card")])
    monkeypatch.setattr(youtube, "buscar", lambda *a, **k: ordem.append("busca") or [])
    monkeypatch.setattr(garimpo, "achar_parecidos_dos_salvos", lambda *a, **k: None)
    monkeypatch.setattr(garimpo, "aprender_termos", lambda *a, **k: 0)
    garimpo.rodar(print)
    assert ordem == ["busca", "pendentes"]


def test_capa_que_sumiu_fica_de_fora(monkeypatch):
    enviadas = []
    monkeypatch.setattr(ia, "_existe", lambda url: "apagado" not in url)
    monkeypatch.setattr(ia, "_perguntar", lambda modelo, sistema, conteudo, **k: enviadas.extend(
        p["image_url"]["url"] for p in conteudo if p["type"] == "image_url") or {"apresentador": False})
    assert ia.sem_rosto(["apagado1", "a", "apagado2", "b", "c", "d"]) is True
    assert enviadas == ["a", "b", "c"]
    monkeypatch.setattr(ia, "_perguntar", lambda *a, **k: pytest.fail("perguntou sem nenhuma capa"))
    assert ia.sem_rosto(["apagado1", "apagado2"]) is None


def test_um_termo_ruim_nao_para_o_garimpo(db, monkeypatch):
    feitas = []
    monkeypatch.setattr(youtube, "cota_hoje", lambda: {"usado": 0, "livre": 10000, "total": 10000, "chaves": 1})
    monkeypatch.setattr(garimpo, "completar_pendentes", lambda *a, **k: 0)
    monkeypatch.setattr(garimpo, "remedir", lambda *a, **k: 0)
    monkeypatch.setattr(garimpo, "_proximos_termos", lambda: [("Finanças", "ruim"), ("Finanças", "bom")])

    def buscar(termo, **k):
        if termo == "ruim":
            raise RuntimeError("quebrou")
        feitas.append(termo)
        return []
    monkeypatch.setattr(youtube, "buscar", buscar)
    monkeypatch.setattr(garimpo, "achar_parecidos_dos_salvos", lambda *a, **k: None)
    monkeypatch.setattr(garimpo, "aprender_termos", lambda *a, **k: 0)
    resultado = garimpo.rodar(print)
    assert feitas == ["bom"] and resultado["buscas"] == 1
    assert banco.um("SELECT estado FROM garimpos")["estado"] == "pronto"


def test_completar_pendentes_tem_prazo(db, monkeypatch):
    for n in range(5):
        banco.gravar("canais", "id", {"id": f"UC{n:022d}", "titulo": "c", "no_radar": 1})
    relogio = iter(range(0, 10000, 100))
    monkeypatch.setattr(garimpo.time, "monotonic", lambda: next(relogio))   # cada canal leva 100 s
    monkeypatch.setattr(garimpo, "_completar", lambda c: None)
    assert garimpo.completar_pendentes(print, minutos=5) == 3


def test_garimpo_recomeca_a_cada_pausa_enquanto_a_fatia_aguenta(db, monkeypatch):
    """Desde 2026-11-01 o garimpo fica rodando: recomeça PAUSA_MINUTOS depois do anterior, e só para quando o que
    resta da fatia do dia não paga nem uma busca (ou quando a pessoa desliga o 'pode gastar')."""
    from datetime import datetime, timedelta, timezone

    def ha(minutos):
        return {"inicio": (datetime.now(timezone.utc) - timedelta(minutes=minutos)).isoformat()}
    monkeypatch.setattr(garimpo, "fatia_do_dia", lambda: {"teto": 6000, "gasto": 0, "resta": 6000})
    assert garimpo.hora_de_garimpar(None)
    assert not garimpo.hora_de_garimpar(ha(garimpo.PAUSA_MINUTOS / 2))
    assert garimpo.hora_de_garimpar(ha(garimpo.PAUSA_MINUTOS * 2))
    monkeypatch.setattr(garimpo, "fatia_do_dia", lambda: {"teto": 6000, "gasto": 5990, "resta": 10})
    assert not garimpo.hora_de_garimpar(None)       # o que resta não paga nem uma busca
    monkeypatch.setattr(garimpo, "fatia_do_dia", lambda: {"teto": 6000, "gasto": 0, "resta": 6000})
    garimpo.definir_ligado(False)
    assert not garimpo.hora_de_garimpar(None)       # a pessoa desligou o "pode gastar"


def test_cota_do_dia_do_groq_nao_vira_espera_de_15_segundos(monkeypatch):
    """2026-11-01: as 11 chaves estouraram a cota de TOKENS DO DIA do modelo de visão ("try again in 31m41.6s").
    A conta antiga procurava só um número seguido de "s", não enxergava o "31m", dormia 15 segundos e tentava de
    novo: o fim do garimpo gastava os 45 minutos inteiros dormindo e não completava um canal."""
    assert ia._espera_pedida("Please try again in 31m41.663999999s.") == pytest.approx(1901.664)
    assert ia._espera_pedida("try again in 15.5s") == 15.5
    assert ia._espera_pedida("try again in 2h3m1s") == 7381
    assert ia._espera_pedida("sem prazo") is None
    assert ia._espera_pedida("try again in 15.5s", {"retry-after": "1902"}) == 1902

    dormiu = []
    monkeypatch.setattr(ia.time, "sleep", lambda s: dormiu.append(s))
    monkeypatch.setattr(ia, "chaves_groq", lambda: ["a", "b"])
    monkeypatch.setattr(ia, "chaves_gemini", lambda: [])      # sem a reserva: aqui é o Groq sozinho
    monkeypatch.setattr(ia, "_ESGOTADAS", {})
    monkeypatch.setattr(ia, "_RODA", None)
    monkeypatch.setattr(ia._CLIENTE, "post", lambda *a, **k: _Resposta(
        429, "Rate limit reached ... on tokens per day (TPD): Limit 200000. Please try again in 31m41.6s."))
    assert ia._perguntar("visao", "sistema", "conteudo", esperar=90) is None
    assert dormiu == []                      # a cota do dia não se espera: a chave sai da roda
    assert ia.esgotado("visao") is True      # e aí nem vale perguntar até ela voltar
    assert ia.esgotado("texto") is False     # o limite é por modelo


def _rodar_uma_busca(monkeypatch, termo="credit card", achados=()):
    monkeypatch.setattr(youtube, "cota_hoje", lambda: {"usado": 0, "livre": 10000, "total": 10000, "chaves": 1})
    monkeypatch.setattr(garimpo, "completar_pendentes", lambda *a, **k: None)
    monkeypatch.setattr(garimpo, "remedir", lambda *a, **k: 0)
    monkeypatch.setattr(garimpo, "_proximos_termos", lambda: [("Finanças", termo)])
    monkeypatch.setattr(youtube, "buscar", lambda *a, **k: list(achados))
    monkeypatch.setattr(garimpo, "achar_parecidos_dos_salvos", lambda *a, **k: None)
    monkeypatch.setattr(garimpo, "aprender_termos", lambda *a, **k: 0)
    garimpo.rodar(print)
    return banco.um("SELECT * FROM buscas_feitas WHERE termo=?", termo)


def test_repetir_a_busca_cedo_nao_vira_lixo(db, monkeypatch):
    """Caso real (2026-11-03): com a bolsa seca o garimpo repetia o termo 10 min depois, o YouTube dava os mesmos
    canais (já no Radar), saía '0 entraram' e na segunda vez o termo virava lixo por 30 dias: os 406 termos bons
    ficaram de lado e o garimpo passou o dia com 0 buscas e 62 mil unidades paradas."""
    banco.executar("INSERT INTO buscas_feitas (termo, nicho, quando, canais, vezes, total, zeros) VALUES (?,?,?,?,?,?,?)",
                   "credit card", "Finanças", banco.agora(), 5, 1, 5, 1)
    b = _rodar_uma_busca(monkeypatch)
    assert b["vezes"] == 2 and b["zeros"] == 1


def test_zero_depois_da_espera_conta_como_lixo(db, monkeypatch):
    banco.executar("INSERT INTO buscas_feitas (termo, nicho, quando, canais, vezes, total, zeros) VALUES (?,?,?,?,?,?,?)",
                   "credit card", "Finanças", "2026-01-01T00:00:00+00:00", 0, 1, 0, 1)
    assert _rodar_uma_busca(monkeypatch)["zeros"] == 2


def test_bolsa_seca_nao_repete_termo_de_horas_atras(db, monkeypatch):
    monkeypatch.setattr(garimpo, "termos", lambda: {"Finanças": ["credit card", "stock market"]})
    banco.executar("INSERT INTO buscas_feitas (termo, nicho, quando, canais, vezes, total, zeros) VALUES (?,?,?,?,?,?,?)",
                   "credit card", "Finanças", banco.agora(), 1, 1, 1, 0)
    banco.executar("INSERT INTO buscas_feitas (termo, nicho, quando, canais, vezes, total, zeros) VALUES (?,?,?,?,?,?,?)",
                   "stock market", "Finanças", (garimpo.datetime.now(garimpo.timezone.utc) - garimpo.timedelta(days=1)).isoformat(), 1, 1, 1, 0)
    assert garimpo._proximos_termos() == [("Finanças", "stock market")]
