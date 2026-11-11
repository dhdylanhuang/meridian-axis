# Free hosting and private remote access

Reviewed **11 November 2026** against official provider documentation. Status: **owner-approved Cloudflare + Supabase production target**, with runtime, persistence, security and capacity qualification still required. See [ADR 0001](decisions/0001-cloudflare-supabase.md). No Supabase project or production remote access has been established by this review. The owner requires **free services only**. The public repository is source code, not permission to publish portfolio data.

## Cloudflare and Supabase - additional review, 11 November 2026

**Cloudflare plus Supabase is the selected hosted platform.** The owner explicitly approved replacing production SQLite with Supabase Postgres and the always-on scheduler with bounded scheduled work, retaining Python/FastAPI where feasibility passes. Cloudflare can serve React and application code; Supabase supplies persistent Postgres and candidate Auth/Realtime/Cron components. Exact component integration remains to qualify. A tunnel is not required for this fully hosted target.

The earlier VM recommendation below answers a narrower question: how to preserve an ordinary long-running Python process, SQLite and an in-process scheduler unchanged. It does not establish that Cloudflare cannot run Python. Current Cloudflare documentation explicitly supports [FastAPI through ASGI in Python Workers](https://developers.cloudflare.com/workers/languages/python/packages/fastapi/).

### Two viable implementation directions

| Direction | Reuse and changes | Unproven gate |
| --- | --- | --- |
| React on Cloudflare; Python/FastAPI Worker; Supabase Postgres | Retains Python domain functions and much of the adapter/API structure. Replace SQLite-specific persistence/backup with Postgres migrations and restore; replace the resident scheduler with scheduled bounded jobs and durable job leases/checkpoints. | Demonstrate package compatibility, database transactions, authentication and representative calculations inside Workers Free CPU/memory limits. This is a port, not an unchanged deployment. |
| React on Cloudflare Pages/static hosting; Supabase Auth, Postgres, TypeScript Edge Functions, Cron and Realtime | Uses Supabase's managed application components; external API calls and authoritative calculations run in server-side functions. Removes the need for a continuously running application host. | Explicitly changes the original Python/FastAPI/SQLAlchemy requirement. Port Decimal financial behavior and analytics with independent regression fixtures; measure representative functions against Edge CPU limits. |

For the first direction, Cloudflare documents Python database drivers through Hyperdrive, including `asyncpg`, `pg8000` and `psycopg`, with a compatibility date of **2026-09-08 or later**. Only synchronous SQLAlchemy ORM is documented as supported; async ORM lacks greenlet support. Hyperdrive connects directly to Supabase Postgres. Using the Supabase HTTP Data API instead is a different persistence adapter; a sequence of independent HTTP writes does not preserve the current atomic import transaction. Use a verified database transaction or narrowly authorized database function. [Python Hyperdrive support](https://developers.cloudflare.com/hyperdrive/examples/python-workers/), [Supabase connection guidance](https://developers.cloudflare.com/workers/databases/third-party-integrations/supabase/)

Python Workers support pure Python, PyEmscripten and included Pyodide packages. Native dependencies are not automatically compatible because they worked on Windows CPython. Test the actual statistical, password-hashing, HTTP, Excel and database packages needed by this app; do not assume a successful FastAPI hello-world validates the full dependency set. [Python package support](https://developers.cloudflare.com/workers/languages/python/packages/)

The second direction uses Deno/TypeScript functions. It is a reasonable alternative if the owner prefers a managed Supabase backend, but it would be a material rewrite of the backend's language and operational model. A managed database/Auth service does not supply this project's portfolio formulas, reconciliation or read-only broker client. [Supabase Edge Functions architecture](https://supabase.com/docs/guides/functions)

### Free-plan budgets to verify before committing to a production shape

| Service | Current documented free allowance or behavior | Consequence for this project |
| --- | --- | --- |
| Cloudflare Workers | 100,000 requests/day; 10 ms CPU per HTTP invocation and Cron invocation; 128 MB memory; 50 subrequests/invocation; five Cron triggers/account | Network wait differs from CPU, but parsing/importing and matrix calculations still consume CPU. Split bounded jobs and benchmark; do not assume free Workers can execute the whole analytics workload. |
| Cloudflare Hyperdrive | 100,000 database statements/day | Batch inserts/queries. The synthetic example below would consume 39,000 statements/day for one write per instrument, before reads, logs and imports. |
| Supabase database | 500 MB database; 5 GB uncached egress and 5 GB cached egress; 1 GB file storage; two active free projects; free projects pause after one week of inactivity | Database size and background-service availability require monitoring. Scheduled jobs are not a guarantee against provider pausing. Keep private off-site exports and a documented resume/recovery procedure. |
| Supabase Edge Functions | 500,000 invocations/month; 256 MB memory; 2 seconds active CPU/request; 150-second free worker wall-clock limit | One minute-level batch job is inexpensive in invocation count, but large history parsing and risk calculations must be profiled/chunked. Long-lived function SSE is not a permanent worker. |
| Supabase Realtime | 200 concurrent connections; two million messages/month; 100 messages/second on Free | Two users fit the connection allowance; per-instrument change delivery can still exhaust message/throughput quotas. Prefer one authorized batched update per cycle. |

Sources: [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [Hyperdrive pricing](https://developers.cloudflare.com/hyperdrive/platform/pricing/), [Supabase pricing and pausing](https://supabase.com/pricing), [Edge runtime limits](https://supabase.com/docs/guides/functions/limits), [Edge invocation pricing](https://supabase.com/docs/guides/functions/pricing), [Realtime limits](https://supabase.com/docs/guides/realtime/limits).

Supabase Cron can invoke SQL or an HTTP/Edge Function job every minute; it replaces the resident APScheduler model. The guidance recommends at most eight concurrently running jobs and a maximum ten-minute job duration, distinct from the tighter Edge Function runtime limit. Use one polling dispatcher, per-exchange market calendars and a database lease to prevent overlap. Persist retry-not-before times and checkpoints rather than sleeping across invocations. Clean Cron run history as well as application polling logs. [Cron](https://supabase.com/docs/guides/cron), [Cron quickstart and history cleanup](https://supabase.com/docs/guides/cron/quickstart)

### Synthetic polling capacity example

These are invented sizing assumptions, not the owner's holdings or balances. Suppose the entire polling scope contains **100 instruments**, each open for **390 minutes/session**, with **65 sessions** in a 90-calendar-day retention window. At one row per instrument per minute:

```text
100 x 390 x 65 = 2,535,000 intraday observations
2,535,000 x an assumed 250-500 bytes per indexed row = about 0.63-1.27 GB
```

The row-size assumption is illustrative and must be measured on the actual schema, including indexes and JSON/provenance. Even the lower estimate exceeds the free 500 MB database before ledger, daily prices, logs and Auth data. A naive row-per-quote implementation therefore cannot be promised to retain 90 days on Supabase Free.

Possible engineering work is compact immutable day/session blocks or lossless private archives with tested retrieval, integrity and retention. That changes storage design, not financial meaning. It must preserve raw prices, timestamps, source, currency/FX provenance and required alert/EOD evidence. Supabase's separate free file-storage allowance is also finite. Alternatively, shorter intraday retention or slower sampling requires an explicit owner scope decision. Do not silently discard observations to stay under quota.

For a synthetic 22-session month, broadcasting every row change to two listening clients produces `100 x 390 x 22 x 2 = 1,716,000` Postgres-change messages, close to the two-million allowance, and a batch can exceed the per-second limit. One cycle-level Broadcast to two clients is about `390 x 22 x 3 = 25,740` messages: one send plus two receipts, before other traffic. Send only changed values, restrict channels and refetch a versioned snapshot on reconnect. Realtime transport is a change from preferred SSE and should be recorded explicitly. [Message accounting](https://supabase.com/docs/guides/platform/manage-your-usage/realtime-messages)

One batch invocation every minute around the clock is 43,200 invocations in a 30-day month, below the stated Edge invocation allowance before retries and other functions. This does not establish provider quote limits, CPU fit, egress fit or polling accuracy. Backups, initial imports and full-table downloads also consume egress. [Supabase egress accounting](https://supabase.com/docs/guides/platform/manage-your-usage/egress)

### Security, precision and operational changes

- Create only the two intended application identities with equal editing rights; prevent unrelated signups from acquiring portfolio access. RLS must restrict rows to explicit portfolio membership, not merely to any authenticated user. Test anonymous, nonmember and both member identities, including Storage and Realtime policies. Keep immutable financial evidence/audit mutations behind validated server-side services or narrow functions rather than granting unrestricted table writes.
- Publishable/legacy anon keys may appear in browser code only with appropriate grants and RLS. Supabase secret/service-role keys, Postgres credentials and Trading 212 credentials remain server-only. Secret keys bypass RLS; a server using them must perform its own authorization. Separate user and scheduled-job credentials; do not expose a privileged scheduled-job endpoint merely because its URL is obscure. [API key roles](https://supabase.com/docs/guides/getting-started/api-keys), [secure frontend/backend access](https://supabase.com/docs/guides/database/secure-data)
- Decide Auth/session transport deliberately. Supabase Auth integration must preserve logout/expiry, exact origins and the application's chosen cookie/CSRF or bearer-token model; do not retain documentation claiming HttpOnly-cookie protections while actually using browser-stored tokens. Managed Auth does not replace application authorization or audit.
- Postgres can store exact numeric values, but the existing SQLite TEXT type and SQLite-specific migration constraints cannot simply be reused without integration tests. Keep exact values serialized as decimal strings at browser/TypeScript boundaries; JavaScript `Number` is not the ledger arithmetic type. Preserve atomic imports, identity constraints, financial controls and source evidence across the migration.
- Supabase Free does not include automatic database backups. Implement private CLI/database exports and prove restore, including required evidence/files and account access. A dashboard project, RLS or provider replication is not a backup. [Free backup guidance](https://supabase.com/docs/guides/platform/backups)

### Accepted target and remaining qualification

Implement toward the **accepted Cloudflare + Supabase target** and complete the synthetic compatibility/capacity spike: authenticated private read, atomic import/rollback, exact Decimal round trip, one scheduled batch with lease/backoff, one correlation workload, lossless intraday storage sizing and restore. Python Workers are the first reuse candidate; they are not assumed to satisfy the free CPU budget. Select the TypeScript Edge direction only through a recorded stack decision if it is preferred or the Python spike fails.

The authoritative architecture now reflects the platform decision. Before claiming production readiness, resolve backend/runtime compatibility and whether full requested polling/retention fits through measured storage changes. Record any approved scope change rather than promising every current requirement fits free hosting unchanged. No provider account, project, secret, migration or deployment was created by this research document.

## Historical stack-preserving recommendation - superseded

The following recommendation predates the owner's Cloudflare + Supabase selection. It preserves the reason VM/self-hosted alternatives were considered; it is **not the active production target**. Current architecture and early qualification gates are recorded in [ADR 0001](decisions/0001-cloudflare-supabase.md).

Keep the current FastAPI/SQLite modular monolith and one scheduler. For a genuinely cloud-hosted instance, first check whether the owner can obtain an **Oracle Cloud Always Free VM** in the chosen home region. This preserves the existing stack and persistent local disk, but capacity and continued availability cannot be promised. Provision only resources explicitly labelled Always Free; a time-limited trial is not the hosting plan.

If no suitable cloud VM is available, the practical alternative is an existing always-on machine with **Tailscale Personal and Serve**. This gives both users a private HTTPS URL without buying a domain. It is self-hosting: power, connectivity, operating-system upkeep and backups remain the owner's responsibility. Hardware and electricity are not included in a £0 service bill. Treat this as the fallback proposal, not an owner-approved decision.

Do not move the financial database onto disposable free web-service storage or rewrite persistence merely to obtain a demo URL. Application authentication, secure cookies, CSRF, audit and restore gates remain mandatory on either path. Hosting research can proceed during development; financial remote access waits for the applicable security and operational acceptance gates.

## Historical alternatives and constraints

| Option | Stack and persistence | Availability and cost limits | Assessment |
| --- | --- | --- | --- |
| Oracle Always Free VM | Runs Python, built React assets, one scheduler and SQLite on a persistent volume | Home-region capacity may be unavailable; idle instances can be reclaimed. Current documented allowance includes 200 GB combined boot/block storage and five volume backups. No Free Tier SLA. Card verification is required. | Conditional cloud candidate; requires owner signup and capacity verification. |
| Existing machine + Tailscale Personal/Serve | Keeps SQLite on the machine; Serve proxies the app over HTTPS inside the tailnet | Personal currently allows six users, enough for two. Machine must remain awake and connected for scheduled polling and access. Each client needs Tailscale access. | Simplest private fallback if an existing machine can stay available. |
| Existing machine + named Cloudflare Tunnel/Access | Tunnel connects an existing origin; it does not supply compute or database storage | Cloudflare lists a free Zero Trust allowance of 50 users. Publishing the standard application route needs a Cloudflare account and a domain on Cloudflare; buying a domain would violate a strict zero-spend requirement unless already owned. | Alternative where an existing domain and browser-only access are preferred; explicitly restrict Access to both identities. |
| Render Free web service | Python works, but local files including SQLite are lost on restart, redeploy or spin-down; persistent disks require paid compute | Sleeps after 15 minutes without inbound traffic. Free Postgres expires after 30 days. | Reject for this durable database and background polling design. Synthetic disposable previews only. |

Sources: [Oracle resource limits and reclamation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [Oracle signup and SLA FAQ](https://www.oracle.com/cloud/free/faq/), [Tailscale pricing](https://tailscale.com/pricing), [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve), [Cloudflare plans](https://www.cloudflare.com/plans/), [Tunnel prerequisites](https://developers.cloudflare.com/tunnel/get-started/), [Render Free limitations](https://render.com/docs/free).

Cloudflare **Quick Tunnels** are a separate development facility: temporary hostname, no uptime guarantee and **no SSE support**. They do not meet this application's streaming/deployment contract. [Quick Tunnel limitations](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)

Static hosting can distribute frontend files but cannot by itself run this Python process, persistent SQLite database or scheduler. The currently available Sites workflow is not assumed compatible with these requirements; a runtime/persistence change would require a separate architectural decision and migration evidence.

## Historical VM/self-hosted deployment shape

Build React once and serve the resulting assets from the same application origin as `/api`. Run one backend process and one scheduler owner. Keep SQLite and imported evidence outside the release directory on local persistent storage with restricted permissions. Do not use a shared network drive as the active database. Backups must survive loss of the host; another directory on the same VM is insufficient.

For either proposed host, Tailscale Serve can provide a tailnet-only HTTPS endpoint in front of a loopback backend. Restrict network policy to the intended two identities and the application port; inspect the initial tailnet policy rather than assuming it is restrictive. Keep two application logins as a second boundary. Use **Serve**, not the public-exposure Funnel feature. Verify the selected machine and client platform support during deployment. [Private web server and Serve guidance](https://tailscale.com/docs/solutions/host-private-server-docker)

HTTPS provisioning publishes the machine/tailnet certificate name in certificate-transparency records. Choose a neutral hostname without financial or personal details; this publishes a name, not the portfolio contents. [Tailscale HTTPS prerequisites and disclosure](https://tailscale.com/docs/how-to/set-up-https-certificates)

For a Cloudflare route, configure Access before making the hostname usable, retain application login and set exact trusted proxy/origin rules. Tunnel tokens are secrets. Test SSE end-to-end rather than assuming ordinary HTTP success proves streaming works. Tunnel is an outbound origin connection; it does not solve host downtime. [Cloudflare Tunnel architecture](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/)

## Historical VM deployment inputs

These inputs applied to the superseded VM/self-hosted candidates; they are not new questions needed to approve the already selected Cloudflare + Supabase target:

1. Whether the owner can obtain an Always Free VM with sufficient capacity, or can keep an existing machine awake during all required exchange sessions. If card verification is unacceptable, exclude Oracle without collecting payment details.
2. Whether both users accept installing Tailscale on their devices. For browser-only access, establish an already-owned suitable domain and Cloudflare account instead.
3. A private off-host backup destination, access policy and retention budget. Demonstrate SQLite online backup and separate-path restore; VM snapshots alone do not establish application consistency.

Before exposing real data, verify fresh install, migrations, two logins, expiry/logout/CSRF, exact HTTPS origin, unauthenticated financial-route denial, secret redaction, scheduler singleton, polling restart/backfill and authenticated SSE reconnection. Demonstrate recovery from host loss/redeploy using the backed-up evidence and database. Record the real recovery time and known polling gaps. Do not promise 24/7 uptime, complete intraday sampling or continuous alerts on unverified free infrastructure.

If Oracle is selected, inspect free eligibility and resource summaries before creation, stay within the documented home-region allowances, and avoid a paid-account upgrade or trial-only resource. If capacity cannot be obtained, report that fact and use an agreed fallback; do not manufacture load to avoid reclamation. Recheck all provider limits at deployment because free plans can change.

No hosting purchase, provider account creation, DNS/firewall change, invitation or production deployment is performed by this research document. Follow the owner's current authorisation and the [development gates](development-stages.md) when implementing the chosen path.
