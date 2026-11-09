// O botão do Radar dentro do Claude e do ChatGPT: perguntas prontas que usam o MCP do Radar e a ajuda para conectá-lo.
// O botão só escreve na caixa de mensagem. Quem aperta enviar é a pessoa.
(() => {
  if (window.__radarChat) return;
  window.__radarChat = true;

  const COMANDO = "claude mcp add radar -- uv run python -m radar mcp";
  const PERGUNTAS = [
    ["Quais canais salvos estão estourando?", "Use o Radar: quais canais que eu salvei estão estourando esta semana? Mostre os 5 principais e o vídeo que puxou cada um."],
    ["Títulos que rendem no meu nicho", "Use o Radar: nos vídeos que mais passaram do normal no nicho [seu nicho], que padrões de título se repetem? Dê 5 exemplos."],
    ["Analisar um canal", "Use o Radar para analisar este canal: [cole o link]. Leia o canal, os vídeos mais vistos e diga o que ele faz diferente."],
    ["O que o público deste vídeo pede?", "Use o Radar para ler os comentários do vídeo [cole o link] e diga o que o público está pedindo."],
    ["Resumir a fala de um vídeo", "Use o Radar para ler a transcrição do vídeo [cole o link] e resuma em 5 pontos."],
  ];
  const CAIXAS = ["#prompt-textarea", 'div[contenteditable="true"].ProseMirror', 'div[contenteditable="true"]', "textarea"];
  const caixa = () => CAIXAS.map((s) => document.querySelector(s)).find(Boolean);

  function escrever(texto) {
    const c = caixa();
    if (!c) return false;
    c.focus();
    if (c.tagName === "TEXTAREA") {
      c.value = texto;
      c.dispatchEvent(new Event("input", { bubbles: true }));
      return true;
    }
    document.execCommand("selectAll");
    return document.execCommand("insertText", false, texto);
  }

  const novo = (tag, estilo, texto) => {
    const e = document.createElement(tag);
    e.style.cssText = estilo;
    if (texto) e.textContent = texto;
    return e;
  };

  const menu = novo("div", "position:fixed;right:18px;bottom:74px;z-index:2147483000;width:300px;padding:8px;border-radius:12px;background:#151820;color:#eef1f7;"
    + "border:1px solid #262b36;font:13px/1.4 system-ui,sans-serif;box-shadow:0 8px 28px rgba(0,0,0,.4);display:none");
  const item = (texto, acao) => {
    const b = novo("button", "display:block;width:100%;padding:8px;border:0;border-radius:8px;background:none;color:inherit;font:inherit;text-align:left;cursor:pointer", texto);
    b.type = "button";
    b.onmouseenter = () => { b.style.background = "#262b36"; };
    b.onmouseleave = () => { b.style.background = "none"; };
    b.onclick = () => acao(b);
    return b;
  };
  PERGUNTAS.forEach(([rotulo, texto]) => menu.append(item(rotulo, () => {
    menu.style.display = "none";
    if (!escrever(texto)) navigator.clipboard.writeText(texto);
  })));
  menu.append(item("Conectar o Radar ao Claude (copiar o comando)", (b) => {
    navigator.clipboard.writeText(COMANDO);
    b.textContent = "Copiado. Rode na pasta do Radar, com ele ligado.";
  }));

  const botao = novo("button", "position:fixed;right:18px;bottom:24px;z-index:2147483000;padding:8px 14px;border:0;border-radius:999px;background:#ff1f35;color:#fff;"
    + "font:600 13px system-ui,sans-serif;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.35)", "Radar");
  botao.type = "button";
  botao.title = "Perguntas prontas do Radar";
  botao.onclick = () => { menu.style.display = menu.style.display === "none" ? "block" : "none"; };

  chrome.storage.local.get("funcoesDesligadas").then(({ funcoesDesligadas }) => {
    if (!(funcoesDesligadas || []).includes("chat")) document.body.append(menu, botao);
  }).catch(() => {});
})();
