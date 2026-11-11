# Repository working instructions

## Read first

1. Read [README](README.md), [documentation index](docs/README.md) and [current status](docs/status-and-handoff.md).
2. Read [product requirements](docs/product-requirements.md), [architecture](docs/architecture.md) and the current stage in [development stages](docs/development-stages.md).
3. Read the domain contract for your task. Read [agent workflow](docs/agent-workflow.md) before coordinating parallel work.

Current repository status: local evidence/import foundations verified; Cloudflare + Supabase is the approved hosted target and is undergoing qualification. Check the actual tree and status document before claiming any feature exists.

**Development resumed by explicit owner request on 11 November 2026**, on the owner's personal laptop, with delegated agents authorised. Preserve the historical pause checkpoint in the handoff. Continue Stage 0H qualification; the owner has now authorised direct Cloudflare CLI access through OAuth, stored in macOS Keychain. Supabase hosted migrations retain their native GitHub delivery path.

The owner reaffirmed full project implementation, verification, commit/push and deployment authority for this conversation, asking not to repeat project permission questions. Continue within the agreed private-data and free-services scope. Platform sandbox approvals remain separate execution constraints.

## Authority and scope

- The user's latest explicit instruction takes precedence. Documentation does not grant permission to deploy, trade, commit, contact others or change the user's workbook.
- A documentation request alone does not authorise application implementation, commits or publication. Follow the owner's latest explicit instruction for each action; the owner has now requested executing the plan with delegated agents, committing and pushing each verified stage, and eventual private hosting using free services only.
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
