"""Check routing/delegation with SDK doubles; real runtime needs workerd."""

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class NativeProbeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.health = AsyncMock(return_value={"status": "ok"})
        self.probe = AsyncMock(return_value={"synthetic": True})

        class Response:
            def __init__(self, body, status=200, headers=None):
                self.body, self.status, self.headers = body, status, headers

            @staticmethod
            def json(body):
                return Response(body)

        module_path = Path(__file__).resolve().parents[1] / "src/native_probe.py"
        spec = importlib.util.spec_from_file_location("native_probe_control_test", module_path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(
            "sys.modules",
            {
                "main": SimpleNamespace(health=self.health, probe=self.probe),
                "workers": SimpleNamespace(Response=Response, WorkerEntrypoint=object),
            },
        ):
            spec.loader.exec_module(self.module)
        self.worker = self.module.Default()

    async def test_get_delegates_each_request_without_cached_results(self):
        for path, function in (("/health", self.health), ("/probe", self.probe)):
            for _ in range(2):
                result = await self.worker.fetch(
                    SimpleNamespace(url="https://synthetic.invalid" + path, method="GET")
                )
                self.assertEqual(result.status, 200)
                self.assertIs(result.body, function.return_value)
            self.assertEqual(function.await_count, 2)

    async def test_known_routes_reject_non_get_without_running_probe(self):
        for path in ("/health", "/probe"):
            for method in ("POST", "PUT", "DELETE", "OPTIONS", "HEAD"):
                response = await self.worker.fetch(
                    SimpleNamespace(url="https://synthetic.invalid" + path, method=method)
                )
                self.assertEqual(response.status, 405)
                self.assertEqual(response.headers, {"Allow": "GET"})
        self.health.assert_not_awaited()
        self.probe.assert_not_awaited()

    async def test_unknown_paths_return_404(self):
        for path in ("/", "/probe/", "/health/", "/other"):
            response = await self.worker.fetch(
                SimpleNamespace(url="https://synthetic.invalid" + path, method="GET")
            )
            self.assertEqual(response.status, 404)
        self.health.assert_not_awaited()
        self.probe.assert_not_awaited()
