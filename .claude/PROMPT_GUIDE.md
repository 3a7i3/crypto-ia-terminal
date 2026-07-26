# PROMPT_GUIDE — Utilisation des prompts d'exécution

> Comment utiliser les fichiers de `.claude/prompts/`. À lire une fois, puis en cas de doute.
> Version 1.0 — 2026-07-24.

---

## 1. À quoi sert ce système

Chaque ticket du chantier possède **un prompt d'exécution autonome**. « Autonome » signifie :
une session Claude qui n'a **jamais vu** la conversation d'origine, ni l'audit, ni le diagnostic,
peut ouvrir ce seul fichier et exécuter le ticket **sans poser de question**.

C'est une propriété délibérée. Elle permet :
- de reprendre le chantier des mois plus tard sans reconstituer le contexte ;
- d'obtenir un comportement identique d'une session à l'autre ;
- de ne jamais dépendre de la mémoire d'une conversation, qui n'est pas un artefact versionné.

Chaque prompt contient les 13 sections : `MISSION`, `CONTEXTE`, `OBJECTIF`, `CONTRAINTES`,
`INVARIANTS`, `FICHIERS`, `ETAPES`, `CHECKLIST`, `TESTS`, `VALIDATION`, `LIVRABLES`,
`STOP CONDITIONS`, `INTERDICTIONS`.

---

## 2. Comment invoquer un prompt

Dans une nouvelle session, écrire **exactement** :

```
Respecte .claude/CLAUDE_IMPLEMENTATION.md et exécute le ticket OBS-001.
```

Ou, pour laisser la session choisir le prochain ticket disponible :

```
Respecte .claude/CLAUDE_IMPLEMENTATION.md, prends le premier ticket PRET
de .claude/IMPLEMENTATION_QUEUE.md et exécute-le. Arrête-toi après.
```

---

## 3. Séquence d'une session type

1. Lire `.claude/CLAUDE_IMPLEMENTATION.md` (protocole).
2. Ouvrir `.claude/IMPLEMENTATION_QUEUE.md`, prendre le **premier ticket de la file PRET**.
3. Vérifier que ses **dépendances** sont en file TERMINE. Sinon, prendre le suivant.
4. Ouvrir `.claude/prompts/PROMPT_<ID>.md`.
5. Relever la **baseline de tests** : `python -m pytest tests/ -q`.
6. Exécuter les `ETAPES` du prompt, dans l'ordre exact.
7. Parcourir la `CHECKLIST` — chaque case doit être cochée.
8. Lancer les `TESTS`. Corriger **uniquement** les erreurs causées par le ticket.
9. Vérifier les critères de `VALIDATION`.
10. Commiter avec le message donné dans `LIVRABLES` (un commit atomique).
11. Mettre à jour `IMPLEMENTATION_QUEUE.md` : déplacer le ticket vers **TERMINE**, dater, noter le SHA.
12. **S'ARRÊTER.** Ne jamais enchaîner sur le ticket suivant.

---

## 4. Convention de nommage

| Ticket | Fichier de prompt |
|---|---|
| `OBS-001` | `.claude/prompts/PROMPT_OBS_001.md` |
| `REST-002` | `.claude/prompts/PROMPT_REST_002.md` |
| `PORT-001` | `.claude/prompts/PROMPT_PORT_001.md` |

Règle : **le tiret de l'identifiant devient un tiret bas dans le nom de fichier.**

---

## 5. Inventaire des prompts

### File PRET — exécutables sous le gel

| ID | Phase | Statut | Titre |
|---|---|---|---|
| GOV-001 | 00 | PRET | ADR-0019 : séparation exposition d'affichage / exposition-gate |
| GOV-002 | 00 | PRET | Registre des invariants INV-1 → INV-4 rendu opposable |
| GOV-003 | 00 | PRET | Journal des décisions du chantier |
| GOV-004 | 00 | PRET | Gabarit de rapport de fin de ticket |
| GOV-005 | 00 | PRET | Checklist de déploiement VPS et vérification |
| OBS-001 | 01 | PRET | Tests de régression d'abord — rouge + garde verte INV-2 |
| OBS-002 | 01 | PRET | Builder CYCLE depuis `_virtual_portfolio` |
| OBS-003 | 01 | PRET | Builder HEARTBEAT — parité stricte |
| OBS-004 | 01 | PRET | Documentation code — affichage ≠ gate (risque R1) |
| OBS-005 | 01 | PRET | Cohérence `integrity_snapshot.py` (optionnel) |
| REST-001 | 03 | PRET | ADR de source unique pour les métriques REST |
| REST-002 | 03 | PRET | Supprimer la recopie `total_pnl_usd = open_pnl_usd` |
| REST-003 | 03 | PRET | Remplacer les 8 littéraux figés |
| REST-004 | 03 | PRET | Tests de garde REST |
| PORT-001 | 04 | PRET | Mesure d'impact hors ligne (passif) |

### File BLOQUE — prompts à générer au déblocage

| ID | Phase | Statut |
|---|---|---|
| SSOT-001 → SSOT-014 | 02 | **BLOQUE** — GATED |
| PORT-002 → PORT-006 | 04 | **BLOQUE** — GATED |

> Les prompts des tickets GATED ne sont **pas encore rédigés**. C'est délibéré : leur contenu dépend
> de décisions non prises (ADR d'époque, arbitrage `SSOT-010` / `PORT-004`). Les rédiger maintenant
> figerait des choix que l'opérateur n'a pas faits. Le détail de ces tickets figure dans
> `phases/PHASE_02_GATED.md` et `phases/PHASE_04_GATED.md`.

---

## 6. Reconnaître un prompt GATED

Un prompt GATED **commence** par un encart d'arrêt :

```
STOP — CE TICKET DECLENCHE UN RESET D'EPOQUE (N → 0).
NE PAS EXECUTER SANS ADR SIGNE PAR L'OPERATEUR.
```

**Que faire** : s'arrêter immédiatement. Vérifier les **quatre** préconditions
(checkpoint L2 · N ≥ 100 sur V4 · rapport `PORT-001` lu · ADR d'époque signé).
Si l'une manque, **ne pas exécuter** et le signaler à l'opérateur.

Aucune dérogation locale n'est admise. Contrairement à ADR-0017 — où l'opérateur a explicitement dérogé
à T1/T2 — une dérogation ici détruirait la mesure **sans compensation possible** : le rollback de code
existe, le rollback d'époque n'existe pas.

---

## 7. Si un prompt est incomplet ou si le code a changé

Les prompts contiennent des marqueurs **`A CONFIRMER AU DEMARRAGE DU TICKET`**. Ils signalent une
information qui n'a pas pu être vérifiée à la rédaction.

**Conduite à tenir :**
1. Vérifier l'information dans le code, en lecture seule.
2. Si elle est confirmée : poursuivre, et le noter dans le rapport de fin de ticket.
3. Si elle est **infirmée** : **s'arrêter**. Ne pas improviser une adaptation.
   Signaler l'écart à l'opérateur avec l'observation exacte (fichier, ligne, ce qui était attendu,
   ce qui est constaté).

Un numéro de ligne peut avoir bougé (le code évolue). Un numéro de ligne faux n'est pas un blocage ;
une **structure de code différente de celle décrite** en est un.

---

## 8. Erreurs fréquentes à éviter

| Erreur | Pourquoi c'est grave |
|---|---|
| Enchaîner deux tickets dans une session | Casse l'atomicité ; un revert devient impossible à cibler. |
| Corriger un test étranger au ticket | Masque une régression réelle ; pollue le diff. |
| Refactorer « au passage » | Le diff cesse d'être revertable ; viole le protocole. |
| Modifier un seuil pour faire passer un test | Viole INV-4 ; fausse la validation scientifique. |
| Toucher `pos_manager` / `check_new_trade` dans un ticket non gated | **Déclenche un reset d'époque non autorisé. Faute la plus grave.** |
| Déployer sans `--confirm` | Viole la règle du geste délibéré. |
| Déployer sans vérifier SHA local = SHA VPS | Précédent : incident du 2026-07-09, 3 tags d'audit mensongers. |
| Publier `0` au lieu de `null` pour une métrique indisponible | Une valeur fausse est pire qu'une valeur absente. |
| Mettre à jour la queue « plus tard » | L'état d'avancement devient faux ; la session suivante repart de travers. |

---

## 9. Rappel — les 4 invariants

- **INV-1** : passivité absolue des observers (ADR-0007).
- **INV-2** : aucun reset de N sans ADR d'époque signé.
- **INV-3** : `paper_trades.jsonl` écrit uniquement par `mexc_simulator.py` et `recorder.py` ;
  historique jamais réécrit.
- **INV-4** : aucun seuil modifié avant N ≥ 500 et CRI ≥ 90.

Tout prompt qui semble demander de violer l'un de ces invariants doit être considéré comme
**erroné** : s'arrêter et le signaler.
