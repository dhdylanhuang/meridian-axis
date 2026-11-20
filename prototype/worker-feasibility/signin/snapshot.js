// Financial values stay decimal strings. No browser totals or browser storage.
(() => {
  const el = id => document.getElementById(id);
  let snapshot = null, generation = 0, controller = null;
  let holdingScope = null;
  const detailControllers = new Set();
  const add = (parent, tag, text) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    parent.append(node);
    return node;
  };
  const when = value => new Date(value).toLocaleString('en-GB',{timeZone:'Europe/London',timeZoneName:'short'});
  function cancelDetails(){ for (const pending of detailControllers) pending.abort(); detailControllers.clear(); }
  let active = false, loading = false, timer = null, failures = 0, nextRead = 0, nextManual = 0;
  const INTERVAL = 600_000, MAX_BACKOFF = 3_600_000, READ_COOLDOWN = 60_000;
  function schedule(delay = INTERVAL) {
    clearTimeout(timer);
    if (active && !document.hidden) timer = setTimeout(load, Math.max(delay, nextRead - Date.now()));
  }
  function backoff() {
    failures++;
    nextRead = Date.now() + Math.min(MAX_BACKOFF, INTERVAL * 2 ** Math.min(failures - 1, 3));
  }
  function start() {
    active = true;
    if (!document.hidden) void load();
  }
  const amounts = ['total-value','investment-value','available-cash','unrealised-pnl','cash-in-pies','reserved-cash','investment-cost','realised-pnl'];
  function decimal(value, currency) {
    if (typeof value !== 'string' || !/^-?\d+(\.\d+)?$/.test(value)) return 'Unavailable';
    const negative = value.startsWith('-');
    const [whole, fraction] = (negative ? value.slice(1) : value).split('.');
    const formatted = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (fraction === undefined ? '' : '.' + fraction);
    return (negative ? '−' : '') + (currency === 'GBP' ? '£' : '') + formatted + (currency && currency !== 'GBP' ? ' ' + currency : '');
  }
  function renderCash(data) {
    const container = el('cash-reconciliation');
    if (!container) return;
    container.replaceChildren();
    const current = add(container, 'dl');
    for (const [label, key] of [['Cash available to trade now','availableToTrade'],['Cash in pies','inPies'],['Reserved for orders','reservedForOrders']]) {
      add(current, 'dt', label); add(current, 'dd', decimal(data.cash_components?.[key], data.currency));
    }
    add(container, 'p', `Trading 212 cash as of ${data.account_retrieval.retrieval_completed_at}. Components are shown separately.`);
    const summary = data.cash_reconciliation, activity = summary?.reported_activity;
    if (!activity) {
      add(container, 'p', 'Dividend, interest, deposit and withdrawal amounts are not available in this saved snapshot. Cash above is broker-reported; no activity totals have been assumed.');
      return;
    }
    add(container, 'h3', 'Income and funding · year to date');
    add(container, 'p', `${activity.since.slice(0,10)} to ${activity.cutoff.slice(0,10)} · Trading 212 activity.`);
    const coverage = summary.history_coverage;
    if (coverage?.scope === 'broker_available_history') {
      for (const family of coverage.families) {
        const name = family.family === 'dividends' ? 'Dividend payouts' : 'Cash movements';
        add(container, 'p', family.state === 'provider_history_traversed'
          ? `${name}: all available broker pages fetched as of ${family.completed_at}. Earliest captured event: ${family.earliest_observed_at || 'no events returned'}.`
          : `${name}: completed broker history traversal has not been established.`);
      }
      add(container, 'p', 'Coverage is the history returned by Trading 212. Complete account-lifetime history is not established; these are not statement-certified totals.');
    } else add(container, 'p', 'Historical coverage is incomplete/unverified; totals may omit earlier or missing events.');
    const currencies = [...new Set([data.currency, ...activity.totals.map(row=>row.currency)])];
    const labels = [['dividends','Paid dividends & distributions'],['cash_interest','Cash interest'],['deposits','Deposits'],['withdrawals','Withdrawals'],['fees','Fees'],['transfers','Transfers'],['lending_interest','Lending interest']];
    for (const currency of currencies) {
      add(container, 'h3', currency);
      const list = add(container, 'dl');
      for (const [category, label] of labels) {
        const row = activity.totals.find(row=>row.currency === currency && row.category === category);
        add(list, 'dt', label); const value = add(list, 'dd', row ? decimal(row.amount, currency) : 'Not established from captured history');
        if (row && summary.activity_details_available) addActivityButton(value, row, summary, add, label);
      }
      const other = activity.totals.find(row=>row.currency === currency && row.category === 'other');
      if (other) { add(list, 'dt', 'Other cash activity · review'); const value=add(list, 'dd', decimal(other.amount, currency)); if(summary.activity_details_available) addActivityButton(value, other, summary, add, 'Other activity'); }
    }
    add(container, 'p', 'Activity amounts retain Trading 212 signs and currencies. Dividend figures are reported payouts, without inferred gross/net tax treatment. Income and funding may already have been invested or spent; these totals do not describe the composition of today’s cash.');
    if (activity.excluded_conflicts) add(container, 'p', `${activity.excluded_conflicts} conflicting records excluded from these totals; review required.`);
  }
  function addActivityButton(parent, total, summary, add, label) {
    const open = add(parent, 'button', 'View transactions'); open.type = 'button';
    const box = add(parent, 'div');
    let loadingPage = false;
    async function page(offset) {
      const version = generation;
      if (loadingPage) return;
      loadingPage = true; open.disabled = true;
      box.replaceChildren(); add(box,'p','Loading transactions…');
      const pending = new AbortController(); detailControllers.add(pending);
      try {
        const cookies = document.cookie.split(';').map(x=>x.trim()).filter(x=>x.startsWith('__Host-meridian_csrf='));
        const csrf = cookies.length === 1 ? cookies[0].slice(cookies[0].indexOf('=')+1) : '';
        const response = await fetch('/api/v1/portfolio/cash-activity', {method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',signal:pending.signal,
          headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
          body:JSON.stringify({snapshot_id:summary.source_snapshot_id,input_revision:summary.input_revision,category:total.category,currency:total.currency,offset,limit:20})});
        if (version !== generation) return;
        if (response.status === 401 || response.status === 403) { clear(); window.dispatchEvent(new Event('meridian-session-ended')); return; }
        if (!response.ok) {
          box.replaceChildren(); add(box,'p',response.status === 409 ? 'This saved total is no longer available for drill-down. Reload the saved snapshot to continue.' : 'Transactions are unavailable. Your saved total is unchanged.'); return;
        }
        const data = await response.json();
        if (version !== generation) return;
        if (data.snapshot_id !== summary.source_snapshot_id || data.input_revision !== summary.input_revision || data.category !== total.category || data.currency !== total.currency || data.offset !== offset || data.total_count !== total.event_count) throw new Error('activity_mismatch');
        box.replaceChildren(); add(box,'p',`${label} · ${decimal(total.amount,total.currency)} total. Showing ${offset+1}–${offset+data.entries.length} of ${data.total_count} transactions.`);
        const scroll=add(box,'div'); scroll.className='table-scroll';
        const table=add(scroll,'table'), head=add(table,'thead'), header=add(head,'tr');
        for(const title of ['Date','Payment / movement','Amount','Trading 212 reference','Source evidence']) add(header,'th',title);
        const body=add(table,'tbody');
        for(const entry of data.entries){
          const row=add(body,'tr'); add(row,'td',entry.occurred_at); add(row,'td',entry.instrument_label || label);
          add(row,'td',decimal(entry.amount,entry.currency)); add(row,'td',entry.reference);
          const evidence=add(add(row,'td'),'details'); add(evidence,'summary',`Revision ${entry.revision}`);
          add(evidence,'p',`Trading 212 · ${entry.family} · ${entry.provider_type}`);
          add(evidence,'p',`Source ${entry.source_id}; revision ${entry.revision_id || 'initial capture'}; SHA-256 ${entry.digest}`);
        }
        if(offset>0){const previous=add(box,'button','Previous page');previous.type='button';previous.addEventListener('click',()=>page(Math.max(0,offset-20)));}
        if(offset+data.entries.length<data.total_count){const next=add(box,'button','Next page');next.type='button';next.addEventListener('click',()=>page(offset+20));}
      } catch(error) {
        if(version === generation && error.name !== 'AbortError'){box.replaceChildren();add(box,'p','Transactions are unavailable. Your saved total is unchanged.');}
      } finally {detailControllers.delete(pending);loadingPage=false;open.disabled=false;}
    }
    open.addEventListener('click',()=>page(0));
  }
  function compare(a, b) {
    if (a == null) return b == null ? 0 : -1;
    if (b == null) return 1;
    const parts = [a,b].map(x => x.split('.'));
    const scale = Math.max(parts[0][1]?.length || 0, parts[1][1]?.length || 0);
    const [x,y] = parts.map(([whole, fraction='']) => BigInt(whole + fraction.padEnd(scale, '0')));
    return x < y ? -1 : x > y ? 1 : 0;
  }
  const tabs = [['axis-tab','axis-panel'],['holdings-tab','holdings-panel']];
  function selectTab(tab) {
    for (const [other, section] of tabs) {
      el(other).setAttribute('aria-pressed',String(other === tab));
      el(section).hidden = other !== tab;
    }
  }
  function showHoldings(scope) {
    holdingScope = scope;
    el('holding-search').value = '';
    el('holding-sort').value = 'value';
    selectTab('holdings-tab');
    renderHoldings();
    (scope ? el('holding-scope') : el('holding-search')).focus?.();
  }
  function holdingLink(parent, label, scope) {
    const button = add(parent, 'button', label);
    button.type = 'button';
    button.className = 'holding-link';
    button.addEventListener('click', () => showHoldings(scope));
    return button;
  }
  function percent(value) {
    return value == null ? 'Unavailable' : `${decimal(value)}%`;
  }
  function exposureTable(parent, columns, label) {
    const scroll = add(parent, 'div');
    scroll.className = 'table-scroll';
    scroll.tabIndex = 0;
    scroll.setAttribute('aria-label', label);
    const table = add(scroll, 'table');
    const header = add(add(table, 'thead'), 'tr');
    for (const title of columns) add(header, 'th', title).scope = 'col';
    return add(table, 'tbody');
  }
  function exposureCells(row, exposure, currency) {
    add(row, 'td', decimal(exposure.value, currency));
    add(row, 'td', percent(exposure.portfolio_pct));
    add(row, 'td', percent(exposure.invested_pct));
  }
  function renderExposures(data) {
    const section = el('portfolio-exposures');
    if (!section) return;
    section.replaceChildren();
    add(section, 'h2', 'Portfolio exposures');
    const report = data.exposures;
    if (!report?.holdings) {
      add(section, 'p', report?.availability === 'failed'
        ? 'Exposure calculation was unavailable for this refresh.'
        : 'This saved snapshot has no exposure calculation. A successful broker refresh can publish one.');
      return;
    }
    const currency = data.currency;
    const columns = ['Value', '% of portfolio', '% of invested value'];
    add(section, 'p', `Trading 212 · Holdings captured ${when(report.positions_as_of)}. Account values captured ${when(report.account_as_of)}.`);
    add(section, 'p', `Portfolio denominator: ${decimal(report.portfolio_denominator, currency)} (broker total value). Invested denominator: ${decimal(report.invested_denominator, currency)} (broker investment value). Weights use account-currency values and may differ from 100% across buckets because the requests are separate and some values may be missing.`);
    const observed = report.observed_holdings;
    add(section, 'p', `Holdings with compatible reported values: ${decimal(observed.value, currency)} · ${percent(observed.invested_pct)} of broker investment value.`);
    if (report.missing_values) add(section, 'p', `${report.missing_values} holdings lack a usable value in ${currency}. Tables show known amounts and weights; the concentration rankings may change once those values are known.`);

    add(section, 'h3', 'Concentration');
    add(section, 'p', 'Largest position and combined weights of the largest five and ten positions, using fewer if the account holds fewer. Cash is excluded from the ranked positions.');
    const concentration = exposureTable(section, ['Largest positions', ...columns], 'Concentration measures');
    for (const measure of report.concentration) {
      const row = add(concentration, 'tr');
      const label = measure.top === 1 ? 'Largest position' : `Top ${measure.top}`;
      add(row, 'td', measure.value == null ? label : `${label} (${measure.position_count} used)`);
      exposureCells(row, measure, currency);
    }
    if (report.missing_values) add(section, 'p', 'Combined concentration weights require a compatible value for every holding.');

    add(section, 'h3', 'Top holdings by reported value');
    const ranked = report.holdings.filter(row => row.value != null).slice(0, 10);
    if (ranked.length) {
      const body = exposureTable(section, ['Holding', ...columns], 'Top holdings');
      const figures = new Map(data.positions.map(row => [row.ticker, row]));
      for (const [index, position] of ranked.entries()) {
        const row = add(body, 'tr'), cell = add(row, 'td');
        const holding = figures.get(position.ticker);
        holdingLink(cell, `${index + 1}. ${holding?.name || position.ticker}`,
          {kind:'ticker', key:position.ticker, label:holding?.name || position.ticker});
        add(cell, 'small', position.ticker);
        exposureCells(row, position, currency);
      }
    } else add(section, 'p', report.holdings.length
      ? 'No holding has a compatible value to rank.' : 'Trading 212 reported no open positions.');
    if (report.holdings.length) holdingLink(section, 'View all holdings', null);

    add(section, 'h3', 'Listing and quote currencies');
    add(section, 'p', 'Trading 212 position currency, with current broker instrument metadata as a fallback. Values are grouped by trading currency. Economic currency exposure requires underlying issuer or fund data.');
    if (report.quote_currencies.length) {
      const body = exposureTable(section, ['Quote currency', ...columns], 'Quote currency allocation');
      for (const bucket of report.quote_currencies) {
        const row = add(body, 'tr'), cell = add(row, 'td');
        const label = bucket.quote_currency || 'Unclassified quote currency';
        holdingLink(cell, label, {kind:'quote', key:bucket.quote_currency, label});
        if (bucket.missing_values) add(cell, 'small', `${bucket.missing_values} missing values`);
        exposureCells(row, bucket, currency);
      }
    } else add(section, 'p', 'No holdings to group.');

    add(section, 'h3', 'Sector and country coverage');
    add(section, 'p', 'Trading 212 positions and instrument metadata supply neither classification. Sector needs a dated issuer-to-sector mapping with a named taxonomy. Country needs a dated issuer-to-country mapping with a defined country basis. Fund look-through requires source-dated constituents and weights.');
    if (report.holdings.length) {
      const body = exposureTable(section, ['Classification', ...columns], 'Classification coverage');
      for (const label of ['Unclassified sector','Unclassified country']) {
        const row = add(body, 'tr');
        holdingLink(add(row, 'td'), label, {kind:'unclassified', label});
        exposureCells(row, observed, currency);
      }
      add(section, 'p', `Classifications supplied for 0 of ${report.holdings.length} holdings. The unclassified amounts show the compatible values available above.`);
    }

    add(section, 'h3', 'Reported cash components');
    const cash = exposureTable(section, ['Component', 'Value', '% of portfolio'], 'Cash component weights');
    for (const [key, label] of [['availableToTrade','Available to trade'],['inPies','In pies'],['reservedForOrders','Reserved for orders']]) {
      const row = add(cash, 'tr');
      add(row, 'td', label);
      add(row, 'td', decimal(data.cash_components[key], currency));
      add(row, 'td', percent(report.cash_component_pct[key]));
    }
    add(section, 'p', 'Shares are calculated separately for each component. Total cash allocation is unavailable because the broker field definitions do not establish that the components are disjoint.');
  }
  function clear() {
    active = false; clearTimeout(timer); failures = 0; nextRead = 0; nextManual = 0;
    generation++; controller?.abort(); cancelDetails(); snapshot = null;
    amounts.forEach(id => el(id).textContent = '—');
    el('holdings-body').replaceChildren(); el('holding-count').textContent = '';
    if (el('cash-reconciliation')) { el('cash-reconciliation').replaceChildren(); el('cash-reconciliation').textContent = '—'; }
    el('snapshot-time').textContent = '—'; el('snapshot-status').textContent = ''; el('refresh-status').textContent = '';
    el('portfolio-exposures')?.replaceChildren();
    holdingScope = null;
    el('holding-scope').hidden = true;
    el('holding-scope').textContent = '';
    el('clear-holding-scope').hidden = true;
    el('holding-search').value = ''; el('refresh-broker').disabled = false; document.body.classList.remove('snapshot-ready');
  }
  function renderHoldings() {
    const query = el('holding-search').value.trim().toLowerCase();
    const report = snapshot?.exposures;
    const weights = new Map((report?.holdings || []).map(row => [row.ticker, row]));
    const scopeLabel = el('holding-scope');
    scopeLabel.textContent = holdingScope?.label || '';
    scopeLabel.hidden = el('clear-holding-scope').hidden = !holdingScope;
    const inScope = row => {
      if (holdingScope?.kind === 'ticker') return row.ticker === holdingScope.key;
      if (holdingScope?.kind === 'quote') return weights.get(row.ticker)?.quote_currency === holdingScope.key;
      return true;
    };
    const rows = (snapshot?.positions || []).filter(row =>
      inScope(row) && `${row.ticker} ${row.name || ''}`.toLowerCase().includes(query));
    rows.sort(el('holding-sort').value === 'name' ? (a,b) => (a.name || a.ticker).localeCompare(b.name || b.ticker) : (a,b) => compare(
      report?.holdings ? weights.get(b.ticker)?.value : b.current_value,
      report?.holdings ? weights.get(a.ticker)?.value : a.current_value));
    const fragment = document.createDocumentFragment();
    for (const row of rows) {
      const tr = document.createElement('tr');
      const name = document.createElement('td'); name.textContent = row.name || row.ticker;
      const ticker = document.createElement('small'); ticker.textContent = row.ticker;
      const metadataStates = {pending:'metadata pending',missing:'metadata unavailable',stale:'metadata stale',conflict:'metadata needs review'};
      if (metadataStates[row.metadata?.state]) ticker.textContent += ` · ${metadataStates[row.metadata.state]}`;
      const weight = weights.get(row.ticker);
      if (weight?.quote_currency) {
        const source = row.quote_currency_source === 'instrument_metadata'
          ? `broker catalogue, ${when(row.metadata.retrieved_at)}` : 'broker position';
        ticker.textContent += ` · Quote: ${weight.quote_currency} (${source})`;
      }
      name.append(ticker); tr.append(name);
      for (const value of [decimal(row.quantity), decimal(row.current_price,row.instrument_currency), decimal(row.current_value,row.account_currency), percent(weight?.portfolio_pct), percent(weight?.invested_pct), decimal(row.total_cost,row.account_currency), decimal(row.unrealized_profit_loss,row.account_currency)]) {
        const cell = document.createElement('td'); cell.textContent = value; tr.append(cell);
      }
      fragment.append(tr);
    }
    el('holdings-body').replaceChildren(fragment);
    el('holding-count').textContent = `${rows.length} of ${snapshot?.positions.length || 0} holdings`;
  }
  async function load() {
    if (loading || document.hidden) return;
    if (Date.now() < nextRead) { schedule(nextRead - Date.now()); return; }
    loading = true;
    generation++; controller?.abort(); cancelDetails(); const version = generation; controller = new AbortController();
    el('snapshot-status').textContent = 'Loading saved broker snapshot…';
    try {
      const response = await fetch('/api/v1/portfolio/snapshot', { credentials:'same-origin', cache:'no-store', redirect:'error', signal:controller.signal });
      if (version !== generation) return;
      if ([401,403].includes(response.status)) { clear(); window.dispatchEvent(new Event('meridian-session-ended')); return; }
      if (response.status === 404) { failures = 0; nextRead = Date.now() + READ_COOLDOWN; el('snapshot-status').textContent = 'No saved snapshot is available yet.'; return; }
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (version !== generation) return;
      if (data.source !== 'trading212' || data.basis !== 'broker_reported' || !Array.isArray(data.positions)) throw new Error('invalid');
      snapshot = data;
      const values = [data.total_value,data.investments.currentValue,data.cash_components.availableToTrade,data.investments.unrealizedProfitLoss,data.cash_components.inPies,data.cash_components.reservedForOrders,data.investments.totalCost,data.investments.realizedProfitLoss];
      amounts.forEach((id,index) => el(id).textContent = decimal(values[index],data.currency));
      el('snapshot-time').textContent = `Trading 212 · ${data.environment.toUpperCase()} account · Account captured ${when(data.account_retrieval.retrieval_completed_at)}; holdings captured ${when(data.positions_retrieval.retrieval_completed_at)}.`;
      const changes = data.holding_changes;
      const additions = changes?.added_tickers || [], closures = changes?.closed_tickers || [];
      el('snapshot-status').textContent = additions.length || closures.length ? `Since previous saved snapshot: ${additions.length} holdings added, ${closures.length} no longer held. These are position observations, not execution confirmations.` : '';
      document.body.classList.add('snapshot-ready'); renderHoldings();
      failures = 0; nextRead = Date.now() + READ_COOLDOWN;
      renderCash(data);
      renderExposures(data);
      health(data.refresh_health);
    } catch (error) {
      if (version === generation && error.name !== 'AbortError') {
        backoff();
        el('snapshot-status').textContent = snapshot ? 'Refresh failed. Last successful snapshot remains displayed. Automatic retries are paused.' : 'The saved snapshot could not be loaded. Automatic retries are paused.';
      }
    } finally { loading = false; if (version === generation) schedule(); }
  }
  function health(status) {
    const job = status?.jobs?.snapshot;
    if (!job) { el('refresh-status').textContent = 'Hosted broker refresh status is unavailable.'; return; }
    el('refresh-status').textContent = job.error === 'action_required' ? 'Broker refresh requires administrator attention. Last successful snapshot remains displayed.' : job.error ? 'Broker refresh is retrying with backoff. Last successful snapshot remains displayed.' : job.stale ? 'Last broker refresh was over twenty minutes ago. Check the retrieval times and market session.' : 'Automatic refresh every ten minutes. Market quote age is unknown.';
  }
  async function refreshBroker() {
    if (Date.now() < Math.max(nextManual, failures ? nextRead : 0)) {
      el('refresh-status').textContent = 'Refresh is cooling down. Please wait before trying again.';
      return;
    }
    nextManual = Date.now() + READ_COOLDOWN;
    const version = generation;
    el('refresh-broker').disabled = true;
    el('refresh-status').textContent = 'Refreshing Trading 212…';
    try {
      const cookies = document.cookie.split(';').map(x => x.trim()).filter(x => x.startsWith('__Host-meridian_csrf='));
      const csrf = cookies.length === 1 ? cookies[0].slice(cookies[0].indexOf('=') + 1) : '';
      const response = await fetch('/api/v1/portfolio/refresh', {method:'POST', credentials:'same-origin', cache:'no-store', redirect:'error', headers:{'X-CSRF-Token':csrf}});
      if (version !== generation) return;
      if ([401,403].includes(response.status)) { clear(); window.dispatchEvent(new Event('meridian-session-ended')); return; }
      if (!response.ok) { backoff(); schedule(); el('refresh-status').textContent = 'Broker refresh is unavailable. Last successful snapshot remains displayed. Retries are paused.'; return; }
      const result = await response.json();
      if (version !== generation) return;
      schedule(READ_COOLDOWN);
      if (result.status === 'queued') el('refresh-status').textContent = 'Broker refresh queued. This view updates automatically.';
      if (result.status === 'deferred') el('refresh-status').textContent = 'Refresh is already running or waiting for the shared rate limit.';
      if (result.status === 'failed' || result.status === 'unavailable') el('refresh-status').textContent = 'Broker refresh failed. Last successful snapshot remains displayed.';
    } catch { if (version === generation) { backoff(); schedule(); el('refresh-status').textContent = 'Broker refresh is unavailable. Last successful snapshot remains displayed. Retries are paused.'; } }
    finally { el('refresh-broker').disabled = false; }
  }
  for (const [tab] of tabs) el(tab).addEventListener('click', () => selectTab(tab));
  el('clear-holding-scope').addEventListener('click', () => showHoldings(null));
  el('holding-search').addEventListener('input',renderHoldings); el('holding-sort').addEventListener('change',renderHoldings);
  el('reload-snapshot').addEventListener('click',load);
  el('refresh-broker').addEventListener('click',refreshBroker);
  document.addEventListener('visibilitychange', () => {
    clearTimeout(timer);
    if (active && !document.hidden) void load();
  });
  window.meridianSnapshot = {load,clear,start};
})();
