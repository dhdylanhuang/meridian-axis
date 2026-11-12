"""Finite ASGI adapter owns completion/cancellation without detached HTTP tasks."""

import asyncio
import importlib.util
import sys
import unittest
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
        asgi=SimpleNamespace(fetch=None),
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


class SessionWorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch.dict(sys.modules, {"workers": WORKER._test_workers})
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_waits_for_pinned_sdk_completion_before_return(self):
        finished = False
        expected = object()

        async def fetch(app, request, env, ctx):
            nonlocal finished
            await asyncio.sleep(0)
            finished = True
            return expected

        WORKER._test_workers.asgi.fetch = fetch
        self.assertIs(await WORKER.buffered_fetch(None, None, None, None), expected)
        self.assertTrue(finished)

    async def test_cancellation_joins_sdk_cleanup(self):
        started, cleaned, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def fetch(*args):
            try:
                started.set()
                await release.wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        WORKER._test_workers.asgi.fetch = fetch
        task = asyncio.create_task(WORKER.buffered_fetch(None, None, None, None))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        self.assertFalse(cleaned.is_set())
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cleaned.is_set())
