// Trava do "Sign out" (Sair) no menu da conta do YouTube e do YouTube Studio.
// Pegamos o clique antes do YouTube (fase de captura na janela) e só deixamos
// passar se o usuário confirmar. Se confirmar, repetimos o clique no mesmo item.
(() => {
  if (window.__radarTravaSair) return;
  window.__radarTravaSair = true;

  const TEXTO = /^(sign out|log out|sair|fazer logout|terminar sessão|cerrar sesión)$/i;
  const ITEM = 'a, [role="menuitem"], [role="option"], tp-yt-paper-item, ytd-compact-link-renderer, yt-list-item-view-model';
  let liberado = false;

  function itemDeSair(ev) {
    const caminho = ev.composedPath ? ev.composedPath() : [ev.target];
    for (const no of caminho.slice(0, 12)) {
      if (!(no instanceof Element)) continue;
      if (no.matches('a[href*="/logout"]')) return no;
      if (!no.matches(ITEM)) continue;
      const texto = (no.textContent || '').replace(/\s+/g, ' ').trim();
      if (TEXTO.test(texto)) return no;
    }
    return null;
  }

  function travar(ev) {
    if (liberado) return;
    const item = itemDeSair(ev);
    if (!item) return;
    ev.preventDefault();
    ev.stopImmediatePropagation();
    if (ev.type !== 'click') return;
    if (!window.confirm('Sair mesmo da conta do YouTube?')) return;
    liberado = true;
    try { item.click(); } finally { setTimeout(() => { liberado = false; }, 0); }
  }

  // O menu do YouTube reage ao clique (e ao "tap", que vem do clique); o pointerup
  // e o mouseup também são barrados para nenhum gesto disparar a saída sozinho.
  for (const tipo of ['click', 'pointerup', 'mouseup']) {
    window.addEventListener(tipo, travar, true);
  }
})();
