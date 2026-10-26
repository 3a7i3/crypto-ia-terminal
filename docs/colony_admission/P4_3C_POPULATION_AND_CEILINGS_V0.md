# P4 / 3C — Population et plafonds, contrat v0

**CONTRACT_FOR_REVIEW / SOURCE_ONLY / LAB_ONLY / NO_IMPLEMENTATION.**
Périmètre validé par Mathieu le 2026-10-26 : contrat détaillé et matrice avant code.
Baseline `main@d890081e94bcf0818145d0f919162e11cae8e58f`, tree
`f70d21a6d2ef456b3bee692636d7f6f79890647d` ; plan initial #508 HEAD
`3c9e502d81585d08fdd69f146c01cd92f1bf874a`, tree
`0c40086d07f202967cb44ab078bf7dc3fec8b541`.
Normes : [P1](ADMISSION_CONTRACT.md), [scénarios P1](SCENARIOS_A0.json),
[plan validé](P4_3C_PLAN_AND_REUSE_V0.md),
[3A](P4_3A_PHYSICAL_EVIDENCE_JOIN_V0.md),
[3B](P4_3B_ATTESTATIONS_AND_ANCESTRY_V0.md),
[matrice 3C](P4_3C_POPULATION_AND_CEILINGS_CASES_V0.json).
P1 prime. Pins : `e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd`
et `4e518bfec6faaa582c2c42633d80e989b8204708b554f74b0eb1bbee6eaa59a1`.
Ce contrat n'amende ni leurs bytes, ni g0, ni un format persistant existant.

## 1. Portée et verdicts

Observer la population actuelle exhaustive, ses preuves propres, sa partition
hors branche et les comptes/plafonds de l'unique opération ouverte. Les anciens
plans ne deviennent pas des inventaires courants ou des snapshots historiques.
Aucune naissance, installation, reprise, consommation ou transition n'est effectuée.

Tout objet public impose accepted=false, non paramétrable. authorization,
durability, rotation, recovery, source_revision_provenance et operational_completeness
restent NOT_EVALUATED (NE). Le champ completeness global reste NE : les comparaisons
bornées se nomment snapshot_completeness et frozen_completeness, avec leur portée.
Aucun qualified/admitted/can_parent/can_resume positif n'est exposé.

Chaque comparaison nommée vaut PASS, FAIL ou NE : FAIL si contradiction observée,
NE si prérequis absent/non supporté, PASS si tous ses prérequis sont établis.
FAIL domine NE. Une liste vide de prérequis inconnus ne produit pas PASS.
Status OBSERVED exige zéro blocker et toutes les comparaisons exigibles du scan
évaluées ; sinon BLOCKED. Une observation OBSERVED reste sans autorité.
Un champ non applicable reste NE avec son code de portée et n'est pas assimilé
à un échec ; les exceptions non bloquantes sont énumérées aux §3, §5, §9 et §11.

## 2. API et données publiques immuables

API distincte : `PopulationObserver(PopulationConfig).scan_population()`, sans
argument de méthode. PopulationConfig contient exactement `attestations`, objet
AttestationConfig existant ; aucun override de foyer, statut, compte, own_child,
required ou terminaison. La validation détachée de configuration/politique fournie
précède tout accès lab/ledger. G0 par défaut est acquis sous son chemin et pin 3B.

Ne pas changer les signatures/résultats de FileObserver ou AttestationObserver.
Le nouveau lecteur peut factoriser leurs primitives, pas appeler leurs méthodes
publiques puis relire. Les résultats, sous-objets et collections sont frozen/tuples ;
pas de dict/list trust, record ou enveloppe mutable renvoyé. Les chemins publics
sont relatifs aux ressources nommées, erreurs à codes fixes sans contenu soumis.

| Objet | Champs requis |
|---|---|
| PopulationEvidence | schema `colony-admission.population-evidence/0`, status, blockers, warnings, sources/metadata_sources, limits/reached, ledger snapshot canonique et coverage, log_coverage, homes, operations, external_terminations, fault_bindings, action_facts |
| Agrégats du scan | inventory, population, snapshot_completeness, global_identity_exclusions ; completeness/authorization et limites §1 NE |
| HomeFact | agent_id, spec_id/digests observés si disponibles, rôle, parent/founder/génération validés, immutable FileFacts, classification, classification_codes, birth_proof, individual_proof, scientific_bindings, identity_exclusions, counted, execution_restriction |
| OperationPopulation | child/id/spec/attempt/digest, latest, source_state, scope CURRENT_OPEN ou HISTORICAL, own_home, besoins/items 3B étendus, decision_partition, population_partition, frozen_completeness, counts, plan_match, ceilings par prédicat et agrégat, blockers |
| Counts | scope CURRENT_BEFORE_BIRTH, included_agent_ids et H(records) triés, P/F/children, six sommes de budgets, complete PASS/FAIL/NE ; valeurs exactes null si univers indéterminé |
| FaultBinding / TerminationFact / ActionFact | références de claims/digests, ressources/identités liées, état des preuves et codes ; aucune permission d'action |

Homes triés par ID ; opérations par (child, attempt, operation digest) ; items par
K de 3B ; codes dédupliqués ; aucun record en bytes n'est exposé dans les items.
Les stamps raw SHA256 restent distincts de H(record canonique complet), lui-même
distinct du champ interne individual.record_hash calculé sans ce champ.
Counted vaut INCLUDED, EXCLUDED_OWN, BLOCKING ou NE, jamais un booléen ambigu.
Execution_restriction = EXECUTION_SUSPENDED uniquement pour SUSPENDED ; son absence
n'est pas EXECUTION_ALLOWED. Aucune mesure ou interdiction effective de run.

Inventory PASS signifie que tous les noms/objets requis ont été acquis sous les
bornes et revalidés, même si un record stable se révèle divergent. Population est
FAIL si au moins un UNAUTHENTICATED, sinon NE si une classification reste NE,
sinon PASS (les cinq statuts ne sont pas cinq permissions). Snapshot_completeness
agrège inventory, population, exclusions globales et disponibilité de tous les
besoins courants exigibles ; aucune omission ou NE bloquante ne laisse ce champ
PASS. Frozen_completeness agrège les deux partitions figées et toutes leurs copies
requises pour CURRENT_OPEN ; crypto et ceilings restent des propriétés séparées.
Global_identity_exclusions exige l'univers entier lié et tous les émetteurs
exigibles contrôlés ; une individuelle absente permise n'invente pas d'émetteur.

## 3. Un seul propriétaire et ordre d'acquisition

1. Configuration détachée valide ; racines explicites séparées ; ouvrir L1 existant
   O_RDONLY et verrou exclusif non bloquant. Aucun lock/fichier créé.
2. Acquérir fault log et installed trust/history une fois, validateurs existants,
   racine actuelle sous pin extérieur, floor max(opérateur, installé), LAB_TEST.
3. Inventorier les logs et les claims externes ; appliquer §10 aux logs faulty.
   Parser tous les autres logs strictement, toutes leurs tentatives ; fragments
   ACK/CR opaques selon parser, pas splitlines. Vérifier nom/lab/child/attempt/hash.
4. Construire U = union dédupliquée des hashes PREPARED inventoriés et des hashes
   de terminaisons externes lexicalement valides du fault log. Au plus 256 U,
   256 tentatives lisibles et 256 noms de logs ; tout dépassement avant ledger.
   Les claims /0 externes participent à U même si leur preuve restera NE.
5. Inventorier individuals/ et les namespaces privés nécessaires (§4, §11),
   établir les chemins/tailles/limites structurelles déjà connaissables. Borne
   d'items policy/hard connue des logs vérifiée avant ledger, sans signature.
6. Ouvrir le ledger une seule fois, FD frais O_RDONLY offset 0 ; sous L2 partagé
   non bloquant appeler inspect_operations_fd(fd, sorted(U)) une seule fois.
   Aucun ajout tardif d'ID, second lot ou autre ouverture ledger.
7. Acquérir records, lignées, attestations et checkout une fois par path/ressource ;
   bornes des besoins dérivés avant toute signature. Vérifications pures ensuite.
8. Revalider listings, absences, FD/path et métadonnées ; close/unlock réussis de
   tout le contexte avant restitution. Résultat construit à l'intérieur reste
   provisoire et est effacé si la sortie du contexte échoue.

Coverage ledger : matched = somme operation_entries des rows distinctes de U ;
MATCH exige legacy_entries=0, total_entries=matched et aucune row CONFLICT.
Les rows d'externes validés expliquent des lignes sans PREPARED lisible mais ne
prouvent pas une naissance. Les autres lignes orphelines restent UNBOUND bloquant ;
l'inspecteur n'exporte pas leurs objets : aucune tentative pour les deviner/lire.
Les données historiques d'une observation externe ne sont pas ce snapshot courant.

Ne pas conserver comme blockers globaux les seules étiquettes STICKY_FAULT ou
EXTERNAL_TERMINATION_NOT_EVALUATED de l'ancien join sans les qualifier : le nouveau
mode applique §10 ; les anciens modes gardent exactement leur refus conservateur.
L1→L2, pas de L1 sous L2, aucun retry ou acquisition imbriquée.

## 4. Inventaire privé et objets requis

Racines lab, individuals/, admission-ops/, registrar-admissions/ et
admission-envelopes/ obligatoires, répertoires euid0700, NOFOLLOW. Absence de
individuals/ = SOURCE_UNAVAILABLE, jamais population vide. Son listing stable
vide est un inventaire vide ; sans opération candidate les prédicats de naissance
restent NE/NO_CURRENT_OPEN_OPERATION, non bloquant si rien d'autre ne l'est.

Chaque entrée individuals/<id> : id hex64 lowercase unique, vrai répertoire privé.
Entrée inconnue, lien/type spécial ou nom invalide => SOURCE_NAMESPACE_INVALID,
invalidation totale. Record/spec JSON stable invalide => FileFact DIVERGENT local,
HomeFact UNAUTHENTICATED ; absence stable => missing explicite, pas de foyer ignoré.
Lire record.json et spec.json pour chaque foyer. L'ID doit égaler nom de répertoire
et identité A1 de spec. Valider la lignée founder→descendant avec visités/borne 9
et lineage.verify_record ; chaque parent doit appartenir à l'inventaire réel.
Pas de pseudo-opération de naissance pour valider un individu isolé. Parent
stablement absent, lien de lignée impossible ou cycle prouvent une structure
divergente : UNAUTHENTICATED, pas un simple NE de capacité scientifique.

Pour chaque descendant, acquérir birth_qualification.json, admission et statement,
avec mapping exact 3B §6. Les enveloppes individuelles/admission/qualification sont
nommées avec H(record correspondant) ; statement avec H(qualification) pour le path
et H(statement) pour son record signé. Toute copie requise d'un même K est acquise
et comparée. Aucun path lu depuis le contenu d'un statement ou un item figé.
Qualifier les records/admissions sur parents/specs acquis avec comparaisons pures
registrar/lineage, politique et exclusions de §8 ; aucun load/prepare/commit.

Layout observé sur métadonnées uniquement : fichiers home autorisés
spec.json, record.json, birth_qualification.json, usage.json, usage.json.tmp,
inflight.json ; dirs tasks/, results/, j01-lab-memory/. Dans tasks/ :
`<task_id>.json` et `<task_id>.json.tmp` ; dans results/ : `<task_id>.json` ; autres noms
refusés. task_id suit exactement Supervisor._TASK_ID, fullmatch ASCII
`[a-z0-9][a-z0-9_.-]{0,63}` ; le suffixe est ajouté hors de cet ID. Ce ne sont pas
des IDs run ou des paths fournis par un claim. Journal : activity.sqlite3 et ses seuls
-wal/-shm/-journal. Chaque entrée régulière single-link euid0600, aucun lien,
sous-répertoire inattendu ou type spécial. Garder FD/métadonnées, jamais lire
les contenus tasks/results/inflight, usage modifié après DONE D3 ou SQLite.
Un layout incomplet/absent est un fait, jamais une réparation automatique.

## 5. Preuve propre d'un foyer et filiation distincte

La classification d'un foyer repose sur ses propres preuves et une lignée
structurelle vérifiée. L'éligibilité à une future filiation exige en plus toute
la branche DECISION 3B sous racine actuelle ; elle n'est pas accordée par le statut.
Ainsi l'absence d'individuelle d'un frère ne contamine pas la branche du candidat,
mais l'absence/invalidité du fondateur est toujours un problème global de population.
Le fondateur n'a ni admission, ni qualification de naissance, ni statement de
naissance inventés : birth_proof et scientific_bindings propres sont NE avec
NOT_APPLICABLE_FOUNDER, non bloquant à lui seul. Son individuelle reste obligatoire.

Pour un descendant, birth_proof exige : exactement une opération COMMITTED de U
avec child ID/spec, H(record), admission et qualification canoniques exacts ; ligne
`/1` unique portant operation_sha256, issuer_id, envelope_id et H(enveloppe admission)
exacts ; preuves admission/qualification/statement et liens auteur/sujet/critères/
budgets/permissions/diff valides ; science prise en charge et recalculée selon 3B.
Un ancien COMMITTED peut fournir cette preuve même s'il n'est plus la dernière
tentative ; aucun fichier actuel n'est attribué à ses anciennes partitions globales.
Deux COMMITTED correspondants => contradiction, pas un choix arbitraire.
Une ligne `/0`, un home seul, admission seule ou FAILED_CONSUMED ne suffit pas.

Réutiliser trust.classify_envelope sur objets acquis, pas bundle/spend/path helpers.
Conserver integrity/authenticity/issuer_authorization/genuine_but_revoked et codes.
Pour la classification seulement, chaque preuve propre attendue doit être PASS
ou genuine_but_revoked exactement selon trust ; toute autre erreur empêche les
classes positives. Les preuves d'ancêtres exigées pour une filiation restent des
propriétés distinctes et ne sont jamais affirmées par cette tolérance de comptage.

### Priorité de classification, après acquisition réussie

| Priorité | Conditions | classification / counted |
|---|---|---|
| 1 | Contradiction indépendante démontrée d'identité, lignée, admission, COMMITTED, `/1`, science supportée, exclusion ou crypto ; preuve propre requise stablement absente hors exception individuelle | UNAUTHENTICATED / BLOCKING ; POPULATION_UNAUTHENTICATED |
| 2 | Candidat de l'unique opération ouverte avec foyer, après BEGIN D3, conditions OWN §6 toutes remplies | OWN_OPERATION / EXCLUDED_OWN |
| 3 | Prérequis manquant/non supporté sans contradiction démontrée, ou OWN partiel ne remplissant pas §6 | NE / NE ; CLASSIFICATION_NOT_EVALUATED |
| 4 | Identité/preuves propres établies, au moins une enveloppe propre genuine_but_revoked et toutes les autres PASS ou genuine ; individuelle descendante peut être stablement absente | SUSPENDED / INCLUDED ; EXECUTION_SUSPENDED signalé |
| 5 | Descendant, birth_proof intégralement PASS, seule individuelle stablement absente | AWAITING_INDIVIDUAL_ATTESTATION / INCLUDED |
| 6 | Fondateur : identité et individuelle PASS ; descendant : birth_proof et individuelle PASS ; aucune révocation | AUTHENTICATED / INCLUDED |

Le manque normal de COMMITTED et d'individuelle d'un candidat OWN potentiel n'est
pas une contradiction de priorité 1 : son origine est d'abord évaluée par §6.
Une preuve falsifiée de candidat, un foyer terminal présent ou un foyer hors
opération sans COMMITTED restent priorité 1. Un fondateur sans individuelle est
UNAUTHENTICATED (COMP-07) ; ce n'est pas un prérequis scientifique inconnu.
AWAITING n'est possible que pour cette absence prouvée, jamais pour bytes malformés,
mauvaise signature ou absence d'admission/qualification/statement. SUSPENDED gagne
sur AWAITING si une autre enveloppe propre est genuinely révoquée. Une erreur
SIGNATURE_INVALID supplémentaire interdit SUSPENDED. Source/profile PC2 non pris
en charge => NE bloquant, jamais AUTHENTICATED ou SUSPENDED par défaut.
Les contradictions prouvées restent FAIL même avec d'autres prérequis NE.

## 6. OWN_OPERATION, jamais une exception par ID seul

Sélectionner automatiquement la seule opération non terminale connue, pas un
argument caller. Plus d'une, ou log non résolu pouvant en cacher une =>
OPERATION_PENDING ; aucune exclusion OWN ou compte exact favorable.
Le foyer doit être celui de son child ID/spec, cette tentative et ce plan exact,
avec BEGIN D3 effectif non annulé, DONE D2 et `/1` admission exacts, preuves DECISION
courantes exigibles valides. Une terminaison (y compris externe vérifiée) interdit
OWN. Une révocation applicable ou incohérence ne bénéficie pas de cette exclusion.

Après DONE D3 : comparer exactement spec.json, record.json et
birth_qualification.json aux bytes attendus 3A ; usage et contenus runtime non lus.
Après BEGIN D3 sans DONE : les mêmes trois fichiers et usage initial `{runs:0}`
doivent être présents et égaux aux bytes attendus ; layout complet 3A requis.
Un foyer partiel avec fichiers présents égaux reste NE/OWN_HOME_INCOMPLETE : il
n'obtient ni exclusion de comptes utilisable ni droit de reprise. Préfixe/short write
divergent conserve les faits et refus 3A. Pas de contournement d'un cold-read gate.

Sans foyer : aucun OWN_OPERATION factice ; population avant naissance inclut tous
les foyers classifiables et ajoutera le candidat une fois dans chaque prédicat.
Après COMMITTED : l'enfant compte comme tout individu ; son ancienne opération ne
peut l'exclure. Ne pas soustraire un admission record orphelin comme s'il était un foyer.

## 7. Besoins et partitions figées

Pour CURRENT_OPEN seulement, construire indépendamment les besoins structurels
courants : DECISION de 3B, et, pour tous les autres foyers INCLUDED, individuelle
si présente et triple admission/qualification/statement s'ils sont descendants.
Les foyers de branche ne fournissent pas des copies POPULATION concurrentes de K.
OWN n'ajoute ni individuelle prématurée ni triple POPULATION du candidat.
Avant toute signature, construire aussi le graphe provisoire des K depuis TOUS
les records structurellement acquis : aucune omission parce qu'un foyer est
supposé invalide ou révoqué. L'absence individuelle et le candidat OWN structurel
potentiel sont identifiés par leurs preuves physiques, sans leur accorder encore
de statut. Ce graphe borne N avant crypto ; P/F structurels ne deviennent des
compteurs prouvés qu'après classification. Si leurs prérequis structurels sont
invalides, pas de borne P/F PASS et pas de preuve complète. Pour un corpus valide,
le graphe provisoire et la dérivation finale coïncident ; sinon aucun PASS sur le
sous-ensemble restant. Les limites policy/hard restent toujours appliquées.
K comprend kind/ID/spec/H(record), une K identique dédupliquée avec tous namespaces,
deux qualifications différentes du même sujet distinctes. Si un record est réutilisé
en DECISION et population, DECISION prend ce rôle unique ; toutes ses copies restent
requises, sans fusionner deux enveloppes différentes pour une même K.

Comparer ensemble des K, rôles et H(enveloppes) à PREPARED, sans compléter ou
réécrire la liste. Omission de preuve nécessaire => ATTESTATION_MISSING ; surplus
non expliqué => ATTESTATION_UNEXPECTED ; copie substituée => FROZEN_ITEM_DIVERGENT ;
rôle divergent => DECISION_ROLE_MISMATCH ou POPULATION_ROLE_MISMATCH.
Les doublons sont déjà refusés par le format lexical. Reclasser un foyer bloquant
pour éviter ses items n'est jamais une preuve de complétude.

COMP-08/COMP-10 : une individuelle stablement absente d'un descendant AWAITING hors
branche n'est pas un item dérivé, et sa K absente de PREPARED n'est pas MISSING.
S'il est requis comme parent/ancêtre, cette même absence empêche DECISION de passer.
Si PREPARED fige une individuelle maintenant absente, ne pas la supprimer : MISSING.
Si une individuelle hors branche est présente maintenant mais sa K manque de
PREPARED, alors que l'omission aurait pu provenir d'AWAITING au moment de D0 :
aucune absence historique n'est prouvée. Conserver la classification actuelle,
marquer frozen_completeness NE/HISTORICAL_POPULATION_ATTESTATION_UNAVAILABLE,
avec blocage, plutôt qu'inventer l'histoire ou réécrire les besoins figés.
Cette exception ne s'applique jamais aux triples descendants ou aux items DECISION.
La comparaison au snapshot courant n'authentifie pas le passé de PREPARED.

## 8. Exclusions et compteurs

Ensemble d'exclusion : tous les IDs de foyers inventoriés et identités de branche
validées, plus child de CURRENT_OPEN. Vérifier les reviewers/admitters par la règle
existante du préfixe 16 caractères, indépendamment des statuts (SUSPENDED/AWAITING
inclus). Pour les individuelles, conserver aussi le contrôle d'émetteur local 3B ;
ne pas le desserrer. Pas de sujet auto-émetteur accepté par un changement de rôle.
Un ID de foyer impossible à lier empêche l'agrégat global ; on ne l'écarte pas.

Counts exacts si inventaire complet et chaque foyer INCLUDED ou EXCLUDED_OWN.
Population P = nombre INCLUDED ; F = fondateurs INCLUDED ; children = descendants
INCLUDED dont parent_agent_id égale le parent candidat ; budget_totals = somme
exacte de chacun des six budgets alloués INCLUDED. Records/budgets contrôlés par
lineage ; int strict, pas bool/float, aucune unité arrondie ou budget runtime.
Sommes en entiers Python sans wrap ; univers borné §12.
Un foyer BLOCKING ou NE => complete FAIL ou NE et P/F/children/sommes exactes null ;
les FileFacts/IDs/raisons restent visibles, pas un reste disponible exploitable.

Plan_match pour CURRENT_OPEN : comparer H(records INCLUDED) triés avec population,
puis population_count/children_count/budget_totals du BirthPlan. Les quatre doivent
correspondre ; divergence => POPULATION_CHANGED, sans nouveau prepare. Statut
SUSPENDED ne retire pas son record ou son budget. G0 ne peut être relevé par le log.

## 9. Plafonds et portée temporelle

| Prédicat | Condition nécessaire, plus prérequis nommés |
|---|---|
| population_limit | P + 1 <= max_population |
| children_limit | children + 1 <= max_children_per_parent |
| generation_limit | génération du parent validé + 1 <= max_generation |
| colony_budget | chaque budget_total + budget candidat <= colony_budget |
| parent_budget | budget candidat <= parent pour les six composantes |
| permissions_and_diff | sous-ensemble autorisé parent/spec et diff exact |
| bundle_bound | N <= 4P - 3F + 3 <= 4*max_population - 4 <= 252, sous P <= max_population-1, F >=1 ; déduplications explicites |

Si P+1 dépasse la politique, population_limit FAIL suffit ; ne pas appliquer la
chaîne de majorations comme si son hypothèse P valide était établie. Le plafond
N policy/hard s'applique toujours, la borne P/F une fois ses hypothèses établies.
Nombre d'items déduit avant signature ; un dépassement est SOURCE_LIMIT avec nom,
zéro payload (§12), distinct d'un prédicat de capacité de naissance FAIL.
Égalité aux plafonds autorisée ; premier dépassement refusé. Codes registrar
GENERATION_LIMIT, POPULATION_LIMIT, CHILDREN_LIMIT, COLONY_BUDGET_EXCEEDED,
BUDGET_ESCALATION, PERMISSION_ESCALATION, UNDECLARED_MUTATION conservés en détails.
G0 reste génération 2, population 6, enfants 2, max_concurrent_runs 1 et budgets
existants. Concurrency_enforcement reste NE/NO_RUNTIME_OBSERVATION : pas de slots
ou environnement runtime lus ; cette limite de portée seule n'est pas un blocker.

HISTORICAL : tous plans/partitions/comptes/plafonds anciens restent NE avec
HISTORICAL_POPULATION_NOT_EVALUATED, non bloquant à lui seul. Ne pas comparer le
plan d'un COMMITTED ancien à la population actuelle moins son child pour conclure
POPULATION_CHANGED. Les preuves propres de ce foyer sont vérifiables aujourd'hui
sans rétablir les anciennes populations. Une opération terminale n'est jamais
rouverte. Sans CURRENT_OPEN, les ceilings de naissance sont NE et non bloquants ;
le scan peut observer la population actuelle sans affirmer qu'une naissance passe.

## 10. Fautes et exception des journaux faulty

Acquérir/project_fault_log strictement. Ressources et paths dérivés de la table
fermée external_evidence.TargetClaim : singleton path vide, OPERATION_LOG=child.log,
HOME_DIRECTORY=child, ADMISSION_ENTRY=child.json, ENVELOPE_ENTRY=child/nom fermé 3B,
QUARANTINE_DIRECTORY=vide ou op ou op/attempt ou op/terminal. HOME_ENTRY doit aussi
appartenir au layout §4 ; un path lexicalement permis mais hors mapping n'est jamais
ouvert, TARGET_BINDING_UNAVAILABLE bloque la propriété et les effets dépendants.
Pas de chemins absolus, traversal, alias ou valeur soumise reflétée dans les erreurs.

Les fautes ledger/ledger-dir et trust install/policy/history/dir restent globalement
bloquantes pour la preuve d'une nouvelle naissance, sans levée par lecture. Les
fautes propres d'une opération ouverte la bloquent ; une terminaison liée ne les
guérit pas mais peut lever sa seule contribution à OPERATION_PENDING. La faute
historique d'une opération terminée ne devient pas un veto global sur une autre
opération sans relation. Une faute de répertoire scope set-aside est observée en
restriction d'action ; si le foyer reste présent il est UNAUTHENTICATED et bloque.
Aucune action n'est autorisée par ce diagnostic, aucune faute n'est effacée.

Pour tout claim TERMINATED_EXTERNALLY lié à une faute OPERATION_LOG du même
lab/child/op/attempt, ne jamais lire les bytes de ce journal dans le mode 3C.
Inventorier/valider seulement son path, type/mode/FD et taille sans en parser le
contenu ; s'il est absent, absence stable estampillée. Les autres logs restent
strictement lus. Aucun nom fourni par l'opération ne permet de se marquer faulty.

Terminal linkage PASS exige claim schema /1 strict, digest observation embarquée
exact, fault_sha256 exact, même child/op/attempt, faute OPERATION_LOG précédente,
code OPERATOR_TERMINATED, forme/classe cohérente selon project_fault_log, et row
courante de U correspondante. Comparer status, operation_entries et entry complète
(`/1` issuer_id/envelope_id/envelope_sha256/operation_sha256) au finding historique.
Pour NO_OPERATION_ENTRY : zéro courant et zéro legacy. Pour OPERATION_ENTRY_PRESENT :
exactement un courant et entry identique. Ne pas comparer les SHA/total_entries du
ledger historique au SHA/total courant : d'autres opérations ont pu l'allonger.
Ces digests historiques restent des claims, pas une attestation de durabilité.

/0 externe (digest sans observation), substitution, conflit ou changement du
finding => terminal linkage NE ou FAIL avec blocage ; le journal faulty reste non
lu et l'état d'ouverture global non prouvé. Ne pas prétendre OPERATION_PENDING
levé. Après linkage PASS : classification terminale FAILED_CONSUMED ou ABANDONED
établie comme fait de terminaison seulement ; pas de BirthPlan inventé, pas de
D2/D3 ou COMMITTED reconstruit. Child ID reste OPERATION_LOG_FAULTY. Home terminal
présent => UNAUTHENTICATED, même si les bytes paraissent complets.

Une faute sans terminaison liée valide ne permet pas d'ignorer un log corrompu.
Hors claim d'exception strictement ciblé ci-dessus, corruption ou torn tail non
acquitté => source fondamentale invalide et payload effacé. Les journaux externes
non lus sont comptés dans la couverture séparément ; pas de fausse exhaustivité
PREPARED sur leurs anciennes tentatives. Cette exception ne supprime aucune trace.

## 11. Quarantaine et correspondances d'action

admission-quarantine/ est facultatif si aucun claim d'action ne le nécessite ;
absence doit être stable, sinon racine requise privée. Inventorier noms op hex64,
puis attempt décimal canonique positif (au plus 128 chiffres, lié à une tentative
connue) ou terminal. Rien d'autre, pas de lien ; chaque destination doit être
liée à un claim d'action connu, sinon ACTION_EVIDENCE_NOT_EVALUATED bloquant.
Acquérir seulement identité attendue et métadonnées récursives du layout §4,
sous budget privé ; pas de lecture de journaux SQLite ou contenus runtime.

| Claim | Observation source/destination | Fait |
|---|---|---|
| BEGIN sans DONE | exactement une localisation du foyer, identité liée si disponible | action_location déterminée, action_completion NE bloquant ; aucune action exécutée |
| DONE | source absente stable, destination présente et liée | action_location PASS ; comparer identité selon type ci-dessous |
| DONE mensonger | source présente ou destination absente/divergente | ACTION_LOCATION_DIVERGENT FAIL ; source présente reste population |
| Source et destination toutes deux présentes ou absentes | ambiguïté sans preuve de renommage | FAIL, aucun foyer ignoré |

Pour QUARANTINE (partiel non terminal), les fichiers identité présents doivent
égaler les bytes attendus (pas de préfixe toléré). Pour SET_ASIDE terminal, identité
peut être absente, égale ou préfixe attendu, selon P1 §8.2 ; aucun autre contenu.
Si le log faulty ne donne aucun BirthPlan acquis, ne pas le fabriquer depuis le
home ou l'observation ledger : identity_binding NE/ACTION_EVIDENCE_NOT_EVALUATED
bloquant, même si le lieu et le fait terminal sont établis.

Layout/location/identity PASS ne certifie ni fsync passé ni validité du journal
SQLite ayant précédé la quarantaine. quarantine_journal_semantics reste NE, limite
non bloquante pour le seul lieu actuel, jamais permission de quarantaine/reprise.
Une identité/lien d'action requis non disponible reste bloquant. Aucune inspection
SQLite sur copie, écriture temporaire, rename, suppression ou fsync dans le scan.

## 12. Capacités, permissions et invalidation

| Ressource | Plafond ferme |
|---|---|
| Noms logs / tentatives lisibles / union U ledger | 256 / 256 / 256, dépassement avant ledger |
| Bytes logs / un log | 32 MiB / formats.MAX_LOG ; parser/64 lignes et reserve inchangés |
| Ledger | 16 MiB / 16384 entrées, une inspection de lot |
| Foyers individuals | 65 noms (capacité 64 + éventuel own, pas une permission de population) |
| Noeuds d'une lignée | 9, visited-set ; contraintes policy plus strictes conservées |
| Record/spec / enveloppe/statement | 64 KiB / 16 KiB |
| Bytes privés de contenu | 32 MiB dédupliqués, partagés avec 3A/3B |
| Entrées privées inventoriées | 8192, racines liées, dossiers et feuilles metadata compris |
| Checkout | 32 MiB cumulés, 16 MiB/fichier, 4096 fichiers, 8192 entrées comme 3B |
| FD retenus | 4096 globalement, racines/ancêtres/fichiers/caches/ledger compris |
| Fault log / trust history / installed policy | 4096*16384 bytes / 4096*1024 bytes / 65536 bytes, formats existants |

Les contenus externes faults/trust/logs gardent leurs budgets dédiés ; pas de
nouveau budget privé par phase. Compter une entrée privée par (ressource racine,
path relatif) à sa première énumération, root incluse ; aliases NOFOLLOW refusés.
Pour champs opaques de layout, aucune lecture de contenu ni limite de taille de
record appliquée ; leur nombre/FD et métadonnées sont bornés. Trop de fichiers
runtime valides reste SOURCE_LIMIT, pas de sous-ensemble silencieux.

Bound item d'opération : min(252, 4*policy.max_population-4), puis §9 avec P/F.
Toute taille/count connu avant crypto l'arrête avant première signature. Si une
précondition nécessaire à la borne P/F est NE, vérifier la borne universelle mais
ne pas annoncer la borne plus serrée PASS. Pas de contournement par découpage des
opérations en lots ou augmentation implicite. OS plus limité => SOURCE_UNAVAILABLE.

Permissions privées euid0700/euid0600 single-link, réguliers, NOFOLLOW/nonblocking ;
checkout règles distinctes 3B (pas group/world writable). Revalider dev/inode/mode/
uid/nlink/size/mtime/ctime sur FD et path, listings/absences avant retour ; absences
uniquement ENOENT d'ouverture sous parent acquis stable. ENOENT read/stat n'est pas
une absence. CONFIG_INVALID, trust/politique fondamentale invalide, log/ledger
corrompu hors exception §10, acquisition, limite, modification ou close/unlock
raté => BLOCKED, homes/opérations/items/claims/stamps vides, ledger bytes/counts/digests
null, coverage NE, tous agrégats NE. Seuls codes fixes et noms de limite restent.
Un JSON stable divergent de matériel privé reste un FileFact local et empêche les
dépendants de passer ; un fichier trop grand est une limite globale, pas ce cas.

## 13. Science, limites et checklist de clôture

Profils/artefacts et digests exactement 3B §8–9, sans copie divergente de la crypto,
ni source arbitraire, import de code soumis, réseau ou campagne. Référencer R8/C9
ne prouve ni signature historique ni fraîcheur/campagne exécutée par l'émetteur.
PC2/p1 reste SCIENTIFIC_PROFILE_UNSUPPORTED, NE bloquant, sans enlever p1 de g0.
Une nouvelle correspondance PC2 exige son amendement contractuel avant code.

Checklist source de l'étape 3 : capacité et matrice 3A, 3B et 3C implémentées et
revues sur leurs arbres exacts ; acquisition exhaustive bornée ; D1/D2/D3, proofs
DECISION/POPULATION, exclusions, comptes/plafonds et correspondances explicitement
évaluées dans le corpus d'acceptation ; aucun manque bloquant rebaptisé PASS.
La fermeture administrative d'une capacité ne prouve pas cette checklist globale,
ni P5/P6, ni installation, ni contrôleur durable. Une limite PC2 ou d'action NE
bloquante doit être citée ; l'étape 3 ne se clôture pas automatiquement avec la PR.

Les limites P1 §13 persistent : compte opérateur, verrous advisory, suppression
hostile de foyers/rollback, caches matériels, pas de compteur fiable, temps/versions
non attestés, contournement du contrôleur par appels directs, aucune exécution
suspendue effectivement par ce code. Aucun accès boot_id pour cold-read runtime.

## 14. Gates et codes

Codes existants de 3A/3B/trust/registrar conservés en détails sans les transformer
en verdict de naissance. Nouveaux codes diagnostiques : SOURCE_NAMESPACE_INVALID,
CLASSIFICATION_NOT_EVALUATED, OWN_HOME_INCOMPLETE, POPULATION_ROLE_MISMATCH,
HISTORICAL_POPULATION_ATTESTATION_UNAVAILABLE, HISTORICAL_POPULATION_NOT_EVALUATED,
NO_CURRENT_OPEN_OPERATION, NO_RUNTIME_OBSERVATION, TARGET_BINDING_UNAVAILABLE,
NOT_APPLICABLE_FOUNDER,
EXTERNAL_TERMINATION_UNPROVEN, EXTERNAL_TERMINATION_DIVERGENT,
ACTION_LOCATION_DIVERGENT. Codes P1 FILIATION_NOT_ATTESTED/FILIATION_SUSPENDED et
POPULATION_UNAUTHENTICATED restent des raisons de refus de preuve, pas des actions.
FILIATION_NOT_ATTESTED pour un AWAITING requis en branche ; FILIATION_SUSPENDED pour
une branche qui inclut un SUSPENDED établi. Aucune transition FAILED_CONSUMED écrite.

La matrice jointe est SPECIFICATION_ONLY_NOT_EXECUTED, pas un compte de tests verts.
Prochaine porte : revue indépendante du contrat/matrice finals, corrections,
CI exacte check-runs filter=all ET workflows tous événements/statuts/pagination,
threads/ruleset, pins/hashes et composition avant fusion gardée expected_head_sha.
Puis arbre main conforme et CI propre complète avant clôture documentaire.
Les petites PR de code auront leurs propres tests et revues ; pas d'API publique
positive avant preuve complète. Aucun feu vert de code ou merge donné par ce texte.
Pas de code produit, writers/installation/recover/restore/naissance, contrôleur,
P5/P6, VPS/runtime/systemd/PPL/FIN/epoch/production/TESTNET/LIVE/secret/Replay ou
Diagnostic automatique. #286 ACTIVE et accepted=false permanents.
