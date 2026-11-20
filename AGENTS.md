# Repository working instructions

## Read first

1. Read [current status](docs/status-and-handoff.md) and [the next task brief](docs/next-milestone.md).
2. Use [the documentation index](docs/README.md) to select the task's domain contract, relevant requirements, implementation and tests. Read architecture/ADRs when changing runtime or persistence.
3. Read [agent workflow](docs/agent-workflow.md) before coordinating parallel work. Historical checkpoints are reference material for a specific evidence question.

Current repository status: authenticated AXIS/HOLDINGS, ten-minute broker refresh and bounded sixty-day detailed-refresh retention are deployed. Native parity is `0008`; gateway/sync source is `17aa7ea`, session owner is `5cc8564`. The cash dashboard shows broker cash now and descriptive year-to-date dividend/interest/deposit/withdrawal amounts, with coverage and separate currencies. Raw event counts and component-window diagnostics no longer drive the main view; the opening-control query is disabled at runtime. Current status owns actual publication verification. Private Rust cash review is deployed through a named gateway service binding and approved snapshots; hosted nonfinancial WASM readiness is verified. Broker-led automatic discovery/enrichment is deployed; exact assets/source tags, preserved bindings and ten-minute schedule were verified without database probes. Daily observed snapshots, latest snapshot and transaction/import/audit history are retained. Post-reset login/automatic cadence and realized query use remain unverified. Trading 212 reported figures stay authoritative; status owns evidence and unresolved gates.

**Current delivery:** monetary totals now have on-demand, generation-pinned
transaction drill-down and completed-broker-history coverage (release evidence in
current status). A private audit found no retained capture-reference gap; lifetime
coverage is still unproven. Do not repeat validation or copy history into snapshots.

**Owner acceptance amendment, 20 November 2026 (DC25):** deliver meaningful monetary
features. Cash must show current broker cash and dated dividend/interest/deposit/
withdrawal amounts; event counts and component-window diagnostics alone do not
satisfy acceptance. Keep current cash separate from past income/funding, and verify
real approved publication. Current status owns implementation/release evidence.

**Current owner scope, 20 November 2026:** begin reconciliation in Rust, with Python retaining ingestion/database access. The native cash core/read-only evidence bridge have seven Rust/four Python checks. WASM packaging and local workerd qualification add three focused checks; reuse evidence in current status. Private invocation/approved summary publication is deployed; live provisional summary/input revision/snapshot identity were observed. Full-bound hosted CPU/memory and verified cash economics remain open in current status. No whole-app rewrite or unqualified hosted Rust deployment. Preserve token/test discipline.

**Prior owner scope, 19 November 2026:** manual XLSX archive completed; see `docs/workbook-archive.md`. The dedicated AXIS Archive sheet contains 1,360 broker-refresh generations. Preserve legacy sheets/formulas and never put the workbook, config, previews or real source rows in Git. The reusable stdlib export needs no temporary venv/Docker, and cloud expiry does not wait for manual exports. Retention implementation and separately approved backup repair are complete. Reuse the targeted/CI evidence in current status; no new platform task is activated. Keep changes/output minimal and flag substantial expansion. For `recovery_docker_unavailable`, start existing Docker Desktop and require a nonempty `docker version --format` server version. Formatted `docker info` can misleadingly return zero alongside a daemon connection error; do not repeat sizing/tests, reconfigure sockets or install clients to diagnose that category.

Minimise sub-agents and unnecessary rate-limit consumption. Use one bounded stream with targeted checks. **Owner instruction, 19 November 2026:** avoid unnecessary validation runs, tests and checks. Select meaningful checks for changed behaviour, reuse passing results, and repeat or broaden only after new changes, failures or unresolved concerns. Do not repeatedly poll CI or live services. Batch independent read-only inspections, avoid duplicate CI runs for the same source, and record completed evidence and outstanding work in the handoff so a resumed agent does not restart validation. Keep changes reviewable and preserve the supported requirements. Prior usage reports and time-based pauses are retained in [historical checkpoints](docs/status-history.md).

## Authority and scope

- The user's latest explicit instruction takes precedence. Documentation does not grant permission to deploy, trade, commit, contact others or change the user's workbook.
- Follow the owner's latest task scope. Earlier project implementation, stage commit/push and private free-hosting authority persists where applicable. A documentation task does not by itself resume platform implementation or activate a proposed next task.
- Preserve the original brief in `docs/context/original-brief.md` as historical context. Active requirements and recorded resolutions take precedence over its contradictions.
- Distinguish CONFIRMED requirements, VERIFIED observations, ADOPTED engineering decisions, PROPOSED defaults and OPEN owner decisions. A plan is not a completed feature.
- Do not promote an assistant suggestion into an owner-confirmed requirement. Use [decisions and questions](docs/decisions-and-questions.md) for unresolved choices.

## Engineering rules

- Keep a modular application. Production uses private Supabase PostgreSQL and Cloudflare; SQLite is local tooling. Preserve Python/FastAPI where the hosting qualification passes. Bounded jobs use durable leases, checkpoints and retry times instead of a resident APScheduler process. Read [ADR 0001](docs/decisions/0001-cloudflare-supabase.md) before changing runtime/persistence.
- Calculation modules are pure and independent of HTTP, SQLAlchemy, provider SDKs and React. Adapters return normalised contracts; they do not own financial formulas.
- Imported evidence is immutable. Corrections, group overrides and provider revisions create traceable records; they do not rewrite raw evidence. The reviewed `0008` fixed-scope capability is the sole expiry exception for eligible detailed broker-refresh pairs; daily anchors, latest snapshots and financial history remain protected.
- Store precise decimal ledger values without database or JavaScript floating-point coercion. Keep canonical decimal strings at public JSON boundaries; convert to floating-point arrays only at the analytics boundary.
- All financial output has a source, as-of date, currency and availability/quality state. Never fill an unsupported metric with a plausible number.
- Do not use intraday quotes as approved daily risk inputs. Do not use provider cost/PnL as HMRC results.
- Follow the verified provider specification. Never invent endpoint paths, IDs, response fields, permissions or quote timestamps.
- Broker read-only scope includes no order creation, modification or cancellation. Credentials never enter the frontend, logs, fixtures or documentation.

## Coordination and delivery

- Assign bounded tasks with explicit file ownership, contract dependencies, acceptance criteria and prohibited scope. Follow platform rules about when delegation is permitted.
- Inspect the working tree before editing. Do not overwrite another contributor's work or reset unrelated changes.
- Serialise shared schema migrations, package manifests, contract changes and integration. Agree interfaces before splitting dependent work.
- Supabase native SQL migrations are the sole hosted schema writer. Keep their reviewed model/Alembic parity tests in the same delivery; never run automatic Alembic upgrades against the hosted project. Test on a validation branch before advancing the production-connected `main`. See [ADR 0002](docs/decisions/0002-hosted-migration-authority.md).
- Test the changed behaviour with meaningful offline fixtures. Record exact commands and outcomes; do not invent command success or claim a whole stage from one passing test.
- Update requirement traceability, open decisions and the status/handoff document where affected. Use the templates in `docs/templates/`.
- No commits, pushes, publication or remote-access configuration unless the user has authorised that action.

## Privacy

Do not copy the real workbook or broker exports into fixtures. Use synthetic or explicitly sanitised data. Check ignore rules before creating runtime files. The repository is public. Documentation must omit actual balances, position sizes, contribution amounts, private paths/digests and personal/employment notes. Keep exact evidence in local source files/runtime manifests; public examples are synthetic. One ISA and equal full editing rights are confirmed; the tax engine is deferred.
