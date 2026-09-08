# Canonical Operator API Contract

Mission O-02W-B · Base SHA `5aecc8859efb7dbeb5ba53177a926abaa43097c` ·
2026-09-06 · Documentation/architecture-only mission (no runtime code
changes, no UI, no API deployment, no Telegram, no VPS).

**R1 remediation (O-02W-B-R1, same date):** independent MASTER review
found three contract-level defects in the original text — (1) an
inaccurate claim that `observability/system_snapshot.py` already
implements the atomic-write pattern this contract proposes (it does
not; the actual precedent is `quant_hedge_ai/dashboard/live_snapshot.py`,
§1.2/§1.3/§18), (2) an overstated cross-process consistency guarantee
for the JSONL ledgers (§6.1 now defines an explicit byte-offset
watermark contract), and (3) no deterministic mechanism preventing a
stale post-restart snapshot from being presented as current runtime
truth (§14.1 now defines a runtime-instance manifest). All three are
corrected in place below; §22 adds the corresponding test requirements.
This remains documentation-only — no runtime source was changed to
make the contract true.

**R2 remediation (O-02W-B-R2, same date):** independent review of the
R1 solution found two further scientific-consistency defects, both now
corrected in place: (1) the R1-2 watermark model used `path`+`byte_
offset` as if a logical ledger path were a stable physical identity —
`scripts/rotate_jsonl.sh` (`mv` + `touch`) proves it is not, so §6.1 now
adds a `generation_id` and a precise binary-byte-offset requirement
(the R1 text's `f.tell()` reference was itself imprecise for a
text-mode file handle); (2) the R1-3 runtime manifest was described in
several places as proof the producer "is alive," conflating a one-time
identity declaration with an ongoing liveness signal — §14.2 now
separates `INSTANCE_RELATION` (identity/succession) from `LIVENESS`
(sourced independently from `system_health.boot_alive`). §22 gains five
corresponding test requirements (9-13). R1's three original corrections
are unchanged and not reverted.

**R3 remediation (O-02W-B-R3, same date):** independent review found the
R2-1 `generation_id` derivation itself conceptually insufficient — inode
alone does not detect a same-inode truncate-in-place, and a first-N-byte
content hash *recomputed on every read* is unstable during ordinary
append growth past N bytes. §6.1 now defines the canonical
`generation_id` as a stable opaque UUID/epoch **allocated once and
persisted** by a new §6.1.1 generation sidecar/metadata mechanism (an
observability identity mechanism only — never a database, daemon,
message bus, or decision component), with inode/content-hash demoted to
an explicitly labeled `LEGACY`/`BEST-EFFORT` fallback (§6.1.3) carrying
documented limitations. §6.1.2 adds the previously-missing governed-
truncate/reset invariant (new identity or explicit invalidation, never
silent retention) and classifies ungoverned destructive mutation as a
detected-and-invalidated integrity violation, not a silently-trusted
read. §22 gains five more test requirements (14-18). Neither the sidecar
nor any other runtime mechanism is implemented by this correction — it
remains a requirement for the future implementation mission. R1 and R2's
corrections are unchanged and not reverted.

**R3.1 micro-remediation (O-02W-B-R3.1, same date):** independent review
of R3 found three remaining defects, corrected in place: (1) §6.1's
closing sentence still called the mechanism "a read-side discipline,"
contradicting R3's own governed-lifecycle-metadata model — now described
as "governed ledger-lifecycle metadata publication plus read-side
validation"; (2) atomically replacing the sidecar record alone does not
atomically bind it to the ledger file it describes — a concrete
sidecar-lags-rotation race was possible — so §6.1.1 now adds a
`metadata_revision` and a `TRANSITIONING` lifecycle state, and new §6.1.4
defines the required governed transition (publish `TRANSITIONING` before
mutating, only then expose the new generation as `ACTIVE`) and reader
protocol (bind at open, `fstat()`-verify physical binding, re-check
before returning, reject/retry on any mismatch — device/inode used only
as a binding-verification observation, never as canonical identity);
(3) "one specific inode/file instance" was too narrow given
`rotate_jsonl.sh`'s own `gzip` step — `generation_id` now identifies one
logical content generation across successive physical representations
(plain then `.gz`), with `byte_offset` explicitly defined against the
canonical *uncompressed* byte stream, decompressed before a watermark is
ever applied to an archived `.gz` file. Test 17 is narrowed to the
specific detectable case (same-inode truncation below a confirmed
offset) rather than implying universal ungoverned-mutation detection;
tests 11 and 15 gain `TRANSITIONING`-interval and
rename/gzip-identity-preservation coverage respectively. R1/R2/R3's
corrections are unchanged and not reverted; still documentation-only.

**R4 remediation (O-02W-B-R4, 2026-09-07):** independent MASTER review
found ten further defects, all corrected in place below (re-reading
`core/advisor_loop.py`'s G8 gate, `_balance_provenance_from_mode()`,
`observability/runtime_provenance_snapshot.py`, `docs/audit/S-03D-
runtime-provenance-exposure.md`, `watchdog_vps.py`,
`observability/operator/domains/system_health.py`, `paper_trading/
mexc_simulator.py`'s `MexcPosition`/`MexcOrder`/`_restore_positions()`/
`_fill_market()`/`_check_positions()`/`get_open_positions_summary()`, and
the `decision_packets_YYYY-MM-DD.jsonl`/`black_box.jsonl` persistence
paths as fresh evidence): (A) the actual mandatory execution-
authorization gate is `DecisionPacket.is_actionable()`
(`_effective_trade_allowed = _dp_r.is_actionable()`, with a missing
packet failing closed to `False`), not "`SHADOW_CANDIDATE`" — the legacy
dict pipeline supplies analysis/blockers/gating inputs but is not the
sole final authority; historical §8/O-01-era language calling the legacy
pipeline "the actual execution driver" is now marked stale; (B) O-02W
must reuse/extend S-03's already-certified
`RuntimeProvenanceSnapshotWriter` (atomic tmp+`os.replace()`, PID,
invocation identity, uptime, `exposure_epoch_id`, sanitization) instead
of inventing a second, independent process-identity mechanism, and
`exposure_epoch_id` is an exposure/process epoch, never the
`CLEAN_DATA_SINCE` experimental epoch; (C) `git rev-parse HEAD` alone is
only a claimed checkout/source SHA — it proves nothing about worktree
cleanliness, deployed-file match, or process-memory match, and must
never be called "the SHA actually running"; (D) `watchdog_vps.py` does
`pgrep` and only logs a debug line when alive — it does not publish any
positive, independently-readable liveness snapshot, so canonical runtime
liveness exposure remains `NOT_EXPOSED` today; (E) mode provenance must
reuse `core/advisor_loop.py::_balance_provenance_from_mode()` (vocabulary
`PAPER`/`REAL_API`/`TESTNET_API`/`UNKNOWN`, fail-closed to `UNKNOWN`,
`PAPER_TRADING_ENABLED` override preserved) rather than describing
`WalletSync.mode` as copied "verbatim"; (F) `MexcPosition` restore sets
`personality="restored"` but never passes `regime` (defaults
`"unknown"`); `current_price` is never stored on `MexcPosition` —
`get_open_positions_summary()` fetches it at read time via
`_fetch_price()`, whose `0.0` return means unavailable price evidence,
not a valid mark price; (G) pipeline-stage availability must distinguish
`CONTRACT_EXISTS`/`RUNTIME_PRODUCER_EXISTS`/`RUNTIME_EXPOSURE_EXISTS` —
the existence of `PIPELINE_STAGES`/`StageObservation`/
`compose_decision_pipeline_snapshot()` is not itself runtime exposure;
(H) `decision_packets_YYYY-MM-DD.jsonl` (DecisionPacket history) and
`black_box.jsonl` (BlackBox outcome/provenance evidence) are two
distinct ledgers, each needing its own source label/freshness/watermark
— `black_box.jsonl` is not a substitute for DecisionPacket history; (I)
§21's `MINIMUM_IMPLEMENTATION_MISSION` is rewritten to define O-02W-C —
an advisor-owned passive snapshot *builder* only — as the sole next
mission, explicitly excluding FastAPI/HTTP/WebSocket/React/cockpit/auth/
VPS/systemd/certification work, deferred to O-02W-D/O-02W-E/T-1/
O-02W-F; (J) F-00 has not started and is not O-02W-B, O-02W-C, or any
cockpit-implementation mission — "before/after F-00" cockpit language is
replaced with explicit O-02W-C/O-02W-D/O-02W-F sequencing. §1, §3, §5,
§7, §8, §9, §10, §14-§15, §17, §18, §19-§22 and the
`REQUIRED_FIELD_CONTRACT_TABLE` are corrected below; all R1-R3.1
corrections (atomicity, watermark/generation model, instance-vs-liveness
split) are preserved and not regressed. Still documentation-only — no
runtime source was changed to make the contract true.

**R4.1 remediation (O-02W-B-R4.1, 2026-09-07):** a fresh independent
MASTER review (`O02WB_REQUEST_CHANGES`, not architectural — the cockpit
architecture is not redesigned) found six residual consistency defects
in R4's text, all corrected in place below, with two files re-read as
fresh evidence (`paper_trading/mexc_simulator.py`'s `_check_positions()`/
`_total_equity()`/full `MexcPosition` field list, and
`governance/decision_trace.py` in full): (A) §2.1's speculative "a second
process... would show `current_price == entry_price`" line was not
grounded in source — re-reading `_check_positions()`/`_total_equity()`
confirms `MexcPosition` has no `current_price` field at all (not merely
unpopulated); the monitor loop fetches price locally per tick only to
update stored `mae_pct`/`mfe_pct` extrema and decide TP/SL/TIMEOUT
closure, never persisting a price/PnL field, and `_total_equity()`'s own
entry-notional fallback (`equity += p.qty_usd` when price is
unavailable) is a real but narrowly-scoped equity-sum behavior, not a
`current_price` field's fallback — §2.1 and §2.3 are corrected to state
this precisely and remove the unsupported claim; (B) the process-identity
model (S-03 `exposure_epoch_id` vs. `process_instance_id` vs.
`operator_runtime_manifest.json`) is resolved into one deterministic
ownership/propagation model with an explicit equality invariant
(`S03.process.process_instance_id == operator_snapshot.process_instance_id
== operator_manifest.process_instance_id`), added to §15; (C) §14's
ATOMICITY_CONTRACT table still carried a standalone required `runtime_sha`
field, contradicting §15's already-renamed `source_sha`/`worktree_state`/
`runtime_sha_evidence_status` model — the §14 row is corrected to point
at, not redefine, the §15 model, and `runtime_sha` is retired terminology
from here on; (D) §14.2's liveness model already correctly classified
current liveness `NOT_EXPOSED`/`UNKNOWN`-only — an explicit negative
invariant and test (28) are added rather than leaving it only as prose;
(E) §22 gains ten new numbered test requirements (23-32) covering the
builder-boundary/fail-passive/price-unavailability/provenance/missing-
packet/liveness/process-identity-equality/no-second-identity/no-secrets/
no-fabricated-`trace_id` cases the mission-assignment table already
implied but had not yet enumerated, each assigned to its correct mission
(O-02W-C, O-02W-D, or T-1) without moving any FastAPI/HTTP/WebSocket/
React/auth/VPS/systemd/certification work into O-02W-C; (F) `trace_id` is
resolved from `PARTIALLY_AVAILABLE`/"pending source inspection" to a
final `NOT_EXPOSED_AS_DISTINCT_FIELD` classification, backed by a full
read of `governance/decision_trace.py` (a pure text-formatting consumer
that establishes no separate trace identity) — §4/§8/§19/§20 are
reconciled to state this consistently and remove all remaining
pending-verification language for this specific question. R1-R4's
corrections are unchanged and not reverted. Still documentation-only —
no runtime source was changed to make the contract true; the two files
re-read above were read, not modified.

**R4.2 remediation (O-02W-B-R4.2, 2026-09-07):** R4.1 was not fully
consistent — it supplemented several sections with corrected text but
left older contradictory sentences standing alongside it. This MINIMAL
pass removes those residual sentences in place, without adding a new
parallel explanation section: (A) the process-identity model in §15/
§21.1/test 30 no longer says S-03 is a "shared RuntimeIdentity source"
or that fields are "produced by (or reconciled with)"/"reuses/
reconciles" S-03 — the advisor bootstrap is now stated as the sole
identity authority and the S-03 writer as a passive consumer/projection
throughout; (B) §14/§15/the field table now define and use the
previously-missing `deployment_evidence` schema field as a fourth
envelope field (source_sha/worktree_state/deployment_evidence/
runtime_sha_evidence_status), removing the stale "three envelope
fields" wording; (C) §13's freshness table and the
`REQUIRED_FIELD_CONTRACT_TABLE`'s `system_health.liveness` row no
longer claim a current "existing watchdog" source or a bare "Watchdog
unreachable -> UNAVAILABLE" — both now state today's `NOT_EXPOSED`/
`UNKNOWN`-only reality separately from the future-only independent-
publisher case, and test 28 is split by owning mission (O-02W-C/
O-02W-D/T-1); (D) §5's restored-position regime row now specifies the
exact `pos_id == trade_id` join (symbol as post-join check only, never
a fallback), replacing the "by trade_id/symbol"/"API should prefer that
join" wording, and clarifies the enrichment belongs to the O-02W-C
producer, not the API; (E) §8's trace_id authority cell no longer says
"Same as packet_id" — it now reads `NOT_EXPOSED_AS_DISTINCT_FIELD`,
matching the classification already established. R1-R4.1's corrections
are unchanged and not reverted; still documentation-only.

**R4.3 remediation (O-02W-B-R4.3, 2026-09-07):** MASTER found three residual
contradictions left standing by R4.2's text, all corrected in place: (A)
§19's `MexcPosition.regime` row still said the API could join by
`trade_id`/`symbol` and perform the enrichment itself — it now states the
same exact `pos_id == trade_id` join, `symbol` as post-join check only, and
O-02W-C-owned enrichment already established in §5/test 26; (B) §22's
mission-assignment table row for test 28 still said the test belonged only
to "O-02W-D or T-1 — not O-02W-C," contradicting test 28's own three-way
split body — the table row now states the same O-02W-C/O-02W-D/T-1 split;
(C) the §5 `current_price` row and the `REQUIRED_FIELD_CONTRACT_TABLE`
`current_price` row still allowed `STALE` as a current-source outcome
(`UNAVAILABLE`/`STALE`, "STALE if no fresh tick since position restore") —
both now state `_fetch_price() == 0.0` maps only to `UNAVAILABLE` today,
`STALE` is `FUTURE_ONLY` pending a verifiable market-source timestamp, and
restore time must never be used to infer price staleness, matching test 25.
R1-R4.2's corrections are unchanged and not reverted; still
documentation-only.

**R4.4 remediation (O-02W-B-R4.4, 2026-09-08):** independent MASTER review
found four residual contradictions in R4.3's text, all corrected in place:
(A) `system_health.boot_alive` and `system_health.liveness` were exposed
as two separate serialized fields with contradictory freshness rules
(§13 said a future stale/unreachable publisher may produce `UNAVAILABLE`;
§14.2 and `REQUIRED_FIELD_CONTRACT_TABLE`'s `liveness` row said
`UNKNOWN`; test 28 implied the API "preserves" a snapshot-carried
`liveness` value from an independent external publisher never owned by
the snapshot) — `system_health.liveness` is retired as a serialized
field; `system_health.boot_alive: ObservedValue[bool]` is now the sole
canonical liveness field, with one deterministic value/semantics mapping
(`UNKNOWN` today; future `PRESENT`/`FALSE`/`UNAVAILABLE`/`STALE`) stated
once in §14.2 and reused verbatim by §10, §13, §17,
`REQUIRED_FIELD_CONTRACT_TABLE`, and tests 13/28; `LIVENESS` remains a
conceptual axis name only; (B) §22's mission-assignment table assigned
tests 19-20 only to "O-02W-D or T-1," leaving the O-02W-C producer
artifact untested for false runtime-proof claims — tests 19-20 and the
mission table now assign producer-side tests to O-02W-C, preservation-
only tests to O-02W-D, and the future verification-mechanism test to
T-1; (C) §6.1's binding requirement 6 said `generation_id` MUST change
when a ledger is "replaced, truncated, or rotated," broader than the
R3.1 logical-generation model and inconsistent with tests 14-17 — reworded
to the exact rule (new generation on new active logical content;
retained generation keeps its ID through rename/gzip; physical-
representation-only changes never create a new generation); (D) §17's
SYSTEM panel row promised the operator could "tell if the machine is
even running" while the same row said `boot_alive` remains
`NOT_EXPOSED` — corrected to state O-02W-D may render system
health/identity/freshness and an honest `boot_alive` `UNKNOWN` state,
never a liveness-determination claim, which remains gated on T-1. R1-R4.3
corrections are unchanged and not reverted; still documentation-only.

**R4.5 remediation (O-02W-B-R4.5, 2026-09-08):** independent review found
residual passages still deferring the future independent liveness
publisher to "O-02W-D, or T-1" / "O-02W-D/T-1" / "post-O-02W-D/T-1"
(§14.2, its canonical mapping table, and the `REQUIRED_FIELD_CONTRACT_
TABLE`'s `system_health.boot_alive` row), contradicting R4.4's own
correctly-stated final mission allocation. All are corrected in place to
one owner: **T-1 alone** implements the independent liveness publisher;
O-02W-C only ever serializes `value=null`/`UNKNOWN`; O-02W-D, before T-1
exists, exposes that `UNKNOWN` state honestly and never builds the
publisher; after T-1 integration, the API reads T-1's independent
artifact and maps it into `system_health.boot_alive`. Test 28 and its
mission-assignment table row are now phase-explicit (O-02W-C /
O-02W-D-pre-T-1 / T-1-integration) rather than describing O-02W-D as
"preserving whatever value the snapshot carries" in a single enduring
statement that blurred the pre-T-1 and post-T-1 cases. R1-R4.4
corrections are unchanged and not reverted; still documentation-only.

This document is the authoritative source-inspected contract for a future
read-only "operator API" serving the React cockpit (`frontend/`). It
supersedes no code — it constrains what a future implementation mission
(§21, `MINIMUM_IMPLEMENTATION_MISSION`) is allowed to build. Every claim
below is traceable to a file actually read for this mission; where
something does not exist or is not instrumented, it is stated plainly
(`NOT_EXPOSED`, `CONTRACT_EXISTS` / `RUNTIME_PRODUCER_EXISTS` /
`RUNTIME_EXPOSURE_EXISTS` distinctions per domain).

This mission builds directly on **Mission O-01**
(`docs/observability/OPERATOR_OBSERVABILITY_ARCHITECTURE.md`,
`observability/operator/*`) — eleven canonical observation domains, a
shared `DomainSnapshot`/`ObservedValue`/`FreshnessStatus` contract, and a
32-metric registry (`docs/observability/METRIC_DICTIONARY.md`). O-01
ships contracts only, no runtime wiring; the "known gaps" it records
(§10 of that document) are carried forward here verbatim where relevant,
not silently re-solved.

Compliance note (per `CLAUDE.md`): Phase II — Validation Scientifique is
in force; this document is measurement/audit/documentation tooling, not
a new feature, indicator, strategy, or decision rule. It proposes zero
new signal, zero new threshold, zero change to `core/advisor_loop.py`,
and zero VPS/Telegram wiring. The STABILIZATION LAB window
(`docs/governance/STABILIZATION_WINDOW_2026-09-03_2026-09-16.md`) is
unaffected: nothing here reads or writes runtime state.

---

## 1. CANONICAL_OPERATOR_ARCHITECTURE

### 1.1 Target architecture

```
AUTHORITATIVE MACHINE SOURCES (process-local objects, JSONL ledgers, JSON packs)
   core/advisor_loop.py (analyze_symbol; G8 gate:
        _effective_trade_allowed = DecisionPacket.is_actionable() — the
        mandatory execution-authorization gate; missing packet fails
        closed to no-order. Legacy dict pipeline (blockers/trade_allowed)
        supplies analysis/gating inputs into this decision, it is not
        itself the sole final authority — see §8)
   paper_trading/mexc_simulator.py::MexcSimulator._positions   (in-memory, process-local)
   infra/wallet_sync.py::get_wallet_sync()                     (in-memory singleton, process-local)
   paper_trading/recorder.py -> databases/paper_trades.jsonl   (disk, append-only)
   tools/regret_repository.py -> databases/regret_*.jsonl      (disk)
   observability/rejection_store.py -> databases/*.jsonl       (disk)
   observability/system_snapshot.py::SystemSnapshot            (in-memory + periodic JSON dump)
        |
        v
CANONICAL OBSERVABILITY MODULES (existing, wrapped, not duplicated — O-01)
   observability/operator/domains/*.py  compose_*_snapshot()
        |
        v
CANONICAL OPERATOR SNAPSHOT/PROJECTION  (producer-owned, materialized OUTSIDE
   the advisor process's own address space — this is the NEW layer this
   mission specifies; nothing here is implemented yet)
        |
        v
READ-ONLY OPERATOR API  (separate FastAPI process; GET + optional read-only WS)
        |
        v
REACT COCKPIT  (frontend/)
```

### 1.2 Transport options evaluated

The producer process (`core/advisor_loop.py`, or a small in-process
publisher it owns) and the API process are, by construction (§2), two
separate OS processes. The API process cannot read the producer's Python
heap directly. Options considered, per the brief's bounded list:

| Option | Verdict | Rationale |
|---|---|---|
| **Atomic JSON snapshot file (single file, atomic rename)** | **SELECTED** | **Correction (R1-1):** `observability/system_snapshot.py` itself does *not* implement this — it is a pure in-memory `@dataclass` model (`SystemSnapshot` and friends) with no file I/O of its own (confirmed by reading the full file: its only disk write is an unrelated `_lifetime` JSON dump, not atomic, not the live snapshot). The actual atomic-write implementation precedent already in production is `quant_hedge_ai/dashboard/live_snapshot.py::write_snapshot()` — `tmp = path.with_suffix(".tmp"); tmp.write_text(...); tmp.replace(path)` (equivalent to `os.replace()`), called from `core/advisor_loop.py` once per cycle to produce `databases/live_snapshot.json`, which `visualization/api/system_snapshot_source.py` then reads (embedding a `system_snapshot` dict built from `SystemSnapshot`'s fields). This existing writer is genuine **implementation precedent/helper** for the pattern this contract selects — not evidence that `SystemSnapshot` itself is atomic, and not something this contract assumes is reused verbatim (§14 defines additional identity/atomicity fields it does not currently write). The NEW canonical operator snapshot writer this contract specifies is a distinct, new O-02W-B publication mechanism modeled on `live_snapshot.py`'s proven tmp-write-then-replace pattern, not an extension of `system_snapshot.py`. Zero new daemon, zero new dependency, low overhead (periodic write, not per-request). |
| Multiple domain snapshot files (one JSON per O-01 domain) | REJECTED (as *sole* mechanism) but compatible as an internal detail | O-01's own domain decomposition (§4) argues for per-domain freshness/composition, but multiple files reintroduces the exact "impossible cross-cycle mixture" risk this contract must prevent (§14, ATOMICITY_CONTRACT) unless every file shares one `snapshot_id`/`cycle` and the API refuses to compose across differing ids. Acceptable *inside* the single-envelope option (§1.3) as a serialization detail, not as the transport itself. |
| Append-only event stream + snapshot | REJECTED for this contract's scope | Real value for DECISION_API history (decision packets are already an event-sourced hash chain, §8) and for TRADE_API history (JSONL ledger already is this). Not needed as the *primary* transport for point-in-time domain state — adds operational complexity (offsets, replay, compaction) with no freshness/atomicity benefit over a snapshot file for state that is naturally "current value," not a stream. The existing JSONL ledgers already give append-only history for trades/decisions; no new bus is required to expose them read-only. |
| Local Unix domain socket (advisor process serves a socket, API process is a client) | REJECTED | Requires the advisor process to run a server loop and accept connections — a scope/coupling increase inside `core/advisor_loop.py`, explicitly forbidden by this mission ("do NOT modify advisor_loop.py"). Also reintroduces liveness coupling: if the advisor process stalls mid-request, the API blocks: the opposite of "low runtime overhead" and "read-only web process independent of producer liveness." |
| Loopback read-only HTTP (advisor process exposes an internal HTTP endpoint, API process proxies it) | REJECTED | Same objection as the socket option — it requires the producer process to run an HTTP server, which is new functional surface inside or beside the trading engine, not a passive observer. It also duplicates the API layer this mission is defining one process too early. |
| Other existing safe mechanism (SQLite / shared file-lock DB) | REJECTED for the *hot* live-state path, ACCEPTABLE unchanged for what already uses it | The existing JSONL ledgers (`paper_trades.jsonl`, `regret_*.jsonl`, `black_box.jsonl`) already are this mechanism for historical/append-only data and should be read directly (§6), subject to the generation-aware watermark discipline in §6.1 (not "as-is" without qualification — append-only alone does not make a rotating ledger a safe multi-reader point-in-time source). Introducing a new SQLite file for *live* snapshot state would be a new storage technology for no benefit over a JSON file already atomic-rename-capable. |

### 1.3 Selected design

**One canonical JSON snapshot file per producer process, atomically
written (tmp file in the destination directory + `os.replace()` or the
equivalent `Path.replace()`), read-only-mounted by the API process. This
is a NEW O-02W-B publication mechanism** — it does not exist today as a
canonical-operator-envelope writer. It is modeled on, and may directly
reuse, the proven tmp-write-then-replace helper already in production at
`quant_hedge_ai/dashboard/live_snapshot.py::write_snapshot()` (implementation
precedent, §1.2), extended with the O-01 domain envelope and the
identity/atomicity/invalidation fields defined in §14-§15. The producer
(the advisor-loop process, or a narrow in-process "operator snapshot
writer" it calls once per cycle — not a new decisional component, purely
a serializer) is the only writer. The API process only ever opens the
file read-only, never imports `MexcSimulator`, `WalletSync`, or
`core/advisor_loop.py` (§ PROCESS_BOUNDARY_VERDICT). Historical/ledger
data (trades, decisions, regret events) continues to be read directly
from its existing JSONL files by the API process, subject to the explicit
read-consistency/watermark contract in §6.1 — those files are
append-only, but append-only is **not** the same guarantee as an atomic,
reproducible point-in-time multi-reader snapshot (see §6.1 for why, and
for the required boundary/watermark mechanism).

**Precise atomic-write requirements** (the write side of this
mechanism, binding on the future implementation mission):

1. The temporary file MUST be created in the same directory as (and
   therefore the same filesystem as) the destination path — a
   cross-filesystem temp location makes the final rename non-atomic on
   POSIX. `live_snapshot.py`'s `path.with_suffix(".tmp")` already
   satisfies this by construction; the new writer must preserve that
   property.
2. The full snapshot payload MUST be completely serialized to the
   temporary file (and the temp file closed) before the replace step —
   no partial/streamed write is replaced mid-flight.
3. The temp-to-final swap MUST use `os.replace()` (or the `pathlib`
   equivalent `Path.replace()`, which wraps it) — not `os.rename()` on
   platforms where rename is not guaranteed atomic when the destination
   exists (POSIX `rename()` is atomic and always replaces; Windows is
   not, which `os.replace()` handles portably; this repo's runtime is
   POSIX-only per its VPS deployment model, but the contract specifies
   `os.replace()` for correctness regardless).
4. If serialization fails (exception during `json.dumps`/`write_text`)
   before the replace step, the previous valid snapshot file MUST remain
   untouched — this falls out for free from the tmp-then-replace design
   *as long as the writer never opens the destination path directly for
   writing*; the implementation mission must preserve this ordering
   (serialize to tmp fully, replace only on success) exactly as
   `live_snapshot.py::write_snapshot()` already does (its `except`
   branch logs and returns without touching `path`).
5. **Durability vs. reader-atomicity — do not conflate them.** This
   contract's guarantee is **reader atomicity only**: no reader ever
   observes a half-written file, because `os.replace()` is atomic with
   respect to concurrent `open()` calls on POSIX. This contract does
   **not** guarantee crash durability of the *last* write — without an
   explicit `os.fsync()` on the temp file descriptor before `replace()`,
   and a directory `fsync()` on the containing directory after it, a
   host power-loss or kernel panic between `write_text()` and the next
   `fsync` boundary can lose the most recent write while still leaving a
   valid (if one-cycle-stale) snapshot on disk — this is acceptable for
   this contract's purpose (an observability/cockpit projection, not a
   durability-critical ledger; the JSONL ledgers remain the durability-
   critical sources, §6.1) but must not be described as crash-durable.
   `live_snapshot.py::write_snapshot()` today does **not** call `fsync`
   at either level — confirmed by reading the full function body — so
   if the implementation mission wants process-crash durability
   (surviving an unclean producer restart with zero data loss on the
   *last* cycle) it must add `os.fsync()` calls explicitly; if it only
   needs "readers never see torn JSON," the existing `tmp.replace()`
   step alone already provides that, with no code change required
   beyond what `live_snapshot.py` already does.

This satisfies every criterion in the brief:
- **Process isolation** — API process never touches producer memory.
- **Reproducibility** — one file = one immutable point-in-time state for
  the *live* domains it carries; a copy of the file plus the ledger
  watermark fields defined in §6.1 (not "referenced ledger offsets" in
  the abstract — see §6.1 for the concrete field) fully reproduces what
  the operator saw, including which historical events were and were not
  in view.
- **Freshness** — `generated_at_utc` + per-domain `freshness` (O-01) let
  the API/cockpit compute staleness without guessing.
- **Atomicity** — `os.replace()` on POSIX is atomic; readers never see a
  half-written file (reader-atomicity only — see the durability caveat
  above); §14 defines the identity fields that let the API detect and
  refuse a torn cross-cycle read even without OS-level torn reads (e.g.
  a slow NFS mount, not applicable to a local VPS disk but documented
  defensively), and §14.1 defines how a stale post-restart snapshot is
  prevented from being presented as current.
- **Restart safety** — file persists across producer restarts; API
  serves the last-known snapshot labeled `LAST_KNOWN` (never `CURRENT`)
  per §14.1's restart-invalidation model, with its true (aging)
  freshness rather than fabricating a fresh empty one.
- **Read-only web process** — the API process opens no write handle to
  producer state, ever.
- **Low runtime overhead** — one JSON write per cycle (comparable to
  `live_snapshot.py`'s existing cost profile), no new network service,
  no new message broker.

No new message bus is introduced. This is a deliberate, evidence-backed
minimality choice per the brief's explicit constraint.

---

## 2. PROCESS_BOUNDARY_MAP

### 2.1 `MexcSimulator` (`paper_trading/mexc_simulator.py`)

Read: `paper_trading/mexc_simulator.py` (constructor, `start()`,
`_restore_positions()`, position dict usage throughout).

- `self._positions: dict[str, MexcPosition]` (line 267) is a **plain
  Python dict on the instance** — pure in-process heap state. There is
  exactly one `MexcSimulator` instance created by the advisor runtime
  process; nothing persists `_positions` to disk as a live structure.
- `_restore_positions()` (called from `start()`) rebuilds an
  *approximation* of open positions from `paper_trades.jsonl` (via
  `paper_trading/recorder.py::get_recorder().trades()`) — but only at
  process start, and only entry-side fields (`entry_price`, `tp_price`,
  `sl_price` computed from fixed 4%/2% assumptions, not the live TP/SL
  the original order actually carried — see `_restore_positions()`
  lines ~410-448).
- **Correction (R4.1/BLOCKER A precision pass — re-reading `_check_
  positions()`, `_total_equity()`, and the full `MexcPosition` field
  list).** `MexcPosition` (dataclass fields: `pos_id`, `symbol`, `side`,
  `qty_usd`, `entry_price`, `tp_price`, `sl_price`, `fee_entry_usd`,
  `score`, `personality`, `regime`, `opened_ts`, `exit_price`,
  `closed_ts`, `pnl_usd`, `pnl_pct`, `close_reason`, `mae_pct`,
  `mfe_pct`) has **no `current_price` field at all** — confirmed by the
  full field list, not merely absent from a partial read. `_positions`
  holds **position state** (entry terms, close/exit bookkeeping,
  MAE/MFE extrema), never a continuously-stored live mark price or
  unrealized PnL. The monitor loop's `_check_positions()` calls
  `_fetch_price(sym)` **locally, once per tick**, purely to (a) update
  the position's stored `mae_pct`/`mfe_pct` extrema via
  `pos.live_pnl_pct(price)`, and (b) decide TP/SL/TIMEOUT closure — it
  never assigns the fetched price to any durable field on the position
  object. `_total_equity()` similarly fetches price locally for a
  mark-to-market equity sum and, **when `_fetch_price()` returns `0` or
  less, falls back to valuing that position at its entry-notional
  (`equity += p.qty_usd`)** for the equity aggregate only — this is a
  real, source-confirmed fallback, but it is scoped to the internal
  equity-sum calculation, not a `current_price` field on `MexcPosition`
  (no such field exists to fall back on). Neither method establishes a
  durable `current_price`/unrealized-PnL field on the position; both are
  read-time-only computations discarded at the end of each tick.
- **Verdict:** a second process instantiating `MexcSimulator()` fresh
  gets `_positions == {}` until (if ever) it independently reconstructs
  approximate entry-side state from the ledger, and even then it has no
  live market price feed of its own wired in this mission's scope, and
  no way to recover the first process's in-memory `mae_pct`/`mfe_pct`
  extrema (never persisted). **This is exactly the failure mode the
  mission brief warns about**: the second process would present empty/
  incomplete state, not the real running machine's in-memory history.

### 2.2 `WalletSync` (`infra/wallet_sync.py`)

Read: `infra/wallet_sync.py` (full file, 264 lines) and
`get_wallet_sync()`.

- `_singleton: Optional[WalletSync]` (line 223) is a **module-level
  global in the Python interpreter of whichever process imports
  `infra.wallet_sync`**. A separate OS process runs a separate Python
  interpreter with its own, independently-`None`-initialized
  `_singleton` — `get_wallet_sync()` in that process constructs its
  *own* `WalletSync()`, never the advisor process's instance. Python
  singletons do not cross `fork`-less process boundaries (no shared
  memory here — this is a plain FastAPI process started independently,
  not a fork of the advisor process).
- **Nuance found on inspection (important, non-obvious):** in **paper
  mode**, `get_balance()` (lines 166-191) is *effectively* cross-process
  safe in practice, because it recomputes `self._base_capital() +
  _read_ledger_pnl()` from disk (`_PAPER_CAPITAL` = `WALLET_PAPER_CAPITAL`
  env var, `_read_ledger_pnl()` re-reads `databases/paper_trades.jsonl`
  from scratch every call) rather than returning cached in-memory state.
  A second process's own fresh `WalletSync(mode="paper")` singleton
  would compute the *same* number, **provided it is told `mode="paper"`**
  — `mode` itself is a constructor parameter, not derived from any
  shared state, so the second process must be independently configured
  with the correct mode (§7, MODE_PROVENANCE_CONTRACT).
- In **live/testnet mode**, `_x` (capital X, set once via `bootstrap()`
  against the real exchange API at startup) and the `_last_value`/
  `_last_fetch_ts` cache (TTL `WALLET_CACHE_TTL_S`, default 30s) **are**
  process-local and not derivable without an independent
  `bootstrap()`/API call from the second process — which would be a
  second, uncoordinated read of the same real exchange account (safe
  read-only, but not a reflection of the running advisor's cached
  value, and doubles exchange API load).
- `_paper_session_pnl0` (session baseline, used only by
  `session_pnl_since_restart()`, explicitly "affichage uniquement" per
  the module's own docstring) is inherently per-process-lifetime and
  **must never be treated as canonical** by a second process; it is a
  display-only convenience counter, not sizing input, and is out of
  scope for any cross-process contract.
- **Verdict:** paper-mode `get_balance()` is derivable by re-implementing
  the same disk read (or, simpler and required by this contract, by
  having the producer materialize the already-computed number into the
  snapshot — see §2.3). Live/testnet-mode balance and the boot-time
  capital `X` are **not** safely re-derivable by a second process and
  **must** be materialized by the producer.

### 2.3 What MUST be materialized by the producer process

| State | Process-local? | Materialization required |
|---|---|---|
| `MexcSimulator._positions` (open paper positions — entry terms, MAE/MFE extrema; **no stored current_price/unrealized PnL field**, §2.1/BLOCKER A) | YES — pure heap state | YES — producer writes the full open-position list into the canonical snapshot every cycle, including a read-time-materialized mark price (via the same `_fetch_price()` call `get_open_positions_summary()` already makes, §5) computed fresh at materialization time, not read out of a stored field that does not exist. |
| `WalletSync.get_balance()` result (paper mode) | Effectively no (re-derivable from disk), but only if `mode` is externally known | YES anyway, for a single point of truth and to avoid the API re-implementing wallet arithmetic (reuse-before-creation, O-01 principle §6) |
| `WalletSync.get_balance()` result (live/testnet mode), `WalletSync.capital_x` | YES — in-memory cache + one-time bootstrap value | YES — mandatory; no safe re-derivation without an independent, uncoordinated exchange API call |
| `WalletSync.mode` | YES — constructor parameter of the process's own singleton | YES — must be carried in the snapshot as explicit provenance (§7) |
| Realized PnL, closed trade history | NO — already disk-resident (`databases/paper_trades.jsonl`, append-only) | NO — API may read the ledger file directly; producer need not re-publish it, though a denormalized summary in the snapshot is convenient (not required for correctness) |
| `DecisionPacket` current/latest state per symbol | YES — held by `core/decision_packet.py`'s in-memory state machine during a decision's lifecycle | YES for "latest live decision"; history is already recoverable from whatever sink persists closed packets (see §8) |
| `SystemSnapshot` (`observability/system_snapshot.py`) | Partially — already periodically dumped to JSON today (`visualization/api/system_snapshot_source.py` reads that dump) | Already solved by the existing pattern; the new canonical snapshot should supersede/wrap it, not duplicate a second competing dump |
| Regret v2 state (`tools/regret_repository.py`) | NO — disk-resident JSONL, `diagnostics()`/`freshness()` are pure reads over files | NO — API may call the same read-only functions directly, in-process, since they do not touch the advisor's live objects |
| Rejection/attrition counts (`observability/rejection_store.py`) | NO — disk-resident | NO — same as above |

---

## 3. SOURCE_TO_EXPOSURE_MATRIX

| Field/domain | Scientific source | Producer process | Current exposure | Target exposure | Cross-process-safe? | Freshness source |
|---|---|---|---|---|---|---|
| Paper open positions (full detail) | `paper_trading/mexc_simulator.py::MexcSimulator._positions` | advisor process only | None (no live API today) | Canonical snapshot, per-cycle | NO (must be materialized, §2.3) | snapshot `generated_at_utc` / cycle |
| Paper equity (paper mode) | `infra/wallet_sync.py::WalletSync.get_balance()` | advisor process (or any process, paper mode only) | `visualization/api/portfolio_api.py` (hardcoded 0.0, defective) | Canonical snapshot | Effectively yes if mode known, but materialize anyway (§2.3) | ledger mtime |
| Real account equity/free/staleness | `observability/real_accounts.py::RealAccountsObserver` | advisor process (poll cadence per notify cycle) | Telegram text block only (never summed with paper — guardrail) | Canonical snapshot, `real_account_*` fields, `NOT_APPLICABLE` if unconfigured | NO for live cache freshness (§2.2) | `RealAccountsObserver` poll timestamp |
| Realized PnL / closed trades | `paper_trading/recorder.py` -> `databases/paper_trades.jsonl` | any process (file read) | None dedicated (portfolio_api.py substitutes open PnL) | Direct ledger read by API, or denormalized in snapshot | YES (append-only JSONL) | file mtime / last CLOSE `ts` |
| DecisionPacket / DecisionObservation (latest, per symbol) | `core/decision_packet.py`, `observability/decision_observation.py` | advisor process | `sdos_terminal/api/app.py::/api/decision/{packet_id}` (DecisionTrace) | Canonical snapshot (latest) + existing trace endpoint (history) | Latest: NO (in-memory during lifecycle); history: depends on packet persistence sink | per-decision `observed_at_utc` |
| `DecisionPacket.is_actionable()` gate (G8, `_effective_trade_allowed`) — mandatory execution-authorization gate | `core/advisor_loop.py::analyze_symbol()` G8 block (~lines 6093-6195) | advisor process | Not exposed over HTTP; drives Telegram/exec only | Canonical snapshot, `decision_pipeline` domain, explicitly labeled `EXECUTION_AUTHORITY` | NO | per-cycle |
| Legacy dict pipeline verdict (`trade_allowed`, `blockers`) — analysis/gating input to the G8 gate, not itself the sole authority (stale historical O-01 comment called it "the actual execution driver"; superseded by the G8 correction above) | `core/advisor_loop.py::analyze_symbol()` | advisor process | Not exposed over HTTP; feeds the G8 gate + Telegram | Canonical snapshot, `decision_pipeline` domain, labeled `OBSERVATIONAL_TELEMETRY` (gating input), never `EXECUTION_AUTHORITY` on its own | NO | per-cycle |
| Pipeline stage counts (attrition) | `observability/rejection_store.py` | any process (file read) | `visualization/api/pipeline_api.py` (narrow, uses `n_signals = n_refused + n_traded`, flagged non-canonical by this mission) | Canonical snapshot via `observability/operator/domains/attrition.py` vocabulary | YES (disk) | RejectionStore record timestamps |
| Regret v2 state | `tools/regret_repository.py` | any process (file read) | CLI only (`tools/cri_calculator.py`); `BurnInSnapshot` omits freshness (O-01 known gap) | Canonical snapshot via `observability/operator/domains/regret_state.py` | YES (disk) | `last_canonical_evaluated_utc` |
| System health (boot alive, health score) | `observability/system_snapshot.py`, `observability/health_score.py`, `watchdog_vps.py` | advisor process (+ watchdog) | `visualization/api/health_api.py` (partial, `SystemSnapshot`-derived) | Canonical snapshot via `system_health` domain | Boot-alive: NO (process liveness is inherently local, needs a watchdog-style external check); health_score: derivable from `MetricsSnapshot` if persisted | watchdog poll / `MetricsSnapshot` cadence |
| Disk / I-O | DA-01 packs (`workflow_dispatch`-triggered forensic audits) | separate CI job, not the advisor process | None operator-facing (O-01 known gap, carried forward) | Canonical snapshot, `disk_io` domain, `UNAVAILABLE` outside audit windows | YES (artifact files), but on-demand only, not continuous | DA-01 pack timestamp |
| Adaptive learning application counters | `MistakeMemory`, `MetaLearner`/`MetaMemory` | advisor process | `FEATURE_ADAPTIVE_DECISION_FEEDBACK` flag only; no `recommendation_count`/`applied_count` (O-01 `S02_PROVENANCE_DEBT`, unresolved) | Canonical snapshot, fields explicitly `NOT_EXPOSED` per §19 | N/A — not instrumented at all yet | N/A |
| CryptoRadar / market telemetry | `scripts/radar_bot.py`, `scripts/dashboard_api.py` | separate `crypto-radar-bot` process/service | `scripts/dashboard_api.py` (its own token-authed FastAPI, port `DASHBOARD_PORT`) | `MARKET` subrouter/proxy, observational only (§12) | YES if radar's own outputs are disk/HTTP-read, but never treated as execution authority | radar poll cadence |

---

## 4. COMMON_VALUE_CONTRACT

O-01 already ships the value envelope this contract needs
(`observability/operator/contracts.py`). This mission **reuses it
verbatim** rather than inventing a competing shape — per O-01's own
"reuse before creation" principle and the brief's explicit instruction
to reconcile against, not replace, existing vocabulary.

`ObservedValue[T]` (`contracts.py:154-261`):

```
value: Optional[T]
semantics: NullSemantics   # PRESENT | ZERO | FALSE | EMPTY | UNKNOWN |
                           # UNAVAILABLE | STALE | NOT_APPLICABLE
```

`DomainSnapshot` (`contracts.py:327-364`) already carries:
`domain, observed_at_utc, source, source_version, freshness, status,
schema_version, evidence`.

Mapping the brief's requested envelope fields onto what already exists
(no gaps requiring a new field, one naming reconciliation noted):

| Brief's requested field | O-01 equivalent | Note |
|---|---|---|
| `value` | `ObservedValue.value` | direct |
| `status` | `DomainSnapshot.status` (closed vocabulary `OK/DEGRADED/ATTENTION_REQUIRED/UNAVAILABLE`) + `ObservedValue.semantics` for per-field null state | O-01 splits domain-level `status` from field-level `semantics` — this is *more* precise than a single per-field status and is kept |
| `population` (sample size backing a metric, e.g. N trades) | Not a first-class O-01 field; carried today as an explicit `PercentageMetric.denominator`/`.numerator` pair (`contracts.py:286-320`) for ratios, or as a plain int `ObservedValue` for counts | Reused as-is; this contract does not invent a generic `population` field distinct from the already-explicit numerator/denominator pattern |
| `source` | `DomainSnapshot.source` | direct |
| `observed_at_utc` | `DomainSnapshot.observed_at_utc` | direct |
| `source_updated_at_utc` | Not a distinct O-01 field today — `observed_at_utc` conflates "when the domain composer ran" with "when the underlying source last changed." **This contract adds it** as a genuinely new, narrow field on the *snapshot envelope* (§14) because the brief's freshness model (§13) requires distinguishing "we polled at T" from "the source's own last-change time is T-5min." This is a documentation-only addition here — no code exists yet; a future implementation mission must add it to `DomainSnapshot` or an envelope wrapper. |
| `freshness` | `DomainSnapshot.freshness` (`FreshnessStatus`: `FRESH/DEGRADED/STALE/UNKNOWN/NOT_APPLICABLE`) | direct |
| `unit` | `MetricDefinition.unit`/`.value_type` (registry-level, not per-value) | reused; units are a property of the *metric definition*, not repeated on every value instance — avoids redundant per-response payload bloat |
| `authority` | **New concept this mission introduces explicitly** — not an O-01 field. See §8 (`DECISION_API_CONTRACT`) for the authority/telemetry split this must encode: `EXECUTION_AUTHORITY` (the `DecisionPacket.is_actionable()` G8 gate's terminal verdict, §8) vs `OBSERVATIONAL_TELEMETRY` (analysis/gating inputs and reporting mirrors, including the legacy dict pipeline and `DecisionObservation`) vs `DECISION_OUTCOME_EVIDENCE` (`BlackBox`, post-hoc outcome/provenance log, never a gate). **Correction (R4/BLOCKER A):** the original draft's third vocabulary value, `SHADOW_CANDIDATE`, described a stale relationship in which the legacy dict pipeline was authoritative and `DecisionPacket` was a mere non-authoritative candidate track — re-reading the current G8 gate shows the reverse is true (`DecisionPacket.is_actionable()` is the mandatory gate; the legacy pipeline is an input). `SHADOW_CANDIDATE` is retired from this vocabulary; use the three values above. Documented here as a required *new* per-field or per-domain tag; not yet implemented in code. |
| `evidence_ref` | `DomainSnapshot.evidence: Mapping[str, Any]` | direct — already a free-form provenance bag per domain |

**Decision:** the future operator API's response envelope = O-01's
`DomainSnapshot.to_dict()` output, augmented with exactly two new
fields not present in O-01 today: `source_updated_at_utc` (§ above) and
`authority` (§8). No other new field is required. This is intentionally
minimal — O-01's vocabulary is sufficient for everything else the brief
asks for.

---

## 5. PORTFOLIO_API_CONTRACT

**Canonical source:** the running `MexcSimulator` instance inside the
advisor process (`paper_trading/mexc_simulator.py`), for open positions
and paper equity's live component; `infra/wallet_sync.py::get_wallet_sync()`
for equity/capital; `observability/real_accounts.py::RealAccountsObserver`
for REAL account fields; `paper_trading/recorder.py` /
`databases/paper_trades.jsonl` for realized PnL and closed history.

**Cross-process materialization strategy (mandatory):** the API process
is explicitly forbidden from `MexcSimulator()` or `WalletSync()`
instantiation of its own (§ PROCESS_BOUNDARY_VERDICT). The advisor
process must, once per cycle, serialize its live `MexcSimulator`
state (via the existing honest-view builder,
`paper_trading/portfolio_status.py::build_portfolio_status()`, which
O-01 already flags `CANONICAL_EXISTING` and "conçu spécifiquement pour
éviter la mésattribution" — reuse this, do not re-derive) into the
canonical snapshot file (§1.3). The API process only ever reads that
file plus the ledger JSONL directly for closed-trade history.

| Field | Source | Exposure target | Notes |
|---|---|---|---|
| `paper_equity_usd` | `WalletSync.get_balance()` (paper mode) | Materialized in snapshot | O-01 `portfolio_state.paper_equity_usd` |
| `paper_open_positions_count` | `MexcSimulator._positions` via `paper_portfolio_view` | Materialized in snapshot | O-01 `portfolio_state.paper_open_positions_count`; `ZERO` if simulator active with no positions, `UNAVAILABLE` if simulator not instantiated |
| `open_positions[]` (list) | `MexcSimulator._positions` | Materialized in snapshot (new — not in O-01's flat scalar model) | See per-position fields below |
| `unrealized_pnl_usd` / `_pct` | `MexcSimulator` position mark-to-market at snapshot time | Materialized in snapshot | O-01 `portfolio_state.paper_unrealized_pnl_usd` |
| `realized_pnl_usd` | Sum of CLOSE events, `paper_trades.jsonl` | API reads ledger directly, or producer denormalizes | O-01 `portfolio_state.paper_realized_pnl_usd` |
| `closed_trade_history[]` | `paper_trading/recorder.py::PaperTradeRecorder.trades()` (closed subset) | API reads ledger directly | See §6 for field list |
| `real_account_equity_usd` | `observability/real_accounts.py` | Materialized in snapshot | `NOT_APPLICABLE` if no real account configured (current stabilization window: none live) |
| `real_account_free_usd` | same | Materialized in snapshot | same |
| `real_account_stale` | same, staleness derived from `RealAccountsObserver` poll cadence | Materialized in snapshot | never silently treated as `False` when unknown — `UNKNOWN` semantics if poll never ran |

**Per-open-position fields** (from `MexcPosition`, `paper_trading/mexc_simulator.py`):

| Field | Available? | Note |
|---|---|---|
| `position_id` | YES (`pos_id`, keyed by ledger `trade_id` on restore, or generated on open) | |
| `symbol` | YES | |
| `side` | YES (`OrderSide`) | |
| `size_usd` (`qty_usd`) | YES | |
| `entry_price` | YES | |
| `current_price` | NOT stored on `MexcPosition` at all (no `current_price` field on the dataclass, confirmed by full field-list read) — it is a **materialized derived observation**, fetched at read/materialization time by `get_open_positions_summary()` calling `_fetch_price(symbol)`. `_fetch_price()` returns `0.0` both when no exchange client is wired (`self._mexc is None`) and on any fetch exception — a `0.0` therefore means **unavailable price evidence**, never a legitimate market price of zero; the snapshot MUST render it as `UNAVAILABLE`, never as `price: 0`. `STALE` is `FUTURE_ONLY` and legal only if a future source supplies a verifiable market-source timestamp or last-valid-price timestamp — position-restoration time must never be used to infer price staleness (today's source exposes no such timestamp and no persistent last-valid tick). Must carry its own `observed_at_utc` distinct from the position's `opened_ts`, since it is computed at materialization time, not stored position state. | |
| `tp_price` / `sl_price` | YES, but on **restore** these are recomputed from a fixed 4%/2% assumption (`_restore_positions()`), not the original order's true TP/SL if it differed — the snapshot MUST carry an explicit `tp_sl_source: "original"` (normal `_fill_market()` open) vs. `"restored_default"` (restore path) provenance tag; `"restored_default"` must never be presented with the same confidence as an order-derived value | |
| `unrealized_pnl_usd` / `_pct` | YES, computed from the materialized `current_price` above at read time (`get_open_positions_summary()`), not stored on `MexcPosition` — inherits the same "0.0 == unavailable, not a valid zero PnL" caveat: if the underlying price fetch failed, PnL must be `UNAVAILABLE`, never silently `0` | |
| `opened_at` | YES (`opened_ts`) | |
| `regime` | On a **normally opened** position (`_fill_market()`), `regime=order.regime` is populated from the originating `MexcOrder` — confirmed present in the constructor call. On a **restored** position, `_restore_positions()`'s `MexcPosition(...)` construction call does **not** pass `regime` at all, so it silently defaults to the dataclass default `"unknown"` — this is a real, confirmed provenance gap distinct from the normal-open path, not a uniform `NOT_EXPOSED`. The snapshot must label a restored position's `regime` as `"unknown"` with an explicit `restored_without_regime: true` (or equivalent) marker, never presented with the same confidence as a normal open's ledger-sourced `regime`. **(R4.2 — exact join key, not `trade_id`/`symbol`.)** The **only** permitted join back to the originating ledger record is `MexcPosition.pos_id == ledger TradeEvent`/`CompleteTrade.trade_id` — `pos_id` is the in-memory position-side identity, `trade_id` is the ledger-side identity, and this exact-id match is the sole lookup key. `symbol` may be used only as a **post-join consistency check** against the matched record, never as a lookup key or fallback join, and never to borrow `regime`/`personality`/TP-SL provenance from a different trade that merely shares the same symbol. If `pos_id` is missing, no exact `trade_id` match exists, or the matched record's `symbol` conflicts, the result is `UNKNOWN`/`UNAVAILABLE`, never a symbol-matched guess (`AVAILABLE_VIA_LEDGER_JOIN` only applies to a genuine exact-id match). This enrichment belongs to the advisor-owned producer/materializer in O-02W-C (§21.1) — the later read-only API exposes the already-materialized result and never repairs or re-infers an open position's provenance independently. |
| `personality` | On a **normally opened** position (`_fill_market()`), `personality=order.personality` is populated from the originating `MexcOrder` — confirmed present in the constructor call, resolving O-19's prior `NEEDS_VERIFICATION`. On a **restored** position, `_restore_positions()` sets the literal string `"restored"` (confirmed at the construction call site) — this is itself a provenance label, not a genuine personality value, and must be exposed as such (`personality: "restored"` is meaningful provenance, distinct from a real personality name). |

**Forbidden:** the future web API process instantiating `MexcSimulator`
or calling `get_wallet_sync()` and treating the result as the live
machine's state (§ PROCESS_BOUNDARY_VERDICT — this is a hard
constitutional constraint of this contract, not a style preference).

---

## 6. TRADE_API_CONTRACT

**Canonical source:** `paper_trading/recorder.py::PaperTradeRecorder` /
`databases/paper_trades.jsonl` (append-only JSONL, `event: "OPEN"|"CLOSE"`
pairs joined by `trade_id`; schema_version currently `3`). Inspected the
full recorder (`paper_trading/recorder.py`, 250+ lines) and confirmed no
`databases/paper_trades.jsonl` file exists in this checkout (fresh
worktree, no runtime data) — the schema below is from the recorder's
`TradeEvent`/`CompleteTrade` dataclasses, not from sampled live data.

| Brief field | Recorder field | Status |
|---|---|---|
| `trade_id` | `trade_id` | AVAILABLE |
| `symbol` | `symbol` | AVAILABLE |
| `side` | `side` | AVAILABLE |
| `entry` (price) | `entry_price` | AVAILABLE |
| `exit` (price) | `exit_price` (`None` while open) | AVAILABLE |
| `size` | `size_usd` | AVAILABLE |
| `opened_at` | `opened_at` (epoch float) / `opened_iso` | AVAILABLE |
| `closed_at` | `closed_at` / `closed_iso` (`None` while open) | AVAILABLE |
| `duration` | `duration_s` | AVAILABLE (computed at close time from `opened_at`) |
| `realized_pnl_usd` | `pnl_usd` | AVAILABLE (closed trades only) |
| `realized_pnl_pct` | `pnl_pct` | AVAILABLE (closed trades only) |
| `close_reason` | `exit_reason` (from `TradeEvent.reason`) | AVAILABLE |
| `fees` | — | **NOT_EXPOSED** — no fee field anywhere in `TradeEvent`/`CompleteTrade`; `MexcSimulator` applies "slippage and fees MEXC" per its own docstring but the recorder schema does not persist a fee amount. Confirmed by reading the full dataclass field lists (lines 171-234). Must render as `NOT_EXPOSED`, never `0`. |
| `regime` | `regime` | AVAILABLE |
| `score` | `score` (int) | AVAILABLE |
| — (extra, found on inspection) | `mode` (`"futures_demo"\|"paper"\|"live"`) | AVAILABLE — required for MODE_PROVENANCE (§7) |
| — | `order_id` | AVAILABLE (open only) |
| — | `mae_pct` / `mfe_pct` | AVAILABLE (close only, `Optional`) |
| — | `market_context` (27-feature `MarketContext`, schema v2+) | AVAILABLE if schema_version ≥ 2 for that record; `NOT_EXPOSED` for schema v1 records (older ledger lines, backward-compatible read returns `None`) |
| — | `decision_context` (`DecisionContext`: conviction, personality, etc., schema v2+) | Same v1/v2 caveat as above |
| — | `runtime_config_version` (schema v3+) | AVAILABLE for v3 records only |
| `is_open` | `is_open` (bool, `True` for OPEN without matching CLOSE) | AVAILABLE — this is how the trade API distinguishes open vs. closed within the same ledger read, no separate "current positions" call needed for the ledger-derived view (though live mark-to-market still requires §5's MexcSimulator materialization) |
| `is_win` | `is_win` (bool, closed only, `pnl_usd > 0`) | AVAILABLE |

No property in this table is fabricated as zero; any field absent for a
given schema version must render `NOT_EXPOSED` for that record, never a
default numeric.

### 6.1 JSONL read-consistency / watermark contract (R1-2, extended R2-1)

**Correction:** the original draft of this contract characterized the
JSONL ledgers (`paper_trades.jsonl`, `regret_*.jsonl`, `black_box.jsonl`)
as directly cross-process-safe, reproducible point-in-time sources
because they are append-only. That is imprecise. Confirmed by reading
`paper_trading/recorder.py` in full:

- `_append()` (the writer) does a plain `self._path.open("a").write(line)`
  — a normal buffered append, no `fsync`, no locking, no atomic-rename
  step. A concurrent reader mid-write can observe a file whose last line
  is not yet newline-terminated (a torn write of the in-progress line
  only — POSIX `write()` on a regular file is not guaranteed atomic
  across arbitrary sizes, though same-line torn reads are the practical
  risk, not corruption of earlier lines).
- `events()` (the reader) iterates line-by-line and wraps each
  `json.loads(line)` in a bare `try/except Exception: pass` — a
  malformed or incomplete trailing line is **silently skipped**, not
  surfaced as an error.

So the correct relationship is:

**APPEND-ONLY ≠ ATOMIC MULTI-READER SNAPSHOT ≠ REPRODUCIBLE
POINT-IN-TIME VIEW.** Append-only guarantees earlier, fully-written lines
are never mutated or removed — it does not guarantee that two reads
(or two different consumers reading concurrently with the writer) see
the same *set* of lines, and it does not distinguish "confirmed-empty"
from "unreadable-tail-currently-being-written."

**Second correction (R2-1): a logical path is not a stable physical
generation.** Confirmed by reading `scripts/rotate_jsonl.sh`:
`rotate_if_large()` does `mv "$file" "$archive"` (archive suffixed with a
UTC timestamp, e.g. `black_box.jsonl.20260906_190000`) followed
immediately by `touch "$file"`, optionally backgrounding a `gzip` of the
archive — applied today to `databases/black_box.jsonl`,
`databases/gate_rejections.csv`, and `databases/integrity_audit.jsonl`
whenever they exceed `ROTATE_THRESHOLD_MB`. After this runs,
`databases/black_box.jsonl` is a **brand-new, empty inode** at the same
path — a `byte_offset` recorded against the pre-rotation file is
meaningless against the post-rotation file at that path: offset 184320
might land mid-object in the old generation's content but past-EOF (or,
worse, coincidentally valid-looking but wrong) in the new one. The
original §6.1 text implicitly treated "path" as a globally immutable
identity; that is false for any rotating ledger and must not be implied
even for ledgers not currently rotated on a schedule (a manual `mv`
achieves the same effect).

**Corrected model — logical ledger vs. physical generation.** The
contract now distinguishes:

- **Logical ledger** — the stable, path-like identity an operator or
  cockpit reasons about ("the paper trades ledger," "the black-box
  ledger") — this is what `path` denotes, and it MAY remain stable
  across rotations.
- **Generation (logical content generation, R3.1 correction)** —
  `generation_id` identifies **one governed logical ledger content
  generation**, not "one specific inode/file instance" (R3's original
  wording was too narrow and conflicts with `rotate_jsonl.sh`'s own
  `gzip "$archive"` step, which changes the archived file's inode/bytes-
  on-disk without changing what content generation it represents).
  **A single generation may have successive physical representations**
  over its lifetime: the plain-text file while active, then a
  compressed `.gz` file once archived. Renaming a generation's file
  (the `mv` half of rotation) does not change its identity. Compressing
  it (`gzip`) does not change its identity **provided decompression
  reproduces the original byte stream exactly** — the sidecar (§6.1.1)
  maps a `generation_id` to whatever its *current* retained physical
  representation is, updating that mapping across rename/compress
  transitions without allocating a new `generation_id` for the same
  content. Rotation creates a **new generation** only for the new
  *active* (post-rotation, empty) ledger at the logical path; the
  archived generation is a *different, retired* generation identity,
  unaffected by whatever physical representation (plain or `.gz`) later
  holds its bytes.

**Field added to the envelope (supersedes the R1-2 shape):**

```
"ledger_watermark": {
    "logical_source": "paper_trades",
    "generation_id": "b7e1f2a4c9d3e8f0",
    "byte_offset": 184320,
    "read_at_utc": "2026-09-06T19:00:00Z",
    "path": "databases/paper_trades.jsonl"
}
```

`path` is retained as **provenance only** (useful for an operator or
debugger to locate the file on disk) and MUST NOT be used as the sole
identity of a watermark for any ledger that can rotate. `generation_id`
is the opaque value that identifies which **logical content generation**
(not which specific on-disk inode/file — see the corrected model above)
a `byte_offset` is meaningful against.

**Canonical byte-offset representation (R3.1 correction).**
`byte_offset` is defined as an offset into the generation's **canonical
uncompressed ledger byte stream** — the plain JSONL content as it was
written, before any archival compression. When a generation's current
retained physical representation is a `.gz` file (post-`rotate_jsonl.sh`
archival), the implementation MUST decompress it and apply/measure the
watermark against the decompressed byte stream — **never against
compressed byte positions**, which have no stable relationship to the
uncompressed content a previously-captured `byte_offset` was measured
against.

**`generation_id` derivation — canonical model (R3 correction).** R2-1
left the derivation open between two zero-schema-change candidates
(inode number, first-N-byte content hash) and described both as
"acceptable." Independent review found both **conceptually insufficient
as a canonical identity**, not merely as implementation shortcuts:

- **Inode alone is insufficient.** A POSIX `mv`+`touch` rotation (the
  actual `rotate_jsonl.sh` mechanism) does produce a new inode at the
  logical path — but a **truncate-in-place** (e.g. `open(path, "w")`
  reopening the same path, or `ftruncate()` on an already-open
  descriptor) can retain the *same* inode while destroying the file's
  entire prior content. Inode identity therefore does not reliably
  distinguish "same governed generation" from "same inode, destructively
  reset content." `inode alone != canonical generation identity`.
- **A naively recomputed first-N-byte hash is unstable.** If the hash is
  *recomputed on every read* (as R2-1's wording implied) rather than
  captured once and persisted, a ledger that starts smaller than N bytes
  changes its own first-N-byte content as ordinary appends grow it past
  N — an entirely legitimate, non-destructive append can then flip the
  "generation identity" a naive implementation would compute, which is
  exactly backwards. `recomputed prefix hash != stable canonical
  generation identity`.

**Corrected canonical definition:** `generation_id` is **a stable
opaque UUID (or an equivalent monotonic generation epoch) allocated
exactly once for one governed ledger generation**, at the moment that
generation is created (first write of a new file, or the moment a
rotation/reset produces a new active file) — never recomputed from
file content or inode on each read. Once allocated, it never changes
for the life of that generation, regardless of how large the file
grows through ordinary append. This requires the identity to be
**persisted outside the ledger file itself**, in the small sidecar/
metadata mechanism defined in §6.1.1 below — it is not something a
reader can safely reconstruct by inspecting file bytes or inode alone
on every read.

This is a documentation-only correction: the sidecar/metadata mechanism
does not exist today and is **not implemented by this contract** — it is
a requirement for the future implementation mission (§21, §6.1.1),
consistent with R2-5's no-runtime-changes constraint on this document.

**Byte-offset unit precision (R2-1 correction).** The original text
suggested deriving `byte_offset` from `f.tell()` "after each successfully
consumed line," but `paper_trading/recorder.py::events()` opens the file
in **text mode** (`self._path.open("r", encoding="utf-8")`). Per the
Python `io` documentation, `TextIOWrapper.tell()` returns an **opaque
cookie**, not a guaranteed byte count — on encodings where character and
byte counts diverge (any non-ASCII UTF-8 content, which this ledger
schema explicitly allows: `symbol`, `close_reason`, and free-text
context fields are not ASCII-constrained), the numeric value returned by
a text-mode `tell()` is not safe to interpret as, or compare against, a
byte offset computed another way (e.g. `os.path.getsize()` or a
binary-mode read). **The field is named `byte_offset` and MUST represent
actual bytes.** The implementation mission must derive it either by (a)
opening the ledger in **binary mode** (`open(path, "rb")`) and tracking
position via the binary handle's `tell()`, decoding each line
individually for JSON parsing, or (b) computing
`len(line.encode("utf-8"))` accumulated per consumed line against a
known starting byte offset. A text-mode `tell()` cookie must never be
stored in or compared as `byte_offset`.

### 6.1.1 Generation sidecar/metadata contract (R3)

The canonical `generation_id` (§6.1's corrected definition above) must
be **persisted**, not recomputed. This requires a minimal metadata
mechanism — an "observability identity sidecar" — owned by the ledger
lifecycle (the same process/tooling that creates, rotates, or resets a
ledger, e.g. `rotate_jsonl.sh` or its future equivalent). This section
defines its **minimum required responsibilities only** — it is not
implemented anywhere today, and this document does not implement it.

**Atomic replacement of the sidecar record alone is not sufficient
(R3.1 correction).** §1.3's tmp-write-plus-`os.replace()` pattern makes
each *individual* sidecar update atomic — but the sidecar and the ledger
file it describes are **two separate filesystem objects**, and nothing
about atomically replacing one alone atomically binds it to the other.
Concretely, this unsafe sequence is possible without the state model
below: (1) sidecar says the active generation at logical path P is `G1`;
(2) the rotator `mv`s the old file at P aside; (3) the rotator creates a
new, empty file at P; (4) the sidecar has **not yet** been advanced to
`G2`; (5) a reader opens the new file at P while the sidecar still
reports `G1`; (6) the reader incorrectly labels the new (empty, post-
rotation) bytes as belonging to `G1`. The sidecar/metadata mechanism
therefore requires a **revision/state model**, not just an atomically-
written record, to make this sequence detectable and rejectable.

The sidecar/metadata mechanism MUST associate, per logical ledger:

- `logical_source` — which logical ledger this entry describes (e.g.
  `"paper_trades"`, `"black_box"`).
- `generation_id` — the opaque UUID/epoch, allocated once, identifying
  a logical content generation (§6.1's corrected model — not tied to
  one specific inode).
- **`metadata_revision`** — a monotonically increasing counter/value on
  the sidecar record itself, incremented on every write to that record.
  This is what lets a reader detect "the sidecar changed underneath me"
  independently of whether `generation_id` also changed (§6.1.4).
- **Lifecycle state** — one of `ACTIVE`, `TRANSITIONING`, `ARCHIVED`, or
  `INVALIDATED` (R3.1 adds `TRANSITIONING` to R3's original three-state
  set): `ACTIVE` is the current live generation at the logical path;
  `TRANSITIONING` is published *before* any rotation/reset mutates the
  active ledger path and cleared only once the new mapping is fully
  published (§6.1.4) — its purpose is to make the unsafe window in the
  race above an explicit, observable state rather than an invisible gap;
  `ARCHIVED` is a retained, replayable past generation; `INVALIDATED` is
  a generation a governed reset explicitly retired without replacement
  data.
- **Generation creation/activation timestamp** — when this generation
  became the active one at its logical path.
- **Intended physical ledger generation** — enough information (e.g. the
  archive filename pattern `rotate_jsonl.sh` already produces, such as
  `black_box.jsonl.20260906_190000`, or its `.gz`-compressed form once
  archived, per §6.1's rename/compression-identity correction) to locate
  the actual file this generation's bytes currently live in, whether
  active or archived.
- **Physical binding observation** — for the *currently active*
  representation only, an observation such as `st_dev` + `st_ino`
  (device + inode) from `fstat()` on the opened handle, recorded so a
  reader can verify its open handle actually corresponds to what the
  sidecar currently calls `ACTIVE` for that logical path. **This is used
  only to verify association between an open handle and the sidecar's
  current record — it is never the canonical generation identity**
  (§6.1's canonical-model correction: `inode alone != canonical
  generation identity` still holds; this field's role is narrower and
  purely defensive).
- **Controlled create/rotate/reset ownership** — which governed
  operation (initial creation, `rotate_jsonl.sh`-style rotation, or an
  explicit governed reset) produced this generation, for audit purposes.

**What the sidecar is explicitly NOT**, per this contract's minimality
principle (§1.2/§1.3): it must not become a new database, a new daemon,
a message bus, a decision component, or a trading authority. It is
strictly an **observability identity mechanism** — small metadata (e.g.
one JSON record per logical ledger, itself written with the same
tmp-file-plus-atomic-replace discipline as §1.3, so its own updates
don't reintroduce the torn-write problem this section exists to solve)
associating a logical ledger with its current and past generation
identities. Nothing about this sidecar grants it authority over trading
decisions, execution, or risk — it exists purely so a read-only API can
correctly label historical data it already has permission to read.

### 6.1.2 Governed truncate/reset vs. ungoverned mutation (R3)

**Governed truncate/reset.** A controlled, in-protocol destructive reset
of a ledger (e.g. an operator-invoked "clear this ledger" maintenance
action, if one is ever implemented) MUST, as part of that same governed
operation:

- allocate a new `generation_id` for the post-reset (now-empty) active
  ledger; **or**
- explicitly mark the previous generation `INVALIDATED` in the sidecar
  (§6.1.1) if the logical path is not immediately reactivated.

A governed reset must **never silently retain the previous generation's
identity** for content that is no longer the same content — doing so
would let a `byte_offset` captured before the reset be replayed against
unrelated post-reset data, exactly the failure mode §6.1's replay
requirements (7-8) exist to prevent.

**Ungoverned mutation is an integrity violation, not a silently-trusted
read.** This contract does **not** claim that every possible out-of-
protocol filesystem mutation (a manual `rm`+recreate outside
`rotate_jsonl.sh`, a stray script, an operator `vim`-editing the file in
place, disk corruption) can always be perfectly detected — that would be
an overstated guarantee this contract explicitly avoids making. What it
does require: if the reader's own integrity observations (e.g. the
generation identity it captured at open time no longer matches what the
sidecar or a legacy fallback signal — §6.1.3 — reports for that logical
path, or a byte range it already validated no longer parses consistently
with what it read) detect such a mutation, the read MUST be
**invalidated rather than silently trusted** — surfaced as an explicit
integrity-violation/invalid state, never presented as a normal
`AVAILABLE` result and never silently reusing the old watermark against
whatever content now happens to be at that path.

### 6.1.3 Legacy/best-effort fallback (R3)

Absent the sidecar (§6.1.1) — e.g. during a transitional period before
the future implementation mission builds it — a reader MAY fall back to
observation-based heuristics: device+inode, file size, modification/
change timestamps, or a content-anchored integrity anchor captured once
at first open (never recomputed per read, per §6.1's corrected
definition). Any such fallback:

- MUST be explicitly labeled `LEGACY` / `BEST-EFFORT` in the API
  response and/or internal diagnostics — never presented as
  equivalent in reliability to the canonical opaque `generation_id`.
- MUST document its own known limitations inline wherever it is used:
  inode alone does not detect every truncate-in-place (§6.1's canonical-
  model correction); a naively *recomputed* prefix hash can change
  during ordinary, non-destructive file growth and is therefore unsafe
  used that way (a prefix hash captured *once* at first-open and never
  recomputed is a legitimate — if still best-effort — content anchor,
  distinct from the naive recompute-per-read approach this section
  rejects); none of these observational signals can fully replace
  governed generation lifecycle metadata, because none of them are
  written *by* the governed lifecycle operation itself — they are
  inferred *after the fact* from whatever state the filesystem happens
  to be in.
- MUST NOT be described in any part of this contract as equivalent to,
  or a substitute for, the canonical sidecar-backed opaque UUID model
  (§6.1.1) once that mechanism exists.

### 6.1.4 Governed lifecycle transition and reader validation protocol (R3.1)

This section defines the **minimal race-safe protocol** required to
close the sidecar/ledger race described in §6.1.1. Like the rest of
§6.1.1-6.1.3, it is a requirement for the future implementation mission
— not implemented by this document.

**Required governed transition** (performed by whatever governed
operation rotates or resets a ledger, e.g. `rotate_jsonl.sh`'s future
equivalent):

1. **Atomically publish `TRANSITIONING`** for the logical ledger's
   sidecar record *before* mutating the active ledger path in any way —
   this closes the window in which a reader could observe `ACTIVE`
   metadata pointing at a path whose content is about to change
   underneath it.
2. Perform the rotation (`mv` old, create new) or reset.
3. **Allocate the new generation identity**, when the transition
   produces a new active generation (rotation, or a reset that doesn't
   invalidate in place).
4. **Preserve the old generation's identity** for any retained
   historical content (the archived file, whether still plain-text or
   later `gzip`-compressed — §6.1's rename/compression-identity
   correction).
5. **Atomically publish the final active/archive mapping** — the
   sidecar record(s) reflecting the new `ACTIVE` generation's identity
   and physical binding, and the old generation's `ARCHIVED` (or
   `INVALIDATED`, per §6.1.2) state and location — as one atomic write
   (or a small ordered sequence the reader protocol below can still
   validate against, per-record `metadata_revision`).
6. **Only then** does the new generation become visible to readers as
   `ACTIVE`. A reader observing `TRANSITIONING` at any point before this
   step must not treat the logical path's content as belonging to
   either the old or the new generation with confidence — see the
   reader protocol below.

**Required reader protocol:**

1. Read the sidecar's metadata revision, call it `M1`, along with the
   current `generation_id`, lifecycle state, and physical binding
   observation for the logical ledger.
2. If the state is not `ACTIVE` (i.e. it is `TRANSITIONING`), **reject
   or retry** — do not proceed to open the ledger path under a
   `TRANSITIONING` state, since which generation's bytes currently sit
   at that path is not yet determined.
3. Open the ledger file at the logical path.
4. Call `fstat()` **on the opened handle** (not a fresh `stat()` on the
   path, which could race a subsequent rotation) to obtain the actual
   `st_dev`/`st_ino` of what was opened.
5. **Verify** that this observed binding matches the physical binding
   observation the sidecar reported for the `ACTIVE` generation at step
   1 — a mismatch means a rotation raced the open between steps 1 and 3,
   and the read must not proceed as if it opened the expected generation.
6. **Re-read the sidecar metadata**, call this `M2`.
7. **Accept the read only if** `M1` and `M2` agree on `generation_id`,
   lifecycle state (`ACTIVE` throughout), and physical binding — i.e.
   nothing about the sidecar's view of this logical ledger changed
   between the initial check and the confirming re-check.
8. For a read that spans a non-trivial duration (large ledger, or a
   long-lived streaming read) during which a rotation could plausibly
   occur, **validate again before returning** the result to the caller,
   not only once at open time — the same revision/binding/state
   comparison as steps 6-7, immediately before the response is finalized.
9. **On any mismatch at any step, retry, or return an explicit
   unavailable/integrity state** — never return an empty successful
   result merely because a transition was observed to be underway, and
   never silently attribute bytes read to a generation the validation
   could not confirm.

Device and inode observations are used **only** as the physical-binding
verification described above — per §6.1's and §6.1.1's corrections,
they never become, and must never be described as, the canonical
generation identity.

**Binding requirements (R1-2 origin, extended by R2-1, extended by R3, extended by R3.1 — thirteen total, R3.1 clarifying rather than adding numbered items):**

1. Every historical/trade-history API response MUST include the
   `ledger_watermark` above, stating exactly which ledger boundary
   (logical source + generation + byte offset) the response represents.
2. A reader MUST NOT treat a `json.loads` failure on the final line as
   "no more data" silently folded into a complete result — the API's
   read loop must stop *before* an unparseable trailing line and must
   not advance `byte_offset` past the last successfully parsed line;
   whether that unparsed tail is itself surfaced (e.g. as a `partial_
   tail_detected: true` diagnostic flag) is an implementation-mission
   decision, but it must never be silently merged into "latest
   confirmed state."
3. **Confirmed-empty vs. unreadable/incomplete are distinct.** A ledger
   file that exists, is fully readable, and contains zero valid lines
   yields `status: AVAILABLE`, `population: 0`, `ledger_watermark.
   byte_offset: 0` (with a real `generation_id` for that empty file) —
   a genuine `ZERO`. A ledger file that cannot be opened, or whose
   *entire* content up to any newline fails to parse, yields `status:
   UNAVAILABLE` — never silently coerced to the same empty-list shape
   as the confirmed-empty case.
4. **Open trades whose CLOSE lies beyond the declared watermark remain
   legitimately `is_open: true` for that historical view**, within the
   same generation. `trades()` pairs `OPEN`/`CLOSE` events by `trade_id`
   only from events at or before the declared `byte_offset` *of that
   generation*; a `CLOSE` line appended after that offset must not
   retroactively be merged in — the trade is correctly reported open
   *as of that watermark*, even if it has since closed. This is a
   feature of point-in-time reproducibility, not a bug: replaying the
   same `generation_id` + `byte_offset` must always reconstruct the same
   view (requirement 9 below).
5. **A single response must not combine events beyond its own declared
   boundary.** If a request spans multiple ledgers (e.g. trades +
   regret), each carries its own independent `ledger_watermark` — the
   API must not read one ledger to a later offset than the other under
   the same request and present them as one consistent point-in-time
   view without that being visible in each resource's own watermark.
6. **A new `generation_id` is allocated when rotation/reset/content
   replacement creates a new active logical content generation** (R4.4 —
   §6.1's logical-ledger-vs-physical-generation model above, not the
   broader and incorrect "replaced, truncated, or rotated" wording this
   requirement previously used). The **retained pre-rotation generation
   keeps its existing `generation_id`**: renaming (`mv`) that retained
   generation does not change its ID; `gzip` compression of that
   retained generation does not change its ID when decompression
   reproduces the canonical uncompressed byte stream exactly (§6.1's
   canonical-byte-offset-representation correction). **Replacing only
   the physical representation of a generation — a rename, or a
   compress/decompress round-trip — is not creation of a new logical
   content generation** and must never be treated as one. A watermark
   captured against the previous active generation must never be applied
   to the new active generation: a watermark captured against a
   pre-rotation generation is a different identity from any watermark
   captured after `rotate_jsonl.sh` (or an equivalent manual
   `mv`+recreate, or a governed reset, §6.1.2) produces a new active
   generation, even though `path`/`logical_source` are unchanged.
7. **A `byte_offset` is meaningful only inside its own `generation_id`.**
   Replay (§22 test requirement 7/9) MUST compare `generation_id` before
   applying a stored `byte_offset` to any file; a replay request whose
   `generation_id` does not match the current (or the specifically
   requested archived) generation at that logical path MUST be refused
   with an explicit error, never silently applied against a
   coincidentally similarly-sized different file.
8. **Referencing a no-longer-retained generation is `UNAVAILABLE`, not
   an empty result.** `rotate_jsonl.sh` retains a gzip-compressed
   archive of the rotated-out generation (subject to its own `-mtime
   +30 -delete` purge for `.gz` files) — if a replay request names a
   `generation_id` whose archive has since been purged, the API MUST
   return `status: UNAVAILABLE` with an explicit "generation no longer
   retained" reason, never an empty-but-`AVAILABLE` history (which would
   be indistinguishable from requirement 3's genuine-zero case).
9. **A reader racing a concurrent `mv`+`touch` rotation must keep
   attributing what it already read to the generation it opened**, per
   the full governed transition + reader validation protocol of §6.1.4
   (revision check, `fstat()`-based physical-binding verification,
   re-check before returning). If a reader has an open file handle (and
   has already captured/bound the `generation_id` from the sidecar,
   §6.1.1, or a labeled `LEGACY` fallback, §6.1.3, at open time) when
   `rotate_jsonl.sh` performs its `mv` followed by `touch`, POSIX
   semantics mean the reader's file descriptor continues to reference
   the *original* (now-unlinked-from-that-path, but still open) inode —
   the reader must label everything it read through that handle with
   the `generation_id` bound at open time, and must not re-stat the
   path mid-read and silently relabel already-consumed bytes as
   belonging to the new (post-`touch`) empty generation. If the reader
   cannot prove this association held for the whole read (e.g. the
   sidecar's `metadata_revision` for that generation changed underneath
   it in a way it cannot reconcile, per §6.1.4 step 9), it must retry, reject,
   or return an explicit integrity/unavailable state — never guess.
10. **Reproducibility claims reference this field, not prose.** §1.3's
    "a copy of the file plus the ledger watermark fields... fully
    reproduces what the operator saw" is this exact mechanism: given the
    same ledger generation's content up to `byte_offset` and the same
    `snapshot_id`/`cycle` from the OperatorSnapshot envelope, replaying
    the read deterministically reconstructs the same operator-visible
    state (see §22, test requirement 9).
11. **A governed truncate/reset MUST allocate a new `generation_id` or
    explicitly invalidate the previous one** (§6.1.2) — it must never
    silently retain the previous generation's identity for content that
    is no longer the same content.
12. **An ungoverned, out-of-protocol destructive mutation is classified
    as an integrity violation when detected, never silently trusted**
    (§6.1.2) — this contract does not claim perfect detection of every
    possible out-of-protocol mutation, only that a *detected* one must
    invalidate the read rather than silently reuse a stale watermark.
13. **A `LEGACY`/`BEST-EFFORT` fallback identity (§6.1.3) must never be
    presented as equivalent to the canonical sidecar-backed opaque
    `generation_id`** — every response or diagnostic using a fallback
    must label it as such, and must not claim the reliability guarantees
    (requirements 6-9, 11-12 above) that only the canonical sidecar-backed
    model can actually provide.

**Non-rotating ledgers may use a simpler sidecar entry** (a single
`generation_id` allocated once at first-observation and never reissued,
since they are never rotated or reset in practice) — but the *common*
contract (this section) must not describe any logical path as globally
immutable, since the mechanism (`mv`+recreate, or an in-place truncate)
that breaks that assumption is generic shell/filesystem capability
applicable to any file in `databases/`, not specific to
`black_box.jsonl`. Even a "non-rotating" ledger's `generation_id` is
still the canonical sidecar-backed identity (§6.1.1), not a value
recomputed from file content on each read.

This mechanism requires **no new database and no new message bus**
(R3.1 correction: it is no longer accurate to describe it as purely "a
read-side discipline" — §6.1.1's sidecar and §6.1.4's governed
transition protocol require **governed ledger-lifecycle metadata
publication plus read-side validation**, i.e. coordinated writes by the
lifecycle operation *and* validated reads, not read-side logic alone),
consistent with R1-2's and R2-5's explicit constraint against new
storage/messaging infrastructure.

---

## 7. MODE_PROVENANCE_CONTRACT

Vocabulary (reusing O-02B semantics — confirmed present in repo history
via the merged PR title `o02b/portfolio-provenance-labeling`, base SHA
`5aecc888` includes this merge; the O-02B mode-labeling work is already
in `main`): **`PAPER` / `REAL_API` / `TESTNET_API` / `UNKNOWN`**.

**Rule (non-negotiable):** the API layer must never infer mode from a
frontend literal, a route name, or a variable name such as `real_capital`
— this is exactly the class of bug the O-01 forensic pass already found
(`docs/observability/OPERATOR_OBSERVABILITY_ARCHITECTURE.md` §10: "`/kpis`
... mixes paper-derived metrics with a real-capital base with no 'paper'
label"). The variable name `real_capital` appearing anywhere in a data
structure is not evidence of mode; only the producer-established mode
value is.

**How the producer establishes mode:** `infra/wallet_sync.py::WalletSync`
is constructed with an explicit `mode: str = "paper"` parameter
(`WalletSync.__init__`, line ~80) and exposes it via the `.mode` property
(read-only, line ~99). `get_wallet_sync(exchange=None, mode=None)`
resolves the mode once, at first call, from whatever the calling code
(ultimately `core/advisor_loop.py`) passed in — this mission did not
trace the exact call site that determines the string literal
(`"paper"`/`"live"`/`"testnet"`) passed into the very first
`get_wallet_sync()` call of the process, since that is inside
`core/advisor_loop.py`, explicitly off-limits to modify but in-scope to
cite: the mode is a **process-wide constant for the lifetime of the
advisor process**, set at startup, never toggled mid-run by this
contract's design.

**Correction (R4/BLOCKER E — reuse `_balance_provenance_from_mode()`,
never "verbatim").** Re-reading `core/advisor_loop.py` confirms a
dedicated, already-existing resolver,
`_balance_provenance_from_mode(exec_mode: str | None) -> str`, whose own
docstring states it reflects "exactement le meme mode effectif que
`ExecutionEngine.fetch_available_capital()`" — it re-reads
`PAPER_TRADING_ENABLED` directly (same env var, same default `"true"`,
same truthy set `{"1","true","yes","on"}`) rather than trusting any
locally-cached advisor-loop variable that "could diverge," and maps
`exec_mode` (`exec_engine._mode`, one of `"paper"/"live"/"testnet"`)
through `{"paper": "PAPER", "live": "REAL_API", "testnet":
"TESTNET_API"}.get(exec_mode, "UNKNOWN")` — an **unrecognized
`exec_mode` fails closed to `"UNKNOWN"`, never defaults to
`"REAL_API"`**, and `PAPER_TRADING_ENABLED=true` **overrides** `exec_mode`
entirely, always resolving to `PAPER` regardless of what `exec_mode`
says. This is the canonical mode-provenance resolver this contract
requires the producer to reuse (or an extracted shared function with
identical semantics) — **the original draft's "carry `WalletSync.mode`
verbatim" language is corrected**: the API must never independently
reinterpret a raw mode string; it must publish whatever the producer's
already-resolved provenance label is (i.e. `_balance_provenance_from_mode()`'s
output, or the equivalent extracted resolver), preserving the
`PAPER_TRADING_ENABLED` override and the fail-closed-to-`UNKNOWN`
behavior exactly.

**How the API exposes it:** the canonical snapshot (§1.3) must carry the
already-resolved provenance label (§ above) as an explicit `mode` field
on the portfolio domain, using the closed
`PAPER/REAL_API/TESTNET_API/UNKNOWN` vocabulary (`UNKNOWN` if the
snapshot was generated before the producer's first successful mode
resolution, or if the underlying `exec_mode` was itself unrecognized —
never defaulted to `PAPER` or `REAL_API` by the API layer's own guess).
This contract distinguishes the **raw internal mode** (`exec_engine._mode`,
or `WalletSync`'s raw constructor parameter — an internal, unresolved
value) from the **presentation provenance** (`_balance_provenance_from_mode()`'s
output, or the reused equivalent) that the API is required to expose —
the API must publish the latter, never the former reinterpreted
independently. `MexcPosition`-level `mode` inherited from the originating
`TradeEvent.mode` (`"futures_demo"|"paper"|"live"`, §6) must be
reconciled against the wallet-level provenance label, not treated as an
independent second source of truth — a mismatch between the two is
itself a reportable anomaly (`ATTENTION_REQUIRED`), not silently
resolved by preferring one over the other.

---

## 8. DECISION_API_CONTRACT

**Correction (R4/BLOCKER A — the current mandatory authorization gate is
`DecisionPacket.is_actionable()`, not "`SHADOW_CANDIDATE`").** Re-reading
`core/advisor_loop.py`'s G8 block (~lines 6093-6195) directly contradicts
the original draft's characterization. The actual sequence at execution
time is:

```
_legacy_trade_allowed = bool(r.get("trade_allowed", r["gate"].allowed))   # legacy pipeline verdict
_dp_r = r.get("decision_packet")
if _dp_r is None:
    _effective_trade_allowed = False        # G8-E: no packet -> no authority -> no order
else:
    _effective_trade_allowed = _dp_r.is_actionable()   # G8-D/E: DecisionPacket is the sole authority
```

The gate's own inline comment is explicit: *"Le DecisionPacket est la
source unique d'autorisation... Principe : DecisionPacket absent =
autorité absente = pas d'ordre."* The subsequent order-placement `if`
block requires `_effective_trade_allowed` (the `DecisionPacket`-derived
value), not the legacy pipeline's `trade_allowed` — a legacy-pipeline
`True` with no (or a non-actionable) `DecisionPacket` is **blocked**,
never executed. Any earlier O-01-era text citing
`core/advisor_loop.py:1488`'s comment calling the legacy dict pipeline
"the actual execution driver today" describes an **historically stale**
relationship that no longer matches the current G8 gate and must not be
relied on; it is preserved below only as historical context, explicitly
marked stale.

**EXECUTION AUTHORITY** — `core/decision_packet.py`'s `DecisionPacket`,
specifically its `is_actionable()` verdict as consumed by the G8 gate
(`core/advisor_loop.py`, ~lines 6093-6195: `_effective_trade_allowed =
_dp_r.is_actionable()`, missing packet fails closed to `False`). This is
the only mandatory execution-authorization gate in the current system
(ADR-0007 — the decision engine, not any observer, remains the sole
component authorized to gate a trade; `DecisionPacket.is_actionable()`
is that engine's terminal gate). The operator API must label any field
sourced from this gate `authority: "EXECUTION_AUTHORITY"`.

**ANALYSIS/GATING INPUT** — `core/advisor_loop.py::analyze_symbol()`'s
**legacy dict pipeline** (`blockers`, `trade_allowed`, `gate.allowed`)
feeds analysis, blockers, and gating context that the G8 gate consults
alongside the `DecisionPacket` — it supplies real inputs to the final
decision (e.g. `_legacy_trade_allowed` is compared against the packet's
verdict for the disagreement-rate metric, and legacy blockers still
suppress execution via other gates earlier in the pipeline), but it is
**not, on its own, the sole final authority**: a legacy `trade_allowed =
True` cannot execute without an actionable `DecisionPacket`. Label:
`authority: "OBSERVATIONAL_TELEMETRY"` for fields sourced purely from
this path once the G8 verdict has been applied; the terminal executed
verdict itself (post-G8) is `EXECUTION_AUTHORITY` regardless of which
inputs fed it.

**DecisionObservation** (`observability/decision_observation.py`)
remains **observational telemetry only** — it mirrors/reports the
terminal verdict for measurement purposes and has no path back into the
gate. Label: `authority: "OBSERVATIONAL_TELEMETRY"`.

**BlackBox** (`quant_hedge_ai/agents/intelligence/black_box.py`) —
`record_decision()`, `record_position_closed()`, `record_halt()`,
`record_regime_change()` etc. confirmed present. This is a
decision-**outcome**/provenance evidence log, not a gate and not an
authorization mechanism of any kind: it records what happened after the
G8 gate already decided. Label: `authority: "DECISION_OUTCOME_EVIDENCE"`.
`BlackBox` must never be described or implemented as an authorization
gate, nor as a substitute source for `DecisionPacket` history — see §8.1
below and BLOCKER H (§ TRADE_API_CONTRACT / decision-history sourcing).

| Field | Source | Authority label |
|---|---|---|
| `packet_id` | `DecisionPacket.packet_id` (UUID, `field(default_factory=uuid.uuid4)`) | Part of the `EXECUTION_AUTHORITY` gate's own identity (the packet whose `is_actionable()` was consulted by G8) |
| `trace_id` | **Resolved (R4.1, full read of `governance/decision_trace.py`):** `DecisionPacket` exposes **no field literally named `trace_id`** — `context_id`/`created_cycle_id` exist and remain semantically distinct identifiers (packet/context/cycle), never a trace identity. `governance/decision_trace.py` is a pure human-readable formatter (`explain_decision()`, `format_decision_chain()`, `format_rejection_reason()`) that renders an existing `DecisionPacket`'s fields as text/log lines — it establishes **no separate canonical `trace_id` concept** of its own; it never introduces, computes, or persists an identity field. Classification: **`NOT_EXPOSED_AS_DISTINCT_FIELD`.** This contract does not alias or synthesize a `trace_id` from `packet_id`/`context_id`/`created_cycle_id` or any other convenient identifier — those remain semantically distinct fields (§19). | N/A — `NOT_EXPOSED_AS_DISTINCT_FIELD` (R4.2 — no distinct `trace_id` authority claim; `packet_id`/`context_id`/`created_cycle_id` retain their own independent authority labels above) |
| `symbol` | Present on `DecisionPacket` context (via `context_id` join) and on the legacy pipeline's per-symbol call | Both tracks |
| `side` | `DecisionSide` enum on `DecisionPacket` | Identity/context of the authority packet |
| `score` | `confidence_raw` / `adjusted_confidence` (`DecisionPacket`, lines 417-418) | Packet-internal scoring input to the G8 gate; legacy pipeline's own `score` field is `OBSERVATIONAL_TELEMETRY` (an analysis input, not itself the terminal verdict) |
| `regime` | `MarketRegime` enum on `DecisionPacket`; also present on legacy pipeline / ledger records | Both, label per source |
| `is_actionable()` verdict (G8 gate) | `DecisionPacket.is_actionable()`, consumed as `_effective_trade_allowed` in `core/advisor_loop.py`'s G8 block | `EXECUTION_AUTHORITY` — this is the terminal, mandatory gate (BLOCKER A correction) |
| `trade_allowed` (legacy pipeline field) | Legacy dict pipeline field (`r["gate"].allowed`/`r.get("trade_allowed")`) — an analysis/gating input consulted alongside the packet, not itself the sole authority | `OBSERVATIONAL_TELEMETRY` |
| `trade_allowed` (`DecisionObservation` copy) | `observability/decision_observation.py::DecisionObservation.trade_allowed` (O-01's canonical telemetry reporting field, `decision_pipeline.trade_allowed` metric) | `OBSERVATIONAL_TELEMETRY` — mirrors the terminal verdict for reporting only, no path back into the gate |
| `first_blocker` | `DecisionObservation.first_blocker` | OBSERVATIONAL_TELEMETRY |
| `all_blockers` | `by_layer_breakdown` in `observability/operator/domains/attrition.py`, backed by `observability/rejection_store.py` | OBSERVATIONAL_TELEMETRY |
| decision outcome (win/loss/etc.) | `BlackBox.record_position_closed()`, ledger `CompleteTrade.is_win` | DECISION_OUTCOME_EVIDENCE |
| timestamps | `DecisionPacket.StateTransition` (per-transition), `BlackBoxEntry` (per-event) | per-source |
| latest decision (per symbol) | Producer must materialize the current `DecisionPacket` state per open/recent symbol into the snapshot — this is in-memory, lifecycle-scoped state, not disk-resident until closed | Materialization required, same rule as §2.3 |
| decision history | See §8.1 below (BLOCKER H) — two distinct ledgers, not one | Split by ledger, §8.1 |

### 8.1 Decision-history sourcing — two distinct ledgers (R4/BLOCKER H)

**Correction:** the original draft treated `black_box.jsonl` as if it
were (or could substitute for) the persisted `DecisionPacket` history.
Re-reading the persistence paths shows these are **two distinct
ledgers** with distinct semantics, distinct freshness clocks, and
distinct watermarks — neither is a substitute for the other:

| Ledger | Path pattern | What it persists | Confirmed consumers | Authority label |
|---|---|---|---|---|
| **DecisionPacket history** | `databases/decision_packets_YYYY-MM-DD.jsonl` (date-sharded, per-day file; `core/advisor_loop.py` writes to `<DP_LOG_DIR>/decision_packets_{date}.jsonl`) | Persisted `DecisionPacket` records — the actual G8-gate authority packets, once terminal | `visualization/api/timeline_api.py` (globs `decision_packets_*.jsonl`), `scripts/trend_scanner.py`, `scripts/daily_signal_report.py`, `scripts/radar_bot.py`, `scripts/dashboard_api.py` | `EXECUTION_AUTHORITY` history (the persisted record of what the gate actually decided) |
| **BlackBox log** | `databases/black_box.jsonl` (`quant_hedge_ai/agents/intelligence/black_box.py`, `_BB_PATH`) | Outcome/provenance events (`record_decision()`, `record_position_closed()`, `record_halt()`, `record_regime_change()`) — what happened, not the authorization act itself | `infra/api/api_server.py`'s `BLACK_BOX` path constant | `DECISION_OUTCOME_EVIDENCE` — never a substitute for DecisionPacket history |

Each ledger requires its **own** `ledger_watermark` (§6.1), its own
`logical_source` label (e.g. `"decision_packets"` vs. `"black_box"`), and
its own freshness clock — an API response must never present one as if
it satisfies the other's history requirement, and both are **disk-
resident, cross-process-readable, subject to §6.1's generation/watermark
consistency rules** (both are named rotation-subject candidates: the
date-sharded `decision_packets_*.jsonl` files rotate by date natively,
and `black_box.jsonl` is one of the three files `scripts/rotate_jsonl.sh`
explicitly rotates by size). This document's own schema-inspection pass
did not sample current runtime data from either ledger — no
`databases/decision_packets_*.jsonl` or `databases/black_box.jsonl` file
exists in this checkout (fresh worktree) — so no claim here is a claim
about *current* runtime content, only about the schema/consumer wiring
confirmed by reading the producing/consuming source.

**Known unresolved measured disagreement** (carried forward from O-01,
not fixed here): `core/advisor_loop.py:6274-6295` measures a
`decision_packet_disagreement_rate` between the `DecisionPacket`-derived
`EXECUTION_AUTHORITY` verdict and the legacy pipeline's own verdict. This
rate itself is a valid, exposable `decision_pipeline.disagreement_rate`
metric (already registered in O-01) — expose it, but it exists precisely
*because* the two tracks can disagree, not as evidence either one is
merely a "candidate": the `DecisionPacket` verdict is what actually
executes (BLOCKER A), the legacy pipeline supplies a comparison signal.

---

## 9. PIPELINE_API_CONTRACT

Per the brief: **`n_signals = n_refused + n_traded` must not be reused
as canonical.** Confirmed on inspection this is exactly what
`visualization/api/pipeline_api.py` currently computes (line ~27:
`n_signals = n_refused + n_traded`, with `n_traded = 1 if decision.get("state")
== "ACTIVE" else 0` — a binary flag, not a count, being summed into a
"total signals" figure). This is flagged `PRESENTATION_ONLY`/non-canonical
by this contract, consistent with O-01's `attrition.py` docstring finding
that `activity_tracker.execution_ratio` is "the one metric in the repo
denominated over all signals," i.e. the one legitimate all-signals-wide
ratio already existing — reuse that, not `pipeline_api.py`'s ad hoc sum.

Canonical/instrumented pipeline sources found:
`observability/operator/domains/decision_pipeline.py` (`PIPELINE_STAGES`
tuple, 13 named stages: `authority, signal, meta_strategy, risk_gate,
no_trade_layer, conviction_awareness, portfolio_brain, capital_allocation,
mistake_memory, executive_override, threat_radar, arbitrator, execution`)
and `observability/operator/domains/attrition.py`
(`by_layer_breakdown`, `rejection_rate_over_rejections`,
`execution_ratio`).

**Correction (R4/BLOCKER G — dataclass/composer existence is not runtime
exposure).** The original draft's `CANONICALLY_AVAILABLE` label was
applied to several `PIPELINE_STAGES` entries on the strength of
`observability/operator/domains/decision_pipeline.py` defining the
`StageObservation` dataclass and a `compose_decision_pipeline_snapshot()`
composer function. Re-reading confirms: **no call site in
`core/advisor_loop.py` (or anywhere else) invokes
`compose_decision_pipeline_snapshot()`** — the composer and its
13-`PIPELINE_STAGES` vocabulary are real, but nothing in the current
runtime populates a `StageObservation` for any stage. This contract now
requires a three-tier classification for every pipeline stage, and
forbids collapsing the first two into the label the brief reserves for
proven runtime exposure:

| Tier | Meaning |
|---|---|
| `CONTRACT_EXISTS` | The stage is named in `PIPELINE_STAGES` and/or has a `StageObservation` shape defined — a vocabulary/schema exists |
| `RUNTIME_PRODUCER_EXISTS` | Something in the running advisor process actually populates a `StageObservation` for that stage (a confirmed call site feeding real counts) |
| `RUNTIME_EXPOSURE_EXISTS` | That populated observation is actually reachable by a reader outside the advisor process (materialized into the canonical snapshot, or otherwise readable) |

None of the 13 `PIPELINE_STAGES` entries currently has a confirmed
`RUNTIME_PRODUCER_EXISTS` or `RUNTIME_EXPOSURE_EXISTS` — `compose_
decision_pipeline_snapshot()` exists as `CONTRACT_EXISTS` only for all
of them, pending the O-02W-C materialization work (§21). Where a stage's
underlying *disk-backed* evidence is separately, genuinely available
today (e.g. `observability/rejection_store.py`'s persisted rejection
records feeding `attrition.py`), that disk-backed evidence is called out
separately from the unpopulated 13-stage `StageObservation` model below
— it is not the same thing as the pipeline-stage composer having a real
producer. `NOT_EXPOSED` replaces the original draft's `CANONICALLY_
AVAILABLE`/`PARTIALLY_AVAILABLE` labels wherever only `CONTRACT_EXISTS`
is true; `PARTIALLY_AVAILABLE` is reserved for a stage with a *proven*
`RUNTIME_PRODUCER_EXISTS` but no full `RUNTIME_EXPOSURE_EXISTS`;
`AMBIGUOUS` is reserved for genuine semantic ambiguity (the brief's
stage concept not cleanly mapping onto any named stage at all), not for
"not yet wired." No fabricated stage counts or percentages are asserted
anywhere below.

| Brief stage | Classification | Evidence |
|---|---|---|
| MARKET OBSERVED | AMBIGUOUS | No dedicated candidate counter upstream of `analyze_symbol()` — O-01's own `decision_pipeline.py` docstring states "UNIVERSE and FEATURES are not separate stages with dedicated candidate counters in the current implementation." |
| CANDIDATES | AMBIGUOUS | Same as above — "happen upstream of `analyze_symbol()` without their own telemetry object." |
| SIGNALS | `CONTRACT_EXISTS` only (`signal` is a named `PIPELINE_STAGES` entry with a defined `StageObservation` shape: `input_count`, `output_count`, `rejection_count`, `status`) — `NOT_EXPOSED` at runtime, no confirmed producer call site | O-01's legacy-pipeline `ModuleDescriptor` additionally notes "FILTERS et SIGNALS sont fusionnés dans gate/meta/no-trade plutôt que d'être des étapes nommées séparées" for the actual execution-driving path — even the *contract* only cleanly names this stage on the `DecisionObservation`/`decision_pipeline.py` side, not on the legacy-authority side. |
| META PASS | `CONTRACT_EXISTS` only — `NOT_EXPOSED` at runtime, no confirmed producer | `meta_strategy` stage named in `PIPELINE_STAGES`; `compose_decision_pipeline_snapshot()` has no call site |
| FILTER PASS | AMBIGUOUS | Not a distinct named stage in `PIPELINE_STAGES` — folded into `risk_gate`/`no_trade_layer` per the legacy-pipeline module descriptor's own admission. |
| GATE PASS | `CONTRACT_EXISTS` only — `NOT_EXPOSED` at runtime, no confirmed producer | `risk_gate` stage named (5-condition `GlobalRiskGate` per the pipeline docstring's chain description); no call site populates it |
| RISK PASS | `CONTRACT_EXISTS` only, overlaps GATE PASS (same `risk_gate` stage; the brief's RISK/GATE split does not exist as two separate stages in the code) — `NOT_EXPOSED` at runtime | `risk_gate` stage |
| PORTFOLIO ADMISSION | `CONTRACT_EXISTS` only — `NOT_EXPOSED` at runtime | `portfolio_brain` stage named (feeds `PortfolioBrain.portfolio_health()` — carries forward O-01's `portfolio_brain_duplicated` known-debt: this stage's counters may inherit the `pos_manager` vs `MexcSimulator` divergence, §5); no confirmed producer call site |
| ORDERS | `CONTRACT_EXISTS` only — `NOT_EXPOSED` at runtime | `execution` stage named, terminal `StageObservation` shape; no confirmed producer call site |
| FILLS | AMBIGUOUS | Not a distinct `PIPELINE_STAGES` entry; fills are implicit in a successful `execution` stage plus the ledger's `OPEN` event — no separate fill-vs-order-sent distinction found (relevant for a simulator with no real exchange fill/reject asymmetry; MexcSimulator's own admission/rejection stub (`_make_rejected_stub`) is closer to a fill-layer signal but was not fully traced for a dedicated counter). |
| REJECTIONS | `PARTIALLY_AVAILABLE` — genuinely proven `RUNTIME_PRODUCER_EXISTS` + disk exposure, but this is `observability/rejection_store.py`'s own persisted evidence, not the `PIPELINE_STAGES`/`StageObservation` model | `observability/rejection_store.py`, wrapped by `attrition.py`'s `by_layer_breakdown` / `dominant_blocker` / `rejection_rate_over_rejections` — explicitly scoped (per that module's own docstring) to actionable `trade_allowed=False` records with `side in (BUY,SELL,LONG,SHORT)`; HOLD/non-actionable signals are never counted here — **this distinguishes zero rejections (a real, `ZERO`-semantics count) from "rejection tracking not instrumented for this cycle" (`UNAVAILABLE`)** per the brief's requirement. This is genuine disk-backed rejection/attrition evidence, kept separate from the unpopulated 13-stage `StageObservation` model above. |

`execution_ratio` (`attrition.py`, `PercentageMetric`, all-signals-wide
denominator) is the canonical numerator/denominator pair to use for any
"how many candidates became trades" question — never a manual
`n_refused + n_traded` reconstruction.

---

## 10. SYSTEM_HEALTH_API_CONTRACT

Reuses O-01's domain vocabulary directly, with zero invented composite
score, per the brief. `observability/operator/domains/operator_summary.py`
already implements exactly the "no opaque global health percentage" rule
the brief asks for: `OperatorSummary.status` is `OK`/`ATTENTION_REQUIRED`
(never a number), and `attention_items` names each struggling domain
explicitly by domain id and its own status/freshness — confirmed at
`OPERATOR_OBSERVABILITY_ARCHITECTURE.md` §8 and the
`operator_summary.py` module itself.

Domains to expose, verbatim from O-01's eleven:

| Domain | O-01 module | This contract's exposure |
|---|---|---|
| SYSTEM HEALTH | `system_health.py` — `boot_alive` (process-liveness tier, distinct from) `health_score`/`health_level` (scientific-health tier), `exchange_connectivity_healthy`, `exchange_latency_ms`, `module_statuses` | Expose both tiers separately, never merged into one number. **`boot_alive` correction (R4/BLOCKER D):** `CONTRACT_EXISTS`/`CHECK_IMPLEMENTATION_EXISTS` (the vocabulary and `watchdog_vps.py`'s `pgrep` check both exist), but canonical runtime exposure is `NOT_EXPOSED` — the watchdog's alive path only `log.debug()`s, publishing no readable artifact; see §14.2 for the required `UNKNOWN`-until-a-real-publisher-exists behavior. |
| MARKET STATE | `market_state.py` | Exposed via §12 MARKET_API_CONTRACT |
| DECISION PIPELINE | `decision_pipeline.py` | §9 |
| ATTRITION | `attrition.py` | §9 |
| PORTFOLIO STATE | `portfolio_state.py` | §5 |
| EXECUTION STATE | `execution_state.py` | Order/execution health (not traced field-by-field in this pass beyond confirming the file exists at 183 lines; defer full field enumeration to the implementation mission, flag `NEEDS_FULL_FIELD_READ`) |
| DATA FRESHNESS | `data_freshness.py` | §13 |
| REGRET STATE | `regret_state.py` | §11 |
| ADAPTIVE PASSIVITY / LEARNING | `adaptive_learning.py` | `decision_feedback_enabled` (FEATURE_ADAPTIVE_DECISION_FEEDBACK) exposed; `recommendation_count`/`applied_count` remain `NOT_EXPOSED` (O-01 `S02_PROVENANCE_DEBT`, unresolved, carried forward — §19) |
| DISK / I-O | `disk_io.py` | On-demand only (DA-01), `UNAVAILABLE` outside audit windows — no continuous producer exists (O-01 known gap) |
| OPERATOR SUMMARY | `operator_summary.py` | Composition-only synthesis of the above ten; never a source of new truth |

---

## 11. REGRET_API_CONTRACT

**Canonical source:** `tools/regret_repository.py` (Regret v2, certified
S-01 architecture per O-01's `regret_state.py` docstring — "does not
redesign Regret"). v1 classification
(`quant_hedge_ai/agents/intelligence/regret_engine.py`) is **LEGACY**,
retired since 2026-07-10 per ADR-0018, and appears only as an explicit
fallback path in `visualization/api/burnin_api.py` — never a silent
substitute for v2 (this contract forbids the future API from defaulting
to v1 output without labeling it `LEGACY_FALLBACK`).

**Field separation:**

| Tier | Fields | Rationale |
|---|---|---|
| **operator-primary** | `v2_active`, `canonical_freshness`, `pending_candidate_count`, `decision_feedback_enabled` (governance flag state) | What an operator needs at a glance: is Regret alive, fresh, and is it (not) feeding decisions |
| **operator-detail** | `canonical_horizon`, `last_event_utc` (producer liveness clock — distinct from) `last_canonical_evaluated_utc` (the real evaluated-on-canonical-horizon freshness clock — O-01 is explicit these must never be conflated), `horizon_status_counts` (`PENDING/MISSING_PRICE/DROPPED/EVALUATED` breakdown), `malformed_count` | Diagnostic depth for someone investigating a stale/degraded state |
| **machine-only** | Raw per-candidate MISSED_WIN/GOOD_REFUSAL classification records, CRI computation internals (`tools/cri_calculator.py`) | Feeds the statistician's N-threshold gates (`CLAUDE.md`'s Règle du statisticien) — not an operator dashboard concern at the per-record level; the CRI *score* itself (0-100) may be operator-detail, but individual regret event records are not a cockpit-facing shape |

`BurnInSnapshot`'s known gap (O-01 §10: omits `tools.regret_repository.
freshness()`, only the CLI sees it) is a defect this contract flags for
the implementation mission to fix by construction — the canonical
snapshot must include `last_canonical_evaluated_utc`-derived freshness,
not silently repeat `BurnInSnapshot`'s omission.

---

## 12. MARKET_API_CONTRACT

No `CryptoRadar` **class** exists in the codebase (searched
system-wide, all `.py` files — zero matches for `class CryptoRadar`).
The brief's "CryptoRadar" refers to the **CryptoRadar product/service**:
`scripts/radar_bot.py` (Telegram bot) and `scripts/dashboard_api.py`
(its own standalone, token-authenticated FastAPI dashboard, title
`"CryptoRadar"`, confirmed at line 16: `app = FastAPI(title="CryptoRadar",
...)`, port `DASHBOARD_PORT` env var, HMAC-token auth already
implemented there).

**Constitutional constraint:** CryptoRadar is **MARKET / observational
telemetry only** — it must never be treated as execution authority
(ADR-0007 applies to it exactly as to every other observer). Nothing in
the inspected `dashboard_api.py`/`radar_bot.py` code path feeds
`core/advisor_loop.py::analyze_symbol()`'s decision; this contract
requires that boundary be preserved by any future integration.

**How it may be incorporated later, without redesigning it:**
- **Reuse existing route semantics as a proxy**: the future operator API
  MAY reverse-proxy read-only GET routes already served by
  `scripts/dashboard_api.py` (it already authenticates and is read-only
  by its own docstring: "LECTURE SEULE") rather than reimplementing its
  data access.
- **Normalized MARKET subrouter**: alternatively, expose a
  `market_state` domain endpoint (O-01's `market_state.py`, already
  covers "is market data fresh and is the exchange reachable") as the
  cockpit-facing MARKET panel, and treat CryptoRadar's own dashboard as
  a separate, unlinked tool rather than merging its output into the
  operator snapshot — avoids coupling two independently-evolving
  surfaces.
- Either path is acceptable; this contract does not mandate one over
  the other, only that CryptoRadar integration, if it happens, is
  additive (a proxy or a subrouter) and never a rewrite of
  `dashboard_api.py`'s existing, working read-only auth/routing.

---

## 13. FRESHNESS_CONTRACT

Reuses O-01's `FreshnessStatus` (`FRESH|DEGRADED|STALE|UNKNOWN|
NOT_APPLICABLE`) and `freshness.py::classify_freshness()` verbatim — "no
timestamp -> UNKNOWN" is already the O-01 rule (`classify_freshness()`
"never invents a threshold: without an evidence-backed `fresh_threshold_s`
/`stale_threshold_s` pair it returns `UNKNOWN`, not a guess").

Per-domain freshness clocks (already domain-specific per O-01 §7, no
single global "snapshot age"):

| Domain | `observed_at`/liveness clock | `source_updated_at` clock | Missing-source behavior | Restart behavior |
|---|---|---|---|---|
| Portfolio (paper) | snapshot `generated_at_utc` | ledger file mtime / last event `ts` | `MexcSimulator` not instantiated -> `UNAVAILABLE`, never `0` positions presented as healthy | Ledger persists; positions restored (approximately, §2.1) at process start — snapshot must reflect `restored_from_ledger: true/false` per position |
| Portfolio (real) | `RealAccountsObserver` poll timestamp | same | No account configured -> `NOT_APPLICABLE` (not `UNAVAILABLE` — it's a deliberate absence, not a failure) | Poll resumes at next cycle; last-known value marked `STALE` if beyond threshold, never silently refreshed as `FRESH` |
| Decision pipeline | per-cycle `DecisionObservation` publication | same | No `DecisionObservation` this cycle for symbol -> `UNKNOWN` | Fresh cycle, no special handling needed (stateless per-cycle) |
| Attrition | `RejectionStore` record timestamps | same | Empty query result -> distinguish **ZERO rejections this window** (`NullSemantics.ZERO`) from **RejectionStore file missing/unreadable** (`UNAVAILABLE`) — never conflate | File persists across restart |
| Regret | `last_canonical_evaluated_utc` (the real clock) vs. `last_event_utc` (producer liveness only — never substituted for the former) | same distinction | No canonical evaluation yet -> `UNKNOWN` | Disk-resident, unaffected by restart |
| System health | `MetricsSnapshot` cadence (scientific tier); boot/liveness tier (`system_health.boot_alive`) has **no current source** (R4.2 — see below) | same for scientific tier | **Today:** `system_health.boot_alive` exposure is `NOT_EXPOSED` as a positive liveness signal — `watchdog_vps.py`'s check runs but publishes no independently-readable artifact, so the value is always `value=null`/`semantics=UNKNOWN`, and `observed_at`/`source_updated_at` for that tier are unavailable/not-applicable because no canonical record exists to timestamp (§14.2 has the full `ObservedValue[bool]` mapping). **Future-only** (after the deferred independent T-1 publisher exists): a publisher record that cannot be read produces `UNAVAILABLE`, and a publisher record older than its own governed freshness threshold produces `STALE` — both distinct from today's `UNKNOWN`. Neither today nor in the future does restart/manifest/snapshot age or presence ever produce `value=true`/`PRESENT` by inference. | Watchdog is a separate process; once the future T-1 publisher exists, its own liveness is a precondition for `boot_alive` to mean anything |
| Disk/IO | DA-01 pack timestamp | same | Outside an audit window -> `UNAVAILABLE`, never `OK`-by-default | On-demand only; no restart concept applies |
| Market state | exchange/market-pulse tick age | same | Exchange unreachable -> `STALE` or `UNAVAILABLE` per `exchange_connectivity_healthy` | New connection attempted next cycle |

Missing file anywhere in this table -> `UNAVAILABLE`. No timestamp ->
`UNKNOWN`. Neither is ever rendered as `0` or as a healthy default.

---

## 14. ATOMICITY_CONTRACT

The canonical snapshot (§1.3) must carry, at the envelope level (outside
any individual domain, since these are cross-domain consistency
guarantees, not domain facts):

| Field | Purpose |
|---|---|
| `snapshot_id` | Opaque unique id per write (e.g. UUID or monotonically increasing counter) — lets a consumer detect "I am looking at two different snapshots" even if timestamps alone are ambiguous |
| `cycle` | The advisor loop's own cycle counter at the moment of composition — the single most important field for preventing "positions from cycle N + capital from cycle N+1" mixtures, since every domain composed into one snapshot write must share one `cycle` value by construction (the write happens once per cycle, not per domain) |
| `source_sha` / `worktree_state` / `deployment_evidence` / `runtime_sha_evidence_status` | **Correction (R4.1/BLOCKER C — schema consistency; R4.2 adds the missing fourth field):** the original draft named a single required `runtime_sha` field here; that name is **retired terminology** (see the remediation history header) and must not reappear anywhere in this contract as a required field. There is no runtime mechanism today that proves which SHA's *bytes are actually executing in process memory*. `git rev-parse HEAD` (§15) is only a **claimed checkout/source SHA** — it does not prove a clean worktree, that deployed files match that commit, that imported bytes on disk match it, or that the running process's memory matches it (`CLAUDE.md`'s own v2/v3 `CLEAN_DATA_SINCE` history is a real precedent for exactly this class of silent divergence — the `ssh -n` bug in `deploy_vps.sh` left a believed-deployed SHA that never actually reached the VPS). This contract therefore never labels `git rev-parse HEAD` alone "the SHA actually running." The **four** envelope fields carrying this information — `source_sha` (claimed, nullable when unavailable), `worktree_state` (`CLEAN`/`DIRTY`/`UNKNOWN`), `deployment_evidence` (a sanitized object recording whether a deployment artifact proves specific files reached the host, never whether those bytes are executing), and `runtime_sha_evidence_status` (`VERIFIED`/`CLAIMED_ONLY`/`UNKNOWN`) — are defined once, canonically, in §15, and reused verbatim here; this table does not redefine them. A `VERIFIED` `deployment_evidence.status` proves file transfer only and MUST NEVER automatically upgrade `runtime_sha_evidence_status`; that field defaults `CLAIMED_ONLY`, never asserted as `VERIFIED` without an independent runtime-attested mechanism — see the four-way distinction in §15. |
| `process_instance_id` | Identifies *which* advisor process instance produced this (relevant across restarts — a new PID after a restart is a new instance even if `source_sha` is unchanged) — subject to the equality invariant defined in §15 (R4.1) |
| `generated_at_utc` | Wall-clock write time |

**Consistency expectation:** the API process must refuse to compose a
cockpit view from two files/reads whose `snapshot_id` (or `cycle` +
`process_instance_id` pair) differ, if it ever needs to merge more than
one snapshot read (e.g. a slow client re-polling mid-write — mitigated
primarily by the atomic-rename write pattern in §1.3, but the id fields
are the belt to that suspenders). A single-file, single-read design
(the selected option) makes true cross-cycle mixture structurally
difficult, but a network hiccup or a client caching an old response
must not be silently reconciled against a new one — the client must
treat `snapshot_id` as a version key and discard stale reads outright,
never merge fields across two ids.

### 14.1 Previous-runtime snapshot invalidation (R1-3)

**Gap in the original draft:** `process_instance_id` (§14, §15) is a
necessary field but is not, by itself, sufficient — nothing in the
original text prevented the API from reading a snapshot file left on
disk by a now-dead producer process and presenting it as `FRESH`/
`CURRENT` merely because its `generated_at_utc` is still inside the
freshness TTL. A restart sequence exposes this precisely:

```
A. producer process P1 (process_instance_id=I1) dies
B. the last snapshot P1 wrote (process_instance_id=I1) remains on disk,
   wall-clock-fresh (e.g. written 3s before the crash)
C. producer restarts as process P2 (new process_instance_id=I2)
D. P2 has not yet completed its first full snapshot-composition cycle
E. an API request arrives in this window
```

At step E, age-based freshness alone (`now - generated_at_utc < stale_
after`) would wrongly label I1's snapshot `FRESH`/current, even though
it is now a different process instance's stale output. **This contract
requires the following invariant, enforced independently of wall-clock
age:**

> `snapshot.process_instance_id != current_producer_process_instance_id`
> ⇒ the snapshot MUST NOT be presented as `CURRENT` runtime truth,
> regardless of `generated_at_utc` age.

**Selected mechanism: a separate, atomically-written runtime-instance
manifest, published before the first domain snapshot of a new process
lifetime.** Concretely:

1. On process start, before entering its main loop (and before writing
   its first periodic domain snapshot), the producer writes a small,
   separate file — e.g. `databases/operator_runtime_manifest.json` —
   containing at minimum `{process_instance_id, boot_timestamp_utc,
   pid, source_sha}`, using the same tmp-file-plus-atomic-replace
   mechanism as §1.3 (this is a second, much smaller atomic write, not
   a new transport). **This manifest declares which process instance
   identity is the most recently started one — it is a one-time,
   write-once-per-boot identity declaration, not a repeated liveness
   heartbeat** (§14.2 makes this precise; do not read step 2 below as
   proof the declared process is still running at read time).
2. Every periodic domain snapshot embeds the writer's own
   `process_instance_id` (already required by §14/§15) — this does not
   change.
3. **On every read, the API process reads both files** and compares
   `snapshot.process_instance_id` against
   `runtime_manifest.process_instance_id`. If they differ, the API
   MUST label the snapshot's runtime-scoped fields (everything except
   whatever it can independently attribute to a durable, non-runtime
   source such as the JSONL ledgers, which have their own §6.1
   watermark and are unaffected by producer identity) as `LAST_KNOWN`,
   never `CURRENT`. `LAST_KNOWN` is presented with its true age and an
   explicit `stale_reason: PRODUCER_RESTARTED` — distinct from ordinary
   TTL-based `STALE`, since the failure mode here is identity mismatch,
   not mere elapsed time.
4. Between step A (manifest published declaring I2) and the first
   complete post-restart domain snapshot, the API has a
   `runtime_manifest` establishing that I2 is the current *declared*
   instance, but the newest domain snapshot still carries I1. This is
   precisely the window this mechanism is for: the API can now
   positively assert `INSTANCE_RELATION=PREVIOUS_INSTANCE` for the I1
   snapshot and `NO_SNAPSHOT_YET` for I2 — a materially different, and
   more honest, operator-facing state than either "everything is fine"
   or "the whole system is down." **This step establishes instance
   relation only; it says nothing about whether I2's process is
   presently alive — see §14.2.**

**Why not rely on snapshot age alone:** a producer can legitimately be
slow for a single cycle (a heavier-than-usual pass) without having
restarted — penalizing every merely-slow cycle with the same signal as
a genuine restart would create false alarms; conversely a fast restart
loop could republish inside one TTL window and never trip an age-only
check at all. Identity comparison via the manifest is deterministic and
restart-detection-specific; age remains the *separate*, complementary
signal for ordinary TTL staleness (§13) once identity is confirmed
unchanged.

**Terminology fixed by this correction:** `LAST_KNOWN` (persisted output
whose `process_instance_id` does not match the manifest's currently
*declared* instance) is a distinct state from `CURRENT` (persisted
output whose `process_instance_id` matches the manifest's declared
instance). A cockpit consumer must render these differently —
`LAST_KNOWN` should visually communicate "this is not what the most
recently started process declared," not merely "this is N seconds old."
**Neither `LAST_KNOWN` nor `CURRENT`, on their own, are a liveness
claim** — §14.2 defines liveness as an independent axis.

### 14.2 Instance identity is not liveness (R2-2)

**Gap in the R1 text:** §14.1 as originally written repeatedly described
the runtime manifest as proof the producer "is alive," "is currently
running," or "is presently alive." That conflates two genuinely
different questions:

- **Was this manifest written by the most recently started process
  instance?** — a fact about **identity/succession**, fully determined
  by comparing `process_instance_id` values, and permanently true once
  established (it never becomes false again for that pair of ids).
- **Is that process instance's OS process still executing right now?**
  — a fact about **liveness**, which can change from one instant to the
  next (the process can hang, deadlock, or crash *after* writing its
  manifest and even after writing several valid snapshots) and which a
  one-time startup write cannot speak to at all.

A manifest written at boot and never revisited proves only the first.
**It is not a heartbeat.** A producer that wrote its manifest at
`boot_timestamp_utc` and then hung indefinitely (e.g. deadlocked before
its first snapshot cycle, or later mid-lifetime) leaves a manifest that
continues to compare as "identity match" against any snapshot it did
manage to publish — this alone must never be read as "therefore it is
still alive."

**Two independent, explicitly separated models:**

**INSTANCE RELATION** (identity/succession only, derived purely from
`snapshot.process_instance_id` vs. `runtime_manifest.process_instance_id`):

| Value | Meaning |
|---|---|
| `CURRENT_INSTANCE` | The snapshot's `process_instance_id` matches the manifest's declared instance. |
| `PREVIOUS_INSTANCE` | They differ — the snapshot was produced by an instance that is not the one the manifest currently declares. |
| `UNKNOWN` | The manifest file is missing, unreadable, or corrupt — identity cannot be determined at all; this is never coerced to `CURRENT_INSTANCE` by default. |

**LIVENESS** (a conceptual axis name only, not a second serialized
field — a genuinely separate signal from `INSTANCE_RELATION`, exposed
through the *one* canonical process-liveness field this contract
defines, `system_health.boot_alive: ObservedValue[bool]`,
§2/§10/`REQUIRED_FIELD_CONTRACT_TABLE`, R4.4 — which is itself
watchdog-polled/future-publisher-sourced and carries its own
freshness/staleness semantics per §13, not derived from the manifest at
all):

**Correction (R4/BLOCKER D — independent liveness is not exposed
today).** Re-reading `watchdog_vps.py` in full: `_is_engine_running()`
runs `pgrep -f <ENGINE_PGREP_PATTERN>` and returns a bool; `_tick()`
calls it and, when the engine **is** running, does nothing but
`log.debug("core/advisor_loop.py OK")` — no file is written, no atomic
snapshot, no positive record readable by any other process. Only when
the engine is judged **dead** does the watchdog act (alert/restart). The
watchdog therefore never publishes a positive, independently-readable
liveness artifact today. This forces a four-way classification, not a
single "boot_alive: AVAILABLE":

| Layer | Classification |
|---|---|
| Liveness **definition**/contract (`system_health.boot_alive`'s meaning, per `observability/operator/domains/system_health.py`) | `CONTRACT_EXISTS` |
| Liveness **checking logic** (`watchdog_vps.py::_is_engine_running()`'s `pgrep`) | `CHECK_IMPLEMENTATION_EXISTS` |
| Canonical, readable **runtime exposure** of that check's result (a file/socket/snapshot a separate API process could read) | `NOT_EXPOSED` — confirmed: the debug-log-only branch produces nothing durable or cross-process-readable |
| API **availability today** (`boot_alive` served over any operator API) | `NOT_EXPOSED` — no such API exists, and even if it did, it would have nothing positive to read from the watchdog |

**Independent liveness must never be derived from**: a process-identity
match (`instance_relation == CURRENT_INSTANCE`, §14.2 rule 3, unchanged),
the mere presence of the S-03 `RuntimeProvenanceSnapshotWriter`'s
identity record (proves only that the process wrote it once — not that
it is still running, exactly the same identity-vs-liveness conflation
§14.2 already forbids for the runtime manifest), or snapshot freshness
alone (a hung process can leave a wall-clock-fresh but stale file, §14.1).
A genuinely independent liveness publisher (the watchdog atomically
writing its own positive "I observed the process alive at T" record,
readable by a separate API process) **is deferred to the future `T-1`
mission, and to `T-1` alone** — it is out of scope for this contract,
for O-02W-C (§21.1), and for O-02W-D (§21.2) to implement. O-02W-D may
only read and expose whatever T-1 eventually publishes; it never builds
the publisher itself.

**Canonical serialized public field (R4.4 — resolves the R4.2 duplication
between this table and `REQUIRED_FIELD_CONTRACT_TABLE`'s separate
`system_health.liveness` row, which is retired): `system_health.boot_alive:
ObservedValue[bool]`.** This is the **one** deterministic, O-01-compatible
public contract for liveness — it reuses O-01's `ObservedValue`/
`NullSemantics` envelope (§4) rather than a second, competing
`ALIVE`/`DEAD`/`UNKNOWN` enum living on a differently-named field.
`LIVENESS` (above) remains a conceptual axis/section name only; it MUST
NOT reappear anywhere in this contract as a second serialized API field
or an independent enum competing with `system_health.boot_alive`.

| State | `value` | `semantics` | When |
|---|---|---|---|
| **Current state — no independent publisher exists** | `null` | `UNKNOWN` | Always, today. §14.2/BLOCKER D: `watchdog_vps.py` publishes no positive, readable record; no liveness-source timestamp exists at all. Never inferred from snapshot freshness, manifest presence, `process_instance_id`/`instance_relation`, PID, or S-03 output. |
| **Future fresh independent publisher — positive observation** | `true` | `PRESENT` | Once a genuinely independent liveness publisher exists (deferred to T-1 alone) and positively observes the process running, within its own freshness window. |
| **Future fresh independent publisher — negative observation** | `false` | `FALSE` | The same future publisher positively observes the process is not running. |
| **Future publisher exists but cannot be read** | `null` | `UNAVAILABLE` | The publisher's record exists but the read fails (unreachable file/socket, parse failure, etc.). |
| **Future publisher record exceeds its governed freshness threshold** | `null` | `STALE` | The publisher's own last-observation timestamp is older than its governed freshness threshold (§13). |
| **No timestamp / no publisher has ever existed** | `null` | `UNKNOWN` | Same today-state as the first row — the default absent any publisher at all. |

**Mission behavior is explicit, not implied:** O-02W-C does not invent
liveness — if `system_health.boot_alive` must be present in the snapshot
schema at all, the producer materializes only the current
`value=null`/`UNKNOWN` state, never a fabricated `true`/`false`.
O-02W-D, before T-1 exists, exposes that `UNKNOWN` state honestly with
zero inference from any other signal. T-1 owns the future independent
publisher. Only after T-1 integration does the API read the independent
publisher's record and map its exact value/freshness into the
`ObservedValue[bool]` semantics above — liveness is never derived from
the advisor-owned snapshot itself, at any point in this sequence.

**Binding rules (R2-2, all four from the remediation brief):**

1. **Identity mismatch → never `CURRENT`.** A `PREVIOUS_INSTANCE`
   relation always yields the higher-level `LAST_KNOWN` label (§14.1),
   regardless of what `LIVENESS` says about anything.
2. **Manifest missing/corrupt → `INSTANCE_RELATION = UNKNOWN`.** Never
   defaulted to `CURRENT_INSTANCE` merely because there is nothing to
   contradict it.
3. **Identity match alone MUST NOT be described as proof of liveness
   (`system_health.boot_alive` = `value=true`/`PRESENT`).**
   `CURRENT_INSTANCE` only means "the most recent snapshot came from the
   instance the manifest currently declares" — it says nothing about
   whether that instance's process is still executing at the moment of
   the API read. A cockpit must consult `system_health.boot_alive`
   separately for that question.
4. **Stale/unavailable liveness evidence MUST NOT be silently converted
   to a positive (`true`/`PRESENT`) value.** If the watchdog/future
   publisher itself is unreachable, `system_health.boot_alive` renders
   `value=null`/`UNAVAILABLE`; if its own freshness has expired, it
   renders `value=null`/`STALE`; absent any publisher at all it renders
   `value=null`/`UNKNOWN` — never defaulted to `true`/`PRESENT` because
   "no evidence of death," and never defaulted to `true`/`PRESENT`
   because the instance relation happens to be `CURRENT_INSTANCE`.

**If the public API continues to expose a single higher-level `CURRENT
| LAST_KNOWN` state** (as a convenience projection for simple cockpit
consumers who do not need the full two-axis model), its derivation MUST
be stated explicitly rather than left implicit:

```
runtime_state =
    LAST_KNOWN   if INSTANCE_RELATION in {PREVIOUS_INSTANCE, UNKNOWN}
    CURRENT      if INSTANCE_RELATION == CURRENT_INSTANCE
                    (this labels data provenance/succession only —
                     it is NOT a liveness claim; a consumer that needs
                     to know whether the producer is still running must
                     read LIVENESS separately, never infer it from
                     runtime_state == CURRENT)
```

This composite intentionally has no liveness (`system_health.boot_alive`)
branch of its own — collapsing liveness into it would silently
reintroduce exactly the conflation this section corrects.

---

## 15. RUNTIME_IDENTITY_CONTRACT

**Correction (R4/BLOCKER B — reuse S-03, do not invent a second
mechanism).** `observability/runtime_provenance_snapshot.py`'s
`RuntimeProvenanceSnapshotWriter` (S-03D, already certified, full-file
read) already publishes, per process, an atomically-written (tmp +
`os.replace()`) sanitized identity block: `process.pid`,
`process.invocation_id`, `process.exposure_epoch_id` (a UUID generated
once per process, `_EXPOSURE_EPOCH_ID = str(uuid.uuid4())`),
`process.uptime_s`, plus component-liveness sub-blocks
(`decision_observation`, `event_bus`, `rejection_store`,
`regret_scheduler`, `dip`, `black_box`). **Correction (R4.2): the sole
identity authority in this model is the advisor bootstrap** (see the
deterministic ownership model immediately below), which generates
`process_instance_id` exactly once per process lifetime — the S-03
writer is a **passive identity consumer/projection**: it receives that
value and republishes it unchanged alongside its own existing fields,
and never generates, reconciles, or otherwise produces an identity of
its own. The `operator_runtime_manifest.json` of §14.1 and the
process-identity fields below MUST publish exactly the value the
advisor bootstrap generated, propagated through the S-03 writer as a
projection — never independently produced, reconciled, or re-derived
by any of these components.

**One deterministic process identity (R4.1 — resolves the ambiguity
between S-03's `exposure_epoch_id`, O-02W's `process_instance_id`,
`operator_runtime_manifest.json`, and any "RuntimeIdentity" concept into
exactly one ownership/propagation model):**

- The advisor bootstrap owns **one canonical `process_instance_id`**,
  generated **exactly once per advisor process lifetime**, at process
  start, before the main loop begins.
- That same value is passed **unchanged** to (a) the S-03 runtime
  provenance projection (`observability/runtime_provenance_snapshot.py`),
  (b) the canonical operator snapshot (§1.3/§14), and (c) the operator
  runtime manifest (§14.1), if the manifest remains part of the design.
- **No writer, no manifest, and no consumer may independently
  regenerate, infer, or "reconcile" a second `process_instance_id`** for
  the same process lifetime — there is exactly one authority (the
  advisor bootstrap) and every other component is a pure propagator of
  the value it already received.
- **Equality invariant (binding on every future implementation):**
  ```
  S03.process.process_instance_id
    == operator_snapshot.process_instance_id
    == operator_manifest.process_instance_id
  ```
  for any triple read from the same advisor process lifetime. A
  violation of this invariant (any two of the three disagreeing while
  both are non-null) is itself an integrity defect the implementation
  mission must surface, never silently tolerate or paper over by
  preferring one value over another.
- S-03's own `exposure_epoch_id` (below) **remains a distinct
  exposure-layer identity**, unchanged in meaning, unless and until a
  separately reviewed migration explicitly changes its semantics —
  `process_instance_id` is never silently aliased to
  `exposure_epoch_id`, in either direction.
- A future O-02W-C mission may extend S-03's inputs/schema so that
  S-03 itself comes to publish the shared `process_instance_id`
  (rather than the operator snapshot/manifest independently deriving
  it) — but any such extension **must preserve S-03's existing
  `exposure_epoch_id` meaning** exactly as already defined; it is an
  additive schema change, not a replacement.
- The `operator_runtime_manifest.json` (§14.1) **may mirror** the
  shared `process_instance_id` for restart detection, but it is **not
  an independent identity authority** — it never generates or
  re-derives its own value; it only republishes what the advisor
  bootstrap generated.
- `experiment_epoch_id`/`clean_data_epoch_id` (below) remain a **third,
  fully separate** identity axis from both process identity and S-03's
  exposure identity — never conflated with either.

**Naming
correction:** S-03's `exposure_epoch_id` is an **exposure/process
epoch** — a UUID scoped to one process lifetime, identifying "which run
of the exposure layer wrote this" — and is explicitly **not** the
`CLEAN_DATA_SINCE` experimental/universe epoch (`CLAUDE.md`'s
`CLEAN_DATA_SINCE_V4` boundary). The two must never share a field name;
this contract uses `experiment_epoch_id` (aliased below,
`clean_data_epoch_id` is an acceptable synonym) for the latter, reserving
`exposure_epoch_id` for S-03's process-scoped meaning exactly as that
module already defines it.

**Correction (R4/BLOCKER C — source claim vs. runtime proof, four-way
distinction).** `git rev-parse HEAD` (or the deploy tag's recorded SHA)
proves only that a checkout claims to be at that commit — never that
the worktree is clean, that the files on disk under that checkout match
the commit's tree, that the bytes actually imported by the running
Python process match those files, or that the process's in-memory state
reflects that code. This contract requires every SHA-shaped identity
field to carry one of these four explicit, non-conflatable states,
never collapsed into a single "SHA" value presented as ambient truth:

| State | Meaning | Source |
|---|---|---|
| **Claimed checkout/source SHA** | What `git rev-parse HEAD` (or the deploy tag) says the checkout is at — a claim, not a proof | `git rev-parse HEAD` at process start, or `CLAUDE.md`'s `deploy-YYYYMMDD-HHMM` annotated tags (SHA + file list) |
| **Worktree state** | `CLEAN` / `DIRTY` / `UNKNOWN` — whether the checkout has uncommitted/untracked changes at the moment of the claim; `UNKNOWN` if this was never checked | `git status --porcelain` (if run) at process start; `UNKNOWN` if not run |
| **Deployment identity/evidence** (`deployment_evidence`, R4.2) | If available — a sanitized record that this specific SHA's files were actually transferred to this host (the deploy tag's file list, or a post-deploy verification step); proves file transfer only, never that those bytes are what the process currently has in memory | `scripts/deploy_vps.sh` audit trail, if the runtime process can read it |
| **Runtime evidence status** | `VERIFIED` (an independent mechanism actually confirmed process-memory/imported-bytes match the claimed SHA — does not exist today), `CLAIMED_ONLY` (only the source-claim above exists, nothing independently confirms it), or `UNKNOWN` (not even a claim was recorded) | No `VERIFIED` mechanism exists in this codebase today; this contract requires the field default to `CLAIMED_ONLY`, never silently upgraded to `VERIFIED` |

**This contract never labels `git rev-parse HEAD` alone "the SHA
actually running."** Absent a genuine runtime-verification mechanism
(none is specified or implemented by this contract), any SHA-shaped
identity exposed by the future snapshot must render as `CLAIMED_ONLY` or
`NOT_EXPOSED` — never `VERIFIED`. **"SOURCE PROOF != RUNTIME PROOF"**
(preserved from the original text) is the summary invariant; §22 adds
negative tests asserting the API never asserts `VERIFIED` runtime-SHA
proof without an actual verification mechanism behind it.

| Field | Meaning | Source |
|---|---|---|
| `source_sha` | The **claimed** checkout/source SHA — see the four-way distinction above; never presented as proof of what is executing | `git rev-parse HEAD` at process start, or the deploy tooling's own record (`CLAUDE.md`'s `deploy-YYYYMMDD-HHMM` annotated tags carry the SHA + file list — reuse that convention as the audit trail, do not invent a second one) |
| `worktree_state` | `CLEAN`/`DIRTY`/`UNKNOWN` — see the four-way distinction above | `git status --porcelain`, if run; `UNKNOWN` otherwise |
| `deployment_evidence` (R4.2 — the fourth envelope field, previously described in prose but never given a literal schema) | A **sanitized object**, never a second SHA claim and never itself proof of what is executing: `{status: VERIFIED \| CLAIMED_ONLY \| UNKNOWN, source: deploy_tag \| deploy_audit \| post_deploy_verification \| null, evidence_ref: sanitized reference \| null, observed_at_utc: UTC timestamp \| null}`. `VERIFIED` here means only that the deployment artifact proves specific files were transferred to this host — it does **not** prove which bytes are currently executing in process memory, and it must **never** automatically upgrade `runtime_sha_evidence_status` to `VERIFIED`. Missing evidence renders `UNKNOWN`, never an assumed deployment. `evidence_ref` MUST NEVER contain a secret path, credential, token, environment dump, or any other sensitive deployment content — sanitized reference only (e.g. a deploy-tag name, not a raw log). | `scripts/deploy_vps.sh`'s `deploy-YYYYMMDD-HHMM` annotated-tag audit trail (`source: deploy_tag`/`deploy_audit`), or a future post-deploy verification step (`source: post_deploy_verification`); `UNKNOWN` if none of these ran |
| `runtime_sha_evidence_status` (was `runtime_sha`/`deployed_sha`) | `CLAIMED_ONLY`/`VERIFIED`/`UNKNOWN` per the four-way distinction above — **renamed and re-scoped by R4**: this field is never itself a second SHA value asserted as ground truth, it is the *evidence status* attached to `source_sha`. `CLAUDE.md`'s own documented history (the v2/v3 `CLEAN_DATA_SINCE` incident, the `ssh -n` bug in `deploy_vps.sh`) is the concrete precedent this field exists to make visible rather than silently assumed away | Deploy tag / `scripts/deploy_vps.sh` audit trail for deployment identity; no `VERIFIED` mechanism exists today, so this field defaults to `CLAIMED_ONLY` |
| `process_instance_id` | Unique per process lifetime | **Generated exactly once, at advisor-process bootstrap, before the main loop begins — the advisor bootstrap is the sole identity authority** (§15 ownership model above). The value is then passed unchanged into S-03's `RuntimeProvenanceSnapshotWriter` (a passive identity consumer/projection of `process.pid`/`process.invocation_id`, never a second generator or a reconciliation point) and published immediately in a dedicated `operator_runtime_manifest.json` per §14.1, ahead of the first domain snapshot, so the API can detect a producer restart (`LAST_KNOWN` vs `CURRENT`, §14.1) independently of snapshot age |
| `pid` | If safe to expose (host-local FastAPI/cockpit under the operator's own control — this contract treats it as safe within the read-only, non-public deployment model of §16; must not be exposed if the API is ever made publicly reachable without auth) | `os.getpid()`, already published by S-03's `process.pid` — reuse that value, do not recompute independently |
| `boot timestamp` | Process start time | Recorded at process start; reconcilable with S-03's `process.uptime_s` (process-monotonic uptime) rather than a second, independently-tracked boot clock |
| `cycle` | See §14 | advisor loop's own counter |
| `schema_version` | Snapshot schema version — reuse O-01's `contracts.SCHEMA_VERSION` pattern (currently `"1.0.0"`), extended for the envelope-level additions this contract proposes (§4) | `observability/operator/contracts.py::SCHEMA_VERSION` |
| `exposure_epoch_id` | S-03's **process/exposure epoch** — a UUID generated once per process (`_EXPOSURE_EPOCH_ID`), identifying which run of the exposure layer produced a given block. Reused verbatim from `observability/runtime_provenance_snapshot.py`, not a second independently-generated value. **Never conflated with the experiment/universe epoch below.** An identity record's existence proves only that this process wrote it once — it is not itself a liveness claim (§14.2 already establishes this principle for the separate runtime manifest; the same rule applies here). | `observability/runtime_provenance_snapshot.py::_EXPOSURE_EPOCH_ID` |
| `experiment_epoch_id` (renamed from the original draft's `exposure_epoch_id` — was a naming collision, R4/BLOCKER B) | The `CLAUDE.md` "époque" concept (e.g. the `CLEAN_DATA_SINCE_V4` universe-epoch boundary) so a cockpit consumer can tell which experimental epoch the currently-exposed data belongs to, without duplicating that governance logic in the API itself (it should read the same canonical epoch boundary the statistician's tooling reads — `scripts/data_quality.py`'s `CLEAN_DATA_SINCE_ACTIVE` alias — never a locally copied constant, per `CLAUDE.md`'s explicit "jamais copiée localement" rule). `clean_data_epoch_id` is an acceptable synonym field name; either name is fine as long as it is never spelled `exposure_epoch_id`. | `scripts/data_quality.py::CLEAN_DATA_SINCE_ACTIVE` |

**No secrets.** No API key, no exchange credential, no Telegram token,
no `.env` value beyond the non-secret identity fields above may ever
appear in the snapshot or the API response. This is a hard constraint,
not a recommendation.

---

## 16. SECURITY_READ_ONLY_CONTRACT

The future operator API is **READ-ONLY**, full stop:

- **Allowed:** `GET` endpoints; an optional read-only WebSocket stream
  (server -> client push of snapshot updates, never client -> server
  commands).
- **Forbidden, unconditionally:** any trading control endpoint; any
  strategy/risk/parameter mutation endpoint; file upload of any kind;
  shell/subprocess execution triggered by a request; a restart route;
  any Telegram control (send/edit/delete) triggered by a request. This
  list matches the brief exactly and is non-negotiable per ADR-0007
  (absolute observer passivity) — a "read-only API" that secretly
  exposes one mutating route is not a passive observer, it is a second,
  undocumented decision surface.
- **Auth requirement (contract-level, not implemented here):** if this
  API is ever reachable outside `localhost`/an operator-only network
  boundary, it **must fail closed** — no route responds without
  authentication. `scripts/dashboard_api.py` already demonstrates a
  working pattern in this codebase (HMAC-signed token,
  `DASHBOARD_PASSWORD` env var, `_verify_token()`) that a future
  implementation may reuse rather than invent a new auth scheme
  (REUSE_TRANSPORT_PATTERN, §18). This contract does not implement auth
  — it requires that the implementation mission not ship a publicly
  reachable, unauthenticated instance under any circumstance.

---

## 17. PANEL_REQUIREMENT_MATRIX

**Correction (R4/BLOCKER J — F-00 has not started and is not this
mission).** The original draft used "F-00" as shorthand for "the first
cockpit release milestone" and framed this matrix as "before/after
F-00." Per `CLAUDE.md` and the mission sequencing this contract itself
defines (§21), **F-00 has not started**: it is a distinct, later
burn-in/certification measurement pass (market freshness, decision
throughput, pipeline attrition, position truth, paper execution, Regret,
adaptive passivity, clock consistency, disk/write growth, restart
stability) that only begins **after** the required operator/runtime
certification sequence below — it is not O-02W-B (this contract), not
O-02W-C (the snapshot-builder mission this contract unblocks, §21), and
not "the initial cockpit implementation." This matrix is corrected to
sequence panels against the actual mission chain instead:

- **O-02W-C** (§21): advisor-owned snapshot *builder* only — no API, no
  UI. Nothing in this matrix ships to an operator's screen at this
  stage; O-02W-C only makes the fields *materializable*.
- **O-02W-D** (§21): read-only API + cockpit panels, MASTER-reviewed
  only after O-02W-C's producer snapshot exists. This is the actual
  first point any panel below can be *rendered*.
- **O-02W-F / O-02C** (§21): later runtime operator-experience
  certification, after O-02W-D ships.
- **F-00**: a separate, later measurement pass, gated on its own
  certification sequence — never described as "the first cockpit
  release" by this contract.

Minimum contracts required for each panel, keyed to the mission that may
first render it (`REQUIRED_FOR_O-02W-D` = needed at first cockpit
render; `SAFE_TO_ADD_AFTER_O-02W-D` = may lag without blocking initial
render):

| Panel | Minimum contract required for O-02W-D |
|---|---|
| **GLOBAL** | RUNTIME_IDENTITY_CONTRACT (§15) + ATOMICITY_CONTRACT (§14) + at minimum `operator_summary` domain (§10) — a cockpit cannot render *anything* trustworthy without knowing what snapshot/cycle it is looking at and whether the system considers itself healthy |
| **MARKET** | `market_state` domain (§10/§12), scoped to freshness/connectivity only — full CryptoRadar integration is explicitly `SAFE_TO_ADD_AFTER_O-02W-D` |
| **PORTFOLIO** | Full §5 PORTFOLIO_API_CONTRACT for paper equity/open positions/realized PnL; REAL account fields may ship as `NOT_APPLICABLE` placeholders if no real account is configured during the stabilization window (current state) |
| **TRADES** | §6 TRADE_API_CONTRACT closed-trade history, ledger-read only — no live position dependency, so this is one of the *cheapest* panels to ship correctly |
| **DECISIONS** | §8's `EXECUTION_AUTHORITY` verdict (`DecisionPacket.is_actionable()`, the G8 gate) + `first_blocker`/`all_blockers` (attrition) at minimum; full `DecisionPacket` detail may ship after O-02W-D's first cut |

| Domain | Classification | Justification |
|---|---|---|
| PIPELINE | `REQUIRED_FOR_O-02W-D` (attrition/rejections subset only) | An operator needs to see *why* trades aren't happening (the single most common operator question); full 13-stage `StageObservation` detail can lag (and per §9/BLOCKER G currently has no runtime producer at all), but `dominant_blocker`/`execution_ratio` cannot |
| RISK | `SAFE_TO_ADD_AFTER_O-02W-D` | `risk_gate`/`execution_state` domains are diagnostic depth, not a first-cut operator need beyond the authority verdict already required for DECISIONS |
| REGRET | `SAFE_TO_ADD_AFTER_O-02W-D` | Statistician-facing (CRI/N-thresholds), not an operational go/no-go signal for day-to-day monitoring; `v2_active`/`canonical_freshness` alone (operator-primary tier, §11) could ship early cheaply, but full regret detail is not required for O-02W-D's first cut |
| DATA (freshness) | `REQUIRED_FOR_O-02W-D` (as a cross-cutting concern, not a standalone panel) | Every other panel's numbers are meaningless without a freshness indicator attached — this is not a separate panel to defer, it is a property every other panel's fields must already carry per §13 |
| SYSTEM | `REQUIRED_FOR_O-02W-D` (system health, runtime identity, and snapshot freshness, plus an explicit `boot_alive` `UNKNOWN`/`NOT_EXPOSED` state, + `operator_summary`; **`boot_alive` itself remains `value=null`/`semantics=UNKNOWN`, `NOT_EXPOSED` as a positive runtime-liveness signal today per §14.2/BLOCKER D**, until the deferred independent T-1 publisher exists) | **Corrected (R4.4):** O-02W-D may render system health, runtime identity, snapshot freshness, and an honest `boot_alive` `UNKNOWN`/`NOT_EXPOSED` state — it must **not** claim it can determine actual process liveness on its own. Actual positive/negative (`true`/`PRESENT` or `false`/`FALSE`) `boot_alive` capability remains gated on the independent T-1 publisher (§14.2). The cockpit must visibly distinguish `CURRENT_INSTANCE`/`LAST_KNOWN` snapshot provenance (data succession, §14.1-§14.2) from known/unknown process liveness — these are never the same claim. Full disk_io/module_statuses detail is `SAFE_TO_ADD_AFTER_O-02W-D` |

This matrix deliberately does not maximize panel count — several O-01
domains (disk_io, adaptive_learning detail, full decision_pipeline stage
breakdown) are explicitly deferred as diagnostic depth rather than
O-02W-D first-cut requirements. None of this matrix is F-00 — F-00 is a
later, separately-gated measurement mission (§21, BLOCKER J).

---

## 18. EXISTING_STACK_DISPOSITION_MATRIX

| Component | Classification | Justification (from actually reading the file) |
|---|---|---|
| `frontend/` (React cockpit, `frontend/src/{App.tsx,components,hooks,lib,views,types.ts}`) | REUSE_UI_SHELL | This is the target consumer this whole contract exists to feed — the shell (routing, view structure, `types.ts`) is the thing to build the new API *for*, not against. Not read field-by-field in this pass (out of scope — no UI changes per the mission's own constraint), but its existence as the intended consumer is confirmed. |
| `infra/api/api_server.py` | REUSE_TRANSPORT_PATTERN only (its route names are NOT canonical, per the brief's explicit warning) | Confirmed: reads directly from `databases/black_box.jsonl`, `databases/cycle_data.jsonl`, `databases/live_snapshot.json`, `logs/trades.jsonl`, `logs/execution_audit/audit.jsonl`, `databases/mistake_memory.jsonl` — a FastAPI-over-JSONL pattern worth reusing structurally, but its data-loading logic (which files, which fields, what shape) is not canonical merely because the route names are convenient, exactly as the brief warns. Its `BLACK_BOX` path-resolution fix (S-03B item 8, repo-root-relative) is a good precedent to follow, not the semantics of what it returns. |
| `sdos_terminal/api/app.py` | REUSE_TRANSPORT_PATTERN + REUSE_DATA_SEMANTICS (partially) | Explicitly documents itself as "Read-only REST API over the SDOS Data API (visualization/api/). No database writes. No engine modification. Passive observer (ADR-0007)" — the right philosophy, and its route list (`/api/health`, `/api/pipeline`, `/api/portfolio`, `/api/rejections`, `/api/burnin`, `/api/regret`, `/api/decision/{packet_id}`, `/api/system`, plus PNG/WS variants) is a reasonable shape to inherit. But it sits on top of `visualization/api/*.py`, which (next rows) carries known, uncorrected defects — so REUSE the shape, not the current values it returns until those are fixed. |
| `visualization/api/portfolio_api.py` | DO_NOT_REUSE (data semantics) | Confirmed: `n_trades=0, n_wins=0, n_losses=0, win_rate_pct=0.0, profit_factor=0.0, expectancy_pct=0.0, max_drawdown_pct=0.0, sharpe=0.0` are literal hardcoded zeros in the constructor call (8 of the ~10 `PortfolioSnapshot` fields), and `total_pnl_usd=float(portfolio.get("open_pnl_usd", 0.0))` substitutes *open* PnL for *total* PnL — exactly the two defects O-01 already flagged. Must not be treated as canonical until independently fixed; this contract's §5 supersedes it. |
| `visualization/api/health_api.py` | DO_NOT_REUSE (data semantics), REUSE_TRANSPORT_PATTERN acceptable | `_bool_score()` computes a bare `sum(bools)/len(bools)*100` composite — exactly the "invented opaque global health percentage" this contract's §10 forbids. Structurally it is a thin `SystemSnapshot`-mapping function, fine as a pattern; its *pseudo-health-percentage* output must not be reused. |
| `visualization/api/pipeline_api.py` | DO_NOT_REUSE (data semantics) | Confirmed `n_signals = n_refused + n_traded` with `n_traded` being a 0/1 flag from `decision.get("state") == "ACTIVE"`, not an actual trade count — the exact non-canonical pattern §9 forbids reusing. A narrow proxy over `SystemSnapshot.block_stats`, not the 13-stage `PIPELINE_STAGES` model. |
| `scripts/dashboard_api.py` | REUSE_TRANSPORT_PATTERN (auth specifically) | Confirmed working HMAC-token auth (`_make_token()`/`_verify_token()`, `DASHBOARD_PASSWORD` env var) in a read-only (`"LECTURE SEULE"` per its own docstring) FastAPI app — good precedent for §16's auth requirement. Its `CryptoRadar`-specific data semantics are out of this contract's PORTFOLIO/TRADES/DECISIONS scope (see §12 for its disposition as a market-telemetry source instead). |
| `sdos_terminal/frontend/` | Not inspected in this pass (directory existence not confirmed independently of `sdos_terminal/api/app.py`'s presence) — classify NEEDS_VERIFICATION rather than guess | — |
| `risk_dashboard_api.py` | Does not exist at repo root (confirmed: `ls` returned "No such file or directory") | N/A — nothing to classify |
| `api_rest.py` | Does not exist at repo root (confirmed: `ls` returned "No such file or directory") | N/A — nothing to classify |
| `observability/system_snapshot.py` + `visualization/api/system_snapshot_source.py` | REUSE_DATA_SEMANTICS (the `SystemSnapshot` dataclass field *model*, not any writer it implements) with an explicit caveat: **`SystemSnapshot != O-01`** — O-01's own architecture doc states this class distinction directly (§10 known gap: "`portfolio_api.py` is defective... `SystemSnapshot != O-01`" is implied by the fact O-01 had to build an entirely parallel domain-snapshot contract rather than just wrapping `SystemSnapshot` fields 1:1). **Correction (R1-1):** `system_snapshot.py` itself is a pure in-memory dataclass model with no atomic-write implementation of its own; the actual atomic-JSON-dump writer already in production is `quant_hedge_ai/dashboard/live_snapshot.py::write_snapshot()` (tmp-file + `Path.replace()`, called from `core/advisor_loop.py`), read back by `visualization/api/system_snapshot_source.py`. Reuse *that* writer's tmp-write-then-replace mechanism as implementation precedent for the new §1.3 canonical snapshot writer — never assume `SystemSnapshot`'s existing field values already satisfy O-01/this contract's semantics without independent field-level certification, and never cite `system_snapshot.py` itself as already atomic. | |
| `quant_hedge_ai/dashboard/live_snapshot.py` (`write_snapshot()`/`read_snapshot()`) | REUSE_TRANSPORT_PATTERN (the atomic tmp-write-then-`Path.replace()` mechanism itself) | Confirmed by full-file read: `write_snapshot()` creates `path.with_suffix(".tmp")` in the destination directory, writes the complete JSON payload via `write_text()`, then calls `tmp.replace(path)` (POSIX-atomic rename), with a bare `except Exception` that logs and leaves the destination untouched on serialization failure — exactly the reader-atomicity property §1.3's precise atomic-write requirements need. It does **not** call `os.fsync()` at any level, so it provides reader-atomicity, not crash-durability of the last write (§1.3 item 5). This is genuine, citable implementation precedent for the new canonical operator snapshot writer — not itself the O-01 envelope, and not `SystemSnapshot`. |

---

## 19. NOT_EXPOSED_REGISTER

Fields investigated and found **not currently recorded/instrumented**,
documented explicitly rather than silently omitted:

| Field | Where it was looked for | Finding |
|---|---|---|
| Trade fees | `paper_trading/recorder.py::TradeEvent`/`CompleteTrade` full field list | No fee field in either dataclass; `MexcSimulator` claims to simulate "fees MEXC" in its docstring but the recorder schema does not persist an amount. `NOT_EXPOSED`, never `0`. |
| Adaptive learning `recommendation_count`/`applied_count` | O-01 `adaptive_learning.py` (already documents this gap as `S02_PROVENANCE_DEBT`) | No dedicated counter exists in `MistakeMemory`/`MetaLearner`/`MetaMemory`/`StrategyMemoryStore`/`StrategyRanker`; `recommendation_equals_applied` is a "fixed structural False" by design post-S02, not a measured rate. `NOT_EXPOSED`. |
| `DecisionPacket.trace_id` (as a distinctly-named field) | `core/decision_packet.py` field list (lines 400-437 range inspected), plus `governance/decision_trace.py` (full read, R4.1) | No field literally named `trace_id` found on `DecisionPacket`; `context_id`/`created_cycle_id` are the closest candidates but remain semantically distinct identifiers, never aliased. `governance/decision_trace.py` is confirmed (full read) to be a pure text-formatting consumer (`explain_decision()`/`format_decision_chain()`/`format_rejection_reason()`) — it establishes no separate canonical trace identity of its own. S-03 counters that refer to "missing trace provenance" elsewhere in the codebase do not prove `DecisionPacket` exposes a distinct trace field; they describe a different (S-03-side) gap. Classification: `NOT_EXPOSED_AS_DISTINCT_FIELD` (resolved — no remaining `PARTIALLY_AVAILABLE`/pending-verification status). |
| Regime/entropy confidence on `SystemSnapshot.market` | O-01 `market_state.py::MODULES` (already documents this gap) | "`RegimePacket` fields exist and are logged but never reach `SystemSnapshot.market`." `NOT_EXPOSED` at the `SystemSnapshot` level; may exist upstream in `RegimePacket` itself (not independently re-verified in this pass beyond citing O-01's finding). |
| Continuous disk/IO operator-facing snapshot | O-01 `disk_io.py::MODULES` (already documents this gap) | DA-01 is `workflow_dispatch`-triggered only, "no operator-facing snapshot (`SystemSnapshot`, `MetricsSnapshot`) carries a disk field today." `UNAVAILABLE` outside audit windows by design, not a bug to fix here. |
| Regret freshness over HTTP | O-01 `regret_state.py::MODULES` (already documents this gap) | `tools/regret_repository.freshness()` exists and is correct but `BurnInSnapshot` omits it; only the CLI (`tools/cri_calculator.py`) sees it today. This contract's §11 requires the implementation mission to close this gap, not perpetuate it. |
| `MexcPosition.current_price` | `paper_trading/mexc_simulator.py::MexcPosition` full field list, `get_open_positions_summary()` | Not a stored field on `MexcPosition` at all — R4 re-read confirms it is a **materialized derived observation** computed at read time by `_fetch_price()`. `_fetch_price()` returns `0.0` both on missing exchange client and on any exception, so a raw `0.0` is unavailable-price evidence, never a genuine zero market price. `AVAILABLE` only as a materialized, separately-timestamped field distinct from `_positions` state; `UNAVAILABLE` (never `0`) when `_fetch_price()` cannot obtain a price. |
| `MexcPosition.personality` for a normally (non-restored) opened position | `paper_trading/mexc_simulator.py::_fill_market()` construction call | R4 re-read confirms: `_fill_market()` constructs `MexcPosition(..., personality=order.personality, regime=order.regime, ...)` — both fields **are** populated from the originating `MexcOrder` on a normal open. This resolves the prior `NEEDS_VERIFICATION`: `AVAILABLE` for normal opens, distinct from the restore path's `personality="restored"` literal (itself a provenance label, not a real personality value). |
| `MexcPosition.regime` | `paper_trading/mexc_simulator.py` (`_restore_positions()` construction site) | R4 re-read confirms `_restore_positions()`'s `MexcPosition(...)` call does not pass `regime` at all, so it silently takes the dataclass default `"unknown"` — a confirmed provenance gap on the restore path specifically (not a uniform gap: normal opens via `_fill_market()` do set `regime=order.regime`, `AVAILABLE`). For a restored position, `regime` on the object itself must be exposed as `"unknown"` with an explicit restored-without-regime marker. The **only** permitted join back to the originating ledger record is `MexcPosition.pos_id == ledger TradeEvent`/`CompleteTrade.trade_id` — `symbol` is usable only as a post-join consistency check, never a lookup key or fallback. `AVAILABLE_VIA_LEDGER_JOIN` applies only to a genuine exact-id match; if `pos_id` is missing, no exact `trade_id` match exists, or the matched record's `symbol` conflicts, the result is `UNKNOWN`/`UNAVAILABLE`, never a symbol-matched guess. This enrichment belongs to the advisor-owned producer in O-02W-C (§21.1); the later read-only API only exposes the already-materialized result and never repairs or re-infers position provenance independently — matching §5 and test 26 exactly. |

---

## 20. CONTRACT RISKS / OPEN QUESTIONS

1. **RESOLVED (R4.1).** `DecisionPacket.trace_id` does not exist as a
   distinct field; `governance/decision_trace.py` (now fully read) is a
   pure text-formatting consumer and establishes no separate canonical
   trace identity. Classification is `NOT_EXPOSED_AS_DISTINCT_FIELD`
   (§8, §19) — the DECISIONS panel's field list must use `packet_id`/
   `context_id`/`created_cycle_id` as the distinct identifiers they are,
   never a synthesized or aliased `trace_id`. No further verification
   pass is required for this specific question.
2. **`execution_state.py` domain fields** were confirmed to exist
   (183-line file) but not individually enumerated in this pass —
   flagged `NEEDS_FULL_FIELD_READ` in §10.
3. **`sdos_terminal/frontend/` existence/purpose** relative to the main
   `frontend/` cockpit is unconfirmed — two frontends may or may not
   both be live; this matters for which one the future operator API is
   actually built to serve. Needs an explicit product decision, not an
   engineering guess.
4. **`MexcPosition` restore-path `regime` gap and `current_price`
   materialization** — §19 above (R4 confirms normal-open `personality`/
   `regime` ARE populated from `MexcOrder` via `_fill_market()`; the
   remaining real gap is `_restore_positions()` never passing `regime`,
   silently defaulting to `"unknown"`, and `current_price` never being
   stored state, only a read-time materialized observation from
   `_fetch_price()`, whose `0.0` means unavailable, not zero). Affects
   whether the PORTFOLIO panel's restored-position `regime` field can
   ship at O-02W-C/D without the ledger join, or must wait for it.
5. **Restored-position TP/SL provenance labeling** (§5: fixed 4%/2%
   default vs. the position's true original TP/SL) is a real,
   observable data-quality risk for any operator trusting the cockpit's
   TP/SL display after a process restart during the STABILIZATION LAB
   window (2026-09-02 -> 2026-09-16, currently active per `CLAUDE.md`)
   — restarts are explicitly authorized during this window, so this
   risk is live, not hypothetical, for the exact period this contract
   is being written in.
6. **Live/testnet `WalletSync` cross-process safety** (§2.2) has no
   clean re-derivation path short of the producer materializing it —
   if a future implementation mission is tempted to have the API
   process independently `bootstrap()` against the real exchange for
   convenience, that doubles exchange API calls and diverges from the
   advisor's own cached value; this contract explicitly forbids that
   shortcut, but it is worth flagging as a temptation the implementation
   mission should watch for.
7. **CryptoRadar (`scripts/dashboard_api.py`) auth token secret
   (`_SECRET = secrets.token_hex(32)`) is generated fresh per process
   start** (confirmed at module scope, not persisted) — any future
   proxy integration (§12) must account for tokens not surviving a
   `dashboard_api.py` restart; this is CryptoRadar's own existing
   behavior, not something this contract changes, but it constrains
   how a proxy could safely reuse its auth.
8. **`FEATURE_AUTO_CALIBRATION` / regret decision-feedback governance
   path** is explicitly out of this contract's scope (`CLAUDE.md`:
   "Regret's `FEATURE_AUTO_CALIBRATION`/`FEATURE_REGRET_DECISION_
   FEEDBACK` remains a separate governance path, untouched by this
   reconciliation" — quoting O-01 verbatim, still true here); the
   REGRET_API_CONTRACT (§11) only exposes its *state*, never its
   governance.
9. **The §6.1.1 generation sidecar does not exist yet** (R3) — until the
   implementation mission builds it and wires it into `rotate_jsonl.sh`
   (or its future equivalent), any reader must operate in the explicitly
   labeled `LEGACY`/`BEST-EFFORT` mode (§6.1.3), with the documented
   inode/prefix-hash limitations. This is a known, real gap for the
   period between this contract's certification and that mission's
   completion — the cockpit must not present `LEGACY`-derived generation
   identity with the same confidence as the canonical sidecar-backed
   model once it exists.

---

## 21. MINIMUM_IMPLEMENTATION_MISSION

**Correction (R4/BLOCKER I — rewritten to define O-02W-C as the ONLY
next mission).** The original draft bundled the snapshot builder, the
JSONL watermark/sidecar mechanisms, a new FastAPI process, cockpit
wiring, and auth into a single "next implementation mission." That
overstates what one mission should responsibly attempt next and blurs
the boundary this document exists to hold (documentation/architecture
only, zero API/UI/VPS/Telegram — see the header). This section is
rewritten to name **O-02W-C** as the **only** mission this contract
unblocks next, with every other piece explicitly deferred to named,
separately-authorized later missions.

### 21.1 O-02W-C — Canonical operator snapshot builder (the only next mission)

**Mission scope:** build the **canonical operator snapshot builder**
inside the advisor process — a narrow, additive materialization step
invoked once per advisor loop cycle (not a new decisional component — a
pure serializer with zero decision authority, zero effect on
`trade_allowed`/`is_actionable()`/timing-critical flow, zero new error
propagation into the loop), which:

- Reads already-existing live, in-process objects (`SystemSnapshot`,
  `MexcSimulator` via `paper_portfolio_view`/`portfolio_status.py`,
  `WalletSync`, `RejectionStore`, `tools/regret_repository.py`,
  `DecisionObservation`, the current/latest `DecisionPacket` per symbol)
  — materializing exactly the fields enumerated as "materialization
  required" in §2.3, §5, §7, §8 of this contract, including the
  corrected §5/§8 provenance labels (`current_price`/`regime` restore
  gaps, BLOCKER F; `EXECUTION_AUTHORITY` vs `OBSERVATIONAL_TELEMETRY` vs
  `DECISION_OUTCOME_EVIDENCE`, BLOCKER A).
- Reuses the O-01 `compose_*_snapshot()` functions already shipped
  (`observability/operator/domains/*.py`) as the composition layer where
  a real producer for that domain now exists — this is exactly the
  "step 1" O-01 itself deferred, and exactly the step that turns a
  domain's classification from `CONTRACT_EXISTS`/`RUNTIME_PRODUCER_
  EXISTS` into genuine `RUNTIME_EXPOSURE_EXISTS` (§9/BLOCKER G) for the
  domains this mission actually wires.
- Propagates the advisor bootstrap's single `process_instance_id`
  (§15's identity-authority model, corrected R4.2) into S-03's
  `RuntimeProvenanceSnapshotWriter` (`observability/
  runtime_provenance_snapshot.py`), which remains a **passive identity
  consumer/projection**, never a generator, rather than inventing a
  second identity mechanism — the `operator_runtime_manifest.json`
  (§14.1) and process-identity fields (§15) publish exactly that value,
  never independently produced or reconciled against it.
- Writes the result via a single atomic tmp-file-plus-`os.replace()`
  write to one canonical JSON path, modeled on `quant_hedge_ai/
  dashboard/live_snapshot.py::write_snapshot()` (§1.2, §1.3) — a new
  writer, not a modification of that existing function's own call site
  — augmented with the envelope-level identity/atomicity fields from
  §14-§15, at a bounded cadence (comparable to S-03's ~30-60s target,
  not per-request).
- Is fail-passive: a serialization/write failure is logged and counted,
  never raised into the advisor loop, never affecting `trade_allowed`/
  `is_actionable()` or any decision path (ADR-0007).
- Ships a focused test suite covering exactly this builder: atomic-write
  reader-atomicity (§22 test 1), failed-serialization preservation (§22
  test 2), the fail-passive guarantee above, and correct materialization
  of the corrected §5/§7/§8 provenance labels (mode override/unknown-mode
  cases, §22; restored-position `regime`/`current_price` labeling, §22).

**Explicitly OUT of scope for O-02W-C** (deferred to named later
missions below, not silently assumed or bundled in):
- Any FastAPI process, HTTP routes, or WebSocket server.
- Any React/cockpit UI work of any kind.
- Auth implementation (§16) — a contract requirement on the *future*
  API, not something O-02W-C builds.
- Any process that reads the JSONL ledgers directly as a "web process"
  concern — O-02W-C only writes the in-process snapshot; it does not
  build a ledger reader.
- The JSONL sidecar/rotation-script implementation (§6.1.1/§6.1.4) —
  wiring `rotate_jsonl.sh` (or its future equivalent) to allocate/
  invalidate `generation_id`s is a **separately authorized** deliverable
  (§21.2 below), not part of O-02W-C.
- Any VPS deployment, systemd unit, or restart action.
- Any runtime/deployment certification claim (§15's `VERIFIED` runtime-
  SHA evidence status, or the independent liveness publisher of §14.2/
  BLOCKER D) — O-02W-C does not claim to produce these.
- Any modification to `core/advisor_loop.py`'s decision logic, any new
  signal/indicator/threshold, any Telegram wiring, any write path back
  toward the advisor process from anything reading its output. The
  writer call site inside the advisor loop is additive instrumentation
  (read current state, serialize, write file) — not a change to what the
  loop decides, and it must never alter decision values, authorization,
  timing-critical flow, or error propagation of the existing loop.

### 21.2 Later missions (named, not started, not bundled into O-02W-C)

- **§6.1's sidecar/transition-protocol implementation** — wiring
  `rotate_jsonl.sh` (or its future equivalent) to allocate/invalidate
  `generation_id`s per §6.1.1-§6.1.4. A separately authorized
  deliverable; may be assigned to O-02W-C's follow-up or a dedicated
  ledger-lifecycle mission, but is not implicitly included in O-02W-C
  itself.
- **O-02W-D** — the read-only API + cockpit panels mission. Explicitly
  gated on O-02W-C's producer snapshot existing and having been
  MASTER-reviewed first; only then does building the FastAPI process
  (§1.3, §16 auth), the JSONL-ledger read/watermark logic (§6.1) as a
  *reader*, and the actual cockpit panel wiring (§17) become in scope.
- **O-02W-E** — Telegram notification/retirement work relating to this
  contract's domains, if any is ever authorized; not this contract's or
  O-02W-C's concern.
- **T-1** (or an equivalently-named dedicated mission) — runtime/
  deployment certification: the genuine independent liveness publisher
  deferred in §14.2/BLOCKER D, and any mechanism that could ever justify
  a `VERIFIED` (not merely `CLAIMED_ONLY`) runtime-SHA evidence status
  per §15/BLOCKER C.
- **O-02W-F / O-02C** — later runtime operator-experience certification,
  after O-02W-D ships and is observed in production.

None of the above is started by this document. This document
(O-02W-B-R4) and O-02W-C together do not constitute F-00 — see §17's
correction (BLOCKER J).

---

## REQUIRED_FIELD_CONTRACT_TABLE

| Field ID | Meaning | Type | Unit | Population | Authority | Null semantics | Zero semantics | Freshness |
|---|---|---|---|---|---|---|---|---|
| `portfolio.paper_equity_usd` | Current simulated equity | float | usd | N/A (scalar) | OBSERVATIONAL_TELEMETRY | `UNAVAILABLE` if WalletSync unreachable | Genuine `$0` equity is `ZERO`, distinct from unavailable | ledger mtime |
| `portfolio.open_positions[]` | Live paper positions | list[object] | — | count = list length | OBSERVATIONAL_TELEMETRY | `UNAVAILABLE` if simulator not instantiated | `EMPTY` list if simulator active with zero positions | snapshot `generated_at_utc` |
| `portfolio.open_positions[].current_price` | Live mark price — **not stored on `MexcPosition`; a materialized derived observation** computed at read time by `get_open_positions_summary()`'s `_fetch_price()` call (§5/BLOCKER F) | float | usd | N/A | OBSERVATIONAL_TELEMETRY | `UNAVAILABLE` if `_fetch_price()` returns `0.0` (no exchange client, or fetch exception — both collapse to `0.0` at the source and must be relabeled `UNAVAILABLE`, never passed through as a price); a positive price fetched during materialization is `PRESENT`; `STALE` is `FUTURE_ONLY` and legal only once a future source supplies a verifiable market-source timestamp or last-valid-price timestamp — position-restoration time must never be used to infer price staleness | N/A (a `0.0` from `_fetch_price()` is unavailable-price evidence, never a legitimate zero market price); unrealized PnL inherits `UNAVAILABLE` whenever price is unavailable | materialization time (own `observed_at_utc`, distinct from position `opened_ts`) |
| `portfolio.open_positions[].regime` | Position-level regime — populated from `MexcOrder.regime` on a normal open (`_fill_market()`); **silently defaults to `"unknown"` on the restore path** (`_restore_positions()` never passes `regime`, §5/BLOCKER F) | str (enum-like) | — | N/A | OBSERVATIONAL_TELEMETRY | Restored positions: `"unknown"` with an explicit `restored_without_regime: true` marker, never presented with the same confidence as a normal open's `regime`; `AVAILABLE_VIA_LEDGER_JOIN` only for a genuine exact `pos_id == trade_id` match (never a `symbol`-only fallback, R4.2 — see §5), performed by the O-02W-C producer/materializer, not re-inferred by the API | N/A (categorical) | position-open time (normal) / restore time (restored, best-effort) |
| `portfolio.realized_pnl_usd` | Sum of closed-trade PnL | float | usd | N over closed trades | OBSERVATIONAL_TELEMETRY | `UNAVAILABLE` if ledger unreadable | `ZERO` if genuinely no closed trades yet | ledger mtime |
| `trade.fees` | Per-trade fee amount | float | usd | N/A | OBSERVATIONAL_TELEMETRY | `NOT_EXPOSED` always (not recorded, §19) | never rendered as 0 | N/A |
| `decision.is_actionable` (G8 gate verdict) | Terminal execution-authorization verdict — `DecisionPacket.is_actionable()` as consumed by `_effective_trade_allowed` in the G8 gate (§8/BLOCKER A); a missing `DecisionPacket` fails closed to `False` | bool | boolean | N/A | EXECUTION_AUTHORITY | `UNKNOWN` if no cycle ran yet for symbol (never coerced to `True`) | `FALSE` is a genuine, meaningful value (blocked, including the "packet absent" case) | per-cycle |
| `decision.trade_allowed` (legacy pipeline field, gating input to the G8 gate) | Legacy dict pipeline verdict — an analysis/gating input the G8 gate consults, not itself the sole authority (§8/BLOCKER A) | bool | boolean | N/A | OBSERVATIONAL_TELEMETRY | `UNKNOWN` if no cycle ran yet for symbol | `FALSE` is meaningful (a blocker fired upstream of G8) | per-cycle |
| `decision.trade_allowed` (DecisionObservation copy) | Mirrored verdict for reporting only, no path back into the gate | bool | boolean | N/A | OBSERVATIONAL_TELEMETRY | same | same | per-cycle |
| `pipeline.execution_ratio` | All-signals-wide executed/refused ratio | PercentageMetric | pct | numerator=executed, denominator=all evaluated signals | OBSERVATIONAL_TELEMETRY | `UNAVAILABLE` if `activity_tracker` unreachable | `0%` is a genuine (bad) rate, not absence | per cycle |
| `attrition.dominant_blocker` | Most frequent rejection layer | str (enum-like) | — | over `RejectionStore` window | OBSERVATIONAL_TELEMETRY | `UNKNOWN` if zero rejection records at all | N/A (categorical) | `RejectionStore` record timestamps |
| `regret.canonical_freshness` | Regret v2 evaluated-horizon freshness | FreshnessStatus | enum | N/A | OBSERVATIONAL_TELEMETRY | `UNKNOWN` if no canonical evaluation has ever run | N/A | `last_canonical_evaluated_utc` |
| `system_health.boot_alive` (`ObservedValue[bool]` — **the one canonical serialized liveness field, R4.4**; `LIVENESS` remains a conceptual axis name only, §14.2, never a second serialized field or a competing `ALIVE`/`DEAD`/`UNKNOWN` enum) | Process liveness — **`CONTRACT_EXISTS`/`CHECK_IMPLEMENTATION_EXISTS` today (watchdog's own `pgrep`-based check runs), but `NOT_EXPOSED` for any independent reader** (§14.2/BLOCKER D: `watchdog_vps.py`'s alive branch only logs `log.debug(...)`, publishing nothing durable). Full mapping (§14.2): today always `value=null`/`UNKNOWN`; once a genuinely independent publisher exists (deferred to T-1 alone; O-02W-D never builds it, only consumes it), a positive observation is `value=true`/`PRESENT`, a negative observation is `value=false`/`FALSE`, an unreadable publisher record is `value=null`/`UNAVAILABLE`, and a publisher record older than its governed freshness threshold is `value=null`/`STALE` | `ObservedValue[bool]` | boolean | N/A | OBSERVATIONAL_TELEMETRY | Today: **must render `value=null`/`semantics=UNKNOWN`** for every read — never inferred from snapshot freshness, manifest presence, `process_instance_id`/`instance_relation`, PID, or S-03 output; post-T-1 integration (once T-1's independent publisher exists and the API consumes its artifact), `UNAVAILABLE` if its record cannot be read, `STALE` if it exceeds its own freshness threshold | `FALSE` (`value=false`) would be genuine (process positively observed down) once a real publisher exists; today there is no genuine value to report at all, only `UNKNOWN` | watchdog poll (once exposed), §13 |
| `system_health.health_score` | Composite scientific health (0-100), NOT a global system percentage — scoped to `MetricsSnapshot` inputs only | float | pct (0-100) | over defined `MetricsSnapshot` inputs | OBSERVATIONAL_TELEMETRY | `UNAVAILABLE` if `MetricsSnapshot` missing | `0` is a genuine (critical) score | `MetricsSnapshot` cadence |
| `mode` (portfolio/wallet) | `PAPER`/`REAL_API`/`TESTNET_API`/`UNKNOWN` — the API publishes the producer's **already-resolved provenance label** (`core/advisor_loop.py::_balance_provenance_from_mode()` or an extracted resolver with identical semantics, §7/BLOCKER E), never reinterprets a raw internal mode independently; `PAPER_TRADING_ENABLED` truthy always overrides to `PAPER` regardless of `exec_mode` | enum | — | N/A | provenance metadata, not authority | `UNKNOWN` if snapshot predates first successful mode resolution, **or if the underlying `exec_mode` was itself unrecognized (fail-closed — never defaulted to `REAL_API` or `PAPER`)** | N/A (categorical) | process-lifetime constant |
| `snapshot_id` / `cycle` / `process_instance_id` | Identity/atomicity spine | mixed | — | N/A | envelope metadata | never null in a valid snapshot | N/A | write-time |
| `source_sha` / `worktree_state` / `deployment_evidence` / `runtime_sha_evidence_status` | Claimed checkout SHA / `CLEAN`\|`DIRTY`\|`UNKNOWN` / sanitized `{status, source, evidence_ref, observed_at_utc}` object (R4.2) / `CLAIMED_ONLY`\|`VERIFIED`\|`UNKNOWN` (§15/BLOCKER C) — `source_sha` is never itself proof of what is executing; `deployment_evidence` proves file transfer only, never process-memory contents, and must never automatically upgrade `runtime_sha_evidence_status`; no `VERIFIED` runtime-evidence mechanism exists today | mixed | — | N/A | envelope metadata | `deployment_evidence` renders `UNKNOWN` if no deploy-tag/audit/verification record exists, never an assumed deployment; `runtime_sha_evidence_status` defaults `CLAIMED_ONLY` if only `git rev-parse HEAD` was read, `UNKNOWN` if nothing was recorded — never `VERIFIED` without an actual verification mechanism | N/A | write-time (claim), not a liveness/freshness clock |
| `ledger_watermark` (`logical_source`/`generation_id`/`byte_offset`/`read_at_utc`/`path`) | Point-in-time boundary for a JSONL-ledger-backed response, generation-aware (§6.1) — `byte_offset` meaningful only within its own `generation_id`; `path` is provenance only, never the sole identity. **`generation_id` is a stable opaque UUID/epoch allocated once per governed generation by the §6.1.1 sidecar** — never recomputed from file content/inode on read; a `LEGACY`/`BEST-EFFORT` fallback (§6.1.3, inode or once-captured content anchor) is labeled distinctly and is not a substitute when the sidecar is available | object | actual bytes (`byte_offset`, binary-derived, §6.1) | N/A | envelope metadata, per-resource | never null on a successful ledger read; `UNAVAILABLE` (not empty) if the referenced `generation_id` is no longer retained (§6.1 requirement 8) or if a detected ungoverned mutation invalidates the read (§6.1.2) | `byte_offset: 0` is a genuine empty-ledger read for that generation, distinct from `UNAVAILABLE` (§6.1 requirement 3) | read-time (per request) |
| `runtime_manifest.process_instance_id` / `boot_timestamp_utc` | Write-once-per-boot declaration of the most recently started producer instance's identity (§14.1) — an **identity/succession fact, not a liveness proof** (§14.2); a producer can hang or crash after writing this without it ever being revised | mixed | — | N/A | envelope metadata, cross-checked against every snapshot read | `UNKNOWN` instance relation if the manifest file itself is missing/corrupt (never coerced to `CURRENT_INSTANCE`, §14.2 rule 2) | N/A | write-time, updated once per process boot |
| `snapshot.instance_relation` (`CURRENT_INSTANCE` \| `PREVIOUS_INSTANCE` \| `UNKNOWN`) | Pure identity/succession comparison of `snapshot.process_instance_id` vs. current `runtime_manifest` (§14.2) — never a liveness claim | enum | — | N/A | envelope metadata, API-computed | `UNKNOWN` if manifest missing/corrupt | N/A | computed at read-time, not stored |
| `snapshot.runtime_state` (`CURRENT` \| `LAST_KNOWN`) | Convenience composite derived solely from `instance_relation` (§14.2) — labels data provenance/succession only, explicitly NOT a liveness claim; consumers needing liveness must read `system_health.boot_alive` separately | enum | — | N/A | envelope metadata, API-computed | N/A (always computable given the manifest) | N/A | computed at read-time, not stored |

---

## 22. CONTRACT_TEST_REQUIREMENTS (R1-4, extended R2-1/R2-2, extended R3, amended R3.1, reassigned R4, completed R4.1 — tests 23-32)

Documentation-only in this mission — these are **requirements a future
implementation mission must satisfy with real tests**, not tests written
here (and, per BLOCKER I/§21, no runtime or deployment proof of any kind
is offered by this doc-only R4 pass). Each maps directly to a semantic
guarantee this contract makes elsewhere; a contract clause with no
corresponding test requirement is not enforceable and would regress
silently.

**Mission assignment (R4 correction — the original text implied one
undifferentiated "future implementation mission"; per §21 there are
several, and each test below belongs to a specific one):**

| Test group | Belongs to |
|---|---|
| Snapshot-writer atomicity/failure-preservation (1-2), fail-passive/materialization correctness (mode override/unknown-mode, restored-position labeling) | **O-02W-C** (§21.1) |
| Ledger-generation/reader/watermark tests (5-18) | **A later ledger/API mission** (§21.2 — the sidecar/transition-protocol implementation and/or O-02W-D's ledger-reader work), not O-02W-C |
| Runtime-manifest/instance-relation/liveness tests (3-4, 13) | **O-02W-C** for the manifest-writing half (§14.1); the API-side read/label half belongs to **O-02W-D** |
| API/auth tests (routes, HMAC auth, WS) | **O-02W-D** (§21.2) exclusively — O-02W-C builds no API surface at all |
| Source-SHA/runtime-evidence tests (19-20, new below) | Three-way split (R4.4, matching tests 19-20's own bodies): **O-02W-C** (producer-side tests — `source_sha`/`worktree_state`/`deployment_evidence`/`runtime_sha_evidence_status` materialization correctness, including the fail-closed/no-upgrade cases), **O-02W-D** (the API preserves the producer's values/statuses without upgrading, inferring, or relabeling them), **T-1** (tests the future independent runtime-attestation mechanism that may legitimately produce `runtime_sha_evidence_status = VERIFIED`) |
| Builder-boundary/no-fresh-instantiation, fail-passive serialization, price-unavailability materialization, restore-vs-normal provenance, missing-`DecisionPacket` materialization, process-identity equality/no-second-identity, no-secrets whitelist (23-27, 29-30, 32, new below) | **O-02W-C** (§21.1) — the advisor-owned passive snapshot builder's own test suite |
| Current-liveness-never-fabricated test (28, new below) | Phase-explicit three-way split, matching test 28's own body (R4.5 — one owner for the publisher): **O-02W-C** (the producer snapshot builder never emits `true`/`PRESENT`, always `value=null`/`UNKNOWN`), **O-02W-D pre-T-1** (the API exposes the honest `value=null`/`UNKNOWN` state with zero inference; it never builds the publisher), **T-1 integration** (T-1 is the sole mission authorized to implement the independent liveness publisher and owns the integration work needed for the API to consume it; only after T-1 integration does the API read T-1's artifact and map it to `true`/`PRESENT`, `false`/`FALSE`, `null`/`UNAVAILABLE`, or `null`/`STALE`) |
| No-fabricated-`trace_id` test (31, new below) | **O-02W-C** (materialization must not synthesize the field) and **O-02W-D** (API exposure must not synthesize it either) — both missions' test suites carry this assertion independently |

1. **Reader never observes a partial canonical JSON snapshot.** A test
   that concurrently reads the snapshot file while a writer repeatedly
   replaces it (tight loop, many iterations) must assert every read
   either fully parses or the file simply doesn't exist yet — never a
   `json.JSONDecodeError` from a torn/partial read. Exercises §1.3 item
   1-3 (atomic-write requirements) and the reader-atomicity claim.
2. **Failed serialization preserves the previous valid snapshot.** A
   test that forces the serialization step to raise (e.g. a
   non-JSON-serializable value injected) must assert the destination
   file's content and mtime are unchanged after the failed write
   attempt — never truncated, never partially overwritten. Exercises
   §1.3 item 4.
3. **A previous-runtime snapshot is detectable immediately after
   restart.** A test that (a) writes a snapshot with
   `process_instance_id=I1`, (b) publishes a fresh `runtime_manifest`
   with `process_instance_id=I2` (simulating a restart) without yet
   writing a new domain snapshot, must assert the API-level read
   immediately reports `runtime_state=LAST_KNOWN` / `stale_reason=
   PRODUCER_RESTARTED` for the I1 snapshot — with zero delay tied to
   snapshot age. Exercises §14.1 steps 1-3.
4. **A stale-identity snapshot cannot be labeled `CURRENT` merely
   because `age < stale_after`.** A test must construct the specific
   case where the I1 snapshot is *well within* its normal freshness TTL
   (e.g. written 2 seconds ago against a 30-second `stale_after`) yet a
   newer `runtime_manifest` already shows `I2` — and assert the label is
   still `LAST_KNOWN`, proving identity comparison overrides age-based
   freshness rather than being redundant with it. Exercises §14.1's
   core invariant directly (this is the test that would fail against
   the original, pre-R1 contract text).
5. **A partial final JSONL line does not silently become confirmed-
   complete history.** A test that appends a deliberately truncated
   (non-newline-terminated, unparseable) final line to a ledger fixture
   must assert the reader's returned `byte_offset` stops at the last
   *complete* line before the truncated one, and that the response is
   not silently presented as the full/final trade list without any
   signal that a tail was excluded. Exercises §6.1 requirement 2.
6. **A historical response exposes a deterministic ledger watermark.**
   A test must assert every JSONL-ledger-backed response (trades,
   regret, decisions) includes a `ledger_watermark` object with a
   non-null `byte_offset` on any successful read, including a
   confirmed-empty ledger (`byte_offset: 0`, distinct from
   `UNAVAILABLE` — requirement 8 below). Exercises §6.1 requirement 1.
7. **Replaying the same snapshot identity + ledger watermark
   reconstructs the same operator-visible historical state.** A test
   must (a) capture a response's `snapshot_id`/`cycle` and
   `ledger_watermark.byte_offset`, (b) append additional events to the
   ledger (simulating time passing / new trades), (c) re-read the
   ledger truncated/bounded to the originally-captured `byte_offset`,
   and assert the reconstructed view (including which trades appear
   `is_open` vs closed) is byte-for-byte identical to the original
   response's trade list — proving requirement 4 of §6.1 (an OPEN whose
   CLOSE lies beyond the watermark stays open for that historical view)
   and the reproducibility claim in §1.3.
8. **`ZERO`/`EMPTY` remains distinct from `UNKNOWN`/`UNAVAILABLE` across
   all of the above failure modes.** A consolidated assertion across
   tests 1-7: a confirmed-empty ledger, a confirmed-zero equity, and a
   confirmed-zero position count must never share a response shape with
   an unreadable file, a missing manifest, or a pre-first-snapshot
   producer state. Exercises §17 (FRESHNESS_CONTRACT)'s "no timestamp ⇒
   UNKNOWN, missing file ⇒ UNAVAILABLE, not zero, not healthy" rule as
   applied specifically to the new mechanisms this R1 introduces
   (watermarks, manifest) rather than only to the domains already
   covered by the original contract text.

**Added by R2-1 (ledger rotation safety):**

9. **Rotation between two reads changes generation identity.** A test
   must (a) read a ledger fixture and capture its `ledger_watermark`,
   (b) run the equivalent of `rotate_jsonl.sh`'s `mv`+`touch` sequence
   against that fixture, (c) read again, and assert the second read's
   `generation_id` differs from the first even though `path`/
   `logical_source` are identical. Exercises §6.1 requirement 6.
10. **The same byte offset against another generation is rejected for
    replay.** A test must attempt to replay a captured `byte_offset`
    against a *different* `generation_id` (e.g. the post-rotation empty
    file, or an unrelated fixture of coincidentally similar size) and
    assert the API refuses with an explicit error rather than returning
    a result that silently misattributes bytes from the wrong
    generation. Exercises §6.1 requirement 7.
11. **Concurrent rotation cannot misattribute the opened generation**
    (amended R3.1)**.** A test must open a ledger read (or capture its
    `generation_id` at open time), then perform the `mv`+`touch`
    rotation sequence while that read is in flight / before a
    subsequent read of the same handle, and assert all bytes attributed
    to that read remain labeled with the originally-opened
    `generation_id`, never silently relabeled to the post-rotation
    generation. **R3.1 addition:** a second case must specifically
    construct a reader that queries the sidecar *during* the
    `TRANSITIONING` interval (§6.1.4) — after `TRANSITIONING` is
    published but before the final active/archive mapping is — and
    assert the reader rejects or retries rather than opening the ledger
    path under an indeterminate state; a third case must assert the
    `fstat()`-based physical-binding check (§6.1.4 reader protocol steps
    4-5) catches a rotation that raced between the reader's initial
    sidecar read and its `open()` call, even if the sidecar's own
    revision check alone would not have. Exercises §6.1 requirement 9
    and §6.1.4 in full.
12. **Watermark offset is measured in actual bytes, including non-ASCII
    UTF-8 content.** A test must construct a ledger fixture containing
    at least one record with non-ASCII UTF-8 content (e.g. a symbol or
    free-text field with multi-byte characters), read it, and assert
    the resulting `byte_offset` matches an independently-computed
    binary byte count (e.g. via `os.path.getsize()` on a truncated copy,
    or `len(line.encode("utf-8"))` accumulation) — not a text-mode
    `tell()` cookie, which this contract's §6.1 correction identifies as
    unsafe for exactly this case. Exercises §6.1's byte-offset-unit
    correction.

**Added by R2-2 (identity vs. liveness):**

13. **Matching identity does not by itself prove liveness.** A test must
    construct the specific sequence: manifest declares I2, the newest
    snapshot also carries I2 (so `instance_relation = CURRENT_INSTANCE`
    and the composite `runtime_state = CURRENT`), and then the producer
    process is killed/hung with no further writes — and assert that a
    read at this point still correctly reports `system_health.boot_alive`
    as `value=false`/`semantics=FALSE` (if a publisher positively
    observes it down) or `value=null`/`semantics=UNKNOWN` (today, absent
    any publisher — R4.4) independently of `instance_relation`/
    `runtime_state` still showing `CURRENT_INSTANCE`/`CURRENT`. This is
    the test that would fail against a naive implementation that infers
    liveness from identity match alone — exactly the conflation §14.2
    corrects.

**Added by R3 (generation identity finalization):**

14. **Stable normal append, including growth through a prospective
    prefix length.** A test must (a) create one governed generation and
    capture its sidecar-assigned `generation_id`, (b) append several
    records to it, deliberately including growth from a file smaller
    than any prospective content-hash prefix length (e.g. append past
    the naive candidate's N-byte boundary from R2-1), and (c) assert the
    `generation_id` remains byte-for-byte unchanged throughout — proving
    it is not recomputed from file content or size. This is the test
    that would fail against R2-1's original naive-recompute suggestion,
    exactly the instability §6.1's canonical-model correction identifies.
15. **Rotation allocates a new generation; a retained archive keeps the
    old one, including through rename and gzip compression** (amended
    R3.1)**.** A test must perform the equivalent of
    `scripts/rotate_jsonl.sh` (`mv`+`touch`) and assert (a) the new
    active ledger at the logical path receives a *new* sidecar-allocated
    `generation_id`, distinct from the pre-rotation one, and (b) the
    retained archived file's `generation_id` — read via its recorded
    location in the sidecar (§6.1.1) — is unchanged from what it was
    before rotation. **R3.1 addition:** the test must continue past the
    `mv` to also run `rotate_jsonl.sh`'s `gzip` step on the archive and
    assert the `generation_id` is *still* unchanged after compression
    (proving rename and compression are both identity-preserving
    physical-representation changes, per §6.1's corrected model); a
    further case must capture a `(generation_id, byte_offset)` watermark
    against the plain-text archive, compress it, then replay the same
    watermark against the now-`.gz` representation and assert the
    implementation decompresses before applying the offset, reproducing
    byte-identical results to the pre-compression read (never applying
    the offset against compressed byte positions, per §6.1's canonical-
    byte-offset-representation correction).
16. **Governed reset creates a new generation or invalidates the
    previous one.** A test must perform a controlled truncate/reset
    against a ledger and assert either (a) a new `generation_id` is
    allocated for the post-reset active ledger, or (b) the previous
    generation's sidecar entry is explicitly marked `INVALIDATED` — and
    that no code path allows the previous identity to silently persist
    unchanged against the now-different content. Exercises §6.1.2's
    governed-reset invariant and binding requirement 11.
17. **A detectable ungoverned destructive mutation is surfaced as an
    integrity violation, never silently trusted** (amended R3.1 for
    precision — this test asserts a specific detectable case, not
    universal detection of every possible ungoverned mutation, which
    §6.1.2 explicitly does not claim). The test: (a) perform a normal
    read and capture a valid watermark with `byte_offset > 0`; (b)
    truncate the *same inode* (e.g. `ftruncate()` on a fresh `open()` of
    the same path, or equivalent) to a size **below** that confirmed
    `byte_offset` — the exact same-inode, content-destroyed case §6.1's
    canonical-model correction describes; (c) assert that on the next
    read, the observed size rollback (or an `fstat()`-based binding
    inconsistency, §6.1.4) is detected and invalidates the read — the
    reader must return an explicit integrity-violation/invalid state,
    never silently reuse the old watermark against the truncated
    content. **Explicit limitation preserved, not overridden by this
    test:** an out-of-protocol mutation that leaves no observable
    inconsistency (e.g. content edited in place without changing size,
    inode, or anything else the reader observes) may not be detectable
    without stronger integrity instrumentation than this contract
    requires — this test targets the case that *is* required to be
    caught, not a claim of universal coverage. Exercises §6.1.2's
    ungoverned-mutation invariant and binding requirement 12.
18. **Legacy fallback is never presented as canonical-equivalent.** A
    test using a `LEGACY`/`BEST-EFFORT` fallback identity (inode-only,
    or a once-captured content anchor) must assert the response/
    diagnostic explicitly labels it as such, and a separate test must
    confirm the fallback path is never silently substituted for a
    sidecar-backed canonical `generation_id` when the sidecar is
    actually available. Exercises §6.1.3 and binding requirement 13.

All R1/R2/R3 requirements remain in force and are not superseded by the
above — in particular: actual binary-byte offsets (test 12), incomplete
final-line handling (test 5), identity distinct from liveness (test 13),
`UNKNOWN != ZERO` and `UNAVAILABLE != EMPTY` (tests 3, 8 above and R3
tests 16-17, which extend the same principle to governed/ungoverned
generation transitions). **R3.1 extends this same principle once more:**
`TRANSITIONING != AVAILABLE` and `TRANSITIONING/UNAVAILABLE != EMPTY` —
a reader observing the sidecar's `TRANSITIONING` state (§6.1.4) must
reject/retry rather than return any result, including an empty one; an
empty successful result is only ever correct for a confirmed `ACTIVE`
generation genuinely containing zero valid lines (requirement 3), never
as a stand-in for "a transition was in progress and I couldn't tell."

**Added by R4 (BLOCKER C — source claim vs. runtime proof, negative
tests):**

19. **A claimed source SHA is never presented as `VERIFIED` runtime
    proof, and `VERIFIED` deployment evidence never auto-upgrades it
    (R4.4 — owning missions made explicit, matching the mission table
    above): O-02W-C (producer), O-02W-D (API preservation), T-1 (future
    verification mechanism).**
    - **O-02W-C** (producer-side — the snapshot builder's own test
      suite, §21.1): a test must construct a snapshot exposing
      `source_sha` derived only from `git rev-parse HEAD` (no
      independent verification mechanism run) and assert the producer
      materializes `runtime_sha_evidence_status = CLAIMED_ONLY` (or
      `UNKNOWN` if not even recorded), never `VERIFIED` — and a separate
      assertion that no string the producer materializes ever states or
      implies "the SHA actually running" for a `CLAIMED_ONLY` value. A
      second case must construct `deployment_evidence.status = VERIFIED`
      (a deploy-tag/audit record proving file transfer) alongside no
      independent runtime-attestation mechanism, and assert the
      producer's own `runtime_sha_evidence_status` still materializes
      as `CLAIMED_ONLY` — proving `VERIFIED` deployment evidence never
      by itself upgrades runtime-SHA evidence status. A third case must
      assert that with no deploy-tag/audit/verification record at all,
      the producer materializes `deployment_evidence.status = UNKNOWN`,
      never an assumed deployment, and that `evidence_ref` never carries
      a secret path, credential, token, or environment dump. No producer
      artifact may claim `VERIFIED` runtime evidence without an actual
      independent runtime-attestation mechanism behind it.
    - **O-02W-D** (API): a test must assert the API exposes exactly the
      producer's materialized `source_sha`/`worktree_state`/
      `deployment_evidence`/`runtime_sha_evidence_status` values/statuses
      unchanged — never upgrading `CLAIMED_ONLY` to `VERIFIED`, never
      inferring a status the producer did not record, and never letting
      a `deployment_evidence.status = VERIFIED` value upgrade
      `runtime_sha_evidence_status`.
    - **T-1**: tests the future independent runtime-attestation
      mechanism that may legitimately produce
      `runtime_sha_evidence_status = VERIFIED` — no such mechanism
      exists today; this case applies only once T-1 builds one.

    Exercises §15's four-way source-claim/worktree-state/deployment-
    evidence/runtime-evidence distinction and the R4.2
    `deployment_evidence` schema.
20. **A dirty or unchecked worktree is never silently reported as
    `CLEAN` (R4.4 — owning missions made explicit): O-02W-C (producer),
    O-02W-D (API preservation).**
    - **O-02W-C** (producer-side): a test must construct the case where
      `git status --porcelain` was never run and assert the producer
      materializes `worktree_state = UNKNOWN`; a second case must
      construct `git status --porcelain` reporting uncommitted changes
      and assert the producer materializes `worktree_state = DIRTY` —
      never defaulted to `CLEAN` merely because nothing contradicts it.
    - **O-02W-D** (API): a test must assert the API exposes exactly the
      producer's materialized `worktree_state` value unchanged — never
      defaulting an absent, `UNKNOWN`, or `DIRTY` value to `CLEAN`.

    Exercises the same §15 distinction, `worktree_state` specifically.

**Added by R4 (BLOCKER E — mode provenance override + unknown-mode
cases):**

21. **`PAPER_TRADING_ENABLED` overrides `exec_mode` regardless of its
    value.** A test must set `PAPER_TRADING_ENABLED` truthy alongside an
    `exec_mode` of `"live"` or `"testnet"` and assert the exposed mode
    provenance resolves to `PAPER` — proving the override in
    `_balance_provenance_from_mode()` (or the reused equivalent) is
    preserved by whatever the API publishes, never independently
    reinterpreted. Exercises §7's override-preservation requirement.
22. **An unrecognized `exec_mode` fails closed to `UNKNOWN`, never
    `REAL_API`.** A test must pass an `exec_mode` value outside
    `{"paper","live","testnet"}` (with `PAPER_TRADING_ENABLED` falsy) and
    assert the exposed mode provenance is `UNKNOWN` — and a second
    assertion that no code path in the exposure layer defaults an
    unrecognized mode to `REAL_API`. Exercises §7's fail-closed
    requirement, the single most safety-critical case in this contract's
    mode vocabulary (a false `REAL_API` label on paper-mode data would be
    exactly the mis-attribution ADR-0007/O-01 already warn against).

**Added by R4.1 (§21.1/O-02W-C boundary, process-identity, secrets, and
trace_id — completing the future-test coverage §22's own mission table
already anticipated but had not yet enumerated as numbered items):**

23. **The builder never instantiates a fresh `MexcSimulator`/
    `WalletSync`/other process-local telemetry owner.** A test must
    inspect (or exercise via dependency injection) the snapshot-builder
    call site and assert it only ever reads the **already-existing, live
    references** the advisor process already holds (the running
    `MexcSimulator` instance, the running `WalletSync` singleton, etc.)
    — never constructs a new instance of any of these classes itself.
    Constructing a fresh instance inside the builder would silently
    reintroduce the exact process-boundary defect this contract's
    `PROCESS_BOUNDARY_VERDICT` forbids, just inside the same process
    instead of a second one. Exercises §2.3/§21.1's "reads already-
    existing live objects" requirement.
24. **Serialization/atomic-write failure is fail-passive.** Extending
    test 2: a test must assert that a forced serialization or
    write-step failure is (a) logged and counted via a metric/counter,
    (b) never raised into or propagated through the advisor loop's own
    call stack, (c) never changes `trade_allowed`/`is_actionable()` or
    any other decision-path value, and (d) never leaves a partial final
    snapshot file at the canonical path (the pre-existing valid snapshot
    remains byte-for-byte unchanged). Exercises §21.1's fail-passive
    guarantee directly, not merely the write-preservation half already
    covered by test 2.
25. **`_fetch_price() == 0.0` maps to `UNAVAILABLE`, never a legitimate
    zero price, and any price-dependent unrealized PnL is `UNAVAILABLE`
    too.** A test must force `_fetch_price()` to return `0.0` (no
    exchange client wired, or a raised/caught fetch exception — both
    collapse to `0.0` at the source, §2.1/§5/BLOCKER A) and assert the
    materialized `open_positions[].current_price` renders `UNAVAILABLE`
    (never `price: 0`) and the corresponding `unrealized_pnl_usd`/`_pct`
    for that position also render `UNAVAILABLE` (never a fabricated
    `0`) — proving the unavailability propagates through the derived
    value, not just the raw price. Exercises §5's per-position field
    table and the `REQUIRED_FIELD_CONTRACT_TABLE` row for
    `current_price`.
26. **Normal-open vs. restored-position provenance is distinguished, and
    ledger enrichment joins by exact `pos_id == trade_id` only, owned by
    the O-02W-C producer.** A test must (a) construct a normally-opened
    position (via `_fill_market()`) and assert its materialized
    `personality`/`regime` are sourced from the originating `MexcOrder`
    with full confidence, (b) construct a restored position (via
    `_restore_positions()`) and assert `personality: "restored"` and
    `regime: "unknown"` with an explicit `restored_without_regime: true`
    (or equivalent) marker are exposed, never presented with the same
    confidence as a normal open, and (c) assert that any historical
    regime/provenance enrichment join against the ledger is performed
    **only** by exact `MexcPosition.pos_id == ledger TradeEvent`/
    `CompleteTrade.trade_id` match — a test fixture with two ledger
    records sharing the same `symbol` but different `trade_id`s must
    confirm the join never falls back to a symbol-only match (symbol is
    usable only as a post-join consistency check), that absent an exact
    `pos_id`/`trade_id` match or on a symbol conflict the result is
    `UNKNOWN`/`UNAVAILABLE`, never guessed from the symbol-sharing
    record, and (d) assert this enrichment happens in the advisor-owned
    O-02W-C producer/materializer, with the API-side test suite (§21.2)
    separately asserting the API exposes the already-materialized result
    without repairing or re-inferring it independently. Exercises
    §5/§19/BLOCKER F in full.
27. **A missing `DecisionPacket` makes the final authorization `False`,
    with correct authority labels preserved.** A test must construct the
    G8-gate case where `decision_packet` is `None` for a cycle and assert
    the materialized `decision.is_actionable` renders `False` (never
    `UNKNOWN` treated as truthy, never inherited from the legacy
    pipeline's own `trade_allowed`), labeled `authority:
    "EXECUTION_AUTHORITY"`, while a legacy-pipeline `trade_allowed: True`
    for the same cycle is separately exposed and correctly labeled
    `authority: "OBSERVATIONAL_TELEMETRY"` — proving the materialization
    never conflates the two tracks or lets the observational track stand
    in for the missing authority. Exercises §8/BLOCKER A and the
    `REQUIRED_FIELD_CONTRACT_TABLE` rows for `decision.is_actionable`/
    `decision.trade_allowed`.
28. **Current liveness remains `value=null`/`semantics=UNKNOWN`,
    `NOT_EXPOSED`, never a fabricated `true`/`PRESENT`, until an
    independent liveness publisher exists (R4.4 — one canonical field,
    `system_health.boot_alive: ObservedValue[bool]`, split by owning
    mission, not one undifferentiated test).**
    - **O-02W-C** (the producer snapshot): a test must assert the
      canonical operator snapshot builder never emits `value=true`/
      `PRESENT` for `system_health.boot_alive` — the materialization
      step only ever writes `value=null`/`semantics=UNKNOWN`, since it
      has no independent liveness publisher to read from (§14.2/
      BLOCKER D).
    - **O-02W-D pre-T-1** (the API, before T-1's independent publisher
      exists): a test must assert the API layer exposes exactly the
      `value=null`/`semantics=UNKNOWN` state honestly, with zero
      inference — it never derives `true`/`false` from
      `instance_relation`, manifest presence, or snapshot freshness, and
      against today's actual system (no publisher built yet) every read
      renders `value=null`/`UNKNOWN`, never `true`/`PRESENT`. This test
      does not implement or assume any publisher; O-02W-D is a consumer/
      presentation layer only, never the publisher's builder.
    - **T-1 integration** (the sole owner of the independent publisher,
      including the integration work the read-only API needs to consume
      it): a test, exercised only once T-1's independent liveness
      publisher exists, must confirm (a) the publisher is the sole
      evidence source — no other signal in this contract's model
      (snapshot freshness, manifest presence, `process_instance_id`/
      `instance_relation`, PID, or S-03 output) may ever authorize a
      value — and (b) the API, after T-1 integration, reads T-1's
      independent artifact and maps its exact evidence deterministically:
      a positive observation to `value=true`/`PRESENT`, a negative
      observation to `value=false`/`FALSE`, an unreadable record to
      `value=null`/`UNAVAILABLE`, and a record older than its governed
      freshness threshold to `value=null`/`STALE` — never silently
      coerced to `PRESENT`.

    Exercises the negative invariant added to §14.2 by this correction.
29. **`process_instance_id` equality holds across S-03, the operator
    snapshot, and the operator manifest; a restart creates a new
    identity.** A test must (a) read all three sources
    (`RuntimeProvenanceSnapshotWriter`'s output, the canonical operator
    snapshot, `operator_runtime_manifest.json`) for one process lifetime
    and assert all three `process_instance_id` values are identical, and
    (b) restart the simulated process and assert all three sources now
    agree on a **new**, different value — never a stale mix where one
    source still reports the pre-restart identity. Exercises §15's
    equality invariant (R4.1) directly.
30. **No component independently regenerates a second process
    identity.** A test must assert that neither the operator-snapshot
    writer nor the operator-manifest writer ever calls its own
    UUID/PID-timestamp generation for `process_instance_id` when a
    shared value is already available from the advisor bootstrap (the
    sole identity authority; S-03 is a passive consumer/projection) —
    i.e. the value is always propagated, never freshly minted a second
    time within the same process lifetime. Exercises §15's "no writer
    may independently regenerate/infer/reconcile a second identity"
    rule.
31. **No distinct `trace_id` is fabricated or aliased from convenient
    identifiers.** A test must assert that no API/snapshot response ever
    contains a field literally named `trace_id`, and that no code path
    synthesizes one by concatenating, hashing, or otherwise deriving a
    value from `packet_id`/`context_id`/`created_cycle_id` — those three
    identifiers remain independently readable and semantically distinct
    in every response. Exercises §8/§19/§20/BLOCKER F's
    `NOT_EXPOSED_AS_DISTINCT_FIELD` classification (R4.1).
32. **No secret material is ever serialized.** A test must assert the
    canonical snapshot and any future API response are produced via a
    **strict field whitelist** (an explicit allow-list of named fields,
    never a generic `__dict__`/`vars()`/object dump of `WalletSync`,
    `MexcSimulator`, or any exchange-client object) and must specifically
    assert the absence of: raw environment-variable dumps, API keys,
    exchange credentials, Telegram bot tokens, private keys, passwords,
    or any value derived from a secret in a way that could reconstruct
    it (e.g. a token substring). This is the hard "No secrets" constraint
    already stated in §15, made testable. Exercises §15's no-secrets
    invariant and §16's read-only/security posture.

---

## PROCESS_BOUNDARY_VERDICT

**Can a separate web API safely instantiate and read `MexcSimulator`
directly?**
**NO.** `MexcSimulator._positions` is a plain instance dict
(`paper_trading/mexc_simulator.py:267`), populated only by the advisor
process's own `start()`/`_restore_positions()`/live monitor loop. A
second process's `MexcSimulator()` call creates an independent,
disconnected object whose `_positions` starts empty and can, at best,
partially and staleley reconstruct entry-side fields from the ledger —
never the live mark-to-market state of the actually-running machine.
Confirmed by direct source inspection, not inferred.

**Can a separate process call `get_wallet_sync()` and be guaranteed to
share the runtime advisor singleton?**
**NO.** `infra/wallet_sync.py`'s `_singleton` (line 223) is a
module-level global inside one Python interpreter process. A second OS
process is a second Python interpreter with its own independently-`None`
-initialized `_singleton` — `get_wallet_sync()` there constructs a *new*
`WalletSync` instance, never the advisor process's. This is a structural
property of the OS process model (no shared memory/IPC exists between
these two processes in the current architecture), not a bug that could
be patched without introducing IPC — which this contract deliberately
avoids (§1.2). One practical mitigation exists and is documented (§2.2):
in **paper mode only**, `get_balance()` happens to recompute from disk
each call, so a second process's *own* singleton, configured with the
correct `mode`, would coincidentally compute the same number — but this
is a property of `get_balance()`'s implementation, not a guarantee of
singleton sharing, and does not hold in live/testnet mode at all.

**What state therefore requires materialization by the producer
process?**
1. `MexcSimulator._positions` — full open-position detail, mark-to-market
   at snapshot time (§2.1, §5).
2. `WalletSync` live/testnet-mode balance, cached value, and capital `X`
   (bootstrap result) — no safe cross-process re-derivation exists
   (§2.2).
3. `WalletSync.mode` itself, as explicit provenance metadata (§7) — a
   second process has no way to know which mode the advisor's singleton
   was constructed with without being told.
4. The current/latest `DecisionPacket` state per symbol during its
   in-memory lifecycle (§8) — closed/terminal packets that reach their
   disk sink (`databases/decision_packets_YYYY-MM-DD.jsonl`, the
   DecisionPacket history ledger, §8.1) do not require this
   materialization, only the live, in-flight state does. (`black_box.
   jsonl` is a separate, distinct ledger — outcome/provenance evidence,
   never a substitute for `DecisionPacket` history, §8.1/BLOCKER H.)
5. Paper-mode `WalletSync.get_balance()` — not strictly *required*
   (re-derivable, §2.2), but materialized anyway by this contract's
   design (§2.3) to give the API one single source of truth instead of
   re-implementing wallet arithmetic in a second place (reuse-before-
   creation, O-01 principle).

Everything else this contract catalogues (realized PnL/closed trades,
Regret v2 state, rejection/attrition counts, `SystemSnapshot`'s existing
JSON-dump fields) is already disk-resident and may be read directly by
the API process without producer materialization, because it never
depended on a single process's live heap in the first place.
