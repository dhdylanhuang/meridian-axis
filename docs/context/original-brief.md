# Archived original owner brief

This is historical source material. Its wording is retained below except that the personal workbook filename is replaced with a generic placeholder for public publication. It contains superseded and conflicting requirements; use [active product requirements](../product-requirements.md), the [decision register](../decisions-and-questions.md) and the owner's latest instructions to determine current scope. The imperative wording below does not authorise application implementation, commits or deployment during a documentation task.

Original attachment: `Pasted text.txt`, supplied by the owner. Do not depend on its machine-specific attachment location.

---

You are an expert full-stack developer and quantitative finance engineer. Build
a private, single-user personal portfolio tracking web app called "Great Dyke
Meridian". Its main summary view is called AXIS. The app will be used by two
people (the owner and a partner). Build it to run locally first. Remote access
comes in a later stage, but keep the design compatible with it.

## Goals
Replace an Excel workbook (portfolio-baseline.xlsx) with a data-dense,
dark-themed dashboard in the style of Koyfin or a Bloomberg-style terminal:
crisp, readable, and built for monitoring rather than marketing.

The Trading 212 CSV exports are the single ongoing source for holdings and
transactions. The app reads them directly and needs no manual re-entry.

Each holding's Slice label from the CSVs is used to organise the portfolio into
groups. The groups behave like sectors: they are used for grouping, aggregation,
exposure breakdowns, sector correlation and attribution. The app does NOT
model pies as objects. It has no pie targets, no pie RAG status, no pie-level
projections, and no pie-level alerts. A group exists only as a label that
holdings carry.

## Stack (fixed unless you find a strong reason to change it, then explain why)
- Backend: Python 3.11+, FastAPI, SQLAlchemy, SQLite (single file DB)
- Frontend: React + Vite + Tailwind CSS. Charts with ECharts (preferred for
  heatmaps and dense charts) or Recharts
- Market data: yfinance (free, unofficial) behind an adapter interface, so a
  paid provider can be added later without changing any calculation code
- Base currency: GBP. All values, returns and risk metrics are reported in GBP.
  Store the FX rate used for each valuation date
- Tests: pytest for all calculations

## Data sources
1. Trading 212 CSV exports (ongoing, primary). Read holdings and transactions
   from these. Validate headers (UTF-8-sig). Detect and exclude the "Total" row.
   Handle the "Dividends gained" field.
2. Excel workbook (one-off baseline). Import historical monthly total NAV and
   total contribution figures to seed the history charts. Mark every imported
   value with source = "excel_migration". Stage 1 acceptance: the imported totals
   match the Excel totals within £0.01.

## Grouping layer (built from the Slice label)
- Each transaction stores the raw Slice label as imported.
- Each instrument is assigned to exactly one group. The group is derived from the
  Slice label of its transactions. If an instrument appears under more than one
  Slice label, flag it for user review rather than guessing.
- Groups are stored in a groups table (name, display order, description). The
  user can rename a group or merge two groups. Renames and merges are logged in
  the audit log and do not alter the raw Slice labels in transactions.
- Group membership is stored separately from raw labels, so a change in group
  never rewrites imported data.
- Groups are used everywhere sectors would be: exposure breakdown, sector
  correlation matrix, sector attribution, and sector-level risk metrics.
- The Total row, cash rows, and any instrument with no Slice label go into a
  group called "Unassigned", which is shown with a warning count.

## Data model
- instruments: ticker, name, listing currency, exchange, asset class
  (stock/ETF/fund/cash), country, ISIN if available, group_id
- groups: id, name, display order, description
- transactions: buy, sell, dividend, fee, FX, deposit, withdrawal. Stores the raw
  Slice label. Deduplicated on Trading 212's transaction id
- holdings: derived from transactions (quantity, cost basis). Not entered by hand
- prices: daily close per instrument, with source and fetch timestamp
- fx_rates: daily GBP cross rates
- benchmarks: S&P 500 (VUAG) and MSCI World (IWDA), daily prices
- risk_free: UK Bank Rate, dated, editable
- valuations: daily snapshots of total NAV, per group, and per holding
- thesis_notes: dated free text per instrument or group, with an optional review date
- ticker_map: Trading 212 ticker to yfinance symbol, editable
- alerts: rule, threshold, triggered_at, acknowledged_at
- settings: all configurable values (windows, thresholds, risk-free rate,
  benchmark tickers, tax-year allowances)
- import_log: file name, file hash, row counts, status, timestamp
- audit_log: append-only. Timestamp, actor, action, entity, before/after JSON,
  and source file hash for imports

## Import pipeline
1. Trading 212 CSV import:
   - Reject any file whose hash has already been imported
   - Import in a single DB transaction. A failed import must leave no partial data
   - Report rows added, duplicates skipped and rows rejected
   - After import, recompute group assignments and list any instrument with
     conflicting Slice labels for review
2. Excel baseline import (one-off): as described under Data sources
3. Price and FX refresh: fetch daily data via the yfinance adapter, cache it, and
   record staleness. Show a warning when any price is more than one trading day old
4. Ticker mapping: store Trading 212 tickers and yfinance symbols separately.
   Warn on unmapped tickers rather than failing

## Cost basis and realised PnL (HMRC rules, UK)
- Use Section 104 pooling for each holding: track a pool of shares and its
  allowable cost, updated on each buy and sell
- Apply the same-day rule and then the 30-day (bed and breakfast) rule before
  matching sales to the Section 104 pool. Implement and test each rule separately
- Convert foreign-currency costs and proceeds to GBP at the transaction-date rate
- Calculate realised gains per UK tax year (6 April to 5 April). Show gains
  against the annual exempt amount and dividend allowance, both stored in settings
- Keep the calculation separate from the display so the figures can be checked
  by hand. Include a worked-example test for each rule

## Calculations (define each in code, with docstrings)
- Holdings: quantity, Section 104 cost, market value (GBP), unrealised PnL,
  realised PnL (HMRC method), dividends received, total return
- Allocation: each holding's weight of NAV, and each group's weight of NAV
- Group aggregation: market value, cost, unrealised and realised PnL, dividends,
  and return for each group. These are sums and ratios over holdings, not
  separate objects
- RAG status per holding, with configurable thresholds
- Returns: daily, MTD, YTD, since inception, and time-weighted return. State how
  cash flows are treated
- Risk (based on daily log returns over a configurable window, default 1 year):
  - Sharpe ratio, using the UK Bank Rate as the risk-free rate
  - Sortino ratio
  - Max drawdown and current drawdown from peak, with peak and trough dates
  - Historical VaR at 95% and 99%, and Expected Shortfall
  - Beta and Jensen's alpha vs VUAG (S&P 500) and vs IWDA (MSCI World), using a
    CAPM regression. Report R-squared and observation count
  - Concentration: top-5 and top-10 weight, HHI, and effective number of holdings,
    both overall and within each group
  - Overlap: flag holdings and ETFs with overlapping underlying exposure. If
    look-through data is unavailable, say so in the UI rather than guessing.
    Known case to test: VNRG and VUAG overlap by about 19% combined
  - Currency exposure: GBP vs USD, EUR and other, by listing currency and by
    underlying revenue currency where data exists
- Projections: compound growth from current total NAV to 30 April 2030, with
  monthly contributions. Scenario inputs (pessimistic, base, optimistic)
  editable in the UI. Reproduce the Excel projection figures exactly first
- Attribution: contribution to return by holding, group and currency, split into
  market (beta) and residual (alpha) components

## CORRELATION MODULE (key feature)
Build this as a dedicated module, shown in its own tab and linked from AXIS.

Calculation rules:
- Use daily log returns in GBP, aligned on common trading dates. Forward-fill
  holidays with a limit of 3 days, and flag any gap beyond that
- For non-synchronous markets (for example Asian listings), also offer weekly
  returns to reduce timing bias. Show which frequency is in use
- Windows: 30, 90 and 252 trading days, selectable in the UI
- Show the observation count and a warning when the overlap is below a
  configurable minimum (default 60 days). Do not present short-window
  correlations as reliable
- Shrinkage: offer Ledoit-Wolf shrinkage as an option for the full covariance
  matrix, and show the difference

Views:
1. Stock-to-stock correlation matrix: all holdings, heatmap with values, sorted
   by hierarchical clustering so related names group together. Clicking a cell
   shows the rolling correlation over time for that pair. Group boundaries are
   drawn on the matrix
2. Group (sector-style) correlation matrix: group indices built as
   weight-averaged returns of the holdings in each group, with weights based on
   current holdings. Include a group-to-benchmark correlation column
3. Benchmark correlation: each holding and group against VUAG and IWDA, sorted
   by value, with 30/90/252-day rolling values
4. Concentration of risk from correlation:
   - Average pairwise correlation across all holdings, and within each group
   - Effective number of independent bets, from the eigenvalues of the
     correlation matrix
   - Diversification ratio
   - Highest-correlated pairs that are both held (flagged as overlap risk)

Correlation alerts (stored in alerts and shown on AXIS):
- Average pairwise correlation across holdings rises above a threshold
- Any held pair's 90-day correlation exceeds a threshold (default 0.85)
- A holding's or group's correlation to VUAG exceeds a threshold
- The number of effective bets falls below a threshold

Tests:
- Matrices are symmetric, with diagonals of 1 and values in [-1, 1]
- Matrices are positive semi-definite (within numerical tolerance)
- Known synthetic series return known correlations
- A pair with insufficient overlap is flagged, not silently computed
- The VNRG and VUAG overlap case is reproduced from fixture data

## Dashboard tabs
1. AXIS (summary): total NAV (GBP), day/MTD/YTD returns, Sharpe, Sortino, max
   drawdown, average pairwise correlation, effective number of bets, next alert,
   data freshness
2. GROUPS: the Slice-based grouping view. For each group: market value, weight,
   return, unrealised and realised PnL, dividends, and holdings count. Drill
   down to the holdings in that group. Includes rename, merge and reassignment
   controls, all logged to the audit log
3. EXPOSURES: holding weights, group breakdown, currency exposure, overlap flags
4. CORRELATION: the module above
5. HOLDINGS: sortable table with ticker, group, quantity, Section 104 cost,
   current price, market value, weight, unrealised and realised PnL, dividends,
   RAG, and a link to the thesis. Filterable by group
6. RISK: VaR 95/99, drawdown chart, concentration (overall and by group),
   rolling beta, stress tests. Interactive toggles: market -10%, -20%, tech
   sell-off, GBP up 5%, GBP down 5%, and a custom shock on any holding or group
7. TRANSACTIONS: filterable log, import history, and the full audit trail
8. ATTRIBUTION: alpha vs beta, win/loss ratio, profit factor, average holding
   period, PnL by holding and group, and the tax-year realised gains summary
9. HISTORY: total NAV and contributions over time, seeded from the Excel baseline

## Alerts (configurable, stored in the DB, shown in the UI)
- Drawdown from peak exceeds X% (total portfolio, individual holding, and group)
- Daily move exceeds X% for any holding
- Single holding weight exceeds X% of NAV
- Group weight exceeds X% of NAV
- Correlation alerts (see the correlation module)
- VaR 95 exceeds X% of NAV
- Price data older than one trading day, or a failed import
- Thesis review due (date set per thesis)
- Instrument with conflicting Slice labels awaiting review

## Security (local stage)
- Bind the app to localhost only
- Login for both users, with hashed passwords (argon2 or bcrypt), session
  cookies (secure and httponly flags), and CSRF protection. Build these now so
  the app is ready for remote access
- Keep secrets in environment variables. No keys in the code or the repo
- Write the audit log for every change, including logins, imports, renames and merges

## Local LLM notes
- The model runs locally (Qwen 35B class). Keep each file small and build in
  stages, finishing and testing each stage before starting the next
- Use fixtures and small sample data for tests so no network call is needed.
  Mark any test that calls yfinance as optional

## Build stages
Stage 1: DB schema. Excel baseline import with reconciliation test (imported
totals match the Excel totals within £0.01). Trading 212 CSV import with dedupe,
import log, and Slice-based group assignment with conflict detection. Holdings
and allocation calculations.

Stage 2: HMRC Section 104 cost basis with the same-day and 30-day rules, and
tests. Price and FX adapter (yfinance). Audit log.

Stage 3: Risk calculations (Sharpe, Sortino, drawdown, VaR, beta, alpha,
concentration, overlap, currency exposure). Projections. The correlation module
and its tests. Group aggregation.

Stage 4: API endpoints and React dashboard, including all nine tabs and the
alerts engine. Stress tests.

Stage 5: Authentication, SQLite backup script, and local run instructions.

Stage 6 (later, after local is stable): remote access via Tailscale or Cloudflare
Tunnel with Access, and deployment notes.

## Deliverables per stage
- Code, file tree, tests, and a short README with run commands
- A list of assumptions made (for example the cost-basis handling of stock
  splits, the yfinance ticker mapping, how an instrument with several Slice
  labels is resolved, how Unassigned is handled, and the treatment of cash
  flows in returns) so they can be confirmed
