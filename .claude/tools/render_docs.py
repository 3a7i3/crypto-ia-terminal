#!/usr/bin/env python3
"""
render_docs.py — Generateur de vues a partir de .claude/manifest.yaml

OUTIL DE DOCUMENTATION UNIQUEMENT.
- Ne fait JAMAIS partie du runtime de trading.
- N'est importe par AUCUN module de production.
- Ne lit ni n'ecrit aucune donnee scientifique (paper_trades.jsonl, databases/).
- Supprimable sans effet sur le systeme.

Usage :
    python .claude/tools/render_docs.py           # valide puis genere
    python .claude/tools/render_docs.py --check   # valide seulement (CI), n'ecrit rien

Genere :
    .claude/INDEX.md                  (integralement)
    .claude/IMPLEMENTATION_QUEUE.md   (integralement)
    .claude/state/*.yaml              (5 fichiers d'etat)
    blocs <!-- GENERATED:x --> ... <!-- /GENERATED:x --> dans les docs rediges a la main

Regle : le statut PRET / BLOQUE n'est PAS declare dans le manifeste, il est DERIVE
des dependances et du gating. Le manifeste ne porte que des faits (TERMINE, EN_COURS).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install pyyaml")

ROOT = Path(__file__).resolve().parents[1]  # .claude/
MANIFEST = ROOT / "manifest.yaml"
STATE_DIR = ROOT / "state"
BANNER = "<!-- GENERATED — ne pas editer a la main. Source : .claude/manifest.yaml -->"

DONE = "TERMINE"
RUNNING = "EN_COURS"


# --------------------------------------------------------------------------- io
def load() -> dict:
    if not MANIFEST.exists():
        sys.exit(f"Manifeste introuvable : {MANIFEST}")
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def write(path: Path, text: str, check: bool) -> bool:
    """Ecrit si le contenu differe. Retourne True si un changement etait necessaire."""
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == text:
        return False
    if not check:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return True


def splice(path: Path, key: str, body: str, check: bool) -> bool:
    """Remplace le bloc <!-- GENERATED:key --> ... <!-- /GENERATED:key --> d'un fichier
    redige a la main, en preservant tout le reste."""
    if not path.exists():
        return False
    start, end = f"<!-- GENERATED:{key} -->", f"<!-- /GENERATED:{key} -->"
    txt = path.read_text(encoding="utf-8")
    i, j = txt.find(start), txt.find(end)
    if i == -1 or j == -1 or j < i:
        return False
    new = txt[: i + len(start)] + "\n" + body.rstrip() + "\n" + txt[j:]
    return write(path, new, check)


# ------------------------------------------------------------------ derivation
def gate_open(m: dict) -> bool:
    return all(p.get("met") for p in m["gating"]["epoch_gate_preconditions"])


def derive(m: dict) -> dict[str, str]:
    """PRET / BLOQUE derives ; TERMINE / EN_COURS lus tels quels."""
    by_id = {t["id"]: t for t in m["tickets"]}
    open_gate = gate_open(m)
    out: dict[str, str] = {}
    for t in m["tickets"]:
        raw = str(t.get("status", "")).upper()
        if raw in (DONE, RUNNING):
            out[t["id"]] = raw
            continue
        if t.get("gated") and not open_gate:
            out[t["id"]] = "BLOQUE"
            continue
        unmet = [
            d
            for d in t.get("depends_on") or []
            if by_id.get(d, {}).get("status") != DONE
        ]
        out[t["id"]] = "BLOQUE" if unmet else "PRET"
    return out


def prompt_of(tid: str, m: dict) -> str:
    p = ROOT / "prompts" / f"PROMPT_{tid.replace('-', '_')}.md"
    return f"`{p.name}`" if p.exists() else "—"


def blockers(t: dict, m: dict, st: dict[str, str]) -> str:
    by_id = {x["id"]: x for x in m["tickets"]}
    if t.get("gated") and not gate_open(m):
        return "PORTE D'EPOQUE"
    unmet = [
        d for d in t.get("depends_on") or [] if by_id.get(d, {}).get("status") != DONE
    ]
    return ", ".join(unmet) if unmet else "—"


# -------------------------------------------------------------------- validate
def validate(m: dict, st: dict[str, str]) -> list[str]:
    errs: list[str] = []
    ids = {t["id"] for t in m["tickets"]}
    phases = {p["id"] for p in m["phases"]}

    seen: set[str] = set()
    for t in m["tickets"]:
        tid = t["id"]
        if tid in seen:
            errs.append(f"ID de ticket duplique : {tid}")
        seen.add(tid)
        if t.get("phase") not in phases:
            errs.append(f"{tid} : phase inconnue '{t.get('phase')}'")
        for d in t.get("depends_on") or []:
            if d not in ids:
                errs.append(f"{tid} : dependance inexistante '{d}'")
        for u in t.get("unblocks") or []:
            if u not in ids:
                errs.append(f"{tid} : unblocks pointe vers un ticket inexistant '{u}'")
        cw = t.get("conflict_with")
        if cw and cw not in ids:
            errs.append(f"{tid} : conflict_with inexistant '{cw}'")

    # Invariant de gating : un ticket non gated ne doit pas toucher un symbole sensible
    for t in m["tickets"]:
        if not t.get("gated") and t.get("risk") == "CRITIQUE":
            errs.append(
                f"{t['id']} : risque CRITIQUE mais non gated — incoherence de gating"
            )

    # Un ticket TERMINE doit etre TRACABLE : pas de "termine" sans preuve.
    for t in m["tickets"]:
        if str(t.get("status", "")).upper() == DONE:
            pr = t.get("proof") or {}
            if not pr:
                errs.append(
                    f"{t['id']} : TERMINE sans bloc 'proof' — affirmation non etayee"
                )
                continue
            for req in ("commit", "files", "completed_at"):
                if not pr.get(req):
                    errs.append(f"{t['id']} : proof incomplet, champ '{req}' manquant")

    # Coherence checkpoint : atteint mais un ticket requis non TERMINE
    by_id = {t["id"]: t for t in m["tickets"]}
    for c in m["checkpoints"]:
        if c.get("reached"):
            missing = [
                r
                for r in c.get("requires_tickets") or []
                if by_id.get(r, {}).get("status") != DONE
            ]
            if missing:
                errs.append(
                    f"Checkpoint {c['id']} atteint mais tickets "
                    f"non termines : {missing}"
                )

    # Sante de la suite : les compteurs figes doivent etre coherents entre eux
    hb = m.get("health_baseline") or {}
    if hb:
        if hb.get("collection_errors") != hb.get("expected_collection_errors"):
            errs.append(
                "health_baseline : collection_errors "
                f"({hb.get('collection_errors')}) != expected_collection_errors "
                f"({hb.get('expected_collection_errors')})"
            )
        if hb.get("failed") != hb.get("expected_failures"):
            errs.append(
                f"health_baseline : failed ({hb.get('failed')}) != "
                f"expected_failures ({hb.get('expected_failures')})"
            )
        kf = hb.get("known_failures") or []
        if len(kf) != (hb.get("expected_failures") or 0):
            errs.append(
                f"health_baseline : {len(kf)} known_failures listes pour "
                f"expected_failures={hb.get('expected_failures')}"
            )

    # Dette epistemique residuelle.
    #
    # PORTEE DE CE CONTROLE : completude STRUCTURELLE uniquement.
    # Il garantit que chaque inconnue porte les champs requis et un genre
    # valide. Il ne garantit PAS la qualite SEMANTIQUE du contenu : un
    # how_to_observe vague ou un niveau de dette mal choisi passent le
    # validateur. NON OBSERVE : la coherence semantique des champs.
    KINDS = {"UNKNOWN", "BLIND_SPOT"}
    DEBTS = {"critique", "majeure", "moyenne", "mineure", "nulle"}
    for u in m.get("residual_epistemic_debt") or []:
        uid = u.get("id", "?")
        for req in (
            "kind",
            "what_is_missing",
            "why_it_matters",
            "blocks",
            "how_to_observe",
            "debt",
            "status",
        ):
            if not u.get(req):
                errs.append(
                    f"{uid} : dette epistemique incomplete, champ '{req}' manquant"
                )
        if u.get("kind") and u["kind"] not in KINDS:
            errs.append(
                f"{uid} : kind '{u['kind']}' invalide (attendu {sorted(KINDS)})"
            )
        if u.get("debt") and u["debt"] not in DEBTS:
            errs.append(f"{uid} : debt '{u['debt']}' hors echelle normative")
        # Cycle de vie : chaque genre a ses statuts admis.
        allowed = (
            {"NON_OBSERVABLE", "OBSERVABLE"}
            if u.get("kind") == "BLIND_SPOT"
            else {"NON_OBSERVE", "OBSERVE"}
        )
        if u.get("status") and u["status"] not in allowed:
            errs.append(
                f"{uid} : status '{u['status']}' incompatible avec "
                f"kind={u.get('kind')} (attendu {sorted(allowed)})"
            )
        # Un angle mort devenu OBSERVABLE n'est plus un angle mort : l'instrument
        # existe, l'observation reste a produire. Il doit etre reclasse UNKNOWN.
        if u.get("kind") == "BLIND_SPOT" and u.get("status") == "OBSERVABLE":
            errs.append(
                f"{uid} : BLIND_SPOT/OBSERVABLE — l'instrument existe, "
                "reclasser en UNKNOWN/NON_OBSERVE (l'observation reste a produire)"
            )
        # Une dette critique affirme qu'une decision IRREVERSIBLE est bloquee :
        # cette affirmation exige sa propre justification et son falsificateur.
        if u.get("debt") == "critique":
            cj = u.get("critical_justification") or {}
            for req in ("decision", "why_irreversible", "falsifier"):
                if not cj.get(req):
                    errs.append(
                        f"{uid} : dette CRITIQUE non demontree, "
                        f"critical_justification.{req} manquant"
                    )
        # Un angle mort sans instrument declare n'est pas gouverne : on sait
        # qu'on ne peut pas observer, mais pas ce qu'il faudrait construire.
        if u.get("kind") == "BLIND_SPOT" and not u.get("instrument_required"):
            errs.append(
                f"{uid} : BLIND_SPOT sans 'instrument_required' — "
                "l'angle mort n'est pas gouverne"
            )

    # Cycle de dependances
    graph = {t["id"]: list(t.get("depends_on") or []) for t in m["tickets"]}
    state: dict[str, int] = {}

    def visit(n: str, path: list[str]) -> None:
        if state.get(n) == 2:
            return
        if state.get(n) == 1:
            errs.append(f"Cycle de dependances : {' -> '.join(path + [n])}")
            return
        state[n] = 1
        for d in graph.get(n, []):
            if d in graph:
                visit(d, path + [n])
        state[n] = 2

    for n in graph:
        visit(n, [])
    return errs


# ------------------------------------------------------------------- rendering
def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def counts(st: dict[str, str]) -> dict[str, int]:
    c = {"PRET": 0, "BLOQUE": 0, RUNNING: 0, DONE: 0}
    for v in st.values():
        c[v] = c.get(v, 0) + 1
    return c


def render_index(m: dict, st: dict[str, str]) -> str:
    c = counts(st)
    ngated = sum(1 for t in m["tickets"] if not t.get("gated"))
    L = [
        BANNER,
        "",
        "# INDEX — Tous les tickets du chantier",
        "",
        f"> Genere le {stamp()} depuis `.claude/manifest.yaml`.",
        "> Pour modifier un statut : editer le manifeste, puis relancer",
        "> `python .claude/tools/render_docs.py`.",
        "",
        f"**{len(m['tickets'])} tickets** · PRET **{c['PRET']}** · "
        f"BLOQUE **{c['BLOQUE']}** · "
        f"EN COURS **{c[RUNNING]}** · TERMINE **{c[DONE]}**",
        "",
        "> **Deux comptages distincts, a ne pas confondre :**",
        f"> **{c['PRET']} tickets PRET** = demarrables *maintenant*",
        "> (dependances satisfaites).",
        f"> **{ngated} tickets NON GATED** = executables sous le gel *a terme* ;",
        "> certains attendent",
        "> encore une dependance. Un ticket non gated dont une dependance",
        "> n'est pas TERMINE",
        "> est **BLOQUE**, pas PRET.",
        "",
    ]
    for ph in m["phases"]:
        tk = [t for t in m["tickets"] if t["phase"] == ph["id"]]
        if not tk:
            continue
        tag = " · **GATED**" if ph.get("gated") else ""
        L += [
            f"## {ph['id']} — {ph['title']}{tag}",
            "",
            "| ID | Titre | Prio | Statut | Bloque par | Prompt | Est. | Risque |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for t in tk:
            L.append(
                f"| `{t['id']}` | {t['title']} | {t.get('priority','—')} | "
                f"**{st[t['id']]}** | {blockers(t, m, st)} | {prompt_of(t['id'], m)} | "
                f"{t.get('estimate','—')} | {t.get('risk','—')} |"
            )
        L.append("")
    notes = [t for t in m["tickets"] if t.get("note")]
    if notes:
        L += ["## Notes", ""] + [f"- `{t['id']}` — {t['note']}" for t in notes] + [""]
    return "\n".join(L) + "\n"


def render_queue(m: dict, st: dict[str, str]) -> str:
    by = lambda s: [t for t in m["tickets"] if st[t["id"]] == s]  # noqa: E731
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    ready = sorted(
        by("PRET"), key=lambda t: (order.get(t.get("priority", "P9"), 9), t["id"])
    )
    c = counts(st)
    L = [
        BANNER,
        "",
        "# IMPLEMENTATION_QUEUE — Backlog priorise",
        "",
        f"> Genere le {stamp()} depuis `.claude/manifest.yaml`.",
        "",
        "## Regle d'execution",
        "",
        "1. **Un seul ticket a la fois.** Jamais deux tickets dans un commit.",
        "2. Prendre le premier de la file **PRET**.",
        "3. Ouvrir `.claude/prompts/PROMPT_<ID>.md` et l'executer.",
        "4. Tester, commiter, mettre a jour le **manifeste**, relancer le generateur.",
        "5. **S'ARRETER.** Jamais d'enchainement automatique.",
        "",
    ]
    if ready:
        L += [f"> **PROCHAIN TICKET : `{ready[0]['id']}` — {ready[0]['title']}**", ""]
    ngated = sum(1 for t in m["tickets"] if not t.get("gated"))
    L += [
        f"## FILE : PRET — {c['PRET']} tickets demarrables maintenant",
        "",
        f"*(Sur {ngated} tickets non gated : les autres attendent une dependance.)*",
        "",
        "| # | ID | Titre | Phase | Prio | Est. | Prompt |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, t in enumerate(ready, 1):
        L.append(
            f"| {i} | `{t['id']}` | {t['title']} | {t['phase']} | "
            f"{t.get('priority','—')} | "
            f"{t.get('estimate','—')} | {prompt_of(t['id'], m)} |"
        )
    L += [
        "",
        f"## FILE : BLOQUE — {c['BLOQUE']} tickets",
        "",
        "| ID | Titre | Bloque par | Risque |",
        "|---|---|---|---|",
    ]
    for t in by("BLOQUE"):
        L.append(
            f"| `{t['id']}` | {t['title']} | {blockers(t, m, st)} | "
            f"{t.get('risk','—')} |"
        )
    L += ["", "### Condition de deblocage — porte d'epoque", ""]
    for p in m["gating"]["epoch_gate_preconditions"]:
        L.append(f"- [{'x' if p.get('met') else ' '}] **{p['id']}** — {p['text']}")
    L += ["", f"## FILE : EN COURS — {c[RUNNING]} tickets", ""]
    run = by(RUNNING)
    L += [f"- `{t['id']}` — {t['title']}" for t in run] if run else ["*(vide)*"]
    L += ["", f"## FILE : TERMINE — {c[DONE]} tickets", ""]
    done = by(DONE)
    if done:
        L += ["| ID | Titre | Commit |", "|---|---|---|"]
        L += [f"| `{t['id']}` | {t['title']} | `{t.get('sha','—')}` |" for t in done]
    else:
        L.append("*(vide)*")
    return "\n".join(L) + "\n"


def render_state(m: dict, st: dict[str, str]) -> dict[str, dict]:
    s, c = m["state"], counts(st)
    ready = [t for t in m["tickets"] if st[t["id"]] == "PRET"]
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    ready.sort(key=lambda t: (order.get(t.get("priority", "P9"), 9), t["id"]))
    nxt = ready[0] if ready else None
    cur_id = s.get("current_ticket")
    cur = next((t for t in m["tickets"] if t["id"] == cur_id), None) if cur_id else None
    ck = next(
        (x for x in m["checkpoints"] if x["id"] == s.get("current_checkpoint")), {}
    )
    ph = next((x for x in m["phases"] if x["id"] == s.get("current_phase")), {})
    return {
        "project_state.yaml": {
            "generated": stamp(),
            "checkpoint": s.get("current_checkpoint"),
            "phase": s.get("current_phase"),
            "tickets_total": len(m["tickets"]),
            "pret": c["PRET"],
            "bloque": c["BLOQUE"],
            "en_cours": c[RUNNING],
            "termine": c[DONE],
            "epoch": s.get("epoch"),
            "gate_open": gate_open(m),
            "decisions_en_attente": [
                d["id"] for d in m["decisions"] if d.get("status") == "EN_ATTENTE"
            ],
        },
        "current_ticket.yaml": (
            {
                "generated": stamp(),
                "ticket": None,
                "next": (nxt or {}).get("id"),
                "next_title": (nxt or {}).get("title"),
                "prompt": (
                    f"prompts/PROMPT_{nxt['id'].replace('-', '_')}.md" if nxt else None
                ),
            }
            if not cur
            else {
                "generated": stamp(),
                "ticket": cur["id"],
                "title": cur["title"],
                "phase": cur["phase"],
                "gated": cur.get("gated"),
                "risk": cur.get("risk"),
                "files": cur.get("files"),
                "prompt": f"prompts/PROMPT_{cur['id'].replace('-', '_')}.md",
            }
        ),
        "current_phase.yaml": {
            "generated": stamp(),
            "phase": ph.get("id"),
            "title": ph.get("title"),
            "gated": ph.get("gated"),
            "doc": ph.get("doc"),
            "estimate": ph.get("estimate"),
        },
        "current_checkpoint.yaml": {
            "generated": stamp(),
            "checkpoint": ck.get("id"),
            "name": ck.get("name"),
            "reversible": ck.get("reversible"),
            "reached": ck.get("reached"),
            "authority": ck.get("authority"),
            "exit_criteria": ck.get("exit_criteria"),
        },
        "last_session.yaml": s.get("last_session")
        or {
            "generated": stamp(),
            "session": None,
            "note": "Aucune session enregistree. Renseigner state.last_session.",
        },
    }


def render_roadmap_block(m: dict, st: dict[str, str]) -> str:
    L = []
    for ph in m["phases"]:
        tk = [t for t in m["tickets"] if t["phase"] == ph["id"]]
        if not tk:
            continue
        L.append(f"### {ph['id']} — {ph['title']}")
        L.append(
            " · ".join(f"[{'x' if st[t['id']] == DONE else ' '}] {t['id']}" for t in tk)
        )
        L.append("")
    return "\n".join(L)


def render_checkpoint_block(m: dict, st: dict[str, str]) -> str:
    by_id = {t["id"]: t for t in m["tickets"]}
    L = ["| Palier | Nom | Atteint | Tickets requis termines |", "|---|---|---|---|"]
    for c in m["checkpoints"]:
        req = c.get("requires_tickets") or []
        done = sum(1 for r in req if by_id.get(r, {}).get("status") == DONE)
        L.append(
            f"| **{c['id']}** | {c['name']} | {'OUI' if c.get('reached') else 'non'} | "
            f"{done}/{len(req)} |"
        )
    return "\n".join(L)


# ------------------------------------------------------------------------ main
def main() -> int:
    check = "--check" in sys.argv
    m = load()
    st = derive(m)

    errs = validate(m, st)
    if errs:
        print("MANIFESTE INVALIDE :")
        for e in errs:
            print(f"  - {e}")
        return 1

    changed: list[str] = []
    if write(ROOT / "INDEX.md", render_index(m, st), check):
        changed.append("INDEX.md")
    if write(ROOT / "IMPLEMENTATION_QUEUE.md", render_queue(m, st), check):
        changed.append("IMPLEMENTATION_QUEUE.md")
    for name, data in render_state(m, st).items():
        body = (
            "# GENERATED — ne pas editer a la main. Source : .claude/manifest.yaml\n"
            + yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        )
        if write(STATE_DIR / name, body, check):
            changed.append(f"state/{name}")
    if splice(
        ROOT / "MASTER_ROADMAP.md", "avancement", render_roadmap_block(m, st), check
    ):
        changed.append("MASTER_ROADMAP.md#avancement")
    if splice(
        ROOT / "CHECKPOINTS.md", "statuts", render_checkpoint_block(m, st), check
    ):
        changed.append("CHECKPOINTS.md#statuts")

    c = counts(st)
    if check:
        if changed:
            print("DESYNCHRONISE — relancer sans --check :")
            for f in changed:
                print(f"  - {f}")
            return 1
        print(f"OK — documents synchronises ({len(m['tickets'])} tickets).")
        return 0

    print(
        f"Genere depuis manifest.yaml — {len(m['tickets'])} tickets : "
        f"PRET {c['PRET']} · BLOQUE {c['BLOQUE']} · "
        f"EN COURS {c[RUNNING]} · TERMINE {c[DONE]}"
    )
    for f in changed:
        print(f"  ecrit  {f}")
    if not changed:
        print("  (aucun changement)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
