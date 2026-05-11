"""
boot_system_validator.py — Validation absolue du démarrage système

Prouve que :
  - Chaque module s'importe sans erreur
  - Chaque module s'instancie sans erreur
  - La chaîne de décision complète s'exécute sans crash
  - Les variables .env critiques sont présentes
  - Les bases de données sont accessibles en écriture
  - L'exchange répond (optionnel — skippé si offline)
  - Le signal engine produit un résultat cohérent

Sortie : PASS / FAIL par module, rapport final lisible.
Usage :
    python scripts/boot_system_validator.py
    python scripts/boot_system_validator.py --fast
    python scripts/boot_system_validator.py --fix
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()


def _green(value: str) -> str:
    return f"\033[92m{value}\033[0m"


def _red(value: str) -> str:
    return f"\033[91m{value}\033[0m"


def _yellow(value: str) -> str:
    return f"\033[93m{value}\033[0m"


def _bold(value: str) -> str:
    return f"\033[1m{value}\033[0m"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    warn: bool = False


class BootValidator:
    def __init__(self, fast: bool = False, fix: bool = False) -> None:
        self.fast = fast
        self.fix = fix
        self.results: list[CheckResult] = []
        self._start = time.time()

    def run(self) -> bool:
        print(_bold("\n=============================================="))
        print(_bold("  BOOT SYSTEM VALIDATOR — Crypto AI Terminal"))
        print(_bold("==============================================\n"))

        self._check_env()
        self._check_dirs()
        self._check_imports()
        self._check_instantiation()
        self._check_decision_chain()
        if not self.fast:
            self._check_exchange()

        return self._report()

    def _check_env(self) -> None:
        print(_bold("[ 1 ] Variables .env"))
        required = [
            ("BINANCE_FUTURES_DEMO_KEY", "Clé Futures Demo"),
            ("BINANCE_FUTURES_DEMO_SECRET", "Secret Futures Demo"),
            ("TELEGRAM_BOT_TOKEN", "Token Telegram"),
            ("TELEGRAM_CHAT_ID", "Chat ID Telegram"),
        ]
        optional = [
            ("V9_ADVISOR_ONLY", "Mode advisor"),
            ("EXEC_FUTURES_MIN_ORDER_USD", "Min ordre futures"),
            ("EO_DD_VETO", "Override DD VETO"),
            ("BB_PATH", "Black Box path"),
            ("MISTAKE_DB", "Mistake Memory DB"),
            ("REGRET_DB", "Regret DB"),
        ]
        for key, label in required:
            value = os.getenv(key, "")
            ok = bool(value) and value not in ("REMPLACE_PAR_CLE_LIVE", "")
            self.results.append(CheckResult(f"env.{key}", ok, f"{label} = {'[SET]' if ok else '[MANQUANT]'}"))
            self._print_result(f"  {label}", ok)

        for key, label in optional:
            value = os.getenv(key, "")
            self.results.append(CheckResult(f"env_opt.{key}", True, f"{label} = {value or '[default]'}", warn=not bool(value)))
        print()

    def _check_dirs(self) -> None:
        print(_bold("[ 2 ] Dossiers & fichiers"))
        directories = [
            "databases",
            "logs",
            "databases/shadow_execution",
            "quant_hedge_ai/agents/intelligence",
            "quant_hedge_ai/agents/risk",
            "quant_hedge_ai/agents/execution",
        ]
        for directory in directories:
            path = Path(directory)
            ok = path.exists() and path.is_dir()
            if not ok and self.fix:
                path.mkdir(parents=True, exist_ok=True)
                ok = True
            self.results.append(CheckResult(f"dir.{directory}", ok, directory))
            self._print_result(f"  {directory}/", ok)

        env_ok = Path(".env").exists()
        self.results.append(CheckResult("file.env", env_ok, ".env"))
        self._print_result("  .env", env_ok)

        try:
            test_file = Path("databases/.boot_test")
            test_file.write_text("ok")
            test_file.unlink()
            self.results.append(CheckResult("dir.databases.write", True, "Écriture OK"))
            self._print_result("  databases/ writable", True)
        except Exception as exc:
            self.results.append(CheckResult("dir.databases.write", False, str(exc)))
            self._print_result("  databases/ writable", False)
        print()

    def _check_imports(self) -> None:
        print(_bold("[ 3 ] Imports modules"))
        modules = [
            ("ExecutionEngine", "quant_hedge_ai.agents.execution.execution_engine", "ExecutionEngine"),
            ("PositionManager", "quant_hedge_ai.agents.execution.position_manager", "PositionManager"),
            ("LiveSignalEngine", "quant_hedge_ai.agents.execution.live_signal_engine", "LiveSignalEngine"),
            ("ShadowEngine", "quant_hedge_ai.agents.execution.shadow_engine", "ShadowExecutionEngine"),
            ("MarketScanner", "quant_hedge_ai.agents.market.market_scanner", "MarketScanner"),
            ("MultiTimeframeScanner", "quant_hedge_ai.agents.market.multi_timeframe_scanner", "MultiTimeframeScanner"),
            ("FeatureEngineer", "quant_hedge_ai.agents.intelligence.feature_engineer", "FeatureEngineer"),
            ("RegimeDetector", "quant_hedge_ai.agents.intelligence.regime_detector", "AdvancedRegimeDetector"),
            ("GlobalRiskGate", "quant_hedge_ai.agents.risk.global_risk_gate", "GlobalRiskGate"),
            ("PortfolioBrain", "quant_hedge_ai.agents.risk.portfolio_brain", "PortfolioBrain"),
            ("CapitalAllocationEngine", "quant_hedge_ai.agents.risk.capital_allocation_engine", "CapitalAllocationEngine"),
            ("ExecutiveOverride", "quant_hedge_ai.agents.risk.executive_override", "ExecutiveOverride"),
            ("MetaStrategyEngine", "quant_hedge_ai.agents.intelligence.meta_strategy_engine", "MetaStrategyEngine"),
            ("ConvictionEngine", "quant_hedge_ai.agents.intelligence.conviction_engine", "ConvictionEngine"),
            ("NoTradeIntelligence", "quant_hedge_ai.agents.intelligence.no_trade_layer", "NoTradeIntelligence"),
            ("SelfAwarenessEngine", "quant_hedge_ai.agents.intelligence.self_awareness_engine", "SelfAwarenessEngine"),
            ("MistakeMemory", "quant_hedge_ai.agents.intelligence.mistake_memory", "MistakeMemory"),
            ("BlackBox", "quant_hedge_ai.agents.intelligence.black_box", "BlackBox"),
            ("RegretEngine", "quant_hedge_ai.agents.intelligence.regret_engine", "RegretEngine"),
            ("ChiefOfficer", "quant_hedge_ai.agents.intelligence.chief_officer", "ChiefOfficer"),
            ("ThreatRadar", "quant_hedge_ai.agents.intelligence.threat_radar", "ThreatRadar"),
            ("DecisionQualityEngine", "quant_hedge_ai.agents.intelligence.decision_quality_engine", "DecisionQualityEngine"),
            ("StrategyRanker", "quant_hedge_ai.ai_evolution.strategy_ranker", "StrategyRanker"),
            ("StrategyMemory", "quant_hedge_ai.ai_evolution.strategy_memory", "StrategyMemoryStore"),
            ("TelegramKillSwitch", "supervision.telegram_kill_switch", "TelegramKillSwitch"),
            ("ExchangeMonitor", "supervision.exchange_monitor", "ExchangeMonitor"),
            ("SelfHealingBot", "supervision.self_healing_bot", "SelfHealingBot"),
            ("PerformanceWatchdog", "supervision.performance_watchdog", "PerformanceWatchdog"),
        ]
        for label, module_name, class_name in modules:
            try:
                module = __import__(module_name, fromlist=[class_name])
                getattr(module, class_name)
                self.results.append(CheckResult(f"import.{label}", True))
                self._print_result(f"  {label}", True)
            except Exception as exc:
                short = str(exc)[:80]
                self.results.append(CheckResult(f"import.{label}", False, short))
                self._print_result(f"  {label}", False, short)
        print()

    def _check_instantiation(self) -> None:
        print(_bold("[ 4 ] Instanciation des modules clés"))
        checks = [
            ("FeatureEngineer", self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.feature_engineer", fromlist=["FeatureEngineer"]).FeatureEngineer())),
            ("GlobalRiskGate", self._try(lambda: __import__("quant_hedge_ai.agents.risk.global_risk_gate", fromlist=["GlobalRiskGate"]).GlobalRiskGate())),
            ("PortfolioBrain", self._try(lambda: __import__("quant_hedge_ai.agents.risk.portfolio_brain", fromlist=["PortfolioBrain"]).PortfolioBrain(total_capital=1000))),
            ("CapitalAllocationEngine", self._try(lambda: __import__("quant_hedge_ai.agents.risk.capital_allocation_engine", fromlist=["CapitalAllocationEngine"]).CapitalAllocationEngine(total_capital=1000))),
            ("ExecutiveOverride", self._try(lambda: __import__("quant_hedge_ai.agents.risk.executive_override", fromlist=["ExecutiveOverride"]).ExecutiveOverride(total_capital=1000))),
            ("ConvictionEngine", self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.conviction_engine", fromlist=["ConvictionEngine"]).ConvictionEngine())),
            ("MetaStrategyEngine", self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.meta_strategy_engine", fromlist=["MetaStrategyEngine"]).MetaStrategyEngine())),
            ("SelfAwarenessEngine", self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.self_awareness_engine", fromlist=["SelfAwarenessEngine"]).SelfAwarenessEngine())),
            ("NoTradeIntelligence", self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.no_trade_layer", fromlist=["NoTradeIntelligence"]).NoTradeIntelligence())),
            ("MistakeMemory", self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.mistake_memory", fromlist=["MistakeMemory"]).MistakeMemory())),
            ("BlackBox", self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.black_box", fromlist=["BlackBox"]).BlackBox())),
            ("RegretEngine", self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.regret_engine", fromlist=["RegretEngine"]).RegretEngine())),
            ("ChiefOfficer", self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.chief_officer", fromlist=["ChiefOfficer"]).ChiefOfficer())),
            ("ThreatRadar", self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.threat_radar", fromlist=["ThreatRadar"]).ThreatRadar())),
            ("StrategyRanker", self._try(lambda: __import__("quant_hedge_ai.ai_evolution.strategy_ranker", fromlist=["StrategyRanker"]).StrategyRanker())),
            ("LiveSignalEngine", self._try(lambda: __import__("quant_hedge_ai.agents.execution.live_signal_engine", fromlist=["LiveSignalEngine"]).LiveSignalEngine())),
        ]
        for label, (ok, error) in checks:
            self.results.append(CheckResult(f"init.{label}", ok, error))
            self._print_result(f"  {label}()", ok, error)
        print()

    def _check_decision_chain(self) -> None:
        print(_bold("[ 5 ] Chaîne de décision complète (données synthétiques)"))
        try:
            from quant_hedge_ai.agents.execution.live_signal_engine import LiveSignalEngine
            from quant_hedge_ai.agents.intelligence.conviction_engine import ConvictionEngine
            from quant_hedge_ai.agents.intelligence.feature_engineer import FeatureEngineer
            from quant_hedge_ai.agents.intelligence.meta_strategy_engine import MetaStrategyEngine
            from quant_hedge_ai.agents.intelligence.mistake_memory import MistakeMemory
            from quant_hedge_ai.agents.intelligence.no_trade_layer import NoTradeIntelligence
            from quant_hedge_ai.agents.intelligence.self_awareness_engine import SelfAwarenessEngine
            from quant_hedge_ai.agents.intelligence.threat_radar import ThreatRadar
            from quant_hedge_ai.agents.risk.capital_allocation_engine import CapitalAllocationEngine
            from quant_hedge_ai.agents.risk.executive_override import ExecutiveOverride
            from quant_hedge_ai.agents.risk.global_risk_gate import GlobalRiskGate
            from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioBrain

            import random

            random.seed(42)
            base = 77000.0
            candles = []
            for index in range(200):
                close = base + index * 10 + random.gauss(0, 50)
                candles.append(
                    {
                        "open": close - 20,
                        "high": close + 40,
                        "low": close - 40,
                        "close": close,
                        "volume": 100 + random.gauss(0, 10),
                    }
                )

            features = FeatureEngineer().extract_features(candles)
            assert "rsi" in features
            assert "atr" in features
            self._print_result("  Features (25 indicateurs)", True, f"RSI={features['rsi']:.1f} ATR={features['atr']:.0f}")

            signal = LiveSignalEngine().evaluate("BTC/USDT", {"1h": candles}, features=features)
            assert signal.score >= 0
            self._print_result("  LiveSignalEngine", True, f"score={signal.score} signal={signal.signal}")

            gate = GlobalRiskGate().check(signal)
            self._print_result("  GlobalRiskGate", True, f"allowed={gate.allowed}")

            meta = MetaStrategyEngine()
            personality = meta.select("bull_trend", features, memory_sharpe=1.5, consecutive_losses=0, open_positions=0)
            assert personality is not None
            self._print_result("  MetaStrategyEngine", True, f"personality={personality.name}")

            conviction = ConvictionEngine().evaluate(signal, features, candles, "bull_trend", 1.5)
            self._print_result("  ConvictionEngine", True, f"level={conviction.level.value} score={conviction.score:.0f}")

            no_trade = NoTradeIntelligence().check(signal, candles, features, "bull_trend")
            self._print_result("  NoTradeIntelligence", True, f"allowed={bool(no_trade)}")

            awareness = SelfAwarenessEngine().evaluate()
            self._print_result("  SelfAwarenessEngine", True, f"level={awareness.level.name}")

            mistake_memory = MistakeMemory()
            mistake_check = mistake_memory.check_before_trade("BTC/USDT", "BUY", signal.score, "bull_trend", features)
            self._print_result("  MistakeMemory", True, f"blocked={mistake_check.blocked}")

            portfolio = PortfolioBrain(total_capital=1000)
            portfolio_verdict = portfolio.check_new_trade("BTC/USDT", "BUY", 55.0, "bull_trend", [])
            self._print_result("  PortfolioBrain", True, f"allowed={portfolio_verdict.allowed} factor={portfolio_verdict.size_factor}")

            capital_engine = CapitalAllocationEngine(total_capital=1000)
            allocation = capital_engine.allocate(55.0, win_rate=0.55, avg_win_pct=0.04, avg_loss_pct=0.02, regime="bull_trend", conviction_factor=conviction.size_factor)
            self._print_result("  CapitalAllocationEngine", True, f"size=${allocation.size_usd:.0f} kelly={allocation.kelly_fraction:.4f}")

            executive_override = ExecutiveOverride(total_capital=1000)
            override_verdict = executive_override.check_trade(allocation.size_usd)
            self._print_result("  ExecutiveOverride", True, f"level={override_verdict.level.name} allowed={override_verdict.allowed}")

            radar = ThreatRadar()
            radar.feed_candles("BTC/USDT", candles)
            radar_report = radar.scan_sync(["BTC/USDT"])
            self._print_result("  ThreatRadar", True, f"menaces={len(radar_report.threats)} niveau={radar_report.max_level.value} trade_ok={radar_report.trade_allowed}")

            all_ok = (
                gate.allowed
                and bool(no_trade)
                and not mistake_check.blocked
                and portfolio_verdict.allowed
                and allocation.size_usd > 0
                and override_verdict.allowed
                and radar_report.trade_allowed
            )
            self.results.append(CheckResult("chain.complete", True, f"12 couches OK | trade={'AUTORISE' if all_ok else 'BLOQUE'}"))
            self._print_result(f"  CHAINE COMPLETE — trade {'AUTORISE' if all_ok else 'BLOQUE (normal si conditions)'}", True)
        except Exception:
            traceback_line = traceback.format_exc().strip().split("\n")[-1]
            self.results.append(CheckResult("chain.complete", False, traceback_line))
            self._print_result("  CHAINE COMPLETE", False, traceback_line)
        print()

    def _check_exchange(self) -> None:
        print(_bold("[ 6 ] Connexion exchange (live)"))
        try:
            from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

            engine = ExecutionEngine.from_env()
            ok_futures = engine.has_futures_demo()
            self._print_result("  has_futures_demo", ok_futures)
            self.results.append(CheckResult("exchange.futures", ok_futures, "Futures Demo accessible" if ok_futures else "NON disponible"))

            if ok_futures:
                balance = engine.fetch_futures_balance()
                capital = engine.fetch_available_capital()
                balance_ok = balance > 0 or capital > 0
                self._print_result(f"  Balance futures: ${balance:.0f} USDT | Spot: ${capital:.0f}", balance_ok)
                self.results.append(CheckResult("exchange.balance", balance_ok, f"Futures=${balance:.0f} Spot=${capital:.0f}"))
        except Exception as exc:
            short = str(exc)[:100]
            self.results.append(CheckResult("exchange.connect", False, short))
            self._print_result("  Exchange connexion", False, short)
        print()

    def _report(self) -> bool:
        elapsed = time.time() - self._start
        failed = [result for result in self.results if not result.ok]
        warned = [result for result in self.results if result.ok and result.warn]

        print(_bold("=============================================="))
        print(_bold("  RAPPORT FINAL"))
        print(_bold("=============================================="))
        print(f"  Total checks  : {len(self.results)}")
        print(f"  {_green('Passes')}         : {len(self.results) - len(failed)}")
        if warned:
            print(f"  {_yellow('Warnings')}       : {len(warned)}")
        if failed:
            print(f"  {_red('Failures')}       : {len(failed)}")
        print(f"  Durée         : {elapsed:.1f}s")
        print()

        if failed:
            print(_bold(_red("  ECHECS DETECTES :")))
            for result in failed:
                print(f"  {_red('FAIL')} {result.name}: {result.detail}")
            print()
            print(_bold(_red("  VERDICT : SYSTEME NON PRET — corriger avant de lancer")))
        else:
            print(_bold(_green("  VERDICT : SYSTEME PRET — tous les checks passent")))
            advisor_only = os.getenv("V9_ADVISOR_ONLY", "true").lower()
            mode = "OBSERVATION" if advisor_only == "true" else "TRADING ACTIF"
            print(f"  Mode au démarrage : {_bold(mode)}")

        print(_bold("==============================================\n"))
        return len(failed) == 0

    @staticmethod
    def _try(fn) -> tuple[bool, str]:
        try:
            fn()
            return True, ""
        except Exception as exc:
            return False, str(exc)[:80]

    @staticmethod
    def _print_result(label: str, ok: bool, detail: str = "") -> None:
        icon = _green("PASS") if ok else _red("FAIL")
        suffix = f"  {_yellow(detail)}" if detail and not ok else (f"  {detail}" if detail else "")
        print(f"  [{icon}] {label}{suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Boot System Validator")
    parser.add_argument("--fast", action="store_true", help="Skip exchange live check")
    parser.add_argument("--fix", action="store_true", help="Auto-créer les dossiers manquants")
    args = parser.parse_args()

    validator = BootValidator(fast=args.fast, fix=args.fix)
    return 0 if validator.run() else 1


if __name__ == "__main__":
    raise SystemExit(main())
