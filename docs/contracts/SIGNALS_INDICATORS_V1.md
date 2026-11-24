# CAT-SIGNALS-01 — Contrat `cat.signals.indicators.v1`

Statut : **L1 contrat + L2 calculateur hors ligne**, symbole de référence BTC.
Aucun collecteur, aucune installation VPS, aucune route API dans ce lot.
Cadrage : note « Bloc de signaux — note de cadrage » (2026-11-23), validée
par le directeur le 2026-11-23 (« on peut commencer son implémentation,
avec un seul symbole disponible sur les 4 marchés comme référence »).

## 1. Rôle et frontières

Le bloc de signaux est un **bloc de lecture** du Radar de signaux
(Marché → Scanner). Pour chaque symbole il lit quatre marchés —
MEXC Spot, MEXC Perpétuel, Kraken Spot, Kraken Perpétuel — et, dans cet
ordre :

1. **vérifie** que chaque donnée est vraie ;
2. **calcule** un jeu fermé d'indicateurs par marché ;
3. **compare** chaque indicateur entre marchés (écarts) ;
4. **publie** valeurs et écarts.

Il ne produit **ni score, ni seuil de décision, ni verdict, ni classement**.

Garde-fous (ADR-0007, #286 `ACTIVE_BURN_IN_IMMUTABILITY_GUARD`) :

- le paquet `observability/signals_indicators/` n'importe que la
  bibliothèque standard et lui-même ; aucun module de `quant_hedge_ai`,
  `core`, `paper_trading`, `src`, `financial_institute`, `risk`, `runtime`
  ne l'importe (test `tests/signals_indicators/test_import_guard.py`) ;
- `quant_hedge_ai/agents/intelligence/feature_engineer.py` est dans le
  chemin de décision gelé : il n'est **ni importé ni modifié** ; il sert
  seulement de référence de formule dans un test de parité ;
- aucune écriture exchange, aucune clé, aucun réseau dans le calculateur ;
- flux interdit : publication → Advisor/PAPER de l'epoch active.

## 2. Entrée `cat.signals.input.v1`

Enveloppe JSON déjà collectée (les collecteurs sont un lot ultérieur) :

| Champ | Règle |
| --- | --- |
| `schema` | `cat.signals.input.v1` |
| `base` | actif de base alphanumérique (`BTC`) |
| `timeframe` | `5m` ou `1h` |
| `as_of_ms` | instant de référence (entier ms UTC) ; le calcul ne lit jamais l'horloge |
| `markets` | objet limité à `mexc_spot`, `mexc_perp`, `kraken_spot`, `kraken_perp` |
| `fixture` | optionnel, `SYNTHETIC` pour une donnée de test, recopié en provenance |

Par marché : `instrument`, `quote` (gardée telle quelle : USD ≠ USDT),
`listed` (false → `NOT_LISTED`), `bars` (barres fermées), `forming`
(barre en cours, optionnelle), `book` (`at_ms`, `bids`, `asks` en
`[prix, qté]`), et pour un perpétuel `oi` et `funding`
(`[{at_ms, value}]`). Une barre : `open_ms`, `o`, `h`, `l`, `c`, `v`,
et optionnellement `buy_v` + `sell_v` (volumes agresseurs).
**Tous les nombres sont des chaînes décimales** ; un float est refusé.

## 3. Vérification (étape 1)

Seuils de qualité de donnée, pas de décision :

| Contrôle | Raison de rejet |
| --- | --- |
| Barres absentes | `SOURCE_EMPTY` (marché `UNRESOLVED`) |
| Marché absent de l'entrée | `SOURCE_MISSING` (`UNRESOLVED`) |
| Nombre non décimal, champ manquant | `INPUT_INVALID` |
| `l > min(o,c)`, `h < max(o,c)`, `l ≤ 0`, `v < 0`, flux négatif | `BAR_INVALID` |
| `open_ms` hors grille UTC du timeframe | `BAR_MISALIGNED` |
| Barres non croissantes | `BAR_ORDER` |
| Barre manquante dans la série | `BAR_GAP` |
| Dernière barre « fermée » non close à `as_of` | `BAR_NOT_CLOSED` |
| Au moins une barre close manquante à la fin | `STALE_BARS` |
| Carnet de plus de 10 s ou daté dans le futur | `STALE_BOOK` (carnet seul) |
| Niveaux non triés, prix/qté ≤ 0 | `BOOK_INVALID` (carnet seul) |
| Meilleur bid ≥ meilleur ask | `BOOK_CROSSED` (carnet seul) |
| Dernière clôture à plus de 200 bps de la médiane des marchés vérifiés | `PRICE_INCOHERENT` (marché `REJECTED`) |

La cohérence entre marchés exige au moins 3 marchés vérifiés ; sinon
`coherence: NOT_EVALUATED` (avec deux marchés, impossible de dire lequel
est faux). Une barre en cours n'est retenue que si elle suit exactement
la dernière barre fermée.

Un marché `REJECTED`, `UNRESOLVED` ou `NOT_LISTED` **ne publie aucune
valeur**. Un carnet rejeté laisse les indicateurs sur barres publiés et
met `imb_top10` / `spread_bps` en `NOT_AVAILABLE` ; il compte dans
`failures` (`component: book`).

## 4. Jeu d'indicateurs `v1`

| Nom | Définition | Marchés |
| --- | --- | --- |
| `rsi_14` | RSI de Wilder (formule identique à `feature_engineer._rsi`, sans epsilon) | tous |
| `di_plus_14`, `di_minus_14`, `adx_14` | DMI / ADX de Wilder ; ADX exige 28 barres | tous |
| `atr14_pct` | ATR de Wilder / clôture × 100 (diffère de la moyenne simple de `feature_engineer`) | tous |
| `ema20_dist_pct`, `ema50_dist_pct` | (clôture − EMA) / EMA × 100 ; EMA amorcée par SMA | tous |
| `ema20_slope_pct`, `ema50_slope_pct` | variation % de l'EMA sur la dernière barre | tous |
| `vwap_session_dist_pct` | distance % au VWAP (prix typique) depuis 00:00 UTC | tous |
| `volume_rel_20` | volume de la barre / moyenne des 20 précédentes | tous |
| `delta_pct_volume` | (achats − ventes agresseurs) / volume × 100, dernière barre | tous, si `buy_v`/`sell_v` |
| `cvd_session` | cumul achats − ventes depuis 00:00 UTC, en actif de base ; **jamais comparé** | tous, si `buy_v`/`sell_v` |
| `imb_top10` | (Σ qté bids − Σ qté asks) / somme, 10 meilleurs niveaux | tous, carnet vérifié |
| `spread_bps` | (ask − bid) / mid × 10 000 | tous, carnet vérifié |
| `oi_change_pct` | variation % entre les deux derniers relevés d'OI | perpétuels |
| `funding_rate` | dernier funding publié | perpétuels |

MACD et Bollinger sont retirés (redondants avec EMA + ADX et ATR %).
Tout ajout ou changement de formule est une nouvelle version du jeu.

## 5. Sortie `cat.signals.indicators.v1`

```text
{schema, indicator_set, as_of, status, provenance{code_sha, input_sha256, fixture},
 symbols[{base, timeframe, coherence,
          markets{<marché>{exchange, kind, instrument, quote, inputs_sha256, check,
                           reason?, detail?, bars{count, first_open, last_open, forming_open},
                           last_close, book{check, at|reason}, values{...}}},
          gaps{<indicateur>{spot_vs_perp{mexc, kraken}, mexc_vs_kraken{spot, perp},
                            dispersion{state, value, markets_used}}, basis_pct{spot_vs_perp{mexc, kraken}}},
          not_compared[], aggregate{spot, perp: {markets_used, markets_total}}}],
 failures[{market, component, check, reason}]}
```

- Indicateur sur barres : `{closed: cellule, provisional: cellule}` ;
  `provisional` = même calcul avec la barre en cours.
- Indicateur instantané : `{snapshot: cellule, at}` ; OI : `{closed: cellule}`.
- Cellule : `{state: "OK", value: "<décimale>"}` ou
  `{state: "NOT_AVAILABLE", reason, …}`. **UNKNOWN ≠ 0** : jamais de
  valeur par défaut. Raisons : `INSUFFICIENT_BARS` (+ `missing`),
  `FLAT_SERIES`, `ZERO_VOLUME`, `ZERO_REFERENCE`, `INPUT_MISSING`,
  `NO_FORMING_BAR`, `BOOK_REJECTED`, `BOOK_UNRESOLVED`, `EMPTY_BOOK`,
  `SIDE_MISSING`, `FEWER_THAN_TWO_MARKETS`, ou la raison de rejet de la série.
- Valeurs : calcul en `Decimal` (précision 34), publiées arrondies au
  1e-8 (arrondi bancaire), en chaîne, sans exposant.
- Écarts (calculés par le producteur, jamais par l'écran), sur les
  valeurs `closed`/`snapshot` des seuls marchés `VERIFIED` :
  `spot_vs_perp.<ex>` = spot − perp ; `mexc_vs_kraken.<type>` = MEXC − Kraken ;
  `dispersion` = max − min sur les marchés disponibles (≥ 2), avec
  `markets_used`. `basis_pct.<ex>` = (clôture perp − clôture spot) /
  clôture spot × 100.
- `status` : `COMPLETE` (tout vérifié), `PARTIAL` (au moins un rejet de
  marché ou de carnet), `FAILED` (aucun marché vérifié). Une panne n'est
  jamais une population vide.
- Déterminisme : même entrée → mêmes octets (test golden).

## 6. Symbole de référence

`BTC` : `mexc_spot` BTCUSDT, `mexc_perp` BTC_USDT, `kraken_spot` BTC/USD,
`kraken_perp` PF_XBTUSD (identifiants à confirmer par l'audit L0 avant
toute collecte réelle). La fixture `tests/signals_indicators/fixtures/`
est **SYNTHÉTIQUE** (`python -m observability.signals_indicators.synthetic`) ;
elle ne constitue jamais une preuve runtime.

## 7. Usage hors ligne

```bash
python -m observability.signals_indicators --input IN.json --output OUT.json --code-sha <sha>
```

Écriture atomique en 0644. Code retour : 0 publié, 1 `FAILED` publié,
2 entrée refusée (rien n'est écrit).

## 8. Suite (chacun derrière son GO)

L0 audit lecture seule des 4 marchés sur le VPS → collecteurs (lecture
publique) → producteur VPS `/var/lib/cat-signals` → route GET
`/api/operator/v1/signals-indicators` (`OPERATOR_SIGNALS_INDICATORS_PATH`)
→ écran du Radar de signaux.
