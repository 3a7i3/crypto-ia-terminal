"""Build g1_stage_verify_measure.sh: g1_template.sh with the six unit files embedded.

The unit files in this directory stay the single source; the generated script is
checked byte-for-byte by tests/test_passive_publishers_units.py.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

DIR = Path(__file__).resolve().parent
UNITS = [
    "crypto-publish-runtime-service.service", "crypto-publish-runtime-service.timer",
    "crypto-publish-storage.service", "crypto-publish-storage.timer",
    "crypto-publish-events.service", "crypto-publish-events.timer",
]


def build() -> str:
    parts = []
    for name in UNITS:
        body = (DIR / name).read_text(encoding="utf-8")
        assert "\nG1_EOF\n" not in body and body.endswith("\n"), name
        parts.append(f"cat > \"$W/units/{name}\" <<'G1_EOF'\n{body}G1_EOF\n")
    template = (DIR / "g1_template.sh").read_text(encoding="utf-8")
    return "#!/bin/sh\n" + template.replace("@@UNITS@@\n", "".join(parts))


def build_paste() -> str:
    """Self-checking block to paste: write the script to a private temp dir, verify its
    sha256, run it, remove the dir, return its exit status."""
    script = build()
    digest = hashlib.sha256(script.encode("utf-8")).hexdigest()
    return (
        "D=$(mktemp -d \"${TMPDIR:-/tmp}/g1blk.XXXXXX\") || exit 1\n"
        "umask 077\n"
        "cat > \"$D/g1.sh\" <<'G1_SCRIPT_EOF'\n"
        f"{script}G1_SCRIPT_EOF\n"
        f"echo \"{digest}  $D/g1.sh\" | sha256sum -c - || {{ rm -rf \"$D\"; echo 'HASH MISMATCH: not run'; exit 1; }}\n"
        "sh \"$D/g1.sh\"; RC=$?\n"
        "rm -rf \"$D\"\n"
        "echo \"exit status: $RC\"\n"
        "exit $RC\n"
    )


if __name__ == "__main__":
    (DIR / "g1_stage_verify_measure.sh").write_text(build(), encoding="utf-8")
    (DIR / "g1_paste_block.sh").write_text(build_paste(), encoding="utf-8")
