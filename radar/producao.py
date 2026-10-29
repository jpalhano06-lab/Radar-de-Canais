"""A produção de cada canal: o que o Roteiro e a Thumbnail já puxam ao escolher o canal, e o Assistente ao lado.

Pedido do usuário em 2026-10-15: "no roteiro tenha um canal: escolhe o canal João o Lobo e ele já puxa a voz e o prompt
para criar o roteiro"; "na thumbnail, trabalhe junto com o Claude para criar o prompt"; e "do lado direito do roteiro e
da thumbnail, uma janela para uma IA como o ChatGPT, para regionalizar o título ou fazer mudanças".

- Cada canal guarda: o perfil da fábrica (é ele que tem a voz), o estilo de roteiro, o tempo, a língua, o estilo de
  thumbnail e para qual IA de imagem o prompt vai (Gemini ou ChatGPT). Sem nada salvo, o perfil da fábrica com o mesmo
  nome do canal (o editor da fábrica cria "canal-joao-o-lobo" com `nome: João o Lobo`) entra sozinho.
- O prompt da thumbnail é escrito pelo Claude (assinatura, `roteiro_claude._claude`) com o estilo do canal, o que a
  pessoa pediu ("tire o texto") e o que a thumbnail de referência mostra (descrita pelo modelo de visão grátis).
- O Assistente é o Claude também, com os dados do canal escolhido nele (o canal do Assistente é à parte do Roteiro)."""
import json
import re

from . import banco, roteiro_claude, thumb

PADRAO = {"perfil": "", "projeto_roteiro_id": "", "minutos": 8, "lingua": "", "thumb_projeto_id": "", "ia_imagem": "gemini",
          "agenda": None, "concorrentes": None,
          # o texto que a extensão cola na descrição do Studio, igual em todo vídeo do canal (pedido do usuário em
          # 2026-10-22: "mais padronizado, só mudando para o tema do vídeo, sem spoilers, apenas uma sinopse")
          # o modelo da descrição: vazio = o modelo padrão do Radar na língua do canal (publicar.modelo_padrao).
          # `marcas` é o que muda de canal para canal dentro do modelo pronto (as redes que o canal cita).
          "modelo_tipo": "geral", "marcas": "",
          # o padrão da publicação deste canal, que a extensão lê no Studio: de quantos em quantos minutos entra
          # anúncio e que tela final montar ("melhor" = vídeo melhor para o espectador + inscrever-se)
          "anuncio_cada": 1, "tela_final": "melhor"}
TELAS_FINAIS = {"melhor": "Vídeo (melhor para o espectador) + inscrever-se",
                "ultimo": "Copiar a tela final do último vídeo", "nenhuma": "Não mexer"}
IAS_IMAGEM = {"gemini": ("Gemini", "https://gemini.google.com/app"), "chatgpt": ("ChatGPT", "https://chatgpt.com/")}


def _perfil(nome: str) -> dict:
    """O que interessa do perfil da fábrica: o nome do canal e a voz (lidos do yaml, sem biblioteca de yaml)."""
    arquivo = roteiro_claude.FABRICA / "perfis" / f"{nome}.yaml"
    if not re.fullmatch(r"[\w.-]+", nome or "") or not arquivo.exists():
        return {}
    texto = arquivo.read_text(encoding="utf-8", errors="ignore")
    achar = lambda chave: (re.search(rf"^\s*{chave}:\s*(.+?)\s*(#.*)?$", texto, re.M) or [None, ""])[1].strip().strip("\"'")
    voz = achar("nome_da_voz") or achar("voz_edge") or achar("voice_id")
    return {"perfil": nome, "canal": achar("nome"), "voz": "" if voz.startswith("COLE_AQUI") else voz,
            "idioma_da_voz": achar("idioma_da_voz"), "provedor": achar("provedor")}


# ---------------------------------------------------------------- o rodapé da descrição, no perfil da fábrica
# Quem escreve a descrição é a fábrica, no publicacao.json de cada projeto: ela põe o resumo, os capítulos, os
# créditos e, no fim, o rodapé do canal (apresentação e aviso legal). O rodapé mora no perfil da fábrica, e o
# Radar edita de lá — assim existe UM lugar só, e o vídeo já sai do projeto com a descrição pronta.
# (pedido do usuário em 2026-10-24: "quero algo já automático direto na fábrica").
RODAPE_MAXIMO = 3000
_MARCA_RODAPE = "  rodape: |"


def _arquivo_do_perfil(nome: str):
    arquivo = roteiro_claude.FABRICA / "perfis" / f"{nome}.yaml"
    return arquivo if re.fullmatch(r"[\w.-]+", nome or "") and arquivo.exists() else None


def rodape_do_perfil(nome: str) -> str:
    """O texto que fecha a descrição de todo vídeo do canal. "" quando o canal ainda não tem um."""
    arquivo = _arquivo_do_perfil(nome)
    if not arquivo:
        return ""
    linhas = arquivo.read_text(encoding="utf-8", errors="ignore").split("\n")
    if _MARCA_RODAPE not in linhas:
        return ""
    saida = []
    for linha in linhas[linhas.index(_MARCA_RODAPE) + 1:]:
        if linha.strip() and not linha.startswith("    "):
            break                      # saiu do bloco indentado
        saida.append(linha[4:] if linha.startswith("    ") else "")
    return "\n".join(saida).strip()


def salvar_rodape(nome: str, texto: str) -> str:
    """Põe (ou troca) o bloco publicacao.rodape do perfil, sem encostar no resto do arquivo."""
    arquivo = _arquivo_do_perfil(nome)
    if not arquivo:
        raise ValueError("Este canal não tem perfil na fábrica.")
    texto = (texto or "").strip()[:RODAPE_MAXIMO]
    atual = arquivo.read_text(encoding="utf-8", errors="ignore")
    sem_bloco = re.sub(r"(?ms)^publicacao:\n(?:[ \t].*\n|\n(?=[ \t]))*", "", atual).rstrip("\n")
    if not texto:
        arquivo.write_text(sem_bloco + "\n", encoding="utf-8")
        return ""
    corpo = "".join(f"    {l}\n" if l.strip() else "\n" for l in texto.split("\n"))
    arquivo.write_text(f"{sem_bloco}\n\npublicacao:\n{_MARCA_RODAPE}\n{corpo}", encoding="utf-8")
    return rodape_do_perfil(nome)


def perfis() -> list[dict]:
    return [_perfil(p) | {"perfil": p} for p in roteiro_claude.perfis_da_fabrica()]


def _perfil_do_canal(titulo: str) -> str:
    """O perfil da fábrica que tem o mesmo nome do canal ("João o Lobo" → canal-joao-o-lobo)."""
    for p in perfis():
        if p.get("canal") and p["canal"].strip().lower() == (titulo or "").strip().lower():
            return p["perfil"]
    return ""


def canal_do_perfil(usuario_id: int, perfil: str) -> tuple[str, str]:
    """(id, título) do canal da pessoa que usa esse perfil da fábrica, pelo que está salvo ou pelo nome do canal."""
    if not perfil:
        return "", ""
    meus = banco.todos("""SELECT c.id, c.titulo FROM meus_canais m JOIN canais c ON c.id = m.canal_id
                           WHERE m.usuario_id=?""", usuario_id)
    for c in meus:
        salvo = banco.um("SELECT dados FROM canais_config WHERE usuario_id=? AND canal_id=?", usuario_id, c["id"])
        if salvo and (json.loads(salvo["dados"]).get("perfil") or "") == perfil:
            return c["id"], c["titulo"]
    nome = (_perfil(perfil).get("canal") or "").strip().lower()
    for c in meus:
        if nome and c["titulo"].strip().lower() == nome:
            return c["id"], c["titulo"]
    return "", ""


def config(usuario_id: int, canal_id: str) -> dict:
    linha = banco.um("SELECT dados FROM canais_config WHERE usuario_id=? AND canal_id=?", usuario_id, canal_id)
    dados = PADRAO | {"agenda": {"por_semana": 3, "dias": []}, "concorrentes": []} | (json.loads(linha["dados"]) if linha else {})
    canal = banco.um("SELECT titulo, nicho, subnicho, pais FROM canais WHERE id=?", canal_id) or {}
    if not dados["perfil"]:
        dados["perfil"] = _perfil_do_canal(canal.get("titulo", ""))
    p = _perfil(dados["perfil"])
    if not dados["lingua"]:
        from .fabrica_api import IDIOMA     # o fabrica_api importa este módulo
        dados["lingua"] = {c: l for l, c in IDIOMA.items()}.get(p.get("idioma_da_voz", ""), "português")
    return dados | {"voz": p.get("voz", ""), "canal": canal.get("titulo", ""), "salvo": bool(linha)}


def salvar(usuario_id: int, canal_id: str, dados: dict) -> dict:
    limpo = {k: dados[k] for k in PADRAO if k in dados}
    if "minutos" in limpo:
        limpo["minutos"] = max(1, min(60, int(limpo["minutos"] or 8)))
    if limpo.get("ia_imagem") not in IAS_IMAGEM:
        limpo["ia_imagem"] = "gemini"
    if "anuncio_cada" in limpo:
        limpo["anuncio_cada"] = max(1, min(60, int(limpo["anuncio_cada"] or 1)))
    if limpo.get("tela_final") not in TELAS_FINAIS:
        limpo["tela_final"] = "melhor"
    banco.executar("INSERT OR REPLACE INTO canais_config (usuario_id, canal_id, dados, criado) VALUES (?,?,?,?)",
                   usuario_id, canal_id, json.dumps(limpo, ensure_ascii=False), banco.agora())
    return config(usuario_id, canal_id)


# ---------------------------------------------------------------- o prompt da thumbnail, pelo Claude

SISTEMA_THUMB = """Você escreve prompts para uma IA de imagem (Gemini ou ChatGPT) criar thumbnails de YouTube para
canais dark (sem apresentador). Responda SÓ com o prompt, pronto para colar, sem comentários, sem aspas, sem título.
Regras: 16:9, 1280x720; uma ideia visual forte, legível no celular; siga o estilo do canal; siga à risca o que a pessoa
pediu (se ela pediu para tirar o texto, a imagem não tem texto nenhum); use a thumbnail de referência como base de
composição, mas peça uma imagem nova e original; escreva o prompt em inglês (as IAs de imagem entendem melhor), e
qualquer texto que apareça na imagem fica na língua do título do vídeo."""


def prompt_da_thumb(usuario_id: int, projeto_id: int | None, pedido: str, titulo: str, video_id: str, ia: str) -> dict:
    base = thumb.montar(usuario_id, projeto_id, titulo, video_id)
    texto = (f"Título do vídeo: {titulo or '(sem título)'}\n\n"
             f"O que a thumbnail de referência mostra: {base['referencia'] or '(sem referência)'}\n\n"
             f"Estilo do canal (o prompt base, já com os campos preenchidos):\n{base['prompt']}\n\n"
             f"O que a pessoa pediu agora: {pedido or '(nada a mais: siga o estilo)'}\n\n"
             f"A IA de imagem é o {IAS_IMAGEM.get(ia, IAS_IMAGEM['gemini'])[0]}. Escreva o prompt.")
    prompt = roteiro_claude._claude(SISTEMA_THUMB, texto)
    nome, link = IAS_IMAGEM.get(ia, IAS_IMAGEM["gemini"])
    return {"prompt": prompt, "referencia": base["referencia"], "estilo": base["projeto"], "ia": nome, "link": link}


# ---------------------------------------------------------------- o Assistente (a janela da direita)

SISTEMA_ASSISTENTE = """Você é o assistente de um produtor de canais dark do YouTube (vídeos narrados, sem rosto),
numa janela ao lado do Roteiro e da Thumbnail ou num painel dentro do YouTube. Ajuda com títulos (regionalizar para
outro país ou língua, deixar mais chamativo sem enganar), descrições, ganchos, ideias e ajustes no texto. Responda em
português, curto e direto, a não ser que a pessoa peça outra língua. Quando der opções, numere. Não invente fatos sobre
pessoas reais."""


def assistente(usuario_id: int, canal_id: str, mensagens: list[dict], pagina: dict | None = None,
               projeto_id: str = "") -> str:
    contexto = ""
    if projeto_id:  # o agente escolhido no painel do YouTube: as mesmas instruções que o Roteiro usa (2026-10-22)
        ag = banco.um("SELECT nome, instrucoes FROM projetos_roteiro WHERE id=? AND usuario_id=?", projeto_id, usuario_id)
        if ag and ag["instrucoes"]:
            contexto += (f"Instruções do agente \"{ag['nome']}\" (o jeito de trabalhar que a pessoa escolheu; valem "
                         f"por cima das regras gerais quando conflitarem):\n{ag['instrucoes'][:8000]}\n\n")
    if pagina:      # o painel do Claude dentro do YouTube manda o que está aberto na aba
        contexto += (f"A pessoa está no YouTube, nesta página: {str(pagina.get('titulo', ''))[:300]}"
                     f"{' (canal ' + str(pagina['canal'])[:100] + ')' if pagina.get('canal') else ''} — "
                     f"{str(pagina.get('url', ''))[:300]}\n\n")
    if canal_id:
        c = banco.um("SELECT titulo, nicho, subnicho, pais, inscritos FROM canais WHERE id=?", canal_id) or {}
        cfg = config(usuario_id, canal_id)
        titulos = [v["titulo"] for v in banco.todos("SELECT titulo FROM videos WHERE canal_id=? ORDER BY views DESC LIMIT 8", canal_id)]
        contexto += (f"Canal em foco: {c.get('titulo', '')} (nicho {c.get('nicho') or '?'}, {c.get('subnicho') or ''}; "
                     f"país {c.get('pais') or '?'}; língua dos vídeos: {cfg['lingua']}).\n"
                     f"Títulos que mais deram view no canal: {' | '.join(titulos) or '(nenhum ainda)'}\n\n")
    conversa = "\n\n".join(f"{'Pessoa' if m.get('papel') == 'pessoa' else 'Assistente'}: {str(m.get('texto', ''))[:4000]}"
                           for m in mensagens[-12:])
    return roteiro_claude._claude(SISTEMA_ASSISTENTE, contexto + "Conversa até agora:\n\n" + conversa
                                  + "\n\nResponda a última mensagem da Pessoa.")
