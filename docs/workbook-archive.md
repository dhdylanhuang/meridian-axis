# Manual workbook archive

Owner-selected **19 November 2026**. The existing portfolio workbook now has an **AXIS Archive** sheet. Its eleven original sheets and their formulas/native parts were preserved. Initial export copied **1,360 retained broker-refresh generations**. The workbook and a pre-change copy remain private and ignored by Git.

From the repository root, with Excel closed:

```sh
python3 tools/archive_workbook.py --config private/workbook-archive/config.json
```

The ignored local config identifies the workbook, authenticated Supabase CLI, project, initial layout template and original-file backup. Ordinary subsequent exports need Python's standard library and the existing CLI only; no temporary virtualenv, spreadsheet package or Docker service is required. The command reads immutable records in pages through the management CLI, without Hyperdrive, broker API calls or database writes. It appends new generations using their creation timestamp and ID, checks source/archive hashes and skips duplicates.

The visible columns show observed UTC and account values in GBP. Summary numbers use Excel's numeric precision and two-decimal display. Exact original source/projection JSON, including decimal strings, separate retrieval times, holdings, identity/provenance and hashes, is retained in numbered text chunks on the same row. Chunks respect Excel's cell-length limit. Repeated exports also support Excel's shared-string representation after a native save. Do not edit archive rows or raw JSON chunks.

**Run at least monthly**, before detailed observations reach sixty days. This is a manual local copy, not an automatic hosted archive or a deletion checkpoint. Cloud cleanup does not wait for the workbook. Already-expired detail cannot be recovered by this command; daily observations remain protected in the database. The website does not read this local file or gain a historical-performance screen from this export.

Writes are staged and replaced atomically only if the workbook has not changed during export. Original ZIP parts are copied unchanged except the new sheet registrations and appended styles. A private pre-archive copy is retained; no blanket re-export or recalculation of existing formulas occurs. A visible Excel lock, source/checksum failure or capacity limit stops without replacing the workbook. Excel row/cell limits and a 256 MiB uncompressed archive/shared-string guard prevent indefinite growth; select another workbook if that guard is reached rather than silently dropping rows. This utility does not change the sixty-day hosted policy or establish an independent encrypted backup.

Verification: one synthetic precision/Unicode/chunking and duplicate-repeat check, one Excel shared-string compatibility check, built-in legacy-part preservation checks during the real export and one visual review of the new view. No backend suite, CI, deployment or production mutation was needed. The original financial workbook/data and private config must not be committed.
