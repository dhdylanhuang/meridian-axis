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
        async with _LOCK:
            try:
                from meridian.security.hosted_sync import run_sync
                result = await run_sync(self.env.HYPERDRIVE, api_key=self.env.BROKER_API_KEY,
                                        api_secret=self.env.BROKER_API_SECRET,
                                        environment=self.env.BROKER_ENVIRONMENT,
                                        scheduled=path == "/scheduled")
                return Response.json(result, headers={"Cache-Control": "no-store"})
            except Exception:
                return Response.json({"status": "unavailable"}, status=503,
                                     headers={"Cache-Control": "no-store"})


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # workers_dev and preview URLs are disabled. Only the approved service
        # binding has access. Browser session/CSRF checks happen before dispatch.
        from js import Request
        from urllib.parse import urlsplit
        if request.method != "POST" or urlsplit(request.url).path != "/refresh":
            return Response("Not found", status=404)
        stub = self.env.SYNC.get(self.env.SYNC.idFromName("shared-isa"))
        return await stub.fetch(Request.new("https://sync.internal/refresh", method="POST"))

    async def scheduled(self, controller):
        from js import Request
        stub = self.env.SYNC.get(self.env.SYNC.idFromName("shared-isa"))
        await stub.fetch(Request.new("https://sync.internal/scheduled", method="POST"))
