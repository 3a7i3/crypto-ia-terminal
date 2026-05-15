"""
exchange_constraints/order_validator.py — Validation d'ordre exchange-aware.

OrderValidator compose tous les filtres Binance et retourne un ValidationResult.

Pipeline de validation selon l'ordre type :

  MARKET orders :
    1. Symbole actif
    2. Qty > 0 et <= market_max_qty
    3. MARKET_LOT_SIZE (arrondi + check min_qty market)
    4. MIN_NOTIONAL (a partir du prix de reference fourni)
    5. Warnings si ajustement > SIGNIFICANT_ADJUSTMENT_PCT

  LIMIT orders :
    1. Symbole actif
    2. Qty > 0 et <= max_qty
    3. Prix > 0
    4. LOT_SIZE (arrondi + check min_qty)
    5. PRICE_FILTER (arrondi tick_size)
    6. PERCENT_PRICE (si mark_price fourni — erreur si hors bornes)
    7. MIN_NOTIONAL (augmente qty si necessaire)
    8. Re-appliquer LOT_SIZE apres ajustement notional
    9. Check max_qty final
    10. Warnings si ajustements significatifs

validate(info, qty, price, order_type, mark_price) -> ValidationResult
"""

from __future__ import annotations

from typing import Optional

from exchange_constraints.models import SymbolInfo, ValidationResult
from exchange_constraints.precision_rules import (
    apply_lot_size,
    apply_min_notional,
    apply_price_filter,
    check_percent_price,
)

# Seuil a partir duquel un ajustement de taille est signale en warning (%)
_SIGNIFICANT_ADJUSTMENT_PCT = 1.0


class OrderValidator:
    """
    Valide et ajuste un ordre selon les contraintes du symbole.

    validate(info, qty, price, order_type, mark_price) -> ValidationResult
    """

    def validate(
        self,
        info: SymbolInfo,
        qty: float,
        price: float,
        order_type: str = "market",
        mark_price: Optional[float] = None,
    ) -> ValidationResult:
        """
        Parameters
        ----------
        info       : regles du symbole (SymbolInfo)
        qty        : quantite demandee (base asset)
        price      : prix de l'ordre (0 pour market orders sans prix cible)
        order_type : "market" | "limit"
        mark_price : prix mark courant (requis pour PERCENT_PRICE, optionnel sinon)
        """
        if order_type not in ("market", "limit"):
            return ValidationResult.reject(
                info.symbol,
                f"unknown_order_type '{order_type}'",
                original_size=qty,
                original_price=price,
                order_type=order_type,
            )

        if order_type == "market":
            return self._validate_market(info, qty, price, order_type)
        return self._validate_limit(info, qty, price, order_type, mark_price)

    # ------------------------------------------------------------------
    # Market order pipeline
    # ------------------------------------------------------------------

    def _validate_market(
        self,
        info: SymbolInfo,
        qty: float,
        ref_price: float,
        order_type: str,
    ) -> ValidationResult:
        original_qty = qty
        warnings: list[str] = []

        # 1. Symbole actif
        if not info.is_active:
            return ValidationResult.reject(
                info.symbol,
                "symbol_not_active",
                original_size=qty,
                original_price=ref_price,
                order_type=order_type,
            )

        # 2. Qty positive + max brut
        if qty <= 0:
            return ValidationResult.reject(
                info.symbol,
                f"qty_must_be_positive ({qty})",
                original_size=qty,
                original_price=ref_price,
                order_type=order_type,
            )
        if qty > info.effective_market_max_qty:
            return ValidationResult.reject(
                info.symbol,
                f"qty_exceeds_market_max ({qty} > {info.effective_market_max_qty})",
                original_size=qty,
                original_price=ref_price,
                order_type=order_type,
            )

        # 3. MARKET_LOT_SIZE
        adjusted_qty = apply_lot_size(qty, info, is_market=True)
        if adjusted_qty < info.effective_market_min_qty:
            return ValidationResult.reject(
                info.symbol,
                f"qty_below_market_min_after_rounding ({adjusted_qty} < {info.effective_market_min_qty})",
                original_size=original_qty,
                original_price=ref_price,
                order_type=order_type,
            )

        # 4. MIN_NOTIONAL (si prix de reference disponible)
        if ref_price is not None and ref_price > 0:
            adjusted_qty = apply_min_notional(adjusted_qty, ref_price, info)
            adjusted_qty = apply_lot_size(adjusted_qty, info, is_market=True)

        # 5. Warning si ajustement significatif
        if original_qty > 0:
            adj_pct = abs(adjusted_qty - original_qty) / original_qty * 100.0
            if adj_pct > _SIGNIFICANT_ADJUSTMENT_PCT:
                warnings.append(
                    f"size_adjusted_by_{adj_pct:.1f}pct "
                    f"({original_qty} -> {adjusted_qty})"
                )

        return ValidationResult.accept(
            symbol=info.symbol,
            original_size=original_qty,
            original_price=ref_price,
            adjusted_size=adjusted_qty,
            adjusted_price=ref_price,
            order_type=order_type,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Limit order pipeline
    # ------------------------------------------------------------------

    def _validate_limit(
        self,
        info: SymbolInfo,
        qty: float,
        price: float,
        order_type: str,
        mark_price: Optional[float],
    ) -> ValidationResult:
        original_qty = qty
        original_price = price
        warnings: list[str] = []

        # 1. Symbole actif
        if not info.is_active:
            return ValidationResult.reject(
                info.symbol,
                "symbol_not_active",
                original_size=qty,
                original_price=price,
                order_type=order_type,
            )

        # 2. Qty positive + max brut
        if qty <= 0:
            return ValidationResult.reject(
                info.symbol,
                f"qty_must_be_positive ({qty})",
                original_size=qty,
                original_price=price,
                order_type=order_type,
            )
        if qty > info.max_qty:
            return ValidationResult.reject(
                info.symbol,
                f"qty_exceeds_max ({qty} > {info.max_qty})",
                original_size=qty,
                original_price=price,
                order_type=order_type,
            )

        # 3. Prix requis pour un limit order
        if price <= 0:
            return ValidationResult.reject(
                info.symbol,
                "limit_order_requires_positive_price",
                original_size=qty,
                original_price=price,
                order_type=order_type,
            )

        # 4. LOT_SIZE
        adjusted_qty = apply_lot_size(qty, info, is_market=False)
        if adjusted_qty < info.min_qty:
            return ValidationResult.reject(
                info.symbol,
                f"qty_below_min_after_rounding ({adjusted_qty} < {info.min_qty})",
                original_size=original_qty,
                original_price=price,
                order_type=order_type,
            )

        # 5. PRICE_FILTER (tick_size)
        adjusted_price = apply_price_filter(price, info)
        if abs(adjusted_price - price) > info.tick_size * 0.5:
            warnings.append(
                f"price_rounded ({price} -> {adjusted_price}, tick={info.tick_size})"
            )

        # 6. PERCENT_PRICE (si mark_price disponible)
        if mark_price is not None and mark_price > 0:
            ok, reason = check_percent_price(adjusted_price, mark_price, info)
            if not ok:
                return ValidationResult.reject(
                    info.symbol,
                    reason,
                    original_size=original_qty,
                    original_price=original_price,
                    order_type=order_type,
                )

        # 7. MIN_NOTIONAL
        adjusted_qty = apply_min_notional(adjusted_qty, adjusted_price, info)
        # 8. Re-appliquer LOT_SIZE apres ajustement notional
        adjusted_qty = apply_lot_size(adjusted_qty, info, is_market=False)

        # 9. Max qty apres tous les ajustements
        if adjusted_qty > info.max_qty:
            return ValidationResult.reject(
                info.symbol,
                f"qty_exceeds_max_after_notional_adjustment ({adjusted_qty} > {info.max_qty})",
                original_size=original_qty,
                original_price=original_price,
                order_type=order_type,
            )

        # 10. Verifier notional final
        notional = adjusted_qty * adjusted_price
        if notional < info.min_notional:
            return ValidationResult.reject(
                info.symbol,
                f"notional_below_min ({notional:.4f} < {info.min_notional})",
                original_size=original_qty,
                original_price=original_price,
                order_type=order_type,
            )

        # 11. Warning si ajustement de taille significatif
        if original_qty > 0:
            adj_pct = abs(adjusted_qty - original_qty) / original_qty * 100.0
            if adj_pct > _SIGNIFICANT_ADJUSTMENT_PCT:
                warnings.append(
                    f"size_adjusted_by_{adj_pct:.1f}pct "
                    f"({original_qty} -> {adjusted_qty})"
                )

        return ValidationResult.accept(
            symbol=info.symbol,
            original_size=original_qty,
            original_price=original_price,
            adjusted_size=adjusted_qty,
            adjusted_price=adjusted_price,
            order_type=order_type,
            warnings=warnings,
        )
