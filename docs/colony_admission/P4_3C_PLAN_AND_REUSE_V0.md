# P4 / 3C — Population et plafonds : plan et audit de réutilisation

**PLAN_FOR_OPERATOR_VALIDATION / SOURCE_ONLY / LAB_ONLY / NO_IMPLEMENTATION.**
Préparé le 2026-10-26, America/Mexico_City. Le « Go » de Mathieu autorise cette
préparation ; il ne vaut pas validation anticipée du présent périmètre détaillé.
Baseline vérifié : `main@d890081e94bcf0818145d0f919162e11cae8e58f`, tree
`f70d21a6d2ef456b3bee692636d7f6f79890647d` ; 3B clôturée dans
[#507](https://github.com/3a7i3/crypto-ia-terminal/pull/507#issuecomment-6417910506).
Aucun code 3C ajouté, aucune revue indépendante de ce plan revendiquée.

Normes : [P1](ADMISSION_CONTRACT.md) §3.1–3.4, §5, §6.1–6.8, §7–10 et §13 ;
[scénarios P1](SCENARIOS_A0.json) ;
[contrat 3A](P4_3A_PHYSICAL_EVIDENCE_JOIN_V0.md) ;
[contrat 3B](P4_3B_ATTESTATIONS_AND_ANCESTRY_V0.md) ;
[livraison 3B](P4_3B_ACQUISITION_DELIVERY_V0.md).
P1 reste prioritaire, sans changement de ses pins ou de ses formats.

## 1. Résultat attendu, sans autorité opérationnelle

Question : tous les foyers présents sont-ils inventoriés et leur classification
est-elle établie ? Les preuves hors branche, les exclusions globales, les comptes
et les plafonds de l'opération ouverte sont-ils cohérents avec ses objets figés ?

Proposer un diagnostic distinct `PopulationObserver(config).scan_population()`,
nom et types à figer dans le contrat suivant. Configuration opérateur épinglée,
pas de population, liste required, exclusion OWN_OPERATION ou compte fourni par
un individu. Les anciennes méthodes observe/scan/scan_evidence/scan_attestations
restent compatibles. On ne les appelle pas successivement pour composer des
snapshots différents : le nouveau propriétaire réutilise leur acquisition commune.

Résultats immuables, `accepted=false` permanent ; faits par foyer, par opération,
par partition, comptes et codes distincts. PASS signifie uniquement la comparaison
nommée. Une contradiction produit FAIL, un prérequis absent NOT_EVALUATED ; FAIL
domine NE. Pas de `admitted=true`, `qualified=true`, `can_parent`, `can_resume`,
permis de naissance, résultat de dry-run registrar ou qualification du contrôleur.
La présence des bytes ne prouve ni durabilité ni droit de reprise à froid.

## 2. Audit : réutiliser les règles, pas les lecteurs path-based

| Source auditée | Réutilisation proposée | Limite à préserver |
|---|---|---|
| `observer._Acquisition`, `evidence_observer._EvidenceAcquisition` et `_scan` | Un propriétaire L1→L2, FD gardés, historique, absences, D1/D2/D3, revalidation et close | L'extension actuelle n'inventorie pas tous les foyers ; les résultats antérieurs ne deviennent pas globaux |
| `attestation_observer._Attestations`, `_attestation_checkout.Checkout` | Politique opérateur, cache de branches/enveloppes, profils scientifiques, bornes communes | Les besoins actuels sont DECISION ; hors branche et population restent NE |
| `_attestation_core.branch/decision_partition/item_fact/ancestor_commit` | Identité/lignée, clé K complète, copies d'enveloppes, trust actuel, COMMITTED + `/1` exact | `branch` valide aussi une naissance candidate ; ne pas inventer une fausse opération pour valider un foyer isolé |
| `_attestation_statement`, `attestation_evidence` | Grammaire fermée, bindings scientifiques, agrégats distincts, révocation authentique | Profil PC2 non supporté ; aucun PASS dérivé d'une signature seule ou d'une liste partielle |
| `trust.inspect_operations_fd`, `classify_envelope` | Un snapshot commun et vérification cryptographique existante | L'inspecteur n'exporte pas les lignes orphelines : une couverture non rapprochée bloque ; aucun second lot |
| `registrar._population/_prepare/_check_admitted/_check_own_home` | Référence des sommes, exclusions, capacités et identité de son propre enfant | Appellent `lab.load`, ouvrent des chemins ; `prepare` lit aussi STOP. Ni appel direct ni instance lab dans le diagnostic |
| `lineage.verify_record/check_qualification`, identité A1 | Validation sur objets déjà acquis et identité canonique | Pas de `Supervisor.load/admit/run`, campagne ou import de code soumis |
| `external_evidence.project_fault_log` et projections d'opérations | Claims fermés, cibles, liaisons, terminaisons et actions observables | Projection structurelle seule ; ne l'utiliser ni pour effacer une faute ni pour ignorer arbitrairement un log corrompu |

Factorisation interne limitée de comparaisons existantes possible dans
`colony_admission/`, après contrat. Aucun changement des sources qualifiées
`colony_lab/`, `sentinel_activity/`, `colony_pilot/`, de g0 ou des formats existants.
Une extension publique de trust ou une divergence de P1 exige un contrat séparé
avant code ; elle n'est pas implicitement autorisée par 3C.

## 3. Inventaire et classification proposés

### 3.1 Univers acquis

Inventorier exhaustivement `individuals/` : chaque entrée doit être un foyer
nommé par un ID hex64, répertoire privé attendu, sans lien ni type spécial.
Une racine inaccessible n'est pas une population vide. Répertoire inconnu,
fichier isolé, double identité ou spec substituée bloque l'inventaire ; on ne les
ignore pas. Garder inventaires avant/après et FD/path, y compris les absences.

Acquérir une fois les records/specs, qualifications de naissance, admissions,
statements et enveloppes requis pour TOUS les foyers et leurs dépendances de
lignée. Un parent absent de l'inventaire n'est pas ajouté comme individu implicite.
Les foyers partagés par plusieurs branches et opérations utilisent les mêmes bytes.
La liste du BirthPlan est une déclaration figée, jamais la source d'inventaire.

Ne pas lire les contenus mutables de tâches/résultats, usage après DONE D3 ou bases
SQLite. Pour les exigences de layout, observer uniquement noms/types/métadonnées
bornés ; une arborescence dont le layout ne peut être établi reste explicitement
non évaluée et bloquante. Ne pas étendre ce parcours en explorateur général du lab.

### 3.2 Cinq statuts P1, avec prérequis explicites

| Statut P1 | Preuve proposée | Comptage et filiation |
|---|---|---|
| AUTHENTICATED | Fondateur : identité/lignée et enveloppe individuelle courante valides. Descendant : identité, COMMITTED unique exact, admission + qualification + statement et `/1` liés ; autres prérequis P1/3B établis | Compte ; filiation seulement si enveloppe individuelle et toute preuve DECISION passent |
| AWAITING_INDIVIDUAL_ATTESTATION | Descendant authentifié dans sa preuve de naissance, mais absence stable de sa seule enveloppe individuelle | Compte ; jamais parent/ancêtre admissible |
| SUSPENDED | Seulement KEY_REVOKED/ENVELOPE_REVOKED sur une preuve requise, signature réellement valide et intégrité/droits et autres prérequis établis | Compte de façon conservatrice ; aucune filiation ; signalement EXECUTION_SUSPENDED sans interdire un run |
| OWN_OPERATION | Unique opération ouverte pertinente, après BEGIN D3, foyer lié exactement au plan et à l'état P1 §6.7 ; pas un simple ID égal au candidat | Exclu du compte avant naissance pour cette opération uniquement ; ne crée aucun droit de reprise |
| UNAUTHENTICATED | Contradiction démontrée : identité/divergence, signature fausse, naissance orpheline, `/0`, FAILED_CONSUMED avec foyer, absence d'attestation fondatrice, etc. | Bloque l'évaluation favorable de toute naissance ; jamais retiré silencieusement des comptes pour gagner une place |

Quand les prérequis sont indisponibles ou non supportés, ne pas inventer un sixième
statut P1 ni remplir AUTHENTICATED/UNAUTHENTICATED par défaut : classification
NOT_EVALUATED, raisons et blocage explicites. Une enveloppe présente mais invalide
n'est pas une absence AWAITING. Révocation + SIGNATURE_INVALID n'est pas SUSPENDED.
Un manque d'autre preuve que l'attestation individuelle ne bénéficie pas d'AWAITING.

Le contrat détaillé devra fixer la priorité de classification entre preuve de
naissance, attestation individuelle, révocation, branche manquante et portée
scientifique non supportée. Il réconciliera explicitement P1 COMP-08/COMP-10 :
l'absence individuelle permise hors branche n'est ni un item DECISION manquant
permis, ni une attestation POPULATION fictive. Pas de nouveau modèle de confiance.

### 3.3 Complétude et exclusions globales

Dériver sur l'univers acquis les besoins POPULATION et DECISION par
`K=(kind, subject.agent_id, subject.agent_spec_id, H(record complet))`.
Records identiques dédupliqués, toutes les copies de stockage attendues liées ;
qualifications différentes d'un même sujet distinctes. Comparer aux deux partitions
figées de PREPARED sans les réécrire ou remplacer ; rôle changé, item omis, inattendu,
doublon, digest substitué ou enveloppes incohérentes ne deviennent pas un PASS.
L'absence individuelle AWAITING est traitée selon COMP-10, pas par complétion fictive.

Exclusions des reviewers/admitters contre candidat, branche et TOUS les individus
réels inventoriés, avec la règle de préfixe 16 caractères existante. Ne pas réduire
cet ensemble aux seuls AUTHENTICATED pour autoriser un auto-émetteur. Un identifiant
non vérifiable empêche la preuve globale ; aucun faux PASS sur sous-ensemble.
Une révocation hors branche peut suspendre et compter le foyer sans devenir une
révocation DECISION ; révoquer une preuve de branche reste bloquant pour elle.

## 4. Comptes, plan figé et plafonds

Pour l'unique opération ouverte dont les preuves sont disponibles, calculer la
population avant naissance, les fondateurs F, les enfants directs du parent, la
somme des six budgets alloués (pas leur consommation runtime), la génération,
les permissions et le diff déclarés. Compter AUTHENTICATED, AWAITING et SUSPENDED.
OWN_OPERATION est exclu une seule fois, après preuve de son identité et de sa portée.
Si un foyer est UNAUTHENTICATED ou NE, ne pas publier de total exact favorable ou
un reste disponible prétendument utilisable : faits partiels bornés et blocage.

Comparer `birth_plan.population` (digests canoniques de records complets),
`population_count`, `children_count`, `budget_totals` aux observations calculées
avec OWN_OPERATION exclu ; ne jamais relancer `Registrar.prepare` ni remplacer le
plan. Différence observée => POPULATION_CHANGED, pas de réparation ni reprise.
Les changements de statut sous racine courante n'effacent pas un record des sommes.

| Contrôle | Règle existante à conserver |
|---|---|
| Population | P + 1 <= policy.max_population |
| Enfants directs | nombre des enfants directs comptés du parent + 1 <= policy.max_children_per_parent |
| Génération | génération parent + 1 <= policy.max_generation ; lignée cohérente |
| Budgets | somme des budgets alloués comptés + budget candidat <= chaque cap colony_budget ; candidat <= parent |
| Permissions/diff | Sous-ensemble des permissions parentales et diff exact des specs, sans élargissement |
| Nombre d'items | N <= 4P - 3F + 3, puis <= 4*max_population - 4 et <= 252 ; déduplication/absences AWAITING explicites |

G0 conserve population 6, génération 2, enfants par parent 2, runs concurrents 1
et tous ses budgets. Max_concurrent_runs est une valeur de politique : sans lire
les slots/états runtime ni lancer de run, le diagnostic n'en certifie pas
l'application actuelle. Toute politique alternative exige bytes/pin opérateur et
`check_policy` comme en 3B. Aucune valeur recalculée depuis le log seul.

**Population courante ≠ population historique.** Les opérations COMMITTED,
REFUSED ou FAILED_CONSUMED anciennes ne sont pas comparées comme une reprise
ouverte : des naissances ultérieures peuvent avoir changé la population légitimement.
Conserver leurs faits historiques ; sans snapshot historique acquis exact, leurs
anciens comptes/partitions globaux restent NE. Les foyers COMMITTED actuels peuvent
être classifiés par leur preuve de naissance sans réauthentifier rétroactivement
l'ancienne population. Plusieurs opérations ouvertes => blocage, aucune sélection
opportuniste de celle dont les comptes passent.

## 5. Fautes, terminaisons externes et correspondances

Relier les cibles fermées du fault log aux ressources nommées du snapshot, aux
IDs/attempts et aux objets d'opération, sans ouvrir de chemin arbitraire soumis.
Séparer faute ledger/trust globale, faute d'opération et faute de répertoire
bloquant une mise à l'écart. Une faute reste sticky ; aucune présence de bytes
ou vérification favorable ne la lève. Aucune nouvelle preuve de durabilité.

P1 §6.1/§7.3 prévoit un log faulty terminé extérieurement qui ne doit pas être
relu par le scan ordinaire. L'acquisition 3A/3B actuelle refuse conservativement
ces terminaisons. Prévoir un mode 3C distinct, contracté et testé : terminalisation
observée uniquement si claim externe strict, lien de faute exact, identité,
classification et finding ledger exacts concordent avec le snapshot unique.
Une entrée `/0`, un digest historique seul ou une ambiguïté ne justifie pas cette
exception. Tout autre log corrompu continue de bloquer ; aucune réparation/ACK.
Les anciennes API gardent leur refus conservateur.

Un foyer terminal présent reste UNAUTHENTICATED et bloque ; une déclaration
SET_ASIDE_DONE ne suffit pas à effacer un foyer encore sous `individuals/`.
Définir les correspondances source/destination requises avec l'inventaire borné
`admission-quarantine/<operation>/<attempt|terminal>` et les cibles de faute,
sans SQLite ni contenu runtime. Si les bytes exacts attendus ne peuvent être liés,
le fait d'action reste NE/bloquant. Pas de permission de déplacer/quarantainer.
La lecture ne valide jamais les préconditions cold-read de recover : étape 5.

## 6. Bornes proposées et invalidation

Conserver les capacités 3A/3B : 256 logs et 256 opérations toutes tentatives,
32 MiB logs, ledger 16 MiB/16384 entrées en un lot, records/specs 64 KiB,
enveloppes/statements 16 KiB, contenu privé partagé 32 MiB, checkout partagé
32 MiB/16 MiB par fichier/4096 fichiers/8192 entrées, total 4096 FD conservés.
Pas de budget additionnel 32 MiB par foyer ou phase ; aucune troncature silencieuse.

Proposer un inventaire d'au plus 65 foyers (64 au plafond absolu de politique +
un éventuel OWN_OPERATION) ; c'est une borne de capacité, pas une permission de
population 65. Les plafonds g0/alternatifs restent des prédicats séparés.
Proposer 8192 entrées privées visitées au total, y compris métadonnées de layout
et quarantaine ; limite ferme avant collecte sans borne. Les règles exactes du
layout et des namespaces facultatifs devront être figées au contrat.
Un corpus valide plus grand reste hors capacité, refusé, pas implicitement accepté.

Inventorier/classifier les besoins structurels et vérifier les plafonds d'items
connus avant toute signature ; les limites déductibles des logs avant le ledger.
Aucune lecture supplémentaire de ledger pour un foyer absent du premier inventaire.
FD/path, inventaires, absences et close doivent tous être revalidés ; erreur IO,
source fondamentale invalide, mutation ou limite => BLOCKED et payload entièrement
effacé, agrégats NE. JSON stable divergent => fait local contradictoire, raw digest
conservé, sans laisser ses dépendants passer. Une absence stable exige parent acquis,
listing stable et ENOENT à l'ouverture ; ENOENT après ouverture est une erreur.

## 7. Familles de tests à spécifier après validation

Ces 30 familles sont des obligations de contrat/matrice futurs, pas des tests exécutés.

| ID | Famille | Résultat attendu |
|---|---|---|
| C-01 | Racine vide stable, racine absente/inaccessible, namespace invalide | Vide prouvé distinct d'indisponible, aucune omission |
| C-02 | Plusieurs fondateurs et branches, ancêtre partagé | Inventaire exhaustif, lectures dédupliquées |
| C-03 | Record/spec/id substitué, parent absent, cycle, profondeur | Pas de préfixe authentifié |
| C-04 | Fondateur avec/sans enveloppe individuelle | AUTHENTICATED ou refus P1 COMP-07 |
| C-05 | Descendant COMMITTED et `/1` exact | Preuve de naissance liée sans consommation |
| C-06 | `/0`, admission orpheline, mauvais op/digest/issuer/envelope_id | Pas d'authentification de population |
| C-07 | Enfant COMMITTED sans individuelle, puis individuelle fausse | AWAITING permis hors branche ; falsification distincte |
| C-08 | AWAITING proposé comme parent/ancêtre | FILIATION_NOT_ATTESTED, aucun PASS DECISION |
| C-09 | Révocation valide seule, puis signature invalide en plus | SUSPENDED compté ; jamais genuine-but-revoked sur faux |
| C-10 | Révocation hors branche versus dans branche | Portées distinctes, capacité ne croît pas par révocation |
| C-11 | Foyer FAILED_CONSUMED ou sans COMMITTED | UNAUTHENTICATED bloque, jamais ignoré |
| C-12 | OWN après BEGIN D3 / DONE D3 / mauvais candidat ou tentative | Exclusion exacte, usage mutable après DONE D3 |
| C-13 | Deux opérations ouvertes, terminale, ancien COMMITTED | Pas de fausse exclusion ni égalité historique inventée |
| C-14 | Population BirthPlan omise/substituée, budget/compte changé | POPULATION_CHANGED sans réécriture |
| C-15 | Items POPULATION omis/inattendus/dupliqués ou reclassés | Complétude exacte, pas de remplacement |
| C-16 | Qualification réutilisée et deux qualifications d'un même sujet | Clé K par record ; copies cohérentes |
| C-17 | Reviewer/admitter lié à individu d'une autre branche | Exclusion globale, même si foyer suspendu/AWAITING |
| C-18 | Population 5/6/7 sous g0 ; plusieurs fondateurs | Plafond inchangé, aucun faux reste disponible |
| C-19 | Deux enfants directs, troisième ; génération 2 vers 3 | CHILDREN_LIMIT / GENERATION_LIMIT |
| C-20 | Six budgets aux bornes, parent et colonie, bool/int | Sommes exactes et refus d'escalade |
| C-21 | Formule P/F, absences AWAITING, 20/21 et 252/253 | Bornes avant signatures, pas de liste tronquée |
| C-22 | PC2/inconnu, source scientifique absente ou altérée | NE bloquant ou FAIL prouvé, jamais authentification complète |
| C-23 | Faute ledger/trust/opération/répertoire et mauvaise cible | Portée liée, sticky conservé |
| C-24 | Terminaison externe stricte / historique substitué / log corrompu | Exception P1 seulement si preuves exactes, sinon blocage |
| C-25 | Quarantaine source+destination, ni l'une ni l'autre, DONE mensonger | Aucun foyer escamoté ni déplacement autorisé |
| C-26 | Capacités foyers/entrées/bytes/logs/FD, close/unlock raté | Invalidation totale, zéro payload provisoire |
| C-27 | Liens/FIFO/hardlinks/permissions et ENOENT read/stat | Pas d'absence inventée ni lecture arbitraire |
| C-28 | Remplacement, mutation d'inventaire, verrou occupé, concurrence | Ordre L1→L2, sans retry |
| C-29 | Instrumentation opens/ledger/imports/résultats immuables | Un snapshot, aucun writer/bundle/spend/réseau/campagne |
| C-30 | Régressions 3A/3B, ACK/CR, python -O, conformité registrar | Pas de changement des anciennes API, pins/hashes conservés |

Relier explicitement ces familles aux IDs P1 valides : COMP-01..10, AUTH-*,
REV-*, CEIL-01..03, OWN-*, TX-*, HOME-*, DUR-* et QUAR-* pertinents, sans
assimiler leurs effets opérationnels à des actions du diagnostic. Fixtures privées
temporaires LAB_TEST et clés publiques de test ; pas de corpus opérationnel.
Les tests normaux et -O se recouvrent ; pas de nombre de réussites promis avant code.

## 8. Découpage, gates et validation demandée

1. **Ce plan documentaire** : audit et périmètre soumis à Mathieu ; aucune implémentation.
2. **Contrat détaillé + matrice 3C** après validation : API/types, tables de priorité,
   mapping exact des chemins, partitions/époques, règles OWN et terminaisons,
   bornes/codes, références P1 et checklist de clôture de l'étape 3.
3. **Revue indépendante de l'arbre contractuel final**, corrections, CI exacte,
   threads/règles/pins/composition ; fusion gardée puis CI propre main.
4. **Petites PR de code** prévues : acquisition globale/classification d'abord,
   rapprochement des plans/plafonds/correspondances ensuite. Si la séparation crée
   un résultat positif incomplet, garder l'API privée jusqu'à preuve complète.
   Tests adversariaux et revue indépendante du tree exact à chaque livraison.
5. **Clôture de capacité 3C SOURCE_ONLY** seulement après arbre fusionné conforme et
   CI propre main complète. La clôture de l'étape 3 exige en plus sa checklist
   globale : aucun prérequis absent, profil scientifique ou fait d'action bloquant
   ne devient PASS par clôture administrative. PC2 reste une limite explicite tant
   que son mapping n'a pas son amendement contractuel et ses preuves.

Avant chaque fusion : inventaire check-runs filter=all ET workflows exact head_sha,
tous événements/statuts et pagination exhaustive, sauts expliqués, logs vérifiés ;
publication Codecov non certifiée si l'upload est refusé. Revue indépendante finale,
threads/protections/ruleset, dépendances, pins/hashes et composition revérifiés.
Fusion seulement avec expected_head_sha ; aucun bypass ni relance aveugle de CI.
Pas de contrôleur durable, reprise, recover, installation de trust/attestations,
restauration, writers, naissance ou P5/P6 dans cette préparation. Aucun VPS/runtime,
systemd/PPL/FIN/epoch/production/TESTNET/LIVE/secret/Replay/Diagnostic automatique.

Pins P1 à préserver : `ADMISSION_CONTRACT.md` =
`e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd` ;
`SCENARIOS_A0.json` =
`4e518bfec6faaa582c2c42633d80e989b8204708b554f74b0eb1bbee6eaa59a1`.
Les sources qualifiées ne sont pas changées. Rollback : revert source seulement,
aucune migration ou mutation d'état opérationnel. #286 reste ACTIVE, accepted=false.

**Décision demandée : valider ce périmètre 3C pour rédiger son contrat détaillé et
sa matrice avant implémentation.** Les bornes et règles proposées seront figées
et revues dans ce contrat ; aucune approbation anticipée du code ou de 3C complet.
