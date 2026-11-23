# Estudo da Dotti em sala limpa (2026-11-22)

Robô estudado: `AppData\Local\DottiStudio\robo`, versão `agente-0.2.174` (build `d1743f756a02`).

**Como foi feito.** Só o que o robô mostra por fora: `robo.log`, `diagnostico.log`, as 3 pastas
`producoes/job_*` e os JSON de dados que vêm soltos no pacote. O núcleo (`agente.cp312-win_amd64.pyd`)
é compilado e **não foi aberto**. Ficaram de fora `.env`, `maquina.chave` e `cookies.txt`.
Nenhum código, texto ou arquivo da Dotti foi copiado. Este documento descreve comportamento.

**Do nosso lado** foram lidas as docstrings de todos os módulos de `radar/` e `fabrica/`, e as linhas
de cada ponto abaixo. Uma busca que não achou nada não prova que a coisa falta: os itens marcados
"não achei" pedem conferência antes de virar tarefa.

## Como o robô trabalha

1. **O site manda, a máquina faz.** O robô pede trabalho ao site (`reivindicar`), recebe um lease com
   época (`fencing_epoch`) e, ao terminar, manda uma prova de entrega (`aprovado` ou `tente_depois`).
   Lease vencido ou época maior: ele larga o vídeo e pega o próximo. A rede caindo não derruba o robô:
   ele tenta de novo com espera crescente (20, 40, 60, 80, 120 s) e guarda o log numa fila até o site
   voltar.
2. **Até 3 produções por máquina.** A máquina é repartida entre elas: núcleos e RAM viram "N beats em
   paralelo", com piso e teto. O computador não suspende enquanto há produção.
3. **As chaves vêm do site em cada produção** (Gemini, Groq, OpenRouter, OpenAI, HeyGen, Kie, a
   narração). A máquina não guarda chave de provedor.
4. **Quadro de tarefas (roteiro e miniatura).** O roteiro e a miniatura são cartões que o robô faz
   com o Claude Code da pessoa. Passos opcionais (pesquisa, revisão, juiz, prompt da miniatura) são
   pulados quando o Claude bate no limite da assinatura, e a máquina só volta a pedir roteiro depois
   de um tempo. A miniatura tenta primeiro o Codex e cai para outro caminho sem ele.

### Etapas de uma produção (pela ordem do `producao.log`)

`reivindicado → youtube → maquina → visuais → trilha → sfx → narracao → timing → beats → cards →
planner → origem → youtube (garimpo) → visuais → ia → encoder → cards → encoder`

- **Narração numa chamada só.** Foram 31.445 caracteres de uma vez, pelo provedor "69labs", com o
  `eleven_multilingual_v2`. Enquanto espera, o log diz quanto costuma levar, medido nas narrações
  anteriores, e avisa quando passa do normal.
- **Tempo pelo Whisper.** Ele ouve o áudio e casa as palavras com o roteiro (cobertura em %). Palavra
  com tempo voltando atrás é empurrada para a frente.
- **Beats curtos.** Um vídeo de 39 min teve 469 beats, de uns 5 s cada.
- **Cards automáticos.** Números, listas e palavras de impacto saem do roteiro ("3 DAYS", "$12") e
  viram PNG por cima do vídeo: 52 num vídeo de 39 min.
- **Planner por lote.** Para cada beat o modelo devolve o assunto, a busca para os bancos, a busca
  para o YouTube e o tipo de mídia (real ou IA). Foram 80 chamadas para 469 beats.
- **"Espinha".** Em vídeo de lista ou ranking, cada beat sabe de que item está falando, e a busca
  tenta o item primeiro. Beat que o roteiro abre fora da espinha fica sem item, em vez de herdar o
  da seção anterior.
- **Divisão real × IA por porcentagem.** A tela pede um alvo de filmagem real. O resto vira imagem de
  IA, e o log fecha com o placar (no job estudado: 91 reais, 378 IA, de 469).
- **Garimpo no YouTube.**
  - Teto de downloads por vídeo, calculado pelo pior caso medido.
  - Título ruim em todos os degraus faz desistir sem baixar nada ("bail").
  - Cada trecho é julgado em 5 quadros: aceito a partir de 64, "excelente" para de baixar outros.
  - Veto de texto queimado, com uma segunda chance cortando a faixa de baixo.
  - Logo de canal no canto é cortado no enquadramento.
  - Trecho com corte do editor original no começo é cortado a partir do maior pedaço contínuo.
  - Vídeo que proíbe tocar fora do YouTube tenta outra rota, e o corte simples que falha tenta o
    corte preciso (com recodificação).
  - Mais de uma produção na máquina divide o ritmo do YouTube e estica o prazo da busca.
  - Avisa quando só uma conta do YouTube está pronta.
- **Bancos em degraus.** Primeiro Pexels, depois Pixabay e Wikimedia. O mesmo candidato não entra em
  dois beats da mesma produção.
- **Imagem de IA pela assinatura do ChatGPT.** Várias sessões em paralelo, conforme a RAM livre, e
  gerada junto com o garimpo, não depois. Sem crédito, a produção **pausa** antes da fase de IA e
  nunca entrega cena repetida.
- **Encoder em escada.** Testa nvenc, qsv e amf com uma prova de 1 s. Se a placa falhar no meio,
  segue em libx264. Fonte mais curta que o beat entra em vaivém.
- **Saídas da pasta do job.** `CREDITS.txt` (autor, licença e fonte de cada filmagem), `custos.jsonl`
  (uma linha por chamada, inclusive as que o site fez), `escolhas.json` (por que cada trecho foi
  aceito ou recusado), `pedidos.json` (o que o planner pediu), `estado.json` e `timing_relato.json`.

### Motion e som (dos JSON soltos no pacote)

- **13 estilos:** dossie, broadcast, kinetico, cinema, notebook, casefile, collage, spreadsheet,
  newspaper, horror, hacker, reopened e investigation.
- **189 peças de motion.** São templates HTML com variáveis, duração mínima e âncoras de posição.
  Um serviço de render remoto renderiza as peças, e o robô não pede nenhuma sem o catálogo.
  Nenhum texto fica fixo no template: os rótulos de cada estilo têm tradução por idioma, e o idioma
  que falta cai no inglês com aviso no log.
- **Som por evento.** Cada peça dispara efeitos em pontos marcados (abre, fecha, foto entra), com
  volume calibrado contra a voz. Cada estilo tem uma música própria.
- **Densidade das edições.** Há famílias com prioridade (seções, fatos, datas, listas, nomes,
  rankings, citações, contrastes, karaokê, perguntas, impactos), **no mínimo 5 s entre duas** e
  **no máximo 6 por minuto**.
- **Transições e loops em vídeo** (queima, flash, dissolve, brasas, poeira) para os vídeos de dormir.

## Comparação com a fábrica e o Radar

### Já temos

| Dotti | Nosso |
|---|---|
| Site manda, máquina faz, com lease e prova | `radar/maquinas.py`, `fabrica/robo.py` (lease, `lease_velha`, prova do `final.mp4`) |
| Fila com limite de vídeos ao mesmo tempo | `radar/fila.py`; `fabrica/vez.py` serializa as etapas lentas |
| Máquina repartida entre produções | `render._parte_da_maquina` |
| Não suspender | `fabrica/acordado.py` |
| Roteiro pelo Claude Code da pessoa | `radar/roteiro_claude.py`, `fabrica/claude_local.py` |
| Imagem pela assinatura do ChatGPT | `fabrica/chatgpt_assinatura.py`, `radar/chatgpt_conta.py` |
| Divisão real × IA | `cenas._aplicar_fracao_da_ia` (`ia.fracao`) |
| Garimpo com teto de downloads, texto queimado e corte da faixa de baixo, várias contas | `fabrica/garimpo.py` |
| Bancos Pexels, Pixabay, Wikimedia e outros | `fabrica/midia.py`, `fabrica/bancos.py` |
| Escada de encoder com prova de 1 s e queda no meio | `fabrica/render.py` (cerca da linha 957) |
| Whisper | `fabrica/conferir_voz.py` (confere a voz; o tempo vem da legenda do provedor) |
| Custo por chamada | `fabrica/custos_reais.py`, `radar/custos.py` |
| Créditos das filmagens | `fabrica/publicacao.py`, `fabrica/entrega_pc.py` |
| Avatar pela HeyGen | `fabrica/avatar.py` |
| Partículas brasas e poeira | `fabrica/camadas.py` (desenhadas por código) |
| Motion por modelos prontos | `fabrica/animacoes.py` (HyperFrames), `motion_ia.py`, `animation_ai.py` |
| Avisos de crédito acabando | `radar/avisos.py` |

### Não achei (conferir antes de fazer)

1. ~~**Logo de canal no canto do trecho do YouTube.**~~ Feito em 2026-11-22:
   `garimpo.limpar_trecho` / `canto_do_logo` (pixels parados com borda num canto só; aperto de no
   máximo 20%). Nos 33 trechos já aceitos: 5 logos reais cortados e 1 cenário parado descartado
   pelo teto do aperto.
2. ~~**Corte do editor original no trecho.**~~ Feito em 2026-11-22: `garimpo.cortes_do_editor` /
   `maior_pedaco`. Fica o maior pedaço que cobre a cena; sem pedaço assim, o trecho fica como veio.
   Nos 33 trechos: 10 tinham corte, 4 conferidos a olho, todos reais.
3. ~~**Regra de densidade das animações.**~~ Feito em 2026-11-22: `animacoes.espacar`. No mínimo 5 s livres
   entre duas animações (`animacoes.intervalo_minimo`) e no máximo 6 começando em qualquer minuto
   (`animacoes.por_minuto`). Quando duas disputam o mesmo lugar, ganha a família mais forte: linha do tempo e mapa,
   depois diagrama, texto na tela e, por último, o card automático. A regra vale para o que a criação anima
   sozinha. A animação pedida no editor e as que já existem ficam como estão.
4. ~~**Cards automáticos de número.**~~ Feito em 2026-11-22: `animacoes.numero_que_pesa`. A narração escreve os
   números por extenso, para a voz ler certo, então a busca é por palavra: número com grandeza, porcentagem ou
   dinheiro ("four hundred billion", "trinta por cento"). Ano, número pequeno, grandeza sozinha ("millions of") e nome
   de índice ("S&P five hundred") ficam de fora. Funciona em inglês, português e espanhol. A cena vira candidata
   a animação com o número como sugestão e entra no ritmo do item 3. Desliga com `animacoes.cards_automaticos: false`.
   Nos projetos medidos, os de dinheiro ganharam 6 a 10 cards em 14 min. O de animais, nenhum.
   Lista e palavra de impacto continuam com o agente de roteiro (`texto_tela`).
5. ~~**Previsão do tempo da narração.**~~ Feito em 2026-11-22: `fabrica/previsao_narracao.py`. Guarda as 10
   últimas narrações de cada provedor e voz (segundos por mil caracteres, em `narracao_tempos.json`). Antes de
   narrar, o log diz quanto costuma levar. Ele avisa uma vez quando a narração passa de 1,5 vez o normal.
6. **Espinha de itens em vídeo de lista ou ranking: já existia.** Cada item da lista é um bloco no
   `roteiro_mapa.json`, com âncora e contexto. Conferido no "15 animais de fazenda": 17 blocos, um por raça. A busca
   usa a âncora do bloco (`midia.py`, perto da linha 1267). Ela também pune a âncora de outro bloco
   (`midia.py:1548`). Não mexi.
7. ~~**Vídeo que proíbe tocar fora do YouTube.**~~ Feito em 2026-11-22: `garimpo._baixar_por_rotas`. Com erro de
   rota (incorporação desligada, formato que não vem, 403, ffmpeg falhando no corte), tenta outros clientes do
   YouTube (`tv,web_safari,mweb`). Se ainda falhar e o vídeo tiver até 15 min, ele vem inteiro e o corte preciso
   é feito aqui. Vídeo privado, apagado ou com direitos bloqueados desiste na hora. O corte já era preciso
   (`--force-keyframes-at-cuts`).
8. **Pausar sem crédito de imagem: já existia.** Sem cota, `imagens.gerar` para a etapa (`SemCota` vira
   `SystemExit`) e a esteira tenta de novo de 5 em 5 min, ou para e pede a pessoa quando é crédito
   (`api._ERRO_PERMANENTE`). Imagem repetida é proibida (`midia.tirar_repetidas`). Não mexi.
9. ~~**Escala do motion.**~~ O estudo errou: já tínhamos 12 temas em `animacoes.TEMAS` (noticiário, dossiê, cinema,
   jornal, caderno, planilha, hacker, terror, colagem, cinético, pasta de caso, caso reaberto). Em 2026-11-22 entraram:
   - o tema **investigação** (cortiça escura, fio e alfinete vermelhos), também na Nova produção do Radar;
   - o **som da entrada por tema** (`animacoes.SOM_DO_TEMA`: papel, bipe e grave, feitos pelo ffmpeg);
   - a **trilha que parte do clima do tema** (`trilha.CLIMA_DO_TEMA`): o modelo ainda escolhe bloco a bloco, e sem
     o modelo as regras saem no clima do tema.

10. ~~**Claude no limite da assinatura.**~~ Feito em 2026-11-22: `roteiro_claude.LimiteDoClaude` e
    `pausa_do_claude`. Quando o Claude Code diz que o limite acabou, o Radar guarda a hora da renovação (lida da
    mensagem; sem ela, meia hora) em `dados/claude/limite.json` e não chama mais o Claude até lá. As etapas que o
    roteiro dispensa seguem sem ele, e a conferência do tamanho fica com a melhor volta. Se o limite cai no rascunho, o
    pedido volta para a fila sem erro, e a fila só pede roteiro de novo quando o limite renova. O roteiro colado anda
    normalmente.

### Conferência das formas de motion e das regras de vídeo (2026-11-22, segunda passada)

Lidos por fora, sem copiar: `edicoes/prioridade.json`, `edicoes/lugares_nomes.json`, `motion/som/catalogo.json`,
`motion/som/cues.json`, `motion/i18n/*.json` e `sleep_efeitos/relatorio.json`. A Dotti tem 172 peças de motion de 80
tipos, em 13 estilos, e 15 famílias de edição. Do nosso lado são três sistemas: `animacoes` (8 modelos), `motion_ia`
(19 modelos) e `animation_ai` (30 layouts em 9 temas).

**Já temos:** número e contador, porcentagem, lista e lista curta, ranking, citação, contraste e antes e depois,
linha do tempo, fato, definição, documento, manchete, comparação em barras, causa e efeito, passos e checklist. Também
o ritmo (5 s e 6 por minuto), o número no formato da língua do vídeo e o garimpo inteiro (nota 64 do trecho, corte do
editor, logo, outra rota).

**Os 13 que faltavam: feitos em 2026-11-22.** As formas novas ficam em `fabrica/animacoes_formas.py`, desenhadas do
zero no padrão dos nossos modelos: o modelo de linguagem só preenche textos curtos e o segundo de cada um. Todas
passam na conferência do HyperFrames e ficam dentro da área útil da tela, sem descer para a legenda.

1. ~~**Título de seção automático.**~~ Forma `secao`: "CAPÍTULO N" e o nome do bloco do roteiro, no começo de cada
   bloco. No máximo um a cada 90 s (os blocos têm uns 50 s, e 15 títulos em 14 min eram demais).
2. ~~**Nome na tela.**~~ Forma `nome`: a tarja embaixo à esquerda, ou a linha de crédito. A fábrica acha o nome sozinha
   (duas a quatro palavras com maiúscula, ou as pessoas reais do mapa do roteiro), uma vez por nome no vídeo.
3. ~~**Data sozinha.**~~ Forma `data`: o ano carimbado no meio ou no canto. Acha o ano escrito por extenso em inglês,
   português e espanhol ("in nineteen eighty-four", "em mil novecentos e trinta"), e não confunde com dinheiro ("dois mil
   reais").
4. ~~**Mapa com geografia real.**~~ Forma `mapa_mundi` e o atlas `fabrica/lugares.py`, escrito aqui: 438 lugares
   (países, capitais, cidades, regiões e marcos) com os nomes nas três línguas, e os contornos dos continentes em
   desenho simplificado. Acende o ponto certo, traça a rota pelo caminho mais curto e mede a distância de verdade
   (Xangai a Berlim, ≈ 8.400 km). O atlas é menor que o da Dotti (9.549 nomes em 32 línguas): lugar que falta volta
   para o modelo usar o `mapa` de antes.
5. ~~**Termo técnico.**~~ Forma `termo`: a palavra digitada letra a letra, com o que ela quer dizer. Acha o termo
   apresentado na fala ("known as short selling", "o que se chama de efeito manada").
6. ~~**Pergunta e palavra gigante automáticas.**~~ Formas `pergunta` e `impacto`, achadas na fala. Só frase inteira:
   o pedaço da frase da cena anterior ("floor.") não conta.
7. ~~**Foto em destaque.**~~ Forma `foto` (polaroid, folha de contato ou lupa no detalhe), com a imagem da própria
   cena.
8. ~~**Karaokê.**~~ Forma `karaoke`: a frase inteira, cada palavra acendendo no segundo em que é falada.
9. ~~**Peças que não tínhamos.**~~ `rede`, `ticker`, `quiz`, `teaser` (desligado por padrão: o título do capítulo já
   diz o que vem; `animacoes.teaser: true` liga), `chamada` (no máximo uma a cada 5 min) e `carrossel` (as fotos das
   cenas seguintes).
10. ~~**Quadro de provas.**~~ Forma `provas` em 4 variantes: ficha, recibo (com valores e total), tiras e fio.
11. ~~**Som por evento.**~~ Cada forma toca o som de cada momento dela (o carimbo bate, a máquina escreve, o ponto
    acende, o botão é clicado), em três níveis contra a voz: o acento 6 dB abaixo dela e os outros de 10 a 16 dB
    (`animacoes.NIVEL_DO_SOM`). Os 8 sons novos (carimbo, máquina, batida, clique, sino, foto, ping, tecla) são feitos
    pelo ffmpeg, sem baixar nada. Os modelos de antes seguem com um som só, no volume de sempre.
12. ~~**Palavras funcionais.**~~ `animacoes_achar.FUNCIONAIS`, em inglês, português e espanhol. Também valem na
    conferência do `animation_ai`, que antes só conhecia as de português.
13. ~~**Transições dos vídeos de dormir.**~~ Quatro transições de luz (`queima`, `superexposicao`, `dissolve`,
    `derreter`) e duas camadas novas (`douradas`, `vazando`), no perfil (`transicao`, `camada`) e na Nova produção do
    Radar. Como cada clipe é renderizado sozinho, a luz cobre o corte: o clipe termina subindo a luz e o seguinte começa
    com ela descendo.

**As famílias achadas na fala** (`fabrica/animacoes_achar.py`) entram no ritmo do item 3 da primeira passada, cada
uma com prioridade: capítulo e inscreva-se primeiro, depois mapa, ano, número, nome, termo, foto, pergunta, karaokê e
impacto. As marcadas pelo agente de roteiro (diagrama, linha do tempo) continuam valendo mais que as achadas. No vídeo
da Tesla (14 min), a fábrica achou 51 candidatas e o ritmo deixou 32. Liga e desliga em `config.yaml`
(`animacoes.formas_automaticas`, `formas_desligadas`, `teaser`).

Não dá para conferir: `fato_perto_impacto` (o nome não diz o que é), e as peças só têm nome e tempo de som no pacote:
o desenho delas vem de um serviço de render remoto da Dotti.

### O que a Dotti não tem e nós temos

O Radar inteiro: garimpo de canais, nichos, molde de título, crachá, retenção, horários, Studio,
Trello e o MCP de leitura. Na fábrica: conferência de mídia pelo Jev e pelo Gemini, diretor,
revisão do vídeo pronto, shorts, kit de publicação, banco próprio de imagens e vozes locais.

### Entregar rápido como a Dotti (terceira passada, 2026-11-22)

Pelos 4 jobs dela neste computador: a Dotti paga uma API só, o Gemini pelo OpenRouter (3.1 Flash Lite no juiz e na
detecção de logo e texto, 3.6 Flash no planejamento), US$ 1,00 a 1,40 por vídeo de 40 min, com zero falhas e zero
esperas de limite. O juiz dela dá nota de 0 a 100 a 5 quadros de cada trecho, uma vez só, na captura (64 aceita, 85
para de baixar). Nos nossos 5 vídeos do mesmo dia os gratuitos falharam de 130 a 460 vezes por vídeo antes de cada
chamada cair na paga. O que mudou:

1. **Cadeia paga primeiro** (`openrouter.gratis_primeiro: false`): a roda começa pelo Gemini 3.1 Flash Lite e pelo
   Gemma 4 26B, pagos; o Gemini 2.5 Flash Lite (que levava 429 do Google) saiu da roda; os gratuitos ficaram no fim,
   de reserva. O mesmo na cadeia de visão. Os Gemini pagos não pensam (`raciocinio_por_modelo`). O teto de gasto subiu
   para US$ 0,12 por minuto de vídeo (o dobro do que a Dotti gasta), para a produção não parar esperando confirmação.
2. **Juiz uma vez só**: o garimpo já julgava o trecho na captura (nota 64) e quem escolhe já via a miniatura e o
   título antes de baixar. A imagem de IA da garantia não volta mais ao juiz (`corrigir.conferir_ia_da_garantia`).
3. **Prazo da busca pelo rendimento** (`midia.rendimento_depois_de_min: 3`, `rendimento_limite_s: 180`): se no ritmo
   de agora o que falta levaria mais de 3 min, as cenas depois do começo vão para a IA.
4. **Animações 4 por vez** (`animacoes.paralelo: 4`, medido: 13 s por animação sozinha, 7,1 s com 4 juntas) e a
   conferência do HyperFrames sem o contraste e com 5 amostras (8,5 s para 6,8 s).
5. **403/429 do YouTube não baixa o vídeo inteiro**: o candidato sai e o garimpo segue para o próximo.

### O que ainda faltava (quarta passada, 2026-11-22)

- **Música própria por tema** (`trilha.MUSICA_DO_TEMA`): cada tema tem tom, modo, faixa de andamento e timbre fixos
  (terror em drone grave, hacker e noticiário em pluck, investigação, dossiê e jornal em piano, cinema em sino). O
  modelo segue escolhendo clima, progressão e intensidade de cada bloco; o tema dá a identidade do vídeo inteiro.
- **Capítulos nas tags** (`publicacao.tags_com_capitulos`): o nome de cada capítulo entra nas tags depois das do
  modelo, sem os genéricos ("introdução", "conclusão") e dentro das 500 letras do YouTube.
- **Atlas maior**: de 438 para 855 lugares e 1.611 nomes, agora também em francês, alemão e italiano, com mares,
  estreitos, cordilheiras e marcos (Torre Eiffel, Cataratas do Iguaçu, Muralha da China). Nomes que também são palavra
  comum ou nome de gente (Natal, Madeira, Granada, Nice, Darwin) só viram lugar depois de uma preposição de lugar.

Ficaram de fora: os sons gravados com licença (precisa baixar uma biblioteca de efeitos, e isso pede a autorização da
pessoa) e as chaves de API vindas do site a cada vídeo (decisão: as nossas ficam no computador).

**Sons gravados (2026-11-22, com a autorização do usuário):** baixados os pacotes Impact Sounds, Interface Sounds e UI
Audio da Kenney (kenney.nl, CC0). Ficaram só os 33 arquivos usados, com a licença de cada pacote, em
`fabrica-videos/efeitos/sons_cc0/kenney` (351 KB). Carimbo, palavra batida, clique, tecla, sino, ping e pop agora são
gravações, variando entre as versões de cada um a cada vez que tocam (`camadas.GRAVADOS`). Passagem, papel, máquina de
escrever, contador, bipe, grave e foto continuam feitos pelo ffmpeg: os pacotes CC0 que os teriam (OpenGameArt) não
deixaram conferir a licença.
