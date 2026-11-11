# Verified holdings CSV contract

Status: one real Trading 212 group snapshot inspected read-only on 11 November 2026. This establishes one export format, not the broker's transaction-history format. Raw file contents, exact source digest, personal amounts and original timestamped filename are not included in this public repository.

## Headers and identity

The sample parses as UTF-8-sig CSV with the exact header sequence:

```text
Slice,Name,Invested value,Value,Result,Owned quantity,Dividends gained,Dividends cash,Dividends reinvested
```

There are holding rows followed by a control row whose `Slice` is `Total`. In holding rows, `Slice` is a ticker/listing label, not the portfolio group. The control row's `Name` supplies the group/export name. Preserve that name as group-context evidence for all holdings in this snapshot, separately from raw Slice text.

The original brief's assumption that a holding's Slice is its sector-style group is therefore wrong for this inspected format. A parser must preserve both fields with their actual meanings. Do not derive a group from ticker text or rely solely on the filename.

## Field semantics and parsing

| Field | Observed content | Policy |
| --- | --- | --- |
| Slice | Holding ticker label; `Total` control | Preserve raw text; resolve listing with metadata/mapping; exclude control from holdings |
| Name | Holding name; group name on Total row | Display evidence; Total-row name is group context, not another instrument |
| Invested value | Numeric snapshot amount | Broker snapshot cost measure, not deposits or tax pool |
| Value | Numeric snapshot amount | Snapshot market value; currency must be supplied/verified externally |
| Result | Numeric snapshot amount | Observed value-minus-invested arithmetic; not complete realised/total-return history |
| Owned quantity | Numeric holding shares; `-` on Total | Decimal shares; nonnumeric total token is expected and not an economic value |
| Dividend fields | `N/A` per holding; numeric group controls | `N/A` is unavailable, not zero; preserve group-level cumulative measures separately |

Holding invested, value and result columns each reconciled to the Total control within £0.01. Each holding's Result matched Value minus Invested value. The inspected dividend controls did **not** satisfy gained = cash + reinvested within that tolerance; their meanings must be verified instead of forcing an invented balancing entry or treating them as three additive income figures.

The sample has no event ID, execution date/time, explicit currency, exchange or ISIN column. It cannot establish which market listing a ticker denotes without other evidence. A timestamp in a filename is export context, not a verified execution time or quote timestamp.

## What this source can and cannot do

Use it for current observed holdings, cost/value controls, group membership evidence and cumulative group-dividend snapshots. It is easier to parse than a history feed but carries less historical information. It cannot independently reconstruct trades, realised PnL, external contributions, historical FX, exact performance or daily risk returns.

The API remains the primary account/history source unless the owner explicitly revises that decision. Transaction CSV fallback still needs a separate real history export and verified cross-source identity fixtures. Never apply transaction-ID deduplication to this file: there are no transaction IDs. Deduplicate accepted snapshots by account, file kind and hash, retaining observation context.

When a holding appears in more than one exported group, preserve competing group-context evidence and flag review. Manual overrides survive subsequent snapshot/API syncs. The Total row is excluded from economics while its group metadata and control sums remain available for validation.

## Safe fixture design

Create a public fixture later with invented names, tickers, quantities and amounts, the same headers, a synthetic Total row, `N/A` dividends and `-` total quantity. Include a separate deliberately nonadditive dividend-control case. It must be explicitly marked synthetic and must not be an anonymised copy that retains real position sizes.

Private source paths are configured locally. The original workbook and CSV remain unchanged and outside the repository. See [imports](imports-and-reconciliation.md) and [integration](trading212-integration.md) for shared processing rules.
