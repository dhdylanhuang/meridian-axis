"""Cron uses the provider's four-argument Python handler and private namespace."""

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

    async def test_cron_dispatches_to_same_named_object_with_no_caller_data(self):
        module = self.load_worker()
        stub = SimpleNamespace(fetch=AsyncMock())
        binding = SimpleNamespace(
            idFromName=Mock(return_value="synthetic-id"), get=Mock(return_value=stub)
        )
        env = SimpleNamespace(SYNC=binding)
        worker = module.Default()
        worker.env = env
        await worker.scheduled(SimpleNamespace(cron="* * * * *"), env, object())
        binding.idFromName.assert_called_once_with("shared-isa")
        stub.fetch.assert_awaited_once_with(
            ("https://sync.internal/scheduled", {"method": "POST"})
        )

    async def test_service_manual_dispatch_uses_same_object(self):
        module = self.load_worker()
        stub = SimpleNamespace(fetch=AsyncMock(return_value="synthetic-response"))
        binding = SimpleNamespace(
            idFromName=Mock(return_value="synthetic-id"), get=Mock(return_value=stub)
        )
        worker = module.Default()
        worker.env = SimpleNamespace(SYNC=binding)
        result = await worker.fetch(
            SimpleNamespace(method="POST", url="https://sync.internal/refresh")
        )
        self.assertEqual(result, "synthetic-response")
        binding.idFromName.assert_called_once_with("shared-isa")
        stub.fetch.assert_awaited_once_with(
            ("https://sync.internal/refresh", {"method": "POST"})
        )

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
