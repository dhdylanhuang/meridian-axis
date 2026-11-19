# Next delivery: broker-led automatic discovery and enrichment

Reviewed **19 November 2026**. The owner selected this next step after the local
quantity diagnostic (`c2cf7b3`). Orders stay in Trading 212; one integrated AXIS
serves PM, trading-monitoring, risk and portfolio treasury/cash workflows.

## Implemented source boundary

Reuse the existing snapshot and held-listing metadata jobs. New positions already
appear on successful broker refresh. Close the daily/scheduled-only metadata gap:
allow new held tickers to request the same metadata job early, preserving active
leases, failure backoff and provider reservations. Enrich the approved snapshot
with whitelisted listing facts and coverage/provenance, and display changes and
metadata limitations through the existing private view. Missing metadata must not
block account/position publication or invent prices. No schema/access change.

Remove the proposed duplicate live-price/current-account valuation requirement.
There is no second implemented live-price service to delete. Retain historical
price/benchmark/FX inputs for later risk/performance. Preserve ten-minute polling,
manual refresh, broker authority and immutable evidence. Read current status for
exact passing checks and deployment state before continuing.

The source implementation is complete with targeted offline checks and is not yet
deployed. Next action is the bounded existing-Worker release and actual enrichment
verification when the quota incident allows it. Current broker
figures publish first; newly fetched metadata appears in the next successful
snapshot. No extra browser/API request or independent current valuation engine.
The unused local quote interval/retention settings and sample environment entries
have been removed. The Worker allowlist includes the shared metadata module.

## Following deliveries

1. Integrate traceable transaction/cash reconciliation; cash/dividend/fee semantics
   and openings/coverage remain unverified. The local quantity diagnostic has 12
   passing tests; reuse evidence for unchanged paths.
2. Portfolio/risk analytics using broker current facts and supported historical
   daily inputs. Do not substitute intraday observations for daily risk history.
3. Complete integrated workflows, alerts, stress, attribution and projections in
   bounded deliveries; no role hierarchy, order execution or tax engine.
4. Operational acceptance: post-reset login/cadence/query usage, browser/workload
   qualification, scheduled backup/key custody and current-schema restore.

## Preserve operational boundaries

Native parity `0008`; deployed sync `0afd670`, session/gateway `073ffca` until a
separately recorded release. Sixty-day detailed expiry preserves daily/latest and
financial history. Manual XLSX archive is complete; do not access/change the real
workbook. Do not probe exhausted Hyperdrive before the scheduled 20 November
00:00 UTC reset. No repeated full suites, CI matrices, sizing or live probes.
Keep exact checks/unfinished work in status. No raw-history grants to the BFF.
