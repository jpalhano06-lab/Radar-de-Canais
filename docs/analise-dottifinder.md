# Dotti Finder por dentro — o que dá para aproveitar no Radar (levantado em 2026-10-22)

Análise do concorrente `dottifinder.com`, feita só com o que é público: as páginas abertas
(`/`, `/entrar`, `/extensao`), os arquivos estáticos que elas carregam
(`app.js` 285 KB, `contas.js` 128 KB, `planos.js`, `planos-cartoes.js`, `esqueleto.js`) e as
rotas de API que respondem sem sessão (`/api/porta`, `/api/abertura`,
`/api/extensao/versao?funcoes=1`). Não houve login: o painel por dentro
(`/api/descoberta/filtros`, `/api/acervo/visoes`, `/api/janela/nichos`) devolve 403, então o que
está aqui sobre essas telas vem do código do front, não da tela renderizada.

---

## 1. O que eles são

Dois produtos numa conta só:

| Produto | O que é | Preço |
| --- | --- | --- |
| **Extensão do Chrome** | Números em cima de cada vídeo dentro do YouTube | Grátis (com conta Google) |
| **Niche Finder** | O painel que garimpa canais sozinho todo dia | Pro (pago) |
| **MCP** | O Dotti dentro do Claude e do ChatGPT | Pro |

Números que o próprio site publica (`/api/porta` e a home, em 22/10/2026):

- **212.765 canais analisados**, 1.640 nichos e subnichos, **2.134.949 vídeos lidos**
- +1.587 canais novos entraram na semana
- Extensão v2.68.0, **911 usuários**, nota 5,0 na Chrome Web Store
- Garantia de 7 dias, cobrança pela Kiwify, login só com Google

> O `/api/porta` é um endpoint público de vitrine: devolve total de canais, nichos, vídeos **e
> 4 canais de exemplo com foto, nicho, inscritos, média de views e 4 capas**. É o que alimenta a
> prova social da home sem precisar de sessão. O Radar não tem nada equivalente.

**Stack:** JS puro, sem framework, sem bundler. Vários `<script>` soltos e ~25 CSS separados por
tela, cada um com hash de versão na query (`styles.css?v=350bf16f71a8`). Roteamento por hash
(`#nf_visao`). Ou seja: **a mesma escolha de arquitetura do Radar**, só que mais madura e
partida em muito mais arquivos.

---

## 2. Como eles organizam o painel

### 2.1 Abas, e o usuário manda nelas

A ordem das abas vem do servidor em `/api/abertura`:

```
novidades · meu_canal · monitor · galeria · achados · meus_outliers · para_alunos ·
acervo · titulos · oportunidades · nichos · conta · robos · estatisticas · sistema · config · manual
```

E junto vêm quatro campos que são a sacada: `abas_ordem`, `abas_ocultas`, `abas_fixas`,
`subs_ordem`, `subs_ocultos`. **Cada usuário reordena e esconde as abas que quiser**, e isso fica
salvo na conta (não no navegador). `sistema` e `config` são fixas e não somem.

No código (`app.js`) isso aparece como `ABAS_TODAS`, `SUBS_TODOS`, `SUBS_FIXOS`, mais a função
`ordemComOsNovos()`, que insere uma aba nova **na posição vizinha certa** em vez de jogar no fim —
detalhe bonito: quando eles lançam uma tela nova, ela aparece perto das parentes dela, sem bagunçar
a ordem que o usuário montou.

Além disso há três níveis de permissão sobre o mesmo menu:

- `viewDisponivel(nome)` — se o plano/papel abre aquela tela
- `modoDisponivel(pai, modo)` — se abre aquele submodo
- `pcGruposVazios()` — grupo cujos filhos sumiram todos **some sozinho** em vez de ficar vazio

### 2.2 O "recorte" — filtros que viram endereço

O conceito mais aproveitável deles. Cada tela registra um **recorte**
(`window.pcRecorte.registrar("vf", …)`): o conjunto de filtro + ordem + período + base. Esse
recorte:

- vai para a **URL** (`glRecorteParaOEndereco()`) — então um filtro montado é um link que se manda
  para outra pessoa, e o botão Voltar do navegador funciona
- tem **"voltar ao padrão"** por tela (`pcVoltarAoPadrao(chave)`, `pcPadraoDaTela`)
- **não** é guardado em `localStorage` — eles chegaram a usar (`nf_visao`, `nf_ordem_v3`,
  `gl_dias`…) e **removeram de propósito**, com uma lista de limpeza que apaga as chaves velhas do
  navegador de quem já tinha usado:

```js
const PC_RECORTE_DO_NAVEGADOR = [
  "nf_visao", "nf_ordem_v3", "nf_sentido_v3", "nf_fonte", "nf_aval", "nf_robo",
  "na_visao", "na_ordem", "na_sentido", "na_dias", "al_ordem", …
];
PC_RECORTE_DO_NAVEGADOR.forEach((k) => localStorage.removeItem(k));
```

Isto é exatamente o bug que o Radar já levou (o commit `21aa438`, "nicho guardado que sumiu não
filtra escondido"). Eles resolveram tirando o estado do navegador e pondo na URL.

### 2.3 Visões prontas ("réguas")

`/api/abertura` entrega `visoes_ordem`:

```
novo_crescendo · media_alta · virou_a_chave · views_poucos_subs · outliers · tudo · sem_concorrencia
```

São buscas nomeadas e reordenáveis — não filtros que o usuário tem que montar. O endpoint
`/api/acervo/visoes?so_reguas=1` sugere que uma visão é uma **régua** (um critério de medida)
salva, não só um conjunto de checkboxes. O usuário abre o painel e já cai numa pergunta pronta:
"quem é novo e está crescendo", "quem virou a chave", "muita view com poucos inscritos",
"nicho sem concorrência".

### 2.4 Mais coisas de produto no código

- **Pastas / propósito** (`pcPropositoFiltro`, `#gl-pasta`): o usuário organiza a base em pastas e
  filtra por elas. Vários depoimentos citam isso como o que mais ajuda.
- **Base compartilhada** (`/api/channels/quem`, `achou=`): dá para ver **a base de outra pessoa** —
  equipe, aluno, professor. Tem um seletor "a base cujos vídeos esta lista mostra".
- **Área VIP de aluno**: quem comprou o curso Dotti Growth ganha 1 ano de uma aba
  (`para_alunos`) com os nichos que os professores selecionam. Casam curso e ferramenta.
- **Cache de 2 minutos no front** (`PC_MEM_MS = 120000`) para uma lista explícita de 26 endpoints
  "frios", e um **pacote de abertura**: `/api/abertura` devolve de uma vez o que seriam 8 chamadas
  (`eu/base`, `eu/partilha`, `eu/modelar`, `extensao/versao`, `config`…). Uma ida ao servidor em vez
  de nove no carregamento.
- **Telemetria por tela**: todo request leva `X-Painel-Tela` e `X-Painel-Abriu` — eles sabem de que
  tela saiu cada chamada e quais telas o usuário abriu no caminho.
- **Erros em português, com a saída**: `pcPorque(err)` traduz 404/401/403/500 em frases do tipo
  "Esta parte do Dotti Finder ainda não subiu. Feche e abra o Dotti Finder (PARAR.bat e depois
  ABRIR.bat)". Eles também rodam uma versão local (`.bat`), igual ao `LIGAR-RADAR.bat`.
- **Faixa de deploy**: quando o servidor devolve 502/503/504 eles mostram "O Dotti Finder está
  atualizando — volta em instantes" e tentam de novo em 2s, 4s, 8s, 15s, 30s, 30s.
- **Sessão caiu em outra aba**: detectam e recarregam, com aviso.

---

## 3. Como eles procuram vídeos e nichos

### 3.1 Dois buscadores separados, com filtros diferentes

**Canais** → `GET /api/channels?` (`filtros()` + `glFiltros()`):

| Grupo | Parâmetros |
| --- | --- |
| Texto | `busca` |
| Natureza | `tipo_canal`, `painel`, `status`, `saude` |
| Marcadores | `favorito`, `so_outliers`, `foi_novo` |
| Faixas (slider) | `subs`, `mediana`, `views_video`, `views30` |
| Listas | `idioma`, `formato`, `monetizacao` |
| Recorte | `nicho`, `idade_max`, `achou` (de quem é a base), `proposito` (pasta) |
| Saída | `ordem`, `sentido`, `limite`, `com_total=1` |

**Vídeos** → `GET /api/videos?` (`filtrosVideo()`):

```
busca · nicho · achou · proposito/proposito_de · outlier_min · dias · views_min ·
tipo · ordem · sentido · so_novos · so_crescendo · modelar_estado · com_cortados · projeto
```

Pontos que o Radar não tem:

- **`views_min` como trilho (slider), não campo** — e o servidor pode **subir o piso sozinho** e
  avisar na tela ("piso de 50 mil views"). Filtro que se auto-ajusta para a lista não vir vazia.
- **`com_cortados`** — mostrar também o que os filtros cortaram, com o aviso
  "sem Fulano e Beltrano (3.412 vídeos)". O usuário vê **o que está perdendo**.
- **`modelar_estado`** (`fila` / `feito`) — uma esteira: o usuário marca o vídeo que vai modelar e
  depois marca como já modelado. É um kanban mínimo embutido na lista de vídeos.
- **`so_crescendo`** — não é "muitas views", é "está acelerando agora".
- **Paginação por levas** (`pcLevas`, passo de 22 vídeos) com `desloca`, e `com_total=1` só na
  primeira página.

### 3.2 Os cinco critérios de ordenação de vídeo

```js
const ORDENS = {
  recente: "Mais recentes",  popular: "Mais vistos",  antigo: "Mais antigos",
  outlier: "Maior outlier",  vph:     "Views por hora",
};
```

### 3.3 Como os canais entram na base (o diferencial deles)

Três entradas, e duas são automáticas:

1. **Garimpo diário do servidor** — igual ao `garimpo.py` do Radar.
2. **"Seus Canais Acharam"** — *cada canal que o usuário salva vira um garimpeiro*: o sistema
   procura sozinho os parecidos com ele e entrega numa aba própria, já medidos. Quanto mais o
   usuário salva, mais a base dele cresce sem ele procurar. É o recurso mais citado nos
   depoimentos ("salvou um canal, ele puxa os parecidos sozinho e te entrega o ouro").
3. **A extensão, medindo enquanto o usuário navega** — a função `feeds_canal`: ao abrir um canal,
   a extensão lê os números públicos dos vídeos recentes e **manda para o servidor**, no máximo uma
   vez a cada 12 h por canal, só para canais que o Dotti já acompanha. Os usuários são a frota de
   medição. Isso está declarado na lista de funções, com "Nada sobre você".

### 3.4 Nichos

- 1.640 nichos e subnichos; `/api/channels/nichos`, `/api/janela/nichos`, `/api/temas/videos?nicho=`
- **Fase de vida do nicho**: "nascendo, crescendo ou saturado" — item de plano, aparece na extensão
  dentro da página do canal
- `/api/temas/corrigir` — alguém (ou uma IA) corrige a classificação de tema
- **"Esse nicho vale a pena?"** e **"Concorrentes do nicho"** como funções Pro da extensão

---

## 4. A extensão deles

v2.68.0, **30 funções declaradas** na API pública (`/api/extensao/versao?funcoes=1`), 19 anunciadas
como grátis. Lista completa, com o plano de cada uma:

**Grátis:** nota de outlier em cada vídeo · views por hora · reação do público (curtidas e
comentários acima do normal do nicho) · inscritos do canal · status de monetização · dados do canal
com gráficos de views e inscritos (7 e 30 dias) · esconder os Shorts · capa em tamanho real ·
painel lateral do vídeo · painel abre sozinho · tags escondidas do vídeo e do canal · sons dos
gestos · selo Raro/Épico/Lendário · views dos últimos 60 min e 48 h **do canal do próprio usuário**
na barra do YouTube · resumo da busca · copiar título · print do cartão do vídeo · foto com um
clique no Studio · ajudar a medir o canal que você abre.

**Pro/Lite:** filtro dos vídeos da página · provar a capa e o título (põe a sua no meio das reais)
· salvar canal · prateleira de canais novos em alta na home do YouTube · transcrição · vídeos
parecidos · canais parecidos · vídeos do nicho · **Método Malandro** (em que língua ninguém fez
esse vídeo ainda, 9 línguas de uma vez) · "esse nicho vale a pena?".

Três detalhes de produto que valem mais que a lista:

- **A extensão é a isca.** Grátis, sem cartão, só login Google. Ela é a porta de entrada do funil
  inteiro — o site repete "Baixar a extensão grátis" seis vezes antes de falar de preço.
- **O preço não aparece antes do cadastro.** "O preço aparece logo depois do cadastro."
- **A própria extensão publica a lista de funções pela API**, com `chave`, `nome`, `desc` e `plano`.
  A página `/extensao` e a tela de planos são geradas dessa lista — uma fonte só.

---

## 5. Onde o Radar já está igual ou à frente

Não é um retrato de perdedor. O Radar tem coisas que o Dotti **não tem**:

| O Radar tem | O Dotti tem? |
| --- | --- |
| Fábrica de vídeo completa (roteiro com Claude, thumbnail, fila, produção, entrega) | Não — eles param na descoberta e vendem um "robô" à parte |
| Custo real por vídeo, por provedor e por canal | Não |
| Publicação automática no YouTube Studio (detalhes, anúncios, questionário) | Só "anúncios automáticos" |
| Métricas de dono via YouTube Studio conectado (retenção, receita, origem das views) | Só as views 60 min / 48 h |
| Radar de países: traduz a ideia e confere se já foi feita em cada país | O Método Malandro faz parecido, em 9 línguas |
| Treinamento por canal (selo 🎯 nos vídeos que combinam) | Não |
| Garimpo com CPM e engajamento por nicho, e termos que ele aprende sozinho | Não declarado |
| 172 rotas de API, 7.600 linhas de Python com testes | — |

Na extensão, o Radar já tem: canais parecidos, concorrentes do nicho, analisar nicho, copiar
capa/título, esconder Shorts, transcrição, filtros dos vídeos da página, resumo da busca. **O
vocabulário é quase idêntico** ("Canal pequeno que estourou", "Esconder os Shorts", outlier, views
por hora).

---

## 6. O que falta — plano em ordem de retorno

### Faixa A — organização (barato, muda a sensação do produto inteiro)

1. **Filtro na URL, não no `localStorage`.** O recorte de cada tela (filtros + ordem + período +
   nicho) vira query no hash. Resolve de vez a classe de bug do commit `21aa438`, faz o Voltar do
   navegador funcionar e deixa o usuário mandar um link de busca pronta. Depois, apagar as chaves
   velhas do `localStorage` como eles fizeram.
2. **Botão "voltar ao padrão" por tela.** Hoje, quando a lista vem vazia, não há saída óbvia.
3. **Visões prontas.** Em vez de o usuário montar o filtro, dar as perguntas feitas:
   *novo e crescendo · média alta · virou a chave · muita view com poucos inscritos · outliers ·
   sem concorrência*. O Radar já tem as telas (`alta`, `ranking`, `grupos`, `ideias`) — falta
   apresentá-las como visões de uma lista só, em vez de telas separadas no menu.
4. **Menu que o usuário reordena e esconde**, salvo na conta. O menu do Radar tem 3 grupos fixos e
   13 itens; o Dotti tem 17 abas e deixa o usuário mandar nelas.
5. **Grupo vazio some sozinho** (hoje o Radar filtra só `admin`/`integracoes` por flag).

### Faixa B — busca (é onde o Dotti ganha hoje)

6. **"Seus canais acharam".** O recurso mais citado nos depoimentos deles. O Radar já tem
   `/api/salvos` com "cada um procura sozinho os parecidos uma vez por semana" — **falta a aba
   própria** que junta a colheita e mostra "chegaram 12 canais novos esta semana a partir dos seus".
   Isso é retrabalho pequeno em cima do que já existe e é o item de maior retorno da lista.
7. **`com_cortados`: mostrar o que o filtro escondeu.** "sem Fulano e Beltrano (3.412 vídeos)".
   Ensina o usuário a afrouxar o filtro em vez de achar que a base é pequena.
8. **Piso automático de views**, com aviso na tela quando o servidor subir o piso.
9. **Trilho (slider) em vez de campo numérico** para views e inscritos.
10. **`so_crescendo`** como marcador separado de "muitas views".
11. **Esteira de modelagem** (`modelar_estado`): marcar o vídeo que vai modelar e o que já modelou,
    e filtrar por isso. O Radar tem `ideias-salvas`, mas sem o estado "já fiz".
12. **Pastas na base** (`proposito`): o usuário agrupa canais por projeto/canal dele.
13. **Paginação por levas** com total só na primeira página (o Radar carrega listas inteiras).

### Faixa C — extensão

14. **Lista de funções vinda da API**, com `chave`, `nome`, `desc`, `plano`, servindo a página de
    ajuda e a tela de planos de uma fonte só. O Radar tem a tela `extensao` escrita à mão.
15. **Selo de raridade** (Raro · Épico · Lendário) no canal fora da curva. Custa pouco e os
    depoimentos mostram que gamificação funciona nesse público.
16. **Reação do público** — curtidas e comentários acima do normal *do nicho*, não do canal. Sinal
    diferente do outlier de views e o Radar não mede.
17. **Prateleira de canais novos em alta na home do YouTube** (7, 14, 30 dias).
18. **Provar a capa e o título**: pôr a sua thumbnail no meio dos vídeos reais da página. O Radar já
    gera thumbnail — fecha o ciclo de teste.
19. **Print do cartão do vídeo** para colar no WhatsApp. Marketing orgânico de graça.

### Faixa D — desempenho e operação

20. **Pacote de abertura**: uma rota que devolve de uma vez o que hoje são várias chamadas no
    carregamento (`/api/eu`, `/api/cota`, `/api/alertas/novos`, `/api/filtros`…).
21. **Cache curto no front** (2 min) para a lista de endpoints frios.
22. **Erros em português com a saída**, no padrão do `pcPorque`: o Radar roda local, então
    "ligue pelo LIGAR-RADAR.bat" é a mensagem certa para 404/conexão recusada.
23. **Faixa de "atualizando"** com nova tentativa em 2s/4s/8s/15s/30s quando o servidor voltar 5xx.
24. **Telemetria por tela** (`X-Painel-Tela`) se um dia o Radar virar multiusuário.

### Faixa E — se o Radar for virar produto pago

25. **Endpoint de vitrine** no estilo `/api/porta`: total de canais, nichos, vídeos e 4 canais de
    exemplo com capa — alimenta uma home sem login.
26. **Extensão grátis como isca**, painel pago. É o funil deles inteiro.
27. **Preço depois do cadastro.**
28. **Depoimento com print do Studio.** Eles têm 20, todos com número e mês. É o que vende.

---

## 7. O que eu não consegui ver

- As telas por dentro do painel (403 sem sessão): a aparência real do Niche Finder, da galeria, das
  visões e do "Seus Canais Acharam". Tudo o que está aqui sobre elas vem do `app.js`.
- A definição das visões (`/api/acervo/visoes`) e dos filtros (`/api/descoberta/filtros`): sei os
  nomes e os parâmetros, não as regras numéricas por trás.
- O código da extensão: a Chrome Web Store não abre no navegador embutido. A lista de 30 funções
  veio da API pública deles, não do código da extensão.
- Preços: só aparecem depois do cadastro.
