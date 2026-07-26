# CHECKPOINTS — Les cinq paliers du chantier

> Où en est le chantier, et ce qu'il faut pour passer au palier suivant.
> **Fichier vivant** : mis à jour quand un palier est franchi.
>
> Ne pas confondre avec les niveaux **PMI L1–L7** du projet (`docs/blueprint_v2.md`), qui mesurent la
> maturité du **système de trading**. Les checkpoints ci-dessous mesurent l'avancement du **chantier
> de remédiation SSoT**. Le seul point de contact est **L3**, qui dépend du checkpoint L2 du projet.

**Palier actuel : `L0`** — infrastructure documentaire en place, aucun ticket exécuté.

---

## Vue d'ensemble

```
  L0 ──► L1 ──► L2 ──►  ╔═══════════╗ ──► L3 ──► L4
 socle  gouv.  obs.     ║  PORTE    ║   decision  SSoT
                        ║  D'EPOQUE ║   prise     restaure
                        ╚═══════════╝
                       (irreversible)
```

| Palier | Nom | Réversible ? | Tickets requis |
|---|---|---|---|
| **L0** | Socle documentaire | — | aucun |
| **L1** | Gouvernance établie | Oui | `GOV-001` → `GOV-005` |
| **L2** | Observabilité honnête | Oui | `OBS-001` → `OBS-004`, `REST-001` → `REST-004` |
| **L3** | Décision d'époque prise | **NON** | `PORT-001` + décision **D-1** |
| **L4** | SSoT restauré | **NON** | `SSOT-001` → `014`, `PORT-002` → `006` |

### Avancement mesuré

> Bloc **généré** depuis `.claude/manifest.yaml` — `python .claude/tools/render_docs.py`.

<!-- GENERATED:statuts -->
| Palier | Nom | Atteint | Tickets requis termines |
|---|---|---|---|
| **L0** | Socle documentaire | OUI | 0/0 |
| **L1** | Gouvernance etablie | non | 0/5 |
| **L2** | Observabilite honnete | non | 0/8 |
| **L3** | Decision d'epoque prise | non | 0/1 |
| **L4** | SSoT restaure | non | 0/18 |
<!-- /GENERATED:statuts -->

---

## L0 — Socle documentaire

**Conditions d'entrée** : aucune. État initial.

**Conditions de sortie** :
- [x] Diagnostic validé et écrit (`ARCHITECTURE.md`)
- [x] Règles écrites (`GOVERNANCE.md`, `CLAUDE_IMPLEMENTATION.md`)
- [x] Roadmap et backlog écrits (`MASTER_ROADMAP.md`, `IMPLEMENTATION_QUEUE.md`, `INDEX.md`)
- [x] Prompts d'exécution des tickets non gated rédigés (15/15)
- [ ] Un ticket exécuté

**Métriques** : 5 phases · 34 tickets · 15 PRET · 19 BLOQUE · 0 TERMINE.

**Validation** : une session sans contexte peut identifier le premier ticket et l'exécuter en suivant
`SESSION_BOOTSTRAP.md`.

**Autorité** : aucune requise (documentation seule).

**Statut : ATTEINT** (2026-07-24).

---

## L1 — Gouvernance établie

**Conditions d'entrée** : L0 atteint.

**Conditions de sortie** :
- [ ] `GOV-002` — registre des invariants opposable, chacun avec son test de violation
- [ ] `GOV-004` — gabarit de rapport de fin de ticket
- [ ] `GOV-003` — journal `DEC-xxx` créé, décisions D-1 à D-5 inscrites
- [ ] `GOV-001` — ADR-0019 rédigé (proposé ; son acceptation est la décision **D-3**)
- [ ] `GOV-005` — checklist de déploiement et de vérification

**Métriques** : 5 tickets TERMINE · 0 fichier `.py` modifié · tests identiques à la baseline.

**Validation** : chaque invariant possède un test de violation **exécutable** ; la checklist de
déploiement aurait détecté l'incident du 2026-07-09 (tags d'audit mensongers).

**Autorité** : session Claude (documentaire). **Décision D-3** (accepter ADR-0019) : opérateur.

**Impact scientifique** : nul. Aucun code touché, N inchangé.

---

## L2 — Observabilité honnête

**Conditions d'entrée** : L1 atteint (au moins `GOV-004`, requis par `OBS-001`).

**Conditions de sortie** :
- [ ] `OBS-001` — bug figé par un test rouge ; garde INV-2 verte
- [ ] `OBS-002` — builder CYCLE dérivé de `_virtual_portfolio`
- [ ] `OBS-003` — builder HEARTBEAT en parité
- [ ] `OBS-004` — risque R1 documenté dans le code
- [ ] `REST-002` — recopie `total_pnl_usd` supprimée
- [ ] `REST-001` — source unique arbitrée par ADR
- [ ] `REST-003` — 8 littéraux figés remplacés
- [ ] `REST-004` — trois gardes anti-régression en place
- [ ] *(optionnel `OBS-005` — selon décision D-4)*

**Métriques cibles** :

| Métrique | Avant | Après L2 |
|---|---|---|
| Exposition affichée avec 3 positions | `0.0 %` | **> 0**, cohérente avec Σ tailles |
| `paper_cash` vs `free_cash` | contradictoires | cohérents |
| `win_rate` publié par le REST | `0 %` (figé) | valeur réelle ou `null` |
| `total_pnl_usd` | recopie du PnL ouvert | valeur réelle ou `null` |
| Tests de garde REST | 0 | 3 |
| Verdict de `check_new_trade` | — | **strictement inchangé** |

**Validation** :
1. Sur un cycle réel avec positions ouvertes, exposition affichée = exposition calculée sur les
   positions réelles.
2. Panneau et `[ALIVE]` donnent les mêmes valeurs (parité `OBS-003`).
3. La garde INV-2 est verte : le comportement de décision n'a pas changé.
4. `git diff` sur `portfolio_brain.py:88-109` (seuils) : **vide**.

**Autorité** : session Claude. Aucun ADR requis.

**Impact scientifique** : **nul**. Le panneau dit la vérité, le moteur décide exactement comme avant.
**N inchangé, burn-in préservé.**

> ⚠ **Ce que L2 ne résout pas** : le gate de décision reste aveugle. C'est le risque R1, documenté par
> `OBS-004`. Atteindre L2 ne doit **pas** être lu comme « le problème est réglé ».

---

## PORTE D'EPOQUE — franchissement irréversible

**Ce n'est pas un palier, c'est un seuil.** Ce qui est franchi ne se refranchit pas.

**Quatre préconditions cumulatives :**

| # | Précondition | Vérifiable par |
|---|---|---|
| 1 | Checkpoint **L2 du projet** franchi (`docs/blueprint_v2.md`) | Score PMI L2 |
| 2 | **N ≥ 100** sur l'époque V4 (`CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z`) | `tools/cri_calculator.py` |
| 3 | Rapport **`PORT-001`** produit **et lu** par l'opérateur | Fichier au dépôt |
| 4 | **ADR d'époque** rédigé et **signé** par l'opérateur | Fichier sous `docs/adr/` |

**Ce que coûte le franchissement** :
- **N → 0.** L'époque V4 est close. Ses données restent archivées mais ne comptent plus pour les
  seuils de la règle du statisticien (500 trades / 150 W / 150 L / 100 MW / 100 GR / CRI ≥ 90).
- Le rollback de code existe ; **le rollback d'époque n'existe pas.**

**Autorité : opérateur seul.** Aucune session Claude ne peut franchir cette porte, ni y déroger.

> Précédent à ne pas rejouer : ADR-0017 a acté une dérogation explicite à ses propres déclencheurs
> T1/T2. Ici, une dérogation détruirait la mesure **sans compensation**, puisque rien ne peut la
> restaurer. **Aucune dérogation n'est admise.**

---

## L3 — Décision d'époque prise

**Conditions d'entrée** : L2 atteint · `PORT-001` terminé · les quatre préconditions réunies.

**Conditions de sortie** :
- [ ] Rapport `PORT-001` produit, avec ses 5 métriques chiffrées et l'auto-validation du harnais
- [ ] **Décision D-1** tranchée par l'opérateur et inscrite au journal `DEC-xxx`
- [ ] **Décision D-2** tranchée (arbitrage `SSOT-010` / `PORT-004`)
- [ ] ADR d'époque signé, référencé au dépôt

**Métriques** :
- Pourcentage de trades V4 qui auraient été refusés avec l'exposition réelle — **le chiffre qui fonde D-1**
- Répartition des motifs de refus parmi les 5 contrôles
- PnL cumulé des trades qui auraient été refusés
- Exposition maximale réellement atteinte vs plafond 40 %

**Validation** : le harnais de rejeu reproduit à l'identique les verdicts historiques avec
`open_positions = []`. Sans cette auto-validation, le chiffre est invérifiable et la décision serait
non informée.

**Autorité : opérateur seul.**

**Impact scientifique** : **la décision elle-même n'a aucun impact** — `PORT-001` est passif.
L'impact commence à `PORT-002`.

> **L3 peut aboutir à NE PAS franchir la porte.** Si le rapport `PORT-001` montre un impact faible,
> conserver l'époque V4 est une décision légitime et documentée — pas un échec du chantier.

---

## L4 — SSoT restauré

**Conditions d'entrée** : L3 atteint, porte d'époque franchie, ADR signé.

**Conditions de sortie** :
- [ ] `SSOT-001` → `SSOT-014` terminés
- [ ] `PORT-002` → `PORT-006` terminés (sauf celui écarté par D-2)
- [ ] Borne `CLEAN_DATA_SINCE_V5` posée, époque V4 archivée avec son N final
- [ ] Déploiement vérifié : SHA VPS = SHA local, service actif, tag `deploy-YYYYMMDD-HHMM`

**Métriques cibles** :

| Métrique | Avant | Après L4 |
|---|---|---|
| Audit SSoT | 0 PASS / 1 WARNING / 8 FAIL | **cible à définir** — au minimum `positions`, `exposure`, `cash` en PASS |
| Stores de positions | 4 | 1 canonique (+ le réel en lecture seule) |
| Classes `PortfolioSnapshot` | 3 | 1 |
| Classes `PortfolioBrain` | 2 | 1 |
| Classes `SystemSnapshot` | 2 | 1 |
| Exposition-gate | aveugle (0 %) | réelle |
| N | ~32 (V4) | **0** (V5) |

**Validation** :
1. Exposition **affichée** = exposition **gate** sur un même cycle.
2. Aucun seuil modifié (`git diff` sur `portfolio_brain.py:88-109` vide).
3. Écart de verdicts avant/après **journalisé et chiffré** (INV-P2).
4. CRI recalculé sur la nouvelle époque : `N(V5) = 0` attendu.
5. Les 9 contrôles V1 → V9 de `PHASE_04_GATED.md` § Validation passent.

**Autorité** : opérateur pour la bascule et le déploiement ; session Claude pour l'implémentation.

**Impact scientifique** : **maximal et irréversible.** Nouvelle époque, burn-in redémarré à zéro,
gate de décision corrigé.

---

## Ce qu'aucun palier ne résout

Énoncé pour qu'aucune session future ne confonde les deux questions :

> Ces cinq paliers mesurent la **réparation de l'instrument**.
> Ils ne disent **rien** sur la question de fond : *le système a-t-il un edge ?*
>
> Atteindre L4 signifie que le système **mesure correctement**. Pas qu'il **gagne**.
> Cette seconde question relève des hypothèses H1–H6 et des verrous Go/No-Go EXP-001,
> hors périmètre de ce chantier.

---

## Mise à jour de ce fichier

Quand un palier est franchi : cocher ses conditions de sortie, renseigner les métriques **mesurées**
(pas estimées), mettre à jour la ligne « Palier actuel » en tête, et inscrire le franchissement au
journal `DEC-xxx`.

**Ce qui rend ce fichier périmé** : un ticket terminé sans que la case correspondante soit cochée.
