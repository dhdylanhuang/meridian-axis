"""Private broker sync entrypoint with one shared manual/scheduled authority."""

import asyncio
from workers import DurableObject, Response, WorkerEntrypoint

_LOCK = asyncio.Lock()


class BrokerSyncDO(DurableObject):
    async def fetch(self, request):
        from urllib.parse import urlsplit

        path = urlsplit(request.url).path
        if request.method != "POST" or path not in {"/refresh", "/scheduled"}:
            return Response("Not found", status=404)
        if path == "/refresh":
            import time

            # A durable signal acknowledges immediately while broker work runs
            # independently of the session object's serialised request lock.
            await self.ctx.storage.setAlarm(int(time.time() * 1000) + 1)
            return Response.json(
                {"status": "queued"}, status=202, headers={"Cache-Control": "no-store"}
            )
        result = await self.execute(scheduled=True)
        return Response.json(
            result,
            status=503 if result["status"] == "unavailable" else 200,
            headers={"Cache-Control": "no-store"},
        )

    async def alarm(self, alarm_info=None):
        from datetime import datetime

        result = await self.execute(scheduled=False)
        if result.get("retry_at"):
            retry = datetime.fromisoformat(result["retry_at"])
            await self.ctx.storage.setAlarm(int(retry.timestamp() * 1000))

    async def execute(self, *, scheduled):
        async with _LOCK:
            try:
                from meridian.security.hosted_sync import run_sync

                return await run_sync(
                    self.env.HYPERDRIVE,
                    api_key=self.env.BROKER_API_KEY,
                    api_secret=self.env.BROKER_API_SECRET,
                    environment=self.env.BROKER_ENVIRONMENT,
                    scheduled=scheduled,
                )
            except Exception:
                return {"status": "unavailable"}


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response("Not found", status=404)
