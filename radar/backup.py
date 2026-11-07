"""A cópia de segurança semanal do Radar (pedido do usuário em 2026-11-06, depois da análise do app: tudo morava num disco só).

Guarda, em RADAR_BACKUP_PASTA (padrão: dados/backups), as 7 últimas cópias de:
- radar-AAAA-MM-DD.db.gz: o banco inteiro, copiado com o Radar ligado (a cópia do próprio SQLite não pega escrita pela metade);
- radar.bundle e fabrica.bundle: o histórico do código dos dois repositórios;
- fabrica-perfis-AAAA-MM-DD.zip: perfis, config.yaml e vozes, que podem estar sem commit.

A cópia pode ir para uma pasta de nuvem, então nada de segredo entra nela: os tokens do Studio e as sessões saem do banco
copiado, e o .env nunca entra. Depois de restaurar é preciso reconectar o Studio e entrar de novo.

Para restaurar: pare o Radar, descompacte o .gz em dados/radar.db, apague radar.db-wal e radar.db-shm e ligue o Radar. O
código volta com `git clone radar.bundle`. As imagens e os vídeos dos projetos não entram: são dezenas de GB.
"""
import gzip
import json
import shutil
import sqlite3
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from . import banco
from .config import AMBIENTE, DADOS, FABRICA, RAIZ

MANTER = 7
HORAS_ENTRE_COPIAS = 7 * 24  # de 7 em 7 dias, a pedido do usuário em 2026-11-06
CHAVE = "backup_ultimo"


def pasta() -> Path:
    return Path(AMBIENTE.get("RADAR_BACKUP_PASTA") or DADOS / "backups")


def _copiar_banco(destino: Path) -> Path:
    """radar-….db.gz sem segredo nenhum."""
    temporario = destino.with_suffix("")
    origem, copia = sqlite3.connect(banco.ARQUIVO), sqlite3.connect(temporario)
    try:
        origem.backup(copia)
        copia.execute("UPDATE studio SET refresh_token='', access_token=''")
        copia.execute("DELETE FROM sessoes")
        copia.commit()
    finally:
        origem.close()
        copia.close()
    with open(temporario, "rb") as entrada, gzip.open(destino, "wb", compresslevel=6) as saida:
        shutil.copyfileobj(entrada, saida, 1 << 20)
    temporario.unlink()
    return destino


def _copiar_codigo(raiz: Path, destino: Path) -> bool:
    r = subprocess.run(["git", "-C", str(raiz), "bundle", "create", str(destino), "--all"], capture_output=True, timeout=300)
    return r.returncode == 0


def _copiar_perfis(destino: Path) -> Path:
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for arquivo in [*sorted((FABRICA / "perfis").glob("*")), FABRICA / "config.yaml", FABRICA / "genaipro_vozes.json"]:
            if arquivo.is_file():
                z.write(arquivo, arquivo.relative_to(FABRICA))
    return destino


def _limpar(lugar: Path) -> None:
    for padrao in ("radar-*.db.gz", "fabrica-perfis-*.zip"):
        for velho in sorted(lugar.glob(padrao))[:-MANTER]:
            velho.unlink()


def fazer() -> dict:
    lugar, dia = pasta(), datetime.now(banco.BRASILIA).strftime("%Y-%m-%d")
    estado = {"quando": banco.agora(), "pasta": str(lugar), "erro": ""}
    try:
        lugar.mkdir(parents=True, exist_ok=True)
        arquivo = _copiar_banco(lugar / f"radar-{dia}.db.gz")
        estado["tamanho_mb"] = round(arquivo.stat().st_size / 1e6)
        _copiar_perfis(lugar / f"fabrica-perfis-{dia}.zip")
        codigo = {"radar": _copiar_codigo(RAIZ, lugar / "radar.bundle"), "fabrica": _copiar_codigo(FABRICA, lugar / "fabrica.bundle")}
        if not all(codigo.values()):
            estado["erro"] = "O código de " + ", ".join(k for k, v in codigo.items() if not v) + " não entrou na cópia."
        _limpar(lugar)
    except (OSError, sqlite3.Error, subprocess.SubprocessError) as erro:
        estado["erro"] = str(erro)[:300]
    banco.executar("INSERT OR REPLACE INTO ajustes (chave, valor) VALUES (?,?)", CHAVE, json.dumps(estado, ensure_ascii=False))
    return estado


def ultimo() -> dict:
    linha = banco.um("SELECT valor FROM ajustes WHERE chave=?", CHAVE)
    return json.loads(linha["valor"]) if linha else {}


def horas_desde_o_ultimo() -> float | None:
    quando = ultimo().get("quando")
    if not quando:
        return None
    marca = datetime.fromisoformat(quando)
    return (datetime.now(marca.tzinfo) - marca).total_seconds() / 3600


def na_hora() -> bool:
    """Sem cópia certa nos últimos 7 dias. A que falhou tenta de novo na próxima volta."""
    horas = horas_desde_o_ultimo()
    return horas is None or horas >= HORAS_ENTRE_COPIAS or bool(ultimo().get("erro"))
