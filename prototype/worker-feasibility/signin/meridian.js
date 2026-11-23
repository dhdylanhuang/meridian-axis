(() => {
  const el = id => document.getElementById(id);
  const add = (parent, tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    parent.append(node);
    return node;
  };
  const button = (parent, label, handler, pressed) => {
    const node = add(parent, 'button', label);
    node.type = 'button';
    if (pressed != null) node.setAttribute('aria-pressed', String(pressed));
    node.addEventListener('click', handler);
    return node;
  };
  const { day, timestamp } = window.meridianDates;
  const pct = value => value == null ? 'Unavailable' : Number(value).toFixed(1).replace('-', '−') + '%';
  const money = value => {
    if (value == null) return 'Unavailable';
    const [whole, fraction] = value.replace(/^-/, '').split('.');
    return (value.startsWith('-') ? '−' : '') + '£' +
      whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (fraction == null ? '' : '.' + fraction);
  };
  const coeff = value => (Math.abs(value) < .005 ? 0 : value).toFixed(2).replace('-', '−');
  const reasons = {
    awaiting_approved_holding_series: 'Approved GBP total-return closes for held listings are missing. Listing and session mappings, split and dividend treatment, eligible prior prices and compatible FX must be reviewed.',
    cutoff_evidence_unavailable: 'Trading 212 cutoff holding marks could not be read. Dated capital remains available.',
    missing_cutoff_marks: 'No usable adjacent 22:00 UTC holding marks',
    reviewed_evidence_invalid: 'The reviewed holdings evidence did not pass validation.',
    needs_two_holdings: 'At least two holdings require enough usable, variable GBP returns.',
    insufficient_common_sample: 'The eligible holdings have too few complete shared daily returns.',
    insufficient_session_grid: 'The selected window needs more scheduled trading sessions.' ,
    missing_gbp_value: 'No comparable saved GBP position value',
    no_positive_value: 'No positive market value',
    position_ineligible: 'Position type or quantity is ineligible',
    missing_approved_series: 'No approved GBP total-return series',
    insufficient_holding_returns: 'Too few usable daily returns',
    constant_holding: 'Constant holding returns',
    constant_on_common_sample: 'Constant on the common sample',
    insufficient_matched_returns: 'Too few matched returns in this window.',
    constant_pair: 'At least one holding has zero variance in this window.',
  };
  const colours = ['#8db9df','#d4967b','#9ec4a0','#bca4df','#d3b777','#d895ad','#81bbb2'];
  let open = false, snapshot = null, report = null, pending = null;
  let checkedSlot = null;
  function cutoffSlot() {
    const elapsed = Date.now() - (22 * 60 + 2) * 60_000;
    const day = new Date(elapsed).getUTCDay();
    return Math.floor(elapsed / 86_400_000) - (day === 0 ? 2 : day === 6 ? 1 : 0);
  }
  let horizon = 90, order = 'global', cluster = -1, exclusionOpen = false, expanded = true;
  let matrixPanel, capitalPanel, detailPanel;
  const toolbar = el('meridian-window');
  const status = el('meridian-status');
  const result = el('meridian-result');
  const controls = [30,90,252].map(value => button(toolbar, String(value), () => {
    if (horizon === value) return;
    horizon = value;
    syncControls();
    report = null;
    void load();
  }, value === horizon));
  const syncControls = () => controls.forEach(node => node.setAttribute('aria-pressed', String(Number(node.textContent) === horizon)));
  const stamp = source => source?.account_retrieval?.retrieval_completed_at;
  const holdingsStamp = source => source?.positions_retrieval?.retrieval_completed_at;

  async function load(pair, pairOnly = false) {
    pending?.abort();
    if (!open || !snapshot) return;
    const request = new AbortController();
    pending = request;
    const previous = report;
    const requestedSlot = cutoffSlot();
    if (!pair) result.replaceChildren();
    status.textContent = pair ? 'Loading rolling windows…' : 'Loading approved evidence…';
    const query = pair ? `&pair=${pair.join(',')}&basis=${pairOnly ? 'pair' : 'common'}` : '';
    try {
      const response = await fetch(`/api/v1/portfolio/meridian?window=${horizon}${query}`, {
        credentials:'same-origin', cache:'no-store', redirect:'error', signal:request.signal,
      });
      if (pending !== request) return;
      if ([401,403].includes(response.status)) {
        window.dispatchEvent(new Event('meridian-session-ended'));
        return;
      }
      if (response.status === 409 && pair) { void load(); return; }
      if (!response.ok) throw new Error('unavailable');
      const next = await response.json();
      if (pending !== request) return;
      if (next.method !== 'meridian_common_sample_v1' || next.window !== horizon) throw new Error('invalid');
      if (pair && (previous.holdings_time !== next.holdings_time || previous.capture_time !== next.capture_time ||
          previous.latest_scheduled_date !== next.latest_scheduled_date ||
          pair.some((k,i) => previous.holdings[k]?.ticker !== next.holdings?.[next.pair?.[i]]?.ticker))) {
        void load();
        return;
      }
      status.textContent = next.descriptive && next.matrix ? `Descriptive view · ${next.n} matched returns · reliable estimates require ${next.minimum}.` : '';
      report = next;
      checkedSlot = requestedSlot;
      if (pair) {
        const basisFocus = detailPanel.contains(document.activeElement);
        matrix();
        history();
        const focus = basisFocus ? detailPanel.querySelector('[aria-pressed="true"]')
          : matrixPanel.querySelector(`[data-pair="${pair.join(',')}"]`);
        focus?.focus({preventScroll:true});
        detailPanel.scrollIntoView({block:'nearest'});
      } else {
        cluster = (next.clusters ?? []).findIndex(group => group.join(',') === next.selected_cluster?.join(','));
        expanded = true;
        render();
      }
    } catch (error) {
      if (pending === request) status.textContent = pair ? 'Rolling history could not be loaded. The prior selection is still displayed.' : 'The Meridian could not load approved evidence.';
    } finally {
      if (pending === request) pending = null;
    }
  }

  function exclusions(parent) {
    const details = add(parent, 'details', null, 'meridian-exclusions');
    details.open = exclusionOpen;
    details.addEventListener('toggle', () => { exclusionOpen = details.open; });
    add(details, 'summary', `Excluded holdings · ${pct(report.excluded_pct)} of ISA`);
    if (!report.excluded.length) { add(details, 'p', 'All saved holdings are eligible for this window.'); return; }
    const list = add(details, 'ul');
    for (const h of report.excluded) {
      add(list, 'li', `${h.name} (${h.ticker}) · ${pct(h.capital)} · ${reasons[h.reason]} · ${h.n} usable returns`);
    }
  }

  const brokerBasis = () => report.price_basis === 'trading212_fixed_cutoff_gbp_price_v1';

  function render() {
    result.replaceChildren();
    const summary = add(result, 'dl', null, 'meridian-coverage');
    for (const [label,value] of [
      ['Holdings as of', timestamp(report.holdings_time)],
      [report.scheduled ? 'Common eligible sessions' : 'Approved holding sessions', `${report.n} / ${report.window}`],
      [report.matrix || report.covered_pct === '0' ? 'Covered risky holdings' : 'Risky holdings with eligible series', pct(report.covered_pct)],
      ['GBP cash available to trade', pct(report.cash_pct)],
    ]) {
      const cell = add(summary, 'div');
      add(cell,'dt',label); add(cell,'dd',value);
    }
    if (brokerBasis()) {
      const scheduled = report.latest_scheduled_date ? ` · Latest scheduled slot ${day(report.latest_scheduled_date)}` : '';
      add(result, 'p', `Trading 212 · 22:00 UTC capture window · GBP price returns${scheduled}. Quote age and corporate-action adjustments are unverified.`, 'meridian-basis');
    }
    exclusions(result);
    const grid = add(result, 'div', null, 'meridian-grid');
    matrixPanel = add(grid, 'section', null, 'meridian-panel');
    capitalPanel = add(grid, 'section', null, 'meridian-panel');
    detailPanel = add(result, 'section', null, 'meridian-panel meridian-history');
    matrix();
    capital();
    history();
  }

  function matrix() {
    matrixPanel.replaceChildren();
    const head = add(matrixPanel, 'div', null, 'meridian-panel-head');
    add(head, 'h2', 'Holdings correlation');
    if (!report.matrix) {
      add(matrixPanel, 'p', reasons[report.state]);
      return;
    }
    const toggle = add(head, 'div', null, 'segmented');
    for (const [mode,label] of [['global','Clustered'], ['sector','Sector order']]) {
      button(toggle, label, () => { order = mode; matrix(); matrixPanel.querySelector('[aria-pressed=true]')?.focus(); }, order === mode);
    }
    add(matrixPanel, 'p', order === 'global' ? (brokerBasis() ? 'Global average linkage · GBP daily log price returns' : 'Global average linkage · GBP daily log returns') : 'Average linkage within each sector');
    const ordering = order === 'global' ? report.order : report.sector_order;
    const sectors = [...new Set(report.holdings.map(h => h.sector))].sort();
    const colour = k => colours[sectors.indexOf(report.holdings[k].sector) % colours.length];
    add(matrixPanel, 'p', 'Swipe across to compare holdings. Tap a cell to inspect the pair.', 'meridian-swipe');
    const tableWrap = add(matrixPanel, 'div', null, 'meridian-heat-wrap');
    tableWrap.setAttribute('role', 'region');
    tableWrap.setAttribute('aria-label', 'Holdings correlation matrix, scrollable');
    tableWrap.tabIndex = 0;
    const table = add(tableWrap, 'div', null, 'meridian-heat');
    table.style.setProperty('--holdings', ordering.length);
    add(table, 'span'); add(table, 'span', 'Holding');
    for (const k of ordering) {
      const col = add(table, 'span', report.holdings[k].ticker, 'meridian-col');
      col.style.setProperty('--sector',colour(k));
    }
    const selected = report.clusters[cluster] ?? [];
    const describe = (a,b) => `${report.holdings[a].name} × ${report.holdings[b].name} · ρ ${coeff(report.matrix[a][b])} · ${report.n} matched returns`;
    const pair = report.pair;
    const readout = add(matrixPanel, 'p', describe(...pair), 'meridian-readout');
    const gridButtons = new Map();
    ordering.forEach((a, row) => {
      const group = order === 'global' ? report.clusters.findIndex(g => g[0] === a) : -1;
      if (group >= 0) {
        const members = report.clusters[group];
        const bracket = button(table, String(group+1), () => selectGroup(group, '.meridian-branch'), group === cluster);
        bracket.className = 'meridian-branch';
        bracket.setAttribute('aria-label', `Cluster ${group+1} · ${members.map(k => report.holdings[k].name).join(', ')}`);
        bracket.style.gridColumn = '1';
        bracket.style.gridRow = `${row+2}/span ${members.length}`;
      }
      const name = add(table,'span',report.holdings[a].name,'meridian-row');
      name.style.setProperty('--sector',colour(a));
      name.style.gridRow = row+2;
      name.style.gridColumn = '2';
      name.title = report.holdings[a].name;
      ordering.forEach((b,col) => {
        const rho = report.matrix[a][b];
        const isSelected = pair.includes(a) && pair.includes(b) && a !== b;
        const cell = a === b ? add(table,'span','1.00') : button(table,coeff(rho),() => void load([a,b]),isSelected);
        const neutral = [34,46,52], endpoint = rho > 0 ? [124,207,186] : [165,92,77];
        cell.style.backgroundColor = `rgb(${neutral.map((v,i) => Math.round(v + (endpoint[i]-v)*Math.abs(rho))).join(',')})`;
        cell.style.color = rho > .48 ? '#111a20' : '#f0f5f7';
        cell.style.gridRow = row+2;
        cell.style.gridColumn = col+3;
        cell.className = 'meridian-cell';
        if (order === 'global' && selected.includes(a) && selected.includes(b)) cell.classList.add('meridian-cluster-cell');
        cell.title = describe(a,b);
        if (a === b) return;
        cell.setAttribute('aria-label', cell.title);
        cell.dataset.pair = `${a},${b}`;
        cell.tabIndex = a === pair[0] && b === pair[1] ? 0 : -1;
        gridButtons.set(`${row},${col}`,cell);
        const inspect = () => { readout.textContent = cell.title; };
        cell.addEventListener('focus', inspect);
        cell.addEventListener('pointerenter', inspect);
        cell.addEventListener('keydown', event => {
          const move = {ArrowUp:[-1,0],ArrowDown:[1,0],ArrowLeft:[0,-1],ArrowRight:[0,1]}[event.key];
          if (!move) return;
          event.preventDefault();
          const [dr,dc] = move;
          let r = row+dr, c = col+dc;
          if (r===c) { r+=dr; c+=dc; }
          const next = gridButtons.get(`${r},${c}`);
          if (!next) return;
          const prior = table.querySelector('[tabindex="0"]');
          if (prior) prior.tabIndex = -1;
          next.tabIndex = 0; next.focus();
        });
      });
    });
    const legend = add(matrixPanel, 'div', null, 'meridian-legend');
    add(legend,'span','−1'); add(legend,'i'); add(legend,'span','+1');
    for (const [i,sector] of sectors.entries()) {
      const label = add(legend,'span',sector,'meridian-sector');
      label.style.setProperty('--sector',colours[i % colours.length]);
    }
  }

  function selectGroup(value, focus) {
    cluster = value;
    expanded = true;
    matrix();
    capital();
    result.querySelector(`${focus}[aria-pressed="true"]`)?.focus({preventScroll:true});
  }

  function bar(parent, value, risk, min, max, reason) {
    const cell = add(parent,'span',null,'meridian-bar');
    if (value == null) { cell.textContent = reason; return; }
    const align = x => 100 * (x-min)/(max-min);
    const track = add(cell,'span',null,'meridian-track');
    track.setAttribute('aria-hidden','true');
    const fill = add(track,'i',null,risk ? (Number(value)<0 ? 'risk negative' : 'risk') : '');
    fill.style.left = `${Math.min(align(0),align(Number(value)))}%`;
    fill.style.width = `${Math.abs(align(Number(value))-align(0))}%`;
    if (risk) {
      const zero = add(track,'b');
      zero.style.left = `${align(0)}%`;
    }
    add(cell,'strong',pct(value));
  }

  function capital() {
    capitalPanel.replaceChildren();
    add(capitalPanel,'h2','Capital & risk');
    add(capitalPanel,'p',`${money(report.isa)} ISA · Account captured ${timestamp(report.capture_time)}`);
    const clusterControls = add(capitalPanel, 'div', null, 'segmented meridian-clusters');
    for (const [i,members] of (report.clusters ?? []).entries()) {
      const label = `Cluster ${i+1} · ${members.map(k => report.holdings[k].ticker).join(' / ')}`;
      const control = button(clusterControls,label,() => selectGroup(i,'.meridian-cluster-choice'),i===cluster);
      control.className = 'meridian-cluster-choice';
    }
    const table = add(capitalPanel,'div',null,'meridian-comparison');
    const headers = add(table,'div',null,'meridian-comparison-row meridian-comparison-head');
    for (const title of ['Holding / group','Capital · % of total ISA','Risk contribution · % of covered basket variance']) add(headers,'span',title);
    const totals = report.group_totals?.[cluster];
    const risk = report.risk ?? [];
    const scale = [...risk, ...((report.group_totals ?? []).flatMap(g => [g.risk ?? 0,g.other_risk ?? 0]))];
    const min = Math.min(-10, Math.floor(Math.min(0,...scale)/10)*10);
    const max = Math.max(100, Math.ceil(Math.max(0,...scale)/10)*10);
    const capitalValues = [report.covered_pct, report.excluded_pct, report.cash_pct, report.residual_pct,
      ...(report.holdings ?? []).map(h => h.capital)].map(Number);
    const capitalMin = Math.min(0, ...capitalValues);
    const capitalMax = Math.max(100, ...capitalValues);
    const reason = report.descriptive ? 'Descriptive view only' : report.matrix ? 'Basket variance unavailable' : 'No approved common covariance';
    const row = (label, value, contribution, why, section = table, className = '') => {
      const line = add(section,'div',null,`meridian-comparison-row ${className}`);
      const name = add(line,'span');
      if (typeof label === 'string') name.textContent = label;
      else name.append(label);
      bar(line,value,false,capitalMin,capitalMax, 'GBP value unavailable');
      bar(line,contribution,true,min,max,why ?? reason);
      return line;
    };
    if (totals) {
      const expand = document.createElement('button');
      expand.type = 'button';
      expand.textContent = `${expanded ? '▾' : '▸'} Cluster ${cluster+1} total`;
      expand.setAttribute('aria-expanded',String(expanded));
      expand.setAttribute('aria-controls','meridian-members');
      row(expand,totals.capital,totals.risk,undefined,table,'meridian-total');
      const members = add(table,'div');
      members.id = 'meridian-members'; members.hidden = !expanded;
      for (const k of report.clusters[cluster]) {
        const h = report.holdings[k];
        row(`${h.ticker} · ${h.sector}`,h.capital,risk[k],undefined,members);
      }
      expand.addEventListener('click',() => {
        expanded = !expanded; members.hidden = !expanded;
        expand.setAttribute('aria-expanded',String(expanded));
        expand.textContent = `${expanded ? '▾' : '▸'} Cluster ${cluster+1} total`;
      });
      row('Other covered holdings',totals.other_capital,totals.other_risk);
    } else {
      row(report.matrix || report.covered_pct === '0' ? 'Covered risky holdings' : 'Eligible risky holdings',report.covered_pct,report.risk ? 100 : null);
    }
    row('Excluded holdings',report.excluded_pct,null,'Outside covered basket');
    row(`Cash available · ${money(report.cash)}`,report.cash_pct,null,'Outside risky basket');
    row('Snapshot difference',report.residual_pct,null,'Outside covered basket');
    const scaleRow = add(table, 'div', null, 'meridian-comparison-row meridian-comparison-head meridian-axis');
    add(scaleRow, 'span');
    add(scaleRow, 'span', `${pct(capitalMin)} to ${pct(capitalMax)}`);
    if (risk.length) add(scaleRow, 'span', `${pct(min)} to ${pct(max)}`);
    add(capitalPanel,'p','Cash is the reported available-to-trade component. The snapshot difference can include other cash, missing marks or capture timing.');
  }

  function history() {
    detailPanel.replaceChildren();
    const head = add(detailPanel,'div',null,'meridian-panel-head');
    add(head,'h2','Rolling correlation');
    if (!report.history) {
      add(detailPanel, 'p', 'Pair history unavailable. ' + reasons[report.state]);
      return;
    }
    const basis = add(head,'div',null,'segmented');
    for (const [label,pairOnly] of [['Common panel',false],['Pair-specific history',true]]) {
      button(basis,label,() => void load(report.pair,pairOnly),report.pair_only === pairOnly);
    }
    const points = report.history;
    const valid = points.filter(point => point.rho != null);
    const counts = valid.length ? `${valid.length} estimates · ${day(valid[0].end)} to ${day(valid.at(-1).end)}` : 'No eligible estimates';
    const pairName = report.pair.map(k => report.holdings[k].name).join(' × ');
    add(detailPanel,'p',`${pairName} · ${report.window}-session ${report.descriptive ? 'descriptive ' : ''}window · ${counts}`);
    const layout = add(detailPanel,'div',null,'meridian-history-grid');
    const chart = add(layout,'div');
    const svg = (parent, tag, attrs) => {
      const node = document.createElementNS('http://www.w3.org/2000/svg',tag);
      for (const [name,value] of Object.entries(attrs)) node.setAttribute(name,String(value));
      parent.append(node);
      return node;
    };
    const plot = svg(chart,'svg',{viewBox:'0 0 700 184',role:'img','aria-label':'Rolling correlation, fixed scale −1 to +1. Use the date selector to inspect the series.'});
    const span = Math.max(points.length-1,1);
    const x = index => points.length === 1 ? 354 : 34 + 640*index/span;
    const y = rho => 14 + 70*(1-rho);
    for (const value of [-1,-.5,0,.5,1]) {
      const label = svg(plot,'text',{x:28,y:y(value)+3,'text-anchor':'end'});
      label.textContent = value > 0 ? '+'+value : String(value).replace('-', '−');
      svg(plot,'line',{x1:34,x2:674,y1:y(value),y2:y(value),class:value === 0 ? 'zero' : 'guide'});
    }
    let path = '';
    let previous = false;
    for (const [i, point] of points.entries()) {
      if (point.rho == null) {
        if (points.length > 1) {
          const left = Math.max(34,x(i-.5));
          svg(plot,'rect',{x:left,y:14,width:Math.min(674,x(i+.5))-left,height:140,class:'gap'});
        }
        previous = false;
      } else {
        path += `${previous ? 'L' : 'M'}${x(i)} ${y(point.rho)}`;
        previous = true;
      }
    }
    svg(plot,'path',{d:path,class:'curve'});
    const ticks = [...new Set([0, Math.floor((points.length-1)/2), points.length-1])];
    for (const i of ticks) {
      const label = svg(plot,'text',{x:x(i),y:173,'text-anchor':ticks.length===1 ? 'middle' : i===0 ? 'start' : i===ticks.at(-1) ? 'end' : 'middle'});
      label.textContent = day(points[i].end);
    }
    const marker = svg(plot,'line',{y1:14,y2:154,class:'marker'});
    const dot = svg(plot,'circle',{r:4,class:'dot'});
    const hit = svg(plot,'rect',{x:34,y:14,width:640,height:140,class:'hit'});
    add(chart,'p',`${report.pair_only ? 'Pair-specific sample · more eligible dates may be available than in the matrix panel.' : 'Same complete-panel basis as the matrix.'} ${points.length-valid.length} unsupported windows.`);
    const info = add(layout,'div',null,'meridian-point');
    const picker = add(info,'input');
    picker.type = 'range'; picker.min = '0'; picker.max = String(points.length-1);
    picker.disabled = points.length === 1;
    picker.setAttribute('aria-label','Select rolling window by date');
    const values = add(info,'dl');
    values.setAttribute('aria-live','polite');
    const inspect = i => {
      const point = points[i];
      picker.value = String(i);
      picker.setAttribute('aria-valuetext',`${day(point.end)} · ${point.rho == null ? 'unavailable' : coeff(point.rho)}`);
      marker.setAttribute('x1',x(i)); marker.setAttribute('x2',x(i));
      dot.setAttribute('cx',x(i)); dot.setAttribute('cy',point.rho == null ? 0 : y(point.rho));
      dot.setAttribute('visibility',point.rho == null ? 'hidden' : 'visible');
      values.replaceChildren();
      for (const [key,value] of [
        [i===points.length-1 && !report.pair_only ? 'Matrix sample · ρ' : 'Rolling ρ',point.rho == null ? 'Unavailable' : coeff(point.rho)],
        ['Window dates',`${day(point.start)} → ${day(point.end)}`],
        ['Matched returns',`${point.n} / ${report.window}`],
        ['Imputed rows',point.imputed ?? 'Provenance unavailable'],
        ['Excluded sessions',`${point.excluded}${point.affected.length ? ' · '+point.affected.join(', ') : ''}`],
      ]) {
        add(values,'dt',key); add(values,'dd',value);
      }
      note.textContent = reasons[point.reason] ?? '';
    };
    const note = add(info,'p');
    picker.addEventListener('input',() => inspect(Number(picker.value)));
    hit.addEventListener('click',event => {
      const local = new DOMPoint(event.clientX,event.clientY).matrixTransform(plot.getScreenCTM().inverse());
      inspect(Math.min(points.length-1,Math.max(0,Math.round((local.x-34)/640*span))));
    });
    inspect(points.length-1);
  }

  window.meridianDiversification = {
    setSnapshot(data) {
      const changed = stamp(snapshot) !== stamp(data) || holdingsStamp(snapshot) !== holdingsStamp(data);
      snapshot = data;
      if (changed) report = null;
      if (open && (changed || (!pending && (!report || checkedSlot !== cutoffSlot())))) void load();
    },
    setOpen(value) {
      if (value === open) return;
      open = value;
      if (open && !snapshot) status.textContent = 'Waiting for an approved GBP ISA snapshot.';
      if (open && (!report || checkedSlot !== cutoffSlot())) void load();
      if (!open) { pending?.abort(); pending = null; }
    },
    clear() {
      pending?.abort(); pending = null;
      open = false; snapshot = null; report = null; checkedSlot = null;
      horizon = 90; cluster = -1; exclusionOpen = false; order = 'global';
      syncControls();
      status.textContent = ''; result.replaceChildren();
    },
  };
})();
