"""Os projetos do claude.ai ligados aos agentes do Radar.

Pedido do usuário em 2026-10-29: "quero que faça uma ligação entre eles, e pra usar os projetos do Claude, por isso eu
criei". O claude.ai não deixa o Radar ler os projetos de fora, então quem lê é a extensão, no Chrome logado da pessoa
(claude-projetos.js), e manda para cá. Cada projeto fica ligado a um agente (pelo uuid): mudou lá, o agente muda aqui
na próxima leitura. As instruções do projeto moram no campo "descrição" dele (prompt_template vem vazio), e os
arquivos anexados (roteiros de exemplo) vêm junto e vão no roteiro."""
import json
import re
import unicodedata

from . import banco

# projeto quase vazio (o "Como usar o Claude" tem 160 letras) não vira agente novo
MINIMO_PARA_CRIAR = 300
# os arquivos do projeto vão no pedido do roteiro até este tanto: o Canada agente tem 651 mil letras de exemplos, o
# que encheria o Claude e gastaria o limite da assinatura a cada roteiro. Os mais novos entram primeiro
ARQUIVOS_NO_ROTEIRO = 120_000
ARQUIVOS_GUARDADOS = 400_000


def _normal(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", texto).strip()


def _nome(texto: str) -> str:
    """"AGENTE UK" e "UK AGENTE" são o mesmo nome."""
    return " ".join(sorted(re.sub(r"[^a-z0-9 ]", " ", _normal(texto)).split()))


def _parecidos(a: str, b: str) -> bool:
    """O texto do agente é uma cópia do projeto (talvez cortada ou um pouco mais velha): o começo é o mesmo."""
    a, b = _normal(a), _normal(b)
    if not a or not b:
        return False
    n = min(len(a), len(b), 2000)
    return n >= 200 and a[:n] == b[:n]


def _arquivos(lista) -> list[dict]:
    saida, total = [], 0
    for a in sorted(lista or [], key=lambda x: str(x.get("criado") or ""), reverse=True):
        texto = str(a.get("texto") or "")
        if not texto.strip() or total + len(texto) > ARQUIVOS_GUARDADOS:
            continue
        saida.append({"nome": str(a.get("nome") or "arquivo")[:200], "texto": texto, "criado": str(a.get("criado") or "")})
        total += len(texto)
    return saida


def sincronizar(usuario_id: int, projetos: list[dict], vistos: list[str] | None = None) -> dict:
    """Liga cada projeto a um agente e copia as instruções e os arquivos. Um projeto ainda sem ligação acha o agente
    que já era cópia dele (o mesmo começo de texto, ou o mesmo nome); sem nenhum, vira um agente novo.

    vistos são os uuids de TODOS os projetos que a extensão achou no claude.ai, arquivados também. Os agentes ligados
    a um projeto que não está entre eles voltam em "faltando": a extensão abre cada um direto no claude.ai e só os
    que dão 404 (excluídos lá) ela manda para excluidos_no_claude. Assim uma lista que veio pela metade não apaga
    agente nenhum (pedido do usuário em 2026-11-02: o agente excluído do Claude sai do Radar)."""
    agentes = banco.todos("SELECT * FROM projetos_roteiro WHERE usuario_id=?", usuario_id)
    resultado = {"atualizados": [], "ligados": [], "criados": [], "ignorados": [], "faltando": []}
    if vistos:
        presentes = {str(v) for v in vistos} | {str(p.get("uuid") or "") for p in projetos or []}
        resultado["faltando"] = [a["claude_uuid"] for a in agentes if a["claude_uuid"] and a["claude_uuid"] not in presentes]
    ligados = {a["claude_uuid"]: a for a in agentes if a["claude_uuid"]}
    livres = [a for a in agentes if not a["claude_uuid"]]
    apagados = {l["claude_uuid"] for l in banco.todos("SELECT claude_uuid FROM claude_ignorados WHERE usuario_id=?", usuario_id)}
    for p in projetos or []:
        uuid, nome = str(p.get("uuid") or ""), str(p.get("nome") or "").strip()[:60]
        instrucoes = str(p.get("instrucoes") or "").strip()[:100000]
        if not uuid or not nome:
            continue
        arquivos = _arquivos(p.get("arquivos"))
        agente = ligados.get(uuid)
        if not agente:
            agente = next((a for a in livres if _parecidos(a["instrucoes"], instrucoes)), None) \
                or next((a for a in livres if _nome(a["nome"]) == _nome(nome)), None)
            if agente:
                livres.remove(agente)
                resultado["ligados"].append(f"{nome} → {agente['nome']}")
        if not agente:
            if len(instrucoes) < MINIMO_PARA_CRIAR or uuid in apagados:
                resultado["ignorados"].append(nome)
                continue
            novo = banco.executar("""INSERT INTO projetos_roteiro (usuario_id, nome, instrucoes, tipo, criado)
                                     VALUES (?,?,?,?,?)""", usuario_id, nome, instrucoes, "roteiro", banco.agora())
            agente = {"id": novo, "nome": nome}
            resultado["criados"].append(nome)
        else:
            resultado["atualizados"].append(agente["nome"])
        banco.executar("""UPDATE projetos_roteiro SET instrucoes=?, claude_uuid=?, claude_nome=?, arquivos=?,
                          sincronizado=? WHERE id=? AND usuario_id=?""",
                       instrucoes, uuid, nome, json.dumps(arquivos, ensure_ascii=False), banco.agora(),
                       agente["id"], usuario_id)
    return resultado


def excluidos_no_claude(usuario_id: int, uuids: list[str]) -> dict:
    """Os projetos que o claude.ai disse não existirem mais (404): o agente ligado a cada um sai do Radar."""
    excluidos = []
    for uuid in {str(u) for u in uuids or [] if u}:
        agente = banco.um("SELECT id, nome FROM projetos_roteiro WHERE usuario_id=? AND claude_uuid=?", usuario_id, uuid)
        if agente:
            banco.executar("DELETE FROM projetos_roteiro WHERE id=? AND usuario_id=?", agente["id"], usuario_id)
            excluidos.append(agente["nome"])
    return {"excluidos": excluidos}


def texto_dos_arquivos(agente: dict | None) -> str:
    """Os arquivos do projeto, para irem no pedido do roteiro (até ARQUIVOS_NO_ROTEIRO letras, os mais novos antes)."""
    try:
        arquivos = json.loads((agente or {}).get("arquivos") or "[]")
    except ValueError:
        return ""
    partes, total = [], 0
    for a in arquivos:
        if total + len(a["texto"]) > ARQUIVOS_NO_ROTEIRO:
            continue
        partes.append(f"=== {a['nome']} ===\n{a['texto'].strip()}")
        total += len(a["texto"])
    return "\n\n".join(partes)


def apagado(usuario_id: int, agente: dict | None) -> None:
    """Apagou o agente ligado: o projeto continua no claude.ai, mas não vira agente de novo."""
    if agente and agente.get("claude_uuid"):
        banco.executar("INSERT OR IGNORE INTO claude_ignorados (usuario_id, claude_uuid) VALUES (?,?)",
                       usuario_id, agente["claude_uuid"])
