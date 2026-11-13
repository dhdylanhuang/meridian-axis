"""Manual refresh uses a durable signal outside the broker execution lock."""

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


class SyncWorkerTests(unittest.IsolatedAsyncioTestCase):
    def load_worker(self):
        spec = importlib.util.spec_from_file_location(
            "sync_worker", Path(__file__).resolve().parents[1] / "src/sync_worker.py"
        )
        module = importlib.util.module_from_spec(spec)
        modules = {
            "workers": SimpleNamespace(
                WorkerEntrypoint=object, DurableObject=object, Response=Mock()
            ),
            "js": SimpleNamespace(
                Object=SimpleNamespace(new=SimpleNamespace),
                Request=SimpleNamespace(
                    new=lambda url, options: (url, {"method": options.method})
                ),
            ),
        }
        patcher = patch.dict("sys.modules", modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        spec.loader.exec_module(module)
        return module

    async def test_manual_signal_is_durable_and_does_not_wait_for_running_broker_work(
        self,
    ):
        module = self.load_worker()
        module.Response.json = lambda body, **options: SimpleNamespace(
            body=body, **options
        )
        worker = module.BrokerSyncDO()
        alarm = AsyncMock()
        worker.ctx = SimpleNamespace(storage=SimpleNamespace(setAlarm=alarm))
        worker.execute = AsyncMock(
            side_effect=AssertionError("Queue must not execute broker I/O")
        )
        async with module._LOCK:
            response = await worker.fetch(
                SimpleNamespace(method="POST", url="https://sync.internal/refresh")
            )
        self.assertEqual(response.status, 202)
        self.assertEqual(response.body, {"status": "queued"})
        alarm.assert_awaited_once()
        worker.execute.assert_not_called()

    async def test_alarm_executes_bounded_manual_job_and_honours_persisted_retry(self):
        module = self.load_worker()
        worker = module.BrokerSyncDO()
        alarm = AsyncMock()
        worker.ctx = SimpleNamespace(storage=SimpleNamespace(setAlarm=alarm))
        worker.execute = AsyncMock(
            return_value={"status": "failed", "retry_at": "2026-11-13T12:00:00+00:00"}
        )
        await worker.alarm(SimpleNamespace(retryCount=0))
        worker.execute.assert_awaited_once_with(scheduled=False)
        self.assertEqual(alarm.await_args.args[0], 1794571200000)
