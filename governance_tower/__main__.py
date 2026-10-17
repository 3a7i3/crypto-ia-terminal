"""Point d'entrée local de Governance Tower (démo SYNTHETIC par défaut).

    python -m governance_tower serve [--port 8765] [--scenario nominal]
    python -m governance_tower ask "Quelle est la roadmap active ?" [--scenario nominal] [--json]

Les lectures réelles exigent des options explicites (``--github-live``,
``--host-snapshots DIR`` ou ``--host-operator-api URL``) et ne sont jamais
activées par défaut. Aucune de ces commandes ne déploie ni ne modifie quoi que
ce soit ; le serveur n'écoute que sur loopback.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from governance_tower.contracts import AgentRun, utc_now
from governance_tower.providers.github import AuthMode
from governance_tower.scenarios import SCENARIOS, demo_providers, live_providers
from governance_tower.sentinel.agent import Sentinel
from governance_tower.sentinel.audit import AuditLog


_GITHUB_AUTH = {"optional-token": AuthMode.OPTIONAL_TOKEN, "app-installation": AuthMode.APP_INSTALLATION}


def build_sentinel(args: argparse.Namespace) -> tuple[Sentinel, str | None]:
    audit = AuditLog(Path(args.audit_log)) if args.audit_log else None
    if args.github_live or args.host_snapshots or args.host_operator_api:
        github, host = live_providers(
            github_live=args.github_live,
            host_snapshots=Path(args.host_snapshots) if args.host_snapshots else None,
            host_operator_api=args.host_operator_api,
            github_auth=_GITHUB_AUTH[args.github_auth],
        )
        return Sentinel(github, host, utc_now, audit=audit), None
    github, host = demo_providers(args.scenario)
    return Sentinel(github, host, utc_now, audit=audit), args.scenario


def render_text(run: AgentRun) -> str:
    a = run.answer
    lines = [f"SENTINEL-01 · {run.mode} · {run.intent.value} · {run.run_id}", "", a.summary, ""]
    if a.refusals:
        lines.append("REFUS")
        lines += [f"  - {r.code} : {r.reason}" for r in a.refusals]
    if a.statements:
        lines.append("CONSTATS")
        lines += [f"  - [{s.claim_status.value}] {s.text}  {list(s.evidence_ids) or ''}" for s in a.statements]
    if a.diagnostics:
        lines.append("DIAGNOSTICS (observation → interprétation → à vérifier)")
        for d in a.diagnostics:
            lines.append(f"  - [{d.level.value}] {d.code.value} — {d.title}")
            lines.append(f"      observation : {d.observation}")
            lines.append(f"      interprétation possible : {d.interpretation}")
            lines += [f"      à vérifier : {v}" for v in d.verification]
            if d.proposal_ref:
                lines.append(f"      proposition (non exécutée) : {d.proposal_ref}")
    if a.excerpts:
        lines.append("EXTRAITS (contenu non fiable, cité)")
        for x in a.excerpts:
            lines.append(f"  - {x.repo}@{x.ref_sha[:12]}:{x.path} L{x.line_start}-L{x.line_end}/{x.total_lines}")
            lines += [f"      {n:>5} │ {t}" for n, t in enumerate(x.text.split("\n"), start=x.line_start)]
    if a.discrepancies:
        lines.append("ÉCARTS GITHUB / VPS")
        lines += [f"  - {d.classification.value} : {d.explanation}" for d in a.discrepancies]
    if a.uncertainties:
        lines.append("INCERTITUDES")
        lines += [f"  - {u}" for u in a.uncertainties]
    if a.proposals:
        lines.append("PROPOSITIONS NON EXÉCUTÉES")
        lines += [f"  - {p.title} (autorité {p.authority}, {p.execution})" for p in a.proposals]
    if a.untrusted_quotes:
        lines.append("CONTENU EXTERNE NON FIABLE (cité, jamais exécuté)")
        lines += [f"  > {q}" for q in a.untrusted_quotes]
    lines.append("")
    lines.append("PREUVES")
    lines += [f"  - {e.evidence_id} · {e.provenance.value} · {e.locator}" for e in run.evidence]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="governance_tower", description="Governance Tower — SENTINEL-01 (READ-ONLY)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("serve", "ask"):
        p = sub.add_parser(name)
        p.add_argument("--scenario", default="nominal", choices=sorted(SCENARIOS))
        p.add_argument("--github-live", action="store_true", help="lecture GitHub réelle (GET, opt-in)")
        p.add_argument(
            "--github-auth",
            default="optional-token",
            choices=sorted(_GITHUB_AUTH),
            help="optional-token : jeton GT_GITHUB_TOKEN facultatif, non attesté ; app-installation : jeton "
            "d'installation de l'App Sentinel obligatoire (GT_SENTINEL_INSTALLATION_TOKEN, GT_SENTINEL_APP_SLUG)",
        )
        p.add_argument("--host-snapshots", help="dossier local de snapshots publiés (opt-in)")
        p.add_argument("--host-operator-api", help="URL loopback de l'Operator API (opt-in)")
        p.add_argument("--audit-log", help="fichier de journal d'audit local (opt-in)")
        if name == "serve":
            p.add_argument("--host", default="127.0.0.1")
            p.add_argument("--port", type=int, default=8765)
        else:
            p.add_argument("question")
            p.add_argument("--shortcut", default=None)
            p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.github_auth != "optional-token" and not args.github_live:
        parser.error("--github-auth app-installation exige --github-live")
    sentinel, scenario = build_sentinel(args)

    if args.command == "ask":
        run = sentinel.ask(args.question, args.shortcut)
        print(json.dumps(run.to_dict(), ensure_ascii=False, indent=2) if args.json else render_text(run))
        return 0

    from governance_tower.server import make_server

    sentinel.prime()
    server = make_server(sentinel, args.host, args.port, scenario)
    host, port = server.server_address[:2]
    print(f"Governance Tower (READ ONLY, {sentinel.mode}) sur http://{host}:{port}/ — Ctrl+C pour arrêter", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
