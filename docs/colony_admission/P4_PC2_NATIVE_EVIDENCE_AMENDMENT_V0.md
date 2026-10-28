# PC2/p1 — amendement de profil scientifique v0 (révision r2)

2026-10-28, America/Mexico_City.
**CONTRACT_FOR_DECISION / NOT_ADOPTED / SOURCE_ONLY / LAB_ONLY / NO_IMPLEMENTATION / PROFILE_BLOCKED.**
Mathieu autorise la préparation documentaire de cet amendement. Ce texte propose une
règle normative ; il ne l'adopte pas, n'active aucun profil, n'autorise ni code
d'activation, ni fusion, ni qualification de PC2.

Baseline revérifiée : `main@cc36e36e84b0496965302a46dc17973ce50fdf41`, tree
`62bcd5cff4e30ed1d3b34c80d28f9b2ca98360bd` (#518 fusionnée). Révision r1 :
`f7f2f5ed0e31af241b2041e7bf069ccce067b5fc` (tree `2fc7b56919b3529ac4557cd716c96822d7c3766c`,
baseline `5df6c6c2`). r2 conserve toutes les règles de r1, numérote les clauses et
ajoute les §10–§16 ; aucune exigence de r1 n'est affaiblie. Les différences r1→r2,
les options comparées et les preuves sont dans le
[dossier de décision](P4_PC2_NATIVE_EVIDENCE_AMENDMENT_DECISION_V0.md) (non normatif).

Références : [P1](ADMISSION_CONTRACT.md) §3.1, §3.5, §5, §11, §13 ;
[3B](P4_3B_ATTESTATIONS_AND_ANCESTRY_V0.md) §8–11 ;
[3C](P4_3C_POPULATION_AND_CEILINGS_V0.md) §5–9, §12–14 ;
[rapport natif pilote](../colony_lab/PILOT_DESCENDANT_REPORT.md) ;
[matrice PC2](P4_PC2_NATIVE_EVIDENCE_AMENDMENT_CASES_V0.json).

Convention : DOIT / NE DOIT PAS sont normatifs. Une clause est citée `Cn.m`.
Alias : S, E, P = fermetures de code du §3 ; q = qualification présentée ; s = son
statement ; qe/se = leurs enveloppes ; I = émetteur présent ; SR = revue scientifique
du §4 ; P1C, PC2, R8C, C9, R8Q = artefacts du §2 ; H(x) = §10.4.

## 0. Statut, priorité et entrée en vigueur

- **C0.1** Ce document est une proposition. Tant que C0.3 n'est pas rempli, il n'a
  aucun effet : PC2/p1 reste `SCIENTIFIC_PROFILE_UNSUPPORTED`/NE bloquant, p1 reste
  dans g0, accepted=false, #286 ACTIVE.
- **C0.2** P1 prime sur tout ce qui n'est pas explicitement dérogé ici. Les seules
  dérogations proposées sont : P1 §3.5 point 1 (copie d'une qualification
  historique) et 3B §8 alinéa PRESENT et §9.2, pour le seul couple profil/scope du
  §1. Aucune autre obligation P1/3A/3B/3C n'est levée ou assouplie.
- **C0.3** Entrée en vigueur, cumulative et dans cet ordre : (a) adoption explicite
  par Mathieu citant la PR, le commit complet, le tree et les SHA256 raw des
  documents de cet arbre ; (b) fusion gardée de cet arbre exact et CI du merge ;
  (c) implémentation selon C8.3–C8.4 avec tests exécutés, revues d'arbre exact et
  CI. Avant (c), les lecteurs existants gardent le refus (C0.1).
- **C0.4** Les bytes de P1 (`ADMISSION_CONTRACT.md`, `SCENARIOS_A0.json`) ne sont
  pas modifiés. Leur sémantique est étendue par cet amendement pour le seul profil
  §1 : le pin P1 seul ne certifie donc plus la règle complète ; un lecteur DOIT
  lire P1 + cet amendement identifiés par leurs SHA256 raw (dossier §5).

## 1. Problème et décision proposée

- **C1.1** Constat : P1 §3.5 décrit la copie présente d'une qualification
  historique (R8Q) ; 3B §8–9 n'en fournit que le profil `sentinel-r8-c9`. Le pilote
  n'a aucune qualification historique au format `colony-lab.qualification/0` ; PC2
  nomme trois fermetures (S, E, P) quand qualification/0 n'a que deux champs de
  code. 3B §9.2 refuse donc PC2/p1 (`SCIENTIFIC_PROFILE_UNSUPPORTED`).
- **C1.2** Profil fermé proposé : `pilot-p1-pc2-present-native-v0`. Il prend en
  charge exclusivement l'attestation présente (`PRESENT_ATTESTATION_OF_EXISTING_EVIDENCE`)
  de l'évidence native PC2, pour le pilote exact du §5, sous les critères p1 exacts.
  Il ne produit aucune qualification, aucun statement ou signature, et n'exécute
  aucune campagne.
- **C1.3** Extension explicite : pour ce seul profil, le record historique nommé par
  `historical_record_path`/`historical_record_sha256` est le record natif
  `colony-lab.pilot-evidence/0` PC2, et les champs scientifiques de q sont fixés par
  les §3–§4, non copiés d'une qualification historique. Ce n'est ni une
  qualification historique retrouvée ni un simple changement de hash.
- **C1.4** Sans la décision C0.3(a), conserver le refus ; NE PAS réinterpréter un
  champ de 3B pour rendre des tests verts.
- **C1.5** Après C0.3 seulement, cette exception remplace le refus de 3B §9.2/3C §13
  pour ce seul couple profil/scope. Les autres profils, R8 compris, gardent leurs
  règles. FRESH pour p1 reste refusé (C4.10).
- **C1.6** Aucun format persistant, kind, chemin D2/D3, clé K ou fichier P1 ne
  change (§10, §15).

## 2. Sources fermées et pins raw

- **C2.1** SHA256 raw = hash des bytes complets du fichier, distinct de H(JSON
  canonique) ; aucune normalisation (fin de ligne, BOM, espaces) n'est admise.

| Alias | Path checkout exact | SHA256 raw | Taille |
|---|---|---|---|
| P1C | `docs/colony_lab/PILOT_CRITERIA_P1.json` | `dcc3fe71909117ee2501ff3c5d2f8866f5343123929af40e06484a8ebf713ef7` | 7185 |
| PC2 | `docs/colony_lab/evidence/PC2_pilot_evidence.json` | `d706928e843275d58cab330426f6745db864194a86ef389fbed1dd93a7bc6b4d` | 18065 |
| R8C | `docs/colony_lab/SENTINEL_QUALIFICATION_CRITERIA_R8.json` | `22528f1629db5d565f54137e11e99f670c68152eb3127cbafabe5f1072ca990a` | 25866 |
| C9 | `docs/colony_lab/evidence/C9_sentinel_evidence.json` | `bc2f37df6bf7ab8138d326862906431154c07b298fb4b482db4fc6a0910f71cf` | 12241 |
| R8Q | `docs/colony_lab/SENTINEL_QUALIFICATION_RECORD_R8.json` | `d38656c56f59c7d950d3031ec969cfe6e6e126ed27f3ab2c83ab3d022518c578` | 742 |

- **C2.2** Le corpus scientifique du profil est exactement ces cinq artefacts. Le
  choix des chemins vient exclusivement du profil compilé, jamais d'un statement,
  d'un argument public ou du contenu d'un artefact.
- **C2.3** Un cache checkout commun peut contenir g0 et les sources d'autres profils ;
  le mapping détaché transmis au validateur PC2 est cette sélection exacte.
- **C2.4** NE remplacent aucun de ces artefacts : PC1/p0, un fichier renommé ou
  déplacé, un hash canonique à la place du pin raw, un record pilote synthétisé dans
  le checkout.
- **C2.5** Chaque artefact est décodé par le lecteur strict existant (§10.5) sans
  réécriture de ses bytes. Les cinq fichiers actuels passent ce lecteur.

## 3. Les trois fermetures de code : signification et liaisons

- **C3.1** Encodage : SHA256 de la concaténation, dans l'ordre trié des chemins
  POSIX relatifs uniques, de `path UTF-8 + NUL + SHA256(raw).digest()`. Sélection et
  caches exactement 3B §9.1–9.3 : tous les fichiers réguliers, pas seulement `*.py`.
  Aucun import des produits.

| Rôle | Signification | Racines | Pin |
|---|---|---|---|
| S — worker sujet | Code exécuté par le pilote : le pilote exécute le code de son parent (P1C.pilot.worker, PC2.not_claimed) | Racines subject 3B §9.1 : `colony_lab/__init__.py`, `colony_lab/workers/__init__.py`, `colony_lab/workers/sentinel.py`, `governance_tower/`, `observability/__init__.py`, `observability/event_center_contract.py`, `observability/runtime_service_contract.py`, `observability/storage_contract.py` | `2c926421416731dc629915067bcea472729e6785ec8dcb6e28f15ae7b41e4ec8` |
| E — évaluateur Sentinel | Laboratoire et évaluateur r8 qui ont produit C9 et que la campagne pilote réutilise (lineage, supervisor, prédicats r8) | `colony_lab/` et `sentinel_activity/` récursifs, moins l'ensemble S | `41b78971184809652dd1190dded49ab27d58c35c8a995351a47bf0f85756faa4` |
| P — évaluateur pilote | Code de campagne p1 qui a produit PC2 | `colony_pilot/` récursif, sans soustraction de E | `97fb6b0489976f8b003823c1536932ec10a1c7faa699ef6f6eb1bd4056238bc7` |

- **C3.2** Liaison S : `q.subject_code_sha256 = s.subject_code_sha256 =
  PC2.subject_code_sha256 = C9.subject.subject_code_sha256 = R8Q.subject_code_sha256
  = S recalculé = pin S`.
- **C3.3** Liaison P : `q.evaluator_code_sha256 = s.evaluator_code_sha256 =
  PC2.pilot_code_sha256 = P recalculé = pin P`. Le champ « évaluateur » de q désigne
  le code qui a produit l'évidence nommée par `q.evidence_sha256`, donc P.
- **C3.4** Liaison E : `PC2.sentinel_evaluator_code_sha256 = C9.evaluator_code_sha256
  = R8Q.evaluator_code_sha256 = E recalculé = pin E`. E n'a pas de champ dans q ; il
  est lié par les bytes PC2 (pin raw = `q.evidence_sha256`, signé par qe et se) et par
  le recalcul courant. E est obligatoire : son absence ou un E optionnel donne
  NE/`SCIENTIFIC_SOURCE_UNAVAILABLE`, sa divergence FAIL/`SCIENTIFIC_DIVERGENCE`.
- **C3.5** Aucun hash composite nouveau, champ supplémentaire, permutation ou
  substitution tolérée (E à la place de P, S à la place de P, etc.).
- **C3.6** Une modification de tout fichier de S, E ou P rend le profil divergent
  (cohérent avec P1 §11 : PC2 devient périmé) ; aucune mise à jour automatique des
  pins.

## 4. Qualification présente, statement, auteur et revue scientifique

- **C4.1** q garde les onze champs fermés de qualification/0 avec exactement :
  `agent_id` = `PC2.pilot.agent_id` = `1eb3baaf0bf1ec4ddc6559e128b8685e4a1d91da49f417ff33cc0fa196c0a22a` ;
  `agent_spec_id` = `PC2.pilot.agent_spec_id` = `660ec9a818fc3c3c41b432520dbcc881cc8c840cdb1a5a80318488ee0e22d986` ;
  `state` `QUALIFIED_SIMULATED` ; `scope` `SIMULATED_DETERMINISTIC` ;
  `criteria_sha256` = pin P1C ; `evidence_sha256` = pin raw PC2 ; S et P selon §3 ;
  `reviewer_kind`/`reviewer_id` = I (§11).
- **C4.2** q est un objet présenté et vérifié, jamais une sortie du diagnostic. Son
  state DOIT résulter du jugement présent de I sur le corpus exact, jamais d'une
  conversion automatique de `PC2.proposed_state`.
- **C4.3** Porte SR (rapport natif, « Before any pilot record ») : avant toute
  émission réelle de q, une revue indépendante de p1, PC2, `colony_pilot/` et des
  tests, avec mutants non vus par leur auteur, de type `EXTERNAL_REVIEW_PROCESS` ou
  `EXTERNAL_HUMAN`, et conclusion favorable justifiant le jugement. Son dossier DOIT
  identifier les artefacts (pins), le tree des tests revus, le reviewer, ses
  conclusions et ses limites.
- **C4.4** La porte SR conditionne la décision externe d'émettre q. Le diagnostic ne
  la certifie pas : les champs persistants ne portent pas ce dossier ; sa provenance
  reste NE, jamais PASS. On n'ajoute ni champ persistant ni sixième artefact
  implicite pour masquer cette limite.
- **C4.5** Ne valent PAS revue SR par le seul effet de cet amendement : la revue de
  cet amendement, la revue de son futur validateur, les tests LAB_TEST, les
  signatures, les revues d'agent de #484 (leur éventuelle prise en compte relève de
  SR/I et du dossier SR, voir dossier de décision §4). Une preuve SR manquante ne
  peut être ni fabriquée ni remplacée par une revue d'agent de l'implémentation.
- **C4.6** Ni `colony-review-481-r8`, ni l'auteur de la campagne PC2, ni un nom de
  reviewer inventé ne reçoit de clé ou de droit par cet amendement.
- **C4.7** Le statement garde tous les champs et types de 3B §8, avec les valeurs
  exigées :

| Champ de s | Valeur exigée |
|---|---|
| `scope` | `PRESENT_ATTESTATION_OF_EXISTING_EVIDENCE` uniquement |
| `historical_record_path` / `historical_record_sha256` | Path PC2 exact / pin raw PC2 exact : record natif d'évidence, pas qualification historique |
| `evidence` | Singleton exact `[{path: PC2, sha256: pin raw PC2}]`, ni R8Q ni C9 |
| `qualification_record_sha256` | H(q) complet (§10.4), ni le hash raw PC2 ni un record_hash interne |
| `campaign_replayed` / `campaign_evidence_sha256` | Littéral `false` / `null` |
| `historical_signature_claimed` | Littéral `false` |
| `subject_agent_id`/`subject_agent_spec_id`, `criteria_sha256`, `subject_code_sha256`, `evaluator_code_sha256` | Égaux à q et aux liaisons §3–§4 |
| `issuer_kind`/`issuer_id`, `issuer_root_version` | I, et version des DEUX enveloppes qe et se |
| `verified_at_source_sha` | hex40 déclaré selon 3B §8, non inféré de `PC2.checkout.git_head`, pas une preuve de provenance Git |

- **C4.8** Le singleton `evidence` ne dispense pas des quatre autres artefacts :
  ce sont des dépendances obligatoires du profil, acquises par le propriétaire.
- **C4.9** Les deux enveloppes sont vérifiées via `trust.classify_envelope` sur les
  objets acquis, sous root/pin/floor courants ; autorisations des kinds
  qualification et statement et exclusions de reviewer obligatoires. Une signature
  de s ne remplace pas celle de q, ni réciproquement.
- **C4.10** `FRESH_CAMPAIGN` sous critères p1 reste NE bloquant
  `SCIENTIFIC_PROFILE_UNSUPPORTED`. Les champs DOIVENT d'abord satisfaire la
  grammaire FRESH générale ; une incohérence prouvée reste FAIL/`STATEMENT_INVALID`.
  Un vieux PC2, un booléen true, un SHA récent ou une signature récente ne démontre
  pas une campagne nouvelle. Un profil FRESH exige un autre contrat ; aucune
  campagne n'est lancée ici.

## 5. Identité et contexte de lignée acquis

- **C5.1** La preuve exige les records/specs acquis du pilote sujet ET de son parent
  Sentinel, issus du propriétaire du snapshot courant, jamais d'arguments publics
  `agent_id`/spec/permissions choisis par l'appelant. Contexte absent :
  NE/`SCIENTIFIC_SOURCE_UNAVAILABLE` ; contexte stable contradictoire :
  FAIL/`SCIENTIFIC_DIVERGENCE`. Une ancienne évidence ne fabrique ni foyer, ni spec,
  ni COMMITTED, ni droit de filiation.
- **C5.2** Valider l'identité A1 et `lineage.verify_record` sur ces objets avant
  crypto, avec la branche structurelle complète de 3B/3C. Comparer le
  `spec_artifact_hash` complet, pas seulement `agent_spec_id`.
- **C5.3** Comparaisons structurées par bytes canoniques, sans égalité Python qui
  confond bool/int : générations int strict (pas bool), `inherits_parent_memory`
  littéral false, budgets int stricts ; aucune coercition.

| Objet | Exigences liées à PC2, C9 et P1C |
|---|---|
| Sentinel parent/fondateur | ID `4279e165b2706c088840d1cdc4ebe3efa76c2ea220bc948a8336c4343eb23173`, spec ID `b74ab69619acdb3747edd64affbc6d5ae3c99f32249c49bf4288e5786836d4ed`, spec artifact `fd130c1bcd6c10a13b9cab3cbcd4d8e78b5b21a388251523b298dbc14927b5a6`, FOUNDER génération 0 ; permissions exactes `DIAGNOSTIC_PRODUCE`, `GOVERNED_ARTIFACT_READ` |
| Pilote sujet de q | ID/spec C4.1, spec artifact `3eb0786822165e7f7fd60b1f8bb8d84bef4c803e90ac52bcbff08e093cbb4dcc`, DESCENDANT génération 1, parent/fondateur = Sentinel exact, même lineage_id ; base spec parent exacte, declared_diff exact `[purpose]` et spec_diff recalculé ; permissions exactes `[DIAGNOSTIC_PRODUCE]` |
| Les deux records | Budget de six entiers stricts : cpu_seconds 30, wall_seconds 60, memory_bytes 1073741824, output_bytes 1048576, runs 10, journal_events 100 ; mémoire `OWN_J01_JOURNAL` sans héritage, credentials NONE, registry NON_DEPLOYED/NOT_AVAILABLE, operational_authority DENIED |

- **C5.4** Ces budgets sont ceux de la campagne épinglée (`qualification.BUDGET`
  dans la fermeture E), pas un budget runtime observé. Une allocation courante
  différente, même plus basse, n'est pas couverte par ce profil exact. Ne pas ouvrir
  usage.json, SQLite ou la mémoire du parent pour « prouver » ces propriétés.
  L'absence d'héritage est la propriété déclarée du record validé, pas une preuve
  de séparation physique actuelle.
- **C5.5** Deux qualifications distinctes : `birth_qualification.json` du pilote
  concerne Sentinel (qualification du parent à la naissance) ; q PC2 concerne le
  pilote lui-même, par exemple présenté comme parent d'un autre candidat. NE JAMAIS
  remplacer la birth qualification du pilote par q, re-signer son ancienne
  naissance ou attribuer PC2 à un nouveau child.
- **C5.6** Qualifications, statements et copies restent dédupliqués par K incluant
  H(record complet), sans fusion des sujets Sentinel/pilote ni de deux q du même sujet.
- **C5.7** Le profil ne s'étend ni à une copie du pilote d'un autre ID/spec, ni à une
  génération 2. Plafonds, générations, diff, permissions de tout candidat et preuves
  COMMITTED/D1/D2/D3 restent des comparaisons séparées inchangées.

## 6. Bindings internes de l'évidence et dépendance R8

En plus des pins raw et des fermetures, exiger :

- **C6.1** P1C : `criteria_schema` `colony-lab.pilot-criteria/0`, `revision` p1,
  `scope` SIMULATED_DETERMINISTIC ; `parent.criteria_revision` r8,
  `parent.record_file`/`parent.evidence_file`, résolus sous `docs/colony_lab/`,
  égaux aux paths R8Q/C9 du §2.
- **C6.2** PC2 : `evidence_schema` `colony-lab.pilot-evidence/0`,
  `criteria_revision` p1, `criteria_status` CURRENT, `criteria_sha256` = pin P1C =
  q.criteria_sha256 ; `scope` = q.scope ; `proposed_state` PROPOSED_QUALIFIED_SIMULATED ;
  `failure_reasons` et `code_irregular` vides ; `deterministic_across_fresh_labs`,
  `evaluator_runtime.source_only`, `sandbox_view.matches_subject` littéraux true ;
  `environment.sandbox` VERIFIED.
- **C6.3** PC2.parent : ID/spec = Sentinel C5.3 ; `matches_current_code` true,
  `mismatched` vide ; `record_sha256` = pin raw R8Q = SHA256(raw R8Q acquis) ;
  `parent.qualification` = R8Q décodé **complet**, reviewer historique inclus. Ce
  reviewer n'est ni émetteur présent ni authentifié.
- **C6.4** R8Q/C9/R8C : R8Q id/spec = C9.subject id/spec = Sentinel ;
  R8Q.criteria_sha256 = pin R8C ; R8Q.evidence_sha256 = pin raw C9 = SHA256(raw C9) ;
  S/E §3 ; state QUALIFIED_SIMULATED, scope SIMULATED_DETERMINISTIC. C9 : critères
  r8/CURRENT, pin R8C, PROPOSED_QUALIFIED_SIMULATED, `failure_reasons`/`code_irregular`
  vides, `deterministic_across_fresh_labs`, `golden_subject_code_matches`,
  `evaluator_runtime.source_only` littéraux true (3B §9.1). NE PAS substituer la
  règle PRESENT R8 (copie d'un q courant) à cette dépendance historique raw.
- **C6.5** PC2.pilot ID/spec/artifact/génération/permissions/diff = contexte §5 ;
  P1C.pilot permissions/diff, identité nominale et purpose concordent avec le spec
  acquis ; specs parent/pilote vérifiés A1 ; `PC2.not_claimed` = `P1C.not_claimed`.
- **C6.6** PC2.rounds : exactement deux listes identiques, chacune contenant les 28
  IDs dans l'ordre B01..B12 de P1C.birth_trials, Q00..Q14 de R8C.trials, puis P01 de
  P1C.permission_trials ; chaque entrée a `passed` littéral true,
  `failed_predicates` vide et `facts_sha256` hex64. Ni doublon, ni essai omis, ni
  27/28. Le pin raw lie aussi codes/kinds/status et tous les autres champs natifs.
- **C6.7** Ces propriétés décrivent les claims du corpus épinglé ; aucun run, import
  de campaign, replay de prédicats ni qualification du contrôleur n'en découle. Les
  28×2 succès natifs ne sont pas des tests exécutés par cet amendement.

## 7. Acquisition, limites et propagation

- **C7.1** Pas de nouvelle API publique, configuration de chemin PC2, override de
  profil ou liste required fournie par l'appelant. Le dispatch interne sélectionne
  le profil selon C10.2. Il reçoit des bytes acquis, un contexte immuable et S/E/P
  calculés depuis les inventaires complets ; pas d'appel public imbriqué ni de
  seconde acquisition.
- **C7.2** Même propriétaire L1→L2, cache d'artefacts et de fermetures, union U/ledger
  et vérification de sortie. Fichiers partagés avec R8 lus une fois ; aucune
  inspection ledger spécifique PC2.
- **C7.3** Limites 3B/3C inchangées et cumulées : checkout 32 MiB, 16 MiB/fichier,
  4096 fichiers, 8192 entrées ; 4096 FD globaux ; contenu privé 32 MiB ; records
  64 KiB ; enveloppes/statements 16 KiB ; items policy/hard et graphe K/N/P/F avant
  signatures. Pas de budget par profil.
- **C7.4** Acquisition manquante, IO, limite, mutation ou close échoué invalide tout
  le payload selon les lecteurs existants ; pas de sous-ensemble de fermeture.
- **C7.5** Même après PASS scientifique, toutes les autres propriétés 3B/3C restent
  requises pour leurs agrégats (§14).

## 8. Plan d'implémentation et portes

- **C8.1** Cette PR documentaire séparée : contrat, matrice, dossier. Revue
  d'agent indépendante de l'arbre exact, corrections, re-revue ; puis décision
  explicite de Mathieu (C0.3(a)). Aucun code d'activation avant.
- **C8.2** CI documentaire exacte : check-runs filter=all et workflows head_sha tous
  événements/statuts paginés ; logs des échecs/skips, revues/threads/ruleset/
  composition/pins ; fusion gardée par expected_head_sha ; CI complète du merge.
- **C8.3** Petite PR SOURCE_ONLY de validateurs internes et tests adversariaux sur
  fixtures LAB_TEST détachées (kinds/auteurs/signatures de test, aucune identité
  humaine ou GitHub imitée). Tests issus de la matrice, lien cas→test exécuté,
  mutants des trois bindings ; revue indépendante de l'arbre exact. Ne pas
  revendiquer la matrice exécutée à partir de son nombre de cas.
- **C8.4** Intégration acquisition/projection isolée, après les prérequis du
  propriétaire global 3C ; pas d'API publique positive partielle. Tester R8 seul,
  PC2 seul et mélange, limites partagées, copies, close et `python -O` séquentiels
  sans bytecode. Revue exacte, CI HEAD, fusion gardée et CI merge à chaque livraison.
- **C8.5** Après C8.3–C8.4, le support logiciel du profil peut être déclaré
  implémenté. Une attestation réelle exige encore SR (C4.3), I identifié et
  autorisé, et ses deux enveloppes valides ; leur absence reste un blocage. La
  validation du contrat et les tests n'autorisent pas à créer ou installer ces
  preuves.
- **C8.6** Pendant C8.1–C8.4 : PC2/p1 reste `SCIENTIFIC_PROFILE_UNSUPPORTED`/NE
  bloquant dans les lecteurs existants ; p1 reste dans g0. Une revue d'agent du code
  n'est ni une approbation GitHub d'identité distincte ni une attestation du pilote.

## 9. Préservation et clôture bornée

- **C9.1** Pins P1 intacts : `ADMISSION_CONTRACT.md`
  `e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd` ;
  `SCENARIOS_A0.json` `4e518bfec6faaa582c2c42633d80e989b8204708b554f74b0eb1bbee6eaa59a1`
  (bytes inchangés ; sémantique étendue selon C0.4).
- **C9.2** g0, formats, sources `colony_lab/`, `sentinel_activity/`, `colony_pilot/`,
  `colony_admission/` et les trois fermetures restent inchangés. Rollback = revert
  documentaire uniquement.
- **C9.3** Aucun VPS/runtime/systemd/PPL/FIN/epoch/production/TESTNET/LIVE/exchange/
  secret, replay/campagne, installation trust, naissance, recovery ou writer
  opérationnel. #286 ACTIVE, accepted=false.
- **C9.4** Ni cette PR, ni son adoption, ni l'ajout du profil ne qualifient PC2 ou ne
  clôturent 3C ou l'étape 3/7 ; leurs checklists et tout autre NE bloquant restent.

## 10. Format, version et canonicalisation

- **C10.1** Aucun format persistant nouveau : q = `colony-lab.qualification/0` (11
  champs, `lineage.check_qualification`) ; s = `colony-admission.attestation-statement/0`
  (18 champs, `STATEMENT_FIELDS`) ; enveloppes trust (`ENVELOPE_FIELDS`) inchangées.
  Tout champ en plus ou en moins : FAIL/`STATEMENT_INVALID`.
- **C10.2** Sélection du profil, déterministe, sans champ persistant de profil :
  1. la grammaire générale de s (3B §8) est évaluée indépendamment du profil ; son
     échec donne FAIL/`STATEMENT_INVALID`, qui domine tout NE de sélection (C13.1) ;
  2. `q.criteria_sha256` = pin R8C ⇒ profil `sentinel-r8-c9` inchangé ;
  3. `q.criteria_sha256` = pin P1C et `s.scope` = PRESENT ⇒ ce profil ;
  4. `q.criteria_sha256` = pin P1C et `s.scope` = FRESH ⇒ NE/`SCIENTIFIC_PROFILE_UNSUPPORTED` ;
  5. tout autre critère ⇒ NE/`SCIENTIFIC_PROFILE_UNSUPPORTED`.
  Aucun autre indice (path, nom de fichier, issuer, contenu) ne sélectionne un profil.
- **C10.3** Version : l'identifiant `pilot-p1-pc2-present-native-v0` est une
  constante de contrat et de code, jamais persistée. Tout changement d'une liaison
  exige un nouvel identifiant (`…-v1`), une nouvelle adoption et une nouvelle
  matrice. Aucun verdict n'est persisté par le diagnostic : un couple q/s conforme à
  v0 est réévalué à chaque appel et peut devenir FAIL ou NE sous une version
  ultérieure ; cette conséquence est déclarée, sans migration.
- **C10.4** H(x) = SHA256 de `formats.canonical(x)` : JSON UTF-8, clés triées,
  séparateurs `,` et `:`, `ensure_ascii=False`, `allow_nan=False`. H s'applique à q
  (`s.qualification_record_sha256`, `qe.record_sha256`), à s (`se.record_sha256`) et
  aux comparaisons structurées. Les pins raw (§2) ne sont jamais remplacés par H.
- **C10.5** Lecture stricte (`record_loads`) : UTF-8, clés en double refusées,
  flottants, NaN et Infinity refusés, entiers bornés, profondeur bornée ; artefacts,
  records et q ≤ 64 KiB au décodage ; s et enveloppes ≤ 16 KiB (3B §10). Booleans
  littéraux, entiers stricts non-bool, hex64/hex40 lowercase.

## 11. Rôles, identités et autorités

**C11.0** Le tableau suivant est normatif.

| Rôle | Qui | Autorité dans ce profil | Ce que son acte prouve |
|---|---|---|---|
| Opérateur | Mathieu | Adopter l'amendement ; autoriser séparément l'installation d'un issuer et toute émission réelle | Décision de gouvernance, hors scanner |
| Émetteur I | Issuer identifié de la racine LAB_TEST courante, `issuer_kind` ∈ {EXTERNAL_HUMAN, EXTERNAL_REVIEW_PROCESS}, autorisé pour les kinds qualification/0 ET statement/0 | Auteur de q (`reviewer_*`) et de s (`issuer_*`) | Que I déclare ces bytes, sous sa clé, maintenant |
| Signataire | La clé de I nommée par qe et se, valide sous `root_version` déclaré | Aucune autre que celle de I | Intégrité et autorisation des bytes ; pas la revue |
| Reviewer scientifique SR | Identifié dans le dossier SR ; peut être I ou un tiers dont I reprend la conclusion | Aucune clé conférée par cet amendement | Jugement scientifique, hors preuve du scanner |
| Reviewer d'agent | Revue de contrat/validateur | Aucune | Conformité d'un arbre exact au contrat |
| Acteurs historiques | Auteur de la campagne PC2, `colony-review-481-r8` | Aucune autorité présente | Rien d'authentifié |

- **C11.1** Auteur = signataire : `q.reviewer_kind/id` = `s.issuer_kind/id` = émetteur
  de qe = émetteur de se ; `qe.root_version` = `se.root_version` = `s.issuer_root_version`.
  Toute divergence : FAIL/`STATEMENT_INVALID` ou refus trust.
- **C11.2** Exclusions vérifiables : I ≠ `colony-review-481-r8` ; I ne contient pas le
  préfixe 16 de l'ID du pilote, de Sentinel/fondateur ou du candidat (règle lineage) ;
  FAIL/`STATEMENT_INVALID` ou `SELF_QUALIFICATION_DENIED`.
- **C11.3** Exclusion déclarative non vérifiable par le scanner : SR NE DOIT PAS être
  l'auteur de la campagne PC2 ni de `colony_pilot/` ; elle est portée par le dossier
  SR (C4.3) et reste NE dans le diagnostic.
- **C11.4** L'adoption par Mathieu ne crée ni issuer, ni clé, ni autorisation
  d'émettre ; l'installation d'une racine et toute émission sont des portes
  distinctes.

## 12. Portées temporelles et versions

**C12.0** Le tableau suivant est normatif.

| Élément | Portée | Statut dans le diagnostic |
|---|---|---|
| Contenu de PC2 (28×2, environnement, `checkout.git_head` 5790976a, Python 3.11.17) | Historique déclaré | Intégrité par pin raw seulement ; non authentifié ; ni date ni auteur attestés |
| R8Q, C9 | Historiques déclarés | Idem ; reviewer historique non authentifié |
| Égalité des fermetures S/E/P aux pins | Courante | Recalculée à chaque appel ; vaut pour les bytes acquis à cet appel |
| Signatures qe/se | Courante | Valides sous la racine courante à cet appel ; date d'émission non attestée (pas d'horloge fiable) |
| `verified_at_source_sha` | Déclarée | Grammaire seule ; `source_revision_provenance` NE |
| Exécution de SR et sa date | Externe | NE, jamais PASS |
| Versions Python/plateforme de la campagne | Historique déclarée | Non attestées ; non recomparées à l'environnement courant |

- **C12.1** Aucune clause n'affirme que le pilote était qualifié à une date passée.
  q est une déclaration présente ; elle ne qualifie rétroactivement ni une naissance,
  ni un PREPARED, ni une décision antérieure à son existence (§16).
- **C12.2** Aucune expiration n'est définie ; la validité cesse par révocation,
  divergence de fermeture, divergence de pin ou nouvelle version (C10.3).

## 13. Absence, ambiguïté, divergence, profil inconnu, révocation, invalidation

**C13.0** Le tableau suivant est normatif ; une q signée dont `state` n'est pas
`QUALIFIED_SIMULATED` (par exemple FAILED ou REVOKED) n'est jamais PASS.

| Situation | Verdict scientifique / code | Effet de branche |
|---|---|---|
| Profil non adopté ou non implémenté | NE / `SCIENTIFIC_PROFILE_UNSUPPORTED` | Bloquant |
| Critère inconnu ou p1 en FRESH | NE / `SCIENTIFIC_PROFILE_UNSUPPORTED` | Bloquant |
| q, s, qe ou se absent | NE / `EVIDENCE_NOT_STORED` ou `ATTESTATION_MISSING` | Bloquant |
| Artefact du §2 ou contexte §5 absent ; fermeture indisponible | NE / `SCIENTIFIC_SOURCE_UNAVAILABLE` | Bloquant |
| Ambiguïté : plusieurs q distinctes du même pilote, ou contenu d'un path qui change pendant l'acquisition | Chaque q est un item distinct (K inclut H) ; seule la q figée/présentée pour la décision est la qualification de décision, chaque copie requise est vérifiée ; aucune fusion ni choix silencieux. Changement de contenu : `SOURCE_CHANGED`, payload effacé | Pas de PASS sur un choix implicite |
| Grammaire ou auteur/sujet/scope de s incohérent | FAIL / `STATEMENT_INVALID` | Refus de preuve |
| Pin raw, fermeture, binding §3–§6 divergent | FAIL / `SCIENTIFIC_DIVERGENCE` | Refus de preuve |
| Lien, type irrégulier, nom interdit dans une fermeture | FAIL / `SOURCE_CODE_IRREGULAR` ou `SOURCE_PATH_FORBIDDEN` | Refus |
| Limite, mutation, IO pendant acquisition | Codes 3A/3B (`SOURCE_LIMIT`, `SOURCE_CHANGED`, …), payload effacé | Pas de PASS |
| Signature invalide | Refus trust (codes existants) | Pas de PASS trust |
| Révocation authentique de clé ou d'enveloppe de q/s | Trust ≠ PASS ; règles P1 §5.2 et SUSPENDED 3C | Filiation interdite ; jamais PASS |
| Racine courante indisponible | `TRUST_CURRENT_UNAVAILABLE` | Bloquant |
| Modification ultérieure d'un fichier S/E/P ou d'un artefact | FAIL / `SCIENTIFIC_DIVERGENCE` aux appels suivants | Invalidation sans écriture |

- **C13.1** FAIL prouvé domine NE sur un même agrégat ; une révocation ou une
  absence n'est jamais convertie en PASS ; trust et science restent des verdicts
  séparés.
- **C13.2** Aucune invalidation n'écrit, ne supprime ni ne modifie un record,
  une enveloppe ou un artefact ; elle est recalculée.

## 14. Conséquences sur les verdicts et les blocages

**C14.0** Le tableau suivant est normatif.

| État | Science PC2 | Agrégats de branche | p1/g0 | Étape 3/7 |
|---|---|---|---|---|
| Aujourd'hui, ou amendement fusionné sans code | NE `SCIENTIFIC_PROFILE_UNSUPPORTED` | NE bloquant | p1 dans g0, inchangé | Bloquée (limite PC2 citée) |
| Code intégré, aucune q/s réelle | NE (`EVIDENCE_NOT_STORED`/`ATTESTATION_MISSING`) en lab réel ; PASS seulement sur fixtures LAB_TEST | NE bloquant en lab réel | Inchangé | La limite « profil non supporté » peut sortir de la checklist si C8.3–C8.4 sont remplies ; les autres items restent |
| q/s réelles valides, SR documentée hors scanner | PASS des comparaisons du profil | PASS seulement si toutes les autres propriétés 3B/3C passent | Inchangé | Inchangé par ce seul fait |

- **C14.1** Un PASS scientifique PC2 n'est ni une admission, ni une autorisation de
  naissance, ni la qualification du contrôleur, ni une provenance PASS.
- **C14.2** Un PASS ne transforme pas un foyer terminal, une preuve COMMITTED
  remplacée ou un OWN incomplet en admis ; genuine-but-revoked interdit la filiation ;
  le comptage conservateur 3C est inchangé.
- **C14.3** accepted=false permanent ; autorité, durabilité, recovery et provenance
  restent NE. Aucun déplacement automatique de p1 hors de g0.

## 15. Compatibilité

- **C15.1** Lecteurs actuels (main@cc36e36e) : un couple q/s PC2 y donne
  NE/`SCIENTIFIC_PROFILE_UNSUPPORTED` ; aucun ancien lecteur ne produit de faux PASS.
- **C15.2** Le profil `sentinel-r8-c9` et la sémantique de copie P1 §3.5 pour R8 sont
  inchangés ; un q/s R8 valide l'est encore après implémentation.
- **C15.3** PC1/p0 n'a aucun profil (critère hors g0) : NE `SCIENTIFIC_PROFILE_UNSUPPORTED`.
- **C15.4** `birth_qualification.json`, les items DECISION/POPULATION, K, les noms de
  stockage `admission-envelopes/` et les formats d'opération sont inchangés.
- **C15.5** Les phrases de 3B §9.2 et 3C §13 qui déclarent PC2/p1 non supporté
  restent exactes jusqu'à C8.4 ; la PR d'intégration DOIT les mettre à jour par un
  texte relu (proposition au dossier §5), sans toucher P1.
- **C15.6** Un futur format à trois champs de code (qualification/1) serait un autre
  profil sous un autre contrat ; cet amendement ne le préjuge pas.

## 16. Historique sans qualification rétroactive ; trois actes distincts

- **C16.1** PC2 reste une évidence historique au state `PROPOSED_QUALIFIED_SIMULATED`.
  Aucun fichier qualification/0 historique du pilote n'est créé, antidaté, déduit ou
  ajouté au checkout ; `historical_signature_claimed` reste false.
- **C16.2** La phrase du rapport natif « Until then the pilot is **not qualified** »
  reste vraie pour toute période sans q valide. Une q ultérieure ne modifie aucun
  item figé d'une opération antérieure.
- **C16.3** Trois actes, aucun ne remplace automatiquement les deux autres :

| Acte | Prouve | Ne prouve pas |
|---|---|---|
| Revue de code (agent ou humain) | Qu'un arbre exact implémente le contrat | Le jugement scientifique ; l'identité d'un émetteur |
| Signature cryptographique (qe, se) | Intégrité et autorisation des bytes par la clé de I sous la racine | Qu'une revue a eu lieu ; sa qualité ; une date |
| Revue scientifique SR | Le jugement sur p1/PC2/`colony_pilot`/tests avec mutants non vus | Que le code du validateur est correct ; que q a été signée |
