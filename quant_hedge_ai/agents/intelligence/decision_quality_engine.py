"""
decision_quality_engine.py — Decision Quality Engine

Un bon trade peut perdre. Un mauvais trade peut gagner.

Le bot ne doit pas apprendre de mauvaises leçons.

Ce module note la QUALITÉ de la décision indépendamment du résultat,
sur 5 critères de discipline :

  1. Process Respect    — la hiérarchie de décision a-t-elle été respectée ?
  2. Context Quality    — les données du contexte étaient-elles fiables ?
  3. Regime Coherence   — la stratégie correspondait-elle au régime ?
  4. Conviction Level   — la conviction était-elle suffisante ?
  5. Discipline Score   — le bot a-t-il respecté ses propres règles ?

Puis croise avec le résultat pour classifier :

  Bonne décision / bon résultat     → VALIDATED   ✓ apprendre
  Bonne décision / mauvais résultat → UNLUCKY     → ne pas pénaliser
  Mauvaise décision / bon résultat  → LUCKY       ⚠ ne pas renforcer
  Mauvaise décision / mauvais résultat → MISTAKE  ✗ corriger

Ce classement nourrit le ranker sans biaiser l'apprentissage.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path(os.getenv("DQE_DB", "databases/decision_quality.jsonl"))


class DecisionClass(str, Enum):
    VALIDATED = "validated"    # bonne déc + bon résultat
    UNLUCKY   = "unlucky"      # bonne déc + mauvais résultat
    LUCKY     = "lucky"        # mauvaise déc + bon résultat
    MISTAKE   = "mistake"      # mauvaise déc + mauvais résultat
    PENDING   = "pending"      # résultat non encore connu


@dataclass
class DecisionRecord:
    """Enregistrement d'une décision avec sa qualité et son résultat."""

    id:               str
    ts:               float
    symbol:           str
    action:           str
    regime:           str
    personality:      str
    signal_score:     int
    conviction_score: float
    conviction_level: str

    # Critères de qualité de la décision [0-100 chacun]
    process_score:    float = 0.0
    context_score:    float = 0.0
    regime_score:     float = 0.0
    discipline_score: float = 0.0

    # Score global décision [0-100]
    decision_quality: float = 0.0

    # Résultat (renseigné après fermeture)
    pnl_pct:          Optional[float] = None
    classification:   DecisionClass   = DecisionClass.PENDING
    closed_at:        Optional[float] = None

    # Seuil séparant bonne/mauvaise décision
    QUALITY_THRESHOLD: float = field(default=60.0, repr=False)

    def classify(self, pnl_pct: float) -> "DecisionRecord":
        self.pnl_pct   = pnl_pct
        self.closed_at = time.time()
        good_decision  = self.decision_quality >= self.QUALITY_THRESHOLD
        good_result    = pnl_pct > 0
        if good_decision and good_result:
            self.classification = DecisionClass.VALIDATED
        elif good_decision and not good_result:
            self.classification = DecisionClass.UNLUCKY
        elif not good_decision and good_result:
            self.classification = DecisionClass.LUCKY
        else:
            self.classification = DecisionClass.MISTAKE
        return self

    def ranker_weight(self) -> float:
        """
        Poids à donner à ce trade dans le ranker [0.0, 1.5].
        VALIDATED  → 1.5 (renforce fortement)
        UNLUCKY    → 0.5 (pénalise peu — la décision était bonne)
        LUCKY      → 0.3 (ne pas trop renforcer — chance)
        MISTAKE    → 1.0 (pénalise normalement)
        """
        return {
            DecisionClass.VALIDATED: 1.5,
            DecisionClass.UNLUCKY:   0.5,
            DecisionClass.LUCKY:     0.3,
            DecisionClass.MISTAKE:   1.0,
            DecisionClass.PENDING:   1.0,
        }[self.classification]

    def to_dict(self) -> dict:
        return {
            "id": self.id, "ts": self.ts, "symbol": self.symbol,
            "action": self.action, "regime": self.regime,
            "personality": self.personality,
            "signal_score": self.signal_score,
            "conviction_score": self.conviction_score,
            "conviction_level": self.conviction_level,
            "process_score": self.process_score,
            "context_score": self.context_score,
            "regime_score": self.regime_score,
            "discipline_score": self.discipline_score,
            "decision_quality": self.decision_quality,
            "pnl_pct": self.pnl_pct,
            "classification": self.classification.value,
            "closed_at": self.closed_at,
            "ranker_weight": self.ranker_weight(),
        }


class DecisionQualityEngine:
    """
    Évalue et archive la qualité de chaque décision de trading.

    Usage :
        dqe = DecisionQualityEngine()

        # Avant d'ouvrir la position
        rec = dqe.evaluate_decision(signal, conviction, regime, personality,
                                     no_trade_verdict, meta_allowed, gate_allowed)
        dqe.record(rec)

        # Après fermeture de position
        dqe.close_decision(order_id, pnl_pct)

        # Métriques
        stats = dqe.stats()
    """

    QUALITY_THRESHOLD = float(os.getenv("DQE_QUALITY_THRESHOLD", "60"))

    def __init__(self) -> None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._pending: dict[str, DecisionRecord] = {}   # order_id → record
        self._closed:  list[DecisionRecord]       = []
        self._load()

    # ── Évaluation ────────────────────────────────────────────────────────────

    def evaluate_decision(
        self,
        signal,
        conviction_score:   float,
        conviction_level:   str,
        regime:             str,
        personality_name:   str,
        no_trade_score:     float   = 0.0,   # score de rejet NoTrade (0=pas de raison)
        meta_allowed:       bool    = True,
        gate_allowed:       bool    = True,
        signal_age_s:       float   = 0.0,
        order_id:           str     = "",
    ) -> DecisionRecord:
        """
        Construit un DecisionRecord AVANT d'exécuter l'ordre.
        """
        sig_score = getattr(signal, "score", 0)
        action    = getattr(signal, "signal", "HOLD")
        symbol    = getattr(signal, "symbol", "?")

        # ── Critère 1 : Process Respect ────────────────────────────────────────
        # A-t-on respecté les couches de décision ?
        process_score = 100.0
        if not gate_allowed:
            process_score -= 40   # gate bloquait — on n'aurait pas dû passer
        if not meta_allowed:
            process_score -= 30
        if no_trade_score >= 50:
            process_score -= 25
        if signal_age_s > 300:
            process_score -= 20
        process_score = max(0.0, process_score)

        # ── Critère 2 : Context Quality ────────────────────────────────────────
        # La conviction reflète la qualité du contexte
        context_score = conviction_score

        # ── Critère 3 : Regime Coherence ──────────────────────────────────────
        regime_matrix = {
            ("bull_trend", "BUY"):   95, ("bull_trend", "SELL"):  20,
            ("bear_trend", "SELL"):  90, ("bear_trend", "BUY"):   15,
            ("sideways",   "BUY"):   55, ("sideways",   "SELL"):  55,
            ("flash_crash","BUY"):    5, ("flash_crash","SELL"):   5,
            ("high_volatility_regime","BUY"): 40,
            ("high_volatility_regime","SELL"): 40,
        }
        regime_score = float(regime_matrix.get((regime, action.upper()), 50))

        # ── Critère 4 : Discipline Score ──────────────────────────────────────
        discipline_score = 100.0
        if sig_score < 70:
            discipline_score -= (70 - sig_score) * 1.5   # pénalise les trades sous le seuil
        if conviction_level in ("minimal", "low"):
            discipline_score -= 30
        if action == "HOLD":
            discipline_score -= 50
        discipline_score = max(0.0, min(100.0, discipline_score))

        # ── Score global ───────────────────────────────────────────────────────
        decision_quality = (
            process_score    * 0.30 +
            context_score    * 0.25 +
            regime_score     * 0.25 +
            discipline_score * 0.20
        )

        rec = DecisionRecord(
            id                = order_id or f"dqe_{int(time.time()*1000)}",
            ts                = time.time(),
            symbol            = symbol,
            action            = action,
            regime            = regime,
            personality       = personality_name,
            signal_score      = int(sig_score),
            conviction_score  = round(conviction_score, 1),
            conviction_level  = conviction_level,
            process_score     = round(process_score, 1),
            context_score     = round(context_score, 1),
            regime_score      = round(regime_score, 1),
            discipline_score  = round(discipline_score, 1),
            decision_quality  = round(decision_quality, 1),
            QUALITY_THRESHOLD = self.QUALITY_THRESHOLD,
        )
        return rec

    # ── Persistance ───────────────────────────────────────────────────────────

    def record(self, rec: DecisionRecord) -> None:
        self._pending[rec.id] = rec
        logger.info(
            "[DQE] Décision enregistrée: %s %s qualité=%.0f/100 (%s)",
            rec.action, rec.symbol, rec.decision_quality,
            "BONNE" if rec.decision_quality >= self.QUALITY_THRESHOLD else "MAUVAISE",
        )

    def close_decision(self, order_id: str, pnl_pct: float) -> Optional[DecisionRecord]:
        rec = self._pending.pop(order_id, None)
        if rec is None:
            return None
        rec.classify(pnl_pct)
        self._closed.append(rec)
        self._append_to_file(rec)
        logger.info(
            "[DQE] Décision fermée: %s → %s (qualité=%.0f, pnl=%.2f%%)",
            rec.id, rec.classification.value,
            rec.decision_quality, pnl_pct * 100,
        )
        return rec

    # ── Métriques ─────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        closed = self._closed
        if not closed:
            return {"total": 0}

        by_class = {}
        for rec in closed:
            c = rec.classification.value
            by_class[c] = by_class.get(c, 0) + 1

        good_decisions  = [r for r in closed if r.decision_quality >= self.QUALITY_THRESHOLD]
        good_outcomes   = [r for r in closed if (r.pnl_pct or 0) > 0]
        validated       = [r for r in closed if r.classification == DecisionClass.VALIDATED]
        lucky           = [r for r in closed if r.classification == DecisionClass.LUCKY]
        unlucky         = [r for r in closed if r.classification == DecisionClass.UNLUCKY]
        mistakes        = [r for r in closed if r.classification == DecisionClass.MISTAKE]

        avg_quality = sum(r.decision_quality for r in closed) / len(closed)
        return {
            "total":               len(closed),
            "avg_decision_quality": round(avg_quality, 1),
            "good_decisions_pct":  round(len(good_decisions) / len(closed), 3),
            "good_outcomes_pct":   round(len(good_outcomes) / len(closed), 3),
            "by_class":            by_class,
            "validated_pct":       round(len(validated) / len(closed), 3),
            "lucky_pct":           round(len(lucky)     / len(closed), 3),
            "unlucky_pct":         round(len(unlucky)   / len(closed), 3),
            "mistake_pct":         round(len(mistakes)  / len(closed), 3),
            "pending":             len(self._pending),
        }

    def recent_quality_trend(self, n: int = 10) -> str:
        """Retourne la tendance récente de qualité : 'improving', 'stable', 'declining'."""
        if len(self._closed) < n * 2:
            return "insufficient_data"
        recent = self._closed[-n:]
        older  = self._closed[-n*2:-n]
        avg_r  = sum(r.decision_quality for r in recent) / n
        avg_o  = sum(r.decision_quality for r in older)  / n
        if avg_r > avg_o + 5:
            return "improving"
        if avg_r < avg_o - 5:
            return "declining"
        return "stable"

    # ── Interne ───────────────────────────────────────────────────────────────

    def _append_to_file(self, rec: DecisionRecord) -> None:
        try:
            with open(_DB_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec.to_dict()) + "\n")
        except Exception as exc:
            logger.warning("[DQE] Erreur écriture: %s", exc)

    def _load(self) -> None:
        if not _DB_PATH.exists():
            return
        try:
            lines = _DB_PATH.read_text(encoding="utf-8").strip().split("\n")
            for line in lines[-500:]:
                if not line.strip():
                    continue
                d   = json.loads(line)
                rec = DecisionRecord(
                    id=d["id"], ts=d["ts"], symbol=d["symbol"],
                    action=d["action"], regime=d["regime"],
                    personality=d["personality"],
                    signal_score=d["signal_score"],
                    conviction_score=d["conviction_score"],
                    conviction_level=d["conviction_level"],
                    process_score=d["process_score"],
                    context_score=d["context_score"],
                    regime_score=d["regime_score"],
                    discipline_score=d["discipline_score"],
                    decision_quality=d["decision_quality"],
                    pnl_pct=d.get("pnl_pct"),
                    classification=DecisionClass(d.get("classification", "pending")),
                    closed_at=d.get("closed_at"),
                )
                if rec.classification == DecisionClass.PENDING:
                    self._pending[rec.id] = rec
                else:
                    self._closed.append(rec)
            logger.info("[DQE] Chargé: %d décisions (%d pending)",
                        len(self._closed), len(self._pending))
        except Exception as exc:
            logger.warning("[DQE] Erreur chargement: %s", exc)
