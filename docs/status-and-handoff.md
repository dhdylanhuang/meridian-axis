# Status and handoff

Last reviewed: **11 November 2026**, including the owner's pre-publication answers and holdings CSV inspection.

## Actual state

| Area | State | Evidence / limits |
| --- | --- | --- |
| Repository | Public GitHub; documentation only | Public-safe source summaries and synthetic examples; no application implementation |
| Account and access | Confirmed | One Trading 212 Stocks and Shares ISA; two logins with equal full editing rights |
| Goal | Confirmed | £100,000 by 2030; original 30 April 2030 target date retained |
| Tax engine | Deferred | Explicit owner decision; no initial tax schemas/screens/matching required |
| Alerts | Confirmed | Group >=10% running drawdown; portfolio >=2% largest peak-to-trough drawdown within two trading days; re-arm after recovery |
| Excel review | Verified read-only | Structure/methods/defects in public-safe workbook baseline; actual amounts and provenance stay local |
| July date | Known unknown | Owner cannot establish actual observation date; preserve source label and uncertainty |
| Holdings CSV | Verified read-only | Slice=ticker; Total-row Name=group; no execution IDs/dates/currency; see CSV contract |
| Transaction-history CSV | Not inspected | Snapshot is not a replacement for execution/cash-flow history |
| Provider research | Documentation reviewed | Official OpenAPI JSON/endpoint pages, no authenticated calls |
| OpenAPI YAML | Still to verify directly | Mandatory before client implementation; browser could not render YAML |
| Application/database/frontend/tests | Not started | No manifests, runnable app, schema, scheduler or automated application tests |
| Secrets and Live access | Not configured | No credentials requested or used |
| Remote access | Deferred | Later owner-authorised stage |
| Commit/push | Explicitly authorised | Owner requested committing and pushing the sanitised documentation baseline; inspect Git history/remote status for the resulting publication state |

## Public-content policy

Real workbook/CSV files, balances, position sizes, contribution amounts, dividends, private source hashes/paths and personal/employment notes stay outside public content. Their original local files are unchanged. Exact migration evidence is generated privately from those files. Public tests and examples use invented inputs; ignore rules do not substitute for reviewing tracked content.

## Next bounded task

Complete Stage 0 source contracts when implementation work is requested. Read requirements, CSV contract, broker integration, imports, and remaining Q01/Q02/Q03 gaps. Verify OpenAPI YAML; inspect a real execution-history export or broker history coverage; confirm primary currency and map stable execution/dividend/cash identities. Do not re-ask resolved account scope, edit rights, tax deferral, alert recovery or July date.

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
