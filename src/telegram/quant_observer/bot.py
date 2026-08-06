"""@QuantCrypto_bot — SDOS Visualization Client.

Architecture (SVA v1.0):
    User command → load API snapshot → VES.render() → PNG → Telegram
    User command → load API snapshot → formatters.format_*() → HTML → Telegram

The bot contains ZERO business logic. It calls the Data API, delegates rendering
to the VES (charts) or to `formatters` (text), and publishes the result. It does
not read databases directly and never computes a metric of its own.

Strictly read-only (ADR-0007 — passivité des observers): there is no command
that writes, calibrates, restarts, or otherwise touches the decision engine.
Adding one would require a signed ADR, not a new entry in COMMANDS.

Access is allowlisted (`QC_ALLOWED_CHAT_IDS`): anyone who discovers the bot
handle can otherwise message it, and these commands disclose capital, dataset
counts and log tails.
"""

from __future__ import annotations

import io
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

QC_BOT_TOKEN = os.getenv("QC_BOT_TOKEN", "")
QC_CHAT_ID = os.getenv("QC_CHAT_ID", "")
QC_PINNED_MSG = os.getenv("QC_PINNED_MSG_ID", "")  # ID of the pinned live message

POLL_INTERVAL_S = int(os.getenv("QC_POLL_INTERVAL", "2"))
PINNED_UPDATE_S = int(os.getenv("QC_PINNED_UPDATE", "600"))  # 10 min

_API_BASE = f"https://api.telegram.org/bot{QC_BOT_TOKEN}"

# ── Authorization ─────────────────────────────────────────────────────────────


def allowed_chat_ids() -> set[str]:
    """Chat ids permitted to issue commands.

    `QC_ALLOWED_CHAT_IDS` (comma-separated) when set, else the single
    `QC_CHAT_ID`. Read from the environment on each call so the allowlist can be
    changed without touching import order.
    """
    raw = os.getenv("QC_ALLOWED_CHAT_IDS", "")
    if raw.strip():
        return {part.strip() for part in raw.split(",") if part.strip()}
    single = os.getenv("QC_CHAT_ID", "").strip()
    return {single} if single else set()


def is_authorized(chat_id: str) -> bool:
    """Fail closed: an empty allowlist authorizes nobody."""
    allowed = allowed_chat_ids()
    if not allowed:
        logger.error(
            "No QC_ALLOWED_CHAT_IDS / QC_CHAT_ID configured — refusing all commands."
        )
        return False
    return str(chat_id).strip() in allowed


# ── Telegram helpers ──────────────────────────────────────────────────────────


def _post(method: str, **kwargs) -> dict:
    try:
        r = requests.post(f"{_API_BASE}/{method}", timeout=15, **kwargs)
        return r.json()
    except Exception as e:
        logger.error("Telegram %s failed: %s", method, e)
        return {}


def send_photo(chat_id: str, png_bytes: bytes, caption: str = "") -> dict:
    return _post(
        "sendPhoto",
        files={"photo": ("chart.png", io.BytesIO(png_bytes), "image/png")},
        data={"chat_id": chat_id, "caption": caption},
    )


def send_message(chat_id: str, text: str, parse_mode: str = "HTML") -> dict:
    return _post(
        "sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    )


def edit_message(chat_id: str, message_id: str, text: str) -> dict:
    return _post(
        "editMessageText",
        json={
            "chat_id": chat_id,
            "message_id": int(message_id),
            "text": text,
            "parse_mode": "HTML",
        },
    )


def get_updates(offset: int = 0) -> list[dict]:
    data = _post("getUpdates", json={"timeout": 20, "offset": offset})
    return data.get("result", [])


# ── SVA rendering helpers ─────────────────────────────────────────────────────


def _ves():
    from visualization.ves import VisualizationEngine

    return VisualizationEngine()


def _render_snapshot() -> bytes:
    ves = _ves()
    return ves.render_snapshot(viewer_level=3)


def _render_health() -> bytes:
    from visualization.api import load_health_snapshot

    return _ves().render(load_health_snapshot(), viewer_level=3)


def _render_pipeline() -> bytes:
    from visualization.api import load_pipeline_snapshot

    return _ves().render(load_pipeline_snapshot(), viewer_level=3)


def _render_portfolio() -> bytes:
    from visualization.api import load_portfolio_snapshot

    return _ves().render(load_portfolio_snapshot(), viewer_level=3)


# ── Text commands ─────────────────────────────────────────────────────────────
#
# Each takes the raw argument list and returns a Telegram-HTML string. Imports
# stay function-local so a text command never pays the matplotlib import that
# `visualization.renderers` performs at module scope.

_REGRET_TYPES = ("MISSED_WIN", "GOOD_REFUSAL", "CORRECT_TRADE", "BAD_TRADE")


def _text_burnin(args: list[str]) -> str:
    from src.telegram.quant_observer import formatters
    from visualization.api import load_burnin_snapshot

    return formatters.format_burnin(load_burnin_snapshot())


def _text_cri(args: list[str]) -> str:
    from src.telegram.quant_observer import formatters
    from visualization.api import load_cri_snapshot

    return formatters.format_cri(load_cri_snapshot())


def _text_regret(args: list[str]) -> str:
    from src.telegram.quant_observer import formatters
    from visualization.api import load_regret_investigation

    regret_type = args[0].upper() if args else "MISSED_WIN"
    snap = load_regret_investigation(regret_type=regret_type)
    text = formatters.format_regret(snap)
    if snap.n_total == 0 and regret_type not in _REGRET_TYPES:
        text += "\n\n<i>Types connus : " + ", ".join(_REGRET_TYPES) + "</i>"
    return text


def _text_science(args: list[str]) -> str:
    from src.telegram.quant_observer import formatters
    from visualization.api import load_scientific_snapshot

    return formatters.format_science(load_scientific_snapshot())


def _text_timeline(args: list[str]) -> str:
    from src.telegram.quant_observer import formatters
    from visualization.api import load_timeline_snapshot

    limit = _first_int(args, default=12, maximum=25)
    return formatters.format_timeline(load_timeline_snapshot(), limit=limit)


def _text_rejects(args: list[str]) -> str:
    from src.telegram.quant_observer import formatters
    from visualization.api import load_rejections_snapshot

    days = _first_int(args, default=1, maximum=30)
    return formatters.format_rejections(load_rejections_snapshot(days=days, limit=20))


def _text_datasets(args: list[str]) -> str:
    from src.telegram.quant_observer import formatters
    from visualization.api import load_datasets_snapshot

    return formatters.format_datasets(load_datasets_snapshot())


def _text_logs(args: list[str]) -> str:
    """`/logs [name] [n] [ERROR|WARNING|INFO]` — order-independent arguments."""
    from src.telegram.quant_observer import formatters
    from visualization.api import load_log_tail
    from visualization.api.logs_api import ALLOWED_LOGS, DEFAULT_LOG

    log_key = DEFAULT_LOG
    n_lines = 30
    level = "ALL"

    for token in args:
        candidate = token.strip().lower()
        if candidate.isdigit():
            n_lines = int(candidate)
        elif candidate.upper() in ("ERROR", "WARNING", "INFO", "ALL"):
            level = candidate.upper()
        elif candidate in ALLOWED_LOGS:
            log_key = candidate
        else:
            return (
                f"⚠️ Argument inconnu : <code>{formatters.esc(token)}</code>\n"
                f"Logs disponibles : <code>{', '.join(sorted(ALLOWED_LOGS))}</code>"
            )

    return formatters.format_logs(
        load_log_tail(log_key=log_key, n_lines=n_lines, level_filter=level)
    )


def _first_int(args: list[str], default: int, maximum: int) -> int:
    for token in args:
        if token.strip().isdigit():
            return max(1, min(int(token.strip()), maximum))
    return default


# ── Pinned message (V3 text, auto-refreshed every 10 min) ────────────────────


def _build_pinned_text() -> str:
    from src.telegram.quant_observer.formatters import bar as bar_text
    from visualization.api import load_health_snapshot, load_pipeline_snapshot

    h = load_health_snapshot()
    p = load_pipeline_snapshot()

    state_icon = "✅" if h.system_state == "NORMAL" else "🚨"
    trade_icon = "🟢" if h.trading_enabled else "🔴"

    def row(label: str, pct: float, val_override: str = "") -> str:
        bar = bar_text(pct, 10)
        icon = "✅" if pct >= 80 else ("⚠️" if pct >= 50 else "🚨")
        val = val_override or f"{pct:.0f}%"
        return f"<code>{label:<10} {bar}  {val}  {icon}</code>"

    lines = [
        f"📍 <b>SDOS LIVE</b> — {h.ts.strftime('%H:%M')} UTC",
        "",
        "<b>SANTÉ SYSTÈME</b>",
        row("Observer", h.observer_pct),
        row("Dataset", h.dataset_pct),
        row("Knowledge", h.knowledge_pct),
        row("Evidence", h.evidence_pct),
        row("Capital", h.capital_pct, f"${h.capital_usd:,.0f}"),
        row("Drift", 100 - h.drift_pct, f"{h.drift_pct:.0f}%↓"),
        "",
        f"<b>PIPELINE</b>  [{p.n_signals} signaux]",
        f"<code>Traités:  {p.n_traded}  |  Refusés: {p.n_refused}  |  "
        f"Pass: {p.pass_rate_pct:.0f}%</code>",
    ]

    if p.regime_distribution:
        dominant = max(p.regime_distribution, key=p.regime_distribution.get)
        total = sum(p.regime_distribution.values()) or 1
        pct = p.regime_distribution[dominant] / total * 100
        lines.append(f"<code>Régime:   {dominant}  {pct:.0f}%</code>")

    lines += [
        "",
        f"<code>{state_icon} {h.system_state}  {trade_icon}  "
        f"N={h.n_trades}  WR={h.win_rate_pct:.0f}%</code>",
    ]

    return "\n".join(lines)


# ── Command dispatch ──────────────────────────────────────────────────────────

# command → (description, kind, handler). "photo" handlers take no argument and
# return PNG bytes; "text" handlers take the argument list and return HTML.
COMMANDS: dict[str, tuple[str, str, callable]] = {
    # Charts (VES)
    "/snapshot": ("SDOS Snapshot (4 panneaux)", "photo", _render_snapshot),
    "/health": ("Santé système (radar)", "photo", _render_health),
    "/pipeline": ("Pipeline de décision", "photo", _render_pipeline),
    "/portfolio": ("KPIs portefeuille", "photo", _render_portfolio),
    # Scientific state (text)
    "/burnin": ("Seuils du statisticien", "text", _text_burnin),
    "/cri": ("Calibration Readiness Index", "text", _text_cri),
    "/science": ("Certification observer + DIP", "text", _text_science),
    "/datasets": ("Historique des certifications", "text", _text_datasets),
    # Decision audit (text)
    "/regret": ("Regret [TYPE]", "text", _text_regret),
    "/rejects": ("Analyse des rejets [jours]", "text", _text_rejects),
    "/timeline": ("Décisions récentes [n]", "text", _text_timeline),
    # Runtime (text)
    "/logs": ("Logs [nom] [n] [niveau]", "text", _text_logs),
}


def _help_text() -> str:
    return (
        "<b>@QuantCrypto_bot — SDOS Observer</b>\n"
        "<i>Lecture seule. Aucune commande n'écrit ni ne décide.</i>\n\n"
        + "\n".join(
            f"<code>{cmd}</code> — {desc}" for cmd, (desc, _, _) in COMMANDS.items()
        )
        + "\n\n<i>SVA v1.0 — Scientific Visualization Architecture</i>"
    )


def _handle_command(text: str, chat_id: str):
    parts = text.strip().split()
    if not parts:
        return
    cmd = parts[0].lower()
    # "/cri@QuantCrypto_bot" — Telegram appends the handle in group chats.
    cmd = cmd.split("@", 1)[0]
    args = parts[1:]

    if cmd in ("/start", "/help"):
        send_message(chat_id, _help_text())
        return

    entry = COMMANDS.get(cmd)
    if entry is None:
        send_message(chat_id, f"Commande inconnue : <code>{cmd}</code>\n/help")
        return

    desc, kind, handler = entry
    try:
        if kind == "photo":
            send_photo(chat_id, handler(), caption=f"SDOS — {desc}")
        else:
            send_message(chat_id, handler(args))
    except Exception as e:
        logger.exception("Handler error for %s", cmd)
        send_message(chat_id, f"⚠️ Erreur ({desc}) : {e}")


# ── Main polling loop ─────────────────────────────────────────────────────────


def run():
    if not QC_BOT_TOKEN:
        raise RuntimeError("QC_BOT_TOKEN not set. Add it to .env.")
    if not QC_CHAT_ID:
        raise RuntimeError("QC_CHAT_ID not set. Add it to .env.")

    allowed = allowed_chat_ids()
    if not allowed:
        raise RuntimeError(
            "No authorized chat: set QC_ALLOWED_CHAT_IDS (or QC_CHAT_ID) in .env."
        )

    logger.info(
        "@QuantCrypto_bot starting — SVA v1.0 — %d authorized chat(s), %d commands",
        len(allowed),
        len(COMMANDS),
    )
    offset = 0
    last_pinned_update = 0.0

    while True:
        try:
            # Update pinned live message every PINNED_UPDATE_S seconds
            now = time.time()
            if QC_PINNED_MSG and (now - last_pinned_update) >= PINNED_UPDATE_S:
                try:
                    edit_message(QC_CHAT_ID, QC_PINNED_MSG, _build_pinned_text())
                    last_pinned_update = now
                except Exception as e:
                    logger.warning("Pinned update failed: %s", e)

            # Poll for commands
            updates = get_updates(offset=offset)
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                text = msg.get("text", "")
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if text.startswith("/") and chat_id:
                    if not is_authorized(chat_id):
                        # Stay silent: replying would confirm the bot is live to
                        # an unknown chat. The rejection is logged instead.
                        logger.warning(
                            "Refused command %r from unauthorized chat %s",
                            text[:40],
                            chat_id,
                        )
                        continue
                    logger.info("Command: %s from %s", text, chat_id)
                    _handle_command(text, chat_id)

        except KeyboardInterrupt:
            logger.info("Bot stopped.")
            break
        except Exception as e:
            logger.exception("Polling error: %s", e)
            time.sleep(5)

        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    run()
