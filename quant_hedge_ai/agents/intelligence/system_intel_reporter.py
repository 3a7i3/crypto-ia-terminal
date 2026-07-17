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
_LM_SYSTEM_PROMPT = (
    "Tu es le module de diagnostic d'un systeme de trading crypto algorithmique. "
    "Tu expliques comment LE SYSTEME fonctionne et percoit le marche, "
    "pas une analyse de marche generique. Style factuel, sans markdown."
)

# Borne canonique du dataset propre — source unique scripts/data_quality.py
# (CLEAN_DATA_SINCE_V3, addendum ADR-0012). Label dérivé dynamiquement : le
# texte "post-2026-06-25" codé en dur était périmé (réconciliation 2026-07-12)
# alors que le calcul de N utilisait déjà la borne v3.
try:
    from scripts.data_quality import CLEAN_DATA_SINCE_ACTIVE as _CLEAN_SINCE

    _CLEAN_SINCE_LABEL = _CLEAN_SINCE.strftime("%Y-%m-%d")
except Exception:  # pragma: no cover — import direct hors racine repo
    _CLEAN_SINCE_LABEL = "borne canonique"


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
    """CLOSE events filtrés par CLEAN_DATA_SINCE (ADR-0011) — même filtre que
    le CRI (tools/cri_calculator.py), pour que ce rapport et le calcul de
    calibration-readiness comptent le même N."""
    try:
        from tools.cri_calculator import load_clean_trades

        return load_clean_trades(_TRADES_LOG)
    except Exception:
        return []


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

    from infra.wallet_sync import get_wallet_sync

    equity = [get_wallet_sync().initial_capital()]
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


def _stall_anomaly(trade_stall_h: float, n_total: int) -> Optional[str]:
    """Alerte famine de trading — moteur actif mais plus aucun trade.

    Constat 2026-07-14 : 26h sans aucun trade (restart 13/07 = rotation
    d'univers, plus aucun candidat ne franchissait son seuil de régime) et
    aucun panneau ne le signalait — l'opérateur a dû le déduire de N figé.
    Observateur passif : signale, ne modifie jamais rien (ADR-0007).
    Seuil : INTEL_TRADE_STALL_ALERT_H (défaut 12h), 0 = désactivé.
    """
    try:
        threshold_h = float(os.getenv("INTEL_TRADE_STALL_ALERT_H", "12"))
    except ValueError:
        threshold_h = 12.0
    if threshold_h <= 0 or n_total <= 0:
        return None
    if trade_stall_h < threshold_h:
        return None
    return (
        f"aucun trade clôturé depuis {trade_stall_h:.0f}h "
        f"(moteur actif, N figé à {n_total})"
    )


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
        last_close_ts = max((float(c.get("ts", 0) or 0) for c in closes), default=0.0)
        trade_stall_h = (now - last_close_ts) / 3600 if last_close_ts else 0.0

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
            "trade_stall_h": trade_stall_h,
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
        violations = getattr(dataset_report, "violations", []) or []
        # "OPEN sans CLOSE" est ambigu pendant que le système tourne : une
        # position actuellement ouverte (légitime) produit la même signature
        # qu'une vraie position fantôme abandonnée. Le gate de démarrage gère
        # déjà la vraie détection/remédiation — ici on ne remonte que les
        # violations qui ne peuvent PAS être expliquées par une position en
        # cours (doublons, NaN, schéma...).
        real_violations = [v for v in violations if "OPEN sans CLOSE" not in v]
        return {
            "violations": len(real_violations),
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
        """
        Rapport volontairement condensé : les chiffres bruts (WR/PF/Sharpe/MaxDD,
        détail par symbole) sont déjà disponibles via @mon_portfolio_bot
        (/portfolio, /validate). Ce rapport se concentre sur ce que les autres
        bots ne disent pas : pourquoi le système agit ainsi, ce qui a changé,
        et la recommandation — pas une redite des stats.
        """
        elapsed = ctx["elapsed_h"]
        period = f"{elapsed:.1f}h" if elapsed > 0 else "1er rapport"
        lines = [f"DIAGNOSTIC SYSTÈME — Cycle {cycle} ({period})", ""]

        # 1. Santé système — une ligne, uniquement si anomalie
        dataset = ctx["dataset"]
        stab = ctx["stability"]
        anomalies = []
        if dataset and dataset.get("violations", 0) > 0:
            anomalies.append(f"{dataset['violations']} violation(s) dataset")
        if stab and stab.get("state", "stable") != "stable":
            anomalies.append(f"comportement {stab['state']}")
        stall = _stall_anomaly(ctx.get("trade_stall_h", 0.0), ctx["kpis"].get("n", 0))
        if stall:
            anomalies.append(stall)
        lines.append(
            "SANTÉ : OK"
            if not anomalies
            else f"SANTÉ : ALERTE — {' | '.join(anomalies)}"
        )

        # 2. Activité depuis dernier rapport — pas de cumulé (déjà sur /validate)
        kpis = ctx["kpis"]
        sign = "+" if ctx["pnl_since"] >= 0 else ""
        lines.append(
            f"DEPUIS DERNIER RAPPORT : {ctx['n_since']} trade(s) clôturé(s) "
            f"({sign}{ctx['pnl_since']:.2f}$) | "
            f"N canonique (post-{_CLEAN_SINCE_LABEL}) {kpis['n']} trades"
        )
        lines.append("")

        # 3. Perception marché — narration groupée par régime, pas une liste brute
        narrative = self._market_narrative(ctx["regimes_now"])
        if narrative:
            lines.append(f"MARCHÉ : {narrative}")
        funnel = ctx["decision_funnel"]
        if funnel.get("total_evaluated", 0) > 0:
            lines.append(
                f"  → {funnel['allowed']}/{funnel['total_evaluated']} signaux "
                f"autorisés, {funnel['blocked']} bloqués par les gates de risque"
            )
        lines.append("")

        # 4. Ce qui a changé — uniquement si quelque chose a changé
        changes = list(ctx["regime_changes"][:3])
        aw = ctx["awareness"]
        if aw.get("level", "OK") != "OK":
            changes.append(f"Self-Awareness → {aw['level']}")
        ov = ctx["override"]
        if ov.get("level", "CLEAR") != "CLEAR":
            changes.append(f"Executive Override → {ov['level']}")
        if changes:
            lines.append("CHANGEMENTS : " + " | ".join(changes))
            lines.append("")

        # 5. Recommandation — toujours présente, c'est l'essentiel du message
        lines.append(f"RECOMMANDATION : {self._recommend(ctx)}")

        return "\n".join(lines)

    def _market_narrative(self, regimes_now: dict) -> str:
        """Regroupe les régimes par catégorie plutôt que de lister chaque paire."""
        if not regimes_now:
            return ""
        groups: dict[str, list[str]] = {}
        for sym, regime in regimes_now.items():
            groups.setdefault(regime, []).append(sym.replace("/USDT", ""))

        labels = {
            "bull_trend": "tendance haussière",
            "bear_trend": "tendance baissière",
            "sideways": "range/consolidation",
            "breakout": "cassure en cours",
            "unknown": "régime indéterminé",
        }
        parts = []
        for regime, syms in sorted(groups.items(), key=lambda x: -len(x[1])):
            label = labels.get(regime, regime)
            names = ", ".join(syms[:4]) + ("..." if len(syms) > 4 else "")
            parts.append(f"{len(syms)} en {label} ({names})")
        return " | ".join(parts)

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

        if _stall_anomaly(ctx.get("trade_stall_h", 0.0), kpis["n"]):
            return (
                "Trading à l'arrêt : aucun candidat ne franchit son seuil de "
                "régime depuis le dernier trade (cf ligne Gate du panneau AI "
                "DECISION). Burn-in suspendu — décision opérateur requise "
                "(univers/seuils), aucun ajustement automatique ne sera fait."
            )

        if kpis["n"] >= 100:
            return (
                f"Seuil 100 trades canoniques atteint "
                f"({kpis['n']}, post-{_CLEAN_SINCE_LABEL}). "
                "Lancer scripts/burnin_calibration_v3.py puis scripts/prelive_gate.py."
            )

        remaining = 100 - kpis["n"]
        return (
            f"Burn-in en cours — {remaining} trade(s) canonique(s) restant(s) avant "
            "calibration. Système stable."
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
