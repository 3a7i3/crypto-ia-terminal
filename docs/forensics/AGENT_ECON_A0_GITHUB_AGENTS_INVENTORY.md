# AGENT-ECON A0 — Inventaire des profils `.github/agents/*.agent.md`

Statut : **DIAGNOSTIC SOURCE / READ-ONLY** — aucun profil n'est modifié par cette mission.
Base : `main@c561fae406950bf7813102b5b3f59c32388566d0`.
Constitution évaluée : [A0 — Forest Maintenance Contract](../contracts/AGENT_ECON_A0_FOREST_MAINTENANCE_CONTRACT.md) ·
[catalogue](../contracts/AGENT_ECON_A1_CAPABILITY_CATALOG.md).
Parent : [#284](https://github.com/3a7i3/crypto-ia-terminal/issues/284) · garde-fou
[#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286).

Ces profils sont des **artefacts historiques/candidats, pas une autorité**. Chaque
fichier a été lu en entier. Aucun n'est déclaré compatible sans inspection.

## Limites de cette preuve

- **SOURCE PROOF seulement.** Aucune observation de la plateforme qui exécute ces
  profils (GitHub Copilot) ni du VPS. Le comportement par défaut d'un front matter sans
  `tools` n'a **pas** pu être vérifié (accès à la documentation plateforme bloqué par le
  proxy d'egress de la session) : il est marqué *non vérifié*. Un pouvoir effectif
  inconnu est traité comme **non borné** (fail-closed), pas comme nul.
- La prose restrictive d'un profil (« READ-ONLY », « ne modifie rien ») **n'est pas un
  enforcement** ; seul un `tools` explicite l'est, sous réserve du comportement plateforme.
- L'historique git des profils ne montre que des commits sans rapport avec les agents
  (`b2a7d7d`, `a499b79`) : l'**auteur et l'intention d'origine sont `NOT_AVAILABLE`**
  depuis `git log` seul.

Statuts : `MIGRATION_CANDIDATE` · `REVIEW_REQUIRED` · `BLOCKED_LEGACY_RECONCILIATION`.
« Niveau V1 » = plafond admissible dans `AGENT_SPEC_V1` (F0–F2) ; F3/F4 sont réservés.

---

## 1. Tableau de synthèse

| # | Profil | `tools` déclaré | Écriture / exécution | Classe future | Niveau recommandé | Statut |
|---|---|---|---|---|---|---|
| 1 | `data-provenance-auditor` | `["read","search"]` | non | `DATA_STEWARD` | F2 | `MIGRATION_CANDIDATE` |
| 2 | `decision-path-forensic` | `["read","search"]` | non | `FORENSIC` | F2 | `MIGRATION_CANDIDATE` |
| 3 | `hedge-fund-architect` | `[read, edit, search, execute, agent, todo]` + `agents: [sniper-engine]` | **oui : édition, exécution, délégation** | aucune enregistrable (`ENGINEER` réservé) | aucun en V1 | `BLOCKED_LEGACY_RECONCILIATION` |
| 4 | `mission-preparation-researcher` | `["read","search","web"]` | non, mais **réseau externe** | `CURATOR` | F2 (sans `web`) | `REVIEW_REQUIRED` |
| 5 | `observability-cartographer` | `["read","search"]` | non | `SENSOR` | F0 | `MIGRATION_CANDIDATE` |
| 6 | `repository-cartographer` | `["read","search"]` | non | `SENSOR` | F0 | `MIGRATION_CANDIDATE` |
| 7 | `security-Guardian-agent` | **aucun** (front matter non fermé) | **indéterminé** | `SECURITY` | F4 réservé ; V1 intérimaire F2 diagnostic seul | `REVIEW_REQUIRED` |
| 8 | `sniper-engine` | **aucun** (pas de front matter) | **décrit l'exécution d'ordres** | aucune | aucun | `BLOCKED_LEGACY_RECONCILIATION` |
| 9 | `statistician-agent` | **aucun** (front matter non fermé) | **indéterminé** | `REVIEWER` (réservé) | F4 réservé ; non enregistrable en V1 | `REVIEW_REQUIRED` |
| 10 | `system-diagnostic` | **aucun** (front matter non fermé) | **indéterminé** ; décrit des commandes VPS | `SRE` | F2 sans lecture runtime | `REVIEW_REQUIRED` |

Aucun profil n'est `MIGRATION_CANDIDATE` *sans* remédiation : « candidat » signifie
qu'une `AgentSpec` neuve est envisageable par PR humaine, pas que le fichier est valide.

---

## 2. Fiches par profil

Champs : nom · objectif actuel · pouvoirs déclarés · capacité écriture/exécution ·
implications runtime · compatibilité A0 · classe/niveau recommandés · statut ·
remédiation requise.

### 2.1 `data-provenance-auditor` — 180 lignes

- **Objectif.** Audit READ-ONLY des datasets : producteurs, consommateurs, identifiants,
  fraîcheur, schémas, rétention, joignabilité.
- **Pouvoirs déclarés.** Front matter fermé ; `tools: ["read","search"]` ;
  `disable-model-invocation: true`, `user-invocable: true` (invocation par l'opérateur
  uniquement) ; `metadata.mode: read-only`.
- **Écriture/exécution.** Aucune déclarée ; prose « Aucune modification… ».
- **Runtime.** Aucun. Précise de ne pas mesurer de doublons runtime depuis le code seul ;
  renvoie les mesures runtime à une « mission séparée ».
- **Compatibilité A0.** Compatible avec F2 (rapport = `DIAGNOSTIC`). Écarts : verdicts
  `DATA_PROVENANCE_COMPLETE/PARTIAL/BLOCKED` auto-labellisés (A0 §16 I7) ; périmètre
  non déclaré sous forme de `scope_policy`.
- **Spec envisagée.** `DATA_STEWARD`, F2 ; `REPOSITORY_READ`, `REPOSITORY_SEARCH`,
  `DIAGNOSTIC_PRODUCE`.
- **Statut.** `MIGRATION_CANDIDATE`.
- **Remédiation.** Écrire une `AgentSpec` (chemins de lecture explicites, hors `.env*`) ;
  renommer les verdicts en constat non certifiant ; ne pas hériter de pouvoirs au-delà
  du catalogue.

### 2.2 `decision-path-forensic` — 167 lignes

- **Objectif.** Forensic READ-ONLY de tout chemin pouvant influencer signal, gate,
  sizing, exécution ; recherche de bypass.
- **Pouvoirs déclarés.** `tools: ["read","search"]`, invocation utilisateur seule,
  `mode: read-only`.
- **Écriture/exécution.** Aucune.
- **Runtime.** Aucun ; classe des chemins `DECISION_ACTIVE`/`EXECUTION_ACTIVE` mais
  sans les modifier. Énonce `OBSERVATION != AUTHORITY`, `RECOMMENDED != APPLIED`
  (cohérent avec A0 §1).
- **Compatibilité A0.** Compatible F2. Écart : verdicts `DECISION_GRAPH_CLOSED` etc.
- **Spec envisagée.** `FORENSIC`, F2 ; `REPOSITORY_READ`, `REPOSITORY_SEARCH`,
  `STATIC_ANALYSIS`, `DIAGNOSTIC_PRODUCE`.
- **Statut.** `MIGRATION_CANDIDATE`.
- **Remédiation.** Spec + renommage des verdicts.

### 2.3 `hedge-fund-architect` — 104 lignes — **BLOQUÉ**

- **Objectif.** Construire/étendre/déboguer un « AI Hedge Fund Trading System » :
  market discovery, memecoin scanner, sniper engine, bot doctor, strategy lab,
  Telegram, dashboard.
- **Pouvoirs déclarés.** `tools: [read, edit, search, execute, agent, todo]` ;
  `agents: [sniper-engine]` (délégation vers le profil 2.8, donc **accessibilité
  transitive** d'une description d'exécution d'ordres).
- **Écriture/exécution.** **Oui, large** (`edit` + `execute` + sous-agent).
- **Runtime.** Demande de scaffolder `sniper_engine/trade_executor.py`,
  `mempool_listener.py`, etc. ; traite « Bot Doctor » comme porte de validation des
  trades (représentation d'architecture ancienne). La règle « Paper trading by default —
  never enable live trading **unless the user explicitly requests it** » ouvre une
  voie d'activation LIVE par simple demande, contraire à #286 et à A0
  (`LIVE_ENABLE`/`EXCHANGE_WRITE` interdits).
- **Architecture périmée (vérifié par `git ls-files`).** `crypto_quant_v16/`,
  `quant-hedge-ai/` (avec tiret), `crypto_quant_v16/v26/bot_doctor.py` et
  `main_v16.py` **n'existent pas** dans l'arbre suivi ; `quant_hedge_ai/` (underscore)
  existe, ainsi que `quant_hedge_ai/main_v91.py`, `quant_hedge_ai/agents/{whales,strategy,market,risk}/`
  et `supervision/bot_doctor.py`. Le profil décrit donc un état antérieur.
- **Compatibilité A0.** **Incompatible** : `edit`/`execute`/délégation hors catalogue ;
  voie vers LIVE ; périmètre trading (domaine séparé de la forêt).
- **Spec envisagée.** Aucune. `ENGINEER` est réservé (F3) ; aucune spec V1 valide
  ne peut représenter ce profil.
- **Statut.** `BLOCKED_LEGACY_RECONCILIATION`.
- **Remédiation.** Décision humaine : archiver (`ARCHIVE`) ou réécrire. Classification
  CLAUDE.md §5 : `UNKNOWN` ⇒ **ne pas supprimer**. Ne lui accorder aucun droit
  automatique. Ne pas le modifier dans cette mission.

### 2.4 `mission-preparation-researcher` — 193 lignes

- **Objectif.** Préparer un « Evidence Pack » READ-ONLY avant une mission (architecture,
  code, tests, ADR, risques, critères d'acceptation proposés).
- **Pouvoirs déclarés.** `tools: ["read","search","web"]`, invocation utilisateur seule,
  `mode: read-only`.
- **Écriture/exécution.** Aucune ; **`web` = lecture réseau externe**, sans équivalent
  dans le catalogue (aucune capability réseau n'existe, volontairement).
- **Runtime.** Aucun. Sépare `REPOSITORY EVIDENCE` de `EXTERNAL REFERENCE`.
- **Compatibilité A0.** Compatible F2 **sans** `web` (sorties `SCOPE_DRAFT`,
  `ACCEPTANCE_CRITERIA_DRAFT`). `web` : décision humaine requise (amender A0 ou retirer).
  Verdicts `READY_FOR_PROMPT` etc. auto-labellisés.
- **Spec envisagée.** `CURATOR`, F2 ; `REPOSITORY_READ`, `REPOSITORY_SEARCH`,
  `SCOPE_DRAFT_PREPARE`, `ACCEPTANCE_CRITERIA_DRAFT_PREPARE`.
- **Statut.** `REVIEW_REQUIRED`.
- **Remédiation.** Trancher `web` (retrait ou amendement constitutionnel humain) ;
  renommer les verdicts.

### 2.5 `observability-cartographer` — 173 lignes

- **Objectif.** Cartographie READ-ONLY des métriques, snapshots, dashboards, bots
  Telegram et sources de vérité opérateur.
- **Pouvoirs déclarés.** `tools: ["read","search"]`, invocation utilisateur seule.
- **Écriture/exécution.** Aucune.
- **Runtime.** Aucun ; inventorie des bots Telegram par nom (pas de secret).
- **Compatibilité A0.** Compatible F0 (rapport transitoire) ; ses classifications sont
  des constats. Verdicts `OBSERVABILITY_MAP_COMPLETE` etc.
- **Spec envisagée.** `SENSOR`, F0 ; `REPOSITORY_READ`, `REPOSITORY_SEARCH`.
- **Statut.** `MIGRATION_CANDIDATE`.
- **Remédiation.** Spec ; si son rapport doit être **persisté** comme preuve, cela
  exige F2 (`DIAGNOSTIC_PRODUCE`) ou un écrivain gouverné — à décider à la migration.

### 2.6 `repository-cartographer` — 189 lignes

- **Objectif.** Cartographie READ-ONLY de l'architecture, modules, call graphs, états
  persistants.
- **Pouvoirs déclarés.** `tools: ["read","search"]`, invocation utilisateur seule.
- **Écriture/exécution.** Aucune ; interdictions détaillées en prose (cohérentes avec
  `tools`).
- **Runtime.** Aucun.
- **Compatibilité A0.** Compatible F0. Recouvre partiellement `repo-architect` (annexe A).
  Verdicts `CARTOGRAPHY_COMPLETE/PARTIAL/BLOCKED`.
- **Spec envisagée.** `SENSOR`, F0 ; `REPOSITORY_READ`, `REPOSITORY_SEARCH`,
  `STATIC_ANALYSIS`.
- **Statut.** `MIGRATION_CANDIDATE`.
- **Remédiation.** Spec ; dédoublonner avec `repo-architect`.

### 2.7 `security-Guardian-agent` — 119 lignes

- **Objectif.** Vérifier sécurité, invariants de gouvernance, frontières
  Research/Paper/Live ; relire branche/diff/commits.
- **Pouvoirs déclarés.** Front matter **ouvert sans fermeture**, seuls `name` et
  `description` ; **aucun `tools`**. Comportement plateforme d'un `tools` omis : **non
  vérifié** (traité comme non borné).
- **Écriture/exécution.** Indéterminée ; prose « Ne jamais… ».
- **Runtime.** Cite `GlobalRiskGate`, `RuntimeStateMachine`, `SAFE_MODE` : ces symboles
  **existent** (`risk/global_risk_gate.py`, `quant_hedge_ai/runtime/runtime_state_machine.py`).
- **Compatibilité A0.** Sa fonction (relecture sécurité) est `SECURITY_REVIEW` = F4
  **réservé** ; elle ne peut être enregistrée en V1 qu'en diagnostic F2. Écarts : « Tu
  es le dernier rempart » (auto-attribution d'autorité finale, contraire à
  `REVIEW != AUTHORITY`) ; verdict `PASS` (absence de finding ≠ acceptation).
- **Spec envisagée.** `SECURITY` ; F4 réservé ; V1 intérimaire F2 (`REPOSITORY_READ`,
  `REPOSITORY_SEARCH`, `STATIC_ANALYSIS`, `DIAGNOSTIC_PRODUCE`) **sans** fonction de
  veto.
- **Statut.** `REVIEW_REQUIRED`.
- **Remédiation.** Fermer le front matter ; déclarer `tools` en lecture ; retirer
  « dernier rempart » ; borner `BLOCK` à un *finding bloquant* d'un futur F4.

### 2.8 `sniper-engine` — 20 lignes — **BLOQUÉ**

- **Objectif.** « Exécution rapide sur les opportunités de trading (sniping) ».
- **Pouvoirs déclarés.** **Aucun front matter** : ni `name`, ni `description`, ni
  `tools`. Chargeabilité par la plateforme **inconnue** ; atteignable par délégation
  depuis `hedge-fund-architect` (2.3).
- **Écriture/exécution.** Décrit « Exécute des ordres d'achat/vente en quelques
  secondes », « Achat instantané », sur « pools de liquidité » et « nouveaux tokens ».
- **Runtime.** Si activé avec des outils : écriture d'ordres = `EXCHANGE_WRITE`
  (interdit, A0 §6). Contraire à #286. L'exemple « Résultat : +12% en 2 minutes » est
  une performance **illustrative non sourcée** ; ne pas la lire comme un fait.
- **Compatibilité A0.** **Incompatible** tant que réécrit. Aucune classe/niveau V1 ne
  peut le représenter.
- **Spec envisagée.** Aucune.
- **Statut.** `BLOCKED_LEGACY_RECONCILIATION`.
- **Remédiation.** Décision humaine : `ARCHIVE` ou réécriture sans exécution. `UNKNOWN`
  ⇒ ne pas supprimer. Ne pas modifier ici. Retirer la référence `agents: [sniper-engine]`
  fait partie de la réconciliation de `hedge-fund-architect`.

### 2.9 `statistician-agent` — 132 lignes

- **Objectif.** « Contre-pouvoir statistique » : biais, validité, `INSUFFICIENT EVIDENCE`.
- **Pouvoirs déclarés.** Front matter non fermé ; **aucun `tools`** (comportement
  plateforme non vérifié).
- **Écriture/exécution.** Indéterminée ; fonction purement analytique en prose.
- **Runtime.** Aucun.
- **Compatibilité A0.** Fonction = `STATISTICAL_REVIEW` (F4 **réservé**). Verdicts
  `SUPPORTED/PROMISING/…/REJECTED` : `SUPPORTED` pourrait être lu comme une acceptation
  (A0 §1). Chevauche le domaine Research (Q6).
- **Spec envisagée.** `REVIEWER` (réservé) ⇒ **non enregistrable en V1** ; pas de spec
  intérimaire recommandée (la déguiser en `DIAGNOSTIC` F2 travestirait une fonction
  de review).
- **Statut.** `REVIEW_REQUIRED` (bloqué par un niveau réservé, pas par un risque).
- **Remédiation.** Fermer le front matter, déclarer des outils de lecture, renommer les
  verdicts ; attendre A7.

### 2.10 `system-diagnostic` — 139 lignes

- **Objectif.** Diagnostic Linux/VPS/systemd/processus/réseau/runtime.
- **Pouvoirs déclarés.** Front matter non fermé ; **aucun `tools`**. Liste des
  commandes « non destructives » (`systemctl status`, `journalctl`, `ps`, `ss`, `lsof`,
  `df`, `free`, …) et règle d'escalade humaine avant tout arrêt/modification.
- **Écriture/exécution.** Indéterminée ; la prose interdit restart/suppression/kill.
- **Runtime.** **Vise le VPS/runtime** : exige une lecture runtime que A0 exclut
  volontairement. Si des outils d'exécution étaient disponibles par défaut, ce profil
  pourrait toucher le runtime gelé (#286).
- **Compatibilité A0.** Partie dépôt compatible (`SRE`, F2) ; partie runtime hors forêt.
- **Spec envisagée.** `SRE`, F2, `REPOSITORY_READ`, `REPOSITORY_SEARCH`,
  `DIAGNOSTIC_PRODUCE`, **sans** lecture runtime.
- **Statut.** `REVIEW_REQUIRED`.
- **Remédiation.** Scinder dépôt/runtime ; les checkpoints VPS READ-ONLY restent des
  **missions humaines distinctes** (#282, #309) ; fermer le front matter.

---

## 3. Constats transverses

| ID | Classe | Constat |
|---|---|---|
| X1 | NEEDS_REVIEW | 4 profils sur 10 (7, 8, 9, 10) n'ont aucun `tools` ; leur pouvoir effectif dépend d'un comportement plateforme **non vérifié ici**. Le profil 3 déclare un `tools` explicite mais très large (`edit`, `execute`, `agent`) |
| X2 | BLOCKING (migration) | profils 3 et 8 : exécution d'ordres/édition+exécution+délégation (voir fiches) |
| X3 | NEEDS_REVIEW | verdicts auto-labellisés dans les profils lecture seule (A0 §16 I7) |
| X4 | OBSERVED | seuls 5 profils portent `disable-model-invocation: true` + `user-invocable: true` (1, 2, 4, 5, 6) ; les autres n'ont pas cette garde déclarée |
| X5 | NON_BLOCKING | `repository-cartographer` et `repo-architect` (annexe) se recouvrent |
| X6 | OBSERVED | `.github/CODEOWNERS` couvre `/.github/` : modifier un profil exige déjà une revue du propriétaire ; `docs/contracts/` n'est pas couvert (A0 §16 I8) |

---

## Annexe A — profils hors du motif demandé (observés, non migrés)

Deux profils `*.agent.md` existent **hors** de `.github/agents/`, à la racine de
`.github/`. Ils ne faisaient pas partie du périmètre demandé ; ils sont notés pour ne
pas laisser de surface d'agent non vue. Même lecture intégrale.

| Profil | Lignes | `tools` | Résumé | Statut proposé |
|---|---|---|---|---|
| `.github/repo-architect.agent.md` | 103 | aucun ; front matter non fermé | cartographie d'architecture ; « NE MODIFIE PAS LE CODE » (prose) ; renvoie des spécifications à « Test Engineer » / « Engineer/implementation workflow », **qui n'existent pas** parmi les profils | `REVIEW_REQUIRED` ; classe envisagée `SENSOR` F0 ; chevauche `repository-cartographer` |
| `.github/research-scientist.agent.md` | 139 | aucun ; front matter non fermé | conception d'expériences reproductibles ; cite `GlobalRiskGate` et « paramètres Live » | `REVIEW_REQUIRED` ; classe `RESEARCH` plafonnée F1 en V1 ; frontière Research ↔ forêt (A1 Q6) |

## Annexe B — autres surfaces d'instruction non inventoriées

Non auditées par cette mission (A0 §16 I5) : `.github/copilot-instructions.md`
(décrit une architecture legacy absente de l'arbre : `crypto_quant_v16`,
`quant-ai-system`, `main_v16.py`), `.github/prompts/*.prompt.md`
(`memecoin-scanner`, `bot-doctor-*`, `enhance-bot-platform-doctor`),
`.github/instructions/bot-doctor.instructions.md`, `.github/skills/`. Classe
`NEEDS_REVIEW` ; mission future d'extension de l'inventaire.
