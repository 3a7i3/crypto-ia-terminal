"""
dip/cli.py — Interface ligne de commande du Decision Intelligence Platform.

Usage:
    python -m dip graph <packet_id>
    python -m dip causal <packet_id>
    python -m dip replay <packet_id> [--step]
    python -m dip diff <packet_id_a> <packet_id_b>
    python -m dip counterfactual <packet_id> [--layer <layer>]
    python -m dip explain <packet_id>
    python -m dip investigate <packet_id>
    python -m dip heatmap [--hours 168] [--type symbol|regime]
    python -m dip sankey [--hours 24] [--symbol BTCUSDT]
    python -m dip alerts [--severity HIGH]
    python -m dip report [--hours 168] [--format json|csv|md]
    python -m dip export <packet_id>
    python -m dip audit [--hours 24]
    python -m dip kb [--symbol BTCUSDT] [--regime SIDEWAYS]
    python -m dip health
    python -m dip metrics [--hours 24]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

# ── Formatters ────────────────────────────────────────────────────────────────


def _print_json(obj) -> None:
    import dataclasses

    def _default(o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if hasattr(o, "value"):
            return o.value
        return str(o)

    print(json.dumps(obj, indent=2, default=_default, ensure_ascii=False))


def _print_table(rows: list[dict], cols: list[str]) -> None:
    if not rows:
        print("(aucune donnée)")
        return
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for r in rows:
        print(" | ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))


def _err(msg: str) -> None:
    print(f"[ERREUR] {msg}", file=sys.stderr)


# ── Commandes ─────────────────────────────────────────────────────────────────


def cmd_graph(args) -> int:
    from dip.modules.decision_graph import get_graph_engine

    engine = get_graph_engine()
    graph = engine.get_graph(args.packet_id)
    if not graph:
        _err(f"Graph non trouvé pour packet_id={args.packet_id}")
        return 1
    print(f"=== Graph — {graph.packet_id} ===")
    print(f"Statut: {graph.status.value}  |  Profondeur: {graph.metrics.depth}")
    print(
        f"Confiance: {graph.metrics.confidence_start:.2f} → {graph.metrics.confidence_end:.2f}"
    )
    print(f"\nCouches traversées ({len(graph.nodes)}):")
    for n in graph.nodes:
        blocker = " ← BLOQUEUR" if n.status.value == "BLOCKED" else ""
        print(
            f"  {n.layer:<25} {n.status.value:<10}  conf={n.confidence_after:.3f}{blocker}"
        )
    if graph.metrics.rejection_layer:
        print(f"\nBloqueur principal: {graph.metrics.rejection_layer}")
        print(f"Raison: {graph.metrics.rejection_reason}")
    return 0


def cmd_causal(args) -> int:
    from dip.modules.causal_tree import get_causal_tree_engine

    engine = get_causal_tree_engine()
    tree = engine.build_causal_tree(args.packet_id)
    if not tree:
        _err(f"Arbre causal non trouvé pour {args.packet_id}")
        return 1
    rc = tree.root_cause
    print(f"=== Arbre Causal — {tree.packet_id} ===")
    print(f"Résultat: {tree.result}")
    print(f"Cause racine: [{rc.cause_type}] {rc.causing_layer}")
    print(f"Description: {rc.description}")
    print(f"Confiance: {rc.confidence:.2f}")
    if rc.contributing_factors:
        print("\nFacteurs contributifs:")
        for f in rc.contributing_factors:
            print(f"  - {f.factor}  (force={f.strength:.2f}, layer={f.layer})")
    return 0


def cmd_explain(args) -> int:
    from dip.modules.explainability import get_explainability_engine

    engine = get_explainability_engine()
    score = engine.compute_score(args.packet_id)
    if not score:
        _err(f"Score d'explicabilité non trouvé pour {args.packet_id}")
        return 1
    print(f"=== Explicabilité — {score.packet_id} ===")
    print(f"Score global: {score.global_score:.3f}  Grade: {score.grade}")
    print("\nDimensions:")
    for d in score.dimensions:
        print(f"  {d.dimension:<30} {d.score:.3f} (poids={d.weight:.2f})")
        print(f"    → {d.detail}")
    if score.recommendations:
        print("\nRecommandations:")
        for r in score.recommendations:
            print(f"  [{r.priority}] {r.dimension}: {r.recommendation}")
    return 0


def cmd_counterfactual(args) -> int:
    from dip.modules.counterfactual import get_counterfactual_engine

    engine = get_counterfactual_engine()
    layer = args.layer or "NoTradeLayer"
    result = engine.simulate_without_layer(args.packet_id, layer)
    if not result:
        _err(f"Simulation impossible pour {args.packet_id}")
        return 1
    print(f"=== Contrefactuel — {result.packet_id} ===")
    print(f"Scénario: {result.scenario.description}")
    print(f"Résultat original: {result.original_status.value}")
    print(f"Résultat simulé:   {result.counterfactual_status.value}")
    print(f"Résultat changé:   {'OUI' if result.impact.outcome_changed else 'NON'}")
    print(f"Δ confiance:       {result.confidence_delta:+.3f}")
    print(f"Impact PnL estimé: ${result.impact.estimated_pnl_impact:+.2f}")
    print(f"Confiance sim.:    {result.confidence:.2f}")
    print(f"\n⚠ {result.disclaimer}")
    return 0


def cmd_replay(args) -> int:
    from dip.modules.decision_replay import get_replay_engine

    engine = get_replay_engine()
    session = engine.build_replay(args.packet_id)
    if not session:
        _err(f"Replay non trouvé pour {args.packet_id}")
        return 1

    print(f"=== Replay — {session.packet_id} ===")
    print(
        f"Symbole: {session.symbol} | Direction: {session.direction} | Régime: {session.regime}"
    )
    print(f"Résultat final: {session.final_status}  |  Étapes: {session.total_steps}")

    if args.step:
        # Mode interactif step-by-step
        replay_id = engine.start_interactive(args.packet_id)
        ir = engine.get_replay(replay_id)
        print(
            "\nMode interactif (ENTER=suivant, b=précédent, q=quitter, B=sauter au bloqueur)"
        )
        while True:
            state = ir.current_state()
            if state.is_finished:
                print(
                    f"\n--- FIN --- Résultat: {'APPROUVÉ' if state.is_approved else 'REJETÉ'}"
                )
                break
            try:
                cmd = input(f"[{state.current_step}/{state.total_steps}] > ").strip()
            except (KeyboardInterrupt, EOFError):
                break
            if cmd in ("q", "quit"):
                break
            elif cmd == "b":
                s = ir.step_backward()
                if s:
                    print(f"  ← {s.layer}: {s.status.value}")
            elif cmd == "B":
                s = ir.jump_to_blocker()
                if s:
                    print(f"  → Bloqueur: {s.layer}")
                else:
                    print("  Aucun bloqueur trouvé")
            else:
                s = ir.step_forward()
                if s:
                    blocker = " ← BLOQUEUR" if s.is_blocker else ""
                    print(
                        f"  {s.step_index}: {s.layer:<25} {s.status.value}{blocker}  conf={s.confidence_after:.3f}"
                    )
        engine.close(replay_id)
    else:
        # Mode liste complète
        for step in session.steps:
            blocker = " ← BLOQUEUR" if step.is_blocker else ""
            print(
                f"  {step.step_index:2d}: {step.layer:<25} {step.status.value:<10}  conf={step.confidence_after:.3f}{blocker}"
            )
    return 0


def cmd_diff(args) -> int:
    from dip.modules.decision_diff import get_diff_engine

    engine = get_diff_engine()
    diff = engine.diff(args.packet_id_a, args.packet_id_b)
    if not diff:
        _err("Diff impossible (un ou deux packets introuvables)")
        return 1
    print(f"=== Diff — {diff.packet_id_a[:8]} vs {diff.packet_id_b[:8]} ===")
    print(f"Résumé: {diff.summary}")
    print(f"\nContexte:")
    for cd in diff.context_diffs:
        mark = "*" if cd.changed else " "
        print(f"  {mark} {cd.field:<15} {cd.value_a!r:<20} → {cd.value_b!r}")
    changed_layers = [ld for ld in diff.layer_diffs if ld.status_changed]
    if changed_layers:
        print(f"\nCouches différentes ({len(changed_layers)}):")
        for ld in changed_layers:
            print(
                f"  {ld.layer:<25} {ld.status_a} → {ld.status_b}  Δconf={ld.confidence_delta:+.3f}"
            )
    return 0


def cmd_investigate(args) -> int:
    from dip.modules.ai_investigator import get_investigator_engine

    engine = get_investigator_engine()
    result = engine.investigate(args.packet_id)
    print(f"=== Investigation — {result.packet_id} ===")
    print(
        f"Source: {result.source} | Modèle: {result.model} | Latence: {result.latency_ms}ms"
    )
    print(f"Confiance: {result.confidence:.2f}")
    print(f"\n[HYPOTHÈSE]\n{result.hypothesis}")
    print(f"\n[ANALYSE]\n{result.root_cause_analysis}")
    print(f"\n[OBSERVATION]\n{result.recommendations}")
    print(f"\n⚠ {result.disclaimer}")
    return 0


def cmd_heatmap(args) -> int:
    from dip.modules.decision_heatmap import get_heatmap_engine

    engine = get_heatmap_engine()
    htype = getattr(args, "type", "symbol")
    if htype == "regime":
        matrix = engine.generate_regime_layer_heatmap(hours=args.hours)
    else:
        matrix = engine.generate_symbol_layer_heatmap(hours=args.hours)

    print(f"=== Heatmap {matrix.heatmap_type.value} — {args.hours}h ===")
    print(f"Décisions analysées: {matrix.total_decisions}")
    hot = [c for c in matrix.cells if c.is_hot_spot]
    cold = [c for c in matrix.cells if c.is_cold_spot]
    print(f"Hot spots: {len(hot)}  |  Cold spots: {len(cold)}")
    if hot:
        print("\nTop hot spots:")
        for c in sorted(hot, key=lambda x: x.value, reverse=True)[:5]:
            print(
                f"  {c.x_value} × {c.y_value}: {c.value:.0%} rejet ({c.count} décisions)"
            )
    if matrix.insights:
        print("\nInsights:")
        for ins in matrix.insights[:5]:
            print(f"  [{ins.severity.value}] {ins.description}")
    return 0


def cmd_sankey(args) -> int:
    from dip.modules.decision_sankey import get_sankey_engine

    engine = get_sankey_engine()
    diagram = engine.generate_sankey(hours=args.hours, symbol=args.symbol)
    funnel = diagram.funnel
    print(f"=== Sankey — {args.hours}h ===")
    print(f"Total packets: {diagram.total_packets}")
    print(f"Taux d'approbation: {funnel.overall_conversion:.1%}")
    print(f"Goulet principal: {funnel.biggest_bottleneck}")
    print("\nConversion par couche:")
    for lc in funnel.conversion_by_layer:
        bar = "█" * int(lc.pass_rate * 20) + "░" * (20 - int(lc.pass_rate * 20))
        print(f"  {lc.layer:<25} {bar} {lc.pass_rate:.0%}  ({lc.reject_count} rejets)")
    return 0


def cmd_alerts(args) -> int:
    from dip.modules.decision_alert import Severity, get_alert_engine

    engine = get_alert_engine()
    severity = None
    if args.severity:
        try:
            severity = Severity(args.severity)
        except ValueError:
            _err(f"Sévérité invalide: {args.severity}")
            return 1
    alerts = engine.get_active_alerts(severity=severity)
    summary = engine.get_summary()
    print(f"=== Alertes actives — {summary.top_severity} ===")
    print(
        f"Total: {summary.total_active}  |  Critique: {summary.critical_count}  |  Warning: {summary.warning_count}"
    )
    if not alerts:
        print("\nAucune alerte active.")
    else:
        print()
        for a in alerts:
            print(f"[{a.severity.value}] {a.title}")
            print(f"  {a.description}")
            print(
                f"  Règle: {a.rule_id}  |  Seuil: {a.threshold:.2f}  |  Valeur: {a.metric_value:.3f}"
            )
            print()
    return 0


def cmd_report(args) -> int:
    from dip.modules.decision_export import get_export_engine

    engine = get_export_engine()
    fmt = args.format or "md"

    if fmt == "json":
        result = engine.export_json(hours=args.hours)
    elif fmt == "csv":
        result = engine.export_csv(hours=args.hours)
    else:
        result = engine.export_markdown(hours=args.hours)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result.content)
        print(
            f"Rapport exporté → {args.output}  ({result.size_bytes} bytes, {result.decision_count} décisions)"
        )
    else:
        print(result.content)
    return 0


def cmd_export(args) -> int:
    from dip.modules.decision_export import get_export_engine

    engine = get_export_engine()
    result = engine.export_packet(args.packet_id)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result.content)
        print(f"Packet exporté → {args.output}")
    else:
        print(result.content)
    return 0


def cmd_audit(args) -> int:
    from dip.modules.audit_trail import get_audit_trail

    trail = get_audit_trail()
    report = trail.generate_report(hours=args.hours)
    print(f"=== Audit Trail — {args.hours}h ===")
    print(f"Entrées totales: {report.total_entries}")
    print(f"Échecs d'intégrité: {report.integrity_failures}")
    if report.entries_by_module:
        print("\nPar module:")
        for m, c in sorted(report.entries_by_module.items(), key=lambda x: -x[1]):
            print(f"  {m:<35} {c}")
    if report.entries_by_action:
        print("\nPar action:")
        for a, c in sorted(report.entries_by_action.items(), key=lambda x: -x[1]):
            print(f"  {a:<35} {c}")
    return 0


def cmd_kb(args) -> int:
    from dip.modules.knowledge_base import get_knowledge_base

    kb = get_knowledge_base()
    summary = kb.get_knowledge_summary()
    print(f"=== Knowledge Base ===")
    print(f"Entries: {summary.total_entries}  |  Règles: {summary.total_rules}")
    print(f"Taux d'approbation global: {summary.overall_approval_rate:.1%}")
    print(f"Couche bloquante dominante: {summary.top_rejection_cause}")
    print(f"Régime dominant (rejets): {summary.top_rejection_regime}")

    patterns = kb.query_patterns(
        symbol=args.symbol,
        regime=args.regime,
    )
    if patterns:
        print(f"\nPatterns ({len(patterns)}):")
        for p in patterns[:10]:
            print(f"  [{p.entry_type.value}] {p.description}  conf={p.confidence:.2f}")
    else:
        print("\nAucun pattern (seuil N≥50 non atteint)")

    if args.drift:
        report = kb.detect_drift("rejection_rate")
        print(f"\nDrift 'rejection_rate': {report.severity}")
        print(
            f"  Actuel={report.current_value:.2%}  Historique={report.historical_value:.2%}  z={report.z_score:.1f}"
        )
    return 0


def cmd_health(args) -> int:
    from dip.core.store import DIPStore

    store = DIPStore.instance()
    total = store.count_decisions()
    alerts = store.get_active_alerts()
    knowledge = store.get_knowledge()

    print("=== DIP Health ===")
    print(f"Décisions indexées: {total}")
    print(f"Alertes actives:    {len(alerts)}")
    print(f"Entries KB:         {len(knowledge)}")
    print(f"Store:              OK")
    print(f"\nStatus global: {'OK' if len(alerts) == 0 else 'WARNING'}")
    return 0


def cmd_metrics(args) -> int:
    from dip.core.store import DIPStore
    from dip.core.types import now_us

    store = DIPStore.instance()
    start_us = now_us() - args.hours * 3_600_000_000
    rows = store.get_decisions(start_us=start_us, limit=10_000)
    total = len(rows)
    if total == 0:
        print(f"Aucune décision dans les dernières {args.hours}h")
        return 0
    approved = sum(1 for r in rows if r.get("status") == "APPROVED")
    rejection_rate = (total - approved) / total
    layers: dict[str, int] = {}
    for r in rows:
        lyr = r.get("root_cause_layer")
        if lyr:
            layers[lyr] = layers.get(lyr, 0) + 1

    print(f"=== Métriques DIP — {args.hours}h ===")
    print(f"Décisions:          {total}")
    print(f"Approuvées:         {approved} ({approved/total:.1%})")
    print(f"Rejetées:           {total-approved} ({rejection_rate:.1%})")
    print(f"\nTop couches bloquantes:")
    for layer, cnt in sorted(layers.items(), key=lambda x: -x[1])[:5]:
        print(f"  {layer:<30} {cnt:4d} ({cnt/total:.1%})")
    return 0


# ── Main ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dip",
        description="Decision Intelligence Platform — observateur passif du moteur de trading",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # graph
    sp = sub.add_parser("graph", help="Affiche le DAG décisionnel d'un packet")
    sp.add_argument("packet_id")

    # causal
    sp = sub.add_parser("causal", help="Arbre causal d'un packet")
    sp.add_argument("packet_id")

    # explain
    sp = sub.add_parser("explain", help="Score d'explicabilité d'un packet")
    sp.add_argument("packet_id")

    # counterfactual
    sp = sub.add_parser("counterfactual", help="Simulation contrefactuelle")
    sp.add_argument("packet_id")
    sp.add_argument("--layer", default=None, help="Couche à supprimer")

    # replay
    sp = sub.add_parser("replay", help="Replay step-by-step d'un packet")
    sp.add_argument("packet_id")
    sp.add_argument("--step", action="store_true", help="Mode interactif")

    # diff
    sp = sub.add_parser("diff", help="Compare deux packets")
    sp.add_argument("packet_id_a")
    sp.add_argument("packet_id_b")

    # investigate
    sp = sub.add_parser("investigate", help="Investigation narrative IA")
    sp.add_argument("packet_id")

    # heatmap
    sp = sub.add_parser("heatmap", help="Heatmap des décisions")
    sp.add_argument("--hours", type=int, default=168)
    sp.add_argument("--type", choices=["symbol", "regime"], default="symbol")

    # sankey
    sp = sub.add_parser("sankey", help="Diagramme Sankey du funnel")
    sp.add_argument("--hours", type=int, default=24)
    sp.add_argument("--symbol", default=None)

    # alerts
    sp = sub.add_parser("alerts", help="Alertes actives")
    sp.add_argument("--severity", default=None, help="Filtrer par sévérité")

    # report
    sp = sub.add_parser("report", help="Rapport scientifique")
    sp.add_argument("--hours", type=int, default=168)
    sp.add_argument("--format", choices=["json", "csv", "md"], default="md")
    sp.add_argument("--output", default=None, help="Fichier de sortie")

    # export
    sp = sub.add_parser("export", help="Export complet d'un packet")
    sp.add_argument("packet_id")
    sp.add_argument("--output", default=None)

    # audit
    sp = sub.add_parser("audit", help="Journal d'audit DIP")
    sp.add_argument("--hours", type=int, default=24)

    # kb
    sp = sub.add_parser("kb", help="Base de connaissances")
    sp.add_argument("--symbol", default=None)
    sp.add_argument("--regime", default=None)
    sp.add_argument("--drift", action="store_true", help="Détecter les dérives")

    # health
    sub.add_parser("health", help="Santé du DIP")

    # metrics
    sp = sub.add_parser("metrics", help="Métriques agrégées")
    sp.add_argument("--hours", type=int, default=24)

    return p


_COMMANDS = {
    "graph": cmd_graph,
    "causal": cmd_causal,
    "explain": cmd_explain,
    "counterfactual": cmd_counterfactual,
    "replay": cmd_replay,
    "diff": cmd_diff,
    "investigate": cmd_investigate,
    "heatmap": cmd_heatmap,
    "sankey": cmd_sankey,
    "alerts": cmd_alerts,
    "report": cmd_report,
    "export": cmd_export,
    "audit": cmd_audit,
    "kb": cmd_kb,
    "health": cmd_health,
    "metrics": cmd_metrics,
}


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = _COMMANDS.get(args.command)
    if not handler:
        _err(f"Commande inconnue: {args.command}")
        return 2
    try:
        return handler(args)
    except Exception as e:
        _err(f"Erreur inattendue: {e}")
        if "--debug" in sys.argv:
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
