// Faz os pedidos ao servidor do Radar pela página do YouTube: o content script não fala direto com o servidor.
const PADRAO = "http://127.0.0.1:8400";

async function config() {
  const { servidor, token } = await chrome.storage.local.get(["servidor", "token"]);
  return { servidor: (servidor || PADRAO).replace(/\/+$/, ""), token };
}

async function pedir({ caminho, metodo = "GET", corpo }) {
  const { servidor, token } = await config();
  // sem token vale o acesso livre do Radar neste computador (sem e-mail e senha)
  try {
    const r = await fetch(servidor + caminho, {
      method: metodo,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: corpo ? JSON.stringify(corpo) : undefined,
    });
    const dados = await r.json().catch(() => ({}));
    if (r.status === 401) await chrome.storage.local.remove("token");
    return r.ok ? { dados } : { erro: dados.detail || `Erro ${r.status}`, status: r.status };
  } catch (e) {
    return { erro: "O servidor do Radar não respondeu.", status: 0 };
  }
}

chrome.runtime.onMessage.addListener((msg, _remetente, responder) => {
  if (msg && msg.tipo === "api") {
    pedir(msg).then(responder);
    return true; // resposta assíncrona
  }
  if (msg && msg.tipo === "binario") {        // uma imagem do Radar (a thumbnail de referência), em base64
    binario(msg.caminho).then(responder);
    return true;
  }
  if (msg && msg.tipo === "imagem") {         // a capa do YouTube em base64, para o print do cartão (sem sujar o canvas)
    imagem(msg.url).then(responder);
    return true;
  }
  if (msg && msg.tipo === "radar") {          // abre uma página do Radar (ex.: o Roteiro com o vídeo de referência)
    config().then(({ servidor }) => chrome.tabs.create({ url: servidor + msg.caminho }));
  }
  if (msg && msg.tipo === "abrir") {
    chrome.tabs.create({ url: msg.url });
  }
});

async function imagem(url) {
  if (!/^https:\/\/i\.ytimg\.com\//.test(url || "")) return { erro: "endereço de imagem não aceito" };
  try {
    const r = await fetch(url);
    if (!r.ok) return { erro: `Erro ${r.status}` };
    const bytes = new Uint8Array(await r.arrayBuffer());
    let texto = "";
    for (let i = 0; i < bytes.length; i += 0x8000) texto += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return { base64: btoa(texto), tipo: r.headers.get("content-type") || "image/jpeg" };
  } catch (e) {
    return { erro: "Não consegui baixar a capa." };
  }
}

async function binario(caminho) {
  const { servidor, token } = await config();
  try {
    const r = await fetch(servidor + caminho, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!r.ok) return { erro: `Erro ${r.status}` };
    const bytes = new Uint8Array(await r.arrayBuffer());
    let texto = "";
    for (let i = 0; i < bytes.length; i += 0x8000) texto += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return { base64: btoa(texto), tipo: r.headers.get("content-type") || "image/jpeg" };
  } catch (e) {
    return { erro: "O servidor do Radar não respondeu." };
  }
}

// Alt+S (chrome://extensions/shortcuts): o content.js da aba aberta salva o canal do vídeo ou da página do canal
chrome.commands.onCommand.addListener(async (comando) => {
  if (comando !== "salvar-canal") return;
  const [aba] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (aba && /^https:\/\/www\.youtube\.com\//.test(aba.url || "")) chrome.tabs.sendMessage(aba.id, { tipo: "salvar-canal" }).catch(() => {});
});
