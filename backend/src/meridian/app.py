"""Foundation HTTP surface. Financial routes are introduced with authentication."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Great Dyke Meridian", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        # Liveness only: no financial data, secrets or database paths.
        return {"status": "ok"}

    return app
