"""Package the locked Rust WASM artifact for Cloudflare's module loader."""

import argparse
import hashlib
import json
import subprocess
import tempfile
import tomllib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wasm", type=Path, required=True)
    parser.add_argument("--wasm-bindgen", type=Path, required=True)
    args = parser.parse_args()
    crate = Path(__file__).resolve().parents[1]
    root = crate.parents[1]
    output = root / "prototype/worker-feasibility/src/reconciliation_wasm"
    allowed = {
        "axis_reconciliation.mjs",
        "axis_reconciliation_bg.wasm",
        "manifest.json",
    }
    if (
        output.is_symlink()
        or output.exists()
        and (
            not (output / "manifest.json").is_file()
            or any(p.is_symlink() or p.name not in allowed for p in output.iterdir())
        )
    ):
        raise ValueError("unmanaged_wasm_destination")
    lock = tomllib.loads((crate / "Cargo.lock").read_text())
    version = next(p["version"] for p in lock["package"] if p["name"] == "wasm-bindgen")
    actual = subprocess.check_output(
        [str(args.wasm_bindgen), "--version"], text=True
    ).strip()
    if actual != "wasm-bindgen " + version:
        raise ValueError("wasm_generator_version_mismatch")
    with tempfile.TemporaryDirectory(prefix="axis-wasm-") as temporary:
        subprocess.run(
            [
                str(args.wasm_bindgen),
                str(args.wasm),
                "--target",
                "web",
                "--no-typescript",
                "--out-name",
                "axis_reconciliation",
                "--out-dir",
                temporary,
            ],
            check=True,
        )
        generated = Path(temporary)
        files = {
            "axis_reconciliation.mjs": (
                generated / "axis_reconciliation.js"
            ).read_bytes(),
            "axis_reconciliation_bg.wasm": (
                generated / "axis_reconciliation_bg.wasm"
            ).read_bytes(),
        }
    manifest = {
        "generator": "axis-cash-wasm-v1",
        "wasm_bindgen": version,
        "files": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for name, data in files.items()
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (output / name).write_bytes(data)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": "packaged",
                "wasm_bindgen": version,
                "wasm_bytes": len(files["axis_reconciliation_bg.wasm"]),
            }
        )
    )


if __name__ == "__main__":
    main()
