# ADR-0019 — Pre-network order authorization and exposure integrity

**Statut :** Accepté
**Date :** 2026-09-11
**Mission :** O-02W-PRE-T1-E-REM-A (première des trois phases de
remédiation planifiées REM-A/B/C sur l'audit `O-02W-PRE-T1-E`, PR #136,
`docs/contracts/O-02W-PRE-T1-E_ORDER_CYCLE_SAFETY.md`). SHA de départ :
`297eba891c56159e4fcc69a6b4f51be4e64443b8`.
**Contexte gouvernance :** fenêtre de stabilisation VPS
(`docs/governance/STABILIZATION_WINDOW_2026-09-03_2026-09-16.md`). Cette ADR
documente une correction d'un défaut déjà audité — pas une nouvelle
fonctionnalité, pas un nouveau signal/indicateur/stratégie, pas une
activation de trading réel.

---

## 1. Décision

Un unique module typé, `quant_hedge_ai/agents/execution/order_authorization.py`
(`authorize_order()` + `evaluate_trading_authority()`), constitue désormais
la frontière d'autorisation pre-network que TOUT chemin de mutation
exchange source-reachable doit appeler et respecter avant son premier appel
réseau de mutation. Couverts dans cette phase (REM-A) :

- `ExecutionEngine._place_live_order()` (chemin spot/live principal)
- `PositionManager._send_close_order()` (chemin de fermeture reduceOnly)
- `ExecutionEngine.create_futures_order()` (chemin futures demo — ajouté en
  **R1**, voir §6bis ci-dessous ; §6 initial documentant sa non-couverture
  reste conservé pour l'historique de la décision R0)

`authorize_order()` accepte désormais un paramètre `require_balance_check`
(défaut `True`, ajouté en R1) : un marché futures/margin consomme de la
marge en devise de cotation aussi bien en BUY qu'en SELL — contrairement au
spot, il n'y a pas de solde d'actif de base à vérifier pour un SHORT.
`create_futures_order()` passe `require_balance_check=False` ; les deux
autres chemins (spot BUY/SELL, close reduceOnly) gardent le comportement
inchangé (`True`).

`authorize_order()` retourne un `OrderAuthorizationResult` immuable et
explicite (jamais un booléen nu, jamais un rejet log-only) :
`authorized`, `symbol`, `side`, `requested_amount`, `authorized_max_amount`,
`normalized_amount`, `normalized_qty`, `authorized_max_notional`,
`denial_reason` (vocabulaire fermé, voir §3), `balance_source`,
`precision_amount`, `min_notional`, `detail`.

## 2. Rationale scientifique

L'audit O-02W-PRE-T1-E (PR #136, `297eba89`) a établi par preuve hermétique
que, sur le chemin `ExecutionEngine._place_live_order()` :

- une taille d'ordre invalide (NaN, infinie, négative, zéro, au-delà d'un
  seuil arbitraire) était **substituée** à `1.0` plutôt que rejetée (H1) ;
- un montant sous le notionnel minimum était **silencieusement enlargé** à
  `min_notional * 1.05`, dépassant l'intention autorisée (H2) ;
- seul le côté BUY vérifiait un solde (quote), aucun contrôle n'existait
  côté SELL (H7, gap non documenté) ;
- l'autorité de trading n'avait pas de composition documentée/testée de
  bout en bout sur le chemin `PositionManager` (portion pre-network de
  H10).

Le Scientific Debt Rule (CLAUDE.md) exige que toute correction soit
justifiée par un besoin de validation déjà établi — ici, l'audit lui-même
constitue ce besoin : ces défauts permettent qu'une intention de trading
logique unique produise un ordre invalide ou anormalement dimensionné avant
même toute question de retry/réconciliation (hors scope REM-A). Corriger
la validation pre-network élimine des variables expérimentales (des
montants d'ordre non reproductibles/non bornés) sans en introduire de
nouvelles : `authorize_order()` ne change aucune formule de sizing, aucun
seuil de risque, aucune stratégie — il valide strictement ce qu'elle
produit déjà.

## 3. Vocabulaire de refus (fermé)

`INVALID_AMOUNT`, `NON_FINITE_AMOUNT`, `NON_POSITIVE_AMOUNT`,
`ABOVE_AUTHORIZED_EXPOSURE`, `BELOW_MIN_NOTIONAL`, `PRECISION_COLLAPSE`,
`PRECISION_WOULD_INCREASE_EXPOSURE`, `INSUFFICIENT_QUOTE_BALANCE`,
`INSUFFICIENT_BASE_BALANCE`, `BALANCE_UNAVAILABLE`, `AUTHORITY_DENIED`,
`UNSUPPORTED_MARKET_SEMANTICS`, `METADATA_UNAVAILABLE`. Une donnée
inconnue/malformée refuse toujours l'autorisation — jamais de passage
silencieux.

## 4. Comportement avant / après

| Défaut | Avant (audit `297eba89`) | Après (REM-A) |
|---|---|---|
| Taille invalide (H1) | Substituée à `1.0`, ordre envoyé | Rejetée (`NON_FINITE_AMOUNT`/`NON_POSITIVE_AMOUNT`/`ABOVE_AUTHORIZED_EXPOSURE`), zéro mutation |
| NaN | Contourne le garde (`nan<=0`/`nan>1e9` = `False`) | `math.isfinite()` explicite ajouté en amont, capturé |
| Notionnel min (H2) | Enlargé à `min_notional*1.05` | Rejeté (`BELOW_MIN_NOTIONAL`), jamais amplifié |
| Précision | Arrondi binaire-float non garanti conservateur | `Decimal`, floor exclusivement (`ROUND_DOWN`), jamais d'enlargissement |
| Balance BUY | Vérifiée (quote) | Inchangée (vérifiée via la même frontière) |
| Balance SELL (H7) | Absente | Vérifiée (base), `INSUFFICIENT_BASE_BALANCE`/`BALANCE_UNAVAILABLE` |
| Capital scientifique | N'alimentait pas le sizing (ADR-0018, préservé) | Toujours exclu — `authorize_order()` n'a aucun paramètre `scientific_capital`, seul `exchange.fetch_balance()` alimente les soldes |
| `PositionManager._send_close_order` swallow (B7) | Exception avalée, `pos.closed=True` inconditionnel | Retourne un résultat explicite ; `pos.closed` reste `False` sur refus/échec (retenté au tick suivant, aucune nouvelle machinerie de retry) |
| Autorité `PositionManager` (H10 partiel) | Ne revérifiait pas `PAPER_TRADING_ENABLED`/`LIVE_TRADING_CONFIRMED` | Revérifie les deux, fail-closed, juste avant mutation |
| Notionnel min futures demo (H2, R1) | `size_usd = max(futures_min, min(futures_max, size_usd))` — enlargissait toujours une taille sous le minimum | Rejeté (`BELOW_MIN_NOTIONAL` via `authorize_order()`), jamais amplifié ; le clamp vers le bas (`min(futures_max, ...)`) est conservé car il ne fait que rétrécir, jamais enlargir |
| `PositionManager._send_close_order` dimension (R1) | Ternaire mort `qty * price if price > 0 else qty * price` — toujours `qty * price` quelle que soit la condition, code trompeur (jamais une vraie substitution de valeur) | Ternaire supprimé ; `requested_notional`/`ceiling_notional` nommés explicitement comme notionnel USD, jamais confondus avec `qty` (base) |
| `PositionManager` appel à `evaluate_trading_authority()` (R1, vérifié) | Déjà correct sur ce HEAD — lit `PAPER_TRADING_ENABLED`/`LIVE_TRADING_CONFIRMED` fraîchement puis appelle la fonction partagée, aucune réimplémentation locale trouvée | Inchangé ; preuve par construction ajoutée (monkeypatch de `evaluate_trading_authority` dans le namespace du module, assertion d'appel avec les kwargs frais) |

## 5. Ce que REM-A NE résout PAS (réservé REM-B/REM-C)

- `clientOrderId` / identité déterministe d'ordre (H3)
- Journalisation durable de l'intention avant réseau (H4/H9)
- Réconciliation après ambiguïté réseau / retry idempotent (H5/H6) —
  `_with_retry` reste un retry aveugle inchangé
- Machine à états de fill partiel, activation de `PendingOrderTracker`
- Recovery après crash pendant la fenêtre réseau

Le contrat `O-02W-PRE-T1-E_ORDER_CYCLE_SAFETY.md` reste donc au verdict
**`REMEDIATION_REQUIRED`** — REM-A ne clôt qu'un sous-ensemble des
bloqueurs (voir la mise à jour §18 du contrat).

## 6. Hors scope de cette phase R0 (superseded en R1 — voir §6bis)

- **`ExecutionEngine.create_futures_order()`** (chemin futures demo) n'avait
  PAS été mis derrière `authorize_order()` en R0. Son clamp existant
  (`size_usd = max(futures_min, min(futures_max, size_usd))`) enlargissait
  toujours une taille sous le minimum — le même anti-pattern que H2, mais
  sur un chemin demo/testnet distinct, avec un test de non-régression
  existant (`test_below_min_clamped_up`) qui encodait ce comportement comme
  intentionnel pour ce chemin.
  **R1 (MASTER review) :** cette décision a été réexaminée — le chemin est
  source-reachable depuis `core/advisor_loop.py:6568`
  (`exec_engine.create_futures_order(...)` sous `has_futures_demo()`), donc
  un candidat REM-B différé était insuffisant. Voir §6bis.
- **`PositionManager._check_partial_close()`** ignore toujours la valeur de
  retour de `_send_close_order()` pour la comptabilité de `pos.qty`/
  `pos.size_usd` après un partial close — la honnêteté d'échec ajoutée à
  `_close_position()` ne s'étend pas à ce chemin, qui ne modifie pas l'état
  de la position tracker au-delà de ce que cette mission autorise à toucher.
- Le mécanisme "autoheal" enregistré sur `alert_manager` pour le module
  `execution` (`execution_autoheal` → `{"action": "force_size",
  "new_size": 1.0}`) écrit toujours cette suggestion dans le journal
  d'audit d'alertes ; elle n'a jamais été appliquée au flux d'exécution
  (vérifié — `run_autoheal()` ne modifie aucune variable de
  `create_order()`), donc ce n'est pas un vecteur de substitution vivant,
  mais l'entrée de log reste trompeuse ("correction: True" pour une
  correction jamais appliquée). Non modifié dans cette phase (hors scope
  des corrections A-E).

## 6bis. R1 — `create_futures_order()` mis derrière la frontière (2026-09-11)

Trois défauts remontés par la revue MASTER du round R0 sont corrigés ici,
sans introduire aucune fonctionnalité REM-B/REM-C :

1. **`create_futures_order()` intégré.** Preuve de source-reachability :
   `core/advisor_loop.py:6568` appelle
   `exec_engine.create_futures_order(sym, signal_action, effective_size)`
   quand `exec_engine.has_futures_demo()` est vrai — ce n'est pas du code
   mort. Le clamp bas (`size_usd = min(futures_max, size_usd)`) est
   conservé (il ne fait que rétrécir, jamais enlargir) ; le clamp haut vers
   `futures_min` est supprimé et remplacé par un appel à `authorize_order()`
   avec `min_notional=futures_min`, qui rejette (`BELOW_MIN_NOTIONAL`) au
   lieu d'enlargir. `require_balance_check=False` car la marge futures
   n'est pas un solde d'actif spot (voir §1). Le fallback de précision par
   défaut (`amt_precision`) est aussi corrigé de `0.001` à `1e-5` — la
   valeur `0.001` était trop grossière pour BTC et aurait causé un
   `PRECISION_COLLAPSE` systématique sur de petits notionnels legitimes
   sous l'arrondi strict (floor) désormais appliqué ; `1e-5` est la même
   valeur de repli déjà utilisée par `_place_live_order()`. `qty` n'est
   **jamais** re-clampé vers `min_qty` après autorisation (le faire
   réintroduirait exactement l'anti-pattern H2 supprimé) — un ordre sous le
   minimum exchange après autorisation échoue visiblement côté exchange,
   il n'est pas silencieusement enlargi.
2. **Défaut dimensionnel dans `PositionManager._send_close_order()`
   corrigé.** Le ternaire mort `qty * price if price > 0 else qty * price`
   est supprimé ; `requested_notional = qty * price` et
   `ceiling_notional = pos.qty * price` sont nommés explicitement comme
   notionnel USD (jamais `qty` brut). Vérification : la valeur numérique
   était déjà correcte avant (le ternaire était toujours équivalent à
   `qty * price`) — c'est un défaut de lisibilité/auditabilité, pas un
   défaut de valeur ; corrigé quand même car un ternaire dont les deux
   branches sont textuellement identiques est un signal fort d'erreur de
   frappe non détectée, inacceptable dans une frontière de sécurité.
   Tests ajoutés à prix non triviaux (50 000 et 0,001) prouvant que
   `normalized_qty` et le notionnel ne peuvent pas être transposés.
3. **Appel de `PositionManager` à `evaluate_trading_authority()`
   ré-examiné.** Vérification sur ce HEAD : `_send_close_order()` lit déjà
   `PAPER_TRADING_ENABLED`/`LIVE_TRADING_CONFIRMED` fraîchement puis appelle
   la fonction partagée — aucune réimplémentation locale du gate n'a été
   trouvée avant ou à la place de cet appel. Aucun changement de code requis
   ; une preuve par construction est ajoutée (monkeypatch de
   `evaluate_trading_authority` dans le namespace `position_manager`,
   assertion que l'appel reçoit les kwargs frais et que sa réponse pilote
   directement le résultat retourné).

## 7. Non-régression

- ADR-0018 (séparation capital scientifique / observation exchange)
  préservée : `authorize_order()` ne référence jamais
  `get_scientific_capital()`, testé structurellement
  (`test_scientific_capital_never_substitutes_for_balance`).
- Formule de sizing et seuils de risque inchangés (`SessionGuard`,
  `size_factor`, `EXEC_MAX_ORDER_USD`, etc.) — `authorize_order()` valide
  la sortie de la stratégie, ne la recalcule jamais.
- Aucun `clientOrderId`, aucune activation de `PendingOrderTracker`.
- Aucun changement de défaut n'active le trading réel.
