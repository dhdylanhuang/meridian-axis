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
checks. Running/failed pages stay excluded. **All exported sign bases are
unverified and opening/closing controls are empty** until real semantics/evidence
support them. This makes current output useful for identity/revision/review work;
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

This is a native offline core, not a deployed feature. WASM packaging/runtime
qualification and approved dashboard publication remain the next integration
boundary; a native executable cannot simply be copied into the current Python
Worker. Verified sign/opening/closing evidence and remaining event families are
also open. The deployed broker snapshot remains authoritative and unchanged.
