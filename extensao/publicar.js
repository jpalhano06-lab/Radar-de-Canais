// A ajuda para publicar no YouTube Studio (pedido do usuário em 2026-10-20: "adicionar a extensão na hora de postar o
// vídeo com anúncios e tudo"; escolhido "só um painel de ajuda"). Na tela de upload (ou de edição) do vídeo aparece um
// painel com o título, a descrição e as tags que a fábrica montou, prontos para copiar, e a lista do que marcar:
// detalhes, monetização e anúncios, questionário de anunciantes, elementos, verificações e visibilidade.
// Não clica, não preenche e não publica nada: quem marca e aperta Publicar é a pessoa.
// O vídeo do Radar é achado pelo nome do arquivo que está subindo (a entrega da fábrica usa o título como nome).
(() => {
  if (window.__radarPublicar) return;
  window.__radarPublicar = true;

  const pedir = (msg) => new Promise((ok) => {
    try {
      chrome.runtime.sendMessage(msg, (r) => ok(r || { erro: "A extensão foi atualizada: recarregue esta página (F5)." }));
    } catch {
      ok({ erro: "A extensão foi atualizada: recarregue esta página (F5)." });
    }
  });

  const EXTENSOES = /\.(mp4|mov|mkv|webm|avi|m4v|wmv|flv|mpe?g)$/i;
  const estado = { arquivo: "", kit: null, opcoes: [], erro: "", carregando: false, aberto: false, feitos: {}, buscado: "" };

  // ------------------------------------------------------------ o nome do arquivo que está subindo
  function novoArquivo(nome) {
    if (!nome || !EXTENSOES.test(nome) || nome === estado.arquivo) return;
    estado.arquivo = nome;
    estado.aberto = true;
    buscar(nome);
  }
  // o seletor de arquivo do Studio e o arrastar-e-soltar
  document.addEventListener("change", (e) => { const f = e.target && e.target.files && e.target.files[0]; if (f) novoArquivo(f.name); }, true);
  document.addEventListener("drop", (e) => { const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]; if (f) novoArquivo(f.name); }, true);

  // reserva: o nome que o Studio mostra ("Nome do arquivo" na tela de upload e na de edição)
  function arquivoDaTela() {
    const onde = document.querySelector("ytcp-uploads-dialog") || document.querySelector("ytcp-app") || document.body;
    for (const el of onde.querySelectorAll("div, span, a, yt-formatted-string")) {
      if (el.children.length) continue;
      const t = (el.textContent || "").trim();
      if (t.length < 200 && EXTENSOES.test(t)) return t;
    }
    return "";
  }

  // ------------------------------------------------------------ quando aparece
  function telaDePublicar() {
    if (/\/video\/[\w-]{11}\/(edit|monetization)/.test(location.pathname)) return true;
    if (/[?&]d=ud\b/.test(location.search) || /\/videos\/upload/.test(location.pathname)) return true;
    const d = document.querySelector("ytcp-uploads-dialog");
    return !!(d && [...d.querySelectorAll("tp-yt-paper-dialog")].some((x) => x.offsetWidth > 0));
  }

  // ------------------------------------------------------------ o Radar
  async function buscar(arquivo) {
    estado.carregando = true; estado.erro = ""; estado.buscado = arquivo;
    desenhar();
    const r = await pedir({ tipo: "api", caminho: `/api/ext/publicar?arquivo=${encodeURIComponent(arquivo || "")}` });
    estado.carregando = false;
    if (r.erro) estado.erro = r.status === 401 ? "Entre na sua conta do Radar pelo ícone da extensão." : r.erro;
    else { estado.kit = r.dados.kit; estado.opcoes = r.dados.opcoes || []; estado.feitos = {}; }
    desenhar();
  }

  async function escolher(nome) {
    if (!nome) return;
    estado.carregando = true; estado.erro = "";
    desenhar();
    const r = await pedir({ tipo: "api", caminho: `/api/ext/publicar/${encodeURIComponent(nome)}` });
    estado.carregando = false;
    if (r.erro) estado.erro = r.erro; else { estado.kit = r.dados; estado.feitos = {}; }
    desenhar();
  }

  async function baixarLegenda(botao) {
    botao.disabled = true; botao.textContent = "Baixando…";
    const r = await pedir({ tipo: "binario", caminho: `/api/ext/publicar/${encodeURIComponent(estado.kit.nome)}/legenda` });
    botao.disabled = false; botao.textContent = "Baixar a legenda (.srt)";
    if (r.erro) return avisar(r.erro, true);
    const bytes = Uint8Array.from(atob(r.base64), (c) => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/x-subrip" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `${estado.kit.nome}.srt` });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }

  // ------------------------------------------------------------ o painel (num shadow root, o CSS do Studio não entra)
  const host = document.createElement("div");
  host.id = "radar-publicar";
  const raiz = host.attachShadow({ mode: "open" });
  raiz.innerHTML = `<style>
    :host { all: initial; }
    * { box-sizing: border-box; }
    .lancador { position: fixed; right: 18px; bottom: 18px; z-index: 2147483646; border: 0; border-radius: 999px; padding: 10px 16px;
      background: #b6f23a; color: #10160a; font: 700 13px Roboto, Arial, sans-serif; cursor: pointer; box-shadow: 0 6px 20px rgba(0,0,0,.35); }
    .painel { position: fixed; right: 16px; top: 72px; bottom: 16px; width: 380px; z-index: 2147483647; display: flex; flex-direction: column;
      background: #0d0f14; color: #eef1f7; border: 1px solid #262b36; border-radius: 14px; box-shadow: 0 12px 40px rgba(0,0,0,.45);
      font: 13px/1.45 Roboto, Arial, sans-serif; overflow: hidden; }
    .cab { display: flex; align-items: center; gap: 8px; padding: 12px 14px; border-bottom: 1px solid #262b36; }
    .cab i { width: 10px; height: 10px; border-radius: 50%; background: #b6f23a; box-shadow: 0 0 8px #b6f23a; flex: none; }
    .cab b { flex: 1; font-size: 14px; }
    .corpo { overflow-y: auto; padding: 12px 14px 18px; display: grid; gap: 12px; }
    .x { border: 0; background: transparent; color: #8d95a8; font-size: 18px; cursor: pointer; line-height: 1; }
    .fraco { color: #8d95a8; font-size: 12px; }
    .erro { color: #ff5263; font-size: 12px; }
    .aviso { background: #2a2210; border: 1px solid #5a4716; color: #ffd98a; border-radius: 10px; padding: 8px 10px; font-size: 12px; }
    .caixa { background: #151820; border: 1px solid #262b36; border-radius: 10px; padding: 10px; display: grid; gap: 6px; }
    .campo-cab { display: flex; align-items: center; gap: 8px; }
    .campo-cab b { flex: 1; }
    .conta { font-size: 11px; color: #8d95a8; }
    .conta.passou { color: #ff5263; font-weight: 700; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; font: 12px/1.45 Roboto, Arial, sans-serif; color: #cfd5e2;
      max-height: 120px; overflow-y: auto; background: #0d0f14; border-radius: 8px; padding: 6px 8px; }
    button.b { border: 0; border-radius: 999px; padding: 5px 11px; cursor: pointer; font: 600 12px Roboto, Arial, sans-serif;
      background: #1c2029; color: #eef1f7; border: 1px solid #2f3542; }
    button.b:hover { background: #262b36; }
    button.b.forte { background: #b6f23a; color: #10160a; border-color: #b6f23a; }
    button.b.copiado { background: #1f3a12; border-color: #3d6b1f; color: #b6f23a; }
    select, input { width: 100%; background: #1c2029; color: #eef1f7; border: 1px solid #262b36; border-radius: 8px; padding: 7px 8px; font: 13px Roboto, Arial, sans-serif; }
    .linha { display: flex; gap: 6px; }
    details { background: #151820; border: 1px solid #262b36; border-radius: 10px; }
    summary { cursor: pointer; padding: 9px 10px; font-weight: 700; display: flex; gap: 8px; align-items: center; list-style: none; }
    summary::-webkit-details-marker { display: none; }
    summary::before { content: "▸"; color: #8d95a8; }
    details[open] summary::before { content: "▾"; }
    summary span { margin-left: auto; font-weight: 500; font-size: 11px; color: #8d95a8; }
    summary span.tudo { color: #b6f23a; }
    .itens { padding: 0 10px 10px; display: grid; gap: 7px; }
    label.item { display: grid; grid-template-columns: 18px 1fr; gap: 6px; align-items: start; cursor: pointer; }
    label.item input { width: 15px; height: 15px; margin: 2px 0 0; accent-color: #b6f23a; }
    label.item.feito > span { color: #8d95a8; text-decoration: line-through; }
    .item small { display: block; color: #8d95a8; font-size: 11.5px; text-decoration: none; }
    .titulo-video { font-weight: 700; }
  </style><button class="lancador" hidden>Radar · ajuda para publicar</button><div class="painel" hidden></div>`;
  const lancador = raiz.querySelector(".lancador");
  const painel = raiz.querySelector(".painel");
  lancador.onclick = () => {
    estado.aberto = true;
    if (!estado.kit && !estado.carregando && !estado.opcoes.length) buscar(estado.arquivo || arquivoDaTela());
    desenhar();
  };

  function el(tag, props = {}, ...filhos) {
    const e = Object.assign(document.createElement(tag), props);
    for (const f of filhos.flat()) if (f != null && f !== false) e.append(f);
    return e;
  }

  function avisar(texto, erro = false) {
    const a = el("div", { className: erro ? "erro" : "fraco", textContent: texto });
    painel.querySelector(".corpo")?.prepend(a);
    setTimeout(() => a.remove(), 6000);
  }

  async function copiar(texto, botao) {
    try {
      await navigator.clipboard.writeText(texto);
    } catch {
      const t = el("textarea", { value: texto });
      raiz.append(t); t.select(); document.execCommand("copy"); t.remove();
    }
    const antes = botao.textContent;
    botao.textContent = "Copiado ✓"; botao.classList.add("copiado");
    setTimeout(() => { botao.textContent = antes; botao.classList.remove("copiado"); }, 1600);
  }

  // um campo para copiar, com a contagem do limite do Studio
  function campo(rotulo, texto, limite, extra) {
    if (!texto) return null;
    const passou = limite && texto.length > limite;
    const botao = el("button", { className: "b forte", textContent: "Copiar" });
    botao.onclick = () => copiar(texto, botao);
    return el("div", { className: "caixa" },
      el("div", { className: "campo-cab" }, el("b", { textContent: rotulo }),
        limite ? el("span", { className: "conta" + (passou ? " passou" : ""), textContent: `${texto.length}/${limite}` }) : null, botao),
      el("pre", { textContent: texto }),
      passou ? el("div", { className: "erro", textContent: `Passa do limite do Studio (${limite} caracteres): corte antes de salvar.` }) : null,
      extra || null);
  }

  // as tags no formato de colar (o Studio separa nas vírgulas) até caber nos 500 caracteres
  function tagsQueCabem(tags) {
    const saida = [];
    for (const t of tags) {
      const proximo = [...saida, t].join(", ");
      if (proximo.length > 500) break;
      saida.push(t);
    }
    return saida;
  }

  // ------------------------------------------------------------ o que marcar, na ordem das etapas do Studio
  function etapas(k) {
    const min = k && k.duracao ? k.duracao / 60 : null;
    const capitulos = (k && k.capitulos || []).filter((c) => c.inicio > 0).map((c) => c.tempo).join(", ");
    const midroll = min == null
      ? { t: "Anúncios durante o vídeo (mid-roll)", d: "Só aparece em vídeos de 8 minutos ou mais. Deixe ligado e escolha \"Posicionar automaticamente\" (ou coloque nos começos de capítulo)." }
      : min >= 8
        ? { t: "Anúncios durante o vídeo (mid-roll): ligado", d: `O vídeo tem ${Math.floor(min)} min. Use "Posicionar automaticamente"${capitulos ? ` ou ponha nas viradas de capítulo: ${capitulos}` : ""}.` }
        : { t: "Sem anúncio no meio", d: `O vídeo tem ${Math.floor(min)} min: o mid-roll só existe a partir de 8 minutos.` };
    return [
      { id: "detalhes", nome: "1. Detalhes", itens: [
        { t: "Título e descrição", d: "Cole os textos lá de cima (a descrição já traz os capítulos)." },
        { t: "Thumbnail", d: "Envie a thumbnail.jpg que está na pasta da entrega." },
        { t: "Playlist", d: "Escolha a playlist do assunto, se tiver." },
        { t: "Público: \"Não, não é conteúdo para crianças\"", d: "Conteúdo para crianças desliga os anúncios personalizados e os comentários." },
        k ? { t: `Conteúdo alterado ou sintético: ${k.sintetico ? "Sim" : "Não"}`, d: k.sintetico ? "O vídeo tem imagens feitas por IA que parecem reais: marque Sim (o YouTube pede)." : "A fábrica não marcou imagens de IA realistas neste vídeo." }
          : { t: "Conteúdo alterado ou sintético", d: "Marque Sim se o vídeo tem imagens de IA que parecem reais." },
        { t: "Mostrar mais → Tags", d: "Cole as tags lá de cima (separadas por vírgula, o Studio separa sozinho)." },
        { t: "Mostrar mais → Idioma do vídeo e categoria", d: "O idioma da narração; categoria do canal (ex.: Educação)." },
      ] },
      { id: "monetizacao", nome: "2. Monetização e anúncios", itens: [
        { t: "Monetização: Ativada", d: "Abra a monetização, escolha Ativada e clique em Concluído." },
        { t: "Tipos de anúncio: todos marcados", d: "Antes do vídeo, anúncios puláveis e não puláveis e depois do vídeo." },
        midroll,
      ] },
      { id: "anunciantes", nome: "3. Adequação para anunciantes", itens: [
        { t: "Responda o questionário com sinceridade", d: "Para cada tema (linguagem, violência, conteúdo adulto, drogas, armas, assuntos polêmicos…), veja se o vídeo mostra aquilo." },
        { t: "\"Nenhuma das opções acima\" só se for verdade", d: "Quando o vídeo não tem nada daquilo. Classificar errado faz o YouTube deixar de confiar nas suas respostas." },
        { t: "Enviar a classificação", d: "Clique em Enviar classificação no fim do questionário." },
      ] },
      { id: "elementos", nome: "4. Elementos do vídeo", itens: [
        { t: "Legendas", d: k && k.legenda ? "Envie o .srt (botão \"Baixar a legenda\" lá em cima) → Enviar arquivo → Com tempo." : "Se tiver o .srt do vídeo, envie com tempo." },
        { t: "Tela final", d: "\"Importar do vídeo\" reaproveita a de um vídeo anterior (vídeo + inscrever-se)." },
        { t: "Cards", d: "Opcional: um card para um vídeo do mesmo assunto." },
      ] },
      { id: "verificacoes", nome: "5. Verificações", itens: [
        { t: "Esperar a verificação de direitos autorais", d: "Se aparecer reivindicação, veja antes de publicar." },
      ] },
      { id: "visibilidade", nome: "6. Visibilidade", itens: [
        { t: "Privado, Não listado, Público ou Agendar", d: "Para agendar, escolha a data e a hora. A Estreia é opcional." },
        { t: "Você clica em Publicar / Agendar", d: "A extensão não publica nada sozinha." },
        { t: "Depois de publicar: fixar o comentário", d: "Comente o texto do \"Comentário fixado\" e fixe no topo." },
      ] },
    ];
  }

  function lista(k) {
    return etapas(k).map((etapa, i) => {
      const feitos = etapa.itens.filter((_, j) => estado.feitos[`${etapa.id}-${j}`]).length;
      const contagem = el("span", { className: feitos === etapa.itens.length ? "tudo" : "", textContent: `${feitos}/${etapa.itens.length}` });
      const d = el("details", { open: estado[`aberta-${etapa.id}`] ?? i === 0 },
        el("summary", {}, etapa.nome, contagem),
        el("div", { className: "itens" }, etapa.itens.map((item, j) => {
          const chave = `${etapa.id}-${j}`;
          const caixa = el("input", { type: "checkbox", checked: !!estado.feitos[chave] });
          const linha = el("label", { className: "item" + (estado.feitos[chave] ? " feito" : "") }, caixa,
            el("span", {}, item.t, el("small", { textContent: item.d })));
          caixa.onchange = () => { estado.feitos[chave] = caixa.checked; desenhar(); };
          return linha;
        })));
      d.addEventListener("toggle", () => { estado[`aberta-${etapa.id}`] = d.open; });
      return d;
    });
  }

  function escolha() {
    const sel = el("select", {}, el("option", { value: "", textContent: estado.opcoes.length ? "Escolha o vídeo da fábrica…" : "Nenhum vídeo da fábrica com descrição pronta" }),
      estado.opcoes.map((o) => el("option", { value: o.nome, textContent: o.titulo, selected: estado.kit && estado.kit.nome === o.nome })));
    sel.onchange = () => escolher(sel.value);
    const nome = el("input", { placeholder: "ou digite o nome do arquivo", value: estado.buscado || "" });
    const ir = el("button", { className: "b", textContent: "Buscar" });
    ir.onclick = () => buscar(nome.value.trim());
    nome.onkeydown = (e) => { if (e.key === "Enter") ir.click(); };
    return [sel, el("div", { className: "linha" }, nome, ir)];
  }

  function desenhar() {
    const mostrar = telaDePublicar() || estado.aberto;
    lancador.hidden = !mostrar || estado.aberto;
    painel.hidden = !estado.aberto;
    if (!estado.aberto) return;
    const k = estado.kit;
    const rolagem = painel.querySelector(".corpo")?.scrollTop || 0;
    const fechar = el("button", { className: "x", title: "Fechar", textContent: "×" });
    fechar.onclick = () => { estado.aberto = false; desenhar(); };

    const video = el("div", { className: "caixa" },
      estado.arquivo ? el("div", { className: "fraco", textContent: `Arquivo: ${estado.arquivo}` }) : null,
      estado.carregando ? el("div", { className: "fraco", textContent: "Procurando no Radar…" })
        : k ? el("div", { className: "titulo-video", textContent: `✓ ${k.titulo}` })
          : el("div", { className: "fraco", textContent: estado.arquivo ? "Não achei este arquivo entre os vídeos da fábrica. Escolha qual é:" : "Escolha o vídeo da fábrica (ou suba o arquivo que eu acho sozinho):" }),
      estado.erro ? el("div", { className: "erro", textContent: estado.erro }) : null,
      estado.carregando ? null : escolha());

    const textos = [];
    if (k) {
      const tags = tagsQueCabem(k.tags || []);
      const tagsTexto = tags.join(", ");
      const descricao = k.descricao || "";
      const faltamHashtags = (k.hashtags || []).filter((h) => !descricao.includes(h));
      textos.push(
        campo("Título", k.titulo, 100),
        (k.titulos_alt || []).length ? el("div", { className: "caixa" }, el("b", { textContent: "Títulos para o teste A/B" }),
          el("div", { className: "fraco", textContent: "Em \"Testar e comparar\", junto com o título principal." }),
          k.titulos_alt.map((t) => { const b = el("button", { className: "b", textContent: "Copiar" }); b.onclick = () => copiar(t, b);
            return el("div", { className: "campo-cab" }, el("span", { textContent: t, style: "flex:1" }), b); })) : null,
        campo("Descrição", descricao, 5000),
        faltamHashtags.length ? campo("Hashtags (no fim da descrição)", faltamHashtags.join(" "), 0) : null,
        campo("Tags", tagsTexto, 500, tags.length < (k.tags || []).length
          ? el("div", { className: "fraco", textContent: `Ficaram ${tags.length} de ${k.tags.length} tags para caber nos 500 caracteres.` }) : null),
        campo("Comentário fixado (depois de publicar)", k.comentario_fixado, 0));
      if (k.legenda) {
        const b = el("button", { className: "b", textContent: "Baixar a legenda (.srt)" });
        b.onclick = () => baixarLegenda(b);
        textos.push(el("div", { className: "caixa" }, el("b", { textContent: "Legenda" }), el("div", { className: "linha" }, b)));
      }
    }

    painel.replaceChildren(
      el("div", { className: "cab" }, el("i"), el("b", { textContent: "Radar · ajuda para publicar" }), fechar),
      el("div", { className: "corpo" },
        el("div", { className: "aviso", textContent: "Só ajuda: copie os textos e vá marcando. Nada é clicado ou publicado pela extensão." }),
        video, textos, el("b", { textContent: "O que marcar em cada etapa" }), lista(k)));
    painel.querySelector(".corpo").scrollTop = rolagem;
  }

  (document.body || document.documentElement).append(host);
  // o Studio troca de tela sem recarregar: confere a cada segundo se é a tela de publicar e se apareceu o nome do arquivo
  let ultimo = "", ultimoVideo = "";
  setInterval(() => {
    // outro vídeo aberto para editar: o arquivo e o kit eram do anterior
    const video = (location.pathname.match(/\/video\/([\w-]{11})/) || location.search.match(/[?&]udvid=([\w-]{11})/) || [])[1] || "";
    if (video && ultimoVideo && video !== ultimoVideo) { estado.arquivo = ""; estado.kit = null; estado.buscado = ""; estado.feitos = {}; desenhar(); }
    if (video) ultimoVideo = video;
    const agora = telaDePublicar();
    if (agora && !estado.arquivo) {
      const nome = arquivoDaTela();
      if (nome) novoArquivo(nome);
    }
    const marca = `${agora}|${estado.aberto}`;
    if (marca !== ultimo) { ultimo = marca; desenhar(); }
  }, 1000);
})();
