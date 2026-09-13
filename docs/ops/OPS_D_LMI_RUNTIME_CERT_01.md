# OPS-D / LMI-RUNTIME-CERT-01

## Statut

- Mission: `OPS-D / LMI-RUNTIME-CERT-01`
- Référence source initiale: `ddd34b4ae325b9852475f043f9b1f6cd1e4c6e23`
- F-00: **NON DÉMARRÉ**
- Burn-in: **NON AUTORISÉ**
- Trading réel: **HORS SCOPE**

Principe directeur:

> `SOURCE PROOF != RUNTIME PROOF`

Cette mission répond à la question:

> **La machine observe-t-elle correctement le marché aujourd'hui ?**

## Capture runtime #1 — 2026-09-13

VPS observé: `crypto-advisor-2`.

### Identité

Le runtime observé ne correspondait pas au SHA `main` attendu:

- expected main: `ddd34b4ae325b9852475f043f9b1f6cd1e4c6e23`
- VPS HEAD observé: `dd0d8a5ac034c3a31edb6bafed07e0e52fe4ad36`
- `git diff` contre le SHA attendu impossible localement car l'objet n'était pas encore présent dans le clone VPS.

Conséquence: cette capture ne peut pas certifier l'identité du futur runtime OPS-D.

### Santé processus

Évidence observée:

- service `crypto-lmi-observatory.service`: `active/running`
- `NRestarts=0`
- démarrage: `2026-09-12 06:35:38 UTC`
- RSS: environ `97 MiB`
- threads: `7`
- FD: `48`
- sockets: `44`
- disque `/`: environ `49 GiB` libres

Verdict: santé processus **PASS provisoire**, à revalider après déploiement du SHA OPS-D.

### Fraîcheur / couverture

Fenêtre observée: 60 secondes.

Début:

- requested/watchlist: `20`
- objets sidecar: `26`
- fresh: `18`
- stale: `1`
- unavailable: `1`

Fin:

- requested/watchlist: `20`
- fresh: `19`
- stale: `0`
- unavailable: `1`

Le compteur `stats.events` a progressé de `319401` à `319579`, soit `+178` PressureFields sur 60 s (~`2.97 PressureFields/s`). Ce compteur est une sortie LMI, **pas** un débit brut WebSocket MEXC.

### Défaut démontré A — états hors watchlist

Sept symboles historiques étaient encore présents dans `symbols` alors qu'ils n'étaient plus dans la watchlist courante:

- `DOGEUSDT`
- `FARTCOINUSDT`
- `INJUSDT`
- `LITUSDT`
- `SOLUSDC`
- `XRPUSDC`
- `ZECUSDT`

Cause source: `LiveStateStore.set_watchlist()` remplaçait la watchlist sans élaguer `_states`.

Impact: `symbols_active` pouvait représenter des états historiques et non la population courante.

### Défaut démontré B — USD1USDT

`USD1USDT` était demandé par le LMI mais sans état courant.

Le journal montrait des `queue stall` continus dépassant 45 minutes.

La capture publique MEXC a ensuite montré:

- `contract/detail`: `1192` contrats renvoyés
- `USD1_USDT_found = False`
- REST deals `USD1_USDT`: `0`

Conclusion: le runtime tentait de souscrire un instrument absent du catalogue MEXC Futures courant.

### Dérive systemd observée

L'unité réellement déployée ne chargeait pas `.env.secrets`, alors que la source de référence initiale le chargeait malgré son propre contrat « zéro clé ».

La remédiation OPS-D conserve le comportement runtime le plus sûr : le service LMI ne reçoit que `.env`, qui contient ses variables de configuration non secrètes. `.env.secrets` n'est plus injecté dans ce processus d'observation publique.

## Remédiation source de cette branche

La branche OPS-D apporte uniquement des changements d'observation/runtime LMI:

1. le sidecar distingue maintenant:
   - `watchlist` = symboles demandés,
   - `stream_watchlist` = symboles effectivement souscrits,
   - `coverage[symbol].status` = `LIVE | STALE | UNAVAILABLE`,
   - raison explicite d'indisponibilité;
2. les états qui ne font plus partie de la population streamable validée sont supprimés du sidecar courant;
3. une mise à jour tardive d'une task annulée ne peut pas réintroduire un symbole hors population streamable;
4. MEXC expose un contrôle public frais du catalogue Futures via `contract/detail`;
5. l'Observatory valide l'existence des instruments MEXC avant d'ouvrir les WebSockets;
6. un catalogue MEXC indisponible est fail-closed pour l'itération de reconcile;
7. le dashboard adapter filtre les états hors watchlist et expose les compteurs de couverture explicites;
8. le service systemd LMI n'injecte plus `.env.secrets` et reste conforme à sa frontière « données publiques / zéro clé ».

Aucun changement stratégie, signal, risk, sizing, portfolio, ordre, capital ou autorité d'exécution.

## Critères SOURCE avant merge

La PR n'est mergeable scientifiquement que si:

- tests OPS-D ciblés: PASS;
- tests Observatory/MEXC/stream concernés: PASS;
- CI canonique pertinente: PASS ou échecs préexistants explicitement attribués;
- aucune dérive hors scope dans le diff;
- SHA de tête exact documenté.

## Critères RUNTIME après merge/déploiement

Le merge ne vaut pas certification runtime.

Le verdict final exige un runtime déployé correspondant au SHA certifié et une nouvelle fenêtre d'observation démontrant au minimum:

1. provenance Git exacte;
2. service actif et ressources bornées;
3. `symbols_active <= symbols_watched` sans états fantômes;
4. `stream_watchlist` cohérente avec le catalogue MEXC courant;
5. instrument absent classé `UNAVAILABLE` sans socket/stall permanent;
6. fraîcheur par symbole fondée sur timestamp marché;
7. progression des PressureFields sur fenêtre bornée;
8. échec/restart/recovery attribuable par symbole si un incident naturel est disponible;
9. artefacts et logs reconstruisibles;
10. aucune confusion entre PressureFields/s et événements WebSocket/s;
11. aucune clé privée injectée dans le processus LMI.

Verdict final autorisé, exactement l'un des deux:

- `OPS_D_RUNTIME_CERTIFIED`
- `OPS_D_REMEDIATION_REQUIRED`
