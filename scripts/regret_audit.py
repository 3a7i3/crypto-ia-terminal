"""
regret_audit.py — Décomposition causale Régime / Moteur / Données

Structure DAG:
    REGIME ──────────┐
                     ↓
    DATA → SIGNAL → DECISION → OUTCOME
                     ↑
               REGRET_STATE

Trois lenses indépendantes:
    [0] DATA LENS    — cohérence des inputs (précondition)
    [1] REGIME LENS  — marché pur : prédit-il MW vs GR ?
    [2] ENGINE LENS  — RegretEngine : regret_delta prédit-il MW vs GR ?

Suivi de:
    [3] CROSS-ANALYSIS — qui domine : REGIME / ENGINE / DATA ?
    [4] TRAJECTOIRE    — historique delta + auto-correction en cours ?

Usage:
    python -X utf8 scripts/regret_audit.py
    python -X utf8 scripts/regret_audit.py --file /tmp/vps_regret.jsonl
    python -X utf8 scripts/regret_audit.py --file /tmp/vps_regret.jsonl --since-days 14
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_EWMA_ALPHA = 0.3
_MIN_SAMPLES = 5
_CLAMP = 5
_AVG_R_THRESHOLD = 0.6
_SIDEWAYS = {"sideways", "RANGE", "unknown", "UNKNOWN"}

_REGIME_BASES: dict[str, int] = {
    "sideways": 60,
    "RANGE": 60,
    "bull_trend": 72,
    "TREND_BULL": 72,
    "bear_trend": 68,
    "TREND_BEAR": 68,
    "high_volatility_regime": 68,
    "VOLATILE": 68,
    "flash_crash": 999,
    "unknown": 72,
    "UNKNOWN": 72,
}


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ── Data loading ──────────────────────────────────────────────────────────────


def load_records(path: Path, since_ts: float) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ts_evaluated", 0) >= since_ts:
                records.append(r)
    return sorted(records, key=lambda r: r.get("ts_evaluated", 0))


# ── EWMA replay (miroir de RegretEngine + GlobalRiskGate) ────────────────────


def _raw_delta(window: list[dict]) -> int:
    if len(window) < _MIN_SAMPLES:
        return 0
    missed = sum(1 for r in window if r.get("regret_type") == "MISSED_WIN")
    good = sum(1 for r in window if r.get("regret_type") == "GOOD_REFUSAL")
    avg_r = sum(r.get("regret_value", 0.0) for r in window) / len(window)
    total = missed + good
    if total == 0:
        return 0
    refusal_acc = good / total
    if missed > good and avg_r > _AVG_R_THRESHOLD:
        regime = window[-1].get("regime", "unknown")
        return -2 if (0.5 <= refusal_acc and regime in _SIDEWAYS) else -1
    if refusal_acc > 0.70 and good > missed * 2:
        return +1
    return 0


def replay(records: list[dict], window_size: int = 20) -> list[dict]:
    """Rejoue l'accumulation et enrichit chaque record avec le delta actif."""
    ewma: float = 0.0
    regret_delta: int = 0
    enriched: list[dict] = []

    for i, r in enumerate(records):
        window = records[max(0, i - window_size + 1) : i + 1]
        raw = _raw_delta(window)
        ewma = _EWMA_ALPHA * raw + (1.0 - _EWMA_ALPHA) * ewma
        smoothed = round(ewma)
        delta_before = regret_delta
        regret_delta = max(-_CLAMP, min(_CLAMP, regret_delta + smoothed))

        er = dict(r)
        er["_delta_before"] = delta_before  # delta actif au moment du refus/éval
        er["_delta_after"] = regret_delta
        er["_raw"] = raw
        er["_ewma"] = round(ewma, 3)
        er["_smoothed"] = smoothed
        enriched.append(er)

    return enriched


# ── LENS 0 : DATA ─────────────────────────────────────────────────────────────


def lens_data(records: list[dict]) -> dict:
    n = len(records)
    if n == 0:
        return {"n": 0, "noise_pct": 100.0, "status": "VIDE", "regime_dist": {}}

    required = {"regime", "regret_type", "score", "ts_evaluated", "ts_signal"}
    missing = sum(1 for r in records if not required.issubset(r))
    invalid = sum(
        1
        for r in records
        if r.get("regret_type") not in ("MISSED_WIN", "GOOD_REFUSAL", "NEUTRAL")
    )
    unk_regime = sum(1 for r in records if r.get("regime", "?") in ("UNKNOWN", "?"))

    ts_list = sorted(r.get("ts_evaluated", 0) for r in records)
    gaps = [(ts_list[i + 1] - ts_list[i]) / 3600 for i in range(len(ts_list) - 1)]
    large = [g for g in gaps if g > 1.0]
    max_gap = max(gaps) if gaps else 0.0

    regime_dist: dict[str, int] = defaultdict(int)
    for r in records:
        regime_dist[r.get("regime", "?")] += 1

    noise = 100 * (missing + invalid) / n
    status = "VALIDES" if noise < 5 else ("DEGRADEES" if noise < 20 else "CORROMPUES")

    return {
        "n": n,
        "missing": missing,
        "invalid": invalid,
        "unk_regime": unk_regime,
        "large_gaps": len(large),
        "max_gap_h": round(max_gap, 1),
        "noise_pct": round(noise, 1),
        "regime_dist": dict(regime_dist),
        "status": status,
    }


# ── LENS 1 : REGIME ───────────────────────────────────────────────────────────


def lens_regime(records: list[dict]) -> dict:
    """Marché pur : le régime à lui seul prédit-il MW vs GR ?"""
    by_r: dict[str, dict] = defaultdict(lambda: {"mw": 0, "gr": 0, "n": 0})
    for r in records:
        v = by_r[r.get("regime", "unknown")]
        v["n"] += 1
        rt = r.get("regret_type", "NEUTRAL")
        if rt == "MISSED_WIN":
            v["mw"] += 1
        elif rt == "GOOD_REFUSAL":
            v["gr"] += 1

    result = {}
    for regime, v in by_r.items():
        n, mw, gr = v["n"], v["mw"], v["gr"]
        mw_pct = 100 * mw / max(1, n)
        gr_pct = 100 * gr / max(1, n)
        net = gr - mw  # positif = refus justifiés par le marché
        if gr_pct > 60:
            signal = "REFUS JUSTIFIES (marche allait mauvais sens)"
        elif mw_pct > 60:
            signal = "REFUS INCORRECTS (marche allait bon sens)"
        else:
            signal = "AMBIGU"
        result[regime] = {
            "n": n,
            "mw": mw,
            "gr": gr,
            "mw_pct": round(mw_pct, 1),
            "gr_pct": round(gr_pct, 1),
            "net": net,
            "signal": signal,
        }

    # Influence du régime = capacité à discriminer les outcomes entre régimes
    # Si un seul régime : pas de variation = influence structurellement faible
    n_active = sum(1 for v in by_r.values() if v["n"] >= 5)
    if n_active <= 1:
        influence = 0.10
    else:
        # Ecart-type de mw_pct entre régimes = mesure de discrimination
        mw_pcts = [100 * v["mw"] / max(1, v["n"]) for v in by_r.values() if v["n"] >= 5]
        mean_mw = sum(mw_pcts) / len(mw_pcts)
        variance = sum((x - mean_mw) ** 2 for x in mw_pcts) / len(mw_pcts)
        std = variance**0.5
        influence = min(0.90, std / 50)  # 50% écart-type max = influence 1.0

    dominant = max(by_r, key=lambda r: by_r[r]["n"]) if by_r else "?"
    return {
        "by_regime": result,
        "influence": round(influence, 3),
        "n_active_regimes": n_active,
        "dominant_regime": dominant,
    }


# ── LENS 2 : ENGINE ───────────────────────────────────────────────────────────


def lens_engine(enriched: list[dict]) -> dict:
    """RegretEngine : le delta prédit-il la qualité des refus ?"""
    by_d: dict[int, dict] = defaultdict(lambda: {"mw": 0, "gr": 0, "n": 0})
    for r in enriched:
        v = by_d[r["_delta_before"]]
        v["n"] += 1
        rt = r.get("regret_type", "NEUTRAL")
        if rt == "MISSED_WIN":
            v["mw"] += 1
        elif rt == "GOOD_REFUSAL":
            v["gr"] += 1

    result = {}
    for d in sorted(by_d.keys()):
        v = by_d[d]
        n, mw, gr = v["n"], v["mw"], v["gr"]
        mw_pct = 100 * mw / max(1, n)
        gr_pct = 100 * gr / max(1, n)
        # Un moteur utile : delta haut -> GR% haut (refus justifiés)
        # Un moteur contre-productif : delta haut -> MW% haut (refus erronés)
        if gr_pct > 60:
            quality = "BON"
        elif mw_pct > 60:
            quality = "MAL CALIBRE"
        else:
            quality = "NEUTRE"
        result[d] = {
            "n": n,
            "mw": mw,
            "gr": gr,
            "mw_pct": round(mw_pct, 1),
            "gr_pct": round(gr_pct, 1),
            "quality": quality,
        }

    # Mesure de la pente GR% = f(delta)
    # Pente positive = moteur utile (delta haut -> GR% haut)
    # Pente négative = moteur contre-productif
    keys = sorted(by_d.keys())
    if len(keys) >= 2:
        gr_series = [100 * by_d[d]["gr"] / max(1, by_d[d]["n"]) for d in keys]
        delta_span = max(1, keys[-1] - keys[0])
        slope = (gr_series[-1] - gr_series[0]) / delta_span
        influence = min(1.0, abs(slope) / 10)
        direction = (
            "UTILE (delta haut -> GR%)"
            if slope > 0
            else "CONTRE-PRODUCTIF (delta haut -> MW%)"
        )
    else:
        slope = 0.0
        influence = 0.0
        direction = "INDETERMINE (variation delta insuffisante)"

    # Détection feedback loop : plateau max + MW dominant
    max_d = max(by_d.keys(), default=0)
    if max_d >= 4 and by_d[max_d]["n"] >= 3:
        plateau_mw = 100 * by_d[max_d]["mw"] / max(1, by_d[max_d]["n"])
        feedback = plateau_mw > 50
    else:
        plateau_mw = 0.0
        feedback = False

    return {
        "by_delta": result,
        "influence": round(influence, 3),
        "slope": round(slope, 3),
        "direction": direction,
        "feedback_loop": feedback,
        "plateau_mw_pct": round(plateau_mw, 1),
    }


# ── INTERVENTION TEST (permutation) ──────────────────────────────────────────


def _chi_sq(groups: dict[str, dict]) -> float:
    """Chi-carré de contingence [label × {MW, GR}]."""
    total_mw = sum(v["mw"] for v in groups.values())
    total_gr = sum(v["gr"] for v in groups.values())
    n = total_mw + total_gr
    if n == 0 or total_mw == 0 or total_gr == 0:
        return 0.0
    stat = 0.0
    for v in groups.values():
        row_n = v["mw"] + v["gr"]
        if row_n == 0:
            continue
        e_mw = row_n * total_mw / n
        e_gr = row_n * total_gr / n
        if e_mw > 0:
            stat += (v["mw"] - e_mw) ** 2 / e_mw
        if e_gr > 0:
            stat += (v["gr"] - e_gr) ** 2 / e_gr
    return stat


def intervention_test(
    records: list[dict],
    enriched: list[dict],
    n_perms: int = 500,
) -> dict:
    """
    Test d'identifiabilité par permutation.

    H₀ REGIME  : P(MW | regime=X) = P(MW | regime=Y) — regime n'est pas prédictif
    H₀ ENGINE  : P(MW | delta=A)  = P(MW | delta=B)  — delta n'est pas prédictif

    On shuffle les LABELS (pas les outcomes) et on compare le chi-carré observé
    à la distribution nulle empirique. p-value = fraction permutations >= observé.
    """
    import random as _rng

    mw_gr = []
    for r in records:
        rt = r.get("regret_type")
        if rt in ("MISSED_WIN", "GOOD_REFUSAL"):
            mw_gr.append((r.get("regime", "?"), rt))

    delta_mw_gr = []
    for r in enriched:
        rt = r.get("regret_type")
        if rt in ("MISSED_WIN", "GOOD_REFUSAL"):
            bkt = max(-5, min(5, r.get("_delta_before", 0)))
            delta_mw_gr.append((bkt, rt))

    def observed_chi(pairs: list[tuple]) -> tuple[float, dict]:
        groups: dict = {}
        for label, rt in pairs:
            if label not in groups:
                groups[label] = {"mw": 0, "gr": 0}
            if rt == "MISSED_WIN":
                groups[label]["mw"] += 1
            else:
                groups[label]["gr"] += 1
        return _chi_sq(groups), groups

    def permute_chi(pairs: list[tuple]) -> float:
        labels = [p[0] for p in pairs]
        outcomes = [p[1] for p in pairs]
        _rng.shuffle(labels)
        groups: dict = {}
        for label, rt in zip(labels, outcomes):
            if label not in groups:
                groups[label] = {"mw": 0, "gr": 0}
            if rt == "MISSED_WIN":
                groups[label]["mw"] += 1
            else:
                groups[label]["gr"] += 1
        return _chi_sq(groups)

    # Regime test
    obs_regime, groups_regime = observed_chi(mw_gr)
    n_labels_regime = len({p[0] for p in mw_gr})
    if n_labels_regime <= 1:
        p_regime = None
        identifiable_regime = False
        verdict_regime = "NON IDENTIFIABLE (variable constante)"
    else:
        null_regime = [permute_chi(mw_gr) for _ in range(n_perms)]
        p_regime = sum(1 for x in null_regime if x >= obs_regime) / n_perms
        identifiable_regime = p_regime < 0.05
        verdict_regime = (
            "CAUSAL (p<0.05)" if identifiable_regime else f"BRUIT (p={p_regime:.2f})"
        )

    # Engine (delta) test
    obs_delta, groups_delta = observed_chi(delta_mw_gr)
    n_labels_delta = len({p[0] for p in delta_mw_gr})
    if n_labels_delta <= 1:
        p_delta = None
        identifiable_delta = False
        verdict_delta = "NON IDENTIFIABLE (delta constant)"
    else:
        null_delta = [permute_chi(delta_mw_gr) for _ in range(n_perms)]
        p_delta = sum(1 for x in null_delta if x >= obs_delta) / n_perms
        identifiable_delta = p_delta < 0.05
        verdict_delta = (
            "CAUSAL (p<0.05)" if identifiable_delta else f"BRUIT (p={p_delta:.2f})"
        )

    return {
        "regime": {
            "n_labels": n_labels_regime,
            "chi_sq": round(obs_regime, 3),
            "p_value": p_regime,
            "identifiable": identifiable_regime,
            "verdict": verdict_regime,
            "groups": {k: v for k, v in groups_regime.items()},
        },
        "engine": {
            "n_labels": n_labels_delta,
            "chi_sq": round(obs_delta, 3),
            "p_value": p_delta,
            "identifiable": identifiable_delta,
            "verdict": verdict_delta,
        },
        "n_perms": n_perms,
    }


# ── CROSS-ANALYSIS : DOMINANCE ────────────────────────────────────────────────


def cross_analysis(data_r: dict, regime_r: dict, engine_r: dict) -> dict:
    ri = regime_r["influence"]
    ei = engine_r["influence"]
    di = min(1.0, data_r["noise_pct"] / 100)

    total = ri + ei + di + 1e-9
    dominance = {
        "REGIME": round(ri / total, 3),
        "ENGINE": round(ei / total, 3),
        "DATA": round(di / total, 3),
    }
    dominant = max(dominance, key=dominance.get)

    # Si seul un régime est présent, l'ENGINE opère sans signal de discrimination
    # => son influence apparente est possiblement confondue avec le régime
    engine_confounded = regime_r["n_active_regimes"] <= 1 and ei > 0.1

    return {
        "dominance": dominance,
        "dominant": dominant,
        "engine_confounded": engine_confounded,
        "feedback_loop": engine_r["feedback_loop"],
    }


# ── TRAJECTOIRE ───────────────────────────────────────────────────────────────


def _window_status(subset: list[dict]) -> dict:
    if not subset:
        return {"n": 0, "mw": 0, "gr": 0, "raw_est": 0, "direction": "?"}
    mw = sum(1 for r in subset if r.get("regret_type") == "MISSED_WIN")
    gr = sum(1 for r in subset if r.get("regret_type") == "GOOD_REFUSAL")
    avg = sum(r.get("regret_value", 0.0) for r in subset) / max(1, len(subset))
    total = mw + gr
    if total == 0:
        raw_est = 0
    elif mw > gr and avg > _AVG_R_THRESHOLD:
        raw_est = -2
    elif gr > mw * 2 and gr / total > 0.70:
        raw_est = +1
    else:
        raw_est = 0
    direction = {
        -2: "CORRECTION RAPIDE",
        -1: "CORRECTION",
        0: "GELE",
        1: "AGGRAVATION",
    }.get(raw_est, "?")
    return {
        "n": len(subset),
        "mw": mw,
        "gr": gr,
        "raw_est": raw_est,
        "direction": direction,
    }


def trajectory(enriched: list[dict]) -> dict:
    if not enriched:
        return {}
    n = len(enriched)
    final = enriched[-1]["_delta_after"]
    at_max = sum(1 for r in enriched if r["_delta_after"] == _CLAMP)
    at_min = sum(1 for r in enriched if r["_delta_after"] == -_CLAMP)

    # Transitions
    transitions = []
    for i, r in enumerate(enriched):
        if i == 0 or r["_delta_after"] != enriched[i - 1]["_delta_after"]:
            transitions.append(
                {
                    "dt": _fmt(r.get("ts_evaluated", 0)),
                    "idx": i,
                    "delta": r["_delta_after"],
                    "type": r.get("regret_type", "?"),
                    "raw": r["_raw"],
                }
            )
    last_change_idx = max((t["idx"] for t in transitions), default=0)

    # Recent vs historique
    cutoff = time.time() - 7 * 86400
    recent = [r for r in enriched if r.get("ts_evaluated", 0) >= cutoff]
    older = [r for r in enriched if r.get("ts_evaluated", 0) < cutoff]

    return {
        "final": final,
        "at_max_pct": round(100 * at_max / n, 1),
        "at_min_pct": round(100 * at_min / n, 1),
        "n_transitions": len(transitions),
        "last_change_idx": last_change_idx,
        "records_frozen": n - last_change_idx - 1,
        "transitions": transitions[:20],
        "recent": _window_status(recent),
        "older": _window_status(older),
    }


# ── PRINT ─────────────────────────────────────────────────────────────────────


def print_report(records: list[dict], enriched: list[dict]) -> None:
    n = len(records)
    if n == 0:
        print("Aucun record.")
        return

    ts0 = records[0].get("ts_evaluated", 0)
    ts1 = records[-1].get("ts_evaluated", 0)

    data_r = lens_data(records)
    regime_r = lens_regime(records)
    engine_r = lens_engine(enriched)
    cross_r = cross_analysis(data_r, regime_r, engine_r)
    traj_r = trajectory(enriched)
    intv_r = intervention_test(records, enriched)

    W = 64

    print(f"\n{'='*W}")
    print(f"  REGRET AUDIT v2 — Décomposition causale Régime/Moteur/Données")
    print(f"{'='*W}")
    print(f"  Records : {n}   Période : {(ts1-ts0)/3600:.0f}h")
    print(f"  De : {_fmt(ts0)}")
    print(f"  A  : {_fmt(ts1)}")

    # ── [0] DATA ──────────────────────────────────────────────────────────────
    print(f"\n{'─'*W}")
    print(f"  [0] DATA LENS — Cohérence des inputs")
    print(f"{'─'*W}")
    print(f"  Champs manquants   : {data_r['missing']}/{n}")
    print(f"  Labels invalides   : {data_r['invalid']}/{n}")
    print(f"  Régimes inconnus   : {data_r['unk_regime']}/{n}")
    print(
        f"  Gaps temporels >1h : {data_r['large_gaps']}"
        f"  (max={data_r['max_gap_h']:.1f}h)"
    )
    print(f"  Bruit total        : {data_r['noise_pct']:.1f}%  => {data_r['status']}")
    print(f"  Distribution régimes:")
    for reg, cnt in sorted(data_r["regime_dist"].items(), key=lambda x: -x[1]):
        print(f"    {reg:<28}: {cnt:>5}  ({100*cnt/n:.0f}%)")

    # ── [1] REGIME ────────────────────────────────────────────────────────────
    print(f"\n{'─'*W}")
    print(f"  [1] REGIME LENS — Marché pur")
    print(f"  Le régime à lui seul explique-t-il MW vs GR ?")
    print(f"{'─'*W}")
    print(f"  {'Régime':<26} {'N':>5}  {'MW%':>6}  {'GR%':>6}  {'Net':>5}  Signal")
    print(f"  {'-'*W}")
    for regime, v in sorted(regime_r["by_regime"].items(), key=lambda x: -x[1]["n"]):
        net_s = f"{v['net']:+d}"
        print(
            f"  {regime:<26} {v['n']:>5}"
            f"  {v['mw_pct']:>5.1f}%  {v['gr_pct']:>5.1f}%"
            f"  {net_s:>5}  {v['signal']}"
        )
    print(
        f"\n  Régimes actifs : {regime_r['n_active_regimes']}  "
        f"Influence REGIME : {regime_r['influence']:.3f}"
    )
    if regime_r["n_active_regimes"] <= 1:
        print(f"  => Seul 1 régime actif : pas de variation inter-régime mesurable")

    # ── [2] ENGINE ────────────────────────────────────────────────────────────
    print(f"\n{'─'*W}")
    print(f"  [2] ENGINE LENS — RegretEngine")
    print(f"  regret_delta prédit-il la qualité des refus ?")
    print(f"{'─'*W}")
    print(f"  {'Delta':>7}  {'N':>5}  {'MW%':>6}  {'GR%':>6}  Qualité")
    print(f"  {'-'*50}")
    for d, v in sorted(engine_r["by_delta"].items()):
        print(
            f"  {d:>+7}  {v['n']:>5}"
            f"  {v['mw_pct']:>5.1f}%  {v['gr_pct']:>5.1f}%  {v['quality']}"
        )
    print(f"\n  Pente GR% = f(delta) : {engine_r['slope']:+.2f}%/pt")
    print(f"  Influence ENGINE     : {engine_r['influence']:.3f}")
    print(f"  Direction            : {engine_r['direction']}")
    fb = engine_r["feedback_loop"]
    if fb:
        pct_fb = engine_r["plateau_mw_pct"]
        print(f"  ALERTE FEEDBACK LOOP : plateau delta_max avec MW={pct_fb:.0f}%")
    else:
        print(f"  Feedback loop        : non détectée")

    # ── [3] CROSS-ANALYSIS ────────────────────────────────────────────────────
    print(f"\n{'─'*W}")
    print(f"  [3] CROSS-ANALYSIS — Qui contrôle le système ?")
    print(f"{'─'*W}")
    dom = cross_r["dominance"]
    for driver, share in sorted(dom.items(), key=lambda x: -x[1]):
        bar = "█" * int(share * 30)
        marker = " <- DOMINANT" if driver == cross_r["dominant"] else ""
        print(f"  {driver:<10} {share:.3f}  {bar}{marker}")
    print()
    if cross_r["engine_confounded"]:
        print(f"  Note : ENGINE confondu avec REGIME (seul régime actif)")
        print(f"         -> influence ENGINE probablement surestimée")
    if cross_r["feedback_loop"]:
        print(f"  ALERTE : Boucle de retro-action confirmee")
    print(f"\n  Dominant driver : {cross_r['dominant']}")

    # ── [4] TRAJECTOIRE ───────────────────────────────────────────────────────
    print(f"\n{'─'*W}")
    print(f"  [4] TRAJECTOIRE regret_delta")
    print(f"{'─'*W}")
    tr = traj_r
    final = tr.get("final", 0)
    print(f"  Valeur finale    : {final:+d}")
    print(f"  Ticks au max +{_CLAMP}  : {tr['at_max_pct']:.0f}%")
    print(f"  Ticks au min -{_CLAMP}  : {tr['at_min_pct']:.0f}%")
    print(f"  Transitions      : {tr['n_transitions']}")
    print(
        f"  Gelé depuis idx  : {tr['last_change_idx']}"
        f"  ({tr['records_frozen']} records sans changement)"
    )

    if tr.get("transitions"):
        print(f"\n  Chronologie (extrait):")
        for t in tr["transitions"][:12]:
            print(
                f"    {t['dt']}  idx={t['idx']:>5}"
                f"  delta={t['delta']:+d}  raw={t['raw']:+d}  {t['type']}"
            )

    print(f"\n  Recent vs historique:")
    for label, key in [
        ("Ancien (avant 7j)", "older"),
        ("Recent (7 derniers j)", "recent"),
    ]:
        w = tr.get(key, {})
        if not w or w.get("n", 0) == 0:
            print(f"  {label:<30}: aucun record")
            continue
        print(
            f"  {label:<30}: N={w['n']:>4}  "
            f"MW={w['mw']:>4} ({100*w['mw']/max(1,w['n']):.0f}%)  "
            f"GR={w['gr']:>4} ({100*w['gr']/max(1,w['n']):.0f}%)  "
            f"raw_est={w['raw_est']:+d}  => {w['direction']}"
        )

    # ── [5] INTERVENTION TEST ─────────────────────────────────────────────────
    print(f"\n{'─'*W}")
    print(f"  [5] INTERVENTION TEST — Identifiabilité causale")
    print(f"  Shuffle labels, outcomes fixes (marche historique immutable)")
    print(f"  N={intv_r['n_perms']} permutations  |  seuil: p<0.05 => variable causale")
    print(f"{'─'*W}")

    rv = intv_r["regime"]
    ev = intv_r["engine"]

    # Regime
    if rv["p_value"] is None:
        p_str = "N/A"
    else:
        p_str = f"{rv['p_value']:.3f}"
    print(f"  REGIME -> OUTCOME")
    print(f"    Labels distincts : {rv['n_labels']}")
    print(f"    Chi-carre observe : {rv['chi_sq']:.2f}")
    print(f"    p-value (permut) : {p_str}")
    print(f"    Verdict          : {rv['verdict']}")
    if rv["groups"]:
        print(f"    Contingence :")
        for label, v in sorted(
            rv["groups"].items(), key=lambda x: -(x[1]["mw"] + x[1]["gr"])
        ):
            tot = v["mw"] + v["gr"]
            mw_p = 100 * v["mw"] / max(1, tot)
            gr_p = 100 * v["gr"] / max(1, tot)
            print(
                f"      {label:<25}: MW={v['mw']:>4} ({mw_p:.0f}%)"
                f"  GR={v['gr']:>4} ({gr_p:.0f}%)"
            )
    print()

    # Engine
    if ev["p_value"] is None:
        p_str_e = "N/A"
    else:
        p_str_e = f"{ev['p_value']:.3f}"
    print(f"  ENGINE (delta bucket) -> OUTCOME")
    print(f"    Labels distincts : {ev['n_labels']}")
    print(f"    Chi-carre observe : {ev['chi_sq']:.2f}")
    print(f"    p-value (permut) : {p_str_e}")
    print(f"    Verdict          : {ev['verdict']}")
    print()

    # Résumé identifiabilité
    both_id = rv["identifiable"] and ev["identifiable"]
    none_id = not rv["identifiable"] and not ev["identifiable"]
    if rv["p_value"] is None and ev["p_value"] is None:
        id_summary = "NON IDENTIFIABLE — dataset mono-régime / mono-delta. VPS requis."
    elif both_id:
        id_summary = "LES DEUX identifiables — interaction REGIME x ENGINE probable"
    elif rv["identifiable"]:
        id_summary = "REGIME seul identifiable — effet ENGINE non significatif"
    elif ev["identifiable"]:
        id_summary = "ENGINE seul identifiable — effet REGIME non significatif"
    else:
        id_summary = "AUCUN identifiable — dataset insuffisant ou bruit dominant"
    print(f"  Identifiabilite : {id_summary}")

    # ── CONCLUSION ────────────────────────────────────────────────────────────
    print(f"\n{'='*W}")
    print(f"  CONCLUSION")
    print(f"{'='*W}")

    dominant = cross_r["dominant"]
    final_delta = traj_r.get("final", 0)

    # Résoudre incohérence CROSS-ANALYSIS vs INTERVENTION TEST
    # Le test de permutation est plus rigoureux : il prend la priorité
    if intv_r["regime"]["identifiable"] and not intv_r["engine"]["identifiable"]:
        dominant = "REGIME"
    elif intv_r["engine"]["identifiable"] and not intv_r["regime"]["identifiable"]:
        dominant = "ENGINE"
    elif intv_r["regime"]["identifiable"] and intv_r["engine"]["identifiable"]:
        dominant = "INTERACTION"
    # Si aucun identifiable: garder dominant du cross-analysis comme approximation

    if data_r["status"] == "CORROMPUES":
        print(f"  [INVALIDE] Pipeline corrompu — diagnostic non fiable")
    elif dominant == "DATA":
        print(f"  [DONNEES] Problème qualité données — corriger avant toute conclusion")
    elif dominant == "REGIME":
        sig = (
            regime_r["by_regime"].get(regime_r["dominant_regime"], {}).get("signal", "")
        )
        if "INCORRECTS" in sig:
            print(f"  [REGIME] Marché dominant + refus incorrects")
            dom_r = regime_r["dominant_regime"]
            print(
                f"           Le régime {dom_r}"
                " génère des signaux valides refusés à tort"
            )
            print(f"           => Vérifier base_min ou seuil pour ce régime")
        else:
            print(f"  [REGIME] Marché dominant + refus justifiés")
            print("           Les refus sont corrects — alpha absent dans ce régime")
    elif dominant == "ENGINE":
        if cross_r["engine_confounded"]:
            print(
                "  [ENGINE/REGIME] ENGINE identifiable mais confond avec REGIME"
                " (1 seul regime)"
            )
            print("                  Caveat: delta et phase marche correlees")
            print("                  => VPS requis pour separer les deux effets")
        elif cross_r["feedback_loop"]:
            print(f"  [ENGINE] Boucle fermee confirmee (test permutation p<0.05)")
            pct_p = engine_r["plateau_mw_pct"]
            print(f"           delta={final_delta:+d} + MW>{pct_p:.0f}% au plateau")
            print(f"           Sortie : 6 cycles trending / ou intervention manuelle")
        else:
            print("  [ENGINE] Moteur causalement identifiable (p<0.05), pas de boucle")
    elif dominant == "INTERACTION":
        print(f"  [REGIME x ENGINE] Les deux sont causalement identifiables")
        print(
            f"                    Interaction probable — analyse conditionnelle requise"
        )

    print(f"\n  Impact seuils effectifs (delta={final_delta:+d}) :")
    for regime, base in [("sideways", 60), ("bull_trend", 72), ("bear_trend", 68)]:
        eff = max(55, base + final_delta)
        print(f"    {regime:<20}: base={base}  eff_min={eff}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regret Audit v2 — décomposition causale"
    )
    parser.add_argument("--file", default="databases/regret_analysis.jsonl")
    parser.add_argument("--since-days", type=float, default=None)
    parser.add_argument("--window", type=int, default=20)
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"Fichier introuvable : {path}", file=sys.stderr)
        sys.exit(1)

    since_ts = (time.time() - args.since_days * 86400) if args.since_days else 0.0
    records = load_records(path, since_ts)
    enriched = replay(records, window_size=args.window)
    print_report(records, enriched)


if __name__ == "__main__":
    main()
