"""CLI : python -m lab01 {run,verify,check,serve}."""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="lab01", description="LAB-01 (SYNTHETIC, sans réseau)"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="exécute les scénarios et écrit les artefacts")
    r.add_argument("--out", required=True)
    r.add_argument("--scenario", action="append")
    sub.add_parser("verify", help="rejoue deux fois et compare les empreintes")
    c = sub.add_parser("check", help="relit les journaux écrits et vérifie les chaînes")
    c.add_argument("--out", required=True)
    s = sub.add_parser("serve", help="API GET-only + interface (127.0.0.1)")
    s.add_argument("--out", required=True)
    s.add_argument("--port", type=int, default=18090)
    s.add_argument("--token-file", required=True)
    e = sub.add_parser(
        "export", help="exporte des rapports nettoyés vers un dossier lisible"
    )
    e.add_argument("--src", required=True)
    e.add_argument("--dst", required=True)
    q = sub.add_parser(
        "prune", help="liste (défaut) ou supprime les plus anciennes expériences"
    )
    q.add_argument("--out", required=True)
    q.add_argument("--keep", type=int, default=20)
    q.add_argument(
        "--apply", action="store_true", help="supprime réellement (jamais par défaut)"
    )
    a = ap.parse_args(argv)

    from lab01 import runner

    if a.cmd == "run":
        res = runner.run_all(a.out, a.scenario)
        for x in res:
            print(f"{x['verdict']:4} {x['experiment_id']} {x['final_state']}")
        return 0 if all(x["verdict"] == "PASS" for x in res) else 1
    if a.cmd == "verify":
        rep = runner.verify_reproducible()
        print(json.dumps(rep, indent=2))
        return (
            0
            if all(
                x["reproducible"] and x["chain_valid"] and x["verdict"] == "PASS"
                for x in rep
            )
            else 1
        )
    if a.cmd == "check":
        rep = runner.verify_written(a.out)
        print(json.dumps(rep, indent=2))
        return 0 if rep and all(x["chain_valid"] for x in rep) else 1
    if a.cmd == "export":
        from lab01 import export

        rep = export.export_reports(a.src, a.dst)
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 0 if not rep["rejected"] else 1
    if a.cmd == "prune":
        from lab01 import retention

        rep = retention.prune(a.out, keep=a.keep, apply=a.apply)
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 0
    from lab01.api import serve

    serve(a.out, a.port, a.token_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
