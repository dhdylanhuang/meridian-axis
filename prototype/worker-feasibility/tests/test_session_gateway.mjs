import assert from "node:assert/strict";
import test from "node:test";
import gateway from "../src/session_gateway.mjs";

const ORIGIN = "https://sessions.example";
const CSRF = "n".repeat(43);

function setup() {
  const requests = [];
  return {
    requests,
    env: {
      PUBLIC_ORIGIN: ORIGIN,
      APP: {
        idFromName(name) { assert.equal(name, "meridian-session-application"); return "fixed-id"; },
        get(id) {
          assert.equal(id, "fixed-id");
          return { async fetch(request) {
            requests.push(request);
            const headers = new Headers({ "content-type": "application/json" });
            headers.append("Set-Cookie", "__Host-meridian_session=synthetic; Secure; HttpOnly; Path=/");
            headers.append("Set-Cookie", "__Host-meridian_csrf=synthetic; Secure; Path=/");
            return new Response('{"status":"synthetic"}', { status: 200, headers });
          } };
        },
      },
    },
  };
}

function request(path = "/api/v1/session/login", options = {}) {
  const method = options.method ?? "POST";
  return new Request(ORIGIN + path, {
    ...options, method,
    headers: { origin: ORIGIN, "x-csrf-token": CSRF, "content-type": "application/json", ...options.headers },
  });
}

function privateResponse(response) {
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(response.headers.get("referrer-policy"), "no-referrer");
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
}

test("all six routes reach the fixed application object with configured authority", async () => {
  for (const [path, method] of [
    ["/health", "GET"], ["/api/v1/session/bootstrap", "GET"],
    ["/api/v1/session/current", "GET"], ["/api/v1/session/login", "POST"],
    ["/api/v1/session/rotate", "POST"], ["/api/v1/session/logout", "POST"],
  ]) {
    const state = setup();
    const response = await gateway.fetch(request(path, { method }), state.env);
    assert.equal(response.status, 200);
    assert.equal(state.requests[0].url, ORIGIN + path);
    assert.equal(state.requests[0].headers.get("host"), "sessions.example");
    assert.equal(state.requests[0].redirect, "manual");
    privateResponse(response);
  }
});

test("only session headers and bounded login bytes are forwarded; cookies remain separate", async () => {
  const state = setup();
  const incoming = request(undefined, { body: '{"email":"invented@example.invalid","password":"invented"}', headers: {
    cookie: "__Host-meridian_login=synthetic; __Host-meridian_session=one; __Host-meridian_session=two",
    authorization: "Bearer synthetic-private", forwarded: "host=unsafe.invalid", "x-forwarded-host": "unsafe.invalid",
    "x-forwarded-for": "192.0.2.1", "cf-connecting-ip": "192.0.2.2",
  } });
  const response = await gateway.fetch(incoming, state.env);
  const upstream = state.requests[0];
  assert.equal(await upstream.text(), '{"email":"invented@example.invalid","password":"invented"}');
  assert.deepEqual([...upstream.headers.keys()].sort(), ["content-type", "cookie", "host", "origin", "x-csrf-token"]);
  assert.equal(upstream.headers.get("cookie"), incoming.headers.get("cookie"));
  assert.equal(response.headers.getSetCookie().length, 2);
  privateResponse(response);
});

test("missing or noncanonical public origin fails closed without binding access", async () => {
  for (const value of [undefined, "http://sessions.example", ORIGIN + "/", ORIGIN + "?", "https://u:p@sessions.example"]) {
    const response = await gateway.fetch(request(), { PUBLIC_ORIGIN: value });
    assert.equal(response.status, 503);
    privateResponse(response);
  }
});

test("authority, Origin, CSRF and merged header ambiguities are rejected", async () => {
  for (const [headers, expected] of [
    [{ host: "unsafe.invalid" }, 403], [{ host: "sessions.example, sessions.example" }, 403],
    [{ origin: "https://unsafe.invalid" }, 403], [{ origin: `${ORIGIN}, ${ORIGIN}` }, 403],
    [{ "x-csrf-token": `${CSRF}, ${CSRF}` }, 403],
    [{ "content-type": "application/json, application/json" }, 400],
  ]) {
    const state = setup();
    assert.equal((await gateway.fetch(request(undefined, { headers }), state.env)).status, expected);
    assert.equal(state.requests.length, 0);
  }
  const state = setup();
  assert.equal((await gateway.fetch(new Request("https://unsafe.invalid/health"), state.env)).status, 403);
  assert.equal((await gateway.fetch(new Request(ORIGIN + "/api/v1/session/logout", { method: "POST" }), state.env)).status, 403);
  assert.equal((await gateway.fetch(new Request(ORIGIN + "/health", { headers: { origin: "https://unsafe.invalid" } }), state.env)).status, 403);
});

test("route and method errors never reach the object or redirect", async () => {
  for (const [path, method, status, allow] of [
    ["/", "GET", 404], ["/api/v1/session/login/", "POST", 404],
    ["/health", "POST", 405, "GET"], ["/api/v1/session/login", "GET", 405, "POST"],
    ["/api/v1/session/current", "HEAD", 405, "GET"],
    ["/health?", "GET", 400], ["/health?input=synthetic", "GET", 400], ["/health#synthetic", "GET", 400],
  ]) {
    const state = setup();
    const response = await gateway.fetch(request(path, { method }), state.env);
    assert.equal(response.status, status);
    assert.equal(response.headers.get("allow"), allow ?? null);
    assert.equal(state.requests.length, 0);
    privateResponse(response);
  }
});

test("streamed login is bounded before forwarding and oversized reader is cancelled", async () => {
  let cancelled = false;
  const stream = new ReadableStream({
    start(controller) { controller.enqueue(new Uint8Array(8192)); controller.enqueue(new Uint8Array(1)); },
    cancel() { cancelled = true; },
  });
  const state = setup();
  const response = await gateway.fetch(request(undefined, { body: stream, duplex: "half" }), state.env);
  assert.equal(response.status, 413);
  assert.equal(cancelled, true);
  assert.equal(state.requests.length, 0);
  const exact = setup();
  assert.equal((await gateway.fetch(request(undefined, { body: new Uint8Array(8192) }), exact.env)).status, 200);
  assert.equal((await exact.requests[0].arrayBuffer()).byteLength, 8192);
});

test("non-login mutations reject bodies without forwarding them", async () => {
  for (const path of ["/api/v1/session/rotate", "/api/v1/session/logout"]) {
    const state = setup();
    const response = await gateway.fetch(request(path, { body: "private-invented-body" }), state.env);
    assert.equal(response.status, 400);
    assert.equal(state.requests.length, 0);
    assert.doesNotMatch(await response.text(), /private-invented/);
  }
});

test("slow input has a total ten-second read deadline and cancels the stream", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let cancelled = false;
  const stream = new ReadableStream({ cancel() { cancelled = true; } });
  const state = setup();
  const pending = gateway.fetch(request(undefined, { body: stream, duplex: "half" }), state.env);
  t.mock.timers.tick(10_000);
  const response = await pending;
  assert.equal(response.status, 408);
  assert.equal(cancelled, true);
  assert.equal(state.requests.length, 0);
});

test("upstream exceptions produce fixed safe noncacheable errors", async () => {
  const state = setup();
  state.env.APP.get = () => { throw new Error("private-database-secret"); };
  const response = await gateway.fetch(request(), state.env);
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), { error: "session_unavailable" });
  privateResponse(response);
});
