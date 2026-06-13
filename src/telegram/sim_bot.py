"""
SimBot — Telegram bot exclusivement dédié au noyau de simulation CMVK.
Token : CMVK_BOT_TOKEN  /  Chat : CMVK_CHAT_ID
Isolé des bots live. Affiche uniquement les logs du simulateur.
"""

import time

from src.agent.breakout_strategy import BreakoutStrategy
from src.agent.codex_agent import CodexAgent
from src.agent.momentum_strategy import MomentumStrategy
from src.agent.rsi_extreme_strategy import RSIExtremeStrategy
from src.agent.rsi_strategy import RSIStrategy
from src.agent.sma_strategy import SMAStrategy
from src.analytics.edge_scorer import EdgeScorer
from src.analytics.performance_breakdown import breakdown
from src.backtest.data_feed import HistoricalDataFeed
from src.backtest.engine import BacktestEngine
from src.backtest.market_generator import for_stress as _gen_stress
from src.backtest.mexc_feed import fetch_mexc_candles, mexc_feed
from src.backtest.walk_forward import sliding_windows
from src.engine.execution_router import ExecutionRouter
from src.engine.virtual_exchange import VirtualExchange
from src.events.event_bus import SimEventBus
from src.execution.enl import ENLConfig, NoisyExchange
from src.journal.trade_logger import TradeLogger
from src.portfolio.portfolio_state import PortfolioState
from src.risk.kill_switch import KillSwitch
from src.risk.regime_gate import RegimeGate
from src.runtime.run_context import RunContext
from src.storage.run_repository import RunRepository
from src.telegram.notifier import Notifier as SimNotifier

_PRESETS = {
    "fast": (3, 10, "SMA_3_10"),
    "slow": (5, 20, "SMA_5_20"),
    "ultra": (2, 7, "SMA_2_7"),
}

# Symboles live supportés (MEXC Spot public)
_LIVE_SYMBOLS = {"btc": "BTCUSDT", "eth": "ETHUSDT", "sol": "SOLUSDT", "xrp": "XRPUSDT"}


class SimBot:
    """
    Logique pure du bot simulation. Testable sans connexion Telegram.
    La couche HTTP (polling) est dans bot_runner.py.

    État persistant sur la durée de vie du processus :
      - journal global  : accumule tous les trades de tous les runs
      - runs_history    : liste des rapports de chaque run
      - kill_switch     : partagé entre tous les runs
    """

    def __init__(
        self,
        initial_balance: float = 10_000.0,
        db_path: str = "databases/sim_runs.sqlite",
    ):
        self._balance = initial_balance
        self._kill_switch = KillSwitch()
        self._bus = SimEventBus()
        self._logger = TradeLogger()
        self._bus.subscribe("TRADE_OPENED", self._logger.on_trade_opened)
        self._bus.subscribe("TRADE_CLOSED", self._logger.on_trade_closed)
        self._runs_history: list[dict] = []
        self._repo = RunRepository(db_path)
        self._notifier = SimNotifier()  # logs vers @mon_portfolio_bot uniquement

    # ------------------------------------------------------------------ #
    # Dispatcher                                                            #
    # ------------------------------------------------------------------ #

    def handle(self, text: str) -> str:
        parts = text.strip().split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        dispatch = {
            "/start": self._cmd_start,
            "/help": self._cmd_help,
            "/run": self._cmd_run,
            "/status": self._cmd_status,
            "/pnl": self._cmd_pnl,
            "/trades": self._cmd_trades,
            "/runs": self._cmd_runs,
            "/kill": self._cmd_kill,
            "/resume": self._cmd_resume,
            "/market": self._cmd_market,
            "/stress": self._cmd_stress,
            "/history": self._cmd_history,
            "/breakdown": self._cmd_breakdown,
            "/overall": self._cmd_overall,
            "/compare": self._cmd_compare,
            "/validate": self._cmd_validate,
            "/race": self._cmd_race,
            "/robust": self._cmd_robust,
            "/distrib": self._cmd_distrib,
            "/friction": self._cmd_friction,
            "/score": self._cmd_score,
        }
        fn = dispatch.get(cmd)
        if fn is None:
            return f"Commande inconnue : `{cmd}`\nTape /help pour la liste."
        return fn(arg)

    # ------------------------------------------------------------------ #
    # Handlers                                                              #
    # ------------------------------------------------------------------ #

    def _cmd_start(self, _: str) -> str:
        return (
            "🤖 *CMVK Simulation Bot*\n"
            "_Aucun ordre réel — simulation uniquement_\n\n"
            "*Backtest synthétique*\n"
            "/run `[fast|slow|ultra]` — candles générées\n\n"
            "*Backtest données réelles MEXC*\n"
            "/run `live [btc|eth|sol|xrp] [1h] [200]`\n\n"
            "*Observation marché*\n"
            "/market `[btc|eth|sol|xrp]` — dernières candles live\n\n"
            "*Journal & état*\n"
            "/status · /pnl · /trades `[N]` · /runs\n"
            "/history `[N]` — derniers N runs persistés\n"
            "/breakdown `[régime]` — stats DB par régime\n\n"
            "*Contrôle*\n"
            "/kill · /resume · /help"
        )

    def _cmd_help(self, arg: str) -> str:
        return self._cmd_start(arg)

    def _cmd_run(self, arg: str) -> str:
        if self._kill_switch.engaged:
            return "⛔ Kill switch actif. Tape /resume avant de lancer un run."

        parts = arg.lower().split() if arg else []

        # -- mode live : /run live [symbol] [interval] [limit] --
        if parts and parts[0] == "live":
            sym_key = parts[1] if len(parts) > 1 else "btc"
            interval = parts[2] if len(parts) > 2 else "1h"
            try:
                limit = int(parts[3]) if len(parts) > 3 else 200
            except ValueError:
                limit = 200

            symbol = _LIVE_SYMBOLS.get(sym_key)
            if symbol is None:
                return f"Symbole inconnu : `{sym_key}`\nChoix : btc | eth | sol | xrp"

            try:
                feed = mexc_feed(symbol, interval, limit)
            except Exception as exc:
                return f"❌ Erreur MEXC : {exc}"

            n_candles = len(feed.candles)
            preset = "fast"
            strategy_id = f"SMA_3_10_LIVE_{sym_key.upper()}_{interval}"
            fast, slow = 3, 10

        # -- mode synthétique : /run [fast|slow|ultra] --
        else:
            preset = parts[0] if parts else "fast"
            if preset not in _PRESETS:
                return f"Preset inconnu : `{preset}`\nChoix : fast | slow | ultra\nOu : live btc|eth|sol|xrp"
            fast, slow, strategy_id = _PRESETS[preset]
            candles = _synthetic_candles(n=120, seed=int(time.time()) % 1000)
            feed = HistoricalDataFeed(candles)
            n_candles = len(candles)
            symbol = "BTC"

        portfolio = PortfolioState(balance=self._balance)
        exchange = VirtualExchange(portfolio, event_bus=self._bus)
        router = ExecutionRouter(exchange)
        agent = CodexAgent(SMAStrategy(fast, slow), self._kill_switch)
        ctx = RunContext(strategy_id=strategy_id)
        engine = BacktestEngine(agent, router, feed, portfolio, run_context=ctx)

        report = engine.run()
        self._runs_history.append(report)
        self._repo.save_run(report, n_candles=n_candles)
        src_label = f"MEXC {symbol}" if "LIVE" in strategy_id else "synthétique"
        self._notifier.run_completed(
            report, source=src_label if "LIVE" in strategy_id else "synth"
        )

        sign = "+" if report["total_pnl"] >= 0 else ""
        regime_emoji = {"trending": "📈", "sideways": "↔️", "volatile": "⚡"}.get(
            report.get("regime", ""), "❓"
        )
        return (
            f"📊 *Run terminé* — `{report['run_id']}`\n"
            f"Source    : {src_label} ({n_candles} candles)\n"
            f"Stratégie : `{strategy_id}`\n"
            f"Régime    : {regime_emoji} {report.get('regime', '?')} "
            f"(ATR {report.get('regime_atr', 0):.2%} | slope {report.get('regime_slope', 0):+.2%})\n"
            f"Trades    : {report['total_trades']}\n"
            f"PnL       : {sign}{report['total_pnl']:.2f} USD\n"
            f"Win rate  : {report['win_rate']:.0%}\n"
            f"Max DD    : {report['max_drawdown']:.2%}\n"
            f"Balance   : {report['final_balance']:.2f} USD"
        )

    def _cmd_status(self, _: str) -> str:
        ks = "⛔ ENGAGÉ" if self._kill_switch.engaged else "✅ libre"
        total_runs = len(self._runs_history)

        if not self._runs_history:
            return (
                f"📋 *Status simulateur*\n"
                f"Runs effectués : 0\n"
                f"Kill switch    : {ks}\n"
                f"Journal        : 0 entrées\n\n"
                "_Tape /run pour démarrer._"
            )

        last = self._runs_history[-1]
        sign = "+" if last["total_pnl"] >= 0 else ""
        return (
            f"📋 *Status simulateur*\n"
            f"Dernier run    : `{last['run_id']}` ({last['strategy_id']})\n"
            f"Balance        : {last['final_balance']:.2f} USD\n"
            f"PnL dernier    : {sign}{last['total_pnl']:.2f} USD\n"
            f"Trades dernier : {last['total_trades']}\n"
            f"Runs session   : {total_runs}\n"
            f"Kill switch    : {ks}\n"
            f"Journal global : {len(self._logger.logs)} entrées"
        )

    def _cmd_pnl(self, _: str) -> str:
        pnl = self._logger.total_pnl()
        wr = self._logger.win_rate()
        closed = len(self._logger.closed_trades())
        runs = len(self._runs_history)
        sign = "+" if pnl >= 0 else ""
        return (
            f"💰 *PnL journal global*\n"
            f"PnL cumulé    : {sign}{pnl:.2f} USD\n"
            f"Win rate      : {wr:.0%}\n"
            f"Trades fermés : {closed}\n"
            f"Runs session  : {runs}"
        )

    def _cmd_trades(self, arg: str) -> str:
        try:
            n = max(1, min(int(arg), 20)) if arg else 5
        except ValueError:
            n = 5

        closed = self._logger.closed_trades()
        if not closed:
            return "Aucun trade fermé dans le journal."

        lines = [f"📜 *Derniers {min(n, len(closed))} trades*"]
        for t in closed[-n:]:
            pnl = t.net_pnl_usd
            sign = "+" if pnl >= 0 else ""
            lines.append(
                f"`{t.symbol}` {sign}{pnl:.2f}$ "
                f"exit={t.exit_price:.2f} "
                f"[{t.strategy_id} #{t.run_id}]"
            )
        return "\n".join(lines)

    def _cmd_runs(self, _: str) -> str:
        if not self._runs_history:
            return "Aucun run cette session."

        lines = [f"🗂 *Historique session ({len(self._runs_history)} runs)*"]
        for r in self._runs_history[-10:]:
            sign = "+" if r["total_pnl"] >= 0 else ""
            lines.append(
                f"`{r['run_id']}` {r['strategy_id']} — "
                f"{sign}{r['total_pnl']:.2f}$ — "
                f"{r['total_trades']}T — "
                f"WR {r['win_rate']:.0%}"
            )
        return "\n".join(lines)

    def _cmd_stress(self, arg: str) -> str:
        if self._kill_switch.engaged:
            return "⛔ Kill switch actif."
        try:
            n = max(10, min(int(arg), 500)) if arg else 100
        except ValueError:
            n = 100

        reports = []
        for seed in range(n):
            candles, expected_regime = _gen_stress(seed=seed, n=120)
            portfolio = PortfolioState(balance=self._balance)
            exchange = VirtualExchange(portfolio, event_bus=self._bus)
            router = ExecutionRouter(exchange)
            feed = HistoricalDataFeed(candles)
            agent = CodexAgent(SMAStrategy(3, 10), self._kill_switch)
            ctx = RunContext(strategy_id="SMA_3_10_STRESS")
            engine = BacktestEngine(agent, router, feed, portfolio, run_context=ctx)
            r = engine.run()
            reports.append(r)
            self._repo.save_run(r, n_candles=120)

        self._runs_history.extend(reports)
        bd = breakdown(reports)
        a = bd["all"]
        self._notifier.stress_completed(
            n, a["avg_pnl"], a["profit_factor"], a["avg_win_rate"]
        )

        def _fmt(s: dict, label: str) -> str:
            if s["n_runs"] == 0:
                return f"  {label}: 0 runs"
            sign = "+" if s["avg_pnl"] >= 0 else ""
            return (
                f"  {label} ({s['n_runs']}r) : "
                f"{sign}{s['avg_pnl']:.2f}$ | "
                f"WR {s['avg_win_rate']:.0%} | "
                f"PF {s['profit_factor']:.2f} | "
                f"DD {s['avg_drawdown']:.2%}"
            )

        a = bd["all"]
        sign = "+" if a["avg_pnl"] >= 0 else ""
        return (
            f"🔬 *Stress test — {n} runs*\n\n"
            f"*Global*\n"
            f"  Avg PnL   : {sign}{a['avg_pnl']:.2f} USD\n"
            f"  Win rate  : {a['avg_win_rate']:.0%}\n"
            f"  Profit F. : {a['profit_factor']:.2f}\n"
            f"  Avg DD    : {a['avg_drawdown']:.2%}\n"
            f"  Trades    : {a['total_trades']}\n\n"
            f"*Par régime*\n"
            + _fmt(bd["trending"], "📈 trend   ")
            + "\n"
            + _fmt(bd["sideways"], "↔️ range   ")
            + "\n"
            + _fmt(bd["volatile"], "⚡ volatile")
        )

    def _cmd_history(self, arg: str) -> str:
        try:
            n = max(1, min(int(arg), 20)) if arg else 10
        except ValueError:
            n = 10
        runs = self._repo.last_runs(n)
        total = self._repo.count()
        if not runs:
            return "Aucun run persisté. Tape /run pour commencer."
        regime_emoji = {"trending": "📈", "sideways": "↔️", "volatile": "⚡"}
        lines = [f"🗄 *Historique DB — {total} runs total* (derniers {len(runs)})"]
        for r in runs:
            sign = "+" if r["total_pnl"] >= 0 else ""
            em = regime_emoji.get(r["regime"], "❓")
            lines.append(
                f"`{r['run_id']}` {em} {r['strategy_id'][:12]} "
                f"{sign}{r['total_pnl']:.2f}$ "
                f"WR {r['win_rate']:.0%} "
                f"`{r['created_at'][:10]}`"
            )
        return "\n".join(lines)

    def _cmd_compare(self, arg: str) -> str:
        """
        Test A/B rigoureux sur les mêmes seeds.
        A = SMA 3/10 brute (trade partout)
        B = SMA 3/10 + RegimeGate (range uniquement)
        """
        if self._kill_switch.engaged:
            return "⛔ Kill switch actif."
        try:
            n = max(10, min(int(arg), 1000)) if arg else 200
        except ValueError:
            n = 200

        from src.analytics.regime_detector import RegimeDetector

        detector = RegimeDetector()

        results_a, results_b = [], []

        for seed in range(n):
            candles, _ = _gen_stress(seed=seed, n=120)

            def _run(use_gate: bool) -> dict:
                portfolio = PortfolioState(balance=self._balance)
                exchange = VirtualExchange(portfolio)
                router = ExecutionRouter(exchange)
                feed = HistoricalDataFeed(candles)
                base = CodexAgent(SMAStrategy(3, 10), self._kill_switch)
                agent = (
                    RegimeGate(base, allowed_regimes={"sideways"}, detector=detector)
                    if use_gate
                    else base
                )
                ctx = RunContext(strategy_id="SMA_B_GATE" if use_gate else "SMA_A_RAW")
                return BacktestEngine(agent, router, feed, portfolio, ctx).run()

            results_a.append(_run(use_gate=False))
            results_b.append(_run(use_gate=True))

        def _agg(reports: list[dict]) -> dict:
            n = len(reports)
            pnls = [r["total_pnl"] for r in reports]
            trades = [r["total_trades"] for r in reports]
            wrs = [r["win_rate"] for r in reports]
            dds = [r["max_drawdown"] for r in reports]
            gains = sum(p for p in pnls if p > 0)
            losses = abs(sum(p for p in pnls if p < 0))
            pf = gains / losses if losses > 0 else (float("inf") if gains > 0 else 0.0)
            avg_trades = sum(trades) / n
            exp = (sum(pnls) / n) / avg_trades if avg_trades > 0 else 0.0
            return {
                "avg_pnl": round(sum(pnls) / n, 2),
                "win_rate": round(sum(wrs) / n, 3),
                "pf": round(pf, 2),
                "avg_dd": round(sum(dds) / n, 4),
                "expectancy": round(exp, 3),
                "trades": sum(trades),
            }

        a = _agg(results_a)
        b = _agg(results_b)

        def _sign(v):
            return "+" if v >= 0 else ""

        def _delta(va, vb, fmt=".3f"):
            d = vb - va
            s = "+" if d >= 0 else ""
            return f"({s}{d:{fmt}})"

        return (
            f"⚖️ *Comparaison A/B — {n} runs identiques*\n\n"
            f"```\n"
            f"                  A (brute)    B (filtre range)\n"
            f"Avg PnL    {_sign(a['avg_pnl'])}{a['avg_pnl']:>8.2f}$   {_sign(b['avg_pnl'])}{b['avg_pnl']:>8.2f}$  {_delta(a['avg_pnl'], b['avg_pnl'], '.2f')}\n"
            f"Expectancy {_sign(a['expectancy'])}{a['expectancy']:>8.3f}    {_sign(b['expectancy'])}{b['expectancy']:>8.3f}   {_delta(a['expectancy'], b['expectancy'])}\n"
            f"Win Rate   {a['win_rate']:>8.0%}   {b['win_rate']:>8.0%}\n"
            f"Prof. Fact {a['pf']:>8.2f}   {b['pf']:>8.2f}\n"
            f"Avg DD     {a['avg_dd']:>8.2%}   {b['avg_dd']:>8.2%}\n"
            f"Trades     {a['trades']:>8d}   {b['trades']:>8d}\n"
            f"```\n"
            f"_Delta B-A : expectancy {_delta(a['expectancy'], b['expectancy'])}_"
        )

    def _cmd_friction(self, arg: str) -> str:
        """
        Test de survie RSI 14 sous 3 niveaux de friction microstructure.
        Même datasets que /robust — réponse : l'edge survit-il aux coûts réels ?
        Usage : /friction [limit]
        """
        if self._kill_switch.engaged:
            return "⛔ Kill switch actif."

        try:
            limit = min(int(arg), 1000) if arg else 500
        except ValueError:
            limit = 500

        datasets = [
            ("BTC 4h", "BTCUSDT", "4h"),
            ("ETH 4h", "ETHUSDT", "4h"),
            ("SOL 1h", "SOLUSDT", "1h"),
        ]

        friction_levels = [
            ("Clean", ENLConfig.clean()),
            ("Light", ENLConfig.light()),
            ("Realistic", ENLConfig.realistic()),
            ("Heavy", ENLConfig.heavy()),
        ]

        def _run_level(candles, config) -> float:
            feeds = sliding_windows(candles, window=120, step=15)
            if not feeds:
                return 0.0
            exps = []
            for feed in feeds:
                feed.reset()
                portfolio = PortfolioState(balance=self._balance)
                exchange = VirtualExchange(portfolio)
                noisy = NoisyExchange(exchange, config)
                router = ExecutionRouter(noisy)
                agent = CodexAgent(RSIStrategy(14, 30, 70), self._kill_switch)
                ctx = RunContext(strategy_id="RSI_FRICTION")
                r = BacktestEngine(agent, router, feed, portfolio, ctx).run()
                t = r["total_trades"]
                exps.append(r["total_pnl"] / t if t > 0 else 0.0)
            return sum(exps) / len(exps) if exps else 0.0

        lines = [
            "🔬 *Friction test RSI 14*\n",
            f"{'Dataset':<10} {'Clean':>8} {'Light':>8} {'Real':>8} {'Heavy':>8}",
            f"{'-'*46}",
        ]

        all_survive = True
        for label, symbol, interval in datasets:
            try:
                candles = fetch_mexc_candles(symbol, interval, limit)
            except Exception as exc:
                lines.append(f"{label:<10} erreur: {exc}")
                continue

            results = [_run_level(candles, cfg) for _, cfg in friction_levels]
            survive = results[-1] > 0  # survit à Heavy ?
            if not survive:
                all_survive = False

            emoji = "✅" if survive else "❌"
            row = f"{label:<10}"
            for v in results:
                s = "+" if v >= 0 else ""
                row += f" {s}{v:>7.3f}"
            lines.append(f"{emoji} {row}")

        lines.append("")
        if all_survive:
            lines.append("✅ Edge survit à la friction heavy sur tous les datasets.")
        else:
            lines.append("⚠️ Edge disparait sous friction heavy sur certains datasets.")

        result_text = "\n".join(lines)
        # Résumé vers @mon_portfolio_bot
        self._notifier.info(
            f"Friction test terminé — survie heavy: {'OUI' if all_survive else 'NON'}"
        )
        return result_text

    def _cmd_score(self, arg: str) -> str:
        """
        Edge Scoring System — viabilité microstructurelle d'une stratégie.
        Matrice 3 datasets x 4 frictions. Score 0-12. Verdict VIABLE/MARGINAL/DEAD.
        Usage : /score [rsi|sma|breakout|all] [limit]
        """
        if self._kill_switch.engaged:
            return "⛔ Kill switch actif."

        parts = (arg or "rsi").lower().split()
        strategy_name = parts[0]
        try:
            limit = int(parts[1]) if len(parts) > 1 else 500
        except ValueError:
            limit = 500

        factories = {
            "rsi": ("RSI 14", lambda: RSIStrategy(14, 30, 70)),
            "sma": ("SMA 3/10", lambda: SMAStrategy(3, 10)),
            "breakout": ("Breakout 20", lambda: BreakoutStrategy(20)),
            "momentum": (
                "Momentum 30/3",
                lambda: MomentumStrategy(period=30, threshold=0.03),
            ),
            "mom20": (
                "Momentum 20/2",
                lambda: MomentumStrategy(period=20, threshold=0.02),
            ),
            "mom50": (
                "Momentum 50/5",
                lambda: MomentumStrategy(period=50, threshold=0.05),
            ),
            "rsi_ext": (
                "RSI 10/90 T50",
                lambda: RSIExtremeStrategy(14, 10, 90, trend_period=50),
            ),
            "rsi_ext2": (
                "RSI 5/95 T50",
                lambda: RSIExtremeStrategy(14, 5, 95, trend_period=50),
            ),
            "rsi_ext3": (
                "RSI 10/90 T20",
                lambda: RSIExtremeStrategy(14, 10, 90, trend_period=20),
            ),
            "rsi_x15": ("RSI 15/85", lambda: RSIExtremeStrategy(14, 15, 85)),
            "rsi_x20": ("RSI 20/80", lambda: RSIExtremeStrategy(14, 20, 80)),
            "rsi_x25": ("RSI 25/75", lambda: RSIExtremeStrategy(14, 25, 75)),
            "rsi_x20t": (
                "RSI 20/80+trend",
                lambda: RSIExtremeStrategy(14, 20, 80, use_trend_filter=True),
            ),
        }

        to_score = (
            factories
            if strategy_name == "all"
            else {strategy_name: factories.get(strategy_name)}
        )

        if None in to_score.values():
            return f"Stratégie inconnue : `{strategy_name}`\nChoix : rsi | sma | breakout | all"

        # Charger les candles une seule fois
        datasets = [
            ("BTC 4h", "BTCUSDT", "4h"),
            ("ETH 4h", "ETHUSDT", "4h"),
            ("SOL 1h", "SOLUSDT", "1h"),
        ]
        candles_map = {}
        for ds_label, symbol, interval in datasets:
            try:
                candles_map[ds_label] = fetch_mexc_candles(symbol, interval, limit)
            except Exception as exc:
                return f"❌ Erreur MEXC ({symbol}): {exc}"

        scorer = EdgeScorer()
        lines = []

        for key, (label, factory) in to_score.items():
            result = scorer.score(factory, candles_map, strategy_id=label)

            verdict_emoji = {"VIABLE": "✅", "MARGINAL": "⚠️", "DEAD": "❌"}[
                result["verdict"]
            ]
            sign = "+" if result["clean_avg"] >= 0 else ""
            be = result["breakeven"] or "aucun"
            sr = result["edge_survival_ratio"]
            if sr is None:
                sr_str = "N/A (clean négatif)"
            else:
                sr_str = f"{sr:+.2f}"

            lines.append(
                f"{verdict_emoji} *{label}* — Score {result['score']}/{result['total']} ({result['verdict']})\n"
                f"  Clean avg exp    : {sign}{result['clean_avg']:.3f}\n"
                f"  Edge buffer      : {result['edge_buffer']:+.3f}\n"
                f"  Survival ratio   : {sr_str}  (realistic/clean)\n"
                f"  Break-even       : {be}\n"
            )

            # Matrice compacte
            header = f"  {'':12} {'C':>7} {'L':>7} {'R':>7} {'H':>7}"
            lines.append(header)
            for ds, vals in result["matrix"].items():
                row = f"  {ds:<12}"
                for lvl in ("clean", "light", "realistic", "heavy"):
                    v = vals.get(lvl, 0.0)
                    s = "+" if v >= 0 else ""
                    row += f" {s}{v:>6.2f}"
                lines.append(row)
            lines.append("")

        return "\n".join(lines)

    def _cmd_distrib(self, arg: str) -> str:
        """
        Distribution des PnL par trade — RSI 14 sur 3 datasets forts.
        Répond à : est-ce que 80% du profit vient de 10% des trades ?
        Usage : /distrib [btc4h|eth4h|sol1h|all]
        """
        if self._kill_switch.engaged:
            return "⛔ Kill switch actif."

        target = arg.lower().strip() if arg else "all"

        datasets = {
            "btc4h": ("BTCUSDT", "4h"),
            "eth4h": ("ETHUSDT", "4h"),
            "sol1h": ("SOLUSDT", "1h"),
        }

        if target != "all" and target not in datasets:
            return f"Choix : btc4h | eth4h | sol1h | all"

        to_run = {target: datasets[target]} if target != "all" else datasets

        def _collect_trades(symbol, interval) -> list[float]:
            try:
                candles = fetch_mexc_candles(symbol, interval, 1000)
            except Exception as exc:
                return []
            feeds = sliding_windows(candles, window=120, step=15)
            all_pnls = []
            for feed in feeds:
                feed.reset()
                portfolio = PortfolioState(balance=self._balance)
                exchange = VirtualExchange(portfolio)
                router = ExecutionRouter(exchange)
                agent = CodexAgent(RSIStrategy(14, 30, 70), self._kill_switch)
                ctx = RunContext(strategy_id="RSI_DISTRIB")
                r = BacktestEngine(agent, router, feed, portfolio, ctx).run()
                all_pnls.extend(t.net_pnl_usd for t in r["trades"])
            return all_pnls

        def _analyze(pnls: list[float], label: str) -> str:
            if not pnls:
                return f"*{label}* : aucun trade."
            n = len(pnls)
            wins = sorted([p for p in pnls if p > 0], reverse=True)
            losses = sorted([p for p in pnls if p <= 0])
            total_pnl = sum(pnls)
            total_gain = sum(wins) if wins else 0.0
            wr = len(wins) / n

            # Concentration : top 10% et top 25% trades
            top10_n = max(1, int(n * 0.10))
            top25_n = max(1, int(n * 0.25))
            top10_pnl = sum(wins[:top10_n])
            top25_pnl = sum(wins[:top25_n])
            top10_pct = top10_pnl / total_gain * 100 if total_gain > 0 else 0
            top25_pct = top25_pnl / total_gain * 100 if total_gain > 0 else 0

            # Percentiles des PnL
            sorted_pnls = sorted(pnls)

            def _pct(p):
                return sorted_pnls[int(n * p / 100)]

            avg_win = sum(wins) / len(wins) if wins else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            wl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

            structure = "fat tail" if top10_pct > 60 else "distribue"

            return (
                f"*{label}* — {n} trades | {structure}\n"
                f"  WR: {wr:.0%} | Avg win: {avg_win:+.2f} | Avg loss: {avg_loss:+.2f} | W/L: {wl_ratio:.2f}\n"
                f"  Total PnL: {total_pnl:+.2f}\n"
                f"  Top 10% trades ({top10_n}t) = {top10_pct:.0f}% du gain total\n"
                f"  Top 25% trades ({top25_n}t) = {top25_pct:.0f}% du gain total\n"
                f"  P10:{_pct(10):+.2f} P25:{_pct(25):+.2f} P50:{_pct(50):+.2f} "
                f"P75:{_pct(75):+.2f} P90:{_pct(90):+.2f}"
            )

        lines = ["📈 *Distribution PnL par trade — RSI 14*\n"]
        all_pnls_combined = []

        for key, (symbol, interval) in to_run.items():
            label = key.upper()
            pnls = _collect_trades(symbol, interval)
            all_pnls_combined.extend(pnls)
            lines.append(_analyze(pnls, label))

        if target == "all" and all_pnls_combined:
            lines.append(_analyze(all_pnls_combined, "GLOBAL"))

        return "\n".join(lines)

    def _cmd_robust(self, arg: str) -> str:
        """
        Test de robustesse walk-forward sur 4 datasets.
        Usage : /robust [strategy] [limit]
          strategy : rsi (défaut) | rsi_x15 | rsi_x20 | rsi_x25 | sma | breakout
          limit    : nombre de candles (défaut 500, max 1000)
        """
        if self._kill_switch.engaged:
            return "⛔ Kill switch actif."

        parts = (arg or "").lower().split()
        # Détecter si le premier arg est une stratégie ou un nombre
        strategy_name = "rsi"
        limit = 500
        for part in parts:
            if part.isdigit():
                limit = min(int(part), 1000)
            elif part in (
                "rsi",
                "rsi_x15",
                "rsi_x20",
                "rsi_x25",
                "sma",
                "breakout",
                "momentum",
                "rsi_ext",
                "rsi_x20t",
            ):
                strategy_name = part

        _robust_factories = {
            "rsi": ("RSI 14", lambda: RSIStrategy(14, 30, 70)),
            "rsi_x15": ("RSI 15/85", lambda: RSIExtremeStrategy(14, 15, 85)),
            "rsi_x20": ("RSI 20/80", lambda: RSIExtremeStrategy(14, 20, 80)),
            "rsi_x25": ("RSI 25/75", lambda: RSIExtremeStrategy(14, 25, 75)),
            "sma": ("SMA 3/10", lambda: SMAStrategy(3, 10)),
            "breakout": ("Breakout 20", lambda: BreakoutStrategy(20)),
            "momentum": ("Momentum 30", lambda: MomentumStrategy(30, 0.03)),
        }

        if strategy_name not in _robust_factories:
            return f"Stratégie inconnue : {strategy_name}\nChoix : " + " | ".join(
                _robust_factories
            )

        strat_label, strat_factory = _robust_factories[strategy_name]

        datasets = [
            ("BTC 4h", "BTCUSDT", "4h"),
            ("ETH 4h", "ETHUSDT", "4h"),
            ("ETH 1h", "ETHUSDT", "1h"),
            ("SOL 1h", "SOLUSDT", "1h"),
        ]

        import math

        def _run_strategy(feed) -> float:
            feed.reset()
            portfolio = PortfolioState(balance=self._balance)
            exchange = VirtualExchange(portfolio)
            router = ExecutionRouter(exchange)
            agent = CodexAgent(strat_factory(), self._kill_switch)
            ctx = RunContext(strategy_id=strat_label)
            r = BacktestEngine(agent, router, feed, portfolio, ctx).run()
            t = r["total_trades"]
            return r["total_pnl"] / t if t > 0 else 0.0

        all_folds: list[float] = []
        lines = [f"🔬 *Robustesse {strat_label} — walk-forward*\n"]

        for label, symbol, interval in datasets:
            try:
                candles = fetch_mexc_candles(symbol, interval, limit)
            except Exception as exc:
                lines.append(f"{label} : erreur MEXC ({exc})")
                continue

            feeds = sliding_windows(candles, window=120, step=15)
            if len(feeds) < 3:
                lines.append(f"{label} : pas assez de candles")
                continue

            folds = [_run_strategy(f) for f in feeds]
            avg = sum(folds) / len(folds)
            pos = sum(1 for x in folds if x > 0)
            variance = sum((x - avg) ** 2 for x in folds) / len(folds)
            std = math.sqrt(variance)

            # Résumé compact des folds (arrondi)
            fold_str = " ".join(f"{'+'if x>=0 else ''}{x:.2f}" for x in folds[:8])
            if len(folds) > 8:
                fold_str += f" …(+{len(folds)-8})"

            verdict = (
                "✅ stable"
                if std < abs(avg) * 0.5 and avg > 0
                else "⚠️ instable" if avg > 0 else "❌ négatif"
            )

            lines.append(
                f"*{label}* ({len(folds)} folds) {verdict}\n"
                f"  Avg exp: {avg:+.3f} | Std: {std:.3f} | Pos: {pos}/{len(folds)}\n"
                f"  Folds: {fold_str}"
            )
            all_folds.extend(folds)

        if all_folds:
            global_avg = sum(all_folds) / len(all_folds)
            global_pos = sum(1 for x in all_folds if x > 0)
            global_std = math.sqrt(
                sum((x - global_avg) ** 2 for x in all_folds) / len(all_folds)
            )
            sign = "+" if global_avg >= 0 else ""
            lines.append(
                f"\n*Global — {len(all_folds)} folds*\n"
                f"  Avg exp  : {sign}{global_avg:.3f}\n"
                f"  Std      : {global_std:.3f}\n"
                f"  Folds >0 : {global_pos}/{len(all_folds)}\n"
                f"  Ratio    : {global_pos/len(all_folds):.0%}"
            )
            self._notifier.robust_completed(
                len(all_folds), global_avg, global_pos / len(all_folds)
            )

        return "\n".join(lines)

    def _cmd_race(self, arg: str) -> str:
        """
        3 familles, mêmes données, tableau comparatif.
        Usage : /race [btc|eth|sol|xrp] [1h|4h] [limit]
        A = SMA 3/10 (trend following)
        B = RSI 14 (mean reversion)
        C = Breakout 20 (breakout)
        """
        if self._kill_switch.engaged:
            return "⛔ Kill switch actif."

        parts = arg.lower().split() if arg else []
        sym_key = parts[0] if parts else "btc"
        interval = parts[1] if len(parts) > 1 else "1h"
        try:
            limit = int(parts[2]) if len(parts) > 2 else 500
        except ValueError:
            limit = 500

        symbol = _LIVE_SYMBOLS.get(sym_key)
        if symbol is None:
            return f"Symbole inconnu : `{sym_key}`\nChoix : btc | eth | sol | xrp"

        try:
            candles = fetch_mexc_candles(symbol, interval, min(limit, 1000))
        except Exception as exc:
            return f"❌ Erreur MEXC : {exc}"

        feeds = sliding_windows(candles, window=120, step=15)
        if len(feeds) < 5:
            return f"Pas assez de candles ({len(candles)} reçues, besoin de 120+)."

        families = [
            ("SMA 3/10", lambda: SMAStrategy(3, 10)),
            ("RSI 14", lambda: RSIStrategy(14, 30, 70)),
            ("Breakout 20", lambda: BreakoutStrategy(20)),
        ]

        def _run_family(make_strategy) -> list[dict]:
            results = []
            for feed in feeds:
                feed.reset()
                portfolio = PortfolioState(balance=self._balance)
                exchange = VirtualExchange(portfolio)
                router = ExecutionRouter(exchange)
                agent = CodexAgent(make_strategy(), self._kill_switch)
                ctx = RunContext(strategy_id="RACE")
                results.append(
                    BacktestEngine(agent, router, feed, portfolio, ctx).run()
                )
            return results

        def _agg(reports):
            n = len(reports)
            pnls = [r["total_pnl"] for r in reports]
            trades = [r["total_trades"] for r in reports]
            dds = [r["max_drawdown"] for r in reports]
            gains = sum(p for p in pnls if p > 0)
            losses = abs(sum(p for p in pnls if p < 0))
            pf = gains / losses if losses > 0 else (float("inf") if gains > 0 else 0.0)
            avg_t = sum(trades) / n if n else 1
            exp = (sum(pnls) / n) / avg_t if avg_t > 0 else 0.0
            return {
                "avg_pnl": round(sum(pnls) / n, 2),
                "pf": round(pf, 2),
                "avg_dd": round(sum(dds) / n, 4),
                "expectancy": round(exp, 3),
                "trades": sum(trades),
            }

        rows = []
        for name, make_fn in families:
            agg = _agg(_run_family(make_fn))
            rows.append((name, agg))

        n_w = len(feeds)
        lines = [
            f"🏁 *Race 3 familles — {symbol} {interval}*",
            f"{n_w} fenêtres × 120 candles\n",
            f"```",
            f"{'Stratégie':<14} {'Exp':>7} {'PnL':>8} {'PF':>6} {'DD':>7} {'T':>5}",
            f"{'-'*47}",
        ]
        for name, a in rows:
            sign = "+" if a["avg_pnl"] >= 0 else ""
            lines.append(
                f"{name:<14} {a['expectancy']:>+7.3f} "
                f"{sign}{a['avg_pnl']:>7.2f}$ "
                f"{a['pf']:>6.2f} "
                f"{a['avg_dd']:>6.2%} "
                f"{a['trades']:>5d}"
            )
        lines.append("```")

        # Gagnant par expectancy
        best = max(rows, key=lambda x: x[1]["expectancy"])
        sign_b = "+" if best[1]["expectancy"] >= 0 else ""
        lines.append(
            f"\nMeilleure expectancy : {best[0]} ({sign_b}{best[1]['expectancy']:.3f})"
        )
        self._notifier.race_completed(symbol, interval, best[0], best[1]["expectancy"])
        return "\n".join(lines)

    def _cmd_validate(self, arg: str) -> str:
        """
        Walk-forward A/B sur données MEXC réelles.
        Usage : /validate [btc|eth|sol|xrp] [1h|4h] [limit]
        Découpe l'historique en fenêtres glissantes de 120 candles.
        """
        if self._kill_switch.engaged:
            return "⛔ Kill switch actif."

        parts = arg.lower().split() if arg else []
        sym_key = parts[0] if len(parts) > 0 else "btc"
        interval = parts[1] if len(parts) > 1 else "1h"
        try:
            limit = int(parts[2]) if len(parts) > 2 else 500
        except ValueError:
            limit = 500

        symbol = _LIVE_SYMBOLS.get(sym_key)
        if symbol is None:
            return f"Symbole inconnu : `{sym_key}`\nChoix : btc | eth | sol | xrp"

        try:
            candles = fetch_mexc_candles(symbol, interval, min(limit, 1000))
        except Exception as exc:
            return f"❌ Erreur MEXC : {exc}"

        feeds = sliding_windows(candles, window=120, step=15)
        n_windows = len(feeds)

        if n_windows < 5:
            return f"Pas assez de candles pour valider ({len(candles)} reçues, besoin de 120+)."

        from src.analytics.regime_detector import RegimeDetector

        detector = RegimeDetector()

        results_a, results_b = [], []
        regime_counts: dict[str, int] = {}

        for feed in feeds:
            regime = detector.classify(feed.candles)
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

            def _run(use_gate: bool, f=feed) -> dict:
                f.reset()
                portfolio = PortfolioState(balance=self._balance)
                exchange = VirtualExchange(portfolio)
                router = ExecutionRouter(exchange)
                base = CodexAgent(SMAStrategy(3, 10), self._kill_switch)
                agent = (
                    RegimeGate(base, allowed_regimes={"sideways"}, detector=detector)
                    if use_gate
                    else base
                )
                ctx = RunContext(strategy_id="SMA_B_GATE" if use_gate else "SMA_A_RAW")
                return BacktestEngine(agent, router, feed, portfolio, ctx).run()

            results_a.append(_run(use_gate=False))
            results_b.append(_run(use_gate=True))

        def _agg(reports):
            n = len(reports)
            pnls = [r["total_pnl"] for r in reports]
            trades = [r["total_trades"] for r in reports]
            dds = [r["max_drawdown"] for r in reports]
            gains = sum(p for p in pnls if p > 0)
            losses = abs(sum(p for p in pnls if p < 0))
            pf = gains / losses if losses > 0 else (float("inf") if gains > 0 else 0.0)
            avg_t = sum(trades) / n if n > 0 else 1
            exp = (sum(pnls) / n) / avg_t if avg_t > 0 else 0.0
            return {
                "avg_pnl": round(sum(pnls) / n, 2),
                "pf": round(pf, 2),
                "avg_dd": round(sum(dds) / n, 4),
                "expectancy": round(exp, 3),
                "trades": sum(trades),
            }

        a = _agg(results_a)
        b = _agg(results_b)

        dist = "  ".join(
            f"{'📈' if k=='trend' else '↔️' if k=='range' else '⚡'}{k[0].upper()}:{v}"
            for k, v in sorted(regime_counts.items())
        )
        delta_exp = b["expectancy"] - a["expectancy"]
        sign_d = "+" if delta_exp >= 0 else ""

        def _sign(v):
            return "+" if v >= 0 else ""

        return (
            f"🔬 *Validation walk-forward — {symbol} {interval}*\n"
            f"{n_windows} fenêtres × 120 candles | {len(candles)} candles totales\n"
            f"Régimes : {dist}\n\n"
            f"```\n"
            f"                  A (brute)    B (filtre range)\n"
            f"Avg PnL    {_sign(a['avg_pnl'])}{a['avg_pnl']:>8.2f}$   {_sign(b['avg_pnl'])}{b['avg_pnl']:>8.2f}$\n"
            f"Expectancy {_sign(a['expectancy'])}{a['expectancy']:>8.3f}    {_sign(b['expectancy'])}{b['expectancy']:>8.3f}   ({sign_d}{delta_exp:.3f})\n"
            f"Prof. Fact {a['pf']:>8.2f}   {b['pf']:>8.2f}\n"
            f"Avg DD     {a['avg_dd']:>8.2%}   {b['avg_dd']:>8.2%}\n"
            f"Trades     {a['trades']:>8d}   {b['trades']:>8d}\n"
            f"```\n"
            f"_Delta expectancy B-A : {sign_d}{delta_exp:.3f}_"
        )

    def _cmd_overall(self, _: str) -> str:
        total = self._repo.count()
        if total == 0:
            return "Aucun run en base. Tape /stress 100 pour commencer."

        runs = self._repo.last_runs(n=10000)
        from src.analytics.performance_breakdown import breakdown as _bd

        bd = _bd(runs)
        a = bd["all"]
        dist = self._repo.regime_distribution()

        sign = "+" if a["avg_pnl"] >= 0 else ""
        dist_str = "  ".join(
            f"{'📈' if k=='trend' else '↔️' if k=='range' else '⚡'}{k[0].upper()}:{v}"
            for k, v in dist.items()
        )
        return (
            f"🔬 *Vue globale — {total} runs*\n\n"
            f"Distribution  : {dist_str}\n\n"
            f"Avg PnL       : {sign}{a['avg_pnl']:.2f} USD\n"
            f"Profit Factor : {a['profit_factor']:.2f}\n"
            f"Expectancy    : {a['expectancy']:.3f} USD/trade\n"
            f"Win Rate      : {a['avg_win_rate']:.0%}\n"
            f"Avg Drawdown  : {a['avg_drawdown']:.2%}\n"
            f"Total trades  : {a['total_trades']}\n\n"
            f"_/breakdown pour le détail par régime_"
        )

    def _cmd_breakdown(self, arg: str) -> str:
        regime_filter = arg.lower().strip() if arg else None
        valid = {"trending", "sideways", "volatile"}

        if regime_filter and regime_filter not in valid:
            return f"Régime inconnu : `{regime_filter}`\nChoix : trending | sideways | volatile"

        if regime_filter:
            runs = self._repo.runs_by_regime(regime_filter)
            label = regime_filter
        else:
            runs = self._repo.last_runs(n=10000)
            label = "global"

        total_db = self._repo.count()
        dist = self._repo.regime_distribution()

        if not runs:
            return f"Aucun run pour le régime `{label}` en base."

        from src.analytics.performance_breakdown import breakdown as _bd

        bd = _bd(runs)

        def _fmt(s: dict, lbl: str, em: str) -> str:
            if s["n_runs"] == 0:
                return f"  {em} {lbl}: 0 runs"
            sign = "+" if s["avg_pnl"] >= 0 else ""
            esign = "+" if s["expectancy"] >= 0 else ""
            return (
                f"  {em} {lbl} ({s['n_runs']}r)\n"
                f"    PnL {sign}{s['avg_pnl']:.2f}$ | WR {s['avg_win_rate']:.0%} "
                f"| PF {s['profit_factor']:.2f} | DD {s['avg_drawdown']:.2%}\n"
                f"    Expectancy {esign}{s['expectancy']:.3f} $/trade"
            )

        dist_str = " | ".join(f"{k}:{v}" for k, v in dist.items())
        return (
            f"📊 *Performance breakdown — DB ({total_db} runs)*\n"
            f"Distribution : {dist_str}\n\n"
            + _fmt(bd["trending"], "trend", "📈")
            + "\n"
            + _fmt(bd["sideways"], "range", "↔️")
            + "\n"
            + _fmt(bd["volatile"], "volatile", "⚡")
            + "\n\n"
            + f"*Tous régimes*\n"
            + _fmt(bd["all"], "all", "🔬")
        )

    def _cmd_market(self, arg: str) -> str:
        sym_key = arg.lower().strip() if arg else "btc"
        symbol = _LIVE_SYMBOLS.get(sym_key)
        if symbol is None:
            return f"Symbole inconnu : `{sym_key}`\nChoix : btc | eth | sol | xrp"
        try:
            candles = fetch_mexc_candles(symbol, interval="1h", limit=5)
        except Exception as exc:
            return f"❌ Erreur MEXC : {exc}"

        if not candles:
            return "Aucune candle reçue."

        last = candles[-1]
        prev = candles[-2] if len(candles) >= 2 else last
        change = (last["close"] - prev["close"]) / prev["close"] * 100
        sign = "+" if change >= 0 else ""
        lines = [f"📈 *{symbol}* — dernières 5 candles 1h"]
        for c in candles:
            lines.append(f"`{c['close']:.4f}` vol={c['volume']:.0f}")
        lines.append(f"\nDernier : `{last['close']:.4f}` ({sign}{change:.2f}%)")
        return "\n".join(lines)

    def _cmd_kill(self, _: str) -> str:
        self._kill_switch.trigger("telegram /kill")
        return "⛔ Kill switch engagé. Aucun run possible jusqu'au /resume."

    def _cmd_resume(self, _: str) -> str:
        self._kill_switch.release()
        return "✅ Kill switch relâché. Le simulateur peut reprendre."


# ------------------------------------------------------------------ #
# Générateur de candles synthétiques                                   #
# ------------------------------------------------------------------ #


def _synthetic_candles(n: int = 120, seed: int = 42) -> list[dict]:
    import math

    candles = []
    price = 100.0
    for i in range(n):
        noise = math.sin(i * 0.3 + seed) * 0.8 + math.cos(i * 0.1) * 0.4
        price = max(1.0, price + noise + 0.05)
        candles.append(
            {
                "timestamp": i,
                "symbol": "BTC",
                "open": round(price - 0.1, 4),
                "high": round(price + 0.3, 4),
                "low": round(price - 0.3, 4),
                "close": round(price, 4),
                "volume": 1000.0 + (i % 10) * 50,
            }
        )
    return candles
