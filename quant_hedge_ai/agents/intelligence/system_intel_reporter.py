"""
system_intel_reporter.py — Diagnostic complet du système, toutes les 6h.

Rôle : expliquer comment le SYSTÈME fonctionne et perçoit le marché —
pas une analyse de marché générique. Répond toujours aux mêmes questions :

  1. Le système est-il en bonne santé (dataset, exécution, décisions) ?
  2. Combien de trades depuis le dernier rapport et au total ?
  3. Quel est le P&L (réalisé, ouvert, par symbole) ?
  4. Comment le système perçoit le marché actuellement (régimes, signaux) ?
  5. Qu'est-ce qui a changé depuis le rapport précédent ?
  6. Quelle est la recommandation actionnable ?

Destination exclusive : bot Intelligence (@rapport_automatique_bot),
via INTEL_BOT_TOKEN — jamais mélangé avec @QuantCrpto_bot ou @mon_portfolio_bot.

Persistance d'un snapshot léger (cache/intel_reports/last_snapshot.json)
pour calculer les deltas entre deux rapports consécutifs.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.system_intel_reporter")

_SNAPSHOT_PATH = Path(
    os.getenv("INTEL_SNAPSHOT_PATH", "cache/intel_reports/last_snapshot.json")
)
_TRADES_LOG = Path(os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl"))
_INITIAL_CAPITAL = float(os.getenv("VIRTUAL_CAPITAL_USD", "100"))
_LM_SYSTEM_PROMPT = (
    "Tu es le module de diagnostic d'un systeme de trading crypto algorithmique. "
    "Tu expliques comment LE SYSTEME fonctionne et percoit le marche, "
    "pas une analyse de marche generique. Style factuel, sans markdown."
)


@dataclass
class _Snapshot:
    ts: float = 0.0
    n_closed: int = 0
    pnl_total: float = 0.0
    regimes: dict = field(default_factory=dict)  # symbol -> regime
    override_level: str = "CLEAR"
    awareness_level: str = "OK"


def _load_snapshot() -> _Snapshot:
    if not _SNAPSHOT_PATH.exists():
        return _Snapshot()
    try:
        data = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        return _Snapshot(**data)
    except Exception:
        return _Snapshot()


def _save_snapshot(snap: _Snapshot) -> None:
    try:
        _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SNAPSHOT_PATH.write_text(json.dumps(snap.__dict__, indent=2), encoding="utf-8")
    except Exception as exc:
        _log.debug("[IntelReporter] snapshot non sauvegardé: %s", exc)


# ── Lecture historique complet (paper_trades.jsonl) ────────────────────────────


def _read_closes() -> list[dict]:
    if not _TRADES_LOG.exists():
        return []
    closes = []
    try:
        for line in _TRADES_LOG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                ev = json.loads(line)
                if ev.get("event") == "CLOSE":
                    closes.append(ev)
    except Exception:
        pass
    return closes


def _compute_kpis(closes: list[dict]) -> dict:
    if not closes:
        return {
            "n": 0,
            "win_rate": 0.0,
            "pf": 0.0,
            "sharpe": 0.0,
            "max_dd": 0.0,
            "total_pnl": 0.0,
            "by_symbol": {},
        }
    n = len(closes)
    pnls = [float(c.get("pnl_usd", 0) or 0) for c in closes]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total_pnl = sum(pnls)

    equity = [_INITIAL_CAPITAL]
    for p in pnls:
        equity.append(equity[-1] + p)
    peak, max_dd = equity[0], 0.0
    for e in equity:
        if e > peak:
            peak = e
        if peak > 0:
            dd = (peak - e) / peak * 100
            if dd > max_dd:
                max_dd = dd

    gross_win = sum(wins)
    gross_loss = abs(sum(losses)) if losses else 0
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

    pcts = [float(c.get("pnl_pct", 0) or 0) for c in closes]
    mean_p = sum(pcts) / n if n else 0
    var_p = sum((p - mean_p) ** 2 for p in pcts) / n if n > 1 else 0
    std_p = math.sqrt(var_p) if var_p > 0 else 0
    sharpe = mean_p / std_p if std_p > 0 else 0.0

    by_symbol: dict[str, dict] = {}
    for c in closes:
        sym = c.get("symbol", "?")
        pnl = float(c.get("pnl_usd", 0) or 0)
        d = by_symbol.setdefault(sym, {"n": 0, "pnl": 0.0, "wins": 0})
        d["n"] += 1
        d["pnl"] += pnl
        if pnl > 0:
            d["wins"] += 1

    return {
        "n": n,
        "win_rate": len(wins) / n * 100,
        "pf": pf,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "total_pnl": total_pnl,
        "by_symbol": by_symbol,
    }


class SystemIntelReporter:
    """
    Diagnostic complet du système — destiné exclusivement au bot Intelligence.

    Usage :
        reporter = SystemIntelReporter()
        text = reporter.build_report(
            cycle=cycle,
            results=results,
            pos_manager=pos_manager,
            awareness_state=awareness_current,
            override=executive_override,
            regret_engine=regret_engine,
            mistake_memory=mistake_memory,
            black_box=black_box,
            activity_tracker=activity_tracker,
            stability_monitor=stability_monitor,
        )
    """

    def __init__(self) -> None:
        self._lm_available: Optional[bool] = None

    # ── Construction principale ──────────────────────────────────────────────

    def build_report(
        self,
        cycle: int,
        results: list,
        pos_manager: Any = None,
        awareness_state: Any = None,
        override: Any = None,
        regret_engine: Any = None,
        mistake_memory: Any = None,
        black_box: Any = None,
        activity_tracker: Any = None,
        stability_monitor: Any = None,
        dataset_report: Any = None,
    ) -> str:
        prev = _load_snapshot()
        now = time.time()
        elapsed_h = (now - prev.ts) / 3600 if prev.ts else 0.0

        closes = _read_closes()
        kpis = _compute_kpis(closes)
        n_since = max(0, kpis["n"] - prev.n_closed)
        pnl_since = kpis["total_pnl"] - prev.pnl_total

        regimes_now = self._current_regimes(results)
        regime_changes = [
            f"{sym}: {prev.regimes.get(sym, '?')} → {reg}"
            for sym, reg in regimes_now.items()
            if prev.regimes.get(sym) and prev.regimes.get(sym) != reg
        ]

        ctx = {
            "cycle": cycle,
            "elapsed_h": elapsed_h,
            "kpis": kpis,
            "n_since": n_since,
            "pnl_since": pnl_since,
            "regimes_now": regimes_now,
            "regime_changes": regime_changes,
            "pos_manager_stats": self._pos_stats(pos_manager),
            "awareness": self._awareness_ctx(awareness_state),
            "override": self._override_ctx(override),
            "decision_funnel": self._decision_funnel(results),
            "dataset": self._dataset_ctx(dataset_report),
            "activity": self._activity_ctx(activity_tracker),
            "stability": self._stability_ctx(stability_monitor),
            "regret": self._regret_ctx(regret_engine),
            "mistakes": self._mistakes_ctx(mistake_memory),
        }

        text = self._render(ctx, cycle)

        _save_snapshot(
            _Snapshot(
                ts=now,
                n_closed=kpis["n"],
                pnl_total=kpis["total_pnl"],
                regimes=regimes_now,
                override_level=ctx["override"].get("level", "CLEAR"),
                awareness_level=ctx["awareness"].get("level", "OK"),
            )
        )
        return text

    # ── Extraction contextes secondaires ─────────────────────────────────────

    def _current_regimes(self, results: list) -> dict:
        out = {}
        for r in results or []:
            sym = r.get("symbol")
            regime = r.get("regime", "unknown")
            if sym:
                out[sym] = regime
        return out

    def _pos_stats(self, pos_manager: Any) -> dict:
        if not pos_manager:
            return {}
        try:
            return pos_manager.stats()
        except Exception:
            return {}

    def _awareness_ctx(self, awareness_state: Any) -> dict:
        if not awareness_state:
            return {"level": "OK"}
        return {
            "level": (
                getattr(awareness_state, "level", None).name
                if hasattr(awareness_state, "level")
                else "OK"
            ),
            "size_factor": getattr(awareness_state, "size_factor", 1.0),
            "safe_mode": getattr(awareness_state, "safe_mode", False),
            "drifts": [
                d.message for d in getattr(awareness_state, "active_drifts", [])[:3]
            ],
        }

    def _override_ctx(self, override: Any) -> dict:
        if not override:
            return {"level": "CLEAR"}
        try:
            return override.metrics_snapshot()
        except Exception:
            return {"level": "CLEAR"}

    def _decision_funnel(self, results: list) -> dict:
        total = len(results or [])
        allowed = sum(1 for r in (results or []) if r.get("trade_allowed"))
        blocked = total - allowed
        scored = [
            r for r in (results or []) if r.get("signal") and r["signal"].score >= 50
        ]
        return {
            "total_evaluated": total,
            "allowed": allowed,
            "blocked": blocked,
            "above_50": len(scored),
        }

    def _dataset_ctx(self, dataset_report: Any) -> dict:
        if not dataset_report:
            return {}
        return {
            "violations": len(getattr(dataset_report, "violations", []) or []),
            "burnin_eligible": getattr(dataset_report, "burnin_eligible", False),
            "integrity_pct": getattr(dataset_report, "integrity_pct", 0.0),
        }

    def _activity_ctx(self, activity_tracker: Any) -> dict:
        if activity_tracker is None:
            return {}
        try:
            return activity_tracker.report()
        except Exception:
            return {}

    def _stability_ctx(self, stability_monitor: Any) -> dict:
        if stability_monitor is None:
            return {}
        try:
            return stability_monitor.report()
        except Exception:
            return {}

    def _regret_ctx(self, regret_engine: Any) -> dict:
        if not regret_engine:
            return {}
        try:
            return regret_engine.stats()
        except Exception:
            return {}

    def _mistakes_ctx(self, mistake_memory: Any) -> dict:
        if not mistake_memory:
            return {}
        try:
            return mistake_memory.stats()
        except Exception:
            return {}

    # ── Rendu texte ───────────────────────────────────────────────────────────

    def _render(self, ctx: dict, cycle: int) -> str:
        lines = [f"DIAGNOSTIC SYSTÈME — Cycle {cycle}", ""]

        elapsed = ctx["elapsed_h"]
        period = f"{elapsed:.1f}h" if elapsed > 0 else "première exécution"
        lines.append(f"Période couverte : {period}")
        lines.append("")

        # 1. Santé système
        dataset = ctx["dataset"]
        if dataset:
            status = "OK" if dataset.get("violations", 0) == 0 else "DEGRADE"
            lines.append(
                f"SANTÉ SYSTÈME : {status} | "
                f"intégrité dataset={dataset.get('integrity_pct', 100):.0f}% | "
                f"violations={dataset.get('violations', 0)}"
            )
        stab = ctx["stability"]
        if stab:
            state = stab.get("state", "stable")
            lines.append(
                f"  Stabilité comportementale : {state} | "
                f"flips régime={stab.get('regime_flips_10c', 0)}/10c"
            )
        lines.append("")

        # 2. Activité trading — depuis dernier rapport + cumulé
        kpis = ctx["kpis"]
        lines.append(
            f"ACTIVITÉ TRADING : {ctx['n_since']} trade(s) depuis le dernier rapport "
            f"| {kpis['n']} au total"
        )
        if kpis["n"] > 0:
            lines.append(
                f"  Cumulé : WR={kpis['win_rate']:.0f}% | PF={kpis['pf']:.2f} | "
                f"Sharpe={kpis['sharpe']:.2f} | MaxDD={kpis['max_dd']:.1f}%"
            )
        lines.append("")

        # 3. P&L
        sign_total = "+" if kpis["total_pnl"] >= 0 else ""
        sign_since = "+" if ctx["pnl_since"] >= 0 else ""
        lines.append(
            f"P&L : {sign_total}{kpis['total_pnl']:.2f}$ total "
            f"({sign_since}{ctx['pnl_since']:.2f}$ depuis dernier rapport)"
        )
        pos_stats = ctx["pos_manager_stats"]
        if pos_stats:
            lines.append(
                f"  Positions ouvertes : {pos_stats.get('open_count', 0)} | "
                f"PnL latent : {pos_stats.get('open_pnl_usd', 0):+.2f}$"
            )
        by_symbol = kpis.get("by_symbol", {})
        if by_symbol:
            top = sorted(by_symbol.items(), key=lambda x: x[1]["pnl"], reverse=True)[:5]
            for sym, d in top:
                lines.append(f"    {sym}: {d['n']}T {d['pnl']:+.2f}$")
        lines.append("")

        # 4. Perception marché — régimes actuels + funnel décisionnel
        regimes_now = ctx["regimes_now"]
        if regimes_now:
            reg_str = " | ".join(f"{s}:{r}" for s, r in list(regimes_now.items())[:8])
            lines.append(f"PERCEPTION MARCHÉ : {reg_str}")
        funnel = ctx["decision_funnel"]
        if funnel.get("total_evaluated", 0) > 0:
            lines.append(
                f"  Funnel décisionnel : {funnel['total_evaluated']} signaux évalués | "
                f"{funnel['above_50']} score>=50 | "
                f"{funnel['allowed']} autorisés | {funnel['blocked']} bloqués"
            )
        lines.append("")

        # 5. Ce qui a changé
        changes = []
        if ctx["regime_changes"]:
            changes.extend(ctx["regime_changes"][:3])
        aw = ctx["awareness"]
        if aw.get("level", "OK") != "OK":
            changes.append(f"Self-Awareness → {aw['level']}")
        ov = ctx["override"]
        if ov.get("level", "CLEAR") != "CLEAR":
            changes.append(f"Executive Override → {ov['level']}")
        if changes:
            lines.append("CE QUI A CHANGÉ :")
            for c in changes:
                lines.append(f"  - {c}")
            lines.append("")

        # 6. Recommandation
        lines.append("RECOMMANDATION :")
        lines.append(f"  {self._recommend(ctx)}")

        return "\n".join(lines)

    def _recommend(self, ctx: dict) -> str:
        dataset = ctx["dataset"]
        if dataset and dataset.get("violations", 0) > 0:
            return (
                f"{dataset['violations']} violation(s) dataset détectée(s). "
                "Intervention requise avant de continuer le burn-in."
            )

        ov = ctx["override"]
        if ov.get("level") == "VETO":
            return "HALTE COMPLÈTE. Aucune position jusqu'à stabilisation."
        if ov.get("level") in ("MINIMAL", "CAREFUL"):
            return (
                f"Prudence active ({ov['level']}). Taille réduite, surveiller recovery."
            )

        aw = ctx["awareness"]
        if aw.get("level") in ("DANGER", "CRITICAL"):
            return (
                "Dérive comportementale critique — réduire taille et surveiller régime."
            )

        kpis = ctx["kpis"]
        if kpis["n"] == 0:
            return (
                "Aucun trade fermé encore — burn-in en phase d'accumulation, "
                "rien à signaler."
            )

        if kpis["n"] >= 100:
            return (
                f"Seuil 100 trades atteint ({kpis['n']}). "
                "Lancer scripts/burnin_calibration_v3.py puis scripts/prelive_gate.py."
            )

        remaining = 100 - kpis["n"]
        return (
            f"Burn-in en cours — {remaining} trade(s) restant(s) avant calibration. "
            "Système stable."
        )

    # ── LM Studio (optionnel, narration enrichie) ────────────────────────────

    def narrate(self, structured_text: str) -> Optional[str]:
        """Tente d'enrichir le rapport structuré via LM Studio. None si indisponible."""
        if self._lm_available is False:
            return None
        try:
            from lm_studio import client as lm_client

            prompt = (
                "Reformule ce diagnostic systeme en 4-6 phrases naturelles, "
                "sans markdown, en gardant tous les chiffres exacts:\n\n"
                f"{structured_text}"
            )
            text = lm_client.chat(
                prompt, system=_LM_SYSTEM_PROMPT, max_tokens=300, temperature=0.3
            )
            self._lm_available = True
            return text.strip()
        except Exception as exc:
            _log.debug("[IntelReporter] LM Studio indisponible: %s", exc)
            self._lm_available = False
            return None
