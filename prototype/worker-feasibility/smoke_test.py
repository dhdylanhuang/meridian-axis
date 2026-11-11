"""Checks an already-running loopback prototype; no external requests or secrets."""

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ORIGIN = "http://127.0.0.1:8791"


def get(path):
    with urlopen(ORIGIN + path, timeout=20) as response:
        assert response.status == 200
        return json.load(response)


def main():
    assert get("/health") == {"status": "ok", "scope": "synthetic-local-only"}
    result = get("/probe")
    assert result["scope"] == "synthetic-local-only"
    assert result["decimal_quantity"] == "0.125000000000000000000001"
    assert result["decimal_product"] == "1.55000000000000000000001240"
    assert result["canonical_product"] == "1.5500000000000000000000124"
    assert result["pydantic_json"] == {
        "quantity": "0.125000000000000000000001",
        "price": "12.40",
    }
    assert result["sqlalchemy_dialect"] == "postgresql"
    assert "SELECT" in result["sql_compiled"]
    assert result["pg8000_imported"] is True
    assert result["mock_http"] == {"synthetic": True}
    assert result["database_connected"] is False
    assert result["hosted_cpu_measured"] is False
    try:
        with urlopen(Request(ORIGIN + "/probe", method="POST"), timeout=20):
            raise AssertionError("Unexpected mutation route")
    except HTTPError as error:
        assert error.code == 405
    print(
        "Synthetic local worker checks passed; hosted CPU and database remain untested."
    )


if __name__ == "__main__":
    main()
