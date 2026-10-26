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
  const legendas = new Map();        // id do vídeo -> [{ lingua, kind, dados }]
  function guardarLegenda(url, texto) {
    try {
      const u = new URL(url, location.href), dados = JSON.parse(texto);
      if (!dados || !dados.events) return;
      const id = u.searchParams.get("v");
      legendas.set(id, [...(legendas.get(id) || []), { lingua: u.searchParams.get("lang") || "", kind: u.searchParams.get("kind") || "", dados }]);
      for (const avisar of [...esperandoLegenda]) avisar(id);
    } catch { /* não era a legenda em JSON */ }
  }
  const abrirXhr = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (metodo, url) {
    if (/\/api\/timedtext/.test(String(url))) this.addEventListener("load", () => guardarLegenda(String(url), this.responseText));
    return abrirXhr.apply(this, arguments);
  };
  const guardada = (id, t) => {
    const lista = legendas.get(id) || [];
    return (lista.find((l) => l.lingua === t.languageCode && l.kind === (t.kind || "")) || lista[0] || {}).dados || null;
  };

  // a legenda feita à mão na língua do vídeo; senão a automática; senão a primeira que houver
  function trilha(r) {
    const trilhas = (r && r.captions && r.captions.playerCaptionsTracklistRenderer
      && r.captions.playerCaptionsTracklistRenderer.captionTracks) || [];
    const auto = trilhas.find((t) => t.kind === "asr");
    return (auto && trilhas.find((t) => t.kind !== "asr" && t.languageCode.split("-")[0] === auto.languageCode.split("-")[0]))
      || auto || trilhas[0] || null;
  }

  async function legendaDoPlayer(id) {
    const p = document.getElementById("movie_player"), r = resposta();
    const t = trilha(r);
    if (!p || !p.setOption || !t || !r.videoDetails || r.videoDetails.videoId !== id) return [];
    let j = guardada(id, t);
    if (!j) {
      const antes = p.getOption && p.getOption("captions", "track");
      let pronto = () => {};
      const avisar = (vid) => { if (vid === id) pronto(); };
      await new Promise((ok) => {
        pronto = ok;
        esperandoLegenda.add(avisar);
        if (p.loadModule) p.loadModule("captions");
        p.setOption("captions", "track", { languageCode: t.languageCode, kind: t.kind || "" });
        setTimeout(ok, 6000);
      });
      esperandoLegenda.delete(avisar);
      if (antes && antes.languageCode) p.setOption("captions", "track", antes);
      else { p.setOption("captions", "track", {}); if (p.unloadModule) p.unloadModule("captions"); }
      j = guardada(id, t);
    }
    const linhas = [];
    for (const ev of (j && j.events) || []) {
      const texto = (ev.segs || []).map((s) => s.utf8 || "").join("").replace(/\s+/g, " ").trim();
      if (texto) linhas.push({ ms: +ev.tStartMs || 0, texto });
    }
    return linhas;
  }

  // o jeito antigo (o botão da descrição), se o YouTube ainda mostrar o botão e a legenda do player falhar
  async function painelDoYoutube(id) {
    const botao = document.querySelector("ytd-video-description-transcript-section-renderer button");
    if (!botao || new URLSearchParams(location.search).get("v") !== id) return [];
    const j = await new Promise((ok) => { esperandoTranscricao = ok; botao.click(); setTimeout(() => ok(null), 7000); });
    esperandoTranscricao = null;
    const fechar = document.querySelector('ytd-engagement-panel-section-list-renderer[target-id*="transcript"] #visibility-button button');
    if (fechar) fechar.click();
    return segmentos(j);
  }

  // Um pedido por vídeo de cada vez: a aba do painel e a janelinha do menu abrem a mesma transcrição, e dois
  // pedidos juntos ligavam e desligavam a legenda do player ao mesmo tempo (era um dos jeitos de bugar).
  const emAndamento = new Map();

  async function transcricao(id) {
    if (emAndamento.has(id)) return emAndamento.get(id);
    const tarefa = (async () => {
      let linhas = [];
      try { linhas = await legendaDoPlayer(id); } catch { /* tenta o outro jeito */ }
      if (!linhas.length) {
        try { linhas = await painelDoYoutube(id); } catch { linhas = []; }
      }
      if (linhas.length) return { linhas };
      // sem nenhuma trilha de legenda o vídeo não tem transcrição mesmo; com trilha, foi o YouTube que não entregou
      const r = resposta();
      return { linhas: [], motivo: r && !trilha(r) ? "sem-legenda" : "nao-deu" };
    })();
    emAndamento.set(id, tarefa);
    // só o acerto fica guardado: o que falhou tem de poder ser tentado de novo
    tarefa.then((t) => { if (!t.linhas.length) emAndamento.delete(id); }, () => emAndamento.delete(id));
    return tarefa;
  }

  window.addEventListener("message", async (e) => {
    if (e.source !== window || !e.data || !e.data.radarPedido) return;
    const { radarPedido: n, tipo, id } = e.data;
    let dados = null;
    try {
      dados = tipo === "video" ? dadosDoVideo() : tipo === "transcricao" ? await transcricao(id)
        : tipo === "canal" ? (ultimoCanal || L.canal(window.ytInitialData)) : null;
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
