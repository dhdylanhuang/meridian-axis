# Market data, intraday monitoring and daily closes

Status: CONFIRMED polling requirements with ADOPTED correctness resolutions. Requested refresh is near-live monitoring, not a real-time-feed guarantee.

## Provider contracts

Keep broker account sync and market-data refresh separate. A broker position price may support held-instrument monitoring, but unheld benchmarks, FX and historical closes require the market-data adapter. Expose capabilities: batch quotes, history, corporate actions, quote timestamps, reported delay, official-close status and supported symbols. Unsupported capabilities return explicit results, not guessed routes.

Initially use yfinance behind this boundary. Pass adjustment, corporate-action, timezone and repair options explicitly; persist selected basis and provider/library version. Its documented download API has configurable OHLC adjustment and repair behaviour. [yfinance reference](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html)

Free/unofficial prices are labelled as such. A daily provider close may be approved by the app without being an official exchange close. Never upgrade a source's authority through a UI label.

## Data axes

Every quote observation includes instrument/listing, raw price, quote currency/unit, fetched_at, quote_at if supplied, source, reported delay if known, session date, poll ID and status. Store GBP-converted price separately with the exact FX observation/rate and conversion timestamp. Do not reuse the instrument's opening-position timestamp as quote time.

Maintain distinct concepts:

- **Fetch health:** was a request completed recently?
- **Market-data freshness:** how old is the provider's quote, considering disclosed delay?
- **Session status:** open, break, closed, halted/unknown where supported.
- **FX freshness:** quality of the conversion leg.

Price unchanged is not proof of failure; request succeeded is not proof of fresh market data. With no quote timestamp, show fetch age and unknown quote age.

## Polling universe and sessions

Poll nonzero held instruments, VUAG/IWDA benchmark listings and necessary GBP FX pairs only. No closed-position or full-map quote polling. Refresh metadata separately. Batch requests when supported; do not label parallel individual requests as provider batching.

Requested interval is a setting, default **60 seconds** during eligible sessions. The adapter's rate limits/capabilities can impose a slower interval, disclosed to the user. Market-hours rules are exchange-specific with time zone, holidays, half-days, lunch breaks and regular-session boundaries. Extended-hours polling is a separate explicit setting, initially off. Sourced calendar data is cached/versioned; editable overrides are audited with dates and reasons.

FX uses its own session/provider policy and may remain relevant while an underlying listing is closed. Stop that instrument's quote polling outside its session, but do not label its GBP valuation frozen if FX continues moving. A closed instrument shows its last selected close, source and session date; before a new close exists, show the last quote as provisional rather than claiming it is the close.

## Worker lifecycle

One scheduler owner runs inside the local FastAPI process. Use lifespan startup/shutdown and a bounded executor for blocking calls. No job overlaps itself. Manual refresh shares job state and provider rate budgets; it does not bypass them. One app worker is the supported initial deployment.

Each cycle: snapshot the eligible universe/calendar → fetch price/FX outside DB transactions → validate/normalise observations → commit short writes and the poll result → compute eligible live valuation/alerts → publish committed changes. A partial batch retains last-good data for failed symbols, shows mixed as-of/coverage, and never silently converts failed responses to zero.

A process crash cannot leave a cycle forever trusted as running: startup marks abandoned runs and backfills daily source data. When the local application is closed, it does not poll. Catch-up cannot reconstruct missed intraday ticks; disclose gaps. Cancel pending waits on shutdown and close clients/executors cleanly. No database transaction spans a sleep, network call or rate-limit wait.

## Storage and retention

Store every successful eligible observation in `intraday_prices` with its poll ID. Default retention **90 days**, configurable. Retain approved daily closes indefinitely. Retention cleanup must preserve daily-selection and alert evidence: retain the selected source observation in a durable daily record or archive the referenced data before deleting short-lived rows.

Every polling cycle, including failures, writes `import_log` with `operation_type=price_poll`, start/end, success/failure counts, source and redacted error. Treat a cycle as one poll run; observations link to it. Keep default import-history views focused on financial imports, with polling operations separately filterable. Configure log retention separately from immutable financial audit; record cleanup outcomes without recursively auditing every deleted tick.

## Session-close selection

At a session end, a final eligible quote can create a daily candidate with source `eod_poll`, quote/fetch time and `quality=provisional`. Candidate quality depends on its proximity to the session end and FX coverage. A morning quote after an afternoon outage is not a credible closing candidate. The allowable age is a validated setting, with no candidate selected if coverage fails.

Fetch the daily provider's observation for **that same trading session** after it becomes available, including startup catch-up. Compare compatible listing, currency, price units, split/adjustment basis and date. If `abs(candidate − daily_close)/abs(daily_close) > 0.005`, log a discrepancy; zero/missing denominator is a separate data error. This is the owner's 0.5% reconciliation requirement.

Retain both observations and mark selection/revision instead of destructive replacement. Call it an official close only if the provider supports that authority. Recompute affected approved valuations/analytics and preserve revision links. Risk/correlation consume only the approved daily selection; the provisional candidate is excluded by default. Provisional dashboards remain available with quality flags.

Daily portfolio valuation cutoff must be explicit: use the latest eligible instrument session close and FX as of a recorded portfolio cutoff, preserving asynchronous-market ages. Never imply a simultaneous global close. See Q13 for final calendar/cutoff selection.

## Backoff and failures

Use exponential backoff with jitter for retryable failures, cap the exponential component at **15 minutes**, and honour any later provider reset/Retry-After time. A successful call resets the consecutive-failure counter. Authentication/permission/schema errors are actionable failures, not endless retries. Backoff is per failing provider/job so one source does not unnecessarily disable another.

After a configurable consecutive-failure threshold, show a persistent AXIS banner with source, last success and safe reason. Preserve last-good values and their ages. A missing mapping, invalid price, unavailable FX and transport error are distinct states.

During an open session, the requested stale threshold is **2× configured polling interval**. Apply it to refresh health and, where known, quote age/delay separately; a larger provider-imposed interval is shown explicitly. Do not reset quote freshness by changing only fetched_at. Daily close freshness uses the instrument's expected trading sessions and warns after more than one trading day, not after a fixed 24 hours.

## UI stream and alerts

Use authenticated SSE for both users. Send a snapshot version, changed values and quality changes. Include periodic heartbeat/refresh-health information even when prices are unchanged. Reconnect always triggers an authoritative snapshot fetch; a lost delta cannot permanently corrupt the display.

Daily-move alerts compare a compatible current quote with the prior approved session close. Live weight/drawdown alerts use a clearly labelled intraday GBP valuation and its coverage. They never overwrite end-of-day alert basis or risk data. Threshold-crossing persistence is defined in [alerts](alerts.md).

## Tests

Use fixed clocks and mocked adapters: regular session, DST boundary, holiday, half-day, Asian lunch break, FX-only open period; held-only scope; batch limits; failure preserves last good; successful unchanged quote updates fetch health; unknown quote time disclosed; cap and provider-reset precedence; duplicate-worker protection; shutdown cancellation; no DB transaction across waits; missed-session backfill; provisional close excluded from risk; same-session 0.5% comparison; SSE reconnect/snapshot and both sessions; retention preserves referenced closing evidence.
