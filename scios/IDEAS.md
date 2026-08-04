# Registre d'idées — objets envisagés, non construits

> Ni ADR, ni spécification, ni engagement. Ce fichier existe pour qu'une idée
> juste ne soit pas perdue **et** ne soit pas construite trop tôt.
>
> Règle d'entrée dans le code : un objet n'est ajouté que lorsqu'il a
> **un producteur réel, un consommateur réel et un test qui démontre son
> utilité**. Tant que les trois ne sont pas réunis, il reste ici.

---

## `Question`

> « Pourquoi DOGE perd-il ? »

Déclencheur d'une campagne scientifique : une question ouvre une hypothèse, qui
ouvre une expérience. Figure déjà dans le modèle gelé (`KNOWLEDGE_MODEL §3.3`)
avec le préfixe `QST`.

**Pourquoi pas maintenant** — aucun producteur (rien ne formule de question),
aucun consommateur (aucune `Hypothesis` n'existe pour la référencer), aucun test
possible.

**Ce qui la débloquerait** : l'objet `Hypothesis`, qui lui donnerait un
consommateur.

---

## `Signal`

Intermédiaire entre `Event` et `Observation` : une coïncidence de conditions
brutes (funding + open interest + pic de volume) qui n'est pas encore un fait
mesuré. Utile le jour où des flux massifs seront traités par plusieurs agents.

**Pourquoi pas maintenant** — aucun détecteur ne le produit, aucun constructeur
d'observation ne le consomme. De plus, contrairement à `Event`, il **n'est pas
dans le modèle gelé** : l'ajouter exigerait un ADR (`FOUNDATION_FREEZE §6.1`).

**Ce qui le débloquerait** : un besoin mesuré de réduire le volume avant
dérivation — c'est-à-dire un ledger dont la taille rend les dérivations
directes trop coûteuses. Ce besoin n'existe pas à 1421 événements.

---

## `Compression`

Enregistrer chaque passe de condensation comme un objet — entrée, sortie,
ratio, algorithme, époque — pour comparer les stratégies de compression entre
elles dans le temps.

**Pourquoi pas maintenant** — son consommateur est la **dérive du ratio**, qui
exige au moins deux points de mesure. Le premier snapshot vient d'être écrit.

**Ce qui le débloquerait** : le second snapshot. C'est l'idée la plus proche
d'être construite.

---

## Réplication externe du ledger (L2)

`PERSISTENT_MEMORY_SPEC` PM-7 exige que le ledger soit répliqué hors du dépôt.
Le manifeste (`scios/snapshot.py`) rend le déplacement sûr : il atteste du
contenu indépendamment de la localisation.

**Pourquoi pas maintenant** — le ledger pèse 2,1 Mo. Git le réplique
suffisamment, et une destination externe non choisie serait une dépendance de
plus sans gain mesuré.

**Ce qui le débloquerait** : un ledger de quelques dizaines de mégaoctets, ou
un besoin d'accès depuis une machine qui n'a pas le dépôt.
