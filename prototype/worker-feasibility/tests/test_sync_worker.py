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

    def storage(self, alarm=None, state=None):
        state = {} if state is None else state

        async def get(key):
            return state.get(key)

        async def put(key, value):
            state[key] = value

        return SimpleNamespace(get=get, put=put, setAlarm=alarm or AsyncMock())

    async def test_manual_signal_is_durable_and_does_not_wait_for_running_broker_work(
        self,
    ):
        module = self.load_worker()
        module.Response.json = lambda body, **options: SimpleNamespace(
            body=body, **options
        )
        worker = module.BrokerSyncDO()
        alarm = AsyncMock()
        worker.ctx = SimpleNamespace(storage=self.storage(alarm))
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
        worker.ctx = SimpleNamespace(storage=self.storage(alarm))
        worker.execute = AsyncMock(
            return_value={"status": "failed", "retry_at": "2026-11-13T12:00:00+00:00"}
        )
        await worker.alarm(SimpleNamespace(retryCount=0))
        worker.execute.assert_awaited_once_with(scheduled=False)
        self.assertEqual(alarm.await_args.args[0], 1794571200000)

    async def test_repeated_manual_signals_do_not_rearm_during_cooldown(self):
        module = self.load_worker()
        module.Response.json = lambda body, **options: SimpleNamespace(body=body, **options)
        worker = module.BrokerSyncDO()
        alarm = AsyncMock()
        worker.ctx = SimpleNamespace(storage=self.storage(alarm))
        request = SimpleNamespace(method="POST", url="https://sync.internal/refresh")
        with patch.object(module.time, "time", return_value=1000):
            first = await worker.fetch(request)
            second = await worker.fetch(request)
        self.assertEqual(first.body, {"status": "queued"})
        self.assertEqual(second.body, {"status": "deferred"})
        alarm.assert_awaited_once()

    async def test_database_failure_backoff_survives_object_recreation(self):
        module = self.load_worker()
        state = {}
        storage = self.storage(state=state)
        env = SimpleNamespace(HYPERDRIVE=object(), BROKER_API_KEY="synthetic",
                              BROKER_API_SECRET="synthetic", BROKER_ENVIRONMENT="demo")
        run = AsyncMock(side_effect=RuntimeError("synthetic outage"))
        fake = SimpleNamespace(run_sync=run)
        with patch.dict("sys.modules", {"meridian.security.hosted_sync": fake}):
            worker = module.BrokerSyncDO()
            worker.ctx, worker.env = SimpleNamespace(storage=storage), env
            with patch.object(module.time, "time", return_value=1000):
                self.assertEqual((await worker.execute(scheduled=True))["status"], "unavailable")
            restarted = module.BrokerSyncDO()
            restarted.ctx, restarted.env = SimpleNamespace(storage=storage), env
            with patch.object(module.time, "time", return_value=1599):
                self.assertEqual((await restarted.execute(scheduled=True))["status"], "deferred")
            self.assertEqual(run.await_count, 1)
            with patch.object(module.time, "time", return_value=1600):
                await restarted.execute(scheduled=True)
            self.assertEqual(run.await_count, 2)
            self.assertEqual(state["database-not-before"], 2800000)
