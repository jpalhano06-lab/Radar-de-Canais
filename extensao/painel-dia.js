// O Meu dia na beirada direita do YouTube (pedido do usuário em 2026-11-14: "aquela aba tem que ir no lugar do Claude,
// pode retirar o Claude"). O painel do Claude e do ChatGPT saiu; no lugar dele, a abinha "Meu dia" e um painel com a
// própria tela do Meu dia (dia.html, num quadro). Abre pela abinha, por dois cliques com o botão direito e pelo Alt+C.
(() => {
  const INTERVALO = 450;           // ms entre os dois cliques direitos
  let ultimo = 0, painel = null, abinha = null;

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
    quadro.src = chrome.runtime.getURL("dia.html") + "?embutido=1";
    quadro.title = "Meu dia";
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
})();
