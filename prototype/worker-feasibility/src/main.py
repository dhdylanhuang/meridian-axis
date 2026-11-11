"""Synthetic compatibility probe. No portfolio, database connection or secrets.

This is not a deployed service or the application's production entrypoint.
"""

import sys
from decimal import Decimal, localcontext
from importlib.metadata import version

import httpx
import pg8000
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import URL, bindparam, create_engine, select
from workers import asgi

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
Default = asgi.entrypoint(app)


class SyntheticInput(BaseModel):
    quantity: Decimal
    price: Decimal


def canonical_decimal(value: Decimal) -> str:
    if value.is_zero():
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@app.get("/health")
async def health():
    return {"status": "ok", "scope": "synthetic-local-only"}


@app.get("/probe")
async def probe():
    sample = SyntheticInput.model_validate_json(
        '{"quantity":"0.125000000000000000000001","price":"12.40"}'
    )
    with localcontext() as context:
        context.prec = 60
        product = sample.quantity * sample.price

    # Initialises the synchronous pg8000 dialect and compiles SQL. It never
    # opens a socket or executes SQL. A DB round trip remains a separate gate.
    engine = create_engine(
        URL.create("postgresql+pg8000", host="synthetic.invalid", database="synthetic")
    )
    try:
        compiled = str(
            select(bindparam("synthetic_amount")).compile(dialect=engine.dialect)
        )
    finally:
        engine.dispose()

    # Exercises HTTPX against an in-process mock, not an external provider.
    def mock(_request):
        return httpx.Response(200, json={"synthetic": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock)) as client:
        mocked = (await client.get("https://synthetic.invalid/probe")).json()

    return {
        "scope": "synthetic-local-only",
        "python": sys.version.split()[0],
        "versions": {
            name: version(name)
            for name in ("fastapi", "pydantic", "httpx", "sqlalchemy", "pg8000")
        },
        "decimal_quantity": format(sample.quantity, "f"),
        "decimal_product": format(product, "f"),
        "canonical_product": canonical_decimal(product),
        "pydantic_json": sample.model_dump(mode="json"),
        "sqlalchemy_dialect": engine.dialect.name,
        "sql_compiled": compiled,
        "pg8000_imported": pg8000.__name__ == "pg8000",
        "mock_http": mocked,
        "database_connected": False,
        "hosted_cpu_measured": False,
    }
