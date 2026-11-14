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
let destinoArquivo = null;   // o vídeo que recebe o arquivo escolhido (null: fica solta)

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
  const g = await chrome.storage.local.get([DIA_CONFIG, "diaCanais"]);
  config = g[DIA_CONFIG] || {};
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

async function guardarDeTransferencia(dt, video) {
  const arquivo = [...(dt.files || [])].find((f) => f.type.startsWith("image/"));
  if (arquivo) {
    const dados = await lerArquivo(arquivo);
    if (dados) return diaGuardarThumb(dados, { nome: arquivo.name, origem: "arquivo", video });
  }
  // uma imagem arrastada de outra aba vem só com o endereço
  const url = (dt.getData && (dt.getData("text/uri-list") || dt.getData("text/plain")) || "").split("\n")[0].trim();
  if (/^data:image\//.test(url)) return diaGuardarThumb(url, { origem: "arrastada", video });
  if (/^https?:\/\//.test(url)) {
    try {
      const r = await fetch(url);
      const b = await r.blob();
      if (r.ok && b.type.startsWith("image/")) return diaGuardarThumb(await lerArquivo(b), { origem: new URL(url).hostname, video });
    } catch (e) { /* o site não deixou */ }
    mostrarErro("Não consegui pegar essa imagem pelo endereço. Salve ela no computador e arraste o arquivo, ou use o botão direito > Salvar thumbnail no Meu dia.");
  }
}

function zonaDeImagem(el, video) {
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("sobre"); });
  el.addEventListener("dragleave", () => el.classList.remove("sobre"));
  el.addEventListener("drop", (e) => { e.preventDefault(); el.classList.remove("sobre"); guardarDeTransferencia(e.dataTransfer, video); });
  el.addEventListener("click", () => { destinoArquivo = video; $("arquivo").value = ""; $("arquivo").click(); });
  return el;
}
$("arquivo").addEventListener("change", async () => {
  const f = $("arquivo").files[0];
  if (f) { const dados = await lerArquivo(f); if (dados) await diaGuardarThumb(dados, { nome: f.name, origem: "arquivo", video: destinoArquivo }); }
});
document.addEventListener("paste", (e) => {
  if (e.target.closest && e.target.closest("input")) return;
  if ([...(e.clipboardData.files || [])].some((f) => f.type.startsWith("image/"))) { e.preventDefault(); guardarDeTransferencia(e.clipboardData, null); }
});

function mostrarErro(texto) {
  const el = $("erro");
  el.textContent = texto; el.hidden = !texto;
  if (texto) setTimeout(() => { if (el.textContent === texto) { el.hidden = true; } }, 9000);
}

const baixar = (thumb, titulo) => h("a", { class: "botao", href: imagens[thumb.id] || "#",
  download: `${(titulo || thumb.nome || "thumbnail").replace(/[\\/:*?"<>|]+/g, " ").slice(0, 80)}.${((imagens[thumb.id] || "").match(/^data:image\/(\w+)/) || [, "png"])[1].replace("jpeg", "jpg")}` }, "Baixar");

// ------------------------------------------------------------ desenho
function cartaoDoVideo(v) {
  const thumb = v.thumb && dia.thumbs.find((t) => t.id === v.thumb);
  const slot = thumb && imagens[thumb.id]
    ? h("div", { class: "slot cheio", title: "Arraste outra imagem para trocar" }, h("img", { src: imagens[thumb.id], alt: "" }))
    : h("div", { class: "slot", title: "Arraste a imagem, ou clique para escolher o arquivo" }, "Arraste a thumbnail aqui");
  zonaDeImagem(slot, v.id);
  const postado = h("input", { type: "checkbox" }); postado.checked = !!v.postado;
  postado.onchange = () => mudarDia((d) => { const x = d.videos.find((y) => y.id === v.id); if (x) x.postado = postado.checked; });
  return h("div", { class: "video" }, slot,
    h("div", {},
      h("b", {}, v.titulo || "vídeo sem título"),
      h("div", { class: `estado ${thumb ? "ok" : "falta"}` },
        thumb ? "✓ Vídeo pedido · ✓ thumbnail feita" : `✓ Vídeo pedido${v.entrada ? " (na Entrada)" : ""} · falta a thumbnail`),
      h("div", { class: "acoes" },
        h("label", { class: "check" }, postado, "Postado"),
        h("span", { class: "fraco" }, hora(v.hora)),
        thumb ? baixar(thumb, v.titulo) : null,
        thumb ? h("button", { class: "x", title: "Tirar a thumbnail deste vídeo (ela fica nas soltas)",
          onclick: () => mudarDia((d) => { const x = d.videos.find((y) => y.id === v.id); if (x) x.thumb = null; }) }, "↺") : null,
        h("button", { class: "x", title: "Tirar este vídeo do dia",
          onclick: () => { if (confirm(`Tirar "${v.titulo}" do Meu dia?`)) mudarDia((d) => { d.videos = d.videos.filter((y) => y.id !== v.id); }); } }, "×"))));
}

function cartaoDoCanal(c, videos) {
  const cfg = config[c.id] || {};
  const meta = cfg.porDia;
  const feitos = videos.length, postados = videos.filter((v) => v.postado).length;
  const falta = meta ? Math.max(0, meta - feitos) : 0;
  const estado = meta == null ? "" : meta === 0 ? "" : falta ? "falta" : "ok";

  const escolherMeta = (n) => guardarConfig(c.id, { porDia: n });
  const pergunta = h("div", { class: "pergunta" },
    h("b", {}, "Você pretende postar quantos vídeos por dia neste canal?"),
    h("div", { class: "linha" }, ...[1, 2, 3, 4].map((n) => h("button", { onclick: () => escolherMeta(n) }, String(n))),
      h("button", { onclick: () => escolherMeta(0), title: "O canal não aparece como pendente" }, "Não posto todo dia")));

  const linkTreino = (() => {
    const input = h("input", { type: "url", placeholder: "Link do canal de treino (a conta onde você treina o algoritmo)", value: cfg.treino || "" });
    const salvar = () => {
      let v = input.value.trim();
      if (v && !/^https?:\/\//i.test(v)) v = "https://" + v.replace(/^\/+/, "");
      if (v && !/^https:\/\/(www\.|m\.)?youtube\.com\//i.test(v) && !/^https:\/\/youtu\.be\//i.test(v)) return mostrarErro("O link do canal de treino precisa ser do YouTube.");
      input.blur();
      guardarConfig(c.id, { treino: v });
    };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") salvar(); });
    return h("div", { class: "linha" }, input, h("button", { onclick: salvar }, "Salvar"));
  })();

  const novoTitulo = h("input", { placeholder: "Título de um vídeo feito fora da Nova produção" });
  const marcar = () => { const t = novoTitulo.value.trim(); novoTitulo.blur(); if (t) diaNovoVideo({ canal: c.id, canalNome: c.titulo, titulo: t }); };
  novoTitulo.addEventListener("keydown", (e) => { if (e.key === "Enter") marcar(); });

  return h("article", { class: `canal ${estado}` },
    h("div", { class: "canal-cab" }, h("b", {}, c.titulo),
      meta == null ? null : h("span", { class: `meta ${estado}` },
        meta === 0 ? plural(feitos, "vídeo hoje", "vídeos hoje") : `${feitos}/${meta} hoje${postados ? ` · ${postados} postado${postados > 1 ? "s" : ""}` : ""}`)),
    meta == null ? pergunta : null,
    falta ? h("div", { class: "linha" }, h("span", { class: "aviso" }, `Falta pedir ${plural(falta, "vídeo", "vídeos")} hoje`),
      h("a", { class: "botao vermelho", href: "https://www.youtube.com/#radar-nova-producao", target: "_blank" }, "Nova produção")) : null,
    cfg.treino ? h("div", { class: "linha" },
      h("a", { class: "botao", href: cfg.treino, target: "_blank", rel: "noopener", title: cfg.treino }, "🎯 Canal de treino: procurar ideia ↗")) : null,
    videos.length ? h("div", { class: "videos" }, ...videos.map(cartaoDoVideo)) : null,
    h("details", {}, h("summary", {}, cfg.treino ? "Ajustes do canal" : "Ajustes do canal · falta o link do canal de treino"),
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
  // primeiro os que faltam, depois os sem meta, depois os em dia
  const peso = (c) => { const m = (config[c.id] || {}).porDia; return m == null ? 1 : m && doCanal(c.id).length < m ? 0 : 2; };
  lista.sort((a, b) => peso(a) - peso(b));
  $("canais").replaceChildren(...(lista.length ? lista.map((c) => cartaoDoCanal(c, doCanal(c.id)))
    : [h("div", { class: "vazio" }, "Nenhum canal ainda. Ligue o Radar e cadastre seus canais.")]));

  const metaTotal = canais.reduce((s, c) => s + ((config[c.id] || {}).porDia || 0), 0);
  const feitosMeta = canais.reduce((s, c) => s + Math.min(doCanal(c.id).length, (config[c.id] || {}).porDia || 0), 0);
  const semThumb = dia.videos.filter((v) => !v.thumb).length, postados = dia.videos.filter((v) => v.postado).length;
  $("resumo").replaceChildren(...[
    metaTotal ? h("span", { class: `pilula ${feitosMeta >= metaTotal ? "ok" : "falta"}` }, `Vídeos ${feitosMeta}/${metaTotal}`) : null,
    dia.videos.length ? h("span", { class: `pilula ${semThumb ? "falta" : "ok"}` }, semThumb ? `${plural(semThumb, "thumbnail falta", "thumbnails faltam")}` : "Thumbnails em dia") : null,
    dia.videos.length ? h("span", { class: "pilula" }, `${postados}/${dia.videos.length} postados`) : null,
    !metaTotal && !dia.videos.length ? h("span", { class: "pilula" }, "Nada pedido hoje") : null].filter(Boolean));

  const usadas = new Set(dia.videos.map((v) => v.thumb).filter(Boolean));
  const soltas = dia.thumbs.filter((t) => !usadas.has(t.id) && imagens[t.id]);
  const semThumbVideos = dia.videos.filter((v) => !v.thumb);
  $("soltas").replaceChildren(
    ...soltas.map((t) => {
      const sel = h("select", {}, h("option", { value: "" }, "Ligar a um vídeo…"),
        ...semThumbVideos.map((v) => h("option", { value: v.id }, `${v.canalNome ? v.canalNome + " · " : ""}${v.titulo}`)));
      sel.onchange = () => sel.value && mudarDia((d) => { const x = d.videos.find((y) => y.id === sel.value); if (x) x.thumb = t.id; });
      return h("div", { class: "solta" }, h("img", { src: imagens[t.id], alt: "" }),
        h("span", { class: "fraco" }, `${hora(t.hora)}${t.origem ? " · " + t.origem : ""}`),
        semThumbVideos.length ? sel : null,
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
  if (area !== "local" || !(mudou[DIA_CHAVE] || mudou[DIA_CONFIG])) return;
  // não redesenha no meio de quem está digitando um link ou título
  const digitando = () => document.activeElement && document.activeElement.tagName === "INPUT" && document.activeElement.type !== "checkbox";
  const tentar = () => (digitando() ? setTimeout(tentar, 1500) : recarregar());
  tentar();
});
// virou o dia com a aba aberta: recomeça
setInterval(() => { if (dia.data !== hojeLocal()) recarregar(); }, 60 * 1000);
document.addEventListener("visibilitychange", () => { if (!document.hidden && dia.data !== hojeLocal()) recarregar(); });

if (new URLSearchParams(location.search).has("embutido")) document.body.classList.add("embutido");
recarregar().then(lerCanais);
