import assert from "node:assert/strict";
import test from "node:test";
import gateway from "../src/probe_gateway.mjs";

function binding() {
  const requests = [];
  const names = [];
  const response = new Response('{"synthetic":true}', {
    headers: { "content-type": "application/json" },
  });
  const id = {};
  const env = {
    PROBE: {
      idFromName(name) {
        names.push(name);
        return id;
      },
      get(actual) {
        assert.equal(actual, id);
        return {
          async fetch(request) {
            requests.push(request);
            return response;
          },
        };
      },
    },
  };
  return { env, requests, names, response };
}

test("allowed routes reach one fixed object without forwarding caller headers", async () => {
  for (const path of ["/health", "/probe"]) {
    const state = binding();
    const result = await gateway.fetch(
      new Request(`https://gateway.example${path}`, {
        headers: { authorization: "synthetic-secret", cookie: "session=synthetic" },
      }),
      state.env,
    );
    assert.equal(result, state.response);
    assert.deepEqual(state.names, ["synthetic-probe"]);
    assert.equal(state.requests.length, 1);
    const forwarded = state.requests[0];
    assert.equal(forwarded.url, `https://synthetic.invalid${path}`);
    assert.equal(forwarded.method, "GET");
    assert.equal(forwarded.body, null);
    assert.deepEqual([...forwarded.headers], []);
  }
});

test("unknown paths never reach the binding", async () => {
  for (const path of ["/", "/unknown", "/probe/", "/probe/extra"]) {
    assert.equal(
      (await gateway.fetch(new Request(`https://gateway.example${path}`), {})).status,
      404,
    );
  }
});

test("methods including requests with bodies are rejected before binding access", async () => {
  for (const path of ["/health", "/probe"]) {
    for (const method of ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]) {
      const request = new Request(`https://gateway.example${path}`, {
        method,
        ...(method === "POST" ? { body: "synthetic-private-input" } : {}),
      });
      const result = await gateway.fetch(request, {});
      assert.equal(result.status, 405);
      assert.equal(result.headers.get("allow"), "GET");
      assert.equal(request.bodyUsed, false);
    }
  }
});

test("query and fragment inputs never reach the binding", async () => {
  for (const suffix of ["?input=synthetic", "#synthetic"]) {
    const result = await gateway.fetch(
      new Request(`https://gateway.example/probe${suffix}`),
      {},
    );
    assert.equal(result.status, 400);
    assert.equal(await result.text(), "Unexpected input");
  }
});
