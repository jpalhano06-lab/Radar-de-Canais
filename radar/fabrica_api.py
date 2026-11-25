"""Acompanhar e Resultados: o Radar conversa com o editor da fábrica (porta 8080) para ver o andamento, o custo e o
vídeo pronto de cada produção (pedido do usuário em 2026-10-15, na organização do Robô do Dotti: Produzir,
Acompanhar e Produções com o custo).

A chave da fábrica (FABRICA_TOKEN, do .env da fábrica) fica só no servidor do Radar; o navegador nunca a vê. O vídeo
pronto é servido pelo próprio Radar, direto da pasta do projeto. Produzir passa pela rota "retomar" da fábrica, que
sem confirmar só devolve o custo: o Radar mostra a estimativa e só manda produzir com a confirmação da pessoa."""
import json
import time
from pathlib import Path

import httpx

from . import producao, roteiro_claude
from .config import AMBIENTE

URL = AMBIENTE.get("FABRICA_URL", "http://127.0.0.1:8080").rstrip("/")
_CUSTOS: dict[str, tuple[float, dict]] = {}       # nome -> (mtime do final.mp4, resumo do custo)


class SemFabrica(RuntimeError):
    """Qualquer "não deu" da fábrica: ela desligada ou um erro dela sobre o que foi pedido."""


class FabricaDesligada(SemFabrica):
    """Só a fábrica fora do ar (porta muda ou chave recusada): nada do pedido tem culpa. A fila da Nova produção
    separa os dois (2026-10-30): um projeto que a fábrica não achou era erro de um pedido só e parava a fila toda."""


def _pedir(metodo: str, caminho: str, corpo: dict | None = None, tempo: float = 20) -> dict:
    token = AMBIENTE.get("FABRICA_TOKEN", "")
    try:
        r = httpx.request(metodo, URL + caminho, json=corpo, timeout=tempo, headers={"x-fabrica-token": token} if token else {})
    except httpx.HTTPError:
        raise FabricaDesligada("O editor da fábrica não está ligado (porta 8080). Ligue a fábrica e tente de novo.")
    if r.status_code == 401:
        raise FabricaDesligada("A fábrica recusou a chave (FABRICA_TOKEN no .env da fábrica).")
    if r.status_code >= 400:
        raise SemFabrica(r.json().get("detail", f"Erro {r.status_code} da fábrica.") if r.headers.get("content-type", "").startswith("application/json") else f"Erro {r.status_code} da fábrica.")
    return r.json()


def _pasta(nome: str):
    return roteiro_claude.FABRICA / "projetos" / nome


def _titulo(nome: str) -> str:
    """O título bonito: o nome dado na entrega, o título do kit de publicação ou o nome da pasta."""
    pasta = _pasta(nome)
    for arquivo, chave in (("projeto.json", "titulo_entrega"), ("publicacao.json", "titulo")):
        try:
            valor = json.loads((pasta / arquivo).read_text(encoding="utf-8")).get(chave)
            if valor:
                return str(valor)
        except (OSError, ValueError):
            pass
    return nome.replace("-", " ").capitalize()


def _do_radar() -> dict[str, str]:
    """Os projetos que saíram do Roteiro do Radar (nome na fábrica -> roteiro)."""
    saida = {}
    for pasta in roteiro_claude.PASTA.glob("*/roteiro.json"):
        try:
            meta = json.loads(pasta.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if (meta.get("fabrica") or {}).get("projeto"):
            saida[meta["fabrica"]["projeto"]] = pasta.parent.name
    return saida


def _capa(nome: str) -> str:
    pasta = _pasta(nome)
    return f"/api/producoes/{nome}/capa" if any((pasta / f).exists() for f in ("thumbnail.jpg", "thumb_1.jpg", "thumbnail_referencia.jpg")) else ""


def _shorts(nome: str) -> list[dict]:
    """Os shorts que a fábrica cortou do vídeo (shorts/S01.mp4...), com o título do post."""
    pasta = _pasta(nome) / "shorts"
    try:
        info = {s["id"]: s for s in json.loads((pasta / "shorts.json").read_text(encoding="utf-8")).get("shorts", [])}
    except (OSError, ValueError):
        info = {}
    return [{"id": f.stem, "titulo": (info.get(f.stem) or {}).get("titulo_post", ""), "duracao": (info.get(f.stem) or {}).get("duracao")}
            for f in sorted(pasta.glob("S*.mp4"))]


def _publicado(nome: str) -> dict | None:
    """O que a fábrica publicou no YouTube (youtube.json): o id do vídeo e o link."""
    try:
        y = json.loads((_pasta(nome) / "youtube.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {"video_id": y["video_id"], "url": y.get("url") or f"https://youtu.be/{y['video_id']}", "pela": "fabrica"} if y.get("video_id") else None


def producoes() -> dict:
    """Tudo da fábrica, separado em andamento e prontos, os mais recentes primeiro."""
    # com dois vídeos pesados andando a lista levou 37 s (2026-11-16), e com 20 s o vigia achava a fábrica desligada
    lista = _pedir("GET", "/api/projetos", tempo=90)["projetos"]
    do_radar = _do_radar()
    andamento, prontos = [], []
    for p in sorted(lista, key=lambda x: x.get("criado") or "", reverse=True):
        nome = p["nome"]
        if nome.startswith("_"):
            continue
        c = p.get("criacao") or {}
        # vídeo postado há mais de 48 h teve o final.mp4 apagado (limpeza_postados.py), mas continua pronto
        if not p.get("tem_final") and (_pasta(nome) / "limpo_pos_postagem.json").exists():
            p = {**p, "tem_final": True}
        perfil = Path(str(p.get("perfil") or "")).stem
        canal = producao._perfil(perfil).get("canal") if perfil else ""
        item = {"nome": nome, "titulo": _titulo(nome), "canal": canal or "Sem canal", "perfil": perfil, "criado": p.get("criado", ""), "duracao": p.get("duracao") or 0,
                "cenas": p.get("cenas_count") or 0, "do_radar": nome in do_radar, "capa": _capa(nome),
                "status": c.get("status") or ("pronto" if p.get("tem_final") else "parado"),
                # o render ainda gravando conta como rodando: o final.mp4 aparece antes de ele terminar, e o vídeo era
                # dado por entregue no meio (o oxfam-uk em 2026-11-21)
                "rodando": bool(c.get("rodando") or p.get("renderizando")), "progresso": c.get("progresso_pct") or 0,
                "mensagem": c.get("mensagem") or "", "precisa_voce": bool(c.get("precisa_voce")),
                "tem_final": bool(p.get("tem_final"))}
        if item["tem_final"]:
            item["shorts"] = _shorts(nome)
            item["publicado"] = _publicado(nome)
        (prontos if item["tem_final"] and not item["rodando"] else andamento).append(item)
    return {"andamento": andamento[:60], "prontos": prontos[:120]}


def custo(nome: str) -> dict:
    """O gasto real do vídeo (pela fábrica), guardado até o vídeo mudar."""
    final = _pasta(nome) / "final.mp4"
    marca = final.stat().st_mtime if final.exists() else time.time() // 300
    if nome in _CUSTOS and _CUSTOS[nome][0] == marca:
        return _CUSTOS[nome][1]
    r = _pedir("GET", f"/api/projetos/{nome}/custos")
    resumo = {k: r.get(k) for k in ("total_usd", "por_minuto_usd", "por_cena_usd", "duracao_segundos", "cenas")}
    resumo["por_categoria"] = r.get("por_categoria") or {}
    resumo["modelos_de_texto"] = r.get("modelos_de_texto") or []     # o provedor de cada gasto de texto (Custos)
    _CUSTOS[nome] = (marca, resumo)
    return resumo


def produzir(nome: str, confirmar: bool) -> dict:
    """Sem confirmar: o que falta e quanto pode custar. Com confirmar: a fábrica começa a produzir."""
    return _pedir("POST", f"/api/projetos/{nome}/retomar", {"confirmar": bool(confirmar)})


# ---------------------------------------------------------------- o Acompanhar (2026-10-18)

def status(nome: str) -> dict:
    """O andamento ao vivo do projeto (etapa, passo, mensagem, se espera o modelo pago)."""
    return _pedir("GET", f"/api/projetos/{nome}/status", tempo=10)


def publicacao(nome: str) -> dict:
    """Título, descrição, tags, capítulos... do vídeo, se a fábrica já montou ({"pronto", "rodando", "publicacao"})."""
    return _pedir("GET", f"/api/projetos/{nome}/publicacao")


def gerar_publicacao(nome: str) -> dict:
    return _pedir("POST", f"/api/projetos/{nome}/publicacao")


def liberar_pago(nome: str) -> dict:
    return _pedir("POST", f"/api/projetos/{nome}/pago", {"liberar": True})


def apagar(nome: str) -> dict:
    return _pedir("DELETE", f"/api/projetos/{nome}")


# ---------------------------------------------------------------- as vozes da fábrica, para a configuração do canal

# as 32 línguas que as vozes da GenAI Pro falam (os modelos Multilingual v2 e Turbo v2.5), com o código dela
IDIOMA = {"português": "pt", "inglês": "en", "espanhol": "es", "francês": "fr", "alemão": "de", "italiano": "it",
          "holandês": "nl", "polonês": "pl", "russo": "ru", "ucraniano": "uk", "turco": "tr", "árabe": "ar",
          "hindi": "hi", "tâmil": "ta", "japonês": "ja", "chinês": "zh", "coreano": "ko", "indonésio": "id",
          "malaio": "ms", "filipino": "fil", "vietnamita": "vi", "sueco": "sv", "dinamarquês": "da",
          "norueguês": "no", "finlandês": "fi", "grego": "el", "tcheco": "cs", "eslovaco": "sk", "húngaro": "hu",
          "romeno": "ro", "búlgaro": "bg", "croata": "hr"}


def drive_status() -> dict:
    return _pedir("GET", "/api/drive/status")


def drive_conectar() -> dict:
    return _pedir("GET", "/api/drive/conectar")


def drive_desconectar() -> dict:
    return _pedir("POST", "/api/drive/desconectar")


def contas_youtube() -> dict:
    return _pedir("GET", "/api/garimpo/contas")


def conta_youtube_nova(nome: str, cookies: str) -> dict:
    return _pedir("POST", "/api/garimpo/contas", {"nome": nome, "cookies": cookies})


def conta_youtube_testar(nome: str) -> dict:
    return _pedir("POST", f"/api/garimpo/contas/{nome}/testar", tempo=90)


def conta_youtube_apagar(nome: str) -> dict:
    return _pedir("DELETE", f"/api/garimpo/contas/{nome}")


# ---------------------------------------------------------------- publicar no YouTube (2026-11-17)
# As contas de publicação são outras: as de cima são os cookies do garimpo (ler o YouTube), estas são o login OAuth
# que autoriza a fábrica a postar. Cada canal é conectado uma vez, porque o token do Google fica preso ao canal
# escolhido na tela de consentimento.

def youtube_contas(tempo: float = 20) -> dict:
    """As contas conectadas para publicar: {"contas": [...], "conta": a única, "conectado": bool}.

    A fábrica produzindo demora a responder: quem pergunta de tempos em tempos manda um tempo curto e tenta de novo
    depois, em vez de ficar esperando."""
    return _pedir("GET", "/api/youtube/status", tempo=tempo)


def youtube_conectar_url() -> str:
    """O endereço da tela de consentimento do Google para ligar mais um canal na fábrica.

    A fábrica responde com um redirecionamento; o Radar lê o destino aqui e manda só ele para o navegador, para a
    chave da fábrica nunca aparecer na barra de endereços. O Host vai como localhost porque é com ele que o endereço
    de volta (redirect_uri) está cadastrado no Google, o mesmo do painel da fábrica."""
    token = AMBIENTE.get("FABRICA_TOKEN", "")
    cabecalhos = {"x-fabrica-token": token} if token else {}
    if URL.startswith("http://127.0.0.1"):
        cabecalhos["host"] = "localhost" + URL.split("127.0.0.1", 1)[1]
    try:
        r = httpx.get(URL + "/api/youtube/conectar", timeout=20, follow_redirects=False, headers=cabecalhos)
    except httpx.HTTPError:
        raise FabricaDesligada("O editor da fábrica não está ligado (porta 8080). Ligue a fábrica e tente de novo.")
    destino = r.headers.get("location", "")
    if not destino:
        raise SemFabrica("A fábrica não devolveu o endereço do login do Google.")
    return destino


def youtube_publicar(nome: str, canal: str, quando: str = "", privacidade: str = "public",
                     com_thumbnail: bool = True, simular: bool = False, titulo: str = "",
                     descricao: str | None = None, tags: list | None = None) -> dict:
    """Manda a fábrica subir o final.mp4 do projeto no canal (o id do canal do YouTube).

    quando: ISO na hora do canal ("2026-11-20T18:00"). Com ela o vídeo sobe privado com publishAt e o YouTube publica
    sozinho no dia marcado, sem a fábrica nem o Radar ligados. Sem thumbnail o YouTube usa os quadros automáticos.

    titulo, descricao e tags: o kit do Radar, escrito pelo Claude junto com o roteiro. Vão no pedido porque a
    fábrica, sozinha, publica pelo publicacao.json dela (o molde dela, que pode até sair sem modelo nenhum)."""
    corpo = {"canal": canal, "privacidade": privacidade, "com_thumbnail": com_thumbnail,
             "com_shorts": False, "simular": simular}
    if quando:
        corpo["agendado_para"] = quando
    if titulo:
        corpo["titulo"] = titulo
    if descricao is not None:
        corpo["descricao"] = descricao
    if tags is not None:
        corpo["tags"] = tags_que_cabem(tags)
    return _pedir("POST", f"/api/projetos/{nome}/youtube/publicar", corpo, tempo=60)


def tags_que_cabem(tags: list) -> list:
    """As tags, na ordem, até onde cabem nos 500 caracteres do YouTube, que conta a vírgula entre elas e as aspas
    em volta da tag com espaço. Passou disso, ele recusa o envio inteiro com invalidTags (The Moon Is Drifting Away
    From Us, 2026-11-20: 18 tags, 512 caracteres). Vírgula dentro da tag ("3,8 cm") e < > também são recusados.
    A fábrica corta igual (youtube_publicar.tags_que_cabem); aqui vale sem esperar ela ser religada."""
    cabem, usado = [], 0
    for tag in tags or []:
        tag = " ".join(str(tag).replace(",", ".").replace("<", " ").replace(">", " ").split())[:100]
        if not tag or tag in cabem:
            continue
        custo = len(tag) + (2 if " " in tag else 0) + (1 if cabem else 0)
        if usado + custo > 500:
            continue
        cabem.append(tag)
        usado += custo
    return cabem


def youtube_publicacao(nome: str, tarefa: str = "") -> dict:
    """O andamento do envio e o que já foi publicado (o youtube.json do projeto)."""
    return _pedir("GET", f"/api/projetos/{nome}/youtube/status" + (f"?task_id={tarefa}" if tarefa else ""))


def youtube_do_projeto(nome: str) -> dict | None:
    """O youtube.json do projeto lido direto da pasta: funciona com a fábrica desligada e não gasta um pedido."""
    return _publicado(nome)


def chatgpt_estado() -> dict:
    """A conta ChatGPT logada no computador da fábrica, o plano e quanto já foi usado das janelas de limite. É a
    fábrica quem gera as imagens, então é lá que o login mora (pedido do usuário em 2026-11-01)."""
    return _pedir("GET", "/api/chatgpt/estado", tempo=30)


def vozes(lingua: str, busca: str = "", genero: str = "", pagina: int = 0) -> dict:
    """A biblioteca de vozes do OpenSpeaker pela fábrica, só as da língua, com a prévia. Não gasta crédito.

    Trocada da GenAI Pro em 2026-11-17. São catálogos diferentes: nenhum voice_id da GenAI Pro existe aqui."""
    from urllib.parse import urlencode
    codigo = IDIOMA.get(lingua, lingua if lingua in IDIOMA.values() else "pt")
    consulta = urlencode({"idioma": codigo, "busca": busca[:60], "genero": genero if genero in ("male", "female") else "",
                          "pagina": pagina})
    r = _pedir("GET", f"/api/vozes/openspeaker?{consulta}", tempo=60)
    # a fábrica antiga não filtra: o provedor completa a página com vozes de outras línguas
    so_da_lingua = [v for v in r.get("vozes", []) if not v.get("idioma") or v["idioma"] == codigo]
    return {"vozes": so_da_lingua, "erro": r.get("erro", ""), "preco_por_mil": r.get("preco_por_mil"),
            "tem_mais": bool(r.get("tem_mais"))}


def criar_canal(nome: str, voz: dict) -> str:
    """Cria (ou atualiza) o canal na fábrica com a voz escolhida (perfis/canal-NOME.yaml, herdando do documentário).
    Devolve o nome do perfil, que o Radar guarda como a voz do canal."""
    r = _pedir("POST", "/api/canais", {"nome": nome, "base": "documentario.yaml", "voz": {
        "provedor": "openspeaker", "voice_id": str(voz.get("voice_id", "")), "nome": str(voz.get("nome", ""))[:80],
        "idioma": str(voz.get("idioma", ""))[:5]}})
    return r["id"]


# ---------------------------------------------------------------- a página Animações (pedido do usuário em 2026-11-07)

def _cru(caminho: str, tempo: float = 20) -> httpx.Response:
    """Um pedido que devolve a página ou o arquivo, não JSON (a prévia e as letras)."""
    token = AMBIENTE.get("FABRICA_TOKEN", "")
    try:
        r = httpx.get(URL + caminho, timeout=tempo, headers={"x-fabrica-token": token} if token else {})
    except httpx.HTTPError:
        raise FabricaDesligada("O editor da fábrica não está ligado (porta 8080). Ligue a fábrica e tente de novo.")
    if r.status_code == 401:
        raise FabricaDesligada("A fábrica recusou a chave (FABRICA_TOKEN no .env da fábrica).")
    if r.status_code >= 400:
        raise SemFabrica(f"Erro {r.status_code} da fábrica.")
    return r


def catalogo_animacoes() -> dict:
    return _pedir("GET", "/api/animacoes/catalogo")


def previa_animacao(ajustes: str, tipo: str, parado: float | None) -> str:
    from urllib.parse import urlencode
    consulta = {"ajustes": ajustes, "tipo": tipo} | ({} if parado is None else {"parado": parado})
    return _cru(f"/api/animacoes/previa?{urlencode(consulta)}").text


def fonte_animacao(arquivo: str) -> bytes:
    from urllib.parse import quote
    return _cru(f"/api/animacoes/fonte/{quote(arquivo, safe='')}").content


def conferir_animacoes(ajustes: dict) -> dict:
    """A mesma conferência da gravação; leva uns 40 s, porque abre um navegador por animação."""
    return _pedir("POST", "/api/animacoes/conferir", {"ajustes": ajustes}, tempo=240)


def animacoes_do_canal(perfil: str) -> dict | None:
    from urllib.parse import urlencode
    return _pedir("GET", f"/api/canais/animacoes?{urlencode({'perfil': perfil})}").get("ajustes")


def salvar_animacoes_do_canal(perfil: str, ajustes: dict) -> dict:
    return _pedir("POST", "/api/canais/animacoes", {"perfil": perfil, "ajustes": ajustes})


def definir_animacoes(projeto: str, ajustes: dict) -> dict:
    """O estilo só deste vídeo, por cima do canal."""
    return _pedir("POST", f"/api/projetos/{projeto}/animacoes", {"ajustes": ajustes})


def pausar(projeto: str, pausado: bool) -> dict:
    """O Pausar/Continuar da fila (2026-11-16): a fábrica segura a criação do vídeo na próxima etapa."""
    return _pedir("POST", f"/api/projetos/{projeto}/pausar", {"pausado": pausado})
