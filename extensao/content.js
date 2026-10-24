// Radar de Canais no YouTube: lê os vídeos da página (sem cota) e manda ao Radar, o resumo da busca, os filtros dos
// vídeos da página, o painel ao lado do vídeo e a análise do canal.
(() => {
  const CAIXAS = [
    "ytd-rich-item-renderer", "ytd-video-renderer", "ytd-compact-video-renderer", "ytd-grid-video-renderer",
    "ytd-playlist-video-renderer", "yt-lockup-view-model", "ytd-reel-item-renderer", "ytm-shorts-lockup-view-model",
  ].join(",");
  const IMAGEM = "ytd-thumbnail, a#thumbnail, yt-thumbnail-view-model, .yt-lockup-view-model__content-image, .shortsLockupViewModelHostThumbnailContainer";
  let semConta = false;

  const api = (caminho, metodo = "GET", corpo) =>
    new Promise((ok) => chrome.runtime.sendMessage({ tipo: "api", caminho, metodo, corpo }, (r) => ok(r || { erro: "sem resposta" })));

  // elemento com texto seguro (nada vindo do YouTube vira HTML)
  function h(tag, attrs = {}, ...filhos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v != null) el.setAttribute(k, v);
    }
    for (const f of filhos.flat()) if (f != null && f !== false) el.append(f instanceof Node ? f : String(f));
    return el;
  }

  // ícones de traço no lugar dos emojis (SVG montado à mão: o YouTube não deixa usar innerHTML)
  const ICONES = {
    fantasma: [["path", { d: "M5 20.5V11a7 7 0 0 1 14 0v9.5l-2.3-1.8-2.4 1.8-2.3-1.8-2.3 1.8-2.4-1.8z" }],
      ["circle", { cx: 9.5, cy: 11, r: 1.2, fill: "currentColor", stroke: "none" }], ["circle", { cx: 14.5, cy: 11, r: 1.2, fill: "currentColor", stroke: "none" }]],
    roteiro: [["path", { d: "M4 20h4L19 9l-4-4L4 16v4z" }], ["path", { d: "M13.5 6.5l4 4" }]],
    ideia: [["path", { d: "M9 18h6M10 21h4" }], ["path", { d: "M12 3a6 6 0 0 0-3.6 10.8c.6.5.6 1.2.6 2.2h6c0-1 0-1.7.6-2.2A6 6 0 0 0 12 3z" }]],
    titulo: [["rect", { x: 9, y: 9, width: 11, height: 11, rx: 2 }], ["path", { d: "M5 15V6a2 2 0 0 1 2-2h9" }]],
    capa: [["rect", { x: 3, y: 5, width: 18, height: 14, rx: 2 }], ["circle", { cx: 8.5, cy: 10, r: 1.5 }], ["path", { d: "M21 16l-5-5-9 8" }]],
    parecidos: [["circle", { cx: 9, cy: 8, r: 3.5 }], ["path", { d: "M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.3c1.8.8 3 3 3 5.7" }]],
    transcricao: [["path", { d: "M4 6h16M4 12h16M4 18h10" }]],
    olho: [["path", { d: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" }], ["circle", { cx: 12, cy: 12, r: 3 }]],
    raio: [["path", { d: "M13 2L4 14h7l-1 8 9-12h-7l1-8z" }]],
    barras: [["path", { d: "M3 20h18M6 16v-5M11 16V6M16 16v-8" }]],
    relogio: [["circle", { cx: 12, cy: 12, r: 9 }], ["path", { d: "M12 7v5l3 2" }]],
    calendario: [["rect", { x: 3, y: 5, width: 18, height: 16, rx: 2 }], ["path", { d: "M3 10h18M8 3v4M16 3v4" }]],
    tendencia: [["path", { d: "M3 17l6-6 4 4 8-8M15 7h6v6" }]],
    usuario: [["circle", { cx: 12, cy: 8, r: 4 }], ["path", { d: "M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8" }]],
    play: [["rect", { x: 2, y: 5, width: 20, height: 14, rx: 4 }], ["path", { d: "M10 9.5v5l4.5-2.5z", fill: "currentColor" }]],
    ordenar: [["path", { d: "M4 6h16M4 12h11M4 18h6" }]],
    baixar: [["path", { d: "M12 4v11M7 10l5 5 5-5M5 20h14" }]],
    limpar: [["path", { d: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5" }]],
    dinheiro: [["path", { d: "M12 2v20M17 6.5C17 4.6 14.8 3.5 12 3.5S7 4.7 7 6.8 9.2 10 12 10.5s5 1.5 5 3.7-2.2 3.8-5 3.8-5-1.1-5-3.1" }]],
    fogo: [["path", { d: "M12 22c4 0 7-3 7-7 0-4-3-6-4-9-1 2-2 3-4 3 0-3-1-5-3-7 0 4-3 6-3 10 0 5 3 10 7 10z" }]],
  };
  function novoSvg(tag, at = {}) {
    const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(at)) e.setAttribute(k, v);
    return e;
  }
  function icone(nome) {
    const s = novoSvg("svg", { viewBox: "0 0 24 24", class: "radar-ic", fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round" });
    for (const [tag, a] of ICONES[nome]) s.append(novoSvg(tag, a));
    return s;
  }
  // botão com ícone e texto (o texto fica no último <span>, para trocar por "copiado ✓" sem perder o ícone)
  const botao = (classe, ic, texto, onclick, acao, tecla) => h("button", { class: classe, "data-acao": acao, onclick, title: tecla ? `${texto} (${tecla})` : null }, icone(ic), h("span", {}, texto));

  const num =(n) => n == null ? "—" : n >= 1e9 ? (n / 1e9).toFixed(1).replace(".", ",") + " bi" : n >= 1e6 ? (n / 1e6).toFixed(1).replace(".", ",") + " mi"
    : n >= 1e3 ? (n >= 1e4 ? Math.round(n / 1e3) : (n / 1e3).toFixed(1).replace(".", ",")) + " mil" : String(Math.round(n));
  const nota = (x) => x == null ? "—" : (x >= 10 ? Math.round(x) : x.toFixed(1).replace(".", ",")) + "x";
  const nivel = (x) => x == null ? "n0" : x >= 10 ? "n4" : x >= 5 ? "n3" : x >= 2 ? "n2" : x >= 1 ? "n1" : "n0";
  const FASES = { nascendo: "nascendo", crescendo: "crescendo", estavel: "estável", caindo: "caindo", parado: "parado" };
  const SELOS = { lendario: "Lendário", epico: "Épico", raro: "Raro" };

  function idDoLink(href) {
    if (!href) return null;
    const m = href.match(/[?&]v=([\w-]{11})/) || href.match(/\/shorts\/([\w-]{11})/);
    return m ? m[1] : null;
  }

  // ------------------------------------------------------------ leitura da página (sem gastar a cota)
  // O leitor.js, dentro da página, manda o que o YouTube carregou (vídeos, views, data, canal). Aqui junta, manda ao
  // Radar (que guarda e dá a nota) e, quando o canal é novo, baixa a página de vídeos dele para achar o normal.

  const PAGINA = new Map();   // id -> vídeo visto nesta página, com a nota e os inscritos que o Radar devolveu
  const paraMandar = new Map();
  const lidos = new Set(), filaCanais = [];
  let canalDaPagina = null, relogioEnvio = null, lendo = false;

  window.addEventListener("message", (e) => {
    if (e.source !== window || !e.data || e.data.radarLeitor !== 1) return;
    for (const v of e.data.videos || []) {
      const antes = PAGINA.get(v.id);
      PAGINA.set(v.id, antes ? { ...antes, ...v, nota: antes.nota, inscritos: antes.inscritos } : v);
      paraMandar.set(v.id, v);
    }
    if (e.data.canal) canalDaPagina = e.data.canal;
    if (!relogioEnvio) relogioEnvio = setTimeout(mandar, 1500);
    atualizarTela();
  });
  // outra página: a lista recomeça (o evento vem antes das respostas da página nova)
  document.addEventListener("yt-navigate-start", () => { PAGINA.clear(); atualizarTela(); });

  async function mandar() {
    relogioEnvio = null;
    if (semConta || (!paraMandar.size && !canalDaPagina)) return;
    const videos = [...paraMandar.values()].slice(0, 150);
    videos.forEach((v) => paraMandar.delete(v.id));
    const canal = canalDaPagina;
    canalDaPagina = null;
    const r = await api("/api/ext/vistos", "POST", { videos, canal });
    if (r.erro) { if (r.status === 401) semConta = true; return; }
    for (const [id, x] of Object.entries(r.dados.videos)) {
      const v = PAGINA.get(id);
      if (v) Object.assign(v, { nota: x.nota, inscritos: x.inscritos, normal: x.normal, raridade: x.raridade, reacao: x.reacao });
    }
    if (r.dados.reacao_alta) reacaoAlta = r.dados.reacao_alta;
    for (const id of r.dados.ler) if (!lidos.has(id)) { lidos.add(id); filaCanais.push(id); }
    lerCanais();
    atualizarTela();
    if (paraMandar.size) relogioEnvio = setTimeout(mandar, 500);
  }

  // canal que o Radar não conhece: a extensão baixa a página de vídeos dele (como a pessoa abriria) e manda ao Radar
  async function lerCanais() {
    if (lendo) return;
    lendo = true;
    try {
      while (filaCanais.length && !semConta) {
        const id = filaCanais.shift();
        // os vídeos deste canal que estão na tela voltam ao Radar para ganhar a nota
        if (await lerCanal(id)) for (const v of PAGINA.values()) if (v.canal_id === id) paraMandar.set(v.id, v);
        atualizarTela();
        await new Promise((ok) => setTimeout(ok, 1200));
      }
    } finally { lendo = false; }
    if (paraMandar.size && !relogioEnvio) relogioEnvio = setTimeout(mandar, 300);
  }

  async function lerCanal(id) {
    try {
      const json = RadarLer.jsonDoHtml(await (await fetch(`https://www.youtube.com/channel/${id}/videos`)).text());
      const canal = json && RadarLer.canal(json);
      if (!canal) return false;
      return !(await api("/api/ext/canal-lido", "POST", { canal, videos: RadarLer.videos(json) })).erro;
    } catch { return false; }   // canal que não abriu: fica para outra vez
  }

  const longo = (v) => !v.duracao_s || v.duracao_s > 180;
  const idade = (d) => d == null ? "" : d < 1 ? "hoje" : d < 30 ? `há ${Math.round(d)} ${Math.round(d) === 1 ? "dia" : "dias"}`
    : d < 365 ? `há ${Math.round(d / 30.44)} ${Math.round(d / 30.44) === 1 ? "mês" : "meses"}` : `há ${Math.round(d / 365.25)} ${Math.round(d / 365.25) === 1 ? "ano" : "anos"}`;
  const mediana = (xs) => { const o = [...xs].sort((a, b) => a - b); return o.length ? o[Math.floor(o.length / 2)] : null; };

  function atualizarTela() {
    clearTimeout(atualizarTela.t);
    atualizarTela.t = setTimeout(() => { varrer(); resumoDaBusca(); botaoFiltros(); botaoProvar(); faixaEmAlta(); menuDoVideo(); numerosTopo(); botaoNovaProducao(); }, 300);
  }

  // ------------------------------------------------------------ resumo da busca: o nicho está aberto?

  function resumoDaBusca() {
    const velho = document.querySelector(".radar-resumo");
    if (location.pathname !== "/results") { if (velho) velho.remove(); return; }
    const conteudo = document.querySelector("ytd-search ytd-section-list-renderer #contents");
    if (!conteudo) return;
    const lista = [...PAGINA.values()].filter((v) => v.views != null && longo(v));
    if (lista.length < 3) { if (velho) velho.remove(); return; }
    const views = lista.map((v) => v.views);
    const recentes = lista.filter((v) => v.dias != null && v.dias <= 30).length;
    const estourados = lista.filter((v) => v.nota >= 3);
    const pequenos = estourados.filter((v) => v.inscritos != null && v.inscritos < 10000);
    const comNota = lista.filter((v) => v.nota != null).length;
    const veredito = pequenos.length >= 2 ? ["boa", "🟢 Nicho aberto: canal pequeno está estourando com esse assunto."]
      : estourados.length >= 3 ? ["media", "🟡 O assunto estoura, mas mais em canais maiores."]
      : recentes / lista.length < 0.2 ? ["fraca", "⚪ Quase nada novo: o assunto está parado (ou ninguém achou ainda)."]
      : ["fraca", "⚪ Nada estourando nesta busca por enquanto."];
    const caixa = h("div", { class: `radar-resumo ${veredito[0]}` },
      h("div", { class: "radar-resumo-titulo" }, h("b", {}, "Radar"), h("span", {}, veredito[1])),
      h("div", { class: "radar-resumo-numeros" },
        h("div", {}, h("b", {}, String(lista.length)), "vídeos lidos"),
        h("div", {}, h("b", {}, num(views.reduce((a, b) => a + b, 0) / views.length)), "views na média"),
        h("div", {}, h("b", {}, num(mediana(views))), "views na mediana"),
        h("div", {}, h("b", {}, `${recentes}`), "dos últimos 30 dias"),
        h("div", {}, h("b", {}, `${estourados.length}`), "com 3x o normal ou mais"),
        h("div", {}, h("b", {}, `${pequenos.length}`), "em canal pequeno (até 10 mil)")),
      h("div", { class: "radar-fraco" }, comNota < lista.length
        ? `A nota de ${lista.length - comNota} vídeos ainda está chegando: o Radar está lendo os canais (sem gastar cota). Role a página para ler mais.`
        : "Role a página para ler mais vídeos. Para ordenar e filtrar, use o botão Vídeos desta página."));
    if (velho) velho.replaceWith(caixa); else conteudo.parentElement.insertBefore(caixa, conteudo);
  }

  // ------------------------------------------------------------ filtros: os vídeos que a página já mostrou

  // o botão Filtros fica no alto do YouTube, ao lado da busca (página inicial, busca, vídeo, canal); sem a barra do
  // YouTube, fica solto no canto da tela
  function botaoFiltros() {
    let b = document.querySelector(".radar-filtros-botao");
    const n = [...PAGINA.values()].filter((v) => v.views != null).length;
    if (n < 4) { if (b) b.remove(); return; }
    const topo = document.querySelector("ytd-masthead #center");
    if (!b || (topo && !topo.contains(b))) {
      if (b) b.remove();
      b = h("button", { class: `radar-filtros-botao${topo ? " no-topo" : ""}`, title: "Filtrar e ordenar os vídeos desta página (Alt+V)", onclick: abrirFiltros },
        h("i", {}), h("span", {}, "Filtros"), h("em", {}));
      if (topo) topo.prepend(b); else document.body.append(b);
    }
    b.querySelector("em").textContent = n;
  }

  // a janela dos vídeos da página: atalhos, faixas de inscritos e de views, data, ordem e planilha (a página não muda)
  const FAIXA_INSCRITOS = [0, 1e3, 5e3, 1e4, 5e4, 1e5, 5e5, 1e6, 5e6];
  const FAIXA_VIEWS = [0, 1e3, 1e4, 5e4, 1e5, 5e5, 1e6, 5e6, 2e7];
  const QUANDO = [["tudo", "Tudo", null], ["hora", "1 hora", 1 / 24], ["hoje", "Hoje", 1], ["semana", "7 dias", 7], ["mes", "30 dias", 30], ["ano", "1 ano", 365]];
  const ORDENS = [["youtube", "YouTube", "play"], ["novos", "Mais novos", "calendario"], ["inscritos", "Inscritos", "usuario"], ["views", "Views", "olho"],
    ["vph", "Views/h", "tendencia"], ["nota", "Outlier", "fogo"]];
  const vph = (v) => v.views != null && v.dias != null ? v.views / Math.max(1, v.dias * 24) : null;

  function abrirFiltros() {
    document.querySelectorAll(".radar-janela-fundo").forEach((j) => j.remove());
    const F = { ordem: "youtube", ins: [0, FAIXA_INSCRITOS.length - 1], vie: [0, FAIXA_VIEWS.length - 1], quando: "tudo", atalho: "" };
    const fundo = h("div", { class: "radar-janela-fundo", onclick: (e) => { if (e.target === fundo) fechar(); } });
    const fechar = () => { fundo.remove(); clearInterval(relogio); };
    const grade = h("div", { class: "rf-grade" });
    const conta = h("div", { class: "rf-conta" }), rodape = h("div", { class: "rf-rodape" });
    const ordem = [...PAGINA.keys()];   // a ordem do YouTube é a ordem em que os vídeos chegaram

    const filtrados = () => {
      const [i0, i1] = F.ins.map((i) => FAIXA_INSCRITOS[i]), [v0, v1] = F.vie.map((i) => FAIXA_VIEWS[i]);
      const lim = (QUANDO.find((q) => q[0] === F.quando) || [])[2];
      let vs = [...PAGINA.values()].filter((v) => v.views != null && longo(v));
      vs = vs.filter((v) => (F.ins[0] === 0 || (v.inscritos != null && v.inscritos >= i0)) && (F.ins[1] === FAIXA_INSCRITOS.length - 1 || (v.inscritos != null && v.inscritos <= i1)));
      vs = vs.filter((v) => v.views >= v0 && (F.vie[1] === FAIXA_VIEWS.length - 1 || v.views <= v1));
      if (lim != null) vs = vs.filter((v) => v.dias != null && v.dias <= lim);
      if (F.atalho === "pequeno") vs = vs.filter((v) => v.inscritos != null && v.inscritos < 1e4 && v.nota >= 3);
      const chave = { novos: (v) => -(v.dias ?? 1e9), inscritos: (v) => v.inscritos ?? -1, views: (v) => v.views, vph: (v) => vph(v) ?? -1, nota: (v) => v.nota ?? -1 }[F.ordem];
      if (chave) vs.sort((a, b) => chave(b) - chave(a)); else vs.sort((a, b) => ordem.indexOf(a.id) - ordem.indexOf(b.id));
      return vs;
    };

    const cartao = (v) => h("a", { class: "rf-card", href: `https://www.youtube.com/watch?v=${v.id}` },
      h("div", { class: "rf-capa" }, h("img", { src: `https://i.ytimg.com/vi/${v.id}/mqdefault.jpg`, alt: "", loading: "lazy" }),
        v.duracao_s ? h("span", { class: "rf-dur" }, minSeg(v.duracao_s)) : null),
      h("div", { class: "rf-info" }, h("span", { class: "rf-letra" }, (v.canal || "?").trim()[0] || "?"),
        h("div", {}, h("b", { class: "rf-titulo" }, v.titulo),
          h("div", { class: "rf-meta" }, [v.canal, v.inscritos != null ? `${num(v.inscritos)} inscritos` : null].filter(Boolean).join(" · ")),
          h("div", { class: "rf-meta" }, [`${num(v.views)} views`, idade(v.dias)].filter(Boolean).join(" · ")),
          h("div", { class: "rf-pilulas" },
            v.nota != null ? h("span", { class: `rf-nota ${corNota(v.nota)}` }, nota(v.nota)) : null,
            vph(v) != null ? h("span", { class: "rf-vph" }, `${num(vph(v))} VPH`) : null))));

    const desenhar = () => {
      const vs = filtrados(), total = [...PAGINA.values()].filter((v) => v.views != null && longo(v)).length;
      conta.replaceChildren(h("b", {}, String(vs.length)), ` de ${total} vídeos`);
      grade.replaceChildren(...(vs.length ? vs.map(cartao) : [h("div", { class: "radar-fraco" }, "Nenhum vídeo com esses filtros. Clique em Limpar ou em Carregar mais vídeos.")]));
      const semIns = vs.filter((v) => v.inscritos == null).length;
      rodape.textContent = semIns ? `${semIns} ainda sem inscritos: o Radar está lendo os canais (sem gastar cota).` : "";
      botoesOrdem.forEach((b) => b.classList.toggle("ligado", b.dataset.o === F.ordem));
      botoesQuando.forEach((b) => b.classList.toggle("ligado", b.dataset.q === F.quando));
      atalhos.forEach((a) => a.classList.toggle("ligado", a.dataset.a === F.atalho));
      for (const fx of faixas) fx.atualizar();
    };

    // faixa com duas pontas (mínimo e máximo), em degraus
    const faixa = (rotulo, ic, degraus, chave, fmt) => {
      const a = h("input", { type: "range", min: "0", max: String(degraus.length - 1), step: "1" });
      const b = h("input", { type: "range", min: "0", max: String(degraus.length - 1), step: "1" });
      const ta = h("span", { class: "rf-valor" }), tb = h("span", { class: "rf-valor" });
      const mudou = () => { let x = +a.value, y = +b.value; if (x > y) [x, y] = [y, x]; F[chave] = [x, y]; F.atalho = ""; desenhar(); };
      a.addEventListener("input", mudou); b.addEventListener("input", mudou);
      const caixa = h("div", { class: "rf-faixa" }, h("div", { class: "rf-faixa-cab" }, h("span", {}, icone(ic), rotulo), ta, h("span", {}, "–"), tb),
        h("div", { class: "rf-dupla" }, a, b));
      caixa.atualizar = () => { a.value = F[chave][0]; b.value = F[chave][1]; ta.textContent = fmt(degraus[F[chave][0]]);
        tb.textContent = fmt(degraus[F[chave][1]]) + (F[chave][1] === degraus.length - 1 ? "+" : ""); };
      return caixa;
    };
    const curto = (n) => n >= 1e6 ? n / 1e6 + "M" : n >= 1e3 ? n / 1e3 + "K" : String(n);
    const faixas = [faixa("Inscritos", "usuario", FAIXA_INSCRITOS, "ins", curto), faixa("Views", "olho", FAIXA_VIEWS, "vie", curto)];

    const ATALHOS = [["pequeno", "fogo", "Canal pequeno que estourou", () => Object.assign(F, { ordem: "nota" })],
      ["rapidos", "tendencia", "Rápidos agora", () => Object.assign(F, { ordem: "vph" })],
      ["semana", "calendario", "Desta semana", () => Object.assign(F, { quando: "semana", ordem: "vph" })],
      ["vistos", "olho", "Os mais vistos", () => Object.assign(F, { ordem: "views" })]];
    const atalhos = ATALHOS.map(([k, ic, t, faz]) => h("button", { class: "rf-atalho", "data-a": k, onclick: () => {
      Object.assign(F, { ordem: "youtube", ins: [0, FAIXA_INSCRITOS.length - 1], vie: [0, FAIXA_VIEWS.length - 1], quando: "tudo" });
      if (F.atalho === k) { F.atalho = ""; } else { F.atalho = k; faz(); }
      desenhar();
    } }, icone(ic), t));
    const botoesQuando = QUANDO.map(([k, t]) => h("button", { class: "rf-chip", "data-q": k, onclick: () => { F.quando = k; F.atalho = ""; desenhar(); } }, t));
    const botoesOrdem = ORDENS.map(([k, t, ic]) => h("button", { class: "rf-chip", "data-o": k, onclick: () => { F.ordem = k; desenhar(); } }, icone(ic), t));
    const shorts = h("input", { type: "checkbox", class: "rf-interruptor", onchange: (e) => chrome.storage.local.set({ semShorts: e.target.checked }) });
    chrome.storage.local.get("semShorts").then(({ semShorts: s }) => { shorts.checked = !!s; });

    const planilha = () => {
      const linhas = [["titulo", "canal", "inscritos", "views", "views_por_hora", "outlier", "dias", "duracao_s", "link"]]
        .concat(filtrados().map((v) => [v.titulo, v.canal, v.inscritos ?? "", v.views, Math.round(vph(v) ?? 0), v.nota ?? "", v.dias != null ? Math.round(v.dias) : "", v.duracao_s ?? "", `https://www.youtube.com/watch?v=${v.id}`]));
      const csv = "﻿" + linhas.map((l) => l.map((x) => `"${String(x).replace(/"/g, '""')}"`).join(";")).join("\r\n");
      const a = h("a", { href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })), download: `radar-videos-${new Date().toISOString().slice(0, 10)}.csv` });
      document.body.append(a); a.click(); a.remove();
    };

    fundo.append(h("div", { class: "rf-janela" },
      h("div", { class: "rf-topo" }, h("span", { class: "rf-marca" }, h("i", {}), "Radar"), h("b", {}, "Filtros"), conta,
        h("div", { class: "rf-topo-acoes" },
          h("button", { class: "rf-forte", onclick: () => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" }) }, icone("baixar"), "Carregar mais vídeos"),
          h("button", { class: "rf-chip rf-borda", onclick: planilha }, icone("baixar"), "Baixar planilha"),
          h("button", { class: "rf-fechar", title: "Fechar", onclick: fechar }, "×"))),
      h("div", { class: "rf-corpo" },
        h("aside", { class: "rf-lado" },
          h("div", { class: "rf-secao" }, "Atalhos"), ...atalhos,
          h("div", { class: "rf-secao" }, "Filtrar", h("button", { class: "rf-limpar", onclick: () => {
            Object.assign(F, { ins: [0, FAIXA_INSCRITOS.length - 1], vie: [0, FAIXA_VIEWS.length - 1], quando: "tudo", atalho: "" }); desenhar();
          } }, icone("limpar"), "Limpar")),
          ...faixas,
          h("div", { class: "rf-faixa-cab" }, h("span", {}, icone("calendario"), "Publicado")), h("div", { class: "rf-chips" }, botoesQuando),
          h("div", { class: "rf-secao" }, "Página"), h("label", { class: "rf-chave" }, h("span", {}, icone("raio"), "Esconder Shorts"), shorts)),
        h("div", { class: "rf-principal" },
          h("div", { class: "rf-ordem" }, h("span", { class: "rf-ordenar" }, icone("ordenar"), "Ordenar"), botoesOrdem),
          grade, rodape))));
    document.body.append(fundo);
    desenhar();
    // a página continua chegando (rolagem, canais lidos): a janela acompanha
    let visto = PAGINA.size;
    const relogio = setInterval(() => {
      if (!fundo.isConnected) return clearInterval(relogio);
      for (const id of PAGINA.keys()) if (!ordem.includes(id)) ordem.push(id);
      const agora = [...PAGINA.values()].reduce((s, v) => s + (v.nota != null) + (v.inscritos != null), PAGINA.size);
      if (agora !== visto) { visto = agora; desenhar(); }
    }, 1500);
  }

  // ------------------------------------------------------------ provar a capa e o título no meio dos vídeos de verdade
  // Só na tela da pessoa: nada é enviado a ninguém. Funciona na página inicial e na busca.

  const PROVA = { capa: "", titulo: "", canal: "Seu canal" };
  const telaDeProvar = () => location.pathname === "/" || location.pathname === "/results";

  function botaoProvar() {
    let b = document.querySelector(".radar-provar-botao");
    if (!telaDeProvar()) { if (b) b.remove(); document.querySelectorAll(".radar-provar-card").forEach((c) => c.remove()); return; }
    if (!b) document.body.append(h("button", { class: "radar-provar-botao", onclick: abrirProvar }, "🧪 Provar capa e título"));
    if (PROVA.capa && !document.querySelector(".radar-provar-card")) porCartao();
  }

  function abrirProvar() {
    document.querySelectorAll(".radar-janela-fundo").forEach((j) => j.remove());
    const fundo = h("div", { class: "radar-janela-fundo", onclick: (e) => { if (e.target === fundo) fundo.remove(); } });
    const arquivo = h("input", { type: "file", accept: "image/*" });
    const titulo = h("input", { type: "text", maxlength: "100", placeholder: "O título do seu vídeo", value: PROVA.titulo });
    const canal = h("input", { type: "text", maxlength: "60", placeholder: "Nome do canal", value: PROVA.canal });
    const aviso = h("div", { class: "radar-fraco" }, "Aparece como o primeiro vídeo da página, só na sua tela. Nada é enviado.");
    fundo.append(h("div", { class: "radar-janela radar-janela-pequena" },
      h("div", { class: "radar-janela-cab" }, h("b", {}, "Provar capa e título"),
        h("button", { class: "radar-janela-x", title: "Fechar", onclick: () => fundo.remove() }, "×")),
      h("label", { class: "radar-campo" }, "A capa (imagem 16:9)", arquivo),
      h("label", { class: "radar-campo" }, "O título", titulo),
      h("label", { class: "radar-campo" }, "O canal", canal),
      aviso,
      h("div", { class: "radar-acoes" },
        h("button", { class: "radar-botao radar-botao-forte", onclick: () => {
          const f = arquivo.files[0];
          if (!f && !PROVA.capa) { aviso.textContent = "Escolha a imagem da capa."; return; }
          if (f) { if (PROVA.capa) URL.revokeObjectURL(PROVA.capa); PROVA.capa = URL.createObjectURL(f); }
          PROVA.titulo = titulo.value.trim() || "Seu título aqui";
          PROVA.canal = canal.value.trim() || "Seu canal";
          fundo.remove(); porCartao(); window.scrollTo({ top: 0, behavior: "smooth" });
        } }, "Pôr no meio dos vídeos"),
        PROVA.capa ? h("button", { class: "radar-botao", onclick: () => { tirarProva(); fundo.remove(); } }, "Tirar da página") : null)));
    document.body.append(fundo);
  }

  function tirarProva() {
    document.querySelectorAll(".radar-provar-card").forEach((c) => c.remove());
    if (PROVA.capa) URL.revokeObjectURL(PROVA.capa);
    PROVA.capa = "";
  }

  function porCartao() {
    document.querySelectorAll(".radar-provar-card").forEach((c) => c.remove());
    if (!PROVA.capa) return;
    const busca = location.pathname === "/results";
    const primeiro = busca ? document.querySelector("ytd-search ytd-video-renderer") : document.querySelector("ytd-rich-grid-renderer ytd-rich-item-renderer");
    if (!primeiro) return;
    const inicial = (PROVA.canal[0] || "?").toUpperCase();
    const card = h("div", { class: `radar-provar-card ${busca ? "na-busca" : "no-inicio"}` },
      h("div", { class: "radar-provar-capa" }, h("img", { src: PROVA.capa, alt: "" }), h("span", { class: "radar-provar-dur" }, "12:34"),
        h("button", { class: "radar-provar-x", title: "Tirar da página", onclick: (e) => { e.preventDefault(); tirarProva(); } }, "×")),
      h("div", { class: "radar-provar-info" }, h("span", { class: "radar-provar-avatar" }, inicial),
        h("div", {}, h("div", { class: "radar-provar-titulo" }, PROVA.titulo),
          h("div", { class: "radar-provar-meta" }, PROVA.canal), h("div", { class: "radar-provar-meta" }, "12 mil visualizações • há 1 dia"))));
    if (!busca) {   // na grade do início, o mesmo tamanho dos outros cartões
      const est = getComputedStyle(primeiro);
      Object.assign(card.style, { width: primeiro.getBoundingClientRect().width + "px", marginLeft: est.marginLeft, marginRight: est.marginRight, marginBottom: est.marginBottom });
    }
    primeiro.parentElement.insertBefore(card, primeiro);
  }

  // ------------------------------------------------------------ esconder os Shorts (ligado no ícone da extensão)

  const semShorts = (sim) => document.documentElement.classList.toggle("radar-sem-shorts", !!sim);
  chrome.storage.local.get("semShorts").then(({ semShorts: s }) => semShorts(s));

  // o selo do Radar e o 🎯 do treino, em cima de cada miniatura
  function varrer() {
    document.querySelectorAll(CAIXAS).forEach((caixa) => {
      if (caixa.parentElement && caixa.parentElement.closest(CAIXAS)) return;
      const link = caixa.querySelector('a[href*="/watch?v="], a[href*="/shorts/"]');
      const id = idDoLink(link && link.getAttribute("href"));
      if (!id) return;
      selarCartao(caixa, id);
      if (treino && caixa.dataset.alvo !== id) marcarAlvo(caixa, id);
    });
  }

  // ------------------------------------------------------------ o selo em cima da miniatura
  // Quantas vezes o vídeo passou do normal do canal, o selo do achado raro e a reação do público, na própria capa:
  // o vídeo que estourou salta da tela sem abrir nada. Só desenha o que o Radar já sabe — o resto chega depois.

  let reacaoAlta = 2;            // o corte vem do Radar (vistos.reacao_alta); este é só o valor de partida

  function selarCartao(caixa, id) {
    const v = PAGINA.get(id);
    const nada = !v || (v.nota == null && !v.raridade && v.reacao == null);
    const assinatura = nada ? "" : `${id}|${v.nota ?? ""}|${v.raridade || ""}|${v.reacao ?? ""}`;
    if (caixa.dataset.selo === assinatura) return;
    caixa.dataset.selo = assinatura;
    caixa.querySelectorAll(".radar-selo").forEach((s) => s.remove());
    if (nada) return;
    const lugar = caixa.querySelector(IMAGEM) || caixa;
    if (getComputedStyle(lugar).position === "static") lugar.style.position = "relative";
    const partes = [];
    if (v.nota != null) {
      partes.push(h("span", { class: `radar-selo-x ${corNota(v.nota)}`, title: `${nota(v.nota)} o normal deste canal${v.normal ? ` (${num(v.normal)} por vídeo)` : ""}` }, nota(v.nota)));
    }
    if (v.raridade && SELOS[v.raridade]) {
      partes.push(h("span", { class: `radar-selo-raro ${v.raridade}`, title: `Canal ${SELOS[v.raridade]}: muita view por vídeo em pouco tempo de canal` }, SELOS[v.raridade]));
    }
    if (v.reacao != null && v.reacao >= reacaoAlta) {
      partes.push(h("span", { class: "radar-selo-reacao", title: `O público reagiu ${nota(v.reacao)} mais que o normal do nicho (curtidas e comentários por view)` }, "♥", nota(v.reacao)));
    }
    if (partes.length) lugar.append(h("div", { class: "radar-selo" }, partes));
  }

  // ------------------------------------------------------------ treino do algoritmo: o selo 🎯 e o progresso

  // o canal escolhido no ícone ("Treinar para"): as palavras do assunto dele e a lista do treino
  let treino = null; // { id, titulo, palavras: Set }: o canal escolhido no ícone e as palavras do treino dele
  const VAZIAS = new Set(["the", "and", "that", "this", "with", "from", "what", "como", "para", "mais", "voce", "video", "videos",
    "documentary", "documentario", "full", "completo", "most", "best", "never", "nunca", "about", "your", "sobre", "porque"]);
  const chaves = (t) => new Set((t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .match(/[a-z0-9]{4,}/g)?.filter((p) => !VAZIAS.has(p)) || []);

  async function carregarTreino() {
    const { canalTreino } = await chrome.storage.local.get("canalTreino");
    if (!canalTreino) { treino = null; return; }
    const r = await api(`/api/ext/assunto/${encodeURIComponent(canalTreino.id)}`);
    if (r.erro) { treino = null; return; }
    treino = { id: canalTreino.id, titulo: r.dados.titulo, palavras: new Set(r.dados.palavras) };
    document.querySelectorAll("[data-alvo]").forEach((c) => { delete c.dataset.alvo; });
  }

  function combina(titulo) {
    if (!treino) return false;
    let n = 0;
    for (const p of chaves(titulo)) if (treino.palavras.has(p) && ++n >= 2) return true;
    return false;
  }

  function marcarAlvo(caixa, id) {
    caixa.dataset.alvo = id;
    caixa.querySelectorAll(".radar-alvo").forEach((s) => s.remove());
    const tituloEl = caixa.querySelector("#video-title, .yt-lockup-metadata-view-model__title, h3");
    const titulo = tituloEl ? tituloEl.textContent.trim() : "";
    if (!combina(titulo)) return;
    const lugar = caixa.querySelector(IMAGEM) || caixa;
    if (getComputedStyle(lugar).position === "static") lugar.style.position = "relative";
    const botao = h("button", { class: "radar-alvo-botao", title: `Salvar ideia em ${treino.titulo}` }, "+ ideia");
    botao.addEventListener("click", async (e) => {
      e.preventDefault(); e.stopPropagation();
      const r = await api("/api/ideias-salvas", "POST", { video_id: id, titulo, canal_id: treino.id });
      botao.textContent = r.erro ? "erro" : "salva ✓";
    });
    lugar.append(h("div", { class: "radar-alvo", title: `Combina com ${treino.titulo}` }, h("span", {}, "🎯"), botao));
  }

  // ------------------------------------------------------------ painel do vídeo

  function botaoSalvar(canal, salvo) {
    const b = h("button", { class: "radar-botao" }, salvo ? "Salvo ✓" : "Salvar canal");
    b.addEventListener("click", async () => {
      const r = await api(`/api/ext/salvar/${canal.id}`, b.textContent.startsWith("Salvo") ? "DELETE" : "POST");
      if (r.erro) return mostrarErro(b, r.erro);
      b.textContent = r.dados.salvo ? "Salvo ✓" : "Salvar canal";
    });
    return b;
  }

  function mostrarErro(perto, texto) {
    const e = h("div", { class: "radar-erro" }, texto);
    perto.after(e); setTimeout(() => e.remove(), 5000);
  }

  function listaDeCanais(canais) {
    return h("div", { class: "radar-lista" }, canais.length ? canais.slice(0, 15).map((c) =>
      h("a", { class: "radar-item", href: `https://www.youtube.com/${c.handle || "channel/" + c.id}` },
        h("img", { src: c.foto, alt: "" }),
        h("span", {}, h("b", {}, c.titulo), h("small", {}, `${num(c.normal_longos)} por vídeo · ${num(c.inscritos)} inscritos${c.fase ? " · " + (FASES[c.fase] || c.fase) : ""}`))))
      : h("div", { class: "radar-fraco" }, "Nenhum parecido achado."));
  }

  async function outrasLinguas(id, onde) {
    onde.replaceChildren(h("div", { class: "radar-fraco" }, "Traduzindo o título…"));
    const r = await api(`/api/ext/linguas/${id}`);
    if (r.erro) return onde.replaceChildren(h("div", { class: "radar-erro" }, r.erro));
    onde.replaceChildren(h("div", { class: "radar-sub" }, "Busque o mesmo assunto em cada língua (abre os mais vistos):"),
      h("div", { class: "radar-lista" }, r.dados.linguas.map((l) =>
        h("a", { class: "radar-item", href: l.link, target: "_blank", rel: "noopener" }, h("span", {}, h("b", {}, l.nome), h("small", {}, l.busca))))));
  }

  async function parecidos(canalId, onde) {
    onde.replaceChildren(h("div", { class: "radar-fraco" }, "Procurando canais parecidos…"));
    const r = await api(`/api/ext/parecidos/${canalId}`);
    if (r.erro) return onde.replaceChildren(h("div", { class: "radar-erro" }, r.erro));
    onde.replaceChildren(h("div", { class: "radar-sub" }, "Canais que fazem o mesmo tipo de vídeo:"), listaDeCanais(r.dados.canais));
  }

  // ------------------------------------------------------------ a busca do YouTube de verdade (para o Método Fantasma)
  // O radar de países saiu do site (2026-10-14): a API do YouTube gastava ~800 da cota por clique e via só 50
  // resultados, noutra ordem. Aqui a extensão abre a página de busca de cada país, como a pessoa abriria, sem cota.
  // O servidor só traduz o título (Groq, grátis) e julga os resultados com as regras testadas (radar_paises.julgar).

  function achar(obj, tipo, saida = []) {
    if (!obj || typeof obj !== "object") return saida;
    if (obj[tipo]) saida.push(obj[tipo]);
    for (const v of Object.values(obj)) if (v && typeof v === "object") achar(v, tipo, saida);
    return saida;
  }
  const texto = (t) => !t ? "" : t.simpleText || (t.runs || []).map((r) => r.text).join("");

  async function buscarNoYoutube(busca, pais, lingua) {
    const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(busca)}&gl=${pais}&hl=${lingua}`;
    const html = await (await fetch(url)).text();
    // os dados vêm num <script id="yt-initial-data" type="application/json"> (o jeito antigo era "var ytInitialData = ...")
    const m = html.match(/id="yt-initial-data"[^>]*>([\s\S]*?)<\/script>/) || html.match(/var ytInitialData = (\{.*?\});<\/script>/s);
    if (!m) return [];
    return achar(JSON.parse(m[1]), "videoRenderer").map((v) => ({
      id: v.videoId, titulo: texto(v.title), canal: texto(v.ownerText), views: texto(v.viewCountText), publicado: texto(v.publishedTimeText),
    })).filter((v) => v.id && v.titulo);
  }

  const bandeira = (c) => h("img", { class: "radar-bandeira", src: `https://flagcdn.com/w40/${c.toLowerCase()}.png`, alt: "" });



  // ------------------------------------------------------------ ponte com o leitor.js: o vídeo aberto e a transcrição

  let pedidos = 0;
  const esperando = new Map();
  window.addEventListener("message", (e) => {
    if (e.source !== window || !e.data || !e.data.radarResposta) return;
    const f = esperando.get(e.data.radarResposta);
    if (f) { esperando.delete(e.data.radarResposta); f(e.data.dados); }
  });
  const pedirPagina = (tipo, id) => new Promise((ok) => {
    const n = ++pedidos;
    esperando.set(n, ok);
    window.postMessage({ radarPedido: n, tipo, id }, location.origin);
    setTimeout(() => { if (esperando.delete(n)) ok(null); }, 15000);
  });
  const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
  const minSeg = (s) => s == null ? "—" : s >= 3600 ? `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`
    : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  // ------------------------------------------------------------ painel do vídeo (sem cota: a página e o banco do Radar)

  async function painelDoVideo(id) {
    document.querySelectorAll(".radar-painel").forEach((p) => p.remove());
    document.querySelectorAll(".radar-fantasma-janela").forEach((j) => { j.hidden = true; });
    if (FANTASMA.id !== id) zerarFantasma(id, "");
    const lugar = document.querySelector("#secondary-inner, #secondary");
    if (!lugar) return;
    const painel = h("div", { class: "radar-painel", "data-id": id }, h("div", { class: "radar-fraco" }, "Radar: lendo o vídeo…"));
    lugar.prepend(painel);
    const vivo = () => painel.dataset.id === id && painel.isConnected;
    // o player pode ainda estar no vídeo anterior: espera ele trocar
    let v = null;
    for (let i = 0; i < 20 && vivo(); i++) {
      v = await pedirPagina("video");
      if (v && v.id === id) break;
      v = null;
      await espera(500);
    }
    if (!vivo()) return;
    if (!v) return painel.replaceChildren(h("div", { class: "radar-fraco" }, "Radar: não consegui ler este vídeo. Recarregue a página."));
    const anuncio = v.anuncios && v.canal_id ? { id: v.canal_id, anuncios: true } : null;
    let r = await api("/api/ext/vistos", "POST", { videos: [v], canal: anuncio });
    if (r.erro) return painel.replaceChildren(h("div", { class: "radar-fraco" }, r.status === 401 ? "Radar: entre na sua conta pelo ícone da extensão." : `Radar: ${r.erro}`));
    let p = await api(`/api/ext/painel/${id}?canal=${encodeURIComponent(v.canal_id || "")}`);
    if (!p.erro && !p.dados.canal && v.canal_id) {   // canal que o Radar não conhece: lê a página dele e pergunta de novo
      painel.replaceChildren(h("div", { class: "radar-fraco" }, "Radar: lendo o canal (sem gastar cota)…"));
      lidos.add(v.canal_id);
      await lerCanal(v.canal_id);
      r = await api("/api/ext/vistos", "POST", { videos: [v] });
      p = await api(`/api/ext/painel/${id}?canal=${encodeURIComponent(v.canal_id)}`);
    }
    if (!vivo()) return;
    desenharPainel(painel, v, (r.dados && r.dados.videos[id]) || {}, p.erro ? {} : p.dados);
  }

  function desenharPainel(painel, v, n, p) {
    const c = p.canal || {}, lite = ["lite", "pro"].includes(p.plano), id = v.id;
    const extra = h("div", { class: "radar-extra" });
    const corpo = h("div", { class: "radar-aba-corpo" });
    // a Capa é a aba principal: a capa com o "quantos x" em vermelho em cima
    const abas = [["capa", "Capa"], ["transcricao", "Transcrição"], ["lingua", "Método Fantasma"]];
    const botoesAba = abas.map(([k, t]) => h("button", { class: "radar-aba", "data-aba": k, onclick: () => abrir(k) }, t));
    const abrir = (k) => {
      botoesAba.forEach((b) => b.classList.toggle("ligada", b.dataset.aba === k));
      corpo.replaceChildren(...({ capa: abaCapa, transcricao: abaTranscricao, lingua: abaLingua }[k])());
    };
    const capaUrl = `https://i.ytimg.com/vi/${id}/maxresdefault.jpg`;
    const abaCapa = () => {
      const img = h("img", { class: "radar-capa", src: capaUrl, alt: "" });
      img.addEventListener("error", () => { if (!img.src.includes("hqdefault")) img.src = `https://i.ytimg.com/vi/${id}/hqdefault.jpg`; });
      // a capa menor, e à direita os números que importam (o "quantos x" em vermelho no topo)
      const dias = v.publicado ? (Date.now() - Date.parse(v.publicado)) / 864e5 : null;
      const quadros = [
        ["fogo", nota(n.nota), "do normal", "radar-quadro-x"],
        ["olho", num(v.views), idade(dias) || "views"],
        ["raio", v.views && dias != null ? num(Math.round(v.views / Math.max(1, dias))) : "—", "por dia"],
        ["barras", num(n.normal), "normal"],
        ["parecidos", num(c.inscritos), "inscritos"],
        ["relogio", v.duracao_s ? minSeg(v.duracao_s) : "—", "duração"],
      ];
      return [h("div", { class: "radar-capa-linha" }, img,
        h("div", { class: "radar-quadros" }, quadros.map(([ic, x, rotulo, classe]) =>
          h("div", { class: `radar-quadro ${classe || ""}` }, h("div", {}, icone(ic), h("b", {}, x)), h("small", {}, rotulo)))))];
    };
    let transcrita = null;
    const abaTranscricao = () => {
      const lista = h("div", { class: "radar-transcricao" }, h("div", { class: "radar-fraco" }, "Lendo a fala do vídeo…"));
      const mostrar = (t) => {
        if (!t || !t.linhas.length) return lista.replaceChildren(h("div", { class: "radar-fraco" }, "Este vídeo não tem transcrição."));
        lista.replaceChildren(...t.linhas.map((l) => h("div", { class: "radar-trecho" },
          h("button", { class: "radar-tempo", title: "Ir para este trecho", onclick: () => { const vid = document.querySelector("video"); if (vid) vid.currentTime = l.ms / 1000; } },
            minSeg(Math.floor(l.ms / 1000))), h("span", {}, l.texto))));
      };
      if (transcrita) mostrar(transcrita);
      else pedirPagina("transcricao", id).then((t) => { transcrita = t; mostrar(t); });
      const copiar = (comTempos) => (e) => {
        if (!transcrita || !transcrita.linhas.length) return;
        navigator.clipboard.writeText(comTempos ? transcrita.linhas.map((l) => `[${minSeg(Math.floor(l.ms / 1000))}] ${l.texto}`).join("\n")
          : transcrita.linhas.map((l) => l.texto).join(" "));
        e.currentTarget.lastChild.textContent = "Copiado ✓";
      };
      return [h("div", { class: "radar-acoes radar-acoes-2" },
        botao("radar-botao radar-botao-vermelho", "titulo", "Copiar sem tempos", copiar(false)),
        botao("radar-botao", "relogio", "Copiar com tempos", copiar(true))), lista];
    };
    // Método Fantasma: a busca fica guardada em FANTASMA; a aba e a janelinha do fantasminha mostram a mesma
    if (FANTASMA.id !== id) zerarFantasma(id, v.titulo); else FANTASMA.titulo = v.titulo;
    const vista = vistaFantasma(painel, true);
    const rodarFantasma = (e) => { metodoFantasma(e.currentTarget); abrir("lingua"); };
    const abaLingua = () => [vista];
    painel.radarTranscricao = abaTranscricao;   // a janelinha da Transcrição (menu Radar) usa a mesma aba
    painel.replaceChildren(
      h("div", { class: "radar-abas" }, botoesAba), corpo,
      h("div", { class: "radar-acoes radar-acoes-2" },
        botao("radar-botao radar-botao-sombra", "fantasma", "Método Fantasma", rodarFantasma, "sombra", "Alt+G"),
        botao("radar-botao radar-botao-forte", "roteiro", "Levar ao Roteiro", () =>
          chrome.runtime.sendMessage({ tipo: "radar", caminho: `/#/trabalho?ref=${id}&titulo=${encodeURIComponent(v.titulo)}` }), "roteiro", "Alt+R"),
        botao("radar-botao", "ideia", treino ? "Salvar ideia em " + treino.titulo : "Salvar ideia", async (e) => {
          const rot = e.currentTarget.lastChild;
          const s = await api("/api/ideias-salvas", "POST", { video_id: id, titulo: v.titulo, canal_id: treino ? treino.id : "" });
          rot.textContent = s.erro ? s.erro : "Ideia salva ✓";
        }, "ideia"),
        botao("radar-botao", "titulo", "Copiar título", (e) => { navigator.clipboard.writeText(v.titulo); e.currentTarget.lastChild.textContent = "Título copiado ✓"; }, "titulo"),
        botao("radar-botao", "capa", "Copiar a capa", (e) => copiarImagem(e.currentTarget.lastChild, capaUrl), "copiar-capa"),
        botao("radar-botao", "barras", "Print do cartão", (e) => copiarCartao(e.currentTarget.lastChild, capaUrl, v, c, n), "print-cartao"),
        lite && c.id ? botao("radar-botao", "parecidos", "Canais parecidos", () => parecidos(c.id, extra)) : null),
      extra);
    abrir("capa");
  }

  // ------------------------------------------------------------ Método Fantasma: em que língua ninguém fez este vídeo
  // Uma busca por vídeo, guardada em FANTASMA: a aba do painel e a janelinha do fantasminha (embaixo do vídeo) mostram
  // a mesma busca e se atualizam quando ela anda.
  const NOME_LINGUA = { pt: "Português", en: "Inglês", es: "Espanhol", fr: "Francês", de: "Alemão", it: "Italiano", nl: "Holandês",
    pl: "Polonês", tr: "Turco", ja: "Japonês", ko: "Coreano", id: "Indonésio", ru: "Russo", ar: "Árabe" };
  const nomeLingua = (p) => NOME_LINGUA[p.lingua] || p.lingua;
  const SITUACAO = (p) => !p.feito ? ["livre", "Ninguém fez"] : p.forca === "fraco" ? ["fraco", "Feito, mas fraco"]
    : p.forca === "medio" ? ["medio", "Já fizeram"] : ["forte", "Já fizeram e foi bem"];
  const ANDANDO = ["traduzindo", "procurando", "julgando"];

  const FANTASMA = { id: null, titulo: "", fase: "", paises: [], feitos: new Set(), lista: null, erro: "", vez: 0, ouvintes: new Set() };
  function avisarFantasma() {
    FANTASMA.ouvintes.forEach((f) => f());
    const F = FANTASMA, livres = F.lista ? F.lista.filter((p) => !p.feito).length : 0;
    const selo = F.fase === "pronto" ? String(livres) : F.fase === "procurando" ? `${F.feitos.size}/${F.paises.length}` : ANDANDO.includes(F.fase) ? "…" : "";
    document.querySelectorAll(".radar-fantasma-botao").forEach((b) => {
      b.classList.toggle("buscando", ANDANDO.includes(F.fase)); b.classList.toggle("pronto", F.fase === "pronto");
      b.querySelector("em").textContent = selo;
    });
  }
  function zerarFantasma(id, titulo) {
    Object.assign(FANTASMA, { id, titulo, fase: "", paises: [], feitos: new Set(), lista: null, erro: "", vez: FANTASMA.vez + 1 });
    avisarFantasma();
  }

  async function metodoFantasma(origem) {
    const F = FANTASMA;
    if (origem && F.paises.length) voarFantasmas(origem, F.paises);   // a busca já tem os países: voam já
    if (!F.id || !F.titulo || ANDANDO.includes(F.fase) || F.fase === "pronto") return;
    const vez = ++F.vez, vale = () => F.vez === vez;   // trocou de vídeo no meio: para
    Object.assign(F, { fase: "traduzindo", paises: [], feitos: new Set(), lista: null, erro: "" }); avisarFantasma();
    const prep = await api("/api/ext/radar/preparar", "POST", { titulo: F.titulo });
    if (!vale()) return;
    if (prep.erro) { Object.assign(F, { fase: "erro", erro: prep.erro }); return avisarFantasma(); }
    Object.assign(F, { fase: "procurando", paises: prep.dados.paises }); avisarFantasma();
    if (origem && origem.isConnected) voarFantasmas(origem, F.paises);
    const resultados = {};
    await Promise.all(F.paises.map(async (p, i) => {
      try { resultados[p.codigo] = await buscarNoYoutube(p.busca, p.codigo, p.lingua); } catch { resultados[p.codigo] = []; }
      if (vale()) { F.feitos.add(i); avisarFantasma(); }
    }));
    if (!vale()) return;
    F.fase = "julgando"; avisarFantasma();
    const r = await api("/api/ext/radar/julgar", "POST", { preparo: prep.dados, resultados, video_id: F.id });
    if (!vale()) return;
    if (r.erro) { Object.assign(F, { fase: "erro", erro: r.erro }); return avisarFantasma(); }
    Object.assign(F, { fase: "pronto", lista: r.dados.paises }); avisarFantasma();
  }

  // a cena: o anel verde enche a cada língua procurada e o fantasminha flutua no meio; no fim cada língua ganha a cor
  // do que achou. `cheia` = a do painel (clicar numa língua mostra os vídeos achados); `dono` saiu da página = a vista para.
  function vistaFantasma(dono, cheia, verNoPainel) {
    const R = 52, volta = +(2 * Math.PI * R).toFixed(1);
    const arco = novoSvg("circle", { cx: 60, cy: 60, r: R, class: "radar-anel-arco", "stroke-dasharray": volta, "stroke-dashoffset": volta, transform: "rotate(-90 60 60)" });
    const anel = novoSvg("svg", { viewBox: "0 0 120 120", class: "radar-anel" });
    anel.append(novoSvg("circle", { cx: 60, cy: 60, r: R, class: "radar-anel-fundo" }), arco);
    const conta = h("b", {}), legenda = h("small", {}), aviso = h("div", { class: "radar-fantasma-aviso" });
    const grade = h("div", { class: "radar-sombra-chips" }), detalhes = h("div", { class: "radar-lista" });
    const comecar = botao("radar-grande", "fantasma", "Procurar com o Método Fantasma", (e) => metodoFantasma(e.currentTarget));
    const el = h("div", { class: `radar-fantasma-vista${cheia ? "" : " compacta"}` },
      h("div", { class: "radar-cena" }, h("span", { class: "radar-cena-brilho" }), anel, h("span", { class: "radar-cena-fantasma" }, icone("fantasma"))),
      h("div", { class: "radar-cena-conta" }, conta, legenda), aviso, comecar, grade,
      verNoPainel ? botao("radar-ver-painel", "olho", "Ver os vídeos de cada língua", verNoPainel) : null, detalhes);
    let chips = [], montada = null, ligada = false;
    const mostrar = (p) => detalhes.replaceChildren(
      h("div", { class: "radar-sub" }, `${nomeLingua(p)} (${p.pais}): ${SITUACAO(p)[1]}. Procurei “${p.busca}”.`),
      ...p.parecidos.map((x) => h("a", { class: "radar-item", href: `https://www.youtube.com/watch?v=${x.id}` },
        h("img", { src: `https://i.ytimg.com/vi/${x.id}/default.jpg`, alt: "", style: "width:56px;height:32px;border-radius:5px" }),
        h("span", {}, h("b", {}, x.titulo), h("small", {}, `${x.canal} · ${num(x.views)} views${x.publicado ? " · " + x.publicado : ""}`)))),
      h("a", { class: "radar-item", href: p.link, target: "_blank", rel: "noopener" }, h("small", {}, "Ver a busca no YouTube →")));
    function atualizar() {
      if (dono.isConnected) ligada = true;
      else if (ligada) return FANTASMA.ouvintes.delete(atualizar);
      const F = FANTASMA, total = F.paises.length, feitos = F.feitos.size;
      el.dataset.fase = F.fase || "parado";
      if (montada !== F.paises) {
        montada = F.paises;
        chips = F.paises.map((p) => h("button", { class: "radar-sombra-chip", type: "button" }, bandeira(p.codigo), h("span", {}, nomeLingua(p)), h("i", {})));
        grade.replaceChildren(...chips); detalhes.replaceChildren();
      }
      arco.setAttribute("stroke-dashoffset", total ? volta * (1 - feitos / total) : volta);
      chips.forEach((c, i) => c.classList.toggle("achado", F.feitos.has(i)));
      comecar.hidden = F.fase !== "" && F.fase !== "erro";
      comecar.lastChild.textContent = F.fase === "erro" ? "Tentar de novo" : "Procurar com o Método Fantasma";
      aviso.classList.toggle("radar-erro", F.fase === "erro");
      if (F.fase === "pronto") {
        const livres = F.lista.filter((p) => !p.feito);
        conta.textContent = livres.length; legenda.textContent = `${livres.length === 1 ? "livre" : "livres"} de ${F.lista.length} línguas`;
        aviso.textContent = livres.length ? "Livre em " + livres.map(nomeLingua).join(", ").replace(/, ([^,]*)$/, " e $1") : "Já fizeram em todas as línguas procuradas.";
        F.lista.forEach((p) => {
          const c = chips[F.paises.findIndex((x) => x.codigo === p.codigo)];
          if (!c) return;
          const [classe, texto] = SITUACAO(p);
          c.classList.add(classe); c.title = texto;
          if (cheia) c.onclick = () => mostrar(p);
        });
      } else {
        conta.textContent = F.fase === "procurando" || F.fase === "julgando" ? feitos : "";
        legenda.textContent = total ? `de ${total} línguas` : "";
        aviso.textContent = { traduzindo: "Traduzindo o título para cada língua…", procurando: "Procurando no YouTube de cada país…",
          julgando: "Vendo quem já fez…", erro: F.erro }[F.fase]
          || "Em que língua ninguém fez este vídeo ainda: o título traduzido, procurado no YouTube de cada país (não gasta cota).";
      }
    }
    FANTASMA.ouvintes.add(atualizar);
    atualizar();
    return el;
  }

  // os fantasminhas saem voando de onde a busca começou, um por país, cada um levando a bandeira dele por cima do
  // vídeo (caminhos diferentes, um depois do outro) e somem lá em cima
  function voarFantasmas(de, paises) {
    const r = de.getBoundingClientRect(), x0 = r.left + r.width / 2, y0 = r.top + r.height / 2;
    const tela = document.querySelector("#movie_player") || document.querySelector("video");
    const a = tela ? tela.getBoundingClientRect() : { left: 0, top: 0, width: innerWidth, height: innerHeight };
    const sorte = (min, max) => min + Math.random() * (max - min);
    paises.forEach((p, i) => {
      const voa = h("div", { class: "radar-fantasma-voando", style: `left:${x0 - 16}px;top:${y0 - 16}px` }, icone("fantasma"), p.codigo ? bandeira(p.codigo) : null);
      const fim = paises.length > 1 ? .08 + .84 * (i / (paises.length - 1)) : .5;   // cada um sai num ponto do alto do vídeo
      const ir = (fx, fy, esc, gira) => `translate(${a.left + a.width * fx - x0}px, ${a.top + a.height * fy - y0}px) scale(${esc}) rotate(${gira}deg)`;
      const meio = (fim + .5) / 2;
      setTimeout(() => {
        document.body.append(voa);
        voa.animate([
          { transform: "translate(0, 0) scale(.6) rotate(0deg)", opacity: 0 },
          { transform: ir(sorte(.3, .7), sorte(.7, .85), 1.5, sorte(-15, 15)), opacity: 1, offset: .25 },
          { transform: ir(meio + sorte(-.08, .08), sorte(.4, .6), 2.3, sorte(-12, 12)), opacity: 1, offset: .55 },
          { transform: ir(fim, sorte(.12, .25), 3.1, sorte(-8, 8)), opacity: 1, offset: .85 },
          { transform: ir(fim, -.05, 3.6, 0), opacity: 0 },
        ], { duration: sorte(1700, 2200), easing: "ease-in-out" }).finished.then(() => voa.remove(), () => voa.remove());
      }, i * 170);
    });
  }

  // a capa (do i.ytimg.com, pela extensão) num <img> que o canvas pode usar
  async function capaLimpa(url) {
    let r = await new Promise((ok) => chrome.runtime.sendMessage({ tipo: "imagem", url }, ok));
    if ((!r || r.erro) && url.includes("maxresdefault")) r = await new Promise((ok) => chrome.runtime.sendMessage({ tipo: "imagem", url: url.replace("maxresdefault", "hqdefault") }, ok));
    if (!r || r.erro) throw new Error((r && r.erro) || "sem capa");
    const img = new Image();
    img.src = `data:${r.tipo};base64,${r.base64}`;
    await img.decode();
    return img;
  }

  async function copiarPng(canvas) {
    const blob = await new Promise((ok) => canvas.toBlob(ok, "image/png"));
    await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
  }

  async function copiarImagem(botao, url) {
    try {
      const img = await capaLimpa(url);
      const cv = Object.assign(document.createElement("canvas"), { width: img.naturalWidth, height: img.naturalHeight });
      cv.getContext("2d").drawImage(img, 0, 0);
      await copiarPng(cv);
      botao.textContent = "Capa copiada ✓ (Ctrl+V para colar)";
    } catch { botao.textContent = "Não consegui copiar"; }
  }

  // ------------------------------------------------------------ print do cartão do vídeo
  // A capa com o título, o canal, as views, a idade e a nota numa imagem só, para colar no WhatsApp ou no grupo.
  // Nada sai do navegador: o desenho é num canvas aqui mesmo e vai direto para a área de transferência.

  const CARTAO = { largura: 760, capa: 428, margem: 26 };

  // quebra o texto em até `linhas` linhas, com "…" onde não couber (uma palavra sozinha maior que a linha é cortada)
  function quebrar(ctx, texto, largura, linhas) {
    const cabe = (t) => ctx.measureText(t).width <= largura;
    const encurtar = (t) => { while (t.length > 1 && !cabe(`${t}…`)) t = t.slice(0, -1); return `${t}…`; };
    const todas = [];
    let atual = "";
    for (const p of String(texto || "").split(/\s+/).filter(Boolean)) {
      const tenta = atual ? `${atual} ${p}` : p;
      if (cabe(tenta) || !atual) { atual = tenta; continue; }   // sem nada na linha, a palavra entra mesmo grande
      todas.push(atual);
      atual = p;
    }
    if (atual) todas.push(atual);
    const saida = todas.slice(0, linhas);
    if (saida.length && todas.length > linhas) saida[saida.length - 1] = encurtar(saida[saida.length - 1]);
    return saida.map((l) => (cabe(l) ? l : encurtar(l)));
  }

  function caixaArredondada(ctx, x, y, w, hh, r) {
    ctx.beginPath();
    ctx.roundRect ? ctx.roundRect(x, y, w, hh, r) : ctx.rect(x, y, w, hh);
    ctx.fill();
  }

  async function copiarCartao(botao, capaUrl, v, c, n) {
    try {
      const img = await capaLimpa(capaUrl);
      const { largura: L, capa: H, margem: M } = CARTAO;
      const cv = Object.assign(document.createElement("canvas"), { width: L, height: H + 196 });
      const ctx = cv.getContext("2d");
      ctx.fillStyle = "#0d0f14";
      ctx.fillRect(0, 0, cv.width, cv.height);
      // a capa recortada para 16:9, sem deformar
      const escala = Math.max(L / img.naturalWidth, H / img.naturalHeight);
      const lw = img.naturalWidth * escala, lh = img.naturalHeight * escala;
      ctx.drawImage(img, (L - lw) / 2, (H - lh) / 2, lw, lh);
      // a nota em cima da capa, no mesmo lugar em que ela aparece no YouTube
      const x = n && n.nota != null ? nota(n.nota) : "";
      if (x) {
        ctx.font = "700 30px Roboto, Arial, sans-serif";
        const w = ctx.measureText(x).width + 28;
        ctx.fillStyle = n.nota >= 6 ? "#b6f23a" : "rgba(0,0,0,.78)";
        caixaArredondada(ctx, M, M, w, 50, 12);
        ctx.fillStyle = n.nota >= 6 ? "#10160a" : "#fff";
        ctx.textBaseline = "middle";
        ctx.fillText(x, M + 14, M + 26);
      }
      // o título, em até duas linhas
      ctx.textBaseline = "alphabetic";
      ctx.fillStyle = "#eef1f7";
      ctx.font = "700 30px Roboto, Arial, sans-serif";
      let y = H + 52;
      for (const linha of quebrar(ctx, v.titulo, L - M * 2, 2)) { ctx.fillText(linha, M, y); y += 38; }
      // o canal e os números
      ctx.fillStyle = "#8d95a8";
      ctx.font = "400 22px Roboto, Arial, sans-serif";
      ctx.fillText(quebrar(ctx, c && c.titulo ? c.titulo : "", L - M * 2 - 40, 1)[0] || "", M, y + 10);
      const partes = [n && n.views != null ? `${num(n.views)} views` : "", v.dias != null ? `há ${Math.round(v.dias)} dias` : "",
        c && c.inscritos != null ? `${num(c.inscritos)} inscritos` : ""].filter(Boolean);
      ctx.fillText(partes.join("  ·  "), M, y + 44);
      // a assinatura, para o print se explicar sozinho quando for parar num grupo
      ctx.fillStyle = "#b6f23a";
      ctx.font = "700 18px Roboto, Arial, sans-serif";
      const marca = "Radar de Canais";
      ctx.fillText(marca, L - M - ctx.measureText(marca).width, y + 44);
      await copiarPng(cv);
      botao.textContent = "Cartão copiado ✓ (Ctrl+V para colar)";
    } catch { botao.textContent = "Não consegui copiar"; }
  }

  // ------------------------------------------------------------ página do canal (sem cota: a página e o banco do Radar)

  const SVG = "http://www.w3.org/2000/svg";
  const svg = (tag, at = {}) => { const e = document.createElementNS(SVG, tag); for (const [k, v] of Object.entries(at)) e.setAttribute(k, v); return e; };

  // os inscritos por dia (linha) e as views dos últimos vídeos (barras: mais forte quando estourou)
  function graficoInscritos(dias) {
    if (!dias || dias.length < 2) return h("div", { class: "radar-fraco" }, "O gráfico de inscritos aparece depois de o Radar ver o canal em dias diferentes.");
    const vs = dias.map((d) => d.inscritos), max = Math.max(...vs), min = Math.min(...vs);
    const g = svg("svg", { viewBox: "0 0 300 70", class: "radar-grafico" });
    g.append(svg("polyline", { points: vs.map((x, i) => `${(i / (vs.length - 1)) * 300},${66 - ((x - min) / Math.max(1, max - min)) * 60}`).join(" ") }));
    const ganho = vs[vs.length - 1] - vs[0];
    return h("div", {}, h("div", { class: "radar-sub" }, `Inscritos: ${ganho >= 0 ? "+" : ""}${num(ganho)} em ${dias.length} dias vistos`), g);
  }
  function graficoVideos(videos) {
    const lista = (videos || []).filter((v) => v.views != null);
    if (lista.length < 2) return null;
    const max = Math.max(...lista.map((v) => v.views)), w = 300 / lista.length;
    const g = svg("svg", { viewBox: "0 0 300 70", class: "radar-barras" });
    lista.forEach((v, i) => {
      const a = Math.max(2, (v.views / max) * 66);
      const r = svg("rect", { x: i * w + 1, y: 68 - a, width: Math.max(1, w - 2), height: a, class: nivel(v.nota) });
      r.append(svg("title")); r.firstChild.textContent = `${v.titulo}: ${num(v.views)} views${v.nota != null ? " · " + nota(v.nota) : ""}`;
      g.append(r);
    });
    return h("div", {}, h("div", { class: "radar-sub" }, `Views dos últimos ${lista.length} vídeos (do mais antigo ao mais novo)`), g);
  }
  function monetizacao(c) {
    return [c.anuncios === 1 ? h("span", { class: "radar-tag" }, "💰 com anúncios") : null,
      c.membros === 1 ? h("span", { class: "radar-tag" }, "⭐ tem membros") : null].filter(Boolean);
  }

  // ------------------------------------------------------------ página do canal
  // Junto do Inscrever-se: o botão "Analisar nicho" (o fantasminha voa e abre a análise embaixo do cabeçalho). Junto
  // das abas do YouTube: "Canais Parecidos" e "Vídeos do Nicho". (A faixa solta embaixo do cabeçalho saiu.)
  const corNota = (x) => x == null ? "" : x >= 15 ? "vermelha" : x >= 6 ? "verde" : "apagada";
  const postando = (c) => c.meses_postando == null ? "—" : c.meses_postando < 1 ? "menos de 1 mês"
    : `${Math.round(c.meses_postando)} ${Math.round(c.meses_postando) === 1 ? "mês" : "meses"}${c.primeiro_exato ? "" : "+"}`;

  function sairDoCanal() {
    document.querySelectorAll(".radar-do-canal").forEach((e) => e.remove());
    document.querySelectorAll(".radar-yt-escondido").forEach((e) => e.classList.remove("radar-yt-escondido"));
  }

  // a vida de um nicho, pelo tempo que o canal posta: cada fase com o começo (dias) e onde fica no gráfico (0 a 1)
  const FASES_NICHO = [
    { nome: "Teste de mercado", ate: 14, x: [0, .2], entrar: ["cedo", "melhor hora de entrar"] },
    { nome: "Decolagem", ate: 60, x: [.2, .4], entrar: ["cedo", "melhor hora de entrar"] },
    { nome: "Corrida por espaço", ate: 120, x: [.4, .6], entrar: ["meio", "ainda dá para entrar"] },
    { nome: "Maturidade", ate: 420, x: [.6, .8], entrar: ["tarde", "tarde para entrar"] },
    { nome: "Saturação", ate: 730, x: [.8, 1], entrar: ["fim", "nicho saturado"] },
  ];
  const ROTULOS_DIAS = ["0", "14 dias", "2 meses", "4 meses", "14 meses", "2 anos +"];
  const faseDoNicho = (dias) => { const i = FASES_NICHO.findIndex((f) => dias < f.ate); return i < 0 ? FASES_NICHO.length - 1 : i; };
  function xDoNicho(dias) {   // onde o canal fica no gráfico (cada fase tem o mesmo espaço, mesmo durando mais)
    const i = faseDoNicho(dias), f = FASES_NICHO[i], de = i ? FASES_NICHO[i - 1].ate : 0;
    return Math.min(.97, f.x[0] + (f.x[1] - f.x[0]) * Math.min(1, (dias - de) / (f.ate - de)));
  }
  // a força do nicho ao longo do tempo: sobe, fica alta e cai na saturação (0 = embaixo, 1 = em cima)
  const forcaDoNicho = (x) => (.12 + .72 / (1 + Math.exp(-14 * (x - .25)))) * (x > .82 ? 1 - Math.pow((x - .82) / .18, 2) * .7 : 1);

  // o que o Radar acha do nicho, explicado: a fase pelo tempo que o canal posta e a força pelos últimos vídeos
  // a régua é 100 mil views (como a do Dotti): quantos vídeos do canal passaram disso, e quantos dos 10 mais novos
  function vereditoDoNicho(c) {
    const dias = c.meses_postando != null ? Math.round(c.meses_postando * 30.44) : null;
    const todos = c.videos || [], recentes = todos.slice(-10);
    const grandes = todos.filter((v) => v.views >= 100000).length, agora = recentes.filter((v) => v.views >= 100000).length;
    const forca = agora >= 3 ? ["forte", "forte agora"] : agora ? ["morno", "morno agora"] : ["fraco", "fraco agora"];
    const i = dias == null ? null : faseDoNicho(dias);
    const provas = grandes ? `${grandes} ${grandes === 1 ? "vídeo passou" : "vídeos passaram"} de 100.000 views`
      : "Nenhum vídeo passou de 100.000 views";
    let titulo, texto;
    if (i == null) { titulo = "Sem a idade do canal ainda"; texto = provas + "."; }
    else if (i <= 1) [titulo, texto] = grandes ? ["Boa hora para entrar", `${provas}: o nicho está nascendo e já dá resultado.`]
      : ["Nicho novo, ainda testando", `${provas}: ainda não deu para saber se pega.`];
    else if (i === 2) [titulo, texto] = grandes ? ["Ainda dá para entrar, rápido", `${provas}: outros canais estão chegando agora.`]
      : ["Corrida sem vencedor", `${provas}: muitos tentando, ninguém estourando.`];
    else [titulo, texto] = grandes ? ["Bom para tirar ideias de títulos", `${provas} — vale copiar o título, não o canal.`]
      : ["Nicho cansado", `${provas}: melhor procurar outro nicho.`];
    const temProxima = i != null && i < FASES_NICHO.length - 1;
    return { dias, i, forca, titulo, texto, falta: temProxima ? FASES_NICHO[i].ate - dias : null, proxima: temProxima ? FASES_NICHO[i + 1].nome : null };
  }

  // "como um nicho nasce e morre": a curva, as cinco fases (as que passaram com ✓, a de agora acesa) e o canal nela
  function graficoDoNicho(c, ver) {
    const L = 1000, A = 180, pontos = [];
    for (let k = 0; k <= 100; k++) { const x = k / 100; pontos.push([x * L, A - forcaDoNicho(x) * A * .92]); }
    const linha = pontos.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    const g = novoSvg("svg", { viewBox: `0 0 ${L} ${A}`, preserveAspectRatio: "none", class: "radar-nicho-curva" });
    const grad = novoSvg("linearGradient", { id: "radar-nicho-cor", x1: 0, x2: 1, y1: 0, y2: 0 });
    [["0", "#39d98a"], [".45", "#39d98a"], [".62", "#f5b83d"], [".8", "#e8742c"], ["1", "#e53935"]]
      .forEach(([o, cor]) => grad.append(novoSvg("stop", { offset: o, "stop-color": cor })));
    const defs = novoSvg("defs"); defs.append(grad);
    g.append(defs,
      novoSvg("polygon", { points: `0,${A} ${linha} ${L},${A}`, fill: "url(#radar-nicho-cor)", opacity: ".14" }),
      novoSvg("polyline", { points: linha, fill: "none", stroke: "url(#radar-nicho-cor)", "stroke-width": 4, "vector-effect": "non-scaling-stroke" }));
    const colunas = FASES_NICHO.map((f, k) => {
      const estado = ver.i == null ? "" : k < ver.i ? "passou" : k === ver.i ? "agora" : "depois";
      const de = k ? FASES_NICHO[k - 1].ate : 0;
      return h("div", { class: `radar-nicho-fase ${estado}` },
        h("b", {}, estado === "passou" ? "✓ " : "", f.nome),
        estado === "agora" ? h("small", {}, `${de}–${f.ate} dias`) : k === 0 && estado !== "agora" ? h("small", { class: "verde" }, "melhor hora de entrar") : null);
    });
    const x = ver.dias != null ? xDoNicho(ver.dias) : null;
    const marca = x == null ? null : h("div", { class: "radar-nicho-marca", style: `left:${x * 100}%;top:${(1 - forcaDoNicho(x) * .92) * 100}%` },
      c.foto ? h("img", { src: c.foto, alt: "", referrerpolicy: "no-referrer" }) : icone("fantasma"));
    return h("div", { class: "radar-nicho-grafico" },
      h("div", { class: "radar-nicho-fases" }, colunas),
      h("div", { class: "radar-nicho-area" }, h("span", { class: "radar-nicho-eixo-y" }, "força do nicho ↑"), g, marca,
        x == null ? null : h("i", { class: "radar-nicho-linha", style: `left:${x * 100}%` })),
      h("div", { class: "radar-nicho-dias" }, ROTULOS_DIAS.map((t) => h("span", {}, t))),
      h("div", { class: "radar-nicho-eixo-x" }, "tempo postando →"));
  }

  // os concorrentes do nicho (os canais parecidos) e a nota de 0 a 10. Procurar os parecidos gasta cota do YouTube:
  // se ainda não foram procurados, aparece o botão; se já foram (aba Canais Parecidos, outra análise), vem direto
  function concorrentesDoNicho(c) {
    const caixa = h("div", { class: "radar-concorrentes" }, h("div", { class: "radar-fraco" }, "Vendo os concorrentes do nicho…"));
    const carregar = async (medir) => {
      if (medir) caixa.replaceChildren(h("div", { class: "radar-fraco" }, "Procurando os concorrentes no YouTube…"));
      const r = await api(`/api/ext/concorrentes/${c.id}${medir ? "?medir=1" : ""}`);
      if (r.erro) return caixa.replaceChildren(h("div", { class: "radar-erro" }, erroDoRadar(r)));
      const d = r.dados;
      if (!d.medido) return caixa.replaceChildren(
        h("div", { class: "radar-concorrentes-cab" }, icone("parecidos"), h("b", {}, "Concorrentes do nicho"), h("span", { class: "radar-fraco" }, "ainda não medidos")),
        h("p", {}, "Para dar a nota do nicho, o Radar procura no YouTube quem faz o mesmo tipo de vídeo (gasta um pouco da cota, fica guardado 7 dias)."),
        botao("radar-ver-painel", "parecidos", "Medir os concorrentes", () => carregar(true)));
      const classe = d.nota >= 7 ? "cedo" : d.nota >= 4 ? "meio" : "fim";
      const numeros = [["Concorrentes", d.total], ["Postaram no último mês", d.ativos], ["Crescendo", d.crescendo], ["Novos que deram certo", d.novos_que_deram_certo]];
      caixa.replaceChildren(
        h("div", { class: "radar-concorrentes-cab" }, icone("parecidos"), h("b", {}, "Concorrentes do nicho"),
          h("span", { class: `radar-nicho-nota ${classe}` }, h("b", {}, String(d.nota).replace(".", ",")), "/10"),
          h("span", { class: `radar-nicho-pilula ${classe}` }, d.rotulo)),
        h("div", { class: "radar-concorrentes-numeros" }, numeros.map(([k, x]) => h("div", {}, h("b", {}, x), h("small", {}, k)))),
        d.canais.length ? h("div", { class: "radar-concorrentes-canais" }, d.canais.map((x) =>
          h("a", { href: `https://www.youtube.com/${x.handle || "channel/" + x.id}`, title: x.titulo },
            h("img", { src: x.foto, alt: "", referrerpolicy: "no-referrer" }),
            h("span", {}, h("b", {}, x.titulo), h("small", {}, `${num(x.normal_longos)} por vídeo`))))) : null,
        h("p", {}, "A nota sobe com concorrentes crescendo (há procura) e com canais novos que já fazem 10 mil por vídeo (dá para entrar); ",
          "desce quando muitos postaram no último mês (pouco espaço). Os concorrentes são os canais parecidos."));
    };
    carregar(false);
    return caixa;
  }

  function analiseDoCanal(c, ver) {
    const estouraram = (c.videos || []).filter((v) => v.nota >= 2).sort((a, b) => b.nota - a.nota).slice(0, 5);
    const entrar = ver.i == null ? ["", "—"] : FASES_NICHO[ver.i].entrar;
    const quadros = [
      ["usuario", num(c.inscritos), "inscritos"], ["barras", num(c.normal_longos), "normal por vídeo"],
      ["play", c.videos_total ?? "—", "vídeos"], ["calendario", postando(c), "postando há"],
    ];
    return [
      h("div", { class: "radar-nicho-corpo" },
        h("div", { class: "radar-nicho-lado" },
          h("div", { class: "radar-nicho-veredito" },
            h("span", { class: "radar-nicho-ic" }, icone("ideia")),
            h("div", {}, h("b", {}, ver.titulo), h("span", { class: `radar-nicho-pilula ${ver.forca[0]}` }, ver.forca[1]), h("p", {}, ver.texto))),
          h("div", { class: "radar-nicho-dias-card" },
            h("div", {}, h("b", {}, ver.dias ?? "—"), h("span", {}, " dias postando")),
            h("span", { class: `radar-nicho-pilula ${entrar[0]}` }, entrar[1]),
            h("p", {}, ver.falta != null ? `${ver.falta} ${ver.falta === 1 ? "dia" : "dias"} para a ${ver.proxima}` : ver.i != null ? "O nicho já passou da saturação." : ""))),
        h("div", { class: "radar-nicho-direita" },
          h("div", { class: "radar-nicho-titulo" }, icone("fantasma"), h("b", {}, "Como um nicho nasce e morre")),
          graficoDoNicho(c, ver))),
      concorrentesDoNicho(c),
      h("p", { class: "radar-nicho-explica" }, "Como ler: o tempo que o canal posta mostra em que fase o nicho está. Nas primeiras fases é mais fácil entrar; ",
        "da maturidade em diante, vale copiar os títulos que estouraram, não o canal. A força vem dos 10 vídeos mais novos: quantos passaram de 100.000 views."),
      h("details", { class: "radar-nicho-mais" }, h("summary", {}, "Números do canal e os vídeos que estouraram"),
        h("div", { class: "radar-analise-cab" }, c.raridade && h("span", { class: `radar-tag ${c.raridade}` }, SELOS[c.raridade]),
          c.fase && h("span", { class: `radar-tag ${c.fase}` }, FASES[c.fase] || c.fase), ...monetizacao(c),
          h("span", { class: "radar-analise-acoes" }, botaoSalvar(c, c.salvo))),
        h("div", { class: "radar-quadros radar-quadros-4" }, quadros.map(([ic, x, rotulo]) =>
          h("div", { class: "radar-quadro" }, h("div", {}, icone(ic), h("b", {}, x)), h("small", {}, rotulo)))),
        h("div", { class: "radar-graficos" }, graficoVideos(c.videos), graficoInscritos(c.inscritos_dias)),
        estouraram.length ? h("div", { class: "radar-lista" }, h("div", { class: "radar-sub" }, "Os que passaram do normal"),
          estouraram.map((v) => h("a", { class: "radar-item", href: `https://www.youtube.com/watch?v=${v.id}` },
            h("span", { class: `rf-nota ${corNota(v.nota)}` }, nota(v.nota)), h("span", {}, h("b", {}, v.titulo), h("small", {}, `${num(v.views)} views`)))))
          : h("div", { class: "radar-fraco" }, "Nenhum vídeo recente passou de 2x o normal do canal.")),
    ];
  }

  const erroDoRadar = (r) => r.status === 404 && /not found/i.test(r.erro || "")
    ? "O servidor do Radar está desatualizado: feche e abra de novo o LIGAR-RADAR.bat." : r.erro;
  function miniVideo(v) {
    const d = v.publicado ? (Date.now() - Date.parse(v.publicado)) / 864e5 : null;
    return h("a", { class: "radar-mini-video", href: `https://www.youtube.com/watch?v=${v.id}` },
      h("div", { class: "rf-capa" }, h("img", { src: `https://i.ytimg.com/vi/${v.id}/mqdefault.jpg`, alt: "", loading: "lazy" }),
        v.duracao_s ? h("span", { class: "rf-dur" }, minSeg(v.duracao_s)) : null),
      h("b", {}, v.titulo),
      h("small", {}, [`${num(v.views)} views`, idade(d)].filter(Boolean).join(" · ")),
      v.nota != null ? h("span", { class: `rf-nota ${corNota(v.nota)}` }, nota(v.nota)) : null);
  }

  // as abas do Radar junto das do YouTube: abrir uma esconde o conteúdo do YouTube; clicar numa aba dele volta
  function abasDoCanal(c, cab) {
    const lista = document.querySelector("ytd-tabbed-page-header [role=tablist], ytd-browse[page-subtype='channels'] [role=tablist], #tabsContent");
    if (!lista) return;
    const conteudo = document.querySelector("ytd-browse[page-subtype='channels'] ytd-two-column-browse-results-renderer, ytd-browse ytd-two-column-browse-results-renderer");
    const secao = h("div", { class: "radar-do-canal radar-canal-secao", hidden: "" });
    const fechar = () => {
      secao.hidden = true;
      abas.forEach((a) => a.classList.remove("ligada"));
      if (conteudo) conteudo.classList.remove("radar-yt-escondido");
    };
    const abrir = (aba, montar) => {
      abas.forEach((a) => a.classList.toggle("ligada", a === aba));
      secao.hidden = false;
      if (conteudo) conteudo.classList.add("radar-yt-escondido");
      montar();
    };
    const parecidosAba = h("button", { class: "radar-do-canal radar-aba-yt", type: "button" }, icone("parecidos"), "Canais Parecidos");
    const nichoAba = h("button", { class: "radar-do-canal radar-aba-yt", type: "button" }, icone("fantasma"), "Vídeos do Nicho");
    const abas = [parecidosAba, nichoAba];
    parecidosAba.onclick = (e) => { e.stopPropagation(); abrir(parecidosAba, async () => {
      secao.replaceChildren(h("div", { class: "radar-fraco" }, "Procurando canais que fazem o mesmo tipo de vídeo…"));
      const r = await api(`/api/ext/parecidos/${c.id}`);
      if (r.erro) return secao.replaceChildren(h("div", { class: "radar-erro" }, erroDoRadar(r)));
      secao.replaceChildren(h("div", { class: "radar-parecidos-linhas" }, r.dados.canais.length ? r.dados.canais.map((x) =>
        h("div", { class: "radar-parecido-linha" },
          h("a", { class: "radar-canal-cartao", href: `https://www.youtube.com/${x.handle || "channel/" + x.id}` },
            h("img", { src: x.foto, alt: "", referrerpolicy: "no-referrer" }), h("b", {}, x.titulo),
            h("small", {}, `${num(x.normal_longos)} por vídeo · ${num(x.inscritos)} inscritos`),
            x.fase ? h("span", { class: `radar-tag ${x.fase}` }, FASES[x.fase] || x.fase) : null),
          h("div", { class: "radar-parecido-videos" }, (x.videos || []).length ? x.videos.map(miniVideo)
            : h("div", { class: "radar-fraco" }, "O Radar ainda não tem os vídeos deste canal."))))
        : [h("div", { class: "radar-fraco" }, "Nenhum parecido achado.")]));
    }); };
    nichoAba.onclick = (e) => { e.stopPropagation(); abrir(nichoAba, async () => {
      secao.replaceChildren(h("div", { class: "radar-fraco" }, "Juntando o que estourou nos canais parecidos…"));
      const r = await api(`/api/ext/nicho-videos/${c.id}`);
      if (r.erro) return secao.replaceChildren(h("div", { class: "radar-erro" }, erroDoRadar(r)));
      const vs = r.dados.videos;
      secao.replaceChildren(vs.length ? h("div", { class: "rf-grade radar-nicho-grade" }, vs.map((v) => {
        const d = v.publicado ? (Date.now() - Date.parse(v.publicado)) / 864e5 : null;
        return h("a", { class: "rf-card", href: `https://www.youtube.com/watch?v=${v.id}` },
          h("div", { class: "rf-capa" }, h("img", { src: `https://i.ytimg.com/vi/${v.id}/mqdefault.jpg`, alt: "", loading: "lazy" }),
            v.duracao_s ? h("span", { class: "rf-dur" }, minSeg(v.duracao_s)) : null),
          h("div", { class: "rf-info" }, v.foto ? h("img", { class: "rf-letra", src: v.foto, alt: "", referrerpolicy: "no-referrer" }) : h("span", { class: "rf-letra" }, (v.canal || "?")[0]),
            h("div", {}, h("b", { class: "rf-titulo" }, v.titulo),
              h("div", { class: "rf-meta" }, [v.canal, v.inscritos != null ? `${num(v.inscritos)} inscritos` : null].filter(Boolean).join(" · ")),
              h("div", { class: "rf-meta" }, [`${num(v.views)} views`, idade(d)].filter(Boolean).join(" · ")),
              h("div", { class: "rf-pilulas" }, h("span", { class: `rf-nota ${corNota(v.nota)}` }, nota(v.nota))))));
      })) : h("div", { class: "radar-fraco" }, "Os canais parecidos ainda não têm vídeos que passaram do normal no Radar."));
    }); };
    // uma aba do YouTube clicada: a seção do Radar some e o conteúdo dele volta
    lista.addEventListener("click", (e) => { if (!abas.some((a) => a.contains(e.target))) fechar(); });
    const ultima = [...lista.querySelectorAll("yt-tab-shape, [role=tab], tp-yt-paper-tab")].filter((t) => !t.closest(".radar-aba-yt")).pop();
    if (ultima) ultima.after(parecidosAba, nichoAba); else lista.append(parecidosAba, nichoAba);
    if (conteudo) conteudo.before(secao);
    else (lista.closest("ytd-tabbed-page-header, #tabs-container, tp-yt-app-toolbar") || cab).after(secao);
  }

  // o $ ao lado do nome do canal: verde = monetizado (o player mostra anúncio), cinza riscado = sem anúncio.
  // Se o Radar ainda não sabe, abre o vídeo mais novo do canal (como a pessoa abriria) e olha a marca "yt_ad" que o
  // próprio YouTube põe nos dados do player de vídeo com anúncio; o resultado vai para o banco.
  async function seloDinheiro(c, cab) {
    const nome = cab.querySelector("yt-page-header-view-model h1, #channel-name h1, h1, #channel-name");
    if (!nome) return;
    const selo = h("span", { class: "radar-do-canal radar-dinheiro" }, "$");
    const pintar = (sim) => {
      selo.className = `radar-do-canal radar-dinheiro ${sim === true ? "sim" : sim === false ? "nao" : ""}`;
      selo.title = sim === true ? "Canal monetizado: os vídeos têm anúncio" : sim === false ? "Canal sem anúncio nos vídeos (não monetizado)"
        : "Radar: vendo se o canal é monetizado…";
    };
    pintar(c.anuncios === 1 ? true : c.anuncios === 0 ? false : null);
    nome.append(selo);
    if (c.anuncios != null) return;
    const ultimo = (c.videos || []).slice(-1)[0];
    if (!ultimo) return pintar(undefined);
    try {
      const html = await (await fetch(`https://www.youtube.com/watch?v=${ultimo.id}`)).text();
      const m = html.match(/"key":"yt_ad","value":"([01])"/);
      if (!m) return pintar(undefined);
      const sim = m[1] === "1";
      pintar(sim);
      api("/api/ext/vistos", "POST", { videos: [], canal: { id: c.id, anuncios: sim } });
    } catch { pintar(undefined); }
  }

  async function painelDoCanal(ref) {
    sairDoCanal();
    const cab = document.querySelector("ytd-browse[page-subtype='channels'] #page-header, ytd-browse #header, #page-header");
    if (!cab) return;
    const analisar = h("button", { class: "radar-analisar", disabled: "", title: "Analisar o nicho deste canal (Alt+G)" }, icone("fantasma"), h("span", {}, "Lendo o canal…"), h("i", { class: "radar-seta" }, "▾"));
    const resumo = h("div", { class: "radar-nicho-resumo" });
    const analise = h("div", { class: "radar-canal-analise", hidden: "" });
    const caixa = h("div", { class: "radar-do-canal radar-nicho-caixa", "data-ref": ref }, h("div", { class: "radar-nicho-barra" }, analisar, resumo), analise);
    const barraDeAbas = document.querySelector("ytd-tabbed-page-header #tabs-container, ytd-tabbed-page-header tp-yt-app-toolbar");
    if (barraDeAbas) barraDeAbas.before(caixa); else cab.after(caixa);
    const vivo = () => caixa.dataset.ref === ref && caixa.isConnected;
    const aviso = (t) => { analisar.querySelector("span").textContent = t; };
    const confere = (c) => c && (ref.startsWith("UC") ? c.id === ref : (c.handle || "").toLowerCase() === ref.toLowerCase());
    let canal = null;
    for (let i = 0; i < 20 && vivo() && !confere(canal); i++) { canal = await pedirPagina("canal"); if (!confere(canal)) await espera(500); }
    if (!vivo()) return;
    if (!confere(canal)) return aviso("Radar: recarregue a página");
    let r = await api(`/api/ext/canal-dados/${canal.id}`);
    if (r.status === 404) {   // o Radar ainda não conhece: lê a página de vídeos dele (sem cota) e pergunta de novo
      aviso("Lendo os vídeos do canal…");
      lidos.add(canal.id);
      await lerCanal(canal.id);
      r = await api(`/api/ext/canal-dados/${canal.id}`);
    }
    if (!vivo()) return;
    if (r.erro) return aviso(`Radar: ${r.erro}`);
    const c = r.dados, ver = vereditoDoNicho(c);
    analise.append(...analiseDoCanal(c, ver));
    resumo.replaceChildren(h("b", {}, ver.titulo), h("small", {}, [ver.i != null ? FASES_NICHO[ver.i].nome : null, ver.dias != null ? `${ver.dias} dias` : null].filter(Boolean).join(" · ")));
    analisar.disabled = false;
    aviso("Analisar nicho");
    analisar.onclick = () => {
      analise.hidden = !analise.hidden;
      caixa.classList.toggle("aberta", !analise.hidden);
      if (!analise.hidden) voarFantasmas(analisar, [{}, {}, {}, {}]);
    };
    abasDoCanal(c, cab);
    seloDinheiro(c, cab);
  }

  // ------------------------------------------------------------ Alt+S: salvar o canal do vídeo aberto ou da página do canal

  function avisoRapido(texto) {
    document.querySelectorAll(".radar-aviso").forEach((a) => a.remove());
    const a = h("div", { class: "radar-aviso" }, texto);
    document.body.append(a);
    setTimeout(() => a.remove(), 3500);
  }
  chrome.runtime.onMessage.addListener((msg) => { if (msg && msg.tipo === "salvar-canal") salvarCanalDaPagina(); });
  // os atalhos da página: Alt+S salva o canal, Alt+G é o fantasminha (Método Fantasma no vídeo, Analisar nicho no
  // canal), Alt+R leva o vídeo ao Roteiro e Alt+V abre os filtros dos vídeos da página. Alt+F e Alt+D ficam com o
  // Chrome (menu e barra de endereço). O atalho do Chrome (commands) fica com uma extensão só (o Dotti Finder também
  // usa Alt+S): a página ouve também.
  const clicar = (seletor, senao) => { const b = document.querySelector(seletor); if (b && !b.disabled) b.click(); else avisoRapido(senao); };
  const TECLAS = {
    KeyS: () => salvarCanalDaPagina(),
    KeyG: () => document.querySelector(".radar-analisar") ? clicar(".radar-analisar", "Radar: o canal ainda está carregando.")
      : clicar(".radar-fantasma-botao", "Radar: abra um vídeo para usar o Método Fantasma."),
    KeyR: () => clicar('.radar-painel [data-acao="roteiro"]', "Radar: abra um vídeo para levar ao Roteiro."),
    KeyV: () => [...PAGINA.values()].some((v) => v.views != null) ? abrirFiltros() : avisoRapido("Radar: ainda não li vídeos nesta página."),
  };
  document.addEventListener("keydown", (e) => {
    if (!e.altKey || e.ctrlKey || e.shiftKey || e.metaKey || !TECLAS[e.code]) return;
    if (e.target.closest && e.target.closest("input, textarea, [contenteditable]")) return;
    e.preventDefault();
    TECLAS[e.code]();
  }, true);
  let salvando = 0;
  function salvarCanalDaPagina() {
    if (Date.now() - salvando < 1500) return;   // o atalho do Chrome e o da página no mesmo aperto: salva uma vez
    salvando = Date.now();
    (async () => {
      const naPagina = location.pathname === "/watch" ? await pedirPagina("video") : await pedirPagina("canal");
      const id = naPagina && (naPagina.canal_id || naPagina.id);
      if (!id || !/^UC[\w-]{22}$/.test(id)) return avisoRapido("Radar: abra um vídeo ou a página de um canal para salvar.");
      const r = await api(`/api/ext/salvar/${id}`, "POST");
      avisoRapido(r.erro ? `Radar: ${r.erro}` : `Radar: canal salvo ✓ ${naPagina.canal || naPagina.titulo || ""}`);
      document.querySelectorAll(".radar-painel .radar-botao, .radar-canal-analise .radar-botao").forEach((b) => { if (b.textContent === "Salvar canal") b.textContent = "Salvo ✓"; });
    })();
  }

  // ------------------------------------------------------------ canais novos em alta, no topo da página inicial

  let emAlta = null;
  async function faixaEmAlta() {
    const velha = document.querySelector(".radar-alta");
    if (location.pathname !== "/") { if (velha) velha.remove(); return; }
    const { altaFechada } = await chrome.storage.local.get("altaFechada");
    if (altaFechada === new Date().toDateString()) { if (velha) velha.remove(); return; }
    const grade = document.querySelector("ytd-browse[page-subtype='home'] ytd-rich-grid-renderer #contents");
    if (!grade || (velha && velha.isConnected)) return;
    if (!emAlta) { const r = await api("/api/ext/em-alta"); emAlta = r.erro ? [] : r.dados.canais; }
    if (!emAlta.length || document.querySelector(".radar-alta")) return;
    const faixa = h("div", { class: "radar-alta" },
      h("div", { class: "radar-alta-cab" }, h("b", {}, "🔥 Canais novos em alta"), h("span", { class: "radar-fraco" }, "do Radar: começaram há até 3 meses e já fazem muita view por vídeo"),
        h("button", { class: "radar-janela-x", title: "Esconder hoje", onclick: () => { chrome.storage.local.set({ altaFechada: new Date().toDateString() }); faixa.remove(); } }, "×")),
      h("div", { class: "radar-alta-lista" }, emAlta.map((c) => h("a", { class: "radar-alta-canal", href: `https://www.youtube.com/${c.handle || "channel/" + c.id}` },
        h("img", { src: c.foto, alt: "", referrerpolicy: "no-referrer" }),
        h("b", {}, c.titulo),
        h("small", {}, `${num(c.normal_longos)} por vídeo · ${num(c.inscritos)} inscritos`),
        h("small", {}, c.meses_postando != null ? `começou há ${c.meses_postando < 1 ? Math.max(1, Math.round(c.meses_postando * 30.44)) + " dias" : Math.round(c.meses_postando) + (Math.round(c.meses_postando) === 1 ? " mês" : " meses")}` : "")))));
    grade.parentElement.insertBefore(faixa, grade);
  }

  // ------------------------------------------------------------ o botão Radar embaixo do vídeo (com o menu)
  // Cada item abre a aba do painel ao lado ou aperta o botão dele: o painel continua sendo o lugar de tudo.

  // null = uma linha separando o que se vê (abas) do que se faz (ações)
  const ITENS_MENU = [
    ["capa", "capa", "Capa e números", "a capa com quantos x deu"],
    ["transcricao", "transcricao", "Transcrição", "a fala com os tempos"],
    ["sombra", "fantasma", "Método Fantasma", "em que língua ninguém fez", true, "Alt+G"],
    null,
    ["roteiro", "roteiro", "Levar ao Roteiro", "abre o Roteiro com este vídeo", false, "Alt+R"],
    ["ideia", "ideia", "Salvar ideia", "guarda no painel do Radar"],
    ["titulo", "titulo", "Copiar o título", "vai para a área de transferência"],
    ["copiar-capa", "capa", "Copiar a capa", "a imagem, para colar onde quiser"],
    ["print-cartao", "barras", "Print do cartão", "a capa com o título e os números"],
  ];

  // a Transcrição numa janelinha presa embaixo do botão Radar (fecha no × ou trocando de vídeo)
  function janelaTranscricao(botao, aba) {
    document.querySelectorAll(".radar-transcricao-janela").forEach((j) => j.remove());
    const janela = h("div", { class: "radar-transcricao-janela" },
      h("div", { class: "radar-janela-cab" }, h("span", { class: "radar-janela-ic" }, icone("transcricao")), h("b", {}, "Transcrição"),
        h("button", { class: "radar-janela-fechar", title: "Fechar", onclick: () => janela.remove() }, "×")),
      ...aba());
    document.body.append(janela);
    const prender = () => {
      if (!janela.isConnected) return removeEventListener("scroll", prender);
      const r = botao.getBoundingClientRect(), largura = janela.offsetWidth;
      janela.style.left = `${Math.min(Math.max(8, r.left), innerWidth - largura - 8)}px`;
      janela.style.top = `${Math.max(8, Math.min(r.bottom + 8, innerHeight - 200))}px`;
    };
    prender();
    addEventListener("scroll", prender, { passive: true });
    document.addEventListener("yt-navigate-start", () => janela.remove(), { once: true });
  }

  function menuDoVideo() {
    if (location.pathname !== "/watch") return;
    // ficam grandes no meio da fileira de baixo do título (entre o canal e o curtir), onde sobra espaço; sem essa
    // fileira, à direita do título; sem os dois, junto dos botões do YouTube
    const lugar = document.querySelector("ytd-watch-metadata #top-row") || document.querySelector("ytd-watch-metadata #title")
      || document.querySelector("ytd-watch-metadata #top-level-buttons-computed, ytd-watch-metadata #actions-inner");
    if (!lugar || lugar.querySelector(".radar-menu")) return;
    const lista = h("div", { class: "radar-menu-lista", hidden: "" });
    const botao = h("button", { class: "radar-menu-botao", title: "Radar de Canais" }, h("i", {}), "Radar", h("span", {}, "▾"));
    const caixa = h("div", { class: "radar-menu" }, botao, lista);
    const fechar = () => { lista.hidden = true; };
    botao.addEventListener("click", (e) => { e.stopPropagation(); lista.hidden = !lista.hidden; });
    document.addEventListener("click", (e) => { if (!caixa.contains(e.target)) fechar(); });
    lista.append(...ITENS_MENU.map((item) => !item ? h("hr", { class: "radar-menu-sep" }) : h("button", { class: `radar-menu-item${item[4] ? " destaque" : ""}`, onclick: (e) => {
      const k = item[0];
      e.stopPropagation(); fechar();
      const painel = document.querySelector(".radar-painel");
      if (!painel) return avisoRapido("Radar: o painel do vídeo ainda está carregando.");
      // a Transcrição abre logo abaixo do botão (no painel ao lado ela ficava lá embaixo quando a coluna desce)
      if (k === "transcricao" && painel.radarTranscricao) return janelaTranscricao(botao, painel.radarTranscricao);
      painel.scrollIntoView({ behavior: "smooth", block: "start" });
      const aba = painel.querySelector(`.radar-aba[data-aba="${k}"]`);
      if (aba) return aba.click();
      const acao = painel.querySelector(`[data-acao="${k}"]`);
      if (acao) acao.click();
    } }, h("span", { class: "radar-menu-ic" }, icone(item[1])), h("span", {}, h("b", {}, item[2]), h("small", {}, item[3])),
      item[5] ? h("kbd", { class: "radar-tecla" }, item[5]) : null)));
    // o fantasminha ao lado do Radar: voa pela tela, abre a janelinha do Método Fantasma ali mesmo e começa a busca
    // (a janelinha fica no <body>, presa ao botão por conta: dentro da fileira do YouTube ela saía no lugar errado)
    document.querySelectorAll(".radar-fantasma-janela").forEach((j) => j.remove());
    const janela = h("div", { class: "radar-fantasma-janela", hidden: "" });
    const prender = () => {
      if (janela.hidden) return;
      const r = fantasma.getBoundingClientRect(), largura = janela.offsetWidth || 310;
      janela.style.left = `${Math.min(Math.max(8, r.left + r.width / 2 - largura / 2), innerWidth - largura - 8)}px`;
      const cabeAcima = r.top - 70 > janela.offsetHeight;   // cabe acima do botão? senão abre embaixo
      janela.style.bottom = cabeAcima ? `${innerHeight - r.top + 10}px` : "auto";
      janela.style.top = cabeAcima ? "auto" : `${r.bottom + 10}px`;
    };
    const fantasma = h("button", { class: "radar-fantasma-botao", title: "Método Fantasma: em que língua ninguém fez este vídeo (Alt+G)", onclick: (e) => {
      e.stopPropagation();
      if (!janela.hidden) { janela.hidden = true; return; }
      if (!FANTASMA.id || !FANTASMA.titulo) return avisoRapido("Radar: o painel do vídeo ainda está carregando.");
      janela.hidden = false;
      prender();
      metodoFantasma(fantasma);
    } }, icone("fantasma"), h("em", {}));
    addEventListener("scroll", prender, { passive: true });
    addEventListener("resize", prender);
    new ResizeObserver(prender).observe(janela);   // a janelinha cresce quando o resultado chega: continua presa
    const caixaFantasma = h("div", { class: "radar-fantasma-caixa" }, fantasma);
    janela.append(
      h("div", { class: "radar-janela-cab" }, h("span", { class: "radar-janela-ic" }, icone("fantasma")), h("b", {}, "Método Fantasma"),
        h("button", { class: "radar-janela-fechar", title: "Fechar", onclick: () => { janela.hidden = true; } }, "×")),
      vistaFantasma(caixaFantasma, false, () => {
        janela.hidden = true;
        const painel = document.querySelector(".radar-painel");
        if (!painel) return;
        painel.scrollIntoView({ behavior: "smooth", block: "start" });
        const aba = painel.querySelector('.radar-aba[data-aba="lingua"]');
        if (aba) aba.click();
      }));
    janela.addEventListener("click", (e) => e.stopPropagation());
    document.addEventListener("click", () => { janela.hidden = true; });
    const juntos = h("div", { class: "radar-titulo-botoes" }, caixa, caixaFantasma);
    if (lugar.id === "top-row") { const dono = lugar.querySelector(":scope > #owner"); juntos.classList.add("radar-grandes"); if (dono) dono.after(juntos); else lugar.prepend(juntos); }
    else if (lugar.id === "title") { lugar.classList.add("radar-com-barra"); lugar.append(juntos); }
    else lugar.prepend(caixa, caixaFantasma);
    document.body.append(janela);
  }

  // ------------------------------------------------------------ os números do seu canal no alto do YouTube
  // O studio.js pede ao YouTube Studio (quando ele está aberto) e guarda na extensão; aqui o botão mostra 1h, 48h, 7d e
  // 30d e abre os cartões com os gráficos, com o "atualizado há X min".
  const milhar = (n) => n == null ? "—" : Math.round(n).toLocaleString("pt-BR");
  const soma = (xs) => xs.reduce((a, b) => a + b, 0);
  function resumoNumeros(n) {
    const h = (n && n.horas) || [], v = (n && n.views) || [];
    return {
      h1: h.length >= 2 ? h[h.length - 2][1] : null,   // a última hora completa (a corrente ainda está contando)
      h48: h.length ? soma(h.map((x) => x[1])) : null,
      d7: v.length ? soma(v.slice(-7)) : null, d30: v.length ? soma(v.slice(-30)) : null,
      horas12: n && n.totalAssistido != null ? n.totalAssistido / 3.6e6 : n && n.assistido && n.assistido.length ? soma(n.assistido) / 3.6e6 : null,
      ganhos12: n && n.totalGanhos != null ? n.totalGanhos / 1000 : n && n.ganhos && n.ganhos.length ? soma(n.ganhos) / 1000 : null,
    };
  }
  function minigrafico(valores) {
    const g = novoSvg("svg", { viewBox: "0 0 100 30", preserveAspectRatio: "none", class: "radar-mini-grafico" });
    if (!valores || valores.length < 2) return g;
    const max = Math.max(...valores, 1), pts = valores.map((y, i) => `${(i / (valores.length - 1)) * 100},${29 - (y / max) * 27}`).join(" ");
    g.append(novoSvg("polygon", { points: `0,30 ${pts} 100,30`, class: "radar-mini-area" }), novoSvg("polyline", { points: pts, class: "radar-mini-linha" }));
    return g;
  }
  const haQuanto = (ms) => { const m = Math.round((Date.now() - ms) / 60000); return m < 1 ? "agora" : m < 60 ? `há ${m} ${m === 1 ? "minuto" : "minutos"}` : `há ${Math.round(m / 60)} h`; };

  let numerosCanal = null;
  chrome.storage.local.get("numerosCanal").then(({ numerosCanal: n }) => { numerosCanal = n || null; numerosTopo(); });

  function numerosTopo() {
    const lugar = document.querySelector("ytd-masthead #end");
    if (!lugar) return;
    let botao = lugar.querySelector(".radar-numeros-topo");
    if (!botao) {
      botao = h("button", { class: "radar-numeros-topo", title: "Números do seu canal (do YouTube Studio)", onclick: (e) => { e.stopPropagation(); abrirNumeros(botao); } });
      lugar.prepend(botao);
    }
    const r = resumoNumeros(numerosCanal);
    botao.replaceChildren(h("i", {}), ...[["h1", "1h"], ["h48", "48h"], ["d7", "7d"], ["d30", "30d"]].map(([k, t]) =>
      h("span", {}, h("b", {}, r[k] == null ? "—" : num(r[k])), h("small", {}, t))));
    const aberta = document.querySelector(".radar-numeros-janela:not([hidden])");
    if (aberta) desenharNumeros(aberta);
  }

  function desenharNumeros(janela) {
    const n = numerosCanal, r = resumoNumeros(n);
    const studio = n && n.canal ? `https://studio.youtube.com/channel/${n.canal}/analytics` : "https://studio.youtube.com";
    const cab = h("div", { class: "radar-numeros-cab" },
      h("a", { class: "radar-numeros-ic", href: "https://studio.youtube.com", target: "_blank", rel: "noopener", title: "Abrir o Studio para atualizar" }, icone("limpar")),
      h("b", {}, "Números do canal"), h("span", { class: "radar-numeros-modo" }, "Tempo real"),
      h("button", { class: "radar-janela-fechar", title: "Fechar", onclick: () => { janela.hidden = true; } }, "×"));
    if (!n) return janela.replaceChildren(cab, h("p", { class: "radar-numeros-vazio" },
      "Abra o YouTube Studio uma vez (com o canal escolhido) para o Radar ler os números do seu canal. ",
      "Enquanto o Studio estiver aberto numa aba, eles se atualizam a cada minuto."),
      h("a", { class: "radar-ver-painel", href: "https://studio.youtube.com", target: "_blank", rel: "noopener" }, "Abrir o YouTube Studio"));
    const horas = (n.horas || []).map((x) => x[1]), views = n.views || [];
    const cartoes = [
      ["olho", "Visualizações · última hora", milhar(r.h1), horas.slice(-13, -1)],
      ["olho", "Visualizações · 48 horas", milhar(r.h48), horas],
      ["olho", "Visualizações · 7 dias", milhar(r.d7), views.slice(-7)],
      ["olho", "Visualizações · 30 dias", milhar(r.d30), views.slice(-30)],
      ["relogio", "Tempo assistido · 12 meses", r.horas12 == null ? "—" : `${num(r.horas12)} h`, n.assistido],
      ["dinheiro", "Ganhos estimados · 12 meses", r.ganhos12 == null ? "—" : `US$ ${r.ganhos12.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, n.ganhos],
    ];
    janela.replaceChildren(cab,
      h("div", { class: "radar-numeros-cartoes" }, cartoes.map(([ic, t, x, serie]) =>
        h("div", { class: "radar-numeros-cartao" }, h("div", {}, h("span", {}, icone(ic), t), h("b", {}, x)), minigrafico(serie)))),
      h("div", { class: "radar-numeros-rodape" }, h("span", {}, `Atualizado ${haQuanto(n.quando)}`),
        h("a", { href: studio, target: "_blank", rel: "noopener" }, "Abrir o Analytics ↗")));
  }

  function abrirNumeros(botao) {
    let janela = document.querySelector(".radar-numeros-janela");
    if (!janela) {
      janela = h("div", { class: "radar-numeros-janela", hidden: "" });
      janela.addEventListener("click", (e) => e.stopPropagation());
      document.addEventListener("click", () => { janela.hidden = true; });
      document.body.append(janela);
      setInterval(() => { if (!janela.hidden) desenharNumeros(janela); }, 60000);   // o "atualizado há X min" anda
    }
    if (!janela.hidden) { janela.hidden = true; return; }
    desenharNumeros(janela);
    janela.hidden = false;
    const r = botao.getBoundingClientRect();
    janela.style.top = `${r.bottom + 8}px`;
    janela.style.left = `${Math.max(8, Math.min(r.left, innerWidth - janela.offsetWidth - 8))}px`;
  }

  // ------------------------------------------------------------ Nova produção, no alto do YouTube
  // A mesma Nova produção do site, em dois passos: 1 · o vídeo (título, link, o agente com Editar e o "parar para eu
  // revisar"); 2 · editar o roteiro (canal, agente, idioma, tamanho, nicho e observação). Sem editar, o Claude escreve
  // com o agente do canal. Num vídeo aberto, o link dele já vem como referência. O último canal usado fica lembrado.
  const POR_PALAVRA = 5.9, MINUTOS_NP = [8, 10, 12, 15, 20, 25, 30];

  function botaoNovaProducao() {
    const lugar = document.querySelector("ytd-masthead #end");
    if (!lugar) return;
    const ja = lugar.querySelector(".radar-np-botao");
    if (ja) { if (lugar.firstElementChild !== ja) lugar.prepend(ja); return; }
    lugar.prepend(h("button", { class: "radar-np-botao", title: "Nova produção: mandar um vídeo para a fábrica", onclick: (e) => { e.stopPropagation(); novaProducao(); } },
      icone("roteiro"), h("span", {}, "Nova produção")));
  }

  async function novaProducao() {
    if (document.querySelector(".radar-np-fundo")) return;
    const fundo = h("div", { class: "radar-np-fundo" }), janela = h("div", { class: "radar-np" });
    fundo.append(janela);
    const fechar = () => { fundo.remove(); document.removeEventListener("keydown", teclas, true); };
    const teclas = (e) => { if (e.key === "Escape") fechar(); };
    document.addEventListener("keydown", teclas, true);
    fundo.addEventListener("click", (e) => { if (e.target === fundo) fechar(); });
    janela.append(h("div", { class: "radar-fraco" }, "Abrindo a Nova produção…"));
    document.body.append(fundo);

    const [rc, ra, { npCanal }] = await Promise.all([api("/api/meus-canais"), api("/api/projetos"), chrome.storage.local.get("npCanal")]);
    if (rc.erro || ra.erro) return janela.replaceChildren(h("div", { class: "radar-erro" }, erroDoRadar(rc.erro ? rc : ra)));
    const canais = rc.dados.canais || [], agentes = ra.dados.projetos || [];
    const daqui = location.pathname === "/watch" && new URLSearchParams(location.search).get("v");
    const N = { passo: 1, titulo: "", link: daqui ? `https://youtu.be/${daqui}` : "", ref: null, cfg: null, agente: "", lingua: "português",
      ppm: 150, caracteres: Math.round(12 * 150 * POR_PALAVRA / 10) * 10, modo: "claude", roteiro: "", nicho: "", obs: "", revisar: false, custo: null,
      canal: canais.some((c) => c.id === npCanal) ? npCanal : canais.length === 1 ? canais[0].id : "" };
    const minutos = () => N.caracteres / POR_PALAVRA / N.ppm;
    const nomeCanal = () => (canais.find((c) => c.id === N.canal) || {}).titulo || "";
    const agenteAtual = () => agentes.find((a) => String(a.id) === String(N.agente));

    const custo = async () => {
      const r = await api(`/api/fila/estimativa?canal=${encodeURIComponent((N.cfg && N.cfg.perfil) || "")}&minutos=${minutos().toFixed(1)}`);
      N.custo = r.erro ? null : r.dados; desenhar();
    };
    const escolherCanal = async (id) => {
      N.canal = id; chrome.storage.local.set({ npCanal: id });
      const r = await api(`/api/producao/${encodeURIComponent(id)}`);
      N.cfg = r.erro ? null : r.dados;
      if (N.cfg) {
        N.lingua = N.cfg.lingua || N.lingua; N.agente = N.cfg.projeto_roteiro_id || "";
        const ritmo = await api(`/api/roteiros/ritmo?perfil=${encodeURIComponent(N.cfg.perfil || "")}&lingua=${encodeURIComponent(N.lingua)}`);
        N.ppm = (!ritmo.erro && ritmo.dados.ppm) || 150;
        N.caracteres = Math.round((N.cfg.minutos || 12) * N.ppm * POR_PALAVRA / 10) * 10;
      }
      desenhar(); custo();
    };
    const lerReferencia = async () => {
      N.ref = null;
      if (N.link) { const r = await api(`/api/titulo-do-video?link=${encodeURIComponent(N.link)}`); N.ref = r.erro ? null : r.dados; }
      desenhar();
    };

    const campo = (rotulo, ...filhos) => h("label", { class: "radar-np-campo" }, h("span", {}, rotulo), ...filhos);
    const entrada = (valor, attrs, aoMudar, evento = "input") => { const i = h("input", { value: valor, ...attrs }); i.addEventListener(evento, (e) => aoMudar(e.target.value)); return i; };
    const chip = (texto, ligado, onclick) => h("button", { type: "button", class: `radar-np-chip${ligado ? " ligado" : ""}`, onclick }, texto);
    const erro = h("span", { class: "radar-np-erro" });

    function desenhar() {
      const ag = agenteAtual();
      const canaisEl = h("div", { class: "radar-np-campo" }, h("span", {}, "Canal"),
        h("div", { class: "radar-np-chips" }, canais.length ? canais.map((c) => chip(c.titulo, c.id === N.canal, () => escolherCanal(c.id)))
          : h("span", { class: "radar-fraco" }, "Nenhum canal: adicione em Meu trabalho → Canais, no site do Radar.")));
      const revisar = h("label", { class: "radar-np-revisar" }, (() => { const c = h("input", { type: "checkbox" }); c.checked = N.revisar; c.onchange = () => { N.revisar = c.checked; }; return c; })(),
        h("span", {}, h("b", {}, "Parar para eu revisar o roteiro"), h("small", {}, "O Claude escreve e espera você aprovar no Acompanhar antes de ir para a fábrica.")));
      const passos = h("div", { class: "radar-np-passos" }, h("span", { class: N.passo === 1 ? "ligado" : "" }, "1 · O vídeo"), h("span", { class: N.passo === 2 ? "ligado" : "" }, "2 · Editar o roteiro"));
      let corpo;
      if (N.passo === 1) {
        corpo = [passos,
          campo("Título do vídeo", entrada(N.titulo, { placeholder: "O título que vai para o YouTube", maxlength: "150", class: "radar-np-titulo" }, (v) => { N.titulo = v; })),
          campo("Vídeo de referência (opcional: o roteiro modela este vídeo)", entrada(N.link, { placeholder: "https://youtu.be/…" }, (v) => { N.link = v.trim(); lerReferencia(); }, "change")),
          N.ref && N.ref.titulo ? h("button", { type: "button", class: "radar-np-usar", onclick: () => { N.titulo = N.ref.titulo; desenhar(); } }, `usar o título da referência: “${N.ref.titulo}”`) : null,
          N.canal ? null : canaisEl,
          h("div", { class: "radar-np-campo" }, h("span", {}, "Agente do roteiro"),
            h("div", { class: "radar-np-agente" },
              h("div", {}, h("b", {}, N.modo === "manual" ? "Roteiro colado por você" : (ag && ag.nome) || "Padrão do Claude"),
                h("small", {}, [nomeCanal() || "escolha o canal", N.lingua, N.modo === "manual" ? null : `≈ ${Math.round(minutos())} min`].filter(Boolean).join(" · "))),
              h("button", { type: "button", class: "radar-np-editar", onclick: () => { N.passo = 2; desenhar(); } }, "Editar")),
            h("small", { class: "radar-fraco" }, "Sem editar, o Claude escreve o roteiro com este agente e o vídeo segue para a fábrica.")),
          revisar];
      } else {
        const sel = (opcoes, atual, aoMudar) => { const s = h("select", {}, opcoes.map(([v, t]) => { const o = h("option", { value: v }, t); if (String(v) === String(atual)) o.selected = true; return o; })); s.onchange = () => aoMudar(s.value); return s; };
        corpo = [passos, h("button", { type: "button", class: "radar-np-usar", onclick: () => { N.passo = 1; desenhar(); } }, "← Voltar ao vídeo"), canaisEl,
          h("div", { class: "radar-np-duas" },
            campo("Agente do roteiro", sel([["", "Padrão do Claude"], ...agentes.map((a) => [a.id, a.nome])], N.agente, (v) => { N.agente = v; desenhar(); })),
            campo("Idioma", sel([...new Set([N.lingua, "português", "inglês", "espanhol", "francês", "alemão", "italiano"])].map((l) => [l, l]), N.lingua, (v) => { N.lingua = v; }))),
          h("div", { class: "radar-np-campo" }, h("span", {}, "Roteiro"), h("div", { class: "radar-np-chips" },
            chip("O Claude escreve", N.modo === "claude", () => { N.modo = "claude"; desenhar(); }), chip("Já tenho o roteiro", N.modo === "manual", () => { N.modo = "manual"; desenhar(); }))),
          ...(N.modo === "manual" ? [(() => { const t = h("textarea", { rows: "7", placeholder: "Cole aqui o roteiro inteiro (só o que vai ser narrado)" }); t.value = N.roteiro; t.oninput = () => { N.roteiro = t.value; }; return t; })()] : [
            h("div", { class: "radar-np-campo" }, h("span", {}, `Tamanho do roteiro: ${N.caracteres.toLocaleString("pt-BR")} caracteres ≈ ${Math.round(minutos())} min`),
              h("div", { class: "radar-np-chips" }, MINUTOS_NP.map((m) => chip(`${m} min`, Math.round(minutos()) === m, () => { N.caracteres = Math.round(m * N.ppm * POR_PALAVRA / 10) * 10; desenhar(); custo(); })))),
            h("div", { class: "radar-np-duas" },
              campo("Nicho (opcional)", entrada(N.nicho, { placeholder: "Ex.: grandes marcas" }, (v) => { N.nicho = v; })),
              campo("Observação (opcional)", entrada(N.obs, { placeholder: "Ex.: sem gírias, fechar com pergunta" }, (v) => { N.obs = v; })))]),
          revisar];
      }
      const enviar = async (comecar, botao) => {
        erro.textContent = "";
        if (!N.titulo.trim()) { erro.textContent = "Escreva o título do vídeo."; return; }
        if (!N.canal) { erro.textContent = "Escolha o canal."; N.passo = 2; return desenhar(); }
        botao.disabled = true; botao.lastChild.textContent = comecar ? "Criando…" : "Salvando…";
        const pedido = { titulo: N.titulo, link: N.link, canal_id: N.canal, agente_id: N.agente, lingua: N.lingua, revisar: N.revisar,
          ...(N.modo === "manual" ? { roteiro_manual: N.roteiro } : { caracteres: N.caracteres, nicho: N.nicho, observacao: N.obs }) };
        const r = await api("/api/fila", "POST", { pedido, comecar });
        if (r.erro) { botao.disabled = false; botao.lastChild.textContent = comecar ? "Criar e começar" : "Salvar na Entrada"; erro.textContent = erroDoRadar(r); return; }
        janela.replaceChildren(h("div", { class: "radar-np-pronto" }, h("span", { class: "radar-janela-ic" }, icone("roteiro")),
          h("b", {}, comecar ? "Na fila! O vídeo começa quando a fábrica tiver vaga." : "Guardado na Entrada."),
          h("div", { class: "radar-np-acoes" },
            h("button", { type: "button", class: "radar-np-secundario", onclick: fechar }, h("span", {}, "Fechar")),
            h("button", { type: "button", class: "radar-np-principal", onclick: () => { chrome.runtime.sendMessage({ tipo: "radar", caminho: "/#/acompanhar" }); fechar(); } }, h("span", {}, "Ver no Acompanhar")))));
      };
      const capa = N.ref && N.ref.id ? h("img", { src: `https://i.ytimg.com/vi/${N.ref.id}/mqdefault.jpg`, alt: "" }) : null;
      janela.replaceChildren(
        h("div", { class: "radar-np-cab" }, h("span", { class: "radar-janela-ic" }, icone("roteiro")), h("b", {}, "Nova produção"),
          h("button", { class: "radar-janela-fechar", title: "Fechar (Esc)", onclick: fechar }, "×")),
        h("div", { class: "radar-np-corpo" }, ...corpo.filter(Boolean)),
        h("div", { class: "radar-np-previa" }, capa,
          h("span", {}, h("b", {}, N.titulo || "O título do vídeo aparece aqui"),
            h("small", {}, [nomeCanal() || "sem canal", N.revisar ? "para para revisar" : "segue direto",
              N.custo && N.custo.usd != null ? `≈ US$ ${N.custo.usd.toFixed(2).replace(".", ",")}` : null].filter(Boolean).join(" · ")))),
        h("div", { class: "radar-np-rodape" }, erro,
          (() => { const b = h("button", { type: "button", class: "radar-np-secundario" }, h("span", {}, "Salvar na Entrada")); b.onclick = () => enviar(false, b); return b; })(),
          (() => { const b = h("button", { type: "button", class: "radar-np-principal" }, h("span", {}, "Criar e começar")); b.onclick = () => enviar(true, b); return b; })()));
      if (N.passo === 1 && !N.titulo) { const t = janela.querySelector(".radar-np-titulo"); if (t) t.focus(); }
    }

    desenhar();
    if (N.canal) escolherCanal(N.canal); else custo();
    if (N.link) lerReferencia();
  }

  // ------------------------------------------------------------ navegação do YouTube

  function pagina() {
    const url = new URL(location.href);
    if (url.pathname === "/watch" && url.searchParams.get("v")) {
      const id = url.searchParams.get("v");
      const atual = document.querySelector(".radar-painel");
      if (!atual || atual.dataset.id !== id) setTimeout(() => painelDoVideo(id), 800);
    } else {
      document.querySelectorAll(".radar-painel").forEach((p) => p.remove());
    }
    const canal = url.pathname.match(/^\/(@[^/]+|channel\/(UC[\w-]{22}))/);
    if (canal) {
      const ref = canal[2] || decodeURIComponent(canal[1]);
      const atual = document.querySelector(".radar-nicho-caixa");
      if (!atual || atual.dataset.ref !== ref) setTimeout(() => painelDoCanal(ref), 1200);
    } else {
      sairDoCanal();
    }
  }

  chrome.storage.onChanged.addListener((mudou) => {
    if (mudou.token) { semConta = !mudou.token.newValue; pagina(); }
    if (mudou.semShorts) semShorts(mudou.semShorts.newValue);
    if (mudou.numerosCanal) { numerosCanal = mudou.numerosCanal.newValue || null; numerosTopo(); }
    if (mudou.canalTreino || mudou.token) carregarTreino().then(() => varrer());
  });
  document.addEventListener("yt-navigate-finish", () => { pagina(); varrer(); atualizarTela(); });
  new MutationObserver(() => { clearTimeout(varrer.t); varrer.t = setTimeout(varrer, 400); })
    .observe(document.body, { childList: true, subtree: true });
  pagina(); varrer();
  carregarTreino().then(() => varrer());
})();
