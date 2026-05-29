"""
dashboard_p6_panel.py — Mini-panel P6 Behavioral Health

5 blocs : régime actuel, threshold drift, oscillation, transitions, BSM/SAFE MODE
Accès   : ssh -L 8501:localhost:8501 user@vps  →  http://localhost:8501
Lancer  : streamlit run dashboard_p6_panel.py
          --server.address 127.0.0.1 --server.port 8501
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

BB_PATH = ROOT / "databases" / "black_box.jsonl"
LOG_PATH = ROOT / "logs" / "advisor.log"
REFRESH_S = 30  # auto-refresh interval

st.set_page_config(
    page_title="P6 Behavioral Health",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Helpers ───────────────────────────────────────────────────────────────────


@st.cache_data(ttl=REFRESH_S)
def load_black_box(n: int = 500) -> list[dict]:
    if not BB_PATH.exists():
        return []
    rows = []
    try:
        with open(BB_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return rows[-n:]


@st.cache_data(ttl=REFRESH_S)
def load_behavior_lines(n: int = 200) -> list[dict]:
    """Parse [BEHAVIOR] lines from advisor.log."""
    if not LOG_PATH.exists():
        return []
    pattern = re.compile(
        r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*"
        r"\[BEHAVIOR\]\s+"
        r"avg_thr=(?P<avg_thr>\d+)\s+std=(?P<std>[\d.]+)\s+flips=(?P<flips>\d+)"
        r".*trans=(?P<trans>\d+)"
        r".*avg_score=(?P<avg_score>\d+)\s+mismatch=(?P<mismatch>\d+)"
        r".*state=(?P<state>\w+)\s+osc=(?P<osc>\w+)"
    )
    results = []
    try:
        with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = pattern.search(line)
                if m:
                    results.append(
                        {
                            "ts": m.group("ts"),
                            "avg_thr": int(m.group("avg_thr")),
                            "std": float(m.group("std")),
                            "flips": int(m.group("flips")),
                            "trans": int(m.group("trans")),
                            "avg_score": int(m.group("avg_score")),
                            "mismatch": int(m.group("mismatch")),
                            "state": m.group("state"),
                            "osc": m.group("osc"),
                        }
                    )
    except OSError:
        pass
    return results[-n:]


def regime_transitions(rows: list[dict]) -> list[dict]:
    """Detect regime changes in black_box rows."""
    transitions = []
    prev = None
    for r in rows:
        reg = r.get("regime")
        if reg and reg != "unknown" and reg != prev:
            if prev is not None:
                transitions.append(
                    {
                        "ts": datetime.fromtimestamp(r["ts"]).strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                        "from": prev,
                        "to": reg,
                        "cycle": r.get("cycle", "?"),
                    }
                )
            prev = reg
    return transitions[-10:]  # last 10


def p6_safe_mode() -> bool:
    val = os.getenv("P6_SAFE_MODE", "false").lower()
    return val in ("true", "1", "yes")


OCC_COLORS = {
    "LOW": "#28a745",
    "MED": "#fd7e14",
    "HIGH": "#dc3545",
}

STATE_COLORS = {
    "stable": "#28a745",
    "oscillating": "#fd7e14",
    "drifting": "#ffc107",
    "frozen": "#6c757d",
    "degraded": "#dc3545",
}

REGIME_LABELS = {
    "sideways": "↔ Sideways",
    "bull_trend": "↑ Bull",
    "bear_trend": "↓ Bear",
    "mean_reversion": "↺ MeanRev",
    "high_volatility": "⚡ VolatHigh",
    "low_volatility": "💤 VolatLow",
    "unknown": "? Unknown",
}

# ── Layout ────────────────────────────────────────────────────────────────────

st.title("🧠 P6 — Behavioral Health Monitor")

_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
safe_mode = p6_safe_mode()
sm_badge = "🔴 SAFE MODE" if safe_mode else "🟢 ADAPTATIF"
st.caption(f"Mise à jour : {_ts}  ·  Mode : {sm_badge}  ·  Refresh : {REFRESH_S}s")

rows = load_black_box()
blines = load_behavior_lines()

# ────────────────────────────────────────────────────────────────────────────
# BLOC 1 + BLOC 3 (row 1)
# ────────────────────────────────────────────────────────────────────────────
col1, col3 = st.columns([2, 1])

with col1:
    st.subheader("Régime actuel")
    if rows:
        # Filtre entrées avec régime réel
        reg_rows = [r for r in rows if r.get("regime") and r["regime"] != "unknown"]
        if reg_rows:
            current_regime = reg_rows[-1]["regime"]
            current_cycle = reg_rows[-1].get("cycle", "?")
            label = REGIME_LABELS.get(current_regime, current_regime)
            st.metric("Régime", label, delta=f"cycle {current_cycle}")

            # Distribution sur les 200 dernières entrées
            recent = reg_rows[-200:]
            counts = Counter(r["regime"] for r in recent)
            total = sum(counts.values())
            dist_df = pd.DataFrame(
                [
                    {
                        "régime": REGIME_LABELS.get(k, k),
                        "pct": round(v / total * 100, 1),
                        "n": v,
                    }
                    for k, v in sorted(counts.items(), key=lambda x: -x[1])
                ]
            )
            st.dataframe(dist_df, use_container_width=True, hide_index=True)
        else:
            st.info("Aucune donnée régime disponible")
    else:
        st.warning("black_box.jsonl introuvable ou vide")

with col3:
    st.subheader("Oscillation")
    if blines:
        last_b = blines[-1]
        osc = last_b["osc"]
        color = OCC_COLORS.get(osc, "#ffffff")
        st.markdown(
            f"<h1 style='color:{color}; text-align:center'>{osc}</h1>",
            unsafe_allow_html=True,
        )
        st.metric("Flips threshold (50c)", last_b["flips"])
        st.metric("Std threshold", last_b["std"])
        st.metric("Avg threshold", last_b["avg_thr"])
        st.metric("Mismatch total", last_b["mismatch"])
    else:
        st.info("En attente du premier\ncycle 50…")
        st.caption("Les données [BEHAVIOR] sont\ngénérées toutes les 50 cycles")

# ────────────────────────────────────────────────────────────────────────────
# BLOC 2 — Threshold drift chart
# ────────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Threshold drift")

if blines:
    df_thr = pd.DataFrame(blines)[["ts", "avg_thr", "std"]].copy()
    df_thr["ts"] = pd.to_datetime(df_thr["ts"])
    df_thr = df_thr.set_index("ts")
    st.line_chart(df_thr[["avg_thr"]], use_container_width=True)
    st.caption(
        f"{len(blines)} snapshots [BEHAVIOR]  ·  "
        f"Dernier avg_thr={blines[-1]['avg_thr']}  ·  "
        f"std={blines[-1]['std']}"
    )
else:
    st.info(
        "Aucune donnée [BEHAVIOR] encore.  "
        "Le premier snapshot arrive après 50 cycles (~3-4h selon le polling)."
    )

# ────────────────────────────────────────────────────────────────────────────
# BLOC 4 + BLOC 5 (row 3)
# ────────────────────────────────────────────────────────────────────────────
st.divider()
col4, col5 = st.columns([2, 1])

with col4:
    st.subheader("Transitions régime récentes")
    if rows:
        transitions = regime_transitions(rows)
        if transitions:
            df_tr = pd.DataFrame(transitions)
            st.dataframe(df_tr, use_container_width=True, hide_index=True)
        else:
            st.success("Aucune transition — régime stable sur toute la fenêtre")
    else:
        st.warning("Pas de données")

with col5:
    st.subheader("État BSM / SAFE MODE")
    if blines:
        last_b = blines[-1]
        state = last_b["state"]
        color = STATE_COLORS.get(state, "#ffffff")
        st.markdown(
            f"<h2 style='color:{color}'>{state.upper()}</h2>",
            unsafe_allow_html=True,
        )
        st.metric("Avg score accepté", last_b["avg_score"])
        st.metric("Transitions (fenêtre)", last_b["trans"])
        st.metric("Snapshots [BEHAVIOR]", len(blines))
    else:
        st.info("En attente de données BSM")

    # SAFE MODE status
    st.divider()
    if safe_mode:
        st.error("P6_SAFE_MODE=true\nBoucles adaptatives DÉSACTIVÉES")
    else:
        st.success("P6_SAFE_MODE=false\nMode adaptatif actif")

# ────────────────────────────────────────────────────────────────────────────
# Score distribution (bonus, bas de page)
# ────────────────────────────────────────────────────────────────────────────
st.divider()
with st.expander("Distribution des scores (black_box)", expanded=False):
    if rows:
        scores = [r["score"] for r in rows if r.get("score", 0) > 0]
        if scores:
            df_sc = pd.DataFrame({"score": scores})
            st.bar_chart(df_sc["score"].value_counts().sort_index())
            avg = sum(scores) / len(scores)
            st.caption(
                f"N={len(scores)}  ·  avg={avg:.1f}"
                f"  ·  min={min(scores)}  max={max(scores)}"
            )
        else:
            st.info("Aucun score > 0")

# ── Auto-refresh ──────────────────────────────────────────────────────────────
time.sleep(REFRESH_S)
st.rerun()
