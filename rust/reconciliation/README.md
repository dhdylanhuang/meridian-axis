# AXIS Rust cash reconciliation: first bounded slice

Owner-selected Rust experiment, 20 November 2026. Pure library plus native stdin /
stdout JSON CLI (`cash_reconciliation_rust_v1`). Python retains broker ingestion,
accepted-evidence reads and database access. No network, database writes, worker,
HTTP endpoint, schema change, credential or actual financial input in this crate.

The Rust `Request` structs in `src/lib.rs` define the strict version-1 boundary.
Unknown fields and numeric JSON money are rejected. Monetary values are strings;
`bigdecimal` preserves exact arithmetic without float conversion. Input is capped
at 64 MiB, 20,000 cash observations, 128 currencies and 128 controls per side.
Source decimal inputs match the existing 128-digit / 128-exponent bounds.

## Implemented economics and review boundary

- Identity is one cash reference within a fixed account/environment. Select latest
  actual observation instant, then revision. Keep every source/revision/digest and
  original date/amount; repeated syncs contribute once, revisions replace effects.
  Conflicting same-rank facts produce review and no effect. Missing later records
  are not deletions. Unknown provider types and future events are not booked.
- Supported cash-family types are DEPOSIT, WITHDRAW, FEE, TRANSFER,
  INTEREST_ON_FREE_CASH and LENDING_INTEREST. A type does **not** establish sign.
  `SignBasis::VerifiedSignedAmount` needs a nonempty evidence reference from a
  trusted, separately validated adapter. The ID is provenance, not a signature;
  the caller must establish its truth. Unverified signs have no cash delta.
- Explicit opening/closing controls carry scope, currency, source, timestamp and
  compatible statement/verified-total basis. Closing time must equal cutoff;
  opening time must precede it. Sum eligible signed movements over
  `(opening time, cutoff]`, add to the opening, compare closing minus replay.
  No opening is ever inferred; missing controls leave the difference null.
- Keep currencies separate, with no FX conversion. Even an exact match is
  `matches_known_events_only`, always provisional with unverified lifetime coverage.
  Transfers have no inferred external-flow classification. No return calculation,
  fill-wallet economics, dividend or tax booking is implemented.
- Trading 212 available-to-trade/in-pies/reserved amounts remain separate broker
  observations. They are never summed or silently chosen as total closing cash.

## Python evidence bridge and local use

`meridian.application.cash_history.cash_history_request` exports only accepted
initial cash rows and completed ongoing cash revisions, with source/digest/scope
checks. Running/failed pages stay excluded. Default exports retain **unverified raw sign bases and empty controls**.
Hosted opt-in `cash_sign_policy=statement_checked_gbp_v1` verifies only live GBP
positive cash interest and nonzero signed transfers against independently checked
private ISA statement evidence. Other cases remain unverified. Optional
`broker_available_to_trade` controls compare actual component observations; they
are never total cash. Original evidence is unchanged; the report carries policy
and derived sign-evidence IDs. Component comparisons include supported/excluded
window counts and remain provisional even on zero residual. This makes current output useful for identity/revision/review work;
it does not claim actual account cash is reconciled.

Build once from the repository root:

```sh
cargo build --manifest-path rust/reconciliation/Cargo.toml --locked
```

Then from `backend`, with the existing Python environment:

```sh
set -o pipefail
python -m meridian.export_cash_history --database /path/to/private.sqlite3 --account-id ACCOUNT_ID \
  | ../rust/reconciliation/target/debug/axis-reconciliation > /path/to/private-report.json
```

The exporter opens SQLite in `mode=ro` with an explicit consistent read transaction
and cannot create a missing database. Both streams contain private financial
records/IDs: keep requests/reports outside Git and public logs. Neither command
fetches real broker/hosted data. Failures emit safe categories and exit 2.

## Validation and remaining integration

Verified with Rust 1.100.0: **7 Rust tests**, **4 Python bridge tests**, including a
real compiled-binary handoff using synthetic accepted capture/revision evidence.
Cargo.lock pins dependencies. Exact commands/outcomes are in current handoff;
reuse them and do not rerun unrelated Python/Worker/retention suites.

The temporary toolchain is under `/private/tmp/meridian-rust`; build output is
`/private/tmp/meridian-rust-target`. Set CARGO_HOME/RUSTUP_HOME/CARGO_TARGET_DIR to
those paths to reuse it. The selected full Xcode failed its license check on the
first build; the installed standalone tools worked with scoped
`DEVELOPER_DIR=/Library/Developer/CommandLineTools`. No license was accepted or
machine-wide selection/profile changed.

This is a native offline core, not a deployed feature. WASM packaging and local Cloudflare runtime qualification are now complete (see
below). Private Python-to-JavaScript invocation, hosted workload qualification and
approved dashboard publication remain the next integration boundary. Verified sign/opening/closing evidence and remaining event families are
also open. The deployed broker snapshot remains authoritative and unchanged.


## WASM packaging and local Worker qualification

The same pure core now exports `reconcile_cash_json` through wasm-bindgen 0.2.130.
No formula is duplicated in JavaScript. WASM accepts at most **512 KiB UTF-8** and
**1,024 observations** per invocation; excess input fails as a whole, never as a
silently partial financial result. Native limits remain unchanged. Strings carry
all precise values; the adapter emits only safe error categories and accepts a
precompiled WebAssembly.Module, never caller-provided executable bytes.

Reproducible commands from the repository root (Rust and Node >=22.12 required):

```sh
rustup target add wasm32-unknown-unknown  # one-time toolchain setup
cargo build --manifest-path rust/reconciliation/Cargo.toml --target wasm32-unknown-unknown --release --lib --locked
python rust/reconciliation/tools/package_wasm.py \
  --wasm rust/reconciliation/target/wasm32-unknown-unknown/release/axis_reconciliation.wasm \
  --wasm-bindgen /path/to/wasm-bindgen
AXIS_RUST_TEST_BINARY=/path/to/native/axis-reconciliation \
  node --test prototype/worker-feasibility/tests/test_cash_wasm.mjs
```

The generator must exactly match Cargo.lock. This delivery used the official
prebuilt 0.2.130 Apple ARM generator, verified against its published SHA-256, under
`/private/tmp/meridian-rust/wasm-bindgen-cli`. No compiler/tool download is needed on
resume. Generated `.wasm`, `.mjs` and hash manifest live in the ignored
`prototype/worker-feasibility/src/reconciliation_wasm/` directory. The release
profile retains target-feature metadata (`strip = "debuginfo"`) needed by the
generator. Packaged WASM size for this source is **406,813 bytes**.

`src/cash_reconciliation.mjs` is a private Worker import with generated bindings;
it is not a browser asset or HTTP route. The separate `reconciliation_probe.mjs`
harness has no credentials/bindings and serves only one fixed invented fixture on
localhost; its Wrangler config disables workers.dev/previews. It is not a fourth
hosted Worker. The three existing production Workers are unchanged.

New evidence: two Node WASM/parity/bounds cases passed; the local workerd case
initially stopped because the shell's Node 20 was below Wrangler's requirement.
The existing compatible Node at `private/dev-tools/node_modules/.bin/node` ran
only that failed case, which passed. The test now uses its own Node interpreter
for the Wrangler child. This establishes generated ABI and local runtime
compatibility, not hosted CPU/memory acceptance or actual cash semantics. Earlier
seven Rust/four Python results were reused; no full suites or hosted probes.

This follows Cloudflare's [precompiled WASM module model](https://developers.cloudflare.com/workers/runtime-apis/webassembly/)
and Rust's [wasm32-unknown-unknown target](https://doc.rust-lang.org/rustc/platform-support/wasm32-unknown-unknown.html).
Next: qualify the private call boundary within the existing application, then
publish an approved summary with source revision/coverage. Do not expose raw
history to the BFF or create a public generic reconciliation endpoint.


## Application integration

The existing gateway now exports a private named `CashReconciliation` service
entrypoint; the sync Python DO calls it through a service binding. The gateway
returns only a whitelisted summary, and Python validates its input revision,
snapshot identity and coverage before atomic snapshot publication. The browser
receives approved review counts/states, never raw Rust observations. No formula
has moved into JavaScript; no schema/grant or fourth Worker is needed.

Runtime preparation deliberately includes only ongoing cash revisions allowed by
the existing sync RLS. Initial captures remain excluded and visibly flagged; the
trusted local exporter keeps its broader evidence. Unverified signs and missing
opening/closing controls mean actual balances stay unreconciled. Limits and private
transport failures produce explicit unavailable states without replacing broker
figures. The fixed nonfinancial health self-check is separate from cash evidence.
Release and exact focused integration checks belong in current status.


## Descriptive income/funding report

Optional `activity_since` requests exact source-reported category totals through
cutoff, inclusive. `Observation.family` defaults to `transactions`; `dividends`
has its own reference namespace. Latest selection/conflicts retain all evidence.
Dividend records are `reported_activity_only` and never contribute cash deltas.
`reported_activity` groups original signed amounts by currency/category, without
FX, inferred ledger sign, tax gross/net treatment or allocating current cash to
past flows. Empty categories are absent, not zero. Runtime uses UTC year to date;
coverage remains incomplete/unverified. Main dashboard shows monetary amounts;
the previous cash control window is an optional diagnostic, not feature acceptance.
