# Excel baseline and migration evidence

Status: VERIFIED read-only inspection, 11 November 2026; public-safe revision following confirmation that GitHub is public. Exact source figures remain in the owner's local workbook, not in this repository.

## Source handling

Configure a local workbook path outside the public repository or inside an ignored private directory. Do not publish the original filename, absolute path, source digest, balances, cost amounts, individual position sizes, contributions, dividends or personal/employment notes. The local import computes its hash and records provenance privately. The workbook was not edited or recalculated in Excel during inspection.

The source is a manually maintained holdings workbook, not a complete execution ledger or a verified all-assets NAV history. It contains a Dashboard, Monthly Tracking, several group sheets and How to Update instructions. Each group sheet has row-7 headers for ticker, name, invested GBP, value GBP, gain GBP, return, quantity, dividends GBP and notes. Summary cells D2/E2/F2/I2 link to group totals. Exact names and total-row locations are discovered from the local source during migration.

The latest recorded snapshot in the reviewed workbook is 11 October 2026. The later example CSV is a separate, more recent group snapshot, not an update already applied to the workbook. Do not mix as-of dates or present either source as today's broker valuation.

## Snapshot migration

Six observations were populated in Monthly Tracking rows 5–10. Retain their original labels, source cells, known dates/date precision, group coverage and private commentary. Source labels include May, July, August, September and two October observations; not every observation is month-end, and June is absent.

The owner has confirmed that the July-labelled row's actual date is unknown. Preserve the label with unknown date precision and no invented day. Do not repeatedly ask for a date the owner does not know. A date-axis UI can show this as an undated observation; it must not silently assign a month-end or infer a date from upload time. A recorded zero dividend field remains an observed value with uncertain coverage, not proof that no dividends had been paid.

At least one early observation excludes a missing group. Preserve that limited coverage rather than filling it with zero. Group values reconciled to each recorded total during inspection. Import the original exact values privately and reconcile within £0.01. Publish only synthetic reconciliation examples.

The recorded invested amount is summed holding cost, not verified external contributions. Consecutive value changes include contributions/disposals and are not investment returns. Cumulative dividends must not be recreated as recurring cash-payment events.

## Verified legacy methods and defects

| Finding | Structural evidence | Active treatment |
| --- | --- | --- |
| Allocation denominator | Dashboard allocation divides group value by total invested cost rather than total portfolio value | Correct active weights; do not publish source allocation percentages |
| Shifted holding formulas | Some holding gain/return formulas reference another row or a subtotal | Calculate from correct holding inputs; synthetic row-shift regression test |
| Dividends not attributed | Holding dividend cells are zero while group totals are manually populated | Retain group-level cumulative observations; never guess individual payments |
| Multiple targets | Dashboard, group summaries, projection boxes and narrative milestones disagree | Owner's current £100,000 target supersedes legacy target amounts |
| Date conflict | Workbook projections use 5 April 2030; original app brief uses 30 April 2030 | Retain legacy method separately; active planned target date remains 30 April 2030 |
| Stale horizon | Group forecasts hardcode 44 months | Active projection uses a dated schedule |
| Old operating instructions | Earlier auto-invest instructions differ from later source notes | Do not assume deposits or investments execute automatically |
| Account wrapper | Owner now confirms one Trading 212 Stocks and Shares ISA | Initial tax engine deferred; no balance-based activation trigger |

The workbook formulas use nominal monthly growth R/12 and end-period contributions:

FV = start × (1+R/12)^n + contribution × ((1+R/12)^n−1)/(R/12), with legacy n=44.

All legacy group forecast results were independently reproduced from local inputs. Exact outputs, scenario assumptions and contribution amounts are intentionally omitted here. Re-read the private workbook for a migration rehearsal; use synthetic cases for public tests. Retaining a legacy reconciliation does not require active group-projection objects.

## Synthetic acceptance examples

These are invented values and do not describe the owner:

- Two holdings worth £300 and £700, with costs £250 and £650: securities value £1,000, cost £900, simple gain £100; securities weights 30%/70%.
- A row with its own cost £80 and value £72 must show −£8 even when the following row has a gain. This tests shifted references without copying personal positions.
- A cumulative dividend observation is metadata, not another payment on every import.
- At zero growth, £1,000 opening value plus £50 at each of 12 period ends yields £1,600.

## Non-goals and privacy

Do not repair or overwrite the source workbook under a documentation task. Do not reconstruct acquisition dates, missing cash flows, currency history or executed trades from snapshot cost/quantity alone. Do not copy source data to public fixtures, screenshots, issue comments or CI logs. Exact provenance and private import manifests belong to local runtime data; public docs preserve methods and known limitations.

## Implemented baseline evidence importer — 13 November 2026

`adapters/workbook_baseline.py` reads six explicitly mapped observations from an `.xlsx` byte stream. `WorkbookBaselineLayout` identifies the worksheet and an `ObservationCells` mapping for each observation. Cell mappings identify the original label, portfolio value, recorded invested cost, group values, optional group invested controls, notes and cumulative dividends. Dates come from explicitly verified layout metadata with `day` precision, month/year labels retain `month` precision through an `observed_month` field, and unknown dates remain absent. Month precision carries no invented day. The mapping belongs with private source administration because the public specification omits original cell locations and private notes.

The reader preserves source cell addresses, exact numeric XML text, cached formula results and formula expressions. It requires a populated numeric cache for financial formulas and performs no recalculation or workbook save. ZIP size/count limits, duplicate-member rejection, internal worksheet relationship validation and XML entity rejection bound parsing. Supported XML uses UTF-8. It rejects malformed or missing required cells with safe error categories.

Every observation reconciles included group values to the recorded securities total within £0.01. Missing groups stay explicit with absent values. When all included groups have mapped invested controls, the reader reconciles their sum within £0.01 and records `invested_reconciled=true`. A historical source that provides portfolio cost alone retains that amount with `invested_reconciled=false`. Cumulative dividends remain observations with uncertain coverage.

`application/workbook_import.py` accepts the full parsed baseline into existing immutable source records with `excel_migration` provenance, original source hash and import-run links. Parsing happens after the durable running log commits and outside the evidence transaction. All six records, audit and success status commit together. Same-account accepted source hashes are deduplicated, including competing acceptance, while revised workbook bytes append a new source version. Failures retain a safe failed attempt and leave no accepted partial observations. Economic events added are zero.

`python -m meridian.workbook_import_cli SOURCE --layout PRIVATE_LAYOUT_JSON` previews a mapped baseline with safe counts. Adding `--import` accepts evidence into the configured, already initialized local database. Preview performs no database writes. The layout JSON uses the same fields as the mapping dataclasses, with ISO dates and year-month strings where supported.

Synthetic tests verify exact decimals, six observations, month precision, unknown dates, missing groups, notes, cached formula handling, penny controls, source versioning, account isolation, rollback/retry and competing duplicate acceptance. Targeted baseline, CLI and existing import verification passed **47 tests** with Ruff checks passing.

The private migration rehearsal on 13 November read the owner's actual workbook and verified all six group-value controls within £0.01. Six recorded portfolio invested amounts, original labels, source cells, notes and cumulative dividend observations round-tripped exactly through immutable source records in an isolated local database. Historical group-level invested controls are absent, so all six retain `invested_reconciled=false`. Three labels supply month/year precision, two supply explicit dates and the owner-confirmed July observation remains undated. One observation retains incomplete group coverage.

Initial acceptance created six source records and one audit record. Reimport logged a duplicate and added no source records. The original workbook's pre/post hashes matched, and the temporary database was removed after verification. Explicit cell mapping and exact reconciliation receipts remain in ignored private runtime files. This verifies the D05 local baseline evidence/import slice. Hosted acceptance and a browser import workflow remain pending.
