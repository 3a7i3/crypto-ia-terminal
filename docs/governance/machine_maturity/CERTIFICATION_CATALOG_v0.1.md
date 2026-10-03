# MACHINE-MATURITY Certification Catalog v0.1

Status: FROZEN INPUT CANDIDATE for #365 MACHINE-MATURITY-01  
Source framework: #362 MACHINE-MATURITY-00  
Catalog version: `MACHINE-MATURITY-CATALOG-v0.1`  
Materialization base: `main@da1973dd5c901a757e4fb7da45adee150500c9bd`

## Canonicalization rule

This artifact is a byte-preserving governance materialization of the three R2
catalog comments listed below, in ascending phase order R2-A → R2-B → R2-C.
The Markdown bodies are copied verbatim after the separators.

Canonical source comments:
- #362 comment 5971120146 — R2-A
- #362 comment 5971148753 — R2-B
- #362 comment 5971167870 — R2-C

The Git blob identity of this file is the content-addressed `catalog_hash`
used by MM-01 after review/merge. Editing this file creates a new catalog
identity/version and cannot silently mutate v0.1.

---

<!-- BEGIN CANONICAL COMMENT 5971120146 -->
# R2-A — CERTIFICATION CATALOG v0.1 — SÉMANTIQUE + L0→L3

Baseline R2 :

`main@eeaec5ae29a72b765bb97feb46520032aba44e2a`

Cette baseline inclut désormais le merge contract-only de PR #348. Ce fait ajoute de la preuve ARCHITECTURE/SOURCE future pour L5/L6, mais **aucune capacité runtime**, aucun agent actif et aucune autorité supplémentaire.

R2 transforme R1 en contrat normatif. Il n’émet aucun certificat de niveau.

---

# 1. Schéma normatif d’un critère

Chaque critère du Certification Catalog doit être représentable comme :

```text
MachineMaturityCriterion {
    criterion_id
    level_id
    title
    statement

    mandatory

    proof_requirement {
        all_of[]
        one_of[]
    }

    accepted_evidence_types[]
    forbidden_substitutions[]
    dependencies[]
    forbidden_states[]
    revocation_invariants[]

    current_assessment
    satisfied_by[]
    unresolved_reason
}
```

## 1.1 current_assessment

Valeurs autorisées dans R2 :

- `SATISFIED`
- `UNRESOLVED`
- `NOT_AVAILABLE`

### SATISFIED

Toutes les classes de preuve exigées existent dans le corpus admissible, les dépendances du critère sont satisfaites au niveau de l’évidence, aucun forbidden state n’est actif pour ce critère et aucune substitution interdite n’a été utilisée.

`SATISFIED != CERTIFIED`

### UNRESOLVED

Des preuves pertinentes existent, mais au moins une condition obligatoire reste non démontrée, contradictoire, trop ancienne, non agrégée ou conditionnelle.

### NOT_AVAILABLE

Aucune preuve admissible ne démontre actuellement le critère.

## 1.2 mandatory

Tous les critères R2 ci-dessous sont `mandatory=true` sauf mention explicite contraire.

Aucun score moyen et aucun pourcentage ne peut compenser un mandatory criterion manquant.

## 1.3 proof_requirement

Syntaxe :

```text
ALL_OF(A, B)
ONE_OF(C, D)
```

Exemple :

```text
ALL_OF(
  GOVERNANCE_PROOF,
  ONE_OF(SOURCE_PROOF, ARCHITECTURE_PROOF)
)
```

## 1.4 accepted evidence

Peuvent être admis selon le critère :

- verdict GitHub avec scope explicite;
- code/contrat versionné au SHA exact;
- CI exacte;
- durable artifact avec identité/hash;
- runtime witness horodaté;
- experiment manifest / dataset / publication immuable;
- browser/UX proof;
- security boundary proof;
- operator/governance authorization;
- rollback/quiescence proof.

Une issue, un commentaire ou un nom de feature seuls ne suffisent pas.

## 1.5 forbidden substitutions globales

Interdictions applicables à tout le catalogue :

- SOURCE_PROOF → RUNTIME_PROOF;
- ARCHITECTURE_PROOF → deployed capability;
- CI green → runtime behavior;
- screenshot synthétique → runtime fact;
- experiment PASS → machine-level certification;
- historical proof → current runtime proof sans identité compatible;
- UNKNOWN / UNRESOLVED / NOT_AVAILABLE → 0 / false / healthy;
- NON_DEPLOYED → available;
- merged PR → certified capability;
- issue closed → certification;
- feature existence → level satisfaction;
- upper-level evidence → missing lower-level criterion.

## 1.6 dépendances et certification

Un niveau Lx ne peut être formellement certifié que si :

1. tous ses mandatory criteria = `SATISFIED`;
2. tous les niveaux L0…L(x-1) possèdent une certification valide;
3. aucune revocation/dependency invalidation n’est active;
4. un evidence manifest borné existe;
5. un `MachineLevelCertification` est émis.

R2 n’exécute pas l’étape 5.

## 1.7 révocation

Un certificat historique n’est jamais effacé.

Deux mécanismes doivent être distingués :

- `DIRECT_REVOCATION` : un invariant du niveau certifié est démontré faux;
- `DEPENDENCY_INVALIDATION` : un niveau inférieur requis n’est plus valide.

Dans les deux cas, le `Formal Certified Frontier` doit reculer jusqu’au dernier niveau dont la chaîne reste valide.

---

# 2. L0 — CONSTITUTIONAL FOUNDATION

## PURPOSE

Prouver que la machine possède une constitution de vérité, d’autorité, de preuve et de changement suffisamment stricte pour empêcher qu’une feature, une observation ou une absence de donnée soit confondue avec une capacité certifiée.

## ENTRY_CONDITIONS

Aucune certification de niveau précédente requise.

---

## L0-G1 — Authority constitution & domain separation

**Statement**

Les autorités Decision / PAPER-PPL / FIN / Research / Operator / Agent / TESTNET-LIVE doivent être explicitement séparées, avec interdiction de promotion implicite.

**proof requirement**

`ALL_OF(GOVERNANCE_PROOF, SOURCE_PROOF)`

**accepted evidence**

#148, #180/#184, #237, #240, #284, #286, contrats d’autorité.

**forbidden substitutions**

- architecture diagram seule;
- nom de service;
- présence d’un module;
- absence d’écriture observée.

**dependencies**

aucune.

**forbidden states**

- dual authority non gouvernée;
- fallback silencieux entre autorités;
- agent/Research/UI pouvant devenir autorité implicite.

**revocation invariants**

Révoquer L0 si une nouvelle voie permet une mutation authoritative sans passer par une autorité explicitement gouvernée ou si deux sources concurrentes revendiquent simultanément la même vérité authoritative.

**assessment**

`SATISFIED`

**satisfied by**

MM-EV-L0-008 + MM-EV-L2-001 + MM-EV-L3-004.

---

## L0-G2 — Proof-type separation / no proof substitution

**Statement**

SOURCE, RUNTIME, EXPERIMENT, ARCHITECTURE, GOVERNANCE, UX et SECURITY doivent rester des classes distinctes; aucune classe plus faible ne peut être substituée à une classe requise.

**proof requirement**

`ALL_OF(GOVERNANCE_PROOF, SOURCE_PROOF)`

**accepted evidence**

#362 R1-A, historique #148, missions séparant explicitement SOURCE PROOF / RUNTIME PROOF.

**forbidden substitutions**

toutes les substitutions globales §1.5.

**dependencies**

L0-G1.

**forbidden states**

un verdict global construit à partir d’une preuve de classe incorrecte.

**revocation invariants**

Toute certification nouvelle qui traite SOURCE comme RUNTIME sans preuve séparée invalide ce critère.

**assessment**

`SATISFIED`

---

## L0-G3 — Fail-closed epistemic semantics

**Statement**

`UNKNOWN`, `UNRESOLVED`, `NOT_AVAILABLE`, `NOT_APPLICABLE`, `NON_DEPLOYED` et zéro explicite doivent conserver des sémantiques non interchangeables.

**proof requirement**

`ALL_OF(SOURCE_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

#201, #268, #237/#248, #307/#315, #362 R1-A.

**forbidden substitutions**

- null→0;
- missing→false;
- unavailable→empty healthy state;
- N/A→zero;
- non deployed→available.

**dependencies**

L0-G2.

**forbidden states**

consumer canonique fabriquant un zéro ou un PASS depuis une absence.

**revocation invariants**

Toute régression canonique transformant missing/unresolved en valeur factuelle révoque ce critère.

**assessment**

`SATISFIED`

---

## L0-G4 — Governed change control

**Statement**

Les changements à portée scientifique/opérationnelle doivent être bornés par identité source, scope, tests, autorisation lorsque nécessaire, preuves et rollback/stop conditions.

**proof requirement**

`ALL_OF(GOVERNANCE_PROOF, SOURCE_PROOF)`

**accepted evidence**

#199, #211, #212, #214, #218→#233, #255, #278/#279, #286.

**forbidden substitutions**

- CI générique sans SHA;
- owner intent implicite;
- merge sans scope;
- remediation cachée dans certification-only.

**dependencies**

L0-G1, L0-G2.

**forbidden states**

mutation non attribuable ou non bornée d’une surface authoritative.

**revocation invariants**

Une mutation authoritative non traçable ou un bypass volontaire d’un gate obligatoire invalide L0-G4.

**assessment**

`SATISFIED`

---

## L0-G5 — Immutable evidence history, supersession & revocation boundary

**Statement**

Les preuves historiques restent append-only/logiquement immuables; une preuve ultérieure peut supersede une conclusion mais ne doit pas réécrire l’historique. Les certifications de niveau doivent être révocables sans suppression.

**proof requirement**

`ALL_OF(GOVERNANCE_PROOF, SOURCE_PROOF)`

**accepted evidence**

historique #225 remediation→certified, #231 contract correction→final certification, #268 resync→certification, #362 R1 EvidenceRecord disposition/supersession.

**forbidden substitutions**

- suppression d’un ancien FAIL;
- édition rétroactive pour faire croire qu’un blocker n’a jamais existé;
- certificat mutable en place.

**dependencies**

L0-G2, L0-G4.

**forbidden states**

historique impossible à reconstruire ou certificat remplacé sans chaîne.

**revocation invariants**

Si evidence lineage/supersession n’est plus reconstructible ou si un certificat peut être muté sans trace, révoquer.

**assessment**

`SATISFIED`

### L0 R2 assessment

`5/5 mandatory criteria = SATISFIED`

Statut de niveau R2 :

`READY_FOR_REVIEW`

Aucun `LEVEL_0_CERTIFIED` n’est émis.

---

# 3. L1 — OBSERVABLE MACHINE

## PURPOSE

Prouver que la machine peut exposer son état et ses décisions de manière structurée, provenance-bound, fail-closed et non-authoritative, avec des preuves runtime suffisantes pour distinguer état réel, stale, absent et dégradé.

## ENTRY_CONDITIONS

L0 evidence assessment = SATISFIED.
La certification formelle future exigera L0 officiellement CERTIFIED.

---

## L1-G1 — Structured machine observation & decision provenance

**Statement**

Les décisions et états critiques doivent être observables avec identités, timestamps et provenance, sans dépendre uniquement de logs narratifs.

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

DecisionPacket/DecisionIdentity, operator snapshots, #223 provenance runtime, #175 producer artifacts.

**forbidden substitutions**

log text seul; screenshot seul.

**dependencies**

L0-G2, L0-G3.

**forbidden states**

état courant sans timestamp/provenance ou origine impossible à attribuer.

**revocation invariants**

Perte durable des identités/timestamps/provenance sur les observations canoniques.

**assessment**

`SATISFIED`

---

## L1-G2 — Durable event truth & deterministic replay

**Statement**

Au moins une vérité lifecycle canonique doit être append-only/durable, ordonnée, idempotente et rejouable de manière déterministe.

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

#154 PPL-02B + #167 runtime SHADOW + #180/#184 authority cutover.

**forbidden substitutions**

JSONL legacy simplement cohérent; snapshot mutable; mémoire process.

**dependencies**

L0-G1, L0-G4.

**forbidden states**

duplicate event identity, replay divergent, corruption silencieusement acceptée.

**revocation invariants**

Échec reproductible du replay déterministe ou append non idempotent.

**assessment**

`SATISFIED`

---

## L1-G3 — Read-only operator observation surface

**Statement**

Une surface opérateur doit pouvoir lire la machine sans obtenir par défaut une autorité de mutation.

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, UX_PROOF)`

**accepted evidence**

#162 WEB-01, #164 WEB-01B, #175 WEB-02.

**forbidden substitutions**

frontend source-only; API mutante non séparée; direct file read depuis React.

**dependencies**

L1-G1.

**forbidden states**

mutation implicite depuis une route/surface présentée comme observation.

**revocation invariants**

Si l’interface read-only acquiert un side effect non gouverné, révoquer.

**assessment**

`SATISFIED`

---

## L1-G4 — Provenance / freshness / uncertainty visible

**Statement**

Les observations doivent exposer provenance, fraîcheur et états d’incertitude sans fake health/convergence.

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

#162, #171 finding/remediation lineage, #175, #223, #309.

**forbidden substitutions**

freshness recalculée arbitrairement côté UI; UNKNOWN masqué; stale présenté live.

**dependencies**

L0-G3, L1-G1.

**forbidden states**

source future-skew/non attribuée traitée comme saine; stale silencieux.

**revocation invariants**

Toute présentation canonique de données stale/unresolved comme live/known.

**assessment**

`SATISFIED`

---

## L1-G5 — Runtime health / recovery observability

**Statement**

Le runtime doit pouvoir prouver process identity, restart/recovery state et continuité des artefacts critiques.

**proof requirement**

`RUNTIME_PROOF`

**accepted evidence**

#164, #167, #174, #175, #223, #309, #319.

**forbidden substitutions**

source tests seuls; systemd template sans observation réelle.

**dependencies**

L1-G1.

**forbidden states**

service supposé running sans witness; restart ayant muté des faits sans attribution.

**revocation invariants**

Perte de capacité à attribuer restart/process/runtime identity sur les surfaces déclarées canoniques.

**assessment**

`SATISFIED`

---

## L1-G6 — Observability is non-authoritative

**Statement**

Les surfaces d’observabilité ne doivent ni recalculer ni modifier la vérité qu’elles exposent.

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

WEB-01/02, #241 domain separation, Direction contracts.

**forbidden substitutions**

React formula; UI-side accounting; observation writer mutating PPL/FIN.

**dependencies**

L0-G1, L1-G3.

**forbidden states**

consumer devenant source de vérité scientifique.

**revocation invariants**

Toute dépendance authoritative inversée Operator/UI → PPL/FIN/Research.

**assessment**

`SATISFIED`

### L1 R2 assessment

`6/6 mandatory criteria = SATISFIED`

Statut de niveau R2 :

`READY_FOR_REVIEW`

Aucun `LEVEL_1_CERTIFIED`.

---

# 4. L2 — GOVERNED PAPER MACHINE

## PURPOSE

Prouver qu’un lifecycle PAPER possède une autorité unique et rejouable, une identité d’expérience/config/capital gouvernée, une finance déterministe/réconciliable et au moins une expérience PAPER complètement clôturée et certifiée.

## ENTRY_CONDITIONS

L0/L1 evidence assessments SATISFIED.
Certification future : L0/L1 formellement CERTIFIED.

---

## L2-G1 — Single governed PAPER lifecycle authority

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

#180/#181/#182/#183/#184, verdict `PPL_02E_RUNTIME_CUTOVER_CERTIFIED`.

**forbidden substitutions**

SHADOW authority; Legacy+PPL dual authority; compatibility ledger.

**dependencies**

L0-G1, L1-G2.

**forbidden states**

deux lifecycle authorities actives ou fallback silencieux.

**revocation invariants**

Réapparition d’un second authoritative writer.

**assessment**

`SATISFIED`

---

## L2-G2 — Replay-complete lifecycle & restart determinism

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

PPL schema v2, #222, #232, #246, #255.

**forbidden substitutions**

reconstruction depuis config courante; legacy inferred facts.

**dependencies**

L2-G1.

**forbidden states**

restart modifiant OPEN/CLOSE/fees/capital ou nécessitant données inventées.

**revocation invariants**

replay divergent ou recovery non déterministe.

**assessment**

`SATISFIED`

---

## L2-G3 — Governed epoch / config / capital identity

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, EXPERIMENT_PROOF)`

**accepted evidence**

#219/#220/#222/#225/#226.

**forbidden substitutions**

Git SHA seul; env partiel; capital fallback.

**dependencies**

L2-G1, L0-G4.

**forbidden states**

epoch/config/capital non fingerprintés ou mismatch accepté.

**revocation invariants**

lifecycle scientifique poursuivi sous config non liée au manifest.

**assessment**

`SATISFIED`

---

## L2-G4 — Controlled admission & runtime authority boundary

**proof requirement**

`ALL_OF(RUNTIME_PROOF, GOVERNANCE_PROOF, EXPERIMENT_PROOF)`

**accepted evidence**

#225/#230/#231/#255.

**forbidden substitutions**

process running = admissions open; signal actionable = trade accepted.

**dependencies**

L2-G1, L2-G3.

**forbidden states**

admission ouverte sans owner/gate; Watchdog/LIVE implicite.

**revocation invariants**

nouvelle admission hors overlay/gate gouverné.

**assessment**

`SATISFIED`

---

## L2-G5 — Financial semantics & deterministic projection

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

#244 FIN-00 + #245 FIN-01 + #246 deterministic replay.

**forbidden substitutions**

PPL realized_pnl = FIN realized_pnl sans définition; UI formulas.

**dependencies**

L2-G1, L2-G2.

**forbidden states**

double release; capital créé/détruit silencieusement; unknown marks→0.

**revocation invariants**

projection financière non déterministe ou double application.

**assessment**

`SATISFIED`

---

## L2-G6 — Reconciliation / no silent correction

**proof requirement**

`ALL_OF(RUNTIME_PROOF, SOURCE_PROOF)`

**accepted evidence**

#247 FIN-02 + #256 Track D.

**forbidden substitutions**

arrondi silencieux; divergence cachée; non-comparable marqué equal.

**dependencies**

L2-G5.

**forbidden states**

écart matériel non visible ou unresolved capital masqué.

**revocation invariants**

reconciliation comparable hors tolérance non signalée.

**assessment**

`SATISFIED`

---

## L2-G7 — Completed governed scientific PAPER experiment

**proof requirement**

`ALL_OF(EXPERIMENT_PROOF, RUNTIME_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

#231/#233/#255/#256.

**forbidden substitutions**

burn-in actif; population partielle; source-only replay.

**dependencies**

L2-G1…G6.

**forbidden states**

open residual, unresolved lifecycle caché, admissions encore ouvertes durant final certification.

**revocation invariants**

preuve gouvernée que la population certifiée a été modifiée/réécrite ou que son identité n’est plus reconstructible.

**assessment**

`SATISFIED`

### L2 R2 assessment

`7/7 mandatory criteria = SATISFIED`

Statut de niveau R2 :

`READY_FOR_REVIEW`

Aucun `LEVEL_2_CERTIFIED`.

---

# 5. L3 — SCIENTIFIC RESEARCH MACHINE

## PURPOSE

Prouver qu’une machine peut transformer des faits PAPER immuables en datasets Research identifiés, replayables et diagnostiquables, produire des candidats gouvernés et préserver strictement la frontière Research → active epoch.

## ENTRY_CONDITIONS

L0→L2 evidence assessments SATISFIED.
Certification future : L0→L2 formellement CERTIFIED.

---

## L3-G1 — Immutable PAPER → Research dataset/provenance

**proof requirement**

`ALL_OF(SOURCE_PROOF, EXPERIMENT_PROOF)`

**accepted evidence**

#238 governed exports + #282 O4/O6-B.

**forbidden substitutions**

copie de fichiers sans manifest; dataset latest implicite.

**dependencies**

L2-G7, L0-G5.

**forbidden states**

dataset non lié à source_boundary/epoch/provenance.

**revocation invariants**

même dataset_id reproduisant des bytes/faits différents.

**assessment**

`SATISFIED`

---

## L3-G2 — Deterministic Research replay

**proof requirement**

`SOURCE_PROOF`

plus au moins une preuve de publication/replay sur dataset réel :

`ONE_OF(EXPERIMENT_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

#239 + #282 O5/O7.

**forbidden substitutions**

backtest non borné; replay dépendant de données live implicites.

**dependencies**

L3-G1.

**forbidden states**

same inputs → different scientific result identity.

**revocation invariants**

non-déterminisme reproductible sur dataset/config identiques.

**assessment**

`SATISFIED`

---

## L3-G3 — Reproducible diagnostics / attribution

**proof requirement**

`ALL_OF(SOURCE_PROOF, EXPERIMENT_PROOF)`

**accepted evidence**

#248 + #282 O6-C.

**forbidden substitutions**

Sharpe inventé; causalité depuis association; métrique sans N/window/population.

**dependencies**

L3-G1, L3-G2.

**forbidden states**

metric sans provenance ou NOT_AVAILABLE converti en estimation autoritative.

**revocation invariants**

diagnostic canonique non reproductible ou population mixing.

**assessment**

`SATISFIED`

---

## L3-G4 — Candidate registry & governed promotion boundary

**proof requirement**

`ALL_OF(SOURCE_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

#240 `RL_CANDIDATE_PROMOTION_BOUNDARY_CERTIFIED`.

**forbidden substitutions**

diff libre non lié à dataset/run; candidate = promoted.

**dependencies**

L3-G2, L3-G3.

**forbidden states**

same-epoch promotion; Research recording AUTHORIZED/EXECUTED without external governance.

**revocation invariants**

voie permettant promotion sans future epoch ou sans evidence chain.

**assessment**

`SATISFIED`

---

## L3-G5 — Market / PAPER / Research domain separation

**proof requirement**

`ALL_OF(SOURCE_PROOF, UX_PROOF)`

**accepted evidence**

#241 + APP source boundaries supporting.

**forbidden substitutions**

PnL agrégé PAPER+Research; candidate shown ACTIVE.

**dependencies**

L0-G1, L3-G1.

**forbidden states**

cross-domain population mixing dans une métrique canonique.

**revocation invariants**

surface canonique fusionnant les domaines sans provenance.

**assessment**

`SATISFIED`

---

## L3-G6 — Same-epoch no-feedback invariant

**proof requirement**

`ALL_OF(SOURCE_PROOF, GOVERNANCE_PROOF)`

et, lorsqu’une epoch Research-observed est active :

`RUNTIME_PROOF`

**accepted evidence**

#242 source certification + #286 guard + #282 runtime observation.

**forbidden substitutions**

simple absence de code observée; promesse documentaire seule pendant epoch active.

**dependencies**

L3-G4, L2-G4.

**forbidden states**

Research/candidate modifiant stratégie/config/risk/sizing de la même epoch.

**revocation invariants**

toute preuve de feedback Research→same active epoch.

**assessment**

`SATISFIED`

---

## L3-G7 — Governed active-experiment capture / replay / diagnostic / publication

**proof requirement**

`ALL_OF(EXPERIMENT_PROOF, RUNTIME_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

#277/#278/#279/#280/#274/#281/#282 O1→O9.

**forbidden substitutions**

F00 historique uniquement; source-only future burn-in contract.

**dependencies**

L3-G1, L3-G2, L3-G3, L3-G6.

**forbidden states**

active experiment sans immutable capture boundary ou publication Research non traçable.

**revocation invariants**

capture/pub Research modifiant l’epoch ou non reproductible.

**assessment**

`SATISFIED`

**note**

La finalisation du burn-in n’est pas requise par ce critère. Ce critère certifie la **capacité Research sur expérience active**, pas la conclusion scientifique de l’expérience.

---

## L3-G8 — Governed Research stack integration / provenance

**proof requirement**

`ALL_OF(SOURCE_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

#275 integration certification + exact-source cold deploy #279 comme supporting runtime lineage.

**forbidden substitutions**

stack branch non intégré; source HEAD sans ancestry.

**dependencies**

L3-G1…G6.

**forbidden states**

runtime Research/burn-in exécuté sur source non identifiable ou stack divergence non tracée.

**revocation invariants**

perte de lineage entre stack certifiée et source utilisée pour les expériences futures.

**assessment**

`SATISFIED`

### L3 R2 assessment

`8/8 mandatory criteria = SATISFIED`

Statut de niveau R2 :

`READY_FOR_REVIEW`

Aucun `LEVEL_3_CERTIFIED`.

---

# R2-A conclusion

À la lumière du catalogue normatif, R1 est confirmé :

```text
L0 = READY_FOR_REVIEW
L1 = READY_FOR_REVIEW
L2 = READY_FOR_REVIEW
L3 = READY_FOR_REVIEW
```

Mais :

```text
FORMAL_CERTIFIED_FRONTIER = NOT_AVAILABLE
```

reste inchangé jusqu’à émission de MachineLevelCertification distincts.
<!-- END CANONICAL COMMENT 5971120146 -->

---

<!-- BEGIN CANONICAL COMMENT 5971148753 -->
# R2-B — CERTIFICATION CATALOG v0.1 — L4→L9

Baseline identique :

`main@eeaec5ae29a72b765bb97feb46520032aba44e2a`

Rappel : un critère supérieur peut déjà posséder une preuve partielle ou même être `SATISFIED` sans que le niveau soit ouvert/certifiable. La chaîne de certification reste strictement séquentielle.

---

# 6. L4 — OPERATOR MACHINE

## PURPOSE

Prouver qu’un opérateur humain peut comprendre l’état global de Crypto AI Terminal depuis une application canonique, avec vérité producteur→projection→API→UI, provenance, sécurité, lisibilité et isolation runtime, sans que l’interface invente une autorité.

## ENTRY_CONDITIONS

L0→L3 evidence assessments SATISFIED.
Certification future : L0→L3 formellement CERTIFIED.

---

## L4-G1 — Operator Truth & Data Parity

**Statement**

Les domaines opérateur principaux doivent être exposés à partir de producteurs/projections gouvernés, sans recomputation de vérité côté React et avec disponibilité/freshness explicites.

**proof requirement**

`ALL_OF(SOURCE_PROOF, UX_PROOF)`

**accepted evidence**

#304 D4, #328 U2, #323 U2b/U3a/U3b, #336 U4, #338 U6.

**forbidden substitutions**

- fixture/screenshot synthétique comme runtime fact;
- frontend calculant PnL/lifecycle/classification;
- valeur absente transformée en zéro;
- API lisant directement un fichier authoritative sans projection/reader contract lorsque le contrat impose une projection.

**dependencies**

L1-G3, L1-G4, L1-G6, L3-G5.

**forbidden states**

- React devient producteur de vérité;
- domain parity revendiquée alors que le producer est absent;
- `NON_DEPLOYED` présenté comme zéro/healthy.

**revocation invariants**

Toute recomputation canonique côté UI ou substitution silencieuse d’une source gouvernée par une donnée de présentation invalide ce critère.

**assessment**

`SATISFIED`

---

## L4-G2 — APP-UNIFY Global Source Certification

**Statement**

L’Operator App unifiée doit disposer d’un verdict source global agrégeant toutes les tranches nécessaires au périmètre L4, sur un SHA exact, avec tests/cross-stack/visual/security contracts et limites explicites.

**proof requirement**

`SOURCE_PROOF`

**accepted evidence**

verdict global exact :

`APP_UNIFY_01_SOURCE_CERTIFIED`

ou futur verdict MACHINE-MATURITY explicitement équivalent et borné.

**forbidden substitutions**

- somme de U2/U2b/U3/U4/U6;
- merge de tranches;
- CI verte isolée;
- U8 preparation.

**dependencies**

L4-G1.

**forbidden states**

tranches intégrées sans revue globale du produit/source.

**revocation invariants**

régression source globale rendant invalide le contrat opérateur unifié.

**assessment**

`NOT_AVAILABLE`

---

## L4-G3 — Operator App Runtime Certification

**Statement**

L’application canonique doit être effectivement déployée et observée sur son plan de release isolé, avec producer→artifact→reader→API→browser réel et sans perturbation de l’Advisor.

**proof requirement**

`ALL_OF(RUNTIME_PROOF, UX_PROOF, SECURITY_PROOF)`

**accepted evidence**

futur verdict :

`APP_UNIFY_01_RUNTIME_CERTIFIED`

avec release SHA exacte, listeners, browser/PWA, artifacts réels, Advisor non-interference, rollback.

**forbidden substitutions**

- U8 PREP;
- CryptoRadar runtime precedent;
- source visual proof;
- local dev server.

**dependencies**

L4-G2, L4-G5, L4-G7.

**forbidden states**

Operator App déclarée canonique alors que runtime non déployé/non observé.

**revocation invariants**

déploiement divergeant du source certifié, perte d’isolation ou mutation de l’Advisor induite par le plan opérateur.

**assessment**

`NOT_AVAILABLE`

---

## L4-G4 — Operator Decision Trust Boundary

**Statement**

L’Operator App doit afficher honnêtement la capacité de décision humaine : une queue non déployée reste `NON_DEPLOYED`; si une queue/action devient opérationnelle, identité, signataires, sources, clés et anti-rollback doivent être gouvernés avant toute mutation.

**proof requirement**

Pour L4 READ-ONLY :

`ALL_OF(ARCHITECTURE_PROOF, GOVERNANCE_PROOF, SOURCE_PROOF)`

Si `operational=true` ou action mutante :

`ALL_OF(ARCHITECTURE_PROOF, GOVERNANCE_PROOF, SOURCE_PROOF, RUNTIME_PROOF, SECURITY_PROOF)`

**accepted evidence**

#307, #313, #315 Gate S + état explicite Gate O.

**forbidden substitutions**

- prototype durable = queue opérationnelle;
- UI button = authority;
- human acceptance = merge/deploy/PAPER mutation.

**dependencies**

L0-G1, L0-G4.

**forbidden states**

- `operational=true` avec Gate O ouverte;
- fake decisions;
- source registry inventé;
- action humaine déclenchant directement merge/deploy/runtime authority hors gate.

**revocation invariants**

Si une mutation devient possible alors qu’un des contrôles Gate O requis manque, révoquer immédiatement ce critère.

**assessment**

`SATISFIED` pour le scope L4 READ-ONLY actuel.

**important**

#315 Gate O ouverte n’empêche pas une certification L4 strictement READ-ONLY si la capacité reste honnêtement `NON_DEPLOYED`. Elle devient obligatoire avant toute revendication de queue/action opérationnelle.

---

## L4-G5 — Source / Runtime Isolation

**Statement**

Le plan de release Operator doit être séparé du checkout runtime de l’Advisor et consommer les artefacts autorisés en lecture seule.

**proof requirement**

`ALL_OF(ARCHITECTURE_PROOF, SOURCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

#342/U8 architecture + future runtime deployment proof.

**forbidden substitutions**

- runbook non exécuté;
- précédent CryptoRadar seul;
- absence de restart supposée.

**dependencies**

L0-G4, L1-G5.

**forbidden states**

Operator release déplaçant/modifiant le checkout gelé de l’Advisor ou obtenant une write path vers PPL/FIN/epoch.

**revocation invariants**

tout déploiement Operator nécessitant mutation non gouvernée du runtime machine.

**assessment**

`UNRESOLVED`

**reason**

ARCHITECTURE/SOURCE existent; runtime APP-UNIFY séparé n’est pas encore démontré.

---

## L4-G6 — Human UX / Mobile / Accessibility

**Statement**

L’interface canonique doit rester compréhensible sur desktop/mobile, préserver les états épistémiques et fournir une accessibilité vérifiée sur le périmètre L4.

**proof requirement**

`ALL_OF(SOURCE_PROOF, UX_PROOF)`

**accepted evidence**

D4 visual proofs, U2/U3/U4/U6 desktop/mobile, semantic rendering tests; futur audit/accessibility aggregate.

**forbidden substitutions**

- une seule capture;
- responsive CSS non testé;
- couleurs seules pour transmettre l’état;
- valeur technique cachée pour simplifier la vue.

**dependencies**

L4-G1.

**forbidden states**

overflow bloquant, information critique uniquement color-coded, états UNKNOWN/STALE masqués.

**revocation invariants**

régression visuelle/accessibilité rendant une preuve ou un état machine indiscernable.

**assessment**

`UNRESOLVED`

**reason**

fort corpus UX/mobile source, mais aucune preuve globale d’accessibilité L4 agrégée n’a été identifiée.

---

## L4-G7 — Security / Access / Deployment Boundary

**Statement**

L’accès opérateur et le déploiement doivent être privés/fail-closed, authentifiés lorsqu’exigé, secrets bornés, listeners maîtrisés et rollback isolé.

**proof requirement**

`ALL_OF(SECURITY_PROOF, RUNTIME_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

WEB-01B historique, #319 CryptoRadar comme précédent, #342 U8 security/deployment plan, futur runtime Operator proof.

**forbidden substitutions**

- source config;
- tailnet design non testé;
- auth UI sans rejection runtime;
- autre service sécurisé comme preuve de l’Operator App.

**dependencies**

L4-G5.

**forbidden states**

exposition publique non gouvernée, mutation API implicite, secrets imprimés, rollback touchant l’Advisor.

**revocation invariants**

perte du fail-closed access boundary ou exposition non autorisée.

**assessment**

`UNRESOLVED`

---

## L4-G8 — L4 Certification Pack

**Statement**

Un pack canonique doit agréger source SHA, runtime SHA/release, contracts, preuve data parity, UX, security, isolation, unresolved items, rollback et criterion matrix sans inventer de PASS.

**proof requirement**

`ALL_OF(GOVERNANCE_PROOF, SOURCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

futur artifact/versioned certification pack + evidence manifest.

**forbidden substitutions**

commentaire ad hoc; issue status; somme de verdicts partiels.

**dependencies**

L4-G1…G7.

**forbidden states**

pack incomplet déclarant L4 READY/CERTIFIED.

**revocation invariants**

evidence pack non reproductible ou perdant son binding aux identités certifiées.

**assessment**

`NOT_AVAILABLE`

### L4 R2 assessment

- SATISFIED : G1, G4
- UNRESOLVED : G5, G6, G7
- NOT_AVAILABLE : G2, G3, G8

Niveau :

`IN_PROGRESS / EVIDENCE_INSUFFICIENT_FOR_CERTIFICATION_REVIEW`

---

# 7. L5 — SELF-MAINTAINING FOREST

## PURPOSE

Prouver qu’un sous-système de maintenance peut observer la machine, ouvrir des problèmes gouvernés, produire des propositions de maintenance isolées, les faire vérifier et les présenter à l’humain sans acquérir d’autorité de merge/deploy/PAPER.

## ENTRY_CONDITIONS

L0→L4 formellement CERTIFIED.

Planning horizon actuel :

`DESIGNED / IN DESIGN`

PR #348 désormais fusionnée reste contract-only.

---

## L5-G1 — Forest maintenance constitution

**Statement**

Le Forest doit posséder un contrat versionné de scope, objets, états, identités, permissions et interdictions.

**proof requirement**

`ALL_OF(ARCHITECTURE_PROOF, GOVERNANCE_PROOF, SOURCE_PROOF)`

**accepted evidence**

#284 + PR #348 lorsque ses questions critiques/actes de gouvernance requis sont fermés.

**forbidden substitutions**

vision #284 seule; merge #348 seul; verdict “READY_FOR_CERTIFICATION” proposé mais non certifié.

**dependencies**

L0-G1, L0-G4.

**forbidden states**

registre sans propriétaire, anti-rollback non défini, stockage/indépendance critiques non résolus.

**revocation invariants**

contrat permettant au Forest d’acheter/obtenir autorité.

**assessment**

`UNRESOLVED`

**reason**

PR #348 est fusionnée et validée contractuellement, mais son propre texte conserve registrar, ancre anti-retour, stockage Q10, indépendance forte et CODEOWNERS non résolus; les verdicts A0/A1 restent proposés/non certifiés.

---

## L5-G2 — Governed Problem Registry

**Statement**

Les problèmes détectés doivent avoir identité, provenance, déduplication, statut et evidence bundle durables.

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

future Problem Registry implementation/runtime.

**forbidden substitutions**

GitHub issue libre; log warning; candidate bounty sans problem identity.

**dependencies**

L5-G1.

**forbidden states**

problème sans source/provenance ou suppressible sans audit.

**revocation invariants**

registry perdant identité/déduplication/audit.

**assessment**

`NOT_AVAILABLE`

---

## L5-G3 — Machine self-observation → problem discovery

**Statement**

Le Forest doit détecter au moins une classe de problème depuis des observations gouvernées sans mutation du runtime observé.

**proof requirement**

`ALL_OF(RUNTIME_PROOF, EXPERIMENT_PROOF)`

**accepted evidence**

future bounded discovery campaign.

**forbidden substitutions**

détection manuelle saisie comme autonome; alerte hardcodée.

**dependencies**

L5-G2, L1-G1.

**forbidden states**

scanner/agent modifiant la source observée pour produire son problème.

**revocation invariants**

feedback observateur→runtime non gouverné.

**assessment**

`NOT_AVAILABLE`

---

## L5-G4 — Isolated maintenance proposal/workspace

**Statement**

Une maintenance doit être réalisée dans un workspace/branch sandbox sans écrire dans le runtime actif.

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, SECURITY_PROOF)`

**accepted evidence**

future sandbox/branch execution proof.

**forbidden substitutions**

Claude/Codex session manuelle; PR humaine; local checkout partagé.

**dependencies**

L5-G2.

**forbidden states**

worker écrivant main/runtime directement.

**revocation invariants**

perte isolation sandbox/branch.

**assessment**

`NOT_AVAILABLE`

---

## L5-G5 — Independent verification before human decision

**Statement**

Une proposition de maintenance doit être vérifiée par une voie indépendante de l’auteur avant présentation comme VALIDATED.

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

future reviewer/verification runtime with author/reviewer identities.

**forbidden substitutions**

self-review; CI seule; modèle auteur réutilisé sans indépendance déclarée.

**dependencies**

L5-G4.

**forbidden states**

proposal passant directement WORKING→ACCEPTED.

**revocation invariants**

contournement de REVIEW/VALIDATED.

**assessment**

`NOT_AVAILABLE`

---

## L5-G6 — Human authority / no automatic merge-deploy

**Statement**

Le Forest peut proposer/valider; il ne peut ni merge, ni deploy, ni restart, ni modifier PAPER/epoch sans une autorité externe explicitement gouvernée.

**proof requirement**

`ALL_OF(GOVERNANCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

future end-to-end negative authority proof.

**forbidden substitutions**

documentation seule.

**dependencies**

L5-G5, L0-G1.

**forbidden states**

auto-merge/deploy/restart.

**revocation invariants**

toute voie automatique Forest→production authority.

**assessment**

`NOT_AVAILABLE`

---

## L5-G7 — Maintenance audit / rollback / outcome evidence

**Statement**

Chaque intervention acceptée doit conserver provenance, diff, tests, décision humaine, déploiement séparé si autorisé, outcome et rollback.

**proof requirement**

`ALL_OF(GOVERNANCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

future maintenance lifecycle completed end-to-end.

**forbidden substitutions**

PR merged = outcome; deploy sans post-proof.

**dependencies**

L5-G4, L5-G5, L5-G6.

**forbidden states**

maintenance sans rollback ou outcome non attribuable.

**revocation invariants**

incapacité à reconstruire une intervention Forest.

**assessment**

`NOT_AVAILABLE`

### L5 R2 assessment

- G1 = UNRESOLVED
- G2…G7 = NOT_AVAILABLE

Certification status :

`NOT_STARTED`

Planning horizon :

`DESIGNED / IN DESIGN`

---

# 8. L6 — GOVERNED AGENT ENGINEERING

## PURPOSE

Prouver que des agents identifiés peuvent prendre en charge des travaux d’ingénierie dans des frontières de capacités, coûts et autorité gouvernées, avec collaboration et revue indépendantes, sans disposer du droit final de production.

## ENTRY_CONDITIONS

L0→L5 formellement CERTIFIED.

---

## L6-G1 — Agent identity & capability registry

**proof requirement**

`ALL_OF(SOURCE_PROOF, GOVERNANCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

future certified Agent Registry + runtime identity issuance.

**forbidden substitutions**

JSON Schema seule; agent name/prompt; PR #348 contract-only.

**dependencies**

L5-G1.

**forbidden states**

agent anonyme ou capability non déclarée.

**revocation invariants**

identité réutilisable/collision non détectée ou capability escalation.

**assessment**

`NOT_AVAILABLE`

---

## L6-G2 — Capability-scoped sandbox execution

**proof requirement**

`ALL_OF(RUNTIME_PROOF, SECURITY_PROOF)`

**accepted evidence**

future agent sandbox with filesystem/network/tool allowlists.

**forbidden substitutions**

branch convention sans enforcement.

**dependencies**

L6-G1.

**forbidden states**

agent accédant hors scope ou runtime actif.

**revocation invariants**

sandbox escape/capability bypass.

**assessment**

`NOT_AVAILABLE`

---

## L6-G3 — Governed Problem/Bounty lifecycle

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

future Problem+Bounty registries and lifecycle evidence.

**forbidden substitutions**

issue GitHub = bounty; AIC promise.

**dependencies**

L5-G2, L6-G1.

**forbidden states**

claim/work sans budget/scope/evidence.

**revocation invariants**

bounty pouvant changer scope/criteria rétroactivement sans audit.

**assessment**

`NOT_AVAILABLE`

---

## L6-G4 — Independent reviewer / validator agents

**proof requirement**

`ALL_OF(RUNTIME_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

future author/reviewer separation and validation trace.

**forbidden substitutions**

same agent role renamed; CI alone.

**dependencies**

L6-G1, L6-G2, L6-G3.

**forbidden states**

self-validation accepted as independent.

**revocation invariants**

independence broken without visibility.

**assessment**

`NOT_AVAILABLE`

---

## L6-G5 — Engineering artifact provenance

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

agent task→branch→commit→PR→tests lineage.

**forbidden substitutions**

chat transcript; generated patch without identity.

**dependencies**

L6-G2.

**forbidden states**

commit/PR impossible à lier à task/agent/evidence.

**revocation invariants**

loss of lineage or artifact tamper undetected.

**assessment**

`NOT_AVAILABLE`

---

## L6-G6 — Compute / cost / internal economy accounting

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

future immutable cost/economy ledger.

**forbidden substitutions**

token budget text; AIC number without ledger.

**dependencies**

L6-G1, L6-G3.

**forbidden states**

récompense sans résultat validé ou coût non attribuable.

**revocation invariants**

double payment, negative/forged balances, untraceable compute.

**assessment**

`NOT_AVAILABLE`

---

## L6-G7 — Human merge/deploy authority remains external

**proof requirement**

`ALL_OF(GOVERNANCE_PROOF, SECURITY_PROOF, RUNTIME_PROOF)`

**accepted evidence**

negative authorization tests + explicit operator gate.

**forbidden substitutions**

policy prose seule.

**dependencies**

L6-G2…G6.

**forbidden states**

agent merge/deploy/PAPER authority direct.

**revocation invariants**

toute escalade agent→production sans gate humain.

**assessment**

`NOT_AVAILABLE`

---

## L6-G8 — Multi-agent collaboration reproducibility

**proof requirement**

`ALL_OF(RUNTIME_PROOF, EXPERIMENT_PROOF)`

**accepted evidence**

future completed multi-agent engineering campaign reproducible/auditable.

**forbidden substitutions**

plusieurs agents configurés mais non exécutés.

**dependencies**

L6-G1…G7.

**forbidden states**

handoffs non traçables, contradictions silently resolved.

**revocation invariants**

campagne agentique non reconstructible.

**assessment**

`NOT_AVAILABLE`

### L6 R2 assessment

`8/8 = NOT_AVAILABLE`

Certification status :

`NOT_STARTED`

Planning horizon :

`FUTURE / DESIGN`

---

# 9. L7 — AUTONOMOUS TEST ENVIRONMENT

## PURPOSE

Prouver qu’un environnement autonome peut générer/exécuter/évaluer des scénarios de test dans une enceinte hermétique, reproductible et indépendante de la production, puis publier des preuves gouvernées sans promotion automatique.

## ENTRY_CONDITIONS

L0→L6 formellement CERTIFIED.

Planning horizon actuel :

`LOCKED`

---

## L7-G1 — Hermetic test substrate

**proof requirement**

`SOURCE_PROOF`

**accepted evidence**

#201 TI-00, #267 HERM-02, Scientific Data Guard.

**forbidden substitutions**

tests partageant les artefacts prod.

**dependencies**

L0-G3, L0-G4.

**forbidden states**

test write leak vers données scientifiques/runtime.

**revocation invariants**

nouvelle contamination silencieuse.

**assessment**

`SATISFIED`

---

## L7-G2 — Deterministic orchestration & exact-head execution

**proof requirement**

`SOURCE_PROOF`

**accepted evidence**

CI exact-head, orchestration integrity, deterministic replay/test gates.

**forbidden substitutions**

retry-until-green non attribué; floating branch evidence.

**dependencies**

L7-G1.

**forbidden states**

résultat de test sans source identity.

**revocation invariants**

test verdict impossible à reproduire sur exact inputs.

**assessment**

`SATISFIED`

---

## L7-G3 — Autonomous scenario generation

**proof requirement**

`ALL_OF(RUNTIME_PROOF, EXPERIMENT_PROOF)`

**accepted evidence**

future autonomous test scenario generation campaign.

**forbidden substitutions**

parametrized tests écrits manuellement.

**dependencies**

L7-G1, L7-G2, L6-G1.

**forbidden states**

scenario generator écrivant production.

**revocation invariants**

generated test cannot be reproduced or attributed.

**assessment**

`NOT_AVAILABLE`

---

## L7-G4 — Candidate/system sandbox under autonomous test

**proof requirement**

`ALL_OF(RUNTIME_PROOF, SECURITY_PROOF)`

**accepted evidence**

future isolated execution of candidate versions.

**forbidden substitutions**

CI on main only.

**dependencies**

L7-G1, L6-G2.

**forbidden states**

candidate test touching production state/network beyond policy.

**revocation invariants**

sandbox boundary breach.

**assessment**

`NOT_AVAILABLE`

---

## L7-G5 — Independent evaluation & adversarial verification

**proof requirement**

`ALL_OF(RUNTIME_PROOF, EXPERIMENT_PROOF)`

**accepted evidence**

future evaluator separate from generator/author.

**forbidden substitutions**

self-score.

**dependencies**

L7-G3, L7-G4, L6-G4.

**forbidden states**

candidate qualifies itself.

**revocation invariants**

loss of evaluator independence.

**assessment**

`NOT_AVAILABLE`

---

## L7-G6 — No production mutation from autonomous testing

**proof requirement**

`ALL_OF(RUNTIME_PROOF, SECURITY_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

negative mutation tests on real automation boundary.

**forbidden substitutions**

source grep alone.

**dependencies**

L7-G4.

**forbidden states**

test environment can merge/deploy/write PAPER/exchange.

**revocation invariants**

any unauthorized production side effect.

**assessment**

`NOT_AVAILABLE`

---

## L7-G7 — Reproducible test evidence publication

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

future immutable test-run manifests/artifacts.

**forbidden substitutions**

CI URL alone.

**dependencies**

L7-G2…G5.

**forbidden states**

run evidence mutable/unbound.

**revocation invariants**

same run identity resolving to different content.

**assessment**

`NOT_AVAILABLE`

---

## L7-G8 — Autonomous closed test loop

**proof requirement**

`ALL_OF(RUNTIME_PROOF, EXPERIMENT_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

future problem/candidate→generated tests→evaluation→human-ready decision package end-to-end.

**forbidden substitutions**

manual orchestration.

**dependencies**

L7-G1…G7.

**forbidden states**

automatic promotion/deployment from test verdict.

**revocation invariants**

test loop crosses the human authority boundary.

**assessment**

`NOT_AVAILABLE`

### L7 R2 assessment

Substrate pre-exists :

- G1 SATISFIED
- G2 SATISFIED

Autonomous capability :

- G3…G8 NOT_AVAILABLE

Certification status :

`NOT_STARTED`

Planning horizon :

`LOCKED`

Upper-level substrate evidence does not bypass L5/L6 dependencies.

---

# 10. L8 — GOVERNED CAPITAL MACHINE

## PURPOSE

Prouver qu’une machine peut gérer une autorité de capital non-PAPER sous contrôle gouverné, avec custody/secrets, allocation, risk, execution, reconciliation, kill/rollback et limites humaines explicites.

## ENTRY_CONDITIONS

L0→L7 formellement CERTIFIED.
Autorisation juridique/opérationnelle explicite du mode de capital concerné.

Planning horizon :

`LOCKED`

---

## L8-G1 — Non-PAPER capital authority contract

**proof requirement**

`ALL_OF(ARCHITECTURE_PROOF, GOVERNANCE_PROOF, SECURITY_PROOF)`

**accepted evidence**

future TESTNET/REAL capital authority contract.

**forbidden substitutions**

FIN PAPER; PPL; hypothetical exchange mode.

**dependencies**

L0-G1, L2-G5.

**assessment**

`NOT_AVAILABLE`

---

## L8-G2 — Credential / custody / secret boundary

**proof requirement**

`ALL_OF(SECURITY_PROOF, RUNTIME_PROOF)`

**accepted evidence**

future credential custody/rotation/access proof.

**forbidden substitutions**

.env presence; masked log.

**dependencies**

L8-G1.

**assessment**

`NOT_AVAILABLE`

---

## L8-G3 — Governed capital allocation / Treasury authority

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

future FIN-03/treasury equivalent.

**forbidden substitutions**

PAPER capital projections.

**dependencies**

L8-G1, L8-G2.

**assessment**

`NOT_AVAILABLE`

---

## L8-G4 — Real/test execution authority & fail-closed risk boundary

**proof requirement**

`ALL_OF(RUNTIME_PROOF, SECURITY_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

future explicitly authorized execution campaign.

**forbidden substitutions**

simulated fills; code path existence.

**dependencies**

L8-G1…G3.

**assessment**

`NOT_AVAILABLE`

---

## L8-G5 — External reconciliation

**proof requirement**

`ALL_OF(RUNTIME_PROOF, EXPERIMENT_PROOF)`

**accepted evidence**

future exchange/account readback vs internal books.

**forbidden substitutions**

PAPER FIN-02.

**dependencies**

L8-G3, L8-G4.

**assessment**

`NOT_AVAILABLE`

---

## L8-G6 — Capital kill / rollback / incident containment

**proof requirement**

`ALL_OF(RUNTIME_PROOF, SECURITY_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

future bounded emergency/rollback proof.

**forbidden substitutions**

documented command never tested.

**dependencies**

L8-G4.

**assessment**

`NOT_AVAILABLE`

---

## L8-G7 — Human capital authority cannot be bought or bypassed

**proof requirement**

`ALL_OF(GOVERNANCE_PROOF, SECURITY_PROOF, RUNTIME_PROOF)`

**accepted evidence**

future negative proof that agents/AIC/Research cannot grant capital authority.

**forbidden substitutions**

#284 policy prose seule.

**dependencies**

L6-G7, L8-G4.

**assessment**

`NOT_AVAILABLE`

---

## L8-G8 — Governed capital certification pack

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, EXPERIMENT_PROOF, SECURITY_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

future capital-cert evidence manifest.

**dependencies**

L8-G1…G7.

**assessment**

`NOT_AVAILABLE`

### L8 R2 assessment

`8/8 = NOT_AVAILABLE`

Les preuves FIN/PPL PAPER sont explicitement **inadmissibles comme substitut** à une preuve non-PAPER.

Certification status :

`NOT_STARTED`

Planning horizon :

`LOCKED`

---

# 11. L9 — ADAPTIVE RESEARCH ORGANIZATION

## PURPOSE

Prouver qu’un ensemble gouverné de capacités Research/Engineering/Agents peut maintenir une mémoire institutionnelle, formuler des hypothèses, allouer des ressources, lancer des expériences, apprendre entre epochs et améliorer l’organisation sans auto-modifier une autorité active ni supprimer le contrôle humain.

## ENTRY_CONDITIONS

L0→L8 formellement CERTIFIED.

Planning horizon :

`VISION`

---

## L9-G1 — Institutional knowledge / lineage memory

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

future governed institutional memory with immutable lineage.

**forbidden substitutions**

chat history; README; model memory.

**assessment**

`NOT_AVAILABLE`

---

## L9-G2 — Hypothesis portfolio & research agenda governance

**proof requirement**

`ALL_OF(SOURCE_PROOF, GOVERNANCE_PROOF, RUNTIME_PROOF)`

**accepted evidence**

future hypothesis/research portfolio registry.

**forbidden substitutions**

issue backlog.

**assessment**

`NOT_AVAILABLE`

---

## L9-G3 — Adaptive resource allocation

**proof requirement**

`ALL_OF(RUNTIME_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

future governed allocation of compute/data/agent budgets.

**forbidden substitutions**

AIC design proposal.

**assessment**

`NOT_AVAILABLE`

---

## L9-G4 — Cross-epoch learning without same-epoch feedback

**proof requirement**

`ALL_OF(EXPERIMENT_PROOF, RUNTIME_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

future sequence of certified epochs showing learning applied only to future boundaries.

**forbidden substitutions**

same-epoch tuning; retrospective narrative.

**assessment**

`NOT_AVAILABLE`

---

## L9-G5 — Multi-agent / human organizational decision separation

**proof requirement**

`ALL_OF(RUNTIME_PROOF, GOVERNANCE_PROOF, SECURITY_PROOF)`

**accepted evidence**

future organizational decision chain with explicit authorities.

**forbidden substitutions**

majority vote d’agents = human authority.

**assessment**

`NOT_AVAILABLE`

---

## L9-G6 — Self-improvement evaluation & anti-Goodhart controls

**proof requirement**

`ALL_OF(EXPERIMENT_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

future independent validation populations / holdouts / anti-self-scoring mechanisms.

**forbidden substitutions**

training/evaluation on same evidence without declaration.

**assessment**

`NOT_AVAILABLE`

---

## L9-G7 — Organizational incident / revocation capability

**proof requirement**

`ALL_OF(RUNTIME_PROOF, GOVERNANCE_PROOF)`

**accepted evidence**

future proof that agents/capabilities/budgets/certifications can be suspended/revoked with audit.

**forbidden substitutions**

manual deletion.

**assessment**

`NOT_AVAILABLE`

---

## L9-G8 — Adaptive organization certification pack

**proof requirement**

`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, EXPERIMENT_PROOF, GOVERNANCE_PROOF, SECURITY_PROOF)`

**accepted evidence**

future end-to-end organizational evidence manifest.

**dependencies**

L9-G1…G7.

**assessment**

`NOT_AVAILABLE`

### L9 R2 assessment

`8/8 = NOT_AVAILABLE`

Certification status :

`NOT_STARTED`

Planning horizon :

`VISION`

---

# R2-B conclusion

Le catalogue rend maintenant explicite qu’il existe trois situations très différentes :

1. **preuves complètes mais pas encore certification formelle** — L0→L3;
2. **niveau réellement en construction avec gaps identifiés** — L4;
3. **architecture/vision future sans capability proof** — L5→L9.

La fusion de PR #348 ne modifie pas cette frontière :

```text
PR #348 merged
= SOURCE/ARCHITECTURE evidence

PR #348 merged
!= Forest runtime

PR #348 merged
!= Agent runtime

PR #348 merged
!= L5/L6 certification
```
<!-- END CANONICAL COMMENT 5971148753 -->

---

<!-- BEGIN CANONICAL COMMENT 5971167870 -->
# R2-C — MATRICE CANONIQUE, GAP PACK L4 ET CLOSURE R2

Baseline :

`main@eeaec5ae29a72b765bb97feb46520032aba44e2a`

Catalog version :

`MACHINE-MATURITY-CATALOG-v0.1`

Nombre de critères mandatory :

`73`

Aucun score pondéré, moyenne ou pourcentage n'est autorisé comme décision de certification.

---

# 1. Matrice agrégée

| Level | Mandatory | SATISFIED | UNRESOLVED | NOT_AVAILABLE | Level evidence state |
|---|---:|---:|---:|---:|---|
| L0 Constitutional Foundation | 5 | 5 | 0 | 0 | READY_FOR_REVIEW |
| L1 Observable Machine | 6 | 6 | 0 | 0 | READY_FOR_REVIEW |
| L2 Governed PAPER Machine | 7 | 7 | 0 | 0 | READY_FOR_REVIEW |
| L3 Scientific Research Machine | 8 | 8 | 0 | 0 | READY_FOR_REVIEW |
| L4 Operator Machine | 8 | 2 | 3 | 3 | IN_PROGRESS |
| L5 Self-Maintaining Forest | 7 | 0 | 1 | 6 | NOT_STARTED |
| L6 Governed Agent Engineering | 8 | 0 | 0 | 8 | NOT_STARTED |
| L7 Autonomous Test Environment | 8 | 2 | 0 | 6 | NOT_STARTED / LOCKED |
| L8 Governed Capital Machine | 8 | 0 | 0 | 8 | NOT_STARTED / LOCKED |
| L9 Adaptive Research Organization | 8 | 0 | 0 | 8 | NOT_STARTED / VISION |

`SATISFIED` signifie uniquement que le corpus admissible remplit le critère R2.

`SATISFIED != CERTIFIED`

---

# 2. Frontières après R2

~~~text
FORMAL_CERTIFIED_FRONTIER
= NOT_AVAILABLE

EVIDENCE_DEMONSTRATED_FRONTIER
= L3 — Scientific Research Machine

DEVELOPMENT_FRONTIER
= L4 — Operator Machine

NEXT_FORMAL_CERTIFICATION_TARGET
= L0 — Constitutional Foundation

NEXT_FRONTIER_ADVANCEMENT_TARGET
= L4 — Operator Machine
~~~

---

# 3. Gap Pack canonique L4

## L4-G1 — Operator Truth & Data Parity

`SATISFIED`

Source/UX evidence suffisante pour le critère.

## L4-G2 — APP-UNIFY Global Source Certification

`NOT_AVAILABLE`

Manque :

`APP_UNIFY_01_SOURCE_CERTIFIED`

Les tranches U2/U2b/U3/U4/U6 ne peuvent pas être additionnées implicitement pour fabriquer ce verdict.

Exit proof attendu :
- scope global APP-UNIFY borné;
- exact source HEAD;
- data contracts;
- cross-stack;
- full frontend/backend tests;
- visual/mobile;
- accessibility aggregate;
- security/source boundary;
- unresolved items;
- explicit no-runtime claim si source-only.

## L4-G3 — Operator App Runtime Certification

`NOT_AVAILABLE`

Manque :

`APP_UNIFY_01_RUNTIME_CERTIFIED`

#342 est PREP/NO DEPLOY.

Exit proof attendu :
- exact immutable release SHA;
- release plane isolé sous `/opt/crypto-ai-terminal/operator/releases/<SHA>`;
- API/Web services réels;
- listeners réels;
- browser/PWA réel;
- governed artifact paths;
- producer→artifact→reader→API→browser;
- Advisor identity/non-interference before/after;
- rollback Operator-only;
- no write path vers PPL/FIN/epoch;
- private/fail-closed access.

Governance blocker courant :

#286 reste actif.

Donc cette gate runtime ne peut être exécutée qu'après une autorisation distincte compatible avec le burn-in.

## L4-G4 — Operator Decision Trust Boundary

`SATISFIED` pour L4 READ-ONLY.

État honnête :

`NON_DEPLOYED`

Gate O #315 :

`OPEN / NON RÉSOLU`

Gate O devient obligatoire seulement avant `operational=true` ou avant toute action OperatorDecision mutante.

L4 ne doit jamais exiger de fabriquer une queue opérationnelle uniquement pour obtenir une certification read-only.

## L4-G5 — Source / Runtime Isolation

`UNRESOLVED`

Établi :
- architecture U8;
- release plane séparé;
- checkout Advisor séparé;
- read-only artifact contract.

Manque :
- preuve runtime APP-UNIFY réelle de cette isolation.

## L4-G6 — Human UX / Mobile / Accessibility

`UNRESOLVED`

Établi :
- nombreuses preuves desktop/mobile;
- semantic states;
- no fake zero;
- no horizontal-overflow evidence sur plusieurs tranches.

Manque :
- preuve/accessibility aggregate au périmètre global L4.

La résolution doit être intégrée à L4-G2, pas créer un second produit.

## L4-G7 — Security / Access / Deployment Boundary

`UNRESOLVED`

Établi :
- WEB-01B precedent;
- CryptoRadar #319 precedent;
- U8 security/deployment design.

Manque :
- preuve runtime de l'Operator App canonique elle-même.

## L4-G8 — L4 Certification Pack

`NOT_AVAILABLE`

Doit être produit seulement après G1→G7.

Minimum conceptuel :

~~~text
L4CertificationPack {
  catalog_version
  catalog_hash

  source_certification_ref
  source_sha

  runtime_certification_ref
  runtime_release_sha

  operator_data_contract_refs[]
  runtime_artifact_refs[]

  ux_proof_refs[]
  accessibility_proof_refs[]
  security_proof_refs[]
  isolation_proof_refs[]

  decision_trust_state

  unresolved_items[]
  rollback_ref

  criterion_matrix
  evidence_manifest_hash
}
~~~

---

# 4. Ordre recommandé pour fermer L4 plus tard

Sous #286, source work seulement :

1. compléter le périmètre APP-UNIFY restant;
2. produire l'aggregate accessibility/UX proof;
3. lancer la revue globale source;
4. obtenir `APP_UNIFY_01_SOURCE_CERTIFIED`.

Ensuite seulement, lorsqu'une mission runtime distincte devient autorisée :

5. exécuter les gates U8 G0→G8;
6. certifier runtime isolation/security/data fidelity;
7. obtenir `APP_UNIFY_01_RUNTIME_CERTIFIED`;
8. assembler L4 Certification Pack;
9. soumettre L4 à MACHINE-MATURITY certification review.

#315 Gate O reste hors chemin critique si OperatorDecision demeure strictement `NON_DEPLOYED`.

---

# 5. MachineLevelCertification — minimum figé par R2

~~~text
MachineLevelCertification {
    schema_version

    level_id
    level_name
    catalog_version
    catalog_hash

    certification_status
    certified_at_utc
    certification_authority

    source_identity
    runtime_identity

    criterion_results[]
    evidence_record_ids[]
    evidence_manifest_hash

    unresolved_items[]
    accepted_not_applicable[]

    previous_certification_hash
    supersedes_certification_hash

    revocation_invariants[]
    revocation_ref

    decision_ref
    certification_hash
}
~~~

Règles :
- `criterion_results[]` inclut tous les mandatory criteria;
- aucune ligne mandatory ne peut être UNRESOLVED/NOT_AVAILABLE lors d'un PASS;
- `accepted_not_applicable[]` doit être autorisé par le critère;
- certificat immutable;
- recertification = nouvel artefact;
- revocation = nouvel artefact/référence;
- previous/supersedes hashes construisent la chaîne.

---

# 6. MachineMaturitySnapshot — minimum figé par R2

Le snapshot futur est une projection des certificats et états, jamais le moteur de certification.

~~~text
MachineMaturitySnapshot {
    schema_version
    catalog_version
    generated_at_utc

    formal_certified_frontier
    evidence_demonstrated_frontier
    development_frontier

    next_formal_certification_target
    next_frontier_advancement_target

    levels[]

    active_experiments[]
    active_governance_guards[]
    blockers[]

    source_refs[]
    snapshot_hash
}
~~~

Chaque niveau expose séparément :
- level_id;
- certification_status;
- planning_horizon_state;
- criterion_counts;
- certification_ref;
- revocation_state.

Le snapshot ne peut jamais calculer un `CERTIFIED` depuis le nombre de critères verts.

Il ne peut que lire un `MachineLevelCertification` valide.

---

# 7. Effet de la fusion PR #348 pendant R2

PR #348 a été fusionnée après R1 :

- head : `18f7c159f207159243cb0227773427f2a209b26a`;
- merge/main : `eeaec5ae29a72b765bb97feb46520032aba44e2a`;
- scope : docs + JSON Schema;
- aucun worker/runtime/provider/GitHub writer/AIC ledger/deploy/PAPER mutation.

Son propre texte précise :
- verdicts A0/A1 proposés, non certifiés;
- registrar non résolu;
- ancre anti-retour non résolue;
- stockage Q10 non résolu;
- indépendance forte non résolue;
- CODEOWNERS non résolu;
- `AVAILABLE` reste inatteignable.

R2 classe donc :

~~~text
L5-G1 = UNRESOLVED
L6 runtime criteria = NOT_AVAILABLE
~~~

Cette fusion ne change ni Evidence-Demonstrated Frontier ni Development Frontier.

---

# 8. Prérequis de MACHINE-MATURITY-01

La rétro-certification L0/L1 peut être ouverte uniquement après revue/adoption du catalogue R2.

## Phase A — L0

- freeze catalog version/hash;
- freeze EvidenceRecord set utilisé;
- vérifier L0-G1…G5;
- rechercher contradictions/supersessions;
- produire L0 evidence manifest;
- émettre soit :
  - `LEVEL_0_CERTIFIED`
  - `LEVEL_0_CERTIFICATION_REMEDIATION_REQUIRED`.

## Phase B — L1

Seulement si L0 = CERTIFIED.

- vérifier L1-G1…G6;
- distinguer historique et état requis;
- produire L1 evidence manifest;
- émettre soit :
  - `LEVEL_1_CERTIFIED`
  - `LEVEL_1_CERTIFICATION_REMEDIATION_REQUIRED`.

Aucune rétro-certification L2/L3 dans la même décision si L0/L1 échouent.

---

# 9. Verdict R2

`MACHINE_MATURITY_R2_CERTIFICATION_CATALOG_READY_FOR_REVIEW`

Cela signifie :
- vocabulaire défini;
- schema criterion défini;
- 73 mandatory criteria définis;
- L0→L9 catalogués;
- preuves requises définies;
- substitutions interdites définies;
- dépendances définies;
- forbidden states définis;
- revocation invariants définis;
- current assessment calculé;
- gap pack L4 défini;
- minimum MachineLevelCertification défini;
- minimum MachineMaturitySnapshot défini.

Cela ne signifie PAS :
- adoption irrévocable du catalogue;
- `LEVEL_0_CERTIFIED`;
- `LEVEL_1_CERTIFIED`;
- modification runtime;
- finalisation #282;
- levée #286;
- fermeture #315;
- activation Forest/agents;
- capacité L5/L6.

Aucune mutation runtime/PAPER/PPL/FIN/epoch/config/strategy/risk/sizing/Watchdog/TESTNET/LIVE/exchange n'a été effectuée par R2.
<!-- END CANONICAL COMMENT 5971167870 -->