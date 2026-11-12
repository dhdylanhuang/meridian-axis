# Application API and user interface

Status: ADOPTED design proposal, with the explicitly configured session component below verified in offline/CI tests. Other route families remain planned, **not existing endpoints and not Trading 212 endpoint paths**. Provider routes belong only in the broker adapter.

The [deployed dashboard preview](https://meridian-axis-preview.meridian-worker-feasibility.workers.dev) implements AXIS, HOLDINGS and GROUPS as a standalone static interface with invented fixtures. It has no financial API or account connection. Other nine-tab requirements and real financial behavior remain unimplemented; see [preview evidence and limits](status-and-handoff.md#dashboard-preview-delivered---12-november-2026).

## Interface principles

Build a dense dark monitoring tool with legible numbers, compact sortable tables and chart labels that remain readable at normal desktop zoom. Use tabular numerals, consistent GBP/percentage formatting and accessible focus/contrast. Colour is secondary to text/symbols for gain, loss, quality and alerts. Avoid decorative hero panels, marketing copy and fabricated sample balances in a real account view.

Use React/Vite/Tailwind and prefer ECharts for matrices and dense charts. Keep query state, persisted settings and transient scenario inputs distinct. Use generated/typed DTO contracts where useful; do not add a state-management framework solely because one might eventually be useful.

## Common response and mutation contract

Financial responses identify environment/account, as_of, result_version, currency, method, source/quality, observation count/coverage and unavailable reason. Use decimal strings for precise amounts and provider IDs, numeric floating-point values for explicitly analytical chart arrays. Missing means null with a reason, never zero. Date-only/session dates remain distinct from UTC timestamps.

List endpoints use bounded pagination and stable ordering. Sort/filter holdings and transaction lists server-side when needed; the frontend must not invent economics from a filtered page. Every mutation validates input, checks an authenticated full-editor session and CSRF, accepts an expected revision for conflict detection, commits audit with the change and returns the new revision. Unknown concurrent revision produces a conflict rather than silently losing another user's edit.

Long operations create job IDs and return promptly. Job state includes queued/running/succeeded/failed/cancelled, progress where measurable, result generation and safe diagnostics. Idempotency applies to manual sync and correction requests; no repeated button click creates duplicate economics.

## Proposed route families

| Family | Intended operations |
| --- | --- |
| `/api/v1/session` | Login/logout/current user; CSRF bootstrap/rotation; no broker credentials |
| `/api/v1/axis` | Coherent summary snapshot, source coverage, alerts and revision |
| `/api/v1/holdings`, `/groups` | Read/filter; explicit group rename/merge/reassignment operations |
| `/api/v1/exposures` | Listing currency, group/holding weights, look-through coverage |
| `/api/v1/transactions`, `/imports`, `/audit` | Filtered evidence/event history, import dry-run/accept, audit reads |
| `/api/v1/sync-jobs`, `/jobs/{id}` | Manual broker sync/market refresh and job status |
| `/api/v1/history` | Baseline and calculated observations with source and date precision |
| `/api/v1/risk`, `/correlation` | Versioned eligible analytics; pair/rolling requests |
| `/api/v1/attribution`, `/tax` | Reconciled PnL/matching reports and explicit unsupported states |
| `/api/v1/projections`, `/stress` | Portfolio scenario calculation and validated inputs |
| `/api/v1/theses`, `/alerts`, `/settings`, `/ticker-mappings` | Audited edits and review/acknowledgement controls |
| `/api/v1/events` | Authenticated SSE with snapshot version and reconnect support |
| `/health` | Minimal service liveness without portfolio/private configuration |

Final methods/schemas are established in the implementation task and FastAPI OpenAPI. Do not implement a public arbitrary SQL, filesystem-path or provider-request proxy endpoint. File uploads are size/type validated and stored privately; server paths are not client-controlled migration credentials.

### Verified session component

`create_app()` still exposes liveness only by default. Supplying an explicit `SessionHttp` enables the following routes; it requires a verified provider adapter, request-owned database factory, session service, shared atomic login-limiter callback and secret signing key of at least 32 bytes. A deployment must generate a random key, configure the shared limiter and qualify proxy/runtime access before activation. There is no local-memory production limiter fallback.

| Route | Contract |
| --- | --- |
| `GET /api/v1/session/bootstrap` | Return a prelogin CSRF nonce and set its signed, HttpOnly, five-minute cookie |
| `POST /api/v1/session/login` | Exact Origin, signed prelogin cookie/nonce header, shared limiter, bounded credentials JSON, verified provider identity and atomic membership-checked session/audit |
| `GET /api/v1/session/current` | Return authenticated subject and expiry only; browser reads its independent CSRF cookie |
| `POST /api/v1/session/rotate` | Exact Origin and bound CSRF header; consume old session, issue new token/nonce and preserve original expiry |
| `POST /api/v1/session/logout` | Exact Origin and bound CSRF header; atomically revoke/audit, then expire cookies |

All session routes require the configured HTTPS authority; foreign Origin headers are rejected on reads, and mutations require Origin. No forwarded header can choose the accepted authority. Cookies use `__Host-` names, Secure, SameSite=Strict, Path=/ and no Domain; the authentication cookie is HttpOnly, while the independent CSRF cookie is browser-readable. Authentication/provider tokens never enter response JSON. Responses are non-cacheable, including route/method failures; automatic slash redirects are disabled. Login accepts at most 8 KiB streamed JSON with exactly string `email`/`password` fields and rejects duplicate keys; fixed errors never echo credentials. Cookie issuance follows commit. These routes do not perform provider refresh or extend a session beyond its original expiry, and are not a usable portfolio application. The empty hosted transport now passes actual HTTPS denial, prelogin-cookie and shared-limiter qualification; positive login for either approved identity remains open. All current routes are finite JSON, with direct ASGI privacy-header middleware; adding streaming/background work requires new resource-lifecycle qualification.

## Nine-tab contract

| Tab | Required content | Honest states and interactions |
| --- | --- | --- |
| **AXIS** | Total NAV or clearly labelled holdings value; day/MTD/YTD; Sharpe/Sortino/max drawdown; average correlation/effective bets; next actionable alert; stale count | Global environment/as-of; intraday versus EOD basis; incomplete data banner; manual sync progress; links to detail |
| **GROUPS** | Value, weight, supported return, unrealised/realised management PnL, dividends, held count and 10% drawdown alert state | Drilldown; rename/merge/reassign with review and audit; Unassigned/conflict counts; no targets, group RAG or projections |
| **EXPOSURES** | Holding/group allocation, listing-currency breakdown, supported underlying currency and overlap | Denominators/coverage explicit; no-data explanation instead of inferred look-through |
| **CORRELATION** | Holding/group heatmaps, benchmarks, pair rolling, shrinkage toggle and diagnostics | Frequency/window/estimator/counts visible; clustering/group sort modes; low overlap warning; unavailable series listed |
| **HOLDINGS** | Ticker/name, group, quantity, management cost; tax cost deferred, current price, value, weight, PnL, dividends, RAG and thesis link | Sort/filter groups; price source/time/delay; tax not applicable/incomplete states; closed positions separate from live poll universe |
| **RISK** | Historical VaR95/99 and ES, drawdown chart/dates, concentration overall/by group, rolling beta and stress toggles | Method/window/count and loss horizon; flow-adjusted wealth; scenario assumptions and custom target selection |
| **TRANSACTIONS** | Filterable economic events; import/sync history; full authorised audit trail | Raw evidence details redacted appropriately; failed rows/conflicts; dedupe counts; polling log filter |
| **ATTRIBUTION** | PnL by holding/group/currency; market/residual analysis; win/loss, profit factor, holding period; tax-year summary deferred | Method gates; reconcile residual; wrapper-aware tax; undefined trade statistics remain unavailable |
| **HISTORY** | Recorded value, true external contributions where available, baseline source invested amounts, cumulative dividends | Irregular snapshot spacing; no fabricated month-end dates; baseline versus derived precedence; May missing Space and July ambiguity visible |

The portfolio planning goal is £100,000 by 30 April 2030; target and forecast remain distinct. Portfolio projections and scenario settings can be a panel/drawer linked from AXIS/HISTORY, not an extra mandatory top-level tab or a group-projection feature. Thesis editing is a holding/group detail action. Settings may be a utility screen; nine tabs describe the main portfolio navigation, not a prohibition on login/settings screens.

## Data quality vocabulary

- `Available`: supported inputs and stated method.
- `Provisional`: incomplete finalisation or selected temporary evidence; explain why.
- `Insufficient history`: required observation count or ledger coverage missing.
- `Not applicable`: account wrapper/entity does not use this measure.
- `Unavailable`: unsupported field/provider or unresolved mapping.
- `Failed`: operation did not succeed; show last successful result with age when safe.

Show reason/coverage beside affected values, with details on demand. Avoid a global green badge when an important underlying calculation failed. Preserve known genuine zero values.

## SSE and interaction states

Both authenticated sessions receive committed updates. Start from a snapshot, apply events with versions, ignore obsolete versions and refetch on a gap/reconnect. Heartbeats/quality events allow unchanged prices to remain visibly monitored. Losing SSE does not log the user out or turn every price to zero; show reconnecting and preserve last data ages.

Support first-run empty, no credentials, Demo with no positions, source-down, incomplete history, pending recomputation, stale FX, conflicting group labels, cancelled jobs and expired session. Loading skeletons must not resemble real values. Destructive local changes such as a group merge or import reversal get a concrete impact preview before execution; normal reversible reads/filters need no confirmation.

## Frontend verification

Use representative invented data including 100 holdings and a dense matrix, not copied source position sizes. Test sorting, filters, missing/zero distinctions, decimal/ID precision, accessible keyboard paths, source/basis labels, two-session changes, stale updates, reconnect recovery and error diagnostics. Verify layout at normal desktop zoom plus a narrow viewport; do not trade readability for a one-screen screenshot. Financial formula correctness belongs to backend tests; UI tests verify presentation and interaction contracts.

The minimal onboarding page adds `POST /api/v1/session/setup` under the same
transport protections as login. Exact JSON fields are `token_hash`, `type`
(`signup` or `recovery`) and `password` (12–128 characters). Only active members
may change their password or receive an application session. The three fixed
same-origin assets `/`, `/signin.js` and `/signin.css` contain no provider key,
user identity or private data; CSP permits only this origin. Signed-in content
currently confirms access and explicitly states that portfolio data is absent.
