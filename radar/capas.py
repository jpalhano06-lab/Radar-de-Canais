"""Capas parecidas: a impressão digital de cada capa que estourou, para achar as que se parecem com a de um vídeo.

A impressão é um dHash de 64 bits: a capa em cinza, encolhida para 9x8, e cada bit diz se um ponto é mais claro que o
vizinho. Capas com a mesma composição dão bits parecidos, e a distância entre duas é quantos bits mudam. Capa de vídeo
apagado fica sem impressão e não é tentada de novo.

O índice cobre os outliers do banco, da maior nota para a menor, e cresce aos poucos em `iniciar`.
"""
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from PIL import Image

from . import banco

BITS = 64
MASCARA = (1 << BITS) - 1
LOTE = 90
AO_MESMO_TEMPO = 6
PAUSA = 15
PARECIDO_MINIMO = 85     # capas sorteadas sem nada em comum chegam a 72: abaixo disso é ruído
TENTAR_DEPOIS = object()    # a rede falhou: isso não diz nada sobre a capa, e ela não pode ficar marcada como apagada


def impressao(imagem: bytes) -> int:
    """O dHash da imagem, como inteiro com sinal: o SQLite guarda até 63 bits sem sinal."""
    cinza = Image.open(io.BytesIO(imagem)).convert("L").resize((9, 8), Image.LANCZOS)
    pontos = list(cinza.getdata())
    valor = 0
    for linha in range(8):
        for coluna in range(8):
            valor = valor << 1 | (pontos[linha * 9 + coluna] > pontos[linha * 9 + coluna + 1])
    return valor - (1 << BITS) if valor >= 1 << (BITS - 1) else valor


def parecenca(a: int, b: int) -> int:
    """De 0 a 100: 100 é a mesma composição."""
    return round(100 * (1 - ((a ^ b) & MASCARA).bit_count() / BITS))


def _baixar(video_id: str):
    """A impressão da capa, None se o vídeo foi apagado (404) ou TENTAR_DEPOIS se a resposta não disse nada."""
    try:
        r = httpx.get(f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg", timeout=12)
        if r.status_code == 404:
            return None
        return impressao(r.content) if r.status_code == 200 else TENTAR_DEPOIS
    except (httpx.HTTPError, OSError):
        return TENTAR_DEPOIS


def preencher(lote: int = LOTE, baixar=_baixar) -> int:
    """Um pedaço dos outliers sem impressão. Devolve quantos olhou: zero quer dizer que acabou."""
    ids = [l["video_id"] for l in banco.todos("SELECT o.video_id FROM outliers o LEFT JOIN capas k ON k.video_id=o.video_id "
                                              "WHERE k.video_id IS NULL ORDER BY o.nota DESC LIMIT ?", lote)]
    if ids:
        with ThreadPoolExecutor(AO_MESMO_TEMPO) as equipe:
            impressoes = list(equipe.map(baixar, ids))
        banco.varios("INSERT OR REPLACE INTO capas (video_id, hash) VALUES (?,?)",
                     [(i, x) for i, x in zip(ids, impressoes) if x is not TENTAR_DEPOIS])
    return len(ids)


def parecidas(video_id: str, quantos: int = 12, baixar=_baixar) -> dict:
    """As capas do índice mais parecidas com a deste vídeo, com o canal, as views e quantas vezes o normal cada uma fez."""
    guardada = banco.um("SELECT hash FROM capas WHERE video_id=?", video_id)
    alvo = guardada["hash"] if guardada and guardada["hash"] is not None else baixar(video_id)
    total = banco.um("SELECT COUNT(*) AS n FROM capas WHERE hash IS NOT NULL")["n"]
    if alvo is None or alvo is TENTAR_DEPOIS:
        return {"videos": [], "indice": total, "sem_capa": True}
    notas = sorted(((parecenca(alvo, l["hash"]), l["video_id"]) for l in banco.todos("SELECT video_id, hash FROM capas WHERE hash IS NOT NULL")
                    if l["video_id"] != video_id), reverse=True)
    melhores = [(p, v) for p, v in notas[:quantos] if p >= PARECIDO_MINIMO]
    if not melhores:
        return {"videos": [], "indice": total}
    por_id = {v: p for p, v in melhores}
    marcas = ",".join("?" * len(por_id))
    videos = banco.todos(f"SELECT v.id, v.titulo, v.views, c.titulo AS canal, o.nota FROM videos v JOIN canais c ON c.id=v.canal_id "
                         f"JOIN outliers o ON o.video_id=v.id WHERE v.id IN ({marcas})", *por_id)
    for v in videos:
        v["parecido"] = por_id[v["id"]]
    return {"videos": sorted(videos, key=lambda v: -v["parecido"]), "indice": total}


def iniciar() -> None:
    def rodar():
        while True:
            try:
                time.sleep(PAUSA if preencher() else 3600)
            except Exception:
                time.sleep(120)
    threading.Thread(target=rodar, daemon=True, name="capas").start()
