"""
order_sizer.py — Taille de position optimale (Kelly + volatilité) (Phase 7).

Formule Kelly modifiée :
    f = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
    size = capital * f * kelly_fraction * volatility_factor

Sécurités :
  - Fraction Kelly plafonnée à kelly_fraction (défaut 0.25 = quart Kelly)
  - Facteur de volatilité : réduit la taille quand σ est élevée
  - Taille minimale et maximale absolues (en USD)
  - Intégration DrawdownGuard : réduit si drawdown en cours

Migration DecisionPacket :
  - OrderSizer.size_packet() — API souveraine sur DecisionPacket.
    Produit la transition APPROVED → EXECUTION_PENDING.
    Lit conviction_size_factor et pb_size_factor en advisory.
    Écrit allocation_pct, os_kelly, os_vol_factor, os_dd_factor, os_size_usd.
  - compute() / compute_from_signal() préservées pour compatibilité.
"""

from __future__ import annotations

from dataclasses import dataclass

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.risk.order_sizer")
_DEFAULT_KELLY_FRACTION = 0.25  # quart-Kelly par défaut (sécuritaire)
_DEFAULT_MIN_SIZE_USD = 10.0
_DEFAULT_MAX_SIZE_USD = 5_000.0


@dataclass
class SizeResult:
    """Résultat du calcul de taille de position."""

    size_usd: float
    size_base: float  # en unité de base (ex: BTC)
    kelly_fraction: float  # fraction Kelly brute avant plafonnement
    volatility_factor: float
    drawdown_factor: float
    final_fraction: float  # fraction finale du capital allouée
    capped: bool  # True si la taille a été plafonnée
    notes: list[str]

    def as_dict(self) -> dict:
        return {
            "size_usd": round(self.size_usd, 2),
            "size_base": round(self.size_base, 6),
            "kelly_fraction": round(self.kelly_fraction, 4),
            "volatility_factor": round(self.volatility_factor, 4),
            "drawdown_factor": round(self.drawdown_factor, 4),
            "final_fraction": round(self.final_fraction, 4),
            "capped": self.capped,
            "notes": self.notes,
        }


class OrderSizer:
    """
    Calcule la taille optimale d'un ordre selon Kelly + ajustements.

    Usage:
        sizer = OrderSizer()
        result = sizer.compute(
            capital=10_000.0,
            win_rate=0.6,
            avg_win_pct=3.0,
            avg_loss_pct=2.0,
            realized_volatility=0.05,
            current_drawdown=0.03,
            price=50_000.0,
        )
        print(f"Taille recommandée : ${result.size_usd:.2f}")
    """

    def __init__(
        self,
        kelly_fraction: float = _DEFAULT_KELLY_FRACTION,
        min_size_usd: float = _DEFAULT_MIN_SIZE_USD,
        max_size_usd: float = _DEFAULT_MAX_SIZE_USD,
        vol_target: float = 0.02,  # volatilité cible journalière (2%)
        drawdown_guard=None,
    ) -> None:
        self.kelly_fraction = max(0.01, min(1.0, kelly_fraction))
        self.min_size_usd = max(0.0, min_size_usd)
        self.max_size_usd = max(self.min_size_usd, max_size_usd)
        self.vol_target = vol_target
        self._drawdown_guard = drawdown_guard

    # ── API principale ─────────────────────────────────────────────────────────

    def compute(
        self,
        capital: float,
        win_rate: float,
        avg_win_pct: float,
        avg_loss_pct: float,
        realized_volatility: float = 0.02,
        current_drawdown: float = 0.0,
        price: float = 1.0,
        signal_score: int = 70,
    ) -> SizeResult:
        """
        Calcule la taille de position optimale.

        Args:
            capital             : capital total disponible en USD
            win_rate            : taux de réussite historique (0-1)
            avg_win_pct         : gain moyen par trade gagnant (%)
            avg_loss_pct        : perte moyenne par trade perdant (%) — positif
            realized_volatility : volatilité réalisée (ex: 0.05 = 5% par jour)
            current_drawdown    : drawdown courant du portefeuille (0-1)
            price               : prix courant de l'actif en USD
            signal_score        : score du signal (0-100) — bonus si très fort

        Returns:
            SizeResult avec taille en USD et en unités de base
        """
        notes: list[str] = []
        capped = False

        # ① Kelly brut
        kelly_raw = self._kelly(win_rate, avg_win_pct, avg_loss_pct)
        kelly_applied = kelly_raw * self.kelly_fraction
        notes.append(
            f"Kelly brut={kelly_raw:.3f} × {self.kelly_fraction} = {kelly_applied:.3f}"
        )

        # ② Facteur volatilité (réduit si vol > cible)
        vol_factor = self._volatility_factor(realized_volatility)
        notes.append(
            f"Vol factor={vol_factor:.3f} (vol={realized_volatility:.3f}, cible={self.vol_target})"
        )

        # ③ Facteur drawdown
        dd_factor = self._drawdown_factor(current_drawdown)
        notes.append(f"DD factor={dd_factor:.3f} (dd={current_drawdown:.3f})")

        # ④ Bonus signal fort (jusqu'à +10%)
        score_bonus = 1.0 + max(0.0, (signal_score - 70)) / 300
        notes.append(f"Score bonus={score_bonus:.3f} (score={signal_score})")

        # ⑤ Fraction finale
        final_fraction = kelly_applied * vol_factor * dd_factor * score_bonus
        final_fraction = max(0.0, min(1.0, final_fraction))

        # ⑥ Taille en USD
        size_usd = capital * final_fraction

        # ⑦ Plafonnement
        if size_usd < self.min_size_usd and size_usd > 0:
            size_usd = self.min_size_usd
            capped = True
            notes.append(f"Plafonné au minimum {self.min_size_usd} USD")
        elif size_usd > self.max_size_usd:
            size_usd = self.max_size_usd
            capped = True
            notes.append(f"Plafonné au maximum {self.max_size_usd} USD")

        # ⑧ Taille en unité de base
        size_base = size_usd / price if price > 0 else 0.0

        _log.info(
            "[OrderSizer] capital=%.0f win_rate=%.1f%% → size=$%.2f (%.2f%%  capital) capped=%s",
            capital,
            win_rate * 100,
            size_usd,
            final_fraction * 100,
            capped,
        )

        return SizeResult(
            size_usd=round(size_usd, 2),
            size_base=round(size_base, 8),
            kelly_fraction=round(kelly_raw, 4),
            volatility_factor=round(vol_factor, 4),
            drawdown_factor=round(dd_factor, 4),
            final_fraction=round(final_fraction, 4),
            capped=capped,
            notes=notes,
        )

    def compute_from_signal(
        self,
        signal_result,
        capital: float,
        win_rate: float = 0.55,
        avg_win_pct: float = 2.0,
        avg_loss_pct: float = 1.5,
        features: dict | None = None,
        current_drawdown: float = 0.0,
        price: float = 1.0,
    ) -> SizeResult:
        """
        Raccourci : calcule directement depuis un SignalResult.
        Extrait la volatilité réalisée depuis features si disponible.
        """
        vol = 0.02
        if features:
            vol = float(features.get("realized_volatility", 0.02))
        score = getattr(signal_result, "score", 70)
        return self.compute(
            capital=capital,
            win_rate=win_rate,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            realized_volatility=vol,
            current_drawdown=current_drawdown,
            price=price,
            signal_score=score,
        )

    # ── API DecisionPacket ────────────────────────────────────────────────────

    def size_packet(
        self,
        packet,
        capital: float,
        win_rate: float = 0.55,
        avg_win_pct: float = 2.0,
        avg_loss_pct: float = 1.5,
        current_drawdown: float = 0.0,
        price: float = 1.0,
    ) -> "SizeResult":
        """
        Calcule la taille et produit la transition APPROVED → EXECUTION_PENDING.

        Lit en advisory depuis le packet :
          - metadata["conviction_size_factor"]  → multiplicateur conviction
          - metadata["pb_size_factor"]           → multiplicateur portefeuille
          - features["realized_volatility"]      → volatilité réalisée
          - confidence                            → signal_score proxy

        Écrit dans le packet :
          - allocation_pct                (fraction du capital allouée)
          - features["os_kelly"]          (fraction Kelly brute)
          - features["os_vol_factor"]     (facteur volatilité)
          - features["os_dd_factor"]      (facteur drawdown)
          - features["os_size_usd"]       (taille finale en USD)
        """
        from core.decision_packet import (
            DecisionState,
            ReasoningCategory,
            ReasoningSeverity,
        )

        actor = "order_sizer"
        packet.add_agent(actor)

        # Inputs advisory
        vol = float(
            packet.features.get(
                "realized_volatility", packet.features.get("atr_ratio", 0.02)
            )
        )
        conv_factor = float(packet.metadata.get("conviction_size_factor", 1.0))
        pb_factor = float(packet.metadata.get("pb_size_factor", 1.0))
        signal_score = int(packet.confidence)

        result = self.compute(
            capital=capital,
            win_rate=win_rate,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            realized_volatility=vol,
            current_drawdown=current_drawdown,
            price=price,
            signal_score=signal_score,
        )

        # Appliquer les facteurs advisory
        final_size = result.size_usd * conv_factor * pb_factor
        final_size = max(self.min_size_usd, min(self.max_size_usd, final_size))
        allocation_pct = final_size / capital if capital > 0 else 0.0

        # Écriture packet
        packet.allocation_pct = round(allocation_pct, 6)
        packet.features["os_kelly"] = result.kelly_fraction
        packet.features["os_vol_factor"] = result.volatility_factor
        packet.features["os_dd_factor"] = result.drawdown_factor
        packet.features["os_size_usd"] = round(final_size, 2)

        # Reasoning
        packet.add_reasoning(
            actor,
            f"Kelly={result.kelly_fraction:.3f} × vol={result.volatility_factor:.2f}"
            f" × dd={result.drawdown_factor:.2f} → base=${result.size_usd:.2f}",
            confidence_impact=0.0,
            category=ReasoningCategory.SIZING,
        )
        if conv_factor != 1.0 or pb_factor != 1.0:
            sev = (
                ReasoningSeverity.WARNING
                if (conv_factor < 0.5 or pb_factor < 0.5)
                else ReasoningSeverity.INFO
            )
            packet.add_reasoning(
                actor,
                f"Facteurs advisory : conviction×{conv_factor:.2f} portfolio×{pb_factor:.2f}"
                f" → final ${final_size:.2f} ({allocation_pct:.1%} capital)",
                confidence_impact=0.0,
                category=ReasoningCategory.SIZING,
                severity=sev,
            )
        else:
            packet.add_reasoning(
                actor,
                f"Taille finale ${final_size:.2f} ({allocation_pct:.1%} capital)",
                confidence_impact=0.0,
                category=ReasoningCategory.SIZING,
            )

        if result.capped:
            packet.add_reasoning(
                actor,
                f"Taille plafonnée : {result.notes[-1]}",
                confidence_impact=0.0,
                category=ReasoningCategory.SIZING,
                severity=ReasoningSeverity.WARNING,
            )

        packet.transition_to(
            DecisionState.EXECUTION_PENDING,
            actor,
            f"Sizing: ${final_size:.2f} ({allocation_pct:.1%} capital)"
            + (" [capped]" if result.capped else ""),
        )

        return result

    # ── Calculs internes ──────────────────────────────────────────────────────

    @staticmethod
    def _kelly(win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> float:
        """Critère de Kelly : f = (p*b - q) / b avec b = avg_win/avg_loss."""
        win_rate = max(0.0, min(1.0, win_rate))
        avg_win_pct = max(0.001, avg_win_pct)
        avg_loss_pct = max(0.001, avg_loss_pct)
        b = avg_win_pct / avg_loss_pct
        q = 1.0 - win_rate
        kelly = (win_rate * b - q) / b
        return max(0.0, kelly)  # Kelly négatif → ne pas trader

    def _volatility_factor(self, realized_vol: float) -> float:
        """Réduit la taille proportionnellement quand vol > cible."""
        if realized_vol <= 0 or self.vol_target <= 0:
            return 1.0
        raw = self.vol_target / max(realized_vol, self.vol_target * 0.1)
        return round(min(1.0, raw), 4)

    def _drawdown_factor(self, current_drawdown: float) -> float:
        """Réduit la taille si drawdown en cours ; utilise DrawdownGuard si dispo."""
        if self._drawdown_guard is not None:
            return self._drawdown_guard.adjust_position_size(
                current_drawdown, base_size=1.0
            )
        if current_drawdown <= 0:
            return 1.0
        factor = max(0.1, 1.0 - current_drawdown * 2.5)
        return round(factor, 4)
