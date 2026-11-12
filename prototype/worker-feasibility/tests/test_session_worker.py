"""Finite ASGI adapter owns completion/cancellation without detached HTTP tasks."""

import asyncio
import importlib.util
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class FakeResponse:
    def __init__(self, body, *, status, headers):
        self.body, self.status, self.headers = body, status, headers


def load_worker():
    workers = SimpleNamespace(
        DurableObject=object,
        WorkerEntrypoint=object,
        Response=FakeResponse,
        asgi=SimpleNamespace(request_to_scope=lambda *args: {"type": "http"}),
    )
    spec = importlib.util.spec_from_file_location(
        "session_worker", Path(__file__).resolve().parents[1] / "src/session_worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "workers": workers,
            "pydantic": SimpleNamespace(SecretStr=str),
            "meridian.security.hosted": SimpleNamespace(hosted_application=None),
        },
    ):
        spec.loader.exec_module(module)
    module._test_workers = workers
    return module


WORKER = load_worker()


class Application:
    def __init__(self, operation):
        self.operation, self.closed = operation, False
        self.router = SimpleNamespace(lifespan_context=self.lifespan)

    @asynccontextmanager
    async def lifespan(self, app):
        try:
            yield
        finally:
            self.closed = True

    async def __call__(self, *args):
        await self.operation(*args)


class SessionWorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch.dict(sys.modules, {"workers": WORKER._test_workers})
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_complete_stream_and_cookie_pairs_before_return(self):
        completed = False

        async def run(scope, receive, send):
            nonlocal completed
            self.assertEqual((await receive())["body"], b"")
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"set-cookie", b"first=synthetic"),
                        (b"set-cookie", b"second=synthetic"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b"{", "more_body": True})
            await asyncio.sleep(0)
            await send({"type": "http.response.body", "body": b"}"})
            await asyncio.sleep(0)
            completed = True

        app = Application(run)
        response = await WORKER.buffered_fetch(
            app, SimpleNamespace(body=None), None, None
        )
        self.assertEqual(response.body, b"{}")
        self.assertEqual(len(response.headers), 2)
        self.assertTrue(completed and app.closed)

    async def test_cancellation_joins_application_cleanup_before_return(self):
        started, cleaned = asyncio.Event(), asyncio.Event()

        async def run(scope, receive, send):
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        app = Application(run)
        task = asyncio.create_task(
            WORKER.buffered_fetch(app, SimpleNamespace(body=None), None, None)
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cleaned.is_set() and app.closed)

    async def test_oversized_response_fails_and_closes_lifespan(self):
        async def run(scope, receive, send):
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b"x" * 65537})

        app = Application(run)
        with self.assertRaisesRegex(ValueError, "response_invalid"):
            await WORKER.buffered_fetch(app, SimpleNamespace(body=None), None, None)
        self.assertTrue(app.closed)
