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


def test_liberar_cria_os_dois_pedidos_sem_narracao(db):
    teste_canal.oferecer(1, "UC1")
    cartao = teste_canal.liberar(1, "UC1", "português")
    assert cartao["estado"] == "liberado" and len(cartao["videos"]) == 2
    temas = [v["tema"] for v in cartao["videos"]]
    assert temas == list(teste_canal.TEMAS[:2]) and len(set(temas)) == 2
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


def test_o_primeiro_sobe_na_hora_e_o_outro_no_dia_seguinte(db, monkeypatch):
    enviados = []
    monkeypatch.setattr(fabrica_api, "youtube_publicar",
                        lambda nome, canal, quando="", com_thumbnail=True, **r:
                        enviados.append((nome, canal, quando, com_thumbnail)) or {"sucesso": True})
    monkeypatch.setattr(fabrica_api, "youtube_do_projeto", lambda nome: None)
    teste_canal.oferecer(1, "UC1")
    cartao = teste_canal.liberar(1, "UC1")
    _entregues(*[v["fid"] for v in cartao["videos"]])

    teste_canal._publicar_prontos()
    assert [e[1] for e in enviados] == ["UC1", "UC1"]                  # os dois no canal do teste
    assert [e[3] for e in enviados] == [False, False]                  # sem thumbnail: o YouTube usa os quadros dele
    assert enviados[0][2] == ""                                        # o primeiro sobe na hora, sem publishAt
    segundo = datetime.fromisoformat(enviados[1][2])
    assert segundo.date() == (datetime.now() + timedelta(days=1)).date()
    assert segundo.hour == teste_canal.HORA_DO_POST
    depois = teste_canal.do_canal(1, "UC1")
    assert depois["estado"] == "feito" and all(v["agendado_para"] for v in depois["videos"])

    teste_canal._publicar_prontos()
    assert len(enviados) == 2                                          # nada sobe duas vezes


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
    monkeypatch.setattr(teste_canal, "ESTOQUE", 2)
    guardados = _encher(2)
    teste_canal.oferecer(1, "UC1")
    assert teste_canal.do_canal(1, "UC1")["estoque"] == 2
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
    # o primeiro subiu na hora: é a vez da pessoa tirar do privado. O outro espera o dia dele
    assert [v["estado"] for v in videos] == ["postar", "espera"]
    assert canais[0]["postar"] == 1

    depois = teste_canal.conferir(1, "UC1", videos[0]["fid"])
    assert [v["estado"] for v in depois[0]["videos"]] == ["publico", "espera"]
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
