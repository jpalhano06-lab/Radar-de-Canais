"""Meu nicho: o perfil de busca de cada pessoa, preenchido no Formulário, e a busca certeira que sai dele.

Pedido do usuário em 2026-10-27, no modelo das escolhas de gênero do Spotify: a pessoa diz o tema do canal
("mercados") e a página mostra os canais já validados que falam disso. Em 2026-10-28: "o YouTube treina com base nas
minhas pesquisas, tem que ser um algoritmo especializado" — e uma página, o Formulário, com tudo o que o algoritmo
precisa, editável a qualquer hora.

A API do YouTube não tem perfil: a mesma busca dá o mesmo resultado para qualquer chave. O "treino" é este perfil.
O que fica guardado (`usuarios.nicho`):

- o canal: tema e o que ele faz;
- as palavras do nicho: as lacunas das estruturas e as palavras soltas que dizem o assunto ("shark", "walmart");
- os canais de referência: os que a pessoa já sabe que são o modelo. Os títulos que mais renderam neles são o
  exemplo que o Groq segue para escrever as buscas, e eles mesmos entram na lista como validados;
- o que é um canal validado (`filtros`): views por vídeo, idade, inscritos, sem rosto, palavras proibidas;
- como buscar: período dos vídeos, duração, ordem, países, língua;
- as buscas: os títulos que a própria pessoa escreveu, as estruturas escritas no nicho e os ganchos do nicho.
"""
import json
import re
from datetime import datetime, timedelta, timezone

from . import banco, estruturas, garimpo, gosto, ia, medir, mercado, metricas, risco, youtube

# as lacunas das estruturas e as "palavras": as soltas que dizem o assunto ("shark", "walmart"). Elas não preenchem
# estrutura nenhuma; servem para reconhecer o canal do nicho, porque "Wildlife Conservation" quase nunca aparece
# inteira num título (o usuário escolheu animais em 2026-10-27 e a lista ficou vazia)
CAMPOS = estruturas.LACUNAS + ("palavras",)

# o canal validado e o jeito de buscar. min_views: 5 mil por vídeo; idade e inscritos 0 = sem limite (o garimpo
# procura os que estão nascendo; aqui a pessoa quer ver quem já dá certo — o filtro de 18 meses deixava animais com zero)
FILTROS = {"min_views": 5_000, "idade_max_meses": 0, "inscritos_min": 0, "inscritos_max": 0, "sem_rosto": False,
           "proibidas": [], "dias": 180, "duracao": "alternar", "ordem": "relevance",
           "paises": ["US", "GB", "CA", "AU"], "lingua": "en"}
DURACOES = ("alternar", "long", "medium", "any")
ORDENS = ("relevance", "viewCount")
PAISES = ("US", "GB", "CA", "AU", "NZ", "IE", "BR", "PT", "ES", "MX", "AR", "IN", "DE", "FR")
LINGUAS = ("en", "pt", "es", "de", "fr")

PADRAO = {"feito": False, "tema": "", "descricao": "", "vocab": {l: [] for l in CAMPOS}, "desligadas": [],
          "buscas": {}, "ganchos": [], "proprias": [], "referencias": [], "filtros": FILTROS}
GANCHO = "(gancho do nicho)"     # o rótulo das buscas que são ganchos típicos do nicho, não de uma estrutura
PROPRIA = "(sua busca)"          # o rótulo dos títulos de busca que a pessoa escreveu
REFERENCIA = "(referência)"      # o canal que a pessoa deu como modelo, na lista de canais do nicho

BUSCAS_POR_VEZ = 2          # cada "Procurar canais" faz 2 buscas (200 unidades) e mede os canais do nicho
CASA_MINIMO = 0.6           # o título tem 60% das palavras do gancho: é a mesma estrutura
MEDIR_POR_BUSCA = 25        # quantos canais do nicho cada busca mede (umas 3 unidades cada)
MAX_REFERENCIAS = 8


def ler(usuario: dict) -> dict:
    try:
        salvo = json.loads(usuario.get("nicho") or "{}")
    except ValueError:
        salvo = {}
    p = PADRAO | salvo
    p["vocab"] = {l: list(p.get("vocab", {}).get(l, [])) for l in CAMPOS}
    p["filtros"] = FILTROS | (p.get("filtros") or {})
    return p


def _palavras(lista, ate: int = 10, tamanho: int = 40, numeros: bool = False) -> list[str]:
    """Uma lista de palavras ou títulos, limpa: sem repetir e, nas lacunas, sem número (a regra das estruturas)."""
    saida = []
    for o in lista if isinstance(lista, list) else []:
        o = re.sub(r"\s+", " ", str(o)).strip()[:tamanho]
        if o and (numeros or not re.search(r"\d", o)) and o.lower() not in {s.lower() for s in saida}:
            saida.append(o)
    return saida[:ate]


def _inteiro(valor, padrao: int, maximo: int) -> int:
    try:
        return max(0, min(maximo, int(float(valor))))
    except (TypeError, ValueError):
        return padrao


def _filtros(d: dict) -> dict:
    d = d if isinstance(d, dict) else {}
    return {
        "min_views": _inteiro(d.get("min_views"), FILTROS["min_views"], 10_000_000),
        "idade_max_meses": _inteiro(d.get("idade_max_meses"), 0, 240),
        "inscritos_min": _inteiro(d.get("inscritos_min"), 0, 100_000_000),
        "inscritos_max": _inteiro(d.get("inscritos_max"), 0, 100_000_000),
        "sem_rosto": bool(d.get("sem_rosto", False)),
        "proibidas": _palavras(d.get("proibidas"), 30, numeros=True),
        "dias": _inteiro(d.get("dias"), FILTROS["dias"], 3650) or FILTROS["dias"],
        "duracao": d.get("duracao") if d.get("duracao") in DURACOES else FILTROS["duracao"],
        "ordem": d.get("ordem") if d.get("ordem") in ORDENS else FILTROS["ordem"],
        "paises": [x for x in d.get("paises", []) if x in PAISES][:8] or list(FILTROS["paises"]),
        "lingua": d.get("lingua") if d.get("lingua") in LINGUAS else FILTROS["lingua"],
    }


def salvar(usuario: dict, dados: dict) -> dict:
    """Guarda o formulário inteiro como veio. As buscas e os ganchos são os que estão na tela (a pessoa pode ter
    editado); o Groq só escreve de novo quando ela pede (`reescrever`) ou quando não há busca nenhuma."""
    vocab = dados.get("vocab") if isinstance(dados.get("vocab"), dict) else {}
    buscas = dados.get("buscas") if isinstance(dados.get("buscas"), dict) else {}
    antes = ler(usuario)
    limpo = {
        "feito": True,
        "tema": re.sub(r"\s+", " ", str(dados.get("tema", ""))).strip()[:80],
        "descricao": re.sub(r"\s+", " ", str(dados.get("descricao", ""))).strip()[:300],
        "vocab": {l: _palavras(vocab.get(l, []), 40 if l == "palavras" else 10) for l in CAMPOS},
        "desligadas": [str(t)[:110] for t in dados.get("desligadas", []) if isinstance(t, str)][:100],
        "buscas": {str(e)[:110]: _palavras(l, 3, 100) for e, l in buscas.items()},
        "ganchos": _palavras(dados.get("ganchos"), 20, 100),
        "proprias": _palavras(dados.get("proprias"), 30, 100, numeros=True),
        "filtros": _filtros(dados.get("filtros")),
        # as referências já medidas ficam (com o id); as novas chegam só com o que a pessoa colou
        "referencias": _referencias(dados.get("referencias"), antes["referencias"]),
        "vez": int(antes.get("vez") or 0),          # onde a fila de buscas parou não volta ao começo ao salvar
    }
    if not (limpo["buscas"] or limpo["ganchos"]) and limpo["tema"]:
        limpo |= reescrever(usuario, limpo)
    banco.executar("UPDATE usuarios SET nicho=? WHERE id=?", json.dumps(limpo, ensure_ascii=False), usuario["id"])
    return limpo


def _referencias(novas, antigas: list[dict]) -> list[dict]:
    """Os canais de referência: o que a pessoa colou (@, link) e, para os já resolvidos, o id e o nome."""
    ja = {r["ref"]: r for r in antigas}
    saida = []
    for ref in _palavras([r.get("ref") if isinstance(r, dict) else r for r in (novas or [])], MAX_REFERENCIAS, 200,
                         numeros=True):
        saida.append(ja.get(ref) or {"ref": ref, "id": "", "titulo": ""})
    return saida


def referencias_pendentes(p: dict) -> list[str]:
    return [r["ref"] for r in p["referencias"] if not r.get("id")]


def guardar_referencia(usuario_id: int, ref: str, canal: dict | None) -> None:
    """Depois de medir: o id e o nome entram no perfil e o canal entra na lista do nicho como modelo."""
    u = banco.um("SELECT * FROM usuarios WHERE id=?", usuario_id)
    p = ler(u)
    for r in p["referencias"]:
        if r["ref"] == ref:
            r["id"], r["titulo"] = (canal["id"], canal["titulo"]) if canal else ("", "não achei esse canal")
    banco.executar("UPDATE usuarios SET nicho=? WHERE id=?", json.dumps(p, ensure_ascii=False), usuario_id)
    if canal:
        banco.executar("INSERT OR REPLACE INTO nicho_canais (usuario_id, canal_id, estrutura, busca, criado) "
                       "VALUES (?,?,?,?,?)", usuario_id, canal["id"], REFERENCIA, "", banco.agora())


def titulos_das_referencias(p: dict, quantos: int = 25) -> list[str]:
    """Os títulos longos que mais renderam nos canais de referência: o estilo que as buscas devem seguir."""
    ids = [r["id"] for r in p["referencias"] if r.get("id")]
    if not ids:
        return []
    return [v["titulo"] for v in banco.todos(
        f"SELECT titulo FROM videos WHERE canal_id IN ({','.join('?' * len(ids))}) AND duracao_s>? "
        "ORDER BY views DESC LIMIT ?", *ids, metricas.CURTO_ATE_S, quantos)]


def reescrever(usuario: dict, p: dict) -> dict:
    """O Groq escreve as buscas de cada estrutura e os ganchos do nicho, a partir do formulário (e dos títulos dos
    canais de referência). Completa as palavras do assunto se estiverem vazias. Não guarda: devolve."""
    vocab = dict(p["vocab"])
    if not vocab.get("palavras"):
        sugestao = sugerir(p["tema"], p["descricao"])
        vocab = {l: vocab.get(l) or sugestao.get(l, []) for l in CAMPOS}
    r = ia.buscas_das_estruturas(p["tema"], p["descricao"], vocab, [e["texto"] for e in estruturas.todas()],
                                 titulos_das_referencias(p))
    return {"vocab": vocab, "buscas": r["estruturas"], "ganchos": r["ganchos"]}


def completar(usuario: dict, p: dict) -> dict:
    """O nicho salvo sem busca nenhuma (salvo antes delas existirem, ou o Groq não respondeu na hora): escreve agora
    e guarda. Antes, sem elas, a procura voltava em silêncio para as lacunas sorteadas (2026-10-28)."""
    if p["buscas"] or p["ganchos"] or p["proprias"] or not p["tema"]:
        return p
    p |= reescrever(usuario, p)
    if p["buscas"] or p["ganchos"]:
        banco.executar("UPDATE usuarios SET nicho=? WHERE id=?", json.dumps(p, ensure_ascii=False), usuario["id"])
    return p


def sugerir(tema: str, descricao: str = "") -> dict[str, list[str]]:
    """As palavras das lacunas para o tema, pelo Groq. Sem Groq, volta vazio e a pessoa escreve."""
    return ia.vocabulario(tema, descricao, CAMPOS)


def com_exemplos(p: dict) -> list[dict]:
    """As estruturas que a tela mostra: cada uma com as buscas que vão sair dela no nicho da pessoa."""
    saida = []
    for e in estruturas.todas():
        prontas = p["buscas"].get(e["texto"], [])
        nao_serve = bool(p["buscas"]) and not prontas
        saida.append({"texto": e["texto"], "origem": e["origem"], "vezes": e.get("vezes") or 0,
                      "canais": e.get("canais") or 0, "exemplos": prontas, "nao_serve": nao_serve,
                      "ligada": e["texto"] not in p["desligadas"] and not nao_serve})
    return saida


def proximas_buscas(p: dict, tentativa: int = 0, quantas: int = 8) -> list[dict]:
    """As buscas que o Procurar vai fazer, na ordem: a tela mostra para a pessoa saber o que vai para o YouTube."""
    fila = _fila(p)
    if not fila:
        return []
    inicio = (tentativa * BUSCAS_POR_VEZ) % len(fila)
    return [{"estrutura": e, "busca": b} for e, b in (fila[inicio:] + fila[:inicio])[:quantas]]


# ---------------------------------------------------------------- procurar

def _fila(p: dict) -> list[tuple[str, str]]:
    """Todas as buscas, na ordem em que vão para o YouTube: primeiro os títulos que a pessoa escreveu, depois as
    estruturas escritas no nicho intercaladas com os ganchos do nicho. Sem nada disso, nada: sortear as lacunas dava
    busca sem sentido ("When Rescue Operations These Reptile Terrariums Become Priceless") e gastava cota à toa."""
    rodadas = max([len(l) for l in p["buscas"].values()] + [1])
    das_estruturas = [(e, lista[i]) for i in range(rodadas) for e, lista in p["buscas"].items()
                      if e not in p["desligadas"] and i < len(lista)]
    ganchos = [(GANCHO, g) for g in p["ganchos"]]
    fila = [(PROPRIA, t) for t in p["proprias"]]
    for i in range(max(len(das_estruturas), len(ganchos))):
        fila += das_estruturas[i:i + 1] + ganchos[i:i + 1]
    return [(e, estruturas.busca(b)) for e, b in fila]


def _proximas(p: dict, quantas: int, tentativa: int) -> list[tuple[str, str]]:
    fila = _fila(p)
    if not fila:
        return []
    inicio = (tentativa * quantas) % len(fila)
    return (fila[inicio:] + fila[:inicio])[:quantas]


def _com_proibidas(termo: str, proibidas: list[str]) -> str:
    """A busca com as palavras proibidas tiradas pelo próprio YouTube ("-react"): só as de uma palavra."""
    menos = " ".join(f"-{w}" for w in proibidas if " " not in w)
    return f"{termo} {menos}".strip()[:200]


def validado(c: dict, f: dict, titulos: list[str]) -> str:
    """Por que o canal NÃO é validado pelo formulário ("" quando é). As regras são as da tela, nesta ordem."""
    if (c.get("base_longos") or 0) < f["min_views"]:
        return "views"
    meses = metricas.meses_postando(c.get("primeiro_video") or "")
    if f["idade_max_meses"] and (meses is None or meses > f["idade_max_meses"]):
        return "idade"
    inscritos = c.get("inscritos") or 0
    if (f["inscritos_min"] and inscritos < f["inscritos_min"]) or (f["inscritos_max"] and inscritos > f["inscritos_max"]):
        return "inscritos"
    if f["sem_rosto"] and c.get("sem_rosto") == 0:
        return "rosto"          # sem saber (None) passa: não sabido não é o mesmo que tem rosto
    proibidas = [gosto._simples(w) for w in f["proibidas"]]
    if proibidas and any(w in gosto._simples(t) for t in titulos for w in proibidas):
        return "proibida"
    if mercado.irrelevante(c.get("nicho"), c.get("subnicho")):
        return "irrelevante"
    return ""


@youtube.por("procura")
def procurar(usuario: dict, tentativa: int | None = None) -> dict:
    """As próximas buscas do perfil, feitas no YouTube agora, com o jeito de buscar do formulário.

    A busca devolve quem tem o gancho, de qualquer assunto ("Is Collapsing" trouxe novela chinesa para quem escolheu
    animais). Então, antes de gastar cota medindo, fica só o canal cujo vídeo achado fala do nicho (de graça, pelo
    título). Esses são medidos, e o que passa no "canal validado" do formulário é do nicho dela. Os que também passam
    no filtro do garimpo (novos, sem risco) entram no Radar de todos.

    Os vídeos que a busca devolveu e que falam do nicho ficam guardados para a pessoa (`nicho_videos`): são a tela do
    Meu nicho. `tentativa` None: continua de onde a fila parou (fica no perfil, para cada visita não refazer as
    mesmas duas buscas)."""
    p = completar(usuario, ler(usuario))
    f = p["filtros"]
    if tentativa is None:
        tentativa = int(p.get("vez") or 0)
    escolhidas = _proximas(p, BUSCAS_POR_VEZ, tentativa)
    if not escolhidas:
        return {"buscas": [], "novos": [], "achados": [], "proxima": tentativa + 1,
                "falta": "O seu perfil ainda não tem busca. No Formulário, escreva seus títulos de busca ou clique em "
                         "Escrever as buscas com IA, e salve."}
    depois = (datetime.now(timezone.utc) - timedelta(days=f["dias"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    expressoes = _expressoes(p)
    feitas, novos, do_nicho, videos_novos = [], [], [], 0
    for n, (estrutura, termo) in enumerate(escolhidas):
        vez = tentativa * BUSCAS_POR_VEZ + n
        duracao = f["duracao"] if f["duracao"] != "alternar" else ("medium" if vez % 2 else "long")
        achados = youtube.buscar(_com_proibidas(termo, f["proibidas"]), publicado_depois=depois, duracao=duracao,
                                 ordem=f["ordem"], regiao=f["paises"][vez % len(f["paises"])], idioma=f["lingua"])
        if not achados:
            # título longo e exato, mais país, duração e data, às vezes zera a busca ("The Shocking Truth About
            # Poaching That Governments Hide" voltou vazia em 2026-10-28): tenta uma vez sem país e sem duração
            achados = youtube.buscar(_com_proibidas(termo, f["proibidas"]), publicado_depois=depois, ordem=f["ordem"],
                                     idioma=f["lingua"])
        com_gancho = {a["canal_id"] for a in achados if estruturas.casa(a["titulo"], estrutura) >= CASA_MINIMO}
        titulos_de: dict[str, list[str]] = {}
        for a in achados:
            titulos_de.setdefault(a["canal_id"], []).append(a["titulo"] + " " + a.get("canal", ""))
        falam = [cid for cid, ts in titulos_de.items() if fala_do_nicho(ts, expressoes)[1]][:MEDIR_POR_BUSCA]
        entraram = garimpo._avaliar(falam, lambda _t: None, {"novos": 0}, rapido=True)
        # o _avaliar marca como medido agora, sem medir, o canal que ele reprova (antigo demais para o Radar): sem
        # forçar, o medir_canais achava que já estava medido e o canal ficava sem views por vídeo (2026-10-27)
        sem_numero = [c["id"] for c in medir._canais_do_banco(falam) if c["base_longos"] is None]
        medidos = medir.medir_canais(falam) | medir.medir_canais(sem_numero, forcar=True)
        bons, recusados, do_assunto_canal = [], {}, set()
        for c in medidos.values():
            titulos = [v["titulo"] for v in banco.todos(
                "SELECT titulo FROM videos WHERE canal_id=? ORDER BY publicado DESC LIMIT 50", c["id"])]
            motivo = validado(c, f, titulos)
            if fala_do_nicho([c["titulo"]] + titulos, expressoes)[2]:
                do_assunto_canal.add(c["id"])
            elif not motivo:
                motivo = "assunto"      # um vídeo falou do nicho, o canal não (novela com "tiger" num título)
            if not motivo and risco.avaliar(titulos[:20]):
                motivo = "risco"        # reaproveitado, em série...: não vale copiar
            if motivo:
                recusados[motivo] = recusados.get(motivo, 0) + 1
                continue
            bons.append(c["id"])
            banco.executar("INSERT OR IGNORE INTO nicho_canais (usuario_id, canal_id, estrutura, busca, criado) "
                           "VALUES (?,?,?,?,?)", usuario["id"], c["id"], estrutura, termo, banco.agora())
        # os vídeos da busca que vão para a tela: o título fala do nicho, sem palavra proibida, o CANAL fala do nicho
        # (uma palavra no título deixava passar "...the Wolf King Spoils Me") e é viral: o canal é validado ou o
        # próprio vídeo passa do mínimo de views do Formulário (entravam vídeos de 0 a 250 views)
        proibidas = [gosto._simples(w) for w in f["proibidas"]]
        candidatos = [a for a in achados if a["canal_id"] in do_assunto_canal
                      and fala_do_nicho([a["titulo"] + " " + a.get("canal", "")], expressoes)[1]
                      and not any(w in gosto._simples(a["titulo"]) for w in proibidas)]
        lidos = medir.medir_videos([a["video_id"] for a in candidatos])      # views e data: 1 unidade a cada 50
        do_assunto = [a for a in candidatos if a["canal_id"] in bons
                      or ((lidos.get(a["video_id"]) or {}).get("views") or 0) >= f["min_views"]]
        for a in do_assunto:
            videos_novos += banco.mudou(
                "INSERT OR IGNORE INTO nicho_videos (usuario_id, video_id, canal_id, estrutura, busca, achado) "
                "VALUES (?,?,?,?,?,?)", usuario["id"], a["video_id"], a["canal_id"], estrutura, termo,
                banco.agora())
        if estrutura not in (GANCHO, PROPRIA):
            estruturas.registrar(estrutura, len(bons))
        feitas.append({"estrutura": estrutura, "busca": termo, "vistos": len(titulos_de),
                       "com_gancho": len(com_gancho), "falam": len(falam), "do_nicho": len(bons),
                       "entraram": len(entraram), "recusados": recusados, "videos": len(do_assunto)})
        novos += [c for c in entraram if c not in novos]
        do_nicho += [c for c in bons if c not in do_nicho]
    _guardar_vez(usuario["id"], tentativa + 1)
    return {"buscas": feitas, "novos": novos, "achados": do_nicho, "videos_novos": videos_novos,
            "proxima": tentativa + 1, "proximas": proximas_buscas(p, tentativa + 1)}


def _guardar_vez(usuario_id: int, vez: int) -> None:
    """Onde a fila de buscas parou. Lê o perfil de novo: a pessoa pode ter salvado o Formulário enquanto buscava."""
    u = banco.um("SELECT * FROM usuarios WHERE id=?", usuario_id)
    p = ler(u) | {"vez": vez}
    banco.executar("UPDATE usuarios SET nicho=? WHERE id=?", json.dumps(p, ensure_ascii=False), usuario_id)


def atualizar_todos(log=print, orcamento: int = 0) -> int:
    """O garimpo de todo dia faz as próximas buscas do nicho de cada pessoa que preencheu o Formulário: os vídeos do
    Meu nicho chegam sem ninguém clicar. Para quando o orçamento de cota acaba (uns 250 por pessoa)."""
    inicio, feitas = youtube.cota_hoje()["usado"], 0
    for u in banco.todos("SELECT * FROM usuarios WHERE nicho<>'{}' ORDER BY id"):
        if not ler(u)["feito"]:
            continue
        if orcamento and youtube.cota_hoje()["usado"] - inicio + 300 > orcamento:
            break
        r = procurar(u)
        feitas += 1
        if r.get("buscas"):
            log(f"Meu nicho de {u['email']}: {r['videos_novos']} vídeos novos, {len(r['achados'])} canais validados")
    return feitas


# ---------------------------------------------------------------- os vídeos do nicho (a tela do Meu nicho)

VIDEOS_DA_TELA = 60


def videos(usuario: dict, limite: int = VIDEOS_DA_TELA, atualizar: bool = True) -> list[dict]:
    """Os vídeos que as buscas do nicho trouxeram, do mais novo para o mais antigo, dentro do período do Formulário.

    `atualizar`: as views dos vídeos com mais de 1 hora de leitura são lidas de novo (1 unidade a cada 50 vídeos):
    a tela mostra o número de agora, não o do dia da busca. Bloqueados pelo ⊘ e palavras proibidas ficam de fora."""
    p = ler(usuario)
    f = p["filtros"]
    corte = (datetime.now(timezone.utc) - timedelta(days=f["dias"])).strftime("%Y-%m-%dT%H:%M:%S")
    linhas = banco.todos(
        "SELECT nv.video_id AS id, nv.busca, nv.estrutura, nv.achado, v.titulo, v.views, v.publicado, v.duracao_s, "
        "v.medido, c.id AS canal_id, c.titulo AS canal, c.foto, c.handle, c.inscritos, c.nicho, c.subnicho, "
        "c.base_longos, c.base_curtos, (SELECT 1 FROM nicho_canais nc WHERE nc.usuario_id=nv.usuario_id "
        "AND nc.canal_id=nv.canal_id) AS validado FROM nicho_videos nv JOIN videos v ON v.id=nv.video_id "
        "LEFT JOIN canais c ON c.id=nv.canal_id WHERE nv.usuario_id=? AND v.publicado >= ? "
        "ORDER BY v.publicado DESC LIMIT ?", usuario["id"], corte, limite * 2)
    # os vídeos novos dos canais de referência: são o modelo, o que eles postam importa. O canal é lido de novo uma
    # vez por dia (umas 3 unidades), e é essa leitura que traz os vídeos novos dele
    refs = [r["id"] for r in p["referencias"] if r.get("id")]
    if refs:
        if atualizar:
            try:
                medir.medir_canais(refs)
            except youtube.SemCota:
                pass
        ja = {l["id"] for l in linhas}
        linhas += [l for l in banco.todos(
            "SELECT v.id, '' AS busca, ? AS estrutura, '' AS achado, v.titulo, v.views, v.publicado, v.duracao_s, "
            "v.medido, c.id AS canal_id, c.titulo AS canal, c.foto, c.handle, c.inscritos, c.nicho, c.subnicho, "
            "c.base_longos, c.base_curtos, 1 AS validado FROM videos v JOIN canais c ON c.id=v.canal_id "
            f"WHERE v.canal_id IN ({','.join('?' * len(refs))}) AND v.publicado >= ? AND v.duracao_s > ?",
            REFERENCIA, *refs, corte, metricas.CURTO_ATE_S) if l["id"] not in ja]
        linhas.sort(key=lambda l: l["publicado"] or "", reverse=True)
    if atualizar:
        velhos = [l["id"] for l in linhas if medir._velho(l["medido"], medir.VIDEO_VALE)]
        if velhos:
            try:
                medir.medir_videos(velhos)
            except youtube.SemCota:
                pass            # sem cota, a tela mostra o último número lido
            agora = {v["id"]: v for v in medir._videos_do_banco(velhos)}
            for l in linhas:
                if l["id"] in agora:
                    l["views"] = agora[l["id"]]["views"]
    filtro = gosto.Filtro(usuario)
    proibidas = [gosto._simples(w) for w in f["proibidas"]]
    saida = []
    for l in linhas:
        if l["id"] in filtro.videos or l["canal_id"] in filtro.canais:
            continue
        if any(w in gosto._simples(l["titulo"]) for w in proibidas):
            continue
        normal = l["base_curtos"] if metricas.curto(l["duracao_s"]) else l["base_longos"]
        saida.append(l | {"nota": metricas.nota_outlier(l["views"], normal),
                          "por_hora": metricas.views_por_hora(l["views"], l["publicado"]),
                          "validado": bool(l["validado"])})
    return saida[:limite]


# ---------------------------------------------------------------- se um título ou um canal é do nicho

def _tokens(texto: str) -> set[str]:
    """As palavras de 3 letras ou mais, sem acento. Contém as de gosto.chaves: a expressão casa contra elas."""
    palavras = set(re.findall(r"[a-z0-9]{3,}", gosto._simples(texto)))
    # o plural conta como o singular: "Why Sharks Never Stop" fala de "shark"
    return palavras | {p[:-1] for p in palavras if len(p) > 3 and p.endswith("s") and not p.endswith("ss")}


def _expressoes(p: dict) -> list[tuple[str, set[str]]]:
    """As expressões do nicho que dizem o assunto (assunto, coisas, lugares e as palavras soltas), cada uma com as
    palavras dela. Uma expressão só casa com um título que tem TODAS: "Private Labels" não casa com "private jet"."""
    saida = []
    for l in ("assunto", "itens", "lugares", "palavras"):
        for o in p["vocab"].get(l, []):
            chaves = gosto.chaves(o) or _tokens(o)       # "dog", "cat": curtas demais para gosto.chaves
            if chaves:
                saida.append((o, chaves))
    return saida


TITULOS_DO_NICHO = 0.15     # o canal é do nicho quando 15% dos títulos (e 2 no mínimo) falam de uma expressão dele


def fala_do_nicho(titulos: list[str], expressoes: list[tuple[str, set[str]]]) -> tuple[set[str], int, bool]:
    """As expressões do nicho que aparecem nos títulos, quantos títulos falam delas e se isso basta para o canal
    ser do nicho."""
    assunto, falam = set(), 0
    for t in titulos:
        do_titulo = _tokens(t)
        casadas = {o for o, chaves in expressoes if chaves <= do_titulo}
        assunto |= casadas
        falam += bool(casadas)
    return assunto, falam, falam >= max(2, TITULOS_DO_NICHO * len(titulos))

