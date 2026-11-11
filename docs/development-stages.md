# Development plan and stage gates

Status: ADOPTED dependency order. All implementation stages are **not started**. Stage 0 documentation exists, but its source-verification gate is still incomplete. This plan is not authorisation to begin code or commit.

## Delivery discipline

Deliver one reviewable vertical capability at a time. Complete offline tests, reconciliation, operational instructions and affected documentation before declaring a stage verified. Do not build nine placeholder tabs as evidence that nine financial capabilities are done.

Original stages mixed prerequisites: holdings value before prices, imports before audit, authentication after the UI, and many undefined metrics in one large stage. The revised sequence moves foundations earlier while retaining the requested scope. Stage 6 remains later remote access.

For every stage, deliver actual code/file tree when authorised, migration implications, tested run commands, fixture/test evidence, assumptions/limitations, requirement IDs and a next handoff. During this documentation task, do not create fictional code/test deliverables.

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

## Stage 1 — durable evidence, ledger and safe import

**Outcome:** accepted source data survives restart, replay is deterministic, and repeated imports do not change economics.

**Entry:** relevant Stage 0 contracts verified; implementation requested.

**Slices:**

- **1A:** project manifests/locked dependencies, configuration validation, test harness, SQLAlchemy/Alembic, Decimal storage, account/environment identity, source records, import/audit and initial backup/restore.
- **1B:** normalised events/cash ledger, corporate-action eligibility, holdings quantities/opening records, fill/reference dedupe and cross-source aliases. Mocked broker HTTP adapter with pagination, rate handling and checkpoints.
- **1C:** CSV dry-run/atomic import, Excel baseline import, group evidence/mapping/conflicts, rename/merge/reassignment service and manual override persistence.

**Exit evidence:** successful fresh migration and previous-schema upgrade test; failure rollback leaves no financial residue; failed attempt logged; identical accepted hash rejected; overlapping API/CSV orders do not double count; partial fills handled; all six Excel values/invested snapshots match within £0.01; source notes/coverage preserved; totals excluded; group conflicts visible; backup restores controls.

Quantity and recorded snapshot allocation can be reconciled here. Do not claim fully current market-value allocation before Stage 2 price/FX selection. Do not call a broker average cost a complete Section 104 result.

## Stage 2 — secure daily valuation and minimal useful dashboard

**Outcome:** both logins can inspect a trustworthy portfolio snapshot with clear source quality.

**Entry:** evidence/import gate, supported quantities/cash and restored schema.

**Slices:**

- **2A:** local HTTPS, two-user bootstrap, password/session/CSRF, equal full-editor permissions (Q04 resolved), audit and exact-origin dev/prod configuration. No financial API exposed without login.
- **2B:** mapping UI/service, market-data adapter, explicit adjusted/unadjusted bases, daily price/FX cache, approved selections, ledger/broker reconciliation, GBP NAV and holding/group weights.
- **2C:** minimal AXIS/HOLDINGS/GROUPS and source-history views; no invented return/risk cards. One scheduler owner, manual jobs, startup daily backfill and job progress.
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

## Stage 5 — complete local application and operational acceptance

**Outcome:** all nine tabs and supported requested capabilities are usable, with a tested recovery path.

**Entry:** prior financial contracts verified; Q08 re-arming/drawdown thresholds confirmed; Q09–Q11 resolved only for their corresponding features.

**Slices:** remaining screens/detail views; thesis notes; durable alerts/re-arm; intraday alert basis and daily-close discrepancy review; historical attribution/currency interaction; defined trading statistics; stress scenarios; settings; retention; mature backup/restore and Windows fresh-install instructions.

**Exit evidence:** nine tabs satisfy the UI contract; values reconcile between summary/detail; alert state survives restart and does not spam; unsupported attribution/overlap states explained; scenario shocks deterministic and not doubled; SSE recovers after a missed delta for both users; retention preserves closing/alert provenance; upgrade and restore drill pass; launch/shutdown instructions verified; actual limitations listed against requirements.

**Acceptance rule:** initial-release capabilities cannot disappear into vague future work. T01/T02 and tax summaries are explicitly owner-deferred. Either implement the supported scope or obtain an explicit owner scope decision for a documented limitation/deferment. A skeleton tab does not satisfy a calculation requirement.

## Stage 6 — remote access, later

**Entry:** explicit owner request, local acceptance and operational restore evidence.

Compare Tailscale versus Cloudflare Tunnel/Access, document the selected access boundary and deploy only after authorisation. Verify intended identities, HTTPS/session/CSRF, SSE, secrets, host storage, backup and rollback. Keep broker integration read-only. Public portfolio access is not a requirement.

## Completion checklist per slice

Contract and requirement IDs → bounded implementation → meaningful offline checks → integration/reconciliation → documentation/status update → handoff with exact commands, results and remaining risks. Broaden testing only for real integration risk or changed behaviour. Do not start the next stage to avoid resolving a failed gate.

## Optional later phase — tax engine

Implement T01/T02 only after a later owner request or genuinely expanded taxable-account scope. Reuse the deferred [tax contract](tax.md) and its worked tests; reverify relevant rules then. This is not triggered when ISA market value reaches £20,000. The annual ISA subscription allowance and portfolio market value are different measures. Initial local-release gates do not require tax matching, tables or allowance screens.
