"""O que a retenção real do canal ensina, para o próximo roteiro do mesmo canal (pedido do usuário em 2026-11-06).

Antes cada roteiro nascia sem saber como os vídeos anteriores do canal seguraram o público. Aqui o Radar lê, no Studio
conectado, quanta gente ainda assistia em 1 minuto nos vídeos dos últimos 90 dias, separa os que mais e menos seguraram,
e o Claude compara o começo da fala deles. O resultado fica guardado 7 dias e entra no pedido do roteiro.

A comparação é sempre no primeiro minuto, nunca pela retenção média: vídeo curto tem média alta só por ser curto (medido em
2026-11-05, canais parecidos só diferiam quando a duração era diferente). Sem Studio conectado, ou com poucos vídeos, não
há lição, e o roteiro sai como sempre: nada aqui para um pedido.
"""
import json
import time
from datetime import date, timedelta

from . import banco, descricao, roteiro_claude, studio

DIAS = 90
VIDEOS_LIDOS = 14       # cada um é uma chamada à Analytics
MINIMO_DE_VIEWS = 200
MINIMO_DE_VIDEOS = 6
DURACAO_MINIMA = 180
EXTREMOS = 3            # os que mais e os que menos seguraram
VALE_POR = 7 * 86400

SISTEMA = """Você compara o começo de vídeos do mesmo canal do YouTube para achar o que segura o público.
Para cada vídeo vem quanta gente ainda assistia em 1 minuto e o que foi dito nesse minuto. Aponte o que os que seguraram
fazem e os que perderam não fazem: o tipo de abertura, quando a promessa aparece, o que atrasa. Fale de mecanismo, não de
assunto, e não cite nomes dos vídeos. Responda só JSON, em português do Brasil:
{"fazer": ["de 2 a 4 regras curtas"], "evitar": ["de 2 a 4 regras curtas"]}"""


def _em_um_minuto(curva: dict, duracao: float) -> float | None:
    if not curva or not duracao:
        return None
    return curva[min(curva, key=lambda k: abs(k - 60 / duracao))]


def medir(token: str, canal_id: str) -> list[dict]:
    """Os vídeos do canal com a parte do público que ainda assistia em 1 minuto, do que mais segurou para o que menos."""
    hoje = date.today()
    inicio, fim = str(hoje - timedelta(days=DIAS)), str(hoje)
    r = studio._relatorio(token, canal_id, inicio, fim, "views,averageViewDuration,averageViewPercentage", dimensions="video",
                          sort="-views", maxResults=VIDEOS_LIDOS * 2)
    videos = []
    for linha in (r or {}).get("linhas", []):
        pct = linha.get("averageViewPercentage") or 0
        duracao = linha.get("averageViewDuration", 0) / pct * 100 if pct else 0
        if linha.get("views", 0) >= MINIMO_DE_VIEWS and duracao >= DURACAO_MINIMA:
            videos.append({"video": linha["video"], "duracao": duracao})
    medidos = []
    for v in videos[:VIDEOS_LIDOS]:
        curva = studio._relatorio(token, canal_id, inicio, fim, "audienceWatchRatio", dimensions="elapsedVideoTimeRatio", filters=f"video=={v['video']}")
        pontos = {float(l["elapsedVideoTimeRatio"]): l["audienceWatchRatio"] for l in (curva or {}).get("linhas", [])}
        minuto = _em_um_minuto(pontos, v["duracao"])
        if minuto is not None:
            medidos.append({**v, "um_minuto": round(minuto, 3)})
    return sorted(medidos, key=lambda x: -x["um_minuto"])


def _comeco_da_fala(video_id: str) -> str:
    try:
        return " ".join(l["texto"] for l in roteiro_claude.fala_com_tempos(video_id) if l.get("ms", l.get("seg", 0) * 1000) < 60000)[:1500]
    except Exception:  # noqa: BLE001 (vídeo sem legenda fica de fora da comparação)
        return ""


def _pedido(extremos: list[dict]) -> str:
    return "\n\n".join(f"Vídeo que {x['grupo']}: {round(x['um_minuto'] * 100)}% do público em 1 minuto.\nFala do primeiro minuto:\n{x['fala']}" for x in extremos)


def aprender(usuario_id: int, canal_id: str) -> dict:
    """{"fazer", "evitar", "videos"}, ou {} quando não dá para comparar."""
    medidos = medir(studio._token(usuario_id, canal_id), canal_id)
    if len(medidos) < MINIMO_DE_VIDEOS:
        return {}
    extremos = [{**v, "grupo": grupo} for grupo, lista in (("segurou", medidos[:EXTREMOS]), ("perdeu", medidos[-EXTREMOS:])) for v in lista]
    for x in extremos:
        x["fala"] = _comeco_da_fala(x["video"])
    extremos = [x for x in extremos if x["fala"]]
    if len({x["grupo"] for x in extremos}) < 2:
        return {}
    dados = descricao._json_do_claude(roteiro_claude._claude(SISTEMA, _pedido(extremos)))
    return {"fazer": [str(x) for x in dados.get("fazer") or []][:4], "evitar": [str(x) for x in dados.get("evitar") or []][:4], "videos": len(medidos)}


def licoes(usuario_id: int, canal_id: str, novo: bool = False) -> dict:
    """As lições guardadas, ou lidas de novo depois de 7 dias. Sem Studio conectado, vazio. Nunca levanta erro."""
    if not canal_id or not banco.um("SELECT 1 FROM studio WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id):
        return {}
    chave = f"retencao:{usuario_id}:{canal_id}"
    linha = banco.um("SELECT dados FROM traducoes WHERE chave=?", chave)
    guardado = json.loads(linha["dados"]) if linha else {}
    if not novo and time.time() - guardado.get("quando", 0) < VALE_POR:
        return guardado.get("licoes") or {}
    try:
        achadas = aprender(usuario_id, canal_id)
    except Exception as erro:  # noqa: BLE001
        print("as lições de retenção não saíram:", str(erro)[:160])
        return guardado.get("licoes") or {}
    banco.executar("INSERT OR REPLACE INTO traducoes (chave, dados, criado) VALUES (?,?,?)", chave,
                   json.dumps({"quando": time.time(), "licoes": achadas}, ensure_ascii=False), banco.agora())
    return achadas


def texto(licao: dict) -> str:
    fazer, evitar = licao.get("fazer") or [], licao.get("evitar") or []
    if not fazer and not evitar:
        return ""
    return ("\nO que a retenção real deste canal ensina (comparação dos vídeos que mais e menos seguraram o público no primeiro "
            f"minuto, {licao.get('videos', '')} vídeos medidos). Siga, principalmente na abertura:\n"
            + "".join(f"- Faça: {x}\n" for x in fazer) + "".join(f"- Evite: {x}\n" for x in evitar))
