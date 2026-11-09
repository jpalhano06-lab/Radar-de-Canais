"""Os estilos de animação que cada pessoa guardou com um nome na página Animações, para usar de novo. Ficam no banco do
Radar (a tabela ajustes); quem confere se valem é a fábrica, na hora de usar."""
import json

from . import banco

LIMITE = 40


def _chave(usuario_id: int) -> str:
    return f"animacoes_estilos:{usuario_id}"


def listar(usuario_id: int) -> list[dict]:
    linha = banco.um("SELECT valor FROM ajustes WHERE chave=?", _chave(usuario_id))
    try:
        return json.loads(linha["valor"]) if linha else []
    except ValueError:
        return []


def _gravar(usuario_id: int, estilos: list[dict]) -> list[dict]:
    banco.executar("INSERT OR REPLACE INTO ajustes (chave, valor) VALUES (?, ?)", _chave(usuario_id),
                   json.dumps(estilos, ensure_ascii=False))
    return estilos


def salvar(usuario_id: int, nome: str, ajustes: dict) -> list[dict]:
    """Guarda com o nome; o mesmo nome troca o que estava guardado."""
    nome = " ".join(str(nome or "").split())[:60]
    if not nome:
        raise ValueError("Dê um nome ao estilo.")
    if not isinstance(ajustes, dict):
        raise ValueError("Os ajustes vieram em formato errado.")
    outros = [e for e in listar(usuario_id) if e["nome"].lower() != nome.lower()]
    if len(outros) >= LIMITE:
        raise ValueError(f"São até {LIMITE} estilos guardados. Apague um antes.")
    return _gravar(usuario_id, [{"nome": nome, "ajustes": ajustes}, *outros])


def apagar(usuario_id: int, nome: str) -> list[dict]:
    return _gravar(usuario_id, [e for e in listar(usuario_id) if e["nome"] != nome])
