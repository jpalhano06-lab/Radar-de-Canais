"""O teste do canal novo (pedido do usuário em 2026-11-17).

Quando a pessoa adiciona um canal no Radar, ele oferece dois vídeos de teste para ver o canal de pé: temas do
espaço, de `fila.MINUTOS_SEM_NARRACAO` minutos, sem narração (só a música dá o clima) e sem thumbnail (o YouTube usa
os quadros automáticos dele). Nada é produzido nem postado sozinho: o cartão no perfil do canal pergunta a língua e
espera o clique.

Liberado o teste, os dois pedidos entram na fila como "entrada" e só começam quando a fila estiver parada (o Radar
não tira a vez de nenhum vídeo de verdade). O primeiro pronto sobe na hora, que é o que mostra o canal de pé; o
segundo é agendado pelo `publishAt` do próprio YouTube para o dia seguinte, e sobe sozinho com o computador
desligado.

Ligar o canal na fábrica pelo login do Google já começa o teste dele sozinho, na língua padrão: entrar na conta e
escolher o canal é a permissão. Para outra língua, comece o teste na aba antes de ligar o canal.

Para não fazer ninguém esperar a produção, o Radar vai deixando vídeos de teste prontos de antemão (pedido do
usuário em 2026-11-17): com a fila parada, ele produz um de cada vez até ter `ESTOQUE` guardados, sempre em
`LINGUA_PADRAO`. Liberado o teste de um canal nessa língua, os dois vídeos saem do estoque na hora; faltando
estoque, os que faltam são pedidos ali mesmo, como antes.

Para postar, o canal precisa ter sido conectado na fábrica (um login do Google por canal: o token fica preso ao
canal escolhido na tela de consentimento). Sem isso o envio falha e o erro fica guardado no cartão, para a pessoa
conectar e o Radar tentar de novo sozinho.
"""
import json
import time
from datetime import datetime, timedelta

from . import banco, fabrica_api, fila

# Os temas são sementes em inglês: o roteiro é escrito na língua escolhida e o título que vai ao ar sai do kit de
# publicação da fábrica, já naquela língua. Vinte dão dez canais antes de qualquer repetição.
TEMAS = (
    "The Day the Sun Will Die",
    "What Falling Into a Black Hole Looks Like",
    "The Silence of the Voyager Probes",
    "Why Mars Lost Its Atmosphere",
    "The Storm on Jupiter That Never Ends",
    "What the James Webb Telescope Found in the Dark",
    "The Moon Is Drifting Away From Us",
    "Europa's Ocean Under the Ice",
    "The Star That Should Not Exist",
    "What Happens to a Body in Space",
    "The Rings of Saturn Are Disappearing",
    "The Edge of the Observable Universe",
    "Titan: The World With Rivers of Methane",
    "The Great Attractor Pulling Our Galaxy",
    "When Andromeda Collides With the Milky Way",
    "The Coldest Place in the Universe",
    "Why Venus Became a Furnace",
    "The Rogue Planets With No Sun",
    "What a Neutron Star Is Made Of",
    "The First Light After the Big Bang",
)
POR_CANAL = 2                 # sempre dois: um num dia, o outro no seguinte
ESTOQUE = len(TEMAS)          # quantos vídeos deixar prontos de antemão: os vinte temas, dez canais de teste
LINGUA_PADRAO = "inglês"      # sem narração, o inglês alcança mais gente sem custar nada a mais
HORA_DO_POST = 18             # na hora do canal (youtube.fuso_horas da fábrica, -3 para Brasília)
ESPERA_NOVA_TENTATIVA = 15 * 60   # segundos entre duas tentativas de envio depois de um erro
CACHE_CONECTADOS = 2 * 60         # segundos guardando a lista de canais ligados na fábrica
# a fila ocupada: enquanto houver um pedido em qualquer um destes estados, o teste espera
TRABALHANDO = ("na_fila", "escrevendo", "sua_vez", "enviando", "produzindo")
# o vídeo do estoque que não está mais a caminho: enquanto houver um a caminho, o estoque não pede outro
PARADOS = ("entregue", "erro", "pausado")


def _linha(usuario_id: int, canal_id: str) -> dict | None:
    return banco.um("SELECT * FROM canais_teste WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id)


def _pedidos(linha: dict) -> list[dict]:
    try:
        dados = json.loads(linha["pedidos"] or "[]")
    except ValueError:
        return []
    return dados if isinstance(dados, list) else []


def _gravar_pedidos(usuario_id: int, canal_id: str, pedidos: list[dict]) -> None:
    banco.executar("UPDATE canais_teste SET pedidos=? WHERE usuario_id=? AND canal_id=?",
                   json.dumps(pedidos, ensure_ascii=False), usuario_id, canal_id)


def oferecer(usuario_id: int, canal_id: str, nome: str = "") -> None:
    """Chamada quando a pessoa adiciona um canal. Só abre o convite: quem decide é ela, no perfil."""
    banco.executar("INSERT OR IGNORE INTO canais_teste (usuario_id, canal_id, estado, criado) VALUES (?,?,?,?)",
                   usuario_id, canal_id, "pendente", banco.agora())
    if nome:
        banco.executar("UPDATE canais_teste SET nome=? WHERE usuario_id=? AND canal_id=? AND nome=''",
                       nome, usuario_id, canal_id)


_CONECTADOS: tuple[float, list] = (0.0, [])      # quando perguntei e o que a fábrica respondeu


def conectados() -> list[dict]:
    """Os canais que já têm login do Google na fábrica, guardados por `CACHE_CONECTADOS` segundos.

    A fábrica produzindo leva segundos para responder e o vigia pergunta a toda volta, por isso a resposta fica
    guardada e o tempo de espera é curto: falhou, vale a de antes e tenta de novo depois. Fábrica desligada no
    primeiro pedido: lista vazia, não é erro de ninguém."""
    global _CONECTADOS
    agora = time.time()
    if agora - _CONECTADOS[0] < CACHE_CONECTADOS:
        return _CONECTADOS[1]
    try:
        lista = fabrica_api.youtube_contas(tempo=8).get("contas") or []
    except Exception:  # noqa: BLE001 (a fábrica desligada não pode derrubar a aba nem o vigia)
        return _CONECTADOS[1]
    _CONECTADOS = (agora, lista)
    return lista


def _e_dono(usuario_id: int, canal_id: str) -> bool:
    """Seu é o canal que está nos seus canais ou que você mesmo ligou na fábrica pelo login do Google."""
    if banco.um("SELECT 1 FROM meus_canais WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id):
        return True
    return any(c.get("canal_id") == canal_id for c in conectados())


def temas_novos(usuario_id: int, quantos: int = POR_CANAL) -> list[str]:
    """Temas que nenhum teste deste usuário usou ainda; esgotados, recomeça do começo da lista."""
    usados = set()
    for l in banco.todos("SELECT pedidos FROM canais_teste WHERE usuario_id=?", usuario_id):
        for p in _pedidos(l):
            usados.add(p.get("tema", ""))
    for l in banco.todos("SELECT tema FROM estoque_teste WHERE usuario_id=?", usuario_id):
        usados.add(l["tema"])
    livres = [t for t in TEMAS if t not in usados]
    if len(livres) < quantos:
        livres += [t for t in TEMAS if t in usados]
    return livres[:quantos]


def _pedido_de_teste(usuario_id: int, tema: str, lingua: str, comecar: bool) -> int:
    """Um pedido de vídeo de teste na fila: sem narração, do tamanho de `fila.MINUTOS_SEM_NARRACAO`."""
    from . import tempo
    agente = banco.um("SELECT id FROM projetos_roteiro WHERE usuario_id=? AND UPPER(nome)='CANAL DE TESTE'", usuario_id)
    perfil = fila.PERFIL_SEM_NARRACAO.get(lingua, fila.SEM_NARRACAO_OUTRAS)
    caracteres = fila.caracteres_de(fila.MINUTOS_SEM_NARRACAO, tempo.ritmo(usuario_id, perfil, lingua)["ppm"])
    # sem canal_id de propósito: a fila só aceita o sem narração fora de um canal (é o Canal de teste). O canal em
    # que publicar é o do teste, guardado na linha do canal
    criado = fila.criar(usuario_id, {"titulo": tema, "lingua": lingua, "caracteres": caracteres,
                                     "sem_narracao": True, "agente_id": agente["id"] if agente else None},
                        comecar=comecar)
    return criado["id"]


def _estoque(usuario_id: int) -> list[dict]:
    """O estoque vivo deste usuário: cada linha com o estado do pedido dela na fila. Some o que foi excluído lá."""
    vivos = []
    for l in banco.todos("SELECT * FROM estoque_teste WHERE usuario_id=? AND usado='' ORDER BY id", usuario_id):
        item = fila.item(usuario_id, l["fid"])
        if not item or item["estado"] == "cancelado":
            banco.executar("DELETE FROM estoque_teste WHERE id=?", l["id"])   # jogado fora na fila: sai do estoque
            continue
        vivos.append({**l, "estado": item["estado"]})
    return vivos


def do_canal(usuario_id: int, canal_id: str) -> dict | None:
    """O cartão do teste no perfil do canal: o estado, a língua e como vão os dois vídeos."""
    linha = _linha(usuario_id, canal_id)
    if not linha:
        return None
    videos = []
    for p in _pedidos(linha):
        item = fila.item(usuario_id, p["fid"]) if p.get("fid") else None
        videos.append({"tema": p.get("tema", ""), "fid": p.get("fid"),
                       "estado": item["estado"] if item else "excluído",
                       "projeto": (item or {}).get("projeto", ""),
                       "agendado_para": p.get("agendado_para", ""), "url": p.get("url", ""),
                       "enviado": bool(p.get("enviado")), "erro": p.get("erro", "")})
    return {"canal_id": canal_id, "nome": linha["nome"] or "", "estado": linha["estado"],
            "lingua": linha["lingua"] or LINGUA_PADRAO, "criado": linha["criado"],
            "lingua_padrao": LINGUA_PADRAO, "minutos": fila.MINUTOS_SEM_NARRACAO, "quantos": POR_CANAL,
            "linguas": list(fabrica_api.IDIOMA), "estoque": estoque_pronto(usuario_id), "videos": videos}


def estoque_pronto(usuario_id: int) -> int:
    """Quantos vídeos de teste já estão prontos, esperando um canal."""
    return len([l for l in _estoque(usuario_id) if l["estado"] == "entregue"])


def todos(usuario_id: int) -> list[dict]:
    """Todos os testes desta pessoa, o mais novo primeiro: é o que a aba Canal de teste mostra."""
    cartoes = [do_canal(usuario_id, l["canal_id"])
               for l in banco.todos("SELECT canal_id FROM canais_teste WHERE usuario_id=? AND estado<>'dispensado' "
                                    "ORDER BY criado DESC, rowid DESC", usuario_id)]
    return [c for c in cartoes if c]


def comecar(usuario_id: int, canal_id: str, lingua: str = "", nome: str = "") -> dict:
    """A aba Canal de teste: dito o @ e a língua, o teste já começa. Sem agente e sem mais nada para preencher."""
    oferecer(usuario_id, canal_id, nome)
    return liberar(usuario_id, canal_id, lingua)


def dispensar(usuario_id: int, canal_id: str) -> dict | None:
    banco.executar("UPDATE canais_teste SET estado='dispensado' WHERE usuario_id=? AND canal_id=? AND estado='pendente'",
                   usuario_id, canal_id)
    return do_canal(usuario_id, canal_id)


def liberar(usuario_id: int, canal_id: str, lingua: str = "") -> dict:
    """O sim da pessoa: cria os dois pedidos sem narração. Eles ficam em "entrada" e só começam com a fila parada."""
    linha = _linha(usuario_id, canal_id)
    if not linha:
        raise ValueError("Esse canal não tem teste para liberar.")
    if linha["estado"] == "liberado":
        raise ValueError("O teste deste canal já foi liberado.")
    if not _e_dono(usuario_id, canal_id):
        raise ValueError("Esse canal não é seu: conecte ele na fábrica pelo login do Google antes.")
    lingua = (lingua or LINGUA_PADRAO).strip()
    pedidos = []
    # o estoque primeiro: vídeo pronto nessa língua vai para este canal na hora, sem esperar produção nenhuma
    for guardado in [l for l in _estoque(usuario_id) if l["estado"] == "entregue" and l["lingua"] == lingua][:POR_CANAL]:
        banco.executar("UPDATE estoque_teste SET usado=? WHERE id=?", canal_id, guardado["id"])
        pedidos.append({"fid": guardado["fid"], "tema": guardado["tema"], "agendado_para": "", "url": "", "erro": ""})
    for tema in temas_novos(usuario_id, POR_CANAL - len(pedidos)):
        fid = _pedido_de_teste(usuario_id, tema, lingua, comecar=False)
        pedidos.append({"fid": fid, "tema": tema, "agendado_para": "", "url": "", "erro": ""})
    banco.executar("UPDATE canais_teste SET estado='liberado', lingua=?, pedidos=?, liberado=? "
                   "WHERE usuario_id=? AND canal_id=?",
                   lingua, json.dumps(pedidos, ensure_ascii=False), banco.agora(), usuario_id, canal_id)
    return do_canal(usuario_id, canal_id)


# ---------------------------------------------------------------- o que o vigia da fila faz a cada volta

def _fila_parada() -> bool:
    marcas = ",".join("?" * len(TRABALHANDO))
    return not banco.um(f"SELECT 1 AS n FROM producoes_fila WHERE estado IN ({marcas}) LIMIT 1", *TRABALHANDO)


def _soltar_um_parado() -> list[int]:
    """Com a fila parada, o teste mais antigo que ainda está em "entrada" começa. Um por volta."""
    if not _fila_parada():
        return []
    for linha in banco.todos("SELECT * FROM canais_teste WHERE estado='liberado' ORDER BY liberado"):
        for p in _pedidos(linha):
            item = fila.item(linha["usuario_id"], p["fid"]) if p.get("fid") else None
            if item and item["estado"] == "entrada":
                fila.comecar(linha["usuario_id"], p["fid"])
                return [p["fid"]]
    return []


def _ligar_conectados() -> list[int]:
    """Ligou o canal na fábrica pelo login do Google? O teste dele já começa (pedido do usuário em 2026-11-17).

    O login é a permissão: quem entrou na conta do Google e escolheu o canal já disse que é dele e que pode postar.
    A língua é a padrão; para outra, o teste é começado na aba antes de ligar o canal."""
    dono = banco.um("SELECT id FROM usuarios WHERE admin=1 ORDER BY id LIMIT 1")
    if not dono:
        return []
    mudaram = []
    for c in conectados():
        canal = c.get("canal_id") or ""
        linha = _linha(dono["id"], canal)
        # o convite ainda esperando resposta vira sim; já liberado, feito ou dispensado, ninguém mexe
        if not canal or (linha and linha["estado"] != "pendente"):
            continue
        mudaram += [v["fid"] for v in comecar(dono["id"], canal, LINGUA_PADRAO, c.get("canal_nome") or "")["videos"]]
    return mudaram


def _encher_estoque() -> list[int]:
    """Com a fila parada, prepara mais um vídeo de teste para o estoque. Um por volta, nunca em lote: o Radar nunca
    tira a vez de um vídeo de verdade nem enche a fila de teste de uma vez."""
    if not _fila_parada():
        return []
    for dono in banco.todos("SELECT usuario_id FROM meus_canais UNION SELECT usuario_id FROM canais_teste"):
        usuario_id = dono["usuario_id"]
        guardados = _estoque(usuario_id)
        if len(guardados) >= ESTOQUE:
            continue
        if any(l["estado"] not in PARADOS for l in guardados):
            continue                       # o anterior ainda está sendo feito: espera ele
        temas = temas_novos(usuario_id, 1)
        if not temas:
            continue
        fid = _pedido_de_teste(usuario_id, temas[0], LINGUA_PADRAO, comecar=True)
        banco.executar("INSERT INTO estoque_teste (usuario_id, tema, lingua, fid, criado) VALUES (?,?,?,?,?)",
                       usuario_id, temas[0], LINGUA_PADRAO, fid, banco.agora())
        return [fid]
    return []


def _proximo_dia(pedidos: list[dict], k: int) -> datetime:
    """Um dia depois do último que já tem hora marcada, sempre às `HORA_DO_POST`."""
    base = datetime.now().replace(hour=HORA_DO_POST, minute=0, second=0, microsecond=0)
    ultimo = base
    for p in pedidos:
        if p.get("agendado_para"):
            try:
                ultimo = max(ultimo, datetime.fromisoformat(p["agendado_para"]))
            except ValueError:
                continue
    seguinte = max(ultimo + timedelta(days=1), base + timedelta(days=1))
    return seguinte.replace(hour=HORA_DO_POST, minute=0, second=0, microsecond=0)


def _publicar_prontos() -> list[int]:
    """Cada vídeo de teste entregue é agendado no canal do teste, um dia depois do outro."""
    mudaram = []
    agora = datetime.now().timestamp()
    for linha in banco.todos("SELECT * FROM canais_teste WHERE estado='liberado'"):
        pedidos, mexeu = _pedidos(linha), False
        for k, p in enumerate(pedidos):
            if p.get("url") or not p.get("fid"):
                continue
            item = fila.item(linha["usuario_id"], p["fid"])
            if not item or not item.get("projeto"):
                continue
            if p.get("enviado"):
                # já mandado: o link aparece quando a fábrica termina o envio e grava o youtube.json
                publicado = fabrica_api.youtube_do_projeto(item["projeto"])
                if publicado and publicado.get("url"):
                    p["url"] = publicado["url"]
                    mexeu = True
                    mudaram.append(p["fid"])
                continue
            if item["estado"] != "entregue":
                continue
            if p.get("erro") and agora - float(p.get("tentado") or 0) < ESPERA_NOVA_TENTATIVA:
                continue
            # o primeiro do canal sobe na hora (pedido do usuário em 2026-11-17): é ele que mostra o canal de pé.
            # O seguinte é agendado para o dia de depois, pelo publishAt do próprio YouTube
            marcar = any(p2.get("agendado_para") for p2 in pedidos)
            quando = _proximo_dia(pedidos, k) if marcar else datetime.now()
            p["tentado"] = agora
            from . import agendar          # import tardio: o agendar usa a fila, como este módulo
            kit = agendar.kit_do_video(linha["usuario_id"], item)
            if not kit.get("descricao"):
                # nenhum vídeo sobe pelado: a descrição se escreve na próxima volta (pedido de 2026-11-17)
                p["erro"] = agendar.SEM_DESCRICAO
                mexeu = True
                mudaram.append(p["fid"])
                continue
            try:
                # sem thumbnail de propósito: o vídeo de teste sobe com os quadros automáticos do YouTube
                fabrica_api.youtube_publicar(item["projeto"], canal=linha["canal_id"],
                                             quando=quando.strftime("%Y-%m-%dT%H:%M") if marcar else "",
                                             com_thumbnail=False,
                                             titulo=kit.get("titulo", ""), descricao=kit["descricao"],
                                             tags=kit.get("tags") or [])
                p |= {"agendado_para": quando.isoformat(timespec="minutes"), "erro": "", "enviado": True}
            except fabrica_api.SemFabrica as erro:
                p["erro"] = str(erro)
            mexeu = True
            mudaram.append(p["fid"])
        if mexeu:
            _gravar_pedidos(linha["usuario_id"], linha["canal_id"], pedidos)
        if pedidos and all(p.get("agendado_para") for p in pedidos):
            banco.executar("UPDATE canais_teste SET estado='feito' WHERE usuario_id=? AND canal_id=?",
                           linha["usuario_id"], linha["canal_id"])
    return mudaram


def andar() -> list[int]:
    """Uma volta do teste dos canais, chamada pelo vigia da fila. Nunca levanta: a fila não pode parar por isto."""
    mudaram = []
    for passo in (_ligar_conectados, _soltar_um_parado, _publicar_prontos, _encher_estoque):
        try:
            mudaram += passo()
        except Exception as erro:  # noqa: BLE001 (o vigia nunca pode parar)
            print("teste do canal:", erro)
    return mudaram
