"""Foundation HTTP surface. Financial routes are introduced with authentication."""

from fastapi import FastAPI, Request

from meridian.security.http import SessionHttp


def create_app(*, session_http: SessionHttp | None = None) -> FastAPI:
    app = FastAPI(
        title="Great Dyke Meridian",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )
    if session_http is not None:
        app.include_router(session_http.router())

    @app.middleware("http")
    async def private_session_responses(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/session"):
            # Includes framework-generated 404/405 responses, with no CORS grant.
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        # Liveness only: no financial data, secrets or database paths.
        return {"status": "ok"}

    return app
