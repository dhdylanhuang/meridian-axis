# Archived integration and polling amendment

Source: the owner's later message, 11 November 2026. Markdown escaping has been normalised. This records the request rather than an implementation. Use the active [integration](../trading212-integration.md), [polling](../market-data-and-polling.md) and [decision](../decisions-and-questions.md) contracts for resolutions of ambiguous wording, especially cost-basis inputs, closing-price selection and alert re-arming.

## Trading 212 integration

- Primary source: Trading 212 Public API (v0). Use the OpenAPI spec at https://docs.trading212.com/_bundle/api.yaml to confirm endpoints and schemas before writing any client code. Do not guess endpoint paths.
- Environments: configurable base URL, Demo by default. Live is enabled only by an explicit setting.
- Auth: API key and secret stored in environment variables, sent as HTTP Basic. Never log or display them.
- Client module: a single adapter with methods for account summary, positions, order history and transaction history, with cursor pagination and retry with backoff. Mock the HTTP layer in tests.
- Sync: scheduled and manual. Each sync is logged to import_log with the same deduplication on Trading 212 transaction IDs used for CSV imports.
- CSV import remains supported as a fallback and as the only source for any field the API does not return (confirm which fields, including Slice labels, in Stage 1 and list them in the README).
- This app is read-only. Do not implement order placement.

## Live price polling

Purpose: show near-live prices and intraday P&L on AXIS, HOLDINGS and GROUPS during market hours. Risk, correlation and cost-basis calculations continue to use daily closes only.

### Polling scope

- Poll only instruments with a non-zero position, plus the benchmarks (VUAG, IWDA) and the GBP FX pairs needed for valuation. Do not poll closed positions or the full ticker map.
- Batch symbols into one request per polling cycle where the adapter supports it.

### Schedule

- Polling interval is a setting. Default 60 seconds during market hours.
- Each instrument is polled only while its own exchange is open. Keep a market hours calendar per exchange (including the London, US, and Asian sessions), with holidays, stored in settings and editable.
- Outside market hours, stop polling and show the last close with its timestamp.
- Run polling in a background worker (for example APScheduler) inside the FastAPI process. It must not block request handling.

### Storage

- Store each poll in an intraday_prices table: instrument, timestamp, price, currency, source, and a poll_id. Keep the raw price in the listing currency and the GBP-converted value separately.
- At the end of each trading day, write one daily close to prices, taken from the last successful poll of the session, and mark it with source = "eod_poll" or replace it with the official close when the adapter provides one.
- Retain intraday data for a configurable period (default 90 days). Daily closes are kept indefinitely.
- Every poll is logged to import_log, including failed polls, with the error.

### Delivery to the UI

- Push updates to the frontend over Server-Sent Events (preferred for a single-user app) or WebSocket. Send only changed values.
- Show on every price: the time of last update, a delayed/stale indicator, and the source name.
- Mark a price as stale when it is older than 2x the polling interval during market hours, and show a stale count on AXIS.

### Alerts on live data

- Daily move alerts are evaluated on each poll against the previous close.
- Drawdown and weight alerts are evaluated on each poll using the live GBP valuation. Mark them as intraday in the alert record, so they are not confused with end-of-day figures.
- Alerts fire once per threshold crossing per session. Re-arm when the value returns inside the threshold. Do not send repeated notifications for the same condition.

### Failure handling

- Exponential backoff on errors or rate limits, capped at 15 minutes.
- After repeated failures, show a banner on AXIS and keep the last good prices. Never display a zero or blank price as a real value.
- The polling worker must stop cleanly on shutdown and must not hold a database transaction open between polls.

### Honesty about data

- Free sources are delayed or unofficial. The UI must show the delay where the adapter reports it, and never label yfinance data as real-time.
- Reconcile the final daily close against the next day's official close where available, and log any difference above 0.5%.

### Tests

- Polling respects market hours using a fixed clock, including a holiday and a half-day session.
- Backoff sequence is correct and capped.
- A failed poll does not overwrite the last good price.
- Alert re-arms after the value returns inside the threshold.
- Intraday data is excluded from the risk and correlation inputs.
- Live polling tests use a mocked adapter, not the network.
