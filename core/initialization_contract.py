"""
core/initialization_contract.py — Execution Initialization Contract (EIC) v2

Trois invariants orthogonaux vérifiables à trois niveaux :

    VALIDITY = AST_OK ∧ IMPORT_GRAPH_OK ∧ RUNTIME_PARITY_OK

Tier 1 — IMPORT_SAFE
    Permis à l'import : constantes, dataclasses, définitions de types,
    getLogger(), lecture d'env sans mutation.
    Interdit : makedirs, load_dotenv, basicConfig, connexions réseau.

Tier 2 — RUNTIME_INIT  (doit être dans main() ou _setup())
    os.makedirs, load_dotenv, logging.basicConfig, RuntimeStateMachine(),
    init_authority() — doivent être appelés APRÈS import, AVANT G1.

Tier 3 — GATE_REQUIRED  (doit être après get_authority().can_trade() == True)
    compute_features(), scanner.scan(), tout ordre d'exécution.

EIC v2 ajoute :
    - ASTSideEffectScanner  : détection AST réelle (pas du pattern matching de chaîne)
    - ImportGraphChecker    : topologie de dépendances, détecte les modules impurs
    - RuntimeSnapshot       : capture avant/après import pour delta sys.modules + env
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple

# ---------------------------------------------------------------------------
# Déclaration formelle des side-effects connus
# ---------------------------------------------------------------------------


class SideEffect(NamedTuple):
    tier: str  # "RUNTIME_INIT" ou "IMPORT_SAFE"
    pattern: str  # fragment lisible identifiant l'appel
    location: str  # fichier:ligne indicatif
    compliant: bool  # True = déjà déplacé au bon niveau


KNOWN_SIDE_EFFECTS: list[SideEffect] = [
    SideEffect(
        tier="RUNTIME_INIT",
        pattern='os.makedirs("logs"',
        location="core/advisor_loop.py:59",
        compliant=False,
    ),
    SideEffect(
        tier="RUNTIME_INIT",
        pattern="load_dotenv(override=True)",
        location="core/advisor_loop.py:167",
        compliant=False,
    ),
    SideEffect(
        tier="RUNTIME_INIT",
        pattern="logging.basicConfig(",
        location="core/advisor_loop.py:175",
        compliant=False,
    ),
    SideEffect(
        tier="IMPORT_SAFE",
        pattern="load_advisor_runtime",
        location="core/advisor_runtime_adapters.py:50",
        compliant=True,
    ),
]


# ---------------------------------------------------------------------------
# Couche 1 — AST : détection statique des side-effects module-level
# ---------------------------------------------------------------------------


class ASTSideEffectScanner:
    """
    Scanne les instructions au niveau module (tree.body) à la recherche
    d'appels appartenant à la classe Tier-2.

    Ne descend PAS dans les corps de fonctions, classes, ni dans les
    guards `if __name__ == '__main__':`. Seules les expressions nues
    `ast.Expr(ast.Call)` sont vérifiées — les assignments (x = call())
    ne sont pas signalés car ils peuvent être des lectures légitimes.
    """

    #: Paires (module_name | None, function_name) interdites au module level.
    _FORBIDDEN: frozenset[tuple[str | None, str]] = frozenset(
        {
            ("os", "makedirs"),
            ("os", "mkdir"),
            ("os", "rmdir"),
            ("os", "remove"),
            ("logging", "basicConfig"),
            ("logging", "FileHandler"),
            ("logging", "StreamHandler"),
            (None, "load_dotenv"),
            (None, "open"),
        }
    )

    def scan(self, source: str) -> list[tuple[int, str]]:
        """
        Retourne [(lineno, source_line_stripped), ...] pour chaque
        expression de module-level qui correspond à un appel interdit.
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        lines = source.splitlines()
        violations: list[tuple[int, str]] = []

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(node, ast.If) and self._is_main_guard(node):
                continue
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                if self._is_forbidden(node.value):
                    lineno = node.lineno
                    line = lines[lineno - 1].strip() if lineno <= len(lines) else ""
                    violations.append((lineno, line))

        return violations

    def _is_forbidden(self, call: ast.Call) -> bool:
        func = call.func
        if isinstance(func, ast.Name):
            return (None, func.id) in self._FORBIDDEN
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            return (func.value.id, func.attr) in self._FORBIDDEN
        return False

    @staticmethod
    def _is_main_guard(node: ast.If) -> bool:
        t = node.test
        if not (
            isinstance(t, ast.Compare)
            and len(t.ops) == 1
            and isinstance(t.ops[0], ast.Eq)
        ):
            return False
        right = t.comparators[0] if t.comparators else None
        return (
            isinstance(t.left, ast.Name)
            and t.left.id == "__name__"
            and isinstance(right, ast.Constant)
            and right.value == "__main__"
        )


# ---------------------------------------------------------------------------
# Couche 2 — Import Graph : topologie de dépendances
# ---------------------------------------------------------------------------


class ImportGraphChecker:
    """
    Construit le graphe statique des imports d'un répertoire et détecte
    les modules qui ont des side-effects Tier-2 à l'import.

    Usage :
        checker = ImportGraphChecker(root=ROOT)
        graph   = checker.build_graph(ROOT / "core")
        impure  = checker.find_impure_modules(ROOT / "core")
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._scanner = ASTSideEffectScanner()

    def build_graph(self, directory: Path) -> dict[str, list[str]]:
        """
        Retourne {chemin_relatif: [noms_de_modules_importés]}.
        Ne descend pas dans __pycache__.
        """
        graph: dict[str, list[str]] = {}
        for py_file in sorted(directory.rglob("*.py")):
            if "__pycache__" in py_file.parts:
                continue
            rel = str(py_file.relative_to(self._root))
            graph[rel] = self._extract_imports(py_file)
        return graph

    def find_impure_modules(self, directory: Path) -> dict[str, list[tuple[int, str]]]:
        """
        Retourne {chemin_relatif: [(lineno, code), ...]} pour chaque fichier
        contenant des side-effects Tier-2 détectés par l'AST scanner.
        """
        impure: dict[str, list[tuple[int, str]]] = {}
        for py_file in sorted(directory.rglob("*.py")):
            if "__pycache__" in py_file.parts:
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            violations = self._scanner.scan(source)
            if violations:
                rel = str(py_file.relative_to(self._root))
                impure[rel] = violations
        return impure

    def _extract_imports(self, path: Path) -> list[str]:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return []
        imports: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        return imports


# ---------------------------------------------------------------------------
# Couche 3 — Runtime Parity : delta avant/après import
# ---------------------------------------------------------------------------


class RuntimeSnapshot:
    """
    Capture l'état runtime avant et après une opération (typiquement un import)
    pour détecter les mutations silencieuses de sys.modules ou os.environ.

    Usage :
        snap = RuntimeSnapshot()
        snap.before()
        import some_module          # ou toute autre opération
        snap.after()
        assert snap.is_env_pure()  # aucune clé d'env ajoutée
        delta = snap.delta()       # {"new_modules": [...], "env_mutations": [...]}
    """

    def __init__(self) -> None:
        self._before: dict[str, set[str]] | None = None
        self._after: dict[str, set[str]] | None = None

    def before(self) -> None:
        self._before = {
            "modules": set(sys.modules.keys()),
            "env": set(os.environ.keys()),
        }
        self._after = None

    def after(self) -> None:
        if self._before is None:
            raise RuntimeError("Appeler before() avant after()")
        self._after = {
            "modules": set(sys.modules.keys()),
            "env": set(os.environ.keys()),
        }

    def delta(self) -> dict[str, list[str]]:
        if self._before is None or self._after is None:
            raise RuntimeError("Appeler before() et after() avant delta()")
        return {
            "new_modules": sorted(self._after["modules"] - self._before["modules"]),
            "env_mutations": sorted(self._after["env"] - self._before["env"]),
        }

    def is_env_pure(self) -> bool:
        """Retourne True si aucune clé d'env n'a été ajoutée."""
        return len(self.delta()["env_mutations"]) == 0


# ---------------------------------------------------------------------------
# API publique (backward-compat avec EIC v1)
# ---------------------------------------------------------------------------


class ContractViolation(Exception):
    """Levée quand un side-effect Tier-2 est détecté à l'import."""


def assert_import_purity(module_path: str | Path) -> list[tuple[int, str]]:
    """
    Vérifie qu'un module Python ne contient pas de side-effects Tier-2
    au niveau module. Utilise ASTSideEffectScanner (v2, réel AST).

    Retourne [(lineno, code_fragment), ...] — liste vide si module pur.
    """
    path = Path(module_path)
    if not path.exists():
        raise FileNotFoundError(f"Module introuvable : {path}")
    source = path.read_text(encoding="utf-8")
    return ASTSideEffectScanner().scan(source)


def check_advisor_loop_purity() -> dict:
    """
    Vérifie les violations EIC dans advisor_loop.py.

    Retourne :
        violations       : liste brute des violations détectées
        compliant        : True si aucune violation
        known_non_compliant : entrées KNOWN_SIDE_EFFECTS avec compliant=False
        undocumented     : violations sans entrée correspondante dans KNOWN_SIDE_EFFECTS
    """
    root = Path(__file__).parent.parent
    advisor_path = root / "core" / "advisor_loop.py"
    violations = assert_import_purity(advisor_path)
    known_non_compliant = [se for se in KNOWN_SIDE_EFFECTS if not se.compliant]
    undocumented = [
        v
        for v in violations
        if not any(se.pattern in v[1] for se in KNOWN_SIDE_EFFECTS)
    ]
    return {
        "violations": violations,
        "compliant": len(violations) == 0,
        "known_non_compliant": known_non_compliant,
        "undocumented": undocumented,
    }


# ---------------------------------------------------------------------------
# Décorateurs-marqueurs de tier (documentation formelle, sans effet runtime)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Authority Totality Contract (ATC)
# ---------------------------------------------------------------------------


class AuthorityTotalityContract:
    """
    ATC — Authority Totality Contract.

    Invariant central (Z3-translatable) :

        ∀ execution trace e:
            get_authority(e) ∈ Authority  (fonction totale, jamais None)
        ⟹
            G1(e) = ¬can_trade(get_authority(e))  (gate total, bien défini)
        ⟹
            ¬G1(e) → compute_graph ⊆ authorized_execution_space

    Deux propriétés vérifiables statiquement :

    1. NULL_FALLBACK : aucun fallback de get_authority() ne retourne None.
       Violation = `return None` dans le corps d'une fonction `_get_authority`.

    2. G1_NULL_GUARD : G1 ne conditionne pas l'autorité sur un check `is not None`.
       Violation = pattern `_auth is not None and` ou `if _auth is not None:`.
       Présence de ce pattern = ancien modèle, graphe non-total.
    """

    # Violation 2 — null-guard sur _auth dans G1 / check secondaire
    _NULL_GUARD_RE = re.compile(
        r"_auth\s+is\s+not\s+None\s+and" r"|if\s+_auth\s+is\s+not\s+None\s*:",
        re.MULTILINE,
    )

    def validate_no_null_fallback(self, source: str) -> list[str]:
        """
        Propriété 1 (NULL_FALLBACK) — inspection AST.

        Cherche la fonction `_get_authority` définie au niveau module
        (fallback ImportError) et vérifie qu'elle ne contient pas de
        `return None`. Utilise l'AST pour éviter les faux positifs
        sur les commentaires contenant le texte "return None".

        Retourne les descriptions des violations. Liste vide = conforme.
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        violations: list[str] = []
        for node in tree.body:
            if not (
                isinstance(node, ast.FunctionDef) and node.name == "_get_authority"
            ):
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Return):
                    is_none = child.value is None or (
                        isinstance(child.value, ast.Constant)
                        and child.value.value is None
                    )
                    if is_none:
                        violations.append(
                            f"line {child.lineno}: `return None` dans _get_authority — "
                            "viole ATC (doit lever RuntimeError)"
                        )
        return violations

    def validate_g1_totality(self, source: str) -> list[tuple[int, str]]:
        """
        Retourne [(lineno, line_stripped), ...] violant la propriété 2 (G1_NULL_GUARD).
        Liste vide = conforme.
        """
        violations: list[tuple[int, str]] = []
        for i, line in enumerate(source.splitlines(), 1):
            if self._NULL_GUARD_RE.search(line):
                violations.append((i, line.strip()))
        return violations

    def validate(self, module_path: str | Path) -> dict:
        """
        Rapport complet ATC sur un module.

        Retourne :
            null_fallback  : violations propriété 1
            g1_null_guard  : violations propriété 2
            compliant      : True si aucune violation
        """
        source = Path(module_path).read_text(encoding="utf-8")
        null_fallback = self.validate_no_null_fallback(source)
        g1_null_guard = self.validate_g1_totality(source)
        return {
            "null_fallback": null_fallback,
            "g1_null_guard": g1_null_guard,
            "compliant": not null_fallback and not g1_null_guard,
        }


# ---------------------------------------------------------------------------
# Exception Normalization Contract (ENC)
# ---------------------------------------------------------------------------


class ExceptionNormalizationContract:
    """
    ENC — Exception Normalization Contract.

    Invariant : toute exception dans le graphe d'exécution doit mapper vers
    un état gouverné (SAFE_MODE decision packet OU controlled shutdown trace).

    Deux niveaux vérifiables :

    ENL-1 (G1) — authority exceptions :
        RuntimeError de _get_authority() est capturé dans analyze_symbol()
        par un except RuntimeError qui retourne un AnalysisResult fail-closed
        avec trace_id. ⟹ "SAFE_MODE decision packet" présent.

    ENL-2 (G3) — compute exceptions :
        Toute exception échappant analyze_symbol() est capturée au niveau
        cycle par `except Exception` qui appelle report_error("cycle_exception").
        ⟹ "controlled shutdown trace" via RSM.
        GAP actuel : aucun DP n'est généré — trace_id de cycle perdu.

    Vérifie statiquement que ces deux chemins existent dans le code.
    """

    # ENL-1 : G1 a un `except RuntimeError` qui retourne (pas re-raise)
    _ENL1_RE = re.compile(
        r"except RuntimeError\s*:(.*?)(?=\n\S|\Z)",
        re.DOTALL,
    )

    # ENL-2 : cycle loop a `report_error("cycle_exception")`
    _ENL2_RE = re.compile(
        r'report_error\s*\(\s*["\']cycle_exception["\']',
        re.MULTILINE,
    )

    def validate_enl1(self, source: str) -> bool:
        """
        Propriété ENL-1 : `except RuntimeError` présent dans le module
        ET le handler retourne un résultat (pas re-raise).

        True = conforme (handler existe).
        """
        match = self._ENL1_RE.search(source)
        if not match:
            return False
        handler_body = match.group(1)
        # Le handler ne doit pas re-raise (pas de `raise` nu dans le corps)
        has_bare_raise = bool(re.search(r"\n\s+raise\b(?!\s+\w)", handler_body))
        return not has_bare_raise

    def validate_enl2(self, source: str) -> bool:
        """
        Propriété ENL-2 : `report_error("cycle_exception")` présent.

        True = conforme (G3 notification existe).
        """
        return bool(self._ENL2_RE.search(source))

    def validate(self, module_path: str | Path) -> dict:
        """
        Rapport ENC complet.

        Retourne :
            enl1_compliant   : G1 RuntimeError handler présent et retourne
            enl2_compliant   : G3 report_error("cycle_exception") présent
            enl2_dp_gap      : True = ENL-2 existe mais sans DP trace record (gap connu)
            compliant        : ENL-1 + ENL-2 structurellement présents
        """
        source = Path(module_path).read_text(encoding="utf-8")
        enl1 = self.validate_enl1(source)
        enl2 = self.validate_enl2(source)
        # ENL-2 DP gap : vérifier que le cycle handler crée un DP trace record.
        # Marqueur unique : symbol="CYCLE_EXCEPTION" dans le source.
        has_dp_in_cycle_handler = bool(
            re.search(
                r"CYCLE_EXCEPTION",
                source,
            )
        )
        return {
            "enl1_compliant": enl1,
            "enl2_compliant": enl2,
            "enl2_dp_gap": enl2 and not has_dp_in_cycle_handler,
            "compliant": enl1 and enl2,
        }


# ---------------------------------------------------------------------------
# Semantic Exhaustiveness Checker (SEP)
# ---------------------------------------------------------------------------


class DPCreationSite(NamedTuple):
    file: str
    lineno: int
    constructor: str  # "DecisionPacket" ou alias
    symbol: str  # valeur de symbol= si constante, sinon ""
    has_explicit_category: bool  # True si event_category= présent
    category_value: str  # valeur string si détectable, sinon ""


class StateTransitionIntegrityChecker:
    """
    STI — State Transition Integrity Checker.

    Vérifie les contraintes croisées catégorie × état de cycle de vie.

    STI-1 : SYSTEM packets ne peuvent pas atteindre les états d'exécution.
            SYSTEM → APPROVED | EXECUTION_PENDING | EXECUTED : impossible.

    STI-2 : GOVERNANCE packets ne peuvent pas recevoir d'approbation de trading.
            GOVERNANCE → APPROVED | EXECUTION_PENDING | EXECUTED : impossible.

    STI-3 : TRADE packets n'ont pas de restrictions supplémentaires.

    Ces contraintes sont implémentées dans DecisionPacket.transition_to() (Garde 3)
    et vérifiées ici de façon statique + runtime.
    """

    # États minimaux qui doivent être bloqués pour SYSTEM et GOVERNANCE
    _REQUIRED_BLOCKED = frozenset(
        {
            "APPROVED",
            "EXECUTION_PENDING",
            "EXECUTED",
        }
    )

    def check_blocked_states_defined(self) -> bool:
        """Vérifie que CATEGORY_BLOCKED_STATES est importable et non-vide."""
        try:
            from core.decision_packet import CATEGORY_BLOCKED_STATES

            return len(CATEGORY_BLOCKED_STATES) >= 2
        except (ImportError, AttributeError):
            return False

    def validate_constraints_complete(self) -> dict:
        """
        Vérifie que SYSTEM et GOVERNANCE ont les états critiques dans leur
        blocked set. Retourne {compliant: bool, violations: list}.
        """
        try:
            from core.decision_packet import (
                CATEGORY_BLOCKED_STATES,
                PacketEventCategory,
            )
        except ImportError:
            return {
                "compliant": False,
                "violations": ["CATEGORY_BLOCKED_STATES non importable"],
            }

        violations: list[str] = []
        for cat_name in ("SYSTEM", "GOVERNANCE"):
            try:
                cat = PacketEventCategory(cat_name)
            except ValueError:
                violations.append(f"PacketEventCategory.{cat_name} absent")
                continue
            if cat not in CATEGORY_BLOCKED_STATES:
                violations.append(f"{cat_name} absent de CATEGORY_BLOCKED_STATES")
                continue
            blocked_values = {s.value for s in CATEGORY_BLOCKED_STATES[cat]}
            missing = self._REQUIRED_BLOCKED - blocked_values
            if missing:
                violations.append(
                    f"{cat_name} manque les états requis : {sorted(missing)}"
                )

        return {"compliant": not violations, "violations": violations}

    def verify_packet(self, dp: Any) -> list[str]:
        """
        Vérifie un packet runtime contre ses contraintes STI.
        Retourne les violations (liste vide = conforme).
        """
        try:
            from core.decision_packet import CATEGORY_BLOCKED_STATES
        except ImportError:
            return []
        blocked = CATEGORY_BLOCKED_STATES.get(dp.event_category, frozenset())
        if dp.lifecycle_state in blocked:
            return [
                f"STI violation runtime : {dp.event_category.value} packet "
                f"en état {dp.lifecycle_state.value}"
            ]
        return []


class SemanticExhaustivenessChecker:
    """
    SEP — Semantic Exhaustiveness Checker.

    Vérifie que le partitionnement TRADE / GOVERNANCE / SYSTEM est
    exhaustif pour tous les sites de création de DecisionPacket.

    Propriétés vérifiées :

    SEP-1  TAXONOMY_COMPLETE
           PacketEventCategory a exactement {TRADE, GOVERNANCE, SYSTEM}.
           Toute nouvelle valeur est une violation.

    SEP-2  SYSTEM_RESERVED
           Tout site avec symbol contenant "EXCEPTION", "TEST", "ERROR",
           "SYSTEM" qui n'est pas explicitement catégorisé SYSTEM est
           un signal d'alerte (potentielle mauvaise classification).

    SEP-3  NO_UNKNOWN_CATEGORY
           Toute valeur explicite de event_category doit être dans
           PacketEventCategory. Valeur inconnue = rupture de contrat.

    SEP-4  CREATION_AUDIT
           Tous les sites de création sont recensés et documentés.
           Un site non audité est un trou dans la preuve.

    Limites : approximation statique. Les aliases dynamiques (import as X)
    sont couverts via _KNOWN_CONSTRUCTORS. Une preuve complète nécessiterait
    une analyse de flux (dataflow analysis), pas seulement syntaxique.
    """

    _KNOWN_CONSTRUCTORS: frozenset[str] = frozenset(
        {
            "DecisionPacket",
            "_DP",  # alias dans advisor_loop.py ENL-2
        }
    )

    # Préfixes/fragments indiquant un DP non-décisionnel
    _SYSTEM_SYMBOL_PATTERNS: tuple[str, ...] = (
        "EXCEPTION",
        "exception",
        "TEST",
        "test_",
        "ERROR",
        "error",
        "SYSTEM",
        "system",
    )

    _EXPECTED_CATEGORIES: frozenset[str] = frozenset(
        {
            "TRADE",
            "GOVERNANCE",
            "SYSTEM",
        }
    )

    def scan_directory(self, directory: Path) -> list[DPCreationSite]:
        """
        Scanne un répertoire à la recherche de tous les sites de création
        de DecisionPacket (noms directs + aliases connus).

        Retourne une liste de DPCreationSite triée par fichier/ligne.
        """
        sites: list[DPCreationSite] = []
        for py_file in sorted(directory.rglob("*.py")):
            if "__pycache__" in py_file.parts:
                continue
            sites.extend(self._scan_file(py_file, directory))
        return sorted(sites, key=lambda s: (s.file, s.lineno))

    def _scan_file(self, path: Path, root: Path) -> list[DPCreationSite]:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return []

        rel = str(path.relative_to(root))
        sites: list[DPCreationSite] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name not in self._KNOWN_CONSTRUCTORS:
                continue

            # Extract symbol= kwarg if constant
            sym_val = ""
            for kw in node.keywords:
                if kw.arg == "symbol" and isinstance(kw.value, ast.Constant):
                    sym_val = str(kw.value.value)
                    break

            # Extract event_category= kwarg
            has_cat = False
            cat_val = ""
            for kw in node.keywords:
                if kw.arg == "event_category":
                    has_cat = True
                    # Try to extract string constant or attribute name
                    v = kw.value
                    if isinstance(v, ast.Constant):
                        cat_val = str(v.value)
                    elif isinstance(v, ast.Attribute):
                        cat_val = v.attr  # e.g. SYSTEM from PacketEventCategory.SYSTEM
                    break

            sites.append(
                DPCreationSite(
                    file=rel,
                    lineno=node.lineno,
                    constructor=name,
                    symbol=sym_val,
                    has_explicit_category=has_cat,
                    category_value=cat_val,
                )
            )
        return sites

    def check_taxonomy_completeness(self) -> dict:
        """
        SEP-1 : vérifie que PacketEventCategory a exactement 3 membres.
        """
        from core.decision_packet import PacketEventCategory

        members = {m.value for m in PacketEventCategory}
        missing = self._EXPECTED_CATEGORIES - members
        extra = members - self._EXPECTED_CATEGORIES
        return {
            "expected": sorted(self._EXPECTED_CATEGORIES),
            "actual": sorted(members),
            "missing": sorted(missing),
            "extra": sorted(extra),
            "compliant": not missing and not extra,
        }

    def check_system_reserved(
        self, sites: list[DPCreationSite]
    ) -> list[DPCreationSite]:
        """
        SEP-2 : sites avec un symbol suggérant un DP non-décisionnel
        mais sans event_category explicite SYSTEM.
        """
        alerts = []
        for site in sites:
            if not site.symbol:
                continue
            is_system_symbol = any(
                p in site.symbol for p in self._SYSTEM_SYMBOL_PATTERNS
            )
            if is_system_symbol and not site.has_explicit_category:
                alerts.append(site)
        return alerts

    def check_no_unknown_category(
        self, sites: list[DPCreationSite]
    ) -> list[DPCreationSite]:
        """
        SEP-3 : sites avec une catégorie explicite hors du set connu.
        """
        return [
            s
            for s in sites
            if s.has_explicit_category
            and s.category_value
            and s.category_value not in self._EXPECTED_CATEGORIES
        ]

    def report(self, directory: Path) -> dict:
        """
        Rapport SEP complet sur un répertoire.

        Retourne :
            total_sites           : nombre de sites de création
            explicit              : sites avec event_category explicite
            default_trade         : sites sans catégorie (défaut TRADE)
            system_reserved_alerts: SEP-2 — symboles système sans catégorie SYSTEM
            unknown_category      : SEP-3 — catégories inconnues
            taxonomy_ok           : SEP-1 — taxonomie complète
            sep_compliant         : True si toutes les propriétés SEP satisfaites
        """
        sites = self.scan_directory(directory)
        taxonomy = self.check_taxonomy_completeness()
        system_alerts = self.check_system_reserved(sites)
        unknown = self.check_no_unknown_category(sites)

        return {
            "total_sites": len(sites),
            "explicit": [s for s in sites if s.has_explicit_category],
            "default_trade": [s for s in sites if not s.has_explicit_category],
            "system_reserved_alerts": system_alerts,
            "unknown_category": unknown,
            "taxonomy_ok": taxonomy["compliant"],
            "sep_compliant": taxonomy["compliant"] and not unknown,
        }


def runtime_init(fn):
    """
    Marqueur : la fonction ne doit être appelée que dans main() / _setup(),
    jamais à l'import. N'a aucun effet à l'exécution.
    """
    fn.__eic_tier__ = "RUNTIME_INIT"
    return fn


def gate_required(fn):
    """
    Marqueur : la fonction ne doit être appelée qu'après
    get_authority().can_trade() == True (post-G1).
    """
    fn.__eic_tier__ = "GATE_REQUIRED"
    return fn
