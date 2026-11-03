"""Acompanhar e Resultados: o Radar conversa com o editor da fábrica (porta 8080) para ver o andamento, o custo e o
vídeo pronto de cada produção (pedido do usuário em 2026-10-15, na organização do Robô do Dotti: Produzir,
Acompanhar e Produções com o custo).

A chave da fábrica (FABRICA_TOKEN, do .env da fábrica) fica só no servidor do Radar; o navegador nunca a vê. O vídeo
pronto é servido pelo próprio Radar, direto da pasta do projeto. Produzir passa pela rota "retomar" da fábrica, que
sem confirmar só devolve o custo: o Radar mostra a estimativa e só manda produzir com a confirmação da pessoa."""
import json
import re
import time
from pathlib import Path

import httpx

from . import producao, roteiro_claude
from .config import AMBIENTE

URL = AMBIENTE.get("FABRICA_URL", "http://127.0.0.1:8080").rstrip("/")
_CUSTOS: dict[str, tuple[float, dict]] = {}       # nome -> (mtime do final.mp4, resumo do custo)


class SemFabrica(RuntimeError):
    def __init__(self, mensagem: str, status: int = 0):
        super().__init__(mensagem)
        self.status = status


def _pedir(metodo: str, caminho: str, corpo: dict | None = None, tempo: float = 20) -> dict:
    token = AMBIENTE.get("FABRICA_TOKEN", "")
    try:
        r = httpx.request(metodo, URL + caminho, json=corpo, timeout=tempo, headers={"x-fabrica-token": token} if token else {})
    except httpx.HTTPError:
        raise SemFabrica("O editor da fábrica não está ligado (porta 8080). Ligue a fábrica e tente de novo.")
    if r.status_code == 401:
        raise SemFabrica("A fábrica recusou a chave (FABRICA_TOKEN no .env da fábrica).")
    if r.status_code >= 400:
        raise SemFabrica(r.json().get("detail", f"Erro {r.status_code} da fábrica.") if r.headers.get("content-type", "").startswith("application/json") else f"Erro {r.status_code} da fábrica.", r.status_code)
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
    lista = _pedir("GET", "/api/projetos")["projetos"]
    do_radar = _do_radar()
    andamento, prontos = [], []
    for p in sorted(lista, key=lambda x: x.get("criado") or "", reverse=True):
        nome = p["nome"]
        if nome.startswith("_"):
            continue
        c = p.get("criacao") or {}
        perfil = Path(str(p.get("perfil") or "")).stem
        canal = producao._perfil(perfil).get("canal") if perfil else ""
        item = {"nome": nome, "titulo": _titulo(nome), "canal": canal or "Sem canal", "perfil": perfil, "criado": p.get("criado", ""), "duracao": p.get("duracao") or 0,
                "cenas": p.get("cenas_count") or 0, "do_radar": nome in do_radar, "capa": _capa(nome),
                "status": c.get("status") or ("pronto" if p.get("tem_final") else "parado"),
                "rodando": bool(c.get("rodando")), "progresso": c.get("progresso_pct") or 0,
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

IDIOMA = {"português": "pt", "inglês": "en", "espanhol": "es"}


MAXIMO_DE_VOZES = 80
_CODIGO_DA_VOZ = re.compile(r"(omnivoice|kokoro|qwen|qwen_design):[^\n\r\"\\]{1,500}")


def _ordem(v: dict, idioma: str) -> tuple:
    """As que falam a língua do canal de nascença primeiro (as gravadas antes), depois as prontas do voicebox, as
    com nome da galeria do VoiceStudio e por último as combinações desenhadas (são centenas)."""
    nativa = v.get("idioma") == idioma
    combinacao = v.get("motor") == "omnivoice" and "," in v.get("id", "")
    return (not nativa, v.get("tipo") != "gravada", combinacao, v.get("origem") != "voicebox")


def vozes(lingua: str, busca: str = "", genero: str = "") -> dict:
    """As vozes grátis da fábrica (2026-10-28: as narrações pagas saíram): as do VoiceStudio e do voicebox, que a
    fábrica roda no próprio computador (GET /api/vozes/local), com a prévia em áudio. Não gasta nada."""
    from urllib.parse import quote, urlencode
    idioma = IDIOMA.get(lingua, lingua if lingua in IDIOMA.values() else "pt")
    consulta = urlencode({"idioma": idioma, "busca": busca[:60],
                          "genero": genero if genero in ("male", "female") else "", "limite": 2000})
    r = _pedir("GET", f"/api/vozes/local?{consulta}", tempo=40)
    lista = sorted(r.get("vozes", []), key=lambda v: _ordem(v, idioma))[:MAXIMO_DE_VOZES]
    return {"vozes": [{"voice_id": v["id"], "nome": v.get("nome") or v["id"], "genero": v.get("genero", ""),
                       "idade": v.get("tipo", ""), "sotaque": v.get("origem", ""), "descricao": v.get("descricao", ""),
                       "idioma": idioma,
                       "previa": f"/api/fabrica/vozes/previa?voz={quote(v['id'])}&idioma={idioma}"} for v in lista],
            "total": r.get("total", len(lista)), "erro": r.get("erro", ""), "preco_por_mil": 0}


def previa(voz: str, idioma: str) -> bytes:
    """O trecho de prévia da voz, gerado pela fábrica (a primeira vez liga o motor de voz: até uns 2 min)."""
    from urllib.parse import urlencode
    token = AMBIENTE.get("FABRICA_TOKEN", "")
    try:
        r = httpx.get(f"{URL}/api/vozes/local/previa?{urlencode({'voz': voz, 'idioma': idioma})}", timeout=300,
                      headers={"x-fabrica-token": token} if token else {})
    except httpx.HTTPError:
        raise SemFabrica("O editor da fábrica não está ligado (porta 8080). Ligue a fábrica e tente de novo.")
    if r.status_code != 200:
        detalhe = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else ""
        raise SemFabrica(detalhe or f"Erro {r.status_code} da fábrica ao gerar a prévia.", r.status_code)
    return r.content


def criar_canal(nome: str, voz: dict) -> str:
    """Cria (ou atualiza) o canal na fábrica com a voz escolhida (perfis/canal-NOME.yaml, herdando do documentário).
    Devolve o nome do perfil, que o Radar guarda como a voz do canal."""
    dados = {"provedor": "local", "voz_local": str(voz.get("voice_id", "")).strip(),
             "nome": str(voz.get("nome", ""))[:80], "idioma": str(voz.get("idioma", ""))[:5]}
    try:
        r = _pedir("POST", "/api/canais", {"nome": nome, "base": "documentario.yaml", "voz": dados})
    except SemFabrica as erro:
        # fábrica sem a rota /api/canais (a do amigo, em 2026-10-28, respondia 405): o Radar escreve o perfil
        if erro.status not in (404, 405):
            raise
        return _escrever_canal(nome, dados)
    return r["id"]


def _escrever_canal(nome: str, voz: dict) -> str:
    """O mesmo que a rota /api/canais faria: perfis/canal-NOME.yaml herdando do documentário, com a voz grátis da
    fábrica (provedor local, o código da voz em voz_local). Se o perfil já existe, só o bloco voz é trocado (o rodapé
    e o resto ficam). A língua vai também em `idioma`, que é o que a fábrica lê para narrar e conferir a voz."""
    perfil = f"canal-{roteiro_claude._slug(nome)}"
    arquivo = roteiro_claude.FABRICA / "perfis" / f"{perfil}.yaml"
    if not _CODIGO_DA_VOZ.fullmatch(voz["voz_local"]):
        raise SemFabrica("Essa voz veio sem um código válido.")
    lingua = voz["idioma"] if re.fullmatch(r"[a-z]{2}(-[A-Za-z]{2})?", voz["idioma"]) else ""
    bloco = (f"voz:\n  provedor: local\n  voz_local: {json.dumps(voz['voz_local'], ensure_ascii=False)}\n"
             f"  nome_da_voz: {json.dumps(voz['nome'], ensure_ascii=False)}\n"
             + (f"  idioma: {lingua[:2]}\n  idioma_da_voz: {lingua}\n" if lingua else ""))
    if arquivo.exists():
        atual = arquivo.read_text(encoding="utf-8", errors="ignore")
        sem_voz = re.sub(r"(?m)^voz:\n(?:[ \t].*\n|\n(?=[ \t]))*", "", atual).rstrip("\n")
        arquivo.write_text(f"{sem_voz}\n\n{bloco}", encoding="utf-8")
    else:
        arquivo.write_text(f"# {nome}: criado pelo Radar ao escolher a voz. Herda tudo do documentário.\n"
                           f"base: documentario.yaml\n\nnome: {json.dumps(nome, ensure_ascii=False)}\n\n{bloco}",
                           encoding="utf-8")
    return perfil
