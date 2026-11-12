# Meridian AXIS dashboard preview

This standalone static preview uses only invented fixtures. It has no API,
broker/database bindings, sign-in, analytics collection or private source files.
The persistent demo notice is part of its contract. It is not the authenticated
financial application and must never receive real portfolio values or secrets.

The initial preview provides AXIS, HOLDINGS and GROUPS. Navigation, chart ranges,
holding search/sort/group filters and detail views operate on static fixtures.
Unavailable account/history/risk data must remain explicit. The other requested
application capabilities retain their stage gates in the project documentation.

## Development

Use Node 22.12 or newer (Node 24 is used in CI):

```sh
npm ci
npm test
npm run build
npm run preview
```

The printed loopback address is a local development preview, not a phone link.
The production build is in ignored `dist/`; source and dependencies are tracked
with `package-lock.json`. React, Vite, Tailwind and ECharts implement the approved
frontend stack. Node tests reconcile invented decimal fixtures with exact
integer arithmetic; these do not verify live financial calculations.

## Separate Cloudflare preview

`wrangler.preview.jsonc` deploys static assets only to `meridian-axis-preview` in
the approved account. It has no Worker handler, secret, database binding, cron
or connection to the protected API. Use the repository's pinned Wrangler from
`prototype/worker-feasibility`, pin the account, disable local deployment logs
and review the clean source checkpoint before deploying. Record the actual
returned URL/version in the handoff; do not infer deployment from a build.

Static security headers deny framing and external connections. Robots metadata
discourages indexing; it is not authentication. Only synthetic content may be
published here. Production login and financial data require the separate
security and recovery acceptance gates.
