# ADR-0019 — Observateur des comptes réels (clés privées, lecture seule)

- **Statut** : **Proposé — v2**, amendé sur demande de l'opérateur (2026-07-31)
- **Date** : 2026-07-31
- **Auteur / signataire** : Mathieu (non signé à ce jour)
- **Rédaction** : Claude Code. Conformément à `.claude/GOVERNANCE.md` §8.2/§8.3,
  un agent peut rédiger un ADR au statut *Proposé* mais **ne peut ni le signer ni
  l'accepter**.
- **Alias opérateur** : « ADR-OBS-001 ». Le dépôt numérote en séquence ; `0018`
  est pris (`docs/ADR-0018-regret-source-canonical-v2.md`, **rangé hors de
  `docs/adr/`** — dette de classement signalée, hors périmètre).
- **Étend** ADR-0007 (passivité) et ADR-0016 (observation passive) sans les
  contredire. **Sort explicitement du périmètre d'ADR-0016** (API publique seule).

> **Changements v1 → v2** : découpage en **Phase A / Phase B** ; **cadence
> différenciée** (soldes horaires, ordres 5 min incrémentaux) ; **base
> d'observation avant toute interface** ; **Event ID chaînable** ;
> `fetch_positions_history` retenu comme source canonique de l'historique réel
> (sonde 3) ; `externalOid` retenu comme marqueur d'origine ; réserve motivée sur
> la section « écart réel / paper ».

---

## Contexte

### La frontière franchie

Jusqu'ici, toute observation du marché passait par l'**API publique**. ADR-0016
fonde son autorisation sous gel architectural précisément là-dessus :

> « API publique MEXC uniquement (aucune clé, aucun ordre possible) »
> — ADR-0016, §Décision, Phase O1

`observability/real_accounts.py` a déjà franchi cette frontière sans ADR dédié.
Cet ADR régularise cet état de fait **et** décide de son extension. Le système
cesse d'être un outil papier qui regarde un marché public : il **observe un
patrimoine réel**. Cette bascule mérite une décision explicite, indépendamment
des montants en jeu (~6 USD à la rédaction).

### Le défaut constaté

| Chemin | Condition | Défaut mesuré |
|---|---|---|
| `advisor_loop.py:6717-6737` | exchange d'exécution présent | equity = **solde USDT seul** ; actifs triés par **quantité**, pas par valeur ; `fetch_positions` appelé mais seul le **compte** est conservé |
| `advisor_loop.py:6754-6762` | mode observation (actuel) | `real_accounts.aggregate()` → **spot uniquement** ; non valorisés exclus du total sans mention ; liste tronquée à `combined[:6]` |

Défaut le plus coûteux : `observability/system_snapshot_renderers.py:105-114`
juxtapose **trois champs API et deux champs paper dans un même bloc, sans
marquage de source**. C'est ce mélange — pas la troncature — qui a produit la
croyance « le bot perd réellement 330 $ ».

### Ce que trois sondes lecture seule ont établi (2026-07-31, VPS)

Exécutées **depuis le VPS** — obligatoire, les clés étant whitelistées par IP :
sonder en local produit un faux négatif. ccxt 4.5.52.

| Appel | Verdict mesuré |
|---|---|
| `spot.fetch_balance` | ✅ |
| `swap.fetch_balance` | ✅ |
| `swap.fetch_positions` | ✅ |
| `swap.fetch_orders` **sans symbole** | ✅ |
| **`swap.fetch_positions_history`** | ✅ **— source canonique de l'historique réel** |
| `swap.fetch_my_trades` **avec** symbole | ✅ |
| `fetch_transfers` (par sens) | ✅ |
| `fetch_deposits` / `fetch_withdrawals` | ✅ |
| `spot.fetch_my_trades` **sans** symbole | ❌ `ArgumentsRequired` |
| `fetchLedger` | ❌ non implémenté par ccxt pour MEXC |

**Une hypothèse de travail est réfutée par la mesure** : on supposait que les clés
spot MEXC ne couvraient pas l'API contrats. C'est faux pour ce compte. Le volet
futures est **établi empiriquement**.

### Le fait qui justifie l'historisation mieux que tout argument

L'opérateur a vu `API Positions : 0` alors qu'une position DOGE existait selon
lui. Au moment de la sonde : `positionMargin: 0` partout, aucune position
ouverte — **le panneau est exact maintenant**. Savoir s'il mentait *à ce
moment-là* est **définitivement impossible** : rien n'historise l'état des
comptes. On ne construit pas cette couche pour mieux voir ; on la construit pour
**pouvoir répondre plus tard à une question posée aujourd'hui**.

---

## Décision

Créer un **observateur des comptes réels** : processus séparé, strictement en
lecture seule, qui mesure et historise l'état des comptes et les événements qui
les affectent, sans jamais influencer une décision.

### Découpage en deux phases

Séparation demandée par l'opérateur, adoptée : elle réduit le risque
architectural et rend la Phase A signable seule.

#### **Phase A — Observateur passif** (objet de cette signature)

Lecture, historisation, restitution. **Rien d'autre.**

- Collecte : soldes spot, soldes futures, positions, ordres, positions fermées,
  transferts, dépôts, retraits.
- Écriture dans une base d'observation dédiée.
- Restitution : vues Telegram **purement descriptives**.
- **Interdits en Phase A** : détection d'anomalie, alerte automatique,
  corrélation, réconciliation, diagnostic, score, verdict. *Seulement la vérité.*

#### **Phase B — Intelligence** (ADR distinct, non autorisée ici)

Détection d'anomalies, alertes, corrélations, réconciliation, diagnostics.
Exigera son propre ADR, une fois la Phase A éprouvée. Aucune ligne de code de
Phase B ne peut être écrite sous cette signature.

### Garanties structurelles (les quatre « jamais »)

L'observateur **ne passe jamais d'ordre**, **ne modifie jamais un portefeuille**,
**ne modifie jamais une configuration**, **ne décide jamais**. Rendues
vérifiables au §Invariants.

### Nommage

Le module **ne portera ni « Layer » ni « Intelligence »** : dans ce dépôt, « Layer »
désigne les couches du graphe de décision et « Scientific Intelligence Layer » le
niveau L3.5 gaté par Observer Certification. Nommer ainsi un observateur passif
inviterait un futur contributeur à le brancher sur la décision.

**Code** : `observation/accounts/` (package `observation/` créé par ADR-0016, déjà
hors process moteur).

### Les quatre collecteurs

#### 1. `AccountCollector` — état instantané

Spot balance, futures balance, marge utilisée, marge libre, equity spot, equity
futures, equity totale, actifs non valorisés, actifs sans prix.

**Valorisation** : `fetch_tickers` en **un seul appel** remplace jusqu'à 60
`fetch_ticker` unitaires et **supprime la raison d'être** du plafond
`_MAX_PRICED_ASSETS = 30` (`real_accounts.py:36`). Coût en baisse, couverture en
hausse.

**Honnêteté** : l'equity publiée est une **borne inférieure explicitement
nommée**, avec le nombre d'actifs non valorisables et le total d'actifs. Aucune
troncature silencieuse — le Top-6 est supprimé.

#### 2. `PositionCollector` — positions ouvertes

Exchange, type, symbole, side, taille, prix d'entrée, prix actuel, PnL latent,
ROI, levier, prix de liquidation, horodatage.

**Seuil de poussière obligatoire** : `fetch_positions` peut rendre 0 alors que le
wallet futures porte un actif non nul (mesuré : `DOGE = 5.2e-9`, `equity: 0`).
Sans seuil, l'observatoire signalerait des positions inexistantes.

#### 3. `TradeCollector` — historique réel et paper

**Amendement majeur v2.** L'historique futures **ne doit pas** être reconstruit en
appariant des ordres : `fetch_positions_history` rend la position fermée complète
en **un appel**, avec tous les champs du format demandé.

| Champ demandé | Source mesurée |
|---|---|
| entrée | `openAvgPrice` |
| sortie | `closeAvgPrice` |
| qty | `closeVol` |
| profit | `realised` (et `closeProfitLoss`) |
| roi | `profitRatio` |
| durée | `updateTime − createTime` |
| levier | `leverage` |
| frais | `fee`, `totalFee`, `holdFee` (funding) |
| liquidation | `liquidatePrice` |
| chaînage | `positionId` |

Échantillon réel mesuré : `positionId 1398747550`, DOGE_USDT, `openAvgPrice
0.10049` → `closeAvgPrice 0.09935`, `realised −1.4978`, `profitRatio −2.293`,
`leverage 200`, `positionShowStatus CLOSED`.

**Conséquence** : le mapping des codes `side` (1..4) reste requis pour la vue
*ordres*, mais **l'historique des trades n'en dépend plus** —
`fetch_positions_history` rend `side: "long"` correctement mappé par ccxt. Le
risque de direction fausse est éliminé sur le flux qui compte.

Schéma **identique** entre réel et paper, pour rendre les deux comparables :

```
event_id, timestamp, exchange, symbol, direction, entry, exit,
qty, fee, profit, roi, duration, origin
```

#### 4. `TransferCollector` — mouvements de fonds

Spot→Futures, Futures→Spot, funding, dépôts, retraits. **C'est le collecteur qui
règle le problème d'origine** : une baisse du solde spot cesse d'être lue comme
une perte, parce que le transfert est **mesuré**. Relevé : SPOT→FUTURES 5.609
USDT (30/07 02:05), FUTURES→SPOT 1.29 USDT (31/07 03:57).

### `origin` — marqueur observable, pas heuristique

**Amendement v2.** ccxt rend `clientOrderId: null`, mais le champ brut MEXC
**`externalOid` est présent** : `"_m_d86b7bca91ea4823b329f3a74cd347da"`.

- **OBSERVÉ** : tous les ordres échantillonnés portent un `externalOid` préfixé
  `_m_`.
- **INFÉRENCE (probable)** : ce préfixe marque les ordres émis depuis
  l'interface MEXC. Support : un seul compte, un seul échantillon, non documenté.
  À confirmer par accumulation avant d'en faire une règle de classement.
- **CERTAIN, indépendamment du préfixe** : `ExecutionEngine.from_env` exige
  `LIVE_TRADING_CONFIRMED` (absent du `.env`) et `_exchange` vaut `None` — le
  moteur est **structurellement incapable** d'émettre un ordre réel. Tout ordre
  observé aujourd'hui est donc d'origine externe. `origin = manual`, sans
  probabilité.

`future_live_bot` deviendra directement observable le jour où le moteur posera
son propre `externalOid` préfixé — **modification du chemin d'exécution, donc
GATED, donc ADR distinct**. Cet ADR réserve la valeur, ne l'autorise pas.

Valeurs : `manual | paper_bot | future_live_bot | unknown`. **`unknown` est
obligatoire** : jamais de classement deviné.

### L'Event Ledger

Journal append-only dont les vues Telegram ne sont que des projections.

#### Event ID chaînable

**Amendement v2, proposition de l'opérateur — adoptée.** Chaque événement reçoit
`EVT-YYYYMMDD-NNNNNN`, séquence quotidienne monotone.

Chaînage `Transfer → Order → Position → Close → PnL`, **chaque lien portant son
propre statut épistémique** :

| Lien | Base | Statut |
|---|---|---|
| Order → Position | `positionId` présent sur l'ordre | **OBSERVÉ** |
| Position → Close | `positionId` identique | **OBSERVÉ** |
| Close → PnL | `realised` du même enregistrement | **OBSERVÉ** |
| Transfer → Order | proximité temporelle seule | **INFÉRÉ — plafonné** |

Le lien `Transfer → Order` est une **inférence causale** : rien dans l'API ne
relie un transfert à un ordre ultérieur. Il doit être marqué comme tel, ou omis.

#### Source de chaque type d'événement

| Événement | Source | Statut |
|---|---|---|
| Transfert, dépôt, retrait | `fetch_transfers` / `fetch_deposits` / `fetch_withdrawals` | **OBSERVÉ** |
| Ordre futures ouvert / fermé / annulé | `fetch_orders` | **OBSERVÉ** |
| Position fermée + PnL réalisé | `fetch_positions_history` | **OBSERVÉ** |
| Position ouverte / augmentée | chaîne d'ordres par `positionId` | **OBSERVÉ** |
| Ordre spot | — | **NON COLLECTABLE** exhaustivement (§Limites) |
| Variation de solde inexpliquée | delta entre snapshots | **INFÉRÉ — plafonné** |

**Conséquence de conception, décisive** : un ledger fondé sur les endpoints
d'historique est **robuste aux trous de sondage** — une position ouverte et
fermée entre deux relevés reste visible. Un ledger fondé sur des deltas de solde
la perdrait, et pourrait fabriquer un faux événement lors d'une panne de source.
**L'historisation repose sur les endpoints d'historique ; les deltas de snapshot
ne servent qu'en dernier recours, explicitement étiquetés INFÉRÉ.**

### Discipline épistémique des sorties

1. **Interdiction d'inférer ce qui est observable.**
2. **Échelle ordinale fermée** (`certain | très probable | probable | spéculatif |
   non démontré | faux`), `docs/protocole_audit_epistemique.md:83-88`. **Aucun
   pourcentage.** Toute inférence appuyée sur un état externe mutable est
   **plafonnée à « très probable »**.
3. **Blocs séparés** `OBSERVÉ` / `INFÉRENCE`. Jamais de bloc `DÉCISION`.
4. **Conclusions d'absence** : « aucun retrait **observé dans les sources lues** »,
   sources énumérées (INV-POWER-001).

Dette à ne pas reproduire : `dip/modules/causal_tree.py:171` code des confiances
`0.90`/`0.85` en dur, sans calibration.

---

## Cadence

**Amendement v2 — la recommandation horaire uniforme de v1 était mauvaise.**

| Flux | Cadence | Justification |
|---|---|---|
| Soldes, equity, actifs | **1 h** | état lentement variable, 3 appels |
| Ordres, positions, positions fermées | **5 min**, **incrémental** (`since` = dernier horodatage vu) | un trade réel mesuré a duré **6 min 37 s** ; à l'heure, la latence de détection dépasse la durée de vie de l'événement |
| Transferts, dépôts, retraits | **1 h** | mouvements rares |

L'objection de v1 (« les endpoints d'historique rendent la cadence indifférente »)
ne vaut que pour l'**exhaustivité**. Elle ne vaut ni pour la **latence de
détection**, ni pour la **reconstruction du cycle de vie d'une position** (prix
courant, PnL latent maximal), qui exige un échantillonnage fin. Elle ignore aussi
le **plafond `limit`** de `fetch_orders` : un sondage trop espacé peut faire
déborder la fenêtre.

Le mode **incrémental** (`since`) borne le coût : seuls les enregistrements
nouveaux sont demandés.

---

## Stockage — la base précède l'interface

**Amendement v2, exigence de l'opérateur — adoptée.** Telegram est une **vue**,
jamais la source. Aucune vue n'est développée avant que la base soit fiable.

- **Emplacement** : `databases/observation/accounts/`, résolu par
  `OBS_ACCOUNTS_DIR` **à l'exécution** (DS-001).
- **Fichiers**, un par flux, rotation quotidienne, `jsonl.gz` append-only :

```
databases/observation/accounts/
    balances_YYYY-MM-DD.jsonl.gz
    positions_YYYY-MM-DD.jsonl.gz
    orders_YYYY-MM-DD.jsonl.gz
    trades_YYYY-MM-DD.jsonl.gz      # positions fermées (historique réel)
    transfers_YYYY-MM-DD.jsonl.gz
    events_YYYY-MM-DD.jsonl.gz      # Event Ledger
```

- `schema_version` sur chaque enregistrement ; écriture atomique
  *write-then-rename* (gabarit ADR-0004) ; exception jamais propagée à l'appelant.
- **Volume** : < 1 Mo/an gzippé pour les soldes ; les ordres à 5 min restent sous
  quelques Mo/an. Trois ordres de grandeur sous les 4-6 Mo/**jour** déjà acceptés
  par ADR-0016.
- **Rétention** : **45 jours**, par alignement sur `OBS_RETENTION_DAYS=45`
  (`observation/market_observer.py:205`) — un seul réglage à comprendre.
  Le volume autoriserait bien davantage si l'audit rétrospectif prime
  (§Questions ouvertes).

**Contraintes d'exploitation**

- `databases/` est **gitignoré ET exclu du déploiement** — filtre vérifié :
  `EXCLUDE_PATTERN='^(databases/|cache/|logs/|tests/|docs/)'`
  (`scripts/deploy_vps.sh:203`). Le répertoire est créé **par le module, à
  l'exécution, sur le VPS**.
  *Corollaire* : `docs/` est dans le même filtre — **cet ADR ne sera jamais
  déployé sur le VPS**. Sans conséquence, mais à savoir lors d'un diagnostic.
- Le Scientific Data Guard (`conftest.py`) fait échouer **toute** session pytest
  si `databases/` change — y compris pour un fichier **ajouté**. Le répertoire
  **doit** être injectable par variable d'environnement.
- `sqlite` écarté : binaire non auditable ligne à ligne, verrou d'écriture,
  incompatible avec la culture append-only du dépôt.

---

## Invariants — passivité rendue vérifiable

| # | Invariant | Vérification |
|---|---|---|
| OBS-A | Aucune méthode d'ordre exposée | test d'introspection : `create_order`, `cancel_order`, `edit_order`, `transfer`, `withdraw` absents de la surface publique — précédent `tests/test_live_exchange_reader.py:148-155` |
| OBS-B | Store **jamais lu** par le chemin de décision | grep d'import bloquant en CI : aucun module `core/`, `src/engine/`, `risk/` ne lit `observation/accounts/` |
| OBS-C | Zéro import moteur depuis l'observateur | test statique sur l'arbre d'imports |
| OBS-D | Écriture **single-writer** | un seul point d'écriture, unité systemd `Type=oneshot` |
| OBS-E | Chemins résolus à l'exécution (DS-001) | contre-modèle à ne pas suivre : `infra/multi_exchange_feed.py:26-27` |
| OBS-F | Imports paresseux, aucune constante capital/risque à la racine (INV-INIT-001) | modèle `observability/real_accounts.py:80` |
| OBS-G | Aucune écriture dans un fichier lu par `load_clean_trades` | INV-3 / INT-09 |
| OBS-H | Garde-fou disque : écriture **sautée** sous seuil | modèle `observation/market_observer.py:204-215` |
| OBS-I | **Phase A ne produit aucune alerte ni verdict** | test : aucun appel d'envoi déclenché par une condition de donnée |

**Sizing** : cet ADR ne modifie **aucune** entrée du moteur. La base de sizing
reste épinglée à `WALLET_PAPER_CAPITAL`. L'equity réelle est **affichage seul**.

---

## Budget d'appels API (mesuré)

**Relevé horaire** (soldes + mouvements) : `spot.fetch_balance` (1),
`swap.fetch_balance` (1), `fetch_tickers` (1), `fetch_transfers` (2 — un par sens,
`fromAccountType`/`toAccountType` obligatoires), `fetch_deposits` (1),
`fetch_withdrawals` (1) = **7 appels/h**.

**Relevé 5 min** (activité), incrémental : `swap.fetch_positions` (1),
`swap.fetch_orders` (1), `swap.fetch_positions_history` (1) = **3 appels**, soit
**36/h**.

**Total ≈ 43 appels/h/exchange.** `rateLimit` ccxt MEXC = 50 ms → ~2 s de throttle
cumulé par heure. À comparer : `real_accounts.py` peut déjà consommer **61 appels
par rafraîchissement** (`_MAX_PRICED_ASSETS=30` × 2 quotes + 1).

**Exécution** : unité systemd `Type=oneshot` + timer, `Nice=10`,
`TimeoutStartSec` borné — gabarit `scripts/systemd/crypto-market-observer.service`.
**Interdit** d'insérer la collecte dans la boucle moteur : mono-thread
(`advisor_loop.py:5060`), garde-fou de charge **désactivé par défaut**
(`ADVISOR_CYCLE_BUDGET_SECONDS=0`, `advisor_loop.py:829`).

---

## Pièges mesurés

1. **`side: "4"` n'est pas mappé par ccxt.** Codes contrats MEXC : `1` = open
   long, `2` = close short, `3` = open short, `4` = close long. Remontés bruts,
   constaté sur 5 ordres sur 10. Mapping explicite et testé obligatoire ; toute
   valeur inconnue → `unknown`, jamais un sens deviné. *Ne concerne que la vue
   ordres* — `fetch_positions_history` rend `side: "long"` correctement.
2. **`clientOrderId: null`** côté ccxt, mais **`externalOid` présent** côté brut :
   c'est lui qu'il faut lire (voir §`origin`).
3. **`fetch_transfers` exige `fromAccountType` ET `toAccountType`** → 2 appels.
4. **Poussière d'arrondi** : seuil obligatoire (voir `PositionCollector`).
5. **Levier élevé sur le compte réel** : `leverage: 143` et `leverage: 200`
   mesurés. Le champ doit être collecté et affiché tel quel — un panneau qui
   l'omet ou le suppose fausserait toute lecture du risque réel.
6. **`fee: 0` sur tous les ordres échantillonnés.** Le champ est remplissable mais
   nul ici ; ne pas coder de frais implicite.

---

## Limites assumées

- **L'historique spot ne peut pas être exhaustif.** `fetch_my_trades` exige un
  symbole, `fetch_orders` exige un symbole en spot, `fetchLedger` absent. Repli :
  détecter les symboles dont le solde a bougé, puis n'interroger que ceux-là.
  L'historique spot est **dérivé et daté, jamais complet rétroactivement** — et
  le panneau doit le dire. *Le futures, lui, est complet* via
  `fetch_positions_history`.
- **Aucune reconstruction rétroactive** au-delà de ce que les endpoints rendent.
- **Un seul compte sondé** : rien n'est établi pour Binance, Kraken, Gate.io.
- **Le préfixe `_m_` n'est pas documenté** : inférence plafonnée, pas une règle.

---

## Réserve motivée — la section « écart réel / paper »

L'opérateur propose une section 🟡 SYNCHRONISATION affichant *écart réel/paper,
écart capital, écart positions, écart exposition*. **Cette section mélange deux
objets sans rapport, et le mot « écart » induit en erreur.**

Le moteur paper trade un capital virtuel épinglé sur un univers épinglé ; le
compte réel est piloté manuellement par l'opérateur. Ce ne sont pas deux mesures
du même objet qui devraient converger : **un « écart » entre eux ne dénote
aucune anomalie**, et le présenter comme tel suggère une réconciliation qui n'a
pas de sens.

Deux objets distincts se cachent derrière, et l'ADR les sépare :

1. **Écart d'observation** (légitime, Phase A) — *ce que le système croit du
   compte réel* contre *ce que l'API dit du compte réel*. C'est le besoin de
   mesure déclaré qui fonde la recevabilité de cet ADR. Section à conserver, sous
   un nom honnête : **« FIABILITÉ D'OBSERVATION »**.
2. **Comparaison opérateur ↔ moteur** (Phase B, descriptive seulement) — deux
   performances côte à côte, chacune avec son N, sans langage de convergence.
   À N faible, elle ne mesure rien (règle du statisticien, INV-POWER-001).

**Interdit sans exception, dans les deux cas** : afficher un seuil suggéré, un
delta de seuil, un « il aurait fallu 58 », ou un compteur cumulé de gains
manqués. `get_threshold_delta()` a été neutralisée exprès (`retourne TOUJOURS 0`,
marquée `[ADR-0007 — PASSIVITÉ]`) ; la ressusciter par l'affichage serait un
contournement de cette neutralisation.

### Sections Telegram retenues (Phase A)

```
🟢 COMPTE RÉEL      spot | futures | positions ouvertes | transferts
🔵 PAPER MACHINE    capital | 20 derniers trades | winrate | PF | drawdown | equity
🟡 FIABILITÉ        dernière synchro | sources lues | sources en échec |
                    actifs sans prix | complétude de l'historique
```

🔴 ALERTES relève de la **Phase B** et n'est pas autorisée ici.

---

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| Module neuf « ExchangeObservatory » | `observability/real_accounts.py` porte déjà cette mission mot pour mot ; `src/telegram/exchange_sync.py` lit déjà positions swap et `fetch_my_trades` (mort, non testé). 3ᵉ chemin → viole `MIGRATION_MATRIX.md:155-173` Q4. **Retenu : étendre l'existant + un appelant hors process.** |
| 8 collecteurs | Décrivent 4 appels : `MarginCollector` est inclus dans `swap.fetch_balance` ; `AssetCollector` recouvre `SpotCollector`. |
| Historique réel par appariement d'ordres | `fetch_positions_history` rend la position fermée complète en un appel, avec `realised`, `profitRatio`, `leverage`, durée et `positionId`. Apparier des ordres serait plus fragile et dépendrait du mapping `side`. |
| Ressusciter `exchange_sync.py` tel quel | Jamais exécuté, zéro test, `_DEFAULT_SYMBOLS` contient `BTCUSDT` sans slash alors que ccxt indexe `BTC/USDT`. Réutilisable après tests, jamais copié à l'aveugle. |
| Réveiller le DIP (D12 `decision_alert`) | `start_dip()` sans appelant : le réveiller activerait D01-D14, plateforme décisionnelle entière restée inerte. Réactivation de couche sous gel → ADR distinct. |
| 7ᵉ mécanisme anti-spam | Six existent, dont quatre morts. Réutiliser `TelegramAlert` (dedup MD5 / 300 s, `scripts/telegram_alerts.py:160-183`). *Phase B.* |
| Collecte dans le cycle moteur | Boucle mono-thread, garde-fou de charge inactif. Processus séparé obligatoire. |
| Event Ledger fondé sur les deltas de solde | Perd les événements entre relevés, fabrique des faux positifs sur panne de source. |
| Cadence horaire uniforme (v1) | Un trade réel mesuré a duré 6 min 37 s. Latence de détection > durée de l'événement. |

---

## Conséquences

**Positives**

- L'equity cesse d'être fausse, et le devient de façon vérifiable.
- Réel et paper deviennent **impossibles à confondre**.
- Une baisse de solde due à un transfert cesse d'être lue comme une perte.
- Le système répond *a posteriori* à « que s'est-il passé à 16 h ? » sans enquête
  manuelle ni reconnexion à l'exchange.
- **Une variable expérimentale est éliminée** : l'écart entre l'état réel des
  comptes et l'état que le système croit observer cesse d'être inconnu.

**Négatives / compromis**

- Un processus de plus à exploiter, superviser, déployer.
- Davantage de code manipulant des clés : scope read-only, mais **exposition
  accrue**.
- ~43 appels API/h/exchange.
- Un store de plus (rotation, rétention, disque).
- L'historique **spot** restera structurellement incomplet — source de questions
  récurrentes s'il n'est pas étiqueté comme tel.

**Règles induites**

1. Le store n'est **jamais** lu par le chemin de décision.
2. L'interface Telegram **ne contient aucune logique métier** : elle projette le
   ledger, elle ne le calcule pas.
3. Toute sortie affirmant une cause, une origine ou une absence respecte la
   discipline `OBSERVÉ` / `INFÉRENCE`.
4. Aucun seuil suggéré, delta de seuil, ni compteur de gains manqués.
5. Toute extension du périmètre des clés au-delà de la lecture exige un ADR.
6. **Aucun code de Phase B sous cette signature.**

---

## Recevabilité sous gel architectural

Test cumulatif `.claude/GOVERNANCE.md` §1.2 :

1. **Éliminer autant de variables expérimentales qu'on en crée** — satisfait :
   l'écart réel/observé, aujourd'hui non mesuré, devient mesuré.
2. **Ne changer aucune entrée lue par le moteur** — satisfait (OBS-B, OBS-G,
   sizing inchangé).
3. **Se rattacher à une hypothèse ou à un besoin de mesure déclaré** — **aucune**
   hypothèse H1-H6 ne porte sur les comptes réels. Rattachement par la seconde
   branche : **besoin de mesure déclaré = la réconciliation entre l'état réel des
   comptes et l'état que le système croit observer**, qui conditionne la validité
   de toute lecture de capital. Déclaré ici, par écrit, comme l'exige la règle.

**INV-ROI-001** : cet ADR **n'accélère pas N**. Il relève de la voie *validité*,
pas *débit*. Seul T1 a une valeur immédiate à coût nul.

---

## Découpage en tickets (INT-16 : ≤ 300 lignes **ou** ≤ 4 fichiers)

Ordre arrêté par l'opérateur (v2), découpage fixé **avant** la première ligne de
code (INV-TRACE-001).

| # | Ticket | Contenu | Dépend de |
|---|---|---|---|
| T0 | **Cet ADR** | signature opérateur (Phase A) | — |
| **T1** | **Corriger l'affichage actuel** | spot/futures séparés, equity correcte (borne inférieure nommée), positions correctes, fin du Top-6, `fetch_tickers` unique, séparation réel/paper + étiquetage de source, test de provenance | **— aucune autorisation nouvelle** |
| T2 | Collecteur d'événements | ordres, transferts, positions, positions fermées + **mapping `side`** + lecture `externalOid` + tests avec injection de fabrique ccxt | T0 |
| T3 | Base historique JSONL | store, Event ID, rotation, rétention, garde-fou disque + tests | T2 |
| T4 | Telegram History | vues REAL / PAPER, projection pure | T3 |
| T5 | *(Phase B)* Détecteur d'anomalies | **hors périmètre de cette signature — ADR distinct** | Phase B |
| T6 | Unité systemd + timer | exploitation, cadences différenciées | T3 |

**T1 ne dépend pas de cet ADR** : aucun module créé, aucun appel ajouté, aucun
fichier écrit, aucune clé touchée. Livrable même si l'ADR est refusé.

---

## Questions ouvertes — décisions d'opérateur

1. **Rétention** : 45 jours (aligné sur l'existant) ou davantage pour l'audit
   rétrospectif ? Le volume ne contraint pas.
2. **Périmètre exchanges** : MEXC seul (seul sondé), ou sonder
   Binance/Kraken/Gate.io avant d'élargir ? Recommandation : MEXC seul.
3. **Canaux Telegram** : réutiliser `REAL_ACCOUNT_BOT_TOKEN` ou créer de
   nouvelles identités ? 6 identités déclarées, 4 configurées, deux fallbacks
   silencieux pouvant faire converger des flux censés distincts. Recommandation :
   **réutiliser**, n'ouvrir qu'après une table de nomenclature.
4. **Défaut à corriger avant T4** : le rapport ne tronque ni ne découpe
   (`advisor_loop.py:925-939`) — au-delà de 4096 caractères le message est
   **perdu** avec un simple `log.warning`. Ajouter des blocs sans traiter ça
   aggrave une perte silencieuse non mesurée.

---

## Prérequis de sécurité

- **Le PAT GitHub en clair dans `.git/config`** (constaté le 2026-07-28) n'est
  toujours pas révoqué. **Révocation recommandée avant T2.**
- Les permissions des clés ne sont vérifiées par aucun code : les sondes du
  2026-07-31 sont un constat ponctuel, pas une garantie permanente. Le collecteur
  doit distinguer `AuthenticationError` de `PermissionDenied` et rendre l'échec
  **visible par source**, jamais silencieux.
- Aucun nouveau fichier de configuration portant des clés.

---

## Signature — Phase A uniquement

```
Statut : Proposé (v2)
Décision de l'opérateur : ____________________  (Accepté / Refusé / Amendé)
Date : ____________________
```

Cette signature n'autorise que la **Phase A**. La Phase B (détection, alertes,
corrélations, réconciliation) exigera un ADR distinct. Tant que ce bloc n'est pas
rempli, **aucun ticket T2 et suivants ne peut être ouvert** ; T1 reste livrable.

---

## Références

- [ADR-0007 — Observabilité passive](0007-observabilite-passive-separation.md)
- [ADR-0016 — Univers d'observation MEXC](0016-univers-observation-mexc-complet.md)
- [ADR-0004 — Rejection Store JSONL](0004-rejection-store-jsonl.md)
- [ADR-0008 — DS-001 résolution des chemins](0008-ds001-runtime-path-resolution.md)
- [CLAUDE.md](../../CLAUDE.md) — gel architectural, Règle du statisticien
- `docs/protocole_audit_epistemique.md` — échelle ordinale, INV-POWER-001
- Sondes de permissions et de champs du 2026-07-31 — résultats au §Contexte
