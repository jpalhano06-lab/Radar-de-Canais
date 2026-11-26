// A aba "Canais de teste" na beirada direita do YouTube e do Studio, embaixo do Meu dia (pedido do usuário em
// 2026-11-25). O Radar não posta mais nos canais de teste: quem posta é a pessoa. Por canal, como a faixa dos dias
// do Meu dia: em cima os canais, embaixo os 3 vídeos do canal aberto, cada um com o dia de postar. Vermelho no dia de
// postar (e depois, se não saiu), azul antes da hora, verde postado. O Postar abre o Studio do canal com o vídeo;
// o "Avaliar métricas" abre as métricas dele. Assim o Radar não precisa do login do Google.
(() => {
  if (window.__radarCanaisTeste) return;
  window.__radarCanaisTeste = true;

  const pedir = (msg) => new Promise((ok) => {
    try { chrome.runtime.sendMessage(msg, (r) => ok(r || { erro: "A extensão foi atualizada: recarregue a página (F5)." })); }
    catch { ok({ erro: "A extensão foi atualizada: recarregue a página (F5)." }); }
  });
  const el = (tag, props = {}, filhos = []) => {
    const e = Object.assign(document.createElement(tag), props);
    for (const f of [].concat(filhos)) if (f != null) e.append(f);
    return e;
  };
  const isoLocal = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  function quandoPostar(iso) {
    const hoje = new Date();
    const amanha = new Date(hoje); amanha.setDate(hoje.getDate() + 1);
    const d = new Date(iso);
    const hora = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    const dia = iso.slice(0, 10) === isoLocal(hoje) ? "hoje" : iso.slice(0, 10) === isoLocal(amanha) ? "amanhã"
      : d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
    return `${dia} às ${hora}`;
  }

  let canais = [], paraPostar = 0, erro = "", painel = null, aberto = "";
  let linguas = [], linguaPadrao = "", adicionando = false, preencher = "";
  // os canais da conta do YouTube que ainda não tiveram teste (2026-11-26): a lista vem do menu do avatar, que o
  // content.js lê e guarda em contasYoutube ("Ler as contas"); o Radar manda todos os canais que já tiveram teste
  let testados = [], contas = [], verSemTeste = false;
  const solto = (t) => { try { return decodeURIComponent(t); } catch { return t; } };   // o @ vem às vezes como %C3%A3
  const normal = (t) => solto(String(t || "")).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
  async function lerContas() {
    try { ({ contasYoutube: contas = [] } = await chrome.storage.local.get("contasYoutube")); } catch { contas = []; }
  }
  try {
    chrome.storage.onChanged.addListener((mudou, area) => {
      if (area === "local" && mudou.contasYoutube) { contas = mudou.contasYoutube.newValue || []; if (painel?.classList.contains("aberto")) desenhar(); }
    });
  } catch { /* extensão recarregada */ }
  lerContas();
  function semTeste() {
    const nomes = new Set(testados.map((t) => normal(t.nome)));
    const handles = new Set(testados.map((t) => normal(t.handle)).filter(Boolean));
    const vistos = new Set();
    return contas.filter((c) => {
      const chave = normal(c.handle) || normal(c.nome);
      if (!chave || vistos.has(chave)) return false;
      vistos.add(chave);
      return !(c.handle && handles.has(normal(c.handle))) && !nomes.has(normal(c.nome));
    });
  }
  try { aberto = localStorage.getItem("radar-teste-aberto") || ""; } catch { /* sem localStorage */ }
  const abinha = el("button", { className: "radar-teste-abinha", textContent: "Canais de teste", title: "Os canais em teste do Radar" });
  abinha.onclick = () => alternar(true);
  document.body.append(abinha);

  function alternar(abrir) {
    if (!painel) {
      painel = el("div", { className: "radar-teste-painel" });
      document.body.append(painel);
    }
    const ver = abrir ?? !painel.classList.contains("aberto");
    painel.classList.toggle("aberto", ver);
    abinha.classList.toggle("escondida", ver);
    if (ver) { desenhar(); carregar(); }
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && painel?.classList.contains("aberto")) alternar(false); });

  function aplicar(r) {
    erro = r.erro || "";
    if (r.dados) {
      canais = r.dados.canais || []; paraPostar = r.dados.para_postar || 0;
      if (r.dados.linguas) { linguas = r.dados.linguas; linguaPadrao = r.dados.lingua_padrao || ""; }
      if (r.dados.testados) testados = r.dados.testados;
    }
    abinha.classList.toggle("vermelha", paraPostar > 0);
    abinha.textContent = paraPostar ? `Canais de teste · ${paraPostar} para postar` : "Canais de teste";
    abinha.title = paraPostar ? `${paraPostar} ${paraPostar === 1 ? "vídeo para postar" : "vídeos para postar"} hoje` : "Os canais em teste do Radar";
    if (painel?.classList.contains("aberto")) desenhar();
  }

  async function carregar() {
    aplicar(await pedir({ tipo: "api", caminho: "/api/ext/teste/canais" }));
  }

  function abrir(canalId) {
    aberto = canalId;
    try { localStorage.setItem("radar-teste-aberto", canalId); } catch { /* sem localStorage */ }
    desenhar();
  }

  function cartaoDoVideo(c, v) {
    const aviso = v.cor === "verde" ? "Postado"
      : !v.quando ? "Ainda sem dia: o vídeo está sendo feito"
      : c.sozinho ? (v.cor === "vermelho" ? `O Radar publica ${quandoPostar(v.quando)}` : `Ainda não é a hora · o Radar publica ${quandoPostar(v.quando)}`)
      : v.cor === "vermelho" ? `Postar ${quandoPostar(v.quando)}` : `Ainda não é a hora · postar ${quandoPostar(v.quando)}`;
    const botoes = [];
    if (v.cor === "verde" && v.url) botoes.push(el("a", { className: "radar-teste-botao", textContent: "Ver", href: v.url, target: "_blank", rel: "noreferrer" }));
    if (v.cor !== "verde" && v.quando) {
      const postar = el("button", { className: `radar-teste-botao ${v.cor === "vermelho" ? "forte-vermelho" : ""}`, textContent: "Postar",
        disabled: !v.id, title: v.id ? "Abre o Studio do canal com este vídeo" : "O vídeo ainda está sendo feito" });
      postar.onclick = async () => {
        postar.disabled = true; postar.textContent = "Abrindo o Studio…";
        const r = await pedir({ tipo: "teste-postar", testeId: v.id });
        if (r.erro) { erro = `Não consegui abrir o Studio de ${c.nome}: ${r.erro}`; desenhar(); }
        else setTimeout(desenhar, 1500);
      };
      botoes.push(postar);
    }
    return el("div", { className: `radar-teste-video ${v.cor}` }, [
      el("div", { className: "radar-teste-video-texto" }, [
        el("small", { textContent: `Vídeo ${v.numero}` }),
        el("b", { textContent: v.tema, title: v.tema }),
        el("span", { className: "radar-teste-aviso", textContent: aviso }),
        // as views que o Radar mede de hora em hora (2026-11-26): a métrica do vídeo sem abrir o Studio
        v.views != null ? el("small", { className: "radar-teste-views", textContent: `${Number(v.views).toLocaleString("pt-BR")} ${v.views === 1 ? "view" : "views"}` }) : null]),
      botoes.length ? el("div", { className: "radar-teste-acoes" }, botoes) : null]);
  }

  // o @ do canal que está aberto no YouTube (youtube.com/@canal), para o "Adicionar canal" já vir preenchido
  const arrobaDaPagina = () => (location.hostname === "www.youtube.com" && (location.pathname.match(/^\/(@[^/]+)/) || [])[1]) || "";

  // adicionar um canal ao teste pela aba (2026-11-26): o mesmo "Começar o teste" do Radar, com o @ e a língua
  function formAdicionar() {
    const arroba = el("input", { className: "radar-teste-campo", placeholder: "@meucanal", value: preencher || decodeURIComponent(arrobaDaPagina()) });
    preencher = "";
    const lingua = el("select", { className: "radar-teste-campo" }, linguas.map((l) =>
      el("option", { value: l, textContent: l, selected: l === linguaPadrao })));
    const origem = el("select", { className: "radar-teste-campo" }, [
      el("option", { value: "radar", textContent: "Vídeos criados pelo Radar" }),
      el("option", { value: "banco", textContent: "Vídeos do meu banco" })]);
    const comecar = el("button", { className: "radar-teste-botao forte", textContent: "Começar o teste" });
    const cancelar = el("button", { className: "radar-teste-botao", textContent: "Cancelar", onclick: () => { adicionando = false; desenhar(); } });
    comecar.onclick = async () => {
      const valor = arroba.value.trim();
      if (!valor) { arroba.focus(); return; }
      comecar.disabled = true; comecar.textContent = "Começando…";
      const r = await pedir({ tipo: "api", caminho: "/api/teste", metodo: "POST",
        corpo: { arroba: valor, lingua: lingua.value, origem: origem.value } });
      if (r.erro) { erro = `Não consegui começar o teste: ${r.erro}`; comecar.disabled = false; comecar.textContent = "Começar o teste"; desenhar(); return; }
      erro = ""; adicionando = false;
      if (r.dados?.canal_id) abrir(r.dados.canal_id);
      await carregar();
      pedir({ tipo: "teste-sincronizar" });
    };
    const form = el("div", { className: "radar-teste-aberto radar-teste-adicionar" }, [
      el("b", { textContent: "Adicionar canal ao teste" }),
      el("label", {}, [el("span", { textContent: "@ do canal" }), arroba]),
      el("label", {}, [el("span", { textContent: "Língua do título" }), lingua]),
      el("label", {}, [el("span", { textContent: "De onde vêm os vídeos" }), origem]),
      el("div", { className: "radar-teste-linha" }, [cancelar, comecar]),
      el("p", { className: "radar-teste-fraco", textContent: "Quem posta é você. Achar o canal pelo @ gasta 1 da cota do YouTube." })]);
    setTimeout(() => arroba.focus(), 0);
    return form;
  }

  function listaSemTeste() {
    const faltam = semTeste();
    const ler = el("button", { className: "radar-teste-botao", textContent: contas.length ? "Ler de novo" : "Ler as contas",
      title: "Abre o YouTube e lê os canais do menu do avatar",
      onclick: () => window.open("https://www.youtube.com/#radar-contas-ler", "_blank") });
    const cab = el("button", { className: "radar-teste-semteste-cab",
      textContent: !contas.length ? "Canais sem teste: ler as contas do YouTube"
        : `Canais sem teste (${faltam.length} de ${contas.length})`,
      onclick: () => { verSemTeste = !verSemTeste; desenhar(); } });
    const caixa = el("div", { className: "radar-teste-semteste" }, [el("div", { className: "radar-teste-linha" }, [cab, ler])]);
    if (!verSemTeste) return caixa;
    if (!contas.length) {
      caixa.append(el("p", { className: "radar-teste-fraco", textContent: "Clique em Ler as contas: o YouTube abre, a extensão lê os canais do menu do avatar e a lista aparece aqui." }));
      return caixa;
    }
    if (!faltam.length) caixa.append(el("p", { className: "radar-teste-fraco", textContent: "Todos os canais da conta já tiveram teste." }));
    for (const c of faltam) {
      const testar = el("button", { className: "radar-teste-botao", textContent: "Testar", disabled: !c.handle,
        title: c.handle ? `Começar o teste de ${c.handle}` : "Sem o @ deste canal: abra o canal no YouTube e use Adicionar canal",
        onclick: () => { preencher = c.handle; adicionando = true; desenhar(); } });
      caixa.append(el("div", { className: "radar-teste-conta" }, [
        el("div", { className: "radar-teste-video-texto" }, [
          el("b", { textContent: c.nome, title: c.nome }),
          el("small", { textContent: [c.handle, c.email].filter(Boolean).join(" · ") })]),
        testar]));
    }
    return caixa;
  }

  function desenhar() {
    painel.replaceChildren();
    const fechar = el("button", { className: "radar-teste-fechar", textContent: "×", title: "Fechar (Esc)", onclick: () => alternar(false) });
    const adicionar = el("button", { className: "radar-teste-botao", textContent: "Adicionar canal", title: "Começar o teste de um canal",
      disabled: adicionando, onclick: () => { adicionando = true; desenhar(); } });
    painel.append(el("div", { className: "radar-teste-cab" }, [el("b", { textContent: "Canais de teste" }),
      el("div", { className: "radar-teste-cab-acoes" }, [adicionar, fechar])]));
    const corpo = el("div", { className: "radar-teste-corpo" });
    painel.append(corpo);
    if (erro) corpo.append(el("p", { className: "radar-teste-erro", textContent: erro }));
    if (adicionando) corpo.append(formAdicionar());
    corpo.append(listaSemTeste());
    if (!canais.length) {
      if (!erro) corpo.append(el("p", { className: "radar-teste-fraco", textContent: "Nenhum canal em teste. Comece um no Radar, em Canal de teste." }));
      return;
    }
    // primeiro quem tem vídeo para postar; aberto, o escolhido (ou o primeiro)
    const ordem = [...canais].sort((a, b) => b.para_postar - a.para_postar);
    const canal = ordem.find((c) => c.canal_id === aberto) || ordem[0];
    corpo.append(el("div", { className: "radar-teste-faixa" }, ordem.map((c) => el("button", {
      className: `radar-teste-chip ${c.para_postar ? "vermelho" : c.postados === c.videos.length ? "verde" : ""} ${c === canal ? "aberto" : ""}`,
      onclick: () => abrir(c.canal_id), title: c.nome }, [
      el("b", { textContent: c.nome }),
      el("span", { textContent: c.para_postar ? `${c.para_postar} para postar` : `${c.postados} de ${c.videos.length} postados` })]))));
    corpo.append(el("div", { className: "radar-teste-aberto" }, [
      el("div", { className: "radar-teste-linha" }, [
        el("b", { textContent: canal.nome }),
        // o postar sozinho do canal (2026-11-25): ligado, a extensão publica cada vídeo no dia e na hora, sem agendar
        el("button", { className: `radar-teste-sozinho ${canal.sozinho ? "ligado" : ""}`,
          textContent: canal.sozinho ? "Postar sozinho: ligado" : "Postar sozinho: desligado",
          title: canal.sozinho ? "O Radar publica cada vídeo no dia e na hora marcados (deixe o Chrome aberto). Clique para desligar."
            : "Ligue para o Radar publicar cada vídeo no dia e na hora marcados, sem agendar",
          onclick: async (e) => {
            e.currentTarget.disabled = true;
            aplicar(await pedir({ tipo: "api", caminho: "/api/ext/teste/sozinho", metodo: "POST", corpo: { canal_id: canal.canal_id, ligado: !canal.sozinho } }));
            pedir({ tipo: "teste-sincronizar" });
          } }),
        el("button", { className: `radar-teste-botao ${canal.avaliar_hoje ? "forte" : ""}`, textContent: "Avaliar métricas",
          title: "Abre as métricas do canal no Studio",
          onclick: async () => {
            // o erro aparece na aba (2026-11-26: com a página velha, depois de recarregar a extensão, falhava calado)
            const r = await pedir({ tipo: "abrir-canal-studio", canalId: canal.canal_id, canalNome: canal.nome, onde: "analytics" });
            if (r.erro) { erro = `Não consegui abrir as métricas de ${canal.nome}: ${r.erro}`; desenhar(); return; }
            aplicar(await pedir({ tipo: "api", caminho: "/api/ext/teste/olhou", metodo: "POST", corpo: { canal_id: canal.canal_id } }));
          } })]),
      // avaliar o canal e parar o teste pela aba (2026-11-26): o mesmo bom/ruim e o "Não testar" do Radar
      el("div", { className: "radar-teste-linha radar-teste-avaliar" }, [
        el("span", { className: "radar-teste-fraco", textContent: "O canal é:" }),
        ...[["bom", "Bom"], ["ruim", "Ruim"]].map(([valor, rotulo]) => el("button", {
          className: `radar-teste-botao ${canal.avaliacao === valor ? (valor === "bom" ? "marcado" : "marcado-ruim") : ""}`,
          textContent: rotulo, title: canal.avaliacao === valor ? "Clique de novo para tirar a avaliação" : `Marcar o canal como ${rotulo.toLowerCase()}`,
          onclick: async (e) => {
            e.currentTarget.disabled = true;
            aplicar(await pedir({ tipo: "api", caminho: "/api/ext/teste/avaliacao", metodo: "POST",
              corpo: { canal_id: canal.canal_id, avaliacao: canal.avaliacao === valor ? "" : valor } }));
          } })),
        el("button", { className: "radar-teste-botao parar", textContent: "Parar teste",
          title: "Tira o canal do teste: os vídeos que faltam não são postados",
          onclick: async (e) => {
            if (!confirm(`Parar o teste de ${canal.nome}? Os vídeos que faltam não serão postados. Dá para voltar no Radar, em Testar de novo.`)) return;
            e.currentTarget.disabled = true;
            const r = await pedir({ tipo: "api", caminho: "/api/ext/teste/parar", metodo: "POST", corpo: { canal_id: canal.canal_id } });
            aplicar(r);
            if (!r.erro) pedir({ tipo: "teste-sincronizar" });
          } })]),
      ...canal.videos.map((v) => cartaoDoVideo(canal, v))]));
  }

  carregar();
  setInterval(carregar, 2 * 60 * 1000);
})();
