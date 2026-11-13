"""Provision the private broker Worker through hidden prompts and Wrangler stdin."""

import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

from meridian.adapters.trading212 import Trading212Client

WORKER = "meridian-axis-sync-runtime"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-read-only",
        action="store_true",
        required=True,
        help="Confirm the key has required read permissions and no trading permissions",
    )
    args = parser.parse_args(argv)
    if not args.confirm_read_only or not sys.stdin.isatty() or not sys.stderr.isatty():
        print("private_terminal_required", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parents[3]
    wrangler = root / "prototype/worker-feasibility/node_modules/.bin/wrangler"
    if not wrangler.is_file():
        print("wrangler_unavailable", file=sys.stderr)
        return 2
    environment = os.environ.copy()
    node_bin = root / "private/dev-tools/node_modules/.bin"
    if (node_bin / "node").is_file():
        environment["PATH"] = str(node_bin) + os.pathsep + environment.get("PATH", "")
    environment.update(WRANGLER_WRITE_LOGS="false", WRANGLER_SEND_METRICS="false")
    try:
        check = subprocess.run(
            [str(wrangler), "whoami", "--json"],
            cwd=wrangler.parents[2],
            env=environment,
            capture_output=True,
            timeout=30,
        )
        if check.returncode:
            raise ValueError
        identity = json.loads(check.stdout)
        account_id = json.loads(
            (wrangler.parents[2] / "wrangler.sync-runtime.template.json").read_text()
        )["account_id"]
        if account_id not in [account.get("id") for account in identity.get("accounts", [])]:
            raise ValueError
        deployed = subprocess.run(
            [str(wrangler), "deployments", "list", "--name", WORKER],
            cwd=wrangler.parents[2],
            env=environment,
            capture_output=True,
            timeout=30,
        )
        if deployed.returncode:
            raise ValueError
    except Exception:
        print("wrangler_authentication_unavailable", file=sys.stderr)
        return 2
    key = getpass.getpass("Trading 212 read-only API key (hidden): ")
    secret = getpass.getpass("Trading 212 API secret (hidden): ")
    # Constructor validation only. Provisioning makes no broker requests.
    try:
        import asyncio

        client = Trading212Client(api_key=key, api_secret=secret, environment="live")
        asyncio.run(client.aclose())
        result = subprocess.run(
            [str(wrangler), "secret", "bulk", "--name", WORKER],
            input=json.dumps({"BROKER_API_KEY": key, "BROKER_API_SECRET": secret}).encode(),
            cwd=wrangler.parents[2],
            env=environment,
            capture_output=True,
            timeout=120,
        )
        if result.returncode:
            raise ValueError
    except Exception:
        print("broker_secret_provision_failed", file=sys.stderr)
        return 2
    print("broker_secret_bindings_provisioned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
