"""
chief_officer.py — AI Chief Officer

Le copilote IA. Il ne trade pas. Il observe tout et parle.

Il synthetise en temps reel :
  - Etat du portefeuille
  - Etat du bot (derive, niveau override)
  - Performances recentes
  - Tendance du marche
  - Risques detectes
  - Recommandations concretes

Et produit un briefing lisible pour le pilote humain.

Exemple de message :
  "Depuis 6h, performance se degrade sur ETH.
   Regime sideways depuis 3 cycles.
   Strategie momentum perd sa validite (WR 38%).
   ConvictionEngine a refuse 4 trades - 2 etaient rentables.
   Executive Override : REDUCE (streak=3).
   Recommandation : passer en safe mode 1h,
   attendre confirmation bull_trend."

Il parle :
  - A chaque N cycles (rapport de synthese)
  - Sur evenement important (niveau override monte)
  - Sur demande

Utilise LM Studio local si disponible, sinon analyse deterministe.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.chief_officer")
_BRIEF_EVERY = int(os.getenv("COO_BRIEF_EVERY", "6"))  # cycles entre briefings
_LM_SYSTEM_PROMPT = (
    "Tu es le Chief Officer d'un systeme de trading crypto algorithmique. "
    "Tu fournis des briefings courts, factuels, actionnables, sans markdown."
)


class ChiefOfficer:
    """
    Copilote IA de supervision. Synthetise l'etat du systeme et conseille.

    Usage :
        coo = ChiefOfficer()
        briefing = coo.briefing(
            cycle           = cycle,
            symbols         = ["BTC/USDT", "ETH/USDT"],
            results         = results,
            pos_manager     = pos_manager,
            awareness_state = awareness_state,
            override        = executive_override,
            regret_engine   = regret_engine,
            mistake_memory  = mistake_memory,
            ranker          = ranker,
            meta_engine     = meta_engine,
        )
        if briefing:
            _telegram(briefing)
    """

    def __init__(self) -> None:
        self._last_brief_ts = 0.0
        self._last_brief_cycle = 0
        self._lm_available: Optional[bool] = None
        self._regime_history: list[str] = []

    # ── Briefing principal ────────────────────────────────────────────────────

    def briefing(
        self,
        cycle: int,
        symbols: list,
        results: list,
        pos_manager=None,
        awareness_state=None,
        override=None,
        regret_engine=None,
        mistake_memory=None,
        ranker=None,
        meta_engine=None,
        black_box=None,
        activity_tracker=None,
        stability_monitor=None,
        force: bool = False,
    ) -> Optional[str]:
        """
        Genere un briefing si le moment est venu (tous les N cycles).
        Retourne None si pas encore l'heure.
        """
        if not force and cycle - self._last_brief_cycle < _BRIEF_EVERY:
            return None

        self._last_brief_cycle = cycle
        self._last_brief_ts = time.time()

        context = self._build_context(
            cycle,
            symbols,
            results,
            pos_manager,
            awareness_state,
            override,
            regret_engine,
            mistake_memory,
            ranker,
            meta_engine,
            black_box,
            activity_tracker,
            stability_monitor,
        )

        # Essayer LM Studio d'abord
        if self._lm_available is not False:
            text = self._lm_analysis(context)
            if text:
                return f"AI CHIEF OFFICER — Cycle {cycle}\n\n{text}"
            self._lm_available = False

        # Fallback : analyse deterministe
        return self._deterministic_analysis(context, cycle)

    def quick_alert(
        self,
        event: str,
        context: dict,
        cycle: int = 0,
    ) -> str:
        """
        Alerte rapide sur un evenement specifique.
        Toujours genere un message (pas de throttle).
        """
        ctx = self._format_context_short(context)
        if self._lm_available is not False:
            prompt = (
                f"Tu es un Chief Officer d'un systeme de trading crypto. "
                f"En 2-3 phrases concises (sans markdown), analyse cet evenement : "
                f"'{event}'. Contexte : {ctx}. "
                f"Donne une recommandation concrete et actionnable."
            )
            text = self._lm_call(prompt, max_tokens=150)
            if text:
                return f"COO ALERTE: {text}"

        return self._quick_deterministic(event, context)

    # ── Construction du contexte ──────────────────────────────────────────────

    def _build_context(
        self,
        cycle,
        symbols,
        results,
        pos_manager,
        awareness_state,
        override,
        regret_engine,
        mistake_memory,
        ranker,
        meta_engine,
        black_box,
        activity_tracker=None,
        stability_monitor=None,
    ) -> dict:
        ctx: dict = {"cycle": cycle, "symbols": symbols}

        # Signaux courants
        ctx["signals"] = [
            {
                "symbol": r.get("symbol"),
                "signal": r.get("signal").signal if r.get("signal") else "?",
                "score": r.get("signal").score if r.get("signal") else 0,
                "regime": r.get("regime", "unknown"),
                "allowed": r.get("trade_allowed", False),
            }
            for r in results
        ]

        # Positions
        if pos_manager:
            try:
                stats = pos_manager.stats()
                ctx["positions"] = {
                    "open": stats.get("open_count", 0),
                    "pnl_open": round(stats.get("open_pnl_usd", 0.0), 2),
                    "pnl_total": round(stats.get("total_pnl_usd", 0.0), 2),
                    "win_rate": round(stats.get("win_rate", 0.0), 3),
                    "closed": stats.get("closed_count", 0),
                }
            except Exception:
                ctx["positions"] = {}

        # Self-Awareness
        if awareness_state:
            ctx["awareness"] = {
                "level": (
                    awareness_state.level.name
                    if hasattr(awareness_state, "level")
                    else "?"
                ),
                "size_factor": getattr(awareness_state, "size_factor", 1.0),
                "safe_mode": getattr(awareness_state, "safe_mode", False),
                "drifts": [
                    d.message for d in getattr(awareness_state, "active_drifts", [])[:3]
                ],
            }

        # Executive Override
        if override:
            snap = override.metrics_snapshot()
            ctx["override"] = snap

        # Regret Engine
        if regret_engine:
            ctx["regret"] = regret_engine.stats()
            ctx["regret_hints"] = regret_engine.calibration_hints()[:3]

        # Mistake Memory
        if mistake_memory:
            mm_stats = mistake_memory.stats()
            ctx["mistakes"] = {
                "total": mm_stats.get("total", 0),
                "error_rate": mm_stats.get("error_rate", 0.0),
                "rules_active": mm_stats.get("rules_active", 0),
                "recent": mistake_memory.explain_last_mistakes(2),
            }

        # Ranker — top strategie
        if ranker:
            try:
                top = ranker.leaderboard(3)
                ctx["top_strategies"] = top
            except Exception:
                pass

        # Meta personality
        if meta_engine:
            p = meta_engine.current_personality()
            if p:
                ctx["personality"] = {
                    "name": p.name,
                    "tp_pct": p.tp_pct,
                    "sl_pct": p.sl_pct,
                }

        # Black Box — derniers evenements
        if black_box:
            ctx["bb_recent"] = black_box.last_n_summary(5)
            ctx["bb_stats"] = black_box.stats()

        # Activity Tracker — inactivité du capital
        if activity_tracker is not None:
            try:
                ctx["activity"] = activity_tracker.report()
            except Exception:
                pass

        # Behavioral Stability Monitor — derives systemiques
        if stability_monitor is not None:
            try:
                ctx["stability"] = stability_monitor.report()
            except Exception:
                pass

        return ctx

    # ── Analyse LM Studio ─────────────────────────────────────────────────────

    def _lm_analysis(self, ctx: dict) -> Optional[str]:
        ctx_str = self._format_context_short(ctx)
        prompt = (
            "Tu es le Chief Officer d'un systeme de trading crypto algorithmique. "
            "Analyse l'etat ci-dessous et produis un briefing de 4-6 phrases maximum. "
            "Sois direct, factuel, actionnable. Pas de markdown. "
            "Identifie : 1) La situation principale, "
            "2) Le risque principal, "
            "3) Une recommandation concrete.\n\n"
            f"ETAT SYSTEME:\n{ctx_str}"
        )
        return self._lm_call(prompt, max_tokens=250)

    def _lm_call(self, prompt: str, max_tokens: int = 200) -> Optional[str]:
        try:
            from lm_studio import client as lm_client

            text = lm_client.chat(
                prompt,
                system=_LM_SYSTEM_PROMPT,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            self._lm_available = True
            return text.strip()
        except Exception as exc:
            _log.debug("[ChiefOfficer] LM Studio indisponible: %s", exc)
        return None

    # ── Analyse deterministe (fallback) ──────────────────────────────────────

    def _deterministic_analysis(self, ctx: dict, cycle: int) -> str:
        lines = [f"AI CHIEF OFFICER — Cycle {cycle}", ""]

        # Etat Override
        override = ctx.get("override", {})
        eo_level = override.get("level", "CLEAR")
        if eo_level != "CLEAR":
            dd = override.get("drawdown_pct", 0)
            streak = override.get("loss_streak", 0)
            lines.append(f"COMMANDEMENT: {eo_level}")
            if dd > 0:
                lines.append(f"  Drawdown: -{dd:.1f}%")
            if streak > 0:
                lines.append(f"  Pertes consecutives: {streak}")
            if eo_level in ("VETO", "MINIMAL"):
                lines.append("  ACTION: Aucun nouveau trade jusqu'a stabilisation.")
            lines.append("")

        # Signaux
        signals = ctx.get("signals", [])
        active = [s for s in signals if s["score"] >= 70]
        blocked = [s for s in signals if s["score"] >= 65 and not s["allowed"]]
        if active:
            lines.append("SIGNAUX ACTIFS:")
            for s in active:
                lines.append(
                    f"  {s['symbol']} {s['signal']} score={s['score']} "
                    f"regime={s['regime']} | {'OK' if s['allowed'] else 'BLOQUE'}"
                )
            lines.append("")
        if blocked:
            lines.append("SIGNAUX BLOQUES:")
            for s in blocked:
                lines.append(f"  {s['symbol']} {s['signal']} score={s['score']}")
            lines.append("")

        # Positions
        pos = ctx.get("positions", {})
        if pos:
            pnl_total = pos.get("pnl_total", 0)
            wr = pos.get("win_rate", 0)
            lines.append(
                f"PORTEFEUILLE: {pos.get('open',0)} ouvertes | "
                f"PnL total: {pnl_total:+.2f}$ | WR: {wr:.0%}"
            )
            lines.append("")

        # Awareness
        aw = ctx.get("awareness", {})
        if aw and aw.get("level", "OK") != "OK":
            drifts = " | ".join(aw.get("drifts", [])[:2])
            lines.append(f"DERIVE DETECTEE: {aw['level']} | {drifts}")
            lines.append("")

        # Regrets
        regret = ctx.get("regret", {})
        missed = regret.get("missed_wins", 0)
        if missed > 0:
            accuracy = regret.get("refusal_accuracy", 0.0)
            lines.append(
                f"ANALYSE REGRETS: {missed} opportunites manquees | "
                f"Precision refus: {accuracy:.0%}"
            )
            hints = ctx.get("regret_hints", [])
            for h in hints[:2]:
                lines.append(f"  Calibration: {h['hint'][:80]}")
            lines.append("")

        # Mistakes
        mm = ctx.get("mistakes", {})
        if mm.get("rules_active", 0) > 0:
            lines.append(
                f"REGLES AUTO: {mm['rules_active']} actives | "
                f"Taux erreur: {mm.get('error_rate', 0):.0%}"
            )
            for err in mm.get("recent", [])[:1]:
                lines.append(f"  Derniere: {err[:80]}")
            lines.append("")

        # Activité du capital
        activity = ctx.get("activity", {})
        if activity:
            inactivity = activity.get("inactivity_ratio", 0.0)
            exec_ratio = activity.get("execution_ratio", 1.0)
            since = activity.get("cycles_since_last_trade", 0)
            alert = activity.get("alert_overfiltered", False)
            prefix = "ALERTE " if alert else ""
            lines.append(
                f"{prefix}CAPITAL: activite={1 - inactivity:.0%} | "
                f"exec={exec_ratio:.0%} | sans trade depuis {since} cycles"
            )
            lines.append("")

        # Stabilite comportementale
        stab = ctx.get("stability", {})
        if stab:
            state = stab.get("state", "stable")
            flips = stab.get("regime_flips_10c", 0)
            delta = stab.get("threshold_cumul_delta", 0)
            entropy = stab.get("portfolio_entropy", 1.0)
            violations = stab.get("violations", [])
            prefix = "ALERTE " if violations else ""
            lines.append(
                f"{prefix}STABILITE: etat={state} | "
                f"flips={flips}/10c | "
                f"delta={delta:+d} | "
                f"entropie={entropy:.2f}"
            )
            for v in violations[:2]:
                lines.append(f"  ! {v[:80]}")
            lines.append("")

        # Recommandation finale
        lines.append("RECOMMANDATION:")
        rec = self._recommend(ctx)
        lines.append(f"  {rec}")

        return "\n".join(lines)

    def _recommend(self, ctx: dict) -> str:
        override = ctx.get("override", {})
        eo_level = override.get("level", "CLEAR")
        aw = ctx.get("awareness", {})
        aw_level = aw.get("level", "OK")
        regret = ctx.get("regret", {})
        accuracy = regret.get("refusal_accuracy", 1.0)
        dd = override.get("drawdown_pct", 0)
        streak = override.get("loss_streak", 0)

        if eo_level == "VETO":
            return "HALTE COMPLETE. Attendre stabilisation. Ne pas ouvrir de positions."
        if eo_level == "MINIMAL":
            return (
                f"Mode survie actif (DD={dd:.1f}%). "
                "Taille minimum. Surveiller recovery."
            )
        if eo_level == "CAREFUL":
            return (
                f"Prudence maximale (streak={streak}). "
                "Taille x25%. Attendre signal exceptionnel."
            )
        if eo_level == "REDUCE":
            return f"Pression detectable. Taille x50%. Eviter les entrees marginales."
        if aw_level in ("DANGER", "CRITICAL"):
            return (
                "Derive comportementale critique. Reduire taille et surveiller regime."
            )
        stab = ctx.get("stability", {})
        stab_state = stab.get("state", "stable")
        if stab_state == "degraded":
            violations = stab.get("violations", [])
            v_str = " | ".join(violations[:2])
            return (
                f"SYSTEME DEGRADE — {len(violations)} invariante(s) violee(s): "
                f"{v_str[:80]}. Intervention manuelle requise."
            )
        if stab_state == "oscillating":
            return (
                f"Oscillation regimes detectee ({stab.get('regime_flips_10c', 0)} "
                f"flips/10c). Verifier stabilite donnees marche."
            )
        if stab_state == "drifting":
            return (
                f"Derive threshold: delta={stab.get('threshold_cumul_delta', 0):+d}. "
                "RegretEngine sur-corrige — verifier qualite des trades refuses."
            )
        activity = ctx.get("activity", {})
        if (
            activity.get("alert_overfiltered")
            and activity.get("cycles_since_last_trade", 0) >= 20
        ):
            return (
                f"Capital inactif depuis {activity['cycles_since_last_trade']} cycles "
                f"(activite={1 - activity.get('inactivity_ratio', 1):.0%}). "
                "Sur-filtrage probable — verifier seuils et conviction."
            )
        if accuracy < 0.5 and regret.get("missed_wins", 0) >= 3:
            return (
                "Trop de bons trades bloques. "
                "Envisager d'assouplir conviction/no-trade."
            )
        return "Systeme en ordre. Continuer selon les signaux habituels."

    def _quick_deterministic(self, event: str, ctx: dict) -> str:
        return (
            f"COO ALERTE: {event} | Contexte: {self._format_context_short(ctx)[:100]}"
        )

    @staticmethod
    def _format_context_short(ctx: dict) -> str:
        parts = []
        if "override" in ctx:
            o = ctx["override"]
            parts.append(
                f"Override={o.get('level','?')} DD={o.get('drawdown_pct',0):.1f}% "
                f"streak={o.get('loss_streak',0)}"
            )
        if "awareness" in ctx:
            parts.append(f"Awareness={ctx['awareness'].get('level','?')}")
        if "positions" in ctx:
            p = ctx["positions"]
            parts.append(f"Pos={p.get('open',0)} PnL={p.get('pnl_total',0):+.1f}$")
        if "signals" in ctx:
            sigs = [
                f"{s['symbol']}:{s['signal']}({s['score']})" for s in ctx["signals"][:3]
            ]
            parts.append(f"Signals={' '.join(sigs)}")
        return " | ".join(parts) if parts else str(ctx)[:200]
