# RESEARCH-NATIVE-QUAL-01 — roster local et faisabilité témoin fsync

Mission #420 ; parents #414/#404/#408/#410 ; contrat #415.
Base source `31c0d3bfa9a83a27ccfe30daaec2404432d24ee8` (#417 intégrée).
Périmètre LOCAL_LAB_ONLY, aucune collecte du VPS ou de l'epoch active.

## 1. Roster acquis avant les packets — observation locale bornée

Le [harness](../../../scripts/research/qualify_future_roster_lab.py) écrit le
roster/plans de son scheduler synthétique dans un répertoire temporaire qu'il
possède, avant le lancement du premier worker. Il rehash le fichier avant/après
les workers et le transmet au verifier uniquement après acquisition séparée des
outputs. Il ne reconstruit aucun candidat/attempt_id depuis les packets.
Les IDs sont natifs au scheduler de laboratoire, jamais ceux du vrai Advisor.

Quatre candidats préenregistrés : packet, retour sans packet, exception avant
packet, non sélectionné ; trois invocations prévues. Chaque invocation utilise
un processus Python `-I -B` séparé, stdin/job explicite et stdout/receipt/packet.
Le worker horodate son appel/retour ; ces horloges natives locales ne sont pas
certifiées ni qualifiées pour des machines distribuées.
La fin des trois subprocess est contrôlée par le parent, pas une quiescence
producteur/queue attestée indépendamment. Un même opérateur contrôle scheduler,
worker et fixture : diversité de processus != racine de confiance indépendante.

[Résultats bruts](NATIVE_ROSTER_LAB_01_RESULTS.jsonl) : quatre runs, source hashes,
worker hash, bytes exacts du roster scheduler, reçus/packets capturés, exits et
réconciliation D1-D V2 conservés. Les fichiers temporaires sont nettoyés après
run ; leurs bytes de roster sont conservés dans l'output avant suppression.
Dataset/boundary/code/config des enveloppes sont explicitement SYNTHETIC ou pins
fictifs de fixture ; les hashes réels du code sont dans source_sha256, pas promus
en identité d'une vraie epoch. Les timestamps rendent le hash de roster propre
à chaque run ; aucune reproductibilité bit-à-bit temporelle revendiquée.

| Run / faute injectée | Résultat observé attendu et testé |
|---|---|
| none | 4 candidats, 1 non sélectionné, 3 tentatives : 1 PACKET_CAPTURED, 1 PROVEN_RETURN_NO_PACKET, 1 PROVEN_EXCEPTION_BEFORE_PACKET |
| drop_packet | Receipt avec packet retourné, capture supprimée intentionnellement : RETURNED_PACKET_NOT_CAPTURED=1 |
| drop_receipt | Packet conservé, receipt retiré intentionnellement : MISSING_INVOCATION_RECEIPT=1 et packet sans retour non ambigu=1 |
| worker_crash | Le premier worker quitte réellement avec code 3, sans receipt/packet : MISSING_INVOCATION_RECEIPT=1, pas RETURN_NO_PACKET fabriqué |

Toutes les conservations sont vérifiées : roster=selected+not_selected ;
planned_attempts=sum(categories)=3 ; hash roster avant/après MATCH.
La faute est injectée dans le laboratoire connu ; les sorties ne prouvent pas
la détection de tous les défauts communs ou opportunités absentes d'un roster.
Une omission réelle avant inscription au roster nécessite un contrôle externe
supplémentaire, non fourni ici. Pas de causal join par proximité temporelle.

Reproduction depuis la racine locale :

```bash
python scripts/research/qualify_future_roster_lab.py
PYTHONPATH="$PWD" python -m pytest -q -c /dev/null --noconftest \
  tests/research_data/test_future_roster_lab.py \
  tests/research_data/test_future_capture_core.py \
  tests/research_data/test_stress_d1_producer_attempts.py \
  tests/research_data/test_stress_d1_producer_denominator.py \
  tests/research_data/test_stress_d1_durability.py
```

Local : 210 tests ciblés PASS ; lint baseline 0 nouvelle violation.
Pas de qualification runtime ou corpus CI final anticipé.

## 2. Témoin fsync externe — préflight réel refusé

Instrument candidat présent : `/usr/bin/strace`. Préflight borné exécuté :

```bash
strace -qq -e trace=fsync -yy -ttt python -c 'import os; os.fsync(-1)'
```

Résultat local, exit 1 :

```
strace: test_ptrace_get_syscall_info: PTRACE_TRACEME: Operation not permitted
strace: ptrace(PTRACE_TRACEME, ...): Operation not permitted
strace: PTRACE_SETOPTIONS: Operation not permitted
strace: cleanup: waitpid(-1, __WALL): No child processes
```

Aucun fsync syscall-return n'a été observé par ce préflight. La qualification
strace est BLOCKED_BY_ENVIRONMENT. Pas d'élévation/bypass du confinement,
pas d'installation d'instrument privilégié, pas de substitution par un logger
applicatif. Le harness de roster ne réexécute pas strace et ne produit aucun
witness ; toutes ses sorties déclarent fsync_witness=NOT_QUALIFIED.

Cette interdiction technique n'est pas un défaut fsync du vrai runtime ni une
preuve que le writer échoue. Elle limite la qualification dans ce laboratoire.
Aucun accès ou changement de permissions du VPS n'est demandé par ce rapport.

## 3. Critères pour le prochain laboratoire autorisé

Avant expérience fsync : environnement distinct explicitement autorisé à observer
ses propres processus tests, provenance/version de l'instrument, confiance de
l'opérateur et permissions revue sécurité. Aucun contournement du confinement
actuel ; aucun instrument sur le burn-in. Commencer par un préflight bénin.

Le writer de test et le tracer sont des processus/canaux séparés. Ils travaillent
uniquement sur des fichiers temporaires de laboratoire. Le traceur doit fournir
entry/return syscall, errno, fd lifetime, file generation, ordre et clock basis.
Les captures de bytes/ranges/digests et écritures réelles doivent être jointes
causalement, pas par timestamp voisin. Strace -yy à lui seul fournit une indication
de chemin, pas une attestation complète inode/generation/source identity.

Cas discriminants obligatoires :
- writer écrit/flush/fsync réussi : syscall-return=0 effectivement observé ;
- writer prétend fsync sur stdout mais n'appelle pas fsync : aucun succès qualifié ;
- fd invalide/fsync errno : erreur native, aucune durabilité inférée ;
- fichier/fd réutilisé, rotation et append partiel : correspondance physique testée ;
- fsync groupé, tracer attach/drop/terminaison ou trace tronquée : UNKNOWN/incomplete,
  pas simple succès extrapolé depuis le dernier appel.

Une ligne strace de fsync réussi n'est ni une preuve de crash/power-loss durability,
ni directory fsync, ni custody indépendante. Le coût ptrace doit être benchmarké ;
une observation intrusive peut modifier l'expérience. Aucun choix production
strace/eBPF/wrapper n'est effectué. Adapter/V2 pour group-fsync/retries reste ouvert.

## 4. Verdicts et frontières

`ROSTER_LAB_MECHANISM=PARENT_PLAN_BEFORE_SEPARATE_WORKER_OBSERVED`
`REAL_PRODUCER_ROSTER_ACQUISITION=NOT_QUALIFIED`
`FSYNC_SYSCALL_WITNESS_QUALIFICATION=BLOCKED_BY_ENVIRONMENT`
`FSYNC_SYSCALL_RETURN_OBSERVED=NOT_OBSERVED`
`D1_D_PRODUCER_COMPLETENESS=NOT_PROVEN`
`D1_E_PER_PACKET_DURABILITY=NOT_PROVEN`
`C2_NATIVE_INSTRUMENT_QUALIFICATION=INCOMPLETE`
`FUTURE_CAPTURE_ACTIVATION=DENIED`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`

Cette livraison ne ferme pas #420 : la preuve du témoin réel reste manquante.
Aucun roster de l'epoch active fabriqué, aucun nouveau flux/export/staging
production, privilege/secret/config/epoch/PPL/FIN/risk/sizing/Watchdog/TESTNET/
LIVE/exchange, déploiement/restart ou feedback. Rollback des seuls fichiers
harness/test/rapport, sans modification du core ou d'un composant déployé.
