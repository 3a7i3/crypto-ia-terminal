# Governance Tower — Matrice de réutilisation (GOV-TOWER-00, lot A)

Décisions : **REUSE** (importé ou repris tel quel), **PATTERN** (discipline reprise, code non importé),
**ISOLATE** (ne pas importer ni coupler), **FUTURE** (hors mandat, gate distincte), **KEEP** (inchangé).
Aucun fichier existant n'est modifié par GOV-TOWER-00.

| Module existant | Décision | Risque si couplé | Justification / preuve |
|---|---|---|---|
| `observability/runtime_service_contract.py` | REUSE (import) | faible : module pur | « no systemd or Advisor I/O here » ; validateur des snapshots déjà publiés (G3–G5, #286) |
| `observability/storage_contract.py` (+ `event_center_contract.py` transitif) | REUSE (import) | faible : module pur | « no filesystem scan or runtime imports » |
| `observability/operator/contracts.py` (`FreshnessStatus`, `NullSemantics`) | PATTERN | lier GT au cycle de vie Operator | vocabulaire repris dans `governance_tower/contracts.py` |
| `observability/operator_api/*` (FastAPI, readers) | ISOLATE | autorité de présentation Operator ; dépendance FastAPI | consommable seulement par HTTP GET opt-in (`OperatorApiHostProvider`) |
| `frontend/` (React, routeur, PWA, session) | ISOLATE | mélange de navigation et d'autorité, contraire à #459 | couleurs de `frontend/src/tokens.css` reprises par valeur |
| `frontend/src/lib/githubRoadmapReader.ts` | PATTERN | — | budget de requêtes, erreurs typées, titres seulement, corps jamais lus |
| `lab01/api.py`, `lab01/ui/` | PATTERN | — | serveur stdlib loopback, CSP, page autonome, tests dédiés |
| `governance/` (decision_router, risk_authorizer, execution_approval) | ISOLATE (import interdit, testé) | autorité de trading | nom de paquet distinct `governance_tower/` |
| `core/`, `paper_trading/`, `financial_institute/` | ISOLATE (import interdit, testé) | burn-in, PPL, FIN | #286 |
| `lab01/ops/`, unités systemd, scripts G2–G5 | KEEP / ISOLATE | installation sur l'hôte | GT ne livre aucune unité ni script (testé) |
| OperatorDecision D5B-R2 (#315) | FUTURE | autorité de décision | aucune file d'approbation avant Gate O |
| Passerelle d'opérations #445 | FUTURE | exécution privilégiée | Sentinel peut seulement *proposer* une mission |
| Agent Registry #374, Agent Economy #284 | FUTURE | économie/paiements | refus `TRADING_OR_PAYMENT_DENIED` |
| CI `ci.yml`, portail ruff | KEEP | — | nouveaux tests sous `tests/governance_tower/` collectés automatiquement ; aucun workflow modifié |
