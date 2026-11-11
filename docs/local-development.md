# Local development and recovery

Local evidence foundation and snapshot-import slice, verified on **11 November 2026**. This provides durable evidence infrastructure, maintenance commands and a liveness endpoint. It is not yet a usable portfolio app. No financial HTTP endpoints, users, scheduler or frontend exist at this checkpoint. The newly approved Cloudflare/Supabase production target is under qualification; these SQLite commands are local tooling, not hosted deployment instructions.

## Install and verify

Use Python **3.12** for the tested environment (project supports 3.12–3.14). The system's default Python may differ. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then from the repository:

```powershell
cd backend
uv sync --locked --python 3.12
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The lockfile pins dependency versions and artifact hashes. uv 0.13.7 was used for the initial lock and is pinned in CI. Ordinary tests use synthetic data and mocked transports; no broker credentials are needed. CI is configured for Windows and Linux; a workflow definition is not evidence of a remote run passing.

Configuration comes from the backend process environment, with `MERIDIAN_` prefixes. `.env.example` is a safe catalogue and is **not loaded automatically**. Credential validation errors never print input values through the CLI. Keep broker keys out of command history/source files; they are not needed by these commands.

## Initialise an isolated database

From `backend`, use the default `private/runtime` directory or an explicit private local directory. Every `private/` directory is ignored. Each broker environment has a separate database filename.

```powershell
$env:MERIDIAN_BROKER_ENVIRONMENT = 'demo'
$env:MERIDIAN_DATA_DIR = 'private/runtime'
uv run --locked meridian db-init
```

This applies the reviewed Alembic migrations and creates one GBP ISA account plus an audit record. It does not connect to Trading 212. Live requires explicitly setting the environment to `live`; do not do so merely to test migrations. A repeated initialisation preserves evidence and creates a verified pre-upgrade backup before applying migrations. Run maintenance with application writes stopped; HTTP startup never performs a schema upgrade.

For the foundation-only HTTP liveness check:

```powershell
uv run --locked uvicorn meridian.app:create_app --factory --host 127.0.0.1 --port 8000
```

`GET /health` returns only `{"status":"ok"}`. This is liveness, not database readiness or portfolio reconciliation. Stop with Ctrl+C. No private financial route exists. Secure local HTTPS and authenticated routes belong to Stage 2; this foundation HTTP command does not weaken their cookie contract.

## Backup and separate-path restore

The following names are examples, not automatic scheduled jobs:

```powershell
uv run --locked meridian backup private/backups/demo-checkpoint.sqlite3
uv run --locked meridian restore private/backups/demo-checkpoint.sqlite3 private/restored/demo.sqlite3
```

Backup uses SQLite's online backup interface, including committed WAL data. It writes a self-contained database and adjacent `.manifest.json` containing digest, schema revision, account scope and table counts. A 30-second copy deadline prevents an indefinite busy loop. Both files are private. Existing destinations are refused. A restore verifies the digest, integrity, foreign keys, schema/count controls and environment before restoring to a new file, then rechecks the copy. It never replaces the active database.

Stop writers before switching to restored storage; retain the original until validation is complete. Copy the complete verified backup/manifest to an agreed private off-host destination when hosting is selected. The manifest detects accidental corruption and mismatches; it is not an authenticated signature against a malicious administrator. Password/session recovery and financial-ledger controls will be added when those tables exist. No measured production recovery-time or backup schedule is claimed yet.

The installed package currently expects migrations from the source checkout; wheel-only deployment is not supported. Hosting will deploy a pinned checkout/build with its migrations, not an unverified standalone wheel.

## Holdings snapshot preview and evidence import

The verified holdings CSV format can now be validated and stored as immutable snapshot evidence. Use `preview-holdings` first with your **verified observation time and currency**; the file has neither field. The following path/time are placeholders that must be replaced, not inferred from an export filename:

```powershell
uv run --locked meridian preview-holdings '<private-export-path.csv>' --currency GBP --observed-at '2026-10-01T10:00:00Z'
uv run --locked meridian import-holdings '<private-export-path.csv>' --currency GBP --observed-at '2026-10-01T10:00:00Z'
```

Preview creates no database/run. Import requires an initialized database, records the attempted operation, validates before a short atomic evidence/audit commit, and logs safe failure categories after rollback. The final Total is retained as a source control, not a holding. Accepted identical account/kind/file hashes are rejected as duplicate attempts; CLI returns exit code 2 for duplicate/failed operations. Successfully accepted files retain their full SHA-256; oversized rejected input has no file hash because the CLI reads only a bounded prefix. Ordinary validation errors preserve safe row/column information without printing amounts. CLI summaries expose counts/status, not holding names or financial values.

This does **not** create trades, dividend payments, ledger holdings, reviewed group memberships or performance. It preserves ticker Slice and Total-row group context for the later mapping/reconciliation service. Actual financial sources were not imported into a runtime database during this checkpoint. The public tests use invented inputs; PDFs remain independently inspected evidence, with no supported PDF importer yet.
