# Application API and user interface

Status, **13 November 2026:** session, portfolio snapshot, manual refresh and refresh-health routes below are deployed. The broader route-family and nine-tab tables describe the target design. Provider routes belong in the broker adapter. [Current status](status-and-handoff.md) owns deployment and acceptance evidence.

The [deployed dashboard preview](https://meridian-axis-preview.meridian-worker-feasibility.workers.dev) implements AXIS, HOLDINGS and GROUPS as a standalone static interface with invented fixtures. It has no financial API or account connection. The private application separately serves real broker-reported AXIS/HOLDINGS data and refresh controls. The remaining target screens and calculated analytics are open. See [historical preview evidence](status-history.md#dashboard-preview-delivered---12-november-2026) and [current application status](status-and-handoff.md).

## Interface principles

Build a dense dark monitoring tool with legible numbers, compact sortable tables and chart labels that remain readable at normal desktop zoom. Use tabular numerals, consistent GBP/percentage formatting and accessible focus/contrast. Colour is secondary to text/symbols for gain, loss, quality and alerts. Avoid decorative hero panels, marketing copy and fabricated sample balances in a real account view.

Use React/Vite/Tailwind and prefer ECharts for matrices and dense charts. Keep query state, persisted settings and transient scenario inputs distinct. Use generated/typed DTO contracts where useful; do not add a state-management framework solely because one might eventually be useful.

## Target response and mutation contract

Future derived financial responses identify their fixed application scope, as_of, result_version, currency, method, source/quality, observation count/coverage and unavailable reason. The deployed broker snapshot follows the explicit projection contract below and omits the private broker account reference. Use decimal strings for precise amounts and provider IDs, numeric floating-point values for explicitly analytical chart arrays. Missing means null with a reason, never zero. Date-only/session dates remain distinct from UTC timestamps.

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
| `POST /api/v1/session/setup` | One-use provider setup token, same login CSRF/limiter, verified active member, prior-session revocation, password update and fresh session |
| `GET /api/v1/session/current` | Return authenticated subject and expiry only; browser reads its independent CSRF cookie |
| `POST /api/v1/session/rotate` | Exact Origin and bound CSRF header; consume old session, issue new token/nonce and preserve original expiry |
| `POST /api/v1/session/logout` | Exact Origin and bound CSRF header; atomically revoke/audit, then expire cookies |

All session routes require the configured HTTPS authority; foreign Origin headers are rejected on reads, and mutations require Origin. No forwarded header can choose the accepted authority. Cookies use `__Host-` names, Secure, SameSite=Strict, Path=/ and no Domain; the authentication cookie is HttpOnly, while the independent CSRF cookie is browser-readable. Authentication/provider tokens never enter response JSON. Responses are non-cacheable, including route/method failures; automatic slash redirects are disabled. Login accepts at most 8 KiB streamed JSON with exactly string `email`/`password` fields and rejects duplicate keys; fixed errors never echo credentials. Cookie issuance follows commit. Session rotation preserves original expiry. Supabase provider-token refresh remains unimplemented, so expiry requires a fresh login. Broker data refresh uses the separate authenticated portfolio route. Both approved identities passed hosted setup/login/session/logout checks, and the owner confirmed browser sign-in. Partner browser confirmation and the remaining browser audit are open. All current routes are finite JSON, with direct ASGI privacy-header middleware; adding streaming/background work requires new resource-lifecycle qualification.

## Portfolio navigation contract

| Tab | Required content | Honest states and interactions |
| --- | --- | --- |
| **AXIS** | Total NAV or clearly labelled holdings value; day/MTD/YTD; Sharpe/Sortino/max drawdown; average correlation/effective bets; next actionable alert; stale count | Global environment/as-of; intraday versus EOD basis; incomplete data banner; manual sync progress; links to detail |
| **GROUPS** | Value, weight, supported return, unrealised/realised management PnL, dividends, held count and 10% drawdown alert state | Drilldown; rename/merge/reassign with review and audit; Unassigned/conflict counts; no targets, group RAG or projections |
| **EXPOSURES** | Holding/group allocation, listing-currency breakdown, supported underlying currency and overlap | Denominators/coverage explicit; no-data explanation instead of inferred look-through |
| **CORRELATION** | Holding/group heatmaps, benchmarks, pair rolling, shrinkage toggle and diagnostics | Frequency/window/estimator/counts visible; clustering/group sort modes; low overlap warning; unavailable series listed |
| **CASH** | Broker cash components, year-to-date income and funding by currency, and on-demand transaction detail | Current cash is separate from past activity. Coverage and source timing are visible, and History links into Cash. |
| **HOLDINGS** | Ticker/name, group, quantity, management cost; tax cost deferred, current price, value, weight, PnL, dividends, RAG and thesis link | Sort/filter groups; price source/time/delay; tax not applicable/incomplete states; closed positions separate from live poll universe |
| **RISK** | Historical VaR95/99 and ES, drawdown chart/dates, concentration overall/by group, rolling beta | Method/window/count and loss horizon; flow-adjusted wealth |
| **PROJECTIONS** | Baseline and two editable plans for £100,000 by 30 April 2030 | Approved GBP opening capture, dated deposits, full allocations, growth assumptions, chart and schedule |
| **STRESS TESTS** | Two deterministic direct-price scenarios | Editable defaults, custom basket, per-holding overrides, loss drivers, GBP cash and uncovered value |
| **TRANSACTIONS** | Filterable economic events; import/sync history; full authorised audit trail | Raw evidence details redacted appropriately; failed rows/conflicts; dedupe counts; polling log filter |
| **ATTRIBUTION** | PnL by holding/group/currency; market/residual analysis; win/loss, profit factor, holding period; tax-year summary deferred | Method gates; reconcile residual; wrapper-aware tax; undefined trade statistics remain unavailable |
| **HISTORY** | Recorded value, true external contributions where available, baseline source invested amounts, cumulative dividends | Irregular snapshot spacing; no fabricated month-end dates; baseline versus derived precedence; May missing Space and July ambiguity visible |

The top-level planning tabs share the existing approved Trading 212 GBP ISA
snapshot and keep assumptions in page memory. Historical risk measures remain
in Risk. In Holdings, selecting a name opens a keyboard-accessible detail
dialog with the approved broker position value, average purchase price, saved
price, quantity and capture time. Position values use the reported account
currency. Prices use the reported listing currency when available.

The dialog provides investment-thesis and exit-criteria fields with optional
writing prompts. Saved notes are scoped to a broker listing and environment
in the current browser profile. They persist across reloads in that profile.
A shared browser profile can expose the same saved notes to both members.
Signing out clears the displayed holding and note text. This local implementation
does not use the planned shared, revisioned instrument and group note store.

The authenticated Worker handles `POST /api/v1/portfolio/projections` and
`POST /api/v1/portfolio/stress-tests`. Both accept JSON assumptions plus
the displayed account and holdings capture timestamps. The gateway requires
the configured Origin, matching CSRF cookie and header, and a successful
authenticated approved-snapshot read from the existing Python session owner.
It returns a capture conflict if the latest approved snapshot has advanced,
passes decimal strings to Rust WASM and returns no-store JSON. Inputs contain
no client-provided balances. The endpoints perform a read-only saved-snapshot
lookup. Assumptions and computed holdings impacts are kept out of public assets.

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
may change their password or receive an application session. The four fixed
same-origin assets `/`, `/signin.js`, `/snapshot.js` and `/signin.css` contain no
provider key, user identity or private data. CSP permits only this origin.
Signed-in content retrieves the approved portfolio snapshot after authorization.

## Authenticated broker snapshot — 13 November 2026

`GET /api/v1/portfolio/snapshot` is the bounded first financial view. It uses the opaque same-origin application session and rechecks active membership for every request. No account identifier, filter or pagination parameter is accepted. Anonymous/expired/revoked/unrelated sessions are denied; Origin/authority checks and no-store privacy headers apply to success and error responses. The runtime reads only `broker_snapshots`, not raw broker history.

Response fields come from the approved broker-reported projection: source/basis/environment/currency; exact decimal-string total value; reported investments/current value/cost/PnL; separately labelled cash components; holdings with reported quantity, instrument-currency price and account-currency value/cost/PnL; separate account/positions retrieval windows; unknown quote time; unavailable historical returns. Missing fields stay null. No broker account ID, source payloads, provider credentials or session token is returned. Empty storage returns 404 `snapshot_unavailable`; integrity/storage failure fails closed.

Successful exposure calculation adds `exposures` to the same snapshot response.
It contains the source snapshot identity and dates, both broker controls used as
denominators, ranked holding weights, quote-currency buckets, coverage,
concentration and independent cash weights. No new route or request is needed.
The Exposures tab links each bucket and ranked holding to the same Holdings table
with a reversible filter. Equity sectors, issuer domicile and fund market
allocations add the exact bucket contribution and source date/link for each
contributing holding. Older approved snapshots open with the original exposure
results and a clear classification availability message. Holdings retains the original broker values alongside its
two weight columns. Both members use the existing approved snapshot access path.
Logout clears exposure and drill-down state.


AXIS shows reported account figures and HOLDINGS supplies search and exact-decimal sorting. Monetary values are formatted from strings without JavaScript Number coercion. Values are not summed to replace the broker total. The browser retrieves the last successfully published snapshot every ten minutes while visible. Snapshot JSON includes browser-safe `refresh_health`, so the client makes one authenticated request per read. Scheduled jobs refresh Trading 212 separately during relevant sessions. The Reload saved snapshot control reads approved storage with a one-minute browser cooldown, and Refresh Trading 212 queues authenticated broker work with a shared one-minute signal cooldown and the persisted ten-minute snapshot eligibility. Hidden tabs pause polling. Transient failures back off from ten minutes to one hour; failed reads preserve last-good figures. Sign-out, expired sessions and denied reads clear financial DOM/state; in-flight responses cannot repopulate it after clearing. The existing synthetic React preview remains separate.

## Observed account history

`GET /api/v1/portfolio/history` uses the same shared account, membership
checks, fixed authority and no-store response policy as the approved snapshot
route. Queries and account selectors are rejected. The response gives source,
basis, currency (GBP), UTC `as_of`, `start_date`, `end_date` and 90 ordered
`days`, including today through `as_of`.

For each UTC date, the final approved snapshot is the row with the greatest
`observed_at`, with descending snapshot ID breaking ties, consistent with
daily retention. An `observed` day includes exact decimal-string
`total_value`, `captured_at` from account-summary retrieval completion and
`observed_at` from the overall snapshot capture. A `missing` day has no saved
row. An `unavailable` day has a saved row that failed integrity or field
validation. Gaps remain empty. The account value includes funding effects and
is an observed mark. Transaction totals and their detail reads retain their
own coverage periods and sources.

The History tab loads once on demand and reloads on request without broker
calls. The chart connects adjacent observed days. The daily table and chart
selection give the original amount and capture times. Sign-out clears the
response and invalidates in-flight reads.

### Funding timeline and observed returns

The same History response adds an optional `performance` report. It contains
the dated transaction evidence visible on the 90-day timeline, completed
funding coverage, valuation and eligible stretches, per-interval return
eligibility, and the latest eligible, month-to-date and year-to-date results.
Funding markers link to the selected day's transaction records and their
Trading 212 references. The separate income totals and detail pages continue
to use their own coverage.

The session application authenticates the shared account and selects approved
daily observations before any private service call. It uses enough retained dates
to check the year boundary internally. The fixed sync object uses its existing
role to read completed funding evidence in a bounded read-only transaction and
invokes the Rust method through the private WASM service. No transaction remains
open during that invocation. No external broker call or new public route is
needed. The private service passes the bounded Rust JSON to the session
application. A failed read reports a fixed `performance_state` and preserves
the 90-day account value response. See [the calculation rules](calculation-contracts.md#observed-modified-dietz).

### VUAG benchmark availability

The optional History performance report includes `benchmark.state`,
eligible and matched counts, and per-interval portfolio return, VUAG return,
percentage-point difference, price and capture endpoints, and any gap reason.
With no valid reviewed close series, saved per-share GBP VUAG position marks
can produce `broker_observed`. That basis reports holdings capture times and
shows gaps for missing marks. Older snapshots qualify by the exact Trading 212
ticker and GBP currency. Any reported ISIN must agree. Without qualifying marks,
an absent or invalid close series leaves the benchmark unavailable. Portfolio
performance still loads. The comparison uses the existing private Rust service.

Supply the reviewed input as a private gateway binding `VUAG_GBP_BENCHMARK`
using the existing raw JSON or `gzip:` base64 format. The binding is optional
and capped at 5,120 characters. The object accepts exactly these keys:

| Key | Value |
| --- | --- |
| `ticker`, `isin`, `currency` | `VUAG`, `IE00BFMXXD54`, `GBP` |
| `basis` | `split_adjusted_lse_market_close_accumulating` |
| `source` | Display label of the approved dated source |
| `reviewed_at` | UTC ISO 8601 review timestamp |
| `rows` | Between 2 and 367 rows ordered by distinct date, each with `date`, UTC `pricing_at` on the same date, and positive exact-decimal string `price_gbp` |

Source qualification must cover the right to serve prices and derived returns
to both members, the GBP listing and pricing time convention, and split treatment.
Keep review and provenance evidence private and retain the revision covering
the requested dates. The input is deployment-managed with no provider polling.
Daily comparison is the initial scope. Longer benchmarks require an eligible
portfolio period and matching benchmark evidence.

### Risk tab

`GET /api/v1/portfolio/risk` authenticates the shared account and returns a
no-store drawdown result from the private Rust calculation. It accepts either
the default 90-day window or exactly `?start=YYYY-MM-DD&end=YYYY-MM-DD`.
The dates are UTC snapshot dates, inclusive, and must span at least two dates
within the last 367 UTC dates. Risk returns drawdown, observed losses and daily
metrics with observation counts and availability. Current concentration reuses
the latest authenticated snapshot. History displays portfolio and benchmark
performance.

Approved session valuation evidence is supplied privately through
`RISK_DAILY_GBP`. The existing approved index-only format remains readable.
The preferred format is `reviewed_gbp_session_marks_v2`:

| Field | Reviewed evidence |
| --- | --- |
| `basis`, `source`, `reviewed_at` | Schema name above, display source label and UTC review time |
| `calendar_evidence`, `valuation_evidence` | Private references to the reviewed calendar and exact-time GBP total-account valuation source |
| `benchmark_evidence` | Optional private reference to the GBP London VUAG listing (ISIN IE00BFMXXD54), the total-return and corporate-action review and the rights to serve the data or derived results to both members. Required to supply benchmark marks. |
| `sessions` | 2–367 strictly ascending UTC dates. Each row has `date` and `cutoff_at`. An approved GBP NAV requires both `portfolio_value_gbp` and `portfolio_at` exactly at the cutoff. An approved VUAG level requires `vuag_index`, `vuag_at` and the scheduled `vuag_close_at`. The observed close must match the scheduled close and be at or before the ISA cutoff. |
| `holdings` | Optional frozen universe with UTC `as_of`, private `evidence` reference and up to 128 `instruments`. Each has a unique broker `ticker`, positive `weight_pct` of ISA NAV, and `levels` aligned by index to every scheduled session. The holdings evidence covers the snapshot revision, mapping, GBP total-return adjustments, FX and close timing, and applicable use rights. Include unqualified held listings with null marks so coverage stays visible. |

Values and weights are decimal strings. Missing marks are null, including for
any unavailable scheduled session. Keep the session row so adjacent returns
cannot span the gap. Closed-market dates follow the reviewed calendar. Keep
the private source files, excluded dates and operator review with the manifest.
Trading 212 snapshot retrieval times do not qualify as close-price evidence.

Run the offline readiness check on the private manifest before publication:
`cargo run --manifest-path rust/reconciliation/Cargo.toml --locked --bin qualify_daily -- "$(date -u +%FT%TZ)" < /path/to/private/reviewed.json`.
For a funding-aware rehearsal, pass a second argument containing the private
funding JSON path. The local read-only exporter uses the same completed
Trading 212 traversal as History and Risk. Run it from `backend` with the
reviewed opening and closing UTC instants and a separate evidence cutoff:

```sh
python -m meridian.export_session_funding --database /path/to/private/evidence.sqlite3 \
  --start-at UTC_OPEN --end-at UTC_CLOSE --as-of UTC_AS_OF \
  --output /path/to/private/funding.json
```

The file retains events exactly on both boundaries, so ambiguous timing
remains visible to the Rust calculation. Coverage is clipped to the export
window. The exporter creates a new private file, preserves existing files and
prints aggregate counts only. Trusted hosted maintenance can call the same
export function inside a read-only transaction.

The command reports eligible ISA and VUAG returns, rejection counts, each
risk measure's sample and availability, and the shared holdings sample. It
uses the same funding validation and analytics as the Risk tab and writes
only aggregate counts and fixed categories. With no funding file, the check
still exercises holding coverage and leaves ISA returns gated. The operator
reviews source rights, calendar completeness and input provenance before
publication. The local check does not confer source approval. Publish only a reviewed
result through the existing private gateway binding. It accepts raw JSON or a
single `gzip:` base64 value. For larger inputs, set the root binding to
`gzip-parts:N` and split the base64 of one gzip stream into consecutive
`RISK_DAILY_GBP_01` through `RISK_DAILY_GBP_NN` secret values. Use up to 24
parts of at most 5,120 characters each and at most 512 KiB uncompressed.
Prepare and activate the complete set together. Keep all prepared secret data
out of source, assets, and logs.

The Risk tab reports approved ISA performance and its separate matched VUAG
stretch, capture times, net external funding, missing inputs, and holding
correlation with its common-sample coverage. For reviewed NAVs, the gateway
combines the marks with the existing completed funding traversal in Rust.
Observed broker drawdown and History remain available independently.

The Risk response also carries the ongoing automatic series under
`metrics.cutoff_pilot` (the original response key for broker observations)
and `metrics.cutoff_returns`. The existing sync records the first valid GBP
account summary within two minutes of 22:00 UTC on each scheduled date.
The grid follows the [LSE business-day calendar](https://www.londonstockexchange.com/en/resources/markets-products/business-days)
through 2028. Weekday evidence can still be collected after the reviewed
calendar expires, with return eligibility paused until the calendar is
reviewed for those dates. Statuses distinguish scheduled, captured, missed
and unavailable. Each computed return shows the net external GBP funding
amount and event count used in the calculation. The date filter bounds the series. For longer ranges the
table shows up to 75 recent dates. The widest risk range uses at most 252
session intervals.

Rust computes Modified Dietz at the actual capture times for adjacent
scheduled dates with complete funding coverage. Missed captures, unsupported
funding, boundary events with ambiguous ordering, and unreviewed calendar
dates block their intervals. The automatic result is provisional by default.
A completed funding window alone cannot approve the valuation basis.

The optional private gateway binding `RISK_CUTOFF_APPROVAL` accepts a reviewed
policy with `basis: trading212_fixed_cutoff_gbp_v1`, UTC ISO `reviewed_at`,
inclusive `effective_from` and `effective_through` dates, and a private
`evidence` reference. The review must establish the comparability of the
broker account-value convention at the fixed cutoff. When authorised and
installed, the policy admits newly computed intervals inside its effective
dates without manual row publication. Only those intervals enter the separate
automatic ISA risk table, with the same 60-return minimum. The statement
returns and their benchmark sample retain their own basis. The policy and
financial rows are private.

AXIS reads History once on the first signed-in snapshot and shares that
response with the History tab. It presents the most recent contiguous set of
matched ISA and VUAG returns, the eligible drawdown and its cutoff, and the
latest top-five concentration from the normal snapshot. The comparison uses
the unrounded return factors and stops at any missing interval. Figures link
to History, Risk, and Exposures for evidence and precise amounts.

## Authenticated broker refresh — 13 November 2026

| Route | Deployed contract |
| --- | --- |
| `POST /api/v1/portfolio/refresh` | Require active membership, session, exact Origin and bound CSRF token. Return 202 with `status=queued` after persisting a durable alarm in the fixed sync object. |
| `GET /api/v1/portfolio/refresh/status` | Require active membership/session. Return target interval, unknown quote age and approved per-task attempt/success/retry/failure health. Private checkpoints and lease tokens are excluded. |

Gateway routes reject query-selected accounts and request bodies on refresh. Manual and scheduled work share database leases and endpoint reservations. A queued acknowledgement records delivery of a signal. Completion is observed through health and the next published snapshot. Published financial values and their original retrieval times remain available on failure. The current browser transport is authenticated periodic pull. SSE and a general job-ID/progress API remain target capabilities.


### Broker-led discovery projection — 19 November 2026

Approved snapshot rows add nullable `isin`/`instrument_type` and `metadata` with
`state`, opaque `source_id` and `retrieved_at`. Coverage states and fallback rules
are defined in [broker integration](trading212-integration.md#automatic-discoveryenrichment--19-november-2026).
The BFF reads only the approved snapshot, with no new raw-source permission or
browser request. The existing holdings view renders metadata limitations as text.

`holding_changes` carries `basis` (`initial_observation` or
`previous_saved_snapshot`), `added_tickers` and `closed_tickers`. The existing
snapshot-status line displays counts since the preceding saved snapshot. These
are observed position-set changes, not order/fill confirmations, and can age out
of the latest view on the next refresh; immutable evidence/history retains its
existing retention policy. Newly fetched metadata appears in the next successful
snapshot. Old saved snapshots without these fields remain readable.


### Approved Rust cash review — 20 November 2026

`cash_reconciliation` is an optional approved snapshot summary: method,
availability/reason, cash as-of, source snapshot ID, input revision, event/observation
counts, review-state counts, per-currency insufficient-control states, warnings and
coverage. Raw observations, references, amounts, evidence payloads and private scope
are not returned by this projection. The BFF keeps its existing snapshot-only grant.
The private WASM entrypoint is a named service binding, not a public HTTP route.

The existing AXIS view shows a cash-history review panel. Provider signs/openings
are unverified; it explicitly says balances are not reconciled. Failed/unsupported
review leaves broker figures available. Older snapshots/pages remain compatible.
`/health` retains ordinary liveness and adds a fixed synthetic WASM readiness header
(`X-Meridian-Reconciliation`); this reads no financial data and accepts no input.


### Cash review interpretation correction — 20 November 2026

`unverified_sign_review` is a shared cash-sign policy prerequisite, not proof that
each observed event is an individual exception. The panel now separates captured
cash activity from detected record conflicts/unsupported types, and lists missing
opening/sign/trade/dividend coverage separately. It does not imply a reconciled
balance or verified sign convention. Optional `activity_counts` report fixed
provider categories over effective Rust records (not repeated observations);
Python validates their allowed keys, integer counts and sum against event count.
Older summaries without the field remain readable. No amount totals are derived.


## Cash total transactions

Each income/funding total exposes “View transactions” and 20-row next/previous
pages, showing date, issuer/type, exact monetary amount and broker reference.
Collapsed source evidence preserves source ID, selected revision and digest. Only
an explicit click fetches data. The authenticated `POST /api/v1/portfolio/cash-activity`
uses existing cookies, exact Origin and CSRF, bounded 2 KiB JSON and no query string.
Both existing members have equal access. Detail responses are no-store; stale or
missing generations return 409 with a reload instruction. Late responses cannot
repopulate after signout or snapshot replacement. Coverage shows completed broker
traversals/earliest captured dates and explicitly limits claims to available broker
history. Old saved summaries retain their existing totals without fake detail rows.

## Portfolio Changes

`GET /api/v1/portfolio/changes?start=YYYY-MM-DD&end=YYYY-MM-DD` requires an
approved member session and ordered UTC dates through today. It returns
`observed_portfolio_changes_v1` with two endpoint statuses, snapshot IDs,
capture and observation times, valid weight denominators and comparison rows.
The private session owner reads two account-scoped approved projections using
the History date selection rule and checks their digests. The gateway computes
the public report in Rust WASM and serves it with `Cache-Control: no-store`.
A date with no usable input returns `missing` or `unavailable` in the report.
Neither date selection nor comparison fetches new broker data.

The Portfolio Changes tab defaults to the last two observed dates in the
loaded History when available. Choose different UTC dates to compare other
retained anchors. Expand a holding for dated source evidence, or expand an
allocation or concentration row and follow its links to the compared holdings.
Holdings are ordered from largest reported GBP gain to largest loss. The
sector comparison uses the same broad categories as Exposures.
The chart overview shows reported ISA values, holding counts by direction,
the largest holding changes in GBP, and the largest sector weight changes in
percentage points. Select a bar row to open its detailed evidence.

## AI portfolio export

Holdings includes a **Download AI brief** action. The same-origin route
`GET /api/v1/portfolio/export` returns versioned JSON. With exactly
`?format=markdown` it returns a dated Markdown attachment. Both use the live
ISA membership check, private/no-store headers and the same pinned source.
The gateway sends one authorised request to the private session owner and
keeps the financial inputs in the request. Files are generated on demand.

The comparison targets one calendar month before the latest saved UTC
observation, clamped at month end. If that day has no saved capture, the
selector uses the nearest earlier capture within seven days. The target and
actual dates, offset, observation IDs and separate retrieval times are
reported. An invalid selected baseline remains unavailable. A missing or
invalid baseline preserves current holdings and leaves changes unavailable.
An absent current snapshot returns 404 and an integrity or service failure
returns a safe 503.

The export reuses observed Portfolio Changes for holdings, cash, concentration
and comparable allocation deltas. It includes broker value, cost, P&L,
current weights, exposure coverage and source attribution. The export adapter
uses fixed-scale exact integer arithmetic for presentation-only deltas and
P&L-to-cost ratios. The Meridian section reuses the 90-session Rust report
with the pinned holdings and includes matched bounds, exclusions, capital
and variance shares, clusters and strongest positive peers. A missing sample
or unavailable risk calculation preserves the rest of the response. Markdown
cells are escaped and the browser drops late downloads after sign-out.

The format covers saved observations and summaries. Trade sizing scenarios,
reconciled monthly transaction attribution, constituent-level overlap and
external research inputs are follow-on work.
