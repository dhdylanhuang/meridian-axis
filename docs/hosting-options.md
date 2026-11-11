# Free hosting and private remote access

Reviewed **11 November 2026** against official provider documentation. Status: researched options and **PROPOSED** deployment choice; no host, account, tunnel or remote access has been configured. The owner has requested hosting and confirmed **free services only**. The public repository is source code, not permission to publish portfolio data.

## Recommendation

Keep the current FastAPI/SQLite modular monolith and one scheduler. For a genuinely cloud-hosted instance, first check whether the owner can obtain an **Oracle Cloud Always Free VM** in the chosen home region. This preserves the existing stack and persistent local disk, but capacity and continued availability cannot be promised. Provision only resources explicitly labelled Always Free; a time-limited trial is not the hosting plan.

If no suitable cloud VM is available, the practical alternative is an existing always-on machine with **Tailscale Personal and Serve**. This gives both users a private HTTPS URL without buying a domain. It is self-hosting: power, connectivity, operating-system upkeep and backups remain the owner's responsibility. Hardware and electricity are not included in a £0 service bill. Treat this as the fallback proposal, not an owner-approved decision.

Do not move the financial database onto disposable free web-service storage or rewrite persistence merely to obtain a demo URL. Application authentication, secure cookies, CSRF, audit and restore gates remain mandatory on either path. Hosting research can proceed during development; financial remote access waits for the applicable security and operational acceptance gates.

## Options and constraints

| Option | Stack and persistence | Availability and cost limits | Assessment |
| --- | --- | --- | --- |
| Oracle Always Free VM | Runs Python, built React assets, one scheduler and SQLite on a persistent volume | Home-region capacity may be unavailable; idle instances can be reclaimed. Current documented allowance includes 200 GB combined boot/block storage and five volume backups. No Free Tier SLA. Card verification is required. | Conditional cloud candidate; requires owner signup and capacity verification. |
| Existing machine + Tailscale Personal/Serve | Keeps SQLite on the machine; Serve proxies the app over HTTPS inside the tailnet | Personal currently allows six users, enough for two. Machine must remain awake and connected for scheduled polling and access. Each client needs Tailscale access. | Simplest private fallback if an existing machine can stay available. |
| Existing machine + named Cloudflare Tunnel/Access | Tunnel connects an existing origin; it does not supply compute or database storage | Cloudflare lists a free Zero Trust allowance of 50 users. Publishing the standard application route needs a Cloudflare account and a domain on Cloudflare; buying a domain would violate a strict zero-spend requirement unless already owned. | Alternative where an existing domain and browser-only access are preferred; explicitly restrict Access to both identities. |
| Render Free web service | Python works, but local files including SQLite are lost on restart, redeploy or spin-down; persistent disks require paid compute | Sleeps after 15 minutes without inbound traffic. Free Postgres expires after 30 days. | Reject for this durable database and background polling design. Synthetic disposable previews only. |

Sources: [Oracle resource limits and reclamation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [Oracle signup and SLA FAQ](https://www.oracle.com/cloud/free/faq/), [Tailscale pricing](https://tailscale.com/pricing), [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve), [Cloudflare plans](https://www.cloudflare.com/plans/), [Tunnel prerequisites](https://developers.cloudflare.com/tunnel/get-started/), [Render Free limitations](https://render.com/docs/free).

Cloudflare **Quick Tunnels** are a separate development facility: temporary hostname, no uptime guarantee and **no SSE support**. They do not meet this application's streaming/deployment contract. [Quick Tunnel limitations](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)

Static hosting can distribute frontend files but cannot by itself run this Python process, persistent SQLite database or scheduler. The currently available Sites workflow is not assumed compatible with these requirements; a runtime/persistence change would require a separate architectural decision and migration evidence.

## Proposed deployment shape

Build React once and serve the resulting assets from the same application origin as `/api`. Run one backend process and one scheduler owner. Keep SQLite and imported evidence outside the release directory on local persistent storage with restricted permissions. Do not use a shared network drive as the active database. Backups must survive loss of the host; another directory on the same VM is insufficient.

For either proposed host, Tailscale Serve can provide a tailnet-only HTTPS endpoint in front of a loopback backend. Restrict network policy to the intended two identities and the application port; inspect the initial tailnet policy rather than assuming it is restrictive. Keep two application logins as a second boundary. Use **Serve**, not the public-exposure Funnel feature. Verify the selected machine and client platform support during deployment. [Private web server and Serve guidance](https://tailscale.com/docs/solutions/host-private-server-docker)

HTTPS provisioning publishes the machine/tailnet certificate name in certificate-transparency records. Choose a neutral hostname without financial or personal details; this publishes a name, not the portfolio contents. [Tailscale HTTPS prerequisites and disclosure](https://tailscale.com/docs/how-to/set-up-https-certificates)

For a Cloudflare route, configure Access before making the hostname usable, retain application login and set exact trusted proxy/origin rules. Tunnel tokens are secrets. Test SSE end-to-end rather than assuming ordinary HTTP success proves streaming works. Tunnel is an outbound origin connection; it does not solve host downtime. [Cloudflare Tunnel architecture](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/)

## Deployment gate and owner inputs

Before selecting a host, establish:

1. Whether the owner can obtain an Always Free VM with sufficient capacity, or can keep an existing machine awake during all required exchange sessions. If card verification is unacceptable, exclude Oracle without collecting payment details.
2. Whether both users accept installing Tailscale on their devices. For browser-only access, establish an already-owned suitable domain and Cloudflare account instead.
3. A private off-host backup destination, access policy and retention budget. Demonstrate SQLite online backup and separate-path restore; VM snapshots alone do not establish application consistency.

Before exposing real data, verify fresh install, migrations, two logins, expiry/logout/CSRF, exact HTTPS origin, unauthenticated financial-route denial, secret redaction, scheduler singleton, polling restart/backfill and authenticated SSE reconnection. Demonstrate recovery from host loss/redeploy using the backed-up evidence and database. Record the real recovery time and known polling gaps. Do not promise 24/7 uptime, complete intraday sampling or continuous alerts on unverified free infrastructure.

If Oracle is selected, inspect free eligibility and resource summaries before creation, stay within the documented home-region allowances, and avoid a paid-account upgrade or trial-only resource. If capacity cannot be obtained, report that fact and use an agreed fallback; do not manufacture load to avoid reclamation. Recheck all provider limits at deployment because free plans can change.

No hosting purchase, provider account creation, DNS/firewall change, invitation or production deployment is performed by this research document. Follow the owner's current authorisation and the [development gates](development-stages.md) when implementing the chosen path.
