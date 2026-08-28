# Telegram Governance — Changelog PR #79
> Date : 2026-08-28 | Branche : `copilot/audit-telegram-architecture-migration`
> Statut : **Prêt à merger**

---

## Contexte

Ce PR transforme l'écosystème Telegram de CRYPTO_AI_TERMINAL d'un ensemble de bots
non gouvernés en une **couche d'observation humaine constitutionnelle**.

Avant ce PR, le système présentait :
- Une collision de polling entre deux bots partageant le même token
- Des commandes de contrôle système accessibles via Telegram
- Des variables d'environnement sans lien avec les identités BotFather réelles
- Une identité active (`REAL_ACCOUNT_BOT_TOKEN`) non documentée dans aucun registre
- Aucune cartographie formelle des notifications envoyées

---

## Architecture officielle après PR

```
📡 @RadarCrypto1_bot          RADAR_BOT_TOKEN               ← isolé, polling dédié
🔇 @Telemetrie_IA_bot         TELEMETRIE_IA_BOT_TOKEN       ← zombie, décision opérateur
📰 @rapport_automatique_bot   RAPPORT_AUTOMATIQUE_BOT_TOKEN ← push 6h, read-only
🧪 @PaperArena_bot            PAPER_ARENA_BOT_TOKEN         ← push expérimental
💼 @mon_portfolio_bot         MON_PORTFOLIO_BOT_TOKEN       ← polling + push
🔬 @QuantCrpto_bot            QUANT_CRYPTO_BOT_TOKEN        ← polling + push
📢 (canal générique)          TELEGRAM_BOT_TOKEN            ← push alertes système
```

**Règle constitutionnelle (invariant permanent) :**
> Telegram = couche d'observation humaine.
> Zéro commande de contrôle. Zéro modification de paramètre.
> Zéro fallback silencieux entre identités.

---

## Phases réalisées

### Phase 1 — Isolation des identités Telegram ✅

**Problème résolu :** collision de polling `getUpdates` entre deux processus
partageant le même `TELEGRAM_BOT_TOKEN`.

**Avant :**
```python
# scripts/radar_bot.py — INTERDIT
TOKEN = os.getenv("RADAR_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
```

**Après :**
```python
TOKEN = os.getenv("RADAR_BOT_TOKEN", "").strip()
if not TOKEN:
    print("[ERREUR] RADAR_BOT_TOKEN manquant", file=sys.stderr)
    sys.exit(1)
```

**Fichiers modifiés :**
- `scripts/radar_bot.py` — fallback interdit supprimé, `exit(1)` explicite

**Tests ajoutés :** `tests/scripts/test_radar_bot.py` — **9/9 ✅**

| Test | Résultat |
|---|---|
| `RADAR_BOT_TOKEN` alimente le RadarBot | ✅ |
| `TELEGRAM_BOT_TOKEN` seul ne peut pas alimenter le RadarBot | ✅ |
| Absence `RADAR_BOT_TOKEN` → exit code 1 | ✅ |
| `RADAR_CHAT_ID` est utilisé | ✅ |
| Aucun fallback inter-identité | ✅ |
| Aucune valeur secrète dans les messages d'erreur | ✅ |

---

### Phase 2 — Cartographie officielle ✅

**Livrables créés :**

| Fichier | Contenu |
|---|---|
| `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` | Audit forensique complet — table d'identités, preuves `file:line`, risques de collision |
| `docs/architecture/TELEGRAM_ECOSYSTEM_MAP.md` | 8 profils d'identité avec entrypoints, services, polling/push |
| `docs/TELEGRAM_BOT_CONSTITUTION.md` | Mission officielle par bot : Must Do / Must Never Do |
| `docs/TELEGRAM_CONSTITUTION.md` | 10 principes constitutionnels invariants |

---

### Phase 3.1 — Violation constitutionnelle CMVK corrigée ✅

**Problème résolu :** `src/telegram/sim_bot.py` contenait des commandes `/kill` et
`/resume` capables de déclencher un kill-switch en production — violation directe du
Principe 5 de la Constitution Telegram.

**Avant :**
```python
# INTERDIT — commandes de contrôle système
@bot.message_handler(commands=["kill"])
def handle_kill(message): ...

@bot.message_handler(commands=["resume"])
def handle_resume(message): ...
```

**Après :** commandes supprimées, docstring constitutionnel ajouté :
```python
# CMVK Experimental Observer — READ-ONLY
# Constitutional rule: no control commands permitted.
```

**Fichiers modifiés :** `src/telegram/sim_bot.py`, `tests/test_sim_bot.py`

**Tests :** **21/21 ✅**

---

### Phase 3.2 — Inventaire exhaustif des notifications ✅

**Livrable créé :** `docs/TELEGRAM_NOTIFICATION_AUDIT.md` (231 lignes)

Cartographie de **chaque appel `sendMessage`/`sendPhoto`/`sendDocument`** dans le
codebase, avec référence `file:line`, déclencheur, fréquence estimée et classification.

**Statistiques globales :**

| Bot | Messages | KEEP | SUMMARIZE | REMOVE | ALERT | Bruit |
|---|---|---|---|---|---|---|
| 📡 CryptoRadar | 8 | 8 | 0 | 0 | 0 | Faible |
| 💼 Portfolio | ~22 | 21 | 1 | 1 | 0 | Faible |
| 🔬 Quant Observer | 5 | 3 | 1 | 0 | 0 | Moyen |
| 🧠 Rapport Auto | 2 | 1 | 0 | 0 | 0 | Faible |
| 🧪 Paper Arena | 3 | 1 | 2 | 0 | 0 | Moyen |
| 📢 Canal générique | 34 | 10 | 8 | 4 | 6 | **Élevé** |

**Découverte :** `REAL_ACCOUNT_BOT_TOKEN` — 6ème identité active, absente de tous
les registres existants.

---

### Phase 3.3.1 — Registre officiel des identités ✅

**Problème résolu :** `REAL_ACCOUNT_BOT_TOKEN` utilisait le même token physique que
`MON_PORTFOLIO_BOT_TOKEN` (confirmé par l'opérateur). Deux variables pour une seule
identité = dette de gouvernance.

**Livrable créé :** `docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md`

| Trouvées | Officielles | Mergées | Dead code |
|---|---|---|---|
| 10 | **7** | 1 (`REAL_ACCOUNT_BOT_TOKEN` → `MON_PORTFOLIO_BOT_TOKEN`) | 2 (`NARRATOR`, `KILLSWITCH`) |

**Fichiers modifiés :**
- `core/advisor_loop.py` — `REAL_BOT_TOKEN` lit désormais `MON_PORTFOLIO_BOT_TOKEN`
- `.env.secrets.example` — `REAL_ACCOUNT_BOT_TOKEN` supprimé

---

### Phase 3.3.1c — Alignement sur les @usernames BotFather ✅

**Motivation :** les anciennes variables (`INTEL_BOT_TOKEN`, `QC_BOT_TOKEN`,
`P10_PORTFOLIO_BOT_TOKEN`…) ne correspondaient pas aux identités BotFather
officielles — source de confusion pour l'opérateur et les futurs développeurs.

**Renommages appliqués :**

| Ancienne variable | Nouvelle variable | @username BotFather |
|---|---|---|
| `INTEL_BOT_TOKEN` | `RAPPORT_AUTOMATIQUE_BOT_TOKEN` | `@rapport_automatique_bot` |
| `INTEL_BOT_CHAT_ID` | `RAPPORT_AUTOMATIQUE_CHAT_ID` | |
| `QC_BOT_TOKEN` | `QUANT_CRYPTO_BOT_TOKEN` | `@QuantCrpto_bot` |
| `QC_CHAT_ID` | `QUANT_CRYPTO_CHAT_ID` | |
| `P10_PORTFOLIO_BOT_TOKEN` | `MON_PORTFOLIO_BOT_TOKEN` | `@mon_portfolio_bot` |
| `P10_PORTFOLIO_CHAT_ID` | `MON_PORTFOLIO_CHAT_ID` | |
| `PAPER_ARENA_TG_TOKEN` | `PAPER_ARENA_BOT_TOKEN` | `@PaperArena_bot` |
| `PAPER_ARENA_TG_CHAT_ID` | `PAPER_ARENA_CHAT_ID` | |
| `CMVK_BOT_TOKEN` | `TELEMETRIE_IA_BOT_TOKEN` | `@Telemetrie_IA_bot` |
| `CMVK_CHAT_ID` | `TELEMETRIE_IA_CHAT_ID` | |
| `REAL_ACCOUNT_BOT_TOKEN` | *supprimé* → `MON_PORTFOLIO_BOT_TOKEN` | (même token) |

**Variables conservées sans changement :**
- `RADAR_BOT_TOKEN` / `RADAR_CHAT_ID` — déjà lisibles
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — canal générique

**Périmètre :** 26 fichiers `.py`, `.env.example`, `.env.secrets.example`,
`.service`, `.md` — hors `_ARCHIVE_2026/`.

**Rétrocompatibilité VPS :** commentaires `# was: OLD_NAME` ajoutés dans
`.env.example` et `.env.secrets.example`.

---

## Récapitulatif des fichiers

### Créés
| Fichier | Type | Description |
|---|---|---|
| `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` | Documentation | Audit forensique Phase A-E |
| `docs/TELEGRAM_CONSTITUTION.md` | Documentation | 10 principes constitutionnels |
| `docs/TELEGRAM_BOT_CONSTITUTION.md` | Documentation | Mission par bot |
| `docs/TELEGRAM_NOTIFICATION_AUDIT.md` | Documentation | Inventaire notifications (231 lignes) |
| `docs/architecture/TELEGRAM_ECOSYSTEM_MAP.md` | Documentation | Carte des identités |
| `docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md` | Documentation | Registre officiel 7 identités |
| `tests/scripts/test_radar_bot.py` | Tests | Isolation token RadarBot |

### Modifiés
| Fichier | Changement |
|---|---|
| `scripts/radar_bot.py` | Suppression fallback interdit + exit(1) |
| `src/telegram/sim_bot.py` | Suppression `/kill` `/resume` + docstring |
| `core/advisor_loop.py` | Merge REAL_ACCOUNT + renommage variables |
| `capital_deployment/command_center_bot.py` | Renommage P10 → MON_PORTFOLIO |
| `src/telegram/notifier.py` | Renommage P10 → MON_PORTFOLIO |
| `src/telegram/quant_observer/bot.py` | Renommage QC → QUANT_CRYPTO |
| `src/paper/paper_report.py` | Renommage PAPER_ARENA_TG → PAPER_ARENA |
| `src/paper/paper_runner.py` | Renommage PAPER_ARENA_TG → PAPER_ARENA |
| `scripts/systemd/crypto-radar-bot.service` | Mise à jour commentaires |
| `scripts/systemd/crypto-quant-observer.service` | Renommage QC → QUANT_CRYPTO |
| `scripts/systemd/paper-arena.service` | Renommage PAPER_ARENA_TG → PAPER_ARENA |
| `.env.example` | Renommage + commentaires `# was:` |
| `.env.secrets.example` | Suppression REAL_ACCOUNT + renommages + `# was:` |
| `docs/architecture/TELEGRAM_BOT_REGISTRY.md` | Section governance gap ajoutée |
| `tests/test_sim_bot.py` | Suppression tests commandes de contrôle |

---

## Validation finale

| Vérification | Résultat |
|---|---|
| Syntaxe `advisor_loop.py` | ✅ |
| Syntaxe `command_center_bot.py` | ✅ |
| Syntaxe `quant_observer/bot.py` | ✅ |
| Syntaxe `paper_report.py` | ✅ |
| Syntaxe `radar_bot.py` | ✅ |
| Aucun `os.getenv("OLD_VAR")` hors archives | ✅ |
| Tests `test_radar_bot.py` | ✅ 9/9 |
| Tests `test_sim_bot.py` | ✅ 21/21 |
| Tests `test_paper.py` | ✅ 35/35 |
| **Total** | **✅ 65/65** |

---

## Action requise — VPS

Avant le prochain redémarrage des services, mettre à jour le `.env` sur le VPS :

```bash
# Renommer dans /path/to/.env sur le VPS :
INTEL_BOT_TOKEN          → RAPPORT_AUTOMATIQUE_BOT_TOKEN
INTEL_BOT_CHAT_ID        → RAPPORT_AUTOMATIQUE_CHAT_ID
QC_BOT_TOKEN             → QUANT_CRYPTO_BOT_TOKEN
QC_CHAT_ID               → QUANT_CRYPTO_CHAT_ID
P10_PORTFOLIO_BOT_TOKEN  → MON_PORTFOLIO_BOT_TOKEN
P10_PORTFOLIO_CHAT_ID    → MON_PORTFOLIO_CHAT_ID
PAPER_ARENA_TG_TOKEN     → PAPER_ARENA_BOT_TOKEN
PAPER_ARENA_TG_CHAT_ID   → PAPER_ARENA_CHAT_ID
CMVK_BOT_TOKEN           → TELEMETRIE_IA_BOT_TOKEN
CMVK_CHAT_ID             → TELEMETRIE_IA_CHAT_ID
# Supprimer :
REAL_ACCOUNT_BOT_TOKEN
REAL_ACCOUNT_CHAT_ID
```

---

## Prochaines étapes (hors périmètre PR #79)

| Phase | Description | Priorité |
|---|---|---|
| 3.3.2 | Résoudre collision de cadence 15 min (cycle report + heartbeat sur même canal) | Haute |
| 3.3.3 | Batcher le fan-out `new_regrets` (N messages → 1 résumé par cycle) | Haute |
| 3.3.4 | Paper Arena per-trade → résumé de session/expérience | Moyenne |
| 3.3.5 | Taxonomie canal générique (CRITICAL/ALERT/REPORT/RESEARCH/DEBUG) | Moyenne |
| 3.3.6 | Forensique dead code (`TelegramKillSwitch`, `S3/01_telegram_alerts.py`) | Basse |
| 4 | Services `.service` indépendants pour Portfolio et Rapport Auto (Principe 9) | Basse |
