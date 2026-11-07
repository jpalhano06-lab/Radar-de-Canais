// Faz os pedidos ao servidor do Radar pela página do YouTube: o content script não fala direto com o servidor.
const PADRAO = "http://127.0.0.1:8400";
importScripts("claude-projetos.js");

async function config() {
  const { servidor, token } = await chrome.storage.local.get(["servidor", "token"]);
  return { servidor: (servidor || PADRAO).replace(/\/+$/, ""), token };
}

// Ligar o Radar de novo (ou o Windows acordar) derrubava um pedido e a página ficava sem números até alguém apertar
// F5. Agora o pedido que não chega é tentado mais duas vezes, com uma pausa curta, que é o tempo de o servidor subir.
const TENTATIVAS = 3;
const pausa = (ms) => new Promise((ok) => setTimeout(ok, ms));

async function pedir({ caminho, metodo = "GET", corpo }) {
  const { servidor, token } = await config();
  // sem token vale o acesso livre do Radar neste computador (sem e-mail e senha)
  for (let tentativa = 1; ; tentativa++) {
    try {
      const r = await fetch(servidor + caminho, {
        method: metodo,
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: corpo ? JSON.stringify(corpo) : undefined,
      });
      const dados = await r.json().catch(() => ({}));
      if (r.status === 401) await chrome.storage.local.remove("token");
      // 502/503/504 é o Radar reiniciando: vale esperar e pedir de novo, como se não tivesse chegado
      if ([502, 503, 504].includes(r.status) && tentativa < TENTATIVAS) { await pausa(700 * tentativa); continue; }
      return r.ok ? { dados } : { erro: dados.detail || `Erro ${r.status}`, status: r.status };
    } catch (e) {
      if (tentativa < TENTATIVAS) { await pausa(700 * tentativa); continue; }
      return { erro: "O servidor do Radar não respondeu. Ele está ligado?", status: 0 };
    }
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
  if (msg && msg.tipo === "sincronizar-claude") {   // o botão "Atualizar do claude.ai" do Radar (site.js)
    sincronizarClaude().then(responder);
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

// Alt+S (chrome://extensions/shortcuts): o content.js da aba aberta salva o canal do vídeo ou da página do canal;
// Alt+C: o claude.js abre ou fecha o painel do Claude
chrome.commands.onCommand.addListener(async (comando) => {
  const tipo = { "salvar-canal": "salvar-canal", "abrir-claude": "claude" }[comando];
  if (!tipo) return;
  const [aba] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (aba && /^https:\/\/www\.youtube\.com\//.test(aba.url || "")) chrome.tabs.sendMessage(aba.id, { tipo }).catch(() => {});
});

// Os projetos do claude.ai viram os agentes do Radar (claude-projetos.js): ao abrir o Chrome e a cada meia hora.
// Falhar aqui não tem problema: abrir o claude.ai faz a mesma leitura pela própria página (claude-sync.js)
async function sincronizarClaude() {
  try {
    const r = await sincronizarProjetosClaude("https://claude.ai", (caminho, corpo) => pedir({ caminho, metodo: "POST", corpo }));
    if (!r.erro) await chrome.storage.local.set({ claudeSincronizado: Date.now(), claudeResultado: r.dados });
    return r;
  } catch (e) {
    return { erro: String(e.message || e) + " Abra o claude.ai neste Chrome e tente de novo.", status: 0 };
  }
}
chrome.runtime.onStartup.addListener(() => sincronizarClaude());
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("claude-projetos", { periodInMinutes: 30 });
  sincronizarClaude();
});
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "claude-projetos") sincronizarClaude(); });

// o que precisa de você vira notificação do Chrome (radar/avisos.py). O mesmo aviso só volta depois de 12 horas. Radar fora do
// ar também avisa, mas só na segunda volta seguida: ligar o Radar de novo leva um minuto
const AVISAR_DE_NOVO = 12 * 3600 * 1000;

function notificar(chave, titulo, texto, link = "") {
  chrome.notifications.create(`radar:${chave}:${link}`, { type: "basic", iconUrl: "icones/128.png", title: titulo, message: texto || "" });
}

async function olharAvisos() {
  const guardado = await chrome.storage.local.get(["funcoesDesligadas", "avisosVistos", "radarFora"]);
  if ((guardado.funcoesDesligadas || []).includes("avisos")) return;
  const r = await pedir({ caminho: "/api/ext/avisos" });
  const fora = r.erro && !r.status ? (guardado.radarFora || 0) + 1 : 0;
  await chrome.storage.local.set({ radarFora: fora });
  if (fora === 2) notificar("radar-fora", "O Radar está fora do ar", "A fila e os avisos ficam parados até ligar de novo.");
  if (r.erro) return;
  const vistos = guardado.avisosVistos || {}, agora = Date.now(), atuais = {};
  for (const a of r.dados.avisos || []) {
    atuais[a.chave] = vistos[a.chave] || 0;
    if (agora - atuais[a.chave] > AVISAR_DE_NOVO) { notificar(a.chave, a.titulo, a.texto, a.link); atuais[a.chave] = agora; }
  }
  await chrome.storage.local.set({ avisosVistos: atuais });
}

chrome.runtime.onInstalled.addListener(() => chrome.alarms.create("avisos", { periodInMinutes: 5 }));
chrome.runtime.onStartup.addListener(() => chrome.alarms.create("avisos", { periodInMinutes: 5 }));
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "avisos") olharAvisos(); });
chrome.notifications.onClicked.addListener(async (id) => {
  const { servidor } = await config();
  chrome.tabs.create({ url: `${servidor}/${id.split(":").slice(2).join(":")}` });
  chrome.notifications.clear(id);
});
