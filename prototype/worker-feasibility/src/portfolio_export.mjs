// Export only approved public projection fields. Financial scalars stay exact.
const DECIMAL = /^-?\d{1,40}(?:\.\d{1,30})?$/;
const SCALE = 10n ** 30n;
const amount = value => typeof value === "string" && DECIMAL.test(value) ? value : null;

function scaled(value) {
  if (amount(value) === null) return null;
  const [whole, fraction = ""] = value.replace(/^-/, "").split(".");
  const n = BigInt(whole) * SCALE + BigInt(fraction.padEnd(30, "0"));
  return value.startsWith("-") ? -n : n;
}

function difference(end, start) {
  const a = scaled(start), b = scaled(end);
  if (a === null || b === null) return null;
  const n = b - a, magnitude = n < 0n ? -n : n;
  const fraction = (magnitude % SCALE).toString().padStart(30, "0").replace(/0+$/, "");
  return (n < 0n ? "-" : "") + String(magnitude / SCALE) + (fraction ? "." + fraction : "");
}

function costPercentage(pnl, cost) {
  const a = scaled(pnl), b = scaled(cost);
  if (a === null || b === null || b <= 0n) return null;
  const magnitude = ((a < 0n ? -a : a) * 10000n + b / 2n) / b;
  return (a < 0n && magnitude ? "-" : "") + (magnitude / 100n) + "." + String(magnitude % 100n).padStart(2, "0");
}

function onePercent(total) {
  if (amount(total) === null || scaled(total) <= 0n) return null;
  const [whole, fraction = ""] = total.split(".");
  const digits = whole.padStart(3, "0") + fraction;
  const dollars = BigInt(digits.slice(0, whole.padStart(3, "0").length - 2));
  const remainder = digits.slice(whole.padStart(3, "0").length - 2).replace(/0+$/, "");
  return String(dollars) + (remainder ? "." + remainder : "");
}

function rank(rows, field, absolute = false) {
  const magnitude = value => absolute && value < 0n ? -value : value;
  return [...rows].sort((a, b) => {
    const x = scaled(a[field]), y = scaled(b[field]);
    if (x === null && y !== null) return 1;
    if (y === null && x !== null) return -1;
    if (x !== null && y !== null && magnitude(x) !== magnitude(y)) {
      return magnitude(x) > magnitude(y) ? -1 : 1;
    }
    return a.ticker < b.ticker ? -1 : a.ticker > b.ticker ? 1 : 0;
  });
}

async function meridianRisk(snapshot, calculate) {
  const fallback = { availability: "unavailable", reason: "meridian_unavailable" };
  if (!calculate) return fallback;
  let timer;
  try {
    const report = JSON.parse(await Promise.race([
      calculate(snapshot, { window: 90, pair: null, pair_only: false }),
      new Promise((_, reject) => { timer = setTimeout(reject, 5000); }),
    ]));
    const { method, state, window, minimum, price_basis, n, scheduled, sample_start, sample_end,
      covered_pct, excluded_pct, excluded, holdings = [], matrix, risk, clusters, group_totals } = report;
    return {
      availability: state === "available" ? "available" : "unavailable",
      reason: state === "available" ? (risk ? null : "variance_unavailable") : state,
      method, window, minimum, price_basis, n, scheduled, sample_start, sample_end,
      covered_pct, excluded_pct, excluded,
      clusters: (clusters ?? []).map((members, index) => ({
        id: index + 1, tickers: members.map(i => holdings[i].ticker),
        isa_weight_pct: group_totals[index].capital, covered_variance_pct: group_totals[index].risk,
      })),
      holdings: holdings.map((row, index) => {
        let peer = null;
        for (const [i, coefficient] of (matrix?.[index] ?? []).entries()) {
          if (i === index || !(coefficient > 0)) continue;
          const ticker = holdings[i].ticker;
          if (!peer || coefficient > peer.coefficient ||
              (coefficient === peer.coefficient && ticker < peer.ticker)) peer = { ticker, coefficient };
        }
        return { ...row, covered_variance_pct: risk?.[index] ?? null, strongest_positive_peer: peer };
      }),
    };
  } catch {
    return fallback;
  } finally {
    clearTimeout(timer);
  }
}

export async function buildExport(inputs, calculateChanges, calculateMeridian) {
  const { snapshot, changes, target_date, refresh_health } = inputs;
  const { start, end } = changes;
  const report = start.status === "observed" ? JSON.parse(calculateChanges(JSON.stringify(changes))) : null;
  const candidate = snapshot.exposures;
  const exposures = candidate?.method === "broker_exposures_v1" && candidate.snapshot_id === end.snapshot_id &&
    candidate.currency === "GBP" && Date.parse(candidate.account_as_of) === Date.parse(end.account_captured_at) &&
    Date.parse(candidate.positions_as_of) === Date.parse(end.positions_captured_at) ? candidate : null;
  const weights = new Map((exposures?.holdings ?? []).map(row => [row.ticker, row.weights]));
  const positions = rank(snapshot.positions.filter(row => scaled(row.quantity) !== 0n).map(row => {
    const { ticker, name, isin, instrument_type, instrument_currency, account_currency, metadata } = row;
    const gbp = account_currency === "GBP";
    const value_gbp = gbp ? amount(row.current_value) : null;
    const cost_gbp = gbp ? amount(row.total_cost) : null;
    const unrealised_pnl_gbp = gbp ? amount(row.unrealized_profit_loss) : null;
    return { ticker, name, isin, instrument_type, instrument_currency,
      metadata: metadata ? { state: metadata.state, retrieved_at: metadata.retrieved_at } : null,
      quantity: amount(row.quantity), quote: amount(row.current_price),
      average_price_paid: instrument_currency ? amount(row.average_price_paid) : null,
      value_gbp, cost_gbp, unrealised_pnl_gbp, unrealised_pnl_on_cost_pct: costPercentage(unrealised_pnl_gbp, cost_gbp),
      isa_weight_pct: weights.get(ticker)?.portfolio_pct ?? null,
      invested_weight_pct: weights.get(ticker)?.invested_pct ?? null,
    };
  }), "value_gbp");
  const monthly = (report?.holdings ?? []).map(row => ({
    ...row, quantity_change: row.status === "identity_conflict" ? null : difference(row.end.quantity, row.start.quantity),
    weight_change_pp: row.status === "identity_conflict" ? null : difference(row.end.weight_pct, row.start.weight_pct),
  }));
  const status = start.status === "observed" ? "available" : "unavailable";
  const { positions: _positions, allocations: _allocations, cash: _cash, ...current } = end;
  return {
    schema_version: 1, generated_at: new Date().toISOString(), currency: "GBP",
    source: "trading212", basis: "broker_reported", current,
    comparison: {
      availability: status, reason: status === "available" ? null : "baseline_" + start.status,
      method: report?.method ?? "observed_portfolio_changes_v1",
      target_date, actual_date: start.observed_at ? start.date : null,
      offset_days: start.observed_at ? (Date.parse(target_date) - Date.parse(start.date)) / 86400000 : null,
      baseline: report?.start ?? { date: start.date, status: start.status, observed_at: start.observed_at ?? null },
    },
    portfolio: {
      total_gbp: amount(snapshot.total_value), invested_gbp: amount(snapshot.investments?.currentValue),
      cash_components_gbp: snapshot.cash_components, cash_component_pct: exposures?.cash_component_pct ?? null,
      concentration: exposures?.concentration ?? null, holdings_hhi: exposures?.holdings_hhi ?? null,
      effective_holdings: exposures?.effective_holdings ?? null, missing_values: positions.filter(row => row.value_gbp === null).length,
      gbp_per_isa_weight_point: onePercent(exposures?.portfolio_denominator ?? report?.end.portfolio_denominator),
      observed_age_seconds: Math.max(0, Math.floor((Date.now() - Date.parse(end.observed_at)) / 1000)),
      refresh_health, quote_age: "unknown", profit_loss_basis: snapshot.profit_loss_basis,
    },
    holdings: positions,
    monthly_changes: {
      holdings: monthly, total_value_change_gbp: report ? difference(end.portfolio_value, start.portfolio_value) : null,
      cash: report?.cash ?? [], top_five: report?.top_five ?? null, allocations: report?.allocations ?? [],
      largest_value_moves: rank(monthly.filter(row => scaled(row.value_change) !== null && scaled(row.value_change) !== 0n), "value_change", true).slice(0, 3),
      largest_weight_moves: rank(monthly.filter(row => scaled(row.weight_change_pp) !== null && scaled(row.weight_change_pp) !== 0n), "weight_change_pp", true).slice(0, 3),
    },
    exposures,
    meridian_risk: await meridianRisk(snapshot, calculateMeridian),
  };
}

const cell = value => value == null ? "—" : String(value)
  .replace(/[\r\n\t]+/g, " ").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c])
  .replace(/[\\|`*_\[\]!]/g, "\\$&");
const table = (columns, rows) => [
  "| " + columns.join(" | ") + " |",
  "| " + columns.map(() => "---").join(" | ") + " |",
  ...rows.map(row => "| " + row.map(cell).join(" | ") + " |"),
];

export function exportMarkdown(data) {
  const { current, comparison, portfolio, holdings, monthly_changes: changes, exposures, meridian_risk: risk } = data;
  const lines = [
    "# Meridian AI portfolio brief", "",
    "Generated " + cell(data.generated_at) + " · Schema " + data.schema_version + " · Trading 212 · GBP", "",
    "## Portfolio at a glance", "",
    "- Saved observation " + cell(current.observed_at) + " · Snapshot " + cell(current.snapshot_id),
    "- Account capture " + cell(current.account_captured_at) + " · Holdings capture " + cell(current.positions_captured_at),
    "- Reported ISA value £" + cell(portfolio.total_gbp) + " · Invested £" + cell(portfolio.invested_gbp),
    "- Available-to-trade cash £" + cell(portfolio.cash_components_gbp?.availableToTrade) +
      " · " + cell(portfolio.cash_component_pct?.availableToTrade) + "% of ISA",
    "- Largest / top-five / top-ten ISA weights " +
      [1, 5, 10].map(top => cell(portfolio.concentration?.find(row => row.top === top)?.weights?.portfolio_pct) + "%").join(" / "),
    "- Monthly top-five weight change " + cell(changes.top_five?.weight_change_pp) + " pp",
    "- Other reported cash fields £" + cell(portfolio.cash_components_gbp?.inPies) + " in pies · £" +
      cell(portfolio.cash_components_gbp?.reservedForOrders) + " reserved for orders",
    "- Securities-only HHI " + cell(portfolio.holdings_hhi) + " · Effective holding count " + cell(portfolio.effective_holdings),
    "- GBP equivalent of one ISA weight point " + cell(portfolio.gbp_per_isa_weight_point),
    "- Quote age unknown · Saved observation age " + cell(portfolio.observed_age_seconds) +
      " seconds · Missing GBP marks " + cell(portfolio.missing_values) +
      " · Last successful refresh " + cell(portfolio.refresh_health?.jobs?.snapshot?.last_success_at),
    "- Comparison target " + cell(comparison.target_date) + " · Actual baseline " + cell(comparison.actual_date) +
      " · Baseline status " + cell(comparison.reason ?? comparison.availability),
    "- Change in reported ISA value £" + cell(changes.total_value_change_gbp) +
      " · Change in available cash £" + cell(changes.cash.find(row => row.label === "availableToTrade")?.value_change),
    "- Largest GBP position movements " + cell(changes.largest_value_moves.map(row => row.ticker + " " + row.value_change).join(", ") || null),
    "- Largest weight movements (pp) " + cell(changes.largest_weight_moves.map(row => row.ticker + " " + row.weight_change_pp).join(", ") || null),
    "- ISA weight excluded from the Meridian risk sample " + cell(risk.excluded_pct) + "%", "",
    "Position value changes can reflect units, price and FX. Open P&L and the P&L-to-cost percentage use broker-reported management figures. A dash indicates unavailable evidence.", "",
    "## Current holdings", "",
    ...table(["Ticker", "Holding", "ISIN", "Type", "Units", "Quote", "Quote currency", "Avg paid", "GBP value", "GBP cost", "GBP P&L", "P&L/cost %", "ISA %", "Invested %"],
      holdings.map(h => [h.ticker, h.name, h.isin, h.instrument_type, h.quantity, h.quote, h.instrument_currency, h.average_price_paid, h.value_gbp, h.cost_gbp, h.unrealised_pnl_gbp, h.unrealised_pnl_on_cost_pct, h.isa_weight_pct, h.invested_weight_pct])),
    "", "## Monthly changes", "",
  ];
  if (comparison.availability === "available") lines.push(
    "Baseline snapshot " + cell(comparison.baseline.snapshot_id) + " · Account " + cell(comparison.baseline.account_captured_at) +
      " · Holdings " + cell(comparison.baseline.positions_captured_at), "",
    ...table(["Ticker", "Status", "GBP start", "GBP end", "GBP change", "Units start", "Units end", "Unit change", "ISA % start", "ISA % end", "Change pp"],
      changes.holdings.map(h => [h.ticker, h.status, h.start.value, h.end.value, h.value_change, h.start.quantity, h.end.quantity, h.quantity_change, h.start.weight_pct, h.end.weight_pct, h.weight_change_pp])),
  );
  else lines.push("Monthly comparison unavailable. " + cell(comparison.reason));
  lines.push("", "## Exposures", "");
  if (exposures) {
    for (const [key, label] of [["sectors", "Equity sectors"], ["issuer_domiciles", "Issuer domicile"], ["fund_markets", "Fund markets"], ["quote_currencies", "Listing quote currency"]]) {
      const item = exposures[key];
      if (!item) continue;
      const delta = changes.allocations.find(row => row.dimension === key);
      const comparable = key !== "sectors" || exposures.sector_rollup_method === "broad_sectors_v1";
      const movement = new Map((comparable ? (delta?.buckets ?? []) : []).map(row => [row.label, row.weight_change_pp]));
      lines.push("### " + label, "",
        ...table(["Exposure", "GBP", "ISA %", "Monthly change pp"],
          (item.buckets ?? item).map(row => [row.label ?? row.quote_currency ?? "Unclassified", row.value, row.weights?.portfolio_pct,
            movement.get(row.label ?? null)])), "");
      if (!Array.isArray(item)) {
        lines.push("Classified GBP " + cell(item.classified?.value) + " · Observed GBP " + cell(item.observed?.value), "");
        const members = (item.buckets ?? []).flatMap(bucket => Object.entries(bucket.members ?? {}).map(([ticker, row]) =>
          [bucket.label ?? "Unclassified", ticker, row.value, row.holding_pct, item.sources?.[ticker]?.as_of, item.sources?.[ticker]?.url]));
        if (members.length) lines.push(...table(["Exposure", "Ticker", "GBP contribution", "Allocation %", "Source date", "Source"], members), "");
      }
    }
  } else lines.push("Compatible saved exposure data unavailable.", "");
  lines.push("## The Meridian risk", "",
    "Status " + cell(risk.reason ?? risk.availability) + " · Basis " + cell(risk.price_basis) +
      " · Matched sessions " + cell(risk.n) + " · Sample " + cell(risk.sample_start) + " to " + cell(risk.sample_end) +
      " · Covered ISA weight " + cell(risk.covered_pct) + "%", "");
  if (risk.holdings?.length) lines.push(
    ...table(["Ticker", "ISA %", "Covered capital %", "Covered variance %", "Strongest positive peer", "Correlation"],
      risk.holdings.map(h => [h.ticker, h.capital, h.covered_capital_pct, h.covered_variance_pct, h.strongest_positive_peer?.ticker, h.strongest_positive_peer?.coefficient])), "");
  if (risk.clusters?.length) lines.push(
    ...table(["Cluster", "Tickers", "ISA %", "Covered variance %"],
      risk.clusters.map(c => [c.id, c.tickers.join(", "), c.isa_weight_pct, c.covered_variance_pct])), "");
  if (risk.excluded?.length) lines.push(
    ...table(["Excluded ticker", "ISA %", "Reason", "Available returns"],
      risk.excluded.map(h => [h.ticker, h.capital, h.reason, h.n])), "");
  return lines.join("\n") + "\n";
}
