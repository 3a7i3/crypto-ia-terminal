# OP-PUB-01 — raccordement des projections burn-in et événements

Mandat opérateur : « PPL en lecture seule → producteurs séparés du checkout
gelé → projections → API → vues existantes ». #286 ACTIVE. Dépend de #472.
Cette livraison est SOURCE_ONLY : ni service installé ni route runtime modifiée.

## Fonctionnement qualifié

`python -m observability.operator_publication_bridge` appelle les producteurs
existants, sans importer Advisor, instancier de store writable ou commander un
service. Le seul lock créé appartient au répertoire de présentation.

```bash
python3 -B -m observability.operator_publication_bridge \
  --source-root /home/mathieu/crypto_ai_terminal \
  --store-root /home/mathieu/crypto_ai_terminal/databases/ppl_authority/store \
  --config-path /home/mathieu/crypto_ai_terminal/databases/ppl_authority/BURN-IN-EPOCH-01-20260926T064144Z.burn-in-experiment-config.json \
  --epoch BURN-IN-EPOCH-01-20260926T064144Z \
  --output-root /home/mathieu/operator_presentation/burnin-bridge
```

Exécuter uniquement depuis une copie source qualifiée séparée du checkout gelé,
avec l'interpréteur déjà qualifié pour l'API ; aucune installation pip dans
l'environnement Advisor. Le parent du répertoire de sortie doit exister.

Entrées : racine source déclarée, store PPL et config snapshot explicites.
Les chemins avec symlinks sont refusés ; la sortie ne peut contenir la source
ni être contenue dedans. Sortie privée 0700, propriétaire du processus requis.
Les comptes de collecte n'obtiennent aucun droit supplémentaire.

Chaque invocation crée `generations/capture-<uuid>/` avec :

- `burn_in_status_snapshot.json` : rejeu canonique, config hash et epoch validés.
- `event_center_snapshot.json` : source lifecycle dérivée ; alertes non fournies
  NOT_CONFIGURED, maximum 100 événements par source explicitement tronqués.
- `manifest.json` : empreintes des sorties, frontière PPL, config hash et dates.

Les deux readers réels valident les fichiers avant la publication. `current`
est un symlink **de répertoire parent**, remplacé atomiquement ; les fichiers
finaux restent réguliers et ne sont pas des liens. Les readers existants
acceptent cette structure (test des deux GET). Les deux requêtes API peuvent
franchir une génération : aucune cohérence transactionnelle inter-requêtes
n'est revendiquée. Le manifeste décrit une génération cohérente.

Un échec avant le remplacement de `current` conserve l'ancien pointeur. Les
générations précédentes restent disponibles pour rollback. Si le fsync après
bascule échoue, `POINTER_SWITCHED_DURABILITY_UNCERTAIN` signale explicitement
qu'une publication a pu avoir lieu. Les erreurs métier ne divulguent pas les
payloads ou les exceptions source dans la sortie CLI.

## Bornes et limites

Une invocation, aucun daemon. Lock non bloquant BUSY. Préflight d'entrée :
16 Mio pour le journal, 1 Mio pour la config ; 4 Mio par artifact de sortie.
Les préflights ne sont pas un quota OS et ne protègent pas d'un adversaire du
même uid modifiant les sources après le contrôle. Le producteur contrôle une
frontière stable du journal. Les comptes privilégiés restent hors modèle.

Maximum 1 440 entrées de générations ; au-delà RETENTION_LIMIT sans suppression
automatique. Préparer une politique de rétention gouvernée avant une exécution
périodique prolongée. Les générations occupent du disque, y compris les copies
abandonnées après un incident avant la bascule. Pas de promesse de capacité/SLO.

Pas de contenu de secrets, de Telegram, d'exchange ou de journaux système.
Aucune source d'alertes n'est inventée. Le PnL reste celui de la projection PPL,
pas une nouvelle finance FIN ; FIN-02 n'est pas activé. Le temps de génération
ne rend pas récents les événements ; `source_updated_at_utc` est conservé.
La date scientifique T0 reste NOT_AVAILABLE faute de témoin admis transmis ;
aucune valeur historique n'est injectée implicitement.

## Gate runtime à soumettre avant toute installation

Les droits précédents portaient sur captures et scripts ponctuels. La
publication périodique et les relances de présentation ont un périmètre
distinct. Le mandat source ne modifie pas #286. CLAUDE.md impose : « Sans mission
et gate distinctes explicitement autorisées : aucun restart Advisor, changement
du checkout/runtime/VPS/systemd ». Préparer puis soumettre les éléments suivants.

1. CI au SHA final et revue indépendante des PR #472 et du bridge. Le code de
   #471 n'est pas une dépendance du publisher.
2. Copier la release qualifiée et ses empreintes dans un répertoire extérieur
   au checkout gelé. Ne pas modifier `/home/mathieu/crypto_ai_terminal`.
3. Invocation ponctuelle comme mathieu, sorties dans le répertoire ci-dessus ;
   vérifier manifest, dernière séquence, 2 lecteurs et empreintes des entrées
   inchangées à frontière égale. Vérifier l'absence de publisher concurrent.
4. Préparer une unité passive dédiée (Nice/ReadOnlyPaths sur les sources,
   ReadWritePaths limité à la sortie, aucun accès aux secrets ni au réseau),
   timer 60 s et rétention. Son installation/activation attend la gate.
5. Préparer une nouvelle release **API de présentation** contenant le correctif
   de validation #472. Sauvegarder unité/drop-ins actuels. Overrides proposés :

   ```ini
   Environment=BURN_IN_STATUS_SNAPSHOT_PATH=/home/mathieu/operator_presentation/burnin-bridge/current/burn_in_status_snapshot.json
   Environment=EVENT_CENTER_SNAPSHOT_PATH=/home/mathieu/operator_presentation/burnin-bridge/current/event_center_snapshot.json
   ```

   Mettre à jour la source API séparée et relancer uniquement
   `crypto-operator-api.service` après autorisation ; jamais Advisor.
6. Préparer la release **frontend** au même contrat #472 : l'ancien validateur
   navigateur refuse lui aussi O/USDT. Sauvegarder la release 8ff089b actuellement
   relevée et le routage avant toute bascule de `crypto-operator-web`.
7. Vérifier les GET et l'affichage réel mobile : historique/IDs, états, 100
   événements récents avec couverture explicite, dates et erreurs. Comparer
   seulement les frontières compatibles avec Telegram, jamais les époques.
8. Rollback : arrêter uniquement le nouveau timer ; restaurer les chemins et
   releases API/web sauvegardés ; relancer ces seuls services si nécessaire.
   Préserver les générations, preuves et sources. Une ancienne génération peut
   aussi être sélectionnée par remplacement atomique du pointeur, sans mutation
   PPL. Ni redémarrage Advisor, ni changement de config/epoch, ni retrait Telegram.

L'accès admin pour les unités reste celui de l'opérateur ; aucune règle sudoers
ou permission globale n'est ajoutée. Cette page prépare la gate ; elle n'est
pas un installateur à exécuter en production.

## Preuves locales — 19 octobre 2026 UTC

Python 3.11.17 : 993 tests ciblés réussis (cross-stack, bridge, runtime-service,
J01 et Governance Tower), un avertissement Starlette ; Ruff 0.15.8 baseline
gate réussi, aucune nouvelle violation. La régression complète n'a pas été
rejouée. La qualification frontend du correctif #472 est documentée dans cette
PR ; le bridge n'ajoute aucun code frontend.

Sur la copie canonique autorisée capturée à 07:10:43 UTC, invocation du CLI
réussie, puis deux vrais GET via TestClient : HTTP 200 / HTTP 200 ; 172 clôtures,
2 positions ouvertes ; 346 événements lifecycle observés, 100 publiés avec
troncature explicite. Les empreintes du manifeste de génération concordent ;
le digest du journal source est conservé :
`070d5f5e53d163bfbb846d871621fa92dd4b0afef008e31683b9980cfa90025f`.
Ces preuves sont hors production et ne prouvent ni déploiement, ni observation
temps réel, ni réconciliation FIN. CI distante et revue indépendante restent
à obtenir au HEAD exact.
