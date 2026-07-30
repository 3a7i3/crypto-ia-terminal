"""
system/provenance.py — preuve de transformation et couverture normative.

Deux primitives, nées de deux limites constatées du protocole (2026-07-29).

**1. Une transformation déclarée n'est pas une transformation prouvée.**
Le § 20 du protocole demande à chaque étape de déclarer son opération, sa perte
d'information et ses hypothèses. Ce sont des phrases. Rien ne permettait de
vérifier qu'un artefact a bien été produit par le script annoncé, à partir des
entrées annoncées. `Provenance` transforme la déclaration en **empreinte
vérifiable** : hash de l'entrée, hash du script, hash de la sortie, population.
Même saut que « les tests passent » → « voici l'observation qui le montre ».

**2. Une couverture citée en remarque n'engage personne.**
« 3 constantes mesurées sur 234 » était une note de bas de page ; le lecteur
devait faire le calcul et en tirer lui-même les conséquences. `Coverage` rend le
ratio normatif : il porte un **plafond de confiance** mécanique, et un rapport
qui affirme plus que son plafond est en contradiction avec ses propres données.

Ce module ne lit aucune configuration et ne décide rien. Il ne sait pas ce qui
est « assez couvert » — il applique une grille écrite ici, discutable, et la
rend visible.

**Limite de `self_test()`, à garder explicite.** L'auto-test prouve une
COHÉRENCE INTERNE, pas une validité externe. `create_proof`, `verify_provenance`
et `self_test` partagent le même modèle de preuve : si ce modèle est
conceptuellement faux, les trois échouent ensemble — et l'auto-test passe. Ce
qu'il élimine réellement, c'est la RÉGRESSION logicielle : un composant qui
cesse de faire ce que les deux autres supposent. Ce qu'il ne peut pas éliminer,
c'est une erreur partagée par les trois. La seule parade connue reste extérieure :
une attaque adversariale, qui a effectivement trouvé deux défauts que ce module
ne pouvait pas voir seul (2026-07-30).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

__all__ = [
    "sha256_text",
    "sha256_file",
    "sha256_json",
    "PROVENANCE_SCHEMA_VERSION",
    "InputRef",
    "Provenance",
    "build_provenance",
    "verify_provenance",
    "CEILING_ORDER",
    "CEILING_NONE",
    "CEILING_LOW",
    "CEILING_MEDIUM",
    "CEILING_HIGH",
    "CEILING_FULL",
    "Coverage",
    "weakest_ceiling",
    "PROOF_KEY",
    "create_proof",
    "attach_proof",
    "verify_artifact",
    "artifact_has_proof",
    "proof_adoption",
    "CeilingBreakdown",
    "REQUIRED_PROOF_FIELDS",
    "MIN_TOTAL_FOR_HIGH_CEILING",
    "MIN_COMPATIBLE_PROOF_VERSION",
    "ValidityReport",
    "self_test",
    "VALIDITY_OK",
    "VALIDITY_BROKEN",
    "REPO_ROOT",
]

#: Version du schéma de provenance. Un consommateur qui lit une provenance dont
#: la version lui est inconnue doit refuser de conclure, pas deviner — c'est la
#: leçon de la gate D, qui lisait une clé qu'aucun producteur n'écrivait.
PROVENANCE_SCHEMA_VERSION = 1

#: Racine du dépôt, pour rendre relatifs les chemins enregistrés dans une preuve.
REPO_ROOT = Path(__file__).resolve().parents[1]

_CHUNK = 1 << 20


# ── Empreintes ────────────────────────────────────────────────────────────────


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> Optional[str]:
    """SHA-256 d'un fichier, ou None s'il est absent/illisible.

    None est un résultat, pas une erreur : un artefact dont l'entrée a disparu
    est précisément ce qu'on veut pouvoir constater.
    """
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while chunk := handle.read(_CHUNK):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def sha256_json(payload: object) -> str:
    """Empreinte d'une structure, indépendante de l'ordre des clés.

    `sort_keys=True` : deux rapports identiques au réordonnancement près ont la
    même empreinte. Sans cela, un simple changement de version de bibliothèque
    ferait croire à une modification de contenu.
    """
    return sha256_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    )


# ── Provenance ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InputRef:
    """Une entrée d'une transformation, avec son empreinte au moment de la lecture."""

    path: str
    sha256: Optional[str]
    n_records: Optional[int] = None


@dataclass
class Provenance:
    """Preuve reproductible d'une transformation observation → artefact.

    `output_sha256` est renseigné APRÈS sérialisation du corps du rapport : la
    provenance décrit un contenu, elle n'en fait pas partie. C'est ce qui permet
    à un consommateur de recalculer l'empreinte et de détecter une édition
    manuelle de l'artefact.
    """

    schema_version: int
    generated_at: str
    tool: str
    tool_sha256: Optional[str]
    inputs: list[InputRef] = field(default_factory=list)
    population: dict = field(default_factory=dict)
    output_sha256: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "tool": self.tool,
            "tool_sha256": self.tool_sha256,
            "inputs": [
                {"path": i.path, "sha256": i.sha256, "n_records": i.n_records}
                for i in self.inputs
            ],
            "population": self.population,
            "output_sha256": self.output_sha256,
            "notes": self.notes,
        }


def build_provenance(
    *,
    tool_path: Path,
    inputs: Sequence[InputRef] = (),
    population: Optional[Mapping] = None,
    notes: str = "",
    generated_at: Optional[str] = None,
) -> Provenance:
    """Provenance d'un artefact en cours de production.

    `tool_path` est haché : deux artefacts produits par deux versions du même
    script portent des empreintes d'outil différentes, ce qui rend visible le cas
    « le rapport a été produit par un code qui n'existe plus » — invisible
    aujourd'hui, et à l'origine de la traçabilité rompue de la gate D.
    """
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Provenance(
        schema_version=PROVENANCE_SCHEMA_VERSION,
        generated_at=stamp,
        tool=tool_path.name,
        tool_sha256=sha256_file(tool_path),
        inputs=list(inputs),
        population=dict(population or {}),
        notes=notes,
    )


def verify_provenance(
    stamp: Mapping, *, body: object = None, repo_root: Optional[Path] = None
) -> list[str]:
    """Écarts entre ce qu'une provenance affirme et ce qui est vérifiable.

    Retourne une liste de constats, vide si tout concorde. Ne lève jamais : un
    outil de vérification qui meurt sur un artefact malformé laisse le
    consommateur sans information, ce qui est le pire des cas.

    Ce qui est vérifié : version de schéma connue, présence de la date, empreinte
    de l'outil recalculable et identique, empreintes d'entrées identiques,
    empreinte de sortie identique au corps fourni.
    Ce qui n'est PAS vérifié : que la transformation annoncée soit celle qui a
    réellement eu lieu. Une empreinte prouve l'identité des octets, pas la
    justesse de l'opération.
    """
    issues: list[str] = []
    if not isinstance(stamp, Mapping):
        return ["provenance absente ou de type inattendu"]

    version = stamp.get("schema_version")
    if version is None:
        issues.append(
            "schema_version absent — le consommateur ne peut pas savoir quoi lire"
        )
    elif version != PROVENANCE_SCHEMA_VERSION:
        issues.append(
            f"schema_version {version} inconnu (attendu {PROVENANCE_SCHEMA_VERSION})"
        )

    if not stamp.get("generated_at"):
        issues.append("generated_at absent — fraîcheur non évaluable")

    # CHAMPS OBLIGATOIRES — corrige un defaut CRITIQUE trouve par verification
    # adversariale (2026-07-30) : `output_sha256` absent ou nul faisait sauter
    # silencieusement le controle du corps, et l'artefact etait certifie « corps
    # inchange ». Un bloc reduit a {schema_version, generated_at} obtenait
    # PREUVE=ok. Une empreinte manquante n'est pas une empreinte satisfaite.
    for champ in ("tool", "tool_sha256"):
        if not stamp.get(champ):
            issues.append(
                f"{champ} absent du bloc de preuve — le producteur n'est pas "
                f"identifiable, la preuve ne prouve rien"
            )
    if not isinstance(stamp.get("inputs"), list):
        issues.append("`inputs` absent ou mal typé — les entrées ne sont pas tracées")

    root = repo_root or Path.cwd()
    tool = stamp.get("tool")
    tool_path = stamp.get("tool_path")
    declared_tool_hash = stamp.get("tool_sha256")
    if tool and declared_tool_hash:
        # `tool_path` (relatif au dépôt) est la voie canonique ; la recherche par
        # NOM dans trois répertoires est un repli pour les preuves écrites avant
        # l'ajout du champ. Un producteur vivant ailleurs était auparavant
        # classé ROMPU alors qu'il était seulement introuvable.
        candidates = []
        if tool_path:
            candidates.append(root / tool_path)
        candidates += [root / "tools" / tool, root / "scripts" / tool, root / tool]
        for candidate in candidates:
            if candidate.exists():
                actual = sha256_file(candidate)
                if actual != declared_tool_hash:
                    issues.append(
                        f"empreinte de l'outil {tool} différente : l'artefact a été "
                        f"produit par une autre version du script"
                    )
                break
        else:
            issues.append(
                f"outil {tool} INTROUVABLE (chemin déclaré : {tool_path or 'aucun'}) "
                f"— l'empreinte n'est pas recalculable ici, ce qui n'est PAS la "
                f"preuve d'une altération"
            )

    for ref in stamp.get("inputs") or []:
        if not isinstance(ref, Mapping):
            issues.append("entrée de provenance malformée")
            continue
        path = ref.get("path")
        declared = ref.get("sha256")
        if not path or not declared:
            issues.append(f"entrée sans chemin ou sans empreinte : {ref}")
            continue
        # Chemins relatifs résolus contre le dépôt, jamais contre le répertoire
        # courant : sinon le verdict dépendait du dossier d'invocation.
        target = Path(path)
        if not target.is_absolute():
            target = root / target
        actual = sha256_file(target)
        if actual is None:
            issues.append(f"entrée disparue depuis la production : {path}")
        elif actual != declared:
            issues.append(f"entrée modifiée depuis la production : {path}")

    if body is not None:
        declared_output = stamp.get("output_sha256")
        if not declared_output:
            issues.append(
                "output_sha256 absent — le corps de l'artefact N'EST PAS vérifié ; "
                "ne pas lire ce bloc comme une garantie d'intégrité"
            )
        elif sha256_json(body) != declared_output:
            issues.append("corps de l'artefact modifié après production")

    return issues


# ── Couverture normative ──────────────────────────────────────────────────────

CEILING_NONE = "AUCUNE"
CEILING_LOW = "FAIBLE"
CEILING_MEDIUM = "MOYENNE"
CEILING_HIGH = "ELEVEE"
#: « COMPLETE » signifie >= 90 %, PAS 100 %. Le nom est optimiste et c'est
#: assume : le seuil est ecrit dans _CEILING_THRESHOLDS juste en dessous, et un
#: rapport qui cite le plafond cite aussi son ratio.
CEILING_FULL = "COMPLETE"

#: Du plus contraignant au moins contraignant. Sert au maillon faible : une
#: chaîne ne vaut jamais mieux que son plafond le plus bas.
CEILING_ORDER = [
    CEILING_NONE,
    CEILING_LOW,
    CEILING_MEDIUM,
    CEILING_HIGH,
    CEILING_FULL,
]

#: Grille de plafonnement. Volontairement grossière et exposée : le seul intérêt
#: d'un seuil est qu'il soit discutable en un coup d'œil. Ces bornes ne sont PAS
#: des seuils du moteur de trading — elles ne gouvernent qu'un niveau de langage
#: admissible dans un rapport.
#: En dessous de ce denominateur, aucun ratio ne peut justifier mieux que MOYENNE.
MIN_TOTAL_FOR_HIGH_CEILING = 5

_CEILING_THRESHOLDS = [
    (0.90, CEILING_FULL),
    (0.50, CEILING_HIGH),
    (0.10, CEILING_MEDIUM),
    (0.0, CEILING_LOW),
]


@dataclass(frozen=True)
class Coverage:
    """Couverture d'une mesure, avec son plafond de confiance MÉCANIQUE.

    Exemple réel : INV-INIT-001 est énoncé sur 234 constantes et mesuré sur 3.
    `Coverage(measured=3, total=234)` rend `ratio=0.0128` et
    `confidence_ceiling=FAIBLE`. Le rapport n'a plus le droit d'écrire
    « vérifié » : son propre objet de couverture le contredit.
    """

    measured: int
    total: int
    subject: str = ""

    @property
    def inconsistent(self) -> bool:
        """Compteur impossible : mesure > total, ou valeurs negatives.

        Accepte silencieusement, `measured=10 total=5` rendait un ratio de 2.0 et
        donc le plafond MAXIMUM — un compteur casse produisait la meilleure note
        (defaut demontre par attaque adversariale le 2026-07-30).
        """
        return self.measured < 0 or self.total < 0 or self.measured > self.total

    @property
    def ratio(self) -> float:
        if self.total <= 0:
            return 0.0
        return min(1.0, max(0.0, self.measured / self.total))

    @property
    def capped_by_small_denominator(self) -> bool:
        """Le plafond est-il abaisse par la petitesse du denominateur ?

        Rendu explicite : le plafonnement etait invisible dans les rapports, donc
        indistinguable d'un vrai ratio faible.
        """
        return 0 < self.total < MIN_TOTAL_FOR_HIGH_CEILING

    @property
    def confidence_ceiling(self) -> str:
        if self.inconsistent:
            return CEILING_NONE
        if self.total <= 0 or self.measured <= 0:
            return CEILING_NONE
        ceiling = CEILING_LOW
        for threshold, candidate in _CEILING_THRESHOLDS:
            if self.ratio >= threshold:
                ceiling = candidate
                break
        # « 1/1 = 100 % » ne vaut pas une couverture complete : un denominateur
        # minuscule rend le ratio bruyant. Defaut demontre le 2026-07-30 —
        # chain_audit annoncait un plafond COMPLETE sur UN seul artefact.
        if self.total < MIN_TOTAL_FOR_HIGH_CEILING:
            ceiling = weakest_ceiling([ceiling, CEILING_MEDIUM])
        return ceiling

    @property
    def unmeasured(self) -> int:
        return max(0, self.total - self.measured)

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "measured": self.measured,
            "total": self.total,
            "unmeasured": self.unmeasured,
            "ratio": round(self.ratio, 6),
            "confidence_ceiling": self.confidence_ceiling,
            "capped_by_small_denominator": self.capped_by_small_denominator,
            "inconsistent": self.inconsistent,
        }

    def sentence(self) -> str:
        """Phrase à recopier dans un rapport — le plafond y est inséparable du ratio."""
        suffixe = ""
        if self.inconsistent:
            suffixe = " [COMPTEUR INCOHERENT]"
        elif self.capped_by_small_denominator:
            suffixe = f" [plafonne : denominateur < {MIN_TOTAL_FOR_HIGH_CEILING}]"
        return (
            f"{self.subject or 'couverture'} : {self.measured}/{self.total} "
            f"({self.ratio:.2%}) — plafond de confiance {self.confidence_ceiling}"
            f"{suffixe}"
        )


def weakest_ceiling(ceilings: Iterable[str]) -> str:
    """Plafond le plus contraignant d'un ensemble — maillon faible (§ 3).

    Une chaîne dont une étape est plafonnée à FAIBLE est plafonnée à FAIBLE,
    quel que soit le soin apporté aux autres étapes.
    """
    worst = CEILING_FULL
    for ceiling in ceilings:
        if ceiling not in CEILING_ORDER:
            return CEILING_NONE
        if CEILING_ORDER.index(ceiling) < CEILING_ORDER.index(worst):
            worst = ceiling
    return worst


@dataclass(frozen=True)
class CeilingBreakdown:
    """Deux plafonds distincts, puis leur composition — ils ne disent PAS la même chose.

    - `coverage_ceiling` répond : « **combien** ai-je mesuré ? » C'est une
      question d'étendue. 40 % d'un domaine mesuré plafonne à MOYENNE même si
      tout ce qui a été mesuré est impeccable.
    - `weakest_link_ceiling` répond : « **quel est mon pire élément** ? » C'est
      une question de qualité locale. Un seul composant invalidé plafonne à
      AUCUNE même si la couverture est complète.

    Les confondre en un seul nombre efface l'information la plus utile : savoir
    s'il faut MESURER PLUS ou CORRIGER CE QUI EST DÉJÀ MESURÉ. Deux actions
    différentes, deux plafonds différents.
    """

    coverage_ceiling: str
    weakest_link_ceiling: str
    #: TROISIÈME composante, ajoutée le 2026-07-30 : l'adoption était repliée dans
    #: le slot COUVERTURE, et le conseil rendu pouvait donc être « mesurer plus »
    #: alors que le vrai problème était « personne n'utilise le mécanisme ».
    #: Trois questions, trois actions différentes.
    adoption_ceiling: Optional[str] = None

    @property
    def _components(self) -> dict:
        parts = {
            "COUVERTURE": self.coverage_ceiling,
            "MAILLON FAIBLE": self.weakest_link_ceiling,
        }
        if self.adoption_ceiling is not None:
            parts["ADOPTION"] = self.adoption_ceiling
        return parts

    @property
    def invalid_components(self) -> list[str]:
        """Composantes dont la valeur n'appartient pas à la grille."""
        return [
            nom for nom, val in self._components.items() if val not in CEILING_ORDER
        ]

    @property
    def final(self) -> str:
        return weakest_ceiling(list(self._components.values()))

    @property
    def binding_reason(self) -> str:
        """Ce qui contraint — donc l'action à mener. Trois causes, trois actions.

        Une valeur hors grille fabriquait un `final` absent de toutes les
        composantes et une raison mensongère ; elle est désormais nommée. Et deux
        plafonds au maximum n'annoncent plus « une contrainte » là où il n'y en a
        aucune (défauts démontrés le 2026-07-30).
        """
        invalides = self.invalid_components
        if invalides:
            return (
                "valeur de plafond INVALIDE pour : "
                + ", ".join(invalides)
                + " — le plafond final est dégradé par précaution, pas mesuré"
            )
        if self.final == CEILING_FULL:
            return "aucune contrainte : toutes les composantes sont au maximum"
        contraignantes = [n for n, v in self._components.items() if v == self.final]
        actions = {
            "COUVERTURE": "mesurer plus, le mesuré est sain",
            "MAILLON FAIBLE": "corriger, mesurer plus n'aidera pas",
            "ADOPTION": "faire ADOPTER le mécanisme, il n'est pas utilisé",
        }
        if len(contraignantes) > 1:
            return "contraint à égalité par : " + ", ".join(contraignantes)
        nom = contraignantes[0]
        return f"contraint par {nom} — {actions[nom]}"

    def to_dict(self) -> dict:
        payload = {
            "coverage_ceiling": self.coverage_ceiling,
            "weakest_link_ceiling": self.weakest_link_ceiling,
            "final": self.final,
            "binding_reason": self.binding_reason,
        }
        if self.adoption_ceiling is not None:
            payload["adoption_ceiling"] = self.adoption_ceiling
        return payload


# ── Bloc de preuve — CONSTRUCTEUR UNIQUE ──────────────────────────────────────

#: Clé sous laquelle un artefact porte sa preuve. Une seule, ici.
PROOF_KEY = "proof"


def create_proof(
    *,
    tool_path: Path,
    inputs: Sequence[InputRef] = (),
    population: Optional[Mapping] = None,
    notes: str = "",
    body: object = None,
    generated_at: Optional[str] = None,
    repo_root: Optional[Path] = None,
    artifact: Optional[str] = None,
) -> dict:
    """**Constructeur UNIQUE d'un bloc de preuve.** Ne jamais écrire ce dict à la main.

    Précédent qui impose cette règle : le dépôt a déjà vu la même structure
    dupliquée dériver **deux** fois — trois loaders de dataset rendant trois
    populations (INV-DATASET-001), puis quatre formules sous le nom « Sharpe »
    (INV-METRIC-001). La dérive de blocs `proof` n'a, elle, encore JAMAIS été
    observée : cet invariant applique à une structure neuve une propriété déjà
    démontrée deux fois sur des structures voisines. C'est une extrapolation
    assumée, pas un constat.

    `body` : le corps de l'artefact **sans** son bloc de preuve. Son empreinte
    est calculée ici et nulle part ailleurs, ce qui garantit que tous les
    producteurs hachent la même chose de la même façon.

    `artifact` : chemin relatif au dépôt de la sortie que cette preuve décrit.
    Sans lui, deux artefacts cohérents sont interchangeables sans que rien ne le
    voie — défaut trouvé par vérification adversariale le 2026-07-30.
    `tool_path` est également enregistré en **relatif au dépôt** quand c'est
    possible : la recherche par nom seul classait « rompu » un producteur
    honnête vivant hors de `tools/` et `scripts/`.
    """
    prov = build_provenance(
        tool_path=tool_path,
        inputs=inputs,
        population=population,
        notes=notes,
        generated_at=generated_at,
    )
    payload = prov.to_dict()
    root = repo_root or REPO_ROOT
    try:
        payload["tool_path"] = tool_path.resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        payload["tool_path"] = None
    payload["artifact"] = artifact
    if body is not None:
        payload["output_sha256"] = sha256_json(body)

    # POINT UNIQUE D'INSTRUMENTATION. Tout ce qui suit est ajouté ici et nulle
    # part ailleurs : une évolution du format ne touchera jamais un producteur.
    # C'est l'avantage que `load_clean_trades()` avait apporté aux datasets.
    payload["min_compatible_version"] = MIN_COMPATIBLE_PROOF_VERSION
    payload["proof_id"] = _proof_id(payload)
    return payload


def _proof_id(payload: Mapping) -> str:
    """Identifiant DÉTERMINISTE d'une preuve — dérivé de son contenu.

    Pas un UUID aléatoire : deux exécutions identiques doivent produire le même
    identifiant, sinon la reproductibilité serait invérifiable. Calculé sur les
    champs qui définissent la transformation, jamais sur la preuve entière (qui
    contiendrait alors son propre identifiant).
    """
    graine = {
        "tool_sha256": payload.get("tool_sha256"),
        "output_sha256": payload.get("output_sha256"),
        "inputs": payload.get("inputs"),
        "artifact": payload.get("artifact"),
        "generated_at": payload.get("generated_at"),
    }
    return sha256_json(graine)[:32]


def attach_proof(
    body: Mapping,
    *,
    tool_path: Path,
    inputs: Sequence[InputRef] = (),
    population: Optional[Mapping] = None,
    notes: str = "",
    generated_at: Optional[str] = None,
    repo_root: Optional[Path] = None,
    artifact: Optional[str] = None,
) -> dict:
    """Retourne une copie de `body` portant son bloc de preuve sous `PROOF_KEY`.

    Point d'entrée recommandé pour un producteur : une ligne, aucune décision à
    prendre sur ce qui est haché. Si `body` contient déjà une preuve, elle est
    ignorée pour le calcul de l'empreinte — sinon ajouter une preuve changerait
    l'empreinte de ce qu'elle prouve, et aucune vérification ne serait possible.
    """
    clean = {k: v for k, v in body.items() if k != PROOF_KEY}
    proof = create_proof(
        tool_path=tool_path,
        inputs=inputs,
        population=population,
        notes=notes,
        body=clean,
        generated_at=generated_at,
        repo_root=repo_root,
        artifact=artifact,
    )
    result = dict(clean)
    result[PROOF_KEY] = proof
    return result


#: Champs sans lesquels un bloc `proof` ne prouve RIEN. Exiger leur PRÉSENCE est
#: ce qui distingue « porte une preuve » de « porte un dictionnaire nommé proof ».
#: Défaut MAJEUR corrigé le 2026-07-30 : un bloc réduit à
#: {schema_version, generated_at} obtenait PREUVE=ok, proven=True et un plafond
#: COMPLETE — l'axe ADOPTION se gagnait donc sans aucune empreinte.
REQUIRED_PROOF_FIELDS = (
    "schema_version",
    "generated_at",
    "tool_sha256",
    "output_sha256",
)


def artifact_has_proof(payload: object) -> bool:
    """L'artefact porte-t-il un bloc de preuve EXPLOITABLE ? (mesure d'ADOPTION)

    Exploitable = les champs qui rendent la vérification possible sont présents.
    Un bloc incomplet compte comme NON adopté : c'est plus honnête que de
    l'annoncer prouvé puis de ne rien vérifier.
    """
    if not isinstance(payload, Mapping):
        return False
    proof = payload.get(PROOF_KEY)
    if not isinstance(proof, Mapping):
        return False
    return all(proof.get(champ) for champ in REQUIRED_PROOF_FIELDS)


def verify_artifact(
    payload: object,
    *,
    repo_root: Optional[Path] = None,
    expected_artifact: Optional[str] = None,
) -> list[str]:
    """Vérifie un artefact complet — preuve comprise — et rend les écarts.

    Sépare l'artefact en corps + preuve exactement comme `attach_proof` les a
    assemblés. Un artefact sans preuve n'est pas « invalide » : il est
    **non prouvé**, et le message le dit, parce que la majorité des artefacts du
    dépôt sont dans ce cas et qu'un faux verdict d'invalidité les noierait.

    `expected_artifact` : chemin attendu. Le fournir détecte la SUBSTITUTION
    d'un artefact cohérent par un autre, invisible autrement.
    """
    if not isinstance(payload, Mapping):
        return ["artefact absent ou de type inattendu"]
    proof = payload.get(PROOF_KEY)
    if not isinstance(proof, Mapping):
        return ["artefact NON PROUVÉ : aucun bloc `proof` (adoption manquante)"]
    manquants = [c for c in REQUIRED_PROOF_FIELDS if not proof.get(c)]
    if manquants:
        return [
            "artefact NON PROUVÉ : bloc `proof` incomplet, champs manquants — "
            + ", ".join(manquants)
        ]
    body = {k: v for k, v in payload.items() if k != PROOF_KEY}
    issues = verify_provenance(proof, body=body, repo_root=repo_root)
    if expected_artifact is not None:
        declared = proof.get("artifact")
        if not declared:
            issues.append(
                "la preuve ne nomme pas l'artefact qu'elle décrit — une "
                "substitution par un autre artefact cohérent serait invisible"
            )
        elif declared != expected_artifact:
            issues.append(
                f"la preuve décrit `{declared}` et non `{expected_artifact}` : "
                f"artefact substitué ou déplacé"
            )
    return issues


def proof_adoption(payloads: Iterable[object], *, subject: str = "") -> Coverage:
    """Couverture d'ADOPTION : combien d'artefacts portent réellement une preuve.

    Cinquième axe, indépendant des quatre autres : un protocole parfait avec 0 %
    d'adoption équivaut à son absence. Aucune règle de validité, de puissance, de
    transformation ou d'indépendance ne mesure cet écart entre ce qui est
    **défini** et ce qui est **utilisé**.
    """
    # Un artefact ABSENT (None) n'est pas « non adopte » : il n'y a rien a
    # prouver. L'inclure au denominateur melangeait deux manques differents —
    # incoherence avec chain_audit, relevee par attaque adversariale.
    items = [p for p in payloads if p is not None]
    return Coverage(
        measured=sum(1 for p in items if artifact_has_proof(p)),
        total=len(items),
        subject=subject or "artefacts portant un bloc de preuve",
    )


# ── VALIDITÉ DU MÉCANISME — sixième famille ───────────────────────────────────
#
# Un mécanisme peut être ADOPTÉ, EXÉCUTÉ et parfaitement TRAÇABLE tout en étant
# incapable de détecter ce qu'il prétend détecter. Ce n'est ni un problème
# d'adoption, ni de transformation : c'est la VALIDITÉ de l'instrument.
#
# Précédent (2026-07-30) : `output_sha256` absent faisait sauter le contrôle du
# corps, et l'axe ADOPTION annonçait « 1/1 = 100 % » sur un mécanisme qui ne
# vérifiait rien. Quatre indicateurs verts, une garantie nulle.
#
# D'où l'auto-test ci-dessous : le mécanisme doit prouver qu'il DÉTECTE des
# altérations connues. Tant qu'il ne l'a pas prouvé, toute garantie qui en
# dérive est INVALIDE — pas « verte », pas « rouge » : invalide.

#: Version minimale de schéma qu'un consommateur doit savoir lire.
MIN_COMPATIBLE_PROOF_VERSION = 1

VALIDITY_OK = "VALIDE"
VALIDITY_BROKEN = "MECANISME_INVALIDE"


@dataclass(frozen=True)
class ValidityReport:
    """Le mécanisme de preuve détecte-t-il ce qu'il prétend détecter ?"""

    status: str
    cases_total: int
    cases_passed: int
    failures: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.status == VALIDITY_OK

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "cases_total": self.cases_total,
            "cases_passed": self.cases_passed,
            "failures": self.failures,
        }


def self_test(repo_root: Optional[Path] = None) -> ValidityReport:
    """Auto-test du mécanisme de preuve — cas POSITIFS **et** NÉGATIFS.

    Un mécanisme qui ne rend jamais d'écart passerait tous les cas positifs. La
    validité exige donc surtout des cas négatifs : des artefacts DONT ON SAIT
    qu'ils sont altérés, et que le mécanisme doit refuser.

    Exécuté en mémoire, sans toucher au disque du dépôt : cet auto-test doit
    pouvoir tourner avant toute lecture d'artefact réel.
    """
    import tempfile

    failures: list[str] = []
    total = 0
    passed = 0

    with tempfile.TemporaryDirectory() as tmp:
        racine = Path(tmp)
        outil = racine / "producteur_de_test.py"
        outil.write_text("VERSION = 1\n", encoding="utf-8")
        entree = racine / "entree.jsonl"
        entree.write_text('{"a": 1}\n', encoding="utf-8")

        corps = {"verdict": "NO_GO", "n": 121}
        sain = attach_proof(
            corps,
            tool_path=outil,
            inputs=[InputRef("entree.jsonl", sha256_file(entree), n_records=1)],
            population={"n_canonical": 121},
            repo_root=racine,
            artifact="sortie.json",
        )

        def _cas(nom: str, condition: bool) -> None:
            nonlocal total, passed
            total += 1
            if condition:
                passed += 1
            else:
                failures.append(nom)

        # POSITIF — un artefact intact doit passer.
        _cas(
            "artefact intact accepté",
            verify_artifact(sain, repo_root=racine, expected_artifact="sortie.json")
            == [],
        )

        # NÉGATIF — corps édité après production.
        falsifie = dict(sain)
        falsifie["verdict"] = "GO"
        _cas(
            "corps falsifié DÉTECTÉ",
            any(
                "modifié après production" in e
                for e in verify_artifact(falsifie, repo_root=racine)
            ),
        )

        # NÉGATIF — empreinte de sortie retirée (le défaut CRITIQUE du 2026-07-30).
        sans_empreinte = dict(sain)
        sans_empreinte[PROOF_KEY] = {
            k: v for k, v in sain[PROOF_KEY].items() if k != "output_sha256"
        }
        _cas(
            "empreinte de sortie manquante DÉTECTÉE",
            verify_artifact(sans_empreinte, repo_root=racine) != [],
        )
        _cas(
            "artefact sans empreinte compté comme NON adopté",
            artifact_has_proof(sans_empreinte) is False,
        )

        # NÉGATIF — bloc forgé minimal (le défaut MAJEUR du 2026-07-30).
        forge = {"verdict": "GO", PROOF_KEY: {"schema_version": 1, "generated_at": "x"}}
        _cas("bloc forgé minimal REFUSÉ", artifact_has_proof(forge) is False)

        # NÉGATIF — entrée modifiée depuis la production.
        entree.write_text('{"a": 2}\n', encoding="utf-8")
        _cas(
            "entrée modifiée DÉTECTÉE",
            any(
                "modifiée depuis la production" in e
                for e in verify_artifact(sain, repo_root=racine)
            ),
        )
        entree.write_text('{"a": 1}\n', encoding="utf-8")

        # NÉGATIF — outil modifié depuis la production.
        outil.write_text("VERSION = 2\n", encoding="utf-8")
        _cas(
            "outil modifié DÉTECTÉ",
            any(
                "autre version du script" in e
                for e in verify_artifact(sain, repo_root=racine)
            ),
        )
        outil.write_text("VERSION = 1\n", encoding="utf-8")

        # NÉGATIF — artefact substitué.
        _cas(
            "substitution d'artefact DÉTECTÉE",
            any(
                "substitué ou déplacé" in e
                for e in verify_artifact(
                    sain, repo_root=racine, expected_artifact="autre.json"
                )
            ),
        )

        # POSITIF — déterminisme : deux constructions identiques, même identifiant.
        rejoue = attach_proof(
            corps,
            tool_path=outil,
            inputs=[InputRef("entree.jsonl", sha256_file(entree), n_records=1)],
            population={"n_canonical": 121},
            repo_root=racine,
            artifact="sortie.json",
            generated_at=sain[PROOF_KEY]["generated_at"],
        )
        _cas(
            "identifiant de preuve déterministe",
            rejoue[PROOF_KEY]["proof_id"] == sain[PROOF_KEY]["proof_id"],
        )

    return ValidityReport(
        status=VALIDITY_OK if not failures else VALIDITY_BROKEN,
        cases_total=total,
        cases_passed=passed,
        failures=failures,
    )
