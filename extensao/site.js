// Avisa o site do Radar que a extensão está instalada: com ela, o "Enviar para o ChatGPT/Gemini" cola o prompt e a
// thumbnail sozinho (colar.js). O atributo fica no <html>, que a página consegue ler.
document.documentElement.dataset.radarExtensao = chrome.runtime.getManifest().version;
// o endereço do Meu dia: a aba "Meu dia" do Radar mostra a tela da extensão num quadro (web_accessible_resources)
document.documentElement.dataset.radarDia = chrome.runtime.getURL("dia.html");
// O botão "Atualizar do claude.ai" dos agentes: a página pede pelo postMessage e recebe a resposta do mesmo jeito
window.addEventListener("message", (e) => {
  if (e.source !== window || !e.data || e.data.radar !== "sincronizar-claude") return;
  chrome.runtime.sendMessage({ tipo: "sincronizar-claude" }, (r) =>
    window.postMessage({ radar: "claude-sincronizado", resposta: r || { erro: "A extensão não respondeu." } }, "*"));
});
// O padrão de postagem do canal na página do canal do Radar (pedido do usuário em 2026-11-25: "a opção de publicação
// padrão para certo horário"). É o mesmo `diaConfig[canal].postagem` do Meu dia (dia.js, linhaDoPadrao): a página
// lê e grava por aqui, e o background segue fazendo o resto (dia-dados.js põe a hora nos vídeos, o postar sozinho
// abre o Studio quando o vídeo fica pronto)
window.addEventListener("message", async (e) => {
  if (e.source !== window || !e.data || !/^padrao-postagem-(ler|guardar)$/.test(e.data.radar || "")) return;
  const canal = String(e.data.canal || "");
  let resposta;
  try {
    if (!canal) throw new Error("Sem o canal.");
    const { diaConfig = {} } = await chrome.storage.local.get("diaConfig");
    const atual = diaConfig[canal] || {};
    if (e.data.radar === "padrao-postagem-guardar") {
      diaConfig[canal] = { ...atual, postagem: { ...(atual.postagem || {}), ...(e.data.postagem || {}) } };
      await chrome.storage.local.set({ diaConfig });
    }
    const c = diaConfig[canal] || {};
    resposta = { postagem: c.postagem || {}, porDia: c.porDia || 0 };
  } catch (erro) { resposta = { erro: String(erro.message || erro) }; }
  window.postMessage({ radar: "padrao-postagem", pedido: e.data.pedido, resposta }, "*");
});
