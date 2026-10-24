"""A ordem das duas listas de Descobrir: o lado que a tela pede e a conta do "na hora de copiar"."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import metricas, servidor  # noqa: E402


def test_toda_ordem_pode_ser_virada():
    assert servidor._ordem_sql("media", "") == "c.base_longos DESC"
    assert servidor._ordem_sql("media", "asc") == "c.base_longos ASC"
    assert servidor._ordem_sql("inscritos", "asc") == "c.inscritos ASC"
    # o aleatório não tem lado
    assert servidor._ordem_sql("aleatorio", "asc") == "RANDOM()"
    # ordem que não existe cai na de sempre, em vez de quebrar a consulta
    assert servidor._ordem_sql("inventada", "") == "c.base_longos DESC"


def test_ordem_de_video_tambem_vira():
    assert servidor._ordem_videos("nota", "") == servidor._NOTA_VIVA + " DESC"
    assert servidor._ordem_videos("nota", "asc") == servidor._NOTA_VIVA + " ASC"
    assert servidor._ordem_videos("views", "asc") == "v.views ASC"
    assert servidor._ordem_videos("inventada", "") == servidor._NOTA_VIVA + " DESC"


def test_na_hora_de_copiar_em_sql_da_a_mesma_ordem_que_a_conta_do_radar():
    """O `pontos` é o metricas.pontos_do_ranking escrito em SQL. Se os dois divergirem, a lista mente."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE canais (id TEXT, base_longos REAL, primeiro_video TEXT, fase TEXT)")
    canais = [
        ("novo-crescendo", 120000.0, "2026-08-01T00:00:00Z", "crescendo"),
        ("velho-grande", 400000.0, "2019-01-01T00:00:00Z", "estavel"),
        ("novinho", 60000.0, "2026-10-01T00:00:00Z", "nascendo"),
        ("caindo", 300000.0, "2024-01-01T00:00:00Z", "caindo"),
        ("parado", 900000.0, "2021-06-01T00:00:00Z", "parado"),
        ("sem-fase", 150000.0, "2025-03-01T00:00:00Z", ""),
    ]
    con.executemany("INSERT INTO canais VALUES (?,?,?,?)", canais)

    em_sql = [l["id"] for l in con.execute(f"SELECT * FROM canais c ORDER BY {servidor._ordem_sql('pontos', '')}")]
    em_python = [c["id"] for c in sorted(
        (dict(l) for l in con.execute("SELECT * FROM canais")),
        key=lambda c: -metricas.pontos_do_ranking(c["base_longos"], metricas.meses_postando(c["primeiro_video"]), c["fase"]))]
    assert em_sql == em_python


def test_filtros_novos_da_lista_de_canais():
    onde, args = servidor._filtro_canais({"com_outlier": "10", "subnicho_ate": "2", "estourando_min": "5"})
    juntos = " AND ".join(onde)
    assert "SELECT canal_id FROM outliers WHERE nota >= ?" in juntos
    assert "GROUP BY subnicho HAVING COUNT(*) <= ?" in juntos
    assert "c.base_longos * 1.0 / MAX(c.inscritos, 100) >= ?" in juntos
    assert args == [5.0, 10.0, 2.0]


def test_o_alerta_saiu_do_radar():
    """O Alerta virou um filtro da lista de canais: as rotas dele não existem mais."""
    caminhos = {r.path for r in servidor.app.routes}
    assert not any(c.startswith("/api/alertas") for c in caminhos)
    assert "/api/videos" in caminhos and "/api/visoes" in caminhos


def test_a_nota_do_video_e_recalculada_na_hora():
    """A nota gravada na tabela envelhece quando o normal do canal é corrigido: a lista usa a conta de agora."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE videos (id TEXT, views INTEGER, duracao_s INTEGER)")
    con.execute("CREATE TABLE canais (id TEXT, base_longos REAL, base_curtos REAL)")
    con.execute("INSERT INTO videos VALUES ('longo', 50000, 600), ('short', 9000, 60), ('sem-base', 100, 600)")
    con.execute("INSERT INTO canais VALUES ('c', 5000.0, 900.0)")
    vivas = {l["id"]: l["nota"] for l in con.execute(
        f"SELECT v.id, ROUND({servidor._NOTA_VIVA}, 1) AS nota FROM videos v, canais c")}
    # o longo mede contra o normal dos longos; o Short, contra o dos Shorts
    assert vivas["longo"] == 10.0 and vivas["short"] == 10.0
    assert vivas["longo"] == metricas.nota_outlier(50000, 5000.0)
    assert vivas["short"] == metricas.nota_outlier(9000, 900.0)


def test_canal_sem_normal_de_verdade_nao_vira_outlier():
    """Um canal cujo vídeo típico faz 19 views não tem razão nenhuma para calcular: ele fica fora da lista."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE videos (id TEXT, views INTEGER, duracao_s INTEGER)")
    con.execute("CREATE TABLE canais (id TEXT, base_longos REAL, base_curtos REAL)")
    con.execute("INSERT INTO videos VALUES ('v', 16137698, 600)")
    con.execute("INSERT INTO canais VALUES ('c', 19.0, NULL)")
    sobra = con.execute(f"SELECT COUNT(*) FROM videos v, canais c WHERE {servidor._NORMAL} >= {servidor.NORMAL_MINIMO}").fetchone()[0]
    assert sobra == 0


def test_o_piso_de_views_sai_das_outras_regras():
    """10x o normal, com o normal medido em pelo menos mil views, já é pedir vídeos de 10 mil para cima."""
    assert servidor.piso_de_views(10, 1000) == 10000
    assert servidor.piso_de_views(5, 1000) == 5000
    assert servidor.piso_de_views(20, 1000) == 20000
    # sem normal mínimo não há piso para anunciar
    assert servidor.piso_de_views(10, 0) == 0
    assert servidor.piso_de_views(0, 1000) == 0


def test_o_piso_nunca_e_negativo():
    assert servidor.piso_de_views(-5, 1000) == 0


def test_o_piso_padrao_bate_com_o_normal_minimo():
    assert servidor.piso_de_views(5, servidor.NORMAL_MINIMO) == 5 * servidor.NORMAL_MINIMO


def test_o_piso_da_lista_de_canais_e_o_do_garimpo():
    """Abaixo de 10 mil views por vídeo o canal nem teria entrado no Radar: pedir menos não traz nada de novo."""
    from radar import garimpo
    assert garimpo.MINIMO_POR_VIDEO == 10000


def test_o_banco_de_titulos_usa_a_nota_de_agora():
    """Igual à lista de vídeos: a nota gravada envelhece, e punha "846.313x" de canal sem base no topo do banco."""
    import sqlite3
    from fastapi.testclient import TestClient
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE videos (id TEXT, views INTEGER, duracao_s INTEGER)")
    con.execute("CREATE TABLE canais (id TEXT, base_longos REAL, base_curtos REAL)")
    con.execute("INSERT INTO videos VALUES ('sem-base', 16137698, 600)")
    con.execute("INSERT INTO canais VALUES ('c', 19.0, NULL)")
    fora = con.execute(
        f"SELECT COUNT(*) FROM videos v, canais c WHERE {servidor._NORMAL} >= {servidor.NORMAL_MINIMO}").fetchone()[0]
    assert fora == 0
    # e a rota existe e pede conta: o banco de títulos não é público
    assert TestClient(servidor.app).get("/api/titulos").status_code == 401
