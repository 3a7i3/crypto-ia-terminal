# ADR-0003 — DecisionExplainer : observabilité du pipeline décisionnel via Telegram

**Date :** 2026-06-29
**Statut :** Accepté
**Auteur :** Mathieu

---

## Contexte

Le moteur dispose de 12 couches décisionnelles (Authority, Meta-Strategy, Gate, Self-Awareness,
Conviction, No-Trade, Portfolio Brain, Capital Allocation, Mistake Memory, Executive Override,
Threat Radar, Arbitrator). Chacune peut bloquer un trade. Aujourd'hui, Telegram affiche
"PRET A TRADER" ou "BLOQUE" sans préciser quelle couche a refusé, avec quel score, pour
quelle raison. Un opérateur doit consulter les logs fichiers pour comprendre une décision,
ce qui rend le suivi opérationnel en temps réel impossible.

## Décision

Créer `observability/decision_explainer.py` : un module passif qui reçoit une
`DecisionObservation` et produit un message Telegram structuré, hiérarchisé et exhaustif.
Le premier bloqueur est visible en 2 lignes. Toutes les couches sont résumées sur une ligne
chacune. Le message est auto-suffisant — aucun accès aux logs n'est nécessaire pour comprendre
la décision.

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| Enrichir les logs existants | Les logs fichiers ne sont pas lisibles en temps réel par un opérateur |
| Dashboard web Streamlit | Ajoute une dépendance UI, exige un navigateur, non disponible sur VPS sans tunnel |
| Enrichir directement `_build_alert()` | Couple le formattage à advisor_loop, viole la séparation des responsabilités |
| Telegram MarkdownV2 | Parsing trop fragile avec les symboles crypto (caractères spéciaux, underscores) |

## Conséquences

**Positives :**
- Un opérateur comprend toute décision en < 10 secondes sur mobile
- Le formateur est entièrement passif : zéro effet sur le pipeline de décision
- Testable indépendamment (unit tests sur chaînes de texte)
- Pas de dépendance externe supplémentaire

**Négatives / compromis :**
- Messages plus longs (~40 lignes vs ~8 lignes actuellement) — reste dans la limite Telegram 4096 chars
- Le dédup 5 min de TelegramAlert doit être désactivé pour les `decision_report()` (chaque signal est unique)

**Règles induites :**
- `DecisionExplainer` ne reçoit que des `DecisionObservation` — jamais de dict brut, jamais d'accès direct aux agents
- Toute modification de format Telegram passe par `decision_explainer.py`, pas par `advisor_loop.py`
- Le module ne lève jamais d'exception en production (try/except global avec fallback texte simple)
