# Dashboard — État global

## Snapshot : 2026-06-07

- Programme actif : **ALPHA_DISCOVERY_100** (burn-in 100 trades)
- Priorité : correction bug restore positions → débloquer burn-in

---

## Feux

| Composant | Statut |
|---|---|
| Service systemd crypto-advisor | 🟢 ACTIF — PID 1149698 |
| Telegram alertes | 🟢 CONFIGURÉ — nouveau token 07/06 |
| Gouvernance G0→G8-E | 🟢 VERT — 63/63 tests |
| Burn-in 100 trades | 🔴 BLOQUÉ — 0 fermés (bug restore) |
| MexcSimulator restore positions | 🔴 BUG — positions perdues au restart |
| PaperTradeRecorder intégration | 🟠 DETTE — non branché dans MexcSimulator |
| Spam Telegram REJETE | 🟠 À CORRIGER |
| runtime_config.json override | 🟠 À NETTOYER |
| Self-heal exchange reconnect | 🟠 DETTE P2 |
| ExecutionRouter refactor | 🔴 GELÉ post burn-in |
| Capital réel | 🔴 PAS PRÊT |

---

## KPI burn-in (2026-06-07)

| KPI | Valeur | Cible |
|---|---|---|
| Trades fermés (N) | 0 | 100 |
| Trades ouverts JSONL | 4 | — |
| Capital simulateur | $100 (en mémoire) | $100 |
| Profit Factor | N/A (N=0) | ≥ 0.8 |
| Win Rate | N/A | ≥ 40% |
| Jours écoulés | J3 | J30–J100 |

---

## Positions paper actives (JSONL — non surveillées après restart)

| Symbole | Side | Entry | Taille | Age |
|---|---|---|---|---|
| INJ/USDT | BUY | $4.5250 | $30.00 | ~20 jours ⚠️ |
| BTC/USDT | BUY | $62477 | $1.50 | ~3 jours |
| SOL/USDT | BUY | $68.88 | $1.30 | ~3 jours |
| ETH/USDT | BUY | $1764.72 | $1.10 | ~3 jours |

> ⚠️ Ces positions ne sont PAS monitorées par le simulateur actif (bug restore).
> TP/SL ne se déclenchera pas sur ces positions.

---

## Prochaines actions prioritaires

1. **URGENT** — Fix MexcSimulator restore positions depuis JSONL (bug bloquant burn-in)
2. Vérifier statut paper_runner (PID 946985) — doublon possible
3. Brancher PaperTradeRecorder dans MexcSimulator (record OPEN/CLOSE)
4. Nettoyer spam Telegram REJETE messages
5. J8 (11 juin) — Bilan N trades fermés → décision semaine 2

---

## Gate décision finale J14 (18 juin)

```
N >= 100 ET PF >= 0.8 ET Sharpe >= 0  → BURNIN_CALIBRATION_V3 (capital réel)
N >= 100 ET PF < 0.8                   → Analyser causes, NE PAS libérer capital
N < 100 à J14                          → Prolonger observation
```

---

## Liens

- [[../02_Execution/Session_2026-06-07]]
- [[../00_Hub/Reprise_2026-06-09]]
- [[../01_Roadmap/ROADMAP_2SEMAINES_2026-06-04]]
