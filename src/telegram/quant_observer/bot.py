"""@QuantCrypto_bot — SDOS Visualization Client.

Architecture (SVA v1.0):
    User command → load API snapshot → VES.render() → PNG → Telegram

The bot contains ZERO business logic. It calls the Data API, delegates
to the VES, and publishes the result. It does not read databases directly.
"""

from __future__ import annotations

import asyncio  # noqa: F401
import hashlib
import html
import io
import json
import logging
import math
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path  # noqa: F401
from typing import Any, Optional

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
QC_SAFETY_REFRESH_S = int(os.getenv("QC_SAFETY_REFRESH", "1800"))  # 30 min
QC_LIVE_RETRY_S = int(os.getenv("QC_LIVE_RETRY", "30"))

_API_BASE = f"https://api.telegram.org/bot{QC_BOT_TOKEN}"

# HTTP timeouts (seconds).
#  - Default write ops (send/edit): short, no long-poll.
#  - getUpdates long-polls Telegram for QC_LONGPOLL_S; the HTTP read timeout MUST
#    be strictly greater than the long-poll, otherwise requests aborts the socket
#    exactly while Telegram is legitimately holding the connection open — turning
#    every idle poll into a spurious network failure. Property enforced below.
_HTTP_TIMEOUT_S = 15
QC_LONGPOLL_S = 20  # Telegram getUpdates long-poll window
_GETUPDATES_HTTP_TIMEOUT_S = 25  # MUST be > QC_LONGPOLL_S (see _post/get_updates)
assert _GETUPDATES_HTTP_TIMEOUT_S > QC_LONGPOLL_S, (
    "getUpdates HTTP timeout must exceed the Telegram long-poll window"
)


# ── Telegram delivery result (TG-QC-001) ──────────────────────────────────────
#
# A Telegram call has a *scientific* outcome, never an implicit one. `{}` is
# never success. Every call funnels through _post() and returns a TransportResult
# that distinguishes: real ACK, "no change" (already current), Telegram API
# error (ok=false), HTTP error, invalid/non-JSON body, and network exception.


class DeliveryKind(str, Enum):
    ACK = "ACK"                    # HTTP 2xx AND Telegram {"ok": true}
    NO_CHANGE = "NO_CHANGE"        # strict editMessageText HTTP/TG 400 already-current
    TELEGRAM_ERROR = "TELEGRAM_ERROR"   # valid JSON with {"ok": false, ...}
    HTTP_ERROR = "HTTP_ERROR"      # non-2xx HTTP not classified as a Telegram error
    INVALID_RESPONSE = "INVALID_RESPONSE"  # 2xx but body is not JSON / lacks "ok"
    NETWORK_ERROR = "NETWORK_ERROR"     # request raised (timeout, connection, …)


@dataclass(frozen=True)
class TransportResult:
    """Explicit, safe-to-log outcome of one Telegram API call.

    Never carries the bot token, the token-bearing URL, or any secret. The
    Telegram `result` payload (when ok=true) is preserved for the caller.
    """

    kind: DeliveryKind
    method: str
    http_status: Optional[int] = None
    error_code: Optional[int] = None            # Telegram error_code (ok=false)
    description_safe: Optional[str] = None       # Telegram description, redacted
    result: Optional[Any] = None                 # Telegram "result" (ok=true only)

    @property
    def is_ack(self) -> bool:
        """A real new delivery acknowledgement (message sent/edited)."""
        return self.kind is DeliveryKind.ACK

    @property
    def is_delivered(self) -> bool:
        """The intended content is present on Telegram's side: either a fresh
        ACK, or NO_CHANGE (the target message already carries this exact
        content). Both mean the LIVE is up to date; only NO_CHANGE is not a
        *new* edit — see Q2.4 semantics."""
        return self.kind in (DeliveryKind.ACK, DeliveryKind.NO_CHANGE)

    @property
    def is_failure(self) -> bool:
        return self.kind in (
            DeliveryKind.TELEGRAM_ERROR,
            DeliveryKind.HTTP_ERROR,
            DeliveryKind.INVALID_RESPONSE,
            DeliveryKind.NETWORK_ERROR,
        )

    def summary_safe(self) -> str:
        bits = [self.method, self.kind.value]
        if self.http_status is not None:
            bits.append(f"http={self.http_status}")
        if self.error_code is not None:
            bits.append(f"tg={self.error_code}")
        if self.description_safe:
            bits.append(self.description_safe)
        return " ".join(bits)


def _redact_secrets(text: str) -> str:
    """Strip the bot token / token-bearing URL from any string before it can
    reach a log or a TransportResult. Defence in depth: exception strings from
    the HTTP layer can embed the request URL (which contains the token)."""
    safe = text
    if QC_BOT_TOKEN:
        safe = safe.replace(QC_BOT_TOKEN, "***")
    return safe.replace(_API_BASE, "https://api.telegram.org/bot***")


def _is_no_change(
    method: str,
    http_status: int,
    error_code: int | None,
    description: str | None,
) -> bool:
    """Recognize Telegram's one legitimate already-current response.

    ``message is not modified`` is meaningful only for editMessageText and only
    with the exact HTTP/Telegram 400 error pair. Other methods or status/error
    combinations remain delivery failures even if their description contains
    the same words.
    """
    return (
        method == "editMessageText"
        and http_status == 400
        and error_code == 400
        and isinstance(description, str)
        and "message is not modified" in description.lower()
    )


def _post(method: str, *, timeout: int = _HTTP_TIMEOUT_S, **kwargs) -> TransportResult:
    """Perform one Telegram call and classify the outcome. Never raises; never
    logs the token or the token-bearing URL."""
    try:
        r = requests.post(f"{_API_BASE}/{method}", timeout=timeout, **kwargs)
    except Exception as e:
        # Only the exception *type* — str(e) can embed the token-bearing URL.
        logger.error("Telegram %s network error: %s", method, type(e).__name__)
        return TransportResult(
            kind=DeliveryKind.NETWORK_ERROR,
            method=method,
            description_safe=type(e).__name__,
        )

    status = r.status_code
    try:
        data = r.json()
    except Exception:
        data = None

    # Telegram returns a JSON envelope even on errors ({"ok": false, ...}).
    # An ok=false envelope is still useful for classifying the Telegram error,
    # including the one strict NO_CHANGE exception below.
    if isinstance(data, dict) and data.get("ok") is False:
        description = data.get("description")
        desc_safe = _redact_secrets(str(description)) if description is not None else None
        error_code = data.get("error_code")
        error_code = int(error_code) if isinstance(error_code, int) else None
        kind = (
            DeliveryKind.NO_CHANGE
            if _is_no_change(method, status, error_code, description)
            else DeliveryKind.TELEGRAM_ERROR
        )
        return TransportResult(
            kind=kind,
            method=method,
            http_status=status,
            error_code=error_code,
            description_safe=desc_safe,
        )

    # HTTP transport success is a prerequisite for ACK. Even a contradictory
    # non-2xx {"ok": true} envelope must never be accepted as delivered.
    if not (200 <= status < 300):
        return TransportResult(
            kind=DeliveryKind.HTTP_ERROR, method=method, http_status=status
        )

    if isinstance(data, dict) and data.get("ok") is True:
        return TransportResult(
            kind=DeliveryKind.ACK,
            method=method,
            http_status=status,
            result=data.get("result"),
        )

    # 2xx without an explicit Telegram {"ok": true/false} envelope.
    return TransportResult(
        kind=DeliveryKind.INVALID_RESPONSE, method=method, http_status=status
    )


def send_photo(chat_id: str, png_bytes: bytes, caption: str = "") -> TransportResult:
    return _post(
        "sendPhoto",
        files={"photo": ("chart.png", io.BytesIO(png_bytes), "image/png")},
        data={"chat_id": chat_id, "caption": caption},
    )


def send_message(chat_id: str, text: str, parse_mode: str = "HTML") -> TransportResult:
    return _post(
        "sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    )


def edit_message(chat_id: str, message_id: str, text: str) -> TransportResult:
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
    # getUpdates long-polls for QC_LONGPOLL_S; the HTTP timeout is deliberately
    # larger (see module constants) so an idle long-poll is not aborted as a
    # network error. This larger timeout is scoped to getUpdates ONLY.
    result = _post(
        "getUpdates",
        timeout=_GETUPDATES_HTTP_TIMEOUT_S,
        json={"timeout": QC_LONGPOLL_S, "offset": offset},
    )
    if result.is_ack and isinstance(result.result, list):
        return result.result
    return []


# ── Delivery state (Q2.5 — in-memory only; no DB, no runtime file) ─────────────
#
# The Telegram engine knows, by itself, whether its last delivery succeeded.
# Pure observability of the transport layer — no burn-in, no persistence.


@dataclass
class DeliveryState:
    """In-memory delivery evidence with ACK and already-current kept distinct."""

    last_attempt_ts: Optional[float] = None
    last_ack_ts: Optional[float] = None
    last_confirmed_current_ts: float | None = None
    last_failure_ts: Optional[float] = None
    last_failure_kind: Optional[str] = None
    last_failure_description_safe: Optional[str] = None

    def record(self, result: TransportResult, now: float) -> TransportResult:
        self.last_attempt_ts = now
        if result.is_ack:
            # Only a fresh Telegram {"ok": true} delivery is a real ACK.
            self.last_ack_ts = now
        if result.is_delivered:
            # ACK and NO_CHANGE both prove the intended content is current.
            self.last_confirmed_current_ts = now
        else:
            self.last_failure_ts = now
            self.last_failure_kind = result.kind.value
            self.last_failure_description_safe = result.description_safe
        return result


# Module-level singleton — the Quant Observer's own delivery memory.
_QC_DELIVERY = DeliveryState()


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
    return render_quant_live_panel(_load_quant_live_snapshot())


def _load_quant_live_snapshot():
    from visualization.api import load_quant_live_snapshot

    return load_quant_live_snapshot()


# ── Change-driven pinned LIVE (Q3 — in-memory only) ───────────────────────────


@dataclass
class ChangeDrivenLiveState:
    """Evidence for the last semantic LIVE state confirmed by Telegram."""

    confirmed_fingerprint: str | None = None
    last_inspection_ts: float | None = None
    last_delivery_attempt_ts: float | None = None
    last_confirmed_ts: float | None = None
    last_delivery_failed: bool = False


_QC_LIVE_STATE = ChangeDrivenLiveState()


def _quantize_rendered_number(value: Any, format_spec: str) -> Any:
    """Return the visible numeric value, tagging non-finite states explicitly."""
    rendered = format(value, format_spec)
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return ["nonfinite", "nan"]
        return ["nonfinite", "+inf" if value > 0 else "-inf"]
    return rendered


def _quant_live_semantic_projection(snap) -> dict[str, Any]:
    """Canonical Q1 scientific content, excluding display-only clock fields.

    Mapping keys are sorted explicitly. Pipeline and trace collections retain
    producer order because stage/causal order is itself meaningful; only the
    fields rendered by Q1 are projected, so hidden metadata cannot trigger an
    edit.
    """
    refusal_breakdown = {
        str(key): value
        for key, value in sorted(
            snap.refusal_breakdown.items(), key=lambda item: str(item[0])
        )
    }
    pipeline_stages = [
        {
            "name": stage.get("name", ""),
            "status": stage.get("status", ""),
            "message": stage.get("message", ""),
        }
        for stage in snap.pipeline_stages
    ]
    decision_trace = [
        {
            "node": node.get("node", ""),
            "decision": node.get("decision", ""),
            "score": node.get("score"),
            "reason_code": node.get("reason_code", ""),
        }
        for node in snap.decision_trace
    ]
    return {
        "health_market": snap.health_market,
        "health_api": snap.health_api,
        "regime": snap.regime,
        # Keep the fingerprint aligned with the visible Q1 representation.
        # This also turns NaN/Inf into stable, immediately deliverable text.
        "exchange_latency_ms": _quantize_rendered_number(
            snap.exchange_latency_ms, ".0f"
        ),
        "exchange_uptime_pct": _quantize_rendered_number(
            snap.exchange_uptime_pct, ".0f"
        ),
        "state": snap.state,
        "top_candidate_symbol": snap.top_candidate_symbol,
        "top_candidate_score": snap.top_candidate_score,
        "required_score": snap.required_score,
        "mean_signal_score": snap.mean_signal_score,
        "reason_text": snap.reason_text,
        "gate_reason": snap.gate_reason,
        "refusal_breakdown": refusal_breakdown,
        "total_refusals": snap.total_refusals,
        "dominant_filter": snap.dominant_filter,
        "dominant_filter_pct": snap.dominant_filter_pct,
        "pipeline_stages": pipeline_stages,
        "decision_trace": decision_trace,
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _canonicalize_fingerprint_value(value: Any) -> Any:
    """Normalize supported semantic values into a deterministic JSON tree.

    Numeric values share one domain (1 == 1.0, including signed zero), while
    booleans retain their own type. Non-finite floats use explicit stable tags
    so an anomalous state remains fingerprintable and visible. Mapping order is
    normalized, while list/tuple order remains semantically significant.
    """
    if value is None:
        return ["none"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["number", value]
    if isinstance(value, float):
        if not math.isfinite(value):
            if math.isnan(value):
                return ["nonfinite", "nan"]
            return ["nonfinite", "+inf" if value > 0 else "-inf"]
        if value == 0.0:
            normalized: int | float = 0
        elif value.is_integer():
            normalized = int(value)
        else:
            normalized = value
        return ["number", normalized]
    if isinstance(value, str):
        return ["string", value]
    if isinstance(value, Mapping):
        entries = [
            [
                _canonicalize_fingerprint_value(key),
                _canonicalize_fingerprint_value(item),
            ]
            for key, item in value.items()
        ]
        entries.sort(key=lambda entry: _canonical_json(entry[0]))
        return ["mapping", entries]
    if isinstance(value, (list, tuple)):
        return [
            "sequence",
            [_canonicalize_fingerprint_value(item) for item in value],
        ]
    raise TypeError(f"unsupported fingerprint value type: {type(value).__name__}")


def _quant_live_fingerprint(snap) -> str:
    canonical_projection = _canonicalize_fingerprint_value(
        _quant_live_semantic_projection(snap)
    )
    canonical = _canonical_json(canonical_projection)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _change_driven_live_tick(now: float, last_pinned_update: float) -> float:
    """Inspect LIVE state and edit only on semantic change or safety refresh.

    ACK and NO_CHANGE confirm the candidate fingerprint. Every Q2 failure keeps
    the preceding fingerprint, making an identical subsequent state retryable.
    """
    if not QC_PINNED_MSG:
        return last_pinned_update

    try:
        snap = _load_quant_live_snapshot()
        fingerprint = _quant_live_fingerprint(snap)
    except Exception as e:  # noqa: BLE001 — keep the polling observer alive
        logger.warning("Pinned inspection failed: %s", type(e).__name__)
        return last_pinned_update

    _QC_LIVE_STATE.last_inspection_ts = now
    safety_refresh_due = (
        _QC_LIVE_STATE.confirmed_fingerprint is not None
        and (
            _QC_LIVE_STATE.last_confirmed_ts is None
            or (now - _QC_LIVE_STATE.last_confirmed_ts) >= QC_SAFETY_REFRESH_S
        )
    )
    if (
        fingerprint == _QC_LIVE_STATE.confirmed_fingerprint
        and not safety_refresh_due
    ):
        return last_pinned_update

    retry_floor_active = (
        _QC_LIVE_STATE.last_delivery_failed
        and _QC_LIVE_STATE.last_delivery_attempt_ts is not None
        and (now - _QC_LIVE_STATE.last_delivery_attempt_ts) < QC_LIVE_RETRY_S
    )
    if retry_floor_active:
        return last_pinned_update

    try:
        text = render_quant_live_panel(snap)
    except Exception as e:  # noqa: BLE001 — keep the polling observer alive
        logger.warning("Pinned render failed: %s", type(e).__name__)
        return last_pinned_update

    _QC_LIVE_STATE.last_delivery_attempt_ts = now
    result = _QC_DELIVERY.record(
        edit_message(QC_CHAT_ID, QC_PINNED_MSG, text), now
    )
    _QC_LIVE_STATE.last_delivery_failed = result.is_failure
    if result.is_delivered:
        _QC_LIVE_STATE.confirmed_fingerprint = fingerprint
        _QC_LIVE_STATE.last_confirmed_ts = now
        return now

    logger.warning("Pinned update not delivered: %s", result.summary_safe())
    return last_pinned_update


def _pinned_tick(now: float, last_pinned_update: float) -> float:
    """One pinned-LIVE update tick (TG-QC-001).

    Returns the possibly-updated ``last_pinned_update``. The timer is advanced
    ONLY on a real delivery (ACK, or NO_CHANGE = already current); a failed edit
    leaves it untouched so the loop retries instead of silently moving on.
    """
    if not QC_PINNED_MSG:
        return last_pinned_update
    if (now - last_pinned_update) < PINNED_UPDATE_S:
        return last_pinned_update
    try:
        text = _build_pinned_text()
    except Exception as e:
        logger.warning("Pinned render failed: %s", type(e).__name__)
        return last_pinned_update
    result = _QC_DELIVERY.record(edit_message(QC_CHAT_ID, QC_PINNED_MSG, text), now)
    if result.is_delivered:
        return now
    logger.warning("Pinned update not delivered: %s", result.summary_safe())
    return last_pinned_update


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
            # Inspect each poll; edit only after semantic change or safety refresh.
            # Q2 ACK/NO_CHANGE alone can confirm the candidate fingerprint.
            now = time.time()
            last_pinned_update = _change_driven_live_tick(now, last_pinned_update)

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
