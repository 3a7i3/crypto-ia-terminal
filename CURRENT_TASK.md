# Reprise canonique — DOC-CANON-03

Mission documentaire : [#412](https://github.com/3a7i3/crypto-ia-terminal/issues/412).
Roadmap : [#285](https://github.com/3a7i3/crypto-ia-terminal/issues/285).
Recherche : [#404](https://github.com/3a7i3/crypto-ia-terminal/issues/404),
[#408 D1-D](https://github.com/3a7i3/crypto-ia-terminal/issues/408),
[#410 D1-E](https://github.com/3a7i3/crypto-ia-terminal/issues/410).
Burn-in : [#282](https://github.com/3a7i3/crypto-ia-terminal/issues/282).
Garde-fou : [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286).
Cockpit : [#323](https://github.com/3a7i3/crypto-ia-terminal/issues/323).

Baseline vérifiée le 2026-10-12 :
`main@598ab14b7fff06fdae5d3f2a24bc8d4484f48e71`.
Cette synchronisation remplace le pointeur DOC-CANON-02 / #380 ; son historique
reste consultable à `a057d4e972cd60ee32710d59f327b4185f3af287`.

## État canonique

- L0, L1 canonique v2, L2 et L3 : `CERTIFIED`.
- `FORMAL_CERTIFIED_FRONTIER = L3` ; `EVIDENCE_DEMONSTRATED_FRONTIER = L3`.
- `DEVELOPMENT_FRONTIER = L4` ; prochaine cible formelle : L4, **non certifiée**.
- [Certificat L3](docs/governance/machine_maturity/LEVEL_3_MACHINE_LEVEL_CERTIFICATION_v1.json) :
  `92b9ee468d1d23256241d2068656ab401f614cb33a524327e620c246dd680f03`.
  Hash canonique et chaîne L0 → L1 v2 → L2 → L3 revérifiés ; ne pas refaire L2/L3.
- U7 : [APP_UNIFY_01_SOURCE_CERTIFIED](docs/certification/APP_UNIFY_01_SOURCE_CERTIFICATION.md),
  périmètre historique #383 ; les deltas ultérieurs ne sont pas recertifiés implicitement.
- U8 runtime : **non certifié** ; aucune autorisation de déploiement par ce pointeur.
- #282 : burn-in **non finalisé** ; #286 : garde d'immuabilité **ACTIVE**.
- #315 Gate O : `OPEN / NON_RESOLVED`, OperatorDecision `NON_DEPLOYED`.
- #374 Agent Registry : `PARKED_SOURCE_ONLY / DRAFT / NON_DEPLOYED`.

## Reprise Research et ordre de travail

1. Consulter l'[inventaire des copies autorisées](docs/research/paper_stress_404/D1_D_E_AUTHORIZED_COPY_INVENTORY_20261012.md).
   Passerelle VPS observée Offline le 2026-10-12 : aucun byte Research relu ici.
2. Quand l'accès gouverné est disponible, vérifier uniquement les copies déjà
   autorisées : custody, manifest, hashes, boundary, roster indépendant et reçus
   natifs par tentative jusqu'au fsync. Une nouvelle copie/export a sa gate distincte.
3. D1-D #409 et D1-E #411 sont intégrées en source. Le roster réel, la complétude,
   la provenance native et les reçus fsync restent `NOT_PROVEN / NOT_OBSERVED`.
   Ne pas reconstruire le roster depuis les packets ni instrumenter l'epoch active.
4. Poursuivre #282 sous mission READ-ONLY distincte, puis établir population finale,
   frontière terminale/quiescente, dataset final et réconciliation financière.
5. Préparer L4/U8 sous leurs gates séparées ; aucun déploiement implicite.
   La future campagne #401 reste `DESIGN_ONLY`, `PAPER_STRESS_RUNTIME_GO=DENIED`.
6. Agent Economy demeure différée sous #284 ; aucun feedback Research vers la même epoch.

Ce fichier est un pointeur de reprise, pas une autorité runtime.
**SOURCE STATE ≠ DEPLOYED RUNTIME STATE.**
Aucune observation VPS fraîche, aucune modification des certificats, aucun
restart/deploy, mutation PAPER/PPL/FIN/epoch/config/stratégie/risk/sizing,
Watchdog/TESTNET/LIVE ou écriture exchange n'est autorisé par cette synchronisation.

Lire [docs/DEVELOPER_ENTRYPOINT.md](docs/DEVELOPER_ENTRYPOINT.md),
[CLAUDE.md](CLAUDE.md) et la mission GitHub applicable.
