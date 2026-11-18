"""O teste do canal novo (pedido do usuário em 2026-11-17).

Quando a pessoa adiciona um canal no Radar, ele oferece dois vídeos de teste para ver o canal de pé: temas do
espaço, de `fila.MINUTOS_SEM_NARRACAO` minutos, sem narração (só a música dá o clima) e sem thumbnail (o YouTube usa
os quadros automáticos dele). Nada é produzido nem postado sozinho: o cartão no perfil do canal pergunta a língua e
espera o clique.

Liberado o teste, os dois pedidos entram na fila como "entrada" e só começam quando a fila estiver parada (o Radar
não tira a vez de nenhum vídeo de verdade). Prontos, cada um é agendado pelo `publishAt` do próprio YouTube: o
primeiro no dia seguinte, o segundo no outro — o YouTube publica sozinho, com o computador desligado.

Para não fazer ninguém esperar a produção, o Radar vai deixando vídeos de teste prontos de antemão (pedido do
usuário em 2026-11-17): com a fila parada, ele produz um de cada vez até ter `ESTOQUE` guardados, sempre em
`LINGUA_PADRAO`. Liberado o teste de um canal nessa língua, os dois vídeos saem do estoque na hora; faltando
estoque, os que faltam são pedidos ali mesmo, como antes.

Para postar, o canal precisa ter sido conectado na fábrica (um login do Google por canal: o token fica preso ao
canal escolhido na tela de consentimento). Sem isso o envio falha e o erro fica guardado no cartão, para a pessoa
conectar e o Radar tentar de novo sozinho.
"""
import json
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


def oferecer(usuario_id: int, canal_id: str) -> None:
    """Chamada quando a pessoa adiciona um canal. Só abre o convite: quem decide é ela, no perfil."""
    banco.executar("INSERT OR IGNORE INTO canais_teste (usuario_id, canal_id, estado, criado) VALUES (?,?,?,?)",
                   usuario_id, canal_id, "pendente", banco.agora())


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
    prontos = len([l for l in _estoque(usuario_id) if l["estado"] == "entregue"])
    return {"canal_id": canal_id, "estado": linha["estado"], "lingua": linha["lingua"] or LINGUA_PADRAO,
            "lingua_padrao": LINGUA_PADRAO, "minutos": fila.MINUTOS_SEM_NARRACAO, "quantos": POR_CANAL,
            "linguas": list(fabrica_api.IDIOMA), "estoque": prontos, "videos": videos}


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
    if not banco.um("SELECT 1 FROM meus_canais WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id):
        raise ValueError("Esse canal não é seu.")
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


def _encher_estoque() -> list[int]:
    """Com a fila parada, prepara mais um vídeo de teste para o estoque. Um por volta, nunca em lote: o Radar nunca
    tira a vez de um vídeo de verdade nem enche a fila de teste de uma vez."""
    if not _fila_parada():
        return []
    for dono in banco.todos("SELECT DISTINCT usuario_id FROM meus_canais"):
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
    """O primeiro vídeo vai para amanhã; cada seguinte, um dia depois do último já agendado."""
    base = datetime.now().replace(hour=HORA_DO_POST, minute=0, second=0, microsecond=0)
    ultimo = base
    for p in pedidos:
        if p.get("agendado_para"):
            try:
                ultimo = max(ultimo, datetime.fromisoformat(p["agendado_para"]))
            except ValueError:
                continue
    return max(ultimo + timedelta(days=1), base + timedelta(days=1))


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
            quando = _proximo_dia(pedidos, k)
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
                                             quando=quando.strftime("%Y-%m-%dT%H:%M"), com_thumbnail=False,
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
    for passo in (_soltar_um_parado, _publicar_prontos, _encher_estoque):
        try:
            mudaram += passo()
        except Exception as erro:  # noqa: BLE001 (o vigia nunca pode parar)
            print("teste do canal:", erro)
    return mudaram
