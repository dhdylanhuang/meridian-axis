"""Private first-use membership data administration; never run by the application.

No schema/grants/role changes, emails, passwords or public identity seeds.
Execute via a trusted administrator's captured SQL stdin in the pinned project.
"""

from uuid import UUID

from pydantic import SecretStr


def initial_membership_sql(subjects: tuple[str, str]) -> SecretStr:
    if (
        not isinstance(subjects, tuple)
        or len(subjects) != 2
        or any(not isinstance(value, str) for value in subjects)
        or len(set(subjects)) != 2
    ):
        raise ValueError("membership_subjects_invalid")
    try:
        if any(str(UUID(value)) != value for value in subjects):
            raise ValueError
    except ValueError:
        raise ValueError("membership_subjects_invalid") from None
    # Canonical UUID validation above excludes SQL metacharacters.
    first, second = subjects
    return SecretStr(f"""
DO $membership$
DECLARE stamp text;
BEGIN
  PERFORM pg_advisory_xact_lock(87730113);
  IF current_user <> 'postgres' OR current_database() <> 'postgres'
     OR current_schema() <> 'public'
     OR (SELECT version_num FROM public.alembic_version) <> '0005'
     OR EXISTS (SELECT FROM public.accounts)
     OR EXISTS (SELECT FROM public.account_members)
     OR EXISTS (SELECT FROM public.app_sessions)
     OR EXISTS (SELECT FROM public.source_records)
     OR EXISTS (SELECT FROM public.import_log)
  THEN RAISE EXCEPTION 'membership_bootstrap_preconditions_failed'; END IF;
  IF (SELECT count(*) FROM auth.users WHERE id IN ('{first}'::uuid, '{second}'::uuid)) <> 2
  THEN RAISE EXCEPTION 'membership_identity_missing'; END IF;
  stamp := to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') || '+00:00';
  INSERT INTO public.accounts (id, environment, broker, wrapper, currency)
    VALUES ('shared-isa', 'live', 'trading212', 'isa', 'GBP');
  INSERT INTO public.account_members (account_id, auth_subject, slot, created_at)
    VALUES ('shared-isa', '{first}', 1, stamp), ('shared-isa', '{second}', 2, stamp);
  INSERT INTO public.audit_log
    (id, occurred_at, actor, action, entity_type, entity_id, details_json)
    VALUES (replace(gen_random_uuid()::text, '-', ''), stamp, 'administration',
            'membership_provision', 'account', 'shared-isa', '{{"members":2}}');
END $membership$;
SELECT true AS membership_provisioned;
""")
