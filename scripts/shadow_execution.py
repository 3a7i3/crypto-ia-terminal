"""
03_shadow_execution.py — Tracker des trades refusés par le gate.

Enregistre chaque refus de gate avec le prix au moment du refus,
puis simule le PnL que ce trade aurait fait.
Compare shadow vs réel pour mesurer le coût du gate en trades manqués.

Deux usages :
  A. API (import dans advisor_loop.py) :
        from S3.shadow_execution import ShadowTracker
        shadow = ShadowTracker()
        shadow.log_refused(symbol, side, score, regime, failed_checks, price)

  B. Analyse standalone :
        python3 S3/03_shadow_execution.py
        python3 S3/03_shadow_execution.py --days 3
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

SHADOW_PATH = "databases/shadow_s3_refused.jsonl"
# Prix de sortie simulé : on lit dans gate_rejections.csv ou paper_trades.jsonl
PT_PATH = "databases/paper_trades.jsonl"


class ShadowTracker:
    """
    Enregistre les refus de gate + estime leur PnL simulé.

    Le PnL simulé utilise les prix futurs observés dans paper_trades.jsonl
    comme proxy du marché. Si pas disponible, marque pnl_simulated=None.
    """

    def __init__(self, path: str = SHADOW_PATH) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log_refused(
        self,
        symbol: str,
        side: str,
        score: float,
        regime: str,
        failed_checks: list[str],
        price: float,
        cycle_id: str = "",
    ) -> None:
        """
        Enregistre un trade refusé par le gate.

        Args:
            symbol        : ex. "BTC/USDT"
            side          : "BUY" | "SELL"
            score         : score du signal
            regime        : régime courant
            failed_checks : liste des conditions échouées
            price         : prix au moment du refus
            cycle_id      : identifiant du cycle (optionnel)
        """
        record = {
            "ts": time.time(),
            "cycle_id": cycle_id,
            "symbol": symbol,
            "side": side,
            "score": score,
            "regime": regime,
            "failed_checks": failed_checks,
            "price_at_refusal": price,
            "pnl_simulated": None,
            "resolved": False,
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def load(self, days: int = 7) -> list[dict]:
        if not self._path.exists():
            return []
        cutoff = time.time() - days * 86400
        rows = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    if d.get("ts", 0) >= cutoff:
                        rows.append(d)
                except json.JSONDecodeError:
                    pass
        return rows


def _load_paper_prices() -> dict[str, list[dict]]:
    """Charge les clôtures paper_trades pour estimer les PnL simulés."""
    p = Path(PT_PATH)
    if not p.exists():
        return {}
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if d.get("event") == "CLOSE" and d.get("symbol"):
                    by_symbol[d["symbol"]].append(d)
            except json.JSONDecodeError:
                pass
    return dict(by_symbol)


def _estimate_pnl(refused: dict, paper_by_symbol: dict) -> float | None:
    """
    Estime le PnL d'un trade refusé en cherchant le prochain trade
    sur le même symbole dans paper_trades comme proxy du prix de sortie.
    """
    sym = refused.get("symbol", "")
    side = refused.get("side", "BUY")
    ts_refused = refused.get("ts", 0)
    price_in = refused.get("price_at_refusal", 0)

    if not price_in or sym not in paper_by_symbol:
        return None

    # Trouver le premier close sur ce symbole APRÈS le refus
    for close in sorted(paper_by_symbol[sym], key=lambda x: x.get("ts", 0)):
        if close.get("ts", 0) > ts_refused:
            price_out = close.get("exit_price") or close.get("price", 0)
            if price_out:
                if side == "BUY":
                    return (price_out - price_in) / price_in
                else:
                    return (price_in - price_out) / price_in
    return None


def analyze(days: int = 7) -> None:
    tracker = ShadowTracker()
    refused = tracker.load(days)

    if not refused:
        print(f"[shadow_execution] Aucun trade refusé dans les {days} derniers jours.")
        print(f"  → Fichier: {SHADOW_PATH}")
        print(
            "  → S'assure que ShadowTracker.log_refused() est appelé dans advisor_loop.py"
        )
        return

    paper_prices = _load_paper_prices()

    # Estimer les PnL simulés
    simulated_pnls = []
    for r in refused:
        pnl = _estimate_pnl(r, paper_prices)
        if pnl is not None:
            simulated_pnls.append(pnl)

    total = len(refused)
    resolved = len(simulated_pnls)

    print(f"\n{'='*60}")
    print(f"  SHADOW EXECUTION — {total} trades refusés ({days} jours)")
    print(f"{'='*60}")

    # ── Top raisons de refus ───────────────────────────────────────────────────
    from collections import Counter

    all_checks: list[str] = []
    for r in refused:
        all_checks.extend(r.get("failed_checks", []))
    top = Counter(all_checks).most_common(8)

    print("\n  Top raisons de refus gate:")
    for reason, count in top:
        pct = count / total * 100
        print(f"    {reason:<40} {count:>4}x  {pct:.0f}%")

    # ── Distribution par régime ────────────────────────────────────────────────
    by_regime: Counter = Counter(r.get("regime", "unknown") for r in refused)
    print("\n  Refus par régime:")
    for reg, count in by_regime.most_common():
        print(f"    {reg:<25} {count:>4}x")

    # ── PnL simulé ────────────────────────────────────────────────────────────
    if simulated_pnls:
        wins = sum(1 for p in simulated_pnls if p > 0)
        avg_pnl = sum(simulated_pnls) / len(simulated_pnls)
        total_pnl = sum(simulated_pnls)
        wr = wins / len(simulated_pnls)

        print(f"\n  PnL simulé des trades refusés ({resolved}/{total} résolus):")
        print(f"    Win rate simulé : {wr:.0%}")
        print(f"    PnL moyen       : {avg_pnl:+.2%}")
        print(f"    PnL total       : {total_pnl:+.2%}")

        if wr > 0.50:
            print(f"\n  ⚠️  Le gate bloque des trades potentiellement gagnants!")
            print(f"     → Envisager de baisser le threshold ou revoir les critères.")
        elif wr < 0.30:
            print(
                f"\n  ✓ Le gate protège correctement (trades refusés auraient perdu {1-wr:.0%})"
            )
    else:
        print(f"\n  PnL simulé: insuffisant de données (0/{total} résolus)")
        print("  → Collecter plus de closes paper_trades pour les mêmes symboles")

    # ── Score moyen des trades refusés ─────────────────────────────────────────
    scores = [r.get("score", 0) for r in refused if r.get("score", 0) > 0]
    if scores:
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        print(f"\n  Score des signaux refusés:")
        print(f"    Moyen={avg_score:.1f}  Max={max_score}")
        if max_score >= 60:
            print(
                f"    → Signaux avec score jusqu'à {max_score} refusés — gate peut-être trop strict?"
            )

    print(f"\n{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse des trades refusés par le gate"
    )
    parser.add_argument(
        "--days", type=int, default=7, help="Fenêtre d'analyse en jours"
    )
    args = parser.parse_args()
    analyze(args.days)


if __name__ == "__main__":
    main()
