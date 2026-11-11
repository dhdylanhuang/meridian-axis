"""Validate the synthetic probe locally or at its explicit public workers.dev origin."""

import argparse
import json
import math
import re
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ORIGIN = "http://127.0.0.1:8791"
MAX_RESPONSE_BYTES = 65536
USER_AGENT = "MeridianAxis-SyntheticProbe/1.0"


class ProbeFailure(Exception):
    """A safe diagnostic without response bodies or potentially private URLs."""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProbeFailure("Probe redirected; use its direct origin.")


def validate_origin(value):
    try:
        parsed = urlsplit(value)
        hosted = (
            parsed.scheme == "https"
            and re.fullmatch(
                r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\."
                r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.workers\.dev",
                parsed.hostname or "",
            )
            and parsed.port is None
        )
        local = (
            parsed.scheme == "http"
            and parsed.hostname == "127.0.0.1"
            and parsed.port is not None
            and 1 <= parsed.port <= 65535
        )
        if (
            not (hosted or local)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or "?" in value
            or "#" in value
            or any(character.isspace() for character in value)
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError(
            "Use an HTTP 127.0.0.1 origin with a port, or an HTTPS workers.dev "
            "origin, without credentials, path, query or fragment."
        ) from None
    return value.rstrip("/")


def validate_timeout(value):
    try:
        timeout = float(value)
        if not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError(
            "Timeout must be greater than 0 and at most 60 seconds."
        ) from None
    return timeout


def require(condition, message):
    if not condition:
        raise ProbeFailure(message)


def get(opener, origin, path, timeout):
    request = Request(origin + path, headers={"User-Agent": USER_AGENT})
    with opener.open(request, timeout=timeout) as response:
        require(response.status == 200, "Expected HTTP 200.")
        body = response.read(MAX_RESPONSE_BYTES + 1)
        require(len(body) <= MAX_RESPONSE_BYTES, "Probe response is too large.")
        try:
            return json.loads(body)
        except (ValueError, UnicodeError):
            raise ProbeFailure("Probe returned invalid JSON.") from None


def check_probe(origin=ORIGIN, timeout=20):
    # Ignore environment proxy settings: no proxy credentials or implicit routes.
    opener = build_opener(ProxyHandler({}), NoRedirects())
    health = get(opener, origin, "/health", timeout)
    require(
        health == {"status": "ok", "scope": "synthetic-local-only"}, "Unexpected health response."
    )
    result = get(opener, origin, "/probe", timeout)
    expected = {
        "scope": "synthetic-local-only",
        "decimal_quantity": "0.125000000000000000000001",
        "decimal_product": "1.55000000000000000000001240",
        "canonical_product": "1.5500000000000000000000124",
        "pydantic_json": {"quantity": "0.125000000000000000000001", "price": "12.40"},
        "sqlalchemy_dialect": "postgresql",
        "pg8000_imported": True,
        "mock_http": {"synthetic": True},
        "database_connected": False,
        "hosted_cpu_measured": False,
    }
    require(isinstance(result, dict), "Expected a probe JSON object.")
    for key, value in expected.items():
        actual = result.get(key)
        require(
            type(actual) is type(value) and actual == value, f"Unexpected synthetic field: {key}."
        )
    require(result["mock_http"].get("synthetic") is True, "Unexpected mock HTTP diagnostic.")
    require(
        isinstance(result.get("sql_compiled"), str) and "SELECT" in result["sql_compiled"],
        "Missing compiled SQL diagnostic.",
    )
    try:
        request = Request(origin + "/probe", method="POST", headers={"User-Agent": USER_AGENT})
        with opener.open(request, timeout=timeout):
            raise ProbeFailure("Unexpected mutation route.")
    except HTTPError as error:
        try:
            require(error.code == 405, "Expected HTTP 405 for POST.")
        finally:
            error.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", type=validate_origin, default=ORIGIN)
    parser.add_argument("--timeout", type=validate_timeout, default=20)
    args = parser.parse_args(argv)
    try:
        check_probe(args.origin, args.timeout)
    except ProbeFailure as error:
        parser.exit(1, f"Probe check failed: {error}\n")
    except (OSError, HTTPException, ValueError):
        # URL/HTTP exceptions can include credentials, redirects or response data.
        parser.exit(1, "Probe check failed: request or response could not be validated.\n")
    print(
        "Synthetic response checks passed; this script measures no hosted CPU or database behavior."
    )


if __name__ == "__main__":
    main()
