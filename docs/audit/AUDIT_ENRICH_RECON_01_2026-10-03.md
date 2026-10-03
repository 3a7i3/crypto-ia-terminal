# Revalidation source de l’audit historique #260

Mission [#349](https://github.com/3a7i3/crypto-ia-terminal/issues/349), roadmap
[#285](https://github.com/3a7i3/crypto-ia-terminal/issues/285), 3 octobre 2026 UTC.

**Verdict : AUDIT_ENRICH_RECON_01_TRIAGED_SOURCE_ONLY.** Ce verdict certifie le
triage, aucune remédiation des défauts ni observation du runtime.

## Baselines et portée

- Audit historique : PR #260, HEAD `70d41b32119ff0a58c22051c4d698befa7bb4b12`,
  source auditée `98082ef01e8bef93f86fe5e4d1d2af48dddec53e`.
- Source revalidée : `c561fae406950bf7813102b5b3f59c32388566d0`, après #344/#346/#343.
- Reproductions : worktree propre isolé, Python 3.12.14, pytest 9.1.1.
  Cette preuve locale ne remplace pas la CI Python 3.11 ni un checkpoint VPS.
- Aucun accès VPS, secret, store PPL réel ou artefact Machine ; aucun changement
  Advisor/PPL/FIN/stratégie/risk/sizing/config/epoch. #286 reste actif.
- U8 reste une préparation source ; les gates G0–G8 d’exécution ne sont pas levées.

Les populations et verdicts de septembre restent historiques. L’ancienne
référence runtime consignée n’a pas été réobservée. SOURCE ≠ RUNTIME.

## Matrice des onze findings

| Finding | État à la baseline source | Preuve / limite | Disposition |
|---|---|---|---|
| A-01 — tests dépendant du catalogue MEXC | REPRODUIT HORS RÉSEAU | Deux tests échouent avec `KeyError: BTCUSDT` quand `urlopen` est refusé ; aucun accès sortant exécuté | [#350](https://github.com/3a7i3/crypto-ia-terminal/issues/350), tests uniquement |
| A-02 — UNKNOWN compté comme perte | REPRODUIT SYNTHÉTIQUE | +2 / -1 / None donnent W=1/L=2/WR=1/3, sans warning ; aucun dataset réel examiné | [#351](https://github.com/3a7i3/crypto-ia-terminal/issues/351), contrat et population certifiable avant patch sensible |
| A-03 — univers 135/125/124 et doctrine | PARTIELLEMENT DÉPASSÉ / RUNTIME UNKNOWN | CLAUDE/ROADMAP ne portent plus un univers ancien comme état courant ; ADR V4 reste historique. Les références #174 ne prouvent pas l’univers instantané du burn-in | Provenance historique KEEP ; éventuelle observation actuelle dans #282, hors de cette mission |
| A-04 — vocabulaires de régime | SOURCE CONFIRMÉE | Enums core et TradeEvent diffèrent ; `trending` perd bull/bear. Des mappings legacy existent déjà dans core/contracts | [#352](https://github.com/3a7i3/crypto-ia-terminal/issues/352), contrat de comparabilité ; aucun diagnostic réel déclaré faux |
| A-05 — pont de conviction | SOURCE CONFIRMÉE, EXÉCUTION UNKNOWN | Aucun appel statique explicite trouvé hors core/contracts ; enum moteur distinct. Recherche statique limitée, pas de preuve d’erreur de sizing | [#353](https://github.com/3a7i3/crypto-ia-terminal/issues/353), cartographie sans changer les facteurs taille |
| A-06 — JSON non fini | SOURCE CONFIRMÉE / RESEARCH PARTIELLEMENT ABSORBÉ | Six appels legacy omettent allow_nan ; cela ne prouve aucun NaN réel. Les sérialisations canoniques Research actuelles sont strictes | [#354](https://github.com/3a7i3/crypto-ia-terminal/issues/354), examen des contrôles amont et contrats |
| A-07 — cycle core | SOURCE CONFIRMÉE | core/lifecycle importe decision_packet ; decision_packet importe lifecycle dans une fonction | Rattachement à [#207](https://github.com/3a7i3/crypto-ia-terminal/issues/207), pas de ticket de cycle concurrent |
| A-08 — PR #204 orpheline | DÉPASSÉ ADMINISTRATIVEMENT | #204 est CLOSED / non fusionnée au relevé GitHub ; aucune nouvelle action sur cette PR | Historique KEEP |
| A-09 — façade documentaire obsolète | ABSORBÉ PAR DOC-CANON-01 | #341 a reconstruit README/CLAUDE/CURRENT_TASK/ROADMAP et l’entrée développeur. BUGS n’était pas dans son périmètre | Aucun nouveau patch documentaire concurrent ; A-04/A-05 traités séparément |
| A-10 — ancien audit npm | ABSORBÉ PAR #257 | #344/#346 fusionnées et #257 clôturée ; ancien audit de septembre n’est plus la baseline de sécurité | Preuves historiques KEEP ; rapport canonique SEC_WEB_DEPS_01_REMEDIATION.md |
| A-11 — concentration/hygiène legacy | PARTIELLEMENT REVALIDÉE, DÉJÀ INVENTORIÉE | advisor_loop : 8 925 lignes ; docs/_build : 118 fichiers suivis. Le gate Panel E2E absent est documenté par son workflow | Inventaires #287/#338 et consolidation gouvernée ; aucun refactor/retrait pendant ce triage |

## Reproductions bornées

### A-01 : indisponibilité contrôlée du catalogue

Dans un worktree propre de la baseline, le wrapper local retire les indicateurs
synthétiques de son processus, remplace `urllib.request.urlopen` par une fonction
levant `URLError('AUDIT260_OFFLINE_GUARD')`, puis lance seulement :

```text
tests/test_mexc_ws_recv_timeout.py::test_reconcile_does_not_restart_alive_task
tests/test_mexc_ws_recv_timeout.py::test_reconcile_repeated_no_duplicate
```

Résultat : **2 failed en 0,19 s**, `market_catalog_unavailable:URLError`,
`KeyError: BTCUSDT`. Les tests mockent `_run_symbol`, mais pas le catalogue que
`Observatory._validate_watchlist` consulte via `fetch_supported_symbols`.
Ces échecs caractérisent l’isolation des tests ; ils ne prouvent aucune panne de
la machine. Aucun paramètre global CI/runtime n’a été modifié.

### A-02 : population synthétique

La reproduction historique de #260 est exécutée contre la baseline actuelle,
avec un JSONL temporaire de trois OPEN/CLOSE appariés : PnL +2, -1, None.
Le fichier temporaire est supprimé ; aucun store PPL réel n’est ouvert.

```text
paired_trades : 3
win_count     : 1
loss_count    : 2
win_rate      : 0.3333333333333333
violations    : []
warnings      : []
```

Le chemin `dataset_validator.py:521–535` transforme None en zéro, puis classe
pnl<=0 en perte. Une correction nécessite d’abord un contrat explicite de
population, d’UNKNOWN et d’éligibilité ; aucune métrique du burn-in réel n’est
recalculée par cette preuve.

## Constats statiques et outil historique

A-06 : les appels JSON suivants n’ont pas de mot-clé `allow_nan` :
`admission_ledger.py:38`, `engine.py:269`, `recorder.py:620`,
`dataset_validator.py:636`, `market_data/replay_engine.py:299`,
`core/decision_packet.py:283`. Une validation amont de finitude peut borner le
risque ; elle reste à examiner. Il ne faut pas modifier un format/hash historique
par un remplacement global. Les chemins canoniques de paper_exporter, replay,
diagnostics, finalisation et registre candidat possèdent déjà `allow_nan=False`.

A-07 : les arêtes se trouvent à `core/lifecycle.py:32` et
`core/decision_packet.py:502–503`. L’import tardif peut éviter un problème au
chargement ; ce constat n’est pas une preuve de panne runtime.

L’outil `research_boundary_auditor.py` de #260 est **INTEGRATE CANDIDATE**, pas
admis tel quel : [#355](https://github.com/3a7i3/crypto-ia-terminal/issues/355).
Il ne résout pas les aliases, ne vérifie pas la valeur d’allow_nan, détecte
seulement les cycles bilatéraux et retourne 0 même avec des findings.
`.get(..., 0)` est un signal de triage, pas automatiquement une violation.
Aucune copie de l’outil n’est ajoutée dans cette mission.

A-11 : le commentaire de `system_intel_reporter.py:46` mentionne encore V3,
alors que le code importe `CLEAN_DATA_SINCE_ACTIVE`. C’est une dette de commentaire,
pas une preuve de calcul avec V3. Les anciens counts globaux de Markdown,
de définitions et d’environnement ne sont pas recopiés comme mesures actuelles.
Les inventaires existants restent le point d’entrée pour la consolidation ;
les README concurrents ne sont pas supprimés par ce triage.

## Archives, admissions et suite

Le rapport historique et les cinq fichiers restent consultables au
[HEAD immuable de #260](https://github.com/3a7i3/crypto-ia-terminal/tree/70d41b32119ff0a58c22051c4d698befa7bb4b12).
Aucune ancienne métrique ni autorisation n’est importée comme état actuel.
Les [preuves structurées](evidence/AUDIT_ENRICH_RECON_01_2026-10-03.json)
portent la portée et les limites de cette revalidation.

Ordre proposé : #350 (tests hermétiques), #351 (contrat UNKNOWN), puis les
contrats #352/#353/#354 et la qualification optionnelle #355 selon #285.
Créer ces missions ne les exécute pas et n’autorise aucun patch métier sensible.
Leur clôture exigera leurs propres preuves ; le triage n’est pas une remédiation.
