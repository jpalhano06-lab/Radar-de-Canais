"""Limpeza depois da postagem: 48 h depois de o vídeo ser marcado como postado, saem os arquivos pesados.

Pedido do usuário em 2026-11-24, com o disco C: em 14,8 GB livres de 930 GB: "depois da postagem tudo é apagado, pra
não ficar ocupando espaço". O vídeo já está no YouTube, então a cópia daqui não precisa ficar.

Sai: final.mp4, narracao.wav e os outros .mp4/.wav da raiz do projeto, as pastas de mídia (imagens, animações, render,
narração, trilha, shorts...) e a pasta _ENTREGA em Downloads. Fica o registro, poucos MB: roteiro, .json, legendas,
thumbs, custos. Assim o vídeo continua nos Resultados do Radar com título, capa, custo e views. Os shorts saem junto,
postados ou não (escolha do usuário).

As 48 h dão tempo de perceber um envio que deu errado. Contam a partir da hora em que o vídeo foi marcado como postado
(resultado_postado). Vídeo marcado só pelo link colado, ou publicado pela própria fábrica (youtube.json), não tem
essa hora: aí conta a do youtube.json ou a do final.mp4.

Fica de fora o projeto que está mexendo (criação rodando, render em andamento, arquivo gravado na última hora) e o que
foi renderizado de novo depois de postado (alguém refazendo o vídeo).
"""
import json
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from . import banco, roteiro_claude

PRAZO_H = 48
MARCA = "limpo_pos_postagem.json"
PASTAS = ("render", "imagens", "midia", "animacoes", "animation_ai", "narracao", "trilha", "shorts", "antigas",
          "conferir", "revisao_video", "garimpo_provas")
EXTENSOES = (".mp4", ".wav")
PARADO_HA = 3600         # segundos sem gravar nada no projeto para ele contar como parado
INTERVALO = 3600         # de hora em hora o Radar confere se algum vídeo passou das 48 h


def _projetos() -> Path:
    return roteiro_claude.FABRICA / "projetos"


def _downloads() -> Path:
    return Path.home() / "Downloads"


def _segundos(texto: str) -> float | None:
    try:
        return datetime.fromisoformat(str(texto)).timestamp()
    except ValueError:
        return None


def _ler(arquivo: Path) -> dict:
    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _tamanho(caminho: Path) -> int:
    if caminho.is_file():
        return caminho.stat().st_size
    return sum(f.stat().st_size for f in caminho.rglob("*") if f.is_file())


def postados() -> dict[str, float]:
    """Projeto -> quando foi postado (segundos). Vale a primeira marca de qualquer pessoa."""
    quando: dict[str, float] = {}
    for linha in banco.todos("SELECT projeto, MIN(quando) AS quando FROM resultado_postado WHERE item='video' GROUP BY projeto"):
        s = _segundos(linha["quando"])
        if s:
            quando[linha["projeto"]] = s
    raiz = _projetos()
    sem_hora = {l["projeto"] for l in banco.todos("SELECT DISTINCT projeto FROM resultado_publicado")} - set(quando)
    if raiz.is_dir():
        sem_hora |= {p.name for p in raiz.iterdir() if (p / "youtube.json").is_file()} - set(quando)
    for nome in sem_hora:
        for arquivo in (raiz / nome / "youtube.json", raiz / nome / "final.mp4"):
            if arquivo.is_file():
                quando[nome] = arquivo.stat().st_mtime
                break
    return quando


def _entrega(projeto: Path) -> Path | None:
    """A pasta _ENTREGA em Downloads, só se ela estiver mesmo lá (nada fora de Downloads sai daqui)."""
    pasta = str(_ler(projeto / "entrega_pc.json").get("pasta") or "")
    if not pasta:
        return None
    caminho = Path(pasta)
    try:
        dentro = caminho.resolve().is_relative_to(_downloads().resolve())
    except OSError:
        return None
    return caminho if dentro and caminho.name.endswith("_ENTREGA") and caminho.is_dir() else None


def sobras(projeto: Path) -> list[Path]:
    """O que sai deste projeto: pastas de mídia, .mp4/.wav da raiz e a pasta da entrega."""
    itens = [projeto / p for p in PASTAS if (projeto / p).exists()]
    itens += [f for f in projeto.iterdir() if f.is_file() and f.suffix.lower() in EXTENSOES]
    entrega = _entrega(projeto)
    return itens + ([entrega] if entrega else [])


def _pode_limpar(projeto: Path, postado: float, agora: float, prazo_h: float) -> bool:
    if agora - postado < prazo_h * 3600:
        return False
    if (projeto / "render_andamento.json").exists():
        return False
    for nome in ("cenas.json", "criacao.json", "chamadas.jsonl", "final.mp4"):
        arquivo = projeto / nome
        if arquivo.exists() and agora - arquivo.stat().st_mtime < PARADO_HA:
            return False
    final = projeto / "final.mp4"
    if final.exists() and final.stat().st_mtime > postado + 60:
        return False      # renderizado de novo depois de postado: alguém está refazendo o vídeo
    return _ler(projeto / "criacao.json").get("status") not in ("processando", "aguardando")


def candidatos(agora: float | None = None, prazo_h: float = PRAZO_H) -> list[Path]:
    agora = time.time() if agora is None else agora
    raiz = _projetos()
    saida = []
    for nome, postado in postados().items():
        projeto = raiz / nome
        if projeto.is_dir() and not nome.startswith("_") and sobras(projeto) and _pode_limpar(projeto, postado, agora, prazo_h):
            saida.append(projeto)
    return sorted(saida, key=lambda p: p.name)


def limpar_projeto(projeto: Path) -> int:
    """Apaga os pesados do projeto e deixa a marca. Devolve os bytes liberados."""
    liberado, apagados = 0, []
    for item in sobras(projeto):
        try:
            tamanho = _tamanho(item)
            shutil.rmtree(item) if item.is_dir() else item.unlink()
        except OSError:
            continue          # arquivo aberto em outro programa: fica para a próxima volta
        liberado += tamanho
        apagados.append(str(item))
    anterior = _ler(projeto / MARCA)
    (projeto / MARCA).write_text(json.dumps({
        "quando": datetime.now().isoformat(timespec="seconds"),
        "liberado_bytes": int(anterior.get("liberado_bytes") or 0) + liberado,
        "apagados": (anterior.get("apagados") or []) + apagados,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return liberado


def limpo(nome: str) -> bool:
    """O vídeo já teve os pesados apagados depois de postado (continua pronto nos Resultados)."""
    return (_projetos() / nome / MARCA).exists()


def limpar(log=print, simular: bool = False, prazo_h: float = PRAZO_H) -> int:
    """Limpa todos os vídeos que passaram do prazo. Devolve os bytes liberados (ou os que liberaria, em simular)."""
    total, feitos = 0, 0
    for projeto in candidatos(prazo_h=prazo_h):
        bytes_ = sum(_tamanho(s) for s in sobras(projeto)) if simular else limpar_projeto(projeto)
        total += bytes_
        feitos += 1
        log(f"  limpeza pós-postagem: {projeto.name} {'liberaria' if simular else 'liberou'} {bytes_ / 2**30:.1f} GB")
    if feitos:
        log(f"limpeza pós-postagem: {feitos} vídeo(s), {total / 2**30:.1f} GB {'a liberar' if simular else 'liberados'}")
    return total


def _relogio():
    time.sleep(300)       # deixa o Radar terminar de ligar
    while True:
        try:
            limpar()
        except Exception as erro:
            print("limpeza pós-postagem falhou:", erro)
        time.sleep(INTERVALO)


def iniciar():
    if os.environ.get("RADAR_LIMPEZA_POSTADOS", "1") == "1":
        threading.Thread(target=_relogio, daemon=True, name="limpeza-postados").start()


if __name__ == "__main__":
    import sys

    limpar(simular="--apagar" not in sys.argv)
