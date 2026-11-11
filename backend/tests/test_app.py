import asyncio

import httpx

from meridian.app import create_app


def test_health_exposes_no_private_configuration():
    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="https://test.invalid"
        ) as client:
            assert (await client.get("/health")).json() == {"status": "ok"}
            assert (await client.get("/docs")).status_code == 404
            assert (await client.get("/api/portfolio")).status_code == 404

    asyncio.run(check())
