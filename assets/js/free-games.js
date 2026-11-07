/* GamerPower timestamps have no documented timezone: never infer one. */
(function () {
  'use strict';
  function storeOf(game) {
    const text = [game.title, game.description, game.instructions].join(' ');
    if (/prime gaming|amazon gaming|amazon prime|luna\.amazon|gaming\.amazon/i.test(text)) return 'Amazon Gaming';
    if (/Epic Games Store/i.test(game.platforms || '')) return 'Epic Games';
    return null;
  }
  function eligible(game) {
    return game.type === 'Game' && game.status === 'Active' && storeOf(game) &&
      !/free weekend|free trial|play for free until|beta access/i.test(game.title + ' ' + game.description);
  }
  if (typeof module !== 'undefined') module.exports = {storeOf, eligible};
  if (typeof document === 'undefined') return;
  const status = document.getElementById('status'), container = document.getElementById('games');
  let games = [], claimed = {}, seen = [], fresh = new Set(), storage = true;
  try { claimed = JSON.parse(localStorage.getItem('sqd-claimed') || '{}'); seen = JSON.parse(localStorage.getItem('sqd-seen') || '[]'); if (!claimed || Array.isArray(claimed) || typeof claimed !== 'object') claimed = {}; if (!Array.isArray(seen)) seen = []; } catch (_) { storage = false; }
  function element(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
  function render() {
    container.replaceChildren();
    const filtered = games.filter(g => (document.getElementById('store').value === 'all' || storeOf(g) === document.getElementById('store').value) && (!document.getElementById('hide').checked || !claimed[g.id]));
    for (const g of filtered) {
      const card = element('article', '');
      card.append(element('p', storeOf(g) + (fresh.has(g.id) ? ' · New since your last visit' : '')),
        element('h2', g.title), element('p', g.description),
        element('p', storeOf(g) === 'Amazon Gaming' ? 'Prime may be required · See claim terms' : 'Epic account required'),
        element('p', g.end_date && g.end_date !== 'N/A' ? 'Feed deadline: ' + g.end_date + ' (timezone unspecified; verify at store)' : 'Deadline not supplied — check store'));
      const link = element('a', 'View offer & claim ↗');
      try { const url = new URL(g.open_giveaway_url); if (url.protocol === 'https:' && url.hostname === 'www.gamerpower.com') { link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; card.append(link); } } catch (_) {}
      const button = element('button', claimed[g.id] ? 'Undo claimed mark' : 'Mark claimed'); button.type = 'button';
      button.onclick = () => { claimed[g.id] = !claimed[g.id]; try { localStorage.setItem('sqd-claimed', JSON.stringify(claimed)); } catch (_) { status.textContent = 'Browser storage unavailable; marks will not persist.'; } render(); };
      card.append(button); container.append(card);
    }
    if (!filtered.length) container.append(element('p', 'No matching offers in this feed. Check the official stores above for complete listings.'));
  }
  async function load() {
    const button = document.getElementById('refresh'); button.disabled = true;
    status.textContent = 'Checking giveaway feed…';
    try {
      const response = await fetch('https://www.gamerpower.com/api/giveaways?type=game', {signal: AbortSignal.timeout(20000)});
      if (!response.ok) throw Error('Feed unavailable');
      const data = await response.json();
      if (!Array.isArray(data) && !(data && Number(data.status) === 201)) throw Error('Unexpected feed response');
      games = (Array.isArray(data) ? data : []).filter(eligible);
      fresh = new Set(seen.length ? games.filter(g => !seen.includes(g.id)).map(g => g.id) : []);
      seen = [...new Set([...seen, ...games.map(g => g.id)])];
      try { localStorage.setItem('sqd-seen', JSON.stringify(seen)); } catch (_) { storage = false; }
      status.textContent = 'Feed checked ' + new Date().toLocaleString() + ' · ' + games.length + ' offers' + (storage ? '' : ' · Browser storage unavailable'); render();
    } catch (_) { status.textContent = 'Could not refresh offers. Any displayed results may be stale. Check the official stores above.'; }
    finally { button.disabled = false; }
  }
  document.getElementById('store').onchange = render; document.getElementById('hide').onchange = render; document.getElementById('refresh').onclick = load;
  load();
})();
