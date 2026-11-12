# Hosted recovery qualification

Verified **12 November 2026** for O01, S01/S02 and QA01/QA02. This is a hosted logical export restored into an isolated local Supabase PostgreSQL target. It is not a replacement hosted project, a failover, or complete operational acceptance.

## Delivered procedure

`meridian.hosted_backup` uses the already authenticated Supabase CLI to capture role definitions without database password verifiers, application/native-migration schema, and database data including Auth records. The default CLI data export **omits native migration history**; an additional explicit `supabase_migrations` data export is required. The first real drill detected this omission through content controls, rolled back, and retained the incomplete archive separately. The corrected archive passed.

SQL stays in captured process memory. The ordinary output is an authenticated AES-256-GCM encrypted archive with a random 96-bit nonce and a separately generated 256-bit key. Its encrypted manifest contains file SHA-256/size controls, project scope, creation time and table content controls. Files are created exclusively with owner-only permissions; existing files are refused. Neither archive nor key belongs in Git or public CI. Auth password hashes and identities are sensitive even though database login password verifiers are omitted. The owner specifically approved their encrypted export and isolated restore during this delivery.

The initial scope is parity `0005` and the eight known public tables. Before/after controls detect changes to application rows, approved Auth identities, native migration history and Storage metadata across the separate dump commands. A changing source fails rather than producing an accepted archive. These are comparison controls, not a global multi-dump database snapshot or a cryptographic signature independent of the encryption key. Stop financial writers and schema changes for maintenance; provider session churn is deliberately excluded from identity controls. Each provider dump supplies its own consistent snapshot.

Nonempty Storage buckets/objects and unknown application tables are refused. Storage binaries, future financial tables and external archives need explicit coverage before extending this procedure. The archive format is bounded to 256 MiB on read and 128 MiB of input SQL; export subprocess capture is currently in memory, so this is an initial small-database procedure rather than a large-database streaming backup.

`meridian.local_restore` accepts only a running local Supabase container with a matching CLI ownership label, a recovery-specific name, **no connected Docker networks**, no public application tables, no Auth users and no Storage objects. There is no remote database URL parameter. It authenticates the archive before writing SQL. The local cluster administrator restores roles/schema/data in one transaction, compares source content controls, then revokes application sessions and removes provider sessions/refresh tokens before commit. A failed control rolls back. Provider baseline rows listed by the trusted dump are cleared only inside this isolated transaction. Restoring arbitrary SQL remains a trusted administrative operation.

## Commands

From `backend`, with the locked environment installed. Paths below are private example locations; create their parent directories with restricted permissions. Use a fresh archive name for each checkpoint.

```sh
uv run --locked python -m meridian.hosted_backup new-key private/recovery-keys/recovery.key
uv run --locked python -m meridian.hosted_backup backup \
  --cli /path/to/authenticated/supabase \
  --project ssqqjyrgrsjubxysobwy \
  --key-file private/recovery-keys/recovery.key \
  private/backups/checkpoint.meridian
```

Keep the key in separately protected recoverable custody. The current key and archive are on the trusted administrative laptop, outside the hosted project; an independently recoverable second key copy and ongoing retention remain outstanding. Losing the key makes the archive unusable. Do not move it into the archive directory or send it through chat.

For a drill, initialise a fresh private CLI work directory with a recovery-specific project ID (for example `recovery-drill`), no remote link and no application migrations, then run `supabase db start --workdir <private-workdir>`. Disconnect that database container from its Docker network **before** restoring; do not start Auth/API services over restored credentials. Confirm the inspected container ownership/name. Then:

```sh
uv run --locked python -m meridian.local_restore \
  --container supabase_db_recovery-drill \
  --key-file private/recovery-keys/recovery.key \
  private/backups/checkpoint.meridian
```

The local Supabase image provides provider-owned schema/roles. Ordinary PostgreSQL alone does not provide that baseline. Match/qualify provider schema versions; mismatched Auth columns or privileges must fail. No hosted migrations are run by these tools. After independent permission checks, stop and remove only the disposable local target and its volumes; retain the encrypted archive and separate key.

## Measured evidence

- Hosted source: PostgreSQL **17.11**, parity `0005`, no financial source rows or Storage objects at this checkpoint.
- Isolated target: Supabase PostgreSQL image **17.11.0.018**, no network connectivity; no paid project or provider branch.
- Corrected hosted export, encryption and read-back verification: **17.72 seconds**. Isolated SQL restore/control verification/session invalidation: **0.16 seconds**, excluding image download, setup and independent checks. These are observations, not RTO/RPO guarantees.
- Full source controls matched for application tables, Auth users/identities and native migration history before deliberate session invalidation.
- Independent target inspection passed: all eight public tables have RLS; eight runtime policies; no browser-role table access; runtime role has no elevated flags or parent roles, no restored password, and no financial-table access; memberships reference restored Auth identities; application/provider sessions are inactive.
- Synthetic drill separately preserved a long exact-decimal evidence string, audit and membership data, and deliberately invalidated a previously active application session. Actual source has no financial ledger to reconcile yet.
- Independent hosted inspection after the drill found both memberships still active, unchanged parity and no financial source rows. The working database, Auth passwords, runtime credential and deployed sign-in were not changed.

After validation, the disposable restored container and its volumes were removed with the project-scoped CLI stop/no-backup operation; independent Docker inspection confirmed their absence. Only encrypted archives and separately protected keys remain.

Local verification: `cd backend && uv run --locked pytest -q -rN` **377 passed, 63 PostgreSQL cases skipped**; Ruff check/format passed. **26 new recovery/capture cases** cover the changed boundaries. Actual PostgreSQL restore evidence above is separate from skipped integration fixtures.

Archive digests, private identifiers, SQL diagnostics and local resource manifests remain ignored and private. Public tests use invented data. No exact portfolio values or identity records appear in this document.

## Remaining gates

Scheduled backups/retention, independent key custody, restore into a replacement hosted project, both browser logins after hosted recovery, runtime-credential rotation/rebinding with active data, Storage/object recovery and future financial reconciliation are still open. Recover provider root/encryption keys separately when features depending on them exist; logical SQL alone does not prove recovery of provider-encrypted secrets. Never select this isolated target as production. Current working logins retain their existing credentials; restored sessions intentionally require fresh login.

References rechecked on 12 November 2026: [Supabase CLI recovery](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore), [Free-plan backup guidance](https://supabase.com/docs/guides/platform/backups), [PostgreSQL dump consistency](https://www.postgresql.org/docs/17/app-pgdump.html), [password-free role exports](https://www.postgresql.org/docs/17/app-pg-dumpall.html), [AES-GCM authenticated encryption](https://cryptography.io/en/latest/hazmat/primitives/aead/).
