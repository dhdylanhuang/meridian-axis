# Repository working instructions

## Read first

1. Read [current status](docs/status-and-handoff.md) and [the next task brief](docs/next-milestone.md).
2. Use [the documentation index](docs/README.md) to select the task's domain contract, relevant requirements, implementation and tests. Read architecture/ADRs when changing runtime or persistence.
3. Read [agent workflow](docs/agent-workflow.md) before coordinating parallel work. Historical checkpoints are reference material for a specific evidence question.

Current repository status: authenticated AXIS/HOLDINGS and ongoing read-only broker refresh are deployed at native parity `0007`. Minute cadence was verified on 13 November 2026. Trading 212 reported figures remain authoritative. Current status owns implementation evidence and unresolved gates.

**Current owner scope, 13 November 2026:** reconcile documentation inconsistencies. Platform development awaits the next instruction after completed minute polling. Scheduled service remains enabled. Earlier project authority and private/free-service boundaries remain subject to the owner's latest task scope and platform execution approvals.

Minimise sub-agents and unnecessary rate-limit consumption. Use one bounded stream with targeted checks. Keep changes reviewable and preserve the supported requirements. Prior usage reports and time-based pauses are retained in [historical checkpoints](docs/status-history.md).

## Authority and scope

- The user's latest explicit instruction takes precedence. Documentation does not grant permission to deploy, trade, commit, contact others or change the user's workbook.
- Follow the owner's latest task scope. Earlier project implementation, stage commit/push and private free-hosting authority persists where applicable. A documentation task does not by itself resume platform implementation or activate a proposed next task.
- Preserve the original brief in `docs/context/original-brief.md` as historical context. Active requirements and recorded resolutions take precedence over its contradictions.
- Distinguish CONFIRMED requirements, VERIFIED observations, ADOPTED engineering decisions, PROPOSED defaults and OPEN owner decisions. A plan is not a completed feature.
- Do not promote an assistant suggestion into an owner-confirmed requirement. Use [decisions and questions](docs/decisions-and-questions.md) for unresolved choices.

## Engineering rules

- Keep a modular application. Production uses private Supabase PostgreSQL and Cloudflare; SQLite is local tooling. Preserve Python/FastAPI where the hosting qualification passes. Bounded jobs use durable leases, checkpoints and retry times instead of a resident APScheduler process. Read [ADR 0001](docs/decisions/0001-cloudflare-supabase.md) before changing runtime/persistence.
- Calculation modules are pure and independent of HTTP, SQLAlchemy, provider SDKs and React. Adapters return normalised contracts; they do not own financial formulas.
- Imported evidence is immutable. Corrections, group overrides and provider revisions create traceable records; they do not rewrite raw evidence.
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
