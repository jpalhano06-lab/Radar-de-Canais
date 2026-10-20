// Avisa o site do Radar que a extensão está instalada: com ela, o "Enviar para o ChatGPT/Gemini" cola o prompt e a
// thumbnail sozinho (colar.js). O atributo fica no <html>, que a página consegue ler.
document.documentElement.dataset.radarExtensao = chrome.runtime.getManifest().version;
