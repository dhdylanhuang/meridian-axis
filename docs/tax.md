# Tax calculation scope and matching

Status: DEFERRED by explicit owner decision, 11 November 2026. One Trading 212 Stocks and Shares ISA is confirmed. This document preserves a possible later extension; it is not an initial-release requirement or stage gate.

## Scope and ownership

The owner confirms one Stocks and Shares ISA and has deferred tax matching, tax summaries and allowance screens. Show initial cost/PnL as management/broker measures, not Section 104 results. Verify connected identity during setup. A future tax view would treat ISA gains as not applicable rather than consuming an ordinary CGT allowance. [HMRC disposal guidance](https://www.gov.uk/tax-sell-shares)

Pool by beneficial owner, security class and legal capacity for supported taxable holdings, not by application user, ticker, group or arbitrary broker account. Transactions in relevant accounts outside this app can affect completeness. The partner's login never receives a separate copy of the owner's tax pool. Same-class securities can span listings; resolve identity before matching. [Section 104 legislation](https://www.legislation.gov.uk/ukpga/1992/12/section/104)

Currency conversion uses executed transaction-date facts under a documented source/rate convention. Preserve costs/proceeds/allowable charges in original currency and GBP. Provider-reported realised PnL and average paid price are reconciliation fields, not HMRC allocations.

## Why deferral is unrelated to portfolio balance

The ISA annual subscription allowance limits money paid in during a tax year; it is not a cap on account market value. Income and capital gains within an ISA are generally tax-free, including when the account grows above its annual subscription allowance. Do not automatically enable a tax engine when the balance passes £20,000. A contribution tracker, if later requested, needs actual dated subscriptions and transfer/withdrawal rules rather than the current invested-cost snapshot. [GOV.UK ISA guidance](https://www.gov.uk/individual-savings-accounts/how-isas-work)

## Matching algorithm contract (future phase only)

For supported disposals, apply same-day matching, then qualifying acquisitions within the following 30 calendar days, then the Section 104 pool. Match quantities and their eligible costs; never treat this as a streaming average-cost sell that is permanently final on disposal day. [HMRC identification order](https://www.gov.uk/hmrc-internal-manuals/capital-gains-manual/cg51555)

Use a deterministic, replayable batch calculation over the required historical horizon. Aggregate same-day activity consistently and allocate costs/proceeds proportionally where a disposal spans matching categories. An acquisition quantity cannot support two disposal matches. The exact interaction of competing disposals/acquisitions requires authoritative worked fixtures, not a naive independent 30-day search per sale.

The remaining qualifying expenditure belongs to the Section 104 pool. Track pool quantity and total allowable expenditure, and release proportional cost when a sale matches it. Preserve calculations at high precision; specify final reporting rounding separately. [HMRC pool guidance](https://www.gov.uk/hmrc-internal-manuals/capital-gains-manual/cg51575)

## Worked acceptance examples

These synthetic examples exclude fees, FX, corporate actions and other matching activity. Money is GBP.

| Example | Inputs | Expected result |
| --- | --- | --- |
| Pool-only disposal | Opening pool 100 shares / £1,000; sell 20 for £300; no same-day or following-30-day acquisitions | Matched cost £200, gain £100, remaining pool 80 / £800 |
| Same-day priority | Opening pool 100 / £1,000; buy 20 for £240 and sell 30 for £450 on the same day; no following acquisitions | Match 20 to £240 and 10 to pool cost £100; gain £110; remaining pool 90 / £900 |
| Following-30-day priority | Opening pool 100 / £1,000; sell 20 for £300 on 1 July; buy 8 for £96 on 15 July | Match 8 to £96 and 12 to pool cost £120; gain £84; pool 88 / £880 after completed matching |

Implement each rule separately, then test interactions. Add day +30 versus day +31, multiple buys/sales, partial matching, same-day precedence over future matching, fractional shares, acquisition fees, disposal fees, foreign currency and a purchase after 5 April matching a prior-tax-year sale. Under unsupported circumstances, return a specific limitation rather than a fabricated pool result.

## Provisional and complete results

A disposal can remain provisional until the imported coverage extends through its relevant following-30-day period. Wall-clock passage alone does not establish complete evidence. Track the data cutoff, last successful history coverage, unresolved event types, cross-account gaps and calculation version. A later import may revise an earlier tax year; retain earlier run provenance and make the change visible.

No complete acquisition history or source-supported opening pool means no reliable full tax cost, even when the broker supplies a current position average. Permit an explicitly supplied and audited opening pool with its limitations; do not infer it from a snapshot's invested amount.

## Tax years and settings

Tax year runs 6 April through 5 April. Adopt Europe/London for deriving the supported tax date from execution timestamps, pending validation against source statements; preserve original timestamps. Use execution, not settlement or import date, unless a verified instrument-specific rule says otherwise.

Store annual exempt amounts and dividend allowances by tax year with sources and effective dates. Do not hardcode a current value into historical years. Show supported realised gains, losses and available allowances without claiming total tax payable. External gains, losses, income, residence, ownership and other obligations are outside the initial ledger's knowledge.

## Explicit gaps

Corporate actions, transfers, stock splits, mergers, spin-offs, return of capital, accumulation income, excess reportable income, equalisation and unusual fund tax treatment require source-supported rules. Splits may preserve total economic cost while changing quantity, but a generic split rule is not sufficient for every corporate action.

Q07's initial-scope decision is resolved: defer this engine. A later owner-authorised tax phase must decide which events/adjustments it supports. The original CSV/API-only ambition does not justify pretending required tax adjustments are present. Accumulation-unit reinvested income can affect allowable expenditure: [relevant legislation](https://www.legislation.gov.uk/ukpga/1992/12/part/III/chapter/III/2023-03-01).

No automatic tax filing, tax payments or accountant messages are in scope. Keep matching schedules inspectable so the owner can check quantities, dates, cost allocations and totals by hand.
