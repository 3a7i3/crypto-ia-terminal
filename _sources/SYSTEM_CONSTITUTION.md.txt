# SYSTEM CONSTITUTION

> Version: 1.0 | Date: 2026-06-02 | Statut: CANONIQUE

Ce document contient les règles immuables du système.
Aucun agent, aucune mise à jour, aucune urgence ne peut les contourner.
Toute modification exige une revue explicite et un incrément de version.

---

## PRÉAMBULE

Ce système est un **AI Operating System financier autonome**.
Il n'est pas simplement un bot de trading.

Sa responsabilité va au-delà de la performance :
- Il doit être **explicable** — chaque décision peut être auditée.
- Il doit être **cohérent** — jamais dans un état impossible.
- Il doit être **survivable** — capable de fonctionner des mois sans intervention.
- Il doit être **traçable** — chaque arrêt a une cause identifiable en < 10 secondes.

---

## ARTICLE 1 — Autorité Unique de Trading

**Aucun ordre ne peut être envoyé à un exchange sans passer par `TradingAuthority.can_trade()`.**

- `TradingAuthority` est le seul juge de l'autorisation d'exécution.
- Toute demande d'arrêt passe par `TradingAuthority.request_halt(source, level, reason)`.
- Toute reprise passe par `TradingAuthority.request_resume(source, reason)`.
- Un arrêt est loggé avec : source, niveau, raison, timestamp UTC.
- Une reprise est loggée avec : source, état précédent, timestamp UTC.

**Violation → `TradingAuthorityBypassError` (non silencieuse).**

---

## ARTICLE 2 — Immutabilité du DecisionPacket

**Un `DecisionPacket` créé ne peut pas voir ses champs d'identité modifiés.**

Champs immuables après création :
- `packet_id`
- `created_at`
- `symbol`
- `timeframe`

La mutation d'état passe **uniquement** par `transition_to()`.
Toute mutation directe d'un champ figé est une violation.

**Enforcement : HARD — exception levée à la tentative d'écriture.**

---

## ARTICLE 3 — Traçabilité de Toute Reprise Manuelle

**Toute reprise manuelle du système (après SAFE_MODE ou EMERGENCY) doit être journalisée.**

Format obligatoire :
```json
{
  "event": "manual_resume",
  "operator": "<source>",
  "previous_state": "<état>",
  "reason": "<raison explicite>",
  "timestamp_utc": "<ISO 8601>",
  "authority_snapshot": { ... }
}
```

Le log doit être écrit dans `logs/governance_audit.jsonl` avant toute reprise effective.

---

## ARTICLE 4 — Traçabilité des Demandes SAFE_MODE / EMERGENCY

**Toute demande de mise en SAFE_MODE ou EMERGENCY doit être traçable.**

Format obligatoire dans `logs/governance_audit.jsonl` :
```json
{
  "event": "halt_requested",
  "source": "<agent|module>",
  "level": "SAFE_MODE|EMERGENCY",
  "reason": "<raison explicite>",
  "timestamp_utc": "<ISO 8601>",
  "active_halts_before": [...]
}
```

Un arrêt sans raison explicite est refusé par `TradingAuthority`.

---

## ARTICLE 5 — Explicabilité de Tout Ordre Exécuté

**Tout ordre exécuté doit pouvoir répondre à la question : "Pourquoi ?"**

Chaque ordre doit être associé à un `DecisionPacket` contenant :
- Les agents sources (`source_agents`)
- Le score de signal (`confidence`)
- La décision du `RiskGate` (`risk_score`, `veto`)
- La taille calculée (`allocation_pct`)
- L'historique des transitions (`state_history`)

Un ordre sans `DecisionPacket` attaché ne peut pas être exécuté.

---

## ARTICLE 6 — GlobalRiskGate Non Contournable

**Aucun ordre ne peut contourner le `GlobalRiskGate`.**

Le `GlobalRiskGate` est le seul point d'autorisation du sizing et du risque absolu.
Ses limites (`max_drawdown`, `max_daily_loss_usd`, etc.) sont modifiables uniquement
via `GlobalRiskGate.set_limit()`, jamais par injection directe.

**Violation → ordre rejeté silencieusement + alerte critique levée.**

---

## ARTICLE 7 — Source de Vérité Unique pour l'État Système

**Un seul objet représente l'état du système à tout instant.**

La hiérarchie canonique des états (du plus sûr au plus permissif) :

```
EMERGENCY   →  Arrêt total immédiat. Aucune lecture ou écriture exchange.
SAFE_MODE   →  Blocage total trading. Lecture exchange possible.
RESTRICTED  →  Trading suspendu. Positions existantes monitorées.
WARNING     →  Trading autorisé, taille réduite (50%). Surveillance accrue.
CLEAR       →  Fonctionnement nominal. Trading plein.
```

Tout agent qui lit l'état système lit depuis **`TradingAuthority.current_level`**.
Tout agent qui écrit l'état système écrit via **`TradingAuthority.request_halt()`**.

---

## ARTICLE 8 — Règles de Reprise Automatique

**Le système ne reprend JAMAIS le trading automatiquement depuis EMERGENCY.**

Depuis SAFE_MODE : reprise automatique possible après `silence_s` secondes sans nouvelles erreurs,
sous réserve que tous les agents de monitoring soient sains.

Depuis EMERGENCY : reprise **exclusivement manuelle** via opérateur ou Telegram.
La reprise doit être journalisée (voir Article 3).

---

## ARTICLE 9 — Santé des Agents Critiques

**Un ordre ne peut être exécuté si un agent critique est en état `UNHEALTHY`.**

Agents critiques (ordre de priorité) :
1. `GlobalRiskGate`
2. `SessionGuard`
3. `ExecutionEngine`
4. `OrderDeduplicator`

Un agent critique non-joignable = RESTRICTED minimum.
Deux agents critiques non-joignables = SAFE_MODE automatique.

---

## ARTICLE 10 — Interdiction de Secrets Hardcodés

**Aucune clé API, secret, mot de passe ou credential ne peut apparaître en clair dans le code.**

Toutes les credentials passent par les variables d'environnement (`.env` ou vault).
Toute violation détectée par un scanner de code = build bloqué.

---

## ANNEXE A — Niveaux d'Enforcement

| Niveau | Comportement |
|--------|-------------|
| `HARD` | Exception levée, jamais silencieux |
| `SOFT` | Valeur clampée ou None, appelant doit vérifier |
| `LOGGED` | Tracé mais non bloquant |

---

## ANNEXE B — Historique des Versions

| Version | Date | Auteur | Changement |
|---------|------|--------|------------|
| 1.0 | 2026-06-02 | System | Version initiale — 10 articles fondateurs |

---

*Ce document est la loi fondamentale du système. Il prime sur tout autre document.*
