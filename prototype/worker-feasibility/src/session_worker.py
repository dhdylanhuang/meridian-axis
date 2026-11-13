"""Private session runtime. Only the public gateway can reach this namespace."""

import asyncio
from contextlib import suppress

from workers import DurableObject, Response, WorkerEntrypoint

_REQUEST_LOCK = asyncio.Lock()


async def buffered_fetch(app, request, env, ctx):
    # Every current route is finite JSON and the privacy middleware is a direct
    # ASGI wrapper, so the pinned SDK joins its HTTP task and lifespan shutdown
    # before returning. No BaseHTTPMiddleware/streaming/background task is used.
    from workers import asgi

    task = asyncio.create_task(asgi.fetch(app, request, env, ctx))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # SDK process_request owns an internal HTTP task. Do not cancel its
        # caller before that task is joined: keep resources/lock until the
        # component-bounded finite exchange finishes, then propagate cancellation.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:  # noqa: BLE001 — preserve original cancellation
                break
        with suppress(Exception):
            task.result()
        raise


class SessionApplicationDO(DurableObject):
    async def fetch(self, request):
        # The established synchronous database driver must not overlap requests
        # on the object's event loop. No transaction spans provider HTTP calls.
        async with _REQUEST_LOCK:
            stage = "application_import"
            try:
                # Heavy ORM/FastAPI imports exceeded the provider's startup
                # snapshot memory bound. Initialise only in the object request;
                # this must still pass actual request resource qualification.
                from meridian.security.hosted import hosted_application
                from pydantic import SecretStr

                stage = "application_configuration"

                async def refresh():
                    from js import Object, Request
                    import json

                    options = Object.new()
                    options.method = "POST"
                    response = await self.env.SYNC.fetch(
                        Request.new("https://sync.internal/refresh", options)
                    )
                    if response.status != 200:
                        return {"status": "unavailable"}
                    result = json.loads(await response.text())
                    if result.get("status") not in {"succeeded", "deferred", "failed"}:
                        return {"status": "unavailable"}
                    return {"status": result["status"]}

                async with hosted_application(
                    self.env.HYPERDRIVE,
                    origin=self.env.PUBLIC_ORIGIN,
                    project_ref=self.env.SUPABASE_PROJECT_REF,
                    publishable_key=SecretStr(self.env.SUPABASE_PUBLISHABLE_KEY),
                    login_csrf_key=SecretStr(self.env.LOGIN_CSRF_KEY),
                    refresh=refresh,
                ) as app:
                    stage = "request_adapter"
                    return await buffered_fetch(app, request, self.env, self.ctx)
            except Exception as error:  # noqa: BLE001 — fixed external categories
                # Never expose binding values, provider errors or driver SQL.
                # Only public, fixed categories; never exception messages,
                # module names, SQL, values, traceback or request inputs.
                category = type(error).__name__
                if category not in {
                    "ModuleNotFoundError",
                    "ImportError",
                    "ValueError",
                    "RuntimeError",
                    "AttributeError",
                    "MemoryError",
                    "TypeError",
                }:
                    category = "Unavailable"
                code = error.args[0] if error.args else None
                if not isinstance(code, str) or code not in {
                    "binding_user_invalid",
                    "binding_database_invalid",
                    "binding_password_invalid",
                    "binding_host_invalid",
                    "binding_port_invalid",
                    "binding_secret_type_invalid",
                    "session_http_configuration_invalid",
                }:
                    code = "configuration_unavailable"
                return Response.json(
                    {
                        "error": "session_unavailable",
                        "code": code,
                        "component": stage,
                        "category": category,
                    },
                    status=503,
                    headers={"Cache-Control": "no-store"},
                )


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response("Not found", status=404)
