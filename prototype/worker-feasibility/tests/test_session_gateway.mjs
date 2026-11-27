import fs from 'node:fs';
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

test("password setup has the same bounded, stripped transport as login", async () => {
  const state = setup();
  const response = await gateway.fetch(request('/api/v1/session/setup', {
    body: JSON.stringify({ token_hash: 'f'.repeat(64), type: 'signup', password: 'invented-password' }),
    headers: { authorization: 'invented-secret', 'x-forwarded-host': 'other.invalid' },
  }), state.env);
  assert.equal(response.status, 200);
  assert.equal(state.requests[0].headers.get('authorization'), null);
  assert.equal(state.requests[0].headers.get('x-forwarded-host'), null);
});

test("only fixed same-origin sign-in assets are served and carry CSP", async () => {
  const state = setup();
  let accessed = 0;
  state.env.ASSETS = { async fetch(req) {
    accessed++;
    assert.equal(new URL(req.url).origin, ORIGIN);
    assert.equal(req.headers.get('cookie'), null);
    return new Response('<html>synthetic</html>', { headers: { 'content-type': 'text/html' } });
  } };
  const response = await gateway.fetch(new Request(ORIGIN + '/', { headers: { cookie: 'invented-private' } }), state.env);
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-security-policy'), /frame-ancestors 'none'/);
  privateResponse(response);
  assert.equal((await gateway.fetch(new Request(ORIGIN + '/private.txt'), state.env)).status, 404);
  assert.equal((await gateway.fetch(new Request(ORIGIN + '/?token=secret'), state.env)).status, 400);
  const dates = await gateway.fetch(new Request(ORIGIN + '/dates.js'), state.env);
  assert.equal(dates.status, 200);
  privateResponse(dates);
  const detail = await gateway.fetch(new Request(ORIGIN + '/holding-detail.js'), state.env);
  assert.equal(detail.status, 200);
  privateResponse(detail);
  assert.equal(accessed, 3);
});

for (const route of ['snapshot', 'history']) test(`${route} GET uses fixed object; no authorization header or query-selected account`, async () => {
  const state=setup();
  const response=await gateway.fetch(request(`/api/v1/portfolio/${route}`,{method:'GET',headers:{authorization:'Bearer discarded'}}),state.env);
  assert.equal(response.status,200);assert.equal(state.requests.length,1);
  assert.equal(state.requests[0].headers.get('authorization'),null);privateResponse(response);
  const forbidden=setup();
  assert.equal((await gateway.fetch(request(`/api/v1/portfolio/${route}?account=foreign`,{method:'GET'}),forbidden.env)).status,400);
  assert.equal(forbidden.requests.length,0);
});
test('Cron dispatches through the fixed sync object with a clean bounded request',async()=>{
 const requests=[];
 const env={SYNC:{idFromName(name){assert.equal(name,'shared-isa');return 'sync-id';},get(id){assert.equal(id,'sync-id');return {async fetch(request){requests.push(request);return new Response('{}');}};}}};
 await gateway.scheduled({cron:'*/10 * * * *'},env,{});
 assert.equal(requests.length,1);assert.equal(requests[0].url,'https://sync.internal/scheduled');assert.equal(requests[0].method,'POST');assert.equal([...requests[0].headers].length,0);assert.equal(await requests[0].text(),'');
});
test('Cron failure exposes only a fixed category',async()=>{
 const env={SYNC:{idFromName(){return 'sync-id';},get(){return {async fetch(){return new Response('{}',{status:503});}};}}};
 await assert.rejects(gateway.scheduled({},env,{}),/broker_sync_unavailable/);
});

test('production template schedules only one refresh per ten-minute slot',()=>{
 const config=JSON.parse(fs.readFileSync(new URL('../wrangler.session-gateway.template.json',import.meta.url),'utf8'));
 assert.deepEqual(config.triggers.crons,['*/10 * * * *']);
});

test('Rust service methods have no public HTTP route',async()=>{
 const state=setup();
 for(const route of ['/reconcileCash','/api/v1/reconciliation','/qualify-rpc']){
  assert.equal((await gateway.fetch(request(route,{method:'GET'}),state.env)).status,404);
 }
 assert.equal(state.requests.length,0);
});

test('activity detail route preserves origin csrf and bounded JSON body',async()=>{
 const state=setup(),path='/api/v1/portfolio/cash-activity';
 const payload=JSON.stringify({snapshot_id:'snapshot',input_revision:'a'.repeat(64),category:'dividends',currency:'GBP',offset:0,limit:20});
 const response=await gateway.fetch(request(path,{body:payload}),state.env);privateResponse(response);
 assert.equal(response.status,200);assert.equal(state.requests.length,1);assert.equal(await state.requests[0].text(),payload);
 assert.equal(state.requests[0].headers.get('content-type'),'application/json');
 for(const options of [{body:'x'.repeat(2049)},{body:payload,headers:{origin:'https://foreign.invalid'}},{body:payload,headers:{'x-csrf-token':'invalid'}}]){
  const denied=await gateway.fetch(request(path,options),state.env);assert.ok([400,403,413].includes(denied.status));
 }
 assert.equal(state.requests.length,1);
});

test('risk forwards only a bounded date query to the established session object',async()=>{
  const state = setup();
  const path = '/api/v1/portfolio/risk';
  const query = '?start=2026-11-18&end=2026-11-20';
  const response = await gateway.fetch(request(path + query, {method:'GET'}),state.env);
  assert.equal(response.status,200);
  privateResponse(response);
  assert.equal(state.requests[0].url,ORIGIN + path + query);
  for (const bad of [path + query + '&account=other',path + '?start=2026-11-18',
    path + query + '&end=2026-11-21','/api/v1/portfolio/history' + query]) {
    assert.equal((await gateway.fetch(request(bad,{method:'GET'}),state.env)).status,400);
  }
  assert.equal(state.requests.length,1);
});

test('Portfolio Changes only returns calculated output from the authorized endpoint read',async()=>{
  const state = setup();
  const path = '/api/v1/portfolio/changes?start=2026-11-18&end=2026-11-20';
  const req = () => request(path,{method:'GET'});
  const result = await gateway.fetch(req(),state.env, raw => {
    assert.equal(JSON.parse(raw).status,'synthetic');
    return '{"method":"observed_portfolio_changes_v1"}';
  });
  privateResponse(result);
  assert.equal(result.status,200);
  assert.deepEqual(await result.json(),{method:'observed_portfolio_changes_v1'});
  assert.equal(state.requests[0].url,ORIGIN+path);
  assert.equal((await gateway.fetch(req(),state.env)).status,503);
  assert.equal((await gateway.fetch(request(path+'&account=other',{method:'GET'}),state.env)).status,400);
});

test("projections use the authenticated saved snapshot and reject a changed capture", async () => {
  const state = setup();
  const snapshot = {
    account_retrieval: { retrieval_completed_at: "2029-04-30T10:00:00Z" },
    positions_retrieval: { retrieval_completed_at: "2029-04-30T10:00:01Z" },
    total_value: "1000",
  };
  let reads = 0;
  state.env.APP.get = () => ({ async fetch(upstream) {
    assert.equal(new URL(upstream.url).pathname, "/api/v1/portfolio/snapshot");
    assert.equal(upstream.method, "GET");
    assert.match(upstream.headers.get("cookie"), /meridian_session=synthetic/);
    assert.equal(await upstream.text(), "");
    reads++;
    return Response.json(snapshot);
  } });
  const send = (capture, csrf = CSRF) => request("/api/v1/portfolio/projections", {
    headers: { cookie: "__Host-meridian_session=synthetic; __Host-meridian_csrf=" + csrf },
    body: JSON.stringify({capture_time: capture, positions_time: "2029-04-30T10:00:01Z",
      assumptions: {}, snapshot: {total_value: "9999"}}),
  });
  const calculators = { projections(input) {
    assert.deepEqual(JSON.parse(input), {snapshot, assumptions: {}});
    return '{"method":"dated_isa_projection_v1"}';
  } };
  const forward = req => gateway.fetch(req, state.env, undefined, calculators);
  const response = await forward(send("2029-04-30T10:00:00Z"));
  assert.equal(response.status, 200);
  privateResponse(response);
  assert.equal((await response.json()).method, "dated_isa_projection_v1");
  assert.equal((await forward(send("2029-04-30T09:00:00Z"))).status, 409);
  assert.equal((await forward(send("2029-04-30T10:00:00Z", "x".repeat(43)))).status, 403);
  assert.equal(reads, 2);
  calculators.projections = () => { throw "allocation_total_invalid"; };
  assert.equal((await forward(send("2029-04-30T10:00:00Z"))).status, 422);
});

test("snapshot sector rollup uses only saved exposures on the authenticated path", async () => {
  const state = setup();
  const original = { total_value: "100.000000000000001", exposures: {
    method: "broker_exposures_v1", portfolio_denominator: "100", invested_denominator: "90",
    sectors: { buckets: [{label:"ICB · Technology", value:"10"}] },
  } };
  let allowed = true;
  state.env.APP.get = () => ({async fetch() {
    return allowed ? Response.json(original) : Response.json({error:"request_denied"},{status:401});
  }});
  const current = request("/api/v1/portfolio/snapshot", {method:"GET"});
  const aggregate = {buckets: [{label:"Information Technology",value:"10"}]};
  let calls = 0;
  const rollup = {sectorRollup(input) {
    calls++;
    assert.deepEqual(JSON.parse(input), {
      sectors:original.exposures.sectors,portfolio_denominator:"100",invested_denominator:"90",
    });
    return JSON.stringify(aggregate);
  }};
  const response = await gateway.fetch(current, state.env, undefined, rollup);
  privateResponse(response);
  const result = await response.json();
  assert.equal(result.total_value, original.total_value);
  assert.deepEqual(result.exposures.sectors, aggregate);
  assert.equal(result.exposures.sector_rollup_method, "broad_sectors_v1");
  allowed = false;
  assert.equal((await gateway.fetch(current, state.env, undefined, rollup)).status, 401);
  assert.equal(calls, 1);
  allowed = true;
  rollup.sectorRollup = () => { throw Error("sector_rollup_invalid"); };
  assert.deepEqual(await (await gateway.fetch(current, state.env, undefined, rollup)).json(), original);
});

test("Meridian requires an approved snapshot and bounds analysis options", async () => {
  const path = "/api/v1/portfolio/meridian";
  const state = setup();
  let runs = 0;
  const planning = { meridian(snapshot, options) {
    runs++;
    assert.equal(snapshot.status, "synthetic");
    assert.deepEqual(options, { window: 90, pair: [0, 2], pair_only: true });
    return '{"state":"available"}';
  } };
  const valid = request(path + "?window=90&pair=0,2&basis=pair", { method: "GET", headers: { cookie: "synthetic" } });
  const response = await gateway.fetch(valid, state.env, undefined, planning);
  assert.equal(await response.json().then(row => row.state), "available");
  privateResponse(response);
  assert.equal(state.requests.length, 1);
  assert.equal(state.requests[0].url, ORIGIN + "/api/v1/portfolio/snapshot");
  assert.equal(state.requests[0].headers.get("cookie"), "synthetic");
  const denied = { ...state.env, APP: { idFromName: () => "", get: () => ({fetch: () => new Response("", {status:401})}) } };
  assert.equal((await gateway.fetch(valid, denied, undefined, planning)).status, 401);
  const invalid = request(path + "?window=30&pair=0,2&basis=pair&window=90", { method: "GET" });
  assert.equal((await gateway.fetch(invalid, state.env, undefined, planning)).status, 400);
  const privateEvidence = request("/cutoff-holdings", { method: "POST" });
  assert.equal((await gateway.fetch(privateEvidence, state.env, undefined, planning)).status, 404);
  assert.equal(runs, 1);
});

test("portfolio export checks membership, pins Meridian input, and renders private Markdown", async () => {
  const { env } = setup();
  const capture = { snapshot_id: "synthetic-save", date: "2026-11-30", status: "observed",
    observed_at: "2026-11-30T20:00:00Z", account_captured_at: "2026-11-30T19:59:00Z",
    positions_captured_at: "2026-11-30T19:59:01Z", portfolio_value: "1000" };
  const position = { ticker: "TEST", name: "A | <b>\nB", quantity: "1", account_currency: "GBP",
    current_value: "15.01", total_cost: "10", unrealized_profit_loss: "5.01" };
  env.APP.get = () => ({ async fetch(upstream) {
    assert.equal(new URL(upstream.url).search, "");
    if (!upstream.headers.has("cookie")) return Response.json({ error: "request_denied" }, { status: 401 });
    return Response.json({ changes: { start: { date: "2026-10-30", status: "missing" }, end: capture },
      target_date: "2026-10-30",
      snapshot: { total_value: "1000", positions: [position] },
    });
  } });
  const path = "/api/v1/portfolio/export";
  const session = { method: "GET", headers: { cookie: "__Host-meridian_session=synthetic" } };
  const opts = { meridian: async snapshot => {
    assert.equal(snapshot.positions[0].current_value, "15.01");
    throw new Error("private diagnostic");
  } };
  const denied = await gateway.fetch(request(path + "?format=markdown", { method: "GET" }), env, null, opts);
  assert.equal(denied.status, 401);
  assert.equal(denied.headers.get("cache-control"), "no-store");
  assert.equal((await gateway.fetch(request(path + "?format=markdown&format=markdown", session), env)).status, 400);

  const json = await gateway.fetch(request(path, session), env, null, opts);
  const data = await json.json();
  assert.equal(data.current.snapshot_id, "synthetic-save");
  assert.equal(data.holdings[0].unrealised_pnl_on_cost_pct, "50.10");
  assert.equal(data.comparison.reason, "baseline_missing");
  assert.equal(data.meridian_risk.reason, "meridian_unavailable");

  const markdown = await gateway.fetch(request(path + "?format=markdown", session), env, null, opts);
  assert.equal(markdown.headers.get("content-disposition"), 'attachment; filename="meridian-portfolio-2026-11-30.md"');
  const text = await markdown.text();
  assert.ok(text.includes("A \\| &lt;b&gt; B"));
  assert.ok(text.includes("15.01") && text.includes("Monthly comparison unavailable"));
  assert.ok(!text.includes("private diagnostic"));
});
