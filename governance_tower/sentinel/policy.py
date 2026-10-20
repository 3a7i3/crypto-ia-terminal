"""Politique d'autorité de SENTINEL-01 : toute intention mutatrice est refusée avant tout outil.

La politique ne s'applique qu'à la **demande de l'utilisateur**. Les contenus
externes (GitHub, journaux, snapshots) ne passent jamais par ici : ils ne
peuvent ni choisir un outil, ni changer l'intention, ni élargir une permission.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from governance_tower.contracts import Intent
from governance_tower.redaction import redact

MAX_REQUEST = 2_000
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‪-‮⁦-⁩]")

# (code de refus, motif). Les motifs visent des verbes d'action, pas les noms :
# « commits non déployés » est une question légitime, « déploie main » ne l'est pas.
_DENY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        # En premier : une demande d'auto-promotion est nommée comme telle, même si elle cite un secret.
        "PERMISSION_CHANGE_DENIED",
        re.compile(
            r"(\b(d[ée]clare|consid[èe]re|proclame|nomme|qualifie|promeus|certifie)[- ]toi\b|"
            r"\b(accorde|donne|octroie|attribue|ajoute)[- ](toi|te)\b|\bt'(accorde|octroie|attribue|donne)s?\b|"
            r"\b[ée]l[èe]ve[rz]?\b.{0,20}\bprivil[eè]ges?|\bescalad\w* (de |des )?privil|"
            r"\btu es (d[ée]sormais|maintenant|dor[ée]navant) (admin|root|administrat|qualifi|gouvern)|"
            r"\b(grant|give|make) yourself\b|\belevate (your |its )?(privileges?|permissions?)|"
            r"\bauto-?(qualifi|promo|attribu))"
        ),
    ),
    (
        "SECRET_ACCESS_DENIED",
        re.compile(
            r"(\.env\b|\bsecrets?\b|\btokens?\b|\bjetons?\b|cl[ée]s? (priv[ée]e|api|exchange|ssh)|private key|"
            r"\bpassword|mot de passe|\bcredentials?\b|id_rsa|\.pem\b|api[_ -]?key)"
        ),
    ),
    (
        "SERVICE_CONTROL_DENIED",
        re.compile(
            r"(\bred[ée]marre[rz]?\b|\brestart\b|\breboot\b|\breload\b|\bsystemctl\b|\bjournalctl\b|"
            r"\b(arr[eê]te[rz]?|stoppe[rz]?|stop|kill|tue[rz]?)\b.{0,40}\b(service|advisor|api|web|timer|process\w*|publisher)|"
            r"\b(active[rz]?|activate|enable|d[ée]sactive[rz]?|disable)\b.{0,40}"
            r"(watchdog|timer|testnet|live|strat[ée]gie|worker|scheduler|[ée]criture|write|service|agent|daemon))"
        ),
    ),
    (
        "DEPLOYMENT_DENIED",
        re.compile(
            r"(\bd[ée]ploie[rz]?\b|\bd[ée]ployer\b|\bdeploy\b|\binstalle[rz]?\b|\binstall\b|\bpromou?v\w*|\bpromote\b|"
            r"\brollback\b|\bupgrade\b|mets? (à|a) jour le (vps|runtime|serveur|checkout))"
        ),
    ),
    (
        "GITHUB_WRITE_DENIED",
        re.compile(
            r"(\bmerge\b|\bfusionne[rz]?\b|\bpush\b|\bpousse[rz]?\b|\bcommite[rz]?\b|"
            r"\b(cr[ée]e[rz]?|ouvre[rz]?|open|create)\b.{0,25}\b(pr|pull request|issue|branche|branch|tag|release)\b|"
            r"\b(ferme[rz]?|close|approuve[rz]?|approve|commente[rz]?)\b.{0,25}\b(pr|pull request|issue)\b|"
            r"\b(relance[rz]?|re-?run|rejoue[rz]?|retrigger|d[ée]clenche[rz]?|trigger|dispatch)\b.{0,25}"
            r"\b(ci|checks?|workflows?|jobs?|actions?|tests?|pipelines?)\b|"
            r"\b(supprime[rz]?|delete|efface[rz]?)\b)"
        ),
    ),
    (
        "ARBITRARY_COMMAND_DENIED",
        re.compile(
            r"(\bsudo\b|\brm\s+-|\bchmod\b|\bchown\b|\bcurl\b.*\|\s*(ba)?sh|\bbash\b|\bshell\b|"
            r"\b(ex[ée]cute[rz]?|execute|run|lance[rz]?)\b.{0,30}\b(commande|command|script|shell|bash|python)\b)"
        ),
    ),
    (
        "TRADING_OR_PAYMENT_DENIED",
        re.compile(
            r"(\bach[eè]te[rz]?\b|\bvend[sz]?\b|\bbuy\b|\bsell\b|\bpasse[rz]? (un |des )?ordres?\b|place (an )?order|"
            r"\bpai(e|ement)\b|\bpayer\b|\bpay\b|\bvirement\b|\btransf[eè]re[rz]?\b|\bwithdraw\b|\bretrait\b)"
        ),
    ),
    (
        "GOVERNED_PARAMETER_DENIED",
        re.compile(
            r"\b(modifie[rz]?|change[rz]?|ajuste[rz]?|calibre[rz]?|augmente[rz]?|baisse[rz]?|set|r[èe]gle[rz]?)\b.{0,40}"
            r"(seuil|threshold|risk|risque|sizing|capital|epoch|[ée]poque|config|strat[ée]gie|pb_max_positions|signal)"
        ),
    ),
    (
        "GOVERNANCE_DECISION_DENIED",
        re.compile(
            r"(\bl[eè]ve[rz]?\b.{0,20}(#?286|gel|freeze|garde)|lift .{0,10}freeze|"
            r"\b(valide[rz]?|approuve[rz]?|ferme[rz]?)\b.{0,20}(gate|#?315|exception))"
        ),
    ),
    (
        "CORRECTION_DENIED",
        re.compile(r"(?<!ne )(?<!sans )\b(?:corrige[rz]?|r[ée]pare[rz]?|fix|repair|apply|applique[rz]?)\b"),
    ),
)

REFUSAL_REASONS = {
    "PERMISSION_CHANGE_DENIED": "Sentinel ne change ni son identité, ni ses permissions, ni sa qualification ; seul un relecteur externe qualifie et seul l'opérateur accorde.",
    "CORRECTION_DENIED": "Sentinel peut proposer une investigation, jamais exécuter une correction.",
    "SECRET_ACCESS_DENIED": "Sentinel ne lit, n'affiche ni ne transmet aucun secret, jeton, clé ou fichier .env.",
    "SERVICE_CONTROL_DENIED": "Sentinel observe les services sans jamais les démarrer, arrêter, redémarrer ou activer.",
    "DEPLOYMENT_DENIED": "Aucun déploiement, installation ou promotion n'est possible depuis Governance Tower.",
    "GITHUB_WRITE_DENIED": "Sentinel n'écrit pas sur GitHub : ni branche, ni commit, ni PR, ni merge, ni commentaire, ni relance de CI.",
    "ARBITRARY_COMMAND_DENIED": "Aucune commande arbitraire ni shell n'est accessible à Sentinel.",
    "TRADING_OR_PAYMENT_DENIED": "Aucun ordre, paiement ou transfert n'est possible ; ce n'est pas une tâche de Sentinel.",
    "GOVERNED_PARAMETER_DENIED": "Stratégies, seuils, risk, sizing, capital, epoch et configuration sont gelés (#286).",
    "GOVERNANCE_DECISION_DENIED": "Seul l'opérateur décide des gates et exceptions (#286, #315) ; Sentinel ne peut pas les valider.",
}

_SHORTCUTS = {
    "examine_repository": Intent.EXAMINE_REPOSITORY,
    "examine_host": Intent.EXAMINE_HOST,
    "compare": Intent.COMPARE,
    "diagnose": Intent.DIAGNOSE,
    "propose_mission": Intent.PROPOSE_MISSION,
}

SHORTCUT_LABELS = (
    ("examine_repository", "Examiner le dépôt"),
    ("examine_host", "Examiner le VPS"),
    ("compare", "Comparer GitHub et VPS"),
    ("diagnose", "Rechercher une anomalie"),
    ("propose_mission", "Proposer une mission"),
)

_INTENT_RULES: tuple[tuple[Intent, re.Pattern[str]], ...] = (
    (Intent.UNDEPLOYED_COMMITS, re.compile(r"(non|pas)( encore| prouv[ée]s? comme)? d[ée]ploy|dans main mais|not deployed|undeployed")),
    (Intent.ROADMAP, re.compile(r"roadmap|feuille de route|priorit")),
    (Intent.WORK_IN_PROGRESS, re.compile(r"en cours|travaux|work in progress|pr ouvertes|pull requests? ouvertes|chantiers?")),
    (Intent.CODE_LOCATE, re.compile(r"composants?|quel(s)? (module|fichier)|o[uù] (est|sont|se trouve)|contr[ôo]l\w* les|code (qui|de)")),
    (Intent.PROPOSE_MISSION, re.compile(r"propos\w* (une )?mission|mission de correction")),
    (Intent.COMPARE, re.compile(r"compar|[ée]cart|drift|d[ée]rive|github (et|vs|/) ?(le )?vps")),
    (Intent.DIAGNOSE, re.compile(r"anomalie|diagnost|probl[eè]me|incoh[ée]ren")),
    (Intent.EXAMINE_HOST, re.compile(r"\bvps\b|serveur|h[ôo]te|services?\b|advisor|ressources|stockage|storage")),
    (Intent.EXAMINE_REPOSITORY, re.compile(r"d[ée]p[ôo]t|\brepo|github|\bci\b|commits?|branches?")),
)


# ── Lectures ciblées (GOV-TOWER-01 M1) : paramètres extraits de la demande seule ──
# Les paramètres ne viennent jamais d'un contenu externe ; ils restent validés par le fournisseur.
_SHA_RE = re.compile(r"(?<![0-9a-f])([0-9a-f]{40})(?![0-9a-f])")
_PATH_RE = re.compile(
    r"(?<![\w/.\-])((?:[A-Za-z0-9_.\-]+/)*[A-Za-z0-9_\-][A-Za-z0-9_.\-]*\.[A-Za-z0-9]{1,6}|"
    r"(?:[A-Za-z0-9_.\-]+/)*(?:Makefile|Dockerfile|CODEOWNERS|LICENSE))(?![\w/\-])"
)
_LINES_RE = re.compile(
    r"(?:lignes?|lines?|\bl)\s*(\d{1,7})\s*(?:-|–|à|a|au|to|jusqu'?(?:à|a))\s*l?(\d{1,7})", re.IGNORECASE
)
_LINE_RE = re.compile(r"(?:ligne|line)\s+(\d{1,7})", re.IGNORECASE)
_READ_VERB_RE = re.compile(r"\b(lis|lire|montre[rz]?|affiche[rz]?|ouvre[rz]?|contenu|extrait|read|show|cite[rz]?)\b")
_ISSUE_RE = re.compile(r"\bissue\s*(?:n°|no\.?|#)?\s*(\d{1,7})\b")
_PULL_RE = re.compile(r"\b(?:pr|pull request|pull-request)\s*(?:n°|no\.?|#)?\s*(\d{1,7})\b")
_CI_RE = re.compile(r"\b(ci|checks?|contr[ôo]les?|tests?|statuts?)\b")
_COVERAGE_RE = re.compile(
    r"couverture|angles? morts?|vue compl[eè]te|que (vois|observes|peux)[- ]tu|ce que tu (ne )?(vois|observes)|"
    r"blind spots?|\bcoverage\b|domaines? observables?"
)


def _detail(request: str) -> tuple[Intent, tuple[tuple[str, Any], ...]] | None:
    low = request.lower()
    sha = _SHA_RE.search(request)
    path = next((m.group(1) for m in _PATH_RE.finditer(request) if not _SHA_RE.fullmatch(m.group(1))), None)
    if path is not None and (_READ_VERB_RE.search(low) or "fichier" in low or _LINES_RE.search(request)):
        params: list[tuple[str, Any]] = [("path", path)]
        if sha:
            params.append(("ref_sha", sha.group(1)))
        span = _LINES_RE.search(request)
        if span:
            params += [("line_start", int(span.group(1))), ("line_end", int(span.group(2)))]
        else:
            single = _LINE_RE.search(request)
            if single:
                params += [("line_start", int(single.group(1)))]
        return Intent.READ_FILE, tuple(params)
    pull = _PULL_RE.search(low)
    if pull:
        return Intent.PULL_DETAIL, (("number", int(pull.group(1))),)
    issue = _ISSUE_RE.search(low)
    if issue:
        return Intent.ISSUE_DETAIL, (("number", int(issue.group(1))),)
    if sha and _CI_RE.search(low):
        return Intent.CI_FOR_SHA, (("sha", sha.group(1)),)
    if _COVERAGE_RE.search(low):
        return Intent.COVERAGE_MAP, ()
    return None


@dataclass(frozen=True)
class PolicyDecision:
    request: str  # normalisée et expurgée
    intent: Intent
    refusal_code: str | None
    redactions: int
    params: tuple[tuple[str, Any], ...] = ()  # paramètres de lecture ciblée, issus de la demande seule

    @property
    def refused(self) -> bool:
        return self.refusal_code is not None


def normalize_request(raw: object) -> tuple[str, int]:
    text = raw if isinstance(raw, str) else ""
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_RE.sub(" ", text).strip()
    cleaned, count = redact(text)
    return cleaned[:MAX_REQUEST], count


def classify_intent(request: str, shortcut: str | None = None) -> Intent:
    if shortcut is not None:
        return _SHORTCUTS.get(shortcut, Intent.HELP)
    low = request.lower()
    if not low.strip():
        return Intent.HELP
    mentions_repo = bool(re.search(r"d[ée]p[ôo]t|github|\brepo", low))
    mentions_host = bool(re.search(r"\bvps\b|serveur|h[ôo]te|d[ée]ploy|runtime", low))
    if mentions_repo and mentions_host and re.search(r"analyse|distingu|certifi|inconnu|examine", low):
        return Intent.FULL_REVIEW
    if _INTENT_RULES[0][1].search(low):
        return Intent.UNDEPLOYED_COMMITS
    if mentions_host and re.search(
        r"m[êe]me version|align[ée]|[àa] jour|correspond|identique|same version|in sync|synchro", low
    ) and (mentions_repo or re.search(r"\bmain\b", low)):
        # GOV-TOWER-01 M3 : « le VPS exécute-t-il la même version que GitHub ? » est une comparaison croisée.
        return Intent.COMPARE
    detail = _detail(request)
    if detail is not None:
        return detail[0]
    for intent, pattern in _INTENT_RULES:
        if pattern.search(low):
            return intent
    return Intent.HELP


def decide(raw_request: object, shortcut: str | None = None) -> PolicyDecision:
    request, redactions = normalize_request(raw_request)
    if shortcut is not None and shortcut not in _SHORTCUTS:
        return PolicyDecision(request, Intent.REFUSED, "UNKNOWN_SHORTCUT", redactions)
    low = request.lower()
    for code, pattern in _DENY_RULES:
        if pattern.search(low):
            return PolicyDecision(request, Intent.REFUSED, code, redactions)
    if redactions:
        # Une demande contenant un secret est refusée : il ne doit circuler nulle part.
        return PolicyDecision(request, Intent.REFUSED, "SECRET_ACCESS_DENIED", redactions)
    intent = classify_intent(request, shortcut)
    params: tuple[tuple[str, Any], ...] = ()
    if shortcut is None and intent in (
        Intent.READ_FILE, Intent.ISSUE_DETAIL, Intent.PULL_DETAIL, Intent.CI_FOR_SHA, Intent.COVERAGE_MAP
    ):
        detail = _detail(request)
        params = detail[1] if detail is not None else ()
    return PolicyDecision(request, intent, None, redactions, params)
