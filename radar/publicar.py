"""A ajuda para publicar no YouTube Studio (pedido do usuário em 2026-10-20: "adicionar a extensão na hora de postar o
vídeo com anúncios e tudo"). A extensão mostra um painel na tela de upload com o título, a descrição e as tags que a
fábrica montou, e a lista do que marcar (anúncios, questionário de anunciantes, público e visibilidade). Ela não
clica nem publica nada: a pessoa copia e marca (escolha do usuário: "só um painel de ajuda").

O vídeo é achado pelo nome do arquivo que está subindo: a entrega no PC usa o título como nome do .mp4
(entrega_pc.json), mas pode ser também o nome da pasta do projeto ou o título do kit. Tudo sai do publicacao.json da
pasta do projeto, então funciona com a fábrica desligada."""
import json
import re
import unicodedata
from pathlib import Path


def _ler(arquivo: Path) -> dict:
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def normalizar(texto: str) -> str:
    """Sem acento, sem extensão, só letras e números separados por espaço: 'Desextinção: Os...mp4' -> 'desextincao os'."""
    texto = re.sub(r"\.(mp4|mov|mkv|webm|avi|m4v|wmv|flv|mpe?g)$", "", (texto or "").strip(), flags=re.I)
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", texto))


def _nomes(pasta: Path) -> list[str]:
    """Os nomes que o arquivo do vídeo pode ter: o da entrega, o título do kit, o da entrega no Radar e o da pasta."""
    pub, proj, entrega = _ler(pasta / "publicacao.json"), _ler(pasta / "projeto.json"), _ler(pasta / "entrega_pc.json")
    nomes = [Path(str(entrega.get("video") or "").replace("\\", "/")).name, pub.get("titulo"),
             (pub.get("textos") or {}).get("titulo"), proj.get("titulo_entrega"), pasta.name]
    return [n for n in (normalizar(str(x)) for x in nomes if x) if n]


def _projetos(raiz: Path) -> list[Path]:
    """Os projetos com kit de publicação, os mais recentes primeiro."""
    try:
        pastas = [p for p in raiz.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "publicacao.json").exists()]
    except OSError:
        return []
    return sorted(pastas, key=lambda p: (p / "publicacao.json").stat().st_mtime, reverse=True)


def achar(raiz: Path, arquivo: str) -> str | None:
    """O nome do projeto cujo vídeo tem esse nome de arquivo (igual primeiro; depois um contendo o outro)."""
    alvo = normalizar(arquivo)
    if len(alvo) < 6 or alvo in ("final", "video", "final video"):
        return None
    projetos = [(p.name, _nomes(p)) for p in _projetos(raiz)]
    for nome, nomes in projetos:
        if alvo in nomes:
            return nome
    for nome, nomes in projetos:
        if any(len(n) >= 12 and (n in alvo or alvo in n) for n in nomes):
            return nome
    return None


def opcoes(raiz: Path, limite: int = 40) -> list[dict]:
    """Para escolher na mão quando o nome do arquivo não diz qual é."""
    return [{"nome": p.name, "titulo": _titulo(p)} for p in _projetos(raiz)[:limite]]


def _titulo(pasta: Path) -> str:
    pub = _ler(pasta / "publicacao.json")
    return str(pub.get("titulo") or (pub.get("textos") or {}).get("titulo") or pasta.name)


def kit(pasta: Path) -> dict:
    """O que vai nos campos do Studio, já no formato de colar (as tags separadas por vírgula, como o Studio aceita)."""
    pub = _ler(pasta / "publicacao.json")
    textos = pub.get("textos") or {}
    tags = [str(t).strip() for t in (pub.get("tags") or textos.get("tags") or []) if str(t).strip()]
    descricao = str(pub.get("descricao") or textos.get("resumo") or "")
    capitulos = [c for c in pub.get("capitulos") or [] if isinstance(c, dict)]
    return {
        "nome": pasta.name,
        "titulo": _titulo(pasta),
        "titulos_alt": [str(t) for t in pub.get("titulos_alt") or textos.get("titulos_alt") or []],
        "descricao": descricao,
        "tags": tags,
        "hashtags": [str(h) for h in pub.get("hashtags") or textos.get("hashtags") or []],
        "comentario_fixado": str(pub.get("comentario_fixado") or textos.get("comentario_fixado") or ""),
        # a descrição já traz os capítulos; o mid-roll fica melhor entre eles
        "capitulos": [{"tempo": str(c.get("tempo", "")), "nome": str(c.get("nome", "")), "inicio": c.get("inicio")} for c in capitulos],
        "sintetico": bool(pub.get("sintetico")),
        "legenda": str(pub.get("legenda") or ""),
        "duracao": _duracao(pasta),
    }


def _duracao(pasta: Path) -> float | None:
    """Os segundos do vídeo (anúncio no meio só a partir de 8 minutos), pela narração alinhada da fábrica."""
    valor = _ler(pasta / "alinhamento.json").get("duracao")
    return float(valor) if isinstance(valor, (int, float)) and valor > 0 else None
