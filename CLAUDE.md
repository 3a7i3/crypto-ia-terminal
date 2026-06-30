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

## Phase actuelle : Validation Scientifique (gel fonctionnel)

Le développement fonctionnel est **gelé**. La valeur du projet vient désormais
de la qualité des données accumulées et de la rigueur de leur exploitation.

Seuls les dashboards de monitoring et les rapports de qualité de données sont autorisés.
Aucune nouvelle couche décisionnelle, aucun nouveau seuil, aucune optimisation.
