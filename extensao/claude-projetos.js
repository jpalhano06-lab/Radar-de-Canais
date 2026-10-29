// Lê os projetos do claude.ai com o login do Chrome e devolve as instruções e os arquivos de cada um (pedido do
// usuário em 2026-10-29: o Radar usar os projetos do Claude de verdade, em vez de uma cópia colada à mão). O Radar liga
// cada projeto a um agente (claude_projetos.py). Roda no background (a cada meia hora) e na página do claude.ai
// (claude-sync.js), que é o caminho garantido quando o background não consegue ler os cookies.
// As instruções do projeto vêm no campo `description`; `prompt_template` vem vazio, mas entra também se tiver texto.
// eslint-disable-next-line no-unused-vars
async function lerProjetosClaude(base = "https://claude.ai") {
  const ler = async (caminho) => {
    const r = await fetch(base + caminho, { credentials: "include" });
    if (!r.ok) throw new Error(r.status === 401 || r.status === 403 ? "Entre no claude.ai neste Chrome." : `claude.ai: erro ${r.status}`);
    return r.json();
  };
  const projetos = [];
  for (const org of await ler("/api/organizations")) {
    if (!(org.capabilities || []).includes("chat")) continue;
    for (const p of await ler(`/api/organizations/${org.uuid}/projects`)) {
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
  return projetos;
}
