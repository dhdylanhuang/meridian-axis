import { buildExport, exportMarkdown } from "./portfolio_export.mjs";

// Application session transport. Provider/database secrets belong to the private owner.
const ROUTES = new Map([
  ["/health", "GET"],
  ["/api/v1/portfolio/snapshot", "GET"],
  ["/api/v1/portfolio/export", "GET"],
  ["/api/v1/portfolio/history", "GET"],
  ["/api/v1/portfolio/changes", "GET"],
  ["/api/v1/portfolio/risk", "GET"],
  ["/api/v1/portfolio/meridian", "GET"],
  ["/api/v1/portfolio/projections", "POST"],
  ["/api/v1/portfolio/stress-tests", "POST"],
  ["/api/v1/portfolio/refresh", "POST"],
  ["/api/v1/portfolio/cash-activity", "POST"],
  ["/api/v1/portfolio/refresh/status", "GET"],
  ["/api/v1/session/bootstrap", "GET"],
  ["/api/v1/session/current", "GET"],
  ["/api/v1/session/login", "POST"],
  ["/api/v1/session/setup", "POST"],
  ["/api/v1/session/rotate", "POST"],
  ["/api/v1/session/logout", "POST"],
]);
const NONCE = /^[A-Za-z0-9_-]{43}$/;

class InvalidInput extends Error {
  constructor(code, status) { super(code); this.status = status; }
}

function privateHeaders(input) {
  const headers = new Headers(input);
  headers.set("Cache-Control", "no-store");
  headers.set("Pragma", "no-cache");
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("Referrer-Policy", "no-referrer");
  return headers;
}

function failure(code, status, headers) {
  const result = privateHeaders(headers);
  result.set("Content-Type", "application/json");
  return new Response(JSON.stringify({ error: code }), { status, headers: result });
}

function configuredOrigin(value) {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.username || url.password || value !== url.origin) {
      return null;
    }
    return url;
  } catch { return null; }
}

async function boundedBody(request, maximum) {
  if (!request.body) return new Uint8Array();
  const reader = request.body.getReader();
  let timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new InvalidInput("request_timeout", 408)), 10_000);
  });
  const chunks = [];
  let length = 0;
  let finished = false;
  try {
    while (true) {
      const { done, value } = await Promise.race([reader.read(), deadline]);
      if (done) { finished = true; break; }
      if (!(value instanceof Uint8Array)) throw new InvalidInput("request_invalid", 400);
      length += value.byteLength;
      if (length > maximum) {
        throw new InvalidInput(maximum === 0 ? "request_invalid" : "request_too_large", maximum === 0 ? 400 : 413);
      }
      if (value.byteLength) chunks.push(value);
    }
    const body = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
    return body;
  } catch (error) {
    if (error instanceof InvalidInput) throw error;
    throw new InvalidInput("request_invalid", 400);
  } finally {
    clearTimeout(timer);
    // Do not await a caller-controlled cancellation callback before rejecting.
    if (!finished) void reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

async function calculatePlan(app, origin, headers, body, calculate) {
  let input;
  try {
    input = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(body));
  } catch {
    return failure("request_invalid", 400);
  }
  if (typeof input?.capture_time !== "string" || typeof input?.positions_time !== "string" ||
      !input.assumptions || typeof input.assumptions !== "object") {
    return failure("request_invalid", 400);
  }
  const source = await app.fetch(new Request(origin.origin + "/api/v1/portfolio/snapshot", {
    method: "GET", headers: { Host: origin.host, Cookie: headers.get("cookie") ?? "" }, redirect: "manual",
  }));
  if (!source.ok) {
    return new Response(source.body, { status: source.status, headers: privateHeaders(source.headers) });
  }
  const snapshot = await source.json();
  if (snapshot.account_retrieval?.retrieval_completed_at !== input.capture_time ||
      snapshot.positions_retrieval?.retrieval_completed_at !== input.positions_time) {
    return failure("snapshot_changed", 409);
  }
  if (!calculate) return failure("calculation_unavailable", 503);
  try {
    const result = calculate(JSON.stringify({ snapshot, assumptions: input.assumptions }));
    return new Response(result, { headers: privateHeaders({ "Content-Type": "application/json" }) });
  } catch (error) {
    const validation = new Set([
      "projection_request_invalid", "growth_invalid", "deposit_limit", "deposit_amount_invalid",
      "deposit_date_invalid", "allocation_limit", "destination_invalid", "allocation_amount_invalid",
      "allocation_total_invalid", "projection_horizon_unavailable",
      "stress_request_invalid", "shock_invalid", "stress_basket_invalid", "stress_override_invalid",
    ]);
    return validation.has(error) ? failure(error, 422) : failure("calculation_unavailable", 503);
  }
}

async function calculateMeridian(app, origin, headers, options, planning) {
  let source = await app.fetch(new Request(origin.origin + "/api/v1/portfolio/snapshot", {
    headers, redirect: "manual",
  }));
  if (!source.ok) {
    return new Response(source.body, { status: source.status, headers: privateHeaders(source.headers) });
  }
  try {
    if (planning.sectorRollup) source = await rollupSnapshot(source, planning.sectorRollup);
    const report = await planning.meridian(await source.json(), options);
    return new Response(report, { headers: privateHeaders({ "Content-Type": "application/json" }) });
  } catch (error) {
    return error === "meridian_pair_invalid"
      ? failure("meridian_pair_invalid", 409)
      : failure("meridian_unavailable", 503);
  }
}

function rollupExposures(snapshot, calculate) {
  const report = snapshot.exposures;
  if (report?.method === "broker_exposures_v1" && report.sectors && calculate) {
    const { sectors, portfolio_denominator, invested_denominator } = report;
    report.sectors = JSON.parse(calculate(JSON.stringify({
      sectors, portfolio_denominator, invested_denominator,
    })));
    report.sector_rollup_method = "broad_sectors_v1";
  }
  return snapshot;
}

// Roll up the already-authorised snapshot without modifying saved evidence.
async function rollupSnapshot(response, calculate) {
  const original = await response.text();
  const headers = privateHeaders(response.headers);
  try {
    const snapshot = rollupExposures(JSON.parse(original), calculate);
    if (snapshot.exposures?.sector_rollup_method === "broad_sectors_v1") {
      headers.delete("Content-Length");
      headers.delete("Content-Encoding");
      return new Response(JSON.stringify(snapshot), { status: response.status, headers });
    }
  } catch {
    // Other snapshot data remains usable if the optional display rollup fails.
  }
  return new Response(original, { status: response.status, headers });
}

export default {
  async scheduled(controller, env, ctx) {
    const id = env.SYNC.idFromName("shared-isa");
    const response = await env.SYNC.get(id).fetch(new Request("https://sync.internal/scheduled", {method:"POST"}));
    if (!response.ok) throw new Error("broker_sync_unavailable");
  },
  async fetch(request, env, calculateChanges, planning = {}) {
    const origin = configuredOrigin(env.PUBLIC_ORIGIN);
    if (!origin) return failure("session_configuration_unavailable", 503);
    try {
      const url = new URL(request.url);
      const host = request.headers.get("host");
      if (url.origin !== origin.origin || (host !== null && host !== origin.host)) {
        return failure("origin_invalid", 403);
      }
      const portfolioExport = url.pathname === "/api/v1/portfolio/export";
      const markdown = portfolioExport && url.search === "?format=markdown";
      const changes = url.pathname === "/api/v1/portfolio/changes";
      const dateRange = (changes || url.pathname === "/api/v1/portfolio/risk") &&
        /^\?start=\d{4}-\d{2}-\d{2}&end=\d{4}-\d{2}-\d{2}$/.test(url.search);
      const meridian = url.pathname === "/api/v1/portfolio/meridian";
      const selection = meridian && /^\?window=(30|90|252)(?:&pair=([0-9]{1,3}),([0-9]{1,3})&basis=(common|pair))?$/.exec(url.search);
      if (((changes || meridian || request.url.includes("?")) && !dateRange && !selection && !markdown) || request.url.includes("#")) {
        return failure("request_invalid", 400);
      }
      if (["/", "/signin.js", "/signin.css", "/snapshot.js", "/planning.js", "/dates.js", "/meridian.js", "/holding-detail.js"].includes(url.pathname) && env.ASSETS) {
        if (request.method !== "GET") return failure("method_not_allowed", 405, { Allow: "GET" });
        const supplied = request.headers.get("origin");
        if (supplied !== null && supplied !== origin.origin) return failure("origin_invalid", 403);
        await boundedBody(request, 0);
        const asset = await env.ASSETS.fetch(new Request(origin.origin + url.pathname));
        const headers = privateHeaders(asset.headers);
        headers.set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
        headers.set("X-Frame-Options", "DENY");
        return new Response(asset.body, { status: asset.status, headers });
      }
      const method = ROUTES.get(url.pathname);
      if (!method) return failure("not_found", 404);
      if (request.method !== method) return failure("method_not_allowed", 405, { Allow: method });
      // Workers combines duplicate headers. Exact comparisons/nonce syntax
      // reject merged Origin, Host, CSRF and login Content-Type values.
      const suppliedOrigin = request.headers.get("origin");
      if ((suppliedOrigin !== null && suppliedOrigin !== origin.origin) ||
          (method === "POST" && suppliedOrigin !== origin.origin)) {
        return failure("origin_invalid", 403);
      }
      const csrf = request.headers.get("x-csrf-token");
      if ((csrf !== null && !NONCE.test(csrf)) || (method === "POST" && csrf === null)) {
        return failure("csrf_invalid", 403);
      }
      const endpoint = url.pathname.split("/").at(-1);
      const calculator = ["projections", "stress-tests"].includes(endpoint) ? endpoint : null;
      if (calculator) {
        const csrfCookies = (request.headers.get("cookie") ?? "").split(";")
          .map(value => value.trim()).filter(value => value.startsWith("__Host-meridian_csrf="));
        if (csrfCookies.length !== 1 || csrfCookies[0] !== "__Host-meridian_csrf=" + csrf) {
          return failure("csrf_invalid", 403);
        }
      }
      const login = ["/api/v1/session/login", "/api/v1/session/setup"].includes(url.pathname);
      const activity = url.pathname === "/api/v1/portfolio/cash-activity";
      if ((login || activity || calculator) && request.headers.get("content-type") !== "application/json") {
        return failure("request_invalid", 400);
      }
      const body = await boundedBody(request, login ? 8192 : activity ? 2048 : calculator ? 96 * 1024 : 0);
      const headers = new Headers({ Host: origin.host });
      for (const name of ["origin", "cookie", "x-csrf-token"]) {
        const value = request.headers.get(name);
        if (value !== null) headers.set(name, value);
      }
      if (login || activity) headers.set("Content-Type", "application/json");
      const upstream = new Request(origin.origin + url.pathname + (dateRange ? url.search : ""), {
        method, headers, redirect: "manual", ...((login || activity) ? { body } : {}),
      });
      const id = env.APP.idFromName("meridian-session-application");
      const app = env.APP.get(id);
      if (selection) {
        const [, window, a, b, basis] = selection;
        return await calculateMeridian(app, origin, headers, {
          window: Number(window), pair: a == null ? null : [Number(a), Number(b)], pair_only: basis === "pair",
        }, planning);
      }
      if (calculator) {
        return await calculatePlan(app, origin, headers, body, planning[calculator]);
      }
      const response = await app.fetch(upstream);
      if (portfolioExport && response.ok) {
        try {
          const inputs = await response.json();
          try { rollupExposures(inputs.snapshot, planning.sectorRollup); } catch {
            // The saved exposure report remains available if the display rollup fails.
          }
          const data = await buildExport(inputs, calculateChanges, planning.meridian, planning);
          const headers = privateHeaders();
          if (!markdown) {
            headers.set("Content-Type", "application/json");
            return new Response(JSON.stringify(data), { headers });
          }
          headers.set("Content-Type", "text/markdown; charset=utf-8");
          headers.set("Content-Disposition", 'attachment; filename="meridian-portfolio-' + data.current.date + '.md"');
          return new Response(exportMarkdown(data), { headers });
        } catch {
          return failure("portfolio_export_unavailable", 503);
        }
      }
      if (url.pathname === "/api/v1/portfolio/snapshot" && response.ok && planning.sectorRollup) {
        return await rollupSnapshot(response, planning.sectorRollup);
      }
      if (changes && response.ok) {
        try {
          if (!calculateChanges) throw new Error("changes_unavailable");
          const report = calculateChanges(await response.text());
          const headers = privateHeaders();
          headers.set("Content-Type", "application/json");
          return new Response(report, { status: 200, headers });
        } catch {
          return failure("changes_unavailable", 503);
        }
      }
      return new Response(response.body, {
        status: response.status,
        headers: privateHeaders(response.headers),
      });
    } catch (error) {
      if (error instanceof InvalidInput) return failure(error.message, error.status);
      return failure("session_unavailable", 502);
    }
  },
};
