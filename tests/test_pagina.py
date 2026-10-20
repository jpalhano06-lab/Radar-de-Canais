"""O que a extensão lê na página do YouTube (sem cota): vídeos vistos, canal lido e o Vídeos que estouraram."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, garimpo, pagina  # noqa: E402

CANAL = "UC" + "a" * 22


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    monkeypatch.setattr(garimpo, "_completar", lambda c, rapido=False: True)   # sem Groq no teste
    yield
    banco._CON.close()
    banco._CON = None


BICHOS = ["octopus", "snow leopard", "honey badger", "axolotl", "shoebill", "pangolin", "narwhal", "okapi", "tardigrade",
          "aye-aye", "blobfish", "saiga", "fossa", "quokka", "dugong", "kakapo"]


def _video(i, views, dias, dur=600):
    # títulos variados: títulos numerados em série são barrados pela regra de risco
    return {"id": f"vid{i:08d}", "titulo": f"Why the {BICHOS[i % len(BICHOS)]} survives where nothing else can", "canal_id": CANAL, "views": views,
            "dias": dias, "duracao_s": dur}


def test_canal_novo_e_lido_e_o_estouro_entra(db):
    r = pagina.vistos([_video(1, 900_000, 20)])
    assert r["ler"] == [CANAL] and r["videos"]["vid00000001"]["nota"] is None
    # a página de vídeos do canal: 12 vídeos maduros com uns 20 mil e o que estourou
    lista = [_video(i, 20_000, 30 + i * 10) for i in range(2, 14)] + [_video(1, 900_000, 20)]
    feito = pagina.canal_lido({"id": CANAL, "titulo": "Bichos", "inscritos": 4_000, "videos_total": 13}, lista)
    assert feito["normal"] == 20_000 and feito["entrou"]
    assert banco.um("SELECT nota FROM outliers WHERE video_id='vid00000001'")["nota"] == 45.0
    # o canal já é conhecido: a próxima vez que o vídeo aparece na tela vem com a nota e não pede para ler
    r = pagina.vistos([_video(1, 950_000, 21)])
    assert r["ler"] == [] and r["videos"]["vid00000001"]["nota"] == 47.5
    assert banco.um("SELECT views FROM videos WHERE id='vid00000001'")["views"] == 950_000


def test_canal_velho_ou_grande_sem_idade_nao_entra(db):
    velho = [_video(i, 30_000, 700 + i) for i in range(1, 8)]
    assert not pagina.canal_lido({"id": CANAL, "inscritos": 2_000, "videos_total": 7}, velho)["entrou"]
    banco.executar("DELETE FROM canais")
    novo_mas_grande = [_video(i, 30_000, 40 + i * 5) for i in range(1, 30)]
    assert not pagina.canal_lido({"id": CANAL, "inscritos": 500_000, "videos_total": 300}, novo_mas_grande)["entrou"]


def test_lixo_da_pagina_e_ignorado(db):
    r = pagina.vistos([{"id": "curto"}, {"id": "vid00000009", "canal_id": "não é canal", "views": "x"}, "texto"])
    assert list(r["videos"]) == ["vid00000009"] and r["ler"] == []


def test_dados_do_canal_monetizacao_e_em_alta(db):
    assert pagina.canal_dados(CANAL, 1) is None          # sem ler o canal, a extensão lê a página antes
    lista = [_video(i, 20_000, 30 + i * 4) for i in range(2, 14)] + [_video(1, 900_000, 20)]
    pagina.canal_lido({"id": CANAL, "titulo": "Bichos", "inscritos": 4_000, "videos_total": 13}, lista)
    pagina.vistos([], {"id": CANAL, "anuncios": True, "membros": True})
    d = pagina.canal_dados(CANAL, 1)
    assert (d["anuncios"], d["membros"], d["normal_longos"]) == (1, 1, 20_000)
    assert len(d["videos"]) == 13 and d["videos"][-1]["nota"] == 45.0     # do mais antigo ao mais novo
    assert d["inscritos_dias"] == [{"dia": banco.agora()[:10], "inscritos": 4_000}]
    banco.executar("UPDATE canais SET no_radar=1 WHERE id=?", CANAL)
    assert [c["id"] for c in pagina.em_alta()] == [CANAL]


def test_videos_do_nicho_sao_os_estouros_dos_parecidos(db, monkeypatch):
    # dois canais parecidos já lidos: um vídeo de cada estourou, o resto é normal
    for n, outro in enumerate(["UC" + "b" * 22, "UC" + "c" * 22]):
        lista = [{**_video(n * 100 + i, 20_000, 30 + i * 10), "canal_id": outro} for i in range(2, 14)]
        lista.append({**_video(n * 100 + 1, 400_000 * (n + 1), 20), "canal_id": outro})
        pagina.canal_lido({"id": outro, "titulo": f"Parecido {n}", "inscritos": 4_000, "videos_total": 13}, lista)
    monkeypatch.setattr(garimpo, "parecidos", lambda cid: [{"id": "UC" + "b" * 22}, {"id": "UC" + "c" * 22}])
    vs = garimpo.videos_do_nicho(CANAL)
    assert [v["id"] for v in vs] == ["vid00000101", "vid00000001"]   # do maior estouro para o menor
    assert vs[0]["nota"] == 40.0 and vs[0]["canal"] == "Parecido 1"


def test_canal_antigo_que_comecou_a_postar_agora_ganha_o_primeiro_video_exato(db, monkeypatch):
    # canal criado em 2014 com 136 vídeos: a página mostra só os mais novos, então o primeiro vídeo não é sabido
    lista = [_video(i, 20_000, 30 + i * 10) for i in range(1, 14)]
    pagina.canal_lido({"id": CANAL, "titulo": "Velho", "inscritos": 10_000, "videos_total": 136}, lista)
    banco.executar("UPDATE canais SET criado_em='2014-01-01T00:00:00Z' WHERE id=?", CANAL)
    assert not banco.um("SELECT primeiro_exato FROM canais WHERE id=?", CANAL)["primeiro_exato"]
    # a lista de envios do canal diz quando foi o primeiro vídeo de verdade: há 309 dias
    from datetime import datetime, timedelta, timezone
    primeiro = (datetime.now(timezone.utc) - timedelta(days=309)).isoformat()
    monkeypatch.setattr(pagina.youtube, "primeiro_envio", lambda cid, total=None: primeiro)
    d = pagina.canal_dados(CANAL, 1)
    assert d["primeiro_exato"] and round(d["meses_postando"] * 30.44) in (308, 309, 310)
    # uma releitura da página (que de novo não vê todos os vídeos) não apaga a data exata
    pagina.canal_lido({"id": CANAL, "titulo": "Velho", "inscritos": 10_000, "videos_total": 136}, lista)
    assert banco.um("SELECT primeiro_video, primeiro_exato FROM canais WHERE id=?", CANAL) == {"primeiro_video": primeiro, "primeiro_exato": 1}


def test_ultimos_videos_do_canal_parecido_com_a_nota(db):
    lista = [_video(i, 20_000, 30 + i * 10) for i in range(2, 14)] + [_video(1, 400_000, 20), _video(99, 5_000, 1, dur=40)]
    pagina.canal_lido({"id": CANAL, "titulo": "Bichos", "inscritos": 4_000, "videos_total": 14}, lista)
    vs = garimpo.ultimos_videos(CANAL, 3)
    assert [v["id"] for v in vs] == ["vid00000001", "vid00000002", "vid00000003"]   # do mais novo, sem Shorts
    assert vs[0]["nota"] == 20.0


def _concorrente(cid, normal, dias_postando, ultimo_dias, fase):
    from datetime import datetime, timedelta, timezone
    agora = datetime.now(timezone.utc)
    banco.gravar("canais", "id", {"id": cid, "titulo": f"Canal {cid[-3:]}", "base_longos": normal, "fase": fase,
                                  "primeiro_video": (agora - timedelta(days=dias_postando)).isoformat(),
                                  "ultimo_video": (agora - timedelta(days=ultimo_dias)).isoformat()})


def test_concorrentes_do_nicho_so_gastam_cota_quando_pedido(db, monkeypatch):
    chamou = []
    monkeypatch.setattr(garimpo, "parecidos", lambda cid: chamou.append(cid) or [])
    assert garimpo.concorrentes(CANAL) == {"medido": False}   # sem a lista guardada, não procura sozinho
    assert chamou == []
    # 3 concorrentes: um novo que deu certo e cresce, um ativo estável e um parado
    ids = ["UC" + "x" * 19 + n for n in ("001", "002", "003")]
    _concorrente(ids[0], 40_000, 60, 2, "crescendo")
    _concorrente(ids[1], 8_000, 900, 5, "estavel")
    _concorrente(ids[2], 3_000, 1500, 200, "parado")
    banco.executar("INSERT INTO traducoes (chave, dados, criado) VALUES (?,?,?)", f"parecidos:{CANAL}", json.dumps(ids), banco.agora())
    monkeypatch.setattr(garimpo, "parecidos", lambda cid: [{"id": i} for i in ids])
    r = garimpo.concorrentes(CANAL)
    assert r["medido"] and r["total"] == 3 and r["ativos"] == 2 and r["crescendo"] == 1 and r["novos_que_deram_certo"] == 1
    assert 0 <= r["nota"] <= 10 and r["rotulo"]
    assert [c["id"] for c in r["canais"]][0] == ids[0]   # o que mais faz view por vídeo primeiro
