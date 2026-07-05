"""
dip/ — Decision Intelligence Platform.

Observateur pur du moteur de décision. Conforme ADR-0007 (passivité absolue).
Aucun module DIP ne modifie, intercepte ou retarde un DecisionPacket.

Modules:
    D01 decision_graph    — DAG par packet
    D02 decision_timeline — Timeline temporelle par packet
    D03 causal_tree       — Arbre causal + cause racine
    D04 counterfactual    — Simulation "et si?"
    D05 decision_heatmap  — Heatmaps multi-axes
    D06 decision_sankey   — Diagramme Sankey du funnel
    D07 decision_replay   — Replay interactif
    D08 explainability    — Score d'explicabilité
    D09 knowledge_base    — Base de connaissances accumulée
    D10 ai_investigator   — Investigation narrative IA
    D11 decision_diff     — Diff entre deux décisions
    D12 decision_alert    — Alertes temps réel
    D13 decision_export   — Export rapports scientifiques
    D14 audit_trail       — Journal d'audit immuable du DIP lui-même
"""

__version__ = "1.0.0"
