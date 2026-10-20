"""O trabalho de cada canal da pessoa: as ideias (com filtros), as ideias salvas no painel da direita e o assunto do
canal, que a extensão usa para o selo 🎯. O treinamento do algoritmo fica em treinamento.py (feito no site)."""
import json
from datetime import datetime, timedelta, timezone

from . import banco, gosto, ia, metricas, perfil


# ---------------------------------------------------------------- ideias de um canal, com filtros

def ideias(usuario: dict, canal: dict, filtros: dict) -> list[dict]:
    lista = gosto.por_lingua(gosto.ideias_para(usuario, canal, limite=400, formato=filtros.get("formato") or "todos"),
                             filtros.get("lingua", ""))
    nota_min = float(filtros.get("nota_min") or 3)
    dias = filtros.get("publicado_dias")
    corte = (datetime.now(timezone.utc) - timedelta(days=int(dias))).isoformat() if dias else ""
    inscritos_max = int(filtros["inscritos_max"]) if filtros.get("inscritos_max") else None
    saida = []
    for v in lista:
        if v["nota"] < nota_min or (corte and v["publicado"] < corte):
            continue
        if inscritos_max and (v["inscritos"] or 0) > inscritos_max:
            continue
        saida.append(v)
    formato = filtros.get("formato")
    if formato in ("longo", "curto"):
        saida = [v for v in saida if metricas.curto(v["duracao_s"]) == (formato == "curto")]
    ordem = filtros.get("ordem") or "parecido"
    if ordem == "aleatorio":
        import random
        random.shuffle(saida)
    if ordem == "nota":
        saida.sort(key=lambda v: -v["nota"])
    elif ordem == "recente":
        saida.sort(key=lambda v: v["publicado"], reverse=True)
    elif ordem == "views":
        saida.sort(key=lambda v: -(v["views"] or 0))
    return saida


# ---------------------------------------------------------------- ideias salvas (o painel da direita)

def salvar_ideia(usuario_id: int, canal_id: str, video_id: str, titulo: str) -> None:
    banco.executar("INSERT OR IGNORE INTO ideias_salvas (usuario_id, canal_id, video_id, titulo, criado) VALUES (?,?,?,?,?)",
                   usuario_id, canal_id or "", video_id, titulo[:200], banco.agora())


def tirar_ideia(usuario_id: int, ideia_id: int) -> None:
    banco.executar("DELETE FROM ideias_salvas WHERE id=? AND usuario_id=?", ideia_id, usuario_id)


def ideias_salvas(usuario_id: int) -> dict:
    """Uma aba por canal da pessoa (e "Geral" para o que foi salvo sem canal)."""
    canais = banco.todos("SELECT c.id, c.titulo, c.foto FROM meus_canais m JOIN canais c ON c.id=m.canal_id "
                         "WHERE m.usuario_id=? ORDER BY c.inscritos DESC", usuario_id)
    linhas = banco.todos("SELECT s.id, s.canal_id, s.video_id, s.titulo, s.criado, v.views, c.titulo AS canal_origem "
                         "FROM ideias_salvas s LEFT JOIN videos v ON v.id=s.video_id LEFT JOIN canais c ON c.id=v.canal_id "
                         "WHERE s.usuario_id=? ORDER BY s.criado DESC", usuario_id)
    abas = [{"id": c["id"], "titulo": c["titulo"], "foto": c["foto"], "ideias": []} for c in canais]
    por_id = {a["id"]: a for a in abas}
    geral = {"id": "", "titulo": "Geral", "foto": "", "ideias": []}
    for l in linhas:
        (por_id.get(l["canal_id"]) or geral)["ideias"].append(l)
    if geral["ideias"] or not abas:
        abas.append(geral)
    return {"abas": abas, "total": len(linhas)}


# ---------------------------------------------------------------- o assunto do canal (selo da extensão)

def assunto(canal: dict, usuario_id: int | None = None) -> set[str]:
    """As palavras que dizem o assunto do canal: a extensão cola o selo nos vídeos do YouTube que falam delas.
    Com o treino feito, valem as palavras dos vídeos que a pessoa escolheu (as recusadas saem)."""
    if usuario_id is not None:
        from .treinamento import pesos
        treinadas = pesos(usuario_id, canal["id"])
        if treinadas:
            return {p for p, w in treinadas.items() if w > 0}
    palavras = set()
    for v in banco.todos("SELECT titulo FROM videos WHERE canal_id=? ORDER BY views DESC LIMIT 30", canal["id"]):
        palavras |= gosto.chaves(v["titulo"])
    for campo in ("subnicho", "nicho"):
        palavras |= gosto.chaves(canal.get(campo) or "")
    return palavras
