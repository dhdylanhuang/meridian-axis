"""Private session runtime. Only the public gateway can reach this namespace."""

import asyncio

from workers import DurableObject, Response, WorkerEntrypoint

_REQUEST_LOCK = asyncio.Lock()


async def buffered_fetch(app, request, env, ctx):
    # Finite JSON-only ASGI exchange. Unlike SDK streaming fetch(), this awaits
    # the entire application call (including middleware cleanup) under the lock.
    # ASGI scope construction remains the installed SDK's implementation.
    from workers import asgi

    scope = asgi.request_to_scope(request, env)
    payload, body, headers = bytearray(), bytearray(), []
    status = None
    received = False
    finished = asyncio.Event()

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": bytes(payload), "more_body": False}
        await finished.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal status, headers
        if message["type"] == "http.response.start":
            if status is not None:
                raise ValueError("response_invalid")
            status = message["status"]
            headers = [
                (key.decode("latin-1"), value.decode("latin-1"))
                for key, value in message.get("headers", [])
            ]
        elif message["type"] == "http.response.body":
            chunk = message.get("body", b"")
            if status is None or len(body) + len(chunk) > 65536:
                raise ValueError("response_invalid")
            body.extend(chunk)
            if not message.get("more_body", False):
                finished.set()
        else:
            raise ValueError("response_invalid")

    async with asyncio.timeout(25):
        if request.body is not None:
            async for chunk in request.body:
                value = chunk.to_bytes()
                if len(payload) + len(value) > 8192:
                    raise ValueError("request_invalid")
                payload.extend(value)
        # No detached HTTP task or streaming writer survives this call. FastAPI
        # owns any middleware child tasks through its structured task groups.
        async with app.router.lifespan_context(app):
            await app(scope, receive, send)
        if status is None or not finished.is_set():
            raise ValueError("response_incomplete")
        return Response(bytes(body), status=status, headers=headers)


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
                async with hosted_application(
                    self.env.HYPERDRIVE,
                    origin=self.env.PUBLIC_ORIGIN,
                    project_ref=self.env.SUPABASE_PROJECT_REF,
                    publishable_key=SecretStr(self.env.SUPABASE_PUBLISHABLE_KEY),
                    login_csrf_key=SecretStr(self.env.LOGIN_CSRF_KEY),
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
