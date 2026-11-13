# Development plan and stage gates

Status, **13 November 2026:** this document defines the delivery roadmap and acceptance gates. [Current status](status-and-handoff.md) owns completed slices and the latest owner scope. Secure two-user broker views and minute refresh are deployed. Stage 1 evidence/import slices and parts of Stage 2 are verified. Full economic replay, daily market inputs, analytics and final operational acceptance remain open. Stage 0H retains unresolved capacity and workload gates.

## Delivery discipline

Deliver one reviewable vertical capability at a time. Complete offline tests, reconciliation, operational instructions and affected documentation before declaring a stage verified. Do not build nine placeholder tabs as evidence that nine financial capabilities are done.

Original stages mixed prerequisites: holdings value before prices, imports before audit, authentication after the UI, and many undefined metrics in one large stage. The revised sequence moves foundations earlier while retaining the requested scope. Hosted feasibility now precedes further production work; Stage 6 performs the final private hosted release and restore acceptance.

For every stage, deliver actual code/file tree when authorised, migration implications, tested run commands, fixture/test evidence, assumptions/limitations, requirement IDs and a next handoff. Only record code/test deliverables that exist and have been checked.

## Stage 0 — verify sources and settle foundational contracts

**Outcome:** a new contributor can parse an event and explain its authority without guessing.

**Entry:** owner requirements, this documentation set and permission to inspect relevant local sources.

**Tasks:**

1. Obtain/verify OpenAPI YAML, date/hash it, compare relevant endpoints/schemas with the reviewed JSON. Document the request allowlist and adapter contracts.
2. Inspect actual CSV types and sample rows. Identify Slice meaning, grouping context, Total controls, IDs, fees, dividend fields and date/currency/number formats.
3. Confirm actual account wrapper/currency, historical coverage, excluded accounts, transfers and supported opening evidence (Q01–Q03).
4. Establish cross-source aliases for fills, dividend and cash references using real but private comparisons; create sanitised/synthetic equivalent fixtures.
5. Preserve workbook baseline/hash and six snapshot expectations. Resolve only the observation-date issues that the import task needs; preserve ambiguous labels when unresolved.
6. Decide foundational identity/precision and the first bounded Stage 1 task. Log decisions and remaining questions.

**Exit evidence:** field-coverage matrix, verified schema source, example normalised records, expected dedupe/reconciliation outcomes, privacy/ignore plan and explicit input completeness. No guess that the API supplies all history or grouping.

**Blocks:** missing real exports blocks a production-ready CSV contract, not drafting pure ledger interfaces. Unresolved scenario/RAG thresholds do not block schema/import work.

## Stage 0H — qualify Cloudflare + Supabase

**Outcome:** a measured, private production path that preserves the financial contracts within free-service limits.

**Entry:** owner-approved platform change; synthetic inputs. Dedicated free projects are authorised, with account sign-in handled by the owner. No reuse of unrelated application projects.

**Tasks:** Python Workers dependency/build and hosted CPU/startup/memory checks; Supabase Postgres migrations/precision/import atomicity; approved two-member Auth/session/RLS/grant boundaries; bounded scheduled jobs with durable leases/fencing/rate budgets; one representative daily-risk/correlation workload; 90-day lossless quote retention capacity including indexes/evidence; private backup/export/restore (hosted export and isolated local restore qualified; full hosted recovery remains open); same-origin HTTPS and streaming reconnect. Preserve SSE preference unless an explicit engineering transport decision qualifies private Realtime.

**Exit evidence:** reproducible local and hosted probe results, authenticated nonmember/anonymous denials, measured budgets, accepted migration/restore evidence, account/project identity and rollback. A local bundle build does not prove free CPU fit or production readiness. Supabase RLS-enabled tables without member policies are a safe closed foundation, not completed authorization. No paid resources or trial-only dependencies.

If a runtime cannot meet scope, record the measured limitation and propose the smallest alternative. Do not silently rewrite Python, reduce requested 60-second polling/90-day retention, or bypass a provider quota. Lossless private archival can preserve retention if it is verified before pruning the hot database.

## Stage 1 — durable evidence, ledger and safe import

**Progress:** foundation, broker observations, durable history revisions, holdings CSV evidence and Excel baseline evidence are implemented. Hosted parity `0007` is verified. Full Stage 1 remains open for economic replay, verified cross-source aliases, corporate-action economics and group workflows. See [current status](status-and-handoff.md).

**Outcome:** accepted source data survives restart, replay is deterministic, and repeated imports do not change economics.

**Entry:** relevant Stage 0 contracts verified; implementation requested.

**Slices:**

- **1A:** project manifests/locked dependencies, configuration validation, test harness, SQLAlchemy/Alembic, Decimal storage, account/environment identity, source records, import/audit and initial backup/restore. Local SQLite evidence is implemented; Supabase Postgres parity, grants/RLS and independent restore require hosted qualification.
- **1B:** normalised events/cash ledger, corporate-action eligibility, holdings quantities/opening records, fill/reference dedupe and cross-source aliases. Mocked broker HTTP adapter with pagination, rate handling and checkpoints.
- **1C:** CSV dry-run/atomic import, Excel baseline import, group evidence/mapping/conflicts, rename/merge/reassignment service and manual override persistence.

**Exit evidence:** successful fresh migration and previous-schema upgrade test; failure rollback leaves no financial residue; failed attempt logged; identical accepted hash rejected; overlapping API/CSV orders do not double count; partial fills handled; all six Excel values/invested snapshots match within £0.01; source notes/coverage preserved; totals excluded; group conflicts visible; backup restores controls.

Quantity and recorded snapshot allocation can be reconciled here. Do not claim fully current market-value allocation before Stage 2 price/FX selection. Do not call a broker average cost a complete Section 104 result.

## Stage 2 — secure daily valuation and minimal useful dashboard

**12 November owner clarification:** the initial financial snapshot uses Trading 212 reported account and position figures directly. Full ledger reconciliation is not a gate for this sourced snapshot; derived valuations/performance/analytics retain separate input/method requirements. Hosted evidence acceptance, authenticated snapshot access/UI and bounded refresh are now verified. Derived valuation and performance keep their own input gates.

**Outcome:** both logins can inspect a trustworthy portfolio snapshot with clear source quality.

**Entry:** accepted account-bound evidence and secure membership access support the broker-reported snapshot. Calculated valuations additionally require supported quantities/cash, price/FX inputs and their reconciliation controls.

**Slices:**

- **2A:** same-origin HTTPS, two approved Supabase Auth identities, secure session/CSRF and explicit portfolio membership, equal full-editor permissions, audited mutations and exact dev/prod origins. Reject unrelated authenticated users as well as anonymous requests. No financial API exposed without login.

  Secure login/session access and approved snapshot/refresh routes are deployed for both identities. Native parity is `0007`. Actual HTTPS access/denial checks and the owner's browser sign-in are recorded in current status. Partner browser confirmation and remaining browser/operational checks are open.
- **2B:** mapping UI/service, market-data adapter, explicit adjusted/unadjusted bases, daily price/FX cache, approved selections, ledger/broker reconciliation, GBP NAV and holding/group weights.
- **2C:** minimal AXIS/HOLDINGS/GROUPS and source-history views; no invented return/risk cards. One scheduled-job authority, shared manual-job leases, durable backfill/checkpoints and job progress. No persistent in-process scheduler on Workers.
- **2D:** basic quote monitoring with requested 60-second interval/capability disclosure, session calendars, stored observations, last-good/freshness, polling operation logs and authenticated SSE. End-session candidate remains provisional. Final alert/retention refinements are Stage 5.

**Exit evidence:** both logins work; insecure/missing session/CSRF rejected; no secrets reach UI/logs; prices/FX convert accurately including pence; NAV decomposes; weights use NAV; missing price cannot improve a total; daily close selection isolated from intraday; duplicate jobs prevented; calendar/half-day/backoff tests pass; provider/network optional tests separately marked; real broker reconciliation differences explained.

**Milestone:** useful daily tracker. If provider capability prevents the requested intraday freshness, expose and record it; do not claim real-time monitoring.

## Stage 3 — financial history and portfolio projections

**Outcome:** supported performance and portfolio projections are explainable from dated inputs. The tax engine is explicitly deferred.

**Entry:** stable valuation contract, coverage metadata, remaining Q05/Q06 timing decisions resolved for the behaviour being delivered.

**Slices:**

- **3A:** cash-flow boundary, exact TWR where possible, labelled Modified Dietz fallback, daily/MTD/YTD/since-inception, wealth index and historical snapshots with source precedence.
- **3B:** portfolio scenario projection with dated contribution schedule; legacy 44-month Excel fixture and zero-rate/beginning/end-period cases; distinguish target from forecast.
- **3C is deferred:** the owner has removed the tax engine from the initial release. Do not build tax schemas, matching, allowances or tax summaries as Stage 3 prerequisites.

**Exit evidence:** deposits do not count as investment gains; known flow examples pass; incomplete history suppresses unsupported results; all legacy FV values reconcile; £100,000 active goal with the retained 30 April 2030 date and chosen contribution timing documented; no initial tax dependency; ordinary management PnL is not labelled HMRC gains.

Performance and projection slices can be assigned separately after shared contracts freeze. The owner explicitly confirmed one ISA and deferred tax; this is a scope decision, not an inference from a source label or account balance.

## Stage 4 — daily risk and correlation

**Outcome:** the key correlation module and risk summary have traceable inputs and sensible failure behaviour.

**Entry:** approved daily GBP return series and sufficient eligible fixtures/history. Q12/Q13 sampling choices settled for shipping paths.

**Slices:** risk ratios/drawdown/VaR/ES/CAPM; concentration/currency evidence; common-sample correlation and weekly mode; group indices/benchmarks; shrinkage/clustering/rolling pairs; diversification/effective bets and quality metadata.

**Exit evidence:** known synthetic correlations; PSD/symmetry/bounds including singular cases; insufficient overlap flagged; all group members accounted for; raw/shrunk comparison same sample; 30-day view cannot silently satisfy 60-day minimum; intraday rejected as risk input; risk edge cases unavailable rather than zero; CAPM n/R² and effective-dated RF correct; look-through fixture provided or explicit uncovered state; workbook ~19% assertion never hardcoded.

**Milestone:** dependable monitoring plus requested central analytics. No alerts from unreliable short samples.

## Stage 5 — complete application and operational acceptance

**Outcome:** all nine tabs and supported requested capabilities are usable, with a tested recovery path.

**Entry:** prior financial contracts verified; Q08 re-arming/drawdown thresholds confirmed; Q09–Q11 resolved only for their corresponding features.

**Slices:** remaining screens/detail views; thesis notes; durable alerts/re-arm; intraday alert basis and daily-close discrepancy review; historical attribution/currency interaction; defined trading statistics; stress scenarios; settings; measured retention/archival; mature Postgres/evidence backup/restore and reproducible development/deployment instructions.

**Exit evidence:** nine tabs satisfy the UI contract; values reconcile between summary/detail; alert state survives restart and does not spam; unsupported attribution/overlap states explained; scenario shocks deterministic and not doubled; SSE recovers after a missed delta for both users; retention preserves closing/alert provenance; upgrade and restore drill pass; launch/shutdown instructions verified; actual limitations listed against requirements.

**Acceptance rule:** initial-release capabilities cannot disappear into vague future work. T01/T02 and tax summaries are explicitly owner-deferred. Either implement the supported scope or obtain an explicit owner scope decision for a documented limitation/deferment. A skeleton tab does not satisfy a calculation requirement.

## Stage 6 — private hosted release

**Entry:** owner-authorised Cloudflare/Supabase free projects, Stage 0H qualification, application acceptance and operational restore evidence.

Deploy pinned Cloudflare assets/API and reviewed Supabase migrations only into dedicated projects. Verify two intended identities, anonymous/nonmember denial, HTTPS/session/CSRF, streaming, secrets, DB/Storage/Realtime policies, scheduler leases/backoff/recovery, measured free limits, private off-host backup and rollback. Conduct a restore into an isolated destination and verify financial controls before selecting it. Keep broker integration read-only. Public portfolio data is not a requirement. VM/Tailscale options are historical alternatives, not the selected target.

## Completion checklist per slice

Contract and requirement IDs → bounded implementation → meaningful offline checks → integration/reconciliation → documentation/status update → handoff with exact commands, results and remaining risks. Broaden testing only for real integration risk or changed behaviour. Do not start the next stage to avoid resolving a failed gate.

## Optional later phase — tax engine

Implement T01/T02 only after a later owner request or genuinely expanded taxable-account scope. Reuse the deferred [tax contract](tax.md) and its worked tests; reverify relevant rules then. This is not triggered when ISA market value reaches £20,000. The annual ISA subscription allowance and portfolio market value are different measures. Initial local-release gates do not require tax matching, tables or allowance screens.
