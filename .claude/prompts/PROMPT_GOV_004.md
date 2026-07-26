# PROMPT — GOV-004 · Gabarit de rapport de fin de ticket

> Ticket **NON GATED**, **documentaire**. Aucun `.py`. **N reste inchangé.**

## MISSION

Produire le gabarit de rapport que **tout** ticket du chantier devra remplir en fin d'exécution,
aligné sur le protocole d'audit épistémique v3 (`docs/protocole_audit_epistemique.md`).

## CONTEXTE

Le dépôt contient un protocole d'audit épistémique v3, fusionné dans `main`. Sa règle centrale :
**ne jamais laisser un mot porter une charge de preuve que les observations ne portent pas.**

Il impose : une phrase = **une** catégorie épistémique (Observation / Inférence / Hypothèse / Décision) ;
la règle du **maillon faible** (une inférence n'est jamais plus forte que sa plus faible observation) ;
la **portée** explicite de chaque affirmation ; un **falsificateur** par inférence porteuse ; la
**dette épistémique** relative à une décision nommée ; le **principe de symétrie** (une preuve favorable
est tenue au même standard qu'une preuve défavorable).

Sans gabarit, chaque rapport de ticket sera rédigé différemment, et les affirmations « le ticket est
terminé », « les tests passent », « rien d'autre n'a changé » seront mélangées sans distinction de
niveau de preuve. Ce ticket rend le format obligatoire et uniforme.

## OBJECTIF

Un gabarit copiable, court, qui force l'auteur d'un rapport de ticket à séparer ce qu'il a **vu**
de ce qu'il **déduit**, de ce qu'il **suppose**, de ce qu'il **recommande**.

## CONTRAINTES

- Documentation seule. Aucun `.py`, aucun test, aucune configuration.
- Le gabarit doit être **court** : un rapport de ticket n'est pas un mémoire.
- Il doit s'appliquer aussi bien à un ticket documentaire qu'à un ticket de code.

## INVARIANTS

INV-1 à INV-4, trivialement respectés (aucun code touché).

## FICHIERS

| Fichier | Action |
|---|---|
| 1 document Markdown sous `.claude/` | Création du gabarit |

## ETAPES

1. Lire `docs/protocole_audit_epistemique.md` pour en reprendre les catégories et règles exactes.
2. Rédiger le gabarit avec, au minimum :
   - **Observation** : ce qui a été effectivement constaté (commandes lancées, sorties obtenues),
     avec source et couverture.
   - **Inférence** : ce qu'on en déduit, avec niveau de confiance, portée et falsificateur.
   - **Hypothèse** : ce qui reste non vérifié (notamment les `A CONFIRMER AU DEMARRAGE DU TICKET`
     rencontrés et leur issue).
   - **Décision** : ce qui est recommandé pour la suite, avec l'autorité qui décide.
   - **Invariants vérifiés** : lesquels, et par quel contrôle.
   - **Ce qui n'a pas été fait** : périmètre volontairement laissé de côté.
3. Ajouter un **exemple rempli** court, pour lever toute ambiguïté d'usage.
4. Ajouter la règle de proportionnalité : un ticket trivial ne remplit pas six sections ;
   la forme longue s'impose seulement si le ticket est porteur, contesté, ou a rencontré un écart.
5. Commiter.

## CHECKLIST

- [ ] Les 4 catégories épistémiques figurent au gabarit
- [ ] Chaque inférence exige confiance + portée + falsificateur
- [ ] Une section « Ce qui n'a pas été fait » est présente
- [ ] Un exemple rempli est fourni
- [ ] La règle de proportionnalité est énoncée (anti-remplissage mécanique)
- [ ] Aucun `.py` au diff

## TESTS

```bash
python -m pytest tests/ -q
```

Attendu : identique à la baseline.

## VALIDATION

**Done si :** le gabarit impose la séparation des 4 catégories, exige portée et falsificateur pour les
inférences, contient un exemple, et borne son propre usage par la règle de proportionnalité.

**Refus si :** le gabarit autorise une conclusion sans observation-support ; il n'exige ni portée ni
falsificateur ; il est si long qu'il ne sera pas utilisé.

## LIVRABLES

- 1 document Markdown.
- Commit :

```
docs(gov): gabarit de rapport de fin de ticket

Aligne sur docs/protocole_audit_epistemique.md v3 : separation
Observation / Inference / Hypothese / Decision, portee et falsificateur
obligatoires, regle de proportionnalite.

Documentation seule.
```

- `.claude/IMPLEMENTATION_QUEUE.md` : `GOV-004` en **TERMINE**.

## STOP CONDITIONS

- `docs/protocole_audit_epistemique.md` est absent ou d'une version différente de v3 ⇒ signaler
  avant de rédiger un gabarit qui divergerait de la référence.

## INTERDICTIONS

- Ne toucher aucun `.py`, test ou configuration.
- Ne pas réécrire `docs/protocole_audit_epistemique.md` : le gabarit s'y **réfère**, il ne le remplace pas.
- Ne pas enchaîner sur un autre ticket. **S'arrêter après le commit.**
- Ne pas déployer.
