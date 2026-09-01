# Claude audit snapshot — governed rebuild

## Purpose

`/srv/claude-audit/repo` is a static research snapshot. It is not the
production worktree and it must never be treated as proof of the code currently
executed by a service.

The snapshot is built from one exact public GitHub commit by the root-owned
administrator tool installed as:

`/usr/local/sbin/claude-audit-snapshot-build`

The tool is deliberately absent from the SSH forced-command allowlist. An AI
audit request can observe the snapshot and its manifest, but cannot rebuild it.

## Security and provenance contract

The builder:

- accepts exactly one lowercase 40-character Git commit SHA;
- fetches only `https://github.com/3a7i3/crypto-ia-terminal.git`;
- never reads or copies `/home/mathieu/crypto_ai_terminal`;
- rejects tracked symlinks and gitlinks;
- verifies `HEAD`, `origin/main`, the Git tree and a clean worktree;
- installs the snapshot as `root:claude-audit` without write bits;
- creates `/srv/claude-audit/AUDIT_MANIFEST.txt` with the source SHA, tree SHA,
  UTC timestamp, builder hash, file count and permission contract;
- moves the previous snapshot and manifest to timestamped backup paths;
- restores the previous paths automatically if final validation fails;
- never deletes the previous material snapshot.

No tracked path is sanitized. This is intentional: the source is the public
GitHub commit, not the production filesystem. The manifest records
`sanitized_paths_count=0` and `production_runtime_source_accessed=false`.

## Governed deployment sequence

Use an exact merged commit and an independently supplied SHA-256 for the
builder file.

1. Download the builder from the exact GitHub commit into `/tmp`.
2. Verify its SHA-256 and compile it with `python3 -m py_compile`.
3. Install it as `root:root`, mode `0755`.
4. Install the matching dispatcher update as `root:root`, mode `0755`.
5. Execute the installed builder with the chosen 40-character source SHA.
6. Keep every `pre-snapshot-*` backup until the GitHub audit actions below are
   certified.

The session operator must receive short, commit-pinned mobile commands for the
exact release. Do not substitute `main` for the source SHA.

## Required post-deployment evidence

Run these existing READ-ONLY actions through BRIDGE-04, one request at a time:

1. `snapshot_manifest_meta` — visible, readable, regular file, bounded size.
2. `snapshot_manifest` — source SHA/tree SHA and permission contract present.
3. `repo_status` — empty stdout and exit code `0`.
4. `repo_log` — `HEAD`, `main` and `origin/main` identify the pinned commit.

Only after all four envelopes are valid may the clone be marked `CONFIRMÉ` as
a scientific static-code source.

## Rollback

The builder performs automatic rollback on a failed transaction. After a
successful build, manual rollback consists of moving the new snapshot aside
and restoring the exact `repo.pre-snapshot-<UTC>` and matching manifest backup.
Because those paths are timestamp-specific, Codex must first inspect and name
the exact targets; this runbook intentionally contains no broad removal or
wildcard command.
