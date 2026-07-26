# PROMPT — GOV-005 · Checklist de déploiement VPS et vérification post-déploiement

> Ticket **NON GATED**, **documentaire**. Aucun `.py`, aucun déploiement effectué. **N reste inchangé.**

## MISSION

Produire la checklist opposable de déploiement VPS et de vérification post-déploiement, intégrant la
leçon de l'incident du 2026-07-09.

## CONTEXTE

Le déploiement vers le VPS est un **geste délibéré** :

```bash
bash scripts/deploy_vps.sh --confirm            # avec confirmation interactive
bash scripts/deploy_vps.sh --confirm --yes      # usage scripté
bash scripts/deploy_vps.sh --confirm --dry-run  # simulation
bash scripts/deploy_vps.sh --confirm --restart  # + redémarrage (double opt-in)
```

Sans `--confirm`, le script affiche l'usage et sort. Le hook `post-commit` qui déployait automatiquement
a été aboli en 2026-07-04 : un commit ne déploie plus jamais rien tout seul.

Après un déploiement réussi, un tag annoté `deploy-YYYYMMDD-HHMM` est créé — **c'est le journal d'audit
des déploiements**.

**Incident du 2026-07-09** : un `ssh` sans `-n` dans `deploy_vps.sh` a fait croire à des succès.
**Trois tags d'audit mensongers** ont été créés, 55 fichiers sur 80 n'avaient jamais été transférés, et
un mécanisme de sécurité était resté inactif sans que personne ne s'en aperçoive. La leçon : **un tag
n'est pas une preuve de déploiement.** Seule une vérification côté serveur en est une.

VPS courant : IP **35.240.166.72** (l'ancienne `34.171.188.99` est morte).

## OBJECTIF

Une checklist qu'on ne peut pas cocher sans avoir réellement vérifié — donc une checklist qui aurait
attrapé l'incident du 2026-07-09.

## CONTRAINTES

- Documentation seule. **Aucun déploiement n'est effectué par ce ticket.**
- Aucun `.py`, aucune configuration, aucun script modifié.
- Chaque item doit être une **vérification concrète**, pas une intention.

## INVARIANTS

INV-1 à INV-4, trivialement respectés (aucun code touché).
**INV-G2** — aucun item de la checklist ne peut être coché sur la foi d'un tag ou d'un message de succès :
seule une observation **côté serveur** vaut preuve.

## FICHIERS

| Fichier | Action |
|---|---|
| 1 document Markdown sous `.claude/` ou `docs/` | Création de la checklist |

## ETAPES

1. Lire `scripts/deploy_vps.sh` pour relever les options réelles et le filtre d'exclusion
   (`databases/|cache/|logs/|tests/|docs/`), qui protège l'état runtime du VPS.
2. Rédiger la checklist **avant déploiement** : baseline de tests verte, commit poussé, périmètre du
   diff connu, `--dry-run` effectué et lu, décision explicite sur `--restart`.
3. Rédiger la checklist **après déploiement**, avec pour chaque item la commande de vérification :
   - comparaison **SHA local = SHA VPS** sur les fichiers effectivement transférés ;
   - service actif (`crypto-advisor`, `crypto-watchdog`) ;
   - nombre de fichiers transférés = nombre attendu ;
   - comportement observable attendu (ex. panneau cohérent au cycle suivant) ;
   - tag `deploy-YYYYMMDD-HHMM` créé **après** vérification, jamais avant.
4. Ajouter un encart rappelant l'incident du 2026-07-09 et sa leçon (un tag n'est pas une preuve).
5. Ajouter la règle du double opt-in pour `--restart`.
6. Commiter.

## CHECKLIST

- [ ] Options réelles de `deploy_vps.sh` relevées par lecture du script
- [ ] Checklist avant déploiement rédigée
- [ ] Checklist après déploiement rédigée, avec une commande par item
- [ ] La comparaison SHA local / SHA VPS figure explicitement
- [ ] L'encart sur l'incident du 2026-07-09 figure
- [ ] Le tag est décrit comme créé **après** vérification
- [ ] Aucun déploiement effectué, aucun `.py` modifié

## TESTS

```bash
python -m pytest tests/ -q
```

Attendu : identique à la baseline.

## VALIDATION

**Done si :** chaque item post-déploiement porte une commande de vérification exécutable ; la
comparaison SHA figure ; l'ordre « vérifier puis taguer » est explicite ; aucun déploiement n'a eu lieu.

**Refus si :** un item se coche sur la foi d'un message de succès du script ; la checklist autorise le
tag avant vérification ; un déploiement a été effectué par ce ticket.

## LIVRABLES

- 1 document Markdown.
- Commit :

```
docs(gov): checklist de deploiement et verification VPS

Checklist avant/apres deploiement, une commande de verification par item.
Integre la lecon de l'incident du 2026-07-09 : un tag n'est pas une preuve
de deploiement, seule une verification cote serveur en est une.

Documentation seule. Aucun deploiement effectue.
```

- `.claude/IMPLEMENTATION_QUEUE.md` : `GOV-005` en **TERMINE**.

## STOP CONDITIONS

- `scripts/deploy_vps.sh` a une interface différente de celle décrite ⇒ documenter l'interface **réelle**,
  ne pas recopier ce prompt.
- La vérification SHA côté VPS s'avère impossible avec les accès disponibles ⇒ le documenter comme
  limitation connue plutôt que de proposer une vérification illusoire.

## INTERDICTIONS

- **Ne déployer sous aucun prétexte** dans ce ticket, même en `--dry-run` sur le VPS de production.
- Ne modifier ni `scripts/deploy_vps.sh`, ni aucune configuration.
- Ne pas créer de tag `deploy-*`.
- Ne pas enchaîner sur un autre ticket. **S'arrêter après le commit.**
