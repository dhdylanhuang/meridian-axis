// Financial values stay decimal strings. No browser totals or browser storage.
(() => {
  const el = id => document.getElementById(id);
  let snapshot = null, generation = 0, controller = null;
  let holdingScope = null;
  let history = null, historyRequest = null, historyIndex = 0, overviewRequested = false;
  let changesRequest = null, overviewRange = 30;
  let riskLoaded = false, riskRequest = null;
  const detailControllers = new Set();
  const add = (parent, tag, text) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    parent.append(node);
    return node;
  };
  const { day: formatDay, timestamp: when } = window.meridianDates;
  function timeCell(row, value, fallback = 'Unavailable') {
    const cell = add(row, 'td', value ? when(value) : fallback);
    if (value) cell.title = value;
    return cell;
  }
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
  window.meridianPlanning?.configure(decimal, () => {
    clear();
    window.dispatchEvent(new Event('meridian-session-ended'));
  });
  function renderCash(data) {
    const container = el('cash-reconciliation');
    if (!container) return;
    container.replaceChildren();
    const current = add(container, 'dl');
    for (const [label, key] of [['Cash available to trade now','availableToTrade'],['Cash in pies','inPies'],['Reserved for orders','reservedForOrders']]) {
      add(current, 'dt', label); add(current, 'dd', decimal(data.cash_components?.[key], data.currency));
    }
    add(container, 'p', `Trading 212 cash as of ${when(data.account_retrieval.retrieval_completed_at)}. Components are shown separately.`);
    const summary = data.cash_reconciliation, activity = summary?.reported_activity;
    if (!activity) {
      add(container, 'p', 'Dividend, interest, deposit and withdrawal amounts are not available in this saved snapshot. Cash above is broker-reported; no activity totals have been assumed.');
      return;
    }
    add(container, 'h3', 'Income and funding · year to date');
    add(container, 'p', `${formatDay(activity.since.slice(0, 10))} to ${formatDay(activity.cutoff.slice(0, 10))} · Trading 212 activity.`);
    const coverage = summary.history_coverage;
    if (coverage?.scope === 'broker_available_history') {
      for (const family of coverage.families) {
        const name = family.family === 'dividends' ? 'Dividend payouts' : 'Cash movements';
        add(container, 'p', family.state === 'provider_history_traversed'
          ? `${name}: all available broker pages fetched as of ${when(family.completed_at)}. Earliest captured event: ${family.earliest_observed_at ? when(family.earliest_observed_at) : 'no events returned'}.`
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
        for(const title of ['Date and time (London)','Payment / movement','Amount','Trading 212 reference','Source evidence']) add(header,'th',title);
        const body=add(table,'tbody');
        for(const entry of data.entries){
          const row=add(body,'tr'); timeCell(row, entry.occurred_at); add(row,'td',entry.instrument_label || label);
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
  const tabs = [
    ['axis-tab', 'axis-panel', 'AXIS overview'],
    ['holdings-tab', 'holdings-panel', 'Holdings'],
    ['exposures-tab', 'portfolio-exposures', 'Exposures'],
    ['history-tab', 'history-panel', 'History'],
    ['changes-tab', 'changes-panel', 'Portfolio Changes'],
    ['risk-tab', 'risk-panel', 'Risk'],
    ['projections-tab', 'projections-panel', 'Projections'],
    ['stress-tab', 'stress-panel', 'Stress Tests'],
  ];
  function selectTab(tab) {
    for (const [other, section, label] of tabs) {
      const selected = other === tab;
      el(other).setAttribute('aria-pressed', String(selected));
      el(section).hidden = !selected;
      if (selected) el('workspace-path').textContent = label;
    }
    if (tab === 'history-tab' && !history) void loadHistory();
    if (tab === 'changes-tab') setChangesDates();
    if (tab === 'risk-tab') {
      renderRiskExposure(snapshot);
      if (!riskLoaded && !riskRequest) void loadRisk();
    }
  }
  const historyLabel = point => point.status === 'missing' ? 'No saved snapshot' : 'Saved snapshot unavailable';
  const historyAmount = point => decimal(point.total_value, 'GBP');
  const fundingDays = new Map();
  const plot = {left: 175, right: 942, top: 24, bottom: 218};
  const plotX = index => plot.left + (plot.right - plot.left) * index / (history.days.length - 1);
  function chartValues(observed) {
    const scale = Math.max(...observed.map(point => point.total_value.split('.')[1]?.length || 0));
    const values = observed.map(point => {
      const [whole, fraction = ''] = point.total_value.split('.');
      return BigInt(whole + fraction.padEnd(scale, '0'));
    });
    return { values, min: values.reduce((a, b) => a < b ? a : b), max: values.reduce((a, b) => a > b ? a : b) };
  }
  function drawHistory() {
    const ctx = el('history-chart').getContext?.('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, 960, 264);
    ctx.font = '13px system-ui';
    ctx.textAlign = 'center';
    ctx.fillStyle = '#a1b0c1';
    const points = history.days;
    for (const index of [0, 22, 44, 67, 89]) {
      ctx.fillText(formatDay(points[index].date, true), plotX(index), 252);
    }
    const observed = points.filter(point => point.status === 'observed');
    if (observed.length) {
      const { values, min, max } = chartValues(observed);
      ctx.textAlign = 'right';
      for (const [value, y] of min === max ? [[min, 121]] : [[max, plot.top], [min, plot.bottom]]) {
        const point = observed[values.indexOf(value)];
        ctx.fillText(historyAmount(point), plot.left - 10, y + 4, plot.left - 14);
        ctx.fillStyle = '#303d4c';
        ctx.fillRect(plot.left, y, plot.right - plot.left, 1);
        ctx.fillStyle = '#a1b0c1';
      }
      let valueIndex = 0;
      let previous = null;
      for (const [index, point] of points.entries()) {
        if (point.status !== 'observed') { previous = null; continue; }
        const value = values[valueIndex++];
        const y = min === max ? 121 : plot.bottom - Number((value - min) * 10000n / (max - min)) / 10000 * (plot.bottom - plot.top);
        const x = plotX(index);
        ctx.fillStyle = '#81d6bf';
        if (previous) {
          ctx.strokeStyle = ctx.fillStyle;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(...previous);
          ctx.lineTo(x, y);
          ctx.stroke();
        }
        ctx.beginPath();
        ctx.arc(x, y, index === historyIndex ? 5 : 2.5, 0, Math.PI * 2);
        ctx.fill();
        previous = [x,y];
      }
    }
    for (const [index, point] of points.entries()) {
      ctx.fillStyle = point.status === 'observed' ? '#81d6bf' : point.status === 'missing' ? '#586a7d' : '#e9b879';
      ctx.fillRect(plotX(index) - 2, 229, 4, 4);
    }
    ctx.fillStyle = '#e9b879';
    for (const [index, point] of points.entries()) {
      if (fundingDays.has(point.date)) ctx.fillRect(plotX(index) - 2, 237, 4, 5);
    }
    ctx.fillStyle = '#ecf8ee';
    ctx.fillRect(plotX(historyIndex) - 1, 223, 2, 12);
  }
  function inspectDay(index) {
    historyIndex = Math.max(0, Math.min(history.days.length - 1, index));
    const point = history.days[historyIndex];
    const day = formatDay(point.date) + (point.date === history.end_date ? ' (today so far)' : '');
    el('history-point').textContent = point.status === 'observed'
      ? `${day} UTC · ${historyAmount(point)} · Account captured ${when(point.captured_at)} · Snapshot observed ${when(point.observed_at)}`
      : `${day} UTC · ${historyLabel(point)}`;
    const count = fundingDays.get(point.date);
    if (count) {
      const link = add(el('history-point'), 'a', `View ${count} funding ${count === 1 ? 'transaction' : 'transactions'}`);
      link.className = 'history-funding-link';
      link.href = '#history-funding-' + point.date;
      link.addEventListener('click', () => { el('history-funding').open = true; });
    }
    drawHistory();
  }
  const performanceReasons = {
    missing_valuation:'A saved valuation is missing',
    funding_coverage_unverified:'Funding coverage is unverified for the interval',
    unclassified_or_unsupported_funding:'A movement needs funding classification',
    funding_valuation_order_unknown:'A movement shares the valuation timestamp',
    capture_order_invalid:'Account captures are out of order',
    nonpositive_account_value:'An account value is zero or negative',
    nonpositive_weighted_capital:'Weighted capital is zero or negative',
    nonpositive_growth:'The interval cannot be linked to a return series',
    period_boundary_unavailable:'A required period boundary is missing',
  };
  const periodRange = row => `${formatDay(row.start_date)} to ${formatDay(row.end_date)}`;
  const adjustedReturn = row => row?.return_pct != null
    ? percent(row.return_pct)
    : performanceReasons[row?.reason] || 'No eligible interval in this window';
  function fundingLabel(event) {
    if (event.kind === 'DEPOSIT') return 'Deposit';
    if (event.kind === 'WITHDRAW') return 'Withdrawal';
    return event.kind === 'TRANSFER' ? 'Transfer' : event.kind;
  }
  function renderBenchmark(section, compare) {
    add(section, 'h3', 'VUAG · S&P 500 benchmark proxy');
    const observed = compare?.state === 'broker_observed';
    if (!observed && compare?.state !== 'qualified_series') {
      add(section, 'p', compare?.state === 'invalid_series'
        ? 'The supplied GBP close series could not be verified.'
        : 'VUAG returns need two saved GBP prices on dates with an eligible portfolio return.');
      return;
    }
    add(section, 'p', `Provisional comparison · ${compare.matched_intervals} of ${compare.eligible_intervals} eligible portfolio intervals matched.`);
    add(section, 'p', observed
      ? 'VUAG GBP per-share prices come from saved Trading 212 holdings. Times show when holdings were captured. Quote age and split adjustments are unverified.'
      : `GBP London closing prices · ${compare.source} · reviewed ${when(compare.reviewed_at)}. Account capture and closing times can differ.`);
    if (!compare.intervals.length) return;
    const body = exposureTable(section, ['UTC dates', 'Portfolio', 'VUAG', 'Difference', 'Account captures (London)', observed ? 'VUAG captures (London)' : 'VUAG closes (London)'], 'Portfolio and VUAG matched returns');
    for (const item of [...compare.intervals].reverse()) {
      const row = add(body, 'tr');
      add(row, 'td', periodRange(item));
      add(row, 'td', percent(item.portfolio_pct));
      add(row, 'td', item.benchmark_pct == null ? 'Unavailable' : percent(item.benchmark_pct));
      add(row, 'td', item.difference_pp == null
        ? (item.reason === 'portfolio_capture_date_mismatch' ? 'Account capture crossed UTC date' : observed ? 'VUAG capture missing' : 'Benchmark endpoint missing')
        : `${decimal(item.difference_pp)} pp`);
      add(row, 'td', [item.portfolio_start_at, item.portfolio_end_at].map(when).join(' to '));
      add(row, 'td', [item.start_mark, item.end_mark].map(mark => mark
        ? `${decimal(mark.price_gbp, 'GBP')} · ${when(mark.at)}` : 'Missing').join(' to '));
    }
  }
  function renderDrawdown(section, drawdown) {
    add(section, 'h3', 'Portfolio drawdown');
    if (!drawdown) {
      add(section, 'p', 'No eligible cash-flow-adjusted interval in the selected dates.');
      return;
    }
    const list = add(section, 'dl');
    add(list, 'dt', 'Drawdown at latest eligible capture');
    add(list, 'dd', percent(drawdown.current_pct));
    add(list, 'dt', 'Worst drawdown in this stretch');
    add(list, 'dd', percent(drawdown.worst_pct));
    add(section, 'p', `Flow-adjusted stretch · ${when(drawdown.start_at)} to ${when(drawdown.as_of)} · ${drawdown.intervals} eligible intervals. Latest running peak captured ${when(drawdown.current_peak_at)}.`);
    if (drawdown.worst_peak_at && drawdown.worst_trough_at) {
      add(section, 'p', `Worst decline · peak ${when(drawdown.worst_peak_at)} · trough ${when(drawdown.worst_trough_at)}.`);
    }
    if (drawdown.later_unavailable_intervals > 0) {
      add(section, 'p', 'The selected range extends beyond the last eligible capture.');
    }
  }
  const riskMeasures = [
    ['volatility','Annualised volatility','%'],['sharpe','Sharpe ratio',''],['sortino','Sortino ratio',''],
    ['var95','One-session VaR · 95%','%'],['es95','Expected shortfall · 95%','%'],
    ['var99','One-session VaR · 99%','%'],['es99','Expected shortfall · 99%','%'],
    ['beta','Beta vs VUAG',''],['jensen_alpha','Annualised log alpha vs VUAG','%'],
    ['r_squared','R² vs VUAG',''],['correlation','Correlation with VUAG',''],
    ['tracking_error','Annualised tracking error vs VUAG','%'],
  ];
  const riskReasons = {
    need_portfolio:'Needs more approved portfolio returns',
    need_rate:'Needs more portfolio returns with dated Bank Rate',
    need_regression:'Needs more aligned portfolio and VUAG returns with dated Bank Rate',
    need_vuag:'Needs more aligned portfolio and VUAG returns',
    need_tail:'Fewer than two tail observations',
    undefined:'Undefined for this sample',
  };
  function renderSessionPerformance(section, performance) {
    add(section, 'h3', 'Approved session performance');
    if (!performance) {
      add(section, 'p', 'Needs reviewed GBP session valuations and verified timing. The History tab shows the available broker observations.');
      return;
    }
    add(section, 'p', 'Modified Dietz adjusts for the amount and timing of external funding. The figures use the latest uninterrupted eligible stretch inside the selected dates.');
    const summaries = exposureTable(section, ['Series', 'UTC dates', 'Sessions', 'ISA', 'VUAG', 'Difference'], 'Approved performance');
    for (const [label, stretch] of [['ISA', performance.latest_portfolio], ['Matched ISA and VUAG', performance.latest_matched]]) {
      const row = add(summaries, 'tr');
      add(row, 'td', label);
      add(row, 'td', stretch ? periodRange(stretch) : 'Unavailable');
      add(row, 'td', String(stretch?.sessions ?? 0));
      add(row, 'td', percent(stretch?.portfolio_pct));
      add(row, 'td', percent(stretch?.vuag_pct));
      add(row, 'td', stretch?.spread_pp == null ? 'Unavailable' : signed(stretch.spread_pp) + ' pp');
    }
    if (!performance.rows.length) return;
    const details = add(section, 'details');
    add(details, 'summary', `Session evidence · ${performance.rows.length} intervals`);
    const rows = exposureTable(details, ['Reviewed cutoffs (London)', 'External GBP funding', 'ISA', 'VUAG', 'VUAG closes (London)'], 'Reviewed session evidence');
    const reasons = {
      missing_session_valuation:'Missing approved valuation',
      funding_coverage_unverified:'Funding history coverage unverified',
      funding_valuation_order_unknown:'Funding and valuation order ambiguous',
      unclassified_or_unsupported_funding:'Unsupported funding event',
    };
    for (const item of performance.rows) {
      const row = add(rows, 'tr');
      add(row, 'td', `${when(item.start_at)} → ${when(item.end_at)}`);
      add(row, 'td', item.net_external_flow_gbp == null ? 'Unavailable'
        : `${decimal(item.net_external_flow_gbp, 'GBP')} · ${item.external_flow_count} ${item.external_flow_count === 1 ? 'event' : 'events'}`);
      add(row, 'td', item.reason ? reasons[item.reason] ?? 'Return unavailable' : percent(item.portfolio_pct));
      add(row, 'td', percent(item.vuag_pct));
      add(row, 'td', item.vuag_start_at && item.vuag_end_at
        ? `${when(item.vuag_start_at)} → ${when(item.vuag_end_at)}` : 'Unavailable');
    }
  }

  function renderHoldingCorrelation(section, report) {
    add(section, 'h3', 'Holding correlation');
    if (!report || report.state === 'awaiting_approved_holding_series') {
      add(section, 'p', 'Needs approved GBP total-return marks for the held listings.');
      return;
    }
    add(section, 'p', `Holdings as of ${when(report.holdings_as_of)} · ${report.included_holdings} of ${report.universe_holdings} holdings · ${percent(report.included_weight_pct)} of ISA value included out of ${percent(report.universe_weight_pct)} submitted, excluding cash.`);
    add(section, 'p', `${report.n} common return intervals${report.start_date ? ` · ${periodRange(report)} UTC` : ''} · minimum ${report.minimum_daily}. Pearson correlation uses the same GBP log-return dates for every pair.`);
    if (report.state === 'available') {
      const rows = exposureTable(section, ['Holding pair', 'Correlation'], 'Highest holding correlations');
      for (const pair of report.pairs) {
        const row = add(rows, 'tr');
        add(row, 'td', `${pair.first} and ${pair.second}`);
        add(row, 'td', decimal(pair.correlation));
      }
      add(section, 'p', `Showing the ${report.pairs.length} highest correlations of ${report.pair_count} pairs.`);
    } else add(section, 'p', report.state === 'needs_two_holdings'
      ? 'At least two holdings need sufficient, variable returns.'
      : 'The eligible holdings have too few shared return dates.');
    if (report.excluded.length) {
      const detail = add(section, 'details');
      add(detail, 'summary', `Excluded holdings · ${report.excluded.length}`);
      const rows = exposureTable(detail, ['Holding', 'ISA weight', 'Returns', 'Reason'], 'Holding correlation exclusions');
      for (const item of report.excluded) {
        const row = add(rows, 'tr');
        add(row, 'td', item.ticker);
        add(row, 'td', percent(item.weight_pct));
        add(row, 'td', String(item.n));
        add(row, 'td', item.reason === 'insufficient_returns' ? 'Insufficient returns'
          : item.reason === 'constant_on_common_sample' ? 'Constant on common dates' : 'Constant returns');
      }
    }
  }

  function renderCutoffCollection(section, report, returns) {
    if (!report) return;
    add(section, 'h3', 'Fixed-cutoff broker collection');
    if (report.state === 'unavailable') {
      add(section, 'p', 'Broker observations could not be loaded.');
      return;
    }
    add(section, 'p', 'Trading 212 reported ISA values captured from 22:00 UTC. Returns use adjacent captures and completed funding history. Net funding shows deposits minus withdrawals. Interest stays in the return. Quote timing remains unknown.');
    if (returns?.approval_state === 'awaiting_review') {
      add(section, 'p', 'Automatic returns remain provisional pending valuation-basis review.');
    } else if (returns?.approval_state === 'invalid_policy') {
      add(section, 'p', 'The supplied approval policy could not be verified.');
    } else if (returns?.state === 'unavailable') {
      add(section, 'p', 'Automatic returns could not be calculated.');
    }
    const latest = returns?.latest;
    if (latest) add(section, 'p', `Latest uninterrupted stretch · ${periodRange(latest)} UTC · ${percent(latest.portfolio_pct)} · ${latest.sessions} returns.`);
    if (report.calendar_reviewed_through) {
      add(section, 'p', `London session calendar reviewed through ${formatDay(report.calendar_reviewed_through)}.`);
    }
    if (!report.observations.length) {
      add(section, 'p', 'No scheduled broker captures in the selected dates.');
      return;
    }
    if (report.older_dates) add(section, 'p', `Showing the latest ${report.observations.length} scheduled dates. Narrow the dates to inspect older captures.`);
    const rows = exposureTable(section, ['Target (London)', 'Actual capture (London)', 'Reported ISA value', 'Status', 'Funding coverage', 'Net external funding', 'ISA return'], 'Fixed-cutoff broker observations');
    const intervals = new Map((returns?.intervals ?? []).map(interval => [interval.end_date, interval]));
    const reasons = {
      missing_cutoff_observation: 'Missing scheduled capture',
      funding_coverage_unverified: 'Funding unverified',
      funding_valuation_order_unknown: 'Ambiguous funding at capture',
      unclassified_or_unsupported_funding: 'Unsupported funding event',
      calendar_unreviewed: 'Calendar unreviewed',
    };
    const states = {observed:'Provisional observation', pending:'Scheduled', missing:'Missed window', unavailable:'Evidence unavailable'};
    const funding = {covered:'Completed history covers interval', unverified:'Unverified', no_previous_observation:'No preceding capture'};
    for (const item of report.observations) {
      const row = add(rows, 'tr');
      timeCell(row, item.target_at);
      timeCell(row, item.captured_at, '—');
      add(row, 'td', decimal(item.total_value_gbp, 'GBP'));
      add(row, 'td', states[item.status]);
      add(row, 'td', funding[item.funding_coverage] || '—');
      const interval = intervals.get(item.date);
      const net = interval?.net_external_flow_gbp;
      const count = interval?.external_flow_count;
      add(row, 'td', net == null ? '—'
        : `${signed(net, 'GBP')} · ${count} ${count === 1 ? 'flow' : 'flows'}`);
      add(row, 'td', interval?.return_pct != null
        ? `${percent(interval.return_pct)} · ${interval.approved ? 'Approved' : 'Provisional'}`
        : (interval ? reasons[interval.reason] ?? 'Unavailable' : '—'));
    }
    if (returns?.approved_risk) {
      const risk = returns.approved_risk;
      add(section, 'h4', 'Risk from approved fixed-cutoff returns');
      add(section, 'p', `${risk.daily_coverage.portfolio} eligible returns · ${risk.daily_coverage.shortfall} more needed for the minimum.`);
      renderRiskMeasures(section, risk.measures, 'Fixed-cutoff risk metrics', false);
    }
  }

  function renderRiskMetrics(section, metrics) {
    if (!metrics) return;
    add(section, 'h3', 'Observed losses');
    const observed = metrics.observed;
    const list = add(section, 'dl');
    add(list, 'dt', 'Eligible return intervals');
    add(list, 'dd', `${observed.eligible} of ${observed.requested}`);
    add(list, 'dt', 'Intervals with a loss');
    add(list, 'dd', observed.eligible ? `${observed.loss_intervals} of ${observed.eligible}` : 'Unavailable');
    add(list, 'dt', 'Worst observed interval return');
    add(list, 'dd', observed.worst ? percent(observed.worst.return_pct) : observed.eligible ? 'No loss' : 'Unavailable');
    if (observed.worst) {
      add(section, 'p', `Worst interval · ${when(observed.worst.start_at)} to ${when(observed.worst.end_at)}.`);
    }

    renderSessionPerformance(section, metrics.session_performance);
    renderCutoffCollection(section, metrics.cutoff_pilot, metrics.cutoff_returns);

    add(section, 'h3', 'Volatility, loss estimates and benchmark risk');
    if (metrics.daily_state === 'approved_series') {
      add(section, 'p', metrics.daily_start
        ? `Approved daily data · ${metrics.daily_start} to ${metrics.daily_end} · ${metrics.source}.`
        : `Approved series · ${metrics.source} · No eligible daily periods in the selected dates.`);
    } else {
      add(section, 'p', metrics.daily_state === 'invalid_series'
        ? 'The supplied daily risk series did not pass validation.'
        : 'These estimates need approved daily GBP returns. Saved Trading 212 marks may span different lengths of time.');
    }
    const coverage = metrics.daily_coverage;
    if (coverage) add(section, 'p', `Selected dates · ${observed.valuation_dates} saved valuation dates · ${coverage.portfolio} approved portfolio sessions · ${coverage.vuag} matched VUAG · ${coverage.with_rate} with a risk-free rate. ${coverage.shortfall} more approved portfolio sessions needed for the minimum.`);
    const bank = metrics.bank_rate;
    if (bank) {
      const note = add(section, 'p', `Bank Rate history verified for period openings from ${formatDay(bank.start_date)} through ${formatDay(bank.verified_through)}. `);
      const link = add(note, 'a', bank.source);
      link.href = bank.url;
    }
    add(section, 'p', `Minimum: ${metrics.minimum_daily} eligible sessions per estimate. VaR is a one-session loss cutoff. Expected shortfall averages losses at or beyond it. Fewer than five tail observations indicates thin coverage.`);
    renderRiskMeasures(section, metrics.measures, 'Daily risk metrics', true);
    renderHoldingCorrelation(section, metrics.holding_correlation);
  }
  const benchmarkRiskKeys = new Set(['beta','jensen_alpha','r_squared','correlation','tracking_error']);
  function renderRiskMeasures(section, values, label, benchmark) {
    const rows = exposureTable(section, ['Measure','Estimate','Sessions','Coverage'], label);
    const measures = new Map(values.map(metric => [metric.key, metric]));
    for (const [key, label, unit] of riskMeasures) {
      if (!benchmark && benchmarkRiskKeys.has(key)) continue;
      const metric = measures.get(key);
      if (!metric) continue;
      const row = add(rows,'tr');
      add(row,'td',label);
      const estimate = metric.value == null ? 'Unavailable' : decimal(metric.value) + unit;
      add(row,'td',metric.value_gbp == null ? estimate : `${estimate} · ${decimal(metric.value_gbp,'GBP')}`);
      add(row,'td',String(metric.n));
      const tail = metric.tail_n == null ? '' : `${metric.tail_n} tail observations${metric.tail_n < 5 ? ' · thin coverage' : ''}`;
      add(row,'td',[riskReasons[metric.reason],tail].filter(Boolean).join(' · ') || '—');
    }
  }
  function renderRiskExposure(data) {
    const section = el('risk-exposures');
    section.replaceChildren();
    add(section, 'h3', 'Current concentration');
    const report = data?.exposures;
    if (!report?.concentration) {
      add(section, 'p', 'Concentration needs an approved holdings snapshot.');
      return;
    }
    add(section, 'p', `Latest saved holdings · ${when(report.positions_as_of)}. These weights are independent of the historical date filter.`);
    const list = add(section,'dl');
    for (const measure of report.concentration) {
      const ticker = measure.top === 1 && measure.portfolio_pct != null ? report.holdings?.[0]?.ticker : null;
      const title = measure.top === 1 ? 'Largest position' : `Top ${measure.top} positions`;
      const holding = ticker ? data.positions?.find(position => position.ticker === ticker) : null;
      add(list,'dt',title + (ticker ? ` · ${holding?.name || ticker}` : '') + ' · % of portfolio');
      add(list,'dd',percent(measure.portfolio_pct));
    }
    for (const [label, value] of [
      ['Holdings HHI · securities only',report.holdings_hhi], ['Effective number of holdings',report.effective_holdings],
    ]) {
      add(list,'dt',label);
      add(list,'dd',value == null ? 'Unavailable' : decimal(value));
    }
    add(list,'dt','Available cash · % of portfolio');
    add(list,'dd',percent(report.cash_component_pct?.availableToTrade));
    if (report.missing_values) add(section,'p',`${report.missing_values} holdings lack usable GBP values.`);
    const link = add(section, 'button', 'View sector, country and currency exposures');
    link.type = 'button';
    link.className = 'holding-link';
    link.addEventListener('click', () => selectTab('exposures-tab'));
  }
  async function loadRisk(start, end) {
    riskRequest?.abort();
    const request = new AbortController();
    riskRequest = request;
    const query = start && end ? `?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}` : '';
    const status = el('risk-status');
    status.textContent = 'Loading drawdown…';
    el('risk-apply').disabled = true;
    try {
      const response = await fetch('/api/v1/portfolio/risk' + query, {credentials:'same-origin', cache:'no-store', redirect:'error', signal:request.signal});
      if (riskRequest !== request) return;
      if ([401,403].includes(response.status)) { clear(); window.dispatchEvent(new Event('meridian-session-ended')); return; }
      if (response.status === 400) {
        status.textContent = 'Choose a start date before the end date within the available UTC dates.';
        return;
      }
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (riskRequest !== request) return;
      if (data.performance_state !== 'available') throw new Error('unavailable');
      for (const [id, key] of [['risk-start','start'],['risk-end','end']]) {
        const input = el(id);
        input.min = data.earliest_date;
        input.max = data.latest_date;
        input.value = data.range[key];
      }
      status.textContent = `Selected dates · ${formatDay(data.range.start)} to ${formatDay(data.range.end)} UTC.`;
      const results = el('risk-results');
      results.replaceChildren();
      renderDrawdown(results, data.drawdown);
      renderRiskMetrics(results, data.metrics);
      riskLoaded = true;
    } catch {
      if (riskRequest === request) status.textContent = riskLoaded
        ? 'Drawdown could not be updated. Showing the last loaded range below.'
        : 'Drawdown is temporarily unavailable. Use Reset to 90 days to retry.';
    } finally {
      if (riskRequest === request) {
        riskRequest = null;
        el('risk-apply').disabled = false;
      }
    }
  }
  function renderPerformance(data) {
    const section = el('history-performance');
    section.replaceChildren();
    add(section, 'h2', 'Cash-flow-adjusted performance');
    const report = data.performance;
    if (!report) {
      add(section, 'p', 'Funding and adjusted performance are temporarily unavailable. Reload History to try again.');
      return;
    }
    add(section, 'p', 'Modified Dietz approximation using saved Trading 212 account values and timed external flows. Longer periods link eligible daily intervals. Retained dividends and interest stay in account performance.');
    const stretch = report.longest_valuation;
    add(section, 'p', stretch
      ? `Longest uninterrupted valuation stretch · ${periodRange(stretch)} UTC · ${stretch.days} saved days.`
      : 'No uninterrupted valuation stretch is available.');
    const coverage = report.funding_coverage;
    add(section, 'p', coverage
      ? `Trading 212 funding evidence · ${when(coverage.start_at)} to ${when(coverage.end_at)}. History traversal finished ${when(coverage.completed_at)}.`
      : 'A completed funding history with a usable coverage window is unavailable.');
    const results = exposureTable(section, ['Period', 'UTC dates', 'Eligible intervals', 'Adjusted return or reason'], 'Adjusted performance');
    for (const [label, item] of [
      ['Latest eligible daily interval', report.latest_eligible], ['Longest eligible stretch', report.longest_eligible],
      ['Month to date', report.month_to_date], ['Year to date', report.year_to_date],
    ]) {
      const row = add(results, 'tr');
      add(row, 'td', label);
      add(row, 'td', item ? periodRange(item) : '—');
      add(row, 'td', item ? String(item.intervals ?? 1) : '—');
      add(row, 'td', adjustedReturn(item));
    }
    renderBenchmark(section, report.benchmark);
    const funding = add(section, 'details');
    funding.id = 'history-funding';
    add(funding, 'summary', `Funding transactions · ${report.funding.length} in this window`);
    if (!report.funding.length) add(funding, 'p', 'The available history showed no funding movements in this window.');
    if (report.funding.length) {
      const events = exposureTable(funding, ['Transaction', 'Reported amount', 'Event time (London)', 'Funding treatment'], 'Funding evidence');
      const dateRows = new Set();
      for (const event of report.funding) {
        const row = add(events, 'tr');
        const day = event.at.slice(0, 10);
        if (!dateRows.has(day)) row.id = 'history-funding-' + day;
        dateRows.add(day);
        const transaction = add(add(row, 'td'), 'details');
        add(transaction, 'summary', fundingLabel(event));
        add(transaction, 'small', 'Trading 212 reference ' + event.reference);
        add(transaction, 'small', 'Provider type ' + event.kind);
        add(row, 'td', decimal(event.amount, event.currency));
        timeCell(row, event.at);
        add(row, 'td', event.signed_gbp ? 'External funding' : 'Review required');
      }
    }
    const intervals = add(section, 'details');
    const eligible = report.intervals.filter(item => item.return_pct != null).length;
    add(intervals, 'summary', `Daily return intervals · ${eligible} of ${report.intervals.length} eligible`);
    const checks = exposureTable(intervals, ['UTC dates', 'Account captures (London)', 'External flows', 'Net funding', 'Adjusted return or reason'], 'Daily return eligibility');
    for (const item of [...report.intervals].reverse()) {
      const row = add(checks, 'tr');
      add(row, 'td', periodRange(item));
      add(row, 'td', [item.start_at, item.end_at].map(time => time ? when(time) : '—').join(' to '));
      add(row, 'td', item.external_flow_count == null ? '—' : String(item.external_flow_count));
      add(row, 'td', item.net_external_flow == null ? '—' : decimal(item.net_external_flow, 'GBP'));
      add(row, 'td', adjustedReturn(item));
    }
  }
  const overviewNumber = new Intl.NumberFormat('en-GB', {minimumFractionDigits:2, maximumFractionDigits:2});
  const overviewPct = value => value == null ? 'Unavailable' : overviewNumber.format(Number(value)) + '%';
  const overviewDifference = new Intl.NumberFormat('en-GB', {minimumFractionDigits:2, maximumFractionDigits:2, signDisplay:'exceptZero'});
  function renderOverviewChart() {
    const caption = el('overview-history-caption');
    const canvas = el('overview-chart');
    const points = history?.days.slice(-overviewRange) ?? [];
    const observed = points.filter(point => point.status === 'observed');
    canvas.hidden = !observed.length;
    if (!observed.length) {
      caption.textContent = history ? 'No usable snapshots in this range.' : 'Waiting for saved history.';
      return;
    }
    caption.textContent = `${observed.length} of ${points.length} UTC days observed · includes funding`;
    const ctx = canvas.getContext?.('2d');
    if (!ctx) return;
    const { values, min, max } = chartValues(observed);
    const left = 124, right = canvas.width - 22, top = 22, bottom = canvas.height - 29;
    const x = index => left + (right - left) * index / (points.length - 1);
    const y = value => min === max ? (top + bottom) / 2
      : bottom - Number((value - min) * 10000n / (max - min)) * (bottom - top) / 10000;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.font = '13px system-ui';
    ctx.textAlign = 'right';
    ctx.fillStyle = '#a1b0c1';
    ctx.strokeStyle = '#354253';
    ctx.setLineDash([4, 4]);
    for (const value of min === max ? [min] : [min, max]) {
      ctx.fillText(historyAmount(observed[values.indexOf(value)]), left - 9, y(value) + 4, left - 23);
      ctx.beginPath(); ctx.moveTo(left, y(value)); ctx.lineTo(right, y(value)); ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.textAlign = 'center';
    for (const index of [0, Math.floor((points.length - 1) / 2), points.length - 1]) {
      ctx.fillText(formatDay(points[index].date, true), x(index), bottom + 21);
    }
    let valueIndex = 0;
    const stretches = [];
    let stretch = [];
    for (const [index, point] of points.entries()) {
      if (point.status === 'observed') {
        stretch.push([x(index), y(values[valueIndex++])]);
      } else if (stretch.length) {
        stretches.push(stretch);
        stretch = [];
      }
    }
    if (stretch.length) stretches.push(stretch);
    const fill = ctx.createLinearGradient(0, top, 0, bottom);
    fill.addColorStop(0, '#81d6bf38');
    fill.addColorStop(1, '#81d6bf00');
    for (const line of stretches) {
      if (line.length === 1) {
        ctx.fillStyle = '#81d6bf';
        ctx.beginPath(); ctx.arc(...line[0], 3, 0, 2 * Math.PI); ctx.fill();
        continue;
      }
      ctx.beginPath();
      ctx.moveTo(...line[0]);
      for (const point of line.slice(1)) ctx.lineTo(...point);
      ctx.strokeStyle = '#81d6bf';
      ctx.lineWidth = 2.4;
      ctx.stroke();
      ctx.lineTo(line.at(-1)[0], bottom);
      ctx.lineTo(line[0][0], bottom);
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
    }
  }
  function renderOverviewAllocation(data) {
    const report = data?.exposures;
    const ring = el('overview-allocation-ring');
    const legend = el('overview-allocation-legend');
    const status = el('overview-allocation-status');
    legend.replaceChildren();
    ring.hidden = true;
    status.textContent = data ? 'No usable sector allocation in this snapshot.' : 'Waiting for a saved exposure calculation.';
    const allocation = report?.sectors;
    const buckets = (allocation?.buckets ?? []).filter(row => row.value != null && compare(row.value, '0') > 0);
    if (!buckets.length || allocation.observed?.value == null) return;
    const colours = ['#78cbd0', '#a8a1ec', '#e7bd7a', '#647993', '#9babbc'];
    const classified = buckets.filter(row => row.label != null);
    const visible = classified.length === 4 ? 4 : 3;
    const groups = classified.slice(0, visible).map((row, colour) => ({
      name: row.label, label: decimal(row.value, data.currency), weight: Number(row.value), colour,
    }));
    const other = classified.slice(visible);
    if (other.length) {
      groups.push({ name: 'Other categories', label: `${other.length} more`,
        weight: other.reduce((sum, row) => sum + Number(row.value), 0), colour: 3 });
    }
    const unclassified = buckets.find(row => row.label == null);
    if (unclassified) {
      groups.push({ name: 'Unclassified', label: decimal(unclassified.value, data.currency),
        weight: Number(unclassified.value), colour: 4 });
    }
    const total = groups.reduce((sum, row) => sum + row.weight, 0);
    if (!Number.isFinite(total) || total <= 0) return;
    status.textContent = report.missing_values ? `${report.missing_values} holdings without a usable GBP mark.` : '';
    el('overview-marked-value').textContent = decimal(allocation.observed.value, data.currency);
    const list = add(legend, 'dl');
    for (const group of groups) {
      const row = add(list, 'div');
      const label = add(row, 'dt');
      add(label, 'i').setAttribute('data-colour', String(group.colour));
      add(label, 'span', group.name);
      add(row, 'dd', group.label);
    }
    ring.hidden = false;
    const canvas = el('overview-allocation');
    const ctx = canvas.getContext?.('2d');
    if (!ctx) return;
    const centre = canvas.width / 2;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.lineWidth = 13;
    let position = -Math.PI / 2;
    for (const group of groups) {
      const size = 2 * Math.PI * group.weight / total;
      const gap = groups.length === 1 ? 0 : Math.min(size / 5, .026);
      ctx.beginPath();
      ctx.strokeStyle = colours[group.colour];
      ctx.arc(centre, centre, centre - 18, position + gap, position + size - gap);
      ctx.stroke();
      position += size;
    }
  }
  function renderOverviewHoldings(data) {
    const section = el('overview-top-holdings');
    section.replaceChildren();
    const ranked = data?.exposures?.holdings?.filter(row => row.value != null).slice(0, 5) ?? [];
    if (!ranked.length) {
      add(section, 'p', data ? 'No saved GBP holding ranking is available.' : 'Waiting for a saved holdings ranking.');
      return;
    }
    const names = new Map(data.positions.map(row => [row.ticker, row.name || row.ticker]));
    const body = exposureTable(section, ['Holding', 'Reported value', '% of ISA'], 'Top five holdings');
    for (const position of ranked) {
      const row = add(body, 'tr');
      const cell = add(row, 'td');
      const label = names.get(position.ticker) || position.ticker;
      holdingLink(cell, label, {kind:'ticker', key:position.ticker, label});
      add(cell, 'small', position.ticker);
      add(row, 'td', decimal(position.value, data.currency));
      add(row, 'td', percent(position.portfolio_pct));
    }
  }
  function renderOverview() {
    renderOverviewChart();
    const report = history?.performance;
    const matched = report?.benchmark?.latest_stretch;
    el('overview-comparison').textContent = matched
      ? `${overviewPct(matched.portfolio_pct)} vs ${overviewPct(matched.benchmark_pct)}`
      : 'Unavailable';
    el('overview-comparison-period').textContent = matched
      ? `${periodRange(matched)} UTC · ${overviewDifference.format(Number(matched.difference_pp))} pp · ${matched.intervals} matched intervals · provisional`
      : 'Needs a matched portfolio and VUAG interval.';
    const drawdown = report?.drawdown;
    el('overview-drawdown').textContent = overviewPct(drawdown?.current_pct);
    el('overview-risk-period').textContent = drawdown
      ? `Worst ${overviewPct(drawdown.worst_pct)} · eligible through ${when(drawdown.as_of)}${drawdown.later_unavailable_intervals ? ` · ${drawdown.later_unavailable_intervals} newer intervals unavailable` : ''}`
      : 'Needs an eligible cash-flow-adjusted interval.';
  }
  function renderOverviewSnapshot(data) {
    renderOverviewAllocation(data);
    renderOverviewHoldings(data);
    el('overview-holding-count').textContent = `${data.positions.length} reported holdings`;
    const pnl = data.investments.unrealizedProfitLoss;
    const direction = pnl == null ? 0 : compare(pnl, '0');
    el('unrealised-pnl').setAttribute('data-tone', direction < 0 ? 'loss' : direction > 0 ? 'gain' : '');
    el('overview-account-time').textContent = `Captured ${when(data.account_retrieval.retrieval_completed_at)}`;
    const exposure = data.exposures;
    const top = exposure?.concentration?.find(row => row.top === 5);
    el('overview-concentration').textContent = overviewPct(top?.portfolio_pct);
    el('overview-exposure-time').textContent = top?.portfolio_pct != null && exposure?.positions_as_of
      ? `% of ISA value · holdings captured ${when(exposure.positions_as_of)}`
      : 'Needs a complete approved holdings snapshot.';
  }
  function renderHistory(data) {
    history = data;
    setChangesDates();
    renderOverview();
    fundingDays.clear();
    for (const event of data.performance?.funding || []) {
      const day = event.at.slice(0, 10);
      fundingDays.set(day, (fundingDays.get(day) || 0) + 1);
    }
    el('history-funding-note').hidden = fundingDays.size === 0;
    renderPerformance(data);
    const body = document.createDocumentFragment();
    let observed = 0, missing = 0, unavailable = 0;
    for (const point of [...data.days].reverse()) {
      const row = add(body, 'tr');
      add(row, 'th', formatDay(point.date) + (point.date === data.end_date ? ' (today so far)' : '')).setAttribute('scope', 'row');
      if (point.status === 'observed') {
        observed++;
        add(row, 'td', historyAmount(point));
        timeCell(row, point.captured_at);
        timeCell(row, point.observed_at);
      } else {
        if (point.status === 'missing') missing++; else unavailable++;
        add(row, 'td', historyLabel(point)).setAttribute('colspan', '3');
      }
    }
    el('history-body').replaceChildren(body);
    el('history-results').hidden = false;
    el('history-status').textContent = `${periodRange(data)} UTC · ${observed} of ${data.days.length} days observed · ${missing} missing${unavailable ? ' · ' + unavailable + ' unavailable' : ''}. Read at ${when(data.as_of)}.`;
    const latest = data.days.findLastIndex(point => point.status === 'observed');
    inspectDay(latest === -1 ? data.days.length - 1 : latest);
  }
  async function loadHistory() {
    if (historyRequest) return;
    const request = new AbortController();
    historyRequest = request;
    el('reload-history').disabled = true;
    el('history-status').textContent = 'Loading saved daily values…';
    try {
      const response = await fetch('/api/v1/portfolio/history', {credentials:'same-origin', cache:'no-store', redirect:'error', signal:request.signal});
      if (historyRequest !== request) return;
      if ([401,403].includes(response.status)) { clear(); window.dispatchEvent(new Event('meridian-session-ended')); return; }
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (historyRequest !== request) return;
      if (data.source !== 'trading212' || data.basis !== 'broker_reported' || data.currency !== 'GBP' || data.days?.length !== 90) throw new Error('invalid');
      renderHistory(data);
    } catch {
      if (historyRequest === request) {
        if (!history) {
          renderOverview();
          el('overview-comparison-period').textContent = 'Saved History could not be loaded.';
          el('overview-risk-period').textContent = 'Saved History could not be loaded.';
          el('overview-history-caption').textContent = 'Saved history could not be loaded.';
        }
        el('history-status').textContent = history ? 'Reload failed. Showing the previously loaded observations.' : 'Saved history could not be loaded. Use Reload history to try again.';
      }
    } finally {
      if (historyRequest === request) {
        historyRequest = null;
        el('reload-history').disabled = false;
      }
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
  function setChangesDates() {
    const start = el('changes-start'), end = el('changes-end');
    start.max = end.max = new Date().toISOString().slice(0, 10);
    if (start.value || end.value || !history) return;
    const recent = history.days.filter(day => day.status === 'observed').slice(-2);
    if (recent.length === 2) {
      start.value = recent[0].date;
      end.value = recent[1].date;
    }
  }
  const signed = (value, currency) => value != null && compare(value, '0') > 0
    ? '+' + decimal(value, currency) : decimal(value, currency);

  function renderChanges(data) {
    const section = el('changes-results');
    section.replaceChildren();
    for (const [label, endpoint] of [['Start', data.start], ['End', data.end]]) {
      add(section, 'h3', `${label} · ${formatDay(endpoint.date)} UTC`);
      if (endpoint.status === 'missing') {
        add(section, 'p', 'No approved Trading 212 snapshot was saved for this date.');
      } else if (endpoint.status === 'unavailable') {
        add(section, 'p', `A snapshot was saved at ${when(endpoint.observed_at)}. Its GBP holdings or capture evidence could not be verified.`);
      } else {
        add(section, 'p', `Holdings captured ${when(endpoint.positions_captured_at)} · Account captured ${when(endpoint.account_captured_at)} · Saved observation ${when(endpoint.observed_at)}`);
        add(section, 'p', `Weight denominator (reported ISA value) · ${decimal(endpoint.portfolio_denominator, 'GBP')}`);
      }
    }
    if (data.start.status !== 'observed' || data.end.status !== 'observed') return;

    add(section, 'h3', 'Observed changes in reported holding value');
    add(section, 'p', 'Ranked by absolute GBP change. Quantity flags compare the saved positions. These snapshots provide no reliable split of the change between price, FX and trading.');
    const labels = {added:'Added', closed:'Closed', quantity_changed:'Quantity changed',
      quantity_unchanged:'Quantity unchanged', quantity_unavailable:'Quantity unavailable',
      identity_conflict:'Listing identity changed'};
    const body = exposureTable(section, ['Holding', 'GBP change', 'Start value', 'End value',
      'Start quantity', 'End quantity', 'Start weight', 'End weight', 'Position status'], 'Holding changes');
    const links = new Map();
    for (const [index, holding] of data.holdings.entries()) {
      const row = add(body, 'tr');
      const evidence = add(add(row, 'td'), 'details');
      evidence.id = 'change-holding-' + index;
      const summary = add(evidence, 'summary', holding.end.name || holding.start.name || holding.ticker);
      links.set(holding.ticker, {evidence, summary});
      add(evidence, 'small', holding.ticker);
      for (const [key, side, label] of [['start', holding.start, 'Start'], ['end', holding.end, 'End']]) {
        const captured = when(data[key].positions_captured_at);
        add(evidence, 'small', side.present
          ? `${label} · ${side.isin || holding.ticker} · ${captured}`
          : `${label} · No open position at ${captured}`);
      }
      add(row, 'td', signed(holding.value_change, 'GBP'));
      for (const field of ['value','quantity','weight_pct']) {
        for (const side of [holding.start, holding.end]) {
          add(row, 'td', field === 'weight_pct' ? percent(side[field])
            : decimal(side[field], field === 'value' ? 'GBP' : undefined));
        }
      }
      add(row, 'td', labels[holding.status]);
    }
    if (!links.size) add(section, 'p', 'Neither snapshot contains open positions.');

    const cashLabels = {availableToTrade:'Available to trade', inPies:'Cash in pies', reservedForOrders:'Reserved for orders'};
    function weightChanges(title, rows) {
      const body = exposureTable(section, ['Reported exposure', 'Start value', 'End value', 'GBP change',
        'Start weight', 'End weight', 'Weight change'], title);
      for (const item of rows) {
        const row = add(body, 'tr'), cell = add(row, 'td');
        const label = cashLabels[item.label] ?? item.label ?? 'Unclassified';
        if (item.members.length) {
          const detail = add(cell, 'details');
          add(detail, 'summary', label);
          const list = add(detail, 'ul');
          for (const member of item.members) {
            const entry = add(list, 'li');
            const target = links.get(member.ticker);
            if (target) {
              const link = add(entry, 'a', member.ticker);
              link.href = '#' + target.evidence.id;
              link.addEventListener('click', () => {
                target.evidence.open = true;
                target.summary.focus?.();
              });
            } else add(entry, 'span', member.ticker);
            add(entry, 'small', `${decimal(member.start_value ?? '0', 'GBP')} → ${decimal(member.end_value ?? '0', 'GBP')}`);
          }
        } else cell.textContent = label;
        for (const field of ['start_value', 'end_value']) add(row, 'td', decimal(item[field], 'GBP'));
        add(row, 'td', signed(item.value_change, 'GBP'));
        for (const field of ['start_weight_pct', 'end_weight_pct']) add(row, 'td', percent(item[field]));
        add(row, 'td', signed(item.weight_change_pp) + ' pp');
      }
    }
    add(section, 'h3', 'Cash and concentration');
    add(section, 'p', 'Cash components come from the two account captures. Top five uses the largest reported holdings at each endpoint. Weight changes are differences between displayed weights.');
    const accountChanges = [...data.cash, ...(data.top_five ? [data.top_five] : [])];
    if (accountChanges.length) weightChanges('Cash and concentration changes', accountChanges);
    const missing = Object.keys(cashLabels).filter(key => !data.cash.some(row => row.label === key)).map(key => cashLabels[key]);
    if (!data.top_five) missing.push('Top five holdings');
    if (missing.length) add(section, 'p', `Comparable data unavailable · ${missing.join(', ')}`);

    const dimensions = {sectors:'Sectors', issuer_domiciles:'Country · direct issuer domicile',
      fund_markets:'Country · fund market allocation'};
    add(section, 'h3', 'Classification changes');
    add(section, 'p', 'Coverage is classified GBP value out of observed GBP holding value within each view. Buckets reflect the classifications saved at each endpoint and can move as coverage changes.');
    for (const allocation of data.allocations) {
      const title = dimensions[allocation.dimension];
      add(section, 'h4', title);
      const coverage = side => `${decimal(allocation[side + '_classified'], 'GBP')} of ${decimal(allocation[side + '_observed'], 'GBP')}`;
      add(section, 'p', `Classified value · Start ${coverage('start')} · End ${coverage('end')}`);
      if (!allocation.comparable) add(section, 'p', 'Comparable saved allocations or complete GBP holding values are unavailable at one or both endpoints.');
      else if (allocation.buckets.length) weightChanges(title, allocation.buckets);
      else add(section, 'p', 'No observed allocation buckets in this view.');
    }
  }

  async function loadChanges(start, end) {
    changesRequest?.abort();
    const request = new AbortController();
    changesRequest = request;
    const status = el('changes-status');
    el('changes-results').replaceChildren();
    status.textContent = 'Loading saved endpoints…';
    el('changes-apply').disabled = true;
    try {
      const response = await fetch(`/api/v1/portfolio/changes?start=${start}&end=${end}`,
        {credentials:'same-origin', cache:'no-store', redirect:'error', signal:request.signal});
      if (changesRequest !== request) return;
      if ([401,403].includes(response.status)) { clear(); window.dispatchEvent(new Event('meridian-session-ended')); return; }
      if (!response.ok) throw new Error('changes_unavailable');
      const data = await response.json();
      if (changesRequest !== request) return;
      if (data.method !== 'observed_portfolio_changes_v1' || data.start.date !== start || data.end.date !== end) {
        throw new Error('changes_mismatch');
      }
      renderChanges(data);
      status.textContent = data.start.status === 'observed' && data.end.status === 'observed'
        ? '' : 'Both dates need usable snapshots for a comparison.';
    } catch {
      if (changesRequest === request) {
        el('changes-results').replaceChildren();
        status.textContent = 'The comparison could not be loaded. Try again.';
      }
    } finally {
      if (changesRequest === request) {
        changesRequest = null;
        el('changes-apply').disabled = false;
      }
    }
  }

  function exposureCells(row, exposure, currency) {
    add(row, 'td', decimal(exposure.value, currency));
    add(row, 'td', percent(exposure.portfolio_pct));
    add(row, 'td', percent(exposure.invested_pct));
  }
  function renderClassification(section, dimension, title, description, data, columns) {
    const allocation = data.exposures[dimension];
    add(section, 'h3', title);
    add(section, 'p', description);
    if (!allocation?.buckets.length) {
      add(section, 'p', allocation ? 'No holdings in this view.' : 'This saved snapshot predates sourced classifications.');
      return;
    }
    add(section, 'p', `Classified: ${decimal(allocation.classified.value, data.currency)} of ${decimal(allocation.observed.value, data.currency)} in observed holdings for this view · ${percent(allocation.classified.invested_pct)} of broker investment value.`);
    const body = exposureTable(section, ['Allocation', ...columns], title);
    for (const bucket of allocation.buckets) {
      const row = add(body, 'tr'), cell = add(row, 'td');
      const label = bucket.label ?? 'Unclassified';
      holdingLink(cell, label, {kind:'classification', dimension, key:bucket.label, label:`${title} · ${label}`});
      const count = Object.keys(bucket.members).length;
      add(cell, 'small', `${count} contributing ${count === 1 ? 'holding' : 'holdings'}`);
      exposureCells(row, bucket, data.currency);
    }
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

    renderClassification(section, 'sectors', 'Equity sectors',
      'Direct shares use reviewed principal-business sectors. Funds use dated manager weights. ICB and other manager-specific categories are labelled separately because their definitions differ. Unclassified includes fund portions without eligible sector data.',
      data, columns);
    renderClassification(section, 'issuer_domiciles', 'Direct shares · issuer domicile',
      'Country of incorporation from issuer filings. Coverage shows the direct-share amounts in this view.',
      data, columns);
    renderClassification(section, 'fund_markets', 'Funds · underlying markets',
      'Published market weights from fund managers. Regional figures keep their regional label wherever country detail is unavailable. Unclassified includes unallocated fund weight.',
      data, columns);

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
    window.meridianPlanning?.clear();
    amounts.forEach(id => el(id).textContent = '—');
    el('holdings-body').replaceChildren(); el('holding-count').textContent = '';
    if (el('cash-reconciliation')) { el('cash-reconciliation').replaceChildren(); el('cash-reconciliation').textContent = '—'; }
    el('snapshot-time').textContent = '—'; el('snapshot-status').textContent = ''; el('refresh-status').textContent = '';
    el('portfolio-exposures')?.replaceChildren();
    historyRequest?.abort(); historyRequest = null; history = null; overviewRequested = false;
    for (const id of ['overview-comparison','overview-drawdown','overview-concentration']) el(id).textContent = '—';
    setOverviewRange(30);
    for (const id of ['overview-chart', 'overview-allocation']) {
      const canvas = el(id);
      canvas.getContext?.('2d')?.clearRect(0, 0, canvas.width, canvas.height);
    }
    renderOverviewAllocation(null);
    renderOverviewHoldings(null);
    el('overview-marked-value').textContent = '';
    el('unrealised-pnl').setAttribute('data-tone', '');
    for (const id of ['overview-holding-count','overview-account-time','overview-comparison-period','overview-risk-period','overview-exposure-time']) el(id).textContent = '';
    changesRequest?.abort(); changesRequest = null;
    el('changes-results').replaceChildren();
    el('changes-status').textContent = '';
    el('changes-start').value = ''; el('changes-end').value = '';
    el('changes-apply').disabled = false;
    riskRequest?.abort(); riskRequest = null; riskLoaded = false;
    el('risk-results').replaceChildren();
    el('risk-exposures').replaceChildren();
    el('risk-status').textContent = '';
    el('risk-start').value = ''; el('risk-end').value = '';
    el('risk-apply').disabled = false;
    el('history-body').replaceChildren();
    fundingDays.clear();
    el('history-performance').replaceChildren();
    el('history-funding-note').hidden = true;
    el('history-point').textContent = '';
    el('history-status').textContent = '';
    el('history-chart').getContext?.('2d')?.clearRect(0, 0, 960, 264);
    el('history-details').open = false;
    el('history-results').hidden = true;
    el('reload-history').disabled = false;
    selectTab('axis-tab');
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
    const classification = holdingScope?.kind === 'classification' ? report?.[holdingScope.dimension] : null;
    const contributions = classification?.buckets.find(bucket => bucket.label === holdingScope.key)?.members;
    const inScope = row => {
      if (holdingScope?.kind === 'classification') return Object.hasOwn(contributions || {}, row.ticker);
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
      name.append(ticker);
      if (contributions) {
        const contribution = contributions[row.ticker];
        add(name, 'small', `Bucket contribution: ${decimal(contribution.value, snapshot.currency)} · ${percent(contribution.holding_pct)} of position`);
        const source = classification.sources[row.ticker];
        if (source) {
          const link = add(add(name, 'small'), 'a', `Source · ${formatDay(source.as_of)}`);
          link.href = source.url;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
        }
      }
      tr.append(name);
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
      window.meridianPlanning?.setSnapshot(data);
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
      renderOverviewSnapshot(data);
      if (active && !overviewRequested && !history && !historyRequest) {
        overviewRequested = true;
        void loadHistory();
      }
      if (!el('risk-panel').hidden) renderRiskExposure(data);
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
  function setOverviewRange(days) {
    overviewRange = days;
    for (const range of [30, 90]) el(`overview-${range}d`).setAttribute('aria-pressed', String(days === range));
    renderOverviewChart();
  }
  for (const range of [30, 90]) el(`overview-${range}d`).addEventListener('click', () => setOverviewRange(range));
  for (const [tab] of tabs) el(tab).addEventListener('click', () => selectTab(tab));
  el('clear-holding-scope').addEventListener('click', () => showHoldings(null));
  el('holding-search').addEventListener('input',renderHoldings); el('holding-sort').addEventListener('change',renderHoldings);
  el('reload-snapshot').addEventListener('click',load);
  el('reload-history').addEventListener('click',loadHistory);
  for (const [button, tab] of [
    ['overview-history', 'history-tab'],
    ['overview-chart-history', 'history-tab'],
    ['overview-risk', 'risk-tab'],
    ['overview-exposures', 'exposures-tab'],
    ['overview-allocation-exposures', 'exposures-tab'],
    ['overview-holdings', 'holdings-tab'],
  ]) {
    el(button).addEventListener('click', () => {
      selectTab(tab);
      el(tab).focus?.();
    });
  }
  el('changes-filter').addEventListener('submit', event => {
    event.preventDefault();
    const start = el('changes-start').value, end = el('changes-end').value;
    if (!start || !end || start >= end) {
      el('changes-status').textContent = 'Choose a start date before the end date.';
      return;
    }
    void loadChanges(start, end);
  });
  el('risk-filter').addEventListener('submit', event => {
    event.preventDefault();
    const start = el('risk-start').value;
    const end = el('risk-end').value;
    if (!start || !end || start >= end) {
      el('risk-status').textContent = 'Choose a start date before the end date.';
      return;
    }
    void loadRisk(start, end);
  });
  el('risk-reset').addEventListener('click', () => { void loadRisk(); });
  el('history-chart').addEventListener('click', event => {
    if (!history) return;
    const chart = el('history-chart');
    const pixel = event.offsetX * chart.width / chart.clientWidth;
    inspectDay(Math.round((pixel - plot.left) * (history.days.length - 1) / (plot.right - plot.left)));
  });
  el('history-chart').addEventListener('keydown', event => {
    if (!history || !['ArrowLeft','ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    inspectDay(historyIndex + (event.key === 'ArrowLeft' ? -1 : 1));
  });
  el('refresh-broker').addEventListener('click',refreshBroker);
  document.addEventListener('visibilitychange', () => {
    clearTimeout(timer);
    if (active && !document.hidden) void load();
  });
  window.meridianSnapshot = {load,clear,start};
})();
