# Decisions and open questions

Baseline: 11 November 2026. This register distinguishes explicit owner requirements from engineering choices. Implementation was subsequently authorised; actual completion evidence is tracked separately.

## Confirmed decisions

| ID | Decision | Origin |
| --- | --- | --- |
| DC01 | Great Dyke Meridian; AXIS summary; private monitoring app | Original brief |
| DC02 | Two separate logins, one owner's portfolio | Explicit owner clarification |
| DC03 | Local first; private hosting required after security/recovery gates; free services only | Original brief, superseded hosting/budget clarification |
| DC04 | Fixed Python/FastAPI/SQLAlchemy/SQLite and React/Vite/Tailwind stack; ECharts preferred | Original brief |
| DC05 | GBP reporting, source/FX provenance, offline calculation tests | Original brief |
| DC06 | Groups from export context; inspected Slice=ticker, Total-row Name=group; reviewed assignments; no pie objects/targets/projections/RAG | Original intent corrected by CSV evidence |
| DC07 | Trading 212 API v0 primary; CSV fallback/enrichment; verify YAML; Demo default; explicit Live | Later owner amendment |
| DC08 | Broker integration read-only; env key/secret using Basic | Later owner amendment |
| DC09 | Requested 60-second session-aware polling, 90-day intraday retention, SSE preferred, last-good preservation | Later owner amendment |
| DC10 | Risk/correlation use daily data; live monitoring has separate basis and source honesty | Later amendment, with cost-basis wording corrected below |
| DC11 | Execute the plan with orchestrated subagents; commit and push each verified stage | Latest owner instruction supersedes the earlier documentation-only restriction |
| DC12 | One Trading 212 Stocks and Shares ISA; both logins have equal full editing rights | Explicit owner answers |
| DC13 | £100,000 target by 2030; retain original 30 April 2030 date unless revised | Owner target clarification |
| DC14 | Tax engine and tax summaries deferred from initial release | Explicit owner scope reduction; no balance trigger |
| DC15 | Re-arm alerts after recovery | Explicit owner answer |
| DC16 | Any group drawdown >=10%; portfolio largest peak-to-trough fall >=2% within two trading days | Owner answer plus follow-up selection |
| DC17 | July observation date unknown; preserve uncertainty | Explicit owner answer |
| DC18 | GitHub public; actual financial data/source files stay local, examples synthetic | Owner visibility statement; conservative publication policy |

## Adopted engineering decisions

These are architect choices made for a coherent, minimal implementation plan. They can change through an evidence-based decision record without pretending the owner previously selected them.

| ID | Choice | Rationale / authoritative home |
| --- | --- | --- |
| DE01 | Modular monolith, single scheduler owner, separate environment DBs | Small local app; architecture |
| DE02 | Pure financial modules and narrow broker/market adapters | Calculations remain provider-independent; architecture |
| DE03 | Separate source evidence, normalised economics and rebuildable results | Avoid duplicate imports and hidden rewrites; data model |
| DE04 | Immutable labels plus effective membership/overrides | Renames and syncs preserve provenance; imports |
| DE05 | Total controls excluded; no Total instrument/Unassigned balance | Prevent double counting; imports |
| DE06 | Broker snapshot reconciles with ledger, never added to it | Position quantity integrity; imports |
| DE07 | Precise Decimal ledger with canonical text persistence | Avoid SQLite numeric coercion; data model |
| DE08 | Exact TWR only with requisite valuations; timed Modified Dietz fallback labelled | Honest return claims; calculations |
| DE09 | Tax cost uses executions/transaction FX, never closes | Correct cost input semantics; tax |
| DE10 | Last poll provisional; same-session daily source supersedes by revision | Protect risk series; polling |
| DE11 | Full matrix uses one common sample; pair-specific views labelled separately | PSD and diagnostic consistency; correlation |
| DE12 | Group constant-weight series combines simple returns before log | Avoid weighted-log error; correlation |
| DE13 | Global clustering uses annotations; group-order mode draws boundaries | Clusters can interleave groups; correlation |
| DE14 | Participation-ratio effective bets; raw/shrunk estimator explicit | Reproducible diagnostics; correlation |
| DE15 | Security/audit/migrations/backup start before usable real-data UI | Retrofitting loses evidence; stages |
| DE16 | Same-origin local HTTPS, Secure sessions, Argon2id | Meet local security requirements; security |
| DE17 | Polling cycles retained in typed import_log and filtered separately | Preserve requested logging without drowning imports; polling |
| DE18 | Legacy workbook facts retained, known defects excluded from active calculations | Reconcile without institutionalising errors; workbook |
| DE19 | Historical attribution uses effective membership; current exposure uses current groups | Prevent unlabelled historical restatement; data model |

## Open decisions and source gaps

Resolve when a task depends on them, not as a pretext to stop all work. Do not repeatedly ask the same answered question. Record the answer, date, source and affected contracts when resolved.

| ID | Question / evidence needed | Proposed handling meanwhile | Blocks |
| --- | --- | --- | --- |
| Q01 | One ISA confirmed; GBP primary currency confirmed; connected identity and history still need source verification | Verify connected identity/coverage; owner supplied annual/activity PDF statements for read-only inspection; do not re-ask account scope | Full replay/since-inception claims |
| Q02 | Snapshot and three PDF structures verified; complete execution-history export/API aliases remain unverified | Slice=ticker, Total-row Name=group; see CSV contract | Transaction CSV parser and event dedupe |
| Q03 | Opening cash/holdings and complete earlier acquisitions remain unestablished after three PDF inspections; account-boundary transfers/corporate actions still need reconciliation. | Show current observed positions with explicit historical limits | Complete NAV replay, cost basis and since-inception results |
| Q05 | £100,000 goal settled; original 30 April date retained; timing/partial periods and scenario rates remain | Legacy model separate; actual contributions private | Final scenario output |
| Q06 | How should date-only cash flows be timed; which actual valuations exist around intraday flows? | No exact TWR claim; use timed Dietz when supported | Return paths with unknown flow timing |
| Q09 | What financial condition should holding RAG measure, with which thresholds? | No invented score or recommendation | RAG output |
| Q10 | Which trade-episode/holding-period definition and multi-period/market-residual attribution method? | Start with reconciled PnL amounts and explicit FX interaction | Trade statistics and final attribution percentages |
| Q11 | Which holdings/shock define tech sell-off; direct-shock versus beta market scenario? | Explicitly configured target set and deterministic shocks | Named stress presets |
| Q12 | Weekly reliability minimum and desired short-horizon descriptive display? | Propose 20 weekly observations; daily minimum remains 60 | Final weekly/reliability controls |
| Q13 | Calendar source/coverage, portfolio valuation cutoff and cross-market time convention? | Cache sourced schedules, store session dates and ages | Production cross-market daily alignment |
| Q14 | Which provider can actually supply required intraday benchmark/FX freshness and its timestamps/delay? | Capability disclosure; no real-time promise | Guaranteed polling expectations, not scheduler skeleton |
| Q15 | What dated data/definition supports VNRG/VUAG overlap, revenue currencies and broader look-through? | Explicit unavailable/coverage; do not hardcode 19% | Evidence-based detailed exposure results |

## Resolution process

Owner-preference decisions require the owner's answer before dependent behaviour is treated as confirmed. Routine engineering choices can be made within authorised scope with rationale and tests. Source gaps are resolved by inspecting actual data/primary documentation, not asking the owner to guess a schema. Do independent useful work while a question remains pending.

Use the [decision template](templates/decision-record.md) if a choice changes shared interfaces, financial meaning, persistence or deployment. Record supersession rather than silently rewriting a past decision. Update the requirement matrix, tests and status when the change affects them.

## Resolved question IDs

| ID | Resolution |
| --- | --- |
| Q04 | Both logins have full editing rights; one permission level, separate sessions/audit identities. |
| Q07 | Tax engine deferred. ISA allowance is not a portfolio-value limit; no balance-triggered activation. |
| Q08 | Re-arm after recovery; group >=10% running drawdown; portfolio >=2% largest peak-to-trough fall within two trading days. Optional hysteresis defaults to zero. |
| Q16 | July date unknown. Preserve label/uncertainty, invent no date and do not ask repeatedly. Dividend coverage remains qualified. |

These drawdown rules do not define holding RAG (Q09) or tech stress (Q11). Resolve remaining questions at their dependent stage; no answer requires publishing personal source data.

## Implementation authorisation and hosting clarification

On 11 November 2026 the owner authorised implementation, delegated agents and stage commits/pushes. The owner requires free hosting services only and confirmed GBP account currency. Hosting remains behind security/recovery acceptance, with a researched [free-hosting comparison](hosting-options.md); no host is selected or deployed. Statement PDFs have been supplied for private inspection; coverage and machine-readable history contracts remain to be established. Routine engineering decisions remain delegated to the orchestrator.
