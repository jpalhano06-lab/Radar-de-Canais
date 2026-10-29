// Avisa o site do Radar que a extensão está instalada: com ela, o "Enviar para o ChatGPT/Gemini" cola o prompt e a
// thumbnail sozinho (colar.js). O atributo fica no <html>, que a página consegue ler.
document.documentElement.dataset.radarExtensao = chrome.runtime.getManifest().version;
// O botão "Atualizar do claude.ai" dos agentes: a página pede pelo postMessage e recebe a resposta do mesmo jeito
window.addEventListener("message", (e) => {
  if (e.source !== window || !e.data || e.data.radar !== "sincronizar-claude") return;
  chrome.runtime.sendMessage({ tipo: "sincronizar-claude" }, (r) =>
    window.postMessage({ radar: "claude-sincronizado", resposta: r || { erro: "A extensão não respondeu." } }, "*"));
});
