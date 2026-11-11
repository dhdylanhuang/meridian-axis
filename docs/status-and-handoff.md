# Status and handoff

Last reviewed: **11 November 2026**, including implementation/delegation authorisation, direct provider verification and the free-hosting constraint.

## Actual state

| Area | State | Evidence / limits |
| --- | --- | --- |
| Repository | Public GitHub; implementation underway | Documentation baseline published; foundations in progress, not a usable tracker |
| Account and access | Confirmed | One Trading 212 Stocks and Shares ISA; two logins with equal full editing rights |
| Goal | Confirmed | £100,000 by 2030; original 30 April 2030 target date retained |
| Tax engine | Deferred | Explicit owner decision; no initial tax schemas/screens/matching required |
| Alerts | Confirmed | Group >=10% running drawdown; portfolio >=2% largest peak-to-trough drawdown within two trading days; re-arm after recovery |
| Excel review | Verified read-only | Structure/methods/defects in public-safe workbook baseline; actual amounts and provenance stay local |
| July date | Known unknown | Owner cannot establish actual observation date; preserve source label and uncertainty |
| Holdings CSV | Verified read-only | Slice=ticker; Total-row Name=group; no execution IDs/dates/currency; see CSV contract |
| Historical source evidence | Three PDFs inspected read-only | Activity trades plus annual/cash controls; opening acquisitions/aliases remain incomplete; [statement contract](statement-source-contract.md) |
| Provider adapter | Stage 1B adapter portion verified | Seven typed GET methods, 39 mocked HTTP tests; no persisted sync or economic booking |
| OpenAPI YAML | Verified directly | Parsed equality with official JSON; [field matrix and hashes](stage-0-source-verification.md) |
| Application/database/tests | Local foundation + adapter/evidence slices verified | Locked Python backend, migrations, safe holdings preview/import and mocked broker adapter; full Stage 1 still open |
| Frontend/auth/scheduler | Not started | No financial endpoint or portfolio UI; Stage 2 security remains a gate |
| Secrets and Live access | Not configured | No credentials requested or used |
| Hosted target | Cloudflare + Supabase approved | Owner created dedicated Supabase project `ssqqjyrgrsjubxysobwy` and confirmed native GitHub deployment settings; schema deployment still needs observation |
| Commit/push | Explicitly authorised per verified stage | Owner has authorised implementation with subagents and stage commits/pushes |

## Public-content policy

Real workbook/CSV files, balances, position sizes, contribution amounts, dividends, private source hashes/paths and personal/employment notes stay outside public content. Their original local files are unchanged. Exact migration evidence is generated privately from those files. Public tests and examples use invented inputs; ignore rules do not substitute for reviewing tracked content.

## Next bounded task

Qualify the newly approved Cloudflare + Supabase production architecture before expanding hosted persistence/auth/jobs. Continue real history identity/opening coverage verification when private API/CSV evidence becomes available. Read requirements, CSV contract, broker integration, imports, and remaining Q01/Q02/Q03 gaps. The YAML prerequisite is complete and GBP currency is owner-confirmed. Establish statement/broker history coverage and stable execution/dividend/cash identity aliases before production replay. Do not re-ask resolved account scope, edit rights, tax deferral, alert recovery or July date.

Deliver a public-safe field matrix, synthetic fixture design and updated decisions. API remains primary unless the owner explicitly changes it. Snapshot group context is already understood; it does not provide historical trades.

## Documentation checks

The public-safe revision audit checked 29 Markdown files (27 under docs), 69 local links, 46 unique requirement IDs, question references, code fences, whitespace and known private source tokens/paths. Those checks passed. The archived brief preserves its body except for the personal filename redaction and terminal whitespace. Both original local source files retained their pre-inspection hashes. Ignore-pattern checks cover private sources/runtime data while allowing the safe environment example and dependency lockfiles. No application test/build/Live/API success is claimed by these documentation checks.

## Do not assume

- Public source code means public financial data or public runtime access.
- Snapshot value/cost establishes complete cash flows, returns or realised PnL.
- Slice is a group in the inspected format; the Total-row Name supplies that context.
- Date-only/unknown dates may be invented to make charts neat.
- Two-day drawdown means endpoint return or 48 wall-clock hours.
- Rebound alone erases an earlier decline from a rolling maximum.
- Tax becomes necessary because ISA market value passes an annual subscription limit.
- Remaining scenario/RAG/stress defaults are owner-approved.

## Source-contract checkpoint - 11 November 2026

Direct OpenAPI YAML and official JSON were downloaded and parsed: structurally identical, 17 paths and 38 schemas. Seven read routes, exact query/continuation contracts, provider rate budgets and unsupported semantics are recorded in the Stage 0 field matrix. This accepts the public provider-contract slice, not the full account-history gate. Owned-file link/fence/whitespace checks passed. No authenticated broker request or financial computation was performed.

## Stage 1A accepted evidence - 11 November 2026

Python 3.12.7, uv 0.13.7; pinned dependency versions/hashes in `backend/uv.lock`. From `backend`: `python -m pytest tests/test_persistence.py tests/test_config.py tests/test_app.py tests/test_backup.py -q` - **36 passed**. Scoped Ruff check and format checks passed. Actual CLI `db-init`, `backup` and separate-path `restore` smoke commands succeeded using an empty synthetic Demo account in ignored storage. The tests verify committed WAL evidence/precision survives restore, corrupt/mismatched backups fail, original files are retained, and cross-account source links are rejected.

This accepts slice 1A, not all Stage 1: economic events, CSV/API aliases, group workflows and workbook reconciliation are not implemented. CI is configured for Windows/Linux but no remote CI result is asserted at this checkpoint. There are no credentials, real imported balances or financial HTTP routes. Source/audit immutability guards ordinary ORM operations; it is not administrator-proof. Migration packaging currently requires the source checkout. See local development for commands and limits.

## Stage 1B adapter checkpoint - 11 November 2026

`python -m pytest tests/test_trading212.py -q` - **39 passed**; owned-file Ruff checks passed. Independent review found no material blocking issue in this observation adapter. Direct YAML/schema verification preceded implementation. No authenticated broker request was made. Full Stage 1B remains open for normalized events, verified aliases, persisted sync/checkpoints and source-backed cash/quantity replay. The preceding Stage 1A commit `073e2df` also passed [GitHub Actions on Windows/Linux](https://github.com/dhdylanhuang/meridian-axis/actions/runs/43101048613).

## Stage 1C snapshot-evidence checkpoint - 11 November 2026

The holdings parser, preview, durable import service and CLI are verified on invented data. Full backend suite: `python -m pytest -q` - **137 passed**; Ruff lint/format passed. Tests include Total exclusion, exact arithmetic, N/A/nonadditive dividends, duplicate races, account isolation, transaction failure after inserted rows, safe failed-run persistence, source preservation and no database writes from preview. Independent service review found no material blocker; the oversized-input digest caveat was fixed and regression-tested.

This accepts only the source-evidence portion of 1C. No economic ledger, PDF importer, group edit workflow, workbook migration or complete reconciliation is delivered. The three supplied statements were inspected read-only; the additional transactions statement is cash-only. It does not provide missing earlier executions or opening controls. Never re-ask for these same PDFs as though they were not inspected. Hosting is now owner-approved Cloudflare + Supabase, with an early runtime/Postgres/capacity/security qualification gate; the SQLite foundation is local tooling.

## Hosting qualification in progress

Cloudflare + Supabase is owner-selected. Dedicated free projects are authorised; the owner handles sign-in. Provider setup through computer use stopped because browser access was unavailable and the native fallback could not verify the browser URL confidently. The owner subsequently created the dedicated Supabase target and connected GitHub; no authenticated Management API/CLI connection, deployment credential or DNS change was created by the agent. Use the native repository integration below; never bypass the browser restriction.

The isolated [Python Worker probe](worker-feasibility.md) passed local runtime smoke and non-deploying bundle checks. It did not connect to PostgreSQL or measure hosted CPU, Auth, analytics, network/provider compatibility or retention capacity. Native PostgreSQL foundation parity is now CI-verified below; this is not an actual Supabase/Hyperdrive deployment. Production auth/jobs/UI remain unimplemented.

## PostgreSQL foundation accepted evidence - 11 November 2026

The [corrected qualification run](https://github.com/dhdylanhuang/meridian-axis/actions/runs/43106146159) passed Windows/Linux backend checks and all six disposable PostgreSQL 17 integration tests. Local backend verification was **149 passed, six skipped** because no local test database is configured; the six integration tests ran against CI's explicit loopback database. Fresh and 0001-to-0002 migrations, evidence preservation, exact Decimal TEXT round-trip, successful-hash uniqueness, rollback/retry, cross-account foreign keys and closed default grants/RLS all passed.

CI initially exposed a test expectation issue: pg8000 maps PostgreSQL foreign-key SQLSTATE 23503 to ProgrammingError, while unique violations map to IntegrityError. The regression now asserts the exact SQLSTATE and `fk_source_run_account` name through DBAPIError. It does not relax the database constraint. Synthetic-only failure annotations preserve useful diagnostics without account credentials. The PostgreSQL CI job now explicitly selects Python 3.13 rather than allowing the local `.python-version` to override setup-python; [that interpreter qualification passed](https://github.com/dhdylanhuang/meridian-axis/actions/runs/43107073716).

Published migration 0001 was retained. Migration 0002 repairs PostgreSQL partial uniqueness and closes PUBLIC/anon/authenticated table grants with RLS enabled; SQLite only advances its schema version. There are no member policies or hosted login/session implementation. Owner/BYPASSRLS powers remain outside RLS, so API authorization and least-privilege runtime credentials still require proof. Existing SQLite backups stay compatible with their recorded revision; use a pre-upgrade backup and a new restore drill for later schemas. No actual Supabase project or production database was changed.

## Provider setup boundary

Provider dashboards were authenticated in a separate browser session; this does not authenticate the CLIs here. Use a trusted administrative device or cloud CI for provider setup and secret management. No persistent provider or broker credential should be copied into this workspace or chat. The Supabase app was not confirmed connected, so the current path is a dedicated Free project named `meridian-axis` created through the dashboard, with only its public project URL shared. Cloudflare dashboard/GitHub integration or cloud CI credentials remain candidate setup paths; none is configured. Do not repeatedly request a connection method the owner could not find.

Temporary PDF extraction text, rendered inspection crops and helper copies under the task's private statement-review directory were removed after inspection. Original source PDFs, workbook and CSV were not targeted or modified. Public statements retain only structural/coverage observations; account contact information stays out of this repository.

## Native Supabase bootstrap qualification

The owner supplied project `ssqqjyrgrsjubxysobwy` and confirmed repository `dhdylanhuang/meridian-axis`, working directory `.`, production branch `main`, production deployment enabled, and automatic preview branching disabled. This is owner-confirmed setup, not an authenticated project inspection by the agent. No Supabase standalone app/CLI token is required for the native GitHub delivery path.

The new `supabase/config.toml` and native SQL bootstrap are being validated on a temporary branch before `main` advances. Local verification: **150 passed, ten PostgreSQL tests skipped** without a local database. The native asset has an independent review and an offline DDL/model parity check; ten service-backed tests must pass on that exact validation commit before production publication. Actual Supabase migration status must then be observed separately. No `[remotes]` config, Auth/API reset, seed data, user creation or financial import is included. [ADR 0002](decisions/0002-hosted-migration-authority.md) establishes one hosted schema writer with paired schema parity.
