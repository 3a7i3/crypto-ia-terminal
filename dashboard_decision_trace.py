"""
dashboard_decision_trace.py — Decision Trace Dashboard

Observabilité cognitive du lifecycle décisionnel.
Lit depuis : databases/decision_packets.jsonl

Lancer avec : streamlit run dashboard_decision_trace.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Decision Trace",
    layout="wide",
    page_icon="🧠",
    initial_sidebar_state="expanded",
)

# ── Styles ────────────────────────────────────────────────────────────────────

st.markdown(
    """
<style>
.stApp { background: #0a0c12; color: #d0d4e0; }
.stTabs [data-baseweb="tab-list"] { background: #111420; border-radius: 8px; }
.stTabs [data-baseweb="tab"] { color: #8899aa; }
.stTabs [data-baseweb="tab"][aria-selected="true"] { color: #00e0ff; }
.state-badge {
    display: inline-block; padding: 2px 10px; border-radius: 4px;
    font-size: 0.75rem; font-weight: 600; margin: 1px 2px;
    font-family: monospace;
}
.badge-green  { background: #0d2e1a; color: #22cc66; border: 1px solid #1a5c33; }
.badge-red    { background: #2e0d0d; color: #ff4455; border: 1px solid #5c1a1a; }
.badge-yellow { background: #2e260d; color: #ffcc22; border: 1px solid #5c4a1a; }
.badge-blue   { background: #0d1a2e; color: #4499ff; border: 1px solid #1a3a5c; }
.badge-gray   { background: #1a1e2a; color: #8899aa; border: 1px solid #2a3040; }
.badge-fatal  { background: #3a0000; color: #ff2200; border: 1px solid #880000; }
.section-header {
    font-size: 0.7rem; font-weight: 700; color: #445566;
    letter-spacing: 0.12em; text-transform: uppercase;
    margin-bottom: 0.3rem; margin-top: 1rem;
}
</style>
""",
    unsafe_allow_html=True,
)

# ── Config ────────────────────────────────────────────────────────────────────

# Résolution du fichier source — même logique que advisor_loop.py.
# DP_LOG_PATH explicite → prioritaire (compat).
# Sinon DP_LOG_DIR → fichiers datés decision_packets_YYYY-MM-DD.jsonl.
_EXPLICIT_PATH = os.getenv("DP_LOG_PATH")
_LOG_DIR = Path(os.getenv("DP_LOG_DIR", "databases"))


def _available_dated_files() -> list[Path]:
    """Retourne les fichiers de trace datés, triés du plus récent au plus ancien."""
    if not _LOG_DIR.exists():
        return []
    return sorted(_LOG_DIR.glob("decision_packets_*.jsonl"), reverse=True)


def _resolve_dp_path(selected_date: str | None = None) -> Path:
    if _EXPLICIT_PATH:
        return Path(_EXPLICIT_PATH)
    if selected_date:
        return _LOG_DIR / f"decision_packets_{selected_date}.jsonl"
    # Fallback : fichier du jour UTC
    from datetime import datetime as _dt

    return _LOG_DIR / f"decision_packets_{_dt.utcnow().strftime('%Y-%m-%d')}.jsonl"


_STATE_COLOR = {
    "CREATED": "gray",
    "SIGNAL_GENERATED": "blue",
    "CONTEXT_ENRICHED": "blue",
    "REGIME_VALIDATED": "blue",
    "RISK_EVALUATED": "blue",
    "APPROVED": "green",
    "EXECUTION_PENDING": "green",
    "EXECUTED": "green",
    "MONITORED": "green",
    "CLOSED": "green",
    "POSTMORTEM_ANALYZED": "green",
    "REJECTED": "red",
    "VETOED": "fatal",
    "EXPIRED": "yellow",
    "CANCELLED": "yellow",
    "FAILED": "red",
}

_SEVERITY_COLOR = {
    "INFO": "#4499ff",
    "WARNING": "#ffcc22",
    "CRITICAL": "#ff8800",
    "FATAL": "#ff2200",
}

_SOVEREIGNTY = [
    ("live_signal_engine", "advisory_only", "Détecte une opportunité statistique"),
    (
        "conviction_engine",
        "advisory_only",
        "Enrichit cognitivement — opinion non contraignante",
    ),
    ("no_trade_layer", "advisory_only (vote)", "Filtre pré-packet via AgentVote"),
    ("global_risk_gate", "reject_authority", "Seul autorisé à reject() en flux normal"),
    (
        "portfolio_brain",
        "allocation_authority",
        "Approuve ou rejette selon l'équilibre portefeuille",
    ),
    ("order_sizer", "sizing_authority", "Traduit en taille opérationnelle"),
    ("execution_engine", "capital_authority", "Engage le capital réel"),
    ("kill_switch", "veto_authority", "Veto global depuis n'importe quel état"),
]


# ── Chargement données ────────────────────────────────────────────────────────


@st.cache_data(ttl=5)
def load_packets(dp_path: str) -> list[dict]:
    p = Path(dp_path)
    if not p.exists():
        return []
    packets = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    packets.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return packets[-500:]


def packet_label(p: dict) -> str:
    ts = p.get("created_at", "")[:19].replace("T", " ")
    return f"{ts}  {p.get('symbol','?')}  {p.get('side','?')}  → {p.get('lifecycle_state','?')}"


def badge(text: str, color: str) -> str:
    return f'<span class="state-badge badge-{color}">{text}</span>'


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🧠 Decision Trace")
    st.markdown("---")
    auto_refresh = st.checkbox("Auto-refresh (5s)", value=False)
    if auto_refresh:
        st.rerun()

    # Sélecteur de date (rotation quotidienne)
    if _EXPLICIT_PATH:
        _selected_path = str(_resolve_dp_path())
        st.caption(f"Source : `{_EXPLICIT_PATH}`")
    else:
        _dated = _available_dated_files()
        if _dated:
            _date_labels = [p.stem.replace("decision_packets_", "") for p in _dated]
            _sel_label = st.selectbox("Date (UTC)", _date_labels, index=0)
            _selected_path = str(_resolve_dp_path(_sel_label))
        else:
            _selected_path = str(_resolve_dp_path())
        st.caption(f"Source : `{_selected_path}`")

    packets = load_packets(_selected_path)
    st.markdown(f"**{len(packets)}** packets chargés")

    if not packets:
        st.warning("Aucun packet — lancer le bot pour générer des données.")
        st.stop()

    # Filtres
    st.markdown("### Filtres")
    symbols = sorted({p.get("symbol", "?") for p in packets})
    sel_symbol = st.selectbox("Symbole", ["Tous"] + symbols)
    states = sorted({p.get("lifecycle_state", "?") for p in packets})
    sel_state = st.selectbox("État final", ["Tous"] + states)

    filtered = packets
    if sel_symbol != "Tous":
        filtered = [p for p in filtered if p.get("symbol") == sel_symbol]
    if sel_state != "Tous":
        filtered = [p for p in filtered if p.get("lifecycle_state") == sel_state]

    st.markdown(f"**{len(filtered)}** packets filtrés")

    # Sélection packet individuel
    st.markdown("### Packet sélectionné")
    packet_labels = [packet_label(p) for p in reversed(filtered)]
    sel_idx = st.selectbox(
        "Packet", range(len(packet_labels)), format_func=lambda i: packet_labels[i]
    )
    selected = list(reversed(filtered))[sel_idx] if filtered else None


# ── Métriques globales ────────────────────────────────────────────────────────

st.markdown("# Decision Trace")

if filtered:
    total = len(filtered)
    rejected = sum(
        1 for p in filtered if p.get("lifecycle_state") in ("REJECTED", "VETOED")
    )
    approved = sum(1 for p in filtered if p.get("lifecycle_state") == "APPROVED")
    executed = sum(1 for p in filtered if p.get("lifecycle_state") == "EXECUTED")
    avg_conf = sum(p.get("confidence", 0) for p in filtered) / total

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Packets", total)
    c2.metric("Rejetés", rejected, f"{rejected/total:.0%}")
    c3.metric("Approuvés", approved, f"{approved/total:.0%}")
    c4.metric("Exécutés", executed)
    c5.metric("Conf. moy.", f"{avg_conf:.1f}")

st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["⟶ Timeline", "~ Confidence", "≡ Reasoning", "✗ Rejets", "⊕ Sovereignty"]
)


# ══ Zone 1 — Decision Timeline ════════════════════════════════════════════════

with tab1:
    if not selected:
        st.info("Sélectionner un packet dans la sidebar.")
    else:
        p = selected
        col_meta, col_timeline = st.columns([1, 2])

        with col_meta:
            st.markdown(
                '<p class="section-header">Identité</p>', unsafe_allow_html=True
            )
            st.markdown(f"**Packet** `{p.get('packet_id','?')[:16]}`")
            st.markdown(f"**Symbole** {p.get('symbol','?')} — {p.get('side','?')}")
            st.markdown(f"**Régime** `{p.get('regime','?')}`")
            st.markdown(f"**Conviction** `{p.get('conviction','?')}`")

            final_state = p.get("lifecycle_state", "?")
            color = _STATE_COLOR.get(final_state, "gray")
            st.markdown(
                f"**État final** {badge(final_state, color)}",
                unsafe_allow_html=True,
            )
            st.markdown(f"**Confiance finale** {p.get('confidence', 0):.1f} / 100")

            # Features portefeuille
            feats = p.get("features", {})
            if any(k.startswith("pb_") for k in feats):
                st.markdown(
                    '<p class="section-header">Portfolio</p>', unsafe_allow_html=True
                )
                if "pb_exposure_pct" in feats:
                    st.metric("Exposition", f"{feats['pb_exposure_pct']*100:.1f}%")
                if "pb_corr_risk" in feats:
                    st.metric("Corrélation", f"{feats['pb_corr_risk']:.2f}")
                if "pb_symbol_pct" in feats:
                    st.metric("Concentration", f"{feats['pb_symbol_pct']*100:.1f}%")

            meta = p.get("metadata", {})
            if "pb_size_factor" in meta:
                st.metric("Size factor", f"×{meta['pb_size_factor']:.2f}")

        with col_timeline:
            st.markdown(
                '<p class="section-header">Lifecycle</p>', unsafe_allow_html=True
            )
            history = p.get("state_history", [])
            if not history:
                st.info("Aucune transition enregistrée.")
            else:
                for i, t in enumerate(history):
                    color = _STATE_COLOR.get(t.get("to_state", ""), "gray")
                    dur = t.get("duration_ms", 0)
                    cb = t.get("confidence_before", 0.0)
                    ca = t.get("confidence_after", 0.0)
                    delta = ca - cb
                    delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
                    dur_str = f"{dur}ms" if dur < 2000 else f"{dur/1000:.1f}s"

                    st.markdown(
                        f'{badge(t.get("to_state","?"), color)} '
                        f'<span style="color:#445566;font-size:0.75rem">'
                        f'by **{t.get("actor","?")}** — {dur_str} — '
                        f"conf {cb:.0f}→{ca:.0f} ({delta_str})"
                        f"</span>",
                        unsafe_allow_html=True,
                    )
                    reason = t.get("reason", "")
                    if reason:
                        st.markdown(
                            f'<span style="color:#556677;font-size:0.72rem;padding-left:1.5rem">'
                            f"↳ {reason[:120]}</span>",
                            unsafe_allow_html=True,
                        )
                    if i < len(history) - 1:
                        st.markdown(
                            '<span style="color:#2a3040;padding-left:0.5rem">│</span>',
                            unsafe_allow_html=True,
                        )


# ══ Zone 2 — Confidence Evolution ════════════════════════════════════════════

with tab2:
    if not selected:
        st.info("Sélectionner un packet dans la sidebar.")
    else:
        reasoning = selected.get("reasoning", [])
        if not reasoning:
            st.info("Aucun raisonnement enregistré pour ce packet.")
        else:
            entries = [r for r in reasoning if r.get("confidence_impact", 0) != 0]
            if not entries:
                st.info("Aucun impact de confiance enregistré.")
            else:
                labels = [
                    f"{r.get('actor','?')}<br><span style='font-size:10px'>{r.get('category','?')}</span>"
                    for r in entries
                ]
                impacts = [r.get("confidence_impact", 0) for r in entries]
                colors = ["#22cc66" if v >= 0 else "#ff4455" for v in impacts]
                severities = [r.get("severity", "INFO") for r in entries]

                # Calcul du running total
                init_conf = (
                    selected.get("state_history", [{}])[0].get("confidence_before", 0)
                    if selected.get("state_history")
                    else 0
                )
                running = [init_conf]
                for v in impacts:
                    running.append(max(0, min(100, running[-1] + v)))

                fig = go.Figure()
                fig.add_trace(
                    go.Bar(
                        x=list(range(len(entries))),
                        y=impacts,
                        marker_color=colors,
                        text=[f"{'+' if v >= 0 else ''}{v:.1f}" for v in impacts],
                        textposition="outside",
                        hovertemplate=[
                            f"<b>{r.get('actor','?')}</b><br>"
                            f"Category: {r.get('category','?')}<br>"
                            f"Severity: {r.get('severity','INFO')}<br>"
                            f"Impact: {r.get('confidence_impact',0):+.1f}<br>"
                            f"Message: {r.get('message','')[:80]}<extra></extra>"
                            for r in entries
                        ],
                        name="Impact",
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=list(range(-1, len(entries) + 1)),
                        y=[running[0]] + running,
                        mode="lines",
                        line=dict(color="#00e0ff", width=1.5, dash="dot"),
                        name="Confiance cumulée",
                    )
                )
                fig.update_layout(
                    paper_bgcolor="#0a0c12",
                    plot_bgcolor="#0e1117",
                    font=dict(color="#8899aa", size=11),
                    xaxis=dict(
                        tickvals=list(range(len(entries))),
                        ticktext=[r.get("actor", "?") for r in entries],
                        tickangle=-30,
                        gridcolor="#1a1e2a",
                    ),
                    yaxis=dict(
                        title="Impact confiance",
                        gridcolor="#1a1e2a",
                        zeroline=True,
                        zerolinecolor="#334455",
                    ),
                    showlegend=True,
                    legend=dict(bgcolor="#111420", bordercolor="#2a3040"),
                    height=380,
                    margin=dict(t=20, b=80, l=60, r=20),
                )
                st.plotly_chart(fig, use_container_width=True)

                # Table détail
                df = pd.DataFrame(
                    [
                        {
                            "Actor": r.get("actor", "?"),
                            "Category": r.get("category", "?"),
                            "Severity": r.get("severity", "INFO"),
                            "Impact": r.get("confidence_impact", 0),
                            "Message": r.get("message", "")[:100],
                        }
                        for r in entries
                    ]
                )
                st.dataframe(df, use_container_width=True, hide_index=True)


# ══ Zone 3 — Reasoning Feed ══════════════════════════════════════════════════

with tab3:
    if not selected:
        all_reasoning = []
        for pkt in filtered[-50:]:
            for r in pkt.get("reasoning", []):
                all_reasoning.append(
                    {
                        **r,
                        "_symbol": pkt.get("symbol", "?"),
                        "_state": pkt.get("lifecycle_state", "?"),
                        "_packet_id": pkt.get("packet_id", "?")[:8],
                    }
                )
        source_label = f"50 derniers packets filtrés ({len(all_reasoning)} entrées)"
    else:
        all_reasoning = [
            {
                **r,
                "_symbol": selected.get("symbol", "?"),
                "_state": selected.get("lifecycle_state", "?"),
                "_packet_id": selected.get("packet_id", "?")[:8],
            }
            for r in selected.get("reasoning", [])
        ]
        source_label = f"Packet sélectionné ({len(all_reasoning)} entrées)"

    st.markdown(f'<p class="section-header">{source_label}</p>', unsafe_allow_html=True)

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        actors = sorted({r.get("actor", "?") for r in all_reasoning})
        sel_actor = st.multiselect("Actor", actors, default=actors)
    with col_f2:
        cats = sorted({r.get("category", "?") for r in all_reasoning})
        sel_cat = st.multiselect("Category", cats, default=cats)
    with col_f3:
        sevs = ["INFO", "WARNING", "CRITICAL", "FATAL"]
        sel_sev = st.multiselect("Severity", sevs, default=sevs)

    feed = [
        r
        for r in all_reasoning
        if r.get("actor", "?") in sel_actor
        and r.get("category", "?") in sel_cat
        and r.get("severity", "INFO") in sel_sev
    ]

    if not feed:
        st.info("Aucune entrée correspondant aux filtres.")
    else:
        for r in reversed(feed[-100:]):
            sev = r.get("severity", "INFO")
            color = _SEVERITY_COLOR.get(sev, "#8899aa")
            impact = r.get("confidence_impact", 0)
            impact_str = (
                f"+{impact:.1f}"
                if impact > 0
                else (f"{impact:.1f}" if impact < 0 else "")
            )
            impact_color = (
                "#22cc66" if impact > 0 else ("#ff4455" if impact < 0 else "#445566")
            )
            st.markdown(
                f'<div style="border-left:3px solid {color};padding:4px 10px;'
                f'margin:2px 0;background:#0e1117;border-radius:0 4px 4px 0">'
                f'<span style="color:{color};font-size:0.7rem;font-weight:700">{sev}</span>'
                f'&nbsp;&nbsp;<span style="color:#6677aa;font-size:0.7rem">'
                f'{r.get("actor","?")} · {r.get("category","?")}</span>'
                f'&nbsp;&nbsp;<span style="color:{impact_color};font-size:0.7rem;font-weight:700">'
                f"{impact_str}</span>"
                f'<br><span style="color:#aabbcc;font-size:0.8rem">{r.get("message","")}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )


# ══ Zone 4 — Rejected Opportunities ══════════════════════════════════════════

with tab4:
    st.markdown(
        '<p class="section-header">Signaux rejetés — opportunités manquées potentielles</p>',
        unsafe_allow_html=True,
    )

    rejected_packets = [
        p
        for p in filtered
        if p.get("lifecycle_state") in ("REJECTED", "VETOED", "EXPIRED")
    ]

    if not rejected_packets:
        st.info("Aucun packet rejeté dans la sélection.")
    else:
        rows = []
        for p in reversed(rejected_packets[-200:]):
            hist = p.get("state_history", [])
            reject_entry = next(
                (
                    t
                    for t in reversed(hist)
                    if t.get("to_state") in ("REJECTED", "VETOED", "EXPIRED")
                ),
                {},
            )
            reject_reasoning = [
                r
                for r in p.get("reasoning", [])
                if "[REJECTED]" in r.get("message", "")
                or "[VETO]" in r.get("message", "")
            ]
            reason = reject_entry.get(
                "reason",
                reject_reasoning[0].get("message", "?") if reject_reasoning else "?",
            )
            rejector = reject_entry.get("actor", "?")
            ts = p.get("created_at", "")[:19].replace("T", " ")

            rows.append(
                {
                    "Timestamp": ts,
                    "Symbole": p.get("symbol", "?"),
                    "Side": p.get("side", "?"),
                    "Régime": p.get("regime", "?"),
                    "Conf finale": round(p.get("confidence", 0), 1),
                    "Conviction": p.get("conviction", "?"),
                    "Rejeté par": rejector,
                    "Raison": reason[:80] if reason else "?",
                    "État": p.get("lifecycle_state", "?"),
                }
            )

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True, height=400)

        # Distribution par acteur
        if len(rows) > 1:
            st.markdown(
                '<p class="section-header">Distribution des rejets par acteur</p>',
                unsafe_allow_html=True,
            )
            by_actor = df["Rejeté par"].value_counts()
            fig = go.Figure(
                go.Bar(
                    x=by_actor.index.tolist(),
                    y=by_actor.values.tolist(),
                    marker_color="#ff4455",
                    text=by_actor.values.tolist(),
                    textposition="outside",
                )
            )
            fig.update_layout(
                paper_bgcolor="#0a0c12",
                plot_bgcolor="#0e1117",
                font=dict(color="#8899aa"),
                height=250,
                xaxis=dict(gridcolor="#1a1e2a"),
                yaxis=dict(gridcolor="#1a1e2a"),
                margin=dict(t=10, b=40, l=40, r=20),
            )
            st.plotly_chart(fig, use_container_width=True)


# ══ Zone 5 — System Sovereignty Map ══════════════════════════════════════════

with tab5:
    st.markdown(
        '<p class="section-header">Hiérarchie institutionnelle des autorités</p>',
        unsafe_allow_html=True,
    )

    _AUTH_COLOR = {
        "advisory_only": "#4499ff",
        "advisory_only (vote)": "#4499ff",
        "reject_authority": "#ffcc22",
        "allocation_authority": "#ff8800",
        "sizing_authority": "#ff8800",
        "capital_authority": "#ff4455",
        "veto_authority": "#ff0033",
    }

    for actor, authority, description in _SOVEREIGNTY:
        color = _AUTH_COLOR.get(authority, "#8899aa")
        st.markdown(
            f'<div style="display:flex;align-items:center;padding:6px 12px;'
            f"margin:3px 0;background:#0e1117;border-radius:6px;"
            f'border-left:3px solid {color}">'
            f'<span style="color:#aabbcc;font-weight:600;font-family:monospace;'
            f'min-width:200px">{actor}</span>'
            f'<span style="color:{color};font-size:0.75rem;font-weight:700;'
            f'min-width:220px;padding:0 16px">{authority}</span>'
            f'<span style="color:#667788;font-size:0.78rem">{description}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown(
        '<p class="section-header">Séparations institutionnelles critiques</p>',
        unsafe_allow_html=True,
    )

    separations = [
        (
            "risk_gate ≠ portfolio_brain",
            "risk_gate protège le système (signal, régime, session). "
            "portfolio_brain protège le portefeuille (exposition, corrélation, concentration).",
        ),
        (
            "advisory ≠ governance",
            "LSE et conviction produisent des opinions. "
            "risk_gate et portfolio_brain produisent des décisions souveraines.",
        ),
        (
            "RISK_EVALUATED ≠ APPROVED",
            "L'évaluation et l'autorisation sont deux actes distincts. "
            "portfolio_brain peut refuser après risk_gate.",
        ),
        (
            "APPROVED ≠ EXECUTED",
            "Espace pour queues, throttling, failover, shadow approval.",
        ),
        (
            "terminaux exceptionnels ≠ terminal nominal",
            "REJECTED/VETOED/EXPIRED = mort prématurée. "
            "POSTMORTEM_ANALYZED = complétion normale. "
            "Seuls les terminaux exceptionnels contournent le graphe.",
        ),
    ]

    for title, desc in separations:
        st.markdown(
            f'<div style="padding:8px 14px;margin:4px 0;background:#0e1117;'
            f'border-radius:6px;border-left:3px solid #334455">'
            f'<span style="color:#00e0ff;font-weight:600;font-size:0.82rem">{title}</span>'
            f'<br><span style="color:#667788;font-size:0.78rem">{desc}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )

    # Stats de souveraineté depuis les données réelles
    if filtered:
        st.markdown(
            '<p class="section-header">Exercice réel de souveraineté</p>',
            unsafe_allow_html=True,
        )
        actor_counts: dict[str, int] = {}
        for p in filtered:
            for t in p.get("state_history", []):
                if t.get("to_state") in ("REJECTED", "VETOED"):
                    a = t.get("actor", "unknown")
                    actor_counts[a] = actor_counts.get(a, 0) + 1
        if actor_counts:
            df_sov = pd.DataFrame(
                [
                    {"Actor": a, "Rejets souverains": n}
                    for a, n in sorted(actor_counts.items(), key=lambda x: -x[1])
                ]
            )
            st.dataframe(df_sov, use_container_width=True, hide_index=True)
        else:
            st.info("Aucun rejet souverain dans les données actuelles.")
