# ADR-0010 — Réconciliation VPS et leçons d'observabilité

- **Statut** : Accepté
- **Date** : 2026-07-05
- **Contexte** : Audit hybride du VPS (branches `main`/`feat/stack-unification`), incident moteur du 2026-07-05, manœuvre de réconciliation — voir `RECOVERY.md`, `tests/test_watchdog_vps.py`, branche `rescue/stack-unif-remains` (commit `eaf3834`)

## Contexte

Un audit de routine du VPS (repository sur `feat/stack-unification` depuis
le 2026-07-02, suite à un `git stash`/`checkout` jamais résolu) a révélé
que le moteur de trading réel (`core/advisor_loop.py`) tournait en mémoire
depuis le 2026-06-30, **déconnecté de son propre fichier source disparu du
disque** — Python ne recharge rien après import, donc aucun symptôme
visible tant que le process ne s'arrêtait pas.

Trois découvertes en cascade, chacune plus profonde que la précédente,
ont précédé la réconciliation :

1. Le script de déploiement (`scripts/deploy_vps.sh --restart`) et le
   watchdog de production (`watchdog_vps.py`, actif depuis le 2026-06-14)
   utilisaient tous deux un `pkill`/`pgrep -f "advisor_loop.py"` **sans
   ancrage** — un motif qui matche indifféremment le moteur réel
   (`core/advisor_loop.py`) et un bot d'observation passif homonyme
   (`advisor_loop.py`, racine). Un `--restart` ou un cycle
   `Restart=always` aurait pu remplacer silencieusement le moteur par
   l'observateur.
2. Le signal de vie historique du watchdog (fraîcheur de
   `databases/live_snapshot.json`) s'est révélé **incapable de distinguer
   les deux process** : le bot passif écrit le même fichier, avec la même
   structure et la même cadence.
3. Pendant la manœuvre de réconciliation elle-même, le premier geste
   (`kill -TERM` sur le watchdog) a tué le moteur réel **en cascade** —
   son cgroup était historiquement partagé avec `crypto_watchdog.service`
   (`KillMode=control-group`, comportement par défaut de systemd), un fait
   déjà documenté mais dont l'implication précise n'avait pas été
   anticipée avant l'action. Détecté à la vérification de sortie de
   l'étape 1 du runbook, sans conséquence (`Pos: 0` confirmé dans
   `paper_trades.jsonl` au moment exact de l'arrêt).

Une quatrième découverte, indépendante de l'incident, est survenue au
même moment : un tag d'audit de déploiement (`deploy-20260704-1837`)
attestait un transfert de fichiers qui n'avait en réalité eu lieu qu'à
60 % (`scp` retournait un code de sortie 0 sans avoir écrit sur le disque
distant).

## Décision — quatre invariants

### 1. Un processus par cgroup, jamais deux processus du projet dans une unit partagée

Toute unit systemd gérant un process du projet doit avoir un cgroup dédié.
Aucune coexistence historique ou accidentelle (héritage de lancement
manuel, `nohup` sous un shell déjà rattaché à un autre cgroup) ne doit
être tolérée au-delà de sa découverte. Conséquence directe de l'incident
du 2026-07-05 : un `kill` ciblé sur un process peut tuer un autre process
du même cgroup sans lien logique avec lui, par le seul effet du
`KillMode=control-group` par défaut de systemd.

**Vérification obligatoire avant tout arrêt de service en production** :
`cat /proc/<PID>/cgroup` pour chaque processus concerné, jamais après.

### 2. Un indicateur n'a de valeur que si on sait exactement quel système il observe

Deux signaux d'observabilité distincts, découverts la même semaine, ne
mesuraient pas ce qu'on croyait :

| Indicateur | Croyance | Réalité |
|---|---|---|
| Fraîcheur de `live_snapshot.json` | Preuve que le moteur réel tourne | Le bot passif écrit le même fichier — preuve seulement qu'*un* process tourne |
| `Pos:` dans les rapports Telegram / heartbeat ALIVE | Exposition réelle en paper trading | Suit `pos_manager`, non synchronisé avec `MexcSimulator` — peut afficher `0` avec des positions réellement ouvertes (`paper_trades.jsonl`) |

Dans les deux cas, le signal existait, semblait fiable, et ne l'était pas
pour la question précise qu'on lui posait. Aucun indicateur ne doit être
utilisé comme preuve d'identité ou d'état sans que le code qui l'alimente
ait été lu et compris — la plausibilité d'un signal n'est pas une preuve
de sa pertinence.

### 3. Un processus dont le source a disparu du disque est déjà mort sans le savoir

Un process qui tourne encore n'est pas une preuve que son code est
reproductible ou redémarrable. Tant que `core/advisor_loop.py` était
absent du disque VPS, le moteur en mémoire fonctionnait normalement —
mais aucun mécanisme (systemd, watchdog, script de déploiement) n'aurait
pu le relancer correctement en cas d'arrêt, crash ou redémarrage GCP. La
vivacité d'un process ne dispense jamais de vérifier que son binaire
source existe, est syntaxiquement valide, et correspond à ce que les
mécanismes de supervision relanceraient réellement.

**Garde induite** : tout mécanisme de relance automatique (watchdog,
`--restart`) doit vérifier l'existence et la validité (`ast.parse`) du
fichier cible avant toute tentative — refus bruyant préférable à un
remplacement silencieux par un process différent ou par rien du tout.

### 4. Un tag d'audit ne vaut que ce que sa vérification prouve

Un mécanisme d'audit (tag git, log de déploiement) qui enregistre un
succès sans l'avoir vérifié indépendamment n'est pas un audit — c'est une
déclaration d'intention. `deploy-20260704-1837` attestait un transfert
complet ; 2 fichiers sur 5 n'avaient pas été écrits. La correction n'a
pas consisté à supprimer silencieusement le tag, mais à le documenter
comme erreur corrigée (`RECOVERY.md` § 5) avant suppression — l'historique
d'audit doit rester honnête sur ses propres défaillances passées, pas
seulement sur celles du système qu'il audite.

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| `systemctl mask` pour neutraliser les unités obsolètes | Échoue à deux reprises sur systemd 249 pour des fichiers non-symlink existants (`--force` inopérant dans ce cas précis) — l'archivage (`mv` vers `~/legacy-units-YYYYMMDD/` + `daemon-reload`) atteint le même résultat (`systemctl status` répond "could not be found") sans lutter contre l'outil |
| Réanimer le code figé en mémoire (`782688a`) plutôt que basculer sur `main` | Impossible par construction — le fichier source de ce commit n'existe plus sur le disque VPS ; la seule voie a toujours été vers l'avant |
| Fusion complète `main` ↔ `feat/stack-unification` | `feat/stack-unification` n'avait que 2 commits uniques (un frontend React non lié à la logique de décision) au-delà d'un point commun ancien — un nettoyage borné, pas une fusion, était le geste juste |
| Corriger `watchdog_vps.py` pour cibler `core/advisor_loop.py` sans mode alerte-seule | Le fichier étant absent du disque à ce moment, une relance automatique aurait échoué en boucle — le mode ALERTE SEULE (`RESTART_DISABLED_UNTIL_RECONCILIATION`) était la seule option honnête tant que la réconciliation n'était pas faite |

## Conséquences

**Positives :**
- Le correctif watchdog déployé le 2026-07-04 (ciblage ancré, mode
  alerte-seule) a été validé en conditions réelles par l'incident du
  2026-07-05 lui-même : le process respawné a correctement alerté plutôt
  que de relancer le mauvais service.
- État final vérifiable point par point : un moteur (`crypto-advisor.service`),
  un watchdog (`crypto-watchdog.service`), cgroups dédiés, aucune ambiguïté
  de nommage, `main`/`origin/main` synchronisés, dataset continu (marqueur
  de provenance en JSONL append, 0 position perdue).
- L'état hybride pré-réconciliation est intégralement préservé
  (`rescue/stack-unif-remains`), aucune décision n'a été prise sous
  contrainte de temps sur le sort du frontend React ou du bot passif.

**Négatives / compromis :**
- Le désaccord `pos_manager`/`MexcSimulator` reste un ticket ouvert,
  bloquant pour Sprint C (une page Overview lisant `live_snapshot.json`
  mentirait structurellement sur l'exposition réelle).
- L'origine de la bascule de format dans `black_box.jsonl` (2026-05-28,
  antérieure et sans lien avec cet incident) reste à investiguer — hypothèse
  à vérifier en priorité : changement de writer documenté plutôt que
  corruption.
- Le durcissement du VPS (sudo `NOPASSWD: ALL`, clé SSH GitHub de compte
  plutôt que deploy key scopée) reste à faire, prévu avec le TLS de
  Sprint B.

**Règles induites :**
- Toute nouvelle unit systemd gérant un process du projet est créée avec
  son propre cgroup, jamais rattachée à une unit existante par commodité.
- Tout indicateur d'observabilité cité dans une décision opérationnelle
  doit être tracé jusqu'au code qui l'écrit avant d'être considéré comme
  preuve.
- Tout mécanisme de relance automatique vérifie l'existence et la
  validité syntaxique de sa cible avant d'agir (`scripts/vps_restart.sh`,
  `watchdog_vps.py`, `scripts/deploy_vps.sh --restart`).
- Tout mécanisme d'audit de déploiement vérifie son propre succès par un
  moyen indépendant de celui qu'il audite (SHA256 local vs distant,
  `scripts/deploy_vps.sh`) avant de produire une preuve d'audit.
