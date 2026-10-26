# 3B — Plan proposé : attestations et ascendance

2026-10-25, America/Mexico_City.
**PLAN_FOR_OPERATOR_VALIDATION / SOURCE_ONLY / LAB_ONLY / NO_IMPLEMENTATION.**

## 1. Point de départ vérifié

GitHub `main@33144194a1ec85e6cff96e3bb9ae6fda5db972f8`, arbre
`374e0a6f0f2341410909ec41d7d3439c28eac20d`, contient le contrat #503 et
l'implémentation #504. CI de ce SHA : 24 check-runs et 19 workflows réussis,
aucun job sauté, échec ou attente. Cela ne signifie pas zéro test skip/xfail ni
publication externe de couverture réussie.
[Clôture 3A](https://github.com/3a7i3/crypto-ia-terminal/pull/504#issuecomment-6404264710).

L'arbre local utilisé pour l'audit est identique à cet arbre GitHub ; son commit
local différent n'est pas présenté comme le HEAD distant. Les ZIP ne font pas foi
pour le code actuel. #286 est OPEN/ACTIVE. Les étapes 1 et 2 et la tranche 3A sont
clôturées ; l'étape 3 entière reste ouverte.

Le « go » autorise la préparation de ce plan. Son contenu concret est soumis à
validation ; cette publication ne vaut ni validation humaine du plan, ni revue
indépendante, ni autorisation d'implémentation déjà obtenue.

## 2. Objectif et frontière d'acceptation

Pour une opération déjà figée, déterminer quelles preuves d'attestation de la
décision et de sa branche parentale sont disponibles, liées aux bons objets et
vérifiables sous la confiance actuelle. Conserver séparément intégrité,
authenticité, autorisation de l'émetteur et couverture des preuves.

Le résultat reste un diagnostic immuable avec **accepted=false**. Un PASS local
concerne seulement une propriété explicitement couverte, jamais une admission,
une naissance, une autorisation de reprise ou une qualification du contrôleur.
L'autorité opérationnelle, la complétude globale, la population et les plafonds,
la durabilité, les actions de restauration et l'exécution restent NOT_EVALUATED.

3B ne remplace pas le `required_attestations` complet de P1 : sa partie population
nécessite 3C. Le diagnostic doit rendre impossible la confusion entre couverture
complète de la branche parentale et couverture complète du laboratoire.

## 3. Audit de réutilisation au baseline

| Source lue | Réutilisation prévue | Limite constatée |
|---|---|---|
| [P1](ADMISSION_CONTRACT.md), §3–5, 6, 11–13 et [scénarios](SCENARIOS_A0.json) | Sémantique normative, clés d'items, confiance actuelle, déclarations de portée | Pins intouchables ; aucune nouvelle politique inventée |
| `colony_admission/evidence_observer.py`, `observer.py` | Acquisition bornée, L1, inventaire de tous les logs, déduplication, vérifications finales/close | `scan_evidence()` ne retourne pas tous les objets nécessaires ; ne pas l'appeler puis rouvrir les sources |
| `formats.py`, `oplog.py`, `physical_evidence.py` | PREPARED, objets figés, parser strict, clés et chemins D2/D3 | Forme/hash ne prouvent pas signature, qualification ou identité sémantique |
| `external_evidence.py`, `observer._external` | Politique actuelle hors lab, pin externe, plancher et historique | Validation structurelle ne prouve pas installation monotone ni résistance au rollback |
| `trust.verify_envelope`, `classify_envelope`, `check_root` | Signature Ed25519, droits d'émetteur, sujet, audience, révocation | Ne pas réimplémenter la cryptographie ; genuine-but-revoked n'est pas authentifié |
| `trust.check_bundle` | Référence de complétude par (kind, subject, record hash) | Son chemin single-use appelle `_spend` et rouvre le ledger même sans écriture : appel interdit dans l'acquisition |
| `trust.verify_consumed`, `inspect_operations_fd` | Sémantique d'admission déjà consommée ; snapshot FD disponible | `verify_consumed` rouvre un chemin ; réutiliser les observations FD, une seule lecture globale |
| `lineage.verify_record`, `check_qualification`, identité A1 | Validation pure des records/specs et liens fondateur-descendant | `check_qualification` ne recalcule pas les hashes d'évidence/code et ne prouve pas la signature |
| Registrar `_ancestry`, `_check_admitted`, `_prepare`, `check_policy` | Référence des liens admission/qualification, exclusions, critères admissibles | Lecteurs path-based et population ; pas de `prepare`, `birth` ou `commit` dans le diagnostic |
| `Supervisor.load`, qualification et pilot : fonctions de hash | Référence de parcours fondateur→parent et fermetures de code | `load` relit les chemins ; les helpers de hash font de l'IO. Ne pas lancer les évaluateurs/campagnes |

Le code actuel ne fournit pas encore un validateur complet de statement P1 §3.5,
ni une dérivation sûre de toute la liste requise depuis un snapshot acquis.
Ces lacunes doivent être spécifiées, pas masquées derrière un appel à `lab.load`.

## 4. Périmètre proposé

### 4.1 Acquisition et interface distinctes

Prévoir un nouvel entrypoint diagnostique distinct de `observe`, `scan` et
`scan_evidence`, sans modifier leurs contrats ni leurs résultats. Le contrat 3B
figera son nom et ses types avant code. Il recevra seulement une configuration
opérateur bornée et épinglée, jamais une liste `required` fournie par un individu.
La politique registrar g0 et son pin sont le défaut ; toute politique alternative
doit être validée avec `check_policy` et un pin explicite, jamais tirée du seul log.

Un seul propriétaire acquiert L1 puis un seul snapshot ledger sous L2, conserve
les sources jusqu'aux vérifications finales et fermetures, déduplique les chemins
entre opérations et ancêtres. Factorisation interne limitée possible ; aucun
appel path-based au lab/registrar/trust qui relirait le ledger ou créerait un verrou.
Conserver les refus 3A : racine indisponible ≠ vide, absence stable ≠ échec IO,
ENOENT après ouverture ≠ absence, ACK/CR opaques, historique complet, aucun retry.
Un échec fondamental, d'acquisition, de limite ou de close efface tout résultat
provisoire. Les contradictions sémantiques restent des faits diagnostiques après
acquisition réussie ; elles ne se transforment pas en permission.

### 4.2 Branche parentale

Pour chaque opération sélectionnée, remonter du parent au fondateur avec ensemble
de visités et borne explicite ; valider ensuite du fondateur vers le parent sur
les records/specs acquis avec les validateurs purs existants. Vérifier identité,
spec, génération, fondateur, parent, diff déclaré et liaisons de qualification.
Cycle, parent manquant, substitution de spec/record ou fondateur incohérent bloquent
la preuve de branche. Le record figé du parent doit correspondre au parent acquis.

Pour chaque ancêtre descendant, exiger son admission, qualification de naissance,
statement et enveloppes, ainsi que sa propre opération COMMITTED correspondante
et son lien exact au ledger /1. Une ligne consommée seule, un terminal
FAILED_CONSUMED, une ligne /0 ou un home sans COMMITTED ne suffisent pas.
Ne pas consommer à nouveau, ne pas utiliser une autre opération du même enfant.
Pour le fondateur, exiger l'attestation individuelle ; ne pas inventer une admission
de naissance de fondateur. Chaque parent/ancêtre exige son attestation individuelle.
L'enfant candidat n'en exige pas une à D2 : c'est une action opérateur ultérieure.

### 4.3 Liste figée et complétude locale

Dériver indépendamment les besoins DECISION de la branche et des trois éléments
présentés (admission enfant, qualification parent, statement). Comparer aux items
de PREPARED, sans jamais réécrire, compléter ou remplacer la liste figée.
Clé : (kind, subject.agent_id, subject.agent_spec_id, record_sha256).
Dédupliquer les records identiques ; ne pas fusionner deux qualifications distinctes
du même sujet. L'envelope_sha256 figé doit désigner l'enveloppe acquise exacte.
Reclasser une preuve nécessaire de DECISION en POPULATION est une divergence.
Item requis absent, dupliqué, inattendu ou substitué reste un refus de preuve.

La partie POPULATION reste explicitement non évaluée en 3B. Les exclusions des
émetteurs doivent couvrir au minimum enfant et branche vérifiée ; la vérification
contre tous les individus réels du lab attend 3C. La population du BirthPlan est
une déclaration figée, jamais la preuve d'un inventaire courant exhaustif.
Sans opération PREPARED, ne pas fabriquer de liste ; avant stockage D2, indiquer
les preuves non disponibles au lieu d'inférer leur authenticité depuis un hash.
Ne pas attribuer les fichiers actuels à une ancienne tentative : conserver la
couverture historique D1 de 3A et rendre les attestations historiques indisponibles
si les objets exacts ne sont plus acquis. Pas de PASS historique reconstruit.

### 4.4 Confiance actuelle, consommation et révocations

Vérifier les enveloppes avec la racine courante validée sous pin opérateur externe
et plancher effectif. La racine historique de PREPARED reste un fait historique.
Une rotation bénigne ne doit pas invalider par principe une ancienne signature
encore valide ; clé/enveloppe révoquée reste un refus de preuve actuelle.
Renvoyer les propriétés et codes trust séparément. Une signature invalide sous clé
révoquée ne devient pas genuine-but-revoked. Aucun verdict SUSPENDED global ni
comptage de population n'est annoncé en 3B.

Distinguer admission candidate non encore consommée, consommée par cette opération,
consommée par une autre et admission d'ancêtre déjà consommée. Le snapshot FD et
les identités complètes d'enveloppe lient la preuve ; aucun helper de consommation
ou de bundle path-based n'est appelé. Une consommation ne prouve ni signature ni
COMMITTED. Aucun événement terminal ou STOP runtime n'est écrit à la révocation.

### 4.5 Statements et portée scientifique

Spécifier les champs fermés et toutes les cohérences de P1 §3.5 : auteur réel,
sujet, version d'émetteur, qualification référencée, critères, code et évidence.
R8 reste inchangé et historiquement non authentifié ; aucun issuer fictif portant
le nom du reviewer historique. PRESENT_ATTESTATION_OF_EXISTING_EVIDENCE conserve
campaign_replayed=false ; FRESH_CAMPAIGN exige des preuves de campagne existantes,
sans lancer de campagne. historical_signature_claimed reste littéralement false.

Inclure dans le contrat la vérification passive des artefacts et fermetures de code
requis pour les familles de qualification explicitement prises en charge. Utiliser
des listes de chemins attendus issues du code/contrat épinglé, jamais ouvrir un
chemin arbitraire fourni par un statement. Ni secret, ni chemin absolu, traversée,
lien, réseau ou exécution d'un module/campagne soumis. Un hash syntaxiquement valide
n'est pas un hash recalculé. Famille inconnue, source indisponible ou fermeture non
vérifiable : NOT_EVALUATED + blocage explicite, jamais qualification valide.
Le contrat devra lister les fichiers et encodages/digests exacts, notamment la
distinction hash canonique de record et hash des octets de chaque artefact.

### 4.6 Bornes proposées à figer dans le contrat

Conserver 256 logs, 256 opérations toutes tentatives, 32 MiB de logs, ledger unique
16 MiB/16384 entrées, 64 KiB/record et 16 KiB/enveloppe ou statement, 4096 FD.
Branche : au plus 9 individus du parent au fondateur (profondeur dure 8 du lab),
avec contrainte plus stricte de la politique applicable. Pas de relèvement de g0.
Références d'items : plafond universel 252 et plafond de politique
4*max_population-4 (20 sous g0), avant toute signature ; la population réelle et
le plafond exact plus serré suivant P/F restent des vérifications 3C.

Pour le nouvel entrypoint seulement, proposer un budget supplémentaire explicite
de 32 MiB pour artefacts scientifiques et sources de code, au plus 16 MiB par
artefact, 4096 fichiers, tout en respectant le plafond global de FD conservés.
Le budget D2/D3 3A reste 32 MiB : aucun changement silencieux de ses limites.
Un corpus valide plus grand est hors capacité, pas tronqué ou automatiquement
élargi. Le contrat final précisera comptage, déduplication, inventaires et méthode
d'acquisition des fichiers checkout (permissions distinctes des fichiers privés
du lab). Aucun PASS sur une fermeture partielle ou une liste tronquée.

## 5. Découpage et portes

| Livraison | Contenu | Condition avant la suivante |
|---|---|---|
| Ce plan, documentation seule | Audit, périmètre, dépendances et obligations | Validation explicite du plan concret par Mathieu |
| 3B contrat, documentation seule | Types/API, chemins exacts, partitions, états/codes, limites, matrice reliée à P1 | Revue indépendante du tree final, corrections, CI exacte et composition avant fusion gardée |
| 3B noyau pur, petite PR | Branche, clés/roles, statements, adaptation des verdicts trust sur objets acquis | Tests adversariaux, revue indépendante et CI au tree final |
| 3B acquisition, petite PR | Assemblage sur snapshot commun, ledger unique, fichiers acquis une fois | Tests réels temporaires et de panne, revue finale, CI exacte, fusion gardée |
| Clôture 3B SOURCE_ONLY | Tree fusionné conforme et CI du nouveau main complète | Arrêt avant code 3C, plan 3C à valider |

Le contrat peut regrouper ou réduire les deux PR de code si la séparation crée une
API intermédiaire dangereuse ; ne pas publier un résultat positif incomplet.
Toute dérive substantielle de périmètre ou conflit P1 revient à validation avant
code. Pas de modification de P1 pour faire passer le nouveau diagnostic.

## 6. Obligations de tests à spécifier (pas des tests exécutés)

| ID | Famille de cas | Résultat exigé |
|---|---|---|
| B-01 | Fondateur puis plusieurs générations, branche complète | Preuves locales explicites, accepted=false |
| B-02 | Cycle, parent absent, profondeur 8/9, parent/spec substitués | Refus borné, pas de récursion illimitée |
| B-03 | Record hash correct mais identité/lignée/diff faux | Validateurs sémantiques refusent |
| B-04 | Attestation individuelle absente d'un parent/ancêtre | Pas de droit de filiation |
| B-05 | Enfant sans attestation individuelle à D2 | Aucune exigence prématurée |
| B-06 | Ancêtre COMMITTED avec ledger /1 exact | Preuve liée, zéro re-consommation |
| B-07 | Ledger /0, autre opération, double entrée, hash/envelope_id divergents | Refus de preuve de consommation |
| B-08 | Home seul, FAILED_CONSUMED ou admission orpheline | Jamais ancêtre authentifié |
| B-09 | Deux qualifications différentes d'un même sujet | Deux clés par hash ; pas de fusion |
| B-10 | Items identiques réutilisés dans plusieurs chemins | Déduplication déterministe, une lecture du fichier |
| B-11 | Required omis/dupliqué/inattendu ou DECISION changé en POPULATION | Complétude locale refusée |
| B-12 | Population hors branche manquante ou falsifiée dans BirthPlan | Complétude globale non évaluée |
| B-13 | Pin faux, racine non LAB_TEST, plancher insuffisant, historique incohérent | Confiance indisponible, aucun PASS dérivé |
| B-14 | Rotation bénigne, clé retirée valide, version future | Sémantique trust existante préservée |
| B-15 | Révocation avec signature valide puis invalide | Restriction distinguée d'authenticité ; jamais droit accordé |
| B-16 | Mauvais lab/sujet/kind/purpose/issuer/scope | Propriétés et codes trust préservés |
| B-17 | Présentation R8 nue, issuer fictif, auteur différent | Pas d'adoption ou de signature historique inventée |
| B-18 | Statement incohérent, champs supplémentaires, duplicate JSON, bool/int | Refus strict, pas de normalisation réparatrice |
| B-19 | Mauvais hash qualification/critères/évidence/code | Divergence détectée ; aucun replay lancé |
| B-20 | Chemin absolu/traversée/lien/secret ou famille inconnue | Aucun accès arbitraire, preuve non évaluée/bloquante |
| B-21 | Sources de code irrégulières ou fermeture incomplète | Pas de hash qualifié sur sous-ensemble |
| B-22 | Avant D2, anciennes tentatives, fichiers actuels d'un autre essai | Indisponibilité et portée déclarées |
| B-23 | 20/21 sous g0, 252/253 universel, 256/257 opérations | Limite avant signatures et avant ledger selon contrat |
| B-24 | Limites contenu/artefacts/FD/profondeur et fermeture de FD en échec | Résultat provisoire entièrement invalidé |
| B-25 | ENOENT ouverture vs read/stat, EACCES, remplacement, inode/mtime/close | Absence stable distincte d'échec ; zéro réparation |
| B-26 | Verrous occupés, appels concurrents, sources modifiées | Refus sans retry, ordre L1→L2 |
| B-27 | Instrumentation fichiers/ledger, import-purity, mutation des résultats | Lecture ledger unique, aucun writer, résultat immuable |
| B-28 | Régressions observe/scan/scan_evidence, ACK/CR, Python -O | Compatibilité, pins et hashes qualifiés préservés |

Relier ces familles aux scénarios P1 pendant le contrat, sans modifier la matrice
P1 épinglée. Les tests utilisent uniquement des fixtures privées temporaires et
clés LAB_TEST de test ; aucune clé réelle ou valeur secrète consultée.
Faire détecter par les tests des affaiblissements ciblés (sujet, révocation,
item omis, ancien COMMITTED non lié), sans confondre mutations tuées et qualification.

## 7. Préservation, revue et décision demandée

Pins P1 recalculés pendant cette préparation :
`ADMISSION_CONTRACT.md` = `e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd` ;
`SCENARIOS_A0.json` = `4e518bfec6faaa582c2c42633d80e989b8204708b554f74b0eb1bbee6eaa59a1`.
Cette livraison n'ajoute que le présent document ; aucune source qualifiée n'est
modifiée. Aucun nouveau calcul de hash qualifié ou test produit n'est revendiqué
pour cette préparation documentaire.

Avant chaque fusion : contenu/plan approuvés, tests appropriés avec limites honnêtes,
revue indépendante au tree final (une CI verte ne la remplace pas), threads résolus,
protections et dépendances, pins/hashes, composition avec main. Fusion uniquement
avec expected_head_sha du HEAD revu ; contrôler arbre fusionné et CI du nouveau main
avant clôture. Les comptes de suites qui se recouvrent ne s'additionnent pas.

Ne modifier ni `colony_lab/`, `sentinel_activity/`, `colony_pilot/`, ni politique g0,
ni formats existants ou valeurs par défaut. Les adaptateurs de preuve vivent dans
`colony_admission/`, sans implémentation cryptographique parallèle. Si une extension
trust publique paraît nécessaire, arrêter et proposer son contrat séparé avant code.
Rollback : revert source seulement ; aucune migration, émission ou réparation.

Hors scope : contrôleur durable, install_trust/store_individual_attestation et tous
writers, restauration/reprise/naissance, inventaire exhaustif et plafonds 3C, P5/P6,
installation/runtime/VPS/systemd/PPL/FIN/epoch/configuration production/TESTNET/LIVE,
secret, Replay ou Diagnostic automatique. Aucun de ces outils n'est lancé par ce plan.

Décision demandée : valider ce périmètre 3B et le découpage contrat→revue→petites PR
SOURCE_ONLY, avec les bornes proposées et la séparation explicite de 3C. Après cette
validation, rédiger le contrat et la matrice avant toute implémentation. La revue
indépendante de ce nouveau contrat et ses preuves restent à obtenir.
