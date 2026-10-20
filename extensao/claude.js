// Painel do Claude no YouTube (pedido do usuário em 2026-10-20): dois cliques com o botão direito abrem um chat no
// canto direito. Quem responde é o Claude do servidor do Radar (/api/assistente, pela assinatura), sabendo qual
// página está aberta. Um clique direito só continua abrindo o menu normal.
(() => {
  const INTERVALO = 450;           // ms entre os dois cliques direitos
  const GUARDA = "claudeConversa";
  let ultimo = 0;
  let painel = null;
  let conversa = [];
  let pensando = false;

  const api = (caminho, metodo = "GET", corpo) =>
    new Promise((ok) => chrome.runtime.sendMessage({ tipo: "api", caminho, metodo, corpo }, (r) => ok(r || { erro: "sem resposta" })));

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

  function desenhar() {
    const lista = painel.querySelector(".radar-claude-msgs");
    lista.replaceChildren(
      ...(conversa.length ? [] : [h("div", { class: "radar-claude-vazio" },
        "Pergunte o que quiser. O Claude sabe qual vídeo ou página está aberta.",
        h("small", {}, "Dois cliques com o botão direito abrem e fecham este painel."))]),
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
    campo.value = "";
    conversa.push({ papel: "pessoa", texto: t });
    pensando = true;
    desenhar();
    const historico = conversa.filter((m) => !m.erro).map(({ papel, texto }) => ({ papel, texto }));
    const r = await api("/api/assistente", "POST", { mensagens: historico, pagina: pagina() });
    pensando = false;
    conversa.push(r.erro ? { papel: "assistente", texto: r.erro, erro: true } : { papel: "assistente", texto: r.dados.resposta });
    chrome.storage.local.set({ [GUARDA]: conversa.slice(-40) });
    desenhar();
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
    painel = h("aside", { class: "radar-claude" },
      h("header", { class: "radar-claude-cab" },
        h("b", {}, "Claude"),
        h("button", { class: "radar-claude-nova", title: "Começar outra conversa", onclick: () => {
          conversa = []; chrome.storage.local.remove(GUARDA); desenhar(); campo.focus();
        } }, "Nova conversa"),
        h("button", { class: "radar-claude-fechar", title: "Fechar (Esc)", onclick: () => alternar(false) }, "×")),
      h("div", { class: "radar-claude-msgs" }),
      h("footer", { class: "radar-claude-pe" }, campo,
        h("button", { class: "radar-claude-enviar", onclick: enviar }, "Enviar")));
    painel.addEventListener("contextmenu", (e) => e.stopPropagation(), true);   // dentro do painel o menu é o normal
    document.body.append(painel);
    chrome.storage.local.get(GUARDA).then((g) => { conversa = g[GUARDA] || []; desenhar(); });
  }

  function alternar(abrir) {
    if (!painel) montar();
    const aberto = abrir ?? !painel.classList.contains("aberto");
    painel.classList.toggle("aberto", aberto);
    document.documentElement.classList.toggle("radar-claude-ligado", aberto);
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
})();
