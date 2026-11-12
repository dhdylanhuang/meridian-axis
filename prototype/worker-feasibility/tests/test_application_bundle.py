"""Bundle only the reviewed public source; refuse unmanaged output or links."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "prepare_application",
    Path(__file__).resolve().parents[1] / "prepare_application.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ApplicationBundleTests(unittest.TestCase):
    def test_exact_allowlist_reproducible_and_refuses_unknown_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source, target = root / "source", root / "target"
            for name in MODULE.FILES:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# synthetic source\n")
            (source / "private.py").write_text("must never be copied")
            first = MODULE.prepare(source, target)
            self.assertEqual(first, MODULE.prepare(source, target))
            self.assertEqual(set(first["sha256"]), set(MODULE.FILES))
            self.assertFalse((target / "private.py").exists())
            self.assertEqual(json.loads((target / MODULE.MARKER).read_text()), first)
            (target / "unmanaged.py").write_text("preserve this")
            with self.assertRaisesRegex(ValueError, "unexpected_file"):
                MODULE.prepare(source, target)
            self.assertEqual((target / "unmanaged.py").read_text(), "preserve this")

    def test_refuses_existing_unmanaged_destination_and_source_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source, target = root / "source", root / "target"
            for name in MODULE.FILES:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# synthetic source\n")
            target.mkdir()
            with self.assertRaisesRegex(ValueError, "unmanaged"):
                MODULE.prepare(source, target)
            path = source / "app.py"
            path.unlink()
            path.symlink_to(source / "__init__.py")
            with self.assertRaisesRegex(ValueError, "symlink_denied"):
                MODULE.prepare(source, root / "new-target")
