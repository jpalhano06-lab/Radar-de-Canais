// O painel de anúncios no meio do vídeo, dentro do editor do YouTube Studio. Refeito em 2026-11-06, a pedido do usuário,
// para funcionar como o do Dotti Finder: três jeitos de distribuir (a cada, quantidade e pausas da fala), a prévia na faixa
// antes de colocar, trocar os que já estão lá, e cada espaço conferido depois de colocado.
//
// O jeito antigo mexia no player e apertava Inserir, mas o Studio cria o espaço onde está a agulha da linha do tempo: os
// anúncios caíam todos no mesmo lugar. Agora o tempo de cada um é escrito no campo da própria linha.
//
// As contas ficam em globalThis.RadarAnuncios.contas para os testes. publicar.js usa RadarAnuncios.colocar.
(() => {
  // ------------------------------------------------------------ contas

  const dois = (n) => String(n).padStart(2, "0");
  const finito = (x) => typeof x === "number" && Number.isFinite(x);
  const MAXIMO = 200; // de uma vez só: ninguém pede mais, e cada espaço custa uma volta no Studio
  const PERTO_DEMAIS = 120; // abaixo disso, o YouTube costuma ignorar um dos dois
  const VIDEO_MINIMO = 480; // só vídeo com 8 minutos ou mais tem anúncio no meio

  // o carimbo do Studio é H:MM:SS:QQ, com o quadro no fim
  function paraCarimbo(segundos, fps = 30) {
    const f = Math.max(1, Math.round(finito(fps) ? fps : 30));
    const quadros = Math.round(Math.max(0, finito(segundos) ? segundos : 0) * f);
    const q = quadros % f, s = (quadros - q) / f;
    return `${Math.floor(s / 3600)}:${dois(Math.floor(s % 3600 / 60))}:${dois(s % 60)}:${dois(q)}`;
  }

  function deCarimbo(texto, fps = 30) {
    const t = String(texto ?? "").trim();
    if (!/^\d+(:\d+){0,3}$/.test(t)) return null;
    const p = t.split(":").map(Number), f = Math.max(1, finito(fps) ? fps : 30);
    while (p.length < 4) p.unshift(0);
    return p[0] * 3600 + p[1] * 60 + p[2] + p[3] / f;
  }

  const tempo = (segundos) => {
    const s = Math.max(0, Math.round(finito(segundos) ? segundos : 0));
    const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60);
    return h ? `${h}:${dois(m)}:${dois(s % 60)}` : `${m}:${dois(s % 60)}`;
  };

  // "2" e "2,5" são minutos; "1:30" e "1:02:00" são relógio
  function deTempo(texto) {
    const t = String(texto ?? "").trim().replace(",", ".");
    if (!t) return null;
    if (/^\d+(\.\d+)?$/.test(t)) return Math.round(parseFloat(t) * 60);
    if (!/^\d+(:\d{1,2}){1,2}$/.test(t)) return null;
    const p = t.split(":").map(Number);
    if (p.slice(1).some((v) => v > 59)) return null;
    return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1];
  }

  // um a cada `passo` segundos, contados de `inicio`. Com início marcado, ele mesmo também recebe um
  function aCada({ dur, passo, inicio = 0 }) {
    if (!(dur > 0) || !(passo >= 1)) return [];
    const base = Math.min(Math.max(inicio, 0), dur), tempos = base > 0 ? [Math.round(base)] : [];
    for (let t = base + passo; t < dur && tempos.length < MAXIMO; t += passo) tempos.push(Math.round(t));
    return tempos;
  }

  function quantidade({ dur, n, inicio = 0 }) {
    const quantos = Math.min(Math.floor(n), MAXIMO);
    if (!(dur > 0) || !(quantos >= 1)) return [];
    const base = Math.min(Math.max(inicio, 0), dur), passo = (dur - base) / (quantos + 1);
    return Array.from({ length: quantos }, (_, i) => Math.round(base + (i + 1) * passo));
  }

  // a força do som em cada coluna do canvas: quantos pontos dela estão pintados
  function ondaDaImagem(rgba, largura, altura) {
    const forca = new Array(largura).fill(0);
    let pico = 0;
    for (let c = 0; c < largura; c++) {
      let n = 0;
      for (let l = 0; l < altura; l++) if (rgba[(l * largura + c) * 4 + 3] > 10) n++;
      forca[c] = altura ? n / altura : 0;
      pico = Math.max(pico, forca[c]);
    }
    return { forca, pico };
  }

  // os trechos quietos, em segundos. `esq` e `dir` dizem que parte do canvas é o vídeo (0 a 1): a onda tem margens
  function acharPausas(forca, { dur, pico, esq = 0, dir = 1, limiar = 10, minMs = 300, depoisDe = 0 }) {
    const colunas = forca?.length || 0;
    if (!colunas || !(dur > 0) || !(pico > 0)) return [];
    const faixa = dir - esq || 1, corte = limiar / 100 * pico, porColuna = dur / (colunas * faixa);
    const minimo = Math.max(1, minMs / 1000 / porColuna);
    const emSegundos = (c) => Math.min(Math.max((c / colunas - esq) / faixa, 0), 1) * dur;
    const achadas = [];
    let inicio = -1;
    for (let c = 0; c <= colunas; c++) {
      if (c < colunas && forca[c] <= corte) { if (inicio < 0) inicio = c; continue; }
      if (inicio >= 0 && c - inicio >= minimo) {
        const t = emSegundos((inicio + c) / 2);
        if (t > depoisDe && t < dur) achadas.push({ t, dura: (c - inicio) * porColuna });
      }
      inicio = -1;
    }
    return achadas;
  }

  // as pausas mais longas ganham, respeitando a distância mínima entre elas e os anúncios que vão ficar
  function escolherPausas(pausas, distancia, ocupados = []) {
    const longe = Math.max(0, distancia || 0), fica = [];
    for (const p of [...pausas].sort((a, b) => b.dura - a.dura || a.t - b.t)) {
      if (ocupados.some((o) => Math.abs(o - p.t) < longe)) continue;
      if (!fica.some((t) => Math.abs(t - p.t) < Math.max(longe, 1))) fica.push(p.t);
    }
    return fica.sort((a, b) => a - b);
  }

  // tira o que não pode entrar: cedo demais, no fim, repetido, em cima de um que fica, além do máximo
  function peneirar(tempos, { dur, naoAntes = 0, nosUltimos = 0, existentes = [] }) {
    const cedo = Math.max(1, naoAntes), tarde = dur - Math.max(1, nosUltimos), fica = [];
    for (const t of tempos.filter(finito).sort((a, b) => a - b)) {
      if (t < cedo || !(dur > 0) || t > tarde) continue;
      if (fica.length && t - fica[fica.length - 1] < 0.5) continue;
      if (existentes.some((e) => Math.abs(e - t) < 1)) continue;
      if (fica.length < MAXIMO) fica.push(t);
    }
    return fica;
  }

  // o plano inteiro, que a faixa mostra e o botão coloca
  function planejar({ modo, dur, inicio = 0, passo, n, pausas = [], distancia, nosUltimos = 0, existentes = [] }) {
    const peneira = { dur, nosUltimos, existentes };
    if (modo === "pausas") {
      const tarde = dur - Math.max(1, nosUltimos), cedo = Math.max(1, inicio);
      return peneirar(escolherPausas(pausas.filter((p) => p.t >= cedo && p.t <= tarde), distancia, existentes), { ...peneira, naoAntes: inicio });
    }
    return peneirar(modo === "quantidade" ? quantidade({ dur, n, inicio }) : aCada({ dur, passo, inicio }), peneira);
  }

  // os quadros por segundo, pela distância entre os quadros que o player entregou
  function fpsDasMarcas(marcas) {
    const passos = [];
    for (let i = 1; i < marcas.length; i++) if (marcas[i] > marcas[i - 1]) passos.push(marcas[i] - marcas[i - 1]);
    if (!passos.length) return 30;
    const bruto = 1 / passos.sort((a, b) => a - b)[Math.floor(passos.length / 2)];
    if (!finito(bruto) || bruto < 5 || bruto > 240) return 30;
    const padrao = [24, 25, 30, 48, 50, 60, 120].find((p) => Math.abs(bruto - p) <= 0.6);
    return padrao || Math.round(bruto);
  }

  // qual linha é a nova: a que sobra quando se tiram as de antes. Se sobrar mais de uma, a mais perto de onde ela nasce
  function acharNova(antes, depois, alvo, fps = 30) {
    const chave = (v) => { const s = deCarimbo(v, fps); return s === null ? `t${String(v).trim()}` : `q${Math.round(s * fps)}`; };
    const conta = new Map();
    for (const v of antes) conta.set(chave(v), (conta.get(chave(v)) || 0) + 1);
    const sobra = [];
    depois.forEach((v, i) => {
      const c = conta.get(chave(v)) || 0;
      if (c > 0) conta.set(chave(v), c - 1); else sobra.push(i);
    });
    if (sobra.length < 2 || !finito(alvo)) return sobra.length ? sobra[0] : -1;
    const distancia = (i) => { const s = deCarimbo(depois[i], fps); return s === null ? 1e9 : Math.abs(s - alvo); };
    return sobra.reduce((melhor, i) => (distancia(i) < distancia(melhor) ? i : melhor));
  }

  // o Studio recusa dois espaços no mesmo segundo, então a agulha precisa estar num lugar sem ninguém
  const cabe = (t, ocupados, dur) => t >= 1 && (!(dur > 2) || t <= dur - 1) && ocupados.every((o) => Math.abs(o - t) >= 1);

  function lugarLivre(ocupados, perto, dur) {
    const base = Math.max(1, Math.round(finito(perto) ? perto : 1)), tomados = ocupados.filter(finito);
    for (let d = 0; d <= 600; d++) for (const t of [base - d, base + d]) if (cabe(t, tomados, dur)) return t;
    return null;
  }

  // para onde tentar mandar um anúncio que o Studio não aceitou no tempo pedido
  function tempoVizinhos(t, dur, ocupados) {
    const tomados = ocupados.filter(finito);
    return [1, 2, 3, 5, 8, 10, 15].flatMap((d) => [t + d, t - d]).filter((c) => cabe(c, tomados, dur));
  }

  const previa = (tempos, quantos = 8) => (tempos.length <= quantos ? tempos.map(tempo).join(", ")
    : `${tempos.slice(0, quantos).map(tempo).join(", ")} e mais ${tempos.length - quantos}`);

  const contas = { paraCarimbo, deCarimbo, tempo, deTempo, aCada, quantidade, ondaDaImagem, acharPausas, escolherPausas, peneirar,
    planejar, fpsDasMarcas, acharNova, lugarLivre, tempoVizinhos, previa, MAXIMO };
  globalThis.RadarAnuncios = { contas };
  if (typeof document === "undefined" || typeof chrome === "undefined" || !chrome.runtime || window.__radarAnuncios) return;
  window.__radarAnuncios = true;

  // ------------------------------------------------------------ a tela do Studio

  const TELA = {
    cabecalho: "ytve-ad-breaks-editor-options-panel div.options-header",
    linhas: "ytve-ad-breaks-editor-options-panel .ad-break-row",
    campo: "ytve-framestamp-input input, ytve-formatted-input input",
    inserir: "#add-ad-break, ytcp-button[test-id='insert-ad-slot'] button",
    agulha: "ytve-playhead#playhead #label",
    relogio: "ytve-toolbar ytcp-media-timestamp-input #display",
    relogioCampo: "ytve-toolbar ytcp-media-timestamp-input input",
    marcas: "ytve-timeline-markers",
    video: "ytcp-html5-video-source video",
    onda: "ytve-audio-waveform canvas",
    faixa: "ytve-ad-breaks-editor-timeline #ad-breaks-row",
    zoom: "#zoom-slider",
    zoomMenos: "#zoom-out, #zoom-out-button, [aria-label='Diminuir zoom'], [aria-label='Menos zoom'], [aria-label='Zoom out'], [aria-label='Afastar']",
    automatico: "ytcp-checkbox-lit[test-id='auto-midroll-checkbox']",
    apagar: "ytcp-icon-button.delete-button",
    rotulo: ".manual-midroll-label",
    alerta: ".warning-icon",
  };
  const PAROU = new Error("parou");
  const FOLGA = 30; // ms para o Studio assentar a linha nova antes de escrever nela

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
  const linhas = () => $$(TELA.linhas);
  const campoDa = (l) => $(TELA.campo, l);
  const valorDa = (l) => String(campoDa(l)?.value || "").trim();
  const vermelha = (l) => /interrup|interromp/i.test($(TELA.rotulo, l)?.textContent || "") || !!$(TELA.alerta, l);
  const temposDasLinhas = (fps) => linhas().map((l) => deCarimbo(valorDa(l), fps)).filter((t) => t !== null);

  function duracao() {
    try {
      const projecao = JSON.parse($(TELA.marcas)?.getAttribute("projection") || "null");
      if (projecao?.maximumMs > 0) return projecao.maximumMs / 1000;
    } catch { /* o Studio mudou o atributo: vale o player */ }
    const v = $(TELA.video);
    if (finito(v?.duration) && v.duration > 0) return v.duration;
    const dur = String(v?.currentSrc || v?.src || "").match(/[?&]dur=([0-9.]+)/);
    return dur ? parseFloat(dur[1]) : 0;
  }

  const agulha = () => deCarimbo($(TELA.agulha)?.textContent || $(TELA.relogio)?.textContent) ?? 0;

  // o campo é do Polymer: ele só percebe o valor novo pelo setter nativo e pelos eventos
  const gravarValor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  function escrever(campo, valor, comEnter) {
    campo.focus();
    gravarValor.call(campo, valor);
    for (const nome of ["input", "change"]) campo.dispatchEvent(new Event(nome, { bubbles: true }));
    if (comEnter) {
      const tecla = { bubbles: true, key: "Enter", code: "Enter", keyCode: 13, which: 13 };
      for (const nome of ["keydown", "keyup"]) campo.dispatchEvent(new KeyboardEvent(nome, tecla));
    }
    campo.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  function moverAgulha(carimbo) {
    const c = $(TELA.relogioCampo), antes = document.activeElement;
    if (!c) return false;
    escrever(c, carimbo, true);
    if (antes && antes !== c && antes !== document.body) antes.focus?.();
    return true;
  }

  function botaoApagado(b) {
    const casca = b.closest("ytcp-button");
    return !!(b.disabled || b.getAttribute("aria-disabled") === "true" || casca?.hasAttribute("disabled") || casca?.getAttribute("aria-disabled") === "true");
  }

  // espera a tela mudar: reage na hora, em vez de dormir o tempo do pior caso
  function quando(teste, limite, sinal) {
    const ja = teste();
    if (ja) return Promise.resolve(ja);
    return new Promise((ok, falha) => {
      let acabou = false;
      const fim = (valor, erro) => {
        if (acabou) return;
        acabou = true;
        vigia.disconnect(); clearInterval(rede); clearTimeout(relogio);
        sinal?.removeEventListener("abort", parar);
        if (erro) falha(erro); else ok(valor);
      };
      const olhar = () => { if (acabou) return; const r = teste(); if (r) fim(r); };
      const parar = () => fim(null, PAROU);
      const vigia = new MutationObserver(olhar), rede = setInterval(olhar, 50), relogio = setTimeout(() => fim(teste() || null), limite);
      vigia.observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true });
      sinal?.addEventListener("abort", parar);
    });
  }

  // aperta Inserir e devolve o campo da linha que nasceu
  async function inserirUm(fps) {
    const botao = await quando(() => { const b = $(TELA.inserir); return b && !botaoApagado(b) ? b : null; }, 400);
    if (!botao) return null;
    const antes = linhas(), valores = antes.map(valorDa), nasce = agulha();
    const achar = () => {
      const agora = linhas();
      if (agora.length <= antes.length) return null;
      let i = acharNova(valores, agora.map(valorDa), nasce, fps);
      if (i < 0) i = agora.findIndex((l) => !antes.includes(l));
      return i >= 0 ? campoDa(agora[i]) : null;
    };
    botao.click();
    const campo = await quando(achar, 1500);
    if (!campo && linhas().length > antes.length) throw new Error("A linha nova apareceu sem o campo de tempo: o Studio pode ter mudado a tela.");
    if (campo) await dormir(FOLGA);
    return campo ? achar() || campo : null;
  }

  const temAnuncioEm = (t, fps) => temposDasLinhas(fps).some((s) => Math.abs(s - t) < 0.6);

  // o Studio às vezes devolve um tempo para o anterior: quem não ficou vai para o vizinho aceito mais perto
  async function conferir(escritos, ficam, planejados, fps, dur, resultado, lugar) {
    const faltam = () => escritos.filter((t) => !temAnuncioEm(t, fps));
    await quando(() => !faltam().length, 800);
    const donos = () => [...ficam, ...planejados, ...resultado.deslocados.map((d) => d.para)];
    const sobra = () => linhas().find((l) => {
      const s = deCarimbo(valorDa(l), fps);
      return s !== null && !donos().some((o) => Math.abs(o - s) < 0.6);
    });
    for (const t of faltam()) {
      let foi = false;
      for (const c of [t, ...tempoVizinhos(t, dur, [...donos(), ...(lugar === null ? [] : [lugar])])]) {
        const campo = sobra() && campoDa(sobra());
        if (!campo) break;
        escrever(campo, paraCarimbo(c, fps), false);
        campo.blur();
        await dormir(250);
        if (temAnuncioEm(c, fps)) { if (c !== t) resultado.deslocados.push({ de: t, para: c }); foi = true; break; }
      }
      if (foi) continue;
      const lixo = sobra() && $(TELA.apagar, sobra());
      if (lixo) { const n = linhas().length; lixo.click(); await quando(() => linhas().length < n, 800); }
      resultado.pulados.push(t);
      resultado.feitos--;
    }
  }

  async function porAnuncios(tempos, fps, sinal, avisar) {
    if (!$(TELA.inserir)) throw new Error("Não achei o botão Inserir espaço de anúncio: o Studio pode ter mudado a tela.");
    const resultado = { feitos: 0, pulados: [], deslocados: [] }, dur = duracao(), ficam = temposDasLinhas(fps), escritos = [];
    const agulhaAntes = agulha(), veu = document.getElementById("overlay-container"), veuAntes = veu?.style.visibility ?? "";
    if (veu) veu.style.visibility = "hidden"; // a janelinha de cada espaço novo piscaria na tela
    const levarAgulha = async (s) => {
      if (Math.abs(agulha() - s) > 0.4 && moverAgulha(paraCarimbo(s, fps))) await quando(() => Math.abs(agulha() - s) <= 0.4, 400);
    };
    let lugar = lugarLivre([...ficam, ...tempos], tempos[0], dur), recusas = 0;
    try {
      if (lugar !== null) await levarAgulha(lugar);
      for (const t of tempos) {
        if (sinal.aborted) throw PAROU;
        let campo = await inserirUm(fps);
        if (!campo) { // a agulha ficou em cima de um: outro lugar livre e mais uma tentativa
          const outro = lugarLivre([...temposDasLinhas(fps), ...tempos], t, dur);
          if (outro !== null) { lugar = outro; await levarAgulha(lugar); campo = await inserirUm(fps); }
        }
        if (!campo) {
          resultado.pulados.push(t);
          if (++recusas >= 3) throw new Error("O Studio parou de criar espaços de anúncio.");
          continue;
        }
        recusas = 0;
        const escrito = deCarimbo(campo.value, fps);
        if (escrito === null || Math.abs(escrito - t) > 0.02) {
          escrever(campo, paraCarimbo(t, fps), false);
          await dormir(FOLGA);
        }
        escritos.push(t);
        avisar(++resultado.feitos);
      }
    } finally {
      try {
        if (linhas().some((l) => l.contains(document.activeElement))) document.activeElement.blur();
        if (escritos.length) await conferir(escritos, ficam, tempos, fps, dur, resultado, lugar);
      } finally {
        moverAgulha(paraCarimbo(agulhaAntes, fps));
        if (veu) veu.style.visibility = veuAntes;
      }
    }
    return resultado;
  }

  const automaticoLigado = () => {
    const c = $(TELA.automatico);
    return !!c && (c.hasAttribute("checked") || $("#checkbox", c)?.getAttribute("aria-checked") === "true");
  };

  async function tirar(tipo, sinal, avisar) {
    const alvo = tipo === "vermelhos" ? vermelha : () => true;
    if (tipo === "todos" && automaticoLigado()) { // ligado, o Studio repõe os dele
      const c = $(TELA.automatico);
      ($("#checkbox", c) || c).click();
      await quando(() => !automaticoLigado(), 400);
    }
    let tirados = 0;
    for (let volta = 0; volta < 1000; volta++) {
      if (sinal.aborted) throw PAROU;
      const todas = linhas(), miras = todas.filter(alvo);
      if (!miras.length) break;
      // apagar muda a posição das que estão abaixo: em "todos" vai de baixo para cima, de uma vez; vermelhos, um por volta
      const lote = tipo === "todos" ? [...miras].reverse() : miras.slice(0, 1);
      const lixos = lote.map((l) => $(TELA.apagar, l)).filter(Boolean);
      if (!lixos.length) throw new Error(`Achei ${miras.length} para tirar, mas nenhum com o botão de apagar: o Studio pode ter mudado a tela.`);
      lixos.forEach((b) => b.click());
      if (!await quando(() => linhas().length < todas.length, 3000)) throw new Error("Apertei apagar e a lista do Studio não diminuiu em 3 segundos.");
      if (tipo === "todos") await quando(() => linhas().length <= todas.length - lixos.length, 600);
      tirados += todas.length - linhas().length;
      avisar(tirados);
    }
    return tirados;
  }

  // ------------------------------------------------------------ quadros por segundo e onda do som

  let fpsMedido = 0;
  function medirFps() {
    const v = $(TELA.video);
    if (fpsMedido) return Promise.resolve(fpsMedido);
    if (!v?.requestVideoFrameCallback) return Promise.resolve(30);
    return new Promise((ok) => {
      const antes = { t: v.currentTime, parado: v.paused, mudo: v.muted }, marcas = [];
      let acabou = false;
      const fim = (fps, medido) => {
        if (acabou) return;
        acabou = true;
        clearTimeout(relogio);
        try { if (antes.parado) v.pause(); v.currentTime = antes.t; v.muted = antes.mudo; } catch { /* o player saiu da tela */ }
        if (medido) fpsMedido = fps;
        ok(fps);
      };
      const relogio = setTimeout(() => fim(30, false), 1500);
      const quadro = (_, dados) => {
        if (acabou) return;
        marcas.push(dados.mediaTime);
        if (marcas.length >= 7) fim(fpsDasMarcas(marcas), true); else v.requestVideoFrameCallback(quadro);
      };
      try {
        v.muted = true;
        v.requestVideoFrameCallback(quadro);
        v.play()?.catch?.(() => fim(30, false));
      } catch { fim(30, false); }
    });
  }

  function zoomAgora() {
    const z = $(TELA.zoom);
    const v = Number(z?.getAttribute("value") ?? z?.getAttribute("aria-valuenow") ?? z?.value ?? 0);
    return finito(v) ? v : 0;
  }

  // a onda só mostra o vídeo inteiro com o zoom todo para trás
  async function afastarZoom() {
    const z = $(TELA.zoom);
    if (!z || zoomAgora() <= 0) return;
    const casa = z.parentElement?.parentElement?.parentElement?.parentElement || z.parentElement;
    const menos = casa && $(TELA.zoomMenos, casa);
    for (let i = 0; menos && i < 30 && zoomAgora() > 0; i++) {
      const antes = zoomAgora();
      menos.click();
      if (!await quando(() => zoomAgora() < antes, 300)) break;
    }
    for (let i = 0; i < 40 && zoomAgora() > 0; i++) {
      const antes = zoomAgora();
      for (const [key, keyCode] of [["Home", 36], ["ArrowLeft", 37]]) {
        for (const nome of ["keydown", "keyup"]) z.dispatchEvent(new KeyboardEvent(nome, { key, code: key, keyCode, which: keyCode }));
      }
      if (!await quando(() => zoomAgora() < antes, 250)) break;
    }
  }

  function lerOnda() {
    if (zoomAgora() > 0) return { erro: "Não consegui afastar o zoom da linha do tempo.", zoom: true };
    const canvas = $(TELA.onda);
    if (!canvas?.width || !canvas.height) return { erro: "Não achei a onda do som no Studio." };
    let imagem;
    try { imagem = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data; }
    catch { return { erro: "O navegador não deixou ler a onda do som." }; }
    const { forca, pico } = ondaDaImagem(imagem, canvas.width, canvas.height);
    if (!(pico > 0)) return { erro: "A onda do som ainda não carregou." };
    let esq = 0, dir = 1;
    const c = canvas.getBoundingClientRect(), f = $(TELA.faixa)?.getBoundingClientRect();
    if (c.width > 0 && f?.width > 0) { esq = (f.left - c.left) / c.width; dir = (f.right - c.left) / c.width; }
    return { forca, pico, esq, dir };
  }

  // ------------------------------------------------------------ o painel

  const PASSOS = [[30, "30 s"], ...[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20].map((m) => [m * 60, `${m} min`])];
  const ajuste = { modo: "cada", passo: 180, n: 4, inicio: "0:00", distancia: 180, limiar: 10, minMs: 300, nosUltimos: 0, trocar: true, maisAjustes: false };
  const CHAVE = "radar-anuncios";
  const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;

  let desligado = false, aberto = false, ui = null, corrida = null, onda = null, ondaErro = "", procurando = false, ondaTentada = "", armado = 0;
  let recado = { texto: "", tipo: "" }, gravacao = 0;

  chrome.storage.local.get(["funcoesDesligadas", CHAVE]).then((d) => {
    desligado = (d.funcoesDesligadas || []).includes("anuncios-onda");
    for (const k of Object.keys(ajuste)) if (typeof d[CHAVE]?.[k] === typeof ajuste[k]) ajuste[k] = d[CHAVE][k];
  }).catch(() => {});
  chrome.storage.onChanged.addListener((m) => {
    if (m.funcoesDesligadas) desligado = (m.funcoesDesligadas.newValue || []).includes("anuncios-onda");
  });

  function guardar() {
    clearTimeout(gravacao);
    gravacao = setTimeout(() => chrome.storage.local.set({ [CHAVE]: ajuste }).catch(() => {}), 400);
  }

  function criar(tag, props = {}, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) if (k.startsWith("on")) e[k] = v; else if (k === "class") e.className = v; else e.setAttribute(k, v);
    e.append(...filhos);
    return e;
  }
  const botao = (classe, texto, onclick) => criar("button", { type: "button", class: classe, onclick }, texto);
  const trocarTexto = (e, texto) => { if (e.textContent !== texto) e.textContent = texto; };
  const mostrar = (e, sim) => { if (e.hidden === sim) e.hidden = !sim; };
  const mudou = () => { guardar(); pintar(); };

  function seletor(rotulo, chave) {
    return criar("select", { class: "radar-an-sel", "aria-label": rotulo, onchange: (e) => { ajuste[chave] = +e.target.value; mudou(); } },
      ...PASSOS.map(([v, nome]) => criar("option", { value: String(v) }, nome)));
  }

  function numero(rotulo, chave, minimo, maximo) {
    return criar("input", { type: "text", inputmode: "decimal", class: "radar-an-num", "aria-label": rotulo, value: String(ajuste[chave]).replace(".", ","),
      oninput: (e) => {
        const v = parseFloat(e.target.value.replace(",", ".")), serve = finito(v) && v >= minimo && v <= maximo;
        e.target.classList.toggle("ruim", !serve && e.target.value.trim() !== "");
        if (serve) { ajuste[chave] = v; mudou(); }
      } });
  }

  function montar() {
    const raiz = criar("section", { class: "radar-an", role: "dialog", "aria-label": "Anúncios do Radar", hidden: "" });
    // sem isso, as teclas digitadas aqui viram atalhos do editor do Studio
    for (const nome of ["keydown", "keyup", "keypress"]) raiz.addEventListener(nome, (e) => e.stopPropagation());
    const abrir = criar("button", { type: "button", class: "radar-an-abrir", "aria-haspopup": "dialog",
      onclick: () => { aberto = !aberto; pintar(); posicionar(); } }, "Radar · Anúncios");
    const ancora = criar("div", { class: "radar-an-ancora" }, abrir);

    const modos = {};
    for (const [id, nome] of [["cada", "A cada"], ["quantidade", "Quantidade"], ["pausas", "Pausas da fala"]]) {
      modos[id] = botao("radar-an-modo", nome, () => {
        ajuste.modo = id; recado = { texto: "", tipo: "" }; mudou();
        if (id === "pausas" && !onda) procurarPausas(false);
      });
    }
    const passo = seletor("Intervalo entre anúncios", "passo"), distancia = seletor("Distância mínima entre anúncios", "distancia");
    const n = numero("Quantos anúncios", "n", 1, MAXIMO);
    const inicio = criar("input", { type: "text", class: "radar-an-num radar-an-tempo", placeholder: "0:00", "aria-label": "A partir de",
      oninput: (e) => {
        const serve = deTempo(e.target.value || "0") !== null;
        e.target.classList.toggle("ruim", !serve);
        if (serve) { ajuste.inicio = e.target.value.trim() || "0:00"; mudou(); }
      } });
    const denovo = botao("radar-an-mini", "Procurar de novo", () => procurarPausas(true));
    const parteCada = criar("div", { class: "radar-an-parte" }, "Um a cada", passo);
    const parteQtd = criar("div", { class: "radar-an-parte" }, n, "anúncios");
    const partePausas = criar("div", { class: "radar-an-parte" }, "Com", distancia, "entre eles", denovo);

    const trilha = criar("div", { class: "radar-an-trilha" }), fimDaRegua = criar("span");
    const faixa = criar("div", { class: "radar-an-faixa", role: "img" }, trilha, criar("div", { class: "radar-an-regua" }, criar("span", {}, "0:00"), fimDaRegua));
    const resumoTexto = criar("span");
    const sugestao = botao("radar-an-mini", "", () => {
      if (sugestao.dataset.faz === "cada") ajuste.modo = "cada"; else ajuste.distancia = +sugestao.dataset.faz;
      mudou();
    });
    const resumo = criar("div", { class: "radar-an-resumo" }, resumoTexto, sugestao);
    const trocaTexto = criar("span");
    const troca = criar("button", { type: "button", role: "switch", class: "radar-an-troca", onclick: () => { ajuste.trocar = !ajuste.trocar; mudou(); } },
      criar("i"), trocaTexto);
    const colocar = botao("radar-an-colocar", "", () => comecarColocar());
    const enche = criar("i"), contagem = criar("span", { class: "radar-an-conta" });
    const andamento = criar("div", { class: "radar-an-andamento", role: "status" }, criar("div", { class: "radar-an-barra" }, enche), contagem,
      botao("radar-an-mini", "Parar", () => corrida?.ctrl.abort()));
    const aviso = criar("p", { class: "radar-an-aviso", role: "status" });

    const tiraVermelhos = botao("radar-an-mini", "", () => comecarTirar("vermelhos")), tiraTodos = botao("radar-an-mini", "", () => comecarTirar("todos"));
    tiraVermelhos.title = "Tirar os que o YouTube marcou de vermelho: ele não usa esses";
    tiraTodos.title = "Tirar todos os anúncios do vídeo";
    const abreAjustes = botao("radar-an-mini radar-an-direita", "Ajustes", () => { ajuste.maisAjustes = !ajuste.maisAjustes; mudou(); });
    const gaveta = criar("div", { class: "radar-an-gaveta" },
      criar("div", { class: "radar-an-parte" }, "Nada nos últimos", numero("Segundos livres no fim", "nosUltimos", 0, 3600), "s"),
      criar("div", { class: "radar-an-parte" }, "Pausa: som abaixo de", numero("Limite do som, em porcentagem", "limiar", 1, 90), "% por",
        numero("Duração da pausa, em milissegundos", "minMs", 50, 10000), "ms"));

    raiz.append(criar("div", { class: "radar-an-modos" }, ...Object.values(modos)),
      criar("div", { class: "radar-an-linha" }, parteCada, parteQtd, partePausas, criar("div", { class: "radar-an-parte" }, "a partir de", inicio)),
      faixa, resumo, troca, colocar, andamento, aviso, criar("div", { class: "radar-an-rodape" }, tiraVermelhos, tiraTodos, abreAjustes), gaveta);
    return { raiz, ancora, abrir, modos, passo, distancia, inicio, denovo, parteCada, parteQtd, partePausas, trilha, fimDaRegua, faixa, resumo, resumoTexto,
      sugestao, troca, trocaTexto, colocar, andamento, enche, contagem, aviso, tiraVermelhos, tiraTodos, abreAjustes, gaveta };
  }

  // o que vale agora: duração, o que já está lá e o plano com o ajuste de agora
  function retrato() {
    const dur = duracao(), existentes = linhas().map((l) => ({ t: deCarimbo(valorDa(l)), vermelha: vermelha(l) })).filter((x) => x.t !== null);
    if (onda && onda.url !== location.href) onda = null;
    const inicio = deTempo(ajuste.inicio || "0") ?? 0, trocando = ajuste.trocar && existentes.length > 0, total = linhas().length;
    const pausas = onda ? acharPausas(onda.forca, { ...onda, dur, limiar: ajuste.limiar, minMs: ajuste.minMs, depoisDe: inicio }) : null;
    const tempos = planejar({ modo: ajuste.modo, dur, inicio, passo: ajuste.passo, n: ajuste.n, pausas: pausas || [], distancia: ajuste.distancia,
      nosUltimos: ajuste.nosUltimos, existentes: trocando ? [] : existentes.map((x) => x.t) });
    const ficam = [...tempos, ...(trocando ? [] : existentes.map((x) => x.t))].sort((a, b) => a - b);
    const menor = ficam.slice(1).reduce((m, t, i) => Math.min(m, t - ficam[i]), Infinity);
    return { dur, existentes, total, vermelhas: linhas().filter(vermelha).length, pausas, tempos, trocando, menor };
  }

  let faixaDesenhada = "";
  function desenharFaixa(r) {
    const chave = JSON.stringify([r.dur, r.trocando, r.existentes, r.tempos]);
    if (chave === faixaDesenhada) return;
    faixaDesenhada = chave;
    ui.trilha.textContent = "";
    if (!(r.dur > 0)) return;
    const traco = (t, classe) => {
      const i = criar("i", { class: `radar-an-t ${classe}` });
      i.style.left = `${Math.min(100, Math.max(0, t / r.dur * 100)).toFixed(2)}%`;
      ui.trilha.append(i);
    };
    for (const x of r.existentes) traco(x.t, `velho${x.vermelha ? " vermelho" : ""}${r.trocando ? " sai" : ""}`);
    for (const t of r.tempos) traco(t, "novo");
    ui.fimDaRegua.textContent = tempo(r.dur);
    ui.faixa.title = r.tempos.length ? previa(r.tempos, 40) : "";
    ui.faixa.setAttribute("aria-label", r.tempos.length ? `${plural(r.tempos.length, "anúncio novo", "anúncios novos")}: ${previa(r.tempos, 40)}` : "Nenhum anúncio novo");
  }

  function pintarResumo(r, pausas, buscando, curto) {
    const n = r.tempos.length;
    let texto, ruim = true, faz = "", fazTexto = "";
    if (!(r.dur > 0)) { texto = "Carregando o vídeo…"; ruim = false; }
    else if (curto) texto = "Só vídeos com 8 min ou mais têm anúncio no meio.";
    else if (buscando) { texto = "Procurando pausas…"; ruim = false; }
    else if (pausas && ondaErro) texto = ondaErro;
    else if (!n && pausas) {
      const achadas = r.pausas?.length || 0;
      if (!achadas) { texto = "O vídeo não tem pausas longas."; faz = "cada"; fazTexto = "Usar “A cada”"; }
      else {
        texto = `${plural(achadas, "pausa", "pausas")}, perto demais umas das outras.`;
        const menor = PASSOS.map((p) => p[0]).filter((v) => v < ajuste.distancia && v >= 60).pop();
        if (menor) { faz = String(menor); fazTexto = `Tentar com ${menor / 60} min`; }
      }
    } else if (!n) texto = "Nenhum anúncio cabe com esse ajuste.";
    else if (r.menor < PERTO_DEMAIS) texto = `${plural(n, "novo", "novos")} · perto demais: o YouTube pode não usar todos`;
    else {
      texto = plural(n, "anúncio novo", "anúncios novos") + (pausas && r.pausas ? ` · ${plural(r.pausas.length, "pausa achada", "pausas achadas")}` : "");
      ruim = false;
    }
    if (n >= MAXIMO) texto += ` · máximo de ${MAXIMO} de uma vez`;
    trocarTexto(ui.resumoTexto, texto);
    ui.resumo.classList.toggle("ruim", ruim);
    ui.sugestao.dataset.faz = faz;
    trocarTexto(ui.sugestao, fazTexto);
    mostrar(ui.sugestao, !!faz && !corrida);
  }

  function pintar() {
    if (!ui) return;
    const r = retrato(), pausas = ajuste.modo === "pausas", curto = r.dur > 0 && r.dur < VIDEO_MINIMO;
    ui.abrir.setAttribute("aria-expanded", String(aberto));
    ui.abrir.classList.toggle("on", aberto);
    mostrar(ui.raiz, aberto);
    for (const [id, b] of Object.entries(ui.modos)) b.classList.toggle("on", ajuste.modo === id);
    mostrar(ui.parteCada, ajuste.modo === "cada");
    mostrar(ui.parteQtd, ajuste.modo === "quantidade");
    mostrar(ui.partePausas, pausas);
    ui.passo.value = String(ajuste.passo);
    ui.distancia.value = String(ajuste.distancia);
    if (document.activeElement !== ui.inicio && ui.inicio.value !== ajuste.inicio) ui.inicio.value = ajuste.inicio;
    ui.denovo.disabled = procurando || !!corrida;

    if (pausas && aberto && !onda && !procurando && !corrida && ondaTentada !== location.href) setTimeout(() => procurarPausas(false), 0);
    const buscando = pausas && !onda && (procurando || !ondaErro);
    ui.trilha.classList.toggle("procurando", buscando);
    desenharFaixa(r);
    pintarResumo(r, pausas, buscando, curto);

    mostrar(ui.troca, r.total > 0);
    ui.troca.setAttribute("aria-checked", String(ajuste.trocar));
    trocarTexto(ui.trocaTexto, r.total === 1 ? "Trocar o que já está lá" : `Trocar os ${r.total} que já estão lá`);

    const n = r.tempos.length, pode = !corrida && n > 0 && !curto && !buscando && !(pausas && ondaErro);
    trocarTexto(ui.colocar, r.trocando ? `Apagar ${r.total} e colocar ${n}` : `Colocar ${plural(n, "anúncio", "anúncios")}`);
    mostrar(ui.colocar, pode);

    mostrar(ui.andamento, !!corrida);
    if (corrida) {
      ui.enche.style.width = `${corrida.total ? Math.min(100, corrida.feitos / corrida.total * 100).toFixed(1) : 0}%`;
      trocarTexto(ui.contagem, `${corrida.fase === "tirar" ? "apagando " : ""}${corrida.feitos} de ${corrida.total}`);
    }
    trocarTexto(ui.aviso, recado.texto);
    ui.aviso.className = `radar-an-aviso ${recado.tipo}`.trim();
    mostrar(ui.aviso, !!recado.texto);

    trocarTexto(ui.tiraVermelhos, `Vermelhos ${r.vermelhas}`);
    ui.tiraVermelhos.disabled = !!corrida || !r.vermelhas;
    trocarTexto(ui.tiraTodos, armado ? "Toque de novo" : `Todos ${r.total}`);
    ui.tiraTodos.disabled = !!corrida || !r.total;
    ui.tiraTodos.classList.toggle("armado", !!armado);
    ui.abreAjustes.classList.toggle("on", ajuste.maisAjustes);
    mostrar(ui.gaveta, ajuste.maisAjustes);
  }

  async function procurarPausas(denovo) {
    if (procurando || corrida || (onda && onda.url === location.href && !denovo)) return;
    procurando = true; ondaTentada = location.href; ondaErro = "";
    if (denovo) onda = null;
    pintar();
    let lida = lerOnda();
    try {
      if (lida.zoom) { await afastarZoom(); lida = lerOnda(); }
      if (lida.erro && !lida.zoom) { // a onda redesenha depois do zoom: vale esperar um pouco
        lida = await quando(() => { const x = lerOnda(); return x.erro ? null : x; }, 2500) || lerOnda();
      }
    } catch { lida = { erro: "Não consegui ler a onda do som." }; }
    procurando = false;
    if (lida.erro) { onda = null; ondaErro = lida.erro; } else onda = { ...lida, url: location.href };
    pintar();
  }

  function fechamento({ feitos, pulados = [], deslocados = [], erro, total, tirados }) {
    const salvar = " Confira e salve no Studio.", tirou = tirados ? `${plural(tirados, "apagado", "apagados")}, ` : "";
    if (erro === PAROU) return { texto: `Parei: ${tirou}${feitos} de ${total} colocados.${feitos || tirados ? salvar : ""}`, tipo: "" };
    if (erro) return { texto: `${erro.message || erro}${feitos || tirados ? ` ${tirou}${feitos} colocados.${salvar}` : ""}`, tipo: "erro" };
    const foram = deslocados.length ? ` ${plural(deslocados.length, "foi", "foram")} para o tempo aceito mais perto (${deslocados.slice(0, 3)
      .map((d) => `${tempo(d.de)} para ${tempo(d.para)}`).join(", ")}${deslocados.length > 3 ? "…" : ""}).` : "";
    const recusou = pulados.length ? ` O Studio não aceitou ${pulados.length} (${previa(pulados, 4)}).` : "";
    return { texto: `${tirou}${plural(feitos, "anúncio colocado", "anúncios colocados")}.${foram}${recusou}${salvar}`, tipo: feitos ? "ok" : "erro" };
  }

  // o trabalho de colocar, sem tela: serve ao painel e ao botão de um aperto só do publicar.js
  async function executar(tempos, { trocando, fps = 30, sinal, fase }) {
    let tirados = 0, resultado = null, erro = null, feitos = 0;
    try {
      if (trocando) {
        const total = linhas().length;
        fase("tirar", total, 0);
        tirados = await tirar("todos", sinal, (k) => { tirados = k; fase("tirar", total, k); });
      }
      fase("colocar", tempos.length, 0);
      resultado = await porAnuncios(tempos, fps, sinal, (k) => { feitos = k; fase("colocar", tempos.length, k); });
      feitos = resultado.feitos;
    } catch (e) { erro = e; }
    return { feitos, tirados, erro, total: tempos.length, pulados: resultado?.pulados || [], deslocados: resultado?.deslocados || [] };
  }

  async function comecarColocar() {
    if (corrida) return;
    const r = retrato(), ctrl = new AbortController();
    if (!r.tempos.length) return;
    recado = { texto: "", tipo: "" };
    corrida = { ctrl, fase: "colocar", total: r.tempos.length, feitos: 0 };
    pintar();
    const fps = ajuste.modo === "pausas" ? await medirFps() : 30; // nos outros modos o tempo é segundo cheio
    const fim = await executar(r.tempos, { trocando: r.trocando, fps, sinal: ctrl.signal, fase: (fase, total, feitos) => { Object.assign(corrida, { fase, total, feitos }); pintar(); } });
    corrida = null;
    recado = fechamento(fim);
    pintar();
  }

  async function comecarTirar(tipo) {
    if (corrida) return;
    const r = retrato(), total = tipo === "vermelhos" ? r.vermelhas : r.total;
    if (!total) return;
    if (tipo === "todos" && !armado) { // segundo toque confirma: apagar todos é um clique errado caro
      armado = setTimeout(() => { armado = 0; pintar(); }, 4000);
      return pintar();
    }
    clearTimeout(armado);
    armado = 0;
    const ctrl = new AbortController();
    corrida = { ctrl, fase: "tirar", total, feitos: 0 };
    recado = { texto: "", tipo: "" };
    pintar();
    let tirados = 0, erro = null;
    try { tirados = await tirar(tipo, ctrl.signal, (k) => { tirados = k; corrida.feitos = k; pintar(); }); }
    catch (e) { erro = e; }
    corrida = null;
    const salvar = tirados ? " Confira e salve no Studio." : "";
    recado = erro === PAROU ? { texto: `Parei: ${plural(tirados, "tirado", "tirados")}.${salvar}`, tipo: "" }
      : erro ? { texto: `${erro.message || erro}${salvar}`, tipo: "erro" }
        : { texto: `${plural(tirados, "anúncio tirado", "anúncios tirados")}.${salvar}`, tipo: "ok" };
    pintar();
  }

  function posicionar() {
    if (!ui || !aberto) return;
    const b = ui.abrir.getBoundingClientRect();
    if (!b.width) return;
    const largura = Math.min(420, innerWidth - 24), topo = b.bottom + 8;
    Object.assign(ui.raiz.style, { left: `${Math.max(12, Math.min(b.left, innerWidth - largura - 12))}px`, top: `${topo}px`, width: `${largura}px`,
      maxHeight: `${Math.max(200, innerHeight - topo - 16)}px` });
  }

  function fecharPainel() { if (aberto) { aberto = false; pintar(); } }
  document.addEventListener("pointerdown", (e) => {
    if (ui && aberto && !corrida && !ui.raiz.contains(e.target) && !ui.abrir.contains(e.target)) fecharPainel();
  }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && ui && aberto) { fecharPainel(); ui.abrir.focus(); } }, true);
  addEventListener("resize", posicionar);
  addEventListener("scroll", posicionar, true);

  // a tela do editor abre e fecha sem trocar de página
  let agendado = false;
  function olhar() {
    agendado = false;
    const cabecalho = $(TELA.cabecalho);
    if (!cabecalho || desligado) {
      corrida?.ctrl.abort();
      if (ui?.raiz.isConnected) { aberto = false; ui.raiz.remove(); ui.ancora.remove(); }
      return;
    }
    ui ||= montar();
    if (!ui.raiz.isConnected) document.body.append(ui.raiz);
    if (ui.ancora.nextElementSibling !== cabecalho) cabecalho.before(ui.ancora);
    if (aberto) { pintar(); posicionar(); } // a agulha mexe na tela a cada quadro: fechado, não há o que atualizar
  }
  const agendar = () => { if (!agendado && !document.hidden) { agendado = true; requestAnimationFrame(olhar); } };
  new MutationObserver(agendar).observe(document.body, { childList: true, subtree: true, characterData: true });
  document.addEventListener("visibilitychange", agendar);
  agendar();

  // ------------------------------------------------------------ o botão de um aperto só do publicar.js

  Object.assign(globalThis.RadarAnuncios, {
    duracao,
    pronto: () => !!$(TELA.inserir),
    // apaga o que o Studio pôs sozinho e coloca os tempos pedidos. Devolve { feitos, pulados, deslocados, tirados, erro }
    colocar: (tempos, aoAndar = () => {}) => executar(tempos, { trocando: linhas().length > 0, sinal: new AbortController().signal, fase: aoAndar }),
  });
})();
