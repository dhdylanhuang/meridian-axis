"""Private administrator recovery archives; never imported by the hosted runtime.

SQL is trusted administrator input. Decryption authenticates bytes, not SQL safety.
Only restore into an isolated target; this module exposes no remote restore route.
"""

import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"MERIDIAN-RECOVERY-1\n"
MAX_BYTES = 256 * 1024 * 1024
FILES = frozenset({"roles.sql", "schema.sql", "data.sql"})


class RecoveryError(ValueError):
    """Safe category: no SQL, credentials or source values in messages."""


def private_write(path: Path, data: bytes) -> None:
    """Exclusive output: never replace a key or a previously accepted archive."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def create_key(path: Path) -> None:
    private_write(path, AESGCM.generate_key(bit_length=256))


def read_key(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RecoveryError("recovery_key_invalid")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise RecoveryError("recovery_key_permissions")
    with path.open("rb") as source:
        key = source.read(33)
    if len(key) != 32:
        raise RecoveryError("recovery_key_invalid")
    return key


def seal(files: dict[str, bytes], controls: dict, key: bytes) -> bytes:
    if set(files) != FILES or any(not data for data in files.values()):
        raise RecoveryError("recovery_files_invalid")
    if sum(map(len, files.values())) > MAX_BYTES // 2:
        raise RecoveryError("recovery_size_limit")
    document = {
        "version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "controls": controls,
        "files": {
            name: {
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "data": base64.b64encode(data).decode("ascii"),
            }
            for name, data in files.items()
        },
    }
    plaintext = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, plaintext, MAGIC)


def unseal(archive: bytes, key: bytes) -> tuple[dict[str, bytes], dict]:
    if len(archive) > MAX_BYTES or not archive.startswith(MAGIC):
        raise RecoveryError("recovery_archive_invalid")
    try:
        offset = len(MAGIC)
        plaintext = AESGCM(key).decrypt(
            archive[offset : offset + 12], archive[offset + 12 :], MAGIC
        )
        document = json.loads(plaintext)
        if document["version"] != 1 or set(document["files"]) != FILES:
            raise ValueError
        if not isinstance(document["controls"], dict):
            raise ValueError
        files = {}
        for name, item in document["files"].items():
            data = base64.b64decode(item["data"], validate=True)
            if not data or len(data) != item["bytes"]:
                raise ValueError
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError
            files[name] = data
        return files, document["controls"]
    except Exception:
        raise RecoveryError("recovery_authentication_failed") from None


def load_archive(path: Path, key_path: Path) -> tuple[dict[str, bytes], dict]:
    with path.open("rb") as source:
        archive = source.read(MAX_BYTES + 1)
    return unseal(archive, read_key(key_path))
