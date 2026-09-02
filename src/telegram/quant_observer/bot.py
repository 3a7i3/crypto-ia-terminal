"""@QuantCrypto_bot — SDOS Visualization Client.

Architecture (SVA v1.0):
    User command → load API snapshot → VES.render() → PNG → Telegram

The bot contains ZERO business logic. It calls the Data API, delegates
to the VES, and publishes the result. It does not read databases directly.
"""

from __future__ import annotations

import asyncio  # noqa: F401
import html
import io
import logging
import os
import time
from pathlib import Path  # noqa: F401

# Kept for display-time consistency across the bot's Telegram surface; the Q1
# LIVE panel reports snapshot *age* (freshness) rather than a wall-clock stamp.
from src.common.time_display import format_vancouver_time  # noqa: F401

import requests

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

QC_BOT_TOKEN = os.getenv("QUANT_CRYPTO_BOT_TOKEN", "")
QC_CHAT_ID = os.getenv("QUANT_CRYPTO_CHAT_ID", "")
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
    """Redirigé vers Portfolio Bot — domaine incorrect pour Quant Observer.
    Conservé pour compatibilité ascendante mais ne rend plus de données portfolio.
    Voir docs/architecture/TELEGRAM_BOT_REGISTRY.md.
    """
    raise NotImplementedError(
        "Le domaine portfolio appartient à 💼 Mon Portfolio bot (MON_PORTFOLIO_BOT_TOKEN). "
        "Cette commande a été retirée de Quant Observer."
    )


# ── Pinned LIVE panel (Q1 — semantically-honest, READ-ONLY projection) ────────
#
# The panel answers ONLY the Quant Observer question: what does the engine see,
# what decision does it produce, where is the attrition, is the chain healthy?
# It is fed exclusively by the READ-ONLY QuantLiveSnapshot projection — no
# portfolio/capital/PnL/win-rate (Portfolio Bot domain), no
# observer/dataset/knowledge/evidence/drift proxies (semantically wrong), no
# host metrics (RAM/CPU/PID), no Telegram/main_channel health.

_LAYER_LABELS = {
    "gate": "Risk gates",
    "meta_strategy": "Meta-strategy",
    "no_trade_layer": "No-trade layer",
    "portfolio": "Portfolio brain",
    "risk": "Risk override",
    "cooldown": "Cooldown",
    "exchange": "Exchange",
}


def _layer_label(key: str) -> str:
    return _LAYER_LABELS.get(key, key.replace("_", " ").capitalize())


def _esc(value) -> str:
    """Escape any dynamic value for Telegram HTML (<, >, &).

    All non-static text placed in the panel goes through this so producer
    strings (engine version, reason_text, gate_reason, symbols, pipeline and
    trace fields, …) can never be interpreted as HTML / injected.
    """
    return html.escape(str(value), quote=False)


def _row(label: str, value: str, width: int = 18) -> str:
    # Pad on the RAW label (alignment), then escape label AND value. Padding
    # before escaping keeps column width correct — entities render as one glyph.
    padded = f"{label:<{width}}"
    return f"<code>{_esc(padded)}{_esc(value)}</code>"


def _ok(flag: bool) -> str:
    return "OK" if flag else "DOWN"


def _fmt_score(value: float) -> str:
    return f"{value:.0f}" if float(value).is_integer() else f"{value:g}"


def render_quant_live_panel(snap) -> str:
    """Pure formatter: QuantLiveSnapshot → Telegram HTML LIVE panel.

    No I/O, no side effects — safe to unit-test with a constructed snapshot.
    All dynamic values are HTML-escaped (see ``_esc`` / ``_row``); only the
    static tags (<b>, <code>) are literal markup.
    """
    engine = snap.engine_version or "n/a"
    score_txt = _fmt_score(snap.top_candidate_score)
    required_txt = _fmt_score(snap.required_score)
    age = snap.snapshot_age_s
    age_txt = "UNAVAILABLE" if age is None else f"{age:.0f}s"
    lines = [
        "🔬 <b>SDOS LIVE</b>",
        f"<code>Cycle {_esc(snap.cycle)} · Engine {_esc(engine)}</code>",
        "",
        "<b>DATA</b>",
        _row("Snapshot age", age_txt),
        _row("Market", _ok(snap.health_market)),
        _row("API", _ok(snap.health_api)),
        "",
        "<b>MARKET</b>",
        _row("Regime", (snap.regime or "unknown").replace("_", " ").upper()),
        _row("Exchange latency", f"{snap.exchange_latency_ms:.0f} ms"),
        _row("Exchange uptime", f"{snap.exchange_uptime_pct:.0f}%"),
        "",
        "<b>DECISION</b>",
        _row("State", snap.state or "—"),
        _row("Top candidate", snap.top_candidate_symbol or "—"),
        _row("Score", f"{score_txt} / {required_txt}"),
        # FIX 3 — producer value is the mean of signal scores, not a confidence.
        _row("Mean signal score", f"{snap.mean_signal_score} / 100"),
    ]
    if snap.reason_text:
        lines.append(_row("Reason", snap.reason_text))
    if snap.gate_reason:
        lines.append(_row("Gate", snap.gate_reason))
    lines.append(_row("Next evaluation", f"{snap.next_evaluation_sec}s"))

    # ── ATTRITION — current cycle only ──
    lines += ["", "<b>ATTRITION — CURRENT CYCLE</b>"]
    if snap.refusal_breakdown:
        for key, count in sorted(
            snap.refusal_breakdown.items(), key=lambda kv: (-kv[1], kv[0])
        ):
            lines.append(_row(_layer_label(key), str(count)))
        lines.append(_row("Total refusals", str(snap.total_refusals)))
        dominant = snap.dominant_filter
        if dominant is not None:
            lines += [
                "",
                "<b>DOMINANT FILTER</b>",
                _row(_layer_label(dominant), f"{snap.dominant_filter_pct:.1f}%"),
            ]
    else:
        lines.append(_row("Total refusals", "0"))

    # ── PIPELINE — REPORTED / PARTIAL ──
    # FIX 5 — this is the state DECLARED by the producer, not independent health
    # instrumentation: some stages are OK by construction. Not proof the chain
    # is sound. Telegram/main_channel is excluded upstream (projection).
    if snap.pipeline_stages:
        lines += ["", "<b>PIPELINE — REPORTED / PARTIAL</b>"]
        for stage in snap.pipeline_stages:
            status = stage.get("status", "")
            message = stage.get("message", "")
            value = f"{status} · {message}" if message else status
            lines.append(_row(stage.get("name", ""), value))

    # ── LIVE TRACE — PARTIAL ──
    # FIX 6 — only the nodes actually present in the snapshot; NOT the full
    # causal chain. No synthetic Gate/MetaStrategy/etc. nodes are invented.
    if snap.decision_trace:
        lines += ["", "<b>LIVE TRACE — PARTIAL</b>"]
        for node in snap.decision_trace:
            parts = [str(node.get("decision", ""))]
            score = node.get("score")
            if score is not None:
                parts.append(_fmt_score(score))
            reason_code = node.get("reason_code")
            if reason_code:
                parts.append(str(reason_code))
            lines.append(_row(node.get("node", ""), " · ".join(p for p in parts if p)))

    return "\n".join(lines)


def _build_pinned_text() -> str:
    from visualization.api import load_quant_live_snapshot

    return render_quant_live_panel(load_quant_live_snapshot())


# ── Command dispatch ──────────────────────────────────────────────────────────

COMMANDS: dict[str, tuple[str, callable]] = {
    "/snapshot": ("SDOS Snapshot (4 panels)", _render_snapshot),
    "/health": ("System Health (radar)", _render_health),
    "/pipeline": ("Decision Pipeline", _render_pipeline),
    # /portfolio retiré — domaine Portfolio (TELEGRAM_BOT_REGISTRY.md)
}


def _handle_command(text: str, chat_id: str):
    cmd = text.strip().lower().split()[0]
    if cmd == "/start" or cmd == "/help":
        help_text = (
            "<b>@QuantCrypto_bot — SDOS Observer</b>\n\n"
            + "\n".join(
                f"<code>{c}</code> — {desc}" for c, (desc, _) in COMMANDS.items()
            )
            + "\n\n<i>Domaine : microstructure SDOS. Pas de données portfolio.</i>"
            "\n<i>SVA v1.0 — Scientific Visualization Architecture</i>"
        )
        send_message(chat_id, help_text)
        return

    if cmd == "/portfolio":
        send_message(
            chat_id,
            "\U0001f52c Quant Observer — domaine SDOS uniquement\n\n"
            "Les KPIs portfolio appartiennent à \U0001f4bc Mon Portfolio bot.\n\n"
            "Commandes disponibles ici : /snapshot /health /pipeline",
        )
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
        raise RuntimeError("QUANT_CRYPTO_BOT_TOKEN not set. Add it to .env.")
    if not QC_CHAT_ID:
        raise RuntimeError("QUANT_CRYPTO_CHAT_ID not set. Add it to .env.")

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
