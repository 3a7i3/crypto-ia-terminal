# PROMPT — OBS-005 · Cohérence d'affichage de `integrity_snapshot.py` (OPTIONNEL)

> Ticket **NON GATED**, **OPTIONNEL** (retenu ou écarté par la décision D-4). Affichage / lecture seule.
> **N reste inchangé.**

## MISSION

Aligner la troisième lignée de recalcul — `system/integrity_snapshot.py` — sur la source d'affichage
retenue par `OBS-002`, **pour ses usages d'observabilité uniquement**.

## CONTEXTE

`system/integrity_snapshot.py:100-135` recalcule de façon indépendante :
`pb_free` ← `health["free_capital"]`, `pb_exposure` ← `health["total_exposure_pct"]`,
`pb_n` ← `health["n_positions"]`, à partir de `pos_manager.get_open()` (`:107-115`) — le même store vide
en mode paper que celui qui cause le bug corrigé par `OBS-002`.

C'est une **troisième** lignée de calcul, après celle du builder de cycle et celle du builder heartbeat.
L'audit SSoT recense au total ≈3 producteurs pour `exposure` et ≈4 pour `open_pnl`.

Ce ticket est marqué **optionnel** car `integrity_snapshot` peut avoir un rôle de contrôle d'intégrité
qui justifie précisément qu'il lise `pos_manager` (pour détecter une divergence, pas pour l'ignorer).
**Cette question doit être tranchée avant d'agir** — c'est l'objet de la première étape.

## OBJECTIF

Soit aligner `integrity_snapshot` sur la source d'affichage, soit **documenter explicitement** pourquoi
il lit délibérément `pos_manager`. Dans les deux cas, l'ambiguïté actuelle disparaît.

## CONTRAINTES

- Maximum 2 fichiers, environ 50 lignes.
- Lecture seule côté décision : aucune écriture vers `pos_manager` ni `check_new_trade`.
- Si l'analyse conclut que `integrity_snapshot` **doit** lire `pos_manager`, le livrable devient
  une **documentation**, pas une modification. C'est un résultat valide du ticket.

## INVARIANTS

- **INV-1** passivité (ADR-0007) · **INV-2** aucun reset de N · **INV-3** `paper_trades.jsonl` intact ·
  **INV-4** aucun seuil modifié.
- **INV-O4** — `integrity_snapshot` ne doit jamais devenir un **quatrième** producteur : soit il consomme
  une source existante, soit il documente pourquoi il en lit une autre.

## FICHIERS

| Fichier | Action |
|---|---|
| `system/integrity_snapshot.py` | Alignement (~100-135) **ou** documentation de l'écart |
| *(éventuel)* fichier de test | Selon l'issue retenue |

## ETAPES

1. Relever la baseline : `python -m pytest tests/ -q`.
2. **Trancher la question préalable** : à quoi sert `integrity_snapshot` ? Détecter une divergence
   (auquel cas lire `pos_manager` est **volontaire** et correct), ou publier un état (auquel cas il doit
   lire la source d'affichage) ? **A CONFIRMER AU DEMARRAGE DU TICKET** — par lecture des consommateurs.
3. Selon la réponse :
   - **Cas A (publication d'état)** : aligner sur la source d'affichage de `OBS-002`.
   - **Cas B (contrôle d'intégrité)** : documenter en clair que la lecture de `pos_manager` est
     délibérée, ce qu'elle détecte, et pourquoi elle ne doit **pas** être alignée.
4. Lancer les tests. Commiter.

## CHECKLIST

- [ ] Baseline relevée
- [ ] Question préalable tranchée, avec la preuve (consommateurs identifiés)
- [ ] Cas A ou Cas B appliqué, jamais les deux
- [ ] Aucun quatrième producteur de métrique créé
- [ ] `pos_manager` et `check_new_trade` non modifiés

## TESTS

```bash
python -m pytest tests/ -q
```

Attendu : zéro échec.

## VALIDATION

**Done si :** le rôle d'`integrity_snapshot` est tranché et écrit ; le code est aligné (cas A) ou
l'écart est documenté (cas B) ; aucun producteur supplémentaire.

**Refus si :** l'alignement est fait sans avoir tranché le rôle ; un quatrième calcul est introduit ;
le fichier écrit vers la décision.

## LIVRABLES

- `system/integrity_snapshot.py` modifié **ou** documenté.
- Commit (cas A) :

```
fix(observability): integrity_snapshot aligne sur la source d'affichage

Aucune modification de l'entree de decision. N inchange.
```

  ou (cas B) :

```
docs(observability): integrity_snapshot lit pos_manager deliberement

Documente le role de controle d'integrite : la lecture de pos_manager est
volontaire et sert a detecter la divergence, pas a la masquer.
```

- `.claude/IMPLEMENTATION_QUEUE.md` : `OBS-005` en **TERMINE**.

## STOP CONDITIONS

- `OBS-002` n'est pas terminé ⇒ ne pas démarrer.
- Le rôle d'`integrity_snapshot` ne peut pas être tranché par lecture ⇒ **STOP**, demander l'opérateur.
  Ne pas deviner : aligner à tort détruirait un mécanisme de détection.
- La décision D-4 a écarté ce ticket ⇒ ne pas l'exécuter.

## INTERDICTIONS

- Ne pas modifier `pos_manager`, `check_new_trade`, le sizing, le risk, `PortfolioBrain` en entrée.
- Ne pas créer un nouveau calcul de métrique.
- Ne pas aligner sans avoir tranché le rôle du module.
- Ne pas enchaîner sur un autre ticket. **S'arrêter après le commit.**
- Ne pas déployer.
