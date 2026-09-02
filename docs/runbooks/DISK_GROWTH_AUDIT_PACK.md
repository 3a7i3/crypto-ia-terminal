# Audit Pack `disk_growth`

## Purpose

`disk_growth` produces a bounded, READ-ONLY disk-allocation snapshot for the
runtime research infrastructure. It answers five narrow questions:

1. How much space and how many inodes are used on the root filesystem?
2. How many bytes are allocated below the fixed `databases/` and `logs/` roots?
3. Which first-level runtime buckets account for that allocation?
4. Which bounded set of regular files currently consumes the most allocated
   space?
5. Was the metadata scan complete, partial or stopped by a declared limit?

It does not open or hash file contents, parse JSON/CSV/log records, inspect
secrets, delete or rotate files, change retention, or claim that a large file
is unnecessary. Those decisions require separate evidence and governance.

## Scientific meaning of “growth”

A READ-ONLY pack must not create a baseline file on the VPS. Consequently,
one result is an attributable **snapshot**, not a growth rate. Growth is
calculated later by comparing two immutable GitHub envelopes:

```text
allocated_delta = current.allocated_bytes - previous.allocated_bytes
elapsed_seconds = current.observed_at_utc - previous.observed_at_utc
allocated_bytes_per_hour = allocated_delta * 3600 / elapsed_seconds
```

The comparison is valid only when both results:

- have `collection_status=complete`;
- have the same `schema_version` and `catalog_sha256`;
- contain the same root label and bucket name;
- have distinct, valid UTC observation timestamps.

The pack therefore emits `growth_computed=false` and a stable
`growth_method`. An AI may compute a delta from archived evidence, but must not
invent a baseline from memory or compare partial scans as if they were exact.

## Fixed observation scope

Version 1 scans exactly two immutable roots:

| Label | Fixed path | Purpose |
|---|---|---|
| `databases` | `/home/mathieu/crypto_ai_terminal/databases` | runtime scientific datasets and state |
| `logs` | `/home/mathieu/crypto_ai_terminal/logs` | runtime application logs |

Filesystem capacity is read only for `/`. The caller cannot select a path,
filename, depth, threshold or sort field. Changing the catalog requires a
reviewed code change and a governed VPS deployment.

## Metadata collected

For `/`, the pack uses Python `os.statvfs()` to report:

- total, used, free and unprivileged-available bytes;
- used percentage as integer basis points (`10_000 = 100%`);
- total, used and free inode counts;
- inode-used percentage in basis points.

For each fixed runtime root, it uses only `stat`, `lstat`-equivalent metadata
and `scandir` directory entries:

- logical and allocated regular-file bytes;
- regular-file, directory, symlink, special-entry and hardlink-duplicate counts;
- bounded first-level bucket totals;
- newest observed metadata modification timestamp;
- bounded largest-file metadata: root label, relative path, logical bytes,
  allocated bytes and modification timestamp;
- permission, metadata, depth, entry, mount-boundary and timeout counters.

Allocated bytes use `st_blocks × 512`. Logical bytes use `st_size`. Hardlinks
are counted once per root by `(device, inode)` so one inode is not presented as
multiple consumed allocations.

## Negative authority contract

The pack:

- accepts no arguments;
- contains no subprocess or shell execution;
- never calls `open()`, `read()`, `read_text()` or `read_bytes()` on runtime
  files;
- never follows a symbolic link;
- never descends into a mounted filesystem with another device identifier;
- never writes a local baseline, cache, lock or temporary file;
- never emits raw exception messages or file content;
- does not run as root and does not invoke `sudo`;
- performs no deletion, compression, rotation, truncation or permission change.

Relative filenames are metadata, not content. They are limited to 160 printable
characters. Unsafe or oversized relative names are replaced with
`path_sha256:<digest>`. Absolute paths can appear only for the two fixed roots
and `/`; discovered file records contain relative paths only.

## Hard bounds

| Bound | Version 1 value |
|---|---:|
| Fixed roots | 2 |
| Time per root | 8 seconds |
| Entries examined per root | 50,000 |
| Recursive depth | 12 |
| First-level buckets emitted per root | 24 plus one aggregate |
| Largest files emitted globally | 20 |
| Relative-path metadata | 160 characters |
| Total stdout | 24,000 UTF-8 bytes |

If the time, entry or depth boundary prevents a complete traversal, the pack
reports the corresponding counter/limit and returns partial evidence. It does
not silently extrapolate missing bytes.

## Function reference

### `utc_now()`

Produces the second-resolution UTC timestamp attached to the snapshot. It does
not inspect application data.

### `catalog_sha256(catalog)`

Hashes the ordered `(label, fixed_path)` catalog as canonical JSON. Matching
catalog hashes are mandatory for cross-run growth calculations.

### `safe_relative_path(relative_path)`

Allows a bounded printable relative path to enter the evidence. Absolute,
control-character or oversized values are replaced by a SHA-256 identifier.
The hash covers path metadata only, never file contents.

### `timestamp_utc(timestamp)`

Converts a numeric filesystem timestamp to second-resolution UTC. Unsupported
or out-of-range values become `unknown` rather than an exception string.

### `filesystem_observation(path)`

Reads capacity and inode counters with `os.statvfs()` for the fixed filesystem.
It normalizes failures to `not_found`, `permission_denied` or `query_error` and
does not expose raw operating-system errors.

### `_empty_bucket()`

Creates zeroed logical-byte, allocated-byte and regular-file counters for one
first-level bucket.

### `_add_file(bucket, file_stat)`

Adds one regular file’s `st_size` and `st_blocks` metadata to counters. It does
not receive a file handle and cannot read file bytes.

### `_offer_largest(largest, candidate)`

Maintains only the 20 largest regular-file metadata records, sorted first by
allocated bytes, then logical bytes and stable path identifiers.

### `_render_buckets(buckets)`

Emits the 24 largest first-level buckets and combines any remainder into
`[other_buckets]`. This preserves total bytes while bounding cardinality.

### `scan_root(spec, monotonic)`

Traverses one fixed root with `os.scandir()` and metadata-only `stat` calls. It
enforces timeout, entry, depth, symlink and mount boundaries; deduplicates
hardlinks; and returns the root record plus bounded largest-file candidates.

The scan is not an atomic filesystem transaction. Files may grow, rotate or
disappear while metadata is collected. Such errors are counted and make the
scan partial rather than being hidden.

### `_absent_root(spec, query_status, started, monotonic)`

Builds a zero-byte, content-free record for an absent, inaccessible or invalid
fixed root.

### `collect_snapshot(catalog, observed_at_utc, monotonic)`

Combines filesystem capacity, both root scans, global largest files, summary
counters, the catalog fingerprint and negative disclosure assertions. It
returns exit code `0` only when capacity and both traversals are complete.

An explicitly absent fixed root is a complete observation and is counted as
`missing_root_count`; a permission error, metadata error or enforced scan limit
makes the overall collection partial.

### `render_snapshot(payload)`

Renders deterministic sorted JSON and fails closed if stdout would exceed
24,000 UTF-8 bytes.

### `main(argv)`

Rejects all caller arguments, performs one observation, emits one JSON document
and returns its collection status. It offers no path-shaped escape hatch.

## Result interpretation

### Capacity

`filesystem.used_basis_points` is an observation, not an automatic incident.
Example: `8_500` means 85.00% used. Operational thresholds must be documented
separately before they can drive alerts or retention changes.

### Allocated versus logical bytes

- `allocated_bytes` estimates physical filesystem allocation and is the main
  field for disk-consumption growth;
- `logical_bytes` is the apparent file length and can be much larger for sparse
  files;
- a discrepancy is evidence to investigate, not proof of corruption.

### Largest files

The list is a bounded prioritization aid. It is not authorization to delete,
truncate, compress or rotate any file. Before modification, establish the
writer service, retention contract, scientific value, backup/rollback and a
runtime validation test.

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Complete capacity and root observation, including explicit missing roots |
| `64` | Caller attempted to supply an argument |
| `69` | Partial observation due to permission/error/time/entry/depth boundary |
| `70` | Rendered output would exceed the hard size ceiling |

The GitHub bridge archives the envelope before marking a non-zero remote action
as failed, so partial evidence remains attributable.

## Tests and negative guarantees

`tests/test_claude_disk_growth.py` verifies:

- the exact fixed root catalog;
- absence of content-read and process-execution primitives;
- content non-disclosure with a sentinel secret;
- symlink non-following and relative-only discovered paths;
- hardlink deduplication;
- explicit missing-root behavior;
- entry and timeout limits;
- path sanitization;
- deterministic bounded rendering;
- argument rejection before collection;
- explicit `growth_computed=false` and no local baseline.

`tests/test_vps_audit_request.py` verifies that `disk_growth` is present in the
request validator, workflow choice list, dispatcher and fixed pack source.

## Governed deployment and runtime certification

After merge:

1. Download the pack and dispatcher from the exact merge commit.
2. Verify independently supplied SHA-256 hashes and Python/Bash syntax.
3. Verify the current installed dispatcher and create one explicit backup.
4. Install the pack root-owned, mode `0755`, as
   `/usr/local/bin/claude-disk-growth`.
5. Run it once directly as `claude-audit` and print only its compact summary.
6. Install the matching root-owned dispatcher.
7. Submit one commit-bound `disk_growth` request through BRIDGE-04.
8. Certify envelope SHA, request hash, exit code, output size, catalog hash and
   negative disclosure contract.
9. Submit a second observation only after a meaningful interval; calculate
   growth from the two archived complete envelopes.

No service is restarted and no runtime file is created, opened for content,
rotated, truncated, compressed or deleted during deployment or certification.

## Rollback

Rollback restores the exact saved dispatcher and removes only
`/usr/local/bin/claude-disk-growth`. Deployment-specific mobile commands must
name the backup path explicitly. Wildcards and recursive deletion are not
permitted.
