# AGENT-ECON A1 — Agent Registry Contract

Statut : **SOURCE CONTRACT V1 / CONTRACT-ONLY / NON DÉPLOYÉ** — conçu, **pas exécuté**.
Verdict de livraison : `AGENT_ECON_A1_AGENT_REGISTRY_CONTRACT_READY_FOR_REVIEW`
(pas `CERTIFIED`).

Parent : [#284](https://github.com/3a7i3/crypto-ia-terminal/issues/284) · Constitution :
[A0 — Forest Maintenance Contract](AGENT_ECON_A0_FOREST_MAINTENANCE_CONTRACT.md) ·
Catalogue : [Capability Catalog & Matrix](AGENT_ECON_A1_CAPABILITY_CATALOG.md) ·
Schémas : [AgentSpec](AGENT_ECON_A1_AGENT_SPEC_V1.schema.json),
[AgentRegistryEvent](AGENT_ECON_A1_AGENT_REGISTRY_EVENT_V1.schema.json).
Base source observée : `main@c561fae406950bf7813102b5b3f59c32388566d0`.

---

## 0. Portée

A1 définit **qui est connu du registre, sous quelle spec exacte, dans quel état, avec
quelle preuve d'historique**. Rien de plus.

A1 ne contient ni Problem Registry, ni bounty, ni wallet, ni balance AIC, ni worker,
ni scheduler, ni provider de modèle, ni credential, ni mutation GitHub. Il n'existe
aucun `agent_economy/*.py` : aucune autorisation d'implémentation source A1 n'a été
trouvée dans #284 à la rédaction (A0 §15). **FAIL CLOSED : contract-only.**

Un registre qui *connaît* un agent ne lui accorde **aucun pouvoir** :
`REGISTERED ≠ running ≠ authorized` (§7).

---

## 1. Précédents réutilisés

| Principe | Précédent dans le dépôt | Usage en A1 |
|---|---|---|
| sérialisation canonique | `research_candidate/candidate.py:51` `canonical_json_bytes` (`ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",",":")`) puis `sha256_json` | identique, §3.1 |
| identité déterministe | `compute_candidate_id`, `compute_event_id` (`research_candidate/`) : document d'identité à schéma explicite, sans horodatage | `agent_id`, `agent_spec_id`, `event_id` |
| tableaux triés/uniques **rejetés**, jamais normalisés en silence | `_sorted_unique_strings` (`research_candidate/registry.py:96`) | AS-04 |
| machine à états + transitions légales fermées | `LEGAL_TRANSITIONS` (`registry.py:49`) | §7 |
| séquence globale croissante + ordinal par objet contigu | `registry_sequence`, `candidate_transition_ordinal` (`registry.py:165`, `project_candidate_states`) | §8 |
| publication write-once, identique ⇒ idempotent, différent ⇒ collision/corruption | `publish_candidate` (`registry.py:502`, `O_CREAT\|O_EXCL`, `ALREADY_EXISTS_IDENTICAL`, `CANDIDATE_ID_COLLISION_OR_CORRUPTION`) | §12 |
| chaîne de hash avec `GENESIS` | `observability/operator_decisions/durable_store.py` (`previous_event_hash`, `event_hash`, `GENESIS`) | §9 |
| fail-closed, `UNKNOWN`, `NON DÉPLOYÉ` ≠ vide | D5A/D5B (`WEB_DIR_01_D5A_OPERATOR_DECISION_QUEUE_CONTRACT.md`) | §7.3 |
| leçon : une chaîne recalculable n'est pas une authenticité | `docs/adr/0020-contrat-de-confiance-operator-decision-d5b-r2.md` §2 (M5), #315 | §9.4 |

Écart observé : le registre `RL-CANDIDATE` n'a **pas** de chaîne de hash (identité +
séquence seulement) ; le journal D5B en a une. A1 combine les deux idées.

### Décision de format machine-readable

Aucun précédent `*.schema.json` n'existe ; les JSON de `docs/contracts/` sont des
profils/revues. Décision : **deux JSON Schema Draft 2020-12 dans `docs/contracts/`**,
à côté des contrats qu'ils appliquent, sans nouveau répertoire, sans dépendance, sans
loader. Ils décrivent des contraintes structurelles ; ce que JSON Schema ne peut pas
exprimer est listé en §9 comme règle de **validateur** (V), jamais supposé couvert.

---

## 2. Identités

Deux identités distinctes, toutes deux SHA-256 hexadécimal minuscule (64 caractères).

### 2.1 `agent_id` — identité logique stable

```text
agent_id = SHA256( canonical_json({
    "agent_identity_schema": "agent-econ.a1.agent-identity.v1",
    "namespace":             <namespace>,
    "canonical_name":        <canonical_name>,
    "agent_class":           <agent_class>
}) )
```

**Interprétation de « schema_version »** : l'élément de version dans l'identité est la
version de **dérivation d'identité** (`agent_identity_schema`), *pas* `agent_schema`.
Raison : l'identité logique doit rester stable quand `AgentSpec` passe de V1 à V2 ;
seule une décision délibérée de changer la dérivation d'identité (et donc de rompre
toutes les identités) doit pouvoir changer `agent_id`.

| Appartient à `agent_id` | N'appartient **pas** à `agent_id` |
|---|---|
| `agent_identity_schema`, `namespace`, `canonical_name`, `agent_class` | `agent_schema`, `spec_revision`, `maintenance_level`, `capabilities`, `scope_policy`, `purpose`, `display_name`, `execution_binding`, tout horodatage/provenance |

Conséquences :

- Changer la **classe** (le métier) produit un **nouvel agent** : l'ancien est retiré
  (`RETIREMENT_SUPERSEDED_BY_NEW_AGENT`), le nouveau enregistré. Aucun re-classement
  silencieux.
- Changer le niveau, les capabilities ou le périmètre **garde** `agent_id` et change
  `agent_spec_id` (§2.2) : c'est une révision de spec, classifiée (§10).
- `canonical_name` est immuable : `^[a-z][a-z0-9_]{2,63}$`. `namespace` V1 : `forest`
  uniquement (énumération fermée).

### 2.2 `agent_spec_id` — identité exacte d'une version matérielle

```text
agent_spec_id = SHA256( canonical_json({
    "agent_spec_identity_schema": "agent-econ.a1.agent-spec-identity.v1",
    "agent_schema", "agent_id", "spec_revision",
    "namespace", "canonical_name", "display_name",
    "agent_class", "maintenance_level", "purpose",
    "capabilities", "scope_policy", "independence_policy",
    "authority_policy", "execution_binding", "supersedes_spec_id"
}) )
```

Toute modification **matérielle** change `agent_spec_id`.

| Appartient à `agent_spec_id` | N'appartient **pas** |
|---|---|
| tous les champs *énoncés* de la spec ci-dessus, `agent_id`, `agent_schema`, `spec_revision`, `supersedes_spec_id` | `agent_spec_id` lui-même (circularité) ; **provenance** : `created_from_ref`, `created_at_utc` |

Justifications :

- `display_name` et `purpose` sont **matériels** : un changement est une nouvelle
  révision. Cela évite toute mutation « non matérielle » d'un artefact write-once.
- `spec_revision` et `supersedes_spec_id` sont matériels : revenir à un contenu antérieur
  produit un `agent_spec_id` **nouveau** (la chaîne de supersession reste injective).
- La provenance est exclue : deux publications du même contenu à des instants différents
  désignent la même spec. Mais l'artefact publié est **write-once** : republier le même
  `agent_spec_id` avec une autre provenance est un conflit (`AGENT_SPEC_PROVENANCE_CONFLICT`,
  §12), pas un écrasement.

### 2.3 Ce qui est vérifié par un banc jetable

Lors de la rédaction, une implémentation de référence **jetable (non livrée)** a vérifié :
déterminisme ; `agent_id` stable à travers une révision et un changement de
`agent_schema` ; `agent_id` sensible à la classe et insensible au niveau/capabilities ;
`agent_spec_id` sensible aux capabilities, au `purpose`, au périmètre et à la
révision, insensible à la provenance ; NFC ≠ NFD donnent des hash différents (donc la
normalisation NFC est une règle de validateur obligatoire, AS-03). **Aucun vecteur de
test n'est publié ici** : un hash d'agent fictif pourrait être pris pour un agent
réel. Les vecteurs doivent être produits par la mission A1 SOURCE depuis des entrées
gouvernées, jamais depuis un agent de démonstration.

---

## 3. Sérialisation canonique

### 3.1 Algorithme (référence : `research_candidate/candidate.py:51`)

```text
canonical_bytes(v) = UTF-8( json.dumps(v, ensure_ascii=False, allow_nan=False,
                                       sort_keys=True, separators=(",", ":")) )
sha256_hex(v)      = lowercase hex of SHA-256(canonical_bytes(v))
```

### 3.2 Règles préalables (rejet, jamais correction silencieuse)

| Règle | Contenu |
|---|---|
| nombres | entiers uniquement. `bool`, `float` (même `1.0`), `NaN`, `Infinity` ⇒ rejet `SPEC_NUMERIC_AMBIGUITY` ; JSON Schema accepte `1.0` comme entier, donc **c'est un contrôle de validateur** |
| texte | NFC obligatoire ; pas de caractère de contrôle (sauf `\n` dans `purpose`) ; pas d'espace de tête/queue ⇒ rejet `SPEC_TEXT_NOT_CANONICAL` |
| ensembles | `capabilities`, `repository_read_paths`, `github_surfaces`, `artifact_domains`, `evidence_refs` : triés ascendant par points de code, uniques ; un tableau non trié est **rejeté**, pas retrié ⇒ `SPEC_ARRAY_NOT_CANONICAL` |
| `null` | explicite, jamais omis : un champ absent est un rejet, pas `null` |
| clés | exactement celles du schéma ; clé inconnue ⇒ rejet (`additionalProperties: false`) |

---

## 4. `AgentSpec` V1

Les contraintes **S** sont portées par le schéma ; **V** exige un validateur (le schéma
ne peut pas les exprimer).

| Champ | Contrainte | |
|---|---|---|
| `agent_schema` | constante `AGENT_SPEC_V1` | S |
| `agent_id` | sha256 hex ; = recalcul §2.1 | S + V |
| `agent_spec_id` | sha256 hex ; = recalcul §2.2 | S + V |
| `spec_revision` | entier ≥ 1 ; `1` ⇔ `supersedes_spec_id = null` ; sinon `supersedes_spec_id` = sha256 | S ; continuité V |
| `namespace` | constante `forest` | S |
| `canonical_name` | `^[a-z][a-z0-9_]{2,63}$` | S |
| `display_name` | 1–80 car., sans espace de tête/queue | S |
| `agent_class` | énumération fermée (14) ; classes réservées non enregistrables | S |
| `maintenance_level` | `F0`/`F1`/`F2` ; F3/F4 **rejetés** (réservés) ; max. par classe | S |
| `purpose` | 20–600 car. | S ; NFC V |
| `capabilities` | non vide ; énumération fermée ; ⊆ ensemble du niveau ; triée/unique | S ; ordre V |
| `scope_policy.repository_read_paths` | chemins relatifs POSIX/globs ; pas d'absolu, `..`, `\`, `.env*`, `*.pem/.key/.p12/.pfx`, `id_rsa*`/`id_ed25519*`, répertoire `secret(s)/` | S ; ordre V |
| `scope_policy.repository_write_paths_future` | **tableau vide obligatoire** en V1 (F3 réservé) | S |
| `scope_policy.github_surfaces` | `BRANCHES` `CHECK_RUNS` `COMMITS` `ISSUES` `PULL_REQUESTS` `WORKFLOW_RUNS` — **lecture seule** | S ; cohérence V |
| `scope_policy.artifact_domains` | `CI_ARTIFACTS` `GOVERNANCE_DOCUMENTS` `OPERATOR_API_PROJECTIONS` `PAPER_CERTIFIED_EXPORTS` `RESEARCH_DATASETS_IMMUTABLE` `RESEARCH_PUBLICATIONS` — **lecture seule** ; aucun domaine runtime/VPS/PPL-ledger/FIN-ledger/exchange/secret | S ; cohérence V |
| `independence_policy.own_work_review_forbidden` | constante `true` | S |
| `independence_policy.independent_review_required` | constante `true` | S |
| `authority_policy.authority_ceiling` | constante `NO_RUNTIME_AUTHORITY` | S |
| `authority_policy.human_decision` | constante `false` | S |
| `authority_policy.economic_status_grants_authority` | constante `false` | S |
| `authority_policy.reputation_grants_authority` | constante `false` | S |
| `authority_policy.consensus_grants_authority` | constante `false` (ajout de ce contrat) | S |
| `execution_binding.status` | constante `UNBOUND` | S |
| `execution_binding.provider` | `null` | S |
| `execution_binding.model` | `null` | S |
| `execution_binding.credential_mode` | constante `NONE` | S |
| `supersedes_spec_id` | `null` ou sha256 | S ; chaîne V |
| `created_from_ref` | SHA de commit à 40 hex (un nom de branche/tag est ambigu et rejeté) | S |
| `created_at_utc` | ISO-8601 UTC se terminant par `Z` | S |

Les constantes ci-dessus sont des **constantes sans alternative** : il n'existe aucune
valeur « active », « bound », `provider` renseigné ni credential. Aucun provider
binding réel n'est créé par A1.

---

## 5. Classes d'agents

Vocabulaire fermé (14) : `SENSOR` `SCOUT` `CURATOR` `ENGINEER` `UX` `TEST_VERIFIER`
`FORENSIC` `DATA_STEWARD` `RESEARCH` `STRATEGY` `SECURITY` `SRE` `REVIEWER`
`GOVERNANCE`.

`agent_class` = **métier**. `maintenance_level` = **plafond d'action**. Ils sont
indépendants, à une contrainte près : le **plafond maximal admissible par classe en V1**
(catalogue §6) ; les classes dépendant de F3/F4 sont reconnues mais non
enregistrables.

---

## 6. Capabilities

Catalogue fermé : [AGENT_ECON_A1_CAPABILITY_CATALOG.md](AGENT_ECON_A1_CAPABILITY_CATALOG.md).
Capability inconnue ⇒ **rejet**. Jamais de repli permissif.

---

## 7. États du registre

### 7.1 Vocabulaire

```text
REGISTERED   SUSPENDED   RETIRED
```

`ACTIVE` n'existe pas : ambigu avec un processus en exécution.
**`REGISTERED` = identité connue du registre.** Ce n'est ni « worker en cours »,
ni « autorisé à agir », ni « authentifié », ni « approuvé par un humain ».
Avant le premier événement, un `agent_id` n'a **aucun état** (il est *absent*, ce
qui est distinct de `RETIRED`).

### 7.2 Transitions (changement d'état)

```text
(absent)    → REGISTERED        AGENT_REGISTERED
REGISTERED  → SUSPENDED         AGENT_SUSPENDED
REGISTERED  → RETIRED           AGENT_RETIRED
SUSPENDED   → REGISTERED        AGENT_REINSTATED
SUSPENDED   → RETIRED           AGENT_RETIRED
RETIRED     → (terminal)
```

`AGENT_SPEC_REVISED` n'est **pas** une transition : l'état est inchangé
(`REGISTERED → REGISTERED` ou `SUSPENDED → SUSPENDED`) ; il change `agent_spec_id`
courant. Aucune révision sur un agent `RETIRED`. Toute autre combinaison est rejetée.

| Événement | `previous_state` | `new_state` | `reason_code` permis | `agent_transition_ordinal` |
|---|---|---|---|---|
| `AGENT_REGISTERED` | `null` | `REGISTERED` | `REGISTRATION_INITIAL` | exactement `1` |
| `AGENT_SPEC_REVISED` | = courant (`REGISTERED`\|`SUSPENDED`) | = `previous_state` | `SPEC_REVISION_ESCALATING` \| `…_NON_ESCALATING` \| `…_REDUCING` | ≥ 2 |
| `AGENT_SUSPENDED` | `REGISTERED` | `SUSPENDED` | `SUSPENSION_GOVERNANCE` \| `SUSPENSION_INCIDENT` | ≥ 2 |
| `AGENT_REINSTATED` | `SUSPENDED` | `REGISTERED` | `REINSTATEMENT_GOVERNANCE` | ≥ 2 |
| `AGENT_RETIRED` | `REGISTERED`\|`SUSPENDED` | `RETIRED` | `RETIREMENT_GOVERNANCE` \| `RETIREMENT_SUPERSEDED_BY_NEW_AGENT` | ≥ 2 |

Le schéma d'événement encode la table (hors égalité `previous_state = new_state` pour
une révision, règle V AE-05). Un `AGENT_REINSTATED` **revalide** la spec courante selon
le schéma en vigueur (AE-08) : si la constitution a été amendée et que la spec n'est
plus valide, la réintégration est rejetée ; une révision est nécessaire d'abord.

### 7.3 Disponibilité du registre (≠ état d'un agent)

| Valeur | Sens |
|---|---|
| `NON_DEPLOYED` | aucun registre/artefact n'existe. **Pas** « 0 agent » |
| `UNKNOWN` | un registre existe mais n'est pas lisible/vérifiable, ou sa complétude n'est pas attestée |
| `NOT_CERTIFIABLE` | la chaîne ou une règle est violée (§9.3) ; tous les états d'agents sont `UNKNOWN` |
| `AVAILABLE` | chaîne intégralement vérifiée **et** complétude attestée |

Tant qu'aucun mécanisme authentifié de complétude/anti-retour n'existe (§9.4, même
famille que la Gate O de #315), un décompte d'agents ne peut être affiché ni contractualisé :
`NON_DEPLOYED` ou `UNKNOWN`. Un registre vide-mais-attesté est `AVAILABLE` avec liste vide ;
un registre absent n'est jamais « vide ». `UNKNOWN ≠ 0`.

### 7.4 Qui peut écrire (A1)

- **Aucun agent** ne peut enregistrer, réviser, suspendre, réintégrer ni retirer un
  agent, y compris lui-même (`AGENT_SPEC_SELF_REVISE`, `AUTHORITY_DELEGATE`).
- Un agent peut *proposer* ; l'ajout d'un événement est l'acte d'un **registrar** agissant
  sur une décision de gouvernance humaine (PR humaine fusionnée).
- Le registrar n'existe pas et n'est pas défini : son identité et son authentification
  sont **non résolues** (même famille que ADR-0020 §3 ; question ouverte Q1).
  Aucune spec ni aucun événement ne peut déclarer sa propre autorisation.

---

## 8. Événements

### 8.1 Types

```text
AGENT_REGISTERED   AGENT_SPEC_REVISED   AGENT_SUSPENDED   AGENT_REINSTATED   AGENT_RETIRED
```

### 8.2 `AgentRegistryEvent` V1 — champs (tous obligatoires)

```text
event_schema              = "AGENT_REGISTRY_EVENT_V1"
event_id                  sha256 (§8.3)
registry_sequence         entier ≥ 1, global, contigu (§9.1)
agent_transition_ordinal  entier ≥ 1, par agent, contigu (§9.1)
agent_id                  sha256
agent_spec_id             sha256 — spec courante APRÈS l'événement
event_type                énumération fermée (§8.1)
previous_state            null | REGISTERED | SUSPENDED
new_state                 REGISTERED | SUSPENDED | RETIRED
reason_code               énumération fermée (§8.5)
reason_detail             string | null (≤ 1000 car. ; hors event_id, dans event_hash)
evidence_refs[]           non vide, triée/unique, grammaire fermée (§8.4)
occurred_at_utc           ISO-8601 UTC, suffixe Z
previous_event_hash       "GENESIS" si registry_sequence = 1, sinon sha256
event_hash                sha256 (§8.6)
```

### 8.3 `event_id` — identité déterministe (idempotence)

```text
event_id = SHA256( canonical_json({
    "agent_event_identity_schema": "agent-econ.a1.agent-event-identity.v1",
    "agent_id", "agent_transition_ordinal", "event_type",
    "previous_state", "new_state", "agent_spec_id",
    "evidence_refs", "reason_code"
}) )
```

Exclus : `registry_sequence`, `occurred_at_utc`, `reason_detail`, hashes de chaîne —
sur le modèle de `candidate_event_identity`. Une requête répétée désigne le même
`event_id` ; elle est idempotente si l'événement existe à l'identique, sinon rejetée
(AC-04).

### 8.4 Grammaire de `evidence_refs`

Fermée ; toute autre forme est rejetée :

```text
github:issue:<entier>
github:pr:<entier>@<sha40>
git:commit:<sha40>
sha256:<hex64>
```

Pas d'URL libre ni de texte libre (empêche aussi qu'un secret soit glissé dans une
référence). Tout événement a ≥ 1 référence : **aucune transition sans preuve**.
`AGENT_REGISTERED`, `AGENT_SPEC_REVISED` (escalade) et `AGENT_REINSTATED` exigent en
outre ≥ 1 référence `github:pr:…@sha40` ou `git:commit:…` (règle V AE-09) qui ancre la
spec dans une source gouvernée. **Le registre ne vérifie pas qu'elle est approuvée par
un humain** ; il rend seulement l'affirmation inspectable (voir Q1).

### 8.5 `reason_code` (fermé)

`REGISTRATION_INITIAL` · `SPEC_REVISION_ESCALATING` · `SPEC_REVISION_NON_ESCALATING` ·
`SPEC_REVISION_REDUCING` · `SUSPENSION_GOVERNANCE` · `SUSPENSION_INCIDENT` ·
`REINSTATEMENT_GOVERNANCE` · `RETIREMENT_GOVERNANCE` ·
`RETIREMENT_SUPERSEDED_BY_NEW_AGENT`.

### 8.6 `event_hash` — chaîne

```text
event_hash = SHA256( canonical_json( event without the field "event_hash" ) )
```

Il couvre donc `previous_event_hash`, `registry_sequence`, `occurred_at_utc`,
`reason_detail` et `event_id`. Le premier événement porte `previous_event_hash =
"GENESIS"` (littéral, comme `durable_store.py`).

---

## 9. Intégrité

### 9.1 Chaîne

```text
GENESIS
   ↓
EVENT 1  (hash h1, previous = "GENESIS")
   ↓
EVENT 2  (hash h2, previous = h1)
   ↓
EVENT N  (hash hN, previous = h(N-1))
```

### 9.2 Règles de validation et codes d'échec

Aucune n'est réparée silencieusement. Toute violation ⇒ rejet de l'ajout, ou
`NOT_CERTIFIABLE` à la lecture.

**Spec (`AS-`)**

| ID | Règle | Code |
|---|---|---|
| AS-01 | validation du schéma fermé | `SPEC_SCHEMA_VIOLATION` |
| AS-02 | nombres : entiers purs | `SPEC_NUMERIC_AMBIGUITY` |
| AS-03 | texte NFC, sans contrôle ni espace de bord | `SPEC_TEXT_NOT_CANONICAL` |
| AS-04 | tableaux d'ensemble triés et uniques | `SPEC_ARRAY_NOT_CANONICAL` |
| AS-05 | jeton de capability : interdit ⇒ `FORBIDDEN_AUTHORITY_REQUESTED` ; réservé ⇒ `RESERVED_CAPABILITY` ; inconnu ⇒ `UNKNOWN_CAPABILITY` | idem |
| AS-06 | capabilities ⊆ ensemble du niveau | `CAPABILITY_ABOVE_CEILING` |
| AS-07 | classe/niveau admissibles (classes réservées incluses) | `CLASS_LEVEL_INADMISSIBLE` |
| AS-08 | `authority_policy` = constantes exactes | `AUTHORITY_POLICY_VIOLATION` |
| AS-09 | `execution_binding` = `UNBOUND`/`null`/`null`/`NONE` | `BINDING_NOT_UNBOUND` |
| AS-10 | `independence_policy` = constantes exactes | `INDEPENDENCE_POLICY_VIOLATION` |
| AS-11 | `agent_id` et `agent_spec_id` = recalculs | `IDENTITY_MISMATCH` |
| AS-12 | révision 1 ⇔ pas de prédécesseur ; révision n+1 supersede la spec courante du **même** `agent_id`, `spec_revision` = courant+1 | `SUPERSESSION_BREAK` |
| AS-13 | cohérence capability ↔ périmètre (catalogue §2) | `SCOPE_CAPABILITY_INCOHERENT` |

**Événement (`AE-`)**

| ID | Règle | Code |
|---|---|---|
| AE-01 | schéma d'événement fermé | `EVENT_SCHEMA_VIOLATION` |
| AE-02 | entiers purs | `EVENT_NUMERIC_AMBIGUITY` |
| AE-03 | `event_id` = recalcul | `EVENT_ID_MISMATCH` |
| AE-04 | `event_hash` = recalcul | `EVENT_HASH_MISMATCH` |
| AE-05 | état précédent = état projeté courant ; transition légale (§7.2) ; révision conserve l'état | `ILLEGAL_TRANSITION` |
| AE-06 | `reason_code` compatible avec `event_type` | `REASON_CODE_MISMATCH` |
| AE-07 | `evidence_refs` non vide, grammaire fermée, triée/unique | `EVIDENCE_INVALID` |
| AE-08 | la spec référencée est **publiée** (§12), son `agent_id` = celui de l'événement ; REGISTERED ⇒ `spec_revision = 1` ; REVISED ⇒ supersede la courante ; SUSPENDED/RETIRED ⇒ `agent_spec_id` inchangé ; REINSTATED ⇒ spec courante revalidée (AS-01…AS-13) | `SPEC_REFERENCE_INVALID` |
| AE-09 | ancrage source exigé (§8.4) | `SOURCE_ANCHOR_MISSING` |
| AE-10 | `reason_code` d'une révision = classification calculée (§10) | `REVISION_CLASS_MISMATCH` |

**Chaîne (`AC-`)**

| ID | Règle | Code |
|---|---|---|
| AC-01 | `registry_sequence` commence à 1, +1 strict, sans trou ni doublon | `SEQUENCE_GAP_OR_DUPLICATE` |
| AC-02 | `previous_event_hash` = `GENESIS` ssi séquence 1, sinon `event_hash` de N−1 | `CHAIN_BREAK` |
| AC-03 | `agent_transition_ordinal` commence à 1 et est contigu par agent | `ORDINAL_GAP` |
| AC-04 | `event_id` unique ; une réémission identique est idempotente (`ALREADY_APPENDED_IDENTICAL`), toute autre collision est rejetée | `EVENT_ID_COLLISION` |
| AC-05 | aucun événement après `AGENT_RETIRED` pour cet agent | `EVENT_AFTER_TERMINAL` |
| AC-06 | régression d'horodatage : **anomalie rapportée**, jamais rupture ; l'ordre d'autorité est `registry_sequence` | `TIMESTAMP_REGRESSION` (WARN) |

**Projection (`AP-`)**

| ID | Règle |
|---|---|
| AP-01 | la projection est une fonction pure de (événements ordonnés, specs publiées) |
| AP-02 | toute violation AS/AE/AC ⇒ registre `NOT_CERTIFIABLE`, **tous** les états d'agents `UNKNOWN` ; pas de « dernier bon état » servi comme vérité |
| AP-03 | états autorisés : `REGISTERED`, `SUSPENDED`, `RETIRED` ; `absent` ≠ `RETIRED` |
| AP-04 | la projection n'émet jamais `ACTIVE`, « running », ni un décompte d'agents « vivants » |
| AP-05 | disponibilité ∈ {`NON_DEPLOYED`, `UNKNOWN`, `NOT_CERTIFIABLE`, `AVAILABLE`} (§7.3) |
| AP-06 | un diagnostic du préfixe vérifié peut être exposé **étiqueté** `PREFIX_ONLY_UNCERTIFIED`, jamais comme état |

### 9.3 Non-certifiabilité

Une rupture (AC-01, AC-02, AC-03, AE-03/04 sur un événement existant, spec publiée
manquante ou altérée) rend le registre `NOT_CERTIFIABLE`. Il n'existe **aucune
réparation silencieuse** : ni recalcul de hash, ni réécriture, ni troncature « pour
repartir ». Une récupération est une décision de gouvernance humaine avec preuve
conservée (CLAUDE.md §5 : préserver journaux/preuves).

### 9.4 Limites : intégrité ≠ authenticité ≠ autorité

La chaîne détecte une corruption ou une édition **partielle**. Elle **ne détecte pas** :

- une réécriture cohérente complète par quelqu'un qui peut écrire le support
  (la chaîne est recalculable — ADR-0020 §2/M5, constat #315) ;
- une **troncature de queue** (sans ancre externe, un préfixe valide est indistinguable
  d'un registre complet) ;
- l'identité de qui a écrit (aucun champ d'acteur dans le schéma minimal imposé).

Donc, tant qu'une ancre anti-retour indépendante et une authentification du registrar
n'existent pas : `AVAILABLE` n'est pas atteignable et le registre est au plus
`UNKNOWN`/`NON_DEPLOYED`. Un registre `REGISTERED` ne prouve **jamais** qu'un humain a
approuvé l'agent.

---

## 10. Classification des révisions de spec

Calcul **déterministe** entre la spec courante `P` et la nouvelle `N` (même `agent_id`) :

1. `ESCALATING` si **au moins un** accroissement : niveau(N) > niveau(P) ; `capabilities(N) ⊄ capabilities(P)` ;
   un chemin de `repository_read_paths(N)` absent à l'identique de `P` (les globs ne
   se comparent pas par inclusion : toute chaîne ajoutée ou modifiée est une escalade) ;
   `github_surfaces(N) ⊄ P` ; `artifact_domains(N) ⊄ P`.
2. sinon `REDUCING` si au moins une réduction stricte (niveau plus bas, ou ensemble
   strictement plus petit).
3. sinon `NON_ESCALATING`.

Précédence : accroissement > réduction > neutre. Le `reason_code` de l'événement doit
**égaler** cette classification (AE-10). `agent_class`, `authority_policy`,
`execution_binding`, `independence_policy` ne peuvent pas changer en V1 (constantes ;
classe ⇒ nouvel `agent_id`). L'**autorisation** d'une escalade est une décision
humaine externe : A1 la rend lisible (ancrage AE-09) sans pouvoir l'authentifier.

---

## 11. Publication write-once des specs (design)

Sur le modèle de `publish_candidate` :

| ID | Règle |
|---|---|
| AW-01 | une spec est publiée sous une clé = `agent_spec_id` (sous `agent_id`) ; emplacement choisi par la mission SOURCE, **hors** de tout répertoire lu/écrit par Advisor, PPL, FIN ou PAPER |
| AW-02 | création exclusive atomique (`O_CREAT\|O_EXCL`, fsync), permissions restreintes |
| AW-03 | octets publiés = `json.dumps(spec, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"` ; identique ⇒ `ALREADY_EXISTS_IDENTICAL` ; octets différents sous le même `agent_spec_id` ⇒ `AGENT_SPEC_PROVENANCE_CONFLICT` (même matière, provenance différente) ou `AGENT_SPEC_ID_COLLISION_OR_CORRUPTION` (matière différente) — **jamais d'écrasement** |
| AW-04 | la spec est publiée **avant** l'événement qui la référence ; un événement référençant une spec non publiée est rejeté (AE-08) |
| AW-05 | une spec publiée n'est jamais modifiée ni supprimée, même pour un agent `RETIRED` |
| AW-06 | la publication d'une spec **ne crée aucun état** : l'état naît uniquement d'un événement |

Le stockage des événements (SQLite, JSONL…) n'est **pas** décidé ici ; la mission SOURCE
doit produire son ADR (précédent : `docs/adr/0019-stockage-durable-operator-decision-d5b-r2.md`)
avec preuves de crash/concurrence. Exigences minimales : ajout atomique, séquence
contiguë garantie, unicité de `event_id` et d'`event_hash`, vérification de chaîne à la
lecture (fail-closed).

---

## 12. Exclusions explicites (A2+)

Le registre ne contient, ne calcule et ne référence : aucun problème (A2), bounty,
claim, récompense (A3), wallet, solde, AIC, treasury, réputation (A4/A11), coût (A5),
worker, scheduler, sandbox, provider, modèle, credential (A6), review exécutable (A7),
mutation GitHub (A8). Les champs `execution_binding` sont des constantes `UNBOUND`.

---

## 13. Critères de préparation pour la mission A1 SOURCE

Une mission ultérieure peut implémenter, **sans réinventer les règles de gouvernance** :

| Capacité | Règles qui la définissent | Preuve attendue à la livraison |
|---|---|---|
| validation d'`AgentSpec` | §3.2, §4, AS-01…AS-13 | un cas négatif par ID ; schéma ≡ catalogue (catalogue §9) |
| `agent_id` déterministe | §2.1 | vecteurs issus d'entrées gouvernées ; stabilité à travers `agent_schema` |
| `agent_spec_id` déterministe | §2.2, §3 | sensibilité matérielle / insensibilité provenance |
| validation de capabilities | catalogue §1–§4 | trois codes de rejet distincts |
| validation d'événements | §8, AE-01…AE-10 | un cas négatif par ID |
| projection d'états | §7, AP-01…AP-06 | rupture ⇒ `NOT_CERTIFIABLE` ; aucun `ACTIVE` ; aucun décompte |
| publication write-once | §11, AW-01…AW-06 | concurrence, identique, collision, spec absente |
| vérification de chaîne | §9, AC-01…AC-06 | troncature, réordonnancement, réécriture, doublon, trou |

Tests proposés (noms indicatifs, **non livrés**) : `test_unknown_capability_rejected`,
`test_forbidden_authority_distinct_from_unknown`, `test_reserved_f3_f4_rejected`,
`test_f0_read_only_matrix`, `test_authority_policy_constants`,
`test_binding_must_be_unbound`, `test_agent_id_stable_across_schema_version`,
`test_spec_id_material_vs_provenance`, `test_numeric_float_one_rejected`,
`test_nfc_required`, `test_unsorted_array_rejected_not_sorted`,
`test_registered_is_not_running`, `test_no_active_state_emitted`,
`test_chain_break_makes_registry_not_certifiable`,
`test_tail_truncation_requires_external_anchor_or_unknown`,
`test_event_after_retired_rejected`, `test_reinstate_revalidates_spec`,
`test_revision_class_must_match_computed`, `test_write_once_collision_fails_closed`,
`test_registry_absent_is_non_deployed_not_zero`.

La mission SOURCE reste soumise à : #284 l'autorisant explicitement ; #286 actif
(aucun changement runtime) ; revue indépendante ; CI au HEAD exact.

---

## 14. Questions ouvertes (aucune masquée)

| # | Question | Pourquoi ouverte |
|---|---|---|
| Q1 | Qui est le **registrar** (identité, authentification, garde de clés) et comment prouve-t-on qu'un événement reflète une décision humaine ? | non défini ; même famille que la Gate O (#315, ADR-0020 §3). A1 ne peut pas l'inventer |
| Q2 | Ancre anti-retour / attestation de complétude du registre | sans elle, `AVAILABLE` est inatteignable (§9.4) |
| Q3 | Définition d'**indépendance** plus forte que `agent_id` différent (modèle, credential, contexte) | A7 ; risque d'erreurs corrélées |
| Q4 | Le schéma minimal imposé n'a pas de champ d'acteur ; faut-il un `registrar_ref` en V2 ? | provenance faible aujourd'hui |
| Q5 | Une lecture runtime read-only est-elle un jour souhaitable pour SRE/forensic ? | exclue par A0 §9 ; amendement humain requis |
| Q6 | Frontière domaine Research ↔ forêt (`RESEARCH`, `STRATEGY` plafonnés F1) | leurs sorties doivent entrer par les contrats `RL-*`, pas par la forêt |
| Q7 | Qui peut ajouter des événements « dans le sens sûr » (`SUSPENDED`, `RETIRED`) sans le cérémonial complet ? | compromis disponibilité du frein / contrôle d'accès |
| Q8 | Protection CODEOWNERS de `docs/contracts/AGENT_ECON_*` | non couverte (A0 §16, I8) |

---

## 15. Verdict

`AGENT_ECON_A1_AGENT_REGISTRY_CONTRACT_READY_FOR_REVIEW`

Non déclaré : `CERTIFIED`, `AGENT_ECONOMY_DEPLOYED`,
`AGENT_ECONOMY_ARCHITECTURE_CERTIFIED`. Aucune capacité d'exécution n'est créée ;
#286 reste actif.
