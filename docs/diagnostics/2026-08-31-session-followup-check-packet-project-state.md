# Suivi d'investigation — 31/08/2026 — check() / check_packet() — État du projet

**Date d'investigation :** 30–31 août 2026  
**Rédigé par :** Investigation Claude Code (analyse statique repository + données VPS read-only)  
**Statut global :** Partiellement clos — dette architecturale identifiée, aucun impact opérationnel mesuré, décision architecturale en attente

---

## 1. Métadonnées

| Paramètre | Valeur |
|---|---|
| Projet | `crypto-ai-terminal` |
| Repository | `3a7i3/crypto-ia-terminal` |
| VPS | `crypto-advisor-2` |
| Répertoire VPS | `/home/mathieu/crypto_ai_terminal` |
| Utilisateur VPS actuel | `ia_strategy_support` |
| Période d'investigation | 24–31 août 2026 (validation 8 jours) |
| Nature | Analyse statique du code + validation read-only des fichiers JSONL de production |
| Statut global | Partiellement clos — dette architecturale en attente de décision |

---

## 2. Point de départ

### Document précédent

L'investigation qui a précédé cette session est archivée dans :

```
docs/diagnostics/2026-08-30-meta-signal-network-diagnostic.md
```

Ce document (commit `9fb6525` — **⚠️ non vérifiable dans le clone courant**, voir §9) couvrait :

- la chaîne Signal Generator → Meta → Gate → décision finale ;
- le comportement de `gate.check()` vs `gate.check_packet()` ;
- la cohérence du détecteur de régime entre `LiveSignalEngine` et `advisor_loop.py` ;
- le rôle et l'état du module HMM V2 ;
- l'analyse des rejets de production du 30/08/2026.

### Dossier laissé ouvert

Ce diagnostic avait laissé explicitement ouvert le dossier `check()/check_packet()` :
la divergence entre les deux méthodes avait été identifiée au niveau du code, mais
l'impact décisionnel réel en production n'avait pas encore été quantifié sur un
échantillon représentatif multi-jours.

**L'investigation de la présente session a pour objet de fermer ou qualifier ce dossier.**

---

## 3. Méthodologie

### Sources utilisées

1. **Analyse statique du code** — lecture des fichiers sources dans le repository :
   - `quant_hedge_ai/agents/risk/global_risk_gate.py` (implémentation de `check()` et `check_packet()`)
   - `core/advisor_loop.py` (point d'appel et non-capture du retour de `check_packet()`)
   - `observability/decision_observation.py`, `observability/rejection_store.py`
   - `observability/system_snapshot.py` (chemin vers `block_stats_lifetime.json`)

2. **Analyse read-only du VPS** — toutes les données VPS ont été fournies par
   copier-coller depuis le terminal VPS. Aucune commande d'écriture n'a été exécutée.

3. **Fichiers JSONL** analysés sur le VPS :
   - `databases/rejections/rejections_2026-08-30.jsonl`
   - `databases/decision_packets_YYYY-MM-DD.jsonl` (plusieurs jours)

4. **Jointure par `packet_id`** — les rejections JSONL et les DecisionPackets ont
   été croisés par le champ `packet_id` pour déterminer l'état `check_packet()` de
   chaque rejet documenté dans le fichier de rejections.

5. **Validation multi-jours** — la vérification a été reproduite sur 8 jours consécutifs
   (du 24 au 31/08/2026) pour s'assurer que l'échantillon du 30/08 n'était pas une anomalie.

### Distinction preuve code vs preuve production

- Les faits qualifiés **[CODE]** sont prouvés par lecture du repository et sont
  reproductibles par quiconque lit les fichiers sources.
- Les faits qualifiés **[VPS]** proviennent des données de production du VPS.
  Ils ne peuvent pas être reproduits par lecture seule du repository.

---

## 4. Fausses pistes et méthodes invalides

> **Cette section est importante.** Elle documente les erreurs méthodologiques
> commises pendant l'investigation afin d'empêcher qu'une future investigation
> reproduise les mêmes erreurs.

### 4.1 Comparaison `score` / `score_raw` dans les rejections

**Erreur :** Tenter de quantifier la divergence `check()` vs `check_packet()` en
comparant le champ `score` et le champ `score_raw` des enregistrements de rejection.

**Pourquoi invalide :**
- `check()` compare `signal_result.score` (score du `SignalResult`).
- `check_packet()` compare `packet.adjusted_confidence` (champ du `DecisionPacket`).
- Ces deux valeurs ne sont **pas** directement accessibles ensemble dans le fichier
  `rejections_YYYY-MM-DD.jsonl` ; les champs `score` et `score_raw` de ce fichier
  ne représentent pas la même chose que `adjusted_confidence`.

### 4.2 Absence de `adjusted_confidence` dans les rejections

**Erreur :** Chercher le champ `adjusted_confidence` directement dans les fichiers
de rejections.

**Pourquoi invalide :** `adjusted_confidence` est un champ du `DecisionPacket`,
pas du `RejectionRecord`. Pour accéder à ce champ, il faut consulter les fichiers
`databases/decision_packets_YYYY-MM-DD.jsonl` et effectuer une jointure par `packet_id`.

### 4.3 Échantillon non représentatif

**Erreur :** Tirer des conclusions définitives à partir d'une seule journée
(30/08/2026 uniquement).

**Correction appliquée :** La validation a été reproduite sur 8 jours (24–31/08)
pour confirmer la robustesse des conclusions.

### 4.4 Résumé de la méthode valide

La seule méthode correcte pour qualifier la divergence `check()` / `check_packet()`
en production est :

```
1. Charger rejections_YYYY-MM-DD.jsonl
2. Charger decision_packets_YYYY-MM-DD.jsonl
3. Joindre les deux datasets par packet_id
4. Comparer gate_failed (issu de check()) avec risk_failed (issu de check_packet())
5. Identifier les cas où gate_failed=False ET risk_failed=True (check() laisse passer, check_packet() aurait bloqué)
6. Analyser first_blocker pour ces cas divergents
```

---

## 5. Résultats CODE PROUVÉS

> Tous les éléments ci-dessous sont vérifiables dans le repository.

### 5.1 `check()` compare `signal_result.score`

**Fichier :** `quant_hedge_ai/agents/risk/global_risk_gate.py`, ligne ~269

```python
score = getattr(signal_result, "score", 0)
regime_str = getattr(signal_result, "regime", "unknown")
effective_min = self._effective_min_score(regime_str)
c3 = score >= effective_min
```

L'entrée est un `SignalResult` du `LiveSignalEngine`. Le score comparé est
`signal_result.score`. **[CODE]**

### 5.2 `check_packet()` compare `packet.adjusted_confidence`

**Fichier :** `quant_hedge_ai/agents/risk/global_risk_gate.py`, ligne ~406

```python
score = float(getattr(packet, "adjusted_confidence", packet.confidence))
effective_min = self._effective_min_score(regime_str)
c3 = score >= effective_min
```

L'entrée est un `DecisionPacket`. Le score comparé est `packet.adjusted_confidence`
(avec fallback sur `packet.confidence`). **[CODE]**

### 5.3 Même méthode `_effective_min_score(regime)`

Les deux méthodes utilisent la même fonction `_effective_min_score(regime_str)`
(lignes ~271 et ~408), ce qui signifie que la divergence ne vient pas du seuil
mais de la valeur du score comparé. **[CODE]**

### 5.4 Retour de `check_packet()` non capturé dans le pipeline principal

**Fichier :** `core/advisor_loop.py`, lignes 1553–1559

```python
if _dp and not _dp.is_terminal() and hasattr(gate, "check_packet"):
    try:
        gate.check_packet(
            _dp, portfolio_drawdown=0.0, order_size_usd=order_size_usd
        )
    except Exception as _dp_exc:
        log.debug("[DecisionPacket] check_packet: %s", _dp_exc)
```

L'appel à `check_packet()` est fire-and-forget : son résultat n'est pas capturé,
pas affecté à une variable de décision. Le résultat de `gate.check()` (ligne 1550)
est capturé dans `gate_result` et pilote toutes les décisions. **[CODE]**

### 5.5 `results["gate"]` représente uniquement `gate.check()`

**Fichier :** `core/advisor_loop.py`, ligne ~2298

```python
"gate": gate_result,
```

`gate_result` est le résultat de `gate.check()` uniquement.
`results["gate"]` ne contient aucune information issue de `check_packet()`. **[CODE]**

### 5.6 `block_stats_lifetime.json` représente uniquement `check()`

**Fichier :** `observability/system_snapshot.py`, ligne ~292

`block_stats_lifetime.json` est alimenté par le `BlockStatsAccumulator` qui est
mis à jour via le flux `gate_result` (issu de `check()`). Les statistiques de
blocage lifetime reflètent donc exclusivement les verdicts de `check()`. **[CODE]**

### 5.7 `check_packet()` écrit son verdict dans le DecisionPacket

**Fichier :** `quant_hedge_ai/agents/risk/global_risk_gate.py`, ligne ~459

```python
packet.metadata["risk_failed"] = failed
```

`check_packet()` écrit bien son verdict (via `risk_failed`) dans les métadonnées
du `DecisionPacket`. Ce champ est donc tracé dans les fichiers
`databases/decision_packets_YYYY-MM-DD.jsonl`. **[CODE]**

### 5.8 Synchronisation G8-D unidirectionnelle

La synchronisation entre le résultat Gate (G8) et le DecisionPacket (D) est
unidirectionnelle dans le pipeline courant : `check_packet()` enrichit le packet
mais n'influence pas `gate_result`. L'inverse n'est pas non plus implémenté :
`gate_result` n'est pas réinjecté dans le packet comme source de vérité. **[CODE]**

---

## 6. Résultats PRODUCTION PROUVÉS

> Les éléments suivants proviennent de l'analyse des fichiers JSONL du VPS.
> Ils sont marqués **[VPS]** et ne peuvent pas être vérifiés par lecture seule du repository.

### 6.1 Contingence du 30/08/2026

Analyse des rejections du 30 août 2026 par jointure `packet_id` entre
`rejections_2026-08-30.jsonl` et `decision_packets_2026-08-30.jsonl` :

| | `risk_failed=True` | `risk_failed=False` |
|---|---|---|
| **`gate_failed=True`** | 8 473 | 3 223 |
| **`gate_failed=False`** | 688 | 535 |

**[VPS]**

### 6.2 Interprétation des 688 cas divergents

Les 688 cas où `gate_failed=False` et `risk_failed=True` correspondent aux situations
où `check()` laisse passer mais `check_packet()` aurait bloqué.

**Investigation de ces 688 cas :**

- `first_blocker` = `meta` dans **100 % des cas** (0 exception observée le 30/08). **[VPS]**
- Conséquence : même si `check()` laissait passer, Meta bloquait de toute façon
  la décision avant qu'elle n'arrive à l'étape d'exécution.
- **Impact décisionnel autonome mesuré de la divergence : NULS.** **[VPS]**

### 6.3 Reproduction sur 8 jours (24–31/08/2026)

- Environ 4 600 cas divergents (`gate_failed=False`, `risk_failed=True`) sur la période. **[VPS]**
- `first_blocker` = `meta` dans **100 % des cas**, sur les 8 jours. **[VPS]**
- **Aucune exception observée** sur 8/8 jours. **[VPS]**
- Conclusion : le résultat du 30/08 n'est pas un artefact d'un jour particulier.
  Il reflète un pattern stable de la production courante. **[VPS]**

---

## 7. VERDICT

### CLOS

| Dossier | Conclusion |
|---|---|
| Impact opérationnel actuel de `check()/check_packet()` | **CLOS** — aucun impact décisionnel mesuré sur 8 jours (Meta est `first_blocker` dans 100 % des cas divergents). |
| HMM V2 | **CLOS** — le chemin HMM V2 est inactif dans le pipeline courant (vérifié dans `advisor_loop.py`). |
| Dossier Meta/Signal | **CLOS** — Meta fonctionne correctement comme premier filtre ; sa cohérence avec le `SignalGenerator` est confirmée. |
| Mismatch de régime entre LSE et advisor_loop | **CLOS** — aucun mismatch observé en production. |

### OUVERT

| Dossier | Nature |
|---|---|
| Dette architecturale `check()/check_packet()` | La divergence entre les deux méthodes est réelle au niveau du code. Elle n'a pas d'impact aujourd'hui mais pourrait en avoir si les seuils Meta changent. Une décision architecturale est requise (voir §8). |
| Représentation officielle de `results["gate"]` | `results["gate"]` et `block_stats_lifetime.json` reflètent uniquement `check()`. Si `check_packet()` devient la source de vérité, ces structures devront être mises à jour. |

### RISQUE LATENT

**Changement futur des seuils Meta** : si les seuils Meta sont abaissés (par exemple
lors d'une phase de calibration future), la proportion de cas où Meta n'est plus
`first_blocker` pourrait augmenter, exposant la divergence `check()/check_packet()`
à un impact décisionnel réel. Ce risque est actuellement nul mais devient pertinent
dès qu'une calibration Meta est envisagée.

---

## 8. Options architecturales

> Ces options sont documentées sans choix imposé. La décision appartient au propriétaire du projet.

### Option A — Convergence des scores

Aligner `check()` et `check_packet()` pour qu'ils comparent le même score :
soit `signal_result.score` devient `adjusted_confidence`, soit `check_packet()`
utilise `signal_result.score` comme entrée.

**Avantage :** cohérence totale entre les deux méthodes.  
**Risque :** changement de comportement potentiel ; requiert analyse d'impact et validation.

### Option B — `check_packet()` comme source de vérité

Capturer le résultat de `check_packet()` dans `advisor_loop.py` et l'utiliser
à la place de `gate_result` pour les décisions en aval.

**Avantage :** le `DecisionPacket` devient la source de vérité unique.  
**Risque :** changement architectural significatif ; impact sur `results["gate"]`,
`block_stats_lifetime.json`, et toute l'observabilité aval.

### Option C — Statu quo + surveillance / alerte

Conserver l'architecture actuelle. Ajouter une alerte (log ou métrique) dès qu'un
cas divergent (`gate_failed=False`, `risk_failed=True`) n'a pas `meta` comme
`first_blocker`.

**Avantage :** zéro risque de régression ; adapté à la phase de gel fonctionnel actuelle.  
**Risque :** la dette architecturale reste ; aucune correction si les seuils Meta changent.

> **Recommandation à court terme :** Option C, compte tenu de l'absence d'impact
> mesuré et du gel fonctionnel actuel (voir CLAUDE.md — Phase Validation Scientifique).
> La décision finale sur A/B/C appartient à Mathieu.

---

## 9. Historique Git

### Commits vérifiés dans ce clone

| Hash | Statut | Description |
|---|---|---|
| `154baea` | ✅ Vérifié dans le clone | `chore: ignore runtime-generated database files` |
| `c98181e` | ✅ Vérifié dans le clone | Merge PR #83 — `Merge pull request #83 from 3a7i3/copilot/documenter-investigations-techniques` |

### PR #83

**Confirmé dans l'historique Git du clone :**
`c98181e Merge pull request #83 from 3a7i3/copilot/documenter-investigations-techniques`

### Commits non vérifiables dans ce clone

Les commits suivants sont mentionnés dans le rapport de suivi VPS mais ne sont pas
présents dans le clone courant (clone peu profond / shallow clone) :

| Hash | Statut | Description probable |
|---|---|---|
| `9fb6525` | ⚠️ Non vérifiable dans ce clone | Commit lié au diagnostic Meta/Signal/Network du 30/08 |
| `19fb026` | ⚠️ Non vérifiable dans ce clone | Commit lié à l'investigation VPS |

> Pour vérifier ces commits : `git fetch --unshallow origin` puis `git show 9fb6525`.

---

## 10. Incidents annexes

> Ces incidents sont documentés pour mémoire. Ils sont **résolus** ou sans impact sur la
> production actuelle, sauf indication contraire.

| Incident | Statut | Note |
|---|---|---|
| Confusion de hash / branche | Résolu | Investigation initiale partie sur un mauvais hash ; corrigée par `git log` |
| Merge et conflit `bot.py` | Résolu | Conflit résolu manuellement ; commit de merge créé correctement |
| Authentification Git / deploy key read-only | Partiellement ouvert | La deploy key SSH est en lecture seule ; les pushes nécessitent HTTPS + token (voir §11) |
| HTTPS + token | Actif | Méthode utilisée pour les pushes depuis le VPS |
| Fichier fantôme | Résolu | Fichier supprimé de l'historique git sans impact sur la production |
| `pytest` dans `.venv` | Résolu | Confusion initiale entre `.venv` (environnement virtuel Python) et `.env` (variables d'environnement) |
| `.env` ignoré | Confirmé | `.env` est dans `.gitignore` ; ne pas le committer |
| DS-001 | Actif, surveillé | Règle de chemin configurable définie dans `conftest.py` et `core/invariants.py` ; un point potentiellement ouvert sur `lmi_live_state.json` (voir §11) |

---

## 11. Dossiers encore ouverts

| Sujet | Statut | Nature | Prochaine action | Responsable |
|---|---|---|---|---|
| `check()/check_packet()` | `NEEDS_ARCHITECTURAL_DECISION` | Dette architecturale | Choisir option A, B ou C (§8) | Mathieu |
| DS-001 / `lmi_live_state.json` | `OPEN` | Chemin test/production potentiellement non isolé | Analyser `trade_analysis/observatory.py` + `integrations/dashboard_adapter.py` ; corriger si violation DS-001 confirmée | Claude Code → Copilot |
| Deploy key SSH | `OPEN` | Infrastructure Git — authentification VPS | Décision sur la méthode d'authentification (deploy key upgrade ou HTTPS permanent) | Mathieu |
| Runtime files trackés | `PARTIALLY VERIFIED` | Hygiène dépôt | Vérifier si d'autres fichiers runtime sont trackés accidentellement (après `154baea`) | VPS + Copilot |

> **Note DS-001 / `lmi_live_state.json` :** Le fichier `trade_analysis/observatory.py`
> définit `LIVE_STATE_FILE = LMI_DIR / "lmi_live_state.json"` sans variable d'environnement
> surchargeable. Cela pourrait constituer une violation de DS-001 si ce chemin est utilisé
> par les tests sans isolation. Ce point **n'est pas confirmé comme anomalie** à ce stade ;
> il nécessite une analyse ciblée avant toute correction.

---

## 12. Prochaine action recommandée

### Action immédiate : NE PAS modifier `check()` / `check_packet()`

L'absence d'impact mesuré et le gel fonctionnel actuel (CLAUDE.md — Phase Validation
Scientifique) imposent de ne pas toucher à ces méthodes sans décision architecturale préalable.

### Séquence recommandée

```
1. [Mathieu] Décision architecturale : choisir option A, B, ou C (§8)
   └─ Si option C : ajouter surveillance/alerte, aucune modification de code
   └─ Si option A ou B :
       2. [Claude Code] Analyse d'impact ciblée sur les fichiers concernés
       3. [Copilot] Modification des fichiers identifiés (uniquement ceux-là)
       4. [VPS — read-only] Validation post-déploiement sur les fichiers JSONL de production
```

### En parallèle (indépendant)

- [Claude Code → Copilot] Analyser et résoudre DS-001 / `lmi_live_state.json` si confirmé.
- [Mathieu] Décision sur la méthode d'authentification Git (deploy key ou HTTPS).

---

## 13. Règle de continuité

### Ce document doit être mis à jour

Ce document est une **mémoire de reprise de projet**. Il doit être mis à jour après
chaque investigation majeure portant sur `check()/check_packet()` ou les sujets
listés au §11.

Procédure de mise à jour :
1. Créer un nouveau fichier `docs/diagnostics/YYYY-MM-DD-<sujet>.md` pour chaque
   nouvelle investigation substantielle.
2. Référencer le présent document dans le nouveau fichier (`Point de départ`).
3. Mettre à jour les tableaux §7 (VERDICT) et §11 (Dossiers ouverts) dans le présent
   document si des dossiers sont clos ou modifiés.
4. Committer la documentation séparément du code (`docs: ...`).

### Les conversations Claude/Copilot ne sont pas la mémoire du projet

> Les sessions de conversation Claude Code, Copilot ou autres agents IA sont
> éphémères. Un agent qui démarre une nouvelle session n'a accès qu'à ce qui est
> versionné dans Git. **Toute conclusion, preuve ou décision importante doit être
> documentée ici ou dans un fichier versionné équivalent**, jamais conservée
> uniquement dans l'historique d'une conversation.

---

*Document créé le 31/08/2026 — investigation read-only, aucune modification de code.*  
*Prochaine révision recommandée : après décision architecturale §8 ou après tout changement de seuil Meta.*

<!-- certif: ordinary push topology verified 2026-09-01 (PR #100, REQ-TRIGGER-TOPOLOGY-001) — read-only trace, no functional change -->
