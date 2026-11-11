# Python Worker compatibility probe

Synthetic compatibility investigation. This is **not** the application or its production entrypoint. It contains no credentials, broker data or database connection.

See [the feasibility evidence and run instructions](../../docs/worker-feasibility.md). Keep `.venv*`, `.wrangler`, `python_modules`, `node_modules` and `dist` out of version control. Preserve the three dependency lockfiles when reproducing the result.

Two configurations have deliberately different purposes:

- `wrangler.jsonc`: existing loopback development configuration; workers.dev and preview URLs disabled.
- `wrangler.probe.jsonc`: prepared **public synthetic probe** named `meridian-axis-probe`; workers.dev enabled, preview URLs and telemetry disabled. No database bindings, secrets, assets, financial inputs or portfolio routes.

The hosted probe is a first infrastructure check, not a finished tracker or proof of the free CPU budget. Preparation and dry-run are complete; a real deployment still needs the owner's Cloudflare-native GitHub connection. Authorize the provider GitHub App for this repository on the owner's device. No token needs to be copied into this repository, terminal or chat.

For Workers Builds, select root `prototype/worker-feasibility`, build command `npm ci && uv sync --frozen --python 3.13`, and deploy command `uv run --frozen pywrangler deploy -c wrangler.probe.jsonc`. See the linked evidence document for build variables, exact boundaries and verification steps. A successful deployment makes the synthetic `/health` and `/probe` responses publicly readable; actual financial data remains outside this probe.
