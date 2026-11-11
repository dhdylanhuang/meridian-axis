// Synthetic diagnostic only. Never attach portfolio data or broker credentials.
const encoder = new TextEncoder();

async function authorized(request, secret) {
  const header = request.headers.get("authorization");
  if (
    typeof secret !== "string" || secret.length === 0 || secret.length > 240 ||
    header === null || header.length > 256
  ) return false;
  try {
    const key = await crypto.subtle.importKey(
      "raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false,
      ["sign", "verify"],
    );
    const expected = await crypto.subtle.sign(
      "HMAC", key, encoder.encode(`Bearer ${secret}`),
    );
    return await crypto.subtle.verify("HMAC", key, expected, encoder.encode(header));
  } catch {
    return false;
  }
}

export default {
  async fetch(request, env) {
    if (!(await authorized(request, env.PROBE_AUTH_TOKEN))) {
      return new Response("Unauthorized", {
        status: 401, headers: { "WWW-Authenticate": "Bearer", "Cache-Control": "no-store" },
      });
    }
    const url = new URL(request.url);
    if (url.pathname !== "/probe") return new Response("Not found", { status: 404 });
    if (request.method !== "GET") {
      return new Response("Method not allowed", { status: 405, headers: { Allow: "GET" } });
    }
    if (url.search || url.hash) return new Response("Unexpected input", { status: 400 });
    try {
      const id = env.PROBE.idFromName("synthetic-database-probe");
      const response = await env.PROBE.get(id).fetch(new Request("https://synthetic.invalid/probe"));
      const headers = new Headers(response.headers);
      headers.set("Cache-Control", "no-store");
      return new Response(response.body, { status: response.status, headers });
    } catch {
      return new Response("Diagnostic unavailable", { status: 502 });
    }
  },
};
