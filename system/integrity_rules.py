"""
system/integrity_rules.py — Règles d'intégrité pures.

Chaque fonction est :
  - pure        : aucun effet de bord
  - deterministic : même entrée → même sortie
  - side-effect free : ne modifie rien

Pattern : check_*(snap) -> list[IntegrityIssue]

Règles organisées en 5 catégories :
  1. signal   — verrous stale, timestamps futurs, ghost locks
  2. position — cohérence comptage, sur-exposition
  3. capital  — capital fantôme, free > total, exposition fantôme
  4. temporal — cooldowns expirés, rate limit, dérive horloge
  5. order    — ordres pending sans position
"""

from __future__ import annotations

from system.integrity_models import IntegrityIssue, IntegritySeverity
from system.integrity_snapshot import StateSnapshot

_COOLDOWN_TTL = 300.0  # 5 min
_STALE_COOLDOWN_AGE = 3600.0  # > 1h = orphelin


def _iss(
    rule: str,
    severity: IntegritySeverity,
    description: str,
    invariant: str,
    observed: str,
    category: str,
) -> IntegrityIssue:
    return IntegrityIssue(
        rule=rule,
        severity=severity,
        description=description,
        invariant=invariant,
        observed=observed,
        category=category,
    )


# ── 1. Signal integrity ────────────────────────────────────────────────────────


def check_signal_integrity(snap: StateSnapshot) -> list[IntegrityIssue]:
    """
    Invariants vérifiés :
      - last_trade_signal[sym] seulement valide si position ouverte OU cooldown actif
      - last_loss_time[sym] ne peut pas être dans le futur
    """
    issues: list[IntegrityIssue] = []
    now = snap.captured_at
    open_symbols = {p["symbol"] for p in snap.open_positions_local}

    for sym, signal in snap.last_trade_signal.items():
        last_loss_ts = snap.last_loss_timestamps.get(sym, 0.0)
        cooldown_active = (now - last_loss_ts) < _COOLDOWN_TTL
        has_position = sym in open_symbols

        if not has_position and not cooldown_active:
            issues.append(
                _iss(
                    rule="signal.stale_lock",
                    severity=IntegritySeverity.WARNING,
                    description=(
                        f"{sym}: last_trade_signal={signal!r} persiste "
                        f"sans position ouverte ni cooldown actif"
                    ),
                    invariant=(
                        "last_trade_signal[sym] valide si position OU cooldown actif"
                    ),
                    observed=(
                        f"position={has_position}, "
                        f"cooldown_age={now - last_loss_ts:.0f}s > {_COOLDOWN_TTL:.0f}s"
                    ),
                    category="signal",
                )
            )

    for sym, ts in snap.last_loss_timestamps.items():
        if ts > now + 60:
            issues.append(
                _iss(
                    rule="signal.future_timestamp",
                    severity=IntegritySeverity.UNSAFE,
                    description=(
                        f"{sym}: last_loss_time est {ts - now:.0f}s dans le futur"
                        " — drift horloge ou corruption"
                    ),
                    invariant="last_loss_time[sym] <= now",
                    observed=f"last_loss_time={ts:.3f}, now={now:.3f}",
                    category="signal",
                )
            )

    return issues


# ── 2. Position integrity ──────────────────────────────────────────────────────


def check_position_integrity(snap: StateSnapshot) -> list[IntegrityIssue]:
    """
    Invariants vérifiés :
      - stats().open_count == len(snapshot())
      - portfolio_brain.n_positions ≈ pos_manager.open_count
      - sum(notional) <= real_capital (pas de sur-exposition totale)
    """
    issues: list[IntegrityIssue] = []

    local_count = snap.open_count_stats
    snapshot_count = len(snap.open_positions_local)
    pb_count = snap.portfolio_n_positions

    if local_count != snapshot_count:
        issues.append(
            _iss(
                rule="position.stats_snapshot_mismatch",
                severity=IntegritySeverity.DEGRADED,
                description="pos_manager.stats().open_count ≠ len(pos_manager.snapshot())",  # noqa: E501
                invariant="stats.open_count == len(snapshot())",
                observed=f"stats={local_count}, snapshot_len={snapshot_count}",
                category="position",
            )
        )

    if abs(pb_count - local_count) > 0:
        issues.append(
            _iss(
                rule="position.brain_manager_mismatch",
                severity=IntegritySeverity.WARNING,
                description="portfolio_brain.n_positions diverge de pos_manager.open_count",  # noqa: E501
                invariant="portfolio_brain.n_positions == pos_manager.open_count",
                observed=f"brain={pb_count}, manager={local_count}",
                category="position",
            )
        )

    total_notional = sum(p.get("size_usd", 0.0) for p in snap.open_positions_local)
    if total_notional > snap.real_capital * 1.01:
        issues.append(
            _iss(
                rule="position.over_exposed",
                severity=IntegritySeverity.UNSAFE,
                description="Notionnel total dépasse le capital total (sur-exposition)",
                invariant="sum(position_notional) <= real_capital",
                observed=f"notional={total_notional:.2f}$, capital={snap.real_capital:.2f}$",  # noqa: E501
                category="position",
            )
        )

    return issues


# ── 3. Capital integrity ───────────────────────────────────────────────────────


def check_capital_integrity(snap: StateSnapshot) -> list[IntegrityIssue]:
    """
    Invariants vérifiés :
      - real_capital > 0
      - portfolio_free_capital <= real_capital
      - exposure_pct ≈ 0 quand 0 positions (capital fantôme)
    """
    issues: list[IntegrityIssue] = []

    if snap.real_capital <= 0:
        issues.append(
            _iss(
                rule="capital.zero_or_negative",
                severity=IntegritySeverity.UNSAFE,
                description="real_capital est nul ou négatif — capital invalide",
                invariant="real_capital > 0",
                observed=f"real_capital={snap.real_capital:.2f}",
                category="capital",
            )
        )
        return issues

    if snap.portfolio_free_capital > snap.real_capital * 1.01:
        issues.append(
            _iss(
                rule="capital.free_exceeds_total",
                severity=IntegritySeverity.UNSAFE,
                description=(
                    "portfolio_brain.free_capital > real_capital"
                    " — capital fantôme détecté"
                ),
                invariant="free_capital <= real_capital",
                observed=(
                    f"free={snap.portfolio_free_capital:.2f}$, "
                    f"total={snap.real_capital:.2f}$"
                ),
                category="capital",
            )
        )

    if snap.open_count_stats == 0 and snap.portfolio_exposure_pct > 0.01:
        issues.append(
            _iss(
                rule="capital.ghost_exposure",
                severity=IntegritySeverity.DEGRADED,
                description=(
                    "portfolio_brain rapporte une exposition non nulle "
                    "avec 0 positions ouvertes"
                ),
                invariant="exposure_pct ≈ 0 quand open_positions == 0",
                observed=(
                    f"exposure={snap.portfolio_exposure_pct:.2%}, "
                    f"positions={snap.open_count_stats}"
                ),
                category="capital",
            )
        )

    return issues


# ── 4. Temporal integrity ──────────────────────────────────────────────────────


def check_temporal_integrity(snap: StateSnapshot) -> list[IntegrityIssue]:
    """
    Invariants vérifiés :
      - last_loss_time orphelins (TTL dépassé de très loin)
      - trades_this_hour atteignant la limite (opération dégradée)
    """
    issues: list[IntegrityIssue] = []
    now = snap.captured_at

    for sym, ts in snap.last_loss_timestamps.items():
        age = now - ts
        if age > _STALE_COOLDOWN_AGE:
            issues.append(
                _iss(
                    rule="temporal.stale_cooldown_entry",
                    severity=IntegritySeverity.WARNING,
                    description=(
                        f"{sym}: last_loss_time vieux de {age / 60:.0f}min"
                        f" (TTL={_COOLDOWN_TTL}s) — entrée orpheline"
                    ),
                    invariant="last_loss_time auto-purgé après TTL",
                    observed=f"age={age:.0f}s, ttl={_COOLDOWN_TTL}s",
                    category="temporal",
                )
            )

    for sym, count in snap.trades_this_hour.items():
        if count >= 10:
            issues.append(
                _iss(
                    rule="temporal.rate_limit_hit",
                    severity=IntegritySeverity.WARNING,
                    description=(
                        f"{sym}: {count} trades/heure — rate limit atteint"
                        ", exécution bloquée"
                    ),
                    invariant="trades_this_hour[sym] < 10 pour opération normale",
                    observed=f"trades_this_hour={count}",
                    category="temporal",
                )
            )

    return issues


# ── 5. Order integrity ─────────────────────────────────────────────────────────


def check_order_integrity(snap: StateSnapshot) -> list[IntegrityIssue]:
    """
    Invariants vérifiés :
      - ordres pending impliquent une position ouverte (ou en cours de remplissage)
    """
    issues: list[IntegrityIssue] = []

    if snap.pending_order_count > 0 and snap.open_count_stats == 0:
        issues.append(
            _iss(
                rule="order.pending_without_position",
                severity=IntegritySeverity.DEGRADED,
                description=(
                    f"{snap.pending_order_count} ordre(s) pending sans position ouverte"
                    " — capital potentiellement réservé inutilement"
                ),
                invariant="pending_orders → open_positions > 0 (ou remplissage récent)",
                observed=(
                    f"pending={snap.pending_order_count}, "
                    f"open_pos={snap.open_count_stats}"
                ),
                category="order",
            )
        )

    return issues


# ── Registre de toutes les règles ─────────────────────────────────────────────

ALL_CHECKS = [
    check_signal_integrity,
    check_position_integrity,
    check_capital_integrity,
    check_temporal_integrity,
    check_order_integrity,
]
