// As contas do horário de postar: node --test tests/horario.test.mjs
import assert from "node:assert/strict";
import test from "node:test";

await import("../extensao/horario.js");
const c = globalThis.RadarHorario.contas;
const dia = { a: 2026, m: 11, d: 7 };

test("17:00 em Nova York é 19:00 em Brasília em novembro", () => {
  const r = c.converter(dia, 17 * 60, "America/New_York", "America/Sao_Paulo");
  assert.equal(c.hhmm(r.min), "19:00");
  assert.equal(r.dias, 0);
});

test("o horário de verão conta", () => {
  const julho = c.converter({ a: 2026, m: 7, d: 7 }, 17 * 60, "America/New_York", "America/Sao_Paulo");
  assert.equal(c.hhmm(julho.min), "18:00");
});

test("Coreia passa de dia", () => {
  const r = c.converter(dia, 8 * 60, "Asia/Seoul", "America/Sao_Paulo");
  assert.equal(c.hhmm(r.min), "20:00");
  assert.equal(r.dias, -1);
});

test("fuso escrito pelo Studio", () => {
  assert.deepEqual(c.fusoEscrito("Fuso horário (GMT-03:00)"), { off: -180 });
  assert.deepEqual(c.fusoEscrito("GMT+5:30"), { off: 330 });
  assert.equal(c.fusoEscrito("sem fuso"), null);
  const r = c.converter(dia, 17 * 60, "America/New_York", { off: -180 });
  assert.equal(c.hhmm(r.min), "19:00");
});

test("hora da lista do Studio", () => {
  assert.equal(c.minutosDe("17:15"), 1035);
  assert.equal(c.minutosDe("5:15 PM"), 1035);
  assert.equal(c.minutosDe("12:00 AM"), 0);
  assert.equal(c.minutosDe("12:30 PM"), 750);
  assert.equal(c.minutosDe("nada"), null);
});

test("data do Studio em cada língua", () => {
  assert.deepEqual(c.dataEscrita("Nov 7, 2026", "en-US"), dia);
  assert.deepEqual(c.dataEscrita("7 de nov. de 2026", "pt-BR"), dia);
  assert.deepEqual(c.dataEscrita("07/11/2026", "pt-BR"), dia);
  assert.deepEqual(c.dataEscrita("11/07/2026", "en-US"), dia);
});

test("as horas se somam, sem a hora que ainda conta", () => {
  const agora = Date.UTC(2026, 10, 7, 12);
  const h = (x) => agora - x * 36e5;
  const mapa = c.juntarHoras({ [h(2000)]: 9 }, [[h(3) / 1000, 10], [h(2) / 1000, 20], [h(0) / 1000, 99]], agora);
  assert.deepEqual(Object.values(mapa).sort((a, b) => a - b), [10, 20]);
});

test("melhores horas pela média, no relógio pedido", () => {
  const t = (d, h) => Date.UTC(2026, 10, d, h);
  const m = c.melhoresHoras({ [t(5, 12)]: 100, [t(6, 12)]: 300, [t(5, 20)]: 50, [t(5, 3)]: 10 }, "UTC", 2);
  assert.deepEqual(m.horas.map((x) => x.hora), [12, 20]);
  assert.equal(m.horas[0].media, 200);
  assert.equal(c.melhoresHoras({ [t(5, 12)]: 1 }, { off: -180 }).horas[0].hora, 9);
});

test("o botão coloca antes do pico, passando da meia-noite", () => {
  assert.equal(c.hhmm(c.antesDoPico(22)), "19:30");
  assert.equal(c.hhmm(c.antesDoPico(1)), "22:30");
});

test("país pela sigla do Studio", () => {
  assert.equal(c.paisDaSigla("US").id, "us-leste");
  assert.equal(c.paisDaSigla("GB").id, "uk");
  assert.equal(c.paisDaSigla("KR").id, "kr");
  assert.equal(c.paisDaSigla("ZZ"), null);
  assert.equal(c.paisDaSigla(""), null);
});

test("país pelo nome do canal", () => {
  assert.equal(c.paisDoNome("Canada Insight").id, "ca-leste");
  assert.equal(c.paisDoNome("UK CartWatch").id, "uk");
  assert.equal(c.paisDoNome("한국의 미래 (Hangugui Mirae)").id, "kr");
  assert.equal(c.paisDoNome("日本の革新").id, "jp");
  assert.equal(c.paisDoNome("Nederland Innoveert").id, "nl");
  assert.equal(c.paisDoNome("João o Lobo"), null);
});

test("instante agendado em qualquer campo, só no futuro", () => {
  const agora = 1793990000000;
  assert.equal(c.instanteAgendado({ scheduledPublishings: { timeSeconds: "1794000000" } }, agora), 1794000000000);
  assert.equal(c.instanteAgendado({ a: "1700000000" }, agora), 0);
  assert.equal(c.instanteAgendado(undefined, agora), 0);
});

test("vídeo colado: pega o mais perto, ignora o próprio e o distante", () => {
  const h = 36e5, base = 1793990000000;
  const videos = [{ id: "a", quando: base + 10 * h }, { id: "b", quando: base + 2 * h }, { id: "c", quando: base + 30 * h }];
  assert.equal(c.videoColado(videos, base).id, "b");
  assert.equal(c.videoColado(videos, base, "b").id, "a");
  assert.equal(c.videoColado([{ id: "c", quando: base + 30 * h }], base), null);
});
