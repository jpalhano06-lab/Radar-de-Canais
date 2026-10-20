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

ESTADOS = ("entrada", "na_fila", "escrevendo", "sua_vez", "enviando", "produzindo", "entregue", "erro", "cancelado")
CARACTERES_POR_PALAVRA = 5.9      # média do inglês e do português narrados, com o espaço
MIN_CARACTERES, MAX_CARACTERES = 1000, 80000
LIMITES = (1, 2, 3, 4, 6, 8)
ESCRITAS_AO_MESMO_TEMPO = 2       # roteiros pelo Claude ao mesmo tempo (20 pedidos de uma vez eram 20 chamadas juntas)
CAMPOS = ("titulo", "link", "canal_id", "agente_id", "lingua", "caracteres", "roteiro_manual", "nicho", "observacao",
          "revisar")


def minutos_de(caracteres: int, ppm: int) -> float:
    return caracteres / CARACTERES_POR_PALAVRA / max(1, ppm)


def caracteres_de(minutos: float, ppm: int) -> int:
    return int(round(minutos * ppm * CARACTERES_POR_PALAVRA / 10) * 10)


def _publico(linha: dict | None) -> dict | None:
    if not linha:
        return None
    return {k: v for k, v in linha.items() if k != "pedido"} | {"pedido": json.loads(linha["pedido"] or "{}")}


def criar(usuario_id: int, pedido: dict, comecar: bool) -> dict:
    limpo = {k: pedido.get(k) for k in CAMPOS if pedido.get(k) not in (None, "")}
    limpo["titulo"] = str(pedido.get("titulo") or "").strip()
    if not limpo["titulo"]:
        raise ValueError("Escreva o título do vídeo.")
    limpo["revisar"] = bool(pedido.get("revisar"))
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
        return cur.rowcount > 0


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


def reparar() -> None:
    """No startup: o que estava no meio (escrevendo, enviando) quando o servidor caiu volta para a fila."""
    banco.executar("UPDATE producoes_fila SET estado='na_fila', atualizado=? WHERE estado IN ('escrevendo', 'enviando')",
                   banco.agora())


def _padrao():
    from . import producao, roteiro_claude, tempo
    return fabrica_api, roteiro_claude, producao.config, tempo.ritmo


def _observacoes(pedido: dict) -> str:
    partes = [f"Nicho: {pedido['nicho']}" if pedido.get("nicho") else "", pedido.get("observacao") or ""]
    return "\n".join(p for p in partes if p)[:1000]


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
            ppm = ritmo(linha["usuario_id"], cfg.get("perfil", ""), lingua)["ppm"]
            agente = pedido.get("agente_id") or cfg.get("projeto_roteiro_id")

            def aviso(texto):
                mudar(linha["id"], "escrevendo", de=("escrevendo",), passo=texto[:200])
            r = roteirista.gerar(usuario_id=linha["usuario_id"], titulo=pedido["titulo"], link=pedido.get("link", ""),
                                 minutos=max(1, round(minutos_de(pedido["caracteres"], ppm))), lingua=lingua,
                                 projeto_id=int(agente) if agente else None, observacoes=_observacoes(pedido),
                                 perfil=cfg.get("perfil", ""), canal=canal, aviso=aviso)
    except Exception as erro:  # noqa: BLE001 (qualquer falha do roteiro vira o erro do pedido, com o motivo)
        mudar(linha["id"], "erro", de=("escrevendo",), erro=str(erro)[:500], passo="")
        return
    revisar = pedido.get("revisar") and not linha["aprovado"]
    # excluído enquanto o Claude escrevia: fica cancelado (antes ele voltava para a fila e ia para a fábrica)
    mudar(linha["id"], "sua_vez" if revisar else "na_fila", de=("escrevendo",), roteiro=r["nome"], passo="")


def passo(fabrica=None, roteirista=None, em_thread: bool = True, config_canal=None, ritmo=None) -> list[int]:
    """Uma volta do vigia. Devolve os ids que mudaram. A fábrica desligada só faz a volta terminar: nada vira erro."""
    if None in (fabrica, roteirista, config_canal, ritmo):
        padrao = _padrao()
        fabrica, roteirista = fabrica or padrao[0], roteirista or padrao[1]
        config_canal, ritmo = config_canal or padrao[2], ritmo or padrao[3]
    if not _TRAVA.acquire(blocking=False):
        return []
    mudaram = []
    try:
        try:
            prod = fabrica.producoes()
        except fabrica_api.SemFabrica:
            return []
        prontos = {p["nome"] for p in prod["prontos"]}
        andamento = {p["nome"]: p for p in prod["andamento"]}
        # 1. o que estava produzindo: ficou pronto, deu erro ou sumiu da fábrica
        for linha in banco.todos("SELECT * FROM producoes_fila WHERE estado='produzindo'"):
            p = andamento.get(linha["projeto"])
            if linha["projeto"] in prontos:
                mudou = mudar(linha["id"], "entregue", de=("produzindo",))
            elif p is None:
                mudou = mudar(linha["id"], "erro", de=("produzindo",), erro="O vídeo sumiu da fábrica.")
            elif p.get("status") == "erro":
                mudou = mudar(linha["id"], "erro", de=("produzindo",), erro=(p.get("mensagem") or "A fábrica parou com erro.")[:500])
            else:
                continue
            if mudou:
                mudaram.append(linha["id"])
        # 2. as vagas: o limite menos o que a fila mandou e os vídeos da fábrica feitos fora dela
        da_fila = {l["projeto"] for l in banco.todos("SELECT projeto FROM producoes_fila WHERE estado IN ('enviando', 'produzindo')")}
        fora = [n for n, p in andamento.items() if p.get("rodando") and n not in da_fila]
        vagas = limite() - len(da_fila) - len(fora)
        # 3. a fila, na ordem: primeiro o roteiro (não ocupa vaga, até ESCRITAS_AO_MESMO_TEMPO), depois o envio (ocupa)
        escrevendo = banco.um("SELECT COUNT(*) AS n FROM producoes_fila WHERE estado='escrevendo'")["n"]
        for linha in banco.todos("SELECT * FROM producoes_fila WHERE estado='na_fila' ORDER BY ordem"):
            if not linha["roteiro"]:
                if escrevendo >= ESCRITAS_AO_MESMO_TEMPO or not mudar(linha["id"], "escrevendo", de=("na_fila",), passo="Começando…"):
                    continue
                escrevendo += 1
                mudaram.append(linha["id"])
                if em_thread:
                    threading.Thread(target=_escrever, args=(linha, roteirista, config_canal, ritmo), daemon=True).start()
                    continue
                _escrever(linha, roteirista, config_canal, ritmo)
                escrevendo -= 1
                linha = banco.um("SELECT * FROM producoes_fila WHERE id=?", linha["id"])
                if linha["estado"] != "na_fila":
                    continue
            if vagas <= 0:
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
                    projeto = roteirista.enviar(linha["usuario_id"], linha["roteiro"], cfg.get("perfil", ""))["projeto"]
                    banco.executar("UPDATE producoes_fila SET projeto=? WHERE id=?", projeto, linha["id"])
                if not mudar(linha["id"], "enviando", de=("enviando",)):
                    continue
                fabrica.produzir(projeto, confirmar=True)
                if mudar(linha["id"], "produzindo", de=("enviando",), passo=""):
                    vagas -= 1
            except fabrica_api.SemFabrica:
                mudar(linha["id"], "na_fila", de=("enviando",), passo="")
                return mudaram
            except Exception as erro:  # noqa: BLE001
                mudar(linha["id"], "erro", de=("enviando",), erro=str(erro)[:500], passo="")
            mudaram.append(linha["id"])
        return mudaram
    finally:
        _TRAVA.release()


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

def estimativa(entregues: list[dict], canal: str, minutos: float) -> dict:
    """Minutos × a média de US$ por minuto dos vídeos entregues do canal (sem nenhum, a de todos)."""
    def por_minuto(lista):
        total = sum(e["minutos"] for e in lista)
        return sum(e["usd"] for e in lista) / total if total else None
    do_canal = por_minuto([e for e in entregues if e["canal"] == canal])
    if do_canal is not None:
        return {"usd": round(do_canal * minutos, 2), "base": "canal"}
    geral = por_minuto(entregues)
    return {"usd": round(geral * minutos, 2), "base": "geral"} if geral is not None else {"usd": None, "base": None}


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
        usd = sum(l["usd"] for l in custos.combinar(fabrica, custos.linhas(FABRICA / "projetos" / p["nome"])))
        if usd and p.get("duracao"):
            # "canal" aqui é o perfil da fábrica: é ele que a Nova produção conhece de cada canal
            lista.append({"canal": p.get("perfil") or "", "minutos": p["duracao"] / 60, "usd": usd})
    _ENTREGUES.update(t=time.time(), lista=lista)
    return lista
