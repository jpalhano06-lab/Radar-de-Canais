"""Configuração do Radar: nome do produto, chaves e limites.

As chaves vêm do finder/.env. Rodando dentro da pasta da fábrica, o que faltar é lido do .env da fábrica
(YOUTUBE_API_KEY, GROQ_API_KEY...), sem copiar nada."""
import os
import re
from pathlib import Path

from dotenv import dotenv_values

NOME = "Radar de Canais"          # o nome do produto, num lugar só
RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
PORTA = int(os.environ.get("RADAR_PORTA", "8400"))


def _pasta_da_fabrica(proprio: dict) -> Path:
    """A pasta da fábrica: RADAR_FABRICA no .env do Radar (quando ele mora numa pasta própria) ou a pasta de cima."""
    caminho = os.environ.get("RADAR_FABRICA") or proprio.get("RADAR_FABRICA")
    return Path(caminho).expanduser() if caminho else RAIZ.parent


def _ambiente() -> dict:
    valores = {}
    proprio = {k: v for k, v in dotenv_values(RAIZ / ".env").items() if v} if (RAIZ / ".env").exists() else {}
    # o .env da fábrica só vale quando a pasta é mesmo a fábrica: no computador de um sócio, a pasta de cima é
    # Downloads ou Documentos, e um .env de outro programa ali não pode virar chave do Radar
    fabrica = _pasta_da_fabrica(proprio)
    if (fabrica / ".env").exists() and (fabrica / "fabrica").is_dir():
        valores.update({k: v for k, v in dotenv_values(fabrica / ".env").items() if v})
    valores.update(proprio)
    valores.update({k: v for k, v in os.environ.items() if v and re.match(r"(YOUTUBE|GROQ|RADAR)_", k)})
    return valores


AMBIENTE = _ambiente()
FABRICA = _pasta_da_fabrica(AMBIENTE)


def recarregar() -> None:
    """Lê os .env de novo depois que a aba Integrações grava uma chave (o mesmo dicionário, para quem já o importou)."""
    novo = _ambiente()
    AMBIENTE.clear()
    AMBIENTE.update(novo)


def _numeradas(prefixo: str) -> list[str]:
    """PREFIXO, PREFIXO1, PREFIXO2... e PREFIXOS com várias separadas por vírgula. Sem repetir."""
    chaves = []
    for nome, valor in sorted(AMBIENTE.items()):
        if re.fullmatch(prefixo + r"S?\d*", nome):
            for parte in valor.split(","):
                parte = parte.strip()
                if parte and parte not in chaves:
                    chaves.append(parte)
    return chaves


def chaves_youtube() -> list[str]:
    return _numeradas("YOUTUBE_API_KEY")


def chaves_groq() -> list[str]:
    return _numeradas("GROQ_API_KEY")


# A API do YouTube dá 10.000 unidades por dia a cada chave (projeto do Google Cloud). Uma busca custa 100;
# ler 50 vídeos ou 50 canais custa 1. A reserva fica para a extensão de quem está navegando.
COTA_POR_CHAVE = int(AMBIENTE.get("RADAR_COTA_POR_CHAVE", "10000"))
COTA_DO_GARIMPO = float(AMBIENTE.get("RADAR_COTA_GARIMPO", "0.6"))   # fração da cota do dia para o garimpo

MODELO_TEXTO = AMBIENTE.get("RADAR_MODELO_TEXTO", "openai/gpt-oss-120b")
MODELO_VISAO = AMBIENTE.get("RADAR_MODELO_VISAO", "qwen/qwen3.8-27b")

# o que cada plano abre
PLANOS = {
    "gratis": {"nome": "Grátis", "preco": 0, "recursos": ["extensao"]},
    "lite": {"nome": "Lite", "preco": 47, "recursos": ["extensao", "salvar", "parecidos", "linguas", "achados"]},
    "pro": {"nome": "Pro", "preco": 97,
            "recursos": ["extensao", "salvar", "parecidos", "linguas", "achados", "radar", "ranking", "outliers"]},
}


def pode(plano: str, recurso: str) -> bool:
    return recurso in PLANOS.get(plano or "gratis", PLANOS["gratis"])["recursos"]
