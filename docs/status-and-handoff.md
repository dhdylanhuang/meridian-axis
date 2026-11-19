# Current status and handoff

Reviewed **19 November 2026**. This file is the authoritative implementation snapshot. Dated delivery evidence and superseded instructions are retained in [historical checkpoints](status-history.md).

## Current work scope

The owner authorized implementing the approved retention fallback after clarifying that older transaction history must remain available. Work is in progress on `feat/bounded-refresh-retention`: native/Alembic parity `0008` adds one fixed-scope PostgreSQL function. Once per UTC day, following successful scheduled sync, it expires at most 200 detailed `trading212_refresh` snapshot/source pairs older than sixty days. It retains the latest observation of every UTC day indefinitely, including the global latest snapshot. These are observed broker snapshots, not approved exchange closes. Initial captures, history/revisions, metadata, imports and existing audit are retained; referenced or mixed-source runs are skipped. No archive infrastructure or broad DELETE grant is added.

Local targeted evidence: retention asset/backup, persistence and recovery checks passed **43 tests, four PostgreSQL cases deselected**; sync-worker checks passed **six tests**. Changed backend files passed Ruff and whitespace checks. Do not rerun these without a new change/failure. Pending one validation-branch CI pass for PostgreSQL boundaries, then a stable encrypted pre-migration backup, native delivery verification and the existing sync Worker update. Runtime remains at `073ffca` / parity `0007` until separately recorded. No deletion has yet run in production.

**Validation discipline, explicit owner instruction on 19 November:** avoid unnecessary tests/checks and repeated validation. Run targeted checks for changed behaviour, reuse passing results and broaden/repeat only for new changes, failures or unresolved risk. Avoid repeated CI polling and live probes, especially during quota exhaustion. Preserve results and outstanding steps here for resumed agents.

## Deployed application

[Open Meridian](https://meridian-axis-session-gateway.meridian-worker-feasibility.workers.dev/) serves authenticated AXIS and HOLDINGS for two approved identities sharing one GBP Stocks ISA. Both users have equal application permissions. The separate [React preview](https://meridian-axis-preview.meridian-worker-feasibility.workers.dev) contains invented data.

- Deployed application source is **`073ffca`**. Supabase native schema parity is **`0007`**, with 12 public tables and RLS enabled. Native GitHub migrations own hosted DDL.
- Trading 212 reported account/cash/position figures are authoritative. Exact decimal strings, separate retrieval windows, missing fields and unknown market quote age remain visible. Historical returns are unavailable.
- Scheduled refresh targets **ten minutes during relevant regular sessions**, per the 19 November owner amendment. Cron dispatch runs in the JavaScript gateway. Python Durable Objects execute bounded work, with PostgreSQL task leases, endpoint reservations and retry state. Unknown schedule coverage permits conservative polling.
- Manual refresh requires membership, session, Origin and CSRF checks. It queues a durable alarm promptly. Evidence, approved snapshot publication, success health and audit commit together. Failures preserve the last successful snapshot.
- The BFF reads approved snapshots and selected refresh-health columns. Raw imports, source evidence and event revisions remain closed to it. A separate restricted broker writer accesses only its fixed account and broker source kinds. Broker keys are held in managed secret bindings.
- The private browser client retrieves saved snapshots and health together every ten minutes while visible and exposes manual broker refresh. An older open client needs one reload to load that implementation. Authenticated SSE remains planned.

## History and import boundaries

Orders, dividends and cash transactions advance one family page per scheduled invocation, rotating families in ten-minute slots (at most one page per family per thirty minutes). Each family uses a one-hour cooldown anchored to its successful final-page attempt. Pagination may take longer, and lifetime completeness remains unverified. Running-page checkpoints and staging survive retries. Complete acceptance appends fill/reference revisions and deduplicates repeated observations. Corporate actions retain original facts with review quality states. Normalized economic replay and calculated performance remain open.

The verified holdings CSV supports preview and atomic evidence import. It retains group context and excludes Total controls from holdings. Transaction CSV formats and API/CSV aliases remain unverified. The owner currently has transaction history in PDF, including the previously inspected cash-only statement.

Six Excel baseline observations are accepted into private hosted evidence with exact read-back and duplicate rejection. Group-value controls reconcile within £0.01. Three observations retain month precision, two explicit days and July an unknown date. Historical group-cost controls are absent. Recorded invested values remain source costs. Original workbook bytes were preserved.

## Verification evidence

19 November fix, local evidence on `fix/ten-minute-query-budget`: `/private/tmp/meridian-query-venv/bin/python -m pytest -q backend/tests/test_broker_sync.py backend/tests/test_snapshot_access.py backend/tests/test_refresh_http.py -m 'not postgres'` passed **23 tests, 42 deselected**. Targeted Node snapshot/gateway checks passed **22 tests**; sync-worker checks passed **four tests**, including persistent outage pause and duplicate manual signal coalescing. Changed backend files passed targeted Ruff checks/formatting, and whitespace checks passed. The synthetic 1,101-event replay passed with three revision SELECTs. These checks need not be repeated on resume. Initial failures reflected old one-minute/three-second timing expectations; tests now follow the ten-minute contract. Existing backend virtualenv points to a removed temporary interpreter; the temporary Python 3.13 environment above holds current dependencies.

Validation-branch CI passed at `b79b90a`: [backend checks](https://github.com/dhdylanhuang/meridian-axis/actions/runs/44605588558) passed Windows/Linux and PostgreSQL, including native restricted-role/concurrency checks; [Worker checks](https://github.com/dhdylanhuang/meridian-axis/actions/runs/44605588372) passed Linux/macOS. A subsequent browser-only refinement applies the same failure pause to manual POST errors; its new targeted test passed (one test, seven unrelated cases deselected). Backend and Worker Python sources are unchanged from passing CI. Per owner instruction, reuse these results rather than retriggering the same CI matrices for promotion/documentation.

Actual 19 November deployment: all three existing Workers (sync, session owner and gateway) updated at `073ffca`. Cloudflare's schedule API reported exactly `*/10 * * * *`. Three nonfinancial asset reads confirmed the ten-minute UI notice, new polling code and updated sign-in lifecycle. Managed secret/Hyperdrive binding sets and the existing uncached TLS origin profiles were preserved. No schema, credential or evidence changes were made. The private deployment receipt retains previous versions for rollback.

**Remaining incident verification:** the owner-reported free query allowance resets at 00:00 UTC on 20 November. Do not claim login recovery, actual ten-minute broker cadence or a measured daily query reduction from deployment/configuration checks. Authenticated cadence and provider-reported account/configuration usage remain unverified until a bounded post-reset check. Avoid repeated probes or rerunning passing CI. Old open tabs need one reload to receive the new browser polling policy. See [query budget](market-data-and-polling.md#hyperdrive-query-budget--19-november-incident).

Earlier deployed acceptance, 13 November:

- [Backend validation](https://github.com/dhdylanhuang/meridian-axis/actions/runs/43404788223) passed Windows/Linux and disposable PostgreSQL checks for the refresh/import implementation. [Worker validation](https://github.com/dhdylanhuang/meridian-axis/actions/runs/43413867781) passed Linux/macOS for the deployed gateway/object correction. Historical test totals remain attached to their original checkpoints.
- Actual scheduled observations at **14:53, 14:54 and 14:55 London on 13 November** demonstrate minute cadence. Consecutive intervals were **51.353 seconds** during startup and **59.688 seconds** thereafter. Snapshot health showed zero consecutive failures. Held-listing metadata refresh completed.
- Both approved identities passed actual HTTPS snapshot/health/manual-queue checks. Responses matched stored projections, and anonymous/nonmember/Origin/CSRF/query/duplicate-cookie/logout denials passed. A further authenticated read returned a snapshot retrieved 50.07 seconds earlier with no-store headers. These checks used provider-verified short-lived test sessions. Password login was qualified in an earlier delivery.
- Native `0007`, restricted role flags, all 12 RLS tables, preserved source/member controls and the existing BFF credential were independently verified. Encrypted pre/post-migration exports were verified. The earlier actual `0006` financial snapshot passed a network-disconnected local restore. A `0007` restore drill remains unverified.
- Earlier desktop Chrome inspection verified the saved holdings view. Visual review of the refresh controls remains open because browser/computer access was unavailable. Partner first-use browser confirmation, mobile checks and the full browser-cookie audit remain open.

Private deployment IDs, receipts, source values, credential material and recovery keys stay outside Git. A clean clone lacks those private administrative resources. Historical first-use helpers pin earlier empty schemas and require inspection before use on an active deployment.

## Remaining delivery

Owner amendment, 19 November: site availability takes priority; 60-day observation retention is approved as a fallback if 90 days cannot fit safely. The same conservative model projects 275–301 MB for 60 additional days. Ninety days remains the target and no cleanup has been implemented. Prefer evaluating this approved fallback before expanding archive infrastructure. Storage capacity does not establish runtime RAM safety; preserve bounded processing and do not claim crash prevention from disk sizing.

The measured-input [storage report](storage-capacity-report.md) is complete. Physical qualification remains open: ten-minute compressed retention may fit, but around-the-clock raw retention exceeds the database allowance. Lossless archive design, scheduled retention/backups and independent key custody remain open. Replacement hosted Auth/browser recovery and active-data credential rotation also remain open.

Other supported requirements include normalized ledger/cash/quantity reconciliation, verified transaction CSV aliases, group mapping/editing, daily prices/FX and approved closes, historical performance, projections, correlation/risk, remaining screens and alerts. Tax remains owner-deferred. The contracts in [the documentation index](README.md) retain those requirements.
