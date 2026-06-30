# CLAUDE.md — Règles invariantes du projet crypto_ai_terminal

Ces règles s'appliquent à toutes les sessions, sans exception.

---

## Règle constitutionnelle — Passivité absolue des observers (ADR-0007)

> Le moteur de décision est le seul composant autorisé à prendre une décision de trading.
> Tous les autres composants (observabilité, télémétrie, regret, calibration, gouvernance,
> laboratoire, replay, IA) sont strictement passifs. Ils peuvent observer, enregistrer,
> simuler, expliquer et recommander, mais ils ne peuvent jamais influencer une décision
> en temps réel. Toute évolution des paramètres doit être validée explicitement par
> l'opérateur et appliquée via un processus de configuration versionné.

**Conséquence directe :** `FEATURE_AUTO_CALIBRATION=false` est le défaut permanent.
Aucune exception sans ADR signé par l'opérateur.

---

## Règle du statisticien — Validation empirique obligatoire

> Aucun paramètre du moteur de trading ne peut être modifié sur la base d'une intuition,
> d'une observation isolée ou d'un faible échantillon. Toute proposition de calibration
> doit être accompagnée d'une justification statistique (taille d'échantillon, intervalles
> de confiance, puissance statistique, impact attendu sur les métriques de risque et de
> performance) et être validée par un opérateur humain avant toute application.

**Seuil minimum absolu avant toute calibration :**

| Catégorie              | Minimum |
|------------------------|---------|
| Trades totaux          | 500     |
| Winners                | 150     |
| Losers                 | 150     |
| MISSED_WIN (regret)    | 100     |
| GOOD_REFUSAL (regret)  | 100     |
| Par régime de marché   | 50      |
| Par couche bloqueuse   | 30      |
| Calibration Readiness Index (CRI) | ≥ 90/100 |

Tant que ces seuils ne sont pas atteints : **ACE interdit, zéro modification de seuil**.

---

## Phase actuelle : Validation Scientifique (gel fonctionnel étendu)

Le développement fonctionnel est **gelé**. Sont désormais **interdits** :

- Nouvelles couches IA ou décisionnelles
- Nouveaux indicateurs techniques
- Nouvelles stratégies ou personnalités
- Nouvelles règles de décision ou de filtrage
- Toute modification des seuils existants

**Autorisés exclusivement :**
outils de mesure, outils d'audit, tableaux de bord scientifiques,
visualisation des hypothèses/datasets/expériences, qualité statistique, reproductibilité.

---

## Research Maturity Index (RMI)

Indicateur de progression du projet. Calculé manuellement à chaque session.

| Composante              | Score actuel | Cible |
|-------------------------|-------------|-------|
| Architecture            | 100         | 100   |
| Observability           | 100         | 100   |
| Data Governance         | 100         | 100   |
| Scientific Governance   | 100         | 100   |
| Dataset Certification   | 0           | 100   |
| Data Quality (S1)       | 0           | 100   |
| Hypothesis Coverage     | 30          | 100   |
| Statistical Power       | 0           | 100   |
| Experiment Coverage     | 20          | 100   |
| Automation              | 30          | 100   |
| **RMI**                 | **48/100**  | 90    |

Le RMI progresse avec les données accumulées, pas avec le code ajouté.
Prochaine mise à jour : quand N≥50 trades certifiés (Dataset Certification active).

---

## Verrous Go/No-Go EXP-001 (en plus des métriques financières)

1. **Zéro Inconclusive critique** : si H1, H2 ou H3 est `Inconclusive` avec
   `n_at_eval >= min_n_required` → passage réel interdit.
2. **Zéro contradiction** : conflits H1↔H3 et H2↔H3 doivent être résolus
   (voir `experiments/EXP-001.yaml § known_conflict_pairs`).
