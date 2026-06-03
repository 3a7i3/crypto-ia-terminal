"""
core/lifecycle.py — S4 : Modèle formel du lifecycle DecisionPacket.

Source unique de vérité pour le graphe d'états du DecisionPacket.
Toute logique de transition dans le système doit dériver d'ici.

Propriétés garanties :
    - ALLOWED_TRANSITIONS est le graphe COMPLET (nominal + terminaux exceptionnels)
    - Chaque état terminal a un ensemble vide de successeurs
    - Toute transition absente est interdite — aucun comportement implicite
    - Le diagramme Mermaid est généré depuis ce graphe (documentation = code)
    - La vérification exhaustive parcourt tous les états et toutes les arêtes

Invariant fondamental :
    ∀ s ∈ TERMINAL_STATES : ALLOWED_TRANSITIONS[s] = ∅

Usage :
    from core.lifecycle import (
        ALLOWED_TRANSITIONS,
        TERMINAL_STATES,
        EXCEPTIONAL_TERMINAL_STATES,
        is_transition_allowed,
        verify_lifecycle_exhaustive,
        generate_mermaid_diagram,
    )
"""

from __future__ import annotations

from typing import FrozenSet

from core.decision_packet import (
    EXCEPTIONAL_TERMINAL_STATES,
    TERMINAL_STATES,
    DecisionState,
)

# ---------------------------------------------------------------------------
# Import des états depuis decision_packet — lifecycle.py ne redéfinit rien.
# Il organise et expose le graphe complet.
# ---------------------------------------------------------------------------


_S = DecisionState  # alias local

# ---------------------------------------------------------------------------
# Graphe complet — source unique de vérité (S4)
#
# Structure : état → frozenset des états atteignables directement
#
# Règles encodées dans ce graphe :
#   1. Flux nominal : séquence linéaire documentée dans DecisionState
#   2. REGIME_VALIDATED optionnel : CONTEXT_ENRICHED peut sauter vers RISK_EVALUATED
#   3. Terminaux exceptionnels (REJECTED, EXPIRED, CANCELLED, FAILED, VETOED) :
#      accessibles depuis tout état non-terminal — représente veto, panne, kill switch
#   4. POSTMORTEM_ANALYZED : terminal nominal uniquement depuis CLOSED
#   5. Tout état terminal → frozenset() vide — aucune transition sortante
# ---------------------------------------------------------------------------

# États terminaux exceptionnels — copiés depuis decision_packet pour clarté locale
_EXCEPTIONAL: FrozenSet[DecisionState] = frozenset(EXCEPTIONAL_TERMINAL_STATES)


# Raccourci : successeurs nominaux d'un état non-terminal
# = ses successeurs du flux linéaire + tous les terminaux exceptionnels
def _nominal(
    *next_states: DecisionState,
) -> FrozenSet[DecisionState]:
    """Construit l'ensemble des successeurs d'un état non-terminal."""
    return frozenset(next_states) | _EXCEPTIONAL


ALLOWED_TRANSITIONS: dict[DecisionState, FrozenSet[DecisionState]] = {
    # ── Flux nominal ──────────────────────────────────────────────────────
    _S.CREATED: _nominal(_S.SIGNAL_GENERATED),
    _S.SIGNAL_GENERATED: _nominal(_S.CONTEXT_ENRICHED),
    _S.CONTEXT_ENRICHED: _nominal(
        _S.REGIME_VALIDATED,  # optionnel — si couche régime présente
        _S.RISK_EVALUATED,  # court-circuit si régime absent
    ),
    _S.REGIME_VALIDATED: _nominal(_S.RISK_EVALUATED),
    _S.RISK_EVALUATED: _nominal(_S.APPROVED),
    _S.APPROVED: _nominal(_S.EXECUTION_PENDING),
    _S.EXECUTION_PENDING: _nominal(_S.EXECUTED),
    _S.EXECUTED: _nominal(_S.MONITORED),
    _S.MONITORED: _nominal(_S.CLOSED),
    _S.CLOSED: _nominal(_S.POSTMORTEM_ANALYZED),
    # ── États terminaux — aucun successeur ────────────────────────────────
    # Propriété : ∀ s ∈ TERMINAL_STATES, ALLOWED_TRANSITIONS[s] = ∅
    _S.POSTMORTEM_ANALYZED: frozenset(),
    _S.REJECTED: frozenset(),
    _S.EXPIRED: frozenset(),
    _S.CANCELLED: frozenset(),
    _S.FAILED: frozenset(),
    _S.VETOED: frozenset(),
}

# Assertion statique : tous les états DecisionState sont couverts
_missing = [s for s in DecisionState if s not in ALLOWED_TRANSITIONS]
if _missing:
    raise RuntimeError(
        f"[lifecycle] États DecisionState non couverts dans ALLOWED_TRANSITIONS : {_missing}. "
        "Mettre à jour core/lifecycle.py lors de tout ajout d'état."
    )


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------


def is_transition_allowed(
    from_state: DecisionState,
    to_state: DecisionState,
) -> bool:
    """
    Retourne True si la transition from_state → to_state est autorisée.

    Source unique : consulte ALLOWED_TRANSITIONS uniquement.
    """
    return to_state in ALLOWED_TRANSITIONS.get(from_state, frozenset())


def successors(state: DecisionState) -> FrozenSet[DecisionState]:
    """Retourne l'ensemble des états atteignables depuis state."""
    return ALLOWED_TRANSITIONS.get(state, frozenset())


def is_terminal(state: DecisionState) -> bool:
    """True si l'état est terminal (aucun successeur)."""
    return not ALLOWED_TRANSITIONS.get(state, frozenset())


def is_exceptional_terminal(state: DecisionState) -> bool:
    """True si l'état est un terminal exceptionnel (veto, panne, reject)."""
    return state in _EXCEPTIONAL


# ---------------------------------------------------------------------------
# Vérification exhaustive — S4
# ---------------------------------------------------------------------------


def verify_lifecycle_exhaustive() -> list[str]:
    """
    Parcourt exhaustivement le graphe et vérifie ses propriétés fondamentales.

    Vérifie :
      1. Couverture : tous les états DecisionState sont dans ALLOWED_TRANSITIONS
      2. Cohérence terminaux : tout état terminal a un ensemble vide
      3. Cohérence non-terminaux : tout état non-terminal atteint au moins un successeur
      4. Accessibilité : tous les états sont atteignables depuis CREATED
      5. Pas de transition auto-référente
      6. États terminaux exceptionnels accessibles depuis tous les non-terminaux

    Returns:
        Liste de violations (vide si le graphe est cohérent).
    """
    violations: list[str] = []

    # 1. Couverture
    for state in DecisionState:
        if state not in ALLOWED_TRANSITIONS:
            violations.append(f"[COV] {state.value} absent de ALLOWED_TRANSITIONS")

    # 2. Cohérence terminaux
    for state in TERMINAL_STATES:
        succs = ALLOWED_TRANSITIONS.get(state, frozenset())
        if succs:
            violations.append(
                f"[TERM] {state.value} est terminal mais a des successeurs : "
                f"{[s.value for s in succs]}"
            )

    # 3. Cohérence non-terminaux
    non_terminals = [s for s in DecisionState if s not in TERMINAL_STATES]
    for state in non_terminals:
        succs = ALLOWED_TRANSITIONS.get(state, frozenset())
        if not succs:
            violations.append(
                f"[NONTERM] {state.value} est non-terminal mais sans successeur"
            )

    # 4. Accessibilité depuis CREATED (BFS)
    reachable: set[DecisionState] = set()
    queue = [DecisionState.CREATED]
    while queue:
        current = queue.pop()
        if current in reachable:
            continue
        reachable.add(current)
        for succ in ALLOWED_TRANSITIONS.get(current, frozenset()):
            queue.append(succ)

    unreachable = [s for s in DecisionState if s not in reachable]
    for state in unreachable:
        violations.append(f"[REACH] {state.value} inaccessible depuis CREATED")

    # 5. Pas d'auto-référence
    for state, succs in ALLOWED_TRANSITIONS.items():
        if state in succs:
            violations.append(
                f"[SELF] {state.value} → {state.value} (auto-référence interdite)"
            )

    # 6. Terminaux exceptionnels accessibles depuis tous les non-terminaux
    for state in non_terminals:
        succs = ALLOWED_TRANSITIONS.get(state, frozenset())
        for exc in _EXCEPTIONAL:
            if exc not in succs:
                violations.append(
                    f"[EXCTERM] {state.value} n'a pas {exc.value} comme successeur "
                    "— terminal exceptionnel doit être accessible depuis tout non-terminal"
                )

    return violations


# ---------------------------------------------------------------------------
# P-01 — Absence de deadlock
# ∀ état non-terminal ∃ chemin vers un terminal
# ---------------------------------------------------------------------------


def verify_no_deadlock() -> list[str]:
    """
    P-01 : Vérifie qu'aucun état non-terminal n'est un deadlock.

    Un deadlock serait un état depuis lequel aucun chemin ne mène à un terminal.
    Par construction du graphe (_EXCEPTIONAL accessibles partout), cette propriété
    est structurellement garantie — cette vérification le prouve formellement.
    """
    violations: list[str] = []
    terminal_set = frozenset(s for s in DecisionState if not ALLOWED_TRANSITIONS.get(s))
    non_terminals = [s for s in DecisionState if s not in terminal_set]

    for start in non_terminals:
        # BFS pour trouver un terminal depuis start
        visited: set[DecisionState] = set()
        queue = [start]
        found_terminal = False
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            if current in terminal_set:
                found_terminal = True
                break
            for succ in ALLOWED_TRANSITIONS.get(current, frozenset()):
                if succ not in visited:
                    queue.append(succ)
        if not found_terminal:
            violations.append(
                f"[P-01/DEADLOCK] {start.value} : aucun chemin vers un terminal"
            )

    return violations


# ---------------------------------------------------------------------------
# P-02 — Absence de cycle dans le flux nominal
# Le graphe des transitions nominales (hors exceptionnels) est un DAG.
# ---------------------------------------------------------------------------


def _nominal_successors(state: DecisionState) -> frozenset:
    """Successeurs nominaux d'un état : successeurs sans les terminaux exceptionnels."""
    return ALLOWED_TRANSITIONS.get(state, frozenset()) - _EXCEPTIONAL


def verify_no_nominal_cycle() -> list[str]:
    """
    P-02 : Vérifie que le flux nominal est acyclique (DAG).

    Un cycle nominal comme APPROVED → RISK_EVALUATED → APPROVED serait catastrophique :
    il permettrait de contourner les gardes en boucle et de re-démarrer un lifecycle.

    Utilise un DFS tri-couleur (blanc/gris/noir) sur les arêtes nominales uniquement.
    Les arêtes vers les terminaux exceptionnels sont ignorées (ils sont absorbants).
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[DecisionState, int] = {s: WHITE for s in DecisionState}
    violations: list[str] = []
    cycle_path: list[DecisionState] = []

    def _dfs(v: DecisionState) -> bool:
        color[v] = GRAY
        cycle_path.append(v)
        for u in sorted(_nominal_successors(v), key=lambda s: s.value):
            if color[u] == GRAY:
                idx = cycle_path.index(u)
                cycle_str = (
                    " -> ".join(s.value for s in cycle_path[idx:]) + f" -> {u.value}"
                )
                violations.append(f"[P-02/CYCLE] Cycle nominal detecte : {cycle_str}")
                return True
            if color[u] == WHITE:
                if _dfs(u):
                    return True
        cycle_path.pop()
        color[v] = BLACK
        return False

    non_terminals = [s for s in DecisionState if s not in TERMINAL_STATES]
    for state in non_terminals:
        if color[state] == WHITE:
            _dfs(state)

    return violations


# ---------------------------------------------------------------------------
# P-03 — Unicité du terminal nominal
# POSTMORTEM_ANALYZED est le seul terminal nominal (non-exceptionnel)
# ---------------------------------------------------------------------------


def verify_unique_nominal_terminal() -> list[str]:
    """
    P-03 : Vérifie que POSTMORTEM_ANALYZED est le seul terminal nominal.

    Les terminaux exceptionnels (REJECTED, EXPIRED, CANCELLED, FAILED, VETOED)
    représentent des résolutions anormales du lifecycle.
    Le seul terminal nominal doit être POSTMORTEM_ANALYZED.

    Propriété utile pour les analyses statistiques : 100% des packets doivent
    idéalement atteindre POSTMORTEM_ANALYZED, les autres sont des résolutions prématurées.
    """
    violations: list[str] = []
    nominal_terminals = frozenset(TERMINAL_STATES) - _EXCEPTIONAL
    expected = frozenset({DecisionState.POSTMORTEM_ANALYZED})
    if nominal_terminals != expected:
        extra = nominal_terminals - expected
        missing = expected - nominal_terminals
        if extra:
            violations.append(
                f"[P-03/EXTRA] Terminaux nominaux non attendus : "
                f"{[s.value for s in sorted(extra, key=lambda s: s.value)]}"
            )
        if missing:
            violations.append(
                f"[P-03/MISSING] POSTMORTEM_ANALYZED absent des terminaux nominaux"
            )
    return violations


# ---------------------------------------------------------------------------
# Vérification complète S4 + P-01/P-02/P-03 unifiée
# ---------------------------------------------------------------------------


def verify_all_properties() -> dict[str, list[str]]:
    """
    Lance toutes les vérifications disponibles.

    Returns:
        Dict {propriété: [violations]} — valeurs vides si propriété satisfaite.
    """
    return {
        "S4_exhaustive": verify_lifecycle_exhaustive(),
        "P01_no_deadlock": verify_no_deadlock(),
        "P02_no_cycle": verify_no_nominal_cycle(),
        "P03_unique_nominal_terminal": verify_unique_nominal_terminal(),
    }


# ---------------------------------------------------------------------------
# Génération de diagramme Mermaid — documentation = code
# ---------------------------------------------------------------------------

_STATE_STYLE: dict[str, str] = {
    "CREATED": "fill:#e8f4fd,stroke:#2196F3",
    "POSTMORTEM_ANALYZED": "fill:#e8f5e9,stroke:#4CAF50",
    "REJECTED": "fill:#fce4ec,stroke:#e91e63",
    "EXPIRED": "fill:#fff3e0,stroke:#FF9800",
    "CANCELLED": "fill:#fff3e0,stroke:#FF9800",
    "FAILED": "fill:#fce4ec,stroke:#e91e63",
    "VETOED": "fill:#fce4ec,stroke:#e91e63",
}


def generate_mermaid_diagram(
    exclude_exceptional: bool = False,
    compact: bool = False,
) -> str:
    """
    Génère un diagramme Mermaid du graphe de lifecycle.

    Args:
        exclude_exceptional : si True, n'affiche pas les arêtes vers
                              les terminaux exceptionnels (diagramme simplifié)
        compact             : si True, format condensé sans labels d'états

    Returns:
        Chaîne Mermaid prête à être rendue dans un README ou un outil de doc.

    Exemple :
        graph TD
            CREATED -->|→| SIGNAL_GENERATED
            ...
    """
    lines = ["stateDiagram-v2", "    direction LR", ""]

    # Styles pour les états terminaux
    for state in TERMINAL_STATES:
        style = _STATE_STYLE.get(state.value, "")
        if style:
            lines.append(f"    {state.value}")

    lines.append("")

    # Arêtes
    for from_state, succs in ALLOWED_TRANSITIONS.items():
        for to_state in sorted(succs, key=lambda s: s.value):
            if exclude_exceptional and to_state in _EXCEPTIONAL:
                continue
            arrow = f"    {from_state.value} --> {to_state.value}"
            lines.append(arrow)

    # Légende classes
    lines.append("")
    lines.append("    classDef terminal fill:#fce4ec,stroke:#e91e63,font-weight:bold")
    lines.append(
        "    class " + ",".join(s.value for s in TERMINAL_STATES) + " terminal"
    )

    return "\n".join(lines)


def generate_ascii_summary() -> str:
    """
    Résumé ASCII du graphe nominal (sans les terminaux exceptionnels).
    Lisible dans les logs et les rapports texte.
    """
    nominal_path = [
        DecisionState.CREATED,
        DecisionState.SIGNAL_GENERATED,
        DecisionState.CONTEXT_ENRICHED,
        DecisionState.REGIME_VALIDATED,
        DecisionState.RISK_EVALUATED,
        DecisionState.APPROVED,
        DecisionState.EXECUTION_PENDING,
        DecisionState.EXECUTED,
        DecisionState.MONITORED,
        DecisionState.CLOSED,
        DecisionState.POSTMORTEM_ANALYZED,
    ]
    exceptional_labels = ", ".join(
        s.value for s in sorted(_EXCEPTIONAL, key=lambda s: s.value)
    )

    lines = ["DecisionPacket Lifecycle — Flux nominal :"]
    for i, state in enumerate(nominal_path):
        prefix = "  " if i == 0 else "    ↓"
        lines.append(f"{prefix} {state.value}")

    lines.append("")
    lines.append(f"  Terminaux exceptionnels (depuis tout état non-terminal) :")
    lines.append(f"    → {exceptional_labels}")
    lines.append("")
    lines.append(f"  Total états     : {len(DecisionState)}")
    lines.append(f"  États terminaux : {len(TERMINAL_STATES)}")
    total_edges = sum(len(s) for s in ALLOWED_TRANSITIONS.values())
    lines.append(f"  Arêtes totales  : {total_edges}")

    return "\n".join(lines)
