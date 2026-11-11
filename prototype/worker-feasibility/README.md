# Python Worker compatibility probe

Synthetic compatibility investigation. This is **not** the application or its production entrypoint. It contains no credentials, broker data or database connection.

See [the feasibility evidence and run instructions](../../docs/worker-feasibility.md). Keep `.venv*`, `.wrangler`, `python_modules`, `node_modules` and `dist` out of version control. Preserve the three dependency lockfiles when reproducing the result.

Two configurations have deliberately different purposes:

- `wrangler.jsonc`: existing loopback development configuration; workers.dev and preview URLs disabled.
- `wrangler.probe.jsonc`: prepared **public synthetic probe** named `meridian-axis-probe`; workers.dev enabled, preview URLs and telemetry disabled. No database bindings, secrets, assets, financial inputs or portfolio routes.

The hosted probe is a first infrastructure check, not a finished tracker or proof of the free CPU budget. It has now deployed through owner-authorised Wrangler OAuth; see the evidence document for its URL/version and measured CPU limitation. The native GitHub Builds flow below remains an unconnected alternative. No token needs to be copied into this repository or chat.

For Workers Builds, select root `prototype/worker-feasibility`, build command `npm ci && uv sync --frozen --python 3.13`, and deploy command `uv run --frozen pywrangler deploy -c wrangler.probe.jsonc`. See the linked evidence document for build variables, exact boundaries and verification steps. A successful deployment makes the synthetic `/health` and `/probe` responses publicly readable; actual financial data remains outside this probe.

Validate the actual returned URL with `python3 smoke_test.py --origin https://meridian-axis-probe.ACCOUNT.workers.dev --timeout 20`, replacing the placeholder with the provider's URL. The default remains `http://127.0.0.1:8791`. This script uses only the Python standard library and never claims hosted CPU or database qualification. Run its offline regression checks with `python3 -m unittest discover -s tests -v`; these use an ephemeral loopback server. Local Worker tooling requires Node >=22.12.0 and Python >=3.13.

Additional experimental configs isolate the observed CPU limitation: `wrangler.native-probe.jsonc` serves the same workload through native Python fetch; `wrangler.do.jsonc` wraps the existing FastAPI app in a private Python Durable Object; `wrangler.gateway.jsonc` exposes fixed synthetic routes to that object. The namespace has no storage calls and is not application persistence. Run gateway tests with `node --test tests/test_probe_gateway.mjs`. Read the evidence document before deploying; none of these controls is the financial application or an accepted production runtime.
