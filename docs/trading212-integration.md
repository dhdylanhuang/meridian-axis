# Trading 212 integration contract

Status, **13 November 2026:** API-first requirements and the verified provider contract underpin deployed read-only snapshot refresh. The YAML was initially verified on 11 November and rechecked unchanged for the refresh delivery. Current AXIS/HOLDINGS and shared scheduled/manual coordination are deployed. History observations/revisions are persisted by bounded jobs. Normalized ledger economics, lifetime completeness and CSV aliases remain open. [Current status](status-and-handoff.md) owns verification evidence.

## Verify before implementing

The owner specified [OpenAPI YAML](https://docs.trading212.com/_bundle/api.yaml) as the client contract. On 11 November 2026, the YAML and [official linked JSON](https://docs.trading212.com/_bundle/api.json?download=) were downloaded directly, parsed and found structurally identical: OpenAPI 3.0.1, API v0, 17 paths and 38 schemas. **The direct YAML prerequisite is verified.** Public source hashes, field matrix, exact request/query contracts and remaining real-history gaps are in [Stage 0 verification](stage-0-source-verification.md). Earlier browser MIME failures did not establish source verification; the subsequent direct download did. Recheck the bundle when changing the client contract.

Use the configured origin and the path from the verified specification exactly once. The documented origin is `https://demo.trading212.com` or `https://live.trading212.com`; paths include `/api/v0`. Do not concatenate `/api/v0` twice. Demo is the default. Live requires an explicit validated setting and clearly visible environment label. Separate accounts, state, evidence and checkpoints across environments.

## Confirmed coverage

| Capability | Documented request | Normalised use |
| --- | --- | --- |
| Account summary | `GET /api/v0/equity/account/summary` | Broker account/cash/value reconciliation |
| Current positions | `GET /api/v0/equity/positions` | Observed holdings and current position prices |
| Historical orders/fills | `GET /api/v0/equity/history/orders` | Execution and corporate-action evidence |
| Paid dividends | `GET /api/v0/equity/history/dividends` | Dividend-event evidence |
| Cash history | `GET /api/v0/equity/history/transactions` | Deposits, withdrawals and other supported cash events |
| Instrument metadata | `GET /api/v0/equity/metadata/instruments` | Listing identity and currency mapping |
| Exchange metadata | `GET /api/v0/equity/metadata/exchanges` | Working-schedule evidence |

See [official specification](https://docs.trading212.com/_bundle/api.json?download=) for paths. Metadata listing is a cached discovery job, not part of every quote cycle. No dedicated quote/history-price/FX endpoint was found in the reviewed specification. The broker adapter therefore does not promise an unheld benchmark or FX feed.

## Adapter boundary

Expose account summary, positions, order history, dividend history, cash-transaction history, instrument metadata and exchange schedules. Each method returns typed normalised data plus source/run/coverage metadata. HTTP parsing is private to this adapter; calculation modules do not consume provider JSON.

Methods must distinguish a complete empty response from an error, an incomplete paginated result and an unsupported capability. Preserve original event identifiers and raw numeric strings before normalisation. A successful positions response does not establish complete historical coverage.

## Credentials, transport and permissions

HTTP Basic uses the key as username and secret as password, sent only over HTTPS to the validated provider origin. Credentials come from environment variables and never reach React, local URLs, error messages, fixtures, audit JSON or request logs. Disable/redact HTTP tracing of Authorization. Allow only the specific read requests above. No order placement, modification, cancellation or pie mutations.

Use keys with the required read permissions and no trading permissions. The initial account types supported by the provider are Invest and Stocks ISA. The owner confirms one Stocks and Shares ISA; verify that connected identity and primary currency during setup. Initial tax features are deferred. [Official authentication/environment documentation](https://docs.trading212.com/api)

## History is not one generic transaction feed

- Historical orders include an order and a fill, each with its own ID. Normalise executed fill quantity/price, not requested order quantity. Retain partially filled/cancelled status and supported corporate-action kinds. Unknown fill types are quarantined with a visible completeness warning. The documented historical-order limit is 20 requests/minute, up to 50 results per page. [Orders contract](https://docs.trading212.com/api/historical-events/orders_1.md)
- Dividends use a `reference`, payment date and currency-specific amount fields. Preserve gross/net semantics only when established; do not infer withholding as zero from an absent field. This is a separate history family. [Dividend contract](https://docs.trading212.com/api/historical-events/dividends.md)
- Cash history uses a `reference` and includes deposits, withdrawals, fees, transfers, free-cash interest and lending interest. It does not replace fill or dividend history. [Cash-history contract](https://docs.trading212.com/api/historical-events/transactions.md)

Candidate identity is `(broker, environment, account, event_kind, external_id)`: fill ID for executions and reference for dividend/cash events. Confirm uniqueness and CSV equivalence using real samples. Store ID aliases where a CSV uses a different namespace. Never fuzzy-merge two same-day equal-amount trades automatically. Unknown matches become review items, not duplicate economic entries or guessed deletions.

## Pagination and resilient sync

Follow returned `nextPagePath` until null for paginated histories. Validate it resolves to the same allowlisted origin and the same history-family route before attaching credentials; do not follow cross-origin redirects. Detect repeated cursors/paths and cap pages/time to avoid infinite loops. Persist a checkpoint only with the accepted financial generation. The bundle prose defines null termination despite a string-only component schema; missing/malformed page fields are not an empty success.

Orders/dividends use int64 cursors with optional ticker and limit; cash history uses a string cursor with optional date-time `time` and limit. Limits default to 20 with maximum 50. Preserve the entire continuation query rather than reconstructing it or inventing unverified date filters. Account summary is limited to 1 request/5 seconds, positions 1/second, each history 20/minute, instruments 1/50 seconds and exchanges 1/30 seconds.

Use per-endpoint/account pacing shared by scheduled sync, manual sync and position reads. Respect provider reset headers; introduce bounded exponential backoff with jitter for transient transport/5xx/429 failures. Do not retry invalid credentials, missing permission or invalid request arguments indefinitely. A cap on exponential delay never permits retrying before a later provider reset. The provider documents per-account limits and `x-ratelimit-*` headers. [Rate limiting and pagination](https://docs.trading212.com/api)

Use a small configurable overlap on incremental historical retrieval and deduplicate. Where the API offers no verified time filter, traverse its supported pagination; do not invent query parameters or assume IDs sort by execution time. Store history-family watermarks separately. Handle late records, corrected fields and out-of-order timestamps explicitly.

Fetch all required history pages into staging outside the financial write transaction. Validate, normalise and reconcile. Commit a coherent generation plus audit and checkpoints together. A failed later page must not expose a new partial ledger as complete. Jobs are retryable and a resumed job cannot double count accepted events. Positions/account summary sampled at different times have bounded reconciliation tolerances and snapshot timestamps; do not claim provider-wide atomicity.

## Position prices and missing fields

Verify account-summary cash components against actual statements before treating them as additive. Funds available to trade, funds associated with groups/pies and reserved amounts may have overlapping meanings. Preserve provider components for reconciliation; do not invent NAV by summing every field containing the word cash. Likewise, a wallet-impact value already in primary currency must not receive a second FX conversion.

Position `currentPrice` is in instrument currency. The documented response does not provide a market quote timestamp or delay; `createdAt` refers to the position, not a quote. Label these observations with retrieval time and unknown quote age. The positions endpoint documents a 1 request/second limit; the app's proposed interval is much slower. [Positions contract](https://docs.trading212.com/api/positions/getpositions.md)

The [Stage 0 verification](stage-0-source-verification.md) publishes a schema/field-coverage matrix without real balances or identifiers. It also records unresolved fill-wallet signs/FX/charge semantics and account cash additivity: preserve those facts without guessing ledger economics. One [holdings snapshot format](csv-contract.md) is verified; transaction-history export matching remains unverified. Present evidence:

| Field | Current evidence | Required policy |
| --- | --- | --- |
| Raw CSV Slice | Not supplied by reviewed position/history contracts; snapshot Slice is ticker | Preserve raw Slice as identity evidence; Total-row Name supplies group context |
| Group context | Inspected CSV Total-row Name identifies the exported group | Preserve metadata without importing Total as a holding; no pie-domain objects |
| Original listing identity | Broker identifiers and metadata available | Verify exact listing and mapping; never guess yfinance suffix |
| Current prices | Held-position price available | Retrieval-time disclosure; separate general market provider |
| Historic close, FX history, benchmark prices | No dedicated route identified | Separate market-data adapter |
| Full multi-currency cash/account detail | General provider limitations apply | Establish response coverage before claiming reconstructed NAV |
| Look-through holdings / revenue currencies | Not established | Evidence-backed external data or explicit unavailable result |

## Required evidence before Live use

Mocked contract tests pass; credentials are redacted; Demo/Live isolation is verified; all history families reconcile on fixtures; CSV aliases are documented; account wrapper and coverage are known; backups restore; a positions mismatch produces a visible exception. Enabling Live reads does not enable broker trading.

## Implemented adapter checkpoint

`backend/src/meridian/adapters/trading212.py` implements the seven typed read methods using the verified YAML. Offline fixtures cover exact Decimal decoding/string IDs, distinct fills under one order, complete pagination, same-family/origin restrictions, redirects, bounded retries/pacing, terminal authentication failures, and strict duplicate-key/nonfinite JSON rejection. **39 contract tests pass**. DTOs are observations with private raw payloads, not a ledger or browser response schema. Standalone client instances pace locally. The hosted driver injects PostgreSQL reservation/response callbacks so scheduled and manual work share account/endpoint budgets across instances.

The adapter checkpoint verifies observation parsing. The later hosted driver supplies persisted task leases, endpoint budgets, bounded page checkpoints and source retrieval context. Economic normalization, CSV aliases and cash replay remain open. Position opening time supplies no market quote timestamp. The one-off capture procedure below remains a separate qualification tool.

## One-off connection and coverage capture

`python -m meridian.broker_capture` performed the original local connection qualification after the initial [recovery drill](hosted-recovery.md). It remains available for separately bounded diagnostics. The owner selected **local process environment variables** for credential provisioning. It uses one existing read-only client for account summary, positions, all three histories, instruments and exchanges; a 300-second total deadline and 100-page/180-second per-family bounds fail safely rather than accepting partial history. Do not run another reader for the same account concurrently: this one-off command does not implement cross-process/account-wide durable rate coordination.

Create an API key on the intended ISA with the required read permissions and no order/trading mutation permissions. Inspect the actual broker permission labels in its current UI; do not infer a role from a successful summary call. There is no API method here that can certify all permissions granted to the key. Keep the pair out of chat, source files and shell history. The command reads `MERIDIAN_BROKER_API_KEY` and `MERIDIAN_BROKER_API_SECRET` from **its own process environment**. Variables exported in a separate terminal do not update an already running agent's environment. `.env` files are not loaded.

Run from the repository root in the same shell where those variables are securely configured (the example requires the already-created private recovery key):

```sh
backend/.venv/bin/python -m meridian.broker_capture \
  --environment live \
  --key-file private/recovery-keys/recovery-v1.key \
  private/runtime/trading212-live-observations.meridian
```

Alternatively append `--prompt-credentials` in an interactive terminal; both key and secret are entered with hidden prompts and kept in process memory. A terminal is required, so `getpass` cannot fall back to echoing input through a pipe. Demo is the default; Live requires the explicit flag above. No credential values belong in command arguments.

All seven families must succeed before a new encrypted file is created. The output records environment, raw parsed payloads with exact Decimal strings, per-family start/end retrieval timestamps and completed traversals. A complete API traversal is **not proof of lifetime account history**. The summary schema cannot verify ISA wrapper; that remains owner-confirmed until evidence establishes the connected account. Non-GBP summary is rejected. Separate requests are not an atomic broker snapshot, and current position quote age remains unknown.

Only safe status/environment/family-completeness output reaches the terminal; it contains no balances, holdings, identifiers or credentials. Output is exclusive AES-GCM encrypted evidence using the separately protected key. This is not a hosted database import, alias reconciliation, derived cash/quantity ledger, scheduler, checkpoint or financial screen. After capture, privately compare identity/history/position evidence with inspected statements before admitting economic events. The owner subsequently ran the hidden-prompt command successfully; the encrypted live capture was independently authenticated and inspected locally. All seven families are present and the summary currency is GBP. Initial signed-fill quantity controls match positions when split/scrip changes are retained, while position-wallet value versus account-summary investments reconciliation remains open. That checkpoint established the local connection. Later hosted snapshot/refresh acceptance is recorded in current status. Exact data and diagnostic controls remain private.

## Durable evidence checkpoint — 12 November 2026

Source `19f4809` accepts complete captured observations into existing closed hosted evidence tables, with account/environment validation, explicitly verified initial broker-reference binding, canonical capture deduplication and atomic source/audit completion. The real capture was accepted after validation CI; independent read-back reproduced its full canonical hash and identical broker snapshot projection, and a replay added no sources. Exact data/identifiers remain private. Economic events added are zero. That checkpoint established durable evidence only. Subsequent snapshot and ongoing-refresh deployments are recorded in current status. A normalized economic ledger remains open.

The owner clarified that Trading 212 reported figures are authoritative for this first snapshot. Use account summary totals/cash and position wallet values/cost/PnL directly, preserving timestamps and missing fields. Do not substitute reconstructed sums or make full ledger reconciliation a gate for that snapshot. The account identifier is independently linked to the provided statement's ISA section; the owner confirms a cash-funded start with no earlier holdings/transfers. Calculated historical performance remains separate and unavailable until supported.

## Deployed ongoing refresh — 13 November 2026

`application/broker_sync.py` accepts version-2 summary/positions evidence and publishes a complete approved projection atomically. `application/broker_jobs.py` owns PostgreSQL leases and shared endpoint reservations. `security/hosted_sync.py` assembles the restricted writer, session-aware polling, daily held-listing metadata and bounded history traversal. Cron runs in the JavaScript gateway, and authenticated manual requests queue the same sync object through a durable alarm. Broker credentials are managed bindings on the private sync Worker.

Each history family advances one page per invocation. Its next eligibility uses a one-hour cooldown anchored to the successful final-page attempt. The cadence can exceed an hour while pagination or retries continue. Complete acceptance appends fill/reference revisions. Corporate-action facts retain review quality states. Lifetime completeness and normalized economics require separate evidence. See [imports](imports-and-reconciliation.md#ongoing-sync-implementation--13-november-2026) and [current status](status-and-handoff.md).
