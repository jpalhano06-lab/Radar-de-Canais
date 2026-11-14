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

function hojeLocal() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** O dia de hoje. Se o guardado é de outro dia, apaga ele (e as imagens dele) e começa um vazio. */
async function lerDia() {
  const { dia } = await chrome.storage.local.get(DIA_CHAVE);
  const hoje = hojeLocal();
  if (dia && dia.data === hoje) return dia;
  if (dia && dia.thumbs && dia.thumbs.length) await chrome.storage.local.remove(dia.thumbs.map((t) => DIA_THUMB + t.id));
  const novo = { data: hoje, videos: [], thumbs: [] };
  await chrome.storage.local.set({ [DIA_CHAVE]: novo });
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

/** Um vídeo pedido hoje (da Nova produção ou marcado à mão): { canal, canalNome, titulo }. */
function diaNovoVideo(v) {
  return mudarDia((d) => { const id = novoIdDia(); d.videos.push({ id, hora: Date.now(), postado: false, thumb: null, ...v }); return id; });
}

/** Guarda uma imagem (data URL). Com `video`, ela já vira a thumbnail desse vídeo. Com `canal` (o botão direito >
 *  Salvar no Meu dia > o canal), ela vira a thumbnail feita desse canal: entra no primeiro vídeo de hoje dele que
 *  ainda não tem thumbnail, ou fica no cartão do canal como feita. Devolve o vídeo que recebeu, se houver. */
async function diaGuardarThumb(dados, { origem = "", nome = "", video = null, canal = null, canalNome = "" } = {}) {
  const id = novoIdDia();
  await chrome.storage.local.set({ [DIA_THUMB + id]: dados });
  return mudarDia((d) => {
    d.thumbs.push({ id, origem, nome, hora: Date.now(), ...(canal ? { canal, canalNome } : {}) });
    const v = video ? d.videos.find((x) => x.id === video)
      : canal ? d.videos.find((x) => x.canal === canal && !x.thumb) : null;
    if (v) v.thumb = id;
    return v || null;
  });
}
