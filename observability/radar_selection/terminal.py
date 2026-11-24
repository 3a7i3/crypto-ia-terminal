"""RADAR terminal: headless CLI and optional line shell over the offline engine.

    python -m observability.radar_selection --fixture calm status
    python -m observability.radar_selection --fixture calm --state-dir DIR select mexc:spot:SOL/USDT
    printf 'status\\ncandidates\\nquit\\n' | python -m observability.radar_selection --fixture calm shell

The process installs an audit hook before any work: every socket, subprocess,
fork or exec is refused, and every file write outside ``--state-dir`` is
refused. Without ``--state-dir`` nothing at all is written. The offline mode
is enforced by this hook, not only printed on the screen.

Exit codes: 0 done, 2 command refused, 3 input refused, 4 usage or state error.
"""
from __future__ import annotations

import os
import shlex
import sys
import textwrap
from pathlib import Path

from . import contract as c
from .fixture import RadarRefusal, canonical

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
NAMED_FIXTURES = {
    "calm": "r0_syn_01_calm.json",
    "volatile": "r0_syn_02_volatile.json",
    "gaps": "r0_syn_03_active_gaps.json",
    "incoherent": "r0_syn_04_incoherent.json",
}
NARROW = 60
MIN_WIDTH = 40
MAX_WIDTH = 120
EXIT_OK, EXIT_REFUSED, EXIT_INPUT, EXIT_USAGE = 0, 2, 3, 4


class UsageError(Exception):
    pass


# ------------------------------------------------------------------ offline guard

_BLOCKED_PREFIXES = ("socket.", "subprocess.", "os.system", "os.exec", "os.posix_spawn", "os.spawn",
                     "os.fork", "os.forkpty", "pty.spawn", "urllib.Request", "http.client.", "ftplib.",
                     "smtplib.", "imaplib.", "poplib.", "nntplib.", "telnetlib.", "webbrowser.")
_PATH_EVENTS = {"os.remove": (0,), "os.rename": (0, 1), "os.mkdir": (0,), "os.rmdir": (0,),
                "os.chmod": (0,), "os.chown": (0,), "os.truncate": (0,), "os.symlink": (0, 1),
                "os.link": (0, 1), "os.utime": (0,), "shutil.rmtree": (0,), "shutil.move": (0, 1),
                "shutil.copyfile": (1,), "shutil.copytree": (1,)}
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_GUARD = {"installed": False, "root": None, "blocked": [], "read_roots": None, "code_roots": []}
# Under the import directories only code may be read: sys.path holds the working
# directory, which must not open every data file below it.
_CODE_SUFFIXES = (".py", ".pyc", ".so", ".pyd", ".pth", ".zip")


def _is_code(path) -> bool:
    try:
        return os.fsdecode(os.fspath(path)).endswith(_CODE_SUFFIXES)
    except TypeError:
        return False


def _inside(path, root) -> bool:
    if root is None or isinstance(path, int):
        return isinstance(path, int)
    try:
        real = os.path.realpath(os.fsdecode(os.fspath(path)))
    except TypeError:
        return False
    return real == root or real.startswith(root + os.sep)


def _hook(event, args):
    if event.startswith(_BLOCKED_PREFIXES):
        _GUARD["blocked"].append(event)
        raise PermissionError(f"RADAR_OFFLINE_GUARD:{event}")
    root = _GUARD["root"]
    if event == "open":
        path, mode, flags = (tuple(args) + (None, None, None))[:3]
        writing = (isinstance(mode, str) and any(ch in mode for ch in "wax+")) or \
                  (isinstance(flags, int) and flags & _WRITE_FLAGS)
        if writing and not _inside(path, root):
            _GUARD["blocked"].append(event)
            raise PermissionError("RADAR_WRITE_OUTSIDE_STATE_DIR")
        readable = _GUARD["read_roots"]
        if not writing and readable is not None and isinstance(path, (str, bytes, os.PathLike)) \
                and not any(_inside(path, r) for r in readable) \
                and not (_is_code(path) and any(_inside(path, r) for r in _GUARD["code_roots"])):
            _GUARD["blocked"].append(event)
            raise PermissionError("RADAR_READ_OUTSIDE_EVIDENCE_ROOT")
    elif event in _PATH_EVENTS:
        for i in _PATH_EVENTS[event]:
            if i < len(args) and not _inside(args[i], root):
                _GUARD["blocked"].append(event)
                raise PermissionError(f"RADAR_WRITE_OUTSIDE_STATE_DIR:{event}")


def _code_roots() -> list:
    """Directories the interpreter imports code from (sys.path and the installation prefixes)."""
    roots = set()
    for entry in [*sys.path, sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix]:
        try:
            real = os.path.realpath(entry or os.getcwd())
        except (TypeError, ValueError, OSError):
            continue
        if os.path.isdir(real):
            roots.add(real)
    return sorted(roots)


def install_offline_guard(state_dir: Path | None, read_roots: list | None = None) -> None:
    """Irreversible for the process: network, processes and outside writes refused.

    With ``read_roots`` (R1-B, ``--evidence-root``) reads are also refused outside
    those roots and ``--state-dir``, except code files (``_CODE_SUFFIXES``) under
    the directories code is imported from.
    """
    sys.dont_write_bytecode = True
    root = None
    if state_dir is not None:
        state_dir = Path(state_dir)
        if not state_dir.exists():
            state_dir.mkdir(mode=0o700)
        if not state_dir.is_dir():
            raise UsageError("STATE_DIR_NOT_A_DIRECTORY")
        root = os.path.realpath(state_dir)
    _GUARD["root"] = root
    if read_roots is not None:
        _GUARD["read_roots"] = sorted({os.path.realpath(r) for r in read_roots} | ({root} if root else set()))
        _GUARD["code_roots"] = _code_roots()
    if not _GUARD["installed"]:
        sys.addaudithook(_hook)
        _GUARD["installed"] = True


# ------------------------------------------------------------------ rendering

class Screen:
    def __init__(self, width: int):
        self.width = max(MIN_WIDTH, min(MAX_WIDTH, width))
        self.narrow = self.width < NARROW
        self.lines: list[str] = []

    def add(self, text: str = "", indent: int = 0) -> None:
        if not text:
            self.lines.append("")
            return
        pad = " " * indent
        self.lines.extend(textwrap.wrap(text, width=self.width, initial_indent=pad,
                                        subsequent_indent=pad + "  ", break_long_words=True,
                                        break_on_hyphens=False) or [""])

    def kv(self, label: str, value, indent: int = 0) -> None:
        self.add(f"{label}: {value}", indent)

    def title(self, text: str) -> None:
        self.add("")
        self.add(text.upper())

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _short(h: str | None) -> str:
    return "—" if not h else h[:12] + "…"


def _market_line(m: dict) -> str:
    return f"{m['venue'].upper()} | {m['market_type']} | {m['base'] or '?'}/{m['quote'] or '?'}"


def header(s: Screen, ev: dict) -> None:
    s.add("CAT MARKET INTELLIGENCE")
    s.add("RADAR — Surveillance et sélection")
    s.add("")
    mode = ev["mode"]
    s.kv("MODE", f"{mode['evidence']} / OFFLINE")
    if s.narrow:
        s.kv("NETWORK", mode["network"])
        s.kv("L2 COLLECTION", mode["l2_collection"])
        s.kv("PAPER", mode["paper"])
    else:
        s.add(f"NETWORK: {mode['network']} · L2 COLLECTION: {mode['l2_collection']} · PAPER: {mode['paper']}")
    s.kv("DATASET", f"{ev['dataset']['id']} ({ev['dataset']['evidence_kind']}, sha256 {_short(ev['dataset']['sha256'])})")
    if ev["dataset"]["schema"] == c.BATCH_SCHEMA:
        s.kv("LOT", f"{ev['dataset']['schema']} · {ev['dataset']['adapter_version']}")
        s.kv("ADMISSION", f"{ev['dataset']['admission']} (aucune admission C2-C/C2-D)")
    s.kv("CONTRAT", f"{ev['schema_version']} · {ev['rules_version']} · {ev['ranking_version']}")
    s.kv("MISSION", ev["mission"]["id"])


def universe_counts(s: Screen, ev: dict) -> None:
    k = ev["counts"]
    s.title("Univers")
    s.kv("Marchés découverts", k["discovered"])
    s.kv("Autorisés", k["authorized"])
    s.kv("Admis (ADMISSIBLE)", k["admissible"])
    s.kv("À qualifier", k["a_qualifier"])
    s.kv("Inconnus (UNKNOWN)", k["unknown"])
    s.kv("Non admissibles", k["non_admissible"])
    s.kv("Exclus manuellement", k["manually_excluded"])
    if k["retired_or_source_not_current"]:
        s.kv("Retirés / source non courante", k["retired_or_source_not_current"])
    if k["orphan_observations"]:
        s.kv("Observations orphelines", k["orphan_observations"])


def reference(s: Screen, ev: dict) -> None:
    r = ev["reference"]
    s.title("Référence")
    s.add(f"{r['venue'].capitalize()} | {r['market_type']} | {r['base']}/{r['quote']}")
    s.kv("Statut", "NOT YET HISTORICALLY ADMITTED")
    s.kv("Radar", f"{r['radar_decision']} ({r['mission']})" + (f" · score {r['score']}" if r["score"] else ""))
    for reason in r["reasons"][:4]:
        s.add(f"- {reason['code']}", 2)
    s.add("Hors classement automatique.", 0)


def candidates(s: Screen, ev: dict, full: bool = False) -> None:
    s.title("Candidats de recherche")
    if not ev["candidates"]:
        s.add(f"Aucun candidat : {ev['candidates_empty_reason']}")
        return
    for x in ev["candidates"]:
        s.add(f"{x['rank']}. {x['market_id']}")
        s.add(_market_line(x) + f" | {x['regime']}", 3)
        s.add(f"Motif : {x['reason']}", 3)
        s.add(f"Statut : PROPOSÉ, NON AUTORISÉ · qualité {x['quality']}", 3)
        if full:
            s.add("Critères disponibles : " + (", ".join(x["criteria_available"]) or "aucun"), 3)
            s.add("Critères manquants : " + (", ".join(x["criteria_missing"]) or "aucun"), 3)
            cost = x["cost"]
            s.add(f"Coût : {cost['basis'] or 'UNKNOWN'} · réseau {cost['network_kib_s'] or '?'} KiB/s · "
                  f"stockage {cost['storage_mib_h'] or '?'} MiB/h · {cost['connections'] if cost['connections'] is not None else '?'} connexion(s)", 3)
            s.add(f"Provenance du coût : {cost['provenance'] or 'UNKNOWN'}", 3)
            s.add("Limites : " + " ; ".join(x["limits"]), 3)
    s.add("Aucune analyse approfondie, collecte L2 ou expérience n'est lancée.")


def manual(s: Screen, ev: dict) -> None:
    m = ev["manual"]
    if not any(m.values()):
        return
    s.title("Contrôle manuel")
    labels = {"selected": "Sélection manuelle", "pinned": "Épinglés", "excluded": "Exclus"}
    for key in ("selected", "pinned", "excluded"):
        for item in m[key]:
            shown = "admissible" if item["presented_as_admissible"] else f"NON présenté comme admissible ({item['decision']})"
            s.add(f"{labels[key]} : {item['market_id']}")
            s.add(shown, 3)


def status(s: Screen, ev: dict) -> None:
    header(s, ev)
    universe_counts(s, ev)
    reference(s, ev)
    candidates(s, ev)
    manual(s, ev)
    s.title("Commandes")
    s.add("universe · scan · candidates · inspect <id> · evidence <id> · select <id> · pin <id> · "
          "exclude <id> · reset · history · status · help · quit")


def universe_list(s: Screen, ev: dict, venue=None, mtype=None, search=None, decision=None) -> None:
    header(s, ev)
    rows = [m for m in ev["markets"]
            if (venue is None or m["venue"] == venue.lower())
            and (mtype is None or m["market_type"] == mtype.upper())
            and (decision is None or m["admissibility"]["decision"] == decision.upper())
            and (search is None or search.upper() in m["market_id"].upper() or search.upper() in m["native_symbol"].upper())]
    s.title(f"Univers ({len(rows)}/{len(ev['markets'])})")
    for m in rows:
        flags = [k.upper() for k, v in m["manual"].items() if v]
        score = m["score"]["value"] if m["score"] else "—"
        s.add(m["market_id"] + (f" [{' '.join(flags)}]" if flags else ""))
        s.add(f"{_market_line(m)} | {m['native_symbol']}", 3)
        s.add(f"{m['admissibility']['decision']} · score {score} · {m['change']}", 3)
        codes = [r["code"] for r in m["admissibility"]["reasons"]]
        if codes:
            s.add("Motifs : " + ", ".join(codes[:4]) + (" …" if len(codes) > 4 else ""), 3)


def _crit_line(name: str, crit: dict) -> str:
    st = crit["state"]
    if name == "l2_quality":
        line = f"{st} · preuve {crit.get('proof')}" + (f" · {crit.get('status')}" if crit.get("status") else "")
        scope = crit.get("scope")
        if crit.get("status") == "VERIFIED_TOP_N" and scope:
            line += (f" · carnet vérifié sur {crit['depth_levels']} niveaux ({scope['verified_by']}), "
                     f"{scope['valid_instants']} instants valides sur {scope['grid_instants']}")
        return line
    if name == "continuity":
        if crit.get("class"):
            return (f"{st} · {crit['class']} {crit['ratio']} ({crit['covered']}/{crit['expected']}) · "
                    f"trous {crit['gaps']} · fraîcheur {crit['freshness']} ({crit['age_ms']} ms)")
        return f"{st} · horodatage {crit.get('time')}"
    if name == "spread_depth":
        sp, dp = crit["spread"], crit["depth"]
        spread = f"spread {sp['median_bps']} bps ({sp['basis']})" if sp.get("median_bps") else f"spread {sp['state']}"
        depth = (f"profondeur {dp.get('bid_quote_10bps')}/{dp.get('ask_quote_10bps')} ({dp.get('basis')})"
                 if dp["state"] != c.CRIT_UNKNOWN else "profondeur UNKNOWN")
        return f"{st} · {spread} · {depth}"
    if name == "activity_volatility":
        a, v = crit["activity"], crit["volatility"]
        act = f"{a['value']} trades" if a["state"] == c.AVAILABLE else "activité UNKNOWN"
        vol = f"vol {v['rms_step_bps']} bps/pas ({v['regime']})" if v["state"] == c.AVAILABLE else "volatilité UNKNOWN"
        return f"{st} · {act} · {vol}"
    if name == "collection_cost":
        if st == c.CRIT_UNKNOWN:
            return st
        return (f"{st} · {crit['basis']} · réseau {crit.get('network_kib_s')} KiB/s · CPU {crit.get('cpu_pct')} % · "
                f"mém. {crit.get('memory_mib')} MiB · stockage {crit.get('storage_mib_h')} MiB/h")
    return f"{st} · régime {crit.get('regime') or 'UNKNOWN'}"


def inspect(s: Screen, ev: dict, m: dict) -> None:
    header(s, ev)
    s.title("Marché")
    s.add(m["market_id"])
    s.add(_market_line(m), 2)
    s.kv("Symbole natif", m["native_symbol"], 2)
    s.kv("Contrat", f"{m['contract_type']} · règlement {m['settlement_asset'] or 'n/a'}", 2)
    lc = m["lifecycle"]
    s.title("Chaîne de qualification")
    s.kv("Découvert", "oui" if lc["discovered"] else "non (cycle précédent)", 2)
    s.kv("Autorisé", {True: "oui", False: "non", None: "UNKNOWN"}[lc["authorized"]]
         + (f" ({lc['authorization_reason']})" if lc["authorization_reason"] else ""), 2)
    s.kv("Source", f"{lc['source_access']}" + (f" ({lc['source_access_reason']})" if lc["source_access_reason"] else ""), 2)
    s.kv("Données récentes", lc["recent_data"], 2)
    s.kv("Admissibilité", f"{lc['scientific']} ({m['admissibility']['mission']})", 2)
    s.kv("Catalogue", f"{m['catalogue']['lifecycle']} · {m['change']}", 2)
    s.title("Six critères")
    labels = {"l2_quality": "1. Qualité L2", "continuity": "2. Continuité", "spread_depth": "3. Spread et profondeur",
              "activity_volatility": "4. Activité et volatilité", "collection_cost": "5. Coût de collecte",
              "diversity": "6. Diversité"}
    for name in c.CRITERIA:
        crit = m["criteria"][name]
        s.add(f"{labels[name]} : {_crit_line(name, crit)}")
        if crit.get("reason"):
            s.add(f"motif : {crit['reason']}", 3)
    s.title("Décision")
    for r in m["admissibility"]["reasons"]:
        s.add(f"- {r['decision']} : {r['code']}", 2)
    if not m["admissibility"]["reasons"]:
        s.add("Aucun motif bloquant pour cette mission.", 2)
    if m["score"]:
        sc = m["score"]
        s.kv("Score", f"{sc['value']}/100 ({sc['quality']}, max atteignable {sc['max_reachable']})", 2)
        s.add("Composantes : " + ", ".join(f"{k} {v}" for k, v in sc["components"].items()), 2)
        if sc["missing"]:
            s.add("Manquantes (0 point, poids non redistribué) : " + ", ".join(sc["missing"]), 2)
    else:
        s.kv("Score", "non calculé (marché non ADMISSIBLE)", 2)


def evidence(s: Screen, ev: dict, m: dict) -> None:
    header(s, ev)
    s.title("Preuves")
    s.add(m["market_id"])
    s.kv("Jeu de données", ev["dataset"]["id"], 2)
    s.kv("SHA-256 du jeu", ev["dataset"]["sha256"], 2)
    cat = m["catalogue"]
    s.kv("Catalogue", f"{cat['source_market']} · {cat['provenance']}", 2)
    s.kv("Statut natif", cat["native_status"] or "—", 2)
    s.kv("Exclusion catalogue", cat["exclusion"] or "aucune", 2)
    s.kv("Collecté (ms)", cat["collected_ms"], 2)
    s.kv("Métadonnées", "courantes" if cat["metadata_current"] else f"non courantes ({cat['metadata_reason']})", 2)
    for name, digest in cat["raw_sha256"].items():
        s.kv(f"SHA-256 {name}", digest, 2)
    o = m["observation"]
    s.kv("Observation", o["evidence_ref"] or f"absente ({o['reason']})", 2)
    if o.get("source_id"):
        src = next((x for x in (ev.get("inputs") or {}).get("sources", []) if x["source_id"] == o["source_id"]), None)
        s.kv("Source", o["source_id"] + (f" · {src['state']} · corpus {src['corpus_id']} · producteur "
                                         f"{src['producer_commit'][:12]}" if src else ""), 2)
    if o["present"]:
        s.kv("Nature du prix", o["price_kind"], 2)
        s.kv("Échantillons", o["sample_count"], 2)
        s.kv("Horodatage", f"{o['time']['state']}" + (f" ({o['time']['reason']})" if o["time"]["reason"] else ""), 2)
        if o["contradictions"]:
            s.kv("Contradictions", ", ".join(o["contradictions"]), 2)
    crit = m["criteria"]
    act = crit["activity_volatility"]["activity"]
    if act.get("evidence_ref"):
        s.kv("Activité", act["evidence_ref"], 2)
    if crit["l2_quality"].get("evidence_ref"):
        s.kv("L2", crit["l2_quality"]["evidence_ref"], 2)
    if crit["collection_cost"].get("provenance"):
        s.kv("Coût", f"{crit['collection_cost']['basis']} · {crit['collection_cost']['provenance']}", 2)
    unknown = [(k, v.get("reason")) for k, v in crit.items() if v["state"] in (c.CRIT_UNKNOWN, c.PARTIAL, c.INVALID)]
    s.title("UNKNOWN et motifs")
    for k, reason in unknown:
        s.add(f"- {k} : {crit[k]['state']} ({reason or 'voir détail'})", 2)
    if not unknown:
        s.add("Aucun critère inconnu.", 2)


def history(s: Screen, entries: list, max_kept: int) -> None:
    s.title(f"Historique (borné à {max_kept})")
    if not entries:
        s.add("Vide.")
    for i, e in enumerate(entries, 1):
        s.add(f"{i}. {e['dataset_id']} · {e['mission']} · {_short(e['evaluation_sha256'])}")
        s.add("Candidats : " + (", ".join(e["candidates"]) or "aucun"), 3)


HELP = [
    ("status", "Tableau de bord : univers, référence, candidats"),
    ("universe [--venue V] [--type T] [--search Q] [--decision D]", "Tous les marchés, filtrables"),
    ("scan", "Évalue l'univers et conserve le résultat (historique borné)"),
    ("candidates", "Les trois propositions détaillées"),
    ("inspect <id>", "Les six critères, la décision et le score"),
    ("evidence <id>", "Références de preuve et motifs UNKNOWN"),
    ("select | unselect <id>", "Choisir un candidat manuel (aucune collecte)"),
    ("pin | unpin <id>", "Épingler un marché (gates inchangées)"),
    ("exclude | include <id>", "Exclure de la sélection automatique"),
    ("reset", "Réinitialiser les préférences"),
    ("history", "Résultats de sélection conservés"),
    ("export", "Évaluation complète en JSON canonique"),
    ("bench [N]", "Mesure locale temps / mémoire / taille"),
    ("help", "Cette aide"),
    ("quit", "Quitter le shell"),
]


def help_screen(s: Screen) -> None:
    s.add("RADAR — commandes")
    for cmd, what in HELP:
        s.add(cmd)
        s.add(what, 3)


# ------------------------------------------------------------------ commands

class Session:
    def __init__(self, fixture: Path | None, state_dir: Path | None, width: int, mission: str,
                 budgets: c.Budgets = c.TEST_BUDGETS, batch: Path | None = None,
                 evidence_root: str | None = None):
        self.fixture = fixture
        self.batch = batch
        self.evidence_root = evidence_root
        self.state_dir = state_dir
        self.width = width
        self.mission = mission
        self.budgets = budgets

    def _raw(self) -> bytes:
        source = self.batch if self.batch is not None else self.fixture
        size = source.stat().st_size
        if size > self.budgets.max_input_bytes:
            raise RadarRefusal(f"INPUT_TOO_LARGE:{size}>{self.budgets.max_input_bytes}")
        return source.read_bytes()

    def _run(self, raw: bytes, prefs: dict) -> dict:
        from .engine import evaluate, evaluate_batch
        if self.batch is None:
            return evaluate(raw, prefs, self.mission, self.budgets)
        from .batch import load_batch, refs
        from .refs import read_all
        blobs = read_all(self.evidence_root, refs(load_batch(raw, self.budgets)["doc"]))
        return evaluate_batch(raw, blobs, prefs, self.mission, self.budgets)

    def evaluate(self) -> dict:
        from .manual import load_preferences
        return self._run(self._raw(), load_preferences(self.state_dir))

    def _market(self, ev: dict, mid: str | None) -> dict:
        if not mid:
            raise UsageError("MARKET_ID_REQUIRED")
        for m in ev["markets"]:
            if m["market_id"] == mid:
                return m
        raise RadarRefusal("UNKNOWN_MARKET:" + mid[:80])

    def run(self, argv: list[str]) -> tuple[int, str]:
        s = Screen(self.width)
        if not argv:
            raise UsageError("COMMAND_REQUIRED")
        cmd, args = argv[0], argv[1:]
        if cmd == "help":
            help_screen(s)
            return EXIT_OK, s.text()
        if cmd == "export":
            return EXIT_OK, canonical(self.evaluate()).decode("utf-8") + "\n"
        if cmd == "bench":
            return EXIT_OK, self.bench(int(args[0]) if args else 5)
        ev = self.evaluate()
        if cmd == "status":
            status(s, ev)
        elif cmd == "universe":
            opts = _options(args, {"--venue", "--type", "--search", "--decision"})
            universe_list(s, ev, opts.get("--venue"), opts.get("--type"), opts.get("--search"), opts.get("--decision"))
        elif cmd == "candidates":
            header(s, ev)
            candidates(s, ev, full=True)
            reference(s, ev)
        elif cmd == "scan":
            from .manual import append_history
            header(s, ev)
            universe_counts(s, ev)
            candidates(s, ev)
            s.title("Résultat")
            s.kv("SHA-256 de l'évaluation", ev["evaluation_sha256"])
            if self.state_dir is None:
                s.add("Historique non conservé (pas de --state-dir).")
            else:
                entries = append_history(self.state_dir, ev, self.budgets.max_kept_evaluations)
                s.add(f"Historique : {len(entries)}/{self.budgets.max_kept_evaluations} évaluations conservées.")
        elif cmd in ("inspect", "evidence"):
            m = self._market(ev, args[0] if args else None)
            (inspect if cmd == "inspect" else evidence)(s, ev, m)
        elif cmd in ("select", "unselect", "pin", "unpin", "exclude", "include", "reset"):
            return self.preference(cmd, args, ev, s)
        elif cmd == "history":
            from .manual import load_history
            history(s, load_history(self.state_dir), self.budgets.max_kept_evaluations)
        else:
            raise UsageError("UNKNOWN_COMMAND:" + cmd[:40])
        return EXIT_OK, s.text()

    def preference(self, cmd: str, args: list, ev: dict, s: Screen) -> tuple[int, str]:
        from .manual import apply, load_preferences, save_preferences
        if self.state_dir is None:
            raise UsageError("STATE_DIR_REQUIRED")
        mid = None
        if cmd != "reset":
            if not args:
                raise UsageError("MARKET_ID_REQUIRED")
            mid = args[0]
        by_id = {m["market_id"]: m for m in ev["markets"]}
        prefs = apply(load_preferences(self.state_dir), cmd, mid, by_id)
        save_preferences(self.state_dir, prefs)
        s.add(f"{cmd.upper()} enregistré (préférence locale, séquence {prefs['seq']}).")
        if mid is not None:
            d = by_id[mid]["admissibility"]["decision"]
            shown = "ADMISSIBLE" if d == c.ADMISSIBLE else f"{d} — NON présenté comme admissible"
            s.kv("Marché", mid)
            s.kv("Admissibilité actuelle", shown)
        s.add("Aucune collecte, aucun job d'observation, aucune expérience n'a été lancé.")
        return EXIT_OK, s.text()

    def bench(self, runs: int) -> str:
        import time
        import tracemalloc
        from .manual import load_preferences
        if not 1 <= runs <= 50:
            raise UsageError("BENCH_RUNS_1_TO_50")
        raw = self._raw()
        prefs = load_preferences(self.state_dir)
        times, peaks, digests = [], [], set()
        size = 0
        for _ in range(runs):
            tracemalloc.start()
            t0 = time.perf_counter()
            ev = self._run(raw, prefs)
            times.append((time.perf_counter() - t0) * 1000)
            peaks.append(tracemalloc.get_traced_memory()[1])
            tracemalloc.stop()
            size = len(canonical(ev))
            digests.add(ev["evaluation_sha256"])
        b = self.budgets
        s = Screen(self.width)
        s.add("RADAR — mesure locale (non représentative de la production)")
        s.kv("Jeu", f"{ev['dataset']['id']} · {len(ev['markets'])} marchés")
        s.kv("Exécutions", runs)
        s.kv("Durée max (ms)", f"{max(times):.1f} / plafond {b.max_cycle_ms}")
        s.kv("Mémoire pic (octets)", f"{max(peaks)} / plafond {b.max_memory_bytes}")
        s.kv("Entrée (octets)", f"{len(raw)} / plafond {b.max_input_bytes}")
        s.kv("Sortie (octets)", f"{size} / plafond {b.max_output_bytes}")
        s.kv("Empreintes distinctes", len(digests))
        ok = max(times) <= b.max_cycle_ms and max(peaks) <= b.max_memory_bytes and size <= b.max_output_bytes \
            and len(digests) == 1
        s.kv("Budget de test", "RESPECTÉ" if ok else "DÉPASSÉ")
        s.kv("Budget de production", c.PRODUCTION_BUDGETS_STATUS)
        return s.text()


def _options(args: list, allowed: set) -> dict:
    out = {}
    it = iter(args)
    for a in it:
        if a not in allowed:
            raise UsageError("UNKNOWN_OPTION:" + a[:40])
        try:
            out[a] = next(it)
        except StopIteration:
            raise UsageError("OPTION_VALUE_REQUIRED:" + a) from None
    return out


def _resolve_fixture(value: str) -> Path:
    if value in NAMED_FIXTURES:
        return FIXTURE_DIR / NAMED_FIXTURES[value]
    path = Path(value)
    if not path.is_file():
        raise UsageError("FIXTURE_NOT_FOUND")
    return path


def _width(value: str | None) -> int:
    if value is not None:
        if not value.isdigit():
            raise UsageError("WIDTH_INTEGER")
        return int(value)
    env = os.environ.get("COLUMNS", "")
    return int(env) if env.isdigit() else 80


def _one(session: Session, argv: list, out, err) -> int:
    try:
        code, text = session.run(argv)
        out.write(text)
        return code
    except UsageError as exc:
        err.write(f"USAGE: {exc}\n")
        return EXIT_USAGE
    except RadarRefusal as exc:
        refused_input = exc.code in ("INPUT_TOO_LARGE", "INPUT_MALFORMED", "INPUT_EMPTY", "DUPLICATE_KEY",
                                     "FLOAT_NOT_ALLOWED", "NONFINITE_NUMBER") or exc.code.endswith("_EXPECTED") \
            or exc.code in ("KEYS_MISMATCH", "OBJECT_EXPECTED", "VALUE_NOT_ALLOWED", "FIXTURE_SCHEMA",
                            "EVIDENCE_KIND_NOT_ALLOWED_IN_R0", "OBSERVATION_TOO_LARGE", "SAMPLES_BOUND",
                            "OUTPUT_TOO_LARGE", "BODY_XOR_ERROR", "CATALOGUE_VALUE", "CATALOGUE_TOO_DEEP",
                            "DATASET_ID", "ERROR_CODE", "SOURCE_ACCESS", "PREVIOUS_UNIVERSE", "MARKET_ID",
                            "OBSERVATIONS_BOUND", "DUPLICATE_VALUE") \
            or exc.code.startswith("REF_") or exc.code in (
                "BATCH_SCHEMA", "ADAPTER_VERSION", "EVIDENCE_KIND_NOT_ALLOWED", "SOURCES_BOUND", "SOURCE_ID",
                "DUPLICATE_SOURCE_ID", "UNKNOWN_SOURCE_ID", "REFS_BOUND", "ARTIFACTS_BOUND", "SHA256_EXPECTED",
                "COMMIT_EXPECTED", "CORPUS_ID", "COVERAGE_EMPTY", "UNKNOWN_REASONS", "BLOBS_EXPECTED",
                "UNKNOWN_REASON_FOR_PRESENT_VALUE", "HISTORICAL_OBSERVATION_WITHOUT_SOURCE",
                "L2_VERIFIED_NOT_ALLOWED_FROM_SOURCE", "L2_SCOPE_ONLY_FOR_TOP_N", "L2_TOP_N_SCOPE_REQUIRED",
                "L2_TOP_N_DEPTH_LEVELS_REQUIRED", "L2_SCOPE_COUNTS", "EVIDENCE_ROOT_MISSING",
                "EVIDENCE_ROOT_NOT_A_DIRECTORY")
        err.write(f"{'ENTRÉE REFUSÉE' if refused_input else 'REFUSÉ'}: {exc}\n")
        return EXIT_INPUT if refused_input else EXIT_REFUSED


def shell(session: Session, stdin, out, err) -> int:
    interactive = hasattr(stdin, "isatty") and stdin.isatty()
    kind = "LOT / OFFLINE" if session.batch is not None else "SYNTHETIC / OFFLINE"
    out.write(f"RADAR — shell local ({kind}). 'help' pour l'aide, 'quit' pour sortir.\n")
    last = EXIT_OK
    while True:
        if interactive:
            out.write("radar> ")
            out.flush()
        line = stdin.readline()
        if not line:
            break
        try:
            argv = shlex.split(line)
        except ValueError:
            err.write("USAGE: LIGNE_MALFORMÉE\n")
            last = EXIT_USAGE
            continue
        if not argv:
            continue
        if argv[0] in ("quit", "exit"):
            break
        last = _one(session, argv, out, err)
        out.write("\n")
    out.write("Fin de session RADAR. Préférences et historique déjà enregistrés atomiquement ; rien en cours.\n")
    out.flush()
    return EXIT_OK if last in (EXIT_OK, EXIT_REFUSED) else last


USAGE = ("usage: python -m observability.radar_selection --fixture NAME|PATH [--state-dir DIR] "
         "[--width N] [--mission M] COMMAND [ARGS]\n"
         "       python -m observability.radar_selection --batch PATH --evidence-root DIR [--state-dir DIR] "
         "[--width N] [--mission M] COMMAND [ARGS]\n"
         f"  NAME: {', '.join(NAMED_FIXTURES)}\n  missions: {', '.join(c.MISSIONS)}\n"
         "  commands: status universe scan candidates inspect evidence select unselect pin unpin "
         "exclude include reset history export bench help shell\n")


def main(argv: list | None = None, stdin=None, stdout=None, stderr=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    stdin, out, err = stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr
    opts = {"--fixture": None, "--state-dir": None, "--width": None, "--mission": c.DEFAULT_MISSION,
            "--batch": None, "--evidence-root": None}
    try:
        while argv and argv[0] in opts:
            if len(argv) < 2:
                raise UsageError("OPTION_VALUE_REQUIRED:" + argv[0])
            opts[argv[0]] = argv[1]
            argv = argv[2:]
        if not argv or argv[0] in ("-h", "--help"):
            out.write(USAGE)
            return EXIT_OK if argv else EXIT_USAGE
        state_dir = Path(opts["--state-dir"]) if opts["--state-dir"] else None
        if opts["--batch"] is not None:
            # R1-B: a radar-batch and the evidence root its references live under.
            if opts["--fixture"] is not None or opts["--evidence-root"] is None:
                raise UsageError("BATCH_NEEDS_EVIDENCE_ROOT_AND_NO_FIXTURE")
            from .refs import evidence_root
            try:
                root = evidence_root(opts["--evidence-root"])
            except RadarRefusal as exc:
                raise UsageError(exc.code) from None
            install_offline_guard(state_dir, read_roots=[root])
            if opts["--mission"] not in c.MISSIONS:
                raise UsageError("UNKNOWN_MISSION")
            batch = Path(opts["--batch"])
            if not batch.is_file():
                raise UsageError("BATCH_NOT_FOUND")
            session = Session(None, state_dir, _width(opts["--width"]), opts["--mission"],
                              batch=batch, evidence_root=root)
        else:
            if opts["--evidence-root"] is not None:
                raise UsageError("EVIDENCE_ROOT_ONLY_WITH_BATCH")
            install_offline_guard(state_dir)
            if opts["--fixture"] is None:
                raise UsageError("FIXTURE_REQUIRED")
            if opts["--mission"] not in c.MISSIONS:
                raise UsageError("UNKNOWN_MISSION")
            session = Session(_resolve_fixture(opts["--fixture"]), state_dir, _width(opts["--width"]),
                              opts["--mission"])
    except UsageError as exc:
        err.write(f"USAGE: {exc}\n")
        return EXIT_USAGE
    if argv[0] == "shell":
        return shell(session, stdin, out, err)
    return _one(session, argv, out, err)
