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

### macOS / zsh

The install/test commands above also work in zsh. The resumed macOS checkout passed **150 offline tests** with Python 3.12.16 and uv 0.13.7; ten PostgreSQL tests skipped without a disposable server. Ruff check and formatting check passed. Lockfiles were unchanged. Install uv using the linked installation guide; avoid using the system Python to resolve unlocked application dependencies.

Replace PowerShell's `$env:` assignments with shell exports when using the examples below:

```sh
export MERIDIAN_BROKER_ENVIRONMENT=demo
export MERIDIAN_DATA_DIR=private/runtime
```

Run these in the same shell as the local CLI/server. This configures local evidence tooling only; it does not set up hosted credentials or connect the broker. During the resume, tooling and a managed interpreter were installed under temporary storage; those temporary paths are disposable and are not a permanent laptop setup.

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

## Production qualification is separate

Cloudflare/Supabase is the approved hosted target. The SQLite CLI above remains local tooling. The [Python Worker probe](worker-feasibility.md) owns a separate lock/runtime and is not an application deployment. Source-backed PostgreSQL parity uses disposable test schemas; Supabase policies, hosted backup/restore, Auth, Hyperdrive request concurrency, job leases and resource budgets remain separate gates. Do not point test fixtures at a production project.

## PostgreSQL foundation verification

Migration `0002` preserves the published `0001` history. On PostgreSQL it repairs accepted-hash partial uniqueness, enables RLS and revokes default financial-table grants; on SQLite it advances the schema revision without changing evidence tables. Canonical Decimal text remains exact in both dialects. The native maintenance helpers require verified TLS except for an explicitly requested disposable loopback test server. They do not configure a Supabase project, Auth policies or a Worker Hyperdrive binding.

The default local suite skips ten `postgres` tests when `MERIDIAN_TEST_POSTGRES_URL` is absent (six foundation tests and four native Supabase migration tests). The service-backed CI job supplies PostgreSQL 17, creates unprivileged Supabase-like test roles and runs `uv run --locked pytest -m postgres -q`. Its fixtures create and clean up only generated isolated schemas in an explicit disposable loopback database. Do not use a production project URL: remote hosts are deliberately rejected by those fixtures. The Windows/Linux offline suite and the ten database-backed tests have passed in the recorded checkpoint; later hosted Supabase/Hyperdrive/Auth evidence is recorded in the current handoff; hosted logical export and isolated local Postgres restore are now qualified in [hosted recovery](hosted-recovery.md), with replacement hosted recovery still open.

The Postgres CI job selects Python 3.13 through `UV_PYTHON`, while the local foundation uses its pinned Python 3.12. Backend CI runs for backend/workflow changes; documentation and the isolated Worker prototype have their own recorded checks.

### Provider CA for private maintenance

`create_postgres_engine(..., ca_certificate=<verified PEM>)` can add a provider CA to the default trust context while retaining required certificate and hostname verification. The hosted direct connection required Supabase's provider CA during broker evidence qualification. Obtain it from the [official SSL configuration](https://github.com/supabase/supabase/blob/master/apps/studio/hooks/custom-content/custom-content.json); never trust the unverified peer certificate as a workaround. CA input is bounded/validated, cannot be combined with the disposable plaintext exception, and does not change the runtime Hyperdrive origin. Administrative credentials remain ephemeral/in memory; the application must keep using its restricted runtime connection.

## Excel baseline and broker secret provisioning

`python -m meridian.workbook_import_cli SOURCE --layout PRIVATE_LAYOUT_JSON` performs a read-only baseline preview. Add `--import` to accept into the already initialized configured local account. The layout explicitly maps six observations, group value/cost cells, date precision, notes and cumulative dividend cells. Keep source, layout and receipts private. `observed_month` records supported month precision and never supplies an invented day.

After the dedicated private sync Worker has been deployed and its restricted database origin verified, run the following from the repository root in a private interactive terminal. Confirm actual broker key permissions before using the flag.

```sh
backend/.venv/bin/python -m meridian.broker_secrets --confirm-read-only
```

Both key and secret use hidden prompts. The helper verifies the Cloudflare account and existing deployment before prompting, then passes the pair to Wrangler secret bindings through stdin. It suppresses provider output and disables Wrangler file logs. The pair stays outside command arguments, source files and the browser. Node/Wrangler authentication must already be available. The existing capture command remains a separate diagnostic reader and must not run concurrently with the production authority.
