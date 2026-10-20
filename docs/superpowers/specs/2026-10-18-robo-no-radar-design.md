# O que o Robô do Dotti tem e o Radar vai ganhar — desenho

Data: 2026-10-18. Pedido do usuário: "acrescentar tudo que tem no Robô Dotti que falta no nosso Radar e que seja
importante, como a quantidade de IA e todo o processo", "essa forma na criação de vídeo" (a janela Nova produção) e
"uma aba lá embaixo para acrescentar as APIs".

## Entendimento combinado

- **O que o usuário pediu**: a janela Nova produção, a aba de APIs, a quantidade de IA (mostrar e escolher), o
  Acompanhar completo, Custos e Máquina (vídeos ao mesmo tempo), e a fila automática.
- **Ficou de fora** (escolha do usuário): velocidade da narração e personagem/avatar por canal.
- **Regras que valem para tudo**:
  - Feito do zero no visual do Radar (escuro com marrom-dourado, `IDENTIDADE` no `app.js`), sem copiar código, texto
    ou visual do Dotti (regra do README).
  - Mexer em chaves, fila e produção é só para a administração (`dono_da_fabrica`). Quem vem pelo túnel continua só
    olhando e não vê as chaves.
  - O Radar mostra e comanda; quem faz o vídeo continua sendo a fábrica (`RADAR_FABRICA`, editor na porta 8080, com o
    `FABRICA_TOKEN`).
  - Sem barras coloridas na esquerda dos cartões; botão selecionado muda o fundo, nunca a cor da letra (regras do README).
  - Confirmação no próprio Radar, nunca `alert`/`confirm` do navegador.
- **Sucesso**: criar um vídeo pela janela em menos de 1 minuto; deixar vários na fila e eles saírem sozinhos, no limite
  escolhido; ver em cada vídeo a etapa, a % de IA, o log e o custo; trocar uma chave sem abrir o `.env`.

## Divisão e ordem

| Ordem | Parte | Onde mexe |
|---|---|---|
| A | Aba Integrações (APIs) | Radar |
| B | Nova produção + Entrada + fila automática + Máquina | Radar |
| C | Acompanhar novo (etapas, Real × IA, log, Arquivos, Tags e descrição) | Radar, lendo a fábrica |
| D | Custos | Radar, lendo a fábrica |
| E | Máximo de IA por vídeo | Fábrica (Tiplabs) + campo da Parte B |

A a D formam um plano de implementação. A E tem o seu próprio plano, escrito depois de ler o código de escolha de
material da fábrica e de puxar as atualizações dos dois repositórios do GitHub (regra do Tiplabs).

---

## Parte A — Integrações (APIs)

**Lugar**: Ferramentas → **Integrações**, item novo no fim do menu (`MENU` no `app.js`), rota `#/integracoes`.

**Tela**
1. **Saldos** (uma linha de cartões):
   - OpenRouter: saldo em US$ pela API do OpenRouter (`GET /api/v1/credits` com a chave da fábrica).
   - GenAI Pro: créditos por `GET /api/genaipro/creditos` da fábrica.
   - Kie.ai: créditos pela API da Kie.
   - YouTube: unidades usadas hoje por chave (tabela `cota` do Radar) e o total do dia.
   - OpenAI: a API não informa saldo; "Informar saldo" guarda um valor à mão (tabela `saldos_informados`), com a data.
   - Serviços grátis (Pexels, Pixabay) aparecem como "Gratuito".
2. **Chaves**: um cartão por serviço com nome, obrigatória/opcional, para que serve, status (testada / falhou / não
   configurada), a prévia mascarada (4 últimos caracteres), **Testar**, **Trocar**, **Remover**, "como funciona o
   limite" e "onde pegar a chave" (link).
   - Várias chaves por serviço onde a leitura já aceita (`YOUTUBE_API_KEY`, `YOUTUBE_API_KEY2`…; `GROQ_API_KEY`…),
     com "+ Adicionar".
3. **Contas**: o Google/YouTube Studio que já existe (`studio.py`), mostrado aqui também.

**Onde grava**
- Chaves do Radar (YouTube, Groq, `RADAR_GOOGLE_*`): no `.env` do Radar, com a mesma mescla linha a linha da fábrica
  (não apaga comentários nem outras chaves). Depois de gravar, `config.AMBIENTE` é recarregado sem reiniciar.
- Chaves da fábrica (OpenRouter, GenAI Pro, OpenAI, Kie, Pexels, Pixabay, Gemini…): por `GET/POST /api/config/chaves`
  da fábrica, que já lista `CHAVES_CONHECIDAS` com o mascaramento e grava no `.env` dela. O Radar não escreve no
  arquivo da fábrica.

**Peças**
- `radar/integracoes.py`: lista de serviços (nome, env, obrigatória, para que serve, onde pegar, como testar),
  `saldos()`, `testar(servico)`, `gravar(servico, valores)`, `remover(servico, indice)`.
- Rotas: `GET /api/integracoes`, `POST /api/integracoes/{servico}/testar`, `POST /api/integracoes/{servico}`,
  `DELETE /api/integracoes/{servico}/{indice}`, `POST /api/integracoes/{servico}/saldo`. Todas exigem a
  administração e recusam pedido pelo túnel.
- O teste faz uma chamada barata (listar modelos, ler 1 vídeo) e fica guardado 1 hora.

**Segurança**: a chave inteira nunca volta para a tela nem para o log; só a prévia.

**Erros**: fábrica desligada → os cartões da fábrica dizem "fábrica desligada" e as chaves do Radar seguem editáveis.

**Testes** (sem rede): mescla do `.env` (troca, acrescenta, mantém comentários), mascaramento, recusa para quem não
é administração e para pedido com `cf-connecting-ip`.

---

## Parte B — Nova produção, Entrada, fila automática e Máquina

**Botão**: "+ Nova produção" no topo de todas as telas (junto do Cores) e no Acompanhar; atalho Ctrl+N. O Produzir de
3 passos continua no menu, sem mudança.

**Janela (duas colunas)**

Esquerda, os campos em ordem:

| Campo | Regra |
|---|---|
| Título do vídeo | Obrigatório |
| Vídeo de referência | Opcional. Colar o link mostra capa e título (`/api/titulo-do-video`); "usar o título da referência" |
| Canal | Chips com foto/sigla dos canais configurados (`canais_config`). Escolher preenche estilo, idioma, voz e tamanho |
| Estilo do roteiro | Os agentes de roteiro (`projetos_roteiro`), cada um com a linha "Ideal para…" (campo novo `ideal_para` no agente, editável onde o agente é editado) |
| Idioma | Vem do canal; muda só neste vídeo |
| Tamanho | Em caracteres, com "≈ N min · ~N palavras" e atalhos 8, 10, 12, 15, 20, 25, 30 min. A conta usa a velocidade medida da voz do canal (o ajuste automático de 2026-10-18, `/api/roteiros/ritmo`); sem medição, 150 palavras por minuto. Limites: 1.000 a 80.000 caracteres |
| Roteiro | "O Claude escreve" (padrão) ou "Já tenho o roteiro" (colar; usa o roteiro manual que já existe) |
| Nicho, Observação | Opcionais, vão no pedido ao Claude |
| Máximo de IA | Só real / até 25% / até 50% / livre. Guardado já; vale quando a Parte E chegar à fábrica (até lá: "em breve na fábrica") |
| Parar para eu revisar | Liga/desliga (o "revisar antes ou mandar direto" que já existe) |

Direita, "Assim ele entra na fila": prévia do cartão (capa ou título, canal, estilo, tamanho, revisão, máximo de IA)
e o **custo estimado** = minutos × média de US$/min dos vídeos entregues daquele canal (dos Resultados; sem
histórico, a média geral; sem nada, não mostra).

Botões: **Salvar na Entrada** (guarda, não começa, não gasta) e **Criar e começar** (Ctrl+Enter).

**A fila (no Radar)**
- Tabela `producoes_fila`: id, usuario_id, criado, estado, ordem, título, referência, canal_id, agente, idioma,
  caracteres, roteiro_manual, nicho, observação, ia_maxima, revisar, nome do roteiro (`dados/roteiros/`), projeto da
  fábrica, erro, atualizado.
- Estados: `entrada` → `na_fila` → `escrevendo` → `sua_vez` (só com revisão ligada) → `enviando` → `produzindo` →
  `entregue`; e `erro`, `cancelado`.
- **Vigia** (thread do servidor, a cada 20 s): conta na fábrica os vídeos produzindo (`/api/projetos` + `/status`);
  enquanto houver vaga no limite, pega o próximo `na_fila` pela ordem e avança: roteiro pelo Claude
  (`roteiro_claude.gerar`, em segundo plano) → revisão (se ligada, para em `sua_vez`) → `roteiro_claude.enviar`
  (grava também `ia_maxima` no `projeto.json`) → produção.
- **"Criar e começar" é o sim para gastar**: o vigia chama a produção da fábrica já confirmada
  (`POST /api/projetos/{nome}/retomar` com `confirmar: true`). Pedidos na Entrada não gastam nada. O ▶ Produzir de
  hoje (estimativa e depois o sim) continua igual para quem não usa a fila.
- O roteiro pelo Claude não ocupa vaga da fábrica (roda neste computador pela assinatura); a vaga conta só os vídeos
  em `enviando` e `produzindo`.
- Fábrica desligada ou computador desligado: a fila espera e volta sozinha. Falha: estado `erro` com o motivo e
  "Tentar de novo" (volta para `na_fila` no ponto onde parou).

**Máquina**: no topo do Acompanhar, "Fábrica ligada · N ao mesmo tempo ▾" (1, 2, 3, 4, 6, 8; padrão 2), guardado no
Radar (tabela de ajustes) e respeitado pelo vigia.

**Rotas**: `POST /api/fila` (criar; `começar` true/false), `GET /api/fila`, `POST /api/fila/{id}/comecar`,
`POST /api/fila/{id}/aprovar` (sai de `sua_vez`), `POST /api/fila/{id}/tentar`, `DELETE /api/fila/{id}`,
`GET/POST /api/fila/ajustes` (vídeos ao mesmo tempo). Criar, começar, aprovar e ajustar exigem a administração.

**Testes** (fábrica de mentira, sem rede): passagens de estado, o vigia respeitando o limite, a revisão parando em
`sua_vez`, retomada depois de erro, e a conta caracteres ↔ minutos pela velocidade da voz.

---

## Parte C — o novo Acompanhar

**Topo**: "Fábrica ligada · N ao mesmo tempo ▾" e os números Produzindo · Na fila · Precisa de você. "Precisa de
você" = roteiro em `sua_vez`, fábrica pedindo o modelo pago (`pago_pendente`/`precisa_voce`) ou erro.

**Esquerda**: blocos Precisa de você, Produzindo, Na fila, Entrada; cartão com canal, hora do pedido, etapa e barra de
%; busca por título e filtro por canal. Os vídeos produzidos fora da fila (pelo Produzir ou pela fábrica) também
aparecem em Produzindo.

**Direita, o vídeo escolhido**: título, canal, hora do pedido, tempo correndo, "etapa X de Y" e %. Quatro abas:

| Aba | Conteúdo | Fonte |
|---|---|---|
| Acompanhamento | Etapas em bolinhas (Roteiro → Narração → Cenas → Material → Imagens de IA → Montagem), a atual destacada, a mensagem de agora e o tempo de cada etapa feita | `/status` (passo_atual, total_passos, mensagem, etapa) e `criacao.json` (`feitas`, "Tempo por etapa") |
| Diagnóstico | Barra Real × IA com os números e a % de IA (e o limite pedido, depois da Parte E); log com filtro (todos, aviso, erro, concluído) e Baixar log | `cenas.json` e `criacao.json` → `logs` |
| Arquivos | Assistir o final, baixar a legenda (.srt), thumbnails, shorts, Abrir pasta | Rotas que já existem nos Resultados |
| Tags e descrição | Título, descrição, tags e capítulos com Copiar; Gerar quando não houver | `GET/POST /api/projetos/{nome}/publicacao` da fábrica |

**Contagem Real × IA** (`radar/diagnostico.py`), por cena do `cenas.json`:
- `midia.fonte` em `animation_ai` ou `motion_ia` → **Animation IA**;
- `midia.fonte` de banco (pexels, pixabay, wikimedia, unsplash, inaturalist, nypl, youtube, storyblocks, acervo…) →
  **Real**;
- sem `midia` real e com imagem gerada (tipo `ia` ou `sem_midia_real`) → **Imagem de IA**;
- sem nada ainda → **pendente** (enquanto produz).
A regra fica perto da que a fábrica usa em `custos.py` (`TIPOS_REAIS`, `sem_midia_real`) e é conferida com a linha
"Origem: … escolhida, … IA, … Animation IA" que a fábrica escreve no fim.

**Ações**: Liberar modelo pago (`POST /pago`), Tentar de novo, Aprovar roteiro (em `sua_vez`), Parar e apagar (com
confirmação no Radar; apaga o pedido da fila e, se já existir, o projeto na fábrica por `DELETE /api/projetos/{nome}`).

**Atualização**: o vídeo aberto a cada 5 s; os outros cartões a cada 20 s.

**Notificação do Windows** (a que já existe): também para entregue, precisa de você e erro.

**Rotas novas**: `GET /api/acompanhar` (blocos e números), `GET /api/acompanhar/{nome}` (cabeçalho e etapas),
`GET /api/acompanhar/{nome}/diagnostico`, `GET /api/acompanhar/{nome}/log.txt`,
`GET/POST /api/acompanhar/{nome}/publicacao`.

**Testes**: contagem Real × IA com um `cenas.json` de exemplo (os três casos e pendente) e o filtro do log.

---

## Parte D — Custos

**Lugar**: Meu trabalho → **Custos**, rota `#/custos`. Fonte: `custos_reais.json` de cada projeto da fábrica (cada
linha tem `categoria`, `valor_usd`, `detalhes.provedor`), lido pela pasta da fábrica e guardado em memória até o
arquivo mudar.

- Resumo do período (7, 30, 90 dias, tudo): total, vídeos, média por vídeo, US$ por minuto de vídeo.
- Por provedor (barras) e por categoria.
- Por vídeo: canal, data, duração, custo, US$/min; filtros de canal e provedor; busca por título; clicar abre o
  detalhe por categoria.
- Por canal: total e média por vídeo (o canal vem do mesmo lugar dos Resultados, `resultado_canal` por cima do perfil).
- Em produção: "medindo…", valor subindo.

**Rotas**: `GET /api/custos?periodo=&canal=&provedor=`, `GET /api/custos/{nome}`.

**Testes**: as somas a partir de um `custos_reais.json` de exemplo (linha sem provedor cai em "outros").

---

## Parte E — máximo de IA por vídeo (fábrica)

**Hoje**: cada cena nasce planejada como real ou IA; a cena real que não acha material vira IA (`sem_midia_real`).

**Regra nova**
1. O Radar grava `ia_maxima` (0, 0.25, 0.5 ou ausente = livre) no `projeto.json` ao enviar.
2. No planejamento das cenas, o agente recebe a meta e planeja mais cenas reais.
3. Ao cair para IA com o vídeo já no limite: fica o melhor material real encontrado, mesmo abaixo da nota mínima de
   captura; senão, foto real animada (Animation IA com foto); imagem de IA só quando nada real sobrou, registrada como
   "passou do limite" no log (aparece no Diagnóstico).
4. `ia_maxima` 0 ("só real") nunca gera imagem de IA.

**Custo da escolha**: com limite baixo, algumas cenas ficam com material menos preciso; o Diagnóstico aponta quais.

**Antes de começar**: puxar as atualizações dos dois repositórios do Tiplabs no GitHub; ler a escolha de material
(`cenas.py`, `diretor.py`, `corrigir.py`, a busca do acervo) e escrever o plano próprio desta parte.

**Testes**: a regra com cenas de exemplo (abaixo do limite, no limite, só real) e um vídeo curto de teste conferindo a
% no Diagnóstico.

---

## Fora deste desenho

Velocidade da narração e personagem/avatar por canal; publicar no YouTube sozinho; Google Drive; Storyblocks; o
"Chat"/comunidade do Dotti; planos e vagas de máquina.
