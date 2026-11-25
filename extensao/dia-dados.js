// "Meu dia" (pedido do usuário em 2026-11-14): a aba que os dois cliques com o botão direito abrem no YouTube. Ela
// organiza o dia: quantos vídeos cada canal precisa ter hoje, os pedidos da Nova produção ("feito, falta a
// thumbnail"), as thumbnails guardadas pelo menu do botão direito e o link do canal de treino do algoritmo.
//
// Tudo fica no chrome.storage.local:
// - `diaConfig` { [canalId]: { porDia, treino } }: a meta de vídeos por dia e o link do canal de treino. Não se apaga.
// - `dia` { data, videos: [], thumbs: [] }: o dia de hoje. Virou o dia, ele recomeça vazio (e as imagens somem).
// - `diaThumb:<id>`: cada imagem, em data URL, separada para o `dia` ficar leve.
// Usado pelo background.js (importScripts) e pela própria aba (dia.html).

const DIA_CHAVE = "dia", DIA_CONFIG = "diaConfig", DIA_THUMB = "diaThumb:";
// "procurar ideia para amanhã" (pedido do usuário em 2026-11-15): o canal escolhido fica em `diaDestino` e o próximo
// pedido da Nova produção dele vai para `diaAmanha` ({ ...video, para: "AAAA-MM-DD" }), que entra no dia quando ele vira
const DIA_AMANHA = "diaAmanha", DIA_DESTINO = "diaDestino";
// todos os dias iguais (pedido do usuário em 2026-11-24): um dia do calendário tem as mesmas coisas que hoje. O que
// não mora num vídeo da fila (as thumbnails feitas do canal e o "não vou postar") fica em `diaFuturo`
// { [AAAA-MM-DD]: { thumbs: [], semPostar: [] } } e entra no `dia` quando ele vira hoje
const DIA_FUTURO = "diaFuturo";
const DESTINO_VALE = 20 * 60 * 60 * 1000;

function hojeLocal() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function amanhaLocal() {
  return diaDaqui(1);
}

/** A data (AAAA-MM-DD) daqui a `n` dias, no fuso do computador. */
function diaDaqui(n) {
  const d = new Date(); d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const ehData = (x) => /^\d{4}-\d{2}-\d{2}$/.test(String(x || ""));

/** O calendário do Meu dia (pedido do usuário em 2026-11-22: "tem que colocar calendário para poder fazer para vários
 *  vídeos"): um pedido vai para qualquer dia, não só para amanhã. Ele pode estar hoje (no `dia`) ou na fila dos
 *  próximos dias (`diaAmanha`, com `para`); vai para `data` com a thumbnail. Hoje ou antes: entra no dia de hoje. */
async function diaMoverParaData(id, data) {
  if (!ehData(data)) return null;
  const hoje = hojeLocal();
  const { [DIA_AMANHA]: fila = [] } = await chrome.storage.local.get(DIA_AMANHA);
  const naFila = fila.find((x) => x.id === id);
  if (naFila) {
    if (data <= hoje) return diaAmanhaParaHoje(id);
    naFila.para = data;
    await chrome.storage.local.set({ [DIA_AMANHA]: fila });
    return naFila;
  }
  if (data <= hoje) return null;  // já está hoje
  const v = await mudarDia((d) => {
    const x = d.videos.find((y) => y.id === id);
    if (!x || x.postado) return null;
    d.videos = d.videos.filter((y) => y.id !== id);
    const ids = new Set([x.thumb, ...(x.ab || [])].filter(Boolean));
    const thumbsGuardadas = d.thumbs.filter((t) => ids.has(t.id));
    d.thumbs = d.thumbs.filter((t) => !ids.has(t.id));
    return { ...x, thumbsGuardadas };
  });
  if (!v) return null;
  const { [DIA_AMANHA]: fila2 = [] } = await chrome.storage.local.get(DIA_AMANHA);
  fila2.push({ ...v, para: data });
  await chrome.storage.local.set({ [DIA_AMANHA]: fila2 });
  return v;
}

/** Planejar um vídeo num dia (o "+ Planejar" do calendário): só o título e o canal, sem pedido na fábrica ainda. */
async function diaPlanejar({ canal, canalNome, titulo, data }) {
  if (!ehData(data) || !String(titulo || "").trim()) return null;
  const novo = { id: novoIdDia(), hora: Date.now(), postado: false, thumb: null, canal, canalNome,
    titulo: String(titulo).trim(), planejado: true };
  if (data <= hojeLocal()) return mudarDia((d) => { d.videos.push(novo); return novo; });
  const { [DIA_AMANHA]: fila = [] } = await chrome.storage.local.get(DIA_AMANHA);
  fila.push({ ...novo, para: data });
  await chrome.storage.local.set({ [DIA_AMANHA]: fila });
  return novo;
}

/** O dia de hoje. Se o guardado é de outro dia, começa um novo com os pedidos guardados para hoje (o "para amanhã"
 *  de ontem) e os vídeos que não foram postados (pedido do usuário em 2026-11-16: "se o vídeo não for postado ele
 *  fica direto para o outro dia"), com a thumbnail e o teste A/B deles; `veioDe` diz de que dia vieram. O resto do
 *  dia velho (postados, thumbnails soltas, tirados) e as imagens dele são apagados. */
async function lerDia() {
  const { dia, [DIA_AMANHA]: fila = [], [DIA_FUTURO]: futuro = {} } = await chrome.storage.local.get([DIA_CHAVE, DIA_AMANHA, DIA_FUTURO]);
  const hoje = hojeLocal();
  if (dia && dia.data === hoje) return dia;
  // o que foi guardado para hoje (ou para um dia que passou sem o Meu dia aberto) no dia do calendário
  const chegaram = Object.keys(futuro).filter((iso) => iso <= hoje);
  const doFuturo = chegaram.map((iso) => futuro[iso] || {});
  for (const iso of chegaram) delete futuro[iso];
  const ficam = ((dia && dia.videos) || []).filter((v) => !v.postado).map((v) => ({ ...v, veioDe: v.veioDe || dia.data }));
  const imagensQueFicam = new Set(ficam.flatMap((v) => [v.thumb, ...(v.ab || [])]).filter(Boolean));
  const thumbsQueFicam = ((dia && dia.thumbs) || []).filter((t) => imagensQueFicam.has(t.id));
  for (const v of fila) for (const t of v.thumbsGuardadas || []) imagensQueFicam.add(t.id);
  const apagar = ((dia && dia.thumbs) || []).filter((t) => !imagensQueFicam.has(t.id));
  if (apagar.length) await chrome.storage.local.remove(apagar.map((t) => DIA_THUMB + t.id));
  const entram = fila.filter((v) => (v.para || "") <= hoje);
  const novo = { data: hoje, videos: [...ficam, ...entram.map(({ para, thumbsGuardadas, ...v }) => v)],
    thumbs: [...thumbsQueFicam, ...entram.flatMap((v) => v.thumbsGuardadas || []), ...doFuturo.flatMap((f) => f.thumbs || [])],
    semPostar: [...new Set(doFuturo.flatMap((f) => f.semPostar || []))] };
  await chrome.storage.local.set({ [DIA_CHAVE]: novo, [DIA_AMANHA]: fila.filter((v) => !entram.includes(v)), [DIA_FUTURO]: futuro });
  return novo;
}

/** Um dia qualquer no mesmo formato do `dia` de hoje ({ data, videos, thumbs, semPostar }). Hoje (ou antes) é o
 *  próprio `dia`; um dia do calendário é montado dos pedidos dele na fila (`diaAmanha`) e do `diaFuturo`. */
async function lerDiaDe(iso) {
  if (!ehData(iso) || iso <= hojeLocal()) return lerDia();
  const { [DIA_AMANHA]: fila = [], [DIA_FUTURO]: futuro = {} } = await chrome.storage.local.get([DIA_AMANHA, DIA_FUTURO]);
  const doDia = fila.filter((v) => v.para === iso);
  const extra = futuro[iso] || {};
  return { data: iso, videos: doDia.map(({ thumbsGuardadas, ...v }) => v),
    thumbs: [...doDia.flatMap((v) => v.thumbsGuardadas || []), ...(extra.thumbs || [])], semPostar: extra.semPostar || [] };
}

/** O mudarDia de um dia qualquer: hoje vai direto no `dia`; num dia do calendário a mudança feita no dia montado
 *  volta para a fila (cada vídeo com as thumbnails dele) e para o `diaFuturo` (as soltas e o "não vou postar"). */
function mudarDiaDe(iso, fn) {
  if (!ehData(iso) || iso <= hojeLocal()) return mudarDia(fn);
  const p = filaDoDia.then(async () => {
    const d = await lerDiaDe(iso);
    const r = await fn(d);
    const { [DIA_AMANHA]: fila = [], [DIA_FUTURO]: futuro = {} } = await chrome.storage.local.get([DIA_AMANHA, DIA_FUTURO]);
    const porId = new Map(d.thumbs.map((t) => [t.id, t]));
    const usadas = new Set();
    const outros = fila.filter((v) => v.para !== iso);
    const doDia = d.videos.map((v) => {
      const ids = [v.thumb, ...(v.ab || [])].filter(Boolean);
      ids.forEach((id) => usadas.add(id));
      return { ...v, para: iso, thumbsGuardadas: ids.map((id) => porId.get(id)).filter(Boolean) };
    });
    const soltas = d.thumbs.filter((t) => !usadas.has(t.id));
    const semPostar = d.semPostar || [];
    if (soltas.length || semPostar.length) futuro[iso] = { thumbs: soltas, semPostar }; else delete futuro[iso];
    await chrome.storage.local.set({ [DIA_AMANHA]: [...outros, ...doDia], [DIA_FUTURO]: futuro });
    return r;
  });
  filaDoDia = p.catch(() => {});
  return p;
}

/** O padrão de postagem de cada canal (pedido do usuário em 2026-11-24: "pode ser criado um padrão para cada canal,
 *  fica mais fácil"): `diaConfig[canal].postagem` = { horas: [18, 21], auto, anuncioCada, telaFinal }. Cada vídeo do
 *  dia sem agendamento ganha a hora da vez dele (o 1º do canal no dia a primeira hora, o 2º a segunda…) e o "postar
 *  sozinho" do padrão. Hora que já passou fica sem; o vídeo em que a pessoa tirou o agendamento (`semPadrao`) também.
 *  Roda no Meu dia (recarregar) e no background antes de olhar a fábrica. Devolve quantos vídeos mudaram. */
async function diaAplicarPadroes() {
  const { [DIA_CONFIG]: config = {}, [DIA_AMANHA]: fila = [] } = await chrome.storage.local.get([DIA_CONFIG, DIA_AMANHA]);
  const padrao = (canal) => (config[canal] || {}).postagem || null;
  if (!Object.values(config).some((c) => c && c.postagem && (c.postagem.horas || []).some((x) => x != null))) return 0;
  const aplicar = (d) => {
    let mudou = 0;
    const porCanal = {};
    for (const v of [...d.videos].sort((a, b) => (a.hora || 0) - (b.hora || 0))) {
      const k = v.canal || "";
      porCanal[k] = (porCanal[k] || 0) + 1;
      const p = padrao(k);
      if (!p || v.postado || v.agendar || v.semPadrao) continue;
      const horas = (p.horas || []).filter((x) => x != null);
      const hr = (p.horas || [])[porCanal[k] - 1] ?? horas[horas.length - 1];
      if (hr == null) continue;
      const quando = `${d.data}T${String(hr).padStart(2, "0")}:00`;
      if (new Date(quando).getTime() <= Date.now() + 10 * 60 * 1000) continue;
      v.agendar = quando;
      if (p.auto) v.auto = true;
      mudou++;
    }
    return mudou;
  };
  // só grava o dia que muda: gravar à toa acorda o Meu dia (storage.onChanged), que chama isto de novo
  const precisa = (d) => aplicar(JSON.parse(JSON.stringify(d))) > 0;
  let total = 0;
  if (precisa(await lerDia())) total += await mudarDia(aplicar);
  for (const iso of [...new Set(fila.map((v) => v.para).filter(ehData))]) {
    if (precisa(await lerDiaDe(iso))) total += await mudarDiaDe(iso, aplicar);
  }
  return total;
}

/** Muda um vídeo pelo id, esteja ele hoje ou num dia do calendário (o "postar sozinho" do background). */
async function diaMudarVideo(id, fn) {
  const achou = await mudarDia((d) => { const v = d.videos.find((x) => x.id === id); if (v) fn(v); return !!v; });
  if (achou) return true;
  const { [DIA_AMANHA]: fila = [] } = await chrome.storage.local.get(DIA_AMANHA);
  const v = fila.find((x) => x.id === id);
  if (!v) return false;
  return mudarDiaDe(v.para, (d) => { const x = d.videos.find((y) => y.id === id); if (x) fn(x); return !!x; });
}

/** Tirar um vídeo de um dia do calendário (o × de lá): sai da fila com as imagens dele. */
async function diaTirarDoCalendario(id) {
  const { [DIA_AMANHA]: fila = [] } = await chrome.storage.local.get(DIA_AMANHA);
  const v = fila.find((x) => x.id === id);
  if (!v) return null;
  await chrome.storage.local.set({ [DIA_AMANHA]: fila.filter((x) => x.id !== id) });
  const imagens = (v.thumbsGuardadas || []).map((t) => DIA_THUMB + t.id);
  if (imagens.length) await chrome.storage.local.remove(imagens);
  return v;
}

// uma mudança de cada vez neste contexto, para duas não se atropelarem
let filaDoDia = Promise.resolve();
function mudarDia(fn) {
  const p = filaDoDia.then(async () => {
    const d = await lerDia();
    const r = await fn(d);
    await chrome.storage.local.set({ [DIA_CHAVE]: d });
    return r;
  });
  filaDoDia = p.catch(() => {});
  return p;
}

const novoIdDia = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

/** Tirar um vídeo do dia (o ×) não apaga mais (pedido do usuário em 2026-11-16: "sem querer eu excluí o vídeo que
 *  pedi"): ele vai para `d.tirados` (com a thumbnail dele, até 20) e volta com diaVoltarVideo. Some quando vira o dia. */
function diaTirarVideo(id) {
  return mudarDia((d) => {
    const v = d.videos.find((x) => x.id === id);
    if (!v) return null;
    d.videos = d.videos.filter((x) => x.id !== id);
    d.tirados = [...(d.tirados || []).filter((x) => x.id !== id), { ...v, tiradoHora: Date.now() }].slice(-20);
    return v;
  });
}
function diaVoltarVideo(id) {
  return mudarDia((d) => {
    const v = (d.tirados || []).find((x) => x.id === id);
    if (!v) return null;
    d.tirados = d.tirados.filter((x) => x.id !== id);
    const { tiradoHora, ...volta } = v;
    d.videos.push(volta);
    return volta;
  });
}
/** Um pedido da fábrica que não está no Meu dia volta para hoje (o "Pôr de volta" do canal). Não passa pelo destino
 *  "para amanhã": é um vídeo que já era de hoje. */
function diaVoltarDaFabrica({ canal, canalNome, titulo, link = "", fila = null }) {
  return mudarDia((d) => {
    const novo = { id: novoIdDia(), hora: Date.now(), postado: false, thumb: null, canal, canalNome, titulo,
      ...(link ? { referencia: link } : {}), ...(fila ? { fila } : {}) };
    d.videos.push(novo);
    return novo;
  });
}

/** Trocar o dia de um pedido (pedido do usuário em 2026-11-17: "sem querer eu coloquei pra amanhã, tem que ter a
 *  opção de mudar pra hoje ou amanhã"). O de amanhã vem para hoje; o de hoje vai para amanhã, com a thumbnail (a
 *  imagem fica guardada enquanto ele estiver na fila). */
async function diaAmanhaParaHoje(id) {
  const { [DIA_AMANHA]: fila = [] } = await chrome.storage.local.get(DIA_AMANHA);
  const v = fila.find((x) => x.id === id);
  if (!v) return null;
  await chrome.storage.local.set({ [DIA_AMANHA]: fila.filter((x) => x.id !== id) });
  const { para, ...volta } = v;
  return mudarDia((d) => {
    d.videos.push(volta);
    for (const t of v.thumbsGuardadas || []) if (!d.thumbs.some((x) => x.id === t.id)) d.thumbs.push(t);
    delete volta.thumbsGuardadas;
    return volta;
  });
}
async function diaHojeParaAmanha(id) {
  const v = await mudarDia((d) => {
    const x = d.videos.find((y) => y.id === id);
    if (!x) return null;
    d.videos = d.videos.filter((y) => y.id !== id);
    const ids = new Set([x.thumb, ...(x.ab || [])].filter(Boolean));
    const thumbsGuardadas = d.thumbs.filter((t) => ids.has(t.id));
    d.thumbs = d.thumbs.filter((t) => !ids.has(t.id));
    return { ...x, thumbsGuardadas };
  });
  if (!v) return null;
  const { [DIA_AMANHA]: fila = [] } = await chrome.storage.local.get(DIA_AMANHA);
  fila.push({ ...v, para: amanhaLocal() });
  await chrome.storage.local.set({ [DIA_AMANHA]: fila });
  return v;
}

/** Um vídeo pedido hoje (da Nova produção ou marcado à mão): { canal, canalNome, titulo }. */
async function diaNovoVideo(v) {
  const { [DIA_DESTINO]: destinos = {} } = await chrome.storage.local.get(DIA_DESTINO);
  const destino = v.canal && destinos[v.canal];
  if (destino) { delete destinos[v.canal]; await chrome.storage.local.set({ [DIA_DESTINO]: destinos }); }
  const novo = { id: novoIdDia(), hora: Date.now(), postado: false, thumb: null, ...v };
  // o destino é "amanha" ou, desde o calendário (2026-11-22), uma data qualquer (AAAA-MM-DD)
  const para = destino && (destino.dia === "amanha" ? amanhaLocal() : ehData(destino.dia) ? destino.dia : "");
  if (para && para > hojeLocal() && Date.now() - destino.quando < DESTINO_VALE) {
    const { [DIA_AMANHA]: fila = [] } = await chrome.storage.local.get(DIA_AMANHA);
    fila.push({ ...novo, para });
    await chrome.storage.local.set({ [DIA_AMANHA]: fila });
    return novo.id;
  }
  return mudarDia((d) => { d.videos.push(novo); return novo.id; });
}

/** Guarda uma imagem (data URL). Com `video`, ela já vira a thumbnail desse vídeo. Com `canal` (o botão direito >
 *  Salvar no Meu dia > o canal), ela vira a thumbnail feita desse canal: entra no primeiro vídeo de hoje dele que
 *  ainda não tem thumbnail, ou fica no cartão do canal como feita. Devolve o vídeo que recebeu, se houver. */
async function diaGuardarThumb(dados, { origem = "", nome = "", video = null, canal = null, canalNome = "", ab = null, data = "" } = {}) {
  const id = novoIdDia();
  await chrome.storage.local.set({ [DIA_THUMB + id]: dados });
  // `data`: o dia do calendário que está na tela (sem ela, hoje)
  return mudarDiaDe(data, (d) => {
    d.thumbs.push({ id, origem, nome, hora: Date.now(), ...(canal ? { canal, canalNome } : {}) });
    // `ab`: o vídeo do teste A/B (2026-11-16): a imagem vira a thumbnail B ou C dele (v.ab, até 2), a A é v.thumb
    if (ab) {
      const alvo = d.videos.find((x) => x.id === ab);
      if (alvo) alvo.ab = [...(alvo.ab || []), id].slice(-2);
      return alvo || null;
    }
    const v = video ? d.videos.find((x) => x.id === video)
      : canal ? d.videos.find((x) => x.canal === canal && !x.thumb) : null;
    if (v) v.thumb = id;
    return v || null;
  });
}

/** Publicou no Studio (publicar.js): o vídeo do Meu dia fica como postado. Acha pelo id (o botão Postar) ou, para
 *  quem subiu sem o botão, pelo título. Devolve o id marcado, ou null. */
function diaMarcarPostado({ id = "", titulos = [] } = {}) {
  const limpo = (t) => String(t || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  const alvos = titulos.map(limpo).filter((t) => t.length >= 6);
  const marcar = (d) => {
    const v = (id && d.videos.find((x) => x.id === id))
      || d.videos.find((x) => !x.postado && alvos.includes(limpo(x.titulo)));
    if (!v) return null;
    v.postado = true;
    v.postadoHora = Date.now();
    return v.id;
  };
  // o vídeo de um dia do calendário (agendado pelo Postar de lá) fica postado no dia dele
  return mudarDia(marcar).then(async (achou) => {
    if (achou) return achou;
    const { [DIA_AMANHA]: fila = [] } = await chrome.storage.local.get(DIA_AMANHA);
    const v = (id && fila.find((x) => x.id === id)) || fila.find((x) => !x.postado && alvos.includes(limpo(x.titulo)));
    return v ? mudarDiaDe(v.para, marcar) : null;
  });
}
