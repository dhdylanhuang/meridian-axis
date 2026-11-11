"""Protected synthetic Hyperdrive transport control; no application-table writes."""

import asyncio
from urllib.parse import urlsplit

import pg8000.dbapi
from workers import DurableObject, Response, WorkerEntrypoint

from database_probe import run_database_probe

_DATABASE_LOCK = asyncio.Lock()


class DatabaseProbeDO(DurableObject):
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
                # This is the Worker-to-Hyperdrive local hop. The separately
                # configured Hyperdrive-to-origin connection must require TLS.
                ssl_context=False,
                timeout=20,
            )

        # Synchronous driver operations must not overlap within an isolate.
        # The probe owns a fresh connection and all transaction cleanup.
        async with _DATABASE_LOCK:
            result = run_database_probe(connect)
        return Response.json(result, status=200 if result["status"] == "ok" else 503)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response("Not found", status=404)
