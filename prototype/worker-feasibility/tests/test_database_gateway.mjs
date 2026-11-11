import assert from "node:assert/strict";
import test from "node:test";
import gateway from "../src/database_gateway.mjs";

const TOKEN = "invented-diagnostic-test-secret";

function request(path = "/probe", options = {}) {
  return new Request(`https://diagnostic.example${path}`, {
    ...options,
    headers: { authorization: `Bearer ${TOKEN}`, ...options.headers },
  });
}

function binding() {
  const calls = [];
  const env = {
    PROBE_AUTH_TOKEN: TOKEN,
    PROBE: {
      idFromName(name) {
        calls.push(name);
        return "synthetic-id";
      },
      get(id) {
        assert.equal(id, "synthetic-id");
        return { async fetch(forwarded) {
          calls.push(forwarded);
          return Response.json({ status: "ok", synthetic: true });
        } };
      },
    },
  };
  return { env, calls };
}

test("missing, incorrect, oversized and malformed authorization never reach binding", async () => {
  for (const header of [null, "Bearer wrong", "Basic wrong", "x".repeat(257)]) {
    const state = binding();
    const headers = header === null ? {} : { authorization: header };
    const result = await gateway.fetch(new Request("https://diagnostic.example/probe", { headers }), state.env);
    assert.equal(result.status, 401);
    assert.equal(result.headers.get("www-authenticate"), "Bearer");
    assert.equal(await result.text(), "Unauthorized");
    assert.deepEqual(state.calls, []);
  }
});

test("missing or invalid configured secret fails closed", async () => {
  for (const secret of [undefined, null, "", 12, "x".repeat(241)]) {
    const state = binding();
    state.env.PROBE_AUTH_TOKEN = secret;
    assert.equal((await gateway.fetch(request(), state.env)).status, 401);
    assert.deepEqual(state.calls, []);
  }
});

test("authorized fixed route strips caller credentials, cookies, headers and body", async () => {
  const state = binding();
  const result = await gateway.fetch(request("/probe", { headers: { cookie: "invented-private-cookie", "x-private": "invented" } }), state.env);
  assert.equal(result.status, 200);
  assert.equal(result.headers.get("cache-control"), "no-store");
  assert.deepEqual(await result.json(), { status: "ok", synthetic: true });
  assert.equal(state.calls[0], "synthetic-database-probe");
  const forwarded = state.calls[1];
  assert.equal(forwarded.url, "https://synthetic.invalid/probe");
  assert.equal(forwarded.method, "GET");
  assert.equal(forwarded.body, null);
  assert.deepEqual([...forwarded.headers], []);
});

test("authenticated unknown routes and input are rejected without binding access", async () => {
  for (const [path, expected] of [["/", 404], ["/health", 404], ["/probe/", 404], ["/probe?input=invented", 400], ["/probe#invented", 400]]) {
    const state = binding();
    assert.equal((await gateway.fetch(request(path), state.env)).status, expected);
    assert.deepEqual(state.calls, []);
  }
});

test("authenticated mutation/body requests and HEAD are rejected without reading body", async () => {
  for (const method of ["POST", "PUT", "DELETE", "HEAD", "OPTIONS"]) {
    const state = binding();
    const incoming = request("/probe", { method, ...(method === "POST" ? { body: "invented-private-body" } : {}) });
    const result = await gateway.fetch(incoming, state.env);
    assert.equal(result.status, 405);
    assert.equal(result.headers.get("allow"), "GET");
    assert.equal(incoming.bodyUsed, false);
    assert.deepEqual(state.calls, []);
  }
});

test("binding failures return fixed safe diagnostics", async () => {
  const result = await gateway.fetch(request(), { PROBE_AUTH_TOKEN: TOKEN });
  assert.equal(result.status, 502);
  assert.equal(await result.text(), "Diagnostic unavailable");
});
