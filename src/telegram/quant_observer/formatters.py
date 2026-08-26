"""Presentation layer for @QuantCrypto_bot text commands.

Pure functions: SDOS Data API snapshot in, Telegram-HTML string out. No I/O, no
database access, no business logic — the API computes, this module only shapes
for a phone screen (narrow rows, monospace alignment, bounded length).

Deliberately free of any `visualization.renderers` import: that package pulls
matplotlib at module scope, which a text-only command must not pay for.
"""

from __future__ import annotations

import html
from typing import Optional

# Telegram hard-caps a message at 4096 chars.
TG_MAX_CHARS = 4096
_CLIP_MARGIN = 120

_BAR_FULL = "█"
_BAR_EMPTY = "░"


# ── Primitives ────────────────────────────────────────────────────────────────


def esc(text: object) -> str:
    """HTML-escape any value before it enters a Telegram HTML message."""
    return html.escape(str(text), quote=False)


def bar(pct: float, width: int = 10) -> str:
    """ASCII progress bar, clamped to [0, 100]."""
    pct = max(0.0, min(100.0, float(pct)))
    filled = round(pct / 100 * width)
    return _BAR_FULL * filled + _BAR_EMPTY * (width - filled)


def icon(ok: bool, warn: bool = False) -> str:
    if ok:
        return "✅"
    return "⚠️" if warn else "🚨"


def clip(text: str, limit: int = TG_MAX_CHARS) -> str:
    """Truncate on a line boundary so HTML tags are never cut mid-token."""
    if len(text) <= limit:
        return text
    budget = limit - _CLIP_MARGIN
    kept: list[str] = []
    used = 0
    for line in text.split("\n"):
        if used + len(line) + 1 > budget:
            break
        kept.append(line)
        used += len(line) + 1
    kept.append("")
    kept.append("<i>… tronqué (limite Telegram)</i>")
    return "\n".join(kept)


def _threshold_row(label: str, value: int, minimum: int) -> str:
    """`label  bar  value/min  icon` — progress toward a constitutional gate."""
    pct = 100.0 if minimum <= 0 else value / minimum * 100
    return (
        f"<code>{label:<9}{bar(pct, 8)} {value:>4}/{minimum:<4}</code>"
        f"{icon(value >= minimum, pct >= 50)}"
    )


def _top_rows(counts: dict, limit: int = 5, total: Optional[int] = None) -> list[str]:
    """Top-N `key  count (pct)` rows from a count mapping, largest first."""
    if not counts:
        return ["<code>  (aucune donnée)</code>"]
    denom = total if total else sum(counts.values())
    rows = []
    for key, count in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[
        :limit
    ]:
        pct = f" {count / denom * 100:>5.1f}%" if denom else ""
        rows.append(f"<code>  {esc(key)[:20]:<20}{count:>5}{pct}</code>")
    return rows


def _ts(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") + " UTC" if dt else "—"


# ── Burn-in ───────────────────────────────────────────────────────────────────


def format_burnin(snap) -> str:
    """Progress against the statistician thresholds (CLAUDE.md)."""
    cri_txt = f"{snap.cri:.1f}/{snap.cri_min}" if snap.cri is not None else "non mesuré"
    cri_ok = snap.cri is not None and snap.cri >= snap.cri_min

    lines = [
        "🧪 <b>BURN-IN</b> — seuils du statisticien",
        f"<i>{_ts(snap.generated_at)}</i>",
        "",
        _threshold_row("Trades", snap.trades_count, snap.trades_min),
        _threshold_row("Winners", snap.wins, snap.wins_min),
        _threshold_row("Losers", snap.losses, snap.losses_min),
        _threshold_row("MissedW", snap.missed_win_count, snap.missed_win_min),
        _threshold_row("GoodRef", snap.good_refusal_count, snap.good_refusal_min),
        "",
        f"<code>CRI      {cri_txt:<14}</code>{icon(cri_ok)}",
        f"<code>Par régime  min {snap.per_regime_min}  |  "
        f"par couche  min {snap.per_layer_min}</code>",
        "",
        "<b>PERFORMANCE</b>",
        f"<code>WR {snap.win_rate_pct:.1f}%  PF {snap.profit_factor:.2f}  "
        f"E {snap.expectancy_pct:+.2f}%</code>",
        f"<code>Couverture {snap.coverage_pct:.1f}%</code>",
        "",
        f"<b>GO/NO-GO :</b> {esc(snap.go_no_go)}",
        (
            "🔒 Calibration VERROUILLÉE (FEATURE_AUTO_CALIBRATION=false)"
            if snap.calibration_locked
            else "🔓 <b>Calibration DÉVERROUILLÉE</b> — ADR requis !"
        ),
    ]

    if snap.blockers:
        lines += ["", "<b>BLOQUEURS</b>"]
        lines += [f"<code>  • {esc(b)[:60]}</code>" for b in snap.blockers[:6]]
    if snap.warnings:
        lines += ["", "<b>AVERTISSEMENTS</b>"]
        lines += [f"<code>  • {esc(w)[:60]}</code>" for w in snap.warnings[:4]]

    return clip("\n".join(lines))


# ── CRI ───────────────────────────────────────────────────────────────────────

_SUB_SCORE_LABELS = {
    "n_score": "N",
    "coverage_score": "Couverture",
    "drift_score": "Drift",
    "balance_score": "Équilibre",
}


def format_cri(snap) -> str:
    """Calibration Readiness Index + dataset provenance."""
    if snap.cri is None:
        return clip(
            "\n".join(
                [
                    "📐 <b>CRI</b> — Calibration Readiness Index",
                    "",
                    "🚨 <b>NON MESURABLE</b>",
                    f"<code>{esc(snap.error or 'raison inconnue')[:200]}</code>",
                    "",
                    "<i>Un CRI absent n'est pas un CRI de 0 : "
                    "aucune conclusion ne peut en être tirée.</i>",
                ]
            )
        )

    gate = icon(snap.gate_ready)
    lines = [
        "📐 <b>CRI</b> — Calibration Readiness Index",
        "",
        f"<code>{bar(snap.cri, 12)}</code>",
        f"<b>{snap.cri:.2f}</b> / {snap.cri_min} requis  {gate}",
        (
            "✅ Gate de calibration ATTEINTE"
            if snap.gate_ready
            else "🔒 Gate NON atteinte — ACE interdit"
        ),
        "",
        "<b>SOUS-SCORES</b>",
    ]

    for key, value in snap.sub_scores.items():
        label = _SUB_SCORE_LABELS.get(key, key)
        weight = snap.weights.get(key.replace("_score", ""), "")
        weight_txt = f" ×{weight}" if weight else ""
        lines.append(
            f"<code>  {label:<11}{bar(value, 8)} {value:>6.2f}{weight_txt}</code>"
        )

    lines += [
        "",
        "<b>DATASET</b>",
        f"<code>  N propre     {snap.n_clean}</code>",
        f"<code>  N regrets    {snap.n_regrets_clean}</code>",
        f"<code>  Borne        {esc(snap.clean_data_since)[:25]}</code>",
    ]

    prov = snap.provenance or {}
    if prov:
        lines.append(
            f"<code>  CLOSE lus    {prov.get('close_events_total', '?')}</code>"
        )
        excluded = prov.get("excluded_by_reason") or {}
        if excluded:
            lines.append("<code>  Exclus :</code>")
            lines += _top_rows(excluded, limit=4)

    validity_icon = "✅" if snap.validity == "OK" else "⚠️"
    lines += ["", f"<b>VALIDITÉ</b> {validity_icon} {esc(snap.validity)}"]
    if snap.regret_source:
        lines.append(f"<code>  source {esc(snap.regret_source)[:30]}</code>")
    if snap.regret_fresh is False:
        lines.append(f"<code>  dernier écrit {esc(snap.regret_last_write)}</code>")
    for warning in snap.warnings[:3]:
        lines.append(f"<code>  ⚠️ {esc(warning)[:70]}</code>")

    return clip("\n".join(lines))


# ── Regret ────────────────────────────────────────────────────────────────────


def format_regret(snap) -> str:
    """Read-only breakdown of one regret category."""
    lines = [
        f"🔍 <b>REGRET</b> — {esc(snap.regret_type)}",
        f"<b>N = {snap.n_total}</b>",
        "",
    ]

    if snap.n_total == 0:
        lines.append("<code>  (aucun enregistrement)</code>")
        return clip("\n".join(lines))

    lines += ["<b>PAR COUCHE BLOQUEUSE</b>"] + _top_rows(snap.by_layer, 5, snap.n_total)
    lines += ["", "<b>PAR RÉGIME</b>"] + _top_rows(snap.by_regime, 4, snap.n_total)
    lines += ["", "<b>PAR BIN DE SCORE</b>"] + _top_rows(
        snap.by_score_bin, 5, snap.n_total
    )

    if snap.by_week:
        recent = list(snap.by_week.items())[-4:]
        lines += ["", "<b>PAR SEMAINE</b>"]
        lines += [f"<code>  {esc(w):<10}{c:>5}</code>" for w, c in recent]

    lines += [
        "",
        f"<code>1er  {_ts(snap.first_evaluated_at)}</code>",
        f"<code>dern {_ts(snap.last_evaluated_at)}</code>",
        "",
        "<i>Observation seule — aucune recalibration (ADR-0007).</i>",
    ]
    return clip("\n".join(lines))


# ── Scientific / certification ────────────────────────────────────────────────


def format_science(snap) -> str:
    """Observer certification + DIP knowledge layer."""
    lines = [
        "🔬 <b>ÉTAT SCIENTIFIQUE</b>",
        "",
        f"<b>Certification</b> — niveau {snap.certification_level}",
        f"<code>{esc(snap.certification_name)}</code>",
        f"<code>III  {bar(snap.iii, 8)} {snap.iii:>6.1f}</code>",
        f"<code>OCS  {bar(snap.ocs, 8)} {snap.ocs:>6.1f}</code>",
        f"<i>{_ts(snap.last_cert_at)}</i>",
        "",
        "<b>DIP</b>",
        f"<code>  Décisions prod  {snap.n_decisions_production:>6}</code>",
        f"<code>  Connaissances   {snap.n_knowledge_entries:>6}</code>",
        f"<code>  Contrefactuels  {snap.n_counterfactuals:>6}</code>",
        f"<code>  Alertes actives {snap.n_alerts_active:>6}</code>"
        + (" 🚨" if snap.n_alerts_active else " ✅"),
        "",
        f"<b>Décision :</b> {esc(snap.cert_decision)[:180]}",
    ]

    failed = [c for c in snap.checks if not c.get("passed", True)]
    if failed:
        lines += ["", f"<b>CHECKS EN ÉCHEC ({len(failed)})</b>"]
        for check in failed[:5]:
            name = check.get("name") or check.get("check") or "?"
            lines.append(f"<code>  🚨 {esc(name)[:40]}</code>")

    return clip("\n".join(lines))


# ── Timeline ──────────────────────────────────────────────────────────────────

_STATE_ICONS = {
    "REJECTED": "🔴",
    "EXECUTED": "🟢",
    "CLOSED": "⚪",
    "EXECUTION_PENDING": "🟡",
    "SIGNAL_GENERATED": "🔵",
}


def format_timeline(snap, limit: int = 12) -> str:
    """Recent decision packets, newest first."""
    lines = [
        "🕒 <b>TIMELINE</b> — décisions récentes",
        f"<code>total {snap.total_packets}  trade {snap.n_trade}  "
        f"exec {snap.n_executed}  rejet {snap.n_rejected}</code>",
        "",
    ]

    if not snap.events:
        lines.append("<code>  (aucun paquet de décision)</code>")
        return clip("\n".join(lines))

    for event in snap.events[:limit]:
        state_icon = _STATE_ICONS.get(event.lifecycle_state, "▫️")
        lines.append(
            f"{state_icon} <code>{event.ts.strftime('%m-%d %H:%M')} "
            f"{esc(event.symbol)[:12]:<12}</code>"
        )
        detail = f"{event.lifecycle_state} · {event.regime} · {event.conviction}"
        lines.append(f"<code>   {esc(detail)[:44]}</code>")
        if event.reason:
            lines.append(f"<code>   {esc(event.reason)[:44]}</code>")

    return clip("\n".join(lines))


# ── Rejections ────────────────────────────────────────────────────────────────


def format_rejections(snap) -> str:
    """Aggregated rejection analysis — which layer blocks, in which regime."""
    lines = [
        "⛔ <b>REJETS</b>",
        f"<code>entrées {snap.n_entries}  uniques {snap.n_unique}</code>",
        f"<code>jours   {len(snap.days_covered)}</code>",
        "",
    ]

    if not snap.n_entries:
        lines.append("<code>  (aucun rejet sur la fenêtre)</code>")
        return clip("\n".join(lines))

    lines += ["<b>PAR COUCHE</b>"] + _top_rows(snap.by_layer, 6, snap.n_entries)
    lines += ["", "<b>PAR RÉGIME</b>"] + _top_rows(snap.by_regime, 4, snap.n_entries)
    if snap.by_personality:
        lines += ["", "<b>PAR PERSONNALITÉ</b>"] + _top_rows(
            snap.by_personality, 4, snap.n_entries
        )

    if snap.recent:
        lines += ["", "<b>RÉCENTS</b>"]
        for event in snap.recent[:6]:
            label = event.first_blocker_label or event.first_blocker or "—"
            lines.append(
                f"<code>  {esc(event.symbol)[:10]:<10}{esc(label)[:24]}</code>"
            )

    return clip("\n".join(lines))


# ── Datasets / certification history ──────────────────────────────────────────


def format_datasets(snap, limit: int = 6) -> str:
    """Observer certification history."""
    lines = [
        "📚 <b>CERTIFICATIONS OBSERVER</b>",
        f"<code>niveau {snap.latest_level}  III {snap.latest_iii:.1f}  "
        f"OCS {snap.latest_ocs:.1f}</code>",
        "",
    ]

    if not snap.certifications:
        lines.append("<code>  (aucune certification)</code>")
        return clip("\n".join(lines))

    for cert in snap.certifications[:limit]:
        lines.append(
            f"<code>{cert.generated_at.strftime('%m-%d %H:%M')} "
            f"L{cert.level} III {cert.iii:>5.1f} OCS {cert.ocs:>5.1f}</code>"
        )
        lines.append(
            f"<code>  live ✅{cert.n_live_passed} 🚨{cert.n_live_failed}  "
            f"N {cert.n_decisions_production}</code>"
        )

    return clip("\n".join(lines))


# ── Logs ──────────────────────────────────────────────────────────────────────

_LEVEL_ICONS = {"ERROR": "🚨", "WARNING": "⚠️", "INFO": "·", "OTHER": " "}


def format_logs(snap) -> str:
    """Bounded, already-redacted log tail."""
    header = [
        "📜 <b>LOGS</b>",
        f"<code>{esc(snap.source_path.split('/')[-1])}  "
        f"filtre={esc(snap.level_filter)}</code>",
    ]

    if snap.error:
        header += ["", f"⚠️ <code>{esc(snap.error)[:150]}</code>"]
        return clip("\n".join(header))

    header.append(
        f"<code>{snap.n_returned} lignes / {snap.n_scanned} lues</code>"
        + (f"  🔒 {snap.n_redacted} masquées" if snap.n_redacted else "")
    )
    header.append("")

    if not snap.lines:
        header.append("<code>  (aucune ligne pour ce filtre)</code>")
        return clip("\n".join(header))

    body = [
        f"{_LEVEL_ICONS.get(line.level, ' ')} <code>{esc(line.raw)[:150]}</code>"
        for line in snap.lines
    ]
    return clip("\n".join(header + body))
