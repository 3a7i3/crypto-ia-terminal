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
| error | fsync(descripteur positif fermé) retourne -1 EBADF réellement tracé ; aucune durabilité |

Préflight strace sur un enfant `pass` avant les cas. Échec => pas de qualification.
Parser fail-closed : toute ligne inconnue, unfinished/resumed, retour contradictoire
ou errno manquant abort. Les tests parser sont synthétiques et ne sont pas
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

## Premier run conservé — diagnostic de fixture

Run 38312088127 / job 115019974692 au HEAD 62fbe6f... : préflight réussi,
fsync réel observé par strace et trace vide pour le faux claim. Run global FAIL
car Python refuse un fd négatif par ValueError avant syscall. Aucun succès
global anticipé. Artifact 11774509686, ZIP SHA256 recalculé
`91dd2cb65f3c93642cb388df837b548424a52075fd774b503a866504b32ee704`.
La fixture est corrigée avec os.dup puis os.close et fsync(fd positif fermé),
pour tester effectivement errno EBADF au kernel ; nouveau HEAD/run à observer.

## Observation effective — run corrigé, 2026-10-12 UTC

Run [38312335279](https://github.com/3a7i3/crypto-ia-terminal/actions/runs/38312335279),
job 115020783899 SUCCESS, testé au HEAD `12547efa9e3ea6c42369dae3818d36593c8f0e11`.
Runner Linux 6.17.0-1022-azure x86_64 / Python 3.12.3 / strace 6.8.
Trois cas complets :
- real : `fsync(3<.../real.jsonl>) = 0` à 1791841396.045183 ;
- claim_without_call : writer claim=true, **zéro byte de trace fsync** ;
- error : `fsync(4) = -1 EBADF` à 1791841396.157109.

[Report natif du harness](fsync_lab_01_evidence_20261012/report.json),
[trace positive](fsync_lab_01_evidence_20261012/real.trace),
[trace erreur](fsync_lab_01_evidence_20261012/error.trace),
[trace vide du faux claim](fsync_lab_01_evidence_20261012/claim_without_call.trace),
[provenance et hashes](fsync_lab_01_evidence_20261012/provenance.json).
Tous les artefacts sont SYNTHETIC_CHILDREN_ONLY, aucun fait de marché/production.

Artifact 11774788285 téléchargé ; ZIP SHA256 recalculé MATCH
`38d374160af2d4acdf6018640ce2731ad080e4725934a4aa3f19ddd624435981`.
Les bytes exacts des douze fichiers du ZIP et un manifest de provenance sont
conservés ici pour survivre à l'expiration GitHub du 2026-10-19.
Script testé SHA256 `8eb6af7a0c6aa4a2e7a2481f5aebadba26a77cf3b02969e36cead6176baaf6de`
revérifié contre source locale ; hashes report/trace/record recalculés MATCH.
Chaque record synthétique a 48 bytes, SHA256
`e74dede43baad52af6d42632ea966d077f1e6053484eb08bdedeafdfff413625`.

**FSYNC_LAB_SYSCALL_MECHANISM_OBSERVED** sur ce run uniquement.
Ce résultat lève l'obstacle d'environnement pour ce laboratoire GitHub, sans
changer le confinement local ou le VPS. La qualification globale C2/D1-E demeure
incomplète : génération fd/file, ranges, joins de décisions, source/trust/custody,
rotation/group-fsync/coût et preuves de la future epoch restent séparés.
Le commit de conservation documentaire n'est pas le HEAD du run mesuré : ne pas
promouvoir la CI au nouveau HEAD ni un merge/main avant vérification séparée.
