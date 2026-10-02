# Constitution de travail — Crypto AI Terminal

Lire d'abord [docs/DEVELOPER_ENTRYPOINT.md](docs/DEVELOPER_ENTRYPOINT.md).
Ce fichier porte les invariants et la méthode, pas l'état opérationnel courant.
La priorisation vit dans [#285](https://github.com/3a7i3/crypto-ia-terminal/issues/285),
la mission dans [CURRENT_TASK.md](CURRENT_TASK.md), les observations dans leurs
preuves GitHub datées. Une documentation ancienne ne constitue jamais une
permission de déployer, calibrer ou modifier une expérience.

## 1. Faits, hypothèses et autorités

- **PPL = vérité lifecycle** : événements et états issus de l'autorité déclarée.
- **FIN = vérité financière** : valeurs, frais et réconciliation issus de FIN.
- **Research = non autoritaire** : PAPER produit les faits ; Research produit
  les hypothèses et candidats pour une future expérience gouvernée.
- **Operator API = boundary GET-only de présentation** ; le frontend consomme
  les projections, sans lecture directe de JSONL/database/exchange/VPS.
- **L'intelligence n'est pas l'autorité** : une recommandation, un score,
  une pastille verte ou une qualification source n'active aucune stratégie.
- **SOURCE PROOF ≠ RUNTIME PROOF** : vérifier le HEAD réel et la portée de la
  preuve ; aucune déduction de déploiement depuis main ou la CI.
- **UNKNOWN ≠ 0** ; NOT_AVAILABLE et UNRESOLVED restent visibles et distincts.
- **UNRESOLVED IS DATA** : conserver l'état, la provenance, la population et
  ses limites ; ne pas effacer un cas difficile pour améliorer un résultat.

Le frontend peut filtrer, expliquer et formater une valeur ; il ne recalcule
ni PnL/equity, ni verdict scientifique, ni classement. Une valeur exacte reste
consultable lorsque son affichage est abrégé. Une panne de lecture n'est pas
une population vide, et une fixture ne devient jamais une preuve runtime.

## 2. Passivité et intégrité expérimentale

Les observers, télémétrie, regret, laboratoire, replay et outils IA observent,
enregistrent, simulent et recommandent. Ils n'influencent pas une décision
active et ne pilotent pas le runtime. Voir ADR-0007 dans les références de
l'entrée développeur.

`FEATURE_AUTO_CALIBRATION=false` reste le défaut permanent ; aucune exception
sans décision de gouvernance explicite. Ne pas changer la base de sizing,
les seuils ou le capital par un redémarrage, un refactor ou un effet de bord.
Les anciennes références `WALLET_PAPER_CAPITAL` ne remplacent pas l'identité et
la configuration gouvernées de l'expérience considérée.

Toute calibration exige des preuves statistiques pertinentes : protocole,
population, coûts, limites, incertitude, reproductibilité et validation humaine.
Les anciennes tables de seuils et fenêtres de dataset sont conservées dans
[l'ancien CLAUDE.md](https://github.com/3a7i3/crypto-ia-terminal/blob/053c8540a012b2c2c7a9bc5e76585a1425858f73/CLAUDE.md).
Cette réécriture ne change aucun protocole ni paramètre. Ne pas réutiliser
`CLEAN_DATA_SINCE_V4`, EXP-001 ou les scores PMI historiques comme état ou
admission d'un dataset actuel ; employer les IDs/boundaries/manifests explicites
et les gates applicables. Atteindre un ancien seuil ne lève aucun freeze.

La Scientific Debt Rule demeure : justifier chaque changement par une mission,
un besoin de validation ou une hypothèse ; éviter de créer des variables
expérimentales inutiles. Les améliorations UI/source autorisées ne sont pas
une autorisation de refactoriser ou d'enrichir la machine déployée.

## 3. Expérience active : vérifier le garde-fou

Avant tout travail, consulter [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286)
et la mission applicable. Tant que `ACTIVE_BURN_IN_IMMUTABILITY_GUARD` est actif,
préserver stratégie, signaux, thresholds, calibration, risk, sizing,
`PB_MAX_POSITIONS`, config, capital initial, manifest, epoch et autorité PPL.

Sans mission et gate distinctes explicitement autorisées : aucun restart
Advisor, changement du checkout/runtime/VPS/systemd, activation Watchdog/FIN,
TESTNET/LIVE, écriture exchange ou mutation PPL/FIN. Ne pas arrêter CryptoRadar,
retirer des sorties ou modifier les notifications dans une mission source/UI.
Les exceptions historiques sont consommées, pas des permissions réutilisables.

Flux admis : `PAPER → dataset immuable → Research → diagnostic/candidat`.
Flux interdit : `Research → même epoch active`.
Une future epoch nécessite ses propres preuves et sa propre autorisation ;
la fin du burn-in n'en crée pas une automatiquement.

Les checkpoints runtime READ-ONLY restent ponctuels dans leur mission autorisée.
Un agent n'accède pas aux secrets par défaut et ne se donne aucune autorité
pour déployer, promouvoir, écrire sur exchange ou merger automatiquement.
Une action source explicitement autorisée par l'opérateur doit rester dans
sa portée ; elle ne vaut jamais autorisation runtime.

## 4. Méthode de modification

1. Lire la mission, ses contraintes et les contrats du domaine. Revérifier les
   références GitHub ; séparer règles permanentes et preuves temporelles.
2. Examiner le tree local, les changements préexistants et le HEAD/base réels.
   Utiliser une branche/PR isolée ; préserver le travail de l'opérateur.
3. Identifier producteur, autorité, artifact, consommateurs et conséquences.
   Ne pas « corriger » une autorité via son lecteur ou sa présentation.
4. Implémenter le scope admis, sans changement runtime implicite ni faux état.
5. Exécuter les contrôles adaptés et les checks requis. Rapporter échecs,
   skips, limites et fraîcheur des preuves au HEAD exact ; pas de baseline
   modifiée ou de test supprimé pour masquer une régression.
6. Livrer une PR/documentation traçable. Une fusion source et une publication
   runtime ont des gates et des preuves différentes.

Ne pas exposer de secrets dans les commandes/logs/artifacts, ni envoyer des
messages à des tiers sans autorisation. Pas de `npm audit fix --force` comme
substitut à une revue de dépendances. Les permissions de secrets, la sécurité
frontend et les protections GitHub ont leurs missions distinctes.

## 5. Cleanup et historique

Classification préalable : `KEEP | INTEGRATE | MOVE | ARCHIVE | RETIRE | UNKNOWN`.
UNKNOWN signifie ne pas supprimer. Avant retrait, vérifier imports,
producteurs/consommateurs, scripts/cron, unités systemd, API/frontend, tests/CI,
preuves scientifiques et rollback. Préserver logs, JSONL, datasets immuables
et sauvegardes nécessaires à l'audit/reprise.

Les anciennes fenêtres STABILIZATION LAB, Phase II, V4 et plans live sont des
archives. Leurs commandes de déploiement et autorisations ne sont pas actives.
[#148](https://github.com/3a7i3/crypto-ia-terminal/issues/148) reste l'archive
canonique de la phase précédente ; [ROADMAP.md](ROADMAP.md) en donne les repères.
