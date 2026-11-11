# ADR 0002 - Hosted migration authority

Date: **11 November 2026**. Status: **ADOPTED engineering decision** within the owner-authorised Cloudflare/Supabase implementation. Actual deployment remains separately evidenced in the handoff.

The owner created a dedicated Supabase project and connected this repository. Native GitHub deployment can apply `supabase/migrations` without copying a database password onto the development machine. The current backend already has published Alembic history through `0002`; two independent hosted migration writers would create drift.

## Decision

- **Supabase native SQL migrations are the sole hosted schema writer.** The production runtime must not run Alembic on startup. Keep Alembic for local tooling, upgrade fixtures and native PostgreSQL parity tests.
- Pair future logical schema changes with their reviewed Alembic/model update and a forward-only Supabase SQL migration in one delivery. Preserve already published migrations. Test both paths against the same expected metadata, identities, constraints and financial controls.
- The initial hosted SQL is a bootstrap for an empty dedicated target, matching current PostgreSQL model DDL and the security contract at `0002`. It creates no owner/account row, login, policy, sample holding or financial source. Existing table-name collisions fail; they are not silently adopted or overwritten.
- Its `alembic_version` row records schema parity, not Supabase deployment history. Supabase owns its separate native migration history. Do not run both migration systems against the hosted project or stamp a mismatched schema to hide drift.
- The managed runner owns the transaction. All new tables and their grants/RLS close together before commit; there is no explicit nested `BEGIN`, concurrent index operation, seed or destructive reset. The trusted hosted runner must target the intended `public` schema. Isolated CI tests execute the same unqualified SQL unchanged in a generated schema and verify it cannot escape that schema.
- RLS and revoked PUBLIC/anonymous/authenticated table grants establish a closed foundation. They do not implement member authorization, constrain table owners/BYPASSRLS, or complete hosted authentication. Add reviewed member/session/service access only at its security gate.
- Initial `supabase/config.toml` enables migrations and disables seeding. It deliberately has no `[remotes]` block, so this bootstrap does not opt into production Auth/API reconfiguration. The GitHub integration owns destination selection; root `project_id` is only a local label.

## Verification and release

Validate the SQL asset on a temporary Git branch with automatic Supabase preview branching off. Service-backed CI must pass native execution, metadata parity, default-grant closure, rollback on a late conflict and import replay before advancing `main`. Then observe the actual Supabase integration result or dashboard migration record; a successful Git push or GitHub backend test is not proof that the remote project migrated.

The target project reference is non-secret deployment metadata supplied by the owner. Credentials and private financial sources remain outside Git. See [Supabase deployment](../supabase-deployment.md) for target metadata, source references, integration settings and verification limits.
