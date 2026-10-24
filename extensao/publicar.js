// A publicação no YouTube Studio feita pela extensão. Começou como painel de copiar-e-colar (2026-10-20) e virou
// automação (2026-10-22). Em 2026-10-23 o painel saiu de vez ("tire também o resto do painel, deixe só o botão"):
// na tela só existe um botão vermelho por etapa, e o que ele faz está decidido no Radar, na tela do canal.
// Em 2026-10-23, pelo jeito do Dotti Finder: o botão entra DENTRO do rodapé do Studio, à esquerda do Voltar e do
// Avançar, em vez de boiar no canto da tela; a monetização liga e já coloca os anúncios de um aperto só (um a
// cada minuto, o padrão fica guardado); a Tela final abre o editor dela sozinha; e os Detalhes marcam sempre
// "Conteúdo alterado ou sintético: Sim", porque os vídeos da fábrica são feitos com IA.
// Ao escolher o vídeo da fábrica ele já escreve título, descrição e tags; a descrição vem no modelo do canal
// (guardado no Radar), sem lista de capítulos, só a sinopse. Quem aperta Publicar continua sendo a pessoa.
(() => {
  if (window.__radarPublicar) return;
  window.__radarPublicar = true;

  const pedir = (msg) => new Promise((ok) => {
    try {
      chrome.runtime.sendMessage(msg, (r) => ok(r || { erro: "A extensão foi atualizada: recarregue esta página (F5)." }));
    } catch {
      ok({ erro: "A extensão foi atualizada: recarregue esta página (F5)." });
    }
  });

  const EXTENSOES = /\.(mp4|mov|mkv|webm|avi|m4v|wmv|flv|mpe?g)$/i;
  const estado = {
    arquivo: "", kit: null, erro: "", carregando: false,
    jaPreencheu: "", trabalhando: "", recado: "", recadoErro: false,
    modoAnuncio: localStorage.getItem("radar-anuncio-modo") || "cada",
    cadaMin: Number(localStorage.getItem("radar-anuncio-cada")) || 1,
    quantos: Number(localStorage.getItem("radar-anuncio-quantos")) || 10,
    telaFinal: localStorage.getItem("radar-tela-final") || "melhor",
  };

  const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

  // ------------------------------------------------------------ o nome do arquivo que está subindo
  function novoArquivo(nome) {
    if (!nome || !EXTENSOES.test(nome) || nome === estado.arquivo) return;
    estado.arquivo = nome;
    buscar(nome);
  }
  document.addEventListener("change", (e) => { const f = e.target && e.target.files && e.target.files[0]; if (f) novoArquivo(f.name); }, true);
  document.addEventListener("drop", (e) => { const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]; if (f) novoArquivo(f.name); }, true);

  // reserva: o nome que o Studio mostra ("Nome do arquivo" na tela de upload e na de edição)
  function arquivoDaTela() {
    const onde = document.querySelector("ytcp-uploads-dialog") || document.querySelector("ytcp-app") || document.body;
    for (const el of onde.querySelectorAll("div, span, a, yt-formatted-string")) {
      if (el.children.length) continue;
      const t = (el.textContent || "").trim();
      if (t.length < 200 && EXTENSOES.test(t)) return t;
    }
    return "";
  }

  // ------------------------------------------------------------ quando aparece
  function telaDePublicar() {
    if (/\/video\/[\w-]{11}\/(edit|monetization)/.test(location.pathname)) return true;
    if (/[?&]d=ud\b/.test(location.search) || /\/videos\/upload/.test(location.pathname)) return true;
    const d = document.querySelector("ytcp-uploads-dialog");
    return !!(d && [...d.querySelectorAll("tp-yt-paper-dialog")].some((x) => x.offsetWidth > 0));
  }

  // ------------------------------------------------------------ mexer na tela do Studio
  // (o Studio é Polymer: o que funciona é focar o campo e "digitar" com insertText, do mesmo jeito que a pessoa faria)
  const visivel = (el) => !!(el && el.offsetWidth + el.offsetHeight > 0 && getComputedStyle(el).visibility !== "hidden");
  const caixa = () => document.querySelector("ytcp-uploads-dialog") || document.querySelector("ytcp-video-editor") || document.body;
  const limpo = (el) => (el.textContent || "").replace(/\s+/g, " ").trim();

  function folhas(re, onde = caixa()) {
    const achados = [];
    for (const el of onde.querySelectorAll("div, span, b, h1, h2, h3, p, yt-formatted-string, tp-yt-paper-item, ytcp-text-label")) {
      if (el.children.length > 1) continue;
      const t = limpo(el);
      if (t && t.length < 120 && re.test(t) && visivel(el)) achados.push(el);
    }
    return achados;
  }
  const temTexto = (re) => folhas(re).length > 0;

  const CLICAVEIS = "button, ytcp-button, tp-yt-paper-button, tp-yt-paper-item, tp-yt-paper-radio-button, #button, [role=button]";
  function botao(re, onde = caixa()) {
    for (const el of onde.querySelectorAll(CLICAVEIS)) {
      if (!visivel(el) || el.disabled || el.getAttribute("aria-disabled") === "true") continue;
      if (re.test(limpo(el))) return el;
    }
    return null;
  }
  function clicar(re, onde) {
    const b = botao(re, onde);
    if (b) b.click();
    return !!b;
  }

  const oQueTem = (el) => String(el.value != null ? el.value : el.textContent || "");

  function escrever(el, texto) {
    el.focus();
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      el.select();
    } else {
      const sel = window.getSelection(), r = document.createRange();
      r.selectNodeContents(el); sel.removeAllRanges(); sel.addRange(r);
    }
    document.execCommand("insertText", false, texto);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // devolve TRUE só quando o texto está mesmo no campo. O execCommand falha calado em alguns campos do Studio, e
  // a extensão vinha dizendo "preenchido: descrição" com o campo vazio — mentira pior do que o erro.
  function digitar(el, texto) {
    if (!el || !texto) return false;
    escrever(el, texto);
    const pedaco = texto.slice(0, 30);
    if (oQueTem(el).includes(pedaco)) return true;
    // segunda tentativa: escrever direto e avisar o Polymer
    if (el.value != null) el.value = texto; else el.textContent = texto;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return oQueTem(el).includes(pedaco);
  }

  // o campo QUE ESTÁ NA TELA: o Studio deixa cópias escondidas do mesmo id pela página, e escrever na escondida
  // era escrever no vazio
  const naTela = (seletor) => [...document.querySelectorAll(seletor)].find(visivel) || null;
  const campoTitulo = () => naTela("#title-textarea #textbox, ytcp-social-suggestions-textbox#title-textarea #textbox");
  const campoDescricao = () => naTela("#description-textarea #textbox, ytcp-social-suggestions-textbox#description-textarea #textbox, ytcp-video-description #textbox, #description-container #textbox");
  const campoTags = () => naTela("#tags-container input, ytcp-form-input-container#tags-container input, #tags-container #text-input");

  // As tags moram atrás do "Mostrar mais" dos Detalhes, e era o campo que mais falhava: o painel clicava uma vez,
  // esperava 700 ms fixos e desistia calado se o Studio ainda estivesse desenhando a seção. Agora ele insiste até o
  // campo aparecer, conferindo de 150 em 150 ms, e o rótulo tem as quatro formas que a tela usa conforme a conta.
  // Clicar de novo com a seção já aberta não faz mal: aberto, o rótulo vira "Mostrar menos" e o clique não acha nada.
  const MAIS_OPCOES = /^(Mostrar mais|Mais opções|Show more|More options)$/i;
  async function abrirAsTags(ate = 5000) {
    const fim = Date.now() + ate;
    for (;;) {
      const tg = campoTags();
      if (tg || Date.now() >= fim) return tg;
      clicar(MAIS_OPCOES);
      await esperar(150);
    }
  }

  // a seção do Studio em volta de um texto: sobe do rótulo até o bloco que tem o controle procurado
  function secaoDe(re, achar) {
    for (const alvo of folhas(re)) {
      let p = alvo.parentElement;
      for (let i = 0; i < 6 && p; i++, p = p.parentElement) {
        if (achar(p)) return p;
      }
    }
    return null;
  }

  function marcar(el, ligado = true) {   // caixinha ou rádio do Polymer
    if (!el) return false;
    const agora = el.checked != null ? el.checked
      : el.getAttribute("aria-checked") === "true" || el.hasAttribute("checked");
    if (!!agora !== ligado) el.click();
    return true;
  }

  // ------------------------------------------------------------ 1. Detalhes: escrever título, descrição e tags
  async function preencherDetalhes({ avancar = false } = {}) {
    estado.trabalhando = "detalhes"; desenhar();
    // chegou aqui sem o vídeo (o nome do arquivo ainda não tinha aparecido): procura agora, sem pedir nada
    if (!estado.kit) await buscar(estado.arquivo || arquivoDaTela());
    const k = estado.kit;
    estado.trabalhando = "detalhes"; desenhar();
    const feitos = [], faltou = [];

    if (k) {
      if (digitar(campoTitulo(), (k.titulo || "").slice(0, 100))) feitos.push("título"); else faltou.push("título");
      await esperar(300);

      if (digitar(campoDescricao(), (k.descricao || "").slice(0, 5000))) feitos.push("descrição"); else faltou.push("descrição");
      await esperar(300);
    }

    const naoCriancas = document.querySelector("tp-yt-paper-radio-button[name=VIDEO_MADE_FOR_KIDS_NOT_MFK]")
      || folhas(/^Não,? não é conteúdo (feito )?para crianças|^Não é conteúdo para crianças|not made for kids/i)
        .map((e) => e.closest("tp-yt-paper-radio-button")).filter(Boolean)[0];
    if (naoCriancas) { marcar(naoCriancas); feitos.push("não é para crianças"); } else faltou.push("público (crianças)");

    const tg = await abrirAsTags();
    const tags = k ? tagsQueCabem(k.tags || []) : [];
    if (!tags.length) faltou.push(k ? "tags (a fábrica não mandou nenhuma para este vídeo)" : "tags");
    else if (!tg) faltou.push("tags (não abriu o Mostrar mais a tempo — abra e aperte de novo)");
    else if (digitar(tg, tags.join(", "))) { tg.blur(); feitos.push(`${tags.length} tags`); }
    else faltou.push("tags");

    await esperar(300);
    if (marcarIA()) feitos.push("uso de IA: sim");
    else faltou.push("uso de IA");

    estado.trabalhando = "";
    const daDescricao = !k ? ` Não achei este vídeo na fábrica${estado.arquivo ? ` (${estado.arquivo})` : ""}: título e descrição ficam com você.`
      : k.modelo === "padrao" ? " A descrição está no modelo padrão do Radar: para mudar, escreva o modelo deste canal no Radar."
        : k.modelo ? "" : " A descrição veio da fábrica: para padronizar, escreva o modelo do canal no Radar.";
    // a lista do que o painel marcou e do que ficou para a pessoa: ela confere a tela batendo o olho, sem ler frase
    const lista = [...feitos.map((t) => `✓ ${t}`), ...faltou.map((t) => `✗ ${t}`)].join(" · ");
    recado(`${lista || "nada a preencher"}${faltou.length ? " — o que está com ✗ fica com você." : ""}${daDescricao}`, !k);
    if (avancar) { await esperar(600); proximaEtapa(); }
  }

  // O "Uso de IA" dos Detalhes: sempre Sim (pedido do usuário em 2026-10-23 — os vídeos da fábrica são feitos com
  // IA, então a resposta é a mesma toda vez). O Studio já chamou essa pergunta de "Conteúdo alterado ou sintético";
  // os dois nomes estão aqui porque a tela muda de uma conta para a outra.
  // O "Sim" é exato: o da promoção paga e o das crianças são frases inteiras ("Sim, meu vídeo inclui promoção
  // paga"), e sem o casamento exato a extensão marcaria a resposta errada numa pergunta que não é dela.
  const IA_PERGUNTA = /Uso de IA|A IA foi usada|Conteúdo alterado ou sintético|conteúdo sintético|Altered or synthetic|AI (was )?used|Use of AI/i;

  function marcarIA() {
    const simDaSecao = (p) => [...p.querySelectorAll("tp-yt-paper-radio-button, ytcp-checkbox-lit, tp-yt-paper-checkbox, ytcp-checkbox")]
      .find((r) => visivel(r) && /^(Sim|Yes)$/i.test(limpo(r)));
    const secao = secaoDe(IA_PERGUNTA, simDaSecao);
    return secao ? marcar(simDaSecao(secao), true) : false;
  }

  // ------------------------------------------------------------ 2. Monetização: ligar e marcar todos os anúncios
  async function ligarAnuncios({ avancar = true } = {}) {
    estado.trabalhando = "monetizacao"; desenhar();
    const seletor = [...caixa().querySelectorAll("ytcp-select, tp-yt-paper-dropdown-menu, ytcp-text-dropdown-trigger")].find(visivel);
    if (seletor) {
      seletor.click();
      await esperar(600);
      clicar(/^(Ativad[ao]|Ativar|On|Monetização ativada)$/i, document.body);
      await esperar(600);
    }
    for (const c of caixa().querySelectorAll("ytcp-checkbox-lit, tp-yt-paper-checkbox, ytcp-checkbox")) {
      if (visivel(c) && c.getAttribute("aria-disabled") !== "true") { marcar(c, true); await esperar(120); }
    }
    clicar(/^(Concluído|Concluir|Salvar|Done|Save)$/i);
    await esperar(600);
    estado.trabalhando = "";
    recado("Monetização ativada com todos os tipos de anúncio.");
    if (avancar) { await esperar(400); proximaEtapa(); }
  }

  // o padrão de um aperto só (pedido do usuário em 2026-10-23: "anúncio a cada 1 minuto, ativa e já coloca"):
  // liga a monetização, abre a linha do tempo dos intermediários e põe os espaços, sem mais nenhum clique
  async function ligarEColocarAnuncios() {
    await ligarAnuncios({ avancar: false });
    estado.trabalhando = "anuncios"; desenhar();
    // a linha do tempo dos intermediários abre pelo "Revisar a posição…" da Monetização; em algumas contas ela
    // é a tela seguinte, e aí quem abre é o Avançar
    if (etapaAtual() !== "anuncios") {
      if (!clicar(/Revisar a posição do anúncio|posição do anúncio intermediário|Review midroll|midroll placement/i)) {
        proximaEtapa();
      }
      await esperar(1500);
    }
    await esperarPeloPlayer();
    if (!videoDaTela()) {
      estado.trabalhando = "";
      return recado("Liguei os anúncios. A linha do tempo dos intermediários ainda não carregou (o vídeo costuma "
        + "precisar terminar de processar): quando ela aparecer, aperte o botão de novo.", true);
    }
    await colocarAnuncios();
  }

  // o player da linha do tempo só existe depois que o vídeo processa: vale esperar meio minuto por ele
  async function esperarPeloPlayer(limite = 30000) {
    const fim = Date.now() + limite;
    while (Date.now() < fim) {
      const v = videoDaTela();
      if (v && v.duration > 1) return true;
      estado.trabalhando = `anuncios:esperando ${Math.ceil((fim - Date.now()) / 1000)}s`; desenhar();
      await esperar(500);
    }
    return false;
  }

  // ------------------------------------------------------------ 2b. Anúncios no meio do vídeo (mid-roll)
  const videoDaTela = () => [...document.querySelectorAll("video")].find((v) => v.duration > 1) || null;

  function quantosAnuncios() {
    const v = videoDaTela();
    const dur = v && v.duration ? v.duration : (estado.kit && estado.kit.duracao) || 0;
    if (!dur) return { dur: 0, tempos: [] };
    const passo = estado.modoAnuncio === "cada" ? Math.max(5, estado.cadaMin * 60) : dur / (Math.max(1, estado.quantos) + 1);
    const tempos = [];
    for (let t = passo; t < dur - 20; t += passo) {
      tempos.push(Math.round(t));
      if (estado.modoAnuncio === "quantidade" && tempos.length >= estado.quantos) break;
    }
    return { dur, tempos };
  }

  async function colocarAnuncios() {
    const { dur, tempos } = quantosAnuncios();
    if (!dur) return recado("Não achei a duração do vídeo nesta tela.", true);
    const v = videoDaTela();
    if (!v) return recado("Esta tela não tem o player dos espaços de anúncio.", true);
    estado.trabalhando = "anuncios"; desenhar();
    let postos = 0;
    for (const t of tempos) {
      try { v.currentTime = t; } catch { break; }
      await esperar(400);
      const b = botao(/espaço de anúncio|adicionar espaço|inserir anúncio|ad break|adicionar anúncio|add ad/i);
      if (!b) { recado(`Coloquei ${postos}. Não achei o botão de adicionar espaço de anúncio nesta tela.`, true); break; }
      b.click();
      postos++;
      estado.trabalhando = `anuncios:${postos}/${tempos.length}`; desenhar();
      await esperar(400);
    }
    estado.trabalhando = "";
    if (postos === tempos.length) {
      recado(`${postos} anúncios colocados${estado.modoAnuncio === "cada" ? ` (um a cada ${estado.cadaMin} min)` : ""}.`);
      clicar(/^(Concluído|Concluir|Salvar|Done|Save)$/i);
      await esperar(800);
      proximaEtapa();
    } else if (postos) {
      recado(`Coloquei ${postos} de ${tempos.length}. Confira a linha do tempo e siga você.`, true);
    }
    desenhar();
  }

  // ------------------------------------------------------------ 3. Adequação para anunciantes
  async function responderNadaDisso({ avancar = true } = {}) {
    estado.trabalhando = "anunciantes"; desenhar();
    const nenhuma = folhas(/^Nenhuma das opções( acima)?$|^None of the above$/i)
      .map((e) => e.closest("ytcp-checkbox-lit, tp-yt-paper-checkbox, ytcp-checkbox") || e.parentElement).filter(Boolean)[0];
    if (nenhuma) { marcar(nenhuma, true); await esperar(500); }
    else recado("Não achei o \"Nenhuma das opções\": marque você e clique em Enviar classificação.", true);
    if (clicar(/^(Enviar classificação|Submit rating)$/i)) await esperar(1200);
    estado.trabalhando = "";
    if (nenhuma) recado("Questionário respondido com \"Nenhuma das opções\" — confira se é verdade para este vídeo.");
    if (avancar) proximaEtapa();
  }

  // ------------------------------------------------------------ 4. Elementos: a tela final
  // O padrão é o que o usuário monta à mão (imagem de 2026-10-23): um elemento de vídeo em "Melhor para o
  // espectador" (o YouTube escolhe qual puxa mais) e o "Inscrever-se" do canal. "Importar do último vídeo" fica
  // como a outra opção, para quem já tem uma tela final pronta e só quer repetir. Qual dos dois vale é do canal,
  // guardado no Radar.

  async function abrirTelaFinal() {
    if (botao(BOTAO_ELEMENTO) || botao(/^(Importar do vídeo|Import from video)$/i)) return true;
    // na lista de elementos, a linha "Tela final" tem Adicionar (ou Editar, quando já existe uma)
    const linha = secaoDe(/^Tela final$|^End screen$/i, (p) => botao(/^(Adicionar|Editar|Add|Edit)$/i, p));
    if (!linha) return false;
    botao(/^(Adicionar|Editar|Add|Edit)$/i, linha).click();
    await esperar(2200);
    return !!(botao(BOTAO_ELEMENTO) || botao(/^(Importar do vídeo|Import from video)$/i));
  }

  const BOTAO_ELEMENTO = /^\+?\s*(Elemento|Element)$|^(Adicionar|Add) (elemento|element)$/i;
  const MARCAVEIS = "tp-yt-paper-radio-button, ytcp-checkbox-lit, tp-yt-paper-checkbox, ytcp-checkbox";

  // o rádio cujo rótulo casa, esteja o texto nele mesmo ou num filho
  function radioComTexto(re, onde = caixa()) {
    const direto = [...onde.querySelectorAll(MARCAVEIS)].find((r) => visivel(r) && re.test(limpo(r)));
    return direto || folhas(re, onde).map((e) => e.closest(MARCAVEIS)).filter(Boolean)[0] || null;
  }
  const temElemento = (re) => folhas(re).length > 0;

  // o menu do "+ Elemento" abre fora da caixa do editor, por isso a procura é no documento inteiro
  async function porElemento(tipo) {
    const b = botao(BOTAO_ELEMENTO);
    if (!b) return false;
    b.click();
    await esperar(900);
    const item = botao(tipo, document.body);
    if (!item) return false;
    item.click();
    await esperar(1600);
    return true;
  }

  async function telaFinalPadrao({ avancar = true } = {}) {
    estado.trabalhando = "elementos"; desenhar();
    const feitos = [], faltou = [];
    if (!(await abrirTelaFinal())) {
      estado.trabalhando = "";
      recado("Não achei a Tela final nesta tela.", true);
      if (avancar) proximaEtapa();
      return;
    }
    if (temElemento(/^(Vídeo|Video):/i)) feitos.push("o vídeo que já estava lá");
    else if (await porElemento(/^(Vídeo|Video)$/i)) {
      await esperar(400);
      // o rótulo pode estar no próprio rádio ou num filho dele: procuro dos dois jeitos, senão a opção fica
      // sem marcar e a tela final sai com "Envio mais recente", que não é o que este canal usa
      const melhor = radioComTexto(/Melhor para o espectador|Best for viewer/i);
      if (melhor) { marcar(melhor, true); feitos.push("vídeo: melhor para o espectador"); }
      else faltou.push('a opção "melhor para o espectador"');
    } else faltou.push("o elemento de vídeo");

    if (temElemento(/^(Inscrever-se|Subscribe)/i)) feitos.push("o inscrever-se que já estava lá");
    else if (await porElemento(/^(Inscrição|Inscrever-se|Subscribe)$/i)) feitos.push("inscrever-se");
    else faltou.push("o elemento de inscrição");

    const salvou = clicar(/^(Salvar|Save)$/i);
    await esperar(1200);
    estado.trabalhando = "";
    recado(`Tela final: ${feitos.join(", ") || "nada mudou"}.`
      + (faltou.length ? ` Faça à mão: ${faltou.join(", ")}.` : "")
      + (salvou ? "" : " Não achei o Salvar: confira e salve você."), !!faltou.length || !salvou);
    if (avancar && !faltou.length && salvou) { await esperar(400); proximaEtapa(); }
  }

  // a outra opção: copiar a tela final do último vídeo do canal (é o jeito que o Studio deixa repetir certinho)
  async function telaFinalDoUltimo({ avancar = true } = {}) {
    estado.trabalhando = "elementos"; desenhar();
    await abrirTelaFinal();
    const importar = botao(/^(Importar do vídeo|Import from video)$/i);
    if (!importar) {
      estado.trabalhando = "";
      recado('Não achei o "Importar do vídeo" da Tela final nesta tela.', true);
      if (avancar) proximaEtapa();
      return;
    }
    importar.click();
    await esperar(1800);
    // a janela lista os vídeos do canal, os mais novos primeiro: o primeiro cartão é o último vídeo
    const janela = [...document.querySelectorAll("tp-yt-paper-dialog, ytcp-dialog")].filter(visivel).pop() || document.body;
    const primeiro = [...janela.querySelectorAll("ytcp-video-row, ytcp-ve, #video-list-item, tp-yt-paper-item, img")]
      .filter((e) => visivel(e) && e.offsetWidth > 60)[0];
    if (primeiro) { primeiro.click(); await esperar(1500); }
    const importou = clicar(/^(Importar|Import|Selecionar|Select)$/i, janela);
    await esperar(1500);
    clicar(/^(Salvar|Save)$/i);
    await esperar(800);
    estado.trabalhando = "";
    recado(primeiro && importou ? "Tela final importada do último vídeo. Confira antes de avançar."
      : 'Abri o "Importar do vídeo": escolha o vídeo na janela (não consegui escolher sozinho).', !(primeiro && importou));
    if (avancar && primeiro && importou) proximaEtapa();
  }

  const TELAS_FINAIS = {
    melhor: { rotulo: "Vídeo (melhor para o espectador) + inscrever-se", botao: "Montar a tela final", tarefa: telaFinalPadrao },
    ultimo: { rotulo: "Copiar a do último vídeo", botao: "Tela final do último e pular", tarefa: telaFinalDoUltimo },
    nenhuma: { rotulo: "Não mexer", botao: "Pular esta etapa", tarefa: () => proximaEtapa() },
  };
  const telaFinalEscolhida = () => TELAS_FINAIS[estado.telaFinal] || TELAS_FINAIS.melhor;

  // ------------------------------------------------------------ andar nas etapas
  function proximaEtapa() {
    if (!clicar(/^(Avançar|Próxima|Continuar|Next|Continue)$/i)) recado("Não achei o botão Avançar.", true);
    setTimeout(desenhar, 1200);
  }

  function etapaAtual() {
    if (temTexto(/Espaços de anúncios intermediários|Mid-?roll ad breaks|anúncios intermediários/i)) return "anuncios";
    if (botao(/^(Enviar classificação|Submit rating)$/i) || temTexto(/Adequação (para|a) anunciantes|Advertiser suitability/i)) return "anunciantes";
    if (visivel(campoDescricao())) return "detalhes";
    if (temTexto(/^Monetização$|^Monetization$/i)) return "monetizacao";
    if (temTexto(/Elementos do vídeo|Video elements/i)) return "elementos";
    if (temTexto(/^Verificaç(ão|ões)$|^Checks?$/i)) return "verificacoes";
    return "";
  }

  // ------------------------------------------------------------ o Radar
  async function buscar(arquivo) {
    estado.carregando = true; estado.erro = "";
    desenhar();
    const r = await pedir({ tipo: "api", caminho: `/api/ext/publicar?arquivo=${encodeURIComponent(arquivo || "")}` });
    estado.carregando = false;
    if (r.erro) estado.erro = r.status === 401 ? "Entre na sua conta do Radar pelo ícone da extensão." : r.erro;
    else estado.kit = r.dados.kit;
    desenhar();
    autoPreencher();
  }

  // escolheu o vídeo → título, descrição e tags já vão sozinhos (sem avançar: a pessoa confere antes)
  // o padrão deste canal vem junto com o kit (está guardado no Radar, na tela do canal): minutos entre anúncios
  // e que tela final montar. Sem canal configurado, fica o que a pessoa escolheu por último aqui.
  function pegarOPadraoDoCanal() {
    const p = estado.kit && estado.kit.padrao;
    if (!p) return;
    if (p.anuncio_cada) { estado.cadaMin = p.anuncio_cada; estado.modoAnuncio = "cada"; }
    if (p.tela_final) estado.telaFinal = p.tela_final;
  }

  function autoPreencher() {
    const k = estado.kit;
    pegarOPadraoDoCanal();
    if (!k || estado.jaPreencheu === k.nome || estado.trabalhando) return;
    if (etapaAtual() !== "detalhes") return;
    estado.jaPreencheu = k.nome;
    preencherDetalhes();
  }

  // as tags no formato de colar (o Studio separa nas vírgulas) até caber nos 500 caracteres
  function tagsQueCabem(tags) {
    const saida = [];
    for (const t of tags || []) {
      if ([...saida, t].join(", ").length > 500) break;
      saida.push(t);
    }
    return saida;
  }

  // ------------------------------------------------------------ a barra (num shadow root, o CSS do Studio não entra)
  const host = document.createElement("div");
  host.id = "radar-publicar";
  const raiz = host.attachShadow({ mode: "open" });
  raiz.innerHTML = `<style>
    :host { all: initial; }
    * { box-sizing: border-box; }
    [hidden] { display: none !important; }
    :host(.na-barra) { display: inline-flex; align-items: center; margin-right: 10px; vertical-align: middle; }
    .barra { position: fixed; right: 24px; bottom: 76px; z-index: 2147483647; display: grid; gap: 8px; justify-items: end;
      font: 13px/1.45 Roboto, Arial, sans-serif; color: #eef1f7; }
    /* dentro do rodapé do Studio (ao lado do Voltar e do Avançar): o botão anda com a janela em vez de boiar no canto */
    .barra.na-barra { position: relative; right: auto; bottom: auto; display: inline-flex; }
    /* no rodapé o botão fica à esquerda, então o cartão abre para a direita: ancorado à direita ele saía da tela */
    .barra.na-barra .acima { position: absolute; bottom: calc(100% + 10px); left: 0; right: auto; justify-items: start; }
    .acima { display: grid; gap: 8px; justify-items: end; }
    .acima:empty { display: none; }
    .botoes { display: flex; gap: 1px; }
    .botoes button { border: 0; cursor: pointer; font: 700 13px Roboto, Arial, sans-serif; background: #cc0000; color: #fff;
      padding: 10px 16px; display: flex; align-items: center; gap: 8px; box-shadow: 0 4px 14px rgba(0,0,0,.4); }
    .botoes button:disabled { opacity: .6; cursor: default; }
    .botoes .acao { border-radius: 4px; }
    .botoes button i { width: 15px; height: 11px; border-radius: 3px; background: #fff; flex: none; }
    /* o único cartão que sobrou é o recado: o que foi preenchido e o que falhou */
    .cartao { max-width: 420px; background: #0d0f14; border: 1px solid #262b36; border-radius: 10px; padding: 10px 12px;
      box-shadow: 0 12px 40px rgba(0,0,0,.45); }
    .erro { color: #ff5263; font-size: 12px; }
    .ok { color: #b6f23a; font-size: 12px; }
  </style><div class="barra" hidden></div>`;
  const barra = raiz.querySelector(".barra");

  function el(tag, props = {}, ...filhos) {
    const e = Object.assign(document.createElement(tag), props);
    for (const f of filhos.flat()) if (f != null && f !== false) e.append(f);
    return e;
  }

  function recado(texto, erro = false) {
    estado.recado = texto; estado.recadoErro = erro;
    desenhar();
  }

  // ------------------------------------------------------------ o botão vermelho de cada etapa
  function acaoDaEtapa(etapa) {
    const ocupado = !!estado.trabalhando;
    if (etapa === "detalhes") {
      return { texto: ocupado || estado.carregando ? "Preenchendo…" : "Preencher e pular",
        tarefa: () => preencherDetalhes({ avancar: true }) };
    }
    if (etapa === "monetizacao") {
      const andando = (estado.trabalhando || "").startsWith("anuncios:") ? ` ${estado.trabalhando.split(":")[1]}` : "";
      return { texto: ocupado ? `Ligando e colocando…${andando}` : `Ligar e colocar (1 a cada ${estado.cadaMin} min)`,
        tarefa: () => ligarEColocarAnuncios() };
    }
    if (etapa === "anuncios") {
      const { tempos } = quantosAnuncios();
      const andamento = (estado.trabalhando || "").startsWith("anuncios:") ? ` ${estado.trabalhando.split(":")[1]}` : "";
      return { texto: ocupado ? `Colocando…${andamento}` : `Colocar ${tempos.length} anúncios`, tarefa: () => colocarAnuncios() };
    }
    if (etapa === "anunciantes") return { texto: ocupado ? "Respondendo…" : "Responder “nada disso” e pular", tarefa: () => responderNadaDisso() };
    if (etapa === "elementos") {
      const tf = telaFinalEscolhida();
      return { texto: ocupado ? "Montando…" : tf.botao, tarefa: () => tf.tarefa() };
    }
    if (etapa === "verificacoes") return { texto: "Pular esta etapa", tarefa: () => proximaEtapa() };
    return null;   // quem aperta Publicar é a pessoa
  }

  // ------------------------------------------------------------ desenhar
  // o rodapé do Studio: o bloco que tem o Voltar e o Avançar. É lá que o botão mora, do lado de fora dos dois.
  function rodapeDoStudio() {
    const avancar = botao(/^(Avançar|Próxima|Continuar|Next|Continue)$/i);
    if (!avancar) return null;
    let p = avancar.parentElement;
    for (let i = 0; i < 5 && p; i++, p = p.parentElement) {
      if ([...p.querySelectorAll(CLICAVEIS)].some((b) => /^(Voltar|Back)$/i.test(limpo(b)))) return p;
    }
    return avancar.parentElement;
  }

  function ancorar() {
    const rodape = rodapeDoStudio();
    if (rodape) {
      if (host.parentElement !== rodape) rodape.insertBefore(host, rodape.firstChild);
      host.classList.add("na-barra"); barra.classList.add("na-barra");
    } else {
      // tela sem rodapé (o vídeo ainda processando, a janela de aviso): volta a boiar, senão o botão sumia
      if (host.parentElement !== document.body) document.body.append(host);
      host.classList.remove("na-barra"); barra.classList.remove("na-barra");
    }
  }

  function desenhar() {
    const etapa = telaDePublicar() ? etapaAtual() : "";
    const a = etapa ? acaoDaEtapa(etapa) : null;
    barra.hidden = !etapa;
    if (!etapa) {
      host.classList.remove("na-barra"); barra.classList.remove("na-barra");
      if (host.parentElement !== document.body) document.body.append(host);
      return;
    }
    ancorar();
    const corpo = [];
    if (estado.recado) corpo.push(el("div", { className: "cartao" },
      el("div", { className: estado.recadoErro ? "erro" : "ok", textContent: estado.recado })));

    const principal = a ? el("button", { className: "acao", disabled: !!estado.trabalhando }, el("i"), a.texto) : null;
    if (principal) principal.onclick = a.tarefa;
    barra.replaceChildren(el("div", { className: "acima" }, corpo), el("div", { className: "botoes" }, principal));
  }

  (document.body || document.documentElement).append(host);
  // o Studio troca de tela sem recarregar: confere a cada segundo a etapa e o nome do arquivo
  let ultimo = "", ultimoVideo = "";
  setInterval(() => {
    const video = (location.pathname.match(/\/video\/([\w-]{11})/) || location.search.match(/[?&]udvid=([\w-]{11})/) || [])[1] || "";
    if (video && ultimoVideo && video !== ultimoVideo) {
      estado.arquivo = ""; estado.kit = null; estado.jaPreencheu = ""; estado.recado = ""; desenhar();
    }
    if (video) ultimoVideo = video;
    const agora = telaDePublicar();
    if (agora && !estado.arquivo && !estado.kit) {
      const nome = arquivoDaTela();
      if (nome) novoArquivo(nome);
    }
    if (agora && estado.kit && estado.jaPreencheu !== estado.kit.nome) autoPreencher();
    // O Studio redesenha o rodapé sozinho e o nosso botão vai junto — não é movido, é apagado da página. O
    // elemento continua existindo aqui (com o shadow root dele), então basta pô-lo de volta: sem isto o botão
    // sumia na primeira vez que o Studio mexia na barra e só voltava recarregando a página.
    if (agora && !estado.trabalhando) {
      const rodape = rodapeDoStudio();
      if (!host.isConnected || (rodape && host.parentElement !== rodape)) ancorar();
    }
    const marca = `${agora}|${!!estado.kit}|${estado.recado}|${etapaAtual()}|${estado.trabalhando}`;
    if (marca !== ultimo) { ultimo = marca; desenhar(); }
  }, 1000);
})();
