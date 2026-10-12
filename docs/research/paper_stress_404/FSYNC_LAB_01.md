# FSYNC-LAB-01 — laboratoire distinct autorisé

Mission #422 ; parents #420/#414/#404 ; autorisation opérateur du 2026-10-12.
Base `31c0d3bfa9a83a27ccfe30daaec2404432d24ee8`.
L'environnement local a refusé ptrace ; passerelle VPS Offline au préflight.
Ce protocole utilise un **runner GitHub hébergé éphémère**, pas le VPS Advisor.

## Frontière et permissions

[Workflow](../../../.github/workflows/fsync-lab-01.yml) : ubuntu-24.04,
contents:read, checkout persist-credentials=false, aucun secret fourni, aucun
service/network/trading/VPS configuré ; délai maximal 5 min. Le traceur observe
seulement son propre enfant de test. Aucun changement seccomp/Yama/capability,
sudo, installation privilégiée ou attachement à un processus existant.
Si strace est absent ou ptrace interdit, le rapport garde NOT_OBSERVED et le
job échoue au lieu de produire un faux succès. Aucune reprise cachée ou bypass.

Le runner utilise checkout/upload-artifact pour le code et les seules preuves
synthétiques. Artifacts retention 7 jours, bornés par trois appels et fichiers
minuscules ; leur archivage durable avant expiration relève du reviewer.
Cette retention n'est pas une custody immuable ni une preuve d'indépendance.
Workflow pull_request filtré au seul protocole de laboratoire et workflow_dispatch
pour une reprise explicite ; pas de déclenchement production/push/main/deploy.

## Cas réellement à observer

[Harness](../../../scripts/research/qualify_fsync_lab.py) : output fresh directory
0700 sous parent temporaire existant ; ouverture exclusive des records ; contenu
constant SYNTHETIC_FSYNC_LAB_ONLY. Un processus strace et un writer Python séparé,
`-I -B`, aucun import du projet. Trace fsync uniquement, timestamps natifs et fd/path.
Hash du script, du worker et du binaire traceur, version Python/strace et plateforme
sont inclus dans report.json. Strace disponible est un candidat, pas une root de
confiance authentifiée simplement parce que le binaire est hashé.

| Cas | Preuve externe exigée |
|---|---|
| real | Exact record bytes lus après writer ; une trace fsync(fd<chemin dédié>) return=0 |
| claim_without_call | Le writer prétend succès ; trace sans fsync, syscall_success_observed=false |
| error | fsync(-1) retourne -1 EBADF réellement tracé ; aucune durabilité |

Préflight strace sur un enfant `pass` avant les cas. Échec => pas de qualification.
Parser fail-closed : toute ligne inconnue, unfinished/resumed, retour contradictoire
ou errno manquant abort. Les huit tests parser sont synthétiques et ne sont pas
un substitute de la trace réellement acquise. Un timeout/tracer fail abort le job,
artefacts existants préservés avec always(). Aucune omission relabellisée succès.

La trace raw, stderr, exact records et report.json sont uploadés. Les joins fd/path
et record hashes sont vérifiés dans le harness. dev/inode enregistrés **après
close** ne prouvent pas la génération/inode pendant le syscall, ni les ranges
couverts ; ces deux garanties restent NOT_QUALIFIED. Même un job vert ne complète
pas le contrat D1-E pour une vraie population de décisions.

## Verdicts selon résultat effectif

Avant lecture réelle du job et des traces : FSYNC_LAB_RESULT=NOT_OBSERVED.
Si les trois cas passent : LAB_SYSCALL_MECHANISM_OBSERVED, portée enfant synthétique
sur ce runner uniquement. Jamais D1_E_PER_PACKET_DURABILITY=CERTIFIED.
Échec d'instrument => NOT_OBSERVED ; fixtures parser PASS ne lèvent pas cette limite.

Restent séparés : confiance/custody, génération fd/file et write ranges, mapping
attempt/packet/receipt, gaps de tracer, rotation, group-fsync/retries, coût ptrace,
clock quality et qualification host. Retour fsync ne démontre ni crash/power-loss
ni directory durability. L'acquisition du vrai roster demeure NOT_QUALIFIED.

`FUTURE_CAPTURE_ACTIVATION=DENIED`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`D1_D_PRODUCER_COMPLETENESS=NOT_PROVEN`
`D1_E_PER_PACKET_DURABILITY=NOT_PROVEN`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`

Aucun collecteur natif installé, aucune modification du burn-in/VPS/runtime/
config/epoch/PPL/FIN/risk/sizing/secret/privilège production/Watchdog/TESTNET/LIVE/
exchange/restart/deploy/feedback. Rollback des seuls fichiers labo et suppression
du workflow, sans effet sur un service ou ledger déployé.
