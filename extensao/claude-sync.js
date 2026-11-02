// Na página do claude.ai: lê os projetos dali mesmo (mesma origem, o login vale sempre) e manda para o Radar, no
// máximo a cada 10 minutos. Mudou um projeto e abriu o claude.ai, o agente do Radar já se atualiza.
(async () => {
  const GUARDA = "claudeSincronizado";
  const { [GUARDA]: ultimo } = await chrome.storage.local.get(GUARDA);
  if (ultimo && Date.now() - ultimo < 10 * 60 * 1000) return;
  try {
    const r = await sincronizarProjetosClaude("", (caminho, corpo) => chrome.runtime.sendMessage({ tipo: "api", caminho, metodo: "POST", corpo }));
    if (r && !r.erro) await chrome.storage.local.set({ [GUARDA]: Date.now(), claudeResultado: r.dados });
  } catch { /* o Radar desligado ou o claude.ai fora do ar: tenta na próxima página */ }
})();
