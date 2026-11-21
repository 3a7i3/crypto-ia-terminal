# MARKET-DERIVATIVES-STRESS-01 — stress du levier, déséquilibre des dérivés et périodicité

Chantier rattaché à III-R3.4 de [#568](https://github.com/3a7i3/crypto-ia-terminal/issues/568)
(funding / basis / OI) ; demande opérateur du 2026-11-20 pour le domaine Marché.
Statut de cette tranche : **SOURCE_ONLY / OFFLINE / NON_DEPLOYED**. Elle n'autorise
aucune collecte, aucun accès VPS, aucun service, aucun déploiement et ne touche pas
l'epoch active (#286 ACTIVE). Suite de [MARKET-MULTI-VENUE-02](MARKET_MULTI_VENUE_02.md).

## Pourquoi un produit distinct

`MarketVenueComparison` qualifie un **carnet** (bid/ask) par sa date de carnet. Le stress du
levier repose sur d'autres faits : prix de marque et d'indice, funding, open interest (OI),
échéances, historique court, et — pour la périodicité — les instants de transactions. Les
mélanger casserait le contrat fermé de #536. `MarketDerivativesStress` 1.0.0 est donc un produit
frère, avec son artifact, son lecteur, sa route et son validateur, sur le même modèle.

## Placement dans l'app

| Onglet Marché | Ajout | Composant |
|---|---|---|
| **Comparaison des plateformes** | section « Stress du levier et déséquilibre des dérivés » sous la comparaison des carnets : prix, prime vs indice, base vs spot, funding, OI, fenêtres 1 h / 4 h / 24 h, écarts entre plateformes | `DerivativesStressPanel.tsx` |
| **Flux** | section « Périodicité temporelle des transactions » : concentration aux frontières (quart d'heure) face à sa part attendue et à un placebo | `TradeTimingPanel.tsx` |

Les deux sections lisent le **même artifact** (`GET /api/operator/v1/derivatives-stress`) mais
sont montées par leur onglet : un onglet inactif ne lit rien. Chaque section est indépendante des
autres sources de son onglet : une comparaison de carnets ou un Flux indisponible ne masque pas
le stress, et inversement. Source absente : `DERIVATIVES_STRESS_NOT_CONFIGURED` (503) est présenté
comme « source non configurée » (composant `MarketSourceNotice`), jamais comme un marché vide.

## Plusieurs plateformes, dès maintenant

Le roster est une liste explicite de **bindings** `(plateforme, symbole natif, InstrumentKey,
mapping_id, mapping_sha256)`. Aucune table fermée de plateformes n'existe dans ce produit : un
identifiant de plateforme est `[a-z][a-z0-9_]{1,30}` et il est admis par un binding revu en amont.
Pour **ajouter un exchange** il faut seulement :

1. ses bindings (un par instrument suivi) et le décodeur/adaptateur qui produit des `LegObservation` ;
2. optionnellement un nom d'affichage dans `frontend/src/lib/venueNames.ts` (sinon l'identifiant s'affiche).

Aucun changement du builder, du schéma, du lecteur, de l'API ou des panneaux. **Une plateforme
n'a pas besoin de tout fournir** : chaque champ absent (prix d'indice, funding, OI, historique,
transactions) donne un bloc `NOT_AVAILABLE` avec sa raison, jamais un zéro. MEXC et Kraken sont la
première configuration prévue ; la fixture synthétique ajoute une plateforme fictive (`exchange_c`)
pour prouver ce point. Les sous-jacents sont `(base, quote)` : BTC/USD et BTC/USDT restent des
groupes distincts, comme dans #536.

## Contrat publié (1.0.0)

`authority=OBSERVATIONAL_TELEMETRY`, `execution_authority=false`, `costs_funding_fx_included=false`,
`evidence_kind=OBSERVATION|SYNTHETIC`, politique de qualité explicite
(`max_age_ms`, `max_skew_ms`, `history_tolerance_ms`, sans défaut de trading), décompte
attendu / reçu / qualifié, `valid_until_utc` = plus ancienne cotation qualifiée + âge maximal.
Validation fermée côté Python (`observability/market_stress/schema.py`) et côté React
(`frontend/src/lib/derivativesStress.ts`) ; le TypeScript n'accepte que ce que le producteur réel
a généré (preuve cross-stack). Décimaux en chaînes exactes, dates UTC, valeurs manquantes `null`.

Par jambe (plateforme × instrument) :

| Bloc | Définition | Indisponible quand |
|---|---|---|
| `premium_to_index` | `(prix − indice) / indice × 10 000`, en bp, même observation | prix ou indice absent ; spot : `NOT_APPLICABLE` |
| `basis_vs_spot` | `(prix dérivé − spot) / spot × 10 000`, en bp, contre le spot de **même plateforme**, sinon le premier spot qualifié du roster ; annualisé simple pour une échéance | pas de spot qualifié, horloge / sémantique de date différentes, décalage > `max_skew_ms` |
| `funding` | taux publié tel que reçu avec son **intervalle** ; équivalent 8 h et annualisé simple = conversions linéaires d'affichage | taux ou intervalle absent (jamais supposé), prochain funding passé, échéance datée : `NOT_APPLICABLE` |
| `open_interest` | valeur et unité publiées (`BASE`, `QUOTE`, `CONTRACTS`) ; notionnel en devise de cotation | notionnel seulement si exact : contrats sans taille de contrat → `CONTRACT_SIZE_UNKNOWN` |
| `windows` | 1 h, 4 h, 24 h : variation de prix (bp) et d'OI (%), avec leur **sens** `UP/DOWN/FLAT` | aucun échantillon à la cible ± tolérance |
| `timing` | voir ci-dessous | série absente, trop courte, heure non qualifiée |

Par sous-jacent : paires orientées d'un même instrument (écart de prix en bp, écart de funding par
8 h, décalage), et `open_interest_total` — **publié seulement si tous les dérivés attendus sont
couverts** ; sinon `PARTIAL_COVERAGE` avec la liste des manquants (une somme partielle ne se lit
pas comme un total).

Ce qui n'est **pas** publié : aucun score composite, classement, seuil de « stress » ni
interprétation des signes (« longs qui s'accumulent » etc.). Une prime élevée n'est pas un verdict ;
un signal composite serait une nouvelle variable expérimentale (Scientific Debt Rule) qui exige sa
propre décision et son protocole.

## Périodicité algorithmique (quarts d'heure)

Méthode descriptive sur une série de transactions fournie (`TradeTape`) :

- **Heure moteur d'appariement uniquement** (`MATCHING_ENGINE`) ; l'heure de réception est refusée
  (`TIMESTAMP_KIND_NOT_MATCHING_ENGINE`). Résolution déclarée (1, 10, 100, 1 000 ms) : une heure hors
  grille est refusée.
- Frontières = multiples de la période depuis l'époque UTC (:00/:15/:30/:45 pour 900 s). Grille
  pré-enregistrée : (60 s, 1 s), (300 s, 1 s), (900 s, 0,5 / 1 / 2 / 5 s), (3 600 s, 1 s).
- Pour chaque entrée : part des transactions et du volume à ± rayon d'une frontière, **part attendue
  sous répartition uniforme sur la grille d'horodatage déclarée** (cellules exactes), facteur
  (lift) et **placebo** (frontières décalées d'une demi-période). Histogramme de 900 intervalles d'une
  seconde (phase dans le quart d'heure) ; l'interface en montre ±30 s autour de la frontière.
- Minimum 1 000 transactions, maximum 500 000, sinon `SAMPLE_TOO_SMALL` / `TAPE_TOO_LARGE`.
- **Aucune p-valeur** : les rafales d'exécution rompent l'indépendance, un test serait trompeur. Les
  périodes de 1 et 5 min contiennent les frontières du quart d'heure ; leurs facteurs sont liés.

Ceci est une mesure, pas un signal. Une piste de recherche (validation sur plusieurs jours
séparés, plateformes et fenêtres, protocole pré-enregistré) relève de Research offline sur dataset
immuable ; elle n'alimente aucun feedback vers l'epoch active.

## Fichiers

| Emplacement | Rôle |
|---|---|
| `observability/market_stress/models.py` | Bindings, observations, échantillons, série de transactions |
| `observability/market_stress/metrics.py` | Métriques exactes (Decimal), constantes pré-enregistrées |
| `observability/market_stress/publication.py` | Construction pure depuis un roster explicite |
| `observability/market_stress/schema.py` | Validation fermée |
| `observability/operator_api/derivatives_stress_reader.py` | Lecture bornée (4 Mo), fichier régulier sans lien symbolique, fraîcheur FRESH/STALE/UNRESOLVED |
| `observability/operator_api/app.py` | `GET /api/operator/v1/derivatives-stress`, `Cache-Control: no-store`, non configuré par défaut (503) |
| `frontend/src/lib/derivativesStress*.ts`, `stressLabels.ts`, `venueNames.ts` | Contrat, client GET-only, libellés |
| `frontend/src/components/DerivativesStressPanel.tsx`, `TradeTimingPanel.tsx`, `market-stress.css` | Sections de l'app |
| `tests/market_stress/`, `tests/cross_stack/generate_derivatives_stress_fixture.py`, `frontend/src/test/derivativesStress.compat.test.tsx`, `frontend/scripts/capture_derivatives_stress_visual.mjs` | Tests et preuves |

Le chemin du fichier lu serait fourni par `OPERATOR_DERIVATIVES_STRESS_PATH` après une admission
distincte. Aucun fichier actif ni variable du runtime n'est ajouté ici.

## Preuves et limites

Toutes les valeurs des tests sont **inventées** ; elles empruntent la chaîne réelle
`builder → fichier → lecteur → route FastAPI → validateur React → vue`. La preuve navigateur
(captures et `checks.json`, 14 jours en CI) intercepte les seuls GET d'artifact, en clair/sombre,
à 1440 / 768 / 393 px, états synthétique, périmé, partiel, non résolu, 503 et contrat invalide.

Commandes (depuis la racine, Python 3.11) :

```bash
python -m pytest -q tests/market_stress tests/cross_stack/ tests/market_venues/
python -m tests.cross_stack.generate_derivatives_stress_fixture --out frontend/.cross-stack-fixtures
cd frontend
CROSS_STACK_FIXTURES_DIR="$PWD/.cross-stack-fixtures" npx vitest run src/test/derivativesStress.compat.test.tsx
npm run build
CROSS_STACK_FIXTURES_DIR="$PWD/.cross-stack-fixtures" node scripts/capture_derivatives_stress_visual.mjs
```

Limites à ne pas effacer :

- **Aucun décodeur natif ni collecteur.** Les formats des produits dérivés de MEXC et Kraken
  (tickers de marque/indice, funding, OI, historique, transactions) n'ont pas été relus ici ; aucun
  endpoint n'a été appelé. Chaque décodeur futur exige sa revue de format officiel, sa sémantique
  de date et son unité d'OI (base, devise de cotation ou contrats) avant tout binding.
- La **série de transactions** est une entrée distincte de la publication Flux (#553) : elle exige
  sa propre capture bornée et sa qualification d'heure.
- La conversion annuelle du funding et de la base est linéaire (365 j), indicative.
- Un échantillon d'historique est une déclaration du producteur (même nature de prix, même unité d'OI).
- Les fixtures ne prouvent ni connexion, ni fraîcheur, ni activité d'un collecteur.

## Prochaines décisions (non autorisées ici)

1. Revue des formats natifs MEXC (contrats) et Kraken (futures), bindings et unités d'OI : matrice documentaire
   dans [NATIVE_FORMAT_MATRIX](../research/market_derivatives_stress_01/NATIVE_FORMAT_MATRIX.md) (comparaisons valides, bloquées et leurs conditions de levée).
2. Univers indépendant, accès, rate limits, coûts, horloges, custody de la capture.
3. Capture bornée, publication passive et rollback, chacun sous sa gate runtime.
4. Éventuel indicateur composite de stress : protocole pré-enregistré par Research, jamais par l'interface.
