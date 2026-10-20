// Roda dentro das páginas do YouTube Studio (world MAIN), com o login da própria pessoa: pede ao Studio os números do
// canal do mesmo jeito que o Studio pede (yta_web/get_cards, ver docs/studio-tempo-real.md) e manda para a extensão,
// que mostra no youtube.com com o "atualizado há X min". Nada disso vai para o servidor do Radar.
// Também põe o "Hoje" (views desde a meia-noite) no cartão Em tempo real do painel.
(() => {
  if (window.__radarStudio) return;
  window.__radarStudio = true;

  const cfg = (k) => window.ytcfg && window.ytcfg.get ? window.ytcfg.get(k) : null;
  const canalDaPagina = () => (location.pathname.match(/\/channel\/(UC[\w-]{22})/) || [])[1] || cfg("CHANNEL_ID") || "";

  // o cabeçalho de login que o próprio Studio manda em cada pedido (feito aqui dentro da página)
  async function autorizacao() {
    const c = (document.cookie.match(/(?:^|; )SAPISID=([^;]+)/) || [])[1];
    if (!c) return null;
    const ts = Math.floor(Date.now() / 1000);
    const buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(`${ts} ${c} ${location.origin}`));
    return `SAPISIDHASH ${ts}_${[...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("")}`;
  }

  async function cartoes(canal, periodo, cards) {
    const auth = await autorizacao();
    if (!auth) return null;
    const cabecalho = { "content-type": "application/json", authorization: auth, "x-origin": location.origin,
      "x-goog-authuser": String(cfg("SESSION_INDEX") || 0) };
    if (cfg("DELEGATED_SESSION_ID")) cabecalho["x-goog-pageid"] = cfg("DELEGATED_SESSION_ID");
    const r = await fetch(`/youtubei/v1/yta_web/get_cards?alt=json&key=${cfg("INNERTUBE_API_KEY")}`, {
      method: "POST", credentials: "include", headers: cabecalho,
      body: JSON.stringify({ context: cfg("INNERTUBE_CONTEXT"), cardConfigs: cards,
        screenConfig: { entity: { channelId: canal }, timePeriod: { timePeriodType: periodo }, currency: "USD",
          timeZoneOffsetSecs: -new Date().getTimezoneOffset() * 60 } }) });
    if (!r.ok) return null;
    const j = await r.json();
    return (j.cards || []).find((c) => !c.isFailed) || null;
  }

  // as views hora a hora das últimas 48 h (a última é a hora corrente, ainda contando)
  async function tempoReal(canal) {
    const c = await cartoes(canal, "ANALYTICS_TIME_PERIOD_TYPE_FOUR_WEEKS",
      [{ latestActivityCardConfig: { tableLimit: 3, includeSubsData: true }, failureMode: "ANALYTICS_CARD_FAILURE_MODE_HIDE" }]);
    const d = c && c.latestActivityCardData && c.latestActivityCardData.datas && c.latestActivityCardData.datas[0];
    if (!d) return null;
    const horas = d.mainChartData.dimensionColumns[0].timestamps.values.map(Number);
    const views = d.mainChartData.metricColumns[0].counts.values.map(Number);
    return horas.map((t, i) => [t, views[i] || 0]);
  }

  // 365 dias: views, tempo assistido (ms) e ganhos (milésimos de dólar), um ponto por dia
  async function ano(canal) {
    const c = await cartoes(canal, "ANALYTICS_TIME_PERIOD_TYPE_YEAR", [{ failureMode: "ANALYTICS_CARD_FAILURE_MODE_FAIL_PAGE",
      keyMetricCardConfig: { timePeriod: {}, metricTabConfigs: [{ metric: "EXTERNAL_VIEWS" }, { metric: "EXTERNAL_WATCH_TIME" }, { metric: "TOTAL_ESTIMATED_EARNINGS" }] } }]);
    const abas = c && c.keyMetricCardData && c.keyMetricCardData.keyMetricTabs;
    if (!abas) return null;
    const aba = (m) => abas.find((x) => x.primaryContent.metric === m);
    const serie = (m) => { const a = aba(m); return a ? a.primaryContent.mainSeries.datums.map((d) => Number(d.y) || 0) : []; };
    const total = (m) => { const a = aba(m); return a && a.primaryContent.total != null ? Number(a.primaryContent.total) : null; };
    // o total que o Studio dá (somar os dias arredonda diferente: 11.406,50 em vez de 11.406,49)
    return { views: serie("EXTERNAL_VIEWS"), assistido: serie("EXTERNAL_WATCH_TIME"), ganhos: serie("TOTAL_ESTIMATED_EARNINGS"),
      totalAssistido: total("EXTERNAL_WATCH_TIME"), totalGanhos: total("TOTAL_ESTIMATED_EARNINGS") };
  }

  let ultimoAno = 0, guardadoAno = null;
  async function coletar() {
    const canal = canalDaPagina();
    if (!canal) return;
    try {
      const horas = await tempoReal(canal);
      if (Date.now() - ultimoAno > 15 * 60 * 1000 || !guardadoAno) {   // o dia a dia muda pouco: a cada 15 min
        const a = await ano(canal);
        if (a) { guardadoAno = a; ultimoAno = Date.now(); }
      }
      if (!horas && !guardadoAno) return;
      window.postMessage({ radarStudio: 1, numeros: { canal, quando: Date.now(), horas: horas || [], ...(guardadoAno || {}) } }, location.origin);
      if (horas) mostrarHoje(horas);
    } catch { /* o Studio mudou alguma coisa: não atrapalha a página */ }
  }

  // ------------------------------------------------------------ o "Hoje" no cartão Em tempo real
  const meiaNoite = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d.getTime(); };
  function mostrarHoje(horas) {
    const hoje = horas.filter(([t]) => t >= meiaNoite()).reduce((s, [, v]) => s + v, 0);
    const rotulo = [...document.querySelectorAll("ytcp-app *")].find((e) => !e.children.length && /^(Últimas 48 horas|Visualizações · Últimas 48 horas|Last 48 hours|Views · Last 48 hours)$/.test(e.textContent.trim()));
    if (!rotulo) return;
    const bloco = rotulo.parentElement && rotulo.parentElement.parentElement ? rotulo.parentElement.parentElement : rotulo.parentElement;
    // numa linha própria logo abaixo do "Últimas 48 horas" (o canto de cima é onde o Dotti põe o dele)
    let caixa = bloco.parentElement.querySelector(":scope > .radar-hoje");
    if (!caixa) {
      caixa = document.createElement("div");
      caixa.className = "radar-hoje";
      caixa.style.cssText = "display:flex;align-items:center;gap:8px;margin:6px 0 4px;padding:6px 10px;border-radius:8px;"
        + "background:rgba(57,255,136,.08);border:1px solid rgba(57,255,136,.35);font-family:Roboto,Arial,sans-serif;";
      bloco.after(caixa);
    }
    caixa.replaceChildren();
    const marca = document.createElement("span");
    marca.style.cssText = "width:9px;height:9px;border-radius:50%;background:#39ff88;box-shadow:0 0 6px #39ff88;flex:none;";
    const numero = document.createElement("b");
    numero.style.cssText = "font-size:16px;";
    numero.textContent = hoje.toLocaleString("pt-BR");
    const legenda = document.createElement("span");
    legenda.style.cssText = "font-size:12px;opacity:.75;";
    legenda.textContent = "visualizações hoje (desde a meia-noite) · Radar";
    caixa.append(marca, numero, legenda);
  }

  // o painel e as estatísticas trocam de tela sem recarregar: pede de novo a cada minuto e quando a tela muda
  setTimeout(coletar, 2500);
  setInterval(coletar, 60 * 1000);
  let ultimaTela = location.pathname;
  setInterval(() => { if (location.pathname !== ultimaTela) { ultimaTela = location.pathname; setTimeout(coletar, 2000); } }, 1000);
})();
