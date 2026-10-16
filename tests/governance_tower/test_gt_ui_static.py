"""GOV-TOWER-00 GT-M5 — interface à panel unique : contrôles statiques sans navigateur.

Ces tests vérifient la forme des fichiers servis (absence de rendu HTML brut,
de script/style inline, de ressource externe et de bouton d'action) et la
conformité de l'exemple ``sample_run.json`` au contrat ``AgentRun``. Ils ne
prouvent pas le rendu réel dans un navigateur.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from governance_tower.contracts import (
    AgentRun,
    Availability,
    ClaimStatus,
    Discrepancy,
    DiscrepancyClass,
    EvidenceRef,
    Finding,
    Intent,
    MissionProposal,
    Provenance,
    Refusal,
    SentinelAnswer,
    Severity,
    SourceKind,
    SourceStatus,
    Statement,
    ToolCall,
)

UI = Path(__file__).resolve().parents[2] / "governance_tower" / "ui"
INDEX = UI / "index.html"
APP = UI / "app.js"
STYLES = UI / "styles.css"
SAMPLE = UI / "sample_run.json"

SHORTCUTS = {
    "examine_repository": "Examiner le dépôt",
    "examine_host": "Examiner le VPS",
    "compare": "Comparer GitHub et VPS",
    "diagnose": "Rechercher une anomalie",
    "propose_mission": "Proposer une mission",
}
FORBIDDEN_JS = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "localStorage", "sessionStorage", "indexedDB")
FORBIDDEN_ACTIONS = ("deploy", "merge", "restart", "redémarrer", "déployer", "fusionner", "activer l'écriture")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class _Collect(HTMLParser):
    """Collecte balises, attributs et libellés de boutons d'index.html."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.scripts: list[tuple[dict[str, str | None], str]] = []
        self.buttons: list[tuple[dict[str, str | None], str]] = []
        self._script: dict[str, str | None] | None = None
        self._button: dict[str, str | None] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        self.tags.append((tag, d))
        if tag == "script":
            self._script, self._text = d, []
        elif tag == "button":
            self._button, self._text = d, []

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            self.scripts.append((self._script, "".join(self._text)))
            self._script = None
        elif tag == "button" and self._button is not None:
            self.buttons.append((self._button, " ".join("".join(self._text).split())))
            self._button = None

    def handle_data(self, data):
        if self._script is not None or self._button is not None:
            self._text.append(data)


@pytest.fixture(scope="module")
def page() -> _Collect:
    parser = _Collect()
    parser.feed(read(INDEX))
    return parser


# ── Présence ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", [INDEX, APP, STYLES, SAMPLE])
def test_ui_files_present(path):
    assert path.is_file() and path.stat().st_size > 0


# ── Sécurité de app.js ───────────────────────────────────────────────────────


@pytest.mark.parametrize("motif", FORBIDDEN_JS)
def test_app_js_has_no_forbidden_sink(motif):
    assert motif not in read(APP)


def test_app_js_no_string_timer_and_no_external_fetch():
    src = read(APP)
    assert not re.search(r"set(?:Timeout|Interval)\(\s*['\"`]", src)
    for cible in re.findall(r"fetch\(\s*([^,)]+)", src):
        assert cible.strip() in {"URL_STATUT", "URL_QUESTION", "URL_APERCU"}, cible
    for constante, valeur in re.findall(r'const (URL_\w+) = "([^"]*)"', src):
        assert valeur.startswith("/"), (constante, valeur)
    assert "http://" not in src
    # Le seul préfixe https admis sert à décider si un locator devient un lien GitHub.
    assert set(re.findall(r"https://[^\"'\s]*", src)) <= {"https://github.com/", "https://github.com"}
    assert 'rel: "noopener noreferrer"' in src


def test_app_js_sends_required_headers():
    src = read(APP)
    assert '"X-GT-Request": "1"' in src and '"Content-Type": "application/json"' in src
    assert "AbortController" in src and "DELAI_MS = 20000" in src


# ── index.html : CSP compatible, aucun inline ────────────────────────────────


def test_index_has_no_inline_script_style_or_handler(page):
    html = read(INDEX)
    assert not re.search(r"<[^>]*\son[a-z]+\s*=", html, re.IGNORECASE)
    assert not re.search(r"\sstyle\s*=", html, re.IGNORECASE)
    assert "<style" not in html.lower()
    assert "javascript:" not in html.lower()
    assert page.scripts, "app.js doit être chargé"
    for attrs, body in page.scripts:
        assert attrs.get("src") == "/app.js" and not body.strip()
    feuilles = [a.get("href") for t, a in page.tags if t == "link" and a.get("rel") == "stylesheet"]
    assert feuilles == ["/styles.css"]


@pytest.mark.parametrize("path", [INDEX, STYLES])
def test_no_external_url_loaded(path):
    src = read(path)
    assert not re.search(r"(?:https?:)?//[a-z0-9.-]+\.[a-z]{2,}", src, re.IGNORECASE)
    assert "@import" not in src and "url(" not in src


def test_index_lang_and_landmarks(page):
    tags = [t for t, _ in page.tags]
    html_attrs = next(a for t, a in page.tags if t == "html")
    assert html_attrs.get("lang") == "fr"
    for landmark in ("header", "main", "footer"):
        assert landmark in tags
    fil = next(a for t, a in page.tags if a.get("id") == "fil")
    assert fil.get("aria-live") == "polite"
    label = next(a for t, a in page.tags if t == "label")
    assert label.get("for") == "question"


# ── Libellés requis ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "libelle",
    ["GOVERNANCE TOWER", "SENTINEL-01", "READ ONLY", "DÉMO — DONNÉES SYNTHÉTIQUES", "GitHub", "VPS"],
)
def test_required_labels_present(libelle):
    assert libelle in read(INDEX)


def test_footer_note_present():
    assert (
        "Sentinel observe et propose. Aucune action n'est exécutée. Toute opération exige "
        "une décision opérateur hors de cette interface (#286, #315)."
    ) in " ".join(read(INDEX).split())


def test_five_shortcuts_with_contract_ids(page):
    trouves = {a.get("data-shortcut"): texte for a, texte in page.buttons if a.get("data-shortcut")}
    assert trouves == SHORTCUTS


def test_no_action_button_labels(page):
    for _, texte in page.buttons:
        bas = texte.lower()
        assert not any(mot in bas for mot in FORBIDDEN_ACTIONS), texte
    # app.js ne crée aucun bouton d'action et ne contient aucun de ces libellés.
    src = read(APP).lower()
    for mot in FORBIDDEN_ACTIONS:
        assert mot not in src, mot


# ── sample_run.json : conforme au contrat AgentRun ───────────────────────────


def _ev(raw):
    return EvidenceRef.from_dict(raw)


def _rebuild(doc: dict) -> AgentRun:
    a = doc["answer"]
    answer = SentinelAnswer(
        summary=a["summary"],
        statements=tuple(
            Statement(s["text"], ClaimStatus(s["claim_status"]), tuple(s["evidence_ids"])) for s in a["statements"]
        ),
        uncertainties=tuple(a["uncertainties"]),
        discrepancies=tuple(
            Discrepancy(**{**d, "classification": DiscrepancyClass(d["classification"]), "evidence": tuple(map(_ev, d["evidence"]))})
            for d in a["discrepancies"]
        ),
        findings=tuple(
            Finding(
                **{
                    **f,
                    "severity": Severity(f["severity"]),
                    "claim_status": ClaimStatus(f["claim_status"]),
                    "evidence": tuple(map(_ev, f["evidence"])),
                }
            )
            for f in a["findings"]
        ),
        proposals=tuple(
            MissionProposal(**{k: tuple(v) if isinstance(v, list) else v for k, v in p.items()}) for p in a["proposals"]
        ),
        refusals=tuple(Refusal(**r) for r in a["refusals"]),
        untrusted_quotes=tuple(a["untrusted_quotes"]),
    )
    return AgentRun(
        **{
            **doc,
            "intent": Intent(doc["intent"]),
            "tool_calls": tuple(
                ToolCall(**{**t, "availability": Availability(t["availability"])}) for t in doc["tool_calls"]
            ),
            "evidence": tuple(map(_ev, doc["evidence"])),
            "sources": tuple(
                SourceStatus(
                    SourceKind(s["source"]),
                    Availability(s["availability"]),
                    Provenance(s["provenance"]) if s["provenance"] is not None else None,
                    s["collected_at_utc"],
                    s["detail"],
                    s["age_s"],
                )
                for s in doc["sources"]
            ),
            "answer": answer,
        }
    )


def test_sample_run_identity():
    doc = json.loads(read(SAMPLE))
    assert doc["operational_authority"] == "DENIED"
    assert doc["capability"] == "OBSERVE_ONLY"
    assert doc["agent_id"] == "SENTINEL-01"
    assert doc["mode"] == "DEMO"


def test_sample_run_round_trips_through_contract():
    doc = json.loads(read(SAMPLE))
    run = _rebuild(doc)
    assert run.to_dict() == doc


def test_sample_run_is_synthetic_and_covers_every_section():
    doc = json.loads(read(SAMPLE))
    provs = {e["provenance"] for e in doc["evidence"]}
    assert "LIVE_READ" not in provs and "SYNTHETIC" in provs
    for s in doc["sources"]:
        assert s["provenance"] == "SYNTHETIC"
    a = doc["answer"]
    for cle in ("statements", "uncertainties", "discrepancies", "findings", "proposals", "refusals", "untrusted_quotes"):
        assert a[cle], cle
    assert {d["classification"] for d in a["discrepancies"]} >= {"EXPECTED_PINNED_RUNTIME"}
    assert {s["claim_status"] for s in a["statements"]} >= {"OBSERVED", "INFERRED", "NOT_PROVEN"}
    for p in a["proposals"]:
        assert p["authority"] == "NONE" and p["execution"] == "NOT_EXECUTED"


# ── Syntaxe JavaScript (si node est disponible) ──────────────────────────────


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent : vérification syntaxique ignorée")
def test_app_js_syntax_with_node():
    resultat = subprocess.run(
        [shutil.which("node"), "--check", str(APP)], capture_output=True, text=True, timeout=60, check=False
    )
    assert resultat.returncode == 0, resultat.stderr


def test_preview_never_overwrites_the_source_banner():
    src = read(APP)
    apercu = src[src.index("async function chargerApercu"):src.index("// ── Formulaire")]
    assert "rendreRun(donnees, true)" in apercu
    assert "if (!apercu && Array.isArray(run.sources))" in src


def test_banner_shows_measured_age_and_refreshes_status_by_get_only():
    src = read(APP)
    assert "entree.age_s" in src and "consulté il y a" in src
    assert re.search(r"window\.setInterval\(chargerStatut, RAFRAICHIR_STATUT_MS\)", src)
    assert "journal d'audit en échec" in src and "journal d'audit plein" in src
