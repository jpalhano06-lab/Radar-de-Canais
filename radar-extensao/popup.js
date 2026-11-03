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
}

// o que a extensão leu hoje nas páginas do YouTube (contado pelo servidor)
async function carregarHoje(servidor, token) {
  try {
    const r = await fetch(servidor + "/api/ext/hoje", { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    const h = await r.json();
    if (h.videos) $("hoje").textContent = `${h.videos.toLocaleString("pt-BR")} vídeos lidos · ${h.estouraram} estouraram · ${h.canais} canais novos no Radar`;
  } catch { /* fica o texto de sempre */ }
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
