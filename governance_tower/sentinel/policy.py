"""Politique d'autorité de SENTINEL-01 : toute intention mutatrice est refusée avant tout outil.

La politique ne s'applique qu'à la **demande de l'utilisateur**. Les contenus
externes (GitHub, journaux, snapshots) ne passent jamais par ici : ils ne
peuvent ni choisir un outil, ni changer l'intention, ni élargir une permission.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from governance_tower.contracts import Intent
from governance_tower.redaction import redact

MAX_REQUEST = 2_000
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‪-‮⁦-⁩]")

# (code de refus, motif). Les motifs visent des verbes d'action, pas les noms :
# « commits non déployés » est une question légitime, « déploie main » ne l'est pas.
_DENY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
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
)

REFUSAL_REASONS = {
    "SECRET_ACCESS_DENIED": "Sentinel ne lit, n'affiche ni ne transmet aucun secret, jeton, clé ou fichier .env.",
    "SERVICE_CONTROL_DENIED": "Sentinel observe les services sans jamais les démarrer, arrêter, redémarrer ou activer.",
    "DEPLOYMENT_DENIED": "Aucun déploiement, installation ou promotion n'est possible depuis Governance Tower.",
    "GITHUB_WRITE_DENIED": "Sentinel n'écrit pas sur GitHub : ni branche, ni commit, ni PR, ni merge, ni commentaire.",
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
    (Intent.EXAMINE_HOST, re.compile(r"\bvps\b|serveur|h[ôo]te|services?\b|advisor|ressources")),
    (Intent.EXAMINE_REPOSITORY, re.compile(r"d[ée]p[ôo]t|\brepo|github|\bci\b|commits?|branches?")),
)


@dataclass(frozen=True)
class PolicyDecision:
    request: str  # normalisée et expurgée
    intent: Intent
    refusal_code: str | None
    redactions: int

    @property
    def refused(self) -> bool:
        return self.refusal_code is not None


def normalize_request(raw: object) -> tuple[str, int]:
    text = raw if isinstance(raw, str) else ""
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_RE.sub(" ", text).strip()[:MAX_REQUEST]
    return redact(text)


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
    return PolicyDecision(request, classify_intent(request, shortcut), None, redactions)
