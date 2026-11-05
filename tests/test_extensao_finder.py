"""O que veio do Dotti Finder para a extensão: o que o servidor entrega para cada função nova."""
import io
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import banco, capas, cracha, garimpo, lente_ia, medir, molde, pagina, pedidos  # noqa: E402


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "radar.db")
    monkeypatch.setattr(banco, "_CON", None)
    return banco


def _leitura(video, horas_atras, views):
    quando = (datetime.now(timezone.utc) - timedelta(hours=horas_atras)).isoformat()
    banco.executar("INSERT INTO leituras (video_id, quando, views) VALUES (?,?,?)", video, quando, views)


def test_rpm_e_a_faixa_do_nicho_menos_a_parte_do_youtube():
    assert garimpo.rpm("Finanças") == {"nicho": "Finanças", "minimo": 8.25, "maximo": 27.5}
    assert garimpo.rpm("Assunto que não está na lista") is None


def test_velocidade_e_medida_entre_duas_leituras(base):
    _leitura("v1", 3, 1000)
    _leitura("v1", 1, 1500)
    assert medir.velocidades(["v1"])["v1"] == {"vph": 250.0, "horas": 2.0}


def test_duas_leituras_coladas_nao_viram_velocidade(base):
    """Dez minutos entre leituras multiplicaria o arredondamento da página por seis."""
    _leitura("v2", 0.3, 1000)
    _leitura("v2", 0.1, 1100)
    assert medir.velocidades(["v2"]) == {}


def test_views_que_desceram_nao_viram_velocidade_negativa(base):
    _leitura("v3", 5, 2000)
    _leitura("v3", 1, 1900)
    assert medir.velocidades(["v3"])["v3"]["vph"] == 0


def test_leituras_de_semanas_atras_nao_sao_a_velocidade_de_agora(base):
    _leitura("v4", 500, 1000)
    _leitura("v4", 1, 9000)
    assert medir.velocidades(["v4"]) == {}


def test_sem_nenhum_video_nao_pergunta_ao_banco(base):
    assert medir.velocidades([]) == {}


def test_painel_diz_se_o_video_esta_na_fila(base):
    banco.executar("INSERT INTO modelar (usuario_id, video_id, estado, quando) VALUES (?,?,?,?)", 1, "abcdefghijk", "fila", banco.agora())
    assert pagina.painel("abcdefghijk", "", 1)["modelar"] == "fila"
    assert pagina.painel("abcdefghijk", "", 2)["modelar"] == ""


AGORA = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)


def _video(dias, views, duracao=600, nota=None):
    return {"views": views, "publicado": (AGORA - timedelta(days=dias)).isoformat(), "duracao_s": duracao, "nota": nota}


def _canal(dias_de_vida):
    return {"primeiro_video": (AGORA - timedelta(days=dias_de_vida)).isoformat(), "criado_em": ""}


def test_sem_video_suficiente_nao_julga():
    x = cracha.julgar(_canal(500), [_video(1, 100), _video(2, 100)], AGORA)
    assert x["tipo"] == "sem_dados" and "2 vídeo" in x["motivos"][0]["texto"]


def test_short_nao_conta_como_video():
    x = cracha.julgar(_canal(500), [_video(i, 9_000_000, duracao=40) for i in range(1, 9)], AGORA)
    assert x["tipo"] == "sem_dados"


def test_canal_novo_com_volume_e_explosao():
    x = cracha.julgar(_canal(40), [_video(d, 300_000) for d in (2, 6, 10, 14)], AGORA)
    assert x["tipo"] == "novo_explodindo" and x["saude"] == "alta"
    assert any("40 dias de vida" in m["texto"] for m in x["motivos"])


def test_canal_antigo_com_volume_e_alta():
    assert cracha.julgar(_canal(900), [_video(d, 300_000) for d in (2, 6, 10, 14)], AGORA)["tipo"] == "alta"


def test_silencio_vale_mais_que_o_volume_e_respeita_o_ritmo_do_canal():
    """Quem posta toda semana e sumiu há 60 dias parou; quem posta por mês e sumiu há 60 dias, não."""
    semanal = cracha.julgar(_canal(900), [_video(60 + 7 * i, 50_000) for i in range(8)], AGORA)
    mensal = cracha.julgar(_canal(900), [_video(60 + 30 * i, 50_000) for i in range(8)], AGORA)
    assert semanal["tipo"] == "queda" and semanal["ritmo_dias"] == 7 and "parou de postar há 60 dias" in semanal["motivos"][0]["texto"]
    assert mensal["tipo"] != "queda" and mensal["ritmo_dias"] == 30


def test_video_de_menos_de_7_dias_nao_derruba_o_momento():
    """Vídeo recém-saído tem poucas views por ser novo, não por o canal cair."""
    videos = [_video(1, 10), _video(2, 10), _video(3, 10)] + [_video(10 + 4 * i, 40_000) for i in range(10)]
    assert cracha.julgar(_canal(900), videos, AGORA)["queda"] == 1.0


def test_videos_novos_bem_abaixo_dos_anteriores_e_queda():
    videos = [_video(10 + 4 * i, 5_000) for i in range(5)] + [_video(30 + 4 * i, 40_000) for i in range(5)]
    x = cracha.julgar(_canal(900), videos, AGORA)
    assert x["tipo"] == "queda" and x["queda"] == 0.12


def test_um_acerto_no_meio_de_videos_fracos_e_fonte_de_titulos():
    videos = [_video(5 + 5 * i, 2_000) for i in range(9)] + [_video(60, 900_000)]
    assert cracha.julgar(_canal(900), videos, AGORA)["tipo"] == "fonte"


def test_video_grande_na_media_do_canal_nao_e_acerto():
    """O típico já faz 175 mil: um de 144 mil não é acerto nenhum, mesmo com o campeão lá em cima."""
    videos = [_video(16, 144_000)] + [_video(200 + 5 * i, 175_000) for i in range(8)] + [_video(400, 2_000_000)]
    assert cracha.julgar(_canal(900), videos, AGORA)["tipo"] != "fonte"


def test_o_motivo_tem_milhar_com_ponto_e_a_frase_fica_inteira():
    videos = [_video(5 + 5 * i, 2_000) for i in range(9)] + [_video(60, 900_000)]
    motivo = next(m["texto"] for m in cracha.julgar(_canal(900), videos, AGORA)["motivos"] if m["voto"] == "fonte")
    assert motivo == "o vídeo típico faz 2.000 views, mas um acertou 900.000 há 60 dias"


def test_canal_sem_sinal_nenhum_e_fraco_e_diz_o_motivo():
    x = cracha.julgar(_canal(900), [_video(5 + 5 * i, 900) for i in range(10)], AGORA)
    assert x["tipo"] == "fraco" and x["motivos"]


def _salvo_com_outlier(nota, achado):
    banco.executar("INSERT INTO canais (id, titulo) VALUES ('UC1', 'Canal') ON CONFLICT DO NOTHING")
    banco.executar("INSERT INTO salvos (usuario_id, canal_id, criado) VALUES (1, 'UC1', '') ON CONFLICT DO NOTHING")
    video = f"v{nota}"
    banco.executar("INSERT INTO videos (id, canal_id, titulo, views) VALUES (?, 'UC1', 'Título', 900)", video)
    banco.executar("INSERT INTO outliers (video_id, canal_id, nota, achado) VALUES (?, 'UC1', ?, ?)", video, nota, achado)


def test_aviso_dos_salvos_so_traz_o_que_passou_do_corte_nas_ultimas_24_horas(base):
    agora = datetime.now(timezone.utc)
    _salvo_com_outlier(8, agora.isoformat())
    _salvo_com_outlier(3, agora.isoformat())
    _salvo_com_outlier(9, (agora - timedelta(days=3)).isoformat())
    assert [v["nota"] for v in pagina.salvos_estouraram(1)] == [8]
    assert pagina.salvos_estouraram(2) == []


def test_mesmo_molde_com_assuntos_diferentes():
    assert molde.de("Why Nobody Talks About Tesla Anymore") == molde.de("Why Nobody Talks About the Roman Empire Anymore".replace(" the Roman Empire", " Rome"))
    assert molde.de("Why Nobody Talks About Tesla Anymore") != molde.de("How I Built a Boat in 30 Days")


def test_numero_vira_marca_e_o_nome_do_canal_no_fim_nao_conta():
    assert molde.de("10 Things You Never Knew About Sharks | Canal X") == molde.de("25 Things You Never Knew About Trains")


def test_titulo_sem_estrutura_nao_tem_molde():
    assert molde.de("Tesla Cybertruck Review") == ""
    assert molde.de("") == ""


def _video_molde(vid, canal, titulo, views):
    banco.executar("INSERT INTO canais (id, titulo, base_longos) VALUES (?, ?, 1000) ON CONFLICT DO NOTHING", canal, canal)
    banco.executar("INSERT INTO videos (id, canal_id, titulo, views, duracao_s) VALUES (?,?,?,?,600)", vid, canal, titulo, views)


def test_molde_preenche_e_conta_quem_escreve_assim(base):
    _video_molde("a", "UC1", "Why Nobody Talks About Tesla", 9000)
    _video_molde("b", "UC2", "Why Nobody Talks About Rome", 3000)
    _video_molde("c", "UC2", "Why Nobody Talks About Sharks", 1000)
    _video_molde("d", "UC3", "Boat Review", 500)
    assert molde.preencher() == 4 and molde.preencher() == 0
    d = molde.parecidos("Why Nobody Talks About Trains", "c")
    assert d["total"] == 2 and d["canais"] == 2 and d["lift"] == 6.0
    assert [v["id"] for v in d["videos"]] == ["a", "b"]


def _imagem(desenhar):
    tela = Image.new("L", (320, 180), 30)
    desenhar(ImageDraw.Draw(tela))
    saida = io.BytesIO()
    tela.convert("RGB").save(saida, "JPEG")
    return saida.getvalue()


def test_capas_de_mesma_composicao_sao_parecidas_e_as_outras_nao():
    esquerda = lambda d: d.rectangle((0, 0, 150, 180), fill=230)  # noqa: E731
    quase = lambda d: d.rectangle((0, 0, 156, 180), fill=220)  # noqa: E731
    outra = lambda d: [d.rectangle((x, 0, x + 18, 180), fill=240) for x in range(0, 320, 40)]  # noqa: E731
    a, b, c = (capas.impressao(_imagem(f)) for f in (esquerda, quase, outra))
    assert capas.parecenca(a, a) == 100
    assert capas.parecenca(a, b) > capas.parecenca(a, c)


def test_impressao_cabe_no_sqlite(base):
    banco.executar("INSERT INTO capas (video_id, hash) VALUES ('x', ?)", -(1 << 63))
    assert banco.um("SELECT hash FROM capas WHERE video_id='x'")["hash"] == -(1 << 63)


def test_capa_apagada_nao_e_tentada_de_novo(base):
    banco.executar("INSERT INTO videos (id, canal_id, titulo) VALUES ('m', 'UC1', 't')")
    banco.executar("INSERT INTO outliers (video_id, canal_id, nota, achado) VALUES ('m', 'UC1', 9, '')")
    assert capas.preencher(baixar=lambda v: None) == 1
    assert capas.preencher(baixar=lambda v: None) == 0


def test_falha_de_rede_nao_marca_a_capa_como_apagada(base):
    banco.executar("INSERT INTO videos (id, canal_id, titulo) VALUES ('r', 'UC1', 't')")
    banco.executar("INSERT INTO outliers (video_id, canal_id, nota, achado) VALUES ('r', 'UC1', 9, '')")
    capas.preencher(baixar=lambda v: capas.TENTAR_DEPOIS)
    assert banco.um("SELECT COUNT(*) AS n FROM capas")["n"] == 0
    assert capas.preencher(baixar=lambda v: 7) == 1
    assert banco.um("SELECT hash FROM capas WHERE video_id='r'")["hash"] == 7


def test_parecidas_nao_devolve_o_proprio_video_e_respeita_o_minimo(base):
    _video_molde("p1", "UC1", "Um", 100)
    _video_molde("p2", "UC1", "Dois", 200)
    _video_molde("p3", "UC1", "Três", 300)
    for vid, h in (("p1", 0), ("p2", 1), ("p3", 0x7FFFFFFFFFFFFFFF)):
        banco.executar("INSERT INTO outliers (video_id, canal_id, nota, achado) VALUES (?, 'UC1', 9, '')", vid)
        banco.executar("INSERT INTO capas (video_id, hash) VALUES (?, ?)", vid, h)
    d = capas.parecidas("p1")
    assert [(v["id"], v["parecido"]) for v in d["videos"]] == [("p2", 98)] and d["indice"] == 3


def test_leitura_da_ia_fica_guardada(base, monkeypatch):
    chamadas = []
    monkeypatch.setattr(lente_ia.roteiro_claude, "_claude", lambda s, p: chamadas.append(p) or '```json\n{"resumo": "curiosidade"}\n```')
    assert lente_ia.por_que("abcdefghijk", "Título")["resumo"] == "curiosidade"
    lente_ia.por_que("abcdefghijk", "Título")
    assert len(chamadas) == 1
    lente_ia.por_que("abcdefghijk", "Título", novo=True)
    assert len(chamadas) == 2


def test_titulos_sem_nenhum_titulo_e_erro(base, monkeypatch):
    monkeypatch.setattr(lente_ia.roteiro_claude, "_claude", lambda s, p: '{"titulos": []}')
    with pytest.raises(RuntimeError):
        lente_ia.titulos("Título", "assunto")


def test_receita_da_capa_sem_resposta_da_visao_e_erro(base, monkeypatch):
    monkeypatch.setattr(lente_ia.ia, "_perguntar", lambda *a, **k: None)
    with pytest.raises(RuntimeError):
        lente_ia.receita_da_capa("abcdefghijk")


def _canal_com_videos():
    banco.executar("INSERT INTO canais (id, titulo) VALUES ('UC1', 'Canal')")
    for i, (views, dur) in enumerate([(9000, 40), (500, 600), (800, 600)]):
        banco.executar("INSERT INTO videos (id, canal_id, titulo, views, duracao_s) VALUES (?,?,?,?,?)", f"v{i}", "UC1", f"Vídeo {i}", views, dur)


def test_mais_vistos_poe_os_longos_antes_dos_shorts(base):
    _canal_com_videos()
    assert [v["id"] for v in pedidos.mais_vistos("UC1")] == ["v2", "v1", "v0"]


def test_pedido_e_quem_pede_ou_pergunta_de_verdade():
    assert pedidos.e_pedido("Faz um vídeo sobre tubarões")
    assert pedidos.e_pedido("Please do a video on sharks")
    assert pedidos.e_pedido("Qual foi a fonte desse dado?")
    assert not pedidos.e_pedido("né?")
    assert not pedidos.e_pedido("Melhor canal do YouTube")


def test_pedidos_vem_pelas_curtidas_sem_repetir_e_ficam_guardados(base):
    _canal_com_videos()
    chamadas = []

    def ler(video_id):
        chamadas.append(video_id)
        if video_id == "v1":
            return None     # comentários desligados
        return [{"texto": "Faz parte 2", "curtidas": 3}, {"texto": "faz  parte 2", "curtidas": 1},
                {"texto": "Please make a video on bears", "curtidas": 50}, {"texto": "Top demais", "curtidas": 900},
                {"texto": "Please buy my merch", "curtidas": 999, "autor": "UC1"}]

    d = pedidos.do_canal("UC1", ler, lambda achados: achados)
    assert d["videos"] == 2
    assert [p["texto"] for p in d["pedidos"]] == ["Please make a video on bears", "Faz parte 2"]
    assert pedidos.do_canal("UC1", ler, lambda achados: []) == d and len(chamadas) == 3
