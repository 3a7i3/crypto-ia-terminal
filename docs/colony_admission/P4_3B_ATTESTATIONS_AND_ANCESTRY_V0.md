# P4 / 3B — Attestations et ascendance, contrat v0

**CONTRACT_FOR_REVIEW / SOURCE_ONLY / LAB_ONLY / NO_IMPLEMENTATION.**
Périmètre validé par Mathieu le 2026-10-25 après présentation du plan #505.
Baseline `main@33144194a1ec85e6cff96e3bb9ae6fda5db972f8`, tree
`374e0a6f0f2341410909ec41d7d3439c28eac20d` ; plan initial HEAD
`08569782f8319a055f9f65e2fa490cc1f4555791`.

Normes : [P1](ADMISSION_CONTRACT.md) §3–5, §6, §11–13,
[scénarios P1](SCENARIOS_A0.json), [3A](P4_3A_PHYSICAL_EVIDENCE_JOIN_V0.md),
[plan validé](P4_3B_PLAN_AND_REUSE_V0.md),
[matrice 3B](P4_3B_ATTESTATIONS_AND_ANCESTRY_CASES_V0.json).
P1 reste prioritaire. Pins SHA256 : `e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd`
et `4e518bfec6faaa582c2c42633d80e989b8204708b554f74b0eb1bbee6eaa59a1`.
Aucun format/pin existant ou source qualifiée n'est modifié.

## 1. Question, couverture et absence d'autorité

Pour chaque dernière opération PREPARED d'un candidat, les preuves exactes de la
décision et du chemin parent→fondateur sont-elles disponibles et cohérentes avec
les objets figés, les signatures sous confiance actuelle et les sources scientifiques
prises en charge ? Les anciennes tentatives gardent leur diagnostic D1 de 3A,
mais leur attestation ne reçoit pas de PASS depuis les fichiers d'une autre tentative.

Chaque résultat impose `accepted=false`, non modifiable par l'appelant. Les champs
globaux `authorization`, `completeness`, `population`, `ceilings`, `durability`,
`rotation`, `recovery`, `source_revision_provenance` restent NOT_EVALUATED.
`authorization` global concerne la décision opérationnelle ;
`issuer_authorization` d'un item désigne seulement les droits vérifiés par trust.
Pas de champ `qualified=true`, `can_resume`, `can_parent` ou `admitted` positif.
La vérification n'écrit ni statut SUSPENDED, ni événement terminal, ni STOP.

La complétude locale vérifie une partie dérivée de la décision, pas tout le lab.
Les items POPULATION et l'exclusion d'un émetteur lié à un individu hors branche
nécessitent 3C. Ni leur liste figée ni un parent signé ne prouvent cet inventaire.
Une couverture de branche complète ne ferme donc pas l'étape 3.

## 2. API et objets immuables proposés

Nouvelle API : `AttestationObserver(config).scan_attestations()`, sans argument de
méthode. Pas de remplacement de FileObserver ni de changement de ses trois méthodes.
`AttestationConfig` contient :

| Champ | Contrat |
|---|---|
| `observer` | ObserverConfig existant exact, chemins explicites, lab_id, root_pin et minimum_root_version opérateur |
| `registrar_policy_bytes` | bytes détachés d'une politique JSON stricte ; défaut None |
| `registrar_policy_pin` | digest canonique SHA256 explicite ; défaut None |

Les deux derniers sont tous deux None (g0 lu au chemin fixe checkout
`docs/colony_registrar/POLICY_G0.json`, pin de registrar.POLICY_SHA256) ou tous deux
fournis. `registrar.check_policy` valide la politique et son pin avant usage.
Les bytes fournis ne sont jamais des chemins et ne peuvent changer après création.
Pas de confiance/politique requise tirée du seul PREPARED ; son policy_sha256 doit
égaler la politique opérateur choisie, sinon POLICY_CONTEXT_MISMATCH.

La projection pure consomme uniquement des bytes/objets détachés et snapshots bornés.
Les objets publics n'exposent aucun dict/list mutable de trust, record ou enveloppe.
Identités triées par (child_agent_id, attempt, operation_sha256), items par clé K.
Les chemins publics sont relatifs à des ressources nommées ; aucune valeur soumise
ou contenu de fichier n'est inclus dans un message d'erreur.

Le résultat comporte : status OBSERVED ou BLOCKED ; blockers dédupliqués ; stamps
3A et checkout ; limites atteintes ; couverture des logs/ledger ; et par opération :
identité, latest, source_state, branche ordonnée, besoins locaux, faits d'items,
faits de statements et de sources scientifiques. Chaque item expose K, rôles,
namespace de stockage, record_sha256/envelope_sha256 attendus et observés,
presence, integrity/authenticity/issuer_authorization (PASS/FAIL/NOT_EVALUATED),
genuine_but_revoked, consommation, codes trust et codes de comparaison.
Chaque besoin garde la distinction ABSENT, UNAVAILABLE, PRESENT_MATCH, DIVERGENT.
genuine_but_revoked vaut NOT_EVALUATED tant que classify_envelope n'a pas pu être
appelé ; une preuve absente n'est pas réputée « non révoquée ».

Pas de verdict agrégé qui rebaptise ces propriétés en admission :
`decision_partition`, `branch_structure`, `branch_attestations`, `statements`,
`scientific_bindings`, `known_identity_exclusions` valent PASS/FAIL/NOT_EVALUATED ;
leur définition et leurs prérequis sont ceux des sections suivantes.
`population_partition` et `global_identity_exclusions` sont toujours NOT_EVALUATED.

## 3. Acquisition unique et invalidation

Réutiliser les mécanismes 3A, éventuellement factorisés sans changer les anciens
résultats : propriétaire unique, L1 existant non bloquant, inventaire complet des
logs, parser strict et fragments ACK/CR opaques, liens filename/lab/attempt/digest,
ensemble de toutes les opérations, puis une seule ouverture fraîche du ledger
O_RDONLY à offset0 et `trust.inspect_operations_fd` sous L2 partagé.
L1 précède L2 ; pas de nouvelle acquisition imbriquée ni appel scan puis relecture.
Conserver les blockers des faults, terminaisons non évaluées, racines et confiance.
Quand politique/config et inventaire figé permettent déjà de détecter une limite
d'items, refuser avant ouverture ledger ; toute limite de besoins dérivés découverte
plus tard refuse avant signature. Une politique de config invalide connue au départ
ne doit déclencher aucun accès lab ou ledger.

Ensuite découvrir les branches à partir des records acquis, compiler les chemins
requis et lire une fois chaque chemin, partagé entre toutes les opérations/ancêtres.
Les branches n'ajoutent aucun ID ledger non inventorié : une opération COMMITTED
d'ancêtre absente de l'inventaire ne peut pas être devinée ou lue dans un second lot.
Conserver FD, checks de chemin et inventaires jusqu'à verification et closes réussis.
Revalider les listes de répertoires visités et absences, métadonnées et descripteurs.
Le résultat n'est publié qu'après sortie réussie du contexte d'acquisition.

Même frontière privée que 3A : dirs leaf owner0700 ; fichiers owner0600, réguliers,
un seul lien ; composants NOFOLLOW, nonblocking, root manquante indisponible.
Une absence n'existe que sous parent acquis, listing stable et absence nofollow
confirmée. Seul ENOENT de l'open du composant permet cette observation. ENOENT de
read/stat, permission refusée, FIFO, lien, remplacement ou close raté sont des échecs.

CONFIG_INVALID, politique invalide, source fondamentale corrompue, acquisition,
limite, instabilité ou close en erreur => BLOCKED et zéro payload utilisable :
opérations/branches/items/stamps vides, ledger bytes/counts/digests null, tous
les agrégats NOT_EVALUATED. Seuls codes fixes et noms de limites restent présents.
JSON invalide d'un artefact acquis stable => DIVERGENT local, raw hash conservé ;
ne jamais sauver un préfixe ou effectuer une correction. Une dépendance invalide
empêche le PASS de ses dépendants, sans inventer leurs propriétés.

Pas de création de lock/fichier, écriture, fsync, chmod, renommage, suppression,
ouverture SQLite, réseau, subprocess, lecture d'environnement, exécution de campagne
ou chargement de code depuis le checkout soumis. Les lectures peuvent modifier atime.
Verrous advisory, compromission opérateur, caches matériels, restauration hostile
des timestamps et rollback hors modèle restent non prouvés comme en 3A/P1 §13.

## 4. Construction de branche et validation sémantique

Partir du parent nommé par l'opération figée. Lire `individuals/<id>/record.json`
et `spec.json`, puis les parents déclarés, avec visited-set et bornes §10. Arrêter
au premier fondateur déclaré, puis valider de ce fondateur vers le parent.
Chaque id est hex64, doit égaler le répertoire ; comparer le record du parent
à `birth_plan.parent` par identité canonique complète.
Réutiliser `lineage.verify_record(record,spec,parent,parent_spec)` et identité A1.
Vérifier rôle, génération, founder/lineage ids, parent id/spec, diff, permissions
et contraintes locales déjà imposées par ces validateurs. Pas de `Supervisor.load`.
Pour chaque descendant, valider sa qualification de naissance sur le parent
avec `lineage.check_qualification`, critères admissibles de la politique choisie,
et exclusions enfant candidat + tous les individus de cette branche.

Pour les admissions d'ancêtres, appliquer les champs fermés ADMISSION_FIELDS et
les règles pures de registrar `_check_admission` : ids enfant/parent, politique,
admitter_kind, absence de self-admission, budget/permissions/diff et digest de
qualification égaux aux record et qualification acquis. Ne pas appeler cette
méthode via une instance lab : adapter ses comparaisons pures dans colony_admission.
Les règles ne sont pas renforcées silencieusement ni présentées comme registrar.prepare.
La même cohérence lie l'admission candidate à birth_plan et au parent vérifié.
Valider aussi le record et child_spec figés du candidat avec verify_record et son
parent vérifié ; lier qualification présentée, budget/permissions/diff et admission.
Refuser une identité candidate égale à celle d'un noeud de branche. La distinction
avec tous les autres individus du lab et les comptes de plafonds reste 3C.

Fondateur : pas d'admission de naissance ni de qualification de naissance inventées.
Chaque noeud parent/ancêtre requiert son enveloppe individuelle ; l'enfant candidat
ne la requiert pas à D2. L'absence est un manque de preuve, pas un statut global
AWAITING_INDIVIDUAL_ATTESTATION. Le sens de ce statut complet appartient à 3C.

Un cycle, une branche incomplète, une substitution, un record/spec invalide, une
qualification ou admission incohérente empêche `branch_structure=PASS`.
Un préfixe reconnu ne reçoit jamais le statut de branche complète. Avec politique
plus restrictive, vérifier génération candidate <= max_generation séparément et
rapporter uniquement ce prédicat local, pas `ceilings=PASS`.

## 5. Dérivation locale et comparaison à PREPARED

Clé K = (kind, subject.agent_id, subject.agent_spec_id, record_sha256).
Dériver indépendamment les besoins suivants depuis les objets vérifiés :

1. admission candidate ; qualification présentée du parent ; son statement ;
2. attestation individuelle de chaque noeud de la branche ;
3. pour chaque descendant de la branche, son admission déjà consommée, sa
   qualification de naissance (sujet = son parent) et son statement.

Un record identique réutilisé à plusieurs endroits donne une seule K avec liste
de namespaces d'origine ; deux records différents du même sujet restent deux K.
Toutes les copies acquises doivent correspondre aux mêmes digests figés. Des
enveloppes différentes pour la même K ne sont pas coalescées : c'est une divergence
de preuve d'opération, même si les deux signatures sont valides.
Les besoins 1 sont liés à op.presented et birth_plan ; tous les autres à leurs
records acquis. La forme, l'ordre et les doublons des items sont déjà contrôlés
par formats.validate_operation ; l'absence sémantique et les rôles sont vérifiés ici.

Comparer l'ensemble dérivé exactement aux items DECISION figés et leurs hashes
d'enveloppes. Missing/duplicated/unexpected => ATTESTATION_MISSING/DUPLICATED/UNEXPECTED.
La même K nécessaire trouvée sous POPULATION => DECISION_ROLE_MISMATCH, pas une
source de remplacement. Une K ne peut être à la fois DECISION et POPULATION.
Ne modifier ni op.items, ni son hash, ni required_attestations historique.
La partie POPULATION n'est pas lue depuis ses seuls chemins déclarés : elle reste
non évaluée, sans supposer que toute entrée hors branche est authentifiée.
`decision_partition=PASS` exige branche structurelle complète et égalité d'ensemble.
Les signatures ne sont pas un prérequis de cette seule égalité structurelle.

En l'absence de PREPARED, produire aucune liste inventée. Pour une opération avant
D2, les records du BirthPlan sont visibles mais une enveloppe non stockée reste
NOT_EVALUATED avec EVIDENCE_NOT_STORED ; le hash figé ne remplace pas ses bytes.
Cette absence attendue n'est ni corruption du journal, ni PASS d'attestation.
Après D2 achevé, tout fichier requis manquant empêche la preuve complète.
Les anciennes tentatives sont marquées HISTORICAL_ATTESTATIONS_NOT_EVALUATED,
même si des paths actuels contiennent des bytes de forme plausible.

## 6. Mapping de stockage, encodages et consommation

Tous les paths suivants sont dérivés d'ids/digests validés, jamais d'une chaîne
libre de l'enveloppe ou du statement. Soit x le descendant propriétaire du matériel,
q sa qualification de naissance concernant son parent et a son admission :

| Objet | Chemin relatif lab |
|---|---|
| Record individuel/spec | `individuals/<x>/record.json`, `individuals/<x>/spec.json` |
| Qualification de naissance | `individuals/<x>/birth_qualification.json` |
| Admission | `registrar-admissions/<x>.json` |
| Enveloppe individuelle | `admission-envelopes/<x>/individual-<H(record)>.envelope.json` |
| Enveloppe admission | `admission-envelopes/<x>/admission-<H(a)>.envelope.json` |
| Enveloppe qualification | `admission-envelopes/<x>/birth-qualification-<H(q)>.envelope.json` |
| Statement et son enveloppe | `admission-envelopes/<x>/statement-<H(q)>.json`, `statement-<H(q)>.envelope.json` |

Pour les trois éléments présentés, x est l'enfant candidat et q vient du BirthPlan ;
la qualification et le statement gardent le parent comme sujet, selon 3A-D05.
Le record du statement a son propre H(statement), différent du digest de q dans
le nom du fichier. Le fondateur n'utilise que les chemins individuels.

H est SHA256 de l'encodage canonique déjà utilisé par A1/trust/formats, sans
confondre `record_hash` individuel (calcul sans ce champ) et H(record complet).
Les artefacts privés sont lus en JSON strict sans doublons/non-finis et comparés
canoniquement comme 3A ; aucune exigence de JSON compact sur des bytes D3 indentés.
Les stamps contiennent aussi SHA256 des bytes bruts, distinct de H.

Pour chaque ancêtre descendant : trouver exactement une opération COMMITTED
correspondant à id/spec, H(record), admission et qualification de naissance.
La ligne /1 de cette opération doit porter issuer_id, envelope_id et H(enveloppe)
exacts de l'admission acquise, avec operation_sha256 exact. /0, ambiguïté, absence,
autre opération, conflit ou terminal FAILED_CONSUMED ne suffisent pas.
Réutiliser les observations FD 3A ; ne pas appeler verify_consumed(path).

Consommation candidate : NOT_CONSUMED ou CONSUMED_BY_THIS_OPERATION sont des faits
séparés selon état/log/D1. CONSUMED_BY_OTHER_OPERATION ou conflit bloque. Aucun de
ces états n'est une acceptation. La couverture historique et le refus des lignes
non rapprochées restent ceux de 3A. Une opération terminale peut avoir des faits
cryptographiques observables ; ils ne la rouvrent jamais.

## 7. Trust et agrégats de branche

Lire racine/policy/history hors lab une fois ; _external/check_root existants
valident le pin fourni par l'opérateur, lab_id, LAB_TEST et plancher effectif
max(config.minimum_root_version, installed.minimum_version). L'historique ne
devient pas une preuve indépendante d'installation ou de monotonicité.
Conserver historical_root_* à titre historique, jamais pour ignorer une révocation.

Par K, vérifier l'enveloppe exacte et le record attendu avec trust.verify_envelope
et classify_envelope sur objets acquis, sous la racine courante. Conserver leurs
codes et propriétés ; mapper authorization de trust vers issuer_authorization.
Ne pas réimplémenter Ed25519, la forme d'enveloppe, scopes, author, purpose ou
validation des clés. Pas d'appel check_bundle path-based, _spend, consume,
make_envelope, verify_bundle, Registrar.prepare/commit/birth ou Supervisor.
L'adaptation locale de complétude ne duplique pas la cryptographie.

Une clé RETIRED peut vérifier une signature déclarée avant son retrait ; une
version future ou pré-introduction est refusée. Genuine-but-revoked n'est vrai
que selon classify_envelope : intégrité/autorisation PASS et seuls codes KEY_REVOKED
et/ou ENVELOPE_REVOKED. SIGNATURE_INVALID supplémentaire interdit cette classe.
Toute révocation de décision bloque branch_attestations, sans admission ni écriture.
Une révocation hors branche ne donne pas de statut population dans cette tranche.

`known_identity_exclusions` teste reviewers/admitters contre candidat et branche
validés, avec la règle des préfixes 16 caractères déjà dans lineage/registrar.
Un PASS local ne couvre pas les autres individus inconnus (3C).
`branch_attestations=PASS` exige decision_partition, branch_structure,
known_identity_exclusions et tous les items attendus avec trois propriétés trust
PASS, tous les statements cohérents, scientific_bindings PASS et consommations
d'ancêtres liées. Sinon FAIL si contradiction prouvée, NOT_EVALUATED si manque de
prérequis sans contradiction. Pas de « toutes les signatures valides donc PASS ».

## 8. Statement fermé et cohérence scientifique

Champs exacts : STATEMENT_FIELDS de physical_evidence, soit statement_schema,
subject_agent_id, subject_agent_spec_id, issuer_kind, issuer_id, issuer_root_version,
qualification_record_sha256, historical_record_path, historical_record_sha256,
evidence, criteria_sha256, subject_code_sha256, evaluator_code_sha256,
verified_at_source_sha, scope, campaign_replayed, campaign_evidence_sha256,
historical_signature_claimed. Aucun champ supplémentaire, doublon ou coercition.
Hashes hex64 lowercase ; source SHA git hex40 lowercase ; root version int strict
1..trust.MAX_VERSION ; booleans littéraux (pas 0/1). evidence est une liste non vide
triée par path, sans doublon, d'objets exactement {path, sha256}.

Sujet du statement = sujet de q ; qualification_record_sha256=H(q). Auteur
issuer_kind/id = reviewer de q = émetteur de ses deux enveloppes. Les deux
root_version d'enveloppe égalent issuer_root_version. Critères et hashes de code
égalent q et les sources prises en charge recalculées, pas seulement un hex valide.
verified_at_source_sha reste un identifiant historique déclaré : sa grammaire
est vérifiée, pas sa preuve passée d'appartenance à main. On ne réécrit pas ce
champ et source_revision_provenance reste NOT_EVALUATED ; les bytes courants
recalculés sont la preuve de correspondance actuelle de code, pas d'un passé Git.

PRESENT_ATTESTATION_OF_EXISTING_EVIDENCE : historical_record_path et digest non
null, campaign_replayed exactement false, campaign_evidence_sha256 null.
Lire le record historique seulement via le profil §9 ; en comparer id/spec,
state/scope, critères/évidence/hashes de code à q. Seuls reviewer_kind/id sont
remplacés par l'émetteur présent ; ne pas exiger H(q)=H(record historique).
historical_signature_claimed est toujours exactement false. Pas d'issuer artificiel
colony-review-481-r8 ni d'enveloppe historique générés pour rendre R8 admissible.

FRESH_CAMPAIGN : historiques tous deux null, campaign_replayed exactement true,
campaign_evidence_sha256 hex64 et égal à q.evidence_sha256 pour le profil mono-
évidence §9. Ce booléen est une déclaration d'émetteur à vérifier sur l'artefact
existant, jamais une instruction de lancement. L'absence d'un profil source pour
une campagne/famille bloque scientific_bindings ; aucun fallback déclaratif.
Toute incohérence de forme/binding connu => STATEMENT_INVALID ; source manquante
ou profil non supporté reste un manque explicite, jamais un statement validé.

## 9. Sources scientifiques : profils fermés et limite actuelle

### 9.1 Profil `sentinel-r8-c9`

Critère exact `22528f1629db5d565f54137e11e99f670c68152eb3127cbafabe5f1072ca990a` :
`docs/colony_lab/SENTINEL_QUALIFICATION_CRITERIA_R8.json` (SHA256 bytes).
Évidence exacte `docs/colony_lab/evidence/C9_sentinel_evidence.json`, SHA256 bytes
`bc2f37df6bf7ab8138d326862906431154c07b298fb4b482db4fc6a0910f71cf`.
Historique autorisé, uniquement pour PRESENT :
`docs/colony_lab/SENTINEL_QUALIFICATION_RECORD_R8.json`, raw digest dans la matrice.
La liste evidence du statement est exactement le singleton C9/digest ; aucune
lecture additionnelle déduite du contenu C9. PRESENT et FRESH peuvent référencer
ce même corpus existant si leurs autres prérequis sont remplis ; le diagnostic
ne certifie pas quand la campagne a été exécutée ou quand l'issuer l'a revue.

Parser ces JSON sans doublons/non-finis, sans changer leurs bytes. Comparer q à
C9.subject.agent_id/agent_spec_id, critères r8/CURRENT, scope SIMULATED_DETERMINISTIC,
subject_code_sha256 et evaluator_code_sha256 ; proposed_state doit être
PROPOSED_QUALIFIED_SIMULATED, failure_reasons/code_irregular vides,
deterministic_across_fresh_labs=true, golden_subject_code_matches=true,
evaluator_runtime.source_only=true. Les artefacts C9/critères sont épinglés par
bytes complets ; on n'affirme pas que ces seules propriétés remplacent tous les
prédicats de la campagne. Ni replay, ni nouvelle qualification, ni preuve non-root.

Hash de code : même algorithme que qualification._hash_files, sur chemins relatifs
POSIX uniques triés : SHA256(concat(path UTF8 + NUL + SHA256(raw).digest())).
Subject roots exacts : colony_lab/__init__.py, colony_lab/workers/__init__.py,
colony_lab/workers/sentinel.py, governance_tower/ (récursif),
observability/__init__.py, observability/event_center_contract.py,
observability/runtime_service_contract.py, observability/storage_contract.py.
Evaluator roots : colony_lab/ et sentinel_activity/ récursifs, moins l'ensemble
des fichiers subject. Ne pas hasher seulement *.py : tous les fichiers réguliers
hors caches éligibles comptent, dont fixtures. Pas d'import du code soumis.
Référence actuelle : subject `2c926421416731dc629915067bcea472729e6785ec8dcb6e28f15ae7b41e4ec8`,
evaluator `41b78971184809652dd1190dded49ab27d58c35c8a995351a47bf0f85756faa4`.
Le résultat courant doit égaler q, C9 et les pins du profil ; dérive => SCIENTIFIC_DIVERGENCE.

Parcours équivalent à supervisor.walk_code : liens/types non réguliers refusés ;
__pycache__ ne contient que fichiers réguliers *.pyc directement dans ce dossier,
ignorés sans lire leur contenu ; sous-dossier, lien ou autre entrée => SOURCE_CODE_IRREGULAR.
Racine attendue absente => source indisponible (pas un hash d'ensemble vide).
Interdire avant toute lecture tout composant dont le nom lowercase commence par
`.env`, contient `secret`, `credential` ou `private_key`, égale `id_rsa`, `id_dsa`,
`id_ecdsa`, `id_ed25519`, ou finit par `.pem`, `.key`, `.p12` ou `.pfx` ; interdire
aussi chemins absolus, composants vides, `.` et `..`. Si une telle entrée existe dans la fermeture,
refuser la fermeture entière, ne pas la sauter pour produire un hash partiel.

### 9.2 PC2 et autres profils

P1 g0 admet aussi les critères pilot p1 ; cela ne fournit pas une correspondance
automatique vers les champs qualification/0. PC2 porte à la fois subject_code_sha256
(Sentinel), pilot_code_sha256 et sentinel_evaluator_code_sha256 ; aucun record
de qualification externe PC2 standard n'est fourni par ce baseline.
Ce contrat n'invente pas lequel remplacerait subject_code_sha256 de q.
Donc critères pilot p1 ou famille inconnue => SCIENTIFIC_PROFILE_UNSUPPORTED,
scientific_bindings et branch_attestations NOT_EVALUATED, jamais PASS ; les faits
trust et structure déjà prouvés restent distincts. Cette capacité limitée est
explicite et ne retire pas p1 de g0. L'ajout d'un profil qualifiant PC2 exige un
amendement contractuel définissant ses bindings avant son code, dans le même scope
SOURCE_ONLY ; une modification de g0 ou des sources qualifiées n'est pas implicite.
Le présent contrat ne revendique donc pas la complétude 3B pour toutes les familles.

### 9.3 Acquisition checkout

Le checkout_root est celui de config, distinct des racines privées. Traverser
composants NOFOLLOW. Sous la racine liée, dirs et fichiers appartiennent à euid et
n'ont aucun bit group/world writable ; fichiers réguliers single-link O_RDONLY.
Pas d'exigence 0600/0700 sur le checkout. Fichiers/répertoires non lisibles =>
SOURCE_UNAVAILABLE. Inventorier les fermetures avant/après et vérifier dev/inode/
mode/uid/nlink/size/mtime/ctime sur FD et path avant restitution, comme le lab.
Un path connu acquis deux fois par rôle utilise les mêmes bytes. Ne pas modifier
les permissions pour rendre un corpus lisible. Aucun git/subprocess ou fetch pour
résoudre verified_at_source_sha ; les limites de provenance sont celles de §8.

## 10. Bornes avant travail coûteux

| Ressource | Borne |
|---|---|
| Logs / opérations toutes tentatives | 256 / 256, dépassement avant ledger |
| Bytes logs / un log | 32 MiB / formats.MAX_LOG, parser et reserve inchangés |
| Ledger / entrées | 16 MiB / 16384, une lecture de lot |
| Items figés par opération | min(252, 4*policy.max_population-4), donc 20 sous g0 |
| Noeuds parent→fondateur par branche | 9 maximum ; visited-set ; politique peut restreindre |
| Record lab/spec | 64 KiB chacun |
| Enveloppe et statement | 16 KiB chacun |
| Contenu privé cumulé | 32 MiB, dédupliqué ; inclut nouveaux reads d'ancêtres |
| Corpus checkout cumulé | 32 MiB, dédupliqué, politique g0 par défaut incluse |
| Un artefact/code checkout | 16 MiB |
| Fichiers checkout / entrées inventoriées checkout | 4096 / 8192, caches inclus dans comptage d'entrées |
| FD ouverts dans l'acquisition globale | 4096, tous roots/dirs/fichiers/ledger compris |

Appliquer limites de taille/count lors de l'inventaire et de chaque read, non
après allocation sans borne ; avant toute signature vérifier nombre d'items,
tant figés que dérivés après déduplication K, tailles des enveloppes et validité
de politique. Les dossiers visités comptent
dans le plafond d'entrées. Le plafond FD peut être atteint avant les plafonds de
fichiers ; capacité OS inférieure => échec source, jamais promesse de disponibilité.
L'agrégat privé compte une fois les bytes partagés avec 3A ; pas 32 MiB par phase.
Maintenir les limites layout 3A pour les chemins déjà couverts ; pas de lecture
nouvelle de usage mutable, journal SQLite, tâches ou résultats.

La formule de politique n'est pas le calcul exhaustif avec P/F réels (3C), ni une
preuve de plafonds. Plus grand corpus valide => SOURCE_LIMIT avec nom fixe atteint,
effacement du payload, aucun agrandissement, troncature ou appel multi-lots caché.

## 11. Codes, agrégats et gates

Codes nouveaux diagnostiques (pas des événements/états P1) :
POLICY_CONTEXT_MISMATCH, BRANCH_CYCLE, BRANCH_INCOMPLETE, BRANCH_DIVERGENT,
BRANCH_DEPTH_LIMIT, ANCESTOR_COMMIT_UNPROVEN, DECISION_ROLE_MISMATCH,
FROZEN_ITEM_DIVERGENT, EVIDENCE_NOT_STORED, HISTORICAL_ATTESTATIONS_NOT_EVALUATED,
SCIENTIFIC_PROFILE_UNSUPPORTED, SCIENTIFIC_SOURCE_UNAVAILABLE,
SCIENTIFIC_DIVERGENCE, SOURCE_CODE_IRREGULAR, SOURCE_PATH_FORBIDDEN.
Réutiliser STATEMENT_INVALID et ATTESTATION_MISSING/DUPLICATED/UNEXPECTED de P1,
codes trust existants et codes source/limits 3A. Conserver les codes des validateurs
purs comme détails structurés sans les traduire en admission refusée/accordée.

PASS = tous les prérequis nommés et comparaisons faites ; FAIL = contradiction
observée ; NOT_EVALUATED = prérequis absent ou capacité non supportée. FAIL domine
NOT_EVALUATED sur un même agrégat en présence d'une contradiction démontrée.
Un agrégat n'est jamais PASS sur un sous-ensemble silencieux. OBSERVED exige zéro
blocker ; une observation OBSERVED reste accepted=false avec scopes globaux NE.
Un manque d'attestation, une portée scientifique non évaluée ou un terminal/action
3A non évalué est bloquant : pas de statut OBSERVED trompeur sur preuve incomplète.

La matrice jointe contient des SPECIFICATION_ONLY, pas des essais exécutés.
Avant code : revue indépendante du tree contractuel final et corrections ; CI
exacte check-runs ET workflows, sauts/limites déclarés, threads/protections,
dépendances, pins/hashes et composition ; fusion avec expected_head_sha seulement.
Puis tree fusionné conforme et CI main avant clôture documentaire. L'implémentation
aura ses propres tests adversariaux, revue finale et gates ; les revues ne se
transfèrent pas à un contenu modifié. Pas de revue indépendante inventée ici.

Hors scope inchangé : 3C population/plafonds, contrôleur durable, writes/installation
trust/attestations, reprise/restauration/naissance, P5/P6, VPS/runtime/systemd/PPL/
FIN/epoch/production/TESTNET/LIVE/secret, Replay ou Diagnostic automatique.
#286 reste ACTIVE. Rollback documentation/source seulement, aucune migration.
