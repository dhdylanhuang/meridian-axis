# Testing and acceptance strategy

Status: acceptance strategy plus verified local foundation, broker-observation, snapshot-evidence and closed identity/session slices. Shared-limiter checkpoint `de5269a` passes Windows/Linux checks and **53 service-backed PostgreSQL cases**, including real database time, concurrent admission, blocked-row timeout and restricted session-service permissions. The full local suite passes **299 offline cases** (including 46 HTTP tests), with 53 PostgreSQL cases skipped locally. HTTP tests use offline ASGI/SQLite fixtures, not browser cookie-policy enforcement or live Supabase identities. Later financial/UI rows remain planned. Actual hosted application security and capacity remain separate gates; see status/handoff. Workbook inspection alone is not an application-test pass.

## Test layers

1. Pure calculation unit tests using small deterministic series/events with hand-checkable expectations.
2. Adapter contract tests using sanitised fixtures and a mocked HTTP transport; no default network calls.
3. SQLite local-tooling and PostgreSQL integration tests for migrations, precise round-trips, constraints, transactions, dedupe and audit. Hosted grants/RLS/Auth plus Postgres/evidence export/restore are separate gates; SQLite recovery tests do not establish them.
4. Application/API tests for authentication, CSRF, authorisation, jobs and versioned result semantics.
5. Focused UI tests and visual inspection for data states, dense tables/matrices, concurrent changes and streaming recovery.
6. Optional provider integration tests explicitly marked/opted in; never require Live credentials to run ordinary checks.

Use pytest for backend calculations and integration. Frontend tooling is selected with its first implementation task; use the smallest maintained stack that tests meaningful interaction. Pin versions/lockfiles before claiming reproducibility. Inject clock, transport, calendar and configuration; tests must not depend on current market hours or downloaded values.

## Fixture policy

Fixtures live with tests, not in `docs/`. Use synthetic or deliberately sanitised records. Retain only necessary schema/identity relationships; remove keys, secrets, account numbers and unnecessary personal data. A fake schema that differs from the provider is not a valid contract fixture. Record fixture origin/version and the expected result separately from the implementation.

Required fixture families: full/partial fills, repeated IDs, corrected-ID conflict, duplicate CSV/API event alias, ticker Slice versus Total-row Name group context, conflicting group exports, Total row, N/A per-holding and nonadditive group dividend controls, fee/withholding/multi-currency, missing opening history, corporate-action unknown, exchange holidays/half-days/DST/lunch break, zero-variance series, PSD/singular covariance, quote timestamp unknown, stale FX, failed later page and scheduler restart.

## Acceptance matrix

| Requirement | Meaningful acceptance evidence |
| --- | --- |
| D01/D02 | Paths/schemas match verified YAML; Basic secret redacted; Demo default; separate history families; cursor terminates and repeated path detected |
| D03/D04 | Hash duplicate rejected; overlapping API/CSV events produce one economic ledger entry in either order; changed same-ID record flags conflict |
| Atomic import | Failure after staged valid rows leaves zero partial financial writes, no checkpoint advance and a persisted failed-run diagnostic |
| D05 | Six workbook snapshots retain source/hash/cells/date precision/coverage and match recorded totals within £0.01; blank future rows omitted |
| G01/G02 | Missing label Unassigned; multiple labels reviewable; manual override persists after sync; rename/merge does not alter raw evidence |
| P03/C01 | Decimal quantity/cash round-trip; pence conversion; reversed FX pair validated; missing rate yields unavailable GBP value; broker snapshots not double counted |
| C02 | NAV denominator, including cash where supported; weights reconcile; empty group and zero/negative NAV handled |
| C03 | Deposit-only portfolio has zero investment return under the chosen timing convention; known TWR chain; cash flows absent from income |
| T01/T02 (DEFERRED) | Future tax phase only: worked pool/same-day/30-day examples and boundaries; not initial-release acceptance |
| R01 | Known Sharpe/Sortino sample; zero variance/downside; wealth-based drawdown unaffected by a deposit; quantile/ES rule and tail count fixed |
| R02 | Synthetic regression with known intercept/slope; singular benchmark unavailable; date alignment, effective RF, n/R² and alpha units verified |
| R03/R04 | Equal weights give HHI=1/n; top-k with fewer holdings; direct+fund exposure reconciles; incomplete look-through not renormalised away |
| F01/F02 | Legacy FV fixtures within £0.01; zero rate; contribution timing; dated horizon; forecast and target remain separate |
| X01 | PnL attribution sums to supported portfolio PnL; closed positions included; FX interaction explicit; trade-stat denominator fixed |
| K01–K05 | Known +1/−1/0 series; symmetry/diagonal/bounds/PSD; singular valid matrix; shared panel; missing group member and short overlap visible |
| L01/L02 | Fixed-clock held-only polling, holidays/half-day/DST/lunch break, one scheduler and no overlap/manual budget bypass |
| L03–L05 | Failed poll preserves last good; unknown quote age disclosed; raw and GBP price retain FX; provisional close excluded from risk; same-date 0.5% discrepancy |
| A01–A03 | One excursion, repeated breach, acknowledgement, recovery/re-arm, restart, rule revision and stale-input unknown state |
| U01/U02 | Nine tab contracts, sorting/filtering, empty/loading/error states, thesis review dates and both login sessions |
| S01/S02 | Password hashing/session expiry/revocation; missing session/CSRF denied; equal full-editor access for both users; secrets absent from all response/log evidence; mutation audit atomic |
| O01 | Upgrade fixture, consistent backup and successful separate-path restore with integrity/count/financial controls |

## Worked financial invariants

All amounts below are invented test inputs, not the owner's finances.

- £100 opening cash plus £50 external deposit and no market movement: closing NAV £150, investment PnL £0. Performance method uses the recorded flow timing, not +50% raw NAV growth.
- Buy 10 at £5 from £100 cash, no charges: £50 cash + £50 securities = £100 NAV. The buy is not another contribution.
- Receive £2 dividend and reinvest £2: income £2, external contribution £0; no duplicate dividend from a cumulative snapshot.
- £200 cash plus two holdings worth £300 and £500: NAV £1,000; weights 20/30/50%. Securities-only concentration separately uses 37.5/62.5%.
- Quote 1,250 pence, quantity 2, GBP listing: value £25, not £2,500. Preserve raw unit and multiplier.
- Price £100 at quote currency/GBP rate 0.8, quantity 2: GBP value £160, with that exact rate retained. New FX alone changes GBP value while the local quote remains unchanged.

Deferred tax examples are in [tax](tax.md); legacy methods and known defects are in the public-safe [workbook baseline](workbook-baseline.md). Exact source values are read privately, not copied to public fixtures. Do not use broken source formulas as expected correct outputs.

## Numerical and property checks

Use precise Decimal equality for identities, quantities and exact ledger controls where the source supports it. Penny reconciliation allows £0.01 on stated source totals; do not round every intermediate component early. Floating-point analytics use documented tolerances/scale and deterministic random seeds when generated data is needed. Independent expected calculations must not call the function under test to generate their own expected answer.

Matrix checks supplement known-series tests; a symmetric PSD matrix of invented zeros is not correctness. Similarly, a passing import-count check without a cash/quantity reconciliation is incomplete evidence.

## Test report and release evidence

Record exact command, environment/runtime versions, relevant fixture set, passed/failed/skipped counts and limitations. Optional skipped network tests are not a claim that Live integration works. Once meaningful checks pass, avoid repeatedly running unrelated expensive suites without new risk.

Each gate names evidence a reviewer can reproduce. A final local acceptance includes both users, actual source reconciliation, source-failure behaviour, dense UI inspection, migration/restore and documented unsupported cases. Do not mark a stage complete merely because its files exist.

## Confirmed alert regression cases

Use synthetic wealth samples. A group falls from 100 to 90: the >=10% default fires. A portfolio path 100 → 97.5 → 100.5 within two trading days has a 2.5% peak-to-trough decline even though its endpoint return is positive, so the >=2% rolling maximum rule fires. A rebound alone does not erase a historical rolling maximum; re-arm once the measured statistic is inside threshold, including after the old decline ages out. Test deposits/withdrawals, exact boundaries, restart and repeat crossings. Preserve sampling/gap quality; never invent intraday extremes from daily closes.
