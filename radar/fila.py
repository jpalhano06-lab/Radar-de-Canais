"""A fila da Nova produção (pedido do usuário em 2026-10-18): os pedidos de vídeo esperam aqui e o vigia manda para a
fábrica quando abre vaga, no limite de vídeos ao mesmo tempo.

Estados: entrada (guardado, não começa) → na_fila → escrevendo (o Claude faz o roteiro) → sua_vez (esperando a
revisão, se ligada) → enviando → produzindo → entregue; ou erro e cancelado. "Criar e começar" é o sim para gastar:
o vigia chama a produção da fábrica já confirmada."""
import json
import threading
import time

from . import banco, fabrica_api
from .config import FABRICA

ESTADOS = ("entrada", "na_fila", "escrevendo", "sua_vez", "enviando", "produzindo", "pausado", "entregue", "erro",
           "cancelado")
PAUSAVEIS = ("entrada", "na_fila", "sua_vez", "produzindo", "erro")   # escrevendo e enviando terminam em segundos
CARACTERES_POR_PALAVRA = 5.9      # média do inglês e do português narrados, com o espaço
MIN_CARACTERES, MAX_CARACTERES = 1000, 80000
LIMITES = (1, 2, 3, 4, 6, 8)
ESCRITAS_AO_MESMO_TEMPO = 2       # roteiros pelo Claude ao mesmo tempo (20 pedidos de uma vez eram 20 chamadas juntas)
CAMPOS = ("titulo", "link", "canal_id", "agente_id", "lingua", "caracteres", "roteiro_manual", "nicho", "observacao",
          "revisar", "perfil", "footage_real", "ia_pct", "tema", "escolhido_na_tela", "destino", "ritmo", "edicao", "transicao", "camada", "ia", "acervo",
          "avatar", "musica", "som_textos", "video_ia", "animacoes", "transcricao_ref", "sem_narracao", "prompt_id")
# o Canal de teste sem narração (pedido do usuário em 2026-11-12): não narra nada e não usa IA de imagem nem de
# vídeo, só banco grátis (Pexels/Pixabay). A língua escolhida vale só para os textos na tela (os motions). O perfil da
# fábrica é o sem-narracao (voz do computador só para medir o tempo, muda no vídeo final: narracao_no_video: false)
MINUTOS_SEM_NARRACAO = 4   # eram 5 até 2026-11-17, quando viraram os dois vídeos de teste de cada canal novo
PERFIL_SEM_NARRACAO = {"português": "sem-narracao"}   # as outras línguas: SEM_NARRACAO_OUTRAS
SEM_NARRACAO_OUTRAS = "sem-narracao-en"
FOOTAGE_REAL = (0, 15, 25, 40)    # % das cenas com trecho de vídeo real do YouTube (o garimpo da fábrica)
# % das cenas com imagem de IA. A barra é livre, de 0 a 100 (pedido do usuário em 2026-11-16): a fábrica mira na parte
# mais perto que o número de cenas permite, sem obrigação de bater exato. Sem escolha, quem decide é o agente de cenas, até ia.teto
IA_PCT = tuple(range(101))
# o que a Nova produção deixa escolher por vídeo. Vazio é o padrão do canal, e aí nada é gravado no projeto
ESCOLHAS = {
    "tema": ("noticiario", "dossie", "cinema", "jornal", "caderno", "planilha", "hacker", "terror", "colagem", "cinetico",
             "arquivo", "reaberto", "investigacao"),  # animacoes.TEMAS
    "ritmo": ("4-6", "5-8"),
    "edicao": ("documentario", "investigacao", "noticiario", "energia", "cinema"),  # render.VISUAIS
    # render.TRANSICOES e render.TRANSICOES_DE_LUZ (as de luz vieram do estudo da Dotti, 2026-11-22)
    "transicao": ("preto", "branco", "brasa", "flash", "queima", "superexposicao", "dissolve", "derreter"),
    "camada": ("brasas", "poeira", "douradas", "vazando"),  # render.CAMADAS
    "ia": ("sem",),
    "acervo": ("sem", "sempre"),
    "avatar": ("sem",),
    "musica": ("sem",),
    "som_textos": ("sim",),
    "video_ia": ("10", "25"),  # % das cenas de imagem de IA que ganham movimento; cada clipe é pago à parte
}


def opcoes_do(usuario_id: int, pedido: dict, cfg: dict | None = None) -> dict:
    """O que vai para o projeto. O que o pedido não disse vem do agente; a Nova produção já mostrou o do agente e a
    pessoa pode ter mudado, então o que vem dela (escolhido_na_tela) fica como está."""
    opcoes = {k: pedido[k] for k in ("footage_real", *ESCOLHAS) if pedido.get(k)}
    if pedido.get("ia_pct") is not None:
        opcoes["ia_pct"] = int(pedido["ia_pct"])
    if pedido.get("sem_narracao"):
        return opcoes | {"sem_narracao": True}   # nada do agente: sem IA, sem footage do YouTube
    agente = pedido.get("agente_id") or (cfg or {}).get("projeto_roteiro_id")
    if pedido.get("escolhido_na_tela") or not agente:
        return opcoes
    linha = banco.um("SELECT tema, ia_pct, footage_real FROM projetos_roteiro WHERE id=? AND usuario_id=?",
                     int(agente), usuario_id)
    if not linha:
        return opcoes
    if "tema" not in opcoes and linha["tema"] in ESCOLHAS["tema"]:
        opcoes["tema"] = linha["tema"]
    if "ia_pct" not in opcoes and linha["ia_pct"] is not None:
        opcoes["ia_pct"] = linha["ia_pct"]
    if "footage_real" not in pedido and linha["footage_real"]:
        opcoes["footage_real"] = linha["footage_real"]
    return opcoes


def minutos_de(caracteres: int, ppm: int) -> float:
    return caracteres / CARACTERES_POR_PALAVRA / max(1, ppm)


def caracteres_de(minutos: float, ppm: int) -> int:
    return int(round(minutos * ppm * CARACTERES_POR_PALAVRA / 10) * 10)


def _publico(linha: dict | None) -> dict | None:
    if not linha:
        return None
    pedido = json.loads(linha["pedido"] or "{}")
    # a transcrição da referência (até 80 mil letras) não vai na lista que o Acompanhar e a extensão leem a toda hora
    if pedido.pop("transcricao_ref", None):
        pedido["com_transcricao_ref"] = True
    return {k: v for k, v in linha.items() if k not in ("pedido", "lease")} | {"pedido": pedido}


class Repetido(ValueError):
    """Já existe um pedido com o mesmo título: só entra outro se a pessoa confirmar (pedido de 2026-11-24)."""


def _chave_titulo(titulo: str) -> str:
    return " ".join(str(titulo or "").split()).casefold()


def pedido_igual(usuario_id: int, titulo: str) -> dict | None:
    """O pedido mais antigo deste usuário com o mesmo título (sem olhar maiúsculas e espaços). O cancelado não conta."""
    chave = _chave_titulo(titulo)
    for linha in banco.todos("SELECT id, estado, pedido FROM producoes_fila WHERE usuario_id=? AND estado!='cancelado' "
                             "ORDER BY id", usuario_id):
        if _chave_titulo(json.loads(linha["pedido"] or "{}").get("titulo")) == chave:
            return {"id": linha["id"], "estado": linha["estado"]}
    return None


def criar(usuario_id: int, pedido: dict, comecar: bool, repetir: bool = False) -> dict:
    limpo = {k: pedido.get(k) for k in CAMPOS if pedido.get(k) not in (None, "")}
    limpo["titulo"] = str(pedido.get("titulo") or "").strip()
    if not limpo["titulo"]:
        raise ValueError("Escreva o título do vídeo.")
    # vídeo saindo em dobro na fábrica (2026-11-24): pedido com título igual a outro só entra com confirmação
    if not repetir and (igual := pedido_igual(usuario_id, limpo["titulo"])):
        raise Repetido(f"Já existe um pedido com esse título (nº {igual['id']}, {igual['estado'].replace('_', ' ')}).")
    limpo["revisar"] = bool(pedido.get("revisar"))
    if limpo.get("sem_narracao"):
        if limpo.get("canal_id"):
            raise ValueError("O vídeo sem narração é só do Canal de teste.")
        # sem IA nenhuma e sem avatar, venha o que vier; o perfil sai da língua (ela só muda os textos na tela)
        limpo |= {"sem_narracao": True, "ia": "sem", "avatar": "sem",
                  "perfil": PERFIL_SEM_NARRACAO.get(limpo.get("lingua") or "português", SEM_NARRACAO_OUTRAS)}
        for campo in ("ia_pct", "video_ia", "footage_real"):
            limpo.pop(campo, None)
    if limpo.get("transcricao_ref"):  # a fala da referência lida pela extensão; o roteiro usa no máximo 60 mil letras
        limpo["transcricao_ref"] = str(limpo["transcricao_ref"])[:80000]
    if int(limpo.get("footage_real") or 0) not in FOOTAGE_REAL:
        raise ValueError("A parte de footage real vai de 0 a 40%.")
    if limpo.get("ia_pct") is not None:
        if int(limpo["ia_pct"]) not in IA_PCT:
            raise ValueError("Essa parte de IA não existe.")
        if int(limpo["ia_pct"]) + int(limpo.get("footage_real") or 0) > 100:
            raise ValueError("IA e YouTube juntos passam de 100% das cenas.")
    if limpo.get("destino") not in (None, "robo"):
        raise ValueError("Esse destino não existe.")
    for campo, validos in ESCOLHAS.items():
        if limpo.get(campo) and limpo[campo] not in validos:
            raise ValueError(f"A escolha de {campo} ({limpo[campo]}) não existe.")
    # a língua do pedido é a da voz do canal (2026-11-17): o pedido manda no roteiro e no título, por cima do agente,
    # então um pedido em outra língua faz o vídeo inteiro sair errado. O Canal de teste não tem canal e fica de fora
    if limpo.get("canal_id") and limpo.get("lingua"):
        from . import producao       # import tardio: o producao chega aqui pelo roteiro_claude
        producao.conferir_lingua(producao.config(usuario_id, limpo["canal_id"]).get("perfil", ""), limpo["lingua"])
    if not str(limpo.get("roteiro_manual") or "").strip():
        limpo.pop("roteiro_manual", None)
        caracteres = int(pedido.get("caracteres") or 0)
        if not MIN_CARACTERES <= caracteres <= MAX_CARACTERES:
            raise ValueError(f"O tamanho vai de {MIN_CARACTERES:,} a {MAX_CARACTERES:,} caracteres.".replace(",", "."))
        limpo["caracteres"] = caracteres
    agora = banco.agora()
    ordem = (banco.um("SELECT MAX(ordem) AS m FROM producoes_fila")["m"] or 0) + 1
    fid = banco.executar("INSERT INTO producoes_fila (usuario_id, criado, atualizado, estado, ordem, pedido) VALUES (?,?,?,?,?,?)",
                         usuario_id, agora, agora, "na_fila" if comecar else "entrada", ordem,
                         json.dumps(limpo, ensure_ascii=False))
    return item(usuario_id, fid)


def listar(usuario_id: int) -> list[dict]:
    return [_publico(l) for l in banco.todos("SELECT * FROM producoes_fila WHERE usuario_id=? AND estado!='cancelado' "
                                             "ORDER BY ordem", usuario_id)]


def item(usuario_id: int, fid: int) -> dict | None:
    return _publico(banco.um("SELECT * FROM producoes_fila WHERE id=? AND usuario_id=?", fid, usuario_id))


def mudar(fid: int, estado: str, de: tuple[str, ...] | None = None, **campos) -> bool:
    """Muda o estado. Com `de`, só muda se o pedido ainda estiver num desses estados (devolve se mudou): o vigia e a
    escrita do roteiro usam isso para nunca passar por cima de um pedido que a pessoa excluiu no meio."""
    if estado not in ESTADOS:
        raise ValueError(f"Estado desconhecido: {estado}")
    campos = {"estado": estado, "atualizado": banco.agora()} | campos
    sql = f"UPDATE producoes_fila SET {', '.join(f'{k}=?' for k in campos)} WHERE id=?"
    args = [*campos.values(), fid]
    if de:
        sql += f" AND estado IN ({', '.join('?' * len(de))})"
        args += list(de)
    with banco._TRAVA:
        c = banco.con()
        cur = c.execute(sql, args)
        c.commit()
        mudou = cur.rowcount > 0
    if mudou and estado == "entregue":
        # o aviso de vídeo pronto no celular (pedido do usuário em 2026-11-08), desta máquina ou de outra (maquinas.py)
        from . import avisos
        avisos.video_pronto(fid)
    return mudou


def _de(usuario_id: int, fid: int, *estados: str) -> dict:
    atual = item(usuario_id, fid)
    if not atual:
        raise ValueError("Esse pedido não existe.")
    if estados and atual["estado"] not in estados:
        raise ValueError("Esse pedido não pode fazer isso agora.")
    return atual


def comecar(usuario_id: int, fid: int) -> dict:
    _de(usuario_id, fid, "entrada")
    mudar(fid, "na_fila")
    return item(usuario_id, fid)


def aprovar(usuario_id: int, fid: int) -> dict:
    _de(usuario_id, fid, "sua_vez")
    mudar(fid, "na_fila", aprovado=1)
    return item(usuario_id, fid)


def tentar(usuario_id: int, fid: int) -> dict:
    _de(usuario_id, fid, "erro")
    mudar(fid, "na_fila", erro="")
    return item(usuario_id, fid)


def pausar(usuario_id: int, fid: int, fabrica=None) -> dict:
    """O botão Pausar (pedido do usuário em 2026-11-16). Na fila, o vigia pula o pedido. Produzindo, a fábrica segura a
    criação na próxima etapa e o vídeo deixa de ocupar vaga, para outro (um prioritário) passar."""
    atual = _de(usuario_id, fid, *PAUSAVEIS)
    if atual["estado"] == "produzindo":
        if atual.get("maquina_id"):
            raise ValueError("Esse vídeo está em outra máquina: lá não dá para pausar.")
        (fabrica or fabrica_api).pausar(atual["projeto"], True)
    if not mudar(fid, "pausado", de=(atual["estado"],), antes_pausa=atual["estado"]):
        raise ValueError("O pedido mudou agora há pouco. Tente de novo.")
    return item(usuario_id, fid)


def continuar(usuario_id: int, fid: int, fabrica=None) -> dict:
    atual = _de(usuario_id, fid, "pausado")
    antes = atual.get("antes_pausa") or "na_fila"
    if antes == "produzindo" and atual["projeto"]:
        (fabrica or fabrica_api).pausar(atual["projeto"], False)
    mudar(fid, antes if antes in ESTADOS else "na_fila", de=("pausado",), antes_pausa="")
    return item(usuario_id, fid)


def priorizar(usuario_id: int, fid: int) -> dict:
    """O botão Prioridade: o pedido vai para o topo da fila, o roteiro começa sem esperar a vez e ele vai para a fábrica
    mesmo com as vagas cheias (o limite ganha uma a mais para ele). Guardado (entrada), já começa."""
    atual = _de(usuario_id, fid, "entrada", "na_fila", "escrevendo", "sua_vez", "erro", "pausado")
    topo = (banco.um("SELECT MIN(ordem) AS m FROM producoes_fila")["m"] or 0) - 1
    banco.executar("UPDATE producoes_fila SET prioridade=1, ordem=?, atualizado=? WHERE id=?", topo, banco.agora(), fid)
    if atual["estado"] == "entrada":
        mudar(fid, "na_fila", de=("entrada",))
    return item(usuario_id, fid)


def excluir(usuario_id: int, fid: int) -> str:
    """Cancela o pedido e devolve o projeto da fábrica, se já existir (quem chama apaga lá)."""
    atual = _de(usuario_id, fid)
    mudar(fid, "cancelado")
    return atual["projeto"]


def limite() -> int:
    linha = banco.um("SELECT valor FROM ajustes WHERE chave='fila_limite'")
    return int(linha["valor"]) if linha else 2


def definir_limite(n: int) -> int:
    if int(n) not in LIMITES:
        raise ValueError("Escolha 1, 2, 3, 4, 6 ou 8 vídeos ao mesmo tempo.")
    banco.executar("INSERT OR REPLACE INTO ajustes (chave, valor) VALUES ('fila_limite', ?)", str(int(n)))
    return int(n)


# ---------------------------------------------------------------- o vigia: puxa a fila para a fábrica

_TRAVA = threading.Lock()
VOLTAS_PARADO = 2                 # voltas seguidas com o projeto parado na fábrica antes do pedido virar erro
_PARADOS: dict[int, int] = {}     # id do pedido -> essas voltas, só na memória do vigia


def reparar() -> None:
    """No startup: o que estava no meio (escrevendo, enviando) quando o servidor caiu volta para a fila."""
    banco.executar("UPDATE producoes_fila SET estado='na_fila', atualizado=? WHERE estado IN ('escrevendo', 'enviando')",
                   banco.agora())


def _padrao():
    from . import producao, roteiro_claude, tempo
    return fabrica_api, roteiro_claude, producao.config, tempo.ritmo


def _observacoes(pedido: dict) -> str:
    partes = [f"Nicho: {pedido['nicho']}" if pedido.get("nicho") else "", pedido.get("observacao") or ""]
    if pedido.get("sem_narracao"):
        # o número sai da constante para não discordar dela; a seção é citada sem o número, que mudou de 5 para 4
        partes.insert(0, f"MODO SEM NARRAÇÃO ({MINUTOS_SEM_NARRACAO} min): siga a seção do vídeo sem narração do "
                         f"agente, com {MINUTOS_SEM_NARRACAO} min em vez do tamanho que ela diz. Ninguém narra: o "
                         "texto vira só as cenas de banco grátis e os textos curtos na tela (motions).")
    return "\n".join(p for p in partes if p)[:1000]


def perfil_do(pedido: dict, cfg: dict) -> str:
    """O perfil da fábrica do vídeo: o que o pedido escolheu (o Canal de teste, que não é canal nenhum, escolhe a voz
    pela língua) ou o do canal."""
    return pedido.get("perfil") or cfg.get("perfil", "")


def minutos_do(pedido: dict, ppm: int) -> int:
    """Os minutos do roteiro pelo tamanho pedido. O Canal de teste (sem canal, com o perfil escolhido) é sempre de 2 a
    3 min (pedido do usuário em 2026-10-29), venha o tamanho que vier."""
    if eh_teste(pedido) and pedido.get("sem_narracao"):
        return MINUTOS_SEM_NARRACAO       # o sem narração (2026-11-12)
    minutos = max(1, round(minutos_de(pedido["caracteres"], ppm)))
    return min(3, max(2, minutos)) if eh_teste(pedido) else minutos


def eh_teste(pedido: dict) -> bool:
    return bool(pedido.get("perfil")) and not pedido.get("canal_id")


def _escrever(linha: dict, roteirista, config_canal, ritmo) -> None:
    """O roteiro do pedido (pelo Claude ou o colado). Termina em sua_vez (revisão) ou de volta na fila."""
    pedido = json.loads(linha["pedido"])
    cfg = config_canal(linha["usuario_id"], pedido["canal_id"]) if pedido.get("canal_id") else {}
    lingua = pedido.get("lingua") or cfg.get("lingua") or "português"
    canal = {"id": pedido.get("canal_id", ""), "titulo": cfg.get("canal", "")}
    try:
        if pedido.get("roteiro_manual"):
            r = roteirista.manual(usuario_id=linha["usuario_id"], titulo=pedido["titulo"], texto=pedido["roteiro_manual"],
                                  link=pedido.get("link", ""), minutos=0, lingua=lingua, canal=canal)
        else:
            ppm = ritmo(linha["usuario_id"], perfil_do(pedido, cfg), lingua)["ppm"]
            agente = pedido.get("agente_id") or cfg.get("projeto_roteiro_id")
            # o prompt do roteiro: o escolhido no pedido, senão o do canal, senão o padrão do Radar (2026-11-20)
            prompt = pedido.get("prompt_id") if "prompt_id" in pedido else cfg.get("prompt_id")

            def aviso(texto):
                mudar(linha["id"], "escrevendo", de=("escrevendo",), passo=texto[:200])
            r = roteirista.gerar(usuario_id=linha["usuario_id"], titulo=pedido["titulo"], link=pedido.get("link", ""),
                                 minutos=minutos_do(pedido, ppm), lingua=lingua,
                                 projeto_id=int(agente) if agente else None, observacoes=_observacoes(pedido),
                                 prompt_id=int(prompt) if str(prompt or "").isdigit() else None,
                                 perfil=perfil_do(pedido, cfg), canal=canal, aviso=aviso,
                                 transcricao_pronta=pedido.get("transcricao_ref") or "")
    except Exception as erro:  # noqa: BLE001 (qualquer falha do roteiro vira o erro do pedido, com o motivo)
        if type(erro).__name__ == "LimiteDoClaude":
            # o limite da assinatura não é defeito do pedido: ele volta para a fila e espera o limite renovar
            mudar(linha["id"], "na_fila", de=("escrevendo",), erro="", passo=str(erro)[:200])
            return
        mudar(linha["id"], "erro", de=("escrevendo",), erro=str(erro)[:500], passo="")
        return
    revisar = pedido.get("revisar") and not linha["aprovado"]
    # excluído enquanto o Claude escrevia: fica cancelado (antes ele voltava para a fila e ia para a fábrica)
    mudar(linha["id"], "sua_vez" if revisar else "na_fila", de=("escrevendo",), roteiro=r["nome"], passo="")


def passo(fabrica=None, roteirista=None, em_thread: bool = True, config_canal=None, ritmo=None) -> list[int]:
    """Uma volta do vigia. Devolve os ids que mudaram. A fábrica desligada só faz a volta terminar: nada vira erro.
    Um erro da fábrica sobre um projeto (ela não achou, recusou) é erro só daquele pedido: a volta segue para os
    outros (2026-10-30: a fábrica ligada na pasta errada não achava o projeto do primeiro da fila, e os de trás nem
    o roteiro começavam)."""
    if None in (fabrica, roteirista, config_canal, ritmo):
        padrao = _padrao()
        fabrica, roteirista = fabrica or padrao[0], roteirista or padrao[1]
        config_canal, ritmo = config_canal or padrao[2], ritmo or padrao[3]
    if not _TRAVA.acquire(blocking=False):
        return []
    mudaram = []
    try:
        # antes da fábrica: uma máquina de fora que sumiu não depende de a fábrica daqui estar ligada
        from . import agendar, maquinas, teste_canal   # import tardio: o teste_canal e o agendar usam esta fila

        mudaram += maquinas.expirar()
        # o teste dos canais novos: solta um pedido quando a fila está parada e agenda os que ficaram prontos
        teste_canal.andar()
        # os vídeos marcados para subir num dia: o que já está entregue vai para a fábrica publicar
        agendar.andar()
        try:
            prod = fabrica.producoes()
        except fabrica_api.SemFabrica:
            # desligada ou lenta (2026-11-16: a lista levou 37 s e o pedido 128 nem o roteiro começava): o roteiro
            # não precisa da fábrica, então ele anda; só o envio espera
            prod = None
        if prod is not None:
            mudaram += _acompanhar(prod)
            vagas = _vagas(prod)
        else:
            vagas = None
        # 3. a fila, na ordem (o prioritário antes): primeiro o roteiro (não ocupa vaga, até ESCRITAS_AO_MESMO_TEMPO),
        # depois o envio (ocupa). O prioritário passa por cima dos dois limites
        escrevendo = banco.um("SELECT COUNT(*) AS n FROM producoes_fila WHERE estado='escrevendo'")["n"]
        # o Claude no limite da assinatura: nenhum roteiro novo começa até renovar (o colado não precisa dele)
        pausa = getattr(roteirista, "pausa_do_claude", lambda: 0)()
        for linha in banco.todos("SELECT * FROM producoes_fila WHERE estado='na_fila' ORDER BY prioridade DESC, ordem"):
            if not linha["roteiro"]:
                if pausa and not json.loads(linha["pedido"]).get("roteiro_manual"):
                    continue
                if (escrevendo >= ESCRITAS_AO_MESMO_TEMPO and not linha["prioridade"]) or \
                        not mudar(linha["id"], "escrevendo", de=("na_fila",), passo="Começando…"):
                    continue
                escrevendo += 1
                mudaram.append(linha["id"])
                if em_thread:
                    threading.Thread(target=_escrever, args=(linha, roteirista, config_canal, ritmo), daemon=True).start()
                    continue
                _escrever(linha, roteirista, config_canal, ritmo)
                escrevendo -= 1
                linha = banco.um("SELECT * FROM producoes_fila WHERE id=?", linha["id"])
                if linha["estado"] != "na_fila" or not linha["roteiro"]:
                    continue          # sem roteiro (o Claude no limite): espera na fila, nada vai para a fábrica
            if json.loads(linha["pedido"]).get("destino") == "robo":
                continue  # com o roteiro pronto, espera uma máquina reivindicar (maquinas.py)
            if vagas is None:
                continue  # a fábrica não respondeu nesta volta
            if vagas <= 0 and not linha["prioridade"]:
                continue
            # cada passo só segue se o pedido ainda estiver onde estava: excluído no meio, para ali e não gasta
            if not mudar(linha["id"], "enviando", de=("na_fila",), passo="Enviando para a fábrica…"):
                continue
            pedido = json.loads(linha["pedido"])
            cfg = config_canal(linha["usuario_id"], pedido["canal_id"]) if pedido.get("canal_id") else {}
            projeto = linha["projeto"]
            try:
                if not projeto:
                    # o projeto fica guardado assim que existe: "Tentar de novo" e um reinício reaproveitam, sem pagar outro
                    opcoes = opcoes_do(linha["usuario_id"], pedido, cfg)
                    projeto = roteirista.enviar(linha["usuario_id"], linha["roteiro"], perfil_do(pedido, cfg),
                                                **({"opcoes": opcoes} if opcoes else {}))["projeto"]
                    banco.executar("UPDATE producoes_fila SET projeto=? WHERE id=?", projeto, linha["id"])
                if not mudar(linha["id"], "enviando", de=("enviando",)):
                    continue
                try:   # a regra Todos pela conexão vale antes de o vídeo começar a gerar imagem
                    from . import producao
                    producao.aplicar_regra()
                except Exception as erro:  # noqa: BLE001 — a regra nunca segura o vídeo
                    print("a regra das imagens não deu para aplicar:", str(erro)[:160])
                if pedido.get("animacoes"):      # o estilo escolhido só para este vídeo, na Nova produção
                    fabrica.definir_animacoes(projeto, pedido["animacoes"])
                fabrica.produzir(projeto, confirmar=True)
                if mudar(linha["id"], "produzindo", de=("enviando",), passo=""):
                    vagas -= 1
            except fabrica_api.FabricaDesligada:
                # a fábrica caiu no meio da volta: o pedido espera, sem erro, e o resto da fila espera com ele
                mudar(linha["id"], "na_fila", de=("enviando",), passo="")
                return mudaram
            except Exception as erro:  # noqa: BLE001 (inclusive um erro da fábrica sobre este projeto: só este para)
                mudar(linha["id"], "erro", de=("enviando",), erro=str(erro)[:500], passo="")
            mudaram.append(linha["id"])
        return mudaram
    finally:
        _TRAVA.release()


def _acompanhar(prod: dict) -> list[int]:
    """Os passos 1 e 1b da volta: o que a fábrica terminou, perdeu ou retomou por fora."""
    mudaram = []
    prontos = {p["nome"] for p in prod["prontos"]}
    andamento = {p["nome"]: p for p in prod["andamento"]}
    # 1. o que estava produzindo: ficou pronto, deu erro, parou no meio ou sumiu da fábrica
    # o que está em outra máquina não passa por aqui: a fábrica daqui não conhece esse projeto
    for linha in banco.todos("SELECT * FROM producoes_fila WHERE estado='produzindo' AND maquina_id IS NULL"):
        p = andamento.get(linha["projeto"])
        if linha["projeto"] in prontos:
            mudou = mudar(linha["id"], "entregue", de=("produzindo",))
        elif p is None:
            mudou = mudar(linha["id"], "erro", de=("produzindo",), erro="O vídeo sumiu da fábrica.")
        elif p.get("status") == "erro":
            mudou = mudar(linha["id"], "erro", de=("produzindo",), erro=(p.get("mensagem") or "A fábrica parou com erro.")[:500])
        elif not p.get("rodando") and p.get("status") == "parado":
            # a fábrica morta no meio religa sem o andamento (ele mora na memória dela): o projeto volta parado,
            # sem erro nenhum, e o pedido ficava "produzindo" para sempre, segurando uma vaga (o vídeo do João o
            # Lobo, 2026-11-04). Vira erro só depois de VOLTAS_PARADO voltas paradas, para não confundir com o
            # instante entre o "produzir" e a fábrica começar de verdade.
            _PARADOS[linha["id"]] = _PARADOS.get(linha["id"], 0) + 1
            if _PARADOS[linha["id"]] < VOLTAS_PARADO:
                continue
            mudou = mudar(linha["id"], "erro", de=("produzindo",), passo="",
                          erro="A fábrica parou no meio deste vídeo (ela foi desligada ou caiu). "
                               "O \"Tentar de novo\" retoma de onde ela parou.")
        else:
            _PARADOS.pop(linha["id"], None)
            continue
        _PARADOS.pop(linha["id"], None)
        if mudou:
            mudaram.append(linha["id"])
    # 1b. o que parou com erro e foi retomado na fábrica por fora do Radar volta a produzindo (12-animais, 2026-10-27:
    # retomado depois do crédito do OpenRouter, o pedido seguia "Parou com erro" com a fábrica andando)
    for linha in banco.todos("SELECT * FROM producoes_fila WHERE estado='erro' AND projeto IS NOT NULL AND projeto != ''"):
        p = andamento.get(linha["projeto"])
        if p and p.get("rodando") and p.get("status") != "erro" and mudar(linha["id"], "produzindo", de=("erro",), erro=""):
            mudaram.append(linha["id"])
    return mudaram


def _vagas(prod: dict) -> int:
    """2. as vagas: o limite menos o que a fila mandou e os vídeos da fábrica feitos fora dela. O pausado não conta: a
    fábrica ainda o mostra rodando, mas ele está parado esperando o Continuar."""
    da_fila = {l["projeto"] for l in banco.todos("SELECT projeto FROM producoes_fila WHERE estado IN ('enviando', 'produzindo') "
                                                 "AND maquina_id IS NULL")}
    pausados = {l["projeto"] for l in banco.todos("SELECT projeto FROM producoes_fila WHERE estado='pausado' AND projeto != ''")}
    fora = [p["nome"] for p in prod["andamento"] if p.get("rodando") and p["nome"] not in da_fila | pausados]
    return limite() - len(da_fila) - len(fora)


def iniciar_vigia(intervalo: int = 20) -> None:
    reparar()

    def rodar():
        while True:
            try:
                passo()
            except Exception as erro:  # noqa: BLE001 (o vigia nunca pode parar)
                print("vigia da fila:", erro)
            time.sleep(intervalo)
    threading.Thread(target=rodar, daemon=True, name="vigia-fila").start()


# ---------------------------------------------------------------- o custo provável, na prévia da Nova produção

CENAS_POR_MINUTO = 17         # medido: 518 cenas nos 30 min do os-10-leoes
IMAGEM_NA_RESERVA = 0.005     # US$ por imagem pela chave de API, quando o limite da assinatura acaba (medido)
IA_DOS_ENTREGUES = 0.25       # a parte de IA dos vídeos que servem de média: a conferência olha só o resto


def estimativa(entregues: list[dict], canal: str, minutos: float, ia_pct: int | None = None) -> dict:
    """Minutos × a média de US$ por minuto dos vídeos entregues do canal (sem nenhum, a de todos). Com a parte de IA
    escolhida: tira da média o que foi pago em imagem, a conferência acompanha o que sobra de material real, e
    usd_limite diz quanto fica se a assinatura do ChatGPT não der conta e todas as imagens saírem pela chave."""
    do_canal = [e for e in entregues if e["canal"] == canal]
    lista, base = (do_canal, "canal") if do_canal else (entregues, "geral")
    total = sum(e["minutos"] for e in lista)
    if not total:
        return {"usd": None, "base": None}
    media = sum(e["usd"] for e in lista) / total
    if ia_pct is None:
        return {"usd": round(media * minutos, 2), "base": base}
    imagem = sum(e.get("imagem", 0) for e in lista) / total
    conferencia = sum(e.get("conferencia", 0) for e in lista) / total
    sobra_real = (1 - ia_pct / 100) / (1 - IA_DOS_ENTREGUES)
    usd = (media - imagem - conferencia + conferencia * sobra_real) * minutos
    imagens = round(CENAS_POR_MINUTO * minutos * ia_pct / 100)
    return {"usd": round(usd, 2), "base": base, "imagens": imagens, "usd_limite": round(usd + imagens * IMAGEM_NA_RESERVA, 2)}


_ENTREGUES: dict = {"t": 0, "lista": []}


def entregues() -> list[dict]:
    """Os vídeos prontos da fábrica com o canal, os minutos e o custo real (custos_reais.json). Guardado 1 hora."""
    if time.time() - _ENTREGUES["t"] < 3600:
        return _ENTREGUES["lista"]
    from . import custos
    lista = []
    for p in fabrica_api.producoes()["prontos"]:
        # o total da fábrica (com os modelos de texto e visão, que o custos_reais.json não tem)
        try:
            fabrica = fabrica_api.custo(p["nome"])
        except fabrica_api.SemFabrica:
            fabrica = None
        gastos = custos.combinar(fabrica, custos.linhas(FABRICA / "projetos" / p["nome"]))
        usd = sum(l["usd"] for l in gastos)
        if usd and p.get("duracao"):
            # "canal" aqui é o perfil da fábrica: é ele que a Nova produção conhece de cada canal
            lista.append({"canal": p.get("perfil") or "", "minutos": p["duracao"] / 60, "usd": usd,
                          "imagem": sum(l["usd"] for l in gastos if l["categoria"] == "imagem"),
                          "conferencia": sum(l["usd"] for l in gastos if l["categoria"] in ("visao", "juiz"))})
    _ENTREGUES.update(t=time.time(), lista=lista)
    return lista
