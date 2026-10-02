# HANDOFF — APP-UNIFY U2 / BurnInStatusSnapshot

Date de handoff : 2026-10-01
Projet : `Crypto AI Terminal — Research Infrastructure`
Repository : `3a7i3/crypto-ia-terminal`

Ce document est la source de reprise recommandée pour une nouvelle conversation.

---

## 1. État global du programme APP-UNIFY

Programme parent :

- #323 — `APP-UNIFY-01 — Operator App unique, cockpit burn-in autonome et intégration CryptoRadar`

Roadmap :

- #285

Freeze runtime/burn-in :

- #286 reste **ACTIVE**
- ne pas fermer #286
- aucun changement de runtime/burn-in n'est autorisé implicitement par U2

### U0 — terminé

Issue :

- #324 — carte exacte de ce que l'app sait / ne sait pas

PR :

- #325

Merge U0 :

- `397c07ecae66eb4d78f9668d9246c47804d1915a`

Résultat principal :

- l'Operator App est la bonne fondation ;
- plusieurs données existaient déjà mais étaient sous-utilisées ;
- `portfolio_status` existait mais était typé `Record<string, unknown>` côté frontend ;
- le vieux CryptoRadar ne doit pas être copié tel quel ;
- Scanner et LMI doivent être intégrés comme projections gouvernées ;
- les anciens signaux Entry/SL/TP ne doivent pas être injectés dans MARKET.

### U1 — terminé

Issue :

- #326 — Vue Propriétaire avec données existantes

PR :

- #327

HEAD final U1 :

- `e5d93908c433c3d3c5dff338b7edbe558cc9361f`

Merge U1 / main avant U2 :

- `a2032b13982ae270cb8cd6e0f96c45ed6d53b721`

Verdict :

- `APP_UNIFY_U1_OWNER_VIEW_SOURCE_READY`

U1 a ajouté :

- contrat frontend fermé `PortfolioStatus` ;
- validation stricte de `portfolio_status` ;
- compteur courant canonique = `paper_open_positions_count` ;
- plafond = `portfolio_status.hard_position_limit` ;
- admission affichée seulement lorsque les compteurs concordent ;
- désaccord => `INCOHÉRENT`, sans réparation/inférence ;
- mode, capital PAPER, source SHA/evidence, worktree, fraîcheur et stale reason au niveau propriétaire ;
- positions ouvertes et âge UI au snapshot ;
- global `INCONNU` et sémantique fédérée/non atomique conservés.

---

## 2. Freeze runtime à ne pas casser

Le checkout runtime VPS reste volontairement gelé sur :

`116634be0d3c015cce1cfa58be7da7255414fbfd`

Burn-in :

`BURN-IN-EPOCH-01-20260926T064144Z`

Config semantic snapshot SHA :

`9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4`

T0 gouverné connu dans les travaux scientifiques précédents :

`2026-09-27T03:06:03.086973Z`

Important :

- le runtime checkout ne doit pas être avancé sur `main` ;
- aucun restart Advisor n'a été fait pour APP-UNIFY ;
- aucun changement PPL/FIN/epoch/config/risk/sizing/`PB_MAX_POSITIONS` n'a été fait ;
- U2 est **SOURCE-ONLY** ;
- le futur déploiement/publisher U2 doit avoir sa propre gate compatible #286.

---

## 3. État scientifique burn-in connu avant U2

Dernier checkpoint PPL read-only documenté avant APP-UNIFY U2 :

- event_count = 63 ;
- last_sequence = 63 ;
- POSITION_OPENED = 32 ;
- POSITION_CLOSED = 30 ;
- POSITION_UNRESOLVED = 0 ;
- OPEN = 2 ;
- PPL append-only stable à ce checkpoint ;
- realized PnL = `-0.6565499307274114` ;
- fees_paid = `0.6200000000000003` ;
- available_cash = `981.1870206508428` ;
- reserved_principal = `20.0`.

À ce checkpoint, les deux positions capturées étaient encore OPEN :

- `521E1597-3`
- `63858D4C-1`

Le probe O9 avait montré :

- `MEXC_SIM_MAX_POSITION_USD=10`
- `PB_MAX_POSITIONS=2`
- `PAPER_PORTFOLIO_BRAIN_LEVEL=a`

et les positions avaient une deadline timeout à environ 8 h avec une fenêtre recovery supplémentaire.

Ces valeurs sont des **preuves VPS ponctuelles historiques**, pas une source produit actuelle.
U2 ne doit jamais lire `/proc/<pid>/environ` comme vérité de configuration affichée.

---

## 4. Pourquoi U2 existe

Les captures d'écran de l'app montraient :

- Portfolio : positions ouvertes visibles mais historique incomplet ;
- PPL Compare : événements PPL bruts, utile pour preuve technique mais pas adapté comme historique opérateur ;
- Financial : vue FIN détaillée, parfois stale ;
- aucune vue consolidée permettant de savoir immédiatement :
  - quelle epoch tourne ;
  - combien d'événements PPL ont été produits ;
  - combien de trades OPEN/CLOSED/UNRESOLVED existent ;
  - quelles positions sont encore ouvertes ;
  - leurs deadlines ;
  - l'historique des ordres ;
  - la provenance config/code/PPL ;
  - l'état de finalisation du burn-in.

Objectif U2 :

> comprendre le burn-in depuis l'app sans ouvrir le VPS.

---

## 5. Issue et PR U2

Issue :

- #328 — `APP-UNIFY-01-U2 — BurnInStatusSnapshot et historique des ordres PAPER`

PR :

- #329 — `APP-UNIFY U2 — BurnInStatusSnapshot et historique PAPER`

Branche :

- `feat/328-app-unify-u2-burn-in-status`

Base PR :

`a2032b13982ae270cb8cd6e0f96c45ed6d53b721`

HEAD courant au moment du handoff :

`5c69b7e56f7b7c95c6326061fecd335ea786ac2c`

PR :

- OPEN ;
- DRAFT ;
- mergeable = true ;
- aucun review thread ;
- aucun review bloquant.

Ne pas merger tant que les deux visual proofs restants ne sont pas corrigés et verts.

---

## 6. Architecture U2 décidée

Architecture obligatoire :

```text
PPL Durable Event Stream + BURN_IN_EXPERIMENT_CONFIG_V1
                         ↓
BurnInStatusSnapshot producer READ-ONLY
                         ↓
artifact JSON atomique
                         ↓
strict Operator API reader
                         ↓
GET /api/operator/v1/burn-in
                         ↓
Direction summary + PAPER LIVE / Burn-in
```

Frontières interdites :

```text
React -> PPL JSONL direct                INTERDIT
Operator API -> PPL JSONL direct         INTERDIT
frontend -> calcul lifecycle/PnL         INTERDIT
frontend -> calcul deadline scientifique INTERDIT
U2 producer -> append PPL                INTERDIT
U2 producer -> créer lock PPL            INTERDIT
```

Le producteur U2 est le seul composant autorisé à lire la frontière source PPL/config.

---

## 7. Lecture PPL read-only : décision importante

Nous avons inspecté `DurableEventStore`.

Certaines méthodes de store utilisent un lock.
Pour un producteur de présentation strictement passif, U2 **n'utilise pas**
le store de façon susceptible de créer/toucher le lock.

Méthode U2 :

1. calcule le fichier d'epoch par SHA256(epoch_id) ;
2. exige un fichier régulier non symlink ;
3. lit une frontière append-only stable ;
4. vérifie taille + mtime avant/après ;
5. exige newline finale ;
6. décode chaque record via le wire-format canonique PPL ;
7. exige que la re-sérialisation canonique soit byte-identical ;
8. vérifie :
   - epoch_id ;
   - sequence contiguë ;
   - event_id unique ;
9. projette avec le vrai `paper_portfolio_ledger.project()` ;
10. n'écrit jamais dans le PPL store.

Le cross-stack U2 contient une preuve explicite :

`ppl_lock_created == false`.

---

## 8. T0 : découverte importante

Recherche source effectuée sur :

- `T0`
- `BURN_IN_T0`
- timestamps connus du burn-in
- contrats de navigation/Direction
- Research/burn-in code

Conclusion :

**scientific T0 n'est pas automatiquement égal à EPOCH_CREATED.**

Donc U2 :

- expose `epoch_created_at_utc` séparément ;
- expose `scientific_t0` avec :
  - `PRESENT` + valeur + source explicite ;
  - ou `NOT_AVAILABLE` ;
- n'infère jamais T0 depuis l'epoch.

Sans artifact/provenance gouvernée :

```json
{
  "status": "NOT_AVAILABLE",
  "value_utc": null,
  "source": null
}
```

---

## 9. Identité config/code/PPL

Le moteur de freeze a été inspecté.

Les préfixes matériels comprennent notamment :

- `PB_`
- `PAPER_`
- `MEXC_SIM_`

Le snapshot scientifique est :

`BURN_IN_EXPERIMENT_CONFIG_V1`

U2 exige une identité triple fail-closed :

```text
PPL epoch.paper_epoch_id
  == config.paper_epoch_id

PPL epoch.code_sha
  == config.runtime_source_sha

PPL epoch.config_snapshot_hash
  == config.snapshot_sha256
```

Whitelist opérateur publiée :

- `PB_MAX_POSITIONS`
- `PAPER_PORTFOLIO_BRAIN_LEVEL`
- `MEXC_SIM_MAX_POSITION_USD`
- `MEXC_SIM_MAX_AGE_H`
- `PAPER_LIFECYCLE_AUTHORITY`

Aucun dump complet d'environnement.

---

## 10. Contrat BurnInStatusSnapshot

Le contrat fermé contient notamment :

### Identité/provenance

- schema_version ;
- product ;
- domain ;
- authority ;
- mode READ_ONLY ;
- generated_at_utc ;
- source_updated_at_utc ;
- paper_epoch_id ;
- epoch_created_at_utc ;
- source_code_sha ;
- config_snapshot_hash ;
- ppl_stream_sha256 ;
- scientific_t0.

### Progression

- event_count ;
- last_sequence ;
- event_counts :
  - EPOCH_CREATED ;
  - POSITION_OPENED ;
  - POSITION_CLOSED ;
  - POSITION_UNRESOLVED ;
  - RECOVERY_COMPLETED ;
- lifecycle_counts :
  - open ;
  - closed ;
  - unresolved ;
  - total ;
- last_event.

### OPEN lifecycles

- trade_id ;
- decision_id ;
- symbol ;
- side ;
- principal_usd ;
- entry_price ;
- entry_fee_usd ;
- opened_sequence ;
- opened_at_utc ;
- age_seconds ;
- tp_price ;
- sl_price ;
- timeout_at_utc ;
- recovery_eligible_until_utc ;
- deadline_state.

Deadline states :

- `BEFORE_TIMEOUT`
- `RECOVERY_WINDOW`
- `RECOVERY_EXPIRED`
- `NOT_AVAILABLE`

Deadlines sont calculées **côté producteur**, jamais dans React.

---

## 11. Historique des ordres / lifecycles

L'utilisateur a explicitement demandé une vue historique des ordres.

U2 publie :

`lifecycle_history`

Une ligne par trade PPL, sans doublon, tri :

`OPEN_SEQUENCE_DESC`

Champs :

- trade_id ;
- open_decision_id ;
- terminal_decision_id ;
- symbol ;
- side ;
- principal_usd ;
- entry_price ;
- entry_fee_usd ;
- opened_sequence ;
- opened_at_utc ;
- status ;
- terminal_sequence ;
- terminal_at_utc ;
- exit_price ;
- exit_fee_usd ;
- gross_pnl_usd ;
- net_realized_pnl_usd ;
- unresolved_reason ;
- duration_seconds.

Sémantique stricte :

### OPEN

Aucun :

- exit_price ;
- exit_fee ;
- gross PnL ;
- net PnL ;
- terminal timestamp ;
- duration terminal.

### CLOSED

Le producteur recalcule le gross PnL selon la comptabilité canonique PPL puis :

```text
net_realized_pnl
  = gross_pnl
  - entry_fee
  - exit_fee
```

Puis le total CLOSED est réconcilié contre :

`PaperPortfolioState.realized_pnl`

Fail-closed si divergence.

### UNRESOLVED

Aucun faux :

- exit ;
- gross PnL ;
- net PnL.

La raison durable `unresolved_reason` est conservée.

---

## 12. Finalisation du burn-in

U2 ne déduit jamais qu'un burn-in est terminé.

Aucun scraping GitHub des verdicts O1…O9.

Sans artifact gouverné explicite :

```text
finalization.state = NOT_AVAILABLE
finalization.reason = NO_GOVERNED_FINALIZATION_ARTIFACT_SUPPLIED
```

Cela évite de confondre documentation scientifique et vérité runtime.

---

## 13. UI U2 construite

Nouvelle route :

`/paper-live/burn-in`

Nouveau sous-onglet :

`Burn-in`

La page contient :

1. résumé burn-in ;
2. OPEN / CLOSED / UNRESOLVED ;
3. dernier événement ;
4. T0 scientifique ;
5. positions ouvertes ;
6. deadlines ;
7. historique des ordres ;
8. config gelée/provenance ;
9. finalization state.

### Desktop

Historique sous forme de table.

### Mobile <= 720px

Le tableau desktop est caché.
L'historique devient une liste de cartes.

But :

- ne pas reproduire les très grandes tables illisibles vues sur les captures mobiles ;
- pouvoir lire symbole/statut/PnL/durée/trade_id sur téléphone.

### Direction

Une cinquième source indépendante est ajoutée :

`GET /api/operator/v1/burn-in`

La carte Direction Burn-in montre :

- epoch ;
- event_count ;
- last_sequence ;
- OPEN/CLOSED/UNRESOLVED ;
- T0 ;
- dernier événement ;
- OPEN lifecycles + deadline ;
- provenance/config.

La doctrine Direction reste :

`FÉDÉRÉ · NON ATOMIQUE`

Aucun état global n'est inféré.

---

## 14. Recherche source exécutée pendant U0/U1/U2

Les fichiers/composants suivants ont été inspectés.

### Operator App / snapshots

- `observability/operator_snapshot_builder.py`
- `frontend/src/types.ts`
- `frontend/src/lib/snapshotValidation.ts`
- `frontend/src/views/DirectionOverview.tsx`
- `frontend/src/views/PortfolioView.tsx`
- `frontend/src/App.tsx`
- `frontend/src/shells/PaperLiveShell.tsx`
- routing/tests frontend

Découvertes :

- `portfolio_status` existait déjà côté producer ;
- il n'était pas typé/validé strictement côté frontend ;
- `paper_open_positions_count` possède une meilleure sémantique de compteur matérialisé ;
- Direction est fédérée et ne doit pas devenir une synthèse atomique artificielle.

### PPL / lifecycle

- `paper_trading/ledger_events.py`
- `paper_trading/paper_portfolio_ledger.py`
- `paper_trading/ppl_authority_runtime.py`
- `paper_trading/durable_event_store.py`
- composants paper portfolio view/status

Découvertes :

- les événements autoritaires suffisants existent pour reconstruire un historique lifecycle ;
- OPEN/CLOSED/UNRESOLVED doivent rester sémantiquement distincts ;
- les deadlines timeout/recovery sont portées par l'état OPEN projeté ;
- le store possède des mécanismes de lock qu'un producteur de présentation passif ne doit pas déclencher ;
- `project()` est la référence sémantique canonique.

### Freeze/config

- `scripts/f00_experiment_config_freeze.py`
- `scripts/burn_in_experiment_config_freeze.py`
- tests RB3/burn-in freeze
- recherches :
  - `BURN_IN_EXPERIMENT_CONFIG_V1`
  - `PB_MAX_POSITIONS`
  - `MEXC_SIM_MAX_POSITION_USD`
  - `MEXC_SIM_MAX_AGE_H`
  - `PAPER_PORTFOLIO_BRAIN_LEVEL`

Découvertes :

- PB_/PAPER_/MEXC_SIM_ sont matériels dans le freeze ;
- la config affichée doit venir du snapshot gelé, pas du process env live ;
- `PB_MAX_POSITIONS=2` était aussi confirmé par l'overlay/runtime probe historique.

### T0 / burn-in

Recherches :

- `T0`
- `BURN_IN_T0`
- timestamps connus
- contrats Direction/navigation
- Research finalization

Découverte :

- T0 scientifique est une notion distincte de EPOCH_CREATED ;
- pas d'inférence autorisée.

### Operator API / readers

Inspectés :

- `observability/operator_api/app.py`
- readers Market/FIN/Research
- patterns d'artifact atomique

Décision :

- U2 suit le pattern reader strict GET-only ;
- Operator API ne lit jamais PPL directement.

### Cross-stack

Inspectés :

- `.github/workflows/cross-stack-compat.yml`
- `tests/cross_stack/generate_fixtures.py`
- `frontend/src/test/crossStack.compat.test.tsx`

U2 ajoute :

- `tests/cross_stack/generate_burn_in_fixture.py`
- fixture J burn-in produite via vrai producteur U2 ;
- vrai endpoint FastAPI ;
- vrai validateur/frontend ;
- assertion `ppl_lock_created=false`.

### Visual proof

Inspectés/modifiés :

- `frontend/scripts/capture_web_dir_d3_visual.mjs`
- workflow Direction visual
- nouvelle preuve U2 :
  - `frontend/scripts/capture_app_unify_u2_visual.mjs`
  - `.github/workflows/app-unify-u2-visual-proof.yml`

Objectif :

- desktop historique ;
- mobile cartes ;
- no horizontal overflow ;
- no mutation HTTP ;
- Direction cinquième source.

---

## 15. Commits U2 exacts

PR #329 contient actuellement :

1. `bd52c63782d99ffabb5160873f7853ca985f2985`
   - créer la projection BurnInStatus read-only

2. `9045cf65bc0d1ebae783c96e7479f127eff9f6f0`
   - corriger le lint du contrat burn-in

3. `787165c5ddd40f0dd7e96f72391a8b2153921494`
   - contrat frontend + historique PAPER

4. `759244060fc0223593b2537eb6d8b4dde2a829b2`
   - brancher Burn-in dans PAPER LIVE et Direction

5. `be2cab36c5d5631667260a61a00ab5088470fcde`
   - étendre tests Direction à la source burn-in

6. `8636b733e7d908b24019c4ff9799ffab7b386226`
   - preuve cross-stack burn-in

7. `e41deead5bfc5f92485e68a4abca7fe69b424a3f`
   - preuve Direction burn-in

8. `87cb0a81af5e0e5e33faf9c784400f51f0af1d03`
   - preuve historique desktop/mobile

9. `a19a58ee27a9908695a4647f0eb20d8d41f12ca6`
   - mise à jour routing Direction 5 sources

10. `1da52a1fdfaf97c4b4fa9b63c1300e89d2eee835`
    - correction narrowing TypeScript

11. `5c69b7e56f7b7c95c6326061fecd335ea786ac2c`
    - nettoyage du contrat source

---

## 16. Erreurs rencontrées et corrections déjà faites

### A. Lint Python

Erreur :

- import inutilisé dans `burn_in_status_contract.py`

Corrigé au SHA :

`9045cf65...`

### B. Routing Direction

Ancien test attendait 4 GET.
U2 introduit la cinquième source Burn-in.

Corrigé :

- test renommé ;
- attente = 5 GET ;
- endpoint burn-in explicitement vérifié.

SHA :

`a19a58ee...`

### C. TypeScript build/narrowing

269 tests frontend passaient mais le build échouait sur :

- narrowing `duration_seconds` ;
- type du `Set` des événements.

Corrigé au SHA :

`1da52a1f...`

### D. Nettoyage contrat source

Whitespace Markdown uniquement.

SHA :

`5c69b7e5...`

---

## 17. CI actuelle au handoff

HEAD :

`5c69b7e56f7b7c95c6326061fecd335ea786ac2c`

### Verts

- integrity
- frontend
- test
- TEST REGRESSION GATE
- LINT REGRESSION GATE
- Smoke test
- CROSS-STACK COMPATIBILITY GATE
- coverage
- codecov
- coveralls
- COVERAGE REGRESSION BASELINE
- LONG-RUN PERFORMANCE GATE
- semgrep
- WEB-01 MARKET VISUAL PROOF
- WEB-02 PPL VISUAL PROOF
- FIN-02 FINANCIAL VISUAL PROOF
- WEB-RL RESEARCH VISUAL PROOF
- screenshots

### Rouges restants

Deux seulement :

1. `APP-UNIFY U2 BURN-IN VISUAL PROOF`
2. `WEB-DIR-01 D3 DIRECTION VISUAL PROOF`

Aucun check pending au moment du handoff.

---

## 18. Cause exacte des deux visual failures

### 18.1 U2 Burn-in visual

Erreur exacte :

`desktop Burn-in evidence missing: RECOVERY_PRICE_UNAVAILABLE`

Cause :

- le fixture contient bien un lifecycle UNRESOLVED avec
  `unresolved_reason=RECOVERY_PRICE_UNAVAILABLE` ;
- la vue mobile affiche cette raison dans la carte ;
- la table desktop actuelle affiche statut/PnL/durée mais **pas la colonne reason** ;
- le script desktop exigeait pourtant cette chaîne.

Ce n'est pas un défaut backend/contrat.

Décision recommandée :

**ajouter une colonne “Raison” dans le tableau desktop**.

Pourquoi :

- l'issue #328 exige explicitement `unresolved_reason` dans l'historique ;
- cela améliore le produit ;
- le desktop doit être aussi informatif que les cartes mobile ;
- ensuite garder l'assertion visuelle.

Ne pas simplement supprimer l'assertion si la colonne peut être affichée proprement.

### 18.2 Direction visual

Erreur exacte :

`U2 Direction burn-in evidence missing: T0 scientifique`

Le composant Direction contient bien le label :

`T0 scientifique`

La cause la plus probable du mismatch est le rendu `innerText()` avec
`text-transform: uppercase` sur les labels, qui produit visuellement :

`T0 SCIENTIFIQUE`

alors que le test compare une chaîne case-sensitive.

Décision recommandée :

- rendre l'assertion case-insensitive ;
- par exemple normaliser `burnInText.toLowerCase()` ;
- ne pas changer le produit pour satisfaire la casse du test.

---

## 19. Prochaine action exacte dans une nouvelle conversation

### Étape 1 — reprendre #329 au HEAD exact

Vérifier :

`5c69b7e56f7b7c95c6326061fecd335ea786ac2c`

et que `main` reste :

`a2032b13982ae270cb8cd6e0f96c45ed6d53b721`

### Étape 2 — corriger les 2 visual proofs seulement

A. Dans `BurnInStatusView.tsx` :

- ajouter colonne desktop `Raison` ;
- afficher `row.unresolved_reason ?? "—"`.

B. Dans `capture_web_dir_d3_visual.mjs` :

- assertion T0 case-insensitive / texte normalisé.

Aucune autre modification fonctionnelle.

### Étape 3 — rerun CI sur nouveau HEAD

Attendre :

- U2 Burn-in visual = PASS ;
- Direction visual = PASS ;
- tous les anciens gates toujours verts ;
- aucun review thread ;
- main inchangé ou rebase/review explicite si main bouge.

### Étape 4 — revue finale

Vérifier le diff complet #329 :

- aucun Advisor ;
- aucun risk/sizing ;
- aucun execution ;
- aucun systemd ;
- aucun PPL write ;
- API GET-only ;
- producteur read-only ;
- frontend strict.

### Étape 5 — sortir du draft et merge si tout est vert

Verdict cible :

`APP_UNIFY_U2_BURN_IN_STATUS_SOURCE_READY`

Mettre à jour :

- #328 ;
- #323.

### Étape 6 — NE PAS déployer automatiquement

Après merge source :

- runtime reste sur `116634be...` ;
- #286 reste ACTIVE ;
- créer/traiter une gate séparée pour publier réellement
  `BurnInStatusSnapshot` sur le VPS ;
- cette gate doit être passive, compatible burn-in et sans restart Advisor si possible.

U2b `RuntimeServiceSnapshot` reste une mission distincte :
elle doit apporter la preuve host/systemd Advisor, pas être confondue avec
le publisher BurnInStatus.

---

## 20. Règles de reprise à conserver

1. Une gate à la fois.
2. Source certification avant runtime.
3. Aucun déploiement implicite.
4. Aucun restart Advisor pendant #286 sans exception explicite.
5. React ne lit pas les fichiers autoritaires.
6. Operator API ne lit pas directement le PPL.
7. Aucun PnL inventé.
8. UNRESOLVED reste UNRESOLVED.
9. T0 n'est jamais assimilé à EPOCH_CREATED.
10. Le vieux CryptoRadar sera retiré seulement après parité app + gate séparée.
11. L'app doit devenir le cockpit principal pour éviter d'ouvrir le VPS.
12. Les preuves desktop et mobile sont obligatoires pour les surfaces importantes.

---

## 21. Prompt de reprise court pour une nouvelle conversation

```text
Projet : 3a7i3/crypto-ia-terminal

Reprendre APP-UNIFY U2 depuis :
docs/handoffs/APP_UNIFY_U2_HANDOFF_2026-10-01.md

Issue : #328
PR : #329
Branch : feat/328-app-unify-u2-burn-in-status
HEAD attendu au handoff : 5c69b7e56f7b7c95c6326061fecd335ea786ac2c
Base/main attendu : a2032b13982ae270cb8cd6e0f96c45ed6d53b721

#286 reste ACTIVE.
Ne pas toucher au runtime/VPS/Advisor/PPL/config/risk/sizing.

Il reste 2 visual failures uniquement :
1. U2 desktop : unresolved_reason absent du tableau desktop.
   Ajouter colonne Raison, conserver l'assertion RECOVERY_PRICE_UNAVAILABLE.
2. Direction visual : assertion "T0 scientifique" sensible à la casse.
   Normaliser/case-insensitive.

Puis rerun toute la CI, revue HEAD/base/diff/threads.
Si tout est vert, sortir #329 du draft, merge au SHA exact, synchroniser #328/#323.
Ne pas déployer après le merge : runtime gate séparée.
```
