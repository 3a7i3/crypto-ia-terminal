# PPL-QUIESCENCE-01 — Lot B, témoin externe v2

Statut : source locale et tests synthétiques, base 51883807453b7e2e90b2b1678b4b3e9ba573bbbe.
Contrat v2 corrigé avant le code, politique CLI approuvée par l'opérateur.
GO opérateur limité à source/tests/contrat ; aucun
commit, push, PR, VPS, service, epoch ou activation. Le lot A v1.2 reste inchangé.

## 1. Fonction

`python -B -m paper_trading.ppl_quiescence_witness` lance une mesure ponctuelle.
Pour isoler aussi les imports du parent, préférer
`python -I -B /chemin/absolu/repo/paper_trading/ppl_quiescence_witness.py`.
Le mode -m reste disponible dans un environnement parent de confiance ; il
n'isole pas à lui seul cet environnement. Les deux chemins sont sans activation.
Le parent crée un interpréteur neuf isolé (`-I -B`), environnement minimal et
groupe de processus distinct. Seul le worker importe les primitives A ; aucun
import Advisor ou MexcSimulator, aucune instanciation de moteur, aucun réseau.
L'import Python du package paper_trading charge ses dépendances statiques
existantes : leurs effets transitifs doivent être testés.

Entrées obligatoires : `--manifest`, `--authority-root`, `--proof-dir`,
`--coordination-file`, `--epoch`, `--observation-sha256`. Tous les chemins sont
absolus, existants, sans symlink dans leurs ancêtres ; les fichiers sont
réguliers. Aucun emplacement de production ou de #282 n'est un défaut.
`--timeout` : défaut 15 s, intervalle [0.5, 60] ; `--max-age` : défaut 900 s,
intervalle ]0, 900]. Aucun `--now`, compteur, PID, `stopped` ou exit_status fourni
par l'opérateur ; l'heure vient de time.time(), les délais de time.monotonic().

Bornes fixes : manifest/coordination 1 MiB chacun ; preuve et autorité 16 MiB
chacune, 4096 entrées chacune, profondeur 4 ; chaque fichier <= 1 MiB sauf ledger
<= 16 MiB ; sortie JSON <= 64 KiB ; fichiers stdout/stderr <= 1 MiB par RLIMIT_FSIZE.
Worker : RLIMIT_AS 512 MiB et CPU timeout arrondi + 2 s. Ces limites sont
techniques, ne modifient aucune configuration scientifique.

## 2. Coordination déclarée

Fichier JSON strict, schéma PPL-WITNESS-COORDINATION-V1, champs exacts : schema,
observation_sha256, authority_store_root, boot_id, pid_namespace, created_at,
expires_at, operator, reason, start_paths_inhibited. Le booléen doit être true,
les chaînes d'auteur/raison non vides ; création passée et expiration future,
validité <= 900 s. La fenêtre doit couvrir le budget restant plus 0.1 s de marge,
sinon refus avant mesure. Racine, observation, boot et namespace doivent correspondre.
Le hash des octets est lié au witness_identity et au résultat. Les triplets
coordination_verified=false, operational_qualification=NOT_QUALIFIED et digest
de coordination sont aussi persistés dans le WITNESS, avec l'intervalle de
mesure, la deadline monotone liée au boot et le caractère non atomique de la
dernière vérification précédant publication.

Il s'agit d'une déclaration, **pas d'une preuve d'inhibition effective**. Chaque
résultat porte operational_qualification=NOT_QUALIFIED et
coordination_verified=false. La future qualification VPS exige une autorité de
coordination externe démontrée ; aucun appel systemd ou cloud dans B. La sonde
LOCK_SH est brève et peut gêner un lancement concurrent hors de cette fenêtre.
Le témoin ne démontre pas l'exclusivité de tous les producteurs et ne produit
aucune clearance de succession.

## 3. Préflight et publication

Avant publication : bornes, chemins, chaîne intacte et entièrement confirmée,
dernière O identifiée par son SHA, fraîcheur, liaisons manifest/epoch/racine/code
et config. Le manifest est lu avec le validateur natif ; son SHA brut doit égaler
son identité native sérialisée. JSON dupliqué ou non fini refusé. Aucune
normalisation implicite du fichier n'est admise.

Le worker doit être distinct du PID observé. Le package témoin est identifié par
le hash canonique des hashes des fichiers Python de paper_trading et
execution_simulator, y compris le nouveau module. Cette empreinte n'est pas le
SHA Git du processus observé et ne certifie pas à elle seule un déploiement.

Réutiliser write_witness sans corps déclaratif, puis assess ; ne jamais appeler
write_observation, write_seal, bind, append d'autorité, close/open de gate ou un
constructeur de simulateur. Le statut de sortie superviseur reste UNKNOWN.
Relire le WITNESS confirmé et vérifier la liaison exacte à O avant résultat.
Après toute attente sur les verrous, puis immédiatement avant le link du record
sous verrou d'écriture de preuve : recontrôler parent, échéance, coordination,
fraîcheur de O et dernière O confirmée. La classe B spécialise les primitives
du ProofStore ; A reste inchangé. Une nouvelle O avant ce link interdit l'ajout.
Si elle arrive après, le résultat devient PUBLISHED_UNVALIDATED avec identité et
confirmation connues ; aucune écriture déjà observée ne devient NOT_PUBLISHED.

Les seules écritures permises sont le répertoire de preuve et l'espace
temporaire. La lecture native ouvre le verrou PPL existant en a+b : aucune
compatibilité avec une autorité montée strictement RO n'est revendiquée.
Le store doit rester dans la fenêtre coordonnée (pas de remplacement de ses
chemins par un autre acteur). L'authenticité face à un écrivain hostile, la
vérité de la coordination, les effets après T et les pannes matérielles sont
hors contrat ; les lectures peuvent modifier atime. Aucun effacement de verrou.

## 4. Échéance et sortie

Échéance globale monotone du parent couvrant le worker entier. Dès le bootstrap,
avant les imports métier, le worker arme Linux PR_SET_PDEATHSIG/SIGKILL et un
timer mural ITIMER_REAL pour la même deadline absolue. Il vérifie le parent
attendu après armement ; décès pendant le bootstrap implique refus avant toute
publication. Primitives indisponibles : échec fermé, jamais mode dégradé.
Le timer couvre les flock bloquants, contrairement à RLIMIT_CPU. Son expiration
termine le worker sans dérouler de nouveau traitement de publication.
stdout/stderr
vont dans des fichiers temporaires, jamais dans des pipes. À toute sortie,
kill du worker encore non récolté et wait borné (2 s maximum après l'échéance).
Ne pas envoyer killpg après wait réussi. Le worker interdit les créations de
processus par les APIs Python auditées et ne crée aucun descendant produit.
Pas de lecture native dans le parent, pas de daemon ou enfant survivant admis.

Sur timeout, le résultat porte publication_state=UNKNOWN et ne prétend pas
qu'aucun enregistrement n'a été publié. Un record visible n'est ni effacé ni
renuméroté ; recovery ne peut concerner que le répertoire de preuve dédié,
explicitement via l'API A, jamais l'autorité. B refuse une chaîne non confirmée
au préflight puis sous verrou d'écriture et n'appelle pas recover(). La garde B
refuse donc aussi un record concurrent non confirmé avant d'entrer dans append()
de A ; elle ne demande pas à A de le resynchroniser automatiquement. Le protocole
de recovery de A reste inchangé et disponible par décision explicite sur le seul
répertoire de preuve. B vérifie de nouveau la chaîne après publication.

JSON de schéma PPL-EXTERNAL-WITNESS-RESULT-V2 (rupture explicite de la politique
CLI v1), séparant command_status, publication_state, witness, assessment, provenance
du package, coordination et limites. Publication : NOT_PUBLISHED (aucun record
de cette tentative), VISIBLE_UNCONFIRMED, CONFIRMED ou UNKNOWN. PersistUncertain
conserve sa seq/sha ; PersistBlocked ne prétend pas avoir consommé une séquence.
Les faits connus sont monotones : un défaut d'assessment ou de coordination
après publication donne PUBLISHED_UNVALIDATED et conserve l'identité du record.
Une chaîne UNRESOLVED et une chaîne UNCONFIRMED ont des motifs distincts.

| Exit mesure | Sens |
|---:|---|
| 0 | Réservé : quiescent=true ET reçu durable ET coordination vérifiée ; impossible pour B actuel |
| 10 | Mesure confirmée, quiescence non établie (voir assessment) |
| 11 | Mesure confirmée, mais receipt_durable=false |
| 12 | Résultat quiescent selon A, coordination toujours non vérifiée |
| 20 | Précondition refusée avant publication |
| 21 | PUBLISHED_UNVALIDATED : record déjà publié, résultat non validé |
| 30 | Erreur de persistance, avec faits de visibilité connus |
| 31 | Erreur E/S d'inspection, distincte d'une erreur de paramètre |
| 40 | Timeout, publication UNKNOWN si le parent n'a pas reçu de faits |
| 50 | Erreur de worker/lancement/ressources ou garde Linux indisponible |

Les sorties d'erreur ne fabriquent aucun flag de quiescence. Le flag scientifique
reste celui de A dans un résultat COMPLETED ; la qualification opérationnelle
reste NOT_QUALIFIED. --help est une opération d'aide conventionnelle en exit 0,
sans JSON de mesure ; elle n'est pas une mesure réussie. Aucun exit n'autorise
une activation, une admission ou une reprise d'Advisor.

Dernier fsync du reçu en échec : record déjà durable selon A v1.2,
receipt_durable=false et code 11 ; ne pas le convertir en PersistUncertain.
PDEATHSIG et timer ne donnent pas une transaction atomique entre mort du parent
et link : interruption à cette frontière peut laisser un record visible avec
ou sans reçu, conformément à A. Les tests de mort du parent pendant attente
doivent démontrer absence de publication tardive ; aucune garantie matérielle
ou résistance à un écrivain hostile n'est ajoutée.

## 5. Acceptation et hors périmètre

Tests sous Python 3.11 hors réseau : liaisons et fraîcheur, compteurs inconnus,
PID vivant/tué, arrêt sans sceau, verrou remplacé/absent, lecture PPL bloquée,
timeouts et nettoyage de groupe, sorties volumineuses, erreurs de persistance,
import passif, autorité/gate inchangées. Les tests A restent verts. Tests
synthétiques seulement ; un contrôle du package ne qualifie pas le VPS.

Aucune modification A/Advisor/simulateur/store/workflow. Un besoin dans ces
fichiers impose une révision de scope. Revue indépendante du patch exact avant
une décision séparée de commit/push/PR ; installation et lot C restent distincts.
