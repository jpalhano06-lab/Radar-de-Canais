"""A barra de carregamento da fábrica, na barra de tarefas do Windows.

Pedido do usuário em 2026-10-25: ver a produção andando sem abrir o Radar, igual o Chrome faz quando está
baixando um arquivo — o ícone na barra de tarefas enche de verde. Página nenhuma de navegador consegue pintar
a barra de tarefas; quem faz isso é o Windows, pelo `ITaskbarList3`, e só para um programa com janela própria.
Então é isto aqui: uma janelinha que pergunta a porcentagem ao Radar e pinta o ícone dela.

Minimize a janela e esqueça: o ícone continua na barra de tarefas, enchendo conforme o vídeo anda.

    uv run pythonw -m radar barra          (ou o BARRA-DA-FABRICA.bat, que é a mesma coisa)
"""
import ctypes
import json
import tkinter as tk
import urllib.error
import urllib.request
from ctypes import wintypes

from .config import PORTA

ESPERA_MS = 10_000          # de quanto em quanto tempo pergunta ao Radar
# os estados que o Windows sabe pintar no ícone: verde, vermelho e amarelo
NADA, VERDE, VERMELHO, AMARELO = 0x0, 0x2, 0x4, 0x8


# ---------------------------------------------------------------- o Windows
class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


def _guid(texto: str) -> _GUID:
    g = _GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(texto), ctypes.byref(g))
    return g


class BarraDaTarefa:
    """O `ITaskbarList3` do Windows, chamado na mão pelo ctypes (sem instalar nada).

    Não existe função solta para isto: é um objeto COM, e as funções dele vêm numa tabela, por posição —
    3 é o `HrInit`, 9 é o `SetProgressValue` e 10 é o `SetProgressState`.
    """

    def __init__(self):
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        eu = ctypes.c_void_p()
        erro = ole32.CoCreateInstance(ctypes.byref(_guid("{56FDF344-FD6D-11D0-958A-006097C9A090}")), None,
                                      1,                        # CLSCTX_INPROC_SERVER
                                      ctypes.byref(_guid("{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}")),
                                      ctypes.byref(eu))
        if erro:
            raise OSError(f"O Windows não entregou a barra de tarefas (erro {erro & 0xFFFFFFFF:#x}).")
        self._eu = eu
        tabela = ctypes.cast(eu, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        funcao = lambda i, *tipos: ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *tipos)(tabela[i])
        funcao(3)(eu)                                            # HrInit
        self._valor = funcao(9, wintypes.HWND, ctypes.c_ulonglong, ctypes.c_ulonglong)
        self._estado = funcao(10, wintypes.HWND, ctypes.c_int)

    def pintar(self, janela: int, estado: int, pct: int = 0) -> None:
        self._estado(self._eu, janela, estado)
        if estado != NADA:
            self._valor(self._eu, janela, max(1, int(pct)), 100)   # 0 de 100 não desenha nada: o mínimo é 1


def _icone(raiz: tk.Tk) -> tk.PhotoImage:
    """O ponto verde do Radar, desenhado aqui mesmo — sem o ícone, a barra de tarefas mostra a pena do
    tkinter, que não diz nada a ninguém."""
    lado, imagem = 64, tk.PhotoImage(width=64, height=64)
    centro, raio = (lado - 1) / 2, lado * 0.33
    linhas = []
    for y in range(lado):
        linha = []
        for x in range(lado):
            dentro = ((x - centro) ** 2 + (y - centro) ** 2) ** 0.5 < raio
            linha.append("#b6f23a" if dentro else "#0d0f14")
        linhas.append("{" + " ".join(linha) + "}")
    imagem.put(" ".join(linhas))
    return imagem


def _mao_da_janela(raiz: tk.Tk) -> int:
    """O número da janela que tem o botão na barra de tarefas. O tkinter entrega a janela de dentro; quem
    aparece na barra de tarefas é a de fora, a mãe dela."""
    raiz.update_idletasks()
    user32 = ctypes.windll.user32
    user32.GetParent.restype = wintypes.HWND
    user32.GetParent.argtypes = [wintypes.HWND]
    dentro = wintypes.HWND(raiz.winfo_id())
    return user32.GetParent(dentro) or dentro.value


# ---------------------------------------------------------------- o Radar
def _perguntar(porta: int) -> dict | None:
    """Pedido de 127.0.0.1 entra como a administração sem login nenhum (o acesso livre do Radar), então
    aqui não precisa de senha nem de token. `None` quer dizer: o Radar está desligado."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/acompanhar", timeout=6) as r:
            return json.load(r)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def _situacao(dados: dict | None) -> tuple[int, int, str, str]:
    """Vira (estado da cor, porcentagem, o número grande, a linha de baixo).

    Com mais de um vídeo na fábrica a barra mostra a média — é uma barra só, e a média é o quanto falta
    para a leva inteira acabar. Quem quiser o de cada um abre o Acompanhar.
    """
    if dados is None:
        return AMARELO, 100, "—", "O Radar está desligado"
    produzindo = dados.get("produzindo") or []
    parados = (dados.get("precisa_voce") or []) + (dados.get("parados") or [])
    if produzindo:
        pcts = [round(x.get("progresso") or 0) for x in produzindo]
        media = round(sum(pcts) / len(pcts))
        if len(produzindo) == 1:
            return VERDE, media, f"{media}%", produzindo[0].get("titulo") or "sem título"
        return VERDE, media, f"{media}%", f"{len(produzindo)} vídeos · " + " · ".join(f"{p}%" for p in pcts)
    if parados:
        titulo = parados[0].get("titulo") or "sem título"
        return VERMELHO, 100, "⏸", f"Parou: {titulo}" if len(parados) == 1 else f"{len(parados)} parados na fábrica"
    return NADA, 0, "—", "Nada sendo produzido agora"


# ---------------------------------------------------------------- a janelinha
def rodar(porta: int | None = None) -> None:
    porta = porta or PORTA
    raiz = tk.Tk()
    raiz.title("Fábrica")
    raiz.configure(bg="#0d0f14")
    raiz.geometry("260x96")
    raiz.minsize(200, 80)
    raiz._icone = _icone(raiz)              # guardado na janela: solto, o Python joga a imagem fora
    raiz.iconphoto(True, raiz._icone)
    numero = tk.Label(raiz, text="—", fg="#b6f23a", bg="#0d0f14", font=("Segoe UI", 28, "bold"))
    numero.pack(pady=(10, 0))
    linha = tk.Label(raiz, text="Perguntando ao Radar…", fg="#8d95a8", bg="#0d0f14",
                     font=("Segoe UI", 9), wraplength=240)
    linha.pack(pady=(2, 8))

    barra = BarraDaTarefa()
    janela = _mao_da_janela(raiz)

    def volta():
        estado, pct, grande, embaixo = _situacao(_perguntar(porta))
        numero.config(text=grande, fg={VERDE: "#b6f23a", VERMELHO: "#ff5263", AMARELO: "#ff9d42"}.get(estado, "#8d95a8"))
        linha.config(text=embaixo)
        raiz.title(f"{pct}% · Fábrica" if estado == VERDE else "Fábrica")
        barra.pintar(janela, estado, pct)
        raiz.after(ESPERA_MS, volta)

    volta()
    raiz.mainloop()
