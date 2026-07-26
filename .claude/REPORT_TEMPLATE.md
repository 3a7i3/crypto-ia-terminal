# REPORT_TEMPLATE — Gabarit de rapport de fin de ticket

> Livrable du ticket **GOV-004**.
>
> Aligné sur `docs/protocole_audit_epistemique.md` v3. Règle centrale de ce protocole :
> **ne jamais laisser un mot porter une charge de preuve que les observations ne portent pas.**
>
> Un rapport de ticket n'est pas un mémoire. Le gabarit ci-dessous tient en une page remplie.

---

## Règle de proportionnalité

Remplir des cases simule la rigueur sans la produire.

| Ticket | Forme du rapport |
|---|---|
| Trivial, sans écart, sans doute | **Forme courte** (5 lignes, voir plus bas) |
| Porteur, contesté, ou avec un écart rencontré | **Forme longue** (gabarit complet) |

Un ticket qui a rencontré un `A CONFIRMER AU DEMARRAGE DU TICKET` infirmé, un test étranger en échec,
ou un doute de gating **exige la forme longue**, quelle que soit sa taille.

---

## Forme courte

```
RAPPORT <TICKET-ID> — <date>
Livrable : <fichiers>
Tests    : <baseline> -> <apres>
Invariants : INV-1..4 verifies (commandes du registre) — sorties vides
INV-ROI-001 : OUI (debit | validite) — <une ligne>
Ecarts   : aucun
```

---

## Forme longue

```
RAPPORT <TICKET-ID> — <titre>            <date>

## OBSERVATION            (ce que j'ai VU — commandes lancees, sorties obtenues)
- <commande> -> <sortie>
  Source : inspection directe | log | doc | memoire
  Couverture : complete | partielle | inconnue

## INFERENCE              (ce que j'en DEDUIS)
- <enonce>
  Confiance : certain | tres probable | probable | speculatif | non demontre | faux
  Portee    : <le domaine EXACT ou l'enonce vaut>
  Falsificateur : <quelle observation le retournerait>

## HYPOTHESE              (ce qui reste NON VERIFIE)
- <les "A CONFIRMER AU DEMARRAGE DU TICKET" rencontres et leur issue>
  Source de plausibilite : <...>

## DECISION               (ce que je RECOMMANDE — jamais une deduction)
- <recommandation>
  Autorite : <qui tranche>
  Premisse de cout/valeur : <le jugement de valeur, explicite>

## INVARIANTS VERIFIES
- INV-1 : <commande> -> <sortie>
- INV-2 : <commande> -> <sortie>
- INV-3 : <commande> -> <sortie>
- INV-4 : <commande> -> <sortie>
- INV-ROI-001 : OUI/NON — voie <debit|validite> — <justification en une ligne>

## CE QUI N'A PAS ETE FAIT
- <perimetre volontairement laisse de cote, et pourquoi>
- <ce qui n'a PAS ete verifie, et pourquoi>

## PROOF (a recopier dans manifest.yaml)
commit / files / tests / invariants / baseline / after / completed_at / caveat
```

---

## Les quatre règles qui font la valeur du gabarit

1. **Une phrase = une catégorie.** « J'ai vu X donc Y est vrai donc il faut Z » se scinde en trois
   lignes, dans trois sections. C'est la guillotine de Hume gravée dans le format : on ne dérive jamais
   un *vouloir* d'un *voir*.
2. **Maillon faible.** Une inférence n'est jamais plus forte que sa plus faible observation.
   Une observation issue de la mémoire ou à couverture inconnue **plafonne** l'inférence à `probable`.
   Une observation d'un état **mutable** (API, ref distante, working tree) la plafonne à
   `très probable` — `certain` est réservé aux objets immuables (contenu d'un commit).
3. **Portée obligatoire.** Une portée manquante **est** un quantificateur universel caché.
   « les tests passent » veut dire « tous les tests, toujours » — écrire ce qu'on a réellement lancé.
4. **« Invariants respectés » ne suffit pas.** Nommer l'invariant **et la commande**. Sans commande,
   ce n'est pas une vérification, c'est une affirmation.

---

## Filtre lexical — avant de valider le rapport

Repérer : `impossible · détruit · prouve · définitivement · nécessairement · toujours · jamais ·
seul · aucun · tout · garantit`.

Pour chacun : **quelle observation autorise précisément ce mot ?** Pas de réponse immédiate ⇒ requalifier.

Second filtre, moins évident : une phrase **sans** mot fort peut cacher un « tout / seul / toujours ».
« le système écrit dans un fichier » sous-entend « un seul, toujours ». Rendre le quantificateur
explicite, puis lui appliquer le premier filtre.

---

## Exemple rempli (extrait réel — GOV-002)

```
## OBSERVATION
- git diff --cached --name-only | grep '\.py$' | grep -v '^\.claude/tools/'  ->  vide
  Source : inspection directe · Couverture : complete

## INFERENCE
- Le ticket ne peut pas affecter la suite de tests.
  Confiance : tres probable   (et non "certain" : l'index git est un etat mutable)
  Portee    : ce diff, a cet instant — PAS "le depot est sain"
  Falsificateur : un .py de production apparaissant au diff

## HYPOTHESE
- Aucun "A CONFIRMER" rencontre.

## DECISION
- Clore le ticket sans relever la baseline pytest complete.
  Autorite : session ; appetit au risque bas (aucun code de production touche)
  Premisse : le cout de la suite complete (~1122 modules) depasse sa valeur ici

## INVARIANTS VERIFIES
- INV-1..INV-4 : 4 commandes du registre -> 4 sorties vides
- INV-ROI-001  : OUI, voie validite — precondition declaree d'OBS-001

## CE QUI N'A PAS ETE FAIT
- Baseline pytest NON RELEVEE (justifiee ci-dessus). Obligatoire pour OBS-001, qui touche tests/.
- Atomicite partiellement violee : le commit porte aussi l'infrastructure. Assume, non masque.
```

> Ce que cet exemple montre, et qui est le but du gabarit : les deux dernières lignes.
> Un rapport qui ne contient **jamais** de section « ce qui n'a pas été fait » non vide est un rapport
> qui ne regarde pas ses propres angles morts.
