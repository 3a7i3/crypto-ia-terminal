"""Build g1_stage_verify_measure.sh: g1_template.sh with the six unit files embedded.

The unit files in this directory stay the single source; the generated script is
checked byte-for-byte by tests/test_passive_publishers_units.py.
"""

from __future__ import annotations

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


if __name__ == "__main__":
    (DIR / "g1_stage_verify_measure.sh").write_text(build(), encoding="utf-8")
