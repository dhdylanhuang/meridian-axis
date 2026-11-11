"""Native fetch control for the same uncached synthetic ASGI probe workload."""

from urllib.parse import urlsplit

from workers import Response, WorkerEntrypoint

from main import health, probe


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlsplit(request.url).path
        if path not in ("/health", "/probe"):
            return Response("Not Found", status=404)
        if request.method != "GET":
            return Response("Method Not Allowed", status=405, headers={"Allow": "GET"})
        result = await (health() if path == "/health" else probe())
        return Response.json(result)
