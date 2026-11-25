// Faz os pedidos ao servidor do Radar pela página do YouTube: o content script não fala direto com o servidor.
const PADRAO = "http://127.0.0.1:8400";
importScripts("claude-projetos.js", "dia-dados.js");

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

// o registro da troca de conta do "procurar ideia" (o mesmo diaTrocaLog do content.js)
// em fila (filaTrocaLog): várias abas gravando juntas apagavam as linhas umas das outras
let filaTrocaLog = Promise.resolve();
function registrarTrocaBg(passo, url = "background") {
  const linha = { t: new Date().toISOString(), url, passo };
  filaTrocaLog = filaTrocaLog.then(async () => {
    const { diaTrocaLog = [] } = await chrome.storage.local.get("diaTrocaLog");
    await chrome.storage.local.set({ diaTrocaLog: [...diaTrocaLog.slice(-59), linha] });
  }).catch(() => {});
}

// abre o YouTube ao lado da aba do clique (na mesma janela: sem windowId ia para a última janela em foco, às vezes
// escondida atrás, onde o YouTube não desenha o menu) e guarda pelo id da aba a conta para trocar e, se houver, para
// onde ir depois (content.js pede com "troca-pendente")
async function abrirParaTrocar(de, alvo, depois) {
  // `de` vazio é o postar sozinho (sem aba de origem): abre na janela em foco
  const aba = await chrome.tabs.create({ url: "https://www.youtube.com/", active: true,
    ...(de && de.windowId >= 0 ? { windowId: de.windowId, index: de.index + 1 } : {}) });
  const { trocasPorAba = {} } = await chrome.storage.session.get("trocasPorAba");
  trocasPorAba[aba.id] = { alvo, depois, quando: Date.now() };
  await chrome.storage.session.set({ trocasPorAba });
  registrarTrocaBg(`aba ${aba.id} aberta para ${alvo}${depois ? ` (depois: ${depois})` : ""}`);
  return aba;
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
  if (msg && msg.tipo === "abrir-dia") abrirDia();       // o "Abrir em aba" do painel do YouTube e o ícone (popup)
  if (msg && msg.tipo === "dia-postado") {               // publicou no Studio: fica verde no Meu dia (publicar.js)
    diaMarcarPostado(msg).then(async (id) => {
      // o postar sozinho acabou bem: libera o próximo
      const { autoPostando } = await chrome.storage.local.get("autoPostando");
      if (autoPostando && (autoPostando.id === id || autoPostando.id === msg.id)) await chrome.storage.local.remove("autoPostando");
      registrarTrocaBg(`postado no Studio: "${msg.titulo}" → ${id || "não achei no Meu dia"}`); responder({ ok: true, id }); },
      (e) => responder({ erro: String(e) }));
    return true;
  }
  // o "procurar ideia" do Meu dia (2026-11-15, terceira volta do bug): o pedido de troca de conta ia para o storage e a
  // primeira aba do YouTube que carregasse levava, que nem sempre era a aba aberta pelo botão. Agora o background abre
  // a aba e guarda o pedido pelo id dela: só ela pega (content.js pede com "troca-pendente")
  // o Postar do Meu dia (2026-11-16): abria o Studio na conta que estivesse aberta. Agora é o caminho do procurar
  // ideia com a conta do próprio canal e, depois da troca, o Studio dele; o pedido de postar (diaPostar) ou de só abrir
  // o upload (diaAbrirUpload) espera lá
  if (msg && msg.tipo === "postar-no-canal") {
    // vai para a raiz do Studio, que abre o canal da conta da aba: o endereço /channel/<id> direto, logo depois da
    // troca, deu "Oops" no teste com João o Lobo (2026-11-16). O painel do Studio confere o canal antes de subir
    const pedido = msg.id ? { diaPostar: { id: msg.id, quando: Date.now(), canal: msg.canalId || "" } } : msg.soAbrir ? {} : { diaAbrirUpload: Date.now() };
    chrome.storage.local.set(pedido).then(() => abrirParaTrocar(_remetente.tab, msg.canalNome, "https://studio.youtube.com/"))
      .then(() => responder({ ok: true }), (e) => responder({ erro: String(e) }));
    return true;
  }
  if (msg && msg.tipo === "procurar-ideia") {
    abrirParaTrocar(_remetente.tab, msg.alvo, "").then(() => responder({ ok: true }), (e) => responder({ erro: String(e) }));
    return true;
  }
  if (msg && msg.tipo === "canva-canal") {             // a caixinha do Canva: o canal escolhido para o PNG baixado
    mandarDoCanva(_remetente.tab && _remetente.tab.id, msg.canal).then(responder, (e) => responder({ erro: String(e) }));
    return true;
  }
  if (msg && msg.tipo === "troca-log") { registrarTrocaBg(msg.passo, `aba ${_remetente.tab ? _remetente.tab.id : "?"} ${msg.url || ""}`); return; }
  if (msg && msg.tipo === "troca-pendente") {
    const id = _remetente.tab && _remetente.tab.id;
    chrome.storage.session.get("trocasPorAba").then(async ({ trocasPorAba = {} }) => {
      const p = trocasPorAba[id];
      if (p) { delete trocasPorAba[id]; await chrome.storage.session.set({ trocasPorAba }); }
      if (p) registrarTrocaBg(`aba ${id} pegou o pedido ${p.alvo}`);
      responder(p && Date.now() - p.quando < 2 * 60 * 1000 ? { alvo: p.alvo, depois: p.depois || "" } : {});
    });
    return true;
  }
  if (msg && msg.tipo === "radar-endereco") {            // o Meu dia baixa o vídeo da fábrica direto do Radar (dia.js)
    config().then(responder);
    return true;
  }
  if (msg && msg.tipo === "dia-video") {                 // um pedido da Nova produção entra no Meu dia (content.js)
    diaNovoVideo(msg.video).then(() => responder({ ok: true }), (e) => responder({ erro: String(e) }));
    return true;
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
// Alt+C: o painel-dia.js abre ou fecha o Meu dia na beirada do YouTube
chrome.commands.onCommand.addListener(async (comando) => {
  const tipo = { "salvar-canal": "salvar-canal", "abrir-claude": "painel-dia" }[comando];
  if (!tipo) return;
  const [aba] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (aba && /^https:\/\/(www|studio)\.youtube\.com\//.test(aba.url || "")) chrome.tabs.sendMessage(aba.id, { tipo }).catch(() => {});
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
  if (id.startsWith("radar:dia-")) { chrome.notifications.clear(id); return abrirDia(); }
  const { servidor } = await config();
  chrome.tabs.create({ url: `${servidor}/${id.split(":").slice(2).join(":")}` });
  chrome.notifications.clear(id);
});

// A % do vídeo em produção no ícone da extensão, no canto do Chrome (pedido do usuário em 2026-11-09). Com mais de um,
// o ícone mostra o mais atrasado e a dica (passar o mouse) lista todos. Nada produzindo: o ícone fica limpo.
async function olharProgresso() {
  const r = await pedir({ caminho: "/api/ext/progresso" });
  const videos = (r.dados && r.dados.videos) || [];
  await chrome.storage.local.set({ progresso: videos });
  if (!videos.length) {
    await chrome.action.setBadgeText({ text: "" });
    await chrome.action.setTitle({ title: "Radar de Canais" });
    return;
  }
  const parado = videos.find((v) => v.estado === "precisa_voce");
  const menor = videos.reduce((a, v) => (v.pct < a.pct ? v : a), videos[0]);
  await chrome.action.setBadgeBackgroundColor({ color: parado ? "#f5b301" : "#ff0000" });
  await chrome.action.setBadgeText({ text: parado ? "!" : `${menor.pct}%` });
  await chrome.action.setTitle({ title: videos.map((v) => `${v.estado === "precisa_voce" ? "parou" : `${v.pct}%`} · ${v.titulo}`).join("\n") });
}
chrome.runtime.onInstalled.addListener(() => { chrome.alarms.create("progresso", { periodInMinutes: 1 }); olharProgresso(); });
chrome.runtime.onStartup.addListener(() => { chrome.alarms.create("progresso", { periodInMinutes: 1 }); olharProgresso(); });
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "progresso") { olharProgresso().catch(() => {}); olharPostarSozinho().catch(() => {}); } });

// ------------------------------------------------------------ postar sozinho (pedido do usuário em 2026-11-24)
// "Uma opção no Meu dia: quando tudo estiver pronto e só faltar o vídeo, o Radar posta quando o vídeo ficar pronto".
// O vídeo marcado (v.auto), com thumbnail e agendamento no futuro, é conferido a cada minuto na fábrica; pronto, abre
// o Studio do canal (o mesmo caminho do Postar) com o pedido `auto`, e o publicar.js faz as etapas e agenda. Um de
// cada vez: `autoPostando` segura os outros até o atual acabar (ou 25 minutos, se a aba morrer no meio).
const AUTO_SEGURA = 25 * 60 * 1000;
const agendaValida = (v) => /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(v.agendar || "") && new Date(v.agendar).getTime() > Date.now() + 5 * 60 * 1000;

async function olharPostarSozinho() {
  await diaAplicarPadroes().catch(() => 0);   // os vídeos novos ganham a hora e o postar sozinho do padrão do canal
  const { autoPostando, [DIA_AMANHA]: fila = [] } = await chrome.storage.local.get(["autoPostando", DIA_AMANHA]);
  if (autoPostando && Date.now() - autoPostando.quando < AUTO_SEGURA) return;
  const hoje = await lerDia();
  const candidatos = [...hoje.videos, ...fila].filter((v) => v.auto && !v.postado && !v.autoFalhou && v.thumb && v.canal && v.canalNome && agendaValida(v));
  for (const v of candidatos) {
    const r = await pedir({ caminho: `/api/ext/postar?titulo=${encodeURIComponent(v.titulo || "")}` });
    if (!(r.dados && r.dados.pronto)) continue;
    await chrome.storage.local.set({ autoPostando: { id: v.id, titulo: v.titulo, quando: Date.now() },
      diaPostar: { id: v.id, quando: Date.now(), canal: v.canal, auto: true } });
    registrarTrocaBg(`postar sozinho: "${v.titulo}" pronto na fábrica, abrindo o Studio de ${v.canalNome}`);
    notificar(`dia-auto-${v.id}`, "Radar: postando sozinho", `"${v.titulo}" ficou pronto. Abrindo o Studio de ${v.canalNome} para agendar.`);
    await abrirParaTrocar(null, v.canalNome, "https://studio.youtube.com/");
    return;
  }
}

/** O Studio contou como acabou o postar sozinho (publicar.js e painel-dia.js). */
async function fimDoAuto({ id, ok, motivo = "" }) {
  await chrome.storage.local.remove("autoPostando");
  if (!id) return;
  if (ok) {
    // agendado, mas alguma etapa reclamou no caminho (ex.: os anúncios não couberam): avisa para conferir
    if (motivo) notificar(`dia-auto-aviso-${id}`, "Radar: agendado, confira", motivo.slice(0, 250));
    return;
  }
  await diaMudarVideo(id, (v) => { v.autoFalhou = motivo || "parou no Studio"; });
  notificar(`dia-auto-falhou-${id}`, "Radar: não postei sozinho", `${motivo || "Parou no Studio"}. O vídeo não foi agendado: confira no Meu dia.`);
}
chrome.runtime.onMessage.addListener((msg, _remetente, responder) => {
  if (msg && msg.tipo === "auto-fim") { fimDoAuto(msg).then(() => responder({ ok: true }), (e) => responder({ erro: String(e) })); return true; }
});

// ------------------------------------------------------------ Meu dia (dia.html, dia-dados.js)
// A aba abre uma vez só: chamar de novo traz para a frente a que já está aberta
async function abrirDia() {
  const url = chrome.runtime.getURL("dia.html");
  try {
    const [aberta] = await chrome.runtime.getContexts({ contextTypes: ["TAB"], documentUrls: [url] });
    if (aberta && aberta.tabId >= 0) {
      const aba = await chrome.tabs.update(aberta.tabId, { active: true });
      if (aba) await chrome.windows.update(aba.windowId, { focused: true });
      return;
    }
  } catch (e) { /* Chrome antigo sem getContexts: abre outra */ }
  chrome.tabs.create({ url });
}

// O menu do botão direito numa imagem, em qualquer site (Canva, Drive, uma aba com a imagem aberta): "Salvar no Meu
// dia" e, dentro, os canais (pedido do usuário em 2026-11-14: "a opção salvar no Meu dia e a opção do canal, e aí fica
// como feito"). Escolher o canal marca a thumbnail dele como feita. Refeito quando o dia ou a lista de canais muda.
const MENU_THUMB = "dia-thumb";
async function canaisDoDia() {
  const { diaCanais } = await chrome.storage.local.get("diaCanais");
  if (diaCanais && diaCanais.length) return diaCanais;
  const r = await pedir({ caminho: "/api/meus-canais" });
  if (r.erro) return [];
  const canais = (r.dados.canais || []).map((c) => ({ id: c.id, titulo: c.titulo }));
  await chrome.storage.local.set({ diaCanais: canais });
  return canais;
}
async function montarMenuDoDia() {
  const [dia, canais] = await Promise.all([lerDia(), canaisDoDia()]);
  await chrome.contextMenus.removeAll();
  chrome.contextMenus.create({ id: MENU_THUMB, title: "Salvar no Meu dia", contexts: ["image"] });
  for (const c of canais) {
    const feita = dia.thumbs.some((t) => t.canal === c.id) || dia.videos.some((v) => v.canal === c.id && v.thumb);
    const falta = dia.videos.some((v) => v.canal === c.id && !v.thumb);
    chrome.contextMenus.create({ id: `${MENU_THUMB}:c:${c.id}`, parentId: MENU_THUMB, contexts: ["image"],
      title: `${c.titulo}${falta ? "  (falta a thumbnail)" : feita ? "  (já tem thumbnail)" : ""}` });
  }
  chrome.contextMenus.create({ id: `${MENU_THUMB}:sep`, parentId: MENU_THUMB, contexts: ["image"], type: "separator" });
  chrome.contextMenus.create({ id: `${MENU_THUMB}:`, parentId: MENU_THUMB, contexts: ["image"], title: "Sem canal (escolho depois)" });
  chrome.contextMenus.create({ id: "dia-abrir", title: "Abrir o Meu dia", contexts: ["page", "image"] });
}
let menuEsperando = null;
const refazerMenu = () => { clearTimeout(menuEsperando); menuEsperando = setTimeout(() => montarMenuDoDia().catch(() => {}), 200); };
chrome.runtime.onInstalled.addListener(refazerMenu);
chrome.runtime.onStartup.addListener(refazerMenu);
chrome.storage.onChanged.addListener((mudou, area) => { if (area === "local" && (mudou[DIA_CHAVE] || mudou.diaCanais)) refazerMenu(); });

const paraDataUrl = (bytes, tipo) => {
  let texto = "";
  for (let i = 0; i < bytes.length; i += 0x8000) texto += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return `data:${tipo || "image/png"};base64,${btoa(texto)}`;
};

// A imagem do clique: primeiro pela própria página (serve para blob:, para o mesmo site e para quem libera), depois
// pela extensão. Sem nenhum dos dois, a pessoa arrasta a imagem para o Meu dia
async function baixarImagemDoMenu(info, tab) {
  const url = info.srcUrl || "";
  if (url.startsWith("data:image/")) return url;
  if (tab && tab.id >= 0) {
    try {
      const [r] = await chrome.scripting.executeScript({
        target: { tabId: tab.id, frameIds: [info.frameId || 0] },
        func: async (u) => {
          try {
            const b = await (await fetch(u)).blob();
            if (!/^image\//.test(b.type)) return null;
            return await new Promise((ok) => { const f = new FileReader(); f.onload = () => ok(f.result); f.onerror = () => ok(null); f.readAsDataURL(b); });
          } catch (e) { return null; }
        },
        args: [url],
      });
      if (r && r.result) return r.result;
    } catch (e) { /* página do Chrome, ou a página não deixou */ }
  }
  try {
    const resp = await fetch(url);
    const tipo = resp.headers.get("content-type") || "";
    if (resp.ok && tipo.startsWith("image/")) return paraDataUrl(new Uint8Array(await resp.arrayBuffer()), tipo);
  } catch (e) { /* o site não deixou */ }
  return null;
}

// ------------------------------------------------------------ Canva: baixou o design, escolhe o canal
// Pedido do usuário em 2026-11-16: "no Canva eu não consigo usar a extensão, não consigo mandar direto para o canal
// correto". No Canva o design não é uma imagem (são camadas na página), então o clique direito não tem o "Salvar no
// Meu dia". Agora, quando um PNG/JPG baixado do Canva termina, aparece no próprio Canva uma caixinha com os canais;
// o clique manda a imagem para o canal no Meu dia, como thumbnail feita.
const canvaPendentes = new Map();   // aba do Canva -> { url, nome }
const ehDoCanva = (u) => { try { return /(^|\.)canva\.com$/i.test(new URL(String(u).replace(/^blob:/, "")).hostname); } catch (e) { return false; } };
chrome.downloads.onChanged.addListener(async (mudou) => {
  if (!mudou.state || mudou.state.current !== "complete") return;
  const [item] = await chrome.downloads.search({ id: mudou.id });
  if (!item) return;
  const url = item.finalUrl || item.url || "";
  const nome = (item.filename || "").split(/[\\/]/).pop();
  const imagem = /^image\/(png|jpe?g|webp)/i.test(item.mime || "") || /\.(png|jpe?g|webp)$/i.test(nome);
  if (!imagem || !(ehDoCanva(url) || ehDoCanva(item.referrer || ""))) return;
  const abas = await chrome.tabs.query({ url: "https://*.canva.com/*" });
  const aba = abas.find((a) => a.active) || abas[0];
  if (!aba) return;
  canvaPendentes.set(aba.id, { url, nome });
  const [dia, canais] = await Promise.all([lerDia(), canaisDoDia()]);
  const lista = canais.map((c) => ({ id: c.id, titulo: c.titulo,
    falta: dia.videos.some((v) => v.canal === c.id && !v.thumb),
    feita: dia.thumbs.some((t) => t.canal === c.id) || dia.videos.some((v) => v.canal === c.id && v.thumb) }));
  try {
    await chrome.scripting.executeScript({ target: { tabId: aba.id }, func: escolherCanalNoCanva, args: [lista, nome] });
  } catch (e) {
    notificar("dia-thumb-erro", "Não consegui abrir a escolha do canal no Canva", "Arraste o arquivo baixado para o Meu dia.");
  }
});

// roda dentro da aba do Canva (chrome.scripting): a caixinha com os canais
function escolherCanalNoCanva(canais, nome) {
  document.getElementById("radar-canva-canal")?.remove();
  const caixa = document.createElement("div");
  caixa.id = "radar-canva-canal";
  caixa.style.cssText = "position:fixed;top:72px;right:16px;z-index:2147483647;width:300px;max-height:70vh;overflow:auto;"
    + "background:#16181d;color:#fff;border:1px solid #333;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.45);"
    + "font:13px/1.35 system-ui,sans-serif;padding:12px";
  const titulo = document.createElement("div");
  titulo.style.cssText = "font-weight:700;margin-bottom:4px";
  titulo.textContent = "Mandar para o Meu dia";
  const sub = document.createElement("div");
  sub.style.cssText = "color:#9aa0a6;font-size:12px;margin-bottom:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
  sub.textContent = nome || "imagem baixada";
  caixa.append(titulo, sub);
  const fechar = () => caixa.remove();
  const botao = (texto, extra, cor, acao) => {
    const b = document.createElement("button");
    b.type = "button";
    b.style.cssText = "display:flex;justify-content:space-between;gap:8px;width:100%;text-align:left;margin:4px 0;padding:8px 10px;"
      + `border-radius:8px;border:1px solid ${cor};background:#1f232b;color:#fff;cursor:pointer;font:inherit`;
    const a = document.createElement("span"); a.textContent = texto;
    b.append(a);
    if (extra) { const e = document.createElement("span"); e.textContent = extra; e.style.cssText = `color:${cor};font-size:11px;white-space:nowrap`; b.append(e); }
    b.onclick = acao;
    return b;
  };
  const mandar = (canal) => {
    caixa.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    sub.textContent = "Mandando…";
    chrome.runtime.sendMessage({ tipo: "canva-canal", canal }).then((r) => {
      sub.textContent = r && r.ok ? `✓ ${r.texto}` : `Não deu: ${(r && r.erro) || "tente arrastar o arquivo para o Meu dia"}`;
      setTimeout(fechar, r && r.ok ? 2500 : 6000);
    }).catch(() => { sub.textContent = "A extensão foi recarregada: baixe de novo."; setTimeout(fechar, 5000); });
  };
  const ordem = [...canais].sort((a, b) => (b.falta - a.falta) || (a.feita - b.feita));
  for (const c of ordem) {
    caixa.append(botao(c.titulo, c.falta ? "falta a thumbnail" : c.feita ? "já tem" : "", c.falta ? "#f5b301" : c.feita ? "#2ecc71" : "#333", () => mandar(c.id)));
  }
  caixa.append(botao("Sem canal (escolho depois)", "", "#333", () => mandar(null)));
  caixa.append(botao("Não mandar", "", "#333", fechar));
  document.body.append(caixa);
  setTimeout(() => { if (caixa.isConnected && !caixa.querySelector("button:disabled")) fechar(); }, 2 * 60 * 1000);
}

async function mandarDoCanva(abaId, canal) {
  const p = canvaPendentes.get(abaId);
  if (!p) return { erro: "não achei o download: baixe de novo" };
  let dados = null;
  try {
    const resp = await fetch(p.url);
    const tipo = resp.headers.get("content-type") || (/\.jpe?g$/i.test(p.nome) ? "image/jpeg" : "image/png");
    if (resp.ok) dados = paraDataUrl(new Uint8Array(await resp.arrayBuffer()), tipo.startsWith("image/") ? tipo : "image/png");
  } catch (e) { /* o endereço do download expirou: tenta pela página */ }
  if (!dados) dados = await baixarImagemDoMenu({ srcUrl: p.url, frameId: 0 }, { id: abaId });
  if (!dados) return { erro: "o Canva não deixou pegar a imagem: arraste o arquivo baixado para o Meu dia" };
  canvaPendentes.delete(abaId);
  const canalNome = canal ? ((await canaisDoDia()).find((c) => c.id === canal) || {}).titulo || "" : "";
  const v = await diaGuardarThumb(dados, { origem: "www.canva.com", nome: p.nome, canal, canalNome });
  return { ok: true, texto: canal ? (v ? `Thumbnail feita: ${canalNome} · "${v.titulo}"` : `Thumbnail feita: ${canalNome}`) : "Guardada no Meu dia, sem canal" };
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "dia-abrir") return abrirDia();
  const id = String(info.menuItemId);
  if (!id.startsWith(MENU_THUMB)) return;
  const canal = id.startsWith(`${MENU_THUMB}:c:`) ? id.slice(`${MENU_THUMB}:c:`.length) : null;
  const dados = await baixarImagemDoMenu(info, tab);
  if (!dados) {
    notificar("dia-thumb-erro", "Não consegui pegar essa imagem", "Abra o Meu dia e arraste a imagem (ou o arquivo baixado) para lá.");
    return;
  }
  let nome = "";
  try { nome = decodeURIComponent(new URL(info.srcUrl).pathname.split("/").pop() || ""); } catch (e) { /* blob: ou data: */ }
  const canalNome = canal ? ((await canaisDoDia()).find((c) => c.id === canal) || {}).titulo || "" : "";
  const v = await diaGuardarThumb(dados, { origem: tab && tab.url ? new URL(tab.url).hostname : "", nome, canal, canalNome });
  notificar("dia-thumb", canal ? `Thumbnail feita: ${canalNome}` : "Thumbnail guardada no Meu dia",
    canal ? (v ? `Marcada como feita em "${v.titulo}".` : "Marcada como feita no cartão do canal.") : "Escolha o canal dela no Meu dia.");
});
