# Security and local operations

Status: CONFIRMED requirements with ADOPTED local deployment design. Stage 1A provides local ISA metadata bootstrap and verified backup/restore; login accounts, certificates, scheduled backups and private hosting are not yet implemented.

## Trust boundary

Local application authentication protects one owner's portfolio from unintended browser/user access. It does not protect against an administrator reading the machine or SQLite files. Broker access is read-only. No order placement, modification or cancellation exists in the allowed integration surface.

Bind application and development services to loopback only. No `0.0.0.0`, public hosting or tunnel in the local stages. An authenticated connection is required for all financial endpoints and SSE. Health checks expose no holdings, credentials, file paths or sensitive configuration.

## Users and sessions

Create two individual application users with the same full editing rights; never a shared password. The owner permits shared treatment for simplicity, but separate logins keep session revocation/audit attribution without a role hierarchy. ADOPTED password hashing choice: Argon2id with maintained library defaults verified at implementation. Store only password hashes. Sessions use high-entropy opaque tokens, server-side expiry/revocation and stored token hashes. Rotate on login; revoke on logout/password reset. Log successful and failed authentication safely and apply bounded login throttling.

Cookies are HttpOnly, Secure and SameSite with a narrow path/origin policy. To satisfy Secure reliably, ADOPTED local deployment is same-origin HTTPS with a local certificate; document trust/setup and both-browser checks when implemented. Do not quietly weaken cookie security to make HTTP development easier. Any development-only exception needs an explicit recorded decision and must be impossible in a remote profile.

Use CSRF protection on state-changing routes, including account/session actions as appropriate; verify Origin and CSRF token. SameSite alone is not the whole CSRF design. SSE is a read-only authenticated connection, not a mutation channel. Use exact development origins/proxy settings, never wildcard credentialed CORS. Render thesis text safely without executable HTML.

Implementation references: [OWASP sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) and [password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). Recheck library parameters during implementation rather than copying a dated hash-cost constant.

Bootstrap/reset is a local administrative operation with explicit account identity and audit, not a public password-reset email system or default password. Q04 is resolved: both logins can perform all application editing operations. This permission applies to local app data/settings; broker trading remains excluded for everyone.

## Secrets and private data

Broker key/secret come from environment variables, remain backend-only and never enter settings exports, URLs, logs, source fixtures, browser storage or API responses. Environment and base origin are validated together; do not send credentials to an arbitrary custom URL supplied by a browser. Test transports are injected without relaxing production origin validation.

The repository is public. Ignore rules now exclude real spreadsheet/CSV imports, runtime directories, database/WAL/SHM files, backups, uploads, Node output and environment-secret variants while retaining safe .env.example. Ignore rules do not remove already tracked content; review every staged diff. Never publish actual portfolio balances, position sizes, contribution schedules, private source paths/digests or personal/employment notes. Public fixtures use invented data; explicitly allowlist only reviewed synthetic files when needed.

Keep the portfolio database and private sources in a configured local data directory with appropriate OS permissions. Do not use a cloud-synchronised/shared network folder for an actively written SQLite database without a separately validated design. A backup can be copied after consistent creation under an explicit retention/privacy policy.

Audit before/after contains only relevant safe fields. Raw financial evidence is private, but never includes HTTP authentication/session headers. Redact exceptions from upstream libraries. File uploads have size/type limits; reject archive/path traversal and never execute workbook macros or external links. Treat imported strings as data, including spreadsheet-formula injection if later exporting CSV.

## Configuration catalogue

Initial environment settings are implemented in `backend/src/meridian/config.py` and catalogued in `.env.example`; other runtime/financial settings below remain planned.

| Setting | Default / policy |
| --- | --- |
| Application bind/origin | Loopback, same-origin local HTTPS |
| Broker environment | Demo; Live requires explicit setting |
| Broker credentials | Environment-only key and secret; no default |
| Database/data path | Explicit private local directory; distinct Demo/Live data |
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

Use SQLite's online backup interface or a verified quiescent backup procedure; copying only the live database file while WAL writes occur is not a dependable backup method. [SQLite backup documentation](https://www.sqlite.org/backup.html)

Begin with a backup before real imports and schema upgrades. PROPOSED recurring policy: daily backups plus pre-migration/pre-correction backups, seven daily and four weekly generations, subject to owner storage preference. Backups exclude secrets; include schema version, timestamp, source DB identity and digest. Source evidence required for replay must be covered by the backup strategy as well as the DB.

Restore drill: stop app/jobs → preserve current DB → restore into a separate verified local path → validate integrity/schema → compare counts/financial controls → start on loopback → verify login and sample views → only then select the restored DB. Never overwrite the only working copy as the first recovery step. A backup task is incomplete until a restore drill passes.

Document recovery point and time expectations after measuring the drill; do not promise untested RPO/RTO. Refresh cached market data after restore without reimporting duplicates. Reconcile abandoned jobs and scheduler ownership at startup.

## Installation, upgrade and shutdown

Tested foundation setup and maintenance commands are in [local development](local-development.md). The implementation must provide fresh-machine Windows instructions, supported Python/Node versions, locked dependencies, environment setup, local certificate setup, database migration, user bootstrap, fixture tests, launch and shutdown. Verify each command on the actual repository. Do not paste plausible commands into README before their manifests/scripts exist.

Upgrade procedure: inspect release/schema notes → backup → stop writes → apply migrations → replay required derived data → run reconciliation/smoke checks → restart. On failure, restore a compatible backup rather than guessing at downgrade scripts. Graceful shutdown cancels jobs, closes HTTP clients and releases scheduler ownership; it does not leave a transaction open.

## Later remote access

Stage 6 compares Tailscale with Cloudflare Tunnel/Access after local acceptance. Preserve application authentication, HTTPS, CSRF, audit and backup even behind a gateway. Eventual private hosting is owner-authorised using free services only; verify the selected host and intended identities/access, examine SQLite host ownership and test remote logout/SSE. Do not publish a public portfolio, open firewall ports, change DNS or configure a tunnel during documentation/local development.
