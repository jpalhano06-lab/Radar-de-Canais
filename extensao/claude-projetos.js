// Lê os projetos do claude.ai com o login do Chrome e devolve as instruções e os arquivos de cada um (pedido do
// usuário em 2026-10-29: o Radar usar os projetos do Claude de verdade, em vez de uma cópia colada à mão). O Radar liga
// cada projeto a um agente (claude_projetos.py). Roda no background (a cada meia hora) e na página do claude.ai
// (claude-sync.js), que é o caminho garantido quando o background não consegue ler os cookies.
// As instruções do projeto vêm no campo `description`; `prompt_template` vem vazio, mas entra também se tiver texto.
// O agente excluído no Claude sai do Radar (2026-11-02): `vistos` leva o uuid de todo projeto achado, arquivado também;
// o Radar devolve os ligados que faltaram e cada um é aberto direto aqui. Só o que dá 404 em todas as organizações
// volta como excluído, para uma lista que veio pela metade não apagar agente nenhum.
// eslint-disable-next-line no-unused-vars
async function lerProjetosClaude(base = "https://claude.ai") {
  const ler = async (caminho) => {
    const r = await fetch(base + caminho, { credentials: "include" });
    if (!r.ok) throw new Error(r.status === 401 || r.status === 403 ? "Entre no claude.ai neste Chrome." : `claude.ai: erro ${r.status}`);
    return r.json();
  };
  const projetos = [], vistos = [], orgs = [];
  for (const org of await ler("/api/organizations")) {
    if (!(org.capabilities || []).includes("chat")) continue;
    orgs.push(org.uuid);
    for (const p of await ler(`/api/organizations/${org.uuid}/projects`)) {
      vistos.push(p.uuid);
      if (p.archived_at) continue;
      const d = await ler(`/api/organizations/${org.uuid}/projects/${p.uuid}`);
      const docs = await ler(`/api/organizations/${org.uuid}/projects/${p.uuid}/docs`).catch(() => []);
      projetos.push({
        uuid: p.uuid, nome: p.name, atualizado: d.updated_at,
        instrucoes: [d.prompt_template, d.description].filter((t) => t && t.trim()).join("\n\n").trim(),
        arquivos: (Array.isArray(docs) ? docs : []).map((x) => ({ nome: x.file_name, texto: x.content || "", criado: x.created_at })),
      });
    }
  }
  return { projetos, vistos, orgs };
}

// Lê, manda para o Radar e confere os que faltaram. `enviar(caminho, corpo)` devolve { dados } ou { erro }.
// eslint-disable-next-line no-unused-vars
async function sincronizarProjetosClaude(base, enviar) {
  const { projetos, vistos, orgs } = await lerProjetosClaude(base);
  const r = await enviar("/api/ext/projetos-claude", { projetos, vistos });
  const faltando = (r && r.dados && r.dados.faltando) || [];
  if (!faltando.length || !orgs.length) return r;
  const excluidos = [];
  for (const uuid of faltando) {
    let some = true;
    for (const org of orgs) {
      const resp = await fetch(`${base}/api/organizations/${org}/projects/${uuid}`, { credentials: "include" });
      if (resp.status !== 404) { some = false; break; }   // existe, ou deu outro erro: na dúvida, o agente fica
    }
    if (some) excluidos.push(uuid);
  }
  if (excluidos.length) {
    const x = await enviar("/api/ext/projetos-claude/excluidos", { uuids: excluidos });
    if (x && x.dados) r.dados.excluidos = x.dados.excluidos;
  }
  return r;
}
