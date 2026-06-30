"""
regret_engine.py — Regret Analysis Engine

Le bot apprend aussi de ce qu'il N'A PAS PRIS.

Niveau tres rare. Tres puissant.

Principe :
  1. A chaque TRADE_REFUSED ou HOLD avec score >= seuil,
     le systeme enregistre le contexte (prix, features, regime)
  2. N cycles plus tard, il compare avec le prix actuel
  3. Si le prix a evolue dans la direction du signal refuse,
     c'est un "REGRET" : le bot aurait du trader
  4. Si la direction est inverse : c'est une "BONNE DECISION de refus"
  5. Les regrets s'accumulent en memoire et ajustent
     les seuils de confiance des modules qui ont refuse

Ce que ca change :
  - Un module qui refuse trop souvent de bons trades → son seuil descend
  - Un module qui refuse bien les mauvais trades → son seuil monte
  - Le systeme s'auto-calibre sur ses propres opportunites manquees

Exemple :
  BTC score=75, regime=bull_trend, conviction=MEDIUM
  → Refuse par: conviction (MEDIUM bloque)
  → 4h plus tard : BTC +3.2%
  → Regret enregistre: conviction a bloque un trade rentable
  → Score de "faussetes negativement" de ConvictionEngine incremente
  → Prochaine fois : seuil MEDIUM abaisse de 1 point

Stocke dans : databases/regret_analysis.jsonl
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.regret_engine")
_DB_PATH = os.getenv("REGRET_DB", "databases/regret_analysis.jsonl")
_CHECK_DELAY = int(os.getenv("REGRET_DELAY_CYCLES", "4"))  # evaluer N cycles plus tard
_MIN_MOVE_PCT = float(
    os.getenv("REGRET_MIN_MOVE", "0.015")
)  # mouvement min pour qualifier
_MIN_SCORE = int(os.getenv("REGRET_MIN_SCORE", "65"))  # score min pour enregistrer
_MAX_DB = int(os.getenv("REGRET_MAX_DB", "500"))


@dataclass
class RegretCandidate:
    """Trade refuse ou HOLD potentiellement rentable — en attente d'evaluation."""

    candidate_id: str
    ts: float
    symbol: str
    signal: str  # BUY ou SELL
    score: int
    regime: str
    price_at_signal: float
    refused_by: list = field(default_factory=list)
    conviction_level: str = "medium"
    evaluated: bool = False
    eval_cycle: int = 0  # cycle auquel evaluer
    current_cycle: int = 0


@dataclass
class RegretRecord:
    """Resultat de l'evaluation d'un candidat."""

    candidate_id: str
    ts_signal: float
    ts_evaluated: float
    symbol: str
    signal: str
    score: int
    regime: str
    price_signal: float
    price_eval: float
    move_pct: float  # mouvement observe
    direction_correct: bool  # True si le signal etait juste
    regret_value: float  # magnitude du regret [0, 1]
    regret_type: str  # MISSED_WIN / GOOD_REFUSAL / NEUTRAL
    refused_by: list = field(default_factory=list)
    conviction_level: str = "medium"
    # Quelle perte potentielle aurait-on evitee ?
    potential_pnl_pct: float = 0.0


class RegretEngine:
    """
    Analyse les opportunites manquees et ajuste les seuils en consequence.

    Usage dans advisor_loop :
        re = RegretEngine()
        # A chaque HOLD/REFUSE avec score >= 65 :
        re.register_candidate(symbol, signal, score, regime, price, refused_by, cycle)
        # A chaque cycle (calcul prix courant) :
        regrets = re.evaluate_pending(current_prices_dict, current_cycle)
        # Stats :
        re.stats()
        re.calibration_hints()
    """

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._candidates: list[RegretCandidate] = []
        self._records: list[RegretRecord] = []
        self._counter = 0
        self._ewma_delta: float = 0.0  # exponential moving average of raw delta
        self._load()

    # ── Enregistrement d'un candidat ─────────────────────────────────────────

    def register_candidate(
        self,
        symbol: str,
        signal: str,
        score: int,
        regime: str,
        price: float,
        refused_by: list,
        cycle: int,
        conviction_level: str = "medium",
    ) -> Optional[RegretCandidate]:
        """
        Enregistre un signal refuse (score >= seuil) comme candidat a evaluer.
        Sera evalue _CHECK_DELAY cycles plus tard.
        """
        if score < _MIN_SCORE:
            return None
        if signal not in ("BUY", "SELL"):
            return None

        self._counter += 1
        cid = f"{symbol}_{signal}_{int(time.time())}_{self._counter}"
        candidate = RegretCandidate(
            candidate_id=cid,
            ts=time.time(),
            symbol=symbol,
            signal=signal,
            score=score,
            regime=regime,
            price_at_signal=price,
            refused_by=refused_by[:],
            conviction_level=conviction_level,
            eval_cycle=cycle + _CHECK_DELAY,
            current_cycle=cycle,
        )
        self._candidates.append(candidate)
        _log.debug(
            "[RegretEngine] Candidat enregistre: %s %s score=%d | refus: %s",
            symbol,
            signal,
            score,
            refused_by,
        )
        return candidate

    # ── Evaluation des candidats en attente ───────────────────────────────────

    def evaluate_pending(
        self,
        current_prices: dict,  # {symbol: float}
        current_cycle: int,
    ) -> list[RegretRecord]:
        """
        Evalue tous les candidats dont le cycle d'eval est atteint.
        Retourne la liste des regrets generes ce cycle.
        """
        new_regrets = []
        remaining = []

        for c in self._candidates:
            if c.evaluated or current_cycle < c.eval_cycle:
                remaining.append(c)
                continue

            price_now = current_prices.get(c.symbol, 0.0)
            if price_now <= 0:
                remaining.append(c)
                continue

            c.evaluated = True
            record = self._evaluate(c, price_now)
            if record:
                self._records.append(record)
                self._save_record(record)
                if record.regret_type == "MISSED_WIN":
                    new_regrets.append(record)
                    _log.info(
                        "[RegretEngine] REGRET: %s %s | "
                        "signal=%.2f eval=%.2f move=%.2f%% | refuse: %s",
                        c.symbol,
                        c.signal,
                        c.price_at_signal,
                        price_now,
                        record.move_pct * 100,
                        c.refused_by,
                    )

        self._candidates = remaining
        return new_regrets

    def _evaluate(self, c: RegretCandidate, price_now: float) -> Optional[RegretRecord]:
        if c.price_at_signal == 0:
            return None

        move_pct = (price_now - c.price_at_signal) / c.price_at_signal

        # Le signal etait-il juste ?
        if c.signal == "BUY":
            direction_correct = move_pct > 0
            potential_pnl = move_pct
        else:  # SELL
            direction_correct = move_pct < 0
            potential_pnl = -move_pct

        abs_move = abs(move_pct)

        if abs_move < _MIN_MOVE_PCT:
            regret_type = "NEUTRAL"
            regret_value = 0.0
        elif direction_correct:
            regret_type = "MISSED_WIN"
            regret_value = min(1.0, abs_move / 0.05)  # 5% = regret max
        else:
            regret_type = "GOOD_REFUSAL"
            regret_value = 0.0

        return RegretRecord(
            candidate_id=c.candidate_id,
            ts_signal=c.ts,
            ts_evaluated=time.time(),
            symbol=c.symbol,
            signal=c.signal,
            score=c.score,
            regime=c.regime,
            price_signal=c.price_at_signal,
            price_eval=price_now,
            move_pct=round(move_pct, 6),
            direction_correct=direction_correct,
            regret_value=round(regret_value, 4),
            regret_type=regret_type,
            refused_by=c.refused_by[:],
            conviction_level=c.conviction_level,
            potential_pnl_pct=round(potential_pnl, 6),
        )

    # ── Calibration — que changer ? ───────────────────────────────────────────

    def calibration_hints(self) -> list[dict]:
        """
        Analyse les MISSED_WIN et retourne des recommandations de calibration.
        Ex: "conviction bloque 5 MISSED_WIN → abaisser seuil MEDIUM"
        """
        missed = [r for r in self._records if r.regret_type == "MISSED_WIN"]
        if not missed:
            return []

        refusal_count: dict[str, int] = {}
        refusal_value: dict[str, float] = {}
        for r in missed:
            for ref in r.refused_by:
                mod = ref.split(":")[0].strip()
                refusal_count[mod] = refusal_count.get(mod, 0) + 1
                refusal_value[mod] = refusal_value.get(mod, 0.0) + r.regret_value

        hints = []
        for mod, count in sorted(refusal_count.items(), key=lambda x: -x[1]):
            avg_val = refusal_value[mod] / count
            if count >= 3 and avg_val > 0.3:
                hints.append(
                    {
                        "module": mod,
                        "missed_wins": count,
                        "avg_regret": round(avg_val, 3),
                        "hint": f"{mod} a bloque {count} trades rentables "
                        f"(regret moy={avg_val:.0%}). "
                        f"Envisager d'assouplir les seuils.",
                    }
                )
        return hints

    def stats(self) -> dict:
        if not self._records:
            return {
                "total_evaluated": 0,
                "missed_wins": 0,
                "good_refusals": 0,
                "pending": len(self._candidates),
            }
        missed = sum(1 for r in self._records if r.regret_type == "MISSED_WIN")
        good = sum(1 for r in self._records if r.regret_type == "GOOD_REFUSAL")
        neutral = sum(1 for r in self._records if r.regret_type == "NEUTRAL")
        avg_regret = (
            sum(r.regret_value for r in self._records) / len(self._records)
            if self._records
            else 0.0
        )
        return {
            "total_evaluated": len(self._records),
            "missed_wins": missed,
            "good_refusals": good,
            "neutral": neutral,
            "pending": len(self._candidates),
            "avg_regret": round(avg_regret, 3),
            "refusal_accuracy": round(good / max(1, missed + good), 3),
        }

    def get_threshold_delta(
        self,
        current_regime: str = "",
        winrate_executed: float = 0.5,
        min_samples: int = 5,
        ewma_alpha: float = 0.3,
    ) -> int:
        """
        [ADR-0007 — PASSIVITÉ] Retourne TOUJOURS 0.

        Cette méthode calculait un delta de seuil appliqué automatiquement en production
        via GlobalRiskGate.apply_regret_delta(). Ce comportement a été gelé (ADR-0007) :
        toute auto-calibration active viole le principe de passivité des observateurs.

        Le calcul est conservé dans calibration_recommendation() pour la Phase 4 (ACE).
        L'application d'un delta requiert une validation humaine explicite via .env ou
        config/settings.py — jamais automatiquement.

        Pour obtenir la recommandation (lecture seule) :
            hint = regret_engine.calibration_recommendation(regime, winrate)
        """
        from config.feature_flags import FEATURE_AUTO_CALIBRATION

        if FEATURE_AUTO_CALIBRATION:
            # Mode legacy — déconseillé, activé uniquement si explicitement demandé
            return self._compute_threshold_delta(
                current_regime, winrate_executed, min_samples, ewma_alpha
            )
        # Mode passif (défaut) : zéro modification automatique des seuils
        return 0

    def calibration_recommendation(
        self,
        current_regime: str = "",
        winrate_executed: float = 0.5,
        min_samples: int = 5,
        ewma_alpha: float = 0.3,
    ) -> dict:
        """
        [Phase 4 — ACE] Recommandation de calibration (lecture seule).

        Retourne un dict: delta recommande, confiance, justification.
        NE MODIFIE JAMAIS de parametre — l'operateur decide de l'appliquer ou non.

        Returns:
            {
                "delta": int (-2 / -1 / 0 / +1),
                "confidence": float (0-1),
                "reason": str,
                "n_samples": int,
                "regime": str,
            }
        """
        delta = self._compute_threshold_delta(
            current_regime, winrate_executed, min_samples, ewma_alpha
        )
        stats = self.stats()
        n = stats["total_evaluated"]
        confidence = min(1.0, n / 50) if n >= min_samples else 0.0
        reason_map = {
            -2: f"Sur-filtrage fort en {current_regime} "
            f"(MISSED_WIN={stats.get('missed_wins', 0)})",
            -1: "Sur-filtrage modéré",
            0: "Calibration correcte",
            1: "Filtrage insuffisant (trop de bons refus manqués)",
        }
        return {
            "delta": delta,
            "confidence": round(confidence, 3),
            "reason": reason_map.get(delta, "?"),
            "n_samples": n,
            "regime": current_regime,
        }

    def _compute_threshold_delta(
        self,
        current_regime: str,
        winrate_executed: float,
        min_samples: int,
        ewma_alpha: float,
    ) -> int:
        """Calcul du delta - logique preservee pour calibration_recommendation()."""
        stats = self.stats()
        if stats["total_evaluated"] < min_samples:
            return 0

        missed = stats["missed_wins"]
        good = stats["good_refusals"]
        avg_r = stats.get("avg_regret", 0.0)
        total = missed + good
        if total == 0:
            return 0

        refusal_accuracy = good / total

        if missed > good and avg_r > 0.6:
            if winrate_executed <= refusal_accuracy and current_regime in (
                "sideways",
                "RANGE",
                "unknown",
                "UNKNOWN",
            ):
                raw_delta = -2
            else:
                raw_delta = -1
        elif refusal_accuracy > 0.70 and good > missed * 2:
            raw_delta = +1
        else:
            raw_delta = 0

        self._ewma_delta = (
            ewma_alpha * raw_delta + (1.0 - ewma_alpha) * self._ewma_delta
        )
        smoothed = round(self._ewma_delta)

        if raw_delta != smoothed:
            _log.debug(
                "[RegretEngine] EWMA delta: raw=%+d → smoothed=%+d (ewma=%.3f α=%.2f)",
                raw_delta,
                smoothed,
                self._ewma_delta,
                ewma_alpha,
            )
        return smoothed

    def recent_regrets(self, n: int = 5) -> list[str]:
        missed = sorted(
            [r for r in self._records if r.regret_type == "MISSED_WIN"],
            key=lambda x: x.ts_evaluated,
            reverse=True,
        )[:n]
        return [
            f"[REGRET] {r.symbol} {r.signal} score={r.score} "
            f"move={r.move_pct:.2%} | refuse par: {r.refused_by}"
            for r in missed
        ]

    # ── Persistance ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._db_path.exists():
            return
        try:
            with open(self._db_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        self._records.append(RegretRecord(**d))
                    except Exception:
                        pass
            self._records = self._records[-_MAX_DB:]
        except Exception as exc:
            _log.warning("[RegretEngine] Chargement: %s", exc)

    def _save_record(self, record: RegretRecord) -> None:
        try:
            with open(self._db_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record), default=str) + "\n")
        except Exception as exc:
            _log.warning("[RegretEngine] Sauvegarde: %s", exc)
