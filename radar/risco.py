"""Canal com risco de perder a monetização (pedido do usuário em 2026-10-14: "que assuntos o YouTube derruba a
monetização, ou tipos de vídeos, para não ser copiado").

Pelas regras do YouTube Partner Program: conteúdo **reaproveitado** (compilações, filmes e episódios inteiros, clipes,
reações, música acelerada), **inautêntico** (antes "repetitivo": em julho de 2025 o YouTube renomeou a regra e deixou
claro que vale para vídeo feito em série, com o mesmo molde e só o assunto trocado), **feito para crianças** (sem
anúncio personalizado, CPM baixíssimo) e **sensível** (violência explícita, sem censura). Usar IA ou não mostrar o
rosto não é proibido; o problema é o vídeo genérico em escala. Um canal assim pode estar estourando hoje e ser
desmonetizado amanhã: não vale copiar. A conta é só pelos títulos, de graça."""
import re
from collections import Counter

from . import gosto

REAPROVEITADO = re.compile(r"\b(compilation|full (movie|episode|film|match|game)|reupload|re-upload|highlights?|clips?|"
                           r"reacts?|reaction|lyrics?|slowed|reverb|sped up|nightcore|8d audio|best moments)\b", re.I)
INFANTIL = re.compile(r"\b(for kids|kids songs?|nursery|toddlers?|children'?s songs?|cocomelon|baby shark|learn colors)\b", re.I)
SENSIVEL = re.compile(r"\b(gore|uncensored|graphic footage|real death|death footage|18\+|nsfw|execution video)\b", re.I)

MOTIVOS = {
    "reaproveitado": "conteúdo reaproveitado (compilações, clipes, reações, música acelerada)",
    "em_serie": "vídeos feitos em série: o mesmo molde com só o assunto trocado",
    "infantil": "feito para crianças (sem anúncio personalizado)",
    "sensivel": "tema sensível (violência explícita, sem censura)",
}


def _molde(titulo: str) -> str:
    """O título sem números e sem o assunto: as 3 primeiras palavras e as 2 últimas."""
    palavras = re.findall(r"[a-z]+", gosto._simples(re.sub(r"\d+", "#", titulo)))
    return " ".join(palavras[:3] + ["…"] + palavras[-2:]) if len(palavras) >= 6 else " ".join(palavras)


def avaliar(titulos: list[str]) -> list[str]:
    """Os motivos de risco do canal (vazio = sem risco aparente), pelos títulos dos vídeos dele."""
    titulos = [t for t in titulos if t]
    if not titulos:
        return []
    motivos = []
    for nome, padrao in (("reaproveitado", REAPROVEITADO), ("infantil", INFANTIL), ("sensivel", SENSIVEL)):
        if sum(1 for t in titulos if padrao.search(t)) >= max(2, len(titulos) * 0.3):
            motivos.append(nome)
    if len(titulos) >= 6:
        mais, n = Counter(_molde(t) for t in titulos).most_common(1)[0]
        if n >= len(titulos) * 0.8 and mais:      # 80%: formato fixo de série boa (ex.: "The Rise and Fall of") passa
            motivos.append("em_serie")
    return motivos
