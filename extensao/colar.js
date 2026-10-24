// Cola o prompt e a thumbnail de referência no ChatGPT ou no Gemini (pedido do usuário em 2026-10-15: "na hora que
// enviar para o ChatGPT ou para o Gemini, já vai com o prompt e a thumbnail de referência").
// O Radar abre a página com #radar-envio=ID; aqui a extensão pega o prompt e a imagem no Radar e cola na caixa de
// mensagem. Não envia sozinha: a pessoa confere e aperta enviar.
(() => {
  const m = location.hash.match(/radar-envio=([\w-]+)/);
  const soColar = /radar-colar/.test(location.hash);          // o painel do YouTube guardou a pergunta (claude.js)
  if (!m && !soColar) return;
  history.replaceState(null, "", location.pathname + location.search);   // tira o #radar-envio do endereço

  const pedir = (msg) => new Promise((ok) => chrome.runtime.sendMessage(msg, (r) => ok(r || { erro: "sem resposta" })));
  const CAIXAS = location.host.includes("gemini")
    ? ['rich-textarea div[contenteditable="true"]', ".ql-editor[contenteditable]", 'div[contenteditable="true"]']
    : location.host.includes("claude.ai")
      ? ['div[contenteditable="true"].ProseMirror', 'div[contenteditable="true"]', "textarea"]
      : ["#prompt-textarea", 'div[contenteditable="true"]', "textarea"];

  function avisar(texto, erro = false) {
    const el = document.createElement("div");
    el.textContent = texto;
    el.style.cssText = `position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:2147483647;padding:10px 16px;
      border-radius:12px;font:600 14px system-ui;color:#fff;background:${erro ? "#d70015" : "#0071e3"};box-shadow:0 8px 30px rgba(0,0,0,.3)`;
    document.body.append(el);
    setTimeout(() => el.remove(), 7000);
  }

  async function esperarCaixa() {
    for (let i = 0; i < 60; i++) {
      for (const sel of CAIXAS) {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null) return el;
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    return null;
  }

  function colarImagem(caixa, arquivo) {
    const dt = new DataTransfer();
    dt.items.add(arquivo);
    caixa.focus();
    caixa.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    // reserva: o campo de arquivo da página (aparece no ChatGPT e no Gemini)
    setTimeout(() => {
      const anexou = document.querySelector('img[src^="blob:"], [data-testid*="attachment"], .file-preview, uploader-file-preview');
      const campo = document.querySelector('input[type="file"]');
      if (!anexou && campo) {
        campo.files = dt.files;
        campo.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }, 1500);
  }

  // a pergunta que o painel do YouTube guardou: vale por 2 minutos, para não colar algo de ontem numa aba qualquer
  async function doPainel() {
    const g = await chrome.storage.local.get("radarColar");
    chrome.storage.local.remove("radarColar");
    const guardado = g.radarColar;
    if (!guardado || Date.now() - (guardado.quando || 0) > 120000) return null;
    return { prompt: guardado.texto, imagem: null };
  }

  (async () => {
    let envio;
    if (soColar) {
      const dados = await doPainel();
      if (!dados) return;
      envio = { dados };
    } else {
      envio = await pedir({ tipo: "api", caminho: `/api/ext/envio/${m[1]}` });
    }
    if (envio.erro) return avisar("Radar: " + envio.erro, true);
    const { prompt, imagem } = envio.dados;
    const caixa = await esperarCaixa();
    if (!caixa) {
      await navigator.clipboard.writeText(prompt).catch(() => {});
      return avisar("Radar: não achei a caixa de mensagem. O prompt foi copiado: cole com Ctrl+V.", true);
    }
    if (imagem) {
      const img = await pedir({ tipo: "binario", caminho: imagem });
      if (!img.erro) {
        const bytes = Uint8Array.from(atob(img.base64), (c) => c.charCodeAt(0));
        colarImagem(caixa, new File([bytes], "thumbnail-referencia.jpg", { type: img.tipo || "image/jpeg" }));
        await new Promise((r) => setTimeout(r, 800));
      }
    }
    caixa.focus();
    if (caixa.tagName === "TEXTAREA") {
      caixa.value = prompt;
      caixa.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      document.execCommand("insertText", false, prompt);
    }
    avisar(imagem ? "Radar: prompt e thumbnail de referência colados. Confira e envie." : "Radar: prompt colado. Confira e envie.");
  })();
})();
