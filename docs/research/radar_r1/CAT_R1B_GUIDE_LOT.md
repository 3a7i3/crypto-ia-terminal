# CAT R1-B — Guide : évaluer un lot d'observations

R1-B permet au Radar R0 de lire un **lot** (`radar-batch/1.0.0`) au lieu d'une
fixture : catalogues bruts d'un passage Scanner et fenêtres BBO déjà rejouées,
référencés par leur empreinte. Tout se fait hors ligne, avec la bibliothèque
standard (Python 3.11 ou plus). Aucune collecte, aucun rejeu de journal, aucune
admission. Contrat : [CAT_R1B_CONTRAT_LOT_RADAR.md](../../contracts/CAT_R1B_CONTRAT_LOT_RADAR.md).

La sortie réelle des commandes ci-dessous est dans
[CAT_R1B_DEMO_SORTIE.txt](CAT_R1B_DEMO_SORTIE.txt).

## 1. Évaluer le lot SYNTHETIC du dépôt

```bash
python3 -m observability.radar_selection \
    --batch tests/radar_selection/evidence/batches/r1b_syn_01_btc_atom.json \
    --evidence-root tests/radar_selection/evidence candidates
```

- `--batch` remplace `--fixture` (les deux ensemble : erreur d'usage).
- `--evidence-root` est obligatoire avec `--batch` : c'est le seul dossier où
  le Radar lit les références du lot. Toute lecture ailleurs est refusée
  (`RADAR_READ_OUTSIDE_EVIDENCE_ROOT`), sauf le code Python importé.
- Les autres options et commandes de R0 (`status`, `inspect`, `evidence`,
  `candidates`, `--mission`, `--state-dir`, `--width`) sont inchangées.

L'en-tête affiche la nature (`MODE: SYNTHETIC / OFFLINE`), la version du lot et
`ADMISSION: NONE`. La qualité L2 Kraken se lit « carnet vérifié sur 10 niveaux
(KRAKEN_CRC32), X instants valides sur Y » ; la commande `evidence` montre la
source, son corpus et son commit producteur.

## 2. Ce que contient l'arbre de preuves

`tests/radar_selection/evidence/` :

| Chemin | Contenu | Régénération |
|---|---|---|
| `scanner/runs/20261117T163500Z/` | cinq catalogues bruts (formes publiques officielles, nombres fractionnaires conservés) et `manifest.json` | `build_batches` |
| `bbo/BBO-{BTC,ATOM}-DRY/` | manifeste de journal et fenêtres rejouées du transport simulé | `build_batches --refresh-bbo` seulement |
| `bbo/bbo-composite-history.json` | ancre scellant les fenêtres | `--refresh-bbo` seulement |
| `bbo/PROVENANCE.json` | générateur, transport, commit de génération | `--refresh-bbo` seulement |
| `specs/r1b_syn_spec.json` | spécification opérateur du lot | `build_batches` |
| `batches/r1b_syn_01_btc_atom.json` | lot construit depuis la spécification | `build_batches` |

```bash
python3 -m tests.radar_selection.build_batches --check   # compare, n'écrit rien
```

Les preuves BBO enregistrent le commit qui les a produites ; elles sont donc
figées et ne sont régénérées que sur demande explicite (`--refresh-bbo`).

## 3. Construire un lot depuis une spécification

```bash
python3 -m observability.radar_selection.batch_build \
    --evidence-root DOSSIER_DE_PREUVES --spec specs/ma_spec.json \
    --state-dir DOSSIER_DE_SORTIE --out mon_lot.json
```

La spécification (`radar-batch-spec/1.0.0`) épingle le manifeste Scanner et,
pour chaque paire BBO, l'ancre, le manifeste de journal et les fenêtres à
utiliser. Le constructeur vérifie les épingles, projette les fenêtres, puis
contrôle le lot avec le vérificateur du Radar avant de l'écrire. Il n'écrit que
dans `--state-dir` et ne remplace jamais un fichier existant. Codes de sortie :
`0` écrit, `3` entrée refusée (rien n'est écrit), `4` usage.

## 4. Lire les résultats sans les surinterpréter

- `VERIFIED_TOP_N` (Kraken) vaut 40 points, comme `TECHNICALLY_COMPATIBLE`
  (MEXC). C'est une pondération **transitoire** (décision D4), pas une preuve de
  fiabilité égale ; seuls 10 niveaux sont attestés, jamais le carnet complet.
- Profondeur ±10 bps, activité et coût restent UNKNOWN avec leur motif
  (`DEPTH_LEVELS_NOT_IN_ARTIFACT`, `TRADE_CHANNEL_NOT_CAPTURED`,
  `COST_NOT_MEASURED`). Leur poids n'est pas redistribué : les scores sont
  `INCOMPLETE`.
- Les instants non synchronisés ou sans BBO sont omis et cités dans la portée
  L2, jamais remplacés.
- Un lot `HISTORICAL` est une entrée hors ligne : `ADMISSION: NONE`, aucun
  marché n'est une référence depuis R-REF, et chaque candidat porte la limite
  « Données HISTORICAL hors ligne ». Aucun lot HISTORICAL n'est livré ici :
  le dépôt ne contient que des preuves SYNTHETIC.
