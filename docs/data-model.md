# Data model and invariants

Status: ADOPTED target logical model; Stage 1A implements accounts, import_log, source_records and audit_log with initial migration and precise storage types. Other tables below remain planned. Add tables when their delivery stage needs them; this model is not an instruction to build every table in Stage 1.

## Production platform amendment

The owner selected Supabase PostgreSQL for production; SQLite remains local evidence tooling. Preserve the entity/identity/provenance contracts below. Port migrations and partial uniqueness deliberately; enable RLS and revoke anonymous/unrelated-user grants before any financial route. Explicit approved portfolio membership and server-side mutation rules remain required; managed Auth alone does not authorize rows. Native Postgres parity is not a hosted pooler/Hyperdrive or Supabase Auth test. See [ADR 0001](decisions/0001-cloudflare-supabase.md).

The foundation continues to preserve canonical Decimal text in both dialects; exact PostgreSQL NUMERIC can be adopted later through a reviewed migration and measured query need. No JavaScript Number or implicit float conversion is permitted at ledger/JSON boundaries. The source checkout migration chain is authoritative, not the historical SQLite-only proposed DDL.

## Identity and precision

- `user_id` identifies an application login. `owner_id` identifies the one beneficial owner. `account_id` identifies an actual broker account and includes environment and wrapper. Two logins never create two tax owners.
- `security_id` represents an economically/tax-relevant security class; `instrument_id` represents a specific listing with exchange, quote currency and provider mappings. Do not merge listings solely by ticker or name. ISIN is evidence, not an excuse to ignore share-class or depositary-receipt differences.
- A provider identifier is stored with its provider, environment, account and event kind. Preserve int64 IDs as strings at the JSON boundary to avoid JavaScript integer loss.
- All event timestamps are timezone-aware UTC; retain original timestamp text/offset and exchange-local session date where relevant. Unknown source dates retain their original label and precision rather than receiving invented timestamps.
- Ledger money, shares, prices and FX use Python Decimal constructed from source strings. Store canonical decimal text through an explicit SQLAlchemy conversion type; SQLite NUMERIC affinity can coerce to floats. Do not aggregate precise ledger values with native SQLite `SUM` over text. Calculate in Decimal and store derived read models deliberately.
- Preserve source precision. Use a documented high-precision decimal context, round GBP display to pennies with ROUND_HALF_EVEN, and compare source totals within £0.01. Tax-specific reporting rounding is separately specified. Analytics arrays may use float64 after eligibility validation.

SQLite's [type-affinity documentation](https://www.sqlite.org/datatype3.html) explains why a column named DECIMAL/NUMERIC alone does not guarantee decimal arithmetic. Verify exact round-trips with the selected driver/SQLAlchemy type before importing money.

## Entities

| Entity | Essential data / constraints |
| --- | --- |
| Supabase Auth, `account_members`, `app_sessions` | External canonical Auth UUIDs; two active equal member slots per account with revocation history; hashed opaque session/CSRF tokens, bounded expiry and revocation; no application passwords or broker credentials |
| `login_rate_limits` (in validation) | Fixed nonpersonal deployment bucket, database epoch seconds and bounded attempt count; no email/IP/password; atomic shared admission, closed browser grants/RLS, no seeded bucket |
| `owners`, `accounts` | One owner and one live ISA; broker, private account reference, isolated demo/live, primary currency and history coverage |
| `securities`, `instruments` | Security-class identity; listing ticker, name, ISIN when known, exchange, currency, unit multiplier, asset class and country evidence |
| `ticker_map` | Instrument/provider symbol mapping, valid interval, reviewer and revision; editable and audited |
| `groups` | Stable ID, name, display order, description, active/merged status; reserved Unassigned identity |
| `group_label_mappings` | Raw label/source context to stable group; preserves renames/merges without changing raw text |
| `group_memberships` | Instrument, group, effective interval, assignment basis, override/reviewer; no overlapping current memberships |
| `group_evidence`, `group_conflicts` | Original group context (Total-row Name in the verified format), source row/run, observed date, competing groups and resolution; Slice ticker remains separate |
| `source_records` | Source kind, immutable payload/row, schema version, digest, run ID, original IDs; private retention/access policy |
| `transactions` | Normalised economic event; account, security/listing, event type, executed time, quantity, money components, original currencies, nullable raw Slice, revision/supersedes links |
| `transaction_sources` | Multiple source records linked to one economic event; prevents a CSV and API observation from creating duplicate economic entries |
| `ledger_entries` | Balanced cash/security movements per transaction; per-currency cash amounts, fees and taxes are explicit components |
| `opening_positions`, `opening_cash` | Explicit source-supported opening records, provenance and limitations; never fabricate acquisition history |
| `broker_snapshots`, `position_snapshots` | Sync generation, broker as-of/fetched time, observed quantities, value/cost/PnL and currency; reconciliation evidence only |
| `holdings` | Rebuildable quantity/cost read model keyed by account/listing/revision, not hand-entered positions |
| `prices` | Instrument, session date, price basis, value, source, quote/fetch times, quality, revision and supersedes link; retain competing observations |
| `fx_rates` | Currency pair, explicit direction, effective date/time, rate, source and quality/revision |
| `intraday_prices` | Poll/run ID, instrument, quote/fetch time, raw currency price/unit, GBP price, exact FX reference/rate, delay/quality and session |
| `benchmarks` | Configured role to verified instrument/provider series and return basis; reuse instrument prices, not duplicate them |
| `risk_free` | Dated UK Bank Rate observations, source/manual override and effective interval |
| `valuations`, `valuation_lines` | Run/session/as-of, basis, ledger/price/FX/group revisions, total cash/securities/NAV and holding/group components |
| `baseline_snapshots`, `baseline_lines` | Original Excel label, known observation date/precision, recorded value/invested/dividends, group coverage, cell addresses, file hash and `excel_migration` |
| `tax_runs`, `tax_matches` (DEFERRED) | Owner/security class/tax year, method version, matched acquisition quantities/costs, residual pool and provisional/completeness state |
| `analytics_runs` | Input revision/hash, settings/method, window, frequency, coverage, result payload and quality; do not build a table per scalar statistic |
| `thesis_notes` | Exactly one instrument or group target, dated text, optional review date, author and revision |
| `alert_rules`, `alert_state`, `alerts` | Versioned thresholds, evaluation basis, durable arm state, excursion identity, observed values and acknowledgement |
| `settings`, `settings_revisions` | Typed validated settings, scope, effective date, actor and before/after; secrets remain outside these tables |
| `import_log` | CSV/Excel/API sync and polling-cycle outcomes, operation type, counts, hash/run, safe error, timing and actor; indexed/filtered by type |
| `sync_checkpoints` | Account/history family and committed source watermark; advance only after successful commit |
| `audit_log` | Append-only timestamp, actor/user or system job, action/entity, redacted before/after JSON, run and source hash |

Supporting entities may be combined when invariants remain enforceable. Use ordinary relations instead of a generic entity-attribute-value financial ledger.

## Critical constraints

1. Successful file imports are unique by account/environment, file kind and content hash. Failed attempts do not permanently prohibit a corrected retry. Repeated accepted files are reported as rejected duplicates.
2. Normalised events are unique by verified external identity. Cross-source aliases link evidence to that identity. An identical ID with changed economics creates a conflict or revision, never an invisible overwrite.
3. Group membership is separate from raw labels. Every visible listing has one current group, possibly Unassigned; unresolved conflicts retain a warning even if a provisional display group is used.
4. Total rows are never transactions, instruments, groups or cash balances. They may be stored as source controls and excluded-row counts.
5. FX conversion always retains the exact source observation. A displayed GBP price alone is insufficient provenance.
6. Cash balances and securities are not counted twice. Broker snapshot totals cannot be added to ledger holdings.
7. Daily closing observations have a basis: unadjusted valuation close, total-return/adjusted input or provisional session candidate. Selection policies must not mix these silently.
8. Each source has separate event, observation and retrieval dates where available. Unknown does not become the import time.
9. Audit records cannot contain credentials, session tokens or unbounded raw payloads. Application code has no routine update/delete path for audit entries; this is not a claim of administrator-proof tamper resistance.

## Read models and migrations

Prefer repository queries and a few explicit read models over precomputing every table/tab combination. Use stable instrument/group IDs for joins, notes and UI keys. Index account/time, instrument/session, run/type, external identity and active-alert lookups before tuning exotic queries.

Numeric sorting must also preserve financial meaning: canonical decimal text cannot be ordered lexicographically as money. Use an explicitly designed sort representation/read model or bounded Decimal sorting, with pagination behaviour tested. Do not fix precision by storing text and then silently cast all ledger arithmetic back to floating point.

The initial migrations establish accounts, precise storage types and import/source/audit evidence. Events, economic ledger and grouping remain later slices. The new `0003` foundation adds closed membership/session tables; it seeds no identity/member/session, exposes no policy or runtime grant, and supplies no usable login on its own. Supabase native SQL and Alembic/model parity must pass validation before hosted promotion. One agent owns the migration sequence at a time. Migrations require an upgrade test from the preceding schema and a backup/restore rehearsal before use with real data.

Member slots are capacity identifiers, not permission levels: both have identical editing rights. A partial unique index limits each account to slots 1/2 while allowing revoked membership history. Sessions reference the composite account/member key, preventing a token from claiming another account's membership. Services still check active membership and expiry on every request; a foreign key alone does not authorize a session. Audit records contain the account/actor/action, never token or CSRF hashes. Runtime policies/roles remain a separate gate.

Historical grouping is effective-dated. ADOPTED display default: exposures use current membership; historical attribution uses membership effective at that date. A separately labelled restatement mode may use current classification; it must not rewrite historical evidence.
