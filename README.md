# Radar de Canais

Produto separado da fábrica (pedido do usuário em 2026-10-13), no modelo do Dotti Finder, **feito do zero**: nada
de código, texto, marca ou visual de lá. O nome fica em `radar/config.py` (`NOME`), num lugar só, e no
`extensao/manifest.json`.

Três peças, uma conta:

| Peça | O que faz |
|---|---|
| **Site** (`radar/web`, porta 8400) | Radar (canais novos que estão indo bem, por nicho), Top 30, Outliers, Salvos, Achados (os parecidos com os salvos), Administração (contas, planos, cota, garimpo) |
| **Extensão do Chrome** (`extensao/`) | Em cada miniatura do YouTube: quantas vezes o vídeo fez o normal do canal e as views por hora. Ao lado do vídeo: números, curva de views, canal, capa em tamanho real, copiar título, tags; no Lite, salvar canal, em que língua ninguém fez e canais parecidos. Na página do canal: a análise e os vídeos que passaram do normal |
| **MCP** (`radar/mcp.py`) | O Radar dentro do Claude e do ChatGPT: 8 ferramentas de leitura (resumo, visões, canais, salvos, acharam, canal, outliers, títulos) |

## Ligar

1. `uv sync` nesta pasta (uma vez).
2. Dois cliques em **LIGAR-RADAR.bat** (ou `uv run python -m radar servidor`).
3. Crie a conta no site. **A primeira conta é a administração** (plano Pro).
4. Extensão: `chrome://extensions` → Modo do desenvolvedor → Carregar sem compactação → pasta `extensao`. Clique no
   ícone, entre com o mesmo e-mail e senha.

Chaves: `finder/.env` (`YOUTUBE_API_KEY`, `YOUTUBE_API_KEY2`..., `GROQ_API_KEY`...). Rodando dentro da pasta da
fábrica, o que faltar vem do `.env` da fábrica.

## Como mede

- **Normal do canal**: a **mediana** das views dos 30 vídeos maduros (3 dias ou mais) mais novos, separada entre
  longos e Shorts (até 3 min). Mediana, para o vídeo que estourou não virar o normal.
- **Nota de outlier**: views do vídeo ÷ normal do canal. **Views por hora**: views ÷ horas desde a publicação.
- **Fase**: nascendo (postando há menos de 3 meses), crescendo (os 10 últimos fazem 1,5x os 20 anteriores), estável,
  caindo (0,6x ou menos), parado (60 dias sem vídeo).
- **Selo**: lendário (300 mil por vídeo em até 6 meses), épico (100 mil em até 9), raro (30 mil em até 12).
- **Postando há**: pelo primeiro vídeo quando o canal tem até 50; senão, pela criação do canal (o "+" no site).
  Antes, o Kurzgesagt (2013) passava por canal de 7 meses e ganhava selo épico.
- Vídeo medido vale 1 hora, canal 24 horas (`medir.py`). Cada leitura de hora em hora vira um ponto da curva.

## Garimpo (`garimpo.py`)

Uma vez por dia sozinho (`RADAR_GARIMPO_AUTOMATICO=0` desliga), pelo botão da Administração ou
`uv run python -m radar garimpar [--unidades N]`. Busca os termos de cada nicho (`TERMOS`, mais
`dados/termos.json`) nos vídeos do último mês, um nicho por vez; cada termo volta depois de 3 dias. Entra no Radar
o canal criado há até 18 meses, com 3 a 400 vídeos e 10 mil views ou mais por vídeo. O Groq (grátis) dá o nicho e diz
se o canal é sem rosto (até 3 capas pequenas por pedido: o Qwen do Groq aceita 3 imagens, e a capa média gastava
6 mil tokens contra o limite de 7 mil por minuto). Vídeo com 5x o normal vai para os Outliers. Depois, cada canal
salvo procura os parecidos uma vez por semana e eles vão para os Achados de quem salvou.

**Cota**: 10.000 unidades por dia por chave (volta às 5 h de Brasília). Busca custa 100, medir canal novo uns 3.
O garimpo usa 60% do que sobrou (`RADAR_COTA_GARIMPO`). Primeiro teste (2026-10-13): 4 buscas, 522 unidades,
25 canais no Radar, 114 outliers. Uma chave rende uns 300 canais novos por dia; mais chaves (de outros projetos do
Google Cloud) rendem mais.

"Em que língua ninguém fez" não gasta cota: o Groq escreve a busca em 9 línguas e a extensão abre a busca do YouTube
ordenada pelos mais vistos.

## Planos (`config.PLANOS`)

Ainda não é para vender (2026-10-13): toda conta nova abre como Pro e o site não mostra planos nem página de venda. Os planos seguem no código para quando for vender: Grátis (a extensão), Lite (salvar, parecidos, línguas, achados), Pro (tudo).
Os preços são provisórios. A administração troca o plano e o vencimento de cada conta. **Falta**: pagamento
(Kiwify ou outro), entrar com o Google, transcrição, "canal monetizado" e publicar a extensão na Chrome Web Store.

## Testes

`uv run python -m pytest tests`: as contas, sem rede.

`node tests/app_js.test.mjs`: o `api()` do painel — a memória curta, a espera para o Radar voltar
(2s, 4s, 8s, 15s, 30s) e os trilhos de views e inscritos. Sem navegador e sem instalar nada: o trecho do
`app.js` roda com o `fetch`, o `document` e o `setTimeout` de mentira, então o teste mede quanto ele
esperaria em vez de esperar.

## Visual do painel

Pedido do usuário em 2026-10-13: abas à esquerda (Descobrir: Radar, Top 30, Outliers; Minha base: Salvos, Achados;
Ferramentas: Extensão, Administração), **a aba aberta em vermelho** (`--vermelho`, #e5383b) e o **verde** (#b6f23a)
como cor de referência (números, nota de outlier, nicho escolhido). Cada canal é um cartão largo com as capas dos 3
vídeos longos que mais renderam (`servidor._vitrine`), com a nota de outlier e a duração em cima da capa. Outliers é uma
grade de capas.

## Abas (2026-10-13, segunda leva, pedido do usuário: "adicione o possível", com o "para que serve" e filtros)

Cada aba abre com uma caixa verde **"Para que serve"** (o × esconde, "para que serve?" mostra de novo; fica no
navegador) e o mesmo texto aparece ao passar o mouse na aba. Textos em `AJUDA`, no `app.js`.

| Grupo | Aba | O que faz |
|---|---|---|
| Descobrir | Visão geral | números, canais em alta (views por dia), entraram esta semana, vídeos que mais estouraram, nichos |
| | Canais | o Radar inteiro com o painel de **Filtros** (abaixo) e 9 ordens |
| | Novos achados | o Radar pela data em que o garimpo achou (hoje, 3, 7, 30 dias) |
| | Grupos de canais | os subnichos como grupos: tamanho, mediana por vídeo, quantos crescendo; aberto (até 2 canais), em formação, concorrido (8 ou mais) |
| | Top 30 | por nicho |
| | Outliers | filtros de nota (3x a 50x), longo ou Short, data de publicação, views, canal pequeno, subnicho; botão "Fazer vídeo deste tema" |
| Minha base | Salvos, Novidades (vídeos novos dos salvos), Meus outliers (só dos salvos), Achados | |
| Produzir | Títulos | banco de títulos com 3x ou mais e gerador no estilo do nicho (Groq) |
| | Pauta para a fábrica | rascunho de roteiro (Groq) em `dados/pautas/`, com o comando `fabrica novo`. Não roda a fábrica sozinho: narrar e gerar imagens continua pedindo confirmação |
| Ferramentas | Medir canal | @, link do canal ou de um vídeo; "Pôr no Radar" classifica e entra na lista |

**Filtros de canal** (`servidor._filtro_canais`): nicho, subnicho, selo, fase, rosto (com/sem), país, inscritos de/até,
views por vídeo de/até, quantidade de vídeos, em alta (views por dia mínimas), começou a postar (nos últimos 1, 3, 6,
12 meses ou entre duas datas), postou por último (3, 7, 30 dias), achado pelo Radar (hoje, 7, 30 dias ou entre datas).
Os campos de número aceitam "20 mil", "1,5 mi", "10k". O filtro fica guardado no navegador por aba.

**Dados novos**: `velocidade` (views por dia dos vídeos do último mês: a medida de "em alta"), `historico` (uma foto por
dia de inscritos, views e vídeos de cada canal) e `ganho_7d` (inscritos ganhos na semana). O garimpo mede de novo os
salvos e os do Radar a cada 20 h (`garimpo.remedir`, até 35% da cota), e aprende buscas novas com os títulos que
estouraram (`aprender_termos`, tabela `termos_auto`, até 400). Outliers entram no banco a partir de 3x (a tela mostra
5x por padrão).

**Subnicho**: o Groq recebe os subnichos que já existem e reaproveita um quando serve. Sem isso cada canal ganhava um
só dele ("Viagem Histórica", "História Documentada") e os Grupos ficavam com 1 canal cada; com a lista, 25 canais
viraram 13 grupos ("Animais em Conflito" com 6).

## No ar para os sócios (túnel da Cloudflare, 2026-10-13)

Pedido do usuário: mandar para os sócios, pelo túnel (grátis, depende deste computador ligado). A Vercel não serve sem
reescrever: o banco é um arquivo SQLite (some a cada atualização lá), o garimpo dura 40 min e o relógio do garimpo
precisa de um programa sempre ligado.

- **Convite**: fora a primeira conta, só cria conta quem tem um link de convite (Administração → Convidar sócio).
  Cada link vale uma conta; o código não fica no banco, só o resumo dele. "Tirar acesso" apaga a conta.
- **Senha errada**: 8 erros em 15 min pelo mesmo endereço (o `cf-connecting-ip` do túnel) e espera (429).
- **Cookie seguro** quando o pedido vem por https (o cloudflared manda `X-Forwarded-Proto`; o uvicorn só confia nele
  vindo do próprio computador).
- **Não dorme**: com o servidor ligado, o Windows não entra em suspensão (`RADAR_ACORDADO=0` desliga). A tela apaga.
- **Extensão para os sócios**: aba Extensão → "Baixar a extensão (.zip)", já apontando para o endereço por onde o site
  foi aberto (`/api/extensao.zip`).
- **Cota**: os sócios dividem a cota do YouTube (10 mil por dia por chave). Mais chaves (`YOUTUBE_API_KEY2`...,
  cada uma de um projeto do Google Cloud) somam.

O túnel deste computador não existia (o editor.bbnews.cc e o mcp.bbnews.cc vêm de outra máquina). Passos no painel da
Cloudflare: Zero Trust → Networks → Tunnels → Create a tunnel → Cloudflared → nome `radar` → Windows → rodar o comando
`cloudflared.exe service install TOKEN` num PowerShell de administrador → Public Hostname `radar` . `bbnews.cc`,
tipo HTTP, URL `localhost:8400`. E uma Regra de Configuração para `radar.bbnews.cc` que desliga o "Estou Sob Ataque"
e a verificação de integridade do navegador, como a do MCP: sem ela, o desafio barra a extensão.

## Simplificado (2026-10-13, quarta leva, pedido do usuário: "muito bagunçado... quero tudo muito simples")

- **Menu de 4 abas que abrem embaixo** (`MENU` no `app.js`): Meu perfil (Meus canais, Salvos, Novidades), Descobrir
  (Procurar nicho, Em alta, Grupos, Top 30), Ideias (Vídeos que estouraram, Títulos, Roteiro), Ferramentas (Medir
  canal, Extensão, Administração). A aba aberta e a opção aberta ficam em vermelho. Saíram como abas próprias: Visão
  geral (virou "Em alta"), Novos achados (filtro "Achado"), Meus outliers (filtro "Só dos meus salvos") e Achados
  (fim da página de Salvos). As caixas "Para que serve" viraram uma linha cinza embaixo do título.
- **Meu perfil é a primeira página** (`perfil.py`, tabela `meus_canais`): conectar canal pelo @ ou link (dados
  públicos, sem senha), totais, um cartão por canal com os 3 últimos vídeos. A página do canal (`#/canal/ID`): gráfico
  de inscritos (do `historico`), últimos vídeos com nota, **ideias para copiar** (outliers do mesmo subnicho, depois
  do mesmo nicho, só do banco) e "Buscar mais ideias no YouTube" (o Groq escreve 2 buscas a partir dos vídeos que mais
  renderam no canal; uns 250 de cota), com "Procurar de novo" que muda o jeito (`perfil.JEITOS`: formato, período,
  ordem, inglês). Os canais conectados são medidos de novo todo dia, antes dos salvos.
- **Procurar nicho**: a busca olha nome, nicho, subnicho e o título dos vídeos de cada canal; "Procurar no YouTube"
  busca na hora (`perfil.procurar`, sem esperar o Groq: nicho e rosto ficam para o garimpo) e o termo entra no garimpo
  de todo dia ("Procurados"). Teste: "cobras venenosas", 37 canais vistos, 10 novos no Radar.
- **Filtros só de escolher** (`selects` no `app.js`): nicho, tamanho do canal (pequeno, médio, grande), views por
  vídeo, idade, quando foi achado, rosto e ordem. O escolhido fica verde; "limpar" volta tudo.

## Studio, roteiro pelo Claude e o "para que serve" de volta (2026-10-14)

- **"Para que serve"** voltou em todas as páginas (`AJUDA` no `app.js`): caixinha verde embaixo do título; o × esconde
  e o "?" ao lado do título mostra de novo.
- **YouTube Studio** (`studio.py`): no perfil, "Conectar com o Google" (o mesmo cliente OAuth da fábrica, só leitura:
  youtube.readonly, yt-analytics.readonly, yt-analytics-monetary.readonly). A página do canal conectado mostra views,
  horas assistidas, duração média, % assistido, inscritos ganhos e perdidos, impressões e cliques na thumbnail,
  receita estimada (só canal monetizado), views por dia, os 10 vídeos que mais renderam, fontes de tráfego e países,
  com 7, 28, 90 ou 365 dias e a comparação com o período anterior (guardado 1 h). **Passo único no Google Cloud**: o
  endereço de volta `http://localhost:8400/api/youtube/retorno` precisa estar em "URIs de redirecionamento
  autorizados" do cliente OAuth, e a YouTube Analytics API ativada no projeto. Testado: o Google recusa esse endereço
  enquanto ele não está cadastrado (o da fábrica, localhost:8080, passa). O login volta pelo `state` (o cookie de
  127.0.0.1 não vale em localhost). O canal do Studio entra em "Meus canais" sozinho.
- **Roteiro pelo Claude** (`roteiro_claude.py`, no perfil e em Ideias → Roteiro): título, tempo (3 a 30 min, 150
  palavras por minuto), língua, projeto e o link do vídeo de referência. A transcrição (`youtube-transcript-api`,
  legenda manual primeiro, depois a automática, em qualquer língua) vai como base; a thumbnail (maxres, depois sd, hq)
  é copiada para `dados/roteiros/NOME/thumbnail.jpg`, com "Baixar" e "Copiar imagem". Quem escreve é o
  `claude -p` deste computador, pela assinatura do claude.ai, numa pasta vazia, sem ferramentas e sem a
  ANTHROPIC_API_KEY no ambiente (com ela o Claude Code cobraria por uso). Roda em segundo plano (`/api/roteiros/tarefa`).
  Teste: 2 minutos em 26 s, 330 palavras a partir de 3.308 da transcrição. O botão "Fazer roteiro deste tema" dos
  vídeos leva o link e o título para o formulário. O roteiro de rascunho pelo Groq (pauta) saiu da tela.
- **Projetos** (`projetos_roteiro`): o estilo de cada canal (tom, público, estrutura), escolhido no formulário e
  enviado junto. O claude.ai não deixa ler os projetos de lá por fora: as instruções são coladas aqui.

## Trabalho, Explorar, bloquear e as perguntas da primeira vez (2026-10-14, sexta leva)

- **Menu de 3 abas**: Meu perfil (Trabalho, Meus canais, Salvos, Novidades, Preferências), Descobrir (Explorar, Procurar
  nicho, Vídeos que estouraram, Em alta, Grupos, Top 30), Ferramentas. Saíram a aba Títulos (o "Sugerir títulos" está
  no Trabalho) e a aba Roteiro (virou o Trabalho). Vermelho mais vivo (#ff1f35) na aba aberta e no botão principal.
- **Trabalho** (a página inicial): 1) a ideia: título com "Sugerir títulos" (Groq), link do vídeo de referência (mostra
  a capa e o título dele), tempo, língua, estilo; 2) o roteiro pelo Claude, editável, com a contagem de palavras e de
  minutos e a thumbnail da referência; 3) **Enviar para a fábrica** (`roteiro_claude.enviar`): `uv run fabrica novo`
  na pasta da fábrica (com `--sim`, que só pula o aviso de vídeo curto; criar não gasta), `titulo_entrega` no
  projeto.json e a thumbnail como `thumbnail_referencia.jpg`. Testado: o projeto nasceu com o título, o roteiro e a capa.
- **Roteiro limpo**: o pedido ao Claude proíbe título de parte e colchete, e `_limpar` tira "[TITULO] ...",
  "## Parte 2", "Introdução:" e linha curta sem pontuação no fim. Os roteiros antigos foram limpos.
- **Perguntas da primeira vez** (`gosto.py`, `#/boas-vindas`, depois em Preferências): nichos, línguas, formato, o
  que nunca mostrar (com rosto vem marcado: canal dark) e 1 a 3 canais de referência (medidos, classificados e com os
  parecidos indo para Salvos). Valem no Explorar, nos Vídeos que estouraram e nas ideias de cada canal.
- **Língua do título** (`gosto.lingua`): 3 letras de outro alfabeto já é "outras"; hindi com letras latinas ("Maut Ke
  Baad...") também. Das 882 ideias da base, 692 passavam antes; hoje passam 619, sem hindi nem bengali.
- **⊘ em cima de cada vídeo**: não mostrar mais este vídeo, o canal ou o subnicho (tabela `bloqueios`; desfaz em
  Preferências).
- **Explorar**: vídeos que estouraram sorteados com peso pela nota, "Mostrar outros" sorteia de novo e "Procurar mais
  no YouTube" busca um termo sorteado dos nichos da pessoa.
- **Ideias de um canal** (`gosto.ideias_para`): pelas palavras dos títulos do canal (parecença), mais o subnicho e o
  nicho, em vez de só o subnicho.
- **Procurar nicho**: só a caixa, tamanho e idade; o rosto segue as respostas.

## Meu trabalho, painel das ideias salvas e treino do algoritmo (2026-10-14, sétima leva)

- **Sem as perguntas da primeira vez** (pedido do usuário). As respostas antigas não valem mais para a língua: ela é
  um filtro de escolha em Ideias, Explorar e Vídeos que estouraram (`gosto.por_lingua`; padrão português, inglês e
  espanhol). A conta tinha marcado "outras" e as ideias vinham em russo.
- **Menu**: Meu trabalho (Roteiro, Meus canais, Ideias, Treinar algoritmo), Descobrir (Explorar, Procurar nicho,
  Vídeos que estouraram, Em alta, Grupos, Top 30, Canais salvos, Novidades), Ferramentas (Medir canal, Extensão,
  Bloqueados, Administração).
- **Meus canais**: conectar com o Google e, à vista, conectar só pelo @.
- **Roteiro de até 1 hora** (60 min, uns 9 mil palavras): se o Claude para antes do tamanho, ele continua de onde
  parou, até 4 vezes (`roteiro_claude.gerar`).
- **Ideias** (`trabalho.ideias`, `/api/meus-canais/ID/ideias`): uma aba por canal seu, filtros de língua, nota, data,
  tamanho do canal e ordem (mais parecido, nota, recente, views), e "Buscar mais no YouTube".
- **Painel da direita "Ideias salvas"** (`ideias_salvas`): o 💡 vermelho na borda abre e fecha em qualquer página;
  uma aba por canal (e "Geral"); cada ideia com capa, título, link, "Levar para o trabalho" (abre o Roteiro com o
  vídeo de referência) e ×. "💡 Salvar ideia" em todo vídeo: vai para o canal da aba aberta; senão pergunta qual.
- **Treinar algoritmo** (`trabalho.plano_de_treino`, tabela `treino`): para cada canal seu, 5 buscas (Groq, guardadas),
  12 vídeos que estouraram no assunto e até 6 canais. A extensão, com "Treinar para" escolhido no ícone, marca o
  progresso sozinha (busca feita, vídeo aberto por 1 minuto, canal aberto) e cola o selo **🎯 + ideia** nos vídeos
  do YouTube que dividem 2 ou mais palavras do assunto do canal (`trabalho.assunto`). A extensão **nunca assiste
  nada sozinha**: view automática é proibida pelo YouTube e marca a conta.

## Treinamento do algoritmo no site, filtros e aleatório (2026-10-14, oitava leva)

- **Treino no site, não no YouTube** (pedido do usuário; o "YouTube virgem" saiu, com a lista de buscas e a marcação de
  progresso da extensão). `treinamento.py`, tabela `treinamentos`. Na primeira vez que a pessoa abre um canal dela
  (Ideias ou a página do canal), em vez das ideias vem o assistente: 1) 1 a 3 canais de referência (medidos e
  classificados; dá para pular e usar só o canal); 2) vídeos para marcar ✓ Faria ou ✕ Não, 30 por vez, dos canais de
  referência e dos que estouraram falando do mesmo assunto, sorteados (`candidatos`); 3) com 10 a 20 escolhidos, as
  palavras ganham peso (as dos recusados ficam negativas), o Groq escreve 5 buscas e o Radar procura no YouTube (uns
  600 de cota). Teste: 25 canais medidos, 25 ideias novas, e as ideias do canal passaram de "as criaturas mais raras"
  para as batalhas que foram escolhidas. "Treinar algoritmo" no menu refaz o treino.
- **As ideias seguem o treino** (`gosto.ideias_para`): soma dos pesos das palavras do título; vídeo que só fala de
  assunto recusado sai. O selo 🎯 da extensão usa as palavras do treino (`trabalho.assunto`).
- **Filtros**: nas ideias do canal (também na página do canal) língua, nota, data, formato, tamanho do canal e ordem;
  no Explorar língua, nicho, nota, data, formato, tamanho do canal e rosto (`gosto.explorar(filtros=)`). O Explorar não
  usa mais o nicho das respostas antigas (limitava a "Animais" sem mostrar).
- **🔀 Aleatório em todas as telas**: no servidor (`ordem=aleatorio`: Procurar, Vídeos que estouraram, Ideias) e na
  tela, embaralhando o que já veio (Em alta, Grupos, Top 30, Salvos, Novidades).

## Acesso livre (2026-10-14)

Pedido do usuário: sem e-mail e senha "por enquanto". Sem sessão, todo pedido vale como a conta da administração
(`servidor._usuario_livre`; sem nenhuma conta, cria `local@radar`). O site não pede login e o rodapé diz "Acesso livre
neste computador"; a extensão fala com o Radar sem token. **Só neste computador**: pedido que não vem do localhost, ou
que traz `cf-connecting-ip`/`X-Forwarded-For` (túnel, proxy), continua precisando de login (testado: 401), e
`--publico` desliga o acesso livre. `RADAR_ABERTO=0` volta a pedir senha. As contas, os convites e o login continuam no
código para quando for vender ou dividir com os sócios.

## Início, treino separado e Radar de países (2026-10-14, nona leva)

- **Início** (a primeira página, `#/inicio`): o perfil, os canais da pessoa com o que falta em cada um (treinado,
  radar de países, Studio, com link para fazer) e o **mapa do app** (`MAPA` no `app.js`: cada parte, o que faz e o
  link).
- **Treinar algoritmo separado de Ideias**: a página do treino explica o que é, para que serve e quanto leva, mostra a
  faixa dos 3 passos (o atual em vermelho) e o estado do canal (treinado em tal dia, com quantos vídeos, as
  referências e as buscas). Ideias não abre mais o treino sozinha: mostra "seguindo o treino de..." ou o aviso
  "este canal ainda não foi treinado" com o botão.
- **Radar de países** (`radar_paises.py`, tabela `radar_projetos`, `#/radar-paises`): um projeto por canal com os
  países e a língua de cada um (28 países). O **📡** em cima de cada vídeo: tira toda a numeração do título
  (`sem_numeros`: "Top 10 Supermercados que Faliram em 2024" vira "Supermercados que Faliram em"), adapta a ideia a
  cada país pelo Groq (`ia.adaptar_ideia`: "grocery chains bankrupt Canada", "... United Kingdom"), busca no YouTube
  daquele país (regionCode + relevanceLanguage) e diz "⚠ já foi feito" (com os parecidos e as views) ou "✅ ninguém fez
  ainda". Vídeo que cita outro país não conta (`paises_citados`: "8 Big UK Grocery Chains" não vale para a Austrália).
  Uns 101 de cota por país; guardado 7 dias. Teste (mercado: Canadá, Austrália, Reino Unido): achou a versão
  canadense (4.527 views) e a britânica (71.886), em 3 s.

## App enxuto, página do canal e o radar pelo título exato (2026-10-14, décima leva)

- **Radar de países pelo título exato** (pedido do usuário: "buscar o título exato no outro país, só sem os
  números"): na mesma língua do título vai o próprio título sem números; em outra língua, a tradução fiel
  (`ia.traduzir_exato`, sem adaptar lugar nenhum), também sem números. Saíram a adaptação da ideia a cada país e o
  filtro de "vídeo de outro país".
- **Menu enxuto**: Meu trabalho (Início, Meus canais, Roteiro), Descobrir (Explorar, Procurar nicho, Vídeos que
  estouraram), Ferramentas (Extensão, Bloqueados, Administração). Em alta, Grupos, Top 30, Salvos, Novidades e Medir
  canal saíram do menu (os endereços continuam funcionando).
- **Meus canais**: dois botões grandes, "Trabalhar com um canal" (os canais em cartões, com o que falta em cada um) e
  "Adicionar canal" (Google ou só o @). Escolher o canal abre **a página do canal** (`#/canal/ID/aba`) com as abas
  Ideias, Treinar algoritmo, Radar de países (o radar daquele canal) e Métricas (Studio e últimos vídeos). Sem treino,
  a página abre na aba do treino. Os endereços antigos (`#/ideias-canal`, `#/treino`, `#/radar-paises`) levam para lá.
- **Início**: faixa vermelha com o "Olá", os dois botões principais e os números; os canais em cartões; "Como
  funciona" em 6 passos; e o mapa do app em cartões grandes.

## Azul, Alerta e thumbnail no Roteiro (2026-10-14, décima primeira leva)

- **Azul como cor principal** (`--vermelho` no CSS virou #2f6bff, o nome ficou para não mexer em tudo) e o vermelho
  (`--detalhe`) nos detalhes: avisos, números dos passos, o ⊘, o 💡, a borda das fotos dos canais.
- **Alerta** (`alertas.py`, Descobrir → Alerta): canal com menos de 4 mil inscritos, sem rosto, dos EUA (país EUA ou
  sem país, e títulos em inglês: um canal "EUA" com títulos em russo ficou de fora) e 20 mil ou mais por vídeo ou um
  vídeo com 100 mil ou mais. Os novos vêm primeiro, com o selo "novo"; abrir a página marca como vistos
  (`alertas_vistos`). No menu, o Alerta fica com um **ponto verde pulsando** quando há canal novo (conferido ao abrir e
  de 5 em 5 minutos). Hoje: Moments survival (963 inscritos, um vídeo com 228 mil) e Rare Kind (2.220, 272 mil).
- **Thumbnail no Roteiro** (`thumb.py`, tabela `thumb_projetos`): ao lado da ideia, a thumbnail do vídeo de referência;
  "Montar o prompt" descreve a capa pelo modelo de visão gratuito (guardado) e monta o prompt do projeto escolhido
  (campos {titulo}, {referencia}, {canal}), com "Copiar prompt" e "Abrir no Gemini". Projetos de thumbnail por canal ou
  para todos, como os estilos do roteiro. O Roteiro ganhou o "Para qual canal?". A extensão que cola o prompt no
  Gemini fica para depois.

## Visual da Apple e cores do app (2026-10-14)

- Fonte do sistema, fundo cinza-claro com cartões brancos, cantos grandes, sombra suave, menu de vidro fosco e botões
  em pílula. As cores vêm de variáveis no fim do `estilo.css` (`--acento` é a cor de destaque, que pinta tudo).
- Botão **Cores** no canto de cima, à direita: 10 cores prontas, uma cor livre e o modo Claro ou Escuro. Fica guardado
  no navegador de cada pessoa (`radar:cor` e `radar:tema`).
- A aba da borda direita mostra o nome "Ideias salvas" do lado de fora, com a contagem.

## Botão Radar em cada vídeo e abas de canal na direita (2026-10-14)

- Cada vídeo tem **📡 Radar** entre "Salvar ideia" e "Trabalho". Ele procura o título, sem os números, traduzido para
  a língua de cada país, e desenha um radar: verde perto do centro = ninguém fez ainda, vermelho fora = já fizeram
  (forte com 100 mil views ou mais, médio com 20 mil, fraco abaixo). Embaixo, um cartão por país; clicar mostra os
  vídeos achados. Canal sem radar próprio usa 8 línguas padrão (EUA, Brasil, Espanha, França, Alemanha, Itália,
  Polônia, Turquia), `projeto_id` 0 em `radar_paises.conferir`. Cada país gasta uns 101 de cota; fica guardado 7 dias.
- A borda direita tem uma aba por canal, com a foto e o nome escrito de pé; clicar abre as ideias salvas daquele canal.

## 🎯, inscrever no algoritmo, placar por país e cores (2026-10-14)

- **🎯 em cada vídeo**: curtida para o algoritmo de um canal seu ("quero ideias assim"). As palavras do título ganham
  peso 2 nas ideias daquele canal (`radar/alvos.py`, tabela `alvos`, somadas em `treinamento.pesos`). Clicar de novo desfaz.
- **+ Inscrever** (no dono de cada vídeo e nos cartões de canal): o canal inteiro entra no algoritmo; as palavras dos 15
  vídeos mais vistos dele pesam 0,4 e os vídeos dele que estouram sobem 2 pontos nas ideias. Ao inscrever, o canal é
  medido em segundo plano (tabela `canais_inscritos`). Fora da página de um canal, o site pergunta qual canal ensinar.
- Passar o mouse mostra a explicação curta (`data-dica`).
- **Oportunidade por país** no lugar do radar circular (que ficava igual ao do concorrente): nota de 0 a 100 por país
  (livre 100, menos 8 por vídeo quase igual, no mínimo 70; feito fraco 55; médio 30; forte 10), em barras, com a
  melhor aposta em destaque.
- Cores: principal e secundária (`--acento`, `--acento2`), aparência clara, cinza ou escura; botões sempre pintados
  (texto branco); barra colorida à esquerda dos blocos (principal nos de trabalho, secundária nos de descoberta).

## Correção do radar de países e ideias novas (2026-10-14)

- O radar dizia "ninguém fez" no Brasil para "15 Bizarre Animals from Papua...", que já existia em português. Três causas:
  a busca ia com a frase inteira traduzida (o YouTube devolvia outra coisa); a conta de parecido media o título achado
  e não a ideia; e só os 15 primeiros resultados eram olhados. Agora: busca pelas palavras do assunto
  (`palavras_da_busca`), conta pela ideia com a raiz das palavras (`mesma_ideia`, 60% = mesma ideia, 40% = parecido),
  vídeo em outra língua não conta (`na_lingua`) e 50 resultados por país (a busca custa 100 de cota com 15 ou com 50).
  Casos em `tests/test_radar_paises.py`.
- Nas ideias do canal, o Aleatório saiu: o **🔄 Buscar ideias novas** procura no YouTube pelo que a pessoa ensinou ao
  algoritmo (🎯, treino e canais inscritos, `perfil._sementes`) e mostra as novas em cima. Cada clique busca de outro jeito.
- O 🎯 fica ao lado do Inscrever, na linha do canal. Os enfeites que eram vermelho fixo seguem a cor secundária.

## Radar de países: segunda correção e o 🎯 no treino (2026-10-14)

- "15 Rarest and Most Beautiful Cat Breeds..." dava o Brasil como livre, e nos EUA os pássaros ("15 Rare Birds So
  Beautiful You Won't Believe They're Real") contavam como a mesma ideia. Agora a comparação (`mesma_ideia`):
  - pela raiz sem plural nem gênero (`_raiz`: gato e gatos, raras e raros);
  - palavras de 3 letras contam ("cat", `palavras`);
  - palavra de isca (`ISCA`: believe, real, mundo, bonitos, raros...) vale metade;
  - o mesmo número do título (o 15) soma 0,2, só quando o assunto já bate pela metade. A busca segue sem números.
- O 🎯 e o + Inscrever também entram no **Treinar algoritmo** do canal (`alvos._no_treino`): o vídeo curtido vira
  escolhido e o canal inscrito vira referência; desmarcar tira.

## O radar de países saiu do site e foi para a extensão (2026-10-14)

- No site, cada 📡 gastava ~800 da cota (uma busca de 100 por país) e a busca da API via só 50 resultados, numa ordem
  diferente da do YouTube. A cota de 10.000 acabava com 8 cliques mais o garimpo.
- Agora o **🌍 Oportunidade por país** fica no painel do vídeo na extensão (0.3.0). O servidor traduz o título
  (`radar_paises.preparar`, Groq, guardado) e a extensão abre a busca do YouTube de cada país
  (`/results?search_query=...&gl=BR&hl=pt`), lendo o `<script id="yt-initial-data">` da página. O servidor julga os
  resultados com as mesmas regras (`radar_paises.julgar`). Não gasta cota e funciona com a cota do dia acabada.
- Saíram do site: o botão 📡 dos vídeos, a aba Radar de países do canal e a etiqueta "radar" dos canais.
  O código antigo (`conferir`, `/api/radar-paises/*`) ficou, sem botão.

## Saíram as ideias para os nossos canais (2026-10-14)

- Pedido do usuário: "ideias de vídeos para nossos canais vamos retirar, vamos deixar apenas os tokens para nichos".
  A cota do YouTube fica para achar nichos (garimpo, Procurar nicho, Alerta, Explorar).
- Saíram do site: a aba Ideias e a aba Treinar algoritmo do canal, o 🎯, o + Inscrever e o 🔄 Buscar ideias novas.
  A página do canal ficou só com os números, os últimos vídeos e as métricas do Studio. As rotas antigas
  (`#/ideias-canal`, `#/treino`) levam para o canal. O código do treino e dos alvos ficou no servidor, sem botão.
- Ficaram: o 💡 Salvar ideia e o painel da direita (não gastam cota e levam ao Roteiro).

## Garimpo focado em CPM alto e sem lixo (2026-10-14)

- Antes: 20 nichos em português, inglês e espanhol, sem país. Dos 1.687 canais vistos, 1.546 foram descartados e só
  uns 9 serviam ao Alerta (História, Animais e Vida Selvagem).
- Agora (`garimpo.TERMOS` e `CPM`): 15 nichos dark de CPM alto ou médio (finanças, economia, negócios, tecnologia,
  direito, ciência primeiro), só em inglês e no YouTube dos EUA (`regiao=US`, `idioma=en`). Saíram desenho, contos,
  boxe, futebol, religião, mitologia e curiosidades. Canal de fora de US/GB/CA/AU/NZ/IE nem é medido.
- Cada termo guarda quanto rendeu (`buscas_feitas.vezes`, `total`, `zeros`): os que trazem canal vão primeiro, e o que
  deu 0 em 2 buscas seguidas fica 30 dias de lado. Termos aprendidos só nos nichos da lista e nunca em pt ou es.
  As procuras da pessoa ("Procurados") seguem sem país.

## Nichos por CPM e engajamento, e o filtro de risco (2026-10-14)

- `garimpo.NICHOS`: 19 nichos com (CPM mínimo, máximo, engajamento 1 a 3), das pesquisas públicas de 2026. Entraram
  carros, imóveis, mistério e religião (CPM baixo, mas audiência fiel). `prioridade` = CPM médio com até 50% a mais
  pelo engajamento; cada rodada dá mais buscas a quem tem prioridade maior (finanças 3, direito 2, religião 1).
- `radar/risco.py`: pelos títulos, marca canal reaproveitado (compilação, clipes, reação, música acelerada), feito em
  série (80% dos títulos no mesmo molde), infantil ou sensível. Esses canais não entram no Radar pelo garimpo nem no
  Alerta. Dos 145 canais do Radar, 5 seriam marcados. Testes em `tests/test_risco.py`.

## Regras de mercado para todas as procuras (2026-10-14)

- `radar/mercado.py`: países de língua inglesa (EUA, Reino Unido, Canadá, Austrália, Nova Zelândia, Irlanda), com os
  EUA em 2 de cada 3 buscas (`regiao`), e os nichos irrelevantes (`IRRELEVANTES`: CPM baixo; e subnicho de histórias
  narradas, menos em religião, crimes reais, história, mistério e guerra, onde a história é real).
- Vale no garimpo (nicho fora da lista entra com prioridade 8, só os irrelevantes não), no Procurar nicho (termo em
  português ou espanhol é traduzido para o inglês), no Alerta (EUA primeiro) e em todas as listas (`gosto.Filtro`).
- Limpeza feita: 31 canais saíram do Radar (irrelevantes ou com risco); ficaram 114.

## Criar: Roteiro com o canal, Thumbnail com o Claude e o Assistente (2026-10-15)

- Menu: Meu trabalho (Início, Meus canais), **Criar** (Roteiro, Thumbnail), Descobrir, Ferramentas.
- **Produção do canal** (`radar/producao.py`, tabela `canais_config`, card na página do canal): perfil da fábrica (a
  voz), estilo do roteiro, tempo, língua, estilo da thumbnail e IA de imagem. Sem nada salvo, o perfil da fábrica com
  o mesmo `nome:` do canal entra sozinho (João o Lobo → canal-joao-o-lobo, voz Davi Andrei).
- **Roteiro**: escolher o canal preenche estilo, tempo e língua e mostra a voz; o envio à fábrica já marca o perfil dele.
  "Salvar como padrão do canal" guarda as escolhas. A thumbnail saiu daqui para a aba própria (botão 🖼 Fazer a thumbnail).
- **Thumbnail**: o pedido em cima ("tire o texto"), o canal, o estilo e a IA; o Claude escreve o prompt
  (`producao.prompt_da_thumb`, com a descrição da referência pelo modelo de visão grátis). ChatGPT abre com o prompt
  escrito (`?q=`) e a thumbnail de referência copiada para colar; Gemini abre com o prompt copiado.
  `/api/thumb/imagem/ID` traz a thumbnail pelo próprio site (para poder copiar).
- **Assistente** à direita do Roteiro e da Thumbnail: o Claude, com o canal dele à parte (os dados do canal vão
  junto); atalhos de regionalizar, mais chamativo, inglês e descrição; a conversa fica no navegador, por canal.

## Correção: Roteiro como antes e a aba Título (2026-10-15)

- O usuário não quis a aba Thumbnail separada nem o Assistente no Roteiro. O Roteiro voltou ao layout de antes, com a
  thumbnail à direita (mais larga, `main` até 1680 px); dentro dela, o pedido, o estilo do canal, o ✨ Criar o prompt
  com o Claude e o Enviar para o Gemini ou ChatGPT. O canal ainda puxa a voz, o estilo e o tempo.
- Nova aba **Título** (Criar → Título, `tituloTela`): o link e o título do vídeo (a extensão vai mandar para cá
  depois), o chat com o Claude ocupando a direita, o botão "usar" em cada título sugerido (o que está entre aspas,
  4 palavras ou mais) e **Levar para o roteiro**, que abre o Roteiro com o título, o link, o canal e a thumbnail.
  Conferir no YouTube se o título já foi feito é manual.

## Sem a aba Título; ChatGPT na lateral; tudo ajustável no Roteiro (2026-10-15)

- A aba Título saiu (o usuário não gostou). Menu: Meu trabalho = Início, Meus canais e Roteiro (a thumbnail dentro dele).
- **ChatGPT na lateral**: o ChatGPT e o Gemini bloqueiam ser abertos dentro de outro site (iframe), então a aba
  verde "ChatGPT" na borda direita abre o ChatGPT de verdade numa janela encostada no lado direito da tela
  (`abrirLateral`, sempre a mesma janela "radar-lateral"), já logado na conta da pessoa. O Enviar da thumbnail usa ela.
- **No Roteiro**: "+ Adicionar um canal novo" na lista de canais (mede pelo @ ali mesmo) e "⚙ ajustar tudo", que abre
  a produção inteira do canal (voz, estilos, tempo, língua, thumbnail, IA) com o Salvar.

## Organização de produção, Acompanhar, Resultados e o envio que cola sozinho (2026-10-15)

- Menu no modelo do Robô do Dotti (sem copiar o visual): Início; **Produção** (Produzir = Roteiro, Acompanhar,
  Resultados); Descobrir; **Configuração** (Canais, Extensão, Bloqueados, Administração).
- **Canal** só com o que é do roteiro: língua, voz (perfil da fábrica) e **agente de roteiro** (o antigo "estilo").
  Criado em Configuração → Canais, e também dá para criar e ajustar no Produzir. Saiu o "Sugerir títulos".
- **Acompanhar** e **Resultados** (`radar/fabrica_api.py`): leem o editor da fábrica (porta 8080, com o
  FABRICA_TOKEN do .env da fábrica, que fica só no servidor). Acompanhar atualiza a cada 5 s e tem ▶ Produzir /
  ↻ Continuar (a rota "retomar" da fábrica: primeiro a estimativa, e só com o sim da pessoa produz). Resultados mostra
  o custo real de cada vídeo (por categoria e por minuto), o total, ▶ Assistir (o final.mp4 pelo Radar) e 📁 Abrir
  pasta (a da entrega). No Produzir, depois de enviar à fábrica, há o ▶ Produzir agora.
- **Enviar para o ChatGPT/Gemini com o prompt e a thumbnail**: com a extensão 0.4.0, o site guarda o envio
  (`/api/envios`, 10 min, uma vez só) e abre a página com #radar-envio=ID; `extensao/colar.js` pega o prompt e a
  imagem e cola na caixa de mensagem (evento de colar; reserva: o campo de arquivo). `extensao/site.js` avisa o site
  que a extensão existe. Sem a extensão, segue o jeito antigo.

## Resultados por canal, perguntas do canal e menos botões (2026-10-15)

- Resultados agrupados por canal (o canal vem do `nome:` do perfil da fábrica do vídeo), com o gasto de cada canal.
- A produção do canal virou perguntas, uma por vez, só na primeira vez (língua, voz, agente de roteiro); depois
  é uma linha simples com "editar". No Produzir, canal sem configuração abre as perguntas sozinho.
- Sem abas ao lado dos vídeos: "💡 Ideias" e "💬 ChatGPT" viraram botões pequenos no canto de cima, junto do Cores.
  Os botões dos cartões de vídeo ficaram pequenos e discretos.

## Canal ligado à fábrica: vozes com prévia, agente e tempo (2026-10-15)

- Menu de volta à organização do vídeo do usuário: Meu trabalho (Início, Canais, Roteiro, Acompanhar, Resultados),
  Descobrir (Alerta, Explorar, Procurar nicho, Vídeos que estouraram), Ferramentas (Extensão, Bloqueados, Administração).
- A configuração do canal ficou maior e com 4 perguntas: língua; **voz** (a biblioteca da GenAI Pro pela fábrica,
  `/api/fabrica/vozes` → `GET /api/vozes/genaipro` da fábrica, com ▶ para ouvir a prévia; escolher chama
  `POST /api/canais` da fábrica, que cria perfis/canal-NOME.yaml com a voz, e o Radar guarda esse perfil);
  **agente de roteiro** (com "Criar um agente novo" ali mesmo); **tempo dos vídeos**.

## Roteiro em passo a passo (2026-10-15)

- `trabalho()` virou 5 passos com a faixa em cima (como o "Como funciona" do Início): 1 Referência (link e título,
  com "usar o título da referência"); 2 Canal e agente (o canal traz voz, língua, agente e tempo; canal novo ou sem
  configuração abre as perguntas ali; agente, língua e tempo podem mudar só neste vídeo); 3 Roteiro (o Claude escreve,
  depois o editor); 4 Thumbnail (Sim / Não, pular; o sim abre o painel com o prompt do Claude); 5 Enviar (perfil da
  fábrica do canal, Enviar e ▶ Produzir agora). Ao lado, sempre: o ponto de partida (a thumbnail da referência) e a
  configuração deste vídeo. "Abrir" num roteiro feito começa no passo 3.
- A configuração do canal, depois de feita, é um cartão grande com as 4 respostas e o Editar.
- Os cartões de vídeo perderam a barra colorida da esquerda.

## Sem barras coloridas e a identidade escura com marrom-dourado (2026-10-15)

- As "abas" que o usuário pedia para tirar eram as barras coloridas na esquerda dos cartões: saíram de todos
  (cartões, blocos, avisos, perguntas, resultados, vídeos) e do título das páginas. Não recolocar.
- Identidade padrão: tema escuro com o marrom-dourado `#a2845e` (`IDENTIDADE` no app.js), aplicada uma vez a quem
  já usava (marca `radar:identidade-2`); o botão Cores continua trocando.

## Produzir centralizado, 4 passos, sem fazer thumbnail (2026-10-15)

- Saiu o passo da thumbnail (o prompt do Claude e o envio ao Gemini/ChatGPT ficam no código, sem botão). Ao lado
  fica só a thumbnail da referência, com Copiar e Baixar.
- `trabalho()`: coluna central de 1180 px, título "Produza seu próximo vídeo", os 4 números (fábrica ligada,
  produzindo agora, prontos, roteiros) e 4 passos: Canal e conteúdo (o canal configura tudo, com o cartão grande dele,
  e o link e o título), Ajustes (só se quiser mudar), Roteiro e Revisão (enviar e ▶ Produzir). Roteiros feitos ficam
  recolhidos embaixo.

- (2026-10-15) Passo 1 do Produzir: primeiro o link e o título; depois o canal em cartões (foto, nome, voz e língua,
  ou "ainda não configurado", e o Adicionar canal), no lugar da lista. A coluna do centro tem 900 px e o ponto de
  partida fica preso no canto direito da tela quando ela tem 1760 px ou mais (abaixo disso, vai para baixo).

## Sem Ajustes, Resultados com filtro e arrastar, menu fechado e botões que mudam o fundo (2026-10-15)

- Produzir em 3 passos (Canal e conteúdo, Roteiro, Revisão): o agente, a língua e o tempo vêm só do canal.
  O ponto de partida ficou maior (390 px), mais para dentro e preso no canto em telas de 1860 px ou mais.
- Resultados: filtro por canal (chips em cima) e arrastar o cartão para o bloco ou o chip de outro canal
  (`/api/resultados/{nome}/canal`, tabela `resultado_canal`, vale por cima do canal do perfil da fábrica).
  Os canais do Radar aparecem mesmo vazios, para receber vídeos.
- Menu: começa só com os três grupos (Meu trabalho, Descobrir, Ferramentas); clicar abre as opções (`menu-aberto2`).
  O grupo em que a pessoa está fica com o fundo da cor.
- Regra dos botões: selecionado ou com o mouse em cima, muda o FUNDO para a cor do app e a letra fica branca. A cor
  da letra nunca muda sozinha (menu, chips, botões, cartões de canal, opções, passos).

## Resultados em linhas, shorts, publicado e temas (2026-10-15)

- Resultados: centralizado (1100 px), abas de canal em cima (dá para arrastar o vídeo para elas), e cada vídeo numa
  linha: capa, título, canal, data e duração, ✓ Publicado (do youtube.json da fábrica, ou "Marcar como publicado" com
  o link, tabela `resultado_publicado`) com as views e curtidas (`/api/resultados/views`, 1 de cota a cada 50), os
  shorts ▶ 1 ▶ 2 ▶ 3 (shorts/S01.mp4, `/api/producoes/{nome}/shorts/{sid}`, abre em pé) e o custo à direita.
- Cores: sem a cor secundária (a mesma cor em tudo); cinza mais escuro; tema Preto e branco (fundo preto, botões
  brancos com letra preta).
- Na página do canal, a conexão com o YouTube virou um passo a passo explicado.

## A página do canal: painel, agenda, descrição e shorts, concorrentes (2026-10-15)

- `radar/canal_painel.py` e `/api/canal-painel/{canal}` (a "fila do canal" o usuário não quis):
  - Painel: inscritos, views por vídeo, gasto na fábrica dos vídeos prontos do canal e custo por mil views (dos
    publicados), e os 5 vídeos que mais renderam.
  - Agenda: vídeos por semana e dias; aviso quando o último vídeo passou de 1,5 vez o intervalo da agenda.
  - Descrição e shorts: `publicacao.texto_fixo` e `shorts.ativo/quantidade` gravados no perfil canal-*.yaml da
    fábrica pelo Python da própria fábrica (o Radar não tem yaml); nunca no perfil base.
  - Concorrentes: até 5 por canal (pelo @, medidos com uns 3 de cota); 🔥 quando um vídeo deles fez 3x o normal nos
    últimos 14 dias.

- (2026-10-15) Página do canal: saíram a agenda de postagem e a descrição e shorts (o código do perfil da fábrica
  ficou, sem botão). No lugar, **Prontos para postar** (`canal_painel.para_postar`: os vídeos prontos do canal ainda
  não publicados, com o título, a descrição e as tags do publicacao.json da fábrica): 📤 Postar no YouTube abre a
  tela de enviar vídeo do YouTube Studio do canal (studio.youtube.com/channel/ID/videos/upload), abre a pasta da
  entrega e copia o título; Copiar descrição e tags; ✓ Já postei marca com o link. Concorrentes na coluna da direita.

- (2026-10-15) Prontos para postar: cada vídeo numa linha com a thumbnail grande (300 px, clica e assiste), os
  shorts ao lado (cartões em pé com o quadro do próprio short, clica e assiste), Assistir, Copiar título, Copiar
  descrição, Postar no YouTube e, no canto, ✓ Postei tudo: marca o vídeo e os shorts como postados sem pedir link
  (`resultado_publicado.video_id = "-"`, que os Resultados mostram como ✓ Publicado sem link e sem views).

- (2026-10-15) Preto e branco: o fim do estilo.css tem um bloco "preto e branco: gerado" com a letra preta para todo
  seletor que tem fundo var(--acento|verde|detalhe) (refazer o bloco quando entrar botão novo com fundo da cor);
  os botões de contorno ficam com a letra clara. Conferido em 9 telas: nenhum texto da mesma cor do fundo.
- Prontos para postar: embaixo do "Postei tudo", uma linha para o vídeo e uma para cada short, com 📤 Postar (Studio
  na tela de enviar, pasta da entrega, título do item copiado) e ✓ Postei / desfazer (tabela `resultado_postado`).
  O vídeo só sai da lista quando ele e todos os shorts estão postados.

## Sócios pela internet, só olhando (2026-10-15)

- Endereço pensado: radar.bbnews.cc, um nome a mais no túnel da Cloudflare do editor, apontando para localhost:8400.
  Quem vem pelo túnel sempre faz login (o túnel traz o cabeçalho cf-connecting-ip); conta nova só por convite e já
  abre tudo (plano pro). Os convites ficam em `finder/convites-socios.txt` (fora do Git).
- `dono_da_fabrica`: produzir, enviar para a fábrica, trocar a voz do canal e gravar no perfil da fábrica só para a
  administração. "Abrir pasta" recusa quem vem de fora (abriria no computador da fábrica). O resto (Descobrir,
  Resultados, Acompanhar, assistir, roteiro) eles usam. A cota do YouTube e a assinatura do Claude são as do dono.

- (2026-10-15) Página do canal em duas colunas: à direita, fixo, o **Desempenho do último vídeo** no modelo do card do
  Studio (`studio.ultimo_video`, `/api/canal-painel/{canal}/ultimo`, guardado 15 min): views, comentários, curtidas,
  posição entre os últimos 10 (2 de cota) e, com o canal conectado ao Studio, impressões, taxa de cliques da
  thumbnail e duração média (Analytics, filtro video==ID; a API precisa estar ativada no projeto do Google).
- No cartão da configuração do canal, "editar o agente" (ou "criar um agente") abre o nome e as instruções do agente ali.

## O que o Robô do Dotti tinha e o Radar ganhou (2026-10-18)

Pedido do usuário: "acrescentar tudo que tem no Robô Dotti que falta no nosso Radar, como a quantidade de IA e todo o
processo", a janela de criar vídeo e "uma aba lá embaixo para as APIs". Feito do zero, no visual do Radar. Desenho em
`docs/superpowers/specs/2026-10-18-robo-no-radar-design.md`, plano em `docs/superpowers/plans/2026-10-18-robo-no-radar-a-d.md`.
Menu: Meu trabalho ganhou **Custos**; Ferramentas ganhou **Integrações** (só a administração).

- **Integrações** (`radar/integracoes.py`, `#/integracoes`): saldo de cada serviço (OpenRouter e Kie pela API deles,
  GenAI Pro pela fábrica, a cota do YouTube de hoje; Groq, Pexels e Pixabay grátis; Gemini com "Informar saldo") e um
  cartão por chave: testar (uma chamada barata, guardada 1 h), trocar, acrescentar (YouTube, Groq, Gemini e Pexels
  aceitam várias) e remover. A tela só recebe os 4 últimos caracteres. As do Radar ficam no `.env` onde já estão (chave
  nova vai para o `.env` do Radar); as da fábrica vão pela rota dela (`POST /api/config/chaves`), que só aceita os nomes
  que conhece: o OpenRouter (`OpenRouter_key`), as chaves extras numeradas e remover são gravados direto no `.env` da
  fábrica e valem quando ela reinicia (a tela avisa). O `.env` guarda os comentários e o fim de linha. Recusa quem vem
  pelo túnel.
- **Nova produção** (botão no topo ou **Alt+N**; o Ctrl+N o Chrome não deixa): título, referência (opcional), canal
  em chips (traz agente, idioma e tamanho), estilo do roteiro com o "Ideal para…" (campo novo do agente), idioma,
  tamanho em **caracteres** com os atalhos de 8 a 30 min (pela velocidade medida da voz do canal; 5,9 caracteres por
  palavra), "O Claude escreve" ou "Já tenho o roteiro", nicho, observação, e "Parar para eu revisar". À
  direita, a prévia com o custo provável (média de US$/min dos vídeos entregues do canal). **Salvar na Entrada** guarda
  sem gastar; **Criar e começar** é o sim para gastar. O Produzir de 3 passos continua.
- **Fila** (`radar/fila.py`, tabela `producoes_fila`): entrada → na fila → escrevendo → sua vez (revisão) → enviando →
  produzindo → entregue, ou erro. Um **vigia** no servidor (a cada 20 s) escreve o roteiro (não ocupa vaga), manda para a
  fábrica e chama a produção já confirmada quando há vaga: o limite "N ao mesmo tempo" (1 a 8, padrão 2, no topo do
  Acompanhar) conta os vídeos da fila e os da fábrica rodando fora dela. Fábrica desligada só faz esperar; servidor
  reiniciado no meio devolve o pedido para a fila.
- **Acompanhar novo**: à esquerda os blocos Precisa de você, Produzindo, Na fila, Entrada e Parados na fábrica (busca
  e canal); à direita o vídeo com o anel, a etapa e as abas **Acompanhamento** (as 6 etapas com o tempo de cada uma,
  do "Tempo por etapa" da fábrica), **Diagnóstico** (`radar/diagnostico.py`: de onde vieram as cenas, real × imagem de IA
  × Animation IA, pelo `midia.fonte` do `cenas.json`; confere com a linha "Origem" da fábrica, 86/71/51 no vídeo dos
  gatos; e o log com filtro e Baixar log: erro que a fábrica contornou, "seguindo com…", conta como aviso), **Arquivos**
  (assistir, legenda .srt, pasta) e **Tags e descrição** (da fábrica, com Copiar e Gerar). Sua vez: o roteiro para ler,
  salvar e aprovar. Confirmações na própria página. Aviso no computador quando um pedido fica pronto, para na revisão
  ou dá erro.
- **Custos** (`radar/custos.py`, `#/custos`): total do período, média por vídeo e por minuto, por provedor, por tipo e
  por canal, e a lista com o detalhe. O total vem da rota `/custos` da fábrica (o mesmo dos Resultados): o
  `custos_reais.json` só tem narração e imagens; texto, visão e o juiz a fábrica soma pelos `modelos_de_texto`.
- O "máximo de IA" na Nova produção saiu (pedido do usuário): a Parte E não será feita; a contagem real × IA do
  Diagnóstico continua.
- **Ajustes de tela** (pedido do usuário): o Início sem o "Olá" e sem os números, com os canais em cartões grandes
  (foto, inscritos, língua e voz, Abrir canal e + Fazer vídeo); na página do canal, o **Prontos para postar** logo
  abaixo do cartão do agente; o Roteiro centralizado e maior (até 1180 px, letra 16 px), com a barra Voltar/Próximo
  presa embaixo da tela.

## Descobrir para achar nicho: filtros grandes, créditos do YouTube (2026-10-19)

- **Menu**: "Canais" saiu de Meu trabalho. A página de cada canal (`#/canal/ID`) continua, aberta pelo Início (que
  fica marcado no menu), e o "+ Adicionar canal" do Início segue igual.
- **Filtros grandes** em todas as páginas que têm filtro (`.selects` no `estilo.css`): a linha ocupa a largura toda,
  em grade, com caixas de 50 px de altura e letra de 15 px; no celular, 2 por linha.
- **Aleatório** saiu do Explorar (mudar um filtro já sorteia outra leva) e do Vídeos que estouraram (a ordem
  "Aleatório" continua no filtro de ordem). O 🔀 do Procurar nicho ficou.
- **Painel dos créditos do YouTube** nas 4 páginas do Descobrir (`painelCota` e `GASTOS` no `app.js`): fica preso ao
  lado, com a cota de hoje (livre, usado, total, chaves) e quanto cada ação daquela página gasta (busca no YouTube 100
  a 250; filtrar, salvar e levar ao Roteiro 0). Lê a rota nova `GET /api/cota` (qualquer conta; a `/api/admin/cota`
  é só do admin) e se atualiza depois de cada busca no YouTube. Abaixo de 1000 px vai logo depois do título.
- **Vídeos que estouraram**: 8 vídeos por vez (duas linhas de 4), com "← Anterior" e "Próximo →" presos embaixo à
  direita da tela no PC (no celular, no fim da lista) (`/api/outliers` aceita `por`, até 60).
  Ficaram só 4 filtros: língua, nota, data e formato (saíram nicho, tamanho do canal, "só dos meus salvos" e ordem;
  vale a maior nota).
- **Cartão de vídeo do Descobrir** (`cartaoVideoGrande`, no Explorar e no Vídeos que estouraram), no jeito do niche
  finder: capa grande (hqdefault), 4 por linha numa tela de PC, a foto do canal ao lado do título, o nome do canal,
  views e data, e as pílulas de views por hora e inscritos. Sem fundo de cartão; Salvar ideia e Trabalho embaixo.
- **Gastar tudo agora** (quadro "Créditos do YouTube" no pé do menu, em todas as páginas): mostra a cota livre de
  hoje e, para o admin, o botão que roda `garimpo.gastar_tudo` (`POST /api/cota/gastar`). Primeiro roda o garimpo com
  100% da cota livre (o automático usa 60%); se os termos acabarem antes (cada um só volta depois de 3 dias), faz
  procuras com termos sorteados dos nichos e jeitos diferentes (`perfil.procurar`) até sobrar menos que uma busca.
  Enquanto roda, o quadro mostra "Garimpando… X de Y" e se atualiza a cada 5 s. O garimpo de todo dia continua igual.
  Com o mouse em cima, o botão explica o que faz; ao apertar, abre uma janela no meio da tela (`janelaGastar`) com
  quantos créditos serão usados, o que o garimpo faz, quanto leva e que as procuras no YouTube param até as 5 h,
  com "Sim, gastar tudo" e "Cancelar".
  Embaixo dos créditos, "🕑 Garimpo automático: hoje às 22:39" (23 h depois do último, `ultimo_garimpo` no
  `/api/cota`), com a explicação no mouse: roda sozinho com 60% da cota, só com o Radar ligado, não recupera o dia.
- **A extensão guarda os vídeos que estouraram**: `medir.medir_videos` (o que a extensão chama para cada miniatura
  que aparece no YouTube) põe na tabela `outliers` todo vídeo com 3x o normal do canal ou mais. Eles aparecem no
  Vídeos que estouraram e nas sugestões dos canais. O canal não entra no Radar por isso (continua sendo o garimpo).
- **Página do canal mais curta**: saíram o Painel do canal (números e "Os que mais renderam"), os Concorrentes, o
  Desempenho do último vídeo, as métricas do Studio e a caixa de conectar ao Studio (e o código delas). Ficaram o
  cartão do canal, a configuração, os Prontos para postar e os últimos vídeos. Embaixo, **Sugestões para este
  canal**: 8 vídeos que estouraram do banco, do subnicho do canal (ou do nicho, ou de tudo, se não tiver nada), com
  Anterior e Próximo; não gasta cota. O "← voltar" leva ao Início.

## Extensão 0.5.0: garimpar enquanto navega, sem cota (2026-10-19, fase 1)

Pedido do usuário: tirar o selo das miniaturas e trazer o que o Dotti Finder tem de bom, na nossa versão (só as
funções; nada de código, texto ou visual de lá). Fase 1 de 3 (2: painel do vídeo com capa, transcrição, tags e
"Levar ao Roteiro"; 3: dados do canal, monetização, Alt+S e canais novos na página inicial).

- **Sai o selo** da nota e das views por hora em cima de cada miniatura (ele pedia à API: 1 de cota a cada 50 vídeos
  e uns 3 por canal novo). O 🎯 do treino continua.
- **Leitor da página** (`extensao/ler.js` + `extensao/leitor.js`, este no world MAIN, antes da página): lê os
  vídeos do `ytInitialData` e das respostas do `/youtubei/v1/` que o próprio YouTube recebe (busca, início,
  sugeridos, canal, rolagem): id, título, canal, views, data (de "há 3 dias"), duração. Entende o jeito antigo
  (`videoRenderer`) e o novo (`lockupViewModel`, com o texto completo no `accessibilityLabel`), em português, inglês
  e espanhol, com as abreviações ("1,2 mi", "12K", "há 7 h"). Só lê; não muda nenhuma resposta.
- O `content.js` junta e manda ao Radar (`POST /api/ext/vistos`, `radar/pagina.py`): o vídeo entra no banco (o que
  já existe só atualiza as views; a data exata da API fica), uma leitura por hora vira a curva, e com o canal
  conhecido sai a nota; 3x ou mais vai para o Vídeos que estouraram. Canal que o Radar não conhece: a extensão baixa
  a página de vídeos dele (`/channel/UC.../videos`, 6 por vez, 1,2 s entre um e outro) e manda
  (`POST /api/ext/canal-lido`): sai o normal do canal (a mesma mediana do `metricas.base`) e, se passar nas regras do
  garimpo (10 mil por vídeo, 3 a 400 vídeos, até 18 meses, inglês/português/espanhol, sem risco), o canal entra no
  Radar e o Groq diz o nicho e o rosto depois. Sem saber o primeiro vídeo (mais vídeos do que a página mostra), só
  entra canal de até 100 mil inscritos, e sem o selo Raro/Épico. Canal lido só é lido de novo depois de 7 dias.
- **Resumo da busca**: em cima dos resultados, se o nicho está aberto (🟢 canal pequeno estourando, 🟡 estoura em
  canal maior, ⚪ parado), com vídeos lidos, média e mediana de views, quantos dos últimos 30 dias, quantos com 3x e
  quantos em canal de até 10 mil inscritos. As notas chegam conforme os canais são lidos.
- **Vídeos desta página** (botão no canto de baixo): uma janela com tudo que a página mostrou, para ordenar (nota,
  views, views por dia, canal menor, mais novos) e filtrar (só longos, só canal pequeno, últimos 30 dias). A página
  do YouTube não muda.
- **Esconder os Shorts**: no ícone da extensão (prateleiras, cards e o atalho do menu). O ícone também mostra o que
  foi lido hoje (`GET /api/ext/hoje`): vídeos lidos, quantos estouraram e canais novos no Radar.
- Teste com páginas de verdade (busca em português e a página de vídeos de um canal): 20 de 20 vídeos com canal,
  views, data e duração; 3 canais lidos; notas de volta; a cota não mudou. `tests/test_pagina.py`.
- O painel do vídeo aberto e o da página do canal ainda usam a API (ficam para as fases 2 e 3).

## Extensão 0.6.0: o vídeo aberto (2026-10-19, fase 2)

- **Painel do vídeo sem cota**: os números vêm do player da própria página (`movie_player.getPlayerResponse()`, pedido
  pelo `content.js` ao `leitor.js` por postMessage): views, duração, tags, descrição e a **data exata** de publicação
  (a do `microformat`, guardada em UTC). A nota sai do `POST /api/ext/vistos`; o canal, a curva e o "salvo" do
  `GET /api/ext/painel/{id}` (só o banco). Canal que o Radar não conhece é lido pela página dele na hora. Saíram as
  curtidas e os comentários (eram da API).
- **Abas**: Números (nota, views, por hora, publicado, duração, curva, cartão do canal), **Capa** (tamanho real,
  abrir e copiar), **Transcrição** e **Tags** (copiar). A transcrição sai do botão "Mostrar transcrição" do próprio
  YouTube: o `leitor.js` clica nele, lê a resposta do `get_transcript` no fetch e fecha o painel do YouTube. Pedir
  direto ao `get_transcript` dá 400 ("Precondition check failed") e a legenda do player (`timedtext`) vem vazia
  (testado em 2026-10-19). Cada trecho tem o tempo, que leva o vídeo até ali; "Copiar a fala inteira".
- **✍️ Levar ao Roteiro**: abre o Radar em `#/trabalho?ref=ID&titulo=...` e o Roteiro já começa com o vídeo de
  referência. **🖼️ Print do cartão**: monta uma imagem 1280×930 (capa, duração, título, canal, views, idade e a nota)
  e copia para colar com Ctrl+V. A capa vem pelo `background.js` (`i.ytimg.com` nas permissões), para o canvas poder
  ser copiado. Continuam: Salvar ideia, Copiar título, Oportunidade por país, Salvar canal e Canais parecidos.
- **🧪 Provar capa e título** (botão no canto, na página inicial e na busca): escolhe a imagem, o título e o nome do
  canal, e o cartão aparece como o primeiro vídeo da página, do mesmo tamanho dos outros, só na tela da pessoa (nada
  é enviado). O × no cartão tira.
- Conferido no Chrome do usuário (YouTube em tema escuro): painel com as 4 abas, capa 1280 px, 29 tags, print do
  cartão copiado, e o cartão do "Provar" como o primeiro da página inicial, com 700 px como os outros. As cores do
  tema escuro do YouTube (`html[dark]`) foram acertadas no `content.css`.

## Extensão 0.7.0: canais (2026-10-19, fase 3)

- **Página do canal no YouTube sem cota**: a faixa embaixo do cabeçalho vem do banco (`GET /api/ext/canal-dados/{id}`,
  `pagina.canal_dados`); o canal da página vem do `leitor.js` (o último que a página mostrou). Canal que o Radar não
  conhece (404) é lido pela página de vídeos dele antes. Mostra o cartão do canal, as **views dos últimos 30 vídeos**
  (barras, mais forte quando estourou; o título e a nota no mouse), os **inscritos por dia** (do `historico`, quando o
  Radar viu o canal em dias diferentes), os que passaram do normal, Salvar canal e Canais parecidos.
  O `/api/ext/canal/{ref}` (que media pela API) ficou sem uso pela extensão.
- **Monetização** (colunas novas `canais.anuncios` e `canais.membros`): anúncio no player do vídeo aberto
  (`adPlacements`/`playerAds`) marca o canal "💰 com anúncios"; o botão "Seja membro" (no cabeçalho do canal ou no dono
  do vídeo) marca "⭐ tem membros". Só se marca o sim: quem tem YouTube Premium não recebe anúncio, e a falta do botão
  não prova nada. Aparece no cartão do canal (painel do vídeo e página do canal).
- **Alt+S** (`commands` no manifest; troca em `chrome://extensions/shortcuts`): salva no Radar o canal do vídeo aberto
  ou da página do canal, com um aviso rápido embaixo da tela. A página também ouve o Alt+S (o atalho do Chrome fica com
  uma extensão só, e o Dotti Finder também usa Alt+S). Com o Dotti ligado, o Alt+S vai para ele: desligue o Dotti ou
  troque o atalho em `chrome://extensions/shortcuts`.
- **🔥 Canais novos em alta** no topo da página inicial do YouTube (`GET /api/ext/em-alta`, `pagina.em_alta`): os 12
  canais do Radar que começaram há até 3 meses e mais fazem views por vídeo, com foto, views por vídeo, inscritos e
  há quanto tempo começaram. O × esconde até o dia seguinte. `tests/test_pagina.py`.
- Conferido no Chrome do usuário: a fileira de 12 canais em alta no início do YouTube e a faixa da página do
  @NatGeo (30 barras, os que passaram do normal) sem gastar cota.

## Extensão 0.8.0: filtros e menu no jeito do Dotti (2026-10-19)

Pedido do usuário (com prints do Dotti Finder): "crie um igual o do Dotti Finder, falta os filtros, falta tudo". Mesma
organização, código e estilo nossos.

- **Janela de filtros** (botão 📊 Vídeos desta página): à esquerda, **Atalhos** (Canal pequeno que estourou, Rápidos
  agora, Desta semana, Os mais vistos), **Filtrar** com faixas de duas pontas para **inscritos** (0 a 5M+) e **views**
  (0 a 20M+), **Publicado** (Tudo, 1 hora, Hoje, 7 dias, 30 dias, 1 ano) e **Esconder Shorts**; em cima, "20 de 20
  vídeos", **Carregar mais vídeos** (rola a página do YouTube, que traz mais) e **Baixar planilha** (CSV com título,
  canal, inscritos, views, views por hora, outlier, dias, duração e link); **Ordenar** por YouTube (a ordem da
  página), Mais novos, Inscritos, Views, Views/h e Outlier; a grade com a capa, o canal, os inscritos, as views, a
  idade, a nota e o VPH; embaixo, quantos ainda estão sem inscritos (o Radar lendo os canais). A janela acompanha o que
  chega enquanto está aberta.
- **Botão Radar embaixo do vídeo** (na linha do Gostei/Compartilhar), com o menu: Este vídeo, Capa, Transcrição,
  Oportunidade por país, Levar ao Roteiro, Salvar ideia, Copiar o título e Print do cartão. Cada item abre a aba ou
  aperta o botão do painel ao lado (`data-acao`).
- **Tema escuro**: os botões do painel estavam escuros no fundo escuro; agora claros (`html[dark] .radar-botao`).

## Extensão 0.9.0: Língua Livre e o painel enxuto (2026-10-19)

- Pedido do usuário (print riscado): saíram do painel do vídeo a aba Tags, a linha de números do vídeo (views, por
  hora, publicado, duração), o cartão com os números do canal e o "Salvar canal" (continua no Alt+S e na página do
  canal). Na aba Números ficaram a nota e a curva.
- **🗺️ Língua Livre** (a nossa versão do "Método Malandro" do Dotti, com outro nome): uma aba no painel com o botão
  grande; traduz o título, procura no YouTube de cada país (sem cota, como a antiga "Oportunidade por país", que saiu)
  e mostra a barra de progresso em pedaços (um por língua, colorido no fim: verde ninguém fez, amarelo feito mas
  fraco, laranja já fizeram, vermelho já fizeram e foi bem), "Livre em …" com as línguas livres, quantas livres e a
  grade das línguas com a bandeira; clicar numa língua mostra os vídeos achados e a busca.
- **Formato dos botões** como no print: abas em faixa de largura igual, botão grande vermelho de largura toda e as
  ações em duas colunas (o "Levar ao Roteiro" na largura toda).

## Extensão: Capa principal e Método Fantasma (2026-10-19)

- **A Capa é a aba principal** (a aba Números saiu): a capa menor à esquerda e, à direita, os números em quadrados
  com ícone (como os do Dotti): o "quantos x" em vermelho, views (com a idade), por dia, normal do canal, inscritos e
  duração. A curva de views e o "Print do cartão" saíram (pedido do usuário).
- **Transcrição**: dois botões, "Copiar sem tempos" (o texto corrido) e "Copiar com tempos" (`[0:04] texto`, uma
  fala por linha).
- **Língua Livre virou Método Fantasma** (aba, botão e menu), com um fantasminha verde neon como marca. Nada de radar
  (seria cópia do Dotti): um anel verde enche a cada língua procurada, o fantasminha flutua no meio com um brilho que
  respira, e no fim ele dá um pulo e mostra quantas línguas estão livres; cada língua ganha a cor do que achou.
- **Fantasminha embaixo do vídeo**, ao lado do botão Radar, com aro verde: cresce com o mouse em cima; no clique sai
  um fantasminha por país, cada um levando a bandeira dele por cima do vídeo (caminhos diferentes, um depois do
  outro, crescendo e sumindo lá em cima; `voarFantasmas`), e abre ali mesmo a janelinha do Método Fantasma, presa ao
  botão e abrindo para cima (fica no `<body>`, posicionada por conta: dentro da fileira do YouTube saía no lugar errado) (a mesma busca do painel:
  fica guardada em `FANTASMA`, e as duas vistas se atualizam juntas). O selo conta as línguas procuradas (vermelho) e,
  no fim, as livres (verde). "Ver os vídeos de cada língua" abre a aba do painel, onde clicar numa língua mostra os
  vídeos achados.
- **Botões em 3D, sem emoji**: ícones de traço em SVG (`ICONES`/`icone()`/`botao()` em `content.js`). O Método
  Fantasma é o botão vermelho no topo; os outros ficam em preto.
- **Menu do botão Radar** com os mesmos ícones em quadradinhos, o Método Fantasma em vermelho e uma linha separando as
  abas das ações.
- **Radar e fantasminha à direita do título do vídeo** (o espaço vazio embaixo do player): `ytd-watch-metadata #title`
  vira flex e ganha a `.radar-titulo-botoes`; sem o título, os botões voltam para a fileira de botões.
- **Os fantasminhas crescem durante o voo todo** (de 0,6x a 3,6x) até sumirem lá em cima.
- **Filtros no alto do YouTube**, ao lado da busca (`ytd-masthead #center`), com o número de vídeos lidos: aparece em
  toda página com vídeos, a página inicial também, e abre a janela de filtros (atalhos, inscritos, views, publicado,
  ordenar, carregar mais e planilha). Sem a barra do YouTube, o botão fica solto no canto da tela como antes.
- **Depois (mesmo dia):** à direita do título ficava apagado; Radar e fantasminha foram para o **meio da fileira de
  baixo do título** (`#top-row`, logo depois do `#owner`, entre o canal e o curtir), **maiores** (`.radar-grandes`:
  Radar com 44px e aro verde, fantasminha com 46px). Sem essa fileira, voltam para o lado do título.
- **Janela de filtros no tamanho da do Dotti** (pedido do usuário: a nossa ficava pequena no meio): 88% da largura e
  90% da altura da tela (antes até 1400px), coluna da esquerda com 290px, 4 vídeos por linha, letras maiores (títulos
  16px), ícones de traço no lugar dos emojis (atalhos, filtros, ordenar, botões do topo), botões vermelhos em 3D e um
  interruptor no "Esconder Shorts".

## Extensão: página do canal com Analisar nicho, Canais Parecidos e Vídeos do Nicho (2026-10-19)

- **Selo de quantas vezes o normal** (filtros, Vídeos do Nicho, análise do canal): abaixo de 6x fica apagado, de 6x
  verde e de 15x vermelho (`corNota`).
- **A faixa solta embaixo do cabeçalho do canal saiu.** No lugar, junto do Inscrever-se, o botão vermelho **Analisar
  nicho** com o fantasminha verde: no clique os fantasminhas voam e abre a análise embaixo do cabeçalho (fase,
  monetização, Salvar canal, 4 quadrados com inscritos / normal por vídeo / vídeos / postando há, os gráficos e os
  vídeos que passaram do normal).
- **Abas do Radar junto das abas do YouTube**: **Canais Parecidos** (cartões com foto, normal por vídeo, inscritos e
  fase; `/api/ext/parecidos`) e **Vídeos do Nicho** (os vídeos longos que passaram de 2x o normal nos canais
  parecidos no último ano, do maior estouro para o menor; `/api/ext/nicho-videos/{canal}` → `garimpo.videos_do_nicho`,
  vídeos do banco, só os parecidos podem gastar cota e ficam guardados 7 dias). Abrir uma esconde o conteúdo do
  YouTube; clicar numa aba do YouTube volta.
- **Depois (mesmo dia), a pedido do usuário:** a análise ficou como a do Dotti, explicada. Uma caixa embaixo do
  cabeçalho do canal com o botão **Analisar nicho** dentro (à esquerda) e o resumo à direita ("Bom para tirar ideias
  de títulos · Maturidade · 309 dias"). Aberta: o veredito com a força (forte/morno/fraco agora, pelos últimos 10
  vídeos que passaram do normal) e o porquê; os dias postando com "melhor hora / ainda dá / tarde para entrar /
  saturado" e quantos dias faltam para a próxima fase; e o gráfico **Como um nicho nasce e morre** (Teste de
  mercado até 14 dias, Decolagem até 2 meses, Corrida por espaço até 4 meses, Maturidade até 14 meses, Saturação),
  com a foto do canal na curva. Os números, os gráficos e os vídeos que estouraram ficaram num "ver mais". As abas
  Canais Parecidos e Vídeos do Nicho entram logo depois da última aba do YouTube (Playlists), e a seção delas fica
  no lugar do conteúdo do YouTube (antes ia para o fim da fileira e ficava torta).
- **Dias postando errados em canal antigo (corrigido):** o Canada Insight foi criado em 2014 mas começou a postar há
  309 dias; o Radar mostrava 4633 dias (Saturação). Com mais vídeos do que a página mostra, o primeiro vídeo vinha da
  data de criação do canal. Agora a página do canal (`canal-dados`) anda a lista de envios uma vez
  (`youtube.primeiro_envio`, 1 unidade por 50 vídeos, até 2.000 vídeos), guarda a data como exata e refaz a fase e o
  selo; as releituras do canal (página e API) não apagam mais essa data.
- **Canais Parecidos em linhas:** cada canal parecido numa linha, o cartão dele à esquerda e os 5 vídeos longos mais
  novos ao lado, com capa, views, idade e o selo de quantas vezes o normal (`/api/ext/parecidos` agora traz
  `videos` de cada um, do banco: `garimpo.ultimos_videos`). A caixa do nicho entra logo acima das abas, na largura
  toda, e a seção das abas também ocupa a largura toda (antes encolhiam no meio da página). Se o servidor do Radar
  estiver aberto desde antes desta versão, as abas avisam para reiniciar o `LIGAR-RADAR.bat`.
- **Régua de 100 mil views** (como a do Dotti) na análise do nicho: o texto conta quantos vídeos do canal passaram de
  100.000 views, e a força (forte/morno/fraco agora) é quantos dos 10 mais novos passaram disso.

## Extensão: atalhos, concorrentes do nicho e o LIGAR-RADAR que fecha o antigo (2026-10-19)

- **Atalhos** (na página do YouTube): **Alt+S** salva o canal, **Alt+G** é o fantasminha (Método Fantasma no vídeo,
  Analisar nicho no canal), **Alt+R** leva o vídeo ao Roteiro, **Alt+V** abre os filtros dos vídeos da página. Alt+F e
  Alt+D ficam com o Chrome (menu e barra de endereço). As teclas aparecem no menu do Radar e no texto dos botões.
- **Concorrentes do nicho** na análise do nicho (`/api/ext/concorrentes/{canal}` → `garimpo.concorrentes`): os canais
  parecidos, quantos postaram no último mês, quantos estão crescendo, quantos canais novos (até 6 meses) já fazem 10
  mil por vídeo, os 6 maiores e a **nota do nicho de 0 a 10** (até 5 pela procura, até 3 pelos novos que deram certo,
  até 2 pelo espaço): 7+ fácil de entrar, 4+ dá para entrar com um bom título, abaixo nicho lotado. Procurar os
  parecidos gasta cota, então só com o botão "Medir os concorrentes" — se já foram procurados (7 dias), vem direto.
- **LIGAR-RADAR.bat** fecha o Radar que estiver ouvindo na porta 8400 antes de ligar o novo (um servidor antigo
  esquecido aberto deixava a página com o código velho).
- **$ da monetização ao lado do nome do canal** (como o do Dotti): verde = monetizado, cinza riscado = sem anúncio.
  Quando o Radar ainda não sabe, a extensão abre o vídeo mais novo do canal (sem cota) e olha a marca `yt_ad` que o
  próprio YouTube põe nos dados do player (1 = vídeo com anúncio); o resultado vai para o banco (`canais.anuncios`).

## Extensão 0.10.0: números do seu canal, do YouTube Studio (2026-10-19)

- **`studio.js`** roda dentro das páginas do YouTube Studio (world MAIN), com o login da própria pessoa, e pede ao
  Studio os números do canal do mesmo jeito que o Studio pede (`yta_web/get_cards`; formato em
  `docs/studio-tempo-real.md`): as views hora a hora das últimas 48 h (a cada minuto) e, a cada 15 min, os 365 dias de
  views, tempo assistido e ganhos estimados (em dólar). O **`studio-ponte.js`** guarda no `chrome.storage.local`
  (`numerosCanal`); nada vai para o servidor do Radar.
- **No alto do youtube.com**, ao lado do Criar: o botão com **1h · 48h · 7d · 30d** (1h = a última hora completa; 7d
  e 30d = a soma dos últimos dias, como o Dotti). Ele abre os cartões com gráfico: views da última hora, 48 horas,
  7 dias, 30 dias, tempo assistido e ganhos estimados de 12 meses, "Atualizado há X minutos" e "Abrir o Analytics".
  Sem números ainda, o cartão pede para abrir o Studio uma vez.
- **"Hoje" no cartão Em tempo real do Studio**: as views desde a meia-noite, ao lado das 48 horas.
- Os números só se atualizam com uma aba do Studio aberta (é o jeito seguro: o pedido sai da própria página do Studio).
- Conferido no Chrome do usuário (Canada Insight): 1h 2.564, 48h 75.893, 7d 324.727, 30d 459.268, 183 mil h, iguais
  aos do Dotti. Ganhos e tempo assistido usam o total que o Studio dá (somar os dias dava 1 centavo a mais). O "Hoje"
  fica numa linha própria embaixo do "Últimas 48 horas" (no canto de cima ficava em cima do "Hoje" do Dotti). O
  Chrome precisa liberar o acesso da extensão ao studio.youtube.com (site novo na 0.10.0).

## Extensão 0.12.0: ajuda para publicar no YouTube Studio (2026-10-20)

Pedido do usuário: "adicionar a extensão na hora de postar o vídeo com anúncios e tudo". Combinado: **só um painel de
ajuda** (a extensão não clica, não preenche e não publica nada), com título, descrição, tags, monetização e anúncios,
questionário de anunciantes, público e visibilidade, achando o vídeo **pelo nome do arquivo**.

- **`extensao/publicar.js`** (no studio.youtube.com, num shadow root para o CSS do Studio não entrar): na tela de
  upload (`?d=ud`, `ytcp-uploads-dialog`) ou de edição do vídeo aparece o botão **Radar · ajuda para publicar**. Ao
  escolher ou arrastar o arquivo, o painel abre sozinho. Ele mostra o título (com a contagem de 100), os títulos do
  teste A/B, a descrição (5.000), as hashtags que faltam na descrição, as tags separadas por vírgula até caber nos 500
  caracteres, o comentário fixado e **Baixar a legenda (.srt)**. Embaixo vem a lista do que marcar em cada etapa
  (Detalhes, Monetização e anúncios, Adequação para anunciantes, Elementos, Verificações e Visibilidade), com caixinhas
  de feito. O mid-roll usa a duração do vídeo (só a partir de 8 min) e sugere as viradas de capítulo. O "Conteúdo
  alterado ou sintético" segue o `sintetico` da fábrica. O questionário diz para marcar "Nenhuma das opções acima" só
  se for verdade.
- **O vídeo pelo nome do arquivo** (`radar/publicar.py`): compara o nome sem acento nem extensão com o .mp4 da entrega
  (`entrega_pc.json`, que usa o título), o título do kit, o `titulo_entrega` e o nome da pasta. Primeiro procura um
  nome igual e depois um que contenha o outro. Com `final.mp4` ou um nome que não diz qual é o vídeo, ele não chuta:
  mostra a lista dos vídeos da fábrica com kit (ou deixa digitar o nome).
- **Rotas**: `GET /api/ext/publicar?arquivo=` (kit e lista), `GET /api/ext/publicar/{nome}` e
  `GET /api/ext/publicar/{nome}/legenda`. Leem o `publicacao.json` da pasta do projeto, então funcionam com a fábrica
  desligada.
- Para usar: em `chrome://extensions`, clique no ↻ do Radar de Canais e recarregue a aba do Studio (F5).

## Nova produção em passos, também no alto do YouTube (2026-10-19)

- **No site** (`novaProducao` em `radar/web/app.js`): o passo **1 · O vídeo** tem só o título, o vídeo de
  referência, o **agente do roteiro** (o do canal, com o botão **Editar**) e o "Parar para eu revisar o roteiro".
  Quem não aperta Editar já cria com o Claude escrevendo no agente do canal. O passo **2 · Editar o roteiro** tem o
  resto (canal, agente, idioma, roteiro colado ou do Claude, tamanho, nicho e observação). O último canal usado fica
  lembrado; a escolha de canal só aparece no passo 1 quando ainda não tem canal.
- **Na extensão**: o botão vermelho **Nova produção** no alto do YouTube, entre a busca e os números do canal, abre a
  mesma janela em dois passos (as mesmas rotas: `/api/meus-canais`, `/api/projetos`, `/api/producao/{canal}`,
  `/api/roteiros/ritmo`, `/api/fila/estimativa`, `/api/titulo-do-video` e `POST /api/fila`). Num vídeo aberto, o link
  dele já vem como referência. No fim, "Ver no Acompanhar" abre o site.
- **LIGAR-RADAR.bat abre o navegador só quando o Radar responde** (2026-10-19): depois que ele passou a fechar o Radar
  antigo, o navegador abria antes do servidor novo subir (uns 5 s) e mostrava "não é possível acessar este site",
  parecendo que o Radar não ligava. Agora uma espera escondida tenta o endereço a cada segundo (até 90 s) e abre o
  navegador quando ele responde.

## Extensão 0.13.0: a publicação se preenche sozinha, e o × para tirar um canal (2026-10-22)

Pedido do usuário: "adicionar estas opções das imagens na extensão, quanto mais agilizar o trabalho melhor", com a
descrição indo sozinha ao escolher o vídeo e a barra de ajuda saindo. Combinado: **a extensão clica e avança** — só o
botão Publicar continua sendo da pessoa.

- **`extensao/publicar.js` virou automação** (a lista de "o que marcar em cada etapa" saiu): ao escolher o vídeo da
  fábrica (ou ao arrastar o arquivo, que acha o vídeo pelo nome), a extensão já **escreve o título, a descrição e as
  tags** na tela de Detalhes e marca "Não, não é conteúdo para crianças". Escreve do jeito que a pessoa escreveria
  (`focus` + `insertText`), que é o que o Polymer do Studio entende; os campos são `#title-textarea #textbox`,
  `#description-textarea #textbox` e `#tags-container input` (abrindo o "Mostrar mais" antes).
- **Um botão vermelho por etapa**, no canto de baixo, perto do Avançar do Studio: **Preencher e pular** (Detalhes),
  **Anúncios ligados e pular** (Monetização: liga a monetização, marca todos os tipos de anúncio e avança),
  **Colocar N anúncios** (espaços intermediários), **Responder "nada disso" e pular** (marca "Nenhuma das opções",
  envia a classificação e avança) e **Pular esta etapa** (Elementos e Verificações). Na Visibilidade não tem botão.
- **Anúncios no meio do vídeo**: no painel dá para escolher *um a cada X minutos* (padrão 1) ou *uma quantidade bem
  dividida*. Ele anda com o player (`video.currentTime`) e clica no "espaço de anúncio" em cada tempo, mostrando o
  andamento. Muito perto um do outro o YouTube pode não usar — 1 a 3 minutos costuma passar.
- **As etapas são achadas pelo texto da tela** (pt-BR e inglês), não por posição: quando um botão não é achado, o
  painel diz o que fazer à mão em vez de clicar errado.
- **× para tirar um canal** (`ligarTirarCanal` em `radar/web/app.js`): sempre à vista no canto de cada cartão de
  **Seus canais** (Início) e de cada quadradinho da tela **Canais**, com janela de confirmação com o nome do canal.
  Usa o `DELETE /api/perfil/canais/{id}` que já existia: sai do Radar com a configuração de produção, o canal no
  YouTube não é tocado e dá para adicionar de novo depois.
- Para usar: em `chrome://extensions`, clique no ↻ do Radar de Canais e recarregue a aba do Studio (F5).

## Extensão 0.14.0: descrição no modelo do canal, horário e tela final (2026-10-22)

Pedidos do usuário no mesmo dia, olhando a publicação de verdade: "não quero aquele tipo de descrição... mais
padronizado, só mudando para o tema do vídeo, sem spoilers, apenas uma sinopse"; o horário de postar com fuso; a tela
final padrão; e "o painel você pode remover".

- **Modelo da descrição, por canal** (escolha do usuário: fica no Radar, não na fábrica, para valer também nos vídeos
  já prontos). Na página do canal, o bloco **🧾 Modelo da descrição**: um texto só, com `{titulo}`, `{sinopse}`,
  `{canal}`, `{hashtags}` (e `{tags}` e `{capitulos}` para quem quiser). **Sem a lista de capítulos**, que era o que
  entregava o vídeo inteiro na descrição da fábrica. O botão **Usar o modelo sugerido** traz um pronto na língua do
  canal (título, sinopse, "sobre o canal", aviso legal, hashtags). Guardado em `canais_config.modelo_descricao`
  (`producao.PADRAO`); vazio = a descrição da fábrica, como era.
- **Quem é o canal do vídeo** (`publicar.perfil_do_projeto` + `producao.canal_do_perfil`): o `projeto.json` da fábrica
  guarda o caminho do perfil (`perfis/canal-uk-market.yaml`); o Radar acha o canal que usa esse perfil (pelo que está
  salvo ou pelo nome) e pega o modelo dele. `GET /api/ext/publicar` e `/api/ext/publicar/{nome}` já devolvem a
  descrição montada, mais `canal` e `modelo` (se o canal tem modelo salvo).
- **A sinopse** é o `resumo` que a fábrica escreve (2 ou 3 frases do que o vídeo mostra), agora exposto no kit.
- **Horário de postar** (na etapa Visibilidade): escolha o fuso do público (EUA Leste, Brasil, Reino Unido…) e a hora
  de lá; a extensão mostra "lá agora" e a hora que isso vira no Studio (a do seu computador), e o botão **Colocar o
  horário** marca Programar e preenche a data e a hora. A conta usa `Intl` com o fuso IANA, então pega horário de
  verão sozinho (17:00 em Nova York = 18:00 em Brasília no teste).
- **Tela final do último e pular** (etapa Elementos): clica em "Importar do vídeo", escolhe o vídeo mais recente e
  salva. Se a janela não abrir do jeito esperado, ele diz para escolher à mão em vez de clicar errado.
- **O painel saiu**: ficou só o botão vermelho da etapa, com uma **setinha** ao lado que abre o vídeo escolhido, os
  anúncios (um a cada X minutos ou uma quantidade), a legenda e o comentário fixado.
- Para usar: em `chrome://extensions`, clique no ↻ do Radar de Canais e recarregue a aba do Studio (F5). O Radar
  precisa ser religado (LIGAR-RADAR.bat) para as rotas novas valerem.

## O tempo do vídeo passa a cair dentro de 1 min 30 s (2026-10-22)

Pedido do usuário: "o Radar sempre gera roteiro, mas dificilmente acerta o tempo do vídeo pedido; sempre que gerar um
roteiro ele tem de ver o resultado que deu o vídeo, para saber se está acertando ou errando. A margem de erro tem que
ser no máximo de um minuto e meio para cima ou para baixo, e ele vai melhorando a cada pedido."

O ajuste já existia (`radar/tempo.py`, 2026-10-18), mas errava feio. Medindo os 10 vídeos entregues: pediu 15 e saiu
23,2; pediu 16 e saiu 19,5; pediu 15 e saiu 11,3. Dois motivos, os dois corrigidos:

- **A medida dependia da fábrica ligada.** `_duracoes()` só sabia o tempo pela API da fábrica; com ela desligada o
  Radar não media nada, caía nas 150 palavras por minuto do padrão e estourava nas vozes lentas (as de inglês falam
  umas 135). Agora a duração vem **do disco** (`alinhamento.json` da pasta do projeto, mais a abertura do
  `render/linha.json`, que é vídeo sem narração), com a API só de reserva. O resultado de cada vídeo também fica
  gravado no `roteiro.json` (`medido`), então o histórico sobrevive à pasta do projeto sair do computador.
- **A conta aprendia a coisa errada.** O ppm era *palavras escritas ÷ minutos*, e o Claude escreve mais do que se
  pede (de 0 a 27% a mais nos vídeos medidos): o excesso se repetia em todo vídeo. Agora quem dimensiona o pedido é o
  **`ppm_alvo` = palavras PEDIDAS ÷ minutos entregues**, que engloba a voz e a mania do Claude de esticar. O `ppm`
  continua sendo mostrado como o ritmo real da voz. Para o João o Lobo: ppm 215, ppm_alvo 205; para o UK MARKET,
  ppm 136 e ppm_alvo 105.
- **A escrita parava cedo demais**: o laço de continuação aceitava faltar 15% (2 min num vídeo de 15). Agora o que
  pode faltar é medido em minutos de narração, dentro da margem (`tempo.MARGEM_MIN`).
- **O acerto aparece na tela** (`ritmo.acerto`): na hora de escrever o roteiro, "🎯 4 de 5 dos últimos vídeos desta
  voz ficaram dentro de 1,5 min do tempo pedido · erro médio +1,2 min · pior: pediu 15 e saiu 18,8 min". No "por
  quê?" vem a lista vídeo a vídeo, em verde quem ficou dentro e em vermelho quem passou.
- `tests/test_tempo.py`: mede do disco somando a abertura, conta o que ficou fora da margem, encolhe o próximo pedido
  e guarda o resultado no roteiro.

## Extensão 0.15.0: abinha, ChatGPT e o agente no painel do YouTube (2026-10-22)

Pedido do usuário: "o Claude que abre na lateral com dois cliques tem que ter uma abinha para mostrar ele, e quero o
ChatGPT também; o Claude ali eu queria que desse para ter acesso a projeto e tudo".

- **A abinha** (`.radar-claude-abinha`): uma lingueta na beirada direita do YouTube, sempre à vista, que abre o
  painel. Os dois cliques com o botão direito e o Alt+C continuam funcionando; ela some enquanto o painel está
  aberto.
- **Duas abas no painel, Claude e ChatGPT.** No Claude continua o chat do Radar (`/api/assistente`, pela assinatura),
  que sabe qual página está aberta.
- **O agente (o "projeto") no Claude**: um seletor no alto do painel com os seus agentes de roteiro — que é onde
  moram as instruções dos projetos do claude.ai. O escolhido vai no `projeto_id` do `/api/assistente` e as
  instruções entram no contexto (`producao.assistente`), valendo por cima das regras gerais. A escolha fica
  guardada.
- **O claude.ai e o ChatGPT de verdade abrem numa janela ao lado.** Os dois mandam `X-Frame-Options: SAMEORIGIN`
  (conferido), então não dá para pôr nenhum dos dois dentro do YouTube. A extensão abre a janela encostada na
  direita e **cola** a pergunta com o título e o endereço da página; quem aperta enviar é a pessoa, como já era no
  envio para o ChatGPT e o Gemini. O texto vai pelo `chrome.storage.local` (`radarColar`, vale 2 minutos) e quem
  cola é o `colar.js`, que agora roda também no `claude.ai` (com o seletor da caixa do ProseMirror) e está no
  `host_permissions`.
- Para usar: em `chrome://extensions`, clique no ↻ do Radar de Canais e recarregue a aba do YouTube (F5).

## Extensão 0.24.0: o horário de postar sai de cena (2026-10-24)

Pedido do usuário: "remova da extensão esse colocar o horário" e, logo depois, tirar também o ajuste no Radar. Quem
agenda o vídeo na etapa **Visibilidade** volta a ser a pessoa, à mão, no próprio Studio.

- **Na extensão** (`extensao/publicar.js`): saíram o botão **Colocar o horário**, a conta do fuso (`deslocamento`,
  `quandoPostar`, `colocarHorario`) e os campos `fuso`/`hora_postar` que vinham no kit. A etapa Visibilidade deixou de
  ser reconhecida: nessa tela a barra do Radar some em vez de ficar ancorada no rodapé sem botão nenhum.
- **No Radar**: a linha **Fuso do público do canal** + **Hora de postar, lá** saiu do bloco 📤 Publicação na página do
  canal (`radar/web/app.js`), junto com o `producao.FUSOS`, os dois campos do `producao.PADRAO` e a validação deles, e
  os dois campos do `padrao` do kit (`GET /api/ext/publicar`). O bloco ficou só com o anúncio a cada X minutos e a
  tela final.
- Para usar: em `chrome://extensions`, clique no ↻ do Radar de Canais e recarregue a aba do Studio (F5). O Radar
  precisa ser religado (LIGAR-RADAR.bat).

## MCP e a lista de funções numa fonte só (2026-10-24, madrugada)

Pedido do usuário: clonar o Dotti Finder "com tudo, tudo igual até a extensão", trabalhando a noite toda. O Radar
já nasceu assim, no modelo deles e feito do zero, então a noite foi gasta em cima do que **faltava** — não num
produto novo e não copiando nada de lá. O levantamento novo está no `docs/analise-dottifinder.md`, seções 8 e 9: a
extensão deles por dentro (pelo pacote público da loja, lido com o REA), os preços, e o plano de 22/10 conferido
item por item — 20 dos 28 itens já estavam feitos.

### O MCP: o Radar dentro do Claude e do ChatGPT (`radar/mcp.py`)

A única porta que o Dotti tem e o Radar não tinha. Eles vendem por cota de pergunta (50 por semana no Grátis, 150
por dia no Lite, 300 por dia no Pro) e a extensão deles liga o conector sozinha no `claude.ai`. Aqui ficou um
servidor **stdio** que fala com o Radar deste computador pela própria API HTTP — de propósito: as regras de filtro,
de plano e de cota moram no servidor, e o MCP não pode ter uma segunda versão delas para desencontrar.

    claude mcp add radar -- uv run python -m radar mcp

**Oito ferramentas, todas de leitura.** Nada aqui mede canal, garimpa ou grava: o que gasta a cota do YouTube
continua sendo escolha da pessoa, no painel.

| Ferramenta | O que responde | Rota |
|---|---|---|
| `radar_resumo` | as contagens da base: canais analisados, no Radar, vídeos lidos, nichos, novos da semana | `/api/resumo` |
| `radar_visoes` | as perguntas prontas, com rótulo e dica (para saber que recorte pedir) | `/api/visoes` |
| `radar_canais` | a lista de canais, com `visao`, nicho, país, média mínima, inscritos, meses e ordem | `/api/radar` |
| `radar_salvos` | a base da pessoa | `/api/salvos` |
| `radar_acharam` | a colheita: os parecidos que cada canal salvo trouxe, e por causa de quem | `/api/achados` |
| `radar_canal` | um canal por dentro: normal por vídeo, fase, raridade, últimos vídeos com nota, histórico, parecidos | `/api/perfil/canal/{id}` |
| `radar_outliers` | os vídeos que estouraram | `/api/outliers` |
| `radar_titulos` | os títulos que mais trazem views | `/api/titulos` |

Três cuidados que mudaram o resultado, os três achados rodando de verdade contra o Radar ligado:

- **A resposta tem de caber no contexto de quem perguntou.** Cada item leva só os campos de decisão e no máximo 25
  itens (`LIMITE`). O `videos` da linha do canal ficou **de fora**: ele vem com a lista inteira de vídeos e 25
  canais viravam 22 KB de resposta — agora são 8,8 KB, e quem quer os vídeos de um canal chama o `radar_canal`.
- **No Windows a saída saía na página de código do DOS** e "história" chegava quebrado no Claude. O laço do stdio
  reajusta a entrada e a saída para UTF-8.
- **A base da pessoa usa `/api/salvos` e `/api/achados`**, não `/api/radar?salvos=1`: a rota do Radar exige o
  recurso `radar` (Pro) e daria 402 para quem é Lite, justamente no que é dele.

Erro em português, com a saída: Radar desligado diz "ligue ele (dois cliques em LIGAR-RADAR.bat)"; 402 repete o
plano que o servidor pediu; 401 manda entrar na conta. `RADAR_MCP_BASE` troca o endereço e `RADAR_MCP_COOKIE` leva
a sessão quando o Radar está aberto para a rede (`--publico`).

`tests/test_mcp.py` (19): o catálogo no formato que o Claude lê, nome que não repete, **nenhuma ferramenta que
escreve**, o aperto de mão, aviso sem resposta, método que não existe, ferramenta que não existe, o que falta dito
antes de sair pedindo, booleano que vira 1, o id que não vaza para a query, o cookie, a resposta enxuta, a lista de
vídeos do canal que não vem na lista de canais, os três erros e o laço do stdio ignorando lixo.

### A lista de funções da extensão numa fonte só (`radar/funcoes.py`)

Item 14 do plano. A tela Extensão era texto escrito à mão, a tela Planos listava recursos e a extensão sabia das
suas funções por conta própria: três listas para desencontrar. Agora são **32 funções** com `chave`, `nome`,
`desc`, `onde` aparece e o `recurso` que a abre — e só isso: quem decide o preço continua sendo o `config.PLANOS`.

- `GET /api/ext/funcoes` devolve a lista com o plano de cada função e, para quem pediu, se está liberada.
- A tela **Extensão** monta sozinha: "32 funções dentro do YouTube, 26 delas no plano Grátis", os passos de
  instalar e os cartões agrupados por onde a função aparece (em cima do vídeo, no painel, na página do canal, na
  busca, no Studio). A função que o plano da pessoa não abre fica apagada, com a etiqueta do plano.
- A tela **Planos** ganhou "N das 32 funções da extensão" por plano, da mesma fonte.
- `tests/test_funcoes.py` (13): chave que não repete, todo recurso em algum plano, o plano de cada função é o mais
  barato que abre o recurso (a mesma conta do 402), cada plano abre o que deve, plano escrito errado vale como
  Grátis, planos cumulativos, a rota pede conta e responde com o plano de quem pediu.

Para comparar: o Dotti anuncia 29 funções, 19 grátis.

**Falta** (do plano de 22/10): o item 5 (grupo vazio sumir sozinho), o 9 (trilho em vez de campo numérico, só um
feito) e conferir o 13 e os 21–24. E, se o MCP for virar produto, a cota de perguntas por plano — hoje ele é
local e livre.

## O pagode no Faceless Outliers, e o Radar só de canal dark (2026-10-25)

"os dotti finder pesquisa canais melhores que o nosso, me explica pq, queremos canal dark que explodiu, mas o nosso
esta trazendo pagode e musica".

**Estava certo, e a causa não era a busca.** Os termos do garimpo são todos dark e em inglês; nenhum de música. O
pagode entrava por outra porta, na **tela**, não na procura.

A extensão guarda todo canal que a pessoa vê enquanto navega no YouTube — é o "ler os vídeos sem gastar cota". Esses
canais ficam no banco com `no_radar=0`: nunca passaram pelo garimpo, então estão **sem nicho, sem rosto sabido e sem
medida de verdade**. Eram 13.658 canais no banco para 420 no Radar.

A lista de vídeos (`/api/outliers`) lia a tabela `outliers` juntando com `canais` **sem conferir o `no_radar`**. Daí:

- o corte dos nichos que pagam pouco (`mercado.irrelevante`) não pegava nada, porque o nicho estava vazio;
- o corte do rosto não pegava nada, porque `sem_rosto` estava nulo;
- e a nota, que é views ÷ o normal do canal, ficava **gigante**: o "normal" de quem foi visto de passagem sai de
  um ou dois vídeos. "Guns N' Roses — November Rain" marcava **50.025x**. Como a tela ordena por nota, o lixo
  encabeçava a lista.

Na base do usuário: dos 4.400 vídeos que a tela trazia, **2.736 (62%) eram de canal fora do Radar**, e os **25
primeiros eram todos** — Guns N' Roses, pagodepontocom, Péricles, Grupo Di Propósito, Música Multishow, MTV.

O mais incômodo: **o `c.no_radar=1` já existia na tela de Títulos**, com um comentário que diz "e o topo virava clipe
de pagode". O conserto foi feito lá e nunca levado para a lista de vídeos, que é a tela que a pessoa usa.

- **A lista de vídeos passa a cortar por `c.no_radar=1`**, como as outras. 62% da lista era lixo.
- **Canal com rosto não entra mais no Radar** (`garimpo._completar`). O rosto só é sabido depois de medir, então o
  canal é medido e só então fica de fora — a medida não se perde. `sem_rosto` nulo (o Groq não respondeu) continua
  entrando: não sabido não é o mesmo que tem rosto. Na base de hoje, 74 dos 420 canais do Radar têm rosto.

Oito testes no `tests/test_so_dark.py`, com o caso real: um "pagodepontocom" com normal de 1.200 e um vídeo de 21
milhões de views, que sem o corte encabeça a tela e com ele não aparece.

## Tudo no meio da tela, cinco capas por canal e Títulos fora do menu (2026-10-25)

- **A tela estava colada na esquerda.** O `main` tinha `max-width: 1280px` e nenhuma margem automática, e um
  `main { max-width: 1680px; }` escrito para o Roteiro valia para **todas** as telas — então em monitor largo o
  Niche Finder nunca chegava ao limite e não havia folga para centralizar. A largura de 1680 passa a valer só para
  o Roteiro (`body[data-tela="trabalho"]`, com o `rota()` marcando a tela no `body`), e o resto centraliza com
  `margin-inline: auto`. Medido a 1600 px: 1280 de conteúdo, com folga igual dos dois lados.
- **Cinco capas por canal** em vez de três (`servidor.VIDEOS_DO_CARTAO`): com três não dá para ver o padrão do
  canal, que é para o que se olha. A grade cai para 4 abaixo de 1500 px e para 3 abaixo de 1180 px.
- **Títulos saiu do menu**, a pedido. A tela continua de pé em `#/titulos` e o gerador de títulos segue no Roteiro,
  que é onde ele é usado.

## Niche Finder numa caixa só, o painel de cota fora e as tags que faltavam (2026-10-25)

Quatro pedidos do usuário, com as telas na mão.

- **O painel de créditos da direita saiu.** Ele repetia o quadro que já existe na barra lateral e comia 290 px de
  largura em toda tela do Niche Finder (`.com-cota` era uma grade de `1fr 290px`). Saíram o `painelCota`, o
  `GASTOS`, a `atualizarCota` e o CSS deles. Quanto custa cada coisa continua na **Administração**, em
  "Onde foi hoje", que é onde ficam os números de verdade — o painel só repetia a tabela de preços.
- **A busca virou uma caixa.** As visões, o campo de procurar, os filtros, os trilhos e as marcas moravam soltos
  na página, cada tela espaçando de um jeito. Agora vão todos dentro de `.busca-caixa`: fundo de painel, borda,
  cantos arredondados e 18–22 px de ar nas laterais. Dentro dela o campo e os selects ficam um tom acima
  (`--painel2`), senão sumiriam no fundo da própria caixa. Está nas quatro telas do Niche Finder que têm filtro —
  **Canais** (visões + procura + filtros + trilhos), **Faceless Outliers** (procura + filtros + trilho + marcas),
  **Grupos de canais** e **Títulos**. A aba **Acharam para você** não tem filtro nenhum hoje, então não ganhou
  caixa: ela é só a lista do que chegou.
- **No Perfil, "Roteiro" virou "Produzir"**, que é o nome do botão que a tela já usa ("▶ Produzir"). O botão
  **Levar ao Roteiro** dos vídeos continua com esse nome: ele fala do que você vai fazer lá, não da aba.
- **Extensão 0.25.0 — as tags.** As tags moram atrás do "Mostrar mais" dos Detalhes, e eram o campo que mais
  falhava: o painel clicava uma vez, esperava 700 ms fixos e **desistia calado** se o Studio ainda estivesse
  desenhando a seção. Agora `abrirAsTags()` insiste até o campo aparecer (de 150 em 150 ms, até 5 s) e o rótulo
  tem as quatro formas que a tela usa conforme a conta: Mostrar mais, Mais opções, Show more, More options.
  Quando ainda assim não dá, ele **diz**: "não abriu o Mostrar mais a tempo" ou "a fábrica não mandou nenhuma
  para este vídeo" — antes, tags sem campo e vídeo sem tags davam no mesmo silêncio.

**E nada disso apareceu na tela.** As quatro mudanças estavam no disco e o servidor as mandava, mas o
`index.html` pede `/web/app.js?v=104` — um número escrito à mão. O `app.js` mudou três vezes sem que o 104
subisse, então o navegador continuou usando o arquivo que já tinha guardado: a tela de ontem, sem erro nenhum
na cara de quem usa. O `/web` também não manda `Cache-Control`, então o navegador decide sozinho quanto tempo
guardar e nem pergunta ao Radar. Agora a rota `/` monta o index na hora e põe no `?v=` o minuto em que o
`app.js` ou o `estilo.css` mudou — mexer no painel já é subir a versão, não existe mais número para esquecer —
e o index vai com `no-store`, senão ele mesmo ficaria guardado e a versão nova não chegaria a ninguém. Dois
testes no `test_abertura.py` cobram as duas coisas.
- **O recado virou lista.** Em vez de uma frase corrida, o painel mostra o que marcou e o que não marcou:
  `✓ título · ✓ descrição · ✓ não é para crianças · ✓ 15 tags · ✓ uso de IA: sim`, e o que está com ✗ fica com
  você. É o "assinalar" do pedido: a pessoa confere a tela batendo o olho.

Conferido com o Radar ligado, no navegador: as quatro telas montam a `.busca-caixa` com os filhos certos, nenhuma
tem mais o `#painel-cota`, e o menu do Perfil mostra Produzir. Para a extensão: `chrome://extensions` → ↻ no Radar
de Canais → F5 na aba do Studio.
