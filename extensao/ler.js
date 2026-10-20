// Lê os vídeos e os canais dos dados que o próprio YouTube manda para a página (o ytInitialData e as respostas do
// /youtubei/v1/...). Não pede nada a ninguém: é o que já veio para a tela, então não gasta a cota da API.
// Carrega duas vezes: dentro da página (leitor.js, para ver as respostas) e na extensão (content.js, para ler a
// página de vídeos de um canal). Tudo fica em globalThis.RadarLer.
(() => {
  if (globalThis.RadarLer) return;

  const texto = (t) => !t ? "" : typeof t === "string" ? t : t.content || t.simpleText || (t.runs || []).map((r) => r.text).join("");

  // "1,2 mi de visualizações", "12 mil", "1.234.567 views", "1.2M views", "12K", "1,5 M de vistas", "3 mil mi"
  function numero(t) {
    t = texto(t).toLowerCase().replace(/ /g, " ");
    if (!t || /nenhuma|no views|sin vistas|nenhum inscrito/.test(t)) return t ? 0 : null;
    const m = t.match(/(\d[\d.,\s]*)\s*(mil mi|mil m|mi\b|mil\b|bi\b|k\b|m\b|b\b|mln|mrd)?/);
    if (!m) return null;
    const cru = m[1].trim(), sufixo = (m[2] || "").trim();
    const mult = { "mil mi": 1e9, "mil m": 1e9, bi: 1e9, b: 1e9, mrd: 1e9, mi: 1e6, m: 1e6, mln: 1e6, mil: 1e3, k: 1e3 }[sufixo] || 1;
    let n;
    if (mult > 1) n = parseFloat(cru.replace(/\s/g, "").replace(/\.(?=\d{3}\b)/g, "").replace(",", "."));
    else n = parseInt(cru.replace(/[.,\s]/g, ""), 10);
    return Number.isFinite(n) ? Math.round(n * mult) : null;
  }

  // "há 3 dias", "3 days ago", "hace 3 días", "Transmitido há 2 horas", "Streamed 1 year ago": dias desde a publicação
  // também as curtas: "há 7 h", "há 57 min.", "há 2 sem.", "3 hr ago", "2 wk ago"
  const UNIDADES = [[/^(seg|s$|sec)/, 1 / 86400], [/^min/, 1 / 1440], [/^(h$|hr|hora|hour)/, 1 / 24], [/^(d$|dia|day|día)/, 1],
    [/^(sem|week|wk)/, 7], [/^(m[eê]s|month|mo$)/, 30.44], [/^(ano|year|año|a$|y$|yr)/, 365.25]];
  function dias(t) {
    t = texto(t).toLowerCase();
    const m = t.match(/(\d+)\s*([a-zà-ú]+)/);
    if (!m) return null;
    const u = UNIDADES.find(([rx]) => rx.test(m[2]));
    return u ? +m[1] * u[1] : null;
  }

  // "12:34" ou "1:02:03" em segundos
  function duracao(t) {
    const m = texto(t).trim().match(/^(\d+):(\d{2})(?::(\d{2}))?$/);
    if (!m) return null;
    return m[3] != null ? +m[1] * 3600 + +m[2] * 60 + +m[3] : +m[1] * 60 + +m[2];
  }

  // procura dentro de um pedaço do JSON: o primeiro valor que passa no teste
  function primeiro(obj, teste, prof = 0) {
    if (!obj || typeof obj !== "object" || prof > 25) return null;
    for (const [k, v] of Object.entries(obj)) {
      if (teste(k, v)) return v;
      const achou = primeiro(v, teste, prof + 1);
      if (achou != null) return achou;
    }
    return null;
  }
  const canalDe = (obj) => primeiro(obj, (k, v) => k === "browseId" && typeof v === "string" && /^UC[\w-]{22}$/.test(v));
  const textos = (obj, saida = [], prof = 0) => {
    if (!obj || typeof obj !== "object" || prof > 25) return saida;
    if (typeof obj.content === "string") saida.push(obj.content);
    if (typeof obj.simpleText === "string") saida.push(obj.simpleText);
    if (typeof obj.text === "string" && !obj.content) saida.push(obj.text);
    for (const v of Object.values(obj)) if (v && typeof v === "object") textos(v, saida, prof + 1);
    return saida;
  };
  const eViews = (s) => /visualiza|views?\b|vistas?\b|visualizaciones/i.test(s);
  const eData = (s) => /(^|\s)(há|ha|hace)\s|\bago\b/i.test(s);   // o \b do JavaScript não entende o "á"
  const eAoVivo = (s) => /assistindo|watching|espectadores|ao vivo|live|premi/i.test(s);

  // o jeito antigo (busca, canal, sugeridos): videoRenderer e parentes
  function doRenderer(r) {
    if (!r || !r.videoId) return null;
    const dono = r.ownerText || r.shortBylineText || r.longBylineText;
    const viewsTxt = texto(r.viewCountText) || texto(r.shortViewCountText);
    const durTxt = texto(r.lengthText) || texto(primeiro(r.thumbnailOverlays, (k) => k === "text"));
    return {
      id: r.videoId, titulo: texto(r.title) || texto(r.headline), canal_id: canalDe(dono) || canalDe(r.channelThumbnailSupportedRenderers) || "",
      canal: texto(dono), views: numero(viewsTxt), dias: dias(r.publishedTimeText), duracao_s: duracao(durTxt),
      ao_vivo: eAoVivo(viewsTxt) || !!(r.badges || []).some((b) => /LIVE/.test(JSON.stringify(b))),
    };
  }

  // o jeito novo (página inicial, sugeridos): lockupViewModel
  function doLockup(l) {
    if (!l || !l.contentId || (l.contentType && l.contentType !== "LOCKUP_CONTENT_TYPE_VIDEO")) return null;
    const meta = l.metadata && l.metadata.lockupMetadataViewModel;
    // cada pedaço da linha: o texto completo fica no accessibilityLabel ("265 mil visualizações"; na tela, só "265 mil")
    const partes = ((((meta || {}).metadata || {}).contentMetadataViewModel || {}).metadataRows || [])
      .flatMap((r) => r.metadataParts || []).map((p) => p.accessibilityLabel || texto(p.text)).filter(Boolean);
    const linhas = partes.length ? partes : textos(meta && meta.metadata);
    const viewsTxt = linhas.find(eViews) || "";
    const durTxt = textos(l.contentImage).find((s) => /^\d+:\d{2}(:\d{2})?$/.test(s.trim())) || "";
    const nomeCanal = linhas.find((s) => !eViews(s) && !eData(s) && s.trim() && s !== "•") || "";
    return {
      id: l.contentId, titulo: texto(meta && meta.title), canal_id: canalDe(meta) || canalDe(l) || "", canal: nomeCanal,
      views: numero(viewsTxt), dias: dias(linhas.find(eData) || ""), duracao_s: duracao(durTxt),
      ao_vivo: eAoVivo(viewsTxt) || linhas.some(eAoVivo),
    };
  }

  const RENDERERS = ["videoRenderer", "gridVideoRenderer", "compactVideoRenderer", "videoWithContextRenderer", "playlistVideoRenderer"];

  // todos os vídeos de um pedaço do JSON
  function videos(json) {
    const saida = new Map();
    const andar = (obj, prof = 0) => {
      if (!obj || typeof obj !== "object" || prof > 40) return;
      if (Array.isArray(obj)) { for (const v of obj) andar(v, prof + 1); return; }
      for (const [k, v] of Object.entries(obj)) {
        let achado = null;
        if (RENDERERS.includes(k)) achado = doRenderer(v);
        else if (k === "lockupViewModel") achado = doLockup(v);
        if (achado && achado.id && achado.titulo) {
          const antes = saida.get(achado.id);
          // o mesmo vídeo pode vir duas vezes: fica o que trouxe mais dados
          if (!antes || (!antes.canal_id && achado.canal_id) || (antes.views == null && achado.views != null)) saida.set(achado.id, achado);
        } else if (v && typeof v === "object") andar(v, prof + 1);
      }
    };
    andar(json);
    return [...saida.values()].filter((v) => !v.ao_vivo);
  }

  // o botão "Seja membro" do canal (no cabeçalho do canal ou no dono do vídeo aberto). Sem ele não dá para dizer "não"
  const temMembros = (obj) => /"(sponsorButton|membershipButton)"|SPONSORSHIP/.test(JSON.stringify(obj || {}));

  // o canal da página (a do canal ou a do vídeo aberto): id, nome, foto, @, inscritos e quantos vídeos
  function canal(json) {
    if (!json || typeof json !== "object") return null;
    const meta = primeiro(json, (k) => k === "channelMetadataRenderer");
    if (meta && meta.externalId) {
      const cab = primeiro(json, (k) => k === "pageHeaderViewModel" || k === "c4TabbedHeaderRenderer") || {};
      const linhas = textos(cab);
      const inscr = texto(cab.subscriberCountText) || linhas.find((s) => /inscrit|subscri|suscript/i.test(s)) || "";
      const qtos = texto(cab.videosCountText) || linhas.find((s) => /v[ií]deos?\b/i.test(s) && /\d/.test(s)) || "";
      const handle = (meta.vanityChannelUrl || "").split("/").pop() || "";
      return { id: meta.externalId, titulo: meta.title || "", foto: ((meta.avatar || {}).thumbnails || []).slice(-1)[0]?.url || "",
        handle: handle.startsWith("@") ? handle : "", inscritos: numero(inscr), videos_total: numero(qtos),
        ...(temMembros(cab) ? { membros: true } : {}) };
    }
    const dono = primeiro(json, (k) => k === "videoOwnerRenderer");
    if (dono) {
      const id = canalDe(dono.navigationEndpoint || dono);
      if (!id) return null;
      return { id, titulo: texto(dono.title), foto: ((dono.thumbnail || {}).thumbnails || []).slice(-1)[0]?.url || "",
        handle: "", inscritos: numero(dono.subscriberCountText), videos_total: null, ...(temMembros(dono) ? { membros: true } : {}) };
    }
    return null;
  }

  // a página de um canal baixada em HTML: o JSON vem num <script> (dois jeitos, o novo e o antigo)
  function jsonDoHtml(html) {
    const m = html.match(/id="yt-initial-data"[^>]*>([\s\S]*?)<\/script>/) || html.match(/var ytInitialData = (\{.*?\});<\/script>/s);
    try { return m ? JSON.parse(m[1]) : null; } catch { return null; }
  }

  globalThis.RadarLer = { texto, numero, dias, duracao, videos, canal, jsonDoHtml };
})();
