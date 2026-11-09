"""O que precisa de você, sem você precisar abrir nada (pedido do usuário em 2026-11-06).

Antes o pedido 76 parou sem ninguém saber, e a assinatura do ChatGPT e o limite da chave do OpenRouter acabaram no meio de
um vídeo sem aviso. Uma linha de fundo olha tudo de 10 em 10 minutos. O site mostra no topo, a extensão avisa pelo Chrome,
e o que for grave chega no celular: pelo ntfy com RADAR_NTFY_TOPICO no .env, ou pelo Telegram com RADAR_TELEGRAM_TOKEN e
RADAR_TELEGRAM_CHAT. O tópico do ntfy não tem senha: quem souber o nome lê, por isso ele é sorteado e nunca vai para o Git.

Cada aviso é {chave, nivel, titulo, texto, link}. A chave é o que impede repetir: é a mesma enquanto o problema for o mesmo.
Nivel: "erro" é parado agora, "atencao" é vai parar. Cada verificação falha sozinha: uma que quebre não cala as outras.
"""
import json
import re
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

from . import backup, banco, config, fabrica_api, integracoes, studio

VOLTA = 600
FABRICA_URL = "http://127.0.0.1:8080/api/saude"
LIMITE_DA_CHAVE_MINIMO = 3.0   # US$: cada imagem reserva bem mais do que custa, e abaixo de 0,50 nenhuma passa
SALDO_MINIMO = 5.0             # US$
ASSINATURA_CHEIA = 90          # % usado da janela
DISCO_MINIMO_GB = 40
HORAS_DEMORANDO = 6
QUALIDADE_MINIMA = 50          # % das cenas certas. A média de hoje é uns 54%: abaixo disso o vídeo foi mal de verdade
ERRADAS_MAXIMO = 15            # % das cenas mostrando outra coisa
DIAS_DA_QUALIDADE = 3
MINUTOS_DE_VOZ = 35           # um vídeo de 30 min, com folga: abaixo disso a narração do próximo não termina
TENTATIVAS_TRAVADO = 3         # a fábrica tenta de novo sozinha; a partir da 3ª é problema que não passa sozinho
# o pedido 83 ficou 3 h tentando narrar com "Not enough credit" da GenAIPro, 46 vezes, e ninguém soube (2026-11-07)
SEM_SALDO = re.compile(r"not enough credit|insufficient (credit|balance|funds)|out of credit|sem saldo|saldo insuficiente"
                       r"|cr[eé]ditos? insuficientes?|payment required|\b402\b", re.I)
HORAS_SEM_BACKUP = 8 * 24     # a cópia sai de 7 em 7 dias: um dia de folga antes de avisar

_atuais: list = []
_enviados: dict = {}
_trava = threading.Lock()


def _aviso(chave, nivel, titulo, texto, link="") -> dict:
    return {"chave": chave, "nivel": nivel, "titulo": titulo, "texto": texto, "link": link}


def fila() -> list:
    saida = []
    for r in banco.todos("SELECT id, projeto, erro FROM producoes_fila WHERE estado='erro' ORDER BY id DESC LIMIT 5"):
        saida.append(_aviso(f"fila-erro-{r['id']}", "erro", f"O pedido {r['id']} parou", (r["erro"] or "Abra a fila para ver o motivo.")[:220], "#/acompanhar"))
    agora = datetime.now(timezone.utc)
    for r in banco.todos("SELECT id, criado FROM producoes_fila WHERE estado IN ('escrevendo','enviando','produzindo')"):
        horas = (agora - datetime.fromisoformat(r["criado"])).total_seconds() / 3600
        if horas >= HORAS_DEMORANDO:
            saida.append(_aviso(f"fila-lenta-{r['id']}", "atencao", f"O pedido {r['id']} está demorando", f"Já são {round(horas)} horas.", "#/acompanhar"))
    return saida


def qualidade() -> list:
    """O vídeo entregue nos últimos dias com muita cena errada. Nada para a entrega: quem decide publicar é você."""
    limite = (datetime.now(timezone.utc) - timedelta(days=DIAS_DA_QUALIDADE)).isoformat()
    ruins = []
    for r in banco.todos("SELECT id, projeto FROM producoes_fila WHERE estado='entregue' AND atualizado>=? ORDER BY id DESC LIMIT 20", limite):
        arquivo = config.FABRICA / "projetos" / str(r["projeto"]) / "qualidade.json"
        if not arquivo.exists():
            continue
        q = json.loads(arquivo.read_text(encoding="utf-8")).get("atual") or {}
        cenas, erradas = q.get("cenas") or 0, len(q.get("erradas") or [])
        if cenas and (q.get("boas_pct", 100) < QUALIDADE_MINIMA or 100 * erradas / cenas > ERRADAS_MAXIMO or q.get("vazias")):
            ruins.append((r["id"], q.get("boas_pct")))
    if not ruins:
        return []
    # um aviso só: um por vídeo enchia a tela e empurrava o resto para baixo
    pedidos = ", ".join(f"{i} ({pct}%)" for i, pct in ruins)
    return [_aviso("qualidade-" + "-".join(str(i) for i, _ in ruins), "atencao", "Revise antes de publicar",
                   f"Pedidos com muita cena errada (% de cenas certas): {pedidos}.", "#/acompanhar")]


def fabrica() -> list:
    if not banco.um("SELECT 1 FROM producoes_fila WHERE estado IN ('na_fila','escrevendo','enviando','produzindo') LIMIT 1"):
        return []
    try:
        httpx.get(FABRICA_URL, timeout=8).raise_for_status()
    except httpx.HTTPError:
        return [_aviso("fabrica-fora", "erro", "A fábrica não responde", "Tem pedido na fila e a fábrica da porta 8080 está fora.", "#/acompanhar")]
    return []


def parada(d: dict | None) -> dict | None:
    """Se a criação (o criacao.json da fábrica) está parada, e por quê. None quando ela anda ou terminou.

    tipo "parou": a fábrica parou e espera alguém (ParadaPrecisaDeVoce) ou deu erro. "saldo": um serviço sem saldo,
    tentando de novo. "repetindo": a mesma falha voltando, TENTATIVAS_TRAVADO vezes ou mais. É daqui que saem o aviso
    no celular e o botão Retomar do Acompanhar."""
    if not d or d.get("concluido"):
        return None
    if d.get("precisa_voce") or d.get("erro"):
        motivo = " ".join(str(d.get("erro") or d.get("mensagem") or "a fábrica parou").split())[:220]
        return {"tipo": "parou", "motivo": motivo, "tentativas": 0, "servico": ""}
    logs = [str(l) for l in (d.get("logs") or [])[-30:]] + [str(d.get("mensagem") or "")]
    tentativas = max([int(n) for n in re.findall(r"tentativa (\d+)", " ".join(logs))] or [0])
    sem_saldo = next((l for l in reversed(logs) if SEM_SALDO.search(l)), "")
    if not sem_saldo and tentativas < TENTATIVAS_TRAVADO:
        return None
    motivo = sem_saldo or next((l for l in reversed(logs) if re.search(r"falhou|recusou|erro", l, re.I)), d.get("mensagem") or "")
    servico = next((s for s in ("GenAIPro", "OpenRouter", "Kie", "Gemini", "Groq") if s.lower() in sem_saldo.lower()), "um serviço") if sem_saldo else ""
    return {"tipo": "saldo" if sem_saldo else "repetindo", "motivo": " ".join(motivo.split())[:180],
            "tentativas": tentativas, "servico": servico}


def travados() -> list:
    """O pedido que a fábrica está tentando de novo sem sair do lugar: sem saldo num serviço, ou a mesma falha que volta."""
    saida = []
    for r in banco.todos("SELECT id, projeto FROM producoes_fila WHERE estado='produzindo' AND projeto<>''"):
        try:
            d = json.loads((config.FABRICA / "projetos" / r["projeto"] / "criacao.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        p = parada(d)
        if not p:
            continue
        motivo, tentativas = p["motivo"], p["tentativas"]
        if p["tipo"] == "parou":
            saida.append(_aviso(f"parado-{r['id']}", "erro", f"O pedido {r['id']} parou na fábrica", motivo, "#/acompanhar"))
        elif p["tipo"] == "saldo":
            saida.append(_aviso(f"travado-saldo-{r['id']}", "erro", f"O pedido {r['id']} parou: acabou o saldo da {p['servico']}",
                                f"{motivo}{f' (tentativa {tentativas})' if tentativas else ''}. Recarregue e clique em Retomar no "
                                "Acompanhar (ou espere: ele segue sozinho de onde parou).", "#/acompanhar"))
        else:
            saida.append(_aviso(f"travado-{r['id']}", "erro", f"O pedido {r['id']} está tentando de novo sem sair do lugar",
                                f"{motivo} (tentativa {tentativas}).", "#/acompanhar"))
    return saida


def voz() -> list:
    """O saldo da GenAIPro, que narra os vídeos: avisa antes de um vídeo parar no meio da narração."""
    if not banco.um("SELECT 1 FROM producoes_fila WHERE estado IN ('na_fila','escrevendo','enviando','produzindo') LIMIT 1")             and not banco.um("SELECT 1 FROM producoes_fila WHERE atualizado>=? LIMIT 1",
                             (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()):
        return []
    try:
        d = fabrica_api._pedir("GET", "/api/genaipro/creditos", tempo=20)
    except Exception:  # fábrica desligada: o aviso da fábrica fora já cobre
        return []
    if not d.get("configurada") or d.get("minutos_de_narracao") is None:
        return []
    minutos = d.get("minutos_de_narracao") or 0
    if minutos >= MINUTOS_DE_VOZ:
        return []
    return [_aviso("genaipro-saldo", "erro" if minutos < 10 else "atencao", "Saldo da GenAIPro acabando",
                   f"Restam {d.get('creditos', 0):,.0f} créditos".replace(",", ".") + f", uns {minutos} min de narração. Um vídeo de 30 min precisa de uns 36 mil. "
                   "Recarregue em genaipro.vn.", "#/integracoes")]


def openrouter() -> list:
    chave = config.AMBIENTE.get(integracoes._servico("openrouter")["env"], "")
    if not chave:
        return []
    cabecalho = {"Authorization": f"Bearer {chave}"}
    saida = []
    dados = httpx.get("https://openrouter.ai/api/v1/key", headers=cabecalho, timeout=15).json()["data"]
    resta = dados.get("limit_remaining")
    if resta is not None and resta < LIMITE_DA_CHAVE_MINIMO:
        saida.append(_aviso("openrouter-limite", "erro" if resta < 0.5 else "atencao", "Limite da chave do OpenRouter acabando",
                            f"Restam US$ {resta:.2f}. Aumente em openrouter.ai/settings/keys ou espere renovar.", "#/integracoes"))
    credito = httpx.get("https://openrouter.ai/api/v1/credits", headers=cabecalho, timeout=15).json()["data"]
    saldo = float(credito["total_credits"]) - float(credito["total_usage"])
    if saldo < SALDO_MINIMO:
        saida.append(_aviso("openrouter-saldo", "atencao", "Saldo do OpenRouter baixo", f"Restam US$ {saldo:.2f}.", "#/integracoes"))
    return saida


def assinatura() -> list:
    arquivo = config.FABRICA / "chatgpt_limites.json"
    if not arquivo.exists():
        return []
    janelas = json.loads(arquivo.read_text(encoding="utf-8")).get("janelas") or {}
    saida = []
    for nome, rotulo in (("janela", "de 5 horas"), ("semana", "da semana")):
        j = janelas.get(nome) or {}
        if (j.get("usado_pct") or 0) >= ASSINATURA_CHEIA and (j.get("volta_em") or 0) > time.time():
            volta = datetime.fromtimestamp(j["volta_em"], banco.BRASILIA).strftime("%d/%m %H:%M")
            saida.append(_aviso(f"assinatura-{nome}", "atencao", "Assinatura do ChatGPT no limite",
                                f"{round(j['usado_pct'])}% da janela {rotulo}, volta {volta}. Até lá as imagens saem pagas.", "#/integracoes"))
    return saida


def conexoes(usuario_id: int) -> list:
    return [_aviso(f"studio-{c['canal_id']}", "atencao", "Studio desconectado", f"{c['titulo']} precisa reconectar.", "#/integracoes")
            for c in studio.contas(usuario_id) if not c["valida"]]


def copia() -> list:
    ultimo, horas = backup.ultimo(), backup.horas_desde_o_ultimo()
    if ultimo.get("erro"):
        return [_aviso("backup-erro", "erro", "A cópia de segurança falhou", ultimo["erro"][:220])]
    if horas is None or horas > HORAS_SEM_BACKUP:
        return [_aviso("backup-velho", "atencao", "Sem cópia de segurança recente", "O Radar faz uma a cada 7 dias; a última passou de 8 dias.")]
    return []


def disco() -> list:
    livre = shutil.disk_usage(config.RAIZ).free / 1e9
    if livre < DISCO_MINIMO_GB:
        return [_aviso("disco", "atencao", "Disco quase cheio", f"Restam {round(livre)} GB. A fábrica precisa de espaço para renderizar.")]
    return []


def verificar(usuario_id: int) -> list:
    saida = []
    for olhar in (fila, travados, qualidade, fabrica, voz, openrouter, assinatura, lambda: conexoes(usuario_id), copia, disco):
        try:
            saida += olhar()
        except Exception as erro:  # noqa: BLE001
            print("aviso que não deu para olhar:", str(erro)[:160])
    return sorted(saida, key=lambda a: a["nivel"] != "erro")


def atuais() -> list:
    with _trava:
        return list(_atuais)


def _no_celular(aviso: dict) -> None:
    token, chat, topico = (config.AMBIENTE.get(k) for k in ("RADAR_TELEGRAM_TOKEN", "RADAR_TELEGRAM_CHAT", "RADAR_NTFY_TOPICO"))
    try:
        if topico:
            httpx.post("https://ntfy.sh/", timeout=15, json={"topic": topico, "title": aviso["titulo"], "message": aviso["texto"], "priority": 4})
        if token and chat:
            httpx.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=15,
                       json={"chat_id": chat, "text": f"{aviso['titulo']}\n{aviso['texto']}"})
    except httpx.HTTPError as erro:
        print("o aviso não chegou no celular:", type(erro).__name__)


def video_pronto(fid: int) -> None:
    """O aviso de vídeo pronto no celular (pedido do usuário em 2026-11-08), uma vez por pedido. Vai numa thread: quem
    chama é o vigia da fila, que não pode esperar o ntfy responder."""
    if fid in _prontos_avisados:
        return
    _prontos_avisados.add(fid)
    linha = banco.um("SELECT pedido, projeto FROM producoes_fila WHERE id=?", fid)
    if not linha:
        return
    try:
        pedido = json.loads(linha["pedido"] or "{}")
    except ValueError:
        pedido = {}
    canal = ""
    if pedido.get("canal_id"):
        c = banco.um("SELECT titulo FROM canais WHERE id=?", pedido["canal_id"])
        canal = (c["titulo"] if c else "") or ""
    titulo = (pedido.get("titulo") or linha["projeto"] or f"pedido {fid}").strip()
    texto = f"{titulo[:150]}{f' · {canal}' if canal else ''}. Está em Acompanhar › Arquivos e em Resultados."
    aviso = _aviso(f"pronto-{fid}", "info", f"✅ Vídeo pronto (pedido {fid})", texto, "#/resultados")
    threading.Thread(target=_no_celular, args=(aviso,), daemon=True, name=f"pronto-{fid}").start()


_prontos_avisados: set = set()


# qualquer problema de vídeo vai ao celular, até o de atenção (pedido do usuário em 2026-11-07: "qualquer problema no
# vídeo deve ser avisado por notificação"). O resto (conexões, disco, cópia, OpenRouter) só quando é erro
DE_VIDEO = ("fila-", "travado", "qualidade-", "genaipro", "fabrica", "parado-")


def vai_ao_celular(aviso: dict) -> bool:
    return aviso["nivel"] == "erro" or aviso["chave"].startswith(DE_VIDEO)


def _uma_volta(usuario_id: int) -> None:
    global _atuais
    if backup.na_hora():
        backup.fazer()
    novos = verificar(usuario_id)
    with _trava:
        _atuais = novos
    agora = time.time()
    for a in novos:  # o mesmo problema só volta ao celular depois de 12 horas
        if vai_ao_celular(a) and agora - _enviados.get(a["chave"], 0) > 12 * 3600:
            _enviados[a["chave"]] = agora
            _no_celular(a)


def _rodar() -> None:
    time.sleep(60)
    while True:
        try:
            dono = banco.um("SELECT id FROM usuarios ORDER BY id LIMIT 1")
            if dono:
                _uma_volta(dono["id"])
        except Exception as erro:  # noqa: BLE001
            print("a volta dos avisos falhou:", str(erro)[:160])
        time.sleep(VOLTA)


def iniciar() -> None:
    threading.Thread(target=_rodar, daemon=True, name="avisos").start()
