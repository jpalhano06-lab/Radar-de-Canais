"""O teste do canal novo (2026-11-17): dois vídeos do espaço, sem narração e sem thumbnail, liberados pela pessoa no
perfil do canal e agendados um dia depois do outro. Sem rede: a fábrica é de mentira."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import agendar, banco, fabrica_api, fila, tempo, teste_canal  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db")
    monkeypatch.setattr(banco, "_CON", None)
    fila._PARADOS.clear()
    monkeypatch.setattr(tempo, "ritmo", lambda uid, perfil, lingua: {"ppm": 150})
    # nenhum vídeo sobe sem a descrição do Claude (2026-11-17): aqui ela já está escrita
    monkeypatch.setattr(agendar, "kit_do_video",
                        lambda uid, item: {"titulo": "Teste", "descricao": "A descrição do Claude.", "tags": ["t"]})
    monkeypatch.setattr(teste_canal, "conectados", list)      # sem rede: a fábrica não é chamada nos testes
    # os testes de antes de 2026-11-25 conferem o envio pela API da fábrica; o da extensão tem os seus, no fim
    monkeypatch.setattr(teste_canal, "POSTAR_PELA_EXTENSAO", False)
    monkeypatch.setattr(teste_canal, "O_RADAR_POSTA", True)     # os de antes de a pessoa postar (2026-11-25)
    # nenhum teste escreve na pasta da fábrica de verdade
    monkeypatch.setattr(fabrica_api.roteiro_claude, "FABRICA", tmp_path / "fabrica")
    banco.executar("INSERT OR IGNORE INTO meus_canais (usuario_id, canal_id, criado) VALUES (?,?,?)",
                   1, "UC1", banco.agora())
    yield
    banco._CON.close()
    banco._CON = None


def _entregues(*fids):
    for k, fid in enumerate(fids, 1):
        banco.executar("UPDATE producoes_fila SET estado='entregue', projeto=? WHERE id=?", f"projeto-{k}", fid)


def test_oferecer_abre_o_convite_pendente(db):
    assert teste_canal.do_canal(1, "UC1") is None
    teste_canal.oferecer(1, "UC1")
    cartao = teste_canal.do_canal(1, "UC1")
    assert cartao["estado"] == "pendente" and cartao["videos"] == []
    assert cartao["quantos"] == teste_canal.POR_CANAL and cartao["minutos"] == fila.MINUTOS_SEM_NARRACAO
    assert cartao["lingua"] == teste_canal.LINGUA_PADRAO     # inglês, até a pessoa escolher outra


def test_liberar_cria_os_tres_pedidos_sem_narracao(db):
    teste_canal.oferecer(1, "UC1")
    cartao = teste_canal.liberar(1, "UC1", "português")
    assert cartao["estado"] == "liberado" and len(cartao["videos"]) == 3
    temas = [v["tema"] for v in cartao["videos"]]
    assert temas == list(teste_canal.TEMAS[:3]) and len(set(temas)) == 3
    for v in cartao["videos"]:
        pedido = fila.item(1, v["fid"])["pedido"]
        # em "entrada": nada começa antes de a fila ficar parada
        assert v["estado"] == "entrada"
        assert pedido["sem_narracao"] and pedido["perfil"] == "sem-narracao" and pedido["lingua"] == "português"
        assert not pedido.get("canal_id")    # a fila só aceita o sem narração fora de um canal


def test_liberar_so_o_que_e_seu_e_so_uma_vez(db):
    teste_canal.oferecer(1, "UC2")           # UC2 não está em meus_canais
    with pytest.raises(ValueError):
        teste_canal.liberar(1, "UC2")
    teste_canal.oferecer(1, "UC1")
    teste_canal.liberar(1, "UC1")
    with pytest.raises(ValueError):
        teste_canal.liberar(1, "UC1")


def test_dispensar_tira_o_cartao(db):
    teste_canal.oferecer(1, "UC1")
    assert teste_canal.dispensar(1, "UC1")["estado"] == "dispensado"


def test_os_temas_nao_se_repetem_entre_canais(db):
    banco.executar("INSERT INTO meus_canais (usuario_id, canal_id, criado) VALUES (?,?,?)", 1, "UC2", banco.agora())
    teste_canal.oferecer(1, "UC1")
    teste_canal.oferecer(1, "UC2")
    primeiros = [v["tema"] for v in teste_canal.liberar(1, "UC1")["videos"]]
    segundos = [v["tema"] for v in teste_canal.liberar(1, "UC2")["videos"]]
    assert not set(primeiros) & set(segundos)


def test_so_comeca_com_a_fila_parada(db):
    teste_canal.oferecer(1, "UC1")
    teste_canal.liberar(1, "UC1")
    ocupando = fila.criar(1, {"titulo": "Um vídeo de verdade", "caracteres": 10620}, comecar=True)
    assert teste_canal._soltar_um_parado() == []          # a fila está trabalhando: o teste espera
    fila.excluir(1, ocupando["id"])
    soltos = teste_canal._soltar_um_parado()
    assert len(soltos) == 1 and fila.item(1, soltos[0])["estado"] == "na_fila"
    assert teste_canal._soltar_um_parado() == []          # um por volta: o outro espera este terminar


def test_os_tres_sobem_na_mesma_hora_de_tres_em_tres_dias(db, monkeypatch):
    enviados = []
    monkeypatch.setattr(fabrica_api, "youtube_publicar",
                        lambda nome, canal, quando="", com_thumbnail=True, **r:
                        enviados.append((nome, canal, quando, com_thumbnail)) or {"sucesso": True})
    monkeypatch.setattr(fabrica_api, "youtube_do_projeto", lambda nome: None)
    teste_canal.oferecer(1, "UC1")
    cartao = teste_canal.liberar(1, "UC1")
    _entregues(*[v["fid"] for v in cartao["videos"]])

    teste_canal._publicar_prontos()
    assert [e[1] for e in enviados] == ["UC1"] * 3                     # os três no canal do teste
    assert [e[3] for e in enviados] == [False] * 3                     # sem thumbnail: o YouTube usa os quadros dele
    horas = [datetime.fromisoformat(e[2]) for e in enviados]
    assert all(h.hour == teste_canal.HORA_DO_POST and h.minute == 0 for h in horas)   # a mesma hora para todos
    assert horas[0] == teste_canal._primeira_hora()
    assert [(b - a).days for a, b in zip(horas, horas[1:])] == [teste_canal.INTERVALO_DIAS] * 2
    depois = teste_canal.do_canal(1, "UC1")
    assert depois["estado"] == "feito" and all(v["agendado_para"] for v in depois["videos"])

    teste_canal._publicar_prontos()
    assert len(enviados) == 3                                          # nada sobe duas vezes


def test_a_primeira_hora_tem_folga_para_o_youtube():
    cedo = datetime(2026, 11, 25, 9, 0)
    assert teste_canal._primeira_hora(cedo) == datetime(2026, 11, 25, teste_canal.HORA_DO_POST)
    tarde = datetime(2026, 11, 25, teste_canal.HORA_DO_POST, 0) - timedelta(minutes=5)
    assert teste_canal._primeira_hora(tarde) == datetime(2026, 11, 26, teste_canal.HORA_DO_POST)


def test_o_erro_do_envio_fica_no_cartao_e_tenta_de_novo_depois(db, monkeypatch):
    def recusar(*a, **k):
        raise fabrica_api.SemFabrica("Esse canal ainda não foi conectado")
    monkeypatch.setattr(fabrica_api, "youtube_publicar", recusar)
    teste_canal.oferecer(1, "UC1")
    cartao = teste_canal.liberar(1, "UC1")
    _entregues(cartao["videos"][0]["fid"])
    teste_canal._publicar_prontos()
    primeiro = teste_canal.do_canal(1, "UC1")["videos"][0]
    assert "não foi conectado" in primeiro["erro"] and not primeiro["agendado_para"]

    chamou = []
    monkeypatch.setattr(fabrica_api, "youtube_publicar",
                        lambda *a, **k: chamou.append(a) or {"sucesso": True})
    teste_canal._publicar_prontos()
    assert chamou == []                                                # espera ESPERA_NOVA_TENTATIVA antes de tentar
    monkeypatch.setattr(teste_canal, "ESPERA_NOVA_TENTATIVA", 0)
    teste_canal._publicar_prontos()
    assert len(chamou) == 1 and not teste_canal.do_canal(1, "UC1")["videos"][0]["erro"]


def test_andar_nao_levanta_quando_algo_falha(db, monkeypatch):
    monkeypatch.setattr(teste_canal, "_fila_parada", lambda: (_ for _ in ()).throw(RuntimeError("banco caiu")))
    assert teste_canal.andar() == []


# ---------------------------------------------------------------- o estoque de vídeos prontos (2026-11-17)

def _encher(quantos):
    """Enche o estoque com `quantos` vídeos já entregues, um de cada vez, como o vigia faz."""
    feitos = []
    for _ in range(quantos):
        feitos += teste_canal._encher_estoque()
        _entregues(*feitos)
    return feitos


def test_o_estoque_enche_um_por_volta_com_a_fila_parada(db, monkeypatch):
    monkeypatch.setattr(teste_canal, "ESTOQUE", 2)
    primeiro = teste_canal._encher_estoque()
    assert len(primeiro) == 1
    assert fila.item(1, primeiro[0])["estado"] == "na_fila"     # a fila estava parada: já começa
    assert teste_canal._encher_estoque() == []                  # agora ela trabalha: nada de um segundo
    _entregues(*primeiro)
    segundo = teste_canal._encher_estoque()
    assert len(segundo) == 1
    _entregues(*primeiro, *segundo)
    assert teste_canal._encher_estoque() == []                  # cheio


def test_o_video_do_estoque_sai_em_ingles_e_sem_narracao(db, monkeypatch):
    monkeypatch.setattr(teste_canal, "ESTOQUE", 1)
    pedido = fila.item(1, teste_canal._encher_estoque()[0])["pedido"]
    assert pedido["sem_narracao"] and pedido["lingua"] == teste_canal.LINGUA_PADRAO
    assert pedido["titulo"] in teste_canal.TEMAS


def test_liberar_leva_os_prontos_do_estoque(db, monkeypatch):
    monkeypatch.setattr(teste_canal, "ESTOQUE", 3)
    guardados = _encher(3)
    teste_canal.oferecer(1, "UC1")
    assert teste_canal.do_canal(1, "UC1")["estoque"] == 3
    cartao = teste_canal.liberar(1, "UC1")                      # em inglês, a língua do estoque
    assert [v["fid"] for v in cartao["videos"]] == guardados
    assert all(v["estado"] == "entregue" for v in cartao["videos"])   # nada a produzir: já estão prontos
    assert teste_canal._estoque(1) == []                        # saíram do estoque


def test_outra_lingua_nao_usa_o_estoque_em_ingles(db, monkeypatch):
    monkeypatch.setattr(teste_canal, "ESTOQUE", 2)
    guardados = _encher(2)
    teste_canal.oferecer(1, "UC1")
    cartao = teste_canal.liberar(1, "UC1", "português")
    assert not {v["fid"] for v in cartao["videos"]} & set(guardados)
    assert all(v["estado"] == "entrada" for v in cartao["videos"])
    assert len(teste_canal._estoque(1)) == 2                    # o estoque em inglês continua lá
    assert not {v["tema"] for v in cartao["videos"]} & {l["tema"] for l in teste_canal._estoque(1)}


def test_o_estoque_esquece_o_video_jogado_fora_na_fila(db, monkeypatch):
    monkeypatch.setattr(teste_canal, "ESTOQUE", 1)
    fila.excluir(1, teste_canal._encher_estoque()[0])
    assert teste_canal._estoque(1) == []
    assert len(teste_canal._encher_estoque()) == 1              # e pede outro no lugar


def test_o_estoque_so_e_feito_para_quem_tem_canal(db, monkeypatch):
    monkeypatch.setattr(teste_canal, "ESTOQUE", 1)
    banco.executar("DELETE FROM meus_canais")
    assert teste_canal._encher_estoque() == []


# ---------------------------------------------------------------- a aba Canal de teste (2026-11-17)

def test_comecar_abre_e_libera_de_uma_vez(db):
    cartao = teste_canal.comecar(1, "UC1", "inglês", "Meu Canal")
    assert cartao["estado"] == "liberado" and cartao["nome"] == "Meu Canal"
    assert len(cartao["videos"]) == teste_canal.POR_CANAL


def test_o_canal_ligado_na_fabrica_tambem_e_seu(db, monkeypatch):
    # UC9 não está em meus_canais: quem diz que é dele é o login do Google na fábrica
    with pytest.raises(ValueError):
        teste_canal.comecar(1, "UC9", "inglês")
    monkeypatch.setattr(teste_canal, "conectados", lambda: [{"canal_id": "UC9", "canal_nome": "Nono"}])
    assert teste_canal.comecar(1, "UC9", "inglês")["estado"] == "liberado"


def test_a_aba_lista_os_testes_do_mais_novo_ao_mais_velho(db):
    banco.executar("INSERT INTO meus_canais (usuario_id, canal_id, criado) VALUES (?,?,?)", 1, "UC2", banco.agora())
    teste_canal.comecar(1, "UC1", "inglês", "Um")
    teste_canal.comecar(1, "UC2", "inglês", "Dois")
    assert [t["canal_id"] for t in teste_canal.todos(1)] == ["UC2", "UC1"]
    teste_canal.oferecer(1, "UC3")
    teste_canal.dispensar(1, "UC3")
    assert "UC3" not in [t["canal_id"] for t in teste_canal.todos(1)]   # o dispensado sai da lista


def test_o_estoque_pronto_conta_so_o_que_esta_entregue(db, monkeypatch):
    monkeypatch.setattr(teste_canal, "ESTOQUE", 2)
    primeiro = teste_canal._encher_estoque()
    assert teste_canal.estoque_pronto(1) == 0           # ainda sendo feito
    _entregues(*primeiro)
    assert teste_canal.estoque_pronto(1) == 1


def test_ligar_o_canal_na_fabrica_ja_comeca_o_teste(db, monkeypatch):
    banco.executar("INSERT OR IGNORE INTO usuarios (id, email, senha_hash, admin, criado) VALUES (1,'eu','x',1,?)",
                   banco.agora())
    monkeypatch.setattr(teste_canal, "conectados",
                        lambda: [{"canal_id": "UC9", "canal_nome": "Nono"}])
    soltos = teste_canal._ligar_conectados()
    assert len(soltos) == teste_canal.POR_CANAL
    cartao = teste_canal.do_canal(1, "UC9")
    assert cartao["estado"] == "liberado" and cartao["nome"] == "Nono"
    assert cartao["lingua"] == teste_canal.LINGUA_PADRAO
    assert teste_canal._ligar_conectados() == []          # o mesmo canal não começa duas vezes


def test_canal_ligado_com_teste_dispensado_fica_quieto(db, monkeypatch):
    banco.executar("INSERT OR IGNORE INTO usuarios (id, email, senha_hash, admin, criado) VALUES (1,'eu','x',1,?)",
                   banco.agora())
    teste_canal.oferecer(1, "UC1")
    teste_canal.dispensar(1, "UC1")
    monkeypatch.setattr(teste_canal, "conectados", lambda: [{"canal_id": "UC1", "canal_nome": "Um"}])
    assert teste_canal._ligar_conectados() == []


def test_canal_ligado_com_convite_pendente_comeca(db, monkeypatch):
    banco.executar("INSERT OR IGNORE INTO usuarios (id, email, senha_hash, admin, criado) VALUES (1,'eu','x',1,?)",
                   banco.agora())
    teste_canal.oferecer(1, "UC1")        # o convite estava lá, esperando resposta
    monkeypatch.setattr(teste_canal, "conectados", lambda: [{"canal_id": "UC1", "canal_nome": "Um"}])
    assert len(teste_canal._ligar_conectados()) == teste_canal.POR_CANAL
    assert teste_canal.do_canal(1, "UC1")["estado"] == "liberado"


# ---------------------------------------------------------------- o lembrete de tirar do privado (2026-11-18)

def test_cada_canal_com_seus_videos_e_a_cor_de_cada_um(db, monkeypatch):
    monkeypatch.setattr(fabrica_api, "youtube_publicar", lambda *a, **k: {"sucesso": True})
    monkeypatch.setattr(fabrica_api, "youtube_do_projeto",
                        lambda nome: {"url": "https://youtu.be/" + nome[:4], "video_id": nome[:4]})
    # o primeiro já passou da hora dele; os outros esperam o dia
    monkeypatch.setattr(teste_canal, "_primeira_hora", lambda agora=None: datetime.now() - timedelta(hours=1))
    teste_canal.oferecer(1, "UC1", "Meu Canal")
    cartao = teste_canal.liberar(1, "UC1")
    assert teste_canal.privados(1) == []                  # nada subiu ainda
    _entregues(*[v["fid"] for v in cartao["videos"]])
    teste_canal._publicar_prontos()
    teste_canal._publicar_prontos()                       # a volta seguinte traz o link e o id do vídeo

    canais = teste_canal.privados(1)
    assert len(canais) == 1 and canais[0]["canal"] == "Meu Canal" and canais[0]["canal_id"] == "UC1"
    videos = canais[0]["videos"]
    assert len(videos) == teste_canal.POR_CANAL and all(v["url"] and v["video_id"] for v in videos)
    # a hora do primeiro chegou: é a vez da pessoa tirar do privado. Os outros esperam o dia deles
    assert [v["estado"] for v in videos] == ["postar", "espera", "espera"]
    assert canais[0]["postar"] == 1

    depois = teste_canal.conferir(1, "UC1", videos[0]["fid"])
    assert [v["estado"] for v in depois[0]["videos"]] == ["publico", "espera", "espera"]
    assert depois[0]["postar"] == 0                       # verde não cobra mais nada


def test_conferir_so_mexe_em_canal_que_tem_teste(db):
    with pytest.raises(ValueError):
        teste_canal.conferir(1, "UC7", 1)


def _fabrica_com_tarefas(monkeypatch, enviados, tarefas):
    """A fábrica como ela é: o envio vira uma tarefa na memória, e o status só conta dela a quem dá o id."""
    def publicar(*a, **k):
        enviados.append(a)
        return {"sucesso": True, "tarefa_id": f"youtube_{len(enviados)}"}
    monkeypatch.setattr(fabrica_api, "youtube_publicar", publicar)
    monkeypatch.setattr(fabrica_api, "youtube_do_projeto", lambda nome: None)    # nada publicado
    monkeypatch.setattr(fabrica_api, "youtube_publicacao",
                        lambda nome, tarefa="": {"tarefa": tarefas.get(tarefa) if tarefa else None, "publicado": None})


def test_envio_perdido_na_fabrica_vai_de_novo(db, monkeypatch):
    enviados = []
    _fabrica_com_tarefas(monkeypatch, enviados, {})     # religada: a memória das tarefas sumiu
    teste_canal.oferecer(1, "UC1")
    cartao = teste_canal.liberar(1, "UC1")
    _entregues(cartao["videos"][0]["fid"])
    teste_canal._publicar_prontos()
    assert len(enviados) == 1

    monkeypatch.setattr(teste_canal, "ESPERA_NOVA_TENTATIVA", 0)
    teste_canal._publicar_prontos()                       # a fábrica não tem tarefa nem publicação: perdeu
    primeiro = teste_canal.do_canal(1, "UC1")["videos"][0]
    assert not primeiro["enviado"] and not primeiro["agendado_para"] and "se perdeu" in primeiro["erro"]
    teste_canal._publicar_prontos()
    assert len(enviados) == 2                             # foi de novo


def test_envio_ainda_andando_na_fabrica_fica_quieto(db, monkeypatch):
    # o vídeo longo leva mais de 15 minutos subindo: perguntar sem o id da tarefa mandava ele de novo, duplicado
    enviados = []
    _fabrica_com_tarefas(monkeypatch, enviados, {"youtube_1": {"status": "enviando"}})
    teste_canal.oferecer(1, "UC1")
    cartao = teste_canal.liberar(1, "UC1")
    _entregues(cartao["videos"][0]["fid"])
    teste_canal._publicar_prontos()
    monkeypatch.setattr(teste_canal, "ESPERA_NOVA_TENTATIVA", 0)
    teste_canal._publicar_prontos()
    assert len(enviados) == 1 and teste_canal.do_canal(1, "UC1")["videos"][0]["enviado"]


def test_envio_que_falhou_na_fabrica_vai_de_novo(db, monkeypatch):
    enviados = []
    _fabrica_com_tarefas(monkeypatch, enviados, {"youtube_1": {"status": "erro", "erro": "quota"}})
    teste_canal.oferecer(1, "UC1")
    cartao = teste_canal.liberar(1, "UC1")
    _entregues(cartao["videos"][0]["fid"])
    teste_canal._publicar_prontos()
    monkeypatch.setattr(teste_canal, "ESPERA_NOVA_TENTATIVA", 0)
    teste_canal._publicar_prontos()
    primeiro = teste_canal.do_canal(1, "UC1")["videos"][0]
    assert not primeiro["enviado"] and "quota" in primeiro["erro"]


def test_envio_sem_id_da_tarefa_nao_vai_em_dobro(db, monkeypatch):
    enviados = []
    _fabrica_com_tarefas(monkeypatch, enviados, {})
    monkeypatch.setattr(fabrica_api, "youtube_publicar", lambda *a, **k: enviados.append(a) or {"sucesso": True})
    teste_canal.oferecer(1, "UC1")
    cartao = teste_canal.liberar(1, "UC1")
    _entregues(cartao["videos"][0]["fid"])
    teste_canal._publicar_prontos()
    monkeypatch.setattr(teste_canal, "ESPERA_NOVA_TENTATIVA", 0)
    teste_canal._publicar_prontos()
    teste_canal._publicar_prontos()
    assert len(enviados) == 1


def test_tags_cabem_nos_500_caracteres_do_youtube():
    # as 18 tags do The Moon (2026-11-20): 512 caracteres contados como o YouTube conta, e ele recusou o envio
    moon = ["lua se afastando da terra", "por que a lua está se afastando", "lua afastando 3,8 cm por ano",
            "moon drifting away", "moon moving away from earth", "how fast is the moon moving away",
            "moon moving away 3.8 cm per year", "lunar laser ranging", "retroreflectors on the moon",
            "apollo mirrors on the moon", "tides and the moon", "tidal bulge moon orbit", "earth days getting longer",
            "earth rotation slowing down", "moon closer to earth in the past", "why total solar eclipses happen",
            "total solar eclipses will end", "moon facts"]
    tags = fabrica_api.tags_que_cabem(moon)
    conta = sum(len(t) + (2 if " " in t else 0) for t in tags) + len(tags) - 1
    assert conta == 499 and tags[0] == moon[0] and len(tags) == 17      # só a última, "moon facts", ficou de fora
    assert "lua afastando 3.8 cm por ano" in tags and not any("," in t for t in tags)
    assert fabrica_api.tags_que_cabem(["a<b>", "", "  x  ", "x"]) == ["a b", "x"]


# ---------------------------------------------------------------- a área Canal de teste (2026-11-25)

def _no_banco(tmp_path, monkeypatch, titulo="Meu cachorro na praia"):
    monkeypatch.setattr(teste_canal, "PASTA_BANCO", tmp_path / "banco")
    temporario = teste_canal.arquivo_temporario(1)
    temporario.write_bytes(b"v" * 4096)
    return teste_canal.guardar_no_banco(1, titulo, "Um passeio.", temporario)


def test_o_banco_guarda_o_video_e_nao_aceita_sem_titulo(db, tmp_path, monkeypatch):
    v = _no_banco(tmp_path, monkeypatch)
    assert teste_canal.arquivo_do_banco(1, v["id"]).read_bytes() == b"v" * 4096
    assert [x["titulo"] for x in teste_canal.banco_de_videos(1)] == ["Meu cachorro na praia"]
    assert teste_canal.arquivo_do_banco(2, v["id"]) is None          # o banco é de cada um
    temporario = teste_canal.arquivo_temporario(1)
    temporario.write_bytes(b"v" * 4096)
    with pytest.raises(ValueError):
        teste_canal.guardar_no_banco(1, "  ", "", temporario)
    teste_canal.apagar_do_banco(1, v["id"])
    assert teste_canal.banco_de_videos(1) == []


def test_o_teste_com_o_banco_posta_o_video_da_pessoa(db, tmp_path, monkeypatch):
    monkeypatch.setattr(fabrica_api.roteiro_claude, "FABRICA", tmp_path / "fabrica")
    (tmp_path / "fabrica" / "perfis").mkdir(parents=True)
    (tmp_path / "fabrica" / "perfis" / "documentario.yaml").write_text("x: 1", encoding="utf-8")
    enviados = []
    monkeypatch.setattr(fabrica_api, "youtube_publicar",
                        lambda nome, canal, quando="", titulo="", descricao=None, **r:
                        enviados.append((nome, titulo, descricao, quando)) or {"tarefa_id": "t1"})
    monkeypatch.setattr(fabrica_api, "youtube_do_projeto", lambda nome: None)
    v = _no_banco(tmp_path, monkeypatch)
    cartao = teste_canal.comecar(1, "UC1", "inglês", "Um", "banco")
    origens = [x["origem"] for x in cartao["videos"]]
    assert origens == ["banco", "radar", "radar"]                    # um no banco: os outros dois o Radar faz
    teste_canal._publicar_prontos()
    nome, titulo, descricao, quando = enviados[0]
    assert nome.startswith(teste_canal.PREFIXO_BANCO) and titulo == "Meu cachorro na praia" and descricao == "Um passeio."
    pasta = fabrica_api._pasta(nome)
    assert (pasta / "final.mp4").read_bytes() == b"v" * 4096 and (pasta / "projeto.json").exists()
    assert datetime.fromisoformat(quando).hour == teste_canal.HORA_DO_POST
    assert teste_canal.banco_de_videos(1)[0]["canais"] == ["Um"]
    assert teste_canal._do_banco_para(1, "UC1", 3) == []              # o mesmo vídeo não vai duas vezes no canal


def test_os_assuntos_escolhem_os_temas_e_os_proprios_vem_primeiro(db):
    teste_canal.salvar_ajustes(1, {"assuntos": ["oceano"], "proprios": "Meu título\n\nOutro título"})
    temas = teste_canal.temas_disponiveis(1)
    assert temas[:2] == ["Meu título", "Outro título"]
    assert set(temas[2:]) == set(teste_canal.ASSUNTOS["oceano"]["temas"])
    assert not set(temas) & set(teste_canal.TEMAS)


def test_a_criacao_em_massa_respeita_a_meta_e_o_desligado(db, monkeypatch):
    teste_canal.salvar_ajustes(1, {"meta": 1, "lingua": "português"})
    feitos = teste_canal._encher_estoque()
    assert fila.item(1, feitos[0])["pedido"]["lingua"] == "português"
    _entregues(*feitos)
    assert teste_canal._encher_estoque() == []                      # a meta era um
    teste_canal.salvar_ajustes(1, {"meta": 5, "ligado": False})
    assert teste_canal._encher_estoque() == []                      # desligada, não faz nada
    assert teste_canal.massa(1)["prontos"] == 1


def _no_ar(monkeypatch, video_id="abcdefghijk"):
    monkeypatch.setattr(fabrica_api, "youtube_publicar", lambda *a, **k: {"tarefa_id": "t1"})
    monkeypatch.setattr(fabrica_api, "youtube_do_projeto",
                        lambda nome: {"url": "https://youtu.be/" + video_id, "video_id": video_id})
    monkeypatch.setattr(teste_canal, "_primeira_hora", lambda agora=None: datetime.now() - timedelta(hours=1))
    teste_canal.oferecer(1, "UC1", "Canal Bom")
    cartao = teste_canal.liberar(1, "UC1")
    _entregues(cartao["videos"][0]["fid"])
    teste_canal._publicar_prontos()
    teste_canal._publicar_prontos()


def test_mil_impressoes_acendem_o_alerta_de_canal_bom(db, monkeypatch):
    from radar import youtube
    _no_ar(monkeypatch)
    monkeypatch.setattr(youtube, "videos", lambda ids: [{"id": i, "views": 40} for i in ids])
    monkeypatch.setattr(teste_canal, "_impressoes", lambda *a: 999)
    teste_canal._medir()
    assert teste_canal.alertas(1) == []
    monkeypatch.setattr(teste_canal, "MEDIR_A_CADA", 0)
    monkeypatch.setattr(teste_canal, "_impressoes", lambda *a: 1500)
    teste_canal._medir()
    alerta = teste_canal.alertas(1)
    assert len(alerta) == 1 and alerta[0]["canal"] == "Canal Bom" and alerta[0]["impressoes"] == 1500
    assert teste_canal.painel(1)["numeros"]["bons"] == 1
    assert teste_canal.alerta_visto(1, "UC1", alerta[0]["chave"]) == []
    assert teste_canal.do_canal(1, "UC1")["bom"]                    # visto sai do topo, mas o canal segue bom


def test_sem_studio_mil_views_tambem_acendem(db, monkeypatch):
    from radar import youtube
    _no_ar(monkeypatch)
    monkeypatch.setattr(youtube, "videos", lambda ids: [{"id": i, "views": 1200} for i in ids])
    monkeypatch.setattr(teste_canal, "_impressoes", lambda *a: None)
    teste_canal._medir()
    alerta = teste_canal.alertas(1)
    assert len(alerta) == 1 and alerta[0]["pelas_views"]


def test_completar_poe_o_terceiro_nos_testes_de_dois(db, monkeypatch):
    enviados = []
    monkeypatch.setattr(fabrica_api, "youtube_publicar",
                        lambda nome, canal, quando="", **r: enviados.append(quando) or {"tarefa_id": "t"})
    monkeypatch.setattr(fabrica_api, "youtube_do_projeto", lambda nome: None)
    monkeypatch.setattr(teste_canal, "POR_CANAL", 2)
    cartao = teste_canal.comecar(1, "UC1", "inglês", "Um")
    _entregues(*[v["fid"] for v in cartao["videos"]])
    teste_canal._publicar_prontos()
    assert teste_canal.do_canal(1, "UC1")["estado"] == "feito"
    monkeypatch.setattr(teste_canal, "POR_CANAL", 3)
    # os títulos dos assuntos ligados acabaram: o terceiro vem de outro assunto
    monkeypatch.setattr(teste_canal, "temas_novos", lambda uid, quantos=3: [])
    assert teste_canal.completar(1) == ["UC1"]
    depois = teste_canal.do_canal(1, "UC1")
    assert depois["estado"] == "liberado" and len(depois["videos"]) == 3
    assert depois["videos"][2]["tema"] not in {v["tema"] for v in depois["videos"][:2]}
    assert teste_canal.completar(1) == []                       # já tem três: nada muda
    _entregues(depois["videos"][0]["fid"], depois["videos"][1]["fid"], depois["videos"][2]["fid"])
    teste_canal._publicar_prontos()
    ultimo, terceiro = datetime.fromisoformat(enviados[1]), datetime.fromisoformat(enviados[2])
    assert (terceiro - ultimo).days == teste_canal.INTERVALO_DIAS


# ---------------------------------------------------------------- o post pela extensão (2026-11-25)

def test_pela_extensao_o_video_vai_para_o_meu_dia_e_o_link_e_achado_no_canal(db, tmp_path, monkeypatch):
    from radar import youtube
    monkeypatch.setattr(fabrica_api.roteiro_claude, "FABRICA", tmp_path / "fabrica")
    monkeypatch.setattr(teste_canal, "POSTAR_PELA_EXTENSAO", True)
    chamou = []
    monkeypatch.setattr(fabrica_api, "youtube_publicar", lambda *a, **k: chamou.append(a))
    cartao = teste_canal.comecar(1, "UC1", "inglês", "Um")
    _entregues(cartao["videos"][0]["fid"])
    teste_canal._publicar_prontos()
    assert chamou == []                                           # a API da fábrica não sobe mais nada
    pendentes = teste_canal.pendentes_extensao(1)
    assert len(pendentes) == 1
    p = pendentes[0]
    assert p["canal"] == "UC1" and p["canalNome"] == "Um" and p["projeto"] == "projeto-1"
    assert p["agendar"] == teste_canal._primeira_hora().isoformat(timespec="minutes")
    assert teste_canal.do_canal(1, "UC1")["videos"][0]["manual"]
    from radar import publicar
    kit = publicar.kit(fabrica_api._pasta("projeto-1"))     # o que a extensão preenche no Studio: só o título
    assert kit["so_titulo"] and kit["titulo"] == cartao["videos"][0]["tema"] and kit["descricao"] == "" and kit["tags"] == []

    assert teste_canal.postado_extensao(1, p["id"], cartao["videos"][0]["tema"])
    assert teste_canal.pendentes_extensao(1) == []                # postado: sai do Meu dia
    monkeypatch.setattr(youtube, "envios", lambda canal, quantos=50: ["abcdefghijk"])
    monkeypatch.setattr(youtube, "videos", lambda ids: [{"id": "abcdefghijk", "titulo": cartao["videos"][0]["tema"]}])
    teste_canal._publicar_prontos()
    v = teste_canal.do_canal(1, "UC1")["videos"][0]
    assert v["video_id"] == "abcdefghijk" and v["url"].endswith("abcdefghijk")


def test_pela_extensao_a_hora_que_passou_vai_para_a_proxima_vaga(db, monkeypatch):
    monkeypatch.setattr(teste_canal, "POSTAR_PELA_EXTENSAO", True)
    cartao = teste_canal.comecar(1, "UC1", "inglês", "Um")
    _entregues(cartao["videos"][0]["fid"])
    teste_canal._publicar_prontos()
    linha = teste_canal._linha(1, "UC1")
    pedidos = teste_canal._pedidos(linha)
    pedidos[0]["agendado_para"] = (datetime.now() - timedelta(hours=2)).isoformat(timespec="minutes")
    teste_canal._gravar_pedidos(1, "UC1", pedidos)
    teste_canal._publicar_prontos()
    v = teste_canal.do_canal(1, "UC1")["videos"][0]
    assert v["agendado_para"] == teste_canal._primeira_hora().isoformat(timespec="minutes") and "remarcado" in v["erro"]


# ---------------------------------------------------------------- a aba Canais de teste do YouTube (2026-11-25)

def test_pela_extensao_qualquer_canal_pelo_arroba_serve(db, monkeypatch):
    monkeypatch.setattr(teste_canal, "POSTAR_PELA_EXTENSAO", True)
    assert teste_canal.comecar(1, "UC9", "inglês", "Nono")["estado"] == "liberado"   # sem login do Google


def test_a_pessoa_posta_e_a_aba_mostra_cada_canal_com_os_tres_videos(db, monkeypatch):
    """2026-11-25: o Radar não posta mais; marca o dia de cada vídeo e confere no canal se a pessoa postou."""
    from radar import youtube
    monkeypatch.setattr(teste_canal, "O_RADAR_POSTA", False)
    monkeypatch.setattr(teste_canal, "_CONFERIDO", {})
    enviados = []
    monkeypatch.setattr(fabrica_api, "youtube_publicar", lambda *a, **k: enviados.append(a) or {})
    cartao = teste_canal.comecar(1, "UC1", "inglês", "Um")
    teste_canal._publicar_prontos()
    pedidos = teste_canal._pedidos(teste_canal._linha(1, "UC1"))
    datas = [datetime.fromisoformat(p["agendado_para"]) for p in pedidos]
    assert enviados == [] and teste_canal.pendentes_extensao(1) == []          # nada sobe; nada pronto ainda
    r = teste_canal.resumo_extensao(1)["canais"][0]
    assert [v["cor"] for v in r["videos"]][1:] == ["azul", "azul"] and not any(v["id"] for v in r["videos"])
    # o vídeo pronto vai para a extensão sem o postar sozinho: o Postar é da pessoa, pela aba
    _entregues(cartao["videos"][1]["fid"])
    teste_canal._publicar_prontos()
    guardados = teste_canal.pendentes_extensao(1)
    assert len(guardados) == 1 and guardados[0]["auto"] is False and enviados == []
    assert teste_canal.resumo_extensao(1)["canais"][0]["videos"][1]["id"] == guardados[0]["id"]
    assert [(b - a).days for a, b in zip(datas, datas[1:])] == [teste_canal.INTERVALO_DIAS] * 2
    assert all(d.hour == teste_canal.HORA_DO_POST for d in datas)

    # o primeiro dia chegou e o canal não postou: vermelho
    pedidos[0]["agendado_para"] = (datetime.now() - timedelta(hours=1)).isoformat(timespec="minutes")
    teste_canal._gravar_pedidos(1, "UC1", pedidos)
    banco.executar("UPDATE canais_teste SET liberado=? WHERE canal_id='UC1'",
                   (datetime.now() - timedelta(days=1)).astimezone().isoformat(timespec="seconds"))
    monkeypatch.setattr(youtube, "envios", lambda canal, n: [])
    teste_canal.conferir_postados(1, 0)
    r = teste_canal.resumo_extensao(1)
    assert r["para_postar"] == 1 and [v["cor"] for v in r["canais"][0]["videos"]] == ["vermelho", "azul", "azul"]

    # a pessoa postou (qualquer vídeo vale): verde, e o vídeo antigo do canal não conta
    publicado = (datetime.now() - timedelta(minutes=30)).astimezone().isoformat()
    velho = (datetime.now() - timedelta(days=30)).astimezone().isoformat()
    monkeypatch.setattr(youtube, "envios", lambda canal, n: ["novo", "velho"])
    monkeypatch.setattr(youtube, "videos", lambda ids: [{"id": "novo", "titulo": "Meu cachorro", "publicado": publicado},
                                                        {"id": "velho", "titulo": "Antigo", "publicado": velho}])
    assert teste_canal.conferir_postados(1, 0) == ["UC1"]
    r = teste_canal.resumo_extensao(1)
    assert r["para_postar"] == 0 and r["canais"][0]["videos"][0]["cor"] == "verde" and r["canais"][0]["postados"] == 1
    assert teste_canal._pedidos(teste_canal._linha(1, "UC1"))[0]["video_id"] == "novo"

    # no ar há dois dias: hoje é dia de olhar as métricas; abriu, o aviso sai
    pedidos = teste_canal._pedidos(teste_canal._linha(1, "UC1"))
    pedidos[0]["agendado_para"] = (datetime.now() - timedelta(days=2)).isoformat(timespec="minutes")
    teste_canal._gravar_pedidos(1, "UC1", pedidos)
    assert teste_canal.resumo_extensao(1)["canais"][0]["avaliar_hoje"]
    teste_canal.olhou_metricas(1, "UC1")
    assert not teste_canal.resumo_extensao(1)["canais"][0]["avaliar_hoje"]
    with pytest.raises(ValueError):
        teste_canal.avaliar(1, "UC1", "ótimo")


def test_so_titulo_usa_o_titulo_traduzido_e_conserta_o_kit_velho(db, monkeypatch):
    from radar import publicar
    monkeypatch.setattr(teste_canal, "POSTAR_PELA_EXTENSAO", True)
    cartao = teste_canal.comecar(1, "UC1", "holandês", "Japão")
    _entregues(cartao["videos"][0]["fid"])
    pasta = fabrica_api._pasta("projeto-1")
    pasta.mkdir(parents=True)
    # o kit do roteiro, com descrição e tags, já estava lá (o vídeo entrou na extensão antes do só título)
    (pasta / "publicacao_radar.json").write_text('{"titulo": "Wat Leeft Op de Bodem", "descricao": "lang", "tags": ["a"]}',
                                                 encoding="utf-8")
    teste_canal._publicar_prontos()
    kit = publicar.kit(pasta)
    assert kit["titulo"] == "Wat Leeft Op de Bodem" and kit["descricao"] == "" and kit["tags"] == [] and kit["so_titulo"]
    (pasta / "publicacao_radar.json").write_text('{"titulo": "Wat Leeft Op de Bodem", "descricao": "lang", "tags": ["a"]}',
                                                 encoding="utf-8")
    teste_canal.pendentes_extensao(1)                        # a extensão pedindo: o kit volta a ser só o título
    assert publicar.kit(pasta)["descricao"] == "" and publicar.kit(pasta)["titulo"] == "Wat Leeft Op de Bodem"


# ---------------------------------------------------------------- nunca o mesmo vídeo duas vezes (2026-11-25)

def _com_pedidos(canal_id, pedidos, estado="liberado", liberado=""):
    import json
    banco.executar("INSERT INTO canais_teste (usuario_id, canal_id, estado, criado, lingua, pedidos, liberado) "
                   "VALUES (?,?,?,?,?,?,?)", 1, canal_id, estado, banco.agora(), "inglês",
                   json.dumps(pedidos), liberado or banco.agora())


def test_o_repetido_ainda_nao_postado_e_trocado_por_um_novo(db):
    sol = "The Day the Sun Will Die"
    _com_pedidos("UCA", [{"fid": 1, "tema": sol, "url": "https://youtu.be/x", "enviado": True}], "feito", "2026-11-17")
    _com_pedidos("UCB", [{"fid": 2, "tema": sol, "manual": True, "agendado_para": "2026-11-26T18:00", "projeto": "p2"},
                         {"fid": 3, "tema": "the day the SUN will die ", "manual": True},
                         {"fid": 4, "tema": "Why Mars Lost Its Atmosphere"}], "liberado", "2026-11-18")
    trocados = teste_canal._trocar_repetidos()
    assert trocados == ["2", "3"]
    temas = [p["tema"] for p in teste_canal._pedidos(teste_canal._linha(1, "UCB"))]
    assert len(temas) == 3 and sol not in temas and len({fila._chave_titulo(t) for t in temas}) == 3
    novos = teste_canal._pedidos(teste_canal._linha(1, "UCB"))[:2]
    assert all(not p.get("agendado_para") and not p.get("manual") and p["trocou"] for p in novos)
    # o que já foi ao ar nunca é trocado, e a segunda volta não mexe em nada
    assert teste_canal._pedidos(teste_canal._linha(1, "UCA"))[0]["fid"] == 1
    assert teste_canal._trocar_repetidos() == []


def test_o_video_do_banco_vai_para_um_canal_so(db, tmp_path, monkeypatch):
    banco.executar("INSERT INTO meus_canais (usuario_id, canal_id, criado) VALUES (?,?,?)", 1, "UC2", banco.agora())
    v = _no_banco(tmp_path, monkeypatch)
    primeiro = teste_canal.comecar(1, "UC1", "inglês", "Um", "banco")
    segundo = teste_canal.comecar(1, "UC2", "inglês", "Dois", "banco")
    assert [x["origem"] for x in primeiro["videos"]].count("banco") == 1
    assert [x["origem"] for x in segundo["videos"]].count("banco") == 0     # o do cachorro já foi para o UC1
    assert teste_canal._do_banco_para(1, "UC2", 3) == [] and v["id"]


def test_nao_testar_para_o_canal_e_testar_de_novo_volta(db):
    teste_canal.oferecer(1, "UC1")
    cartao = teste_canal.liberar(1, "UC1")
    fids = [v["fid"] for v in cartao["videos"]]
    teste_canal.dispensar(1, "UC1")
    assert teste_canal.todos(1) == [] and teste_canal.sem_teste(1)[0]["canal_id"] == "UC1"
    assert all(fila.item(1, f)["estado"] == "cancelado" for f in fids)    # nem começaram: não gastam a fila
    assert teste_canal._trocar_repetidos() == [] and teste_canal._soltar_um_parado() == []
    assert teste_canal.pendentes_extensao(1) == []
    teste_canal.voltar(1, "UC1")
    assert teste_canal._linha(1, "UC1")["estado"] == "liberado"
    assert all(fila.item(1, f)["estado"] == "entrada" for f in fids)
    with pytest.raises(ValueError):
        teste_canal.voltar(1, "UC1")


def test_o_botao_postar_sozinho_publica_na_hora_sem_agendar(db, monkeypatch):
    monkeypatch.setattr(teste_canal, "O_RADAR_POSTA", False)
    cartao = teste_canal.comecar(1, "UC1", "inglês", "Um")
    _entregues(cartao["videos"][0]["fid"])
    teste_canal._publicar_prontos()
    assert [(t["auto"], t["naHora"]) for t in teste_canal.pendentes_extensao(1)] == [(False, False)]
    teste_canal.postar_sozinho(1, "UC1", True)
    assert teste_canal.resumo_extensao(1)["canais"][0]["sozinho"]
    assert [(t["auto"], t["naHora"]) for t in teste_canal.pendentes_extensao(1)] == [(True, True)]
    teste_canal.postar_sozinho(1, "UC1", False)
    assert not teste_canal.resumo_extensao(1)["canais"][0]["sozinho"]
    with pytest.raises(ValueError):
        teste_canal.postar_sozinho(1, "UC9", True)
