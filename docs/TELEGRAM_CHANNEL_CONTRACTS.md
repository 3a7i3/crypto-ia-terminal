# TELEGRAM_CHANNEL_CONTRACTS — contrats de canal

> **Statut : contrat normatif. Aucun code n'a été modifié pour l'écrire.**
> Établi le 2026-08-05. Fréquences et câblages **mesurés**, jamais supposés —
> voir [TELEGRAM_AUDIT_REPORT.md](TELEGRAM_AUDIT_REPORT.md) pour la méthode.
>
> Ce document précède l'Event Router et le conditionne. Un routeur construit
> sans contrats amplifierait le désordre au lieu de le résoudre : il aurait
> besoin de savoir quoi envoyer où, et cette information n'existe nulle part
> ailleurs que dans les habitudes accumulées du code.

---

## 0. Ce qu'un contrat engage

Chaque canal déclare six choses. Les trois premières disent ce qu'il *est* ; les
trois dernières le rendent **vérifiable** — sans elles, un contrat n'est qu'une
intention.

| Champ | Rôle |
|---|---|
| **Mission** | *Une seule* question à laquelle le canal répond |
| **Sources autorisées** | D'où vient légitimement sa donnée |
| **Événements reçus** | Ce qu'il accepte |
| **Événements interdits** | Ce qu'il refuse, **et où cela appartient** |
| **Niveau d'urgence** | Ce qui justifie de réveiller un humain |
| **Fréquence maximale** | Plafond au-delà duquel le canal devient du bruit |

**Règle de conflit.** Une donnée n'a qu'un seul canal propriétaire. Si deux
contrats la revendiquent, le contrat est en faute — pas le code.

---

## 1. Matrice de routage — source unique de vérité

C'est la table qu'un futur Event Router devra implémenter. Toute émission qui
n'y figure pas est hors contrat.

| Donnée | Propriétaire unique | Aujourd'hui émise par |
|---|---|---|
| Santé infra (API/DB/TG/Market) | ① rapport_automatique | ① **et** ④ |
| Gouvernance scientifique (N canonique, gates) | ① rapport_automatique | ① |
| Equity / cash simulé | ② PaperArena | ④ **et** ⑤ **et** `[ALIVE]` |
| Positions ouvertes | ② PaperArena | ④ **et** ⑤ |
| Événements de trade (entrée/sortie) | ② PaperArena | **aucun** — cf. § 8 |
| KPI simulation (WR, PF, DD, Sharpe) | ② PaperArena | ① **et** ⑤ |
| Vue humaine agrégée | ③ mon_portfolio | ⑤ |
| Univers, régimes, tendance | ④ QuantCrypto | ① **et** ④ **et** ⑤ |
| Scores, actionnables, candidats | ④ QuantCrypto | ④ **et** ⑤ |
| Meta-strategy, confidence, mode | ④ QuantCrypto | ④ |
| Seuil effectif, deltas, oscillation | ⑤ Behavior | ⑤ |
| Soldes réels exchange | ⑥ compte réel | ④ **et** ⑥ |

Douze lignes, **huit en conflit**. C'est la mesure du désordre actuel.

---

## 2. ① @rapport_automatique_bot — *System Health & Scientific Status*

**Mission.** « Est-ce que la machine fonctionne correctement, et où en est la
preuve scientifique ? » — jamais « que fait le marché ».

**Sources autorisées.** `system_intel_reporter.build_report`,
`tools/cri_calculator` (N canonique), `scripts/prelive_gate`, sondes runtime
(uptime, RAM, latence exchange), `scripts/data_quality`.

**Événements reçus.** `HEALTH_SNAPSHOT` · `HEALTH_DEGRADED` ·
`GOVERNANCE_MILESTONE` (seuil N franchi, gate ouverte) · `EXPERIMENT_STATUS` ·
`NEXT_ACTION`.

**Événements interdits.** Distribution des régimes (→ ④) · comptage
signaux autorisés/bloqués (→ ④) · liste de paires (→ ④) · KPI de performance
(→ ②) · equity (→ ②).

**Niveau d'urgence.** `HEALTH_DEGRADED` = **haut** (réveille). Le reste = bas.

**Fréquence maximale.** 1 briefing / 6 h. Une dégradation peut interrompre ce
plafond ; un retour à la normale, non — il attend le briefing suivant.

*Mesuré :* `_send_intel` (`advisor_loop.py:1059`), appelé `:7186`.
Silencieux si non configuré, **sans repli** — comportement correct.

---

## 3. ② @PaperArena_bot — *Capital & Execution Simulator*

**Mission.** « Que fait mon capital simulé ? »

**Sources autorisées.** `MexcSimulator` (positions, capital, trades fermés),
`paper_trading/recorder`, `databases/paper_trades.jsonl`.

**Événements reçus.** `TRADE_OPENED` · `TRADE_CLOSED` · `POSITION_SNAPSHOT` ·
`EQUITY_SNAPSHOT` · `SIMULATION_KPI` (WR, PF, DD, Sharpe, N).

**Événements interdits.** Santé infra (→ ①) · scanner et régimes (→ ④) ·
candidats non tradés (→ ④) · soldes réels (→ ⑥) · comportement du seuil (→ ⑤).

**Niveau d'urgence.** `TRADE_OPENED`/`TRADE_CLOSED` = moyen (temps réel, sans
réveil). `SIMULATION_KPI` = bas.

**Fréquence maximale.** Événements de trade : **sans plafond** — ils sont rares
(~10/jour mesurés) et c'est le seul canal où le temps réel a un sens.
Snapshots : 1 / heure.

> **⚠ Précondition bloquante.** Ce canal **n'existe pas** : ni token ni
> `chat_id` dans `.env`, présent uniquement dans `.env.example`. Le contrat est
> écrit, il n'est pas applicable. Créer le bot passe par BotFather — action
> opérateur. Tant qu'il manque, `TRADE_OPENED`/`TRADE_CLOSED` n'ont **aucune
> destination légitime** (cf. § 8).

---

## 4. ③ @mon_portfolio_bot — *Human Dashboard*

**Mission.** « En un coup d'œil, où j'en suis ? » — pour un humain pressé, pas
pour un analyste.

**Sources autorisées.** Les mêmes que ②, **agrégées**. Ce canal ne calcule
rien : il résume ce que ② possède.

**Événements reçus.** `DAILY_DIGEST` uniquement — capital, variation du jour,
nombre de positions, niveau de risque, phase.

**Événements interdits.** Toute liste (signaux, paires, positions détaillées) ·
métriques internes · logs moteur · santé infra.

**Niveau d'urgence.** Bas. Ce canal n'alerte jamais.

**Fréquence maximale.** 2 / jour. Au-delà, il redevient un flux et perd sa
raison d'être.

*Mesuré :* `CommandCenterBot._report_loop`
(`capital_deployment/command_center_bot.py:1546`), cadence
`report_interval_h = 1.0` par défaut (`:1138`) — **24 messages/jour, soit 12 ×
le plafond contractuel**. Tourne dans le processus `advisor_loop` (`:3611`),
pas en service séparé.

---

## 5. ④ @QuantCrypto_bot — *Market Intelligence Engine*

**Mission.** « Que raconte le marché ? »

**Sources autorisées.** Scanner d'univers, `MarketRegimeClassifier`,
scoring des signaux, `MetaStrategyEngine`.

**Événements reçus.** `MARKET_SNAPSHOT` (univers, régime dominant) ·
`ACTIONABLE_CANDIDATES` · `STRATEGY_STATE` (personnalité, confidence, mode).

**Événements interdits.** Equity et cash (→ ②) · positions (→ ②) · soldes réels
MEXC/Binance (→ ⑥) · santé infra (→ ①) · comportement du seuil (→ ⑤).

**Niveau d'urgence.** Bas — le marché n'est pas une alerte.

**Fréquence maximale.** 1 / 30 min. Aujourd'hui : **1 / cycle = 1 / 5 min**,
soit 6 × le plafond.

**Frontière avec ① et ⑤ — le point de friction principal.**

| Question | Canal |
|---|---|
| « Le marché est en bear trend » | ④ — état du **monde** |
| « La machine tourne, N=189 » | ① — état de la **machine** |
| « Le seuil est passé de 64 à 66 » | ⑤ — état de la **politique** |

Trois objets distincts que le panneau actuel mélange dans un seul message.

---

## 6. ⑤ Rapport_ia-crypto-quant — *Behavior Research Monitor*

**Mission.** « Comment la politique de décision de la machine se comporte-t-elle ? »
Ce n'est pas un canal de trading : c'est un instrument scientifique.

**Sources autorisées.** `BehavioralStabilityMonitor`, `GlobalRiskGate.explain_threshold`,
détecteur de transitions de régime.

**Événements reçus.** `BEHAVIOR_SNAPSHOT` (seuil min-max, écart-type, flips,
transitions, oscillation, mismatch, état) · `REGIME_TRANSITION_DIGEST` ·
`THRESHOLD_MUTATION`.

**Événements interdits.** Trades · equity · candidats · santé infra.

**Niveau d'urgence.** `state=degraded` ou `osc=HIGH` = moyen. Le reste = bas.

**Fréquence maximale.** 1 snapshot / 4 h ; 1 digest de transitions / h.

*Mesuré :* **seul canal déjà conforme.** `cycle % 50` = 4 h 10
(`advisor_loop.py:6558`), digest plafonné à 3600 s. Corrigé par `1ce42c4`
et `5209b83`.

---

## 7. ⑥ Bot compte réel — *Real Account Observer*

**Mission.** « Que contiennent réellement mes comptes exchange ? »

**Sources autorisées.** Lectures API MEXC/Binance en lecture seule (ADR-0019).

**Événements reçus.** `REAL_BALANCE_SNAPSHOT` · `EXECUTION_MODE_CHANGE`
(STANDBY ↔ LIVE).

**Événements interdits.** Tout ce qui est simulé (→ ②) · marché (→ ④).

**Niveau d'urgence.** `EXECUTION_MODE_CHANGE` = **haut**. Snapshot = bas.

**Fréquence maximale.** 1 / heure. *Mesuré :* `REAL_BOT_REPORT_EVERY = 12`
cycles = 1 h (`advisor_loop.py:799`) — **déjà conforme**.

---

## 8. Ce que le contrat laisse en suspens

**Les événements de trade sont GELÉS — décision opérateur du 2026-08-05.**

Le contrat les attribue à ②, qui n'existe pas. Trois issues étaient ouvertes :
créer @PaperArena_bot, les confier temporairement à ③ en acceptant qu'il viole
son plafond, ou geler. **Le gel a été retenu**, dans l'attente de la création du
bot par l'opérateur.

État exact du code, à jour :

| élément | fichier | état |
|---|---|---|
| `format_entree` / `format_sortie` | `paper_trading/mexc_simulator.py` | écrits, testés |
| `MexcSimulator._journal()` | idem | écrit, absorbe toute exception |
| paramètre `trade_journal_fn` | idem | présent, **non fourni** |
| câblage dans `advisor_loop` | `core/advisor_loop.py` | **retiré volontairement** |
| tests | `tests/test_telegram_trade_journal.py` | 12, verts |

**Dégeler tient en une ligne** : passer `trade_journal_fn=<émetteur PaperArena>`
à la construction du simulateur.

> **Pourquoi cette dormance est déclarée deux fois** — ici et en commentaire au
> site de construction. Un chemin écrit et non exécuté qui n'est *pas* documenté
> devient un piège : ce dépôt en compte déjà quatre (modules `v2_*`, `seal()`,
> `market_context`, message `SORTIE` sur `pos_manager.on_close`). Chacun a coûté
> une investigation pour être retrouvé. Un cinquième, créé sciemment et laissé
> muet, serait une faute — pas une dette.

**Anomalie mesurée, indépendante du contrat.** Aucun événement de trade
n'atteint Telegram aujourd'hui : le message `SORTIE` existe
(`advisor_loop.py:4088`) mais sur le callback `pos_manager.on_close` (`:4103`),
alors que les trades sont ouverts et fermés par `MexcSimulator` (`:711`, `:881`).
Le chemin instrumenté n'est pas le chemin exécuté — motif rencontré quatre fois
dans ce dépôt.

---

## 9. Comment vérifier qu'un contrat est respecté

Un contrat invérifiable est une décoration. Trois contrôles, réalisables sans
Event Router :

1. **Propriété unique.** Pour chaque ligne de la matrice § 1, un seul émetteur.
   Vérifiable par lecture des sites d'appel.
2. **Plafond de fréquence.** Compter les messages émis sur 24 h par canal et
   comparer au plafond déclaré. Aujourd'hui : ③ à 24/jour pour un plafond de 2,
   ④ à 288/jour pour un plafond de 48.
3. **Absence de repli silencieux.** `_telegram_behavior` (`:1022`) retombe sur
   `TELEGRAM_CHAT` si son `chat_id` est vide : un canal mal configuré déverse
   sur un autre **sans aucun signal**. Un contrat ne peut pas tenir sous un
   repli muet — à supprimer avant toute mise en application.

---

## 10. Ordre d'application

1. Créer @PaperArena_bot, ou trancher le § 8.
2. Supprimer le repli silencieux (§ 9.3) — sinon les contrats sont contournables.
3. Appliquer les interdits de la matrice § 1, canal par canal, en commençant par
   les huit conflits.
4. Aligner les fréquences sur les plafonds.
5. **Alors seulement**, construire l'Event Router : il aura une table à
   implémenter au lieu d'habitudes à deviner.
