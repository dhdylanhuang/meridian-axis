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

    async def test_successful_scheduled_work_runs_retention_once_per_utc_day(self):
        module = self.load_worker()
        state = {}
        worker = module.BrokerSyncDO()
        worker.ctx = SimpleNamespace(storage=self.storage(state=state))
        worker.env = SimpleNamespace(HYPERDRIVE=object(), BROKER_API_KEY="synthetic",
                                     BROKER_API_SECRET="synthetic", BROKER_ENVIRONMENT="demo")
        run = AsyncMock(return_value={"status": "succeeded"})
        retention = Mock(return_value={"status": "completed"})
        with patch.dict("sys.modules", {"meridian.security.hosted_sync": SimpleNamespace(
                run_sync=run, run_retention=retention)}):
            with patch.object(module.time, "time", return_value=1000):
                await worker.execute(scheduled=False)
                retention.assert_not_called()
                await worker.execute(scheduled=True)
                await worker.execute(scheduled=True)
                retention.assert_called_once()
                self.assertEqual(state["retention-not-before"], 86400000)
            with patch.object(module.time, "time", return_value=86401):
                await worker.execute(scheduled=True)
                self.assertEqual(retention.call_count, 2)

    async def test_retention_failure_keeps_snapshot_success_and_waits_an_hour(self):
        module = self.load_worker()
        state = {}
        worker = module.BrokerSyncDO()
        worker.ctx = SimpleNamespace(storage=self.storage(state=state))
        worker.env = SimpleNamespace(HYPERDRIVE=object(), BROKER_API_KEY="synthetic",
                                     BROKER_API_SECRET="synthetic", BROKER_ENVIRONMENT="demo")
        run = AsyncMock(return_value={"status": "succeeded"})
        retention = Mock(side_effect=RuntimeError("synthetic"))
        with patch.dict("sys.modules", {"meridian.security.hosted_sync": SimpleNamespace(
                run_sync=run, run_retention=retention)}):
            with patch.object(module.time, "time", return_value=1000):
                result = await worker.execute(scheduled=True)
                await worker.execute(scheduled=True)
                self.assertEqual(result["status"], "succeeded")
                self.assertEqual(result["retention"], "deferred")
                retention.assert_called_once()
                self.assertEqual(state["retention-not-before"], 4600000)

    async def test_private_rust_binding_is_passed_to_python_job(self):
        module = self.load_worker()
        worker = module.BrokerSyncDO()
        worker.ctx = SimpleNamespace(storage=self.storage())
        binding = SimpleNamespace(
            reconcileCash=AsyncMock(return_value='{"method":"synthetic"}'),
            portfolioExposures=AsyncMock(
                return_value='{"method":"broker_exposures_v1"}'
            ),
        )
        worker.env = SimpleNamespace(
            HYPERDRIVE=object(),
            BROKER_API_KEY="synthetic",
            BROKER_API_SECRET="synthetic",
            BROKER_ENVIRONMENT="demo",
            RECONCILIATION=binding,
        )

        async def run(_binding, **kwargs):
            self.assertEqual(
                await kwargs["reconcile_cash"]("synthetic-input"),
                '{"method":"synthetic"}',
            )
            self.assertEqual(
                await kwargs["calculate_exposures"]("synthetic-exposures"),
                '{"method":"broker_exposures_v1"}',
            )
            return {"status": "succeeded"}

        with patch.dict(
            "sys.modules",
            {"meridian.security.hosted_sync": SimpleNamespace(run_sync=run)},
        ):
            self.assertEqual(
                (await worker.execute(scheduled=False))["status"], "succeeded"
            )
        binding.reconcileCash.assert_awaited_once_with("synthetic-input")
        binding.portfolioExposures.assert_awaited_once_with("synthetic-exposures")

    async def test_activity_page_uses_readonly_service_without_broker_execution(self):
        module = self.load_worker()
        module.Response.json = lambda body, **options: SimpleNamespace(
            body=body, **options
        )
        worker = module.BrokerSyncDO()
        worker.ctx = SimpleNamespace(storage=self.storage())
        binding = SimpleNamespace(cashActivityDetails=AsyncMock(return_value="result"))
        worker.env = SimpleNamespace(HYPERDRIVE=object(), RECONCILIATION=binding)
        worker.execute = AsyncMock(side_effect=AssertionError("No broker work"))
        engine = Mock()
        create = Mock(return_value=engine)

        async def page(actual, value, reconcile):
            self.assertIs(actual, engine)
            self.assertEqual(value, {"synthetic": True})
            self.assertEqual(await reconcile("request"), "result")
            return {"entries": []}, 200

        with patch.dict(
            "sys.modules",
            {
                "meridian.security.hosted": SimpleNamespace(
                    create_binding_engine=create
                ),
                "meridian.application.cash_activity": SimpleNamespace(
                    cash_activity_page=page
                ),
            },
        ):
            response = await worker.fetch(
                SimpleNamespace(
                    method="POST",
                    url="https://sync.internal/cash-activity",
                    text=AsyncMock(return_value='{"synthetic":true}'),
                )
            )
        self.assertEqual(response.status, 200)
        create.assert_called_once_with(
            worker.env.HYPERDRIVE, expected_role="meridian_sync_public"
        )
        engine.dispose.assert_called_once()
        worker.execute.assert_not_called()

    async def test_performance_uses_fixed_readonly_path_without_broker_execution(self):
        module = self.load_worker()
        module.Response.json = lambda body, **options: SimpleNamespace(
            body=body, **options
        )
        module.Response.side_effect = lambda body, **options: SimpleNamespace(body=body, **options)
        worker = module.BrokerSyncDO()
        worker.ctx = SimpleNamespace(storage=self.storage())
        binding = SimpleNamespace(
            observedPerformance=AsyncMock(return_value="synthetic-result")
        )
        worker.env = SimpleNamespace(HYPERDRIVE=object(), RECONCILIATION=binding)
        worker.execute = AsyncMock(side_effect=AssertionError("No broker work"))
        engine = Mock()
        create = Mock(return_value=engine)

        async def report(actual, value, calculate):
            self.assertIs(actual, engine)
            self.assertEqual(value, {"days": []})
            self.assertEqual(await calculate("invented"), "synthetic-result")
            return '{"method":"modified_dietz_observed_v1"}'

        with patch.dict(
            "sys.modules",
            {
                "meridian.security.hosted": SimpleNamespace(
                    create_binding_engine=create
                ),
                "meridian.application.performance_evidence": SimpleNamespace(
                    performance_report=report,
                    MAX_REQUEST_BYTES=128 * 1024,
                    PerformanceUnavailable=RuntimeError,
                ),
            },
        ):
            response = await worker.fetch(
                SimpleNamespace(
                    method="POST",
                    url="https://sync.internal/observed-performance",
                    text=AsyncMock(return_value='{"days":[]}'),
                )
            )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers, {"Cache-Control": "no-store", "Content-Type":"application/json"})
        create.assert_called_once_with(
            worker.env.HYPERDRIVE, expected_role="meridian_sync_public"
        )
        engine.dispose.assert_called_once()
        worker.execute.assert_not_called()
