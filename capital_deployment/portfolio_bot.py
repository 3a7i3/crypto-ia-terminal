"""
capital_deployment/portfolio_bot.py — Bot Telegram Portefeuille (Read-Only)

Bot dédié à la surveillance du portefeuille en production.
Répond aux commandes, envoie des rapports automatiques toutes les heures.

Commandes :
  /status   — Phase + KPIs (WR, Sharpe, DD) + résumé
  /balance  — Soldes de tous les comptes
  /positions — Positions ouvertes
  /pnl      — PnL détaillé (jour / total)
  /phase    — Infos phase F-01→F-05 + temps restant

Sécurité :
  - Répond uniquement au chat_id configuré
  - Thread daemon (ne bloque pas l'arrêt)
  - Read-only : ne peut pas envoyer d'ordres ni stopper le système
    (le KillSwitch reste sur l'autre bot)

Env vars :
  P10_PORTFOLIO_BOT_TOKEN  — token du nouveau bot @BotFather
  P10_PORTFOLIO_CHAT_ID    — ton chat_id (même que TELEGRAM_CHAT_ID si absent)
  P10_PORTFOLIO_REPORT_H   — intervalle rapport auto en heures (défaut 1)
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("capital_deployment.portfolio_bot")

_POLL_TIMEOUT = 30  # long-polling Telegram (secondes)
_RETRY_DELAY = 5.0  # pause si erreur réseau
_MAX_MSG_LEN = 4000  # limite Telegram

# ── Data provider ─────────────────────────────────────────────────────────────


@dataclass
class BotDataProvider:
    """
    Callbacks appelés à chaque commande.
    Chaque callable retourne None si la donnée n'est pas disponible.

    Wiring dans advisor_loop.py :
        provider = BotDataProvider(
            get_kpis      = lambda: _p10_kpi.snapshot() if _p10_kpi else None,
            get_balances  = lambda: {"spot": real_capital, "futures": futures_bal},
            get_positions = lambda: pos_manager.get_open_positions() if pos_manager else [],
            get_phase     = lambda: _P10_PHASE,
            get_throttle  = lambda: _p10_throttle,
        )
    """

    get_kpis: Optional[Callable[[], Any]] = None
    get_balances: Optional[Callable[[], Any]] = None
    get_positions: Optional[Callable[[], Any]] = None
    get_phase: Optional[Callable[[], Any]] = None
    get_throttle: Optional[Callable[[], Any]] = None


# ── Formatteurs ───────────────────────────────────────────────────────────────


def _check(value: float, threshold: float, low_is_good: bool = False) -> str:
    ok = (value <= threshold) if low_is_good else (value >= threshold)
    return "✅" if ok else "❌"


def _fmt_status(provider: BotDataProvider) -> str:
    lines = ["📊 *PHASE STATUS*"]

    phase = provider.get_phase() if provider.get_phase else "?"
    throttle = provider.get_throttle() if provider.get_throttle else None
    kpis = provider.get_kpis() if provider.get_kpis else None

    # Phase + capital alloué
    if throttle is not None:
        alloc = throttle.allocated_capital
        elapsed = throttle.allocation().days_elapsed()
        min_days = throttle.allocation().min_duration_days
        lines.append(f"Phase: *{phase}*  |  Alloué: *{alloc:.2f} USD*")
        lines.append(f"Durée: *{elapsed:.1f}j* / {min_days}j requis")
    else:
        lines.append(f"Phase: *{phase}*")

    lines.append("")

    # KPIs
    if kpis is not None:
        from capital_deployment.phase_kpi_tracker import PHASE_CRITERIA

        crit = PHASE_CRITERIA.get(phase, {})

        wr_thr = crit.get("min_win_rate", 0.45)
        sh_thr = crit.get("min_sharpe", 1.0)
        dd_thr = crit.get("max_drawdown", 0.02)

        wr_icon = _check(kpis.win_rate, wr_thr)
        sh_icon = _check(kpis.sharpe, sh_thr)
        dd_icon = _check(kpis.max_drawdown, dd_thr, low_is_good=True)

        lines.append("📈 *KPIs*")
        lines.append(
            f"Win Rate:  *{kpis.win_rate:.1%}* {wr_icon}  (seuil {wr_thr:.0%})"
        )
        lines.append(f"Sharpe:    *{kpis.sharpe:.2f}* {sh_icon}  (seuil {sh_thr})")
        lines.append(
            f"Max DD:    *{kpis.max_drawdown:.2%}* {dd_icon}  (seuil {dd_thr:.0%})"
        )
        lines.append(f"Trades:    {kpis.total_trades}")

        if kpis.unsigned_decisions > 0:
            lines.append(f"⚠️ Décisions non signées: {kpis.unsigned_decisions}")
    else:
        lines.append("_KPIs non disponibles_")

    return "\n".join(lines)


def _fmt_balance(provider: BotDataProvider) -> str:
    lines = ["💰 *SOLDES*"]
    balances = provider.get_balances() if provider.get_balances else None

    if not balances:
        lines.append("_Soldes non disponibles_")
        return "\n".join(lines)

    total = 0.0
    for account, amount in balances.items():
        if amount is None:
            continue
        try:
            v = float(amount)
        except (TypeError, ValueError):
            continue
        total += v
        lines.append(f"{account.capitalize()}: *{v:.2f} USD*")

    lines.append(f"\nTotal: *{total:.2f} USD*")
    return "\n".join(lines)


def _fmt_positions(provider: BotDataProvider) -> str:
    lines = ["📋 *POSITIONS OUVERTES*"]
    positions = provider.get_positions() if provider.get_positions else None

    if positions is None:
        lines.append("_Positions non disponibles_")
        return "\n".join(lines)

    if not positions:
        lines.append("_Aucune position ouverte_")
        return "\n".join(lines)

    lines.append(f"Total: {len(positions)} position(s)\n")
    for pos in positions:
        try:
            sym = pos.get("symbol", "?")
            side = pos.get("side", "?").upper()
            size = float(pos.get("size_usd", pos.get("capital", 0)))
            pnl = float(pos.get("unrealized_pnl", pos.get("pnl", 0)))
            pnl_pct = float(pos.get("pnl_pct", 0))
            icon = "🟢" if pnl >= 0 else "🔴"
            sign = "+" if pnl >= 0 else ""
            lines.append(
                f"{icon} {sym} {side}  {size:.2f}$  "
                f"{sign}{pnl:.2f}$ ({sign}{pnl_pct:.1f}%)"
            )
        except Exception:
            lines.append(f"• {pos}")

    return "\n".join(lines)


def _fmt_pnl(provider: BotDataProvider) -> str:
    lines = ["💹 *PnL DÉTAILLÉ*"]
    kpis = provider.get_kpis() if provider.get_kpis else None
    balances = provider.get_balances() if provider.get_balances else None

    if kpis is not None:
        lines.append(f"Trades:     {kpis.total_trades}")
        lines.append(f"Win rate:   {kpis.win_rate:.1%}")
        lines.append(f"Drawdown:   {kpis.max_drawdown:.2%}")
        lines.append(f"DD courant: {kpis.current_drawdown:.2%}")

    if balances is not None:
        total = sum(float(v) for v in balances.values() if v is not None)
        lines.append(f"Capital:    {total:.2f} USD")

    if kpis is None and balances is None:
        lines.append("_Données non disponibles_")

    return "\n".join(lines)


def _fmt_phase(provider: BotDataProvider) -> str:
    from capital_deployment.capital_throttle import PHASE_CONFIGS, PHASE_ORDER
    from capital_deployment.phase_kpi_tracker import PHASE_CRITERIA

    phase = provider.get_phase() if provider.get_phase else "F-01"
    throttle = provider.get_throttle() if provider.get_throttle else None

    lines = [f"🏷️ *PHASE {phase}*\n"]

    cfg = PHASE_CONFIGS.get(phase, {})
    crit = PHASE_CRITERIA.get(phase, {})
    lines.append(
        f"Capital alloué: *{cfg.get('capital_pct', 0)*100:.0f}%*"
        + (
            f" / max {cfg['max_capital_eur']:.0f} EUR"
            if cfg.get("max_capital_eur")
            else ""
        )
    )
    lines.append(f"Durée minimale: *{crit.get('min_duration_days', 0)} jours*")
    lines.append("")
    lines.append("*Critères de validation :*")
    lines.append(f"  Win Rate > {crit.get('min_win_rate', 0):.0%}")
    lines.append(f"  Sharpe   > {crit.get('min_sharpe', 0)}")
    lines.append(f"  Max DD   < {crit.get('max_drawdown', 0):.0%}")

    if throttle is not None:
        elapsed = throttle.allocation().days_elapsed()
        remaining = throttle.allocation().min_duration_days - elapsed
        lines.append(f"\nTemps écoulé:  *{elapsed:.1f}j*")
        if remaining > 0:
            lines.append(f"Temps restant: *{remaining:.1f}j*")
        else:
            lines.append("Durée minimum: ✅ *atteinte*")

    # Prochaine phase
    idx = PHASE_ORDER.index(phase) if phase in PHASE_ORDER else -1
    if 0 <= idx < len(PHASE_ORDER) - 1:
        next_p = PHASE_ORDER[idx + 1]
        next_crit = PHASE_CRITERIA.get(next_p, {})
        lines.append(f"\n➡️ Phase suivante: *{next_p}*")
        lines.append(
            f"   Capital: {PHASE_CONFIGS[next_p]['capital_pct']*100:.0f}%  "
            f"Sharpe > {next_crit.get('min_sharpe', '?')}  "
            f"DD < {next_crit.get('max_drawdown', 0)*100:.0f}%"
        )

    return "\n".join(lines)


# ── Bot principal ──────────────────────────────────────────────────────────────

_COMMANDS = {
    "/status": ("📊 Phase + KPIs", _fmt_status),
    "/balance": ("💰 Soldes comptes", _fmt_balance),
    "/positions": ("📋 Positions ouvertes", _fmt_positions),
    "/pnl": ("💹 PnL détaillé", _fmt_pnl),
    "/phase": ("🏷️ Info phase F-xx", _fmt_phase),
}


class PortfolioBot:
    """
    Bot Telegram read-only pour surveillance portefeuille.

    Usage dans advisor_loop.py :
        provider = BotDataProvider(
            get_kpis      = lambda: _p10_kpi.snapshot() if _p10_kpi else None,
            get_balances  = lambda: {"spot": real_capital, "futures": futures_bal},
            get_positions = lambda: pos_manager.get_open_positions(),
            get_phase     = lambda: _P10_PHASE,
            get_throttle  = lambda: _p10_throttle,
        )
        bot = PortfolioBot.from_env(provider)
        bot.start()
    """

    def __init__(
        self,
        token: str,
        chat_id: str,
        provider: BotDataProvider,
        report_interval_h: float = 1.0,
    ) -> None:
        self._token = token
        self._chat_id = str(chat_id)
        self._provider = provider
        self._report_interval = report_interval_h * 3600.0
        self._running = False
        self._update_id = 0
        self._poll_thread: Optional[threading.Thread] = None
        self._report_thread: Optional[threading.Thread] = None
        self._last_report = 0.0

    @classmethod
    def from_env(cls, provider: BotDataProvider) -> "PortfolioBot":
        import os

        token = os.getenv("P10_PORTFOLIO_BOT_TOKEN", "")
        chat_id = os.getenv(
            "P10_PORTFOLIO_CHAT_ID",
            os.getenv("TELEGRAM_CHAT_ID", ""),
        )
        report_h = float(os.getenv("P10_PORTFOLIO_REPORT_H", "1.0"))
        return cls(
            token=token, chat_id=chat_id, provider=provider, report_interval_h=report_h
        )

    def start(self) -> None:
        if not self._token:
            _log.warning(
                "[PortfolioBot] P10_PORTFOLIO_BOT_TOKEN non configuré — bot désactivé"
            )
            return
        self._running = True

        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="PortfolioBot-Poll"
        )
        self._poll_thread.start()

        self._report_thread = threading.Thread(
            target=self._report_loop, daemon=True, name="PortfolioBot-Report"
        )
        self._report_thread.start()

        _log.info(
            "[PortfolioBot] Démarré — rapport toutes les %.1fh",
            self._report_interval / 3600,
        )
        self.send("🤖 *Portfolio Bot démarré*\nTape /status pour un résumé.")

    def stop(self) -> None:
        self._running = False

    def send(self, text: str) -> bool:
        if not self._token or not self._chat_id:
            return False
        try:
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            payload = json.dumps(
                {
                    "chat_id": self._chat_id,
                    "text": text[:_MAX_MSG_LEN],
                    "parse_mode": "Markdown",
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as exc:
            _log.debug("[PortfolioBot] send error: %s", exc)
            return False

    # ── Polling ────────────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        _log.info("[PortfolioBot] Polling démarré")
        while self._running:
            try:
                updates = self._get_updates()
                for upd in updates:
                    self._update_id = max(self._update_id, upd["update_id"] + 1)
                    msg = upd.get("message", {})
                    if msg:
                        self._handle(msg)
            except Exception as exc:
                _log.debug("[PortfolioBot] poll error: %s", exc)
                time.sleep(_RETRY_DELAY)

    def _get_updates(self) -> list[dict]:
        url = (
            f"https://api.telegram.org/bot{self._token}/getUpdates"
            f"?offset={self._update_id}&timeout={_POLL_TIMEOUT}"
        )
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=_POLL_TIMEOUT + 5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("result", [])

    def _handle(self, msg: dict) -> None:
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip().lower().split()[0]  # première mot

        # Sécurité : ignorer les messages d'autres chats
        if chat_id != self._chat_id:
            _log.warning(
                "[PortfolioBot] Message ignoré de chat_id=%s (attendu %s)",
                chat_id,
                self._chat_id,
            )
            return

        if text == "/start" or text == "/help":
            lines = ["🤖 *Portfolio Bot — Commandes*\n"]
            for cmd, (desc, _) in _COMMANDS.items():
                lines.append(f"{cmd} — {desc}")
            self.send("\n".join(lines))
            return

        if text in _COMMANDS:
            _, fmt_fn = _COMMANDS[text]
            try:
                reply = fmt_fn(self._provider)
                self.send(reply)
            except Exception as exc:
                _log.error("[PortfolioBot] Erreur commande %s: %s", text, exc)
                self.send(f"⚠️ Erreur: {exc}")
        elif text.startswith("/"):
            self.send(f"Commande inconnue: `{text}`\nTape /help pour la liste.")

    # ── Rapport automatique horaire ────────────────────────────────────────────

    def _report_loop(self) -> None:
        while self._running:
            time.sleep(60)
            if not self._running:
                break
            if time.time() - self._last_report >= self._report_interval:
                try:
                    report = _fmt_status(self._provider)
                    self.send(f"⏰ *Rapport automatique*\n\n{report}")
                    self._last_report = time.time()
                except Exception as exc:
                    _log.debug("[PortfolioBot] auto-report error: %s", exc)
