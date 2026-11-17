// A aba "Meu dia" (dia.html). Os dados e a virada do dia moram em dia-dados.js.
const $ = (id) => document.getElementById(id);
const api = (caminho) => new Promise((ok) => {
  try { chrome.runtime.sendMessage({ tipo: "api", caminho }, (r) => ok(r || { erro: "sem resposta" })); }
  catch (e) { ok({ erro: String(e) }); }
});

function h(tag, attrs = {}, ...filhos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const f of filhos.flat()) if (f != null && f !== false) el.append(f.nodeType ? f : String(f));
  return el;
}

let canais = [], config = {}, dia = { data: hojeLocal(), videos: [], thumbs: [] }, imagens = {}, erroRadar = "";
let amanha = [];                      // os pedidos guardados para amanhã (dia-dados.js, diaAmanha)
const abertos = new Set();            // os cartões verdes que a pessoa abriu de novo clicando no nome
let destinoArquivo = null;   // quem recebe o arquivo escolhido: o vídeo, { canal } ou null (fica solta)
let colarEm = null;          // o canal sob o mouse: o Ctrl+V cai nele
// dentro da aba Meu dia do site do Radar (o quadro leva ?site=1): o "+ Adicionar thumbnail" de cada canal fica só na
// extensão (pedido do usuário em 2026-11-14)
const NO_SITE = new URLSearchParams(location.search).has("site");
// dentro do painel do YouTube Studio (painel-dia.js leva ?studio=1): o Postar sobe o vídeo ali mesmo
const NO_STUDIO = new URLSearchParams(location.search).has("studio");
let postarAoAbrir = new URLSearchParams(location.search).get("postar") || "";

const hora = (t) => new Date(t).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;

async function guardarConfig(canal, mudanca) {
  const { [DIA_CONFIG]: atual = {} } = await chrome.storage.local.get(DIA_CONFIG);
  atual[canal] = { ...(atual[canal] || {}), ...mudanca };
  await chrome.storage.local.set({ [DIA_CONFIG]: atual });
}

async function carregarImagens() {
  const faltam = dia.thumbs.map((t) => t.id).filter((id) => !(id in imagens));
  if (!faltam.length) return;
  const g = await chrome.storage.local.get(faltam.map((id) => DIA_THUMB + id));
  for (const id of faltam) imagens[id] = g[DIA_THUMB + id] || "";
}

async function recarregar() {
  dia = await lerDia();
  const g = await chrome.storage.local.get([DIA_CONFIG, "diaCanais", DIA_AMANHA]);
  config = g[DIA_CONFIG] || {};
  amanha = g[DIA_AMANHA] || [];
  if (!canais.length) canais = g.diaCanais || [];
  for (const id of Object.keys(imagens)) if (!dia.thumbs.some((t) => t.id === id)) delete imagens[id];
  await carregarImagens();
  desenhar();
}

async function lerCanais() {
  const r = await api("/api/meus-canais");
  if (r.erro) { erroRadar = `Não li os canais do Radar (${r.erro}). Mostrando os da última vez.`; desenhar(); return; }
  erroRadar = "";
  canais = (r.dados.canais || []).map((c) => ({ id: c.id, titulo: c.titulo }));
  chrome.storage.local.set({ diaCanais: canais });
  desenhar();
}

// ------------------------------------------------------------ imagens: arquivo, arrastar e colar
const lerArquivo = (arquivo) => new Promise((ok) => {
  const f = new FileReader(); f.onload = () => ok(f.result); f.onerror = () => ok(null); f.readAsDataURL(arquivo);
});

// `alvo`: { video } para o vídeo, { canal, canalNome } para o canal (fica como feita nele) ou {} para as soltas
const alvoDe = (alvo) => (alvo && typeof alvo === "object" ? alvo : { video: alvo || null });
// as thumbnails que já estão num vídeo: a principal (A) e as do teste A/B (B e C)
const thumbsUsadas = () => new Set(dia.videos.flatMap((v) => [v.thumb, ...(v.ab || [])]).filter(Boolean));
const abAbertos = new Set();   // os vídeos com o teste A/B aberto no cartão

async function guardarDeTransferencia(dt, alvo) {
  alvo = alvoDe(alvo);
  const arquivo = [...(dt.files || [])].find((f) => f.type.startsWith("image/"));
  if (arquivo) {
    const dados = await lerArquivo(arquivo);
    if (dados) return diaGuardarThumb(dados, { nome: arquivo.name, origem: "arquivo", ...alvo });
  }
  // uma imagem arrastada de outra aba vem só com o endereço
  const url = (dt.getData && (dt.getData("text/uri-list") || dt.getData("text/plain")) || "").split("\n")[0].trim();
  if (/^data:image\//.test(url)) return diaGuardarThumb(url, { origem: "arrastada", ...alvo });
  if (/^https?:\/\//.test(url)) {
    try {
      const r = await fetch(url);
      const b = await r.blob();
      if (r.ok && b.type.startsWith("image/")) return diaGuardarThumb(await lerArquivo(b), { origem: new URL(url).hostname, ...alvo });
    } catch (e) { /* o site não deixou */ }
    mostrarErro("Não consegui pegar essa imagem pelo endereço. Salve ela no computador e arraste o arquivo, ou use o botão direito > Salvar no Meu dia.");
  }
}

function zonaDeImagem(el, alvo) {
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("sobre"); });
  el.addEventListener("dragleave", () => el.classList.remove("sobre"));
  el.addEventListener("drop", (e) => { e.preventDefault(); el.classList.remove("sobre"); guardarDeTransferencia(e.dataTransfer, alvo); });
  el.addEventListener("click", () => { destinoArquivo = alvo; $("arquivo").value = ""; $("arquivo").click(); });
  return el;
}
$("arquivo").addEventListener("change", async () => {
  const f = $("arquivo").files[0];
  if (f) { const dados = await lerArquivo(f); if (dados) await diaGuardarThumb(dados, { nome: f.name, origem: "arquivo", ...alvoDe(destinoArquivo) }); }
});
document.addEventListener("paste", (e) => {
  if (e.target.closest && e.target.closest("input")) return;
  if ([...(e.clipboardData.files || [])].some((f) => f.type.startsWith("image/"))) { e.preventDefault(); guardarDeTransferencia(e.clipboardData, colarEm); }
});

function mostrarErro(texto) {
  const el = $("erro");
  el.textContent = texto; el.hidden = !texto;
  if (texto) setTimeout(() => { if (el.textContent === texto) { el.hidden = true; } }, 9000);
}

const baixar = (thumb, titulo) => h("a", { class: "botao", href: imagens[thumb.id] || "#",
  download: `${(titulo || thumb.nome || "thumbnail").replace(/[\\/:*?"<>|]+/g, " ").slice(0, 80)}.${((imagens[thumb.id] || "").match(/^data:image\/(\w+)/) || [, "png"])[1].replace("jpeg", "jpg")}` }, "Baixar");

// ------------------------------------------------------------ as cores (pedido do usuário em 2026-11-15)
// vermelho: nada feito · amarelo: meio caminho (um vídeo postado de 2, o vídeo sem a thumbnail) · verde: tudo certo
const videoCompleto = (v) => !!(v.thumb && v.postado);
// 2026-11-16 (pedido do usuário): "não vou postar nada hoje" deixa o canal verde; azul é quando os vídeos do dia já
// têm pedido e thumbnail e só falta postar; a faixa do canto do cartão se divide em um pedaço por vídeo do dia
const semPostarHoje = (id) => (dia.semPostar || []).includes(id);
const corDoVideo = (v) => (!v ? "falta" : v.postado ? "ok" : v.thumb ? "azul" : "meio");
function faixaDoCanal(meta, videos, semPostar) {
  if (semPostar) return ["ok"];
  const ordem = [...videos].sort((a, b) => (a.hora || 0) - (b.hora || 0));
  const n = Math.max(meta || 0, ordem.length);
  return Array.from({ length: n }, (_, i) => corDoVideo(ordem[i]));
}
function corDoCanal(meta, videos, thumbFeita, semPostar = false) {
  if (semPostar) return "ok";
  const completos = videos.filter(videoCompleto).length;
  const faixa = faixaDoCanal(meta, videos, false);
  if (faixa.length && faixa.every((x) => x === "ok" || x === "azul") && faixa.includes("azul")) return "azul";
  if (!meta) {                       // sem meta ou "não posto todo dia": só ganha cor quando tem o que mostrar
    if (!videos.length) return thumbFeita ? "meio" : "";
    return completos === videos.length ? "ok" : "meio";
  }
  if (!videos.length && !thumbFeita) return "falta";
  return videos.length >= meta && completos === videos.length ? "ok" : "meio";
}
const corDaConta = (feito, total) => (!total ? "" : feito >= total ? "ok" : feito > 0 ? "meio" : "falta");

// ------------------------------------------------------------ a thumbnail de referência
// Pedido do usuário em 2026-11-15: copiar a thumbnail do vídeo de referência (o da Nova produção) para colar no
// ChatGPT/Canva. Só o nome do vídeo aparece; a imagem vai direto para a área de transferência.
const idDoYoutube = (link) => (String(link || "").match(/(?:[?&]v=|youtu\.be\/|shorts\/|embed\/|live\/)([\w-]{11})/) || [])[1] || "";

async function capaDaReferencia(id) {
  for (const tamanho of ["maxresdefault", "sddefault", "hqdefault"]) {
    try {
      const r = await fetch(`https://i.ytimg.com/vi/${id}/${tamanho}.jpg`);
      if (!r.ok) continue;
      // a área de transferência só aceita PNG
      const img = await createImageBitmap(await r.blob());
      const tela = new OffscreenCanvas(img.width, img.height);
      tela.getContext("2d").drawImage(img, 0, 0);
      return await tela.convertToBlob({ type: "image/png" });
    } catch { /* tenta o próximo tamanho */ }
  }
  throw new Error("Não consegui baixar a thumbnail do vídeo de referência.");
}

const COPIAR_REF = "Copiar thumbnail de referência";
async function copiarReferencia(v, botao) {
  const id = idDoYoutube(v.referencia);
  if (!id) return mostrarErro("O link de referência deste vídeo não é de um vídeo do YouTube.");
  botao.disabled = true; botao.textContent = "Copiando…";
  try {
    // a promessa entra direto no ClipboardItem: assim o clique ainda vale quando a imagem chega
    await navigator.clipboard.write([new ClipboardItem({ "image/png": capaDaReferencia(id) })]);
    botao.textContent = "✓ Copiada";
  } catch (e) {
    botao.textContent = COPIAR_REF;
    mostrarErro(`Não copiei a thumbnail de referência: ${(e && e.message) || e}`);
  } finally {
    botao.disabled = false;
    setTimeout(() => { if (botao.textContent === "✓ Copiada") botao.textContent = COPIAR_REF; }, 4000);
  }
}

function linhaDaReferencia(v) {
  if (!v.referencia) return null;
  const botao = h("button", { type: "button", class: "ref-copiar", title: "Copia a thumbnail do vídeo de referência (cole com Ctrl+V)" }, COPIAR_REF);
  botao.onclick = () => copiarReferencia(v, botao);
  return h("div", { class: "ref" }, h("span", { class: "ref-nome", title: v.referencia }, `Ref.: ${v.referenciaTitulo || v.referencia}`), botao);
}

// ------------------------------------------------------------ o Postar (pedido do usuário em 2026-11-15)
// No Studio, sobe o vídeo da fábrica e a thumbnail do Meu dia de uma vez (publicar.js recebe e põe nos campos). Fora
// dele, abre o Studio com o pedido guardado: o Meu dia de lá começa sozinho.
const pedirAoFundo = (msg) => new Promise((ok) => { try { chrome.runtime.sendMessage(msg, (r) => ok(r || {})); } catch { ok({}); } });
const nomeDeArquivo = (t) => (t || "video").replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 120) || "video";
let postando = "";

// o Postar do canal que ainda não tem vídeo pedido: só abre o upload do Studio
// o Studio do canal certo (2026-11-16): fora do Studio, ou no Studio de outro canal, o background abre uma aba, troca
// para a conta do canal e segue para o Studio dele, onde o pedido (postar este vídeo ou só abrir o upload) espera
const CANAL_DO_STUDIO = new URLSearchParams(location.search).get("canalStudio") || "";
const noStudioDoCanal = (canal) => NO_STUDIO && (!canal || !CANAL_DO_STUDIO || CANAL_DO_STUDIO === canal);
function abrirNoCanal(canal, canalNome, id) {
  return pedirAoFundo({ tipo: "postar-no-canal", canalId: canal || "", canalNome: canalNome || "", id: id || "" });
}

async function abrirUpload(canal, canalNome) {
  if (noStudioDoCanal(canal)) return window.parent.postMessage({ tipo: "radar-abrir-upload" }, "https://studio.youtube.com");
  if (canal && canalNome) return abrirNoCanal(canal, canalNome, "");
  window.open("https://studio.youtube.com/", "_blank");
  await chrome.storage.local.set({ diaAbrirUpload: Date.now() });
}

async function postar(v, botao, canal) {
  if (!v) return abrirUpload(canal && canal.id, canal && canal.titulo);
  if (!noStudioDoCanal(v.canal)) {
    if (v.canal && v.canalNome) return abrirNoCanal(v.canal, v.canalNome, v.id);
    window.open("https://studio.youtube.com/", "_blank");
    await chrome.storage.local.set({ diaPostar: { id: v.id, quando: Date.now() } });
    return;
  }
  if (postando) return;
  postando = v.id;
  if (!botao) desenhar();             // começou sozinho: o botão do vídeo mostra "Baixando…"
  const texto = (t) => { if (botao) botao.textContent = t; };
  try {
    texto("Procurando na fábrica…");
    const r = await api(`/api/ext/postar?titulo=${encodeURIComponent(v.titulo || "")}`);
    if (r.erro) throw new Error(`O Radar não respondeu (${r.erro}).`);
    if (!r.dados.nome) throw new Error(`Não achei "${v.titulo}" na fábrica. Suba o vídeo pelo Criar do Studio.`);
    if (!r.dados.pronto) throw new Error("A fábrica ainda não terminou este vídeo.");
    const { servidor, token } = await pedirAoFundo({ tipo: "radar-endereco" });
    const resp = await fetch(`${servidor}/api/ext/postar/${encodeURIComponent(r.dados.nome)}/video`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!resp.ok) throw new Error(`O Radar não entregou o vídeo (erro ${resp.status}).`);
    const total = Number(resp.headers.get("content-length")) || r.dados.tamanho || 0;
    const leitor = resp.body.getReader(), pedacos = [];
    let veio = 0;
    for (;;) {
      const { done, value } = await leitor.read();
      if (done) break;
      pedacos.push(value); veio += value.length;
      texto(total ? `Baixando ${Math.round((veio / total) * 100)}%` : `Baixando ${Math.round(veio / 1048576)} MB`);
    }
    const video = new File(pedacos, `${nomeDeArquivo(r.dados.titulo || v.titulo)}.mp4`, { type: "video/mp4" });
    const thumb = v.thumb && imagens[v.thumb];
    let capa = null;
    if (thumb) {
      const bloco = await (await fetch(thumb)).blob();
      capa = new File([bloco], `${nomeDeArquivo(v.titulo)}.${(bloco.type.split("/")[1] || "png").replace("jpeg", "jpg")}`, { type: bloco.type || "image/png" });
    }
    // o teste A/B (2026-11-16): com as thumbnails B e C, o Studio monta o "Testar e comparar" sozinho
    const capasAB = [];
    for (const [i, idAB] of (v.ab || []).entries()) {
      if (!imagens[idAB]) continue;
      const b = await (await fetch(imagens[idAB])).blob();
      capasAB.push(new File([b], `${nomeDeArquivo(v.titulo)} ${"BC"[i]}.${(b.type.split("/")[1] || "png").replace("jpeg", "jpg")}`, { type: b.type || "image/png" }));
    }
    texto("Abrindo o upload…");
    window.parent.postMessage({ tipo: "radar-postar", id: v.id, titulo: v.titulo, video, capa, capasAB }, "https://studio.youtube.com");
  } catch (e) {
    mostrarErro((e && e.message) || String(e));
  } finally {
    postando = "";
    setTimeout(desenhar, 1500);
  }
}

// ------------------------------------------------------------ quanto falta na fábrica
// Pedido do usuário em 2026-11-15: "sempre tem que avisar quanto falta do vídeo para ficar pronto". O background lê o
// progresso da fábrica a cada minuto (progresso, /api/ext/progresso); o vídeo é achado pelo título. Fora da lista
// (terminou ou nem começou), o Radar diz se o vídeo já está pronto (/api/ext/postar), uma vez por minuto no máximo
let progresso = [];
const prontoNaFabrica = {};   // id do vídeo -> { pronto, achou, quando, buscando }
async function lerProgresso() { ({ progresso = [] } = await chrome.storage.local.get("progresso")); }
const tituloNormal = (t) => String(t || "").normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
function linhaDaFabrica(v) {
  const p = progresso.find((x) => tituloNormal(x.titulo) === tituloNormal(v.titulo));
  if (p) {
    const pct = Math.max(0, Math.min(100, Math.round(p.pct || 0)));
    const parado = p.estado === "precisa_voce";
    return h("div", { class: `fabrica${parado ? " parado" : ""}`, title: p.mensagem || "" },
      h("div", { class: "fabrica-barra" }, h("span", { style: `width:${pct}%` })),
      h("span", { class: "fabrica-texto" }, parado ? `Fábrica parada em ${pct}%: precisa de você` : `Fábrica: ${pct}% · falta ${100 - pct}%`,
        p.mensagem && !parado ? h("span", { class: "fraco" }, ` · ${p.mensagem.replace(/(\.{3}|…)$/, "")}`) : null));
  }
  const r = prontoNaFabrica[v.id];
  if ((!r || Date.now() - r.quando > 60 * 1000) && !(r && r.buscando)) {
    prontoNaFabrica[v.id] = { ...(r || {}), buscando: true, quando: (r && r.quando) || 0 };
    api(`/api/ext/postar?titulo=${encodeURIComponent(v.titulo || "")}`).then((x) => {
      prontoNaFabrica[v.id] = { pronto: !!(x.dados && x.dados.pronto), achou: !!(x.dados && x.dados.nome), quando: Date.now() };
      desenhar();
    }, () => { prontoNaFabrica[v.id] = { quando: Date.now() }; });
  }
  if (!r || r.pronto == null) return null;
  if (r.pronto) return h("div", { class: "fabrica ok" }, "✓ Vídeo pronto na fábrica: é só postar");
  if (r.achou) return h("div", { class: "fabrica" }, "Fábrica: na fila, ainda não começou");
  return null;
}

// ------------------------------------------------------------ teste A/B
// Pedido do usuário em 2026-11-16: "coloque na extensão a opção de teste A/B e quando for pedido para postar faça
// automático". A thumbnail do vídeo é a A; aqui entram a B e a C. No Postar, o Studio abre o "Testar e comparar"
// (Thumbnail only) e põe as três (publicar.js)
function linhaDoTesteAB(v, thumb) {
  const ab = (v.ab || []).filter((id) => imagens[id]);
  if (!ab.length && !abAbertos.has(v.id)) {
    return h("button", { type: "button", class: "ab-abrir", title: "Testar 2 ou 3 thumbnails no Studio (Testar e comparar)",
      onclick: () => { abAbertos.add(v.id); desenhar(); } }, "+ Teste A/B");
  }
  const tirar = (id) => mudarDia((d) => { const x = d.videos.find((y) => y.id === v.id); if (x) x.ab = (x.ab || []).filter((y) => y !== id); });
  const mini = (letra, id) => id
    ? h("div", { class: "ab-slot cheio", title: `Thumbnail ${letra}` }, h("img", { src: imagens[id], alt: "" }),
      h("span", { class: "ab-letra" }, letra),
      h("button", { type: "button", class: "ab-x", title: `Tirar a thumbnail ${letra}`, onclick: (e) => { e.stopPropagation(); tirar(id); } }, "×"))
    : zonaDeImagem(h("div", { class: "ab-slot", title: `Arraste ou clique para escolher a thumbnail ${letra}` }, h("span", { class: "ab-letra" }, letra), "+"), { ab: v.id });
  const aviso = !thumb ? "Ponha a thumbnail A (a principal) também."
    : ab.length ? `No Postar, o Studio monta o teste com ${ab.length + 1} thumbnails sozinho.` : "Arraste a B (e a C, se quiser).";
  return h("div", { class: "ab" },
    h("div", { class: "ab-cab" }, h("b", {}, "Teste A/B"), h("span", { class: "fraco" }, aviso),
      !ab.length ? h("button", { type: "button", class: "x", title: "Fechar o teste A/B", onclick: () => { abAbertos.delete(v.id); desenhar(); } }, "×") : null),
    h("div", { class: "ab-slots" },
      thumb ? h("div", { class: "ab-slot cheio a", title: "Thumbnail A (a principal)" }, h("img", { src: imagens[thumb.id], alt: "" }), h("span", { class: "ab-letra" }, "A")) : null,
      mini("B", ab[0]), mini("C", ab[1])));
}

// ------------------------------------------------------------ tirar e pegar de volta (2026-11-16)
// "Sem querer eu excluí o vídeo que pedi": o × leva o vídeo para "Tirados hoje" (com Desfazer na hora), e cada canal
// mostra os pedidos de hoje da fábrica que não estão no Meu dia, com "Pôr de volta"
let desfazer = null;   // { id, titulo, ate }
async function tirarVideo(v) {
  await diaTirarVideo(v.id);
  desfazer = { id: v.id, titulo: v.titulo, ate: Date.now() + 10000 };
  setTimeout(() => { if (desfazer && Date.now() >= desfazer.ate) { desfazer = null; desenhar(); } }, 10100);
}
function avisoDesfazer() {
  if (!desfazer || Date.now() >= desfazer.ate) return null;
  const id = desfazer.id;
  return h("div", { class: "desfazer" }, h("span", {}, `Tirei "${desfazer.titulo}".`),
    h("button", { type: "button", onclick: () => { desfazer = null; diaVoltarVideo(id); } }, "Desfazer"));
}
let pedidosFabrica = [], pedidosLidos = 0;
function lerPedidosDaFabrica() {
  if (Date.now() - pedidosLidos < 60 * 1000) return;
  pedidosLidos = Date.now();
  api("/api/ext/pedidos-recentes?horas=36").then((r) => {
    if (r && r.dados && Array.isArray(r.dados.pedidos)) { pedidosFabrica = r.dados.pedidos; desenhar(); }
  }, () => {});
}
const meiaNoiteLocal = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d.getTime(); };
function foraDoMeuDia(c) {
  const no = new Set([...dia.videos, ...amanha].map((v) => tituloNormal(v.titulo)));
  return pedidosFabrica.filter((p) => p.canal_id === c.id && Date.parse(p.criado) >= meiaNoiteLocal() && !no.has(tituloNormal(p.titulo)));
}
function linhaForaDoMeuDia(c) {
  const fora = foraDoMeuDia(c);
  if (!fora.length) return null;
  return h("div", { class: "fora" }, h("b", {}, "Pedido hoje na fábrica, fora do Meu dia:"),
    ...fora.map((p) => h("div", { class: "fora-item" }, h("span", { class: "fora-titulo", title: p.titulo }, p.titulo),
      h("button", { type: "button", title: "Volta para o Meu dia de hoje", onclick: () => diaVoltarDaFabrica({ canal: c.id, canalNome: c.titulo,
        titulo: p.titulo, link: p.link, fila: p.id }) }, "Pôr de volta"))));
}
function secaoTirados() {
  const lista = [...(dia.tirados || [])].reverse();
  if (!lista.length) return [];
  return [h("h2", {}, "Tirados hoje"),
    h("section", { class: "tirados" }, ...lista.map((v) => h("div", { class: "tirado" },
      h("span", { class: "fraco" }, v.canalNome || ""), h("span", { class: "fora-titulo", title: v.titulo }, v.titulo || "vídeo sem título"),
      h("button", { type: "button", onclick: () => diaVoltarVideo(v.id) }, "Voltar"))))];
}
// a legenda das cores (pedido do usuário em 2026-11-16: "dentro do Meu dia coloque as cores e explique o que cada uma
// significa")
const legenda = () => h("div", { class: "legenda" },
  ...[["falta", "Vídeo ainda não pedido"], ["meio", "Pedido, falta a thumbnail"], ["azul", "Pedido e thumbnail: só falta postar"],
    ["ok", "Postado (ou hoje sem postar)"]].map(([cor, texto]) => h("span", { class: "leg" }, h("i", { class: `pedaco ${cor}` }), texto)));

// ------------------------------------------------------------ desenho
// 2026-11-16 (pedido do usuário: "deixe a caixinha de dentro na cor, deixe mais claro que cada um é de cada cor"):
// cada caixinha de vídeo tem a cor dela e o número dela (1, 2…), o mesmo dos pedacinhos no alto do canal
const NOME_DA_COR = { falta: "ainda não pedido", meio: "falta a thumbnail", azul: "só falta postar", ok: "postado" };
function cartaoDoVideo(v, numero) {
  const thumb = v.thumb && dia.thumbs.find((t) => t.id === v.thumb);
  const slot = thumb && imagens[thumb.id]
    ? h("div", { class: "slot cheio", title: "Arraste outra imagem para trocar" }, h("img", { src: imagens[thumb.id], alt: "" }))
    : h("div", { class: "slot", title: "Arraste a imagem, ou clique para escolher o arquivo" }, "Arraste a thumbnail aqui");
  zonaDeImagem(slot, v.id);
  const postado = h("input", { type: "checkbox" }); postado.checked = !!v.postado;
  postado.onchange = () => mudarDia((d) => { const x = d.videos.find((y) => y.id === v.id); if (x) x.postado = postado.checked; });
  const estadoTexto = v.postado && thumb ? "✓ Vídeo · ✓ thumbnail · ✓ postado"
    : thumb ? "✓ Vídeo pedido · ✓ thumbnail feita · falta postar"
      : `✓ Vídeo pedido${v.entrada ? " (na Entrada)" : ""} · falta a thumbnail${v.postado ? " · ✓ postado" : ""}`;
  const fabrica = v.postado ? null : linhaDaFabrica(v);
  const testeAB = v.postado ? null : linhaDoTesteAB(v, thumb);
  const botaoPostar = v.postado ? null : h("button", { type: "button", class: "vermelho postar",
    title: NO_STUDIO ? "Sobe o vídeo da fábrica e a thumbnail no Studio" : "Abre o YouTube Studio já com o vídeo e a thumbnail" },
  postando === v.id ? "Baixando…" : NO_STUDIO ? "Postar" : "Postar ↗");
  if (botaoPostar) botaoPostar.onclick = () => postar(v, botaoPostar);
  return h("div", { class: `video ${corDoVideo(v)}` }, numero ? h("span", { class: "num", title: NOME_DA_COR[corDoVideo(v)] }, String(numero)) : null, slot,
    h("div", {},
      v.veioDe && v.veioDe !== dia.data ? h("span", { class: "veio-de", title: "Não foi postado no dia dele: passou para hoje" },
        `↪ de ${v.veioDe.slice(8, 10)}/${v.veioDe.slice(5, 7)}`) : null,
      h("b", {}, v.titulo || "vídeo sem título"),
      h("div", { class: `estado ${videoCompleto(v) ? "ok" : "falta"}` }, estadoTexto),
      fabrica,
      linhaDaReferencia(v),
      testeAB,
      h("div", { class: "acoes" },
        botaoPostar,
        h("label", { class: "check" }, postado, "Postado"),
        h("span", { class: "fraco" }, hora(v.hora)),
        thumb ? baixar(thumb, v.titulo) : null,
        thumb ? h("button", { class: "x", title: "Tirar a thumbnail deste vídeo (ela fica nas soltas)",
          onclick: () => mudarDia((d) => { const x = d.videos.find((y) => y.id === v.id); if (x) x.thumb = null; }) }, "↺") : null,
        v.postado ? null : h("button", { type: "button", class: "mudar-dia", title: "Passa este vídeo para amanhã (com a thumbnail)",
          onclick: () => diaHojeParaAmanha(v.id).then(recarregar) }, "Para amanhã"),
        h("button", { class: "x", title: "Tirar este vídeo do dia (fica em Tirados hoje, dá para voltar)",
          onclick: () => tirarVideo(v) }, "×"))));
}

// o "procurar ideia": abre o YouTube e a extensão troca para a conta de treino (content.js). Pelo #radar-conta= do
// link, o YouTube perdia o endereço no carregamento; pelo storage (diaTrocarConta), outra aba do YouTube podia pegar o
// pedido. Agora o background abre a aba e entrega o pedido só para ela (procurar-ideia / troca-pendente).
// `quando` ("hoje" ou "amanha", pedido do usuário em 2026-11-15) diz para que dia vai o próximo pedido deste canal
async function procurarIdeia(c, treino, quando) {
  const { [DIA_DESTINO]: destinos = {} } = await chrome.storage.local.get(DIA_DESTINO);
  destinos[c.id] = { dia: quando, quando: Date.now() };
  await chrome.storage.local.set({ [DIA_DESTINO]: destinos });
  // o background abre a aba e entrega o pedido só para ela (antes ia pelo storage e outra aba do YouTube podia pegar)
  chrome.runtime.sendMessage({ tipo: "troca-log", url: "Meu dia", passo: `botão procurar ideia: ${treino}` }).catch(() => {});
  chrome.runtime.sendMessage({ tipo: "procurar-ideia", alvo: treino }).catch((e) => alert(`Não consegui abrir o YouTube: ${e}`));
}

// as contas do "Trocar de conta" do YouTube (pedido do usuário em 2026-11-15: "deixe lá todas as opções que tem no
// YouTube, aí só seleciono"). A extensão lê a lista no menu do avatar (content.js) e guarda em contasYoutube
let contasYoutube = [];
async function lerContasYoutube() {
  ({ contasYoutube = [] } = await chrome.storage.local.get("contasYoutube"));
}
const LER_CONTAS = "https://www.youtube.com/#radar-contas-ler";

function cartaoDoCanal(c, videos) {
  const cfg = config[c.id] || {};
  const meta = cfg.porDia;
  const feitos = videos.length, postados = videos.filter((v) => v.postado).length;
  const falta = meta ? Math.max(0, meta - feitos) : 0;

  const escolherMeta = (n) => guardarConfig(c.id, { porDia: n });
  const pergunta = h("div", { class: "pergunta" },
    h("b", {}, "Você pretende postar quantos vídeos por dia neste canal?"),
    h("div", { class: "linha" }, ...[1, 2, 3, 4].map((n) => h("button", { onclick: () => escolherMeta(n) }, String(n))),
      h("button", { onclick: () => escolherMeta(0), title: "O canal não aparece como pendente" }, "Não posto todo dia")));

  // a conta de treino é escolhida na lista das contas do YouTube, agrupada por e-mail. O valor guardado é o @ do canal
  // (ou o nome, nos canais de outros e-mails, que o menu mostra sem @): é com ele que a extensão acha a conta
  const linkTreino = (() => {
    const valorDe = (conta) => conta.handle || conta.nome;
    const atual = cfg.treino || "";
    const porEmail = new Map();
    for (const conta of contasYoutube) {
      if (!porEmail.has(conta.email)) porEmail.set(conta.email, []);
      porEmail.get(conta.email).push(conta);
    }
    // a lista nativa (select) abria branca, com o @ e os e-mails misturados aos nomes (pedido do usuário em
    // 2026-11-15: "só os nomes dos canais, sem o @, e mais bonito"). Agora é um painel do próprio Meu dia: o e-mail
    // é só o título pequeno de cada grupo, e cada conta é o nome com a inicial
    const nomeAtual = (contasYoutube.find((conta) => valorDe(conta) === atual) || {}).nome || atual;
    const inicial = (nome) => [...(nome || "?").trim()][0].toUpperCase();
    const painel = h("div", { class: "contas", hidden: true },
      ...[...porEmail].map(([email, contas]) => h("div", { class: "contas-grupo" },
        h("div", { class: "contas-email" }, email || "Conta do YouTube"),
        h("div", { class: "contas-lista" }, ...contas.map((conta) => {
          const escolhida = valorDe(conta) === atual;
          return h("button", { type: "button", class: `conta${escolhida ? " escolhida" : ""}`, title: conta.handle || conta.nome,
            onclick: () => { painel.hidden = true; guardarConfig(c.id, { treino: valorDe(conta) }); } },
          h("span", { class: "conta-ic" }, inicial(conta.nome)), h("span", { class: "conta-nome" }, conta.nome),
          escolhida ? h("span", { class: "conta-ok" }, "✓") : null);
        })))));
    const escolha = h("button", { type: "button", class: `conta-escolha${atual ? "" : " vazia"}`,
      onclick: (e) => {
        e.stopPropagation();
        if (!contasYoutube.length) return window.open(LER_CONTAS, "_blank");
        painel.hidden = !painel.hidden;
        if (!painel.hidden) document.addEventListener("click", function fora(ev) {
          if (!painel.contains(ev.target)) { painel.hidden = true; document.removeEventListener("click", fora); }
        });
      } },
    atual ? h("span", { class: "conta-ic" }, inicial(nomeAtual)) : null,
    h("span", { class: "conta-nome" }, atual ? nomeAtual : contasYoutube.length ? "Escolher a conta de treino" : "Ler as contas do YouTube"),
    h("span", { class: "conta-seta" }, "▾"));
    return h("div", { class: "conta-treino" }, h("span", { class: "fraco" }, "Conta de treino"),
      h("div", { class: "conta-caixa" }, escolha, painel),
      contasYoutube.length ? h("a", { class: "conta-ler", href: LER_CONTAS, target: "_blank", rel: "noopener",
        title: "Abre o YouTube e lê de novo todas as contas do menu Trocar de conta" }, "↻ Ler as contas de novo") : null);
  })();

  const novoTitulo = h("input", { placeholder: "Título de um vídeo feito fora da Nova produção" });
  const marcar = () => { const t = novoTitulo.value.trim(); novoTitulo.blur(); if (t) diaNovoVideo({ canal: c.id, canalNome: c.titulo, titulo: t }); };
  novoTitulo.addEventListener("keydown", (e) => { if (e.key === "Enter") marcar(); });

  // as thumbnails salvas para o canal pelo botão direito que não entraram num vídeo: ficam aqui, como feitas
  const usadas = thumbsUsadas();
  const doCanal = dia.thumbs.filter((t) => t.canal === c.id && !usadas.has(t.id) && imagens[t.id]);
  const thumbFeita = doCanal.length || videos.some((v) => v.thumb);
  const semPostar = semPostarHoje(c.id);
  const estado = corDoCanal(meta, videos, thumbFeita, semPostar);
  const faixa = faixaDoCanal(meta, videos, semPostar);
  const pedacos = faixa.length > 1 || (faixa.length === 1 && !semPostar) ? h("div", { class: "pedacos" },
    ...faixa.map((cor, i) => h("span", { class: `pedaco ${cor}`, title: `Vídeo ${i + 1}: ${NOME_DA_COR[cor]}` }, String(i + 1)))) : null;
  const ordem = [...videos].sort((a, b) => (a.hora || 0) - (b.hora || 0));
  const numeroDe = (v) => ordem.indexOf(v) + 1;
  // os vídeos da meta que ainda não foram pedidos: uma caixinha vermelha para cada
  const naoPedidos = Array.from({ length: Math.max(0, (meta || 0) - videos.length) }, (_, i) => h("div", { class: "video falta vazio-pedido" },
    h("span", { class: "num" }, String(videos.length + i + 1)), h("div", {}, h("b", {}, `Vídeo ${videos.length + i + 1}`),
      h("div", { class: "estado falta" }, "Ainda não pedido: procure a ideia e faça a Nova produção"))));
  const alternarSemPostar = () => mudarDia((d) => {
    const lista = new Set(d.semPostar || []);
    if (lista.has(c.id)) lista.delete(c.id); else lista.add(c.id);
    d.semPostar = [...lista];
  });
  const cartaoThumb = (t) => h("div", { class: "video" },
    h("div", { class: "slot cheio" }, h("img", { src: imagens[t.id], alt: "" })),
    h("div", {},
      h("div", { class: "estado ok" }, "Thumbnail feita"),
      h("div", { class: "acoes" }, h("span", { class: "fraco" }, `${hora(t.hora)}${t.origem ? " · " + t.origem : ""}`), baixar(t, c.titulo),
        h("button", { class: "x", title: "Apagar esta thumbnail", onclick: async () => {
          await mudarDia((d) => { d.thumbs = d.thumbs.filter((x) => x.id !== t.id); });
          chrome.storage.local.remove(DIA_THUMB + t.id);
        } }, "×"))));

  // a thumbnail entra direto no canal (pedido do usuário em 2026-11-14: soltar lá embaixo e depois escolher o canal era
  // trabalho a mais). Arraste, clique para escolher o arquivo, ou passe o mouse e cole (Ctrl+V)
  const novaThumb = zonaDeImagem(h("div", { class: "solta-zona canal-thumb", tabindex: "0",
    title: "Arraste a imagem, clique para escolher o arquivo, ou passe o mouse aqui e cole (Ctrl+V)" }, "+ Adicionar thumbnail"),
  { canal: c.id, canalNome: c.titulo });
  novaThumb.addEventListener("mouseenter", () => { colarEm = { canal: c.id, canalNome: c.titulo }; });
  novaThumb.addEventListener("mouseleave", () => { colarEm = null; });

  // procurar ideia para hoje ou para amanhã (o próximo pedido deste canal entra no dia escolhido)
  const procurar = cfg.treino
    ? h("div", { class: "linha procurar" }, h("span", { class: "fraco" }, "Procurar ideia:"),
      h("button", { type: "button", title: `Abre o YouTube na conta ${cfg.treino}; o próximo pedido deste canal fica para hoje`,
        onclick: () => procurarIdeia(c, cfg.treino, "hoje") }, "Para hoje ↗"),
      h("button", { type: "button", title: `Abre o YouTube na conta ${cfg.treino}; o próximo pedido deste canal fica para amanhã`,
        onclick: () => procurarIdeia(c, cfg.treino, "amanha") }, "Para amanhã ↗"))
    : null;
  const deAmanha = amanha.filter((v) => v.canal === c.id);
  const listaAmanha = deAmanha.length ? h("div", { class: "amanha" }, ...deAmanha.map((v) => h("div", { class: "amanha-item" },
    h("span", { class: "fraco" }, "Amanhã:"), h("span", { class: "amanha-titulo" }, v.titulo || "vídeo sem título"),
    h("button", { type: "button", class: "mudar-dia", title: "Este pedido é para hoje", onclick: () => diaAmanhaParaHoje(v.id).then(recarregar) }, "Passar para hoje"),
    h("button", { class: "x", title: "Tirar este pedido de amanhã", onclick: async () => {
      const { [DIA_AMANHA]: fila = [] } = await chrome.storage.local.get(DIA_AMANHA);
      await chrome.storage.local.set({ [DIA_AMANHA]: fila.filter((x) => x.id !== v.id) });
      recarregar();
    } }, "×")))) : null;

  // tudo postado (pedido do usuário em 2026-11-15): fica só o nome em verde e o procurar ideia. Clicar no nome abre
  if (semPostar && !abertos.has(c.id)) {
    return h("article", { class: "canal ok fechado" },
      h("div", { class: "canal-cab", title: "Clique para abrir o canal", onclick: () => { abertos.add(c.id); desenhar(); } },
        h("b", {}, `✓ ${c.titulo}`), h("span", { class: "meta ok" }, "hoje sem postar ▸")),
      h("div", { class: "linha" }, h("button", { type: "button", onclick: alternarSemPostar }, "Desfazer: vou postar hoje"), procurar),
      listaAmanha);
  }
  const tudoPostado = estado === "ok" && videos.length > 0;
  if (tudoPostado && !abertos.has(c.id)) {
    return h("article", { class: "canal ok fechado" },
      h("div", { class: "canal-cab", title: "Clique para ver os vídeos de hoje", onclick: () => { abertos.add(c.id); desenhar(); } },
        h("b", {}, `✓ ${c.titulo}`), h("span", { class: "meta ok" }, `${plural(postados, "postado", "postados")} ▸`)),
      procurar || h("span", { class: "fraco" }, "Escolha a conta de treino em Ajustes do canal (clique no nome) para procurar ideia."),
      linhaForaDoMeuDia(c),
      listaAmanha);
  }

  // no lugar da Nova produção, o Postar (pedido do usuário em 2026-11-15): sobe o próximo vídeo não postado do canal;
  // sem vídeo pedido, abre o upload do Studio
  const naoPostados = videos.filter((v) => !v.postado);
  const avisos = [naoPostados.length ? `Falta postar ${plural(naoPostados.length, "vídeo", "vídeos")}` : "",
    falta ? `falta pedir ${plural(falta, "vídeo", "vídeos")} hoje` : ""].filter(Boolean).join(" · ");
  const postarCanal = h("button", { type: "button", class: "vermelho",
    title: naoPostados.length ? `Postar "${naoPostados[0].titulo}"` : "Abre o upload do YouTube Studio" },
  NO_STUDIO ? "Postar" : "Postar ↗");
  postarCanal.onclick = () => postar(naoPostados[0], postarCanal, c);
  const botaoSemPostar = h("button", { type: "button", class: "sem-postar", title: semPostar ? "Volta a contar este canal hoje" : "O canal fica verde hoje e sai da conta do dia",
    onclick: alternarSemPostar }, semPostar ? "Desfazer: vou postar hoje" : "Hoje não vou postar");

  return h("article", { class: `canal ${estado}` },
    h("div", { class: "canal-cab", ...(tudoPostado || semPostar ? { title: "Clique para recolher", onclick: () => { abertos.delete(c.id); desenhar(); } } : {}) },
      h("b", {}, c.titulo),
      meta == null ? null : h("span", { class: `meta ${estado}` },
        meta === 0 ? plural(feitos, "vídeo hoje", "vídeos hoje") : `${feitos}/${meta} hoje${postados ? ` · ${postados} postado${postados > 1 ? "s" : ""}` : ""}`)),
    pedacos,
    thumbFeita ? h("div", { class: "estado ok" }, "Thumbnail feita") : null,
    meta == null ? pergunta : null,
    avisos && !semPostar ? h("div", { class: "linha" }, h("span", { class: "aviso" }, avisos[0].toUpperCase() + avisos.slice(1)), postarCanal, botaoSemPostar)
      : !tudoPostado ? h("div", { class: "linha" }, botaoSemPostar) : null,
    procurar,
    linhaForaDoMeuDia(c),
    listaAmanha,
    videos.length || doCanal.length || naoPedidos.length ? h("div", { class: "videos" },
      ...videos.map((v) => cartaoDoVideo(v, (meta || 0) > 1 || videos.length > 1 ? numeroDe(v) : 0)),
      ...(semPostar || (meta || 0) < 2 ? [] : naoPedidos), ...doCanal.map(cartaoThumb)) : null,
    c.id && !NO_SITE ? novaThumb : null,
    h("details", {}, h("summary", {}, !cfg.treino ? "Ajustes do canal · falta a conta de treino"
      : /^https?:\/\//i.test(cfg.treino) && !/@[\w.\-]+/.test(cfg.treino) ? "Ajustes do canal · troque o link pelo @ da conta de treino" : "Ajustes do canal"),
      h("div", { style: "display:grid;gap:8px" },
        linkTreino,
        meta == null ? null : h("div", { class: "linha" }, h("span", { class: "fraco" }, "Vídeos por dia:"),
          ...[0, 1, 2, 3, 4].map((n) => h("button", { class: n === meta ? "vermelho" : "", onclick: () => escolherMeta(n) }, n === 0 ? "não posto todo dia" : String(n)))),
        h("div", { class: "linha" }, novoTitulo, h("button", { onclick: marcar }, "+ vídeo")))));
}

function desenhar() {
  const d = new Date();
  $("data").textContent = d.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });
  if (erroRadar) mostrarErro(erroRadar);

  const lista = [...canais];
  for (const v of dia.videos) if (!lista.some((c) => c.id === v.canal)) lista.push({ id: v.canal || "", titulo: v.canalNome || "Sem canal" });
  const doCanal = (id) => dia.videos.filter((v) => (v.canal || "") === id);
  // primeiro o vermelho, depois o amarelo, os sem cor e por fim os verdes
  const peso = (c) => {
    const m = (config[c.id] || {}).porDia, cor = corDoCanal(m, doCanal(c.id), dia.thumbs.some((t) => t.canal === c.id), semPostarHoje(c.id));
    return { falta: 0, meio: 1, azul: 2, "": 3, ok: 4 }[cor];
  };
  lista.sort((a, b) => peso(a) - peso(b));
  $("canais").replaceChildren(...(lista.length ? lista.map((c) => cartaoDoCanal(c, doCanal(c.id)))
    : [h("div", { class: "vazio" }, "Nenhum canal ainda. Ligue o Radar e cadastre seus canais.")]));

  // os canais de "hoje não vou postar" saem da conta do dia
  const contam = canais.filter((c) => !semPostarHoje(c.id));
  const metaTotal = contam.reduce((s, c) => s + ((config[c.id] || {}).porDia || 0), 0);
  const feitosMeta = contam.reduce((s, c) => s + Math.min(doCanal(c.id).length, (config[c.id] || {}).porDia || 0), 0);
  const semThumb = dia.videos.filter((v) => !v.thumb).length, postados = dia.videos.filter((v) => v.postado).length;
  const n = dia.videos.length;
  $("resumo").replaceChildren(...[
    metaTotal ? h("span", { class: `pilula ${corDaConta(feitosMeta, metaTotal)}` }, `Vídeos ${feitosMeta}/${metaTotal}`) : null,
    n ? h("span", { class: `pilula ${corDaConta(n - semThumb, n)}` }, semThumb ? `${plural(semThumb, "thumbnail falta", "thumbnails faltam")}` : "Thumbnails em dia") : null,
    n ? h("span", { class: `pilula ${corDaConta(postados, n)}` }, `${postados}/${n} postados`) : null,
    !metaTotal && !dia.videos.length ? h("span", { class: "pilula" }, "Nada pedido hoje") : null].filter(Boolean));
  $("legenda").replaceChildren(legenda(), ...[avisoDesfazer()].filter(Boolean));
  $("tirados").replaceChildren(...secaoTirados());
  lerPedidosDaFabrica();

  const usadas = thumbsUsadas();
  const soltas = dia.thumbs.filter((t) => !usadas.has(t.id) && !t.canal && imagens[t.id]);
  const semThumbVideos = dia.videos.filter((v) => !v.thumb);
  $("soltas").replaceChildren(
    ...soltas.map((t) => {
      // escolher o canal (ou um vídeo de hoje) marca a thumbnail como feita lá
      const sel = h("select", {}, h("option", { value: "" }, "Escolher o canal…"),
        ...canais.map((c) => h("option", { value: "c:" + c.id }, c.titulo)),
        ...semThumbVideos.map((v) => h("option", { value: "v:" + v.id }, `${v.canalNome ? v.canalNome + " · " : ""}${v.titulo}`)));
      sel.onchange = () => sel.value && mudarDia((d) => {
        const [tipo, alvo] = [sel.value.slice(0, 1), sel.value.slice(2)];
        const th = d.thumbs.find((x) => x.id === t.id);
        const x = tipo === "v" ? d.videos.find((y) => y.id === alvo) : d.videos.find((y) => y.canal === alvo && !y.thumb);
        if (x) x.thumb = t.id;
        if (th && tipo === "c") { th.canal = alvo; th.canalNome = (canais.find((c) => c.id === alvo) || {}).titulo || ""; }
      });
      return h("div", { class: "solta" }, h("img", { src: imagens[t.id], alt: "" }),
        h("span", { class: "fraco" }, `${hora(t.hora)}${t.origem ? " · " + t.origem : ""}`),
        sel,
        h("div", { class: "linha" }, baixar(t),
          h("button", { class: "x", title: "Apagar", onclick: async () => {
            await mudarDia((d) => { d.thumbs = d.thumbs.filter((x) => x.id !== t.id); });
            chrome.storage.local.remove(DIA_THUMB + t.id);
          } }, "×")));
    }),
    zonaDeImagem(h("div", { class: "solta-zona" }, "Arraste uma imagem, cole (Ctrl+V) ou clique para escolher"), null));
}

// ------------------------------------------------------------ começo e atualizações
chrome.storage.onChanged.addListener((mudou, area) => {
  if (area === "local" && mudou.contasYoutube) lerContasYoutube().then(desenhar);
  if (area === "local" && mudou.progresso) {
    // saiu da lista (terminou): pergunta de novo se ficou pronto
    for (const id of Object.keys(prontoNaFabrica)) delete prontoNaFabrica[id];
    lerProgresso().then(() => { const a = document.activeElement; if (!(a && a.tagName === "INPUT" && a.type !== "checkbox")) desenhar(); });
  }
  if (area !== "local" || !(mudou[DIA_CHAVE] || mudou[DIA_CONFIG] || mudou[DIA_AMANHA])) return;
  // não redesenha no meio de quem está digitando um link ou título
  const digitando = () => document.activeElement && document.activeElement.tagName === "INPUT" && document.activeElement.type !== "checkbox";
  const tentar = () => (digitando() ? setTimeout(tentar, 1500) : recarregar());
  tentar();
});
// virou o dia com a aba aberta: recomeça
setInterval(() => { if (dia.data !== hojeLocal()) recarregar(); }, 60 * 1000);
document.addEventListener("visibilitychange", () => { if (!document.hidden && dia.data !== hojeLocal()) recarregar(); });

if (new URLSearchParams(location.search).has("embutido")) document.body.classList.add("embutido");
Promise.all([lerContasYoutube(), lerProgresso()]).then(() => recarregar()).then(() => {
  // veio do Postar apertado fora do Studio: começa sozinho
  const v = postarAoAbrir && dia.videos.find((x) => x.id === postarAoAbrir);
  postarAoAbrir = "";
  if (v && NO_STUDIO) postar(v, null);
}).then(lerCanais);
