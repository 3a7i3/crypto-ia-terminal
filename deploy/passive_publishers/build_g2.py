"""Build g2_install_inactive.sh and g2_paste_block.sh from g2_template.sh.

The reviewed unit files in this directory stay the single source. Only the publishers
in G2_PUBLISHERS are embedded (events is deliberately absent until its contract/release
decision is made); the sha256 of every embedded unit is baked into the script so the
operator-side check compares the installed bytes with the reviewed ones.
Tests check both generated files byte-for-byte against this module.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

DIR = Path(__file__).resolve().parent
G2_PUBLISHERS = ["runtime-service", "storage"]


def unit_names(publishers: list[str] | None = None) -> list[str]:
    names: list[str] = []
    for pub in publishers or G2_PUBLISHERS:
        names += [f"crypto-publish-{pub}.service", f"crypto-publish-{pub}.timer"]
    return names


def unit_hashes(publishers: list[str] | None = None) -> dict[str, str]:
    return {
        name: hashlib.sha256((DIR / name).read_bytes()).hexdigest()
        for name in unit_names(publishers)
    }


def build(publishers: list[str] | None = None) -> str:
    pubs = publishers or G2_PUBLISHERS
    hashes = unit_hashes(pubs)
    embedded, expect = [], []
    for name in unit_names(pubs):
        body = (DIR / name).read_text(encoding="utf-8")
        assert "\nG2_EOF\n" not in body and body.endswith("\n"), name
        embedded.append(f"cat > \"$W/units/{name}\" <<'G2_EOF'\n{body}G2_EOF\n")
        expect.append(f"{name}) echo {hashes[name]} ;;")
    template = (DIR / "g2_template.sh").read_text(encoding="utf-8")
    for key in ("@@PUBS@@", "@@EXPECT@@", "@@UNITS@@\n"):
        assert template.count(key) == 1, key
    out = (
        template.replace("@@PUBS@@", " ".join(pubs))
        .replace("@@EXPECT@@", "\n".join(expect))
        .replace("@@UNITS@@\n", "".join(embedded))
    )
    return "#!/bin/sh\n" + out


# Runs INSIDE the (privileged, for apply/rollback) shell: the script arrives on stdin, is written
# to a directory that only that shell's user can enter (/run, 0700, for root), is re-hashed THERE,
# and only that protected copy is executed. No user-writable path sits between check and use.
PROTECTED_RUNNER = (
    "umask 077; "
    'if [ "$(id -u)" -eq 0 ]; then P=/run; else P="${TMPDIR:-/tmp}"; fi; '
    'R=$(mktemp -d "$P/g2priv.XXXXXX") || exit 1; '
    'cat > "$R/g2.sh" || { rm -rf "$R"; echo "COPY FAILED: not run"; exit 1; }; '
    'echo "$1  $R/g2.sh" | sha256sum -c - '
    '|| { rm -rf "$R"; echo "HASH MISMATCH OF THE PROTECTED COPY: not run"; exit 1; }; '
    'sh "$R/g2.sh" "$2"; RC=$?; rm -rf "$R"; exit $RC'
)


def build_paste(publishers: list[str] | None = None) -> str:
    """Self-checking block. The mode comes from G2_MODE (default `plan`, which writes nothing).
    apply/rollback run through sudo (typed by the operator); the script is hashed again by the
    privileged shell on its own root-only copy before it runs. The block prints the exit status."""
    script = build(publishers)
    digest = hashlib.sha256(script.encode("utf-8")).hexdigest()
    assert "'" not in PROTECTED_RUNNER
    return (
        "MODE=${G2_MODE:-plan}; unset G2_MODE\n"
        'case "$MODE" in plan|verify|apply|rollback) ;; '
        '*) echo "G2_MODE must be plan|verify|apply|rollback"; exit 2;; esac\n'
        f"RUN='{PROTECTED_RUNNER}'\n"
        'PRIV=""; case "$MODE" in apply|rollback) PRIV=sudo;; esac\n'
        f'$PRIV sh -c "$RUN" g2priv {digest} "$MODE" <<\'G2_SCRIPT_EOF\'\n'
        f"{script}G2_SCRIPT_EOF\n"
        "RC=$?\n"
        'echo "G2 $MODE exit status: $RC"\n'
        "exit $RC\n"
    )


if __name__ == "__main__":
    (DIR / "g2_install_inactive.sh").write_text(build(), encoding="utf-8")
    (DIR / "g2_paste_block.sh").write_text(build_paste(), encoding="utf-8")
