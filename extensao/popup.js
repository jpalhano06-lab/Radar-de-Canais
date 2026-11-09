const PADRAO = "http://127.0.0.1:8400";
const $ = (id) => document.getElementById(id);
// a extensão pede estas permissões ela mesma: no chrome://extensions as chaves podem ficar travadas
const ORIGENS = ["http://127.0.0.1/*", "http://localhost/*", "https://www.youtube.com/*"];

const endereco = async () => ((await chrome.storage.local.get("servidor")).servidor || PADRAO).replace(/\/+$/, "");

function mostrarSo(id) {
  for (const x of ["permissao", "desligado", "dentro", "entrar"]) $(x).hidden = x !== id;
}

let reconferir = 0;

async function mostrar() {
  clearTimeout(reconferir);
  $("erro").textContent = "";
  const servidor = await endereco();
  $("servidor").value = servidor;
  let permitido = true;
  try { permitido = await chrome.permissions.contains({ origins: ORIGENS }); } catch (e) { $("erro").textContent = "Permissão: " + e.message; }
  if (!permitido) return mostrarSo("permissao");
  const { token, eu } = await chrome.storage.local.get(["token", "eu"]);
  let resposta = null;
  try {
    const r = await fetch(servidor + "/api/eu", { headers: token ? { Authorization: `Bearer ${token}` } : {}, signal: AbortSignal.timeout(6000) });
    resposta = r.ok ? await r.json() : { precisaEntrar: r.status === 401 };
  } catch {
    // o Radar pode estar subindo: a janelinha olha de novo sozinha, em vez de a pessoa ter de fechar e abrir
    mostrarSo("desligado");
    clearTimeout(reconferir);
    reconferir = setTimeout(() => mostrar().catch(() => {}), 3000);
    return;
  }
  if (resposta.precisaEntrar) return mostrarSo("entrar");
  mostrarSo("dentro");
  $("quem").textContent = resposta.livre ? "Acesso livre neste computador" : `${(eu || resposta).email}`;
  $("sair").hidden = !!resposta.livre;
  carregarCanais(servidor, token);
  carregarHoje(servidor, token);
  carregarProgresso(servidor, token);
  carregarFuncoes(servidor, token);
}

// `ler` fica de fora: sem ele não há nota nenhuma para mostrar. As do Studio não passam pelo content.js.
const SEM_INTERRUPTOR = new Set(["ler", "publicar", "sem-shorts", "treino", "capa-2mb", "horario-postar", "escrever-publicacao",
  "numeros-meu-canal", "foto-studio"]);

async function carregarFuncoes(servidor, token) {
  const caixa = $("funcoes");
  try {
    const r = await fetch(servidor + "/api/ext/funcoes", { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    const { funcoes, onde } = await r.json();
    const { funcoesDesligadas } = await chrome.storage.local.get("funcoesDesligadas");
    const desligadas = new Set(funcoesDesligadas || []);
    caixa.replaceChildren();
    for (const [chave, titulo] of Object.entries(onde)) {
      const grupo = funcoes.filter((f) => f.onde === chave && f.liberada !== false && !SEM_INTERRUPTOR.has(f.chave));
      if (!grupo.length) continue;
      const cabeca = document.createElement("b");
      cabeca.textContent = titulo;
      caixa.append(cabeca);
      for (const f of grupo) {
        const rotulo = document.createElement("label"), marca = document.createElement("input");
        rotulo.className = "linha-check";
        rotulo.title = f.desc;
        marca.type = "checkbox";
        marca.checked = !desligadas.has(f.chave);
        marca.onchange = () => {
          if (marca.checked) desligadas.delete(f.chave); else desligadas.add(f.chave);
          chrome.storage.local.set({ funcoesDesligadas: [...desligadas] });
        };
        rotulo.append(marca, " " + f.nome);
        caixa.append(rotulo);
      }
    }
    $("personalizar").hidden = !caixa.children.length;
  } catch { $("personalizar").hidden = true; }
}

// o que a extensão leu hoje nas páginas do YouTube (contado pelo servidor)
// a barra de cada vídeo em produção (a mesma % do ícone): vem do Radar na hora em que a janelinha abre
async function carregarProgresso(servidor, token) {
  try {
    const r = await fetch(servidor + "/api/ext/progresso", { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    const videos = r.ok ? (await r.json()).videos || [] : [];
    $("progresso").hidden = !videos.length;
    $("progresso-lista").replaceChildren(...videos.map((v) => {
      const linha = document.createElement("div");
      linha.className = `pv${v.estado === "precisa_voce" ? " parado" : ""}`;
      linha.title = v.mensagem || "";
      const titulo = document.createElement("span"), pct = document.createElement("span"), barra = document.createElement("i"), cheia = document.createElement("i");
      titulo.textContent = v.titulo;
      pct.textContent = v.estado === "precisa_voce" ? "parou" : `${v.pct}%`;
      cheia.style.width = `${v.pct}%`;
      barra.append(cheia);
      linha.append(titulo, pct, barra);
      return linha;
    }));
  } catch { /* sem o Radar, a caixa fica escondida */ }
}

async function carregarHoje(servidor, token) {
  try {
    const r = await fetch(servidor + "/api/ext/hoje", { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    const h = await r.json();
    if (h.videos) $("hoje").textContent = `${h.videos.toLocaleString("pt-BR")} vídeos lidos · ${h.estouraram} estouraram · ${h.canais} canais novos no Radar`;
  } catch { /* fica o texto de sempre */ }
  try {
    const r = await fetch(servidor + "/api/ext/patente", { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (r.ok) {
      const p = await r.json();
      $("patente-nome").textContent = `${p.patente} · ${p.salvos} canais salvos`;
      $("patente-falta").textContent = p.proxima ? `Faltam ${p.faltam} para ${p.proxima}` : "O último degrau.";
      $("patente").hidden = false;
    }
  } catch { /* a patente é só um enfeite: sem ela, a janelinha segue */ }
  try {
    const [aba] = await chrome.tabs.query({ active: true, currentWindow: true });
    const c = aba && /youtube\.com/.test(aba.url || "") ? await chrome.tabs.sendMessage(aba.id, { tipo: "contadores" }) : null;
    if (c) {
      $("aba-numeros").textContent = `${c.videos} vídeos · ${c.estouraram} acima de 5x · ${c.canais} canais`;
      $("aba").hidden = false;
    }
  } catch { /* aba sem a extensão */ }
  const { semShorts } = await chrome.storage.local.get("semShorts");
  $("sem-shorts").checked = !!semShorts;
  $("sem-shorts").onchange = () => chrome.storage.local.set({ semShorts: $("sem-shorts").checked });
}

$("permitir").onclick = async () => {
  const ok = await chrome.permissions.request({ origins: ORIGENS });
  if (!ok) { $("erro").textContent = "Sem a permissão, a extensão não funciona. Clique em Permitir e depois em Permitir na janela do Chrome."; return; }
  mostrar();
};

$("servidor").onchange = async () => {
  await chrome.storage.local.set({ servidor: $("servidor").value.trim().replace(/\/+$/, "") || PADRAO });
  mostrar();
};

$("botao").onclick = async () => {
  $("erro").textContent = "";
  const servidor = await endereco();
  try {
    const r = await fetch(servidor + "/api/ext/entrar", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: $("email").value.trim(), senha: $("senha").value }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { $("erro").textContent = d.detail || `Erro ${r.status}`; return; }
    await chrome.storage.local.set({ token: d.token, eu: d.eu });
    $("senha").value = "";
    mostrar();
  } catch { $("erro").textContent = "O servidor não respondeu. Ele está ligado?"; }
};

async function carregarCanais(servidor, token) {
  const sel = $("treino");
  try {
    const r = await fetch(servidor + "/api/meus-canais", { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    const { canais } = await r.json();
    const { canalTreino } = await chrome.storage.local.get("canalTreino");
    sel.replaceChildren(new Option("Nenhum (sem selo)", ""));
    // o nome do canal entra como texto, nunca como HTML
    for (const c of canais || []) {
      const o = new Option(c.titulo, c.id, false, !!canalTreino && canalTreino.id === c.id);
      o.dataset.titulo = c.titulo;
      sel.add(o);
    }
    sel.onchange = () => {
      const o = sel.selectedOptions[0];
      if (!sel.value) chrome.storage.local.remove("canalTreino");
      else chrome.storage.local.set({ canalTreino: { id: sel.value, titulo: o.dataset.titulo } });
    };
  } catch { sel.replaceChildren(new Option("Não consegui ler os seus canais", "")); }
}

$("sair").onclick = async () => {
  const servidor = await endereco();
  const { token } = await chrome.storage.local.get("token");
  fetch(servidor + "/api/ext/sair", { method: "POST", headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
  await chrome.storage.local.remove(["token", "eu"]);
  mostrar();
};

$("site").onclick = async () => chrome.tabs.create({ url: await endereco() });

// qualquer erro aparece na janela, em vez de deixar ela vazia
mostrar().catch((e) => { $("erro").textContent = "Erro ao abrir: " + (e && e.message ? e.message : e); });
