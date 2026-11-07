"""De onde vêm os canais e onde estão as ideias (pedido do usuário em 2026-11-07, depois de ver o Dotti Finder).

A ideia de cada peça veio de olhar o que eles mostram; a conta, os cortes e os nomes são nossos, com o que o Radar já
mede — a regra da casa continua: nada de copiar código, texto ou visual de concorrente.

- **A origem do canal**: cada canal guarda por onde entrou no Radar (a busca do garimpo, a categoria em alta, a
  extensão, os parecidos de um salvo...). Só a primeira origem vale: quem já tem uma não troca.
- **Palavras-chave e tópicos**: o que o dono cadastrou no canal (brandingSettings.keywords) e as categorias de tópico
  do YouTube. Os termos entre aspas são compostos, onde o dono apostou: bom ponto de partida para subtemas.
- **Subtemas dos vídeos que estouraram**: os vídeos com SUBTEMA_NOTA vezes o normal do canal (e pelo menos
  SUBTEMA_VIEWS views) ganham, do modelo de texto, o subtema em poucas palavras. Fica guardado; só é perguntado de
  novo quando a lista de vídeos muda.
- **Nichos com espaço**: subnichos em que vídeos estouraram nos últimos ESPACO_DIAS dias e quase ninguém faz
  (ESPACO_MAX_CANAIS canais ou menos no Radar). É a sondagem do nicho vazio, sem gastar cota: só lê o banco.
"""
import json
import re
from datetime import datetime, timedelta, timezone

from . import banco, metricas
from .config import MODELO_TEXTO

ORIGENS = {
    "busca": "Busca do garimpo no YouTube",
    "categoria": "Em alta na categoria do YouTube",
    "navegador": "Achado no navegador",
    "lente": "A extensão leu enquanto você navegava",
    "parecidos": "Parecido com um canal salvo",
    "procura": "Procura de nicho na hora",
    "treino": "Treino do algoritmo",
    "manual": "Você adicionou",
    "repescagem": "Repescagem: voltou a crescer",
    "garimpo": "Busca do garimpo no YouTube",
}

SUBTEMA_NOTA = 6
SUBTEMA_VIEWS = 6000
SUBTEMAS_MAX = 20
CHAVE_SUBTEMAS = "subtemas:"

ESPACO_DIAS = 30
ESPACO_MAX_CANAIS = 3


def marcar_origem(ids, origem: str) -> None:
    """Guarda por onde o canal entrou. Só preenche quem ainda não tem origem."""
    ids = [i for i in dict.fromkeys(ids or []) if i]
    if not ids or not origem:
        return
    for i in range(0, len(ids), 500):
        lote = ids[i:i + 500]
        banco.executar(f"UPDATE canais SET origem=? WHERE id IN ({','.join('?' * len(lote))}) "
                       "AND (origem IS NULL OR origem='')", origem, *lote)


def palavras(keywords: str) -> list[dict]:
    """As palavras-chave do canal, como o YouTube guarda: separadas por espaço, as compostas entre aspas."""
    saida, vistos = [], set()
    for bruto in re.findall(r'"[^"]+"|\S+', keywords or ""):
        termo = bruto.strip('"').strip()
        if termo and termo.lower() not in vistos:
            vistos.add(termo.lower())
            saida.append({"termo": termo, "composto": bruto.startswith('"') or " " in termo})
    return saida[:60]


def topicos(guardado) -> list[str]:
    """As categorias de tópico do YouTube (links da Wikipédia) viram o nome do fim do link."""
    try:
        lista = json.loads(guardado) if isinstance(guardado, str) else (guardado or [])
    except ValueError:
        return []
    return [str(t).rsplit("/", 1)[-1].replace("_", " ") for t in lista if t][:12]


def _estouraram(canal_id: str) -> list[dict]:
    c = banco.um("SELECT base_longos FROM canais WHERE id=?", canal_id) or {}
    normal = c.get("base_longos")
    if not normal:
        return []
    saida = []
    for v in banco.todos("SELECT id, titulo, views, publicado FROM videos WHERE canal_id=? AND duracao_s>? "
                         "AND views>=? ORDER BY views DESC LIMIT 200", canal_id, metricas.CURTO_ATE_S, SUBTEMA_VIEWS):
        nota = metricas.nota_outlier(v["views"], normal)
        if nota and nota >= SUBTEMA_NOTA:
            saida.append(v | {"nota": nota})
    saida.sort(key=lambda v: -v["nota"])
    return saida[:SUBTEMAS_MAX]


def subtemas(canal_id: str, perguntar=None) -> dict:
    """Os subtemas dos vídeos que estouraram no canal. perguntar é o modelo (ia._perguntar), trocável no teste."""
    videos = _estouraram(canal_id)
    if not videos:
        return {"videos": [], "nota_minima": SUBTEMA_NOTA, "views_minimas": SUBTEMA_VIEWS}
    chave = CHAVE_SUBTEMAS + canal_id
    assinatura = ",".join(sorted(v["id"] for v in videos))
    guardado = banco.um("SELECT dados FROM traducoes WHERE chave=?", chave)
    feitos = {}
    if guardado:
        try:
            dados = json.loads(guardado["dados"])
            if dados.get("assinatura") == assinatura:
                feitos = dados.get("subtemas") or {}
        except ValueError:
            pass
    faltam = [v for v in videos if v["id"] not in feitos]
    if faltam:
        if perguntar is None:
            from .ia import _perguntar as perguntar
        lista = "\n".join(f"{i + 1}. {v['titulo']}" for i, v in enumerate(faltam))
        resposta = perguntar(
            MODELO_TEXTO,
            "Para cada título de vídeo do YouTube, escreva o subtema em 2 a 5 palavras em português: o assunto exato "
            "do vídeo, sem o nome próprio de um vídeo só, do jeito que um produtor de canal anotaria para fazer outro "
            "vídeo parecido (exemplos: 'Golpes de pirâmide famosos', 'Animais que mudam de sexo', 'Cidades "
            "abandonadas da URSS'). Responda só JSON: {\"subtemas\": [{\"n\": 1, \"subtema\": \"...\"}]}.",
            lista, esperar=30) or {}
        for item in resposta.get("subtemas") or []:
            try:
                n = int(item.get("n")) - 1
            except (TypeError, ValueError, AttributeError):
                continue
            texto = re.sub(r"\s+", " ", str(item.get("subtema") or "")).strip(" .")[:60]
            if 0 <= n < len(faltam) and texto:
                feitos[faltam[n]["id"]] = texto[:1].upper() + texto[1:]
        banco.executar("INSERT OR REPLACE INTO traducoes (chave, dados, criado) VALUES (?,?,?)", chave,
                       json.dumps({"assinatura": assinatura, "subtemas": feitos}, ensure_ascii=False), banco.agora())
    return {"videos": [v | {"subtema": feitos.get(v["id"], "")} for v in videos],
            "nota_minima": SUBTEMA_NOTA, "views_minimas": SUBTEMA_VIEWS}


def com_espaco(dias: int = ESPACO_DIAS, max_canais: int = ESPACO_MAX_CANAIS) -> list[dict]:
    """Subnichos em que algum vídeo estourou há pouco e quase ninguém do Radar faz. O melhor exemplo vai junto."""
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    linhas = banco.todos(
        "SELECT c.subnicho, MAX(c.nicho) AS nicho, COUNT(DISTINCT c.id) AS canais, "
        "COUNT(DISTINCT CASE WHEN o.achado>=? THEN o.video_id END) AS estouros "
        "FROM canais c LEFT JOIN outliers o ON o.canal_id=c.id "
        "WHERE c.no_radar=1 AND c.subnicho!='' GROUP BY c.subnicho", desde)
    saida = []
    for l in linhas:
        if not l["estouros"] or l["canais"] > max_canais:
            continue
        exemplo = banco.um(
            "SELECT o.video_id, o.nota, v.titulo, v.views, c.titulo AS canal, c.id AS canal_id FROM outliers o "
            "JOIN canais c ON c.id=o.canal_id LEFT JOIN videos v ON v.id=o.video_id "
            "WHERE c.subnicho=? AND c.no_radar=1 AND o.achado>=? ORDER BY o.nota DESC LIMIT 1", l["subnicho"], desde)
        saida.append({"subnicho": l["subnicho"], "nicho": l["nicho"], "canais": l["canais"],
                      "estouros": l["estouros"], "exemplo": exemplo})
    saida.sort(key=lambda x: (-x["estouros"] / x["canais"], -x["estouros"]))
    return saida[:40]


def repescados(limite: int = 40) -> list[dict]:
    """Os canais que a repescagem do garimpo trouxe de volta, do mais recente para o mais antigo."""
    return banco.todos("SELECT * FROM canais WHERE origem='repescagem' AND no_radar=1 ORDER BY repescado DESC LIMIT ?",
                       limite)
