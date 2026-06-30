"""
tools/dataset_certifier.py — Data Governance Specification v1.0 Certifier.

Applique strictement les 24 critères DG-001→DG-024 définis dans
docs/data_governance_spec_v1.md. Ne jamais interpréter — uniquement appliquer.

Usage CLI :
    python tools/dataset_certifier.py databases/rejections/
    python tools/dataset_certifier.py databases/rejections/ --manifest EXP-001.yaml
    python tools/dataset_certifier.py databases/rejections/ --quiet

Usage Python :
    from tools.dataset_certifier import DatasetCertifier
    report = DatasetCertifier().certify(Path("databases/rejections/"))
    print(report.level)      # CERTIFIED | PASS | WARNING | FAIL
    print(report.is_certifiable)  # True si CERTIFIED ou PASS
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Structures ────────────────────────────────────────────────────────────────


@dataclass
class DGViolation:
    """Violation d'un critère DG-xxx."""

    criterion_id: str
    severity: str  # ERROR | WARNING
    record_index: Optional[int]
    observation_id: Optional[str]
    message: str

    def __str__(self) -> str:
        loc = (
            f"[record {self.record_index}]"
            if self.record_index is not None
            else "[dataset]"
        )
        return f"{self.criterion_id} {self.severity} {loc}: {self.message}"


@dataclass
class CertificationReport:
    """Résultat complet de certification d'un dataset."""

    dataset_path: str
    total_records: int
    parsed_records: int
    error_count: int
    warning_count: int
    violations: List[DGViolation] = field(default_factory=list)
    level: str = "FAIL"  # CERTIFIED | PASS | WARNING | FAIL
    certification_id: Optional[str] = None
    generated_at: str = ""

    @property
    def is_certifiable(self) -> bool:
        """True si le dataset peut alimenter une analyse scientifique (§3)."""
        return self.level in ("CERTIFIED", "PASS")

    def summary(self, max_violations: int = 20) -> str:
        lines = [
            "━━ Dataset Certification Report ━━",
            f"Path     : {self.dataset_path}",
            f"Records  : {self.parsed_records}/{self.total_records} parsés",
            f"Errors   : {self.error_count}",
            f"Warnings : {self.warning_count}",
            f"Level    : {self.level}",
        ]
        if self.certification_id:
            lines.append(f"CertID   : {self.certification_id}")
        lines.append(f"Generated: {self.generated_at}")
        if self.violations:
            lines.append("\nViolations :")
            for v in self.violations[:max_violations]:
                lines.append(f"  {v}")
            if len(self.violations) > max_violations:
                lines.append(
                    f"  ... {len(self.violations) - max_violations} autres violations"
                )
        return "\n".join(lines)


# ── Constantes de validation ──────────────────────────────────────────────────

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
_HASH_RE = re.compile(r"^[0-9A-F]{12}$")

_VALID_SIDES = {"BUY", "SELL", "LONG", "SHORT", "HOLD"}
_VALID_REGIMES = {"bull_trend", "bear_trend", "sideways", "volatile", "unknown"}

# Champs ERROR-obligatoires (§2.1 data_governance_spec_v1, RejectionRecord v1).
# trade_allowed/gate_allowed/state_history absents de RejectionRecord v1.
_REQUIRED_NON_NULL = frozenset(
    {
        "observation_id",
        "packet_id",
        "ts",
        "ts_iso",
        "symbol",
        "side",
        "score",
        "price",
        "regime",
        "cycle",
        "engine_version",
        "all_blockers",
        "human_verdict",
        "features",
    }
)


# ── DatasetCertifier ──────────────────────────────────────────────────────────


class DatasetCertifier:
    """
    Certifie un dataset JSONL selon la Data Governance Specification v1.0.

    Applique les 24 critères DG-001→DG-024. Ne jamais interpréter — appliquer.
    Niveaux : CERTIFIED (0 ERR + 0 WARN) > PASS (0 ERR + ≤5 WARN)
              > WARNING (0 ERR + >5 WARN) > FAIL (≥1 ERR).
    """

    def __init__(self, cert_sequence: int = 1) -> None:
        self._cert_seq = cert_sequence

    def certify(
        self,
        dataset_dir: Path,
        manifest: Optional[Dict[str, Any]] = None,
    ) -> CertificationReport:
        """
        Certifie tous les *.jsonl dans dataset_dir.

        Args:
            dataset_dir : répertoire contenant les fichiers JSONL.
            manifest    : dict issu de dataset_manifest d'un EXP-xxx.yaml (optionnel).

        Returns:
            CertificationReport avec violations détaillées et niveau certifié.
        """
        dataset_dir = Path(dataset_dir)
        violations: List[DGViolation] = []
        records: List[Dict[str, Any]] = []
        total_lines = 0

        # Lecture + DG-011 (JSON valide) ───────────────────────────────────────
        for jfile in sorted(dataset_dir.glob("*.jsonl")):
            try:
                with open(jfile, "r", encoding="utf-8") as f:
                    for line_no, raw in enumerate(f):
                        raw = raw.strip()
                        if not raw:
                            continue
                        total_lines += 1
                        try:
                            rec = json.loads(raw)
                            records.append(rec)
                        except json.JSONDecodeError as exc:
                            violations.append(
                                DGViolation(
                                    "DG-011",
                                    "ERROR",
                                    total_lines - 1,
                                    None,
                                    f"JSON invalide {jfile.name}:{line_no + 1}: {exc}",
                                )
                            )
            except OSError as exc:
                violations.append(
                    DGViolation(
                        "DG-011",
                        "ERROR",
                        None,
                        None,
                        f"Lecture impossible ({jfile.name}): {exc}",
                    )
                )

        # Vérifications dataset-level ──────────────────────────────────────────
        violations += self._check_dg001_unique_ids(records)
        violations += self._check_dg010_monotone_timestamps(records)
        if manifest is not None:
            violations += self._check_manifest(manifest)

        # Vérifications par enregistrement ─────────────────────────────────────
        for idx, rec in enumerate(records):
            obs_id = rec.get("observation_id")
            violations += self._check_record(idx, obs_id, rec)

        # Calcul du niveau ─────────────────────────────────────────────────────
        n_errors = sum(1 for v in violations if v.severity == "ERROR")
        n_warnings = sum(1 for v in violations if v.severity == "WARNING")

        if n_errors > 0:
            level, cert_id = "FAIL", None
        elif n_warnings == 0:
            level, cert_id = "CERTIFIED", self._gen_cert_id()
        elif n_warnings <= 5:
            level, cert_id = "PASS", self._gen_cert_id()
        else:
            level, cert_id = "WARNING", None

        return CertificationReport(
            dataset_path=str(dataset_dir),
            total_records=total_lines,
            parsed_records=len(records),
            error_count=n_errors,
            warning_count=n_warnings,
            violations=violations,
            level=level,
            certification_id=cert_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Vérifications dataset-level ───────────────────────────────────────────

    def _check_dg001_unique_ids(self, records: List[Dict]) -> List[DGViolation]:
        """DG-001 — observation_id unique dans le dataset (ERROR)."""
        seen: Dict[str, int] = {}
        out = []
        for idx, rec in enumerate(records):
            oid = rec.get("observation_id")
            if oid is None:
                continue
            if oid in seen:
                out.append(
                    DGViolation(
                        "DG-001",
                        "ERROR",
                        idx,
                        str(oid),
                        f"observation_id dupliqué — déjà vu à l'index {seen[oid]}",
                    )
                )
            else:
                seen[str(oid)] = idx
        return out

    def _check_dg010_monotone_timestamps(
        self, records: List[Dict]
    ) -> List[DGViolation]:
        """DG-010 — Timestamps monotones croissants (WARNING)."""
        out = []
        prev_ts: Optional[float] = None
        prev_idx: Optional[int] = None
        for idx, rec in enumerate(records):
            ts = rec.get("ts")
            if not isinstance(ts, (int, float)):
                continue
            ts_f = float(ts)
            if prev_ts is not None and ts_f < prev_ts:
                out.append(
                    DGViolation(
                        "DG-010",
                        "WARNING",
                        idx,
                        rec.get("observation_id"),
                        f"ts={ts_f} < ts précédent={prev_ts} (index {prev_idx})",
                    )
                )
            prev_ts = ts_f
            prev_idx = idx
        return out

    def _check_manifest(self, manifest: Dict) -> List[DGViolation]:
        """DG-002, DG-005, DG-006, DG-023 — critères niveau Dataset Manifest."""
        out = []

        # DG-002 — dataset_uuid conforme RFC-4122 (ERROR)
        uuid_val = str(manifest.get("uuid", ""))
        if not uuid_val:
            out.append(
                DGViolation("DG-002", "ERROR", None, None, "uuid absent du manifest")
            )
        elif not _UUID_RE.match(uuid_val):
            out.append(
                DGViolation(
                    "DG-002",
                    "ERROR",
                    None,
                    None,
                    f"uuid non conforme RFC-4122: {uuid_val}",
                )
            )

        # DG-005 — observability_version >= 2 (ERROR)
        obs_ver = manifest.get("observability_version")
        if obs_ver is None:
            out.append(
                DGViolation(
                    "DG-005",
                    "ERROR",
                    None,
                    None,
                    "observability_version absent du manifest",
                )
            )
        else:
            try:
                if int(obs_ver) < 2:
                    out.append(
                        DGViolation(
                            "DG-005",
                            "ERROR",
                            None,
                            None,
                            f"observability_version={obs_ver} < 2 (pre-P0 invalide)",
                        )
                    )
            except (TypeError, ValueError):
                out.append(
                    DGViolation(
                        "DG-005",
                        "ERROR",
                        None,
                        None,
                        f"observability_version non entier: {obs_ver}",
                    )
                )

        # DG-006 — feature_flags_hash présent, format 12 chars hex (WARNING)
        ffh = str(manifest.get("feature_flags_hash", ""))
        if not ffh:
            out.append(
                DGViolation(
                    "DG-006",
                    "WARNING",
                    None,
                    None,
                    "feature_flags_hash absent du manifest",
                )
            )
        elif not _HASH_RE.match(ffh):
            out.append(
                DGViolation(
                    "DG-006",
                    "WARNING",
                    None,
                    None,
                    f"feature_flags_hash format invalide: {ffh}",
                )
            )

        # DG-023 — config_hash présent (WARNING)
        if not manifest.get("config_hash", ""):
            out.append(
                DGViolation(
                    "DG-023", "WARNING", None, None, "config_hash absent du manifest"
                )
            )

        return out

    # ── Vérifications par enregistrement ─────────────────────────────────────

    def _check_record(
        self,
        idx: int,
        obs_id: Optional[str],
        rec: Dict,
    ) -> List[DGViolation]:
        out: List[DGViolation] = []

        # DG-003 — engine_version présent et non vide (ERROR)
        ev = rec.get("engine_version", "")
        if not ev or not isinstance(ev, str) or not ev.strip():
            out.append(
                DGViolation(
                    "DG-003", "ERROR", idx, obs_id, "engine_version absent ou vide"
                )
            )

        # DG-004 — git_commit format valide si présent (ERROR si présent mais invalide)
        gc = rec.get("git_commit", "")
        if gc and not _COMMIT_RE.match(str(gc)):
            out.append(
                DGViolation(
                    "DG-004", "ERROR", idx, obs_id, f"git_commit format invalide: {gc}"
                )
            )

        # DG-007 — ts présent, float, > 0 (ERROR)
        ts = rec.get("ts")
        if ts is None:
            out.append(DGViolation("DG-007", "ERROR", idx, obs_id, "ts absent"))
        elif not isinstance(ts, (int, float)) or float(ts) <= 0:
            out.append(
                DGViolation("DG-007", "ERROR", idx, obs_id, f"ts invalide: {ts}")
            )

        # DG-008 — ts_iso conforme ISO-8601 UTC (ERROR)
        ts_iso = rec.get("ts_iso", "")
        ts_iso_epoch: Optional[float] = None
        if not ts_iso:
            out.append(DGViolation("DG-008", "ERROR", idx, obs_id, "ts_iso absent"))
        else:
            try:
                dt = datetime.fromisoformat(str(ts_iso).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    out.append(
                        DGViolation(
                            "DG-008",
                            "ERROR",
                            idx,
                            obs_id,
                            "ts_iso sans fuseau horaire UTC",
                        )
                    )
                else:
                    ts_iso_epoch = dt.timestamp()
            except ValueError:
                out.append(
                    DGViolation(
                        "DG-008", "ERROR", idx, obs_id, f"ts_iso non ISO-8601: {ts_iso}"
                    )
                )

        # DG-009 — ts cohérent avec ts_iso ±1s (ERROR)
        if ts is not None and ts_iso_epoch is not None and isinstance(ts, (int, float)):
            delta = abs(float(ts) - ts_iso_epoch)
            if delta > 1.0:
                out.append(
                    DGViolation(
                        "DG-009",
                        "ERROR",
                        idx,
                        obs_id,
                        f"ts et ts_iso divergent de {delta:.2f}s > 1s",
                    )
                )

        # DG-012 + DG-013 — champs ERROR-obligatoires présents et non-null
        for fname in _REQUIRED_NON_NULL:
            if fname not in rec:
                out.append(
                    DGViolation(
                        "DG-012",
                        "ERROR",
                        idx,
                        obs_id,
                        f"champ obligatoire manquant: {fname}",
                    )
                )
            elif rec[fname] is None:
                out.append(
                    DGViolation(
                        "DG-013",
                        "ERROR",
                        idx,
                        obs_id,
                        f"champ obligatoire null: {fname}",
                    )
                )

        # DG-014 — types conformes (ERROR)
        score = rec.get("score")
        if score is not None and not isinstance(score, (int, float)):
            out.append(
                DGViolation(
                    "DG-014",
                    "ERROR",
                    idx,
                    obs_id,
                    f"score type invalide: {type(score).__name__}",
                )
            )
        cycle_val = rec.get("cycle")
        if cycle_val is not None and not isinstance(cycle_val, int):
            out.append(
                DGViolation(
                    "DG-014",
                    "ERROR",
                    idx,
                    obs_id,
                    f"cycle type invalide: {type(cycle_val).__name__}",
                )
            )
        ab = rec.get("all_blockers")
        if ab is not None and not isinstance(ab, list):
            out.append(
                DGViolation(
                    "DG-014", "ERROR", idx, obs_id, "all_blockers doit être list"
                )
            )

        # DG-015 — score dans [0, 100] (ERROR)
        if isinstance(score, (int, float)) and not (0.0 <= float(score) <= 100.0):
            out.append(
                DGViolation(
                    "DG-015", "ERROR", idx, obs_id, f"score={score} hors [0, 100]"
                )
            )

        # DG-016 — side valide (ERROR)
        side = rec.get("side")
        if side is not None and str(side) not in _VALID_SIDES:
            out.append(
                DGViolation("DG-016", "ERROR", idx, obs_id, f"side={side!r} invalide")
            )

        # DG-017 — price > 0 si side != HOLD (ERROR)
        price = rec.get("price")
        if side != "HOLD":
            if price is None:
                out.append(
                    DGViolation(
                        "DG-017", "ERROR", idx, obs_id, "price absent (side != HOLD)"
                    )
                )
            elif isinstance(price, (int, float)) and float(price) <= 0:
                out.append(
                    DGViolation("DG-017", "ERROR", idx, obs_id, f"price={price} <= 0")
                )

        # DG-018 — blockers cohérents avec trade_allowed (WARNING)
        trade_allowed = rec.get("trade_allowed")
        actionable = rec.get("actionable", True)
        if trade_allowed is False and actionable is True:
            if isinstance(ab, list) and len(ab) == 0:
                out.append(
                    DGViolation(
                        "DG-018",
                        "WARNING",
                        idx,
                        obs_id,
                        "trade_allowed=False + actionable=True mais all_blockers vide",
                    )
                )

        # DG-019 — regime dans les valeurs connues (WARNING)
        regime = rec.get("regime")
        if regime is not None and str(regime) not in _VALID_REGIMES:
            out.append(
                DGViolation(
                    "DG-019",
                    "WARNING",
                    idx,
                    obs_id,
                    f"regime={regime!r} non répertorié",
                )
            )

        # DG-020 — state_history est list si présent (ERROR)
        sh = rec.get("state_history")
        if sh is not None and not isinstance(sh, list):
            out.append(
                DGViolation(
                    "DG-020", "ERROR", idx, obs_id, "state_history doit être list"
                )
            )

        # DG-021 — features est dict (ERROR)
        feat = rec.get("features")
        if feat is not None and not isinstance(feat, dict):
            out.append(
                DGViolation("DG-021", "ERROR", idx, obs_id, "features doit être dict")
            )

        # DG-022 — packet_id non vide (ERROR)
        pid = rec.get("packet_id", "")
        if not pid or (isinstance(pid, str) and not pid.strip()):
            out.append(
                DGViolation("DG-022", "ERROR", idx, obs_id, "packet_id absent ou vide")
            )

        # DG-024 — replay possible : state_history ou features non vide (WARNING)
        sh_ok = isinstance(sh, list) and len(sh) > 0
        feat_ok = isinstance(feat, dict) and len(feat) > 0
        if not sh_ok and not feat_ok:
            out.append(
                DGViolation(
                    "DG-024",
                    "WARNING",
                    idx,
                    obs_id,
                    "state_history et features vides — replay theoriquement impossible",
                )
            )

        return out

    def _gen_cert_id(self) -> str:
        now = datetime.now(timezone.utc)
        q = (now.month - 1) // 3 + 1
        return f"CERT-{now.year}-Q{q}-{self._cert_seq:03d}"


# ── CLI ───────────────────────────────────────────────────────────────────────


def _load_manifest(path: Optional[str]) -> Optional[Dict]:
    if not path:
        return None
    try:
        import yaml  # type: ignore[import]

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("dataset_manifest", data)
    except Exception as exc:
        print(f"[WARN] manifest non chargé ({path}): {exc}", file=sys.stderr)
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="DatasetCertifier — applique la Data Governance Spec v1.0"
    )
    parser.add_argument("dataset_dir", help="Répertoire contenant les *.jsonl")
    parser.add_argument(
        "--manifest", "-m", default=None, help="Chemin vers EXP-xxx.yaml"
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Afficher seulement le niveau"
    )
    args = parser.parse_args()

    manifest = _load_manifest(args.manifest)
    report = DatasetCertifier().certify(Path(args.dataset_dir), manifest=manifest)

    if args.quiet:
        print(report.level)
    else:
        print(report.summary())

    sys.exit(0 if report.is_certifiable else 1)
