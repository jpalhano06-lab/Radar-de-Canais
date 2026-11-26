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

A área Canal de teste (pedido do usuário em 2026-11-25): agora são três vídeos por canal, um a cada
`INTERVALO_DIAS` dias, todos na mesma hora (`HORA_DO_POST`) para todo canal. Os vídeos saem de dois lugares: o
banco de vídeos (vídeos de verdade que a pessoa sobe, como o do cachorro) ou a criação em massa do Radar, que vai
deixando prontos vídeos baratos (sem narração, só música) sobre os assuntos que a pessoa ligou. Um vídeo de teste
que passa de `LIMITE_ALERTA` impressões acende o alerta de canal novo bom, em todas as telas.
"""
import json
import shutil
import time
from datetime import datetime, timedelta

from . import banco, fabrica_api, fila
from .config import DADOS

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
# Os assuntos da criação em massa (2026-11-25): cada um traz títulos prontos, para o vídeo sair sem gastar nada com
# IA para inventar o tema. O espaço é o de sempre; os outros são do mesmo jeito barato (sem narração, só música).
ASSUNTOS = {
    "espaco": {"nome": "Espaço", "temas": TEMAS},
    "oceano": {"nome": "Oceano profundo", "temas": (
        "What Lives at the Bottom of the Mariana Trench", "The Giant Squid Nobody Has Seen Alive",
        "Why the Deep Ocean Glows in the Dark", "The Underwater Lakes That Kill Everything",
        "The Loudest Sound Ever Recorded in the Ocean", "Creatures That Survive Without Sunlight",
        "The Shipwrecks Still Hidden in the Deep", "Why We Know More About Mars Than the Ocean Floor",
        "The Whale Fall: A Feast at the Bottom of the Sea", "The Blue Hole That Swallows Divers")},
    "dinossauros": {"nome": "Dinossauros", "temas": (
        "The Last Day of the Dinosaurs", "The Biggest Dinosaur That Ever Walked",
        "How Birds Survived the Asteroid", "The Dinosaur With the Strongest Bite",
        "What the Earth Looked Like Under the Dinosaurs", "The Sea Monsters of the Jurassic",
        "Why Dinosaurs Grew So Big", "The Fossil That Changed Everything",
        "The Flying Reptiles Bigger Than Planes", "Could Dinosaurs Have Survived Until Today")},
    "civilizacoes": {"nome": "Civilizações antigas", "temas": (
        "The Lost City Under the Desert Sand", "How the Pyramids Were Really Built",
        "The Library That Burned and Took History With It", "The Empire That Vanished Overnight",
        "The Roads of Rome That Still Exist", "The Mystery of the Indus Valley Script",
        "Why Angkor Wat Was Abandoned", "The Bronze Age Collapse", "The City Carved Into a Mountain",
        "The Oldest Temple on Earth")},
    "natureza": {"nome": "Natureza e animais", "temas": (
        "The Longest Migration on the Planet", "How Octopuses Think", "The Forest That Talks Underground",
        "The Animal That Never Dies", "The Coldest Place Life Survives", "How Elephants Mourn Their Dead",
        "The Desert That Blooms Once a Decade", "The Birds That Never Land",
        "Why Bees Are Disappearing", "The Island Where Evolution Went Wild")},
    "misterios": {"nome": "Mistérios da Terra", "temas": (
        "The Lake That Turns Animals to Stone", "The Door to Hell Burning for Fifty Years",
        "The Sailing Stones of Death Valley", "The Hum Nobody Can Explain",
        "The Island No One Is Allowed to Visit", "The Waterfall That Disappears Into Nowhere",
        "The Forest Where Trees Grow Crooked", "The Lights That Appear Over the Same Valley",
        "The Hole at the Top of the World", "The Glacier That Bleeds Red")},
}
ASSUNTOS_PADRAO = ("espaco",)
POR_CANAL = 3                 # três vídeos por canal novo (2026-11-25), um a cada INTERVALO_DIAS
INTERVALO_DIAS = 3            # dias entre um vídeo de teste e o seguinte no mesmo canal
ESTOQUE = len(TEMAS)          # quantos vídeos deixar prontos de antemão, quando a pessoa não disse outro número
ESTOQUE_MAXIMO = 60           # o teto que a tela aceita: a fila é uma só e o teste nunca pode tomar ela
LINGUA_PADRAO = "inglês"      # sem narração, o inglês alcança mais gente sem custar nada a mais
HORA_DO_POST = 18             # a mesma para todo canal, na hora do canal (youtube.fuso_horas, -3 para Brasília)
LIMITE_ALERTA = 1000          # impressões de um vídeo de teste que dizem que o canal novo é bom
MEDIR_A_CADA = 60 * 60        # segundos entre duas leituras das impressões e views de um vídeo de teste
PASTA_BANCO = DADOS / "banco_teste"
TAMANHO_MAXIMO = 2 * 1024 ** 3    # 2 GB por vídeo do banco
PREFIXO_BANCO = "teste-banco-"    # a pasta na fábrica de um vídeo do banco (fica fora das produções)
# Quem posta o vídeo de teste (pedido do usuário em 2026-11-25): a extensão, pelo YouTube Studio, como o "postar
# sozinho" do Meu dia, que preenche título, descrição e tags. Pela API da fábrica o vídeo subia só com título.
POSTAR_PELA_EXTENSAO = True
# 2026-11-25, depois: o Radar não posta mais nos canais de teste. Cada vídeo do teste vira um dia marcado (às
# HORA_DO_POST, um a cada INTERVALO_DIAS) e a pessoa posta; o Radar só confere no canal se saiu vídeo e pinta o dia
# de verde (postado) ou vermelho (chegou o dia e não saiu) na aba Canais de teste do YouTube.
O_RADAR_POSTA = False
CONFERIR_A_CADA = 30 * 60         # segundos entre duas conferências do canal pelo vigia (2 de cota cada)
CONFERIR_NA_ABA = 5 * 60          # a aba aberta confere de novo depois disto, para o verde sair logo
FOLGA_DO_STUDIO = 20 * 60         # segundos antes da hora: sem postar até aí, o vídeo vai para a próxima vaga
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


def _chave(p: dict) -> str:
    """O nome de um vídeo de teste dentro do canal: o pedido da fila, ou o vídeo do banco."""
    return f"banco-{p['banco_id']}" if p.get("banco_id") else str(p.get("fid") or "")


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
    """Temas que nenhum teste deste usuário usou ainda e que não têm pedido de mesmo título na fila.
    Esgotados, não recomeça: recomeçar fez "The Day the Sun Will Die" sair 13 vezes (2026-11-18), e pedido de título
    repetido só entra com a confirmação de uma pessoa (pedido de 2026-11-24)."""
    usados = set()
    for l in banco.todos("SELECT pedidos FROM canais_teste WHERE usuario_id=?", usuario_id):
        for p in _pedidos(l):
            usados.add(p.get("tema", ""))
    for l in banco.todos("SELECT tema FROM estoque_teste WHERE usuario_id=?", usuario_id):
        usados.add(l["tema"])
    livres = [t for t in temas_disponiveis(usuario_id) if t not in usados and not fila.pedido_igual(usuario_id, t)]
    return livres[:quantos]


# ---------------------------------------------------------------- a criação em massa (2026-11-25)

def ajustes(usuario_id: int) -> dict:
    """Os assuntos ligados, os títulos da própria pessoa, quantos deixar prontos, a língua e se está ligada."""
    linha = banco.um("SELECT dados FROM teste_ajustes WHERE usuario_id=?", usuario_id)
    try:
        dados = json.loads(linha["dados"]) if linha else {}
    except ValueError:
        dados = {}
    assuntos = [a for a in (dados.get("assuntos") or ASSUNTOS_PADRAO) if a in ASSUNTOS]
    proprios = [str(t).strip()[:100] for t in (dados.get("proprios") or []) if str(t).strip()]
    try:
        meta = max(0, min(ESTOQUE_MAXIMO, int(dados.get("meta", ESTOQUE))))
    except (TypeError, ValueError):
        meta = ESTOQUE
    lingua = dados.get("lingua") if dados.get("lingua") in fabrica_api.IDIOMA else LINGUA_PADRAO
    return {"assuntos": assuntos, "proprios": proprios, "meta": meta, "lingua": lingua,
            "ligado": bool(dados.get("ligado", True)),
            # os canais de teste com o postar sozinho ligado (2026-11-25): a extensão publica no dia e na hora
            "sozinho": [str(c) for c in (dados.get("sozinho") or []) if str(c).startswith("UC")]}


def salvar_ajustes(usuario_id: int, novos: dict) -> dict:
    atual = ajustes(usuario_id)
    for chave in ("assuntos", "proprios", "meta", "lingua", "ligado", "sozinho"):
        if chave in novos:
            atual[chave] = novos[chave]
    if isinstance(atual["proprios"], str):
        atual["proprios"] = atual["proprios"].splitlines()
    banco.executar("INSERT OR REPLACE INTO teste_ajustes (usuario_id, dados) VALUES (?,?)",
                   usuario_id, json.dumps(atual, ensure_ascii=False))
    return ajustes(usuario_id)


def temas_disponiveis(usuario_id: int) -> list[str]:
    """Os títulos que a criação em massa pode usar: os da própria pessoa primeiro, depois os dos assuntos ligados."""
    a = ajustes(usuario_id)
    todos_ = list(a["proprios"]) + [t for chave in a["assuntos"] for t in ASSUNTOS[chave]["temas"]]
    return list(dict.fromkeys(todos_))


def massa(usuario_id: int) -> dict:
    """A aba Criar em massa: os ajustes, os assuntos para escolher e como vai o estoque."""
    guardados = _estoque(usuario_id)
    livres = temas_novos(usuario_id, 10_000)
    return {"ajustes": ajustes(usuario_id), "linguas": list(fabrica_api.IDIOMA), "maximo": ESTOQUE_MAXIMO,
            "assuntos": [{"chave": k, "nome": v["nome"], "quantos": len(v["temas"]), "exemplo": v["temas"][0]}
                         for k, v in ASSUNTOS.items()],
            "prontos": len([l for l in guardados if l["estado"] == "entregue"]),
            "fazendo": len([l for l in guardados if l["estado"] not in PARADOS]),
            "com_erro": len([l for l in guardados if l["estado"] == "erro"]),
            "temas_livres": len(livres), "minutos": fila.MINUTOS_SEM_NARRACAO,
            "estoque": [{"tema": l["tema"], "lingua": l["lingua"], "estado": l["estado"], "fid": l["fid"]}
                        for l in guardados]}


# ---------------------------------------------------------------- o banco de vídeos (2026-11-25)

def _do_banco(usuario_id: int, banco_id: int) -> dict | None:
    return banco.um("SELECT * FROM banco_teste WHERE id=? AND usuario_id=?", banco_id, usuario_id)


def arquivo_do_banco(usuario_id: int, banco_id: int):
    linha = _do_banco(usuario_id, banco_id)
    if not linha:
        return None
    caminho = PASTA_BANCO / linha["arquivo"]
    return caminho if caminho.exists() else None


def banco_de_videos(usuario_id: int) -> list[dict]:
    """Os vídeos que a pessoa subiu, com os canais em que cada um já foi."""
    usos: dict[int, list[str]] = {}
    for l in banco.todos("SELECT nome, canal_id, pedidos FROM canais_teste WHERE usuario_id=?", usuario_id):
        for p in _pedidos(l):
            if p.get("banco_id"):
                usos.setdefault(p["banco_id"], []).append(l["nome"] or l["canal_id"])
    saida = []
    for v in banco.todos("SELECT * FROM banco_teste WHERE usuario_id=? ORDER BY id DESC", usuario_id):
        saida.append({"id": v["id"], "titulo": v["titulo"], "descricao": v["descricao"], "tamanho": v["tamanho"],
                      "criado": v["criado"], "canais": usos.get(v["id"], []),
                      "existe": (PASTA_BANCO / v["arquivo"]).exists()})
    return saida


def arquivo_temporario(usuario_id: int):
    """Onde o vídeo que está chegando é escrito, aos pedaços, antes de entrar no banco."""
    PASTA_BANCO.mkdir(parents=True, exist_ok=True)
    return PASTA_BANCO / f"subindo-{usuario_id}-{time.time_ns()}.part"


def guardar_no_banco(usuario_id: int, titulo: str, descricao: str, temporario) -> dict:
    """Guarda no banco o vídeo que a pessoa subiu (já escrito em `temporario`, que é levado para o lugar dele)."""
    titulo = " ".join(str(titulo or "").split())[:100]
    if not titulo:
        raise ValueError("Dê um título ao vídeo: é o título com que ele vai ao ar.")
    tamanho = temporario.stat().st_size if temporario.exists() else 0
    if tamanho < 1024:
        raise ValueError("O arquivo chegou vazio. Escolha o vídeo de novo.")
    banco_id = banco.executar("INSERT INTO banco_teste (usuario_id, titulo, descricao, arquivo, tamanho, criado) "
                              "VALUES (?,?,?,?,?,?)", usuario_id, titulo, str(descricao or "")[:4900], "",
                              tamanho, banco.agora())
    nome = f"{banco_id}.mp4"
    temporario.replace(PASTA_BANCO / nome)
    banco.executar("UPDATE banco_teste SET arquivo=? WHERE id=?", nome, banco_id)
    return {"id": banco_id, "titulo": titulo, "tamanho": tamanho}


def mudar_no_banco(usuario_id: int, banco_id: int, titulo: str, descricao: str) -> None:
    titulo = " ".join(str(titulo or "").split())[:100]
    if not titulo:
        raise ValueError("O título não pode ficar vazio.")
    if not _do_banco(usuario_id, banco_id):
        raise ValueError("Esse vídeo não está no seu banco.")
    banco.executar("UPDATE banco_teste SET titulo=?, descricao=? WHERE id=?", titulo, str(descricao or "")[:4900],
                   banco_id)


def apagar_do_banco(usuario_id: int, banco_id: int) -> None:
    """Tira o vídeo do banco. O que já foi para um canal continua lá: a fábrica tem a cópia dela."""
    linha = _do_banco(usuario_id, banco_id)
    if not linha:
        raise ValueError("Esse vídeo não está no seu banco.")
    if linha["arquivo"]:
        (PASTA_BANCO / linha["arquivo"]).unlink(missing_ok=True)
    banco.executar("DELETE FROM banco_teste WHERE id=?", banco_id)


def _do_banco_para(usuario_id: int, canal_id: str, quantos: int) -> list[dict]:
    """Os vídeos do banco que ainda não foram para canal nenhum, os mais antigos primeiro. Cada vídeo do banco vai
    para um canal de teste só: vídeo de teste nunca se repete (pedido do usuário em 2026-11-25)."""
    if quantos <= 0:
        return []
    lista = [v for v in banco_de_videos(usuario_id) if v["existe"] and not v["canais"]]
    lista.sort(key=lambda v: v["id"])
    return lista[:quantos]


def _projeto_do_banco(linha: dict, p: dict) -> str:
    """A pasta na fábrica do vídeo do banco para este canal, criada na primeira vez.

    A extensão posta pela pasta de um projeto (o final.mp4 e o kit do Radar, publicacao_radar.json): cada vídeo do
    banco ganha uma por canal, com o nome começando em PREFIXO_BANCO, que fica fora das produções. É cópia, não link:
    a pasta da fábrica pode ser limpa depois de postar, e o original do banco não pode sumir junto."""
    nome = f"{PREFIXO_BANCO}{p['banco_id']}-{linha['canal_id'][-8:].lower()}"
    pasta = fabrica_api._pasta(nome)
    if (pasta / "final.mp4").exists():
        return nome
    origem = arquivo_do_banco(linha["usuario_id"], p["banco_id"])
    if not origem:
        raise ValueError("O vídeo saiu do banco antes de ir para o canal.")
    perfis = fabrica_api.roteiro_claude.FABRICA / "perfis"
    perfil = next((perfis / f for f in ("documentario.yaml", "base-documentario.yaml") if (perfis / f).exists()), None)
    if not perfil:
        raise ValueError("Não achei a pasta da fábrica para preparar o vídeo do banco.")
    pasta.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origem, pasta / "final.mp4.part")
    (pasta / "final.mp4.part").replace(pasta / "final.mp4")
    (pasta / "projeto.json").write_text(json.dumps({
        "nome": nome, "perfil": str(perfil), "offline": True, "criado": datetime.now().isoformat(timespec="seconds"),
        "titulo_entrega": p.get("tema", ""), "teste_banco": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    (pasta / "publicacao.json").write_text(json.dumps({
        "titulo": p.get("tema", ""), "descricao": p.get("descricao", ""), "tags": []}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return nome


def _kit_so_titulo(projeto: str, p: dict) -> dict:
    """O kit do vídeo de teste: só o título (pedido do usuário em 2026-11-25: "não precisa de descrição nem tags").
    `so_titulo` faz o Studio deixar a descrição e as tags vazias, sem cair no texto da fábrica. O vídeo do banco é de
    verdade (`real`): no Studio, "Uso de IA" fica Não."""
    pasta = fabrica_api._pasta(projeto)
    # o título traduzido na língua do teste (o "Wat Leeft Op de Bodem…" do canal holandês), não a semente em inglês
    titulo = p.get("tema", "")
    if not p.get("banco_id"):
        for nome in ("publicacao_radar.json", "publicacao.json"):
            try:
                achado = str(json.loads((pasta / nome).read_text(encoding="utf-8")).get("titulo") or "").strip()
            except (OSError, ValueError):
                achado = ""
            if achado:
                titulo = achado
                break
    kit = {"titulo": titulo[:100], "descricao": "", "sinopse": "", "tags": [], "hashtags": [], "so_titulo": True,
           "sintetico": not p.get("banco_id"), "real": bool(p.get("banco_id")), "origem": "radar",
           "criado": banco.agora()}
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "publicacao_radar.json").write_text(json.dumps(kit, ensure_ascii=False, indent=1), encoding="utf-8")
    return kit


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
        if p.get("banco_id"):
            estado = "entregue" if _do_banco(usuario_id, p["banco_id"]) or p.get("enviado") else "excluído"
            item = None
        else:
            item = fila.item(usuario_id, p["fid"]) if p.get("fid") else None
            estado = item["estado"] if item else "excluído"
        videos.append({"tema": p.get("tema", ""), "fid": p.get("fid"), "chave": _chave(p),
                       "origem": "banco" if p.get("banco_id") else "radar",
                       "estado": estado, "projeto": (item or {}).get("projeto", ""),
                       "agendado_para": p.get("agendado_para", ""), "url": p.get("url", ""),
                       "video_id": p.get("video_id", ""),
                       "enviado": bool(p.get("enviado") or p.get("postado")), "erro": p.get("erro", ""),
                       "manual": bool(p.get("manual")), "postado": bool(p.get("postado")),
                       "impressoes": p.get("impressoes"), "views": p.get("views"),
                       "sem_studio": bool(p.get("sem_studio")), "alerta": bool(p.get("alerta_em"))})
    avaliacao = linha.get("avaliacao") or ""
    return {"canal_id": canal_id, "nome": linha["nome"] or "", "estado": linha["estado"],
            "intervalo": INTERVALO_DIAS, "hora": HORA_DO_POST, "limite": LIMITE_ALERTA,
            "bom": avaliacao == "bom" or (avaliacao != "ruim" and any(v["alerta"] for v in videos)),
            "avaliacao": avaliacao, "avaliado": linha.get("avaliado") or "",
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


def privados(usuario_id: int) -> list[dict]:
    """Os vídeos de teste já mandados, um grupo por canal, cada um com a sua cor (2026-11-18).

    Enquanto o projeto do Google não passar pela auditoria da YouTube API Services, todo vídeo que a API sobe fica
    travado em privado, mesmo pedindo público. Quem tira do privado é a pessoa, no Studio do canal — e com vários
    canais isso se perde. Aqui cada canal tem a sua aba, e cada vídeo a cor do que falta fazer nele."""
    agora = datetime.now()
    canais = []
    for linha in banco.todos("SELECT * FROM canais_teste WHERE usuario_id=? AND estado IN ('liberado','feito') "
                             "ORDER BY criado, rowid", usuario_id):
        videos = []
        for p in _pedidos(linha):
            if not p.get("enviado"):
                continue
            url, quando = p.get("url", ""), p.get("agendado_para", "")
            # os primeiros subiram antes de o id ser guardado: ele é o fim do próprio link
            video_id = p.get("video_id") or (url.rstrip("/").rsplit("/", 1)[-1] if url else "")
            videos.append({"tema": p.get("tema", ""), "fid": p.get("fid"), "chave": _chave(p),
                           "url": url or (f"https://youtu.be/{video_id}" if video_id else ""),
                           "video_id": video_id, "agendado_para": quando,
                           "estado": _cor(p, quando, agora)})
        if videos:
            canais.append({"canal_id": linha["canal_id"], "canal": linha["nome"] or linha["canal_id"],
                           "videos": videos, "postar": len([v for v in videos if v["estado"] == "postar"])})
    return canais


def _cor(pedido: dict, quando: str, agora: datetime) -> str:
    """Verde: a pessoa já pôs no ar. Azul: esperando o dia dele. Vermelho: a hora chegou e ainda está privado."""
    if pedido.get("conferido"):
        return "publico"
    try:
        return "espera" if quando and datetime.fromisoformat(quando) > agora else "postar"
    except ValueError:
        return "postar"


def conferir(usuario_id: int, canal_id: str, fid) -> list[dict]:
    """A pessoa diz que já olhou aquele vídeo no canal: ele sai da lista de lembretes. `fid` é o número do pedido
    na fila ou a chave do vídeo (`_chave`), que é como o do banco de vídeos é chamado."""
    linha = _linha(usuario_id, canal_id)
    if not linha:
        raise ValueError("Esse canal não tem teste.")
    pedidos = _pedidos(linha)
    for p in pedidos:
        if p.get("fid") == fid or _chave(p) == str(fid):
            p["conferido"] = True
    _gravar_pedidos(usuario_id, canal_id, pedidos)
    return privados(usuario_id)


def comecar(usuario_id: int, canal_id: str, lingua: str = "", nome: str = "", origem: str = "") -> dict:
    """A aba Canal de teste: dito o @ e a língua, o teste já começa. Sem agente e sem mais nada para preencher."""
    oferecer(usuario_id, canal_id, nome)
    return liberar(usuario_id, canal_id, lingua, origem)


def dispensar(usuario_id: int, canal_id: str) -> dict | None:
    """Não testar este canal (pedido do usuário em 2026-11-25): vale para o convite e para o teste já andando. O que
    já foi ao ar fica no canal; o resto não é postado (sai do Meu dia da extensão) e o pedido que nem começou na fila
    é cancelado. O canal ligado na fábrica não volta a testar sozinho: só com "Testar de novo" (`voltar`)."""
    linha = _linha(usuario_id, canal_id)
    if not linha:
        raise ValueError("Esse canal não tem teste.")
    banco.executar("UPDATE canais_teste SET estado='dispensado' WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id)
    for p in _pedidos(linha):
        if p.get("fid") and not _fixo(p):
            fila.mudar(p["fid"], "cancelado", de=("entrada",))
    return do_canal(usuario_id, canal_id)


def voltar(usuario_id: int, canal_id: str) -> dict | None:
    """Testar de novo o canal que a pessoa tinha tirado do teste: os vídeos que faltam voltam a andar."""
    linha = _linha(usuario_id, canal_id)
    if not linha or linha["estado"] != "dispensado":
        raise ValueError("Esse canal não está fora do teste.")
    pedidos = _pedidos(linha)
    estado = "pendente" if not pedidos else "feito" if all(_fixo(p) for p in pedidos) else "liberado"
    banco.executar("UPDATE canais_teste SET estado=? WHERE usuario_id=? AND canal_id=?", estado, usuario_id, canal_id)
    for p in pedidos:
        item = fila.item(usuario_id, p["fid"]) if p.get("fid") and not _fixo(p) else None
        if item and item["estado"] == "cancelado":
            fila.mudar(p["fid"], "entrada", de=("cancelado",))
    return do_canal(usuario_id, canal_id)


def sem_teste(usuario_id: int) -> list[dict]:
    """Os canais que a pessoa tirou do teste, para poder testar de novo."""
    return [{"canal_id": l["canal_id"], "nome": l["nome"] or l["canal_id"]}
            for l in banco.todos("SELECT canal_id, nome FROM canais_teste WHERE usuario_id=? AND estado='dispensado' "
                                 "ORDER BY rowid DESC", usuario_id)]


def liberar(usuario_id: int, canal_id: str, lingua: str = "", origem: str = "") -> dict:
    """O sim da pessoa: separa os três vídeos do canal. Com `origem` "banco", os do banco de vídeos vão primeiro (os
    que ainda não foram para canal nenhum); o que faltar sai do estoque do Radar e, sem estoque, vira pedido
    sem narração na fila, em "entrada", que só começa com a fila parada. "radar" pula o banco."""
    linha = _linha(usuario_id, canal_id)
    if not linha:
        raise ValueError("Esse canal não tem teste para liberar.")
    if linha["estado"] == "liberado":
        raise ValueError("O teste deste canal já foi liberado.")
    # postando pela extensão, quem diz que o canal é seu é a conta do Google aberta no Chrome: o Radar não precisa do
    # login do Google dele (pedido do usuário em 2026-11-25)
    if not POSTAR_PELA_EXTENSAO and not _e_dono(usuario_id, canal_id):
        raise ValueError("Esse canal não é seu: conecte ele na fábrica pelo login do Google antes.")
    lingua = (lingua or LINGUA_PADRAO).strip()
    pedidos = []
    if origem == "banco":
        for v in _do_banco_para(usuario_id, canal_id, POR_CANAL):
            pedidos.append({"banco_id": v["id"], "tema": v["titulo"], "descricao": v["descricao"],
                            "agendado_para": "", "url": "", "erro": ""})
    # o estoque primeiro: vídeo pronto nessa língua vai para este canal na hora, sem esperar produção nenhuma
    for guardado in [l for l in _estoque(usuario_id) if l["estado"] == "entregue" and l["lingua"] == lingua][:POR_CANAL - len(pedidos)]:
        banco.executar("UPDATE estoque_teste SET usado=? WHERE id=?", canal_id, guardado["id"])
        pedidos.append({"fid": guardado["fid"], "tema": guardado["tema"], "agendado_para": "", "url": "", "erro": ""})
    for tema in temas_novos(usuario_id, POR_CANAL - len(pedidos)):
        fid = _pedido_de_teste(usuario_id, tema, lingua, comecar=False)
        pedidos.append({"fid": fid, "tema": tema, "agendado_para": "", "url": "", "erro": ""})
    banco.executar("UPDATE canais_teste SET estado='liberado', lingua=?, pedidos=?, liberado=? "
                   "WHERE usuario_id=? AND canal_id=?",
                   lingua, json.dumps(pedidos, ensure_ascii=False), banco.agora(), usuario_id, canal_id)
    return do_canal(usuario_id, canal_id)


def completar(usuario_id: int) -> list[str]:
    """Os testes de antes de 2026-11-25 tinham dois vídeos: aqui cada um ganha os que faltam até `POR_CANAL`
    (pedido do usuário em 2026-11-25). Primeiro o estoque pronto na língua do teste, depois um título livre dos
    assuntos ligados e, esgotados, um de qualquer assunto. O vídeo novo entra `INTERVALO_DIAS` depois do último."""
    mudados = []
    for linha in banco.todos("SELECT * FROM canais_teste WHERE usuario_id=? AND estado IN ('liberado','feito')",
                             usuario_id):
        pedidos = _pedidos(linha)
        faltam = POR_CANAL - len(pedidos)
        if faltam <= 0:
            continue
        lingua = linha["lingua"] or LINGUA_PADRAO
        for guardado in [l for l in _estoque(usuario_id) if l["estado"] == "entregue" and l["lingua"] == lingua][:faltam]:
            banco.executar("UPDATE estoque_teste SET usado=? WHERE id=?", linha["canal_id"], guardado["id"])
            pedidos.append({"fid": guardado["fid"], "tema": guardado["tema"], "agendado_para": "", "url": "", "erro": ""})
        temas = temas_novos(usuario_id, POR_CANAL - len(pedidos))
        if len(temas) < POR_CANAL - len(pedidos):
            usados = {p.get("tema") for l in banco.todos("SELECT pedidos FROM canais_teste WHERE usuario_id=?",
                                                         usuario_id) for p in _pedidos(l)}
            usados |= {l["tema"] for l in banco.todos("SELECT tema FROM estoque_teste WHERE usuario_id=?", usuario_id)}
            reserva = [t for a in ASSUNTOS.values() for t in a["temas"]
                       if t not in usados and t not in temas and not fila.pedido_igual(usuario_id, t)]
            temas += reserva[:POR_CANAL - len(pedidos) - len(temas)]
        for tema in temas:
            fid = _pedido_de_teste(usuario_id, tema, lingua, comecar=False)
            pedidos.append({"fid": fid, "tema": tema, "agendado_para": "", "url": "", "erro": ""})
        if len(pedidos) > len(_pedidos(linha)):
            banco.executar("UPDATE canais_teste SET estado='liberado', pedidos=? WHERE usuario_id=? AND canal_id=?",
                           json.dumps(pedidos, ensure_ascii=False), usuario_id, linha["canal_id"])
            mudados.append(linha["canal_id"])
    return mudados


# ---------------------------------------------------------------- nunca o mesmo vídeo duas vezes (2026-11-25)

def _marca(p: dict) -> tuple:
    """O que faz dois vídeos de teste serem o mesmo: o vídeo do banco, ou o título (sem olhar maiúsculas e espaços)."""
    return ("banco", p["banco_id"]) if p.get("banco_id") else ("tema", fila._chave_titulo(p.get("tema")))


def _fixo(p: dict) -> bool:
    """O vídeo que já foi ao canal (ou está indo): esse não se troca mais."""
    return bool(p.get("postado") or p.get("enviado") or p.get("url"))


def _substituto(usuario_id: int, canal_id: str, lingua: str, vistos: set) -> dict | None:
    """Um vídeo de teste que nenhum canal teve: o do estoque pronto na língua, senão um título livre (dos assuntos
    ligados e, esgotados, de qualquer assunto) que vira pedido na fila. None quando não sobra nenhum."""
    for guardado in _estoque(usuario_id):
        if guardado["estado"] == "entregue" and guardado["lingua"] == lingua and ("tema", fila._chave_titulo(guardado["tema"])) not in vistos:
            banco.executar("UPDATE estoque_teste SET usado=? WHERE id=?", canal_id, guardado["id"])
            return {"fid": guardado["fid"], "tema": guardado["tema"]}
    usados = {fila._chave_titulo(l["tema"]) for l in banco.todos("SELECT tema FROM estoque_teste WHERE usuario_id=?", usuario_id)}
    candidatos = temas_novos(usuario_id, 10_000) + [t for a in ASSUNTOS.values() for t in a["temas"]]
    for tema in candidatos:
        chave = fila._chave_titulo(tema)
        if ("tema", chave) in vistos or chave in usados or fila.pedido_igual(usuario_id, tema):
            continue
        return {"fid": _pedido_de_teste(usuario_id, tema, lingua, comecar=False), "tema": tema}
    return None


def _trocar_repetidos() -> list:
    """Vídeo de teste nunca vai duas vezes ao ar (pedido do usuário em 2026-11-25): o recomeço dos temas de antes de
    2026-11-18 deu ao canal Pode Cortes três "The Day the Sun Will Die", que o PALHANO já tinha. Cada vídeo ainda não
    postado que repete um que já foi (ou outro mais antigo da lista) é trocado por um novo; sem nenhum novo, sai do
    teste, que fica com um a menos, mas não repete. O do Meu dia sai também (a extensão vê que sumiu da lista)."""
    mudaram, vistos_de = [], {}
    linhas = banco.todos("SELECT * FROM canais_teste ORDER BY liberado, rowid")
    for linha in linhas:
        vistos = vistos_de.setdefault(linha["usuario_id"], set())
        vistos |= {_marca(p) for p in _pedidos(linha) if _fixo(p)}
    for linha in linhas:
        if linha["estado"] not in ("liberado", "feito"):
            continue                       # o canal fora do teste não ganha vídeo novo
        vistos = vistos_de[linha["usuario_id"]]
        pedidos, novos, mexeu = _pedidos(linha), [], False
        for p in pedidos:
            if _fixo(p):
                novos.append(p)
                continue
            if _marca(p) not in vistos:
                vistos.add(_marca(p))
                novos.append(p)
                continue
            outro = _substituto(linha["usuario_id"], linha["canal_id"], linha["lingua"] or LINGUA_PADRAO, vistos)
            mexeu = True
            mudaram.append(_chave(p))
            if outro:
                vistos.add(_marca(outro))
                novos.append({**outro, "agendado_para": "", "url": "", "erro": "", "trocou": p.get("tema", "")})
        if mexeu:
            estado = "liberado" if linha["estado"] == "feito" and not all(_fixo(p) for p in novos) else linha["estado"]
            banco.executar("UPDATE canais_teste SET pedidos=?, estado=? WHERE usuario_id=? AND canal_id=?",
                           json.dumps(novos, ensure_ascii=False), estado, linha["usuario_id"], linha["canal_id"])
    return mudaram


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
        a = ajustes(usuario_id)
        guardados = _estoque(usuario_id)
        if not a["ligado"] or len(guardados) >= a["meta"]:
            continue
        if any(l["estado"] not in PARADOS for l in guardados):
            continue                       # o anterior ainda está sendo feito: espera ele
        temas = temas_novos(usuario_id, 1)
        if not temas:
            continue
        fid = _pedido_de_teste(usuario_id, temas[0], a["lingua"], comecar=True)
        banco.executar("INSERT INTO estoque_teste (usuario_id, tema, lingua, fid, criado) VALUES (?,?,?,?,?)",
                       usuario_id, temas[0], a["lingua"], fid, banco.agora())
        return [fid]
    return []


def _primeira_hora(agora: datetime | None = None) -> datetime:
    """A próxima `HORA_DO_POST` com folga para o YouTube aceitar o publishAt (ele pede 10 minutos no futuro)."""
    agora = agora or datetime.now()
    hoje = agora.replace(hour=HORA_DO_POST, minute=0, second=0, microsecond=0)
    return hoje if hoje >= agora + timedelta(minutes=30) else hoje + timedelta(days=1)


def _proximo_dia(pedidos: list[dict], k: int = 0) -> datetime:
    """A hora do próximo vídeo do canal: `INTERVALO_DIAS` depois do último marcado, sempre às `HORA_DO_POST`, a
    mesma de todo canal (pedido do usuário em 2026-11-25). O primeiro vai na próxima `HORA_DO_POST`."""
    primeira = _primeira_hora()
    marcados = []
    for p in pedidos:
        if p.get("agendado_para"):
            try:
                marcados.append(datetime.fromisoformat(p["agendado_para"]))
            except ValueError:
                continue
    if not marcados:
        return primeira
    seguinte = max(max(marcados) + timedelta(days=INTERVALO_DIAS), primeira)
    return seguinte.replace(hour=HORA_DO_POST, minute=0, second=0, microsecond=0)


def _pronto_para_subir(linha: dict, p: dict) -> tuple[str, dict | None]:
    """O projeto da fábrica deste vídeo de teste e o item da fila dele ("" quando ainda não dá para subir).

    O do banco está sempre pronto: a pasta dele na fábrica é feita aqui na primeira vez. O do Radar espera a fila."""
    if p.get("banco_id"):
        return _projeto_do_banco(linha, p), None
    if not p.get("fid"):
        return "", None
    item = fila.item(linha["usuario_id"], p["fid"])
    if not item or not item.get("projeto"):
        return "", item
    return item["projeto"], item


def _publicar_prontos() -> list:
    """Cada vídeo de teste pronto é agendado no canal do teste, `INTERVALO_DIAS` depois do outro, sempre às
    `HORA_DO_POST` (o publishAt do próprio YouTube: sobe com o computador desligado)."""
    mudaram = []
    agora = datetime.now().timestamp()
    # "feito" entra junto: os vídeos podem ter sido mandados na mesma volta, e o link de cada um só aparece depois,
    # quando a fábrica termina o envio e grava o youtube.json
    for linha in banco.todos("SELECT * FROM canais_teste WHERE estado IN ('liberado','feito')"):
        pedidos, mexeu = _pedidos(linha), False
        if not O_RADAR_POSTA:
            # quem posta é a pessoa: aqui só se marca o dia de cada vídeo e se separa o vídeo pronto (2026-11-25)
            if _marcar_dias(pedidos) | _separar_prontos(linha, pedidos):
                _gravar_pedidos(linha["usuario_id"], linha["canal_id"], pedidos)
                mudaram.append(linha["canal_id"])
            continue
        for k, p in enumerate(pedidos):
            if p.get("url"):
                continue
            try:
                projeto, item = _pronto_para_subir(linha, p)
            except (ValueError, OSError) as erro:
                if p.get("erro") != str(erro):
                    p["erro"] = str(erro)
                    mexeu = True
                continue
            if not projeto:
                continue
            if p.get("enviado"):
                # já mandado: o link aparece quando a fábrica termina o envio e grava o youtube.json
                publicado = fabrica_api.youtube_do_projeto(projeto)
                if publicado and publicado.get("url"):
                    p["url"] = publicado["url"]
                    p["video_id"] = publicado.get("video_id", "")
                    mexeu = True
                    mudaram.append(_chave(p))
                    continue
                if agora - float(p.get("tentado") or 0) < ESPERA_NOVA_TENTATIVA:
                    continue
                # sem link depois de todo esse tempo: ou a fábrica ainda está subindo, ou ela foi religada no meio e
                # o envio morreu com ela (a tarefa dela só existe na memória). Sem tarefa e sem publicação, manda de novo
                # A fábrica só conta a tarefa a quem dá o id dela: sem ele a resposta vem sempre sem tarefa, e todo envio
                # que passava de 15 minutos subia de novo, duplicado (The Moon, 2026-11-20). Envio de antes de guardar
                # o id fica quieto: sem como perguntar, mandar de novo arrisca o vídeo em dobro no canal.
                if not p.get("tarefa"):
                    continue
                try:
                    andamento = fabrica_api.youtube_publicacao(projeto, p["tarefa"])
                except fabrica_api.SemFabrica:
                    continue
                tarefa = andamento.get("tarefa") or {}
                if andamento.get("publicado") or (tarefa and tarefa.get("status") != "erro"):
                    continue
                motivo = (f"O envio falhou na fábrica ({tarefa.get('erro')}); mandando de novo." if tarefa
                          else "O envio se perdeu na fábrica; mandando de novo.")
                p |= {"enviado": False, "agendado_para": "", "tarefa": "", "erro": motivo}
                mexeu = True
                mudaram.append(_chave(p))
                continue
            if p.get("manual"):
                mexeu |= _andar_na_extensao(linha, p, agora)
                continue
            if item is not None and item["estado"] != "entregue":
                continue
            if p.get("erro") and agora - float(p.get("tentado") or 0) < ESPERA_NOVA_TENTATIVA:
                continue
            # todos na mesma hora, de INTERVALO_DIAS em INTERVALO_DIAS (pedido do usuário em 2026-11-25): até
            # 2026-11-25 o primeiro subia na hora e o outro no dia seguinte
            quando = _proximo_dia(pedidos, k)
            p["tentado"] = agora
            if POSTAR_PELA_EXTENSAO:
                # vai para o Meu dia da extensão (/api/ext/teste/pendentes): ela abre o Studio do canal, sobe o vídeo
                # só com o título e agenda para `quando`
                _kit_so_titulo(projeto, p)
                p |= {"agendado_para": quando.isoformat(timespec="minutes"), "erro": "", "manual": True,
                      "projeto": projeto}
                mexeu = True
                mudaram.append(_chave(p))
                continue
            if p.get("banco_id"):
                # o vídeo de verdade da pessoa: o título e a descrição são os que ela escreveu no banco
                kit = {"titulo": p.get("tema", ""), "descricao": p.get("descricao") or p.get("tema", ""), "tags": []}
            else:
                from . import agendar          # import tardio: o agendar usa a fila, como este módulo
                kit = agendar.kit_do_video(linha["usuario_id"], item)
                if not kit.get("descricao"):
                    # nenhum vídeo sobe pelado: a descrição se escreve na próxima volta (pedido de 2026-11-17)
                    p["erro"] = agendar.SEM_DESCRICAO
                    mexeu = True
                    mudaram.append(_chave(p))
                    continue
            try:
                # sem thumbnail de propósito: o vídeo de teste sobe com os quadros automáticos do YouTube
                resposta = fabrica_api.youtube_publicar(projeto, canal=linha["canal_id"],
                                                        quando=quando.strftime("%Y-%m-%dT%H:%M"),
                                                        com_thumbnail=False,
                                                        titulo=kit.get("titulo", ""), descricao=kit["descricao"],
                                                        tags=kit.get("tags") or [])
                p |= {"agendado_para": quando.isoformat(timespec="minutes"), "erro": "", "enviado": True,
                      "tarefa": (resposta or {}).get("tarefa_id", "")}
            except fabrica_api.SemFabrica as erro:
                p["erro"] = str(erro)
            mexeu = True
            mudaram.append(_chave(p))
        if mexeu:
            _gravar_pedidos(linha["usuario_id"], linha["canal_id"], pedidos)
        if pedidos and all(p.get("enviado") or p.get("postado") for p in pedidos):
            banco.executar("UPDATE canais_teste SET estado='feito' WHERE usuario_id=? AND canal_id=?",
                           linha["usuario_id"], linha["canal_id"])
    return mudaram


# ---------------------------------------------------------------- a pessoa posta (2026-11-25)

def _marcar_dias(pedidos: list[dict]) -> bool:
    """O dia de cada vídeo do teste que ainda não tem: um a cada `INTERVALO_DIAS`, às `HORA_DO_POST`."""
    mexeu = False
    for p in pedidos:
        if not p.get("agendado_para") and not _fixo(p):
            p["agendado_para"] = _proximo_dia(pedidos).isoformat(timespec="minutes")
            mexeu = True
    return mexeu


def _separar_prontos(linha: dict, pedidos: list[dict]) -> bool:
    """O vídeo de teste que ficou pronto vai para a aba Canais de teste com o Postar: o projeto da fábrica e o kit só
    com o título. `manual` é o que faz a extensão avisar quando postou (`postado_extensao`)."""
    mexeu = False
    for p in pedidos:
        if _fixo(p) or p.get("projeto"):
            continue
        try:
            projeto, item = _pronto_para_subir(linha, p)
        except (ValueError, OSError):
            continue
        if not projeto or (item is not None and item["estado"] != "entregue"):
            continue
        _kit_so_titulo(projeto, p)
        p |= {"projeto": projeto, "manual": True, "erro": ""}
        mexeu = True
    return mexeu


_CONFERIDO: dict[str, float] = {}


def _local(publicado: str) -> datetime | None:
    try:
        return datetime.fromisoformat(publicado.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def _conferir_canal(linha: dict) -> bool:
    """Saiu vídeo no canal? Cada dia que chegou e ainda não tem vídeo fica com o primeiro vídeo público que o canal
    soltou depois do começo do teste e que não é de outro dia. Qualquer vídeo vale (o do cachorro também): o que
    importa é o canal ter postado. Vídeo agendado só aparece quando vai ao ar. Devolve se mexeu."""
    from . import youtube
    pedidos = _pedidos(linha)
    hoje = datetime.now().date().isoformat()
    agora = datetime.now().isoformat(timespec="minutes")
    vez = sorted((p for p in pedidos if not _fixo(p) and (p.get("agendado_para") or "9")[:10] <= hoje),
                 key=lambda p: p["agendado_para"])
    # agendado pela extensão e já no ar: falta só o link, achado pelo título
    sem_link = [p for p in pedidos if p.get("postado") and not p.get("url") and (p.get("agendado_para") or "9") <= agora]
    if not vez and not sem_link:
        return False
    _CONFERIDO[linha["canal_id"]] = time.time()
    with youtube.gastando("studio"):
        ids = youtube.envios(linha["canal_id"], 15)
        videos = youtube.videos(ids) if ids else []
    inicio = _local(linha["liberado"] or linha["criado"] or "") or datetime.min
    usados = {p.get("video_id") for p in pedidos if p.get("video_id")}
    livres = sorted((v for v in videos
                     if v["id"] not in usados and (_local(v.get("publicado", "")) or datetime.min) >= inicio),
                    key=lambda v: v["publicado"])
    mexeu = False
    from . import publicar
    for p in sem_link:
        alvos = {publicar.normalizar(t) for t in (p.get("tema"), p.get("titulo_postado")) if t}
        achado = next((v for v in livres if publicar.normalizar(v["titulo"]) in alvos), None)
        if achado:
            livres.remove(achado)
            p |= {"url": f"https://youtu.be/{achado['id']}", "video_id": achado["id"], "enviado": True}
            mexeu = True
    for p, v in zip(vez, livres):
        p |= {"url": f"https://youtu.be/{v['id']}", "video_id": v["id"], "postado": True, "enviado": True,
              "postado_em": _local(v["publicado"]).isoformat(timespec="minutes"),
              "titulo_postado": v["titulo"][:200], "erro": ""}
        p.pop("falhou", None)
        mexeu = True
    if mexeu:
        _gravar_pedidos(linha["usuario_id"], linha["canal_id"], pedidos)
    return mexeu


def conferir_postados(usuario_id: int | None = None, a_cada: int = CONFERIR_A_CADA) -> list:
    """Confere os canais com dia vencido sem vídeo (o vigia, de meia em meia hora; a aba aberta, mais vezes)."""
    if O_RADAR_POSTA:
        return []
    mudaram = []
    sql, args = "SELECT * FROM canais_teste WHERE estado IN ('liberado','feito')", []
    if usuario_id is not None:
        sql, args = sql + " AND usuario_id=?", [usuario_id]
    for linha in banco.todos(sql, *args):
        if time.time() - _CONFERIDO.get(linha["canal_id"], 0) < a_cada:
            continue
        try:
            if _conferir_canal(linha):
                mudaram.append(linha["canal_id"])
        except Exception as erro:  # noqa: BLE001 (sem cota ou sem rede: confere na próxima volta)
            _CONFERIDO[linha["canal_id"]] = time.time()
            print("teste do canal, conferir:", erro)
    return mudaram


# ---------------------------------------------------------------- o post pela extensão (2026-11-25)

def _andar_na_extensao(linha: dict, p: dict, agora: float) -> bool:
    """O vídeo que está com a extensão. Postado: procura o link dele no canal. Ainda não e a hora chegando: vai para a
    próxima vaga (o Chrome estava fechado, o Studio parou no meio), e a extensão pega a hora nova. Devolve se mexeu."""
    if p.get("postado"):
        if agora - float(p.get("tentado") or 0) < ESPERA_NOVA_TENTATIVA:
            return False
        p["tentado"] = agora
        try:
            achado = _achar_no_canal(linha["canal_id"], p)
        except Exception:  # noqa: BLE001 (sem cota: procura na próxima volta)
            achado = None
        if achado:
            p |= achado
        return True
    # o kit só com o título, sempre: o vídeo que entrou na extensão antes dele subia com a descrição e as tags do
    # roteiro (o do canal japão, 2026-11-25)
    if p.get("projeto") and not _so_titulo_pronto(p["projeto"]):
        _kit_so_titulo(p["projeto"], p)
    limite = datetime.now() + timedelta(seconds=FOLGA_DO_STUDIO)
    if p.get("agendado_para") and p["agendado_para"] > limite.isoformat(timespec="minutes"):
        return False
    p["agendado_para"] = _primeira_hora().isoformat(timespec="minutes")
    p["erro"] = "O Studio não postou até a hora: remarcado para a próxima vaga."
    p["falhou"] = p["erro"]
    return True


def _so_titulo_pronto(projeto: str) -> bool:
    try:
        return bool(json.loads((fabrica_api._pasta(projeto) / "publicacao_radar.json").read_text(encoding="utf-8")).get("so_titulo"))
    except (OSError, ValueError):
        return False


def _achar_no_canal(canal_id: str, p: dict) -> dict | None:
    """O link do vídeo postado pelo Studio: o último envio do canal com o mesmo título (2 de cota)."""
    from . import publicar, youtube
    alvos = {publicar.normalizar(t) for t in (p.get("tema"), p.get("titulo_postado")) if t}
    with youtube.gastando("studio"):
        ids = youtube.envios(canal_id, 15)
        videos = youtube.videos(ids) if ids else []
    for v in videos:
        if publicar.normalizar(v["titulo"]) in alvos:
            return {"url": f"https://youtu.be/{v['id']}", "video_id": v["id"], "enviado": True, "erro": ""}
    return None


def pendentes_extensao(usuario_id: int) -> list[dict]:
    """Os vídeos de teste que a extensão guarda para postar. Com o Radar postando, cada um com o postar sozinho; com a
    pessoa postando (`O_RADAR_POSTA` desligado, 2026-11-25), sem ele: o Postar é apertado na aba Canais de teste."""
    saida = []
    sozinhos = set(ajustes(usuario_id)["sozinho"])
    for linha in banco.todos("SELECT * FROM canais_teste WHERE usuario_id=? AND estado IN ('liberado','feito')",
                             usuario_id):
        auto = O_RADAR_POSTA or linha["canal_id"] in sozinhos
        for p in _pedidos(linha):
            if p.get("manual") and not p.get("postado") and p.get("agendado_para") and p.get("projeto"):
                if not _so_titulo_pronto(p["projeto"]):
                    _kit_so_titulo(p["projeto"], p)
                saida.append({"id": f"{linha['canal_id']}:{_chave(p)}", "titulo": p.get("tema", ""),
                              "canal": linha["canal_id"], "canalNome": linha["nome"] or "",
                              "agendar": p["agendado_para"][:16], "projeto": p["projeto"], "auto": auto,
                              # com a pessoa postando, o sozinho publica no dia e na hora, sem agendar no Studio
                              "naHora": auto and not O_RADAR_POSTA})
    return saida


DIAS_PARA_AVALIAR = 2     # depois de um vídeo de teste ir ao ar, quantos dias até valer olhar as métricas


def _falhou(p: dict) -> str:
    """Por que o Radar não conseguiu postar este vídeo (vazio quando está tudo certo)."""
    if p.get("postado") or p.get("url"):
        return ""
    return p.get("falhou") or (p.get("erro") if p.get("manual") and p.get("erro") else "")


def resumo_extensao(usuario_id: int) -> dict:
    """A aba Canais de teste da beirada direita do YouTube, por canal (pedido do usuário em 2026-11-25): a faixa com
    os canais, como a dos dias do Meu dia, e em cada um os 3 vídeos com o dia de postar. Vermelho no dia de postar (e
    depois, se não saiu), azul antes, verde postado. Quem posta é a pessoa: o Postar abre o Studio do canal com o
    vídeo; o "Avaliar métricas" abre as métricas dele."""
    hoje = datetime.now().date().isoformat()
    agora = datetime.now().isoformat(timespec="minutes")
    canais = []
    sozinhos = set(ajustes(usuario_id)["sozinho"])
    for c in todos(usuario_id):
        if c["estado"] not in ("liberado", "feito"):
            continue
        pedidos = _pedidos(_linha(usuario_id, c["canal_id"]))
        no_ar = sorted(p["agendado_para"] for p in pedidos
                       if p.get("agendado_para") and p["agendado_para"] <= agora and _fixo(p))
        avaliar_em = ((datetime.fromisoformat(no_ar[-1]).date() + timedelta(days=DIAS_PARA_AVALIAR)).isoformat()
                      if no_ar else "")
        avaliar_hoje = bool(avaliar_em) and avaliar_em <= hoje and (c["avaliado"] or "")[:10] < avaliar_em
        videos = []
        for k, p in enumerate(pedidos, 1):
            quando = (p.get("agendado_para") or "")[:16]
            cor = ("verde" if _fixo(p) else "" if not quando else "vermelho" if quando[:10] <= hoje else "azul")
            videos.append({"numero": k, "tema": p.get("tema", ""), "quando": quando, "cor": cor,
                           "url": p.get("url", ""), "pronto": bool(p.get("projeto")), "views": p.get("views"),
                           "id": f"{c['canal_id']}:{_chave(p)}" if p.get("projeto") and not _fixo(p) else ""})
        canal = banco.um("SELECT handle FROM canais WHERE id=?", c["canal_id"]) or {}
        canais.append({"canal_id": c["canal_id"], "nome": c["nome"] or c["canal_id"], "avaliar_hoje": avaliar_hoje,
                       "handle": canal.get("handle") or "",
                       "bom": c["bom"], "avaliacao": c["avaliacao"], "videos": videos, "sozinho": c["canal_id"] in sozinhos, "postados": sum(v["cor"] == "verde" for v in videos),
                       "para_postar": sum(v["cor"] == "vermelho" for v in videos)})
    # as línguas vão junto para o "Adicionar canal" da aba, e todos os canais que já tiveram teste (qualquer estado),
    # para a aba dizer quais canais da conta do YouTube ainda faltam testar (2026-11-26)
    testados = [{"canal_id": r["canal_id"], "nome": r["nome"] or "", "handle": r["handle"] or "", "estado": r["estado"]}
                for r in banco.todos("SELECT t.canal_id, t.nome, t.estado, c.handle FROM canais_teste t "
                                     "LEFT JOIN canais c ON c.id = t.canal_id WHERE t.usuario_id=?", usuario_id)]
    return {"canais": canais, "para_postar": sum(c["para_postar"] for c in canais),
            "linguas": list(fabrica_api.IDIOMA), "lingua_padrao": LINGUA_PADRAO, "testados": testados}


def avaliar(usuario_id: int, canal_id: str, avaliacao: str) -> None:
    """O que a pessoa achou do canal olhando as métricas: "bom" acende o alerta de canal bom; "ruim" apaga."""
    if avaliacao not in ("bom", "ruim", ""):
        raise ValueError("A avaliação é bom ou ruim.")
    if not _linha(usuario_id, canal_id):
        raise ValueError("Esse canal não tem teste.")
    banco.executar("UPDATE canais_teste SET avaliacao=?, avaliado=? WHERE usuario_id=? AND canal_id=?",
                   avaliacao, datetime.now().isoformat(timespec="minutes"), usuario_id, canal_id)


def postar_sozinho(usuario_id: int, canal_id: str, ligado: bool) -> None:
    """O botão "Postar sozinho" do canal na aba Canais de teste (2026-11-25): ligado, a extensão publica cada vídeo
    do teste no dia e na hora marcados, na hora mesmo (sem agendar antes no Studio)."""
    if not _linha(usuario_id, canal_id):
        raise ValueError("Esse canal não tem teste.")
    atuais = [c for c in ajustes(usuario_id)["sozinho"] if c != canal_id]
    salvar_ajustes(usuario_id, {"sozinho": atuais + ([canal_id] if ligado else [])})


def olhou_metricas(usuario_id: int, canal_id: str) -> None:
    """A pessoa abriu as métricas do canal pelo "Avaliar métricas": o aviso de hoje sai, a avaliação fica."""
    banco.executar("UPDATE canais_teste SET avaliado=? WHERE usuario_id=? AND canal_id=?",
                   datetime.now().isoformat(timespec="minutes"), usuario_id, canal_id)


def falhou_extensao(usuario_id: int, ident: str, motivo: str) -> bool:
    """O Studio parou no meio do postar sozinho: o canal fica vermelho até o vídeo ser postado."""
    canal_id, _, chave = ident.partition(":")
    linha = _linha(usuario_id, canal_id)
    if not linha:
        return False
    pedidos = _pedidos(linha)
    for p in pedidos:
        if _chave(p) == chave:
            p["falhou"] = (motivo or "o Studio parou no meio")[:300]
            p["ultima_falha"] = f"{banco.agora()} {p['falhou']}"
            _gravar_pedidos(usuario_id, canal_id, pedidos)
            return True
    return False


def postado_extensao(usuario_id: int, ident: str, titulo: str = "") -> bool:
    """A extensão agendou o vídeo no Studio. O link é achado no canal depois (`_achar_no_canal`)."""
    canal_id, _, chave = ident.partition(":")
    linha = _linha(usuario_id, canal_id)
    if not linha:
        return False
    pedidos = _pedidos(linha)
    for p in pedidos:
        if _chave(p) == chave and p.get("manual"):
            p |= {"postado": True, "postado_em": banco.agora(), "titulo_postado": titulo[:200], "erro": "",
                  "tentado": 0, "falhou": ""}
            _gravar_pedidos(usuario_id, canal_id, pedidos)
            return True
    return False


# ---------------------------------------------------------------- as impressões e o alerta de canal bom (2026-11-25)

def _impressoes(usuario_id: int, canal_id: str, video_id: str, desde: str) -> int | None:
    """As impressões do vídeo desde o dia em que subiu, pelo Studio do Radar. None sem o Studio ligado no canal.

    O login da fábrica só posta (escopo youtube): quem lê as impressões é o YouTube Analytics, e ele pede o canal
    conectado no Studio do Radar (Perfil, Seus canais)."""
    from datetime import date

    from . import studio
    if canal_id not in studio.conectados(usuario_id):
        return None
    token = studio._token(usuario_id, canal_id)
    inicio = (desde or date.today().isoformat())[:10]
    r = studio._relatorio(token, canal_id, inicio, date.today().isoformat(), "videoThumbnailImpressions",
                          filters=f"video=={video_id}")
    if r is None:
        return None
    linhas = r.get("linhas") or []
    return int(linhas[0].get("videoThumbnailImpressions") or 0) if linhas else 0


def _medir() -> list:
    """De hora em hora, as views (1 de cota para até 50 vídeos) e as impressões de cada vídeo de teste no ar.
    Passou de `LIMITE_ALERTA` impressões, o canal acende o alerta. Sem o Studio, as views valem no lugar: um vídeo
    com mil views teve mais de mil impressões ou veio de fora, e as duas coisas dizem que o canal pegou."""
    from . import youtube
    agora = time.time()
    agora_iso = datetime.now().isoformat(timespec="minutes")
    mudaram = []
    for linha in banco.todos("SELECT * FROM canais_teste WHERE estado IN ('liberado','feito')"):
        pedidos = _pedidos(linha)
        vez = [p for p in pedidos if p.get("video_id") and agora - float(p.get("medido") or 0) >= MEDIR_A_CADA
               and (p.get("agendado_para") or "") <= agora_iso]
        if not vez:
            continue
        try:
            with youtube.gastando("studio"):
                views = {v["id"]: v["views"] for v in youtube.videos([p["video_id"] for p in vez])}
        except Exception:  # noqa: BLE001 (sem cota ou sem rede: mede na próxima volta)
            views = {}
        for p in vez:
            p["medido"] = agora
            if views.get(p["video_id"]) is not None:
                p["views"] = views[p["video_id"]]
            try:
                imp = _impressoes(linha["usuario_id"], linha["canal_id"], p["video_id"], p.get("agendado_para", ""))
            except Exception:  # noqa: BLE001 (o Studio fora do ar não apaga a leitura de antes)
                imp = None
            p["sem_studio"] = imp is None and p.get("impressoes") is None
            if imp is not None:
                p["impressoes"] = max(imp, int(p.get("impressoes") or 0))
            passou = ((p.get("impressoes") or 0) >= LIMITE_ALERTA
                      or (p.get("impressoes") is None and (p.get("views") or 0) >= LIMITE_ALERTA))
            if passou and not p.get("alerta_em"):
                p["alerta_em"] = banco.agora()
            mudaram.append(_chave(p))
        _gravar_pedidos(linha["usuario_id"], linha["canal_id"], pedidos)
    return mudaram


def alertas(usuario_id: int) -> list[dict]:
    """Os canais novos bons que a pessoa ainda não dispensou: um por vídeo que passou do limite."""
    saida = []
    for linha in banco.todos("SELECT * FROM canais_teste WHERE usuario_id=? AND estado IN ('liberado','feito')",
                             usuario_id):
        for p in _pedidos(linha):
            if p.get("alerta_em") and not p.get("alerta_visto") and (linha.get("avaliacao") or "") != "ruim":
                saida.append({"canal_id": linha["canal_id"], "canal": linha["nome"] or linha["canal_id"],
                              "chave": _chave(p), "tema": p.get("tema", ""), "url": p.get("url", ""),
                              "impressoes": p.get("impressoes"), "views": p.get("views"),
                              "pelas_views": p.get("impressoes") is None, "quando": p["alerta_em"]})
    return sorted(saida, key=lambda a: a["quando"], reverse=True)


def alerta_visto(usuario_id: int, canal_id: str, chave: str = "") -> list[dict]:
    """A pessoa viu o alerta: ele sai do topo das telas. O canal continua marcado como bom no Painel."""
    linha = _linha(usuario_id, canal_id)
    if not linha:
        raise ValueError("Esse canal não tem teste.")
    pedidos = _pedidos(linha)
    for p in pedidos:
        if not chave or _chave(p) == chave:
            p["alerta_visto"] = True
    _gravar_pedidos(usuario_id, canal_id, pedidos)
    return alertas(usuario_id)


def painel(usuario_id: int) -> dict:
    """O Painel da área Canal de teste: os números de cima, os canais com os três vídeos e os alertas."""
    testes = todos(usuario_id)
    videos = [v for t in testes for v in t["videos"]]
    agora = datetime.now().isoformat(timespec="minutes")
    return {"testes": testes, "sem_teste": sem_teste(usuario_id), "alertas": alertas(usuario_id), "limite": LIMITE_ALERTA,
            "intervalo": INTERVALO_DIAS, "hora": HORA_DO_POST, "quantos": POR_CANAL,
            "numeros": {"canais": len(testes), "bons": len([t for t in testes if t["bom"]]),
                        "no_ar": len([v for v in videos if v["url"] and v["agendado_para"] <= agora]),
                        "agendados": len([v for v in videos if v["enviado"] and v["agendado_para"] > agora]),
                        "banco": len(banco_de_videos(usuario_id)), "estoque": estoque_pronto(usuario_id)}}


def andar() -> list[int]:
    """Uma volta do teste dos canais, chamada pelo vigia da fila. Nunca levanta: a fila não pode parar por isto."""
    mudaram = []
    for passo in (_ligar_conectados, _trocar_repetidos, _soltar_um_parado, _publicar_prontos, conferir_postados, _medir, _encher_estoque):
        try:
            mudaram += passo()
        except Exception as erro:  # noqa: BLE001 (o vigia nunca pode parar)
            print("teste do canal:", erro)
    return mudaram
