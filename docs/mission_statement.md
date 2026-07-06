# Mission Statement — crypto_ai_terminal
# Document d'ingénierie. Version : 1.0   Date : 2026-06-30

---

## Mission

Construire un **Scientific Decision Operating System (SDOS)** : une plateforme
scientifique d'analyse décisionnelle dont chaque décision de trading, chaque
évolution du moteur et chaque changement de configuration sont justifiés par des
données certifiées, des expériences reproductibles et une gouvernance explicite.

Le trading est le premier cas d'usage. L'identité durable du projet est la
production de connaissances fiables sur un système de décision.

---

## Principes immuables

**1. La sécurité du capital prime sur la fréquence de trading.**
Un cycle sans trade est une décision valide. Le refus est une donnée scientifique.

**2. Les données priment sur l'intuition.**
Aucun paramètre ne change sans justification statistique documentée :
taille d'échantillon, intervalle de confiance, puissance, effet attendu.

**3. Les hypothèses sont falsifiables.**
Une hypothèse non testable n'est pas une hypothèse — c'est une opinion.
Toute hypothèse est formulée avec un critère de rejet explicite.

**4. La gouvernance humaine reste le dernier niveau de validation.**
Aucun système automatisé ne prend de décision finale sans validation opérateur.
L'IA recommande. L'opérateur décide. Toujours.

**5. Toute Release est traçable, reproductible et réversible.**
Chaque dataset porte un UUID. Chaque expérience référence un commit.
Un résultat non reproductible n'est pas un résultat.

---

## Critère d'évaluation d'une nouvelle idée

Avant d'implémenter quoi que ce soit, une seule question :

> Cette idée est-elle cohérente avec la mission, ou optimise-t-elle une métrique
> intermédiaire au détriment de la rigueur scientifique ?

Si la réponse est ambiguë, la réponse est non.

---

## Ce que ce projet n'est pas

- Un simple bot de trading dont l'identité se limite à l'exécution
- Un système d'optimisation continue sans validation scientifique
- Une infrastructure de machine learning auto-apprenante sans supervision
- Un outil pour maximiser le nombre de trades ou la fréquence d'activité
- Un projet où l'architecture évolue plus vite que les données

---

## North Star

Le succès ne se mesure pas au nombre de fonctionnalités livrées.
Il se mesure à la qualité des hypothèses validées, à la rigueur des datasets
produits, et à la confiance statistique avec laquelle l'opérateur peut
prendre une décision de capital réel.

**PMI Evidence Score >= 50% est le premier seuil de maturité réelle.**
Tout ce qui précède est de l'infrastructure.
