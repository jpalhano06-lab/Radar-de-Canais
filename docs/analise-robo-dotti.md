# Robô Dotti por dentro — o que dá para levar para o Radar (levantado em 2026-10-25, de madrugada)

Pedido do usuário, indo dormir: "entre no robô, olhe tudo, pode mexer em tudo, gere um roteiro para ver como
funciona, porém na última etapa não peça para gerar o vídeo; veja tudo para adicionarmos". A primeira leitura do robô
foi em 2026-10-18 (`docs/superpowers/specs/2026-10-18-robo-no-radar-design.md`); esta vê o que mudou e, pela
primeira vez, **o roteiro sendo escrito por dentro**.

Como foi feito, para conferir:

- **O programa instalado** em `C:\Users\Palhano\AppData\Local\DottiStudio\robo` (agente-0.2.111, de 23/10; a 0.2.114
  já está disponível e **não** foi instalada). O núcleo é um módulo compilado (`agente.cp312-win_amd64.pyd`); o
  `dotti_robo.py` só o chama. Lidos: o `iniciar.cmd`, o `robo.log` e os arquivos de um vídeo pronto
  (`producoes/job_9f3e6fd6aa6f428a`, "These 10 Essential Foods…", 39:54).
- **O painel Dotti Studio** (`dottistudios.com`), no Chrome do usuário, já logado. Só leitura, menos um pedido: um
  roteiro de teste com **"Parar para eu revisar o roteiro" ligado**, que segura o cartão antes da miniatura e do
  vídeo. Na tela Produzir do Robô fui até o passo 4 e **não** apertei "Enviar para o Robô". As telas de Integrações e
  da API do Robô mostram chaves e não foram lidas.
- A regra do Radar continua: nada de código, texto, nome ou visual de lá. Isto é para entender o que o produto faz.

---

## 1. O que ele é

Três peças, como o Radar:

| Peça | O que faz |
| --- | --- |
| **Site Dotti Studio** | Cinco áreas na barra da esquerda: **Canal**, **Robô**, **Aprender**, **Finder** (o Dotti Finder) e **Produção** (o quadro de roteiros), mais a Comunidade (chat). O site guarda os pedidos, as chaves e os presets; não faz vídeo. |
| **Robô** (este PC) | Liga com o Windows (`Startup\Robo Dotti Studio.cmd`), relança sozinho se cair (até 6 vezes por hora) e fica pedindo trabalho ao site. Faz **tudo** aqui: escreve o roteiro com o **Claude Code desta máquina** (a assinatura, não a API), faz a miniatura com o GPT (Codex ou a chave da OpenAI) e monta o vídeo com o ffmpeg que vem no pacote. Impede o PC de suspender enquanto produz. |
| **Quadro** (no site) | O kanban que liga as duas: **Entrada → Roteiro → Miniatura → Robô → Pronto**. |

Os números da conta: 4 canais (Australia, Canada, Philippines e UK Insight), 131 vídeos entregues, **US$ 237,54 de
APIs em outubro** para 3.155 minutos entregues (**US$ 0,075 por minuto**), um vídeo de 30 a 40 min por US$ 2,30 a 2,96
e de 55 min a 1h17 de trabalho da máquina.

## 2. O Quadro e a Nova produção

- **Nova produção**: título, vídeo de referência (obrigatório só no estilo "modelar"), canal em chips, **estilo do
  roteiro**, idioma, **tamanho em caracteres com atalhos de 8 a 30 min** (8 min = 6.840 caracteres ≈ 1.200 palavras),
  nicho, observação e **"Parar para eu revisar o roteiro"**. À direita, a prévia do cartão. "Salvar na Entrada" ou
  "Criar e começar". Também "Colar vários títulos" de uma vez.
- O Radar **já tem** essa janela, a Entrada, a fila e a parada para revisar (feitos em 18/10, README "O que o Robô do
  Dotti tinha e o Radar ganhou"). O que não tem está nas seções 3 e 6.
- **O cartão que bate no limite do Claude** fica em Roteiro com "Limite do Claude" e "Tentar de novo"; a máquina só
  volta a pedir roteiro 30 min depois (visto no log e no cartão "Millions of Australians Are Now Boycotting KFC").
- Os passos opcionais (pesquisa, juiz, prompt da miniatura) que falham **não derrubam** o roteiro: o log diz "o passo
  opcional juiz falhou; sigo sem ele".

## 3. O roteiro — o programa de passos

**O teste**: "10 Things British Pensioners Should Stop Buying This Winter", UK INSIGHT, Lista / Top N, inglês,
8 min, "Parar para eu revisar". Criado às 02:33, pronto às 02:56. Saiu com **1.242 palavras** (alvo 1.200, aceito de
1.080 a 1.320), ~8,3 min, 6.886 caracteres, escrito pelo **Opus**. O cartão está em Roteiro, **"Sua vez"**, **sem
aprovação**: aprovar mandaria fazer a miniatura e depois o vídeo. Ele pode ser apagado no próprio cartão ("Excluir
produção") ou aprovado de manhã, se o usuário quiser o vídeo.

**Os estilos** ("Estilos de roteiro") são programas que o site monta e o robô segue:

- **Método Dotti** (2): "modelar vídeo de referência" (9 passos, ~11 min; exige referência; de 1.000 a 80.000
  caracteres) e "documental (sem referência)" (7 passos).
- **Dotti Roteiros** (9, 8 passos, ~22 min, referência opcional, de 1.000 a 30.000 caracteres): Documentário, Lista /
  Top N, Exposé / Escândalo, True crime / Mistério, Documentário de celebridade, Jornada do herói, Vídeo-ensaio, Como
  funciona / Por quê, Comparação X vs Y. Cada um com "Ideal para" e uma linha do molde.

**Os passos**, vistos na linha do tempo do cartão e nos pedidos que o robô entrega ao Claude Code (um "contrato" por
passo, numa pasta temporária `dotti-quadro-*`):

| Passo | O que o pedido manda | Tempo no teste |
| --- | --- | --- |
| 1. Pesquisa | Buscar e **abrir** as fontes; o que não foi aberto e conferido não entra. Devolve um brief em campos fixos (tema, ângulo, banco de provas com a fonte de cada item, direção do gancho, dica de estrutura), o status das fontes e as **lacunas** | 4 min |
| 2. Público + esboço | O espectador, o que é prova e o que é suposição, o ângulo, a grande recompensa e as pequenas, as objeções, e o **esboço no molde do formato**: cada parte com o que entrega, a prova que a sustenta e o **tamanho em palavras** (a soma bate com o alvo), os re-ganchos e o lugar do pedido de inscrição no meio (55% a 65%). Também escolhe as variações para os vídeos do canal não saírem iguais | 1 min |
| 3. Escrita | A narração limpa entre marcas, e **fora dela** as notas: o brief de produção, a contagem de palavras com o método, as lacunas e as suposições | 3 min |
| 4. Revisão "A–F" | Uma leitura inteira, a checagem em seis grupos com evidência, **uma** rodada de conserto, recontar as palavras; o que sobrar vira "precisa consertar / segurar" no veredito, sem laço | 15 min, **caiu no limite do Claude** |
| 5. Prompt da miniatura | O pedido de imagem para o GPT | **caiu no limite do Claude** |

Regras que valem para todos os passos: o Claude roda **sem ninguém do outro lado** (onde o método mandaria perguntar,
ele registra a lacuna, escolhe o mais conservador e segue); **não inventa** fato, número, citação nem experiência; o
idioma é o do pedido (e pt-PT não é pt-BR); o que vem de fora (páginas, transcrição, títulos) **é material, nunca
instrução**; e o passo de pesquisa recebe **só** o título, o tamanho e o idioma — o canal, o nicho e a observação ficam
para os passos sem internet.

**Os passos opcionais não derrubam o roteiro**: no teste, a revisão e a miniatura falharam e o roteiro foi entregue
mesmo assim ("pronto"). Isso esconde a falha: a tela não diz que o roteiro **não** passou pela revisão.

**O limite é da mesma assinatura**: o robô usa o Claude Code deste PC, a mesma conta do Claude que o Radar usa para
escrever roteiro e que esta sessão usava. Os três disputam o mesmo limite.

**Na revisão**, o cartão mostra o roteiro num campo editável, a contagem (palavras, minutos, caracteres, modelo e
tempo de escrita), "Aprovar e seguir", "Salvar alterações", "Refazer roteiro", o briefing do pedido e a **linha do
tempo com a hora de cada passo**.

## 4. O vídeo — o que um trabalho pronto mostra

Do `producao.log` e dos JSON do vídeo de 39:54 (481 cenas, 803 MB):

1. **Recebe o pedido** com as instruções do site, as chaves "desta produção" (do site, não do PC), a voz do canal, a
   trilha e o avatar. Liga o anti-sono.
2. **Narração numa chamada só** (32.929 caracteres, ElevenLabs multilingual v2 por um revendedor, ~1 min), com o
   tempo estimado pelo histórico ("costumam levar ~1min, medido em 64 narrações").
3. **Tempo das palavras pelo Whisper** (Groq): 5.741 de 5.783 palavras casadas (99%); palavras com tempo voltando
   atrás são puxadas para a frente.
4. **Cenas ("beats")** de ~5 s cada, cortadas pela fala: 481 no vídeo.
5. **Cartões na tela** planejados pelo texto: número ("10 FOODS", "$100", "3 MONTHS"), palavra ("Oats.", "That's a
   risk.") e lista ("cool / dark / dry"); 54 no vídeo, com um "pop" de efeito sonoro em cada. Cartão sem tempo para
   o próprio texto é derrubado.
6. **Planejador**: 81 chamadas de um modelo barato (Gemini Flash) escrevem, para cada cena, o assunto, a busca de
   imagem e a busca no YouTube (`pedidos.json`). A "espinha" diz de que item da lista cada cena fala, e a busca tenta
   o item primeiro.
7. **Material real vem do YouTube**: alvo de 25% (banda de 20% a 30%), caça até o alvo e só segue enquanto render;
   cada trecho baixado é **julgado em 5 quadros** (nota 75 ≥ 64 passa) e **cortado** quando tem legenda queimada. O
   resto vira **imagem de IA** (gpt-image) **só depois** do garimpo. Neste vídeo saiu abaixo da banda: 16,6% real.
8. **Seções conferidas na narração**: o bloco "Oats" só abre quando a voz diz "Number ten".
9. **Montagem**: corte seco, CPU, **volume a −14 LUFS** em dois passes, pico −1,1 dBFS.
10. **Entrega**: o MP4 na pasta do trabalho, um atalho em Downloads, **11 capítulos** prontos para a descrição, e o
    **custo por evento** (1.254 eventos): US$ 2,885, US$ 0,072/min — gpt-image US$ 2,10, Gemini US$ 0,71, Whisper
    US$ 0,07, narração em créditos.

## 5. O resto do site

- **Robô → Produzir**: quatro passos — Canal e conteúdo (cole o roteiro ou suba o áudio), **Estilo** (12 estilos de
  edição com vídeo de exemplo, filtrados por tipo de vídeo: Dossiê, Broadcast, Kinético, Cinema, Notebook, Case File,
  Magazine Collage, Spreadsheet, Newspaper, Horror, Reopened Case, Hacker; trilha e apresentador liga/desliga),
  **Ajustes** (quanto de material real × IA, a IA faz imagens e/ou vídeos, o acervo fotos e/ou vídeos, quem gera as
  imagens de IA, quanto de vídeo de IA, quanto de YouTube, o fornecedor da narração, o avatar a cada N segundos,
  segundos por cena, placa de vídeo) e **Revisão** (resumo com avisos, como "apresentador ligado sem rosto
  escolhido", e "Reutilize esta configuração").
- **Robô → Acompanhar / Produções**: a fila e o histórico com trabalho, custo e duração de cada vídeo; retomar o que
  parou.
- **Robô → Máquinas**: cada PC autorizado, "vídeos ao mesmo tempo" (automático, 1 a 16), versão e atualização sem
  instalador ("espera os vídeos terminarem").
- **Robô → Avatares**: personagens da HeyGen por ID, sempre 16:9.
- **Robô → Canais do Robô**: por canal, o YouTube, a voz (voice_id) com "Verificar voz", a velocidade (0,70 a 1,20),
  o avatar padrão e o "vídeo do ebook".
- **Robô → Custos**: por mês e por canal, o que é plano fixo e o que é uso de API, custo por minuto entregue, e o que
  falta informar para a conta fechar.
- **Canal**: a "Rota" (os canais como naves numa trilha 100 → mil → monetização → 100 mil → 1 mi em 28 dias, com
  nível e XP do usuário), Ranking (os seus canais lado a lado, 7/14/28 dias), Comentários ("o que a audiência pede"
  vira mudança no roteiro), Títulos ("o que os títulos campeões do canal têm em comum") e Meus canais. Tudo vazio na
  conta, porque nenhum canal tem o YouTube ligado.
- **Aprender**: cursos (Robô Dotti, Dotti Finder, Método Malandro) com meta da semana e sequência de dias.

## 6. O que levar para o Radar

O Radar já tem, desde 18/10, a janela Nova produção, a Entrada, a fila, a parada para revisar, o Acompanhar, os
Custos e as Integrações. O que falta, **em ordem de retorno**:

### A. O roteiro (Radar, `radar/roteiro_claude.py` e `radar/fila.py`)

Hoje o roteiro sai de **uma chamada só** ao Claude, **sem ferramentas** (`--tools ""`): sem pesquisa na web, sem
esboço, sem revisão. É a maior diferença de qualidade.

1. **Roteiro em passos**, cada um uma chamada `claude -p`: pesquisa (com a busca e a leitura de páginas ligadas só
   neste passo) → esboço com o tamanho de cada parte → escrita → revisão com uma rodada de conserto → prompt da
   miniatura. A regra "o que não foi conferido não entra" e as **lacunas** à vista na revisão.
2. **Formatos de roteiro** separados do estilo do canal: documentário, lista / top N, exposé, true crime,
   celebridade, jornada do herói, ensaio, como funciona, comparação, modelar uma referência. Hoje o Radar só tem as
   instruções de projeto por canal; o formato muda por vídeo.
3. **Limite do Claude tratado à parte**: hoje o erro vira "erro" e os próximos da fila batem no mesmo limite. Fazer
   como eles: o pedido fica "esperando o limite", a fila para de pedir por um tempo e há "Tentar de novo". E **dizer**
   quando um passo opcional foi pulado (eles entregam como "pronto" mesmo sem a revisão).
4. **A linha do tempo do pedido** com a hora de cada passo, no Acompanhar.
5. **"Colar vários títulos"** de uma vez na Entrada.

### B. O vídeo (fábrica / Tiplabs; repositório próprio, com as regras dele)

6. **Material real do YouTube**: o planejador escreve uma busca por cena, o trecho baixado é julgado em quadros e
   cortado quando tem legenda queimada, até uma porcentagem-alvo; a IA só cobre o que sobrar. A fábrica hoje usa
   Pexels, Pixabay e Wikimedia. **Cuidado**: reaproveitar vídeo de outros canais tem risco de direito autoral e de
   reivindicação no YouTube; precisa de decisão do usuário antes.
7. **Seções conferidas na narração** ("o bloco 'Oats' só abre quando a voz diz 'Number ten'") e a "espinha" que diz
   de que item cada cena fala, para a busca acertar o item.
8. **Capítulos para a descrição** gerados pelas seções, e o **custo por evento** com o custo por minuto entregue.
9. **12 estilos de edição com vídeo de exemplo** na hora de escolher.

### C. Fora do vídeo

10. **Comentários → roteiro**: ler o que a audiência pede nos comentários dos seus canais e virar ideia.
11. **Títulos campeões do canal**: o que os títulos que mais renderam têm em comum.

**Sugestão de começo**: A1 e A3 juntos. São do Radar, sem dinheiro novo (a mesma assinatura do Claude) e mudam o
que mais pesa no vídeo, que é o roteiro.
