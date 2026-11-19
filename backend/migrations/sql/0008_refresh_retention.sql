-- A fixed-scope retention capability; no general DELETE privilege is granted.
DO $retention_install$
DECLARE target_schema text := current_schema(); writer text; denied_role text;
BEGIN
 IF NOT (target_schema='public' OR target_schema ~ '^meridian_test_[0-9a-f]{32}$')
 THEN RAISE EXCEPTION 'Retention requires reviewed schema'; END IF;
 writer := 'meridian_sync_' || target_schema;
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=writer)
 THEN RAISE EXCEPTION 'Restricted sync role required'; END IF;
 EXECUTE format($function$
 CREATE FUNCTION %1$I.prune_broker_refresh() RETURNS jsonb
 LANGUAGE plpgsql SECURITY DEFINER
 SET search_path = pg_catalog, pg_temp
 SET statement_timeout = '5s'
 AS $body$
 DECLARE
   stamp timestamptz := statement_timestamp();
   cutoff timestamptz := stamp - interval '60 days';
   day_key text := to_char(stamp AT TIME ZONE 'UTC', 'YYYY-MM-DD');
   audit_id text := 'refresh-retention-' || day_key;
   snapshots text[]; sources text[]; runs text[];
   removed_snapshots integer := 0; removed_sources integer := 0;
 BEGIN
   IF NOT pg_try_advisory_xact_lock(hashtextextended(%2$L, 0)) THEN
     RETURN jsonb_build_object('status','busy');
   END IF;
   IF EXISTS (SELECT 1 FROM %1$I.audit_log WHERE id=audit_id) THEN
     RETURN jsonb_build_object('status','already_completed');
   END IF;
   WITH daily AS MATERIALIZED (
     -- Stored observations are canonical UTC ISO strings. Keep the final
     -- observation of every UTC day, including the global latest snapshot.
     SELECT DISTINCT ON (substring(observed_at,1,10)) id
     FROM %1$I.broker_snapshots WHERE account_id='shared-isa'
     ORDER BY substring(observed_at,1,10), observed_at DESC, id DESC
   ), candidates AS MATERIALIZED (
     SELECT s.id AS snapshot_id, src.id AS source_id, r.id AS run_id
     FROM %1$I.broker_snapshots s
     JOIN %1$I.import_log r ON r.id=s.source_run_id AND r.account_id=s.account_id
     JOIN %1$I.source_records src ON src.run_id=r.id AND src.account_id=r.account_id
     WHERE s.account_id='shared-isa' AND s.observed_at::timestamptz < cutoff
       AND r.kind='trading212_refresh' AND r.status='succeeded'
       AND src.kind='trading212_refresh' AND src.schema_version='trading212_sync_v2'
       AND src.row_number=1
       AND NOT EXISTS (SELECT 1 FROM daily d WHERE d.id=s.id)
       AND NOT EXISTS (SELECT 1 FROM %1$I.source_records other
                       WHERE other.run_id=r.id AND other.id<>src.id)
       AND NOT EXISTS (SELECT 1 FROM %1$I.broker_event_revisions e
                       WHERE e.source_id=src.id)
     ORDER BY s.observed_at, s.id LIMIT 200
     FOR UPDATE OF s,src SKIP LOCKED
   )
   SELECT array_agg(snapshot_id), array_agg(source_id), array_agg(run_id)
     INTO snapshots,sources,runs FROM candidates;
   IF snapshots IS NOT NULL THEN
     DELETE FROM %1$I.broker_snapshots WHERE id=ANY(snapshots) AND account_id='shared-isa';
     GET DIAGNOSTICS removed_snapshots = ROW_COUNT;
     DELETE FROM %1$I.source_records WHERE id=ANY(sources) AND account_id='shared-isa'
       AND kind='trading212_refresh';
     GET DIAGNOSTICS removed_sources = ROW_COUNT;
     IF removed_snapshots<>cardinality(snapshots) OR removed_sources<>cardinality(sources) THEN
       RAISE EXCEPTION 'Retention batch changed';
     END IF;
   END IF;
   INSERT INTO %1$I.audit_log
     (id,occurred_at,actor,action,entity_type,entity_id,run_id,details_json)
   VALUES (audit_id,stamp::text,'broker-retention','refresh_observations_expired',
     'retention_policy','shared-isa',NULL,
     jsonb_build_object('days',60,'batch_limit',200,'daily_observations_preserved',true,
       'cutoff',cutoff,'snapshots_removed',removed_snapshots,'sources_removed',removed_sources,
       'expired_run_ids',COALESCE(to_jsonb(runs),'[]'::jsonb))::text);
   RETURN jsonb_build_object('status','completed','snapshots_removed',removed_snapshots,
     'sources_removed',removed_sources);
 END $body$;
 $function$, target_schema, target_schema || ':shared-isa:refresh-retention');
 EXECUTE format('REVOKE ALL ON FUNCTION %I.prune_broker_refresh() FROM PUBLIC',target_schema);
 FOREACH denied_role IN ARRAY ARRAY['anon','authenticated','meridian_bff_' || target_schema] LOOP
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=denied_role) THEN
     EXECUTE format('REVOKE ALL ON FUNCTION %I.prune_broker_refresh() FROM %I',target_schema,denied_role);
   END IF;
 END LOOP;
 EXECUTE format('GRANT EXECUTE ON FUNCTION %I.prune_broker_refresh() TO %I',target_schema,writer);
END $retention_install$;
