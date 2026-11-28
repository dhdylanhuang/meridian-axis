export const positions = [
  { ticker: "SYNl_EQ", name: "Synthetic &amp; Co", isin: "GB00SYNTH000", quantity: "50",
    instrument_currency: "GBX", current_price: "1200", account_currency: "GBP",
    current_value: "600", total_cost: "550", unrealized_profit_loss: "50", instrument_type: "STOCK" },
  { ticker: "FND_US_EQ", name: "Synthetic Fund", quantity: "2.5", instrument_currency: "USD",
    current_price: "105", account_currency: "GBP", current_value: "200", total_cost: "150",
    unrealized_profit_loss: "50", instrument_type: "ETF" },
];
const baselinePositions = [
  { ...positions[0], current_value: "550", current_price: "1100" },
  { ...positions[1], current_value: "150", current_price: "100" },
];
const start = { snapshot_id: "synthetic-baseline", status: "observed", date: "2026-10-20",
  observed_at: "2026-10-20T16:01:00Z", account_captured_at: "2026-10-20T16:00:00Z",
  positions_captured_at: "2026-10-20T16:01:00Z", portfolio_value: "900", invested_value: "700" };
const end = { snapshot_id: "synthetic-current", status: "observed", date: "2026-11-30",
  observed_at: "2026-11-30T16:01:00Z", account_captured_at: "2026-11-30T16:00:00Z",
  positions_captured_at: "2026-11-30T16:01:00Z", portfolio_value: "1000", invested_value: "800" };

export const inputs = {
  target_date: "2026-10-30", changes: { start, end },
  snapshot: { total_value: "1000", investments: { currentValue: "800", totalCost: "700",
      realizedProfitLoss: "10", unrealizedProfitLoss: "100" },
    cash_components: { availableToTrade: "160", inPies: "30", reservedForOrders: "10" }, positions },
  weekly: [{ ...start, positions: baselinePositions }],
  baseline_positions: baselinePositions,
};

export const changesReport = () => JSON.stringify({
  method: "observed_portfolio_changes_v1", start, end,
  holdings: positions.map((row, i) => ({
    ticker: row.ticker, status: "quantity_unchanged", value_change: "50",
    start: { quantity: row.quantity, value: baselinePositions[i].current_value, weight_pct: null },
    end: { quantity: row.quantity, value: row.current_value, weight_pct: null },
  })),
});

export const options = {
  exportConfig: {
    holdings: {
      SYNl_EQ: { role: "core", theme: "Infrastructure", conviction: 4, thesis_status: "Under review",
        date_bought: "2026-08-04", next_catalyst: "2026-12-17", stop_gbp: "10", max_isa_pct: "55",
        pre_clearance_status: "Approved", pre_clearance_expiry: "2026-12-02" },
    },
    cash_interest: { rate_pct: "3.25", as_of: "2026-11-28", basis: "AER" },
  },
  exportEvidence: async () => ({
    monthly_net_deposits_gbp: "50", monthly_trade_activity: ["CLOSED_US_EQ"],
    monthly_dividends_gbp: { SYNl_EQ: "2" }, weekly_net_deposits_gbp: { "2026-10-20": "450" },
    isa: { tax_year_start: "2026-04-06", tax_year_end: "2027-04-05", as_of: "2026-11-30T16:00:00Z", limit_gbp: "20000", net_subscriptions_gbp: "500",
      remaining_from_this_isa_only_gbp: "19500", prior_funds_replaceable_gbp: "0" },
    trades: [{ at: "2026-11-01T12:00:00Z", ticker: "CLOSED_US_EQ", side: "SELL", units: "2",
      price: "10", currency: "GBP", proceeds_gbp: "20", realised_pnl_gbp: "4" }],
    trade_count: 1, trade_coverage: "incomplete", turnover_pct: null,
    orders: { as_of: "2026-11-30T16:02:00Z", rows: [
      { ticker: "SYNl_EQ", side: "SELL", status: "NEW", type: "LIMIT", quantity: "-1",
        filledQuantity: "0", limitPrice: "13", currency: "GBP", created_at: "2026-11-30T15:59:00Z" },
    ] },
  }),
};
