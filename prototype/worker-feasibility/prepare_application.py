"""Copy a fixed public application allowlist into the locked Worker bundle.

Run before pywrangler build/deploy. Never copy backend configuration, migrations,
CLI modules, evidence or private files. Generated files are ignored by Git.
"""

import hashlib
import json
from pathlib import Path

FILES = (
    "__init__.py",
    "app.py",
    "application/__init__.py",
    "application/snapshot_access.py",
    "application/refresh_status.py",
    "application/broker_jobs.py",
    "application/broker_sessions.py",
    "application/broker_sync.py",
    "application/broker_snapshot.py",
    "application/snapshot_publish.py",
    "application/broker_ingestion.py",
    "application/imports.py",
    "adapters/__init__.py",
    "adapters/trading212.py",
    "adapters/broker_evidence.py",
    "adapters/holdings_csv.py",
    "persistence/__init__.py",
    "persistence/models.py",
    "persistence/types.py",
    "security/__init__.py",
    "security/hosted.py",
    "security/hosted_sync.py",
    "security/http.py",
    "security/login_limiter.py",
    "security/sessions.py",
    "security/supabase_auth.py",
)
MARKER = ".application-bundle.json"


def prepare(source: Path, destination: Path):
    if source.is_symlink() or destination.is_symlink():
        raise ValueError("bundle_symlink_denied")
    # Read and validate the whole source before writing anything.
    contents = {}
    for relative in FILES:
        path = source / relative
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError("bundle_symlink_denied")
        contents[relative] = path.read_bytes()
    if destination.exists():
        marker = destination / MARKER
        if not marker.is_file() or marker.is_symlink():
            raise ValueError("bundle_destination_unmanaged")
        recorded = json.loads(marker.read_text())
        if recorded.get("generator") != "meridian-application-allowlist-v1":
            raise ValueError("bundle_destination_unmanaged")
        for path in destination.rglob("*"):
            if path.is_symlink():
                raise ValueError("bundle_symlink_denied")
            if path.is_file() and path.relative_to(destination).as_posix() not in (
                *FILES,
                MARKER,
            ):
                raise ValueError("bundle_destination_unexpected_file")
    destination.mkdir(parents=True, exist_ok=True)
    for relative, content in contents.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = {
        "generator": "meridian-application-allowlist-v1",
        "sha256": {
            name: hashlib.sha256(value).hexdigest() for name, value in contents.items()
        },
    }
    (destination / MARKER).write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    prototype = Path(__file__).resolve().parent
    prepare(prototype.parents[1] / "backend/src/meridian", prototype / "src/meridian")
    print("Prepared fixed public application allowlist")
