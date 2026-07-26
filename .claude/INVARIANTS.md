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

## INV-HEALTH-001 — La santé de la suite est un état de référence, pas un caveat

**Énoncé.** Chaque ticket déclare la **santé de la suite** sur laquelle il s'appuie, et le nombre
d'erreurs de collecte **attendu**. L'écart entre observé et attendu est un verdict binaire.

| Observé vs attendu | Verdict |
|---|---|
| `observé == expected` | **PASS** — dette connue, inchangée |
| `observé > expected` | **FAIL** — le ticket a introduit une dette. Annuler. |
| `observé < expected` | **La dette a diminué.** Mettre à jour `health_baseline` dans le manifeste. |

**Raison d'être.** La suite du dépôt ne s'exécute pas avec `pytest tests/ -q` : la collecte est
interrompue par un `ImportError` préexistant. Traiter cela comme un « caveat » le rend invisible et
non comparable. Le transformer en **nombre attendu** en fait un invariant mesurable : une dette connue
cesse d'être une excuse et devient une borne.

**État de référence** (mesuré au commit `8cb42fb`, avant tout travail sur `tests/`) :

```
Commande officielle :
    python -m pytest tests/ -q --continue-on-collection-errors

suite_state                : DEGRADED
expected_collection_errors : 1
known_error                : tests/test_full_integration.py:13
                             ModuleNotFoundError: tracker_system.exchange.binance_client
```

**Test de violation.**
```bash
python -m pytest tests/ -q --continue-on-collection-errors 2>&1 | grep -c "^ERROR "
```
Résultat ≠ `expected_collection_errors` du manifeste ⇒ traiter selon le tableau ci-dessus.

**Ce que cet invariant interdit explicitement.** Réparer `test_full_integration.py` pendant la campagne.
Ce ticket échoue à **INV-ROI-001** : il n'améliore ni le débit de trades, ni la validité de la mesure
de N, et ne débloque aucun ticket. C'est une **dette de maintenance, pas un ticket de campagne** —
à traiter hors gel, jamais pendant.

**Conséquence d'une violation.** Une erreur de collecte supplémentaire masque potentiellement des
dizaines de tests jamais exécutés. Le « vert » de la suite deviendrait un vert par absence, pas par
succès — exactement le type de mensonge d'instrument que tout ce chantier corrige.

---

## INV-TRACE-001 — Le diff est exactement le contrat, rien de plus

**Énoncé.** L'ensemble des fichiers modifiés par un ticket doit être **exactement égal** à la liste
annoncée dans son contrat d'exécution. Ni plus, ni moins.

**Raison d'être.** Empêcher le « au passage j'ai corrigé… », qui produit trois effets tous nuisibles :
un diff non revertable proprement, une régression attribuée au mauvais ticket, et une revue qui ne
peut plus se fier au périmètre annoncé.

**Test de violation.**
```bash
diff <(git diff --cached --name-only | sort) <(printf '%s\n' "${CONTRACT_FILES[@]}" | sort)
```
Sortie non vide = **FAIL**. Le ticket ne se commite pas tant que les deux ensembles ne coïncident pas.

Variante minimale, sans variable de contrat :
```bash
git diff --cached --name-only            # a comparer a l'oeil avec la section FICHIERS du prompt
```

**Conséquence d'une violation.** Deux issues, jamais une troisième : soit on **retire** du staging ce
qui déborde (`git restore --staged <fichier>`), soit on **révise le contrat explicitement** et on le
consigne. Jamais « c'était petit, je l'ai laissé ».

**Précédent documenté — `GOV-002` (2026-07-26).** Le commit annonçait un registre d'invariants et a
emporté 43 fichiers d'infrastructure. **Atomicité violée.** L'écart a été consigné dans `proof.caveat`
au lieu d'être masqué, mais l'invariant n'existait pas encore pour l'empêcher. `GOV-004`, exécuté
ensuite, a tenu 2 fichiers — périmètre strict. C'est le comportement attendu.

---

## INV-ROI-001 — Tout ticket doit servir la campagne en cours

**Énoncé.** Chaque ticket doit répondre **OUI** à :

> **« Ce ticket rapproche-t-il le projet de l'accumulation de N, ou rend-il la mesure de N valide ? »**

Si **NON** → le ticket est **différé**, **gated**, ou **supprimé**. Pas « fait quand même parce qu'il
est utile un jour ».

**Raison d'être.** Les invariants INV-1 à INV-4 empêchent de *casser* la campagne. Celui-ci empêche
de la *diluer*. Sous un gel dont l'unique objectif est d'atteindre N ≥ 100 puis N ≥ 500, toute
construction dont le retour arrive après la campagne consomme le temps de la campagne sans la servir.

**Les deux réponses qui valent OUI — ne pas les confondre.**

| Voie | Question | Exemple |
|---|---|---|
| **Débit** | Accélère l'accumulation de trades ? | Corriger une famine de trading |
| **Validité** | Rend la mesure de N digne de confiance ? | `OBS-002` : le panneau cesse de mentir |

La seconde voie est la moins intuitive et la plus importante : **N = 100 trades mesurés par un
instrument faux ne vaut rien.** Réparer l'instrument sert la campagne même sans accélérer un seul trade.

**Test de violation.** Question posée à voix haute avant d'ouvrir un fichier. Réponse consignée dans
le rapport de fin de ticket. Une réponse du type « ça améliore la maintenance future », « ce sera utile
plus tard », « c'est plus propre » est un **NON déguisé**.

**Précédent documenté — `render_docs.py` (2026-07-26).** Générateur de vues construit pendant le gel.
Débit : non. Validité de la mesure : non. Il améliore la maintenance documentaire, dont le retour
arrive **après** la campagne. **INV-ROI-001 l'aurait différé.** Il est conservé, gelé en l'état, et
sert de cas de référence : l'argument « ça réduit la maintenance » est précisément la forme que prend
la violation.

**Application au chantier SSoT lui-même** — l'invariant doit passer son propre test :

| Phase | Débit | Validité | Verdict |
|---|---|---|---|
| PHASE_01 (observabilité) | non | **oui** | OUI — le panneau cesse de mentir |
| PHASE_03 (REST) | non | **oui** | OUI — le dashboard cesse de publier `0` |
| PHASE_00 (gouvernance) | non | indirect | OUI **conditionnel** — précondition de PHASE_01, jamais une fin |
| PHASE_02 / PHASE_04 (gated) | non | oui, mais **coûte N → 0** | Arbitrage `D-1`, décidé sur le chiffre de `PORT-001` |
| `render_docs.py` | non | non | **NON** — précédent ci-dessus |

**Conséquence d'une violation.** Aucune donnée n'est corrompue : c'est du temps de campagne dépensé
hors campagne. Le coût est invisible sur le moment et ne se voit qu'à la fin — c'est ce qui rend cet
invariant nécessaire.

> **Limite assumée.** INV-ROI-001 n'est pas mécaniquement vérifiable, contrairement à INV-1 → INV-4.
> Il repose sur une réponse honnête à une question. Sa seule force est d'obliger à la formuler
> **avant** d'écrire, et à la consigner. C'est peu, et c'est mieux que rien.

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
