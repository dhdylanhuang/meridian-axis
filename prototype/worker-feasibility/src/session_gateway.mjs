// Application session transport. Provider/database secrets belong to the private owner.
const ROUTES = new Map([
  ["/health", "GET"],
  ["/api/v1/portfolio/snapshot", "GET"],
  ["/api/v1/portfolio/refresh", "POST"],
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

export default {
  async fetch(request, env) {
    const origin = configuredOrigin(env.PUBLIC_ORIGIN);
    if (!origin) return failure("session_configuration_unavailable", 503);
    try {
      const url = new URL(request.url);
      const host = request.headers.get("host");
      if (url.origin !== origin.origin || (host !== null && host !== origin.host)) {
        return failure("origin_invalid", 403);
      }
      if (request.url.includes("?") || request.url.includes("#")) {
        return failure("request_invalid", 400);
      }
      if (["/", "/signin.js", "/signin.css", "/snapshot.js"].includes(url.pathname) && env.ASSETS) {
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
      const login = ["/api/v1/session/login", "/api/v1/session/setup"].includes(url.pathname);
      if (login && request.headers.get("content-type") !== "application/json") {
        return failure("request_invalid", 400);
      }
      const body = await boundedBody(request, login ? 8192 : 0);
      const headers = new Headers({ Host: origin.host });
      for (const name of ["origin", "cookie", "x-csrf-token"]) {
        const value = request.headers.get(name);
        if (value !== null) headers.set(name, value);
      }
      if (login) headers.set("Content-Type", "application/json");
      const upstream = new Request(origin.origin + url.pathname, {
        method, headers, redirect: "manual", ...(login ? { body } : {}),
      });
      const id = env.APP.idFromName("meridian-session-application");
      const response = await env.APP.get(id).fetch(upstream);
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
