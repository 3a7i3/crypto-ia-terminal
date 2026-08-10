# DESIGN BRIEF — Crypto AI Terminal Dashboards
> Document de référence pour Anara — audit complet UI/UX
> Généré le : 2026-05-15 | Mis à jour : 2026-05-18
> Version schéma Anara : 1.1 (25 modules, 6 layers)

---

## 1. SYSTÈME DE COULEURS GLOBAL (`anara_context/color_system.json`)

### Backgrounds
| Token | Hex | Usage |
|-------|-----|-------|
| `background.dark` | `#0f172a` | Fond principal de l'app |
| `background.card` | `#1e293b` | Fond des cartes, métriques |
| `background.card_hover` | `#334155` | Hover / onglet actif |
| `background.border` | `#334155` | Bordures, séparateurs |

### Textes
| Token | Hex | Usage |
|-------|-----|-------|
| `text.primary` | `#f8fafc` | Titres, valeurs importantes |
| `text.secondary` | `#94a3b8` | Labels, descriptions |
| `text.muted` | `#475569` | Timestamps, infos secondaires |

### Statuts
| Token | Hex | Usage |
|-------|-----|-------|
| `status.ok` | `#22c55e` | Succès, signal bull, win |
| `status.warning` | `#f59e0b` | Attention, sideways, watch |
| `status.error` | `#ef4444` | Erreur, signal bear, loss |
| `status.neutral` | `#6b7280` | Inactif, HOLD |
| `status.info` | `#3b82f6` | Info, testnet mode |

### Couleur d'action principale
| Token | Hex | Usage |
|-------|-----|-------|
| `ACCENT` | `#00e0ff` | Signal actionable (TRADE), onglet actif Decision Trace |

### États de conviction
```
VERY_HIGH  #22c55e   HIGH      #84cc16
MEDIUM     #f59e0b   LOW       #f97316
SKIP       #6b7280
```

### Régimes de marché
```
TREND_BULL  #22c55e   TREND_BEAR  #ef4444
RANGE       #6b7280   VOLATILE    #f59e0b
UNKNOWN     #9ca3af
```

### Lifecycle DecisionPacket
```
CREATED              #6b7280   SIGNAL_GENERATED  #6b7280
CONTEXT_ENRICHED     #3b82f6   REGIME_VALIDATED  #8b5cf6
RISK_EVALUATED       #f59e0b   APPROVED          #14b8a6
EXECUTION_PENDING    #f97316   EXECUTED          #22c55e
MONITORED            #22c55e   CLOSED            #6b7280
POSTMORTEM_ANALYZED  #6b7280   REJECTED          #ef4444
EXPIRED              #92400e   VETOED            #7f1d1d
```

### Post-mortem
```
VALIDATED  #22c55e   LUCKY    #84cc16
UNLUCKY    #f59e0b   MISTAKE  #ef4444
```

### Exchanges (Multi-Exchange dashboard)
```
Binance     #f3ba2f   Bybit   #f7a600
OKX         #00d4aa   MEXC    #1d9bf0
Hyperliquid #a855f7
```

---

## 2. TYPOGRAPHIE ET COMPOSANTS COMMUNS

### Font sizes utilisées
- Titre section : `1rem` bold `#f8fafc`
- Description / subtitle : `0.8-0.9rem` `#94a3b8`
- Badge signal : `0.7rem` bold monospace
- Chip indicateur : `0.67rem` bold monospace
- Port / meta info : `0.7rem` monospace `#475569`
- Timeline entry : `0.72-0.75rem`
- Table cells : Streamlit default

### Composants récurrents

**Metric card** (Streamlit st.metric)
- Background: `#1e293b` | Border: `1px solid #334155` | Radius: `8px` | Padding: `10px 14px`

**Signal badge** (inline HTML)
- TRADE : bg `#00e0ff`, fg `#0a0c12`
- WATCH : bg `#f59e0b`, fg `#0a0c12`
- HOLD  : bg `#334155`, fg `#94a3b8`
- BLOCK : bg `#ef4444`, fg `#fff`

**Module card** (grid status)
- `border-left: 3px solid <status_color>` | bg `#1e293b` | radius `6px` | padding `7px 12px`

**Verdict bar**
- `border-left: 4px solid <verdict_color>` | bg `#1e293b` | radius `6px` | padding `0.55rem 1rem`

---

## 3. DASHBOARDS — INVENTAIRE COMPLET

---

### 3.1 COCKPIT UNIFIÉ — `localhost:8500`

**Fichier :** `dashboard_unified.py` _(dashboard_hub.py non créé — remplacé)_
**Titre page :** "Crypto AI Terminal" (icon 🎛️)
**Layout :** `wide`, sidebar collapsed

#### Structure actuelle
```
[TITRE] "Crypto AI — Dashboard Hub"
[subtitle] "Lancez et accédez à tous les dashboards depuis un seul endroit."
[divider]

[GRILLE 2 colonnes] — 10 cartes dashboard
  Colonne gauche  : Live, Decision Trace, Risk, Positions, Execution Health
  Colonne droite  : Master, Command Center, Evolution, Compare Multi, Multi-Exchange

  Par carte :
    [TAG badge coloré] [Nom dashboard]
    [Description courte]
    [Port : fichier.py]
    [btn Lancer/Arrêter] [btn Ouvrir] [● En cours / ○ Arrêté]

[divider]
[footer] "N dashboard(s) actif(s) — Ce hub tourne sur le port 8500..."
```

#### Couleurs des tags
| Dashboard | Tag | Couleur |
|-----------|-----|---------|
| Live Dashboard | PRINCIPAL | `#22c55e` |
| Master Dashboard | MASTER | `#3b82f6` |
| Decision Trace | DECISIONS | `#8b5cf6` |
| Command Center | CONTRÔLE | `#f59e0b` |
| Risk Dashboard | RISQUE | `#ef4444` |
| Positions | POSITIONS | `#14b8a6` |
| Evolution | LEARNING | `#f97316` |
| Compare Multi | ANALYSE | `#6b7280` |
| Execution Health | EXECUTION | `#00e0ff` |
| Multi-Exchange | LIVE DATA | `#a855f7` |

#### Points d'amélioration possibles
- Les boutons Lancer/Arrêter/Ouvrir ne sont pas alignés visuellement sous chaque carte
- Pas de preview / screenshot miniature par dashboard
- Status "En cours / Arrêté" peu visible (petit texte)

---

### 3.2 MASTER DASHBOARD — `localhost:8502`

**Fichier :** `dashboard_master.py`
**Titre page :** "Crypto AI — Master Dashboard" (icon 🤖)
**Layout :** `wide`, sidebar avec toggle "Mode compact"

#### Structure actuelle

**Header (fixe)**
```
[col 5/6] "## Crypto AI — Master Dashboard"
[col 1/6] [small "auto 20s"] [btn ↻ Rafraîchir]
[divider]
```

**Onglets (4)**
```
↗ Vue Globale | ● Marchés Live | ⚡ Analyse Décisions | ■ Positions
```

---

**TAB 1 — Vue Globale**
```
[ROW 6 métriques]
  Capital $  |  Cycle #  |  Durée cycle ms  |  Latence exchange ms  |  Uptime %  |  Safe Mode

[ROW 4 métriques]
  Symboles analysés  |  Signaux actionnables  |  Trades exécutés  |  Refusés

[caption] "Dernière mise à jour : ... | Cycle #..."
[Exchange status] texte coloré inline

[2 colonnes]
  Gauche : table "Couches de refus — cycle courant" (Couche | Refus)
  Droite : table "Régimes détectés ce cycle" (Régime | Symboles)

[divider]
[titre] "Modules système"
[GRILLE 4 colonnes — 18 modules]
  Chaque module : card avec border-left coloré + tag OK/absent/vide

[divider]
[2 colonnes]
  Gauche : line_chart "Capital (150 derniers cycles)" height=175
  Droite : line_chart "Durée cycle ms" height=175

[si non-compact] bar_chart "Refus cumulés par couche" height=190
```

---

**TAB 2 — Marchés Live**
```
[titre] "Signaux live — Cycle #..."
[dataframe] tableau principal (Symbole | State | Prix | Score | Conviction | Régime | RSI | BB% | ATR% | MACD | EMA | Squeeze | Gate | Trade)

[titre] "Détail par symbole"

[MODE COMPACT] 3 colonnes : badge state + progress bar par symbole

[MODE NORMAL] Par symbole (rangée verticale) :
  [glyph coloré] [nom symbole] [signal badge] [score /100]
  [chips] RSI | BB% | ATR | MACD | EMA | Squeeze
  [progress bar 0-100]

[divider]
[expander] "◎ Mini graphe live — Score / PnL / Exposition"
  Radio : Score signal | PnL cumulé | Exposition
  → line_chart height=160
```

---

**TAB 3 — Analyse Décisions**
```
[verdict bar] texte coloré selon état
[caption] "N décisions · K cycles · dernier cycle..."

[ROW 5 métriques]
  Total décisions | HOLD (%) | Trades exécutés | Positions fermées | Refus explicites

[divider]
[bar_chart] "Distribution des scores de signal" height=190
[caption] "Moyenne X · Max Y · Min Z"

[2 colonnes]
  Gauche : table "Régimes" (Régime | Count)
  Droite : table "Conviction · Personnalité" (Type | Valeur | Count)

[si non-compact]
  [line_chart] "Évolution du score par cycle" height=210
  [caption] seuil mental à 70

[divider]
[table] "Raisons de refus — top modules" (Raison | Occurrences)

[si non-compact]
  [table] "Modules qui valident (passed_by)" (Module | Validations)

[divider]
[titre] "Cohérence Signal → Résultat (post-mortem automatique)"

[ROW 5 métriques]
  Trades analysés | VALIDATED % | LUCKY % | UNLUCKY % | MISTAKE %

[verdict bar] modèle cohérent / incohérent / signal utile / neutre

[2 métriques]
  Win rate score ≥ 70 | Win rate score < 70

[expander] "Détail trade par trade" → dataframe

[divider]
[table] "50 dernières décisions" (Heure | Symbole | Décision | Score | Régime | Conviction | Prix | Raison)
```

---

**TAB 4 — Positions**
```
[titre] "Positions ouvertes"
[dataframe] brut des positions snapshot | ou info "Aucune position ouverte"

[divider]
[titre] "Historique des positions fermées"
[dataframe] 100 derniers exits (Symbole | Résultat | PnL% | PnL$ | Régime | Conviction | Direction | Entrée | Sortie | Durée | Raison sortie | Paper | Date)

[divider]
[titre] "Performance globale"
[ROW 6 métriques]
  Total trades | Win Rate | PnL total | PnL moyen/trade | Meilleur trade | Pire trade

[titre] "PnL cumulé ($)"
[line_chart] height=175

[si non-compact] table "Raisons de sortie" (Raison | Count)
```

---

### 3.3 RISK DASHBOARD — `localhost:8505`

**Fichier :** `dashboard_risk.py`
**Titre page :** "Crypto AI — Risk Dashboard" (icon 📊)
**Layout :** `wide`, sidebar EXPANDED

> Note : ce dashboard utilise un style moins unifié que les autres — pas du color_system.json pour le fond, emojis dans titres, style Streamlit par défaut pour le fond.

#### Sidebar
```
⚙️ Paramètres
  slider "Shadow trades affichés" (10-200, défaut 50)
  slider "Lignes de log" (50-500, défaut 200)
  checkbox "Afficher log brut"
  [divider]
  "Commandes Telegram" : /STATUS /SAFE_MODE /RESUME /STOP_ALL /CLOSE_ALL
  [divider]
  [btn 🔄 Actualiser maintenant]
```

#### Corps (vertical, pas de tabs)
```
[TITRE] "📊 Crypto AI Terminal — Risk Dashboard"
[caption] "Actualisation automatique toutes les 15s | Mode: ADVISOR ONLY"

[ROW 1 — 4 métriques]
  ✅/❌ Exchange Binance (latence ms)
  🧪 Shadow Trades (slippage moyen)
  📋 Ordres loggés (rejetés)
  📈 Dernier signal (score)

[divider]
[ROW 2 — Signaux par symbole]
  "Signaux actifs par symbole"
  [N colonnes = N symboles] par symbole :
    Nom symbole
    Prix $...
    Signal : BUY/SELL/HOLD coloré
    [progress bar] Score X/100
    caption Régime | Gate

[divider]
[ROW 3 — Graphique historique]
  "Historique des scores (derniers cycles)"
  [line_chart] pivot par symbole, index=timestamp, width="stretch"
  caption "Seuils: 70+ actionable | 50-69 surveiller | <50 pas d'action"

[divider]
[ROW 4 — Shadow trades]
  "🧪 Shadow Trades simulés"
  [dataframe] 20 derniers shadow trades
  [3 métriques] Slippage moyen | Slippage max | Latence moyenne

[divider]
[ROW 5 — Journal ordres]
  "📋 Journal des ordres"
  [dataframe] ou info message

[divider]
[ROW 6 — Trade Replay — expander]
  "🔁 Trade Replay"
  Sous-expander 1 : "Rejouer un trade par ID" → text_input + btn Rejouer
  Sous-expander 2 : "Recherche dans les shadow trades" → 3 selectbox + slider + btn

[divider]
[ROW 7 — Confidence Score — expander ouvert]
  "🔍 Analyse de confiance par symbole"
  selectbox symbole
  3 métriques : Score global | Signal | Régime
  progress bar score
  [si shadow trade] composants MTF/Régime/Qualité/Mémoire avec progress bars
  verdict coloré (success/warning/info)
  [si historique] line_chart score pour ce symbole

[divider]
[ROW 8 — Monte Carlo — expander fermé]
  "🎲 Monte Carlo Stress Test"
  3 cols de paramètres : Capital, win rate, gains, pertes, chemins, trades, position%
  checkbox "Calibrer depuis shadow trades"
  [btn Lancer] → tableau scenarios + verdict + bar_chart survie

[si show_raw_log]
  "📄 Log brut" avec coloration ERROR/WARNING/SIGNAL ACTIONABLE

[caption] "Dernière actualisation: HH:MM:SS"
```

---

### 3.4 DECISION TRACE — `localhost:8503`

**Fichier :** `dashboard_decision_trace.py`
**Titre page :** "Decision Trace" (icon 🧠)
**Layout :** `wide`, sidebar EXPANDED

#### Sidebar
```
## 🧠 Decision Trace
---
checkbox "Auto-refresh (5s)"
selectbox "Date (UTC)" [rotation fichiers datés]
caption "Source : chemin/fichier"
"N packets chargés"

### Filtres
selectbox "Symbole" [Tous + liste]
selectbox "État final" [Tous + liste]
"N packets filtrés"

### Packet sélectionné
selectbox "Packet" [liste timestamps + symbole + side + état]
```

#### Corps
```
[TITRE] "# Decision Trace"

[ROW 5 métriques]
  Packets | Rejetés % | Approuvés % | Exécutés | Conf. moy.

[divider]

[ONGLETS 5]
  ⟶ Timeline | ~ Confidence | ≡ Reasoning | ✗ Rejets | ⊕ Sovereignty
```

---

**TAB 1 — Timeline**
```
[2 colonnes 1:2]

Colonne gauche (méta) :
  section-header "Identité"
  Packet [id tronqué à 16 chars]
  Symbole — side
  Régime
  Conviction
  État final [badge coloré]
  Confiance finale X/100

  [si features pb_*]
    section-header "Portfolio"
    3 métriques : Exposition % | Corrélation | Concentration %
    Metric : Size factor ×N

Colonne droite (lifecycle) :
  section-header "Lifecycle"
  [liste de transitions]
    [badge état coloré] by [acteur] — [durée] — conf X→Y (+Z)
    ↳ [raison tronquée à 120 chars]
    │ séparateur
```

---

**TAB 2 — Confidence**
```
[Plotly Figure — Bar + Line overlay]
  Bars : impacts positifs (#22c55e) / négatifs (#ef4444) par acteur
  Line : confiance cumulée (#00e0ff, dash=dot)
  Background : paper=#0a0c12, plot=#0e1117
  Axes : gridcolor=#1a1e2a, tickangle=-30
  Légende : bg=#111420
  Height : 380px

[dataframe] table détail (Actor | Category | Severity | Impact | Message)
```

---

**TAB 3 — Reasoning Feed**
```
[section-header] "N packets · N entrées"

[3 colonnes filtres]
  multiselect "Actor"
  multiselect "Category"
  multiselect "Severity" [INFO/WARNING/CRITICAL/FATAL]

[feed vertical] par entrée :
  border-left: 3px solid <severity_color>
  bg: #0e1117 | radius: 0 4px 4px 0 | padding: 4px 10px
  [sev coloré] [acteur · catégorie] [impact coloré +X/-X]
  [message 0.8rem #aabbcc]
```

---

**TAB 4 — Rejets**
```
[section-header] "Signaux rejetés — opportunités manquées potentielles"

[dataframe] height=400 (Timestamp | Symbole | Side | Régime | Conf finale | Conviction | Rejeté par | Raison | État)

[si > 1 rejet]
  [section-header] "Distribution des rejets par acteur"
  [Plotly Bar]
    color = #ef4444
    text outside
    bg paper=#0a0c12 / plot=#0e1117
    height=250
```

---

**TAB 5 — Sovereignty**
```
[section-header] "Hiérarchie institutionnelle des autorités"

[liste verticale — 8 agents]
  display:flex | bg: #0e1117 | radius: 6px | border-left: 3px solid <auth_color>
  [acteur monospace min-width:200px]
  [autorité coloré min-width:220px]
  [description]

Couleurs autorités :
  advisory_only        #4499ff
  reject_authority     #ffcc22
  allocation_authority #ff8800
  sizing_authority     #ff8800
  capital_authority    #ff4455
  veto_authority       #ff0033

[section-header] "Séparations institutionnelles critiques"
[5 items] border-left:#334455 | titre #00e0ff | desc #667788

[section-header] "Exercice réel de souveraineté"
[dataframe] Actor | Rejets souverains
```

---

### 3.5 EXECUTION HEALTH — `localhost:8509`

**Fichier :** `execution_health.py`
**Titre page :** "Execution Health" (icon ⚙️)
**Layout :** `wide`, sidebar collapsed

#### Header
```
<h2> "⚙️ Execution Health"
<p>  "P2 Operational — validation · rate limiter · simulation · audit"

[col 8:2]
  col droite : caption "Auto-refresh 20s" + btn "↻ Refresh"

[divider]
```

#### Onglets (4)
```
⚡ Audit P2 Live | 📊 Trades Historiques | 🚫 Pipeline & Rejections | 🛡️ Robustness GO/NO-GO
```

---

**TAB 1 — Audit P2 Live**
```
[si vide]
  card centrée bg=#1e293b border=#334155 radius=8px padding=32px :
    "⏳" (2rem)
    "En attente de données live" (1rem)
    explication fichier audit.jsonl
    "Lancer : python advisor_loop.py"

[si données]
  [ROW 5 métriques]
    Ordres tentés | Validés (-rejetés) | Rejection rate | Slippage moyen bps | Latence simulée ms

  [texte] "Fees totaux simulés : $X.XXXX USD sur N ordres"
  [divider]
  [dataframe] 200 derniers audits (Heure UTC | Symbole | Side | Size USD | Prix | Validé ✅❌ | Slippage bps | Latence ms | Fee USD | Partial ⚠)

  [si données slippage]
    [bar_chart] "Distribution slippage simulé (bps)"
```

---

**TAB 2 — Trades Historiques**
```
[si vide] message centré

[si données]
  [ROW 5 métriques]
    Total trades | Win Rate | PnL total | Profit Factor | Drawdown max

  [divider]
  [line_chart] "PnL cumulé ($)" height=200
  [divider]
  [2 colonnes]
    Gauche : bar_chart "PnL par régime" height=200
    Droite : table "Post-mortem" (Catégorie | Count | %)
  [divider]
  [dataframe] table trades (Symbole | Side | PnL$ | PnL% | Win | Régime | Conviction | Post-mortem | Durée min | Date | R-multiple)
```

---

**TAB 3 — Pipeline & Rejections**
```
[si vide] message

[si données]
  [ROW 4 métriques]
    Total decisions | Rejected | Passed | Avg latence ms

  [bar_chart] "Refus par couche" height=200
  [dataframe] "Dernières decisions" (Timestamp | Symbole | État | Score | Couche rejet | Raison)
```

---

**TAB 4 — Robustness GO/NO-GO**
```
[verdict central] GO / NO-GO avec couleur
[ROW 5 KPIs]
  Win Rate | Profit Factor | Drawdown | Avg Win/Loss | N trades

[tableau critères]
  Critère | Valeur | Seuil | Statut ✅❌
```

---

### 3.6 MULTI-EXCHANGE — `localhost:8510`

**Fichier :** `dashboard_multi_exchange.py`
**Titre page :** "Crypto AI — Multi-Exchange" (icon 🌐)
**Layout :** `wide`, sidebar collapsed

#### Structure actuelle
```
[TITRE] "🌐 Multi-Exchange — Prix Live"
[caption] "Données publiques — aucune clé API requise | Refresh 30s"

[ROW 3 métriques]
  Exchanges actifs (N/5) | Symboles suivis | Dernière mise à jour

[divider]

[PAR SYMBOLE — 4 fois]
  ### BTC/USDT <badge spread X.XXX%>
  [5 colonnes = 5 exchanges]
    Chaque colonne :
      [EXCHANGE nom coloré] [tag ✓ moins cher / ↑ plus cher]
      [prix en gros]
      [variation 24h | diff vs Binance]

  [dataframe] mini (exchange | price) si ≥ 2 exchanges
  [divider]

### Spreads inter-exchange
[dataframe] (Symbole | Prix min | Prix max | Spread % | Moins cher | Plus cher)

[caption] "Auto-refresh dans 30s"
```

#### Style spécifique
- Background: `#0a0c12` (plus sombre que les autres)
- Cards exchange : `#1e293b`, `border: 1px solid #334155`, `radius: 8px`
- Font: `monospace 0.85rem`
- Spread badge: bg `<color>22` + texte coloré + radius `3px`

---

## 4. URLS DE CHAQUE DASHBOARD

| Dashboard | URL locale | Fichier |
|-----------|------------|---------|
| Cockpit unifié | `http://localhost:8500` | `dashboard_unified.py` |
| Live | `http://localhost:8501` | `dashboard_live.py` |
| Master | `http://localhost:8502` | `dashboard_master.py` |
| Decision Trace | `http://localhost:8503` | `dashboard_decision_trace.py` |
| Command Center | `http://localhost:8504` | `command_center_dashboard.py` |
| Risk | `http://localhost:8505` | `dashboard_risk.py` |
| Positions | `http://localhost:8506` | `dashboard_positions.py` |
| Evolution | `http://localhost:8507` | `evolution_dashboard.py` |
| Compare Multi | `http://localhost:8508` | `dashboard_compare_multi.py` |
| Execution Health | `http://localhost:8509` | `execution_health.py` |
| Multi-Exchange | `http://localhost:8510` | `dashboard_multi_exchange.py` |

---

## 5. POINTS D'AMÉLIORATION IDENTIFIÉS

### Incohérences visuelles cross-dashboards
1. **Risk Dashboard** (8505) n'utilise pas `color_system.json` — fond clair Streamlit par défaut, émojis dans titres, sidebar expanded par défaut. Doit être aligné sur le dark theme des autres.
2. **Emojis dans les titres** : présents sur Risk (📊🧪📋📈📄🔁🔍🎲) et Execution Health (⚙️📊🚫🛡️), absents sur Master et Decision Trace. Manque de cohérence.
3. **Sidebar Risk** toujours ouverte — prend de l'espace sur un écran standard.

### Positionnement graphiques
1. **Master Tab 1** — Le "Modules système" (grille 4 colonnes de 18 modules) est placé entre les tables et les graphiques. Visuellement lourd au milieu du flux.
2. **Master Tab 2** — Le tableau principal + détail par symbole = duplication de l'information. Le tableau en haut liste déjà tout, puis le détail le répète en format card.
3. **Risk Row 7** (Confidence) — Expander ouvert par défaut + toujours en bas après Monte Carlo. Devrait être en haut ou dans une position plus accessible.
4. **Multi-Exchange** — Le mini dataframe sous chaque symbole (juste exchange + price) est redondant avec les cards au-dessus.

### Textes à revoir
1. **Execution Health Tab 1** message vide : "En attente de données live" — texte trop long, style trop technique.
2. **Decision Trace Sidebar** : label "Packet sélectionné" avec selectbox de packets — timestamp brut peu lisible.
3. **Risk Dashboard** caption : "Mode: ADVISOR ONLY" — terme interne peu significatif pour un utilisateur.
4. **Master Tab 3** verdict bar — texte statique peu dynamique, pourrait afficher le score directement.

### Couleurs manquantes / sous-utilisées
1. La couleur accent `#00e0ff` est utilisée uniquement dans Master et Decision Trace. Risk utilise `green`/`red`/`gray` natifs.
2. Les couleurs de post-mortem (`VALIDATED/LUCKY/UNLUCKY/MISTAKE`) ne sont affichées qu'en texte dans les tableaux — aucun badge visuel coloré.
3. Les couleurs de régime (`TREND_BULL` vert, `TREND_BEAR` rouge) ne colorent que les glyphs dans Master. Dans Risk, les régimes sont affichés en texte brut.
