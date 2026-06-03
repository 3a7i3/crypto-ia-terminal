"""
portfolio_brain.py — Portfolio Brain

Le bot pense portefeuille, pas trade isolé.

Analyse en temps réel :
  1. Exposition totale (notionnel total / capital)
  2. Corrélation BTC/ETH/SOL (trop corrélé = exposition cachée)
  3. Concentration risk (trop de capital sur un seul actif)
  4. Regime exposure cap (trop de positions dans le même régime)
  5. Futures leverage cap (levier agrégé max)
  6. Capital fragmentation (trop de petites positions)
  7. Opportunity ranking global (quel actif mérite le capital ?)

Retourne :
  PortfolioVerdict(allowed, reason, size_factor, capital_available)

Le capital est déployé comme un général déploie ses troupes.

Migration DecisionPacket :
  - PortfolioBrain.approve_packet() — API souveraine sur DecisionPacket.
    Produit la transition RISK_EVALUATED → APPROVED, ou appelle packet.reject().
    Chaque check est tracé dans reasoning + features du packet.
  - check_new_trade() classique préservé pour compatibilité ascendante.

Souveraineté : risk_gate protège le système (signal, régime, session).
portfolio_brain protège le portefeuille (exposition, corrélation, concentration).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.risk.portfolio_brain")
# ── Corrélations crypto historiques (approximations) ─────────────────────────
# Mis à jour dynamiquement si données disponibles, sinon valeurs par défaut
_DEFAULT_CORRELATIONS = {
    ("BTC/USDT", "ETH/USDT"): 0.85,
    ("BTC/USDT", "SOL/USDT"): 0.78,
    ("ETH/USDT", "SOL/USDT"): 0.80,
    ("BTC/USDT", "BTC/USDT"): 1.00,
    ("ETH/USDT", "ETH/USDT"): 1.00,
    ("SOL/USDT", "SOL/USDT"): 1.00,
}


@dataclass
class PortfolioVerdict:
    allowed: bool
    reason: str
    size_factor: float  # multiplicateur taille [0.0, 1.0]
    capital_available: float  # capital estimé disponible pour ce trade
    warnings: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.allowed


@dataclass
class PortfolioSnapshot:
    total_exposure_usd: float = 0.0
    total_exposure_pct: float = 0.0  # % du capital total engagé
    n_positions: int = 0
    by_symbol: dict = field(default_factory=dict)
    by_regime: dict = field(default_factory=dict)
    correlation_risk: float = 0.0  # [0,1] risque corrélation agrégé
    leverage_weighted: float = 0.0  # levier moyen pondéré
    open_pnl_usd: float = 0.0


class PortfolioBrain:
    """
    Gestionnaire de risque portefeuille global.

    Usage :
        brain = PortfolioBrain(total_capital=1000)
        verdict = brain.check_new_trade("BTC/USDT", "BUY", 55.0, regime="bull_trend",
                                         open_positions=pos_manager.get_open())
        if verdict.allowed:
            exec_engine.create_futures_order(...)
    """

    # ── Limites globales ──────────────────────────────────────────────────────
    MAX_TOTAL_EXPOSURE_PCT = float(
        os.getenv("PB_MAX_EXPOSURE_PCT", "0.40")
    )  # 40% du capital max
    MAX_SINGLE_SYMBOL_PCT = float(
        os.getenv("PB_MAX_SYMBOL_PCT", "0.20")
    )  # 20% sur un seul actif
    MAX_SAME_REGIME_PCT = float(
        os.getenv("PB_MAX_REGIME_PCT", "0.30")
    )  # 30% dans même régime
    MAX_LEVERAGE_WEIGHTED = float(
        os.getenv("PB_MAX_LEVERAGE", "2.0")
    )  # levier agrégé max
    MAX_CORRELATION_RISK = float(
        os.getenv("PB_MAX_CORRELATION", "0.75")
    )  # risque corrélation max
    MIN_FRAGMENTATION_USD = float(
        os.getenv("PB_MIN_POSITION_USD", "10.0")
    )  # taille minimum
    MAX_POSITIONS = int(os.getenv("PB_MAX_POSITIONS", "5"))  # max positions simultanées
    MAX_SAME_DIRECTION = int(
        os.getenv("PB_MAX_SAME_DIRECTION", "3")
    )  # max long ou short

    def __init__(self, total_capital: float = 1000.0) -> None:
        self._capital = total_capital
        self._corr_matrix = dict(_DEFAULT_CORRELATIONS)
        self._history: list[dict] = []

    def update_capital(self, capital: float) -> None:
        self._capital = max(1.0, capital)

    # ── Vérification principale ───────────────────────────────────────────────

    def check_new_trade(
        self,
        symbol: str,
        action: str,
        size_usd: float,
        regime: str,
        open_positions: list,  # list[Position]
        leverage: int = 1,
        conviction_score: float = 50.0,
    ) -> PortfolioVerdict:
        """
        Vérifie si ce nouveau trade est compatible avec l'état du portefeuille.
        Retourne un verdict avec facteur de taille ajusté.
        """
        snap = self._snapshot(open_positions)
        warnings = []
        factors = []

        # ── 1. Exposition totale ──────────────────────────────────────────────
        new_exposure_pct = (snap.total_exposure_usd + size_usd) / self._capital
        if new_exposure_pct > self.MAX_TOTAL_EXPOSURE_PCT:
            overshoot = new_exposure_pct - self.MAX_TOTAL_EXPOSURE_PCT
            f = max(0.0, 1.0 - overshoot / 0.10)
            factors.append(f)
            if f <= 0:
                return PortfolioVerdict(
                    allowed=False,
                    reason=f"Exposition totale trop élevée: {new_exposure_pct:.0%} > {self.MAX_TOTAL_EXPOSURE_PCT:.0%}",
                    size_factor=0.0,
                    capital_available=0.0,
                    warnings=warnings,
                    metrics=snap.__dict__,
                )
            warnings.append(f"Exposition {new_exposure_pct:.0%} — taille réduite")

        # ── 2. Concentration sur l'actif ──────────────────────────────────────
        sym_exposure = snap.by_symbol.get(symbol, 0.0)
        sym_pct = (sym_exposure + size_usd) / self._capital
        if sym_pct > self.MAX_SINGLE_SYMBOL_PCT:
            overshoot = sym_pct - self.MAX_SINGLE_SYMBOL_PCT
            f = max(0.0, 1.0 - overshoot / 0.10)
            factors.append(f)
            if f <= 0:
                return PortfolioVerdict(
                    allowed=False,
                    reason=f"Concentration trop forte sur {symbol}: {sym_pct:.0%}",
                    size_factor=0.0,
                    capital_available=0.0,
                    warnings=warnings,
                    metrics=snap.__dict__,
                )
            warnings.append(f"Concentration {symbol} {sym_pct:.0%}")

        # ── 3. Exposition au régime ───────────────────────────────────────────
        regime_exposure = snap.by_regime.get(regime, 0.0)
        regime_pct = (regime_exposure + size_usd) / self._capital
        if regime_pct > self.MAX_SAME_REGIME_PCT:
            f = max(0.3, 1.0 - (regime_pct - self.MAX_SAME_REGIME_PCT) / 0.10)
            factors.append(f)
            warnings.append(f"Régime '{regime}' sur-exposé: {regime_pct:.0%}")

        # ── 4. Corrélation ────────────────────────────────────────────────────
        corr_risk = self._correlation_risk(symbol, open_positions)
        if corr_risk > self.MAX_CORRELATION_RISK:
            f = max(0.4, 1.0 - (corr_risk - self.MAX_CORRELATION_RISK) / 0.25)
            factors.append(f)
            warnings.append(f"Corrélation élevée: {corr_risk:.2f}")

        # ── 5. Levier agrégé ──────────────────────────────────────────────────
        new_lev = self._weighted_leverage(open_positions, size_usd, leverage)
        if new_lev > self.MAX_LEVERAGE_WEIGHTED:
            f = max(0.3, self.MAX_LEVERAGE_WEIGHTED / new_lev)
            factors.append(f)
            warnings.append(f"Levier agrégé: ×{new_lev:.1f}")

        # ── 6. Nombre de positions ────────────────────────────────────────────
        if snap.n_positions >= self.MAX_POSITIONS:
            return PortfolioVerdict(
                allowed=False,
                reason=f"Max positions atteint: {snap.n_positions}/{self.MAX_POSITIONS}",
                size_factor=0.0,
                capital_available=0.0,
                warnings=warnings,
                metrics=snap.__dict__,
            )

        # ── 7. Position opposée sur même symbole ─────────────────────────────
        is_long = action.upper() == "BUY"
        opp_side = "short" if is_long else "long"
        for p in open_positions:
            if (
                getattr(p, "symbol", None) == symbol
                and getattr(p, "side", None) is not None
                and p.side.value == opp_side
            ):
                return PortfolioVerdict(
                    allowed=False,
                    reason=f"Position {opp_side.upper()} existante sur {symbol} — hedge interdit",
                    size_factor=0.0,
                    capital_available=0.0,
                    warnings=warnings,
                    metrics=snap.__dict__,
                )

        # ── 8. Direction dominante ────────────────────────────────────────────
        longs = sum(
            1
            for p in open_positions
            if getattr(p, "side", None) and p.side.value == "long"
        )
        shorts = sum(
            1
            for p in open_positions
            if getattr(p, "side", None) and p.side.value == "short"
        )
        if is_long and longs >= self.MAX_SAME_DIRECTION:
            f = 0.5
            factors.append(f)
            warnings.append(f"Direction long sur-représentée: {longs} positions")
        elif not is_long and shorts >= self.MAX_SAME_DIRECTION:
            f = 0.5
            factors.append(f)
            warnings.append(f"Direction short sur-représentée: {shorts} positions")

        # ── 9. Fragmentation ──────────────────────────────────────────────────
        if size_usd < self.MIN_FRAGMENTATION_USD:
            return PortfolioVerdict(
                allowed=False,
                reason=f"Taille ${size_usd:.0f} trop petite (min ${self.MIN_FRAGMENTATION_USD:.0f})",
                size_factor=0.0,
                capital_available=0.0,
                warnings=warnings,
                metrics=snap.__dict__,
            )

        # ── Facteur final ─────────────────────────────────────────────────────
        final_factor = min(factors) if factors else 1.0
        # Bonus conviction élevée
        if conviction_score >= 80 and not factors:
            final_factor = min(1.2, final_factor * 1.1)

        capital_avail = max(
            0.0, self._capital * self.MAX_TOTAL_EXPOSURE_PCT - snap.total_exposure_usd
        )

        if warnings:
            _log.info(
                "[PortfolioBrain] Warnings: %s | factor=%.2f",
                " | ".join(warnings),
                final_factor,
            )

        return PortfolioVerdict(
            allowed=True,
            reason="OK" if not warnings else " | ".join(warnings[:2]),
            size_factor=round(final_factor, 3),
            capital_available=round(capital_avail, 2),
            warnings=warnings,
            metrics={
                "total_exposure_pct": round(snap.total_exposure_pct, 3),
                "n_positions": snap.n_positions,
                "corr_risk": round(corr_risk, 3),
                "leverage_weighted": round(new_lev, 2),
                "open_pnl_usd": round(snap.open_pnl_usd, 2),
            },
        )

    # ── API DecisionPacket ────────────────────────────────────────────────────

    def approve_packet(
        self,
        packet,
        open_positions: list,
        order_size_usd: float = 0.0,
    ) -> "PortfolioVerdict":
        """
        Évaluation portefeuille depuis un DecisionPacket.

        SOUVERAINETÉ : produit la transition RISK_EVALUATED → APPROVED,
        ou appelle packet.reject() si le portefeuille ne peut absorber la position.

                Écrit dans packet.features :
                    pb_exposure_pct, pb_symbol_pct, pb_corr_risk, pb_leverage_weighted,
                    pb_size_factor, pb_capital_available
                Écrit dans packet.metadata :
                    pb_warnings

        Args:
            packet          : DecisionPacket en état RISK_EVALUATED
            open_positions  : positions ouvertes (list[Position])
            order_size_usd  : taille estimée de l'ordre en USD
        """
        from core.decision_packet import (
            DecisionState,
            ReasoningCategory,
            ReasoningSeverity,
        )

        actor = "portfolio_brain"
        packet.add_agent(actor)

        _CONV_SCORE = {"VERY_HIGH": 90, "HIGH": 75, "MEDIUM": 50, "LOW": 25, "SKIP": 0}
        conviction_score = _CONV_SCORE.get(packet.conviction.value, 50)
        is_long = packet.side.value == "LONG"
        symbol = packet.symbol
        regime = packet.regime.value
        size_usd = order_size_usd

        snap = self._snapshot(open_positions)
        warnings: list[str] = []
        factors: list[float] = []

        # ── 1. Exposition totale ──────────────────────────────────────────
        new_exposure_pct = (snap.total_exposure_usd + size_usd) / self._capital
        packet.features["pb_exposure_pct"] = round(new_exposure_pct, 4)
        if new_exposure_pct > self.MAX_TOTAL_EXPOSURE_PCT:
            overshoot = new_exposure_pct - self.MAX_TOTAL_EXPOSURE_PCT
            f = max(0.0, 1.0 - overshoot / 0.10)
            factors.append(f)
            if f <= 0:
                reason = f"Exposition totale {new_exposure_pct:.0%} > seuil {self.MAX_TOTAL_EXPOSURE_PCT:.0%}"
                packet.add_reasoning(
                    actor,
                    reason,
                    confidence_impact=-30.0,
                    category=ReasoningCategory.PORTFOLIO_EXPOSURE,
                    severity=ReasoningSeverity.CRITICAL,
                )
                packet.reject(actor, reason)
                return PortfolioVerdict(
                    allowed=False,
                    reason=reason,
                    size_factor=0.0,
                    capital_available=0.0,
                    warnings=warnings,
                    metrics=snap.__dict__,
                )
            msg = f"Exposition {new_exposure_pct:.0%} — taille réduite (×{f:.2f})"
            warnings.append(msg)
            packet.add_reasoning(
                actor,
                msg,
                confidence_impact=-8.0,
                category=ReasoningCategory.PORTFOLIO_EXPOSURE,
                severity=ReasoningSeverity.WARNING,
            )
        else:
            packet.add_reasoning(
                actor,
                f"Exposition totale OK: {new_exposure_pct:.0%}",
                confidence_impact=2.0,
                category=ReasoningCategory.PORTFOLIO_EXPOSURE,
            )

        # ── 2. Concentration symbole ──────────────────────────────────────
        sym_exposure = snap.by_symbol.get(symbol, 0.0)
        sym_pct = (sym_exposure + size_usd) / self._capital
        packet.features["pb_symbol_pct"] = round(sym_pct, 4)
        if sym_pct > self.MAX_SINGLE_SYMBOL_PCT:
            overshoot = sym_pct - self.MAX_SINGLE_SYMBOL_PCT
            f = max(0.0, 1.0 - overshoot / 0.10)
            factors.append(f)
            if f <= 0:
                reason = f"Concentration {symbol}: {sym_pct:.0%} > seuil {self.MAX_SINGLE_SYMBOL_PCT:.0%}"
                packet.add_reasoning(
                    actor,
                    reason,
                    confidence_impact=-25.0,
                    category=ReasoningCategory.PORTFOLIO_CONCENTRATION,
                    severity=ReasoningSeverity.CRITICAL,
                )
                packet.reject(actor, reason)
                return PortfolioVerdict(
                    allowed=False,
                    reason=reason,
                    size_factor=0.0,
                    capital_available=0.0,
                    warnings=warnings,
                    metrics=snap.__dict__,
                )
            msg = f"Concentration {symbol} {sym_pct:.0%} — taille réduite"
            warnings.append(msg)
            packet.add_reasoning(
                actor,
                msg,
                confidence_impact=-5.0,
                category=ReasoningCategory.PORTFOLIO_CONCENTRATION,
                severity=ReasoningSeverity.WARNING,
            )
        else:
            packet.add_reasoning(
                actor,
                f"Concentration {symbol} OK: {sym_pct:.0%}",
                confidence_impact=1.0,
                category=ReasoningCategory.PORTFOLIO_CONCENTRATION,
            )

        # ── 3. Exposition au régime ───────────────────────────────────────
        regime_exposure = snap.by_regime.get(regime, 0.0)
        regime_pct = (regime_exposure + size_usd) / self._capital
        if regime_pct > self.MAX_SAME_REGIME_PCT:
            f = max(0.3, 1.0 - (regime_pct - self.MAX_SAME_REGIME_PCT) / 0.10)
            factors.append(f)
            msg = f"Régime {regime} sur-exposé: {regime_pct:.0%}"
            warnings.append(msg)
            packet.add_reasoning(
                actor,
                msg,
                confidence_impact=-5.0,
                category=ReasoningCategory.PORTFOLIO_EXPOSURE,
                severity=ReasoningSeverity.WARNING,
            )

        # ── 4. Corrélation ────────────────────────────────────────────────
        corr_risk = self._correlation_risk(symbol, open_positions)
        packet.features["pb_corr_risk"] = round(corr_risk, 4)
        if corr_risk > self.MAX_CORRELATION_RISK:
            f = max(0.4, 1.0 - (corr_risk - self.MAX_CORRELATION_RISK) / 0.25)
            factors.append(f)
            msg = f"Corrélation portefeuille élevée: {corr_risk:.2f}"
            warnings.append(msg)
            packet.add_reasoning(
                actor,
                msg,
                confidence_impact=-8.0,
                category=ReasoningCategory.PORTFOLIO_CORRELATION,
                severity=ReasoningSeverity.WARNING,
            )
        else:
            packet.add_reasoning(
                actor,
                f"Corrélation OK: {corr_risk:.2f}",
                confidence_impact=1.0,
                category=ReasoningCategory.PORTFOLIO_CORRELATION,
            )

        # ── 5. Levier agrégé ──────────────────────────────────────────────
        new_lev = self._weighted_leverage(open_positions, size_usd, 1)
        packet.features["pb_leverage_weighted"] = round(new_lev, 3)
        if new_lev > self.MAX_LEVERAGE_WEIGHTED:
            f = max(0.3, self.MAX_LEVERAGE_WEIGHTED / new_lev)
            factors.append(f)
            msg = f"Levier agrégé ×{new_lev:.1f} > seuil ×{self.MAX_LEVERAGE_WEIGHTED}"
            warnings.append(msg)
            packet.add_reasoning(
                actor,
                msg,
                confidence_impact=-6.0,
                category=ReasoningCategory.PORTFOLIO_EXPOSURE,
                severity=ReasoningSeverity.WARNING,
            )

        # ── 6. Nombre de positions ────────────────────────────────────────
        if snap.n_positions >= self.MAX_POSITIONS:
            reason = f"Max positions atteint: {snap.n_positions}/{self.MAX_POSITIONS}"
            packet.add_reasoning(
                actor,
                reason,
                confidence_impact=-30.0,
                category=ReasoningCategory.PORTFOLIO_RISK_BUDGET,
                severity=ReasoningSeverity.CRITICAL,
            )
            packet.reject(actor, reason)
            return PortfolioVerdict(
                allowed=False,
                reason=reason,
                size_factor=0.0,
                capital_available=0.0,
                warnings=warnings,
                metrics=snap.__dict__,
            )

        # ── 7. Position opposée sur même symbole ─────────────────────────────
        opp_side = "short" if is_long else "long"
        for p in open_positions:
            if (
                getattr(p, "symbol", None) == symbol
                and getattr(p, "side", None) is not None
                and p.side.value == opp_side
            ):
                reason = f"Position {opp_side.upper()} existante sur {symbol} — hedge interdit"
                packet.add_reasoning(
                    actor,
                    reason,
                    confidence_impact=-50.0,
                    category=ReasoningCategory.PORTFOLIO_RISK_BUDGET,
                    severity=ReasoningSeverity.CRITICAL,
                )
                packet.reject(actor, reason)
                return PortfolioVerdict(
                    allowed=False,
                    reason=reason,
                    size_factor=0.0,
                    capital_available=0.0,
                    warnings=warnings,
                    metrics=snap.__dict__,
                )

        # ── 8. Direction dominante ────────────────────────────────────────
        longs = sum(
            1
            for p in open_positions
            if getattr(p, "side", None) and p.side.value == "long"
        )
        shorts = sum(
            1
            for p in open_positions
            if getattr(p, "side", None) and p.side.value == "short"
        )
        if is_long and longs >= self.MAX_SAME_DIRECTION:
            f = 0.5
            factors.append(f)
            msg = f"Direction LONG sur-représentée: {longs} positions"
            warnings.append(msg)
            packet.add_reasoning(
                actor,
                msg,
                confidence_impact=-4.0,
                category=ReasoningCategory.PORTFOLIO_RISK_BUDGET,
                severity=ReasoningSeverity.WARNING,
            )
        elif not is_long and shorts >= self.MAX_SAME_DIRECTION:
            f = 0.5
            factors.append(f)
            msg = f"Direction SHORT sur-représentée: {shorts} positions"
            warnings.append(msg)
            packet.add_reasoning(
                actor,
                msg,
                confidence_impact=-4.0,
                category=ReasoningCategory.PORTFOLIO_RISK_BUDGET,
                severity=ReasoningSeverity.WARNING,
            )

        # ── 9. Fragmentation ──────────────────────────────────────────────
        if size_usd < self.MIN_FRAGMENTATION_USD:
            reason = f"Taille ${size_usd:.0f} trop petite (min ${self.MIN_FRAGMENTATION_USD:.0f})"
            packet.add_reasoning(
                actor,
                reason,
                confidence_impact=-20.0,
                category=ReasoningCategory.PORTFOLIO_RISK_BUDGET,
                severity=ReasoningSeverity.WARNING,
            )
            packet.reject(actor, reason)
            return PortfolioVerdict(
                allowed=False,
                reason=reason,
                size_factor=0.0,
                capital_available=0.0,
                warnings=warnings,
                metrics=snap.__dict__,
            )

        # ── Facteur final ─────────────────────────────────────────────────
        final_factor = min(factors) if factors else 1.0
        if conviction_score >= 80 and not factors:
            final_factor = min(1.2, final_factor * 1.1)

        capital_avail = max(
            0.0, self._capital * self.MAX_TOTAL_EXPOSURE_PCT - snap.total_exposure_usd
        )

        packet.features["pb_size_factor"] = round(final_factor, 3)
        packet.features["pb_capital_available"] = round(capital_avail, 2)
        packet.metadata["pb_warnings"] = warnings

        if warnings:
            _log.info(
                "[PortfolioBrain] %s | warnings: %s | factor=%.2f",
                symbol,
                " | ".join(warnings),
                final_factor,
            )

        packet.transition_to(
            DecisionState.APPROVED,
            actor,
            f"Portfolio OK — factor={final_factor:.2f}"
            + (f" | {warnings[0]}" if warnings else ""),
        )

        return PortfolioVerdict(
            allowed=True,
            reason="OK" if not warnings else " | ".join(warnings[:2]),
            size_factor=round(final_factor, 3),
            capital_available=round(capital_avail, 2),
            warnings=warnings,
            metrics={
                "total_exposure_pct": round(snap.total_exposure_pct, 3),
                "n_positions": snap.n_positions,
                "corr_risk": round(corr_risk, 3),
                "leverage_weighted": round(new_lev, 2),
                "open_pnl_usd": round(snap.open_pnl_usd, 2),
            },
        )

    # ── Classement opportunités ───────────────────────────────────────────────

    def rank_opportunities(
        self,
        candidates: list[
            dict
        ],  # [{"symbol": ..., "score": ..., "regime": ..., "conviction": ...}]
        open_positions: list,
    ) -> list[dict]:
        """
        Classe les opportunités par valeur attendue ajustée au portefeuille.
        Pénalise les actifs déjà surreprésentés.
        """
        snap = self._snapshot(open_positions)
        ranked = []
        for c in candidates:
            sym = c.get("symbol", "")
            score = float(c.get("score", 50))
            conv = float(c.get("conviction", 50))
            sym_pct = snap.by_symbol.get(sym, 0) / self._capital
            penalty = max(0.0, sym_pct / self.MAX_SINGLE_SYMBOL_PCT)
            adj_score = score * (1 - penalty * 0.5) * (conv / 100)
            ranked.append(
                {**c, "adj_score": round(adj_score, 2), "sym_pct": round(sym_pct, 3)}
            )
        return sorted(ranked, key=lambda x: x["adj_score"], reverse=True)

    def portfolio_health(self, open_positions: list) -> dict:
        snap = self._snapshot(open_positions)
        return {
            "total_exposure_pct": round(snap.total_exposure_pct * 100, 1),
            "n_positions": snap.n_positions,
            "open_pnl_usd": round(snap.open_pnl_usd, 2),
            "correlation_risk": round(snap.correlation_risk * 100, 1),
            "leverage_weighted": round(snap.leverage_weighted, 2),
            "by_symbol": {k: round(v, 2) for k, v in snap.by_symbol.items()},
            "by_regime": {k: round(v, 2) for k, v in snap.by_regime.items()},
            "capital": round(self._capital, 2),
            "free_capital": round(
                max(
                    0,
                    self._capital * self.MAX_TOTAL_EXPOSURE_PCT
                    - snap.total_exposure_usd,
                ),
                2,
            ),
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _snapshot(self, positions: list) -> PortfolioSnapshot:
        snap = PortfolioSnapshot()
        for p in positions:
            if getattr(p, "closed", False):
                continue
            size = getattr(p, "size_usd", 0.0)
            sym = getattr(p, "symbol", "?")
            rgm = getattr(p, "regime", "unknown")
            pnl = getattr(p, "pnl_usd", 0.0)
            snap.total_exposure_usd += size
            snap.n_positions += 1
            snap.by_symbol[sym] = snap.by_symbol.get(sym, 0) + size
            snap.by_regime[rgm] = snap.by_regime.get(rgm, 0) + size
            snap.open_pnl_usd += pnl
        snap.total_exposure_pct = (
            snap.total_exposure_usd / self._capital if self._capital else 0
        )
        snap.correlation_risk = self._portfolio_correlation_risk(positions)
        snap.leverage_weighted = self._weighted_leverage(positions)
        return snap

    def _correlation_risk(self, new_symbol: str, positions: list) -> float:
        """Risque de corrélation entre le nouveau trade et les positions existantes."""
        if not positions:
            return 0.0
        corr_sum = 0.0
        for p in positions:
            sym = getattr(p, "symbol", "?")
            corr = self._corr_matrix.get(
                (sym, new_symbol), self._corr_matrix.get((new_symbol, sym), 0.5)
            )
            size = getattr(p, "size_usd", 0)
            corr_sum += corr * size
        total = sum(getattr(p, "size_usd", 0) for p in positions)
        return corr_sum / total if total else 0.0

    def _portfolio_correlation_risk(self, positions: list) -> float:
        if len(positions) < 2:
            return 0.0
        pairs = [
            (positions[i], positions[j])
            for i in range(len(positions))
            for j in range(i + 1, len(positions))
        ]
        if not pairs:
            return 0.0
        risks = []
        for a, b in pairs:
            sym_a = getattr(a, "symbol", "")
            sym_b = getattr(b, "symbol", "")
            corr = self._corr_matrix.get(
                (sym_a, sym_b), self._corr_matrix.get((sym_b, sym_a), 0.5)
            )
            risks.append(corr)
        return sum(risks) / len(risks)

    @staticmethod
    def _weighted_leverage(
        positions: list, new_size: float = 0, new_lev: int = 1
    ) -> float:
        total_notional = sum(
            getattr(p, "size_usd", 0) * getattr(p, "leverage", 1)
            for p in positions
            if not getattr(p, "closed", False)
        )
        total_notional += new_size * new_lev
        total_size = sum(
            getattr(p, "size_usd", 0)
            for p in positions
            if not getattr(p, "closed", False)
        )
        total_size += new_size
        return total_notional / total_size if total_size else 1.0
