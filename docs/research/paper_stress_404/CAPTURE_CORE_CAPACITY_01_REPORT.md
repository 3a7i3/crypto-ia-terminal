# RESEARCH-CAPTURE-CAPACITY-01 — qualification synthétique locale

Mission #418 ; parent #414 ; noyau #416/#417 intégré dans
`main@31c0d3bfa9a83a27ccfe30daaec2404432d24ee8`.
Module SHA256 : `e5a742bc8c9ecdde848726f17acd670e104a9afca19a3e19aa9c8b7c0bd003b3`.
Worker SHA256 : `728ae6f3a83ad4471b58e86c7014ebe91db008582d81e3d35c27079bcae29dc4`.
Aucune modification du module de capture dans cette mission.

## Méthode reproductible

Depuis la racine d'un checkout de laboratoire, Python 3.12.14, Linux x86_64 :

```bash
python scripts/research/benchmark_future_capture_core.py
```

Le script importe explicitement deux modules purs sous un package isolé et
exécute six processus enfants `python -I -B`, trois par scénario. Il utilise
uniquement des événements SYNTHETIC qu'il génère localement. Il ne lit aucun
journal/secret/environnement/runtime et ne se connecte à aucun réseau/VPS.
Les opérations fichier lisent le code local ; les subprocess sont des workers
bornés de benchmark, pas une instrumentation de production.
Le main guard empêche le benchmark de s'exécuter à l'import.

Limites proposées du contrat : 4096 événements, 16 MiB retenus, 64 KiB par événement.
Chaque worker fournit exactement 8192 événements avec séquences consécutives.
Padding de 2048 bytes (scenario count), puis 64000 bytes (scenario bytes).
L'append p99 mesure appels acceptés ET refusés, sans génération JSON ; CPU/wall
mesurent la boucle complète incluant génération et instrumentation des timings.
Le seal est mesuré séparément. RSS est le **high-water mark du processus Linux**,
pas une allocation exclusive du core : imports, timing list et décodage inclus.
Les données brutes figurent dans [RESULTS.jsonl](CAPTURE_CORE_CAPACITY_01_RESULTS.jsonl).
La première série exploratoire n'est pas confondue avec les mesures consignées.

## Résultats consignés — trois répétitions par scénario

| Scénario | Acceptés | Bytes retenus | Refus | Append p99 | Seal | RSS pic après seal |
|---|---:|---:|---:|---:|---:|---:|
| Count | 4096 | 10498823 | 4096 EVENT_COUNT_LIMIT | 35.814–73.471 µs | 8.824–10.355 ms | 25034752 bytes (~23.875 MiB) |
| Bytes | 260 | 16773056 | 7932 BYTE_LIMIT | 206.001–367.123 µs | 10.296–12.982 ms | 30015488 bytes (~28.625 MiB) |

Tous les workers : assertions bounds/count/bytes/refus/hash PASS ; zero gap
**dans les séquences synthétiques fournies** ; capture_status INCOMPLETE (refus).
Aucun module core/runtime/paper_trading/observability chargé dans les workers.
Manifest identique pour les trois répétitions d'un même scénario :
- count : `9a80e3075f45519393d2427dfb6c7c5424125d7795ee4011b8f22dafa869adb5` ;
- bytes : `89c93e3377125aeab04a1c221e4c6932ea8affad34ca37bc46c0bd9cb25dcb96`.

RSS high-water entre la 4096e et 8192e tentative : +262144 bytes dans les deux
scénarios. Cela inclut l'accumulation fixe des 8192 timings et le processus ;
ce n'est pas une preuve d'absence de croissance du heap core à durée infinie.
CPU boucle : count 176.737–192.314 ms ; bytes 1838.884–2023.374 ms.
Aucune mesure CPU sur 60 s, scheduler/threads concurrents ou hardware VPS.

## Interprétation et limites de la gate

**C3_CORE_LOCAL_SYNTHETIC_BOUNDS_OBSERVED** : limites exactes respectées et
refus explicites, sans éviction des bytes acceptés dans ces scénarios.
Les mesures sont compatibles avec le budget proposé RSS 128 MiB **dans cet
échantillon local seulement**, et ne qualifient pas la somme collecteur+writer+witness.
Le p99 append seul ne démontre pas un overhead invocation Advisor <5 ms ;
le seal p99 n'est pas estimé à partir de trois appels, seuls min/max sont reportés.
Le gel prend ici jusqu'à ~13 ms : pas de seal synchrone dans l'analyse active
admis par ce rapport. Production/fsync/disk/CPU host/clock/custody restent non mesurés.

Les six répétitions ne sont pas des observations de marché ni une puissance
statistique de trading. La reproductibilité du manifest vérifie les bytes
fournis, pas l'indépendance de producteurs ou la durabilité.
Aucune suite générale locale rerun revendiquée pour ce protocole ; le core
possède sa CI historique au HEAD #417. Nouveau HEAD protocole à vérifier.

Validation source locale : 32 tests core PASS, Ruff ciblé et gate baseline
PASS (0 nouvelle violation), parsing des sept lignes JSON de résultats,
liens relatifs et diff --check. Aucun test/baseline/certificat runtime modifié.

## Suite effective

Avant acquisition native : qualifier le mécanisme de roster et son contrôle
externe, définir le témoin syscall indépendant et permissions, protocoles
retries/group-fsync/clock/fences et budgets writer+witness. L'implémentation
future demeure isolée du burn-in ; source review/qualification et activation
sont des gates séparées. Les propriétaires et roots de confiance restent à admettre.

`C3_HOST_WRITER_WITNESS_QUALIFICATION=NOT_PROVEN`
`NATIVE_CAPTURE_PIPELINE=NOT_IMPLEMENTED`
`D1_D_PRODUCER_COMPLETENESS=NOT_PROVEN`
`D1_E_PER_PACKET_DURABILITY=NOT_PROVEN`
`FUTURE_CAPTURE_ACTIVATION=DENIED`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`

Aucun VPS, nouvelle capture/export production, mutation de config/epoch/PPL/FIN/
risk/sizing, instrumentation active, secret/privilège/restart/deploy/Watchdog/
TESTNET/LIVE/exchange ou feedback. Rollback : revert du protocole et rapport,
sans modification du noyau ou d'un composant déployé.
