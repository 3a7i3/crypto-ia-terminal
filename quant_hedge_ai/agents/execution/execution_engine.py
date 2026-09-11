from __future__ import annotations

import math
import os
import time

from observability.json_logger import get_logger
from quant_hedge_ai.agents.execution.order_authorization import authorize_order
from quant_hedge_ai.agents.execution.order_deduplicator import OrderDeduplicator
from quant_hedge_ai.agents.execution.order_intent_protocol import (
    AdapterCapabilities,
    ExchangeMutationOutcome,
    ExchangeMutationResult,
    OrderIntentCoordinator,
    OrderIntentJournal,
    SubmissionOutcome,
    build_order_intent,
)
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

# ── O-02W-PRE-T1-E REM-B — durable order-intent journal (I3/I4/I6/I8) ─────
# Single default durable location, consistent with this repo's other
# runtime-state files under `databases/` (see `databases/runtime_config.json`,
# `databases/system_state.json`). Overridable via env for tests/ops.
_DEFAULT_ORDER_INTENT_JOURNAL_PATH = os.getenv(
    "ORDER_INTENT_JOURNAL_PATH", "databases/order_intent_journal.jsonl"
)
_CCXT_CAPABILITIES = AdapterCapabilities(
    supports_client_order_id=True,
    client_order_id_param="clientOrderId",
    supports_lookup_by_client_order_id=True,
)


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
        _exch_id = os.getenv("EXCHANGE_ID", "mexc").lower()
        _futures_exchanges = {"krakenfutures", "binanceusdm"}
        self._quote_asset = "USD" if _exch_id in _futures_exchanges else "USDT"
        if live:
            self._exchange = self._init_exchange()
            self._exchange_futures = self._init_futures_demo()

        # O-02W-PRE-T1-E REM-B — durable idempotent submission coordinator.
        # Lazily constructed (see `_get_order_intent_coordinator` below): a
        # plain `ExecutionEngine()` construction (paper mode, most tests)
        # must not touch disk under `databases/` unless a caller actually
        # exercises the `decision_id=` REM-B path — avoids contaminating the
        # scientific data guard baseline (.ci/scientific_data_guard_baseline.json,
        # conftest.py) on every unrelated test run.
        self._order_intent_journal = None
        self._order_intent_coordinator = None

        # Safety layer
        self._dedup = OrderDeduplicator(
            window_seconds=float(os.getenv("EXEC_DEDUP_WINDOW", "30"))
        )
        self._guard = SessionGuard(
            max_session_drawdown=float(os.getenv("EXEC_MAX_DD", "0.05")),
            max_session_loss=float(os.getenv("EXEC_MAX_LOSS", "0.03")),
            max_consecutive_losses=int(os.getenv("EXEC_MAX_CONSEC_LOSSES", "3")),
            max_order_size_usd=float(os.getenv("EXEC_MAX_ORDER_USD", "50")),
        )
        self._logger = TradeLogger(
            db_path=os.getenv("EXEC_TRADE_LOG", "databases/trade_log.sqlite")
        )

    def _init_exchange(self):
        """Initialise le client Spot via ExchangeFactory (multi-exchange)."""
        try:
            from infra.exchange_factory import ExchangeFactory, detect_mode

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
        - MEXC : paper trading géré par MexcSimulator — pas de connexion CCXT futures
        """
        exch_id = os.getenv("EXCHANGE_ID", "").lower()

        # krakenfutures testnet — même exchange que le principal
        if exch_id == "krakenfutures" and self._exchange is not None:
            _log.info(
                "[ExecutionEngine] Futures Demo = krakenfutures testnet (exchange partagé)"
            )
            return self._exchange

        _log.debug(
            "[ExecutionEngine] Futures demo via MexcSimulator — aucune connexion CCXT directe"
        )
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
        """Retourne un moteur live si des clés API sont présentes pour l'exchange
        actif ET que LIVE_TRADING_CONFIRMED=true, sinon paper.

        LIVE_TRADING_CONFIRMED — 2e ligne de défense (SEC-01, 2026-07-08) : la
        seule présence de clés API ne suffit plus à armer l'exécution réelle.
        Variable absente par défaut partout — à poser uniquement lors d'une
        activation volontaire du trading réel (procédure checklist dédiée),
        jamais comme effet de bord d'une config existante.
        """
        from infra.exchange_factory import ExchangeFactory

        info = ExchangeFactory.info()
        live_trading_confirmed = os.getenv(
            "LIVE_TRADING_CONFIRMED", "false"
        ).lower() in {"1", "true", "yes", "on"}
        live = (
            info["has_api_key"] and info["mode"] != "paper" and live_trading_confirmed
        )
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
        Retourne le capital de décision scientifique — SEULE entrée pour le
        sizing/risque (O-02W-PRE-T1-D remediation,
        docs/adr/0018-scientific-capital-exchange-observation-separation.md).

        WALLET_PAPER_CAPITAL + somme cumulative des pnl_usd du ledger
        (databases/paper_trades.jsonl) — identique à ce qu'affichent
        /portfolio, le bot Intel et prelive_gate.py.

        Cette valeur est désormais STRICTEMENT indépendante de
        EXCHANGE_MODE, PAPER_TRADING_ENABLED, LIVE_TRADING_CONFIRMED, de
        self._mode/self._exchange, et de l'ordre d'initialisation du
        singleton WalletSync — elle ne fait AUCUN appel exchange (défauts
        #1-#6 de l'audit PRE-T1-D, closés). Les soldes d'exchange réels
        restent purement observationnels : voir
        infra.wallet_sync.WalletSync.observe_exchange_balance() /
        observability/real_accounts.py, qui ne doivent jamais alimenter ce
        retour.
        """
        from infra.wallet_sync import get_scientific_capital

        return get_scientific_capital()

    def detect_quote_asset(self, symbol: str) -> str:
        """Détecte la devise de quote d'une paire (ex: BTC/USDT → USDT)."""
        if "/" in symbol:
            return symbol.split("/")[1]
        return self._quote_asset

    # ── Main API ───────────────────────────────────────────────────────────────

    def create_order(
        self, symbol: str, action: str, size: float, decision_id: str | None = None
    ) -> dict:
        """
        Place an order through the full safety pipeline.

        Returns an order dict with a `mode` field:
          - "paper"       — paper trade accepted
          - "live"        — live order filled
          - "live_failed" — live order failed (exchange error)
          - "rejected"    — blocked by safety layer

        `decision_id` (O-02W-PRE-T1-E REM-B, optional): when the caller
        already has a stable upstream causal identifier for this order
        intention (e.g. a DecisionPacket id), pass it to route the live
        mutation through the durable, deterministic, idempotent
        submission protocol (order_intent_protocol.py). When omitted, this
        call keeps its pre-REM-B behavior unchanged — REM-B does not yet
        claim I4/I8 coverage for callers that have no causal id to give it
        (see ADR — advisor_loop.py causal-id plumbing is REM-C-adjacent
        scope, not modified by this mission).
        """
        size = size * self._size_factor

        # ── 1. Sanity check on size (Correction A, O-02W-PRE-T1-E REM-A) ───────
        # Invalid/non-finite/non-positive sizes are REJECTED, never
        # substituted with an arbitrary tradable amount — a substitution here
        # would let one bad intention silently become a real order.
        try:
            size_is_finite = math.isfinite(size)
        except TypeError:
            size_is_finite = False
        if not size_is_finite or size <= 0 or size > 1e9:
            alert = Alert(
                type_="order_size_anomaly",
                severity="critical",
                module="execution",
                message=f"Taille d'ordre anormale : {size}",
                context={"symbol": symbol, "action": action, "size": size},
            )
            alert_manager.raise_alert(alert)
            reason = f"invalid order size (pre-network authorization): {size}"
            _log.warning("[ExecutionEngine] Order rejected — %s", reason)
            self._logger.log_rejected(symbol, action, size, reason)
            return {
                "symbol": symbol,
                "action": action,
                "size": size if size_is_finite else 0.0,
                "mode": "rejected",
                "error": reason,
                "denial_reason": (
                    "NON_FINITE_AMOUNT"
                    if not size_is_finite
                    else "NON_POSITIVE_AMOUNT"
                    if size <= 0
                    else "ABOVE_AUTHORIZED_EXPOSURE"
                ),
            }

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
            result = self._place_live_order(symbol, action, size, decision_id=decision_id)
        else:
            result = {
                "symbol": symbol,
                "action": action,
                "size": round(max(0.0, size), 4),
                "mode": "paper",
            }

        # ── 5. Register dedup + audit log ─────────────────────────────────────
        self._dedup.register(symbol, action, size)
        status = (
            "error" if result.get("mode") in ("live_failed", "rejected") else "ok"
        )
        self._logger.log(result, status=status)

        return result

    def _to_futures_symbol(self, symbol: str) -> str:
        """Convertit un symbole spot vers le format perp de l'exchange actif."""
        exch_id = os.getenv("EXCHANGE_ID", "mexc").lower()
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
            # MEXC/generic perp: BTC/USDT → BTC/USDT:USDT
            quote = symbol.split("/")[1] if "/" in symbol else "USDT"
            return f"{base}/{quote}:{quote}"

    def create_futures_order(
        self,
        symbol: str,
        action: str,
        size_usd: float,
        leverage: int = 1,
        decision_id: str | None = None,
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
        # Narrowing-only clamp (never amplifies): a request above the
        # configured ceiling is capped down, exactly like `authorized_max_amount`
        # elsewhere in this module. The below-minimum case is NOT handled here
        # anymore — amplifying it up to `futures_min` was the H2-shaped defect
        # (O-02W-PRE-T1-E REM-A R1); it is now rejected by `authorize_order()`
        # below via `min_notional=futures_min`, never silently enlarged.
        size_usd = min(futures_max, size_usd)

        if self._exchange_futures is None:
            return {
                "symbol": symbol,
                "mode": "futures_unavailable",
                "error": "Futures demo non configuré — paper trading via MexcSimulator (vérifier MEXC_API_KEY dans .env)",
            }

        side = "buy" if action.upper() == "BUY" else "sell"
        ccxt_symbol = self._to_futures_symbol(symbol)

        try:
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
                amt_precision = mkt.get("precision", {}).get("amount") or 1e-5
            except Exception:
                amt_precision = 1e-5

            # Pre-network authorization (Correction B, O-02W-PRE-T1-E REM-A
            # R1): closes the H2-shaped defect this path had (silently
            # enlarging a below-minimum size instead of rejecting it).
            # `require_balance_check=False` — a futures/margin market draws
            # down quote-denominated margin on BOTH buy and sell, unlike
            # spot's base/quote split; there is no base-asset balance to
            # check for a SHORT here (see order_authorization.py docstring,
            # ADR-0019 §6). `min_qty` (exchange-reported minimum quantity)
            # is folded into `amount_precision` handling below via the
            # existing floor-only normalization — `authorize_order()` never
            # rounds up to satisfy it.
            auth = authorize_order(
                symbol=ccxt_symbol,
                side=side,
                requested_amount=size_usd,
                price=price,
                amount_precision=amt_precision,
                min_notional=futures_min,
                require_balance_check=False,
                balance_source="futures_margin_not_balance_checked",
            )
            if not auth.authorized:
                reason = auth.denial_reason.value if auth.denial_reason else "denied"
                _log.warning(
                    "[ExecutionEngine] Ordre futures demo refusé (pre-network "
                    "authorization) %s %s: %s — %s",
                    action,
                    symbol,
                    reason,
                    auth.detail,
                )
                return {
                    "symbol": symbol,
                    "action": action,
                    "size": size_usd,
                    "mode": "rejected",
                    "error": auth.detail,
                    "denial_reason": reason,
                }

            # NOT `max(min_qty, ...)`: clamping the authorized quantity up to
            # the exchange's minimum tradeable size would silently re-widen
            # exposure beyond what `authorize_order()` just authorized — the
            # exact H2 shape this fix removes. If `min_qty` is unmet the
            # exchange itself rejects the order (visible failure, not a
            # silent amplification).
            qty = auth.normalized_qty

            if decision_id:
                intent = build_order_intent(
                    namespace="ExecutionEngine.futures",
                    causal_id=decision_id,
                    account_scope=f"{os.getenv('EXCHANGE_ID', 'mexc')}:futures_demo",
                    symbol=ccxt_symbol,
                    side=side,
                    order_type="market",
                    amount=qty,
                    price=price,
                    reduce_only=False,
                )
                mutate = self._mutate_via_coordinator(
                    self._exchange_futures.create_order, ccxt_symbol, side, qty
                )
                sub = self._get_order_intent_coordinator().submit(
                    intent,
                    authorized=True,
                    authorization_ref=auth.detail,
                    mutate=mutate,
                )
                if sub.outcome != SubmissionOutcome.ACKNOWLEDGED:
                    _log.warning(
                        "[ExecutionEngine] Ordre futures non acquitté (REM-B) %s %s: %s",
                        action,
                        symbol,
                        sub.outcome.value,
                    )
                    return {
                        "symbol": symbol,
                        "action": action,
                        "size": size_usd,
                        "mode": "futures_ambiguous"
                        if sub.outcome
                        in (
                            SubmissionOutcome.RECONCILE_REQUIRED,
                            SubmissionOutcome.RECONCILED_NOT_FOUND_PENDING,
                        )
                        else "futures_failed",
                        "error": sub.detail,
                        "order_intent_outcome": sub.outcome.value,
                        "client_order_id": sub.client_order_id,
                    }
                order = (sub.raw_evidence or {}).get("order", {"id": sub.exchange_order_id})
            else:
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

    @staticmethod
    def _paper_trading_enabled() -> bool:
        """Lu à l'appel, jamais mis en cache (DS-001, ADR-0008) — permet de
        désarmer l'exécution réelle sans redémarrage."""
        return os.getenv("PAPER_TRADING_ENABLED", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _get_order_intent_coordinator(self) -> OrderIntentCoordinator:
        if self._order_intent_coordinator is None:
            self._order_intent_journal = OrderIntentJournal(
                _DEFAULT_ORDER_INTENT_JOURNAL_PATH
            )
            self._order_intent_coordinator = OrderIntentCoordinator(
                self._order_intent_journal, _CCXT_CAPABILITIES
            )
        return self._order_intent_coordinator

    def _mutate_via_coordinator(self, mutate_fn, ccxt_symbol, side, qty):
        """Wraps a raw `self._exchange.create_order(...)` call (via
        `_with_retry`) into the typed `ExchangeMutationResult` the
        coordinator requires — REM-B never adds its OWN retry loop around a
        submission; `_with_retry` here only covers pre-submission read calls
        upstream (ticker/markets/balance), never the mutation itself (I5)."""

        def mutate(intent, client_order_id):
            try:
                order = mutate_fn(
                    ccxt_symbol,
                    "market",
                    side,
                    qty,
                    params={"clientOrderId": client_order_id},
                )
                return ExchangeMutationResult(
                    outcome=ExchangeMutationOutcome.ACKNOWLEDGED,
                    exchange_order_id=order.get("id"),
                    raw={"order": order},
                )
            except Exception as exc:  # noqa: BLE001 — classify below
                msg = str(exc).lower()
                if any(k in msg for k in ("timeout", "timed out", "econnreset", "connection")):
                    return ExchangeMutationResult(
                        outcome=ExchangeMutationOutcome.AMBIGUOUS,
                        error_category="transport_error",
                        raw={"error": str(exc)},
                    )
                if any(k in msg for k in ("insufficient", "invalid", "rejected", "not enough")):
                    return ExchangeMutationResult(
                        outcome=ExchangeMutationOutcome.EXPLICITLY_REJECTED,
                        error_category="exchange_rejected",
                        raw={"error": str(exc)},
                    )
                # Unknown exception shape — never assume success or failure.
                return ExchangeMutationResult(
                    outcome=ExchangeMutationOutcome.AMBIGUOUS,
                    error_category="unknown_response",
                    raw={"error": str(exc)},
                )

        return mutate

    def _place_live_order(
        self, symbol: str, action: str, size: float, decision_id: str | None = None
    ) -> dict:
        """
        Passe un ordre market réel via ccxt.
        size = montant en USD à dépenser (BUY) ou valeur USD à vendre (SELL).
        """
        if self._paper_trading_enabled():
            # SEC-01 (2026-07-08) — gate d'exécution réelle, plus un flag
            # narratif. Neutralité stricte : même forme de retour que le
            # rejet MEXC 700007 (mode="live_failed"), avant tout appel
            # réseau — mêmes compteurs d'erreurs et mode DEGRADED en aval.
            _log.warning(
                "[ExecutionEngine] Ordre live bloqué par PAPER_TRADING_ENABLED — %s %s",
                action,
                symbol,
            )
            return {
                "symbol": symbol,
                "action": action,
                "size": round(size, 4),
                "mode": "live_failed",
                "error": "blocked_by_paper_gate",
            }

        # Authority composition (Correction E, O-02W-PRE-T1-E REM-A):
        # `_place_live_order` is only ever reachable when `self._exchange is
        # not None` (create_order's step 4 gate) AND `self._live` is True.
        # `self._live` is set True only by `ExecutionEngine.from_env()` after
        # BOTH `info["has_api_key"]` and `LIVE_TRADING_CONFIRMED=true`
        # (execution_engine.py `from_env`), or by an explicit
        # `ExecutionEngine(live=True)` construction that a caller chose
        # deliberately (out of this module's control — documented, not
        # silently trusted: the `PAPER_TRADING_ENABLED` check immediately
        # above is what actually fails closed on THIS call, read fresh from
        # the environment on every invocation, never cached). This is the
        # documented, tested composition of authorities for this path — no
        # single canonical module claims to own it alone (see ADR).
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

            # Récupérer la balance de l'actif exécutable pertinent (BUY: quote,
            # SELL: base) — jamais le capital scientifique, jamais fabriquée
            # (Correction D, O-02W-PRE-T1-E REM-A). fetch_balance() est le
            # seul appel réseau ici, PAS une mutation — la mutation reste
            # create_order() plus bas, seulement atteinte si autorize_order()
            # autorise.
            quote = self.detect_quote_asset(ccxt_symbol)
            base = ccxt_symbol.split("/")[0] if "/" in ccxt_symbol else None
            balance_error = False
            available_quote = None
            available_base = None
            try:
                bal = self._exchange.fetch_balance()
                free = bal.get("free", {}) or {}
                available_quote = free.get(quote)
                available_base = free.get(base) if base else None
            except Exception as bal_exc:
                _log.warning(
                    "[ExecutionEngine] fetch_balance erreur (%s): %s",
                    ccxt_symbol,
                    bal_exc,
                )
                balance_error = True

            auth = authorize_order(
                symbol=ccxt_symbol,
                side=side,
                requested_amount=size,
                price=price,
                amount_precision=amt_precision,
                min_notional=min_notional,
                available_quote_balance=available_quote,
                available_base_balance=available_base,
                balance_error=balance_error,
                balance_source="exchange.fetch_balance",
            )
            if not auth.authorized:
                reason = auth.denial_reason.value if auth.denial_reason else "denied"
                _log.warning(
                    "[ExecutionEngine] Ordre live refusé (pre-network authorization) "
                    "%s %s: %s — %s",
                    action,
                    symbol,
                    reason,
                    auth.detail,
                )
                return {
                    "symbol": symbol,
                    "action": action,
                    "size": round(size, 4),
                    "mode": "rejected",
                    "error": auth.detail,
                    "denial_reason": reason,
                }

            qty = auth.normalized_qty

            if decision_id:
                # O-02W-PRE-T1-E REM-B — durable, deterministic, idempotent
                # submission path. Not entered when the caller has no
                # upstream causal id (see create_order docstring).
                intent = build_order_intent(
                    namespace="ExecutionEngine.spot",
                    causal_id=decision_id,
                    account_scope=f"{os.getenv('EXCHANGE_ID', 'mexc')}:live",
                    symbol=ccxt_symbol,
                    side=side,
                    order_type="market",
                    amount=qty,
                    price=price,
                    reduce_only=False,
                )
                mutate = self._mutate_via_coordinator(
                    self._exchange.create_order, ccxt_symbol, side, qty
                )
                sub = self._get_order_intent_coordinator().submit(
                    intent,
                    authorized=True,
                    authorization_ref=auth.detail,
                    mutate=mutate,
                )
                if sub.outcome != SubmissionOutcome.ACKNOWLEDGED:
                    _log.warning(
                        "[ExecutionEngine] Ordre live non acquitté (REM-B) %s %s: %s",
                        action,
                        symbol,
                        sub.outcome.value,
                    )
                    return {
                        "symbol": symbol,
                        "action": action,
                        "size": round(size, 4),
                        "mode": "live_ambiguous"
                        if sub.outcome
                        in (
                            SubmissionOutcome.RECONCILE_REQUIRED,
                            SubmissionOutcome.RECONCILED_NOT_FOUND_PENDING,
                        )
                        else "live_failed",
                        "error": sub.detail,
                        "order_intent_outcome": sub.outcome.value,
                        "client_order_id": sub.client_order_id,
                    }
                order = (sub.raw_evidence or {}).get("order", {"id": sub.exchange_order_id})
            else:
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
