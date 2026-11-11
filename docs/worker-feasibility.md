# Python Workers feasibility evidence

Reviewed **11 November 2026**. The owner selected Cloudflare + Supabase, with free services only. This bounded synthetic experiment verifies **local runtime compatibility**, not production readiness or the free-tier CPU budget. No Cloudflare account/login, hosted Worker, Supabase project, credentials, external provider request or database connection was used.

## Result

The [isolated prototype](../prototype/worker-feasibility/README.md) runs in local Wrangler/workerd using Python Workers' Pyodide runtime. `GET /health` and `GET /probe` returned HTTP 200; the smoke script verified exact Decimal values, canonical string output, Pydantic serialization, synchronous SQLAlchemy PostgreSQL dialect compilation, pg8000 import and HTTPX with an in-process mocked transport. `POST /probe` returned 405.

This supports continuing with Python/FastAPI as a reuse candidate. It does not establish that the current application can be hosted unchanged: SQLite persistence, resident jobs, local file imports and backups need explicit hosted equivalents. Full financial workload capacity and the actual Postgres/Auth path remain gates.

## Reproducible source and tooling

The prototype owns its dependencies and does not modify `backend` manifests. `uv.lock` pins native development tooling; `pylock.toml` pins the Workers-compatible runtime wheels; `package-lock.json` pins Wrangler/workerd dependencies. Generated environments, vendored packages, runtime state and bundles are ignored locally. Pywrangler uses its runtime lock to constrain subsequent resolution unless explicitly upgraded; review lock changes before accepting a refreshed result.

| Item | Verified version / configuration |
| --- | --- |
| Host tools | Windows, Node 26.13.0, uv 0.13.7 |
| Native tool environment | Python 3.13.18; Pywrangler 1.17.9; Workers runtime SDK 1.9.6 |
| Worker tool-generated environment | Native Python 3.14.10; Pyodide Python **3.14.2** |
| Wrangler | 4.160.1 |
| Compatibility | `2026-11-11`, `python_workers` flag |
| Runtime packages exercised | FastAPI 0.162.4, Pydantic 2.14.3, HTTPX 0.28.1, SQLAlchemy 2.1.8, pg8000 1.31.6 |
| Network boundary | Loopback `127.0.0.1:8791`; no remote bindings; workers.dev/previews disabled |

The native development interpreter is not the Worker interpreter. Pywrangler automatically downloaded its matching native and WebAssembly environments; the probe response confirmed the actual Worker Python version. These were isolated tool installations, not global runtime upgrades.

With `uv`, Node and npm available on PATH, run from `prototype/worker-feasibility`:

```powershell
npm.cmd ci
uv sync --frozen --python 3.13
$env:WRANGLER_SEND_METRICS = 'false'
uv run --frozen pywrangler dev --local --ip 127.0.0.1 --port 8791 --inspector-port 9231
```

In a second terminal from the same directory:

```powershell
uv run --frozen python smoke_test.py
```

Stop the local server, then measure the bundle without uploading:

```powershell
uv run --frozen pywrangler deploy --dry-run --outdir dist
```

The actual investigation invoked `.venv/Scripts/pywrangler.exe` directly after `uv sync`, with the isolated uv tool on PATH; the commands above select that same locked environment. Initial execution failed safely with `Command not found: uv` until PATH was configured. Network permission was needed to download tooling/packages, not to authenticate or deploy. Local development succeeded after setup; no platform workaround or account was required.

## Observed checks

| Check | Observed result | What it does not prove |
| --- | --- | --- |
| Loopback `/health` | 200, synthetic-local-only scope | Hosted routing, auth or availability |
| Decimal input | Quantity `0.125000000000000000000001`, price `12.40` | Full valuation, portfolio reconciliation or browser arithmetic |
| Decimal result | Exact `1.55000000000000000000001240`; canonical `1.5500000000000000000000124` | Database numeric round-trip |
| Pydantic output | Quantity/price remain JSON **strings** | All application response schemas |
| SQLAlchemy + pg8000 | Both import; synchronous PostgreSQL dialect compiles `SELECT %s AS anon_1` | TCP/TLS, Supabase pooler, transactions, migrations, ORM queries or RLS |
| HTTPX | AsyncClient request succeeds against MockTransport | Real Worker outbound HTTPS, broker Basic auth or provider quota handling |
| Method boundary | POST to the probe returns 405 | Application authorization, which is absent in this synthetic probe |
| Reproducible script | `Synthetic local worker checks passed; hosted CPU and database remain untested.` | Production acceptance or a hosted performance test |
| Final local dry-run | Exit 0, no bindings, explicitly exited without deployment | Account-specific deploy/startup validation |
| Source quality | Scoped Ruff format/check passed for the two prototype Python files | Existing backend tests do not exercise this Worker |

Final dry-run output: **19,927.58 KiB uncompressed**, **4,663.03 KiB gzip**, including 1,448 vendored modules. The current official limits page states a **64 MiB uncompressed** Worker bundle limit on both Free and Paid, with no compressed-size limit. This prototype fits that documented bundle limit. It is a small compatibility probe; adding analytics/data libraries changes size and memory. Recheck limits at deployment. [Cloudflare bundle and runtime limits](https://developers.cloudflare.com/workers/platform/limits/)

## Runtime constraints and package assessment

Cloudflare documents FastAPI using the Workers ASGI adapter and packages managed by Pywrangler. Pure Python and appropriate PyEmscripten/Pyodide wheels are supported; ordinary Windows/Linux binary wheels are not interchangeable with WebAssembly wheels. The prototype runtime lock selected a PyEmscripten Pydantic core wheel and a pure-Python SQLAlchemy wheel. [FastAPI entrypoint](https://developers.cloudflare.com/workers/languages/python/packages/fastapi/), [package support](https://developers.cloudflare.com/workers/languages/python/packages/)

Cloudflare lists pg8000 among supported Python Hyperdrive drivers, requires a sufficiently recent compatibility date, and currently supports synchronous SQLAlchemy rather than its greenlet-dependent async ORM. Its guidance serializes synchronous database operations with an asyncio lock. This is supporting provider documentation, not proof that our unconnected dialect probe has executed a transaction. Define a request-scoped unit of work and verify concurrency against a real disposable Postgres database before porting application imports. [Python database drivers and concurrency](https://developers.cloudflare.com/hyperdrive/examples/python-workers/)

The runtime filesystem is ephemeral and isolates do not share files. Threading/multiprocessing are not functional as normal native worker processes. Keep explicit Cron/job leases and durable external persistence; do not embed the SQLite database or run an in-process APScheduler in this Worker. Decimal is supplied through its WebAssembly C implementation. [Python standard-library limits](https://developers.cloudflare.com/workers/languages/python/stdlib/)

NumPy, pandas, SciPy and scikit-learn appear in the current Pyodide package catalog, so their native code is not automatically a reason to reject Python Workers. **They were not installed, bundled, imported or benchmarked in this probe.** Availability in the catalog does not prove compatible versions, 128 MB memory fit or CPU suitability for the planned correlation workload. [Current Pyodide packages](https://pyodide.org/en/stable/usage/packages-in-pyodide.html)

yfinance currently declares dependencies including `curl_cffi`, lxml, NumPy, pandas and websockets. It is not a pure-Python HTTP wrapper that can be assumed portable unchanged. Its complete Workers wheel resolution and real network behavior remain unverified; this experiment makes no claim that it works or is impossible. Keep the narrow market-provider interface and verify the chosen source before introducing a replacement or reducing requested coverage. [yfinance dependency manifest](https://github.com/ranaroussi/yfinance/blob/main/pyproject.toml)

## Unresolved hosted gates

1. **Free runtime CPU and memory:** current Free limits include 10 ms CPU per HTTP/Cron invocation and 128 MB memory. Local elapsed request times include tool/runtime overhead and are not hosted CPU measurements. Profile actual authentication, Decimal parsing, import validation, sync and a representative correlation calculation in the intended hosted environment before promising fit. Network waiting is different from CPU consumption. [Runtime limits](https://developers.cloudflare.com/workers/platform/limits/)
2. **Actual database behavior:** prove exact Decimal-string/Postgres numeric round-trip, committed and rolled-back import generations, dedupe races, immutable evidence/audit guards, timezone round-trip, pooler/TLS behavior and source-backed restore. A successful `create_engine` without `connect` is not any of these tests.
3. **Private request boundary:** establish the two Supabase identities, explicit portfolio membership, anonymous/nonmember rejection and chosen session/CSRF model. No real financial route should use this prototype's unauthenticated probe design.
4. **Scheduled execution:** replace process-resident sleeps with durable retry-not-before times/checkpoints and job leases. Verify market calendars and polling provenance. No Cron, scheduled batch, SSE/Realtime channel or retry dispatcher was tested here.
5. **Retention/capacity:** measure intraday layout, indexes, logs, backups and lossless retention against Supabase Free quotas. A compatible Worker does not settle storage sizing.
6. **Startup and remote network:** dry-run does not report actual deployed snapshot startup validation, account quota behavior or a real broker/market request. These require the approved project/account setup and private credentials configured through the appropriate secret mechanism.

The next shared contract is therefore the **hosted request/unit-of-work and job boundary**, preserving the existing pure calculations and source-evidence invariants while deliberately replacing local storage/session/job plumbing. The parent architecture decision should name which existing backend parts remain reusable and which are still local-only. Keep the application backend and this probe distinct until those gates pass.
