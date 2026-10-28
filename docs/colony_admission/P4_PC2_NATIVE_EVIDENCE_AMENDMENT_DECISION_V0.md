# PC2/p1 — dossier de décision de l'amendement (non normatif)

2026-10-28. **DECISION_DOSSIER / NOT_ADOPTED / SOURCE_ONLY / NO_IMPLEMENTATION.**
Ce dossier accompagne le [contrat r2](P4_PC2_NATIVE_EVIDENCE_AMENDMENT_V0.md) et sa
[matrice](P4_PC2_NATIVE_EVIDENCE_AMENDMENT_CASES_V0.json). Il n'a aucune force normative :
en cas d'écart, le contrat prime, et P1 prime sur le contrat (C0.2). Il ne vaut ni
adoption, ni revue scientifique, ni qualification de PC2.

Baseline : `main@cc36e36e84b0496965302a46dc17973ce50fdf41`, tree
`62bcd5cff4e30ed1d3b34c80d28f9b2ca98360bd`. PR #510 (Draft), branche
`docs/pc2-profile-contract-20261026`. Le commit et le tree soumis sont cités dans le
commentaire de PR de soumission, pas ici (un document ne peut pas contenir le hash
de l'arbre qui le contient).

## 1. Ce qui est demandé à Mathieu

Une seule décision : adopter, ou non, la règle « attestation présente de l'évidence
native PC2 » (contrat §1 et C10.2), avec la correspondance S → `subject_code_sha256`,
P → `evaluator_code_sha256`, E lié par les bytes de PC2. L'adoption autoriserait
seulement la fusion documentaire puis de petites PR d'implémentation ; elle
n'autorise ni émission de q, ni installation d'émetteur, ni naissance, ni sortie de
p1 de g0, ni clôture de l'étape 3/7.

## 2. Faits vérifiés, classés

Classes : **OBS** = donnée historique observée dans un artefact épinglé ;
**CUR** = preuve actuelle recalculée le 2026-10-28 sur `main@cc36e36e` ;
**INT** = interprétation proposée ; **ABS** = information absente.

| # | Fait | Classe | Source et vérification |
|---|---|---|---|
| F1 | PC2 rapporte deux séries de 28 réussites (`passed` true, `failed_predicates` vides), listes identiques, ordre B01..B12, Q00..Q14, P01 | OBS | `PC2_pilot_evidence.json` lu ; ordre comparé à P1C.birth_trials + R8C.trials + P1C.permission_trials |
| F2 | Trois hashes distincts : S `2c926421…` (worker Sentinel), E `41b78971…` (évaluateur Sentinel), P `97fb6b04…` (pilote) | OBS + CUR | Champs PC2 ; recalcul `qualification.subject_code_sha256`, `evaluator_code_sha256`, `campaign.pilot_code_sha256` sur une copie `git archive` de main : égaux ; `code_irregular` vide |
| F3 | qualification/0 n'a que deux champs de code (`subject_code_sha256`, `evaluator_code_sha256`) parmi onze champs | CUR | `colony_lab/lineage.py` `check_qualification` |
| F4 | Aucune qualification/0 historique du pilote n'est démontrée | ABS | Seuls fichiers de main citant l'ID pilote `1eb3baaf…` : rapport natif, PC1, PC2, `tests/colony_pilot/test_campaign.py` ; rapport natif : « Until then the pilot is **not qualified** » |
| F5 | PC2/p1 reste `SCIENTIFIC_PROFILE_UNSUPPORTED`/NE bloquant ; p1 est dans g0 | CUR | `_attestation_statement.py` (`scientific_bindings` : critère ≠ pin R8 ⇒ ce code) ; `POLICY_G0.json` `admissible_parent_criteria_sha256` contient le pin P1C ; 3B §9.2, 3C §13 |
| F6 | La proposition r1 prévoyait une exception explicite à P1 §3.5 pour un record natif PC2/PRESENT, S/P dans q et E séparé | OBS | #510 @ `f7f2f5ed`, contrat r1 §1, §3 |
| F7 | Les cinq pins raw (P1C, PC2, R8C, C9, R8Q) et les pins P1 (`e8a125bd…`, `4e518bfe…`) sont inchangés à main@cc36e36e | CUR | `sha256sum` des bytes de main |
| F8 | Les cinq artefacts passent le lecteur strict `record_loads` (tailles 742–25866 bytes) | CUR | Exécution locale |
| F9 | PC2.parent.qualification est égal à R8Q décodé complet ; PC2.not_claimed = P1C.not_claimed | CUR (sur OBS) | Comparaison locale |
| F10 | Le rapport natif exige, avant tout record pilote, une revue indépendante de p1, PC2, `colony_pilot/` et des tests avec mutants non vus, de type EXTERNAL_*, et précise qu'un record pilote devrait nommer le hash de l'évaluateur pilote | OBS | `PILOT_DESCENDANT_REPORT.md` « Before any pilot record » |
| F11 | #484 a eu 13 revues d'agent lecture seule ; la 13e (`3121d3d8`) est favorable sous les règles A/B, dont 49 mutants non divulgués | OBS | Rapport natif ; `/mnt/project-files/governance-tower/COLONY_484_REVUE_INDEPENDANTE_3121d3d8.md` |
| F12 | Aucune racine trust, aucun issuer, aucune q/s/enveloppe réelle pour le pilote n'existe dans le dépôt | ABS | Aucun record pilote émis (rapport natif) ; trust LAB_TEST seulement |
| F13 | La date d'exécution de la campagne PC2 et l'identité de son auteur ne sont attestées par aucune signature | ABS | PC2 porte `checkout.git_head` 5790976a, pas d'horodatage signé |
| F14 | #286 est ouverte, `ACTIVE_BURN_IN_IMMUTABILITY_GUARD` | CUR | Lecture GitHub le 2026-10-28 |

Interprétations proposées (INT) : P est « l'évaluateur » au sens de qualification/0
pour PC2 (§6) ; E reste une dépendance obligatoire liée par PC2 ; l'attestation
présente d'une évidence native est admissible si elle est déclarée comme telle.
Le rapport natif de succès (F1) n'est pas transformé en qualification actuelle :
PC2 reste `PROPOSED_QUALIFIED_SIMULATED` et non signé.

## 3. Problème normatif exact

1. P1 §3.5 point 1 définit la q présente comme une **copie** d'une qualification
   historique existante (R8Q), au reviewer près ; la phrase finale l'étend à « every
   qualification the controller uses ». Pour le pilote, il n'y a rien à copier (F4).
2. 3B §8 (alinéa PRESENT) exige un record historique du profil comparable champ à
   champ à q, et 3B §9.2 refuse explicitement de choisir lequel des trois hashes
   PC2 irait dans `subject_code_sha256` : il renvoie à un amendement.
3. qualification/0 ne peut nommer que deux fermetures (F3), alors que la science
   PC2 dépend de trois (F2) et que le rapport natif veut que P soit nommé (F10).
4. g0 admet p1 comme critère parent (F5) : la capacité de lecture est donc
   incomplète tant que ce profil n'est pas défini, et la limite est citée comme
   bloquante dans la checklist de l'étape 3/7 (3C §13).

Le problème n'est pas l'absence de succès natifs ; c'est l'absence d'une règle qui
dise comment une attestation présente se lie à une évidence native sans
qualification historique, et quel hash va dans quel champ.

## 4. Preuves disponibles

| Preuve | État | Portée |
|---|---|---|
| Cinq artefacts épinglés (F7–F9) | Disponibles | Intégrité par pins raw ; contenu historique non authentifié |
| Fermetures S/E/P courantes (F2) | Disponibles, recalculées | Égalité aux pins à main@cc36e36e |
| Rapport natif et 13 revues #484 (F10–F11) | Disponibles | Revues d'agent du code et de la campagne, favorable à la 13e. Classement : **candidates non établies** comme revue SR (C4.3). Selon la note de la revue 13, elles ont été rendues par un sous-agent en lecture seule et sauvegardées sous forme condensée par l'auteur de la PR ; aucun reviewer EXTERNAL_* identifié dans une racine trust ; le rapport natif garde « Until then the pilot is not qualified ». La revue 13 déclare n'autoriser « ni … record pilote » et laissait ouverte la condition « suite complète, gate ruff et campagne témoin par un relecteur disposant d'une copie inscriptible ». Cette condition a été déclarée close par une vérification `644aab6f` (`/mnt/project-files/governance-tower/COLONY_484_VERIFICATION_INSCRIPTIBLE_644aab6f.md` : suite, ruff et campagne témoin 28/28 ×2 CONFORMES), qui est elle aussi un rapport de sous-agent condensé par l'auteur de la PR, hors arbre, preuve locale sans CI revérifiée ; `colony_pilot/` est inchangé de `644aab6f` à `cc36e36e`. Leur éventuelle prise en compte est un jugement de SR/I documenté dans le dossier SR, pas une conséquence de cet amendement (C4.5) |
| Revue d'agent de r1 (`/root/review_pc2_contract`, arbre `2fc7b569`) | Disponible (déclarée dans #510) | Revue du texte r1 seulement ; ne couvre pas r2 |
| Matrice r1 (54 cas) | Disponible, vérifiée | 54 IDs uniques ; repris sans changement de given/when/then |

## 5. Différences exactes avec le contrat actuel (proposées, NON appliquées)

Aucun de ces textes n'est modifié par cette PR. Les blocs montrent la lecture
qu'imposerait l'adoption (P1) ou le texte que la PR d'intégration devrait proposer
(3B/3C, C15.5).

**P1 `ADMISSION_CONTRACT.md` §3.5 — bytes et pin `e8a125bd…` inchangés, sémantique
étendue par superposition (C0.4). C'est la première extension sémantique de P1 par
un document séparé : AMENDMENT_3 (registrar) et AMENDMENT_4 (trust) amendent des
contrats dépendants prévus par P1 §12 et citent ses pins sans étendre sa sémantique ;
ils ne sont donc pas un précédent pour cette extension. Dérogations (1)–(3) de C0.2 :**

```diff
 1. A **new** qualification record `colony-lab.qualification/0`, with R8's `agent_id`, ...
    `evaluator_code_sha256`, and `reviewer_kind`/`reviewer_id` equal to the issuer's kind and id ...
+   [Amendement PC2, profil pilot-p1-pc2-present-native-v0 seulement] There is no historical
+   qualification to copy. The new record has PC2.pilot's agent_id/agent_spec_id, state
+   QUALIFIED_SIMULATED, scope SIMULATED_DETERMINISTIC, criteria_sha256 = raw pin of
+   PILOT_CRITERIA_P1.json, evidence_sha256 = raw pin of PC2, subject_code_sha256 = S,
+   evaluator_code_sha256 = P; E is bound through the PC2 bytes (contrat §3).
 2. ... `historical_record_path`, `historical_record_sha256` (R8); `evidence` (... C9) ...
+   [PC2] historical_record_path/sha256 = the native PC2 evidence record; evidence = [PC2].
 The same procedure applies to every qualification the controller uses.
+   [PC2] except that the "historical record" is native evidence, not a qualification;
+   FRESH_CAMPAIGN under p1 stays unsupported.
```

**3B `P4_3B_ATTESTATIONS_AND_ANCESTRY_V0.md` §8 alinéa PRESENT et §9.2 (dérogations
(4)–(5)) — texte proposé pour la PR d'intégration (C15.5), pas avant :**

```diff
 Lire le record historique seulement via le profil §9 ; en comparer id/spec,
 state/scope, critères/évidence/hashes de code à q. Seuls reviewer_kind/id sont
 remplacés par l'émetteur présent ; ne pas exiger H(q)=H(record historique).
+Exception : pour le profil pilot-p1-pc2-present-native-v0 de l'amendement P4_PC2
+(raw SHA256 <adopté>), le record historique est l'évidence native PC2, qui n'est pas
+une qualification ; q n'en est pas une copie et ses champs sont fixés par les §3–§6
+de cet amendement.
```

```diff
-Donc critères pilot p1 ou famille inconnue => SCIENTIFIC_PROFILE_UNSUPPORTED,
+Critères pilot p1 en PRESENT => profil pilot-p1-pc2-present-native-v0 de
+l'amendement P4_PC2 (raw SHA256 <adopté>) ; p1 en FRESH ou famille inconnue =>
+SCIENTIFIC_PROFILE_UNSUPPORTED,
```

**3C `P4_3C_POPULATION_AND_CEILINGS_V0.md` §13 (dérogation (6)) — idem, à la PR d'intégration :**

```diff
-PC2/p1 reste SCIENTIFIC_PROFILE_UNSUPPORTED, NE bloquant, sans enlever p1 de g0.
-Une nouvelle correspondance PC2 exige son amendement contractuel avant code.
+PC2/p1 PRESENT est évalué par l'amendement P4_PC2 (raw SHA256 <adopté>) ; FRESH reste
+SCIENTIFIC_PROFILE_UNSUPPORTED, NE bloquant ; p1 reste dans g0.
```

**Code (référence, inchangé)** : `colony_admission/_attestation_statement.py`,
`scientific_bindings` renvoie `SCIENTIFIC_PROFILE_UNSUPPORTED` pour tout critère
autre que R8. L'implémentation ajouterait la sélection C10.2 dans une PR séparée.

Inchangés : `SCENARIOS_A0.json`, g0, qualification/0, statement/0, enveloppes, kinds,
D2/D3, K, `colony_lab/`, `sentinel_activity/`, `colony_pilot/`, `colony_admission/`.

## 6. Options comparées et recommandation

| Option | Description | Formats/pins | Nomme P (F10) | Lie E | Risque principal | Réversibilité |
|---|---|---|---|---|---|---|
| O0 Maintien du blocage | Rien ne change | Aucun | — | — | Étape 3/7 reste bloquée sur cette limite tant que g0 admet p1 | Totale |
| **O1 Profil natif PRESENT (recommandée)** | Contrat r2 : S→subject, P→evaluator, E par PC2 | Aucun format ; P1 étendue par superposition (première fois) | Oui | Oui, par pin raw PC2 + recalcul | Sémantique P1 répartie sur deux documents (atténué par C0.4) | Revert documentaire avant code ; ensuite PR de retrait |
| O2 Mapping S→subject, E→evaluator | Convention Sentinel conservée, P seulement via PC2 | Aucun format | Non (contredit F10) | Oui | Le champ « évaluateur » ne désigne pas le code qui a produit l'évidence | Idem O1 |
| O3 qualification/1 à trois champs | Nouveau format | Change `colony_lab/lineage.py` ⇒ E change ⇒ R8 et PC2 périmés (P1 §11) | Oui | Oui | Requalification Sentinel ; amendement P1 et trust (kind) | Coûteuse |
| O4 Hash composite S‖E‖P | Un champ porte un digest combiné | Aucun format, nouveau sens d'un champ | Indirect | Indirect | Ambiguïté : le champ n'égale plus aucun hash natif ; nouveau calcul à spécifier | Moyenne |
| O5 Retirer p1 de g0 | Politique g0 modifiée | Change g0 | — | — | Change une politique gouvernée ; interdit implicitement par la mission | Gate distincte |
| O6 Profil FRESH p1 | Nouvelle campagne | Aucun | Oui | Oui | Exige une campagne (interdite ici) et un autre contrat | — |

Recommandation : **O1**, parce qu'elle ne change aucun format ni aucune fermeture,
nomme P comme l'exige le rapport natif, garde E obligatoire, s'aligne sur la
superposition sans toucher aux bytes épinglés de P1 (première extension de ce
genre, déclarée par C0.4), et laisse intactes les portes SR, émetteur et signatures. O0 reste recevable si Mathieu préfère ne pas étendre
P1 : la conséquence est que la limite PC2 reste citée comme bloquante à l'étape 3/7.
Cette recommandation n'est pas une adoption.

## 7. Justification du mapping recommandé

- **S → `subject_code_sha256`** : le pilote n'a pas de métier propre ; il exécute le
  worker de son parent (P1C.pilot.worker, PC2.not_claimed). Le sujet évalué est ce
  code ; c'est aussi la valeur de C9 et R8Q, donc la chaîne parent est cohérente.
- **P → `evaluator_code_sha256`** : `q.evidence_sha256` désigne PC2, produite par la
  campagne `colony_pilot/` ; le champ évaluateur doit désigner le code qui a produit
  cette évidence. Le rapport natif l'exige explicitement (F10).
- **E par PC2** : E est la base du laboratoire réutilisée par P ; il est déjà un
  champ de PC2, de C9 et de R8Q. Le pin raw PC2 (= `q.evidence_sha256`, signé) et le
  recalcul courant le lient sans nouveau champ. Le rendre optionnel rouvrirait une
  faille (évaluateur Sentinel affaibli) : il est donc obligatoire (C3.4).

## 8. Preuves manquantes et auteurs possibles

Aucune de ces preuves n'est générée par ce chantier.

| # | Preuve manquante | Nécessaire pour | Auteur possible | Ne peut pas venir de |
|---|---|---|---|---|
| M1 | Décision d'adoption citant PR, commit, tree et SHA256 raw des documents | C0.3(a) | Mathieu | Un agent, la CI, une revue |
| M2 | CI exacte du HEAD documentaire et du merge | C8.2 | GitHub Actions, constatée par un agent | Une CI d'un autre arbre |
| M3 | Validateurs et tests exécutés liés aux 80 cas, mutants des bindings | C8.3 | PR SOURCE_ONLY future (développeur/agent) + revue indépendante d'arbre exact | Cette matrice (spécification) |
| M4 | Intégration acquisition/projection, R8/PC2/mélange | C8.4 | PR future après prérequis 3C | — |
| M5 | Dossier SR (revue scientifique de p1, PC2, `colony_pilot/`, tests, mutants non vus) | C4.3 | Reviewer EXTERNAL_HUMAN ou EXTERNAL_REVIEW_PROCESS identifié, qui n'est pas un auteur de la campagne au sens de C11.3. Mathieu (EXTERNAL_HUMAN) est possible s'il déclare son rôle de commanditaire ; un agent commandité dans ce projet seulement si Mathieu désigne ce processus (question Q2 du §12) | Revue de cet amendement ou du validateur ; signatures |
| M6 | Racine LAB_TEST autorisant I pour qualification/0 et statement/0 | C4.9, C11 | Opérateur, gate d'installation distincte | Cet amendement (C11.4) |
| M7 | q réelle et qe | Attestation | I, après M5 et M6 et autorisation d'émission | Le diagnostic, un agent sans clé |
| M8 | s réel et se | Attestation | I | Idem |
| M9 | Contexte acquis : records/specs du pilote dans un lab réel | C5.1 | Une naissance future sous le contrôleur (gate distincte, interdite ici) | PC2 seule |
| M10 | Provenance temporelle de la campagne PC2 et de SR | — | Non obtenable pour PC2 ; reste NE (seul un profil FRESH futur pourrait la produire) | — |

Les fixtures synthétiques LAB_TEST de la future PR M3 illustrent le contrat ; elles
ne qualifient rien et ne portent aucune identité réelle.

## 9. Risques, compatibilité et blocages restants

- **Superposition** : un lecteur de P1 seul ignore l'exception. Atténuation : C0.4,
  mise à jour 3B/3C à l'intégration (C15.5), dossier citant les deux SHA256.
- **Confusion de champs** : un futur outil pourrait lire `evaluator_code_sha256` du
  pilote comme une valeur Sentinel. Atténuation : sélection par critère (C10.2), cas
  PC2-06/07/57/58.
- **Glissement d'autorité** : risque de traiter une signature ou une revue d'agent
  comme une revue SR. Atténuation : C4.4–C4.5, C16.3, cas PC2-53/65/78.
- **Péremption** : toute modification de `colony_lab/`, `sentinel_activity/`,
  `governance_tower/`, des quatre fichiers `observability/` de S, ou de `colony_pilot/` rend PC2
  divergent (C3.6, P1 §11) ; le profil n'a pas de mécanisme de requalification.
- **Compatibilité** : formats et profil R8 inchangés ; lecteurs actuels restent
  fail-closed (C15.1–C15.2).
- **Blocages qui restent après adoption** : M2–M9 ; matrices 3A/3B/3C non exécutées
  (dossier 3C) ; étape 3/7 non close ; accepted=false ; #286 ACTIVE ; aucune
  étape 4.

## 10. Différences r1 → r2

- Baseline revérifiée sur `main@cc36e36e` (3C fusionnée) ; pins et fermetures
  inchangés ; branche mise à jour par merge de main (aucun conflit, aucune
  modification de fichier hors des documents PC2).
- Clauses numérotées C0–C16 ; contenu r1 conservé sans affaiblissement.
- Ajouts : statut/entrée en vigueur (§0), sélection déterministe et versionnage du
  profil (C10.2–C10.3), canonicalisation et lecture stricte (C10.4–C10.5), rôles et
  autorités (§11), portées temporelles (§12), table absence/ambiguïté/divergence/
  révocation/invalidation (§13), table de conséquences (§14), compatibilité (§15),
  historique sans rétroactivité et trois actes distincts (§16), q à state non
  qualifié (C13.0), classement explicite des revues #484 (C4.5, dossier §4).
- Matrice : schéma `/1`, champ `clauses` sur chaque cas, 54 cas r1 inchangés,
  26 cas r2 (PC2-55..PC2-80), toutes les clauses couvertes.
- Nouveau document : ce dossier.

Corrections après la revue 1 (arbre `e7623017`, FAVORABLE AVEC CONDITIONS,
0 bloquant, 6 moyens, 10 mineurs) : liste exhaustive des six dérogations (C0.2) ;
précédent AMENDMENT_3/4 retiré et première extension de P1 déclarée (§5–§6) ;
révocation définie (C13.4, cas PC2-80) ; exclusions d'émetteur alignées sur 3C §8
(C11.2, PC2-64) ; code exact par fait (C13.3, C10.1, cas r2 précisés, note de
lecture des cas r1) ; auteur de la campagne défini et désignation d'un agent comme
SR laissée à Mathieu (C11.3, §8, Q2) ; ordre de tri (C3.1) ; bloc 3B §8 PRESENT
(§5) ; conditions de la revue 13 (§4) ; portée de la ligne « absent » (C13.0) ;
deux phrases r1 rétablies (C4.3, C6.7) ; PC2-03/PC2-75 ; fichiers `observability/`
de S ; limite `EVIDENCE_NOT_STORED` à citer (C14.0) ; effet de verdict et de
gouvernance distingués (C0.1) ; grammaire générale délimitée (C10.2).

Corrections après la revue 2 (arbre `cabd63fe`, FAVORABLE AVEC CONDITIONS, 0
bloquant, 1 moyen, 4 mineurs) : statut exact des agrégats pour une attestation
absente (C13.0, C13.3, C14.0) ; liste des commits auteurs (C11.3) ; couverture
d'exclusion par couche (C11.2) ; source et nature de la vérification `644aab6f`
(§4) ; code statement pour un champ de q manquant (C10.1).

## 11. Vérifications documentaires exécutées et limites

Exécutées localement le 2026-10-28 : pins raw des cinq artefacts et de P1 ;
recalcul S/E/P et `code_irregular` sur une copie `git archive` de main ; lecture
stricte des cinq artefacts ; ordre et identité des 28×2 rounds ; égalité
PC2.parent.qualification = R8Q ; 80 IDs uniques ; toute clause citée existe et toute
clause est citée ; 54 cas r1 identiques à r1. Non exécutés : aucun test produit,
aucune campagne, aucun validateur, aucune CI (elle s'exécute sur le HEAD poussé).

Les résultats de la revue indépendante d'agent sont consignés hors de l'arbre
(commentaire de #510 et fichiers du projet) afin que l'arbre revu soit exactement
l'arbre soumis. Cette revue vérifie la proposition ; elle n'est ni adoption ni
validation scientifique.

## 12. Question d'adoption (forme)

« Adoptes-tu le profil `pilot-p1-pc2-present-native-v0` tel que défini par #510 au
commit `<SHA complet>`, tree `<tree>`, documents de SHA256 raw `<contrat>`,
`<matrice>`, `<dossier>` — avec S→subject, P→evaluator et E lié par PC2 — sachant
que cette adoption n'autorise que la fusion documentaire gardée puis de petites PR
d'implémentation, sans émission, installation, naissance, sortie de p1 de g0 ni
clôture de l'étape 3/7 ? » (Q1)

Sous-question liée (Q2, C11.3) : une revue par un agent commandité dans ce projet
peut-elle être désignée comme processus `EXTERNAL_REVIEW_PROCESS` pour la porte SR,
ou la revue SR doit-elle être humaine ou externe au projet ? Recommandation : ne
rien désigner maintenant ; décider au moment où un dossier SR concret existe. Q2
ne conditionne pas Q1.

Les valeurs exactes figurent dans le commentaire de soumission de #510.
