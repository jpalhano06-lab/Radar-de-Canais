"""As máquinas que produzem para a fila, além desta (como o Robô do Dotti: o site manda, a máquina faz).

Cada máquina recebe uma chave, mostrada uma vez só: aqui fica o hash dela. O pedido com destino "robo" não vai para a
fábrica desta máquina: ele espera na fila, com o roteiro pronto, até uma máquina reivindicar.

Reivindicar dá um lease de LEASE_SEGUNDOS, que a máquina renova batendo enquanto trabalha. Máquina que some deixa o
lease vencer, e o pedido volta para a fila (`expirar`, em cada volta do vigia). Se ela voltar depois disso, o lease
velho é recusado: dois computadores nunca fazem o mesmo vídeo achando que é o dono.

O vídeo fica na máquina que fez. O que volta para cá é a prova da entrega: tamanho, duração e SHA-256 do arquivo.
"""
import hashlib
import json
import os
import secrets
import tempfile
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import banco, fila, roteiro_claude

LEASE_SEGUNDOS = 300
ONLINE_SEGUNDOS = 120
MAX_EVENTOS = 50


# O que vai para a outra máquina. Lista do que entra, e não do que sai: a pasta da fábrica tem .env.antes, chaves do
# painel e dados de clientes, e um arquivo novo com segredo não pode ir embora porque ninguém lembrou de bloquear.
PACOTE_PASTAS = ("fabrica", "perfis", "simbolos", "motores_voz", "musicas")
PACOTE_ARQUIVOS = ("pyproject.toml", "uv.lock", "config.yaml", ".env.exemplo", "ROBO.ps1", "INSTALAR-ROBO.ps1", "README.md")
FORA_DO_PACOTE = (".pyc", ".antes", ".antes-token", ".key", ".db", ".log")


def _entra_no_pacote(caminho: Path) -> bool:
    nome = caminho.name.lower()
    return ("__pycache__" not in caminho.parts and not nome.endswith(FORA_DO_PACOTE) and ".antes" not in nome
            and not nome.startswith(".env"))


def pacote(raiz: Path, destino: Path | None = None) -> Path:
    """Monta o zip da fábrica que o instalador baixa. Sem .env, sem projetos e sem nada de cliente."""
    if destino is None:
        aberto, nome = tempfile.mkstemp(suffix=".zip", prefix="fabrica-robo-")
        os.close(aberto)  # no Windows o arquivo aberto aqui não deixaria apagar depois da entrega
        destino = Path(nome)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as saida:
        for nome in PACOTE_ARQUIVOS:
            if (raiz / nome).is_file():
                saida.write(raiz / nome, nome)
        for pasta in PACOTE_PASTAS:
            for arquivo in sorted((raiz / pasta).rglob("*")):
                if arquivo.is_file() and _entra_no_pacote(arquivo):
                    saida.write(arquivo, arquivo.relative_to(raiz).as_posix())
    return destino


class LeaseVelha(RuntimeError):
    """A máquina perdeu este pedido: o lease venceu, foi trocado ou o pedido saiu da fila."""


def _hash(chave: str) -> str:
    return hashlib.sha256(chave.encode()).hexdigest()


def criar(nome: str) -> dict:
    """Cria a máquina e devolve a chave. É a única vez que ela aparece."""
    nome = str(nome or "").strip()[:60]
    if not nome:
        raise ValueError("Dê um nome para a máquina.")
    chave = "rdm_" + secrets.token_urlsafe(32)
    mid = banco.executar("INSERT INTO maquinas (nome, chave_hash, criada) VALUES (?,?,?)", nome, _hash(chave), banco.agora())
    return {"id": mid, "nome": nome, "chave": chave}


def _online(visto_em: str) -> bool:
    if not visto_em:
        return False
    limite = datetime.now(timezone.utc) - timedelta(seconds=ONLINE_SEGUNDOS)
    return datetime.fromisoformat(visto_em) >= limite


def listar() -> list[dict]:
    """As máquinas ativas, sem a chave, com o que está rodando em cada uma."""
    lista = []
    for m in banco.todos("SELECT id, nome, criada, visto_em, capacidades FROM maquinas WHERE ativa=1 ORDER BY id"):
        fazendo = banco.todos("SELECT id, passo FROM producoes_fila WHERE estado='produzindo' AND maquina_id=?", m["id"])
        lista.append({**m, "capacidades": json.loads(m["capacidades"] or "{}"), "online": _online(m["visto_em"]),
                      "fazendo": fazendo})
    return lista


def revogar(mid: int) -> bool:
    """Tira a máquina. O que ela estava fazendo volta para a fila, e a chave para de valer na hora."""
    mexeu = banco.mudou("UPDATE maquinas SET ativa=0 WHERE id=? AND ativa=1", mid)
    for linha in banco.todos("SELECT id FROM producoes_fila WHERE estado='produzindo' AND maquina_id=?", mid):
        _devolver(linha["id"], "A máquina foi retirada; o vídeo voltou para a fila.")
    return bool(mexeu)


def autenticar(chave: str) -> dict | None:
    if not chave:
        return None
    maquina = banco.um("SELECT id, nome FROM maquinas WHERE chave_hash=? AND ativa=1", _hash(chave))
    if maquina:
        banco.executar("UPDATE maquinas SET visto_em=? WHERE id=?", banco.agora(), maquina["id"])
    return maquina


def _devolver(fid: int, passo: str) -> None:
    fila.mudar(fid, "na_fila", de=("produzindo",), maquina_id=None, lease="", lease_ate=0, passo=passo)


def expirar() -> list[int]:
    """Devolve à fila o que a máquina largou sem avisar. Chamado em cada volta do vigia."""
    vencidos = banco.todos("SELECT id FROM producoes_fila WHERE estado='produzindo' AND maquina_id IS NOT NULL "
                           "AND lease_ate < ?", time.time())
    for linha in vencidos:
        _devolver(linha["id"], "A máquina parou de responder; o vídeo voltou para a fila.")
    return [l["id"] for l in vencidos]


def _trabalho(linha: dict, lease: str) -> dict:
    """Tudo o que a máquina precisa para fazer o vídeo sem falar com mais ninguém."""
    pedido = json.loads(linha["pedido"])
    cfg = fila._padrao()[2](linha["usuario_id"], pedido["canal_id"]) if pedido.get("canal_id") else {}
    pasta, meta = roteiro_claude._do_usuario(linha["usuario_id"], linha["roteiro"])
    config, do_perfil = roteiro_claude.ajustes_do_video(fila.opcoes_do(linha["usuario_id"], pedido, cfg))
    return {"id": linha["id"], "lease": lease, "lease_segundos": LEASE_SEGUNDOS, "projeto": f"robo-{linha['id']}",
            "perfil": fila.perfil_do(pedido, cfg), "titulo": pedido.get("titulo", ""),
            "titulo_entrega": roteiro_claude.titulo_de_entrega(meta),
            "roteiro": (pasta / "roteiro.txt").read_text(encoding="utf-8"),
            "config_override": config, "perfil_override": do_perfil}


def reivindicar(maquina: dict, capacidades: dict | None = None) -> dict | None:
    """O primeiro pedido para robô com o roteiro pronto, ou None. `fila.mudar` com `de` é o que garante que duas
    máquinas pedindo ao mesmo tempo não levam o mesmo vídeo."""
    banco.executar("UPDATE maquinas SET capacidades=? WHERE id=?", json.dumps(capacidades or {}, ensure_ascii=False), maquina["id"])
    for linha in banco.todos("SELECT * FROM producoes_fila WHERE estado='na_fila' AND roteiro != '' ORDER BY ordem"):
        if json.loads(linha["pedido"]).get("destino") != "robo":
            continue
        lease = secrets.token_urlsafe(16)
        if not fila.mudar(linha["id"], "produzindo", de=("na_fila",), maquina_id=maquina["id"], lease=lease,
                          lease_ate=time.time() + LEASE_SEGUNDOS, projeto=f"robo-{linha['id']}",
                          passo=f"Na máquina {maquina['nome']}"):
            continue
        try:
            return _trabalho(linha, lease)
        except (RuntimeError, OSError, ValueError) as erro:
            fila.mudar(linha["id"], "erro", de=("produzindo",), maquina_id=None, lease="", lease_ate=0,
                       erro=f"O roteiro não pôde ir para a máquina: {str(erro)[:300]}", passo="")
    return None


def _do_lease(maquina: dict, fid: int, lease: str) -> dict:
    linha = banco.um("SELECT * FROM producoes_fila WHERE id=? AND estado='produzindo' AND maquina_id=?", fid, maquina["id"])
    if not linha or not lease or not secrets.compare_digest(str(linha["lease"]), str(lease)):
        raise LeaseVelha("lease_velha")
    return linha


def bater(maquina: dict, fid: int, lease: str, passo: str = "", eventos: list | None = None) -> dict:
    """Renova o lease e guarda o andamento. Levanta LeaseVelha quando o pedido não é mais desta máquina."""
    linha = _do_lease(maquina, fid, lease)
    guardados = (json.loads(linha["eventos"] or "[]") + [str(e)[:300] for e in (eventos or [])])[-MAX_EVENTOS:]
    banco.executar("UPDATE producoes_fila SET lease_ate=?, passo=?, eventos=?, atualizado=? WHERE id=?",
                   time.time() + LEASE_SEGUNDOS, str(passo)[:200] or linha["passo"], json.dumps(guardados, ensure_ascii=False),
                   banco.agora(), fid)
    return {"lease_segundos": LEASE_SEGUNDOS}


def concluir(maquina: dict, fid: int, lease: str, prova: dict) -> bool:
    """O vídeo ficou pronto. Sem prova de um arquivo de verdade o pedido não vira entregue."""
    _do_lease(maquina, fid, lease)
    if not (int(prova.get("bytes") or 0) > 0 and float(prova.get("duracao") or 0) > 0 and prova.get("sha256")):
        raise ValueError("A prova da entrega precisa do tamanho, da duração e do SHA-256 do vídeo.")
    return fila.mudar(fid, "entregue", de=("produzindo",), lease="", lease_ate=0, passo="",
                      prova=json.dumps({**prova, "maquina": maquina["nome"]}, ensure_ascii=False))


def falhar(maquina: dict, fid: int, lease: str, erro: str) -> bool:
    """A máquina desistiu. O "Tentar de novo" manda de volta para a fila, para ela ou para outra."""
    _do_lease(maquina, fid, lease)
    return fila.mudar(fid, "erro", de=("produzindo",), maquina_id=None, lease="", lease_ate=0, passo="",
                      erro=f"Na máquina {maquina['nome']}: {str(erro)[:400]}")
