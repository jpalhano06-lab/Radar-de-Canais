"""Para onde todas as procuras do app olham (pedido do usuário em 2026-10-14): países de língua inglesa, os EUA de
preferência, e nunca os nichos que pagam pouco ou de histórias narradas. Vale para o garimpo, o Procurar nicho, o
Alerta e as listas das telas.

"Pode buscar em outros países da língua inglesa, mas de preferência os EUA. Não quero que fique limitado a esses
nichos, porém histórias e esses nichos que pagam pouco não são relevantes. Isso quero para todas as procuras do app."
"""
import re

from . import gosto

PREFERIDO = "US"
PAISES = ["US", "GB", "CA", "AU", "NZ", "IE"]
ACEITOS = set(PAISES) | {""}          # canal sem país informado também (muitos canais não dizem)
_OUTROS = ["GB", "CA", "AU"]

# CPM baixo (US$ 0,25 a 6 nas pesquisas de 2026) ou histórias narradas: não entram no Radar, no Alerta nem nas listas.
# Qualquer outro nicho entra, mesmo fora da lista do garimpo: o app não fica preso a ela.
IRRELEVANTES = {"Desenho Animado", "Ficção e Contos", "Games", "Infantil", "Música", "Comida", "Esportes",
                "Boxe e Luta", "Futebol", "Curiosidades", "Mitologia", "Motivação"}
# "histórias" no plural são contos; "história" no singular é o nicho de história (documentário), que fica
_HISTORIAS = re.compile(r"\b(historias|contos?|stories|story|narrad[ao]s?|reddit|creepypasta|fabulas?|lendas?|"
                        r"animad[ao]s?|desenhos?|novelas?)\b", re.I)


def regiao(n: int) -> str:
    """O país da busca de número n: duas em cada três nos EUA, a terceira no Reino Unido, Canadá ou Austrália."""
    return PREFERIDO if n % 3 != 2 else _OUTROS[(n // 3) % len(_OUTROS)]


def irrelevante(nicho: str | None, subnicho: str | None = "") -> bool:
    """Nicho que paga pouco ou subnicho de histórias narradas ("Histórias de Terror", "Contos Animados")."""
    if (nicho or "") in IRRELEVANTES:
        return True
    if (nicho or "") in _HISTORIAS_REAIS:
        return False          # "Histórias da Bíblia", "Histórias de Crimes Reais": fatos, não contos inventados
    return bool(subnicho and _HISTORIAS.search(gosto._simples(subnicho)))


_HISTORIAS_REAIS = {"Religião", "Crimes Reais", "História", "Mistério", "Guerra"}


def ordem_pais(pais: str | None) -> int:
    """Para ordenar: EUA primeiro, depois os outros de língua inglesa."""
    return 0 if (pais or "") == PREFERIDO else 1
