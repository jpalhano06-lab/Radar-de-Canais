"""Roteiro pelo Claude: o título escolhido, o tempo e o vídeo de referência (a transcrição dele vira a base e a
thumbnail é copiada).

Pedido do usuário em 2026-10-14. Quem escreve é o Claude Code deste computador (`claude -p`), pela assinatura do
claude.ai: sem chave de API, sem custo por uso (gasta o limite da assinatura). A chave ANTHROPIC_API_KEY é tirada do
ambiente antes de chamar, senão o Claude Code cobraria por ela. Os "projetos" são as instruções de estilo do canal,
guardadas aqui (o claude.ai não deixa ler os projetos de lá por fora), e vão junto em todo roteiro."""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import uuid
from datetime import datetime

import httpx

from . import banco
from .config import DADOS, FABRICA as _FABRICA

PASTA = DADOS / "roteiros"
VAZIA = DADOS / "claude"          # o Claude roda numa pasta vazia, para não ler nenhum CLAUDE.md
PALAVRAS_POR_MINUTO = 150
_TAREFAS: dict[str, dict] = {}
_TRAVA = threading.Lock()


def id_do_video(link: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([\w-]{11})", link or "")
    if m:
        return m.group(1)
    return link.strip() if re.fullmatch(r"[\w-]{11}", (link or "").strip()) else None


def transcricao(video_id: str) -> tuple[str, str]:
    """O texto falado do vídeo e a língua. Prefere a legenda feita à mão; senão a automática; em qualquer língua."""
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    try:
        disponiveis = list(api.list(video_id))
    except Exception as erro:
        raise RuntimeError("Não consegui ler a legenda desse vídeo (ele pode não ter legenda, ou o YouTube bloqueou "
                           f"a leitura agora). Detalhe: {str(erro)[:120]}")
    if not disponiveis:
        raise RuntimeError("Esse vídeo não tem legenda, nem automática.")
    preferidas = ["pt", "pt-BR", "en", "es"]
    escolhida = sorted(disponiveis, key=lambda t: (t.is_generated,
                                                   preferidas.index(t.language_code) if t.language_code in preferidas else 9))[0]
    trechos = escolhida.fetch()
    texto = re.sub(r"\s+", " ", " ".join(s.text for s in trechos)).strip()
    return texto, escolhida.language_code


def tem_legenda(video_id: str) -> bool:
    """Se dá para ler a legenda desse vídeo. A Nova produção da extensão pergunta isso na confirmação, para a pessoa
    saber antes de criar que o roteiro vai sair só do título (pedido do usuário em 2026-10-28)."""
    from youtube_transcript_api import YouTubeTranscriptApi
    try:
        return bool(list(YouTubeTranscriptApi().list(video_id)))
    except Exception:
        return False


def copiar_thumbnail(video_id: str, destino) -> bool:
    for nome in ("maxresdefault", "sddefault", "hqdefault"):
        r = httpx.get(f"https://i.ytimg.com/vi/{video_id}/{nome}.jpg", timeout=20)
        if r.status_code == 200 and len(r.content) > 5000:
            destino.write_bytes(r.content)
            return True
    return False


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")[:50] or "roteiro"


INSTRUCOES = """Você é roteirista de canais sem rosto do YouTube. Escreve o texto que uma voz vai narrar, do começo ao fim.

Regras:
- Responda SÓ com o roteiro. Nada antes nem depois: sem "Aqui está", sem comentários, sem markdown, sem asteriscos.
- É um script LIMPO para narração: só as frases que a voz vai falar, em parágrafos. Nenhum título de parte, nenhum
  subtítulo, nenhuma numeração de seção, nenhum colchete, nenhuma indicação de cena, câmera, música ou efeito.
- A passagem de um assunto para o outro é feita pela própria fala (uma frase de ligação), nunca por um título.
- Os primeiros 15 segundos são um gancho forte que segura quem chegou pelo título.
- A transcrição do vídeo de referência é a BASE: use a estrutura, os fatos e o que fez o vídeo funcionar. Não copie
  frases: reescreva com palavras próprias, melhore o ritmo e acrescente o que faltar para cumprir o título.
- Só fatos de que você tem certeza. Nada inventado sobre pessoas reais. Número, data e nome só se estiverem certos.
- Termine com um fechamento curto.
- Respeite o tamanho pedido (palavras), porque ele vira o tempo do vídeo."""


def _claude(sistema: str, pedido: str, modelo: str = "") -> str:
    executavel = shutil.which("claude")
    if not executavel:
        raise RuntimeError("O Claude Code não está instalado neste computador (comando claude).")
    VAZIA.mkdir(parents=True, exist_ok=True)
    ambiente = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    comando = [executavel, "-p", "--output-format", "json", "--system-prompt", sistema, "--tools", "",
               "--strict-mcp-config", "--no-session-persistence"]
    if modelo:
        comando += ["--model", modelo]
    r = subprocess.run(comando, input=pedido, capture_output=True, text=True, encoding="utf-8", cwd=VAZIA,
                       env=ambiente, timeout=900)
    try:
        dados = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError("O Claude Code não respondeu. Ele está logado? Rode `claude` no terminal e digite /login. "
                           + (r.stderr or "")[:200])
    if dados.get("is_error"):
        raise RuntimeError("O Claude Code recusou: " + str(dados.get("result", ""))[:300])
    return str(dados.get("result", "")).strip()


# linha que é título de parte e não fala: "[TITULO] A fuga", "## Parte 2", "Introdução", "1. O começo"
_TITULO = re.compile(r"^\s*(\[[^\]]*\].*|#+.*|(parte|cap[ií]tulo|se[cç][aã]o|bloco)\s*\d+.*|"
                     r"(introdu[cç][aã]o|conclus[aã]o|fechamento|gancho|abertura|encerramento)\s*:?)\s*$", re.I)


def _limpar(texto: str) -> str:
    """Deixa só o que a voz fala. Pedido do usuário em 2026-10-14: o roteiro vinha com "[TITULO] ..." no meio, e o
    script tem que ser limpo para narração."""
    texto = re.sub(r"^\s*(aqui está|segue)[^\n]*\n", "", texto, flags=re.I)
    texto = re.sub(r"\*\*|__|`", "", texto)
    linhas = []
    for linha in texto.splitlines():
        limpa = linha.strip()
        if _TITULO.match(limpa):
            continue
        # linha curta sem pontuação no fim, sozinha entre linhas vazias, é título ("A fuga", "Por que elas trapaceiam")
        if limpa and len(limpa.split()) <= 7 and not re.search(r"[.!?…:;,\"”)]$", limpa):
            continue
        linhas.append(limpa)
    texto = "\n".join(linhas)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def gerar(usuario_id: int, titulo: str, link: str, minutos: int, lingua: str, projeto_id: int | None,
          observacoes: str, perfil: str = "", canal: dict | None = None, projeto_descricao_id: int | None = None,
          aviso=lambda _t: None) -> dict:
    video_id = id_do_video(link)
    if link and not video_id:
        raise RuntimeError("Não reconheci o link do vídeo de referência.")
    pasta = PASTA / f"{datetime.now(banco.BRASILIA).strftime('%Y-%m-%d-%H%M')}-{_slug(titulo)}"
    pasta.mkdir(parents=True, exist_ok=True)
    base, lingua_base, thumb, base_erro = "", "", False, ""
    if video_id:
        aviso("Lendo a transcrição do vídeo de referência…")
        # sem legenda não derruba o pedido (pedido do usuário em 2026-10-28): o vídeo pode estar com as legendas
        # desligadas pelo dono, e antes disso o pedido inteiro parava com erro. Agora o roteiro sai do título, das
        # observações e do estilo do canal, e o motivo fica no roteiro.json para a Revisão poder dizer
        try:
            base, lingua_base = transcricao(video_id)
            (pasta / "transcricao.txt").write_text(base, encoding="utf-8")
        except Exception as erro:  # noqa: BLE001
            base, lingua_base, base_erro = "", "", str(erro)
            aviso("Esse vídeo não deu a legenda. Escrevendo o roteiro a partir do título…")
        aviso("Copiando a thumbnail…")
        thumb = copiar_thumbnail(video_id, pasta / "thumbnail.jpg")
    projeto = banco.um("SELECT * FROM projetos_roteiro WHERE id=? AND usuario_id=?", projeto_id, usuario_id) if projeto_id else None
    # o ritmo real da voz, medido nos vídeos que a fábrica já entregou (tempo.py)
    from . import tempo
    ritmo = tempo.ritmo(usuario_id, perfil, lingua)
    # o ppm_alvo já desconta a mania do Claude de escrever mais do que se pede (tempo.py): é ele que dimensiona o
    # pedido, para o vídeo cair dentro de 1 min 30 s do tempo escolhido
    palavras = minutos * (ritmo.get("ppm_alvo") or ritmo["ppm"])
    sistema = INSTRUCOES + (f"\n\nInstruções do projeto \"{projeto['nome']}\" (estilo do canal, valem por cima das "
                            f"regras acima quando conflitarem):\n{projeto['instrucoes']}" if projeto and projeto["instrucoes"] else "")
    pedido = (f"Título do vídeo: {titulo}\nLíngua do roteiro: {lingua}\nTamanho: cerca de {palavras} palavras "
              f"({minutos} minutos narrados)\n")
    if observacoes:
        pedido += f"Observações de quem pediu: {observacoes}\n"
    if base:
        # a transcrição muito longa é cortada: o começo e a estrutura importam mais
        pedido += f"\nTranscrição do vídeo de referência (língua: {lingua_base}):\n{base[:60000]}\n"
    elif base_erro:
        pedido += ("\nO vídeo de referência existe, mas não deu para ler a legenda dele: escreva a partir do título, "
                   "das observações e do estilo do canal, sem nenhuma base de transcrição.\n")
    else:
        pedido += "\nSem vídeo de referência: escreva a partir do título.\n"
    aviso(f"O Claude está escrevendo (cerca de {palavras} palavras)…")
    inicio = time.time()
    roteiro = _limpar(_claude(sistema, pedido))
    # roteiro longo (até 1 hora, uns 9 mil palavras): o Claude às vezes para antes do tamanho. Ele continua de onde
    # parou, até 4 vezes, sem repetir o que já escreveu
    # antes ele parava quando faltava menos de 15% (num vídeo de 15 min, 2 min a menos): agora o que sobra tem de
    # caber na margem de 1 min 30 s do usuário, então a conta é em minutos de narração, não em porcentagem
    falta_demais = max(200, (ritmo.get("ppm_alvo") or ritmo["ppm"]) * (tempo.MARGEM_MIN - 0.5))
    for _ in range(4):
        faltam = palavras - len(roteiro.split())
        if faltam < falta_demais:
            break
        aviso(f"O Claude está continuando o roteiro ({len(roteiro.split())} de {palavras} palavras)…")
        resto = _limpar(_claude(sistema, pedido + "\n\nVocê já escreveu este começo (NÃO repita nada dele):\n" + roteiro[-12000:]
                                + f"\n\nContinue o roteiro exatamente de onde ele parou, com mais cerca de {faltam} palavras, "
                                  "até o fechamento. Responda só com a continuação."))
        if len(resto.split()) < 50:
            break
        roteiro = roteiro + "\n\n" + resto
    (pasta / "roteiro.txt").write_text(roteiro, encoding="utf-8")
    meta = {"titulo": titulo, "link": link, "video_id": video_id, "minutos": minutos, "lingua": lingua,
            "projeto": projeto["nome"] if projeto else "", "palavras": len(roteiro.split()),
            "palavras_base": len(base.split()), "base_erro": base_erro[:300], "thumbnail": thumb,
            "segundos": round(time.time() - inicio), "criado": banco.agora(), "usuario_id": usuario_id, "ritmo": ritmo, "canal": canal or {}}
    (pasta / "roteiro.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    _escrever_descricao(usuario_id, pasta, projeto_descricao_id, aviso)
    return _publico(pasta)


def _escrever_descricao(usuario_id: int, pasta, projeto_descricao_id, aviso=lambda _t: None) -> None:
    """A descrição do vídeo, escrita logo depois do roteiro (pedido do usuário em 2026-10-28: ela fica pronta
    enquanto o vídeo está sendo feito, em vez de só existir no fim, quando a fábrica monta o publicacao.json).

    Falhar aqui não derruba o roteiro: o roteiro é o que a pessoa pediu, e a descrição se refaz com um botão.
    O que deu errado fica no roteiro.json, para a tela de Revisão poder dizer."""
    from . import descricao as _descricao
    aviso("Roteiro pronto. O Claude está escrevendo a descrição e as tags…")
    meta = json.loads((pasta / "roteiro.json").read_text(encoding="utf-8"))
    try:
        _descricao.gerar(usuario_id, pasta, projeto_descricao_id)
        meta["descricao_erro"] = ""
    except Exception as erro:
        meta["descricao_erro"] = str(erro)[:300]
    (pasta / "roteiro.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def manual(usuario_id: int, titulo: str, texto: str, link: str = "", minutos: int = 0, lingua: str = "",
           canal: dict | None = None) -> dict:
    """O roteiro que a pessoa escreveu (pedido do usuário em 2026-10-18): fica igual a um do Claude, para revisar e
    mandar para a fábrica. Com link, a thumbnail da referência é copiada também."""
    texto = re.sub(r"\n{3,}", "\n\n", texto.replace("\r\n", "\n")).strip()
    if len(texto.split()) < 30:
        raise RuntimeError("Cole o roteiro inteiro (tem menos de 30 palavras).")
    video_id = id_do_video(link) if link else None
    if link and not video_id:
        raise RuntimeError("Não reconheci o link do vídeo de referência.")
    pasta = PASTA / f"{datetime.now(banco.BRASILIA).strftime('%Y-%m-%d-%H%M')}-{_slug(titulo)}"
    pasta.mkdir(parents=True, exist_ok=True)
    thumb = copiar_thumbnail(video_id, pasta / "thumbnail.jpg") if video_id else False
    (pasta / "roteiro.txt").write_text(texto, encoding="utf-8")
    meta = {"titulo": titulo, "link": link, "video_id": video_id, "minutos": minutos, "lingua": lingua, "projeto": "",
            "palavras": len(texto.split()), "palavras_base": 0, "thumbnail": thumb, "segundos": 0, "manual": True,
            "criado": banco.agora(), "usuario_id": usuario_id, "canal": canal or {}}
    (pasta / "roteiro.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return _publico(pasta)


def _nome_do_canal(meta: dict) -> str:
    """Para qual canal é o vídeo (pedido do usuário em 2026-10-18: identificar cada vídeo feito). Os roteiros novos
    guardam o canal; os antigos saem pela voz da fábrica (o perfil tem o nome do canal) ou pelo agente de roteiro."""
    if (meta.get("canal") or {}).get("titulo"):
        return meta["canal"]["titulo"]
    perfil = (meta.get("fabrica") or {}).get("perfil", "")
    if perfil:
        from . import producao
        nome = producao._perfil(perfil).get("canal", "")
        if nome and perfil != "documentario":
            return nome
    # o canal que usa o mesmo agente de roteiro
    agente = banco.um("SELECT id FROM projetos_roteiro WHERE nome=? AND usuario_id=?", meta.get("projeto") or "", meta.get("usuario_id"))
    if agente:
        for linha in banco.todos("SELECT c.dados, k.titulo FROM canais_config c JOIN canais k ON k.id=c.canal_id WHERE c.usuario_id=?",
                                 meta.get("usuario_id")):
            if str(json.loads(linha["dados"]).get("projeto_roteiro_id") or "") == str(agente["id"]):
                return linha["titulo"]
    return (meta.get("projeto") or "").title()


def _publico(pasta) -> dict:
    meta = json.loads((pasta / "roteiro.json").read_text(encoding="utf-8"))
    meta["canal_nome"] = _nome_do_canal(meta)
    arquivo = pasta / "roteiro.txt"
    from . import descricao as _descricao
    return meta | {"nome": pasta.name, "roteiro": arquivo.read_text(encoding="utf-8"), "arquivo": str(arquivo),
                   "descricao": _descricao.ler(pasta),
                   "thumbnail_url": f"/api/roteiros/{pasta.name}/thumbnail.jpg" if (pasta / "thumbnail.jpg").exists() else "",
                   "comando": f'uv run fabrica novo {pasta.name} --roteiro "{arquivo}" --perfil perfis/documentario.yaml'}


def lista(usuario_id: int) -> list[dict]:
    if not PASTA.exists():
        return []
    saida = []
    for meta in sorted(PASTA.glob("*/roteiro.json"), reverse=True)[:60]:
        try:
            if json.loads(meta.read_text(encoding="utf-8")).get("usuario_id") == usuario_id:
                saida.append(_publico(meta.parent))
        except (ValueError, OSError):
            continue
    return saida


# ---------------------------------------------------------------- tarefa em segundo plano (leva 1 a 3 minutos)

def comecar(usuario_id: int, enviar_perfil: str = "", **pedido) -> str:
    """Escreve o roteiro em segundo plano. Com enviar_perfil, assim que fica pronto ele já vai para a fábrica, sem
    esperar a revisão (pedido do usuário em 2026-10-18: escolher entre revisar antes ou mandar direto)."""
    tid = uuid.uuid4().hex[:12]
    with _TRAVA:
        _TAREFAS[tid] = {"usuario_id": usuario_id, "estado": "rodando", "passo": "Começando…", "resultado": None, "erro": "",
                         "titulo": pedido.get("titulo", ""), "link": pedido.get("link", ""), "direto": bool(enviar_perfil),
                         "criado": banco.agora(), "fabrica": None, "erro_envio": "",
                         "canal_nome": (pedido.get("canal") or {}).get("titulo", "")}

    def rodar():
        def aviso(texto):
            _TAREFAS[tid]["passo"] = texto
        try:
            resultado = gerar(usuario_id, aviso=aviso, **pedido)
        except Exception as erro:
            _TAREFAS[tid].update(estado="erro", erro=str(erro))
            return
        if enviar_perfil:
            aviso("Roteiro pronto. Enviando para a fábrica…")
            try:
                _TAREFAS[tid]["fabrica"] = enviar(usuario_id, resultado["nome"], enviar_perfil)
                resultado = _publico(PASTA / resultado["nome"])
            except Exception as erro:
                _TAREFAS[tid]["erro_envio"] = str(erro)
        _TAREFAS[tid].update(resultado=resultado, estado="pronto")
    threading.Thread(target=rodar, daemon=True).start()
    return tid


def tarefa(usuario_id: int, tid: str) -> dict | None:
    t = _TAREFAS.get(tid)
    return t if t and t["usuario_id"] == usuario_id else None


def tarefas(usuario_id: int) -> list[dict]:
    """Os roteiros pedidos desde que o servidor ligou, os mais novos primeiro (sem o texto, que é grande)."""
    saida = []
    for tid, t in list(_TAREFAS.items()):
        if t["usuario_id"] != usuario_id:
            continue
        r = t["resultado"] or {}
        saida.append({"tarefa": tid, "titulo": t["titulo"], "link": t["link"], "estado": t["estado"], "passo": t["passo"],
                      "erro": t["erro"], "direto": t["direto"], "criado": t["criado"], "fabrica": t["fabrica"],
                      "erro_envio": t["erro_envio"], "canal_nome": t.get("canal_nome", ""), "nome": r.get("nome", ""), "thumbnail_url": r.get("thumbnail_url", "")})
    return sorted(saida, key=lambda x: x["criado"], reverse=True)


# ---------------------------------------------------------------- enviar para a fábrica

FABRICA = _FABRICA      # a pasta de cima (o Radar dentro da fábrica) ou RADAR_FABRICA no .env do Radar


def fabrica_conectada() -> bool:
    return (FABRICA / "fabrica").is_dir() and (FABRICA / "perfis").is_dir() and bool(shutil.which("uv"))


def perfis_da_fabrica() -> list[str]:
    if not fabrica_conectada():
        return []
    return sorted(p.stem for p in (FABRICA / "perfis").glob("*.yaml") if not p.stem.startswith(("base-", "teste-")))


def _do_usuario(usuario_id: int, nome: str):
    pasta = PASTA / nome
    if not re.fullmatch(r"[\w.-]+", nome) or not (pasta / "roteiro.json").exists():
        raise RuntimeError("Roteiro não encontrado.")
    meta = json.loads((pasta / "roteiro.json").read_text(encoding="utf-8"))
    if meta.get("usuario_id") != usuario_id:
        raise RuntimeError("Roteiro não encontrado.")
    return pasta, meta


def salvar_texto(usuario_id: int, nome: str, texto: str, titulo: str = "") -> dict:
    """A pessoa pode corrigir o roteiro antes de mandar para a fábrica."""
    pasta, meta = _do_usuario(usuario_id, nome)
    (pasta / "roteiro.txt").write_text(texto.strip(), encoding="utf-8")
    meta["palavras"] = len(texto.split())
    if titulo.strip():
        meta["titulo"] = titulo.strip()[:150]
    (pasta / "roteiro.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return _publico(pasta)


def enviar(usuario_id: int, nome: str, perfil: str) -> dict:
    """Cria o projeto na fábrica com o roteiro e o título (`fabrica novo`, grátis: narrar e gerar imagens continuam
    pedindo confirmação lá). O título vai em titulo_entrega, que a fábrica usa no nome do vídeo entregue."""
    if not fabrica_conectada():
        raise RuntimeError("A fábrica não está nesta pasta. O Radar precisa estar dentro da pasta da fábrica.")
    if perfil not in perfis_da_fabrica():
        raise RuntimeError("Escolha um perfil da fábrica.")
    pasta, meta = _do_usuario(usuario_id, nome)
    projeto = re.sub(r"-+", "-", _slug(meta["titulo"]).replace(".", "-"))[:40].strip("-") or "roteiro"
    final, n = projeto, 2
    while (FABRICA / "projetos" / final).exists():
        final, n = f"{projeto}-{n}", n + 1
    r = subprocess.run([shutil.which("uv"), "run", "fabrica", "novo", final, "--roteiro", str(pasta / "roteiro.txt"),
                        "--perfil", f"perfis/{perfil}.yaml", "--sim"],
                       cwd=FABRICA, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    destino = FABRICA / "projetos" / final
    if not (destino / "projeto.json").exists():
        raise RuntimeError("A fábrica não criou o projeto: " + (r.stderr or r.stdout or "")[-400:])
    dados = json.loads((destino / "projeto.json").read_text(encoding="utf-8"))
    dados["titulo_entrega"] = meta["titulo"]
    (destino / "projeto.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    if (pasta / "thumbnail.jpg").exists():
        shutil.copy2(pasta / "thumbnail.jpg", destino / "thumbnail_referencia.jpg")
    # a descrição escrita junto com o roteiro vai junto: a extensão já acha este vídeo no Studio com o vídeo
    # ainda sendo feito, em vez de esperar o publicacao.json da fábrica
    from . import descricao as _descricao
    levou = _descricao.levar(pasta, destino, meta["titulo"], perfil)
    meta["fabrica"] = {"projeto": final, "perfil": perfil, "enviado": banco.agora(), "descricao": levou,
                       "palavras": len((pasta / "roteiro.txt").read_text(encoding="utf-8").split())}
    (pasta / "roteiro.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    estimativa = "\n".join(l for l in (r.stdout or "").splitlines() if "US$" in l or "min" in l)[-600:]
    return {"projeto": final, "pasta": str(destino), "estimativa": estimativa,
            "proximo": f"uv run fabrica tudo {final}"}
