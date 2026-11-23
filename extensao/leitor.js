// Roda dentro da página do YouTube (world MAIN, antes dela começar) para ver os dados que o próprio YouTube recebe:
// o ytInitialData da primeira carga e as respostas do /youtubei/v1/ (busca, página inicial, sugeridos, rolagem).
// Só lê: não muda nenhuma resposta. O que acha vai por postMessage para o content.js, que manda ao Radar.
(() => {
  if (window.__radarLeitor) return;
  window.__radarLeitor = true;
  const L = globalThis.RadarLer;
  if (!L) return;

  const ROTAS = /\/youtubei\/v1\/(browse|search|next|guide)\b/;

  function mandar(json, origem) {
    if (!json) return;
    try {
      const videos = L.videos(json);
      const canal = L.canal(json);
      if (canal) ultimoCanal = canal;
      if (videos.length || canal) window.postMessage({ radarLeitor: 1, origem, videos, canal, url: location.href }, location.origin);
    } catch { /* o YouTube mudou alguma coisa: não atrapalha a página */ }
  }

  let esperandoTranscricao = null;   // a transcrição pedida pelo content.js, esperando a resposta do YouTube
  let ultimoCanal = null;            // o último canal que a página mostrou (para a faixa da página do canal)
  const fetchOriginal = window.fetch;
  window.fetch = async function (...args) {
    const resposta = await fetchOriginal.apply(this, args);
    try {
      const url = typeof args[0] === "string" ? args[0] : (args[0] && args[0].url) || "";
      if (ROTAS.test(url)) {
        const rota = url.match(ROTAS)[1];
        resposta.clone().json().then((json) => mandar(json, rota)).catch(() => {});
      }
      if (/\/youtubei\/v1\/get_transcript\b/.test(url) && esperandoTranscricao) {
        resposta.clone().json().then((j) => esperandoTranscricao && esperandoTranscricao(j)).catch(() => {});
      }
      if (/\/api\/timedtext/.test(url)) resposta.clone().text().then((t) => guardarLegenda(url, t)).catch(() => {});
    } catch { /* nada */ }
    return resposta;
  };

  // ------------------------------------------------------------ os números do seu canal, sem o Studio aberto
  // Os mesmos pedidos que o studio.js faz, daqui do youtube.com e com o mesmo login. Só para quando o Studio está fechado:
  // o content.js manda o pedido quando os números guardados passaram de 15 minutos.
  const cfg = (k) => window.ytcfg && window.ytcfg.get ? window.ytcfg.get(k) : null;
  async function cabecalhoDoLogin() {
    const c = (document.cookie.match(/(?:^|; )(?:__Secure-3PAPISID|SAPISID)=([^;]+)/) || [])[1];
    if (!c) return null;
    const ts = Math.floor(Date.now() / 1000);
    const buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(`${ts} ${c} ${location.origin}`));
    const cab = { "content-type": "application/json", "x-origin": location.origin, "x-goog-authuser": String(cfg("SESSION_INDEX") || 0),
      authorization: `SAPISIDHASH ${ts}_${[...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("")}` };
    if (cfg("DELEGATED_SESSION_ID")) cab["x-goog-pageid"] = cfg("DELEGATED_SESSION_ID");
    return cab;
  }
  async function pedirAoYoutube(caminho, corpo) {
    const headers = await cabecalhoDoLogin();
    if (!headers) return null;
    const r = await fetchOriginal.call(window, `/youtubei/v1/${caminho}?alt=json&key=${cfg("INNERTUBE_API_KEY")}`,
      { method: "POST", credentials: "include", headers, body: JSON.stringify({ context: cfg("INNERTUBE_CONTEXT"), ...corpo }) });
    return r.ok ? r.json() : null;
  }
  async function numerosSemStudio() {
    const menu = await pedirAoYoutube("account/account_menu", {});
    const canal = (JSON.stringify(menu || {}).match(/"browseId":"(UC[\w-]{22})"/) || [])[1];
    if (!canal) return null;
    const j = await pedirAoYoutube("yta_web/get_cards", { cardConfigs: [{ latestActivityCardConfig: { tableLimit: 3, includeSubsData: true }, failureMode: "ANALYTICS_CARD_FAILURE_MODE_HIDE" }],
      screenConfig: { entity: { channelId: canal }, timePeriod: { timePeriodType: "ANALYTICS_TIME_PERIOD_TYPE_FOUR_WEEKS" }, currency: "USD", timeZoneOffsetSecs: -new Date().getTimezoneOffset() * 60 } });
    const cartao = ((j && j.cards) || []).find((c) => !c.isFailed);
    const d = cartao && cartao.latestActivityCardData && cartao.latestActivityCardData.datas && cartao.latestActivityCardData.datas[0];
    if (!d) return null;
    const views = d.mainChartData.metricColumns[0].counts.values.map(Number);
    return { canal, quando: Date.now(), horas: d.mainChartData.dimensionColumns[0].timestamps.values.map((t, i) => [Number(t), views[i] || 0]) };
  }
  window.addEventListener("message", async (e) => {
    if (e.source !== window || !e.data || e.data.radarNumerosPedido !== 1) return;
    let numeros = null;
    try { numeros = await numerosSemStudio(); } catch { /* sem canal nesta conta, ou o YouTube mudou */ }
    if (numeros) window.postMessage({ radarNumerosResposta: 1, numeros }, location.origin);
  });

  // ------------------------------------------------------------ pedidos do content.js (o vídeo aberto e a transcrição)
  // O content.js não enxerga o player nem a configuração do YouTube; pede aqui por postMessage e recebe a resposta.

  const resposta = () => {
    const p = document.getElementById("movie_player");
    return (p && p.getPlayerResponse && p.getPlayerResponse()) || window.ytInitialPlayerResponse || null;
  };

  function dadosDoVideo() {
    const r = resposta();
    const d = r && r.videoDetails, mf = r && r.microformat && r.microformat.playerMicroformatRenderer;
    if (!d) return null;
    return { id: d.videoId, titulo: d.title, canal_id: d.channelId, canal: d.author, views: +d.viewCount || null,
      duracao_s: +d.lengthSeconds || null, tags: d.keywords || [], descricao: d.shortDescription || "",
      // as faixas de áudio dubladas: o id vem como "en.4"
      audios: [...new Set(((r.streamingData && r.streamingData.adaptiveFormats) || []).map((f) => f.audioTrack && String(f.audioTrack.id || "").split(".")[0]).filter(Boolean))],
      publicado: (mf && (mf.publishDate || mf.uploadDate)) || "", ao_vivo: !!d.isLive,
      // anúncio no player = canal monetizado (quem tem YouTube Premium não recebe anúncio: aí não dá para saber)
      anuncios: !!((r.adPlacements && r.adPlacements.length) || (r.playerAds && r.playerAds.length)) };
  }

  const segmentos = (j) => {
    const linhas = [];
    (function andar(o) {
      if (!o || typeof o !== "object") return;
      const s = o.transcriptSegmentRenderer;
      if (s) { const t = L.texto(s.snippet).trim(); if (t) linhas.push({ ms: +s.startMs || 0, texto: t }); return; }
      for (const v of Object.values(o)) andar(v);
    })(j);
    return linhas;
  };

  // A transcrição vem da legenda do próprio player (2026-10-20: o YouTube passou a recusar o /get_transcript com 400 e
  // o botão "Mostrar transcrição" sumiu da descrição). Pedir a legenda direto vem vazio (falta o token que só o player
  // tem), então a legenda é ligada por um instante, a resposta que o player baixa é lida e a legenda volta como estava.
  // O player não baixa de novo uma legenda que já baixou: toda legenda que passa fica guardada por vídeo.
  const esperandoLegenda = new Set();   // quem está esperando a próxima legenda (um por pedido)
  // `tlang` é a tradução automática do player (2026-11-22: com "Traduzir automaticamente" ligado no YouTube, a
  // legenda baixada vinha com lang=en&tlang=ar e era guardada como a fala em inglês; a transcrição saía em árabe, e
  // vídeos em inglês viravam roteiro com base em português). A traduzida fica guardada à parte e nunca vale como fala.
  const legendas = new Map();        // id do vídeo -> [{ lingua, kind, tlang, url, dados }]
  function guardarLegenda(url, texto) {
    try {
      const u = new URL(url, location.href), dados = JSON.parse(texto);
      if (!dados || !dados.events) return;
      const id = u.searchParams.get("v");
      legendas.set(id, [...(legendas.get(id) || []), { lingua: u.searchParams.get("lang") || "", kind: u.searchParams.get("kind") || "",
        tlang: u.searchParams.get("tlang") || "", url: u.href, dados }]);
      for (const avisar of [...esperandoLegenda]) avisar(id);
    } catch { /* não era a legenda em JSON */ }
  }
  const abrirXhr = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (metodo, url) {
    if (/\/api\/timedtext/.test(String(url))) this.addEventListener("load", () => guardarLegenda(String(url), this.responseText));
    if (/\/youtubei\/v1\/get_transcript\b/.test(String(url))) this.addEventListener("load", () => {
      if (!esperandoTranscricao) return;
      try { esperandoTranscricao(JSON.parse(this.responseText)); } catch { /* não era JSON */ }
    });
    return abrirXhr.apply(this, arguments);
  };
  // `exata`: a língua foi escolhida no seletor, e outra legenda já baixada não serve no lugar dela
  const guardada = (id, t, exata = false) => {
    const lista = (legendas.get(id) || []).filter((l) => !l.tlang);
    return (lista.find((l) => l.lingua === t.languageCode && l.kind === (t.kind || "")) || (exata ? null : lista[0]) || {}).dados || null;
  };
  // a legenda feita à mão na língua do vídeo; senão a automática; senão a primeira que houver
  const trilhasDe = (r) => (r && r.captions && r.captions.playerCaptionsTracklistRenderer
    && r.captions.playerCaptionsTracklistRenderer.captionTracks) || [];
  const chaveDa = (t) => `${t.languageCode}|${t.kind || ""}`;

  // Vídeo com dublagem (várias faixas de áudio, comum nos canais de IA): o YouTube gera uma legenda automática por
  // dublagem, e a primeira da lista podia ser a do árabe (2026-11-22: "Salvos Has Been Caught" transcrito em árabe).
  // A fala original é a faixa que não é dublagem automática ("Inglês (US) original"): a faixa padrão (audioIsDefault)
  // é a dublagem na língua de quem assiste, pt-BR aqui.
  const base = (codigo) => String(codigo || "").split(/[-_.]/)[0].toLowerCase();
  function linguaDoAudio(r) {
    const faixas = ((r && r.streamingData && r.streamingData.adaptiveFormats) || []).map((f) => f.audioTrack).filter(Boolean);
    const original = faixas.find((a) => !a.isAutoDubbed && /original/i.test(a.displayName || ""))
      || (faixas.some((a) => a.isAutoDubbed) && faixas.find((a) => !a.isAutoDubbed))
      || faixas.find((a) => a.audioIsDefault);
    if (original) return base(original.id);
    const rend = r && r.captions && r.captions.playerCaptionsTracklistRenderer;
    const faixa = rend && rend.audioTracks && rend.audioTracks[rend.defaultAudioTrackIndex || 0];
    return faixa && faixa.audioTrackId ? base(faixa.audioTrackId) : "";
  }
  function automaticaOriginal(r) {
    const autos = trilhasDe(r).filter((t) => t.kind === "asr"), lingua = linguaDoAudio(r);
    return (lingua && autos.find((t) => base(t.languageCode) === lingua)) || autos[0] || null;
  }

  function trilha(r, pedida) {
    const trilhas = trilhasDe(r);
    const escolhida = pedida && trilhas.find((t) => chaveDa(t) === pedida);
    if (escolhida) return escolhida;
    const auto = automaticaOriginal(r);
    return (auto && trilhas.find((t) => t.kind !== "asr" && t.languageCode.split("-")[0] === auto.languageCode.split("-")[0]))
      || auto || trilhas[0] || null;
  }

  async function legendaDoPlayer(id, pedida) {
    const p = document.getElementById("movie_player"), r = resposta();
    const t = trilha(r, pedida);
    if (!p || !p.setOption || !t || !r.videoDetails || r.videoDetails.videoId !== id) return [];
    let j = guardada(id, t, !!pedida);
    if (!j) {
      for (const fim = Date.now() + 15000; p.classList.contains("ad-showing") && Date.now() < fim;) await new Promise((ok) => setTimeout(ok, 500));
      const antes = p.getOption && p.getOption("captions", "track");
      let pronto = () => {};
      const avisar = (vid) => { if (vid === id) pronto(); };
      await new Promise((ok) => {
        pronto = ok;
        esperandoLegenda.add(avisar);
        if (p.loadModule) p.loadModule("captions");
        p.setOption("captions", "track", {});
        setTimeout(() => p.setOption("captions", "track", { languageCode: t.languageCode, kind: t.kind || "" }), 300);
        setTimeout(ok, 6000);
      });
      esperandoLegenda.delete(avisar);
      if (antes && antes.languageCode) p.setOption("captions", "track", antes);
      else { p.setOption("captions", "track", {}); if (p.unloadModule) p.unloadModule("captions"); }
      j = guardada(id, t, !!pedida);
    }
    const linhas = [];
    for (const ev of (j && j.events) || []) {
      const texto = (ev.segs || []).map((s) => s.utf8 || "").join("").replace(/\s+/g, " ").trim();
      if (texto) linhas.push({ ms: +ev.tStartMs || 0, texto });
    }
    return linhas;
  }

  // o painel do YouTube (botão da descrição), se a legenda do player falhar. A resposta nem sempre passa pelo fetch
  // (o YouTube também pede por XHR) e, com o painel já aberto, ele não pede nada de novo: por isso o que vale no fim
  // são os trechos que estão no painel, lidos do DOM. Esperar só a resposta de rede era o que deixava a aba em
  // "Lendo a fala do vídeo…" com a transcrição escrita na tela (2026-11-17).
  // 2026-11-22: o painel novo ("Neste vídeo", com Capítulos e Transcrição) vem sem target-id e com
  // transcript-segment-view-model; sem achar os trechos, ele ficava aberto embaixo e a aba dizia que não deu
  const TRECHO_FALA = "ytd-transcript-segment-renderer, yt-transcript-segment-view-model, transcript-segment-view-model, .ytTranscriptSegmentViewModel";
  const painelFala = () => {
    const seg = document.querySelector(TRECHO_FALA);
    return (seg && seg.closest("ytd-engagement-panel-section-list-renderer"))
      || document.querySelector('ytd-engagement-panel-section-list-renderer[target-id*="transcript"][visibility*="EXPANDED"]');
  };
  const emMs = (t) => {
    const p = String(t || "").trim().split(":").map(Number);
    if (!p.length || p.some((n) => !Number.isFinite(n))) return 0;
    return p.reduce((total, n) => total * 60 + n, 0) * 1000;
  };
  function trechosNoPainel() {
    const painel = painelFala();
    const linhas = [];
    for (const seg of (painel || document).querySelectorAll(TRECHO_FALA)) {
      const tempo = seg.querySelector(".segment-timestamp, .ytwTranscriptSegmentViewModelTimestamp, [class*='imestamp']:not([class*='11y'])");
      const texto = seg.querySelector(".segment-text, [class*='egmentText'], .ytAttributedStringHost");
      const bruto = ((texto || seg).textContent || "").replace(/\s+/g, " ").trim();
      const marca = tempo ? (tempo.textContent || "").replace(/\s+/g, " ").trim() : "";
      const t = !texto && marca && bruto.startsWith(marca) ? bruto.slice(marca.length).trim() : bruto;
      if (t) linhas.push({ ms: emMs(marca), texto: t });
    }
    return linhas;
  }

  async function painelDoYoutube(id) {
    if (new URLSearchParams(location.search).get("v") !== id) return [];
    const jaNaTela = trechosNoPainel();
    if (jaNaTela.length) return jaNaTela;   // o painel já está aberto: clicar só o fecharia, e nada seria pedido
    const botao = document.querySelector("ytd-video-description-transcript-section-renderer button");
    if (!botao) return [];
    const j = await new Promise((ok) => {
      let relogio = 0;
      const terminar = (valor) => { clearInterval(relogio); esperandoTranscricao = null; ok(valor); };
      esperandoTranscricao = terminar;
      botao.click();
      const fim = Date.now() + 7000;
      relogio = setInterval(() => { if (trechosNoPainel().length || Date.now() > fim) terminar(null); }, 250);
    });
    esperandoTranscricao = null;
    const doDom = trechosNoPainel();   // lido antes de fechar: fechar o painel tira os trechos da tela
    const aberto = painelFala();
    const fechar = aberto && aberto.querySelector('#visibility-button button, button[aria-label="Fechar"], button[aria-label="Close"], [aria-label*="echar"], [aria-label*="lose"]');
    if (fechar) fechar.click();
    const linhas = segmentos(j);
    return linhas.length ? linhas : doDom;
  }

  // Um pedido por vídeo de cada vez: a aba do painel e a janelinha do menu abrem a mesma transcrição, e dois
  // pedidos juntos ligavam e desligavam a legenda do player ao mesmo tempo (era um dos jeitos de bugar).
  const emAndamento = new Map();

  // as legendas que o YouTube já tem: o seletor da aba Transcrição mostra estas, nada é traduzido aqui. A trilha
  // automática é a língua falada: o YouTube só gera a automática da fala, as outras são escritas ou traduzidas.
  const faixasDe = (r) => {
    const trilhas = trilhasDe(r), auto = automaticaOriginal(r);
    return { falada: auto ? auto.languageCode : "", faixas: trilhas.map((t) => ({ chave: chaveDa(t), codigo: t.languageCode,
      nome: L.texto(t.name) || t.languageCode, auto: t.kind === "asr" })) };
  };

  async function transcricao(id, pedida = "") {
    const chave = `${id}|${pedida}`;
    if (emAndamento.has(chave)) return emAndamento.get(chave);
    const tarefa = (async () => {
      let linhas = [];
      try { linhas = await legendaDoPlayer(id, pedida); } catch { /* tenta o outro jeito */ }
      if (!linhas.length && !pedida) {
        try { linhas = await painelDoYoutube(id); } catch { linhas = []; }
      }
      const r = resposta(), t = trilha(r, pedida), lista = faixasDe(r);
      if (linhas.length) return { linhas, ...lista, atual: t ? chaveDa(t) : "" };
      // sem nenhuma trilha de legenda o vídeo não tem transcrição mesmo; com trilha, foi o YouTube que não entregou
      return { linhas: [], ...lista, atual: t ? chaveDa(t) : "", motivo: r && !t ? "sem-legenda" : "nao-deu" };
    })();
    emAndamento.set(chave, tarefa);
    // só o acerto fica guardado: o que falhou tem de poder ser tentado de novo
    tarefa.then((t) => { if (!t.linhas.length) emAndamento.delete(chave); }, () => emAndamento.delete(chave));
    return tarefa;
  }

  // o canal da página que está na tela, tirado do ytd-page-manager (2026-11-10): o ultimoCanal pode ser o de uma página
  // anterior (o YouTube às vezes troca de página sem passar pelo fetch) e o ytInitialData é o da primeira página
  // aberta; com os dois velhos, a faixa do canal ficava em "Radar: recarregue a página" e nada do Radar aparecia
  function canalAtual() {
    try {
      const pm = document.querySelector("ytd-page-manager");
      const d = pm && pm.getCurrentData && pm.getCurrentData();
      return d ? L.canal(d.response || d) : null;
    } catch { return null; }
  }

  window.addEventListener("message", async (e) => {
    if (e.source !== window || !e.data || !e.data.radarPedido) return;
    const { radarPedido: n, tipo, id, lingua } = e.data;
    let dados = null;
    try {
      dados = tipo === "video" ? dadosDoVideo() : tipo === "transcricao" ? await transcricao(id, lingua)
        : tipo === "canal" ? (canalAtual() || ultimoCanal || L.canal(window.ytInitialData)) : null;
    } catch { dados = null; }
    window.postMessage({ radarResposta: n, dados }, location.origin);
  });

  // a primeira carga vem no ytInitialData; na troca de página o YouTube manda a resposta no evento
  const inicial = () => mandar(window.ytInitialData, "inicial");
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", inicial, { once: true });
  else inicial();
  document.addEventListener("yt-navigate-finish", (e) => {
    const r = e.detail && e.detail.response;
    mandar((r && r.response) || window.ytInitialData, "navegou");
  });
})();
