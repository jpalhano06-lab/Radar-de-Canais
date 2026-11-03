"""O radar de países com os casos reais que já deram errado (sem rede)."""
from radar import gosto, radar_paises as r

PAPUA = "Animais Bizarros de Papua Que Parecem Vir de Outro Mundo!"


def test_busca_vai_so_com_as_palavras_do_assunto():
    # a frase inteira trazia jacaré e tribo canibal; as palavras-chave acham os vídeos brasileiros
    assert r.palavras_da_busca("15 " + PAPUA) == "Animais Bizarros Papua Parecem Outro"


def test_mesma_ideia_com_outras_palavras_de_ligacao():
    alvo = gosto.chaves(r.sem_numeros(PAPUA))
    assert r.mesma_ideia("15 Animais Bizarros da Papua Que Parecem Ter Vindo de Outro Mundo!", alvo) >= r.PARECIDO
    assert r.mesma_ideia("15 Animais Bizarros de Papua que Parecem Ser de Outro Mundo!", alvo) >= r.PARECIDO


def test_outro_assunto_nao_e_a_mesma_ideia():
    alvo = gosto.chaves(r.sem_numeros(PAPUA))
    assert r.mesma_ideia("ANIMAIS BIZARROS DE CHERNOBYL", alvo) < r.PARECIDO
    assert r.mesma_ideia("OS 20 ANIMAIS MAIS ESTRANHOS DO MUNDO!", alvo) < r.PARECIDO


def test_plural_genero_e_mesmo_numero():
    # "gatos" e "gato", "raras" e "raros"; e o mesmo 15 do título original reforça
    alvo = gosto.chaves(r.sem_numeros("15 Raças de Gato Mais Raras e Mais Bonitas do Mundo que Você Não Vai Acreditar que São Reais"))
    achado = "As 15 Raças de Gatos Mais Raras e Lindas do Mundo Que Você Não Vai Acreditar que Existem"
    assert r.mesma_ideia(achado, alvo, r.numeros("15 Rarest and Most Beautiful Cat Breeds")) >= r.PARECIDO
    assert r.mesma_ideia("As 5 raças de gatos mais caras do mundo!", alvo, {"15"}) < r.PARECIDO


def test_palavra_de_isca_nao_faz_outra_ideia_virar_a_mesma():
    # "Rare Birds... You Won't Believe They're Real" batia com a ideia dos gatos pelas palavras de isca e pelo 15
    ideia = "15 Rarest and Most Beautiful Cat Breeds in the World You Won't Believe Are Real"
    alvo = r.palavras(r.sem_numeros(ideia))
    assert "cat" in alvo
    assert r.mesma_ideia("15 Rare Birds So Beautiful You Won't Believe They're Real", alvo, r.numeros(ideia)) < r.PARECIDO
    assert r.mesma_ideia("15 Rarest Cat Breeds in the World", alvo, r.numeros(ideia)) >= r.PARECIDO


def test_reupload_em_ingles_nao_conta_para_o_brasil():
    assert not r.na_lingua("15 Bizarre Animals from Papua That Look Like They're From Another World!", "pt")
    assert r.na_lingua("15 Animais Bizarros da Papua Que Parecem Ter Vindo de Outro Mundo!", "pt")


def test_japones_e_coreano_tambem_batem():
    # sem os pedaços do japonês e do coreano o alvo saía vazio e o Japão e a Coreia saíam sempre "ninguém fez"
    alvo = r.palavras(r.sem_numeros("パプアの奇妙な動物たち 別世界から来たような"))
    assert r.mesma_ideia("【衝撃】パプアの奇妙な動物15選 別世界から来たような生き物", alvo) >= r.PARECIDO
    assert r.mesma_ideia("チェルノブイリの猫", alvo) < r.PARECIDO
    alvo = r.palavras(r.sem_numeros("다른 세상에서 온 것 같은 파푸아의 기묘한 동물들"))
    assert r.mesma_ideia("다른 세상에서 온 것 같은 파푸아의 기묘한 동물 15가지", alvo) >= r.PARECIDO
    assert r.mesma_ideia("체르노빌의 고양이", alvo) < r.PARECIDO
    assert r.palavras_da_busca("다른 세상에서 온 파푸아의 동물들") == "다른 세상에서 온 파푸아의 동물들"


def test_video_coreano_nao_conta_para_o_japao():
    assert not r.na_lingua("파푸아의 기묘한 동물들", "ja") and r.na_lingua("パプアの奇妙な動物", "ja")
    assert not r.na_lingua("パプアの奇妙な動物", "ko") and r.na_lingua("파푸아의 기묘한 동물들", "ko")


def _sem_banco(monkeypatch, troca):
    guardado = {}
    monkeypatch.setattr(r.banco, "um", lambda sql, chave: {"dados": guardado[chave]} if chave in guardado else None)
    monkeypatch.setattr(r.banco, "executar", lambda sql, chave, dados, criado: guardado.__setitem__(chave, dados))
    monkeypatch.setattr(r.ia, "traduzir_exato", lambda titulo, linguas: {"en": "Canadian supermarkets that went bankrupt"})
    pedidos = []
    monkeypatch.setattr(r.ia, "regionalizar", lambda titulo, alvos, acrescentar=False: pedidos.append((sorted(alvos), acrescentar)) or troca)
    return pedidos


CANADA = {"lugar": "Canadá", "titulos": {"US": "Supermarkets in the USA that went bankrupt", "BR": "Supermercados do Brasil que faliram",
                                         "GB": "Supermarkets in the UK that went bankrupt"},
          "marcas": {"US": ["USA", "United States", "America", "American"], "BR": ["Brasil", "brasileiro"], "GB": ["UK", "Britain", "British"]}}


def test_raiz_so_traduz(monkeypatch):
    pedidos = _sem_banco(monkeypatch, CANADA)
    prep = r.preparar("10 supermercados do Canadá que faliram", "raiz")
    us = {p["codigo"]: p for p in prep["paises"]}["US"]
    assert us["busca"] == "Canadian supermarkets went bankrupt" and not us["trocado"] and not pedidos


def test_adaptado_troca_o_lugar_pelo_pais(monkeypatch):
    # mercados do Canadá e dos EUA são ideias diferentes: nos EUA procura "supermarkets in the USA"
    pedidos = _sem_banco(monkeypatch, CANADA)
    prep = r.preparar("10 supermercados do Canadá que faliram", "adaptado")
    paises = {p["codigo"]: p for p in prep["paises"]}
    assert prep["lugar"] == "Canadá" and paises["US"]["busca"] == "Supermarkets USA went bankrupt" and paises["US"]["trocado"]
    assert paises["BR"]["traduzido"] == "Supermercados do Brasil que faliram" and paises["BR"]["marcas"] == ["Brasil", "brasileiro"]
    assert not paises["FR"]["trocado"]      # o Groq não trocou: fica a tradução
    assert pedidos == [(sorted(c for c, _ in r.PADRAO), True)]
    r.preparar("10 supermercados do Canadá que faliram", "adaptado")
    assert len(pedidos) == 1        # guardada: não pergunta de novo


def test_premium_so_paises_de_lingua_inglesa_sem_o_do_titulo(monkeypatch):
    pedidos = _sem_banco(monkeypatch, CANADA)
    prep = r.preparar("10 supermercados do Canadá que faliram", "premium")
    assert [p["codigo"] for p in prep["paises"]] == ["US", "GB"]      # CA (o do título), AU, NZ e IE sem título trocado ficam fora
    assert all(p["lingua"] == "en" for p in prep["paises"]) and pedidos == [(sorted(r.PREMIUM), False)]


def test_premium_sem_lugar_procura_o_titulo_em_ingles_nos_seis(monkeypatch):
    _sem_banco(monkeypatch, {"lugar": "", "titulos": {}, "marcas": {}})
    prep = r.preparar("Supermercados que faliram", "premium")
    assert [p["codigo"] for p in prep["paises"]] == r.PREMIUM and not any(p["trocado"] for p in prep["paises"])


ADAPTADO_US = {"codigo": "US", "pais": "Estados Unidos", "lingua": "en", "traduzido": "Supermarkets in the USA that went bankrupt",
               "busca": "Supermarkets USA went bankrupt", "trocado": True, "marcas": ["USA", "United States", "America", "American"]}


def test_com_o_pais_trocado_o_achado_tem_que_falar_do_pais():
    preparo = {"titulo": "Supermercados do Canadá que faliram", "paises": [ADAPTADO_US]}
    do_pais = {"id": "x1", "titulo": "American Supermarkets That Went Bankrupt", "canal": "C", "views": "250,000 views"}
    de_outro = {"id": "x2", "titulo": "Supermarkets That Went Bankrupt", "canal": "D", "views": "900,000 views"}
    us = r.julgar(preparo, {"US": [de_outro, do_pais]})["paises"][0]
    assert us["feito"] and [p["id"] for p in us["parecidos"]] == ["x1"] and us["forca"] == "forte"


def test_nao_contam_o_mesmo_canal_nem_video_velho_e_fraco_e_relativo():
    preparo = {"titulo": "Supermercados do Canadá que faliram", "paises": [ADAPTADO_US]}
    base = {"titulo": "Supermarkets in the USA That Went Bankrupt", "views": "60,000 views"}
    mesmo_canal = base | {"id": "a", "canal_id": "UCmeu"}
    velho = base | {"id": "b", "publicado": "3 years ago"}
    novo = base | {"id": "c", "publicado": "2 months ago"}
    us = r.julgar(preparo, {"US": [mesmo_canal, velho, novo, novo]}, canal_id="UCmeu", views=2_000_000)["paises"][0]
    assert [p["id"] for p in us["parecidos"]] == ["c"] and us["velhos"] == 1
    assert us["forca"] == "fraco"       # 60 mil é menos de 5% dos 2 milhões do vídeo aberto
    assert r.julgar(preparo, {"US": [novo]})["paises"][0]["forca"] == "medio"   # sem as views do vídeo: o corte fixo


def test_video_velho_em_cada_lingua():
    assert all(r.velho(t) for t in ["há 2 anos", "3 years ago", "hace 1 año", "il y a 2 ans", "vor 2 Jahren", "2 anni fa",
                                    "2 lata temu", "2 yıl önce", "2 jaar geleden", "2年前", "2년 전", "Streamed 1 year ago"])
    assert not any(r.velho(t) for t in ["há 11 meses", "2 months ago", "3 semaines", "vor 5 Tagen", ""])


def test_holanda_japao_e_coreia_no_metodo_fantasma():
    assert {("NL", "nl"), ("JP", "ja"), ("KR", "ko")} <= set(r.PADRAO)


def test_o_pais_que_o_titulo_ja_cita_fica_sem_troca(monkeypatch):
    # o Groq trocou "California" nos EUA também; o título já fala dos americanos: os EUA saem do premium
    _sem_banco(monkeypatch, {"lugar": "Estados Unidos", "titulos": {
        "US": "Why Americans Are Leaving United States", "GB": "Why Brits Are Leaving Britain"},
        "marcas": {"US": ["United States", "USA", "American", "Americans"], "GB": ["UK", "Britain", "Brits"]}})
    prep = r.preparar("Why Americans Are Leaving California", "premium")
    assert [p["codigo"] for p in prep["paises"]] == ["GB"]
