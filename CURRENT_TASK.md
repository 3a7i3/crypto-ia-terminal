# CURRENT_TASK

> Dernière mise à jour : 2026-09-26
> Cette page est un **pointeur**, pas une source de vérité.

## Autorité de la feuille de route

**[#148 — MASTER ROADMAP](https://github.com/3a7i3/crypto-ia-terminal/issues/148)**
est la seule autorité de priorisation courante.

Ce fichier ne duplique pas #148 : en cas de divergence, **#148 gagne**.

## Mission active

**[#240 — RL-CANDIDATE-01](https://github.com/3a7i3/crypto-ia-terminal/issues/240)**
— Candidate Registry & Promotion Boundary.

| Élément | Valeur |
|---|---|
| PR canonique | [#264](https://github.com/3a7i3/crypto-ia-terminal/pull/264) — DRAFT |
| Miroir CI | [#265](https://github.com/3a7i3/crypto-ia-terminal/pull/265) — **DO NOT MERGE** |
| État | `RC1 PASS / RC1A PASS / RC2 SOURCE IMPLEMENTED / CI PENDING` |
| Gate courante | `RC2_EXACT_HEAD_TEST_AND_REPOSITORY_CI` |
| Création de candidat | `CANDIDATE_CREATION_AUTHORIZED = NO` |

## Chaîne Research canonique

```
F00 certifié
  └─ Research Infrastructure (#237 RL-ARCH-00)
       ├─ #238  RL-DATA-01      ✅ SOURCE CERTIFIED
       ├─ #239  RL-REPLAY-01    ✅ SOURCE CERTIFIED / CLOSED
       ├─ #248  RL-DIAG-01      ✅ SOURCE CERTIFIED / CLOSED
       ├─ #240  RL-CANDIDATE-01 🟡 ACTIVE
       ├─ #241  WEB-RL-01       ⏳
       └─ #242  RL-BURNIN-01    ⏳
```

Séquence aval non négociable : `#240 → #241 → #242`.

## Non-autorisations permanentes de la phase courante

⛔ merge de #264 / #265 vers `main`
⛔ création d'un candidat substantiel avant certification RC2
⛔ mutation runtime stratégie / signal / risk / sizing
⛔ burn-in, nouvelle époque PAPER, activation Watchdog
⛔ TESTNET, LIVE, écritures exchange

## Historique

Le contenu précédent de cette page (P10 Evolutionary Architecture, branche
`feat/stack-unification`) décrivait un focus de mai 2026 sans rapport avec la
chaîne Research courante. Il est retiré comme **STALE** — voir `ROADMAP.md`
pour l'historique des phases P1-P13.
