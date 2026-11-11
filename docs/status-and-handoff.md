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
| Transaction-history CSV | Not inspected | Snapshot is not a replacement for execution/cash-flow history |
| Provider research | Documentation reviewed | Official OpenAPI JSON/endpoint pages, no authenticated calls |
| OpenAPI YAML | Verified directly | Parsed equality with official JSON; [field matrix and hashes](stage-0-source-verification.md) |
| Application/database/tests | Stage 1A verified | Locked Python backend, initial migration, evidence/audit constraints, liveness, backup/restore; 36 offline tests pass |
| Frontend/auth/scheduler | Not started | No financial endpoint or portfolio UI; Stage 2 security remains a gate |
| Secrets and Live access | Not configured | No credentials requested or used |
| Remote access | Required, free services only | [Hosting review](hosting-options.md); no host selected or configured |
| Commit/push | Explicitly authorised per verified stage | Owner has authorised implementation with subagents and stage commits/pushes |

## Public-content policy

Real workbook/CSV files, balances, position sizes, contribution amounts, dividends, private source hashes/paths and personal/employment notes stay outside public content. Their original local files are unchanged. Exact migration evidence is generated privately from those files. Public tests and examples use invented inputs; ignore rules do not substitute for reviewing tracked content.

## Next bounded task

Continue Stage 1B broker adapter and Stage 1C verified holdings parser while inspecting the private annual/activity PDF statements. Read requirements, CSV contract, broker integration, imports, and remaining Q01/Q02/Q03 gaps. The YAML prerequisite is complete and GBP currency is owner-confirmed. Establish statement/broker history coverage and stable execution/dividend/cash identity aliases before production replay. Do not re-ask resolved account scope, edit rights, tax deferral, alert recovery or July date.

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

## Source-contract checkpoint ? 11 November 2026

Direct OpenAPI YAML and official JSON were downloaded and parsed: structurally identical, 17 paths and 38 schemas. Seven read routes, exact query/continuation contracts, provider rate budgets and unsupported semantics are recorded in the Stage 0 field matrix. This accepts the public provider-contract slice, not the full account-history gate. Owned-file link/fence/whitespace checks passed. No authenticated broker request or financial computation was performed.

## Stage 1A accepted evidence ? 11 November 2026

Python 3.12.7, uv 0.13.7; pinned dependency versions/hashes in `backend/uv.lock`. From `backend`: `python -m pytest tests/test_persistence.py tests/test_config.py tests/test_app.py tests/test_backup.py -q` ? **36 passed**. Scoped Ruff check and format checks passed. Actual CLI `db-init`, `backup` and separate-path `restore` smoke commands succeeded using an empty synthetic Demo account in ignored storage. The tests verify committed WAL evidence/precision survives restore, corrupt/mismatched backups fail, original files are retained, and cross-account source links are rejected.

This accepts slice 1A, not all Stage 1: economic events, CSV/API aliases, group workflows and workbook reconciliation are not implemented. CI is configured for Windows/Linux but no remote CI result is asserted at this checkpoint. There are no credentials, real imported balances or financial HTTP routes. Source/audit immutability guards ordinary ORM operations; it is not administrator-proof. Migration packaging currently requires the source checkout. See local development for commands and limits.
