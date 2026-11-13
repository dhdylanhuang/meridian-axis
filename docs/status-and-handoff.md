# Current status and handoff

Reviewed **13 November 2026**. This file is the authoritative implementation snapshot. Dated delivery evidence and superseded instructions are retained in [historical checkpoints](status-history.md).

## Current work scope

The owner requested documentation reconciliation after minute polling was fixed. Platform development awaits the owner's next instruction. Scheduled broker refresh remains enabled. The [next task brief](next-milestone.md) contains a proposed bounded follow-up for owner selection.

## Deployed application

[Open Meridian](https://meridian-axis-session-gateway.meridian-worker-feasibility.workers.dev/) serves authenticated AXIS and HOLDINGS for two approved identities sharing one GBP Stocks ISA. Both users have equal application permissions. The separate [React preview](https://meridian-axis-preview.meridian-worker-feasibility.workers.dev) contains invented data.

- Deployed application source is **`0410a8e`**. Supabase native schema parity is **`0007`**, with 12 public tables and RLS enabled. Native GitHub migrations own hosted DDL.
- Trading 212 reported account/cash/position figures are authoritative. Exact decimal strings, separate retrieval windows, missing fields and unknown market quote age remain visible. Historical returns are unavailable.
- Scheduled refresh targets **60 seconds during relevant regular sessions**. Cron dispatch runs in the JavaScript gateway. Python Durable Objects execute bounded work, with PostgreSQL task leases, endpoint reservations and retry state. Unknown schedule coverage permits conservative polling.
- Manual refresh requires membership, session, Origin and CSRF checks. It queues a durable alarm promptly. Evidence, approved snapshot publication, success health and audit commit together. Failures preserve the last successful snapshot.
- The BFF reads approved snapshots and selected refresh-health columns. Raw imports, source evidence and event revisions remain closed to it. A separate restricted broker writer accesses only its fixed account and broker source kinds. Broker keys are held in managed secret bindings.
- The private browser client retrieves saved snapshots every 60 seconds and exposes manual broker refresh. An older open client needs one reload to load that implementation. Authenticated SSE remains planned.

## History and import boundaries

Orders, dividends and cash transactions advance one family page per scheduled invocation, rotating families. Each family uses a one-hour cooldown anchored to its successful final-page attempt. Pagination may take longer, and lifetime completeness remains unverified. Running-page checkpoints and staging survive retries. Complete acceptance appends fill/reference revisions and deduplicates repeated observations. Corporate actions retain original facts with review quality states. Normalized economic replay and calculated performance remain open.

The verified holdings CSV supports preview and atomic evidence import. It retains group context and excludes Total controls from holdings. Transaction CSV formats and API/CSV aliases remain unverified. The owner currently has transaction history in PDF, including the previously inspected cash-only statement.

Six Excel baseline observations are accepted into private hosted evidence with exact read-back and duplicate rejection. Group-value controls reconcile within £0.01. Three observations retain month precision, two explicit days and July an unknown date. Historical group-cost controls are absent. Recorded invested values remain source costs. Original workbook bytes were preserved.

## Verification evidence

- [Backend validation](https://github.com/dhdylanhuang/meridian-axis/actions/runs/43404788223) passed Windows/Linux and disposable PostgreSQL checks for the refresh/import implementation. [Worker validation](https://github.com/dhdylanhuang/meridian-axis/actions/runs/43413867781) passed Linux/macOS for the deployed gateway/object correction. Historical test totals remain attached to their original checkpoints.
- Actual scheduled observations at **14:53, 14:54 and 14:55 London on 13 November** demonstrate minute cadence. Consecutive intervals were **51.353 seconds** during startup and **59.688 seconds** thereafter. Snapshot health showed zero consecutive failures. Held-listing metadata refresh completed.
- Both approved identities passed actual HTTPS snapshot/health/manual-queue checks. Responses matched stored projections, and anonymous/nonmember/Origin/CSRF/query/duplicate-cookie/logout denials passed. A further authenticated read returned a snapshot retrieved 50.07 seconds earlier with no-store headers. These checks used provider-verified short-lived test sessions. Password login was qualified in an earlier delivery.
- Native `0007`, restricted role flags, all 12 RLS tables, preserved source/member controls and the existing BFF credential were independently verified. Encrypted pre/post-migration exports were verified. The earlier actual `0006` financial snapshot passed a network-disconnected local restore. A `0007` restore drill remains unverified.
- Earlier desktop Chrome inspection verified the saved holdings view. Visual review of the refresh controls remains open because browser/computer access was unavailable. Partner first-use browser confirmation, mobile checks and the full browser-cookie audit remain open.

Private deployment IDs, receipts, source values, credential material and recovery keys stay outside Git. A clean clone lacks those private administrative resources. Historical first-use helpers pin earlier empty schemas and require inspection before use on an active deployment.

## Remaining delivery

The immediate proposed follow-up is storage and retention qualification. Private sizing indicates that 90 days of full refresh evidence/projections can exceed or severely pressure the free database allowance before indexes, audit and history overhead. Lossless archive design, scheduled retention/backups and independent key custody remain open. Replacement hosted Auth/browser recovery and active-data credential rotation also remain open.

Other supported requirements include normalized ledger/cash/quantity reconciliation, verified transaction CSV aliases, group mapping/editing, daily prices/FX and approved closes, historical performance, projections, correlation/risk, remaining screens and alerts. Tax remains owner-deferred. The contracts in [the documentation index](README.md) retain those requirements.
