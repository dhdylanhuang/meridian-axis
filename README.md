# Great Dyke Meridian

Great Dyke Meridian is a planned private portfolio monitoring app. **AXIS** is its main dashboard. Two people have separate logins with equal full editing rights for one owner's Trading 212 Stocks and Shares ISA.

The intended stack is Python 3.11+, FastAPI, SQLAlchemy, SQLite, React, Vite, Tailwind CSS and ECharts. Trading 212 is the primary broker-data source; CSV exports provide fallback and missing grouping metadata. Market prices and FX use a separate provider adapter, initially yfinance.

## Current status

**Documentation only. No application, database, broker client, authentication, scheduler or automated tests have been implemented.** The specifications describe intended behaviour, not existing features. There are no application setup or run commands yet.

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
- Localhost first. Remote access is a later, separately authorised stage.
- Broker integration is read-only: no placing, changing or cancelling orders.
- Groups are labels on holdings, derived from verified CSV group context and reviewed assignments. In the inspected export, Slice is the holding ticker and the Total row's Name supplies group context. There are no broker-pie objects, pie targets or pie projections in the app.
- GBP is the reporting currency. Imported facts, estimated values and calculated results remain distinguishable.
- Intraday monitoring is separate from daily risk and correlation inputs. The tax engine is deferred from the initial release; management cost/PnL remain supported.
- Missing data produces an explicit limitation. It never becomes a fabricated zero, return, tax result or exposure estimate.

The reviewed Trading 212 position/history schemas do not expose the CSV's raw Slice label. The reviewed API also has no dedicated general quote, historical-close or FX feed. CSV grouping evidence and a separate market-data adapter therefore remain necessary. One [holdings CSV format](docs/csv-contract.md) is now verified; transaction-history formats and CSV/API event matching still need inspection. The snapshot cannot supply missing execution history.

## Before implementation

Begin with Stage 0 in the [development plan](docs/development-stages.md). In particular, inspect real CSV schemas, verify the Trading 212 OpenAPI YAML, establish historical coverage and resolve decisions that affect the first implementation task. Do not assume that every open decision blocks all progress.

This GitHub repository is public; the running app and portfolio data remain private. Real balances, position sizes, contribution amounts, source files, private notes, credentials, databases and backups must not be published. Documentation preserves methods and synthetic examples. Ignore rules protect local runtime inputs, but tracked/publication content must still be reviewed.

## Keeping this useful

Update the relevant contract when behaviour changes and update the status document when work is verified. Keep the README short. Detailed definitions belong in the linked documents, with one authoritative home per topic.
