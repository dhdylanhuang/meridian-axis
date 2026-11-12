"""Private object for a protected restricted-role diagnostic; not application Auth."""

import asyncio
from urllib.parse import urlsplit

import pg8000.dbapi
from runtime_access_probe import run_runtime_access_probe
from workers import DurableObject, Response, WorkerEntrypoint

_DATABASE_LOCK = asyncio.Lock()


class RuntimeAccessProbeDO(DurableObject):
    async def fetch(self, request):
        url = urlsplit(request.url)
        if url.path != "/probe":
            return Response("Not found", status=404)
        if request.method != "GET":
            return Response("Method not allowed", status=405, headers={"Allow": "GET"})
        if url.query or url.fragment:
            return Response("Unexpected input", status=400)

        def connect():
            binding = self.env.HYPERDRIVE
            return pg8000.dbapi.connect(
                user=binding.user,
                password=binding.password,
                host=binding.host,
                port=int(binding.port),
                database=binding.database,
                # Only the Worker-to-Hyperdrive local hop omits TLS. Its
                # separately configured origin must require verified TLS.
                ssl_context=False,
                timeout=20,
            )

        async with _DATABASE_LOCK:
            result = run_runtime_access_probe(connect)
        return Response.json(result, status=200 if result["status"] == "ok" else 503)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response("Not found", status=404)
