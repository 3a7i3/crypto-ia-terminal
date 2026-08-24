# FORENSIC AUDIT — SCIOS / Crypto AI Terminal

**Date:** 2026-08-24
**Mode:** FORENSIC OBSERVATION ONLY — zero data loss, no code/process/config changes
**Subject:** PID 423 — `core/advisor_loop.py` (long-lived, PPID 1, port 8080)
**Auditor scope note:** The auditor has **no direct access to the VPS**. Sections
marked **[VPS-PENDING]** require the read-only runbook in §16 to be run and pasted
back. All other findings are derived by **static analysis of the repository at
branch `claude/crypto-ia-deployment-51az7k`** and are labelled accordingly.

Evidence grades used throughout: **OBSERVED FACT** (measured on the VPS or in
repo), **STRONG EVIDENCE** (code proves the mechanism; symptom predicted),
**HYPOTHESIS** (plausible, not yet proven), **UNKNOWN** (needs evidence).

---

## 1. EXECUTIVE SUMMARY

The single most important finding is a **structural file-descriptor and data-loss
defect in the JSON logging layer** (`observability/json_logger.py`). It fully
explains the observed symptom — many descriptors of PID 423 pointing at a
**deleted** `logs/runtime/2026-08-22.jsonl.7`.

**Mechanism (STRONG EVIDENCE):** every module that logs through the structured
logger gets its **own** `RotatingFileHandler` bound to the **same** shared
category file (`logs/<category>/<date>.jsonl`). The repository contains **190
distinct modules** calling `get_logger(...)`, and `INFO/DEBUG/WARNING` all route
to the single `runtime` category. So a long-lived process ends up with **many
independent `RotatingFileHandler` instances writing the same file**.
`RotatingFileHandler` assumes it is the *only* writer. When any one instance
crosses 50 MB it renames/unlinks the backups (`.1`…`.7`), but the other handlers
keep the **now-deleted inode open and keep writing to it**. Those records become
invisible and are **permanently lost when the process exits**; meanwhile the open
deleted inodes **retain disk space invisibly** until PID 423 dies.

This is not a cosmetic leak. It is simultaneously: (a) an FD leak, (b) an
invisible-disk-consumption bug, (c) a **silent data-loss** bug for `runtime`,
`errors`, and `incidents` streams after each rotation, and (d) a
"daily" file scheme that does **not actually rotate by day**.

Secondary: the process **is** protected against duplicate execution by a robust
`flock` singleton (`logs/advisor.lock`), with two narrow edge-case risks (PID
recycling can block a legitimate restart; a stale-lock cleanup race could
theoretically admit a second instance).

No remediation is proposed in this document per mission rules. §16 lists the
minimal evidence still required before a fix is designed.

---

## 2. CRITICAL FINDINGS

| # | Finding | Grade | Section |
|---|---------|-------|---------|
| C1 | N `RotatingFileHandler` instances on one shared category file → FD leak + deleted-inode retention | STRONG EVIDENCE | §5, §6 |
| C2 | Records written to a deleted inode after rotation are **lost** (silent) | STRONG EVIDENCE | §5, §8 |
| C3 | "Daily" JSONL files do **not** rotate by date in a long-lived process (date frozen at first log call) | STRONG EVIDENCE | §5 |
| C4 | Concurrent rollover across handler instances can corrupt/interleave lines | HYPOTHESIS | §8 |
| C5 | PID recycling can make the singleton lock **block a legitimate restart** | HYPOTHESIS | §4 |
| C6 | Stale-lock cleanup race could admit a **second instance** in a narrow window | HYPOTHESIS | §4 |
| C7 | FD count, socket states, actual retained disk — **not yet measured** | UNKNOWN / [VPS-PENDING] | §6, §7, §16 |

---

## 3. OBSERVED RUNTIME ARCHITECTURE

**OBSERVED FACT (from prior session logs, not this audit's measurement):**
- PID 423 runs `.venv/bin/python core/advisor_loop.py`, cwd `/home/mathieu/crypto_ai_terminal`, PPID 1.
- Mode `OBSERVATION ONLY (V9_ADVISOR_ONLY=true)`, capital ≈ $683 paper.
- BOOT markers previously reported: `verrou précédent non nettoyé (PID … — arrêt non-propre)` — see §4.
- A TCP listener on **:8080** exists (STRONG EVIDENCE it is the chart/dashboard server — `capital_deployment/chart_server.py` / `dashboard_api.py` bind a port; **[VPS-PENDING]** confirm which).

**PPID = 1** ⇒ the process was **re-parented to init** ⇒ its original launcher
exited. This is consistent with `nohup … &` from an interactive shell
(`scripts/vps_restart.sh`), **not** a systemd-supervised unit (a systemd service
would show PPID = 1 too, but the unit is absent — see §4/§11). **STRONG
EVIDENCE:** the real engine is launched by `scripts/vps_restart.sh`
(`nohup env PYTHONPATH=… .venv/bin/python3 core/advisor_loop.py`), which
detaches → PPID 1.

---

## 4. PROCESS LIFECYCLE MAP & SINGLETON/LOCK (Objectives A, B, I)

### Launch (STRONG EVIDENCE, repo)
- Canonical launcher: `scripts/vps_restart.sh` — anchored `pkill -f 'core/advisor_loop\.py$'`, then `nohup env PYTHONPATH=$HOME/crypto_ai_terminal .venv/bin/python3 core/advisor_loop.py >> logs/advisor.log 2>&1 &`.
- `scripts/crypto_advisor.service` (systemd) exists **in the repo** but targets `advisor_loop.py` (root, the *passive* observer bot) and user `mathieuhasard111` — **not** `core/advisor_loop.py` and not user `mathieu`. **HYPOTHESIS:** this unit is either not installed or points at the wrong target on this VPS. **[VPS-PENDING]** `systemctl status crypto_advisor.service crypto-advisor.service`.
- `watchdog_vps.py` exists and, per `RECOVERY.md`, runs in **ALERT-ONLY** mode (`RESTART_DISABLED_UNTIL_RECONCILIATION=1`) — it does **not** auto-restart the engine. **STRONG EVIDENCE** (code + doc); **[VPS-PENDING]** confirm the watchdog process is alive and which code version it holds in memory.

### Duplicate-execution safety (STRONG EVIDENCE, `core/advisor_loop.py:2878–3002`)
- Exclusive `fcntl.flock(LOCK_EX | LOCK_NB)` on `logs/advisor.lock`; `FD_CLOEXEC` set so children don't inherit the lock; PID written into the file; `atexit` releases it.
- Stale-lock handling: on `BlockingIOError`, reads stored PID; `os.kill(pid, 0)`; if `ProcessLookupError` → unlink lock and retry **once**; if alive → `exit(1)`.

**Answers to the mission's questions:**
- *Can two instances run simultaneously?* **Normally NO** (OS-level flock). **HYPOTHESIS (C6):** a race between `os.unlink(lockfile)` (stale cleanup) and a concurrent starter reopening a fresh file could let two `flock` calls succeed on two different inodes. Narrow; requires two starts within milliseconds.
- *Can a stale lock prevent restart?* **HYPOTHESIS (C5): YES via PID recycling.** If the dead engine's PID has been reused by any live process, `os.kill(pid,0)` succeeds, the code assumes the engine is alive, and `exit(1)`. This matches the class of "restart does nothing / exits immediately" symptoms.
- *Can a restart create a second process while the first is alive?* **NO** through this lock (second exits 1). The only way is bypassing `vps_restart.sh` with a different cwd/lock path (`ADVISOR_LOCK_FILE` override).

**OBSERVED FACT (prior logs):** BOOT reported the lock **pre-existed** and the
previous PID did not clean up ⇒ previous stop was **non-clean** (SIGKILL or crash;
`atexit` did not run). The OS still released the flock on death, so restart
succeeded. This is expected and safe, but it means **`atexit`-based flushing is
not guaranteed to run** — relevant to §8 data durability.

---

## 5. LOGGING ARCHITECTURE MAP (Objective C) — ROOT OF C1/C2/C3

Two independent logging systems coexist:

### System 1 — stdlib root logging (`core/advisor_loop.py:650`)
- `logging.basicConfig` with `StreamHandler(stdout)` + `RotatingFileHandler("logs/advisor_loop.log", 10 MB, backupCount=5)`.
- Runs **once** at module import (basicConfig is a no-op if root already has handlers). **Low risk.** This is the `advisor_loop.log` / nohup target.

### System 2 — structured JSON logger (`observability/json_logger.py`) — **DEFECTIVE**
- `get_logger(module, category)` → one `StructuredLogger` per `module:category` (factory-cached, `_loggers`, line 248–258).
- **But** `StructuredLogger._get_logger(cat)` (line 131–160) creates, **per (module, category)**, a brand-new `RotatingFileHandler(LOG_ROOT/cat/<date>.jsonl, maxBytes=50 MB, backupCount=7)` and `addHandler`s it to a logger named `sys.<module>.<category>` with `propagate=False`.

| Attribute | Value (STRONG EVIDENCE) |
|---|---|
| Source | `observability/json_logger.py:143` |
| Target | `logs/<category>/<YYYY-MM-DD>.jsonl` (category ∈ runtime, trading, ai, market, errors, incidents, decisions, audits) |
| Open mode | append (RotatingFileHandler default), one **new** handler **per module** |
| Open frequency | lazily, first log call per (module, category); **never closed** for process lifetime |
| Close behavior | none (no `removeHandler`/`close`; relies on process exit) |
| Rotation | **size only**, 50 MB, `backupCount=7` → `.1`…`.7`, `.7` unlinked on roll |
| Writers per file | **up to N-modules** (see below) — the fatal design flaw |

**Magnitude (STRONG EVIDENCE):** `grep get_logger` → **190 modules**. Every one
that emits INFO/DEBUG/WARNING maps to category `runtime`
(`_LEVEL_TO_CAT`, line 117–123). ⇒ up to **~190 `RotatingFileHandler` instances
all bound to the same `logs/runtime/<date>.jsonl`**.

**C1 — FD leak:** N handlers × 1 open FD each = N FDs on the runtime file family.
Each rollover by any handler renames the file others still hold → the others now
hold **deleted** inodes and **open a new** FD on the next write cycle is *not*
performed (RotatingFileHandler only reopens on *its own* rollover). Result: the
exact observed pattern — **many FDs on `logs/runtime/2026-08-22.jsonl.7 (deleted)`**.

**C2 — silent data loss:** after handler A rotates, handlers B…N keep `write()`-ing
to the unlinked inode. Those bytes exist only in the deleted file, invisible to
any reader, and are **reclaimed (lost) when PID 423 exits**. Severity: HIGH for
`errors`/`incidents` streams (forensic value destroyed exactly when needed).

**C3 — no real daily rotation:** `date_str` is captured **once** at first handler
creation (line 141). A process that started 2026-08-22 keeps writing to
`2026-08-22.jsonl` on 2026-08-23/24. The `<date>` in the name is **frozen at boot
day**, not the event day. This alone explains why the leaked file is dated
`2026-08-22` while today is `2026-08-24`.

---

## 6. FILE DESCRIPTOR ANALYSIS (Objective D) — [VPS-PENDING for exact numbers]

**STRONG EVIDENCE (predicted):** FDs on `logs/runtime/*.jsonl*` ≈ number of
distinct modules that have logged at INFO+ since boot (bounded by 190), plus
`errors`/`incidents` handlers, plus the `.log` handlers. Multiple FDs will share
few inodes (the deleted rotated backups).

**Still UNKNOWN — must be measured on the VPS (see §16):** exact FD count, exact
inodes, per-inode size, whether the deleted files still grow, total invisible
disk retained, growth rate per day. Do **not** close descriptors manually.

---

## 7. NETWORK CONNECTION ANALYSIS (Objective F) — [VPS-PENDING]

**Repo signals to verify at runtime:**
- `requests` is used for Telegram (`core/advisor_loop.py` `_telegram*`) and likely ccxt/exchange. Whether a shared `requests.Session` is reused vs a fresh connection per call is **UNKNOWN** — drives CLOSE_WAIT accumulation.
- CLOSE_WAIT sockets = remote closed, local never `close()`d → classic un-closed-response leak. **HYPOTHESIS:** per-call `requests.post`/`get` without session pooling, or ccxt clients not closed. **[VPS-PENDING]** measure whether CLOSE_WAIT is **stable or growing** (the decisive question).

---

## 8. DATA PERSISTENCE ANALYSIS (Objective E, J)

**Persistent streams (repo):** `databases/paper_trades.jsonl` (source of truth,
append-only via `paper_trading/recorder.py` — plain `open(a)`+`write`, **no fsync**),
`databases/regret/…`, `logs/<cat>/*.jsonl` (defective, §5), decision packets,
`cache/startup/*.jsonl`.

- **paper_trades.jsonl:** append-only, one line per event. **STRONG EVIDENCE:** no
  `flush`/`fsync` after write ⇒ on power loss / SIGKILL the last buffered lines can
  be lost, and a partial final line is possible. Readers (CRI, data_quality)
  tolerate a trailing partial line by `try/except` per line — **so partial-write
  risk is bounded** but last-record durability is not guaranteed.
- **Structured JSON logs:** subject to C2 (post-rotation loss) and C3 (wrong-day
  files). Not a reliable forensic record today.

**Durability across SIGTERM/crash:** `atexit` (lock release, any flush) runs only
on clean exit; the observed stops were **non-clean** (§4) ⇒ **do not rely on
`atexit` for durability**.

---

## 9. TELEGRAM DELIVERY ANALYSIS (Objective G)

**OBSERVED FACT (earlier this engagement):** `_telegram()` sent to a wrong/dead
token for 8 days while logging `"[RAPPORT] Telegram envoye"` unconditionally →
invisible silence. Already mitigated on branch (visibility + escalation).

**STRONG EVIDENCE (architecture):** there is **no single event-bus→classifier→bot
pipeline** for Telegram. Instead there are **≥4 direct sender functions** in
`advisor_loop` (`_telegram`, `_telegram_behavior`, `_telegram_real`, `_send_intel`),
each hitting the Telegram HTTP API directly with its own token, **bypassing** any
bus. The intended "SCIOS event bus → classifier → Health/Trading/Research bots"
is **NOT IMPLEMENTED** for Telegram (see §15). Consequences: duplicate send paths,
no retry/persistence of failed messages, blocking `requests.post(timeout=10)` on
the trading thread. **This is why one bot can go silent while the process runs:
each channel fails independently and silently.**

---

## 10. EVENT BUS ANALYSIS (Objective H) — [partly VPS-PENDING]

`observability/decision_event_bus.py` exists and starts with "4 workers"
(OBSERVED in boot logs). **UNKNOWN without reading it in depth:** bounded vs
unbounded queue, persistence, backpressure, subscriber isolation. Deferred to a
dedicated pass. Key questions to answer: *if Telegram is down 30 min, do events
queue, drop, or block a worker?* and *can a subscriber exception propagate into
`advisor_loop`?*

---

## 11. RESTART / RECOVERY ANALYSIS (Objective I)

- No installed systemd unit for `core/advisor_loop.py` confirmed (**[VPS-PENDING]**).
- Watchdog in ALERT-ONLY mode ⇒ **no automatic recovery** today; restart is manual (`vps_restart.sh`). **STRONG EVIDENCE** (RECOVERY.md + `watchdog_vps.py`).
- Competing mechanisms: `crypto_advisor.service` (passive bot), watchdog, `vps_restart.sh`, `deploy_vps.sh --restart` (disabled). **HYPOTHESIS:** naming confusion (`crypto-advisor` vs `crypto_advisor`) risks starting the wrong target.

---

## 12. DATA LOSS THREAT MODEL (Objective J)

| Event | Data at risk | Current protection | Failure mode | Severity | Evidence | (Mitigation deferred) |
|---|---|---|---|---|---|---|
| Process crash / SIGKILL | last buffered `paper_trades.jsonl` lines; all deleted-inode log bytes | append-only; OS flush | atexit skipped; deleted inodes reclaimed | **HIGH** | STRONG (§5,§8) | — |
| Log rotation (50 MB) | runtime/errors/incidents records from N-1 handlers | none | write to deleted inode (C2) | **HIGH** | STRONG (§5) | — |
| FD exhaustion | whole process | OS ulimit | ~190+ FDs grow with rotations; `EMFILE` → crash | **HIGH** | STRONG/[VPS] | — |
| Machine reboot | in-flight data; process not auto-restarted | none (watchdog alert-only) | silent stop until manual restart | **HIGH** | STRONG (§11) | — |
| Disk full (invisible retention) | all writes | none | deleted-but-open files hide usage; `df` misleads | **HIGH** | STRONG (§5,§6) | — |
| Telegram outage | notifications | per-channel try/except | messages dropped, not persisted | MED | STRONG (§9) | — |
| Duplicate process | dataset double-write | flock | blocked normally | LOW | STRONG (§4) | — |
| Stale lock / PID recycle | restart availability | dead-PID cleanup | live recycled PID blocks restart (C5) | MED | HYPOTHESIS (§4) | — |
| Partial JSONL write | last record | per-line try/except in readers | trailing partial line tolerated | LOW | STRONG (§8) | — |
| Exception inside logging | log record + caller | stdlib swallows in handler | lost log line | LOW | STRONG | — |
| Handler duplication | FDs, disk, records | none | C1/C2/C3 | **HIGH** | STRONG (§5) | — |

---

## 13. ROOT CAUSE HYPOTHESES (ranked)

1. **RC-1 (STRONG EVIDENCE):** `StructuredLogger` creates a per-module
   `RotatingFileHandler` on a shared category file. This is the single root cause
   of the FD leak, invisible disk retention, and post-rotation data loss (C1/C2).
2. **RC-2 (STRONG EVIDENCE):** date-in-filename captured once ⇒ no daily rotation
   (C3); explains the `2026-08-22` filename on 2026-08-24.
3. **RC-3 (HYPOTHESIS):** CLOSE_WAIT growth from un-pooled/un-closed HTTP responses
   (needs §7 measurement).
4. **RC-4 (HYPOTHESIS):** restart fragility via PID-recycling on the singleton lock.

---

## 14. EVIDENCE TABLE (key)

| Claim | File:line | Grade |
|---|---|---|
| Per-module RotatingFileHandler on shared file | `observability/json_logger.py:131–160` | STRONG |
| backupCount=7 ⇒ `.jsonl.7` | `observability/json_logger.py:144` | STRONG |
| INFO/DEBUG/WARNING → `runtime` category | `observability/json_logger.py:117–123` | STRONG |
| 190 modules use get_logger | `grep -rl get_logger` | STRONG |
| date frozen at first call | `observability/json_logger.py:141` | STRONG |
| flock singleton + stale handling | `core/advisor_loop.py:2896–2987` | STRONG |
| BOOT "verrou non nettoyé" ⇒ non-clean stop | prior VPS logs | OBSERVED |
| ≥4 direct Telegram senders, no bus | `core/advisor_loop.py:_telegram*` | STRONG |
| paper_trades.jsonl no fsync | `paper_trading/recorder.py:_append` | STRONG |

---

## 15. UNKNOWN / UNVERIFIED ITEMS

- [VPS] Exact FD count / inodes / retained disk / growth rate (§6).
- [VPS] CLOSE_WAIT stable vs growing; which library leaks (§7).
- [VPS] Contents of `/tmp/scios_forensics_*` snapshot (never inspected — not on auditor host).
- [VPS] Which process owns :8080; whether a second Python process exists.
- [VPS] systemd unit states; watchdog liveness + in-memory code version.
- [CODE] `decision_event_bus.py` queue semantics (§10) — deferred deep read.
- ADR vs reality matrix (Objective K) — deferred; intended event-bus→classifier→bots pipeline is **NOT IMPLEMENTED** for Telegram (§9), other ADRs unverified.

---

## 16. READ-ONLY VPS EVIDENCE RUNBOOK (run, paste back — changes nothing)

```bash
cd ~/crypto_ai_terminal
PID=423   # adjust if the current engine PID differs (pgrep -f 'core/advisor_loop\.py$')

echo "== A. process topology =="
ps -o pid,ppid,etime,rss,nlwp,cmd -p "$PID"
pgrep -af 'advisor_loop\.py' ; pgrep -af watchdog_vps

echo "== B. snapshot inventory (inspect first, do not trust completeness) =="
ls -la /tmp/scios_forensics_* 2>/dev/null; find /tmp/scios_forensics_* -maxdepth 2 -type f 2>/dev/null | head -50

echo "== C. FD / deleted-inode leak (the critical measurement) =="
ls -l /proc/$PID/fd | wc -l
ls -l /proc/$PID/fd | grep -c '(deleted)'
ls -l /proc/$PID/fd | grep 'logs/runtime' | head
# per-inode grouping of deleted log files + retained bytes:
lsof -p "$PID" 2>/dev/null | awk '/logs\/(runtime|errors|incidents)/ {print $7, $9}' | sort | uniq -c | sort -rn | head
lsof -p "$PID" 2>/dev/null | awk '/deleted/ {s+=$7} END {printf "retained-invisible bytes: %d\n", s}'

echo "== D. sockets =="
ss -tanp 2>/dev/null | grep -c CLOSE-WAIT
ss -tanp 2>/dev/null | awk '{print $1}' | sort | uniq -c

echo "== E. disk reality (df lies while inodes are open) =="
df -h . ; du -sh logs/ 2>/dev/null; ls -laS logs/runtime 2>/dev/null | head

echo "== F. supervision =="
systemctl status paper-arena.service crypto_advisor.service crypto-advisor.service crypto_watchdog.service --no-pager 2>&1 | head -40

echo "== G. lock =="
cat logs/advisor.lock 2>/dev/null; ls -l logs/advisor.lock 2>/dev/null
```

**Take a second FD/socket sample ~30 min later** so we can classify each leak as
*stable* vs *growing* — that single delta decides urgency.
