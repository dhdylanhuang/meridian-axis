# Security and operations

Status: CONFIRMED access/privacy requirements and owner-approved **Cloudflare + Supabase** production target, 11 November 2026. [ADR 0001](decisions/0001-cloudflare-supabase.md) supersedes production SQLite and the resident scheduler. Stage 1A's implemented backup/restore is an **offline SQLite foundation**. Hosted closed-schema RLS and backend identity/session foundations are verified; application authorization, scheduled backups and production financial access remain open.

## Trust boundary

Application authentication and authorization protect one owner's portfolio from unintended access. They do not protect against a trusted database/platform administrator reading stored data. Broker access remains read-only: no placement, modification or cancellation exists in the allowed integration surface.

Production target: React static assets and a Worker API under one Cloudflare HTTPS origin, with private Supabase Postgres behind it. Publicly downloadable application assets do not grant access to portfolio data. Require authenticated membership for every financial endpoint, source download, settings mutation and streaming subscription. Health checks expose no holdings, credentials, paths or sensitive configuration. Local development remains loopback-only; it does not acquire public access because the hosted target is now authorized.

Use explicit database roles and RLS. Anonymous access to financial tables, private Storage and channels is denied; unrelated authenticated Supabase identities are also denied. Only the two approved members can access the shared ISA, with equal editing capabilities. Preserve server-side service boundaries: equal editors cannot directly rewrite immutable evidence or audit. Use narrow database functions or validated API services for financial changes. Test grants and RLS on every exposed table/function and separately test both approved identities, a nonmember and an anonymous client. Direct Postgres roles must not bypass these boundaries accidentally.

## Users and sessions

Create two individually authenticated identities with equal editing rights, separate sessions and audit attribution. Initial account provisioning is restricted administration; disable unrestricted signup or ensure signup can never grant portfolio membership. No default/shared password or open registration grants access.

**Preferred design pending prototype:** Supabase Auth manages identities; a same-origin Worker backend-for-frontend (BFF) keeps provider tokens server-side and issues high-entropy opaque application-session cookies. Store token hashes for lookup, bounded expiry/revocation and protected server-side token material only when necessary. The prototype must demonstrate provider refresh, session rotation, logout/reset, expired/revoked membership and concurrent sessions. Do not claim that Supabase JWT validation alone provides immediate application-session revocation. Log authentication outcomes safely and apply bounded throttling.

The original local-only Argon2id/password-database design is superseded as the preferred hosted identity approach; it remains historical rationale, not an instruction to maintain two competing password systems. Final Auth/session transport must be accepted from prototype evidence. A browser-stored bearer-token alternative requires an explicit recorded security decision, not documentation falsely claiming HttpOnly protection.

For the preferred BFF, cookies are HttpOnly, Secure and SameSite with narrow origin/path policy. Cloudflare terminates browser HTTPS; trust only the configured gateway/origin chain. Local secure-cookie development needs tested HTTPS/certificate setup. Any development-only exception is explicit and impossible in the remote profile.

Use CSRF protection on state-changing routes, including account/session actions as appropriate; verify Origin and CSRF token. SameSite alone is not the whole CSRF design. SSE is a read-only authenticated connection, not a mutation channel. Use exact development origins/proxy settings, never wildcard credentialed CORS. Render thesis text safely without executable HTML.

Implementation references: [OWASP sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) and [password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). Recheck library parameters during implementation rather than copying a dated hash-cost constant.

Bootstrap/reset remains an authenticated administrative operation with explicit identity and audit; no public password-reset email workflow is required initially. Q04 is resolved: both members can perform application editing operations. Broker trading remains excluded for everyone.

### Closed membership/session foundation

The `0003` schema adds `account_members` and `app_sessions` with RLS enabled and PUBLIC/anon/authenticated grants revoked. It creates no identity, member, session or runtime policy. The application owns no password hashes; Supabase Auth remains the identity provider.

The exact validation-branch commit passed Windows/Linux and all 31 PostgreSQL cases before promotion. Read-only hosted inspection verified parity `0003`, zero rows/policies on both new tables and denied PUBLIC/anon/authenticated table privileges. This verifies a closed schema, not usable application access.

The new HTTP adapter performs password grant followed by authenticated provider user verification, pins the project origin and requires matching canonical UUIDs. It returns identity/expiry only and discards provider tokens from its return contract. Mocked HTTP tests cover malformed/expired responses, redirects, injected client defaults/cookies, bounded streams and safe errors. Live identity and refresh qualification remain open.

The session service issues 256-bit opaque tokens with hash-only persistence, separate CSRF nonces and a maximum one-hour fresh-login lifetime bounded by provider expiry. It rechecks session/account membership, enforces exact HTTPS Origin and CSRF for mutations, and commits session changes/audit within the caller's transaction. Rotation consumes the old row through a conditional update to prevent two simultaneous successors; revocation denies later authorization checks. It does not cancel work already authorized. Provider refresh material is not stored at this stage.

The explicitly configured HTTP component passes offline tests and Windows/Linux/PostgreSQL CI. It supplies secure session/CSRF cookies, five-minute HMAC-signed prelogin CSRF, exact HTTPS authority/Origin checks, bounded credentials input and safe non-cacheable errors. The prelogin nonce may be reused within its validity window; it is CSRF protection, not a one-time authentication credential. Provider verification precedes the database transaction; cookies follow commit. A required injected shared login limiter fails closed on denial, failure or timeout; there is no default production limiter. This component does not prove the deployed limiter or proxy. Browser execution, runtime role/RLS, provider refresh and hosted two-member verification remain required before a usable authenticated application is claimed. See the [session route contract](api-and-ui.md#verified-session-component), [Starlette cookie API](https://starlette.dev/responses/) and [streaming request API](https://starlette.dev/requests/).

### Runtime session permissions under qualification

The next synthetic qualification uses a dedicated trusted BFF database role, distinct from Supabase's browser/API roles. It must be a non-owner without superuser, role/database creation, inheritance or BYPASSRLS powers. Grant only schema usage, membership/session SELECT, session/audit INSERT and column-level UPDATE of `app_sessions.revoked_at`. Do not grant member provisioning, session DELETE/expiry updates, audit reads/updates/deletes or financial-table access. Never grant this role to `anon`, `authenticated` or the API authenticator.

RLS must bind rows to an administratively fixed deployment account, not a request-controlled setting. Session policies require active membership; revocation must remain possible without hiding its newly revoked row during UPDATE. Audit INSERT is restricted to session actions, the fixed account and an active member actor, with no import-run link. The credential remains trusted to act for approved members; provider identity verification is still the BFF's responsibility. A stolen backend credential is not equivalent to an unrelated browser login.

The disposable qualification passed at `ade9abf`: the actual session service runs as the restricted role, both member lifecycles/audit succeed, forbidden SQL and cross-account inserts are denied, and rollback preserves atomicity. This is not deployed permissions or a credential-login test. Production provisioning must still verify role memberships, actual Hyperdrive login and credential recovery. Table owners and BYPASSRLS roles do not establish these properties. PostgreSQL documents [RLS evaluation and owner exceptions](https://www.postgresql.org/docs/17/ddl-rowsecurity.html) and [column-level grants](https://www.postgresql.org/docs/17/sql-grant.html).

## Secrets and private data

Broker key/secret come from local environment variables or production secret bindings and remain server-only. Keep Supabase secret/service-role keys, database passwords, scheduled-job credentials and any archive encryption keys out of React, settings exports, URLs, logs, fixtures and API responses. Only Supabase publishable/legacy anon keys may enter a client bundle, and those confer no financial access without validated user identity, grants and RLS. Secret/service-role keys bypass RLS; use them only in narrow server/admin operations with explicit authorization. A scheduled endpoint needs a verified job credential; being absent from frontend navigation is not protection.

Environment and broker base origin are validated together; do not send credentials to an arbitrary browser-supplied URL. Separate Demo/Live and preview/production secrets and data. Preview builds must never silently connect to the real ISA or production database. Test transports are injected without relaxing production origin validation. [Supabase API key roles](https://supabase.com/docs/guides/getting-started/api-keys), [grants/RLS guidance](https://supabase.com/docs/guides/database/secure-data)

The repository is public. Ignore rules now exclude real spreadsheet/CSV imports, runtime directories, database/WAL/SHM files, backups, uploads, Node output and environment-secret variants while retaining safe .env.example. Ignore rules do not remove already tracked content; review every staged diff. Never publish actual portfolio balances, position sizes, contribution schedules, private source paths/digests or personal/employment notes. Public fixtures use invented data; explicitly allowlist only reviewed synthetic files when needed.

Keep local sources/runtime files in a private configured directory with appropriate OS permissions; active local SQLite must not live on a shared/synchronized network filesystem. Hosted source objects and quote archives use private access policies. If measured free-plan storage requires lossless archives, validate encryption/key recovery, authorized retrieval, integrity manifests and independent backups before deleting a database copy. Do not archive into the public Git repository or a publicly readable Storage bucket. The 90-day quote requirement is not permission to expose data or silently shorten retention.

Audit before/after contains only relevant safe fields. Raw financial evidence is private, but never includes HTTP authentication/session headers. Redact exceptions from upstream libraries. File uploads have size/type limits; reject archive/path traversal and never execute workbook macros or external links. Treat imported strings as data, including spreadsheet-formula injection if later exporting CSV.

## Configuration catalogue

Initial environment settings are implemented in `backend/src/meridian/config.py` and catalogued in `.env.example`; other runtime/financial settings below remain planned.

| Setting | Default / policy |
| --- | --- |
| Application bind/origin | Local loopback; production Cloudflare same-origin HTTPS API/assets |
| Broker environment | Demo; Live requires explicit setting |
| Broker credentials | Environment/secret-binding key and secret; no default |
| Database/data scope | Current offline private SQLite; production Supabase Postgres with isolated Demo/Live and preview scopes |
| Hosted Auth/session | Preferred Supabase Auth + secure-cookie BFF; prototype and final contract pending |
| Scheduled work | One authority; protected invocation, durable lease/checkpoint/retry state; no resident scheduler |
| Quote interval | Requested 60 seconds, bounded by provider capability |
| Quote stale threshold | 2× configured interval while session open; fetch/quote age separately |
| Intraday retention | 90 days; configurable |
| Daily retention | Indefinite |
| Backoff cap | 15 minutes for exponential component; later provider reset still honoured |
| Risk horizon / frequency | 252 daily observations; daily default |
| Correlation windows / daily minimum | 30/90/252 trading-day horizons; reliable minimum 60 |
| Held-pair correlation threshold | 0.85 for eligible 90-day result |
| EOD discrepancy threshold | 0.5%, same session and price basis |
| Risk-free / allowances | Effective-dated risk-free values; taxable allowance features deferred |
| Goal / drawdown thresholds | £100,000 by 30 April 2030; group >=10%; rolling two-trading-day portfolio max drawdown >=2%; re-arm after recovery |
| Scenario/RAG/other alert thresholds | Remaining owner values or unresolved configuration; no fabricated defaults |

Validate ranges, currencies, time zones and chronology. Persist non-secret settings with revision/effective dates and audit. A settings change invalidates affected computations rather than silently reusing old cache results.

## Backups and restore

**Current offline foundation:** SQLite online backup and separate-path restore are implemented/tested. Copying only a live WAL database file is not a dependable backup procedure. These checks do not verify Postgres recovery. [SQLite backup documentation](https://www.sqlite.org/backup.html)

**Required hosted path:** Supabase Free has no included automatic database backups. Provide private off-host logical exports using a verified Supabase CLI/Postgres procedure, plus source/archive objects required for replay and operational identity/access metadata. Keep encryption keys and credentials protected and recoverable separately; do not bundle reusable secrets into ordinary financial exports. Storage objects require their own backup coverage. Include schema/migration version, scope, timestamp, digests and reconciliation controls. [Supabase backup guidance](https://supabase.com/docs/guides/platform/backups)

Begin with a backup before real imports, schema upgrades and corrections. The original proposed daily/seven-daily/four-weekly policy remains a target to qualify, not a working schedule. Measure export size, storage and egress against the free plan; record any revised recovery policy explicitly. A copy in the same Supabase project is not an off-host recovery path. Public CI logs/artifacts must never receive financial dumps or environment secrets.

Restore drill: suspend mutations/scheduling → preserve the current target → restore into a separate isolated database/environment → restore referenced private evidence → validate migrations, identities/grants/RLS and financial controls → verify both logins, read-only broker configuration and sample views → reconcile durable job/alert state → only then select the restored target. Never overwrite the only working copy first. Verify the free-account/project limit permits the chosen drill; a local Postgres drill and a hosted access check are distinct pieces of evidence.

Record measured recovery point/time and resume instructions, including free-project pause or exhausted-quota behavior. Do not promise an SLA or untested RPO/RTO. Refresh market data after restore without duplicate economics, recover expired leases/checkpoints and disclose missing intraday observations.

## Installation, upgrade and shutdown

Tested **offline foundation** setup/maintenance commands are in [local development](local-development.md). Hosted commands, Worker compatibility versions, Postgres migrations, Auth bootstrap, secret bindings and rollback instructions must be implemented and tested before being advertised. Provide fresh-machine Windows/local commands plus the actual hosted build/runtime qualification. A locally passing Python test does not establish Worker compatibility.

Upgrade procedure: inspect release/schema notes → backup → suspend writes/scheduled dispatch → migrate the selected target → replay affected derived data → run reconciliation/security smoke checks → activate a versioned release and dispatch. On failure, restore a compatible backup or documented compatible application version. Worker shutdown closes resources; lease expiry/idempotency handle abrupt termination without a transaction spanning external waits. Do not assume a shutdown callback always executes.

## Hosting qualification and activation

The owner has selected Cloudflare + Supabase with free services only. Platform feasibility/security qualification is now an **early gate**, rather than leaving every hosting decision to Stage 6. Use synthetic accounts/data to establish private Postgres access, session/membership denial, atomicity, job recovery, streaming and resource budgets before real financial migration. Preserve final operational acceptance and actual release activation as explicit stage evidence.

An origin reachable over the Internet must still disclose no financial data to anonymous/nonmember visitors. A custom domain, public Storage bucket or tunnel is not required by this target. Tailscale/Tunnel comparisons remain historical alternatives in the [hosting review](hosting-options.md); they are not the selected architecture. No production access has been configured merely by updating this document.
