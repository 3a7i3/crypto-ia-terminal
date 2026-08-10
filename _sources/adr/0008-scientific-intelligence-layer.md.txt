# ADR-0008 - Scientific Intelligence Layer et SDOS

**Date :** 2026-07-01
**Statut :** Accepte - Decision d'architecture strategique
**Auteur :** Mathieu

---

## Contexte

Le projet a depasse le cadre d'un bot de trading. Le moteur de trading reste le
cas d'usage principal, mais les couches livrees autour du DIP produisent deja une
plateforme d'observation, de replay, de causalite, de certification et de
gouvernance scientifique.

Le risque architectural actuel n'est plus le manque d'outils. Le risque est de
continuer a ajouter des outils sans langage commun pour representer ce que le
systeme sait reellement de son propre comportement.

La question cible n'est donc plus seulement :

> Pourquoi ce trade a-t-il ete refuse ?

Elle devient :

> Que savons-nous reellement du comportement du moteur de decision ?

## Decision

Le projet adopte l'identite architecturale suivante :

> **Scientific Decision Operating System (SDOS)** - une plateforme scientifique
> d'analyse decisionnelle dont le trading est le premier cas d'usage.

Nous introduisons un niveau intermediaire :

> **L3.5 - Scientific Intelligence Layer**

Ce niveau est situe apres la gouvernance scientifique L3 et avant le Research Lab
L4. Il ne cree pas de nouvelle capacite decisionnelle et n'a aucun droit
d'influence runtime sur le moteur. Il transforme les observations DIP en
connaissance scientifique structuree.

Le niveau L7 est renomme :

> **Scientific Intelligence Core**

L7 devient l'integration mature et long terme des moteurs de connaissance,
d'evidence, de memoire scientifique, de planification de recherche et de
detection des contradictions.

## Portee normative

L3.5 contient huit moteurs conceptuels, tous passifs :

| ID | Moteur | Role |
|----|--------|------|
| SI-01 | Decision Knowledge Graph | Relie Decision, RootCause, Hypothesis, Dataset, Evidence, Confidence, Conclusion et Experiment |
| SI-02 | Causal Memory | Accumule les motifs causaux recurrents et leur valeur empirique |
| SI-03 | Evidence Engine | Suit confirmations, contradictions, invalidations et niveaux d'evidence |
| SI-04 | Scientific Timeline | Montre l'evolution temporelle de la connaissance, pas seulement des trades |
| SI-05 | Contradiction Detector | Detecte les hypotheses compatibles ou incompatibles entre elles |
| SI-06 | Knowledge Confidence | Mesure la confiance dans la connaissance produite, distincte de l'OCS |
| SI-07 | Scientific Drift | Detecte le vieillissement ou la degradation d'une conclusion scientifique |
| SI-08 | Decision DNA | Encode les decisions en sequences comparables pour identifier des familles decisionnelles |

## Alternatives rejetees

| Alternative | Raison du rejet |
|------------|-----------------|
| Garder L7 sous le nom "Meta Intelligence" | Trop vague. Le projet vise une intelligence scientifique, pas une meta-couche generale |
| Ajouter directement des modules DIP D15+ | Violerait l'esprit de la Scientific Debt Rule : plus d'outils avant langage commun |
| Integrer L3.5 dans L4 Research Lab | L4 genere de nouvelles hypotheses ; L3.5 structure d'abord la connaissance existante |
| Faire de L3.5 une couche active d'auto-calibration | Interdit par ADR-0007 et par `FEATURE_AUTO_CALIBRATION=false` |

## Consequences

**Positives :**
- Le DIP devient le socle d'un SDOS, pas seulement un observateur de trading.
- Les futures analyses parleront en termes de connaissance, evidence,
  contradiction, confiance et derive scientifique.
- Les modules existants D01-D14 sont recontextualises sans changer leur code.
- Le passage vers robotique, agents IA, cybersécurité ou finance reste possible
  car le coeur devient l'analyse decisionnelle.

**Negatives / compromis :**
- Le PMI doit distinguer le score historique en 7 niveaux du score SDOS incluant
  L3.5.
- Les livrables L3.5 devront resister a la tentation de devenir des features
  runtime.
- La mise en oeuvre devra attendre des donnees certifiees suffisantes.

**Regles induites :**
- Toute implementation L3.5 est passive et append-only.
- Aucun moteur SI ne modifie un seuil, une decision, un ordre ou une configuration
  live.
- Toute conclusion produite par L3.5 reference un dataset certifie, une hypothese
  versionnee et un niveau d'evidence explicite.
- `OCS` repond a "peut-on faire confiance a l'observateur ?".
  `Knowledge Confidence` repond a "peut-on faire confiance a la connaissance produite ?".
- Le document de reference technique est
  `docs/dip/SCIENTIFIC_INTELLIGENCE_LAYER.md`.
