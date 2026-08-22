# Convergence Forensique — Read Only

Statut: **opérationnel**

Ce runbook implémente un protocole de restauration de confiance sans mutation runtime:

- **NE MODIFIE RIEN**
- **NE REDÉMARRE RIEN**
- **NE DÉPLOIE RIEN**
- **NE COMMIT RIEN sur VPS**

## Objectifs (gates)

- **P0-A** — Scientific Ledger survivability
- **P0-B** — VPS ↔ Git reconciliation
- **P1-A** — Persistence failure observability
- **P1-B** — CI constitutional coverage

Retour GO global uniquement si **P0-A=PASS** et **P0-B=PASS**.

---

## 1) Exécution du protocole

Depuis la racine du dépôt:

```bash
python tools/convergence_forensic_readonly.py
```

Sortie JSON complète:

```bash
python tools/convergence_forensic_readonly.py --json
```

Snapshot scientifique agrégé (versionnable, sans brut):

```bash
python tools/convergence_forensic_readonly.py \
  --snapshot-out docs/audit/scientific_snapshots/latest.json
```

Réconciliation VPS read-only:

```bash
python tools/convergence_forensic_readonly.py \
  --json \
  --vps-host <host> \
  --vps-user <user> \
  --vps-path <path_on_vps> \
  --vps-key <private_key_path>
```

Pré-requis SSH sécurité: la clé hôte VPS doit déjà être présente dans
`~/.ssh/known_hosts` (le protocole utilise `StrictHostKeyChecking=yes`).

---

## 2) Preuves collectées

Le protocole collecte:

1. SHA Git local + état dirty
2. Hash critiques locaux:
   - `core/advisor_loop.py`
   - `core/advisor_runtime_adapters.py`
   - `quant_hedge_ai/agents/intelligence/regime_detector.py`
3. Classification `regime_detector.py`: `ACTIVE/SHIM/LEGACY/ORPHAN/UNCERTAIN`
4. Ledger local:
   - `databases/paper_trades.jsonl`
   - `databases/regret_analysis.jsonl`
   - `databases/decision_packets*.jsonl`
5. Snapshot scientifique:
   - `epoch_clean_data_since`
   - CRI + provenance
   - hash du snapshot
6. Permissions + espace disque
7. Scan sémantique exceptions (`advisor_loop.py`)
8. Scan statique passivité observers
9. Couverture CI constitutionnelle (workflow `ci.yml`)
10. Si VPS renseigné:
   - SHA Git VPS + dirty state
   - `systemd ExecStart`, `MainPID`, service status
   - python exécutable, cwd, virtualenv
   - hash VPS des 3 fichiers critiques
   - journal persistence errors (24h)
   - stat des artefacts ledger

---

## 3) Check-list Zaki (Go/No-Go)

- [ ] SHA runtime VPS identifié et concordant avec la référence attendue
- [ ] `advisor_loop` actif identifié + hash local/VPS comparé
- [ ] `advisor_runtime_adapters` hash local/VPS comparé
- [ ] `regime_detector` réellement chargé identifié + hash validé
- [ ] `ExecStart` systemd exact documenté
- [ ] PID, cwd, python exécutable et venv réels prouvés
- [ ] Services actifs + derniers redémarrages tracés
- [ ] `paper_trades` : existence / taille / lignes / 1ère post-V4 / dernière
- [ ] `regret_analysis` : mêmes contrôles
- [ ] `decision_packets` : volume et fraîcheur mesurés
- [ ] MetaLearner classé : `PERSISTENT` / `EPHEMERAL` / `PARTIAL` / `BROKEN`
- [ ] Permissions filesystem + espace disque validés
- [ ] Journaux systemd : erreurs critiques de persistance traitées
- [ ] SHA git VPS prouvé + état dirty/non-committé établi
- [ ] Snapshot scientifique exportable produit
- [ ] `ObserverPurityInvariant` vérifié (statique + runtime)
- [ ] CI minimale constitutionnelle en place
- [ ] Verdict final Zaki : GO uniquement si `P0-A` et `P0-B` sont `PASS`

---

## 4) Interprétation des verdicts

- `PASS` : preuve suffisante dans le périmètre audité.
- `FAIL` : contradiction ou manque critique bloquant.
- `UNCERTAIN` : preuve insuffisante (souvent absence d’accès VPS).

Tant que `P0-A` ou `P0-B` n’est pas `PASS`, **aucune optimisation trading**.
