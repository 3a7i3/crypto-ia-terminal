# PC2/p1 — amendement de profil scientifique v0

2026-10-26, America/Mexico_City.
**CONTRACT_FOR_REVIEW / SOURCE_ONLY / LAB_ONLY / NO_IMPLEMENTATION / PROFILE_BLOCKED.**
Mathieu autorise la préparation d'un amendement précis, puis ses tests avant
activation. Ce document soumet la règle normative concrète ; il ne vaut pas encore
validation de cette règle ni autorisation d'activer un profil.

Baseline vérifiée : `main@5df6c6c248f3a1aef9b5f8819e18153def16fca5`,
tree `9fb13944121b5cf4b461c2280da4afdafe52638e` (#508 clôturée).
#509 reste une livraison privée distincte ; son état CI/fusion n'est pas déduit
ici. L'audit/proposition de sa livraison3C1 n'était pas un amendement approuvé.
Les ZIP ne constituent pas le baseline du présent travail.

Références : [P1](ADMISSION_CONTRACT.md) §3.5, §4–5 et §13 ;
[3B](P4_3B_ATTESTATIONS_AND_ANCESTRY_V0.md) §8–10 ;
[3C](P4_3C_POPULATION_AND_CEILINGS_V0.md) §5–9 et §12–13 ;
[matrice PC2](P4_PC2_NATIVE_EVIDENCE_AMENDMENT_CASES_V0.json).

## 1. Décision proposée et priorité normative

Profil fermé proposé : `pilot-p1-pc2-present-native-v0`.
Il prend en charge exclusivement l'attestation présente de l'évidence native PC2,
concernant le pilote exact, sous les critères p1 exacts. Il ne produit aucune
qualification, aucun statement ou signature et n'exécute aucune campagne.

**Extension explicite soumise à validation :** P1 §3.5 décrit la copie présente
d'une qualification historique (R8) et 3B §8–9 en précise les profils. PC2 n'a pas
de qualification historique pilote au format `colony-lab.qualification/0`.
Ce texte propose, uniquement pour ce profil, que le record historique nommé par
`historical_record_path` soit le record natif `colony-lab.pilot-evidence/0` PC2,
et que les champs scientifiques du nouveau q soient dérivés par la table §3.
Ce n'est ni une qualification historique retrouvée ni un simple changement de hash.

Cette extension de l'interprétation P1 §3.5 doit être explicitement approuvée avec
l'arbre exact de l'amendement. Les bytes/pins P1 restent intacts ; l'ancien pin P1
seul ne certifie pas cette nouvelle règle. Le dossier de validation doit identifier
P1 + cet amendement (commit/tree et SHA256 raw des deux documents), et citer la
portée de l'exception. Sans cette décision explicite, **conserver le refus PC2** ;
ne pas réinterpréter silencieusement un champ de 3B pour rendre les tests verts.
Aucune préséance de cet amendement sur les autres obligations P1.

Après validation et implémentation seulement, cette exception remplace le refus
scientifique systématique de 3B §9.2/3C §13 pour ce seul couple profil/scope. Les
autres profils et toutes les anciennes attestations R8 gardent leurs règles.
Les formats persistants qualification/0, statement/0, enveloppes et PREPARED,
les kinds, les chemins D2/D3 et les clés K ne changent pas.

## 2. Sources fermées et pins raw

SHA256 ci-dessous = hash des bytes complets, distinct de H(JSON canonique).
Tous les JSON sont lus sans doublons/non-finis ; les bytes ne sont pas réécrits.
Le choix des chemins vient exclusivement du profil compilé, jamais d'un statement.

| Alias | Path checkout exact | SHA256 raw |
|---|---|---|
| P1C | `docs/colony_lab/PILOT_CRITERIA_P1.json` | `dcc3fe71909117ee2501ff3c5d2f8866f5343123929af40e06484a8ebf713ef7` |
| PC2 | `docs/colony_lab/evidence/PC2_pilot_evidence.json` | `d706928e843275d58cab330426f6745db864194a86ef389fbed1dd93a7bc6b4d` |
| R8C | `docs/colony_lab/SENTINEL_QUALIFICATION_CRITERIA_R8.json` | `22528f1629db5d565f54137e11e99f670c68152eb3127cbafabe5f1072ca990a` |
| C9 | `docs/colony_lab/evidence/C9_sentinel_evidence.json` | `bc2f37df6bf7ab8138d326862906431154c07b298fb4b482db4fc6a0910f71cf` |
| R8Q | `docs/colony_lab/SENTINEL_QUALIFICATION_RECORD_R8.json` | `d38656c56f59c7d950d3031ec969cfe6e6e126ed27f3ab2c83ab3d022518c578` |

Le corpus scientifique PC2 acquis contient exactement ces cinq artefacts ; un
cache checkout commun peut également contenir g0 et les sources d'autres profils,
mais le mapping détaché transmis au validateur PC2 est cette sélection exacte.
PC1/p0, un fichier renommé, un hash canonique remplaçant le pin raw, ou un record
pilote synthétisé dans checkout ne remplace aucun de ces artefacts.

## 3. Correspondance exhaustive des trois fermetures de code

Hash = SHA256(concaténation triée de path POSIX UTF8 + NUL + SHA256(raw).digest()).
La sélection de fichiers et le traitement des caches sont exactement 3B §9.1–9.3,
tous fichiers réguliers inclus, pas seulement *.py. Pas d'import des produits.

| Rôle | Racines et exclusions | Pin de fermeture | Liaison obligatoire |
|---|---|---|---|
| Worker sujet S | Racines subject 3B §9.1 : `colony_lab/__init__.py`, `colony_lab/workers/__init__.py`, `colony_lab/workers/sentinel.py`, `governance_tower/`, `observability/__init__.py`, `observability/event_center_contract.py`, `observability/runtime_service_contract.py`, `observability/storage_contract.py` | `2c926421416731dc629915067bcea472729e6785ec8dcb6e28f15ae7b41e4ec8` | `q.subject_code_sha256 = statement.subject_code_sha256 = PC2.subject_code_sha256 = C9.subject.subject_code_sha256 = R8Q.subject_code_sha256 = S` |
| Évaluateur Sentinel E | `colony_lab/` et `sentinel_activity/`, moins l'ensemble subject | `41b78971184809652dd1190dded49ab27d58c35c8a995351a47bf0f85756faa4` | `PC2.sentinel_evaluator_code_sha256 = C9.evaluator_code_sha256 = R8Q.evaluator_code_sha256 = E` |
| Évaluateur pilote P | `colony_pilot/` récursif, sans soustraction de E | `97fb6b0489976f8b003823c1536932ec10a1c7faa699ef6f6eb1bd4056238bc7` | `q.evaluator_code_sha256 = statement.evaluator_code_sha256 = PC2.pilot_code_sha256 = P` |

Chaque égalité exige aussi le recalcul courant égal au pin correspondant.
E ne disparaît pas parce que qualification/0 n'a que deux champs : PC2 entier,
nommé par q.evidence_sha256 et par le statement, le lie sous signature présente.
Aucun hash composite nouveau, champ supplémentaire ou permutation tolérée.

## 4. Qualification présente, auteur et scope

q garde les onze champs fermés de qualification/0. Valeurs scientifiques exactes :

- `agent_id` = `PC2.pilot.agent_id` = `1eb3baaf0bf1ec4ddc6559e128b8685e4a1d91da49f417ff33cc0fa196c0a22a` ;
- `agent_spec_id` = `PC2.pilot.agent_spec_id` = `660ec9a818fc3c3c41b432520dbcc881cc8c840cdb1a5a80318488ee0e22d986` ;
- state `QUALIFIED_SIMULATED`, scope `SIMULATED_DETERMINISTIC` ;
- critères = pin P1C ; evidence_sha256 = pin raw PC2 ; hashes code S et P selon §3 ;
- reviewer_kind/id = auteur actuel identifié, autorisé dans la confiance courante.

Le nouveau q est un objet présenté à vérifier, pas une sortie du diagnostic. Son
state doit résulter du jugement actuel de cet auteur sur le corpus PC2 exact,
jamais d’une conversion automatique de PC2.proposed_state. La porte scientifique
« Before any pilot record » du [rapport natif](../colony_lab/PILOT_DESCENDANT_REPORT.md)
reste nécessaire avant toute émission réelle : revue indépendante de p1, PC2,
colony_pilot et des tests, avec mutants non vus par leur auteur, de type
EXTERNAL_REVIEW_PROCESS ou EXTERNAL_HUMAN, et conclusion favorable justifiant
ce jugement. Son dossier doit identifier les artefacts, le tree des tests revus,
le reviewer et ses conclusions/limites ; aucune référence historique non lue
n’est présentée comme cette preuve. La revue de cet amendement ou de son futur
validateur n’est PAS cette revue scientifique de qualification. Une preuve
manquante de cette revue ne peut pas être fabriquée ou remplacée par une revue
d’agent de l’implémentation.

Cette porte concerne la décision externe d’émettre q ; le diagnostic ne certifie
pas son exécution à partir de deux signatures. Les champs existants ne portent
pas un dossier de revue indépendant vérifiable par le scanner : sa provenance
reste hors preuve du profil, jamais annoncée PASS. On n’ajoute ni champ persistant
ni sixième artefact implicite pour dissimuler cette limite. En l’absence du dossier
requis, l’émission réelle et l’activation opérationnelle restent bloquées, même
si la capacité logicielle de comparer ce profil est testée. Ni `colony-review-481-r8`, ni l'auteur de l'évidence PC2, ni un
nom de reviewer inventé ne reçoit de clé ou de droits par cet amendement.

Le statement conserve tous les champs et types de 3B §8, avec les exceptions de
profil explicitement définies au §1. Pour le profil PC2 présent :

| Champ | Valeur exigée |
|---|---|
| scope | `PRESENT_ATTESTATION_OF_EXISTING_EVIDENCE` uniquement |
| historical_record_path / historical_record_sha256 | Path PC2 exact / pin raw PC2 exact : **record natif d'évidence**, pas qualification historique |
| evidence | Singleton exact `[{path: PC2, sha256: pin raw PC2}]` (valeurs du §2), pas R8Q ni C9 à sa place |
| qualification_record_sha256 | H(q complet canonique), pas hash raw PC2 ou record_hash interne |
| campaign_replayed / campaign_evidence_sha256 | Littéral false / null |
| historical_signature_claimed | Littéral false |
| subject et hashes scientifiques | Identiques à q et aux liaisons §3–4 |
| issuer_kind/id et issuer_root_version | Reviewer de q et émetteur/version des DEUX enveloppes q et statement |
| verified_at_source_sha | hex40 déclaré selon 3B ; pas inféré du HEAD PC2 ni preuve de provenance Git |

La liste evidence singleton ne dispense pas des quatre autres artefacts : ils
sont des dépendances scientifiques obligatoires du profil fermé, acquises par
l'owner. Les deux enveloppes actuelles sont vérifiées via trust.classify_envelope
sur les objets acquis, sous root/pin/floor courants. Les autorisations des kinds
qualification et statement et les exclusions des reviewers restent obligatoires.
Une signature de statement ne remplace pas celle de q, ni réciproquement.

FRESH_CAMPAIGN pour les critères p1 reste **NE bloquant / SCIENTIFIC_PROFILE_UNSUPPORTED**
dans ce profil. Les champs doivent d'abord satisfaire la grammaire FRESH générale ;
une incohérence prouvée garde STATEMENT_INVALID/FAIL. Un vieux PC2, un booléen true,
un SHA git récent ou une signature récente ne démontre pas une nouvelle campagne.
Un futur profil FRESH exige un autre contrat ; aucune campagne n'est lancée ici.

## 5. Identité et contexte de lignée acquis

La preuve scientifique PC2 exige des records/specs acquis du sujet pilote ET de
son parent Sentinel. Ils viennent du propriétaire du snapshot courant, pas de
nouveaux arguments publics agent_id/spec/permissions choisis par l'appelant.
Un contexte absent donne NE/SCIENTIFIC_SOURCE_UNAVAILABLE ; un contexte stable
contradictoire donne FAIL/SCIENTIFIC_DIVERGENCE. Une ancienne évidence seule ne
fabrique ni foyer, ni spec, ni COMMITTED, ni droit de filiation.

Valider l'identité A1 et lineage.verify_record sur ces objets avant crypto, avec
la branche structurelle complète prévue par 3B/3C. Comparer le spec_artifact_hash
complet, pas seulement agent_spec_id. Comparaisons structurées via bytes
canoniques, sans égalité Python qui confond bool/int : générations sont des int
stricts (pas bool), inherits_parent_memory est le littéral false, budgets des int
stricts ; aucune coercition. Valeurs de ce profil exact :

| Objet | Exigences liées à PC2, C9 et critères |
|---|---|
| Sentinel parent/fondateur | ID `4279e165b2706c088840d1cdc4ebe3efa76c2ea220bc948a8336c4343eb23173`, spec ID `b74ab69619acdb3747edd64affbc6d5ae3c99f32249c49bf4288e5786836d4ed`, spec artifact `fd130c1bcd6c10a13b9cab3cbcd4d8e78b5b21a388251523b298dbc14927b5a6`, FOUNDER génération0 ; permissions exactes `DIAGNOSTIC_PRODUCE`, `GOVERNED_ARTIFACT_READ` |
| Pilote sujet de q | ID/spec §4, spec artifact `3eb0786822165e7f7fd60b1f8bb8d84bef4c803e90ac52bcbff08e093cbb4dcc`, DESCENDANT génération1, parent/fondateur = Sentinel exact, même lineage_id ; base spec parent exacte, declared_diff exact `[purpose]` et spec_diff recalculé ; permissions exactes `[DIAGNOSTIC_PRODUCE]` |
| Les deux records | Budget six entiers stricts exacts : cpu_seconds30, wall_seconds60, memory_bytes1073741824, output_bytes1048576, runs10, journal_events100 ; mémoire OWN_J01_JOURNAL sans héritage, credentials NONE, registry NON_DEPLOYED/NOT_AVAILABLE et operational_authority DENIED |

Ces budgets sont ceux de la campagne épinglée (qualification.BUDGET dans la
fermeture E), pas un budget runtime observé. Une allocation courante différente
ne peut pas être qualifiée par ce profil exact, même si plus basse. Ne pas ouvrir
usage.json, SQLite ou la mémoire du parent pour « prouver » ces propriétés.
L'absence d'héritage est la propriété déclarée du record validé, pas une preuve
de séparation physique actuelle de tous les bytes de mémoire.

**Deux qualifications distinctes :** birth_qualification.json du pilote concerne
Sentinel (qualification du parent lors de sa naissance). q PC2 concerne le pilote
lui-même, par exemple présenté comme parent d'un autre candidat. Ne jamais remplacer
birth_qualification.json du pilote par q PC2, signer son ancienne naissance à
nouveau ou attribuer les résultats PC2 à un nouveau child. Les qualifications,
statements et copies restent dédupliqués par K incluant H(record complet), sans
fusion des sujets Sentinel/pilote ou de deux q du même sujet.

Ce profil ne généralise pas PC2 à une copie de pilote portant un autre ID/spec,
ni à une génération2. Les plafonds/générations/diff/permissions de tout candidat
et les preuves COMMITTED/D1/D2/D3 restent des comparaisons séparées inchangées.

## 6. Bindings internes de l'évidence et dépendance R8

En plus des pins raw et des fermetures complètes, exiger les comparaisons :

1. P1C.criteria_schema `colony-lab.pilot-criteria/0`, revision p1, scope
   SIMULATED_DETERMINISTIC ; son parent r8 et ses paths sont exactement ceux §2.
2. PC2.evidence_schema `colony-lab.pilot-evidence/0`, criteria_revision p1,
   criteria_status CURRENT, criteria_sha256 = pin P1C = q.criteria_sha256.
   Scope = q.scope ; proposed_state PROPOSED_QUALIFIED_SIMULATED,
   failure_reasons/code_irregular vides, deterministic_across_fresh_labs true,
   evaluator_runtime.source_only true, environment.sandbox VERIFIED,
   sandbox_view.matches_subject true. Tous ces booleans sont des littéraux.
3. PC2.parent ID/spec = Sentinel du §5 ; matches_current_code true, mismatched vide.
   PC2.parent.record_sha256 = pin raw R8Q = SHA256(raw R8Q acquis), et
   PC2.parent.qualification égale R8Q décodé **complet**, reviewer historique inclus.
   Ce dernier n'est pas accepté comme émetteur actuel et n'est pas authentifié.
4. R8Q id/spec = C9.subject id/spec = Sentinel ; R8Q.criteria_sha256 = pin R8C,
   R8Q.evidence_sha256 = pin raw C9 = SHA256(raw C9 acquis), hashes S/E §3,
   state QUALIFIED_SIMULATED, scope SIMULATED_DETERMINISTIC. C9 critères r8/CURRENT,
   pin R8C, état PROPOSED_QUALIFIED_SIMULATED, failure_reasons/code_irregular vides,
   deterministic_across_fresh_labs/golden_subject_code_matches true et
   evaluator_runtime.source_only true comme 3B §9.1. Ne pas substituer la règle
   PRESENT R8 de copie d'un q courant à cette dépendance historique raw.
5. PC2.pilot ID/spec/artifact/génération/permissions/diff = contexte §5 ;
   P1C.pilot permissions/diff, identité nominale et purpose concordent avec le spec
   acquis ; specs parent/pilote vérifiés A1. PC2.not_claimed = P1C.not_claimed.
6. PC2.rounds : deux listes identiques, chacune contient exactement les28 IDs
   dans l'ordre B01..B12 de P1C.birth_trials, Q00..Q14 de R8C.trials puis P01 de
   P1C.permission_trials. Chaque entrée a passed littéral true, failed_predicates
   vide et facts_sha256 hex64. Pas de doublon, essai omis ou 27/28 retenu.
   Le pin raw lie aussi les codes/kinds/status et tous les autres champs natifs.

Ces propriétés décrivent les claims du corpus épinglé ; aucun run, import du
campaign, replay de prédicats ou qualification du contrôleur n'en découle. La
provenance temporelle, la fraîcheur et l'exécution passée par l'auteur courant
restent NE. Les28x2 succès natifs ne sont pas des tests exécutés dans cet amendement.

## 7. Acquisition, limites et verdicts

Pas de nouvelle API publique, de config de chemin PC2, d'override de profil ou de
liste required fournie par l'appelant. Le dispatch interne sélectionne p1 exact
puis le scope fermé §4. Il reçoit des bytes acquis et un contexte immuable,
ainsi que S/E/P calculés depuis les inventaires complets, jamais un E optionnel.
Interface interne et propagation des résultats à définir au code selon ce contrat ;
pas d'appel public imbriqué ni de seconde acquisition pour compléter le contexte.

Réutiliser le même propriétaire L1→L2, le cache des artefacts et des fermetures,
la même union U/ledger et la vérification de sortie. Tous les fichiers partagés
avec R8 sont lus une fois. Aucune inspection ledger spécifique PC2. Limites 3B/3C
inchangées : checkout32MiB cumulés,16MiB/fichier,4096 fichiers,8192 entrées ;
4096 FD globaux, contenu privé32MiB, records64KiB, enveloppes/statements16KiB,
items policy/hard et graphe K/N/P/F avant signatures. Pas de32MiB par profil.

Acquisition manquante/IO/limite/mutation/close échoué invalide tout le payload
selon les lecteurs existants ; pas de sous-ensemble de fermeture scientifique.
Une source stable contraire aux pins ou liaisons connues donne FAIL/SCIENTIFIC_DIVERGENCE ;
forme/auteur/scope contradictoire donne FAIL/STATEMENT_INVALID ; un contexte détaché
requis absent donne NE/SCIENTIFIC_SOURCE_UNAVAILABLE. Profil/scope non pris en
charge => NE/SCIENTIFIC_PROFILE_UNSUPPORTED. FAIL prouvé domine NE sans convertir
une révocation ou absence en PASS. Conserver séparément les verdicts trust et science.

Même après une preuve scientifique PASS, il faut toutes les autres propriétés
3B/3C pour leurs agrégats. Genuine-but-revoked interdit la filiation ; le comptage
conservateur de population reste celui de 3C. Aucun PASS scientifique ne transforme
un foyer terminal, une preuve remplacée du COMMITTED ou un OWN incomplet en admis.
accepted=false permanent ; autorité, durabilité, recovery et provenance restent NE.

## 8. Plan d'implémentation et portes

1. **Cette PR documentaire séparée**, contrat et matrice seulement. Revue
   indépendante de l'arbre exact et corrections, puis validation explicite de
   l'exception native du §1 par Mathieu. Aucun code d'activation avant cela.
2. CI documentaire exacte, inventaires check-runs filter=all et workflows head_sha
   tous événements/statuts paginés jusqu'aux pages vides ; logs des échecs/skips et
   transports de couverture inspectés, revue/threads/ruleset/composition/pins.
   Fusion gardée expected_head_sha seulement, puis CI propre du merge complète.
3. Petite PR SOURCE_ONLY de validateurs internes et tests adversariaux sur fixtures
   LAB_TEST détachées (kinds/auteurs/signatures de test, aucune identité GitHub
   humaine imitée). Tests issus de la matrice, liens cas→tests effectivement
   exécutés et mutants des trois bindings ; revue indépendante du tree exact.
   Ne pas revendiquer la matrice exécutée à partir de son seul nombre de cas.
4. Intégration acquisition/projection isolée, seulement une fois disponibles les
   prérequis du propriétaire global 3C ; pas d'API publique positive partielle.
   Tester R8 seul, PC2 seul et mélange R8/PC2, limites partagées, effets des copies,
   close et `python -O` séquentiels sans écrire de bytecode. Nouvelle revue exacte,
   CI HEAD, fusion gardée et CI du merge à chaque livraison.
5. Le support scientifique PC2 peut être déclaré implémenté après ces gates. Une
   attestation réelle exige encore le jugement et le dossier de revue scientifique
   indépendants du §4, un auteur externe identifié et ses DEUX enveloppes
   existantes valides ; leur absence reste un blocage. Validation du
   contrat et tests ne sont pas une autorisation de créer/installer ces preuves.

Pendant les portes1–4 : PC2/p1 reste SCIENTIFIC_PROFILE_UNSUPPORTED/NE bloquant
dans les lecteurs existants ; p1 reste dans g0. Ne pas transformer une revue
d'agent du code en approbation GitHub d'identité distincte ni en attestation du pilote.

## 9. Préservation et clôture bornée

Pins P1 intacts : ADMISSION_CONTRACT.md
`e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd` ;
SCENARIOS_A0.json `4e518bfec6faaa582c2c42633d80e989b8204708b554f74b0eb1bbee6eaa59a1`.
G0, formats, sources `colony_lab/`, `sentinel_activity/`, `colony_pilot/` et les
trois hashes qualifiés restent inchangés. Rollback = revert source uniquement.

Aucun VPS/runtime/systemd/PPL/FIN/epoch/production/TESTNET/LIVE/exchange/secret,
replay/campagne, installation trust, naissance, recovery ou writer opérationnel.
#286 reste ACTIVE, accepted=false. Ni cette PR ni l'ajout du profil ne clôturent
3C ou l'étape3/7 ; leurs checklists et tout autre NE bloquant restent nécessaires.
