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

  // A transcrição vem do botão "Mostrar transcrição" do próprio YouTube: pedir direto ao /get_transcript é recusado
  // (400) e a legenda do player vem vazia. O clique abre o painel do YouTube; a resposta é lida no fetch acima e o
  // painel é fechado em seguida.
  async function transcricao(id) {
    const botao = document.querySelector("ytd-video-description-transcript-section-renderer button");
    if (!botao || new URLSearchParams(location.search).get("v") !== id) return { linhas: [] };
    const j = await new Promise((ok) => { esperandoTranscricao = ok; botao.click(); setTimeout(() => ok(null), 12000); });
    esperandoTranscricao = null;
    const fechar = document.querySelector('ytd-engagement-panel-section-list-renderer[target-id*="transcript"] #visibility-button button');
    if (fechar) fechar.click();
    return { linhas: segmentos(j) };
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
