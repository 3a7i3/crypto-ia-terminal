# Plan de reprise — Crypto AI Terminal

> Document autonome destiné à un autre assistant pour reprendre le travail.
> Tout ce qui suit est du français/technique, copier-coller-able tel quel.
> **Lis-le en entier avant de toucher au code.**

---

## 1. Contexte

L'utilisateur (Mathieu) développe un bot de trading crypto en Python qui tourne
contre **Binance Spot Testnet + Futures Demo**. Le bot s'appelle
`advisor_loop.py` à la racine de `C:\Users\WINDOWS\crypto_ai_terminal`.

Architecture en couches (toutes appelées dans `analyze_symbol()` autour des
lignes 350-750 d'`advisor_loop.py`) :

1. **MarketScanner** + **MultiTimeframeScanner** — données OHLCV via CCXT
2. **MetaStrategyEngine** — choisit une "personnalité" (MEAN_REVERSION,
   MOMENTUM_FOLLOWING, etc.) selon le régime de marché
3. **LiveSignalEngine** (`SignalResult`) — produit BUY/SELL/HOLD + score 0-100
4. **GlobalRiskGate** — bloque si score < 70 ou non-confirmé
5. **ConvictionEngine** — calcule un score de conviction multi-dimension
6. **PortfolioBrain / CapitalAllocationEngine** — sizing Kelly
7. **NoTradeIntelligence / MistakeMemory** — refus basé sur patterns historiques
8. **ExecutiveOverride** — VETO global selon DD / loss_streak / open_pnl
9. **ThreatRadar / DecisionArbitrator V2** — couches finales
10. **ExecutionEngine** — pose l'ordre via CCXT

Le tout en cycles de 300s par défaut, avec watchdog de timing et
`[FLOW]` logs à chaque étape.

---

## 2. État actuel (au moment de la passation)

### 2.1 Bugs CORRIGÉS (déjà appliqués au repo)

#### a) `property 'actionable' has no setter`
- **Symptôme** : `AttributeError: property 'actionable' of 'SignalResult'`
  ligne 423 d'`advisor_loop.py`.
- **Cause** : `SignalResult` (`quant_hedge_ai/agents/execution/live_signal_engine.py`
  ligne 37-39) déclare `actionable` en `@property` (lecture seule).
  Le code essayait `signal.actionable = True`.
- **Fix appliqué** : remplacé par `gate_result.allowed = True` et
  `signal_to_execute = "BUY"` quand override actif.
- **Vérif** : grep `signal.actionable\s*=` ne retourne plus que des
  commentaires + 2 fichiers de tests qui utilisent `MagicMock` (OK).

#### b) Faux drawdown 89.9% qui déclenchait `ExecutiveOverride VETO`
- **Symptôme** : `[ExecutiveOverride] CLEAR -> VETO | triggers: DD=89.9%`
  alors que le capital n'a jamais bougé.
- **Cause racine** : Binance retourne par moments
  `{"code":-1021,"msg":"Timestamp for this request was 1000ms ahead of the
  server's time."}`. La fonction `fetch_available_capital()` du fichier
  `quant_hedge_ai/agents/execution/execution_engine.py` retombait alors sur
  `V9_INITIAL_CAPITAL=1000` (fallback). Donc `peak_capital=9854` et
  `capital_current=1000` → DD calculé à 89.9% → VETO.
- **Fix appliqué** : la fonction garde maintenant en mémoire la dernière
  valeur valide (`self._last_known_capital`) et la retourne au lieu du
  fallback fixe quand l'API plante temporairement.
- **Code actuel de `fetch_available_capital()` (lignes ~157-180)** :

  ```python
  def fetch_available_capital(self) -> float:
      if self._exchange is not None:
          try:
              bal = self._exchange.fetch_balance()
              usdt = float(bal.get("free", {}).get(self._quote_asset, 0.0))
              if usdt > 0:
                  self._last_known_capital = usdt
                  return usdt
          except Exception as exc:
              logger.warning("[ExecutionEngine] fetch_balance erreur: %s", exc)
      last = getattr(self, "_last_known_capital", 0.0)
      if last > 0:
          return last
      return float(os.getenv("V9_INITIAL_CAPITAL", "1000"))
  ```

#### c) `meta_allowed` non bypassé en mode test
- **Symptôme** : `FORCE_TEST_EXECUTION=true` ne suffisait pas, les ordres
  ne partaient pas car `meta_allowed=False` (la personnalité MEAN_REVERSION
  exige score ≥ 72).
- **Fix appliqué** : ajouté `meta_allowed = True` dans le bloc
  `FORCE_TEST_EXECUTION` lignes ~610-625 d'`advisor_loop.py`.

#### d) Taille `$0.00` dans les logs
- **Symptôme** : ordres Binance partaient au minimum (`0.0007 BTC ≈ $5`)
  au lieu de la taille configurée `EXEC_MAX_ORDER_USD=50`.
- **Cause** : la personnalité passait en `TRADING BLOQUE` (size×0) →
  `effective_order_size(50, perso) = 0`.
- **Fix appliqué** : dans le bloc `FORCE_TEST_EXECUTION`, on restaure
  `order_size_usd = EXEC_MAX_ORDER_USD` quand il a été ramené à 0.

#### e) Mistake memory `LOW_CONVICTION_LOSS`
- **Symptôme** : 2 entrées historiques bloquaient les trades à conviction
  faible (règle auto-générée dans `databases/mistake_memory.jsonl`).
- **Fix appliqué** : fichier vidé manuellement.

### 2.2 État fonctionnel à la passation

✅ Le bot tourne sans crash
✅ Connexion Binance OK (`Capital disponible: $9854.36 | Mode: TRADING ACTIF
   - Futures Demo (CONNECTE $4992 USDT)`)
✅ Cycles complets en ~1.9s
✅ Trades partent sur Futures Demo avec `FORCE_TEST_EXECUTION=true` +
   `GATE_MIN_SCORE_OVERRIDE=50` :
   - LONG BTC/USDT entry $81380.70 SL $79753.09 TP $84635.93
   - LONG ETH/USDT entry $2371.70 SL $2324.27 TP $2466.57
✅ Plus de DD=89.9%, plus de VETO

---

## 3. Ce qu'il reste à faire (par ordre de priorité utilisateur)

### Phase 1 — Reconnexion Binance robuste **(PRIORITÉ ABSOLUE)**

**Pourquoi** : ligne 1142-1148 d'`advisor_loop.py` :

```python
healer.register_simple(
    "exchange",
    health_fn=exchange_monitor.is_healthy,
    restart_fn=lambda: log.warning(
        "[SelfHeal] Exchange unhealthy — aucun restart auto possible"
    ),
)
```

Le `restart_fn` est un **no-op**. Si Binance tombe pendant la nuit, le bot
détecte la coupure mais ne se reconnecte jamais → utilisateur en aveugle.

**Sous-tâches** :

1. **Ajouter `ExecutionEngine.reconnect()`** dans
   `quant_hedge_ai/agents/execution/execution_engine.py` :
   - Fermer les clients CCXT existants (`self._exchange`, `self._exchange_futures`)
     avec try/except
   - Reconstruire via `_build_spot_client()` / `_build_futures_client()`
     (les fonctions internes existantes — vérifier leur nom exact dans le
     fichier, elles sont dans la méthode `__init__`)
   - Réauthentifier (load_markets)
   - Logger `[ExecutionEngine] Reconnexion réussie en X.Xs (latence Y ms)`
   - Retourner `True` si OK, `False` sinon

2. **Wrapper retry sur les appels CCXT critiques** :
   - `fetch_balance`, `fetch_ticker`, `fetch_ohlcv`, `create_order`
   - 3 essais avec backoff exponentiel : 0.5s, 1s, 2s
   - Sur 3e échec, déclencher `self.reconnect()` puis 1 dernier essai
   - Helper interne `_with_retry(fn, *args, **kwargs)`

3. **Brancher le vrai `restart_fn`** dans `advisor_loop.py` ligne 1142 :

   ```python
   def _exchange_restart() -> None:
       try:
           ok = exec_engine.reconnect()
           if ok:
               log.info("[SelfHeal] Exchange reconnecté")
           else:
               log.error("[SelfHeal] Reconnexion échouée")
       except Exception as exc:
           log.exception("[SelfHeal] Reconnexion exception: %s", exc)

   healer.register_simple(
       "exchange",
       health_fn=exchange_monitor.is_healthy,
       restart_fn=_exchange_restart,
   )
   ```

4. **Heartbeat plus fin** :
   - Dans `supervision/exchange_monitor.py` : passer `CHECK_INTERVAL=60`
     à `15` (ou env var `EXCHANGE_HEARTBEAT_S`).
   - `WARN_AFTER=2` reste OK (= 30s avant alerte).

5. **Test manuel** : couper le wifi 30s pendant que le bot tourne, vérifier
   qu'on voit dans les logs :
   ```
   [ExchangeMonitor] Connexion perdue (3 échecs consécutifs)
   [SelfHeal] Composant exchange unhealthy → restart
   [ExecutionEngine] Reconnexion tentative 1/3...
   [ExecutionEngine] Reconnexion réussie en 1.2s
   ```

### Phase 2 — Snapshot live unifié

**But** : un fichier JSON mis à jour chaque cycle, lisible par n'importe quel
dashboard en 1 ligne, pour avoir vue temps réel sur tout.

**Sous-tâches** :

1. **Créer un module** `quant_hedge_ai/dashboard/live_snapshot.py` avec :
   ```python
   def write_snapshot(path: Path, data: dict) -> None:
       """Atomique : écrit dans .tmp puis rename."""
       tmp = path.with_suffix(".tmp")
       tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
       tmp.replace(path)
   ```

2. **À la fin de chaque cycle** dans `advisor_loop.py` (juste avant
   `Prochain cycle dans Xs`), construire et écrire :
   ```python
   snapshot = {
       "ts": time.time(),
       "cycle": cycle,
       "capital": real_capital,
       "exchange": exchange_monitor.snapshot(),     # latency, healthy, uptime
       "kill_switch": {"safe_mode": kill_switch.is_safe_mode()},
       "executive_override": executive_override.metrics_snapshot(),
       "positions": [s for s in pos_manager.snapshot()],
       "symbols": [
           {
               "symbol": r["symbol"],
               "prix": r["prix"],
               "signal": r["signal"].signal,
               "score": r["signal"].score,
               "actionable": r["signal"].actionable,
               "regime": r["signal"].regime,
               "confirmed": r["signal"].confirmed,
               "components": r["signal"].components,    # détail par dimension
               "gate_allowed": r["gate"].allowed,
               "gate_reason": getattr(r["gate"], "reason", ""),
               "trade_allowed": r.get("trade_allowed"),
               "conviction_level": r["conviction"].level.value if r.get("conviction") else None,
               "conviction_score": r["conviction"].score if r.get("conviction") else None,
               "personality": r.get("personality").name if r.get("personality") else None,
               "futures_result": r.get("futures_result"),
           }
           for r in results
       ],
   }
   write_snapshot(Path("databases/live_snapshot.json"), snapshot)
   ```

3. **Adapter `dashboard_live.py`** (déjà existant, à la racine) pour qu'il
   lise ce fichier toutes les 1-2s au lieu de gratter les logs.

### Phase 3 — Data persistence par cycle

**But** : une ligne JSON par cycle dans `databases/cycle_data.jsonl` pour
analyse offline (quel score donne quels résultats, etc.).

**Sous-tâches** :

1. À la fin de chaque cycle, juste après `write_snapshot`, faire :
   ```python
   with open("databases/cycle_data.jsonl", "a", encoding="utf-8") as f:
       f.write(json.dumps(snapshot, default=str) + "\n")
   ```
2. Rotation : si le fichier > 50 Mo, renommer en `cycle_data.YYYYMMDD.jsonl`
   et repartir d'un fichier vide.
3. Créer `tools/analyze_cycles.py` : script qui lit le `.jsonl` et produit
   des stats (taux de signal actionable, distribution des scores, win-rate
   par régime, etc.).

### Phase 4 — Panneau de contrôle / tuning à chaud

**But** : pouvoir changer `GATE_MIN_SCORE_OVERRIDE`, `FORCE_TEST_EXECUTION`,
seuils SL/TP, etc. **sans redémarrer**.

**Sous-tâches** :

1. Créer `databases/runtime_config.json` rechargé en début de chaque cycle
   par `advisor_loop.py`. Ce fichier surcharge les variables d'env pour les
   paramètres "tunables".
2. Créer `tune.py` à la racine : petit script TUI ou web minimal qui lit/écrit
   `runtime_config.json`. Champs :
   - `GATE_MIN_SCORE_OVERRIDE` (slider 0-100)
   - `FORCE_TEST_EXECUTION` (toggle)
   - `EXEC_MAX_ORDER_USD` (input)
   - `EO_DD_VETO`, `EO_DD_MINIMAL`... (sliders)
   - `SIGNAL_MIN_SCORE` (slider)
3. Documenter dans le `README` que ces variables sont écrasées par
   `runtime_config.json` quand il existe.

---

## 4. Variables d'environnement importantes

| Var | Défaut | Effet |
|---|---|---|
| `BINANCE_API_KEY`, `BINANCE_API_SECRET` | — | Auth (déjà set dans `.env`) |
| `V9_INITIAL_CAPITAL` | 1000 | Fallback capital — **NE PAS UTILISER en run normal** |
| `SIGNAL_MIN_SCORE` | 70 | Seuil score minimum pour `actionable=True` |
| `GATE_MIN_SCORE_OVERRIDE` | 0 | Si > 0 et score >= cette valeur → force trade |
| `FORCE_TEST_EXECUTION` | false | Bypass meta/awareness/conviction/etc. |
| `EXEC_MAX_ORDER_USD` | 50 | Taille max d'un ordre |
| `V9_MAX_POSITION_WEIGHT` | 0.05 | % du capital par position |
| `EO_DD_VETO` | 0.10 | DD au-dessus duquel ExecutiveOverride met VETO |
| `EO_DD_RECOVERY` | 0.04 | DD pour sortir du VETO |
| `EXCHANGE_HEARTBEAT_S` | (à créer) | Fréquence du ping exchange |

Le mode test pour vérifier que tout marche :

```cmd
set GATE_MIN_SCORE_OVERRIDE=50
set FORCE_TEST_EXECUTION=true
.venv\Scripts\python.exe advisor_loop.py
```

Ou double-clic sur `run_test_mode.bat` (créé à la racine).

---

## 5. Pièges connus

1. **PowerShell vs cmd.exe** — `set VAR=valeur` ne marche pas en PowerShell.
   En PS il faut `$env:VAR = "valeur"`. L'utilisateur n'est pas familier
   avec la distinction. Préférer `.bat` quand possible.

2. **Erreur Binance `-1021` (timestamp drift)** — récurrente sur Windows si
   l'horloge n'est pas synchronisée. Le `.bat` `run_test_mode.bat` fait un
   `w32tm /resync /force` au démarrage.

3. **MEAN_REVERSION en `TRADING BLOQUE`** — quand le régime n'est pas favorable,
   `personality.order_size_factor=0`. Cela ramène `effective_order_size` à 0.
   L'execution_engine met alors le minimum Binance (`min_notional * 1.05`).
   Le `FORCE_TEST_EXECUTION` corrige ça en restaurant `order_size_usd`.

4. **`signal.actionable`** — c'est une `@property` (lecture seule), JAMAIS
   essayer de l'assigner. Si on veut "forcer" un signal, modifier le score
   ou utiliser `signal_to_execute` à part.

5. **Persistance peak_capital** — vérifié, aucune persistance problématique :
   - `ExecutiveOverride` : RAM uniquement
   - `SessionGuard` : RAM uniquement
   - `RiskEngineMVP` (`databases/mvp_risk_state.json`) : existe mais le
     fichier n'est pas créé chez l'utilisateur

6. **`mistake_memory.jsonl`** — peut générer des `BlockRule` permanentes
   après quelques pertes. Vide-le si tu veux repartir propre :
   `del databases\mistake_memory.jsonl`

---

## 6. Fichiers clés à connaître

| Fichier | Rôle |
|---|---|
| `advisor_loop.py` | Boucle principale, ~2100 lignes |
| `quant_hedge_ai/agents/execution/execution_engine.py` | Client CCXT |
| `quant_hedge_ai/agents/execution/live_signal_engine.py` | `SignalResult` + `LiveSignalEngine` |
| `quant_hedge_ai/agents/risk/executive_override.py` | Couche VETO globale |
| `quant_hedge_ai/agents/risk/global_risk_gate.py` | Gate score >= 70 |
| `quant_hedge_ai/agents/intelligence/conviction_engine.py` | Score conviction |
| `quant_hedge_ai/agents/intelligence/meta_strategy_engine.py` | Choisit la personnalité |
| `quant_hedge_ai/agents/intelligence/mistake_memory.py` | Apprentissage erreurs |
| `supervision/exchange_monitor.py` | Ping Binance |
| `supervision/self_healing_bot.py` | Restart ciblé |
| `observer_logs.py` | Tail logs en temps réel |
| `run_test_mode.bat` | Script de lancement avec env vars + resync horloge |
| `logs/advisor_loop.log` | Log principal |
| `databases/mistake_memory.jsonl` | Erreurs apprises |

---

## 7. Procédure de reprise recommandée

1. **Lire ce document en entier** avant de toucher au code.
2. Confirmer avec l'utilisateur qu'il veut bien commencer par la **Phase 1**
   (sa priorité absolue).
3. Lire les sections concernées des fichiers listés (`execution_engine.py`,
   `advisor_loop.py` lignes 1140-1170, `exchange_monitor.py`).
4. Implémenter Phase 1 comme décrit en section 3.
5. Tester en coupant le réseau.
6. Demander à l'utilisateur s'il veut enchaîner sur Phase 2.

**Ne pas** :
- Toucher à `SignalResult.actionable` (c'est une `@property`, en lecture seule)
- Réintroduire un fallback fixe dans `fetch_available_capital()`
- Lancer en LIVE (l'utilisateur teste sur Futures Demo, ne pas confondre)

---

## 8. Contact / contexte utilisateur

- L'utilisateur s'appelle Mathieu, il est francophone.
- Il préfère les explications concrètes, pas trop théoriques.
- Il utilise PowerShell par défaut — donner les `.bat` ou les commandes
  PS quand pertinent.
- Pour l'instant **tout est sur Binance Testnet + Futures Demo**, jamais
  en LIVE. Garder cette précaution.

Bonne reprise.
