# LAB-01 — audit borné de l'hôte (lecture seule, 2026-10-15)

Hôte `crypto-advisor-2`, compte `chatgpt-ro` (uid 996, sans sudo), 06:12:27Z, par le
connecteur Remote Desktop Commander (appareil en ligne `8514dba5…`). Deux commandes
groupées, lecture seule. Aucun `.env`, aucune valeur de secret, aucun scan récursif,
aucune écriture. #286 inchangé. Les observations de G0–G2 (14–15/10) sont réutilisées,
non relevées à nouveau.

## 1. Ressources (relevé ponctuel du 2026-10-15 à 06:12Z ; ni moyenne ni garantie)
| Élément | Valeur | Lecture |
|---|---|---|
| CPU | 2 vCPU ; load 1,17 / 0,95 / 0,97 ; PSI cpu `some` avg300 2,12 % | peu de marge : 2 cœurs seulement |
| RAM | 15 991 Mo total, 7 988 Mo utilisés, 7 663 Mo « disponibles » **à cet instant** (relevé ponctuel, variable) ; **pas de swap** | sans swap, un dépassement déclenche l'OOM-killer |
| Disque | 97 Go, 57 Go utilisés, 41 Go libres (59 %), un seul volume `/` | LAB et production partagent le même volume |
| Disponibilité | up 27 j | — |
| Consommation | `crypto-advisor.service` : PID 882633, **6,9 Go** (cgroup, 135 tâches), ≈ 65 % d'un cœur ; lmi-observatory 418 Mo ; market-snapshot 330 Mo ; operator-api 38 Mo | Advisor = ~87 % de la RAM utilisée |
| Limites cgroup | `MemoryMax=infinity`, `CPUQuota=infinity` sur advisor, paper-arena, operator-api | aucune enveloppe en production |
| cgroup / systemd | cgroup v2 (`cgroup2fs`), systemd 249 (Ubuntu 22.04) | slices, `MemoryMax`, `IPAddressDeny` disponibles |

## 2. Identités, groupes, chemins
- Comptes ≥ 1000 : `ubuntu`(1000), `mathieu`(1001), `ia_strategy_support`(1002), `claude-audit`(1003). `chatgpt-ro` est un compte système (996) sans groupe additionnel.
- Advisor, lmi-observatory, market-snapshot et operator-api tournent sous `mathieu` (processus et `User=` observés) ; `paper-arena`, `dashboard`, `radar-bot` : utilisateur non vérifié. `mathieu` appartient à `adm`, `lxd`, `google-sudoers`, `ollama`, `ubuntu`.
- `/home/mathieu` `0750 mathieu` : **INACCESSIBLE** à `chatgpt-ro` (checkout, `databases/`, `.env`). `/home/ia_strategy_support`, `/home/claude-audit` : `0750`, inaccessibles. `/srv/claude-audit` : `root:claude-audit 0750`, inaccessible. `/opt/crypto-ai-terminal` : `root 0755` (lisible ; seul `operator/presentation/` a été lu en G0).
- `sudo -n` : mot de passe requis (aucun sudo pour `chatgpt-ro`).

## 3. Services et ports utiles
Services actifs : advisor, dashboard, lmi-observatory, market-snapshot, operator-api, operator-web, quant-observer, radar-bot, `paper-arena`, `ollama`, tailscaled, ssh (+ agents Google Cloud). Écoutes TCP observées (propriétaires **INACCESSIBLES** sans `ss -p` privilégié) : 22 ; 127.0.0.1 : 8181, 8090, 8050, 11434 ; 0.0.0.0 : 8080, 20202 ; `*:20201` ; adresse tailnet 100.99.170.96 : 443, 8443, 39248. **Libre : 18090** (port proposé au LAB, loopback).
Dépendances nécessaires au cycle : Python 3.11.15 (`/usr/bin/python3.11`, `ensurepip` présent), `git`, `unshare`, `nft`, `iptables` installés ; Node 24 hors usage. Le cycle n'a **aucune dépendance tierce** (bibliothèque standard seule).

## 4. Séparation code / données / secrets (état actuel)
Code et données de production sont sous `/home/mathieu/crypto_ai_terminal` (une seule identité), les secrets dans des `.env`/`EnvironmentFile` de cet arbre (jamais lus). `/opt/crypto-ai-terminal` (root) contient des publications de présentation. Aucune séparation d'identité entre l'exploitation et d'éventuelles expériences : un LAB sur l'hôte exige **sa propre identité** et ses propres chemins.

## 5. INACCESSIBLE avec `chatgpt-ro` (commandes opérateur : voir `LAB_01_OPERATOR_COMMANDS.md`, bloc 0a sans privilège et 0b privilégié séparé)
Règles réseau `nft`/`iptables` (« Operation not permitted »), propriétaires de ports, `unprivileged_userns`, historique OOM du noyau, contenu et droits de `/home/mathieu/*`, `EnvironmentFile` des unités (volontairement non lus), cadence des écritures d'Advisor.
