# ADR-0009 — SDOS Terminal comme interface d'observation, abrogation de la règle Telegram-only

**Date :** 2026-07-02
**Statut :** Accepté
**Auteur :** Mathieu

---

## Contexte

Le nettoyage du 2026-06-05 (voir mémoire de session, non formalisé en ADR à l'époque) avait
supprimé l'ensemble des dashboards et visualisations du projet (`dashboard/`, `frontend/` React/Vite,
`infra/visualization/`, `infra/panels/`, `quant_hedge_ai/dashboard/`, `tracker_system/dashboard/`,
`pieuvre/dashboard/`, `capital_deployment/chart_server.py`, `monitor/`, `monitoring/`) au nom d'un
principe de concentration : « la machine doit être 100% focalisée sur le trading quantitatif
autonome, Telegram = seule interface humaine avec la machine ».

Depuis, deux couches ont été reconstruites sans qu'une décision d'architecture ne l'acte
formellement :

- `visualization/` — bibliothèque backend pure (`api/*.py`, `renderers/*.py`, `ves/` — Visualization
  Engine Selector) qui lit les sources canoniques (`databases/system_state.json`,
  `databases/live_snapshot.json`, `cache/burn_in_reports/burnin_v3.json`,
  `databases/decision_packets_*.jsonl`, `databases/certifications/observer_cert_history.jsonl`,
  `databases/dip/dip.sqlite`) et les assemble en snapshots typés.
- `sdos_terminal/` — serveur FastAPI + React/Vite (`sdos_terminal/api/app.py`, port 8765) qui
  expose `visualization/` en HTTP : endpoints JSON (`/api/health`, `/api/pipeline`, `/api/portfolio`,
  `/api/scientific`, `/api/timeline`, `/api/datasets`, `/api/system`), endpoints PNG, WebSocket
  `/ws/live`. Le frontend contient déjà `HealthPanel`, `PipelinePanel`, `TimelinePanel`,
  `PortfolioPanel`, `ScientificPanel`, `DatasetsPanel` — fonctionnel, pas un squelette.

Ni `docs/adr/0008-scientific-intelligence-layer.md`, ni `docs/dip/DIP_OPERATIONS_MANUAL.md` ne
mentionnent `sdos_terminal`, « dashboard » ou « frontend » : le pivot existe en code mais pas en
gouvernance. Séparément, `crypto-dashboard.service` (VPS, systemd) référence encore
`dashboard_decision_trace.py`, un script Streamlit supprimé lors du gel architectural
(`fc96f66`) — ce service est un résidu de l'ancienne génération de dashboards, non lié à
`sdos_terminal`, et `deploy/setup_vps.sh` n'a pas été mis à jour après la migration.

## Décision

**La règle « Telegram = seule interface » (nettoyage 2026-06-05) est abrogée.**

`sdos_terminal/` (consommant `visualization/`) est désormais l'interface d'observation de
référence du projet, en complément de Telegram — pas en remplacement. Répartition des rôles :

- **Telegram** : notifications push temps réel (trade ouvert/fermé, kill switch, alertes) et
  commandes opérateur ponctuelles (`/status`, `/positions`, `/pnl`, `/pause`, `/resume`).
- **SDOS Terminal** : exploration et audit — état du pipeline de décision par couche, historique
  des refus, timeline des `DecisionPacket`, certification scientifique, burn-in, santé système.
  Il remplace la lecture manuelle de logs (`tail -f`, `grep`, `cat trades.jsonl`) par des vues
  structurées.

Cette réhabilitation reste strictement compatible avec le gel fonctionnel (Scientific Debt Rule) :
`sdos_terminal` et `visualization` sont des **outils de mesure et d'audit**, catégorie
explicitement autorisée par le CLAUDE.md même en phase de gel. Ils respectent le principe de
passivité (ADR-0007) : lecture seule, aucune écriture vers le pipeline de décision.

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| Maintenir Telegram comme seule interface | Devenu impraticable dès que le volume d'information (pipeline multi-couches, DIP, burn-in) dépasse ce qu'un flux de messages peut représenter lisiblement |
| Réintroduire les anciens dashboards Streamlit (`dashboard_decision_trace.py`, etc.) | Explicitement écartés par le gel architectural `fc96f66` ; `sdos_terminal`/`visualization` sont une reconstruction propre, pas un retour en arrière |
| Créer une nouvelle couche décisionnelle affichée dans le dashboard | Interdit par ADR-0007 : un dashboard ne peut être qu'un observateur passif |

## Conséquences

**Positives :**
- Comble un point mort opérationnel : les investigations répétitives par log deviennent des vues
  du terminal (pipeline par couche, reject analyzer, timeline)
- Aligne la gouvernance documentée sur l'état réel du code (`sdos_terminal` existait déjà,
  non documenté)
- N'introduit aucune nouvelle variable expérimentale : lecture seule des sources déjà canoniques

**Négatives / compromis :**
- Deux surfaces d'observation à maintenir (Telegram + SDOS Terminal) au lieu d'une seule
- `crypto-dashboard.service` (VPS) reste un résidu à traiter séparément (référence un script
  supprimé) — non couvert par cet ADR, action de suivi distincte

**Règles induites :**
- Tout nouveau panneau du SDOS Terminal doit rester un observateur passif (ADR-0007) : lecture
  seule des sources canoniques, aucune écriture vers le pipeline de décision
- Avant de développer un nouveau panneau, vérifier l'existant dans `sdos_terminal/frontend/src/`
  et `visualization/api/` pour éviter la duplication
- `deploy/setup_vps.sh` et le service `crypto-dashboard.service` doivent être mis à jour ou
  retirés pour ne plus référencer l'ancienne génération de dashboards Streamlit
