// A ponte do Studio: o studio.js (dentro da página) não acessa a extensão; aqui os números do canal são guardados
// para o youtube.com mostrar (chrome.storage.local, só neste computador).
window.addEventListener("message", (e) => {
  if (e.source !== window || !e.data || e.data.radarStudio !== 1 || !e.data.numeros) return;
  chrome.storage.local.set({ numerosCanal: e.data.numeros });
});
