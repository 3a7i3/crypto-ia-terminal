# RECOVERY.md — Procédure de reprise après incident VPS

Document créé le 2026-07-04, suite à un audit en lecture seule ayant révélé
que le moteur de trading réel tourne en mémoire, déconnecté de son propre
fichier source disparu du disque. Ce document décrit comment reprendre la
main SANS relancer par réflexe le mauvais processus.

**Ne PAS suivre cette procédure avant qu'un incident réel ne survienne**
(crash, redémarrage GCP, `systemctl stop` accidentel). Tant que
`core/advisor_loop.py` PID (voir `logs/advisor.lock`) tourne, ne touche à
rien — l'arrêter est le seul moment où l'interruption deviendrait réelle.

---

## 0. Pourquoi ce document existe

Le 2026-07-02 07:05 UTC, le dépôt VPS a basculé de `main` vers
`feat/stack-unification` (stash `vps-temp-before-stack-unification` jamais
résolu depuis). `core/advisor_loop.py` — le moteur de trading réel —
**n'existe plus sur cette branche**. Le process qui l'exécute (PID variable,
identifiable via `logs/advisor.lock`) tourne depuis le 2026-06-30 07:28,
**avant** ce switch : il vit uniquement en mémoire (Python ne recharge pas
le code après import). Tant qu'il tourne, aucun problème. **S'il s'arrête,
rien ne peut le relancer correctement en l'état** — voir § 2.

## 1. Ne PAS faire en premier réflexe

- **Ne pas relancer `advisor_loop.py` (racine) en croyant relancer le
  moteur.** C'est un bot d'observation passif (aucune position, aucun
  ordre — confirmé par docstring + logs). Il tourne déjà en permanence sous
  `crypto_advisor.service` (avec underscore) et ce n'est pas un problème en
  soi — mais ce n'est pas le moteur.
- **Ne pas faire confiance au redémarrage automatique.** Trois mécanismes
  existent sur ce VPS et AUCUN ne restaure correctement le moteur
  aujourd'hui (détail § 2) :
  - `crypto-advisor.service` (avec tiret) — unit systemd correcte
    (`ExecStart=.../core/advisor_loop.py`), mais **inactive depuis
    2026-06-30 07:27** (arrêtée manuellement, jamais relancée) et
    échouerait immédiatement si démarrée aujourd'hui (fichier absent).
  - `crypto_watchdog.service` — watchdog Python (`watchdog_vps.py`) actif
    depuis le 2026-06-14, **toujours en mémoire avec l'ancien code** (Python
    ne recharge rien après import, comme le moteur lui-même). Le code sur
    disque a été corrigé le 2026-07-04 (ciblage ancré `core/advisor_loop\.py$`,
    mode ALERTE SEULE tant que `RESTART_DISABLED_UNTIL_RECONCILIATION=1`,
    refus si fichier absent/syntaxe invalide — voir `tests/test_watchdog_vps.py`)
    mais **ce correctif ne prend effet qu'au rechargement du process**, prévu
    lors de la manœuvre de réconciliation, pas avant. **Jusque-là, le
    comportement réellement actif reste l'ancien** : avec
    `WATCHDOG_USE_SYSTEMD=1` (`.env`), une tentative de reprise appellerait
    `systemctl restart crypto_advisor.service` — le service avec underscore,
    qui lance le bot passif, pas le moteur. `watchdog_vps.py` croirait avoir
    réparé le système alors qu'il aurait remplacé le moteur par l'observateur.
  - **Découverte aggravante** : `advisor_loop.py` (racine, bot passif) écrit
    `databases/live_snapshot.json` avec exactement la même structure et la
    même cadence que `core/advisor_loop.py`. La détection historique du
    watchdog (fraîcheur de ce fichier) ne permet donc pas, à elle seule, de
    distinguer moteur réel et bot passif — un fait resté vrai tant que le
    process en mémoire n'est pas rechargé avec le correctif du 2026-07-04
    (qui ajoute une vérification par `pgrep` ancrée, indépendante du contenu
    du snapshot).
  - `deploy_vps.sh --restart` — corrigé le 2026-07-04 (ciblage exact,
    refus si le fichier cible est absent), mais **désactivé en bloc**
    (`RESTART_DISABLED_UNTIL_RECONCILIATION=1`, `.env` — source unique,
    relue aussi par `watchdog_vps.py`) tant que ce document n'a pas servi
    de base à une vraie réconciliation de branche.
- **Piège de nommage à connaître** : `crypto-advisor.service` (tiret) et
  `crypto_advisor.service` (underscore) sont deux unités différentes. La
  première vise le moteur réel, la seconde le bot passif. Ne pas les
  confondre dans l'urgence — vérifier le nom exact avant toute commande
  `systemctl`.

## 2. Diagnostic — l'état exact au 2026-07-04

| Élément | État | Détail |
|---|---|---|
| Process moteur réel | vivant, mémoire seule | cwd=`core/advisor_loop.py`, détient `logs/advisor.lock`, cgroup=`crypto_watchdog.service` (héritage historique, pas un lancement voulu) |
| `core/advisor_loop.py` sur disque VPS | **absent** | supprimé par le checkout du 2026-07-02 vers `feat/stack-unification` |
| `crypto-advisor.service` | inactive (dead) | ExecStart correct, mais échouerait — fichier absent |
| `crypto_advisor.service` | active (running) | lance le bot passif racine — fonctionne, mais ce n'est pas le moteur |
| `crypto_watchdog.service` | active (running) depuis 3 semaines, **code corrigé sur disque mais pas rechargé** | en mémoire : `USE_SYSTEMD=1` → relance `crypto_advisor.service` (mauvais service) en cas de coupure détectée. Sur disque (2026-07-04) : ciblage ancré + mode alerte seule, dormant jusqu'au rechargement coordonné |
| `crypto-api.service` (port 8000) | active (running) | expose `api_server.py` publiquement — voir action port 8000, prioritaire et séparée de ce document |
| `crypto-dashboard.service` (port 8501) | active (running) | Streamlit obsolète (ADR-0009), loopback seulement, pas de risque réseau |
| `crypto-feed.service` | failed depuis 3 semaines | sans rapport avec cet incident, pas de quoi urgent |

## 3. Procédure de reprise (à exécuter dans l'ordre, seulement si le moteur est réellement arrêté)

### 3.1 Préserver l'état avant de toucher à quoi que ce soit

```bash
cd /home/mathieuhasard111/crypto_ai_terminal
git status --short > /tmp/vps_state_before_recovery_$(date +%Y%m%d%H%M).txt
git stash list >> /tmp/vps_state_before_recovery_$(date +%Y%m%d%H%M).txt
```

Ne PAS faire `git stash` ou `git checkout` avant d'avoir cette trace — l'état
hybride actuel (feat/stack-unification + fichiers main déployés dessus +
stash `vps-temp-before-stack-unification` non résolu) est lui-même une
preuve utile pour la réconciliation à venir.

### 3.2 Basculer sur `main`

```bash
git stash push -u -m "recovery-$(date +%Y%m%d%H%M) — état hybride pré-reprise"
git checkout main
git pull origin main
```

Le stash existant (`vps-temp-before-stack-unification`, non résolu depuis le
2026-07-02) reste dans la pile — ne pas le drop, ne pas le pop. Il sera traité
lors de la réconciliation complète, pas en urgence.

### 3.3 Vérifier le code avant de le lancer

```bash
test -f core/advisor_loop.py && echo "présent" || echo "ABSENT — ne pas continuer"
python3 -c "import ast; ast.parse(open('core/advisor_loop.py', encoding='utf-8').read()); print('syntaxe OK')"
```

Vérifié en local (hors VPS) le 2026-07-04 sur `main` HEAD : **syntaxe
valide**. La comparaison complète avec le code figé en mémoire depuis le
30 juin (commit `782688a`) montre une différence purement additive et
passive — observabilité (Decision Event Bus, RejectionStore, RegretScheduler,
tous gated par feature flags avec repli sur le comportement historique) et
durcissement ADR-0007 (`suggest_threshold_adjustment` retourne toujours 0
sauf `FEATURE_AUTO_CALIBRATION=true`, jamais appelé par le moteur de toute
façon). **Aucune divergence de logique de décision** — relancer sur `main`
est scientifiquement neutre pour la continuité du dataset.

### 3.4 Relancer le moteur

```bash
sudo systemctl start crypto-advisor.service    # unité avec TIRET — ExecStart=core/advisor_loop.py
sleep 15
sudo systemctl status crypto-advisor.service --no-pager
```

Si l'unité échoue pour une raison indépendante du fichier manquant (env,
dépendances), fallback manuel documenté dans l'unité elle-même :

```bash
nohup .venv/bin/python3 core/advisor_loop.py < /dev/null >> logs/advisor.log 2>&1 &
```

**Note (2026-07-08) :** `logs/advisor.log` n'est alimenté QUE par ce fallback
manuel. Sous `crypto-advisor.service` (cas normal), systemd capture
stdout/stderr via journald — le fichier reste à 0 octet même moteur vivant et
sain, ce n'est PAS un signe de panne. Pour consulter les logs en
fonctionnement normal :

```bash
sudo journalctl -u crypto-advisor.service --no-pager -n 100
sudo journalctl -u crypto-advisor.service --since "10 min ago" --no-pager
```

### 3.5 Vérifier la reprise

- **`pgrep -af 'core/advisor_loop\.py$'` — LA vérification qui compte.**
  `databases/live_snapshot.json` frais ne suffit PAS : `advisor_loop.py`
  (bot passif) écrit le même fichier avec la même cadence — un snapshot
  frais peut être produit par le mauvais process. Le pgrep ancré est le
  seul signal qui distingue vraiment les deux.
- `ls -l logs/advisor.lock` — repris par le nouveau PID (comparer avec
  `cat /proc/<PID>/status | grep Pid`, ou simplement `lsof logs/advisor.lock`).
- ~~`curl -m 5 http://127.0.0.1:8080/`~~ — **obsolète, retiré 2026-07-08** :
  aucun endpoint HTTP de ce type n'existe dans `core/advisor_loop.py` (vérifié
  par grep sur tout le repo). Remplacé par les deux items déjà présents
  ci-dessus (pgrep ancré) et ci-dessous (mtime snapshot) — suffisants et déjà
  utilisés en pratique lors de la reprise du 2026-07-08.
- `stat -c %y databases/live_snapshot.json` — timestamp récent, en
  complément du pgrep ci-dessus, jamais à sa place.
- Message Telegram de démarrage reçu (canal `TELEGRAM_CHAT_ID`).
- `sudo systemctl status crypto_watchdog.service` — une fois rechargé avec
  le code du 2026-07-04, ses logs confirment `core/advisor_loop.py` détecté
  vivant (et non plus seulement un snapshot frais).

## 4. Ce que ce document NE couvre PAS

- La résolution du stash bloqué (`hypothesis_registry.yaml` / `EXP-001.yaml`)
  et la récupération des deux commits uniques à `feat/stack-unification`
  (`342c618`, `cf4d857` — un frontend React `ScientificView`/`ScoresView` et
  les endpoints `/api/scientific` associés dans `api_server.py`) — objet de
  la réconciliation complète à planifier séparément, pas d'une reprise
  d'urgence.
- Le renommage de `crypto-advisor.service` / `crypto_advisor.service` pour
  éliminer l'ambiguïté — recommandé lors de la réconciliation.
- **Le rechargement du watchdog en production.** Le code corrigé
  (`watchdog_vps.py`, `scripts/vps_restart.sh`, `RESTART_DISABLED_UNTIL_RECONCILIATION`)
  est déployé sur le disque VPS depuis le 2026-07-04 mais volontairement
  PAS rechargé — le process en mémoire (PID actif depuis le 2026-06-14)
  continue de tourner avec l'ancien comportement jusqu'à la manœuvre de
  réconciliation, où `sudo systemctl restart crypto_watchdog.service` (ou
  équivalent) doit être une étape explicite et coordonnée, pas un effet de
  bord du déploiement.

## 5. Incident corrigé — faux tag d'audit `deploy-20260704-1837`

Le déploiement du correctif watchdog (2026-07-04, 18:37 UTC) a affiché
`Transfert OK` et créé/poussé le tag `deploy-20260704-1837` alors que
**2 des 5 fichiers (`watchdog_vps.py`, `scripts/vps_restart.sh`) n'avaient
en réalité pas été transférés** — `scp` a retourné un code de sortie 0 sans
avoir réellement écrit sur le disque distant (cause probable : aléa réseau/
multiplexage SSH, non élucidé précisément). Détecté par vérification
manuelle du contenu déployé (mtime + `grep`), pas par `deploy_vps.sh`
lui-même.

**Correctifs appliqués** :
- `scripts/deploy_vps.sh` vérifie désormais chaque fichier par SHA256
  (local vs distant) après le transfert — le tag n'est créé que si 100%
  des fichiers sont confirmés identiques. Un nouveau déploiement a été
  relancé et vérifié manuellement : les 5 fichiers sont bien présents et
  corrects (tag `deploy-20260704-2002`, désormais fiable puisque vérifié
  indépendamment de la nouvelle logique qu'il valide).
- Le tag `deploy-20260704-1837` a été **supprimé** (local + `origin`) —
  il attestait un transfert partiel, il ne doit pas rester dans l'historique
  comme preuve d'un déploiement complet qu'il n'a pas été. Cette note
  documente la suppression : rien n'est réécrit en silence.
- Le tag `deploy-20260704-2002` reste l'unique preuve valable du
  déploiement du correctif watchdog de cette date.

## 6. Réconciliation exécutée — 2026-07-05, état final

La manœuvre décrite en creux dans ce document a été exécutée dans la nuit
du 2026-07-05, avec un incident en cours de route qui a validé — de la
pire façon possible mais sans dommage — exactement le risque que ce
document existait pour prévenir.

**Ce qui s'est passé pendant la manœuvre** : le premier geste (`kill -TERM`
sur le PID du watchdog, 429) a immédiatement tué le moteur réel (PID
1456244) en cascade — son cgroup était historiquement partagé avec
`crypto_watchdog.service` (`KillMode=control-group` par défaut de systemd),
un fait documenté § 2 mais dont l'implication précise (un `kill` sur le
watchdog balaie tout son cgroup) n'avait pas été anticipée avant l'action.
Détecté à la vérification de sortie de l'étape 1, jamais avant — leçon
gravée : **toujours `cat /proc/<PID>/cgroup` pour chaque processus avant
le moindre kill.** Aucune position perdue (`Pos: 0` confirmé dans
`paper_trades.jsonl` — les OPEN sans CLOSE correspondant — au moment exact
de l'arrêt), et **le correctif watchdog déployé plus tôt le 2026-07-04 a
fonctionné correctement en conditions réelles** : le process respawné par
`Restart=always` a détecté le moteur mort et déclenché le mode ALERTE
SEULE (`ENGINE_DEAD_NO_AUTO_RESTART`, `supervision/watchdog_audit.jsonl`)
au lieu de relancer le mauvais service.

**État final** :
- Moteur sur `main@8ad76e4`, unit `crypto-advisor.service`, cgroup dédié
  `/system.slice/crypto-advisor.service` (confirmé — plus aucun partage
  de cgroup possible).
- Watchdog : nouvelle unit dédiée `crypto-watchdog.service` (tiret, cgroup
  propre `/system.slice/crypto-watchdog.service`), code du 2026-07-04
  (ciblage ancré, mode armé — `RESTART_DISABLED_UNTIL_RECONCILIATION=0`
  dans `.env` VPS).
- Trois unités historiques (`crypto_advisor.service`, `crypto_watchdog.service`,
  `watchdog_crypto.service` — trois noms pour deux rôles) archivées dans
  `~/legacy-units-20260705/` sur le VPS, retirées de `/etc/systemd/system/`
  (`systemctl mask` a échoué à deux reprises sur ce systemd 249 pour des
  fichiers non-symlink — l'archivage résout le même besoin sans lutter
  contre l'outil : `systemctl status` répond désormais "could not be found").
- État hybride pré-réconciliation (`feat/stack-unification` + stash bloqué
  + les deux commits uniques `342c618`/`cf4d857`) intégralement préservé
  sur la branche `rescue/stack-unif-remains` (commit `eaf3834`, poussée sur
  `origin` — clé SSH dédiée du VPS reconfigurée à cette occasion,
  `core.sshCommand` scopé au dépôt ; le remote HTTPS avec jeton placeholder
  `TON_TOKEN_ICI` n'avait jamais fonctionné). Décision sur le frontend React
  (`ScientificView`/`ScoresView`) reportée à froid, contre `sdos_terminal/`.
- Marqueur de provenance scientifique écrit en JSONL append (`databases/black_box.jsonl`
  et `logs/decisions/2026-07-05.jsonl`) : `decision_type: RESTART`, SHA
  avant/après (`782688a` → `8ad76e4`), cause de l'arrêt (non propre, cgroup),
  0 position perdue, et les 3 premiers trades post-réconciliation
  (XRP/BNB/BTC, 04:19:43–04:20:00 UTC) comme borne de reprise du dataset.
- Sauvegarde complète pré-manœuvre : `~/pre-reconciliation-20260705.tar.gz`
  (databases/, cache/, .env, lock), SHA256 noté ; forensique de l'arrêt
  dans `~/engine-death-forensics-20260705.txt` ; stash rescue dans
  `~/stash-rescue.patch`.

**Deux découvertes de fond, au-delà de l'incident du soir** :

1. **`databases/live_snapshot.json` (`Pos:` affiché dans les rapports
   Telegram et le heartbeat ALIVE) ne reflète PAS l'exposition réelle en
   paper trading** — il suit un système de tracking (`pos_manager`)
   différent et non synchronisé avec celui de `MexcSimulator`
   (`paper_trading/mexc_simulator.py`), qui écrit les positions réellement
   ouvertes dans `paper_trades.jsonl`. Le F1 de cette nuit (vérifier
   `Pos: 0` avant la fenêtre de maintenance) était juste sur le fond —
   confirmé a posteriori par dépouillement de `paper_trades.jsonl` — mais
   sa méthode était défaillante : le snapshot peut afficher `0` avec des
   positions réellement ouvertes. **Toute vérification future d'exposition
   doit se faire sur `paper_trades.jsonl` (OPEN sans CLOSE correspondant),
   jamais sur `live_snapshot.json`.** Ticket bloquant pour Sprint C : une
   page Overview qui afficherait le `Pos:` du snapshot mentirait
   structurellement sur l'exposition réelle.
2. **Symétrie avec la leçon du bot passif** (§ 1 — un heartbeat qui ne
   prouvait pas l'identité du process vivant) : deux signaux d'observabilité
   distincts, découverts la même semaine, qui ne mesurent pas ce qu'on
   croyait. Leçon à graver dans l'ADR de débrief de cette réconciliation :
   *un indicateur n'a de valeur que si on sait exactement quel système il
   observe.*
