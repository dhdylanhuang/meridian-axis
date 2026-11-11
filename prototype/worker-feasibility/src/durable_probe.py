"""Synthetic FastAPI control inside a Durable Object; no storage or credentials."""

from workers import DurableObject, Response, WorkerEntrypoint, asgi

from main import app


class SyntheticProbeDO(DurableObject):
    async def fetch(self, request):
        # Reuse the exact existing synthetic workload. The SQLite-backed namespace
        # is required for Free eligibility, but this probe never uses its storage.
        return await asgi.fetch(app, request, self.env, self.ctx)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # Only the separate gateway's namespace binding reaches the control.
        return Response("Not found", status=404)
