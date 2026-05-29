# Dashboards — Consolidation

Un seul dashboard actif : **dashboard_master.py**

Les autres dashboards sont conservés comme archives de référence mais ne sont plus appelés par le runtime.

Pour lancer le dashboard :
```bash
python infra/dashboards/dashboard_master.py
```

Liste des dashboards archivés (ne pas utiliser directement) :
- dashboard_hub.py, dashboard_live.py, dashboard_risk.py
- dashboard_positions.py, dashboard_unified.py
- dashboard_compare_multi.py, dashboard_decision_trace.py
- dashboard_multi_exchange.py, command_center_dashboard.py
- dashboard_p6_panel.py, evolution_dashboard.py
