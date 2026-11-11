"""Offline contract tests; every account, instrument and number is synthetic."""

import asyncio
import base64
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from meridian.adapters.trading212 import BrokerError, Trading212Client

ROOT = "/api/v0/equity/"
INSTRUMENT = {"ticker": "SYNTH_US_EQ", "currency": "USD", "name": "Synthetic"}


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def wall(self):
        return 1_000 + self.now

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def reader(handler, clock=None, **kwargs):
    clock = clock or Clock()
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
    return (
        Trading212Client(
            api_key="synthetic-key",
            api_secret="synthetic-secret",
            client=http,
            monotonic=clock.monotonic,
            wall_clock=clock.wall,
            sleep=clock.sleep,
            random_value=lambda: 1,
            **kwargs,
        ),
        http,
        clock,
    )


def order(fill_id, *, kind="TRADE", quantity=0.125):
    return {
        "order": {
            "id": 80000000000000001,
            "instrument": INSTRUMENT,
            "side": "BUY",
            "status": "PARTIALLY_FILLED",
            "quantity": 999,
        },
        "fill": {
            "id": fill_id,
            "filledAt": "2026-10-01T11:00:00+01:00",
            "quantity": quantity,
            "price": 12.4,
            "type": kind,
            "walletImpact": {"currency": "GBP", "netValue": -1.2},
        },
        "newProviderField": "preserved",
    }


def test_decimal_ids_basic_auth_and_partial_fills_are_preserved():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert request.url.host == "demo.trading212.com"
        expected = base64.b64encode(b"synthetic-key:synthetic-secret").decode()
        assert request.headers["authorization"] == "Basic " + expected
        if request.url.path.endswith("summary"):
            return httpx.Response(
                200,
                content=b'{"id":9007199254740993,"currency":"GBP",'
                b'"totalValue":0.1000000000000000000000001}',
            )
        return httpx.Response(
            200,
            json={
                "items": [order(9007199254740993), order(9007199254740994)],
                "nextPagePath": None,
            },
        )

    async def scenario():
        api, http, _ = reader(handler)
        async with http:
            summary = await api.account_summary()
            fills = await api.order_history()
            assert summary.account_id == "9007199254740993"
            assert summary.total_value == Decimal("0.1000000000000000000000001")
            assert [f.fill.fill_id for f in fills] == ["9007199254740993", "9007199254740994"]
            assert fills[0].order_id == fills[1].order_id == "80000000000000001"
            assert fills[0].fill.quantity == Decimal("0.125")
            assert fills[0].fill.price == Decimal("12.4")
            assert fills[0].fill.filled_at == datetime(2026, 10, 1, 10, tzinfo=UTC)
            assert fills[0].raw_payload["newProviderField"] == "preserved"
            assert fills[0].raw_payload["fill"]["walletImpact"]["netValue"] == Decimal("-1.2")
            assert "synthetic-key" not in repr(api)
            await api.aclose()
            assert not http.is_closed  # Injected clients remain caller-owned.

    asyncio.run(scenario())
    assert len(requests) == 2


def test_all_other_observation_methods_and_unknown_types():
    fixtures = {
        "positions": [
            {
                "instrument": INSTRUMENT,
                "quantity": -0.25,
                "currentPrice": 12.4,
                "averagePricePaid": 11,
                "createdAt": "2026-09-01T00:00:00Z",
            }
        ],
        "history/dividends": {
            "items": [
                {
                    "reference": "DIV-1",
                    "paidOn": "2026-10-02T00:00:00Z",
                    "amount": 2.5,
                    "currency": "GBP",
                    "type": "FUTURE_DIVIDEND_KIND",
                    "instrument": INSTRUMENT,
                }
            ],
            "nextPagePath": None,
        },
        "history/transactions": {
            "items": [
                {
                    "reference": "CASH-1",
                    "dateTime": "2026-10-02T00:00:00Z",
                    "amount": -10.5,
                    "currency": "GBP",
                    "type": "TRANSFER",
                }
            ],
            "nextPagePath": None,
        },
        "metadata/instruments": [
            {
                "ticker": "SYNTH_US_EQ",
                "currencyCode": "USD",
                "name": "Synthetic",
                "type": "STOCK",
                "workingScheduleId": 9007199254740993,
            }
        ],
        "metadata/exchanges": [
            {
                "id": 1,
                "name": "Synthetic Exchange",
                "workingSchedules": [
                    {
                        "id": 9007199254740993,
                        "timeEvents": [
                            {
                                "date": "2026-10-01T13:30:00Z",
                                "type": "OPEN",
                            }
                        ],
                    }
                ],
            }
        ],
    }

    def handler(request):
        return httpx.Response(200, json=fixtures[request.url.path.removeprefix(ROOT)])

    async def scenario():
        api, http, _ = reader(handler)
        async with http:
            position = (await api.positions())[0]
            assert position.quantity == Decimal("-0.25")  # No inferred side/sign correction.
            assert position.opened_at == datetime(2026, 9, 1, tzinfo=UTC)
            assert not hasattr(position, "quote_timestamp")
            assert (await api.dividend_history())[0].dividend_type == "FUTURE_DIVIDEND_KIND"
            assert (await api.transaction_history())[0].amount == Decimal("-10.5")
            assert (await api.instruments())[0].working_schedule_id == "9007199254740993"
            assert (await api.exchanges())[0].working_schedules[0].schedule_id == "9007199254740993"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "continuation",
    [
        "https://evil.example/api/v0/equity/history/orders?cursor=2",
        "//evil.example/api/v0/equity/history/orders?cursor=2",
        "https://user:password@demo.trading212.com/api/v0/equity/history/orders?cursor=2",
        "https://live.trading212.com/api/v0/equity/history/orders?cursor=2",
        "/api/v0/equity/history/transactions?cursor=2",
        "/api/v0/equity/orders?cursor=2",
        "/api/v0/equity/history/orders#fragment",
        "/api/v0/equity/history/orders?api_key=leak",
        "/api/v0/equity/history/orders\n?cursor=2",
    ],
)
def test_invalid_continuation_rejected_before_second_request(continuation):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"items": [], "nextPagePath": continuation})

    async def checked():
        api, http, _ = reader(handler)
        async with http:
            with pytest.raises(BrokerError, match="invalid_continuation"):
                await api.order_history()

    asyncio.run(checked())
    assert len(requests) == 1


def test_cash_string_cursor_and_entire_returned_query_are_used():
    requests = []
    next_path = (
        ROOT + "history/transactions?cursor=opaque%2Ftoken&limit=2&time=2026-10-01T00%3A00%3A00Z"
    )

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "items": [],
                "nextPagePath": next_path if len(requests) == 1 else None,
            },
        )

    async def scenario():
        api, http, clock = reader(handler)
        async with http:
            assert await api.transaction_history() == []
            assert clock.sleeps == [3]

    asyncio.run(scenario())
    assert str(requests[1].url) == "https://demo.trading212.com" + next_path


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_terminal_errors_do_not_retry_or_disclose_response(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, text="sensitive synthetic-key synthetic-secret")

    async def scenario():
        api, http, clock = reader(handler)
        async with http:
            with pytest.raises(BrokerError) as error:
                await api.account_summary()
            assert error.value.status == status
            assert error.value.code == "http_failure"
            assert "synthetic" not in str(error.value)
            assert clock.sleeps == []

    asyncio.run(scenario())
    assert len(requests) == 1


def test_backoff_cap_reset_and_shared_endpoint_pacing():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) < 4:
            headers = {"x-ratelimit-reset": "5000"} if len(requests) == 3 else {}
            return httpx.Response(429, headers=headers)
        return httpx.Response(200, json={"id": 1, "currency": "GBP", "totalValue": 10})

    async def scenario():
        api, http, clock = reader(handler, backoff_seconds=600)
        async with http:
            await api.account_summary()
            # 600, then capped 900, then provider reset exceeds the 900 cap.
            assert clock.sleeps == [600, 900, 2500]
            await asyncio.gather(api.account_summary(), api.account_summary())
            assert clock.sleeps[-2:] == [5, 5]

    asyncio.run(scenario())


@pytest.mark.parametrize("first_status", [200, 429])
def test_provider_reset_survives_success_or_exhausted_retry(first_status):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(
            first_status if count == 1 else 200,
            json=[],
            headers={"x-ratelimit-reset": "1020", "x-ratelimit-remaining": "0"}
            if count == 1
            else {},
        )

    async def scenario():
        api, http, clock = reader(handler, max_attempts=1)
        async with http:
            if first_status == 429:
                with pytest.raises(BrokerError, match="retry_exhausted"):
                    await api.positions()
            else:
                await api.positions()
            await api.positions()
            assert clock.sleeps == [20]

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [408, 500, 503])
def test_transient_status_retries_are_bounded(status):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(status)

    async def scenario():
        api, http, _ = reader(handler, max_attempts=2)
        async with http:
            with pytest.raises(BrokerError, match="retry_exhausted"):
                await api.positions()

    asyncio.run(scenario())
    assert count == 2


def test_transport_errors_are_safe_and_retry_then_succeed():
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        if count == 1:
            raise httpx.ConnectError("synthetic-secret in transport error", request=request)
        return httpx.Response(200, json=[])

    async def scenario():
        api, http, _ = reader(handler)
        async with http:
            assert await api.positions() == []

    asyncio.run(scenario())
    assert count == 2


def test_failed_later_page_does_not_return_a_partial_history():
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        if count == 1:
            return httpx.Response(
                200,
                json={
                    "items": [order(1)],
                    "nextPagePath": ROOT + "history/orders?cursor=2",
                },
            )
        return httpx.Response(503)

    async def scenario():
        api, http, _ = reader(handler, max_attempts=1)
        async with http:
            with pytest.raises(BrokerError, match="retry_exhausted"):
                await api.order_history()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode,code",
    [
        ("cycle", "pagination_cycle"),
        ("limit", "pagination_limit"),
        ("missing", "invalid_response"),
        ("timeout", "history_timeout"),
    ],
)
def test_bad_pagination_never_masquerades_as_complete(mode, code):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        if mode == "missing":
            return httpx.Response(200, json={"items": []})
        cursor = 1 if mode == "cycle" else count
        return httpx.Response(
            200,
            json={
                "items": [],
                "nextPagePath": ROOT + f"history/orders?cursor={cursor}",
            },
        )

    async def scenario():
        api, http, _ = reader(
            handler, max_pages=3, max_history_seconds=1 if mode == "timeout" else 100
        )
        async with http:
            with pytest.raises(BrokerError, match=code):
                await api.order_history()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "body",
    [
        b"not JSON",
        b'{"id":true,"currency":"GBP","totalValue":1}',
        b'{"id":1,"currency":"GBP","totalValue":NaN}',
        b'{"id":1,"currency":"GBP","totalValue":Infinity}',
        b'{"id":1,"currency":"GBP","totalValue":-Infinity}',
        b'{"id":1,"currency":"GBP","totalValue":10,"totalValue":999}',
        b'{"id":1,"currency":"GBP","totalValue":10,"cash":{"amount":1,"amount":999}}',
        b'{"id":1,"currency":"GBP","totalValue":"not-a-number"}',
    ],
)
def test_malformed_values_fail_without_echoing_inputs(body):
    async def scenario():
        api, http, _ = reader(lambda _: httpx.Response(200, content=body))
        async with http:
            with pytest.raises(BrokerError, match="^invalid_response$"):
                await api.account_summary()

    asyncio.run(scenario())


def test_unknown_fill_kind_preserved_and_missing_price_is_not_zero():
    payload = order(1, kind="FUTURE_CORPORATE_ACTION")
    del payload["fill"]["price"]

    async def scenario():
        api, http, _ = reader(
            lambda _: httpx.Response(
                200,
                json={
                    "items": [payload],
                    "nextPagePath": None,
                },
            )
        )
        async with http:
            observed = (await api.order_history())[0]
            assert observed.fill.fill_type == "FUTURE_CORPORATE_ACTION"
            assert observed.fill.price is None

    asyncio.run(scenario())


def test_redirects_rejected_even_when_injected_client_follows_them():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://evil.example/"})

    async def scenario():
        api, http, _ = reader(handler)
        async with http:
            with pytest.raises(BrokerError, match="redirect_rejected"):
                await api.positions()

    asyncio.run(scenario())
    assert len(requests) == 1


def test_explicit_live_origin_and_invalid_environment():
    async def scenario():
        api, http, _ = reader(lambda request: httpx.Response(200, json=[]), environment="live")
        async with http:
            assert api.base_url == "https://live.trading212.com"
            assert await api.positions() == []
        with pytest.raises(BrokerError, match="invalid_environment"):
            Trading212Client(api_key="x", api_secret="y", environment="other")

    asyncio.run(scenario())
