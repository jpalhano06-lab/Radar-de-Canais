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
const DESTINO_VALE = 20 * 60 * 60 * 1000;

function hojeLocal() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function amanhaLocal() {
  const d = new Date(); d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** O dia de hoje. Se o guardado é de outro dia, começa um novo com os pedidos guardados para hoje (o "para amanhã"
 *  de ontem) e os vídeos que não foram postados (pedido do usuário em 2026-11-16: "se o vídeo não for postado ele
 *  fica direto para o outro dia"), com a thumbnail e o teste A/B deles; `veioDe` diz de que dia vieram. O resto do
 *  dia velho (postados, thumbnails soltas, tirados) e as imagens dele são apagados. */
async function lerDia() {
  const { dia, [DIA_AMANHA]: fila = [] } = await chrome.storage.local.get([DIA_CHAVE, DIA_AMANHA]);
  const hoje = hojeLocal();
  if (dia && dia.data === hoje) return dia;
  const ficam = ((dia && dia.videos) || []).filter((v) => !v.postado).map((v) => ({ ...v, veioDe: v.veioDe || dia.data }));
  const imagensQueFicam = new Set(ficam.flatMap((v) => [v.thumb, ...(v.ab || [])]).filter(Boolean));
  const thumbsQueFicam = ((dia && dia.thumbs) || []).filter((t) => imagensQueFicam.has(t.id));
  for (const v of fila) for (const t of v.thumbsGuardadas || []) imagensQueFicam.add(t.id);
  const apagar = ((dia && dia.thumbs) || []).filter((t) => !imagensQueFicam.has(t.id));
  if (apagar.length) await chrome.storage.local.remove(apagar.map((t) => DIA_THUMB + t.id));
  const entram = fila.filter((v) => (v.para || "") <= hoje);
  const novo = { data: hoje, videos: [...ficam, ...entram.map(({ para, thumbsGuardadas, ...v }) => v)],
    thumbs: [...thumbsQueFicam, ...entram.flatMap((v) => v.thumbsGuardadas || [])] };
  await chrome.storage.local.set({ [DIA_CHAVE]: novo, [DIA_AMANHA]: fila.filter((v) => !entram.includes(v)) });
  return novo;
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
  if (destino && destino.dia === "amanha" && Date.now() - destino.quando < DESTINO_VALE) {
    const { [DIA_AMANHA]: fila = [] } = await chrome.storage.local.get(DIA_AMANHA);
    fila.push({ ...novo, para: amanhaLocal() });
    await chrome.storage.local.set({ [DIA_AMANHA]: fila });
    return novo.id;
  }
  return mudarDia((d) => { d.videos.push(novo); return novo.id; });
}

/** Guarda uma imagem (data URL). Com `video`, ela já vira a thumbnail desse vídeo. Com `canal` (o botão direito >
 *  Salvar no Meu dia > o canal), ela vira a thumbnail feita desse canal: entra no primeiro vídeo de hoje dele que
 *  ainda não tem thumbnail, ou fica no cartão do canal como feita. Devolve o vídeo que recebeu, se houver. */
async function diaGuardarThumb(dados, { origem = "", nome = "", video = null, canal = null, canalNome = "", ab = null } = {}) {
  const id = novoIdDia();
  await chrome.storage.local.set({ [DIA_THUMB + id]: dados });
  return mudarDia((d) => {
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
  return mudarDia((d) => {
    const v = (id && d.videos.find((x) => x.id === id))
      || d.videos.find((x) => !x.postado && alvos.includes(limpo(x.titulo)));
    if (!v) return null;
    v.postado = true;
    v.postadoHora = Date.now();
    return v.id;
  });
}
