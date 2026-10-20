"""O 🎯 de cada vídeo e o "inscrever canal no algoritmo" (pedido do usuário em 2026-10-14).

O 🎯 é uma curtida para o algoritmo de um canal da pessoa: "quero ideias assim". As palavras do título marcado ganham
peso nas ideias daquele canal, como os vídeos escolhidos no treino, e cada 🎯 a mais deixa as buscas melhores.
Inscrever um canal no algoritmo é o mesmo para um canal inteiro: os assuntos dele pesam nas ideias e os vídeos dele que
estouram entram primeiro. Ao inscrever, o canal é medido (uns 3 de cota) para os vídeos dele entrarem na base."""
import threading
from collections import Counter

from . import banco, gosto, perfil

PESO_ALVO = 2.0          # cada palavra de um vídeo com 🎯 (o treino dá 1 por vídeo escolhido)
PESO_INSCRITO = 0.4      # cada palavra dos 15 vídeos de maior views de um canal inscrito
BONUS_INSCRITO = 2.0     # vídeo de um canal inscrito sobe nas ideias


def tudo(usuario_id: int) -> dict:
    """Por canal da pessoa: os vídeos com 🎯 e os canais inscritos."""
    saida: dict[str, dict] = {}
    for l in banco.todos("SELECT canal_id, video_id FROM alvos WHERE usuario_id=?", usuario_id):
        saida.setdefault(l["canal_id"], {"videos": [], "canais": []})["videos"].append(l["video_id"])
    for l in banco.todos("SELECT canal_id, ref_canal_id FROM canais_inscritos WHERE usuario_id=?", usuario_id):
        saida.setdefault(l["canal_id"], {"videos": [], "canais": []})["canais"].append(l["ref_canal_id"])
    return saida


def marcar(usuario_id: int, canal_id: str, video_id: str, titulo: str, ligar: bool) -> int:
    if ligar:
        if not titulo:
            v = banco.um("SELECT titulo FROM videos WHERE id=?", video_id)
            titulo = v["titulo"] if v else ""
        banco.executar("INSERT OR REPLACE INTO alvos (usuario_id, canal_id, video_id, titulo, criado) VALUES (?,?,?,?,?)",
                       usuario_id, canal_id, video_id, titulo[:300], banco.agora())
    else:
        banco.executar("DELETE FROM alvos WHERE usuario_id=? AND canal_id=? AND video_id=?", usuario_id, canal_id, video_id)
    _no_treino(usuario_id, canal_id, video=video_id, ligar=ligar)
    return banco.um("SELECT COUNT(*) AS n FROM alvos WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id)["n"]


def _no_treino(usuario_id: int, canal_id: str, *, video: str = "", canal: str = "", ligar: bool) -> None:
    """O 🎯 e o inscrever também vão para o Treinar algoritmo do canal (pedido do usuário em 2026-10-14): o vídeo
    curtido entra nos escolhidos (e sai dos recusados) e o canal inscrito entra nos canais de referência."""
    from . import treinamento
    t = treinamento.estado(usuario_id, canal_id) or {}
    positivos, negativos, refs = list(t.get("positivos", [])), list(t.get("negativos", [])), list(t.get("referencias", []))
    if video:
        positivos = [v for v in positivos if v != video] + ([video] if ligar else [])
        negativos = [v for v in negativos if v != video]
    if canal:
        refs = [c for c in refs if c != canal] + ([canal] if ligar else [])
    treinamento._gravar(usuario_id, canal_id, positivos=positivos, negativos=negativos, referencias=refs)


def inscrever(usuario_id: int, canal_id: str, ref_canal_id: str, ligar: bool) -> int:
    if ligar:
        banco.executar("INSERT OR REPLACE INTO canais_inscritos (usuario_id, canal_id, ref_canal_id, criado) VALUES (?,?,?,?)",
                       usuario_id, canal_id, ref_canal_id, banco.agora())
        # mede o canal e os vídeos dele em segundo plano: os que estouraram entram nas ideias
        threading.Thread(target=lambda: _medir(usuario_id, ref_canal_id), daemon=True).start()
    else:
        banco.executar("DELETE FROM canais_inscritos WHERE usuario_id=? AND canal_id=? AND ref_canal_id=?",
                       usuario_id, canal_id, ref_canal_id)
    _no_treino(usuario_id, canal_id, canal=ref_canal_id, ligar=ligar)
    return banco.um("SELECT COUNT(*) AS n FROM canais_inscritos WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id)["n"]


def _medir(usuario_id: int, ref_canal_id: str) -> None:
    try:
        perfil.conectar(usuario_id, ref_canal_id, meu=False)
    except Exception:
        pass


def inscritos(usuario_id: int, canal_id: str) -> set[str]:
    return {l["ref_canal_id"] for l in banco.todos(
        "SELECT ref_canal_id FROM canais_inscritos WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id)}


def pesos(usuario_id: int, canal_id: str) -> Counter:
    """As palavras que o 🎯 e os canais inscritos ensinaram, com peso."""
    conta: Counter = Counter()
    for l in banco.todos("SELECT titulo FROM alvos WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id):
        for p in gosto.chaves(l["titulo"]):
            conta[p] += PESO_ALVO
    for ref in inscritos(usuario_id, canal_id):
        for v in banco.todos("SELECT titulo FROM videos WHERE canal_id=? ORDER BY views DESC LIMIT 15", ref):
            for p in gosto.chaves(v["titulo"]):
                conta[p] += PESO_INSCRITO
    return conta


def contagem(usuario_id: int, canal_id: str) -> dict:
    return {"alvos": banco.um("SELECT COUNT(*) AS n FROM alvos WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id)["n"],
            "inscritos": len(inscritos(usuario_id, canal_id))}
