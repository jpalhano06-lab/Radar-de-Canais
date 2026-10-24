// O `api()` do painel: a memória curta e a espera para o Radar voltar (itens 21 e 23 do plano do Dotti).
//
// É o único pedaço de JavaScript do Radar com regra de verdade — o resto é tela. Como o painel não tem bundler
// nem navegador nos testes, o trecho do `app.js` é recortado e roda aqui com o `fetch`, o `document` e o
// `setTimeout` de mentira: o teste mede quanto ele ESPERARIA, sem esperar.
//
//     node tests/app_js.test.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..");
const FONTE = readFileSync(join(RAIZ, "radar/web/app.js"), "utf8");

const inicio = FONTE.indexOf("const PACOTE = new Map();");
const fim = FONTE.indexOf("// a abertura: uma chamada traz o que a primeira tela pediria em várias");
assert.ok(inicio > 0 && fim > inicio, "não achei o trecho do api() no app.js");
const TRECHO = FONTE.slice(inicio, fim);

/** Monta o trecho com um mundo de mentira. `respostas` é a fila que o fetch vai devolver. */
function montar(respostas) {
  const pedidos = [], esperas = [];
  const faixas = [];                                   // o que foi posto e tirado do corpo da página
  const corpo = {
    appendChild: (e) => { faixas.push(e); return e; },
  };
  const documento = {
    body: corpo,
    getElementById: (id) => faixas.find((e) => e.id === id && !e.removido) || null,
    createElement: () => {
      const e = { id: "", textContent: "", removido: false, setAttribute() {}, remove() { this.removido = true; } };
      return e;
    },
  };
  const fetchFalso = async (caminho, opcoes) => {
    pedidos.push({ caminho, metodo: (opcoes && opcoes.method) || "GET" });
    const r = respostas.shift();
    if (!r) throw new Error("fetch sem resposta na fila para " + caminho);
    return { ok: r.status < 400, status: r.status, json: async () => r.corpo ?? {} };
  };
  const esperarFalso = (ok, ms) => { esperas.push(ms); ok(); return 0; };

  const fn = new Function("fetch", "document", "setTimeout",
    TRECHO + "; return { api, esquecer, ESPERAS };");
  return { ...fn(fetchFalso, documento, esperarFalso), pedidos, esperas, faixas };
}

const ok = (corpo = { tudo: "bem" }) => ({ status: 200, corpo });
const caiu = (status) => ({ status, corpo: { detail: "caiu" } });

test("503 duas vezes e depois responde: tenta de novo sozinho e entrega o dado", async () => {
  const m = montar([caiu(503), caiu(503), ok({ total: 7 })]);
  const d = await m.api("/api/radar");
  assert.deepEqual(d, { total: 7 });
  assert.equal(m.pedidos.length, 3, "pediu três vezes");
  assert.deepEqual(m.esperas, [2000, 4000], "esperou 2s e 4s, na ordem do plano");
});

test("a espera cresce 2s, 4s, 8s, 15s, 30s e para de crescer", async () => {
  const m = montar([...Array(6).fill(caiu(502)), ok()]);   // seis quedas: uma para cada espera da escala
  await m.api("/api/radar");
  assert.deepEqual(m.esperas, [2000, 4000, 8000, 15000, 30000, 30000]);
  assert.deepEqual(m.esperas, m.ESPERAS, "a escala é a do próprio app.js");
});

test("se não voltar nunca, desiste e o erro chega para a tela", async () => {
  const m = montar([...Array(7).fill(caiu(504))]);
  await assert.rejects(() => m.api("/api/radar"), (e) => e.status === 504);
  assert.equal(m.pedidos.length, 7, "sete pedidos: o primeiro e as seis esperas");
});

test("a faixa aparece enquanto espera e sai quando o Radar volta", async () => {
  const m = montar([caiu(503), ok()]);
  await m.api("/api/radar");
  assert.equal(m.faixas.length, 1, "uma faixa só");
  assert.equal(m.faixas[0].id, "faixa-voltando");
  assert.match(m.faixas[0].textContent, /voltando/);
  assert.equal(m.faixas[0].removido, true, "a faixa saiu sozinha");
});

test("erro que não é o Radar reiniciando não tenta de novo", async () => {
  for (const status of [401, 402, 404, 500]) {
    const m = montar([caiu(status)]);
    await assert.rejects(() => m.api("/api/radar"), (e) => e.status === status);
    assert.equal(m.pedidos.length, 1, `${status} pediu uma vez só`);
    assert.deepEqual(m.esperas, [], `${status} não esperou`);
    assert.equal(m.faixas.length, 0, `${status} não pôs faixa`);
  }
});

test("a memória curta guarda o que muda devagar e não guarda o resto", async () => {
  const m = montar([ok({ nichos: 21 })]);
  assert.deepEqual(await m.api("/api/resumo"), { nichos: 21 });
  assert.deepEqual(await m.api("/api/resumo"), { nichos: 21 }, "a segunda vez vem da memória");
  assert.equal(m.pedidos.length, 1, "um pedido só para os dois");

  const n = montar([ok({ a: 1 }), ok({ a: 2 })]);
  await n.api("/api/radar");
  await n.api("/api/radar");
  assert.equal(n.pedidos.length, 2, "a lista de canais não fica guardada");
});

test("quem escreve faz a leitura do mesmo caminho ser pedida de novo", async () => {
  const m = montar([ok({ nichos: 1 }), ok({ gravado: true }), ok({ nichos: 2 })]);
  await m.api("/api/resumo");
  await m.api("/api/resumo", { method: "POST", body: { x: 1 } });
  assert.deepEqual(await m.api("/api/resumo"), { nichos: 2 }, "a memória velha foi jogada fora");
  assert.equal(m.pedidos.length, 3);
});

test("duas telas pedindo a mesma coisa viram um pedido só", async () => {
  const m = montar([ok({ junto: true })]);
  const [a, b] = await Promise.all([m.api("/api/filtros"), m.api("/api/filtros")]);
  assert.deepEqual(a, b);
  assert.equal(m.pedidos.length, 1);
});

// ---------------------------------------------------------------- o trilho (item 9 do plano)

function trilhos() {
  const i = FONTE.indexOf("function trilho(chave, rotulo, degraus, f) {");
  const j = FONTE.indexOf("function ligarTrilhos(");
  const d = FONTE.indexOf("const DEGRAUS = {");
  const e = FONTE.indexOf("const degrausDe = (k) =>");
  assert.ok(i > 0 && j > i && d > 0 && e > d, "não achei o trilho nem os degraus no app.js");
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fn = new Function("esc", FONTE.slice(i, j) + FONTE.slice(d, e) + "; return { trilho, DEGRAUS };");
  return fn(esc);
}

test("views e inscritos são trilho, não campo de digitar", () => {
  const { trilho, DEGRAUS } = trilhos();
  for (const chave of ["views_min", "inscritos_max", "media_min"]) {
    const degraus = DEGRAUS[chave];
    assert.ok(degraus && degraus.length >= 6, `${chave} precisa de uma escala`);
    assert.equal(degraus[0][0], "", `${chave} começa no vazio, para o filtro poder ficar desligado`);
    const html = trilho(chave, "Rótulo", degraus, {});
    assert.match(html, /type="range"/, `${chave} tem de ser trilho`);
    assert.doesNotMatch(html, /type="number"|type="text"/, `${chave} não pede número digitado`);
    assert.match(html, new RegExp(`max="${degraus.length - 1}"`), "um degrau por passo");
    assert.match(html, /class="trilho-piso" hidden/, "cabe o aviso do piso do servidor");
  }
});

test("o trilho abre no degrau do filtro que já está ligado", () => {
  const { trilho, DEGRAUS } = trilhos();
  const degraus = DEGRAUS.views_min;
  const alvo = degraus.findIndex(([v]) => v === 100000);
  const html = trilho("views_min", "Views a partir de", degraus, { views_min: "100000" });
  assert.match(html, new RegExp(`value="${alvo}"`), "o cursor começa onde a pessoa deixou");
  assert.match(html, new RegExp(`>${degraus[alvo][1]}<`), "e o rótulo mostra o valor por nome");
  assert.match(trilho("views_min", "x", degraus, {}).match(/value="(\d+)"/)[1], /^0$/, "sem filtro, começa no zero");
});
