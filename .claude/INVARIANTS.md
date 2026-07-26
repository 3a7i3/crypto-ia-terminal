# INVARIANTS — Registre opposable du chantier

> Livrable du ticket **GOV-002**.
>
> `GOVERNANCE.md` explique **pourquoi** ces règles existent. Ce registre dit **comment prouver
> qu'elles ont été violées**. Il ne recopie pas la gouvernance : il la rend vérifiable.
>
> Un invariant sans test de violation exécutable n'arrête personne. Chaque entrée ci-dessous porte
> donc une **commande** ou un **contrôle concret**, dont la sortie tranche sans discussion.

Version 1.0 — 2026-07-24 · Cité par tous les tickets du chantier.

---

## INV-1 — Passivité absolue des observers

**Énoncé.** Aucun composant d'observabilité, de télémétrie, de regret ou de calibration ne peut
influencer une décision de trading en temps réel. Le moteur de décision est le seul à décider.

**Raison d'être.** ADR-0007. Un observateur qui influence la chose qu'il observe cesse d'être une
mesure et devient une variable expérimentale non contrôlée. La validation scientifique en cours
serait invalidée sans qu'aucun test ne le signale.

**Test de violation.**
```bash
git diff --cached | grep -nE "^\+.*(observability|dip/|regret|telemetry).*\.(check_new_trade|place_market_order|add_position)"
```
Toute correspondance = violation. Contrôle complémentaire : dans le diff, un module d'observabilité
ne doit apparaître qu'en **lecture** (jamais en argument d'une fonction de décision).

**Conséquence d'une violation.** Les données produites depuis la violation sont contaminées :
elles ne mesurent plus le moteur mais la boucle observateur-moteur. Annuler le commit et remonter
à l'opérateur ; ne pas « corriger en avançant ».

---

## INV-2 — Aucun reset de N sans ADR d'époque signé

**Énoncé.** Modifier ce que le moteur **regarde** change son comportement, impose une nouvelle borne
d'époque et remet le compteur de trades à zéro. Interdit sans ADR signé par l'opérateur.

**Raison d'être.** Le burn-in est le seul actif du projet. Époque courante :
`CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z` (`scripts/data_quality.py`, alias
`CLEAN_DATA_SINCE_ACTIVE`). Le rollback de code existe ; **le rollback d'époque n'existe pas.**

**Test de violation.**
```bash
git diff --cached --name-only | grep -E "(portfolio_brain|data_quality)\.py$"
git diff --cached -- core/advisor_loop.py | grep -nE "^[+-].*(pos_manager\.get_open|check_new_trade)"
git diff --cached -- quant_hedge_ai/agents/risk/portfolio_brain.py | grep -nE "^[+-].*MAX_[A-Z_]+ *="
```
Une correspondance sur un ticket **non gated** = violation.

### Test de gating — à appliquer à TOUT changement, avant de coder

> **« Ce changement modifie-t-il ce que le moteur REGARDE, ou seulement ce qu'il MONTRE ? »**

| Réponse | Classement | Conséquence |
|---|---|---|
| Ce qu'il **montre** — panneau, REST, logs, documentation, tests | **NON GATED** | Exécutable. N inchangé. |
| Ce qu'il **regarde** — voir symboles ci-dessous | **GATED** | Reset d'époque. ADR signé obligatoire. |

**Symboles sensibles — tout contact déclenche le gating :**

`PositionManager` · `check_new_trade` · sizing · risk · `PortfolioBrain` **en entrée de décision** ·
seuils par régime · `CLEAN_DATA_SINCE_*`

**Règle de défaut :** en cas de doute, la réponse est **GATED**, et on s'arrête.
Le coût des deux erreurs n'est pas symétrique — s'arrêter à tort coûte une session, continuer à tort
peut coûter le burn-in complet, sans retour possible.

**Conséquence d'une violation.** N est détruit sans décision, sans ADR, sans archivage de l'époque.
Perte irréversible. C'est la violation la plus grave du registre.

---

## INV-3 — `paper_trades.jsonl` : écrivains uniques, historique jamais réécrit

**Énoncé.** Seuls `paper_trading/mexc_simulator.py` et `paper_trading/recorder.py` écrivent dans
`paper_trades.jsonl`. L'historique existant n'est jamais modifié ni supprimé — on ajoute, on ne
réécrit pas.

**Raison d'être.** C'est le grand livre scientifique, lu par `tools/cri_calculator.py` et
`scripts/data_quality.py`. Une ligne modifiée après coup rend tout calcul de CRI, de N et de seuil
non reproductible — et la falsification serait indétectable.

**Test de violation.**
```bash
git diff --cached --name-only | grep -E "^(databases/|.*paper_trades\.jsonl)"
git diff --cached | grep -nE "^\+.*open\(.*paper_trades.*['\"](w|a|r\+)"
```
Toute correspondance hors des deux écrivains autorisés = violation.
Contrôle complémentaire : `git diff` sur le fichier de données doit être **vide** pour tout ticket.

**Conséquence d'une violation.** Le dataset devient non certifiable ; le CRI et le N deviennent faux
sans signal. Annuler immédiatement, ne pas tenter de « réparer » les lignes.

---

## INV-4 — Aucun seuil modifié avant N ≥ 500 et CRI ≥ 90

**Énoncé.** Aucune constante de seuil du moteur de décision n'est modifiée tant que la règle du
statisticien n'est pas satisfaite (500 trades / 150 winners / 150 losers / 100 MISSED_WIN /
100 GOOD_REFUSAL / 50 par régime / 30 par couche / CRI ≥ 90). Base de sizing épinglée à
`WALLET_PAPER_CAPITAL`.

**Raison d'être.** Un seuil ajusté sur un faible échantillon est un surapprentissage déguisé en
calibration. Modifier un seuil pendant la mesure invalide la mesure.

**Test de violation.**
```bash
git diff --cached -- quant_hedge_ai/agents/risk/portfolio_brain.py | grep -nE "^[+-].*(MAX_TOTAL_EXPOSURE_PCT|MAX_SINGLE_SYMBOL_PCT|MAX_SAME_REGIME_PCT|MAX_LEVERAGE_WEIGHTED|MAX_CORRELATION_RISK|MIN_FRAGMENTATION_USD|MAX_POSITIONS|MAX_SAME_DIRECTION)"
```
Sortie non vide = violation. Attendu pour tout ticket du chantier : **sortie vide**.

**Piège documenté.** La tentation apparaît précisément après `PORT-002` : le gate devient plus
restrictif, le débit de trades chute, et « assouplir un seuil pour compenser » paraît raisonnable.
C'est exactement la violation que cet invariant existe pour interdire. La chute de débit est le
**résultat attendu** d'un gate qui voit enfin la réalité, pas un défaut à corriger.

**Conséquence d'une violation.** La campagne de mesure en cours perd sa validité : on ne mesure plus
un moteur stable mais un moteur ajusté en cours de route.

---

## Application

**Avant chaque commit**, exécuter les quatre tests de violation ci-dessus sur le diff **stagé**.
Attendu pour tout ticket non gated : **les quatre sorties sont vides**.

Une seule sortie non vide ⇒ **ne pas commiter**, et appliquer `EXECUTION_FLOW.md` §1.

**Dans le rapport de fin de ticket** (gabarit `GOV-004`), la section « Invariants vérifiés » nomme
les invariants contrôlés **et la commande utilisée**. Écrire « invariants respectés » sans citer le
contrôle n'est pas une vérification : c'est une affirmation.

---

## Ce que ce registre n'est pas

Ce n'est pas une liste de bonnes pratiques. Ce sont **quatre conditions dont la violation invalide
la campagne scientifique en cours** — deux d'entre elles (INV-2, INV-3) de façon irréversible.

Il ne contient délibérément que quatre entrées. Un registre de vingt invariants ne serait pas lu,
donc ne protégerait rien.
