# LAB-01 — environnement autonome de développement et simulation

Statut : **plan et code préparés, testés localement ; rien d'installé, rien observé sur l'hôte.**
Décision de Mathieu (2026-10-15) : A validée comme étape locale ; B à **préparer**, installation **non autorisée** pour le moment ; C écartée.
Parents : #445 (passerelle d'opérations privilégiées), #432 ; issue #447 ; roadmap #285 ; garde #286 **active** (rien ici ne la lève).
Audit : [LAB_01_AUDIT_VPS_20261015.md](LAB_01_AUDIT_VPS_20261015.md). Commandes : [LAB_01_OPERATOR_COMMANDS.md](LAB_01_OPERATOR_COMMANDS.md). G3 publishers reste une tâche distincte.

## 1. Ce qui est démontré aujourd'hui (testé localement)
Cycle `données synthétiques → signal → risque → DecisionPacket → simulation PAPER → événements → API → interface` : code `lab01/`, tests `tests/lab01/` (69).
Il réutilise `core.decision_packet.DecisionPacket` et `execution_simulator` sans les modifier ; il ne touche ni Advisor, ni PPL, ni FIN, ni stratégies/seuils actifs.

| Scénario | Données | Issue attendue | Critères explicites (verdict PASS/FAIL) |
|---|---|---|---|
| `accepted_closed` | seed 11, vol 15 bps | `POSTMORTEM_ANALYZED`, PnL synthétique | risque APPROVED, ORDER_FILLED, POSITION_OPENED/CLOSED, aucune erreur, chaînes intègres |
| `risk_rejected` | seed 11, vol 150 bps | `REJECTED`, `VOLATILITY_ABOVE_LIMIT` | RISK_REJECTED avec observé > limite et justification ; aucun ordre ni position |
| `execution_error` | scénario 1 + panne injectée au 1er ordre | `FAILED`, `SIMULATED_EXCHANGE_TIMEOUT` | EXECUTION_ERROR visible et tracé ; aucun fill, position ni PnL |

Le risque n'est jamais assoupli : mêmes limites dans les trois scénarios, seul le jeu de données change le verdict. Chaque événement porte `experiment_id`, `trace_id`, la provenance SYNTHETIC et une horloge synthétique ; les événements sont chaînés par hachage.
Le PnL du LAB est synthétique : ni vérité FIN, ni lifecycle PPL, ni entrée Research. Aucun retour LAB → Research/production.

**Reproductibilité — ce qui l'est et ce qui ne l'est pas.** Sont identiques **octet par octet** (testé : rejeu, inter-processus, paquet autonome) : `events.jsonl`, `result.json`, `bars.json`.
**Ne le sont pas** : `packet.json` (le vrai `DecisionPacket` horodate ses transitions à l'heure murale) et `manifest.json` (`wall_clock_utc`, `git_head`, `python`, `platform`). L'expérience dans son ensemble n'est donc **pas** identique octet par octet ; ces deux fichiers sont exclus des empreintes, déclarés comme tels dans le manifeste (`reproducibility`) et `packet.json` n'est pas exporté.

Mesures locales (sandbox, Python 3.13) : cycle ≈ 0,2 s, ≈ 22 Mo RSS, ≈ 170 Ko d'artefacts. **Non mesuré sur l'hôte** (Python 3.11, systemd 249).

## 2. Autonomie réelle : trois niveaux distincts
| Niveau | Qui, où | Ce que cela permet | État |
|---|---|---|---|
| 1. Développement autonome | l'IA, dans un workspace non privilégié (sandbox cloud/CI ; sur l'hôte, un espace de préparation sans droits tel que `scratch/` de #445) | écrire le code, lancer `python -m lab01 run|verify`, produire paquet et empreintes ; **aucun sudo, aucun accès à la production** | **réel aujourd'hui** (hors hôte) |
| 2. Exécution confinée | unités LAB (`lab01-run`, `lab01-export`, `lab01-api`) sous l'utilisateur `lab01` | rejouer les scénarios sous plafonds, sans réseau, sans secret | préparée, **non installée** ; le démarrage d'une unité reste réservé à l'opérateur |
| 3. Installation | l'opérateur, par commit épinglé et staging root | créer l'utilisateur, le volume, les unités | préparée, **non autorisée** |

Ce que cela n'est pas : le compte `lab01` (nologin) et les commandes `sudo` de l'opérateur **ne constituent pas un accès autonome pour les IA** ; il n'existe aujourd'hui aucun moyen pour une IA de lancer le niveau 2.
**Chemin admis par le connecteur, sans sudo pour l'IA** (préparé, non activé) : l'IA dépose une *demande* (`request.json`, données seulement, commit complet et empreintes, `not_an_authorization: true`) dans l'espace de #445 ; l'opérateur l'approuve et l'exécute en un geste (étage A de #445, catalogue désactivé) ; l'IA lit ensuite les **rapports exportés** (§5) avec son compte d'observation `chatgpt-ro`, en lecture seule. Opérations candidates : `lab01.apply` (installation) puis `lab01.run` (démarrer run + export). Aucune ne dépend de la passerelle pour le premier cycle ; leur qualification relève de #445.

## 3. Comparaison des architectures
| | A. Local puis hébergement léger | B. LAB limité sur le VPS | C. Environnement distinct |
|---|---|---|---|
| Coût | 0 supplémentaire (bac à sable + CI existants) ; hébergement léger **non chiffré**, requis seulement pour consulter à distance | 0 marginal ; plafond initial 256 Mo / 25 % d'un cœur / 64 Mo de disque | récurrent, **non estimé** ; aucun budget supposé |
| Contraintes | pas d'accès hôte : preuves « testées localement » seulement | 2 vCPU, sans swap, Advisor sans plafond ; exception #286 pour toute unité ; noyau et E/S partagés | nouvelle surface (accès, mises à jour, sauvegardes) |
| Risque production | nul | réduit par cgroup, identité dédiée, volume borné, réseau refusé ; **non nul par construction** | nul |
| Ce que ça prouve | logique, reproductibilité, refus | + isolation et plafonds **observés sur l'hôte** | isolation sans cohabitation |
**Décision : A faite ; B préparée, non autorisée ; C écartée** (mesures : ≈ 22 Mo, 0,2 s, bibliothèque standard seule donc aucune préparation de dépendances ni réseau).
Passage à C si : OOM noyau relevé par le bloc 0, PSI cpu `some` avg60 > 10 % pendant un essai, besoin d'importer des copies de production, besoin de réseau sortant, ou refus de l'exception #286.

## 4. LAB sur le VPS (option B) — conception préparée, non installée
- **Identité** : `lab01`, utilisateur système nologin, sans sudo, sans groupe additionnel, sans clé SSH.
- **Espaces** : `/srv/lab01/release` (root, paquet vérifié) ; **volume dédié de taille fixe** : image ext4 de 64 Mo (`/var/lib/lab01/lab01.img`) montée sur `/srv/lab01/data` (`nodev,nosuid,noexec`), contenant `runs/` (lab01 0700, privé) et `reports/` (lab01 0755, fichiers 0644). `/srv/lab01/token` : root:lab01 0640. Rien sous `/home/mathieu`, `/opt/crypto-ai-terminal`, `/srv/claude-audit`. Branche distincte `claude/project-thread-c2x3i9` → PR brouillon.
- **Plafonds cumulés** (`lab01.slice`) : `MemoryHigh=192M`, `MemoryMax=256M`, `MemorySwapMax=0`, `CPUQuota=25%`, `TasksMax=64`, `IOWeight=10` ; par unité : 64 processus, 256 fichiers, pas de core, `LimitFSIZE=4M` (export).
- **Services indépendants** : `lab01-run` (oneshot, sans réseau), `lab01-export` (oneshot, sans réseau), `lab01-api` (loopback 127.0.0.1:18090). Aucune dépendance `Requires/Wants/After/BindsTo/PartOf/OnFailure` vers la production, aucun `EnvironmentFile`, aucune section d'installation (jamais lancé au boot).
- **Réseau** : exécution et export = `PrivateNetwork=yes`, `IPAddressDeny=any`, `AF_UNIX` seul ; API = `IPAddressDeny=any` + `IPAddressAllow=127.0.0.0/8 ::1`. Dans le code : `deny_network()` refuse connexion et DNS pendant le cycle.
- **Authentification** : l'API **refuse de démarrer sans jeton valide**, même en loopback (≥ 32 caractères, jeu restreint, fichier non accessible à « autres ») ; il n'existe aucun mode sans authentification. Le jeton n'est jamais dans un argument de processus (§7 : en-tête lu par `curl -H @fichier`).
- **Aucune clé exchange, aucun ordre réel** : `lab01` n'a accès à aucun secret ; le LAB refuse de démarrer si une variable d'environnement ressemble à un secret (noms seulement) ; le paquet ne contient que `lab01`, `core.decision_packet`/`lifecycle`, `execution_simulator`, `observability.json_logger`.
- **Données** : synthétiques seulement ; aucun montage de production. Tout import = copie autorisée, bornée, identifiée et vérifiée, sous gate distincte.
- **Préparation vs exécution** : préparation = paquet déterministe construit hors hôte, **commit épinglé** (40 caractères) ; exécution = unités sans réseau. Aucune dépendance à installer : le seul accès réseau est le `git clone` de l'opérateur.

## 5. Matrice des permissions
`runs` est **privé** (lab01 0700) : `chatgpt-ro` ne le lit pas. L'observateur lit uniquement `reports/`, produit par `lab01-export` après contrôle.
| Acteur | Release | `runs` (privé) | `reports` | Jeton | Arbre production | Secrets / `.env` | Réseau sortant | Unités de production | Exchange |
|---|---|---|---|---|---|---|---|---|---|
| `lab01-run` | R | **RW** | refusé | refusé | refusé | aucun | refusé | aucun lien | aucun |
| `lab01-export` | R | R | **RW** | refusé | refusé | aucun | refusé | aucun lien | aucun |
| `lab01-api` | R | R | — | R | refusé | aucun | refusé (loopback) | aucun lien | aucun |
| `lab01` (compte) | R | RW | RW | R | refusé (0750) | aucun | non contraint hors unité | aucun droit | aucun |
| `chatgpt-ro` (observateur) | R | **refusé** (0700) | **R** | **refusé** | refusé | refusé | — | lecture seule | aucun |
| Opérateur `mathieu` (sudo) | installe | R | R | RW | habituel | habituel | habituel | habituel, non utilisé par le LAB | habituel |
| IA (autorité d'exécution) | **aucune** : pas de sudo ; ses actions passent par une demande approuvée par l'opérateur | | | | | | | | |
**Export nettoyé** (`lab01 export`) : liste blanche `result.json`, `events.jsonl`, `manifest.json` (sans `platform` ni `git_head`) ; `packet.json` et `bars.json` exclus ; refus et rapport visible (`rejected`) si la chaîne est invalide, la provenance n'est pas SYNTHETIC, un lien symbolique ou un fichier trop gros est rencontré, ou une chaîne de production/jeton/secret apparaît ; écriture atomique, droits posés explicitement. L'export n'élargit ni `runs`, ni l'accès au jeton, ni aux données de production.

## 6. Ressources, bornes et garanties
- **Relevé ponctuel, pas une garantie** : 7,7 Go « disponibles » mesurés une fois le 2026-10-15 à 06:12Z ; la valeur varie (Advisor ≈ 6,9 Go, sans plafond, sans swap).
- **Plafond mémoire initial proportionné** : 22 Mo mesurés (hors hôte) × ≈ 10 de marge (interpréteur de l'hôte, fils de l'API) = **256 Mo** (`MemoryHigh` 192 Mo), non 2 Go. Ne le relever que sur mesure faite sur l'hôte. CPU 25 % d'un cœur (le cycle dure ≈ 0,2 s), 64 tâches.
- **Disque, borne réellement appliquée** : volume de **64 Mo** monté `noexec` ; le LAB ne peut pas le dépasser (échec visible `ENOSPC`, jamais d'éviction automatique de preuves). Si le montage échoue, `apply` s'interrompt. En complément, garde applicative : `lab01 run` refuse de démarrer au-delà de 32 Mo d'artefacts (`LAB_QUOTA_EXCEEDED`).
- **Rétention** : par défaut, aucune suppression. `lab01 prune --keep N` **liste** les candidats (dry-run) ; `--apply` est un acte explicite de l'opérateur ; seuls des dossiers nommés comme une expérience sont concernés (jamais `reports`, `_logs`, ni liens symboliques). Les preuves sont conservées après retrait (§7).
- **Garanties** : les limites cgroup et le volume **réduisent** le risque ; ils **ne garantissent pas** l'absence d'impact sur la production (même noyau, 2 cœurs, cache disque, E/S et périphérique loop partagés). Seuils d'abandon : variation du PID ou de `ActiveEnterTimestamp` d'Advisor/API pendant un essai, PSI cpu `some` avg60 > 10 %.

## 7. Installation et retrait (source préparée, rien exécuté)
Détail et commandes : [LAB_01_OPERATOR_COMMANDS.md](LAB_01_OPERATOR_COMMANDS.md). Ordre : bloc 0 (0a sans privilège, 0b privilégié, séparés) → bloc 1 (empreintes) → autorisation écrite → bloc 2 (**staging root**) → bloc 3 (`apply`) → bloc 4 (refus, exécution, export, API) → bloc 5 (retrait).
- **Commit complet épinglé**, jamais une branche mutable ; vérifié par `git rev-parse HEAD`.
- **Staging root protégé** : le code d'installation est copié dans `/root/lab01-staging/<commit>` (0700) puis **revérifié depuis ce répertoire** (`verify-staging` : empreinte du manifeste publiée, `sha256sum -c`, aucun fichier en trop, propriétaire root, non inscriptible) avant toute exécution.
- **Environnement de l'appelant non transmis** (aucune variable) : paramètres explicites (`--auth`, `--bundle`, `--bundle-sha256`, `--manifest-sha256`).
- **Commit épinglé dans le paquet** : le fichier `COMMIT` fait partie du manifeste ; `verify-staging` exige `--commit`, le compare au fichier et au nom du dossier de staging.
- **Préconditions (`preflight`, lecture seule, rejouées par `apply`)** : commandes requises, systemd ≥ 249, support loop, espace libre (image + preuves), mémoire disponible à l'instant, port 18090 libre, compte `lab01` absent ou conforme, volume non monté depuis autre chose, aucune unité existante différente écrasée, aucune dépendance de production. Un échec arrête `apply` **avant toute écriture**.
- **Échec partiel et reprise** : étapes `user, dirs, image, units, mount, data, release`, chacune idempotente et atomique (image : fichier `.partial` puis `mv` ; release : dossier `.partial` puis `mv` ; unités : fichier temporaire puis `mv`). Journal append-only `/var/lib/lab01/install.journal` (0600). Un échec laisse un état **inerte** (aucune unité activée ni démarrée, rien d'écrit si le montage manque) ; `status` relève l'état réel ; relancer le même `apply` reprend ; `remove` conserve les preuves.
- **Retrait qui conserve les preuves** : avant tout arrêt, `remove` écrit `/var/lib/lab01/evidence/<horodatage>/` (archive `runs`+`reports`, unités installées, journal, état, empreinte de l'image) avec `MANIFEST.sha256` **vérifié** ; si cela échoue (espace, outil), **rien n'est retiré**. Ensuite : arrêts, démontage, unités retirées. **L'image, les expériences, l'utilisateur, le journal et les preuves sont conservés.** `--purge` est refusé ; toute suppression des données est une décision séparée. Rollback honnête : il retire ce que le LAB a ajouté, il ne restaure pas l'état antérieur ; `verify` le constate.

## 8. Tests
- **Positifs** (locaux, 69 au total) : scénarios et critères, chaînes, reproductibilité (fichiers déclarés identiques octet par octet), API, export lisible aux bons droits, interface (bannière SYNTHETIC ; liste rendue depuis l'API dans un Chromium headless, détail non parcouru).
- **Refus** (locaux) : chaque règle de risque ; altération d'événement ; réseau refusé puis restauré ; secrets refusés sans révéler la valeur ; sorties sous l'arbre de production ; **API sans jeton / jeton court / invalide / fichier de jeton lisible par tous : refus de démarrer** ; POST/PUT/DELETE/PATCH → 405, chemins hors liste → 404, sans jeton → 401, artefact manquant → 503 ; export : chaîne altérée, chaîne interdite, lien symbolique rejetés ; **staging : fichier modifié, fichier en trop, empreinte erronée refusés** ; `--purge` refusé ; quota ; `prune` sans effet par défaut ; unités sans dépendance de production ni secret ; audit : erreur de journal = INDÉTERMINÉ (jamais 0), refus et troncature visibles, aucune lecture d'unité.
- **Isolation effective sur l'hôte** (`lab01_host_tests.sh` → `host_isolation_tests.py`, **non exécutés**) : une directive présente dans un fichier n'est pas une preuve. Le lanceur relit les propriétés des **fichiers d'unité prévus** (`unit_props.py`, source unique : aucune restriction écrite à la main), les applique à une unité transitoire dans `lab01.slice`, et des sondes **dans le processus** observent l'effet réel (`NoNewPrivs`, capacités, seccomp, W^X, espaces de noms, SUID, familles d'adresses, interfaces réseau, IPAddressDeny, volumes en lecture seule, chemins masqués, `/tmp` privé, `/dev` réduit, `/proc/sys`, cgroupfs, limites, `UMask`, plafonds cgroup de la slice, environnement sans secret, volume `noexec`). **Chaque refus est confronté à un essai témoin sans la directive** : refusé avec, autorisé sans = `OK` ; refusé aussi sans = `INDÉTERMINÉ` (refus non attribuable, par ex. droits Unix) ; autorisé avec = `KO`. Un chemin LAB absent est un `KO`. Les unités **installées** doivent être identiques octet pour octet aux fichiers du paquet vérifié. Les directives non sondées (`RestrictRealtime`, `ProtectClock`, délais, `RequiresMountsFor`) sont **listées avec leur motif**, jamais supposées ; une directive ajoutée à une unité sans sonde ni exemption fait échouer le test de couverture. `--functional` lance en plus les vraies commandes `ExecStart` sous ces propriétés (run, export, API avec jeton : 200 / sans jeton : 401).
- **Limite des tests locaux de l'isolation** : sans systemd ici, seule l'émulation de trois restrictions (`NoNewPrivileges`, capacités, `PrivateNetwork`) est exercée localement (verdicts `OK` attribuables) ; les autres directives y ressortent `KO`, ce qui démontre que le lanceur ne prend pas une directive écrite pour une preuve. L'effet réel sous systemd 249 reste **à observer sur l'hôte**.
- **Défaut réel trouvé par cette relecture** : un chemin inexistant dans `InaccessiblePaths` fait échouer le démarrage de l'unité (échec de l'espace de noms) ; les chemins étrangers au LAB portent désormais le préfixe `-` (ignorés s'ils n'existent pas) ; un test l'impose.
- **Relevé OOM** (`lab01_oom_probe.sh`) : états `ACCÈS_REFUSÉ`, `RÉTENTION_INSUFFISANTE`, `AUCUNE_CORRESPONDANCE`, `ÉVÉNEMENTS`, `ERREUR`, jamais confondus ; compteur noyau `oom_kill` depuis le démarrage (lisible sans privilège) en plus du journal ; tests locaux avec un faux `journalctl`.

## 9. États des preuves
| Composant | Préparé | Testé localement | Installé | Observé sur l'hôte |
|---|---|---|---|---|
| Cycle, scénarios, critères, API/interface, export, rétention | oui | oui | non | non |
| Paquet autonome, manifeste d'installation, `request.json` | oui | oui | non | non |
| Unités, slice, montage borné | oui | analyse statique (`systemd-analyze verify` 255 ; l'hôte est en 249) | non | non |
| `lab01_ops.sh` (staging épinglé, préconditions, apply reprenable, retrait avec preuves), `lab01_audit.sh`, `lab01_oom_probe.sh` | oui | dossiers temporaires et faux outils : épinglage, préconditions, échec de `mkfs`/montage puis reprise, retrait refusé si preuve non écrite ; **`apply` réel, montage loop, `mkfs` réel non exécutés** | non | non (0a seul : `lab01_audit.sh user`, 15/10 17:52Z) |
| `host_isolation_tests.py` + `hostprobe.py` + `unit_props.py` | oui | logique, couverture, essais témoins, 3 restrictions émulées | non | non |
| Ressources, identités, ports | — | — | — | oui, partiel (relevé ponctuel du 15/10, lecture seule) |
Non établi : comportement des unités sous systemd 249 (`MemoryDenyWriteExecute` avec Python 3.11 ; filtre syscall ; montage loop), pare-feu, propriétaires de ports, historique OOM (journal illisible pour `chatgpt-ro` : INDÉTERMINÉ ; compteur `oom_kill` à relever). Le pare-feu et les propriétaires de ports restent un inventaire séparé (bloc 0b, non autorisé) qui ne retarde pas l'étape locale A.

## 10. Décisions attendues
1. Autoriser (ou non) le bloc 0 : 0a sans privilège, 0b séparé nécessitant sudo.
2. Plus tard seulement : exception #286 pour les blocs 2 à 4 (installation et essais). **Non demandée maintenant.**
3. Mode d'accès à l'interface (aucun / tunnel / tailnet) : changement réseau distinct.
