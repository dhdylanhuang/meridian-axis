"""Read-only Trading 212 v0 observations from the verified 2026-11-11 contract.

Raw provider facts are retained, not interpreted as a cash ledger. In particular,
wallet signs, cash additivity and fee/FX semantics still need real reconciliation.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, TypeVar
from urllib.parse import parse_qsl, urlsplit

import httpx
from pydantic import SecretStr

Raw = dict[str, Any]
T = TypeVar("T")
PREFIX = "/api/v0/equity/"
INTERVALS = {
    PREFIX + "account/summary": 5.0,
    PREFIX + "positions": 1.0,
    PREFIX + "history/orders": 3.0,
    PREFIX + "history/dividends": 3.0,
    PREFIX + "history/transactions": 3.0,
    PREFIX + "metadata/instruments": 50.0,
    PREFIX + "metadata/exchanges": 30.0,
}


class BrokerError(Exception):
    """Safe public error category. Never includes a URL, body or transport error."""

    def __init__(self, code: str, status: int | None = None):
        self.code = code
        self.status = status
        super().__init__(code if status is None else f"{code} (HTTP {status})")


@dataclass(frozen=True)
class Instrument:
    ticker: str
    currency: str
    isin: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class AccountSummary:
    account_id: str
    currency: str
    total_value: Decimal
    raw_payload: Raw = field(repr=False)


@dataclass(frozen=True)
class Position:
    instrument: Instrument
    quantity: Decimal
    current_price: Decimal | None
    average_price_paid: Decimal | None
    opened_at: datetime | None
    raw_payload: Raw = field(repr=False)


@dataclass(frozen=True)
class Fill:
    fill_id: str
    filled_at: datetime
    quantity: Decimal
    price: Decimal | None
    fill_type: str


@dataclass(frozen=True)
class HistoricalOrder:
    order_id: str
    instrument: Instrument
    side: str
    status: str
    fill: Fill | None
    raw_payload: Raw = field(repr=False)


@dataclass(frozen=True)
class Dividend:
    reference: str
    paid_on: datetime
    amount: Decimal
    currency: str
    instrument: Instrument | None
    dividend_type: str
    raw_payload: Raw = field(repr=False)


@dataclass(frozen=True)
class CashTransaction:
    reference: str
    occurred_at: datetime
    amount: Decimal
    currency: str
    transaction_type: str
    raw_payload: Raw = field(repr=False)


@dataclass(frozen=True)
class InstrumentMetadata:
    instrument: Instrument
    working_schedule_id: str | None
    instrument_type: str
    raw_payload: Raw = field(repr=False)


@dataclass(frozen=True)
class TimeEvent:
    at: datetime
    event_type: str


@dataclass(frozen=True)
class WorkingSchedule:
    schedule_id: str
    time_events: tuple[TimeEvent, ...]


@dataclass(frozen=True)
class Exchange:
    exchange_id: str
    name: str
    working_schedules: tuple[WorkingSchedule, ...]
    raw_payload: Raw = field(repr=False)


def _json_object(pairs: list[tuple[str, Any]]) -> Raw:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_json_constant(_: str) -> None:
    raise ValueError


def _object(value: Any) -> Raw:
    if not isinstance(value, dict):
        raise BrokerError("invalid_response")
    return value


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BrokerError("invalid_response")
    return value


def _identifier(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise BrokerError("invalid_response")
    return _text(str(value))


def _currency(value: Any) -> str:
    value = _text(value)
    if re.fullmatch(r"[A-Z]{3}", value) is None:
        raise BrokerError("invalid_response")
    return value


def _optional_text(value: Any) -> str | None:
    return None if value is None else _text(value)


def _decimal(value: Any) -> Decimal:
    # JSON is decoded directly to Decimal, never through a binary float.
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise BrokerError("invalid_response")
    result = Decimal(value)
    if not result.is_finite():
        raise BrokerError("invalid_response")
    return result


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else _decimal(value)


def _datetime(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        raise BrokerError("invalid_response") from None


def _instrument(raw: Any, *, metadata: bool = False) -> Instrument:
    raw = _object(raw)
    return Instrument(
        ticker=_text(raw.get("ticker")),
        currency=_currency(raw.get("currencyCode" if metadata else "currency")),
        isin=_optional_text(raw.get("isin")),
        name=_optional_text(raw.get("name")),
    )


def _account(raw: Raw) -> AccountSummary:
    return AccountSummary(
        _identifier(raw.get("id")),
        _currency(raw.get("currency")),
        _decimal(raw.get("totalValue")),
        raw,
    )


def _position(raw: Raw) -> Position:
    opened = raw.get("createdAt")
    return Position(
        _instrument(raw.get("instrument")),
        _decimal(raw.get("quantity")),
        _optional_decimal(raw.get("currentPrice")),
        _optional_decimal(raw.get("averagePricePaid")),
        _datetime(opened) if opened is not None else None,
        raw,
    )


def _order(raw: Raw) -> HistoricalOrder:
    order = _object(raw.get("order"))
    fill_raw = raw.get("fill")
    fill = None
    if fill_raw is not None:
        fill_raw = _object(fill_raw)
        kind = _text(fill_raw.get("type"))
        price = _optional_decimal(fill_raw.get("price"))
        if kind == "TRADE" and price is None:
            raise BrokerError("invalid_response")
        fill = Fill(
            _identifier(fill_raw.get("id")),
            _datetime(fill_raw.get("filledAt")),
            _decimal(fill_raw.get("quantity")),
            price,
            kind,
        )
    return HistoricalOrder(
        _identifier(order.get("id")),
        _instrument(order.get("instrument")),
        _text(order.get("side")),
        _text(order.get("status")),
        fill,
        raw,
    )


def _dividend(raw: Raw) -> Dividend:
    instrument = raw.get("instrument")
    return Dividend(
        _identifier(raw.get("reference")),
        _datetime(raw.get("paidOn")),
        _decimal(raw.get("amount")),
        _currency(raw.get("currency")),
        _instrument(instrument) if instrument is not None else None,
        _text(raw.get("type")),
        raw,
    )


def _transaction(raw: Raw) -> CashTransaction:
    return CashTransaction(
        _identifier(raw.get("reference")),
        _datetime(raw.get("dateTime")),
        _decimal(raw.get("amount")),
        _currency(raw.get("currency")),
        _text(raw.get("type")),
        raw,
    )


def _metadata(raw: Raw) -> InstrumentMetadata:
    schedule = raw.get("workingScheduleId")
    return InstrumentMetadata(
        _instrument(raw, metadata=True),
        _identifier(schedule) if schedule is not None else None,
        _text(raw.get("type")),
        raw,
    )


def _exchange(raw: Raw) -> Exchange:
    schedules = raw.get("workingSchedules")
    if not isinstance(schedules, list):
        raise BrokerError("invalid_response")
    result = []
    for schedule in schedules:
        schedule = _object(schedule)
        events = schedule.get("timeEvents")
        if not isinstance(events, list):
            raise BrokerError("invalid_response")
        result.append(
            WorkingSchedule(
                _identifier(schedule.get("id")),
                tuple(
                    TimeEvent(_datetime(_object(e).get("date")), _text(e.get("type")))
                    for e in events
                ),
            )
        )
    return Exchange(_identifier(raw.get("id")), _text(raw.get("name")), tuple(result), raw)


class Trading212Client:
    """One account/environment reader with shared endpoint pacing.

    Use one instance per account to share budgets among manual/scheduled callers.
    An injected AsyncClient remains owned by its caller; redirects are disabled
    per request even when that client's default enables them.
    """

    def __init__(
        self,
        *,
        api_key: SecretStr | str,
        api_secret: SecretStr | str,
        environment: Literal["demo", "live"] = "demo",
        client: httpx.AsyncClient | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_value: Callable[[], float] = random.random,
        max_attempts: int = 4,
        max_pages: int = 1000,
        max_history_seconds: float = 1800,
        backoff_seconds: float = 1,
    ):
        if environment not in ("demo", "live"):
            raise BrokerError("invalid_environment")
        if not 1 <= max_attempts <= 10 or not 1 <= max_pages <= 10000:
            raise BrokerError("invalid_client_configuration")
        if not all(math.isfinite(n) and n > 0 for n in (max_history_seconds, backoff_seconds)):
            raise BrokerError("invalid_client_configuration")
        key = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        secret = api_secret.get_secret_value() if isinstance(api_secret, SecretStr) else api_secret
        if (
            not isinstance(key, str)
            or not isinstance(secret, str)
            or not key.strip()
            or not secret.strip()
        ):
            raise BrokerError("missing_credentials")
        if ":" in key or any(c in key + secret for c in "\r\n"):
            raise BrokerError("invalid_credentials")
        self.environment = environment
        self.base_url = f"https://{environment}.trading212.com"
        self._auth = httpx.BasicAuth(key, secret)
        self._client = client or httpx.AsyncClient(trust_env=False, timeout=30)
        self._owns_client = client is None
        self._monotonic, self._wall_clock = monotonic, wall_clock
        self._sleep, self._random = sleep, random_value
        self._max_attempts, self._max_pages = max_attempts, max_pages
        self._max_history_seconds, self._backoff = max_history_seconds, backoff_seconds
        self._next_request: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def __aenter__(self) -> Trading212Client:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _url(self, value: str, route: str) -> str:
        if (
            not isinstance(value, str)
            or not value.isascii()
            or len(value) > 4096
            or any(c.isspace() for c in value)
        ):
            raise BrokerError("invalid_continuation")
        try:
            parts = urlsplit(value)
            if parts.username or parts.password or parts.fragment:
                raise ValueError
            if parts.scheme or parts.netloc:
                if (
                    parts.scheme != "https"
                    or parts.hostname != f"{self.environment}.trading212.com"
                    or parts.port not in (None, 443)
                ):
                    raise ValueError
            elif not value.startswith("/") or value.startswith("//"):
                raise ValueError
            if route not in INTERVALS or parts.path != route:
                raise ValueError
            allowed = {"cursor", "limit"}
            if route.endswith("transactions"):
                allowed.add("time")
            elif route.endswith(("orders", "dividends", "positions")):
                allowed.add("ticker")
            if any(key not in allowed for key, _ in parse_qsl(parts.query, keep_blank_values=True)):
                raise ValueError
        except ValueError:
            raise BrokerError("invalid_continuation") from None
        # Construct from validated origin and exact path/query, never untrusted userinfo.
        return self.base_url + parts.path + ("?" + parts.query if parts.query else "")

    async def _wait(self, route: str, deadline: float | None = None) -> None:
        delay = self._next_request.get(route, 0) - self._monotonic()
        if deadline is not None and self._monotonic() + max(0, delay) >= deadline:
            raise BrokerError("history_timeout")
        if delay > 0:
            await self._sleep(delay)

    def _reset_delay(self, headers: Mapping[str, str]) -> float:
        try:
            reset = float(headers.get("x-ratelimit-reset", "0"))
        except (ValueError, TypeError):
            return 0
        return max(0, reset - self._wall_clock()) if math.isfinite(reset) else 0

    async def _request(self, path: str, route: str, deadline: float | None = None) -> Any:
        url = self._url(path, route)
        lock = self._locks.setdefault(route, asyncio.Lock())
        async with lock:
            for attempt in range(self._max_attempts):
                await self._wait(route, deadline)
                self._next_request[route] = self._monotonic() + INTERVALS[route]
                response = None
                try:
                    timeout = 30 if deadline is None else min(30, deadline - self._monotonic())
                    if timeout <= 0:
                        raise BrokerError("history_timeout")
                    response = await self._client.get(
                        url, auth=self._auth, follow_redirects=False, timeout=timeout
                    )
                except httpx.TransportError:
                    if attempt + 1 == self._max_attempts:
                        raise BrokerError("transport_failure") from None
                if response is not None:
                    status = response.status_code
                    reset_delay = self._reset_delay(response.headers)
                    if status == 429 or response.headers.get("x-ratelimit-remaining") == "0":
                        self._next_request[route] = max(
                            self._next_request[route], self._monotonic() + reset_delay
                        )
                    if status == 200:
                        try:
                            return json.loads(
                                response.content,
                                parse_float=Decimal,
                                parse_constant=_invalid_json_constant,
                                object_pairs_hook=_json_object,
                            )
                        except (ValueError, UnicodeError, RecursionError):
                            raise BrokerError("invalid_response") from None
                    if 300 <= status < 400:
                        raise BrokerError("redirect_rejected", status)
                    if status not in (408, 429) and not 500 <= status <= 599:
                        raise BrokerError("http_failure", status)
                    if attempt + 1 == self._max_attempts:
                        raise BrokerError("retry_exhausted", status)
                else:
                    reset_delay = 0
                exponential = min(900.0, self._backoff * (2**attempt))
                delay = exponential * (0.5 + 0.5 * self._random())
                self._next_request[route] = max(
                    self._next_request[route],
                    self._monotonic() + max(delay, reset_delay),
                )
        raise AssertionError("unreachable")

    async def _array(self, route: str, parse: Callable[[Raw], T]) -> list[T]:
        raw = await self._request(route, route)
        if not isinstance(raw, list):
            raise BrokerError("invalid_response")
        return [parse(_object(item)) for item in raw]

    async def _history(self, family: str, parse: Callable[[Raw], T]) -> list[T]:
        route = PREFIX + "history/" + family
        path = route + "?limit=50"
        seen: set[str] = set()
        results = []
        started = self._monotonic()
        for _ in range(self._max_pages):
            normalised = self._url(path, route)
            if normalised in seen:
                raise BrokerError("pagination_cycle")
            if self._monotonic() - started >= self._max_history_seconds:
                raise BrokerError("history_timeout")
            seen.add(normalised)
            page = _object(
                await self._request(path, route, deadline=started + self._max_history_seconds)
            )
            if self._monotonic() - started >= self._max_history_seconds:
                raise BrokerError("history_timeout")
            if not isinstance(page.get("items"), list) or "nextPagePath" not in page:
                raise BrokerError("invalid_response")
            results.extend(parse(_object(item)) for item in page["items"])
            path = page["nextPagePath"]
            if path is None:
                return results
            if not isinstance(path, str):
                raise BrokerError("invalid_response")
        raise BrokerError("pagination_limit")

    async def account_summary(self) -> AccountSummary:
        route = PREFIX + "account/summary"
        return _account(_object(await self._request(route, route)))

    async def positions(self) -> list[Position]:
        return await self._array(PREFIX + "positions", _position)

    async def order_history(self) -> list[HistoricalOrder]:
        return await self._history("orders", _order)

    async def dividend_history(self) -> list[Dividend]:
        return await self._history("dividends", _dividend)

    async def transaction_history(self) -> list[CashTransaction]:
        return await self._history("transactions", _transaction)

    async def instruments(self) -> list[InstrumentMetadata]:
        return await self._array(PREFIX + "metadata/instruments", _metadata)

    async def exchanges(self) -> list[Exchange]:
        return await self._array(PREFIX + "metadata/exchanges", _exchange)
