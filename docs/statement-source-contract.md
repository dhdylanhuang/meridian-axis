# Statement evidence and historical coverage

Status: **VERIFIED read-only source inspection, 11 November 2026**. Three owner-supplied Trading 212 PDF statements were inspected with text extraction and rendered table-header checks. This document describes observed structure and limits; it is not a production PDF importer or proof of a complete ledger.

Raw statements, extracted text, source hashes, account identifiers, balances, position sizes and source paths remain private. Public fixtures must use invented records. The owner has separately confirmed GBP and one Stocks and Shares ISA in application scope.

## Sources and periods

| Source alias | Observed coverage and structure | Authority and limits |
| --- | --- | --- |
| Annual statement | 11 pages. Printed period **5 April 2025 22:00 UTC to 5 April 2026 22:00 UTC**. Stocks ISA overview, end-period open positions, sell/disposal results, interest and dividend detail, explanatory notes. | The annual filename is not evidence of calendar-year coverage. This is not an all-buy/all-sell execution and cash history. It cannot independently reconstruct acquisition history or contributions. |
| Activity statement | 60 pages. Printed period **31 December 2025 22:00 UTC to 10 November 2026 21:59 UTC**; generated 11 November 2026. Stocks ISA trade table, open-position summary, cash breakdown, cash transactions, dividends and notes. | The filename's date range is not a substitute for these printed UTC boundaries. Table coverage is useful for reconciliation; it does not prove that the account opened at this period's start. |
| Transactions statement | 46 pages. Printed date range **1 May 2025 to 10 November 2026**; generated 11 November 2026. Account-separated cash transaction tables. | Extends cash evidence into 2025. It is not an execution statement and does not establish opening holdings/cash or complete earlier buys. The UTC label was verified on generation time, not on the transaction-time column or date-range boundaries. |

The periods overlap. Never add the annual disposal/dividend totals to the activity events as new economics. Use them as independently identified source observations and controls, linking overlapping evidence only after verified identity matching.

The annual and activity PDFs contain **Stocks ISA and Cash ISA sections**. The additional transactions statement has **Cash ISA, CFD, ISA and Invest account sections**; its ISA account identifier was privately matched to the prior activity statement's account identity; the actual identifier is omitted here. A section's presence does not mean it contains trades or any activity. The confirmed application scope remains the Stocks and Shares ISA. Restrict parsing by explicit account/section identity; do not import Cash ISA balances or income because they occur in the same PDF. Transfers between accounts require classification at the chosen account boundary, even where both accounts belong to the same owner.

## Activity trade table

The rendered header confirms this column order:

```text
Execution time | Instrument | ISIN | Order ID | Direction | Quantity |
Execution price | Value | Order type | Execution venue | Session |
FX rate | FX fee | Exchange & govt fees | Return | Value
```

The two `Value` columns have different context: one sits beside the execution price and one at the account-currency end of the row. Preserve column positions and context rather than collapsing duplicate names into one dictionary key. The statement notes define value as quantity times price; fee/FX/net-cash treatment still requires a reconciled normalization contract before posting cash.

Observed parsing facts:

- Execution timestamps use `YYYY-MM-DD HH:MM:SS`; the notes explicitly state transaction execution times are UTC. Keep the original text and source row/page. Do not replace execution time with statement generation time.
- `Order ID` is numeric text. The notes explicitly say one order can have multiple fills. A repeated ID was observed for distinct market-buy rows with different execution times, quantities and prices. **Order ID alone cannot deduplicate fills.** No separate fill-ID column was observed.
- Both Buy and Sell rows use positive quantities; Direction supplies their economic sign. Thousands separators and decimal fractions occur. Preserve Decimal precision and validate the documented number format.
- Monetary fields use currency symbols; trade prices/values include more than one currency, while account-side values and charges show GBP. A dollar symbol alone cannot identify the listing's ISO currency. Link a verified listing/provider record before normalization; ISIN and execution venue are not sufficient to infer the listing exchange or quote currency.
- Charges and returns can use `-` as a missing/not-applicable token. A negative monetary value is distinct from that token. Do not replace all dashes with zero without a field-specific verified rule.
- Order types include ordinary market/limit activity **and stock-split and scrip-dividend records**. These require explicit corporate-action/income semantics. They must not enter a generic Buy parser and create fabricated purchase cash flows or acquisition costs.
- Execution venue and session are present, including non-regular sessions. Execution venue is not an exchange calendar identity for future quote polling.

The read-only exploratory extraction detected 511 trade rows across the trade section. This is a source-shape check, not a claim of 511 independent economic events or a verified cash replay. The extraction is private inspection tooling and is not a supported parser.

## Other statement families

| Family | Verified fields / observations | Required handling |
| --- | --- | --- |
| Activity open positions | Instrument, ISIN, quantity, average price, price, return and value in instrument currency, FX rate, return and value in account currency. | End-period reconciliation observation, not additional acquisitions. Position average price is not evidence of complete execution cost history. The notes describe this position FX rate as a guidance/end-of-month rate; do not reuse it as transaction-date FX. |
| Activity cash breakdown | GBP total cash, GBP settled cash, settled cash held in banks and qualifying money-market funds. Notes distinguish settled and unsettled funds. | Supports GBP account reporting and end-period cash controls. Do not add the banks/QMMF decomposition to total cash. Settled cash is not necessarily free/total cash. |
| Activity Stocks ISA cash transactions | `Time`, `Type`, `Amount`; dated entries include interest, transfers between accounts, deposit/provider descriptions and ADR charges. Monetary amounts are signed GBP. No stable transaction-reference column was observed. | Preserve raw type and sign. Classify boundary flows, income and charges explicitly; a provider description alone is not a complete economic contract. Do not invent broker references or alias cash events by amount/date alone. |
| Activity dividends | Instrument, ISIN, issuing country, eligible holdings, pay date, amount per share, FX rate, total amount in instrument currency, WHT rate, WHT and total amount in account currency. No dividend-reference column was observed. | Preserve source components and date precision. Verify gross/net/withholding and API matching before normalizing; avoid counting one payment again from a cumulative holding/group snapshot. |
| Annual open positions | Instrument, ISIN, instrument type, position size, average price, price and total result. | Additional end-period controls with the annual statement's own date and method, not the activity statement's date. |
| Annual disposal results | Execution time, instrument, ISIN, instrument type, reporting status, position size, average price, execution price, FX rate, account-currency execution price and total result. | Disposal/cost-result evidence only. Missing earlier buys are not implied to exist in this source. Broker results are not a tax-engine implementation. |
| Annual dividends | Instrument, ISIN, issuing country, holdings/pay date, per-share and gross amounts, FX, withholding and net amount fields. | Period-level reconciliation evidence. Retain overlap with activity dividends as evidence, not additive income. |

## Opening history and identity gaps

No explicit opening-holdings schedule or opening-cash control for the activity start was established in this review. The annual statement supplies a later open-position snapshot, not the missing starting ledger. None of the three sources establishes account inception or confirms all historical acquisitions, transfers and corporate actions before the activity period. Q03 therefore remains open.

For a trustworthy history replay, obtain an all-history transaction CSV/API export that covers account opening, including executions, cash movements, dividends, fees and supported corporate actions. If complete history cannot be obtained, use a source-supported opening position/cash record at a documented cutoff and mark earlier cost/performance unavailable. A current position snapshot must never manufacture past purchases.

Cross-source deduplication remains unverified: the activity PDF exposes order IDs but no independent fill IDs or cash/dividend references. The additional transactions PDF supplies payment-provider transaction identifiers in some notes, not a uniformly populated broker reference column; their namespace/equivalence to API references remains unverified. Compare private API/transaction-export evidence before creating aliases. A proposed composite identity based on order/time/quantity/price can assist review, but must not be silently treated as a broker-issued unique key. Ambiguous matches go to reconciliation; changed same-ID economics remain conflicts or revisions.


## Additional transactions statement

The newly supplied statement is a **cash-movement report**, despite the broad word “transactions”. Its rendered table header is:

```text
AMOUNT | CURRENCY | TIME | TRANSACTION TYPE | NOTES
```

The ISA table spans pages 15–45. Exploratory shape inspection detected 569 dated rows in this section, all with GBP currency labels. This count is not a reconciled cash ledger. Cash ISA activity is separately labelled and excluded from application economics; CFD and Invest sections must also remain excluded. The private ISA account identifier matches the prior activity statement. Continue matching identity rather than relying on page numbers as a permanent parsing rule.

- Time values use `DD/MM/YYYY HH:MM:SS`. The cover's generation stamp explicitly says UTC, but this review did not establish the time zone of the transaction rows or the exact inclusive/exclusive period cutoffs. Preserve original text and date precision until verified; do not copy the activity statement's execution-time convention onto this separate report without evidence.
- Observed transaction-type labels include interest on cash, transfers between accounts, ADR fees and payment-provider descriptions. A provider name is not itself a verified deposit/withdrawal classification. Classify signed amounts and the Stocks ISA boundary with reconciliation evidence.
- Some Notes contain a `Transaction ID`; many rows do not. Such notes can also contain private bank/counterparty references. Store them as private source evidence, never in public fixtures/logs. Do not assume a payment-provider ID is the Trading 212 cash-history `reference`, and do not manufacture IDs for unreferenced interest or transfer rows.
- No instrument, ISIN, execution quantity/price, order ID, independent fill ID or dividend-reference columns are present in this cash table. It cannot replace the missing pre-2026 acquisition/execution history or establish a stock-split/dividend-share action.
- Account-value controls appear separately from the cash rows. They are not an opening-cash schedule or opening-holdings inventory. No explicit opening balance, zero-opening/inception statement or complete-history assertion was established.

This source materially improves dated cash-flow evidence for 2025–2026, but **Q02/Q03 are not resolved**. The remaining task is to obtain/verify execution history and source identities through the API or a machine-readable history export, or establish an evidenced opening cutoff. Retain the supplied PDFs as independent reconciliation evidence; do not repeatedly ask the owner for these same statements.

## PDF versus CSV/API

These PDFs contain a text layer and readable tables, so they are useful source evidence. Reliable automation still needs page-coordinate/header contracts, repeated-header removal, wrapped cells, duplicate column labels, section/account boundaries, sign and missing-token rules, corporate-action classification and complete reconciliation. Ordinary text extraction can interleave adjacent columns. It is not equivalent to a verified CSV schema.

Prefer the official API and a machine-readable all-history CSV for the economic ledger. Retain PDFs as independent controls and evidence. A dedicated PDF importer is a separate bounded task if machine-readable history cannot be supplied; do not add an untested parser merely because exploratory extraction produced rows.

These gaps block complete historical reconciliation, production cross-source aliases and since-inception performance claims. They do **not** block persistence, precision, import logging, synthetic contract tests or supported current snapshot work. See [imports and reconciliation](imports-and-reconciliation.md), [broker integration](trading212-integration.md), [holdings CSV contract](csv-contract.md) and [stage gates](development-stages.md).

## Inspection evidence

Read-only inspection used the bundled Python PDF libraries for all 117 pages and Poppler rendering of relevant table headers. The trade, open-position, dividend and cash schemas were checked against source layout, including the additional transactions statement's ISA table header. Private extraction files stay in an ignored review directory; no raw source rows were added to fixtures or documentation. No source PDF was edited, no authenticated broker request occurred and no automated financial import or cash/quantity reconciliation is claimed.
