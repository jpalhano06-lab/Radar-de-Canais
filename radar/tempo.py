"""O ajuste do tempo do vídeo: o Radar compara o tempo pedido com o tempo que a fábrica entregou e corrige quantas
palavras pedir ao Claude na próxima vez.

Pedido do usuário em 2026-10-18: "pediu 15 min e o vídeo saiu com 12, então ele ajusta para aumentar na próxima".
Cada voz fala num ritmo, então a medida é por perfil da fábrica (a voz do canal): palavras enviadas ÷ minutos do
vídeo entregue. Vale a mediana dos últimos vídeos daquela voz; sem nenhum, a mesma língua; sem nada, 150 por minuto.

Pedido do usuário em 2026-10-22: "sempre que ele gere um roteiro ele veja o resultado que deu o vídeo, para saber se
está acertando ou errando; a margem de erro tem que ser no máximo de um minuto e meio para cima ou para baixo".
Por isso:

- **A medida vem do disco**, do `alinhamento.json` da pasta do projeto (mais a abertura do `render/linha.json`, que é
  tempo de vídeo sem narração). Antes vinha só da API da fábrica: com a fábrica desligada o Radar não media nada,
  caía nas 150 palavras por minuto do padrão e errava feio justo nas vozes lentas (as de inglês falam umas 135).
- **Cada roteiro guarda o que deu** (`medido` no `roteiro.json`): o tempo entregue e o erro em minutos. Assim o
  histórico não se perde quando a pasta do projeto sai do computador.
- **O acerto é contado**: quantos dos últimos vídeos daquela voz ficaram dentro da margem, e o erro médio.
- **A conta fecha pelas palavras PEDIDAS, não pelas escritas.** O Claude escreve mais do que se pede (nos vídeos
  medidos, de 0 a 27% a mais). Medindo "palavras escritas ÷ minutos" o Radar aprendia só a voz e repetia o erro do
  excesso todo vídeo. Agora o número que manda no próximo pedido é `ppm_alvo` = palavras **pedidas** ÷ minutos
  entregues: ele engloba a voz e a mania do Claude de esticar, então o próximo roteiro cai dentro da margem e vai
  melhorando a cada vídeo. O `ppm` continua existindo, para mostrar na tela o ritmo real da voz.

Pedido do usuário em 2026-11-01: "o Radar tá entregando vídeos com a duração errada, tem que conferir e colocar algo
que sempre confira o resultado e regule pra acertar cada vez mais; o vídeo de 30 min saiu com 17, o máximo de erro é
1 minuto". Nos 32 vídeos medidos até ali, 19 estavam fora de 1 minuto, com erro médio de 2,2 min e o pior com 8,2.
O que faltava:

- **A margem é de 1 minuto** (era 1 min 30 s).
- **A conferência**, `conferir()`: a conta que diz quantos minutos ESTE roteiro vai dar, no ritmo real da voz. O
  `roteiro_claude` roda ela antes de o roteiro sair daqui e corrige o roteiro até cair dentro da margem — antes o
  tamanho era só uma aposta feita antes de escrever, e ninguém olhava o roteiro pronto.
- **O erro da previsão é medido também** (`erro_previsao_min`): o tempo que a conferência previu contra o vídeo que a
  fábrica entregou. É esse número que tem de ir a zero, porque o erro de tamanho do roteiro a conferência já corrige.
- **A base aprende por tamanho parecido** (`_parecidos`): um vídeo de 3 min e um de 30 min da mesma voz não medem a
  mesma coisa, e misturar os dois fazia a mediana pular de 120 para 182 palavras por minuto na mesma voz.
- **A língua só serve de reserva entre vozes que falam parecido.** A mesma língua tem voz de 120 e voz de 219
  palavras por minuto: dimensionar 30 min pela voz lenta dá 17 minutos de vídeo na voz rápida. Vozes que discordam
  mais de 20% não servem de reserva uma para a outra — fica o padrão, e a tela avisa que a voz ainda não tem medida.
"""
import json
import statistics
import time

from . import fabrica_api, roteiro_claude

PADRAO = roteiro_claude.PALAVRAS_POR_MINUTO
ULTIMOS = 7
MARGEM_MIN = 1.0        # o erro que o usuário aceita: um minuto para cima ou para baixo
_CACHE: dict = {"quando": 0.0, "duracoes": {}}


def _do_disco(nome: str) -> float | None:
    """Os segundos do vídeo entregue: a narração alinhada mais a abertura que o render põe na frente."""
    pasta = roteiro_claude.FABRICA / "projetos" / nome
    try:
        segundos = float(json.loads((pasta / "alinhamento.json").read_text(encoding="utf-8")).get("duracao") or 0)
    except (OSError, ValueError, TypeError):
        return None
    if segundos <= 30:
        return None
    try:
        segundos += float(json.loads((pasta / "render" / "linha.json").read_text(encoding="utf-8")).get("atraso") or 0)
    except (OSError, ValueError, TypeError):
        pass
    return segundos


def _da_api() -> dict[str, float]:
    """O que a fábrica ligada sabe (reserva para os projetos que não estão mais neste computador), por um minuto."""
    if time.time() - _CACHE["quando"] > 60:
        try:
            projetos = fabrica_api._pedir("GET", "/api/projetos")["projetos"]
            _CACHE["duracoes"] = {p["nome"]: float(p["duracao"]) for p in projetos
                                  if p.get("tem_narracao") and (p.get("duracao") or 0) > 30}
        except Exception:
            pass                    # fábrica desligada: fica com o que já sabia
        _CACHE["quando"] = time.time()
    return _CACHE["duracoes"]


def _na_lingua_do_video(arquivo, meta: dict) -> bool:
    """Vídeo que narrou texto no alfabeto errado não mede a voz: os dois vídeos japoneses do cobre (2026-11-03)
    narraram perguntas em português e deram ao canal um ritmo de 116 palavras por minuto que não é o dele."""
    codigo = roteiro_claude.codigo_da_lingua(meta.get("lingua") or "")
    if codigo not in roteiro_claude._ALFABETOS:
        return True
    try:
        return roteiro_claude._escrito_em((arquivo.parent / "roteiro.txt").read_text(encoding="utf-8"), codigo)
    except OSError:
        return True


def _guardar_medida(meta_arquivo, meta: dict, medida: dict) -> None:
    """Grava no roteiro.json o que o vídeo deu, para o histórico não depender da pasta do projeto."""
    if (meta.get("medido") or {}) == medida:
        return
    try:
        meta["medido"] = medida
        meta_arquivo.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def conferir(palavras: int, minutos: float, ppm: int) -> dict:
    """O tempo que ESTE roteiro vai dar, no ritmo real da voz, e o quanto ele erra do tempo pedido.

    É a conta que o Radar faz antes de o roteiro sair daqui (`roteiro_claude`), e a mesma que ele guarda para comparar
    depois com o vídeo entregue. `faltam` é quantas palavras ainda cabem (negativo: quantas sobram)."""
    ppm = ppm or PADRAO
    previsto = round(palavras / ppm, 1)
    alvo = round(minutos * ppm)
    erro = round(previsto - minutos, 1)
    return {"ppm": ppm, "palavras": palavras, "alvo_palavras": alvo, "faltam": alvo - palavras,
            "pedido_min": minutos, "previsto_min": previsto, "erro_min": erro,
            "dentro": bool(minutos) and abs(erro) <= MARGEM_MIN, "margem": MARGEM_MIN}


def _parecidos(base: list[dict], minutos: float) -> list[dict]:
    """Só os vídeos de tamanho parecido, quando há pelo menos dois.

    Um vídeo de 3 min e um de 30 min da mesma voz não medem a mesma coisa: no curto, a abertura e as pausas pesam
    muito mais no ritmo, e misturar os dois fazia a mediana pular (a mesma voz já apareceu com 120, 136 e 182
    palavras por minuto de um vídeo para o outro)."""
    if not minutos:
        return base
    perto = [m for m in base if m["pedido_min"] and 0.5 <= m["pedido_min"] / minutos <= 2]
    return perto if len(perto) >= 2 else base


def medicoes(usuario_id: int) -> list[dict]:
    """Os vídeos do Radar que já ficaram prontos: o pedido, o entregue, o erro e o ritmo real da voz.

    Os mais novos primeiro. Um roteiro que ainda não virou vídeo não entra."""
    da_api = _da_api()
    saida = []
    for arquivo in sorted(roteiro_claude.PASTA.glob("*/roteiro.json"), reverse=True):
        try:
            m = json.loads(arquivo.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if m.get("usuario_id") != usuario_id or not _na_lingua_do_video(arquivo, m):
            continue
        f = m.get("fabrica") or {}
        projeto = f.get("projeto", "")
        guardado = m.get("medido") or {}
        segundos = (_do_disco(projeto) if projeto else None) or da_api.get(projeto) or guardado.get("segundos")
        palavras = f.get("palavras") or m.get("palavras") or 0
        pedido = m.get("minutos") or 0
        if not segundos or palavras < 100:
            continue
        entregue = round(segundos / 60, 1)
        # o que foi pedido ao Claude naquele dia (minutos x o ppm daquele momento); sem isso, o que ele escreveu
        pedidas = round(pedido * ((m.get("ritmo") or {}).get("ppm") or 0)) or palavras
        conferencia = m.get("conferencia") or {}
        previsto = conferencia.get("previsto_min")
        medida = {"segundos": round(segundos, 1), "entregue_min": entregue,
                  "erro_min": round(entregue - pedido, 1) if pedido else None,
                  # o quanto a conferência de antes do envio errou do vídeo que saiu: é isso que diz se o ritmo
                  # aprendido está bom, separado do erro de tamanho do roteiro (que a conferência já corrige)
                  "previsto_min": previsto,
                  "erro_previsao_min": round(entregue - previsto, 1) if previsto else None}
        _guardar_medida(arquivo, m, medida)
        saida.append({"titulo": m.get("titulo", ""), "perfil": f.get("perfil", ""), "lingua": m.get("lingua", ""),
                      "pedido_min": pedido, "entregue_min": entregue, "palavras": palavras,
                      "palavras_pedidas": pedidas, "erro_min": medida["erro_min"],
                      "previsto_min": previsto, "erro_previsao_min": medida["erro_previsao_min"],
                      "dentro": medida["erro_min"] is not None and abs(medida["erro_min"]) <= MARGEM_MIN,
                      "ppm": round(palavras / (segundos / 60)),
                      "ppm_alvo": round(pedidas / (segundos / 60))})
    return saida


def _acerto(base: list[dict]) -> dict:
    """Quantos dos últimos vídeos desta voz ficaram dentro da margem, e o quanto o Radar erra em média.

    `erro_previsao_medio` é o erro da conferência (o tempo previsto contra o entregue): é esse que tem de ir a zero,
    porque o erro de tamanho do roteiro a conferência já corrige antes de enviar."""
    com_pedido = [m for m in base if m["erro_min"] is not None]
    if not com_pedido:
        return {"total": 0, "dentro": 0, "erro_medio": None, "erro_previsao_medio": None, "margem": MARGEM_MIN}
    previstos = [m["erro_previsao_min"] for m in com_pedido if m.get("erro_previsao_min") is not None]
    return {"total": len(com_pedido), "dentro": sum(1 for m in com_pedido if m["dentro"]),
            "erro_medio": round(statistics.fmean(m["erro_min"] for m in com_pedido), 1),
            "erro_previsao_medio": round(statistics.fmean(previstos), 1) if previstos else None,
            "conferidos": len(previstos),
            "pior": max(com_pedido, key=lambda m: abs(m["erro_min"])), "margem": MARGEM_MIN}


def ritmo(usuario_id: int, perfil: str = "", lingua: str = "", minutos: float = 0) -> dict:
    """Quantas palavras por minuto pedir para esta voz, de onde veio o número e se ele está acertando.

    A base são os últimos vídeos DESTA voz, de tamanho parecido com o que está sendo pedido. Sem nenhum vídeo da voz,
    a língua serve de reserva — mas só entre vozes que falam parecido: a mesma língua já tem voz de 120 e voz de 219
    palavras por minuto, e pegar a média das duas é como não medir nada (um pedido de 30 min dimensionado pela voz
    lenta vira 17 minutos de vídeo na voz rápida). Quando as vozes da língua discordam demais, o Radar prefere dizer
    que está no padrão, e a conferência do roteiro avisa que ainda não há medida desta voz."""
    todas = medicoes(usuario_id)
    da_voz = _parecidos([m for m in todas if perfil and m["perfil"] == perfil], minutos)[:ULTIMOS]
    base = da_voz
    de = "voz"
    if not base:
        da_lingua = _parecidos([m for m in todas if lingua and m["lingua"] == lingua], minutos)[:ULTIMOS]
        ppms = [m["ppm"] for m in da_lingua]
        # vozes que falam parecido (até 20% de diferença entre a mais lenta e a mais rápida) podem servir de reserva
        if ppms and max(ppms) <= min(ppms) * 1.2:
            base, de = da_lingua, "lingua"
    if not base:
        return {"ppm": PADRAO, "ppm_alvo": PADRAO, "medidos": 0, "padrao": PADRAO, "exemplo": None, "de": "padrao",
                "acerto": _acerto([]), "ultimos": []}
    limites = lambda x: int(min(260, max(90, x)))
    ppm = limites(statistics.median(m["ppm"] for m in base))
    return {"ppm": ppm, "ppm_alvo": limites(statistics.median(m["ppm_alvo"] for m in base)),
            "medidos": len(base), "padrao": PADRAO, "exemplo": base[0],
            "de": de, "acerto": _acerto(base),
            "ultimos": [{k: m[k] for k in ("titulo", "pedido_min", "entregue_min", "erro_min", "dentro")} for m in base]}
