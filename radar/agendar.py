"""Postar no dia marcado (pedido do usuário em 2026-11-17: "já arruma pra postar um hoje e outro amanhã").

Um pedido da fila pode sair marcado para subir no canal. O Radar não espera ninguém: a cada volta do vigia da fila
ele olha os marcados, e o que já está entregue vai para a fábrica publicar. Sem dia (`quando` vazio) o vídeo sobe
assim que fica pronto; com dia marcado ele sobe privado com o `publishAt` do próprio YouTube, que publica sozinho no
dia e na hora, com o Radar e o computador desligados.

Para subir, o canal precisa estar conectado na fábrica: o login do Google é um por canal, porque o token fica preso
ao canal escolhido na tela de consentimento. Sem isso o envio falha, o erro fica guardado e o Radar tenta de novo a
cada `ESPERA_NOVA_TENTATIVA` — conectar o canal basta para o vídeo subir sozinho na volta seguinte.

É o mesmo caminho dos dois vídeos de teste do canal novo (`teste_canal`), que tem o agendamento dele por ser de lá
a conta dos dias."""
from datetime import datetime

from . import banco, fabrica_api, fila

ESPERA_NOVA_TENTATIVA = 15 * 60   # segundos entre duas tentativas de envio depois de um erro
SEM_DESCRICAO = ("Sem a descrição do Claude ainda: o vídeo não sobe pelado. O Radar escreve e tenta de novo.")


def kit_do_video(usuario_id: int, item: dict) -> dict:
    """A descrição do Claude deste vídeo, escrita agora se ainda não existir (pedido do usuário em 2026-11-17:
    "coloque sempre descrição para o Claude criar e ir com o vídeo"). Ela vai no pedido de publicar porque a
    fábrica, sozinha, sobe com o publicacao.json dela."""
    from . import descricao, producao
    pedido = item.get("pedido") or {}
    perfil = pedido.get("perfil") or ""
    if not perfil and pedido.get("canal_id"):
        perfil = producao.config(usuario_id, pedido["canal_id"]).get("perfil", "")
    return descricao.garantir(usuario_id, item.get("projeto", ""), item.get("roteiro") or "",
                              titulo=pedido.get("titulo", ""), perfil=perfil)


def marcar(usuario_id: int, fid: int, canal_id: str, quando: str = "", com_thumbnail: bool = True) -> dict:
    """Marca um pedido da fila para subir no canal. `quando`: ISO na hora do canal ("2026-11-18T18:00"), ou vazio
    para subir assim que o vídeo ficar pronto."""
    if not fila.item(usuario_id, fid):
        raise ValueError("Esse pedido não está na fila.")
    if not canal_id:
        raise ValueError("Diga em que canal o vídeo sobe.")
    if quando:
        try:
            quando = datetime.fromisoformat(quando).strftime("%Y-%m-%dT%H:%M")
        except ValueError:
            raise ValueError("A data de postar não é uma data.")
    banco.executar("INSERT INTO agendamentos (usuario_id, fid, canal_id, quando, com_thumbnail, criado) "
                   "VALUES (?,?,?,?,?,?)", usuario_id, fid, canal_id, quando, int(bool(com_thumbnail)), banco.agora())
    return do_pedido(usuario_id, fid) or {}


def desmarcar(usuario_id: int, fid: int) -> None:
    """Tira o agendamento que ainda não foi mandado para a fábrica (o que já subiu, o YouTube é que desfaz)."""
    banco.executar("DELETE FROM agendamentos WHERE usuario_id=? AND fid=? AND enviado=''", usuario_id, fid)


def do_pedido(usuario_id: int, fid: int) -> dict | None:
    linha = banco.um("SELECT * FROM agendamentos WHERE usuario_id=? AND fid=? ORDER BY id DESC", usuario_id, fid)
    return dict(linha) if linha else None


def do_usuario(usuario_id: int) -> list[dict]:
    """Os vídeos marcados para subir, para o Acompanhar mostrar o dia em cada pedido."""
    return [dict(l) for l in banco.todos("SELECT * FROM agendamentos WHERE usuario_id=? ORDER BY id", usuario_id)]


def do_canal(usuario_id: int, canal_id: str) -> list[dict]:
    return [dict(l) for l in banco.todos("SELECT * FROM agendamentos WHERE usuario_id=? AND canal_id=? ORDER BY id",
                                         usuario_id, canal_id)]


def andar() -> list[int]:
    """Uma volta do agendamento, chamada pelo vigia da fila. Nunca levanta: a fila não pode parar por isto."""
    mudaram = []
    agora = datetime.now().timestamp()
    for linha in banco.todos("SELECT * FROM agendamentos WHERE url='' ORDER BY id"):
        try:
            item = fila.item(linha["usuario_id"], linha["fid"])
            if not item or not item.get("projeto"):
                continue
            if linha["enviado"]:
                # já mandado: o link aparece quando a fábrica termina o envio e grava o youtube.json
                publicado = fabrica_api.youtube_do_projeto(item["projeto"])
                if publicado and publicado.get("url"):
                    banco.executar("UPDATE agendamentos SET url=? WHERE id=?", publicado["url"], linha["id"])
                    mudaram.append(linha["fid"])
                continue
            if item["estado"] != "entregue":
                continue
            if linha["erro"] and agora - float(linha["tentado"] or 0) < ESPERA_NOVA_TENTATIVA:
                continue
            banco.executar("UPDATE agendamentos SET tentado=? WHERE id=?", agora, linha["id"])
            kit = kit_do_video(linha["usuario_id"], item)
            if not kit.get("descricao"):
                # nenhum vídeo sobe pelado: sem a descrição do Claude, espera a próxima volta (ela se escreve lá)
                banco.executar("UPDATE agendamentos SET erro=? WHERE id=?", SEM_DESCRICAO, linha["id"])
                mudaram.append(linha["fid"])
                continue
            try:
                fabrica_api.youtube_publicar(item["projeto"], canal=linha["canal_id"], quando=linha["quando"],
                                             com_thumbnail=bool(linha["com_thumbnail"]),
                                             titulo=kit.get("titulo", ""), descricao=kit["descricao"],
                                             tags=kit.get("tags") or [])
                banco.executar("UPDATE agendamentos SET enviado=?, erro='' WHERE id=?", banco.agora(), linha["id"])
            except fabrica_api.SemFabrica as erro:
                banco.executar("UPDATE agendamentos SET erro=? WHERE id=?", str(erro)[:300], linha["id"])
            mudaram.append(linha["fid"])
        except Exception as erro:  # noqa: BLE001 (o vigia nunca pode parar)
            print("postar no dia marcado:", erro)
    return mudaram
