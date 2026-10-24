"""A página Custos (pedido do usuário em 2026-10-18): quanto cada vídeo, cada provedor (GenAI Pro, OpenRouter, Kie...)
e cada canal gastou, pelo custos_reais.json que a fábrica grava em cada projeto. Arquivo ausente ou quebrado conta
como sem gasto; linha sem provedor vai para "outros"."""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from . import banco

_LIDOS: dict[str, tuple] = {}      # arquivo -> (mtime, linhas)


def linhas(pasta: Path) -> list[dict]:
    arquivo = pasta / "custos_reais.json"
    try:
        # a hora sozinha não serve de marca: duas gravações no mesmo tique do relógio do disco davam a mesma, e a
        # leitura guardada voltava com o conteúdo velho. O tamanho junto já separa os dois casos.
        dados = arquivo.stat()
        marca = (dados.st_mtime, dados.st_size)
    except OSError:
        return []
    if str(arquivo) in _LIDOS and _LIDOS[str(arquivo)][0] == marca:
        return _LIDOS[str(arquivo)][1]
    try:
        brutas = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    saida = []
    for l in brutas if isinstance(brutas, list) else []:
        if not isinstance(l, dict):
            continue
        saida.append({"quando": l.get("quando") or "", "categoria": l.get("categoria") or "outros",
                      "provedor": (l.get("detalhes") or {}).get("provedor") or "outros",
                      "usd": float(l.get("valor_usd") or 0), "cena": (l.get("detalhes") or {}).get("cena")})
    _LIDOS[str(arquivo)] = (marca, saida)
    return saida


def combinar(fabrica: dict | None, reais: list[dict]) -> list[dict]:
    """As linhas de gasto com o total da fábrica (a rota /custos, a mesma dos Resultados). O custos_reais.json só tem a
    narração e as imagens; texto, visão e o juiz a fábrica calcula à parte e lista em modelos_de_texto. Cada tipo de
    gasto é repartido entre os provedores do arquivo (narração → genaipro) ou, sem nenhum, entre os modelos de texto."""
    if not fabrica or not fabrica.get("por_categoria"):
        return reais
    modelos: dict[str, float] = {}
    for m in fabrica.get("modelos_de_texto") or []:
        if float(m.get("custo_usd") or 0) > 0:
            nome = str(m.get("provedor") or "outros").lower()
            modelos[nome] = modelos.get(nome, 0) + float(m["custo_usd"])
    saida = []
    for categoria, total in fabrica["por_categoria"].items():
        total = float(total or 0)
        if total <= 0:
            continue
        donos: dict[str, float] = {}
        for l in reais:
            if l["categoria"] == categoria and l["usd"] > 0:
                donos[l["provedor"]] = donos.get(l["provedor"], 0) + l["usd"]
        donos = donos or modelos or {"outros": 1}
        soma = sum(donos.values())
        saida += [{"quando": "", "categoria": categoria, "provedor": p, "usd": total * v / soma} for p, v in donos.items()]
    return saida


def _somar(itens, chave) -> dict:
    soma: dict[str, float] = {}
    for l in itens:
        soma[l[chave]] = soma.get(l[chave], 0) + l["usd"]
    return {k: round(v, 2) for k, v in sorted(soma.items(), key=lambda kv: -kv[1])}


def resumo(videos: list[dict], dias: int | None, hoje: str | None = None) -> dict:
    """videos: [{"nome", "titulo", "canal", "criado", "minutos", "linhas"}]. Só os criados nos últimos `dias` (None = tudo)."""
    if dias:
        corte = (date.fromisoformat(hoje) if hoje else datetime.now(banco.BRASILIA).date()) - timedelta(days=dias)
        videos = [v for v in videos if (v.get("criado") or "")[:10] > corte.isoformat()]
    todas = [l for v in videos for l in v["linhas"]]
    total = round(sum(l["usd"] for l in todas), 2)
    minutos = sum(v["minutos"] or 0 for v in videos)
    lista = []
    for v in videos:
        usd = round(sum(l["usd"] for l in v["linhas"]), 2)
        lista.append({k: v[k] for k in ("nome", "titulo", "canal", "criado", "minutos")}
                     | {"usd": usd, "usd_por_minuto": round(usd / v["minutos"], 2) if v["minutos"] else None})
    canais: dict[str, list] = {}
    for item in lista:
        canais.setdefault(item["canal"] or "Sem canal", []).append(item["usd"])
    return {"total": total, "videos": len(videos), "media_video": round(total / len(videos), 2) if videos else 0,
            "usd_por_minuto": round(total / minutos, 2) if minutos else 0,
            "por_provedor": _somar(todas, "provedor"), "por_categoria": _somar(todas, "categoria"),
            "por_canal": sorted(({"canal": c, "total": round(sum(u), 2), "media": round(sum(u) / len(u), 2)} for c, u in canais.items()),
                                key=lambda c: -c["total"]),
            "lista": sorted(lista, key=lambda x: x["criado"] or "", reverse=True)}


def detalhe(pasta: Path, fabrica: dict | None = None) -> dict:
    ls = combinar(fabrica, linhas(pasta))
    return {"por_categoria": _somar(ls, "categoria"), "por_provedor": _somar(ls, "provedor"),
            "imagens_ia": sum(1 for l in linhas(pasta) if l["categoria"] == "imagem"), "total": round(sum(l["usd"] for l in ls), 2)}
