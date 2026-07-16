# ADR-0016 — Univers d'observation MEXC complet (spot + perp), strictement passif

- **Statut** : Accepté (décision opérateur Mathieu, 2026-07-15 — « On oriente
  les objectifs sur le fait que la machine puisse observer tout le marché
  crypto spot/perp de MEXC »)
- **Date** : 2026-07-15
- **Contexte** : suite d'ADR-0015 (univers tradé épinglé à 28 paires) et de
  la sonde de débit (2026-07-15) qui a montré que le débit du burn-in est
  borné par la taille de l'univers, pas par les seuils.

## Contexte

L'opérateur veut que la machine **voie l'ensemble du marché crypto MEXC**
(spot + perpétuels) pour enrichir massivement ses mesures internes, sans
attendre que le marché « passe devant » les 28 paires épinglées.

Deux faits structurent la solution :

1. **Voir ≠ trader.** L'univers TRADÉ reste épinglé (ADR-0015) jusqu'aux
   gates du burn-in — c'est la preuve scientifique en cours, intouchable.
   L'observation, elle, peut être totale dès aujourd'hui.
2. **Point critique de passivité (découvert en préparant cet ADR)** : le
   `RegretEngine` du moteur n'est PAS un simple observateur — son
   `get_threshold_delta()` alimente l'AdaptiveThresholdEngine qui règle les
   deltas du gate (`advisor_loop.py`, bloc P6/ATE). Brancher l'univers
   d'observation sur le RegretEngine live aurait donc modifié les seuils de
   décision — une contamination ADR-0007. **La couche d'observation doit
   écrire dans ses propres stores, jamais lus par le chemin de décision.**

## Décision

Créer une couche d'observation **hors process moteur**, en trois phases :

### Phase O1 — Pouls du marché complet (cet ADR, implémentée)

- Nouveau module autonome `observation/market_observer.py` — **processus
  séparé** du moteur : zéro import du moteur, zéro écriture dans ses stores,
  API publique MEXC uniquement (aucune clé, aucun ordre possible).
- À chaque tick (défaut : 15 min, systemd timer) : 2 appels batch
  `fetch_tickers()` (spot + swap) → un enregistrement compact par paire
  (prix, bid/ask, spread, volume 24h, variation 24h) pour **tout le
  marché** (~2500 spot + ~600 perp).
- Stockage : `databases/observation/market_pulse_YYYY-MM-DD.jsonl.gz`
  (gzip à l'écriture, rotation quotidienne).

**Budget ressources (disque VPS à 92% au moment de la décision — 2,6 Go
libres)** :
- API : 2 appels / 15 min — négligeable (rate limit MEXC ~20 req/s).
- Disque : ~3100 paires × 96 ticks/jour × ~110 o ≈ 33 Mo/jour brut →
  **~4-6 Mo/jour gzip** ; rétention `OBS_RETENTION_DAYS` (défaut 45 j)
  ≈ 250 Mo au plafond.
- Garde-fou : si l'espace libre passe sous `OBS_MIN_FREE_DISK_GB`
  (défaut 1,5 Go), l'observateur SAUTE l'écriture et le signale — il ne
  met jamais le moteur en danger.
- RAM/CPU : processus éphémère (`--once` par tick systemd timer), rien de
  résident.

### Phase O2 — Évaluation à horizons sur univers élargi (ADR ultérieur)

Top ~200 paires liquides du pouls : OHLCV léger + évaluation directionnelle
à horizons (5m/30m/1h) façon RegretScheduler, mais dans un store
d'observation dédié. Donne les gradients de qualité par régime/score sur un
univers 7× plus large — lisible par `tools/throughput_probe.py`.

### Phase O3 — Élargissement de l'univers TRADÉ (post-burn-in, ADR séparé)

Paliers 28 → 80 → 200, chacun justifié par les mesures O1/O2 (débit +
qualité par palier) et acté par ADR. Le ranker amélioré (cf ADR-0014)
devient l'organe de sélection.

## Conséquences

- **Gain** : data massive dès maintenant (~300 000 observations/jour),
  couverture totale du marché, matière pour le CRI (coverage), pour le
  ranker futur et pour les décisions d'élargissement — sans toucher au
  burn-in ni au moteur.
- **Coût** : un timer systemd de plus à opérer ; ~250 Mo de disque au
  plafond de rétention.
- **Risque contenu** : le processus est read-only vis-à-vis de l'exchange
  (endpoints publics) et write-only vers `databases/observation/` — un
  répertoire que le moteur ne lit pas. Sa panne n'affecte rien.
- **Dette signalée** : le disque VPS à 92% est un risque opérationnel
  préexistant (databases/ ne pèse que 1,5 Go sur 27 utilisés) — un
  nettoyage indépendant est recommandé.

## Implémentation

- `observation/market_observer.py` — CLI : `--once` (un tick),
  `--interval N` (boucle), `--summary [fichier]` (lecture d'un jour).
- `scripts/systemd/crypto-market-observer.{service,timer}` — unité oneshot
  + timer 15 min, à installer sur le VPS (geste opérateur).
- Tests : `tests/observation/test_market_observer.py` (fabrication des
  enregistrements, garde-fou disque, rétention, round-trip gzip — aucun
  appel réseau).

## Liens

- ADR-0007 (passivité des observateurs — le point RegretEngine→ATE ci-dessus
  en est un corollaire opérationnel)
- ADR-0015 (univers tradé épinglé — inchangé par le présent ADR)
- ADR-0014 (proposé — ranker/MexcSim ; consommateur futur des données O1/O2)
