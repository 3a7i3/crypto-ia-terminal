"""
capital_deployment/command_center_bot.py — Telegram Command Center

Interface Telegram complète : lecture ET écriture de tous les paramètres.
Remplace tout dashboard. Bot unique pour tout contrôler.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMANDES DISPONIBLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 STATUS
  /status          Résumé rapide (phase, KPIs, capital)
  /kpis            KPIs détaillés (WR, Sharpe, DD, trades)
  /phase           Info phase F-xx + temps restant
  /regime          Régime marché par symbole
  /signals         Scores signaux actuels
  /risk            État risque (drawdown, EO, pertes consec.)
  /health          Santé de tous les modules

💰 PORTEFEUILLE
  /balance         Soldes de tous les comptes
  /positions       Positions ouvertes + PnL non réalisé
  /pnl             PnL réalisé détaillé
  /trades [n]      Derniers N trades (défaut 10)

⚙️ CONFIGURATION
  /config          Tous les paramètres par section
  /config <section> Section spécifique (trading, risk, tp, eo...)
  /get <PARAM>     Valeur d'un paramètre précis
  /set <PARAM> <val> Modifier un paramètre (nécessite /confirm)

🔧 CONTRÔLE
  /pause           Passer en mode observation seule
  /resume          Reprendre le trading actif
  /setphase <F-xx> Changer de phase (F-01 à F-05)
  /maxorder <usd>  Changer la taille max d'ordre
  /confirm         Confirmer la dernière action en attente
  /cancel          Annuler

📋 SYSTÈME
  /logs [n]        Derniers N logs (défaut 20)
  /help            Cette liste

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sécurité :
  - Répondre uniquement au chat_id configuré
  - Toute modification nécessite /confirm dans les 60s
  - Les modifications sont écrites dans .env ET appliquées live si possible

Env vars :
  P10_PORTFOLIO_BOT_TOKEN   Token du bot
  P10_PORTFOLIO_CHAT_ID     Chat autorisé
  P10_PORTFOLIO_REPORT_H    Rapport auto (heures, défaut 1)
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("capital_deployment.command_center_bot")

_POLL_TIMEOUT = 30
_RETRY_DELAY = 5.0
_CONFIRM_TTL = 60.0  # secondes pour /confirm
_MAX_MSG = 4000
_ENV_PATH = Path(os.getenv("ENV_PATH", ".env"))
_LOG_PATH = Path(os.getenv("ADVISOR_LOG", "logs/advisor_loop.log"))

# ── Sections de configuration ─────────────────────────────────────────────────

_CONFIG_SECTIONS: dict[str, list[str]] = {
    "trading": [
        "EXEC_MAX_ORDER_USD",
        "EXEC_FUTURES_MIN_ORDER_USD",
        "EXEC_FUTURES_MAX_ORDER_USD",
        "V9_MAX_POSITION_WEIGHT",
        "V9_SYMBOLS",
        "SIGNAL_MIN_SCORE",
        "GATE_REQUIRE_CONFIRMED",
        "LSE_MTF_MIN_AGREE",
    ],
    "risk": [
        "EXEC_MAX_DD",
        "EXEC_MAX_LOSS",
        "EXEC_MAX_CONSEC_LOSSES",
        "V9_MAX_DRAWDOWN",
        "V9_MIN_SHARPE",
        "V9_KELLY_SAFETY",
        "REGIME_ABSOLUTE_FLOOR",
        "REGIME_SIDEWAYS_MIN_SCORE",
    ],
    "tp": [
        "PM_TP_PCT",
        "PM_SL_PCT",
        "PM_TRAILING_PCT",
        "META_MOMENTUM_TP",
        "META_MOMENTUM_SL",
        "META_SHORT_TP",
        "META_SHORT_SL",
        "META_RANGE_TP",
        "META_RANGE_SL",
        "META_SCALP_TP",
        "META_SCALP_SL",
    ],
    "eo": [
        "EO_DD_REDUCE",
        "EO_DD_CAREFUL",
        "EO_DD_MINIMAL",
        "EO_DD_VETO",
        "EO_DAILY_REDUCE",
        "EO_DAILY_CAREFUL",
        "EO_DAILY_MINIMAL",
        "EO_DAILY_VETO",
        "EO_STREAK_REDUCE",
        "EO_STREAK_CAREFUL",
        "EO_MAX_TRADES_HOUR",
    ],
    "phase": [
        "P10_PHASE",
        "P10_PORTFOLIO_REPORT_H",
    ],
    "system": [
        "V9_ADVISOR_ONLY",
        "P6_SAFE_MODE",
        "V9_LOG_LEVEL",
        "ADVISOR_NOTIFY_EVERY",
        "MTF_SCAN_MAX_WORKERS",
    ],
    "kelly": [
        "CAE_KELLY_SAFETY",
        "CAE_KELLY_MAX",
        "CAE_EV_MIN",
        "CAE_VOL_REFERENCE",
        "CAE_LEVERAGE_MAX",
        "CAE_MIN_TRADES_KELLY",
    ],
    "conviction": [
        "CONV_THRESH_EXCEPTIONAL",
        "CONV_THRESH_HIGH",
        "CONV_THRESH_MEDIUM",
        "CONV_SIZE_LOW",
        "CONV_SIZE_MEDIUM",
        "CONV_SIZE_HIGH",
        "CONV_SIZE_EXCEPTIONAL",
    ],
}

# Params que l'on peut changer LIVE (sans redémarrage)
_LIVE_PARAMS = {
    "EXEC_MAX_ORDER_USD",
    "EXEC_FUTURES_MAX_ORDER_USD",
    "EXEC_MAX_DD",
    "EXEC_MAX_LOSS",
    "EXEC_MAX_CONSEC_LOSSES",
    "PM_TP_PCT",
    "PM_SL_PCT",
    "PM_TRAILING_PCT",
    "SIGNAL_MIN_SCORE",
    "GATE_REQUIRE_CONFIRMED",
    "P10_PHASE",
    "V9_ADVISOR_ONLY",
}


# ── Data provider ─────────────────────────────────────────────────────────────


@dataclass
class CommandDataProvider:
    """
    Callbacks injectés depuis advisor_loop.py.
    Tous optionnels — le bot fonctionne même partiellement câblé.
    """

    # Lecture
    get_kpis: Optional[Callable[[], Any]] = None
    get_balances: Optional[Callable[[], Any]] = None
    get_positions: Optional[Callable[[], Any]] = None
    get_phase: Optional[Callable[[], Any]] = None
    get_throttle: Optional[Callable[[], Any]] = None
    get_regime: Optional[Callable[[], Any]] = None  # -> dict {symbol: regime}
    get_signals: Optional[Callable[[], Any]] = None  # -> list[dict]
    get_risk: Optional[Callable[[], Any]] = None  # -> dict
    get_health: Optional[Callable[[], Any]] = None  # -> dict {module: bool}
    get_trades: Optional[Callable[[], Any]] = None  # -> list[dict]
    get_eo: Optional[Callable[[], Any]] = (
        None  # -> dict (ExecutiveOverride.metrics_snapshot)
    )
    get_gate: Optional[Callable[[], Any]] = (
        None  # -> dict (GlobalRiskGate last snapshot)
    )
    get_blackbox: Optional[Callable[[int], Any]] = None  # (n) -> list[BlackBoxEntry]
    # Actions
    reset_kpis: Optional[Callable[[], bool]] = None  # réinitialise les KPIs
    # Écriture live
    set_param: Optional[Callable[[str, str], bool]] = None  # (name, value) -> ok


# ── Formatteurs ───────────────────────────────────────────────────────────────

_SEP = "─" * 28


def _v(val: Any) -> str:
    if val is None:
        return "N/A"
    if isinstance(val, float):
        return f"{val:.4g}"
    return str(val)


def _chk(val: float, thr: float, low_good: bool = False) -> str:
    ok = (val <= thr) if low_good else (val >= thr)
    return "OK" if ok else " —"


def _bar(val: float, target: float, width: int = 8, low_good: bool = False) -> str:
    if not target:
        return "░" * width
    ratio = val / target
    filled = (
        max(0, int((1.0 - ratio) * width))
        if low_good
        else min(width, max(0, int(ratio * width)))
    )
    return "▓" * filled + "░" * (width - filled)


def _kpi_line(label: str, val_str: str, bar: str, target_str: str, status: str) -> str:
    return f"{label:<9} {bar}  {val_str:<7} cible {target_str:<6} {status}"


def _fmt_status(p: CommandDataProvider) -> str:
    from datetime import datetime, timezone

    phase = p.get_phase() if p.get_phase else "?"
    thr = p.get_throttle() if p.get_throttle else None
    kpis = p.get_kpis() if p.get_kpis else None
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lines = [f"*PORTEFEUILLE — {now}*", f"Phase *{phase}*"]
    if thr:
        a = thr.allocated_capital
        el = thr.allocation().days_elapsed()
        mn = thr.allocation().min_duration_days
        lines.append(f"Capital *{a:.2f} USD* — Jour {el:.1f} / {mn}")
    if kpis:
        from capital_deployment.phase_kpi_tracker import PHASE_CRITERIA

        c = PHASE_CRITERIA.get(phase, {})
        wr_t = c.get("min_win_rate", 0.45)
        sh_t = c.get("min_sharpe", 1.0)
        dd_t = c.get("max_drawdown", 0.02)
        lines += [
            "",
            _SEP,
            _kpi_line(
                "Win Rate",
                f"{kpis.win_rate:.0%}",
                _bar(kpis.win_rate, wr_t),
                f">{wr_t:.0%}",
                _chk(kpis.win_rate, wr_t),
            ),
            _kpi_line(
                "Sharpe",
                f"{kpis.sharpe:.2f}",
                _bar(kpis.sharpe, sh_t),
                f">{sh_t:.1f}",
                _chk(kpis.sharpe, sh_t),
            ),
            _kpi_line(
                "Max DD",
                f"{kpis.max_drawdown:.1%}",
                _bar(kpis.max_drawdown, dd_t, low_good=True),
                f"<{dd_t:.0%}",
                _chk(kpis.max_drawdown, dd_t, low_good=True),
            ),
            _SEP,
            f"Trades: {kpis.total_trades}  |  DD courant: {kpis.current_drawdown:.1%}",
        ]
        if kpis.unsigned_decisions:
            lines.append(f"*WARN* {kpis.unsigned_decisions} decision(s) non signee(s)")
    return "\n".join(lines)


def _fmt_kpis(p: CommandDataProvider) -> str:
    kpis = p.get_kpis() if p.get_kpis else None
    if not kpis:
        return "_KPIs non disponibles_"
    phase = p.get_phase() if p.get_phase else "?"
    from capital_deployment.phase_kpi_tracker import PHASE_CRITERIA

    c = PHASE_CRITERIA.get(phase, {})
    wr_t = c.get("min_win_rate", 0.45)
    sh_t = c.get("min_sharpe", 1.0)
    dd_t = c.get("max_drawdown", 0.02)
    lines = [f"*KPIs — Phase {phase}*", _SEP]
    lines.append(
        _kpi_line(
            "Win Rate",
            f"{kpis.win_rate:.1%}",
            _bar(kpis.win_rate, wr_t),
            f">{wr_t:.0%}",
            _chk(kpis.win_rate, wr_t),
        )
    )
    lines.append(
        _kpi_line(
            "Sharpe",
            f"{kpis.sharpe:.3f}",
            _bar(kpis.sharpe, sh_t),
            f">{sh_t:.1f}",
            _chk(kpis.sharpe, sh_t),
        )
    )
    lines.append(
        _kpi_line(
            "Max DD",
            f"{kpis.max_drawdown:.2%}",
            _bar(kpis.max_drawdown, dd_t, low_good=True),
            f"<{dd_t:.0%}",
            _chk(kpis.max_drawdown, dd_t, low_good=True),
        )
    )
    lines += [
        _SEP,
        f"DD courant:    {kpis.current_drawdown:.2%}",
        f"Total trades:  {kpis.total_trades}",
        f"Non signes:    {kpis.unsigned_decisions}",
        f"Jours ecoules: {kpis.days_elapsed:.1f} j",
    ]
    v = kpis.violations(phase)
    if v:
        lines.append(f"\n*VIOLATIONS ({len(v)})*")
        for vi in v:
            lines.append(f"  !! {vi}")
    else:
        lines.append("\nTous les criteres: *OK*")
    return "\n".join(lines)


def _fmt_balance(p: CommandDataProvider) -> str:
    bal = p.get_balances() if p.get_balances else None
    if not bal:
        return "_Soldes non disponibles_"
    lines = ["*SOLDES*", _SEP]
    total = 0.0
    for acc, amt in bal.items():
        try:
            v = float(amt or 0)
            total += v
            lines.append(f"{acc.capitalize():<14}  {v:>9.2f} USD")
        except Exception:
            pass
    lines += [_SEP, f"{'Total':<14}  *{total:>9.2f} USD*"]
    return "\n".join(lines)


def _fmt_positions(p: CommandDataProvider) -> str:
    pos = p.get_positions() if p.get_positions else None
    if pos is None:
        return "_Positions non disponibles_"
    if not pos:
        return "*POSITIONS OUVERTES*\n\nAucune position ouverte"
    lines = [f"*POSITIONS OUVERTES  {len(pos)}*"]
    for position in pos:
        try:
            sym = position.get("symbol", "?")
            side = position.get("side", "?").upper()
            entry = float(position.get("entry", position.get("entry_price", 0)))
            cur = float(position.get("current", position.get("current_price", 0)))
            pnl = float(position.get("pnl_usd", position.get("unrealized_pnl", 0)))
            pct = float(position.get("pnl_pct", 0))
            tp = float(position.get("tp", position.get("tp_price", 0)))
            sl = float(position.get("sl", position.get("sl_price", 0)))
            sz = float(position.get("size_usd", position.get("capital", 0)))
            age = float(position.get("age_min", 0))
            vol = float(position.get("volatility", 0))
            # Distance % depuis l'entrée
            if entry > 0 and cur > 0:
                dist_pct = (cur - entry) / entry * 100
            else:
                dist_pct = pct
            sg = "+" if pnl >= 0 else ""
            dsg = "+" if dist_pct >= 0 else ""
            # Durée formatée
            if age >= 60:
                age_s = f"{int(age // 60)}h{int(age % 60):02d}m"
            else:
                age_s = f"{int(age)}m"
            tp_s = f"${tp:.4g}" if tp else "N/A"
            sl_s = f"${sl:.4g}" if sl else "N/A"
            vol_s = f"{vol:.3f}" if vol else "N/A"
            lines += [
                _SEP,
                f"*{sym}*  {side}  Vol: ${sz:.2f}  ({age_s})",
                f"Entry ${entry:.4g}  →  ${cur:.4g}  {dsg}{dist_pct:.2f}%",
                f"TP: {tp_s}  SL: {sl_s}  Volatilite: {vol_s}",
                f"PnL: *{sg}${pnl:.2f}* ({sg}{pct:.1f}%)",
            ]
        except Exception as exc:
            lines.append(f"  ERR {exc}")
    lines.append(_SEP)
    return "\n".join(lines)


def _fmt_pnl(p: CommandDataProvider) -> str:
    kpis = p.get_kpis() if p.get_kpis else None
    bal = p.get_balances() if p.get_balances else None
    lines = ["*PnL DETAILS*", _SEP]
    if kpis:
        lines += [
            f"Trades:        {kpis.total_trades}",
            f"Win rate:      {kpis.win_rate:.1%}",
            f"Max drawdown:  {kpis.max_drawdown:.2%}",
            f"DD courant:    {kpis.current_drawdown:.2%}",
        ]
    if bal:
        total = sum(float(v or 0) for v in bal.values())
        lines.append(f"Capital total: *{total:.2f} USD*")
    if not kpis and not bal:
        lines.append("_Donnees non disponibles_")
    return "\n".join(lines)


def _fmt_trades(p: CommandDataProvider, n: int = 10) -> str:
    from datetime import datetime

    trades = p.get_trades() if p.get_trades else None
    if not trades:
        return "_Historique trades non disponible_"
    recent = trades[-n:]
    lines = [f"*DERNIERS {len(recent)} TRADES*", _SEP]
    for t in reversed(recent):
        try:
            sym = t.get("symbol", "?")
            side = t.get("side", "?").upper()
            pnl = float(t.get("pnl", 0))
            sg = "+" if pnl >= 0 else ""
            ts_ = t.get("ts", 0)
            dt = (
                datetime.fromtimestamp(ts_).strftime("%m-%d %H:%M") if ts_ else "     ?"
            )
            lines.append(f"`{dt}`  {sym:<12} {side:<5}  *{sg}${pnl:.2f}*")
        except Exception:
            pass
    lines.append(_SEP)
    return "\n".join(lines)


def _fmt_phase(p: CommandDataProvider) -> str:
    from capital_deployment.capital_throttle import PHASE_CONFIGS, PHASE_ORDER
    from capital_deployment.phase_kpi_tracker import PHASE_CRITERIA

    phase = p.get_phase() if p.get_phase else "F-01"
    thr = p.get_throttle() if p.get_throttle else None
    cfg = PHASE_CONFIGS.get(phase, {})
    crit = PHASE_CRITERIA.get(phase, {})
    cap_lbl = f"{cfg.get('capital_pct', 0)*100:.0f}%"
    if cfg.get("max_capital_eur"):
        cap_lbl += f" / max {cfg['max_capital_eur']:.0f} EUR"
    lines = [
        f"*PHASE {phase}*",
        _SEP,
        f"Capital:   {cap_lbl}",
        f"Duree min: {crit.get('min_duration_days', 0)} jours",
        "",
        "Criteres de passage:",
        f"  Win Rate > {crit.get('min_win_rate', 0):.0%}",
        f"  Sharpe   > {crit.get('min_sharpe', 0)}",
        f"  Max DD   < {crit.get('max_drawdown', 0):.0%}",
    ]
    if thr:
        el = thr.allocation().days_elapsed()
        mn = crit.get("min_duration_days", 0)
        rem = max(0.0, mn - el)
        prog = _bar(el, float(mn)) if mn else "░" * 8
        lines += [
            _SEP,
            f"Progression: {prog}  {el:.1f} / {mn} j",
            f"Restant:  {rem:.1f} j" if rem > 0 else "Duree:    *VALIDEE*",
        ]
    idx = PHASE_ORDER.index(phase) if phase in PHASE_ORDER else -1
    if 0 <= idx < len(PHASE_ORDER) - 1:
        np_ = PHASE_ORDER[idx + 1]
        nc = PHASE_CRITERIA.get(np_, {})
        lines.append(
            f"\nSuivante: *{np_}*  Sharpe>{nc.get('min_sharpe','?')}  DD<{nc.get('max_drawdown',0)*100:.0f}%"
        )
    return "\n".join(lines)


def _fmt_regime(p: CommandDataProvider) -> str:
    reg = p.get_regime() if p.get_regime else None
    if not reg:
        return "_Regime non disponible_"
    lines = ["*REGIMES MARCHE*", _SEP]
    for sym, r in reg.items() if isinstance(reg, dict) else []:
        if isinstance(r, dict):
            name = r.get("regime", r.get("name", str(r)))
            score = r.get("score", r.get("confidence", ""))
            sc_s = f"  {score:.0f}%" if isinstance(score, (int, float)) else ""
            lines.append(f"{sym:<15}  {name}{sc_s}")
        else:
            lines.append(f"{sym}: {r}")
    return "\n".join(lines)


def _fmt_signals(p: CommandDataProvider) -> str:
    sigs = p.get_signals() if p.get_signals else None
    if not sigs:
        return "_Signaux non disponibles_"
    lines = ["*SIGNAUX ACTUELS*", _SEP]
    items = sigs.items() if isinstance(sigs, dict) else list(enumerate(sigs))
    for sym, s in items:
        if isinstance(s, dict):
            score = float(s.get("score", s.get("confidence", 0)))
            action = s.get("action", s.get("signal", "?"))
            act = "  actionable" if s.get("actionable") else ""
            lines.append(
                f"{sym:<14}  {_bar(score, 100.0)}  {score:3.0f}  {action}{act}"
            )
        else:
            lines.append(f"{sym}: {s}")
    return "\n".join(lines)


def _fmt_risk(p: CommandDataProvider) -> str:
    risk = p.get_risk() if p.get_risk else None
    if not risk:
        return "_Etat risque non disponible_"
    lines = ["*ETAT RISQUE*", _SEP]
    for k, v in risk.items():
        lines.append(f"{k:<26} {_v(v)}")
    return "\n".join(lines)


def _fmt_health(p: CommandDataProvider) -> str:
    h = p.get_health() if p.get_health else None
    if not h:
        return "_Sante modules non disponible_"
    ok_mods = [m for m, alive in h.items() if alive]
    bad_mods = [m for m, alive in h.items() if not alive]
    lines = [f"*SANTE MODULES*  {len(ok_mods)}/{len(h)} OK", _SEP]
    if bad_mods:
        lines.append("*!! EN DEFAUT:*")
        for m in bad_mods:
            lines.append(f"  !! {m}")
        lines.append("")
    for m in ok_mods:
        lines.append(f"  OK  {m}")
    return "\n".join(lines)


def _fmt_eo(p: CommandDataProvider) -> str:
    snap = p.get_eo() if p.get_eo else None
    if not snap:
        return "_ExecutiveOverride non disponible_"
    lvl = snap.get("level", "?")
    sf = snap.get("size_factor", 1.0)
    dd = snap.get("drawdown_pct", 0.0)
    dl = snap.get("daily_loss_pct", 0.0)
    st = snap.get("loss_streak", 0)
    op = snap.get("open_pnl_pct", 0.0)
    tt = snap.get("trades_today", 0)
    cap = snap.get("capital_current", 0.0)
    _ICONS = {
        "CLEAR": "OK",
        "REDUCE": "REDUCE",
        "CAREFUL": "CAUTION",
        "MINIMAL": "MINIMAL",
        "VETO": "!! VETO",
    }
    icon = _ICONS.get(lvl, lvl)
    lines = [
        f"*EO — {icon}*  taille x{sf:.2f}",
        _SEP,
        f"Drawdown:       {dd:.2f}%  (VETO>{int(float(os.getenv('EO_DD_VETO','0.10'))*100)}%)",
        f"Perte jour:     {dl:.2f}%  (VETO>{int(float(os.getenv('EO_DAILY_VETO','0.08'))*100)}%)",
        f"Streak pertes:  {st}  (VETO>{os.getenv('EO_STREAK_VETO','10')})",
        f"PnL latent:     {op:.2f}%",
        f"Trades auj:     {tt}  |  Capital: {cap:.2f} USD",
    ]
    thresholds = [
        (
            "REDUCE",
            f"DD>{int(float(os.getenv('EO_DD_REDUCE','0.03'))*100)}%"
            f" ou streak>={os.getenv('EO_STREAK_REDUCE','3')}",
        ),
        (
            "CAREFUL",
            f"DD>{int(float(os.getenv('EO_DD_CAREFUL','0.05'))*100)}%"
            f" ou streak>={os.getenv('EO_STREAK_CAREFUL','5')}",
        ),
        (
            "MINIMAL",
            f"DD>{int(float(os.getenv('EO_DD_MINIMAL','0.07'))*100)}%"
            f" ou perte jour>{int(float(os.getenv('EO_DAILY_MINIMAL','0.05'))*100)}%",
        ),
        (
            "VETO",
            f"DD>{int(float(os.getenv('EO_DD_VETO','0.10'))*100)}%"
            f" ou perte jour>{int(float(os.getenv('EO_DAILY_VETO','0.08'))*100)}%",
        ),
    ]
    lines += ["", "*Seuils:*"]
    for name, cond in thresholds:
        marker = "→" if name == lvl else " "
        lines.append(f"{marker} {name:<8}  {cond}")
    return "\n".join(lines)


def _fmt_gate(p: CommandDataProvider) -> str:
    snap = p.get_gate() if p.get_gate else None
    if not snap:
        return "_GlobalRiskGate non disponible_"
    if hasattr(snap, "__dict__"):
        snap = snap.__dict__
    lvl = snap.get("level", "?")
    if hasattr(lvl, "value"):
        lvl = lvl.value
    sf = snap.get("size_factor", 1.0)
    dd = snap.get("drawdown", 0.0)
    corr = snap.get("avg_correlation", 0.0)
    vol = snap.get("vol_ratio", 1.0)
    exp = snap.get("net_exposure", 0.0)
    msg = snap.get("message", "")
    conds = snap.get("triggered_conditions", [])
    icon = {"SAFE": "SAFE", "WARNING": "WARN", "CRITICAL": "!! CRITICAL"}.get(
        str(lvl), str(lvl)
    )
    lines = [
        f"*GATE — {icon}*  x{sf:.2f}",
        _SEP,
        f"Drawdown:       {dd:.1%}",
        f"Correlation:    {corr:.2f}",
        f"Vol ratio:      {vol:.1f}x",
        f"Exposition:     {exp:.1%}",
    ]
    if msg:
        lines.append(f"Message: {msg}")
    if conds:
        lines += ["", "*Conditions déclenchées:*"]
        for c in conds:
            lines.append(f"  !! {c}")
    else:
        lines.append("\nAucune condition déclenchée")
    return "\n".join(lines)


def _fmt_blackbox(p: CommandDataProvider, n: int = 10) -> str:
    from datetime import datetime

    entries = p.get_blackbox(n) if p.get_blackbox else None
    if not entries:
        return "_BlackBox vide ou non disponible_"
    lines = [f"*BLACKBOX — {len(entries)} entrées*", _SEP]
    for e in entries:
        try:
            dt = (
                datetime.fromtimestamp(e.ts).strftime("%m-%d %H:%M")
                if hasattr(e, "ts")
                else "?"
            )
            sym = getattr(e, "symbol", "?")
            dt_ = getattr(e, "decision_type", "?")
            sig = getattr(e, "signal", "?")
            sc = getattr(e, "score", 0)
            rsn = getattr(e, "reason", "")[:50]
            ref = getattr(e, "refused_by", [])
            ref_s = f"  refus:{','.join(ref[:2])}" if ref else ""
            lines.append(f"`{dt}`  {sym:<12} {dt_:<16}  {sig} {sc}{ref_s}")
            if rsn:
                lines.append(f"         {rsn}")
        except Exception:
            lines.append(f"  {e}")
    lines.append(_SEP)
    return "\n".join(lines)


def _fmt_perf(p: CommandDataProvider) -> str:
    trades = p.get_trades() if p.get_trades else None
    if not trades:
        return "_Historique trades requis pour /perf_"
    pnls = []
    for t in trades:
        try:
            pnls.append(float(t.get("pnl", 0)))
        except Exception:
            pass
    if not pnls:
        return "_Aucun PnL dans l'historique_"
    cumul = []
    running = 0.0
    for p_ in pnls:
        running += p_
        cumul.append(running)
    HEIGHT = 8
    WIDTH = min(len(cumul), 40)
    step = max(1, len(cumul) // WIDTH)
    sampled = [cumul[i] for i in range(0, len(cumul), step)][-WIDTH:]
    mn, mx = min(sampled), max(sampled)
    span = mx - mn if mx != mn else 1.0
    rows = []
    for row in range(HEIGHT - 1, -1, -1):
        threshold = mn + (row / (HEIGHT - 1)) * span
        line = ""
        for v in sampled:
            line += "▓" if v >= threshold else " "
        label = f"{threshold:+.2f}" if row in (HEIGHT - 1, HEIGHT // 2, 0) else "      "
        rows.append(f"`{label}|{line}`")
    total = cumul[-1] if cumul else 0
    sg = "+" if total >= 0 else ""
    return (
        f"*PnL CUMULATIF*  {sg}${total:.2f} USD  ({len(pnls)} trades)\n\n"
        + "\n".join(rows)
    )


def _fmt_recap(p: CommandDataProvider, days: int = 7) -> str:
    import time
    from datetime import datetime

    trades = p.get_trades() if p.get_trades else None
    if not trades:
        return "_Historique trades requis pour /recap_"
    cutoff = time.time() - days * 86400
    recent = [t for t in trades if float(t.get("ts", 0)) >= cutoff]
    if not recent:
        return f"_Aucun trade sur les {days} derniers jours_"
    pnls = [float(t.get("pnl", 0)) for t in recent]
    total = sum(pnls)
    wins = sum(1 for x in pnls if x > 0)
    wr = wins / len(pnls) if pnls else 0
    best = max(pnls) if pnls else 0
    worst = min(pnls) if pnls else 0
    sg = "+" if total >= 0 else ""
    lines = [
        f"*RECAP {days}j*  ({len(recent)} trades)",
        _SEP,
        f"PnL total:   *{sg}${total:.2f}*",
        f"Win rate:    {wr:.0%}  ({wins}W / {len(pnls)-wins}L)",
        f"Meilleur:    +${best:.2f}",
        f"Pire:        ${worst:.2f}",
        _SEP,
    ]
    lines.append("*Derniers trades:*")
    for t in reversed(recent[-5:]):
        try:
            sym = t.get("symbol", "?")
            pnl = float(t.get("pnl", 0))
            ts_ = float(t.get("ts", 0))
            dt = datetime.fromtimestamp(ts_).strftime("%m-%d %H:%M") if ts_ else "?"
            sg2 = "+" if pnl >= 0 else ""
            lines.append(f"`{dt}`  {sym:<12} {sg2}${pnl:.2f}")
        except Exception:
            pass
    return "\n".join(lines)


def _fmt_history(p: CommandDataProvider, n: int = 20) -> str:
    """Historique complet entrées/sorties avec PnL réalisé."""
    from datetime import datetime

    trades = p.get_trades() if p.get_trades else None
    if not trades:
        return "_Historique trades non disponible_"
    recent = trades[-n:]
    total_pnl = sum(float(t.get("pnl", 0)) for t in recent)
    wins = sum(1 for t in recent if float(t.get("pnl", 0)) > 0)
    sg = "+" if total_pnl >= 0 else ""
    lines = [f"*HISTORIQUE {len(recent)} TRADES*  PnL: {sg}${total_pnl:.2f}", _SEP]
    for t in reversed(recent):
        try:
            sym = t.get("symbol", "?")
            side = t.get("side", "?").upper()
            pnl = float(t.get("pnl", 0))
            entry = float(t.get("entry_price", t.get("price", 0)))
            exit_ = float(t.get("exit_price", t.get("close_price", 0)))
            reason = t.get("reason", t.get("close_reason", ""))[:12]
            ts_ = float(t.get("ts", t.get("opened_at", 0)))
            ts_cl = float(t.get("closed_at", 0))
            dt = datetime.fromtimestamp(ts_).strftime("%m-%d %H:%M") if ts_ else "?"
            dur_m = (ts_cl - ts_) / 60 if ts_ and ts_cl else 0
            dur_s = (
                (
                    f"{int(dur_m//60)}h{int(dur_m%60):02d}m"
                    if dur_m >= 60
                    else f"{int(dur_m)}m"
                )
                if dur_m > 0
                else "?"
            )
            sg2 = "+" if pnl >= 0 else ""
            icon = "W" if pnl > 0 else "L"
            entry_s = f"${entry:.4g}" if entry else ""
            exit_s = f"${exit_:.4g}" if exit_ else ""
            arrow = f"{entry_s}→{exit_s}" if entry_s and exit_s else ""
            lines.append(f"`{dt}`  {icon}  {sym:<12} {side:<5}  *{sg2}${pnl:.2f}*")
            if arrow or reason or dur_s != "?":
                lines.append(f"         {arrow}  {reason}  {dur_s}")
        except Exception:
            pass
    lines.append(_SEP)
    return "\n".join(lines)


def _fmt_charts_button() -> str:
    """Message avec bouton d'ouverture des charts (inline keyboard)."""
    url = os.getenv("CHART_SERVER_URL", "")
    if not url:
        return (
            "_CHART\\_SERVER\\_URL non configure dans .env_\n"
            "Exemple: `CHART_SERVER_URL=https://34.171.188.99:8080`"
        )
    return (
        f"*Charts temps reel*\n"
        f"{url}\n\n"
        f"PnL cumulatif, positions ouvertes, KPIs — rafraichi toutes les 5s."
    )


def _fmt_certif() -> str:
    import subprocess

    try:
        result = subprocess.run(
            ["python", "certification/p10_checker.py"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path(__file__).parent.parent),
        )
        raw = (result.stdout + result.stderr).strip()
        # Retirer les codes ANSI
        import re

        clean = re.sub(r"\x1b\[[0-9;]*m", "", raw)
        lines = [ln.rstrip() for ln in clean.splitlines() if ln.strip()]
        body = "\n".join(lines[:40])
        return f"*CERTIF P10*\n```\n{body}\n```"
    except Exception as exc:
        return f"_Erreur certif: {exc}_"


def _fmt_config(section: Optional[str] = None) -> str:
    from dotenv import dotenv_values

    env = dotenv_values(_ENV_PATH)
    lines = [f"*CONFIG{' — ' + section.upper() if section else ''}*", _SEP]
    if section:
        keys = _CONFIG_SECTIONS.get(section.lower(), [])
        if not keys:
            available = ", ".join(_CONFIG_SECTIONS.keys())
            return f"Section inconnue. Disponibles: {available}"
        for k in keys:
            v = env.get(k, "_non defini_")
            live = "live" if k in _LIVE_PARAMS else "restart"
            lines.append(f"`{k}` = {v} [{live}]")
    else:
        lines.append("Sections: " + ", ".join(_CONFIG_SECTIONS.keys()))
        lines.append("\nTape `/config <section>` pour les details.")
        lines.append("Tape `/get PARAM` pour un parametre precis.")
    return "\n".join(lines)


def _fmt_logs(n: int = 20) -> str:
    try:
        if not _LOG_PATH.exists():
            return f"_Fichier log non trouve: {_LOG_PATH}_"
        with open(_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines_all = f.readlines()
        # Filtrer les DEBUG exchange/ohlcv verbeux
        filtered = [
            ln.strip()
            for ln in lines_all
            if not ("[DEBUG" in ln and "ExchangeMonitor" in ln)
            and not ("[DEBUG" in ln and "ohlcv" in ln.lower())
            and ln.strip()
        ]
        recent = filtered[-n:]
        cleaned = [ln[:110] + "..." if len(ln) > 110 else ln for ln in recent]
        return f"*DERNIERS {len(cleaned)} LOGS*\n\n```\n" + "\n".join(cleaned) + "\n```"
    except Exception as exc:
        return f"_Erreur lecture logs: {exc}_"


def _fmt_rapport(p: CommandDataProvider) -> str:
    """Rapport complet envoyé automatiquement toutes les N heures."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%d/%m %H:%M UTC")
    phase = p.get_phase() if p.get_phase else "?"
    thr = p.get_throttle() if p.get_throttle else None
    kpis = p.get_kpis() if p.get_kpis else None
    pos = (p.get_positions() if p.get_positions else None) or []
    sigs = (p.get_signals() if p.get_signals else None) or {}
    trades = (p.get_trades() if p.get_trades else None) or []

    lines = [f"*RAPPORT — {now}*", f"Phase *{phase}*"]
    if thr:
        a = thr.allocated_capital
        el = thr.allocation().days_elapsed()
        mn = thr.allocation().min_duration_days
        lines.append(f"Capital *{a:.2f} USD* — Jour {el:.1f} / {mn}")

    if kpis:
        from capital_deployment.phase_kpi_tracker import PHASE_CRITERIA

        c = PHASE_CRITERIA.get(phase, {})
        wr_t = c.get("min_win_rate", 0.45)
        sh_t = c.get("min_sharpe", 1.0)
        dd_t = c.get("max_drawdown", 0.02)
        lines += [
            "",
            "*PERFORMANCE*",
            _kpi_line(
                "Win Rate",
                f"{kpis.win_rate:.0%}",
                _bar(kpis.win_rate, wr_t),
                f">{wr_t:.0%}",
                _chk(kpis.win_rate, wr_t),
            ),
            _kpi_line(
                "Sharpe",
                f"{kpis.sharpe:.2f}",
                _bar(kpis.sharpe, sh_t),
                f">{sh_t:.1f}",
                _chk(kpis.sharpe, sh_t),
            ),
            _kpi_line(
                "Max DD",
                f"{kpis.max_drawdown:.1%}",
                _bar(kpis.max_drawdown, dd_t, low_good=True),
                f"<{dd_t:.0%}",
                _chk(kpis.max_drawdown, dd_t, low_good=True),
            ),
            f"Trades: {kpis.total_trades}  DD: {kpis.current_drawdown:.1%}",
        ]

    n_pos = len(pos)
    lines += ["", f"*POSITIONS  {n_pos} ouverte{'s' if n_pos != 1 else ''}*"]
    if pos:
        for position in pos:
            try:
                sym = position.get("symbol", "?")
                side = position.get("side", "?").upper()
                pnl = float(position.get("unrealized_pnl", position.get("pnl", 0)))
                pct = float(position.get("pnl_pct", 0))
                sg = "+" if pnl >= 0 else ""
                lines.append(f"  {sym} {side}  {sg}${pnl:.2f} ({sg}{pct:.1f}%)")
            except Exception:
                pass
    else:
        lines.append("  Aucune position")

    if sigs:
        lines += ["", "*SIGNAUX*"]
        items = sigs.items() if isinstance(sigs, dict) else []
        for sym, s in items:
            if isinstance(s, dict):
                score = s.get("score", 0)
                action = s.get("action", s.get("signal", "?"))
                regime = s.get("regime", "")
                lines.append(f"  {sym}  {score}/100  {action}  {regime}")

    if trades:
        from datetime import datetime as _dt

        lines += ["", "*DERNIERS TRADES*"]
        for t in reversed(trades[-3:]):
            try:
                sym = t.get("symbol", "?")
                pnl = float(t.get("pnl", 0))
                sg = "+" if pnl >= 0 else ""
                ts_ = t.get("ts", 0)
                dt_ = _dt.fromtimestamp(ts_).strftime("%m-%d %H:%M") if ts_ else "?"
                lines.append(f"  {dt_}  {sym}  {sg}${pnl:.2f}")
            except Exception:
                pass

    return "\n".join(lines)


# ── Modification .env ─────────────────────────────────────────────────────────


def _write_env(param: str, value: str) -> bool:
    try:
        from dotenv import set_key

        set_key(str(_ENV_PATH), param, value)
        return True
    except Exception as exc:
        _log.error("[CommandCenter] Erreur write .env: %s", exc)
        return False


def _get_env(param: str) -> Optional[str]:
    from dotenv import dotenv_values

    return dotenv_values(_ENV_PATH).get(param)


# ── Bot principal ─────────────────────────────────────────────────────────────

_HELP_TEXT = """
*COMMANDES DISPONIBLES*

STATUS
/status           Resume rapide
/kpis             KPIs detailles
/phase            Phase F-xx + temps restant
/regime           Regime marche par symbole
/signals          Scores signaux
/risk             Etat risque
/health           Sante modules
/eo               ExecutiveOverride (niveau + seuils)
/gate             GlobalRiskGate (conditions actives)
/certif           Certification P10-G (phases signees)

ANALYSE
/perf             Courbe PnL cumulatif ASCII
/recap [n]        Recap N derniers jours (defaut 7)
/history [n]      Entrees/sorties + PnL realise (defaut 20)
/blackbox [n]     Dernieres N entrees BlackBox
/charts           Lien dashboard temps reel (graphiques)

PORTEFEUILLE
/balance          Soldes comptes
/positions        Positions ouvertes (TP/SL/vol/duree)
/pnl              PnL detaille
/trades [n]       Derniers trades

CONFIGURATION
/config                Sections disponibles
/config <section>      Params d'une section
/get <PARAM>           Valeur d'un param
/set <PARAM> <val>     Modifier (+ /confirm)

CONTROLE
/pause            Mode observation seule
/resume           Reprendre trading
/setphase <F-xx>  Changer de phase
/maxorder <usd>   Changer max ordre
/reset            Remettre les KPIs a zero
/restart          Redemarrer advisor_loop (VPS)

SYSTEME
/logs [n]         Derniers logs
/confirm          Confirmer action
/cancel           Annuler
""".strip()


class CommandCenterBot:
    """
    Bot Telegram complet : lecture + ecriture + controle du systeme.
    Thread daemon, confirmation requise pour les actions destructives.
    """

    def __init__(
        self,
        token: str,
        chat_id: str,
        provider: CommandDataProvider,
        report_interval_h: float = 1.0,
    ) -> None:
        self._token = token
        self._chat_id = str(chat_id)
        self._provider = provider
        self._report_s = report_interval_h * 3600.0
        self._running = False
        self._offset = 0
        self._last_report = time.time()  # évite envoi immédiat au démarrage

        # Confirmation pending : {description, action_fn, expires}
        self._pending: Optional[dict] = None
        self._pending_lock = threading.Lock()

    @classmethod
    def from_env(cls, provider: CommandDataProvider) -> "CommandCenterBot":
        token = os.getenv("P10_PORTFOLIO_BOT_TOKEN", "")
        chat_id = os.getenv("P10_PORTFOLIO_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID", ""))
        rep_mins = float(os.getenv("P10_PORTFOLIO_REPORT_MINS", "0"))
        rep_h = (
            rep_mins / 60.0
            if rep_mins > 0
            else float(os.getenv("P10_PORTFOLIO_REPORT_H", "1.0"))
        )
        return cls(
            token=token, chat_id=chat_id, provider=provider, report_interval_h=rep_h
        )

    # ── Démarrage / arrêt ────────────────────────────────────────────────────

    def start(self) -> None:
        if "PYTEST_CURRENT_TEST" in os.environ:
            _log.warning(
                "[CommandCenter] Exécution sous pytest détectée — bot désactivé "
                "(évite l'envoi de messages réels avec données de test)"
            )
            return
        if not self._token:
            _log.warning(
                "[CommandCenter] P10_PORTFOLIO_BOT_TOKEN manquant — bot desactive"
            )
            return
        self._running = True
        threading.Thread(
            target=self._poll_loop, daemon=True, name="CmdBot-Poll"
        ).start()
        threading.Thread(
            target=self._report_loop, daemon=True, name="CmdBot-Report"
        ).start()
        _log.info(
            "[CommandCenter] Demarre — rapport toutes les %.0fmin", self._report_s / 60
        )
        from datetime import datetime, timezone

        _stamp_file = Path(".portfolio_bot_started")
        _now = time.time()
        _last_start = float(_stamp_file.read_text()) if _stamp_file.exists() else 0.0
        if _now - _last_start > 300:  # message "connecte" max 1 fois / 5 min
            _stamp_file.write_text(str(_now))
            rep_label = (
                f"{self._report_s/60:.0f}min"
                if self._report_s < 3600
                else f"{self._report_s/3600:.0f}h"
            )
            self.send(
                f"*Mon Portefeuille — connecte*\n"
                f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}\n"
                f"{_SEP}\n"
                f"Signaux, positions et clotures en direct.\n"
                f"Rapport auto toutes les {rep_label}\n"
                f"Tape /help pour les commandes."
            )

    def stop(self) -> None:
        self._running = False

    # ── Envoi ────────────────────────────────────────────────────────────────

    def send(self, text: str) -> bool:
        if "PYTEST_CURRENT_TEST" in os.environ:
            return False
        if not self._token or not self._chat_id:
            return False
        try:
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            safe = text[:_MAX_MSG].replace("_", "\\_")
            payload = json.dumps(
                {
                    "chat_id": self._chat_id,
                    "text": safe,
                    "parse_mode": "Markdown",
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as exc:
            _log.debug("[CommandCenter] send error: %s", exc)
            return False

    # ── Polling ──────────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        while self._running:
            try:
                updates = self._get_updates()
                for upd in updates:
                    self._offset = max(self._offset, upd["update_id"] + 1)
                    msg = upd.get("message") or upd.get("edited_message", {})
                    if msg:
                        self._route(msg)
            except Exception as exc:
                _log.debug("[CommandCenter] poll error: %s", exc)
                time.sleep(_RETRY_DELAY)

    def _get_updates(self) -> list[dict]:
        url = (
            f"https://api.telegram.org/bot{self._token}/getUpdates"
            f"?offset={self._offset}&timeout={_POLL_TIMEOUT}"
        )
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=_POLL_TIMEOUT + 5) as resp:
            return json.loads(resp.read().decode())["result"]

    # ── Routage des commandes ─────────────────────────────────────────────────

    def _route(self, msg: dict) -> None:
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id != self._chat_id:
            return
        raw = (msg.get("text") or "").strip()
        if not raw:
            return
        parts = raw.split()
        cmd = parts[0].lower().split("@")[0]  # /command@botname → /command
        args = parts[1:]

        handlers = {
            "/help": lambda: _HELP_TEXT,
            "/start": lambda: _HELP_TEXT,
            "/status": lambda: _fmt_status(self._provider),
            "/kpis": lambda: _fmt_kpis(self._provider),
            "/balance": lambda: _fmt_balance(self._provider),
            "/positions": lambda: _fmt_positions(self._provider),
            "/pnl": lambda: _fmt_pnl(self._provider),
            "/phase": lambda: _fmt_phase(self._provider),
            "/regime": lambda: _fmt_regime(self._provider),
            "/signals": lambda: _fmt_signals(self._provider),
            "/risk": lambda: _fmt_risk(self._provider),
            "/health": lambda: _fmt_health(self._provider),
            "/eo": lambda: _fmt_eo(self._provider),
            "/gate": lambda: _fmt_gate(self._provider),
            "/perf": lambda: _fmt_perf(self._provider),
            "/certif": lambda: _fmt_certif(),
            "/charts": lambda: _fmt_charts_button(),
            "/confirm": lambda: self._do_confirm(),
            "/cancel": lambda: self._do_cancel(),
        }

        if cmd in handlers:
            try:
                reply = handlers[cmd]()
                self.send(reply)
            except Exception as exc:
                self.send(f"Erreur: `{exc}`")
            return

        # Commandes avec arguments
        try:
            if cmd == "/config":
                section = args[0] if args else None
                self.send(_fmt_config(section))

            elif cmd == "/get":
                if not args:
                    self.send("Usage: `/get PARAM`")
                    return
                val = _get_env(args[0].upper())
                self.send(f"`{args[0].upper()}` = `{val or '_non defini_'}`")

            elif cmd == "/logs":
                n = int(args[0]) if args else 20
                n = min(n, 50)
                self.send(_fmt_logs(n))

            elif cmd == "/trades":
                n = int(args[0]) if args else 10
                self.send(_fmt_trades(self._provider, n))

            elif cmd == "/set":
                if len(args) < 2:
                    self.send("Usage: `/set PARAM valeur`")
                    return
                param = args[0].upper()
                value = " ".join(args[1:])
                self._queue_set(param, value)

            elif cmd == "/pause":
                self._queue_action(
                    description="Passer en mode OBSERVATION (V9_ADVISOR_ONLY=true)",
                    action=lambda: self._apply_set("V9_ADVISOR_ONLY", "true"),
                )

            elif cmd == "/resume":
                self._queue_action(
                    description="Reprendre TRADING ACTIF (V9_ADVISOR_ONLY=false)",
                    action=lambda: self._apply_set("V9_ADVISOR_ONLY", "false"),
                )

            elif cmd == "/setphase":
                if not args:
                    self.send("Usage: `/setphase F-02`")
                    return
                phase = args[0].upper()
                if phase not in ["F-01", "F-02", "F-03", "F-04", "F-05"]:
                    self.send(
                        f"Phase invalide: `{phase}`\nValides: F-01 F-02 F-03 F-04 F-05"
                    )
                    return
                self._queue_action(
                    description=f"Changer phase → {phase}",
                    action=lambda: self._apply_set("P10_PHASE", phase),
                )

            elif cmd == "/maxorder":
                if not args:
                    self.send("Usage: `/maxorder 75` (en USD)")
                    return
                try:
                    val = float(args[0])
                    if val <= 0:
                        raise ValueError
                except ValueError:
                    self.send("Valeur invalide — doit etre un nombre positif")
                    return
                self._queue_action(
                    description=f"Changer EXEC_MAX_ORDER_USD → {val:.2f}",
                    action=lambda: self._apply_set("EXEC_MAX_ORDER_USD", str(val)),
                )

            elif cmd == "/blackbox":
                n = int(args[0]) if args else 10
                n = min(max(n, 1), 50)
                self.send(_fmt_blackbox(self._provider, n))

            elif cmd == "/history":
                n = int(args[0]) if args else 20
                n = min(max(n, 1), 50)
                self.send(_fmt_history(self._provider, n))

            elif cmd == "/recap":
                raw_days = args[0].rstrip("j").rstrip("d") if args else "7"
                try:
                    days = int(raw_days)
                except ValueError:
                    days = 7
                self.send(_fmt_recap(self._provider, days))

            elif cmd == "/reset":
                self._queue_action(
                    description="Remettre les KPIs à zéro (nouvelle phase)",
                    action=self._do_reset_kpis,
                )

            elif cmd == "/restart":
                self._queue_action(
                    description="Redémarrer advisor_loop.py sur le VPS",
                    action=self._do_restart,
                )

            elif cmd.startswith("/"):
                self.send(f"Commande inconnue: `{cmd}`\nTape /help")

        except Exception as exc:
            _log.error("[CommandCenter] route error on %s: %s", cmd, exc)
            self.send(f"Erreur: `{exc}`")

    # ── Confirmation ─────────────────────────────────────────────────────────

    def _queue_action(self, description: str, action: Callable[[], Any]) -> None:
        with self._pending_lock:
            self._pending = {
                "description": description,
                "action": action,
                "expires": time.time() + _CONFIRM_TTL,
            }
        self.send(
            f"ACTION EN ATTENTE:\n`{description}`\n\n"
            f"Tape /confirm pour executer ou /cancel pour annuler ({_CONFIRM_TTL:.0f}s)"
        )

    def _queue_set(self, param: str, value: str) -> None:
        old_value = _get_env(param)  # capturer avant confirmation
        command_str = f"/set {param} {value}"
        live_tag = " [live]" if param in _LIVE_PARAMS else " [redemarrage requis]"
        self._queue_action(
            description=f"{param}: `{old_value}` → `{value}`{live_tag}",
            action=lambda: self._apply_set(
                param, value, old_value=old_value, command=command_str
            ),
        )

    def _do_confirm(self) -> str:
        with self._pending_lock:
            p = self._pending
            if p is None:
                return "_Aucune action en attente_"
            if time.time() > p["expires"]:
                self._pending = None
                return "_Action expiree (> 60s). Recommence._"
            action = p["action"]
            desc = p["description"]
            self._pending = None

        try:
            result = action()
            _log.info("[CommandCenter] Action confirmee: %s", desc)
            ok_str = str(result) if result is not None else "OK"
            return f"Confirme: `{desc}`\nResultat: {ok_str}"
        except Exception as exc:
            return f"Erreur execution: `{exc}`"

    def _do_cancel(self) -> str:
        with self._pending_lock:
            if self._pending is None:
                return "_Aucune action en attente_"
            self._pending = None
        return "Action annulee"

    # ── Actions système ──────────────────────────────────────────────────────

    def _do_reset_kpis(self) -> str:
        if self._provider.reset_kpis:
            try:
                ok = self._provider.reset_kpis()
                return "KPIs remis a zero" if ok else "reset_kpis a retourne False"
            except Exception as exc:
                return f"Erreur reset: {exc}"
        return "reset_kpis non cable — relance manuelle requise"

    def _do_restart(self) -> str:
        import subprocess

        script = Path(__file__).parent.parent / "scripts" / "vps_restart.sh"
        if not script.exists():
            return f"Script introuvable: {script}"
        try:
            result = subprocess.Popen(
                ["bash", str(script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            _log.info("[CommandCenter] vps_restart.sh lance PID=%s", result.pid)
            return f"Redemarrage lance — PID {result.pid}\n(logs dans logs/advisor.log)"
        except Exception as exc:
            return f"Erreur restart: {exc}"

    # ── Application des changements ───────────────────────────────────────────

    def _apply_set(
        self,
        param: str,
        value: str,
        old_value: str = "",
        command: str = "",
    ) -> str:
        from config.parameter_audit import record_parameter_change

        # 1. Audit append-only (avant écriture pour capturer l'ancien état)
        change_id = record_parameter_change(
            parameter=param,
            old_value=old_value,
            new_value=value,
            source="telegram",
            command=command or f"/set {param} {value}",
            operator=self._chat_id,
        )

        # 2. Ecrire dans .env
        written = _write_env(param, value)
        os.environ[param] = value  # mise a jour process courant aussi

        # 3. Appliquer live si possible
        live_ok = False
        if param in _LIVE_PARAMS and self._provider.set_param:
            try:
                live_ok = self._provider.set_param(param, value)
            except Exception as exc:
                _log.warning("[CommandCenter] set_param live error: %s", exc)

        env_tag = ".env mis a jour" if written else "ERREUR ecriture .env"
        live_tag = (
            " + applique live" if live_ok else " (redemarrage pour effet complet)"
        )
        _log.info(
            "[CommandCenter] SET %s=%s — %s%s [%s]",
            param,
            value,
            env_tag,
            live_tag,
            change_id,
        )
        return f"{env_tag}{live_tag}\n`{change_id}`"

    # ── Rapport automatique ───────────────────────────────────────────────────

    def _report_loop(self) -> None:
        while self._running:
            time.sleep(60)
            if not self._running:
                break
            if time.time() - self._last_report >= self._report_s:
                try:
                    self.send(_fmt_rapport(self._provider))
                    self._last_report = time.time()
                except Exception as exc:
                    _log.debug("[CommandCenter] auto-report error: %s", exc)
