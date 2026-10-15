# LAB-01 — environnement autonome de développement et simulation

Statut : **plan et code préparés, testés localement, rien d'installé, rien observé sur l'hôte.**
Parents : #445 (passerelle d'opérations privilégiées), #432 (passerelle frontend) ; roadmap #285 ;
garde #286 **active** (aucune de ces actions ne la lève). Audit : [LAB_01_AUDIT_VPS_20261015.md](LAB_01_AUDIT_VPS_20261015.md).
Commandes : [LAB_01_OPERATOR_COMMANDS.md](LAB_01_OPERATOR_COMMANDS.md). G3 publishers reste une tâche distincte.

## 1. Ce qui est démontré aujourd'hui (testé localement)
Cycle complet `données synthétiques → signal → risque → DecisionPacket → simulation PAPER → événements → API → interface`,
code dans `lab01/`, tests `tests/lab01/` (38). Réutilise `core.decision_packet.DecisionPacket` (machine d'états et chaîne de hachage réelles)
et `execution_simulator` (frais, latence, slippage, spread) ; ne touche ni Advisor, ni PPL, ni FIN, ni stratégies/seuils actifs.

| Scénario | Données | Issue attendue | Critères explicites (tous évalués, verdict PASS/FAIL) |
|---|---|---|---|
| `accepted_closed` | seed 11, vol 15 bps | `POSTMORTEM_ANALYZED`, PnL synthétique | verdict risque APPROVED, ORDER_FILLED, POSITION_OPENED/CLOSED, aucune erreur, chaînes intègres |
| `risk_rejected` | seed 11, vol 150 bps | `REJECTED`, `VOLATILITY_ABOVE_LIMIT` | RISK_REJECTED avec observé > limite et justification ; aucun ordre, aucune position |
| `execution_error` | scénario 1 + panne injectée au 1er ordre | `FAILED`, `SIMULATED_EXCHANGE_TIMEOUT` | EXECUTION_ERROR visible et tracé ; aucun fill, aucune position, aucun PnL |

Le risque n'est **jamais assoupli** : les limites sont identiques dans les trois scénarios ; seul le jeu de données change le verdict. Chaque règle a un test de refus.
Chaque expérience porte `experiment_id` (`LAB01-<scénario>-<12 hex>` = empreinte du code, de la configuration et des seeds), `trace_id`, provenance `SYNTHETIC`
sur chaque événement, horloge **synthétique** (2026-01-01…), chaîne de hachage des événements, `manifest.json` (empreintes de code/config, seeds, HEAD git).
Reproductibilité : mêmes empreintes d'événements en deux rejeux, entre deux processus, et depuis le paquet autonome (même `experiment_id` que le dépôt).
Limite connue : le `DecisionPacket` réel horodate ses transitions à l'heure murale ; `packet.json` est fourni mais exclu des empreintes.
Le PnL du LAB est un PnL synthétique : ce n'est ni de la vérité FIN, ni du lifecycle PPL, ni une entrée Research. Aucun retour LAB → Research/production.

Mesures locales (sandbox, Python 3.13) : cycle complet ≈ 0,2 s, ≈ 22 Mo RSS, ≈ 170 Ko d'artefacts. **Non mesuré sur l'hôte.**

## 2. Comparaison des architectures
| | A. Local puis hébergement léger | B. LAB limité sur le VPS actuel | C. Environnement distinct |
|---|---|---|---|
| Coût | 0 supplémentaire (bac à sable + CI GitHub existants) ; l'hébergement léger n'est **pas chiffré**, il n'est requis que si l'on veut consulter l'interface à distance | 0 marginal ; consomme ≤ 2 Go / 0,5 vCPU de l'hôte existant | Coût récurrent **non estimé** (devis à obtenir) ; aucun budget supposé |
| Contraintes | Aucun accès à l'hôte ; preuves « testé localement » seulement | 2 vCPU et 7,7 Go disponibles, **sans swap**, Advisor sans plafond ; levée d'exception #286 pour toute unité ; disque partagé | Nouvelle surface (accès, mises à jour, secrets d'accès, sauvegardes) ; transfert des artefacts à organiser |
| Risque pour la production | Nul | Faible si plafonds cgroup + identité dédiée + réseau refusé ; non nul par construction (même noyau, mêmes 2 cœurs) | Nul |
| Ce que ça prouve | Logique, reproductibilité, refus (déjà fait) | De plus : isolation et plafonds **observés sur l'hôte** | Isolation réelle sans cohabitation |

**Retenu : A maintenant (fait), B ensuite et seulement sur autorisation, C écartée.**
Justification : les faits mesurés ne l'exigent pas. Le cycle tient en ≈ 22 Mo et 0,2 s ; la bibliothèque standard suffit (aucune préparation de dépendances,
donc aucun réseau requis, même pour l'installation) ; les 7,7 Go disponibles couvrent largement un plafond de 2 Go. Le premier cycle ne dépend donc pas de la passerelle #445.
Passage à C si l'une de ces conditions apparaît : OOM du noyau relevé par le bloc 0, PSI cpu `some` avg60 > 10 % pendant un essai du LAB, besoin d'importer des copies
de production, besoin d'un accès réseau sortant pendant l'expérience, ou refus de l'exception #286.

## 3. LAB sur le VPS (option B) — conception préparée, non installée
- **Identité** : utilisateur système `lab01` (nologin, sans sudo, sans groupe additionnel, sans clé SSH). Aucune session interactive associée ; l'opérateur agit par `sudo systemd-run`/`systemctl`.
- **Espaces** : `/srv/lab01/release` (root, lecture seule pour `lab01`, paquet vérifié par SHA-256), `/srv/lab01/runs` (`lab01` 0700), `/srv/lab01/token` (root:lab01 0640). Rien sous `/home/mathieu`, `/opt/crypto-ai-terminal` ni `/srv/claude-audit` (inaccessibles par l'unité). Branche de travail distincte : `claude/project-thread-c2x3i9` → PR brouillon ; aucun checkout de production modifié.
- **Plafonds cumulés** (`lab01.slice`) : `MemoryMax=2G`, `MemoryHigh=1536M`, `MemorySwapMax=0`, `CPUQuota=50 %`, `TasksMax=128`, `IOWeight=10`. Plafonds par unité : 64 processus, 256 fichiers, pas de core dump.
- **Services indépendants** : `lab01-run.service` (oneshot, sans réseau) et `lab01-api.service` (loopback 127.0.0.1:18090, jeton Bearer, lecture seule). Aucune dépendance `Requires/Wants/After/BindsTo/PartOf/OnFailure` vers une unité de production, aucun `EnvironmentFile`, aucune section d'installation (jamais démarré au boot). Le test `test_units_have_no_production_dependency_or_secret_source` l'impose.
- **Réseau** : exécution = `PrivateNetwork=yes`, `IPAddressDeny=any`, `AF_UNIX` seul ; API = `IPAddressDeny=any` + `IPAddressAllow=127.0.0.0/8 ::1`. Défense en profondeur dans le code : `deny_network()` refuse `connect`/DNS pendant le cycle.
- **Aucune clé exchange, aucun ordre réel** : `lab01` n'a accès à aucun secret ; le LAB refuse de démarrer si une variable d'environnement ressemble à un secret exchange (noms seulement, jamais les valeurs) ; aucun module d'ordres réels n'est importé (le paquet ne contient que `core`, `execution_simulator`, `observability.json_logger`).
- **Préparation vs exécution** : préparation = construction du paquet (`make_bundle`, déterministe, stdlib seule) hors hôte ou dans un clone temporaire ; l'hôte n'a besoin d'aucun `pip install`. Exécution = unités sans réseau. Le seul accès réseau est le clone git du bloc 1, côté opérateur.
- **Interface authentifiée** : jeton ≥ 24 caractères comparé en temps constant ; sans jeton configuré, le serveur l'annonce (`auth=AUCUNE`) et reste en loopback. Toute exposition distante est un changement réseau séparé.
- **Données** : synthétiques seulement ; aucun montage de production. Tout import futur = copie explicitement autorisée, bornée, identifiée et vérifiée, sous une gate distincte.

## 4. Matrice des permissions
| Acteur / objet | Code LAB (release) | Artefacts (runs) | Jeton | Arbre production (`/home/mathieu`, `/opt/crypto-ai-terminal`) | Secrets / `.env` | Réseau sortant | Unités de production | Exchange / ordres |
|---|---|---|---|---|---|---|---|---|
| `lab01-run` (unité) | R | **RW** | — | refusé (`InaccessiblePaths`) | aucun accès | refusé | aucun lien | aucun |
| `lab01-api` (unité) | R | R | R | refusé | aucun accès | refusé (loopback seul) | aucun lien | aucun |
| `lab01` (utilisateur) | R | RW | R | refusé (modes 0750) | aucun | non contraint hors unité | aucun droit (pas de sudo, pas de polkit) | aucun |
| Opérateur `mathieu` (sudo) | RW via `apply` | R | RW | R/W habituels | habituels | habituel | habituel, **non utilisés par le LAB** | habituel |
| `chatgpt-ro` (agent) | R (lecture) | R | refusé | refusé | refusé | — | lecture seule | aucun |
| Agent (autorité d'exécution) | **aucune** : l'agent ne reçoit aucun droit d'exécution privilégiée | | | | | | | |

## 5. Budget de ressources
Pour tout le LAB, en plus du plafond ci-dessus. Cible d'usage : RAM ≤ 100 Mo (mesuré local ≈ 22 Mo), CPU < 5 % d'un cœur en moyenne, disque ≤ 50 Mo (`/srv/lab01`, mesuré ≈ 0,2 Mo par exécution), processus ≤ 10.
Part de l'hôte : plafond 2 Go = 12,5 % de la RAM ; 0,5 vCPU = 25 % de la capacité CPU ; la marge disponible (7,7 Go) reste > 3× le plafond.
Arrêt d'urgence : `systemctl stop lab01-run lab01-api` ; le dépassement de `MemoryMax` tue le LAB seul (cgroup), pas Advisor.
Seuils d'abandon de B : toute variation du PID ou de `ActiveEnterTimestamp` d'Advisor/API pendant un essai, ou PSI cpu `some` avg60 > 10 %.

## 6. Procédure d'installation et de retrait (source préparée, rien exécuté)
Étapes et commandes exactes : [LAB_01_OPERATOR_COMMANDS.md](LAB_01_OPERATOR_COMMANDS.md). Ordre : bloc 0 (relevé) → bloc 1 (paquet vérifié) → autorisation écrite → bloc 2 (`apply`, rien ne démarre) → bloc 3 (tests de refus, exécution, API) → bloc 4 (retrait).
`lab01_ops.sh` : `plan` par défaut (n'écrit rien), `apply`/`remove` exigent root **et** un identifiant d'autorisation cité, vérifient l'empreinte du paquet, refusent toute unité référençant la production. Retrait : unités retirées, données conservées ; `--purge` supprime `/srv/lab01` et l'utilisateur. Rollback honnête : il ne restaure pas l'état antérieur de l'hôte, il retire ce que le LAB a ajouté ; `verify` le constate.

## 7. Tests
- **Positifs** (locaux, 38 tests) : trois scénarios et leurs critères, chaînes d'événements, reproductibilité (rejeu, inter-processus, paquet autonome), API (liste, détail, événements), interface (bannière SYNTHETIC ; liste des expériences rendue depuis l'API dans un Chromium headless ; le détail n'a pas été parcouru).
- **Refus** (locaux) : chaque règle de risque refuse ; altération d'un événement ou de la provenance casse la chaîne ; réseau refusé puis restauré ; variables ressemblant à des secrets refusées sans en révéler la valeur ; sorties sous l'arbre de production refusées ; scénario inconnu refusé ; API : POST/PUT/DELETE/PATCH → 405, chemins hors liste ou traversants → 404, absence de jeton → 401, artefact manquant → 503 et non liste vide, bind non loopback refusé ; unités sans dépendance de production ni secret ; script d'installation sans autorisation → refus.
- **Refus sur l'hôte** (`lab01_host_tests.sh`, **non exécutés**) : réseau, DNS, `/home/mathieu`, arbre production, écriture `/etc` et hors `runs`, montée de privilèges. Le script n'accepte comme refus que celui de l'OS (code 42 sur `OSError`) et abandonne si le contrôle d'exécution échoue ; sa logique est testée avec un `systemd-run` factice (4 tests).

## 8. États des preuves
| Composant | Préparé | Testé localement | Installé | Observé sur l'hôte |
|---|---|---|---|---|
| Cycle synthétique, scénarios, critères | oui | oui (38 tests) | non | non |
| API GET-only et interface | oui | oui (tests + rendu navigateur) | non | non |
| Paquet autonome | oui | oui (déterminisme, équivalence d'identités) | non | non |
| Unités systemd, slice | oui | analyse statique (`systemd-analyze verify` 255, hors hôte 249) | non | non |
| `lab01_ops.sh`, `lab01_host_tests.sh` | oui | syntaxe, refus sans autorisation, logique de classification | non | non |
| Ressources, identités, ports | — | — | — | **oui, partiel** (audit du 15/10, lecture seule) |

Non établi : comportement des unités sous systemd 249 (notamment `MemoryDenyWriteExecute` avec Python 3.11), état du pare-feu et des espaces de noms, historique OOM. Ces points sont l'objet du bloc 0 et du bloc 3.

## 9. Gouvernance et décisions attendues
1. Valider l'architecture retenue (A fait ; B sur autorisation ; C écartée) ou demander C.
2. Autoriser, séparément, le bloc 0 (lecture) puis une exception #286 pour les blocs 2 et 3 (installation, essais). Rien n'est modifié avant.
3. Choisir le mode d'accès à l'interface (aucun/ tunnel SSH / tailnet) : changement réseau distinct.
Si #445 est qualifiée plus tard, `lab01.apply` pourra devenir une opération nommée ; le premier cycle n'en dépend pas.
