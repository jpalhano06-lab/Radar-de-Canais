"""Alerta: canal dark pequeno com métrica absurda, dos EUA (pedido do usuário em 2026-10-14).

Menos de 4 mil inscritos, sem rosto, dos EUA (o país do canal, ou sem país, e os títulos em inglês) e muita view: o normal
por vídeo de 20 mil ou mais, ou um vídeo com 100 mil ou mais. No menu, um ponto verde pisca quando aparece um canal que
a pessoa ainda não viu."""
from . import banco, gosto, mercado, risco

PADRAO = {"inscritos_max": 4000, "media_min": 20000, "pico_min": 100000}


def _dos_eua(c: dict) -> bool:
    """País EUA (ou sem país) e títulos em inglês: um canal marcado como EUA com títulos em russo não é dos EUA."""
    if (c["pais"] or "") not in mercado.ACEITOS:
        return False
    titulos = [v["titulo"] for v in banco.todos("SELECT titulo FROM videos WHERE canal_id=? ORDER BY views DESC LIMIT 6", c["id"])]
    linguas = [gosto.lingua(t) for t in titulos]
    return bool(linguas) and linguas.count("en") >= len(linguas) / 2


def _arriscado(c: dict) -> bool:
    """Canal que o YouTube costuma desmonetizar (reaproveitado, feito em série, infantil, sensível) não entra no
    Alerta: não vale copiar o que pode perder a monetização amanhã (`risco.avaliar`)."""
    titulos = [v["titulo"] for v in banco.todos("SELECT titulo FROM videos WHERE canal_id=? ORDER BY publicado DESC LIMIT 20", c["id"])]
    return bool(risco.avaliar(titulos))


def canais(usuario_id: int, filtros: dict | None = None) -> list[dict]:
    f = PADRAO | {k: int(v) for k, v in (filtros or {}).items() if k in PADRAO and str(v).isdigit()}
    candidatos = banco.todos(
        "SELECT c.*, (SELECT MAX(views) FROM videos v WHERE v.canal_id=c.id AND v.duracao_s>180) AS pico, "
        "(SELECT visto FROM alertas_vistos a WHERE a.usuario_id=? AND a.canal_id=c.id) AS visto "
        "FROM canais c WHERE c.inscritos IS NOT NULL AND c.inscritos < ? AND c.sem_rosto=1 AND c.base_longos IS NOT NULL",
        usuario_id, f["inscritos_max"])
    saida = [c for c in candidatos
             if ((c["base_longos"] or 0) >= f["media_min"] or (c["pico"] or 0) >= f["pico_min"]) and _dos_eua(c)
             and not mercado.irrelevante(c["nicho"], c["subnicho"]) and not _arriscado(c)]
    # os novos primeiro; depois os dos EUA; depois o tamanho do estouro
    saida.sort(key=lambda c: (c["visto"] is not None, mercado.ordem_pais(c["pais"]), -((c["pico"] or 0) / max(100, c["inscritos"] or 0))))
    return saida


def novos(usuario_id: int) -> int:
    return sum(1 for c in canais(usuario_id) if c["visto"] is None)


def marcar_vistos(usuario_id: int, ids: list[str]) -> None:
    banco.varios("INSERT OR IGNORE INTO alertas_vistos (usuario_id, canal_id, visto) VALUES (?,?,?)",
                 [(usuario_id, i, banco.agora()) for i in ids])
