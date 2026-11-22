"""Pilote ``data-provenance-auditor`` — référence déterministe exécutée en banc isolé.

Question bornée (``DATASET_PROVENANCE_CHAIN``) : pour un seul dataset, établir la
chaîne source → producteur → stockage → lecteur → API → client → affichage avec
preuves localisables, puis examiner une capture autorisée (fraîcheur, unités,
jointures, rejeu).

Ce module n'est pas un runner : il n'appelle aucun modèle, aucun réseau, aucun
service ; il n'écrit rien. Il produit un rapport scellé que seuls le banc de
tests et la revue humaine peuvent qualifier. Voir
docs/contracts/AGENT_OBSERVATION_MISSION_V1.md.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

from agent_bench.observation import contract as c
from agent_bench.observation.scoped_io import BudgetExceeded, ScopedReader
from agent_bench.observation.source_index import (
    NETWORK,
    index_python,
    index_ts,
    ts_literal_lines,
)

AUDITOR_VERSION = "data-provenance-auditor.bench.v1"
HOPS = ("SOURCE_TO_PRODUCER", "PRODUCER", "PRODUCER_TO_STORAGE", "STORAGE_TO_READER",
        "READER_TO_API", "API_TO_CLIENT", "CLIENT_TO_VIEW")
LIMITS = [
    "STATIC_ANALYSIS_ONLY_NO_CODE_EXECUTED",
    "NO_RUNTIME_OBSERVATION_SOURCE_PROOF_IS_NOT_RUNTIME_PROOF",
    "ONE_DATASET_DIRECT_CONSUMERS_ONLY",
    "DYNAMIC_PATHS_AND_INDIRECTION_BEYOND_ONE_HOP_ARE_INCONCLUSIVE",
    "REPORT_IS_NOT_SELF_CERTIFYING",
]
DEC = re.compile(r"^-?(0|[1-9][0-9]{0,30})(\.[0-9]{1,18})?$")


# --------------------------------------------------------------------------- helpers

def _utc_ms(text):
    return int(datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _ev(path, line, symbol, etype, sha=None):
    e = {"path": path, "line": line, "symbol": symbol, "evidence_type": etype}
    if sha:
        e["file_sha256"] = sha
    return e


def _strict_json(data: bytes):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError(f"duplicate field {k}")
            out[k] = v
        return out

    def constant(_):
        raise ValueError("non-finite number")

    return json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def resolve(doc, pointer):
    """Valeurs d'un pointeur ``a.b[*].c`` (``[*]`` aplatit). Champ absent => rien."""
    items = [(doc, [])]
    for part in pointer.split("."):
        star = part.endswith("[*]")
        key = part[:-3] if star else part
        nxt = []
        for value, parents in items:
            if not isinstance(value, dict) or key not in value:
                continue
            v = value[key]
            if star:
                if isinstance(v, list):
                    nxt.extend((x, parents + [value]) for x in v)
            else:
                nxt.append((v, parents + [value]))
        items = nxt
    return items


def _outer(pointer):
    i = pointer.find("[*]")
    return (pointer[: i + 3], pointer[i + 4:]) if i >= 0 else (None, pointer)


# --------------------------------------------------------------------------- auditor

class _Run:
    def __init__(self, mission, reader, sha_of):
        self.m = mission
        self.q = mission["question"]
        self.r = reader
        self.sha = sha_of
        self.findings = []
        self.chain = {}
        self.unknowns = []
        self.measurements = []
        self.errors = []

    # ---- recording
    def finding(self, category, code, claim, level, confidence, evidence):
        for e in evidence:
            if e.get("path") and "file_sha256" not in e and e["path"] in self.r.consulted:
                e["file_sha256"] = self.r.consulted[e["path"]]["sha256"]
        key = {"category": category, "code": code, "evidence": evidence}
        self.findings.append({"finding_id": c.sha256_json(key)[:16], "category": category, "code": code,
                              "claim": claim, "level": level, "confidence": confidence, "evidence": evidence})

    def hop(self, name, level, summary, evidence=()):
        ev = list(evidence)
        for e in ev:
            if e.get("path") in self.r.consulted:
                e.setdefault("file_sha256", self.r.consulted[e["path"]]["sha256"])
        self.chain[name] = {"hop": name, "level": level, "summary": summary, "evidence": ev}

    def unknown(self, code, question, measurement):
        self.unknowns.append({"code": code, "question": question})
        if measurement:
            self.measurements.append({"code": code, "measurement": measurement})

    # ---- code chain
    def index(self):
        files = self.r.list_files()
        self.py, self.ts = {}, {}
        ts_files = [f for f in files if f.endswith((".ts", ".tsx"))]
        known_ts = set(ts_files)
        for rel in files:
            if rel.endswith(".py"):
                data = self.r.read(rel)
                if data is not None:
                    pm = index_python(rel, data)
                    if pm.syntax_error:
                        self.errors.append({"code": "SOURCE_UNPARSABLE", "detail": rel})
                    self.py[rel] = pm
            elif rel in known_ts:
                data = self.r.read(rel)
                if data is not None:
                    self.ts[rel] = index_ts(rel, data, known_ts)

    def module_rel(self, module):
        return module.replace(".", "/") + ".py"

    def code_chain(self):
        ds = self.q["dataset_id"]
        lit = {rel: [f for f in pm.literals if f.detail == ds] for rel, pm in self.py.items()}
        producers = [pm for rel, pm in sorted(self.py.items()) if lit[rel] and pm.writes]
        producer = producers[0] if len(producers) == 1 else None
        self.producer = producer
        if len(producers) > 1:
            self.finding("CHAIN", "MULTIPLE_PRODUCERS", f"{len(producers)} modules écrivent un fichier et portent l'identifiant du dataset ; producteur non unique.",
                         "PROVEN", "HIGH", [_ev(p.path, lit[p.path][0].line, lit[p.path][0].symbol, "LITERAL") for p in producers])

        # PRODUCER
        if producer:
            w = producer.writes
            self.hop("PRODUCER", "PROVEN", f"{producer.module} porte l'identifiant du dataset et écrit un fichier.",
                     [_ev(producer.path, lit[producer.path][0].line, lit[producer.path][0].symbol, "LITERAL")]
                     + [_ev(producer.path, f.line, f.symbol, "CALL_SITE") for f in w])
            self.finding("CHAIN", "PRODUCER_IDENTIFIED", f"Producteur : {producer.module} ({', '.join(sorted({f.symbol for f in w}))}).",
                         "PROVEN", "HIGH", [_ev(producer.path, f.line, f.symbol, "CALL_SITE") for f in w])
        else:
            self.hop("PRODUCER", "NOT_FOUND", "Aucun module du périmètre ne porte l'identifiant du dataset ET n'écrit de fichier.")
            self.finding("CHAIN", "PRODUCER_NOT_FOUND", "Aucun producteur prouvé dans le périmètre ; aucun producteur n'est supposé.",
                         "NOT_FOUND", "HIGH", [_ev(None, None, None, "MISSION_INPUT")])
            self.unknown("PRODUCER_UNKNOWN", "Quel processus écrit ce dataset ?", "Identifier hors périmètre le producteur réel (mission séparée).")

        # SOURCE_TO_PRODUCER
        if producer:
            inputs = sorted({t.detail for t in producer.templates} - {t.detail for t in producer.write_templates})
            ups = [(pm, f) for rel, pm in sorted(self.py.items()) if pm is not producer
                   for f in pm.write_templates if f.detail in inputs]
            if ups:
                linked = sorted({f.detail for _, f in ups})
                ev = [_ev(f.path, f.line, f.symbol, "CALL_SITE") for _, f in ups]
                ev += [_ev(t.path, t.line, t.symbol, "LITERAL") for t in producer.templates if t.detail in linked]
                self.hop("SOURCE_TO_PRODUCER", "PROVEN", f"Fichiers écrits en amont puis lus par le producteur : {', '.join(linked)}.", ev)
                missing = sorted(set(inputs) - set(linked))
                if missing:
                    self.finding("CHAIN", "PRODUCER_INPUT_WRITER_NOT_FOUND", f"Entrées du producteur sans écrivain prouvé : {', '.join(missing)}.",
                                 "INCONCLUSIVE", "MEDIUM", [_ev(t.path, t.line, t.symbol, "LITERAL") for t in producer.templates if t.detail in missing])
                for pm in sorted({id(p): p for p, _ in ups}.values(), key=lambda p: p.path):
                    nets = sorted({(f.line, f.detail) for f in pm.literals if NETWORK.match(f.detail)})
                    if nets:
                        self.finding("SOURCE", "UPSTREAM_ENDPOINTS_DECLARED",
                                     f"{pm.module} déclare les sources réseau {', '.join(n for _, n in nets)} ; la connexion effective n'est pas prouvée par le code.",
                                     "SUPPORTED", "MEDIUM", [_ev(pm.path, ln, "<module>", "LITERAL") for ln, _ in nets])
                        self.unknown("UPSTREAM_RUNTIME_UNPROVEN", "La collecte a-t-elle réellement lu ces sources, et à quelle heure ?",
                                     "Lire le manifest scellé de la collecte (heures, symboles, reconnexions) sur l'hôte, en mission READ-ONLY séparée.")
                    if pm.append_modes:
                        self.finding("REPLAY", "UPSTREAM_APPEND_ONLY_LOG", f"{pm.module} ouvre {len(pm.append_modes)} fichier(s) en ajout ; une relance dans le même répertoire ajouterait des lignes.",
                                     "PROVEN", "HIGH", [_ev(f.path, f.line, f.symbol, "CALL_SITE") for f in pm.append_modes])
                        self.unknown("UPSTREAM_DUPLICATE_LINES", "Le journal amont contient-il des lignes rejouées ?",
                                     "Compter sur la capture scellée les doublons de ligne et les ruptures de séquence (mesure runtime).")
            else:
                self.hop("SOURCE_TO_PRODUCER", "NOT_FOUND" if inputs else "INCONCLUSIVE",
                         "Aucun écrivain des entrées du producteur dans le périmètre." if inputs else "Le producteur ne nomme aucune entrée fichier reconnaissable.",
                         [_ev(t.path, t.line, t.symbol, "LITERAL") for t in producer.templates if t.detail in inputs])
                self.unknown("SOURCE_UNKNOWN", "D'où viennent les entrées du producteur ?", "Identifier l'écrivain amont (mission séparée).")
        else:
            self.hop("SOURCE_TO_PRODUCER", "NOT_FOUND", "Sans producteur prouvé, le maillon amont ne peut pas être établi.")

        # PRODUCER_TO_STORAGE
        self.producer_binding = set()
        if producer:
            ev = []
            for f in producer.writes:
                for t in f.targets:
                    if t in producer.argdest:
                        self.producer_binding.add("CLI:" + producer.argdest[t])
                        cli = next(x for x in producer.cli if x.detail == producer.argdest[t])
                        ev.append(_ev(cli.path, cli.line, cli.symbol, "CODE"))
                for e in producer.env:
                    if e.symbol == f.symbol:
                        self.producer_binding.add("ENV:" + e.detail)
                        ev.append(_ev(e.path, e.line, e.symbol, "CALL_SITE"))
            if self.producer_binding:
                self.hop("PRODUCER_TO_STORAGE", "PROVEN", f"Chemin écrit fourni par {', '.join(sorted(self.producer_binding))}.",
                         ev + [_ev(producer.path, f.line, f.symbol, "CALL_SITE") for f in producer.writes])
            else:
                self.hop("PRODUCER_TO_STORAGE", "INCONCLUSIVE", "Origine du chemin écrit non reconnue (chemin dynamique).",
                         [_ev(producer.path, f.line, f.symbol, "CALL_SITE") for f in producer.writes])
            replaces = [f for f in producer.writes if f.detail == "os.replace"]
            direct = [f for f in producer.writes if f.detail in ("write_bytes", "write_text") or f.detail.startswith("open:w")]
            if direct and not replaces:
                self.finding("REPLAY", "RISK_NON_ATOMIC_OVERWRITE", "Le producteur écrase le fichier publié sans renommage atomique : un lecteur peut voir un fichier partiel.",
                             "PROVEN", "HIGH", [_ev(f.path, f.line, f.symbol, "CALL_SITE") for f in direct])
            if producer.wallclock:
                self.finding("REPLAY", "RISK_WALLCLOCK_IN_PUBLICATION", "Le producteur lit l'horloge : deux constructions depuis la même preuve ne sont pas identiques à l'octet.",
                             "PROVEN", "HIGH", [_ev(f.path, f.line, f.symbol, "CALL_SITE") for f in producer.wallclock])
            dup = [f for f in producer.literals if "DUPLICATE" in f.detail and f.detail.isupper()]
            if dup:
                self.finding("REPLAY", "GUARD_DUPLICATE_REJECTED", "Le validateur du producteur nomme un rejet de doublon.",
                             "SUPPORTED", "MEDIUM", [_ev(f.path, f.line, f.symbol, "LITERAL") for f in dup[:3]])
        else:
            self.hop("PRODUCER_TO_STORAGE", "NOT_FOUND", "Sans producteur prouvé, aucun stockage ne peut lui être rattaché.")

        # API / CLIENT / VIEW, then READER (resolved from the route)
        clients = [tm for rel, tm in sorted(self.ts.items()) if ts_literal_lines(tm, ds) and tm.api_literals]
        client = clients[0] if clients else None
        route = None
        if client:
            api_paths = sorted({f.detail for f in client.api_literals})
            for rel, pm in sorted(self.py.items()):
                for r in pm.routes:
                    if r.detail in api_paths:
                        route = (pm, r)
                        break
                if route:
                    break
        reader_mod, reader_rel, reader_call = None, None, None
        if route:
            pm, r = route
            for call in pm.route_calls.get(r.symbol, []):
                if call.detail in pm.globals_cls:
                    cls, _ = pm.globals_cls[call.detail]
                    imp = next((i for i in pm.imports if i.detail.endswith(":" + cls)), None)
                    if imp:
                        reader_mod = imp.detail.split(":")[0]
                        reader_rel = self.module_rel(reader_mod)
                        reader_call = (call, cls, imp)
                        break
            if reader_call:
                call, cls, imp = reader_call
                self.hop("READER_TO_API", "PROVEN", f"La route {r.detail} ({r.symbol}) appelle {call.detail}, instance de {cls} importé de {reader_mod}.",
                         [_ev(pm.path, r.line, r.symbol, "CODE"), _ev(pm.path, call.line, r.symbol, "CALL_SITE"),
                          _ev(pm.path, imp.line, "<module>", "IMPORT")])
            else:
                self.hop("READER_TO_API", "INCONCLUSIVE", f"La route {r.detail} existe mais son lecteur n'est pas résolu statiquement.",
                         [_ev(pm.path, r.line, r.symbol, "CODE")])
            lines = ts_literal_lines(client, r.detail)
            self.hop("API_TO_CLIENT", "PROVEN", f"Le client {client.path} appelle {r.detail}, servi par {pm.path}.",
                     [_ev(pm.path, r.line, r.symbol, "CODE")] + [_ev(client.path, ln, "<module>", "LITERAL") for ln in lines[:1]]
                     + [_ev(client.path, ts_literal_lines(client, ds)[0], "<module>", "LITERAL")])
        else:
            self.hop("READER_TO_API", "NOT_FOUND", "Aucune route du périmètre ne sert l'endpoint du client du dataset.")
            self.hop("API_TO_CLIENT", "NOT_FOUND" if not client else "INCONCLUSIVE",
                     "Aucun client portant l'identifiant du dataset et un endpoint /api." if not client
                     else "Le client nomme un endpoint qu'aucune route du périmètre ne sert.",
                     [_ev(client.path, f.line, "<module>", "LITERAL") for f in client.api_literals[:2]] if client else [])

        if client:
            fns = {n for n, _ in client.export_fns}
            views = [(tm, names, ln) for rel, tm in sorted(self.ts.items()) for (res, names, ln) in tm.imports
                     if res == client.path and fns & set(names)]
            if views:
                ev = [_ev(tm.path, ln, "<module>", "IMPORT") for tm, _, ln in views]
                hosts = []
                for tm, _, _ in views:
                    comps = {n for n, _ in tm.export_consts} | {n for n, _ in tm.export_fns}
                    hosts += [(h, ln) for rel, h in sorted(self.ts.items()) for (res, names, ln) in h.imports
                              if res == tm.path and comps & set(names)]
                ev += [_ev(h.path, ln, "<module>", "IMPORT") for h, ln in hosts]
                self.hop("CLIENT_TO_VIEW", "PROVEN", f"Vue(s) consommatrice(s) : {', '.join(tm.path for tm, _, _ in views)}"
                         + (f" ; rendue(s) par {', '.join(h.path for h, _ in hosts)}." if hosts else "."), ev)
            else:
                self.hop("CLIENT_TO_VIEW", "NOT_FOUND", "Aucune vue du périmètre n'importe une fonction exportée du client.")
        else:
            self.hop("CLIENT_TO_VIEW", "NOT_FOUND", "Sans client prouvé, aucun affichage ne peut être rattaché.")

        # STORAGE_TO_READER
        if reader_rel is None:
            self.hop("STORAGE_TO_READER", "NOT_FOUND" if not route else "INCONCLUSIVE",
                     "Aucun lecteur résolu depuis l'API.")
        elif reader_rel not in self.py:
            self.r.read(reader_rel)  # consigne le refus si hors périmètre ; n'ouvre rien sinon
            refused = self.r.refused.get(reader_rel)
            self.hop("STORAGE_TO_READER", "INCONCLUSIVE",
                     f"Le lecteur {reader_rel} n'a pas été lu ({refused or 'MISSING'}) : lien au stockage non établi.",
                     [_ev(route[0].path, reader_call[2].line, "<module>", "IMPORT")])
            self.finding("SCOPE", "READER_OUT_OF_SCOPE_NOT_READ" if refused == "OUT_OF_SCOPE_NOT_READ" else "READER_MISSING",
                         f"Le lecteur {reader_rel} est hors périmètre ou absent : il n'est ni lu ni présumé conforme.",
                         "PROVEN", "HIGH", [_ev(route[0].path, reader_call[2].line, "<module>", "IMPORT")])
            self.unknown("READER_UNREAD", f"Que lit réellement {reader_rel} ?", None)
        else:
            rd = self.py[reader_rel]
            reads = rd.reads
            schema_imp = [i for i in rd.imports if producer and i.detail.split(":")[0] == producer.module]
            has_lit = [f for f in rd.literals if f.detail == ds]
            binding = {"ENV:" + e.detail for e in rd.env} | {"CLI:" + x.detail for x in rd.cli}
            shared = sorted(binding & self.producer_binding)
            ev_r = [_ev(rd.path, f.line, f.symbol, "CALL_SITE") for f in reads[:2]]
            if not reads:
                self.hop("STORAGE_TO_READER", "INCONCLUSIVE", f"{reader_rel} n'effectue aucune lecture reconnue.")
            elif shared:
                self.hop("STORAGE_TO_READER", "PROVEN", f"Producteur et lecteur partagent la liaison {', '.join(shared)}.",
                         ev_r + [_ev(e.path, e.line, e.symbol, "CALL_SITE") for e in rd.env if "ENV:" + e.detail in shared])
            elif schema_imp or has_lit:
                ev = ev_r + [_ev(i.path, i.line, "<module>", "IMPORT") for i in schema_imp] + [_ev(rd.path, f.line, f.symbol, "LITERAL") for f in has_lit[:1]]
                self.hop("STORAGE_TO_READER", "INFERRED",
                         f"Le lecteur valide le même schéma mais lit {', '.join(sorted(binding)) or 'un chemin non résolu'} alors que le producteur écrit via {', '.join(sorted(self.producer_binding)) or 'un chemin non résolu'} : le fichier commun n'est relié que par la configuration de déploiement.",
                         ev)
                self.unknown("STORAGE_BINDING_RUNTIME", "Le fichier lu par le lecteur est-il celui écrit par le producteur ?",
                             f"Sur l'hôte : comparer la valeur de {', '.join(sorted(binding)) or 'la configuration du lecteur'} au chemin passé à {', '.join(sorted(self.producer_binding)) or 'le producteur'}, puis le sha256 du fichier servi à celui de la publication.")
            else:
                self.hop("STORAGE_TO_READER", "INCONCLUSIVE",
                         f"{reader_rel} lit un fichier sans lien prouvé avec le dataset (ni schéma, ni identifiant, ni liaison commune).", ev_r)
                self.finding("CHAIN", "READER_WITHOUT_PROVEN_STORAGE_LINK",
                             f"Le lecteur servi par l'API ({reader_rel}) n'a aucun lien prouvé avec le stockage du producteur.",
                             "PROVEN", "HIGH", ev_r + [_ev(e.path, e.line, e.symbol, "CALL_SITE") for e in rd.env])
                self.unknown("READER_STORAGE_UNPROVEN", "Le lecteur sert-il bien ce dataset ?", "Comparer sur l'hôte le fichier lu et la publication (sha256).")
            guard = [f for f in rd.literals if f.detail.endswith("CHANGED_DURING_READ")]
            if guard:
                self.finding("REPLAY", "READER_DETECTS_CHANGE_DURING_READ", "Le lecteur refuse un fichier modifié pendant sa lecture.",
                             "SUPPORTED", "MEDIUM", [_ev(f.path, f.line, f.symbol, "LITERAL") for f in guard[:1]])

    # ---- capture
    def capture(self):
        cap = self.m["capture"]
        data = self.r.read(cap["path"])
        out = {"capture_id": cap["capture_id"], "path": cap["path"], "kind": cap["kind"], "parsed": False}
        try:
            doc = _strict_json(data)
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
            self.errors.append({"code": "CAPTURE_MALFORMED", "detail": type(exc).__name__})
            self.finding("INPUT", "CAPTURE_MALFORMED", "La capture autorisée n'est pas un JSON strict ; fraîcheur, unités et jointures restent non conclusives.",
                         "PROVEN", "HIGH", [_ev(cap["path"], None, None, "CAPTURE_FIELD")])
            self.unknown("CAPTURE_UNREADABLE", "Que contient la publication ?", "Obtenir une capture valide (nouvelle mission).")
            self.freshness = {"classification": "INCONCLUSIVE", "verdict": "INCONCLUSIVE", "effective_source": None}
            return out
        out["parsed"] = True
        q = self.q
        if not isinstance(doc, dict) or q["dataset_id"] not in [v for v in doc.values() if isinstance(v, str)]:
            self.finding("INPUT", "CAPTURE_DATASET_MISMATCH", "La capture ne déclare pas l'identifiant du dataset demandé.",
                         "PROVEN", "HIGH", [_ev(cap["path"], None, None, "CAPTURE_FIELD")])
        self._freshness(doc, cap["path"])
        self._units(doc, cap["path"])
        self._joins(doc, cap["path"])
        self._replay(doc, cap["path"])
        return out

    def _ts_values(self, doc, pointer):
        vals = []
        for v, _ in resolve(doc, pointer):
            if isinstance(v, int) and not isinstance(v, bool) and 10**12 <= v < 10**13:
                vals.append(v)
            elif isinstance(v, str) and c.UTC_SECONDS.match(v):
                vals.append(_utc_ms(v))
        return vals

    def _freshness(self, doc, path):
        q = self.q
        as_of = _utc_ms(q["as_of_utc"])
        src = self._ts_values(doc, q["source_ts"])
        wr = self._ts_values(doc, q["write_ts"])
        mtime = self.r.stat_mtime_ms(path)
        f = {"as_of_utc": q["as_of_utc"], "max_source_age_ms": q["max_source_age_ms"],
             "source_event_ts": _iso(max(src)) if src else None, "source_age_ms": as_of - max(src) if src else None,
             "write_ts": _iso(max(wr)) if wr else None, "write_age_ms": as_of - max(wr) if wr else None,
             "mtime": _iso(mtime) if mtime is not None else None, "mtime_age_ms": as_of - mtime if mtime is not None else None,
             "mtime_used_as_evidence": False}
        f["classification"] = ("FRESHNESS_CANONICAL" if src and wr else "FRESHNESS_PARTIAL" if src or wr
                               else "MTIME_ONLY" if mtime is not None else "NO_FRESHNESS_CONTRACT")
        f["effective_source"] = "source_event_ts" if src else "write_ts" if wr else None
        ev = [_ev(path, None, q["source_ts"], "CAPTURE_FIELD")]
        if not src:
            f["verdict"] = "INCONCLUSIVE"
            self.finding("FRESHNESS", "SOURCE_TS_MISSING", "La capture ne porte pas d'heure source exploitable ; aucune fraîcheur n'est déduite du mtime.",
                         "PROVEN", "HIGH", ev)
        elif q["max_source_age_ms"] is None:
            f["verdict"] = "AGE_REPORTED_NO_THRESHOLD"
            self.finding("FRESHNESS", "SOURCE_AGE_REPORTED", f"Heure source la plus récente {f['source_event_ts']} ; aucun seuil de fraîcheur n'est déclaré pour ce dataset.",
                         "PROVEN", "HIGH", ev)
        elif f["source_age_ms"] > q["max_source_age_ms"]:
            f["verdict"] = "SOURCE_STALE"
            self.finding("FRESHNESS", "SOURCE_STALE", f"Donnée source périmée : âge {f['source_age_ms']} ms > seuil {q['max_source_age_ms']} ms.",
                         "PROVEN", "HIGH", ev)
            if mtime is not None and f["mtime_age_ms"] <= q["max_source_age_ms"]:
                self.finding("FRESHNESS", "MTIME_RECENT_SOURCE_STALE", "Le mtime est récent mais la source est périmée : le mtime ne masque pas l'âge de la donnée.",
                             "PROVEN", "HIGH", ev + [_ev(path, None, "mtime", "FILE_STAT")])
        else:
            f["verdict"] = "SOURCE_WITHIN_THRESHOLD"
            self.finding("FRESHNESS", "SOURCE_WITHIN_THRESHOLD", f"Heure source {f['source_event_ts']} dans le seuil déclaré.", "PROVEN", "HIGH", ev)
        self.freshness = f

    def _units(self, doc, path):
        for pointer, unit in sorted(self.q["units"].items()):
            vals = [v for v, _ in resolve(doc, pointer)]
            ev = [_ev(path, None, pointer, "CAPTURE_FIELD")]
            outer, rest = _outer(pointer)
            absent = 0 if outer is None else sum(1 for e, _ in resolve(doc, outer) if rest and not resolve(e, rest))
            if not vals or absent:
                self.finding("UNIT", "UNIT_MISSING", f"Champ {pointer} absent ({absent or 'toutes les'} occurrence(s)) : unité {unit} non vérifiable là où il manque.",
                             "PROVEN", "HIGH", ev)
            if not vals:
                continue
            bad = []
            for v in vals:
                if unit == "EPOCH_MS":
                    ok = isinstance(v, int) and not isinstance(v, bool) and 10**12 <= v < 10**13
                elif unit == "UTC_ISO_SECONDS":
                    ok = isinstance(v, str) and bool(c.UTC_SECONDS.match(v))
                elif unit == "DURATION_MS":
                    ok = isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 10**12
                elif unit == "DECIMAL_STRING_BPS":
                    ok = isinstance(v, str) and bool(DEC.match(v))
                else:
                    ok = isinstance(v, int) and not isinstance(v, bool) and v >= 0
                if not ok:
                    bad.append(v)
            if bad:
                self.finding("UNIT", "UNIT_INCOMPATIBLE", f"{len(bad)} valeur(s) de {pointer} incompatibles avec {unit} (ex. {json.dumps(bad[0])}).",
                             "PROVEN", "HIGH", ev)

    def _joins(self, doc, path):
        for j in self.q["join_checks"]:
            lo, lrest = _outer(j["left"])
            ro, rrest = _outer(j["right"])
            ev = [_ev(path, None, j["left"], "CAPTURE_FIELD"), _ev(path, None, j["right"], "CAPTURE_FIELD")]
            if lo is None or lo != ro:
                self.finding("JOIN", "JOIN_CHECK_NOT_ALIGNED", f"{j['left']} et {j['right']} n'ont pas le même tableau parent.", "INCONCLUSIVE", "LOW", ev)
                continue
            bad, seen = 0, 0
            for elem, _ in resolve(doc, lo):
                lv = [v for v, _ in resolve(elem, lrest)] if lrest else [elem]
                rv = [v for v, _ in resolve(elem, rrest)] if rrest else [elem]
                if not lv or not rv:
                    continue
                seen += 1
                a, b = lv[0], rv[0]
                ok = (a == b if j["relation"] == "EQUALS" else
                      isinstance(a, str) and isinstance(b, str) and a in b if j["relation"] == "CONTAINED_IN" else
                      isinstance(a, list) and isinstance(b, list) and len(a) == len(b))
                bad += not ok
            if seen == 0:
                self.finding("JOIN", "JOIN_KEYS_MISSING", f"Clés {j['left']} / {j['right']} absentes : jointure non vérifiable.", "INCONCLUSIVE", "MEDIUM", ev)
            elif bad:
                self.finding("JOIN", "JOIN_KEY_CONTRADICTION", f"{bad}/{seen} élément(s) contredisent {j['left']} {j['relation']} {j['right']}.", "PROVEN", "HIGH", ev)

    def _replay(self, doc, path):
        key = self.q["observation_key"]
        # L'enregistrement est le tableau le plus profond de la clé ; les autres champs
        # sont lus sur ses parents (le plus proche d'abord).
        deepest = max(key, key=lambda p: p.count("[*]"))
        base = deepest.rsplit("[*]", 1)[0] + "[*]"
        rows = resolve(doc, base)
        seen, distinct, dups, conflicts = {}, 0, 0, 0
        for rec, parents in rows:
            k = []
            for ptr in key:
                if ptr.startswith(base + "."):
                    vals = [v for v, _ in resolve(rec, ptr[len(base) + 1:])]
                else:
                    owner = next((p for p in reversed(parents) if isinstance(p, dict) and ptr.split(".")[-1] in p), None)
                    vals = [owner[ptr.split(".")[-1]]] if owner else []
                k.append(vals[0] if vals else None)
            kk = c.sha256_json(k)
            body = c.sha256_json(rec)
            if kk not in seen:
                seen[kk] = body
                distinct += 1
            elif seen[kk] == body:
                dups += 1
            else:
                conflicts += 1
        self.observations = {"records": len(rows), "distinct_observations": distinct,
                             "identical_replays": dups, "key_conflicts": conflicts, "key": key}
        ev = [_ev(path, None, base, "CAPTURE_FIELD")]
        if dups:
            self.finding("REPLAY", "IDENTICAL_REPLAY_COUNTED_ONCE", f"{dups} enregistrement(s) identiques à un précédent pour la même clé : comptés une seule fois ({distinct} observations distinctes).",
                         "PROVEN", "HIGH", ev)
        if conflicts:
            self.finding("REPLAY", "OBSERVATION_KEY_CONFLICT", f"{conflicts} enregistrement(s) partagent une clé avec un contenu différent : contradiction conservée, non dédupliquée.",
                         "PROVEN", "HIGH", ev)


def _dedup(items):
    return [json.loads(x) for x in sorted({json.dumps(u, sort_keys=True, ensure_ascii=False) for u in items})]


def _blocked(mission, code, detail, profile_read=None):
    m = mission if isinstance(mission, dict) else {}
    return {
        "contract": c.REPORT_CONTRACT, "auditor_version": AUDITOR_VERSION,
        "agent_id": m.get("agent_id") if isinstance(m.get("agent_id"), str) else None,
        "mission_id": m.get("mission_id") if isinstance(m.get("mission_id"), str) else None,
        "analyzed_ref": m.get("analyzed_ref") if isinstance(m.get("analyzed_ref"), dict) else None,
        "status": "BLOCKED", "chain": [], "findings": [], "inferred_links": [], "freshness": None,
        "capture": None, "observations": None, "unknowns": [], "runtime_measurements_required": [],
        "sources_consulted": [profile_read] if profile_read else [], "refused_paths": [],
        "errors": [{"code": code, "detail": detail}], "limits": LIMITS,
    }


def audit(mission, workspace_root, profile_root, *, clock=time.time_ns):
    """Exécute la mission et retourne le rapport scellé. N'écrit rien."""
    started = clock()
    perf0 = time.perf_counter_ns()
    tracemalloc.start()
    try:
        content = _audit_content(mission, workspace_root, profile_root)
    except Exception as exc:  # noqa: BLE001 — un échec interne devient FAILED, jamais un succès
        content = _blocked(mission, "INTERNAL_ERROR", type(exc).__name__)
        content["status"] = "FAILED"
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ended = clock()
    run = {"started_utc": _iso(started // 1_000_000), "ended_utc": _iso(ended // 1_000_000),
           "duration_ms": round((time.perf_counter_ns() - perf0) / 1e6, 3), "peak_traced_bytes": peak,
           "sources_read": len(content["sources_consulted"]),
           "bytes_read": sum(s["bytes"] for s in content["sources_consulted"])}
    return c.seal_report(content, run)


def _audit_content(mission, workspace_root, profile_root):
    try:
        c.validate_mission(mission)
    except c.MissionRejected as exc:
        return _blocked(mission, exc.code, exc.detail)
    # Version exacte du profil : blob git du fichier .agent.md, lu hors périmètre d'analyse.
    prof = mission["profile"]
    try:
        pdata = (Path(profile_root) / prof["source_path"]).read_bytes()
    except OSError:
        return _blocked(mission, "PROFILE_UNREADABLE", prof["source_path"])
    pread = {"path": "profile:" + prof["source_path"], "bytes": len(pdata), "sha256": hashlib.sha256(pdata).hexdigest()}
    if c.git_blob_sha1(pdata) != prof["blob_sha1"]:
        return _blocked(mission, "PROFILE_VERSION_MISMATCH", prof["source_path"], pread)
    b = mission["budget"]
    reader = ScopedReader(workspace_root, mission["scope"]["read_paths"], max_files=b["max_files"], max_bytes=b["max_bytes"])
    cap = reader.read(mission["capture"]["path"])
    if cap is None:
        rep = _blocked(mission, "CAPTURE_UNREADABLE", reader.refused.get(mission["capture"]["path"], ""), pread)
        rep["refused_paths"] = reader.refusals()
        return rep
    if hashlib.sha256(cap).hexdigest() != mission["capture"]["sha256"]:
        rep = _blocked(mission, "CAPTURE_FINGERPRINT_MISMATCH", mission["capture"]["path"], pread)
        rep["sources_consulted"] += reader.inventory()
        return rep
    run = _Run(mission, reader, None)
    budget_hit = None
    deadline = time.monotonic() + b["max_wall_ms"] / 1000
    try:
        run.index()
        if time.monotonic() > deadline:
            raise BudgetExceeded("max_wall_ms")
        run.code_chain()
    except BudgetExceeded as exc:
        budget_hit = str(exc)
        run.errors.append({"code": "BUDGET_EXCEEDED", "detail": budget_hit})
    run.freshness, run.observations = None, None
    capture_info = run.capture()
    for h in HOPS:
        run.chain.setdefault(h, {"hop": h, "level": "INCONCLUSIVE", "summary": "Non évalué (budget ou échec partiel).", "evidence": []})
    chain = [run.chain[h] for h in HOPS]
    all_proven = all(h["level"] == "PROVEN" for h in chain)
    if budget_hit and not any(h["level"] == "PROVEN" for h in chain):
        status = "FAILED"
    elif all_proven and capture_info["parsed"] and not budget_hit and not any(e["code"] == "SOURCE_UNPARSABLE" for e in run.errors):
        status = "COMPLETE"
    else:
        status = "PARTIAL"
    for f in run.findings:
        for e in f["evidence"]:
            if e.get("path") == mission["capture"]["path"]:
                e["file_sha256"] = mission["capture"]["sha256"]
    return {
        "contract": c.REPORT_CONTRACT, "auditor_version": AUDITOR_VERSION,
        "agent_id": mission["agent_id"], "profile": prof, "mission_id": mission["mission_id"],
        "analyzed_ref": mission["analyzed_ref"], "question": {"kind": mission["question"]["kind"],
                                                             "dataset_id": mission["question"]["dataset_id"]},
        "status": status,
        "chain": chain,
        "findings": sorted(run.findings, key=lambda f: (f["category"], f["code"], f["finding_id"])),
        "inferred_links": [h["hop"] for h in chain if h["level"] == "INFERRED"],
        "freshness": run.freshness, "capture": capture_info, "observations": run.observations,
        "unknowns": _dedup(run.unknowns),
        "runtime_measurements_required": _dedup(run.measurements),
        "sources_consulted": [pread] + reader.inventory(),
        "refused_paths": reader.refusals(),
        "errors": sorted(run.errors, key=lambda e: (e["code"], e["detail"])),
        "limits": LIMITS,
    }
