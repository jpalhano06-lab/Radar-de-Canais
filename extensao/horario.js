// O horário de postar, na tela de agendar do Studio. Refeito em 2026-11-06, a pedido do usuário, para funcionar como o do
// Dotti Finder: escolhe o país do público e a hora em que o vídeo deve sair lá, vê a hora certa no relógio do Studio e
// coloca no agendamento com um aperto. País e hora ficam lembrados por canal, e as horas com mais views do próprio canal
// viram botões. As views vêm das últimas 48 horas que o studio.js lê; aqui elas vão se somando, até 35 dias.
// Melhorias pedidas depois: o botão coloca antes do pico, o país abre pelo público do canal, e a tela avisa quando já há
// outro vídeo do canal perto da hora escolhida.
//
// As contas ficam em globalThis.RadarHorario.contas para os testes.
(() => {
  // ------------------------------------------------------------ contas

  const dois = (n) => String(n).padStart(2, "0");
  const hhmm = (min) => `${dois(Math.floor(min / 60))}:${dois(min % 60)}`;
  const HORA_BOA = 17 * 60; // só uma sugestão: fim de tarde lá, até a pessoa trocar
  const DIAS_GUARDADOS = 35;
  const ANTES_DO_PICO = 150; // o vídeo precisa de tempo para circular: publicar na hora do pico já é tarde
  const VIDEOS_COLADOS = 20 * 36e5; // 20 h, e não 24: quem posta todo dia na mesma faixa varia uma hora ou outra

  const PAISES = [["us-leste", "Estados Unidos (Nova York)", "America/New_York"], ["us-centro", "Estados Unidos (Chicago)", "America/Chicago"],
    ["us-oeste", "Estados Unidos (Los Angeles)", "America/Los_Angeles"], ["uk", "Reino Unido", "Europe/London"], ["ca-leste", "Canadá (Toronto)", "America/Toronto"],
    ["ca-oeste", "Canadá (Vancouver)", "America/Vancouver"], ["au-leste", "Austrália (Sydney)", "Australia/Sydney"], ["au-oeste", "Austrália (Perth)", "Australia/Perth"],
    ["nz", "Nova Zelândia", "Pacific/Auckland"], ["ie", "Irlanda", "Europe/Dublin"], ["br", "Brasil (São Paulo)", "America/Sao_Paulo"], ["pt", "Portugal", "Europe/Lisbon"],
    ["es", "Espanha", "Europe/Madrid"], ["mx", "México", "America/Mexico_City"], ["ar", "Argentina", "America/Argentina/Buenos_Aires"], ["co", "Colômbia", "America/Bogota"],
    ["cl", "Chile", "America/Santiago"], ["fr", "França", "Europe/Paris"], ["de", "Alemanha", "Europe/Berlin"], ["nl", "Holanda", "Europe/Amsterdam"], ["be", "Bélgica", "Europe/Brussels"],
    ["it", "Itália", "Europe/Rome"], ["pl", "Polônia", "Europe/Warsaw"], ["se", "Suécia", "Europe/Stockholm"], ["tr", "Turquia", "Europe/Istanbul"], ["za", "África do Sul", "Africa/Johannesburg"],
    ["ae", "Emirados Árabes", "Asia/Dubai"], ["in", "Índia", "Asia/Kolkata"], ["ph", "Filipinas", "Asia/Manila"], ["id", "Indonésia", "Asia/Jakarta"], ["sg", "Singapura", "Asia/Singapore"],
    ["jp", "Japão", "Asia/Tokyo"], ["kr", "Coreia do Sul", "Asia/Seoul"]].map(([id, nome, zona]) => ({ id, nome, zona }));

  // zona é o nome do fuso ou {off: minutos}, quando o Studio escreve só "GMT-3"
  function partesEm(ms, zona) {
    if (typeof zona === "object") {
      const d = new Date(ms + zona.off * 6e4);
      return { a: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate(), min: d.getUTCHours() * 60 + d.getUTCMinutes() };
    }
    const p = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: zona, hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric",
      hour: "numeric", minute: "numeric" }).formatToParts(new Date(ms)).map((x) => [x.type, Number(x.value)]));
    return { a: p.year, m: p.month, d: p.day, min: (p.hour % 24) * 60 + p.minute };
  }

  const desvio = (ms, zona) => {
    const p = partesEm(ms, zona);
    return Math.round((Date.UTC(p.a, p.m - 1, p.d, 0, p.min) - Math.floor(ms / 6e4) * 6e4) / 6e4);
  };

  // o instante de um dia e hora escritos num fuso. Duas voltas: a primeira pode cair do outro lado do horário de verão
  function instanteDe(dia, min, zona) {
    const ingenuo = Date.UTC(dia.a, dia.m - 1, dia.d, 0, min);
    return ingenuo - desvio(ingenuo - desvio(ingenuo, zona) * 6e4, zona) * 6e4;
  }

  // a hora `min` de `de` no dia `dia`, vista no relógio de `para`. dias: -1 ou 1 quando lá é outro dia
  function converter(dia, min, de, para) {
    const p = partesEm(instanteDe(dia, min, de), para);
    return { min: p.min, dia: { a: p.a, m: p.m, d: p.d }, dias: Math.round((Date.UTC(p.a, p.m - 1, p.d) - Date.UTC(dia.a, dia.m - 1, dia.d)) / 864e5) };
  }

  function periodos(lingua) {
    try {
      const partes = (h) => new Intl.DateTimeFormat(lingua || undefined, { hour: "numeric", hour12: true, timeZone: "UTC" })
        .formatToParts(new Date(Date.UTC(2026, 0, 1, h))).find((x) => x.type === "dayPeriod")?.value.toUpperCase() || "";
      return { am: partes(9), pm: partes(21) };
    } catch { return { am: "", pm: "" }; }
  }

  // "17:00", "5:00 PM", "오후 5:00" viram minutos do dia
  function minutosDe(texto, lingua) {
    const t = String(texto || "").replace(/\s+/g, " ").trim(), m = t.match(/(\d{1,2})[:.h](\d{2})/);
    if (!m || +m[2] > 59) return null;
    const h = +m[1], resto = (t.slice(0, m.index) + t.slice(m.index + m[0].length)).toUpperCase(), { am, pm } = periodos(lingua);
    const tarde = (pm && resto.includes(pm)) || /\bP\.?\s?M\b/.test(resto), manha = !tarde && ((am && resto.includes(am)) || /\bA\.?\s?M\b/.test(resto));
    if (tarde || manha) return h > 12 ? null : ((h % 12) + (tarde ? 12 : 0)) * 60 + +m[2];
    return h > 23 ? null : h * 60 + +m[2];
  }

  function fusoEscrito(texto) {
    const m = String(texto || "").match(/\b(?:GMT|UTC)\s*([+\-−])\s*(\d{1,2})(?:\s*:?\s*(\d{2}))?/);
    if (!m || +m[2] > 14 || +(m[3] || 0) > 59) return null;
    return { off: (m[1] === "+" ? 1 : -1) * (+m[2] * 60 + +(m[3] || 0)) };
  }

  const semAcento = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ.]/g, "");

  function meses(lingua) {
    const nomes = [];
    for (const l of [lingua, "en-US"].filter(Boolean)) {
      try {
        for (const month of ["short", "long"]) {
          const f = new Intl.DateTimeFormat(l, { month, timeZone: "UTC" });
          for (let i = 0; i < 12; i++) nomes.push([semAcento(f.format(new Date(Date.UTC(2026, i, 15)))), i + 1]);
        }
      } catch { /* língua que o navegador não conhece */ }
    }
    return nomes;
  }

  // a data do campo do Studio: "7 de nov. de 2026", "Nov 7, 2026", "07/11/2026"
  function dataEscrita(texto, lingua) {
    const t = String(texto || ""), numerica = t.match(/\b(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})\b/);
    if (numerica) {
      const a = +numerica[1], b = +numerica[2], mesAntes = a <= 12 && (b > 12 || /^en-US/i.test(lingua || ""));
      const d = mesAntes ? b : a, m = mesAntes ? a : b;
      return m <= 12 && d >= 1 && d <= 31 ? { a: +numerica[3], m, d } : null;
    }
    const ano = t.match(/\b20\d{2}\b/);
    if (!ano) return null;
    const resto = t.replace(ano[0], " "), dia = resto.match(/\b\d{1,2}\b/), nomes = meses(lingua);
    let mes = 0;
    for (const p of semAcento(resto).match(/[a-z]{3,}/g) || []) {
      const achado = nomes.find(([n]) => n === p || n.startsWith(p) || (p.length > 3 && p.startsWith(n)));
      if (achado) { mes = achado[1]; break; }
    }
    return dia && mes && +dia[0] >= 1 && +dia[0] <= 31 ? { a: +ano[0], m: mes, d: +dia[0] } : null;
  }

  // junta as 48 horas lidas agora ao que já estava guardado. A última hora ainda está contando e fica de fora
  function juntarHoras(guardadas, horas, agora) {
    const mapa = { ...(guardadas || {}) }, corte = agora - DIAS_GUARDADOS * 864e5;
    for (const [t, v] of (horas || []).slice(0, -1)) {
      const ms = t < 1e12 ? t * 1000 : t;
      if (ms >= corte && ms + 36e5 <= agora) mapa[ms] = v;
    }
    for (const k of Object.keys(mapa)) if (+k < corte) delete mapa[k];
    return mapa;
  }

  // as horas com mais views, na média, no relógio pedido
  function melhoresHoras(mapa, zona, quantas = 3) {
    const soma = new Array(24).fill(0), n = new Array(24).fill(0), dias = new Set();
    for (const [t, v] of Object.entries(mapa || {})) {
      const p = partesEm(+t, zona), h = Math.floor(p.min / 60);
      soma[h] += +v || 0;
      n[h]++;
      dias.add(`${p.a}-${p.m}-${p.d}`);
    }
    const horas = soma.map((s, hora) => ({ hora, media: n[hora] ? s / n[hora] : -1 })).filter((x) => x.media >= 0)
      .sort((a, b) => b.media - a.media || a.hora - b.hora).slice(0, quantas);
    return { horas, pontos: Object.keys(mapa || {}).length, dias: dias.size };
  }

  const antesDoPico = (hora) => (hora * 60 - ANTES_DO_PICO + 1440) % 1440;

  // a sigla do país que mais assiste (Studio) vira uma opção da lista. Os países grandes abrem no fuso mais populoso
  const SIGLAS = { us: "us-leste", gb: "uk", ca: "ca-leste", au: "au-leste" };
  const paisDaSigla = (sigla) => {
    const s = String(sigla || "").toLowerCase(), id = SIGLAS[s] || s;
    return PAISES.find((p) => p.id === id) || null;
  };

  // sem o dado do Studio, o nome do canal costuma dizer: Canada Insight, UK CartWatch, 한국의 미래
  const PELO_NOME = [[/canad/i, "ca-leste"], [/\b(uk|britain|british|england)\b/i, "uk"], [/austral/i, "au-leste"], [/nederland|holland/i, "nl"], [/brasil|brazil/i, "br"],
    [/[\uac00-\ud7a3]/, "kr"], [/[\u3040-\u30ff]|日本/, "jp"]];
  const paisDoNome = (nome) => {
    const achado = PELO_NOME.find(([padrao]) => padrao.test(nome || ""));
    return achado ? PAISES.find((p) => p.id === achado[1]) : null;
  };

  // o instante agendado de um vídeo da lista do Studio. O formato do campo não está documentado: vale o primeiro número em
  // segundos, dentro dele, que caia no futuro
  function instanteAgendado(detalhes, agora) {
    for (const valor of Object.values(detalhes || {})) {
      if (valor && typeof valor === "object") {
        const dentro = instanteAgendado(valor, agora);
        if (dentro) return dentro;
      } else if (/^\d{10}$/.test(String(valor)) && +valor * 1000 > agora) return +valor * 1000;
    }
    return 0;
  }

  // o vídeo do canal mais perto do instante escolhido, se estiver perto demais
  function videoColado(videos, instante, proprio = "") {
    return (videos || []).filter((v) => v.id !== proprio && Math.abs(v.quando - instante) < VIDEOS_COLADOS)
      .sort((a, b) => Math.abs(a.quando - instante) - Math.abs(b.quando - instante))[0] || null;
  }

  globalThis.RadarHorario = { contas: { PAISES, partesEm, instanteDe, converter, minutosDe, fusoEscrito, dataEscrita, juntarHoras, melhoresHoras, hhmm,
    antesDoPico, paisDaSigla, paisDoNome, instanteAgendado, videoColado } };
  if (typeof document === "undefined" || typeof chrome === "undefined" || !chrome.runtime || window.__radarHorario) return;
  window.__radarHorario = true;

  // ------------------------------------------------------------ a tela do Studio

  const CHAVE = "horarioDoCanal", CHAVE_HORAS = "horasDoCanal";
  const $ = (s, r = document) => r.querySelector(s);
  const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
  const lingua = () => document.documentElement.lang || navigator.language;
  const visivel = (e) => !!e?.getClientRects().length;

  function criar(tag, props = {}, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) if (k.startsWith("on")) e[k] = v; else if (k === "class") e.className = v; else e.setAttribute(k, v);
    e.append(...filhos);
    return e;
  }

  async function esperar(teste, limite) {
    const fim = Date.now() + limite;
    for (;;) {
      const r = teste();
      if (r || Date.now() > fim) return r || null;
      await dormir(100);
    }
  }

  const listaDeHoras = () => [...document.querySelectorAll("tp-yt-paper-listbox")].find((l) => {
    const item = $("tp-yt-paper-item", l);
    return item && visivel(l) && minutosDe(item.textContent, lingua()) !== null;
  });

  // abre a lista de horas do Studio e aperta a hora. Devolve o erro, ou vazio
  async function agendar(minutos, caixa) {
    const campo = () => { const i = $("#time-of-day-container input", caixa); return visivel(i) ? i : null; };
    if (!campo()) $("#second-container-expand-button", caixa)?.click();
    const entrada = await esperar(campo, 3000);
    if (!entrada) return "Não achei o campo de hora. Escolha Programar primeiro.";
    entrada.click();
    const lista = await esperar(listaDeHoras, 2500);
    if (!lista) return "A lista de horas do Studio não abriu.";
    const item = [...lista.querySelectorAll("tp-yt-paper-item")].find((i) => minutosDe(i.textContent, lingua()) === minutos);
    if (!item) return "O Studio não tem esta hora na lista.";
    item.scrollIntoView({ block: "center" });
    await dormir(100);
    item.click();
    return "";
  }

  // o relógio em que o Studio está agendando: o que ele escreve na tela, ou o deste computador
  function relogioDoStudio(caixa) {
    let lido = "";
    const passo = document.createTreeWalker(caixa, NodeFilter.SHOW_TEXT);
    for (let n = passo.nextNode(); n; n = passo.nextNode()) if (!n.parentElement?.closest(".radar-hr")) lido += ` ${n.nodeValue}`;
    const escrito = fusoEscrito(lido);
    if (escrito) return { zona: escrito, nome: "fuso do Studio" };
    const zona = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    return { zona, nome: "relógio deste computador" };
  }

  function diaDoStudio(caixa, zona) {
    const campo = $("#datepicker-trigger, #date-picker input, ytcp-date-picker", caixa);
    const lido = campo && dataEscrita(campo.innerText || campo.textContent || campo.value, lingua());
    if (lido) return { dia: lido, lido: true };
    const p = partesEm(Date.now(), zona);
    return { dia: { a: p.a, m: p.m, d: p.d }, lido: false };
  }

  async function canalDaTela() {
    const m = location.pathname.match(/\/channel\/(UC[\w-]{22})/);
    if (m) return m[1];
    return (await chrome.storage.local.get("numerosCanal")).numerosCanal?.canal || "";
  }

  const pedirRadar = (caminho) => new Promise((ok) => {
    try { chrome.runtime.sendMessage({ tipo: "api", caminho }, (r) => ok(r || {})); } catch { ok({}); }
  });

  // quem manda no país: o que a pessoa escolheu neste canal, o país que mais assiste, o nome do canal, o último usado
  async function paisDoCanal(canal, lembrados) {
    const escolhido = PAISES.find((p) => p.id === lembrados[canal]?.pais);
    if (escolhido) return { pais: escolhido, dica: "Fica lembrado neste canal" };
    const publico = canal ? await pedirRadar(`/api/ext/publico/${canal}`) : {};
    const pelaSigla = paisDaSigla(publico.dados?.pais);
    if (pelaSigla) return { pais: pelaSigla, dica: "O país que mais assiste este canal" };
    const peloNome = paisDoNome($("#entity-name, #channel-title")?.textContent);
    if (peloNome) return { pais: peloNome, dica: "Pelo nome do canal: troque se o público for outro" };
    return { pais: PAISES.find((p) => p.id === lembrados._ultimo?.pais) || PAISES[0], dica: "Escolha uma vez: este canal lembra" };
  }

  // a lista sai do studio.js, dentro da página, com o login da pessoa
  let pedidos = 0;
  const videosDoCanal = (canal) => new Promise((ok) => {
    const pedido = ++pedidos;
    const ouvir = (e) => {
      if (e.source !== window || !e.data?.radarVideosResposta || e.data.pedido !== pedido) return;
      removeEventListener("message", ouvir);
      ok((e.data.videos || []).map((x) => ({ ...x, quando: instanteAgendado(x.agendamento, Date.now()) || x.publicado })).filter((x) => x.quando > 0));
    };
    addEventListener("message", ouvir);
    setTimeout(() => { removeEventListener("message", ouvir); ok([]); }, 8000);
    postMessage({ radarVideos: 1, pedido, canal }, location.origin);
  });

  const idDesteVideo = () => (location.pathname.match(/\/video\/([\w-]{11})/) || $("ytcp-video-info a[href*='youtu.be/'], a.ytcp-video-info[href*='youtu.be/']")?.href.match(/youtu\.be\/([\w-]{11})/) || [])[1] || "";

  async function montar(caixa) {
    const raiz = criar("div", { class: "radar-hr" });
    // sem isso, as teclas digitadas aqui viram atalhos do Studio
    for (const nome of ["keydown", "keyup", "keypress"]) raiz.addEventListener(nome, (e) => e.stopPropagation());
    caixa.append(raiz);
    const canal = await canalDaTela();
    const dados = await chrome.storage.local.get([CHAVE, CHAVE_HORAS]);
    const lembrados = dados[CHAVE] || {}, doCanal = lembrados[canal] || lembrados._ultimo || {}, inicial = await paisDoCanal(canal, lembrados);
    let pais = inicial.pais, hora = Number.isFinite(doCanal.hora) ? doCanal.hora : HORA_BOA, ultima = null, erro = "", videos = [];

    const guardar = () => {
      lembrados._ultimo = lembrados[canal] = { pais: pais.id, hora };
      chrome.storage.local.set({ [CHAVE]: lembrados }).catch(() => {});
    };
    const agoraLa = criar("span", { class: "radar-hr-agora" }), respostaHora = criar("b"), aviso = criar("p", { class: "radar-hr-aviso" });
    const colado = criar("p", { class: "radar-hr-aviso" });
    const seletor = criar("select", { "aria-label": "País do público", title: inicial.dica,
      onchange: () => { pais = PAISES.find((p) => p.id === seletor.value) || pais; erro = ""; guardar(); pintar(); } },
    ...PAISES.map((p) => criar("option", { value: p.id }, p.nome)));
    seletor.value = pais.id;
    const entrada = criar("input", { type: "time", step: "900", "aria-label": "Hora em que sai lá",
      oninput: () => { const m = minutosDe(entrada.value); if (m !== null) hora = m; pintar(); }, onchange: () => guardar() });
    const colocar = criar("button", { type: "button", class: "radar-hr-colocar", onclick: async () => {
      if (!ultima) return;
      erro = await agendar(ultima.min, caixa);
      colocar.textContent = erro ? "Colocar" : "Colocado ✓";
      setTimeout(() => { colocar.textContent = "Colocar"; }, 2500);
      pintar();
    } }, "Colocar");

    function pintar() {
      if (!raiz.isConnected) return;
      const relogio = relogioDoStudio(caixa), { dia, lido } = diaDoStudio(caixa, relogio.zona);
      agoraLa.textContent = `lá agora ${hhmm(partesEm(Date.now(), pais.zona).min)}`;
      if (document.activeElement !== entrada) entrada.value = hhmm(hora);
      const quero = minutosDe(entrada.value);
      if (quero === null) return;
      ultima = converter(dia, quero, pais.zona, relogio.zona);
      respostaHora.textContent = hhmm(ultima.min);
      respostaHora.parentElement.title = `${hhmm(quero)} em ${pais.nome} = ${hhmm(ultima.min)} (${relogio.nome})${lido ? "" : ", usando a data de hoje"}. Já conta o horário de verão.`;
      aviso.textContent = erro || (ultima.dias < 0 ? "No Studio ainda é o dia anterior: mude a data." : ultima.dias > 0 ? "No Studio já é o dia seguinte: mude a data." : "");
      aviso.hidden = !aviso.textContent;
      const instante = instanteDe(ultima.dia, ultima.min, relogio.zona), perto = videoColado(videos, instante, idDesteVideo());
      colado.textContent = perto ? `Já tem “${perto.titulo.slice(0, 50)}” a ${Math.max(1, Math.round(Math.abs(perto.quando - instante) / 36e5))} h desta hora: `
        + "vídeos colados tiram público um do outro." : "";
      colado.hidden = !perto;
    }
    raiz.pintar = pintar;
    raiz.append(criar("div", { class: "radar-hr-cab" }, criar("b", {}, "Horário de postar"), agoraLa),
      criar("div", { class: "radar-hr-linha" }, seletor, entrada, "→", criar("span", { class: "radar-hr-resposta" }, respostaHora, " no Studio"), colocar), aviso, colado);

    const relogio = relogioDoStudio(caixa), melhores = melhoresHoras((dados[CHAVE_HORAS] || {})[canal], relogio.zona);
    const canalCaixa = criar("div", { class: "radar-hr-canal" }, criar("b", {}, "Horas com mais views no seu canal"));
    if (melhores.pontos < 24) {
      canalCaixa.append(criar("p", {}, "Abra o Painel do Studio deste canal uma vez: o Radar lê as últimas 48 horas e volta com as horas."));
    } else {
      const recado = criar("p", {}, `Coloca 2h30 antes do pico, para o vídeo ter tempo de circular. Média de ${melhores.dias} ${melhores.dias === 1 ? "dia" : "dias"}, no ${relogio.nome}.`);
      canalCaixa.append(criar("div", { class: "radar-hr-horas" }, ...melhores.horas.map((h) => criar("button", { type: "button",
        title: `${Math.round(h.media).toLocaleString("pt-BR")} views por hora às ${dois(h.hora)}:00`, onclick: async () => {
          recado.textContent = await agendar(antesDoPico(h.hora), caixa) || "Hora colocada. Confira a data e salve.";
        } }, "Postar ", criar("b", {}, hhmm(antesDoPico(h.hora))), ` (pico ${dois(h.hora)}:00)`))), recado);
    }
    raiz.append(canalCaixa);
    pintar();
    if (canal) { videos = await videosDoCanal(canal); pintar(); }
  }

  // ------------------------------------------------------------ as views de hora em hora, somadas por canal

  let somando = Promise.resolve();
  const somarHoras = (numeros) => {
    if (!numeros?.canal || !numeros.horas?.length) return;
    somando = somando.then(async () => {
      const tudo = (await chrome.storage.local.get(CHAVE_HORAS))[CHAVE_HORAS] || {};
      tudo[numeros.canal] = juntarHoras(tudo[numeros.canal], numeros.horas, Date.now());
      await chrome.storage.local.set({ [CHAVE_HORAS]: tudo });
    }).catch(() => {});
  };

  let desligado = false;
  chrome.storage.local.get(["funcoesDesligadas", "numerosCanal"]).then((d) => {
    desligado = (d.funcoesDesligadas || []).includes("hora-pais");
    somarHoras(d.numerosCanal);
  }).catch(() => {});
  chrome.storage.onChanged.addListener((m) => {
    if (m.funcoesDesligadas) desligado = (m.funcoesDesligadas.newValue || []).includes("hora-pais");
    if (m.numerosCanal) somarHoras(m.numerosCanal.newValue);
  });

  // a tela de agendar abre e fecha sem trocar de página
  setInterval(() => {
    if (document.hidden) return;
    for (const caixa of document.querySelectorAll("ytcp-video-visibility-select #second-container, #second-container.ytcp-video-visibility-select")) {
      const ja = $(":scope > .radar-hr", caixa);
      if (desligado) ja?.remove();
      else if (ja) ja.pintar?.();
      else if (visivel(caixa)) montar(caixa).catch(() => {});
    }
  }, 1000);
})();
