"""
test_boot_system.py — Validation absolue du démarrage système

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
    python test_boot_system.py
    python test_boot_system.py --fast     # skip exchange live check
    python test_boot_system.py --fix      # tente de créer les dossiers manquants
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

# Charger .env avant tout
from dotenv import load_dotenv
load_dotenv()


# ── Couleurs terminal ─────────────────────────────────────────────────────────

def _green(s: str) -> str: return f"\033[92m{s}\033[0m"
def _red(s: str) -> str:   return f"\033[91m{s}\033[0m"
def _yellow(s: str) -> str: return f"\033[93m{s}\033[0m"
def _bold(s: str) -> str:  return f"\033[1m{s}\033[0m"


@dataclass
class CheckResult:
    name:    str
    ok:      bool
    detail:  str = ""
    warn:    bool = False


class BootValidator:

    def __init__(self, fast: bool = False, fix: bool = False) -> None:
        self.fast    = fast
        self.fix     = fix
        self.results: list[CheckResult] = []
        self._start  = time.time()

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

    # ── 1. Variables .env ─────────────────────────────────────────────────────

    def _check_env(self) -> None:
        print(_bold("[ 1 ] Variables .env"))
        required = [
            ("BINANCE_FUTURES_DEMO_KEY",  "Clé Futures Demo"),
            ("BINANCE_FUTURES_DEMO_SECRET","Secret Futures Demo"),
            ("TELEGRAM_BOT_TOKEN",        "Token Telegram"),
            ("TELEGRAM_CHAT_ID",          "Chat ID Telegram"),
        ]
        optional = [
            ("V9_ADVISOR_ONLY",    "Mode advisor"),
            ("EXEC_FUTURES_MIN_ORDER_USD", "Min ordre futures"),
            ("EO_DD_VETO",         "Override DD VETO"),
            ("BB_PATH",            "Black Box path"),
            ("MISTAKE_DB",         "Mistake Memory DB"),
            ("REGRET_DB",          "Regret DB"),
        ]
        for key, label in required:
            val = os.getenv(key, "")
            ok  = bool(val) and val not in ("REMPLACE_PAR_CLE_LIVE", "")
            self.results.append(CheckResult(
                f"env.{key}", ok,
                f"{label} = {'[SET]' if ok else '[MANQUANT]'}"
            ))
            self._print_result(f"  {label}", ok)

        for key, label in optional:
            val = os.getenv(key, "")
            self.results.append(CheckResult(
                f"env_opt.{key}", True, f"{label} = {val or '[default]'}", warn=not bool(val)
            ))
        print()

    # ── 2. Dossiers et fichiers requis ────────────────────────────────────────

    def _check_dirs(self) -> None:
        print(_bold("[ 2 ] Dossiers & fichiers"))
        dirs = [
            "databases", "logs", "databases/shadow_execution",
            "quant_hedge_ai/agents/intelligence",
            "quant_hedge_ai/agents/risk",
            "quant_hedge_ai/agents/execution",
        ]
        for d in dirs:
            p   = Path(d)
            ok  = p.exists() and p.is_dir()
            if not ok and self.fix:
                p.mkdir(parents=True, exist_ok=True)
                ok = True
            self.results.append(CheckResult(f"dir.{d}", ok, d))
            self._print_result(f"  {d}/", ok)

        # Fichier .env
        ok = Path(".env").exists()
        self.results.append(CheckResult("file.env", ok, ".env"))
        self._print_result("  .env", ok)

        # Écriture dans databases/
        try:
            test_file = Path("databases/.boot_test")
            test_file.write_text("ok")
            test_file.unlink()
            self.results.append(CheckResult("dir.databases.write", True, "Écriture OK"))
            self._print_result("  databases/ writable", True)
        except Exception as e:
            self.results.append(CheckResult("dir.databases.write", False, str(e)))
            self._print_result("  databases/ writable", False)
        print()

    # ── 3. Imports ────────────────────────────────────────────────────────────

    def _check_imports(self) -> None:
        print(_bold("[ 3 ] Imports modules"))
        modules = [
            # Infrastructure
            ("ExecutionEngine",          "quant_hedge_ai.agents.execution.execution_engine",     "ExecutionEngine"),
            ("PositionManager",          "quant_hedge_ai.agents.execution.position_manager",     "PositionManager"),
            ("LiveSignalEngine",         "quant_hedge_ai.agents.execution.live_signal_engine",   "LiveSignalEngine"),
            ("ShadowEngine",             "quant_hedge_ai.agents.execution.shadow_engine",        "ShadowExecutionEngine"),
            # Market
            ("MarketScanner",            "quant_hedge_ai.agents.market.market_scanner",          "MarketScanner"),
            ("MultiTimeframeScanner",    "quant_hedge_ai.agents.market.multi_timeframe_scanner", "MultiTimeframeScanner"),
            ("FeatureEngineer",          "quant_hedge_ai.agents.intelligence.feature_engineer",  "FeatureEngineer"),
            ("RegimeDetector",           "quant_hedge_ai.agents.intelligence.regime_detector",   "AdvancedRegimeDetector"),
            # Risk
            ("GlobalRiskGate",           "quant_hedge_ai.agents.risk.global_risk_gate",          "GlobalRiskGate"),
            ("PortfolioBrain",           "quant_hedge_ai.agents.risk.portfolio_brain",           "PortfolioBrain"),
            ("CapitalAllocationEngine",  "quant_hedge_ai.agents.risk.capital_allocation_engine","CapitalAllocationEngine"),
            ("ExecutiveOverride",        "quant_hedge_ai.agents.risk.executive_override",        "ExecutiveOverride"),
            # Intelligence
            ("MetaStrategyEngine",       "quant_hedge_ai.agents.intelligence.meta_strategy_engine","MetaStrategyEngine"),
            ("ConvictionEngine",         "quant_hedge_ai.agents.intelligence.conviction_engine", "ConvictionEngine"),
            ("NoTradeIntelligence",      "quant_hedge_ai.agents.intelligence.no_trade_layer",    "NoTradeIntelligence"),
            ("SelfAwarenessEngine",      "quant_hedge_ai.agents.intelligence.self_awareness_engine","SelfAwarenessEngine"),
            ("MistakeMemory",            "quant_hedge_ai.agents.intelligence.mistake_memory",    "MistakeMemory"),
            ("BlackBox",                 "quant_hedge_ai.agents.intelligence.black_box",         "BlackBox"),
            ("RegretEngine",             "quant_hedge_ai.agents.intelligence.regret_engine",     "RegretEngine"),
            ("ChiefOfficer",             "quant_hedge_ai.agents.intelligence.chief_officer",     "ChiefOfficer"),
            ("ThreatRadar",              "quant_hedge_ai.agents.intelligence.threat_radar",       "ThreatRadar"),
            ("DecisionQualityEngine",    "quant_hedge_ai.agents.intelligence.decision_quality_engine","DecisionQualityEngine"),
            # Learning
            ("StrategyRanker",           "quant_hedge_ai.ai_evolution.strategy_ranker",         "StrategyRanker"),
            ("StrategyMemory",           "quant_hedge_ai.ai_evolution.strategy_memory",         "StrategyMemoryStore"),
            # Supervision
            ("TelegramKillSwitch",       "supervision.telegram_kill_switch",                    "TelegramKillSwitch"),
            ("ExchangeMonitor",          "supervision.exchange_monitor",                        "ExchangeMonitor"),
            ("SelfHealingBot",           "supervision.self_healing_bot",                        "SelfHealingBot"),
            ("PerformanceWatchdog",      "supervision.performance_watchdog",                    "PerformanceWatchdog"),
        ]
        for label, mod, cls in modules:
            try:
                m = __import__(mod, fromlist=[cls])
                getattr(m, cls)
                self.results.append(CheckResult(f"import.{label}", True))
                self._print_result(f"  {label}", True)
            except Exception as e:
                short = str(e)[:80]
                self.results.append(CheckResult(f"import.{label}", False, short))
                self._print_result(f"  {label}", False, short)
        print()

    # ── 4. Instanciation ──────────────────────────────────────────────────────

    def _check_instantiation(self) -> None:
        print(_bold("[ 4 ] Instanciation des modules clés"))

        checks = [
            ("FeatureEngineer",         self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.feature_engineer", fromlist=["FeatureEngineer"]).FeatureEngineer())),
            ("GlobalRiskGate",          self._try(lambda: __import__("quant_hedge_ai.agents.risk.global_risk_gate", fromlist=["GlobalRiskGate"]).GlobalRiskGate())),
            ("PortfolioBrain",          self._try(lambda: __import__("quant_hedge_ai.agents.risk.portfolio_brain", fromlist=["PortfolioBrain"]).PortfolioBrain(total_capital=1000))),
            ("CapitalAllocationEngine", self._try(lambda: __import__("quant_hedge_ai.agents.risk.capital_allocation_engine", fromlist=["CapitalAllocationEngine"]).CapitalAllocationEngine(total_capital=1000))),
            ("ExecutiveOverride",       self._try(lambda: __import__("quant_hedge_ai.agents.risk.executive_override", fromlist=["ExecutiveOverride"]).ExecutiveOverride(total_capital=1000))),
            ("ConvictionEngine",        self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.conviction_engine", fromlist=["ConvictionEngine"]).ConvictionEngine())),
            ("MetaStrategyEngine",      self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.meta_strategy_engine", fromlist=["MetaStrategyEngine"]).MetaStrategyEngine())),
            ("SelfAwarenessEngine",     self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.self_awareness_engine", fromlist=["SelfAwarenessEngine"]).SelfAwarenessEngine())),
            ("NoTradeIntelligence",     self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.no_trade_layer", fromlist=["NoTradeIntelligence"]).NoTradeIntelligence())),
            ("MistakeMemory",           self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.mistake_memory", fromlist=["MistakeMemory"]).MistakeMemory())),
            ("BlackBox",                self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.black_box", fromlist=["BlackBox"]).BlackBox())),
            ("RegretEngine",            self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.regret_engine", fromlist=["RegretEngine"]).RegretEngine())),
            ("ChiefOfficer",            self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.chief_officer", fromlist=["ChiefOfficer"]).ChiefOfficer())),
            ("ThreatRadar",             self._try(lambda: __import__("quant_hedge_ai.agents.intelligence.threat_radar", fromlist=["ThreatRadar"]).ThreatRadar())),
            ("StrategyRanker",          self._try(lambda: __import__("quant_hedge_ai.ai_evolution.strategy_ranker", fromlist=["StrategyRanker"]).StrategyRanker())),
            ("LiveSignalEngine",        self._try(lambda: __import__("quant_hedge_ai.agents.execution.live_signal_engine", fromlist=["LiveSignalEngine"]).LiveSignalEngine())),
        ]
        for label, (ok, err) in checks:
            self.results.append(CheckResult(f"init.{label}", ok, err))
            self._print_result(f"  {label}()", ok, err)
        print()

    # ── 5. Chaîne de décision (données synthétiques) ─────────────────────────

    def _check_decision_chain(self) -> None:
        print(_bold("[ 5 ] Chaîne de décision complète (données synthétiques)"))
        try:
            from quant_hedge_ai.agents.intelligence.feature_engineer import FeatureEngineer
            from quant_hedge_ai.agents.execution.live_signal_engine import LiveSignalEngine
            from quant_hedge_ai.agents.risk.global_risk_gate import GlobalRiskGate
            from quant_hedge_ai.agents.intelligence.meta_strategy_engine import MetaStrategyEngine
            from quant_hedge_ai.agents.intelligence.conviction_engine import ConvictionEngine
            from quant_hedge_ai.agents.intelligence.no_trade_layer import NoTradeIntelligence
            from quant_hedge_ai.agents.intelligence.self_awareness_engine import SelfAwarenessEngine
            from quant_hedge_ai.agents.intelligence.mistake_memory import MistakeMemory
            from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioBrain
            from quant_hedge_ai.agents.risk.capital_allocation_engine import CapitalAllocationEngine
            from quant_hedge_ai.agents.risk.executive_override import ExecutiveOverride

            # Bougies synthétiques : tendance haussière claire
            import random
            random.seed(42)
            base = 77000.0
            candles = []
            for i in range(200):
                close = base + i * 10 + random.gauss(0, 50)
                candles.append({
                    "open":   close - 20,
                    "high":   close + 40,
                    "low":    close - 40,
                    "close":  close,
                    "volume": 100 + random.gauss(0, 10),
                })

            # Layer 1 — Features
            feat = FeatureEngineer().extract_features(candles)
            assert "rsi" in feat, "Features manquantes: rsi"
            assert "atr" in feat, "Features manquantes: atr"
            self._print_result("  Features (25 indicateurs)", True,
                               f"RSI={feat['rsi']:.1f} ATR={feat['atr']:.0f}")

            # Layer 2 — Signal
            signal = LiveSignalEngine().evaluate("BTC/USDT", {"1h": candles}, features=feat)
            assert signal.score >= 0
            self._print_result("  LiveSignalEngine", True,
                               f"score={signal.score} signal={signal.signal}")

            # Layer 3 — Gate
            gate = GlobalRiskGate().check(signal)
            self._print_result("  GlobalRiskGate", True,
                               f"allowed={gate.allowed}")

            # Layer 4 — Meta
            meta  = MetaStrategyEngine()
            perso = meta.select("bull_trend", feat, memory_sharpe=1.5,
                                consecutive_losses=0, open_positions=0)
            assert perso is not None
            self._print_result("  MetaStrategyEngine", True,
                               f"personality={perso.name}")

            # Layer 5 — Conviction
            conv = ConvictionEngine().evaluate(signal, feat, candles, "bull_trend", 1.5)
            self._print_result("  ConvictionEngine", True,
                               f"level={conv.level.value} score={conv.score:.0f}")

            # Layer 6 — No-Trade
            nt = NoTradeIntelligence().check(signal, candles, feat, "bull_trend")
            self._print_result("  NoTradeIntelligence", True,
                               f"allowed={bool(nt)}")

            # Layer 7 — SelfAwareness
            aw = SelfAwarenessEngine().evaluate()
            self._print_result("  SelfAwarenessEngine", True,
                               f"level={aw.level.name}")

            # Layer 8 — MistakeMemory
            mm = MistakeMemory()
            mm_check = mm.check_before_trade("BTC/USDT", "BUY", signal.score,
                                             "bull_trend", feat)
            self._print_result("  MistakeMemory", True,
                               f"blocked={mm_check.blocked}")

            # Layer 9 — PortfolioBrain
            pb = PortfolioBrain(total_capital=1000)
            pv = pb.check_new_trade("BTC/USDT", "BUY", 55.0, "bull_trend", [])
            self._print_result("  PortfolioBrain", True,
                               f"allowed={pv.allowed} factor={pv.size_factor}")

            # Layer 10 — CapitalAllocationEngine
            cae = CapitalAllocationEngine(total_capital=1000)
            alloc = cae.allocate(55.0, win_rate=0.55, avg_win_pct=0.04,
                                 avg_loss_pct=0.02, regime="bull_trend",
                                 conviction_factor=conv.size_factor)
            self._print_result("  CapitalAllocationEngine", True,
                               f"size=${alloc.size_usd:.0f} kelly={alloc.kelly_fraction:.4f}")

            # Layer 11 — ExecutiveOverride
            eo = ExecutiveOverride(total_capital=1000)
            ev = eo.check_trade(alloc.size_usd)
            self._print_result("  ExecutiveOverride", True,
                               f"level={ev.level.name} allowed={ev.allowed}")

            # Layer 12 — ThreatRadar
            from quant_hedge_ai.agents.intelligence.threat_radar import ThreatRadar
            radar = ThreatRadar()
            radar.feed_candles("BTC/USDT", candles)
            radar_report = radar.scan_sync(["BTC/USDT"])
            threat_count = len(radar_report.threats)
            self._print_result("  ThreatRadar", True,
                               f"menaces={threat_count} niveau={radar_report.max_level.value} trade_ok={radar_report.trade_allowed}")

            # Verdict chaîne
            all_ok = (gate.allowed and bool(nt) and not mm_check.blocked
                      and pv.allowed and alloc.size_usd > 0 and ev.allowed
                      and radar_report.trade_allowed)
            self.results.append(CheckResult("chain.complete", True,
                                            f"12 couches OK | trade={'AUTORISE' if all_ok else 'BLOQUE'}"))
            self._print_result(
                f"  CHAINE COMPLETE — trade {'AUTORISE' if all_ok else 'BLOQUE (normal si conditions)'}",
                True
            )

        except Exception:
            tb = traceback.format_exc().strip().split("\n")[-1]
            self.results.append(CheckResult("chain.complete", False, tb))
            self._print_result("  CHAINE COMPLETE", False, tb)
        print()

    # ── 6. Exchange live (optionnel) ──────────────────────────────────────────

    def _check_exchange(self) -> None:
        print(_bold("[ 6 ] Connexion exchange (live)"))
        try:
            from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine
            eng = ExecutionEngine.from_env()
            ok_futures = eng.has_futures_demo()
            self._print_result("  has_futures_demo", ok_futures)
            self.results.append(CheckResult("exchange.futures", ok_futures,
                                            "Futures Demo accessible" if ok_futures else "NON disponible"))

            if ok_futures:
                bal = eng.fetch_futures_balance()
                cap = eng.fetch_available_capital()
                ok  = bal > 0 or cap > 0
                self._print_result(
                    f"  Balance futures: ${bal:.0f} USDT | Spot: ${cap:.0f}", ok
                )
                self.results.append(CheckResult("exchange.balance", ok,
                                                f"Futures=${bal:.0f} Spot=${cap:.0f}"))
        except Exception as e:
            short = str(e)[:100]
            self.results.append(CheckResult("exchange.connect", False, short))
            self._print_result("  Exchange connexion", False, short)
        print()

    # ── Rapport final ─────────────────────────────────────────────────────────

    def _report(self) -> bool:
        elapsed = time.time() - self._start
        failed  = [r for r in self.results if not r.ok]
        warned  = [r for r in self.results if r.ok and r.warn]

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
            for r in failed:
                print(f"  {_red('FAIL')} {r.name}: {r.detail}")
            print()
            print(_bold(_red("  VERDICT : SYSTEME NON PRET — corriger avant de lancer")))
        else:
            print(_bold(_green("  VERDICT : SYSTEME PRET — tous les checks passent")))
            advisor_only = os.getenv("V9_ADVISOR_ONLY", "true").lower()
            mode = "OBSERVATION" if advisor_only == "true" else "TRADING ACTIF"
            print(f"  Mode au démarrage : {_bold(mode)}")

        print(_bold("==============================================\n"))
        return len(failed) == 0

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _try(fn) -> tuple[bool, str]:
        try:
            fn()
            return True, ""
        except Exception as e:
            return False, str(e)[:80]

    @staticmethod
    def _print_result(label: str, ok: bool, detail: str = "") -> None:
        icon   = _green("PASS") if ok else _red("FAIL")
        suffix = f"  {_yellow(detail)}" if detail and not ok else (f"  {detail}" if detail else "")
        print(f"  [{icon}] {label}{suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Boot System Validator")
    parser.add_argument("--fast", action="store_true", help="Skip exchange live check")
    parser.add_argument("--fix",  action="store_true", help="Auto-créer les dossiers manquants")
    args = parser.parse_args()

    validator = BootValidator(fast=args.fast, fix=args.fix)
    ok = validator.run()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
