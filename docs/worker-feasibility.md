# Python Workers feasibility evidence

Reviewed **11 November 2026**. The owner selected Cloudflare + Supabase, with free services only. The original local experiment below used no account, hosted deployment, credentials or database. The resumed hosted experiment now verifies synthetic response compatibility but **does not qualify ordinary Free CPU fit**. Neither experiment establishes production readiness.

## Hosted result after resume

The owner completed Wrangler OAuth device authorization with credentials held in macOS Keychain. Direct CLI deployment of source commit `53cd2ab40aaa18d6c11bca51f907520ad96f7fac` succeeded:

- URL: `https://meridian-axis-probe.meridian-worker-feasibility.workers.dev`.
- Version: `bca2d322-ba23-45f8-bc51-465c49bb56db`; provider version inspection matched the source annotation, `2026-11-11` / `python_workers`, and empty bindings.
- Upload: **19,927.56 KiB / 4,660.05 KiB gzip**. Reported startup: **4,424 ms**; upload and trigger deployment exited successfully. The accepted metric is not a measured request cold start or a rejected startup.
- Native GitHub Builds remains unconnected. This deployment used the authorised local CLI, without changing Supabase's schema writer.

After the newly created workers.dev subdomain finished TLS propagation, three controlled hosted smoke passes verified `/health` and `/probe` HTTP 200 with exact expected JSON and POST `/probe` HTTP 405. The default `Python-urllib` user agent received 403; identifying the synthetic client as `MeridianAxis-SyntheticProbe/1.0` resolved that failure without changing server access controls or disabling TLS verification. The client identification fix and eight offline regression tests were checked separately from the deployed Worker code.

`wrangler tail meridian-axis-probe -c wrangler.probe.jsonc --format json` returned actual timing fields for the matching version:

| Controlled invocation | Run 1 CPU / wall ms | Run 2 CPU / wall ms | Run 3 CPU / wall ms |
| --- | --- | --- | --- |
| GET `/health`, 200 | 50 / 51 | 15 / 16 | 8 / 8 |
| GET `/probe`, 200 | 617 / 619 | 375 / 376 | 64 / 65 |
| POST `/probe`, 405 | 13 / 13 | 5 / 5 | 5 / 5 |

All nine outcomes were `ok`, with no reported exception. These are provider CPU measurements for fixed synthetic checks, not representative authenticated financial workloads. Cloudflare documents **10 ms** for ordinary Free HTTP requests and allows occasional bursts; successful responses above that budget do not prove sustained fit. The current Python/FastAPI path therefore remains **unqualified for ordinary Free CPU**. A native Python-handler control is next, with a Python Durable Object candidate only if separately measured and accepted. Python is not being silently replaced with browser formulas. [Worker CPU limits and burst behavior](https://developers.cloudflare.com/workers/platform/limits/#cpu-time)

No account plan upgrade was made. Account billing plan and memory are not established by the runtime `standard` usage model or these outcomes. The 4,424 ms deployment diagnostic also needs interpretation against Python's snapshot lifecycle rather than being called a startup rejection. [Python runtime lifecycle](https://developers.cloudflare.com/workers/languages/python/how-python-workers-work/)

Raw tail events include request/client metadata and stay in ignored private diagnostics. Public records retain only synthetic method/path/status, version, CPU/wall and outcome. In Wrangler 4.160.1, explicit `--sampling-rate 1` is rejected; omit that option for the default stream. Stop the temporary tail after the bounded measurements.

The validator [Linux/macOS CI run](https://github.com/dhdylanhuang/meridian-axis/actions/runs/43115439729) passed for the source checkpoint. No backend code or schema changed in that delivery; the separately observed Supabase emitted check passed. Database/Auth/job/analytics/retention/recovery gates remain open.

## Separate runtime controls

The CPU finding warrants bounded synthetic controls before choosing the application runtime. All reuse the original `main.py` workload and the existing dependency locks; they contain no portfolio input or credentials.

| Configuration | Purpose | Boundary |
| --- | --- | --- |
| `wrangler.native-probe.jsonc` | `meridian-axis-native-probe`: native Python fetch calls the same `health`/`probe` functions for every request | Public synthetic GET routes; no bindings; no cached calculations |
| `wrangler.do.jsonc` | `meridian-axis-do-probe`: existing FastAPI app inside a Python Durable Object | No workers.dev route; default entrypoint rejects requests; namespace binding only |
| `wrangler.gateway.jsonc` | `meridian-axis-do-gateway`: small JavaScript gateway to that object | Public fixed GET routes; no forwarded caller headers/body/query; other methods rejected |

The Durable Object's migration creates a **SQLite-backed runtime namespace**, required for Free eligibility, but the control makes **no storage calls**. This is not a Supabase migration or an application database; Supabase remains the sole application persistence target and native SQL remains its schema writer. Python Durable Objects and external namespace bindings are supported by the inspected provider SDK/configuration. [Python Durable Objects](https://developers.cloudflare.com/changelog/post/2025-05-14-python-worker-durable-object/), [namespace configuration](https://developers.cloudflare.com/workers/wrangler/configuration/#durable-objects), [Free namespace eligibility and quotas](https://developers.cloudflare.com/durable-objects/platform/pricing/)

The Durable Object limit table documents a separate default CPU allowance, while other provider wording refers to ordinary Worker limits. This control is a qualification candidate, not an accepted guarantee of Free capacity. Measure both the gateway's stateless CPU and the object's CPU/outcomes, then assess daily request/duration quotas, memory, database behavior and recovery before adopting it. [Durable Object limits](https://developers.cloudflare.com/durable-objects/platform/limits/)

Prepared checks: **11 Python tests passed** (eight validator and three native-routing/delegation cases), **four Node gateway tests passed**, and scoped Ruff passed. Native routing uses SDK doubles; only workerd/hosted execution proves the SDK bridge. The gateway tests verify route/method/input rejection and that forwarded requests contain no caller credentials or body. CI now includes both suites for all probe-source/config changes.

Dry-runs exited 0 without deployment: native **19,928.18 KiB / 4,660.62 KiB gzip**, no bindings; Python object **19,928.85 KiB / 4,660.84 KiB gzip**, only its expected namespace binding; gateway **0.76 KiB / 0.40 KiB gzip**, only its expected external namespace binding. The initial native/gateway runs encountered sandbox denial for Wrangler's external log file; subsequent object/gateway checks used an explicit temporary `WRANGLER_LOG_PATH` and had no such warning. These results establish bundle preparation, not a hosted migration or runtime result.

Use the native probe config for its separate pinned deployment. For the Durable Object candidate, deploy the namespace-owning Python config with Pywrangler **before** deploying the gateway config with Wrangler. Never deploy the Python config as an application route or attach application secrets to these public controls.

## Original local result

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

On macOS/zsh use `npm ci` instead of `npm.cmd ci` and `export WRANGLER_SEND_METRICS=false` instead of the PowerShell assignment. The other `uv` commands are the same. Keep backend and probe environments separate: backend verification uses Python 3.12, while the probe toolchain requires Python 3.13 or later. Locked Wrangler/Miniflare require **Node >=22.12.0**; use the configured hosted Node 24.22.1 to align tooling. The Mac's system Node is 20.18.1; the resumed qualification installed Node 24.22.1 in ignored project tooling without changing the system installation.

The resumed macOS dry-run used Node 24.22.1, npm 10.8.2, uv 0.13.7 and native Python 3.13.5, retaining all three probe lockfiles. Pywrangler selected native Python 3.14.3 and Pyodide Python 3.14.2 for its separate Worker environments. The explicit probe configuration dry-run exited **0**, reporting **19,927.56 KiB uncompressed / 4,660.05 KiB gzip**, 1,448 vendored modules, **No bindings found** and **exiting without deployment**. Small bundle-size differences from the historical Windows result are recorded rather than treated as hosted runtime measurements.

The same Mac then ran the original loopback configuration with `pywrangler dev --local --ip 127.0.0.1 --port 8791 --inspector-port 9231`. `.venv/bin/python smoke_test.py --timeout 20` passed against the actual Worker. Download and loopback execution permissions were needed in the restricted sandbox. No database or external provider was contacted by these local checks.

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

## Prepared public probe through Cloudflare-native Builds

Preparation checkpoint: **11 November 2026**. A separate `wrangler.probe.jsonc` now describes a Worker named `meridian-axis-probe`, using the same synthetic source, compatibility date and Python flag. It enables a workers.dev URL, disables preview URLs and telemetry, and supplies **no** database binding, secrets, assets, custom-domain route, account ID or financial endpoint. The original local-only `wrangler.jsonc` is unchanged. No hosted deployment was made by this preparation.

This public probe is harmless diagnostic content: fixed invented decimals, package versions, a compiled SQL string and mock HTTP output. It accepts no declared portfolio input and opens no database or provider connection. Do not attach Trading 212, Supabase, database or other application credentials. Its `synthetic-local-only` response label is the original fixture label, not evidence about where a later request executed. Actual portfolio data and authentication belong to the separate application work.

Configure a **Worker** with Cloudflare-native Workers Builds, rather than a Pages static site. The owner connects GitHub on their own device and authorizes the Cloudflare Workers & Pages App for only this repository. Cloudflare manages its build deployment credential; it is not copied to this workspace or chat. The Worker name selected in the dashboard must match `meridian-axis-probe`. [Native GitHub integration](https://developers.cloudflare.com/workers/ci-cd/builds/git-integration/github-integration/), [Build configuration and managed credential](https://developers.cloudflare.com/workers/ci-cd/builds/configuration/)

| Workers Builds setting | Prepared value |
| --- | --- |
| Repository | The existing `meridian-axis` repository |
| Production branch | `main` after the parent has published the reviewed probe configuration |
| Root directory | `prototype/worker-feasibility` |
| Build command | `npm ci && uv sync --frozen --python 3.13` |
| Deploy command | `uv run --frozen pywrangler deploy -c wrangler.probe.jsonc` |
| Non-production branch/preview builds | Disabled for this bounded probe |
| Runtime variables/secrets/bindings | None |

Build variables are non-secret tool configuration, separate from Worker runtime variables:

| Build variable | Value / reason |
| --- | --- |
| `SKIP_DEPENDENCY_INSTALL` | `1`; use the explicit frozen install command above |
| `PYTHON_VERSION` | `3.13.18`; native build/tool interpreter; Pywrangler selects its own WebAssembly runtime |
| `NODE_VERSION` | `24.22.1`; current documented preinstalled Node version |
| `WRANGLER_SEND_METRICS` | `false`; disable CLI telemetry |

The current Workers Builds image documents Python/Node version overrides, preinstalled uv 0.13.4, and the dependency-install skip variable. Pywrangler 1.17.9's installed CLI source requires uv **at least 0.13.4**, so the documented image meets its version check. This investigation ran locally with uv 0.13.7; the remote Linux build and selected overrides have **not** been executed yet. There is no documented `UV_VERSION` override in the inspected build-image table; do not invent one. The current Python Workers package guide requires Python >=3.13 for development tooling. [Build image and variables](https://developers.cloudflare.com/workers/ci-cd/builds/build-image/), [Python package tooling](https://developers.cloudflare.com/workers/languages/python/packages/)

An optional build watch path can restrict rebuilds to `prototype/worker-feasibility/**`; leaving watch paths at their default is acceptable for the initial connection. It is an optimisation, not an authorization boundary. Never use a preview build to bypass application security gates.

### Configuration verification

Wrangler 4.160.1's local `deploy --help` confirms `-c, --config` selects a configuration file and `--dry-run` bundles/checks without upload. The checked command is:

```powershell
uv run --frozen pywrangler deploy -c wrangler.probe.jsonc --dry-run --outdir dist/probe
```

With telemetry disabled, that local dry-run exited **0**, selected the explicit probe config, reported **19,927.58 KiB uncompressed / 4,663.03 KiB gzip**, reported **No bindings found**, and exited without deployment. Dependency download permissions were required locally; no Cloudflare account lookup, login or credential was used. The existing three dependency locks remain the basis for the probe.

After the owner connects the project, verify the real build's commit/config, successful upload, actual workers.dev URL and `/health` plus `/probe` responses. Do not guess the account's workers.dev suffix. A hosted HTTP 200 establishes only this synthetic path; it does not prove representative authenticated imports, market polling, database transactions or correlation meet Free CPU/memory limits. Record actual hosted CPU measurements and error outcomes separately before accepting that gate.

### Repeatable response validation

The standard-library validator now accepts an explicit hosted origin, while retaining the loopback default. After obtaining the real URL from the provider, run from the probe directory (replace the uppercase placeholder):

```sh
python3 smoke_test.py --origin https://meridian-axis-probe.ACCOUNT.workers.dev --timeout 20
```

No Worker toolchain or account credentials are required by this script. It checks exact synthetic Decimal strings, mock HTTP/SQL diagnostics and POST rejection. It accepts only HTTP loopback with an explicit port or HTTPS workers.dev origins, refuses credentials/paths/queries/fragments and redirects, ignores environment proxies, bounds response size and socket timeout, and redacts network error details. Socket timeout is not an overall invocation deadline or a CPU measurement. It makes no database connection and cannot verify a deployment's source SHA; inspect the actual Cloudflare build record separately.

Offline regression checks use an ephemeral loopback server with invented payloads:

```sh
python3 -m unittest discover -s tests -v
python3 -O -m unittest discover -s tests -v
```

Eight tests passed on macOS, including malformed/oversized responses, wrong decimal/boolean types, mutation-route acceptance, redirects, URL/timeout validation and safe failure messages. The validator CI workflow runs on Linux/macOS with Python 3.13; actual completed results are linked above. Loopback socket binding required execution permission in the restricted development sandbox. Hosted response and CPU evidence is separately recorded above; the response script itself does not measure CPU.

### Authorised direct CLI path

After resuming, the owner requested a direct Cloudflare connection and approved Wrangler's device authorization in their browser. `wrangler login --device --browser=false --use-keyring` succeeded; `wrangler whoami --json` verified account access without copying credentials into the repository or chat. The account's email/name are omitted from public evidence. This makes direct pinned CLI deployment an authorised alternative to the unconnected native Builds flow above; it does not alter Supabase's migration authority.

Publish the reviewed checkpoint before deployment, use `uv run --frozen pywrangler deploy -c wrangler.probe.jsonc --message <source-commit>`, and record the returned deployment/version and actual URL. Only the dedicated synthetic probe is in scope. Do not attach database/broker credentials, create paid services, or infer free-runtime qualification from a successful upload.
