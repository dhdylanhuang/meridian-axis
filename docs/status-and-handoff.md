# Current status and handoff

Reviewed **19 November 2026**. This file is the authoritative implementation snapshot. Dated delivery evidence and superseded instructions are retained in [historical checkpoints](status-history.md).

## Current work scope

The owner selected **broker-led automatic holding discovery/enrichment** next:
orders remain in Trading 212; one integrated AXIS supports PM, trading-monitoring,
risk and portfolio cash/treasury workflows. Current prices and reported figures
come from the broker. A parallel current-account valuation/live-price engine is
removed from the delivery plan; historical price/benchmark/FX inputs remain for
risk/performance. See the [requirements amendment](product-requirements.md#broker-led-monitoring-amendment--19-november-2026)
and revised delivery order. No role or tax scope change.

Implemented source: new held tickers request the existing metadata job before its
successful daily cooldown ends, preserving leases, failures and provider retry
limits. Scheduled and manual success share that job. Snapshot publication adds
whitelisted listing enrichment/coverage/provenance and observed additions/closures;
the existing private view displays these states. Position facts always win, cash
components remain separate, and quote age remains unknown. Financial publication
precedes metadata lookup; fresh enrichment appears in the next successful snapshot.
The existing metadata reader is shared by session checks and publication. There
was no duplicate live-price service to delete; the unused sixty-second quote and
ninety-day local retention settings/sample environment entries were removed.
The fixed Worker bundle allowlist includes the new shared module. No schema,
credential, grant, ten-minute cadence, retention or workbook change.

Offline checks completed once for changed paths:
- `/private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_holding_discovery.py backend/tests/test_broker_sync.py backend/tests/test_snapshot_access.py -m 'not postgres'`: **31 passed, 42 deselected**.
- `node --test prototype/worker-feasibility/tests/test_snapshot_ui.mjs`: **9 passed**.
- `/private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_config.py prototype/worker-feasibility/tests/test_application_bundle.py`: **10 passed**.
- Targeted Ruff check/format passed for changed Python files. No full suite/CI
  matrix, retention test, sizing query or hosted database probe was repeated.

Coverage includes new/closed holdings, repeated and missing metadata, exact broker
figures, manual/scheduled dispatch, successful cooldown bypass, active leases,
retry/terminal pauses, metadata provenance/conflict/staleness, immutable snapshots,
unheld catalogue exclusion, UI notices and removal of unused configuration.
PostgreSQL execution and actual broker enrichment remain unverified. **Source
`e327fc9` is deployed to all three existing Workers.** Cloudflare active deployment
annotations independently matched the full source commit for sync, session owner
and gateway. Three nonfinancial asset reads matched local source bytes exactly,
returned HTTP 200 and `Cache-Control: no-store`. Managed secret/Hyperdrive binding
sets were preserved; preflight retained the existing uncached TLS origin profiles.
Cloudflare's schedule API still reports exactly `*/10 * * * *`. No schema,
credential, workbook or database operation was performed, and passing targeted
evidence above was reused without rerunning tests/CI.

The initial immediate static-asset check failed and its rollback completed for
sync/gateway but not the session owner. A bounded forward release restored all
three Workers to `e327fc9`, with source annotations, bindings, schedule and exact
asset checks passing. The failed and successful private receipts retain prior/
active version IDs; do not rerun the original first-use helpers or overwrite those
receipts. The initial asset mismatch's root cause is not established. Future
source-only releases should check active source and allow a bounded asset
propagation retry before deciding rollback. Quota exhaustion limits live database
verification, not authority to deploy the reviewed source.

Next operational check: bounded login/cadence/actual enrichment verification when
the quota incident allows it; actual query usage remains unverified. No financial
endpoint or database was probed for this release. An already open client needs one
reload to receive the updated metadata/change notices. Next feature work remains
integrated transaction/cash reconciliation under the revised delivery order.

## Previous completed slice

The preceding delivery (`c2cf7b3`) implements a **local, read-only execution quantity diagnostic**
(method `known_trade_quantity_v1`). It normalizes accepted initial capture order
rows and ongoing fill revisions into one effective quantity record per identity,
preserving evidence/revision links. It compares known signed trade deltas with the
latest saved Trading 212 positions and exposes unexplained residuals, corporate
actions, sign conflicts and incomplete coverage. It never invents opening balances.
Zero residuals remain provisional. Cash/dividend/fee economics, a persisted ledger,
CSV aliases and dashboard presentation remain unfinished.

Run from `backend`: `python -m meridian.reconcile_history --database /path/to/private.sqlite3 --account-id ACCOUNT_ID`.
The JSON is private financial output; keep it outside Git/logs. SQLite is opened
read-only in one consistent transaction. Each capture/revision read fails closed
above 20,000 observations. See [method and boundary](imports-and-reconciliation.md#execution-quantity-diagnostic--19-november-2026).
No hosted operation, migration, access change, deployment, polling/retention change
or workbook access was needed. Deployed sources/native parity below remain current.

New offline evidence (19 November):
`/private/tmp/meridian-query-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_history_reconciliation.py`
passed **12 tests**. Coverage includes real synthetic evidence acceptance and
snapshot publication, repeated syncs, revised effects, running-page exclusion,
precise residuals, signed sells, distinct fills, closed positions, future fills,
conflicts, scope/limits, read-only CLI and digest failures. Targeted Ruff check and
format check passed for the three new modules, domain package and new test file.
The first nine-case run passed; after adding currency/integrity coverage the final
twelve-case run passed. A Ruff cache write was sandbox-denied; `--no-cache` checks
then passed. Reuse these results; no full suite, CI matrix, live probe or retention
check was run. No real-input reconciliation or PostgreSQL execution is claimed.

The manual Excel archive remains completed: the private **AXIS Archive** sheet has
1,360 retained refresh generations, with original sheets/formulas preserved. Use
[the manual export command](workbook-archive.md); no workbook was read or changed
for this delivery. [Next assignment](next-milestone.md) identifies the revised delivery sequence.

Bounded retention and the separately authorized backup repair are **complete and deployed**. Native schema parity is `0008`; the sync Worker source is `0afd670`. Session/gateway source remains `073ffca`. Detailed broker-refresh snapshot/source pairs expire after sixty days, in one daily batch of at most 200 pairs, while the final observed snapshot of every UTC day is kept indefinitely. The global latest snapshot, all transaction/dividend/cash history, revisions, initial captures, metadata, Excel/CSV evidence, imports and prior audit are retained. Referenced or mixed-source runs are skipped. Daily observations are not approved exchange closes or implemented historical performance.

The first actual capability execution completed with **zero snapshots and zero sources removed**. The ten-minute Cron was restored. No archive infrastructure, general DELETE grant, credential replacement or UI change was introduced. This implementation controls only the selected expiry workload; other capacity/RAM limits remain separate. No further task is activated automatically.

Reusable evidence: targeted local persistence/recovery/retention checks passed **43 tests**, with four PostgreSQL cases deselected; **six Worker tests** passed. [PostgreSQL CI](https://github.com/dhdylanhuang/meridian-axis/actions/runs/44611266327) passed through native and Alembic paths, including all four new retention execution/permissions cases. [Worker CI](https://github.com/dhdylanhuang/meridian-axis/actions/runs/44611266304) passed Linux/macOS. Linux backend CI had one outdated backup-version assertion and 462 other passing tests; the assertion was corrected and **eight targeted backup tests passed**. Windows was cancelled by fail-fast and is not claimed as verified. One additional secret-free Docker-error regression passed. Do not rerun these matrices on resume without a relevant new change or failure.

The encrypted pre-migration `0007` backup and authenticated read-back were verified. The release independently observed the native `0008` history marker, twelve RLS tables, function/table ownership, sync-only capability access and absence of broad DELETE privilege. The sync Worker update preserved existing secret and Hyperdrive bindings. Trusted maintenance exercised the fixed capability; automated invocation through Hyperdrive remains unobserved during the reported daily quota exhaustion. No `0008` restore drill is claimed.

Backup failure diagnosis: Docker Desktop was stopped, while formatted `docker info` returned zero alongside a daemon error. Starting the existing app repaired export; no new tool or license acceptance was needed. `recovery_docker_unavailable` and [the recovery prerequisite](hosted-recovery.md) now make this actionable. Future agents must check a nonempty `docker version --format` server version, not repeat sizing/tests or change sockets/install clients. Private release receipts, backup and key remain ignored.

**Validation discipline, explicit owner instruction on 19 November:** avoid unnecessary tests/checks and repeated validation. Run targeted checks for changed behaviour, reuse passing results and broaden/repeat only for new changes, failures or unresolved risk. Avoid repeated CI polling and live probes, especially during quota exhaustion. Preserve results and outstanding steps here for resumed agents.

## Deployed application

[Open Meridian](https://meridian-axis-session-gateway.meridian-worker-feasibility.workers.dev/) serves authenticated AXIS and HOLDINGS for two approved identities sharing one GBP Stocks ISA. Both users have equal application permissions. The separate [React preview](https://meridian-axis-preview.meridian-worker-feasibility.workers.dev) contains invented data.

- Session/gateway and sync source are **`e327fc9`**. Supabase native schema parity is **`0008`**, with 12 public tables and RLS enabled. Native GitHub migrations own hosted DDL.
- Trading 212 reported account/cash/position figures are authoritative. Exact decimal strings, separate retrieval windows, missing fields and unknown market quote age remain visible. Historical returns are unavailable.
- Scheduled refresh targets **ten minutes during relevant regular sessions**, per the 19 November owner amendment. Cron dispatch runs in the JavaScript gateway. Python Durable Objects execute bounded work, with PostgreSQL task leases, endpoint reservations and retry state. Unknown schedule coverage permits conservative polling.
- Manual refresh requires membership, session, Origin and CSRF checks. It queues a durable alarm promptly. Evidence, approved snapshot publication, success health and audit commit together. Failures preserve the last successful snapshot.
- The BFF reads approved snapshots and selected refresh-health columns. Raw imports, source evidence and event revisions remain closed to it. A separate restricted broker writer accesses only its fixed account and broker source kinds. Broker keys are held in managed secret bindings.
- The private browser client retrieves saved snapshots and health together every ten minutes while visible and exposes manual broker refresh. An older open client needs one reload to load that implementation. Authenticated SSE remains planned.

## History and import boundaries

Orders, dividends and cash transactions advance one family page per scheduled invocation, rotating families in ten-minute slots (at most one page per family per thirty minutes). Each family uses a one-hour cooldown anchored to its successful final-page attempt. Pagination may take longer, and lifetime completeness remains unverified. Running-page checkpoints and staging survive retries. Complete acceptance appends fill/reference revisions and deduplicates repeated observations. Corporate actions retain original facts with review quality states. A bounded local quantity diagnostic now replays supported signed trade observations; persisted economic replay, cash reconciliation and calculated performance remain open.

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

Owner amendment, 19 November: site availability takes priority; 60-day observation retention is approved as a fallback if 90 days cannot fit safely. The same conservative model projects 275–301 MB for 60 additional days. Ninety days remains the capacity target; the sixty-day detailed-refresh cleanup is implemented and deployed as recorded above. Hosted archive infrastructure remains deferred. Storage capacity does not establish runtime RAM safety; preserve bounded processing and do not claim crash prevention from disk sizing.

The measured-input [storage report](storage-capacity-report.md) is complete. Physical qualification remains open: ten-minute compressed retention may fit, but around-the-clock raw retention exceeds the database allowance. Hosted lossless archive infrastructure remains deferred; scheduled backups and independent key custody remain open. Detailed-refresh retention is deployed. Replacement hosted Auth/browser recovery and active-data credential rotation also remain open.

Other supported requirements include normalized ledger/cash/quantity reconciliation, verified transaction CSV aliases, group mapping/editing, daily prices/FX and approved closes, historical performance, projections, correlation/risk, remaining screens and alerts. Tax remains owner-deferred. The contracts in [the documentation index](README.md) retain those requirements.
