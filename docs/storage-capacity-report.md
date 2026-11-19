# Ninety-day storage budget and retention proposal

Reviewed **19 November 2026**. Requirements: P02, L03, O01, QA02; question Q18. Status: **measured-input sizing report; production capacity and archive implementation remain unqualified**. Automatic refresh stays at ten minutes. This assignment changes documentation only.

## Minimal physical measurement — 19 November, 20:24 UTC

One read-only aggregate through the existing administrative transport measured the database at **52.25 MB**, about **10.5%** of the conservative 500 MB allowance. No Hyperdrive query, financial-value readout, test suite or live refresh was needed. Table/TOAST and index totals were returned in the same query. Source records occupy 23.81 MB (1.00 MB indexes), snapshots 12.39 MB (0.37 MB indexes); imports/audit occupy 2.17 MB combined. These relation totals are components of the database baseline, not additional allocations.

A limited sample of 50 refresh generations averaged **10,021 bytes** per stored source datum and **7,281 bytes** per projection, combined **17,302 bytes**. Their timestamps are 02:33–03:27 UTC on 19 November, preceding the ten-minute deployment; this does not verify subsequent refresh or login recovery. Snapshot table/TOAST/index allocation averages roughly 9.1 KB per estimated live row, so datum sizes alone understate physical cost. Statistics-based row counts and mixed source kinds do not establish an exact marginal generation cost.

Replacing the earlier baseline and generic compression assumption with these measurements gives **361.14–400.02 MB** for 90 additional around-the-clock days, using the existing metadata and 50 MB growth reserves and **assumed 2–5 KB row/index overhead per generation**. No expired rows are subtracted. This is conservative about existing history but still assumes stable payload sizes and reserve adequacy.

**Decision:** no immediate storage emergency or archive provisioning is needed at 52.25 MB. The modeled 90-day result remains below 500 MB but exceeds the proposed 350 MB operating ceiling. Full 90-day capacity is therefore still unqualified. Select a bounded retention/archive follow-up before committing to that retention guarantee; do not silently lower the ceiling, prune evidence or repeatedly remeasure now. Exact byte counts and relation statistics remain in the ignored private receipt. No further live checks are needed for this measurement task.

## Recommendation

Keep the present PostgreSQL runtime unchanged following the minimal measurement above. Ten-minute polling materially changes the earlier one-minute sizing: compressed payloads may fit, but compression cannot yet be relied on. Do not provision an archive or prune evidence based on this estimate.

Use a **proposed 350 MB operating ceiling** against a conservative 500 MB database allowance, leaving 150 MB for unexpected growth and maintenance. This is an engineering planning threshold, not an owner requirement or provider quota reservation. If measured growth projects above the ceiling, select a separate archive implementation task. Existing historical rows must be included before deciding that any design fits.

## Inputs and evidence limits

All units below use decimal MB (1,000,000 bytes). Existing private aggregate receipts from 13 November supplied these storage-only measurements. No portfolio values, identifiers or source hashes are published. No live SQL or new financial export was performed for this report.

| Input | Bytes | Meaning |
| --- | ---: | --- |
| Historical database baseline | 15,365,811 | Whole database at the earlier checkpoint; includes existing structures/data, not today's usage |
| Refresh source JSON | 34,997 | One measured summary/positions evidence payload |
| Approved projection JSON | 23,528 | One measured browser-safe snapshot |
| Combined raw generation | 58,525 | Source plus projection; excludes row/index/audit overhead |
| Generic compressed generation | 12,092 | Existing zlib rehearsal estimate; not a measured PostgreSQL or encrypted-archive size |
| Stored projection datum | 7,229 | Earlier `pg_column_size` result for one projection; excludes its surrounding heap/index/TOAST-table overhead |
| Held-listing metadata JSON | 96,999 | One selected metadata generation, refreshed daily |

These are single-sample inputs, not averages or bounds. The baseline predates subsequent minute polling, history imports and the 19 November change. Repeating captured payloads measures representative byte size only. New holdings, revisions and fields can increase it. Generic zlib and PostgreSQL TOAST need not produce the same size. Encryption/compression order, manifests and object framing add archive overhead.

## Ninety-day generation model

The illustrative window is **19 November 2026–16 February 2027 inclusive**, containing 64 weekdays. Weekday cases ignore exchange holidays, breaks and half-days. Eight/13-hour cases describe a portfolio's aggregate eligible-session window, not individual market hours. Unknown schedule coverage can permit polling around the clock, so the 24-hour case is the planning bound. It assumes no more than one successful generation per ten-minute slot; boundary jitter, manual attempts and retries still require a margin.

| Case | Generations | Refresh rows | Raw payload MB | Generic compressed MB | Row/index allowance MB |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8 hours, weekdays | 3,072 | 12,288 | 179.79 | 37.15 | 6.14 |
| 13 hours, weekdays | 4,992 | 19,968 | 292.16 | 60.36 | 9.98 |
| 24 hours, every day | 12,960 | 51,840 | 758.48 | 156.71 | 25.92 |

A successful refresh currently appends one import, one source, one snapshot and one publication audit row. The allowance above is **assumed at 2,000 bytes per generation across those four rows and their indexes**, in addition to payloads. It is not a physical measurement. Import/source/snapshot uniqueness and lookup indexes, audit indexes, tuple headers and TOAST storage must be counted. Sensitivity at 500–5,000 bytes/generation adds **6.48–64.80 MB** in the around-the-clock case, versus 25.92 MB centrally. Dead tuples, free-space/bloat, WAL and provider disk accounting are separate concerns.

For an illustrative whole-database envelope add the old 15.37 MB baseline, **8.73 MB** for 90 raw daily metadata payloads and a **proposed 50 MB combined reserve** for history growth, metadata row/index overhead, new imports/audit, sessions and operational growth:

| Case | Raw-envelope MB | Compressed-envelope MB |
| --- | ---: | ---: |
| 8 hours, weekdays | 260.03 | 117.39 |
| 13 hours, weekdays | 376.24 | 144.44 |
| 24 hours, every day | 858.50 | 256.73 |

The reserve is an assumption, not measured coverage. History pages advance at most once per family per thirty minutes, with the existing one-hour completed-traversal cooldown. Pages retain raw evidence even when revision deduplication adds no new events. New/revised events append further rows. The 50 MB reserve could be exceeded, and existing history in the baseline must not be counted as new growth again. Failed jobs, bootstrap imports, auth/session churn and long-lived audit/index growth also need measurement.

**Result:** uncompressed around-the-clock retention exceeds 500 MB before a safe margin. The compressed scenario falls below the proposed 350 MB ceiling, but does not prove fit. Under these assumptions the maximum average physical refresh-generation cost is **21,288 bytes**, including its four rows/indexes, to stay under 350 MB. Recompute that threshold using the current baseline and measured non-refresh growth. Logical JSON length, a single `pg_column_size`, and SQL query quota are different metrics.

## Provider allowances checked for this report

Supabase lists **500 MB database size per Free project**, **1 GB file storage** and **5 GB egress**. File storage is separate from the database allowance. Use the provider's dashboard usage definition for the final capacity decision; the 500,000,000-byte working cap here is conservative. [Supabase pricing](https://supabase.com/pricing), [disk accounting](https://supabase.com/docs/guides/platform/manage-your-usage/disk-size), [egress accounting](https://supabase.com/docs/guides/platform/manage-your-usage/egress).

R2 Standard includes **10 GB-month**, **one million Class A** and **ten million Class B operations/month**, with direct R2 egress free. Infrequent Access does not receive that free tier. These are allowances, not a guarantee against overage billing or confirmation that R2 is enabled on this account. [R2 pricing](https://developers.cloudflare.com/r2/pricing/).

## Conditional archive proposal

If physical sizing fails the operating ceiling, retain **seven days of refresh payloads in PostgreSQL** and move older eligible immutable refresh payloads into **encrypted daily blocks**, preserving the full 90-day logical observation window. Seven days is a proposed hot tier, not shortened retention. Latest snapshot, durable jobs/rate state, membership/session controls and a compact archive catalogue remain in PostgreSQL. Daily closes retain their indefinite policy. Ledger events, revisions, Excel/CSV evidence and financial audit must not inherit a blanket 90-day deletion policy.

For the maximum modeled rate, seven hot days contain **58.99 MB raw** refresh payloads. The other 83 days contain **699.49 MB raw**, or **144.52 MB at the generic compression estimate**, before manifests/encryption/history/backups. One raw day is about 8.43 MB. Actual encoded block sizes and safe Worker memory/CPU still need qualification.

Prefer evaluating a private bucket in the existing Supabase project first if its unused 1 GB allowance, total backup footprint and egress permit it. R2 Standard is the fallback capacity candidate if that budget fails; enabling it and any billing configuration need separate selection under the free-only constraint. No bucket or service is created by this report. One block plus one manifest daily would be roughly 60 object writes/month before retries; splitting blocks and re-uploads increase that. Reads must follow measured usage, not the large free allowance alone.

Required implementation properties:

- **Exact evidence and precision:** compress original accepted payload bytes without parsing/re-encoding financial decimals. Include source/import/snapshot IDs, schema versions, retrieval/session times, byte counts and plaintext/ciphertext checksums in a private versioned manifest. Preserve revisions and group/FX provenance where present.
- **Safe publication:** upload under a unique immutable key, authenticate/decrypt/read back, verify checksums and record counts, then atomically publish the catalogue entry. Failed uploads remain unavailable. A catalogue failure leaves an orphan blob for later reconciliation; it must never justify deleting the source.
- **Authorized retrieval:** use existing server-side membership/session checks for date ranges, bounded pagination/decompression and private reads. Reconstruct approved projections with their quality/freshness; no public buckets, browser credentials or silently missing archived observations.
- **Migration and references:** current source/audit mutation guards, restricted-role grants and import/source foreign keys prevent a simple cleanup cron. A reviewed native migration and catalogue/reference design are required before relocating payload storage. Preserve stable source identities and audit links. No broad DELETE grant, disabled immutability trigger or pruning is authorized here.
- **Keys and corruption:** authenticated encryption with unique nonces and versioned key IDs; keep keys separate from buckets and maintain an independently recoverable copy. Key rotation must keep old blocks readable. Reject corrupt, truncated, missing, oversized or wrong-account blocks.
- **Backup and restore:** maintain a consistent database catalogue plus immutable object inventory and a second encrypted copy outside the primary project's failure domain. Restore into an isolated target using separately recovered keys; verify all referenced blocks, exact decimal strings, row/checksum controls and access denials. Existing `0007` backup verification is not an archive restore drill. The current hosted backup helper refuses nonempty Storage, so it must be extended before a Storage-based archive goes live.

This is substantial follow-up implementation, outside the report assignment. Do not begin it automatically or delete existing evidence.

## Egress and backup budget

Archive placement does not remove all transfer costs. At 144 daily runs, reading the measured projection and metadata once each per run is roughly **0.52 GB/month** of logical database result payload, before protocol/history/auth traffic. Two clients visible eight hours daily would add about **0.068 GB/month** of snapshot JSON before health/headers. These are scenario estimates; actual sessions, compression and database query results differ. Exporting every raw generation once adds roughly **0.253 GB/month** before metadata/history/manifests.

Backups can dominate: downloading a 350 MB logical dump daily would transfer **10.5 GB/month**, exceeding a 5 GB allowance by itself. Physical database size is not dump size; measure the actual export stream. Encryption after download does not reduce source egress. Neither generic payload compression nor R2's free outbound transfer proves the whole backup route is free.

A later backup task must choose RPO/RTO, full/incremental cadence, retention and independent key custody using actual dump/object sizes. Do not promise daily backups within the free tier from these estimates. Copies, restores and archive retrievals share the relevant allowances. A retained archive in the same project is not an independent backup.

## Reproduce the arithmetic

Run this standard-library-only calculation from the repository root. It uses storage aggregates only, contacts no service and needs no source file or credentials:

```sh
python3 - <<'PY'
from datetime import date, timedelta
start = date(2026, 11, 19)
weekdays = sum((start + timedelta(days=i)).weekday() < 5 for i in range(90))
base, raw, compressed, metadata = 15365811, 58525, 12092, 96999
for label, n in [('8h', weekdays*48), ('13h', weekdays*78), ('24h', 90*144)]:
    extra = base + 90*metadata + 50_000_000 + n*2000
    print(label, n, 4*n, *(round(x/1e6, 2) for x in
          (n*raw, n*compressed, n*2000, extra+n*raw, extra+n*compressed)))
print('generation ceiling:', (350_000_000-base-90*metadata-50_000_000)//12960)
PY
```

The existing aggregate receipts already measured payload lengths, generic compression and the earlier database/projection sizes. Re-running their financial rehearsals is unnecessary for this report. Arithmetic was calculated once locally; no application tests, CI, restore drill or live SQL was run.

## Unresolved inputs and smallest next action

Current baseline and per-table heap/index/TOAST growth; representative source compression and larger payloads; retained history/revision volumes; precise source-retention policy; manual/retry excess; calendar coverage; actual dump/backup size and egress; bucket/account availability and other usage; archive CPU/memory, retrieval and key recovery remain unverified. This report cannot close Q18 or operational acceptance.

The selected **one bounded aggregate measurement** above is complete. It returned current database/table/index/TOAST sizes and a limited recent-generation sample as byte counts only. No broker calls were replayed. Provider dashboard accounting and future marginal growth were not separately measured. Reuse the existing source receipts and CI. The result supports no immediate storage intervention, while the 90-day safety-margin gate remains open. No implementation task is activated by this recommendation.


## Owner-approved fallback — 19 November 2026

Availability takes priority. The owner permits reducing observation retention from 90 to **60 days if necessary** to maintain safe capacity. Ninety days remains the target; this is fallback authority, not an implemented cleanup policy. With the measured baseline and the same conservative 50 MB growth reserve, 60 additional around-the-clock days project to approximately **275–301 MB**, using assumed 2–5 KB per-generation overhead. This is below the proposed 350 MB operating ceiling, subject to payload/history growth and actual provider accounting.

Before expanding into archive infrastructure, consider the approved 60-day fallback through a bounded retention implementation proposal. Existing immutable evidence guards, source references and indefinite financial audit/daily-close requirements still need explicit handling; do not apply a blanket deletion rule. No pruning or runtime configuration changed with this approval. Database capacity and Worker memory are distinct: these storage estimates do not qualify peak RAM, large history traversals or archive compression memory.
