// Financial values stay decimal strings. No browser totals or browser storage.
(() => {
  const el = id => document.getElementById(id);
  let snapshot = null, generation = 0, controller = null;
  const amounts = ['total-value','investment-value','available-cash','unrealised-pnl','cash-in-pies','reserved-cash','investment-cost','realised-pnl'];
  function decimal(value, currency) {
    if (typeof value !== 'string' || !/^-?\d+(\.\d+)?$/.test(value)) return 'Unavailable';
    const negative = value.startsWith('-');
    const [whole, fraction] = (negative ? value.slice(1) : value).split('.');
    const formatted = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (fraction === undefined ? '' : '.' + fraction);
    return (negative ? '−' : '') + (currency === 'GBP' ? '£' : '') + formatted + (currency && currency !== 'GBP' ? ' ' + currency : '');
  }
  function compare(a, b) {
    if (a == null) return b == null ? 0 : -1;
    if (b == null) return 1;
    const parts = [a,b].map(x => x.split('.'));
    const scale = Math.max(parts[0][1]?.length || 0, parts[1][1]?.length || 0);
    const [x,y] = parts.map(([whole, fraction='']) => BigInt(whole + fraction.padEnd(scale, '0')));
    return x < y ? -1 : x > y ? 1 : 0;
  }
  function clear() {
    generation++; controller?.abort(); snapshot = null;
    amounts.forEach(id => el(id).textContent = '—');
    el('holdings-body').replaceChildren(); el('holding-count').textContent = '';
    el('snapshot-time').textContent = '—'; el('snapshot-status').textContent = ''; el('refresh-status').textContent = '';
    el('holding-search').value = ''; document.body.classList.remove('snapshot-ready');
  }
  function renderHoldings() {
    const query = el('holding-search').value.trim().toLowerCase();
    const rows = (snapshot?.positions || []).filter(row => `${row.ticker} ${row.name || ''}`.toLowerCase().includes(query));
    rows.sort(el('holding-sort').value === 'name' ? (a,b) => (a.name || a.ticker).localeCompare(b.name || b.ticker) : (a,b) => compare(b.current_value,a.current_value));
    const fragment = document.createDocumentFragment();
    for (const row of rows) {
      const tr = document.createElement('tr');
      const name = document.createElement('td'); name.textContent = row.name || row.ticker;
      const ticker = document.createElement('small'); ticker.textContent = row.ticker; name.append(ticker); tr.append(name);
      for (const value of [decimal(row.quantity), decimal(row.current_price,row.instrument_currency), decimal(row.current_value,row.account_currency), decimal(row.total_cost,row.account_currency), decimal(row.unrealized_profit_loss,row.account_currency)]) {
        const cell = document.createElement('td'); cell.textContent = value; tr.append(cell);
      }
      fragment.append(tr);
    }
    el('holdings-body').replaceChildren(fragment);
    el('holding-count').textContent = `${rows.length} of ${snapshot?.positions.length || 0} holdings`;
  }
  async function load() {
    generation++; controller?.abort(); const version = generation; controller = new AbortController();
    el('snapshot-status').textContent = 'Loading saved broker snapshot…';
    try {
      const response = await fetch('/api/v1/portfolio/snapshot', { credentials:'same-origin', cache:'no-store', redirect:'error', signal:controller.signal });
      if (version !== generation) return;
      if ([401,403].includes(response.status)) { clear(); window.dispatchEvent(new Event('meridian-session-ended')); return; }
      if (response.status === 404) { el('snapshot-status').textContent = 'No saved snapshot is available yet.'; return; }
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (version !== generation) return;
      if (data.source !== 'trading212' || data.basis !== 'broker_reported' || !Array.isArray(data.positions)) throw new Error('invalid');
      snapshot = data;
      const values = [data.total_value,data.investments.currentValue,data.cash_components.availableToTrade,data.investments.unrealizedProfitLoss,data.cash_components.inPies,data.cash_components.reservedForOrders,data.investments.totalCost,data.investments.realizedProfitLoss];
      amounts.forEach((id,index) => el(id).textContent = decimal(values[index],data.currency));
      const when = value => new Date(value).toLocaleString('en-GB',{timeZone:'Europe/London',timeZoneName:'short'});
      el('snapshot-time').textContent = `Trading 212 · ${data.environment.toUpperCase()} account · Account captured ${when(data.account_retrieval.retrieval_completed_at)}; holdings captured ${when(data.positions_retrieval.retrieval_completed_at)}.`;
      el('snapshot-status').textContent = ''; document.body.classList.add('snapshot-ready'); renderHoldings();
      await health(version);
    } catch (error) {
      if (version === generation && error.name !== 'AbortError') { el('snapshot-status').textContent = snapshot ? 'Refresh failed. Last successful snapshot remains displayed.' : 'The saved snapshot could not be loaded. Try again shortly.'; }
    }
  }
  async function health(version) {
    try {
      const response = await fetch('/api/v1/portfolio/refresh/status', {credentials:'same-origin', cache:'no-store', redirect:'error', signal:controller.signal});
      if (version !== generation) return;
      if ([401,403].includes(response.status)) { clear(); window.dispatchEvent(new Event('meridian-session-ended')); return; }
      if (!response.ok) { el('refresh-status').textContent = 'Broker refresh status is unavailable.'; return; }
      const status = await response.json();
      if (version !== generation) return;
      const job = status.jobs?.snapshot;
      if (!job) { el('refresh-status').textContent = 'Hosted broker refresh has not completed yet.'; return; }
      el('refresh-status').textContent = job.error === 'action_required' ? 'Broker refresh requires administrator attention. Last successful snapshot remains displayed.' : job.error ? 'Broker refresh is retrying. Last successful snapshot remains displayed.' : job.stale ? 'Last broker refresh was over two minutes ago. Check the retrieval times and market session.' : 'Broker refresh is healthy. Market quote age is unknown.';
    } catch (error) { if (version === generation && error.name !== 'AbortError') el('refresh-status').textContent = 'Broker refresh status is unavailable.'; }
  }
  async function refreshBroker() {
    const version = generation;
    el('refresh-broker').disabled = true;
    el('refresh-status').textContent = 'Refreshing Trading 212…';
    try {
      const cookies = document.cookie.split(';').map(x => x.trim()).filter(x => x.startsWith('__Host-meridian_csrf='));
      const csrf = cookies.length === 1 ? cookies[0].slice(cookies[0].indexOf('=') + 1) : '';
      const response = await fetch('/api/v1/portfolio/refresh', {method:'POST', credentials:'same-origin', cache:'no-store', redirect:'error', headers:{'X-CSRF-Token':csrf}});
      if (version !== generation) return;
      if ([401,403].includes(response.status)) { clear(); window.dispatchEvent(new Event('meridian-session-ended')); return; }
      if (!response.ok) { el('refresh-status').textContent = 'Broker refresh is unavailable. Last successful snapshot remains displayed.'; return; }
      const result = await response.json();
      if (version !== generation) return;
      await load();
      if (result.status === 'deferred') el('refresh-status').textContent = 'Refresh is already running or waiting for the shared rate limit.';
      if (result.status === 'failed' || result.status === 'unavailable') el('refresh-status').textContent = 'Broker refresh failed. Last successful snapshot remains displayed.';
    } catch { if (version === generation) el('refresh-status').textContent = 'Broker refresh is unavailable. Last successful snapshot remains displayed.'; }
    finally { el('refresh-broker').disabled = false; }
  }
  for (const [tab,panel] of [['axis-tab','axis-panel'],['holdings-tab','holdings-panel']]) {
    el(tab).addEventListener('click', () => {
      for (const [other,section] of [['axis-tab','axis-panel'],['holdings-tab','holdings-panel']]) { el(other).setAttribute('aria-pressed',String(other===tab)); el(section).hidden=section!==panel; }
    });
  }
  el('holding-search').addEventListener('input',renderHoldings); el('holding-sort').addEventListener('change',renderHoldings);
  el('reload-snapshot').addEventListener('click',load);
  el('refresh-broker').addEventListener('click',refreshBroker);
  window.meridianSnapshot = {load,clear};
})();
