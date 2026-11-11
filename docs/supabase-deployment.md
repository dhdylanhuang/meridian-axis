# Supabase native GitHub deployment

Reviewed **11 November 2026**. The owner reports creating a dedicated Supabase project and connecting this repository. Project reference **`ssqqjyrgrsjubxysobwy`** is a nonsecret identifier; it is not an API key or evidence that a deployment succeeded. [Project dashboard](https://supabase.com/dashboard/project/ssqqjyrgrsjubxysobwy)

No authenticated Supabase Management API, CLI or standalone Supabase app connection is established in this workspace. The owner could not find the proposed standalone app connection, so the selected delivery path is the **native Supabase GitHub integration**. Dashboard authentication elsewhere does not authenticate tools here. Never request a database password, service-role key or persistent management token in chat or commit it to this public repository.

## Free-plan production deployment

Official documentation now explicitly supports automatic GitHub-to-production deployment on **all plans**. Preview branching is optional and requires Pro. A Free project can deploy migrations from `main` without creating preview branches or buying an upgrade. [Deployment workflow and plan availability](https://supabase.com/docs/guides/deployment)

Repository authorization and production deployment are distinct states. A GitHub connection lets Supabase read the repository; the integration must also target the correct directory/branch and have **Deploy to production** enabled. A successful repository push or our ordinary backend CI is not proof that Supabase applied the schema.

## Owner dashboard verification

The owner reports confirming these values in the dedicated project's **Project Settings → Integrations → GitHub Integration**. They have not been independently read through an authenticated management connection here:

| Setting | Intended value |
| --- | --- |
| Repository | `dhdylanhuang/meridian-axis` |
| Working directory | `.` - the repository root contains the `supabase/` folder |
| Production branch | `main` |
| Deploy to production | Enabled for this dedicated project |
| Automatic branching / paid preview environments | Disabled |

Recheck them if a deployment does not appear. The official setup guide defines the working directory as the parent of `supabase/`; entering `supabase` here would point at the wrong level. [GitHub integration setup](https://supabase.com/docs/guides/deployment/branching/github-integration)

Do not enable paid branching merely to obtain a status page or migration deployment. Preview resources have separate usage charges and are not covered by the Spend Cap. [Branch usage and billing](https://supabase.com/docs/guides/platform/manage-your-usage/branching)

## Repository contract

The deployment root is:

```text
supabase/
  config.toml
  migrations/
    20261111000100_evidence_foundation.sql
```

The bootstrap SQL mirrors the PostgreSQL evidence foundation through Alembic revision `0002`: accounts, import attempts, immutable source/audit evidence, account-scoped foreign keys, accepted-hash partial uniqueness and associated indexes. It enables RLS and removes PUBLIC/anon/authenticated table privileges, including the version marker. It adds **no account, portfolio, source, Auth-user or financial seed rows**, no member policies and no runtime database credential. It intentionally fails on conflicting pre-existing application tables rather than silently adopting an unknown schema.

This is a closed schema bootstrap, not the finished portfolio app. Owners/BYPASSRLS roles retain PostgreSQL administrative powers; runtime least-privilege access and two-member policies remain separate implementation gates. Keep real CSV/PDF/workbook data out of migrations and seeds. See [data model](data-model.md), [security](security-and-operations.md) and [current handoff](status-and-handoff.md).

## Production configuration and remote targeting

The top-level `project_id` in `config.toml` is a **local project label**, not a production project reference. The initial bootstrap deliberately contains **no `[remotes]` block**: production/persistent branches skip general API/Auth configuration by default without one. This avoids replacing unknown project Auth/API settings with local defaults before the hosted origin/session design is ready. Migrations still deploy through the saved GitHub integration. **Hosted public signup is not proven disabled by this bootstrap**; closed financial-table grants/RLS are a separate boundary. [Remote configuration](https://supabase.com/docs/guides/deployment/branching/configuration)

The initial root configuration is intentionally limited to the local project label, the database/migration target and disabled seeding:

```toml
project_id = "meridian-axis"

[db]
major_version = 17

[db.migrations]
enabled = true

[db.seed]
enabled = false
```

Use the committed file as the actual configuration; this excerpt is not a second configuration to maintain. PostgreSQL 17 is the tested foundation target, not an independently observed hosted server version. Check the actual version before making version-specific deployment assumptions. No database upgrade is implied by a local version field. [CLI database and seed configuration](https://supabase.com/docs/guides/local-development/cli/config)

After the Auth/session origin is ready and its settings are reviewed, an explicitly scoped remote entry can opt production into configuration changes. For example, the following is **future configuration, not part of the initial bootstrap**:

```toml
[remotes.main]
project_id = "ssqqjyrgrsjubxysobwy"

[remotes.main.db.seed]
enabled = false

[remotes.main.auth]
enable_signup = false
enable_anonymous_sign_ins = false
```

The remote's `project_id` must match the existing dedicated project. `auth.enable_signup` controls public registration; `auth.enable_anonymous_sign_ins` controls anonymous Auth sessions. RLS/grants independently deny anonymous financial access. Disabling signup does not provision either editor or implement the planned secure-cookie BFF. Do not add fake user emails, default passwords, a pretend production origin or secret literals. Review all intended Auth/API changes before remote opt-in, and verify actual settings afterward. [CLI configuration keys](https://supabase.com/docs/guides/local-development/cli/config)

The native workflow applies pending migration files and declared deployment assets. It is not necessary to add a second GitHub Action with database credentials solely to duplicate this delivery path. Keep production seeding disabled; no Edge Functions or Storage buckets are required by the evidence bootstrap. [Native deployment behavior](https://supabase.com/docs/guides/deployment/branching)

## One production schema writer

**Supabase SQL migrations are the sole hosted schema writer for this project.** Alembic remains the application-side schema history, offline tooling and CI parity reference. The bootstrap contains a single `alembic_version` marker at `0002` to identify the equivalent application schema; that marker is not permission to run automatic Alembic upgrades on the hosted database as well.

For every schema change, review the Alembic representation and Supabase SQL asset together, prove their equivalent constraints/indexes/types/grants on disposable PostgreSQL, and deploy the hosted SQL exactly once through its migration history. Never have API startup, native GitHub integration and a separate CLI job racing to alter the same database. Never edit an already applied SQL migration to conceal a correction; publish a reviewed forward migration. Existing-table conflicts require inspection and a deliberate baseline/recovery decision, not `IF NOT EXISTS` or blind history stamping.

CI must run the exact checked-in SQL asset, compare it with the equivalent Alembic head, verify closed privileges/RLS, and exercise failure rollback. A passing disposable PostgreSQL test is schema evidence; actual Supabase execution, configuration application and hosted authorization still require observation. An empty dedicated project is the intended initial target. Preserve any unexpected existing data before a migration decision; no reset/delete operation is part of this guide.

## Observe deployment rather than infer it

The initial release path is a temporary validation branch with automatic previews disabled, passing repository CI on that exact commit, then a reviewed fast-forward to `main` to trigger native production migration deployment. A validation-branch CI pass is not a hosted migration result. After the reviewed commit reaches `main`:

1. Open that exact GitHub commit and inspect its Checks/status details. Record any **actual Supabase-provided check name**, conclusion and Details URL alongside the full commit SHA. `Supabase Preview` appears in [preview-workflow guidance](https://supabase.com/docs/guides/deployment/branching/working-with-branches); it must not be invented as the required production check on this Free project. Backend Windows/Linux/Postgres CI checks are separate evidence.
2. Follow the native integration's deployment Details link, or inspect the project's branch/deployment workflow logs in Supabase. Confirm the expected project, branch and commit. If the dashboard groups these under **Manage Branches → selected branch → View logs**, inspecting the existing production branch does not require enabling automatic previews.
3. Verify `migrate` completed and the expected migration appears in history. With the initial no-remotes configuration, general Auth/API configuration is intentionally skipped; do not report signup as closed. If a later remote block is adopted, verify the intended settings actually applied. Seeding should be disabled; absent functions should not be mistaken for a missing application deploy.
4. Verify the four application tables plus version marker, expected revision, accepted-hash partial index, RLS and revoked public/client grants. The project must contain no seeded financial rows. Do not paste data, account responses or secrets into a public issue/check log.

Workflow step statuses are `CREATED`, `RUNNING`, `EXITED` (success), `PAUSED` (warning or intentional skip) and `DEAD` (failure). A failed health step can be a warning while later work continues; a dead migration blocks dependent seed/deploy steps. Therefore a green-looking summary or a warning alone does not replace checking the migration/configuration result. [Deployment monitoring and status meanings](https://supabase.com/docs/guides/deployment/branching/troubleshooting)

Do not hardcode a required GitHub check until its actual emitted name is observed. A report should identify which checks passed and which deployment details remain unavailable. A bare project URL responding, repository authorization, or the owner's signed-in dashboard does not prove schema readiness, RLS or a working application.

## If no deployment appears

First check the dedicated project, saved production-deploy toggle, `main`, working directory `.`, GitHub repository permission and presence of the pushed migration/config files. Check workflow logs for the exact commit rather than repeatedly reconnecting an unrelated app. Do not turn on paid previews as a workaround. Use a reviewed harmless config/schema change only when a fresh deployment trigger is actually needed; repeated dummy pushes are not a diagnosis.

If native deployment remains unavailable, a trusted authenticated administrative device may use the documented Supabase CLI workflow instead, after recording it as the single writer for that release. Inspect the installed CLI's current help and plan the exact command before use; this guide does not guess flags or request credentials here. Manual execution in the project's SQL console is a last fallback, requiring the exact reviewed asset, transaction/history reconciliation and post-apply checks; do not execute it and then let the integration blindly reapply the same bootstrap.

No authenticated remote deployment or project inspection is performed by writing this document. Update the handoff only after actual commit/check/deployment results are observed. Hosted Auth, API routes, scheduled sync, market-provider access, streaming and backup/restore remain separate gates after this empty-schema bootstrap.
