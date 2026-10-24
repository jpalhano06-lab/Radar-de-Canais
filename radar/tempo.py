"""O ajuste do tempo do vídeo: o Radar compara o tempo pedido com o tempo que a fábrica entregou e corrige quantas
palavras pedir ao Claude na próxima vez.

Pedido do usuário em 2026-10-18: "pediu 15 min e o vídeo saiu com 12, então ele ajusta para aumentar na próxima".
Cada voz fala num ritmo, então a medida é por perfil da fábrica (a voz do canal): palavras enviadas ÷ minutos do
vídeo entregue. Vale a mediana dos últimos vídeos daquela voz; sem nenhum, a mesma língua; sem nada, 150 por minuto.

Pedido do usuário em 2026-10-22: "sempre que ele gere um roteiro ele veja o resultado que deu o vídeo, para saber se
está acertando ou errando; a margem de erro tem que ser no máximo de um minuto e meio para cima ou para baixo".
Por isso:

- **A medida vem do disco**, do `alinhamento.json` da pasta do projeto (mais a abertura do `render/linha.json`, que é
  tempo de vídeo sem narração). Antes vinha só da API da fábrica: com a fábrica desligada o Radar não media nada,
  caía nas 150 palavras por minuto do padrão e errava feio justo nas vozes lentas (as de inglês falam umas 135).
- **Cada roteiro guarda o que deu** (`medido` no `roteiro.json`): o tempo entregue e o erro em minutos. Assim o
  histórico não se perde quando a pasta do projeto sai do computador.
- **O acerto é contado**: quantos dos últimos vídeos daquela voz ficaram dentro de 1 min 30 s, e o erro médio.
- **A conta fecha pelas palavras PEDIDAS, não pelas escritas.** O Claude escreve mais do que se pede (nos vídeos
  medidos, de 0 a 27% a mais). Medindo "palavras escritas ÷ minutos" o Radar aprendia só a voz e repetia o erro do
  excesso todo vídeo. Agora o número que manda no próximo pedido é `ppm_alvo` = palavras **pedidas** ÷ minutos
  entregues: ele engloba a voz e a mania do Claude de esticar, então o próximo roteiro cai dentro da margem e vai
  melhorando a cada vídeo. O `ppm` continua existindo, para mostrar na tela o ritmo real da voz.
"""
import json
import statistics
import time

from . import fabrica_api, roteiro_claude

PADRAO = roteiro_claude.PALAVRAS_POR_MINUTO
ULTIMOS = 5
MARGEM_MIN = 1.5        # o erro que o usuário aceita: um minuto e meio para cima ou para baixo
_CACHE: dict = {"quando": 0.0, "duracoes": {}}


def _do_disco(nome: str) -> float | None:
    """Os segundos do vídeo entregue: a narração alinhada mais a abertura que o render põe na frente."""
    pasta = roteiro_claude.FABRICA / "projetos" / nome
    try:
        segundos = float(json.loads((pasta / "alinhamento.json").read_text(encoding="utf-8")).get("duracao") or 0)
    except (OSError, ValueError, TypeError):
        return None
    if segundos <= 30:
        return None
    try:
        segundos += float(json.loads((pasta / "render" / "linha.json").read_text(encoding="utf-8")).get("atraso") or 0)
    except (OSError, ValueError, TypeError):
        pass
    return segundos


def _da_api() -> dict[str, float]:
    """O que a fábrica ligada sabe (reserva para os projetos que não estão mais neste computador), por um minuto."""
    if time.time() - _CACHE["quando"] > 60:
        try:
            projetos = fabrica_api._pedir("GET", "/api/projetos")["projetos"]
            _CACHE["duracoes"] = {p["nome"]: float(p["duracao"]) for p in projetos
                                  if p.get("tem_narracao") and (p.get("duracao") or 0) > 30}
        except Exception:
            pass                    # fábrica desligada: fica com o que já sabia
        _CACHE["quando"] = time.time()
    return _CACHE["duracoes"]


def _guardar_medida(meta_arquivo, meta: dict, medida: dict) -> None:
    """Grava no roteiro.json o que o vídeo deu, para o histórico não depender da pasta do projeto."""
    if (meta.get("medido") or {}).get("entregue_min") == medida["entregue_min"]:
        return
    try:
        meta["medido"] = medida
        meta_arquivo.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def medicoes(usuario_id: int) -> list[dict]:
    """Os vídeos do Radar que já ficaram prontos: o pedido, o entregue, o erro e o ritmo real da voz.

    Os mais novos primeiro. Um roteiro que ainda não virou vídeo não entra."""
    da_api = _da_api()
    saida = []
    for arquivo in sorted(roteiro_claude.PASTA.glob("*/roteiro.json"), reverse=True):
        try:
            m = json.loads(arquivo.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if m.get("usuario_id") != usuario_id:
            continue
        f = m.get("fabrica") or {}
        projeto = f.get("projeto", "")
        guardado = m.get("medido") or {}
        segundos = (_do_disco(projeto) if projeto else None) or da_api.get(projeto) or guardado.get("segundos")
        palavras = f.get("palavras") or m.get("palavras") or 0
        pedido = m.get("minutos") or 0
        if not segundos or palavras < 100:
            continue
        entregue = round(segundos / 60, 1)
        # o que foi pedido ao Claude naquele dia (minutos x o ppm daquele momento); sem isso, o que ele escreveu
        pedidas = round(pedido * ((m.get("ritmo") or {}).get("ppm") or 0)) or palavras
        medida = {"segundos": round(segundos, 1), "entregue_min": entregue,
                  "erro_min": round(entregue - pedido, 1) if pedido else None}
        _guardar_medida(arquivo, m, medida)
        saida.append({"titulo": m.get("titulo", ""), "perfil": f.get("perfil", ""), "lingua": m.get("lingua", ""),
                      "pedido_min": pedido, "entregue_min": entregue, "palavras": palavras,
                      "palavras_pedidas": pedidas, "erro_min": medida["erro_min"],
                      "dentro": medida["erro_min"] is not None and abs(medida["erro_min"]) <= MARGEM_MIN,
                      "ppm": round(palavras / (segundos / 60)),
                      "ppm_alvo": round(pedidas / (segundos / 60))})
    return saida


def _acerto(base: list[dict]) -> dict:
    """Quantos dos últimos vídeos desta voz ficaram dentro da margem, e o quanto o Radar erra em média."""
    com_pedido = [m for m in base if m["erro_min"] is not None]
    if not com_pedido:
        return {"total": 0, "dentro": 0, "erro_medio": None, "margem": MARGEM_MIN}
    return {"total": len(com_pedido), "dentro": sum(1 for m in com_pedido if m["dentro"]),
            "erro_medio": round(statistics.fmean(m["erro_min"] for m in com_pedido), 1),
            "pior": max(com_pedido, key=lambda m: abs(m["erro_min"])), "margem": MARGEM_MIN}


def ritmo(usuario_id: int, perfil: str = "", lingua: str = "") -> dict:
    """Quantas palavras por minuto pedir para esta voz, de onde veio o número e se ele está acertando."""
    todas = medicoes(usuario_id)
    da_voz = [m for m in todas if perfil and m["perfil"] == perfil][:ULTIMOS]
    base = da_voz or [m for m in todas if lingua and m["lingua"] == lingua][:ULTIMOS]
    if not base:
        return {"ppm": PADRAO, "ppm_alvo": PADRAO, "medidos": 0, "padrao": PADRAO, "exemplo": None, "de": "padrao",
                "acerto": _acerto([]), "ultimos": []}
    limites = lambda x: int(min(260, max(90, x)))
    ppm = limites(statistics.median(m["ppm"] for m in base))
    return {"ppm": ppm, "ppm_alvo": limites(statistics.median(m["ppm_alvo"] for m in base)),
            "medidos": len(base), "padrao": PADRAO, "exemplo": base[0],
            "de": "voz" if da_voz else "lingua", "acerto": _acerto(base),
            "ultimos": [{k: m[k] for k in ("titulo", "pedido_min", "entregue_min", "erro_min", "dentro")} for m in base]}
