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

    async def test_activity_callback_forwards_only_to_fixed_private_sync_object(self):
        import json
        from contextlib import asynccontextmanager
        from unittest.mock import AsyncMock

        module = load_worker()
        captured = []

        async def forward(request):
            captured.append(request)
            return SimpleNamespace(
                status=200, text=AsyncMock(return_value='{"entries":[]}')
            )

        @asynccontextmanager
        async def hosted(binding, **options):
            result = await options["cash_activity"]({"snapshot_id": "saved"})
            self.assertEqual(result, ({"entries": []}, 200))
            yield object()

        worker = module.SessionApplicationDO()
        worker.ctx = SimpleNamespace()
        worker.env = SimpleNamespace(
            HYPERDRIVE=object(),
            PUBLIC_ORIGIN="https://sessions.example",
            SUPABASE_PROJECT_REF="synthetic",
            SUPABASE_PUBLISHABLE_KEY="synthetic",
            LOGIN_CSRF_KEY="synthetic",
            SYNC=SimpleNamespace(
                idFromName=lambda name: name,
                get=lambda name: SimpleNamespace(fetch=forward),
            ),
        )
        module.buffered_fetch = AsyncMock(return_value="response")
        js = SimpleNamespace(
            Object=SimpleNamespace(new=SimpleNamespace),
            Request=SimpleNamespace(
                new=lambda url, options: (url, options.method, options.body)
            ),
        )
        with patch.dict(
            sys.modules,
            {
                "meridian.security.hosted": SimpleNamespace(hosted_application=hosted),
                "js": js,
                "pydantic": SimpleNamespace(SecretStr=str),
            },
        ):
            self.assertEqual(await worker.fetch(object()), "response")
        self.assertEqual(
            captured[0][:2], ("https://sync.internal/cash-activity", "POST")
        )
        self.assertEqual(json.loads(captured[0][2]), {"snapshot_id": "saved"})
