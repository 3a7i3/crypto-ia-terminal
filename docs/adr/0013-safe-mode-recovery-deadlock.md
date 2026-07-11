# ADR-0013 — Deux points morts dans la machine d'état runtime (SAFE_MODE / RECOVERY)

- **Statut** : Accepté (validé par Mathieu, 2026-07-11)
- **Date** : 2026-07-11
- **Contexte** : Incident 2026-07-10/11 — `self_awareness` a placé le moteur
  en `SAFE_MODE` sur un échantillon de 5 trades post-restart, gel total
  pendant ~15h, sortie manuelle par `/RESUME` puis par redémarrage complet
  du process (`crypto-advisor.service`, 2026-07-11 05:59:13Z). Voir mémoire
  d'incident (session Claude Code, non versionnée) pour le détail
  chronologique complet.

## Contexte

### Ce qui s'est passé

Le 2026-07-10 14:43:57 UTC, `self_awareness` (`quant_hedge_ai/agents/intelligence/self_awareness_engine.py`)
a évalué un niveau `WARNING` et appelé `runtime_authority.request_safe_mode("self_awareness", ...)`
(`core/advisor_loop.py:3775`), verrouillant `RuntimeStateMachine` en `SAFE_MODE`.
Conséquence immédiate et complète : le gate G1 d'`analyze_symbol()`
(`core/advisor_loop.py:853-918`) court-circuite les 28 paires à chaque
cycle, **avant même l'appel au scanner de marché** — `prix=0.0`,
`n_1h=0`, `regime="unknown"` sont les valeurs par défaut du stub de
retour anticipé, pas la trace d'une panne de données. Le moteur est resté
dans cet état ~15h au total (14:43:57Z → redémarrage 05:59:13Z le
2026-07-11, ~183 cycles) — 150 cycles documentés au snapshot du
diagnostic (02:58Z, cycle 519 − cycle 369) —, l'invariante
`CAPITAL_GELE` (max=30) violée en continu.

Deux points morts distincts ont été traversés, chacun nécessitant une
intervention manuelle :

### Point mort n°1 — `SAFE_MODE` ne s'auto-lève jamais (voulu ; le défaut est le déclencheur)

`self_awareness` calcule ses dérives sur `self._trades` (une deque
alimentée par les trades fermés). Or `SAFE_MODE` bloque justement tout
nouveau trade — `self._trades` ne peut plus grossir, donc le niveau ne
peut jamais redescendre sous `WARNING` tout seul. Seule sortie : une
requête externe (`/RESUME` Telegram → `clear_all_safe_mode_requests()`,
`runtime_state_machine.py:217-227`) ou un redémarrage du process.

**Ce qui est un défaut ici, et ce qui ne l'est pas.** La halte-jusqu'à-
`/RESUME` est le comportement de sécurité *voulu* face à une dérive
réelle — un `self_awareness` qui bloque tout le moteur jusqu'à
confirmation opérateur n'est pas en soi un bug, c'est un circuit-breaker
qui fait son travail. Le défaut isolé ici est uniquement le
**déclencheur** : un `WARNING` levé sur un échantillon de 5 trades,
insuffisant pour distinguer bruit et dérive. La décision #1 (§ Décision)
corrige ce déclencheur ; elle ne rend pas — et ne prétend pas rendre —
`SAFE_MODE` auto-levable face à une vraie dérive sur échantillon
suffisant : ce serait un défaut de sécurité, pas un objectif de ce
document.

**Root cause précise du déclenchement initial**, vérifiée ligne à ligne
avec seulement ~5 trades en mémoire depuis le restart du 2026-07-09 :

- Win rate / Sharpe (`_check_performance_drift`, `self_awareness_engine.py:329-343`)
  : exclus mécaniquement — `RECENT_WINDOW=10` (défaut, ligne 85) > 5 trades,
  donc `baseline = list(self._trades)[:-10] or list(self._trades)`
  (ligne 332) retombe sur `baseline == recent` → `wr_drop = sh_drop = 0`.
- Market mismatch / regime instability (`_check_market_mismatch`,
  ligne 467-470) : exclus formellement par sa propre garde
  (`if len(self._trades) < self.RECENT_WINDOW: return signals`).
- Infra/latence : ne produit jamais `WARNING` directement (seulement
  `CAUTION`/`DANGER`, `_check_infra_drift`, ligne 515+).
- **`drawdown_acceleration`** (ligne 383-399) : **pas protégé par la même
  garde que win rate/Sharpe**. Il calcule `cumdd` sur `recent_pnls` (les
  seuls trades disponibles, ici 5) indépendamment de la taille de
  `baseline`. `DD_ACCEL_WARN=0.03` (3%, ligne 93) suffit à déclencher
  `WARNING` sur un enchaînement de pertes parmi 5 trades. C'est
  l'incohérence structurelle : la même fonction protège deux de ses
  quatre signaux par une garde de taille d'échantillon et laisse le
  troisième (`drawdown_acceleration`) sans protection équivalente.
- Alternative non exclue : `FREEZE_OVERRIDE_HALTS=3` (ligne 117-228,
  DANGER rétrogradé WARNING après 3 halts sans trade) — même conclusion
  quel que soit le chemin exact, le contexte de l'incident étant vide
  (`context: {}`, `logs/incidents/2026-07-10.jsonl`) et la dérive précise
  non journalisée (seul le message Telegram, non persisté, et la deque
  mémoire, perdue au restart, la portaient).

### Point mort n°2 — `RECOVERY` n'est pas une vraie sortie non plus

`/RESUME` (`_on_resume`, `core/advisor_loop.py:2891-2899`) appelle
`clear_all_safe_mode_requests()`, qui fait transitionner `SAFE_MODE` vers
`RECOVERY` — **jamais directement `NORMAL`**
(`runtime_state_machine.py:217-227`). Or `_POLICIES[RECOVERY]`
(ligne 44-50) a `can_trade=False` — le gate G1 continue donc de
court-circuiter tous les symboles exactement comme en `SAFE_MODE`, avec
les mêmes symptômes (`CAPITAL_GELE` continue d'incrémenter).

La seule transition `RECOVERY → NORMAL` est dans `report_ok()`
(ligne 147-176), conditionnée à
`now - self._recovery_started >= self._stability_s` (60s par défaut) —
**mais `report_ok()` n'est appelé nulle part en production**. Grep
exhaustif : seuls `quant_hedge_ai/runtime/chaos_orchestrator.py` (harnais
de tests chaos) et les tests unitaires l'appellent. `core/advisor_loop.py`
n'appelle que `runtime_authority.report_error("cycle_exception")`
(ligne 7150, sur exception de cycle) ; la façade `core/authority.py`
(`GovernanceKernel`, utilisée par le gate G1) n'expose que des lectures
(`can_trade`, `can_fetch`, `can_place_order`, `size_factor`, `rsm_state`,
`snapshot`). Conséquence vérifiée empiriquement le 2026-07-11 : après
`/RESUME`, le moteur est resté en `RSM:RECOVERY` sur au moins 2 cycles
supplémentaires (`CAPITAL_GELE` 175→176) sans aucune tendance à
graduer — seul un redémarrage complet du process (qui réinitialise
`RuntimeStateMachine.__init__` à `NORMAL`) a permis la reprise, vérifiée
à 05:59:13Z (`RSM state=NORMAL` au boot, prix/régimes réels dès le
premier cycle).

Ce même défaut condamne symétriquement `DEGRADED`/`CRITICAL → RECOVERY`
(ligne 163-166, même mécanisme `report_ok()`) — pas seulement
`RECOVERY → NORMAL`. Tout état dégradé non résolu par une requête externe
explicite est, en l'état actuel du code, un état terminal jusqu'au
prochain redémarrage.

### Défaut annexe trouvé en cours de diagnostic (hors décision, noté pour mémoire)

`scripts/deploy_vps.sh --restart core|advisor` ne fait pas
`systemctl restart` — il fait `pkill` ancré + relance `nohup` brute
(légataire d'avant la réconciliation systemd du 2026-07-05, ADR-0010).
Sur l'unité actuelle (`Restart=on-failure`,
`/etc/systemd/system/crypto-advisor.service`), un `pkill` qui ne produit
pas une sortie propre (code 0) risque de faire courir la relance
`nohup` du script contre le propre redémarrage automatique de systemd —
le survivant de la course sortirait du cgroup managé
(`/system.slice/crypto-advisor.service`), reproduisant la classe de
problème qu'ADR-0010 avait résolue. Le redémarrage du 2026-07-11 a
contourné ce risque en utilisant directement
`sudo systemctl restart crypto-advisor.service` sur le VPS. Correctif
proposé en Conséquences, non urgent (pas déclenché cette fois).

## Décision

### 1. Étendre la garde de taille d'échantillon à `drawdown_acceleration`

Dans `_check_performance_drift()` (`self_awareness_engine.py:329-343`),
faire porter la garde `len(recent) < 3 or len(baseline) < 3` (ligne 334)
sur le calcul du drawdown également, **et** durcir la condition pour
exiger un baseline structurellement indépendant plutôt qu'un fallback
identique à `recent` : remplacer la garde par
`len(self._trades) < self.RECENT_WINDOW` (le même seuil, la même forme
que la garde déjà en place dans `_check_market_mismatch`,
ligne 469 — cohérence interne du fichier, pas un nouveau concept). Avec
`RECENT_WINDOW=10` par défaut, aucune des quatre familles de dérive ne
pourra plus produire de signal avant 10 trades accumulés depuis le
dernier reset de la deque (restart ou purge explicite).

**Neutre pour win rate/Sharpe, ne resserre que le drawdown.** Remplacer
la garde ligne 334 par `len(self._trades) < RECENT_WINDOW` s'applique
aussi aux signaux win rate/Sharpe — mais ceux-ci ne peuvent déjà produire
un `drop≠0` en dessous de `RECENT_WINDOW` trades (le fallback
`baseline == recent`, ligne 332, force `wr_drop = sh_drop = 0` dans cette
zone). L'unification ne change donc leur comportement en rien ; elle ne
resserre que `drawdown_acceleration`, seul signal non protégé
aujourd'hui.

### 2. Appeler `report_ok()` une fois par cycle réussi

Dans la boucle principale de `core/advisor_loop.py`, au point symétrique
de l'appel `runtime_authority.report_error("cycle_exception")`
(ligne 7150) — c'est-à-dire sur le chemin de sortie normal d'un cycle qui
n'a pas levé d'exception — ajouter `runtime_authority.report_ok()`. Cela
restaure le comportement documenté par le docstring de
`RuntimeStateMachine` (« RECOVERY → silence confirmé, retour progressif
vers NORMAL ») pour les quatre transitions descendantes
(`SAFE_MODE`\* → `RECOVERY` déjà géré par requête explicite ; `RECOVERY
→ NORMAL`, `DEGRADED/CRITICAL → RECOVERY`, et leur enchaînement complet
vers `NORMAL`), sans changer aucun seuil ni aucune logique de décision de
trading — c'est un appel à une méthode déjà existante et déjà testée
(`tests/chaos/test_chaos_runtime_state.py`), jamais câblée en production.

**Pourquoi cet appel est sûr même câblé sur chaque cycle réussi** (deux
garanties vérifiées dans le code, pas supposées) :
- `report_ok()` ne vide jamais `self._errors` — seuls `clear_*` et
  `force_recovery()` le font ; il se contente d'`_evict()` par fenêtre
  temporelle (`window_s`). L'accumulation `DEGRADED`/`CRITICAL` reste
  donc intacte même appelé à chaque cycle : aucun risque de masquer une
  dégradation en cours.
- Appelé pendant que `SAFE_MODE` est actif avec au moins une requête en
  cours, il court-circuite sans effet (`runtime_state_machine.py:169-170`)
  — no-op garanti. Câbler l'appel sur le chemin normal du cycle est donc
  sûr même si un cycle s'exécute pendant qu'une requête `self_awareness`
  reste active.

**Comportement attendu après le fix, vérifiable empiriquement** :
`clear_all_safe_mode_requests()` pose `recovery_started = now` au moment
du `/RESUME` (`runtime_state_machine.py:226`, méthode plurielle réellement
appelée par `_on_resume()` — à ne pas confondre avec `clear_safe_mode_request()`
singulière, ligne 213-214, qui fait la même chose mais pour une seule
source). Comme
`stability_s=60s` est inférieur à la cadence de cycle (300s), le
**premier** `report_ok()` post-`/RESUME` (au cycle suivant) satisfait
déjà `≥60s` → transition immédiate vers `NORMAL`. Critère de
vérification du fix : **`/RESUME` suivi d'un cycle complet doit suffire à
observer `RSM:NORMAL`**, sans redémarrage.

Nuance de vérification, pour éviter un faux négatif au test en conditions
réelles : `report_ok()` étant câblé en fin de cycle (symétrique de
`report_error`), le cycle qui suit `/RESUME` démarre encore en
`RECOVERY` — G1 court-circuite, `prix=0` — et ne gradue vers `NORMAL`
qu'à sa fin. Les prix/régimes réels ne reviennent donc qu'au cycle
**suivant celui-là**. `RSM:NORMAL` s'observe à N+1 cycle après
`/RESUME`, la donnée réelle à N+2 — ne pas conclure à un échec du fix si
le tout premier cycle post-`/RESUME` affiche encore des zéros.

\* `SAFE_MODE` reste gouverné exclusivement par requêtes explicites
(`request_safe_mode`/`clear_safe_mode_request`), `report_ok()` n'y change
rien (`runtime_state_machine.py:168-174` — `SAFE_MODE` exige le double du
silence standard **et** l'absence de requêtes actives ; ce chemin existe
déjà et n'est pas modifié par cette décision).

### 3. `deploy_vps.sh --restart core` doit appeler `systemctl restart`

Remplacer le bloc `pkill` + `nohup` par
`ssh ... "sudo systemctl restart crypto-advisor.service"` (avec la même
vérification `pgrep` ancrée en sortie) pour la cible `core`, qui tourne
sous cette unité réconciliée depuis ADR-0010. Élimine la course avec
`Restart=on-failure` et garde le process dans son cgroup managé dans tous
les cas, pas seulement quand l'opérateur pense à taper la commande
systemd à la main.

**Précision d'implémentation (vérifiée sur le VPS, 2026-07-11,
`systemctl list-units --all --type=service`)** : seule la cible `core`
possède une unité systemd (`crypto-advisor.service`). La cible `advisor`
(bot d'observation passif racine) n'en a aucune — elle reste donc sur le
mécanisme `pkill` + `nohup` existant jusqu'à ce qu'elle soit elle-même
productionisée sous systemd, ce qui est hors périmètre de cet ADR (le bot
passif n'est pas le composant concerné par l'incident).

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| Relever `DD_ACCEL_WARN` (3%→X%) pour réduire la sensibilité sur petit échantillon | Modification d'un seuil existant — interdite par le gel fonctionnel (Scientific Debt Rule, CLAUDE.md) sans validation statistique préalable |
| Empêcher `self_awareness` d'appeler `request_safe_mode()` du tout | Supprime un mécanisme de sécurité fonctionnel pour un usage légitime (dérive réelle sur échantillon suffisant) — le problème est la garde de taille d'échantillon manquante sur un seul signal, pas le mécanisme lui-même |
| Ajouter un `force_normal()` / override manuel pour sortir de `RECOVERY` sans toucher à `report_ok()` | Traite le symptôme (comment sortir de `RECOVERY` cette fois) sans corriger la cause (`DEGRADED`/`CRITICAL` resteraient des états terminaux, `report_ok()` resterait mort en production) |
| Ne rien changer, documenter la procédure de redémarrage comme sortie normale | Chaque épisode futur coûterait à nouveau un redémarrage complet pour un défaut de robustesse identifié et compris — contraire à l'esprit de L3.5 (Scientific Intelligence Layer) qui suppose une supervision qui s'auto-corrige dans ses marges définies |

## Conséquences

**Positives :**
- `self_awareness` retrouve une garde de taille d'échantillon cohérente
  sur ses quatre familles de dérive — plus de gel total déclenchable sur
  N=5.
- `RECOVERY`/`DEGRADED`/`CRITICAL` redeviennent des états transitoires
  comme conçu, sans dépendre d'un redémarrage manuel pour graduer.
- Le correctif `deploy_vps.sh` ferme une classe de risque déjà identifiée
  et corrigée une fois côté systemd (ADR-0010) mais pas côté outillage de
  déploiement.

**Négatives / compromis :**
- Le correctif n°1 retarde légèrement la détection de dérive réelle après
  chaque restart (10 trades au lieu de 3 minimum actuel pour `drawdown_acceleration`)
  — compromis jugé favorable : un faux positif total (gel de 15h+) coûte
  bien plus cher à l'objectif N≥100 qu'un délai de détection de quelques
  trades.
- Le correctif n°2 change un comportement observable (le moteur
  graduera désormais seul après un incident, sans confirmation
  opérateur). Nuance sur `stability_s=60s` : à 300s/cycle, `RECOVERY`
  dure de toute façon toujours au moins un cycle complet — on ne peut pas
  graduer plus vite que la cadence elle-même, donc "60s est-il trop
  court" n'est pas la bonne question. La vraie question, à surveiller sur
  le premier épisode réel post-fix : un cycle complet sans erreur
  suffit-il comme preuve de santé, ou faut-il en exiger plusieurs avant
  `NORMAL` ?

**Règles induites :**
- Toute nouvelle famille de dérive ajoutée à `self_awareness_engine.py`
  doit passer par la garde `RECENT_WINDOW`-based commune, jamais un calcul
  isolé sur `recent` seul.
- `report_ok()`/`report_error()` sont désormais les deux seuls points
  d'entrée attendus depuis `core/advisor_loop.py` vers
  `RuntimeStateMachine` — tout nouveau code touchant au cycle principal
  qui voudrait signaler un état de santé doit passer par l'un des deux,
  jamais manipuler `_state` ou les requêtes `SAFE_MODE` directement.
- Ce document et ses correctifs doivent être validés explicitement par
  Mathieu avant implémentation (règle constitutionnelle ADR-0007 —
  gouvernance et calibration ne s'auto-approuvent jamais).
