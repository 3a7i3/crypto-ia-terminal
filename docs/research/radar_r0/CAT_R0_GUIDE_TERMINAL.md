# CAT R0 — Guide du terminal RADAR

Le Radar fonctionne localement, sur les fixtures SYNTHETIC du dépôt, sans
réseau, sans serveur et sans dépendance hors bibliothèque standard Python
(3.11 ou plus). Il ne lance aucune collecte, aucun job, aucune expérience.

La sortie réelle d'une session complète est dans
[CAT_R0_DEMO_SORTIE.txt](CAT_R0_DEMO_SORTIE.txt).

## 1. Démarrer

Depuis la racine d'un checkout de la branche R0 :

```bash
python3 -m observability.radar_selection --fixture calm status
```

Options, à placer **avant** la commande :

| Option | Rôle |
|---|---|
| `--fixture NOM\|CHEMIN` | `calm`, `volatile`, `gaps`, `incoherent`, ou un fichier `radar-fixture/1.0.0` |
| `--state-dir DOSSIER` | seul dossier où le Radar peut écrire (préférences, historique). Absent : rien n'est écrit |
| `--width N` | largeur d'affichage (40 à 120). Par défaut `COLUMNS`, sinon 80. Sous 60 : affichage étroit |
| `--mission M` | `DEEP_OBSERVATION` (défaut), `PRICE_STUDY`, `L2_DEPTH_STUDY` |

Codes de sortie : `0` fait, `2` commande refusée (marché inconnu ou non
autorisé), `3` entrée refusée (trop grande, malformée, non SYNTHETIC), `4`
usage ou état (commande inconnue, `--state-dir` requis).

## 2. Les quatre univers

| Nom | Fichier | Contenu |
|---|---|---|
| `calm` | `r0_syn_01_calm.json` | Marchés calmes, données correctes et complètes |
| `volatile` | `r0_syn_02_volatile.json` | Marchés volatils, données correctes ; deux marchés sans observation |
| `gaps` | `r0_syn_03_active_gaps.json` | Marchés actifs : trous, source ancienne, horodatage et BBO manquants, source dégradée, marché retiré (LUNA) et ajouté (WIF) |
| `incoherent` | `r0_syn_04_incoherent.json` | Conflits d'identité, carnet croisé, horodatages désordonnés, doublons, catalogue indisponible ou ancien, contrat inconnu, observations orphelines |

Chaque univers contient des marchés Kraken et MEXC, Spot et Perpétuel. Les
fichiers sont régénérés à l'identique par
`python3 -m tests.radar_selection.build_fixtures` (`--check` compare sans
écrire).

## 3. Commandes

| Commande | Effet |
|---|---|
| `status` | Tableau de bord : mode, univers, trois candidats (plus de référence BTC depuis R-REF) |
| `universe [--venue V] [--type T] [--search Q] [--decision D]` | Tous les marchés, filtrables (`--type SPOT\|PERPETUAL`, `--decision ADMISSIBLE\|A_QUALIFIER\|NON_ADMISSIBLE\|UNKNOWN`) |
| `scan` | Évalue l'univers ; avec `--state-dir`, ajoute le résultat à l'historique borné (20) |
| `candidates` | Les trois propositions détaillées : critères, coût et provenance, limites |
| `inspect <id>` | Les six critères, la chaîne de qualification, la décision, le score |
| `evidence <id>` | Références de preuve complètes (SHA-256, catalogue, observation) et motifs UNKNOWN |
| `select <id>` / `unselect <id>` | Candidat manuel (préférence locale) |
| `pin <id>` / `unpin <id>` | Épingler sans contourner les gates |
| `exclude <id>` / `include <id>` | Retirer d'une sélection automatique / l'y remettre |
| `reset` | Vider sélections, épingles et exclusions |
| `history` | Historique borné des sélections |
| `export` | Évaluation complète en JSON canonique (entrée des étages suivants) |
| `bench [N]` | Mesure locale : durée, mémoire pic, tailles, empreintes |
| `help` | Aide |
| `shell` | Shell ligne à ligne (`quit` ou fin d'entrée pour sortir) |

Les identifiants suivent `venue:type:BASE/QUOTE`, par exemple
`kraken:spot:BTC/USDT`, `mexc:perp:BTC/USDT`, `kraken:perp:BTC/USD`.

## 4. Parcours type

```bash
# 1. Vue d'ensemble
python3 -m observability.radar_selection --fixture volatile status

# 2. Les candidats et pourquoi
python3 -m observability.radar_selection --fixture volatile candidates

# 3. Un marché en détail, puis ses preuves
python3 -m observability.radar_selection --fixture gaps inspect kraken:spot:SOL/USDT
python3 -m observability.radar_selection --fixture gaps evidence kraken:spot:ADA/USDT

# 4. Préférences (dossier explicite)
python3 -m observability.radar_selection --fixture gaps --state-dir ./radar-state select kraken:spot:BTC/USD
python3 -m observability.radar_selection --fixture gaps --state-dir ./radar-state exclude kraken:perp:BTC/USD
python3 -m observability.radar_selection --fixture gaps --state-dir ./radar-state status
python3 -m observability.radar_selection --fixture gaps --state-dir ./radar-state reset

# 5. Déterminisme : deux empreintes identiques
python3 -m observability.radar_selection --fixture calm export | sha256sum
python3 -m observability.radar_selection --fixture calm export | sha256sum

# 6. Terminal étroit
python3 -m observability.radar_selection --fixture calm --width 48 status

# 7. Shell sans interaction (tests, scripts)
printf 'status\ncandidates\nquit\n' | python3 -m observability.radar_selection --fixture calm shell
```

Le shell n'affiche pas d'invite quand l'entrée n'est pas un terminal ;
interactif, il affiche `radar>`.

## 5. Lire l'écran

- `MODE: SYNTHETIC / OFFLINE` et `NETWORK / L2 COLLECTION / PAPER: DISABLED`
  sont toujours affichés : aucune valeur n'est LIVE.
- **Univers** : découverts, autorisés, admis, à qualifier, inconnus, non
  admissibles, exclus manuellement.
- **Référence** : écran retiré par R-REF (`radar-evaluation/1.2.0`). Aucun
  marché n'est une référence ; `Kraken | SPOT | BTC/USDT` est classé comme les
  autres et peut être exclu par `exclude`.
- **Candidats** : `PROPOSÉ, NON AUTORISÉ`. Une proposition ne lance rien.
- Un marché choisi ou épinglé qui n'est pas `ADMISSIBLE` est affiché
  « NON présenté comme admissible ».

## 6. Ce que le terminal refuse

- Toute connexion réseau, tout sous-processus et toute écriture hors
  `--state-dir` (garde active avant la première commande).
- Une entrée de plus de 2 000 000 octets, un JSON malformé, une clé dupliquée,
  un nombre à virgule flottante, une clé inconnue, un `evidence_kind` autre que
  `SYNTHETIC`.
- `select`/`pin` d'un marché inconnu ou hors univers autorisé.

## 7. Tests

```bash
python3 -m pytest -q tests/radar_selection
```

Les tests de la CLI s'exécutent dans des processus séparés, la garde hors
réseau étant irréversible dans un processus.
