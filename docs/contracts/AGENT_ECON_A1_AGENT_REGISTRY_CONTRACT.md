# AGENT-ECON A1 — Agent Registry Contract

**Parent :** [#284](https://github.com/3a7i3/crypto-ia-terminal/issues/284) ·
**Roadmap :** [#285](https://github.com/3a7i3/crypto-ia-terminal/issues/285) ·
**Garde-fou :** [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286) ·
**Gate liée :** [#315](https://github.com/3a7i3/crypto-ia-terminal/issues/315)
**Constitution :** [A0 `AGENT_ECON_A0_FOREST_V1`](AGENT_ECON_A0_FOREST_MAINTENANCE_CONTRACT.md)
**Base source :** `c561fae406950bf7813102b5b3f59c32388566d0`
**Statut :** `CONTRACT DEFINED — NO IMPLEMENTATION — NON_DEPLOYED`

A1 est **conçu, pas exécuté**. Aucun module `agent_economy/` n'est créé et
#284 n'autorise pas, à la date de cette base, d'implémentation source A1 :
la mission reste contract/schema-only. Ce contrat doit permettre à une mission
ultérieure d'implémenter la validation, l'identité, la projection, la
publication write-once et la vérification de chaîne sans réinventer les règles.

Il réutilise les patterns du dépôt : identité SHA-256 déterministe et JSON
canonique (`research_candidate/candidate.py`), séquence de registre globale et
ordinal par objet contigu, états terminaux, publication write-once `O_EXCL`
(`research_candidate/registry.py`), hash-chain `GENESIS → previous_event_hash →
event_hash` et vérification fail-closed (`observability/operator_decisions/durable_store.py`).

## 1. Ce qu'A1 est et n'est pas

A1 est le registre **d'identités et de spécifications** d'agents. Il répond à :
« quelles identités sont connues, quel est leur plafond, quelle est leur
version courante, dans quel état ? ».

A1 n'est pas : un lanceur, un orchestrateur, un registre de problèmes,
de bounties, de wallets ou de réputation, une file de tâches, une autorité de
permission d'exécution. `REGISTERED` ≠ worker running ≠ autorisé à agir.

## 2. Canonicalisation

Toute identité et tout hash utilisent la même sérialisation que
`research_candidate.candidate.canonical_json_bytes` :

```text
json.dumps(value, ensure_ascii=False, allow_nan=False,
           sort_keys=True, separators=(",", ":")).encode("utf-8")
```

- hash = SHA-256 en hexadécimal minuscule de 64 caractères ;
- pas de flottant dans les objets hachés ; entiers non booléens ;
- tableaux de chaînes **triés et sans doublon** (refus sinon, pas de tri silencieux) ;
- timestamps : RFC 3339 UTC, suffixe `Z`, jusqu'à 6 décimales ;
- tout identifiant de schéma inconnu est rejeté.

## 3. Deux identités distinctes

### 3.1 `agent_id` — identité logique stable

```text
agent_id = SHA256( canonical_json({
    "agent_identity_schema": "agent-econ-a1.agent-identity.v1",
    "namespace": <namespace>,
    "canonical_name": <canonical_name>,
    "agent_class": <agent_class>
}) )
```

`namespace` et `canonical_name` : ASCII minuscule `^[a-z0-9]+(?:[._-][a-z0-9]+)*$`,
64 caractères max (pas de normalisation Unicode à définir). Le namespace
`fixture` est réservé aux vecteurs de test et refusé par tout registre non fixture.

**Appartient au calcul :** version d'identité, namespace, nom canonique, classe.
**N'y appartient pas :** niveau, capabilities, scopes, politiques, binding,
état, révision, dates, modèle, nom d'affichage, finalité. Changer de niveau,
de capability ou d'objectif conserve donc `agent_id`. Changer de **classe**
crée un autre agent : c'est un autre métier.

### 3.2 `agent_spec_id` — version exacte

```text
agent_spec_id = SHA256( canonical_json(AgentSpec sans le champ agent_spec_id) )
```

**Appartient au calcul :** tous les autres champs de l'`AgentSpec` : `agent_schema`,
`agent_id`, `spec_revision`, `constitution_version`, `namespace`, `canonical_name`,
`display_name`, `agent_class`, `maintenance_level`, `purpose`, `capabilities`,
`scope_policy`, `independence_policy`, `authority_policy`, `execution_binding`,
`supersedes_spec_id`, `created_from_ref`, `created_at_utc`.

**N'y appartient pas :** l'état du registre (`REGISTERED/SUSPENDED/RETIRED`), les
événements, `registry_sequence`, les hashes de chaîne, toute donnée AIC,
réputation, coût, wallet. L'état est une projection d'événements, jamais une
propriété du spec : suspendre un agent ne change donc pas son `agent_spec_id`.

**Décision de conception soumise à revue :** `created_at_utc`, `created_from_ref`,
`spec_revision` et `supersedes_spec_id` sont inclus. Conséquences : toute
modification, même cosmétique, change `agent_spec_id` ; un même contenu écrit
à une autre date est une autre version ; un fichier publié pour un
`agent_spec_id` donné est donc entièrement déterminé par ce hash, ce qui rend la
publication write-once sans ambiguïté. L'alternative (exclure les champs de
provenance) autoriserait deux fichiers distincts pour un même identifiant.

Toute implémentation doit **recalculer** `agent_id` et `agent_spec_id` et refuser
un document dont les valeurs déclarées diffèrent.

## 4. AgentSpec v1

Forme normative : [`AGENT_ECON_A1_AGENT_SPEC_V1.schema.json`](AGENT_ECON_A1_AGENT_SPEC_V1.schema.json)
(JSON Schema 2020-12, `additionalProperties: false` partout). Champs :

| Champ | Contrainte |
|---|---|
| `agent_schema` | `AGENT_ECON_A1_AGENT_SPEC_V1` |
| `agent_id`, `agent_spec_id` | SHA-256 recalculés (§3) |
| `spec_revision` | entier ≥ 1 ; `1` ⇒ `supersedes_spec_id = null` ; `≥2` ⇒ hash du spec précédent |
| `constitution_version` | `AGENT_ECON_A0_FOREST_V1` |
| `namespace`, `canonical_name`, `display_name` | voir §3.1 ; affichage ≤ 120 caractères |
| `agent_class` | une des 14 classes de la [matrice](AGENT_ECON_A1_CAPABILITY_CATALOG.md) |
| `maintenance_level` | `F0`…`F4`, compatible avec la classe |
| `purpose` | texte, 1000 caractères max |
| `capabilities[]` | non vide, triées, uniques, dans le catalogue fermé et dans l'ensemble du niveau |
| `scope_policy` | `repository_read_paths[]`, `repository_write_paths_future[]`, `github_surfaces[]`, `artifact_domains[]` |
| `independence_policy` | `own_work_review_forbidden = true`, `independent_review_required = true` |
| `authority_policy` | `authority_ceiling = NO_RUNTIME_AUTHORITY`, `human_decision = false`, `economic_status_grants_authority = false`, `reputation_grants_authority = false`, `consensus_grants_authority = false` |
| `execution_binding` | `status = UNBOUND`, `provider = null`, `model = null`, `credential_mode = NONE` |
| `supersedes_spec_id`, `created_from_ref`, `created_at_utc` | provenance ; `created_from_ref` = SHA Git de 40 caractères |

Ajouts par rapport au brief, signalés pour revue : `constitution_version`
(lie le spec à la version de la constitution et le rend matériel) et
`authority_policy.consensus_grants_authority` (rend explicite
`AGENT CONSENSUS != AUTHORITY`).

Rejets structurels du schéma : capability inconnue ou interdite, champ inconnu,
plafond d'autorité autre, `human_decision` vrai, booléens ou valeurs ambigus
(chaînes `"true"`, `null` hors champs nuls), binding actif, provider, modèle,
credential, chemins avec `..`, absolus, `.env*`, clés, ou chemin d'écriture
dans un préfixe gelé, capabilities hors du niveau, niveau hors de la classe,
chemins d'écriture sans `SOURCE_EDIT_ISOLATED`.

**Hors du schéma, imposé par l'implémentation source :** recalcul des deux
identités, tri des tableaux, indépendance entre agents (§9), progression
cohérente des révisions (§6), classification des élévations de privilège (§7).

Le spec ne contient ni wallet, ni solde AIC, ni réputation, ni coût, ni
tâche, ni problème, ni état.

## 5. États

Le mot `ACTIVE` est proscrit (ambigu avec un processus en cours).

| État | Sens | Interdit de lui prêter |
|---|---|---|
| `REGISTERED` | identité connue du registre, spec courant défini | exécution, binding, permission d'agir |
| `SUSPENDED` | connue mais gelée par décision ; ses outputs ne sont plus acceptés | suppression |
| `RETIRED` | terminal ; identité jamais réutilisée | réinscription sous le même `agent_id` |

Transitions :

```text
(absent) → REGISTERED
REGISTERED → SUSPENDED          REGISTERED → RETIRED
SUSPENDED  → REGISTERED         SUSPENDED  → RETIRED
RETIRED    → (terminal)
```

Toute autre transition est rejetée. Un agent retiré n'est pas effacé : ses
événements et specs restent. Un agent qui change de classe est un nouvel
`agent_id` ; l'ancien est `RETIRED` avec `reason_code = SUPERSEDED_BY_NEW_AGENT`.

## 6. Événements

Cinq types, avec la table de transition normative :

| `event_type` | `previous_state` → `new_state` | `agent_spec_id` | Condition |
|---|---|---|---|
| `AGENT_REGISTERED` | `null` → `REGISTERED` | spec de révision 1 | ordinal 1 ; `supersedes_spec_id = null` |
| `AGENT_SPEC_REVISED` | `REGISTERED` → `REGISTERED` ou `SUSPENDED` → `SUSPENDED` | nouveau spec | `supersedes_spec_id` = spec courant ; `spec_revision` = précédent + 1 ; même `agent_id` |
| `AGENT_SUSPENDED` | `REGISTERED` → `SUSPENDED` | spec courant | identique au courant |
| `AGENT_REINSTATED` | `SUSPENDED` → `REGISTERED` | spec courant | identique au courant ; le spec courant reste valide |
| `AGENT_RETIRED` | `REGISTERED`/`SUSPENDED` → `RETIRED` | spec courant | identique au courant |

Réviser un spec suspendu permet de corriger avant réintégration ; la révision
ne réintègre pas.

### 6.1 `AgentRegistryEvent`

| Champ | Règle |
|---|---|
| `event_schema` | `AGENT_ECON_A1_REGISTRY_EVENT_V1` |
| `event_id` | SHA-256 de l'identité d'événement (ci-dessous), déterministe |
| `registry_sequence` | entier, **contigu** 1, 2, 3… sur tout le registre |
| `agent_transition_ordinal` | entier, **contigu** 1, 2, 3… pour cet `agent_id` |
| `agent_id`, `agent_spec_id` | SHA-256 ; le second doit désigner un spec publié valide |
| `event_type`, `previous_state`, `new_state` | table §6 |
| `reason_code` | énumération fermée ci-dessous |
| `reason_detail` | texte, 1000 caractères max, entre dans le hash |
| `evidence_refs[]` | triées, uniques, au moins une |
| `occurred_at_utc` | RFC 3339 UTC ; ne régresse pas par rapport à l'événement précédent |
| `previous_event_hash` | `GENESIS` pour la séquence 1, sinon `event_hash` de la séquence − 1 |
| `event_hash` | §8 |

Identité d'événement :

```text
event_id = SHA256( canonical_json({
    "event_identity_schema": "agent-econ-a1.event-identity.v1",
    "agent_id", "agent_transition_ordinal", "event_type",
    "agent_spec_id", "new_state" }) )
```

Elle exclut séquence, date et raison : un même fait logique rejoué est
détecté comme doublon idempotent et non comme nouvel événement.

`reason_code` : `INITIAL_REGISTRATION`, `SPEC_CORRECTION`, `CAPABILITY_REDUCTION`,
`PRIVILEGE_INCREASE`, `SCOPE_CHANGE`, `SAFETY_SUSPENSION`,
`GOVERNANCE_REVIEW_PENDING`, `REMEDIATION_COMPLETE`, `LEGACY_RECONCILIATION_BLOCK`,
`SUPERSEDED_BY_NEW_AGENT`, `OBSOLETE`. Valeur inconnue : rejet.

Références de preuve admises : `git:<sha40>`, `github-issue:<owner>/<repo>#<n>`,
`github-pr:<owner>/<repo>#<n>`, `sha256:<hash64>`. Une référence est une
**citation**, jamais la preuve d'une autorisation humaine tant que les six
décisions opérationnelles de Gate O (#315) ne sont pas fermées.

## 7. Élévation de privilège

Une révision est une **élévation** si, par rapport au spec précédent, le
niveau monte, une capability, un chemin de lecture ou d'écriture, une surface
GitHub ou un domaine d'artifact est ajouté. Toute élévation doit porter
`reason_code = PRIVILEGE_INCREASE` et référencer une PR ou issue de gouvernance
dans `evidence_refs`. Une élévation étiquetée autrement est rejetée. Un même
`agent_id` ne peut pas franchir F3 ↔ F4 : la classe, qui fait partie de
l'identité, fixe les niveaux possibles et aucune classe n'admet à la fois F3 et F4.

## 8. Intégrité et hash-chain

```text
GENESIS ─▶ EVENT 1 ─▶ EVENT 2 ─▶ … ─▶ EVENT N
event_hash(n) = SHA256( canonical_json(event_n sans event_hash) )
event_n.previous_event_hash = event_hash(n−1)   (GENESIS pour n=1)
```

Procédure de vérification (aucune étape n'est optionnelle) :

1. schéma d'événement connu, champs exacts ;
2. `registry_sequence` contigu depuis 1 ;
3. `previous_event_hash` et `event_hash` recalculés égaux ;
4. `agent_transition_ordinal` contigu par agent ;
5. `event_id` recalculé ;
6. transition légale selon §5 et §6 depuis l'état projeté ;
7. spec référencé publié, valide (schéma + deux identités recalculées), cohérent
   avec l'`agent_id` et la révision ;
8. date non régressive.

Verdicts : `CHAIN_VERIFIED`, `NOT_CERTIFIABLE(reason)`. Une seule rupture rend
**tout** le registre non certifiable. Jamais de réparation silencieuse, de
réordonnancement, de saut de séquence ou de reconstruction « au mieux ». La
reprise est une mission forensic distincte qui conserve l'artefact cassé.

**Limites déclarées (même nature que les constats de #315/#316) :** une chaîne
SHA-256 se détecte contre la corruption, pas contre un écrivain malveillant qui
la recalcule, et ne détecte pas une troncature de queue. L'authenticité,
l'identité de l'écrivain et l'ancre anti-retour (par exemple le SHA Git de la
tête du registre) sont **hors de ce contrat** ; tant qu'ils ne sont pas définis,
A1 ne produit qu'un verdict d'intégrité, jamais d'autorisation opérationnelle.

## 9. Indépendance entre agents

Règles à implémenter hors schéma, au niveau registre/projection (A1 source) puis
appliquées par A7 :

- l'auteur d'un travail (`agent_id` F3) ne peut pas être le relecteur du même
  travail ; le relecteur doit avoir un `agent_id` différent ;
- un F1 ne vérifie pas son `CANDIDATE_PROBLEM` ; la vérification est faite par
  un F2 d'un autre `agent_id` ;
- aucun `agent_id` n'a deux niveaux simultanés (un spec = un niveau) ;
- une même ressource d'exécution partagée par auteur et relecteur n'est pas
  traitée ici car `execution_binding` est `UNBOUND` ; l'**indépendance
  substantielle** (modèle, fournisseur, contexte) est une question ouverte pour
  A6/A7 et ne doit pas être présumée.

## 10. Publication write-once et projection

- Un spec est publié sous une clé dérivée de `agent_spec_id` (le stockage n'est pas
  choisi ici). Création exclusive (`O_EXCL` ou équivalent) ; si la clé existe
  et que le contenu est octet pour octet identique : doublon idempotent ; sinon :
  corruption, rejet.
- Aucune modification, aucun remplacement, aucune suppression d'un spec publié.
- Projection : fonction pure de la liste ordonnée d'événements vérifiée ; elle
  fournit par agent `state`, `current_agent_spec_id`, `current_spec_revision`,
  `last_agent_transition_ordinal`, et pour le registre `head_sequence` et
  `head_event_hash`. Elle ne lit aucune autre source et peut être reconstruite.
- Résultats de lecture distincts : `NOT_DEPLOYED` (aucun artefact de registre ni
  producteur), `UNVERIFIED`, `CHAIN_VERIFIED(n agents)`, `NOT_CERTIFIABLE`. Un
  registre inexistant n'est pas un registre vide ; un nombre d'agents inconnu
  n'est pas 0. Un registre « vide certifié » exigerait une ancre externe non
  définie : tant qu'elle manque, le comptage reste `UNKNOWN`.
- Aucun agent n'écrit le registre (`AGENT_REGISTRY_WRITE` interdit).

## 11. Vecteurs de test (FIXTURE ONLY)

Ces valeurs permettent de vérifier une future implémentation. Elles ne
représentent **aucun agent enregistré** ; le namespace `fixture` est réservé et
doit être refusé par un registre de production. Calculées avec la
canonicalisation de §2.

```text
agent_id (namespace=fixture, canonical_name=sensor-vector, agent_class=SENSOR):
  aadec63021f4bfb1e593feaede05c191c7c8950ebb663cf8d475d9d2fc85e2e0
```

Spec : `SENSOR`, `F0`, `capabilities = ["REPOSITORY_READ","REPOSITORY_SEARCH"]`,
`repository_read_paths = ["docs/"]`, autres listes vides, révision 1,
`supersedes_spec_id = null`, `created_from_ref = c561fae406950bf7813102b5b3f59c32388566d0`,
`created_at_utc = 2026-10-03T00:00:00Z`, `display_name = "Fixture sensor (test vector)"`,
`purpose = "Fixture vector. Never registered."`, politiques et binding aux valeurs
du §4 :

```text
agent_spec_id:
  b8f18d4912cde32fa35347afe8b5fb68ad0e547936d9e609e60c5f58ca073736
```

Événement `AGENT_REGISTERED` (séquence 1, ordinal 1, `INITIAL_REGISTRATION`,
`reason_detail = "Fixture vector. Never registered."`,
`evidence_refs = ["git:c561fae406950bf7813102b5b3f59c32388566d0"]`,
`occurred_at_utc = 2026-10-03T00:00:00Z`, `previous_event_hash = "GENESIS"`) :

```text
event_id:   98a66104cb3d32aeb7f96c7dfed79b46c034cc19028871c5eeb5d1a09da1a399
event_hash: 36c928cef2a5a108a465b517cd3d53ccff3dc270265897ff22ea1e74f9bb0011
```

## 12. Tests futurs proposés (non écrits ici)

1. identité : `agent_id` stable face à la révision ; `agent_spec_id` change à tout
   champ ; les trois vecteurs ci-dessus ; refus d'un identifiant déclaré incorrect ;
2. schéma : un test négatif par rejet structurel listé en §4 ; capability
   interdite (chaque entrée de A0 §6) refusée ; valeur ambiguë refusée ;
3. matrice : chaque couple classe×niveau, chaque capability×niveau ;
4. états : toutes les transitions légales et illégales ; `RETIRED` terminal ;
5. événements : séquence trouée ou dupliquée, ordinal non contigu, `event_id`
   faux, transition illégale, élévation étiquetée autrement que `PRIVILEGE_INCREASE` ;
6. chaîne : modification d'un octet, suppression d'un événement, réordonnancement,
   `GENESIS` mal placé → `NOT_CERTIFIABLE` ; aucune réparation ;
7. publication : doublon identique idempotent, contenu différent même clé rejeté,
   création concurrente ;
8. projection : fonction pure, déterministe, `NOT_DEPLOYED ≠ vide`, `UNKNOWN ≠ 0` ;
9. frontière statique : le futur paquet n'importe ni runtime, ni PPL, ni FIN, ni exchange,
   ni client de modèle, ni client GitHub en écriture ; aucune dépendance ajoutée ;
10. aucun fichier `.github/agents/*` n'est lu comme autorité.

## 13. Critères d'acceptation avant une implémentation source A1

Ne démarrer que si : (a) ce contrat est revu par un humain ; (b) #284 autorise
explicitement l'implémentation source A1 ; (c) le stockage cible, l'écrivain
autorisé et l'ancre d'intégrité sont décidés (voir §8) ; (d) #286 est respecté ;
(e) aucune dépendance externe n'est nécessaire.

## 14. Hors périmètre A1

Problem Registry (A2), Bounty (A3), wallet, AIC, balance, ledger (A4), coûts
(A5), worker, sandbox (A6), revue automatisée (A7), mutation GitHub (A8),
scheduler, fournisseur de modèle, credential, UI, API Operator.
