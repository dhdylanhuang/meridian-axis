# Market data, intraday monitoring and daily closes

Status: CONFIRMED polling requirements with ADOPTED correctness resolutions. The owner-approved Cloudflare + Supabase target replaces the resident polling process with bounded scheduled work; see [ADR 0001](decisions/0001-cloudflare-supabase.md). No hosted polling capability is implemented or verified yet. Requested refresh remains near-live monitoring, not a real-time-feed guarantee.

## Provider contracts

Keep broker account sync and market-data refresh separate. A broker position price may support held-instrument monitoring, but unheld benchmarks, FX and historical closes require the market-data adapter. Expose capabilities: batch quotes, history, corporate actions, quote timestamps, reported delay, official-close status and supported symbols. Unsupported capabilities return explicit results, not guessed routes.

The initial market-adapter candidate remains yfinance behind this boundary. Its Worker dependency/runtime suitability and provider access must pass qualification; ordinary CPython compatibility does not establish that. A substitute provider needs a recorded field/capability contract rather than guessed endpoints or a hidden freshness reduction. Pass adjustment, corporate-action, timezone and repair options explicitly; persist selected basis and provider/library version. Its documented download API has configurable OHLC adjustment and repair behaviour. [yfinance reference](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html)

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

**Production target:** one scheduling authority invokes bounded work, either a Cloudflare scheduled entry point or Supabase Cron invoking a protected endpoint, selected through the early hosting spike. Do not run both for the same job family. The prior local FastAPI/APScheduler singleton design is superseded for hosting; no continuously running thread, process or in-memory timer is assumed. Manual refresh shares persisted job/rate state and never bypasses it.

Each job has a deterministic scope/cycle identity, status, lease owner/expiry, attempt count, retry-not-before and committed checkpoint in Postgres. Claim work atomically. A lease has a bounded expiry and generation/fencing check so a stale owner cannot commit after takeover. One active logical cycle is permitted per account/job family; duplicate scheduled deliveries and retried commits must not duplicate observations, alerts or financial effects. Exactly-once delivery is not assumed.

Each cycle: snapshot the eligible universe/calendar → fetch price/FX outside DB transactions → validate/normalise observations → commit short writes and the poll result → compute eligible live valuation/alerts → publish committed changes. A partial batch retains last-good data for failed symbols, shows mixed as-of/coverage, and never silently converts failed responses to zero.

The invocation does only the bounded pages/symbol batches supported by its measured wall-clock, CPU and subrequest budget, then records progress and returns. Persist a retry/continuation time rather than waiting for the next poll or a long backoff inside the Worker. An expired lease is recoverable by a later invocation; an abrupt termination cannot leave a job permanently trusted as running. Close clients when possible, but correctness does not depend on a shutdown callback. No database transaction spans network I/O, a sleep or a rate-limit wait.

Hosted dispatch can continue while the browser is closed if the selected services are active; free-plan pause, quota and provider outages can interrupt it. Detect missed cycles and backfill eligible daily data on recovery. Catch-up cannot recreate missed intraday ticks or retroactively promise continuous alerts. Preserve gaps and monitor scheduler last-success separately from a user's browser session. The offline foundation does not provide an always-on hosted scheduler.

Requested intervals must be supported by the chosen trigger and measured provider budget. The default is still 60 seconds; do not advertise a configurable faster interval that the deployed scheduling mechanism cannot honor. [Supabase Cron scheduling](https://supabase.com/docs/guides/cron), [Cloudflare Worker limits](https://developers.cloudflare.com/workers/platform/limits/)

## Storage and retention

Preserve every successful eligible observation in the logical `intraday_prices` history with its poll ID. Default retention remains **90 days**, configurable; approved daily closes are indefinite. Supabase Free's database budget must be measured against expected scope, indexes and provenance before production. The [hosting capacity example](hosting-options.md) shows why a naive row-per-quote 90-day table may not fit; it is synthetic sizing, not a measured account allocation.

If storage measurements require it, keep recent observations in Postgres and move older immutable day/session blocks to encrypted, private, lossless archives with manifests and authorized retrieval. This physical design is conditional on a tested size/egress budget, exact round-trip precision, date-range queries, key recovery and independent backup. Preserve instrument, raw and GBP prices, timestamps, source, currency/unit, FX provenance, poll ID and quality. Do not declare the history available if only an unreadable archive exists, and do not silently shorten retention or reduce sampling to fit a free quota. A scope reduction requires the owner's explicit decision.

Retention cleanup preserves daily-selection and alert evidence beyond tick expiry: retain the selected source facts in a durable daily/alert record or independently backed-up evidence archive. Publish an archive manifest only after verifying its complete write/checksum and read-back; remove hot rows only after durable references and retrieval are proven. Daily risk inputs remain approved daily selections, never reconstructed from arbitrary archived intraday points.

Every polling cycle, including failures, writes `import_log` with `operation_type=price_poll`, start/end, success/failure counts, source and redacted error. Treat a cycle as one poll run; observations link to it. Keep default import-history views focused on financial imports, with polling operations separately filterable. Configure log retention separately from immutable financial audit; record cleanup outcomes without recursively auditing every deleted tick.

## Session-close selection

At a session end, a final eligible quote can create a daily candidate with source `eod_poll`, quote/fetch time and `quality=provisional`. Candidate quality depends on its proximity to the session end and FX coverage. A morning quote after an afternoon outage is not a credible closing candidate. The allowable age is a validated setting, with no candidate selected if coverage fails.

Fetch the daily provider's observation for **that same trading session** after it becomes available, including startup catch-up. Compare compatible listing, currency, price units, split/adjustment basis and date. If `abs(candidate − daily_close)/abs(daily_close) > 0.005`, log a discrepancy; zero/missing denominator is a separate data error. This is the owner's 0.5% reconciliation requirement.

Retain both observations and mark selection/revision instead of destructive replacement. Call it an official close only if the provider supports that authority. Recompute affected approved valuations/analytics and preserve revision links. Risk/correlation consume only the approved daily selection; the provisional candidate is excluded by default. Provisional dashboards remain available with quality flags.

Daily portfolio valuation cutoff must be explicit: use the latest eligible instrument session close and FX as of a recorded portfolio cutoff, preserving asynchronous-market ages. Never imply a simultaneous global close. See Q13 for final calendar/cutoff selection.

## Backoff and failures

Use exponential backoff with jitter for retryable failures, cap the exponential component at **15 minutes**, and honor any later provider reset/Retry-After time. Store failure count, next eligible request time and provider/endpoint rate-reset state durably; atomically reserve shared request budgets across Worker instances and manual/scheduled callers. Return the invocation when work is not yet eligible rather than sleeping until reset. The current offline broker client's in-process pacing/retry state is not this production coordination mechanism.

A successful call resets the appropriate consecutive-failure counter. Authentication/permission/schema errors are actionable failures, not endless retries. Backoff is per failing provider/job so one source does not unnecessarily disable another. Persist only safe error categories/statuses; credentials, headers and raw upstream error bodies never enter the operation log.

After a configurable consecutive-failure threshold, show a persistent AXIS banner with source, last success and safe reason. Preserve last-good values and their ages. A missing mapping, invalid price, unavailable FX and transport error are distinct states.

During an open session, the requested stale threshold is **2× configured polling interval**. Apply it to refresh health and, where known, quote age/delay separately; a larger provider-imposed interval is shown explicitly. Do not reset quote freshness by changing only fetched_at. Daily close freshness uses the instrument's expected trading sessions and warns after more than one trading day, not after a fixed 24 hours.

## UI stream and alerts

Authenticated SSE remains preferred, but its Worker lifecycle, session expiry and reconnection behavior must be tested before selecting a hosted implementation. Authorized private Supabase Realtime can be adopted after an explicit implementation decision if it better fits measured free-runtime limits. It is a transport alternative, not permission for a public channel or a parallel source of truth.

Send a snapshot version, changed values and quality changes; batch cycle-level deltas rather than emitting one database-row notification per instrument to every client. Include heartbeat/refresh-health information even when prices are unchanged. Apply the approved-membership boundary to both users, revoke expired/removed access and test anonymous/nonmember denial. Reconnect fetches an authoritative snapshot; a lost delta cannot permanently corrupt the display. Measure messages/second, monthly delivery and egress with both users; no assumption that low user count alone guarantees quota fit.

Daily-move alerts compare a compatible current quote with the prior approved session close. Live weight/drawdown alerts use a clearly labelled intraday GBP valuation and its coverage. They never overwrite end-of-day alert basis or risk data. Threshold-crossing persistence is defined in [alerts](alerts.md).

## Tests

Use fixed clocks and mocked adapters: regular session, DST boundary, holiday, half-day, Asian lunch break, FX-only open period; held-only scope; batch limits; failure preserves last good; successful unchanged quote updates fetch health; unknown quote time disclosed; cap and later provider reset survive process replacement; concurrent/manual dispatch shares rate budgets; duplicate delivery and expired-lease takeover cannot duplicate effects; a stale owner cannot commit; no DB transaction across external waits; missed-session backfill; provisional close excluded from risk; same-session 0.5% comparison; authenticated stream reconnect/snapshot for both sessions and denial for anonymous/nonmembers; retention preserves referenced closing evidence.

The early hosted feasibility gate additionally requires representative CPU/memory measurements, Postgres lease/idempotency tests, quota-aware batch delivery and a lossless 90-day retention/restore sizing result. Archive tests cover precision, corrupt/incomplete blobs, atomic manifest publication, unauthorized access and key recovery. These are required evidence, not tests claimed to exist today.

## Broker-refresh implementation — 13 November 2026

The pending `0007` runtime uses one private Python Durable Object authority reached by a minute Cron trigger or the existing session-checked manual route. Task leases and endpoint reservations are stored in PostgreSQL. Manual dispatch persists a Durable Object alarm and acknowledges promptly, keeping broker waits outside the session object’s serialised request lock. The alarm and Cron share the PostgreSQL task leases and endpoint reservations. Provider calls, retries and user authorization hold no financial transaction open. Each hosted request makes one HTTP attempt, then persists retry eligibility and returns. Exponential jitter caps at 15 minutes and later provider reset/Retry-After deadlines remain in shared endpoint state. Authentication, permission and schema failures stop for administrative correction.

Summary/positions refresh has a 60-second target and minute-aligned next eligibility. Metadata refresh is daily. Its retained evidence is explicitly scoped to held listing rows and their matching working schedules. The full discovery catalogue is fetched for selection and does not create repeated daily catalogue copies. History families have separate jobs and an hourly complete-traversal target. Broker schedule instants cover regular sessions, breaks and explicit closure intervals only when they bracket the current instant. Held listings with missing mappings, expired metadata or missing schedule coverage produce `unknown` and allow conservative polling. This default may poll outside sessions while coverage is unknown.

The private UI exposes authenticated manual broker refresh, health and periodic saved-snapshot retrieval. It retains last successful figures after a failed reload and clears private fields on session denial. Browser delivery currently uses a 60-second authenticated pull. SSE remains open. Actual deployed cadence, free capacity/retention and recovery require hosted verification. Retrieval success never establishes a fresh market quote timestamp.

Private source sizing indicates that 90 days of full refresh evidence and projections can exceed or severely pressure the free PostgreSQL allowance before index/audit/history overhead. A current aggregate database baseline is recorded privately. Long-term retention and lossless archive/restore qualification remain open. No observations are discarded or sampled to meet the budget.
