// Radar de Canais. Quatro abas à esquerda, cada uma abre as suas opções embaixo (a aberta fica em vermelho).
// A primeira página é o perfil, com os canais da pessoa. Os filtros são só de escolher, nada de digitar.
const tela = document.getElementById("tela");
let EU = null, NOME = "Radar de Canais", NUMEROS = {}, PREFS = null;

// ---------------------------------------------------------------- utilidades
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (n) => n == null ? "—" : n >= 1e9 ? (n / 1e9).toFixed(1).replace(".", ",") + " bi" : n >= 1e6 ? (n / 1e6).toFixed(1).replace(".", ",") + " mi"
  : n >= 1e3 ? Math.round(n / 1e3).toLocaleString("pt-BR") + " mil" : Math.round(n).toLocaleString("pt-BR");
const nota = (x) => x == null ? "" : (x >= 10 ? Math.round(x) : x.toFixed(1).replace(".", ",")) + "x";
const FASES = { nascendo: "nascendo", crescendo: "crescendo", estavel: "estável", caindo: "caindo", parado: "parado" };
const SELOS = { lendario: "Lendário", epico: "Épico", raro: "Raro" };
const linkCanal = (c) => `https://www.youtube.com/${c.handle || "channel/" + (c.id || c.canal_id)}`;
const linkVideo = (id) => `https://www.youtube.com/watch?v=${id}`;

function ha(iso) {
  const dias = (Date.now() - new Date(iso)) / 864e5;
  if (!(dias >= 0)) return "";
  if (dias < 1 / 24) return "agora";
  if (dias < 1) return `há ${Math.round(dias * 24)} h`;
  if (dias < 30) return `há ${Math.round(dias)} ${Math.round(dias) === 1 ? "dia" : "dias"}`;
  if (dias < 365) { const m = Math.round(dias / 30.4); return `há ${m} ${m === 1 ? "mês" : "meses"}`; }
  const a = Math.round(dias / 365); return `há ${a} ${a === 1 ? "ano" : "anos"}`;
}
function duracao(s) {
  if (!s) return "";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0");
}
function vida(c) {
  if (c.meses_postando == null) return "";
  const dias = Math.round(c.meses_postando * 30.44), mais = c.primeiro_exato ? "" : "+";
  return dias < 365 ? `${dias}${mais} dias de vida` : `${(dias / 365).toFixed(1).replace(".", ",")}${mais} anos de vida`;
}
function aviso(texto) {
  const a = document.getElementById("aviso");
  a.textContent = texto; a.hidden = false;
  clearTimeout(aviso.t); aviso.t = setTimeout(() => (a.hidden = true), 4500);
}
const guardado = (k, padrao) => { try { return JSON.parse(localStorage.getItem("radar:" + k)) ?? padrao; } catch { return padrao; } };
const guardar = (k, v) => { try { localStorage.setItem("radar:" + k, JSON.stringify(v)); } catch {} };

// ---------------------------------------------------------------- falar com o Radar
// Três coisas moram aqui, para nenhuma tela ter de lembrar delas: o pacote de abertura (a primeira chamada de cada
// caminho frio já vem respondida), a memória curta (o que muda devagar não volta ao servidor a cada tela) e o que
// fazer quando o Radar não responde — dizer em português o que a pessoa faz a seguir, e esperar ele voltar.

const PACOTE = new Map();            // caminho -> resposta que veio na abertura, servida uma vez só
let PACOTE_PRONTO = null;

// o que muda devagar: vale reaproveitar por dois minutos em vez de pedir de novo a cada troca de tela
// `/api/eu` fica de fora de propósito: ele muda por /api/entrar e /api/sair, que são outros caminhos, e uma
// resposta velha aqui mostraria a conta de quem acabou de sair
const FRIAS = ["/api/resumo", "/api/prefs", "/api/painel", "/api/alvos", "/api/filtros", "/api/visoes", "/api/pastas"];
const MEM_MS = 120000;
const MEM = new Map();               // caminho -> { quando, dados }
const VOO = new Map();               // caminho -> a chamada que já está no ar (duas telas não pedem a mesma coisa)
const fria = (caminho) => FRIAS.includes(caminho.split("?")[0]);
// esquecer o que ficou velho depois de uma mudança (um canal salvo, um garimpo novo). Sem caminho, esquece tudo:
// é o que entrar e sair precisam, porque daí em diante quem pergunta é outra pessoa
const esquecer = (...caminhos) => {
  if (!caminhos.length) { MEM.clear(); PACOTE.clear(); return; }
  caminhos.forEach((c) => { MEM.delete(c); PACOTE.delete(c); });
};

// o que a pessoa faz agora, não o número do erro. O Radar roda na máquina dela: quase sempre é religar.
function porque(erro) {
  const s = erro && erro.status;
  if (!s) return `Não consegui falar com o Radar. Ligue ele (dois cliques em LIGAR-RADAR.bat, na pasta do Radar) e tente de novo.`;
  if (s === 401) return "A sua sessão terminou. Entre de novo.";
  if (s === 402) return erro.message;                 // o próprio servidor diz de que plano é
  if (s === 404) return "Esta parte do Radar ainda não subiu. Feche e abra o Radar (LIGAR-RADAR.bat).";
  if (s >= 500) return `O Radar falhou ao responder. Tente de novo em instantes. (${erro.message})`;
  return erro.message || "Algo deu errado.";
}

// enquanto o Radar está voltando (deploy, reinício), a faixa em cima da tela em vez de um erro seco.
// Quem manda na faixa é quantos pedidos estão tentando de novo, não o último que respondeu: o /api/cota de fundo
// chega a toda hora, e se ele apagasse a faixa ela sumiria com a tela ainda esperando.
const ESPERAS = [2000, 4000, 8000, 15000, 30000, 30000];
let tentandoDeNovo = 0;
function voltando() {
  const f = document.getElementById("faixa-voltando");
  if (!tentandoDeNovo) { if (f) f.remove(); return; }
  if (f || !document.body) return;
  const nova = document.createElement("div");
  nova.id = "faixa-voltando";
  nova.setAttribute("role", "status");
  nova.textContent = "O Radar está voltando — um instante.";
  document.body.appendChild(nova);
}

async function umPedido(caminho, opcoes) {
  const r = await fetch(caminho, { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...opcoes,
    body: opcoes.body ? JSON.stringify(opcoes.body) : undefined });
  const dados = await r.json().catch(() => ({}));
  // "resposta" marca o erro que veio do próprio Radar (ele explicou em JSON o que houve), e não de um
  // servidor caído no meio do caminho: só o segundo adianta tentar de novo.
  if (!r.ok) throw Object.assign(new Error(dados.detail || "Algo deu errado."), { status: r.status, resposta: !!dados.detail });
  return dados;
}

async function api(caminho, opcoes = {}) {
  const leitura = !opcoes.method || opcoes.method === "GET";
  if (!leitura) esquecer(caminho);                    // quem escreve invalida a leitura do mesmo caminho
  if (leitura) {
    if (PACOTE.has(caminho)) { const d = PACOTE.get(caminho); PACOTE.delete(caminho); return d; }
    const guardado = MEM.get(caminho);
    if (guardado && Date.now() - guardado.quando < MEM_MS) return guardado.dados;
    if (VOO.has(caminho)) return VOO.get(caminho);
  }
  // 502/503/504 sem resposta do Radar é ele reiniciando: espera e tenta de novo, com a faixa avisando.
  // Quando o 503 é o próprio Radar dizendo que algo de fora está desligado (a fábrica na porta 8080, por
  // exemplo), tentar de novo seis vezes só deixava a tela em "Carregando…" por um minuto e meio: esse erro
  // é uma resposta, passa direto para a tela mostrar o que houve.
  const tentar = async () => {
    let contado = false;
    try {
      for (let i = 0; ; i++) {
        try {
          return await umPedido(caminho, opcoes);
        } catch (erro) {
          if (![502, 503, 504].includes(erro.status) || erro.resposta || i >= ESPERAS.length) throw erro;
          if (!contado) { contado = true; tentandoDeNovo++; voltando(); }
          await new Promise((ok) => setTimeout(ok, ESPERAS[i]));
        }
      }
    } finally {
      if (contado) { tentandoDeNovo--; voltando(); }
    }
  };
  if (!leitura) return tentar();
  const voo = tentar().then((d) => {
    if (fria(caminho)) MEM.set(caminho, { quando: Date.now(), dados: d });
    return d;
  }).finally(() => VOO.delete(caminho));
  VOO.set(caminho, voo);
  return voo;
}

// a abertura: uma chamada traz o que a primeira tela pediria em várias
async function abrirPacote() {
  PACOTE_PRONTO = umPedido("/api/abertura", {})
    .then((d) => { for (const [k, v] of Object.entries(d.pacote || {})) PACOTE.set("/api/" + k, v); })
    .catch(() => {});
  return PACOTE_PRONTO;
}
const consulta = (obj) => new URLSearchParams(Object.entries(obj).filter(([, v]) => v !== "" && v != null && v !== false)).toString();
// as listas que as telas pedem: a memória curta do api() já guarda, não precisam de cache próprio
const opcoes = () => api("/api/filtros");
// as visões: as perguntas prontas da lista de canais. A regra de cada uma é do servidor; aqui só o nome e o rótulo.
// Se o servidor não souber responder, a faixa some e o resto da tela continua de pé: procurar não depende dela.
const visoes = () => api("/api/visoes").then((d) => d.visoes).catch(() => []);
// as pastas da base: a lista sai de quem está guardado, então ela muda sozinha quando um canal troca de pasta
const pastas = () => api("/api/pastas").catch(() => ({ pastas: [], sem_pasta: 0 }));

async function carregando(botao, texto, tarefa) {
  const antes = botao.innerHTML; botao.disabled = true; botao.textContent = texto;
  try { return await tarefa(); } catch (e) { aviso(porque(e)); } finally { if (botao.isConnected) { botao.disabled = false; botao.innerHTML = antes; } }
}

// ---------------------------------------------------------------- ícones
const I = {
  perfil: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
  descobrir: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5"/>',
  criar: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/>',
  producao: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9l5 3-5 3z"/>',
  ideias: '<path d="M9 18h6M10 22h4M12 2a7 7 0 00-4 12.7V16h8v-1.3A7 7 0 0012 2z"/>',
  ferramentas: '<path d="M14.7 6.3a4 4 0 00-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 005.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/>',
  seta: '<path d="M9 6l6 6-6 6"/>',
  youtube: '<rect x="2" y="5" width="20" height="14" rx="4"/><path d="M10 9l5 3-5 3z"/>',
  marcar: '<path d="M6 3h12v18l-6-4-6 4z"/>',
  roteiro: '<path d="M14 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
  pasta: '<path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>',
  olho: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="3"/>',
  olhoFechado: '<path d="M3 3l18 18"/><path d="M10.6 6.2A9.8 9.8 0 0112 6c6.5 0 10 6 10 6a16 16 0 01-3.4 4M6.5 7.7A16 16 0 002 12s3.5 6 10 6c1.3 0 2.5-.2 3.5-.6"/>',
  arrastar: '<path d="M8 6h.01M8 12h.01M8 18h.01M16 6h.01M16 12h.01M16 18h.01"/>',
};
const icone = (n, classe = "") => `<svg ${classe ? `class="${classe}"` : ""} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I[n]}</svg>`;

// ---------------------------------------------------------------- menu: 4 abas que abrem

// Descobrir vem primeiro: é onde o trabalho começa, e agora são duas listas só — canais e vídeos — em vez de
// seis telas que faziam quase a mesma pergunta (Alerta, Explorar, Procurar, Em alta, Top 30, Salvos).
// A terceira posição de uma aba é o endereço dela, quando não é só "#/rota": serve para a mesma tela entrar no
// menu com um recorte pronto (Entraram hoje é a lista de canais com a visão já ligada).
const MENU = [
  ["perfil", "Perfil", [["inicio", "Início"], ["trabalho", "Produzir"], ["acompanhar", "Acompanhar"], ["resultados", "Resultados"], ["custos", "Custos"]]],
  ["descobrir", "Niche Finder", [["base", "Canais"], ["entraram", "Entraram hoje", "#/base?visao=entraram_hoje"],
    // Títulos saiu do menu de manhã (25/10) e voltou de tarde, no mesmo dia, quando o usuário pediu os "títulos
    // recomendados": agora a tela abre com os títulos que estouraram NOS NICHOS DOS CANAIS DELE, que é o que
    // faltava para ela valer o lugar no menu. O gerador continua aqui e no Roteiro.
    ["videos", "Faceless Outliers"], ["titulos", "Títulos que funcionam"], ["grupos", "Grupos de canais"],
    ["acharam", "Acharam para você"]]],
  ["ferramentas", "Ferramentas", [["extensao", "Extensão"], ["medir", "Medir canal"], ["bloqueados", "Bloqueados"], ["planos", "Planos"], ["admin", "Administração"], ["integracoes", "Integrações"]]],
];
const DICAS = {
  planos: "O que cada plano abre, e o preço",
  base: "Todos os canais do Radar, com as perguntas prontas", videos: "Todos os vídeos que estouraram, num filtro só",
  acharam: "Os parecidos que os seus canais salvos trouxeram", grupos: "Os nichos, do mais aberto ao mais concorrido",
  entraram: "Os canais que o garimpo achou nas últimas 24 horas", titulos: "Títulos no estilo dos que estouraram, e o banco deles",
  inicio: "Começo: seus canais e como o app funciona", canais: "Seus canais e as métricas do Studio",
  trabalho: "O roteiro com o Claude, a thumbnail e o envio para a fábrica", acompanhar: "O que a fábrica está produzindo agora",
  resultados: "Os vídeos prontos, com o custo de cada um", custos: "Quanto cada vídeo, provedor e canal gastou",
  titulo: "Converse com o Claude sobre o título e leve para o roteiro", medir: "Cole um @ e veja os números na hora",
  extensao: "Garimpa enquanto você usa o YouTube", bloqueados: "O que você escondeu pelo ⊘", admin: "Cota do YouTube, garimpo e convites",
  integracoes: "As chaves de API e o saldo de cada serviço",
};

// a aba de endereço pronto (Entraram hoje) está acesa quando a tela é a dela e o recorte dela está ligado
function noEndereco(endereco) {
  const [base, q] = endereco.split("?");
  if ("#/" + rotaAtual() !== base) return false;
  const atual = new URLSearchParams(location.hash.split("?")[1] || "");
  return [...new URLSearchParams(q || "")].every(([k, v]) => atual.get(k) === v);
}

function grupoDa(rota) {
  if (rota === "canal") return "perfil";
  if (rota === "perfil") return "perfil";
  return (MENU.find(([, , subs]) => subs.some(([r]) => r === rota)) || MENU[0])[0];
}

// ---------------------------------------------------------------- o menu é de quem usa
// A ordem das abas e as que você escondeu ficam na sua conta, não no navegador. No modo organizar, cada aba
// pode ser arrastada dentro do grupo dela e escondida pelo olho — e a lista de canais não some, porque sem ela
// não sobra por onde começar.
let PAINEL = { abas_ordem: [], abas_ocultas: [], fixas: ["base"] };
let ORGANIZANDO = false;

// uma aba nova entra ao lado das vizinhas dela, não no fim: quem já arrumou o menu não arruma de novo
function ordemComAsNovas(todas, pedida) {
  const fila = pedida.filter((r) => todas.includes(r));
  if (!fila.length) return todas;
  todas.forEach((r, i) => {
    if (fila.includes(r)) return;
    let onde = 0;
    for (let j = i - 1; j >= 0; j--) {
      const k = fila.indexOf(todas[j]);
      if (k !== -1) { onde = k + 1; break; }
    }
    fila.splice(onde, 0, r);
  });
  return fila;
}

const abaEscondida = (r) => PAINEL.abas_ocultas.includes(r) && !PAINEL.fixas.includes(r);

async function salvarPainel() {
  try { PAINEL = await api("/api/painel", { method: "POST", body: PAINEL }); }
  catch (e) { aviso(porque(e)); }
}

function menu(rota) {
  document.getElementById("lateral").hidden = !EU;
  if (!EU) return;
  const aberto = grupoDa(rota);
  const abertos = guardado("menu-aberto2", {});   // os outros grupos ficam como você deixou; o grupo da tela abre sozinho
  const atalho = MENU.flatMap(([, , subs]) => subs).find(([, , endereco]) => endereco && noEndereco(endereco));
  document.getElementById("menu").className = ORGANIZANDO ? "organizando" : "";
  document.getElementById("menu").innerHTML = MENU.map(([g, nome, subs]) => {
    const podem = subs.filter(([r]) => !["admin", "integracoes"].includes(r) || EU.admin);
    const naOrdem = ordemComAsNovas(podem.map(([r]) => r), PAINEL.abas_ordem)
      .map((r) => podem.find(([x]) => x === r)).filter(Boolean);
    const itens = ORGANIZANDO ? naOrdem : naOrdem.filter(([r]) => !abaEscondida(r));
    const mostra = g === aberto || !!abertos[g] || (ORGANIZANDO && itens.length > 0);
    if (!itens.length) return "";
    return `<div class="aba ${mostra ? "aberta" : ""} ${g === aberto ? "dentro" : ""}" data-grupo="${g}">${icone(g)}<span>${nome}</span>${icone("seta", "seta")}</div>
      <div class="subs" ${mostra ? "" : "hidden"} data-grupo="${g}">${itens.map(([r, t, endereco]) => {
        const ativo = endereco ? atalho && atalho[0] === r
          : !atalho && (r === rota || ((rota === "canal" || rota === "perfil" || rota === "canais") && r === "inicio"));
        const fixa = PAINEL.fixas.includes(r);
        return `<a href="${endereco || "#/" + r}" data-aba="${r}" draggable="${ORGANIZANDO}"
          class="${ativo ? "ativo" : ""} ${abaEscondida(r) ? "escondida" : ""}" title="${esc(DICAS[r] || "")}">
          ${ORGANIZANDO ? `<i class="pega">${icone("arrastar")}</i>` : ""}<span class="rot">${t}</span>
          ${ORGANIZANDO && !fixa ? `<button class="olho" data-esconder="${r}" title="${abaEscondida(r) ? "Mostrar esta aba" : "Esconder esta aba"}">${icone(abaEscondida(r) ? "olhoFechado" : "olho")}</button>` : ""}</a>`;
      }).join("")}</div>`;
  }).join("");
  document.querySelectorAll("nav .aba").forEach((a) => (a.onclick = () => {
    const g = a.dataset.grupo, subs = a.nextElementSibling, f = guardado("menu-aberto2", {});
    f[g] = subs.hidden; guardar("menu-aberto2", f);
    subs.hidden = !f[g]; a.classList.toggle("aberta", f[g]);
  }));
  if (ORGANIZANDO) ligarOrganizar(rota);
  // acesso livre (sem e-mail e senha): não tem o que sair
  document.getElementById("conta").innerHTML = `<button class="organizar" id="organizar">${ORGANIZANDO ? "✓ Pronto" : "Organizar o menu"}</button>`
    + (EU.livre ? `<span class="sub">Acesso livre neste computador</span>`
      : `<span><b>${esc(EU.nome || EU.email)}</b></span><button class="botao sec" id="sair">Sair</button>`);
  quadroCota();
  document.getElementById("organizar").onclick = () => { ORGANIZANDO = !ORGANIZANDO; menu(rota); };
  const sair = document.getElementById("sair");
  if (sair) sair.onclick = async () => { await api("/api/sair", { method: "POST" }); esquecer(); EU = null; location.hash = "#/entrar"; };
}

// no modo organizar: arrastar a aba dentro do grupo dela e o olho para esconder. Cada mexida já fica salva na conta.
function ligarOrganizar(rota) {
  const raiz = document.getElementById("menu");
  const guardarOrdem = async () => {
    PAINEL.abas_ordem = [...raiz.querySelectorAll("a[data-aba]")].map((a) => a.dataset.aba);
    await salvarPainel();
  };
  raiz.querySelectorAll("[data-esconder]").forEach((b) => (b.onclick = async (e) => {
    e.preventDefault(); e.stopPropagation();
    const r = b.dataset.esconder;
    PAINEL.abas_ocultas = abaEscondida(r) ? PAINEL.abas_ocultas.filter((x) => x !== r) : [...PAINEL.abas_ocultas, r];
    await salvarPainel();
    menu(rota);
  }));
  let arrastando = null;
  raiz.querySelectorAll("a[data-aba]").forEach((a) => {
    a.onclick = (e) => { if (ORGANIZANDO) e.preventDefault(); };   // organizando não navega: o clique é para arrastar
    a.ondragstart = (e) => { arrastando = a; a.classList.add("arrastando"); e.dataTransfer.effectAllowed = "move"; };
    a.ondragend = async () => { a.classList.remove("arrastando"); arrastando = null; await guardarOrdem(); };
    a.ondragover = (e) => {
      if (!arrastando || arrastando === a || arrastando.parentElement !== a.parentElement) return;
      e.preventDefault();                       // só dentro do mesmo grupo: a aba não troca de assunto ao ser movida
      const r = a.getBoundingClientRect();
      a.parentElement.insertBefore(arrastando, e.clientY > r.top + r.height / 2 ? a.nextSibling : a);
    };
    a.ondrop = (e) => e.preventDefault();
  });
}

// "Para que serve": a caixinha verde de cada página. O × esconde; o "?" ao lado do título mostra de novo.
const AJUDA = {
  "radar-paises": "Um <b>radar por canal</b>: os países e as línguas onde conferir se uma ideia já foi feita. No <b>📡</b> de cada vídeo, o Radar tira toda a numeração do título, traduz a ideia para a língua de cada país e procura no YouTube daquele país: <b>⚠ já foi feito</b> (com os vídeos parecidos) ou <b>✅ ninguém fez ainda</b>.",
  "ideias-canal": "Ideias para <b>cada canal seu</b> (uma aba por canal): vídeos que estouraram falando do mesmo assunto. <b>💡 Salvar ideia</b> guarda no painel da direita, e de lá <b>Levar para o trabalho</b> abre o roteiro com o vídeo de referência.",
  bloqueados: "Tudo o que você escondeu pelo <b>⊘</b> em cima dos vídeos: vídeos, canais e tipos de vídeo. Desbloqueie para voltar a ver.",
  custos: "Quanto a fábrica gastou: o <b>total do período</b>, a média por vídeo e por minuto, e onde foi o dinheiro: <b>por provedor</b> (GenAI Pro, OpenRouter, Kie...), por tipo de gasto (narração, imagens de IA...) e <b>por canal</b>. Clique num vídeo para ver o detalhe.",
  integracoes: "Os serviços que o Radar e a fábrica usam: o <b>saldo</b> de cada um e as <b>chaves de API</b>, para testar, trocar, acrescentar e remover sem abrir o arquivo .env. A chave inteira nunca aparece, só o fim dela.",
  acompanhar: "A fila da fábrica: à esquerda o que <b>precisa de você</b>, o que está produzindo, o que espera a vez e a <b>Entrada</b> (guardados, não gastam). Escolha um vídeo para ver as etapas, o <b>Diagnóstico</b> (quantas cenas são reais e quantas são de IA, e o log), os arquivos e as tags. Em cima, quantos vídeos a fábrica faz ao mesmo tempo: o resto espera e começa sozinho.",
  resultados: "Os vídeos prontos com o <b>custo real</b> de cada um (narração, imagens, visão), o custo por minuto e o total. Assista aqui ou abra a pasta da entrega.",
  titulo: "Cole o <b>título</b> e o link do vídeo (depois a extensão manda direto para cá) e converse com o <b>Claude</b>: regionalizar para outro país, deixar mais chamativo, traduzir. Clique em <b>usar</b> no título que gostar e em <b>Levar para o roteiro</b>: o Roteiro abre com o título, o link e a thumbnail. Conferir no YouTube se o título já foi feito é com você.",
  thumbnail: "Escreva o que quer (ex.: <b>tire o texto</b>), escolha o canal e cole o vídeo de referência. O <b>Claude</b> escreve o prompt com o estilo de thumbnail do canal e o que a referência mostra, e o botão manda para o <b>Gemini</b> ou o <b>ChatGPT</b>. Cada canal guarda o estilo e a IA dele.",
  trabalho: "Aqui você <b>cria o vídeo</b>, um passo de cada vez: o <b>link da referência</b> e o título; o <b>canal</b> (a voz, a língua, o agente e o tempo vêm dele); o <b>Claude</b> escreve o roteiro limpo, só o texto para narrar; a <b>thumbnail</b>, se quiser; e o <b>envio para a fábrica</b>, com o ▶ Produzir.",
  preferencias: "As respostas das perguntas da primeira vez (nichos, línguas, formato, o que nunca mostrar) e tudo o que você bloqueou pelo <b>⊘</b>. Elas valem no Explorar, nos Vídeos que estouraram e nas ideias de cada canal.",
  perfil: "Seus canais. Conecte ao <b>YouTube Studio</b> para ver as métricas que só o dono vê (horas assistidas, retenção, receita, de onde vêm as views). Clicando num canal, as <b>ideias para copiar</b>: vídeos que estouraram falando do mesmo assunto.",
  canal: "Tudo de um canal: os últimos vídeos com a nota de cada um, as <b>ideias para copiar</b> (vídeos que estouraram em canais do mesmo nicho) e, se o canal for seu e estiver conectado, as métricas do YouTube Studio.",
  base: "Uma lista só com todos os canais do Radar. Em cima, as <b>visões</b>: perguntas já feitas (novo e crescendo, virou a chave, sem concorrência…), com quantos canais cada uma tem — clique numa para ver a lista, clique de novo para desligar. Embaixo, o filtro: base, nicho, tamanho, idade, fase e a <b>ordem</b>, que o ↓ vira para o outro lado. O que era Alerta, Procurar nicho, Em alta, Top 30 e Salvos virou filtro desta tela. Todo canal que você salva ganha um botão de <b>pasta</b>: guarde por projeto, e a pasta vira filtro aqui e nos Vídeos.",
  videos: "Uma lista só com os vídeos que fizeram <b>muitas vezes o normal do próprio canal</b>. Se um assunto fez 10 vezes o normal, o público quer aquele assunto. Filtre por língua, nicho, nota, data e formato; as marcas ligam <b>só os desta semana</b> e <b>só de canal crescendo</b>. Quando as suas respostas escondem vídeos, a contagem diz quantos são e abre com um clique. Passe o mouse na capa e clique no <b>🔖</b> do canto para pôr o vídeo na esteira: um clique marca <b>vou modelar</b>, outro marca <b>já modelei</b>, e o filtro <b>Toda a esteira</b> mostra só esses.",
  acharam: "Cada canal que você salva vira um garimpeiro: uma vez por semana ele procura sozinho os canais <b>parecidos</b> com ele. O que eles acharam chega aqui, já medido. Quanto mais canais você salva, mais chega.",
  grupos: "Canais que fazem o <b>mesmo tipo de vídeo</b>, juntos. Poucos canais com muita view é <b>nicho aberto</b>; muitos canais, já está concorrido. Clique num grupo para ver os canais.",
  titulos: "Escreva o tema e o gerador faz <b>títulos no estilo dos que estouraram</b>. Embaixo, o banco de títulos que deram certo, para se inspirar.",
  roteiro: "O <b>Claude</b> escreve o roteiro: você põe o título que escolheu, o tempo do vídeo e o link de um vídeo de referência. A <b>transcrição</b> dele vira a base e a <b>thumbnail</b> é copiada. Grátis pela sua assinatura do Claude.",
  medir: "Cole o @ de <b>qualquer canal</b> e veja na hora quanto ele faz por vídeo, a fase e os vídeos que estouraram. Dá para pôr no Radar.",
  extensao: "Enquanto você navega no YouTube, a extensão <b>lê os vídeos da tela</b> (sem gastar a cota) e guarda no Radar os que estouraram e os canais novos. Na busca, mostra se o <b>nicho está aberto</b>; o botão <b>Vídeos desta página</b> ordena e filtra o que a página mostrou.",
  admin: "A cota grátis da API do YouTube (10 mil por dia), o garimpo que procura canais novos e os convites para os sócios.",
};

function titulo(t, sub, chave = rotaAtual()) {
  const fechada = guardado("ajuda-fechada", {})[chave];
  const texto = AJUDA[chave];
  return `<div class="cab-tela"><div><h1>${t}${texto && fechada ? ` <button class="mostrar-ajuda" data-rota="${chave}" title="Para que serve?">?</button>` : ""}</h1>
    ${sub ? `<p class="linha-sub">${sub}</p>` : ""}</div></div>
    ${texto && !fechada ? `<div class="ajuda"><span class="i">i</span><span><b>Para que serve:</b> ${texto}</span><button title="Esconder" data-fechar="${chave}">×</button></div>` : ""}`;
}
function rotaAtual() { return location.hash.replace(/^#\/?/, "").split(/[?/]/)[0]; }

// ---------------------------------------------------------------- o recorte: o filtro mora no endereço
// O que a pessoa escolhe numa tela (filtros, ordem, período) vira a consulta do endereço:
// #/explorar?nicho=História&nota_min=10. Assim o filtro montado é um link para mandar para alguém, o
// Voltar do navegador devolve a tela do jeito que ela estava, e nada continua filtrando escondido —
// filtro guardado no navegador que a tela não mostrava já deixou lista vazia sem ninguém entender.
// Só o que difere do padrão da tela entra no endereço: sem mexer em nada, o endereço fica limpo.

const PADRAO_VALE = (f, padrao, k) => String(f[k] ?? "") !== String(padrao[k] ?? "");
const mudouDoPadrao = (f, padrao) => Object.keys(padrao).some((k) => PADRAO_VALE(f, padrao, k));

// o filtro da tela: o padrão, com o que veio no endereço por cima (só as chaves que a tela conhece)
function recorte(padrao) {
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  const f = { ...padrao };
  for (const k of Object.keys(padrao)) if (q.has(k)) f[k] = q.get(k);
  return f;
}
// replaceState não dispara o hashchange: o endereço acompanha o filtro sem a tela ser desenhada de novo
function recorteParaOEndereco(f, padrao) {
  const q = new URLSearchParams();
  for (const k of Object.keys(padrao)) if (PADRAO_VALE(f, padrao, k)) q.set(k, f[k]);
  const base = "#/" + location.hash.replace(/^#\/?/, "").split("?")[0];
  const novo = q.toString() ? `${base}?${q}` : base;
  if (location.hash !== novo) history.replaceState(null, "", novo);
}
// o "voltar ao padrão" só aparece quando há o que desfazer (sem contar o que ele não mexe, como a busca digitada)
function marcarBotaoPadrao(raiz, f, padrao, manter = []) {
  const b = raiz.querySelector(".selects .limpar");
  if (b) b.hidden = !Object.keys(padrao).some((k) => !manter.includes(k) && PADRAO_VALE(f, padrao, k));
}
document.addEventListener("click", (e) => {
  const fechar = e.target.closest("[data-fechar]"), mostrar = e.target.closest(".mostrar-ajuda");
  if (!fechar && !mostrar) return;
  const f = guardado("ajuda-fechada", {});
  if (fechar) { f[fechar.dataset.fechar] = 1; fechar.closest(".ajuda").remove(); }
  else { delete f[mostrar.dataset.rota]; rota(); }
  guardar("ajuda-fechada", f);
});

// ---------------------------------------------------------------- peças

// o 🔀 das listas que já vieram inteiras: embaralha o que está na tela
const botaoAleatorio = (alvo) => ` <button class="botao vermelho embaralhar" data-alvo="${alvo}" style="font-size:13px;vertical-align:middle">🔀 Aleatório</button>`;
document.addEventListener("click", (e) => {
  const b = e.target.closest(".embaralhar");
  if (!b) return;
  document.querySelectorAll(b.dataset.alvo).forEach((lista) => {
    const itens = [...lista.children];
    for (let i = itens.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [itens[i], itens[j]] = [itens[j], itens[i]]; }
    itens.forEach((x) => lista.appendChild(x));
    // dentro de "Em alta" as duas colunas também
    lista.querySelectorAll(".bloco").forEach((bl) => { const ls = [...bl.querySelectorAll(".linha-canal")]; ls.sort(() => Math.random() - 0.5).forEach((x) => bl.appendChild(x)); });
  });
});

function capaDoVideo(v) {
  return `<a class="capa" href="${linkVideo(esc(v.id))}" target="_blank" rel="noopener">
    <img loading="lazy" src="https://i.ytimg.com/vi/${esc(v.id)}/mqdefault.jpg" alt="">
    ${v.nota != null ? `<span class="nota ${v.nota >= 5 ? "alta" : ""}" title="Fez ${nota(v.nota)} o normal do canal">${nota(v.nota)}</span>` : ""}
    ${v.duracao_s ? `<span class="dur">${duracao(v.duracao_s)}</span>` : ""}</a>`;
}

function cartaoVideo(v, { canal = true, roteiro = true, bloquear = true } = {}) {
  return `<div class="video" data-video="${esc(v.id)}" data-canal="${esc(v.canal_id || "")}" data-nomecanal="${esc(v.canal || "")}" data-nicho="${esc(v.subnicho || v.nicho || "")}" data-titulo="${esc(v.titulo)}">
    ${capaDoVideo(v)}<div class="icones-capa">${canal && v.canal ? "" : botaoAlvo(v)}${bloquear && v.canal_id ? '<button class="bloq" data-dica="Não mostrar mais este vídeo nem este canal">⊘</button>' : ""}</div>
    <a class="titulo" href="${linkVideo(esc(v.id))}" target="_blank" rel="noopener">${esc(v.titulo)}</a>
    <div class="meta">${num(v.views)} views · ${ha(v.publicado)}${v.por_hora ? ` · ${num(v.por_hora)}/h` : ""}</div>
    ${canal && v.canal ? `<a class="dono" href="#/canal/${esc(v.canal_id)}"><img src="${esc(v.foto)}" alt="" referrerpolicy="no-referrer">
      <span>${esc(v.canal)}${v.inscritos != null ? " · " + num(v.inscritos) + " inscritos" : ""}</span><span class="dono-acoes">${botaoAlvo(v)}${v.canal_id ? botaoInscrever(v.canal_id) : ""}</span></a>` : ""}
    ${roteiro ? `<div class="video-acoes"><button class="botao sec salvar-ideia" title="Guarda no painel da direita">💡 Salvar ideia</button>
      <a class="botao sec" href="#/trabalho" data-roteiro="${esc(v.id)}" data-titulo="${esc(v.titulo)}" title="Abre o Roteiro com este vídeo de referência">${icone("roteiro")}Trabalho</a></div>` : ""}
  </div>`;
}
// o cartão grande do Descobrir (Explorar e Vídeos que estouraram), no jeito do niche finder:
// capa grande, a foto do canal ao lado do título e as pílulas de views por hora e inscritos
function cartaoVideoGrande(v) {
  const horas = v.publicado ? Math.max(1, (Date.now() - Date.parse(v.publicado)) / 36e5) : 0;
  const porHora = v.por_hora || (horas && v.views ? Math.round(v.views / horas) : 0);
  return `<div class="video yt" data-video="${esc(v.id)}" data-canal="${esc(v.canal_id || "")}" data-nomecanal="${esc(v.canal || "")}" data-nicho="${esc(v.subnicho || v.nicho || "")}" data-titulo="${esc(v.titulo)}">
    ${capaDoVideo(v).replace("/mqdefault.jpg", "/hqdefault.jpg")}<div class="icones-capa">${marcadorEsteira(v)}${v.canal_id ? '<button class="bloq" data-dica="Não mostrar mais este vídeo nem este canal">⊘</button>' : ""}</div>
    <div class="yt-linha"><a class="yt-foto" href="#/canal/${esc(v.canal_id || "")}"><img src="${esc(v.foto || "")}" alt="" loading="lazy" referrerpolicy="no-referrer"></a>
      <div class="yt-texto"><a class="titulo" href="${linkVideo(esc(v.id))}" target="_blank" rel="noopener">${esc(v.titulo)}</a>
        <a class="yt-canal" href="#/canal/${esc(v.canal_id || "")}">${esc(v.canal || "")}</a>
        <div class="meta">${num(v.views)} views · ${ha(v.publicado)}</div>
        <div class="pilulas">${porHora ? `<span>${num(porHora)} por hora</span>` : ""}${v.inscritos != null ? `<span>${num(v.inscritos)} inscritos</span>` : ""}</div></div></div>
    <div class="video-acoes"><button class="botao sec salvar-ideia" title="Guarda no painel da direita">💡 Salvar ideia</button>
      <a class="botao sec" href="#/trabalho" data-roteiro="${esc(v.id)}" data-titulo="${esc(v.titulo)}" title="Abre o Roteiro com este vídeo de referência">${icone("roteiro")}Trabalho</a></div>
  </div>`;
}
function ligarRoteiro(raiz = tela) {
  raiz.querySelectorAll("[data-roteiro]").forEach((a) => (a.onclick = () =>
    guardar("roteiro-preset", { link: linkVideo(a.dataset.roteiro), titulo: a.dataset.titulo || "" })));
}

// ---------------------------------------------------------------- a esteira: vou modelar → já modelei
// O marcador no canto da capa anda sozinho a cada clique, sem menu: vazio → vou modelar → já modelei → vazio.
// Serve para não perder de vista o vídeo que você escolheu no meio de milhares, e para não refazer o que já fez.
const ESTEIRA = {
  "": { proximo: "fila", sinal: "🔖", dica: "Marcar: vou modelar este vídeo" },
  fila: { proximo: "feito", sinal: "📌", dica: "Vou modelar — clique para marcar como já modelado" },
  feito: { proximo: "", sinal: "✓", dica: "Já modelei — clique para tirar o marcador" },
};
const marcadorEsteira = (v) => {
  const estado = ESTEIRA[v.modelar] ? v.modelar : "";
  return `<button class="marcador ${estado}" data-modelar="${esc(v.id)}" data-estado="${estado}"
    title="${ESTEIRA[estado].dica}">${ESTEIRA[estado].sinal}</button>`;
};
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-modelar]");
  if (!b) return;
  e.preventDefault(); e.stopPropagation();
  const estado = ESTEIRA[b.dataset.estado] ? b.dataset.estado : "";
  const novo = ESTEIRA[estado].proximo;
  try {
    await api(`/api/modelar/${encodeURIComponent(b.dataset.modelar)}`, { method: "POST", body: { estado: novo } });
    b.dataset.estado = novo;
    b.className = `marcador ${novo}`;
    b.textContent = ESTEIRA[novo].sinal;
    b.title = ESTEIRA[novo].dica;
  } catch (erro) { aviso(porque(erro)); }
});

function tagsDoCanal(c) {
  return [
    c.novo && '<span class="tag novo">novo</span>',
    c.raridade && `<span class="tag ${c.raridade}">${SELOS[c.raridade]}</span>`,
    (c.subnicho || c.nicho) && `<span class="tag">${esc(c.subnicho || c.nicho)}</span>`,
    c.fase && `<span class="tag ${c.fase}">${FASES[c.fase] || c.fase}</span>`,
    c.sem_rosto && '<span class="tag">sem rosto</span>',
  ].filter(Boolean).join("");
}

function miolo(c, { posicao } = {}) {
  return `<div class="canal-cab">
      ${posicao ? `<div class="posicao">${posicao}</div>` : ""}
      <img class="avatar" src="${esc(c.foto)}" alt="" loading="lazy" referrerpolicy="no-referrer">
      <div class="canal-info">
        <div class="canal-nome"><a href="#/canal/${esc(c.id)}">${esc(c.titulo)}</a>${tagsDoCanal(c)}</div>
        <div class="numeros"><span><b>${num(c.inscritos)}</b> inscritos${c.ganho_7d ? ` <span style="color:var(--verde)">+${num(c.ganho_7d)}/sem</span>` : ""}</span>
          <span><b>${c.videos_total ?? "—"}</b> vídeos</span><span>${vida(c)}</span>
          <span class="media"><b>${num(c.normal_longos)}</b> por vídeo</span></div>
      </div>
      <div class="canal-acoes">
        <button class="botao ${c.salvo ? "salvo" : "vermelho"} salvar" data-id="${esc(c.id)}">${icone("marcar")}${c.salvo ? "Salvo" : "Salvar"}</button>
        ${botaoPasta(c)}
        <a class="botao sec" href="${esc(linkCanal(c))}" target="_blank" rel="noopener" title="Abrir no YouTube">${icone("youtube")}</a>
      </div>
    </div>`;
}

function cartaoCanal(c, { posicao, rodape = "" } = {}) {
  return `<article class="canal" data-id="${esc(c.id)}">${miolo(c, { posicao })}<div class="inscrever-canal">${botaoInscrever(c.id)}</div>
    ${c.videos && c.videos.length ? `<div class="capas">${c.videos.map((v) => `<div class="video">${capaDoVideo(v)}
      <a class="titulo" href="${linkVideo(esc(v.id))}" target="_blank" rel="noopener">${esc(v.titulo)}</a>
      <div class="meta">${num(v.views)} views · ${ha(v.publicado)}</div></div>`).join("")}</div>` : ""}
    ${rodape}</article>`;
}

function linhaCanal(c, valor) {
  return `<a class="linha-canal" href="#/canal/${esc(c.id)}">
    <img src="${esc(c.foto)}" alt="" referrerpolicy="no-referrer" loading="lazy">
    <span class="nome"><b>${esc(c.titulo)}</b><small>${esc(c.subnicho || c.nicho || "")}</small></span>${valor}</a>`;
}

// a pasta do canal: só aparece em quem já está na base, porque pasta é jeito de organizar o que é seu
const botaoPasta = (c) => c.salvo
  ? `<button class="botao sec pasta-canal ${c.pasta ? "tem" : ""}" data-pasta-de="${esc(c.id)}" data-pasta="${esc(c.pasta || "")}"
      title="${c.pasta ? `Na pasta ${esc(c.pasta)} — clique para trocar` : "Guardar numa pasta"}">${icone("pasta")}${c.pasta ? esc(c.pasta) : ""}</button>`
  : "";

function ligarCartoes(raiz = tela) {
  raiz.querySelectorAll(".salvar").forEach((b) => (b.onclick = async () => {
    const salvo = b.classList.contains("salvo");
    try {
      await api(`/api/ext/salvar/${b.dataset.id}`, { method: salvo ? "DELETE" : "POST" });
      b.classList.toggle("salvo", !salvo); b.classList.toggle("vermelho", salvo);
      b.innerHTML = icone("marcar") + (salvo ? "Salvar" : "Salvo");
      // o botão de pasta nasce e morre junto com o salvar: sem estar na base não há pasta para escolher
      const acoes = b.parentElement;
      acoes.querySelector(".pasta-canal")?.remove();
      if (!salvo) b.insertAdjacentHTML("afterend", botaoPasta({ id: b.dataset.id, salvo: true, pasta: "" }));
    } catch (e) { aviso(porque(e)); }
  }));
}

// escolher a pasta: as que já existem, ou uma nova escrita ali mesmo. Fica num menu em cima do botão, sem sair da lista
async function porNaPasta(alvo, nome) {
  try {
    await api(`/api/salvos/${encodeURIComponent(alvo.dataset.pastaDe)}/pasta`, { method: "POST", body: { pasta: nome } });
    alvo.dataset.pasta = nome;
    alvo.classList.toggle("tem", !!nome);
    alvo.innerHTML = icone("pasta") + (nome ? esc(nome) : "");
    alvo.title = nome ? `Na pasta ${nome} — clique para trocar` : "Guardar numa pasta";
    esquecer("/api/pastas");            // a lista de pastas muda junto: ela sai de quem está guardado
    aviso(nome ? `Guardado na pasta ${nome}.` : "Tirado da pasta.");
  } catch (erro) { aviso(porque(erro)); }
}

document.addEventListener("click", async (e) => {
  const aberto = document.querySelector(".menu-pasta");
  const botao = e.target.closest(".pasta-canal");
  const opcao = e.target.closest(".menu-pasta [data-por]");
  if (opcao) {
    const alvo = aberto._botao;
    aberto.remove();
    await porNaPasta(alvo, opcao.dataset.por);
    return;
  }
  if (aberto && !e.target.closest(".menu-pasta")) aberto.remove();
  if (!botao) return;
  e.preventDefault(); e.stopPropagation();
  const { pastas: lista } = await pastas();
  const atual = botao.dataset.pasta || "";
  const menu = document.createElement("div");
  menu.className = "menu-bloq menu-pasta";
  menu.innerHTML = `<small>Guardar na pasta:</small>
    ${lista.map((x) => `<button data-por="${esc(x.nome)}" class="${x.nome === atual ? "marcada" : ""}">${esc(x.nome)} <span class="n">${x.canais}</span></button>`).join("")}
    <form class="pasta-nova"><input placeholder="Pasta nova…" maxlength="40" aria-label="Nome da pasta nova"><button class="botao sec">Criar</button></form>
    ${atual ? '<button data-por="">Tirar da pasta</button>' : ""}`;
  menu._botao = botao;
  document.body.appendChild(menu);
  menu.querySelector(".pasta-nova").onsubmit = async (ev) => {
    ev.preventDefault();
    const nome = ev.target.querySelector("input").value.trim();
    if (!nome) return;
    menu.remove();
    await porNaPasta(botao, nome);
  };
  const r = botao.getBoundingClientRect();
  menu.style.left = Math.max(8, Math.min(window.innerWidth - 250, r.left + window.scrollX)) + "px";
  menu.style.top = r.bottom + window.scrollY + 6 + "px";
  menu.querySelector(".pasta-nova input").focus();
});

function grafico(pontos, campo) {
  const p = pontos.filter((x) => x[campo] != null);
  if (p.length < 2) return '<p class="linha-sub">O gráfico aparece depois de alguns dias: o canal é medido de novo uma vez por dia.</p>';
  const max = Math.max(...p.map((x) => x[campo])), min = Math.min(...p.map((x) => x[campo]));
  const xy = p.map((x, i) => `${(i / (p.length - 1)) * 600},${85 - ((x[campo] - min) / Math.max(1, max - min)) * 75}`);
  return `<svg class="grafico" viewBox="0 0 600 90" preserveAspectRatio="none"><polygon class="area" points="0,90 ${xy.join(" ")} 600,90"/><polyline points="${xy.join(" ")}"/></svg>
    <p class="linha-sub">${num(p[0][campo])} → ${num(p[p.length - 1][campo])} inscritos em ${p.length} dias</p>`;
}

// ---------------------------------------------------------------- filtros: só de escolher

// cada filtro: [chave, texto da opção "qualquer" (vazio = sem essa opção), [[valor, texto]...]]
function selects(defs, f) {
  // um valor que não está mais entre as opções (nicho que sumiu, opção tirada) aparecia como "Todos" mas
  // continuava filtrando: volta para o "qualquer" (ou a primeira opção), o mesmo que a tela mostra
  defs.forEach(([k, vazio, ops]) => {
    const vale = (f[k] === "" || f[k] == null) ? !!vazio : ops.some(([v]) => String(v) === String(f[k]));
    if (!vale) f[k] = vazio ? "" : String(ops[0]?.[0] ?? "");
  });
  // o botão nasce escondido: quem decide se ele aparece é o ligarSelects, logo abaixo, que conhece o padrão
  return `<div class="selects">${defs.map(([k, vazio, ops]) => `<select data-f="${k}" class="${f[k] !== "" && f[k] != null && k !== "ordem" && vazio ? "ligado" : ""}">
    ${vazio ? `<option value="">${vazio}</option>` : ""}${ops.map(([v, t]) => `<option value="${esc(v)}" ${String(f[k]) === String(v) ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>`).join("")}
    <button class="limpar" type="button" title="Desfaz as suas escolhas e devolve a tela como ela abre" hidden>voltar ao padrão</button></div>`;
}
// ---------------------------------------------------------------- o trilho: escolher o número arrastando
// No lugar de um select com três opções, a escala inteira à vista: a pessoa sente onde está e até onde dá para ir.
// Os degraus são nomeados (o valor vai para o recorte como qualquer filtro), e embaixo cabe o aviso do piso —
// o mínimo que as outras regras já impõem, para ninguém ficar arrastando um filtro que já está decidido.
function trilho(chave, rotulo, degraus, f) {
  const i = Math.max(0, degraus.findIndex(([v]) => String(v) === String(f[chave] ?? "")));
  return `<label class="trilho" data-trilho="${chave}">
    <span class="trilho-cab"><span>${esc(rotulo)}</span><b class="trilho-valor">${esc(degraus[i][1])}</b></span>
    <input type="range" min="0" max="${degraus.length - 1}" step="1" value="${i}" aria-label="${esc(rotulo)}">
    <small class="trilho-piso" hidden></small></label>`;
}

function ligarTrilhos(raiz, f, degrausDe, aoMudar) {
  const pintar = () => raiz.querySelectorAll("[data-trilho]").forEach((l) => {
    const degraus = degrausDe(l.dataset.trilho);
    const i = Math.max(0, degraus.findIndex(([v]) => String(v) === String(f[l.dataset.trilho] ?? "")));
    l.querySelector("input").value = i;
    l.querySelector(".trilho-valor").textContent = degraus[i][1];
  });
  raiz.querySelectorAll("[data-trilho]").forEach((l) => {
    const k = l.dataset.trilho, degraus = degrausDe(k);
    const entrada = l.querySelector("input"), valor = l.querySelector(".trilho-valor");
    entrada.oninput = () => { valor.textContent = degraus[+entrada.value][1]; };   // arrastando, só o rótulo anda
    entrada.onchange = () => { f[k] = String(degraus[+entrada.value][0]); aoMudar(); };
  });
  return pintar;
}

// o piso que o servidor aplicou por cima do que foi pedido, dito no próprio trilho
function avisarPiso(raiz, chave, aplicado, pedido, texto) {
  const aviso = raiz.querySelector(`[data-trilho="${chave}"] .trilho-piso`);
  if (!aviso) return;
  const vale = aplicado > (Number(pedido) || 0);
  aviso.hidden = !vale;
  if (vale) aviso.textContent = texto(aplicado);
}

// `manter`: as chaves que o "voltar ao padrão" não mexe (o que a pessoa digitou, como a busca)
function ligarSelects(raiz, f, padrao, aoMudar, manter = []) {
  const pintar = (s) => s.classList.toggle("ligado", s.value !== "" && s.dataset.f !== "ordem" && !!s.querySelector('option[value=""]'));
  const acompanhar = () => { recorteParaOEndereco(f, padrao); marcarBotaoPadrao(raiz, f, padrao, manter); };
  raiz.querySelectorAll(".selects select").forEach((s) => (s.onchange = () => { f[s.dataset.f] = s.value; pintar(s); acompanhar(); aoMudar(); }));
  const limpar = raiz.querySelector(".selects .limpar");
  if (limpar) limpar.onclick = () => {
    const meu = Object.fromEntries(manter.map((k) => [k, f[k]]));
    Object.assign(f, padrao, meu);
    raiz.querySelectorAll(".selects select").forEach((s) => { s.value = f[s.dataset.f] ?? ""; pintar(s); });
    acompanhar(); aoMudar();
  };
  acompanhar();   // valor que a tela corrigiu (nicho que sumiu) não fica no endereço filtrando escondido
  return acompanhar;
}

const TAMANHOS = { pequeno: { inscritos_max: 10000 }, medio: { inscritos_min: 10000, inscritos_max: 100000 }, grande: { inscritos_min: 100000 } };
const paraApi = (f) => ({ visao: f.visao, busca: f.busca, nicho: f.nicho, fase: f.fase, pasta: f.pasta,
  ...(TAMANHOS[f.tamanho] || {}), inscritos_max: f.inscritos_max, media_min: f.media_min,
  idade_max: f.etapa && ETAPAS_DIAS[f.etapa] ? emMeses(ETAPAS_DIAS[f.etapa][1]) : f.idade,
  idade_min: f.etapa && ETAPAS_DIAS[f.etapa] ? emMeses(ETAPAS_DIAS[f.etapa][0]) : "",
  achado_dias: f.achado, rosto: f.rosto, ordem: f.ordem, sentido: f.sentido,
  salvos: f.base === "salvos" ? "1" : "", acharam: f.base === "acharam" ? "1" : "" });

// ---------------------------------------------------------------- entrar

function entrar(criar) {
  tela.innerHTML = `<form class="form cartao" id="f">
    <div class="marca"><span class="ponto"></span><b>${esc(NOME)}</b></div>
    ${criar ? '<input name="nome" placeholder="Seu nome">' : ""}
    <input name="email" type="email" placeholder="E-mail" required autocomplete="email">
    <input name="senha" type="password" placeholder="Senha${criar ? " (8 ou mais letras)" : ""}" required autocomplete="${criar ? "new-password" : "current-password"}">
    <button class="botao">${criar ? "Criar conta" : "Entrar"}</button>
    <span class="sub" style="text-align:center">${criar ? 'Já tem conta? <a href="#/entrar" style="color:var(--verde)">Entrar</a>' : 'Primeira vez? <a href="#/criar" style="color:var(--verde)">Criar conta</a>'}</span></form>`;
  const convite = new URLSearchParams(location.hash.split("?")[1] || "").get("convite") || "";
  if (criar && convite) document.getElementById("f").insertAdjacentHTML("beforeend", '<span class="sub" style="text-align:center;color:var(--verde)">Você foi convidado. Crie a sua conta.</span>');
  mostrarVitrine();
  document.getElementById("f").onsubmit = async (e) => {
    e.preventDefault();
    try { await api(criar ? "/api/cadastro" : "/api/entrar", { method: "POST", body: { ...Object.fromEntries(new FormData(e.target)), convite } });
      esquecer();   // daqui em diante quem pergunta é outra pessoa
      EU = await api("/api/eu"); PREFS = (await api("/api/prefs")).prefs; location.hash = "#/trabalho"; }
    catch (erro) { aviso(porque(erro)); }
  };
}

// ---------------------------------------------------------------- a vitrine: o que o Radar já achou, antes de entrar
// Os números e alguns canais de verdade embaixo do formulário: quem chega vê o que a ferramenta faz sem precisar
// de conta. Os canais vêm da régua do "na hora de copiar", nenhum escolhido a dedo, e nada aqui é de usuário.

// quem usou, com o print do Studio. Nada é escrito aqui: os depoimentos entram pela Administração, um a um, e
// enquanto não houver nenhum esta parte da vitrine simplesmente não existe
function depoimentos(lista) {
  if (!lista || !lista.length) return "";
  return `<h2>Quem usou</h2>
    <p class="linha-sub">Com o print do YouTube Studio de cada um.</p>
    <div class="depoimentos">${lista.map((d) => `<figure class="depoimento">
      ${d.print ? `<a href="${esc(d.print)}" target="_blank" rel="noopener"><img src="${esc(d.print)}" alt="Print do YouTube Studio de ${esc(d.nome)}" loading="lazy"></a>` : ""}
      <figcaption>
        ${d.resultado ? `<b class="resultado">${esc(d.resultado)}</b>` : ""}
        ${d.texto ? `<blockquote>${esc(d.texto)}</blockquote>` : ""}
        <span class="quem">${esc(d.nome)}${d.canal ? ` · ${esc(d.canal)}` : ""}</span>
      </figcaption></figure>`).join("")}</div>`;
}

async function mostrarVitrine() {
  const v = await api("/api/vitrine").catch(() => null);
  if (!v || !["entrar", "criar"].includes(rotaAtual())) return;   // a pessoa já saiu da tela enquanto carregava
  const numeros = [
    [v.canais, "canais no Radar"], [v.nichos, "nichos"], [v.estouraram, "vídeos que estouraram"],
    [v.videos, "vídeos lidos"],
  ].filter(([n]) => n);
  tela.insertAdjacentHTML("beforeend", `<section class="vitrine">
    <div class="vitrine-isca">
      <h2>Comece pela extensão: ela é de graça</h2>
      <p>Com a conta grátis você instala a <b>extensão do Chrome</b>, e ela escreve em cima de cada vídeo do YouTube
        quantas vezes ele passou do normal do canal, as views por hora e os inscritos — enquanto você navega, sem
        gastar a cota da API. O painel, com a lista de canais e as perguntas prontas, vem depois.</p>
      <p class="linha-sub">A conta é preciso ter: é por ela que a extensão sabe o que você já salvou. O preço dos
        planos aparece lá dentro, depois do cadastro.</p>
    </div>
    <div class="vitrine-numeros">${numeros.map(([n, t]) => `<div><b>${num(n)}</b><span>${t}</span></div>`).join("")}
      ${v.novos_semana ? `<div class="novos"><b>+${num(v.novos_semana)}</b><span>entraram esta semana</span></div>` : ""}</div>
    ${v.exemplos && v.exemplos.length ? `<h2>Alguns canais que o Radar achou</h2>
      <p class="linha-sub">Pela mesma régua do painel: muita view por vídeo, com peso para canal novo e crescendo. Nenhum escolhido a dedo.</p>
      <div class="vitrine-canais">${v.exemplos.map((c) => `<article class="vitrine-canal">
        <div class="vitrine-capas">${c.capas.map((id) => `<img src="https://i.ytimg.com/vi/${esc(id)}/mqdefault.jpg" alt="" loading="lazy" referrerpolicy="no-referrer">`).join("")}</div>
        <div class="vitrine-cab"><img class="avatar" src="${esc(c.foto)}" alt="" loading="lazy" referrerpolicy="no-referrer">
          <div><b>${esc(c.nome)}</b>${c.raridade && SELOS[c.raridade] ? `<span class="tag ${esc(c.raridade)}">${SELOS[c.raridade]}</span>` : ""}
            <span class="sub">${esc(c.nicho || "")}</span></div></div>
        <div class="vitrine-numeros-canal"><span><b>${num(c.media)}</b> por vídeo</span><span><b>${num(c.inscritos)}</b> inscritos</span>${c.dias ? `<span><b>${num(c.dias)}</b> dias de vida</span>` : ""}</div>
      </article>`).join("")}</div>` : ""}
    ${depoimentos(v.depoimentos)}
  </section>`);
}

// ---------------------------------------------------------------- Trabalho: a ideia, o roteiro pelo Claude e a fábrica

function gerenciarProjetos(caixa, projetos, depois) {
  caixa.innerHTML = `<div class="bloco" style="margin-top:6px"><h3>Agentes de roteiro</h3>
    <p class="sub">Cada agente guarda o jeito de escrever de um canal (tom, público, como abrir e fechar). Cole aqui as instruções de um projeto do claude.ai: vão junto em todo roteiro feito com esse agente.</p>
    ${projetos.map((p) => `<div class="titulo-linha"><span class="t"><b>${esc(p.nome)}</b><small>${esc(p.instrucoes.slice(0, 120))}${p.instrucoes.length > 120 ? "…" : ""}</small></span>
      <button class="botao sec editar-projeto" data-id="${p.id}">Editar</button><button class="botao sec apagar-projeto" data-id="${p.id}">×</button></div>`).join("")}
    <input id="p-nome" placeholder="Nome do agente (ex.: canal de animais)"><input type="hidden" id="p-id">
    <input id="p-ideal" placeholder="Ideal para… (opcional: aparece embaixo do estilo na Nova produção)">
    <textarea id="p-instrucoes" rows="6" placeholder="Instruções: tom de voz, público, estrutura, o que evitar…"></textarea>
    <button class="botao" id="p-salvar" style="justify-self:start">Salvar agente</button></div>`;
  caixa.querySelectorAll(".editar-projeto").forEach((b) => (b.onclick = () => {
    const p = projetos.find((x) => x.id === +b.dataset.id);
    caixa.querySelector("#p-id").value = p.id; caixa.querySelector("#p-nome").value = p.nome; caixa.querySelector("#p-instrucoes").value = p.instrucoes;
    caixa.querySelector("#p-ideal").value = p.ideal_para || "";
  }));
  caixa.querySelectorAll(".apagar-projeto").forEach((b) => (b.onclick = async () => {
    if (!confirm("Apagar este agente de roteiro?")) return;
    await api(`/api/projetos/${b.dataset.id}`, { method: "DELETE" }); depois();
  }));
  caixa.querySelector("#p-salvar").onclick = async () => {
    try {
      await api("/api/projetos", { method: "POST", body: { id: caixa.querySelector("#p-id").value || null,
        nome: caixa.querySelector("#p-nome").value, instrucoes: caixa.querySelector("#p-instrucoes").value,
        ideal_para: caixa.querySelector("#p-ideal").value } });
      aviso("Agente salvo."); depois();
    } catch (e) { aviso(porque(e)); }
  };
}

// O Produzir, em 4 passos e centralizado (pedidos do usuário em 2026-10-15: "passo a passo, pra não ficar tão
// bagunçado"; "tudo centralizado bonitinho"; "no primeiro passo o canal, que você escolhe e já configura tudo"; "retirar
// a parte de fazer a thumbnail, só a thumbnail do lado para pegar a referência"). Ao lado, o ponto de partida.
const PASSOS_ROTEIRO = [
  ["Canal e conteúdo", "o ponto de partida"], ["Roteiro", "o Claude escreve"], ["Revisão", "confira e envie"],
];

async function trabalho() {
  const preset = guardado("roteiro-preset", {});
  guardar("roteiro-preset", {});
  // a extensão abre #/trabalho?ref=ID&titulo=... ("Levar ao Roteiro" no painel do vídeo do YouTube)
  const daExtensao = new URLSearchParams(location.hash.split("?")[1] || "");
  if (/^[\w-]{11}$/.test(daExtensao.get("ref") || "")) { preset.link = linkVideo(daExtensao.get("ref")); preset.titulo = daExtensao.get("titulo") || ""; }
  const [{ projetos }, fab, { roteiros }, prod] = await Promise.all([api("/api/projetos"), api("/api/fabrica"), api("/api/roteiros"),
    api("/api/producoes").catch(() => null)]);
  const agentes = projetos;
  const E = { passo: 0, link: preset.link || "", titulo: preset.titulo || "", ref: null, canal: CANAL_ATUAL || "", cfg: null,
    agente: "", lingua: "português", minutos: 8, obs: "", r: null, perfil: "", quem: "", rascunho: "", ritmo: null, ppm: 150 };
  const perfilDireto = () => (fab.perfis.includes(E.perfil) ? E.perfil : fab.perfis.includes("documentario") ? "documentario" : fab.perfis[0] || "");
  // o canal vai junto no roteiro, para cada vídeo feito mostrar de qual canal é
  const canalDoVideo = () => ({ canal_id: E.canal, canal_titulo: ((MEUS || []).find((c) => c.id === E.canal) || {}).titulo || "" });
  // o ritmo real da voz do canal (o ajuste do tempo): quantas palavras por minuto pedir
  const carregarRitmo = async () => {
    try { E.ritmo = await api("/api/roteiros/ritmo?" + consulta({ perfil: perfilDireto(), lingua: E.lingua })); E.ppm = E.ritmo.ppm; } catch { E.ritmo = null; E.ppm = 150; }
  };
  const produzindo = prod ? prod.andamento.filter((p) => p.rodando).length : 0;

  tela.innerHTML = `<div class="produzir">
    <header class="produzir-cab"><div><h1>Produza seu próximo vídeo</h1><p>Escolha o canal, cole a referência e o Claude escreve. A fábrica narra, monta e entrega o MP4.</p></div></header>
    <div class="produzir-numeros">
      <div><small>Fábrica</small><b class="${fab.conectada && prod ? "verde" : ""}">${fab.conectada && prod ? "Ligada" : "Desligada"}</b><span>editor na porta 8080</span></div>
      <div><small>Produzindo agora</small><b>${produzindo}</b><span>${produzindo === 1 ? "vídeo" : "vídeos"} na fábrica</span></div>
      <div><small>Vídeos prontos</small><b>${prod ? prod.prontos.length : "—"}</b><span>em Resultados</span></div>
      <div><small>Roteiros</small><b>${roteiros.length}</b><span>escritos pelo Claude</span></div>
    </div>
    <nav class="passos-roteiro" id="rt-passos"></nav>
    <div class="rt-grade"><section class="rt-corpo" id="rt-corpo"></section><aside class="rt-lado" id="rt-lado"></aside></div>
    <div class="rt-navega"><span class="sub" id="rt-etapa"></span><button class="botao sec" id="rt-voltar">← Voltar</button><button class="botao vermelho" id="rt-proximo"></button></div>
    ${roteiros.length ? `<details class="rt-feitos"><summary>Roteiros feitos (${roteiros.length})</summary><div class="lista-titulos">${roteiros.map((r, i) => `<div class="titulo-linha">
      ${r.thumbnail_url ? `<img src="${esc(r.thumbnail_url)}" alt="" style="width:80px;border-radius:6px;flex:none">` : ""}
      <span class="t"><b>${esc(r.titulo)}</b><small>${r.palavras} palavras · ${new Date(r.criado).toLocaleString("pt-BR")}${r.fabrica ? ` · <span class="ok-fabrica">na fábrica: ${esc(r.fabrica.projeto)}</span>` : ""}</small></span>
      <button class="botao sec abrir" data-i="${i}">Abrir</button></div>`).join("")}</div></details>` : ""}
  </div>`;
  const $ = (id) => document.getElementById(id);

  const carregarRef = async () => {
    const vid = idDoVideo(E.link);
    if (!vid) { E.ref = null; return; }
    try { E.ref = await api("/api/titulo-do-video?" + consulta({ link: E.link })); } catch { E.ref = { id: vid, titulo: "" }; }
  };
  const carregarCanal = async () => {
    if (!E.canal) { E.cfg = null; return; }
    E.cfg = await api(`/api/producao/${encodeURIComponent(E.canal)}`);
    E.agente = String(E.cfg.projeto_roteiro_id || ""); E.lingua = E.cfg.lingua || E.lingua;
    E.minutos = +E.cfg.minutos || E.minutos; E.perfil = E.cfg.perfil || "";
  };

  const faixa = () => {
    $("rt-passos").innerHTML = PASSOS_ROTEIRO.map(([nome, sub], i) => `<button class="passo-rt ${i < E.passo ? "feito" : i === E.passo ? "atual" : ""}" data-i="${i}" ${i > E.passo ? "disabled" : ""}>
      <span class="num">${i < E.passo ? "✓" : i + 1}</span><span class="txt"><b>${nome}</b><small>${sub}</small></span></button>`).join("");
    $("rt-passos").querySelectorAll(".passo-rt:not([disabled])").forEach((b) => (b.onclick = () => ir(+b.dataset.i)));
  };
  // ao lado: o ponto de partida (a thumbnail da referência, para copiar) e o que já foi escolhido
  const lado = () => {
    const vid = idDoVideo(E.link), canal = (MEUS || []).find((c) => c.id === E.canal);
    $("rt-lado").innerHTML = `<h3>📌 Seu ponto de partida</h3>
      ${vid ? `<img class="thumb-ref" src="/api/thumb/imagem/${esc(vid)}" alt="">
        <div class="linha" style="gap:6px"><button class="botao sec" id="rt-copiar-thumb">Copiar a thumbnail</button><a class="botao sec" href="/api/thumb/imagem/${esc(vid)}" download="thumbnail-referencia.jpg">Baixar</a></div>
        ${E.ref && E.ref.titulo ? `<small class="sub">${esc(E.ref.titulo)}${E.ref.views ? ` · ${num(E.ref.views)} views` : ""}</small>` : ""}`
        : '<div class="thumb-vazia">A thumbnail do vídeo de referência aparece aqui.</div>'}
      <h3>Configuração deste vídeo</h3>
      <small class="sub">${esc(canal ? canal.titulo : "Nenhum canal escolhido")}</small>
      <dl class="rt-config">
        <dt>Título</dt><dd>${esc(E.titulo || "—")}</dd>
        <dt>Voz</dt><dd>${esc((E.cfg && E.cfg.voz) || "—")}</dd>
        <dt>Agente</dt><dd>${esc((agentes.find((a) => String(a.id) === E.agente) || {}).nome || "Agente padrão")}</dd>
        <dt>Língua</dt><dd>${esc(E.lingua)}</dd>
        <dt>Tempo</dt><dd>${E.minutos} min</dd>
        <dt>Roteiro</dt><dd>${E.r ? `${E.r.roteiro.split(/\s+/).filter(Boolean).length} palavras` : "—"}</dd>
      </dl>`;
    const copiar = $("rt-copiar-thumb");
    if (copiar) copiar.onclick = async () => {
      try { await copiarImagem(`/api/thumb/imagem/${vid}`); copiar.textContent = "Copiada ✓"; } catch { aviso("O navegador não deixou copiar. Use o Baixar."); }
    };
  };

  const passos = [
    // 1. o conteúdo (o link e o título, o mais importante) e o canal, em cartões, que configura o resto
    () => {
      const canais = MEUS || [];
      $("rt-corpo").innerHTML = `<h2>Qual vídeo vamos fazer?</h2>
        <p class="sub">Cole o vídeo de referência e o título. Depois escolha o canal: ele traz a voz, a língua, o agente e o tempo. <b>Sem link?</b> No próximo passo você cola o seu roteiro.</p>
        <div class="rt-conteudo">
          <label class="campo"><span>Link do vídeo de referência <em class="opcional">opcional</em></span><input id="rt-link" placeholder="https://www.youtube.com/watch?v=…" value="${esc(E.link)}"></label>
          <label class="campo"><span>Título que vamos usar</span><input id="rt-titulo" placeholder="O título do seu vídeo" value="${esc(E.titulo)}"></label>
          ${E.ref && E.ref.titulo ? `<button class="link-editar" id="rt-usar-titulo" style="margin:0">usar o título da referência: “${esc(E.ref.titulo)}”</button>` : ""}</div>
        <h3 class="rt-sub">Para qual canal?</h3>
        <div class="canais-op">${canais.map((c) => `<button class="canal-op ${c.id === E.canal ? "marcado" : ""}" data-canal="${esc(c.id)}">
            <img src="${esc(c.foto)}" alt="" referrerpolicy="no-referrer"><span><small>Canal</small><b>${esc(c.titulo)}</b>
            <em data-resumo="${esc(c.id)}">${c.id === E.canal && E.cfg ? esc([E.cfg.voz, E.cfg.lingua].filter(Boolean).join(" · ")) : "&nbsp;"}</em></span></button>`).join("")}
          <button class="canal-op novo" id="rt-canal-novo"><span class="mais">＋</span><span><small>Canal</small><b>Adicionar canal</b><em>pelo @ do canal</em></span></button></div>
        <div id="rt-novo" class="conectar" hidden><input id="rt-novo-ref" placeholder="@docanal ou link do canal"><button class="botao" id="rt-novo-ok">Adicionar</button></div>
        <div id="rt-config-canal"></div>`;
      const guardarCampos = () => { E.link = $("rt-link").value.trim(); E.titulo = $("rt-titulo").value; };
      $("rt-link").onchange = async () => { guardarCampos(); E.quem = ""; await carregarRef(); passos[0](); lado(); };
      $("rt-titulo").oninput = () => { E.titulo = $("rt-titulo").value; lado(); };
      const usar = $("rt-usar-titulo");
      if (usar) usar.onclick = () => { E.titulo = E.ref.titulo; $("rt-titulo").value = E.titulo; lado(); };
      // o que cada canal já tem (voz e língua), embaixo do nome
      canais.forEach((c) => api(`/api/producao/${encodeURIComponent(c.id)}`).then((p) => {
        const el = $("rt-corpo").querySelector(`[data-resumo="${CSS.escape(c.id)}"]`);
        if (el) el.textContent = p.salvo ? [p.voz, p.lingua].filter(Boolean).join(" · ") : "ainda não configurado";
      }).catch(() => {}));
      $("rt-corpo").querySelectorAll(".canal-op[data-canal]").forEach((b) => (b.onclick = async () => {
        guardarCampos(); E.canal = b.dataset.canal; CANAL_ATUAL = E.canal; await carregarCanal(); passos[0](); lado();
      }));
      $("rt-canal-novo").onclick = () => { $("rt-novo").hidden = false; $("rt-novo-ref").focus(); };
      $("rt-novo-ok").onclick = (e) => carregando(e.currentTarget, "Medindo o canal…", async () => {
        guardarCampos();
        const { canal: c } = await api("/api/perfil/canais", { method: "POST", body: { ref: $("rt-novo-ref").value.trim() } });
        await meusCanais(true); E.canal = c.id; CANAL_ATUAL = c.id; await carregarCanal(); passos[0](); lado();
      });
      // o canal escolhido aparece configurado; o que ainda não foi configurado pergunta aqui mesmo
      if (E.canal) formProducao($("rt-config-canal"), E.canal, async () => { await carregarCanal(); lado(); });
      return () => {
        guardarCampos(); E.titulo = E.titulo.trim();
        if (!E.titulo) return "Escreva o título que vamos usar.";
        return E.canal ? "" : "Escolha o canal.";
      };
    },
    // 3. o roteiro: o Claude escreve ou a pessoa cola o dela (pedido do usuário em 2026-10-18: sem link, já vai
    // direto para colar o roteiro)
    () => {
      const editor = () => {
        $("rt-corpo").innerHTML = `<h2>O roteiro</h2><p class="sub">Leia, corrija o que quiser e salve. Só o texto que a voz fala.</p>
          <textarea class="roteiro" id="rt-texto">${esc(E.r.roteiro)}</textarea>
          <div class="linha"><span class="sub" id="rt-conta"></span><button class="botao sec" id="rt-copiar">Copiar</button>
            <button class="botao sec" id="rt-salvar">Salvar alterações</button><button class="botao sec" id="rt-refazer">${E.r.manual ? "Trocar o roteiro" : "Escrever de novo"}</button></div>`;
        const contar = () => { const n = $("rt-texto").value.split(/\s+/).filter(Boolean).length; $("rt-conta").textContent = `${n} palavras · uns ${Math.max(1, Math.round(n / E.ppm))} minutos de narração`; };
        contar();
        $("rt-texto").oninput = () => { E.r.roteiro = $("rt-texto").value; contar(); };
        $("rt-copiar").onclick = (e) => { navigator.clipboard.writeText($("rt-texto").value); e.target.textContent = "Copiado ✓"; };
        $("rt-salvar").onclick = (e) => carregando(e.currentTarget, "Salvando…", async () => { await salvar(); aviso("Roteiro salvo."); });
        $("rt-refazer").onclick = () => { E.r = null; passos[1](); lado(); };
      };
      if (E.r) { editor(); return () => (salvar(), ""); }

      if (!E.quem) E.quem = E.link ? "claude" : "manual";
      const escolhaQuem = `<div class="painel-modos quem-escreve">
          <button class="${E.quem === "claude" ? "ativo" : ""}" data-quem="claude">✍️ O Claude escreve</button>
          <button class="${E.quem === "manual" ? "ativo" : ""}" data-quem="manual">📋 Eu colo o meu roteiro</button></div>`;
      const ligarQuem = () => $("rt-corpo").querySelectorAll("[data-quem]").forEach((b) => (b.onclick = () => { E.quem = b.dataset.quem; passos[1](); }));

      if (E.quem === "manual") {
        $("rt-corpo").innerHTML = `<h2>Cole o seu roteiro</h2>${escolhaQuem}
          <p class="sub">${E.link ? "Você escreveu o roteiro: ele vai com o título" : "Sem vídeo de referência: o roteiro vai com o título"} <b>“${esc(E.titulo)}”</b>. Só o texto que a voz fala, sem títulos de parte.</p>
          <textarea class="roteiro" id="rt-manual" placeholder="Cole aqui o roteiro inteiro…">${esc(E.rascunho || "")}</textarea>
          <div class="linha"><span class="sub" id="rt-manual-conta">0 palavras</span>
            <button class="botao vermelho grande" id="rt-usar-manual">Usar este roteiro →</button></div>`;
        ligarQuem();
        const contar = () => {
          E.rascunho = $("rt-manual").value;
          const n = E.rascunho.split(/\s+/).filter(Boolean).length;
          $("rt-manual-conta").textContent = `${n} palavras · uns ${Math.max(n ? 1 : 0, Math.round(n / E.ppm))} minutos de narração${E.ritmo && E.ritmo.medidos ? " (no ritmo real da voz)" : ""}`;
        };
        $("rt-manual").oninput = contar; contar();
        $("rt-usar-manual").onclick = (e) => carregando(e.currentTarget, "Guardando o roteiro…", async () => {
          E.r = await api("/api/roteiros/manual", { method: "POST", body: { titulo: E.titulo, roteiro: $("rt-manual").value, link: E.link, minutos: E.minutos, lingua: E.lingua, ...canalDoVideo() } });
          E.rascunho = ""; ir(2); window.scrollTo({ top: 0, behavior: "smooth" });
        });
        return () => "Clique em “Usar este roteiro” primeiro.";
      }

      // revisar antes ou mandar direto (pedido do usuário em 2026-10-18); a escolha fica guardada para a próxima vez
      const podeDireto = fab.conectada && EU.admin;
      let modo = podeDireto ? guardado("roteiro-modo", "revisar") : "revisar";
      const alvo = E.minutos * ((E.ritmo && E.ritmo.ppm_alvo) || E.ppm);
      const ac = (E.ritmo && E.ritmo.acerto) || {};
      const sinal = (x) => (x > 0 ? "+" : "") + String(x).replace(".", ",");
      const placar = ac.total
        ? `<div class="ritmo-placar ${ac.dentro === ac.total ? "bom" : ac.dentro ? "meio" : "ruim"}">🎯 <b>${ac.dentro} de ${ac.total}</b> dos últimos vídeos desta voz ficaram dentro de ${String(ac.margem).replace(".", ",")} min do tempo pedido${ac.erro_medio != null ? ` · erro médio <b>${sinal(ac.erro_medio)} min</b>` : ""}${ac.pior && !ac.pior.dentro ? ` · pior: pediu ${ac.pior.pedido_min} e saiu ${String(ac.pior.entregue_min).replace(".", ",")} min` : ""}</div>`
        : "";
      $("rt-corpo").innerHTML = `<h2>Agora o Claude escreve</h2>${escolhaQuem}
        <p class="sub">${E.link ? "Ele lê a transcrição da referência e escreve" : "Sem vídeo de referência, ele escreve a partir do título"} um roteiro limpo, só o texto para narrar, com o agente e o tempo escolhidos. Grátis pela sua assinatura do Claude.</p>
        <div class="ritmo-linha ${E.ritmo && E.ritmo.medidos ? "ajustado" : ""}">⏱ ${E.ritmo && E.ritmo.medidos
          ? `<span><b>Tempo ajustado:</b> esta voz fala <b>${E.ppm} palavras por minuto</b> (medido em ${E.ritmo.medidos} ${E.ritmo.medidos === 1 ? "vídeo entregue" : "vídeos entregues"}). Para ${E.minutos} min, o Claude mira <b>${alvo.toLocaleString("pt-BR")} palavras</b>${E.ritmo.ppm_alvo && E.ritmo.ppm_alvo !== E.ppm ? " (já descontando o quanto ele costuma escrever a mais)" : ""}.</span><button class="link-editar" id="rt-por-que">por quê?</button>`
          : `<span>Para ${E.minutos} min, o Claude mira ${alvo.toLocaleString("pt-BR")} palavras. Quando a fábrica entregar os vídeos desta voz, o Radar mede o tempo real e <b>ajusta sozinho</b>.</span>`}</div>${placar}
        <h3 class="rt-sub">Quando o roteiro ficar pronto…</h3>
        <div class="modo-op">
          <button class="modo ${modo === "revisar" ? "marcado" : ""}" data-modo="revisar"><span class="ic">👀</span><b>Quero revisar antes</b><small>Você lê, corrige e só depois manda para a fábrica.</small></button>
          <button class="modo ${modo === "direto" ? "marcado" : ""}" data-modo="direto" ${podeDireto ? "" : "disabled"}><span class="ic">🚀</span><b>Enviar direto para a fábrica</b>
            <small>${podeDireto ? `Assim que ficar pronto, vira projeto na fábrica com a voz <b>${esc(perfilDireto())}</b>. Produzir ainda pede o seu sim.` : fab.conectada ? "Só a administração manda para a fábrica." : "A fábrica não está ligada a este Radar."}</small></button>
        </div>
        <p class="sub aviso-notif">🔔 Você recebe uma <b>notificação no computador</b> quando o roteiro ficar pronto. Pode sair desta página.</p>
        <button class="botao vermelho grande" id="rt-escrever" style="justify-self:start">✍️ Escrever o roteiro com o Claude</button>
        <div id="rt-escrevendo"></div>`;
      ligarQuem();
      const porQue = $("rt-por-que");
      if (porQue) porQue.onclick = () => explicarAjusteTempo(E.ritmo, E.minutos);
      $("rt-corpo").querySelectorAll(".modo:not([disabled])").forEach((b) => (b.onclick = () => {
        modo = b.dataset.modo; guardar("roteiro-modo", modo);
        $("rt-corpo").querySelectorAll(".modo").forEach((x) => x.classList.toggle("marcado", x === b));
      }));
      $("rt-escrever").onclick = async (e) => {
        const botao = e.currentTarget; botao.disabled = true;
        pedirPermissaoNotificacao();
        // a primeira vez que o ajuste do tempo é usado, o Radar explica o que fez (pedido do usuário em 2026-10-18)
        if (E.ritmo && E.ritmo.medidos && !guardado("ajuste-tempo-explicado", false)) explicarAjusteTempo(E.ritmo, E.minutos);
        try {
          const direto = modo === "direto";
          const { tarefa } = await api("/api/roteiros", { method: "POST", body: { titulo: E.titulo, link: E.link, minutos: E.minutos, lingua: E.lingua,
            projeto_id: E.agente, observacoes: E.obs, enviar_direto: direto, perfil: perfilDireto(), ...canalDoVideo() } });
          vigiarRoteiro(tarefa, E.titulo);
          $("rt-corpo").querySelectorAll(".modo, [data-quem]").forEach((x) => (x.disabled = true));
          for (;;) {
            await new Promise((r) => setTimeout(r, 2000));
            if (!$("rt-escrevendo")) return;          // saiu da página: a notificação avisa
            const t = await api(`/api/roteiros/tarefa/${tarefa}`);
            if (t.estado === "rodando") { botao.textContent = t.passo; continue; }
            if (t.estado === "erro") throw new Error(t.erro);
            E.r = t.resultado;
            if (t.fabrica) { ir(2); mostrarEnviado(t.fabrica); break; }
            if (t.erro_envio) aviso("O roteiro ficou pronto, mas não foi para a fábrica: " + t.erro_envio);
            editor(); lado(); break;
          }
        } catch (erro) { aviso(porque(erro)); botao.disabled = false; botao.textContent = "✍️ Escrever o roteiro com o Claude"; }
      };
      return () => "Escreva o roteiro primeiro.";
    },
    // 4. revisão e envio para a fábrica
    () => {
      $("rt-corpo").innerHTML = `<h2>Confira e envie</h2>
        ${fab.conectada ? `<p class="sub">Cria o projeto na fábrica com este roteiro, este título e a voz do canal. <b>Não gasta nada</b>: produzir pede a sua confirmação.</p>
          <label class="campo"><span>Voz (perfil da fábrica)</span><select id="rt-perfil">${fab.perfis.map((p) => `<option ${p === (E.perfil || "documentario") ? "selected" : ""}>${esc(p)}</option>`).join("")}</select></label>
          <button class="botao vermelho grande" id="rt-enviar" style="justify-self:start">🏭 Enviar para a fábrica</button><div id="rt-enviado"></div>`
          : '<p class="sub">A fábrica não está nesta pasta: o Radar precisa estar dentro da pasta da fábrica para enviar.</p>'}`;
      const enviar = $("rt-enviar");
      if (enviar) enviar.onclick = () => carregando(enviar, "Criando o projeto na fábrica…", async () => {
        await salvar();
        mostrarEnviado(await api(`/api/roteiros/${encodeURIComponent(E.r.nome)}/fabrica`, { method: "POST", body: { perfil: $("rt-perfil").value } }));
      });
      return () => "";
    },
  ];
  const mostrarEnviado = (f) => {
    if (!$("rt-enviado")) return;
    if ($("rt-enviar")) $("rt-enviar").hidden = true;
    $("rt-enviado").innerHTML = `<p class="ok-fabrica">Projeto "${esc(f.projeto)}" criado na fábrica.</p>
      ${f.estimativa ? `<pre class="log">${esc(f.estimativa)}</pre>` : ""}
      <div class="linha"><button class="botao vermelho" id="rt-produzir">▶ Produzir agora</button><a class="botao sec" href="#/acompanhar">Acompanhar</a></div>`;
    $("rt-produzir").onclick = (ev) => carregando(ev.currentTarget, "Consultando a fábrica…", async () => {
      if (await produzirNaFabrica(f.projeto, E.titulo)) location.hash = "#/acompanhar";
    });
  };
  const salvar = () => E.r && api(`/api/roteiros/${encodeURIComponent(E.r.nome)}/texto`, { method: "POST", body: { roteiro: E.r.roteiro, titulo: E.titulo } });
  let validar = () => "";
  const ir = (i) => {
    E.passo = i; faixa(); validar = passos[i]() || (() => "");
    $("rt-etapa").textContent = `Etapa ${i + 1} de ${PASSOS_ROTEIRO.length}`;
    $("rt-voltar").hidden = i === 0;
    $("rt-proximo").hidden = i === PASSOS_ROTEIRO.length - 1;
    $("rt-proximo").textContent = i < PASSOS_ROTEIRO.length - 1 ? `${PASSOS_ROTEIRO[i + 1][0]} →` : "";
    lado();
  };
  $("rt-proximo").onclick = async () => {
    const erro = await validar();
    if (erro) return aviso(erro);
    if (E.passo === 0 && E.link && !E.ref) await carregarRef();
    if (E.passo === 0) await carregarRitmo();
    ir(E.passo + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  $("rt-voltar").onclick = () => ir(Math.max(0, E.passo - 1));
  tela.querySelectorAll(".abrir").forEach((b) => (b.onclick = async () => {
    const r = roteiros[+b.dataset.i];
    Object.assign(E, { r, titulo: r.titulo, link: r.link || "", lingua: r.lingua || E.lingua, minutos: r.minutos || E.minutos });
    await Promise.all([carregarRef(), carregarRitmo()]); ir(1); window.scrollTo({ top: 0, behavior: "smooth" });
  }));
  await meusCanais();
  await Promise.all([carregarRef(), carregarCanal()]);
  ir(0);
}

function editorRoteiro(caixa, r, fab) {
  const minutos = (texto) => Math.max(1, Math.round(texto.split(/\s+/).filter(Boolean).length / 150));
  caixa.innerHTML = `
    <div class="passo"><h2><span class="n">2</span>O roteiro</h2>
      <input id="e-titulo" value="${esc(r.titulo)}" title="Título que vai para a fábrica">
      ${r.thumbnail_url ? `<div class="linha" style="align-items:flex-start"><img src="${esc(r.thumbnail_url)}" alt="" style="width:300px;max-width:100%;border-radius:10px;flex:none">
        <div style="display:grid;gap:8px;flex:none"><span class="sub">Thumbnail do vídeo de referência</span>
        <a class="botao sec" href="${esc(r.thumbnail_url)}?baixar=1">Baixar thumbnail</a><button class="botao sec" id="e-copiar-thumb">Copiar imagem</button></div></div>` : ""}
      <textarea class="roteiro" id="e-texto">${esc(r.roteiro)}</textarea>
      <div class="linha"><span class="sub" id="e-conta">${r.roteiro.split(/\s+/).filter(Boolean).length} palavras · uns ${minutos(r.roteiro)} minutos de narração</span>
        <button class="botao sec" id="e-copiar">Copiar o roteiro</button><button class="botao sec" id="e-salvar">Salvar alterações</button></div>
    </div>
    <div class="passo"><h2><span class="n">3</span>Enviar para a fábrica</h2>
      ${fab.conectada ? `<p class="sub" style="margin:0">Cria o projeto na fábrica com este roteiro e este título. <b>Não gasta nada</b>: narrar e gerar as imagens continuam pedindo a sua confirmação lá.</p>
        <div class="linha"><select id="e-perfil">${fab.perfis.map((p) => `<option ${p === (PRODUCAO.perfil || "documentario") ? "selected" : ""}>${esc(p)}</option>`).join("")}</select>
          <button class="botao vermelho" id="e-enviar">Enviar para a fábrica</button></div>
        <div id="e-resultado">${r.fabrica ? `<p class="ok-fabrica">Já está na fábrica como "${esc(r.fabrica.projeto)}".</p>` : ""}</div>`
        : '<p class="sub">A fábrica não está nesta pasta: o Radar precisa estar dentro da pasta da fábrica para enviar.</p>'}
    </div>`;
  const $ = (id) => document.getElementById(id);
  $("e-texto").oninput = () => { const t = $("e-texto").value; $("e-conta").textContent = `${t.split(/\s+/).filter(Boolean).length} palavras · uns ${minutos(t)} minutos de narração`; };
  $("e-copiar").onclick = (e) => { navigator.clipboard.writeText($("e-texto").value); e.target.textContent = "Copiado ✓"; };
  const salvar = () => api(`/api/roteiros/${encodeURIComponent(r.nome)}/texto`, { method: "POST", body: { roteiro: $("e-texto").value, titulo: $("e-titulo").value } });
  $("e-salvar").onclick = (e) => carregando(e.currentTarget, "Salvando…", async () => { await salvar(); aviso("Roteiro salvo."); });
  const ct = $("e-copiar-thumb");
  if (ct) ct.onclick = async () => {
    try {
      const png = await new Promise(async (ok) => {   // a área de transferência aceita PNG, não JPG
        const img = new Image(); img.src = URL.createObjectURL(await (await fetch(r.thumbnail_url)).blob()); await img.decode();
        const c = document.createElement("canvas"); c.width = img.naturalWidth; c.height = img.naturalHeight;
        c.getContext("2d").drawImage(img, 0, 0); c.toBlob(ok, "image/png");
      });
      await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]); ct.textContent = "Copiada ✓";
    } catch { aviso("O navegador não deixou copiar a imagem. Use o Baixar thumbnail."); }
  };
  const enviar = $("e-enviar");
  if (enviar) enviar.onclick = () => carregando(enviar, "Criando o projeto na fábrica…", async () => {
    await salvar();
    const f = await api(`/api/roteiros/${encodeURIComponent(r.nome)}/fabrica`, { method: "POST", body: { perfil: $("e-perfil").value } });
    $("e-resultado").innerHTML = `<p class="ok-fabrica">Projeto "${esc(f.projeto)}" criado na fábrica, com o título e a thumbnail de referência.</p>
      ${f.estimativa ? `<pre class="log">${esc(f.estimativa)}</pre>` : ""}
      <span class="sub">Abra o editor da fábrica, ou rode na pasta da fábrica (ele mostra o custo e pede confirmação antes de gastar):</span>
      <code class="comando">${esc(f.proximo)}</code>
      <div class="linha"><button class="botao vermelho" id="e-produzir">▶ Produzir agora</button><a class="botao sec" href="#/acompanhar">Acompanhar</a></div>`;
    $("e-produzir").onclick = (ev) => carregando(ev.currentTarget, "Consultando a fábrica…", async () => {
      if (await produzirNaFabrica(f.projeto, $("e-titulo").value)) location.hash = "#/acompanhar";
    });
  });
  caixa.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------------------------------------------------------- Criar: a produção do canal, a Thumbnail e o Assistente
// Pedido do usuário em 2026-10-15: escolher o canal no Roteiro já puxa a voz e o estilo; a Thumbnail com o Claude
// escrevendo o prompt; e uma janela de IA ao lado das duas, com o canal dela à parte.

let PRODUCAO = {};      // a produção do canal escolhido no Roteiro (o "Enviar para a fábrica" usa o perfil dele)
const MINUTOS = [3, 5, 8, 10, 12, 15, 20, 30, 40, 50, 60];

// o resumo do canal no Roteiro: voz, estilo e tempo, e os campos já preenchidos
async function aplicarProducao(canalId, caixa, campos) {
  if (!canalId) { PRODUCAO = {}; caixa.innerHTML = '<p class="sub" style="margin:0">Escolha o canal: a voz, o estilo e o tempo vêm dele.</p>'; return; }
  const p = await api(`/api/producao/${encodeURIComponent(canalId)}`);
  PRODUCAO = p;
  if (campos.projeto && p.projeto_roteiro_id) campos.projeto.value = p.projeto_roteiro_id;
  if (campos.lingua && p.lingua) campos.lingua.value = p.lingua;
  if (campos.minutos && MINUTOS.includes(+p.minutos)) campos.minutos.value = p.minutos;
  const estilo = campos.projeto ? campos.projeto.selectedOptions[0]?.textContent.replace(/^Agente: /, "") : "";
  caixa.innerHTML = `<div class="producao-resumo">
    <span>🎙 <b>${p.voz ? esc(p.voz) : "sem voz"}</b><small>${p.perfil ? "perfil " + esc(p.perfil) : "nenhum perfil da fábrica com o nome deste canal"}</small></span>
    <span>✍️ <b>${esc(estilo || "Padrão")}</b><small>agente de roteiro</small></span>
    <span>🌐 <b>${esc(p.lingua)}</b><small>língua</small></span>
    <span>⏱ <b>${esc(p.minutos)} min</b><small>tempo do vídeo</small></span>
    <button class="botao sec" id="pr-salvar" data-dica="Guarda o agente de roteiro e a língua escolhidos aqui como o padrão deste canal.">Salvar como padrão do canal</button>
    <a class="sub" href="#" id="pr-ajustar">editar</a></div>`;
  caixa.querySelector("#pr-salvar").onclick = (e) => carregando(e.currentTarget, "Salvando…", async () => {
    await api(`/api/producao/${encodeURIComponent(canalId)}`, { method: "POST", body: { ...p,
      projeto_roteiro_id: campos.projeto?.value || "", lingua: campos.lingua?.value || p.lingua } });
    aviso("Padrão do canal salvo.");
  });
}

const bandeiraImg = (c) => `<img src="https://flagcdn.com/w40/${c}.png" alt="" style="width:28px;height:20px;object-fit:cover;border-radius:3px">`;
// a produção do canal: na primeira vez, uma pergunta por vez (língua, voz, agente de roteiro, tempo); depois, uma
// linha simples com o "editar". Pedidos do usuário em 2026-10-15: "uma pergunta por vez, só na primeira vez"; "maior";
// "conectar a fábrica para já aparecer as vozes e dar para testar antes de escolher"; "adicionar o agente na terceira
// pergunta, além do tempo dos vídeos".
async function formProducao(caixa, canalId, depois = () => {}, perguntarDeNovo = false) {
  let [p, { projetos }] = await Promise.all([api(`/api/producao/${encodeURIComponent(canalId)}`), api("/api/projetos")]);
  const escolha = { lingua: p.lingua, perfil: p.perfil, projeto_roteiro_id: String(p.projeto_roteiro_id || ""), minutos: String(p.minutos || 8) };
  let tocando = null, botaoTocando = null;
  const parar = () => { if (tocando) { tocando.pause(); tocando = null; } if (botaoTocando) { botaoTocando.textContent = "▶"; botaoTocando = null; } };
  const agenteDe = (id) => (projetos.find((x) => String(x.id) === String(id)) || {}).nome || "Agente padrão";
  const TOTAL = 4;
  const moldura = (i, corpo) => `<div class="pergunta-caixa">
      <div class="pergunta-passos">${Array.from({ length: TOTAL }, (_, j) => `<i class="${j < i ? "feito" : j === i ? "atual" : ""}"></i>`).join("")}</div>
      <small class="pergunta-de">Pergunta ${i + 1} de ${TOTAL} · configurando ${esc(p.canal)}</small>${corpo}
      ${i ? '<button class="link-editar" id="pg-voltar">← voltar</button>' : ""}</div>`;
  const ligarVoltar = (i) => { const v = caixa.querySelector("#pg-voltar"); if (v) v.onclick = () => { parar(); perguntas[i - 1](); }; };
  const opcoes = (lista, chave, aoEscolher) => {
    caixa.querySelectorAll(".opcao[data-v]").forEach((b) => (b.onclick = () => { escolha[chave] = b.dataset.v; aoEscolher(); }));
    return lista;
  };
  const cartoes = (lista, chave) => `<div class="pergunta-opcoes">${lista.map(([v, ic, nome, sub]) => `<button class="opcao ${escolha[chave] === v ? "marcada" : ""}" data-v="${esc(v)}">
      <span class="ic">${ic}</span><b>${esc(nome)}</b>${sub ? `<small>${esc(sub)}</small>` : ""}</button>`).join("")}</div>`;

  const perguntas = [
    // 1. a língua
    () => {
      caixa.innerHTML = moldura(0, `<h3>Em que língua são os vídeos deste canal?</h3>` + cartoes([
        ["português", bandeiraImg("br"), "Português"], ["inglês", bandeiraImg("us"), "Inglês"], ["espanhol", bandeiraImg("es"), "Espanhol"]], "lingua"));
      opcoes(null, "lingua", () => perguntas[1]());
    },
    // 2. a voz, da biblioteca da fábrica, com a prévia
    async (busca = "", genero = "") => {
      caixa.innerHTML = moldura(1, `<h3>Qual voz narra os vídeos?</h3>
        <p class="sub">As vozes da fábrica (GenAI Pro) em ${esc(escolha.lingua)}. Aperte ▶ para ouvir antes de escolher.${p.voz ? ` Voz de agora: <b>${esc(p.voz)}</b>.` : ""}</p>
        <div class="linha voz-filtros"><input id="vz-busca" placeholder="Procurar voz (ex.: deep, narrator, calm)" value="${esc(busca)}">
          <select id="vz-genero"><option value="">Homem e mulher</option><option value="male" ${genero === "male" ? "selected" : ""}>Homem</option><option value="female" ${genero === "female" ? "selected" : ""}>Mulher</option></select>
          <button class="botao sec" id="vz-procurar">Procurar</button>${p.voz ? '<button class="botao sec" id="vz-manter">Manter a voz de agora</button>' : ""}</div>
        <div class="vozes-lista" id="vz-lista"><div class="vazio">Buscando as vozes na fábrica…</div></div>`);
      ligarVoltar(1);
      const procurar = () => perguntas[1](caixa.querySelector("#vz-busca").value.trim(), caixa.querySelector("#vz-genero").value);
      caixa.querySelector("#vz-procurar").onclick = procurar;
      caixa.querySelector("#vz-busca").onkeydown = (e) => { if (e.key === "Enter") procurar(); };
      const manter = caixa.querySelector("#vz-manter");
      if (manter) manter.onclick = () => { parar(); perguntas[2](); };
      let r;
      try { r = await api("/api/fabrica/vozes?" + consulta({ lingua: escolha.lingua, busca, genero })); }
      catch (e) { caixa.querySelector("#vz-lista").innerHTML = `<div class="vazio">${esc(e.message)}</div>`; return; }
      const lista = caixa.querySelector("#vz-lista");
      if (!lista) return;
      lista.innerHTML = r.erro ? `<div class="vazio">${esc(r.erro)}</div>` : r.vozes.map((v, k) => `<div class="voz-cartao">
          <button class="voz-ouvir" data-k="${k}" title="Ouvir">▶</button>
          <div class="voz-info"><b>${esc(v.nome)}</b><small>${esc([v.genero, v.idade, v.sotaque].filter(Boolean).join(" · "))}</small>
            <p>${esc((v.descricao || "").slice(0, 140))}${(v.descricao || "").length > 140 ? "…" : ""}</p></div>
          <button class="botao" data-escolher="${k}">Escolher</button></div>`).join("") || '<div class="vazio">Nenhuma voz achada. Tente outra busca.</div>';
      lista.querySelectorAll(".voz-ouvir").forEach((b) => (b.onclick = () => {
        const v = r.vozes[+b.dataset.k];
        const mesmo = botaoTocando === b; parar();
        if (mesmo || !v.previa) return;
        tocando = new Audio(v.previa); botaoTocando = b; tocando.play(); b.textContent = "■";
        tocando.onended = parar;
      }));
      lista.querySelectorAll("[data-escolher]").forEach((b) => (b.onclick = () => carregando(b, "Criando o canal na fábrica…", async () => {
        parar();
        const v = r.vozes[+b.dataset.escolher];
        const novo = await api(`/api/producao/${encodeURIComponent(canalId)}/voz`, { method: "POST", body: { voice_id: v.voice_id, nome: v.nome, idioma: v.idioma } });
        p = { ...p, ...novo }; escolha.perfil = novo.perfil;
        aviso(`Voz ${v.nome} guardada no canal (na fábrica: ${novo.perfil}).`);
        perguntas[2]();
      })));
    },
    // 3. o agente de roteiro, com a opção de criar um novo ali mesmo
    () => {
      caixa.innerHTML = moldura(2, `<h3>Qual agente de roteiro escreve para este canal?</h3>
        <p class="sub">O agente guarda o jeito de escrever: tom, público, como abrir e fechar.</p>` + cartoes([
          ["", "✍️", "Agente padrão", "o Claude no jeito padrão"], ...projetos.map((x) => [String(x.id), "✍️", x.nome, x.instrucoes.slice(0, 80)]),
        ], "projeto_roteiro_id") + `
        <button class="opcao opcao-nova" id="ag-novo"><span class="ic">＋</span><b>Criar um agente novo</b><small>cole as instruções de um projeto do claude.ai</small></button>
        <div class="agente-novo" id="ag-form" hidden><input id="ag-nome" placeholder="Nome do agente (ex.: canal de animais em inglês)">
          <textarea id="ag-instr" rows="7" placeholder="Instruções: tom de voz, público, estrutura, como abrir e fechar, o que evitar…"></textarea>
          <button class="botao" id="ag-salvar">Salvar o agente e usar neste canal</button></div>`);
      ligarVoltar(2);
      opcoes(null, "projeto_roteiro_id", () => perguntas[3]());
      caixa.querySelector("#ag-novo").onclick = () => { caixa.querySelector("#ag-form").hidden = false; caixa.querySelector("#ag-nome").focus(); };
      caixa.querySelector("#ag-salvar").onclick = (e) => carregando(e.currentTarget, "Salvando…", async () => {
        const { id } = await api("/api/projetos", { method: "POST", body: { nome: caixa.querySelector("#ag-nome").value, instrucoes: caixa.querySelector("#ag-instr").value } });
        projetos = (await api("/api/projetos")).projetos;
        escolha.projeto_roteiro_id = String(id);
        perguntas[3]();
      });
    },
    // 4. o tempo dos vídeos
    () => {
      caixa.innerHTML = moldura(3, `<h3>Quanto tempo costumam ter os vídeos?</h3>
        <p class="sub">É o tamanho que o Claude mira no roteiro. Dá para mudar em cada vídeo, no Roteiro.</p>` +
        cartoes(MINUTOS.map((m) => [String(m), "⏱", `${m} minutos`, ""]), "minutos"));
      ligarVoltar(3);
      opcoes(null, "minutos", async () => {
        await api(`/api/producao/${encodeURIComponent(canalId)}`, { method: "POST", body: { ...p, ...escolha } });
        p = await api(`/api/producao/${encodeURIComponent(canalId)}`);
        aviso(`${p.canal} configurado.`); resumo(); depois();
      });
    },
  ];
  // editar o texto do agente (o que ele sabe sobre o canal) ou criar um, sem sair da página
  const editarAgente = () => {
    const a = projetos.find((x) => String(x.id) === String(p.projeto_roteiro_id)) || { id: "", nome: "", instrucoes: "" };
    caixa.innerHTML = `<div class="pergunta-caixa"><h3>${a.id ? "Editar o agente de roteiro" : "Criar o agente de roteiro"}</h3>
      <p class="sub">O agente guarda o jeito de escrever do canal: tom, público, como abrir e fechar, o que evitar. Vale para os próximos roteiros${a.id ? " de todos os canais que usam este agente" : ""}.</p>
      <label class="campo"><span>Nome</span><input id="ag-nome" value="${esc(a.nome)}" placeholder="Ex.: canal de animais em português"></label>
      <label class="campo"><span>Ideal para (opcional)</span><input id="ag-ideal" value="${esc(a.ideal_para || "")}" placeholder="Ex.: modelar um vídeo que foi muito bem num canal de outro país"></label>
      <label class="campo"><span>Instruções</span><textarea id="ag-instr" rows="12" placeholder="Cole aqui as instruções (de um projeto do claude.ai, por exemplo)">${esc(a.instrucoes)}</textarea></label>
      <div class="linha"><button class="botao" id="ag-salvar">Salvar o agente</button><button class="botao sec" id="ag-cancelar">Cancelar</button></div></div>`;
    caixa.querySelector("#ag-cancelar").onclick = () => resumo();
    caixa.querySelector("#ag-salvar").onclick = (e) => carregando(e.currentTarget, "Salvando…", async () => {
      const r = await api("/api/projetos", { method: "POST", body: { id: a.id || null, nome: caixa.querySelector("#ag-nome").value,
        instrucoes: caixa.querySelector("#ag-instr").value, ideal_para: caixa.querySelector("#ag-ideal").value } });
      projetos = (await api("/api/projetos")).projetos;
      if (!a.id) {
        await api(`/api/producao/${encodeURIComponent(canalId)}`, { method: "POST", body: { ...p, projeto_roteiro_id: String(r.id) } });
        p.projeto_roteiro_id = String(r.id);
      }
      aviso("Agente salvo."); resumo(); depois();
    });
  };
  const resumo = () => {
    caixa.innerHTML = `<div class="pergunta-caixa producao-pronta"><div class="producao-pronta-cab"><h3>Configuração de ${esc(p.canal)}</h3>
        <button class="botao sec" id="pc-editar">Editar</button></div>
      <div class="producao-respostas">
        <div><span class="ic">🌐</span><small>Língua</small><b>${esc(p.lingua)}</b></div>
        <div><span class="ic">🎙</span><small>Voz</small><b>${esc(p.voz || p.perfil || "sem voz")}</b></div>
        <div><span class="ic">✍️</span><small>Agente de roteiro</small><b>${esc(agenteDe(p.projeto_roteiro_id))}</b>
          <button class="link-editar" id="pc-editar-agente" style="margin:4px 0 0">${p.projeto_roteiro_id ? "editar o agente" : "criar um agente"}</button></div>
        <div><span class="ic">⏱</span><small>Tempo dos vídeos</small><b>${esc(p.minutos)} minutos</b></div></div></div>`;
    caixa.querySelector("#pc-editar").onclick = () => perguntas[0]();
    caixa.querySelector("#pc-editar-agente").onclick = () => editarAgente();
  };
  p.salvo && !perguntarDeNovo ? resumo() : perguntas[0]();
  return p;
}

// O ChatGPT e o Gemini não deixam ser abertos dentro de outro site (bloqueiam o iframe). A lateral é uma janela do
// navegador encostada no lado direito da tela, já logada na conta da pessoa, sempre a mesma (o nome "radar-lateral").
function abrirLateral(url) {
  const largura = Math.min(520, Math.round(screen.availWidth * 0.34));
  const janela = window.open(url, "radar-lateral",
    `popup=yes,width=${largura},height=${screen.availHeight},left=${screen.availWidth - largura},top=0`);
  if (!janela) { aviso("O navegador bloqueou a janela. Permita pop-ups para este site e clique de novo."); return null; }
  janela.focus();
  return janela;
}

// copia uma imagem (a área de transferência só aceita PNG)
async function copiarImagem(url) {
  const blob = await (await fetch(url)).blob();
  const img = new Image(); img.src = URL.createObjectURL(blob); await img.decode();
  const c = document.createElement("canvas"); c.width = img.naturalWidth; c.height = img.naturalHeight;
  c.getContext("2d").drawImage(img, 0, 0);
  const png = await new Promise((ok) => c.toBlob(ok, "image/png"));
  await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
}

const idDoVideo = (link) => (String(link || "").match(/(?:v=|youtu\.be\/|\/shorts\/|\/live\/)([\w-]{11})/) || [])[1] || "";

async function thumbnail() {
  const preset = guardado("thumb-preset", {}); guardar("thumb-preset", {});
  const [canais, dados] = await Promise.all([meusCanais(), api("/api/thumb-projetos")]);
  tela.innerHTML = titulo("Thumbnail", "Diga o que quer: o Claude escreve o prompt com o estilo do canal e a thumbnail de referência, e você manda para a IA de imagem.", "thumbnail") + `
    <div class="criar-grade"><div class="criar-main">
      <div class="passo"><h2><span class="n">1</span>O que você quer</h2>
        <textarea id="th-pedido" rows="3" placeholder="Ex.: igual à referência, mas sem texto · troque o leão por um lobo · fundo mais escuro e dramático"></textarea>
        <div class="linha"><select id="th-canal"><option value="">Escolha o canal</option>${canais.map((c) => `<option value="${esc(c.id)}" ${c.id === (preset.canal || CANAL_ATUAL) ? "selected" : ""}>Canal: ${esc(c.titulo)}</option>`).join("")}</select>
          <select id="th-estilo"></select><select id="th-ia"><option value="gemini">Mandar para o Gemini</option><option value="chatgpt">Mandar para o ChatGPT</option></select>
          <a href="#" id="th-estilos" class="sub">estilos</a></div>
        <div id="th-estilos-caixa" hidden></div>
        <input id="th-link" placeholder="Link do vídeo de referência (a thumbnail dele é a base)" value="${esc(preset.link || "")}">
        <input id="th-titulo" placeholder="Título do seu vídeo" value="${esc(preset.titulo || "")}">
        <div id="th-ref"></div>
        <div class="linha"><button class="botao" id="th-criar">✨ Criar o prompt com o Claude</button>
          <button class="botao sec" id="th-padrao" data-dica="Guarda o estilo e a IA de imagem escolhidos como o padrão deste canal.">Salvar como padrão do canal</button></div>
      </div>
      <div class="passo" id="th-resultado" hidden><h2><span class="n">2</span>Mandar para a IA de imagem</h2>
        <textarea id="th-prompt" rows="9"></textarea>
        <div class="linha"><button class="botao vermelho" id="th-enviar"></button><button class="botao sec" id="th-copiar">Copiar o prompt</button>
          <button class="botao sec" id="th-copiar-img">Copiar a thumbnail de referência</button></div>
        <p class="sub" id="th-como"></p>
      </div>
    </div><aside class="assistente" id="assistente"></aside></div>`;
  const $ = (id) => document.getElementById(id);
  const estilos = (atual = "") => {
    const canal = $("th-canal").value;
    $("th-estilo").innerHTML = '<option value="">Estilo padrão</option>' + dados.projetos.filter((p) => !p.canal_id || p.canal_id === canal)
      .map((p) => `<option value="${p.id}" ${String(p.id) === String(atual) ? "selected" : ""}>Estilo: ${esc(p.nome)}</option>`).join("");
  };
  const doCanal = async () => {
    const canal = $("th-canal").value;
    if (!canal) return estilos();
    const p = await api(`/api/producao/${encodeURIComponent(canal)}`);
    estilos(p.thumb_projeto_id); $("th-ia").value = p.ia_imagem || "gemini";
    if (!$("th-titulo").value) $("th-titulo").placeholder = `Título do seu vídeo para ${p.canal}`;
  };
  const verRef = () => {
    const vid = idDoVideo($("th-link").value);
    $("th-ref").innerHTML = vid ? `<img class="thumb-ref grande" src="/api/thumb/imagem/${esc(vid)}" alt="">` : "";
  };
  $("th-canal").onchange = doCanal; $("th-link").oninput = verRef; doCanal(); verRef();
  $("th-estilos").onclick = (e) => {
    e.preventDefault(); const c = $("th-estilos-caixa"); c.hidden = !c.hidden;
    if (!c.hidden) gerenciarThumbs(c, dados, canais, async () => { Object.assign(dados, await api("/api/thumb-projetos")); estilos($("th-estilo").value); });
  };
  $("th-padrao").onclick = (e) => {
    const canal = $("th-canal").value;
    if (!canal) return aviso("Escolha o canal primeiro.");
    carregando(e.currentTarget, "Salvando…", async () => {
      const p = await api(`/api/producao/${encodeURIComponent(canal)}`);
      await api(`/api/producao/${encodeURIComponent(canal)}`, { method: "POST", body: { ...p, thumb_projeto_id: $("th-estilo").value, ia_imagem: $("th-ia").value } });
      aviso("Padrão da thumbnail salvo no canal.");
    });
  };
  const nomeIa = () => ($("th-ia").value === "chatgpt" ? "ChatGPT" : "Gemini");
  $("th-criar").onclick = (e) => carregando(e.currentTarget, "O Claude está escrevendo o prompt…", async () => {
    const r = await api("/api/thumb/claude", { method: "POST", body: { link: $("th-link").value.trim(), titulo: $("th-titulo").value.trim(),
      pedido: $("th-pedido").value.trim(), projeto_id: $("th-estilo").value, ia: $("th-ia").value } });
    $("th-resultado").hidden = false; $("th-prompt").value = r.prompt;
    $("th-enviar").textContent = `Enviar para o ${nomeIa()}`;
    $("th-resultado").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("th-copiar").onclick = (e) => { navigator.clipboard.writeText($("th-prompt").value); e.target.textContent = "Copiado ✓"; };
  $("th-copiar-img").onclick = async (e) => {
    const vid = idDoVideo($("th-link").value);
    if (!vid) return aviso("Cole o link do vídeo de referência.");
    try { await copiarImagem(`/api/thumb/imagem/${vid}`); e.target.textContent = "Imagem copiada ✓"; } catch { aviso("O navegador não deixou copiar a imagem."); }
  };
  // ChatGPT: abre com o prompt já escrito e a imagem copiada para colar. Gemini: o prompt copiado, e depois a imagem.
  $("th-enviar").onclick = async () => {
    const prompt = $("th-prompt").value, vid = idDoVideo($("th-link").value), janela = window.open("", "_blank");
    if ($("th-ia").value === "chatgpt") {
      if (vid) { try { await copiarImagem(`/api/thumb/imagem/${vid}`); } catch {} }
      janela.location = "https://chatgpt.com/?q=" + encodeURIComponent(prompt);
      $("th-como").innerHTML = vid ? "O ChatGPT abriu com o prompt escrito e a <b>thumbnail de referência está copiada</b>: clique na caixa de mensagem, aperte <b>Ctrl+V</b> para colar a imagem e envie."
        : "O ChatGPT abriu com o prompt escrito. É só enviar.";
    } else {
      await navigator.clipboard.writeText(prompt);
      janela.location = "https://gemini.google.com/app";
      $("th-como").innerHTML = "O <b>prompt está copiado</b>: no Gemini, aperte <b>Ctrl+V</b> na caixa de mensagem." +
        (vid ? " Para mandar a referência junto, volte aqui, clique em <b>Copiar a thumbnail de referência</b> e cole lá também." : "");
    }
  };
  montarAssistente($("assistente"), () => $("th-titulo").value.trim());
}

// ---------------------------------------------------------------- Título: o chat com o Claude e o "Levar para o roteiro"
// Pedido do usuário em 2026-10-15: uma aba para o título do vídeo (a extensão vai mandar para cá depois), onde se pede
// para regionalizar ou o que quiser, num chat; e um botão que leva para o Roteiro com o link e a thumbnail. Conferir se
// o título já foi feito no YouTube é manual.

async function tituloTela() {
  const preset = guardado("titulo-preset", {}); guardar("titulo-preset", {});
  const canais = await meusCanais();
  tela.innerHTML = titulo("Título", "Cole o título e o link do vídeo, converse com o Claude para regionalizar ou mudar o que quiser, e leve para o roteiro.", "titulo") + `
    <div class="titulo-grade">
      <div class="passo titulo-origem"><h2><span class="n">1</span>O vídeo</h2>
        <input id="ti-link" placeholder="Link do vídeo de referência" value="${esc(preset.link || "")}">
        <input id="ti-original" placeholder="Título do vídeo" value="${esc(preset.titulo || "")}">
        <div id="ti-ref"></div>
        <h2><span class="n">2</span>O título escolhido</h2>
        <input id="ti-escolhido" placeholder="Clique em “usar” num título do Claude, ou escreva aqui">
        <select id="ti-canal"><option value="">Para qual canal? (o Roteiro puxa a voz dele)</option>${canais.map((c) => `<option value="${esc(c.id)}">Canal: ${esc(c.titulo)}</option>`).join("")}</select>
        <button class="botao vermelho grande" id="ti-levar">Levar para o roteiro →</button>
        <p class="sub" style="margin:0">Vai com o título escolhido, o link e a thumbnail do vídeo.</p>
      </div>
      <aside class="assistente grande" id="assistente"></aside>
    </div>`;
  const $ = (id) => document.getElementById(id);
  const verRef = async () => {
    const vid = idDoVideo($("ti-link").value);
    $("ti-ref").innerHTML = vid ? `<img class="thumb-ref" src="/api/thumb/imagem/${esc(vid)}" alt="">` : "";
    if (vid && !$("ti-original").value.trim()) {
      try { $("ti-original").value = (await api("/api/titulo-do-video?" + consulta({ link: $("ti-link").value.trim() }))).titulo; } catch {}
    }
  };
  $("ti-link").onchange = verRef; verRef();
  $("ti-levar").onclick = () => {
    const tituloFinal = $("ti-escolhido").value.trim() || $("ti-original").value.trim();
    if (!tituloFinal) return aviso("Escreva ou escolha o título.");
    guardar("roteiro-preset", { link: $("ti-link").value.trim(), titulo: tituloFinal });
    if ($("ti-canal").value) CANAL_ATUAL = $("ti-canal").value;
    location.hash = "#/trabalho";
  };
  montarAssistente($("assistente"), () => $("ti-escolhido").value.trim() || $("ti-original").value.trim(),
    { aoUsar: (t) => { $("ti-escolhido").value = t; $("ti-escolhido").focus(); aviso("Título escolhido. Agora é só levar para o roteiro."); } });
}

// os prontos para postar da página do canal
async function painelCanal(caixa, canalId) {
  const url = `/api/canal-painel/${encodeURIComponent(canalId)}`;
  let d;
  try { d = await api(url); } catch (e) { caixa.innerHTML = `<div class="vazio">${esc(e.message)}</div>`; return; }
  const desenhar = () => {
    caixa.innerHTML = `<div class="cp-main">
      <section class="cp-bloco"><h3>🎬 Prontos para postar <small class="sub">${d.para_postar.length}</small></h3>
        <p class="sub">Os vídeos que a fábrica já entregou para este canal e ainda não foram publicados.</p>
        <div class="cp-postar">${d.para_postar.map((v, i) => `<div class="cp-post">
            <div class="cp-post-midia">
              <button class="cp-post-capa" data-assistir-p="${i}" title="Assistir o vídeo">${v.capa ? `<img src="${esc(v.capa)}" alt="">` : '<div class="prod-sem-capa">🎬</div>'}<span class="dur">${minSeg(v.duracao)}</span><span class="play">▶</span></button>
              ${v.shorts.map((s, k) => `<button class="cp-short" data-short-p="${i}" data-sid="${esc(s.id)}" title="${esc(s.titulo || "Short " + (k + 1))}">
                <video src="/api/producoes/${encodeURIComponent(v.nome)}/shorts/${encodeURIComponent(s.id)}#t=1" preload="metadata" muted></video><span>▶ Short ${k + 1}</span></button>`).join("")}
            </div>
            <div class="cp-post-info"><b>${esc(v.titulo)}</b><small>${minSeg(v.duracao)} · pronto em ${v.criado ? new Date(v.criado).toLocaleDateString("pt-BR") : "—"} · ${v.shorts.length} ${v.shorts.length === 1 ? "short" : "shorts"}</small>
              <div class="video-acoes"><button class="botao sec" data-assistir-p="${i}">▶ Assistir</button><button class="botao sec" data-copiar="titulo" data-i="${i}">Copiar título</button>
                <button class="botao sec" data-copiar="descricao" data-i="${i}">Copiar descrição</button></div></div>
            <div class="cp-post-acoes"><button class="botao cp-postei" data-ja="${i}" title="Marca o vídeo e os shorts como postados">✓ Postei tudo</button>
              <div class="cp-itens">${[["video", "Vídeo"], ...v.shorts.map((s, k) => [s.id, `Short ${k + 1}`])].map(([id, nomeItem]) => {
                const feito = v.postados.includes(id);
                return `<div class="cp-item ${feito ? "feito" : ""}"><span>${feito ? "✓ " : ""}${nomeItem}</span>
                  <button class="mini-bt" data-postar="${i}" data-item="${id}">📤 Postar</button>
                  <button class="mini-bt" data-postei="${i}" data-item="${id}" data-feito="${feito ? 1 : 0}">${feito ? "desfazer" : "✓ Postei"}</button></div>`;
              }).join("")}</div></div>
          </div>`).join("") || '<div class="vazio">Nada esperando: todo vídeo pronto deste canal já foi publicado.</div>'}</div>
        <p class="sub" id="cp-como"></p>
      </section>
      </div>`;
    const $ = (id) => caixa.querySelector("#" + id);
    const lista = d.para_postar;
    caixa.querySelectorAll("[data-copiar]").forEach((b) => (b.onclick = () => {
      navigator.clipboard.writeText(lista[+b.dataset.i][b.dataset.copiar] || ""); b.textContent = "Copiado ✓";
    }));
    caixa.querySelectorAll("[data-assistir-p]").forEach((b) => (b.onclick = () => { const v = lista[+b.dataset.assistirP]; assistir(v.nome, v.titulo); }));
    // postar: abre a tela de enviar vídeo do YouTube Studio deste canal e a pasta da entrega, com o título copiado
    caixa.querySelectorAll("[data-postar]").forEach((b) => (b.onclick = async () => {
      const v = lista[+b.dataset.postar], item = b.dataset.item || "video";
      const short = v.shorts.find((s) => s.id === item);
      window.open(`https://studio.youtube.com/channel/${encodeURIComponent(canalId)}/videos/upload?d=ud`, "_blank");
      navigator.clipboard.writeText(short ? short.titulo || v.titulo : v.titulo).catch(() => {});
      api(`/api/producoes/${encodeURIComponent(v.nome)}/pasta`, { method: "POST", body: {} }).catch(() => {});
      $("cp-como").innerHTML = short
        ? `O <b>YouTube Studio</b> abriu na tela de enviar e a <b>pasta da entrega</b> abriu: o ${esc(b.closest(".cp-item").querySelector("span").textContent.replace("✓ ", ""))} está na pasta <b>shorts</b>. O título do short já está copiado. Depois de publicar, clique em <b>✓ Postei</b>.`
        : `O <b>YouTube Studio</b> abriu na tela de enviar vídeo deste canal e a <b>pasta da entrega</b> abriu no computador: arraste o MP4 para o Studio. O título já está copiado; use <b>Copiar descrição</b> para o resto. Depois de publicar, clique em <b>✓ Postei</b>.`;
    }));
    caixa.querySelectorAll("[data-short-p]").forEach((b) => (b.onclick = () => {
      const v = lista[+b.dataset.shortP]; assistir(v.nome, `${v.titulo} · ${b.textContent.trim().replace("▶ ", "")}`, b.dataset.sid);
    }));
    // postei um item (o vídeo ou um short); clicar de novo desfaz
    caixa.querySelectorAll("[data-postei]").forEach((b) => (b.onclick = async () => {
      const v = lista[+b.dataset.postei];
      await api(`/api/resultados/${encodeURIComponent(v.nome)}/postado`, { method: "POST", body: { item: b.dataset.item, postado: b.dataset.feito !== "1" } });
      d = await api(url); desenhar();
    }));
    // postei tudo: o vídeo e os shorts saem da lista e contam como publicados, sem pedir o link
    caixa.querySelectorAll("[data-ja]").forEach((b) => (b.onclick = () => carregando(b, "Marcando…", async () => {
      const v = lista[+b.dataset.ja];
      await api(`/api/resultados/${encodeURIComponent(v.nome)}/publicado`, { method: "POST", body: { postado: true } });
      aviso(`“${v.titulo}” marcado como postado.`); d = await api(url); desenhar();
    })));
  };
  desenhar();
}

// o modelo da descrição que a extensão cola no Studio: o mesmo texto em todo vídeo do canal, trocando só o que é
// deste vídeo (pedido do usuário em 2026-10-22: "mais padronizado, só mudando para o tema do vídeo, sem spoilers")
async function modeloDaDescricao(caixa, canalId) {
  const p = await api(`/api/producao/${encodeURIComponent(canalId)}`);
  const telas = p.telas_finais || { melhor: "Vídeo (melhor para o espectador) + inscrever-se" };
  const tipos = p.tipos_de_modelo || { geral: "Geral" };
  const padroes = p.rodapes_padrao || {};
  caixa.innerHTML = `<h3>📤 Publicação</h3>
    <p class="sub">Esta tela <b>não publica nada</b>. Ela guarda as escolhas que você faria à mão em todo vídeo deste
      canal, e a extensão do Radar repete sozinha na tela de enviar vídeo do YouTube Studio: liga a monetização e
      espalha os anúncios, escolhe a tela final, marca o uso de IA e preenche título, descrição e tags do vídeo que
      a fábrica entregou. <b>Quem aperta Publicar continua sendo você</b> — a extensão para antes disso.</p>
    <div class="linha">
      <label class="campo"><span>Anúncio no meio do vídeo, a cada</span>
        <div class="par"><input id="pb-anuncio" type="number" min="1" max="60" value="${+p.anuncio_cada || 1}"> <span>minutos</span></div></label>
      <label class="campo"><span>Tela final</span><select id="pb-tela">${Object.entries(telas).map(([v, nome]) =>
        `<option value="${esc(v)}" ${(p.tela_final || "melhor") === v ? "selected" : ""}>${esc(nome)}</option>`).join("")}</select></label>
    </div>
    <p class="sub">O uso de IA vai marcado como <b>Sim</b> em todo vídeo: os da fábrica são feitos com IA.</p>

    <h3>🧾 Rodapé da descrição</h3>
    <p class="sub">A apresentação do canal e o aviso legal, iguais em todo vídeo. <b>Quem escreve a descrição é a
      fábrica</b>: ela põe o resumo do vídeo, os capítulos e, no fim, este texto. Então o vídeo já sai do projeto
      com a descrição pronta — a extensão só cola. A lista de onde vêm as imagens <b>não entra mais na descrição</b>
      (25/10/2026); ela continua no <code>creditos.txt</code> da pasta do projeto, para conferir quando precisar.
      Isto fica no perfil <code>${esc(p.perfil || "—")}</code> da fábrica, não no Radar.</p>
    <div class="linha">
      <label class="campo"><span>Marcas e lojas que o canal cita</span>
        <input id="md-marcas" maxlength="300" placeholder="Ex.: Tesco, Asda, Sainsbury&#39;s, Morrisons, Aldi, Lidl" value="${esc(p.marcas || "")}"></label>
      <label class="campo"><span>Padrão para copiar</span><select id="md-tipo">${Object.entries(tipos).map(([v, nome]) =>
        `<option value="${esc(v)}" ${(p.modelo_tipo || "geral") === v ? "selected" : ""}>${esc(nome)}</option>`).join("")}</select></label>
    </div>
    <label class="campo"><span>O texto, como vai sair no YouTube</span>
      <textarea id="md-texto" rows="14" maxlength="3000" placeholder="Vazio: a descrição sai sem rodapé">${esc(p.rodape || "")}</textarea></label>
    <div class="linha"><button class="botao" id="md-salvar">Salvar</button>
      <button class="botao sec" id="md-sugerido">Copiar o padrão para cá</button></div>`;
  // o padrão já vem com o nome do canal e as marcas trocados: o que a pessoa copia é o texto final
  caixa.querySelector("#md-sugerido").onclick = () => {
    caixa.querySelector("#md-texto").value = padroes[caixa.querySelector("#md-tipo").value] || "";
  };
  caixa.querySelector("#md-salvar").onclick = (e) => carregando(e.currentTarget, "Salvando…", async () => {
    await api(`/api/producao/${encodeURIComponent(canalId)}`, { method: "POST",
      body: { ...p, marcas: caixa.querySelector("#md-marcas").value.trim(),
        modelo_tipo: caixa.querySelector("#md-tipo").value, rodape: caixa.querySelector("#md-texto").value,
        anuncio_cada: +caixa.querySelector("#pb-anuncio").value || 1,
        tela_final: caixa.querySelector("#pb-tela").value } });
    aviso("Salvo no perfil da fábrica. Os próximos vídeos deste canal já saem com este rodapé.");
  });
}

// o texto fixo da descrição e os shorts, gravados no perfil da fábrica do canal
async function fabricaDoCanal(caixa, url) {
  let f;
  try { f = await api(url + "/fabrica"); }
  catch (e) { caixa.innerHTML = `<h3>📝 Descrição e shorts</h3><p class="sub">${esc(e.message)}</p>`; return; }
  caixa.innerHTML = `<h3>📝 Descrição e shorts</h3>
    <p class="sub">Fica no perfil do canal na fábrica (${esc(f.perfil)}) e vale para os próximos vídeos.</p>
    <label class="campo"><span>Texto fixo no começo da descrição (links, redes, hashtags)</span>
      <textarea id="cf-texto" rows="5" maxlength="1500" placeholder="Ex.: Inscreva-se para mais vídeos como este! #animais #natureza">${esc(f.texto_fixo)}</textarea></label>
    <div class="cp-shorts"><label class="cp-liga"><input type="checkbox" id="cf-shorts" ${f.shorts_ativo ? "checked" : ""}> Cortar shorts de cada vídeo</label>
      <select id="cf-qtd">${[1, 2, 3, 4, 5].map((n) => `<option value="${n}" ${n === +f.shorts_quantidade ? "selected" : ""}>${n} ${n === 1 ? "short" : "shorts"} por vídeo</option>`).join("")}</select></div>
    <button class="botao" id="cf-salvar" style="justify-self:start">Salvar na fábrica</button>`;
  caixa.querySelector("#cf-salvar").onclick = (e) => carregando(e.currentTarget, "Gravando na fábrica…", async () => {
    await api(url + "/fabrica", { method: "POST", body: { texto_fixo: caixa.querySelector("#cf-texto").value,
      shorts_ativo: caixa.querySelector("#cf-shorts").checked, shorts_quantidade: caixa.querySelector("#cf-qtd").value } });
    aviso("Descrição e shorts salvos no perfil da fábrica.");
  });
}

// o aviso que explica o ajuste do tempo, na primeira vez que ele é usado (e no "por quê?" depois)
function explicarAjusteTempo(ritmo, minutos) {
  guardar("ajuste-tempo-explicado", true);
  const ex = ritmo.exemplo || {};
  const antes = minutos * ritmo.padrao, agora = minutos * (ritmo.ppm_alvo || ritmo.ppm);
  const n = (x) => Math.round(x).toLocaleString("pt-BR");
  const min = (x) => String(x).replace(".", ",");
  notificar("⏱ Tempo do vídeo ajustado", `A voz fala ${ritmo.ppm} palavras por minuto: para ${minutos} min, o Claude vai escrever ${n(agora)} palavras.`);
  document.getElementById("ajuste-tempo")?.remove();
  document.body.insertAdjacentHTML("beforeend", `<div class="modal-fundo" id="ajuste-tempo"><div class="modal-tempo">
    <div class="mt-ic">⏱</div>
    <h2>O Radar ajusta o tempo do vídeo sozinho</h2>
    <p>Cada voz fala num ritmo. Por isso o Radar <b>olha quanto tempo cada vídeo entregue ficou de verdade</b> e corrige quantas palavras pedir ao Claude na próxima vez.</p>
    ${ex.titulo ? `<div class="mt-exemplo">
      <small>O que aconteceu em “${esc(ex.titulo)}”</small>
      <div class="mt-barras">
        <div><span>Pedido</span><i style="width:100%"></i><b>${min(ex.pedido_min)} min</b></div>
        <div><span>Entregue</span><i class="curta" style="width:${Math.min(100, Math.round(ex.entregue_min / ex.pedido_min * 100))}%"></i><b>${min(ex.entregue_min)} min</b></div>
      </div>
      <p>${n(ex.palavras)} palavras viraram ${min(ex.entregue_min)} minutos: esta voz fala <b>${ex.ppm} palavras por minuto</b>, e não as ${ritmo.padrao} da conta padrão.</p></div>` : ""}
    <div class="mt-conta"><div><small>Antes</small><b>${n(antes)}</b><span>palavras para ${minutos} min</span></div><div class="seta">→</div>
      <div class="agora"><small>Agora</small><b>${n(agora)}</b><span>palavras para ${minutos} min</span></div></div>
    ${(ritmo.ultimos || []).length ? `<div class="mt-lista"><small>O que deu em cada vídeo (a margem é ${String((ritmo.acerto || {}).margem || 1.5).replace(".", ",")} min)</small>
      ${ritmo.ultimos.map((u) => `<div class="mt-linha ${u.dentro ? "dentro" : "fora"}"><span>${esc(u.titulo)}</span>
        <b>${u.pedido_min} → ${min(u.entregue_min)} min</b><i>${u.erro_min > 0 ? "+" : ""}${min(u.erro_min)}</i></div>`).join("")}</div>` : ""}
    <p class="sub">Vale a mediana dos últimos ${ritmo.medidos === 1 ? "vídeo" : `${ritmo.medidos} vídeos`} ${ritmo.de === "lingua" ? "nesta língua" : "desta voz"}, e o número vai se acertando a cada vídeo entregue. Você não precisa fazer nada.</p>
    <button class="botao vermelho grande" id="mt-ok">Entendi</button></div></div>`);
  const fechar = () => document.getElementById("ajuste-tempo")?.remove();
  document.getElementById("mt-ok").onclick = fechar;
  document.getElementById("ajuste-tempo").onclick = (e) => { if (e.target.id === "ajuste-tempo") fechar(); };
}

// ---------------------------------------------------------------- o aviso no computador quando o roteiro fica pronto
// Pedido do usuário em 2026-10-18: mandou fazer o roteiro, recebe uma notificação no PC quando ele fica pronto (em
// qualquer página do Radar). Os roteiros vigiados ficam no navegador, então o aviso continua depois de recarregar.

function pedirPermissaoNotificacao() {
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission().catch(() => {});
}
function notificar(titulo, corpo, destino) {
  aviso(`${titulo} ${corpo}`);
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  try {
    const n = new Notification(titulo, { body: corpo, tag: "radar-" + titulo + corpo, icon: document.querySelector("link[rel=icon]")?.href });
    n.onclick = () => { window.focus(); if (destino) location.hash = destino; n.close(); };
  } catch {}
}
function vigiarRoteiro(tarefa, tituloVideo) {
  const v = guardado("roteiros-vigiados", []);
  if (!v.some((x) => x.tarefa === tarefa)) guardar("roteiros-vigiados", [...v, { tarefa, titulo: tituloVideo }]);
  rodarVigia();
}
async function rodarVigia() {
  if (rodarVigia.ligado) return;
  rodarVigia.ligado = true;
  while (guardado("roteiros-vigiados", []).length) {
    await new Promise((r) => setTimeout(r, 4000));
    for (const { tarefa, titulo: t } of guardado("roteiros-vigiados", [])) {
      let estado;
      try { estado = await api(`/api/roteiros/tarefa/${tarefa}`); }
      catch (e) { if (e.status === 404) estado = { estado: "sumiu" }; else continue; }
      if (estado.estado === "rodando") continue;
      guardar("roteiros-vigiados", guardado("roteiros-vigiados", []).filter((x) => x.tarefa !== tarefa));
      if (estado.estado === "pronto" && estado.fabrica) notificar("🚀 Roteiro pronto e na fábrica", `“${t}” virou o projeto ${estado.fabrica.projeto}. Falta só dar o ▶ Produzir.`, "#/acompanhar");
      else if (estado.estado === "pronto") notificar("✅ Roteiro pronto", `“${t}” está pronto para você revisar${estado.erro_envio ? " (não foi para a fábrica: " + estado.erro_envio + ")" : ""}.`, "#/trabalho");
      else if (estado.estado === "erro") notificar("⚠ O roteiro não saiu", `“${t}”: ${estado.erro}`, "#/trabalho");
      if (document.getElementById("painel-ideias")?.hidden === false) painel();
    }
  }
  rodarVigia.ligado = false;
}

// ---------------------------------------------------------------- Acompanhar e Resultados (as produções da fábrica)
// Pedido do usuário em 2026-10-15, na organização do Robô do Dotti: uma aba para acompanhar a produção e outra para os
// resultados com o custo. Quem produz é a fábrica (editor na porta 8080); o Radar só mostra e manda produzir.

const minSeg = (s) => { s = Math.round(s || 0); return s >= 3600 ? `${Math.floor(s / 3600)}h${String(Math.floor(s % 3600 / 60)).padStart(2, "0")}` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
const dolar = (v) => v == null ? "—" : "US$ " + Number(v).toFixed(2).replace(".", ",");

// Produzir: primeiro a estimativa da fábrica, e só com o "sim" da pessoa a fábrica começa (é aí que gasta)
async function produzirNaFabrica(nome, titulo) {
  const est = await api(`/api/producoes/${encodeURIComponent(nome)}/produzir`, { method: "POST", body: { confirmar: false } });
  if (est.status === "processando") return aviso("Este vídeo já está sendo produzido.");
  const custo = est.custo_estimado_usd ? `\n\nImagens que faltam: ${est.sem_imagem_ia || 0} de IA e ${est.sem_acervo || 0} do acervo, uns ${dolar(est.custo_estimado_usd)}.` : "";
  if (!confirm(`Produzir "${titulo}" agora?\n\nA fábrica narra, monta as cenas, busca as imagens e renderiza. Isso gasta créditos (narração e imagens de IA), como no editor da fábrica.${custo}`)) return false;
  await api(`/api/producoes/${encodeURIComponent(nome)}/produzir`, { method: "POST", body: { confirmar: true } });
  aviso("A fábrica começou. Acompanhe na aba Acompanhar.");
  return true;
}

// o anel de porcentagem do vídeo aberto no Acompanhar
function anel(pct) {
  const r = 26, c = 2 * Math.PI * r;
  return `<svg class="anel" viewBox="0 0 64 64"><circle class="trilho" cx="32" cy="32" r="${r}"/>
    <circle class="cheio" cx="32" cy="32" r="${r}" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${(c * (1 - pct / 100)).toFixed(1)}"/></svg>
    <span class="anel-pct"><b>${pct}</b>%</span>`;
}

// Acompanhar novo (2026-10-18, no modelo do Robô do Dotti, feito do zero): à esquerda a fila em blocos (precisa de
// você, produzindo, na fila, entrada, parados); à direita o vídeo escolhido com as abas Acompanhamento, Diagnóstico
// (de onde vieram as cenas: real × IA, e o log), Arquivos e Tags e descrição. O vídeo aberto atualiza a cada 5 s, a
// lista a cada 20 s.
const BLOCOS_AC = [["precisa_voce", "✋ Precisa de você"], ["produzindo", "⚙️ Produzindo"], ["na_fila", "⏳ Na fila"],
  ["entrada", "📥 Entrada"], ["parados", "⏸ Parados na fábrica"]];
const ESTADO_FILA = { entrada: "Na Entrada", na_fila: "Na fila", escrevendo: "Escrevendo o roteiro", sua_vez: "Esperando sua revisão",
  enviando: "Enviando para a fábrica", produzindo: "Produzindo", erro: "Parou com erro", precisa_voce: "Precisa de você", parado: "Parado" };

async function acompanhar() {
  const A = { dados: null, escolhido: guardado("ac-escolhido", ""), aba: "acompanhamento", busca: "", canal: "", tipoLog: "todos" };
  tela.innerHTML = titulo("Acompanhar", "A fila da fábrica: o que precisa de você, o que está produzindo e o que espera a vez. Atualiza sozinho.", "acompanhar") +
    '<div class="acn" id="acn"><div class="vazio">Carregando…</div></div>';
  const raiz = document.getElementById("acn");
  const todos = () => BLOCOS_AC.flatMap(([k]) => A.dados?.[k] || []);
  const achar = (chave) => todos().find((x) => x.chave === chave);

  const cartao = (x) => {
    const pct = Math.round(x.progresso || 0);
    return `<button class="acn-item ${x.chave === A.escolhido ? "escolhido" : ""}" data-chave="${esc(x.chave)}">
      <span class="acn-item-topo"><span class="acn-estado e-${esc(x.estado)}">${esc(ESTADO_FILA[x.estado] || x.estado)}</span><small>${x.criado ? esc(ha(x.criado)) : ""}</small></span>
      <b>${esc(x.titulo)}</b><small>${esc(x.canal || "")}${x.passo && x.tipo === "fila" ? ` · ${esc(x.passo)}` : ""}</small>
      ${pct && x.estado !== "entrada" ? `<span class="acn-barra"><i style="width:${pct}%"></i></span>` : ""}</button>`;
  };

  const desenharLista = () => {
    const d = A.dados, canais = [...new Set(todos().map((x) => x.canal).filter(Boolean))];
    const filtro = (x) => (!A.busca || x.titulo.toLowerCase().includes(A.busca)) && (!A.canal || x.canal === A.canal);
    raiz.querySelector(".acn-lista").innerHTML = `
      <div class="acn-filtros"><input id="acn-busca" placeholder="Buscar título" value="${esc(A.busca)}">
        <select id="acn-canal"><option value="">Todos os canais</option>${canais.map((c) => `<option ${c === A.canal ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></div>
      ${BLOCOS_AC.map(([k, nome]) => { const itens = d[k].filter(filtro); return itens.length ? `<section class="acn-bloco b-${k}"><h3>${nome}<em>${itens.length}</em></h3>${itens.map(cartao).join("")}</section>` : ""; }).join("")
        || `<div class="ac-calmo"><div class="ac-calmo-ic">🏭</div><b>A fábrica está tranquila</b><span>Nada na fila.</span>${EU.admin ? '<button class="botao" id="acn-nova">+ Nova produção</button>' : ""}</div>`}`;
    raiz.querySelector("#acn-busca").oninput = (e) => { A.busca = e.target.value.toLowerCase(); desenharLista(); raiz.querySelector("#acn-busca").focus(); };
    raiz.querySelector("#acn-canal").onchange = (e) => { A.canal = e.target.value; desenharLista(); };
    raiz.querySelector("#acn-nova")?.addEventListener("click", () => novaProducao());
    raiz.querySelectorAll(".acn-item").forEach((b) => (b.onclick = () => {
      // roteiro mexido e não salvo: o primeiro clique só avisa; o segundo sai sem salvar
      if (A.sujo) { A.sujo = false; aviso("O roteiro tem alterações não salvas: clique em Salvar alterações, ou clique de novo para sair sem salvar."); return; }
      A.escolhido = b.dataset.chave; A.aba = "acompanhamento"; guardar("ac-escolhido", A.escolhido); desenharLista(); desenharVideo(); }));
  };

  const carregarLista = async () => {
    A.dados = await api("/api/acompanhar");
    const d = A.dados;
    if (!achar(A.escolhido)) A.escolhido = (todos()[0] || {}).chave || "";
    raiz.innerHTML = `<div class="acn-topo">
        <span class="acn-fabrica ${d.fabrica_ligada ? "ligada" : ""}"><i></i>Fábrica ${d.fabrica_ligada ? "ligada" : "desligada"}</span>
        <label class="acn-limite">${EU.admin ? `<select id="acn-limite">${[1, 2, 3, 4, 6, 8].map((n) => `<option value="${n}" ${n === d.limite ? "selected" : ""}>${n}</option>`).join("")}</select>` : `<b>${d.limite}</b>`} ao mesmo tempo</label>
        <span class="acn-num"><b>${d.numeros.produzindo}</b> produzindo</span><span class="acn-num"><b>${d.numeros.na_fila}</b> na fila</span>
        <span class="acn-num ${d.numeros.precisa_voce ? "alerta" : ""}"><b>${d.numeros.precisa_voce}</b> precisa${d.numeros.precisa_voce === 1 ? "" : "m"} de você</span>
        <span class="acn-num"><b>${d.prontos_hoje}</b> pronto${d.prontos_hoje === 1 ? "" : "s"} hoje · <a href="#/resultados">Resultados</a></span>
        ${EU.admin ? '<button class="botao" id="acn-nova-topo">+ Nova produção</button>' : ""}</div>
      <div class="acn-corpo"><div class="acn-lista"></div><div class="acn-video"></div></div>`;
    raiz.querySelector("#acn-limite")?.addEventListener("change", async (e) => {
      try { await api("/api/fila/ajustes", { method: "POST", body: { limite: Number(e.target.value) } }); aviso(`A fábrica faz até ${e.target.value} ao mesmo tempo.`); } catch (er) { aviso(er.message); }
    });
    raiz.querySelector("#acn-nova-topo")?.addEventListener("click", () => novaProducao());
    desenharLista(); desenharVideo();
  };

  const acao = (texto, classe, attr) => EU.admin ? `<button class="botao ${classe}" ${attr}>${texto}</button>` : "";

  async function desenharVideo() {
    const caixa = raiz.querySelector(".acn-video");
    const x = achar(A.escolhido);
    if (!x) { caixa.innerHTML = '<div class="vazio">Escolha um vídeo à esquerda.</div>'; return; }
    // pedido da fila que ainda não está na fábrica: o resumo do pedido e o que dá para fazer
    if (!x.projeto) {
      caixa.innerHTML = `<header class="acn-cab"><span class="acn-estado e-${esc(x.estado)}">${esc(ESTADO_FILA[x.estado])}</span>
          <h2>${esc(x.titulo)}</h2><small>${esc(x.canal || "sem canal")} · pedido ${esc(ha(x.criado))}</small></header>
        ${x.erro ? `<div class="chamada aviso">⚠ ${esc(x.erro)}</div>` : ""}
        <p class="acn-explica">${{ entrada: "Guardado na Entrada: não começa sozinho e não gasta nada.", na_fila: "Esperando a vez: começa quando a fábrica tiver vaga.",
          escrevendo: `O Claude está escrevendo o roteiro. ${esc(x.passo || "")}`, sua_vez: "O roteiro está pronto. Leia, ajuste se quiser e aprove para ir para a fábrica.",
          enviando: "Criando o projeto na fábrica…", erro: "Corrija o que o aviso diz e tente de novo." }[x.estado] || ""}</p>
        <div class="acn-acoes">${x.estado === "entrada" ? acao("▶ Começar", "", 'data-a="comecar"') : ""}
          ${x.estado === "erro" ? acao("↻ Tentar de novo", "", 'data-a="tentar"') : ""}
          ${acao("Excluir pedido", "contorno", 'data-a="excluir"')}</div>
        <div id="acn-revisao"></div>`;
      if (x.estado === "sua_vez") {
        const r = await api(`/api/fila/${x.id}/roteiro`);
        caixa.querySelector("#acn-revisao").innerHTML = `<label class="campo"><span>Roteiro (${r.palavras.toLocaleString("pt-BR")} palavras)</span>
          <textarea id="acn-texto" rows="16">${esc(r.roteiro)}</textarea></label>
          <div class="acn-acoes">${acao("Salvar alterações", "contorno", 'id="acn-salvar"')}${acao("✓ Aprovar e mandar para a fábrica", "", 'id="acn-aprovar"')}</div>`;
        // texto mexido e não salvo: a atualização automática não redesenha (antes, em 20 s, a edição sumia)
        caixa.querySelector("#acn-texto").oninput = () => { A.sujo = true; };
        const salvar = async () => {
          await api(`/api/roteiros/${encodeURIComponent(r.nome)}/texto`, { method: "POST", body: { roteiro: caixa.querySelector("#acn-texto").value } });
          A.sujo = false;
        };
        caixa.querySelector("#acn-salvar")?.addEventListener("click", (e) => carregando(e.currentTarget, "Salvando…", async () => { await salvar(); aviso("Roteiro salvo."); }));
        caixa.querySelector("#acn-aprovar")?.addEventListener("click", (e) => carregando(e.currentTarget, "Aprovando…", async () => {
          await salvar(); await api(`/api/fila/${x.id}/aprovar`, { method: "POST" }); aviso("Aprovado: vai para a fábrica na próxima vaga."); await carregarLista();
        }));
      }
      caixa.querySelectorAll("[data-a]").forEach((b) => (b.onclick = () => {
        if (b.dataset.a === "excluir") return confirmar(b, "Excluir este pedido?", async () => { await api(`/api/fila/${x.id}`, { method: "DELETE" }); await carregarLista(); });
        carregando(b, "…", async () => { await api(`/api/fila/${x.id}/${b.dataset.a}`, { method: "POST" }); await carregarLista(); });
      }));
      return;
    }
    // vídeo na fábrica: cabeçalho ao vivo e as quatro abas
    let v;
    try { v = await api(`/api/acompanhar/${encodeURIComponent(x.projeto)}`); } catch (e) { caixa.innerHTML = `<div class="vazio">${esc(e.message)}</div>`; return; }
    const st = v.status || {}, pct = Math.round(st.progresso_pct ?? x.progresso ?? (v.tem_final ? 100 : 0));
    const et = v.etapas;
    caixa.innerHTML = `<header class="acn-cab acn-cab-video"><div class="acn-anel">${anel(pct)}</div>
        <div><span class="acn-estado e-${esc(x.estado)}">${esc(ESTADO_FILA[x.estado] || x.estado)}</span><h2>${esc(v.titulo || x.titulo)}</h2>
        <small>${esc(x.canal || "")}${x.criado ? ` · pedido ${esc(ha(x.criado))}` : ""}${et.total ? ` · etapa ${et.passo} de ${et.total}` : ""}</small>
        <small class="acn-msg">› ${esc(et.mensagem || x.mensagem || "")}</small></div></header>
      ${v.pago_pendente ? `<div class="chamada aviso">Os modelos grátis acabaram: a fábrica espera você liberar o modelo pago. ${acao("Liberar o pago hoje", "", 'id="acn-pago"')}</div>` : ""}
      ${x.erro ? `<div class="chamada aviso">⚠ ${esc(x.erro)}</div>` : ""}
      <nav class="acn-abas">${[["acompanhamento", "Acompanhamento"], ["diagnostico", "Diagnóstico"], ["arquivos", "Arquivos"], ["tags", "Tags e descrição"]]
        .map(([id, n]) => `<button data-aba="${id}" class="${A.aba === id ? "ativa" : ""}">${n}</button>`).join("")}</nav>
      <div class="acn-aba"></div>
      <div class="acn-acoes acn-rodape">${x.tipo === "fila" && x.estado === "erro" ? acao("↻ Tentar de novo", "", 'data-a="tentar"') : ""}
        ${x.tipo === "fabrica" && x.estado !== "produzindo" ? acao(x.progresso ? "↻ Continuar" : "▶ Produzir", "", 'id="acn-produzir"') : ""}
        ${acao("Parar e apagar", "contorno perigo", 'id="acn-apagar"')}</div>`;
    caixa.querySelectorAll(".acn-abas button").forEach((b) => (b.onclick = () => { A.aba = b.dataset.aba; caixa.querySelectorAll(".acn-abas button").forEach((o) => o.classList.toggle("ativa", o === b)); desenharAba(v, x); }));
    caixa.querySelector("#acn-pago")?.addEventListener("click", (e) => carregando(e.currentTarget, "Liberando…", async () => { await api(`/api/acompanhar/${encodeURIComponent(x.projeto)}/pago`, { method: "POST" }); desenharVideo(); }));
    caixa.querySelector("[data-a=tentar]")?.addEventListener("click", (e) => carregando(e.currentTarget, "…", async () => { await api(`/api/fila/${x.id}/tentar`, { method: "POST" }); await carregarLista(); }));
    caixa.querySelector("#acn-produzir")?.addEventListener("click", (e) => carregando(e.currentTarget, "Consultando a fábrica…", async () => { if (await produzirNaFabrica(x.projeto, x.titulo)) await carregarLista(); }));
    caixa.querySelector("#acn-apagar")?.addEventListener("click", (e) => confirmar(e.currentTarget, "Parar a produção e apagar o projeto da fábrica?", async () => {
      await api(`/api/acompanhar/${encodeURIComponent(x.projeto)}`, { method: "DELETE" }); A.escolhido = ""; await carregarLista();
    }));
    desenharAba(v, x);
  }

  async function desenharAba(v, x) {
    const caixa = raiz.querySelector(".acn-aba");
    if (!caixa) return;
    const nome = encodeURIComponent(x.projeto);
    if (A.aba === "acompanhamento") {
      caixa.innerHTML = `<ol class="acn-etapas">${v.etapas.lista.map((e, i) => `<li class="${e.estado}"><span class="bola">${e.estado === "feita" ? "✓" : i + 1}</span>
          <b>${esc(e.nome)}</b><small>${e.estado === "agora" ? "em andamento" : e.estado === "feita" ? (e.tempo || "feita") : "a seguir"}</small></li>`).join("")}</ol>
        <p class="acn-explica">O Robô continua mesmo com esta página fechada. Quando o vídeo ficar pronto, ele aparece em Arquivos e em Resultados.</p>`;
    } else if (A.aba === "diagnostico") {
      const d = await api(`/api/acompanhar/${nome}/diagnostico?tipo=${A.tipoLog}`);
      const c = d.contagem, feitas = c.total - c.pendente || 1;
      const parte = (n, classe, rotulo) => n ? `<i class="${classe}" style="width:${(n / feitas * 100).toFixed(1)}%" title="${rotulo}: ${n}"></i>` : "";
      caixa.innerHTML = `<h3>De onde vieram as cenas</h3>
        ${c.total ? `<div class="acn-ia"><div class="acn-ia-barra">${parte(c.real, "real", "Filmagem/foto real")}${parte(c.imagem_ia, "img", "Imagem de IA")}${parte(c.animacao, "anim", "Animation IA")}</div>
          <ul class="acn-ia-legenda"><li><i class="real"></i><b>${c.real}</b> reais</li><li><i class="img"></i><b>${c.imagem_ia}</b> imagens de IA</li>
            <li><i class="anim"></i><b>${c.animacao}</b> Animation IA</li>${c.pendente ? `<li><b>${c.pendente}</b> ainda sem material</li>` : ""}</ul>
          <p class="acn-pct"><b>${String(c.pct_ia).replace(".", ",")}%</b> das cenas feitas por IA · ${c.total} cenas</p></div>`
          : '<p class="acn-explica">As cenas ainda não foram definidas.</p>'}
        <div class="acn-log-cab"><h3>Log da produção</h3><div class="chips">${[["todos", "Todos"], ["info", "Informação"], ["concluido", "Concluído"], ["aviso", "Aviso"], ["erro", "Erro"]]
          .map(([t, n]) => `<button class="chip ${A.tipoLog === t ? "ativo" : ""}" data-tipo="${t}">${n}</button>`).join("")}</div>
          <a class="botao contorno" href="/api/acompanhar/${nome}/log.txt">Baixar log</a></div>
        <div class="acn-log">${d.log.slice().reverse().map((l) => `<div class="l-${l.tipo}">${esc(l.texto)}</div>`).join("") || '<div class="vazio">Nada no log.</div>'}</div>`;
      caixa.querySelectorAll("[data-tipo]").forEach((b) => (b.onclick = () => { A.tipoLog = b.dataset.tipo; desenharAba(v, x); }));
    } else if (A.aba === "arquivos") {
      caixa.innerHTML = v.tem_final ? `<div class="acn-arquivos">
          <button class="botao" id="acn-assistir">▶ Assistir o vídeo</button>
          ${v.legenda ? `<a class="botao contorno" href="/api/acompanhar/${nome}/legenda">Baixar a legenda (.srt)</a>` : ""}
          <button class="botao contorno" id="acn-pasta">📁 Abrir pasta</button></div>
          <p class="acn-explica">Os shorts, as thumbnails e o custo ficam em <a href="#/resultados">Resultados</a>.</p>`
        : '<p class="acn-explica">O vídeo final e a legenda aparecem aqui quando a produção terminar.</p>';
      caixa.querySelector("#acn-assistir")?.addEventListener("click", () => window.open(`/api/producoes/${nome}/video`, "_blank"));
      caixa.querySelector("#acn-pasta")?.addEventListener("click", (e) => carregando(e.currentTarget, "Abrindo…", () => api(`/api/producoes/${nome}/pasta`, { method: "POST" })));
    } else {
      const p = await api(`/api/acompanhar/${nome}/publicacao`).catch((e) => ({ erro: e.message }));
      const pub = p.publicacao;
      const copiar = (rotulo, texto) => texto ? `<div class="acn-pub"><div class="acn-pub-cab"><b>${rotulo}</b><button class="link-editar" data-copiar="${esc(texto)}">Copiar</button></div><pre>${esc(texto)}</pre></div>` : "";
      caixa.innerHTML = p.erro ? `<p class="acn-explica">${esc(p.erro)}</p>` : pub ? copiar("Título", pub.titulo) + copiar("Descrição", pub.descricao)
          + copiar("Tags", (pub.tags || []).join(", ")) + copiar("Capítulos", (pub.capitulos || []).map((c) => `${c.tempo} ${c.nome}`).join("\n"))
          + copiar("Comentário fixado", pub.comentario_fixado)
        : `<p class="acn-explica">${p.rodando ? "A fábrica está montando a descrição e as tags…" : "A descrição, as tags e os capítulos ainda não foram feitos."}</p>
          ${p.rodando ? "" : acao("Gerar descrição e tags", "", 'id="acn-gerar"')}`;
      caixa.querySelectorAll("[data-copiar]").forEach((b) => (b.onclick = async () => { await navigator.clipboard.writeText(b.dataset.copiar); aviso("Copiado."); }));
      caixa.querySelector("#acn-gerar")?.addEventListener("click", (e) => carregando(e.currentTarget, "Pedindo à fábrica…", async () => {
        await api(`/api/acompanhar/${nome}/publicacao`, { method: "POST" }); aviso("A fábrica começou a montar: volta em alguns segundos."); desenharAba(v, x);
      }));
    }
  }

  try { await carregarLista(); } catch (e) { raiz.innerHTML = `<div class="vazio">${esc(e.message)}</div>`; return; }
  // o vídeo aberto a cada 5 s (sem mexer na aba de log/arquivos, que a pessoa pode estar lendo) e a lista a cada 20 s
  let voltas = 0;
  clearInterval(acompanhar.relogio);
  acompanhar.relogio = setInterval(async () => {
    if (rotaAtual() !== "acompanhar" || !document.getElementById("acn")) { clearInterval(acompanhar.relogio); return; }
    if (A.sujo || document.querySelector("#acn textarea:focus, #acn input:focus")) return;
    voltas += 1;
    try {
      if (voltas % 4 === 0) await carregarLista();
      else if (A.aba === "acompanhamento" && achar(A.escolhido)?.projeto) await desenharVideo();
    } catch {}
  }, 5000);
}

// confirmação dentro da página (nunca o confirm do navegador): o botão vira "Sim / Não"
function confirmar(botao, pergunta, tarefa) {
  const caixa = document.createElement("span");
  caixa.className = "confirmar";
  caixa.innerHTML = `<span>${esc(pergunta)}</span><button class="botao vermelho">Sim</button><button class="botao contorno">Não</button>`;
  botao.replaceWith(caixa);
  const [, sim, nao] = caixa.children;
  nao.onclick = () => caixa.replaceWith(botao);
  sim.onclick = () => carregando(sim, "…", async () => { await tarefa(); });
}

// avisos da fila no computador, em qualquer página: entregue, esperando sua revisão e erro (uma vez por mudança)
async function vigiarFila() {
  if (!EU?.admin) return;
  try {
    const { itens } = await api("/api/fila");
    const vistos = guardado("fila-estados", {});
    for (const i of itens) {
      if (vistos[i.id] && vistos[i.id] !== i.estado) {
        const t = i.pedido.titulo;
        if (i.estado === "entregue") notificar("🎬 Vídeo pronto", `“${t}” foi entregue pela fábrica.`, "#/resultados");
        if (i.estado === "sua_vez") notificar("✍️ Roteiro para revisar", `“${t}” espera sua aprovação no Acompanhar.`, "#/acompanhar");
        if (i.estado === "erro") notificar("⚠ A produção parou", `“${t}”: ${i.erro}`, "#/acompanhar");
      }
      vistos[i.id] = i.estado;
    }
    guardar("fila-estados", vistos);
  } catch {}
}

// Resultados: os vídeos prontos em linhas limpas, centralizados (pedidos do usuário em 2026-10-15: dividir por canal,
// ver só o canal que quiser, arrastar para outro canal, os shorts de cada vídeo, publicado ✓ e as views).
const CUSTOS_VISTOS = {};
const PADRAO_RESULTADOS = { canal: "" };
async function resultados() {
  const f = recorte(PADRAO_RESULTADOS);
  tela.innerHTML = `<div class="resultados">
    <header class="produzir-cab"><div><h1>Seus vídeos prontos</h1><p>O custo de cada vídeo, os shorts e o que já foi publicado. Arraste um vídeo para a aba de outro canal para mudar o canal dele.</p></div></header>
    <nav class="res-abas" id="res-filtro"></nav>
    <div class="res-resumo" id="res-resumo"></div>
    <div id="res-lista"><div class="vazio">Carregando…</div></div></div>`;
  let d, movidos, manuais;
  try {
    [d, { canais: movidos }, { publicados: manuais }] = await Promise.all([api("/api/producoes"), api("/api/resultados/canais"), api("/api/resultados/publicados"), meusCanais()]);
  } catch (e) { document.getElementById("res-lista").innerHTML = `<div class="vazio">${esc(e.message)}</div>`; return; }
  const todos = d.prontos.map((p) => ({ ...p, canal: movidos[p.nome] || p.canal,
    publicado: p.publicado || (manuais[p.nome] ? (manuais[p.nome] === "-" ? { video_id: "", url: "", pela: "pessoa" }
      : { video_id: manuais[p.nome], url: `https://youtu.be/${manuais[p.nome]}`, pela: "pessoa" }) : null) }));
  const nomes = [...new Set([...(MEUS || []).map((c) => c.titulo), ...todos.map((p) => p.canal)])];
  // canal do endereço que não existe mais: nenhuma aba acenderia e a lista viria vazia sem explicação
  if (f.canal && !nomes.includes(f.canal)) { f.canal = ""; recorteParaOEndereco(f, PADRAO_RESULTADOS); }
  const filtro = f.canal;
  document.getElementById("res-filtro").innerHTML = ["", ...nomes].map((n) => `<button class="res-aba ${n === filtro ? "ativa" : ""}" data-filtro="${esc(n)}" data-canal-alvo="${esc(n)}">
    ${n ? esc(n) : "Todos"} <span class="n">${n ? todos.filter((p) => p.canal === n).length : todos.length}</span></button>`).join("");
  // a aba "Todos" é o próprio voltar ao padrão desta tela
  document.querySelectorAll("[data-filtro]").forEach((b) => (b.onclick = () => { f.canal = b.dataset.filtro; recorteParaOEndereco(f, PADRAO_RESULTADOS); resultados(); }));
  const lista = todos.filter((p) => !filtro || p.canal === filtro);
  const caixa = document.getElementById("res-lista");

  const linha = (p) => `<article class="res-linha" draggable="true" data-nome="${esc(p.nome)}">
      <div class="res-capa">${p.capa ? `<img src="${esc(p.capa)}" alt="" draggable="false">` : '<div class="prod-sem-capa">🎬</div>'}<span class="dur">${minSeg(p.duracao)}</span>
        <button class="res-play" data-assistir="${esc(p.nome)}" title="Assistir">▶</button></div>
      <div class="res-info"><b>${esc(p.titulo)}</b>
        <small>${esc(p.canal)} · ${p.criado ? new Date(p.criado).toLocaleDateString("pt-BR") : ""} · ${minSeg(p.duracao)} · ${p.cenas} cenas</small>
        <div class="res-selos">${p.publicado
          ? `${p.publicado.url ? `<a class="selo-pub sim" href="${esc(p.publicado.url)}" target="_blank" rel="noopener">✓ Publicado</a>` : '<span class="selo-pub sim">✓ Publicado</span>'}${p.publicado.pela === "pessoa" ? `<button class="selo-x" data-despublicar="${esc(p.nome)}" title="Desmarcar">×</button>` : ""}
             ${p.publicado.video_id ? `<span class="res-views" data-views="${esc(p.publicado.video_id)}">…</span>` : ""}`
          : `<button class="selo-pub" data-publicar="${esc(p.nome)}" title="Cole o link do vídeo no YouTube">Marcar como publicado</button>`}</div>
        ${p.shorts && p.shorts.length ? `<div class="res-shorts"><span>Shorts</span>${p.shorts.map((s, i) => `<button data-short="${esc(p.nome)}" data-sid="${esc(s.id)}" title="${esc(s.titulo || "")}">▶ ${i + 1}</button>`).join("")}</div>` : ""}
      </div>
      <div class="res-direita"><div class="res-custo">${CUSTOS_VISTOS[p.nome] ? CUSTOS_VISTOS[p.nome].html : '<span class="sub">calculando…</span>'}</div>
        <div class="video-acoes"><button class="botao sec" data-assistir="${esc(p.nome)}">▶ Assistir</button><button class="botao sec" data-pasta="${esc(p.nome)}">📁 Pasta</button></div></div>
    </article>`;
  const grupos = (filtro ? [filtro] : nomes).map((n) => [n, lista.filter((p) => p.canal === n)])
    .filter(([n, vs]) => vs.length || filtro);
  caixa.innerHTML = grupos.map(([canal, vs]) => `<section class="res-grupo" data-canal-alvo="${esc(canal)}">
      ${filtro ? "" : `<h2>${esc(canal)} <small>${vs.length} ${vs.length === 1 ? "vídeo" : "vídeos"} · <span class="res-tot"></span></small></h2>`}
      <div class="res-linhas">${vs.map(linha).join("") || '<div class="res-vazio">Nenhum vídeo neste canal. Arraste um vídeo para a aba dele.</div>'}</div></section>`).join("")
    || '<div class="vazio">Nenhum vídeo pronto ainda.</div>';

  const achar = (nome) => todos.find((x) => x.nome === nome);
  caixa.querySelectorAll("[data-assistir]").forEach((b) => (b.onclick = (e) => { e.stopPropagation(); assistir(b.dataset.assistir, achar(b.dataset.assistir).titulo); }));
  caixa.querySelectorAll("[data-short]").forEach((b) => (b.onclick = () => assistir(b.dataset.short, `${achar(b.dataset.short).titulo} · ${b.textContent.trim()}`, b.dataset.sid)));
  caixa.querySelectorAll("[data-pasta]").forEach((b) => (b.onclick = () => api(`/api/producoes/${encodeURIComponent(b.dataset.pasta)}/pasta`, { method: "POST", body: {} }).catch((e) => aviso(porque(e)))));
  caixa.querySelectorAll("[data-publicar]").forEach((b) => (b.onclick = async () => {
    const link = prompt("Cole o link do vídeo publicado no YouTube:");
    if (!link) return;
    try { await api(`/api/resultados/${encodeURIComponent(b.dataset.publicar)}/publicado`, { method: "POST", body: { link } }); resultados(); } catch (e) { aviso(porque(e)); }
  }));
  caixa.querySelectorAll("[data-despublicar]").forEach((b) => (b.onclick = async () => {
    await api(`/api/resultados/${encodeURIComponent(b.dataset.despublicar)}/publicado`, { method: "POST", body: { link: "" } }); resultados();
  }));
  // arrastar: a linha vai para a aba (ou o bloco) de outro canal
  caixa.querySelectorAll(".res-linha").forEach((c) => {
    c.ondragstart = (e) => { e.dataTransfer.setData("text/plain", c.dataset.nome); c.classList.add("arrastando"); };
    c.ondragend = () => c.classList.remove("arrastando");
  });
  document.querySelectorAll("[data-canal-alvo]").forEach((alvo) => {
    if (!alvo.dataset.canalAlvo) return;
    alvo.ondragover = (e) => { e.preventDefault(); alvo.classList.add("solta-aqui"); };
    alvo.ondragleave = () => alvo.classList.remove("solta-aqui");
    alvo.ondrop = async (e) => {
      e.preventDefault(); alvo.classList.remove("solta-aqui");
      const p = achar(e.dataTransfer.getData("text/plain")), canal = alvo.dataset.canalAlvo;
      if (!p || p.canal === canal) return;
      await api(`/api/resultados/${encodeURIComponent(p.nome)}/canal`, { method: "POST", body: { canal } });
      aviso(`“${p.titulo}” agora está em ${canal}.`);
      resultados();
    };
  });
  // as views dos publicados (1 unidade da cota a cada 50 vídeos)
  const ids = lista.filter((p) => p.publicado && p.publicado.video_id).map((p) => p.publicado.video_id);
  if (ids.length) api("/api/resultados/views", { method: "POST", body: { ids } }).then(({ videos }) => {
    caixa.querySelectorAll("[data-views]").forEach((el) => {
      const v = videos[el.dataset.views];
      el.textContent = v ? `👁 ${num(v.views)} views${v.curtidas != null ? ` · 👍 ${num(v.curtidas)}` : ""}` : "";
    });
  }).catch(() => caixa.querySelectorAll("[data-views]").forEach((el) => (el.textContent = "")));
  // o custo de cada vídeo e os totais
  const resumo = () => {
    const somados = lista.filter((p) => CUSTOS_VISTOS[p.nome]);
    const total = somados.reduce((s, p) => s + CUSTOS_VISTOS[p.nome].total, 0), minutos = somados.reduce((s, p) => s + CUSTOS_VISTOS[p.nome].minutos, 0);
    document.getElementById("res-resumo").innerHTML = `<div class="kpi"><span>Vídeos</span><b>${lista.length}</b></div>
      <div class="kpi"><span>Publicados</span><b>${lista.filter((p) => p.publicado).length}</b></div>
      <div class="kpi"><span>Gasto total</span><b>${dolar(total)}</b></div>
      <div class="kpi"><span>Custo por minuto</span><b>${dolar(minutos ? total / minutos : 0)}</b></div>`;
    grupos.forEach(([canal, vs]) => {
      const el = caixa.querySelector(`[data-canal-alvo="${CSS.escape(canal)}"] .res-tot`);
      if (el) el.textContent = `${dolar(vs.reduce((s, p) => s + ((CUSTOS_VISTOS[p.nome] || {}).total || 0), 0))} gastos`;
    });
  };
  resumo();
  for (const p of lista) {
    if (CUSTOS_VISTOS[p.nome]) continue;
    const lugar = caixa.querySelector(`[data-nome="${CSS.escape(p.nome)}"] .res-custo`);
    try {
      const c = await api(`/api/producoes/${encodeURIComponent(p.nome)}/custo`);
      const partes = Object.entries(c.por_categoria || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, 3)
        .map(([k, v]) => `${({ narracao: "narração", imagem: "imagens", visao: "visão", juiz: "juiz", texto: "texto" })[k] || k} ${dolar(v)}`).join(" · ");
      const html = `<b>${dolar(c.total_usd)}</b><span class="sub">${dolar(c.por_minuto_usd)} por minuto</span><small>${esc(partes)}</small>`;
      CUSTOS_VISTOS[p.nome] = { html, total: c.total_usd || 0, minutos: (c.duracao_segundos || 0) / 60 };
      if (lugar) lugar.innerHTML = html;
      resumo();
    } catch (e) { if (lugar) lugar.innerHTML = `<span class="sub">${esc(e.message)}</span>`; }
    if (rotaAtual() !== "resultados") return;
  }
}

function assistir(nome, tituloVideo, short = "") {
  let modal = document.getElementById("modal-video");
  if (!modal) {
    document.body.insertAdjacentHTML("beforeend", '<div id="modal-video" class="modal-fundo"><div class="modal modal-video"></div></div>');
    modal = document.getElementById("modal-video");
    modal.onclick = (e) => { if (e.target === modal || e.target.closest(".fechar-modal")) { modal.hidden = true; modal.querySelector("video")?.pause(); } };
  }
  modal.hidden = false;
  modal.querySelector(".modal").classList.toggle("em-pe", !!short);
  const src = short ? `/api/producoes/${encodeURIComponent(nome)}/shorts/${encodeURIComponent(short)}` : `/api/producoes/${encodeURIComponent(nome)}/video`;
  modal.querySelector(".modal").innerHTML = `<div class="painel-cab"><b>${esc(tituloVideo)}</b><button class="botao sec fechar-modal">×</button></div>
    <video src="${src}" controls autoplay style="width:100%;border-radius:12px;background:#000;max-height:78vh"></video>`;
}


// ---------------------------------------------------------------- o Assistente: a janela de IA à direita

const ATALHOS = [
  ["🌍 Regionalizar", (t) => `Adapte este título para o público dos EUA, do Reino Unido e da Austrália (uma versão para cada), sem perder a ideia: "${t}"`],
  ["🔥 Mais chamativo", (t) => `Me dê 5 versões mais chamativas deste título, sem enganar quem clica: "${t}"`],
  ["🇺🇸 Para o inglês", (t) => `Reescreva este título em inglês, do jeito que um canal americano grande escreveria: "${t}"`],
  ["📝 Descrição", (t) => `Escreva a descrição de YouTube (3 parágrafos curtos e 5 hashtags) para o vídeo "${t}"`],
];

// os títulos de uma resposta (linhas numeradas ou com marcador), para o botão "usar"
const titulosDaResposta = (texto) => {
  // o que está entre aspas é o título ("EUA: “15 Rarest…”" → só o título); sem aspas, as linhas numeradas
  const limpo = texto.replace(/\*\*/g, "");
  const aspas = [...limpo.matchAll(/["“]([^"”\n]{8,140})["”]/g)].map((m) => m[1].trim()).filter((x) => x.split(/\s+/).length >= 4);   // trecho curto citado na explicação não é título
  if (aspas.length) return [...new Set(aspas)];
  return limpo.split("\n").map((l) => (l.match(/^\s*(?:\d+[.)]|[-•*])\s+(.+)$/) || [])[1]).filter(Boolean)
    .map((l) => l.trim()).filter((l) => l.length >= 8 && l.length <= 140);
};

async function montarAssistente(caixa, obterTitulo = () => "", opcoes = {}) {
  const canais = await meusCanais();
  let canal = guardado("assistente-canal", "");
  caixa.innerHTML = `<div class="assist-cab"><b>💬 Assistente</b>
      <select id="as-canal" data-dica="O canal do Assistente é à parte: ele usa os dados deste canal para responder."><option value="">Sem canal</option>${canais.map((c) => `<option value="${esc(c.id)}" ${c.id === canal ? "selected" : ""}>${esc(c.titulo)}</option>`).join("")}</select>
      <button class="botao sec" id="as-limpar" data-dica="Começar uma conversa nova">↺</button></div>
    <div class="assist-msgs" id="as-msgs"></div>
    <div class="assist-atalhos">${ATALHOS.map(([t], i) => `<button class="chip" data-i="${i}">${t}</button>`).join("")}</div>
    <textarea id="as-texto" rows="3" placeholder="Peça qualquer coisa: regionalizar o título, deixar mais chamativo, traduzir, mudar o gancho…"></textarea>
    <button class="botao" id="as-enviar">Enviar</button>`;
  const $ = (id) => caixa.querySelector("#" + id);
  const chave = () => "assistente:" + (canal || "geral");
  let conversa = guardado(chave(), []);
  const desenhar = () => {
    $("as-msgs").innerHTML = conversa.length ? conversa.map((m, i) => `<div class="msg ${m.papel}">${esc(m.texto).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")}${m.papel === "assistente"
      ? `<button class="copiar-msg" data-i="${i}" title="Copiar">⧉</button>${opcoes.aoUsar ? titulosDaResposta(m.texto).map((tt) =>
        `<button class="usar-titulo" data-t="${esc(tt)}">usar</button>`).length ? `<div class="usar-linhas">${titulosDaResposta(m.texto).map((tt) =>
        `<button class="usar-titulo" data-t="${esc(tt)}" title="Usar este título">↳ usar: ${esc(tt)}</button>`).join("")}</div>` : "" : ""}` : ""}</div>`).join("")
      : '<div class="sub">Converse com o Claude sobre o vídeo: ele vê os dados do canal escolhido aqui em cima.</div>';
    $("as-msgs").scrollTop = $("as-msgs").scrollHeight;
    $("as-msgs").querySelectorAll(".copiar-msg").forEach((b) => (b.onclick = () => { navigator.clipboard.writeText(conversa[+b.dataset.i].texto); b.textContent = "✓"; }));
    $("as-msgs").querySelectorAll(".usar-titulo").forEach((b) => (b.onclick = () => opcoes.aoUsar(b.dataset.t)));
  };
  const enviar = async () => {
    const texto = $("as-texto").value.trim();
    if (!texto) return;
    conversa.push({ papel: "pessoa", texto }); $("as-texto").value = ""; desenhar();
    $("as-msgs").insertAdjacentHTML("beforeend", '<div class="msg assistente pensando">Pensando…</div>');
    $("as-enviar").disabled = true;
    try {
      const r = await api("/api/assistente", { method: "POST", body: { canal_id: canal, mensagens: conversa } });
      conversa.push({ papel: "assistente", texto: r.resposta });
    } catch (e) { conversa.push({ papel: "assistente", texto: "⚠ " + e.message }); }
    guardar(chave(), conversa.slice(-30)); $("as-enviar").disabled = false; desenhar();
  };
  $("as-enviar").onclick = enviar;
  $("as-texto").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); } };
  $("as-canal").onchange = () => { canal = $("as-canal").value; guardar("assistente-canal", canal); conversa = guardado(chave(), []); desenhar(); };
  $("as-limpar").onclick = () => { conversa = []; guardar(chave(), []); desenhar(); };
  caixa.querySelectorAll(".assist-atalhos .chip").forEach((b) => (b.onclick = () => {
    const t = obterTitulo() || "COLE O TÍTULO AQUI";
    $("as-texto").value = ATALHOS[+b.dataset.i][1](t); $("as-texto").focus();
  }));
  desenhar();
}

// ---------------------------------------------------------------- Meus canais (as abas de canal) e Ideias

let MEUS = null;              // os canais da pessoa, para as abas e para o "Salvar ideia"
let CANAL_ATUAL = "";         // o canal da aba aberta em Ideias ou no Treino: o "Salvar ideia" vai direto para ele
async function meusCanais(recarregar = false) {
  if (!MEUS || recarregar) MEUS = (await api("/api/meus-canais")).canais;
  return MEUS;
}

function abasDeCanal(canais, atual, rota) {
  return `<div class="chips abas-canal">${canais.map((c) => `<a class="chip ${c.id === atual ? "ativo" : ""}" href="#/${rota}/${esc(c.id)}">
    <img src="${esc(c.foto)}" alt="" referrerpolicy="no-referrer" style="width:18px;height:18px;border-radius:50%;vertical-align:middle;margin-right:6px">${esc(c.titulo)}</a>`).join("")}</div>`;
}

function semCanais(texto) {
  return `<div class="vazio">${texto}<br><br><a class="botao vermelho" href="#/canais/novo">Adicionar um canal</a></div>`;
}

const PADRAO_IDEIAS_CANAL = { lingua: "ptenes", nota_min: "3", publicado_dias: "", formato: "longo", inscritos_max: "", ordem: "parecido" };

// as ideias de um canal da pessoa, com filtros e o aleatório (na aba Ideias e na página do canal)
async function componenteIdeias(caixa, canalId) {
  const f = recorte(PADRAO_IDEIAS_CANAL);
  caixa.innerHTML = `<div class="grande-acao"><button class="botao vermelho" id="ic-youtube" data-dica="Procura no YouTube agora vídeos que estão estourando no assunto que você ensinou ao algoritmo (🎯, treino e canais inscritos). Cada clique busca de um jeito diferente. Gasta uns 250 da cota grátis.">🔄 Buscar ideias novas</button>
    ${selects([
      ["lingua", "", [["ptenes", "Português, inglês e espanhol"], ["pt", "Só português"], ["en", "Só inglês"], ["es", "Só espanhol"], ["todas", "Todas as línguas"]]],
      ["nota_min", "", [[3, "3x o normal ou mais"], [5, "5x ou mais"], [10, "10x ou mais"], [20, "20x ou mais"]]],
      ["publicado_dias", "Qualquer data", [[7, "Últimos 7 dias"], [30, "Últimos 30 dias"], [90, "Últimos 3 meses"], [365, "Último ano"]]],
      ["formato", "Longos e Shorts", [["longo", "Só vídeos longos"], ["curto", "Só Shorts"]]],
      ["inscritos_max", "Canal de qualquer tamanho", [[10000, "Só canal pequeno (até 10 mil)"], [100000, "Até 100 mil inscritos"]]],
      ["ordem", "", [["parecido", "Mais parecidos primeiro"], ["nota", "Maior nota"], ["recente", "Mais recentes"], ["views", "Mais views"], ["aleatorio", "Aleatório"]]],
    ], f)}</div>
    <div id="ic-do-youtube"></div>
    <div class="contagem" id="ic-contagem"></div><div class="grade-videos" id="ic-lista"></div>
    <div class="mais"><button class="botao sec" id="ic-mais" hidden>Carregar mais</button></div>`;
  let pagina = 0, tentativa = 0;
  const carregar = async (mais = false) => {
    pagina = mais ? pagina + 1 : 0;
    const { videos, total } = await api(`/api/meus-canais/${encodeURIComponent(canalId)}/ideias?` + consulta({ ...f, pagina }));
    const lista = caixa.querySelector("#ic-lista");
    const html = videos.map((v) => cartaoVideo(v)).join("");
    if (mais) lista.insertAdjacentHTML("beforeend", html);
    else lista.innerHTML = html || '<div class="vazio" style="grid-column:1/-1">Nenhuma ideia com essas escolhas. Use o botão "Buscar mais no YouTube".</div>';
    caixa.querySelector("#ic-contagem").textContent = `${total} ideias`;
    caixa.querySelector("#ic-mais").hidden = lista.querySelectorAll(".video").length >= total;
    ligarRoteiro(lista);
  };
  ligarSelects(caixa, f, PADRAO_IDEIAS_CANAL, () => carregar());
  caixa.querySelector("#ic-mais").onclick = () => carregar(true);
  // 🔄 busca ideias novas no YouTube pelo que a pessoa ensinou ao algoritmo; as novas aparecem em cima e entram na lista
  caixa.querySelector("#ic-youtube").onclick = (e) => carregando(e.currentTarget, "Procurando ideias novas no YouTube…", async () => {
    const r = await api(`/api/perfil/canal/${encodeURIComponent(canalId)}/ideias`, { method: "POST", body: { tentativa } });
    tentativa = r.proxima;
    const sai = caixa.querySelector("#ic-do-youtube");
    sai.innerHTML = `<div class="bloco novas-ideias"><h3>🔄 Ideias novas de agora</h3>
      <p class="sub">Procurei <b>${esc(r.buscas.join(", "))}</b> (${esc(r.jeito)}): ${r.videos.length} ${r.videos.length === 1 ? "vídeo" : "vídeos"} acima do normal do canal. Clique de novo para buscar de outro jeito.</p>
      <div class="grade-videos">${r.videos.map((v) => cartaoVideo(v)).join("") || '<span class="sub">Nada novo desta vez. Marque mais 🎯 para o algoritmo entender melhor.</span>'}</div></div>`;
    ligarRoteiro(sai);
    carregar();
  });
  carregar();
}

// ---------------------------------------------------------------- treinamento do algoritmo, no site

async function assistenteTreino(caixa, canal, aoTerminar) {
  const est = await api(`/api/treinamento/${encodeURIComponent(canal.id)}`);
  const escolhidos = new Map(), recusados = new Set(), vistos = new Set();
  caixa.innerHTML = `<div id="tr-faixa">${faixaPassos(1)}</div>
    <div class="passo"><h2><span class="n">1</span>Canais de referência</h2>
      <p class="sub" style="margin:0">Cole de 1 a 3 canais (@ ou link) que são o modelo do <b>${esc(canal.titulo)}</b>: o tipo de vídeo que você quer fazer. Um por linha.</p>
      <textarea id="tr-refs" rows="3" placeholder="@canalmodelo1&#10;@canalmodelo2">${esc(est.referencias.map((r) => r.handle || r.id).join("\n"))}</textarea>
      <div class="linha"><button class="botao" id="tr-usar">Usar estes canais</button>
        <a href="#" id="tr-pular" class="sub" style="color:var(--fraco)">pular: usar só o meu canal</a></div>
      <div id="tr-refs-ok"></div></div>
    <div class="passo" id="tr-passo2" hidden><h2><span class="n">2</span>Escolha os vídeos que você faria</h2>
      <p class="sub" style="margin:0">Marque <b style="color:var(--verde)">✓ Faria</b> nos vídeos do jeito que você quer, e <b style="color:var(--vermelho-claro)">✕ Não</b> nos que não têm nada a ver. Escolha de ${est.minimo} a ${est.maximo}.</p>
      <div class="barra-treino"><b id="tr-conta">0 escolhidos</b><span class="sub">mínimo ${est.minimo}, ideal ${est.maximo}</span>
        <button class="botao sec" id="tr-mais">Mostrar outros vídeos</button><button class="botao vermelho" id="tr-treinar" disabled>Treinar com os escolhidos</button></div>
      <div class="grade-videos" id="tr-videos"></div></div>
    <div id="tr-fim"></div>`;
  const $ = (id) => caixa.querySelector("#" + id);
  const conta = () => {
    const n = escolhidos.size;
    $("tr-conta").textContent = `${n} ${n === 1 ? "escolhido" : "escolhidos"}`;
    $("tr-treinar").disabled = n < est.minimo;
  };
  const mostrar = async () => {
    const { videos } = await api(`/api/treinamento/${encodeURIComponent(canal.id)}/candidatos`, { method: "POST", body: { excluir: [...vistos] } });
    videos.forEach((v) => vistos.add(v.id));
    $("tr-videos").innerHTML = videos.map((v) => `<div class="video escolha" data-id="${esc(v.id)}">${capaDoVideo({ ...v, nota: null })}
      <span class="titulo">${esc(v.titulo)}</span><div class="meta">${num(v.views)} views · ${esc(v.canal)}</div>
      <div class="video-acoes"><button class="botao sec sim">✓ Faria</button><button class="botao sec nao">✕ Não</button></div></div>`).join("")
      || '<div class="vazio" style="grid-column:1/-1">Acabaram os vídeos deste assunto na base. Treine com os escolhidos ou cole outros canais de referência.</div>';
    $("tr-videos").querySelectorAll(".escolha").forEach((card) => {
      const id = card.dataset.id;
      card.querySelector(".sim").onclick = () => {
        if (escolhidos.has(id)) escolhidos.delete(id); else { escolhidos.set(id, true); recusados.delete(id); }
        card.classList.toggle("marcado-sim", escolhidos.has(id)); card.classList.remove("marcado-nao"); conta();
      };
      card.querySelector(".nao").onclick = () => {
        if (recusados.has(id)) recusados.delete(id); else { recusados.add(id); escolhidos.delete(id); }
        card.classList.toggle("marcado-nao", recusados.has(id)); card.classList.remove("marcado-sim"); conta();
      };
    });
    window.scrollTo({ top: $("tr-passo2").offsetTop - 20, behavior: "smooth" });
  };
  const passo2 = () => { $("tr-passo2").hidden = false; $("tr-faixa").innerHTML = faixaPassos(2); mostrar(); };
  $("tr-usar").onclick = (e) => {
    const refs = $("tr-refs").value.split(/\n/).map((x) => x.trim()).filter(Boolean).slice(0, 3);
    if (!refs.length) return aviso("Cole pelo menos um canal de referência, ou clique em pular.");
    carregando(e.currentTarget, "Medindo os canais…", async () => {
      const r = await api(`/api/treinamento/${encodeURIComponent(canal.id)}/referencias`, { method: "POST", body: { refs } });
      $("tr-refs-ok").innerHTML = r.referencias.map((c) => linhaCanal(c, `<span class="valor verde"><b>${num(c.normal_longos)}</b>por vídeo</span>`)).join("");
      passo2();
    });
  };
  $("tr-pular").onclick = (e) => { e.preventDefault(); passo2(); };
  $("tr-mais").onclick = () => mostrar();
  $("tr-treinar").onclick = async (e) => {
    const botao = e.currentTarget; botao.disabled = true;
    $("tr-faixa").innerHTML = faixaPassos(3);
    try {
      const { tarefa } = await api(`/api/treinamento/${encodeURIComponent(canal.id)}/concluir`, { method: "POST", body: { positivos: [...escolhidos.keys()], negativos: [...recusados] } });
      for (;;) {
        await new Promise((r) => setTimeout(r, 2000));
        const t = await api(`/api/treinamento/tarefa/${tarefa}`);
        if (t.estado === "rodando") { botao.textContent = t.passo; continue; }
        if (t.estado === "erro") throw new Error(t.erro);
        const r = t.resultado;
        $("tr-faixa").innerHTML = faixaPassos(4);
        $("tr-fim").innerHTML = `<div class="passo"><h2><span class="n">3</span>Treinado</h2>
          <p style="margin:0">O Radar aprendeu o assunto do canal: <b>${esc(r.palavras.slice(0, 10).join(", "))}</b>.</p>
          <p class="sub" style="margin:0">Procurei no YouTube: ${esc(r.termos.join(" · "))}. ${r.canais} canais medidos, <b style="color:var(--verde)">${r.ideias_novas} ideias novas</b>.</p>
          <div><button class="botao vermelho" id="tr-ver">Ver as ideias</button></div></div>`;
        $("tr-ver").onclick = () => aoTerminar();
        $("tr-fim").scrollIntoView({ behavior: "smooth" });
        break;
      }
    } catch (erro) { aviso(porque(erro)); botao.disabled = false; }
    botao.textContent = "Treinar com os escolhidos";
  };
}

// a faixa dos 3 passos do treino: o passo atual fica em vermelho
const PASSOS_TREINO = ["Canais de referência", "Escolher os vídeos", "O Radar procura"];
function faixaPassos(atual) {
  return `<div class="passos">${PASSOS_TREINO.map((p, i) => `<div class="passo-faixa ${i + 1 === atual ? "atual" : i + 1 < atual ? "feito" : ""}"><span>${i + 1 < atual ? "✓" : i + 1}</span>${p}</div>`).join("")}</div>`;
}

// ---------------------------------------------------------------- Início

const CAMINHO = [
  ["🔎", "Ache o nicho", "Alerta, Explorar e Procurar"], ["📈", "Veja o que estourou", "Os vídeos acima do normal"],
  ["💡", "Salve a ideia", "No painel da direita"], ["🧩", "Confira na extensão", "Em que país ninguém fez?"],
  ["✍️", "Escreva o roteiro", "O Claude escreve"], ["🏭", "Mande para a fábrica", "Vira vídeo"],
];
const MAPA = [
  ["canais", "📺", "Meus canais", "Seus canais com os números e as métricas do YouTube Studio."],
  ["trabalho", "✍️", "Roteiro", "O Claude escreve o roteiro a partir de um vídeo de referência (transcrição e thumbnail) e você manda para a fábrica."],
  ["explorar", "🔀", "Explorar", "Vídeos que estouraram, sorteados, com filtros de língua, nicho, nota e data."],
  ["procurar", "🔎", "Procurar nicho", "Escreva um assunto e ache os canais dele, na base ou no YouTube na hora."],
  ["ideias", "📈", "Vídeos que estouraram", "A lista completa dos vídeos que fizeram muitas vezes o normal do próprio canal."],
  ["extensao", "🧩", "Extensão", "A nota de cada vídeo e o 🌍 Oportunidade por país, dentro do próprio YouTube."],
];

async function inicio() {
  const d = await api("/api/inicio");
  const sigla = (t) => t.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
  // pedido do usuário em 2026-10-18: sem o "Olá", os canais grandes e organizados no topo
  tela.innerHTML = `
    <section class="secao-inicio"><div class="ini-cab"><h2>Seus canais</h2>
        <a class="botao contorno" href="#/canais/novo">+ Adicionar canal</a></div>
      <div class="ini-canais">${d.canais.map((c) => `<article class="ini-canal">
        <a class="ini-foto" href="#/canal/${esc(c.id)}">${c.foto ? `<img src="${esc(c.foto)}" alt="" referrerpolicy="no-referrer" data-sigla="${esc(sigla(c.titulo))}">` : `<i>${esc(sigla(c.titulo))}</i>`}</a>
        <a class="ini-nome" href="#/canal/${esc(c.id)}">${esc(c.titulo)}</a>
        <span class="ini-inscritos">${num(c.inscritos)} inscritos</span>
        <span class="ini-config">${c.configurado ? `${esc(c.lingua)}${c.voz ? ` · voz ${esc(c.voz)}` : ""}` : '<em>ainda não configurado</em>'}</span>
        <div class="ini-acoes"><a class="botao contorno" href="#/canal/${esc(c.id)}">Abrir canal</a>
          ${EU.admin ? `<button class="botao ini-fazer" data-canal="${esc(c.id)}">+ Fazer vídeo</button>` : ""}</div>
        <button class="tirar-canal" data-canal="${esc(c.id)}" data-nome="${esc(c.titulo)}" title="Tirar este canal do Radar">×</button>
      </article>`).join("") || '<div class="vazio">Nenhum canal ainda. <a href="#/canais/novo">Adicione o primeiro</a>.</div>'}</div></section>

    <section class="secao-inicio"><h2>Como funciona</h2>
      <div class="caminho">${CAMINHO.map(([ic, t, s], i) => `<div class="etapa"><span class="num">${i + 1}</span><span class="ic">${ic}</span><b>${t}</b><small>${s}</small></div>`).join("")}</div></section>

    <section class="secao-inicio"><h2>O que tem no app</h2>
      <div class="mapa-grande">${MAPA.map(([rota, ic, t, txt]) => `<a class="mapa-card" href="#/${rota}"><span class="ic">${ic}</span><b>${t}</b><p>${txt}</p><span class="ir">Abrir →</span></a>`).join("")}</div></section>`;
  tela.querySelectorAll(".ini-foto img").forEach((img) => (img.onerror = () => {
    const i = document.createElement("i"); i.textContent = img.dataset.sigla; img.replaceWith(i);
  }));
  tela.querySelectorAll(".ini-fazer").forEach((b) => (b.onclick = () => novaProducao({ canal: b.dataset.canal })));
  // o × no canto do cartão: tira o canal do Radar (o canal no YouTube não é tocado), sempre perguntando antes
  ligarTirarCanal(inicio);
}

// o × no canto do cartão do canal: tira o canal do Radar (o canal no YouTube não é tocado), sempre perguntando antes
function ligarTirarCanal(redesenhar) {
  tela.querySelectorAll(".tirar-canal").forEach((b) => (b.onclick = async (e) => {
    e.preventDefault(); e.stopPropagation();
    if (!confirm(`Tirar "${b.dataset.nome}" dos seus canais?

Sai do Radar com a configuração de produção (língua, voz, agente). O canal no YouTube continua igual, e dá para adicionar de novo depois.`)) return;
    try { await api(`/api/perfil/canais/${b.dataset.canal}`, { method: "DELETE" }); redesenhar(); }
    catch (erro) { aviso(porque(erro)); }
  }));
}

// ---------------------------------------------------------------- Meus canais: trabalhar com um canal ou adicionar

async function canais(acao) {
  const [p, st] = await Promise.all([api("/api/inicio"), api("/api/youtube/status")]);
  const ok = new URLSearchParams(location.hash.split("?")[1] || "").get("studio") === "ok";
  tela.innerHTML = titulo("Canais", "Seus canais e a produção de cada um: a língua, a voz e o agente de roteiro.") + `
    ${ok ? '<div class="chamada"><span class="texto"><b>YouTube Studio conectado.</b> Escolha o canal para ver as métricas.</span></div>' : ""}
    <div class="dois-grandes">
      <button class="grande-escolha ${acao === "novo" ? "" : "ativa"}" id="op-trabalhar"><span class="ic">📺</span><b>Ver um canal</b><small>Os números e as métricas do Studio</small></button>
      <button class="grande-escolha ${acao === "novo" ? "ativa" : ""}" id="op-adicionar"><span class="ic">➕</span><b>Adicionar canal</b><small>Pelo Google ou só pelo @</small></button>
    </div>
    <div id="op-trabalhar-caixa" ${acao === "novo" ? "hidden" : ""}>
      <div class="tiles">${p.canais.map((c) => `<a class="tile" href="#/canal/${esc(c.id)}">
        <img src="${esc(c.foto)}" alt="" referrerpolicy="no-referrer">
        <b>${esc(c.titulo)}</b><small>${num(c.inscritos)} inscritos · ${num(c.normal_longos)} por vídeo</small>
        <span class="tile-etapas"><i class="${c.studio ? "ok" : ""}">📊 ${c.studio ? "Studio" : "sem Studio"}</i></span>
        <button class="tirar-canal" data-canal="${esc(c.id)}" data-nome="${esc(c.titulo)}" title="Tirar este canal do Radar">×</button></a>`).join("")
        || '<div class="vazio">Nenhum canal ainda. Clique em <b>Adicionar canal</b>.</div>'}</div></div>
    <div id="op-adicionar-caixa" ${acao === "novo" ? "" : "hidden"}>
      <div class="duas">
        <div class="bloco"><h3>Pelo Google (com as métricas do Studio)</h3>
          <p class="sub">Entre com a conta Google do canal: horas assistidas, retenção, receita, cliques na thumbnail e de onde vêm as views. Só leitura.</p>
          ${st.configurado ? '<button class="botao vermelho grande" id="studio">Conectar com o Google</button>' : '<span class="sub">Falta o login do Google no .env.</span>'}</div>
        <div class="bloco"><h3>Só pelo @</h3>
          <p class="sub">Sem login: os números públicos. Serve para qualquer canal.</p>
          <div class="conectar"><input id="ref" placeholder="@seucanal ou link do canal"><button class="botao grande" id="conectar">Adicionar</button></div></div>
      </div></div>`;
  const alternar = (novo) => {
    document.getElementById("op-trabalhar").classList.toggle("ativa", !novo);
    document.getElementById("op-adicionar").classList.toggle("ativa", novo);
    document.getElementById("op-trabalhar-caixa").hidden = novo;
    document.getElementById("op-adicionar-caixa").hidden = !novo;
  };
  document.getElementById("op-trabalhar").onclick = () => alternar(false);
  document.getElementById("op-adicionar").onclick = () => alternar(true);
  ligarTirarCanal(() => { MEUS = null; canais(acao); });
  const b = document.getElementById("studio");
  if (b) b.onclick = async () => { const { url } = await api("/api/youtube/conectar"); location.href = url; };
  const conectar = () => {
    const ref = document.getElementById("ref").value.trim();
    if (!ref) return;
    carregando(document.getElementById("conectar"), "Medindo…", async () => {
      const { canal: c } = await api("/api/perfil/canais", { method: "POST", body: { ref } });
      MEUS = null; location.hash = `#/canal/${c.id}`;
    });
  };
  document.getElementById("conectar").onclick = conectar;
  document.getElementById("ref").onkeydown = (e) => { if (e.key === "Enter") conectar(); };
}

// ---------------------------------------------------------------- a página do canal: ideias, treino, radar e métricas

// as ideias e o treino do algoritmo saíram em 2026-10-14 (pedido do usuário: a cota do YouTube fica só para nichos)
const ABAS_CANAL = [["metricas", "📊 Métricas"]];

async function canal(id, aba) {
  const [d, est] = await Promise.all([api(`/api/perfil/canal/${encodeURIComponent(id)}`),
    api(`/api/treinamento/${encodeURIComponent(id)}`).catch(() => null)]);
  const c = d.canal;
  if (!d.meu) {   // canal que não é da pessoa: só os números e os vídeos
    tela.innerHTML = `<a class="voltar" href="javascript:history.back()">← voltar</a><article class="canal">${miolo(c)}</article>
      <section class="cp-bloco" id="horarios-canal"></section>
      <div class="secao-tela"><h2>Últimos vídeos</h2><div class="grade-videos">${d.ultimos.map((v) => cartaoVideo(v, { canal: false })).join("")}</div></div>`;
    horariosDoCanal(document.getElementById("horarios-canal"), d.horarios);
    ligarCartoes(); ligarRoteiro(); return;
  }
  CANAL_ATUAL = id;
  aba = "metricas";
  tela.innerHTML = `<div class="canal-pagina"><div class="canal-centro"><a class="voltar" href="#/inicio">← início</a>
    <article class="canal">${miolo(c)}</article>
    <div id="producao-canal"></div>
    <section class="cp-bloco" id="modelo-descricao"></section>
    <section class="cp-bloco" id="horarios-canal"></section>
    <div id="painel-canal"></div>
    <div id="aba-corpo"></div>
    <div id="sugestoes-canal"></div></div></div>`;
  formProducao(document.getElementById("producao-canal"), id);
  modeloDaDescricao(document.getElementById("modelo-descricao"), id).catch(() => {});
  horariosDoCanal(document.getElementById("horarios-canal"), d.horarios);
  painelCanal(document.getElementById("painel-canal"), id);
  sugestoesDoCanal(document.getElementById("sugestoes-canal"), c);
  ligarCartoes();
  const corpo = document.getElementById("aba-corpo");
  if (aba === "ideias") {
    corpo.innerHTML = (est && est.feito
      ? `<div class="chamada"><span class="texto">🎯 <b>Seguindo o treino</b> de ${new Date(est.quando).toLocaleDateString("pt-BR")} (${est.escolhidos} vídeos escolhidos). Salve as boas no 💡. Para saber em que país ninguém fez ainda, use o 🌍 da extensão no YouTube.</span></div>`
      : `<div class="chamada aviso"><span class="texto">⚠ <b>Este canal ainda não foi treinado.</b> As ideias seguem só os títulos do canal e podem vir misturadas.</span><a class="botao vermelho" href="#/canal/${esc(id)}/treino">Treinar agora</a></div>`) +
      '<div id="ideias-corpo"></div>';
    componenteIdeias(document.getElementById("ideias-corpo"), id);
  } else if (aba === "treino") {
    telaTreino(corpo, { id, titulo: c.titulo }, est);
  } else {
    corpo.innerHTML = `<div class="secao-tela"><h2>Seus últimos vídeos</h2><p class="linha-sub">A nota é quantas vezes o vídeo fez o normal do canal (${num(c.normal_longos)} por vídeo).</p>
        <div class="grade-videos">${d.ultimos.map((v) => cartaoVideo(v, { canal: false, roteiro: false, bloquear: false })).join("")}</div></div>`;
  }
}

// o melhor horário para postar, das curvas de views por hora que o Radar já guarda deste canal (sem cota).
// Pedido do usuário em 2026-10-25, depois de abrir a vidIQ com o REA: lá, sem dado do canal, essa curva é uma matriz
// fixa no código com ruído semeado pelo id do vídeo. Aqui, sem curva suficiente, a tela diz o que falta e não
// desenha faixa nenhuma — ver radar/horarios.py.
function horariosDoCanal(caixa, h) {
  if (!caixa) return;
  if (!h) { caixa.remove(); return; }
  const cabeca = `<h3>🕒 Melhor horário para postar</h3>
    <p class="sub">Das curvas de views por hora deste canal, somando ${num(h.horas)} ${h.horas === 1 ? "hora" : "horas"} de curva de ${num(h.videos)} ${h.videos === 1 ? "vídeo" : "vídeos"}. As primeiras ${h.ignorado_h} h de cada vídeo ficam de fora: o pico de estreia diz a hora em que você postou, não a hora em que o público assiste.</p>`;
  if (!h.suficiente) {
    caixa.innerHTML = `${cabeca}<div class="chamada aviso"><span class="texto">⚠ <b>Ainda não dá para dizer.</b>
      O Radar precisa de ${h.minimo.videos} vídeos e ${num(h.minimo.horas)} horas de curva deste canal; tem ${num(h.videos)} e ${num(h.horas)}.
      Enquanto não tiver, não aparece horário nenhum aqui — número inventado é pior que número nenhum.</span></div>`;
    return;
  }
  let dia = "geral";
  const desenhar = () => {
    const valores = h.por_dia[dia] || [];
    const topo = Math.max(...valores);
    const pico = valores.indexOf(topo);
    const faixa = h.faixas[pico];
    const abas = ["geral", ...h.dias].map((d) => `<button class="botao sec${d === dia ? " ativo" : ""}" data-dia="${esc(d)}">${d === "geral" ? "Semana toda" : esc(d)}</button>`).join("");
    const barras = valores.map((v, i) => {
      const altura = Math.max(Math.round((v / (topo || 1)) * 100), 4);
      const titulo = `${h.faixas[i][0]}h às ${h.faixas[i][1]}h59 · ${(v * 100).toFixed(1).replace(".", ",")}% do que o canal rende`;
      return `<div class="hr-col${i === pico ? " pico" : ""}" title="${esc(titulo)}">
        <div class="hr-barra"><i style="height:${altura}%"></i></div><span>${h.faixas[i][0]}h</span></div>`;
    }).join("");
    caixa.innerHTML = `${cabeca}<div class="hr-abas">${abas}</div><div class="hr-grafico">${barras}</div>
      <p class="hr-pico">Pico ${dia === "geral" ? "da semana" : `de ${esc(dia)}`}: <b>${faixa[0]}h às ${faixa[1]}h59</b>
        (${(topo * 100).toFixed(1).replace(".", ",")}% do que o canal rende). Poste um pouco antes, para o vídeo já estar no ar quando o público chegar.</p>`;
    caixa.querySelectorAll("[data-dia]").forEach((b) => { b.onclick = () => { dia = b.dataset.dia; desenhar(); }; });
  };
  desenhar();
}

// embaixo da página do canal: vídeos que estouraram, do banco que o Radar já juntou, do mesmo assunto (não gasta cota)
async function sugestoesDoCanal(caixa, c) {
  const POR = 8;
  const tentativas = [c.subnicho && { subnicho: c.subnicho }, c.nicho && { nicho: c.nicho }, {}].filter(Boolean);
  let filtro = null, pagina = 0;
  const pedir = (f, n) => api("/api/outliers?" + consulta({ ...f, lingua: "todas", nota_min: 3, tipo: "longo", pagina: n, por: POR }));
  const desenhar = ({ videos, total }) => {
    const paginas = Math.max(1, Math.ceil(total / POR));
    caixa.innerHTML = `<div class="secao-tela"><h2>Sugestões para este canal</h2>
      <p class="linha-sub">Vídeos que estouraram${filtro.subnicho || filtro.nicho ? ` em <b>${esc(filtro.subnicho || filtro.nicho)}</b>` : ""}, achados pelo garimpo, pelas procuras e pela extensão.</p>
      <div class="grade-videos grandes">${videos.filter((v) => v.canal_id !== c.id).map((v) => cartaoVideoGrande(v)).join("") || '<div class="vazio" style="grid-column:1/-1">Nada no banco ainda.</div>'}</div>
      ${total > POR ? `<div class="paginas"><button class="botao sec" id="sg-ant" ${pagina ? "" : "disabled"}>← Anterior</button><span>Página ${pagina + 1} de ${num(paginas)}</span>
        <button class="botao sec" id="sg-prox" ${pagina + 1 >= paginas ? "disabled" : ""}>Próximo →</button></div>` : ""}</div>`;
    ligarRoteiro(caixa);
    const ir = async (n) => { pagina = n; desenhar(await pedir(filtro, n)); caixa.scrollIntoView({ behavior: "smooth" }); };
    if (caixa.querySelector("#sg-ant")) { caixa.querySelector("#sg-ant").onclick = () => ir(pagina - 1); caixa.querySelector("#sg-prox").onclick = () => ir(pagina + 1); }
  };
  try {
    for (const f of tentativas) {   // o subnicho; se não tiver nada, o nicho; senão, tudo
      const r = await pedir(f, 0);
      filtro = f;
      if (r.total) return desenhar(r);
    }
    desenhar({ videos: [], total: 0 });
  } catch (e) { caixa.innerHTML = `<div class="vazio">${esc(e.message)}</div>`; }
}

function telaTreino(caixa, canalInfo, est) {
  caixa.innerHTML = `<div class="explica">
      <div><b>O que é:</b> você ensina ao Radar o tipo de vídeo que <b>${esc(canalInfo.titulo)}</b> faz, escolhendo vídeos de exemplo.</div>
      <div><b>Para que serve:</b> depois do treino, a aba <b>Ideias</b> só mostra vídeos desse tipo, e o selo 🎯 da extensão também segue o treino.</div>
      <div><b>Quanto leva:</b> uns 2 minutos. Faça uma vez; refaça quando o canal mudar de rumo.</div></div><div id="treino-corpo"></div>`;
  const corpo = caixa.querySelector("#treino-corpo");
  const comecar = () => assistenteTreino(corpo, canalInfo, () => { location.hash = `#/canal/${canalInfo.id}/ideias`; });
  if (est && est.feito) {
    corpo.innerHTML = `<div class="passo"><h2><span class="n">✓</span>Este canal já foi treinado</h2>
      <p style="margin:0">Treinado em ${new Date(est.quando).toLocaleDateString("pt-BR")}, com <b>${est.escolhidos} vídeos escolhidos</b>${est.referencias.length ? ` e as referências ${est.referencias.map((r) => esc(r.titulo)).join(", ")}` : ""}.</p>
      ${est.termos.length ? `<p class="sub" style="margin:0">Buscas que o Radar fez: ${est.termos.map(esc).join(" · ")}</p>` : ""}
      <div class="linha"><a class="botao vermelho" href="#/canal/${esc(canalInfo.id)}/ideias" style="flex:none">Ver as ideias</a><button class="botao sec" id="refazer" style="flex:none">Treinar de novo</button></div></div>`;
    corpo.querySelector("#refazer").onclick = comecar;
  } else comecar();
}

async function telaRadar(caixa, canalInfo) {
  const { projetos, paises, linguas } = await api("/api/radar-paises");
  const meus = projetos.filter((p) => p.canal_id === canalInfo.id);
  const atual = meus[0] || null;
  caixa.innerHTML = `<div class="explica">
      <div><b>O que é:</b> os países e as línguas onde o 📡 de cada vídeo vai conferir se a ideia já foi feita.</div>
      <div><b>Como procura:</b> o <b>título exato</b> do vídeo, <b>sem nenhum número</b>. Na mesma língua vai o título igual; em outra língua, a tradução fiel dele.</div>
      <div><b>Custo:</b> uns 101 da cota grátis do YouTube por país conferido. O resultado fica guardado 7 dias.</div></div>
    <div class="passo"><h2><span class="n">📡</span>${atual ? "O radar deste canal" : "Criar o radar deste canal"}</h2>
      <input id="rp-nome" placeholder="Nome do radar" value="${esc(atual ? atual.nome : "Radar do " + canalInfo.titulo)}">
      <p class="sub" style="margin:0">Marque os países. Cada um usa a língua ao lado (troque se quiser).</p>
      <div class="paises">${paises.map((p) => {
        const x = atual && atual.paises.find((y) => y.codigo === p.codigo);
        return `<label class="pais"><input type="checkbox" value="${p.codigo}" ${x ? "checked" : ""}> <span>${esc(p.nome)}</span>
          <select data-lingua="${p.codigo}">${Object.entries(linguas).map(([c, n]) => `<option value="${c}" ${c === (x ? x.lingua : p.lingua) ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></label>`;
      }).join("")}</div>
      <div><button class="botao vermelho grande" id="rp-salvar">Salvar o radar</button></div></div>`;
  caixa.querySelector("#rp-salvar").onclick = async () => {
    const escolhidos = [...caixa.querySelectorAll(".pais input:checked")].map((ck) => ({ codigo: ck.value, lingua: caixa.querySelector(`select[data-lingua="${ck.value}"]`).value }));
    try {
      await api("/api/radar-paises", { method: "POST", body: { id: atual ? atual.id : null, nome: caixa.querySelector("#rp-nome").value, canal_id: canalInfo.id, paises: escolhidos } });
      RADARES = null; aviso("Radar salvo. Agora use o 📡 em cima dos vídeos das Ideias."); telaRadar(caixa, canalInfo);
    } catch (e) { aviso(porque(e)); }
  };
}

// os endereços antigos levam para a página do canal
const ideiasCanal = async (id) => { location.hash = id ? `#/canal/${id}` : "#/canais"; };
const treino = async (id) => { location.hash = id ? `#/canal/${id}` : "#/canais"; };
const radarPaises = async () => { const c = (await meusCanais(true))[0]; location.hash = c ? `#/canal/${CANAL_ATUAL || c.id}/radar` : "#/canais"; };

// ---------------------------------------------------------------- o Radar de cada vídeo: em que país ninguém fez ainda

let RADARES = null;
async function radares() { if (!RADARES) RADARES = (await api("/api/radar-paises")).projetos; return RADARES; }
const RADAR_PADRAO = { id: 0, nome: "Radar de línguas", paises: [] };
const NOMES_LINGUA = { pt: "Português", en: "Inglês", es: "Espanhol", fr: "Francês", de: "Alemão", it: "Italiano", nl: "Holandês",
  pl: "Polonês", tr: "Turco", ja: "Japonês", ko: "Coreano", id: "Indonésio", ru: "Russo", ar: "Árabe" };
const FORCA = { forte: "forte", medio: "médio", fraco: "fraco" };
const bandeira = (codigo) => codigo === "un" ? '<span class="bandeira" style="display:inline-block;background:var(--linha)"></span>' : `<img class="bandeira" src="https://flagcdn.com/w40/${esc(codigo.toLowerCase())}.png" alt="" loading="lazy">`;

// o placar de oportunidade: uma nota de 0 a 100 por país (livre vale mais; feito fraco ainda vale; feito forte quase não)
function oportunidade(p) {
  if (!p.feito) return Math.max(70, 100 - (p.quase || 0) * 8);
  return { fraco: 55, medio: 30, forte: 10 }[p.forca] ?? 30;
}
const PORQUE = (p) => !p.feito ? (p.quase ? `Ninguém fez. ${p.quase} ${p.quase === 1 ? "vídeo chega perto" : "vídeos chegam perto"}, mas não é a mesma ideia.` : "Ninguém fez esse vídeo nessa língua.")
  : p.forca === "fraco" ? "Já fizeram, mas foi fraco: dá para fazer melhor." : p.forca === "medio" ? "Já fizeram e foi razoável." : "Já fizeram e foi muito bem.";
const corNota = (n) => n >= 70 ? "boa" : n >= 40 ? "media" : "ruim";

function linhaPlacar(p, carregando = false) {
  const n = carregando ? 0 : oportunidade(p);
  return `<button class="placar-linha ${carregando ? "carregando" : corNota(n)}" data-codigo="${esc(p.codigo)}">
    <span class="placar-pais">${bandeira(p.codigo)}<b>${esc(p.pais || p.nome)}</b><small>${esc(NOMES_LINGUA[p.lingua] || p.lingua)}</small></span>
    <span class="placar-barra"><i style="width:${carregando ? 100 : n}%"></i></span>
    <span class="placar-n">${carregando ? "…" : n}</span></button>`;
}

async function conferirPaises(projeto, videoId, tituloVideo) {
  let modal = document.getElementById("modal-radar");
  if (!modal) {
    document.body.insertAdjacentHTML("beforeend", '<div id="modal-radar" class="modal-fundo"><div class="modal modal-radar"></div></div>');
    modal = document.getElementById("modal-radar");
    modal.onclick = (e) => { if (e.target === modal || e.target.closest(".fechar-modal")) modal.hidden = true; };
  }
  const caixa = modal.querySelector(".modal");
  modal.hidden = false;
  const cab = (nome) => `<div class="painel-cab"><b>🌍 Oportunidade por país</b><button class="botao sec fechar-modal">×</button></div>
    <p class="sub radar-pergunta">${esc(nome)} · onde este vídeo ainda vale a pena ser feito</p>`;
  caixa.innerHTML = cab(projeto.nome) + `<div class="placar">${(projeto.paises.length ? projeto.paises : Array.from({ length: 8 }, () => ({ codigo: "un", nome: "Procurando…", lingua: "" })))
    .map((p) => linhaPlacar(p, true)).join("")}</div>
    <p class="sub" style="text-align:center">Procurando o título, sem os números, no YouTube de cada país… (até 30 segundos)</p>`;
  try {
    const r = await api(`/api/radar-paises/${projeto.id}/conferir`, { method: "POST", body: { video_id: videoId, titulo: tituloVideo } });
    const ordem = [...r.paises].sort((a, b) => oportunidade(b) - oportunidade(a));
    const melhor = ordem[0], livres = ordem.filter((p) => !p.feito).length;
    caixa.innerHTML = cab(r.projeto) + `
      <div class="melhor-aposta ${corNota(oportunidade(melhor))}">
        <img class="bandeira-grande" src="https://flagcdn.com/w160/${esc(melhor.codigo.toLowerCase())}.png" alt="">
        <div><small>Melhor aposta</small><b>${esc(melhor.pais)} · ${esc(NOMES_LINGUA[melhor.lingua] || melhor.lingua)}</b><span>${esc(PORQUE(melhor))}</span></div>
        <div class="aposta-n">${oportunidade(melhor)}<small>de 100</small></div></div>
      <div class="placar-resumo"><span class="pilula boa">${livres} ${livres === 1 ? "país livre" : "países livres"}</span>
        <span class="pilula ruim">${ordem.length - livres} já ${ordem.length - livres === 1 ? "feito" : "feitos"}</span>
        <span class="sub">Procurei “${esc(r.ideia)}” na língua de cada país${r.guardado ? " · guardado, sem gastar cota" : ""}</span></div>
      <div class="placar">${ordem.map((p) => linhaPlacar(p)).join("")}</div>
      <button class="botao sec ver-todos" style="width:100%;justify-content:center;margin-top:12px">Ver os vídeos de cada país</button>
      <div class="radar-detalhes" hidden>${ordem.map((p) => `<div class="pais-resultado ${p.feito ? "feito" : "livre"}" data-codigo="${esc(p.codigo)}">
        <div class="pais-cab">${bandeira(p.codigo)} <b>${esc(p.pais)}</b> <span class="sub">${esc(PORQUE(p))} Busquei “${esc(p.busca)}”.</span></div>
        ${p.parecidos.map((v) => `<a class="mini" href="${linkVideo(esc(v.id))}" target="_blank" rel="noopener">
          <img src="https://i.ytimg.com/vi/${esc(v.id)}/default.jpg" alt="" style="width:64px;height:36px;border-radius:5px">
          <span><b>${esc(v.titulo)}</b><small>${esc(v.canal)} · ${num(v.views)} views${v.publicado ? " · " + ha(v.publicado) : ""}</small></span></a>`).join("")}
        <a class="sub" href="${esc(p.link)}" target="_blank" rel="noopener" style="color:var(--acento)">ver a busca no YouTube →</a></div>`).join("")}</div>`;
    const detalhes = caixa.querySelector(".radar-detalhes");
    caixa.querySelector(".ver-todos").onclick = (e) => { detalhes.hidden = !detalhes.hidden; e.target.textContent = detalhes.hidden ? "Ver os vídeos de cada país" : "Esconder os vídeos"; };
    caixa.querySelectorAll(".placar-linha").forEach((b) => (b.onclick = () => {
      detalhes.hidden = false;
      const alvo = detalhes.querySelector(`[data-codigo="${b.dataset.codigo}"]`);
      alvo.scrollIntoView({ behavior: "smooth", block: "center" }); alvo.classList.add("piscar"); setTimeout(() => alvo.classList.remove("piscar"), 1200);
    }));
  } catch (e) {
    caixa.innerHTML = cab(projeto.nome) + `<p>${esc(e.message)}</p>`;
  }
}

document.addEventListener("click", async (e) => {
  const botao = e.target.closest(".radar-pais");
  const escolha = e.target.closest(".menu-radar button");
  const menuAberto = document.querySelector(".menu-radar");
  if (escolha) {
    menuAberto.remove();
    const p = +escolha.dataset.id ? (await radares()).find((x) => x.id === +escolha.dataset.id) : RADAR_PADRAO;
    return conferirPaises(p, escolha.dataset.video, escolha.dataset.titulo);
  }
  if (menuAberto && !e.target.closest(".menu-radar")) menuAberto.remove();
  if (!botao) return;
  e.preventDefault(); e.stopPropagation();
  const v = botao.closest(".video");
  const lista = await radares();
  // sem radar próprio, confere nas 8 línguas padrão; com o radar do canal aberto, vai direto nele
  const doCanal = lista.find((p) => p.canal_id && p.canal_id === CANAL_ATUAL);
  if (doCanal || !lista.length) return conferirPaises(doCanal || RADAR_PADRAO, v.dataset.video, v.dataset.titulo);
  const menu = document.createElement("div");
  menu.className = "menu-bloq menu-radar";
  menu.innerHTML = "<small>Conferir com qual radar?</small>" + [...lista, { id: 0, nome: "8 línguas padrão", paises: { length: 8 } }].map((p) => `<button data-id="${p.id}" data-video="${esc(v.dataset.video)}" data-titulo="${esc(v.dataset.titulo)}">${esc(p.nome)} · ${p.paises.length} ${p.paises.length === 1 ? "país" : "países"}</button>`).join("");
  document.body.appendChild(menu);
  const r = botao.getBoundingClientRect();
  menu.style.left = Math.max(8, Math.min(window.innerWidth - 250, r.right + window.scrollX - 230)) + "px";
  menu.style.top = r.bottom + window.scrollY + 6 + "px";
});

// ---------------------------------------------------------------- Bloqueados

async function bloqueados() {
  const { bloqueios } = await api("/api/bloqueios");
  tela.innerHTML = titulo("Bloqueados", "O que você escondeu pelo ⊘ em cima dos vídeos. Desbloqueie para voltar a ver.") +
    `<div class="lista-titulos">${bloqueios.map((b) => `<div class="titulo-linha"><span class="t"><b>${esc(b.rotulo || b.valor)}</b><small>${{ video: "vídeo", canal: "canal", nicho: "nicho", subnicho: "tipo de vídeo", palavra: "palavra" }[b.tipo]}</small></span>
      <button class="botao sec desbloquear" data-tipo="${esc(b.tipo)}" data-valor="${esc(b.valor)}">Desbloquear</button></div>`).join("") || '<div class="vazio">Nada bloqueado.</div>'}</div>`;
  tela.querySelectorAll(".desbloquear").forEach((b) => (b.onclick = async () => {
    await api("/api/bloqueios", { method: "DELETE", body: { tipo: b.dataset.tipo, valor: b.dataset.valor } }); bloqueados();
  }));
}

// ---------------------------------------------------------------- Integrações: as chaves de API (2026-10-18)
// Saldo de cada serviço e as chaves, para testar, trocar, acrescentar e remover. Só a administração, neste computador.

async function integracoes(dados) {
  const d = dados || await api("/api/integracoes");
  const bt = (classe, texto, extra = "") => `<button class="botao ${classe}" ${extra}>${texto}</button>`;
  const status = (c) => !c.teste ? '<span class="ig-st">não testada</span>'
    : c.teste.ok ? '<span class="ig-st ok">✓ testada</span>' : `<span class="ig-st erro" title="${esc(c.teste.erro)}">✕ ${esc(c.teste.erro)}</span>`;
  const bloqueado = (s) => s.dono === "fabrica" && !d.fabrica_ligada;
  const saldos = d.servicos.map((s) => `<div class="ig-saldo"><b>${esc(s.nome)}</b><span class="ig-valor">${esc(s.saldo.texto)}</span>
      ${s.saldo.informado && s.chaves.length ? `<button class="link-editar ig-informar" data-s="${s.id}">Informar saldo</button>` : ""}</div>`).join("");
  const cartoes = d.servicos.map((s) => `<div class="bloco ig-cartao" data-s="${s.id}">
      <div class="ig-cab"><h3>${esc(s.nome)}</h3><span class="ig-selo ${s.obrigatoria ? "obr" : ""}">${s.obrigatoria ? "obrigatória" : "opcional"}</span></div>
      <p class="sub">${esc(s.para_que)}</p>
      ${bloqueado(s) ? '<p class="ig-aviso">Fábrica desligada: ligue a fábrica para mexer nesta chave.</p>' : ""}
      <div class="ig-chaves">${s.chaves.map((c, i) => `<div class="ig-chave" data-i="${i}">
          <code>${esc(c.previa)}</code>${status(c)}
          ${bloqueado(s) ? "" : `<span class="ig-acoes">${bt("sec ig-testar", "Testar")}${bt("sec ig-trocar", "Trocar")}${bt("contorno ig-remover", "Remover")}</span>`}
        </div>`).join("") || '<div class="ig-vazia">Nenhuma chave.</div>'}</div>
      ${!bloqueado(s) && (s.varias || !s.chaves.length) ? bt("sec ig-adicionar", "+ Adicionar chave") : ""}
      <details class="ig-limite"><summary>Como funciona o limite</summary><p>${esc(s.limite)}</p></details>
      <a class="ig-onde" href="${esc(s.onde)}" target="_blank" rel="noopener">Onde pegar a chave ↗</a>
    </div>`).join("");
  let conta = "";
  try {
    const y = await api("/api/youtube/status");
    conta = !y.configurado ? "Login do Google não configurado" : y.conectados.length
      ? `${y.conectados.length === 1 ? "1 canal conectado" : `${y.conectados.length} canais conectados`} ao YouTube Studio` : "Nenhum canal conectado";
  } catch { conta = "—"; }
  tela.innerHTML = titulo("Integrações", "Saldos e chaves dos serviços que o Radar e a fábrica usam.") +
    (d.fabrica_ligada ? "" : '<div class="chamada aviso">A fábrica está desligada: as chaves dela ficam só para ver.</div>') +
    (d.aviso ? `<div class="chamada aviso">${esc(d.aviso)}</div>` : "") +
    `<h2 class="ig-h2">Saldos</h2><div class="ig-saldos">${saldos}</div>
     <h2 class="ig-h2">Chaves de API</h2><div class="ig-grade">${cartoes}</div>
     <h2 class="ig-h2">Contas</h2><div class="bloco ig-conta"><b>Google / YouTube Studio</b><span>${conta}</span><a href="#/canais">Abrir Canais</a></div>`;

  const cartao = (el) => el.closest(".ig-cartao");
  const indice = (el) => Number(el.closest(".ig-chave")?.dataset.i ?? -1);
  const campo = (el, indiceAlvo) => {            // o campo para colar a chave, dentro do próprio cartão
    cartao(el).querySelector(".ig-campo")?.remove();
    const caixa = document.createElement("div");
    caixa.className = "ig-campo";
    caixa.innerHTML = `<input type="password" autocomplete="off" placeholder="Cole a chave aqui">${bt("", "Salvar")}${bt("contorno", "Cancelar")}`;
    cartao(el).querySelector(".ig-chaves").after(caixa);
    const [entrada, salvar, cancelar] = caixa.children;
    entrada.focus();
    cancelar.onclick = () => caixa.remove();
    salvar.onclick = () => carregando(salvar, "Salvando…", async () =>
      integracoes(await api(`/api/integracoes/${cartao(el).dataset.s}`, { method: "POST", body: { valor: entrada.value, indice: indiceAlvo } })));
    entrada.onkeydown = (e) => { if (e.key === "Enter") salvar.click(); if (e.key === "Escape") caixa.remove(); };
  };
  tela.querySelectorAll(".ig-testar").forEach((b) => (b.onclick = () => carregando(b, "Testando…", async () => {
    await api(`/api/integracoes/${cartao(b).dataset.s}/testar`, { method: "POST", body: { indice: indice(b) } });
    integracoes();
  })));
  tela.querySelectorAll(".ig-trocar").forEach((b) => (b.onclick = () => campo(b, indice(b))));
  tela.querySelectorAll(".ig-adicionar").forEach((b) => (b.onclick = () => campo(b, null)));
  tela.querySelectorAll(".ig-remover").forEach((b) => (b.onclick = () => {
    const servico = cartao(b).dataset.s, i = indice(b);   // antes de trocar os botões: o b sai da página
    const acoes = b.closest(".ig-acoes");
    acoes.innerHTML = `<span class="ig-pergunta">Remover esta chave?</span>${bt("vermelho ig-sim", "Sim, remover")}${bt("contorno ig-nao", "Não")}`;
    acoes.querySelector(".ig-nao").onclick = () => integracoes(d);
    const sim = acoes.querySelector(".ig-sim");
    sim.onclick = () => carregando(sim, "Removendo…", async () =>
      integracoes(await api(`/api/integracoes/${servico}/${i}`, { method: "DELETE" })));
  }));
  tela.querySelectorAll(".ig-informar").forEach((b) => (b.onclick = () => {
    const caixa = b.parentElement;
    caixa.insertAdjacentHTML("beforeend", `<span class="ig-campo"><input inputmode="decimal" placeholder="US$ 25,40">${bt("", "Salvar")}</span>`);
    b.remove();
    const [entrada, salvar] = caixa.querySelector(".ig-campo").children;
    entrada.focus();
    salvar.onclick = () => carregando(salvar, "Salvando…", async () =>
      integracoes(await api(`/api/integracoes/${b.dataset.s}/saldo`, { method: "POST", body: { valor: entrada.value } })));
  }));
}

// ---------------------------------------------------------------- Custos (2026-10-18)
// O gasto do período, por provedor, por tipo e por canal, e a lista de vídeos (pelo custos_reais.json da fábrica).

const NOMES_CATEGORIA = { narracao: "Narração", imagem: "Imagens de IA", texto: "Modelos de texto", visao: "Análise das imagens",
  juiz: "Jev (juiz)", cenas: "Divisão de cenas", escolha: "Escolha do acervo", conferencia: "Conferência", efeito: "Efeitos sonoros", outros: "Outros" };
const PADRAO_CUSTOS = { dias: "30", canal: "", provedor: "", busca: "" };

async function custos() {
  const C = recorte(PADRAO_CUSTOS);
  tela.innerHTML = titulo("Custos", "Quanto a fábrica gastou e com o quê.") + '<div id="cu" class="cu"><div class="vazio">Carregando…</div></div>';
  const raiz = document.getElementById("cu");
  const barras = (obj, nomes = {}) => {
    const maior = Math.max(...Object.values(obj), 0.0001);
    return Object.entries(obj).map(([k, v]) => `<div class="cu-barra"><span>${esc(nomes[k] || k)}</span><i><b style="width:${(v / maior * 100).toFixed(1)}%"></b></i><em>${dolar(v)}</em></div>`).join("")
      || '<p class="acn-explica">Nada no período.</p>';
  };
  const carregar = async () => {
    let r;
    try { r = await api("/api/custos?" + consulta({ dias: C.dias, canal: C.canal, provedor: C.provedor })); }
    catch (e) { raiz.innerHTML = `<div class="vazio">${esc(e.message)}</div>`; return; }
    // canal ou provedor do endereço que não está mais na lista: o select mostraria "Todos" e continuaria filtrando
    if (C.canal && !r.canais.includes(C.canal)) C.canal = "";
    if (C.provedor && !r.provedores.includes(C.provedor)) C.provedor = "";
    recorteParaOEndereco(C, PADRAO_CUSTOS);
    const lista = r.lista.filter((v) => !C.busca || v.titulo.toLowerCase().includes(C.busca));
    raiz.innerHTML = `<div class="cu-filtros chips">${[[7, "7 dias"], [30, "30 dias"], [90, "90 dias"], [0, "Tudo"]].map(([d, n]) => `<button class="chip ${String(C.dias) === String(d) ? "ativo" : ""}" data-dias="${d}">${n}</button>`).join("")}
        <button class="limpar" type="button" id="cu-padrao" title="Desfaz as suas escolhas e devolve a tela como ela abre" ${mudouDoPadrao(C, PADRAO_CUSTOS) ? "" : "hidden"}>voltar ao padrão</button></div>
      <div class="cu-numeros"><div><small>Total</small><b>${dolar(r.total)}</b></div><div><small>Vídeos</small><b>${r.videos}</b></div>
        <div><small>Média por vídeo</small><b>${dolar(r.media_video)}</b></div><div><small>Por minuto de vídeo</small><b>${dolar(r.usd_por_minuto)}</b></div></div>
      <div class="cu-duas"><section class="bloco"><h3>Por provedor</h3>${barras(r.por_provedor)}</section>
        <section class="bloco"><h3>Por tipo de gasto</h3>${barras(r.por_categoria, NOMES_CATEGORIA)}</section></div>
      <section class="bloco"><h3>Por canal</h3><div class="cu-canais">${r.por_canal.map((c) => `<div><b>${esc(c.canal)}</b><span>${dolar(c.total)}</span><small>média ${dolar(c.media)} por vídeo</small></div>`).join("") || '<p class="acn-explica">Nada no período.</p>'}</div></section>
      <section class="bloco"><div class="cu-lista-cab"><h3>Por vídeo</h3>
          <input id="cu-busca" placeholder="Buscar título" value="${esc(C.busca)}">
          <select id="cu-canal"><option value="">Todos os canais</option>${r.canais.map((c) => `<option ${c === C.canal ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>
          <select id="cu-prov"><option value="">Todos os provedores</option>${r.provedores.map((p) => `<option ${p === C.provedor ? "selected" : ""}>${esc(p)}</option>`).join("")}</select></div>
        <div class="cu-tabela">${lista.map((v) => `<button class="cu-linha" data-nome="${esc(v.nome)}"><span class="cu-t"><b>${esc(v.titulo)}</b><small>${esc(v.canal || "Sem canal")} · ${esc((v.criado || "").slice(0, 10).split("-").reverse().join("/"))} · ${v.minutos ? `${String(v.minutos).replace(".", ",")} min` : "—"}</small></span>
            <span class="cu-v">${v.produzindo ? '<small class="acn-estado e-produzindo">medindo…</small>' : ""}<b>${dolar(v.usd)}</b><small>${v.usd_por_minuto != null ? dolar(v.usd_por_minuto) + "/min" : ""}</small></span></button>
            <div class="cu-detalhe" data-de="${esc(v.nome)}" hidden></div>`).join("") || '<div class="vazio">Nenhum vídeo com esses filtros.</div>'}</div></section>`;
    const mudou = () => { recorteParaOEndereco(C, PADRAO_CUSTOS); carregar(); };
    raiz.querySelectorAll("[data-dias]").forEach((b) => (b.onclick = () => { C.dias = b.dataset.dias; mudou(); }));
    raiz.querySelector("#cu-busca").onchange = (e) => { C.busca = e.target.value.toLowerCase(); mudou(); };
    raiz.querySelector("#cu-canal").onchange = (e) => { C.canal = e.target.value; mudou(); };
    raiz.querySelector("#cu-prov").onchange = (e) => { C.provedor = e.target.value; mudou(); };
    raiz.querySelector("#cu-padrao").onclick = () => { Object.assign(C, PADRAO_CUSTOS); mudou(); };
    raiz.querySelectorAll(".cu-linha").forEach((b) => (b.onclick = async () => {
      const caixa = raiz.querySelector(`.cu-detalhe[data-de="${CSS.escape(b.dataset.nome)}"]`);
      if (!caixa.hidden) { caixa.hidden = true; return; }
      const d = await api(`/api/custos/${encodeURIComponent(b.dataset.nome)}`);
      caixa.innerHTML = `<div class="cu-duas"><div>${barras(d.por_categoria, NOMES_CATEGORIA)}</div><div>${barras(d.por_provedor)}</div></div>
        <small>${d.imagens_ia} imagens de IA cobradas · total ${dolar(d.total)}</small>`;
      caixa.hidden = false;
    }));
  };
  carregar();
}

// ---------------------------------------------------------------- Nova produção (2026-10-18)
// A janela de criar vídeo: os campos à esquerda, "Assim ele entra na fila" à direita. Salvar na Entrada guarda sem
// começar; Criar e começar põe na fila (o sim para gastar). O Produzir de 3 passos continua no menu.
// Passo a passo (pedido do usuário, 2026-10-19): o passo 1 tem só o título, o link, o agente (com Editar) e o "parar
// para eu revisar"; quem não aperta Editar já cria com o Claude escrevendo no agente do canal. O passo 2 (Editar) tem
// o resto: canal, agente, idioma, roteiro, tamanho, nicho e observação. O último canal usado fica lembrado.

const CARACTERES_POR_PALAVRA = 5.9;
const ATALHOS_MIN = [8, 10, 12, 15, 20, 25, 30];

async function novaProducao(preset = {}) {
  if (document.getElementById("nova-producao")) return;
  if (!EU?.admin) { aviso("Só a administração cria produções."); return; }
  const [canais, { projetos: agentes }] = await Promise.all([meusCanais(), api("/api/projetos")]);
  const lembrado = canais.some((c) => c.id === guardado("np-canal", "")) ? guardado("np-canal", "") : "";
  const N = { passo: 1, titulo: preset.titulo || "", link: preset.link || "", canal: preset.canal || CANAL_ATUAL || lembrado || (canais.length === 1 ? canais[0].id : ""), cfg: null, agente: "",
    lingua: "português", ppm: 150, caracteres: 0, modo: "claude", roteiro: "", nicho: "", obs: "", revisar: false, ref: null, custo: null };
  N.caracteres = Math.round(12 * N.ppm * CARACTERES_POR_PALAVRA / 10) * 10;
  const minutos = () => N.caracteres / CARACTERES_POR_PALAVRA / N.ppm;
  const palavras = () => Math.round(N.caracteres / CARACTERES_POR_PALAVRA);
  const nomeCanal = () => (canais.find((c) => c.id === N.canal) || {}).titulo || "";
  const sigla = (t) => t.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
  const LINGUAS = ["português", "inglês", "espanhol", "francês", "alemão", "italiano"];

  document.body.insertAdjacentHTML("beforeend", `<div class="modal-fundo" id="nova-producao"><div class="np" role="dialog" aria-label="Nova produção">
    <header class="np-cab"><h2>Nova produção</h2><button class="np-fechar" title="Fechar (Esc)">×</button></header>
    <div class="np-corpo"><div class="np-campos"></div><aside class="np-previa"></aside></div>
    <footer class="np-rodape"><span class="np-atalho"><kbd>Ctrl</kbd> + <kbd>Enter</kbd> cria e começa</span><span class="np-erro"></span>
      <button class="botao contorno" id="np-entrada">Salvar na Entrada</button><button class="botao" id="np-comecar">Criar e começar</button></footer>
  </div></div>`);
  const fundo = document.getElementById("nova-producao");
  const campos = fundo.querySelector(".np-campos"), previa = fundo.querySelector(".np-previa");
  const fechar = () => { fundo.remove(); document.removeEventListener("keydown", teclas); };
  const teclas = (e) => {
    if (e.key === "Escape") fechar();
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); fundo.querySelector("#np-comecar").click(); }
  };
  document.addEventListener("keydown", teclas);
  fundo.querySelector(".np-fechar").onclick = fechar;
  fundo.onclick = (e) => { if (e.target === fundo) fechar(); };

  const desenharPrevia = () => {
    const agente = agentes.find((a) => String(a.id) === String(N.agente));
    const capa = N.ref?.id ? `<img src="https://i.ytimg.com/vi/${esc(N.ref.id)}/mqdefault.jpg" alt="">` : "";
    previa.innerHTML = `<small>Assim ele entra na fila</small>
      <div class="np-cartao">${capa}<b>${esc(N.titulo || "O título do vídeo aparece aqui")}</b>
        <span class="np-cartao-rodape"><span>● Nova produção</span><span>≈ ${Math.round(minutos())} min</span></span></div>
      <dl class="np-resumo"><dt>Canal</dt><dd>${esc(nomeCanal() || "falta")}</dd>
        <dt>Estilo</dt><dd>${N.modo === "manual" ? "roteiro colado" : esc(agente?.nome || "padrão do Claude")}</dd>
        <dt>Tamanho</dt><dd>${N.modo === "manual" ? `${(N.roteiro.split(/\s+/).filter(Boolean).length).toLocaleString("pt-BR")} palavras` : `≈ ${Math.round(minutos())} min · ~${palavras().toLocaleString("pt-BR")} palavras`}</dd>
        <dt>Revisão</dt><dd>${N.revisar ? "Para para eu revisar" : "Segue direto"}</dd>
        <dt>Custo</dt><dd>${N.custo?.usd != null ? `≈ US$ ${N.custo.usd.toFixed(2).replace(".", ",")}${N.custo.base === "geral" ? " (média geral)" : ""}` : "—"}</dd></dl>`;
  };
  const atualizarCusto = async () => {
    try { N.custo = await api("/api/fila/estimativa?" + consulta({ canal: N.cfg?.perfil || "", minutos: minutos().toFixed(1) })); } catch { N.custo = null; }
    desenharPrevia();
  };
  const escolherCanal = async (id) => {
    N.canal = id;
    guardar("np-canal", id);
    try {
      N.cfg = await api(`/api/producao/${encodeURIComponent(id)}`);
      N.lingua = N.cfg.lingua || N.lingua;
      N.agente = N.cfg.projeto_roteiro_id || "";
      N.ppm = (await api("/api/roteiros/ritmo?" + consulta({ perfil: N.cfg.perfil, lingua: N.lingua }))).ppm || 150;
      N.caracteres = Math.round((N.cfg.minutos || 12) * N.ppm * CARACTERES_POR_PALAVRA / 10) * 10;
    } catch { N.cfg = null; }
    desenhar(); atualizarCusto();
  };

  function desenhar() {
    const agente = agentes.find((a) => String(a.id) === String(N.agente));
    const canaisHtml = `<div class="campo"><span>Canal</span><div class="np-canais">${canais.map((c) => `<button type="button" class="np-canal ${c.id === N.canal ? "escolhido" : ""}" data-id="${esc(c.id)}">
          ${c.foto ? `<img src="${esc(c.foto)}" alt="" data-sigla="${esc(sigla(c.titulo))}">` : `<i>${esc(sigla(c.titulo))}</i>`}${esc(c.titulo)}</button>`).join("") || '<span class="np-dica">Nenhum canal: adicione em Meu trabalho → Canais.</span>'}</div>
        ${N.canal && N.cfg && !N.cfg.perfil ? '<span class="np-dica alerta">Este canal ainda não tem voz da fábrica: configure em Canais antes de começar.</span>' : ""}</div>`;
    const revisarHtml = `<label class="np-revisar"><input type="checkbox" id="np-revisar" ${N.revisar ? "checked" : ""}><span><b>Parar para eu revisar o roteiro</b><small>O Claude escreve e espera você aprovar no Acompanhar antes de ir para a fábrica.</small></span></label>`;
    const passos = `<div class="np-passos"><span class="${N.passo === 1 ? "ativo" : ""}">1 · O vídeo</span><span class="${N.passo === 2 ? "ativo" : ""}">2 · Editar o roteiro</span></div>`;
    if (N.passo === 1) {
      campos.innerHTML = `${passos}
      <label class="campo"><span>Título do vídeo</span><input id="np-titulo" value="${esc(N.titulo)}" placeholder="O título que vai para o YouTube" maxlength="150"></label>
      <label class="campo"><span>Vídeo de referência <small>(opcional: o roteiro modela este vídeo)</small></span><input id="np-link" value="${esc(N.link)}" placeholder="https://youtu.be/…"></label>
      ${N.ref?.titulo ? `<button class="link-editar np-usar" type="button">usar o título da referência: “${esc(N.ref.titulo)}”</button>` : ""}
      ${N.canal ? "" : canaisHtml}
      <div class="campo"><span>Agente do roteiro</span><div class="np-agente">
        <div><b>${esc(N.modo === "manual" ? "Roteiro colado por você" : agente?.nome || "Padrão do Claude")}</b>
          <small>${esc([nomeCanal() || "escolha o canal", N.lingua, N.modo === "manual" ? null : `≈ ${Math.round(minutos())} min`].filter(Boolean).join(" · "))}</small>
          ${agente?.ideal_para && N.modo !== "manual" ? `<small class="np-ideal">Ideal para: ${esc(agente.ideal_para)}</small>` : ""}</div>
        <button type="button" class="botao contorno" id="np-editar">Editar</button></div>
        <small class="np-dica">Sem editar, o Claude escreve o roteiro com este agente e o vídeo segue para a fábrica.</small></div>
      ${revisarHtml}`;
    } else {
      campos.innerHTML = `${passos}
      <button type="button" class="link-editar" id="np-voltar">← Voltar ao vídeo</button>
      ${canaisHtml}
      <div class="np-duas">
        <label class="campo"><span>Agente do roteiro</span><select id="np-agente"><option value="">Padrão do Claude</option>${agentes.map((a) => `<option value="${a.id}" ${String(a.id) === String(N.agente) ? "selected" : ""}>${esc(a.nome)}</option>`).join("")}</select>
          ${agente?.ideal_para ? `<small class="np-ideal">Ideal para: ${esc(agente.ideal_para)}</small>` : ""}</label>
        <label class="campo"><span>Idioma</span><select id="np-lingua">${[...new Set([N.lingua, ...LINGUAS])].map((l) => `<option ${l === N.lingua ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
      </div>
      <div class="campo"><span>Roteiro</span><div class="np-modos">
        <button type="button" class="chip ${N.modo === "claude" ? "ativo" : ""}" data-modo="claude">O Claude escreve</button>
        <button type="button" class="chip ${N.modo === "manual" ? "ativo" : ""}" data-modo="manual">Já tenho o roteiro</button></div></div>
      ${N.modo === "manual" ? `<label class="campo"><textarea id="np-roteiro" rows="8" placeholder="Cole aqui o roteiro inteiro (só o que vai ser narrado)">${esc(N.roteiro)}</textarea></label>` : `
      <div class="campo"><span>Tamanho do roteiro <small>(em caracteres)</small></span>
        <div class="np-tamanho"><input id="np-caracteres" type="number" min="1000" max="80000" step="10" value="${N.caracteres}">
          <b>≈ ${Math.round(minutos())} min · ~${palavras().toLocaleString("pt-BR")} palavras</b></div>
        <div class="np-atalhos">${ATALHOS_MIN.map((m) => `<button type="button" class="chip ${Math.round(minutos()) === m ? "ativo" : ""}" data-min="${m}">${m} min</button>`).join("")}</div>
        <small class="np-dica">De 1.000 a 80.000 caracteres. A conta usa a velocidade da voz do canal (${N.ppm} palavras por minuto).</small></div>
      <div class="np-duas">
        <label class="campo"><span>Nicho <small>(opcional)</small></span><input id="np-nicho" value="${esc(N.nicho)}" placeholder="Ex.: grandes marcas"></label>
        <label class="campo"><span>Observação para o roteiro <small>(opcional)</small></span><input id="np-obs" value="${esc(N.obs)}" placeholder="Ex.: sem gírias, fechar com pergunta"></label>
      </div>`}
      ${revisarHtml}`;
    }
    const $n = (id) => campos.querySelector("#" + id);
    $n("np-editar")?.addEventListener("click", () => { N.passo = 2; desenhar(); });
    $n("np-voltar")?.addEventListener("click", () => { N.passo = 1; desenhar(); });
    $n("np-titulo")?.addEventListener("input", (e) => { N.titulo = e.target.value; desenharPrevia(); });
    $n("np-link")?.addEventListener("change", async (e) => {
      N.link = e.target.value.trim(); N.ref = null;
      if (N.link) { try { N.ref = await api("/api/titulo-do-video?" + consulta({ link: N.link })); } catch { N.ref = null; } }
      desenhar(); desenharPrevia();
    });
    campos.querySelector(".np-usar")?.addEventListener("click", () => { N.titulo = N.ref.titulo; desenhar(); desenharPrevia(); });
    campos.querySelectorAll(".np-canal").forEach((b) => (b.onclick = () => escolherCanal(b.dataset.id)));
    // foto do canal que não carrega (link velho do YouTube): fica a sigla
    campos.querySelectorAll(".np-canal img").forEach((img) => (img.onerror = () => {
      const i = document.createElement("i"); i.textContent = img.dataset.sigla; img.replaceWith(i);
    }));
    $n("np-agente")?.addEventListener("change", (e) => { N.agente = e.target.value; desenhar(); desenharPrevia(); });
    $n("np-lingua")?.addEventListener("change", (e) => { N.lingua = e.target.value; desenharPrevia(); });
    campos.querySelectorAll("[data-modo]").forEach((b) => (b.onclick = () => { N.modo = b.dataset.modo; desenhar(); desenharPrevia(); }));
    $n("np-roteiro")?.addEventListener("input", (e) => { N.roteiro = e.target.value; desenharPrevia(); });
    $n("np-caracteres")?.addEventListener("change", (e) => { N.caracteres = Math.max(1000, Math.min(80000, Number(e.target.value) || 0)); desenhar(); atualizarCusto(); });
    campos.querySelectorAll("[data-min]").forEach((b) => (b.onclick = () => {
      N.caracteres = Math.round(Number(b.dataset.min) * N.ppm * CARACTERES_POR_PALAVRA / 10) * 10; desenhar(); atualizarCusto();
    }));
    $n("np-nicho")?.addEventListener("input", (e) => { N.nicho = e.target.value; });
    $n("np-obs")?.addEventListener("input", (e) => { N.obs = e.target.value; });
    $n("np-revisar").onchange = (e) => { N.revisar = e.target.checked; desenharPrevia(); };
  }

  const enviar = (botao, comecar) => carregando(botao, comecar ? "Criando…" : "Salvando…", async () => {
    const erro = fundo.querySelector(".np-erro");
    erro.textContent = "";
    if (!N.titulo.trim()) { erro.textContent = "Escreva o título do vídeo."; return; }
    if (!N.canal) { erro.textContent = "Escolha o canal."; N.passo = 2; desenhar(); return; }
    const pedido = { titulo: N.titulo, link: N.link, canal_id: N.canal, agente_id: N.agente, lingua: N.lingua, revisar: N.revisar,
      ...(N.modo === "manual" ? { roteiro_manual: N.roteiro } : { caracteres: N.caracteres, nicho: N.nicho, observacao: N.obs }) };
    try {
      await api("/api/fila", { method: "POST", body: { pedido, comecar } });
    } catch (e) { erro.textContent = e.message; return; }
    fechar();
    aviso(comecar ? "Na fila: o vídeo começa quando a fábrica tiver vaga." : "Guardado na Entrada.");
    if (rotaAtual() === "acompanhar") acompanhar(); else location.hash = "#/acompanhar";
  });
  fundo.querySelector("#np-entrada").onclick = (e) => enviar(e.currentTarget, false);
  fundo.querySelector("#np-comecar").onclick = (e) => enviar(e.currentTarget, true);

  desenhar(); desenharPrevia();
  if (N.canal) escolherCanal(N.canal); else atualizarCusto();
  if (N.link) campos.querySelector("#np-link").dispatchEvent(new Event("change"));
  campos.querySelector("#np-titulo").focus();
}

// ---------------------------------------------------------------- painel da direita: ideias salvas

// ---------------------------------------------------------------- 🎯 e "inscrever no algoritmo": a pessoa ensina o algoritmo
// O 🎯 é uma curtida para o algoritmo de um canal dela ("quero ideias assim"); inscrever um canal faz o mesmo com o canal
// inteiro. Quanto mais ela marca, mais as ideias daquele canal ficam parecidas com o que ela quer.

let ALVOS = {};
const DICA_ALVO = "🎯 Ensinar o algoritmo: “quero ideias assim”. Funciona como uma curtida: quanto mais você marca, melhores ficam as ideias e as buscas do seu canal.";
const DICA_INSCREVER = "Inscrever no algoritmo: os assuntos deste canal passam a pesar nas ideias do seu canal, e os vídeos dele que estouram aparecem primeiro.";
async function carregarAlvos() { try { ALVOS = (await api("/api/alvos")).canais; } catch { ALVOS = {}; } }
function canalDoContexto() { return ["ideias-canal", "treino", "canal"].includes(rotaAtual()) && CANAL_ATUAL ? CANAL_ATUAL : ""; }
function temAlvo(tipo, valor) {
  const c = canalDoContexto();
  return c ? (ALVOS[c]?.[tipo] || []).includes(valor) : Object.values(ALVOS).some((x) => (x[tipo] || []).includes(valor));
}
const botaoAlvo = (_v) => "";
const _botaoAlvoAntigo = (v) => `<button class="alvo ${temAlvo("videos", v.id) ? "ligado" : ""}" data-dica="${DICA_ALVO}" aria-label="Ensinar o algoritmo">🎯</button>`;
const botaoInscrever = (_c) => "";
const _botaoInscreverAntigo = (canalId) => `<button class="inscrever ${temAlvo("canais", canalId) ? "ligado" : ""}" data-inscrever="${esc(canalId)}" data-dica="${DICA_INSCREVER}">${temAlvo("canais", canalId) ? "✓ Inscrito" : "+ Inscrever"}</button>`;

// para qual canal da pessoa vai o ensino: o da página aberta; senão o único; senão ela escolhe num menu
async function escolherMeuCanal(botao) {
  const noCanal = canalDoContexto();
  if (noCanal) return noCanal;
  const canais = await meusCanais();
  if (!canais.length) { aviso("Adicione um canal seu primeiro, em Meus canais."); return ""; }
  if (canais.length === 1) return canais[0].id;
  document.querySelector(".menu-alvo")?.remove();
  return new Promise((resolver) => {
    const menu = document.createElement("div");
    menu.className = "menu-bloq menu-alvo";
    menu.innerHTML = "<small>Ensinar o algoritmo de qual canal?</small>" + canais.map((c) => `<button data-id="${esc(c.id)}">${esc(c.titulo)}</button>`).join("");
    document.body.appendChild(menu);
    const r = botao.getBoundingClientRect();
    menu.style.left = Math.max(8, Math.min(window.innerWidth - 250, r.left + window.scrollX)) + "px";
    menu.style.top = r.bottom + window.scrollY + 6 + "px";
    const fechar = (e) => {
      if (e.target.closest(".menu-alvo button")) { resolver(e.target.closest("button").dataset.id); menu.remove(); document.removeEventListener("click", fechar, true); }
      else if (!e.target.closest(".menu-alvo")) { resolver(""); menu.remove(); document.removeEventListener("click", fechar, true); }
    };
    setTimeout(() => document.addEventListener("click", fechar, true));
  });
}

document.addEventListener("click", async (e) => {
  const alvo = e.target.closest(".alvo"), inscrever = e.target.closest("[data-inscrever]");
  if (!alvo && !inscrever) return;
  e.preventDefault(); e.stopPropagation();
  const botao = alvo || inscrever;
  const canal = await escolherMeuCanal(botao);
  if (!canal) return;
  const nome = ((await meusCanais()).find((c) => c.id === canal) || {}).titulo || "seu canal";
  ALVOS[canal] = ALVOS[canal] || { videos: [], canais: [] };
  try {
    if (alvo) {
      const v = alvo.closest(".video"), ligar = !(ALVOS[canal].videos.includes(v.dataset.video));
      const r = await api("/api/alvos", { method: "POST", body: { canal_id: canal, video_id: v.dataset.video, titulo: v.dataset.titulo, ligar } });
      ALVOS[canal].videos = ligar ? [...ALVOS[canal].videos, v.dataset.video] : ALVOS[canal].videos.filter((x) => x !== v.dataset.video);
      document.querySelectorAll(`.video[data-video="${CSS.escape(v.dataset.video)}"] .alvo`).forEach((b) => b.classList.toggle("ligado", ligar));
      aviso(ligar ? `🎯 Ensinado ao algoritmo de ${nome} (${r.alvos} ${r.alvos === 1 ? "vídeo" : "vídeos"}). Quanto mais 🎯, melhores as ideias.` : "🎯 Tirado do algoritmo.");
    } else {
      const ref = inscrever.dataset.inscrever, ligar = !(ALVOS[canal].canais.includes(ref));
      const r = await api("/api/alvos/canal", { method: "POST", body: { canal_id: canal, ref_canal_id: ref, ligar } });
      ALVOS[canal].canais = ligar ? [...ALVOS[canal].canais, ref] : ALVOS[canal].canais.filter((x) => x !== ref);
      document.querySelectorAll(`[data-inscrever="${CSS.escape(ref)}"]`).forEach((b) => { b.classList.toggle("ligado", ligar); b.textContent = ligar ? "✓ Inscrito" : "+ Inscrever"; });
      aviso(ligar ? `Canal inscrito no algoritmo de ${nome} (${r.inscritos} ${r.inscritos === 1 ? "canal" : "canais"}). Os assuntos dele já contam nas ideias.` : "Canal tirado do algoritmo.");
    }
  } catch (erro) { aviso(porque(erro)); }
}, true);

let PAINEL_ABA = guardado("painel-aba", null);
let PAINEL_MODO = guardado("painel-modo2", "ideias");

async function painel(abrir) {
  let caixa = document.getElementById("painel-ideias");
  if (!caixa) {
    document.body.insertAdjacentHTML("beforeend", `<div id="abas-direita"></div><aside id="painel-ideias" hidden></aside>`);
    caixa = document.getElementById("painel-ideias");
  }
  const abas = document.getElementById("abas-direita");
  abas.hidden = !EU;
  if (!EU) { caixa.hidden = true; return; }
  if (abrir !== undefined) { caixa.hidden = !abrir; guardar("painel-aberto", abrir); abas.classList.toggle("com-painel", !!abrir); }
  // o painel abre nos vídeos mandados fazer: o link da referência e a thumbnail para copiar (pedido do usuário em
  // 2026-10-18); as ideias salvas ficam na segunda aba
  const [d, { roteiros }, { tarefas }] = await Promise.all([api("/api/ideias-salvas"), api("/api/roteiros").catch(() => ({ roteiros: [] })),
    api("/api/roteiros/tarefas").catch(() => ({ tarefas: [] }))]);
  const escrevendo = tarefas.filter((t) => t.estado === "rodando");
  // a aba na borda direita fica sempre à mão, em qualquer página, para abrir e fechar o painel (pedido do usuário em
  // 2026-10-18); com o painel aberto ela encosta nele e vira o "fechar"
  abas.hidden = false;
  abas.classList.toggle("com-painel", !caixa.hidden);
  abas.innerHTML = `<button class="aba-lateral ${caixa.hidden ? "" : "aberta"}" title="${caixa.hidden ? "Abrir" : "Fechar"} as ideias salvas e os vídeos feitos">
    <span class="seta-lat">${caixa.hidden ? "‹" : "›"}</span><span class="txt">💡 Ideias e vídeos</span>
    ${escrevendo.length ? `<span class="n girando">${escrevendo.length}</span>` : roteiros.length ? `<span class="n">${roteiros.length}</span>` : ""}</button>`;
  abas.querySelector("button").onclick = () => painel(caixa.hidden);
  const botaoIdeias = document.getElementById("bt-ideias");
  if (botaoIdeias) botaoIdeias.innerHTML = `💡 Ideias e vídeos${escrevendo.length ? ` <span class="n girando">${escrevendo.length}</span>` : roteiros.length ? ` <span class="n">${roteiros.length}</span>` : ""}`;
  if (caixa.hidden) return;
  const modo = PAINEL_MODO === "feitos" ? "feitos" : "ideias";
  const thumbDe = (r) => r.thumbnail_url || (idDoVideo(r.link) ? `/api/thumb/imagem/${idDoVideo(r.link)}` : "");
  const feitos = [...escrevendo.map((t) => ({ ...t, escrevendo: true })), ...roteiros];
  const cartaoFeito = (r, i) => {
    const th = r.escrevendo ? (idDoVideo(r.link) ? `/api/thumb/imagem/${idDoVideo(r.link)}` : "") : thumbDe(r);
    const estado = r.escrevendo ? `<span class="feito-estado escrevendo">✍️ ${esc(r.passo || "Escrevendo…")}</span>`
      : r.fabrica ? `<span class="feito-estado fabrica">🏭 Na fábrica</span>` : `<span class="feito-estado pronto">📝 Roteiro pronto</span>`;
    return `<div class="feito" data-i="${i}">
      <div class="feito-capa">${th ? `<img src="${esc(th)}" alt="" loading="lazy">` : '<div class="prod-sem-capa">🎬</div>'}${estado}</div>
      <span class="feito-canal${r.canal_nome ? "" : " sem"}">📺 ${esc(r.canal_nome || "Canal não informado")}</span>
      <b class="feito-titulo">${esc(r.titulo)}</b>
      ${r.link ? `<div class="feito-link"><a href="${esc(r.link)}" target="_blank" rel="noopener" title="Abrir a referência no YouTube">${esc(r.link.replace(/^https?:\/\/(www\.)?/, ""))}</a></div>`
        : '<div class="feito-link sem">Sem vídeo de referência</div>'}
      <div class="feito-acoes">
        ${r.link ? `<button class="botao sec" data-copiar-link>🔗 Copiar link</button>` : ""}
        ${th ? `<button class="botao sec" data-copiar-thumb>🖼 Copiar thumbnail</button><a class="botao sec" href="${esc(th)}" download="thumbnail-referencia.jpg" title="Baixar a thumbnail">⬇</a>` : ""}
      </div></div>`;
  };
  caixa.innerHTML = `<div class="painel-cab"><b>${modo === "feitos" ? "Vídeos feitos" : "Ideias salvas"}</b><button class="botao sec" id="fechar-painel">×</button></div>
    <div class="painel-modos"><button class="${modo === "ideias" ? "ativo" : ""}" data-modo="ideias">💡 Ideias salvas · ${d.total || 0}</button>
      <button class="${modo === "feitos" ? "ativo" : ""}" data-modo="feitos">🎬 Vídeos feitos · ${feitos.length}</button></div>
    <div id="painel-corpo"></div>`;
  const corpo = document.getElementById("painel-corpo");
  if (modo === "feitos") {
    corpo.innerHTML = `<div class="painel-lista">${feitos.map(cartaoFeito).join("")
      || '<p class="sub">Nenhum vídeo mandado fazer ainda. Escreva um roteiro em <a href="#/trabalho">Roteiro</a>: ele aparece aqui com o link e a thumbnail da referência.</p>'}</div>`;
    corpo.querySelectorAll(".feito").forEach((el) => {
      const r = feitos[+el.dataset.i], th = el.querySelector("img")?.getAttribute("src");
      const bl = el.querySelector("[data-copiar-link]"), bt = el.querySelector("[data-copiar-thumb]");
      if (bl) bl.onclick = async () => { try { await navigator.clipboard.writeText(r.link); } catch {
        // sem permissão da área de transferência: o jeito antigo, que funciona com o clique
        const t = Object.assign(document.createElement("textarea"), { value: r.link }); document.body.appendChild(t); t.select();
        const ok = document.execCommand("copy"); t.remove(); if (!ok) return aviso("O navegador não deixou copiar."); }
      bl.textContent = "✓ Link copiado"; };
      if (bt) bt.onclick = async () => { try { await copiarImagem(th); bt.textContent = "✓ Thumbnail copiada"; } catch { aviso("O navegador não deixou copiar. Use o ⬇ para baixar."); } };
    });
  } else {
    // todas as ideias numa lista só, sem separar por canal (pedido do usuário em 2026-10-18)
    const vistas = new Set(), ideias = d.abas.flatMap((a) => a.ideias).filter((i) => !vistas.has(i.id) && vistas.add(i.id));
    corpo.innerHTML = `<div class="painel-lista">${ideias.length ? ideias.map((i) => `<div class="ideia">
      <a href="${linkVideo(esc(i.video_id))}" target="_blank" rel="noopener"><img src="https://i.ytimg.com/vi/${esc(i.video_id)}/mqdefault.jpg" alt=""></a>
      <div class="ideia-texto"><a href="${linkVideo(esc(i.video_id))}" target="_blank" rel="noopener"><b>${esc(i.titulo)}</b></a>
        <small>${i.views ? num(i.views) + " views · " : ""}${esc(i.canal_origem || "")}</small>
        <div class="ideia-acoes"><a class="botao vermelho" href="#/trabalho" data-roteiro="${esc(i.video_id)}" data-titulo="${esc(i.titulo)}">Levar para o trabalho</a>
          <button class="botao sec tirar-ideia" data-id="${i.id}" title="Tirar">×</button></div></div></div>`).join("")
      : '<p class="sub">Nenhuma ideia salva. Use o botão <b>💡 Salvar ideia</b> nos vídeos.</p>'}</div>`;
    corpo.querySelectorAll(".tirar-ideia").forEach((b) => (b.onclick = async () => { await api(`/api/ideias-salvas/${b.dataset.id}`, { method: "DELETE" }); painel(); }));
    ligarRoteiro(corpo);
  }
  document.getElementById("fechar-painel").onclick = () => painel(false);
  caixa.querySelectorAll("[data-modo]").forEach((b) => (b.onclick = () => { PAINEL_MODO = b.dataset.modo; guardar("painel-modo2", PAINEL_MODO); painel(); }));
  // enquanto um roteiro está sendo escrito, o painel aberto se atualiza sozinho
  clearTimeout(painel.t);
  if (escrevendo.length) painel.t = setTimeout(() => { if (!caixa.hidden) painel(); }, 5000);
}

async function salvarIdeia(videoId, tituloVideo, canalId) {
  await api("/api/ideias-salvas", { method: "POST", body: { video_id: videoId, titulo: tituloVideo, canal_id: canalId } });
  PAINEL_ABA = canalId; guardar("painel-aba", canalId); PAINEL_MODO = "ideias"; guardar("painel-modo2", "ideias");
  aviso("Ideia salva no painel da direita 💡");
  painel(true);
}

// o botão "Salvar ideia" de cada vídeo: salva direto, sem perguntar o canal (pedido do usuário em 2026-10-18: as
// ideias salvas não são mais separadas por canal)
document.addEventListener("click", async (e) => {
  const botao = e.target.closest(".salvar-ideia");
  if (!botao) return;
  e.preventDefault();
  const v = botao.closest(".video");
  const noCanal = ["ideias-canal", "treino", "canal"].includes(rotaAtual()) && CANAL_ATUAL;
  salvarIdeia(v.dataset.video, v.dataset.titulo, noCanal || "");
});

// ---------------------------------------------------------------- a thumbnail no Roteiro: projetos de prompt por canal

function gerenciarThumbs(caixa, dados, canais, depois) {
  caixa.innerHTML = `<div class="bloco" style="margin-top:8px"><h3>Projetos de thumbnail</h3>
    <p class="sub">Cada projeto é um prompt pronto, com o jeito das capas de um canal. Use os campos ${esc(dados.campos)}: o Radar troca pelo título, pela descrição da thumbnail de referência e pelo nome do canal.</p>
    ${dados.projetos.map((p) => `<div class="titulo-linha"><span class="t"><b>${esc(p.nome)}</b><small>${p.canal ? esc(p.canal) : "Todos os canais"}</small></span>
      <button class="botao sec editar-thumb" data-id="${p.id}">Editar</button><button class="botao sec apagar-thumb" data-id="${p.id}">×</button></div>`).join("")}
    <input type="hidden" id="tp-id"><div class="linha"><input id="tp-nome" placeholder="Nome (ex.: capa estilo documentário)">
      <select id="tp-canal"><option value="">Todos os canais</option>${canais.map((c) => `<option value="${esc(c.id)}">${esc(c.titulo)}</option>`).join("")}</select></div>
    <textarea id="tp-prompt" rows="8">${esc(dados.padrao)}</textarea>
    <button class="botao" id="tp-salvar" style="justify-self:start">Salvar projeto de thumbnail</button></div>`;
  caixa.querySelectorAll(".editar-thumb").forEach((b) => (b.onclick = () => {
    const p = dados.projetos.find((x) => x.id === +b.dataset.id);
    caixa.querySelector("#tp-id").value = p.id; caixa.querySelector("#tp-nome").value = p.nome;
    caixa.querySelector("#tp-canal").value = p.canal_id; caixa.querySelector("#tp-prompt").value = p.prompt;
  }));
  caixa.querySelectorAll(".apagar-thumb").forEach((b) => (b.onclick = async () => {
    if (!confirm("Apagar este projeto de thumbnail?")) return;
    await api(`/api/thumb-projetos/${b.dataset.id}`, { method: "DELETE" }); depois();
  }));
  caixa.querySelector("#tp-salvar").onclick = async () => {
    try {
      await api("/api/thumb-projetos", { method: "POST", body: { id: caixa.querySelector("#tp-id").value || null, nome: caixa.querySelector("#tp-nome").value,
        canal_id: caixa.querySelector("#tp-canal").value, prompt: caixa.querySelector("#tp-prompt").value } });
      aviso("Projeto de thumbnail salvo."); depois();
    } catch (e) { aviso(porque(e)); }
  };
}

// o painel da thumbnail, à direita do Roteiro: o pedido, o estilo do canal, o Claude escreve o prompt e manda para a IA
async function painelThumb(caixa, obter) {
  const dados = await api("/api/thumb-projetos"), canais = await meusCanais();
  let ultimoCanal = null, cfg = {};
  const desenhar = async () => {
    const { link, canal, titulo } = obter();
    const vid = idDoVideo(link);
    if (canal !== ultimoCanal) { ultimoCanal = canal; cfg = canal ? await api(`/api/producao/${encodeURIComponent(canal)}`).catch(() => ({})) : {}; }
    const antes = { pedido: caixa.querySelector("#th-pedido")?.value || "", prompt: caixa.querySelector("#th-prompt")?.value || "",
      projeto: caixa.querySelector("#th-projeto")?.value ?? cfg.thumb_projeto_id ?? "", ia: caixa.querySelector("#th-ia")?.value || cfg.ia_imagem || "gemini" };
    if (canal && caixa.dataset.canal !== canal) { antes.projeto = cfg.thumb_projeto_id || ""; antes.ia = cfg.ia_imagem || "gemini"; }
    caixa.dataset.canal = canal || "";
    const lista = dados.projetos.filter((p) => !p.canal_id || p.canal_id === canal);
    const nomeIa = (ia) => (ia === "chatgpt" ? "ChatGPT" : "Gemini");
    caixa.innerHTML = `<h3 style="margin:0">🖼 Thumbnail</h3>
      ${vid ? `<img class="thumb-ref" src="/api/thumb/imagem/${esc(vid)}" alt="">` : '<div class="thumb-vazia">Cole o link do vídeo de referência e a thumbnail dele aparece aqui.</div>'}
      <textarea id="th-pedido" rows="2" placeholder="O que você quer? Ex.: igual à referência, mas sem texto · troque o leão por um lobo">${esc(antes.pedido)}</textarea>
      <div class="linha" style="gap:6px"><select id="th-projeto"><option value="">Estilo padrão</option>${lista.map((p) => `<option value="${p.id}" ${String(p.id) === String(antes.projeto) ? "selected" : ""}>Estilo: ${esc(p.nome)}</option>`).join("")}</select>
        <select id="th-ia"><option value="gemini" ${antes.ia === "gemini" ? "selected" : ""}>Gemini</option><option value="chatgpt" ${antes.ia === "chatgpt" ? "selected" : ""}>ChatGPT</option></select>
        <a href="#" id="th-projetos" class="sub" style="flex:none">estilos</a></div>
      <button class="botao" id="th-montar" ${vid ? "" : "disabled"}>✨ Criar o prompt com o Claude</button>
      <textarea id="th-prompt" rows="9" placeholder="O Claude escreve o prompt aqui, com o estilo do canal, o seu pedido e a referência.">${esc(antes.prompt)}</textarea>
      <div class="linha" style="gap:6px"><button class="botao vermelho" id="th-enviar">Enviar para o ${nomeIa(antes.ia)}</button>
        <button class="botao sec" id="th-copiar">Copiar prompt</button><button class="botao sec" id="th-copiar-img" ${vid ? "" : "disabled"}>Copiar a thumbnail</button></div>
      <p class="sub" id="th-como" style="margin:0"></p>
      <div id="th-projetos-caixa" hidden></div>`;
    const $ = (id) => caixa.querySelector("#" + id);
    $("th-ia").onchange = () => { $("th-enviar").textContent = `Enviar para o ${nomeIa($("th-ia").value)}`; };
    $("th-montar").onclick = (e) => carregando(e.currentTarget, "O Claude está escrevendo o prompt…", async () => {
      const r = await api("/api/thumb/claude", { method: "POST", body: { link, titulo: obter().titulo, pedido: $("th-pedido").value.trim(),
        projeto_id: $("th-projeto").value, ia: $("th-ia").value } });
      $("th-prompt").value = r.prompt;
    });
    $("th-copiar").onclick = (e) => { navigator.clipboard.writeText($("th-prompt").value); e.target.textContent = "Copiado ✓"; };
    $("th-copiar-img").onclick = async (e) => {
      try { await copiarImagem(`/api/thumb/imagem/${vid}`); e.target.textContent = "Copiada ✓"; } catch { aviso("O navegador não deixou copiar a imagem."); }
    };
    // ChatGPT: abre com o prompt escrito e a thumbnail copiada para colar. Gemini: abre com o prompt copiado.
    $("th-enviar").onclick = async () => {
      const prompt = $("th-prompt").value.trim();
      if (!prompt) return aviso("Crie o prompt primeiro (✨ Criar o prompt com o Claude).");
      // com a extensão: a página do ChatGPT ou do Gemini abre e ela cola o prompt E a thumbnail sozinha
      if (document.documentElement.dataset.radarExtensao) {
        const janela = abrirLateral("about:blank");
        const { id } = await api("/api/envios", { method: "POST", body: { prompt, video_id: vid } });
        const destino = ($("th-ia").value === "chatgpt" ? "https://chatgpt.com/" : "https://gemini.google.com/app") + "#radar-envio=" + id;
        if (janela) janela.location = destino;
        $("th-como").innerHTML = `O ${nomeIa($("th-ia").value)} abriu ao lado e a extensão cola o <b>prompt${vid ? " e a thumbnail de referência" : ""}</b> sozinha. Confira e aperte enviar.`;
        return;
      }
      if ($("th-ia").value === "chatgpt") {
        if (vid) { try { await copiarImagem(`/api/thumb/imagem/${vid}`); } catch {} }
        abrirLateral("https://chatgpt.com/?q=" + encodeURIComponent(prompt));
        $("th-como").innerHTML = vid ? "O ChatGPT abriu com o prompt escrito e a <b>thumbnail copiada</b>: clique na caixa de mensagem, <b>Ctrl+V</b> para colar a imagem e envie." : "O ChatGPT abriu com o prompt escrito.";
      } else {
        await navigator.clipboard.writeText(prompt);
        abrirLateral("https://gemini.google.com/app");
        $("th-como").innerHTML = "O <b>prompt está copiado</b>: no Gemini, <b>Ctrl+V</b> na caixa de mensagem." + (vid ? " Para mandar a referência junto, clique em <b>Copiar a thumbnail</b> e cole lá também." : "");
      }
    };
    $("th-projetos").onclick = (e) => {
      e.preventDefault();
      const c = $("th-projetos-caixa"); c.hidden = !c.hidden;
      if (!c.hidden) gerenciarThumbs(c, dados, canais, async () => { Object.assign(dados, await api("/api/thumb-projetos")); desenhar(); });
    };
  };
  await desenhar();
  return desenhar;
}

// ---------------------------------------------------------------- bloquear (o ⊘ em cima de cada vídeo)

document.addEventListener("click", async (e) => {
  const aberto = document.querySelector(".menu-bloq");
  const botao = e.target.closest(".bloq");
  const opcao = e.target.closest(".menu-bloq button");
  if (opcao) {
    const d = opcao.dataset, card = aberto._card;
    aberto.remove();
    await api("/api/bloqueios", { method: "POST", body: { tipo: d.tipo, valor: d.valor, rotulo: d.rotulo } });
    const alvo = d.tipo === "video" ? `.video[data-video="${CSS.escape(d.valor)}"]` : d.tipo === "canal" ? `.video[data-canal="${CSS.escape(d.valor)}"]` : `.video[data-nicho="${CSS.escape(d.valor)}"]`;
    document.querySelectorAll(alvo).forEach((v) => { v.classList.add("sumindo"); setTimeout(() => v.remove(), 260); });
    if (card && card.isConnected) { card.classList.add("sumindo"); setTimeout(() => card.remove(), 260); }
    aviso("Bloqueado. Para desfazer: Ferramentas → Bloqueados.");
    return;
  }
  if (aberto && !e.target.closest(".menu-bloq")) aberto.remove();
  if (!botao) return;
  e.preventDefault(); e.stopPropagation();
  const v = botao.closest(".video"), d = v.dataset;
  const menu = document.createElement("div");
  menu.className = "menu-bloq";
  menu.innerHTML = `<small>Não mostrar mais:</small>
    <button data-tipo="video" data-valor="${esc(d.video)}" data-rotulo="${esc(d.titulo)}">Este vídeo</button>
    ${d.canal ? `<button data-tipo="canal" data-valor="${esc(d.canal)}" data-rotulo="${esc(d.nomecanal)}">O canal ${esc(d.nomecanal)}</button>` : ""}
    ${d.nicho ? `<button data-tipo="subnicho" data-valor="${esc(d.nicho)}" data-rotulo="${esc(d.nicho)}">Vídeos de ${esc(d.nicho)}</button>` : ""}`;
  menu._card = v;
  document.body.appendChild(menu);
  const r = botao.getBoundingClientRect();
  menu.style.left = Math.max(8, Math.min(window.innerWidth - 250, r.right + window.scrollX - 230)) + "px";
  menu.style.top = r.bottom + window.scrollY + 6 + "px";
});

// ---------------------------------------------------------------- Descobrir: duas listas, canais e vídeos
// Uma tela para cada pergunta, não seis. "Canais" responde qual canal vale copiar; "Vídeos", qual vídeo fazer.
// As duas têm o mesmo esqueleto: as perguntas prontas ou o filtro em cima, a contagem, a lista e o carregar mais.
// O que era Alerta, Explorar, Procurar nicho, Em alta, Top 30, Salvos e Novidades virou filtro destas duas.

// o botão que vira a ordem: toda ordem pode ser lida dos dois lados
const botaoSentido = () => `<button class="sentido" id="sentido" type="button">↓</button>`;
function ligarSentido(f, aoMudar) {
  const b = document.getElementById("sentido");
  const pintar = () => {
    const sobe = f.sentido === "asc";
    b.textContent = sobe ? "↑" : "↓";
    b.classList.toggle("invertido", sobe);
    b.title = sobe ? "Do menor para o maior: clique para inverter" : "Do maior para o menor: clique para inverter";
  };
  b.onclick = () => { f.sentido = f.sentido === "asc" ? "" : "asc"; pintar(); aoMudar(); };
  return pintar;
}

// as marcas: os liga-desliga do filtro, que não cabem num select porque valem junto com todos os outros
function marcas(defs, f) {
  return `<div class="chips marcas">${defs.map(([k, rot, dica]) =>
    `<button class="chip ${f[k] === "1" ? "ativo" : ""}" data-marca="${k}" title="${esc(dica)}">${esc(rot)}</button>`).join("")}</div>`;
}
function ligarMarcas(raiz, f, aoMudar) {
  const botoes = [...raiz.querySelectorAll("[data-marca]")];
  botoes.forEach((b) => (b.onclick = () => {
    const k = b.dataset.marca;
    f[k] = f[k] === "1" ? "" : "1";
    b.classList.toggle("ativo", f[k] === "1");
    aoMudar();
  }));
  return () => botoes.forEach((b) => b.classList.toggle("ativo", f[b.dataset.marca] === "1"));
}

// a faixa das visões: a regra de cada uma vem do servidor, aqui só o rótulo e o que ela já tem de canal
function faixaVisoes(caixa, vs, f, aoEscolher) {
  caixa.hidden = !vs.length;
  if (!vs.length) return;
  const atual = vs.find((v) => v.chave === f.visao);
  caixa.innerHTML = `<div class="chips">${vs.map((v) => `<button class="chip ${v.chave === f.visao ? "ativo" : ""}"
    data-visao="${esc(v.chave)}" title="${esc(v.dica)}">${esc(v.rotulo)} <span class="n">${num(v.canais)}</span></button>`).join("")}</div>
    ${atual ? `<p class="visao-dica">${esc(atual.dica)}</p>` : ""}`;
  caixa.querySelectorAll("[data-visao]").forEach((b) => (b.onclick = () => aoEscolher(vs.find((x) => x.chave === b.dataset.visao))));
}

// as opções do select de pasta: as que existem, mais "sem pasta" para achar o que ainda não foi guardado
const opcoesDePasta = (p) => [...p.pastas.map((x) => [x.nome, `📁 ${x.nome} (${x.canais})`]),
  ...(p.sem_pasta ? [["sem_pasta", `Sem pasta (${p.sem_pasta})`]] : [])];

const PADRAO_BASE = { visao: "", busca: "", base: "", pasta: "", nicho: "", inscritos_max: "", media_min: "",
  tamanho: "", idade: "", fase: "", ordem: "media", sentido: "", modo: "", etapa: "",
  vida_forma: "", vida_etapa: "" };
// as etapas da curva da vida, nos MESMOS dias do radar/nichos.py, convertidos em meses porque é assim que o
// filtro da lista pede a idade. Com meses redondos (1, 3, 6, 24) a lista trazia um canal a mais que a faixa.
const DIA_MES = 30.44;
const ETAPAS_DIAS = { testando: [0, 30], decolando: [30, 90], disputando: [90, 180], firme: [180, 730], veterano: [730, null] };
const emMeses = (dias) => (dias === null || dias === undefined ? "" : String(dias / DIA_MES));

// ---------------------------------------------------------------- as três visões da tela Canais
// Pedido do usuário em 2026-10-25, com duas telas do Dotti Finder na mão. A mesma lista de canais, olhada de três
// jeitos: um por um (a lista de sempre), pela idade de quem posta (a curva da vida) e por nicho (a tabela).
// A conta é nossa (radar/nichos.py), feita com o que o Radar mede; aqui só se desenha.

const MODOS = [["", "Canais", "um cartão por canal"], ["vida", "Curva da vida", "em que etapa estão os canais"],
  ["nichos", "Por nicho", "uma linha por nicho, para comparar"]];
// o vermelho de verdade (--detalhe), nao o --vermelho-claro: nos temas de acento marrom ele sai bege e
// "tarde para entrar" perdia o aviso
const COR_VEREDITO = { entrar: "var(--verde)", apertado: "var(--laranja)", tarde: "var(--detalhe)" };

function faixaModos(caixa, f, trocar) {
  caixa.innerHTML = MODOS.map(([v, nome, dica]) =>
    `<button class="modo${(f.modo || "") === v ? " ligado" : ""}" data-modo="${v}" title="${esc(dica)}">${esc(nome)}</button>`).join("");
  caixa.querySelectorAll("[data-modo]").forEach((b) => (b.onclick = () => trocar(b.dataset.modo)));
}

// quanto tempo de vida a etapa cobre, escrito como se fala
function idadeEmPalavras(de, ate) {
  const mes = (d) => Math.round(d / DIA_MES);
  const anos = (d) => Math.round(d / 365);
  if (ate === null) return mes(de) >= 12 ? `mais de ${anos(de)} anos` : `mais de ${mes(de)} meses`;
  if (de === 0) return `até ${ate} dias`;
  return mes(ate) >= 12 ? `${mes(de)} meses a ${anos(ate)} anos` : `${mes(de)} a ${mes(ate)} meses`;
}

// Quatro jeitos de olhar a mesma faixa. Pedido do usuário em 2026-10-25: a curva da vida tinha um desenho só, o
// de barras, e ele quis escolher. Os quatro saem dos MESMOS números do /api/nichos/vida — nenhum recalcula nada,
// só mostra de outro jeito. E clicar numa etapa, em qualquer uma das formas, abre os VÍDEOS dela aqui embaixo
// (antes o clique trocava de tela e levava para a lista de canais; isso virou um botão dentro do bloco).
const FORMAS_VIDA = [["barras", "Barras", "a altura de cada etapa diz quantos canais"],
  ["faixa", "Faixa inteira", "uma régua só: cada etapa com a sua fatia do nicho"],
  ["funil", "Funil", "uma linha por etapa, do começo da vida ao fim"],
  ["tabela", "Tabela", "os números de todas as etapas lado a lado"]];

const altura = (n, topo) => Math.max(Math.round((n / (topo || 1)) * 100), n ? 3 : 0);

function desenhoVida(d, forma, escolhida) {
  const topo = d.topo || 1;
  const cor = (e) => COR_VEREDITO[e.veredito];
  const marcada = (e) => (e.chave === escolhida ? " escolhida" : "");
  if (forma === "faixa") {
    const total = d.etapas.reduce((s, e) => s + e.canais, 0) || 1;
    return `<div class="vida-regua">${d.etapas.map((e) => `<button class="vida-fatia${marcada(e)}" data-etapa="${esc(e.chave)}"
        style="flex:${e.canais || 0.15};background:${cor(e)}" title="${esc(e.nome)}: ${num(e.canais)} canais">
        <span>${Math.round((e.canais / total) * 100)}%</span></button>`).join("")}</div>
      <div class="vida-legenda">${d.etapas.map((e) => `<button class="vida-chip${marcada(e)}" data-etapa="${esc(e.chave)}">
        <i style="background:${cor(e)}"></i><b>${esc(e.nome)}</b>
        <small>${num(e.canais)} ${e.canais === 1 ? "canal" : "canais"} · ${esc(idadeEmPalavras(e.de, e.ate))}</small></button>`).join("")}</div>`;
  }
  if (forma === "funil") {
    return `<div class="vida-funil">${d.etapas.map((e) => `<button class="vida-degrau${marcada(e)}" data-etapa="${esc(e.chave)}">
      <span class="vida-degrau-nome"><b>${esc(e.nome)}</b><small>${esc(idadeEmPalavras(e.de, e.ate))}</small></span>
      <span class="vida-degrau-barra"><i style="width:${altura(e.canais, topo)}%;background:${cor(e)}"></i></span>
      <span class="vida-degrau-n"><b>${num(e.canais)}</b><small>${e.views_mes ? `${num(e.views_mes)} views/mês` : "ninguém postou"}</small></span>
      <span class="vida-selo" style="color:${cor(e)};border-color:${cor(e)}">${esc(e.veredito_nome)}</span></button>`).join("")}</div>`;
  }
  if (forma === "tabela") {
    return `<table class="tabela tab-vida"><thead><tr><th>Etapa</th><th>Tempo postando</th><th class="n">Canais</th>
        <th class="n">Postaram no mês</th><th class="n">Crescendo</th><th class="n">Views/mês</th><th>Para entrar</th><th></th></tr></thead>
      <tbody>${d.etapas.map((e) => `<tr class="${e.chave === escolhida ? "escolhida" : ""}">
        <td><b>${esc(e.nome)}</b><small class="sub"> · ${esc(e.o_que)}</small></td>
        <td>${esc(idadeEmPalavras(e.de, e.ate))}</td>
        <td class="n">${num(e.canais)}</td><td class="n">${num(e.postando || 0)}</td>
        <td class="n" style="color:var(--verde)">${e.crescendo || "—"}</td>
        <td class="n">${e.views_mes ? num(e.views_mes) : "—"}</td>
        <td><span class="vida-selo" style="color:${cor(e)};border-color:${cor(e)}">${esc(e.veredito_nome)}</span></td>
        <td><button class="botao sec" data-etapa="${esc(e.chave)}">ver os vídeos</button></td></tr>`).join("")}</tbody></table>`;
  }
  return `<div class="vida">${d.etapas.map((e) => `<button class="vida-et${marcada(e)}" data-etapa="${esc(e.chave)}">
    <span class="vida-barra"><i style="height:${altura(e.canais, topo)}%;background:${cor(e)}"></i></span>
    <b>${esc(e.nome)}</b><small>${esc(idadeEmPalavras(e.de, e.ate))}</small>
    <span class="vida-n">${num(e.canais)}</span><small>${e.canais === 1 ? "canal" : "canais"}</small>
    <small class="vida-mes">${e.views_mes ? `${num(e.views_mes)} views/mês em média` : "ninguém publicou este mês"}</small>
    <span class="vida-selo" style="color:${cor(e)};border-color:${cor(e)}">${esc(e.veredito_nome)}</span>
    <small class="vida-o-que">${esc(e.o_que)}</small></button>`).join("")}</div>`;
}

// os vídeos dos canais de uma etapa: a mesma lista da tela Vídeos, recortada pela idade de QUEM POSTA
async function videosDaEtapa(caixa, f, e, abrirCanais, aoFechar) {
  if (!e) { caixa.innerHTML = ""; return; }
  caixa.innerHTML = `<div class="vazio">Procurando os vídeos de ${esc(e.nome)}…</div>`;
  let d;
  try {
    d = await api("/api/videos?" + consulta({ etapa: e.chave, nicho: f.nicho, nota_min: 5, tipo: "longo",
      lingua: "ptenes", ordem: "nota", por: 12, pagina: 0 }));
  } catch (err) { caixa.innerHTML = `<div class="vazio">${esc(porque(err))}</div>`; return; }
  caixa.innerHTML = `<div class="vida-cab vida-videos-cab">
      <h3>O que estourou nos canais em ${esc(e.nome)}${f.nicho ? ` · ${esc(f.nicho)}` : ""}</h3>
      <p class="sub">Vídeos que fizeram 5x o normal do próprio canal, em canais que estão postando há
        ${esc(idadeEmPalavras(e.de, e.ate))}.${d.total ? ` São ${num(d.total)}; aqui estão os ${Math.min(12, d.total)} de maior nota.` : ""}</p>
      <div class="vida-videos-acoes"><button class="botao sec" id="vida-canais">Ver os canais desta etapa</button>
        <button class="botao sec" id="vida-fechar">Fechar</button></div></div>
    <div class="grade-videos grandes">${d.videos.map((v) => cartaoVideoGrande(v)).join("")
      || '<div class="vazio" style="grid-column:1/-1">Nenhum vídeo desta etapa ainda. O Radar só mostra o que já mediu: garimpe mais canais, ou escolha outra etapa.</div>'}</div>`;
  ligarRoteiro(caixa);
  caixa.querySelector("#vida-canais").onclick = () => abrirCanais(e.chave);
  caixa.querySelector("#vida-fechar").onclick = () => { caixa.innerHTML = ""; aoFechar(); };
}

async function visaoVida(caixa, f, abrirCanais, acompanhar) {
  caixa.innerHTML = '<div class="vazio">Contando os canais…</div>';
  let d;
  try { d = await api("/api/nichos/vida?" + consulta({ nicho: f.nicho })); }
  catch (e) { caixa.innerHTML = `<div class="vazio">${esc(porque(e))}</div>`; return; }
  if (!FORMAS_VIDA.some(([v]) => v === f.vida_forma)) f.vida_forma = "barras";
  if (!d.etapas.some((e) => e.chave === f.vida_etapa)) f.vida_etapa = "";
  caixa.innerHTML = `<div class="vida-cab"><h2>Como um nicho envelhece</h2>
      <p class="sub">Cada canal entra na etapa do tempo que ele <b>já está postando</b>${f.nicho ? ` em ${esc(f.nicho)}` : ""}.
        Muita gente nas duas primeiras significa assunto que ainda está abrindo; muita gente nas duas últimas, assunto
        com dono. A média do mês é das views dos vídeos que cada canal publicou nos últimos 30 dias.</p></div>
    <div class="modos modos-forma" id="formas-vida"></div>
    <div id="vida-desenho"></div>
    <p class="sub">${num(d.canais)} canais nesta conta${d.sem_data ? ` · ${d.sem_data} ficaram de fora (o Radar ainda não sabe quando eles começaram)` : ""}. Clique numa etapa para ver os vídeos dela aqui embaixo.</p>
    <div id="vida-videos"></div>`;
  const videos = caixa.querySelector("#vida-videos");
  const pintar = () => {
    caixa.querySelector("#formas-vida").innerHTML = FORMAS_VIDA.map(([v, nome, dica]) =>
      `<button class="modo${f.vida_forma === v ? " ligado" : ""}" data-forma="${v}" title="${esc(dica)}">${esc(nome)}</button>`).join("");
    caixa.querySelector("#vida-desenho").innerHTML = desenhoVida(d, f.vida_forma, f.vida_etapa);
    caixa.querySelectorAll("[data-forma]").forEach((b) => (b.onclick = () => {
      f.vida_forma = b.dataset.forma; acompanhar(); pintar();
    }));
    caixa.querySelectorAll("[data-etapa]").forEach((b) => (b.onclick = () => {
      f.vida_etapa = b.dataset.etapa; acompanhar(); pintar();
      videosDaEtapa(videos, f, d.etapas.find((e) => e.chave === f.vida_etapa), abrirCanais,
        () => { f.vida_etapa = ""; acompanhar(); pintar(); });
      videos.scrollIntoView({ behavior: "smooth", block: "start" });
    }));
  };
  pintar();
  if (f.vida_etapa) {
    videosDaEtapa(videos, f, d.etapas.find((e) => e.chave === f.vida_etapa), abrirCanais,
      () => { f.vida_etapa = ""; acompanhar(); pintar(); });
  }
}

async function visaoNichos(caixa, f, abrirNicho) {
  caixa.innerHTML = '<div class="vazio">Somando os nichos…</div>';
  let d;
  try { d = await api("/api/nichos/tabela?" + consulta({ nicho: f.nicho })); }
  catch (e) { caixa.innerHTML = `<div class="vazio">${esc(porque(e))}</div>`; return; }
  if (!d.nichos.length) { caixa.innerHTML = '<div class="vazio">Nenhum nicho com canais nestes filtros.</div>'; return; }
  caixa.innerHTML = `<table class="tabela tab-nichos"><thead><tr>
      <th>Nicho</th><th class="n">Canais</th><th class="n">Tráfego típico</th><th class="n">Crescendo</th>
      <th class="n">Parados</th><th class="n">Views no mês</th><th class="n">Público</th><th></th></tr></thead>
    <tbody>${d.nichos.map((l) => `<tr>
      <td><b>${esc(l.nicho)}</b>${l.novos ? `<small class="sub"> · ${l.novos} com menos de 3 meses</small>` : ""}</td>
      <td class="n">${num(l.canais)}</td>
      <td class="n" title="A mediana do normal por vídeo dos canais deste nicho">${num(l.tipico)}</td>
      <td class="n" style="color:var(--verde)">${l.crescendo || "—"}</td>
      <td class="n" style="color:${l.parados ? "var(--vermelho-claro)" : "inherit"}">${l.parados || "—"}</td>
      <td class="n">${num(l.views_mes)}</td>
      <td class="n">${num(l.publico)}</td>
      <td><button class="botao sec" data-nicho="${esc(l.nicho)}">ver canais</button></td></tr>`).join("")}</tbody></table>
    <p class="sub">Tráfego típico é a <b>mediana</b> do normal por vídeo, não a média: um canal gigante no meio de
      pequenos faria o nicho parecer o que ele não é. Views no mês são as dos vídeos publicados nos últimos
      ${d.mes_dias} dias.</p>`;
  caixa.querySelectorAll("[data-nicho]").forEach((b) => (b.onclick = () => abrirNicho(b.dataset.nicho)));
}

async function baseCanais() {
  const f = recorte(PADRAO_BASE);
  const [vs, o, p] = await Promise.all([visoes(), opcoes(), pastas()]);
  if (f.visao && !vs.some((v) => v.chave === f.visao)) f.visao = "";   // visão do endereço que não existe mais
  // o select de tamanho virou trilho: um link antigo com ?tamanho=pequeno continua abrindo a lista certa
  if (f.tamanho) { f.inscritos_max = String((TAMANHOS[f.tamanho] || {}).inscritos_max || ""); f.tamanho = ""; }
  tela.innerHTML = titulo("Canais", "Todos os canais do Radar. Escolha uma pergunta pronta, ou monte o filtro.") + `
    <div class="busca-caixa">
    <div class="visoes" id="visoes"></div>
    <div class="procura"><input id="busca" placeholder="Ex.: cobras, história de Roma, custo de vida" value="${esc(f.busca)}"><button class="botao vermelho" id="ir">Procurar</button></div>
    <div class="filtra">${selects([
      ["base", "Todos os canais", [["salvos", "Só os que eu salvei"], ["acharam", "Só os que acharam para mim"]]],
      ...(opcoesDePasta(p).length ? [["pasta", "Todas as pastas", opcoesDePasta(p)]] : []),
      ["nicho", "Todos os nichos", o.nichos.map((n) => [n.valor, n.valor])],
      ["idade", "Qualquer idade", [[1, "Canal de até 1 mês"], [3, "Até 3 meses"], [6, "Até 6 meses"], [12, "Até 1 ano"]]],
      ["fase", "Qualquer fase", [["nascendo", "Nascendo"], ["crescendo", "Crescendo"], ["estavel", "Estável"], ["caindo", "Caindo"]]],
      ["ordem", "", [["media", "Mais views por vídeo"], ["alta", "Em alta agora"], ["estourando", "Muita view para o tamanho"],
        ["pontos", "Na hora de copiar"], ["ganho", "Mais inscritos na semana"], ["jovens", "Canais mais novos"],
        ["novos", "Entraram por último"], ["inscritos", "Mais inscritos"], ["aleatorio", "Aleatório"]]],
    ], f)}${botaoSentido()}</div>
    <div class="trilhos">
      ${trilho("inscritos_max", "Inscritos", degrausDe("inscritos_max"), f)}
      ${trilho("media_min", "Views por vídeo, a partir de", degrausDe("media_min"), f)}
    </div>
    </div>
    <div class="modos" id="modos"></div>
    <div id="outra-visao"></div>
    <div id="youtube"></div>
    <div class="contagem" id="contagem"></div><div class="lista-canais" id="lista"></div>
    <div class="mais"><button class="botao sec" id="mais" hidden>Carregar mais</button></div>`;
  let pagina = 0, tentativa = 0;
  const rosto = PREFS && PREFS.sem_rosto ? "sem" : "";
  const caixaYoutube = (vazio) => {
    const termo = f.busca.trim();
    document.getElementById("youtube").innerHTML = termo ? `<div class="chamada"><span class="texto">${vazio ? "<b>Nada na base com isso.</b>" : "<b>Não achou o que queria?</b>"} Procuro "${esc(termo)}" no YouTube agora.</span>
      <button class="botao" id="no-youtube">Procurar no YouTube</button></div><div id="resultado-youtube"></div>` : "";
    const b = document.getElementById("no-youtube");
    if (b) b.onclick = (e) => noYoutube(e.currentTarget);
  };
  const noYoutube = (botao) => carregando(botao, "Procurando no YouTube… (até 1 minuto)", async () => {
    const r = await api("/api/procurar", { method: "POST", body: { termo: f.busca, tentativa } });
    tentativa = r.proxima;
    const novos = r.canais.filter((c) => c.novo).length;
    const caixa = document.getElementById("resultado-youtube");
    caixa.innerHTML = `<p class="linha-sub">Achei <b style="color:var(--verde)">${novos} canais novos</b> e ${r.canais.length - novos} que já estavam no Radar.</p>
      <div class="lista-canais">${r.canais.map((c) => cartaoCanal(c)).join("") || '<div class="vazio">Nenhum canal novo desta vez.</div>'}</div>
      <div class="chamada"><span class="texto">Não era isso? Procuro de outro jeito (outro período, outro formato ou em inglês).</span><button class="botao" id="de-novo">Procurar de novo</button></div>`;
    ligarCartoes(caixa); esquecer("/api/filtros", "/api/visoes");
    document.getElementById("de-novo").onclick = (e) => noYoutube(e.currentTarget);
  });
  const carregar = async (mais = false) => {
    const outra = document.getElementById("outra-visao");
    faixaModos(document.getElementById("modos"), f, (m) => { f.modo = m; f.etapa = ""; acompanhar(); carregar(); });
    // fora do modo lista a tela é outra: a lista, a contagem e a caixa do YouTube somem em vez de ficarem embaixo
    for (const id of ["lista", "contagem", "mais", "youtube"]) document.getElementById(id).hidden = !!f.modo;
    outra.hidden = !f.modo;
    if (f.modo === "vida") {
      return visaoVida(outra, f, (etapa) => { f.modo = ""; f.etapa = etapa; acompanhar(); carregar(); }, () => acompanhar());
    }
    if (f.modo === "nichos") {
      return visaoNichos(outra, f, (nicho) => {
        f.modo = ""; f.nicho = nicho;
        // o select tem de mostrar o nicho escolhido na tabela, senao o filtro fica ligado sem aparecer onde
        const sel = tela.querySelector('select[data-f="nicho"]');
        if (sel) sel.value = nicho;
        sincronizar(); acompanhar(); carregar();
      });
    }
    pagina = mais ? pagina + 1 : 0;
    const lista = document.getElementById("lista");
    let d;
    // o carregar é chamado sem await (a tela já está montada): o erro morre aqui, dito na própria lista
    try { d = await api("/api/radar?" + consulta({ ...paraApi({ ...f, rosto }), pagina, por: 30 })); }
    catch (e) { lista.innerHTML = `<div class="vazio">${esc(porque(e))}</div>`; return; }
    const html = d.canais.map((c) => cartaoCanal(c)).join("");
    if (mais) lista.insertAdjacentHTML("beforeend", html);
    else lista.innerHTML = html || '<div class="vazio">Nenhum canal com esses filtros. Afrouxe um, ou procure o assunto no YouTube.</div>';
    const quantos = lista.querySelectorAll(".canal").length;
    avisarPiso(tela, "media_min", d.media_min, f.media_min, (n) =>
      `O piso é ${num(n)}: abaixo disso o canal nem teria entrado no Radar. Para subir, arraste para a direita.`);
    const piso = d.media_min > (Number(f.media_min) || 0) ? ` · piso de ${num(d.media_min)} por vídeo` : "";
    const daEtapa = f.etapa ? ` · só a etapa ${f.etapa}` : "";
    document.getElementById("contagem").textContent = d.total
      ? `${d.total.toLocaleString("pt-BR")} ${d.total === 1 ? "canal" : "canais"} na base · mostrando ${quantos}${piso}${daEtapa}` : "";
    document.getElementById("mais").hidden = quantos >= d.total;
    if (!mais) caixaYoutube(!d.total);
    ligarCartoes(lista);
  };
  const desenharVisoes = () => faixaVisoes(document.getElementById("visoes"), vs, f, (v) => {
    const ligar = f.visao !== v.chave;
    f.visao = ligar ? v.chave : "";
    f.ordem = ligar ? v.ordem : PADRAO_BASE.ordem;
    f.sentido = "";
    tela.querySelector('select[data-f="ordem"]').value = f.ordem;
    sincronizar(); acompanhar(); carregar();
  });
  let pintarSentido = () => {}, pintarTrilhos = () => {};
  const sincronizar = () => { pintarSentido(); pintarTrilhos(); desenharVisoes(); };
  const acompanhar = ligarSelects(tela, f, PADRAO_BASE, () => { sincronizar(); carregar(); }, ["busca"]);
  pintarSentido = ligarSentido(f, () => { acompanhar(); carregar(); });
  pintarTrilhos = ligarTrilhos(tela, f, degrausDe, () => { acompanhar(); carregar(); });
  const ir = () => { f.busca = document.getElementById("busca").value.trim(); tentativa = 0; acompanhar(); carregar(); };
  document.getElementById("ir").onclick = ir;
  document.getElementById("busca").onkeydown = (e) => { if (e.key === "Enter") ir(); };
  document.getElementById("mais").onclick = () => carregar(true);
  sincronizar();
  carregar();
}

// os degraus dos trilhos: a escala que faz sentido para cada número, do "qualquer" ao teto
const DEGRAUS = {
  views_min: [["", "qualquer"], [10000, "10 mil"], [50000, "50 mil"], [100000, "100 mil"], [500000, "500 mil"],
    [1000000, "1 milhão"], [5000000, "5 milhões"], [10000000, "10 milhões"]],
  inscritos_max: [["", "qualquer tamanho"], [1000, "até 1 mil"], [5000, "até 5 mil"], [10000, "até 10 mil"],
    [50000, "até 50 mil"], [100000, "até 100 mil"], [500000, "até 500 mil"]],
  media_min: [["", "qualquer"], [10000, "10 mil"], [50000, "50 mil"], [100000, "100 mil"], [300000, "300 mil"],
    [1000000, "1 milhão"]],
};
const degrausDe = (k) => DEGRAUS[k] || [["", "qualquer"]];

const PADRAO_VIDEOS = { base: "", pasta: "", busca: "", lingua: "ptenes", nicho: "", nota_min: "5", publicado_dias: "", tipo: "longo",
  views_min: "", modelar_estado: "", ordem: "nota", sentido: "", so_novos: "", so_crescendo: "", com_cortados: "" };

// A tela travada. Pedido do usuário em 2026-10-25: a lista infinita rolava embaixo da busca e ele perdia de vista
// o que já tinha olhado. Travar mostra 10 vídeos de cada vez, com Anterior e Próximo, recolhe o núcleo de busca
// numa aba que se puxa de volta, e dá a cada vídeo um jeito de ser SEPARADO (botão ou arrastando) para uma pilha
// em cima — a pilha dos que ele quer rever depois.
//
// A pilha vive SÓ NESTA JANELA, de propósito, como ele pediu: não vai para o servidor nem para o endereço. Fechou
// a aba, acabou. Quem quiser guardar de verdade tem a esteira (🔖 no canto da capa) e o 💡 Salvar ideia, que já
// gravam. Isto aqui é a mesa de trabalho de uma sessão de garimpo, não um arquivo.
async function videosLista() {
  const f = recorte(PADRAO_VIDEOS);
  const [o, p] = await Promise.all([opcoes(), pastas()]);
  tela.innerHTML = titulo("Vídeos", "Todos os vídeos que fizeram muitas vezes o normal do próprio canal: o assunto já provou que dá view.") + `
    <div class="grande-acao"><button class="botao" id="mais-youtube">Buscar vídeos novos no YouTube</button>
      <button class="botao sec" id="travar" title="Mostra 10 de cada vez, recolhe a busca e deixa você separar os que quer rever">📌 Travar 10 na tela</button></div>
    <button class="puxar-busca" id="puxar" hidden>🔍 Abrir a busca e os filtros</button>
    <div class="busca-caixa" id="busca-caixa">
    <div class="procura"><input id="busca" placeholder="Procurar no título do vídeo ou do canal" value="${esc(f.busca)}"><button class="botao vermelho" id="ir">Procurar</button></div>
    <div class="filtra">${selects([
      ["base", "Todos os canais", [["salvos", "Só os que eu salvei"], ["acharam", "Só os que acharam para mim"]]],
      ...(opcoesDePasta(p).length ? [["pasta", "Todas as pastas", opcoesDePasta(p)]] : []),
      ["modelar_estado", "Toda a esteira", [["fila", "🔖 Vou modelar"], ["feito", "✓ Já modelei"]]],
      ["lingua", "", [["ptenes", "Português, inglês e espanhol"], ["pt", "Só português"], ["en", "Só inglês"], ["es", "Só espanhol"], ["todas", "Todas as línguas"]]],
      ["nicho", "Todos os nichos", o.nichos.map((n) => [n.valor, n.valor])],
      ["nota_min", "", [[3, "3x o normal ou mais"], [5, "5x ou mais"], [10, "10x ou mais"], [20, "20x ou mais"]]],
      ["publicado_dias", "Qualquer data", [[7, "Últimos 7 dias"], [30, "Últimos 30 dias"], [90, "Últimos 3 meses"], [365, "Último ano"]]],
      ["tipo", "Longos e Shorts", [["longo", "Só vídeos longos"], ["curto", "Só Shorts"]]],
      ["ordem", "", [["nota", "Maior nota"], ["por_hora", "Views por hora"], ["views", "Mais views"], ["recentes", "Mais recentes"],
        ["inscritos", "Canal maior"], ["achados", "Achados por último"], ["aleatorio", "Aleatório"]]],
    ], f)}${botaoSentido()}</div>
    <div class="trilhos">${trilho("views_min", "Views a partir de", degrausDe("views_min"), f)}</div>
    ${marcas([
      ["so_novos", "Só os desta semana", "O vídeo saiu nos últimos 7 dias"],
      ["so_crescendo", "Só de canal crescendo", "O canal está acelerando agora, não é um acerto antigo"],
      ["com_cortados", "Mostrar o que foi cortado", "Inclui o que as suas respostas e os seus bloqueios estavam escondendo"],
    ], f)}
    </div>
    <div class="separados" id="separados" hidden></div>
    <div class="contagem" id="contagem"></div><div class="grade-videos grandes" id="lista"></div>
    <div class="paginador" id="paginador" hidden>
      <button class="botao sec" id="ant">← Anterior</button>
      <span class="pag-onde" id="pag-onde"></span>
      <button class="botao sec" id="prox">Próximo →</button></div>
    <div class="mais"><button class="botao sec" id="mais" hidden>Carregar mais</button></div>`;
  const POR = 24, POR_TRAVADO = 10;
  let pagina = 0, travado = false, paginas = 1;
  const separados = [];                 // a pilha desta janela, na ordem em que ele separou
  const naTela = new Map();             // id → vídeo da página que está na tela, para saber o que arrastaram
  const caixaBusca = document.getElementById("busca-caixa");
  const bandeja = document.getElementById("separados");

  const pintarSeparados = () => {
    bandeja.hidden = !travado && !separados.length;
    bandeja.innerHTML = `<div class="sep-cab"><b>Separados para ver depois · ${separados.length}</b>
        <span class="sub">Arraste um vídeo para cá, ou clique em <b>Separar</b>. Esta pilha vive só nesta janela: para guardar de verdade, use o 🔖 da capa ou o 💡 Salvar ideia.</span>
        ${separados.length ? '<button class="botao sec" id="sep-limpar">Limpar a pilha</button>' : ""}</div>
      <div class="sep-itens">${separados.map((v) => `<div class="sep-item" data-sep="${esc(v.id)}">
        <a href="${linkVideo(esc(v.id))}" target="_blank" rel="noopener"><img src="https://i.ytimg.com/vi/${esc(v.id)}/mqdefault.jpg" alt="" loading="lazy"></a>
        <div class="sep-texto"><a href="${linkVideo(esc(v.id))}" target="_blank" rel="noopener">${esc(v.titulo)}</a>
          <small>${esc(v.canal || "")}${v.nota != null ? ` · ${nota(v.nota)} o normal` : ""}</small></div>
        <button class="sep-tirar" data-tirar="${esc(v.id)}" title="Tirar da pilha">✕</button></div>`).join("")
        || '<div class="vazio">Nada separado ainda.</div>'}</div>`;
    const limpar = document.getElementById("sep-limpar");
    if (limpar) limpar.onclick = () => { separados.length = 0; pintarSeparados(); marcarSeparados(); };
    bandeja.querySelectorAll("[data-tirar]").forEach((b) => (b.onclick = () => {
      const i = separados.findIndex((v) => v.id === b.dataset.tirar);
      if (i >= 0) separados.splice(i, 1);
      pintarSeparados(); marcarSeparados();
    }));
  };
  const separar = (id) => {
    const v = naTela.get(id);
    if (!v || separados.some((x) => x.id === id)) return;
    separados.push(v); pintarSeparados(); marcarSeparados();
  };
  // o que já está na pilha fica apagado na grade, para ele não separar duas vezes nem reler o mesmo vídeo
  const marcarSeparados = () => document.getElementById("lista").querySelectorAll(".video.yt").forEach((c) => {
    const ja = separados.some((v) => v.id === c.dataset.video);
    c.classList.toggle("separado", ja);
    const b = c.querySelector(".separar");
    if (b) b.textContent = ja ? "✓ Separado" : "⇥ Separar";
  });
  bandeja.addEventListener("dragover", (e) => { e.preventDefault(); bandeja.classList.add("recebendo"); });
  bandeja.addEventListener("dragleave", () => bandeja.classList.remove("recebendo"));
  bandeja.addEventListener("drop", (e) => {
    e.preventDefault(); bandeja.classList.remove("recebendo");
    separar(e.dataTransfer.getData("text/plain"));
  });

  const carregar = async (mais = false, mesmaPagina = false) => {
    if (!mesmaPagina) pagina = mais ? pagina + 1 : 0;
    const por = travado ? POR_TRAVADO : POR;
    const lista = document.getElementById("lista");
    let d;
    try {
      d = await api("/api/videos?" + consulta({ ...f, salvos: f.base === "salvos" ? "1" : "",
        acharam: f.base === "acharam" ? "1" : "", pagina, por }));
    } catch (e) { lista.innerHTML = `<div class="vazio" style="grid-column:1/-1">${esc(porque(e))}</div>`; return; }
    const html = d.videos.map((v) => cartaoVideoGrande(v)).join("");
    if (mais && !travado) lista.insertAdjacentHTML("beforeend", html);
    else lista.innerHTML = html || '<div class="vazio" style="grid-column:1/-1">Nenhum vídeo com esses filtros. Afrouxe um, ou busque vídeos novos no YouTube.</div>';
    if (!mais || travado) naTela.clear();
    d.videos.forEach((v) => naTela.set(v.id, v));
    if (travado) {
      lista.querySelectorAll(".video.yt").forEach((c) => {
        c.draggable = true;
        c.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/plain", c.dataset.video));
        const acoes = c.querySelector(".video-acoes");
        if (acoes && !acoes.querySelector(".separar")) {
          acoes.insertAdjacentHTML("afterbegin", '<button class="botao sec separar" title="Põe na pilha de cima, para rever depois">⇥ Separar</button>');
          acoes.querySelector(".separar").onclick = () => separar(c.dataset.video);
        }
      });
      marcarSeparados();
    }
    const quantos = lista.querySelectorAll(".video.yt").length;
    // o que o filtro cortou não fica escondido: a tela diz quantos são e abre com um clique
    const fora = d.cortados && f.com_cortados !== "1"
      ? ` · <button class="link-cortados" id="ver-cortados">${d.cortados} escondidos pelas suas respostas</button>` : "";
    avisarPiso(tela, "views_min", d.views_min, f.views_min, (n) =>
      `O piso é ${num(n)}: pedir ${Number(f.nota_min)}x o normal do canal, com o normal medido em pelo menos `
      + `${num(Math.round(d.piso / (Number(f.nota_min) || 5)))} views, já exige isso. Para subir, arraste para a direita.`);
    const piso = d.views_min > (Number(f.views_min) || 0) ? ` · piso de ${num(d.views_min)} views` : "";
    paginas = Math.max(1, Math.ceil(d.total / por));
    const onde = travado && d.total ? ` · página ${pagina + 1} de ${num(paginas)}` : "";
    document.getElementById("contagem").innerHTML = d.total
      ? `${d.total.toLocaleString("pt-BR")} ${d.total === 1 ? "vídeo" : "vídeos"} · mostrando ${quantos}${onde}${piso}${fora}`
      : `${piso.replace(/^ · /, "")}${fora}`;
    document.getElementById("mais").hidden = travado || quantos >= d.total;
    if (travado) {
      document.getElementById("ant").disabled = pagina === 0;
      document.getElementById("prox").disabled = pagina + 1 >= paginas;
      document.getElementById("pag-onde").textContent = d.total
        ? `${pagina * por + 1}–${pagina * por + quantos} de ${d.total.toLocaleString("pt-BR")}` : "nada aqui";
    }
    const ver = document.getElementById("ver-cortados");
    if (ver) ver.onclick = () => { f.com_cortados = "1"; sincronizar(); acompanhar(); carregar(); };
    ligarRoteiro(lista);
  };

  const botaoTravar = document.getElementById("travar");
  const travar = (ligar) => {
    travado = ligar;
    caixaBusca.classList.toggle("recolhida", ligar);
    document.getElementById("puxar").hidden = !ligar;
    document.getElementById("paginador").hidden = !ligar;
    botaoTravar.textContent = ligar ? "✕ Soltar a tela" : "📌 Travar 10 na tela";
    botaoTravar.classList.toggle("vermelho", ligar);
    pintarSeparados();
    carregar().then(() => {
      if (ligar) document.getElementById("separados").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };
  botaoTravar.onclick = () => travar(!travado);
  document.getElementById("puxar").onclick = () => caixaBusca.classList.toggle("recolhida");
  const virar = (passo) => {
    const alvo = Math.min(Math.max(pagina + passo, 0), paginas - 1);
    if (alvo === pagina) return;
    pagina = alvo;
    carregar(false, true).then(() => document.getElementById("separados").scrollIntoView({ behavior: "smooth", block: "start" }));
  };
  document.getElementById("ant").onclick = () => virar(-1);
  document.getElementById("prox").onclick = () => virar(1);
  // as setas do teclado viram a página também; o ouvinte sai sozinho quando esta tela não está mais no ar
  const teclas = (e) => {
    const px = document.getElementById("paginador");
    if (!px || !tela.contains(px)) return document.removeEventListener("keydown", teclas);
    if (!travado || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    if (e.key === "ArrowRight") virar(1);
    if (e.key === "ArrowLeft") virar(-1);
  };
  document.addEventListener("keydown", teclas);

  let pintarSentido = () => {}, pintarMarcas = () => {}, pintarTrilhos = () => {};
  const sincronizar = () => { pintarSentido(); pintarMarcas(); pintarTrilhos(); };
  const acompanhar = ligarSelects(tela, f, PADRAO_VIDEOS, () => { sincronizar(); carregar(); }, ["busca"]);
  pintarSentido = ligarSentido(f, () => { acompanhar(); carregar(); });
  pintarMarcas = ligarMarcas(tela, f, () => { acompanhar(); carregar(); });
  pintarTrilhos = ligarTrilhos(tela, f, degrausDe, () => { acompanhar(); carregar(); });
  const ir = () => { f.busca = document.getElementById("busca").value.trim(); acompanhar(); carregar(); };
  document.getElementById("ir").onclick = ir;
  document.getElementById("busca").onkeydown = (e) => { if (e.key === "Enter") ir(); };
  document.getElementById("mais").onclick = () => carregar(true);
  document.getElementById("mais-youtube").onclick = (e) => carregando(e.currentTarget, "Procurando no YouTube…", async () => {
    const r = await api("/api/explorar/mais", { method: "POST" });
    aviso(`Procurei "${r.termo}" (${r.nicho}): ${r.novos} canais novos.`);
    esquecer("/api/filtros", "/api/visoes"); await carregar();
  });
  sincronizar();
  carregar();
}

// Acharam para você: os parecidos que cada canal salvo trouxe sozinho, numa tela só
async function acharam() {
  const { canais } = await api("/api/achados");
  tela.innerHTML = titulo("Acharam para você", "Cada canal que você salva procura sozinho os parecidos com ele. O que eles acharam chega aqui, já medido.") + `
    <div class="contagem">${canais.length ? `${canais.length} ${canais.length === 1 ? "canal chegou" : "canais chegaram"} a partir dos seus salvos` : ""}</div>
    <div class="lista-canais">${canais.map((c) => cartaoCanal(c, {
      rodape: `<div class="sub">veio de <b>${esc(c.por_causa_de || "um canal seu")}</b>${c.achado ? ` · ${ha(c.achado)}` : ""}</div>` })).join("")
      || `<div class="vazio">Ainda não chegou nenhum. Salve canais na aba <a href="#/base">Canais</a>: cada um procura os parecidos uma vez por semana.</div>`}</div>`;
  ligarCartoes();
}

const PADRAO_GRUPOS = { nicho: "", min: "" };

async function grupos() {
  const filtro = recorte(PADRAO_GRUPOS);
  const o = await opcoes();
  if (!o.nichos.some((n) => n.valor === filtro.nicho)) filtro.nicho = "";   // nicho do endereço que não está mais na lista
  const { grupos: lista } = await api("/api/grupos?" + consulta({ nicho: filtro.nicho }));
  const mostrar = lista.filter((g) => g.canais >= (+filtro.min || 1));
  tela.innerHTML = titulo("Grupos de canais" + botaoAleatorio(".grade-grupos"), "Canais que fazem o mesmo tipo de vídeo. Poucos canais e muita view: nicho aberto. Clique num grupo para ver os canais.") +
    `<div class="busca-caixa">${selects([["nicho", "Todos os nichos", o.nichos.map((n) => [n.valor, n.valor])], ["min", "Qualquer número de canais", [[2, "2 canais ou mais"], [3, "3 ou mais"], [5, "5 ou mais"]]]], filtro)}</div>` + `
    <div class="grade-grupos">${mostrar.map((g) => {
      const leitura = g.canais <= 2 ? "nicho aberto" : g.canais >= 8 ? "concorrido" : "em formação";
      return `<div class="grupo" data-sub="${esc(g.subnicho)}">
        <div class="mosaico">${g.capas.map((id) => `<img src="https://i.ytimg.com/vi/${esc(id)}/mqdefault.jpg" alt="" loading="lazy">`).join("")}</div>
        <div><h3>${esc(g.subnicho)}</h3><span class="sub">${esc(g.nicho)} · <b style="color:${g.canais <= 2 ? "var(--verde)" : g.canais >= 8 ? "var(--vermelho-claro)" : "var(--laranja)"}">${leitura}</b></span></div>
        <div class="numeros"><span><b>${g.canais}</b> canais</span><span class="media"><b>${num(g.mediana)}</b> por vídeo</span><span><b>${g.crescendo}</b> crescendo</span></div>
      </div>`; }).join("") || '<div class="vazio">Os grupos aparecem quando os canais ganham subnicho (no garimpo).</div>'}</div>`;
  ligarSelects(tela, filtro, PADRAO_GRUPOS, () => grupos());
  // o grupo abre o Procurar já com o subnicho escrito: a busca vai no endereço, não guardada por fora
  tela.querySelectorAll(".grupo").forEach((g) => (g.onclick = () => { location.hash = "#/base?busca=" + encodeURIComponent(g.dataset.sub); }));
}

// Os títulos recomendados: os que estouraram NOS NICHOS DOS CANAIS DA PESSOA (pedido do usuário em 2026-10-25).
// É a única recomendação que o Radar pode fazer sem inventar nada — ele não sabe o que vai funcionar amanhã, sabe
// o que já funcionou no mesmo assunto. Sem canal cadastrado (ou sem nicho neles) o bloco diz isso, em vez de
// mostrar uma lista qualquer fingindo que é para você.
async function recomendados(caixa) {
  if (!caixa) return;
  caixa.innerHTML = '<h3>⭐ Recomendados para os seus canais</h3><p class="sub">Procurando…</p>';
  let lista;
  try { ({ titulos: lista } = await api("/api/titulos?meus=1&nota_min=5")); }
  catch (e) { caixa.innerHTML = `<h3>⭐ Recomendados para os seus canais</h3><p class="sub">${esc(porque(e))}</p>`; return; }
  const nichos = [...new Set(lista.map((t) => t.nicho).filter(Boolean))];
  caixa.innerHTML = `<h3>⭐ Recomendados para os seus canais</h3>
    <p class="sub">${lista.length
      ? `Os títulos que mais estouraram ${nichos.length ? `em ${nichos.map(esc).join(", ")}` : "nos seus nichos"} — 5x o normal do canal ou mais. Não é previsão: é o que já deu certo no seu assunto.`
      : "Nenhum título ainda. Isto enche quando os seus canais (no Perfil) tiverem nicho e o Radar achar vídeos que estouraram nele."}</p>
    <div class="lista-titulos">${lista.slice(0, 12).map((t) => `<div class="titulo-linha">
      <span class="t"><b>${esc(t.titulo)}</b><small>${esc(t.canal)} · ${esc(t.nicho)} · ${num(t.views)} views</small></span>
      <span class="n">${nota(t.nota)}</span>
      <button class="botao sec" data-copiar="${esc(t.titulo)}">Copiar</button>
      <a class="botao sec" href="#/trabalho?ref=${esc(t.id)}&titulo=${encodeURIComponent(t.titulo)}">Levar ao Roteiro</a>
    </div>`).join("")}</div>`;
  caixa.querySelectorAll("[data-copiar]").forEach((b) => (b.onclick = async () => {
    await navigator.clipboard.writeText(b.dataset.copiar); b.textContent = "Copiado ✓";
  }));
}

// ---------------------------------------------------------------- Títulos
// Em cima o gerador: o tema e o nicho, e o Claude escreve no estilo dos títulos que estouraram naquele nicho
// (os exemplos saem do próprio Radar, nunca de fora). Embaixo o banco: os títulos de verdade que deram certo,
// com a nota de cada um, para copiar ou levar ao Roteiro.

const PADRAO_TITULOS = { nicho: "", nota_min: "3", publicado_dias: "", busca: "" };
const LINGUAS_TITULO = ["português", "inglês", "espanhol"];

async function titulos() {
  const filtro = recorte(PADRAO_TITULOS);
  const o = await opcoes();
  if (filtro.nicho && !o.nichos.some((n) => n.valor === filtro.nicho)) filtro.nicho = "";
  tela.innerHTML = titulo("Títulos", "O gerador escreve no estilo dos que estouraram. Embaixo, o banco de títulos que deram certo.") + `
    <div class="gerador tit-gerador">
      <div class="linha"><input id="tit-tema" placeholder="O tema do vídeo (ex.: naufrágios que ninguém explicou)" maxlength="300"></div>
      <div class="linha">
        <select id="tit-nicho"><option value="">Estilo de todos os nichos</option>${o.nichos.map((n) => `<option value="${esc(n.valor)}" ${filtro.nicho === n.valor ? "selected" : ""}>${esc(n.valor)}</option>`).join("")}</select>
        <select id="tit-lingua">${LINGUAS_TITULO.map((l) => `<option value="${l}">${l[0].toUpperCase() + l.slice(1)}</option>`).join("")}</select>
        <select id="tit-quantos">${[5, 10, 15].map((q) => `<option value="${q}" ${q === 10 ? "selected" : ""}>${q} títulos</option>`).join("")}</select>
        <button class="botao" id="tit-gerar">Gerar títulos</button>
      </div>
      <p class="sub">Grátis: usa o Groq, não gasta cota do YouTube.</p>
      <div id="tit-saida"></div>
    </div>
    <section id="tit-recomendados" class="cp-bloco"></section>
    <h2 style="margin-top:26px">Banco de títulos que estouraram</h2>
    <div class="busca-caixa">${selects([["nicho", "Todos os nichos", o.nichos.map((n) => [n.valor, n.valor])],
      ["nota_min", "", [["3", "3x o normal ou mais"], ["5", "5x ou mais"], ["10", "10x ou mais"]]],
      ["publicado_dias", "De qualquer data", [["7", "Da última semana"], ["30", "Do último mês"], ["365", "Do último ano"]]]], filtro)}
    <div class="procura"><input id="tit-busca" placeholder="Procurar no título" value="${esc(filtro.busca)}"></div></div>
    <div id="tit-banco" class="lista-titulos"><div class="vazio">Carregando…</div></div>`;

  const banco = async () => {
    const alvo = document.getElementById("tit-banco");
    try {
      const { titulos: lista } = await api("/api/titulos?" + consulta({ nicho: filtro.nicho, nota_min: filtro.nota_min,
        publicado_dias: filtro.publicado_dias, busca: filtro.busca }));
      alvo.innerHTML = lista.map((t) => `<div class="titulo-linha">
        <span class="t"><b>${esc(t.titulo)}</b><small>${esc(t.canal)} · ${num(t.views)} views · ${esc((t.publicado || "").slice(0, 10))}</small></span>
        <span class="n">${nota(t.nota)}</span>
        <button class="botao sec" data-copiar="${esc(t.titulo)}">Copiar</button>
        <a class="botao sec" href="#/trabalho?ref=${esc(t.id)}&titulo=${encodeURIComponent(t.titulo)}">Levar ao Roteiro</a>
      </div>`).join("") || '<div class="vazio">Nenhum título com esses filtros. Baixe a nota ou tire a data.</div>';
      alvo.querySelectorAll("[data-copiar]").forEach((b) => (b.onclick = async () => { await navigator.clipboard.writeText(b.dataset.copiar); b.textContent = "Copiado ✓"; }));
    } catch (e) { alvo.innerHTML = `<div class="vazio">${esc(porque(e))}</div>`; }
  };
  recomendados(document.getElementById("tit-recomendados"));
  ligarSelects(tela, filtro, PADRAO_TITULOS, banco, ["busca"]);
  let espera;
  document.getElementById("tit-busca").oninput = (e) => {
    filtro.busca = e.target.value.trim();
    clearTimeout(espera); espera = setTimeout(() => { recorteParaOEndereco(filtro, PADRAO_TITULOS); banco(); }, 350);
  };
  document.getElementById("tit-gerar").onclick = (e) => carregando(e.currentTarget, "Escrevendo…", async () => {
    const tema = document.getElementById("tit-tema").value.trim();
    if (!tema) return aviso("Escreva o tema do vídeo.");
    const saida = document.getElementById("tit-saida");
    const d = await api("/api/titulos/gerar", { method: "POST", body: { tema,
      nicho: document.getElementById("tit-nicho").value, lingua: document.getElementById("tit-lingua").value,
      quantos: +document.getElementById("tit-quantos").value } });
    saida.innerHTML = `<p class="sub">No estilo de ${d.exemplos} títulos que estouraram${document.getElementById("tit-nicho").value ? " neste nicho" : ""}.</p>
      <div class="lista-titulos">${d.titulos.map((t) => `<div class="titulo-linha"><span class="t"><b>${esc(t)}</b></span>
        <button class="botao sec" data-copiar="${esc(t)}">Copiar</button>
        <button class="botao sec" data-roteiro="${esc(t)}">Levar ao Roteiro</button></div>`).join("")}</div>`;
    saida.querySelectorAll("[data-copiar]").forEach((b) => (b.onclick = async () => { await navigator.clipboard.writeText(b.dataset.copiar); b.textContent = "Copiado ✓"; }));
    // o Roteiro lê este preset ao abrir: o título gerado não tem vídeo de referência, só o texto
    saida.querySelectorAll("[data-roteiro]").forEach((b) => (b.onclick = () => { guardar("roteiro-preset", { titulo: b.dataset.roteiro }); location.hash = "#/trabalho"; }));
  });
  banco();
}

// ---------------------------------------------------------------- Ferramentas

function medir() {
  tela.innerHTML = titulo("Medir canal", "Cole o @ de qualquer canal, o link dele ou o link de um vídeo.") + `
    <div class="procura"><input id="ref" placeholder="@canal ou link"><button class="botao" id="ir">Medir</button></div>
    <div id="resultado" class="lista-canais" style="margin-top:14px"></div>`;
  const ir = () => {
    const ref = document.getElementById("ref").value.trim();
    if (!ref) return;
    carregando(document.getElementById("ir"), "Medindo…", async () => {
      const { canal: c } = await api("/api/medir", { method: "POST", body: { ref } });
      const res = document.getElementById("resultado");
      res.innerHTML = cartaoCanal(c, { rodape: c.no_radar ? '<span class="sub">Já está no Radar.</span>' : `<div><button class="botao" id="por" data-id="${esc(c.id)}">Pôr no Radar</button></div>` });
      ligarCartoes(res);
      const b = document.getElementById("por");
      if (b) b.onclick = () => carregando(b, "Classificando…", async () => { await api(`/api/radar/adicionar/${b.dataset.id}`, { method: "POST" }); b.replaceWith("No Radar ✓"); esquecer("/api/filtros", "/api/visoes"); });
    });
  };
  document.getElementById("ir").onclick = ir;
  document.getElementById("ref").onkeydown = (e) => { if (e.key === "Enter") ir(); };
}

// ---------------------------------------------------------------- depoimentos, na Administração
// O print vai como data URL (o servidor confere tipo e tamanho e guarda em dados/depoimentos). Esconder tira da
// vitrine sem apagar nada; apagar leva o print junto.

async function montarDepoimentos() {
  const form = document.getElementById("dep-form");
  if (!form) return;
  form.innerHTML = `<div class="dep-campos">
      <input id="dep-nome" placeholder="Nome de quem está falando" maxlength="80">
      <input id="dep-canal" placeholder="O canal dele (opcional)" maxlength="80">
      <input id="dep-resultado" placeholder="O resultado em uma linha (ex.: 105 mil views em 48 horas)" maxlength="120">
      <textarea id="dep-texto" rows="3" placeholder="O que a pessoa escreveu, do jeito que escreveu" maxlength="1200"></textarea>
      <label class="dep-print">Print do YouTube Studio (JPEG, PNG ou WebP, até 4 MB)<input id="dep-print" type="file" accept="image/jpeg,image/png,image/webp"></label>
      <button class="botao" id="dep-salvar">Guardar depoimento</button></div>`;
  document.getElementById("dep-salvar").onclick = (e) => carregando(e.currentTarget, "Guardando…", async () => {
    const nome = document.getElementById("dep-nome").value.trim();
    if (!nome) return aviso("Diga o nome de quem está falando.");
    const arquivo = document.getElementById("dep-print").files[0];
    const corpo = {
      nome, canal: document.getElementById("dep-canal").value.trim(),
      resultado: document.getElementById("dep-resultado").value.trim(),
      texto: document.getElementById("dep-texto").value.trim(),
      print: arquivo ? await new Promise((ok, erro) => {
        const leitor = new FileReader();
        leitor.onload = () => ok(leitor.result);
        leitor.onerror = () => erro(new Error("Não consegui ler a imagem."));
        leitor.readAsDataURL(arquivo);
      }) : "",
    };
    await api("/api/admin/depoimentos", { method: "POST", body: corpo });
    aviso("Guardado. Já aparece na tela de entrar.");
    montarDepoimentos();
  });
  const { depoimentos: lista } = await api("/api/admin/depoimentos");
  const caixa = document.getElementById("dep-lista");
  caixa.innerHTML = lista.length ? `<table class="tabela"><tr><th>Quem</th><th>Resultado</th><th>Print</th><th></th></tr>
    ${lista.map((d) => `<tr class="${d.mostrar ? "" : "escondido"}">
      <td>${esc(d.nome)}${d.canal ? `<br><span class="sub">${esc(d.canal)}</span>` : ""}</td>
      <td>${esc(d.resultado || "—")}</td>
      <td>${d.print ? `<a href="${esc(d.print)}" target="_blank" rel="noopener">ver</a>` : "—"}</td>
      <td><a href="#" class="dep-mostrar" data-id="${d.id}" data-mostrar="${d.mostrar ? "0" : "1"}">${d.mostrar ? "esconder" : "mostrar"}</a>
        · <a href="#" class="dep-apagar" data-id="${d.id}" style="color:var(--vermelho-claro)">apagar</a></td></tr>`).join("")}</table>`
    : '<p class="sub">Nenhum depoimento ainda. Enquanto não houver, a vitrine não mostra essa parte.</p>';
  caixa.querySelectorAll(".dep-mostrar").forEach((a) => (a.onclick = async (e) => {
    e.preventDefault();
    await api(`/api/admin/depoimentos/${a.dataset.id}`, { method: "POST", body: { mostrar: a.dataset.mostrar === "1" } });
    montarDepoimentos();
  }));
  caixa.querySelectorAll(".dep-apagar").forEach((a) => (a.onclick = async (e) => {
    e.preventDefault();
    await api(`/api/admin/depoimentos/${a.dataset.id}`, { method: "DELETE" });
    montarDepoimentos();
  }));
}

// ---------------------------------------------------------------- os planos: o preço, depois do cadastro
// O que cada plano abre sai do próprio servidor (config.PLANOS), então a tela não tem lista escrita à mão para
// desencontrar da regra que de fato libera as coisas.
const O_QUE_ABRE = {
  extensao: "A extensão do Chrome, com os números em cima de cada vídeo",
  salvar: "Salvar canais na sua base e organizar em pastas",
  parecidos: "Canais parecidos, e os que os seus salvos acharam",
  linguas: "Em que língua ninguém fez o vídeo ainda",
  achados: "A aba Acharam para você",
  radar: "O painel: a lista de canais, as visões e os filtros",
  ranking: "A ordem Na hora de copiar",
  outliers: "A lista de vídeos que estouraram",
};

async function telaPlanos() {
  // a contagem de funções é um extra: se ela falhar, a tela de planos (que é por onde se assina) continua de pé
  const [{ planos, meu }, ext] = await Promise.all([api("/api/planos"), api("/api/ext/funcoes").catch(() => null)]);
  const ordem = Object.keys(planos);
  const quantas = (k) => !ext ? null : ext.funcoes.filter((f) => ordem.indexOf(f.plano) <= ordem.indexOf(k)).length;
  const chaves = Object.keys(planos);
  tela.innerHTML = titulo("Planos", "O que cada plano abre no Radar.") + `
    <div class="planos">${chaves.map((k) => {
      const p = planos[k], antes = chaves[chaves.indexOf(k) - 1];
      const novos = p.recursos.filter((r) => !antes || !planos[antes].recursos.includes(r));
      return `<article class="plano ${k === meu ? "meu" : ""}">
        <h3>${esc(p.nome)}</h3>
        <div class="preco">${p.preco ? `R$ ${num(p.preco)}<small>/mês</small>` : "grátis"}</div>
        ${k === meu ? '<span class="tag">o seu plano</span>' : ""}
        <ul>${novos.map((r) => `<li>${esc(O_QUE_ABRE[r] || r)}</li>`).join("")}</ul>
        ${ext ? `<p class="linha-sub" style="margin-bottom:0">${quantas(k)} das ${ext.contagem.total} funções da extensão.</p>` : ""}
        ${antes ? `<p class="linha-sub">Tudo do ${esc(planos[antes].nome)}, e mais.</p>` : ""}
      </article>`;
    }).join("")}</div>`;
}

// A lista de funcoes vem do servidor (radar/funcoes.py), numa fonte so: a tela de ajuda, a tela de planos e a
// propria extensao leem daqui. Antes eram tres listas escritas a mao, e quem mexia numa esquecia as outras.
async function extensao() {
  const { funcoes, onde, contagem } = await api("/api/ext/funcoes");
  const grupos = Object.keys(onde).filter((g) => funcoes.some((f) => f.onde === g));
  const cartao = (f) => `
    <article class="plano${f.liberada === false ? " trancada" : ""}">
      <h3>${esc(f.nome)}${f.plano === "gratis" ? "" : ` <span class="tag">${esc(f.plano_nome)}</span>`}</h3>
      <p class="sub">${esc(f.desc)}</p>
      ${f.atalho ? `<p class="linha-sub" style="margin-bottom:0">Atalho: <b>${esc(f.atalho)}</b></p>` : ""}
    </article>`;
  tela.innerHTML = titulo("Extensão do Chrome",
    `${contagem.total} funções dentro do YouTube, ${contagem.gratis} delas no plano Grátis. Enquanto você navega, a extensão lê os vídeos da tela — sem gastar a cota — e guarda no Radar os que estouraram.`) + `
    <div class="cartao"><p style="margin-top:0"><a class="botao" href="/api/extensao.zip">Baixar a extensão</a></p>
    <ol style="margin:0;padding-left:20px;display:grid;gap:8px">
    <li>Descompacte o zip numa pasta que não vai apagar (Documentos).</li>
    <li>Abra <b>chrome://extensions</b> e ligue o <b>Modo do desenvolvedor</b>.</li>
    <li>Clique em <b>Carregar sem compactação</b> e escolha a pasta <b>radar-extensao</b>.</li>
    <li>Já tem a extensão? Em <b>chrome://extensions</b>, clique no ↻ dela para carregar a versão nova.</li></ol></div>
    ${grupos.map((g) => `<h3 style="margin:22px 0 0">${esc(onde[g])}</h3>
      <div class="planos">${funcoes.filter((f) => f.onde === g).map(cartao).join("")}</div>`).join("")}`;
}

async function admin() {
  if (!EU.admin) return (tela.innerHTML = '<div class="vazio">Só a administração.</div>');
  const [{ usuarios }, { cota, garimpos, motivos }, { convites }] = await Promise.all([api("/api/admin/usuarios"), api("/api/admin/cota"), api("/api/admin/convites")]);
  tela.innerHTML = titulo("Administração", "") + `
    <div class="cartao"><h3 style="margin-top:0">Garimpo</h3>
      <p class="sub">Cota do YouTube hoje: ${num(cota.usado)} de ${num(cota.total)} usadas. Volta às 5 h. O garimpo roda sozinho uma vez por dia.</p>
      ${ondeFoiACota({ motivos })}
      <div class="selects"><select id="unidades"><option value="">Usar 60% do que sobrou</option><option value="1000">Pouco (1.000)</option><option value="3000">Médio (3.000)</option><option value="6000">Muito (6.000)</option></select>
        <button class="botao" id="garimpar">Garimpar agora</button></div>
      <table class="tabela"><tr><th>Começo</th><th>Estado</th><th>Buscas</th><th>Canais novos</th><th>Unidades</th><th></th></tr>
      ${garimpos.map((g) => `<tr><td>${new Date(g.inicio).toLocaleString("pt-BR")}</td><td>${esc(g.estado)}</td><td>${g.buscas}</td><td>${g.canais_novos}</td><td>${g.unidades}</td>
        <td><a href="#" data-g="${g.id}" class="ver" style="color:var(--verde)">ver</a></td></tr>`).join("")}</table><pre class="log" id="log" hidden></pre></div>
    <div class="cartao" style="margin-top:16px"><h3 style="margin-top:0">Convites e contas</h3>
      <div class="selects"><button class="botao" id="convidar">Gerar link de convite</button></div><div id="link-convite"></div>
      <table class="tabela"><tr><th>Conta</th><th>Criada</th><th></th></tr>
      ${usuarios.map((u) => `<tr><td>${esc(u.email)}${u.admin ? " (você)" : ""}</td><td>${new Date(u.criado).toLocaleDateString("pt-BR")}</td>
        <td>${u.admin ? "" : `<a href="#" class="tirar" data-id="${u.id}" data-email="${esc(u.email)}" style="color:var(--vermelho-claro)">tirar acesso</a>`}</td></tr>`).join("")}
      ${convites.filter((c) => !c.usado_por).map((c) => `<tr><td class="sub">convite esperando</td><td>${new Date(c.criado).toLocaleString("pt-BR")}</td>
        <td><a href="#" class="cancelar" data-id="${esc(c.id)}" style="color:var(--vermelho-claro)">cancelar</a></td></tr>`).join("")}</table></div>
    <div class="cartao" style="margin-top:16px" id="dep-cartao"><h3 style="margin-top:0">Depoimentos da vitrine</h3>
      <p class="sub">Quem usou o Radar, com o print do YouTube Studio. Aparecem na tela de entrar, para quem ainda
        não tem conta. O Radar não escreve nenhum: entram aqui, um a um, com o que a pessoa de fato mandou.</p>
      <div id="dep-form"></div><div id="dep-lista"></div></div>`;
  montarDepoimentos();
  document.getElementById("garimpar").onclick = async () => {
    const unidades = document.getElementById("unidades").value;
    await api("/api/admin/garimpar", { method: "POST", body: unidades ? { unidades: +unidades } : {} });
    aviso("Garimpo começou. Atualize em alguns minutos."); setTimeout(admin, 3000);
  };
  document.getElementById("convidar").onclick = async () => {
    const r = await api("/api/admin/convites", { method: "POST", body: {} });
    document.getElementById("link-convite").innerHTML = `<code class="comando">${esc(r.link)}</code><button class="botao sec" id="copiar-link" style="margin:8px 0">Copiar o link</button>`;
    document.getElementById("copiar-link").onclick = (e) => { navigator.clipboard.writeText(r.link); e.target.textContent = "Copiado ✓"; };
  };
  tela.querySelectorAll(".ver").forEach((a) => (a.onclick = async (e) => {
    e.preventDefault(); const g = await api(`/api/admin/garimpos/${a.dataset.g}`);
    const log = document.getElementById("log"); log.hidden = false; log.textContent = g.linhas.join("\n");
  }));
  tela.querySelectorAll(".cancelar").forEach((a) => (a.onclick = async (e) => { e.preventDefault(); await api(`/api/admin/convites/${a.dataset.id}`, { method: "DELETE" }); admin(); }));
  tela.querySelectorAll(".tirar").forEach((a) => (a.onclick = async (e) => {
    e.preventDefault();
    if (!confirm(`Tirar o acesso de ${a.dataset.email}?`)) return;
    await api(`/api/admin/usuarios/${a.dataset.id}`, { method: "DELETE" }); admin();
  }));
}

// ---------------------------------------------------------------- o quadro dos créditos no menu, com o "Gastar tudo agora"
// (pedido do usuário: antes de desligar o PC, gastar o que sobrou da cota no garimpo)

let relogioCota = null;
async function quadroCota() {
  const caixa = document.getElementById("quadro-cota");
  if (!caixa || !EU) return;
  clearTimeout(relogioCota);
  let c;
  try { c = await api("/api/cota"); } catch { return; }
  const pct = c.total ? Math.min(100, Math.round(c.usado / c.total * 100)) : 0;
  const botao = !EU.admin ? "" : c.garimpando
    ? `<button class="botao" disabled>Garimpando…${c.orcamento ? ` ${num(c.gasto)} de ${num(c.orcamento)}` : ""}</button>`
    : `<button class="botao" id="gastar-tudo" ${c.livre < 110 ? "disabled" : ""} data-dica="Usa toda a cota do YouTube que sobrou hoje para achar canais novos e vídeos que estouraram. Bom de apertar antes de desligar o PC: a cota volta às 5 h e o que não for usado se perde.">⚡ Gastar tudo agora</button>`;
  // o garimpo automático roda 23 h depois do último, se o Radar estiver ligado
  const proximo = c.ultimo_garimpo ? new Date(Date.parse(c.ultimo_garimpo) + 23 * 36e5) : null;
  const quando = !proximo || proximo < new Date() ? "na próxima hora"
    : (proximo.toDateString() === new Date().toDateString() ? "hoje" : "amanhã") + ` às ${proximo.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
  caixa.innerHTML = `<div class="quadro-cota"><b>Créditos do YouTube</b>
    <div class="barra-cota"><i style="width:${pct}%"></i></div>
    <span class="sub"><b>${num(c.livre)}</b> livres de ${num(c.total)}</span>
    <span class="sub auto-garimpo" data-dica="Todo dia, sozinho, o Radar procura canais novos e mede de novo os seus com 60% da cota livre. Só roda com o Radar ligado: com o PC desligado ele não roda e não recupera o dia. O próximo é 23 h depois do último. A cota volta às 5 h e o que sobrar se perde; por isso o Gastar tudo antes de desligar.">🕑 Garimpo automático: ${c.garimpando ? "rodando agora" : quando} <u>?</u></span>${botao}</div>`;
  const b = document.getElementById("gastar-tudo");
  if (b) b.onclick = () => janelaGastar(c);
  relogioCota = setTimeout(quadroCota, c.garimpando ? 5000 : 60000);
}

// a janela no meio da tela para ter certeza antes de gastar a cota
function janelaGastar(c) {
  const fundo = document.createElement("div");
  fundo.className = "modal-fundo";
  fundo.innerHTML = `<div class="modal janela-gastar"><h2>⚡ Gastar toda a cota de hoje?</h2>
    <p>O Radar vai usar os <b>${c.livre.toLocaleString("pt-BR")} créditos livres</b> do YouTube de hoje, de uma vez, para:</p>
    <ul><li><b>Procurar canais novos</b> nos seus nichos (cada busca gasta 100). Os que estão indo bem entram no Radar e no Alerta.</li>
      <li><b>Medir de novo</b> os canais do Radar e os salvos: views, vídeos novos e quem está em alta.</li>
      <li>Guardar os <b>vídeos que estouraram</b> (3x o normal ou mais) no Vídeos que estouraram.</li></ul>
    <p class="sub">Leva de 10 a 30 minutos. <b>Deixe o Radar ligado até terminar</b>; pode fechar esta tela. Depois disso,
      <b>Procurar no YouTube</b> e <b>Procurar mais</b> não funcionam até a cota voltar, às 5 h (Brasília). A cota é grátis: não tem cobrança.</p>
    <div class="linha"><button class="botao" id="gastar-sim">Sim, gastar tudo</button><button class="botao contorno" id="gastar-nao">Cancelar</button></div></div>`;
  document.body.appendChild(fundo);
  const fechar = () => fundo.remove();
  fundo.onclick = (e) => { if (e.target === fundo) fechar(); };
  fundo.querySelector("#gastar-nao").onclick = fechar;
  fundo.querySelector("#gastar-sim").onclick = async () => {
    const r = await api("/api/cota/gastar", { method: "POST" });
    fechar();
    aviso(r.ok ? "Garimpo começou com toda a cota livre. Pode fechar a tela; deixe o Radar ligado." : r.motivo);
    quadroCota();
  };
}

// ---------------------------------------------------------------- Descobrir: o painel com os créditos do YouTube

// quanto cada ação da página gasta da cota (busca na API = 100; medir canal ≈ 3; ver 50 vídeos = 1)
// O painel de cota que ficava à direita saiu (pedido do usuário em 2026-10-25): ele repetia o quadro da barra
// lateral e comia 290px da largura em todas as telas do Niche Finder. Quanto custa cada coisa continua na
// Administração, em "Onde foi hoje".
// em que a cota de hoje foi gasta: o servidor conta cada pedido ao YouTube no motivo de quem pediu
function ondeFoiACota(c) {
  const lista = (c.motivos || []).filter((m) => m.unidades > 0);
  if (!lista.length) return '<p class="sub">Nenhuma busca no YouTube hoje ainda.</p>';
  return `<h3 style="margin-top:14px">Onde foi hoje</h3><div class="gastos">${lista.map((m) =>
    `<div><span>${esc(m.rotulo)}</span><b>${num(m.unidades)}</b></div>`).join("")}</div>
    <p class="sub">${lista.reduce((s, m) => s + m.chamadas, 0)} pedidos ao YouTube hoje.</p>`;
}


// ---------------------------------------------------------------- rotas

// os endereços antigos de Descobrir levam para a lista nova, já com o filtro que fazia aquela tela: ninguém
// perde um link guardado, e cada tela velha vira uma linha de filtro em vez de uma tela.
const VELHAS = {
  alerta: "#/base?visao=views_poucos_subs", procurar: "#/base", alta: "#/base?ordem=alta", ranking: "#/base?ordem=pontos",
  salvos: "#/base?base=salvos", achados: "#/acharam",
  ideias: "#/videos", explorar: "#/videos?ordem=aleatorio", novidades: "#/videos?base=salvos&publicado_dias=7&nota_min=3",
};
const ROTAS = { entrar: () => entrar(false), criar: () => entrar(true), inicio, canais, perfil: canais, canal,
  "ideias-canal": ideiasCanal, treino, trabalho, acompanhar, resultados, titulo: () => { location.hash = "#/trabalho"; }, thumbnail: () => { location.hash = "#/trabalho"; },
  base: baseCanais, videos: videosLista, acharam, grupos, titulos, medir, extensao, bloqueados, admin, integracoes, custos,
  entraram: () => { location.hash = "#/base?visao=entraram_hoje"; },
  planos: telaPlanos,
  ...Object.fromEntries(Object.entries(VELHAS).map(([de, para]) => [de, () => { location.hash = para; }])) };

// os filtros que ficavam guardados no navegador agora moram no endereço: apaga o que sobrou de antes, uma vez,
// senão quem já usou o Radar continua com um filtro velho em algum canto sem nada na tela para desfazer
const RECORTES_ANTIGOS = ["alerta", "explorar", "procura", "ideias", "ideias-canal", "filtro-grupos",
  "nicho-ranking", "dias-novidades", "custos-dias", "resultados-canal"];
try { RECORTES_ANTIGOS.forEach((k) => localStorage.removeItem("radar:" + k)); } catch {}

async function rota() {
  const [nome, param, extra] = location.hash.replace(/^#\/?/, "").split("?")[0].split("/");
  if (!EU && !["entrar", "criar"].includes(nome)) { location.hash = "#/entrar"; return; }
  if (EU && (!ROTAS[nome] || nome === "entrar" || nome === "criar")) { location.hash = "#/inicio"; return; }
  menu(nome);
  document.body.dataset.tela = nome;   // o CSS precisa saber a tela: só o Roteiro usa a janela inteira
  tela.innerHTML = '<div class="vazio">Carregando…</div>';
  window.scrollTo(0, 0);
  painel();
  try { await ROTAS[nome](param, extra); }
  catch (e) { tela.innerHTML = `<div class="vazio">${esc(porque(e))}</div>`; }
}

// ---------------------------------------------------------------- cores do app: a identidade visual de cada pessoa
// As cores de destaque da Apple, uma cor livre e o modo claro ou escuro, guardados no navegador.
const CORES = [["#0071e3", "Azul"], ["#5e5ce6", "Índigo"], ["#bf5af2", "Roxo"], ["#ff375f", "Rosa"], ["#ff3b30", "Vermelho"],
  ["#ff9f0a", "Laranja"], ["#34c759", "Verde"], ["#30b0c7", "Verde-água"], ["#1d1d1f", "Grafite"], ["#a2845e", "Marrom"]];

// a identidade do app (pedido do usuário em 2026-10-15, pela imagem da versão escura): tema escuro e o marrom-dourado
const IDENTIDADE = { cor: "#a2845e", cor2: "#a2845e", tema: "escuro" };
try {
  if (!localStorage.getItem("radar:identidade-2")) {
    for (const [k, v] of Object.entries(IDENTIDADE)) guardar(k, v);
    localStorage.setItem("radar:identidade-2", "1");
  }
} catch {}

function aplicarCores() {
  const raiz = document.documentElement;
  raiz.style.setProperty("--acento", guardado("cor", IDENTIDADE.cor));
  raiz.style.setProperty("--acento2", guardado("cor", IDENTIDADE.cor));   // sem cor secundária: a mesma cor em tudo
  raiz.dataset.tema = guardado("tema", IDENTIDADE.tema);
}

// duas cores (a principal e a secundária) e três aparências: claro, cinza e escuro
function seletorCores() {
  const grupo = (chave, titulo) => `<b>${titulo}</b><div class="bolinhas" data-chave="${chave}"></div>
      <label>Outra cor <input type="color" data-chave="${chave}"></label>`;
  document.body.insertAdjacentHTML("beforeend", `<div id="cores"><button id="bt-ideias" class="bt-topo" title="As ideias salvas e os vídeos mandados fazer">💡 Ideias e vídeos</button>
    <button id="bt-chatgpt" class="bt-topo" title="Abre o ChatGPT numa janela no lado direito da tela">💬 ChatGPT</button>
    <button id="bt-nova" class="bt-topo bt-nova" title="Nova produção (Alt+N)" hidden>+ Nova produção</button>
    <button id="bt-cores" title="Cores do app"><i></i><i class="seg"></i>Cores</button>
    <div class="caixa-cores" hidden>${grupo("cor", "Cor do app")}
      <b>Aparência</b><div class="temas"><button data-tema="claro">☀️ Claro</button><button data-tema="cinza">🌫 Cinza</button><button data-tema="escuro">🌙 Escuro</button><button data-tema="pb">◐ Preto e branco</button></div></div></div>`);
  const caixa = document.querySelector("#cores .caixa-cores");
  const PADRAO = { cor: IDENTIDADE.cor, cor2: IDENTIDADE.cor2 };
  const marcar = () => {
    for (const chave of ["cor"]) {
      const atual = guardado(chave, PADRAO[chave]);
      caixa.querySelectorAll(`.bolinhas[data-chave="${chave}"] button`).forEach((b) => b.classList.toggle("escolhida", b.dataset.cor === atual));
      caixa.querySelector(`input[data-chave="${chave}"]`).value = atual;
    }
    caixa.querySelectorAll(".temas button").forEach((b) => b.classList.toggle("escolhido", b.dataset.tema === guardado("tema", IDENTIDADE.tema)));
  };
  caixa.querySelectorAll(".bolinhas").forEach((g) => {
    g.innerHTML = CORES.map(([cor, nome]) => `<button data-cor="${cor}" title="${nome}" style="background:${cor}"></button>`).join("");
    g.querySelectorAll("button").forEach((b) => (b.onclick = () => { guardar(g.dataset.chave, b.dataset.cor); aplicarCores(); marcar(); }));
  });
  caixa.querySelectorAll("input[type=color]").forEach((i) => (i.oninput = () => { guardar(i.dataset.chave, i.value); aplicarCores(); marcar(); }));
  caixa.querySelectorAll(".temas button").forEach((b) => (b.onclick = () => { guardar("tema", b.dataset.tema); aplicarCores(); marcar(); }));
  document.getElementById("bt-cores").onclick = (e) => { e.stopPropagation(); caixa.hidden = !caixa.hidden; marcar(); };
  document.getElementById("bt-chatgpt").onclick = () => abrirLateral("https://chatgpt.com/");
  document.getElementById("bt-ideias").onclick = () => { const c = document.getElementById("painel-ideias"); painel(c ? c.hidden : true); };
  document.getElementById("bt-nova").onclick = () => novaProducao();
  // Alt+N abre a Nova produção (o Ctrl+N o Chrome guarda para abrir janela nova)
  document.addEventListener("keydown", (e) => { if (e.altKey && e.key.toLowerCase() === "n" && EU?.admin) { e.preventDefault(); novaProducao(); } });
  document.addEventListener("click", (e) => { if (!e.target.closest("#cores")) caixa.hidden = true; });
}
aplicarCores();

(async () => {
  seletorCores();
  await abrirPacote();   // uma chamada só: daqui saem o resumo, a conta, as preferências, o menu, os alvos e as listas
  const p = await api("/api/resumo").catch(() => ({}));
  NOME = p.nome || NOME; NUMEROS = p;
  document.getElementById("nome-produto").textContent = NOME; document.title = NOME;
  document.querySelector(".marca").setAttribute("href", "#/inicio");
  EU = await api("/api/eu").catch(() => null);
  if (EU) {
    const [p, painel] = await Promise.all([api("/api/prefs"), api("/api/painel").catch(() => null)]);
    PREFS = p.prefs;
    if (painel) PAINEL = painel;
    await carregarAlvos();
  }
  document.getElementById("bt-nova").hidden = !EU?.admin;
  window.onhashchange = rota; rota();
  if (EU) { painel(guardado("painel-aberto", false) ? true : undefined); rodarVigia(); vigiarFila(); setInterval(vigiarFila, 30000); }
})();
