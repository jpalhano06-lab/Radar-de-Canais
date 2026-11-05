// O que a extensão acrescenta às telas do YouTube Studio, além da publicação (publicar.js): visualizações engajadas,
// foto do cartão, onde o vídeo perde gente, nota do título, capítulos da fala, hora por país e anúncios pela onda do
// som. Cada peça olha a tela a cada segundo e só aparece onde o elemento dela existe. O Studio muda sem aviso: elemento
// que não existe mais faz a peça sumir, nunca quebra a página.
// As contas puras ficam em globalThis.RadarStudio para os testes.
(() => {
  // ------------------------------------------------------------ contas

  // a curva de retenção é um path SVG: 100 pontos de 0 a 1, onde 1 é o pé do gráfico
  function curvaDoPath(d, alto) {
    const pts = [...String(d || "").matchAll(/[ML](-?[\d.]+)[, ](-?[\d.]+)/g)].map((m) => ({ x: +m[1], y: +m[2] }));
    if (pts.length < 4) return null;
    const x0 = pts[0].x, x1 = pts[pts.length - 1].x, altura = alto || Math.max(...pts.map((p) => p.y)) || 1;
    if (x1 <= x0) return null;
    const curva = [];
    let i = 1;
    for (let k = 0; k < 100; k++) {
      const x = x0 + (x1 - x0) * (k / 99);
      while (i < pts.length - 1 && pts[i].x < x) i++;
      const a = pts[i - 1], b = pts[i], f = b.x === a.x ? 0 : (x - a.x) / (b.x - a.x);
      curva.push((a.y + f * (b.y - a.y)) / altura);
    }
    return curva;
  }

  // as maiores descidas em janelas de 3 pontos, longe umas das outras. y cresce para baixo: cair é y aumentar
  function maioresQuedas(curva, quantas = 3) {
    const janelas = [];
    for (let i = 0; i + 3 < curva.length; i++) janelas.push({ i, cai: curva[i + 3] - curva[i] });
    janelas.sort((a, b) => b.cai - a.cai);
    const fica = [];
    for (const j of janelas) {
      if (j.cai <= 0.005 || fica.length === quantas) break;
      if (!fica.some((f) => Math.abs(f.i - j.i) < 6)) fica.push(j);
    }
    return fica.sort((a, b) => a.i - b.i);
  }

  // a força do som em cada coluna do canvas: quantos pontos dela estão pintados
  function ondaDaImagem(rgba, largura, altura) {
    const onda = new Array(largura).fill(0);
    for (let c = 0; c < largura; c++) {
      let n = 0;
      for (let l = 0; l < altura; l++) if (rgba[(l * largura + c) * 4 + 3] > 10) n++;
      onda[c] = altura ? n / altura : 0;
    }
    return onda;
  }

  // os trechos quietos da onda, em segundos: abaixo de `corte` (fração do pico) por pelo menos `minimo` segundos
  function pausasDaOnda(onda, duracao, corte = 0.08, minimo = 0.35) {
    const pico = Math.max(0, ...onda);
    if (!pico || !(duracao > 0)) return [];
    const porColuna = duracao / onda.length, pausas = [];
    let inicio = -1;
    for (let c = 0; c <= onda.length; c++) {
      if (c < onda.length && onda[c] <= corte * pico) { if (inicio < 0) inicio = c; continue; }
      if (inicio >= 0 && (c - inicio) * porColuna >= minimo) pausas.push({ t: (inicio + c) / 2 * porColuna, dura: (c - inicio) * porColuna });
      inicio = -1;
    }
    return pausas;
  }

  // as pausas mais longas primeiro, respeitando a distância mínima, o começo e o fim do vídeo
  function escolherPausas(pausas, duracao, distancia, naoAntes = 30, fim = 20) {
    const fica = [];
    for (const p of [...pausas].sort((a, b) => b.dura - a.dura || a.t - b.t)) {
      if (p.t < naoAntes || p.t > duracao - fim) continue;
      if (!fica.some((t) => Math.abs(t - p.t) < distancia)) fica.push(p.t);
    }
    return fica.sort((a, b) => a - b).map((t) => Math.round(t));
  }

  const tempo = (s) => {
    s = Math.max(0, Math.round(s));
    const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = String(s % 60).padStart(2, "0");
    return h ? `${h}:${String(m).padStart(2, "0")}:${x}` : `${m}:${x}`;
  };

  // a hora de um instante num fuso, como o relógio de lá mostra
  const horaEm = (quando, fuso) => new Intl.DateTimeFormat("pt-BR", { timeZone: fuso, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(quando);

  // os capítulos entram no fim da descrição, no lugar dos que já estavam lá
  function comCapitulos(descricao, capitulos) {
    const linhas = String(descricao || "").split("\n").filter((l) => !/^\s*\d{1,2}:\d{2}(:\d{2})?\s/.test(l));
    return `${linhas.join("\n").trimEnd()}\n\n${capitulos.map((c) => `${c.tempo} ${c.titulo}`).join("\n")}`.trimStart();
  }

  globalThis.RadarStudio = { curvaDoPath, maioresQuedas, ondaDaImagem, pausasDaOnda, escolherPausas, comCapitulos, horaEm, tempo };
  if (typeof chrome === "undefined" || !chrome.runtime || window.__radarStudioLente) return;
  window.__radarStudioLente = true;

  // ------------------------------------------------------------ ajudas

  const pedir = (msg) => new Promise((ok) => {
    try { chrome.runtime.sendMessage(msg, (r) => ok(r || { erro: "A extensão foi atualizada: recarregue esta página (F5)." })); }
    catch { ok({ erro: "A extensão foi atualizada: recarregue esta página (F5)." }); }
  });
  const api = (caminho, metodo, corpo) => pedir({ tipo: "api", caminho, metodo, corpo });
  const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  function el(tag, props = {}, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) if (k.startsWith("on")) e[k] = v; else if (v != null) e.setAttribute(k, v);
    e.append(...filhos.flat().filter((f) => f != null));
    return e;
  }
  const num = (n) => Number(n || 0).toLocaleString("pt-BR");
  const videoDaUrl = () => (location.pathname.match(/\/video\/([\w-]{11})\//) || [])[1] || "";
  let desligadas = new Set();
  const ligada = (chave) => !desligadas.has(chave);
  chrome.storage.local.get("funcoesDesligadas").then((d) => { desligadas = new Set(d.funcoesDesligadas || []); }).catch(() => {});
  chrome.storage.onChanged.addListener((m) => { if (m.funcoesDesligadas) desligadas = new Set(m.funcoesDesligadas.newValue || []); });

  // ------------------------------------------------------------ visualizações engajadas (a coluna no Conteúdo)
  // o pedido sai do studio.js, dentro da página, com o login da pessoa; a resposta volta por postMessage
  let pedidos = 0;
  const esperando = new Map();
  window.addEventListener("message", (e) => {
    if (e.source !== window || !e.data || e.data.radarEngajadasResposta !== 1) return;
    const ok = esperando.get(e.data.pedido);
    if (ok) { esperando.delete(e.data.pedido); ok(e.data.dados || null); }
  });
  const engajadasDe = (ids) => new Promise((ok) => {
    const pedido = ++pedidos;
    esperando.set(pedido, ok);
    window.postMessage({ radarEngajadas: 1, pedido, ids }, location.origin);
    setTimeout(() => { if (esperando.delete(pedido)) ok(null); }, 15000);
  });
  const ENGAJADAS = new Map();
  let lendoEngajadas = false;
  async function colunaEngajadas() {
    if (!ligada("engajadas")) return $$(".radar-eng").forEach((x) => x.remove());
    const cabeca = $(".tablecell-views.cell-header");
    if (!cabeca) return;
    if (!$(".radar-eng-cab")) cabeca.after(el("div", { class: "radar-eng radar-eng-cab", title: "Visualizações engajadas · Radar" }, "Engajadas"));
    const celulas = $$(".cell-body.tablecell-views").map((c) => {
      const a = (c.closest("ytcp-video-row") || c.parentElement).querySelector('a[href*="/video/"]');
      return { c, id: ((a && a.getAttribute("href") || "").match(/\/video\/([\w-]{11})/) || [])[1] };
    }).filter((x) => x.id);
    const faltam = celulas.filter((x) => !ENGAJADAS.has(x.id)).map((x) => x.id);
    if (faltam.length && !lendoEngajadas) {
      lendoEngajadas = true;
      const dados = await engajadasDe(faltam);
      faltam.forEach((id) => ENGAJADAS.set(id, dados ? dados[id] || null : null));
      lendoEngajadas = false;
    }
    for (const { c, id } of celulas) {
      const d = ENGAJADAS.get(id), texto = d ? `${num(d.engajadas)}${d.views ? ` (${Math.round(d.engajadas / d.views * 100)}%)` : ""}` : "—";
      let nossa = c.parentElement.querySelector(":scope > .radar-eng-cel");
      if (!nossa) { nossa = el("div", { class: "radar-eng radar-eng-cel" }); c.after(nossa); }
      if (nossa.textContent !== texto) nossa.textContent = texto;
    }
  }

  // a mesma conta no cartão do último vídeo, no Painel
  async function linhaEngajadas() {
    if (!ligada("engajadas")) return;
    const tabela = $("yta-entity-snapshot #metrics-table");
    if (!tabela || tabela.querySelector(".radar-eng-linha") || lendoEngajadas) return;
    const cartao = tabela.closest("ytcd-card"), a = cartao && cartao.querySelector('a[href*="/video/"]');
    const id = ((a && a.getAttribute("href") || "").match(/\/video\/([\w-]{11})/) || [])[1];
    if (!id) return;
    if (!ENGAJADAS.has(id)) {
      lendoEngajadas = true;
      const dados = await engajadasDe([id]);
      ENGAJADAS.set(id, dados ? dados[id] || null : null);
      lendoEngajadas = false;
    }
    const d = ENGAJADAS.get(id);
    if (d && !tabela.querySelector(".radar-eng-linha")) tabela.append(el("div", { class: "radar-eng-linha" }, el("span", {}, "Engajadas"), el("b", {}, num(d.engajadas))));
  }

  // ------------------------------------------------------------ foto do cartão: um clique, pronta para colar

  async function comoImagem(no) {
    const { width, height } = no.getBoundingClientRect();
    const copia = no.cloneNode(true);
    const origem = [no, ...no.querySelectorAll("*")], destino = [copia, ...copia.querySelectorAll("*")];
    origem.forEach((o, i) => {
      const estilo = getComputedStyle(o);
      destino[i].style.cssText = [...estilo].map((p) => `${p}:${estilo.getPropertyValue(p)}`).join(";");
    });
    copia.querySelectorAll(".radar-foto-botao, script, video, iframe").forEach((x) => x.remove());
    // imagem de fora suja o canvas: a de capa vem em base64 pelo background, a que não dá sai da foto
    await Promise.all([...copia.querySelectorAll("img")].map(async (img) => {
      const r = /i\.ytimg\.com/.test(img.src) ? await pedir({ tipo: "imagem", url: img.src }) : {};
      if (r.base64) img.src = `data:${r.tipo};base64,${r.base64}`; else img.remove();
    }));
    const xml = new XMLSerializer().serializeToString(copia);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width * 2}" height="${height * 2}" viewBox="0 0 ${width} ${height}">`
      + `<foreignObject width="100%" height="100%">${xml}</foreignObject></svg>`;
    const imagem = new Image();
    await new Promise((ok, erro) => { imagem.onload = ok; imagem.onerror = erro; imagem.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`; });
    const tela = el("canvas", { width: width * 2, height: height * 2 });
    const pincel = tela.getContext("2d");
    pincel.fillStyle = getComputedStyle(document.body).backgroundColor || "#fff";
    pincel.fillRect(0, 0, tela.width, tela.height);
    pincel.drawImage(imagem, 0, 0);
    return new Promise((ok) => tela.toBlob(ok, "image/png"));
  }

  function botoesDeFoto() {
    if (!ligada("foto-cartao")) return $$(".radar-foto-botao").forEach((x) => x.remove());
    for (const cartao of $$("ytcd-card, yta-key-metric-card, yta-line-chart-base-card, ytcp-analytics-card")) {
      if (cartao.querySelector(":scope > .radar-foto-botao")) continue;
      if (getComputedStyle(cartao).position === "static") cartao.style.position = "relative";
      cartao.append(el("button", { class: "radar-foto-botao", type: "button", title: "Copiar a foto deste cartão (cola com Ctrl+V)", onclick: async (e) => {
        e.stopPropagation();
        const b = e.currentTarget;
        b.textContent = "…";
        try {
          // o ClipboardItem aceita a promessa: o Chrome só deixa copiar enquanto o clique ainda vale
          await navigator.clipboard.write([new ClipboardItem({ "image/png": comoImagem(cartao) })]);
          b.textContent = "✓";
        } catch { b.textContent = "✕"; b.title = "O Studio não deixou copiar este cartão."; }
        setTimeout(() => { b.textContent = "📷"; }, 1800);
      } }, "📷"));
    }
  }

  // ------------------------------------------------------------ onde o vídeo perde gente

  let quedasDe = "";
  async function perdeGente() {
    const cartao = $("yta-audience-retention-highlights-player-and-chart-v2");
    const video = videoDaUrl();
    if (!cartao || !video || !ligada("perde-gente")) return;
    const caminho = $("yta-line-chart-base path.line-series", cartao);
    const d = caminho && caminho.getAttribute("d");
    if (!d || quedasDe === video + d.length) return;
    quedasDe = video + d.length;
    const svg = caminho.ownerSVGElement, curva = curvaDoPath(d, svg && svg.getBoundingClientRect().height);
    if (!curva) return;
    const player = $("video", cartao) || $("video");
    const duracao = player && player.duration;
    $$(".radar-perde").forEach((x) => x.remove());
    const caixa = el("section", { class: "radar-perde" }, el("b", {}, "Onde o vídeo perde gente"));
    cartao.after(caixa);
    const quedas = maioresQuedas(curva);
    if (!quedas.length) return caixa.append(el("p", {}, "A curva não tem nenhuma queda forte."));
    if (!duracao) return caixa.append(el("p", {}, "Dê play no vídeo do gráfico para eu saber a duração."));
    const fala = await api(`/api/ext/fala/${video}`);
    for (const q of quedas) {
      const ini = q.i / 99 * duracao, fim = (q.i + 3) / 99 * duracao;
      const dito = fala.erro ? "" : fala.dados.trechos.filter((t) => t.seg >= ini - 4 && t.seg <= fim + 2).map((t) => t.texto).join(" ");
      caixa.append(el("div", { class: "radar-perde-q" }, el("button", { type: "button", onclick: () => { if (player) player.currentTime = ini; } }, tempo(ini)),
        el("span", {}, `perde ${Math.round(q.cai * 100)} pontos`), el("p", {}, dito ? (dito.length > 220 ? `${dito.slice(0, 217)}…` : dito) : "Sem legenda neste trecho.")));
    }
  }

  // ------------------------------------------------------------ nota do título e títulos no molde

  const campoTitulo = () => $("#title-textarea #textbox") || $('ytcp-social-suggestions-textbox[label*="ítulo"] #textbox');
  const campoDescricao = () => $("#description-textarea #textbox") || $('ytcp-social-suggestions-textbox[label*="escri"] #textbox');
  let tituloLido = "";
  async function notaDoTitulo() {
    const campo = campoTitulo();
    if (!campo || !ligada("nota-titulo")) return;
    const casa = campo.closest("#title-textarea") || campo.parentElement;
    let caixa = $(".radar-nota-titulo");
    if (!caixa) {
      caixa = el("div", { class: "radar-nota-titulo" });
      casa.after(caixa);
      tituloLido = "";
    }
    const titulo = campo.textContent.trim();
    if (!titulo || titulo === tituloLido) return;
    tituloLido = titulo;
    const r = await api(`/api/ext/nota-titulo?titulo=${encodeURIComponent(titulo)}`);
    if (r.erro || titulo !== tituloLido) return;
    const { nota, motivos, molde } = r.dados, lista = el("div", { class: "radar-titulos" });
    caixa.replaceChildren(el("b", { class: `radar-nota-${nota >= 70 ? "boa" : nota >= 45 ? "media" : "fraca"}` }, `${nota}/100`),
      el("span", {}, motivos.join(" · ")),
      molde ? el("button", { type: "button", onclick: async (e) => {
        const b = e.currentTarget;
        b.disabled = true; b.textContent = "Escrevendo…";
        const v = await api("/api/ext/ia/titulos", "POST", { video_id: videoDaUrl() || "00000000000", titulo, assunto: titulo });
        b.disabled = false; b.textContent = "Títulos neste molde";
        lista.replaceChildren(...(v.erro ? [el("small", {}, v.erro)] : v.dados.titulos.map((t) => el("button", { type: "button", title: "Copiar", onclick: (x) => {
          navigator.clipboard.writeText(t); x.currentTarget.classList.add("copiado");
        } }, t))));
      } }, "Títulos neste molde") : null, lista);
  }

  // ------------------------------------------------------------ capítulos da fala

  function escreverNoCampo(campo, texto) {
    campo.focus();
    document.execCommand("selectAll");
    return document.execCommand("insertText", false, texto);
  }
  function botaoCapitulos() {
    const campo = campoDescricao(), video = videoDaUrl();
    if (!campo || !video || !ligada("capitulos") || $(".radar-capitulos")) return;
    const lista = el("div", { class: "radar-capitulos-lista" });
    const botao = el("button", { type: "button", onclick: async () => {
      botao.disabled = true; botao.textContent = "Lendo a fala…";
      const titulo = (campoTitulo() || {}).textContent || "";
      const r = await api("/api/ext/ia/capitulos", "POST", { video_id: video, titulo: titulo.trim() || video });
      botao.disabled = false; botao.textContent = "Capítulos da fala";
      if (r.erro) return lista.replaceChildren(el("small", {}, r.erro));
      const { capitulos } = r.dados;
      lista.replaceChildren(...capitulos.map((c) => el("div", {}, el("b", {}, c.tempo), ` ${c.titulo}`)), el("button", { type: "button", onclick: (e) => {
        const feito = escreverNoCampo(campoDescricao(), comCapitulos(campoDescricao().innerText, capitulos));
        e.currentTarget.textContent = feito ? "Colocado ✓" : "Não achei a descrição";
      } }, "Colocar na descrição"));
    } }, "Capítulos da fala");
    (campo.closest("#description-textarea") || campo.parentElement).after(el("div", { class: "radar-capitulos" }, botao, lista));
  }

  // ------------------------------------------------------------ hora por país

  const FUSOS = [["Estados Unidos (Nova York)", "America/New_York"], ["Estados Unidos (Los Angeles)", "America/Los_Angeles"], ["Reino Unido", "Europe/London"],
    ["Canadá (Toronto)", "America/Toronto"], ["Austrália (Sydney)", "Australia/Sydney"], ["Portugal", "Europe/Lisbon"], ["Espanha", "Europe/Madrid"],
    ["México", "America/Mexico_City"], ["Argentina", "America/Argentina/Buenos_Aires"], ["França", "Europe/Paris"], ["Alemanha", "Europe/Berlin"],
    ["Itália", "Europe/Rome"], ["Polônia", "Europe/Warsaw"], ["Turquia", "Europe/Istanbul"], ["Índia", "Asia/Kolkata"], ["Japão", "Asia/Tokyo"], ["Coreia do Sul", "Asia/Seoul"]];

  async function horaPorPais() {
    const agenda = $("ytcp-datetime-picker, #schedule-radio-button, ytcp-video-visibility-select");
    if (!agenda || !ligada("hora-pais") || $(".radar-hora-pais")) return;
    const canal = (await chrome.storage.local.get("numerosCanal")).numerosCanal?.canal || "";
    const chave = `fusoDoCanal:${canal}`;
    const guardado = (await chrome.storage.local.get(chave))[chave] || FUSOS[0][1];
    if ($(".radar-hora-pais")) return;
    const seletor = el("select", { title: "O país do público deste canal", onchange: () => { chrome.storage.local.set({ [chave]: seletor.value }); mostrar(); } },
      FUSOS.map(([nome, fuso]) => { const o = el("option", { value: fuso }, nome); if (fuso === guardado) o.selected = true; return o; }));
    const saida = el("span", {}), melhores = el("small", {});
    function mostrar() {
      saida.textContent = `Agora são ${horaEm(new Date(), seletor.value)} lá`;
      if (melhores.dataset.base) {
        const base = JSON.parse(melhores.dataset.base), hoje = new Date();
        melhores.textContent = `Horas com mais views: ${base.map((h) => horaEm(new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate(), h), seletor.value)).join(", ")} lá`;
      }
    }
    agenda.after(el("div", { class: "radar-hora-pais" }, seletor, saida, melhores));
    const r = canal ? await api(`/api/ext/horarios/${canal}?fuso=${-new Date().getTimezoneOffset()}`) : { erro: "sem canal" };
    if (!r.erro && r.dados.suficiente) {
      const v = r.dados.por_dia.geral || [];
      melhores.dataset.base = JSON.stringify(v.map((x, i) => [x, r.dados.faixas[i][0]]).sort((a, b) => b[0] - a[0]).slice(0, 3).map(([, h]) => h));
    }
    mostrar();
  }

  // ------------------------------------------------------------ anúncios pela onda do som

  const LINHA_ANUNCIO = "ytve-ad-breaks-editor-options-panel .ad-break-row";
  const vermelha = (l) => /interrup/i.test(l.textContent) || !!l.querySelector(".error, [class*='warning']");
  async function tirarAnuncios(filtro, aviso) {
    const linhas = $$(LINHA_ANUNCIO).filter(filtro).reverse();
    let tirados = 0;
    for (const l of linhas) {
      const lixo = l.querySelector("ytcp-icon-button.delete-button");
      if (!lixo) continue;
      lixo.click(); tirados++;
      await espera(120);
    }
    aviso.textContent = tirados ? `${tirados} tirados.` : "Nada para tirar.";
  }

  async function anunciosPelaOnda(aviso, minutos) {
    const video = $("ytcp-html5-video-source video") || $("video"), canvas = $("ytve-audio-waveform canvas");
    if (!video || !video.duration) return (aviso.textContent = "O vídeo do editor ainda não carregou.");
    if (!canvas || !canvas.width) return (aviso.textContent = "Não achei a onda do som nesta tela.");
    let imagem;
    try { imagem = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data; }
    catch { return (aviso.textContent = "O Studio não deixou ler a onda do som."); }
    const pausas = pausasDaOnda(ondaDaImagem(imagem, canvas.width, canvas.height), video.duration);
    const tempos = escolherPausas(pausas, video.duration, minutos * 60);
    if (!tempos.length) return (aviso.textContent = `Achei ${pausas.length} pausas, nenhuma serve. Afaste o zoom para a onda mostrar o vídeo inteiro.`);
    const inserir = $("#add-ad-break") || $("ytcp-button[test-id='insert-ad-slot'] button");
    if (!inserir) return (aviso.textContent = "Não achei o botão de inserir anúncio.");
    let postos = 0;
    for (const t of tempos) {
      video.currentTime = t;
      await espera(350);
      inserir.click();
      postos++;
      aviso.textContent = `${postos} de ${tempos.length}…`;
      await espera(300);
    }
    aviso.textContent = `${postos} anúncios em pausas da fala. Confira e salve você.`;
  }

  function barraDeAnuncios() {
    const painel = $("ytve-ad-breaks-editor-options-panel");
    if (!painel || !ligada("anuncios-onda") || $(".radar-onda")) return;
    const aviso = el("small", {}), minutos = el("input", { type: "number", min: "1", max: "30", value: "2", title: "Distância mínima entre anúncios, em minutos" });
    painel.prepend(el("div", { class: "radar-onda" }, el("b", {}, "Radar"), el("label", {}, "A cada ", minutos, " min"),
      el("button", { type: "button", onclick: () => anunciosPelaOnda(aviso, Math.max(1, +minutos.value || 2)) }, "Colocar nas pausas"),
      el("button", { type: "button", onclick: () => tirarAnuncios(vermelha, aviso) }, "Tirar os vermelhos"),
      el("button", { type: "button", onclick: () => tirarAnuncios(() => true, aviso) }, "Tirar todos"), aviso));
  }

  // ------------------------------------------------------------ a olhada de cada segundo

  const PECAS = [colunaEngajadas, linhaEngajadas, botoesDeFoto, perdeGente, notaDoTitulo, botaoCapitulos, horaPorPais, barraDeAnuncios];
  setInterval(() => PECAS.forEach((p) => { try { Promise.resolve(p()).catch(() => {}); } catch { /* peça que não achou a tela */ } }), 1000);
})();
