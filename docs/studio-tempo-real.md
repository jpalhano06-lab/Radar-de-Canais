# Números do canal em tempo real (o que o YouTube Studio usa) — levantado em 2026-10-19

O widget do Dotti (1h, 48h, 7d, 30d, tempo assistido e ganhos de 12 meses) e o "Hoje" do cartão Em tempo real
saem da API interna do próprio Studio. Visto no Chrome do usuário, no canal Canada Insight:

- Rota: `POST https://studio.youtube.com/youtubei/v1/yta_web/get_cards` (só aceita a origem do Studio; pedida do
  www.youtube.com os cartões voltam `isFailed`, e de outra origem dá "Origin doesn't match Host").
- Tempo real: `cardConfigs: [{ latestActivityCardConfig: { tableLimit: 3, includeSubsData: true } }]` →
  `cards[0].latestActivityCardData.datas[0]` com `timePeriod = ..._REALTIME_LAST_48_HOURS`,
  `mainChartData.dimensionColumns[0].timestamps.values` (48 horas, início de cada hora em ms) e
  `mainChartData.metricColumns[0].counts.values` (views por hora; a última é a hora corrente, parcial).
  1h = a última hora completa; 48h = a soma; Hoje = a soma das horas desde a meia-noite local.
- Métricas: `screenConfig.timePeriod.timePeriodType = ANALYTICS_TIME_PERIOD_TYPE_YEAR` (365 dias, um ponto por dia)
  e `cardConfigs: [{ keyMetricCardConfig: { metricTabConfigs: [EXTERNAL_VIEWS, EXTERNAL_WATCH_TIME,
  TOTAL_ESTIMATED_EARNINGS] } }]` → `keyMetricCardData.keyMetricTabs[i].primaryContent` com `total` e
  `mainSeries.datums` ({x: ms, y}). 7d e 30d = soma dos últimos 7 e 30 dias (bate com o Dotti: 324.727 e 459.268);
  tempo assistido em milissegundos (÷ 3.600.000 = horas: 182.794 ≈ "183 mil h"); ganhos em milésimos da moeda pedida
  em `screenConfig.currency` (`USD` → 11.406,49, igual ao Dotti).
- Outros tipos de período que a API aceita: WEEK, FOUR_WEEKS, QUARTER, LAST_6_MONTHS, YEAR, LIFETIME.
