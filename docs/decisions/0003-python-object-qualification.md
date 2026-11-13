# ADR 0003 - Python object runtime qualification

- Date: **11 November 2026**.
- Status: **ADOPTED runtime direction** on 11 November 2026, subsequently deployed for session/snapshot/broker-refresh scope by 13 November. General analytics and full capacity/recovery acceptance remain open.
- Owner/reviewer: orchestrator and delegated runtime reviewers.
- Requirements/questions: P02, QA01/QA02, Q17/Q18; depends on ADR 0001 and ADR 0002.

## Problem and evidence

The deployed synthetic Python/FastAPI Worker returns correct responses, but measured full-probe CPU exceeds the documented ordinary Free request budget. A native Python fetch control running the same functions also exceeds it. Removing ASGI alone therefore does not qualify this workload. Exact source commits, provider versions and timing samples live in [Worker feasibility](../worker-feasibility.md).

A separately deployed JavaScript gateway calling the same FastAPI app inside a Python Durable Object passed three synthetic response checks. Its provider traces distinguish stateless gateway execution from object execution, with the gateway reporting 0 ms CPU at the exposed measurement precision. The original synthetic probe object performed no storage calls. This gives a concrete candidate for retaining Python while continuing the approved Cloudflare/Supabase architecture.

## Decision

Use the gateway/Python-object path. The initial synthetic qualification progressed to the deployed private session and broker-refresh runtime. Do not promote the ordinary Python HTTP Worker to the application runtime based on its successful responses. Keep the separately named controls distinct from the application and from each other.

The gateway owns routing/transport only. Authoritative financial calculations remain Python modules; the experiment is not permission to recreate them in JavaScript. Supabase remains application persistence, including durable leases, accepted checkpoints, sessions and audit. An object instance or its in-memory state does not establish job ownership, transaction correctness or durable financial state.

The SQLite-backed namespace is provider runtime infrastructure for Free eligibility. Neither the experiment nor this decision adds a second application database or changes Supabase's native SQL migration authority. Any future decision to store application data in an object requires a separate review.

## Alternatives and tradeoffs

- Ordinary Python HTTP handler: compatible but the measured workload remains above its documented Free CPU budget.
- Native Python handler: isolates ASGI overhead; measured full-probe CPU still exceeds the ordinary budget.
- Python object behind a small gateway: preserves the language and measured workload with a separately documented object budget, but adds an internal hop, object lifecycle/concurrency and daily-duration constraints that require measurement.
- Paid compute or a backend language change: outside the current free-services constraint or original language-preservation preference; neither is selected.

## Consequences and remaining gates

The public synthetic gateway intentionally strips caller headers/body/query. It is **not** the production Auth/session boundary and must not be attached to financial credentials. A protected database diagnostic needs a separate least-privilege connection and explicit authentication before any credential is bound.

The original production-qualification gates required verification of actual account Free eligibility/quotas, object lifetime and aggregate daily duration, memory, representative analytics, external provider behavior, request-scoped database commit/rollback, authorization-context isolation, two-member Auth/CSRF, job fencing, retention capacity and independent restore. Successful synthetic traces are not the whole Stage 0H gate. The provider's CPU allowance and burst behavior must be interpreted from current documentation and actual outcomes rather than inferred from HTTP 200 alone.

No Supabase schema or application-data backfill was included in the original runtime experiment. [Architecture](../architecture.md), [current handoff](../status-and-handoff.md) and the requirement/question register consume this direction.

## Deployed progression — 13 November 2026

The JavaScript gateway dispatches HTTP session work and minute Cron signals to Python Durable Objects. Session-checked manual refresh reaches the same sync object. Its alarm persists a wake-up time so broker waits release the session request lock. Supabase continues to own financial evidence, leases, rate state, checkpoints, sessions and audit. Actual deployed snapshot/refresh evidence is recorded in [current status](../status-and-handoff.md). This acceptance covers that bounded workload. Future analytics, 90-day capacity and expanded recovery require their own measurements.
