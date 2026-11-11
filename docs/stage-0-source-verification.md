# Stage 0 source verification

Verified on **11 November 2026**. Scope: public provider contract, previously inspected holdings CSV and workbook structures. No authenticated broker request was made. This closes the direct OpenAPI YAML prerequisite for read-only client development; it does **not** establish this account's historical completeness or CSV/API identity equivalence.

## Provider contract evidence

Both official bundles were downloaded directly over HTTPS, parsed and compared as Python objects:

| Source | Bytes | SHA-256 |
| --- | ---: | --- |
| [Requested YAML](https://docs.trading212.com/_bundle/api.yaml) | 61,831 | `f2cda2ad99b9a22663c78a7b9187099c829df2fec655ea7f017236e11105c433` |
| [Official JSON](https://docs.trading212.com/_bundle/api.json?download=) | 77,378 | `a272f70a713fa9f2f906e9b4be12136c9d5d63d7f9f48562e939aa35c4fc041d` |

Result: **YAML and JSON are structurally identical**. OpenAPI version `3.0.1`, API version `v0`, 17 paths and 38 component schemas. Parsing used Python 3.12 and PyYAML 6.0.3 `safe_load`; JSON used the standard library. Downloads and temporary tooling were kept in ignored local storage. These are public specification digests, not private portfolio-file digests. Earlier browser MIME and sandbox-network failures were retrieval limitations; a subsequent permitted direct download succeeded.

The source can change without its version string changing. Before changing an adapter contract, retrieve again and record any digest/schema difference. Do not describe a schema-only verification as a Demo or Live integration test.

## Read request allowlist

Origins are `https://demo.trading212.com` and `https://live.trading212.com`. Paths already include `/api/v0`; configure the origin separately. Demo is the default. Live requires an explicit setting and separate local state. HTTP Basic is the documented key/secret mechanism; do not reproduce the legacy header mechanism merely because it is also present in the bundle.

| Method and path | Response schema | Documented limit / read scope |
| --- | --- | --- |
| `GET /api/v0/equity/account/summary` | `AccountSummary` | 1 / 5 seconds; `account` |
| `GET /api/v0/equity/positions` | array of `Position` | 1 / second; `portfolio` |
| `GET /api/v0/equity/history/orders` | `PaginatedResponseHistoricalOrder` | 20 / minute; `history:orders` |
| `GET /api/v0/equity/history/dividends` | `PaginatedResponseHistoryDividendItem` | 20 / minute; `history:dividends` |
| `GET /api/v0/equity/history/transactions` | `PaginatedResponseHistoryTransactionItem` | 20 / minute; `history:transactions` |
| `GET /api/v0/equity/metadata/instruments` | array of `TradableInstrument` | 1 / 50 seconds; `metadata` |
| `GET /api/v0/equity/metadata/exchanges` | array of `Exchange` | 1 / 30 seconds; `metadata` |

This intentionally excludes other GET routes as well as **all** POST/PUT/PATCH/DELETE operations. No orders, cancellations, broker export generation or pie management are implemented by this allowlist. Metadata is documented as refreshing every ten minutes and should be cached rather than polled with prices.

## Field coverage and authority

| Need | Verified schema fields / source | Meaning and normalisation limit |
| --- | --- | --- |
| Broker account identity/currency | `AccountSummary.id`, `.currency` | Convert int64 identity to a string without a float intermediate. Currency is the primary account currency. The schema does not provide an ISA-wrapper field; owner confirmation and setup evidence establish wrapper scope. |
| Account controls | `totalValue`; `cash.availableToTrade`, `.inPies`, `.reservedForOrders`; `investments.currentValue`, `.totalCost`, `.realizedProfitLoss`, `.unrealizedProfitLoss` | Store independent broker controls. Validate account reconciliation against real evidence before assuming cash components are disjoint or reconstructing NAV from them. |
| Listing identity | `Instrument.ticker`, `.isin`, `.currency`, `.name`; `TradableInstrument.currencyCode`, `.workingScheduleId`, `.type` | Provider ticker identifies the broker listing. Do not merge by display ticker, infer exchange suffixes or silently convert pence without unit evidence. |
| Held quantities/cost/value | `Position.quantity`, `.averagePricePaid`, `.currentPrice`, `.walletImpact` | Average/current price are explicitly in instrument currency. Wallet impact has its own `.currency`, `.currentValue`, `.totalCost`, `.unrealizedProfitLoss`, nullable `.fxImpact`; preserve its currency and avoid double FX conversion. |
| Quote time and delay | Not provided by `Position` | `createdAt` is the position opening time. Store fetch time, unknown quote age and unknown delay. A successful fetch is not evidence of a fresh market quote. |
| Execution identity | `HistoricalOrder.fill.id` and `.order.id` | Fill ID is the execution identity candidate; order ID is a separate relationship. Two different fills under one order must remain two executions. Uniqueness across real sources remains to verify. |
| Executed trade facts | `fill.filledAt`, `.quantity`, `.price`, `.type`; `order.side`, `.instrument`, `.currency`, `.status` | Prefer executed fill facts over order requested/cumulative quantity. Retain original signs and order side; validate their relationship before ledger booking. Preserve original timestamp text and parsed UTC. |
| Fill wallet components | `fill.walletImpact.currency`, `.netValue`, `.fxRate`, `.realisedProfitLoss`, `.taxes[]` | The bundle does not define enough sign/direction/gross-net semantics to assume how these reconcile. Retain raw components; require fixture/statement validation before deriving cash or splitting fees. |
| Charges | `Tax.name`, `.quantity`, `.currency`, `.chargedAt` | The field is named `quantity`, not `amount`. Preserve it as provider evidence until its monetary/sign semantics are verified; never guess a missing charge as zero. |
| Dividend identity/payment | `reference`, `paidOn`, `amount`, `currency`, `grossAmountPerShare`, `quantity`, `instrument` plus legacy ticker fields | `amount`/`currency` are primary-account-currency fields; gross per share is instrument currency. No explicit withholding amount or gross/net definition for the total is established. Do not derive withholding without verified conversion/tax semantics. |
| Cash events | `reference`, `dateTime`, `amount`, `currency`, `type` | Separate from orders/dividends. Types are `WITHDRAW`, `DEPOSIT`, `FEE`, `TRANSFER`, `INTEREST_ON_FREE_CASH`, `LENDING_INTEREST`. Amount sign and transfer boundary require real evidence before flow/performance treatment. |
| Group context | Verified holdings CSV Total-row `Name` | API position/history schemas do not expose the raw CSV Slice label or this group context. CSV Slice is ticker. Preserve group evidence and overrides independently of the broker adapter. |
| Session evidence | `Exchange.id`, `.name`, `.workingSchedules`; `WorkingSchedule.id`, `.timeEvents`; `TimeEvent.date`, `.type` | Join metadata through working schedule IDs. Events include open/close/break/extended-hours kinds. This does not establish holiday/half-day coverage, schedule horizon or portfolio cutoff; validate calendars separately. |
| Historic closes / unheld benchmark quotes / FX history | No dedicated route in the verified bundle | Separate market adapter required. Position prices cannot provide the requested independent benchmark or approved daily-risk histories. |
| Transaction CSV aliases | No verified real history export yet | The inspected holdings CSV has no event IDs or dates. It cannot verify fill/reference aliases or replace transaction history. |

The bundle's general multi-currency limitation says account/position/result values use primary currency, while specific position price fields explicitly say instrument currency. Use field-specific definitions and explicit wallet currency; do not apply the general sentence indiscriminately.

## Pagination, pacing and parsing contracts

- Orders and dividends accept optional integer/int64 `cursor`, optional `ticker`, and integer `limit` (default 20, maximum 50). Cash transactions accept string `cursor`, optional date-time `time` (retrieve starting from that time), and `limit`. Positions accept optional `ticker`. Do not invent `from`/`to` parameters or time filters on the other families.
- Histories return `items` and `nextPagePath`. Follow the entire returned path, validating origin **and the same history-family route** before attaching Basic credentials. Detect repeated paths and bound pages/runtime. Do not parse a cursor numerically and reconstruct it, discard supplied query parameters, or follow a redirect to another origin.
- The prose explicitly defines `nextPagePath: null` as the end even though the component schema declares only `string`. Support the documented null termination. A missing `items`, malformed page or missing continuation field is a contract error, not an empty successful sync.
- Rate budgets are per account, regardless of key/IP. Honour `x-ratelimit-limit`, `-period`, `-remaining`, `-reset` (Unix seconds) and `-used`; do not bypass a limit via another key or manual sync. Account-wide endpoint pacing must be shared by callers.
- Retry transient transport failures, HTTP 408/429 and eligible 5xx with bounded exponential backoff/jitter. Never retry before a later provider reset time. Treat 400/401/403 as terminal errors for the operation. Log only safe error categories/statuses, never Authorization, credentials or raw provider error bodies.
- Numeric JSON is parsed directly into Decimal; int64 identifiers remain exact and become strings at application boundaries. Unknown enum values/unsupported corporate actions preserve evidence and produce a coverage warning or quarantine, not a fabricated ordinary trade.
- These schemas generally omit `required` declarations. Their optionality cannot justify accepting an economic record without identity, currency, timestamp or quantities needed for its use. Validate requirements for each normalisation path and retain unsupported evidence without booking it.

Fill kinds in the verified bundle are `TRADE`, `STOCK_SPLIT`, `STOCK_DISTRIBUTION`, `FOP`, `FOP_CORRECTION`, `CUSTOM_STOCK_DISTRIBUTION`, `EQUITY_RIGHTS`, `SCRIP_STOCK_DIVIDENDS`, `STOCK_DIVIDENDS`, `STOCK_ACQUISITION`, `CASH_AND_STOCK_ACQUISITION`, `SPIN_OFF`. Their presence is not a promise that initial ledger replay understands them. Unsupported kinds block an unqualified historical-completeness claim.

## Synthetic normalisation examples and test design

All identities and numbers in this section are invented. The examples describe preserved source facts, not an authenticated account or a final executable DTO schema.

```json
{
  "source": "trading212_api",
  "environment": "demo",
  "event_kind": "execution",
  "external_id": "9000000000000001",
  "order_id": "8000000000000001",
  "provider_instrument_id": "SYNTH_US_EQ",
  "executed_at": "2026-10-01T10:00:00Z",
  "side": "BUY",
  "fill_type": "TRADE",
  "quantity": "0.125",
  "price": "12.40",
  "instrument_currency": "USD",
  "economic_booking_state": "awaiting_verified_wallet_semantics"
}
```

A second source fill with ID `9000000000000002` and the **same** order ID must not be removed as a duplicate. Repeated identical fill IDs in the same account/environment/family add evidence without changing economics. A repeated ID with changed economic fields creates a conflict/revision. Different environments/accounts never deduplicate together. CSV aliases are accepted only through verified explicit namespace mappings, never date/amount similarity.

Fixture acceptance must cover integer IDs above JavaScript's exact range, fractional quantities/decimal tokens, two fills under one order, cancelled/partially filled orders, unknown fill kind, null final page, cash string cursor/time query, repeated and malicious cross-origin continuation, failed later page, 401/403 terminal errors, 429 reset plus retry cap, no financial checkpoint advance on incomplete sync, and a position opening date that must not become a quote timestamp.

The holdings fixture family uses the [verified CSV contract](csv-contract.md), invented names/amounts, ticker Slice, Total-row group context, `N/A` dividends and `-` Total quantity. Keep nonadditive dividend controls as controls without forcing a balancing payment. The workbook fixture preserves uncertain July date precision and excludes blank future rows; exact real-source reconciliation stays private.

## Remaining source gates

| Gap | Impact | Permitted work meanwhile |
| --- | --- | --- |
| Actual history export and API/CSV aliases uninspected | Production transaction CSV ingestion and cross-source economic dedupe are not established | Build exact-ID/source-alias primitives and synthetic tests; do not ship a guessed CSV parser |
| Historical range, opening cash/positions, transfers and corporate actions unverified | No complete NAV replay, since-inception returns or unqualified cost basis | Preserve snapshots and coverage metadata; implement durable evidence and explicit unavailable results |
| Fill cash/fee/FX and cash-sign semantics lack real reconciliation | Do not infer cash ledger amounts solely from undocumented signs/field names | Typed read-only adapter can preserve raw facts and report incomplete normalisation |
| Account cash-component additivity not reconciled | No reconstructed NAV from guessed cash sum | Store all broker summary controls separately |
| Calendar coverage and market-provider capability unverified | No production promise of requested freshness/cross-market alignment | Build injectable calendar/market interfaces and fixed-clock tests |

Primary currency has been confirmed as GBP by the owner; connected-account currency still needs validation when credentials are configured privately. Full history has been requested. The original source files stay outside version control and are not modified. Stage 1A foundations and a mocked read-only adapter can proceed under these boundaries; the full Stage 1 import/replay gate still requires its real-source evidence.
