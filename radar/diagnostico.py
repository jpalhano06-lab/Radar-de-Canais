"""O Diagnóstico do Acompanhar (pedido do usuário em 2026-10-18, "a quantidade de IA"): de onde veio o material de
cada cena (filmagem real, imagem de IA ou Animation IA), as etapas da produção com o tempo de cada uma e o log.
Tudo lido dos arquivos que a fábrica já grava no projeto (cenas.json, criacao.json); arquivo ausente ou pela metade
(o vídeo começando) vira "pendente", nunca erro."""
import json
import re
from pathlib import Path

FONTES_ANIMACAO = {"animation_ai", "motion_ia"}

# as 6 etapas da tela e as etapas da fábrica que entram em cada uma
ETAPAS = [("roteiro", "Roteiro", {"mapa"}), ("narracao", "Narração", {"narracao"}), ("cenas", "Cenas", {"cenas"}),
          ("material", "Material", {"midia", "conferir"}), ("imagens", "Imagens de IA", {"imagens", "animacoes", "motion"}),
          ("montagem", "Montagem", {"render", "concluido"})]
# o "Tempo por etapa" do log da fábrica, por palavra do nome
TEMPOS = [("roteiro", ("mapa do roteiro",)), ("narracao", ("narração",)), ("cenas", ("cenas",)),
          ("material", ("acervo", "conferência", "sem imagens repetidas")), ("imagens", ("imagens de ia", "anima")),
          ("montagem", ("render", "trilha"))]


def _json(arquivo: Path) -> dict:
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def origem_da_cena(cena: dict) -> str:
    fonte = (cena.get("midia") or {}).get("fonte")
    if fonte in FONTES_ANIMACAO:
        return "animacao"
    if fonte:                 # qualquer banco: pexels, wikimedia, pixabay, inaturalist, unsplash, nypl, smithsonian...
        return "real"
    if cena.get("tipo") == "ia" or cena.get("sem_midia_real"):   # a imagem de IA não fica em "midia"
        return "imagem_ia"
    return "pendente"


def contagem(pasta: Path) -> dict:
    cenas = _json(pasta / "cenas.json").get("cenas") or []
    conta = {"total": len(cenas), "real": 0, "imagem_ia": 0, "animacao": 0, "pendente": 0}
    for c in cenas:
        conta[origem_da_cena(c)] += 1
    feitas = conta["total"] - conta["pendente"]
    conta["pct_ia"] = round((conta["imagem_ia"] + conta["animacao"]) / feitas * 100, 1) if feitas else 0
    return conta


def _segundos(texto: str) -> int:
    m = re.fullmatch(r"(?:(\d+)h)?\s*(?:(\d+)min)?\s*(?:(\d+)s)?", texto.strip())
    return (int(m[1] or 0) * 3600 + int(m[2] or 0) * 60 + int(m[3] or 0)) if m else 0


def _formatar(s: int) -> str:
    if not s:
        return ""
    return f"{s // 60}min{s % 60:02d}s" if s >= 60 else f"{s}s"


def _tempos(logs: list[str]) -> dict[str, int]:
    linha = next((l for l in reversed(logs) if "Tempo por etapa:" in l), "")
    soma: dict[str, int] = {}
    for parte in linha.split("Tempo por etapa:", 1)[-1].split(";"):
        m = re.match(r"\s*(.+?)\s+((?:\d+h)?\s*(?:\d+min)?\s*(?:\d+s)?)\s*$", parte)
        if not m or not m[2].strip():
            continue
        nome = m[1].lower()
        if "esperando" in nome:
            continue
        etapa = next((e for e, palavras in TEMPOS if any(p in nome for p in palavras)), None)
        if etapa:
            soma[etapa] = soma.get(etapa, 0) + _segundos(m[2])
    return soma


def etapas(pasta: Path, status: dict) -> dict:
    criacao = _json(pasta / "criacao.json")
    feitas = set(criacao.get("feitas") or [])
    agora = status.get("etapa") or criacao.get("etapa") or ""
    if status.get("status") == "renderizando":
        agora = "render"
    pronto = (pasta / "final.mp4").exists()
    tempos = _tempos([l for l in criacao.get("logs") or [] if isinstance(l, str)])
    lista = []
    for eid, nome, da_fabrica in ETAPAS:
        if eid == "montagem" and pronto:
            estado = "feita"
        elif agora in da_fabrica:
            estado = "agora"
        elif feitas & da_fabrica:
            estado = "feita"
        else:
            estado = "falta"
        lista.append({"id": eid, "nome": nome, "estado": estado, "tempo": _formatar(tempos.get(eid, 0))})
    return {"lista": lista, "mensagem": status.get("mensagem") or criacao.get("mensagem") or "",
            "passo": status.get("passo_atual") or criacao.get("passo_atual") or 0,
            "total": status.get("total_passos") or criacao.get("total_passos") or 0}


def blocos(fila_itens: list[dict], producoes: dict) -> dict:
    """Os blocos da esquerda do Acompanhar, cada vídeo num só: precisa de você, produzindo, na fila, entrada e os
    projetos da fábrica parados fora da fila. O pedido da fila que já está na fábrica leva o andamento de lá."""
    andamento = {p["nome"]: p for p in producoes.get("andamento", [])}
    saida = {k: [] for k in ("precisa_voce", "produzindo", "na_fila", "entrada", "parados")}
    da_fila = set()
    for f in fila_itens:
        if f["estado"] in ("entregue", "cancelado"):
            continue
        p = andamento.get(f["projeto"]) if f["projeto"] else None
        if p:
            da_fila.add(f["projeto"])
        item = {"chave": f"fila-{f['id']}", "tipo": "fila", "id": f["id"], "projeto": f["projeto"],
                "titulo": f["pedido"].get("titulo", ""), "canal_id": f["pedido"].get("canal_id", ""), "estado": f["estado"],
                "passo": f.get("passo", ""), "erro": f.get("erro", ""), "criado": f.get("criado", ""),
                "progresso": (p or {}).get("progresso") or 0, "mensagem": (p or {}).get("mensagem") or f.get("passo", ""),
                "capa": (p or {}).get("capa", ""), "canal": (p or {}).get("canal", "")}
        if f["estado"] in ("sua_vez", "erro") or (p and p.get("precisa_voce")):
            saida["precisa_voce"].append(item)
        elif f["estado"] in ("escrevendo", "enviando", "produzindo"):
            saida["produzindo"].append(item)
        else:
            saida[f["estado"]].append(item)
    for nome, p in andamento.items():
        if nome in da_fila:
            continue
        item = {"chave": nome, "tipo": "fabrica", "projeto": nome, "titulo": p.get("titulo", nome), "canal": p.get("canal", ""),
                "progresso": p.get("progresso") or 0, "mensagem": p.get("mensagem", ""), "criado": p.get("criado", ""),
                "capa": p.get("capa", ""), "status": p.get("status", "")}
        if p.get("precisa_voce") or p.get("status") == "erro":
            saida["precisa_voce"].append(item | {"estado": "precisa_voce"})
        elif p.get("rodando"):
            saida["produzindo"].append(item | {"estado": "produzindo"})
        else:
            saida["parados"].append(item | {"estado": "parado"})
    saida["numeros"] = {"produzindo": len(saida["produzindo"]), "na_fila": len(saida["na_fila"]),
                        "precisa_voce": len(saida["precisa_voce"])}
    return saida


def _tipo(texto: str) -> str:
    t = texto.lower()
    contornado = any(p in t for p in ("seguindo", "tentando de novo", "tentando outra", "reserva", "volta sozinh"))
    if ("erro" in t or "falhou" in t or "✕" in t) and not contornado:
        return "erro"
    if "aviso" in t or "⚠" in t or contornado:
        return "aviso"
    if "pronto" in t or "pronta" in t or "concluído" in t or "concluida" in t or "concluída" in t or "✓" in t:
        return "concluido"
    return "info"


def log(pasta: Path, tipo: str = "todos") -> list[dict]:
    linhas = [{"texto": l.strip(), "tipo": _tipo(l)} for l in _json(pasta / "criacao.json").get("logs") or []
              if isinstance(l, str) and l.strip()]
    return linhas if tipo == "todos" else [l for l in linhas if l["tipo"] == tipo]
