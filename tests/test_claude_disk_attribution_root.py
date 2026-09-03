from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts/claude-disk-attribution-root"
SUDOERS = ROOT / "deploy/sudoers/claude-audit-disk-attribution"


class TestDiskAttributionRootBoundary(unittest.TestCase):
    def test_wrapper_has_valid_bash_syntax(self):
        result = subprocess.run(["bash", "-n", str(WRAPPER)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrapper_executes_only_fixed_isolated_python_pack(self):
        source = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("exec /usr/bin/python3 -I /usr/local/bin/claude-disk-attribution\n", source)
        self.assertNotIn("eval ", source)
        self.assertNotIn("bash -c", source)
        self.assertNotIn("$SSH_ORIGINAL_COMMAND", source)

    def test_wrapper_rejects_all_arguments_before_pack_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "executed"
            fake_pack = root / "fake.py"
            fake_pack.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding="utf-8")
            wrapper = root / "wrapper"
            wrapper.write_text(WRAPPER.read_text(encoding="utf-8").replace(
                "/usr/local/bin/claude-disk-attribution", str(fake_pack)
            ), encoding="utf-8")
            wrapper.chmod(0o700)
            result = subprocess.run([str(wrapper), "caller-controlled"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 64)
            self.assertFalse(marker.exists())
            self.assertEqual(result.stdout, "")

    def test_sudoers_grants_one_exact_root_wrapper(self):
        active = [line.strip() for line in SUDOERS.read_text(encoding="utf-8").splitlines()
                  if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(active, [
            "claude-audit ALL=(root) NOPASSWD: /usr/local/sbin/claude-disk-attribution-root"
        ])
        self.assertNotIn("/bin/bash", active[0])
        self.assertNotIn("/bin/sh", active[0])


if __name__ == "__main__":
    unittest.main()
