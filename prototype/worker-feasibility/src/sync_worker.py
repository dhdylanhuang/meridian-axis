"""Private broker sync entrypoint with one shared manual/scheduled authority."""

import asyncio
import time

from workers import DurableObject, Response, WorkerEntrypoint

_LOCK = asyncio.Lock()
_SIGNAL_LOCK = asyncio.Lock()


def deadline(value):
    return value if isinstance(value, (int, float)) else 0


class BrokerSyncDO(DurableObject):
    async def fetch(self, request):
        from urllib.parse import urlsplit

        path = urlsplit(request.url).path
        if path == "/export-evidence" and request.method == "POST":
            return await self.export_evidence(request)
        if path == "/cutoff-holdings" and request.method == "POST":
            return await self.cutoff_holdings(request)
        if (
            path in {"/cash-activity", "/observed-performance"}
            and request.method == "POST"
        ):
            async with _LOCK:
                engine = None
                performance = path == "/observed-performance"
                unavailable = (
                    "performance_unavailable" if performance else "activity_unavailable"
                )
                try:
                    import json

                    from meridian.application.cash_activity import cash_activity_page
                    from meridian.security.hosted import create_binding_engine

                    if performance:
                        from meridian.application.performance_evidence import (
                            MAX_REQUEST_BYTES,
                            PerformanceUnavailable,
                            performance_report,
                        )

                    raw = await request.text()
                    if len(raw.encode()) > (MAX_REQUEST_BYTES if performance else 2048):
                        return Response.json(
                            {"error": "request_invalid"},
                            status=400,
                            headers={"Cache-Control": "no-store"},
                        )
                    if int(time.time() * 1000) < deadline(
                        await self.ctx.storage.get("database-not-before")
                    ):
                        return Response.json(
                            {"error": unavailable},
                            status=503,
                            headers={"Cache-Control": "no-store"},
                        )
                    engine = create_binding_engine(
                        self.env.HYPERDRIVE, expected_role="meridian_sync_public"
                    )

                    if performance:

                        async def calculate(encoded):
                            return str(
                                await self.env.RECONCILIATION.observedPerformance(
                                    encoded
                                )
                            )

                        try:
                            result = await performance_report(engine, json.loads(raw), calculate)
                        except PerformanceUnavailable as error:
                            return Response.json(
                                {"error": str(error)}, status=503,
                                headers={"Cache-Control": "no-store"},
                            )
                        return Response(
                            result, status=200,
                            headers={"Cache-Control": "no-store", "Content-Type": "application/json"},
                        )

                    async def reconcile(encoded):
                        return str(
                            await self.env.RECONCILIATION.cashActivityDetails(encoded)
                        )

                    result, status = await cash_activity_page(
                        engine, json.loads(raw), reconcile
                    )
                    return Response.json(
                        result, status=status, headers={"Cache-Control": "no-store"}
                    )
                except ValueError:
                    return Response.json(
                        {"error": "request_invalid"},
                        status=400,
                        headers={"Cache-Control": "no-store"},
                    )
                except Exception:  # noqa: BLE001 — private errors never expose input or credentials
                    return Response.json(
                        {"error": unavailable},
                        status=503,
                        headers={"Cache-Control": "no-store"},
                    )
                finally:
                    if engine is not None:
                        engine.dispose()
        if request.method != "POST" or path not in {"/refresh", "/scheduled"}:
            return Response("Not found", status=404)
        if path == "/refresh":
            # Operational deadlines only: no financial/session data in object storage.
            async with _SIGNAL_LOCK:
                now = int(time.time() * 1000)
                blocked = max(
                    deadline(await self.ctx.storage.get("manual-not-before")),
                    deadline(await self.ctx.storage.get("database-not-before")),
                )
                if now < blocked:
                    return Response.json(
                        {"status": "deferred"},
                        status=202,
                        headers={"Cache-Control": "no-store"},
                    )
                await self.ctx.storage.put("manual-not-before", now + 60_000)
                # A durable signal acknowledges without waiting for broker execution.
                await self.ctx.storage.setAlarm(now + 1)
            return Response.json(
                {"status": "queued"}, status=202, headers={"Cache-Control": "no-store"}
            )
        result = await self.execute(scheduled=True)
        return Response.json(
            result,
            status=503 if result["status"] == "unavailable" else 200,
            headers={"Cache-Control": "no-store"},
        )

    async def export_evidence(self, request):
        import json
        from datetime import UTC, datetime

        from meridian.adapters.trading212 import Trading212Client
        from meridian.application.broker_jobs import BrokerJobs
        from meridian.application.broker_sync import decimal_strings
        from meridian.application.export_evidence import export_history
        from meridian.security.hosted import create_binding_engine
        from sqlalchemy.orm import Session

        headers = {"Cache-Control": "no-store"}
        engine = None
        try:
            raw = await request.text()
            if len(raw.encode()) > 4096:
                return Response.json({"error": "request_invalid"}, status=400, headers=headers)
            async with _LOCK:
                now = int(time.time() * 1000)
                blocked = deadline(await self.ctx.storage.get("database-not-before"))
                if now < blocked:
                    return Response.json(
                        {"error": "export_evidence_unavailable"}, status=503, headers=headers
                    )
                engine = create_binding_engine(
                    self.env.HYPERDRIVE, expected_role="meridian_sync_public"
                )
                with engine.connect() as connection:
                    if connection.dialect.name == "postgresql":
                        connection.exec_driver_sql(
                            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                        )
                        connection.exec_driver_sql("SET LOCAL statement_timeout = '2s'")
                    with Session(bind=connection) as db:
                        result = export_history(db, json.loads(raw), datetime.now(UTC))
            result["orders"] = {"reason": "pending_orders_unavailable", "rows": None}
            jobs = BrokerJobs(engine, "shared-isa")
            try:
                async with asyncio.timeout(2), Trading212Client(
                    api_key=self.env.BROKER_API_KEY,
                    api_secret=self.env.BROKER_API_SECRET,
                    environment=self.env.BROKER_ENVIRONMENT,
                    max_attempts=1, reserve_request=jobs.reserve, observe_response=jobs.observe,
                ) as api:
                    pending = await api.pending_orders()
                if len(pending) <= 1000:
                    result["orders"] = {"reason": None, "rows": decimal_strings(pending),
                                        "as_of": datetime.now(UTC).isoformat()}
            except Exception:  # noqa: BLE001 — keep completed history if the live read fails.
                result["orders"]["reason"] = "pending_orders_unavailable"
            return Response.json(result, headers=headers)
        except Exception:  # noqa: BLE001 — keep private inputs out of HTTP errors.
            return Response.json({"error": "export_evidence_unavailable"}, status=503, headers=headers)
        finally:
            if engine is not None:
                engine.dispose()

    async def cutoff_holdings(self, request):
        import json
        from datetime import UTC, datetime

        from meridian.application.cutoff_holdings import read_holdings
        from meridian.security.hosted import create_binding_engine

        headers = {"Cache-Control": "no-store"}
        engine = None
        async with _LOCK:
            try:
                raw = await request.text()
                if len(raw.encode()) > 24 * 1024:
                    return Response.json({"error": "request_invalid"}, status=400, headers=headers)
                if int(time.time() * 1000) < deadline(await self.ctx.storage.get("database-not-before")):
                    return Response.json({"error": "cutoff_holdings_unavailable"}, status=503, headers=headers)
                engine = create_binding_engine(
                    self.env.HYPERDRIVE, expected_role="meridian_sync_public"
                )
                result = read_holdings(engine, json.loads(raw), now=datetime.now(UTC))
                return Response.json(result, headers=headers)
            except (KeyError, TypeError, ValueError):
                return Response.json({"error": "request_invalid"}, status=400, headers=headers)
            except Exception:  # noqa: BLE001 — keep private evidence out of HTTP errors.
                return Response.json({"error": "cutoff_holdings_unavailable"}, status=503, headers=headers)
            finally:
                if engine is not None:
                    engine.dispose()

    async def alarm(self, alarm_info=None):
        from datetime import datetime

        result = await self.execute(scheduled=False)
        if result.get("retry_at"):
            retry = datetime.fromisoformat(result["retry_at"])
            await self.ctx.storage.setAlarm(int(retry.timestamp() * 1000))

    async def execute(self, *, scheduled):
        async with _LOCK:
            now = int(time.time() * 1000)
            if now < deadline(await self.ctx.storage.get("database-not-before")):
                return {"status": "deferred"}
            try:
                from meridian.security.hosted_sync import run_sync

                binding = getattr(self.env, "RECONCILIATION", None)

                async def reconcile_cash(encoded):
                    return str(await binding.reconcileCash(encoded))

                async def calculate_exposures(encoded):
                    return str(await binding.portfolioExposures(encoded))

                result = await run_sync(
                    self.env.HYPERDRIVE,
                    api_key=self.env.BROKER_API_KEY,
                    api_secret=self.env.BROKER_API_SECRET,
                    environment=self.env.BROKER_ENVIRONMENT,
                    scheduled=scheduled,
                    reconcile_cash=reconcile_cash if binding else None,
                    calculate_exposures=calculate_exposures if binding else None,
                )
            except Exception:
                result = {"status": "unavailable"}
            if result.get("status") in {"unavailable", "failed"}:
                failures = deadline(await self.ctx.storage.get("database-failures")) + 1
                delay = min(3_600_000, 600_000 * 2 ** min(failures - 1, 3))
                until = int(time.time() * 1000) + delay
                await self.ctx.storage.put("database-failures", failures)
                await self.ctx.storage.put("database-not-before", until)
                # Do not allow a shorter manual alarm retry to undo outage backoff.
                from datetime import UTC, datetime

                retry = result.get("retry_at")
                if retry:
                    until = max(until, int(datetime.fromisoformat(retry).timestamp() * 1000))
                result["retry_at"] = datetime.fromtimestamp(until / 1000, UTC).isoformat()
            elif result.get("status") in {"succeeded", "outside_session"}:
                await self.ctx.storage.put("database-failures", 0)
                await self.ctx.storage.put("database-not-before", 0)
                if scheduled and now >= deadline(
                    await self.ctx.storage.get("retention-not-before")
                ):
                    # One daily fixed-scope SQL call, not a payload scan in Python.
                    try:
                        from meridian.security.hosted_sync import run_retention

                        retention = run_retention(self.env.HYPERDRIVE)
                        complete = retention.get("status") in {"completed", "already_completed"}
                    except Exception:
                        complete = False
                    # Failed cleanup cannot invalidate a successfully published snapshot.
                    # Retry at most hourly; daily database audit also fences duplicate calls.
                    if not complete:
                        print("broker_retention_deferred")
                    due = (now // 86_400_000 + 1) * 86_400_000 if complete else now + 3_600_000
                    await self.ctx.storage.put("retention-not-before", due)
                    result["retention"] = "completed" if complete else "deferred"
            return result


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response("Not found", status=404)
