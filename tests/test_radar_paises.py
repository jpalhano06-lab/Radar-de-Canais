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


def test_holanda_japao_e_coreia_no_metodo_fantasma():
    assert {("NL", "nl"), ("JP", "ja"), ("KR", "ko")} <= set(r.PADRAO)


def _sem_banco(monkeypatch, regional):
    guardado = {}
    monkeypatch.setattr(r.banco, "um", lambda sql, chave: {"dados": guardado[chave]} if chave in guardado else None)
    monkeypatch.setattr(r.banco, "executar", lambda sql, chave, dados, criado: guardado.__setitem__(chave, dados))
    monkeypatch.setattr(r.ia, "traduzir_exato", lambda titulo, linguas: {"en": "Canadian supermarkets that went bankrupt"})
    pedidos = []
    monkeypatch.setattr(r.ia, "regionalizar", lambda titulo, alvos: pedidos.append(titulo) or regional)
    return pedidos


def test_versao_local_troca_o_lugar_pelo_pais(monkeypatch):
    # mercados do Canadá e dos EUA são ideias diferentes: nos EUA também procura "supermarkets in the USA"
    pedidos = _sem_banco(monkeypatch, {"lugar": "Canadá", "titulos": {
        "US": "Supermarkets in the USA that went bankrupt", "BR": "Supermercados do Brasil que faliram"}})
    prep = r.preparar("10 supermercados do Canadá que faliram")
    paises = {p["codigo"]: p for p in prep["paises"]}
    assert prep["lugar"] == "Canadá" and paises["US"]["regional"]["busca"] == "Supermarkets USA went bankrupt"
    assert paises["BR"]["regional"]["traduzido"] == "Supermercados do Brasil que faliram"
    assert paises["FR"]["regional"] is None
    r.preparar("10 supermercados do Canadá que faliram")
    assert len(pedidos) == 1        # guardada: não pergunta de novo


def test_titulo_sem_lugar_nao_tem_versao_local(monkeypatch):
    _sem_banco(monkeypatch, {"lugar": "", "titulos": {}})
    assert all(p["regional"] is None for p in r.preparar("Animais que parecem de outro mundo")["paises"])


def test_placar_da_versao_local_fica_a_parte():
    preparo = {"titulo": "Supermercados do Canadá que faliram", "paises": [
        {"codigo": "US", "pais": "Estados Unidos", "lingua": "en", "traduzido": "Canadian supermarkets that went bankrupt",
         "busca": "Canadian supermarkets went bankrupt",
         "regional": {"traduzido": "Supermarkets in the USA that went bankrupt", "busca": "Supermarkets USA went bankrupt"}}]}
    achado = {"id": "x1", "titulo": "Supermarkets in the USA That Went Bankrupt", "canal": "C", "views": "250,000 views"}
    j = r.julgar(preparo, {"US": [], "US:regional": [achado]})
    us = j["paises"][0]
    assert not us["feito"] and us["regional"]["feito"] and us["regional"]["parecidos"][0]["id"] == "x1"
    assert us["regional"]["forca"] == "forte" and j["livres"] == 1 and j["livres_regional"] == 0
