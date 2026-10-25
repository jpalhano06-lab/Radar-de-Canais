"""Banco do Radar (SQLite): contas, sessões, canais e vídeos medidos, salvos, achados, cota e garimpos."""
import hashlib
import json
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from .config import DADOS

ARQUIVO = DADOS / "radar.db"
_TRAVA = threading.RLock()
BRASILIA = timezone(timedelta(hours=-3))

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    nome TEXT NOT NULL DEFAULT '',
    senha_hash TEXT NOT NULL,
    admin INTEGER NOT NULL DEFAULT 0,
    plano TEXT NOT NULL DEFAULT 'gratis',
    vence TEXT NOT NULL DEFAULT '',
    criado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessoes (
    token_hash TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'site',
    criado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS canais (
    id TEXT PRIMARY KEY,
    titulo TEXT NOT NULL DEFAULT '',
    handle TEXT NOT NULL DEFAULT '',
    foto TEXT NOT NULL DEFAULT '',
    pais TEXT NOT NULL DEFAULT '',
    idioma TEXT NOT NULL DEFAULT '',
    inscritos INTEGER,
    videos_total INTEGER,
    views_total INTEGER,
    criado_em TEXT NOT NULL DEFAULT '',
    primeiro_video TEXT NOT NULL DEFAULT '',
    primeiro_exato INTEGER NOT NULL DEFAULT 0,
    ultimo_video TEXT NOT NULL DEFAULT '',
    base_longos REAL,
    base_curtos REAL,
    media_longos REAL,
    longos_medidos INTEGER NOT NULL DEFAULT 0,
    fase TEXT NOT NULL DEFAULT '',
    nicho TEXT NOT NULL DEFAULT '',
    sem_rosto INTEGER,
    raridade TEXT NOT NULL DEFAULT '',
    no_radar INTEGER NOT NULL DEFAULT 0,
    descoberto TEXT NOT NULL DEFAULT '',
    medido TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS canais_radar ON canais(no_radar, media_longos);
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    canal_id TEXT NOT NULL DEFAULT '',
    titulo TEXT NOT NULL DEFAULT '',
    publicado TEXT NOT NULL DEFAULT '',
    duracao_s INTEGER,
    views INTEGER,
    curtidas INTEGER,
    comentarios INTEGER,
    tags TEXT NOT NULL DEFAULT '[]',
    medido TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS videos_canal ON videos(canal_id, publicado);
CREATE TABLE IF NOT EXISTS leituras (
    video_id TEXT NOT NULL,
    quando TEXT NOT NULL,
    views INTEGER NOT NULL,
    PRIMARY KEY (video_id, quando)
);
CREATE TABLE IF NOT EXISTS outliers (
    video_id TEXT PRIMARY KEY,
    canal_id TEXT NOT NULL,
    nota REAL NOT NULL,
    achado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS salvos (
    usuario_id INTEGER NOT NULL,
    canal_id TEXT NOT NULL,
    criado TEXT NOT NULL,
    procurado TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (usuario_id, canal_id)
);
CREATE TABLE IF NOT EXISTS achados (
    usuario_id INTEGER NOT NULL,
    canal_id TEXT NOT NULL,
    por_causa_de TEXT NOT NULL,
    criado TEXT NOT NULL,
    PRIMARY KEY (usuario_id, canal_id)
);
CREATE TABLE IF NOT EXISTS cota (
    dia TEXT NOT NULL,
    chave TEXT NOT NULL,
    unidades INTEGER NOT NULL DEFAULT 0,
    esgotada INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dia, chave)
);
CREATE TABLE IF NOT EXISTS cota_motivo (
    dia TEXT NOT NULL,
    motivo TEXT NOT NULL,
    chamadas INTEGER NOT NULL DEFAULT 0,
    unidades INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dia, motivo)
);
CREATE TABLE IF NOT EXISTS garimpos (
    id INTEGER PRIMARY KEY,
    inicio TEXT NOT NULL,
    fim TEXT NOT NULL DEFAULT '',
    unidades INTEGER NOT NULL DEFAULT 0,
    buscas INTEGER NOT NULL DEFAULT 0,
    canais_novos INTEGER NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'rodando',
    linhas TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS buscas_feitas (
    termo TEXT PRIMARY KEY,
    nicho TEXT NOT NULL,
    quando TEXT NOT NULL,
    canais INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS historico (
    canal_id TEXT NOT NULL,
    dia TEXT NOT NULL,
    inscritos INTEGER,
    views_total INTEGER,
    videos_total INTEGER,
    PRIMARY KEY (canal_id, dia)
);
CREATE TABLE IF NOT EXISTS ideias_salvas (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL,
    canal_id TEXT NOT NULL DEFAULT '',
    video_id TEXT NOT NULL,
    titulo TEXT NOT NULL DEFAULT '',
    criado TEXT NOT NULL,
    UNIQUE (usuario_id, canal_id, video_id)
);
CREATE TABLE IF NOT EXISTS depoimentos (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    canal TEXT NOT NULL DEFAULT '',
    resultado TEXT NOT NULL DEFAULT '',
    texto TEXT NOT NULL DEFAULT '',
    print TEXT NOT NULL DEFAULT '',
    quando TEXT NOT NULL,
    mostrar INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS modelar (
    usuario_id INTEGER NOT NULL,
    video_id TEXT NOT NULL,
    estado TEXT NOT NULL,
    quando TEXT NOT NULL,
    PRIMARY KEY (usuario_id, video_id)
);
CREATE TABLE IF NOT EXISTS thumb_projetos (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL,
    canal_id TEXT NOT NULL DEFAULT '',
    nome TEXT NOT NULL,
    prompt TEXT NOT NULL,
    criado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS radar_projetos (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL,
    canal_id TEXT NOT NULL DEFAULT '',
    nome TEXT NOT NULL,
    paises TEXT NOT NULL DEFAULT '[]',
    criado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS treinamentos (
    usuario_id INTEGER NOT NULL,
    canal_id TEXT NOT NULL,
    referencias TEXT NOT NULL DEFAULT '[]',
    positivos TEXT NOT NULL DEFAULT '[]',
    negativos TEXT NOT NULL DEFAULT '[]',
    palavras TEXT NOT NULL DEFAULT '{}',
    termos TEXT NOT NULL DEFAULT '[]',
    feito TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (usuario_id, canal_id)
);
CREATE TABLE IF NOT EXISTS treino (
    usuario_id INTEGER NOT NULL,
    canal_id TEXT NOT NULL,
    item TEXT NOT NULL,
    feito TEXT NOT NULL,
    PRIMARY KEY (usuario_id, canal_id, item)
);
CREATE TABLE IF NOT EXISTS resultado_postado (
    usuario_id INTEGER NOT NULL,
    projeto TEXT NOT NULL,
    item TEXT NOT NULL,
    quando TEXT NOT NULL,
    PRIMARY KEY (usuario_id, projeto, item)
);
CREATE TABLE IF NOT EXISTS resultado_publicado (
    usuario_id INTEGER NOT NULL,
    projeto TEXT NOT NULL,
    video_id TEXT NOT NULL,
    PRIMARY KEY (usuario_id, projeto)
);
CREATE TABLE IF NOT EXISTS resultado_canal (
    usuario_id INTEGER NOT NULL,
    projeto TEXT NOT NULL,
    canal TEXT NOT NULL,
    PRIMARY KEY (usuario_id, projeto)
);
CREATE TABLE IF NOT EXISTS canais_config (
    usuario_id INTEGER NOT NULL,
    canal_id TEXT NOT NULL,
    dados TEXT NOT NULL DEFAULT '{}',
    criado TEXT NOT NULL,
    PRIMARY KEY (usuario_id, canal_id)
);
CREATE TABLE IF NOT EXISTS alvos (
    usuario_id INTEGER NOT NULL,
    canal_id TEXT NOT NULL,
    video_id TEXT NOT NULL,
    titulo TEXT NOT NULL DEFAULT '',
    criado TEXT NOT NULL,
    PRIMARY KEY (usuario_id, canal_id, video_id)
);
CREATE TABLE IF NOT EXISTS canais_inscritos (
    usuario_id INTEGER NOT NULL,
    canal_id TEXT NOT NULL,
    ref_canal_id TEXT NOT NULL,
    criado TEXT NOT NULL,
    PRIMARY KEY (usuario_id, canal_id, ref_canal_id)
);
CREATE TABLE IF NOT EXISTS bloqueios (
    usuario_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    valor TEXT NOT NULL,
    rotulo TEXT NOT NULL DEFAULT '',
    criado TEXT NOT NULL,
    PRIMARY KEY (usuario_id, tipo, valor)
);
CREATE TABLE IF NOT EXISTS studio (
    usuario_id INTEGER NOT NULL,
    canal_id TEXT NOT NULL,
    titulo TEXT NOT NULL DEFAULT '',
    refresh_token TEXT NOT NULL DEFAULT '',
    access_token TEXT NOT NULL DEFAULT '',
    expira REAL NOT NULL DEFAULT 0,
    conectado TEXT NOT NULL,
    PRIMARY KEY (usuario_id, canal_id)
);
CREATE TABLE IF NOT EXISTS projetos_roteiro (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    instrucoes TEXT NOT NULL DEFAULT '',
    criado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meus_canais (
    usuario_id INTEGER NOT NULL,
    canal_id TEXT NOT NULL,
    criado TEXT NOT NULL,
    PRIMARY KEY (usuario_id, canal_id)
);
CREATE TABLE IF NOT EXISTS convites (
    codigo_hash TEXT PRIMARY KEY,
    nota TEXT NOT NULL DEFAULT '',
    criado TEXT NOT NULL,
    usado_por INTEGER,
    usado_em TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS termos_auto (
    termo TEXT PRIMARY KEY,
    nicho TEXT NOT NULL,
    origem TEXT NOT NULL DEFAULT '',
    criado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS producoes_fila (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL,
    criado TEXT NOT NULL,
    atualizado TEXT NOT NULL,
    estado TEXT NOT NULL,
    ordem INTEGER NOT NULL,
    pedido TEXT NOT NULL DEFAULT '{}',
    roteiro TEXT NOT NULL DEFAULT '',
    projeto TEXT NOT NULL DEFAULT '',
    aprovado INTEGER NOT NULL DEFAULT 0,
    erro TEXT NOT NULL DEFAULT '',
    passo TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ajustes (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saldos_informados (
    servico TEXT PRIMARY KEY,
    valor REAL NOT NULL,
    quando TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS traducoes (
    chave TEXT PRIMARY KEY,
    dados TEXT NOT NULL,
    criado TEXT NOT NULL
);
"""


# colunas que entraram depois do primeiro banco: são criadas no banco que já existe
COLUNAS_NOVAS = {
    "canais": {"subnicho": "TEXT NOT NULL DEFAULT ''", "velocidade": "REAL", "ganho_7d": "INTEGER",
               "anuncios": "INTEGER", "membros": "INTEGER",    # monetização vista pela extensão (1, 0 ou sem saber)
               "repescado": "TEXT NOT NULL DEFAULT ''"},       # quando o garimpo.repescar mediu o canal de novo
    # painel: a ordem e as abas escondidas do menu de cada pessoa. Fica fora de `prefs` porque salvar_prefs reescreve
    # aquele JSON inteiro a cada resposta das perguntas, e levaria o menu junto
    "usuarios": {"prefs": "TEXT NOT NULL DEFAULT '{}'", "painel": "TEXT NOT NULL DEFAULT '{}'"},
    "salvos": {"pasta": "TEXT NOT NULL DEFAULT ''"},          # a pasta em que a pessoa guardou aquele canal
    "projetos_roteiro": {"ideal_para": "TEXT NOT NULL DEFAULT ''"},
    "buscas_feitas": {"vezes": "INTEGER NOT NULL DEFAULT 0", "total": "INTEGER NOT NULL DEFAULT 0", "zeros": "INTEGER NOT NULL DEFAULT 0"},
}


def _migrar(c: sqlite3.Connection) -> None:
    for tabela, colunas in COLUNAS_NOVAS.items():
        existentes = {l[1] for l in c.execute(f"PRAGMA table_info({tabela})")}
        for nome, tipo in colunas.items():
            if nome not in existentes:
                c.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")
    c.execute("CREATE INDEX IF NOT EXISTS canais_subnicho ON canais(subnicho)")
    c.commit()


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hoje_pacifico() -> str:
    """A cota da API do YouTube vira à meia-noite do horário do Pacífico (UTC-8, ou -7 no verão de lá)."""
    return (datetime.now(timezone.utc) - timedelta(hours=8)).date().isoformat()


def _conexao() -> sqlite3.Connection:
    DADOS.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ARQUIVO, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


_CON = None


def con() -> sqlite3.Connection:
    global _CON
    if _CON is None:
        with _TRAVA:
            if _CON is None:
                c = _conexao()
                c.executescript(ESQUEMA)
                _migrar(c)
                _CON = c
    return _CON


def um(sql: str, *args) -> dict | None:
    with _TRAVA:
        linha = con().execute(sql, args).fetchone()
    return dict(linha) if linha else None


def todos(sql: str, *args) -> list[dict]:
    with _TRAVA:
        return [dict(l) for l in con().execute(sql, args).fetchall()]


def executar(sql: str, *args) -> int:
    with _TRAVA:
        c = con()
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid


def mudou(sql: str, *args) -> int:
    """Como o executar, mas diz quantas linhas mexeu: UPDATE e DELETE não têm lastrowid para responder isso."""
    with _TRAVA:
        c = con()
        cur = c.execute(sql, args)
        c.commit()
        return cur.rowcount


def varios(sql: str, linhas: list[tuple]) -> None:
    if not linhas:
        return
    with _TRAVA:
        c = con()
        c.executemany(sql, linhas)
        c.commit()


def gravar(tabela: str, chave: str, dados: dict) -> None:
    """INSERT ou UPDATE pelos campos dados (os outros ficam como estão)."""
    campos = list(dados)
    sql = (f"INSERT INTO {tabela} ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))}) "
           f"ON CONFLICT({chave}) DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in campos if c != chave))
    executar(sql, *[json.dumps(v) if isinstance(v, (list, dict)) else v for v in dados.values()])


# ---------------------------------------------------------------- senhas e tokens

def hash_senha(senha: str) -> str:
    sal = secrets.token_hex(16)
    return sal + "$" + hashlib.pbkdf2_hmac("sha256", senha.encode(), sal.encode(), 200_000).hex()


def senha_confere(senha: str, guardado: str) -> bool:
    sal, _, valor = guardado.partition("$")
    return secrets.compare_digest(hashlib.pbkdf2_hmac("sha256", senha.encode(), sal.encode(), 200_000).hex(), valor)


def novo_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
