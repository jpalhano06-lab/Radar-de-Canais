# Robô no Radar (Partes A a D) — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao Radar a aba Integrações (APIs), a janela Nova produção com Entrada e fila automática, o Acompanhar novo
(etapas, Real × IA, log, Arquivos, Tags e descrição) e a página Custos.

**Architecture:** Quatro módulos Python novos e focados em `radar/` (`integracoes.py`, `fila.py`, `diagnostico.py`,
`custos.py`), cada um com funções puras testáveis e rotas finas no `servidor.py`. A fila mora no SQLite do Radar e um
vigia (thread no startup) puxa os pedidos para a fábrica dentro do limite. A tela segue o `app.js` de página única
(`MENU`, `ROTAS`, `api()`), com CSS no `estilo.css`.

**Tech Stack:** Python 3.11+, FastAPI, httpx, SQLite (`radar/banco.py`), pytest; JavaScript puro e CSS em `radar/web/`.

**Spec:** `docs/superpowers/specs/2026-10-18-robo-no-radar-design.md`

## Global Constraints

- Feito do zero no visual do Radar (escuro com marrom-dourado, `IDENTIDADE` no `app.js`); sem copiar código, texto ou visual do Dotti.
- Mexer em chaves, fila, produção e ajustes: só a administração (`Depends(dono_da_fabrica)`); rotas de chave também recusam `_de_fora(request)` (403).
- A chave inteira nunca volta para a tela nem para log: só a prévia `••••` + 4 últimos caracteres.
- Chaves da fábrica só por `GET/POST /api/config/chaves` da fábrica (`fabrica_api._pedir`); o Radar nunca escreve no `.env` da fábrica.
- Sem barra colorida na esquerda dos cartões; botão selecionado muda o fundo para `var(--acento)` e a letra nunca muda de cor sozinha. Botão novo com fundo da cor entra no bloco "preto e branco: gerado" do fim do `estilo.css`.
- Confirmações no próprio Radar (caixa na página), nunca `alert`/`confirm`/`prompt`.
- Textos da tela em português do Brasil.
- Testes sem rede: `uv run python -m pytest tests`.
- A pasta não é um repositório git: os passos "Registrar" rodam os testes e anotam a mudança no README; não há commit. (Se o usuário rodar `git init`, cada "Registrar" vira um commit.)

## Review Focus

- Fábrica desligada (porta 8080 fora): Integrações, Acompanhar e Custos abrem e dizem "fábrica desligada", sem erro 500; a fila espera sem perder pedidos. → testes nas Tasks 2, 5, 8.
- Servidor do Radar reiniciado no meio da fila: pedido em `escrevendo` ou `enviando` volta para `na_fila` no startup, sem ficar preso. → teste na Task 5.
- `.env` com comentários, linhas repetidas e chave sem valor: gravar uma chave não apaga nada além dela. → teste na Task 1.
- `cenas.json` ou `criacao.json` ausente ou pela metade (vídeo começando): o Diagnóstico mostra "pendente", não quebra. → teste na Task 7.
- `custos_reais.json` com linha sem `detalhes.provedor` ou sem `valor_usd`: entra em "outros" / vale 0. → teste na Task 9.

---

### Task 1: Integrações — catálogo, mescla do `.env` e mascaramento

**Files:**
- Create: `radar/integracoes.py`
- Modify: `radar/config.py` (função `recarregar()`)
- Test: `tests/test_integracoes.py`

**Interfaces:**
- Produces:
  - `SERVICOS: list[dict]` — cada um `{"id", "nome", "dono": "radar"|"fabrica", "env": str, "varias": bool, "obrigatoria": bool, "para_que": str, "limite": str, "onde": str (url)}`. Radar: `youtube` (`YOUTUBE_API_KEY`, varias), `groq` (`GROQ_API_KEY`, varias). Fábrica: `openrouter` (`OPENROUTER_API_KEY`), `genaipro` (`GENAIPRO_API`), `openai` (`OPENAI_API_KEY`), `kie` (`KIE_API_KEY`), `gemini` (`GEMINI_API_KEY`), `pexels` (`PEXELS_API_KEY`), `pixabay` (`PIXABAY_API_KEY`). Os nomes de env da fábrica são conferidos contra `CHAVES_CONHECIDAS` da fábrica no passo 3.
  - `mascarar(valor: str) -> str` → `"••••" + valor[-4:]`, `""` para vazio.
  - `mesclar_env(texto: str, novas: dict[str, str | None]) -> str` — `None` remove a linha.
  - `nomes_numerados(prefixo: str, ambiente: dict) -> list[str]` — `PREFIXO`, `PREFIXO2`, `PREFIXO3`… presentes, em ordem.
  - `gravar_radar(env: str, valor: str | None, arquivo: Path = config.RAIZ / ".env") -> None` — escreve e chama `config.recarregar()`.
  - `config.recarregar() -> None` — refaz `config.AMBIENTE` (mesmo objeto dict: `.clear()` + `.update(_ambiente())`).

- [ ] **Step 1: Write the failing tests**

```python
def test_mascarar():
    assert integracoes.mascarar("sk-or-123456789") == "••••6789"
    assert integracoes.mascarar("") == ""

def test_mesclar_troca_acrescenta_remove_e_mantem_comentarios():
    texto = "# chaves\nA=1\nB=2\nA=velho\n\n# fim\n"
    saida = integracoes.mesclar_env(texto, {"A": "novo", "C": "3", "B": None})
    assert saida.splitlines() == ["# chaves", "A=novo", "", "# fim", "C=3"]

def test_nomes_numerados():
    amb = {"YOUTUBE_API_KEY": "a", "YOUTUBE_API_KEY3": "c", "YOUTUBE_API_KEY2": "b", "GROQ_API_KEY": "g"}
    assert integracoes.nomes_numerados("YOUTUBE_API_KEY", amb) == ["YOUTUBE_API_KEY", "YOUTUBE_API_KEY2", "YOUTUBE_API_KEY3"]

def test_gravar_radar_escreve_e_recarrega(tmp_path, monkeypatch):
    env = tmp_path / ".env"; env.write_text("# x\nYOUTUBE_API_KEY=velha\n", encoding="utf-8")
    chamado = []
    monkeypatch.setattr(integracoes.config, "recarregar", lambda: chamado.append(1))
    integracoes.gravar_radar("YOUTUBE_API_KEY2", "nova", arquivo=env)
    assert env.read_text(encoding="utf-8").splitlines() == ["# x", "YOUTUBE_API_KEY=velha", "YOUTUBE_API_KEY2=nova"]
    assert chamado == [1]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_integracoes.py -v`
Expected: FAIL (`ModuleNotFoundError: radar.integracoes`)

- [ ] **Step 3: Implement** `SERVICOS`, `mascarar`, `mesclar_env` (linhas repetidas da mesma chave: fica a primeira, trocada; as outras saem), `nomes_numerados`, `gravar_radar` em `radar/integracoes.py` e `recarregar()` em `radar/config.py`. Conferir os nomes `env` da fábrica lendo `CHAVES_CONHECIDAS` em `C:/Users/Palhano/Documents/fabrica-videos/fabrica/api.py` e usar exatamente os de lá.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/test_integracoes.py -v`
Expected: PASS (4 testes)

- [ ] **Step 5: Registrar** — `uv run python -m pytest tests` todo verde.

---

### Task 2: Integrações — testar, saldos e rotas

**Files:**
- Modify: `radar/integracoes.py`, `radar/servidor.py`, `radar/banco.py` (tabela `saldos_informados`)
- Test: `tests/test_integracoes.py`

**Interfaces:**
- Consumes: Task 1 (`SERVICOS`, `mascarar`, `nomes_numerados`, `gravar_radar`); `fabrica_api._pedir`, `fabrica_api.SemFabrica`; `banco.cota` (unidades do dia por chave, já existente).
- Produces:
  - `estado() -> dict` → `{"servicos": [{"id", "nome", "dono", "obrigatoria", "para_que", "limite", "onde", "chaves": [{"env", "previa", "teste": {"ok": bool, "quando": str, "erro": str} | None}], "saldo": {"valor": float|None, "unidade": "US$"|"créditos"|"unidades", "texto": str, "informado": bool}}], "fabrica_ligada": bool}`
  - `testar(servico: str, indice: int = 0) -> dict` → `{"ok": bool, "erro": str}`; resultado guardado 1 hora em memória (`_TESTES[(servico, env)]`).
  - `gravar(servico: str, valor: str, indice: int | None = None) -> dict` (None = acrescentar, só se `varias`) e `remover(servico: str, indice: int) -> dict` — Radar via `gravar_radar`, fábrica via `POST /api/config/chaves` `{"chaves": {ENV: valor}}`. Ambos devolvem `estado()`.
  - `informar_saldo(servico: str, valor: float) -> dict` — grava em `saldos_informados(servico TEXT PRIMARY KEY, valor REAL, quando TEXT)`.
  - Rotas (todas `Depends(dono_da_fabrica)` + 403 se `_de_fora(request)`): `GET /api/integracoes`, `POST /api/integracoes/{servico}/testar` (`{"indice"}`), `POST /api/integracoes/{servico}` (`{"valor", "indice"}`), `DELETE /api/integracoes/{servico}/{indice}`, `POST /api/integracoes/{servico}/saldo` (`{"valor"}`).
- Testes de chamada (barata): youtube `videos?part=id&id=dQw4w9WgXcQ` (1 de cota); groq e openrouter `GET /models`; openrouter saldo `GET https://openrouter.ai/api/v1/credits`; genaipro saldo `GET /api/genaipro/creditos` da fábrica; kie saldo pela API de créditos da Kie; openai sem saldo (`informado`); pexels/pixabay `"Gratuito"`. Conferir o formato do corpo do `POST /api/config/chaves` lendo a fábrica antes de escrever.

- [ ] **Step 1: Write the failing tests**

```python
def test_estado_sem_fabrica_nao_quebra(monkeypatch):
    def sem(*a, **k): raise integracoes.fabrica_api.SemFabrica("desligada")
    monkeypatch.setattr(integracoes.fabrica_api, "_pedir", sem)
    e = integracoes.estado()
    assert e["fabrica_ligada"] is False
    assert any(s["id"] == "youtube" for s in e["servicos"])

def test_estado_nunca_devolve_a_chave_inteira(monkeypatch):
    monkeypatch.setitem(integracoes.config.AMBIENTE, "YOUTUBE_API_KEY", "AIzaSEGREDO1234")
    monkeypatch.setattr(integracoes.fabrica_api, "_pedir", lambda *a, **k: {"chaves": []})
    assert "SEGREDO" not in json.dumps(integracoes.estado())

def test_rota_recusa_quem_vem_pelo_tunel():
    from fastapi.testclient import TestClient
    from radar import servidor
    r = TestClient(servidor.app).get("/api/integracoes", headers={"cf-connecting-ip": "1.2.3.4"})
    assert r.status_code in (401, 403)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_integracoes.py -v`
Expected: FAIL (`estado` não existe)

- [ ] **Step 3: Implement** `estado`, `testar`, `gravar`, `remover`, `informar_saldo`, a tabela no `ESQUEMA` e as cinco rotas. `estado()` pega `SemFabrica` e devolve os cartões da fábrica com `"fabrica_ligada": False`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/test_integracoes.py -v`
Expected: PASS (7 testes)

- [ ] **Step 5: Registrar** — testes todos verdes.

---

### Task 3: Integrações — a tela

**Files:**
- Modify: `radar/web/app.js` (`MENU`, `DICAS`, `AJUDA`, `ROTAS`, função `integracoes()`), `radar/web/estilo.css`

**Interfaces:**
- Consumes: as rotas da Task 2.
- Produces: rota `#/integracoes`; item "Integrações" no fim de Ferramentas (só para `EU.admin`, como `admin`).

- [ ] **Step 1: Implement** `async function integracoes()`: título "Integrações", linha de "Para que serve" (`AJUDA.integracoes`); bloco **Saldos** (um cartão por serviço com `saldo.texto`, "Informar saldo" abrindo um campo na própria página quando `informado`); bloco **Chaves** (cartão por serviço: nome, selo obrigatória/opcional, para que serve, cada chave com prévia + status + Testar/Trocar/Remover, "+ Adicionar" quando `varias`, "Como funciona o limite", link "Onde pegar a chave"); bloco **Contas** (o estado do `/api/youtube/status`). Trocar/Adicionar abre um campo `type=password` no cartão com Salvar e Cancelar; Remover pede confirmação no cartão ("Remover esta chave? Sim / Não"). Com `fabrica_ligada: false`, os cartões da fábrica mostram "Fábrica desligada" e ficam sem botões.

- [ ] **Step 2: Verificar no navegador** — ligar com `uv run python -m radar servidor`, abrir `http://127.0.0.1:8400/#/integracoes` e conferir: saldos aparecem; Testar a chave do YouTube mostra ✓; Adicionar uma chave falsa do Groq mostra "falhou" no Testar e Remover tira; nenhuma chave inteira no HTML (`document.body.innerText`). Conferir também no tema Preto e branco.

- [ ] **Step 3: Registrar** — anotar no README a seção "Integrações (2026-10-18)".

---

### Task 4: Fila — tabela, estados e o tamanho em caracteres

**Files:**
- Create: `radar/fila.py`
- Modify: `radar/banco.py` (tabelas `producoes_fila`, `ajustes`; coluna `ideal_para` em `projetos_roteiro`)
- Test: `tests/test_fila.py`

**Interfaces:**
- Consumes: `banco.um/todos/executar/agora`; `tempo.ritmo(usuario_id, perfil, lingua) -> {"ppm": int, ...}`.
- Produces:
  - `ESTADOS = ("entrada", "na_fila", "escrevendo", "sua_vez", "enviando", "produzindo", "entregue", "erro", "cancelado")`
  - `CARACTERES_POR_PALAVRA = 5.9`, `MIN_CARACTERES = 1000`, `MAX_CARACTERES = 80000`
  - `minutos_de(caracteres: int, ppm: int) -> float` e `caracteres_de(minutos: float, ppm: int) -> int` (arredonda para dezena).
  - `criar(usuario_id: int, pedido: dict, comecar: bool) -> dict` — campos do pedido: `titulo` (obrigatório), `link`, `canal_id`, `agente_id`, `lingua`, `caracteres`, `roteiro_manual`, `nicho`, `observacao`, `ia_maxima` (None, 0, 0.25, 0.5), `revisar` (bool). Estado inicial `na_fila` se `comecar`, senão `entrada`. Recusa (`ValueError`) título vazio e caracteres fora de 1000–80000 (sem roteiro manual).
  - `listar(usuario_id: int) -> list[dict]`, `item(usuario_id: int, fid: int) -> dict | None`
  - `mudar(fid: int, estado: str, **campos) -> None` (valida `estado in ESTADOS`)
  - `comecar(usuario_id, fid)` (entrada → na_fila), `aprovar(usuario_id, fid)` (sua_vez → `na_fila` com `aprovado=1`, para o vigia enviar na próxima vaga), `tentar(usuario_id, fid)` (erro → na_fila), `excluir(usuario_id, fid)` (→ cancelado; devolve o `projeto` da fábrica, se houver)
  - `limite() -> int` e `definir_limite(n: int) -> int` — tabela `ajustes(chave TEXT PRIMARY KEY, valor TEXT)`, chave `fila_limite`, padrão 2, aceita 1, 2, 3, 4, 6, 8.
- Tabela `producoes_fila`: `id INTEGER PRIMARY KEY, usuario_id INTEGER, criado TEXT, atualizado TEXT, estado TEXT, ordem INTEGER, pedido TEXT (json), roteiro TEXT DEFAULT '', projeto TEXT DEFAULT '', aprovado INTEGER DEFAULT 0, erro TEXT DEFAULT '', passo TEXT DEFAULT ''`.

- [ ] **Step 1: Write the failing tests** (usar um banco temporário: `monkeypatch.setattr(banco, "ARQUIVO", tmp_path / "t.db"); monkeypatch.setattr(banco, "_CON", None)`, numa fixture)

```python
def test_conta_de_tamanho():
    assert fila.minutos_de(10620, 150) == pytest.approx(12.0, abs=0.1)
    assert fila.caracteres_de(12, 150) == 10620

def test_criar_comecar_e_entrada(db):
    a = fila.criar(1, {"titulo": "T", "caracteres": 10620}, comecar=True)
    b = fila.criar(1, {"titulo": "U", "caracteres": 10620}, comecar=False)
    assert (a["estado"], b["estado"]) == ("na_fila", "entrada")
    fila.comecar(1, b["id"]); assert fila.item(1, b["id"])["estado"] == "na_fila"

def test_recusa_titulo_vazio_e_tamanho_fora(db):
    with pytest.raises(ValueError): fila.criar(1, {"titulo": " ", "caracteres": 5000}, True)
    with pytest.raises(ValueError): fila.criar(1, {"titulo": "T", "caracteres": 500}, True)
    assert fila.criar(1, {"titulo": "T", "caracteres": 0, "roteiro_manual": "texto"}, True)["estado"] == "na_fila"

def test_limite(db):
    assert fila.limite() == 2
    assert fila.definir_limite(4) == 4
    with pytest.raises(ValueError): fila.definir_limite(5)

def test_outro_usuario_nao_mexe(db):
    a = fila.criar(1, {"titulo": "T", "caracteres": 5000}, False)
    assert fila.item(2, a["id"]) is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_fila.py -v`
Expected: FAIL (`ModuleNotFoundError: radar.fila`)

- [ ] **Step 3: Implement** `radar/fila.py`, as tabelas no `ESQUEMA` e `"projetos_roteiro": {"ideal_para": "TEXT NOT NULL DEFAULT ''"}` em `COLUNAS_NOVAS`. Onde o agente é criado/editado hoje (`POST /api/projetos` e a tela do agente no `app.js`), aceitar e mostrar `ideal_para`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/test_fila.py -v`
Expected: PASS (5 testes)

- [ ] **Step 5: Registrar** — testes todos verdes.

---

### Task 5: Fila — o vigia

**Files:**
- Modify: `radar/fila.py`, `radar/servidor.py` (startup e rotas da fila)
- Test: `tests/test_fila.py`

**Interfaces:**
- Consumes: Task 4; `roteiro_claude.gerar(usuario_id, titulo, link, minutos, lingua, projeto_id, observacoes, perfil, canal, aviso) -> {"nome", ...}`, `roteiro_claude.manual(usuario_id, titulo, texto, link, minutos, lingua, canal) -> {"nome", ...}`, `roteiro_claude.enviar(usuario_id, nome, perfil) -> {"projeto", ...}`, `fabrica_api.produzir(nome, confirmar=True)`, `fabrica_api.producoes() -> {"andamento": [...], "prontos": [...]}`, `producao.config(usuario_id, canal_id) -> {"perfil", "projeto_roteiro_id", "lingua", "canal", ...}`.
- Produces:
  - `passo(fabrica=None, roteirista=None) -> list[int]` — uma volta do vigia; devolve os ids que mudaram. `fabrica` e `roteirista` são objetos injetáveis (padrão: os módulos reais) com `producoes()`, `produzir(nome, confirmar)`, `enviar(usuario_id, nome, perfil)`, `gerar(...)`, `manual(...)`.
  - Regras de uma volta:
    1. `produzindo` cujo projeto está em `prontos` → `entregue`; cujo projeto saiu da fábrica → `erro` ("o vídeo sumiu da fábrica").
    2. Vagas = `limite()` − (`enviando` + `produzindo` + vídeos em `andamento` da fábrica que não são da fila).
    3. Para cada `na_fila` pela `ordem` (também os aprovados): sem roteiro → `escrevendo` e gera em thread (ao terminar: `revisar` e não `aprovado` → `sua_vez`; senão volta `na_fila` com `roteiro`). Com roteiro e vaga → `enviando`: `enviar` (grava `ia_maxima` no `projeto.json` da fábrica, ao lado do `titulo_entrega`), `produzir(projeto, confirmar=True)` → `produzindo`; consome uma vaga.
    4. Qualquer exceção no pedido → `erro` com a mensagem; `SemFabrica` não vira erro: o pedido fica onde está e a volta termina.
  - `reparar() -> None` — no startup: `escrevendo` e `enviando` voltam para `na_fila` (o roteiro já gravado é mantido).
  - `iniciar_vigia() -> None` — `reparar()` e thread daemon com `passo()` a cada 20 s.
  - Rotas: `POST /api/fila` (`{"pedido": {...}, "comecar": bool}`), `GET /api/fila`, `POST /api/fila/{fid}/comecar`, `POST /api/fila/{fid}/aprovar`, `POST /api/fila/{fid}/tentar`, `DELETE /api/fila/{fid}` (se houver projeto, `DELETE /api/projetos/{nome}` na fábrica), `GET /api/fila/ajustes`, `POST /api/fila/ajustes` (`{"limite"}`). Escrita com `Depends(dono_da_fabrica)`.

- [ ] **Step 1: Write the failing tests** (fábrica e roteirista de mentira; `gerar` síncrono no teste: `fila.passo` aceita `em_thread=False`)

```python
class Fabrica:
    def __init__(self, andamento=(), prontos=()): self.a, self.p, self.produzidos = list(andamento), list(prontos), []
    def producoes(self): return {"andamento": [{"nome": n} for n in self.a], "prontos": [{"nome": n} for n in self.p]}
    def produzir(self, nome, confirmar): assert confirmar; self.produzidos.append(nome); self.a.append(nome)

def test_vigia_respeita_o_limite(db):
    fila.definir_limite(1)
    ids = [fila.criar(1, {"titulo": f"T{i}", "caracteres": 0, "roteiro_manual": "x"}, True)["id"] for i in range(3)]
    fab = Fabrica(); fila.passo(fabrica=fab, roteirista=Roteirista(), em_thread=False)
    estados = [fila.item(1, i)["estado"] for i in ids]
    assert estados.count("produzindo") == 1 and estados.count("na_fila") == 2

def test_revisao_para_em_sua_vez_e_aprovar_segue(db):
    a = fila.criar(1, {"titulo": "T", "caracteres": 5000, "revisar": True}, True)
    fila.passo(fabrica=Fabrica(), roteirista=Roteirista(), em_thread=False)
    assert fila.item(1, a["id"])["estado"] == "sua_vez"
    fila.aprovar(1, a["id"]); fila.passo(fabrica=Fabrica(), roteirista=Roteirista(), em_thread=False)
    assert fila.item(1, a["id"])["estado"] == "produzindo"

def test_entregue_quando_fica_pronto(db): ...   # produzindo + projeto em prontos → entregue
def test_fabrica_desligada_nao_vira_erro(db): ...  # producoes() levanta SemFabrica → estado continua na_fila
def test_erro_e_tentar_de_novo(db): ...          # enviar levanta RuntimeError("x") → erro "x"; tentar → na_fila
def test_reparar_depois_de_reiniciar(db):
    a = fila.criar(1, {"titulo": "T", "caracteres": 5000}, True); fila.mudar(a["id"], "enviando")
    fila.reparar(); assert fila.item(1, a["id"])["estado"] == "na_fila"
```

(`Roteirista` de mentira: `gerar`/`manual` devolvem `{"nome": "r1"}`; `enviar` devolve `{"projeto": "p-" + nome}`. Os três testes com `...` seguem o mesmo molde, com a asserção escrita no comentário.)

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_fila.py -v`
Expected: FAIL (`passo` não existe)

- [ ] **Step 3: Implement** `passo`, `reparar`, `iniciar_vigia` e as rotas; chamar `fila.iniciar_vigia()` no `@app.on_event("startup")` existente (`servidor.py:1834`). Minutos para o `gerar` = `round(minutos_de(caracteres, ritmo["ppm"]))`, com o `ritmo` do perfil do canal.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest tests/test_fila.py -v`
Expected: PASS (11 testes)

- [ ] **Step 5: Registrar** — testes todos verdes.

---

### Task 6: Nova produção — a janela

**Files:**
- Modify: `radar/web/app.js` (função `novaProducao()`, botão no topo, atalhos), `radar/web/estilo.css`, `radar/servidor.py` (rota do custo estimado)

**Interfaces:**
- Consumes: rotas da Task 5; `/api/meus-canais` (canais), `/api/producao/{canal_id}` (config do canal), `/api/projetos` (agentes, agora com `ideal_para`), `/api/roteiros/ritmo` (ppm), `/api/titulo-do-video`.
- Produces: `GET /api/fila/estimativa?canal_id=&minutos=` → `{"usd": float | None, "base": "canal"|"geral"|null}` (média US$/min dos entregues, de `fabrica_api.custo`, guardada 1 hora); `function novaProducao()` aberta pelo botão "+ Nova produção" do topo e por Ctrl+N.

- [ ] **Step 1: Write the failing test** para a estimativa

```python
def test_estimativa_pela_media_do_canal():
    entregues = [{"canal": "A", "minutos": 30, "usd": 3.0}, {"canal": "A", "minutos": 10, "usd": 1.0}, {"canal": "B", "minutos": 10, "usd": 5.0}]
    assert fila.estimativa(entregues, "A", 12) == {"usd": 1.2, "base": "canal"}
    assert fila.estimativa(entregues, "C", 10) == {"usd": round(9 / 50 * 10, 2), "base": "geral"}
    assert fila.estimativa([], "A", 10) == {"usd": None, "base": None}
```

- [ ] **Step 2: Run to verify it fails** — `uv run python -m pytest tests/test_fila.py::test_estimativa_pela_media_do_canal -v` → FAIL.

- [ ] **Step 3: Implement** `fila.estimativa(entregues: list[dict], canal: str, minutos: float) -> dict` e a rota. Depois a janela no `app.js`, nos campos e na ordem da tabela da Parte B do spec: duas colunas; chips de canal (escolher preenche agente, idioma e tamanho pelo `producao/{canal_id}`); tamanho com campo em caracteres + "≈ N min · ~N palavras" + atalhos 8/10/12/15/20/25/30 min, convertendo pelo ppm do canal (`CARACTERES_POR_PALAVRA = 5.9` também no JS); "O Claude escreve" / "Já tenho o roteiro"; Máximo de IA com o aviso "em breve na fábrica"; revisar; prévia "Assim ele entra na fila" com o custo; botões Salvar na Entrada / Criar e começar; Ctrl+Enter = Criar e começar; Esc fecha. Erro da rota aparece dentro da janela.

- [ ] **Step 4: Run the test** — PASS. **Verificar no navegador**: abrir pelo botão e por Ctrl+N; escolher um canal muda idioma e tamanho; 12 min mostra ~10.620 caracteres para 150 ppm; "Salvar na Entrada" cria em `entrada` (conferir em `/api/fila`); a janela funciona em 375 px de largura.

- [ ] **Step 5: Registrar** — README: seção "Nova produção e fila (2026-10-18)".

---

### Task 7: Diagnóstico — Real × IA, etapas e log

**Files:**
- Create: `radar/diagnostico.py`
- Test: `tests/test_diagnostico.py`

**Interfaces:**
- Consumes: a pasta do projeto (`config.FABRICA / "projetos" / nome`): `cenas.json`, `criacao.json`.
- Produces:
  - `FONTES_REAIS = {"pexels", "pixabay", "wikimedia", "unsplash", "inaturalist", "nypl", "youtube", "storyblocks", "acervo", "openverse"}`; `FONTES_ANIMACAO = {"animation_ai", "motion_ia"}`
  - `origem_da_cena(cena: dict) -> "real" | "animacao" | "imagem_ia" | "pendente"` — `midia.fonte` em animação → animacao; em reais → real; sem `midia` com `tipo == "ia"` ou `sem_midia_real` → imagem_ia; senão pendente.
  - `contagem(pasta: Path) -> {"total": int, "real": int, "imagem_ia": int, "animacao": int, "pendente": int, "pct_ia": float}` (`pct_ia` = (imagem_ia + animacao) / (total − pendente) × 100, 0 sem cenas).
  - `etapas(pasta: Path, status: dict) -> {"lista": [{"id", "nome", "estado": "feita"|"agora"|"falta", "tempo": str}], "mensagem": str, "passo": int, "total": int}` — as 6 etapas `roteiro, narracao, cenas, material, imagens, montagem`; tempos tirados da linha "Tempo por etapa:" do log.
  - `log(pasta: Path, tipo: str = "todos") -> list[{"texto": str, "tipo": "info"|"aviso"|"erro"|"concluido"}]` — classificação pelo texto (`erro`/`falhou` → erro; `aviso`/`⚠` → aviso; `pronto`/`concluído`/`✓` → concluido).
- Arquivo ausente ou JSON pela metade → resultado vazio com tudo `pendente`, nunca exceção.

- [ ] **Step 1: Write the failing tests**

```python
def test_origem_da_cena():
    assert diagnostico.origem_da_cena({"midia": {"fonte": "pexels"}}) == "real"
    assert diagnostico.origem_da_cena({"midia": {"fonte": "animation_ai"}}) == "animacao"
    assert diagnostico.origem_da_cena({"tipo": "video_real", "sem_midia_real": True}) == "imagem_ia"
    assert diagnostico.origem_da_cena({"tipo": "ia"}) == "imagem_ia"
    assert diagnostico.origem_da_cena({"tipo": "video_real"}) == "pendente"

def test_contagem(tmp_path):
    cenas = [{"midia": {"fonte": "pexels"}}] * 6 + [{"tipo": "ia"}] * 3 + [{"midia": {"fonte": "animation_ai"}}] + [{"tipo": "video_real"}] * 2
    (tmp_path / "cenas.json").write_text(json.dumps({"cenas": cenas}), encoding="utf-8")
    c = diagnostico.contagem(tmp_path)
    assert c == {"total": 12, "real": 6, "imagem_ia": 3, "animacao": 1, "pendente": 2, "pct_ia": 40.0}

def test_arquivos_ausentes_ou_quebrados(tmp_path):
    assert diagnostico.contagem(tmp_path)["total"] == 0
    (tmp_path / "criacao.json").write_text('{"logs": ["a"', encoding="utf-8")
    assert diagnostico.log(tmp_path) == []

def test_log_filtra(tmp_path):
    (tmp_path / "criacao.json").write_text(json.dumps({"logs": ["narração pronta", "aviso: cota", "erro ao baixar", "lendo"]}), encoding="utf-8")
    assert [l["tipo"] for l in diagnostico.log(tmp_path)] == ["concluido", "aviso", "erro", "info"]
    assert len(diagnostico.log(tmp_path, "erro")) == 1
```

- [ ] **Step 2: Run to verify they fail** — `uv run python -m pytest tests/test_diagnostico.py -v` → FAIL.

- [ ] **Step 3: Implement** `radar/diagnostico.py`. Conferir a regra com o projeto real mais recente da fábrica: a contagem deve bater com a linha "Origem: N escolhida, N IA, N Animation IA" do `criacao.json` (lá: 86 / 71 / 51 em 208 cenas). Se não bater, ajustar `origem_da_cena` e acrescentar o caso ao teste.

- [ ] **Step 4: Run to verify they pass** — PASS (4 testes).

- [ ] **Step 5: Registrar** — testes todos verdes.

---

### Task 8: Acompanhar novo — rotas e tela

**Files:**
- Modify: `radar/servidor.py`, `radar/fabrica_api.py`, `radar/web/app.js` (substituir `acompanhar()` em `app.js:1258`), `radar/web/estilo.css`
- Test: `tests/test_diagnostico.py`

**Interfaces:**
- Consumes: Task 4/5 (`fila.listar`, `fila.limite`, `fila.aprovar`, `fila.tentar`, `fila.excluir`), Task 7, `fabrica_api.producoes()`, `fabrica_api._pedir`.
- Produces:
  - `fabrica_api.status(nome) -> dict` (`GET /api/projetos/{nome}/status`), `fabrica_api.publicacao(nome) -> dict` e `fabrica_api.gerar_publicacao(nome) -> dict` (`GET`/`POST /api/projetos/{nome}/publicacao`), `fabrica_api.liberar_pago(nome) -> dict` (`POST /pago {"liberar": true}`), `fabrica_api.apagar(nome) -> dict` (`DELETE /api/projetos/{nome}`).
  - `diagnostico.blocos(fila_itens: list[dict], producoes: dict) -> {"precisa_voce": [...], "produzindo": [...], "na_fila": [...], "entrada": [...], "numeros": {"produzindo", "na_fila", "precisa_voce"}}` — precisa_voce = fila em `sua_vez`/`erro` + produções da fábrica com `precisa_voce`; produzindo inclui as da fábrica fora da fila (sem duplicar o mesmo projeto).
  - Rotas: `GET /api/acompanhar` (blocos + `limite` + `fabrica_ligada`), `GET /api/acompanhar/{nome}` (cabeçalho + `etapas`), `GET /api/acompanhar/{nome}/diagnostico` (`contagem` + `log`), `GET /api/acompanhar/{nome}/log.txt` (texto puro, download), `GET/POST /api/acompanhar/{nome}/publicacao`, `POST /api/acompanhar/{nome}/pago`, `DELETE /api/acompanhar/{nome}` (apaga na fábrica e cancela na fila). Escrita com `Depends(dono_da_fabrica)`.

- [ ] **Step 1: Write the failing test**

```python
def test_blocos_sem_duplicar_e_precisa_voce():
    fila_itens = [{"id": 1, "estado": "produzindo", "projeto": "p1"}, {"id": 2, "estado": "sua_vez", "projeto": ""},
                  {"id": 3, "estado": "na_fila", "projeto": ""}, {"id": 4, "estado": "entrada", "projeto": ""}]
    prod = {"andamento": [{"nome": "p1"}, {"nome": "p9", "precisa_voce": True}], "prontos": []}
    b = diagnostico.blocos(fila_itens, prod)
    assert b["numeros"] == {"produzindo": 2, "na_fila": 1, "precisa_voce": 2}
    assert [x.get("projeto") or x.get("nome") for x in b["produzindo"]] == ["p1", "p9"]
```

- [ ] **Step 2: Run to verify it fails** — FAIL.

- [ ] **Step 3: Implement** `blocos`, as funções do `fabrica_api` e as rotas (`SemFabrica` → `fabrica_ligada: false` e listas só da fila). Depois a tela `acompanhar()` como na Parte C do spec: topo com "Fábrica ligada · N ao mesmo tempo ▾" (`POST /api/fila/ajustes`) e os três números; esquerda com os quatro blocos, busca e filtro por canal; direita com cabeçalho e as abas Acompanhamento / Diagnóstico (barra Real × IA, filtro do log, Baixar log) / Arquivos (reaproveitar as funções dos Resultados: assistir, legenda, thumbnails, shorts, abrir pasta) / Tags e descrição (Copiar e Gerar). Ações: Aprovar roteiro, Tentar de novo, Liberar modelo pago, Começar (Entrada), Parar e apagar com confirmação na página. Atualizar o vídeo aberto a cada 5 s e a lista a cada 20 s; parar os relógios ao sair da rota. Usar `notificar()` (já existente) para entregue, precisa de você e erro, uma vez por mudança.

- [ ] **Step 4: Run the test** — PASS. **Verificar no navegador** com um vídeo real em produção: etapas avançam, a barra Real × IA mostra números, o log filtra e baixa, Tags e descrição mostra a da fábrica; com a fábrica desligada a página abre com o aviso.

- [ ] **Step 5: Registrar** — README: seção "Acompanhar novo (2026-10-18)".

---

### Task 9: Custos

**Files:**
- Create: `radar/custos.py`
- Modify: `radar/servidor.py`, `radar/web/app.js` (`MENU` Meu trabalho, `ROTAS`, função `custos()`), `radar/web/estilo.css`
- Test: `tests/test_custos.py`

**Interfaces:**
- Consumes: `custos_reais.json` de cada pasta em `config.FABRICA / "projetos"`; o canal do vídeo pela mesma regra dos Resultados (`resultado_canal` por cima do perfil, `fabrica_api.producoes()` → `canal`); a duração (`duracao` do mesmo `producoes()`).
- Produces:
  - `linhas(pasta: Path) -> list[dict]` — lê o arquivo (ausente ou quebrado → `[]`); cada item `{"quando", "categoria", "provedor", "usd"}` (`provedor` = `detalhes.provedor` ou `"outros"`; `usd` = `valor_usd` ou 0).
  - `resumo(videos: list[dict], dias: int | None) -> dict` — `videos` = `[{"nome", "titulo", "canal", "criado", "minutos", "linhas": [...]}]`; devolve `{"total", "videos", "media_video", "usd_por_minuto", "por_provedor": {prov: usd}, "por_categoria": {cat: usd}, "por_canal": [{"canal", "total", "media"}], "lista": [{"nome", "titulo", "canal", "criado", "minutos", "usd", "usd_por_minuto"}]}`, só os vídeos com `criado` dentro de `dias` (None = tudo); valores arredondados em 2 casas.
  - `detalhe(pasta: Path) -> {"por_categoria", "por_provedor", "imagens_ia": int}`
  - Rotas: `GET /api/custos?dias=&canal=&provedor=` (filtros só na lista; resumo do período inteiro), `GET /api/custos/{nome}`. Leitura guardada em memória pela data de modificação do arquivo.

- [ ] **Step 1: Write the failing tests**

```python
def test_linhas_toleram_campos_faltando(tmp_path):
    (tmp_path / "custos_reais.json").write_text(json.dumps([
        {"quando": "2026-10-18T00:00:00", "categoria": "narracao", "valor_usd": 0.3, "detalhes": {"provedor": "genaipro"}},
        {"quando": "2026-10-18T00:01:00", "categoria": "imagem", "detalhes": {}}]), encoding="utf-8")
    assert [(l["provedor"], l["usd"]) for l in custos.linhas(tmp_path)] == [("genaipro", 0.3), ("outros", 0)]
    assert custos.linhas(tmp_path / "nada") == []

def test_resumo():
    l = lambda prov, cat, usd: {"quando": "", "categoria": cat, "provedor": prov, "usd": usd}
    videos = [{"nome": "a", "titulo": "A", "canal": "X", "criado": "2026-10-17", "minutos": 30, "linhas": [l("genaipro", "narracao", 1.0), l("openrouter", "imagem", 2.0)]},
              {"nome": "b", "titulo": "B", "canal": "Y", "criado": "2026-10-16", "minutos": 10, "linhas": [l("openrouter", "imagem", 1.0)]}]
    r = custos.resumo(videos, None)
    assert (r["total"], r["videos"], r["media_video"], r["usd_por_minuto"]) == (4.0, 2, 2.0, 0.1)
    assert r["por_provedor"] == {"genaipro": 1.0, "openrouter": 3.0}
    assert r["por_canal"][0] == {"canal": "X", "total": 3.0, "media": 3.0}
```

- [ ] **Step 2: Run to verify they fail** — `uv run python -m pytest tests/test_custos.py -v` → FAIL.

- [ ] **Step 3: Implement** `radar/custos.py` e as rotas. Depois a tela `custos()` (rota `#/custos`, item "Custos" depois de "Resultados" em Meu trabalho): período 7/30/90/tudo; números do resumo; barras por provedor e por categoria (CSS simples, sem biblioteca); tabela por vídeo com filtros de canal e provedor, busca por título, clicar abre o detalhe; por canal. Vídeo em produção mostra "medindo…".

- [ ] **Step 4: Run to verify they pass** — PASS (2 testes). **Verificar no navegador**: o total do período bate com a soma dos custos dos Resultados para os mesmos vídeos.

- [ ] **Step 5: Registrar** — README: seção "Custos (2026-10-18)".

---

### Task 10: Conferência final

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** `uv run python -m pytest tests -v` — tudo verde (os 4 arquivos antigos + `test_integracoes`, `test_fila`, `test_diagnostico`, `test_custos`).
- [ ] **Step 2:** Ligar o Radar e percorrer, no navegador: Integrações → Nova produção (Salvar na Entrada, depois Começar) → Acompanhar (o pedido passa por escrevendo → produzindo; a barra Real × IA aparece quando as cenas existem) → Custos. Conferir em 375 px e no tema Preto e branco (o bloco "preto e branco: gerado" do `estilo.css` inclui os botões novos).
- [ ] **Step 3:** Pedido de fora (`cf-connecting-ip`) nas rotas de escrita novas devolve 401/403.
- [ ] **Step 4:** README com o menu atualizado (Meu trabalho: … Acompanhar, Resultados, Custos; Ferramentas: … Integrações) e a observação de que o Máximo de IA só vale depois da Parte E (plano próprio, na fábrica).
