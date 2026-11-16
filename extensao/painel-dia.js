// O Meu dia na beirada direita do YouTube (pedido do usuário em 2026-11-14: "aquela aba tem que ir no lugar do Claude,
// pode retirar o Claude"). O painel do Claude e do ChatGPT saiu; no lugar dele, a abinha "Meu dia" e um painel com a
// própria tela do Meu dia (dia.html, num quadro). Abre pela abinha, por dois cliques com o botão direito e pelo Alt+C.
(() => {
  const INTERVALO = 450;           // ms entre os dois cliques direitos
  let ultimo = 0, painel = null, abinha = null;
  const NO_STUDIO = location.hostname === "studio.youtube.com";
  let pendente = "";

  function montar() {
    painel = document.createElement("div");
    painel.className = "radar-dia-painel";
    const cab = document.createElement("div");
    cab.className = "radar-dia-cab";
    const titulo = document.createElement("b");
    titulo.textContent = "Meu dia";
    const aba = document.createElement("button");
    aba.textContent = "Abrir em aba";
    aba.title = "Abrir o Meu dia numa aba própria";
    aba.onclick = () => { try { chrome.runtime.sendMessage({ tipo: "abrir-dia" }); } catch { /* extensão recarregada */ } alternar(false); };
    const fechar = document.createElement("button");
    fechar.textContent = "×";
    fechar.title = "Fechar (Esc)";
    fechar.className = "radar-dia-fechar";
    fechar.onclick = () => alternar(false);
    cab.append(titulo, aba, fechar);
    const quadro = document.createElement("iframe");
    // no Studio o Meu dia tem o "Postar" de cada vídeo (pedido do usuário em 2026-11-15); o `pendente` vem do Postar
    // apertado no YouTube (dia.js guarda diaPostar e abre o Studio) e já começa o upload daquele vídeo
    const postar = pendente; pendente = "";
    // o canal do Studio aberto (2026-11-16): o Postar de um vídeo de outro canal abre o Studio do canal certo
    const canalStudio = NO_STUDIO ? ((location.pathname.match(/\/channel\/(UC[\w-]{22})/) || [])[1] || "") : "";
    quadro.src = chrome.runtime.getURL("dia.html") + "?embutido=1" + (NO_STUDIO ? "&studio=1" : "") + (postar ? `&postar=${postar}` : "")
      + (canalStudio ? `&canalStudio=${canalStudio}` : "");
    quadro.title = "Meu dia";
    quadro.allow = "clipboard-write";
    painel.append(cab, quadro);
    painel.addEventListener("contextmenu", (e) => e.stopPropagation(), true);
    document.body.append(painel);
  }

  function alternar(abrir) {
    if (!painel) montar();
    const aberto = abrir ?? !painel.classList.contains("aberto");
    painel.classList.toggle("aberto", aberto);
    document.documentElement.classList.toggle("radar-dia-ligado", aberto);
    abinha.classList.toggle("escondida", aberto);
  }

  abinha = document.createElement("button");
  abinha.className = "radar-dia-abinha";
  abinha.title = "Meu dia (Alt+C ou dois cliques com o botão direito)";
  abinha.textContent = "Meu dia";
  abinha.onclick = () => alternar(true);
  document.body.append(abinha);

  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && painel && painel.classList.contains("aberto")) alternar(false); });

  // o primeiro clique direito abre o menu normal; o segundo, logo em seguida, fecha esse menu e abre o Meu dia
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

  chrome.runtime.onMessage.addListener((msg) => { if (msg && msg.tipo === "painel-dia") alternar(); });
  // o Meu dia pediu para postar: o painel sai da frente do upload
  window.addEventListener("message", (e) => {
    if (e.origin === new URL(chrome.runtime.getURL("")).origin && e.data && e.data.tipo === "radar-postar" && painel) alternar(false);
  });
  // o Studio redireciona a página inicial e o #endereço se perde no caminho: o pedido vem pelo storage
  const canalAqui = () => (location.pathname.match(/\/channel\/(UC[\w-]{22})/) || [])[1] || "";
  function avisoNoStudio(texto) {
    const a = document.createElement("div");
    a.textContent = texto;
    a.style.cssText = "position:fixed;top:70px;left:50%;transform:translateX(-50%);z-index:2147483647;background:#b00020;color:#fff;"
      + "padding:10px 16px;border-radius:10px;font:600 13px system-ui,sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.4);max-width:520px";
    document.body.append(a);
    setTimeout(() => a.remove(), 12000);
  }
  if (NO_STUDIO) chrome.storage.local.get("diaPostar").then(async ({ diaPostar }) => {
    if (!diaPostar || Date.now() - diaPostar.quando > 5 * 60 * 1000) return;   // a troca de conta antes pode levar um tempo
    // a raiz do Studio leva ao canal da conta: espera o endereço com o canal e confere se é o do vídeo (2026-11-16)
    const fim = Date.now() + 15000;
    while (!canalAqui() && Date.now() < fim) await new Promise((r) => setTimeout(r, 500));
    if (diaPostar.canal && canalAqui() && canalAqui() !== diaPostar.canal) {
      avisoNoStudio("Meu dia: este Studio é de outro canal. Troque de conta e aperte Postar de novo (o vídeo não foi enviado).");
      return;
    }
    chrome.storage.local.remove("diaPostar");
    pendente = diaPostar.id;
    if (painel) { painel.remove(); painel = null; }   // já aberto: monta de novo, com o pedido
    alternar(true);
  }).catch(() => {});
})();
