// As contas do painel de anúncios: node --test tests/anuncios.test.mjs
import assert from "node:assert/strict";
import test from "node:test";

await import("../extensao/anuncios.js");
const c = globalThis.RadarAnuncios.contas;

test("carimbo do Studio vai e volta", () => {
  assert.equal(c.paraCarimbo(3725.5, 30), "1:02:05:15");
  assert.equal(c.deCarimbo("1:02:05:15", 30), 3725.5);
  assert.equal(c.deCarimbo("02:05:15", 30), 125.5);
  assert.equal(c.deCarimbo("nada"), null);
});

test("o tempo digitado aceita minutos e relógio", () => {
  assert.equal(c.deTempo("2,5"), 150);
  assert.equal(c.deTempo("1:30"), 90);
  assert.equal(c.deTempo("1:02:00"), 3720);
  assert.equal(c.deTempo("1:75"), null);
});

test("a cada: conta do início e não passa do fim", () => {
  assert.deepEqual(c.aCada({ dur: 600, passo: 180 }), [180, 360, 540]);
  assert.deepEqual(c.aCada({ dur: 600, passo: 180, inicio: 60 }), [60, 240, 420]);
});

test("quantidade: espalha por igual", () => {
  assert.deepEqual(c.quantidade({ dur: 600, n: 2 }), [200, 400]);
  assert.equal(c.quantidade({ dur: 6000, n: 900 }).length, c.MAXIMO);
});

test("a onda ignora a margem do canvas ao converter para segundos", () => {
  // 10 colunas, as duas das pontas são margem; a pausa está no meio do trecho útil
  const forca = [0, 1, 1, 1, 0, 0, 1, 1, 1, 0];
  const pausas = c.acharPausas(forca, { dur: 80, pico: 1, esq: 0.1, dir: 0.9, minMs: 100 });
  assert.equal(pausas.filter((p) => p.t > 0 && p.t < 80).length, 1);
  assert.equal(Math.round(pausas.find((p) => p.t > 1 && p.t < 79).t), 40);
});

test("pausas: a mais longa ganha e a distância vale", () => {
  const lista = [{ t: 100, dura: 0.4 }, { t: 130, dura: 0.9 }, { t: 400, dura: 0.5 }];
  assert.deepEqual(c.escolherPausas(lista, 120), [130, 400]);
  assert.deepEqual(c.escolherPausas(lista, 120, [420]), [130]);
});

test("o plano tira o que cai no fim e em cima de um que fica", () => {
  const plano = c.planejar({ modo: "cada", dur: 600, passo: 180, nosUltimos: 90, existentes: [360] });
  assert.deepEqual(plano, [180]);
});

test("o plano por pausas respeita o início", () => {
  const pausas = [{ t: 50, dura: 2 }, { t: 300, dura: 1 }];
  assert.deepEqual(c.planejar({ modo: "pausas", dur: 600, inicio: 60, pausas, distancia: 120 }), [300]);
});

test("fps pelas marcas do player", () => {
  assert.equal(c.fpsDasMarcas([0, 1 / 30, 2 / 30, 3 / 30]), 30);
  assert.equal(c.fpsDasMarcas([0, 1 / 24, 2 / 24]), 24);
  assert.equal(c.fpsDasMarcas([]), 30);
});

test("acha a linha nova mesmo com tempos repetidos", () => {
  assert.equal(c.acharNova(["0:00:10:00"], ["0:00:10:00", "0:00:10:00"], 10), 1);
  assert.equal(c.acharNova(["0:00:10:00"], ["0:00:05:00", "0:00:10:00"], 5), 0);
  assert.equal(c.acharNova(["0:00:10:00"], ["0:00:10:00"], 5), -1);
});

test("lugar livre foge de quem está ocupado", () => {
  assert.equal(c.lugarLivre([180], 180, 600), 179);
  assert.deepEqual(c.tempoVizinhos(180, 600, [181]).slice(0, 2), [179, 182]);
});
