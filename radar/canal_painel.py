"""A página de cada canal da pessoa (pedido do usuário em 2026-10-15): o painel (números, os vídeos que mais renderam,
quanto o canal gastou na fábrica e o custo por view), a agenda de postagem com o aviso de canal parado, os concorrentes
para acompanhar e, na fábrica, o texto fixo da descrição e os shorts do canal.

O texto fixo e os shorts ficam no perfil da fábrica do canal (perfis/canal-NOME.yaml: `publicacao.texto_fixo` e
`shorts`), que a fábrica lê em todo vídeo. Quem escreve o yaml é o Python da própria fábrica (ela tem a biblioteca de
yaml; o Radar não), só nos perfis de canal (canal-*), nunca no perfil base."""
import json
import shutil
import subprocess
from datetime import datetime, timezone

from . import banco, fabrica_api, metricas, producao, roteiro_claude, youtube

AGENDA_PADRAO = {"por_semana": 3, "dias": []}
DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MAX_CONCORRENTES = 5


def _dias_desde(data: str | None) -> int | None:
    if not data:
        return None
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(data.replace("Z", "+00:00"))).days
    except ValueError:
        return None


def _com_nota(c: dict, videos: list[dict]) -> list[dict]:
    for v in videos:
        normal = c["base_curtos"] if metricas.curto(v["duracao_s"]) else c["base_longos"]
        v["nota"] = metricas.nota_outlier(v["views"], normal)
    return videos


def _gasto(usuario_id: int, titulo: str) -> dict:
    """Quanto os vídeos prontos deste canal gastaram na fábrica, e as views dos que foram publicados."""
    try:
        prontos = fabrica_api.producoes()["prontos"]
    except fabrica_api.SemFabrica:
        return {"fabrica": False}
    movidos = {l["projeto"]: l["canal"] for l in banco.todos("SELECT projeto, canal FROM resultado_canal WHERE usuario_id=?", usuario_id)}
    manuais = {l["projeto"]: l["video_id"] for l in banco.todos("SELECT projeto, video_id FROM resultado_publicado WHERE usuario_id=?", usuario_id)}
    do_canal = [p for p in prontos if (movidos.get(p["nome"]) or p["canal"]) == titulo]
    total, ids = 0.0, []
    for p in do_canal:
        try:
            total += fabrica_api.custo(p["nome"]).get("total_usd") or 0
        except fabrica_api.SemFabrica:
            pass
        vid = (p.get("publicado") or {}).get("video_id") or manuais.get(p["nome"])
        if vid and vid != "-":
            ids.append(vid)
    views = 0
    if ids:
        try:
            views = sum(v["views"] or 0 for v in youtube.videos(ids))
        except youtube.SemCota:
            views = 0
    return {"fabrica": True, "videos": len(do_canal), "publicados": len(ids), "gasto_usd": round(total, 2),
            "views_publicados": views, "custo_por_mil_views": round(total / views * 1000, 2) if views else None}


def para_postar(usuario_id: int, titulo: str) -> list[dict]:
    """Os vídeos prontos deste canal que ainda não foram publicados, com o kit de publicação da fábrica (título,
    descrição e tags do publicacao.json), para levar à postagem no YouTube Studio."""
    try:
        prontos = fabrica_api.producoes()["prontos"]
    except fabrica_api.SemFabrica:
        return []
    movidos = {l["projeto"]: l["canal"] for l in banco.todos("SELECT projeto, canal FROM resultado_canal WHERE usuario_id=?", usuario_id)}
    postados: dict[str, set] = {}
    for l in banco.todos("SELECT projeto, item FROM resultado_postado WHERE usuario_id=?", usuario_id):
        postados.setdefault(l["projeto"], set()).add(l["item"])
    links = {l["projeto"] for l in banco.todos("SELECT projeto FROM resultado_publicado WHERE usuario_id=? AND video_id<>'-'", usuario_id)}
    tudo_antigo = {l["projeto"] for l in banco.todos("SELECT projeto FROM resultado_publicado WHERE usuario_id=? AND video_id='-'", usuario_id)}
    saida = []
    for p in prontos:
        if (movidos.get(p["nome"]) or p["canal"]) != titulo:
            continue
        itens = {"video"} | {s["id"] for s in (p.get("shorts") or [])}
        feitos = postados.get(p["nome"], set()) | ({"video"} if p.get("publicado") or p["nome"] in links else set())
        antigo = p["nome"] in tudo_antigo and p["nome"] not in postados     # "Postei tudo" de antes do item por item
        if itens <= feitos or antigo:
            continue        # o vídeo e todos os shorts já foram postados
        try:
            kit = json.loads((roteiro_claude.FABRICA / "projetos" / p["nome"] / "publicacao.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            kit = {}
        saida.append({"nome": p["nome"], "titulo": kit.get("titulo") or p["titulo"], "capa": p["capa"], "duracao": p["duracao"],
                      "criado": p["criado"], "shorts": p.get("shorts") or [], "postados": sorted(feitos), "descricao": kit.get("descricao") or "",
                      "tags": ", ".join(kit.get("tags") or []) if isinstance(kit.get("tags"), list) else str(kit.get("tags") or "")})
    return saida


def painel(usuario_id: int, canal_id: str) -> dict:
    c = banco.um("SELECT * FROM canais WHERE id=?", canal_id) or {}
    cfg = producao.config(usuario_id, canal_id)
    agenda = AGENDA_PADRAO | (cfg.get("agenda") or {})
    top = _com_nota(c, banco.todos("SELECT id, titulo, views, publicado, duracao_s FROM videos WHERE canal_id=? "
                                   "ORDER BY views DESC LIMIT 5", canal_id)) if c else []
    ultimo = c.get("ultimo_video") or (banco.um("SELECT MAX(publicado) AS p FROM videos WHERE canal_id=?", canal_id) or {}).get("p")
    dias_sem = _dias_desde(ultimo)
    intervalo = 7 / max(1, int(agenda["por_semana"]))
    concorrentes = []
    for cid in cfg.get("concorrentes") or []:
        k = banco.um("SELECT * FROM canais WHERE id=?", cid)
        if not k:
            continue
        recentes = _com_nota(k, banco.todos("SELECT id, titulo, views, publicado, duracao_s FROM videos WHERE canal_id=? "
                                            "ORDER BY publicado DESC LIMIT 6", cid))
        estouro = next((v for v in recentes if (v["nota"] or 0) >= 3 and (_dias_desde(v["publicado"]) or 99) <= 14), None)
        concorrentes.append({"id": cid, "titulo": k["titulo"], "foto": k["foto"], "inscritos": k["inscritos"],
                             "normal": k["base_longos"], "ultimo": recentes[0] if recentes else None, "estourou": estouro})
    return {"canal": {"titulo": c.get("titulo"), "inscritos": c.get("inscritos"), "ganho_7d": c.get("ganho_7d"),
                      "videos_total": c.get("videos_total"), "views_total": c.get("views_total"), "normal": c.get("base_longos")},
            "top": top, "agenda": agenda, "dias": DIAS, "dias_sem_video": dias_sem,
            "atrasado": dias_sem is not None and dias_sem > intervalo * 1.5, "intervalo_dias": round(intervalo, 1),
            "concorrentes": concorrentes, "gasto": _gasto(usuario_id, c.get("titulo", "")),
            "para_postar": para_postar(usuario_id, c.get("titulo", ""))}


def salvar_agenda(usuario_id: int, canal_id: str, dados: dict) -> dict:
    agenda = {"por_semana": max(1, min(21, int(dados.get("por_semana") or 3))),
              "dias": [d for d in dados.get("dias", []) if d in DIAS]}
    return producao.salvar(usuario_id, canal_id, producao.config(usuario_id, canal_id) | {"agenda": agenda})


def concorrente(usuario_id: int, canal_id: str, ref_id: str, ligar: bool) -> dict:
    cfg = producao.config(usuario_id, canal_id)
    lista = [x for x in (cfg.get("concorrentes") or []) if x != ref_id]
    if ligar:
        if len(lista) >= MAX_CONCORRENTES:
            raise ValueError(f"No máximo {MAX_CONCORRENTES} concorrentes por canal.")
        lista.append(ref_id)
    return producao.salvar(usuario_id, canal_id, cfg | {"concorrentes": lista})


# ---------------------------------------------------------------- o perfil da fábrica do canal

_CODIGO = r'''
import json, pathlib, sys, yaml
arquivo = pathlib.Path(sys.argv[1]); pedido = json.loads(sys.argv[2])
texto = arquivo.read_text(encoding="utf-8")
dados = yaml.safe_load(texto) or {}
if pedido.get("escrever"):
    pub = dados.get("publicacao") or {}
    pub["texto_fixo"] = str(pedido.get("texto_fixo", ""))[:1500]
    dados["publicacao"] = pub
    shorts = dados.get("shorts") or {}
    shorts["ativo"] = bool(pedido.get("shorts_ativo", True))
    shorts["quantidade"] = max(1, min(5, int(pedido.get("shorts_quantidade") or 3)))
    dados["shorts"] = shorts
    cabeca = []
    for linha in texto.splitlines(True):
        if not linha.startswith("#"):
            break
        cabeca.append(linha)
    arquivo.write_text("".join(cabeca) + yaml.safe_dump(dados, allow_unicode=True, sort_keys=False), encoding="utf-8")
shorts = dados.get("shorts") or {}
print(json.dumps({"texto_fixo": (dados.get("publicacao") or {}).get("texto_fixo") or "",
                  "shorts_ativo": shorts.get("ativo", True), "shorts_quantidade": shorts.get("quantidade", 3)}, ensure_ascii=False))
'''


def perfil_fabrica(usuario_id: int, canal_id: str, novo: dict | None = None) -> dict:
    """Lê (ou escreve) o texto fixo da descrição e os shorts no perfil da fábrica do canal."""
    cfg = producao.config(usuario_id, canal_id)
    perfil = cfg.get("perfil") or ""
    if not perfil.startswith("canal-"):
        raise ValueError("Este canal ainda não tem o perfil próprio na fábrica. Escolha a voz dele na configuração (o perfil é criado junto).")
    arquivo = roteiro_claude.FABRICA / "perfis" / f"{perfil}.yaml"
    if not arquivo.exists():
        raise ValueError(f"O perfil {perfil} não está na pasta da fábrica.")
    pedido = {"escrever": novo is not None, **(novo or {})}
    r = subprocess.run([shutil.which("uv"), "run", "--no-sync", "python", "-c", _CODIGO, str(arquivo), json.dumps(pedido, ensure_ascii=False)],
                       cwd=roteiro_claude.FABRICA, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if r.returncode != 0:
        raise ValueError("A fábrica não conseguiu ler o perfil: " + (r.stderr or "")[-300:])
    return json.loads(r.stdout.strip().splitlines()[-1]) | {"perfil": perfil}
