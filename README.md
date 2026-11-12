# Great Dyke Meridian

Great Dyke Meridian is a private portfolio monitoring app in development. **AXIS** is its main dashboard. Two people have separate logins with equal full editing rights for one owner's Trading 212 Stocks and Shares ISA.

The hosted target is Cloudflare + Supabase PostgreSQL, with React, Vite, Tailwind CSS and ECharts. Python/FastAPI/SQLAlchemy remain the preferred backend where free-runtime feasibility checks pass. SQLite supports the verified local evidence tooling. Trading 212 is the primary broker-data source; CSV exports provide fallback and missing grouping metadata. A separate market-data adapter supplies prices and FX; yfinance compatibility still needs hosting verification.

## Current status

**Development resumed at the owner's request on 12 November 2026.** Continue from [status and handoff](docs/status-and-handoff.md). Stage 0H hosting qualification is the current gate; direct Cloudflare and Supabase management access is established.

**Local foundation, broker adapter and snapshot-evidence slices are verified.** Exact-decimal persistence, migrations, evidence/audit records, isolated configuration, backup/restore and holdings CSV preview/atomic import are available. The broker adapter is tested with mocked HTTP. The app exposes liveness only; there is no usable portfolio UI or hosted application yet. Full Stage 1 financial replay and reconciliation remain open.

Start with the tested [local development guide](docs/local-development.md). The required provider YAML is verified; see [source contracts](docs/stage-0-source-verification.md) for account-history limitations.

PostgreSQL foundation parity also passes disposable service-backed CI. This verifies migrations and evidence constraints, not a hosted Supabase login or deployment. The [status and handoff](docs/status-and-handoff.md) distinguishes completed slices from the remaining financial and hosting gates.

The empty Supabase evidence schema has deployed through the native GitHub integration and was confirmed in Table Editor. Synthetic Cloudflare controls are deployed and measured: ordinary Python HTTP exceeds the documented Free CPU budget for the probe; a thin gateway to a Python Durable Object passed synthetic checks and is the next qualification candidate. Database/Auth/capacity/recovery remain open. No real portfolio data, app logins or finished financial interface have been deployed.

The planning baseline was established on **11 November 2026** from the owner's requirements, a read-only review of the Excel tracker, and official provider documentation. The workbook's latest recorded snapshot is **11 October 2026**, not a current account valuation.

## Start here

- [Documentation index](docs/README.md): reading routes and document ownership.
- [Product requirements](docs/product-requirements.md): scope, requirement IDs and revisions to the original brief.
- [Architecture](docs/architecture.md): component boundaries and data flow.
- [Development stages](docs/development-stages.md): dependency order and acceptance gates.
- [Status and next handoff](docs/status-and-handoff.md): actual progress and the next bounded task.
- [Agent instructions](AGENTS.md): repository rules and coordination for human and agent contributors.

## Product boundaries

- One Trading 212 Stocks and Shares ISA; two equally authorised, individually authenticated users. No role hierarchy or separate portfolios in the initial scope.
- Portfolio planning target: £100,000 by 2030; retain 30 April 2030 from the original brief unless explicitly revised.
- Cloudflare + Supabase is the approved free hosting target. Runtime, PostgreSQL, authentication and storage qualification now happen early; no real data is exposed before security/recovery acceptance. See [the hosting decision](docs/decisions/0001-cloudflare-supabase.md).
- Broker integration is read-only: no placing, changing or cancelling orders.
- Groups are labels on holdings, derived from verified CSV group context and reviewed assignments. In the inspected export, Slice is the holding ticker and the Total row's Name supplies group context. There are no broker-pie objects, pie targets or pie projections in the app.
- GBP is the reporting currency. Imported facts, estimated values and calculated results remain distinguishable.
- Intraday monitoring is separate from daily risk and correlation inputs. The tax engine is deferred from the initial release; management cost/PnL remain supported.
- Missing data produces an explicit limitation. It never becomes a fabricated zero, return, tax result or exposure estimate.

The reviewed Trading 212 position/history schemas do not expose the CSV's raw Slice label. The reviewed API also has no dedicated general quote, historical-close or FX feed. CSV grouping evidence and a separate market-data adapter therefore remain necessary. One [holdings CSV format](docs/csv-contract.md) is now verified; transaction-history formats and CSV/API event matching still need inspection. The snapshot cannot supply missing execution history.

## Delivery order

Begin with Stage 0 in the [development plan](docs/development-stages.md). In particular, establish actual historical coverage and cross-source identities, then resolve decisions that affect the first implementation task. Do not assume that every open decision blocks all progress.

This GitHub repository is public; the running app and portfolio data remain private. Real balances, position sizes, contribution amounts, source files, private notes, credentials, databases and backups must not be published. Documentation preserves methods and synthetic examples. Ignore rules protect local runtime inputs, but tracked/publication content must still be reviewed.

## Keeping this useful

Update the relevant contract when behaviour changes and update the status document when work is verified. Keep the README short. Detailed definitions belong in the linked documents, with one authoritative home per topic.
