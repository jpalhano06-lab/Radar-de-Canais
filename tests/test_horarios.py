"""O melhor horário do próprio canal, sem banco e sem rede."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import horarios  # noqa: E402

ESTREIA = datetime(2026, 10, 5, 0, tzinfo=timezone.utc)      # uma segunda-feira, meia-noite UTC


def _video(rendimentos, estreia=ESTREIA, pular_h=horarios.IGNORAR_H):
    """Um vídeo com uma leitura por hora. `rendimentos` são as views ganhas em cada hora depois do corte da estreia."""
    inicio = estreia + timedelta(hours=pular_h)
    leituras, views = [], 1000
    for i, ganho in enumerate([0] + list(rendimentos)):
        views += ganho
        hora = inicio + timedelta(hours=i)
        leituras.append({"quando": hora.isoformat()[:13], "views": views})
    return {"publicado": estreia.isoformat().replace("+00:00", "Z"), "leituras": leituras}


def _bastante(videos):
    """Repete os vídeos até passar do mínimo, para o resumo considerar a conta suficiente."""
    return [dict(v) for v in videos for _ in range(horarios.MIN_VIDEOS)]


def test_as_views_caem_na_hora_local_em_que_entraram():
    # 24 h de corte sobre a meia-noite de segunda UTC: a primeira hora contada é meia-noite UTC de terça,
    # que em Brasília (-3) é 21 h de segunda
    m = horarios.matriz([_video([500])])
    assert m["matriz"][0][21] == 1.0          # segunda, faixa das 21 h: o vídeo todo
    assert m["videos"] == 1 and m["horas"] == 1


def test_o_fuso_desloca_a_hora():
    em_utc = horarios.matriz([_video([500])], fuso_min=0)
    assert em_utc["matriz"][1][0] == 1.0      # a mesma hora em UTC é meia-noite de terça


def test_as_primeiras_24_horas_nao_contam():
    # leituras começando na própria estreia: as 24 primeiras horas são descartadas, sobra uma
    v = _video([100] * 25, pular_h=0)
    m = horarios.matriz([v])
    assert m["horas"] == 1


def test_cada_video_pesa_igual_mesmo_o_que_estourou():
    normal = [_video([0, 100]) for _ in range(5)]            # rendem na segunda hora contada
    estourou = _video([1_000_000, 0])                        # rende tudo na primeira, com 10 mil vezes mais views
    m = horarios.matriz(normal + [estourou])
    linha = m["matriz"][0]
    assert round(linha[21], 3) == 1.0                        # o que estourou entra valendo 1, não 1 milhão
    assert round(linha[22], 3) == 5.0                        # os cinco normais valem 5
    assert linha[22] > linha[21]                             # e por isso ganham do viral


def test_buraco_largo_entre_leituras_e_descartado():
    estreia = ESTREIA
    inicio = estreia + timedelta(hours=horarios.IGNORAR_H)
    longe = inicio + timedelta(hours=horarios.BURACO_MAX_H + 1)
    v = {"publicado": estreia.isoformat().replace("+00:00", "Z"),
         "leituras": [{"quando": inicio.isoformat()[:13], "views": 1000},
                      {"quando": longe.isoformat()[:13], "views": 9000}]}
    assert horarios.matriz([v])["horas"] == 0


def test_buraco_curto_e_espalhado_pelas_horas_cobertas():
    estreia = ESTREIA
    inicio = estreia + timedelta(hours=horarios.IGNORAR_H)
    depois = inicio + timedelta(hours=3)
    v = {"publicado": estreia.isoformat().replace("+00:00", "Z"),
         "leituras": [{"quando": inicio.isoformat()[:13], "views": 1000},
                      {"quando": depois.isoformat()[:13], "views": 1300}]}
    m = horarios.matriz([v])
    assert m["horas"] == 3
    linha = m["matriz"][0]
    assert [round(linha[h], 4) for h in (21, 22, 23)] == [0.3333, 0.3333, 0.3333]


def test_views_que_cairam_nao_contam():
    estreia = ESTREIA
    inicio = estreia + timedelta(hours=horarios.IGNORAR_H)
    v = {"publicado": estreia.isoformat().replace("+00:00", "Z"),
         "leituras": [{"quando": inicio.isoformat()[:13], "views": 5000},
                      {"quando": (inicio + timedelta(hours=1)).isoformat()[:13], "views": 4000}]}
    assert horarios.matriz([v])["horas"] == 0


def test_as_24_horas_viram_oito_faixas_de_tres():
    somas = [[0.0] * 24 for _ in range(7)]
    somas[0][0] = somas[0][1] = somas[0][2] = 1.0            # as três primeiras horas de segunda
    somas[3][18] = 5.0                                       # 18 h de quinta
    f = horarios.faixas(somas)
    assert len(f["segunda"]) == 8
    assert f["segunda"][0] == 3.0                            # faixa 0-2 somada
    assert f["quinta"][6] == 5.0                             # faixa 18-20
    assert f["geral"][0] == 3.0 and f["geral"][6] == 5.0     # o geral soma a semana


def test_sem_curva_suficiente_o_radar_diz_que_nao_sabe():
    r = horarios.resumo([_video([500])])                     # um vídeo, uma hora
    assert r["suficiente"] is False
    assert r["pico"] is None and r["ranking"] == []
    assert r["minimo"] == {"videos": horarios.MIN_VIDEOS, "horas": horarios.MIN_HORAS}


def test_sem_video_nenhum_nao_quebra_e_nao_inventa():
    r = horarios.resumo([])
    assert r["suficiente"] is False and r["pico"] is None
    assert r["por_dia"]["geral"] == [0.0] * 8
    assert r["videos"] == 0 and r["horas"] == 0


def test_com_curva_suficiente_sai_o_pico_e_o_ranking():
    # cada vídeo rende forte na faixa das 18-20 (Brasília) e fraco no resto
    rendimentos = []
    for h in range(27):                                      # horas contadas, passando do mínimo com a repetição
        rendimentos.append(900 if 21 <= (h + 21) % 24 <= 23 else 100)
    r = horarios.resumo(_bastante([_video(rendimentos)]))
    assert r["suficiente"] is True
    assert r["videos"] >= horarios.MIN_VIDEOS and r["horas"] >= horarios.MIN_HORAS
    assert r["pico"]["inicio"] == 21 and r["pico"]["fim"] == 23
    assert r["ranking"][0] == r["pico"]
    assert round(sum(r["por_dia"]["geral"]), 3) == 1.0       # as partes fecham em 1
    assert r["pico"]["parte"] == max(f["parte"] for f in r["ranking"])


def test_a_matriz_entregue_tem_sete_linhas_de_vinte_e_quatro():
    r = horarios.resumo([_video([500])])
    assert len(r["matriz"]) == 7
    assert all(len(linha) == 24 for linha in r["matriz"])
    assert r["faixas"] == [[0, 2], [3, 5], [6, 8], [9, 11], [12, 14], [15, 17], [18, 20], [21, 23]]
    assert r["dias"][0] == "segunda" and r["dias"][6] == "domingo"
