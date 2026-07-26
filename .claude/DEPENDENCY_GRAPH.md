# DEPENDENCY_GRAPH — Graphe de dépendances des tickets

> Qui dépend de quoi, qui débloque quoi, ce qui peut être parallélisé.
>
> **Ce qui rend ce fichier périmé** : l'ajout, la suppression ou le renumérotage d'un ticket.
> En cas de divergence avec `phases/`, **les documents de phase font foi**.

---

## Graphe global

```
                            ┌─ GOV-002 ─┐
                            ├─ GOV-004 ─┤   (aucune dependance entre eux)
        PHASE_00 ───────────┼─ GOV-003 ─┤
                            ├─ GOV-005 ─┤
                            └─ GOV-001 ─┴──────────┐
                                   │               │
                                   ▼               ▼
        PHASE_01           OBS-001            REST-001
                              │                   │
                              ▼                   ▼
                          OBS-002 ────┐      REST-003 ◄── REST-002 (independant)
                              │       │           │            │
                    ┌─────────┼───────┤           └──────┬─────┘
                    ▼         ▼       ▼                  ▼
                OBS-003   OBS-004  OBS-005            REST-004


        PORT-001  (PASSIF — aucune dependance, executable des maintenant)
             │
             │  produit le chiffre qui fonde la decision D-1
             ▼
   ╔═══════════════════════════════════════════════════════════════╗
   ║  PORTE D'EPOQUE   (4 preconditions cumulatives)               ║
   ║   1. checkpoint L2 franchi                                    ║
   ║   2. N >= 100 sur l'epoque V4                                 ║
   ║   3. rapport PORT-001 lu par l'operateur                      ║
   ║   4. ADR d'epoque signe                                       ║
   ╚═══════════════════════════════════════════════════════════════╝
             │
             ▼
   SSOT-001 ─┬─► SSOT-002 ─┐
             └─► SSOT-003 ─┴─► SSOT-004 ─► SSOT-005 ─► SSOT-006 ─► SSOT-007
                                                                       │
                                                                       ▼
                                                                   SSOT-008
                                    ┌──────────┬──────────┬──────────┬────┴─────┐
                                    ▼          ▼          ▼          ▼          ▼
                                SSOT-009   SSOT-010⚠  SSOT-011   SSOT-012      │
                                                                     │          │
                                                            ┌────────┴────┐     │
                                                            ▼             ▼     │
                                                        SSOT-013     SSOT-014   │
                                                                                │
                                    SSOT-007 + PORT-001 ────────────────────────┘
                                                │
                                                ▼
                                            PORT-002   ← POINT DE NON-RETOUR
                              ┌──────────┬──────┴───┬──────────┐
                              ▼          ▼          ▼          ▼
                          PORT-003   PORT-004⚠  PORT-005   PORT-006 (borne V5)
```

⚠ **`SSOT-010` / `PORT-004`** — même objet (arbitrage des deux `PortfolioBrain`).
Décision **D-2** requise : n'en exécuter qu'un.

---

## Table : dépendances → débloque → impacts

| Ticket | Dépend de | Débloque | Impacts si terminé |
|---|---|---|---|
| GOV-002 | — | Tous (référence d'invariants) | Les invariants deviennent opposables |
| GOV-004 | — | OBS-001 | Format de rapport uniforme |
| GOV-003 | — | — | Décisions traçables |
| GOV-001 | — | REST-001 | ADR-0019 proposé (acceptation = D-3) |
| GOV-005 | — | Tout déploiement futur | Déploiement vérifiable |
| OBS-001 | GOV-004 | OBS-002 | Le bug est figé par un test |
| **OBS-002** | OBS-001 | OBS-003, OBS-004, OBS-005 | **Le panneau dit la vérité** |
| OBS-003 | OBS-002 | — | Cohérence rapport / `[ALIVE]` |
| OBS-004 | OBS-002 | — | Le risque R1 devient visible dans le code |
| OBS-005 | OBS-002 | — | 3ᵉ lignée alignée ou documentée |
| REST-001 | GOV-001 | REST-003 | Source unique arbitrée |
| REST-002 | — | REST-004 | Fin d'une valeur activement fausse |
| REST-003 | REST-001 | REST-004 | Fin des 8 littéraux figés |
| REST-004 | REST-002, REST-003 | — | Régression rendue détectable |
| **PORT-001** | — | **Décision D-1** | **Le reset d'époque devient une décision informée** |
| SSOT-001 | PORTE | SSOT-002, SSOT-003 | Contrat de store défini |
| SSOT-004 | SSOT-002, SSOT-003 | SSOT-005 | Flag disponible, non câblé |
| SSOT-005 | SSOT-004 | SSOT-006 | Écarts mesurables avant bascule |
| SSOT-006 | SSOT-005 | SSOT-007 | Affichage sur store canonique |
| **SSOT-007** | SSOT-006 | SSOT-008, PORT-002 | **La décision lit le store résolu** |
| SSOT-008 | SSOT-007 | SSOT-009→014 | Snapshot unique |
| SSOT-012 | SSOT-008 | SSOT-013, SSOT-014 | Métriques de capital canoniques |
| **PORT-002** | SSOT-007, PORT-001, PORTE | PORT-003→006 | **Point de non-retour scientifique** |
| PORT-006 | PORT-002 | — | Borne V5 posée, N recompté |

---

## Branches parallélisables

Ces ensembles n'ont **aucune dépendance croisée** — ils peuvent avancer en parallèle (sessions ou
personnes différentes), à condition de rester **un ticket par commit**.

| # | Branche | Tickets | Condition |
|---|---|---|---|
| **B1** | Gouvernance | `GOV-001` · `GOV-002` · `GOV-003` · `GOV-005` | Aucune. 4 tickets indépendants entre eux. |
| **B2** | Chaîne observabilité | `OBS-001` → `OBS-002` → {`OBS-003`, `OBS-004`, `OBS-005`} | Séquentielle jusqu'à `OBS-002`, puis 3 branches parallèles. |
| **B3** | REST | `REST-002` en parallèle de `REST-001` → `REST-003` | Convergent sur `REST-004`. |
| **B4** | Mesure d'impact | `PORT-001` | Totalement isolé. Peut tourner pendant tout le reste. |

**Parallélisme maximal utile : 4 branches.** Au-delà, les tickets partagent `core/advisor_loop.py`
(7 776 lignes) et les conflits de merge deviennent le facteur limitant.

**Recommandation** : `PORT-001` (B4) en premier ou en parallèle — c'est le chemin le plus long
(1–2 j) et il conditionne une décision qui, elle, prend du temps à mûrir.

---

## Chemin critique

```
GOV-004 → OBS-001 → OBS-002 → [PHASE_01 close]
                                    │
PORT-001 ───────────────────────────┤
                                    ▼
                          [ PORTE D'EPOQUE ]        ◄── attente : N de ~32 à >= 100
                                    │                    (non datable)
                                    ▼
              SSOT-001 → ... → SSOT-007 → PORT-002 → PORT-006
```

Le chemin critique **n'est pas** un chemin de travail : son maillon le plus long est **l'attente de N**,
qui ne dépend d'aucun ticket. Tout le travail non gated (15 tickets, ~5–9 jours) tient largement dans
cette fenêtre d'attente.

**Conséquence de planification** : il n'y a aucun gain à précipiter les phases 00/01/03. Il y a en
revanche un gain réel à exécuter `PORT-001` tôt, pour que la décision D-1 soit prête le jour où N
atteint 100.

---

## Règle de propagation d'un échec

Si un ticket échoue ou est rejeté :

1. **Tous ses descendants directs deviennent non démarrables** — pas « à risque », **non démarrables**.
2. Les branches parallèles (`B1`, `B3`, `B4`) ne sont **pas** affectées si elles ne partagent aucun ancêtre.
3. Cas particulier : un échec de `OBS-002` bloque `OBS-003`, `OBS-004` et `OBS-005` simultanément
   (trois descendants d'un même nœud).
4. Cas particulier : un échec de `PORT-001` ne bloque aucun ticket **technique**, mais bloque la
   **décision D-1**, donc toute la moitié gated du chantier.

Voir `EXECUTION_FLOW.md` pour la conduite à tenir en cas d'échec.
