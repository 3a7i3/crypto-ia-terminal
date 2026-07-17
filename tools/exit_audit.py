"""
tools/exit_audit.py — Audit des sorties (hypothèse H-exit, 2026-07-17).

Constat V4 J1 : 4 perdants sur 6 étaient montés à >= +1% de gain latent
(MFE) avant de finir TIMEOUT/SL, pendant que R2 mesure des mouvements
médians ~1% à 4h — hypothèse : les TP (2.5-4x ATR, plusieurs %) visent des
mouvements que le marché n'offre pas à l'horizon des trades, et la
géométrie de sortie rend l'alpha d'entrée au marché.

Cet outil MESURE (lecture seule, gel-compatible) :
  1. le capture ratio : PnL final / meilleur gain latent (MFE) ;
  2. un what-if par géométrie de TP (0.8 / 1.0 / 1.5 / 2.0 % brut), rejoué
     sur les excursions réelles MAE/MFE de chaque trade, net du coût
     aller-retour (2 x (taker + slippage) = ~0.30 %).

Honnêteté du modèle (limites assumées) :
  - MAE/MFE ne donnent pas l'ORDRE des excursions : un trade qui a la fois
    MFE >= TP simulé et SL réellement touché est classé AMBIGU — le rapport
    donne une borne optimiste (TP d'abord) ET pessimiste (SL d'abord).
  - Les variantes de timeout exigent le chemin intra-trade : v2 pourra le
    reconstruire depuis le pouls (market_pulse, 15 min) pour les trades
    postérieurs au 2026-07-16 — pas simulé ici.
  - Toute MODIFICATION réelle de TP/SL reste une décision opérateur par
    ADR, soumise à la règle du statisticien — cet outil produit le dossier,
    jamais le réglage.

Usage :
  python tools/exit_audit.py                 # époque active (V4)
  python tools/exit_audit.py --all           # toutes époques avec MAE/MFE
  python tools/exit_audit.py --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

_REPO_ROOT = (
    Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd()
)
sys.path.insert(0, str(_REPO_ROOT))

TP_GRID_PCT = [0.8, 1.0, 1.5, 2.0]
DEFAULT_TRADES = Path("databases/paper_trades.jsonl")


def _f(value, default: float = 0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if v == v else default


def roundtrip_cost_pct() -> float:
    """Coût aller-retour net (%) — mêmes constantes que MexcSimulator."""
    try:
        from paper_trading.mexc_simulator import _SLIPPAGE, _TAKER_FEE

        return 2.0 * (_TAKER_FEE + _SLIPPAGE) * 100.0
    except Exception:
        return 0.30  # 2 x (0.1% taker + 0.05% slippage)


def load_trades(path: Path, since_epoch: bool) -> tuple[list[dict], int]:
    """CLOSE avec MAE/MFE exploitables. Retourne (trades, total_close)."""
    if since_epoch:
        from tools.cri_calculator import load_clean_trades

        closes = load_clean_trades(path)
    else:
        from tools.cri_calculator import _read_jsonl

        closes = [d for d in _read_jsonl(path) if d.get("event") == "CLOSE"]
    usable = [
        t
        for t in closes
        if t.get("mfe_pct") is not None and t.get("mae_pct") is not None
    ]
    return usable, len(closes)


def net_actual_pct(trade: dict) -> float:
    """PnL réel NET en % du notionnel (pnl_usd est net de frais)."""
    size = _f(trade.get("size_usd"))
    if size > 0:
        return 100.0 * _f(trade.get("pnl_usd")) / size
    # fallback : brut - coût aller-retour
    return 100.0 * _f(trade.get("pnl_pct")) - roundtrip_cost_pct()


def capture_stats(trades: list[dict]) -> dict:
    """Capture ratio + MFE des perdants — le coeur du constat H-exit."""
    ratios: list[float] = []
    mfe_losers: list[float] = []
    for t in trades:
        mfe = _f(t.get("mfe_pct"))
        gross = 100.0 * _f(t.get("pnl_pct"))
        if mfe > 0.05:
            ratios.append(gross / mfe)
        if _f(t.get("pnl_usd")) <= 0:
            mfe_losers.append(mfe)
    out: dict = {"n": len(trades)}
    if ratios:
        out["capture_ratio_median"] = round(statistics.median(ratios), 3)
    if mfe_losers:
        out["mfe_perdants_moy_pct"] = round(sum(mfe_losers) / len(mfe_losers), 3)
        out["perdants_mfe_ge_0.5"] = sum(1 for m in mfe_losers if m >= 0.5)
        out["perdants_mfe_ge_1.0"] = sum(1 for m in mfe_losers if m >= 1.0)
        out["n_perdants"] = len(mfe_losers)
    return out


def simulate_tp(trades: list[dict], tp_pct: float, cost_pct: float) -> dict:
    """What-if : TP à tp_pct (brut) sur les excursions réelles.

    Trois classes par trade :
      - TP_SUR   : MFE >= tp et le trade n'a jamais touché son SL réel →
                   TP capturé de façon certaine (+tp - coût, net)
      - AMBIGU   : MFE >= tp mais SL réellement touché — ordre inconnu →
                   optimiste = TP, pessimiste = résultat réel
      - INCHANGÉ : MFE < tp → résultat réel (net)
    """
    tp_net = tp_pct - cost_pct
    n_sure = n_ambiguous = n_unchanged = 0
    pnl_optimistic = pnl_pessimistic = 0.0
    for t in trades:
        mfe = _f(t.get("mfe_pct"))
        actual = net_actual_pct(t)
        hit_sl = str(t.get("reason", "")).upper() == "SL"
        if mfe >= tp_pct and not hit_sl:
            n_sure += 1
            pnl_optimistic += tp_net
            pnl_pessimistic += tp_net
        elif mfe >= tp_pct and hit_sl:
            n_ambiguous += 1
            pnl_optimistic += tp_net
            pnl_pessimistic += actual
        else:
            n_unchanged += 1
            pnl_optimistic += actual
            pnl_pessimistic += actual
    n = max(1, len(trades))
    return {
        "tp_pct": tp_pct,
        "n_tp_sur": n_sure,
        "n_ambigu": n_ambiguous,
        "n_inchange": n_unchanged,
        "esperance_optimiste_pct": round(pnl_optimistic / n, 4),
        "esperance_pessimiste_pct": round(pnl_pessimistic / n, 4),
        "total_optimiste_pct": round(pnl_optimistic, 3),
        "total_pessimiste_pct": round(pnl_pessimistic, 3),
    }


def audit(path: Path = DEFAULT_TRADES, since_epoch: bool = True) -> dict:
    trades, total = load_trades(path, since_epoch)
    cost = roundtrip_cost_pct()
    actual_net = [net_actual_pct(t) for t in trades]
    return {
        "fenetre": "epoque_active" if since_epoch else "toutes_epoques",
        "n_utilisables": len(trades),
        "n_close_total": total,
        "cout_aller_retour_pct": round(cost, 3),
        "esperance_reelle_pct": (
            round(sum(actual_net) / len(actual_net), 4) if actual_net else None
        ),
        "capture": capture_stats(trades),
        "what_if_tp": [simulate_tp(trades, tp, cost) for tp in TP_GRID_PCT],
    }


def render_report(a: dict) -> str:
    lines = [
        f"AUDIT DES SORTIES (H-exit) — fenêtre: {a['fenetre']}",
        f"  {a['n_utilisables']} trades avec MAE/MFE sur {a['n_close_total']} CLOSE"
        f" | coût aller-retour: {a['cout_aller_retour_pct']:.2f}%",
    ]
    cap = a["capture"]
    if cap.get("n_perdants"):
        lines.append(
            f"  Capture ratio médian: {cap.get('capture_ratio_median', '?')}"
            f" | MFE moyen des perdants: +{cap['mfe_perdants_moy_pct']:.2f}%"
            f" ({cap['perdants_mfe_ge_1.0']}/{cap['n_perdants']} perdants"
            f" montés >= +1%)"
        )
    if a["esperance_reelle_pct"] is not None:
        lines.append(
            f"  Espérance RÉELLE (géométrie actuelle): "
            f"{a['esperance_reelle_pct']:+.3f}% net/trade"
        )
    lines.append("")
    lines.append(
        f"  {'TP brut':>8} | {'TP sûrs':>7} | {'ambigus':>7} | {'inchangés':>9}"
        f" | {'espérance nette/trade (pess. .. opt.)':>38}"
    )
    for s in a["what_if_tp"]:
        lines.append(
            f"  {s['tp_pct']:>7.1f}% | {s['n_tp_sur']:>7} | {s['n_ambigu']:>7}"
            f" | {s['n_inchange']:>9}"
            f" | {s['esperance_pessimiste_pct']:>+9.3f}% .. "
            f"{s['esperance_optimiste_pct']:+.3f}%"
        )
    lines += [
        "",
        "  Lecture : 'TP sûrs' = MFE >= TP sans SL touché (gain certain a",
        "  posteriori). 'Ambigus' = MFE >= TP mais SL réel touché — l'ordre",
        "  des excursions est inconnu, d'où la fourchette pessimiste/optimiste.",
        "  Cet audit DÉCRIT ; tout changement de TP/SL = ADR + règle du",
        "  statisticien (N>=500). v2 : rejouer le chemin exact depuis le pouls.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit des sorties (H-exit)")
    parser.add_argument("--trades", default=str(DEFAULT_TRADES))
    parser.add_argument(
        "--all",
        action="store_true",
        help="toutes les époques (caveat: univers mélangés)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = audit(Path(args.trades), since_epoch=not args.all)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(render_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
