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

  // ------------------------------------------------------------ o painel novo de estatísticas (2026-11-12)
  // O Studio trocou o painel (analytics/hub_overview): a tela agora vem pronta do youtubei/v1/browse, e o get_cards
  // passou a voltar os cartões com isFailed e statusCode 7 (sem permissão). Os mesmos números estão nos cartões do
  // browse: o de 48 horas é um gráfico de barras (início de cada hora em ms, views) e a aba Receita traz um gráfico
  // de linha com a receita dia a dia, cada ponto com o valor já escrito na moeda da página.
  function cabecalhos(auth) {
    const c = { "content-type": "application/json", authorization: auth, "x-origin": location.origin,
      "x-goog-authuser": String(cfg("SESSION_INDEX") || 0) };
    if (cfg("DELEGATED_SESSION_ID")) c["x-goog-pageid"] = cfg("DELEGATED_SESSION_ID");
    return c;
  }

  // o params do browse é um protobuf com o canal, {200: {1: {2: "UC..."}}}, em base64, igual ao que o Studio manda
  function paramsDoCanal(canal) {
    const id = [...new TextEncoder().encode(canal)];
    const dentro = [0x12, id.length, ...id], meio = [0x0a, dentro.length, ...dentro];
    return encodeURIComponent(btoa(String.fromCharCode(0xc2, 0x0c, meio.length, ...meio)));
  }

  async function tela(browseId, canal) {
    const auth = await autorizacao();
    if (!auth) return [];
    const r = await fetch("/youtubei/v1/browse?alt=json", { method: "POST", credentials: "include", headers: cabecalhos(auth),
      body: JSON.stringify({ context: cfg("INNERTUBE_CONTEXT"), browseId, params: paramsDoCanal(canal) }) });
    if (!r.ok) return [];
    const lista = [];
    (function andar(o) {
      if (!o || typeof o !== "object") return;
      if (o.cardViewModel) lista.push(o.cardViewModel);
      for (const k in o) andar(o[k]);
    })(await r.json());
    return lista;
  }

  const tituloDoCartao = (c) => (((c.topContent || {}).sectionHeaderViewModel || {}).headline || {}).content || "";
  function graficoDoCartao(c, tipo) {
    let achado = null;
    (function andar(o) {
      if (achado || !o || typeof o !== "object") return;
      if (o[tipo]) { achado = o[tipo]; return; }
      for (const k in o) andar(o[k]);
    })(c.bodyContent);
    return achado;
  }

  // o cartão de 48 horas: o único com gráfico de barras de hora em hora
  async function tempoRealNovo(canal) {
    const cards = await tela("FEanalytics_hub_channel_overview", canal);
    // o cartão Views: o primeiro gráfico de linha de um ponto por dia (domain = início do dia, measure = views)
    for (const c of cards) {
      const g = graficoDoCartao(c, "lineChartViewModel");
      const pts = g && g.series && g.series[0] && g.series[0].dataPoints;
      if (!pts || pts.length < 2 || +pts[1].domain - +pts[0].domain !== 864e5) continue;
      tituloViews = tituloDoCartao(c);
      viewsPorDia = { canal, dias: pts.filter((p) => p.measure != null).map((p) => [Number(p.domain), Number(p.measure) || 0]) };
      break;
    }
    for (const c of cards) {
      const g = graficoDoCartao(c, "barChartViewModel");
      const pts = g && g.series && g.series[0] && g.series[0].dataPoints;
      if (!pts || pts.length < 24 || +pts[1].domain - +pts[0].domain !== 3600e3) continue;
      tituloDe48h = tituloDoCartao(c);
      return pts.map((p) => [Number(p.domain), Number(p.measure) || 0]);
    }
    return null;
  }

  // a receita do último dia que já tem valor (os últimos dias o Studio ainda está processando e vêm sem valor)
  async function ultimaReceita(canal) {
    for (const c of await tela("FEanalytics_hub_channel_revenue", canal)) {
      const g = graficoDoCartao(c, "lineChartViewModel");
      const pts = g && g.series && g.series[0] && g.series[0].dataPoints;
      if (!pts || !pts.length) continue;
      const ultimo = [...pts].reverse().find((p) => p.measure != null);
      if (!ultimo) return null;
      const h = (g.dataHovercards || []).find((x) => String(x.domainValue) === String(ultimo.domain));
      const hover = h && h.hovercard && h.hovercard.hoverCardViewModel;
      const metrica = hover && hover.metric && hover.metric.simpleMetricViewModel;
      // a faixa hachurada do gráfico: os dias que o Studio ainda está processando (o valor ainda pode mudar)
      const faixa = ((g.domainAxis || {}).highlights || []).map((x) => x.rangeHighlight).find(Boolean);
      const valorTexto = (metrica && metrica.value && metrica.value.content) || "";
      return { titulo: tituloDoCartao(c), valor: valorTexto || String(ultimo.measure),
        // o measure vem em milésimos da moeda da página (665115 = R$665.12); o símbolo sai do texto do hover
        moeda: valorTexto.replace(/[\d.,\s]+$/, "").trim(),
        dias: pts.filter((p) => p.measure != null).map((p) => [Number(p.domain), Number(p.measure) / 1000]),
        dia: Number(ultimo.domain), diaTexto: (hover && hover.title && hover.title.content) || "",
        processando: !!faixa && Number(ultimo.domain) >= Number(faixa.start) };
    }
    return null;
  }

  // as views hora a hora das últimas 48 h (a última é a hora corrente, ainda contando)
  async function tempoReal(canal) {
    try { const novo = await tempoRealNovo(canal); if (novo) return novo; } catch { /* tenta o pedido antigo */ }
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

  let ultimoAno = 0, guardadoAno = null, ultimasHoras = null, tituloDe48h = "", receita = null, ultimaLeituraReceita = 0;
  let tituloViews = "", viewsPorDia = null;
  async function coletar() {
    const canal = canalDaPagina();
    if (!canal) return;
    try {
      if (Date.now() - ultimaLeituraReceita > 15 * 60 * 1000 || !receita || receita.canal !== canal) {   // muda 1x por dia
        ultimaLeituraReceita = Date.now();
        try { const r = await ultimaReceita(canal); receita = r ? { ...r, canal } : null; } catch { receita = null; }
        mostrarReceita();
      }
      const horas = await tempoReal(canal);
      if (Date.now() - ultimoAno > 15 * 60 * 1000 || !guardadoAno) {   // o dia a dia muda pouco: a cada 15 min
        const a = await ano(canal);
        if (a) { guardadoAno = a; ultimoAno = Date.now(); }
      }
      if (!horas && !guardadoAno) return;
      window.postMessage({ radarStudio: 1, numeros: { canal, quando: Date.now(), horas: horas || [], ...(guardadoAno || {}) } }, location.origin);
      if (horas) { ultimasHoras = horas; mostrarHoje(horas); guardarOntem(canal, horas); }
      mostrarOntem();
    } catch { /* o Studio mudou alguma coisa: não atrapalha a página */ }
  }

  // ------------------------------------------------------------ o "Hoje" no cartão Em tempo real
  const meiaNoite = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d.getTime(); };
  function mostrarHoje(horas) {
    const hoje = horas.filter(([t]) => t >= meiaNoite()).reduce((s, [, v]) => s + v, 0);
    // painel novo: o cartão com o título do cartão de 48 horas que veio no browse ("48 hour views", em qualquer idioma)
    const novo = cartaoDaTela(tituloDe48h);
    if (novo) return porLinha(novo, "radar-hoje", hoje.toLocaleString("pt-BR"), "visualizações hoje (desde a meia-noite) · Radar");
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

  // o cartão do painel novo pelo título (yt-card-view-model > ... > h2)
  function cartaoDaTela(titulo) {
    if (!titulo) return null;
    const h2 = [...document.querySelectorAll("yt-card-view-model h2")].find((e) => e.textContent.trim() === titulo);
    return h2 ? h2.closest("yt-card-view-model") : null;
  }

  // uma linha do Radar logo abaixo do título do cartão
  function porLinha(cartao, classe, numeroTexto, legendaTexto, dica) {
    const topo = cartao.querySelector("yt-section-header-view-model") || cartao.querySelector("h2");
    if (!topo) return;
    let caixa = cartao.querySelector(`.${classe}`);
    if (!caixa) {
      caixa = document.createElement("div");
      caixa.className = classe;
      caixa.style.cssText = "display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:6px 0 4px;padding:6px 10px;border-radius:8px;"
        + "background:rgba(57,255,136,.08);border:1px solid rgba(57,255,136,.35);font-family:Roboto,Arial,sans-serif;";
      topo.after(caixa);
    }
    caixa.title = dica || "";
    caixa.replaceChildren();
    const marca = document.createElement("span");
    marca.style.cssText = "width:9px;height:9px;border-radius:50%;background:#39ff88;box-shadow:0 0 6px #39ff88;flex:none;";
    const numero = document.createElement("b");
    numero.style.cssText = "font-size:16px;";
    numero.textContent = numeroTexto;
    const legenda = document.createElement("span");
    legenda.style.cssText = "font-size:12px;opacity:.75;";
    legenda.textContent = legendaTexto;
    caixa.append(marca, numero, legenda);
  }

  // no cartão Receita estimada (painel e aba Receita): sempre o valor do último dia que o Studio já fechou
  function mostrarReceita() {
    if (!receita || receita.canal !== canalDaPagina()) return;
    const cartao = cartaoDaTela(receita.titulo);
    if (!cartao) return;
    const dia = new Date(receita.dia).toLocaleDateString("pt-BR", { day: "numeric", month: "short", timeZone: "UTC" }).replace(/\./g, "");
    const caixa = cartao.querySelector(".radar-receita");
    if (caixa && caixa.dataset.de === `${receita.dia}${receita.valor}`) return;
    porLinha(cartao, "radar-receita", receita.valor, `último dia recebido · ${dia}${receita.processando ? " (ainda processando)" : ""} · Radar`,
      `Receita estimada de ${receita.diaTexto || dia}, o dia mais recente que já tem valor no Studio`
      + (receita.processando ? ". O Studio ainda está processando esse dia: o valor pode mudar um pouco." : "."));
    cartao.querySelector(".radar-receita").dataset.de = `${receita.dia}${receita.valor}`;
  }
  // ------------------------------------------------------------ o último dia no cartão Views (2026-11-14)
  // Pedido do usuário: "salvando quanto deu o último dia o tanto de visualizações e o valor mais ou menos esperado".
  // As views de ontem saem das barras de 48 h (de meia-noite a meia-noite, no fuso do computador) e ficam guardadas
  // no localStorage do Studio, por canal, para continuarem lá quando as 48 h passarem. O valor esperado é ontem ×
  // RPM dos últimos 7 dias que já têm receita no Studio (receita do dia ÷ views do mesmo dia, do cartão Views).
  //
  // 2026-11-15: o "ontem" do Radar dava 35.936 e o gráfico do Studio, 43.170 para o mesmo 14 de nov. O Radar somava as
  // barras de meia-noite a meia-noite no horário do Brasil, e o YouTube fecha o dia no horário do Pacífico (5 h
  // depois): eram duas janelas de 24 h diferentes. Agora o dia é o do Pacífico, e quando o gráfico do Studio já tem
  // esse dia, o número é o dele (o mesmo que a pessoa vê passando o mouse); as barras de 48 h ficam de reserva.
  const FUSO_YT = "America/Los_Angeles";
  const partesPT = (ms) => Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: FUSO_YT, year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", hourCycle: "h23" }).formatToParts(ms).map((x) => [x.type, x.value]));
  const chaveDia = (ms) => { const p = partesPT(ms); return `${p.year}-${p.month}-${p.day}`; };
  // a meia-noite do Pacífico do dia `chave` (UTC-8 no inverno, UTC-7 no verão)
  function inicioDoDiaPT(chave) {
    const [a, m, d] = chave.split("-").map(Number);
    for (const h of [7, 8]) { const t = Date.UTC(a, m - 1, d, h); if (partesPT(t).hour === "00") return t; }
    return Date.UTC(a, m - 1, d, 8);
  }
  const ontemPT = () => chaveDia(inicioDoDiaPT(chaveDia(Date.now())) - 12 * 36e5);
  const lerGuardado = (canal) => { try { return JSON.parse(localStorage.getItem(`radar-views-dia:${canal}`) || "{}"); } catch { return {}; } };
  // o número do gráfico diário do Studio para o dia `chave` (o domínio do ponto é a meia-noite UTC do dia)
  function viewsDoGrafico(canal, chave) {
    if (!viewsPorDia || viewsPorDia.canal !== canal) return null;
    const p = viewsPorDia.dias.find(([t]) => new Date(t).toISOString().slice(0, 10) === chave);
    return p && p[1] > 0 ? p[1] : null;
  }

  function guardarOntem(canal, horas) {
    const chave = ontemPT(), inicio = inicioDoDiaPT(chave), fim = inicioDoDiaPT(chaveDia(Date.now()));
    // só vale se as barras cobrem o dia inteiro de ontem
    if (!horas.length || horas[0][0] > inicio) return;
    const views = viewsDoGrafico(canal, chave) ?? horas.filter(([t]) => t >= inicio && t < fim).reduce((s, [, v]) => s + v, 0);
    const salvo = lerGuardado(canal);
    salvo[chave] = views;
    const dias = Object.keys(salvo).sort().slice(-90);   // três meses bastam
    try { localStorage.setItem(`radar-views-dia:${canal}`, JSON.stringify(Object.fromEntries(dias.map((k) => [k, salvo[k]])))); } catch { /* sem espaço: só não guarda */ }
  }

  // receita ÷ views dos últimos 7 dias que têm os dois números, em moeda por mil views
  function rpm(canal) {
    if (!receita || receita.canal !== canal || !viewsPorDia || viewsPorDia.canal !== canal || !receita.dias) return null;
    const views = new Map(viewsPorDia.dias.map(([t, v]) => [Math.floor(t / 864e5), v]));
    const pares = receita.dias.map(([t, r]) => [r, views.get(Math.floor(t / 864e5))]).filter(([r, v]) => r > 0 && v > 0).slice(-7);
    if (!pares.length) return null;
    const r = pares.reduce((s, [x]) => s + x, 0), v = pares.reduce((s, [, x]) => s + x, 0);
    return { valor: (r / v) * 1000, dias: pares.length };
  }

  const dinheiro = (moeda, n) => `${moeda || "$"}${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  function mostrarOntem() {
    const canal = canalDaPagina();
    const cartao = cartaoDaTela(tituloViews);
    if (!canal || !cartao) return;
    const chave = ontemPT();
    const doStudio = viewsDoGrafico(canal, chave);
    const views = doStudio ?? lerGuardado(canal)[chave];
    if (views == null) return;
    const dia = new Date(`${chave}T12:00:00Z`).toLocaleDateString("pt-BR", { day: "numeric", month: "short", timeZone: "UTC" }).replace(/\./g, "");
    const taxa = rpm(canal);
    const esperado = taxa ? ` · ≈ ${dinheiro(receita.moeda, (views * taxa.valor) / 1000)} esperado` : "";
    const texto = `${views.toLocaleString("pt-BR")}|${esperado}`;
    const caixa = cartao.querySelector(".radar-ontem");
    if (caixa && caixa.dataset.de === texto) return;
    porLinha(cartao, "radar-ontem", views.toLocaleString("pt-BR"), `visualizações ontem · ${dia}${esperado} · Radar`,
      (doStudio != null ? "Views de ontem do gráfico do Studio (o dia do YouTube, no horário do Pacífico). "
        : "Views de ontem somadas das barras de 48 h, no dia do YouTube (horário do Pacífico); o gráfico do Studio ainda não tinha esse dia. ")
      + (taxa ? `Valor esperado: views × RPM de ${dinheiro(receita.moeda, taxa.valor)} por mil views, `
        + `a média dos últimos ${taxa.dias} dias que já têm receita no Studio. É uma estimativa: o valor real aparece em 2 ou 3 dias.`
        : "O valor esperado aparece quando a receita dos últimos dias carregar."));
    cartao.querySelector(".radar-ontem").dataset.de = texto;
  }

  // o Studio redesenha os cartões ao trocar de período ou de aba: a linha volta sozinha
  setInterval(() => {
    try {
      mostrarReceita();
      mostrarOntem();
      const c = cartaoDaTela(tituloDe48h);
      if (ultimasHoras && c && !c.querySelector(".radar-hoje")) mostrarHoje(ultimasHoras);
    } catch { /* o Studio mudou: só não aparece */ }
  }, 1500);

  // ------------------------------------------------------------ visualizações engajadas de uma lista de vídeos
  const dois = (n) => String(n).padStart(2, "0");
  const diaId = (d) => Number(`${d.getFullYear()}${dois(d.getMonth() + 1)}${dois(d.getDate())}`);
  async function engajadas(ids) {
    const auth = await autorizacao();
    if (!auth || !ids.length) return null;
    const cabecalho = { "content-type": "application/json", authorization: auth, "x-origin": location.origin, "x-goog-authuser": String(cfg("SESSION_INDEX") || 0) };
    if (cfg("DELEGATED_SESSION_ID")) cabecalho["x-goog-pageid"] = cfg("DELEGATED_SESSION_ID");
    const consulta = { orders: [], returnDataInNewFormat: true, limitedToBatchedData: false, dimensions: [{ type: "VIDEO" }], limit: { pageSize: ids.length, pageOffset: 0 },
      metrics: [{ type: "ENGAGED_VIEWS", includeTotal: true }, { type: "EXTERNAL_VIEWS", includeTotal: true }], restricts: [{ dimension: { type: "VIDEO" }, inValues: ids }],
      timeRange: { dateIdRange: { inclusiveStart: 20050101, exclusiveEnd: diaId(new Date(Date.now() + 864e5)) } } };
    const r = await fetch(`/youtubei/v1/yta_web/join?alt=json&key=${cfg("INNERTUBE_API_KEY")}`, { method: "POST", credentials: "include", headers: cabecalho,
      body: JSON.stringify({ nodes: [{ key: "1__TOP_ENTITIES_TABLE_QUERY_KEY", value: { query: consulta } }], connectors: [], allowFailureResultNodes: true,
        context: cfg("INNERTUBE_CONTEXT"), trackingLabel: "web_explore_latest_activity" }) });
    if (!r.ok) return null;
    const tabela = ((((await r.json()).results || [])[0] || {}).value || {}).resultTable;
    if (!tabela) return null;
    const coluna = (tipo) => (((tabela.metricColumns || []).find((c) => c.metric && c.metric.type === tipo) || {}).counts || {}).values || [];
    const lista = (((tabela.dimensionColumns || []).find((c) => c.dimension && c.dimension.type === "VIDEO") || {}).strings || {}).values || [];
    const eng = coluna("ENGAGED_VIEWS"), vis = coluna("EXTERNAL_VIEWS"), saida = {};
    lista.forEach((id, i) => { saida[id] = { engajadas: Number(eng[i]) || 0, views: Number(vis[i]) || 0 }; });
    return saida;
  }
  window.addEventListener("message", async (e) => {
    if (e.source !== window || !e.data || e.data.radarEngajadas !== 1) return;
    let dados = null;
    try { dados = await engajadas(e.data.ids || []); } catch { /* o Studio mudou: a coluna fica com o traço */ }
    window.postMessage({ radarEngajadasResposta: 1, pedido: e.data.pedido, dados }, location.origin);
  });

  // os últimos vídeos do canal, publicados ou agendados, para o horário de postar avisar quando um novo sai colado neles
  async function ultimosVideos(canal) {
    const auth = await autorizacao();
    if (!auth) return [];
    const cabecalho = { "content-type": "application/json", authorization: auth, "x-origin": location.origin,
      "x-goog-authuser": String(cfg("SESSION_INDEX") || 0) };
    if (cfg("DELEGATED_SESSION_ID")) cabecalho["x-goog-pageid"] = cfg("DELEGATED_SESSION_ID");
    const r = await fetch("/youtubei/v1/creator/list_creator_videos?alt=json", { method: "POST", credentials: "include", headers: cabecalho,
      body: JSON.stringify({ context: cfg("INNERTUBE_CONTEXT"), order: "VIDEO_ORDER_DISPLAY_TIME_DESC", pageSize: 30,
        filter: { and: { operands: [{ channelIdIs: { value: canal } }, { videoOriginIs: { value: "VIDEO_ORIGIN_UPLOAD" } }] } },
        mask: { videoId: true, title: true, timePublishedSeconds: true, scheduledPublishingDetails: { all: true } } }) });
    if (!r.ok) return [];
    return ((await r.json()).videos || []).map((v) => ({ id: v.videoId, titulo: v.title || "", publicado: +v.timePublishedSeconds * 1000 || 0,
      agendamento: v.scheduledPublishingDetails || null }));
  }
  window.addEventListener("message", async (e) => {
    if (e.source !== window || !e.data || e.data.radarVideos !== 1) return;
    let videos = [];
    try { videos = await ultimosVideos(e.data.canal); } catch { /* o Studio mudou: o aviso só não aparece */ }
    window.postMessage({ radarVideosResposta: 1, pedido: e.data.pedido, videos }, location.origin);
  });

  // o painel e as estatísticas trocam de tela sem recarregar: pede de novo a cada minuto e quando a tela muda
  setTimeout(coletar, 2500);
  setInterval(coletar, 60 * 1000);
  let ultimaTela = location.pathname;
  setInterval(() => { if (location.pathname !== ultimaTela) { ultimaTela = location.pathname; setTimeout(coletar, 2000); } }, 1000);
})();
