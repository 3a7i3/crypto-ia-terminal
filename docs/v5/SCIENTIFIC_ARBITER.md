# SCIENTIFIC_ARBITER.md

> **Statut : conception.** Composant de L4, sans autorité.

---

## 1. Mission et non-mission

**Mission.** Recevoir N contributions indépendantes portant sur une même
question, et produire une **carte de l'état du désaccord** : ce sur quoi les
contributions convergent, ce sur quoi elles s'opposent, ce que personne ne peut
trancher faute de données, et ce qui reste ouvert.

**Non-mission.** L'arbitre ne décide pas laquelle est vraie.

> **L'arbitre ne classe pas les hypothèses par qualité. Il les classe par
> testabilité et par coût de test.**

C'est la distinction qui le rend utile : son produit n'est pas un gagnant, c'est
une **file d'expériences ordonnée**.

### 1.1 L'arbitre n'est pas l'arbitre final

Le nom est trompeur et doit être compris ainsi : l'arbitre organise le débat.
**Le rejeu tranche** (axiome A3). Une hypothèse peut recevoir un consensus
unanime de six agents et être réfutée par la première expérience — c'est un
fonctionnement nominal, pas un échec de l'arbitre.

---

## 2. Entrées / sorties

| | |
|---|---|
| **Entrées** | ≥ 2 `Contribution` sur une même `Question`, produites **en aveugle** ; le sous-graphe de connaissance pertinent |
| **Sorties** | `ArbitrationReport` |
| **Artefact** | `knowledge/arbitrations/ARB-YYYY-NNN.json` |
| **Autorité** | aucune |

---

## 3. Structure de l'`ArbitrationReport`

```
id, question_id, contributions[], created_at

consensus[]:                # affirmations partagées
  - claim, supported_by[], evidence[], confidence_basis_min

conflicts[]:                # affirmations incompatibles
  - claim_a, claim_b, held_by_a[], held_by_b[]
    conflict_type: empirical | definitional | methodological | scope
    discriminating_experiment: ExperimentSpec | null

data_gaps[]:                # ce que personne ne peut trancher
  - question, blocking_reason, required_instrumentation

open_questions[]:           # engendrées par l'arbitrage

experiment_queue[]:         # LE produit utile
  - hypothesis_id, information_gain, cost, testable_now: bool
    priority_score
```

---

## 4. Les quatre sections

### 4.1 Consensus — et pourquoi il ne prouve rien

Une affirmation partagée par plusieurs agents. Enregistrée avec le
`confidence_basis` **le plus faible** parmi ses soutiens.

> **Règle C-1.** Un consensus fondé uniquement sur `raisonnement` ou
> `intuition_du_modele` est étiqueté **`CONSENSUS_SANS_PREUVE`** et reçoit une
> priorité de test **supérieure** à une hypothèse contestée.

**Rationale.** Des modèles entraînés sur des corpus proches partagent des biais.
Un accord unanime sans preuve est un signal de **biais commun**, pas de vérité.
C'est le point où un conseil d'IA est le plus dangereux, et la règle C-1 inverse
délibérément l'intuition : l'accord facile est suspect.

### 4.2 Conflits — typés, car chaque type se résout différemment

| Type | Nature | Résolution |
|---|---|---|
| `empirical` | désaccord sur un fait | **expérience discriminante** |
| `definitional` | même mot, sens différents | clarification humaine — aucune expérience ne le résoudra |
| `methodological` | désaccord sur la méthode de mesure | arbitrage humain ou méta-expérience |
| `scope` | vrai dans des domaines de validité différents | souvent **les deux ont raison** — le conflit disparaît en explicitant le domaine |

**Le typage est la valeur ajoutée de l'arbitre.** Lancer une expérience sur un
conflit `definitional` est un gaspillage garanti : aucune donnée ne tranchera un
désaccord de vocabulaire.

Pour tout conflit `empirical`, l'arbitre doit produire une
`discriminating_experiment` — le protocole minimal dont les deux camps
accepteraient le verdict **avant** de le connaître. Si aucune expérience
discriminante n'est formulable, le conflit est reclassé en `data_gap`.

### 4.3 Lacunes de données

Ce que l'architecture actuelle **ne peut pas** trancher. Chaque lacune nomme
l'instrumentation manquante.

Exemples issus des mesures actuelles :
- laquelle des deux machines d'état prévaut sur `SAFE_MODE` → trace runtime
- les deux `CapitalThrottle` se composent-ils → trace d'instances
- fidélité du simulateur MEXC → comparaison fills simulés / réels

**Les lacunes sont le produit le plus actionnable de l'arbitrage** : elles
orientent l'investissement en instrumentation, qui a un meilleur rendement que
l'investissement en hypothèses supplémentaires.

### 4.4 File d'expériences

```
priority_score = information_gain × testable_now / cost
```

| Terme | Définition |
|---|---|
| `information_gain` | nombre de nœuds `Knowledge` passant de `UNKNOWN`/`CONTESTED` à un état déterminé, pondéré par le nombre de décisions concernées |
| `testable_now` | 1 si corpus, instrumentation et rejeu sont disponibles ; 0 sinon |
| `cost` | temps de calcul + budget de corpus consommé (`usage_count`) |

**Une hypothèse à `testable_now = 0` reste dans le graphe avec priorité nulle.**
Elle n'est pas rejetée : elle attend l'instrumentation, et elle documente
pourquoi cette instrumentation aurait de la valeur.

---

## 5. Ce qui est explicitement interdit à l'arbitre

| Interdiction | Raison |
|---|---|
| Pondérer une contribution par la performance passée de son `actor_impl` | reproduirait l'autorité par réputation |
| Départager par vote majoritaire | des modèles corrélés votent ensemble ; la majorité mesure la corrélation, pas la vérité |
| Produire un score de « probabilité de vérité » | agrégerait des opinions en un nombre faussement objectif |
| Écarter une contribution minoritaire | une hypothèse isolée peut être la seule juste ; elle est conservée avec sa priorité propre |
| Formuler sa propre hypothèse | l'arbitre organise, il ne participe pas |
| Fusionner deux contributions en une synthèse | la synthèse est une nouvelle affirmation, que personne n'a proposée ni ne défend |

**Le dernier point mérite insistance.** Une « synthèse » d'arbitre crée une
affirmation orpheline, sans auteur, sans falsifieur, sans limitations déclarées.
C'est le mécanisme le plus courant par lequel un système multi-agents fabrique
de la fausse connaissance.

---

## 6. Traitement du cas dégénéré

| Situation | Comportement |
|---|---|
| Une seule contribution | rapport produit, `consensus` vide, contribution marquée `NON_CONTESTÉE` — jamais confondue avec un consensus |
| Contributions identiques | signal de **contamination** : vérifier que l'aveugle a été respecté (protocole §7.3) |
| Toutes en `intuition_du_modele` | rapport marqué `SANS_FONDEMENT_EMPIRIQUE`, escaladé à l'humain avant toute dépense de calcul |
| Aucun conflit et aucune preuve | signal de biais commun ; priorité de test relevée (règle C-1) |

---

## 7. Ce que l'arbitre ne résout pas

**7.1** Il ne détecte pas un angle mort partagé par tous les agents. Si aucune
contribution ne soulève une question, l'arbitre ne peut pas la faire apparaître.
C'est la fonction du rôle **Archiviste** et de la revue humaine — pas la sienne.

**7.2** Il ne mesure pas la qualité d'une question, seulement le coût et le gain
attendu de sa réponse.

**7.3** Il dépend entièrement de l'honnêteté des champs `confidence_basis` et
`limitations`. Un agent qui déclare mal ses bases fausse tout l'arbitrage. Seule
la mesure de `calibration_error` dans le temps (`AI_COUNCIL_SPEC §5`) détecte
cette dérive — **a posteriori**, jamais sur le coup.
