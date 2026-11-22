// Assumptions and results live in the signed-in page only.
(() => {
  const el = id => document.getElementById(id);
  function add(parent, tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    parent.append(node);
    return node;
  }
  function button(parent, label, action) {
    const node = add(parent, 'button', label);
    node.type = 'button';
    node.addEventListener('click', action);
    return node;
  }
  function input(parent, label, type, value, constraints = {}) {
    const node = add(add(parent, 'label', label), 'input');
    Object.assign(node, { type, value, required: true }, constraints);
    return node;
  }
  function select(parent, label, options) {
    const node = add(add(parent, 'label', label), 'select');
    for (const [value, name] of options) add(node, 'option', name).value = value;
    if (options.length) node.value = options[0][0];
    return node;
  }
  function table(parent, headers, rows) {
    const scroll = add(parent, 'div');
    scroll.className = 'table-scroll';
    scroll.tabIndex = 0;
    const node = add(scroll, 'table');
    const head = add(add(node, 'thead'), 'tr');
    for (const label of headers) add(head, 'th', label).scope = 'col';
    const body = add(node, 'tbody');
    for (const values of rows) {
      const row = add(body, 'tr');
      for (const value of values) add(row, 'td', value);
    }
  }

  const targetDate = '2030-04-30';
  const errors = {
    projection_request_invalid: 'Check the dates and amounts in both plans.',
    growth_invalid: 'Enter an annual growth rate between −100% and 1,000% for each destination and the opening ISA.',
    deposit_limit: 'Use at most 12 deposit instructions per plan.',
    deposit_amount_invalid: 'Enter a positive deposit in GBP to the nearest penny, up to £1 billion.',
    deposit_date_invalid: 'Choose a deposit date from the snapshot date through 30 April 2030.',
    allocation_limit: 'Add between 1 and 24 allocation destinations per deposit.',
    destination_invalid: 'Use each destination once per deposit. Choose a current holding or name your hypothetical stock.',
    allocation_amount_invalid: 'Each allocation must be positive, use at most two decimal places and fit within its deposit total.',
    allocation_total_invalid: 'For each deposit, allocations must add up to 100% or to the full GBP deposit amount.',
    projection_horizon_unavailable: 'The snapshot date is outside the supported forecast period.',
    stress_request_invalid: 'Check both scenarios and enter a direct price shock.',
    shock_invalid: 'Use a price shock between −100% and 1,000%.',
    stress_basket_invalid: 'Select at least one eligible holding for a custom basket.',
    stress_override_invalid: 'Use each override once and select its holding in the basket.',
    snapshot_changed: 'A newer approved snapshot is available. Reload the saved snapshot, then recalculate.',
    snapshot_unavailable: 'The approved GBP snapshot is unavailable.',
  };
  let snapshot = null, projection = null, stress = null, formatMoney, sessionEnded;
  const stamp = data => data?.account_retrieval?.retrieval_completed_at;
  const holdingsStamp = data => data?.positions_retrieval?.retrieval_completed_at;
  const captureDate = () => new Date(stamp(snapshot)).toISOString().slice(0, 10);
  const holdingOptions = () => snapshot.positions.map(row => [row.ticker, row.name ? `${row.name} (${row.ticker})` : row.ticker])
    .sort((left, right) => left[1].localeCompare(right[1]));
  function fillHoldings(node) {
    const previous = node.value;
    node.replaceChildren();
    add(node, 'option', 'Choose a holding').value = '';
    const options = holdingOptions();
    for (const [ticker, label] of options) add(node, 'option', label).value = ticker;
    node.value = options.some(([ticker]) => ticker === previous) ? previous : '';
  }
  function invalidate(view, message = 'Assumptions changed. Calculate to update the results.') {
    view.pending?.abort();
    view.pending = null;
    view.submit.disabled = !snapshot;
    view.results.replaceChildren();
    view.status.textContent = message;
  }
  async function calculate(view, endpoint, assumptions, render) {
    if (!snapshot || view.pending) return;
    const pending = new AbortController();
    view.pending = pending;
    view.submit.disabled = true;
    view.status.textContent = 'Calculating…';
    view.results.replaceChildren();
    try {
      const cookies = document.cookie.split(';').map(value => value.trim())
        .filter(value => value.startsWith('__Host-meridian_csrf='));
      const csrf = cookies.length === 1 ? cookies[0].slice('__Host-meridian_csrf='.length) : '';
      const time = stamp(snapshot);
      const response = await fetch(`/api/v1/portfolio/${endpoint}`, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
        signal: pending.signal, headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify({ capture_time: time, positions_time: holdingsStamp(snapshot), assumptions }),
      });
      if (view.pending !== pending) return;
      if ([401, 403].includes(response.status)) { sessionEnded(); return; }
      const data = await response.json();
      if (view.pending !== pending) return;
      if (!response.ok) {
        view.status.textContent = errors[data.error] ?? 'Calculation is unavailable. Try again.';
        return;
      }
      if (data.capture_time !== time || data.currency !== 'GBP') throw new Error('invalid_result');
      render(view.results, data);
      view.status.textContent = 'Results updated.';
    } catch {
      if (view.pending === pending) view.status.textContent = 'Calculation is unavailable. Try again.';
    } finally {
      if (view.pending === pending) {
        view.pending = null;
        view.submit.disabled = false;
      }
    }
  }

  function newView(formId, statusId, resultsId) {
    const form = el(formId);
    return { form, status: el(statusId), results: el(resultsId) };
  }
  function allocationEditor(parent, index, unit, remove) {
    const section = add(parent, 'fieldset');
    section.className = 'plan-entry';
    add(section, 'legend', `Allocation ${index}`);
    const kind = select(section, 'Destination', [['cash', 'Cash'], ['holding', 'Current holding'], ['hypothetical', 'Hypothetical stock']]);
    const holding = select(section, 'Current holding', []);
    const name = input(section, 'Stock name or ticker', 'text', '', { maxLength: 128 });
    const share = input(section, 'Allocation', 'number', '', { min: '0.01', step: '0.01' });
    const growth = input(section, 'Annual growth (%)', 'number', '0', { min: '-100', max: '1000', step: 'any' });
    holding.dataset.planningHolding = '';
    fillHoldings(holding);
    const syncKind = () => {
      holding.parentElement.hidden = kind.value !== 'holding';
      holding.required = !holding.parentElement.hidden;
      name.parentElement.hidden = kind.value !== 'hypothetical';
      name.required = !name.parentElement.hidden;
    };
    syncKind();
    kind.addEventListener('change', syncKind);
    share.setAttribute('aria-label', unit.value === 'gbp' ? 'Allocation (GBP)' : 'Allocation (%)');
    button(section, 'Remove allocation', remove);
    return {
      section, share,
      read: () => ({ kind: kind.value, name: kind.value === 'holding' ? holding.value : kind.value === 'hypothetical' ? name.value : '',
        share: share.value, growth_pct: growth.value }),
    };
  }
  function depositEditor(parent, index, view, remove) {
    const section = add(parent, 'fieldset');
    section.className = 'plan-entry';
    add(section, 'legend', `Deposit ${index}`);
    const frequency = select(section, 'Frequency', [['once', 'One-off'], ['monthly', 'Monthly at month-end']]);
    const first = input(section, 'Date or first month', 'date', captureDate(), { min: captureDate(), max: targetDate });
    first.dataset.planningDate = '';
    const amount = input(section, 'Deposit amount (GBP)', 'number', '', { min: '0.01', max: '1000000000', step: '0.01' });
    const unit = select(section, 'Allocation unit', [['percent', 'Percentage (%)'], ['gbp', 'GBP (£)']]);
    const split = add(section, 'div');
    const allocations = [];
    let next = 0;
    const create = () => {
      if (allocations.length >= 24) return;
      const row = allocationEditor(split, ++next, unit, () => {
        row.section.remove();
        allocations.splice(allocations.indexOf(row), 1);
        addAllocation.disabled = false;
        invalidate(view);
      });
      allocations.push(row);
      addAllocation.disabled = allocations.length >= 24;
      return row;
    };
    const addAllocation = button(section, 'Add allocation', () => {
      create();
      invalidate(view);
    });
    button(section, 'Remove deposit', remove);
    create().share.value = '100';
    unit.addEventListener('change', () => {
      for (const row of allocations) {
        row.share.value = '';
        row.share.setAttribute('aria-label', unit.value === 'gbp' ? 'Allocation (GBP)' : 'Allocation (%)');
      }
    });
    return { section, read: () => ({ first_date: first.value, frequency: frequency.value, amount: amount.value,
      unit: unit.value, allocations: allocations.map(row => row.read()) }) };
  }
  function setupProjection() {
    const view = newView('projections-form', 'projections-status', 'projections-results');
    const opening = input(view.form, 'Existing ISA annual growth (%)', 'number', '0', { min: '-100', max: '1000', step: 'any' });
    const grid = add(view.form, 'div');
    grid.className = 'planning-grid';
    const plans = ['Plan A', 'Plan B'].map(label => {
      const section = add(grid, 'fieldset');
      add(section, 'legend', label);
      const list = add(section, 'div');
      const deposits = [];
      let next = 0;
      const more = button(section, 'Add deposit', () => {
        const deposit = depositEditor(list, ++next, view, () => {
          deposit.section.remove();
          deposits.splice(deposits.indexOf(deposit), 1);
          more.disabled = false;
          invalidate(view);
        });
        deposits.push(deposit);
        more.disabled = deposits.length >= 12;
        invalidate(view);
      });
      return { read: () => ({ deposits: deposits.map(deposit => deposit.read()) }) };
    });
    view.submit = add(view.form, 'button', 'Calculate projections');
    view.submit.type = 'submit';
    view.form.oninput = () => invalidate(view);
    view.form.onsubmit = event => {
      event.preventDefault();
      return calculate(view, 'projections', {
        opening_growth_pct: opening.value, plans: plans.map(plan => plan.read()),
      }, renderProjection);
    };
    return view;
  }

  function renderProjection(parent, report) {
    if (report.method !== 'dated_isa_projection_v1') throw new Error('invalid_result');
    const paths = [report.baseline, ...report.plans];
    const labels = ['Baseline', 'Plan A', 'Plan B'];
    const money = value => formatMoney(value, 'GBP');
    add(parent, 'h3', 'Target-date comparison');
    table(parent, ['Path', 'Projected value', 'New deposits', 'Projected growth', 'Gap or surplus'], paths.map((path, index) =>
      [labels[index], money(path.target_value), money(path.deposits), money(path.growth),
        `${money(path.goal_difference)} ${path.goal_difference.startsWith('-') ? 'gap' : path.goal_difference === '0' ? 'on target' : 'surplus'}`]));
    add(parent, 'p', `Opening ISA growth assumption · ${report.opening_growth_pct}% annually. Destination rates are in each schedule.`);
    renderChart(parent, paths, labels, report.goal);
    for (let index = 1; index < paths.length; index++) {
      const details = add(parent, 'details');
      add(details, 'summary', `${labels[index]} cash-flow schedule`);
      const rows = paths[index].schedule;
      if (!rows.length) add(details, 'p', 'No deposits entered.');
      else {
        const instructions = paths[index].instructions;
        table(details, ['Deposit', 'Amount', 'Destinations and annual growth'], instructions.map((instruction, i) => [
          String(i + 1), money(instruction.total), instruction.allocations.map(row =>
            `${row.kind === 'cash' ? 'Cash' : row.name}${row.kind === 'hypothetical' ? ' (hypothetical)' : ''} · ${money(row.amount)} · ${row.growth_pct}%`).join(' / '),
        ]));
        table(details, ['Deposit date (UTC)', 'Deposit', 'Total deposit'], rows.map(flow => [
          flow.date, String(flow.deposit + 1), money(instructions[flow.deposit].total),
        ]));
      }
    }
  }
  function renderChart(parent, paths, labels, goal) {
    add(parent, 'h3', 'Projected ISA value over time');
    const colors = ['#a0aec0', '#59dcc3', '#ffb274'];
    for (let index = 0; index < labels.length; index++) {
      add(parent, 'span', labels[index]).className = `planning-key planning-key-${index}`;
    }
    const canvas = add(parent, 'canvas');
    canvas.className = 'planning-chart';
    canvas.width = 900;
    canvas.height = 310;
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'Projected GBP ISA values from capture to the goal date, with a £100,000 goal line.');
    const ctx = canvas.getContext?.('2d');
    if (!ctx) return;
    const series = paths.map(path => path.series);
    const first = Date.parse(series[0][0].date);
    const last = Date.parse(targetDate);
    const maximum = Math.max(Number(goal), ...series.flatMap(line => line.map(point => Number(point.value))));
    const x = date => 95 + 778 * (Date.parse(date) - first) / (last - first || 1);
    const y = value => 275 - 245 * Number(value) / maximum;
    ctx.font = '14px system-ui';
    ctx.fillStyle = '#b8c7bb';
    for (const value of [0, maximum / 2, maximum]) {
      ctx.fillText(new Intl.NumberFormat('en-GB', {style: 'currency', currency: 'GBP', maximumFractionDigits: 0}).format(value), 7, y(value) + 4, 80);
      ctx.strokeStyle = '#496150';
      ctx.beginPath(); ctx.moveTo(95, y(value)); ctx.lineTo(873, y(value)); ctx.stroke();
    }
    ctx.fillText(series[0][0].date, 95, 299);
    if (last !== first) ctx.fillText(targetDate, 795, 299);
    ctx.setLineDash([5, 5]);
    ctx.strokeStyle = '#dde7f4';
    ctx.beginPath(); ctx.moveTo(95, y(goal)); ctx.lineTo(873, y(goal)); ctx.stroke();
    ctx.setLineDash([]);
    series.forEach((line, index) => {
      ctx.strokeStyle = colors[index];
      ctx.lineWidth = 2;
      ctx.beginPath();
      line.forEach((point, position) => ctx[position ? 'lineTo' : 'moveTo'](x(point.date), y(point.value)));
      ctx.stroke();
      ctx.fillStyle = colors[index];
      const end = line.at(-1);
      ctx.beginPath(); ctx.arc(x(end.date), y(end.value), 3, 0, Math.PI * 2); ctx.fill();
    });
  }

  const positiveDecimal = value => typeof value === 'string' && /^\d+(?:\.\d+)?$/.test(value) && /[1-9]/.test(value);
  function stressOptions() {
    const eligible = new Set(snapshot.positions.filter(row => row.account_currency === 'GBP' &&
      ['STOCK', 'ETF'].includes(row.instrument_type) && positiveDecimal(row.current_value) && positiveDecimal(row.quantity))
      .map(row => row.ticker));
    return holdingOptions().filter(([ticker]) => eligible.has(ticker));
  }

  function stressEditor(parent, label, initialShock) {
    const section = add(parent, 'fieldset');
    add(section, 'legend', label);
    const scope = select(section, 'Apply shock to', [['all', 'All eligible holdings'], ['basket', 'Custom basket']]);
    const rate = input(section, 'Direct price shock (%)', 'number', initialShock, { min: '-100', max: '1000', step: 'any' });
    const basketNotice = add(section, 'p', 'Select holdings for this basket. An optional holding shock replaces the scenario shock.');
    const details = add(section, 'details');
    add(details, 'summary', 'Select holdings and set overrides');
    const list = add(details, 'div');
    list.className = 'stress-holdings';
    let choices = [];
    const syncScope = () => {
      const custom = scope.value === 'basket';
      basketNotice.hidden = !custom;
      for (const { selected, override } of choices) {
        selected.parentElement.hidden = !custom;
        override.disabled = custom && !selected.checked;
      }
      if (custom) details.open = true;
    };
    scope.addEventListener('change', syncScope);

    function update() {
      const previous = new Map(choices.map(row => [row.ticker, row]));
      list.replaceChildren();
      choices = stressOptions().map(([ticker, name]) => {
        const row = add(list, 'fieldset');
        add(row, 'legend', name);
        const selected = input(row, 'Include in basket', 'checkbox', '', { required: false, checked: previous.get(ticker)?.selected.checked ?? false });
        const override = input(row, 'Override shock (%)', 'number', previous.get(ticker)?.override.value ?? '',
          { min: '-100', max: '1000', step: 'any', required: false });
        selected.addEventListener('change', syncScope);
        return { ticker, selected, override };
      });
      if (!choices.length) add(list, 'p', 'No eligible holdings are available in this snapshot.');
      syncScope();
    }
    function read() {
      const active = choices.filter(row => scope.value === 'all' || row.selected.checked);
      return { scope: scope.value, price_shock_pct: rate.value,
        basket: scope.value === 'basket' ? active.map(row => row.ticker) : [],
        overrides: active.filter(row => row.override.value !== '')
          .map(row => ({ ticker: row.ticker, price_shock_pct: row.override.value })),
      };
    }
    return { update, read };
  }

  function setupStress() {
    const view = newView('stress-form', 'stress-status', 'stress-results');
    const grid = add(view.form, 'div');
    grid.className = 'planning-grid';
    const scenarios = [stressEditor(grid, 'Scenario A', '-10'), stressEditor(grid, 'Scenario B', '-20')];
    view.update = () => scenarios.forEach(scenario => scenario.update());
    view.submit = add(view.form, 'button', 'Compare scenarios');
    view.submit.type = 'submit';
    view.form.oninput = () => invalidate(view);
    view.form.onsubmit = event => {
      event.preventDefault();
      return calculate(view, 'stress-tests', { scenarios: scenarios.map(scenario => scenario.read()) }, renderStress);
    };
    return view;
  }

  function renderStress(parent, report) {
    if (report.method !== 'direct_isa_stress_v1') throw new Error('invalid_result');
    const money = value => formatMoney(value, 'GBP');
    const pct = value => value === null ? 'Unavailable' : `${value.replace('-', '−')}%`;
    const labels = ['Scenario A', 'Scenario B'];
    const scenarios = report.scenarios;
    table(parent, ['Measure', ...labels], [
      ['Direct price shock', ...scenarios.map(row => `${pct(row.price_shock_pct)} · ${row.scope === 'all' ? 'all eligible' : 'custom basket'}`)],
      ['Baseline ISA value', ...scenarios.map(() => money(report.opening_value))],
      ['Stressed ISA value', ...scenarios.map(row => money(row.stressed_value))],
      ['Impact (GBP)', ...scenarios.map(row => money(row.impact))],
      ['Impact (% of ISA)', ...scenarios.map(row => pct(row.impact_pct))],
      ['Scenario coverage', ...scenarios.map(row => `${money(row.covered_value)} · ${pct(row.covered_pct)} of ISA · ${row.covered_holdings} of ${report.total_holdings} holdings`)],
      ['GBP cash available to trade', ...scenarios.map(() => money(report.known_cash))],
      ['Uncovered value excluding displayed cash', ...scenarios.map(row => money(row.uncovered_value))],
      ['Of which marked holdings outside the shock', ...scenarios.map(row => money(row.unshocked_marked_value))],
      ['Of which snapshot reconciliation difference', ...scenarios.map(() => money(report.unreconciled_value))],
    ]);
    if (report.availability === 'insufficient_data') add(parent, 'p', 'No holdings have sufficient evidence for a direct price shock.');
    add(parent, 'p', `${report.unvalued_holdings} holdings lack a usable GBP mark. ${report.ineligible_holdings} marked holdings are outside the eligible instrument or position scope.`);
    add(parent, 'p', 'Displayed cash is the available-to-trade component. The signed reconciliation difference is the ISA value less marked holdings and displayed cash. It can include other cash components, missing marks and differences between capture times.');
    const grid = add(parent, 'div');
    grid.className = 'planning-grid';
    scenarios.forEach((scenario, index) => {
      const section = add(grid, 'section');
      add(section, 'h3', `${labels[index]} largest losses`);
      const lossRows = scenario.holdings.filter(row => row.impact.startsWith('-')).slice(0, 5);
      const holdingRows = items => items.map(row => [
        row.name ? `${row.name} (${row.ticker})` : row.ticker, money(row.opening_value),
        `${pct(row.shock_pct)}${row.basis === 'holding_override' ? ' · override' : ''}`,
        money(row.impact), money(row.stressed_value),
      ]);
      const headers = ['Holding', 'Baseline', 'Shock', 'Impact', 'Stressed'];
      if (lossRows.length) table(section, headers, holdingRows(lossRows));
      else add(section, 'p', 'No holding losses in this scenario.');
      if (scenario.holdings.length) {
        const details = add(section, 'details');
        add(details, 'summary', 'All holding impacts');
        table(details, headers, holdingRows(scenario.holdings));
      }
    });
  }

  function setSnapshot(data) {
    if (stamp(snapshot) === stamp(data) && holdingsStamp(snapshot) === holdingsStamp(data)) return;
    snapshot = data?.currency === 'GBP' ? data : null;
    if (!snapshot) {
      clear();
      return;
    }
    const refreshed = projection !== null;
    if (!projection) projection = setupProjection();
    if (!stress) stress = setupStress();
    for (const node of projection.form.querySelectorAll('[data-planning-holding]')) fillHoldings(node);
    for (const node of projection.form.querySelectorAll('[data-planning-date]')) node.min = captureDate();
    el('projections-capture').textContent = `Approved Trading 212 ISA · ${formatMoney(snapshot.total_value, 'GBP')} · captured ${new Date(stamp(snapshot)).toISOString()}`;
    stress.update();
    el('stress-capture').textContent = `Approved Trading 212 ISA · Account captured ${new Date(stamp(snapshot)).toISOString()} · Holdings captured ${new Date(holdingsStamp(snapshot)).toISOString()}`;
    invalidate(projection, refreshed ? 'The approved snapshot changed. Check your dates and holdings, then recalculate.' : 'Enter assumptions for either plan, then calculate.');
    invalidate(stress, refreshed ? 'The approved snapshot changed. Check your holding selections, then recalculate.' : 'Compare the default shocks or edit either scenario.');
  }
  function clear() {
    if (projection) {
      invalidate(projection, 'Waiting for an approved GBP ISA snapshot.');
      projection.form.replaceChildren();
      projection = null;
    }
    if (stress) {
      invalidate(stress, 'Waiting for an approved GBP ISA snapshot.');
      stress.form.replaceChildren();
      stress = null;
    }
    snapshot = null;
    el('projections-capture').textContent = '';
    el('stress-capture').textContent = '';
  }

  window.meridianPlanning = {
    configure(money, denied) { formatMoney = money; sessionEnded = denied; },
    setSnapshot, clear,
  };
})();
