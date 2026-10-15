# D1-D/E — inventaire des copies Research autorisées, 2026-10-12

Mission #412 ; parents #404/#408/#410 et roadmap #285 ; #282/#286 protégées.
Base source vérifiée : `598ab14b7fff06fdae5d3f2a24bc8d4484f48e71`.

## Question et méthode

Les copies déjà autorisées contiennent-elles un roster producteur acquis
indépendamment et des reçus natifs permettant de relier chaque tentative à
`BUILD → PUBLISH → DELIVERY → FILTER → VALIDATE → APPEND → FLUSH → FSYNC_RETURN` ?
La présence de code fsync, d'un JSONL ou d'un retour listener ne suffit pas.

Relecture GitHub des commentaires de #404/#282 et contrats D1-D/E sur main.
Remote Desktop Commander `list_devices` a retourné `crypto-advisor-2` **Offline**,
last seen `19h ago`, version 0.2.52. Ce résultat décrit la passerelle, pas la santé
Advisor. Aucun shell VPS ni fichier Research distant ouvert dans cette reprise.
Les pièces jointes ZIP sont des snapshots source : elles ne sont pas admises
comme copies de preuves producteur ou de receipts natifs.

## Inventaire de preuve, sans promotion historique en état courant

| Copie / référence | Autorisation et preuve publiées | Roster indépendant / reçus fsync | État de cette reprise |
|---|---|---|---|
| O4/O6-B, #282 | Export Research historique ; dataset O6-B `410955659523d575b14445eebe7aad5525f73152c24e76f14294a015e383c768`, boundary `d60d1b73e48d2ff567e62469b96df0799c9711ffc90bd3f24697f17b5d6ac78e` ; 32 OPEN liés à 32 packets/identities | Sous-population OPEN, pas roster exhaustif des opportunités/invocations ; aucun reçu natif per-packet fsync démontré par cette preuve | HISTORICAL_REFERENCE_ONLY ; bytes actuels NOT_OBSERVED |
| D1-C, `/var/lib/crypto-ai-research-audit/readonly_research_staging` | Copie opérateur sélectionnée ; fenêtre `[2026-10-10T00:00:00Z, 2026-10-11T00:00:00Z)` ; manifest SHA256 `a57d64a69aa4c65df5d5c601a5d56b169a8e31e7f81fd9b39de6a277bfeeb657` ; custody root:chatgpt-ro 0550 publiée | 10824 packets ; 9672 REJECTED = 5486 LINKED + 4186 PROVEN_NOT_ELIGIBLE ; `persistence_attempts=NOT_OBSERVED`, producer completeness NOT_PROVEN ; aucun roster autonome/receipt fsync montré | Autorisation et vérification HISTORIQUES ; existence/intégrité/accessibilité actuelles NOT_OBSERVED |
| D1-C source isolée, `/var/lib/crypto-ai-research-audit/readonly_d1_c_source` | Trois fichiers source réguliers 0440, répertoire 0550, preuves SHA publiées ; runner/classifier/auditeur | Code d'analyse, pas un jeu de reçus natifs ; ne fournit aucun dénominateur indépendant | SOURCE_REFERENCE_ONLY ; fichiers distants non relus |
| D1-D/E sur main, #409/#411 | Code pur et tests synthétiques intégrés ; quatre bundles D1-E explicites épinglés par hash | Capacité à vérifier des preuves fournies, aucune nouvelle preuve réelle ou acquisition indépendante | SOURCE_CAPABILITY ; REAL_INPUTS_NOT_OBSERVED |

Sources datées :
- [O6-B/O6-C](https://github.com/3a7i3/crypto-ia-terminal/issues/282#issuecomment-5924128455).
- [D1-C copie autorisée et rehash historiques](https://github.com/3a7i3/crypto-ia-terminal/issues/404#issuecomment-6115424334).
- [Forensic et gates D1-D/E](https://github.com/3a7i3/crypto-ia-terminal/issues/404#issuecomment-6116403851).
- [Intégration source #409/#411](https://github.com/3a7i3/crypto-ia-terminal/issues/404#issuecomment-6119896484).

Les identités O4/O6-B ne sont jamais transférées à D1-C : ce dernier déclare
`source_epoch_binding=UNVERIFIED`, `dataset_id=null`, `source_boundary_id=null`.
Les 4186 nonactionables ne sont pas un nombre de pertes de persistance.
L'indisponibilité de la passerelle ne démontre pas l'absence d'autres fichiers.

## Reprise bornée quand la passerelle autorisée est disponible

1. Vérifier identité limitée et permission pour les seuls chemins Research
   explicitement admis ; aucun home runtime, secret ou recherche globale VPS.
2. Inventorier les fichiers réguliers de la copie autorisée, sans suivre symlinks,
   puis vérifier custody/ancêtres, manifest historique épinglé et SHA recalculés.
   Ne pas déduire l'autorisation d'un nom de fichier ou d'une permission Linux.
3. Si roster/receipts sont présents dans ce périmètre, relever provenance native,
   source/code/config/epoch, dataset/boundary, fenêtre et cutoff, prefixes/offsets,
   acquisition indépendante et clock basis. Pins et source_id disjoints ne
   prouvent ni origine, ni indépendance, ni complétude.
4. Vérifier les plans natifs attempt_id (y compris retours sans packet, exceptions,
   interruptions et réanalyses), conservation du dénominateur et joins causaux.
   Ne jamais reconstruire un roster à partir des seuls packets/identities.
5. Pour D1-E : receipts de chaque étape, record bytes/hash/range, partition UTC
   physique, témoin fsync distinct lié au même appel, retards et fence de queue.
   RETURNED du listener n'est pas un reçu de persistance ; fsync-return ne prouve
   pas résistance aux crashs/pannes ni durabilité du répertoire.
6. Si ces preuves ne sont pas observables dans la copie autorisée : conserver
   NOT_OBSERVED/NOT_PROVEN. Une nouvelle copie, extension de permission ou export
   production exige une gate opérateur distincte. Instrumentation éventuelle
   pour une future epoch uniquement ; aucun backfill de preuves historiques.

Aucune commande d'export ou d'instrumentation n'est lancée par cet inventaire.
Un inventaire de noms/métadonnées serait un préflight ; l'admission exige la
vérification des bytes et de leur provenance sur un boundary explicite.

## Verdict

`AUTHORIZED_RESEARCH_COPY_REFERENCES=HISTORICALLY_OBSERVED`
`CURRENT_RESEARCH_COPY_BYTES=NOT_OBSERVED`
`D1_D_REAL_INDEPENDENT_ROSTER=NOT_OBSERVED`
`D1_D_PRODUCER_COMPLETENESS=NOT_PROVEN`
`D1_E_NATIVE_FSYNC_RECEIPTS=NOT_OBSERVED`
`D1_E_PER_PACKET_DURABILITY=NOT_PROVEN`
`D1_NATIVE_EPOCH_BOUNDARY_BINDING=NOT_PROVEN`
`COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`

Aucune finalisation burn-in, certification L4/U8, mutation runtime/PPL/FIN/config/
epoch/risk/sizing, restart/deploy, Watchdog/TESTNET/LIVE/exchange ou feedback
Research vers la même epoch. L3/U7 historiques ne remplacent pas ces gates.
