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


def build_paste(publishers: list[str] | None = None) -> str:
    """Self-checking block: write the script to a private temp dir, verify its sha256, run
    it in the mode named by G2_MODE (default `plan`, which writes nothing), remove the dir,
    print and return the exit status. apply/rollback run the script through sudo, typed
    by the operator; the block itself never escalates anything else."""
    script = build(publishers)
    digest = hashlib.sha256(script.encode("utf-8")).hexdigest()
    return (
        "MODE=${G2_MODE:-plan}; unset G2_MODE\n"
        'case "$MODE" in plan|verify|apply|rollback) ;; *) echo "G2_MODE must be plan|verify|apply|rollback"; exit 2;; esac\n'
        'D=$(mktemp -d "${TMPDIR:-/tmp}/g2blk.XXXXXX") || exit 1\n'
        "umask 077\n"
        "cat > \"$D/g2.sh\" <<'G2_SCRIPT_EOF'\n"
        f"{script}G2_SCRIPT_EOF\n"
        f'echo "{digest}  $D/g2.sh" | sha256sum -c - || {{ rm -rf "$D"; echo \'HASH MISMATCH: not run\'; exit 1; }}\n'
        'case "$MODE" in\n'
        '  apply|rollback) sudo sh "$D/g2.sh" "$MODE"; RC=$?;;\n'
        '  *) sh "$D/g2.sh" "$MODE"; RC=$?;;\n'
        "esac\n"
        'rm -rf "$D"\n'
        'echo "G2 $MODE exit status: $RC"\n'
        "exit $RC\n"
    )


if __name__ == "__main__":
    (DIR / "g2_install_inactive.sh").write_text(build(), encoding="utf-8")
    (DIR / "g2_paste_block.sh").write_text(build_paste(), encoding="utf-8")
