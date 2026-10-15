"""Build g3_trials.sh and g3_paste_block.sh from g3_template.sh.

Same discipline as build_g2: the reviewed unit files stay the single source and their sha256 are
baked in; only runtime-service and storage are in scope (events is deliberately absent). The paste
block runs one publisher per invocation (G3_PUB), `plan` without sudo, `run` through sudo with
the script re-hashed on a root-only copy before it runs. Tests check both generated files
byte-for-byte against this module.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from build_g2 import G2_PUBLISHERS, unit_hashes, unit_names

DIR = Path(__file__).resolve().parent
G3_PUBLISHERS = list(G2_PUBLISHERS)

PROTECTED_RUNNER = (
    "umask 077; "
    'if [ "$(id -u)" -eq 0 ]; then P=/run; else P="${TMPDIR:-/tmp}"; fi; '
    'R=$(mktemp -d "$P/g3priv.XXXXXX") || exit 1; '
    'cat > "$R/g3.sh" || { rm -rf "$R"; echo "COPY FAILED: not run"; exit 1; }; '
    'echo "$1  $R/g3.sh" | sha256sum -c - '
    '|| { rm -rf "$R"; echo "HASH MISMATCH OF THE PROTECTED COPY: not run"; exit 1; }; '
    'sh "$R/g3.sh" "$2" "$3"; RC=$?; rm -rf "$R"; exit $RC'
)


def build() -> str:
    hashes = unit_hashes(G3_PUBLISHERS)
    expect = "\n".join(f"{n}) echo {hashes[n]} ;;" for n in unit_names(G3_PUBLISHERS))
    template = (DIR / "g3_template.sh").read_text(encoding="utf-8")
    for key in ("@@UNITS@@", "@@EXPECT@@"):
        assert template.count(key) == 1, key
    out = template.replace("@@UNITS@@", " ".join(unit_names(G3_PUBLISHERS))).replace(
        "@@EXPECT@@", expect
    )
    return "#!/bin/sh\n" + out


def build_paste() -> str:
    script = build()
    digest = hashlib.sha256(script.encode("utf-8")).hexdigest()
    assert "'" not in PROTECTED_RUNNER
    return (
        "MODE=${G3_MODE:-plan}; PUB=${G3_PUB:-}; unset G3_MODE G3_PUB\n"
        'case "$MODE" in plan|run) ;; *) echo "G3_MODE must be plan|run"; exit 2;; esac\n'
        'case "$PUB" in runtime-service|storage) ;; '
        '*) echo "G3_PUB must be runtime-service|storage (one per run)"; exit 2;; esac\n'
        f"RUN='{PROTECTED_RUNNER}'\n"
        'PRIV=""; case "$MODE" in run) PRIV=sudo;; esac\n'
        f'$PRIV sh -c "$RUN" g3priv {digest} "$MODE" "$PUB" <<\'G3_SCRIPT_EOF\'\n'
        f"{script}G3_SCRIPT_EOF\n"
        "RC=$?\n"
        'echo "G3 $MODE $PUB exit status: $RC"\n'
        "exit $RC\n"
    )


if __name__ == "__main__":
    (DIR / "g3_trials.sh").write_text(build(), encoding="utf-8")
    (DIR / "g3_paste_block.sh").write_text(build_paste(), encoding="utf-8")
