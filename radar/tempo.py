"""O ajuste do tempo do vídeo: o Radar compara o tempo pedido com o tempo que a fábrica entregou e corrige quantas
palavras pedir ao Claude na próxima vez.

Pedido do usuário em 2026-10-18: "pediu 15 min e o vídeo saiu com 12, então ele ajusta para aumentar na próxima".
Cada voz fala num ritmo, então a medida é por perfil da fábrica (a voz do canal): palavras enviadas ÷ minutos da
narração gravada. Vale a mediana dos últimos vídeos daquela voz; sem nenhum, a mesma língua; sem nada, 150 por minuto."""
import json
import statistics
import time

from . import fabrica_api, roteiro_claude

PADRAO = roteiro_claude.PALAVRAS_POR_MINUTO
ULTIMOS = 5
_CACHE: dict = {"quando": 0.0, "duracoes": {}}


def _duracoes() -> dict[str, float]:
    """A duração da narração de cada projeto da fábrica (segundos), guardada por um minuto."""
    if time.time() - _CACHE["quando"] > 60:
        try:
            projetos = fabrica_api._pedir("GET", "/api/projetos")["projetos"]
            _CACHE["duracoes"] = {p["nome"]: float(p["duracao"]) for p in projetos
                                  if p.get("tem_narracao") and (p.get("duracao") or 0) > 30}
        except Exception:
            pass                    # fábrica desligada: fica com o que já sabia
        _CACHE["quando"] = time.time()
    return _CACHE["duracoes"]


def medicoes(usuario_id: int) -> list[dict]:
    """Os vídeos do Radar que já têm narração: o pedido, o entregue e o ritmo real da voz. Os mais novos primeiro."""
    duracoes = _duracoes()
    saida = []
    for meta in sorted(roteiro_claude.PASTA.glob("*/roteiro.json"), reverse=True):
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        f = m.get("fabrica") or {}
        segundos = duracoes.get(f.get("projeto", ""))
        palavras = f.get("palavras") or m.get("palavras") or 0
        if m.get("usuario_id") != usuario_id or not segundos or palavras < 100:
            continue
        saida.append({"titulo": m.get("titulo", ""), "perfil": f.get("perfil", ""), "lingua": m.get("lingua", ""),
                      "pedido_min": m.get("minutos"), "entregue_min": round(segundos / 60, 1), "palavras": palavras,
                      "ppm": round(palavras / (segundos / 60))})
    return saida


def ritmo(usuario_id: int, perfil: str = "", lingua: str = "") -> dict:
    """Quantas palavras por minuto pedir para esta voz, e de onde veio o número."""
    todas = medicoes(usuario_id)
    base = [m for m in todas if perfil and m["perfil"] == perfil][:ULTIMOS] or \
           [m for m in todas if lingua and m["lingua"] == lingua][:ULTIMOS]
    if not base:
        return {"ppm": PADRAO, "medidos": 0, "padrao": PADRAO, "exemplo": None}
    ppm = int(min(260, max(100, statistics.median(m["ppm"] for m in base))))
    return {"ppm": ppm, "medidos": len(base), "padrao": PADRAO, "exemplo": base[0],
            "de": "voz" if base[0]["perfil"] == perfil else "lingua"}
