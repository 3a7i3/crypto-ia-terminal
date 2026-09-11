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

`ExecutionEngine.create_futures_order()` (chemin futures demo) n'est PAS
couvert par cette phase — voir §6 "Hors scope" ci-dessous.

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

## 6. Hors scope de cette phase (documenté, pas silencieusement omis)

- **`ExecutionEngine.create_futures_order()`** (chemin futures demo) n'a
  PAS été mis derrière `authorize_order()`. Son clamp existant
  (`size_usd = max(futures_min, min(futures_max, size_usd))`) enlarge
  toujours une taille sous le minimum — le même anti-pattern que H2, mais
  sur un chemin demo/testnet distinct, avec un test de non-régression
  existant (`test_below_min_clamped_up`) qui encode ce comportement comme
  intentionnel pour ce chemin. Le traiter aurait élargi le blast radius
  au-delà des citations H1/H2 de l'audit (qui visent explicitement
  `execution_engine.py:274-283` et `:493-500`, le chemin spot/live) et créé
  un risque de régression non justifié par une hypothèse H1-H12 précise.
  Signalé ici comme candidat explicite pour REM-B.
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
