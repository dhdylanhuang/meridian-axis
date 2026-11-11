# ADR 0001 - Cloudflare and Supabase production target

- Date: **11 November 2026**.
- Status: **ACCEPTED owner platform decision**. Runtime, Auth transport, storage layout and production implementation remain subject to measured qualification.
- Decision owner: project owner; implementation and review: orchestrator and assigned contributors.
- Related requirements: P01/P02/P03, D01-D05, L01-L05, S01/S02, O01; source gaps Q01-Q03 and market-data questions Q13/Q14 remain separate.
- Authoritative consumers: [architecture](../architecture.md), [security and operations](../security-and-operations.md), [polling](../market-data-and-polling.md), [development stages](../development-stages.md), [current handoff](../status-and-handoff.md).

## Problem and evidence

The original plan selected Python/FastAPI, SQLite and a scheduler inside one local process, with remote access investigated after local completion. The owner subsequently requested hosting, required free services only, asked about Cloudflare and Supabase, and explicitly approved replacing **production SQLite with Supabase Postgres** and the **always-on APScheduler model with bounded scheduled jobs**. Preserve Python/FastAPI where feasibility passes.

This changes deployment and persistence before there is a complete financial application to migrate. The existing SQLite foundation and its tests remain useful offline evidence; they do not validate Postgres, Cloudflare runtime compatibility, RLS, production Auth or hosting.

Current official Cloudflare documentation supports Python FastAPI/ASGI and Python Postgres drivers via Hyperdrive. Its SQLAlchemy support is synchronous; async ORM lacks greenlet support. Free Worker CPU and database quotas still constrain real workloads. Supabase provides persistent Postgres, Auth and scheduled-function capabilities, but its free database is limited, inactivity can pause projects and automatic backups are not included. The [hosting review](../hosting-options.md) owns the dated source details and synthetic capacity estimates; none is a production measurement.

## Accepted decision

1. Target Cloudflare-hosted React static assets with an API under the same browser HTTPS origin, backed by private Supabase Postgres. A public Git repository and downloadable UI assets do not make the portfolio public.
2. Preserve Python domain modules, broker/source adapters and FastAPI **when the selected Cloudflare runtime passes a synthetic compatibility/capacity spike**. Do not assume a normal CPython/Uvicorn process or its dependencies deploy unchanged. The platform choice does not by itself authorize silently rewriting all authoritative calculations in TypeScript or moving them into React.
3. Replace resident APScheduler/process ownership with one bounded scheduling authority: Cloudflare scheduled entry points or Supabase Cron calling a protected endpoint, selected by the spike. Persist leases, generations, idempotency keys, rate-reset state, retry-not-before and committed checkpoints in Postgres. No in-memory singleton or long sleep establishes cross-instance correctness.
4. Keep two individually authenticated, approved members with equal editing rights for one Stocks and Shares ISA. Deny anonymous and unrelated authenticated access through grants/RLS/API authorization, including private Storage and streaming. Preserve immutable evidence/audit through validated server-side mutations.
5. Use production secret bindings/server-side credentials for Trading 212, database and privileged Supabase/job access. No broker credentials, database passwords or secret/service-role keys enter React or public logs. Demo, Live and preview scopes remain separate.
6. Bring hosted qualification forward before deeper SQLite-specific production development. Require a verified migration, security and restore path before real financial production imports. Final release acceptance remains necessary after functional delivery.

## Pending implementation decisions

| Topic | Preferred or candidate handling | Evidence required before adoption |
| --- | --- | --- |
| API runtime | Python/FastAPI Worker first for reuse | Actual dependency bundle, CPU/memory, database/HTTP behavior and representative analytics; not just hello-world. If it fails, record the alternative and obtain a scope decision where the original language/calculation requirement changes. |
| Database access | Reviewed Postgres driver/Hyperdrive or transactional server-side database functions | Atomic import/rollback, exact decimals/IDs, constraints, pooling and authorization-context isolation. Independent HTTP writes are not an atomic import. |
| Identity/session transport | Supabase Auth plus same-origin secure-cookie BFF is preferred | Two-member restriction, login/refresh, HttpOnly/Secure/SameSite, CSRF/origin checks, logout/revocation, expiry and unauthorized financial-route denial. No hosted session behavior exists merely because this preference is documented. |
| Scheduling | One authority dispatches bounded jobs | Concurrent/manual delivery, expiry/takeover fencing, persisted backoff/reset, idempotent effects, abandoned-run recovery and no transaction over network waits. |
| UI updates | Authenticated SSE preferred; private batched Realtime is an alternative | Expired/nonmember denial, two-user reconnect/snapshot, lifecycle and free message/CPU/egress budgets. Record an adopted transport change explicitly. |
| Intraday storage | Full requested 90-day history; compact encrypted private archives only if measured necessary | Actual row/index/archive sizes, lossless decimal/provenance round-trip, authorized queries, integrity/key recovery and independent backups. No quiet sampling/retention reduction. |
| Recovery | Private off-host Postgres exports plus required source/archive objects | Separate-target restore, migrations/grants/RLS and financial controls, identity/session/job recovery, measured storage/egress and recovery point/time. SQLite backup tests do not satisfy this. |

## Supersession and retained reasoning

- Supersedes the **production SQLite** part of DC04 and the single resident scheduler implementation of DE01. The modular application, pure calculations, narrow adapters and separate environments remain appropriate.
- Supersedes the assumption that all hosting decisions wait for Stage 6. Qualify the target early; do not expose real data before the security/recovery gates pass.
- DE07's exact-value invariant survives. Its current canonical TEXT SQLite implementation is offline behavior; production Postgres persistence must be deliberately implemented and tested, not silently coerced to floating point.
- The former same-origin local HTTPS/Argon2id design in DE16 explains the initial session boundary. Supabase Auth with a secure-cookie BFF is now the preferred hosted candidate, pending proof; do not create two independent password systems by accident.
- The original local-process and VM/Tailscale/Tunnel choices remain historical alternatives in the [hosting review](../hosting-options.md). They were superseded by owner preference, not a measured SQLite scaling failure.
- Broker read-only permissions, API-first evidence, source immutability, GBP reporting, daily-only risk/correlation inputs, two-member scope, alert definitions, goal and tax deferral remain active requirements.

## Delivery and verification consequences

Use synthetic data for the initial hosted spike. It must demonstrate an authenticated private read, anonymous/nonmember denial, both editors, exact Decimal round-trip, atomic import/failure rollback, one bounded scheduled batch with durable lease/backoff, a representative correlation calculation, intraday storage sizing and a restore drill. Record exact commands, runtime versions, measurements and failures. A local unit suite does not establish deployed feasibility.

Add reviewed Postgres migrations and integration tests alongside the existing offline migration history; do not rewrite a published migration to conceal a backend change. Preserve account identity, original source IDs/hashes, accepted import controls and exact evidence during any migration. Build into a separate target and compare controls before selecting it. Financial outputs remain unavailable where history or market evidence is incomplete.

The owner authorized stage commits/pushes and the hosted platform. This ADR records design acceptance; it does **not** claim that a Cloudflare deployment, Supabase project, credentials, production RLS, hosted scheduler or real-data migration has been created. Any limitation that would remove an initial-release requirement stays visible and requires an explicit scope decision.

## Primary references

- [Cloudflare FastAPI/ASGI](https://developers.cloudflare.com/workers/languages/python/packages/fastapi/).
- [Python Hyperdrive and SQLAlchemy compatibility](https://developers.cloudflare.com/hyperdrive/examples/python-workers/).
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/).
- [Supabase pricing, database allowance and pausing](https://supabase.com/pricing).
- [Supabase Cron](https://supabase.com/docs/guides/cron).
- [Supabase key roles](https://supabase.com/docs/guides/getting-started/api-keys) and [grants/RLS](https://supabase.com/docs/guides/database/secure-data).
- [Supabase backup guidance](https://supabase.com/docs/guides/platform/backups).

References were checked on 11 November 2026 for the hosting review. Reverify plan/runtime limits when implementing; published support is not application-level test evidence.
