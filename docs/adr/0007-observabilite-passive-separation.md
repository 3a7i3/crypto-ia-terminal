# ADR-0007 — Principe de passivité : séparation stricte moteur/observabilité

**Date :** 2026-06-29
**Statut :** Accepté — Règle constitutionnelle
**Auteur :** Mathieu

---

## Contexte

Le moteur de décision actuel contient une violation de passivité identifiée :
`RegretEngine.get_threshold_delta()` calcule un delta de seuil basé sur les regrets et
l'applique en production via `GlobalRiskGate.apply_regret_delta()`. Ce mécanisme
d'auto-calibration active peut entraîner :
- une dérive invisible des seuils de score minimum
- des oscillations si le signal de regret est bruité (N<50 trades)
- une perte d'auditabilité (quel seuil est actif en ce moment ?)

Plus généralement, toute couche d'observabilité qui modifie un paramètre du pipeline de décision
crée un couplage non contrôlé entre l'analyse et l'exécution.

## Décision

**Règle constitutionnelle (non négociable) :**

> Le moteur de décision est le seul composant autorisé à prendre une décision de trading.
> Tous les composants d'observabilité (DecisionExplainer, RejectionStore, RegretScheduler,
> DecisionEventBus, et toutes les Phases 4-7 futures) sont strictement passifs.
> Ils peuvent observer, enregistrer, simuler, expliquer et recommander.
> Ils ne peuvent jamais influencer une décision en temps réel.
> Toute évolution des paramètres doit être validée explicitement par l'opérateur et
> appliquée via un processus de configuration versionné (config/settings.py ou .env).

**Implémentation immédiate :**
`RegretEngine.get_threshold_delta()` est conservé mais son résultat n'est plus
appliqué automatiquement. Il devient une source de `CalibrationRecommendation` (Phase 4).
L'appel `GlobalRiskGate.apply_regret_delta()` est supprimé ou conditionné à
`FEATURE_AUTO_CALIBRATION=true` (défaut : false).

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| Garder l'auto-calibration avec garde N>100 | Même avec N>100, la boucle restante est opaque et non auditée |
| Remplacer par bandit multi-bras | Introduce un modèle stochastique dans le pipeline — risque de dérive systémique |
| Désactiver uniquement en burn-in | Incohérent : le principe de passivité doit être permanent, pas conditionnel |

## Conséquences

**Positives :**
- Auditabilité totale : les paramètres actifs sont toujours dans config/settings.py ou .env
- Aucune dérive silencieuse des seuils entre deux sessions
- La Phase 4 (ACE) peut produire des recommandations sans risque d'application accidentelle
- Le système est déterministe : mêmes paramètres = mêmes décisions

**Négatives / compromis :**
- L'auto-calibration ne fonctionne plus — l'opérateur doit valider et appliquer manuellement
- Plus de latence entre la détection d'un sur-filtrage et la correction

**Règles induites :**
- `FEATURE_AUTO_CALIBRATION=false` est le défaut permanent
- Toute recommandation produite par ACE (Phase 4) est un `CalibrationRecommendation` avec
  confiance, échantillon N, impact simulé sur PF/Sharpe — jamais un setter direct
- La prise d'effet d'une recommandation nécessite une approbation explicite dans `.env` ou
  `config/settings.py`, suivie d'un redémarrage ou rechargement de config
