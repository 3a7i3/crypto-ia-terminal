from __future__ import annotations

import os
import time

from observability.json_logger import get_logger
from quant_hedge_ai.agents.execution.order_deduplicator import OrderDeduplicator
from quant_hedge_ai.agents.execution.trade_logger import TradeLogger
from quant_hedge_ai.agents.risk.session_guard import (
    OrderTooLargeError,
    SessionGuard,
    SessionHaltedError,
)
from supervision.alert_manager import Alert, AlertManager

_log = get_logger("quant_hedge_ai.agents.execution.execution_engine")
alert_manager = AlertManager()


def execution_autoheal(alert):
    return {"action": "force_size", "new_size": 1.0}


alert_manager.register_autoheal("execution", execution_autoheal)


class ExecutionEngine:
    """
    Moteur d'exécution multi-exchange (Gate.io, Bybit, OKX, MEXC, Binance…).

    Exchange actif : EXCHANGE_ID dans .env (défaut: binance)
    Modes détectés automatiquement par ExchangeFactory :
      testnet   — clés API + EXCHANGE_TESTNET=true
      live      — clés API + EXCHANGE_TESTNET=false
      paper     — aucune clé (simulation locale)

    Safety layer (toujours actif) :
      1. OrderDeduplicator  — bloque les ordres dupliqués (< 30 s)
      2. SessionGuard       — halt si drawdown / pertes consécutives dépassent les seuils
      3. TradeLogger        — log SQLite de tous les ordres (audit)
    """

    def __init__(self, live: bool = False, _sleep=time.sleep) -> None:
        self._size_factor: float = 1.0
        self._sleep = _sleep
        self._live = live
        self._position_manager = None
        self._exchange = None
        self._exchange_futures = None  # futures demo séparé
        self._mode = "paper"
        _exch_id = os.getenv("EXCHANGE_ID", "binance").lower()
        _futures_exchanges = {"krakenfutures", "binanceusdm"}
        self._quote_asset = "USD" if _exch_id in _futures_exchanges else "USDT"
        if live:
            self._exchange = self._init_exchange()
            self._exchange_futures = self._init_futures_demo()

        # Safety layer
        self._dedup = OrderDeduplicator(
            window_seconds=float(os.getenv("EXEC_DEDUP_WINDOW", "30"))
        )
        self._guard = SessionGuard(
            max_session_drawdown=float(os.getenv("EXEC_MAX_DD", "0.05")),
            max_session_loss=float(os.getenv("EXEC_MAX_LOSS", "0.03")),
            max_consecutive_losses=int(os.getenv("EXEC_MAX_CONSEC_LOSSES", "3")),
            max_order_size_usd=float(os.getenv("EXEC_MAX_ORDER_USD", "10000")),
        )
        self._logger = TradeLogger(
            db_path=os.getenv("EXEC_TRADE_LOG", "databases/trade_log.sqlite")
        )

    def _init_exchange(self):
        """Initialise le client Spot via ExchangeFactory (multi-exchange)."""
        try:
            from exchange_factory import ExchangeFactory, detect_mode

            exchange = ExchangeFactory.create()
            if exchange is None:
                _log.warning("[ExecutionEngine] ExchangeFactory échec — mode paper")
                self._live = False
                return None
            mode = detect_mode()
            self._mode = mode
            _log.info("[ExecutionEngine] Exchange initialisé — mode=%s", mode)
            return exchange
        except Exception as exc:
            _log.error("[ExecutionEngine] Init spot erreur: %s", exc)
            self._live = False
            return None

    def _init_futures_demo(self):
        """
        Initialise le client Futures Demo.
        - krakenfutures testnet : réutilise self._exchange (même exchange)
        - Binance futures demo  : BINANCE_FUTURES_DEMO_KEY requis (legacy)
        """
        exch_id = os.getenv("EXCHANGE_ID", "").lower()

        # krakenfutures testnet — même exchange que le principal
        if exch_id == "krakenfutures" and self._exchange is not None:
            _log.info(
                "[ExecutionEngine] Futures Demo = krakenfutures testnet (exchange partagé)"
            )
            return self._exchange

        # Binance futures demo (legacy)
        try:
            import ccxt

            key = os.getenv("BINANCE_FUTURES_DEMO_KEY", "")
            secret = os.getenv("BINANCE_FUTURES_DEMO_SECRET", "")
            if not key or not secret:
                _log.debug("[ExecutionEngine] Pas de clés futures demo — ignoré")
                return None
            ex = ccxt.binanceusdm(
                {
                    "apiKey": key,
                    "secret": secret,
                    "enableRateLimit": True,
                    "options": {"adjustForTimeDifference": True},
                }
            )
            ex.enable_demo_trading(True)
            bal = ex.fetch_balance()
            usdt = bal.get("total", {}).get("USDT", 0)
            _log.info(
                "[ExecutionEngine] Futures Demo Binance connecté — USDT: %.2f", usdt
            )
            return ex
        except Exception as exc:
            _log.warning("[ExecutionEngine] Futures demo non disponible: %s", exc)
            return None

    def reconnect(self) -> bool:
        """
        Ferme et recrée les clients CCXT spot et futures.
        Retourne True si au moins un client est actif après reconnexion.
        Appelé automatiquement par SelfHealingBot quand l'exchange est hors ligne.
        """
        t0 = time.time()
        _log.info("[ExecutionEngine] Reconnexion en cours...")
        was_live = self._live
        closed = set()
        for ex in (self._exchange, self._exchange_futures):
            if ex is not None and id(ex) not in closed:
                try:
                    ex.close()
                    closed.add(id(ex))
                except Exception as _exc:
                    _log.debug("[ExecutionEngine] close() ignoré: %s", _exc)
        self._exchange = None
        self._exchange_futures = None
        try:
            if was_live:
                self._exchange = self._init_exchange()
            self._exchange_futures = self._init_futures_demo()
            # _init_exchange met _live=False sur erreur — restaurer pour réessais futurs
            if was_live and self._exchange is None:
                self._live = True
            ok = self._exchange is not None or self._exchange_futures is not None
            elapsed = time.time() - t0
            if ok:
                _log.info("[ExecutionEngine] Reconnexion réussie en %.1fs", elapsed)
            else:
                _log.error(
                    "[ExecutionEngine] Reconnexion échouée — aucun client actif après %.1fs",
                    elapsed,
                )
            return ok
        except Exception as exc:
            self._live = was_live
            _log.error("[ExecutionEngine] Reconnexion exception: %s", exc)
            return False

    def _with_retry(self, fn, *args, **kwargs):
        """
        Exécute fn avec jusqu'à 3 essais (backoff 0.5s / 1s / 2s).
        Sur 3e échec, tente une reconnexion puis un dernier essai.
        Lève la dernière exception si tout échoue.
        """
        delays = (0.5, 1.0, 2.0)
        last_exc: Exception | None = None
        for i, delay in enumerate(delays):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                _log.warning(
                    "[ExecutionEngine] Retry %d/%d (pause %.1fs): %s",
                    i + 1,
                    len(delays),
                    delay,
                    exc,
                )
                self._sleep(delay)
        _log.warning(
            "[ExecutionEngine] 3 échecs consécutifs — reconnexion avant dernier essai"
        )
        try:
            self.reconnect()
            return fn(*args, **kwargs)
        except Exception as exc:
            raise exc from last_exc

    @classmethod
    def from_env(cls) -> "ExecutionEngine":
        """Retourne un moteur live si des clés API sont présentes pour l'exchange actif, sinon paper."""
        from exchange_factory import ExchangeFactory

        info = ExchangeFactory.info()
        live = info["has_api_key"] and info["mode"] != "paper"
        return cls(live=live)

    def has_futures_demo(self) -> bool:
        """True si le client Futures Demo est connecté."""
        return self._exchange_futures is not None

    def fetch_futures_balance(self) -> float:
        """Retourne la balance USD/USDT sur le compte Futures Demo."""
        if self._exchange_futures is None:
            return 0.0
        try:
            bal = self._exchange_futures.fetch_balance()
            free = bal.get("free", {})
            return float(free.get("USDT", 0.0) or free.get("USD", 0.0))
        except Exception as exc:
            _log.warning("[ExecutionEngine] fetch_futures_balance erreur: %s", exc)
            return 0.0

    # ── Configuration ──────────────────────────────────────────────────────────

    def set_size_factor(self, factor: float) -> None:
        self._size_factor = max(0.0, min(1.0, float(factor)))

    def start_session(self, equity: float) -> None:
        """Reset session-level risk counters. Call once per trading session."""
        self._guard.start_session(equity)

    def fetch_available_capital(self) -> float:
        """
        Retourne le capital USDT libre sur le compte (live/testnet).

        - Au premier appel : si l'exchange echoue, fallback sur V9_INITIAL_CAPITAL.
        - Aux appels suivants : si l'exchange echoue (ex : timestamp drift Binance),
          on retourne la DERNIERE valeur connue plutot que le fallback fixe.
          Cela evite de fabriquer un faux drawdown quand fetch_balance plante
          temporairement (cf bug DD=89.9% / ExecutiveOverride VETO).
        """
        if self._exchange is not None:
            try:
                bal = self._with_retry(self._exchange.fetch_balance)
                usdt = float(bal.get("free", {}).get(self._quote_asset, 0.0))
                if usdt > 0:
                    self._last_known_capital = usdt
                    return usdt
            except Exception as exc:
                _log.warning(
                    "[ExecutionEngine] fetch_balance erreur après retry: %s", exc
                )
        last = getattr(self, "_last_known_capital", 0.0)
        if last > 0:
            return last
        return float(os.getenv("V9_INITIAL_CAPITAL", "1000"))

    def detect_quote_asset(self, symbol: str) -> str:
        """Détecte la devise de quote d'une paire (ex: BTC/USDT → USDT)."""
        if "/" in symbol:
            return symbol.split("/")[1]
        return self._quote_asset

    # ── Main API ───────────────────────────────────────────────────────────────

    def create_order(self, symbol: str, action: str, size: float) -> dict:
        """
        Place an order through the full safety pipeline.

        Returns an order dict with a `mode` field:
          - "paper"       — paper trade accepted
          - "live"        — live order filled
          - "live_failed" — live order failed (exchange error)
          - "rejected"    — blocked by safety layer
        """
        size = size * self._size_factor

        # ── 1. Sanity check on size ────────────────────────────────────────────
        if size <= 0 or size > 1e9:
            alert = Alert(
                type_="order_size_anomaly",
                severity="critical",
                module="execution",
                message=f"Taille d'ordre anormale : {size}",
                context={"symbol": symbol, "action": action, "size": size},
            )
            alert_manager.raise_alert(alert)
            size = 1.0

        # ── 2. SessionGuard ────────────────────────────────────────────────────
        try:
            self._guard.check_order(symbol, action, size_usd=size)
        except (SessionHaltedError, OrderTooLargeError) as exc:
            reason = str(exc)
            _log.warning("[ExecutionEngine] Order rejected by SessionGuard: %s", reason)
            self._logger.log_rejected(symbol, action, size, reason)
            return {
                "symbol": symbol,
                "action": action,
                "size": round(size, 4),
                "mode": "rejected",
                "error": reason,
            }

        # ── 3. Deduplication ───────────────────────────────────────────────────
        if self._dedup.is_duplicate(symbol, action, size):
            reason = f"duplicate order within {self._dedup._window:.0f}s window"
            self._logger.log_rejected(symbol, action, size, reason)
            return {
                "symbol": symbol,
                "action": action,
                "size": round(size, 4),
                "mode": "rejected",
                "error": reason,
            }

        # ── 4. Execute ────────────────────────────────────────────────────────
        if self._live and self._exchange is not None:
            result = self._place_live_order(symbol, action, size)
        else:
            result = {
                "symbol": symbol,
                "action": action,
                "size": round(max(0.0, size), 4),
                "mode": "paper",
            }

        # ── 5. Register dedup + audit log ─────────────────────────────────────
        self._dedup.register(symbol, action, size)
        status = "ok" if result.get("mode") != "live_failed" else "error"
        self._logger.log(result, status=status)

        return result

    def _to_futures_symbol(self, symbol: str) -> str:
        """Convertit un symbole spot vers le format perp de l'exchange actif."""
        exch_id = os.getenv("EXCHANGE_ID", "binance").lower()
        if ":" in symbol:
            return symbol
        base = symbol.split("/")[0] if "/" in symbol else symbol[:3]
        if exch_id == "krakenfutures":
            # XRP uses inverse perp (XRP/USD:XRP) — testnet price tracks real price, no collar issues
            # BTC/SOL/ETH use linear perp (USD:USD) — inverse requires 1 full coin minimum
            if base == "XRP":
                return f"{base}/USD:{base}"
            return f"{base}/USD:USD"
        else:
            # Binance USDM perp: BTC/USDT → BTC/USDT:USDT
            quote = symbol.split("/")[1] if "/" in symbol else "USDT"
            return f"{base}/{quote}:{quote}"

    def create_futures_order(
        self,
        symbol: str,
        action: str,
        size_usd: float,
        leverage: int = 1,
    ) -> dict:
        """
        Passe un ordre Futures Demo (krakenfutures testnet ou Binance demo).
        symbol    : ex. 'BTC/USDT' — converti automatiquement selon l'exchange
        action    : 'BUY' (long) ou 'SELL' (short)
        size_usd  : notionnel en USD
        leverage  : levier (1 = pas de levier, max recommandé: 3)
        """
        futures_min = float(os.getenv("EXEC_FUTURES_MIN_ORDER_USD", "55"))
        futures_max = float(os.getenv("EXEC_FUTURES_MAX_ORDER_USD", "100"))
        size_usd = max(futures_min, min(futures_max, size_usd))

        if self._exchange_futures is None:
            return {
                "symbol": symbol,
                "mode": "futures_unavailable",
                "error": "Futures demo non configuré — vérifier EXCHANGE_ID et BINANCE_FUTURES_DEMO_KEY dans .env",
            }

        side = "buy" if action.upper() == "BUY" else "sell"
        ccxt_symbol = self._to_futures_symbol(symbol)

        try:
            import math as _math

            # Définir le levier
            if leverage != 1:
                try:
                    self._exchange_futures.set_leverage(leverage, ccxt_symbol)
                except Exception:
                    pass

            ticker = self._with_retry(self._exchange_futures.fetch_ticker, ccxt_symbol)
            price = float(ticker["last"])

            # Limites du marché
            try:
                markets = self._exchange_futures.load_markets()
                mkt = markets.get(ccxt_symbol, {})
                amt_precision = mkt.get("precision", {}).get("amount") or 0.001
                min_qty = (mkt.get("limits") or {}).get("amount", {}).get(
                    "min"
                ) or 0.001
            except Exception:
                amt_precision = 0.001
                min_qty = 0.001

            raw_qty = size_usd / price
            decimals = (
                max(0, -int(round(_math.log10(amt_precision))))
                if 0 < amt_precision < 1
                else 3
            )
            qty = max(min_qty, round(raw_qty, decimals))

            order = self._with_retry(
                self._exchange_futures.create_order, ccxt_symbol, "market", side, qty
            )
            _log.info(
                "[ExecutionEngine] Ordre FUTURES DEMO: %s %.4f %s @ $%.2f (lev x%d) id=%s",
                action,
                qty,
                symbol,
                price,
                leverage,
                order.get("id"),
            )
            self._logger.log(
                {**order, "mode": "futures_demo", "usd_size": round(qty * price, 2)}
            )
            return {**order, "mode": "futures_demo", "usd_size": round(qty * price, 2)}

        except Exception as exc:
            _log.error(
                "[ExecutionEngine] Echec futures demo %s %s: %s", action, symbol, exc
            )
            return {
                "symbol": symbol,
                "action": action,
                "size": size_usd,
                "mode": "futures_failed",
                "error": str(exc),
            }

    # ── Live order placement ───────────────────────────────────────────────────

    def _place_live_order(self, symbol: str, action: str, size: float) -> dict:
        """
        Passe un ordre market réel via ccxt.
        size = montant en USD à dépenser (BUY) ou valeur USD à vendre (SELL).
        """
        side = "buy" if action.upper() == "BUY" else "sell"
        ccxt_symbol = symbol.replace("USDT", "/USDT") if "/" not in symbol else symbol
        try:
            # Récupérer le prix actuel et les limites du marché
            ticker = self._with_retry(self._exchange.fetch_ticker, ccxt_symbol)
            price = float(ticker["last"])

            # Charger les limites de marché (min notionnel, précision)
            try:
                markets = self._exchange.load_markets()
                mkt = markets.get(ccxt_symbol, {})
                min_notional = float(
                    (mkt.get("limits") or {}).get("cost", {}).get("min") or 5.0
                )
                amt_precision = mkt.get("precision", {}).get("amount") or 1e-5
            except Exception:
                min_notional = 5.0
                amt_precision = 1e-5

            # Vérifier que le montant USD couvre le minimum notionnel
            if size < min_notional:
                _log.warning(
                    "[ExecutionEngine] Montant $%.2f < minimum notionnel $%.2f pour %s — ajusté",
                    size,
                    min_notional,
                    ccxt_symbol,
                )
                size = min_notional * 1.05  # 5% de marge au-dessus du minimum

            # Vérifier la balance quote disponible pour un achat
            if side == "buy":
                quote = self.detect_quote_asset(ccxt_symbol)
                bal = self._exchange.fetch_balance()
                available = float(bal.get("free", {}).get(quote, 0.0))
                if available < size:
                    _log.warning(
                        "[ExecutionEngine] Balance %s insuffisante (%.2f < %.2f USD) — taille réduite",
                        quote,
                        available,
                        size,
                    )
                    size = available * 0.95  # utilise 95% de la balance disponible

            # Convertir USD → quantité de base avec la bonne précision
            import math as _math

            raw_qty = size / price
            # Arrondir à la précision du marché (ex: 1e-5 → 5 décimales)
            decimals = (
                max(0, -int(round(_math.log10(amt_precision))))
                if 0 < amt_precision < 1
                else 5
            )
            qty = round(raw_qty, decimals)

            if qty <= 0:
                raise ValueError(f"Quantité calculée nulle ou négative: {qty}")

            order = self._with_retry(
                self._exchange.create_order, ccxt_symbol, "market", side, qty
            )
            _log.info(
                "[ExecutionEngine] Ordre live: %s %.8f %s @ $%.2f (USD: $%.2f) id=%s",
                action,
                qty,
                symbol,
                price,
                qty * price,
                order.get("id"),
            )
            return {**order, "mode": "live", "usd_size": round(qty * price, 4)}

        except Exception as exc:
            _log.error(
                "[ExecutionEngine] Echec ordre live %s %s: %s", action, symbol, exc
            )
            return {
                "symbol": symbol,
                "action": action,
                "size": round(size, 4),
                "mode": "live_failed",
                "error": str(exc),
            }

    @staticmethod
    def _log10_safe(x: float) -> float:
        import math

        return math.log10(x) if x > 0 else 0.0

    # ── Observability ──────────────────────────────────────────────────────────

    def safety_status(self) -> dict:
        """Return a snapshot of all safety-layer state."""
        return {
            "session": self._guard.state(),
            "trade_log": self._logger.stats(),
            "live_mode": self._live,
        }
