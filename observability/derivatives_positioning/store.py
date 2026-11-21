"""Durable local store of derivatives positioning observations (SQLite, WAL).

One file, ``positioning.sqlite3``, inside a directory that must already exist (on
the VPS it is created by systemd ``StateDirectory``; the store never creates its
volume). Writes are one ``BEGIN IMMEDIATE`` transaction each (or per batch) with
``synchronous=FULL``: an interruption leaves either the whole write or nothing.

Outcome of a write, per observation:

* ``INSERTED``  new identity;
* ``DUPLICATE`` same identity, same content (replay, retry, later receipt): nothing written;
* ``CONFLICT``  same identity, different content: the original is kept, the conflicting
  content is journaled once per distinct content (a retry only bumps a counter);
* ``REJECTED``  input contract violated (``code``);
* ``NOT_WRITTEN`` the storage refused the write (``code``): stored history is untouched.

No network, no service, no API route, no purge. Data never leaves the directory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import json
from pathlib import Path
import shutil
import sqlite3
import time
import uuid

from observability.market_stress import metrics

from .contract import ContractError, iso_ms, normalize
from .migrations import LATEST_VERSION, MIGRATIONS, sql_sha256
from .policy import PositioningPolicy

DB_NAME = "positioning.sqlite3"
WINDOWS_S = metrics.WINDOWS_S  # 1 h, 4 h, 24 h: same pre-registered windows as MarketDerivativesStress
MAX_SCAN_ROWS = 500_000


class StorageError(Exception):
    """The storage cannot serve the request. ``code`` is stable and observable."""

    def __init__(self, code, detail=""):
        super().__init__(code if not detail else "%s: %s" % (code, detail))
        self.code = code
        self.detail = detail


def _storage_code(exc):
    """Map an sqlite3 / OS error to a stable storage code."""
    code = getattr(exc, "sqlite_errorcode", None)
    primary = None if code is None else code & 0xFF
    text = str(exc).lower()
    if primary == 13 or "disk is full" in text or isinstance(exc, OSError) and exc.errno == 28:
        return "STORAGE_FULL"
    if primary == 8 or "readonly" in text or "read-only" in text:
        return "STORAGE_READ_ONLY"
    if primary == 5 or primary == 6 or "locked" in text:
        return "STORAGE_BUSY"
    if primary in (11, 26) or isinstance(exc, sqlite3.DatabaseError) and "malformed" in text:
        return "STORAGE_CORRUPT"
    return "STORAGE_UNAVAILABLE"


@dataclass(frozen=True)
class IngestResult:
    status: str
    code: str | None = None
    observation_key: str | None = None
    seq: int | None = None
    out_of_order: bool | None = None

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class BatchResult:
    ok: bool
    code: str | None = None
    results: list = field(default_factory=list)

    def as_dict(self):
        return {"ok": self.ok, "code": self.code, "results": [r.as_dict() for r in self.results]}


def _now_ms():
    return int(time.time() * 1000)


class PositioningStore:
    def __init__(self, data_dir, *, policy=None, read_only=False, now_ms=_now_ms):
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / DB_NAME
        self.policy = policy or PositioningPolicy()
        self.read_only = read_only
        self.now_ms = now_ms
        self._conn = None
        self._open()

    # ------------------------------------------------------------------ lifecycle
    def _open(self):
        if not self.data_dir.exists():
            raise StorageError("STORAGE_DIRECTORY_MISSING", str(self.data_dir))
        if self.data_dir.is_symlink() or not self.data_dir.is_dir():
            raise StorageError("STORAGE_NOT_A_DIRECTORY", str(self.data_dir))
        if self.db_path.is_symlink():
            raise StorageError("STORAGE_INVALID_PATH", str(self.db_path))
        try:
            if self.read_only:
                if not self.db_path.exists():
                    raise StorageError("STORAGE_EMPTY_NOT_INITIALISED", str(self.db_path))
                uri = "file:%s?mode=ro" % self.db_path.resolve()
                self._conn = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)
            else:
                self._conn = sqlite3.connect(str(self.db_path), isolation_level=None, timeout=5)
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._migrate()
        except StorageError:
            self.close()
            raise
        except (sqlite3.Error, OSError) as exc:
            self.close()
            raise StorageError(_storage_code(exc), str(exc)) from exc

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _migrate(self):
        c = self._conn
        exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
        applied = {}
        if exists:
            applied = {v: (name, sha) for v, name, sha in
                       c.execute("SELECT version, name, sql_sha256 FROM schema_migrations")}
        if applied and max(applied) > LATEST_VERSION:
            raise StorageError("STORAGE_SCHEMA_NEWER", "database version %d > code %d" % (max(applied), LATEST_VERSION))
        for version, name, sql in MIGRATIONS:
            if version in applied:
                if applied[version] != (name, sql_sha256(sql)):
                    raise StorageError("STORAGE_MIGRATION_TAMPERED", "migration %d" % version)
                continue
            if self.read_only:
                raise StorageError("STORAGE_SCHEMA_OUTDATED_READ_ONLY", "migration %d missing" % version)
            # One transaction per migration; values are integers/hex digests only.
            script = ("BEGIN IMMEDIATE;\n"
                      "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL,"
                      " sql_sha256 TEXT NOT NULL, applied_at_ms INTEGER NOT NULL);\n"
                      + sql +
                      "\nINSERT INTO schema_migrations VALUES (%d, '%s', '%s', %d);\n" % (
                          version, name, sql_sha256(sql), self.now_ms()))
            if version == 1:
                script += "INSERT INTO store_identity VALUES (1, '%s', %d);\n" % (uuid.uuid4().hex, self.now_ms())
            try:
                c.executescript(script + "COMMIT;")
            except sqlite3.Error:
                if c.in_transaction:
                    c.execute("ROLLBACK")
                raise

    # ------------------------------------------------------------------ writes
    def ingest(self, raw) -> IngestResult:
        batch = self.ingest_batch([raw])
        return batch.results[0]

    def ingest_batch(self, raws) -> BatchResult:
        """All valid observations of the batch are written atomically, or none of them."""
        raws = list(raws)
        prepared = []
        for raw in raws:
            try:
                prepared.append(normalize(raw))
            except ContractError as exc:
                prepared.append(exc)
        if self.read_only:
            return self._not_written(prepared, "STORAGE_READ_ONLY")
        if not self.data_dir.is_dir():
            return self._not_written(prepared, "STORAGE_DIRECTORY_MISSING")
        c = self._conn
        results = []
        try:
            c.execute("BEGIN IMMEDIATE")
            for item in prepared:
                if isinstance(item, ContractError):
                    results.append(IngestResult("REJECTED", item.code))
                else:
                    results.append(self._write_one(item))
            c.execute("COMMIT")
        except (sqlite3.Error, OSError) as exc:
            if c.in_transaction:
                try:
                    c.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            return self._not_written(prepared, _storage_code(exc))
        return BatchResult(True, None, results)

    @staticmethod
    def _not_written(prepared, code):
        results = [IngestResult("REJECTED", p.code) if isinstance(p, ContractError)
                   else IngestResult("NOT_WRITTEN", code, p.observation_key) for p in prepared]
        return BatchResult(False, code, results)

    def _write_one(self, obs):
        c = self._conn
        now = self.now_ms()
        row = c.execute("SELECT seq, content_sha256 FROM observations WHERE observation_key = ?",
                        (obs.observation_key,)).fetchone()
        doc_json = json.dumps(obs.document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if row is None:
            effective = obs.source_time_ms if obs.source_time_ms is not None else obs.received_at_ms
            basis = "SOURCE" if obs.source_time_ms is not None else "RECEIPT"
            newer = c.execute(
                "SELECT 1 FROM observations WHERE venue=? AND native_symbol=? AND contract_type=?"
                " AND effective_time_ms > ? LIMIT 1",
                (obs.venue, obs.native_symbol, obs.contract_type, effective)).fetchone()
            cur = c.execute(
                "INSERT INTO observations (observation_key, content_sha256, venue, native_symbol, contract_type,"
                " quote_currency, source_time_ms, received_at_ms, effective_time_ms, time_basis, out_of_order,"
                " stored_at_ms, document) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (obs.observation_key, obs.content_sha256, obs.venue, obs.native_symbol, obs.contract_type,
                 obs.quote_currency, obs.source_time_ms, obs.received_at_ms, effective, basis,
                 1 if newer else 0, now, doc_json))
            return IngestResult("INSERTED", None, obs.observation_key, cur.lastrowid, bool(newer))
        seq, stored_content = row
        if stored_content == obs.content_sha256:
            return IngestResult("DUPLICATE", None, obs.observation_key, seq)
        c.execute(
            "INSERT INTO conflicts (observation_key, content_sha256, first_seen_ms, last_seen_ms, attempts, document)"
            " VALUES (?,?,?,?,1,?) ON CONFLICT (observation_key, content_sha256)"
            " DO UPDATE SET last_seen_ms = excluded.last_seen_ms, attempts = attempts + 1",
            (obs.observation_key, obs.content_sha256, now, now, doc_json))
        return IngestResult("CONFLICT", "CONTENT_DIFFERS_ORIGINAL_KEPT", obs.observation_key, seq)

    # ------------------------------------------------------------------ reads
    def _query(self, sql, args=()):
        try:
            return self._conn.execute(sql, args).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(_storage_code(exc), str(exc)) from exc

    def _view(self, row, as_of_ms=None):
        (seq, key, content, source_ms, received_ms, effective_ms, basis, out_of_order, stored_ms, doc_json) = row
        doc = json.loads(doc_json)
        measures = doc["measures"]
        latency = None if source_ms is None else received_ms - source_ms
        if latency is None:
            lateness = "UNDETERMINED"
        else:
            lateness = "LATE" if latency > self.policy.late_after_ms else "ON_TIME"
        unavailable = [{"field": name, "reason": m["reason"]}
                       for name, m in measures.items() if m["status"] != "AVAILABLE"]
        oi, fund = measures["open_interest"], measures["funding_rate"]
        view = {
            "seq": seq, "observation_key": key, "content_sha256": content,
            "venue": doc["venue"], "native_symbol": doc["native_symbol"], "contract_type": doc["contract_type"],
            "quote_currency": doc["quote_currency"], "base_currency": doc["base_currency"],
            "capture_id": doc["capture_id"],
            "source_time_utc": iso_ms(source_ms), "received_at_utc": iso_ms(received_ms),
            "effective_time_utc": iso_ms(effective_ms), "time_basis": basis,
            "receipt_latency_ms": latency, "lateness": lateness, "out_of_order_at_ingest": bool(out_of_order),
            "stored_at_utc": iso_ms(stored_ms),
            "provenance": {**doc["provenance"], "collector_run_id": doc.get("collector_run_id")},
            "measures": _public_measures(measures),
            "unavailable_fields": unavailable,
            "units": {
                "prices": doc["quote_currency"],
                "open_interest": oi.get("unit"),
                "contract_size_base": oi.get("contract_size_base"),
                "funding_interval_s": fund.get("interval_s"),
                "funding_rate": "FRACTION_PER_INTERVAL" if fund["status"] == "AVAILABLE" else None,
            },
            "derived": _derived(doc, measures, effective_ms),
        }
        if as_of_ms is not None:
            view["freshness"] = self._freshness(effective_ms, as_of_ms)
        return view

    def _freshness(self, effective_ms, as_of_ms):
        age = as_of_ms - effective_ms
        if age < 0:
            status = "FUTURE_OR_INCONSISTENT_CLOCK"
        else:
            status = "FRESH" if age <= self.policy.max_age_ms else "STALE"
        return {"as_of_utc": iso_ms(as_of_ms), "age_ms": age, "status": status,
                "max_age_ms": self.policy.max_age_ms}

    _COLUMNS = ("seq, observation_key, content_sha256, source_time_ms, received_at_ms, effective_time_ms,"
                " time_basis, out_of_order, stored_at_ms, document")

    def latest(self, venue, native_symbol, contract_type, *, as_of_ms=None):
        as_of = self.now_ms() if as_of_ms is None else as_of_ms
        rows = self._query(
            "SELECT " + self._COLUMNS + " FROM observations WHERE venue=? AND native_symbol=? AND contract_type=?"
            " AND effective_time_ms <= ? ORDER BY effective_time_ms DESC, seq DESC LIMIT 1",
            (venue, native_symbol, contract_type, as_of))
        if not rows:
            return {"status": "NOT_AVAILABLE", "reason": "NO_OBSERVATION", "as_of_utc": iso_ms(as_of),
                    "observation": None}
        return {"status": "AVAILABLE", "reason": None, "as_of_utc": iso_ms(as_of),
                "observation": self._view(rows[0], as_of)}

    def history(self, venue, native_symbol, contract_type, start_ms, end_ms, *, limit=None, cadence_s=None):
        if start_ms > end_ms:
            raise ValueError("HISTORY_INVALID_PERIOD")
        bound = self.policy.history_max_rows if limit is None else min(int(limit), self.policy.history_max_rows)
        if bound < 1:
            raise ValueError("HISTORY_INVALID_LIMIT")
        rows = self._query(
            "SELECT " + self._COLUMNS + " FROM observations WHERE venue=? AND native_symbol=? AND contract_type=?"
            " AND effective_time_ms BETWEEN ? AND ? ORDER BY effective_time_ms, seq LIMIT ?",
            (venue, native_symbol, contract_type, start_ms, end_ms, bound + 1))
        truncated = len(rows) > bound
        rows = rows[:bound]
        items = [self._view(r) for r in rows]
        field_counts = {}
        for it in items:
            for u in it["unavailable_fields"]:
                field_counts[u["field"]] = field_counts.get(u["field"], 0) + 1
        coverage = {"observations": len(items), "truncated": truncated,
                    "first_utc": items[0]["effective_time_utc"] if items else None,
                    "last_utc": items[-1]["effective_time_utc"] if items else None,
                    "unavailable_by_field": field_counts,
                    "late": sum(1 for it in items if it["lateness"] == "LATE"),
                    "lateness_undetermined": sum(1 for it in items if it["lateness"] == "UNDETERMINED")}
        if cadence_s is None:
            coverage.update(expected=None, ratio=None, reason="CADENCE_UNKNOWN")
        else:
            expected = _expected_points(end_ms - start_ms, cadence_s)
            distinct = len({it["effective_time_utc"] for it in items})
            coverage.update(expected=expected, ratio=metrics.fixed(min(Decimal(1), Decimal(distinct) / expected), 6),
                            reason=None)
        return {"venue": venue, "native_symbol": native_symbol, "contract_type": contract_type,
                "start_utc": iso_ms(start_ms), "end_utc": iso_ms(end_ms), "limit": bound,
                "coverage": coverage, "observations": items}

    def oi_change(self, venue, native_symbol, contract_type, *, as_of_ms, cadence_s, windows_s=WINDOWS_S):
        """OI change over each window, only between comparable points with sufficient coverage.

        Both ends use the same rule: the observation nearest to the target instant within
        ``max(min_tolerance, cadence)``, with an available OI. They must share unit,
        contract size, contract type and time basis. Without a cadence, nothing is computed.
        """
        out = {"venue": venue, "native_symbol": native_symbol, "contract_type": contract_type,
               "as_of_utc": iso_ms(as_of_ms), "cadence_s": cadence_s,
               "policy": {"min_coverage": self.policy.min_coverage,
                          "min_tolerance_ms": self.policy.min_tolerance_ms},
               "windows": []}
        if isinstance(cadence_s, bool) or not isinstance(cadence_s, int) or cadence_s <= 0:
            out["tolerance_ms"] = None
            out["windows"] = [_oi_refused(w, "CADENCE_UNKNOWN") for w in windows_s]
            return out
        tol = self.policy.tolerance_ms(cadence_s)
        out["tolerance_ms"] = tol
        lo = as_of_ms - max(windows_s) * 1000 - tol
        rows = self._query(
            "SELECT effective_time_ms, time_basis, document FROM observations WHERE venue=? AND native_symbol=?"
            " AND contract_type=? AND effective_time_ms BETWEEN ? AND ? ORDER BY effective_time_ms, seq LIMIT ?",
            (venue, native_symbol, contract_type, lo, as_of_ms + tol, MAX_SCAN_ROWS + 1))
        if len(rows) > MAX_SCAN_ROWS:
            out["windows"] = [_oi_refused(w, "SCAN_BUDGET_EXCEEDED") for w in windows_s]
            return out
        points = []
        for t, basis, doc_json in rows:
            oi = json.loads(doc_json)["measures"]["open_interest"]
            if oi["status"] == "AVAILABLE":
                points.append({"t": t, "basis": basis, "value": oi["value"], "unit": oi["unit"],
                               "size": oi["contract_size_base"]})
        now_point = _nearest(points, as_of_ms, tol)
        for w in windows_s:
            out["windows"].append(self._one_window(points, now_point, as_of_ms, w, cadence_s, tol))
        return out

    def _one_window(self, points, now_point, as_of_ms, w, cadence_s, tol):
        if now_point is None:
            return _oi_refused(w, "NO_COMPARABLE_POINT_AT_END")
        ref = _nearest(points, as_of_ms - w * 1000, tol)
        if ref is None:
            return _oi_refused(w, "NO_COMPARABLE_POINT_AT_START")
        why = _incompatible(ref, now_point)
        if why:
            return _oi_refused(w, why)
        inside = {p["t"] for p in points
                  if as_of_ms - w * 1000 <= p["t"] <= as_of_ms and not _incompatible(p, now_point)}
        expected = _expected_points(w * 1000, cadence_s)
        ratio = min(Decimal(1), Decimal(len(inside)) / expected)
        base = {"window_s": w, "unit": now_point["unit"], "contract_size_base": now_point["size"],
                "time_basis": now_point["basis"],
                "start": {"at_utc": iso_ms(ref["t"]), "value": ref["value"], "gap_ms": abs(ref["t"] - (as_of_ms - w * 1000))},
                "end": {"at_utc": iso_ms(now_point["t"]), "value": now_point["value"], "gap_ms": abs(now_point["t"] - as_of_ms)},
                "coverage": {"points": len(inside), "expected": expected, "ratio": metrics.fixed(ratio, 6)},
                "change_pct": None}
        if ratio < self.policy.coverage:
            return {**base, "status": "NOT_AVAILABLE", "reason": "INSUFFICIENT_COVERAGE"}
        o0, o1 = Decimal(ref["value"]), Decimal(now_point["value"])
        if o0 <= 0:
            return {**base, "status": "NOT_AVAILABLE", "reason": "REFERENCE_OPEN_INTEREST_ZERO"}
        with localcontext() as ctx:
            ctx.prec = metrics.PRECISION
            change = (o1 - o0) / o0 * 100
        return {**base, "status": "AVAILABLE", "reason": None, "change_pct": metrics.fixed(change, 6)}

    def compare(self, legs, *, as_of_ms):
        """Latest observation of each leg, native values kept; says which comparisons are unavailable."""
        latest = []
        for venue, symbol, ctype in legs:
            latest.append(((venue, symbol, ctype), self.latest(venue, symbol, ctype, as_of_ms=as_of_ms)))
        pairs = []
        for i in range(len(latest)):
            for j in range(i + 1, len(latest)):
                (ka, la), (kb, lb) = latest[i], latest[j]
                pairs.append({"a": ":".join(ka), "b": ":".join(kb), **_compare_pair(la, lb)})
        return {"as_of_utc": iso_ms(as_of_ms),
                "legs": [{"leg": ":".join(k), **v} for k, v in latest], "pairs": pairs}

    # ------------------------------------------------------------------ operations
    def status(self):
        store_id, created = self._query("SELECT store_id, created_at_ms FROM store_identity")[0]
        versions = [v for (v,) in self._query("SELECT version FROM schema_migrations ORDER BY version")]
        (count, oldest, newest), = self._query(
            "SELECT COUNT(*), MIN(effective_time_ms), MAX(effective_time_ms) FROM observations")
        (conflicts, attempts), = self._query("SELECT COUNT(*), COALESCE(SUM(attempts), 0) FROM conflicts")
        legs = self._query("SELECT venue, native_symbol, contract_type, COUNT(*) FROM observations"
                           " GROUP BY venue, native_symbol, contract_type ORDER BY 1, 2, 3")
        sizes = {}
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(self.db_path) + suffix)
            sizes[DB_NAME + suffix] = p.stat().st_size if p.exists() else 0
        used = sum(sizes.values())
        disk = shutil.disk_usage(self.data_dir)
        return {
            "store_id": store_id, "created_at_utc": iso_ms(created), "data_dir": str(self.data_dir),
            "database": str(self.db_path), "read_only": self.read_only,
            "schema_versions": versions, "schema_latest_known": LATEST_VERSION,
            "observations": count, "oldest_utc": iso_ms(oldest), "newest_utc": iso_ms(newest),
            "conflicts": {"distinct": conflicts, "attempts": attempts},
            "legs": [{"venue": v, "native_symbol": s, "contract_type": t, "observations": n} for v, s, t, n in legs],
            "files_bytes": sizes, "store_bytes": used,
            "volume": {"total_bytes": disk.total, "free_bytes": disk.free},
            "budget": {"disk_budget_bytes": self.policy.disk_budget_bytes, "retention_days": self.policy.retention_days,
                       "status": "HYPOTHESIS_NOT_ENFORCED", "purge_enabled": False,
                       "used_ratio": metrics.fixed(Decimal(used) / Decimal(max(1, self.policy.disk_budget_bytes)), 6)},
        }

    def checkpoint(self):
        """Fold the WAL into the main file (used by measurements and before a cold copy)."""
        if self.read_only:
            raise StorageError("STORAGE_READ_ONLY")
        try:
            return self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        except sqlite3.Error as exc:
            raise StorageError(_storage_code(exc), str(exc)) from exc


# ---------------------------------------------------------------------- helpers
def _public_measures(measures):
    out = {}
    for name, m in measures.items():
        m = dict(m)
        if "next_funding_ms" in m:
            m["next_funding_utc"] = iso_ms(m.pop("next_funding_ms"))
        out[name] = m
    return out


def _derived(doc, measures, effective_ms):
    """Descriptive conversions from one observation, reusing market_stress.metrics. No score."""
    mark, index, spot = measures["mark_price"], measures["index_price"], measures["spot_reference"]
    mark_v = mark.get("value")
    if mark["status"] == "AVAILABLE" and index["status"] == "AVAILABLE":
        premium = metrics.premium(mark_v, index["value"])
    else:
        premium = metrics.refused("MARK_OR_INDEX_MISSING", bps=None)
    premium["definition"] = "(mark - index) / index, bps, same venue and observation"
    if mark["status"] != "AVAILABLE":
        basis = metrics.refused("MARK_MISSING", bps=None, annualized_pct=None)
    elif spot["status"] != "AVAILABLE":
        basis = metrics.refused("SPOT_REFERENCE_NOT_QUALIFIED_OR_MISSING", bps=None, annualized_pct=None)
    else:
        basis = metrics.basis(mark_v, spot["value"])
        basis["against"] = {"venue": spot["venue"], "native_symbol": spot["native_symbol"]}
    basis["definition"] = "(mark - qualified spot reference) / spot, bps"
    fund = measures["funding_rate"]
    if fund["status"] == "AVAILABLE":
        nxt = fund.get("next_funding_ms")
        nxt_dt = None if nxt is None else datetime.fromtimestamp(nxt / 1000, timezone.utc)
        eff = datetime.fromtimestamp(effective_ms / 1000, timezone.utc)
        funding = metrics.funding(fund["value"], fund["interval_s"], nxt_dt, eff)
        funding["next_funding_utc"] = iso_ms(nxt)
    else:
        funding = metrics.refused("FUNDING_RATE_MISSING", rate=None, interval_s=None, next_funding_utc=None,
                                  rate_8h_equivalent=None, annualized_simple_pct=None)
    funding["conversion"] = "SIMPLE_LINEAR (display only)"
    oi = measures["open_interest"]
    if oi["status"] == "AVAILABLE":
        notional = metrics.open_interest(oi["value"], oi["unit"], mark_v, oi["contract_size_base"])
    else:
        notional = metrics.refused("OPEN_INTEREST_MISSING", value=None, unit=None, notional_quote=None)
    return {"premium_to_index": premium, "basis_vs_spot": basis, "funding": funding,
            "open_interest_notional": notional}


def _expected_points(span_ms, cadence_s):
    return span_ms // (cadence_s * 1000) + 1


def _nearest(points, target_ms, tol_ms):
    best = None
    for p in points:
        gap = abs(p["t"] - target_ms)
        if gap <= tol_ms and (best is None or gap < abs(best["t"] - target_ms)):
            best = p
    return best


def _incompatible(a, b):
    if a["unit"] != b["unit"]:
        return "OPEN_INTEREST_UNITS_DIFFER"
    if a["size"] != b["size"]:
        return "CONTRACT_SIZES_DIFFER"
    if a["basis"] != b["basis"]:
        return "TIME_BASES_DIFFER"
    return None


def _oi_refused(window_s, reason):
    return {"window_s": window_s, "status": "NOT_AVAILABLE", "reason": reason, "unit": None,
            "contract_size_base": None, "time_basis": None, "start": None, "end": None,
            "coverage": None, "change_pct": None}


def _compare_pair(la, lb):
    if la["status"] != "AVAILABLE" or lb["status"] != "AVAILABLE":
        return {"open_interest": {"status": "NOT_AVAILABLE", "reason": "LEG_WITHOUT_OBSERVATION"},
                "funding": {"status": "NOT_AVAILABLE", "reason": "LEG_WITHOUT_OBSERVATION"}}
    a, b = la["observation"], lb["observation"]
    oa, ob = a["measures"]["open_interest"], b["measures"]["open_interest"]
    if oa["status"] != "AVAILABLE" or ob["status"] != "AVAILABLE":
        oi = {"status": "NOT_AVAILABLE", "reason": "OPEN_INTEREST_MISSING"}
    elif oa["unit"] != ob["unit"]:
        oi = {"status": "NOT_AVAILABLE", "reason": "OPEN_INTEREST_UNITS_DIFFER",
              "units": [oa["unit"], ob["unit"]]}
    elif oa["contract_size_base"] != ob["contract_size_base"]:
        oi = {"status": "NOT_AVAILABLE", "reason": "CONTRACT_SIZES_DIFFER",
              "contract_sizes_base": [oa["contract_size_base"], ob["contract_size_base"]]}
    elif oa["unit"] == "QUOTE" and a["quote_currency"] != b["quote_currency"]:
        oi = {"status": "NOT_AVAILABLE", "reason": "QUOTE_CURRENCIES_DIFFER"}
    else:
        oi = {"status": "AVAILABLE", "reason": None, "unit": oa["unit"], "values": [oa["value"], ob["value"]]}
    fa, fb = a["measures"]["funding_rate"], b["measures"]["funding_rate"]
    if fa["status"] != "AVAILABLE" or fb["status"] != "AVAILABLE":
        fund = {"status": "NOT_AVAILABLE", "reason": "FUNDING_RATE_MISSING"}
    elif fa["interval_s"] != fb["interval_s"]:
        fund = {"status": "NOT_AVAILABLE", "reason": "FUNDING_INTERVALS_DIFFER",
                "intervals_s": [fa["interval_s"], fb["interval_s"]],
                "note": "native rates are per different intervals; see each leg's derived 8 h equivalent (linear)"}
    else:
        fund = {"status": "AVAILABLE", "reason": None, "interval_s": fa["interval_s"],
                "rates": [fa["value"], fb["value"]]}
    return {"open_interest": oi, "funding": fund}
