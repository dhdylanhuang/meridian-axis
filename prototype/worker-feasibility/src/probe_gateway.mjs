// Experimental synthetic gateway. It accepts no portfolio data or credentials.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== "/health" && url.pathname !== "/probe") {
      return new Response("Not found", { status: 404 });
    }
    if (request.method !== "GET") {
      return new Response("Method not allowed", {
        status: 405,
        headers: { Allow: "GET" },
      });
    }
    if (url.search || url.hash) {
      return new Response("Unexpected input", { status: 400 });
    }
    const id = env.PROBE.idFromName("synthetic-probe");
    const stub = env.PROBE.get(id);
    // A fresh fixed-origin request carries no caller headers, body or query.
    return stub.fetch(new Request(`https://synthetic.invalid${url.pathname}`));
  },
};
