// Na página do claude.ai: lê os projetos dali mesmo (mesma origem, o login vale sempre) e manda para o Radar, no
// máximo a cada 10 minutos. Mudou um projeto e abriu o claude.ai, o agente do Radar já se atualiza.
(async () => {
  const GUARDA = "claudeSincronizado";
  const { [GUARDA]: ultimo } = await chrome.storage.local.get(GUARDA);
  if (ultimo && Date.now() - ultimo < 10 * 60 * 1000) return;
  try {
    const projetos = await lerProjetosClaude("");
    const r = await chrome.runtime.sendMessage({ tipo: "api", caminho: "/api/ext/projetos-claude", metodo: "POST", corpo: { projetos } });
    if (r && !r.erro) await chrome.storage.local.set({ [GUARDA]: Date.now(), claudeResultado: r.dados });
  } catch { /* o Radar desligado ou o claude.ai fora do ar: tenta na próxima página */ }
})();
