"""
mistake_memory.py — Cerveau autonome d'apprentissage des erreurs

Ce module donne au bot la capacité de :
  1. ENREGISTRER chaque trade avec son contexte complet (pourquoi il a tradé)
  2. ANALYSER si un trade fermé était une erreur (et POURQUOI)
  3. EXPLIQUER en clair la raison de l'erreur
  4. APPRENDRE : produire des règles de blocage pour ne plus la répéter
  5. BLOQUER les configurations qui ont mené à des erreurs répétées

Format des erreurs mémorisées (JSONL) :
  {
    "ts": 1234567890,
    "order_id": "...",
    "symbol": "BTC/USDT",
    "signal": "BUY",
    "score": 72,
    "regime": "sideways",
    "regime_at_entry": "sideways",
    "conviction_level": "medium",
    "pnl_pct": -0.025,
    "error_type": "REGIME_MISMATCH",
    "explanation": "Signal BUY dans un régime sideways — la stratégie momentum ne fonctionne pas en range",  # noqa: E501
    "context": { ... features ... },
    "rule_generated": "sideways + momentum + score<80 -> BLOCK",
    "blocked_count": 0   # combien de fois cette règle a depuis bloqué un trade
  }

Types d'erreurs détectées :
  - REGIME_MISMATCH       : signal momentum en range, short en bull, etc.
  - LOW_CONVICTION_LOSS   : conviction LOW ou MEDIUM → perte > 2%
  - FOMO_ENTRY            : entrée après move >3% dans la direction
  - OVERTRADING           : 3+ trades perdants consécutifs
  - HIGH_VOL_ENTRY        : entrée en haute volatilité sans score >= 80
  - LATE_ENTRY            : signal expiré (age >5min) mais exécuté
  - CORRELATION_TRAP      : positions trop corrélées → perte simultanée
  - CONSECUTIVE_LOSS      : 3e perte consécutive sur même symbole
  - UNKNOWN               : perte non catégorisée
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.mistake_memory")
_DB_PATH = os.getenv("MISTAKE_DB", "databases/mistake_memory.jsonl")


# ── Types d'erreurs ───────────────────────────────────────────────────────────


class ErrorType:
    REGIME_MISMATCH = "REGIME_MISMATCH"
    LOW_CONVICTION_LOSS = "LOW_CONVICTION_LOSS"
    FOMO_ENTRY = "FOMO_ENTRY"
    OVERTRADING = "OVERTRADING"
    HIGH_VOL_ENTRY = "HIGH_VOL_ENTRY"
    LATE_ENTRY = "LATE_ENTRY"
    CORRELATION_TRAP = "CORRELATION_TRAP"
    CONSECUTIVE_LOSS = "CONSECUTIVE_LOSS"
    TIME_STOP = "TIME_STOP"
    GOOD_TRADE = "GOOD_TRADE"
    UNLUCKY = "UNLUCKY"
    UNKNOWN = "UNKNOWN"


# ── Règle de blocage générée automatiquement ─────────────────────────────────


@dataclass
class BlockRule:
    rule_id: str
    error_type: str
    conditions: dict  # ex: {"regime": "sideways", "signal": "BUY", "max_score": 79}
    explanation: str  # pourquoi cette règle existe
    created_ts: float = field(default_factory=time.time)
    trigger_count: int = 0  # combien de fois cette règle a bloqué un trade
    confirmed_saves: int = 0  # combien de fois le trade bloqué aurait été perdant

    def matches(self, context: dict) -> bool:
        """Retourne True si le contexte déclenche cette règle de blocage."""
        for key, val in self.conditions.items():
            if key == "max_score":
                if context.get("score", 100) > val:
                    return False
            elif key == "min_score":
                if context.get("score", 0) < val:
                    return False
            elif key == "regime":
                if context.get("regime") != val:
                    return False
            elif key == "signal":
                if context.get("signal") != val:
                    return False
            elif key == "conviction_level":
                if context.get("conviction_level") not in (
                    val if isinstance(val, list) else [val]
                ):
                    return False
            elif key == "max_vol":
                if context.get("atr_ratio", 0) <= val:
                    return False
            elif key == "consecutive_losses_min":
                if context.get("consecutive_losses", 0) < val:
                    return False
        return True

    def describe(self) -> str:
        cond_str = " + ".join(f"{k}={v}" for k, v in self.conditions.items())
        return (
            f"[{self.error_type}] {cond_str} -> BLOCK | triggers={self.trigger_count}"
        )


# ── Résultat de vérification ──────────────────────────────────────────────────


@dataclass
class MistakeCheckResult:
    blocked: bool
    reason: str
    rule_id: Optional[str] = None
    similar_mistakes: int = 0  # nb d'erreurs similaires mémorisées

    def __bool__(self) -> bool:
        return not self.blocked


# ── Cerveau principal ─────────────────────────────────────────────────────────


class MistakeMemory:
    """
    Cerveau autonome d'apprentissage des erreurs.

    Usage dans advisor_loop :
        mm = MistakeMemory()

        # Avant un trade
        check = mm.check_before_trade(  # noqa: E501
            symbol, signal, score, regime, features, consecutive_losses
        )
        if check.blocked:
            log.info("Trade bloqué par MistakeMemory: %s", check.reason)
            continue

        # Après fermeture d'une position
        mm.record_trade_result(order_id, symbol, signal, score, regime,
                               conviction_level, pnl_pct, context_features,
                               signal_age_sec, consecutive_losses)
    """

    MIN_LOSS_TO_ANALYZE = float(
        os.getenv("MM_MIN_LOSS_PCT", "-0.003")
    )  # -0.3% min pour analyser (couvre time_stop ~-0.5%)
    REPEAT_BLOCK_THRESHOLD = int(
        os.getenv("MM_REPEAT_THRESHOLD", "2")
    )  # 2 erreurs similaires → règle
    RULE_EXPIRY_DAYS = int(
        os.getenv("MM_RULE_EXPIRY_DAYS", "30")
    )  # règles expirent après 30j
    MAX_MISTAKES_DB = int(os.getenv("MM_MAX_DB", "1000"))  # max enregistrements

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._mistakes: list[dict] = self._load()
        self._rules: list[BlockRule] = []
        self._rebuild_rules()

    # ── API principale ─────────────────────────────────────────────────────────

    def check_before_trade(
        self,
        symbol: str,
        signal: str,
        score: int,
        regime: str,
        features: dict,
        consecutive_losses: int = 0,
        conviction_level: str = "medium",
        signal_age_sec: float = 0.0,
    ) -> MistakeCheckResult:
        """
        Vérifie si ce trade ressemble à une erreur passée.
        Retourne MistakeCheckResult(blocked=True, reason=...) si à bloquer.
        """
        context = {
            "symbol": symbol,
            "signal": signal,
            "score": score,
            "regime": regime,
            "conviction_level": conviction_level,
            "consecutive_losses": consecutive_losses,
            "signal_age_sec": signal_age_sec,
            "atr_ratio": features.get("atr_ratio", 0.0),
            "rsi": features.get("rsi", 50.0),
            "volume_ratio": features.get("volume_ratio", 1.0),
        }

        # Vérifie chaque règle active
        for rule in self._rules:
            if rule.matches(context):
                rule.trigger_count += 1
                similar = self._count_similar(rule.error_type, regime, signal)
                _log.info(
                    "[MistakeMemory] BLOQUÉ rule=%s reason=%s (triggers=%d similar=%d)",
                    rule.rule_id,
                    rule.explanation,
                    rule.trigger_count,
                    similar,
                )
                return MistakeCheckResult(
                    blocked=True,
                    reason=f"[{rule.error_type}] {rule.explanation}",
                    rule_id=rule.rule_id,
                    similar_mistakes=similar,
                )

        return MistakeCheckResult(blocked=False, reason="OK")

    def record_trade_result(
        self,
        order_id: str,
        symbol: str,
        signal: str,
        score: int,
        regime: str,
        conviction_level: str,
        pnl_pct: float,
        context_features: dict,
        signal_age_sec: float = 0.0,
        consecutive_losses: int = 0,
        exit_reason: str = "",
        personality: str = "",
        entry_price: float = 0.0,
        exit_price: float = 0.0,
        opened_at: float = 0.0,
        tp_pct: float = 0.0,
        sl_pct: float = 0.0,
        tp_price: float = 0.0,
        sl_price: float = 0.0,
        atr_entry: float = 0.0,
    ) -> Optional[dict]:
        """
        Enregistre le résultat d'un trade et analyse s'il était une erreur.
        Génère automatiquement une règle de blocage si erreur répétée.
        Retourne le record enregistré.
        """
        # Analyse le type d'erreur
        error_type, explanation = self._classify_error(
            pnl_pct,
            signal,
            score,
            regime,
            conviction_level,
            context_features,
            signal_age_sec,
            consecutive_losses,
            exit_reason=exit_reason,
            personality=personality,
        )

        _closed_at = time.time()
        record = {
            "ts": _closed_at,
            "order_id": order_id,
            "symbol": symbol,
            "signal": signal,
            "score": score,
            "regime": regime,
            "conviction_level": conviction_level,
            "pnl_pct": round(pnl_pct, 6),
            "exit_reason": exit_reason,
            "personality": personality,
            "error_type": error_type,
            "explanation": explanation,
            "trade": {
                "entry_price": round(entry_price, 8) if entry_price else None,
                "exit_price": round(exit_price, 8) if exit_price else None,
                "opened_at": opened_at if opened_at else None,
                "closed_at": _closed_at,
                "duration_s": round(_closed_at - opened_at, 1) if opened_at else None,
                "tp_pct": round(tp_pct, 6) if tp_pct else None,
                "sl_pct": round(sl_pct, 6) if sl_pct else None,
                "tp_price": round(tp_price, 8) if tp_price else None,
                "sl_price": round(sl_price, 8) if sl_price else None,
                "atr_entry": round(atr_entry, 8) if atr_entry else None,
            },
            "context": {
                k: context_features.get(k)
                for k in (
                    "rsi",
                    "atr_ratio",
                    "momentum",
                    "volume_ratio",
                    "macd_hist",
                    "ema_bullish",
                    "bb_pct",
                    "trend_strength",
                )
            },
            "signal_age_sec": signal_age_sec,
            "consecutive_losses": consecutive_losses,
            "rule_generated": None,
            "blocked_count": 0,
        }

        # Si erreur → tenter de générer une règle
        if error_type not in (ErrorType.GOOD_TRADE, ErrorType.UNLUCKY):
            similar_count = self._count_similar(error_type, regime, signal)
            if similar_count >= self.REPEAT_BLOCK_THRESHOLD:
                rule = self._generate_rule(
                    error_type,
                    regime,
                    signal,
                    score,
                    conviction_level,
                    context_features,
                    explanation,
                )
                if rule:
                    record["rule_generated"] = rule.rule_id
                    self._rules.append(rule)
                    _log.warning(
                        "[MistakeMemory] NOUVELLE RÈGLE générée: %s | %s",
                        rule.rule_id,
                        rule.describe(),
                    )

        self._mistakes.append(record)
        self._trim()
        self._save(record)

        if error_type not in (ErrorType.GOOD_TRADE, ErrorType.UNLUCKY):
            _log.info(
                "[MistakeMemory] Erreur enregistrée: %s | %s → pnl=%.2f%%",
                error_type,
                explanation,
                pnl_pct * 100,
            )
        return record

    # ── Classification des erreurs ────────────────────────────────────────────

    def _classify_error(
        self,
        pnl_pct: float,
        signal: str,
        score: int,
        regime: str,
        conviction_level: str,
        features: dict,
        signal_age_sec: float,
        consecutive_losses: int,
        exit_reason: str = "",
        personality: str = "",
    ) -> tuple[str, str]:
        """Retourne (error_type, explication lisible)."""

        # Trade gagnant ou neutre
        if pnl_pct >= 0.005:  # > 0.5% = clairement positif
            return ErrorType.GOOD_TRADE, "Trade gagnant — aucune erreur détectée"

        # Petite perte < seuil d'analyse
        if pnl_pct > self.MIN_LOSS_TO_ANALYZE:
            return (
                ErrorType.UNLUCKY,
                f"Petite perte ({pnl_pct:.2%}) — probablement malchance",
            )

        # ── TIME_STOP ─────────────────────────────────────────────────────────
        if exit_reason == "time_stop":
            return ErrorType.TIME_STOP, (
                f"Position expirée au time_stop ({pnl_pct:.2%}) — "
                f"TP non atteint. Régime={regime}, personnalité={personality or '?'}"
            )

        # ── REGIME_MISMATCH ───────────────────────────────────────────────────
        momentum_in_range = (
            signal in ("BUY", "SELL")
            and regime == "sideways"
            and personality not in ("mean_reversion", "range_fade")
        )
        long_in_bear = signal == "BUY" and regime in ("bear_trend", "flash_crash")
        short_in_bull = signal == "SELL" and regime == "bull_trend"
        if momentum_in_range:
            return ErrorType.REGIME_MISMATCH, (
                f"Signal {signal} dans régime sideways — la stratégie directionnelle "
                f"échoue en range. Attendre un régime trending."
            )
        if long_in_bear:
            return ErrorType.REGIME_MISMATCH, (
                f"Signal BUY dans régime {regime} — contre-tendance majeure. "
                f"N'acheter que sur signal exceptionnel (score ≥85) en bear."
            )
        if short_in_bull:
            return ErrorType.REGIME_MISMATCH, (
                "Signal SELL dans régime bull_trend — contre-tendance. "
                "Short uniquement si score ≥80 et conviction HIGH+"
            )

        # ── LOW_CONVICTION_LOSS ───────────────────────────────────────────────
        if conviction_level in ("low", "minimal") and pnl_pct < -0.015:
            return ErrorType.LOW_CONVICTION_LOSS, (
                f"Perte {pnl_pct:.2%} avec conviction {conviction_level} — "
                f"ne pas trader avec conviction faible. Attendre signal HIGH+."
            )

        # ── FOMO_ENTRY ────────────────────────────────────────────────────────
        momentum = features.get("momentum", 0.0)
        if signal == "BUY" and momentum > 0.03 and pnl_pct < -0.01:
            return ErrorType.FOMO_ENTRY, (
                f"Achat après hausse de {momentum:.1%} — entrée FOMO trop tardive. "
                f"Le mouvement était déjà fait."
            )
        if signal == "SELL" and momentum < -0.03 and pnl_pct < -0.01:
            return ErrorType.FOMO_ENTRY, (
                f"Short après baisse de {abs(momentum):.1%} — entrée FOMO trop tardive."
                " La baisse était déjà faite."
            )

        # ── HIGH_VOL_ENTRY ────────────────────────────────────────────────────
        atr_ratio = features.get("atr_ratio", 0.0)
        if atr_ratio > 0.03 and score < 80:
            return ErrorType.HIGH_VOL_ENTRY, (
                f"Entrée haute vol (ATR={atr_ratio:.2%}) score {score}/100."
                " Exiger score ≥80 et conviction HIGH."
            )

        # ── LATE_ENTRY ────────────────────────────────────────────────────────
        if signal_age_sec > 300 and pnl_pct < -0.01:
            return ErrorType.LATE_ENTRY, (
                f"Signal vieux de {signal_age_sec:.0f}s exécuté → perte {pnl_pct:.2%}. "
                f"Ignorer les signaux de plus de 5 minutes."
            )

        # ── CONSECUTIVE_LOSS ──────────────────────────────────────────────────
        if consecutive_losses >= 3:
            return ErrorType.CONSECUTIVE_LOSS, (
                f"3e perte consécutive ({consecutive_losses} pertes d'affilée)."
                " Marché défavorable — réduire taille et attendre retournement."
            )

        # ── OVERTRADING ───────────────────────────────────────────────────────
        recent_losses = sum(
            1
            for m in self._mistakes[-10:]
            if m.get("pnl_pct", 0) < -0.01 and m.get("symbol") == "any"
        )
        if recent_losses >= 3 and pnl_pct < -0.01:
            return ErrorType.OVERTRADING, (
                f"3+ pertes récentes détectées — probable overtrading. "
                f"Le bot devrait se reposer 30 minutes."
            )

        return ErrorType.UNKNOWN, (
            f"Perte {pnl_pct:.2%} — cause non identifiée. "
            f"Score={score}, régime={regime}, conviction={conviction_level}"
        )

    # ── Génération de règles ──────────────────────────────────────────────────

    def _generate_rule(
        self,
        error_type: str,
        regime: str,
        signal: str,
        score: int,
        conviction_level: str,
        features: dict,
        explanation: str,
    ) -> Optional[BlockRule]:
        """Génère une règle de blocage automatique depuis une erreur répétée."""
        rule_id = f"{error_type}_{regime}_{signal}_{int(time.time())}"

        if error_type == ErrorType.REGIME_MISMATCH:
            return BlockRule(
                rule_id=rule_id,
                error_type=error_type,
                conditions={"regime": regime, "signal": signal, "max_score": 79},
                explanation=explanation,
            )

        if error_type == ErrorType.LOW_CONVICTION_LOSS:
            return BlockRule(
                rule_id=rule_id,
                error_type=error_type,
                conditions={"conviction_level": ["low", "minimal"], "max_score": 74},
                explanation=explanation,
            )

        if error_type == ErrorType.FOMO_ENTRY:
            return BlockRule(
                rule_id=rule_id,
                error_type=error_type,
                conditions={"regime": regime, "signal": signal, "max_score": 79},
                explanation=explanation,
            )

        if error_type == ErrorType.HIGH_VOL_ENTRY:
            atr = features.get("atr_ratio", 0.03)
            return BlockRule(
                rule_id=rule_id,
                error_type=error_type,
                conditions={"max_vol": atr * 0.8, "max_score": 79},
                explanation=explanation,
            )

        if error_type == ErrorType.CONSECUTIVE_LOSS:
            return BlockRule(
                rule_id=rule_id,
                error_type=error_type,
                conditions={"consecutive_losses_min": 3, "max_score": 84},
                explanation=explanation,
            )

        if error_type == ErrorType.TIME_STOP:
            # TIME_STOP répété dans un régime → forcer score plus élevé
            return BlockRule(
                rule_id=rule_id,
                error_type=error_type,
                conditions={"regime": regime, "signal": signal, "max_score": 74},
                explanation=explanation,
            )

        return None

    # ── Stats & reporting ──────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Résumé des erreurs mémorisées."""
        if not self._mistakes:
            return {"total": 0, "errors": {}, "rules_active": 0}
        total = len(self._mistakes)
        by_type: dict[str, int] = {}
        for m in self._mistakes:
            t = m.get("error_type", "UNKNOWN")
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total": total,
            "errors": by_type,
            "rules_active": len(self._rules),
            "good_trades": by_type.get(ErrorType.GOOD_TRADE, 0),
            "error_rate": round(
                (
                    total
                    - by_type.get(ErrorType.GOOD_TRADE, 0)
                    - by_type.get(ErrorType.UNLUCKY, 0)
                )
                / max(1, total),
                3,
            ),
        }

    def explain_last_mistakes(self, n: int = 5) -> list[str]:
        """Retourne les N dernières erreurs en texte lisible."""
        errors = [
            m
            for m in self._mistakes
            if m.get("error_type") not in (ErrorType.GOOD_TRADE, ErrorType.UNLUCKY)
        ]
        recent = sorted(errors, key=lambda x: x.get("ts", 0), reverse=True)[:n]
        return [
            f"[{m['error_type']}] {m['symbol']} {m['signal']} "
            f"pnl={m['pnl_pct']:.2%} | {m['explanation']}"
            for m in recent
        ]

    def active_rules_summary(self) -> list[str]:
        return [r.describe() for r in self._rules]

    # ── Persistance ───────────────────────────────────────────────────────────

    def _load(self) -> list[dict]:
        if not self._db_path.exists():
            return []
        records = []
        with open(self._db_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        r = json.loads(line)
                        # Sanitize: pnl_pct must be a fraction (|val| <= 1.0 normally).
                        # Values outside [-2, 2] were stored as percentages by mistake.
                        pnl = r.get("pnl_pct", 0.0)
                        if isinstance(pnl, (int, float)) and abs(pnl) > 2.0:
                            r["pnl_pct"] = pnl / 100.0
                            _log.debug(
                                "[MistakeMemory] pnl_pct sanitisé: %.4f -> %.6f",
                                pnl,
                                r["pnl_pct"],
                            )
                        records.append(r)
                    except json.JSONDecodeError as exc:
                        _log.warning(
                            "[MistakeMemory] Ligne ignorée (JSON invalide): %s", exc
                        )
        return records[-self.MAX_MISTAKES_DB :]

    def _save(self, record: dict) -> None:
        try:
            with open(self._db_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as exc:
            _log.warning("[MistakeMemory] Sauvegarde échouée: %s", exc)

    def _trim(self) -> None:
        if len(self._mistakes) > self.MAX_MISTAKES_DB:
            self._mistakes = self._mistakes[-self.MAX_MISTAKES_DB :]

    def _rebuild_rules(self) -> None:
        """Reconstruit les règles depuis l'historique des erreurs au démarrage."""
        from collections import Counter

        error_counts: Counter = Counter()
        for m in self._mistakes:
            et = m.get("error_type", "")
            if et not in (ErrorType.GOOD_TRADE, ErrorType.UNLUCKY, ""):
                key = (et, m.get("regime", ""), m.get("signal", ""))
                error_counts[key] += 1
        for (et, regime, signal), count in error_counts.items():
            if count >= self.REPEAT_BLOCK_THRESHOLD:
                existing = any(
                    r.error_type == et
                    and r.conditions.get("regime") == regime
                    and r.conditions.get("signal") == signal
                    for r in self._rules
                )
                if not existing:
                    rule = self._generate_rule(
                        et,
                        regime,
                        signal,
                        75,
                        "medium",
                        {},
                        f"Règle reconstruite: {et}",
                    )
                    if rule:
                        self._rules.append(rule)
        if self._rules:
            _log.info(
                "[MistakeMemory] %d règles reconstruites depuis l'historique",
                len(self._rules),
            )

    def _count_similar(self, error_type: str, regime: str, signal: str) -> int:
        return sum(
            1
            for m in self._mistakes
            if m.get("error_type") == error_type
            and m.get("regime") == regime
            and m.get("signal") == signal
        )
