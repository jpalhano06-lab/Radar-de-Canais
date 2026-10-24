"""As funções da extensão, numa fonte só.

A tela **Extensão** do site, a tela **Planos** e a própria extensão liam listas diferentes, escritas à mão em
três lugares: quem mexia numa esquecia as outras. Aqui fica a lista inteira, e cada função diz só de que
`recurso` ela depende — quem decide o preço continua sendo o `config.PLANOS`, que já é a fonte dos recursos.
Assim, mudar o que um plano abre não mexe nesta lista.

`onde` é a tela do YouTube em que a função aparece, e serve para agrupar na tela de ajuda.
"""
from .config import PLANOS, pode

# chave, nome, o que faz, onde aparece, o recurso que a abre, atalho
FUNCOES: list[dict] = [
    # ---- em cima de cada vídeo, enquanto a pessoa navega
    {"chave": "nota", "nome": "Nota de outlier", "onde": "video", "recurso": "extensao",
     "desc": "Quantas vezes o vídeo passou do normal do canal, escrito em cima de cada capa."},
    {"chave": "vph", "nome": "Views por hora", "onde": "video", "recurso": "extensao",
     "desc": "A velocidade do vídeo, medida e não estimada: views dividido pelas horas desde que ele saiu."},
    {"chave": "selo", "nome": "Selo Raro · Épico · Lendário", "onde": "video", "recurso": "extensao",
     "desc": "O selo que só o canal fora da curva recebe, na capa e na análise do canal."},
    {"chave": "reacao", "nome": "Reação do público", "onde": "video", "recurso": "extensao",
     "desc": "Quando o vídeo é curtido e comentado bem acima do normal, mesmo sem ser outlier de views."},
    {"chave": "inscritos", "nome": "Inscritos do canal", "onde": "video", "recurso": "extensao",
     "desc": "O tamanho do canal sem precisar abrir a página dele."},
    {"chave": "monetizado", "nome": "Canal monetizado", "onde": "video", "recurso": "extensao",
     "desc": "Se os vídeos do canal estão com anúncio."},
    {"chave": "sem-shorts", "nome": "Esconder os Shorts", "onde": "video", "recurso": "extensao",
     "desc": "Tira as prateleiras e os cartões de Shorts de todas as telas do YouTube."},
    {"chave": "som", "nome": "Sons dos gestos", "onde": "video", "recurso": "extensao",
     "desc": "Um som curto ao salvar, ao desfazer e ao achar um canal raro. Fica em silêncio enquanto houver vídeo tocando."},
    {"chave": "ler", "nome": "Ler os vídeos sem gastar cota", "onde": "video", "recurso": "extensao",
     "desc": "Enquanto você navega, a extensão lê os números que a página já mostra e guarda no Radar os que estouraram."},
    {"chave": "treino", "nome": "Selo do treino", "onde": "video", "recurso": "extensao",
     "desc": "Os vídeos que combinam com o canal seu já treinado no site ganham o selo, com o botão de salvar a ideia."},

    # ---- o painel ao lado do vídeo e o botão Radar
    {"chave": "painel", "nome": "Painel ao lado do vídeo", "onde": "painel", "recurso": "extensao",
     "desc": "Os números do vídeo, a curva de views, o canal, a capa e as tags sem sair da página."},
    {"chave": "capa", "nome": "Capa e números", "onde": "painel", "recurso": "extensao",
     "desc": "A capa em tamanho real, com quantos x o vídeo deu, e o botão de copiar a imagem."},
    {"chave": "tags", "nome": "Tags do vídeo e do canal", "onde": "painel", "recurso": "extensao",
     "desc": "As palavras que o dono do canal escondeu, com um clique para copiar."},
    {"chave": "transcricao", "nome": "Transcrição", "onde": "painel", "recurso": "extensao",
     "desc": "A fala inteira do vídeo com o tempo de cada trecho, para ler e copiar com ou sem os tempos."},
    {"chave": "titulo", "nome": "Copiar o título", "onde": "painel", "recurso": "extensao",
     "desc": "O título do vídeo na área de transferência, com um clique."},
    {"chave": "print-cartao", "nome": "Print do cartão", "onde": "painel", "recurso": "extensao",
     "desc": "A capa com o título, o canal, as views e a nota, como imagem, para colar onde quiser (Ctrl+V)."},
    {"chave": "provar", "nome": "Provar capa e título", "onde": "painel", "recurso": "extensao",
     "desc": "Põe a sua capa e o seu título no meio dos vídeos de verdade da página, para comparar."},
    {"chave": "roteiro", "nome": "Levar ao Roteiro", "onde": "painel", "recurso": "extensao",
     "desc": "Abre o Roteiro do Radar já com este vídeo.", "atalho": "Alt+R"},
    {"chave": "ideia", "nome": "Salvar ideia", "onde": "painel", "recurso": "extensao",
     "desc": "Guarda o vídeo na Entrada do painel do Radar."},
    {"chave": "claude", "nome": "Claude e ChatGPT no YouTube", "onde": "painel", "recurso": "extensao",
     "desc": "A abinha na beirada direita abre o painel do Claude, que sabe qual página está aberta.", "atalho": "Alt+C"},

    # ---- na página do canal e na busca
    {"chave": "numeros-canal", "nome": "Números do canal", "onde": "canal", "recurso": "extensao",
     "desc": "Na página do canal: a análise, a fase do nicho e os vídeos que passaram do normal."},
    {"chave": "resumo-busca", "nome": "Resumo da busca", "onde": "busca", "recurso": "extensao",
     "desc": "Uma faixa em cima dos resultados com os números dos vídeos da página e se o nicho está aberto."},
    {"chave": "filtros", "nome": "Filtros dos vídeos da página", "onde": "busca", "recurso": "extensao",
     "desc": "Os vídeos que a página já mostrou, em ordem de outlier, de views por hora ou de inscritos, com planilha.",
     "atalho": "Alt+V"},

    # ---- no YouTube Studio
    {"chave": "numeros-meu-canal", "nome": "Números do seu canal", "onde": "studio", "recurso": "extensao",
     "desc": "As views e os ganhos do SEU canal, lidos do YouTube Studio conectado."},
    {"chave": "foto-studio", "nome": "Foto com um clique no Studio", "onde": "studio", "recurso": "extensao",
     "desc": "Uma câmera no canto de cada cartão do Studio: um clique copia a foto do gráfico."},
    {"chave": "publicar", "nome": "Preencher a publicação", "onde": "studio", "recurso": "extensao",
     "desc": "Preenche sozinha os detalhes, os anúncios e o questionário do vídeo no Studio. Quem aperta publicar é você."},

    # ---- o que depende do plano
    {"chave": "salvar", "nome": "Salvar canal no Radar", "onde": "video", "recurso": "salvar",
     "desc": "Um clique no vídeo ou na página do canal guarda o canal no Radar, para você acompanhar.", "atalho": "Alt+S"},
    {"chave": "parecidos", "nome": "Canais parecidos", "onde": "canal", "recurso": "parecidos",
     "desc": "Uma aba nova no canal com os canais que falam dos mesmos assuntos, do mais parecido para o menos."},
    {"chave": "nicho", "nome": "Analisar o nicho", "onde": "canal", "recurso": "parecidos",
     "desc": "Se o nicho está nascendo, em corrida ou cansado, e quem são os concorrentes dele.", "atalho": "Alt+G"},
    {"chave": "videos-nicho", "nome": "Vídeos do nicho", "onde": "canal", "recurso": "parecidos",
     "desc": "Os vídeos dos canais parecidos com este, do que mais estourou para o menos."},
    {"chave": "linguas", "nome": "Método Fantasma", "onde": "painel", "recurso": "linguas",
     "desc": "Em que língua ninguém fez este vídeo ainda: a busca pronta em 9 línguas, sem gastar cota."},
    {"chave": "alta", "nome": "Canais novos em alta", "onde": "video", "recurso": "radar",
     "desc": "Uma faixa no topo da página inicial do YouTube com os canais novos que o garimpo achou crescendo."},
]

ONDE = {"video": "Em cima de cada vídeo", "painel": "No painel ao lado do vídeo", "canal": "Na página do canal",
        "busca": "Na busca do YouTube", "studio": "No YouTube Studio"}


def plano_de(recurso: str) -> str:
    """O plano mais barato que abre este recurso (a mesma conta do 402 do servidor)."""
    return next((k for k, v in PLANOS.items() if recurso in v["recursos"]), "pro")


def lista(plano: str | None = None) -> list[dict]:
    """A lista inteira; com o plano da pessoa, cada função já diz se está liberada para ela."""
    saida = []
    for f in FUNCOES:
        exige = plano_de(f["recurso"])
        saida.append({**f, "plano": exige, "plano_nome": PLANOS[exige]["nome"],
                      "liberada": pode(plano, f["recurso"]) if plano else None})
    return saida


def por_plano() -> dict[str, list[str]]:
    """Para a tela de planos: o nome de cada função que cada plano abre."""
    return {k: [f["nome"] for f in lista(k) if f["liberada"]] for k in PLANOS}


def contagem() -> dict:
    """Quantas funções no total e quantas no plano grátis — o número que a tela de ajuda mostra no alto."""
    todas = lista("gratis")
    return {"total": len(todas), "gratis": sum(1 for f in todas if f["liberada"])}
