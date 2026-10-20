"""As contas do Radar, sem rede."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import metricas, youtube  # noqa: E402

AGORA = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)


def _video(dias, views, duracao=600):
    return {"publicado": (AGORA - timedelta(days=dias)).isoformat().replace("+00:00", "Z"), "views": views,
            "duracao_s": duracao}


def test_normal_e_mediana_e_ignora_novos_e_shorts():
    videos = [_video(1, 10_000_000)]                       # 1 dia: ainda não conta
    videos += [_video(10 + i, v) for i, v in enumerate([100, 200, 300, 5_000_000])]
    videos += [_video(5, 50, duracao=40), _video(6, 70, duracao=40)]
    b = metricas.base(videos, AGORA)
    assert b["base_longos"] == 250                          # o que estourou não vira o normal
    assert b["base_curtos"] == 60
    assert b["longos_medidos"] == 4


def test_nota_outlier():
    assert metricas.nota_outlier(1000, 100) == 10.0
    assert metricas.nota_outlier(1000, 0) is None
    assert metricas.nota_outlier(None, 100) is None


def test_views_por_hora_nunca_divide_por_menos_de_uma_hora():
    agora = AGORA
    publicado = (agora - timedelta(minutes=10)).isoformat()
    assert metricas.views_por_hora(500, publicado, agora) == 500


def test_fases():
    crescendo = [_video(10 + i, 10_000) for i in range(10)] + [_video(200 + i, 2_000) for i in range(20)]
    assert metricas.fase(crescendo, _video(400, 0)["publicado"], AGORA) == "crescendo"
    caindo = [_video(10 + i, 1_000) for i in range(10)] + [_video(200 + i, 10_000) for i in range(20)]
    assert metricas.fase(caindo, _video(400, 0)["publicado"], AGORA) == "caindo"
    assert metricas.fase([_video(90, 1000)], _video(100, 0)["publicado"], AGORA) == "parado"
    assert metricas.fase([_video(5, 1000)], _video(30, 0)["publicado"], AGORA) == "nascendo"


def test_raridade():
    assert metricas.raridade(400_000, 5) == "lendario"
    assert metricas.raridade(400_000, 8) == "epico"
    assert metricas.raridade(400_000, 30) == ""              # canal antigo nunca é achado raro
    assert metricas.raridade(20_000, 3) == ""


def test_duracao_iso():
    assert youtube.duracao("PT1H2M3S") == 3723
    assert youtube.duracao("PT45S") == 45
    assert youtube.duracao("P0D") == 0


def test_velocidade_so_conta_o_ultimo_mes():
    videos = [_video(10, 10_000), _video(5, 5_000), _video(60, 1_000_000)]
    assert metricas.velocidade(videos, AGORA) == 2000.0      # 10.000/10 + 5.000/5
    assert metricas.velocidade([_video(90, 5)], AGORA) is None


def test_medir_canal_aceita_arroba_link_e_id():
    from radar.servidor import _ref_do_canal
    assert _ref_do_canal("@fossil") == "@fossil"
    assert _ref_do_canal("https://www.youtube.com/@Um.Documentario/videos") == "@Um.Documentario"
    assert _ref_do_canal("https://www.youtube.com/channel/UCsXVk37bltHxD1rDPwtNM8Q") == "UCsXVk37bltHxD1rDPwtNM8Q"
    assert _ref_do_canal("qualquer coisa") is None


def test_ler_numero_do_filtro_no_servidor():
    from radar.servidor import _numero, _data
    assert _numero({"a": "20000"}, "a") == 20000
    assert _numero({"a": ""}, "a") is None
    assert _data({"d": "2026-10-01"}, "d") == "2026-10-01"
    assert _data({"d": "01/10/2026"}, "d") == ""


def test_lingua_do_titulo():
    from radar.gosto import lingua
    assert lingua("Os animais mais perigosos do mundo") == "pt"
    assert lingua("Los animales más extraños del mundo") == "es"
    assert lingua("The strangest animals in the world") == "en"
    assert lingua("Maut Ke Baad Narak Mein") == "outras"
    assert lingua("MRI Machine कैसे काम करती है") in ("outras", "?")
    assert lingua("ПОЧЕМУ ЭТО ПРОИЗОШЛО") == "outras"


def test_parecenca_pelo_assunto():
    from radar.gosto import chaves, parecenca
    alvo = chaves("The Fall of Rome Explained") | chaves("Ancient Egypt Secrets Revealed")
    assert parecenca("What Rome Looked Like at Its Height", alvo) > 0
    assert parecenca("Python attacks porcupine", alvo) == 0


def test_hindi_com_letras_latinas_e_ingles_sem_artigo():
    from radar.gosto import lingua
    assert lingua("Maut Ke Baad Narak Mein Milti Hain saat Bhayanak Sazaayein") == "outras"
    assert lingua("Ye Monster Jitna Bada Hota Gaya Utna Hi Khatarnaak") == "outras"
    assert lingua("Honey Badger vs Black Mamba : A Deadly African Showdown") == "en"


def test_titulo_misturado_com_outro_alfabeto():
    from radar.gosto import lingua
    assert lingua("দুই বোনের ভাগ্য | Bangla Animated Moral Story | Cartoon Golpo Bangla") == "outras"
    assert lingua("Pokémon: o anime explicado") == "pt"


def test_ideia_sem_numeracao():
    from radar.radar_paises import sem_numeros
    assert sem_numeros("Top 10 Supermercados que Faliram em 2024") == "Supermercados que Faliram em"
    assert sem_numeros("These 10 Big Grocery Chains That Filed for Bankruptcy") == "These Big Grocery Chains That Filed for Bankruptcy"
    assert sem_numeros("#1 Rarest Animal | 5 Facts") == "Rarest Animal Facts"
    assert sem_numeros("O 3º maior mistério") == "O maior mistério"
