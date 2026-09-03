# Audit Pack `disk_attribution`

## Purpose

`disk_attribution` localizes filesystem growth that is not explained by the
two runtime roots measured by `disk_growth`. It emits allocation totals grouped
only by the first component below `/` (for example `home`, `var`, and `usr`).
It is a diagnostic companion, not a replacement for the comparable
`disk_growth` baseline.

## Security contract

- accepts no arguments;
- scans only the fixed root `/`;
- reads filesystem metadata, never file contents;
- emits aggregate bucket names only, never file paths;
- does not follow symbolic links;
- does not cross filesystem boundaries;
- does not execute subprocesses;
- writes no VPS baseline or other runtime file;
- stops at 500,000 entries, 32 levels, 45 seconds, or 16,000 output bytes;
- reports partial or limited collection instead of presenting it as complete.

The forced-command path is fixed end to end:

```text
disk_attribution
  -> sudo -n /usr/local/sbin/claude-disk-attribution-root
  -> python3 -I /usr/local/bin/claude-disk-attribution
```

The sudoers fragment grants only the argument-free root wrapper. The wrapper
rejects any argument before starting the Python pack.

## Interpretation

Compare two complete `disk_attribution` envelopes with the same
`catalog_sha256`. The difference for each top-level bucket identifies where
the root filesystem's named regular-file allocation changed.

Directory blocks, filesystem metadata, reserved blocks, and deleted files
that remain open are not attributed to a named regular file. Therefore:

```text
filesystem used delta - sum(bucket allocated deltas) = residual
```

A material residual is evidence for a narrower READ-ONLY follow-up; it must
not be silently assigned to the application.

## Staged deployment

1. Validate the Python pack, wrapper, sudoers fragment, dispatcher, and tests.
2. Install the pack as `/usr/local/bin/claude-disk-attribution` (`0755`, root).
3. Install the wrapper as `/usr/local/sbin/claude-disk-attribution-root`
   (`0755`, root).
4. Validate and install the sudoers fragment as
   `/etc/sudoers.d/claude-audit-disk-attribution` (`0440`, root).
5. Test the wrapper positively and verify argument rejection.
6. Install the reviewed dispatcher and submit one commit-bound request.

No service restart, deletion, compression, retention change, or permission
change under `/home/mathieu` is part of this procedure.

## Rollback

Restore the previous dispatcher, then remove only these three installed files:

```text
/usr/local/bin/claude-disk-attribution
/usr/local/sbin/claude-disk-attribution-root
/etc/sudoers.d/claude-audit-disk-attribution
```

Validate the complete sudoers policy after removal. No runtime data is touched.
