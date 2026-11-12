"""A conferência do tempo do roteiro: antes de o roteiro sair para a fábrica, o Radar mede quantos minutos ele vai
dar no ritmo real da voz e corrige até cair dentro de 1 minuto do tempo pedido.

Pedido do usuário em 2026-11-01: "o Radar tá entregando vídeos com a duração errada, tem que conferir e colocar algo
que sempre confira o resultado e regule pra acertar cada vez mais; o vídeo de 30 min saiu com 17, o máximo de erro é
1 minuto". Aqui o Claude é falso (nenhuma chamada de verdade), para o teste rodar sem rede e sem assinatura."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar import roteiro_claude, tempo  # noqa: E402


def _mundo(monkeypatch, tmp_path):
    roteiros, fabrica = tmp_path / "roteiros", tmp_path / "fabrica"
    roteiros.mkdir()
    (fabrica / "projetos").mkdir(parents=True)
    monkeypatch.setattr(roteiro_claude, "PASTA", roteiros)
    monkeypatch.setattr(roteiro_claude, "FABRICA", fabrica)
    monkeypatch.setattr(tempo, "_da_api", lambda: {})
    monkeypatch.setattr(tempo, "MEDICOES_SEGUNDOS", 0)    # sem a conta guardada de outro teste
    return roteiros, fabrica


def _roteiro(roteiros, nome, *, minutos, palavras, ppm_usado, projeto, perfil="canal-x", lingua="inglês",
             conferencia=None):
    pasta = roteiros / nome
    pasta.mkdir()
    meta = {"titulo": nome, "minutos": minutos, "palavras": palavras, "lingua": lingua, "usuario_id": 1,
            "ritmo": {"ppm": ppm_usado}, "fabrica": {"projeto": projeto, "perfil": perfil, "palavras": palavras}}
    if conferencia:
        meta["conferencia"] = conferencia
    (pasta / "roteiro.json").write_text(json.dumps(meta), encoding="utf-8")
    return pasta


def _projeto(fabrica, nome, segundos):
    pasta = fabrica / "projetos" / nome
    pasta.mkdir(parents=True)
    (pasta / "alinhamento.json").write_text(json.dumps({"duracao": segundos}), encoding="utf-8")


def _texto(palavras: int) -> str:
    return " ".join(["palavra"] * palavras)


# ------------------------------------------------------------------------------------ a conta da conferência

def test_a_margem_que_o_usuario_aceita_e_de_um_minuto():
    assert tempo.MARGEM_MIN == 1.0


def test_conferir_diz_quantos_minutos_o_roteiro_vai_dar_e_quantas_palavras_faltam():
    c = tempo.conferir(palavras=3000, minutos=30, ppm=215)
    assert c["previsto_min"] == 14.0            # 3.000 palavras numa voz de 215 por minuto
    assert c["erro_min"] == -16.0 and not c["dentro"]
    assert (c["alvo_palavras"], c["faltam"]) == (6450, 3450)


def test_conferir_aceita_o_roteiro_que_cai_dentro_da_margem():
    c = tempo.conferir(palavras=6450, minutos=30, ppm=215)
    assert c["dentro"] and abs(c["erro_min"]) <= tempo.MARGEM_MIN


# ---------------------------------------------------------------- o roteiro curto é continuado até caber no tempo

def test_o_roteiro_curto_e_continuado_ate_cair_dentro_do_tempo(monkeypatch):
    """O caso que o usuário viu: 30 min pedidos e um roteiro de 17 minutos. Antes ele ia para a fábrica assim."""
    chamadas = []

    def falso(sistema, pedido, modelo=""):
        chamadas.append(pedido)
        return _texto(1500)

    monkeypatch.setattr(roteiro_claude, "_claude", falso)
    roteiro, conf = roteiro_claude._conferir_tamanho(_texto(3655), "sis", "ped", 30, {"ppm": 215, "de": "voz"})
    assert conf["dentro"], conf
    assert len(roteiro.split()) >= 6450 - 215    # chegou ao alvo das 30 min dentro da margem
    assert chamadas and "Continue o roteiro" in chamadas[0]


def test_uma_continuacao_fraca_nao_desiste_do_roteiro(monkeypatch):
    """Era o que fazia o vídeo sair curto: uma volta que voltava quase vazia parava o laço de vez."""
    respostas = ["", _texto(1400), _texto(1400)]

    monkeypatch.setattr(roteiro_claude, "_claude", lambda s, p, modelo="": respostas.pop(0) if respostas else "")
    roteiro, conf = roteiro_claude._conferir_tamanho(_texto(1000), "sis", "ped", 15, {"ppm": 215, "de": "voz"})
    assert len(roteiro.split()) == 3800          # as duas continuações boas entraram, apesar da primeira vazia
    assert [v["o_que"] for v in conf["voltas"][:3]] == ["continuar"] * 3


# ------------------------------------------------------------------- o roteiro comprido é condensado, não cortado

def test_o_roteiro_comprido_e_condensado(monkeypatch):
    """15 min pedidos que saíam com 23: agora o Claude reescreve menor em vez de ninguém olhar."""
    pedidos = []

    def falso(sistema, pedido, modelo=""):
        pedidos.append(pedido)
        return _texto(3200)

    monkeypatch.setattr(roteiro_claude, "_claude", falso)
    roteiro, conf = roteiro_claude._conferir_tamanho(_texto(4900), "sis", "ped", 15, {"ppm": 215, "de": "voz"})
    assert conf["dentro"] and len(roteiro.split()) == 3200
    assert "Reescreva o roteiro INTEIRO" in pedidos[0]
    assert conf["voltas"][0]["o_que"] == "condensar"


def test_a_volta_que_piora_nao_entra_no_roteiro(monkeypatch):
    """O Claude condensou demais: fica o roteiro de antes, que erra menos, e não o pior."""
    monkeypatch.setattr(roteiro_claude, "_claude", lambda s, p, modelo="": _texto(400))
    roteiro, conf = roteiro_claude._conferir_tamanho(_texto(4000), "sis", "ped", 15, {"ppm": 215, "de": "voz"})
    assert len(roteiro.split()) == 4000
    assert not conf["dentro"] and conf["palavras"] == 4000


def test_sem_tempo_pedido_a_conferencia_nao_mexe_no_roteiro(monkeypatch):
    monkeypatch.setattr(roteiro_claude, "_claude", lambda s, p, modelo="": _texto(9999))
    roteiro, conf = roteiro_claude._conferir_tamanho(_texto(2000), "sis", "ped", 0, {"ppm": 215, "de": "voz"})
    assert len(roteiro.split()) == 2000 and conf["voltas"] == []


# --------------------------------------------------------- o que a voz aprende depois, com o vídeo já entregue

def test_o_erro_da_previsao_e_medido_contra_o_video_entregue(monkeypatch, tmp_path):
    """O que tem de ir a zero: o tempo que a conferência previu contra o que a fábrica entregou."""
    roteiros, fabrica = _mundo(monkeypatch, tmp_path)
    _roteiro(roteiros, "2026-11-01-a", minutos=30, palavras=6450, ppm_usado=215, projeto="p1",
             conferencia={"previsto_min": 30.0, "ppm": 215})
    _projeto(fabrica, "p1", 1878.0)              # 31,3 min: a conferência errou 1,3 min
    (m,) = tempo.medicoes(1)
    assert (m["previsto_min"], m["erro_previsao_min"]) == (30.0, 1.3)
    assert tempo.ritmo(1, "canal-x", "inglês")["acerto"]["erro_previsao_medio"] == 1.3


def test_o_ritmo_de_uma_voz_lenta_nao_dimensiona_a_voz_rapida(monkeypatch, tmp_path):
    """A causa do vídeo de 17 min: sem medida da voz, a língua servia de reserva mesmo juntando 134 e 215 palavras
    por minuto. Dimensionar 30 min pela voz lenta dá 17 minutos de vídeo na voz rápida."""
    roteiros, fabrica = _mundo(monkeypatch, tmp_path)
    _roteiro(roteiros, "2026-11-01-a", minutos=30, palavras=6450, ppm_usado=215, projeto="p1", perfil="voz-rapida")
    _projeto(fabrica, "p1", 1800.0)              # 215 palavras por minuto
    _roteiro(roteiros, "2026-11-01-b", minutos=30, palavras=4020, ppm_usado=134, projeto="p2", perfil="voz-lenta")
    _projeto(fabrica, "p2", 1800.0)              # 134 palavras por minuto, na mesma língua
    r = tempo.ritmo(1, "voz-nova", "inglês", 30)
    assert r["de"] == "padrao" and r["medidos"] == 0
    # e cada voz continua medida por si
    assert tempo.ritmo(1, "voz-rapida", "inglês", 30)["ppm"] == 215
    assert tempo.ritmo(1, "voz-lenta", "inglês", 30)["ppm"] == 134


def test_o_video_curto_nao_puxa_o_ritmo_do_video_longo(monkeypatch, tmp_path):
    """Vídeos de 3 min da mesma voz faziam a mediana pular; agora a base é do tamanho parecido com o que se pede."""
    roteiros, fabrica = _mundo(monkeypatch, tmp_path)
    for i, (minutos, palavras, segundos) in enumerate([(3, 450, 180.0), (3, 450, 180.0),
                                                       (30, 6450, 1800.0), (30, 6450, 1800.0)]):
        _roteiro(roteiros, f"2026-11-01-{i}", minutos=minutos, palavras=palavras, ppm_usado=150,
                 projeto=f"p{i}", perfil="canal-x")
        _projeto(fabrica, f"p{i}", segundos)
    assert tempo.ritmo(1, "canal-x", "inglês", 30)["medidos"] == 2     # só os dois de 30 min
    assert tempo.ritmo(1, "canal-x", "inglês", 3)["medidos"] == 2      # só os dois de 3 min


def test_condensar_que_quase_nao_encurta_para_logo(monkeypatch):
    """2026-11-12: 30 min pedidos, seis reescritas inteiras de 45,9 a 44,2 min. Volta que melhora menos de meio
    minuto encerra o laço: fica a melhor, sem gastar outro roteiro inteiro."""
    respostas = [_texto(9750), _texto(9700), _texto(9650)]
    chamadas = []

    def falso(sistema, pedido, modelo=""):
        chamadas.append(pedido)
        return respostas.pop(0)

    monkeypatch.setattr(roteiro_claude, "_claude", falso)
    roteiro, conf = roteiro_claude._conferir_tamanho(_texto(9800), "sis", "ped", 30, {"ppm": 215, "de": "voz"})
    assert len(chamadas) == 1 and len(roteiro.split()) == 9750


def test_o_radar_chama_o_claude_sem_as_configuracoes_pessoais(monkeypatch, tmp_path):
    """O plugin caveman e o ~/.claude/CLAUDE.md entravam em todo roteiro (2026-11-12)."""
    import json as _json, subprocess as _sp
    visto = {}

    def run(comando, **k):
        visto["comando"] = comando
        return _sp.CompletedProcess(comando, 0, _json.dumps({"result": "ok"}), "")

    monkeypatch.setattr(roteiro_claude, "VAZIA", tmp_path)
    monkeypatch.setattr(roteiro_claude.shutil, "which", lambda _n: "claude")
    monkeypatch.setattr(roteiro_claude.subprocess, "run", run)
    assert roteiro_claude._claude("s", "p") == "ok"
    c = visto["comando"]
    assert c[c.index("--setting-sources") + 1] == "" and "--disable-slash-commands" in c


# ------------------------------------------------- o primeiro pedido já sai no tamanho: partes medidas e base avisada

def test_o_roteiro_longo_e_pedido_em_partes_que_somam_o_tempo():
    partes, cada = roteiro_claude.partes_do_roteiro(6390)
    assert partes == 11 and abs(partes * cada - 6390) < partes
    texto = roteiro_claude.tamanho_no_pedido(6390, 30, "português")
    assert "6390 palavras" in texto and f"[PARTE 1/{partes}]" in texto
    assert "PARTE" not in roteiro_claude.tamanho_no_pedido(300, 2, "português")


def test_a_marca_da_parte_sai_e_a_fala_grudada_nela_fica():
    texto = "[PARTE 1/3]\nPrimeira frase da voz.\n\n[PARTE 2/3] Segunda frase da voz.\n\n[Parte 3/3]: Terceira frase."
    limpo = roteiro_claude._limpar(texto)
    assert "PARTE" not in limpo.upper()
    assert "Segunda frase da voz." in limpo and "Terceira frase." in limpo and "\n\n" in limpo


def test_a_referencia_maior_vem_avisada_e_o_tamanho_repetido_no_fim(monkeypatch, tmp_path):
    from radar import tempo as _tempo
    monkeypatch.setattr(roteiro_claude, "PASTA", tmp_path)
    monkeypatch.setattr(roteiro_claude, "_escrever_descricao", lambda *a, **k: None)
    monkeypatch.setattr(roteiro_claude, "transcricao", lambda _v: ("fala " * 10000, "pt"))
    monkeypatch.setattr(roteiro_claude, "copiar_thumbnail", lambda *a: False)
    monkeypatch.setattr(roteiro_claude, "por_que_estourou", lambda *a, **k: {})
    monkeypatch.setattr(_tempo, "ritmo", lambda *a, **k: {"ppm": 213, "ppm_alvo": 213, "de": "voz"})
    pedidos = []

    def falso(sistema, pedido, modelo=""):
        pedidos.append(pedido)
        return "Frase do roteiro. " * 3195

    monkeypatch.setattr(roteiro_claude, "_claude", falso)
    roteiro_claude.gerar(usuario_id=1, titulo="T", link="https://youtu.be/abcdefghijk", minutos=30, lingua="",
                         projeto_id=None, observacoes="")
    p = pedidos[0]
    assert "10000 palavras" in p and "NÃO siga o tamanho dela" in p
    assert p.rstrip().endswith("A última parte é o fechamento.") and p.count("[PARTE 1/11]") == 2


def test_o_roteiro_vai_no_opus_com_esforco_baixo(monkeypatch, tmp_path):
    import json as _json, subprocess as _sp
    visto = {}
    monkeypatch.setattr(roteiro_claude, "VAZIA", tmp_path)
    monkeypatch.setattr(roteiro_claude.shutil, "which", lambda _n: "claude")
    monkeypatch.setattr(roteiro_claude.subprocess, "run",
                        lambda c, **k: visto.update(c=c) or _sp.CompletedProcess(c, 0, _json.dumps({"result": "ok"}), ""))
    roteiro_claude._claude("s", "p", modelo=roteiro_claude.ROTEIRO)
    c = visto["c"]
    assert c[c.index("--model") + 1] == "opus" and c[c.index("--effort") + 1] == "low"
    roteiro_claude._claude("s", "p", modelo="sonnet")
    assert "--effort" not in visto["c"]
