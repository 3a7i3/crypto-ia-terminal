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

### 3.5 Vérifier la reprise

- **`pgrep -af 'core/advisor_loop\.py$'` — LA vérification qui compte.**
  `databases/live_snapshot.json` frais ne suffit PAS : `advisor_loop.py`
  (bot passif) écrit le même fichier avec la même cadence — un snapshot
  frais peut être produit par le mauvais process. Le pgrep ancré est le
  seul signal qui distingue vraiment les deux.
- `ls -l logs/advisor.lock` — repris par le nouveau PID (comparer avec
  `cat /proc/<PID>/status | grep Pid`, ou simplement `lsof logs/advisor.lock`).
- `curl -m 5 http://127.0.0.1:8080/` répond (health check interne du moteur).
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
