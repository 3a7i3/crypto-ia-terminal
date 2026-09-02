from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts/claude-disk-growth-root"
SUDOERS = ROOT / "deploy/sudoers/claude-audit-disk-growth"


class TestDiskGrowthRootBoundary(unittest.TestCase):
    def test_wrapper_has_valid_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(WRAPPER)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrapper_executes_only_fixed_isolated_python_pack(self):
        source = WRAPPER.read_text(encoding="utf-8")
        self.assertIn(
            "exec /usr/bin/python3 -I /usr/local/bin/claude-disk-growth\n",
            source,
        )
        self.assertNotIn("eval ", source)
        self.assertNotIn("bash -c", source)
        self.assertNotIn("$SSH_ORIGINAL_COMMAND", source)

    def test_wrapper_rejects_all_arguments_before_pack_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "executed"
            fake_pack = root / "fake-pack.py"
            fake_pack.write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed')\n",
                encoding="utf-8",
            )
            wrapper = root / "wrapper"
            wrapper.write_text(
                WRAPPER.read_text(encoding="utf-8").replace(
                    "/usr/local/bin/claude-disk-growth", str(fake_pack)
                ),
                encoding="utf-8",
            )
            wrapper.chmod(0o700)

            result = subprocess.run(
                [str(wrapper), "caller-controlled"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 64)
            self.assertFalse(marker.exists())
            self.assertEqual(result.stdout, "")
            self.assertEqual(
                result.stderr,
                "DISK_GROWTH_ROOT_REJECTED: arguments are not accepted\n",
            )

    def test_sudoers_grants_one_exact_root_wrapper(self):
        active = [
            line.strip()
            for line in SUDOERS.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertEqual(
            active,
            [
                "claude-audit ALL=(root) NOPASSWD: "
                "/usr/local/sbin/claude-disk-growth-root"
            ],
        )
        self.assertNotIn("ALL,", active[0])
        self.assertNotIn("/bin/bash", active[0])
        self.assertNotIn("/bin/sh", active[0])


if __name__ == "__main__":
    unittest.main()
