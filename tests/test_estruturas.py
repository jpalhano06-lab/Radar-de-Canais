"""As estruturas de título: o esqueleto sem números, preencher, casar e escolher. Sem banco e sem rede."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import estruturas  # noqa: E402

VOCAB = {"assunto": ["Walmart"], "itens": ["Foods"], "lugares": ["Grocery Stores"], "publico": ["Seniors"],
         "momento": ["Prices Rise"]}


def test_sem_numeros_tira_numero_ano_e_preco():
    assert estruturas.sem_numeros("New Rules Coming in 2027 (Don't Lose Your Membership!)") == \
        "New Rules Coming in (Don't Lose Your Membership!)"
    assert estruturas.sem_numeros("12 Products That Destroy Premium Brands") == "Products That Destroy Premium Brands"
    assert estruturas.sem_numeros("Why $5 Meals Are Gone 🔥") == "Why Meals Are Gone"
    assert estruturas.sem_numeros("Is Collapsing — And Nobody Can Save It!") == "Is Collapsing — And Nobody Can Save It!"


def test_as_da_partida_valem_e_nao_tem_numero():
    for e in estruturas.PARTIDA:
        assert estruturas.valida(e), e


def test_estrutura_sem_gancho_ou_com_numero_nao_vale():
    assert not estruturas.valida("{assunto}")                       # sem gancho
    assert not estruturas.valida("Top 10 {itens} You Need")          # número
    assert not estruturas.valida("Millions of People Love Pizza")    # sem lacuna
    assert not estruturas.valida("{marca} Is Collapsing Right Now")  # lacuna que não existe


def test_preencher_troca_cada_lacuna_e_desiste_quando_falta_palavra():
    cheia = estruturas.preencher("Essential {itens} {publico} Will Stockpile", VOCAB, random.Random(1))
    assert cheia == "Essential Foods Seniors Will Stockpile"
    assert estruturas.preencher("Worst and Best {lugares}", {"lugares": []}) == ""


def test_a_busca_vai_sem_pontuacao():
    assert estruturas.busca("New Rules Coming (Don't Lose Your Costco Membership)") == \
        "New Rules Coming Don't Lose Your Costco Membership"


def test_casa_pelo_gancho_e_nao_pelo_assunto():
    g = "Millions of People Are Now Boycotting {assunto}"
    assert estruturas.casa("Millions of People Are Now Boycotting Target", g) == 1.0
    assert estruturas.casa("Millions of People Are Boycotting Starbucks Right Now", g) >= 0.6
    assert estruturas.casa("Target Earnings Explained", g) < 0.2


def test_escolher_so_usa_o_que_o_vocabulario_preenche_e_anda_a_cada_tentativa(monkeypatch):
    monkeypatch.setattr(estruturas, "todas", lambda: [{"texto": t, "origem": "partida", "vezes": 0, "canais": 0}
                                                      for t in estruturas.PARTIDA])
    so_assunto = {"assunto": ["Costco"]}
    escolhidas = estruturas.escolher(so_assunto, 10)
    assert escolhidas and all("{" not in b for _e, b in escolhidas)
    assert all(estruturas.lacunas_de(e) == ["assunto"] for e, _b in escolhidas)
    primeira = estruturas.escolher(VOCAB, 2, tentativa=0)
    segunda = estruturas.escolher(VOCAB, 2, tentativa=1)
    assert [e for e, _ in primeira] != [e for e, _ in segunda]
    assert estruturas.escolher(VOCAB, 2, desligadas=list(estruturas.PARTIDA)) == []


def test_a_expressao_do_nicho_so_casa_inteira():
    from radar import gosto, meu_nicho
    p = {"vocab": {"assunto": ["Private Labels"], "itens": [], "lugares": ["Whole Foods", "Walmart"]}}
    expressoes = meu_nicho._expressoes(p)
    casa = lambda t: {o for o, ch in expressoes if ch <= meu_nicho._tokens(t)}  # noqa: E731
    assert casa("Inside the Private Jet of a Billionaire") == set()       # "private" sozinho não é o nicho
    assert casa("Why Private Labels Are Beating Big Brands") == {"Private Labels"}
    assert casa("Whole Foods Is Collapsing") == {"Whole Foods"}
    assert casa("Walmart Just Changed Everything") == {"Walmart"}


def test_canal_com_o_gancho_mas_de_outro_assunto_nao_e_do_nicho():
    """Quem escolheu animais buscou "... Is Collapsing" e ganhou novela chinesa: o gancho casa, o assunto não."""
    from radar import meu_nicho
    p = {"vocab": {"assunto": ["Wild Animals"], "itens": ["Pets"], "lugares": ["Zoos"]}}
    novela = ["They Sent the Foolish Heiress to Marry a Mad Prince", "Two Sisters Swapped Grooms by Mistake",
              "Reborn as a Fallen Princess, She Used Her Arsenal"]
    assert meu_nicho.fala_do_nicho(novela, meu_nicho._expressoes(p))[2] is False
    bichos = ["Why Zoos Are Closing Everywhere", "Pets That Destroy Premium Brands", "The Ocean at Night"]
    assunto, falam, do_nicho = meu_nicho.fala_do_nicho(bichos, meu_nicho._expressoes(p))
    assert do_nicho and falam == 2 and assunto == {"Zoos", "Pets"}


def test_palavra_solta_do_nicho_reconhece_o_canal_mesmo_curta():
    from radar import meu_nicho
    p = {"vocab": {"assunto": ["Wildlife Conservation"], "palavras": ["shark", "dog", "lion"]}}
    ex = meu_nicho._expressoes(p)
    titulos = ["The Dog That Saved a Town", "Why Sharks Never Stop", "This Lion Was Betrayed", "A Day at Sea"]
    assunto, falam, do_nicho = meu_nicho.fala_do_nicho(titulos, ex)
    assert do_nicho and falam == 3 and assunto == {"dog", "shark", "lion"}   # "Sharks" no plural conta como "shark"
    assert not meu_nicho.fala_do_nicho(["A Million Reasons to Leave"], ex)[1]   # "lion" dentro de "million" não conta


def test_com_buscas_prontas_so_usa_as_estruturas_que_servem_e_anda_nas_buscas(monkeypatch):
    monkeypatch.setattr(estruturas, "todas", lambda: [{"texto": t, "origem": "partida", "vezes": 0, "canais": 0}
                                                      for t in estruturas.PARTIDA[:3]])
    a, b, c = estruturas.PARTIDA[:3]
    prontas = {a: ["Coral Reefs Are Collapsing and Nobody Can Save Them", "Bees Are Collapsing"], b: [], c: ["X Y Z"]}
    assert [e for e, _ in estruturas.escolher({}, 5, prontas=prontas)] == [a, c]      # b não serve no nicho
    primeira = estruturas.escolher({}, 2, prontas=prontas, tentativa=0)
    volta = estruturas.escolher({}, 2, prontas=prontas, tentativa=1)
    assert primeira[0][1] == "Coral Reefs Are Collapsing and Nobody Can Save Them"
    assert volta[0][1] == "Bees Are Collapsing"          # a segunda volta usa a segunda busca pronta


def test_o_formulario_decide_o_que_e_canal_validado():
    from radar import meu_nicho
    f = meu_nicho._filtros({"min_views": 10000, "idade_max_meses": 12, "inscritos_max": 100000, "sem_rosto": True,
                            "proibidas": ["react"], "paises": ["US", "XX"], "duracao": "nada"})
    assert f["paises"] == ["US"] and f["duracao"] == "alternar"        # o que não existe volta ao padrão
    bom = {"base_longos": 20000, "primeiro_video": "2026-06-01T00:00:00Z", "inscritos": 5000, "sem_rosto": None,
           "nicho": "Animais", "subnicho": ""}
    assert meu_nicho.validado(bom, f, ["Why Sharks Never Stop"]) == ""
    assert meu_nicho.validado(bom | {"base_longos": 900}, f, []) == "views"
    assert meu_nicho.validado(bom | {"primeiro_video": "2020-01-01T00:00:00Z"}, f, []) == "idade"
    assert meu_nicho.validado(bom | {"inscritos": 500000}, f, []) == "inscritos"
    assert meu_nicho.validado(bom | {"sem_rosto": 0}, f, []) == "rosto"
    assert meu_nicho.validado(bom, f, ["Shark Attack REACT"]) == "proibida"


def test_a_fila_comeca_pelos_titulos_da_pessoa_e_tira_as_proibidas_na_busca():
    from radar import meu_nicho
    p = meu_nicho.PADRAO | {"proprias": ["Why Sharks Never Stop"], "ganchos": ["G1", "G2"],
                            "buscas": {"{assunto} Is Collapsing": ["Wildlife Is Collapsing"]}, "desligadas": []}
    fila = meu_nicho._fila(p)
    assert fila[0] == (meu_nicho.PROPRIA, "Why Sharks Never Stop")
    assert [b for _e, b in fila[1:]] == ["Wildlife Is Collapsing", "G1", "G2"]
    assert meu_nicho._com_proibidas("Shark Facts", ["react", "for kids"]) == "Shark Facts -react"


def test_os_videos_do_nicho_vem_do_mais_novo_e_sem_proibidas(tmp_path, monkeypatch):
    """A tela do Meu nicho: os vídeos das buscas, o mais novo no topo, fora do período e com palavra proibida não."""
    import json
    from datetime import datetime, timedelta, timezone
    from radar import banco, meu_nicho
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "radar.db")
    monkeypatch.setattr(banco, "_CON", None, raising=False)
    agora = datetime.now(timezone.utc)
    data = lambda dias: (agora - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    perfil = {"feito": True, "tema": "Animais", "filtros": {"dias": 30, "proibidas": ["react"]}}
    uid = banco.executar("INSERT INTO usuarios (email, senha_hash, criado, nicho) VALUES (?,?,?,?)",
                         "a@b.c", "x", banco.agora(), json.dumps(perfil))
    banco.executar("INSERT INTO canais (id, titulo, base_longos) VALUES ('UC1', 'Wild', 10000)")
    for vid, titulo, dias in [("v1", "Sharks Old", 3), ("v2", "Sharks New", 1), ("v3", "Too Old", 90),
                              ("v4", "Shark REACT", 0)]:
        banco.executar("INSERT INTO videos (id, canal_id, titulo, publicado, duracao_s, views, medido) "
                       "VALUES (?,?,?,?,?,?,?)", vid, "UC1", titulo, data(dias), 900, 5000, banco.agora())
        banco.executar("INSERT INTO nicho_videos (usuario_id, video_id, canal_id, busca, achado) VALUES (?,?,?,?,?)",
                       uid, vid, "UC1", "sharks", banco.agora())
    u = banco.um("SELECT * FROM usuarios WHERE id=?", uid)
    assert [v["id"] for v in meu_nicho.videos(u, atualizar=False)] == ["v2", "v1"]
