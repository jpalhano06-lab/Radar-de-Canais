"""Treinamento do algoritmo, dentro do site (pedido do usuário em 2026-10-14, no lugar do "YouTube virgem").

Na primeira vez que a pessoa abre um canal dela: 1) dá 1 a 3 canais de referência; 2) o site mostra vários vídeos
(dos canais de referência, dos parecidos e dos que estouraram no mesmo nicho) e ela marca os que faria (10 a 20) e os
que não faria; 3) com os escolhidos, o Radar aprende as palavras do assunto (com peso), escreve buscas novas e procura
no YouTube. Daí em diante as ideias do canal e o selo 🎯 da extensão seguem esse treino."""
import json
import random
import threading
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import banco, gosto, ia, medir, metricas, perfil, youtube

MINIMO, MAXIMO = 10, 20
_TAREFAS: dict[str, dict] = {}


def estado(usuario_id: int, canal_id: str) -> dict | None:
    t = banco.um("SELECT * FROM treinamentos WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id)
    if not t:
        return None
    return {k: json.loads(t[k]) if k in ("referencias", "positivos", "negativos", "palavras", "termos") else t[k]
            for k in t if k not in ("usuario_id",)}


def _gravar(usuario_id: int, canal_id: str, **dados) -> None:
    atual = estado(usuario_id, canal_id) or {}
    junto = {"referencias": [], "positivos": [], "negativos": [], "palavras": {}, "termos": [], "feito": ""} | \
        {k: v for k, v in atual.items() if k != "canal_id"} | dados
    banco.executar("INSERT OR REPLACE INTO treinamentos (usuario_id, canal_id, referencias, positivos, negativos, palavras, "
                   "termos, feito) VALUES (?,?,?,?,?,?,?,?)", usuario_id, canal_id,
                   *[json.dumps(junto[k], ensure_ascii=False) for k in ("referencias", "positivos", "negativos", "palavras", "termos")],
                   junto["feito"])


def recomecar(usuario_id: int, canal_id: str) -> None:
    banco.executar("DELETE FROM treinamentos WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id)


def referencias(usuario_id: int, canal_id: str, ids: list[str]) -> list[dict]:
    """Mede os canais de referência (uns 3 de cota cada) e guarda. O próprio canal da pessoa entra junto."""
    todos = list(dict.fromkeys([canal_id, *ids]))
    medidos = medir.medir_canais(todos)
    for cid in ids:
        c = medidos.get(cid)
        if c and (not c["nicho"] or not c["subnicho"]):
            perfil.conectar(usuario_id, cid, meu=False)
    _gravar(usuario_id, canal_id, referencias=ids, feito="")
    return [medir._canal_publico(medidos[c]) for c in ids if c in medidos]


SELECT = ("SELECT v.id, v.titulo, v.views, v.publicado, v.duracao_s, c.id AS canal_id, c.titulo AS canal, c.foto, c.handle, "
          "c.inscritos, c.nicho, c.subnicho, c.sem_rosto, c.base_longos AS normal FROM videos v JOIN canais c ON c.id=v.canal_id ")


@youtube.por("treino")
def candidatos(usuario: dict, canal_id: str, excluir: set[str], quantos: int = 30) -> list[dict]:
    """Vídeos para a pessoa escolher: dos canais de referência, dos que estouraram falando do mesmo assunto e do mesmo
    nicho. Sorteados, sem os que ela já viu nesta rodada."""
    t = estado(usuario["id"], canal_id) or {}
    refs = t.get("referencias", [])
    filtro = gosto.Filtro(usuario)
    filtro.linguas = {"outras"}
    pool: dict[str, dict] = {}
    if refs:
        marcas = ",".join("?" * len(refs))
        for v in banco.todos(SELECT + f"WHERE c.id IN ({marcas}) AND v.duracao_s>? ORDER BY v.views DESC LIMIT 120",
                             *refs, metricas.CURTO_ATE_S):
            pool[v["id"]] = v | {"origem": "referência", "peso": 3}
    alvo, nichos, subs = set(), set(), set()
    for cid in [*refs, canal_id]:
        c = banco.um("SELECT nicho, subnicho FROM canais WHERE id=?", cid)
        if c:
            nichos.add(c["nicho"]); subs.add(c["subnicho"])
        for v in banco.todos("SELECT titulo FROM videos WHERE canal_id=? ORDER BY views DESC LIMIT 30", cid):
            alvo |= gosto.chaves(v["titulo"])
    for l in banco.todos(gosto.SELECT_VIDEO + "WHERE o.nota >= 2"):
        if l["id"] in pool:
            continue
        p = gosto.parecenca(l["titulo"], alvo) * 3 + (1 if l["subnicho"] in subs else 0) + (0.5 if l["nicho"] in nichos else 0)
        if p > 0.5:
            pool[l["id"]] = l | {"origem": "parecido", "peso": p}
    lista = [v for v in gosto.por_lingua(list(pool.values()), "ptenes")
             if v["id"] not in excluir and v["canal_id"] != canal_id and filtro.aceita(v)]
    sorteio = random.Random()
    lista.sort(key=lambda v: -sorteio.random() ** (1 / max(0.5, v["peso"])))
    return lista[:quantos]


@youtube.por("treino")
def concluir(usuario: dict, canal_id: str, positivos: list[str], negativos: list[str], aviso=lambda _t: None) -> dict:
    """Aprende as palavras dos escolhidos (com peso), escreve as buscas e procura no YouTube (uns 500 a 600 de cota)."""
    def titulos(ids):
        if not ids:
            return []
        return [v["titulo"] for v in banco.todos(f"SELECT titulo FROM videos WHERE id IN ({','.join('?' * len(ids))})", *ids)]
    bons, ruins = titulos(positivos), titulos(negativos)
    conta = Counter(p for t in bons for p in gosto.chaves(t))
    contra = Counter(p for t in ruins for p in gosto.chaves(t))
    # palavra que aparece nos escolhidos ganha peso; a que só aparece nos recusados fica negativa
    palavras = {p: n for p, n in conta.items()}
    for p, n in contra.items():
        palavras[p] = palavras.get(p, 0) - n * 0.7
    canal = banco.um("SELECT * FROM canais WHERE id=?", canal_id)
    aviso("Escrevendo as buscas com os vídeos que você escolheu…")
    termos = ia.sugerir_termos(canal.get("subnicho") or canal.get("nicho") or canal["titulo"], bons, 5) or \
        [w for w, _ in conta.most_common(3)]
    _gravar(usuario["id"], canal_id, positivos=positivos, negativos=negativos, palavras=palavras, termos=termos)
    depois = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%SZ")
    achados, novos_outliers = [], 0
    for n, termo in enumerate(termos):
        aviso(f"Procurando no YouTube: \"{termo}\" ({n + 1} de {len(termos)})…")
        try:
            achados += youtube.buscar(termo, publicado_depois=depois, duracao="medium" if n % 2 else "long", quantos=30)
        except youtube.SemCota:
            break
    aviso("Medindo os canais achados…")
    ids_canais = [c for c in dict.fromkeys(a["canal_id"] for a in achados) if c != canal_id][:25]
    try:
        canais = medir.medir_canais(ids_canais)
        for v in youtube.videos([a["video_id"] for a in achados if a["canal_id"] in canais]):
            c = canais[v["canal_id"]]
            nota = metricas.nota_outlier(v["views"], c["base_curtos"] if metricas.curto(v["duracao_s"]) else c["base_longos"])
            if nota and nota >= 3:
                banco.executar("INSERT OR REPLACE INTO outliers (video_id, canal_id, nota, achado) VALUES (?,?,?,?)",
                               v["id"], c["id"], nota, banco.agora())
                novos_outliers += 1
    except youtube.SemCota:
        pass
    _gravar(usuario["id"], canal_id, feito=banco.agora())
    return {"termos": termos, "canais": len(ids_canais), "ideias_novas": novos_outliers,
            "palavras": [p for p, _ in sorted(palavras.items(), key=lambda x: -x[1])[:15]]}


def comecar(usuario: dict, canal_id: str, positivos: list[str], negativos: list[str]) -> str:
    tid = uuid.uuid4().hex[:12]
    _TAREFAS[tid] = {"usuario_id": usuario["id"], "estado": "rodando", "passo": "Começando…", "resultado": None, "erro": ""}

    def rodar():
        try:
            _TAREFAS[tid]["resultado"] = concluir(usuario, canal_id, positivos, negativos,
                                                  aviso=lambda t: _TAREFAS[tid].update(passo=t))
            _TAREFAS[tid]["estado"] = "pronto"
        except Exception as erro:
            _TAREFAS[tid].update(estado="erro", erro=str(erro))
    threading.Thread(target=rodar, daemon=True).start()
    return tid


def tarefa(usuario_id: int, tid: str) -> dict | None:
    t = _TAREFAS.get(tid)
    return t if t and t["usuario_id"] == usuario_id else None


def pesos(usuario_id: int, canal_id: str) -> dict[str, float]:
    """As palavras aprendidas no treino, com peso (negativo = assunto que a pessoa recusou), mais o que o 🎯 e os
    canais inscritos no algoritmo ensinaram (`alvos.pesos`)."""
    from . import alvos
    t = estado(usuario_id, canal_id)
    junto = dict(t["palavras"]) if t and t.get("feito") else {}
    for p, n in alvos.pesos(usuario_id, canal_id).items():
        junto[p] = junto.get(p, 0) + n
    return junto
