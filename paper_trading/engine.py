"""
paper_trading/engine.py — Moteur de simulation burn-in avec friction réaliste.

BurninSimulationEngine reçoit les signaux de l'advisor et :
  1. Simule le fill entry via ExecutionSimulator (slippage + latence + fees)
  2. Ouvre un PaperTrade dans le ledger
  3. À la clôture : simule le fill exit et calcule le P&L net
  4. Logge chaque trade en JSONL pour audit

Scope : infrastructure d'observation burn-in (P5). Ne pas confondre avec
PaperTradingEngine de quant_hedge_ai/agents/execution/ qui est le moteur
paper mode du runtime live.

Fidélité cible : 95%+ vs exécution réelle (grâce au simulateur calibré MEXC).

Usage :
    from paper_trading.engine import BurninSimulationEngine
    from execution_simulator.config import mexc_futures_simulator

    engine = BurninSimulationEngine(
        simulator=mexc_futures_simulator(),
        initial_capital=10_000.0,
        log_path="logs/paper_trading.jsonl",
    )
    # Sur signal advisor :
    engine.on_signal("BTCUSDT", "buy", price=65_000.0, size_usd=500.0, regime="bull")
    # Sur signal de sortie :
    engine.on_signal("BTCUSDT", "sell", price=66_000.0, size_usd=500.0)
    # Rapport :
    print(engine.report())
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional

from execution_simulator.models import MarketSnapshot, OrderIntent
from execution_simulator.simulator import ExecutionSimulator
from paper_trading.ledger import PaperLedger, PaperTrade


class BurninSimulationEngine:
    """
    Moteur de simulation burn-in avec friction d'exécution réaliste.

    Réservé à l'infrastructure d'observation P5. Runtime live → voir
    quant_hedge_ai/agents/execution/paper_trading_engine.py.

    simulator       : ExecutionSimulator calibré (ex: mexc_futures_simulator())
    initial_capital : capital de départ en USD
    log_path        : chemin vers le fichier JSONL d'audit (None = pas de log)
    volume_24h      : volume journalier estimé pour le simulateur (USD)
    volatility_pct  : volatilité journalière estimée (%)
    """

    def __init__(
        self,
        simulator: ExecutionSimulator,
        initial_capital: float = 10_000.0,
        log_path: Optional[str] = "logs/paper_trading.jsonl",
        volume_24h: float = 1_000_000_000.0,
        volatility_pct: float = 2.0,
    ) -> None:
        self._sim = simulator
        self._ledger = PaperLedger(initial_capital=initial_capital)
        self._log_path = Path(log_path) if log_path else None
        self._volume_24h = volume_24h
        self._volatility_pct = volatility_pct

        if self._log_path:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # API principale
    # ------------------------------------------------------------------

    def on_signal(
        self,
        symbol: str,
        side: str,
        price: float,
        size_usd: float,
        regime: str = "unknown",
        strategy_id: str = "",
        exit_reason: str = "signal",
        volume_24h: Optional[float] = None,
        volatility_pct: Optional[float] = None,
    ) -> Optional[PaperTrade]:
        """
        Traite un signal advisor.

        Si une position est déjà ouverte sur le symbole dans la direction opposée
        (ou même direction pour sortie), ferme d'abord la position existante,
        puis ouvre une nouvelle si le signal est une entrée.

        Retourne le PaperTrade créé ou fermé (None si rien à faire).
        """
        sym_clean = symbol.replace("/", "")
        existing = self._ledger.get_open(sym_clean)

        # Clôture si position ouverte dans direction opposée ou signal de sortie
        closed = None
        if existing is not None:
            opposite = (existing.side == "buy" and side == "sell") or (
                existing.side == "sell" and side == "buy"
            )
            if opposite or side in ("close", "exit"):
                closed = self._close_position(
                    sym_clean,
                    price,
                    exit_reason,
                    volume_24h or self._volume_24h,
                    volatility_pct or self._volatility_pct,
                )
                self._log(closed)
                if side in ("close", "exit"):
                    return closed

        # Ouvre nouvelle position si entrée
        if side in ("buy", "sell"):
            trade = self._open_position(
                sym_clean,
                side,
                price,
                size_usd,
                regime,
                strategy_id,
                volume_24h or self._volume_24h,
                volatility_pct or self._volatility_pct,
            )
            self._log(trade)
            return trade

        return closed

    def close_all(
        self, prices: dict[str, float], reason: str = "manual"
    ) -> list[PaperTrade]:
        """Ferme toutes les positions ouvertes aux prix donnés."""
        closed = []
        for trade in self._ledger.open_trades:
            price = prices.get(trade.symbol, 0.0)
            if price > 0:
                t = self._close_position(trade.symbol, price, reason)
                if t:
                    self._log(t)
                    closed.append(t)
        return closed

    def report(self) -> dict:
        """Rapport complet : summary + liste des trades fermés."""
        summary = self._ledger.summary()
        closed = [t.as_dict() for t in self._ledger.closed_trades]
        open_ = [t.as_dict() for t in self._ledger.open_trades]
        return {
            "summary": summary,
            "open_trades": open_,
            "closed_trades": closed[-50:],  # 50 derniers
        }

    @property
    def ledger(self) -> PaperLedger:
        return self._ledger

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _make_snapshot(
        self, symbol: str, price: float, volume_24h: float, volatility_pct: float
    ) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            price=price,
            volume_24h=volume_24h / price,  # convertir USD → base asset
            volatility_pct=volatility_pct,
            timestamp=time.time(),
        )

    def _open_position(
        self,
        symbol: str,
        side: str,
        price: float,
        size_usd: float,
        regime: str,
        strategy_id: str,
        volume_24h: float,
        volatility_pct: float,
    ) -> PaperTrade:
        qty = max(0.001, size_usd / price)
        intent = OrderIntent(
            symbol=symbol,
            side=side,
            size=qty,
            order_type="market",
            signal_price=price,
            timestamp=time.time(),
            strategy_id=strategy_id,
        )
        snapshot = self._make_snapshot(symbol, price, volume_24h, volatility_pct)
        fill = self._sim.execute(intent, snapshot)

        entry_price = fill.fill_price if not fill.is_rejected else price
        trade = PaperTrade(
            trade_id=str(uuid.uuid4())[:8],
            symbol=symbol,
            side=side,
            size_usd=size_usd,
            signal_price=price,
            entry_price=entry_price,
            entry_slippage_bps=fill.slippage_bps if not fill.is_rejected else 0.0,
            entry_latency_ms=fill.latency_ms if not fill.is_rejected else 0.0,
            entry_fee_usd=fill.fee_usd if not fill.is_rejected else 0.0,
            entry_ts=time.time(),
            regime=regime,
            strategy_id=strategy_id,
            is_open=True,
        )
        self._ledger.open_trade(trade)
        return trade

    def _close_position(
        self,
        symbol: str,
        price: float,
        reason: str,
        volume_24h: Optional[float] = None,
        volatility_pct: Optional[float] = None,
    ) -> Optional[PaperTrade]:
        existing = self._ledger.get_open(symbol)
        if existing is None:
            return None

        exit_side = "sell" if existing.side == "buy" else "buy"
        qty = max(0.001, existing.size_usd / price)
        intent = OrderIntent(
            symbol=symbol,
            side=exit_side,
            size=qty,
            order_type="market",
            signal_price=price,
            timestamp=time.time(),
        )
        vol = volume_24h or self._volume_24h
        vola = volatility_pct or self._volatility_pct
        snapshot = self._make_snapshot(symbol, price, vol, vola)
        fill = self._sim.execute(intent, snapshot)

        exit_price = fill.fill_price if not fill.is_rejected else price
        return self._ledger.close_trade(
            symbol=symbol,
            exit_price=exit_price,
            exit_slippage_bps=fill.slippage_bps if not fill.is_rejected else 0.0,
            exit_latency_ms=fill.latency_ms if not fill.is_rejected else 0.0,
            exit_fee_usd=fill.fee_usd if not fill.is_rejected else 0.0,
            exit_reason=reason,
        )

    def _log(self, trade: Optional[PaperTrade]) -> None:
        if trade is None or self._log_path is None:
            return
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(trade.as_dict()) + "\n")
        except Exception:
            pass
