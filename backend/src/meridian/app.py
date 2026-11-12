"""Foundation HTTP surface. Financial routes are introduced with authentication."""

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders

from meridian.security.http import SessionHttp


class PrivateSessionResponses:
    """Add privacy headers without turning finite JSON into an ASGI stream.

    BaseHTTPMiddleware creates a streamed response and a separate request task.
    This direct wrapper preserves completion before the hosted SDK returns.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/v1/session"):

            async def private_send(message):
                if message["type"] == "http.response.start":
                    headers = MutableHeaders(scope=message)
                    headers["Cache-Control"] = "no-store"
                    headers["Pragma"] = "no-cache"
                    headers["Referrer-Policy"] = "no-referrer"
                    headers["X-Content-Type-Options"] = "nosniff"
                await send(message)

            await self.app(scope, receive, private_send)
        else:
            await self.app(scope, receive, send)


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
    # Includes framework 404/405; no CORS grant or automatic slash redirects.
    app.add_middleware(PrivateSessionResponses)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        # Liveness only: no financial data, secrets or database paths.
        return {"status": "ok"}

    return app
