// Painel de IA no YouTube (pedido do usuário em 2026-10-20: dois cliques com o botão direito abrem um chat no canto
// direito). Em 2026-10-22 ele ganhou o que o usuário pediu: uma abinha sempre à vista para abrir, duas abas
// (Claude e ChatGPT) e, no Claude, o agente (o "projeto") que ele usa para responder.
//
// - **Claude**: quem responde é o Claude do servidor do Radar (/api/assistente, pela assinatura), sabendo qual
//   página está aberta e, se você escolher, com as instruções de um agente seu (os mesmos do Roteiro, que é onde
//   moram as instruções dos projetos do claude.ai).
// - **ChatGPT**: o chatgpt.com não deixa ser aberto dentro de outro site (X-Frame-Options), então a extensão abre
//   uma janela ao lado e **cola** a pergunta com o contexto da página. Quem aperta enviar é a pessoa (colar.js).
// - O claude.ai inteiro (com os projetos de verdade) abre do mesmo jeito, pelo botão da aba Claude.
(() => {
  const INTERVALO = 450;           // ms entre os dois cliques direitos
  const GUARDA = "claudeConversa";
  const GUARDA_AGENTE = "claudeAgente";
  let ultimo = 0;
  let painel = null, abinha = null;
  let conversa = [];
  let pensando = false;
  let aba = "claude";
  let listaMsgs = null;
  let agentes = [], agente = "";

  const api = (caminho, metodo = "GET", corpo) => new Promise((ok) => {
    try {
      chrome.runtime.sendMessage({ tipo: "api", caminho, metodo, corpo }, (r) => ok(r || { erro: chrome.runtime.lastError ? "A extensão foi recarregada: aperte F5 nesta página." : "sem resposta", status: 0 }));
    } catch { ok({ erro: "A extensão foi recarregada: aperte F5 nesta página.", status: 0 }); }
  });

  // elemento com texto seguro (o YouTube não deixa usar innerHTML)
  function h(tag, attrs = {}, ...filhos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v != null) el.setAttribute(k, v);
    }
    for (const f of filhos.flat()) if (f != null && f !== false) el.append(f instanceof Node ? f : String(f));
    return el;
  }

  // **negrito** vira <b>; o resto fica texto puro
  function texto(t) {
    return String(t).split(/\*\*(.+?)\*\*/g).map((parte, i) => (i % 2 ? h("b", {}, parte) : parte));
  }

  function pagina() {
    const titulo = document.querySelector("ytd-watch-metadata h1, h1.ytd-watch-metadata")?.textContent?.trim()
      || document.title.replace(/ - YouTube$/, "");
    const canal = document.querySelector("ytd-watch-metadata ytd-channel-name a, #owner ytd-channel-name a, "
      + "yt-page-header-view-model h1, #channel-name #text")?.textContent?.trim() || "";
    return { titulo, canal, url: location.href };
  }

  // o que a outra IA precisa saber sobre a página aberta, já que ela não vê a aba
  function contextoDaPagina() {
    const p = pagina();
    return `Estou no YouTube, nesta página: ${p.titulo}${p.canal ? ` (canal ${p.canal})` : ""}\n${p.url}\n\n`;
  }

  // ------------------------------------------------------------ abrir a IA numa janela ao lado
  // (claude.ai e chatgpt.com mandam X-Frame-Options: SAMEORIGIN, então não dá para pôr dentro do YouTube)
  async function abrirAoLado(url, pergunta) {
    if (pergunta) {
      await chrome.storage.local.set({ radarColar: { texto: pergunta, quando: Date.now() } });
      url += (url.includes("#") ? "" : "#") + "radar-colar";
    }
    const largura = Math.min(560, Math.round(screen.availWidth * 0.42));
    window.open(url, "radar-ia", `popup,width=${largura},height=${screen.availHeight - 60},`
      + `left=${screen.availWidth - largura},top=0`);
  }

  // ------------------------------------------------------------ a conversa com o Claude do Radar
  function desenharMensagens() {
    const lista = listaMsgs;
    if (!lista) return;
    lista.replaceChildren(
      ...(conversa.length ? [] : [h("div", { class: "radar-claude-vazio" },
        "Pergunte o que quiser. O Claude sabe qual vídeo ou página está aberta.",
        h("small", {}, "A abinha na beirada, dois cliques com o botão direito ou Alt+C abrem e fecham este painel."))]),
      ...conversa.map((m) => h("div", { class: `radar-claude-msg ${m.papel}${m.erro ? " erro" : ""}` }, texto(m.texto))),
      ...(pensando ? [h("div", { class: "radar-claude-msg assistente pensando" }, "Pensando…")] : []),
    );
    lista.scrollTop = lista.scrollHeight;
    painel.querySelector("button.radar-claude-enviar").disabled = pensando;
  }

  async function enviar() {
    const campo = painel.querySelector("textarea");
    const t = campo.value.trim();
    if (!t || pensando) return;
    if (aba === "chatgpt") { campo.value = ""; return abrirAoLado("https://chatgpt.com/", contextoDaPagina() + t); }
    campo.value = "";
    conversa.push({ papel: "pessoa", texto: t });
    pensando = true;
    desenharMensagens();
    const historico = conversa.filter((m) => !m.erro).map(({ papel, texto }) => ({ papel, texto }));
    const r = await api("/api/assistente", "POST", { mensagens: historico, pagina: pagina(), projeto_id: agente || "" });
    pensando = false;
    conversa.push(r.erro ? { papel: "assistente", texto: r.erro, erro: true } : { papel: "assistente", texto: r.dados.resposta });
    chrome.storage.local.set({ [GUARDA]: conversa.slice(-40) });
    desenharMensagens();
  }

  // ------------------------------------------------------------ o painel
  function trocarAba(nova) {
    aba = nova;
    painel.querySelectorAll(".radar-claude-aba").forEach((b) => b.classList.toggle("ativa", b.dataset.aba === aba));
    painel.querySelector(".radar-claude-barra").style.display = aba === "claude" ? "" : "none";
    painel.querySelector(".radar-claude-enviar").textContent = aba === "chatgpt" ? "Abrir no ChatGPT" : "Enviar";
    painel.querySelector("textarea").placeholder = aba === "chatgpt"
      ? "Escreva e eu abro o ChatGPT ao lado com isto colado…"
      : "Escreva para o Claude… (Enter envia, Shift+Enter pula linha)";
    painel.querySelector(".radar-claude-corpo").replaceChildren(aba === "chatgpt" ? painelChatgpt() : listaMsgs);
    if (aba === "claude") desenharMensagens();
    painel.querySelector("textarea").focus();
  }

  function painelChatgpt() {
    return h("div", { class: "radar-claude-vazio" },
      "O ChatGPT não deixa ser aberto dentro do YouTube, então ele abre numa janela ao lado — já com a sua pergunta e o endereço desta página colados.",
      h("small", {}, "A extensão cola, mas não envia: você confere e aperta enviar."),
      h("button", { class: "radar-claude-abrir", onclick: () => abrirAoLado("https://chatgpt.com/", contextoDaPagina()) },
        "Abrir o ChatGPT ao lado"));
  }

  function barraDoAgente() {
    const sel = h("select", { class: "radar-claude-agente", title: "O agente que o Claude usa para responder",
      onchange: (e) => { agente = e.target.value; chrome.storage.local.set({ [GUARDA_AGENTE]: agente }); } },
      h("option", { value: "" }, "Sem agente"),
      ...agentes.map((a) => h("option", { value: String(a.id), selected: String(a.id) === agente ? "" : null }, a.nome)));
    return h("div", { class: "radar-claude-barra" }, sel,
      h("button", { class: "radar-claude-abrir pequeno", title: "Abre o claude.ai de verdade, com os seus projetos",
        onclick: () => abrirAoLado("https://claude.ai/new", contextoDaPagina()) }, "claude.ai ↗"));
  }

  function montar() {
    const campo = h("textarea", { rows: 3, placeholder: "Escreva para o Claude… (Enter envia, Shift+Enter pula linha)" });
    campo.addEventListener("keydown", (e) => {
      e.stopPropagation();          // não deixa os atalhos do YouTube (k, f, m, espaço...) pegarem a digitação
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); }
      if (e.key === "Escape") alternar(false);
    });
    campo.addEventListener("keyup", (e) => e.stopPropagation());
    campo.addEventListener("keypress", (e) => e.stopPropagation());
    listaMsgs = h("div", { class: "radar-claude-msgs" });
    painel = h("aside", { class: "radar-claude" },
      h("header", { class: "radar-claude-cab" },
        h("div", { class: "radar-claude-abas" },
          h("button", { class: "radar-claude-aba ativa", "data-aba": "claude", onclick: () => trocarAba("claude") }, "Claude"),
          h("button", { class: "radar-claude-aba", "data-aba": "chatgpt", onclick: () => trocarAba("chatgpt") }, "ChatGPT")),
        h("button", { class: "radar-claude-nova", title: "Começar outra conversa", onclick: () => {
          conversa = []; chrome.storage.local.remove(GUARDA); desenharMensagens(); campo.focus();
        } }, "Nova"),
        h("button", { class: "radar-claude-fechar", title: "Fechar (Esc)", onclick: () => alternar(false) }, "×")),
      barraDoAgente(),
      h("div", { class: "radar-claude-corpo" }, listaMsgs),
      h("footer", { class: "radar-claude-pe" }, campo,
        h("button", { class: "radar-claude-enviar", onclick: enviar }, "Enviar")));
    painel.addEventListener("contextmenu", (e) => e.stopPropagation(), true);   // dentro do painel o menu é o normal
    document.body.append(painel);
    chrome.storage.local.get([GUARDA, GUARDA_AGENTE]).then((g) => {
      conversa = g[GUARDA] || [];
      agente = g[GUARDA_AGENTE] || "";
      desenharMensagens();
      carregarAgentes();
    });
  }

  async function carregarAgentes() {
    const r = await api("/api/projetos");
    if (r.erro || !r.dados) return;
    agentes = (r.dados.projetos || []).map((p) => ({ id: p.id, nome: p.nome }));
    painel.querySelector(".radar-claude-barra").replaceWith(barraDoAgente());
  }

  // ------------------------------------------------------------ a abinha na beirada
  function montarAbinha() {
    abinha = h("button", { class: "radar-claude-abinha", title: "Abrir o Claude e o ChatGPT (Alt+C)",
      onclick: () => alternar(true) }, "✦ Claude");
    document.body.append(abinha);
  }

  function alternar(abrir) {
    if (!painel) montar();
    const aberto = abrir ?? !painel.classList.contains("aberto");
    painel.classList.toggle("aberto", aberto);
    document.documentElement.classList.toggle("radar-claude-ligado", aberto);
    if (abinha) abinha.classList.toggle("escondida", aberto);
    if (aberto) setTimeout(() => painel.querySelector("textarea").focus(), 50);
  }

  // O primeiro clique direito abre o menu normal; o segundo, logo em seguida, fecha esse menu e abre o painel.
  window.addEventListener("contextmenu", (e) => {
    if (painel?.contains(e.target)) return;
    const agora = Date.now();
    if (agora - ultimo < INTERVALO) {
      e.preventDefault();
      e.stopImmediatePropagation();
      ultimo = 0;
      document.querySelectorAll(".ytp-contextmenu").forEach((m) => { m.style.display = "none"; });  // o menu do player
      alternar();
    } else {
      ultimo = agora;
    }
  }, true);

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.tipo === "claude") alternar();
  });

  montarAbinha();
})();
