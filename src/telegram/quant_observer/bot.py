"""@QuantCrypto_bot — SDOS Visualization Client.

Architecture (SVA v1.0):
    User command → load API snapshot → VES.render() → PNG → Telegram

The bot contains ZERO business logic. It calls the Data API, delegates
to the VES, and publishes the result. It does not read databases directly.
"""

from __future__ import annotations

import asyncio  # noqa: F401
import io
import logging
import os
import time
from pathlib import Path  # noqa: F401

import requests

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

QC_BOT_TOKEN = os.getenv("QC_BOT_TOKEN", "")
QC_CHAT_ID = os.getenv("QC_CHAT_ID", "")
QC_PINNED_MSG = os.getenv("QC_PINNED_MSG_ID", "")  # ID of the pinned live message

POLL_INTERVAL_S = int(os.getenv("QC_POLL_INTERVAL", "2"))
PINNED_UPDATE_S = int(os.getenv("QC_PINNED_UPDATE", "600"))  # 10 min

_API_BASE = f"https://api.telegram.org/bot{QC_BOT_TOKEN}"

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


# ── Pinned message (V3 text, auto-refreshed every 10 min) ────────────────────


def _build_pinned_text() -> str:
    from visualization.api import load_health_snapshot, load_pipeline_snapshot
    from visualization.renderers.base import bar_text, pct_to_color  # noqa: F401

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

COMMANDS: dict[str, tuple[str, callable]] = {
    "/snapshot": ("SDOS Snapshot (4 panels)", _render_snapshot),
    "/health": ("System Health (radar)", _render_health),
    "/pipeline": ("Decision Pipeline", _render_pipeline),
    "/portfolio": ("Portfolio KPIs", _render_portfolio),
}


def _handle_command(text: str, chat_id: str):
    cmd = text.strip().lower().split()[0]
    if cmd == "/start" or cmd == "/help":
        help_text = (
            "<b>@QuantCrypto_bot — SDOS Observer</b>\n\n"
            + "\n".join(
                f"<code>{c}</code> — {desc}" for c, (desc, _) in COMMANDS.items()
            )
            + "\n\n<i>SVA v1.0 — Scientific Visualization Architecture</i>"
        )
        send_message(chat_id, help_text)
        return

    if cmd in COMMANDS:
        desc, renderer_fn = COMMANDS[cmd]
        try:
            png = renderer_fn()
            send_photo(chat_id, png, caption=f"SDOS — {desc}")
        except Exception as e:
            logger.exception("Render error for %s", cmd)
            send_message(chat_id, f"⚠️ Render error: {e}")
    else:
        send_message(chat_id, f"Unknown command: <code>{cmd}</code>\nUse /help")


# ── Main polling loop ─────────────────────────────────────────────────────────


def run():
    if not QC_BOT_TOKEN:
        raise RuntimeError("QC_BOT_TOKEN not set. Add it to .env.")
    if not QC_CHAT_ID:
        raise RuntimeError("QC_CHAT_ID not set. Add it to .env.")

    logger.info("@QuantCrypto_bot starting — SVA v1.0")
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
