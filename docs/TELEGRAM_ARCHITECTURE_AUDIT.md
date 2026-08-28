# Telegram Architecture — Forensic Audit

**Date de l'audit** : 2026-08-28
**Portée** : lecture seule, aucune modification effectuée en Phase A/B/C.
**Méthode** : recherche exhaustive de `getUpdates`, `sendMessage`, `sendPhoto`,
`sendDocument`, `telegram.org`, `*_BOT_TOKEN`, `*_CHAT_ID` sur l'ensemble du
dépôt, croisement avec `docs/architecture/TELEGRAM_BOT_REGISTRY.md` (contrat
fonctionnel existant, v2.0), les fichiers `.service` systemd et les fichiers
`.env.example` / `.env.secrets.example`.

> Ce document est un constat forensique indépendant. Il confirme, complète et
> parfois nuance `TELEGRAM_BOT_REGISTRY.md` (qui reste le contrat de référence
> pour le comportement fonctionnel de chaque bot). Là où les deux divergent,
> la preuve trouvée dans le code fait foi et est signalée explicitement.

---

## Table des identités Telegram

| Identity | Python Component | Entrypoint | Service | Token Variable | Chat Variable | getUpdates | sendMessage | Active Evidence | Current Responsibility | Collision Risk |
|---|---|---|---|---|---|---|---|---|---|---|
| 📡 CryptoRadar | `scripts/radar_bot.py` | `main()` → `poll_loop()` | `crypto-radar-bot.service` (ExecStart présent) | `RADAR_BOT_TOKEN` **avec fallback interdit** `TELEGRAM_BOT_TOKEN` (ligne 20) | `RADAR_CHAT_ID` avec fallback `TELEGRAM_CHAT_ID` (ligne 21) | Oui (long-poll `timeout=30`, boucle infinie) | Oui (`send_message`) | Service systemd dédié présent dans `scripts/systemd/`, `RADAR_BOT_TOKEN`/`RADAR_CHAT_ID` déjà présents dans `.env.example` | Scanner marché : `/scan /top50 /longs /shorts /symbol /lmi` (lecture seule, redirige `/signals` et `/status` hors domaine) | **ÉLEVÉ tant que `RADAR_BOT_TOKEN` est vide** — retombe alors sur `TELEGRAM_BOT_TOKEN`, un token générique utilisé ailleurs pour du push (voir ci-dessous) |
| 💼 Portfolio (CommandCenter) | `capital_deployment/command_center_bot.py` | classe avec méthode `start()` (in-process, invoquée par `crypto-advisor`) | in-process `crypto-advisor.service` (UNKNOWN — service non trouvé dans `scripts/systemd/`) | `P10_PORTFOLIO_BOT_TOKEN` (ligne 1132, pas de fallback token) | `P10_PORTFOLIO_CHAT_ID` avec fallback `TELEGRAM_CHAT_ID` si absent (ligne 1133) | Oui (`getUpdates` ligne 1235) | Oui | Code présent, référencé dans `TELEGRAM_BOT_REGISTRY.md`, token dédié isolé | Capital, performance, KPIs, positions (lecture seule) | FAIBLE côté token (isolé) ; MOYEN côté chat_id (fallback partagé `TELEGRAM_CHAT_ID`, risque de destinataire incorrect, pas de collision `getUpdates`) |
| 🔬 Quant Observer | `src/telegram/quant_observer/bot.py` | `run()` (ligne 212) → `if __name__ == "__main__"` (ligne 254) | `crypto-quant-observer.service` (ExecStart `python -m src.telegram.quant_observer.bot`) | `QC_BOT_TOKEN` (pas de fallback) | `QC_CHAT_ID` (pas de fallback) | Oui (ligne 73) | Oui | Service systemd dédié présent, token dédié dans `.env.secrets.example` | Univers scanné, régime, scores signaux, méta-stratégie + message épinglé auto-refresh 10 min | FAIBLE — token et chat entièrement isolés, aucun fallback trouvé |
| 🧠 Rapport Automatique | `quant_hedge_ai/agents/intelligence/system_intel_reporter.py` | fonction de rapport périodique (in-process, pas de boucle `poll_loop`/`getUpdates` trouvée) | in-process `crypto-advisor.service` (UNKNOWN — pas de `.service` dédié) | `INTEL_BOT_TOKEN` (déclaré dans `.env.example`/`.env.secrets.example`) | `INTEL_BOT_CHAT_ID` | **Non** (aucune occurrence `getUpdates` dans ce fichier) | UNKNOWN (envoi via un notifier partagé, pas de `sendMessage` direct trouvé dans ce fichier) | Variables déclarées dans les deux fichiers `.env*.example` | Rapport IA de synthèse toutes les 6h, push uniquement | AUCUN (pas de polling) |
| 🧪 Paper Arena | `src/paper/paper_runner.py` + `src/paper/paper_report.py` | `paper_report.py` définit `_TOKEN`/`_CHAT` (lignes 11-12), pas de `getUpdates` trouvé | `paper-arena.service` (ExecStart `python3 -m src.paper.paper_runner`) | `PAPER_ARENA_TG_TOKEN` (pas de fallback) | `PAPER_ARENA_TG_CHAT_ID` (pas de fallback) | Non | UNKNOWN (module de reporting, pas de `sendMessage` direct confirmé dans l'extrait audité) | Service systemd dédié présent, variables dédiées dans `.env.secrets.example` | Résultats d'expérience RSI ETH/4H (push uniquement) | AUCUN (pas de polling) |
| ⚠️ TELEGRAM_BOT_TOKEN générique (push) | `scripts/telegram_alerts.py`, `S3/01_telegram_alerts.py`, `supervision/notifications/telegram_notifier.py`, `config/settings.py`, CI (`.github/workflows/ci.yml`) | `sendMessage` uniquement, aucune boucle `getUpdates` trouvée dans ces fichiers | Aucun service dédié — utilisé in-process par `advisor_loop` | `TELEGRAM_BOT_TOKEN` (natif, pas un fallback ici) | `TELEGRAM_CHAT_ID` / `TELEGRAM_BEHAVIOR_CHAT_ID` | Non (aucune occurrence trouvée) | Oui (plusieurs émetteurs indépendants) | Utilisé activement pour alertes trade/danger/erreur/heartbeat | Alertes généralistes push (trade, danger, heartbeat, daily summary) | **C'est ce même token que CryptoRadar utilise en fallback `getUpdates`** — voir Phase C |
| 🔴 KillSwitch Telegram (legacy, code mort) | `supervision/kill_switch.py` (classe `TelegramKillSwitch`, polling réel `/STOP_ALL /CLOSE_ALL /SAFE_MODE /RESUME /STATUS`) | Classe jamais instanciée avec un vrai `bot_token` dans le code actif — seule instanciation trouvée est dans le docstring d'exemple (ligne 12) | Aucun (`KILLSWITCH_BOT_TOKEN`/`KILLSWITCH_CHAT_ID` n'apparaissent nulle part dans le code, uniquement mentionnés comme supprimés dans `TELEGRAM_BOT_REGISTRY.md`) | `KILLSWITCH_BOT_TOKEN` (aucune référence `os.getenv` trouvée — variable non câblée) | `KILLSWITCH_CHAT_ID` (idem) | Oui dans le code de la classe, mais **jamais exécuté en pratique** | Oui (`sendMessage` dans la classe) | `core/advisor_loop.py` importe en réalité `runtime.TelegramKillSwitch`, qui résout vers `supervision.killswitch_hardened.KillSwitchHardened` (aucune trace Telegram) — confirmé par absence totale de `TOKEN`/`CHAT_ID`/`telegram` dans `killswitch_hardened.py` | Kill switch **interne** uniquement (`force_halt`/`force_resume`), documenté comme retiré de Telegram par `supervision/telegram_kill_switch.py` (constitution 2026-08-28) | AUCUN actuellement (code mort), mais risque latent si quelqu'un réinstancie `supervision.kill_switch.TelegramKillSwitch` avec `TELEGRAM_BOT_TOKEN` |
| ⚪ Sim/CMVK Bot | `src/telegram/bot_runner.py`, `src/telegram/sim_bot.py` | `if __name__ == "__main__"` (ligne 147, `bot_runner.py`) | Aucun `.service` trouvé | `CMVK_BOT_TOKEN` (`os.environ.get`, ligne 148) | `CMVK_CHAT_ID` (ligne 149) | Oui (lignes 69, 92) | UNKNOWN | Référencé uniquement par ses propres fichiers + `tests/test_sim_bot.py` ; documenté comme supprimé (`@FtnTrading_bot`) dans `TELEGRAM_BOT_REGISTRY.md` | Bot de simulation — retiré de production selon le registry | FAIBLE — token dédié `CMVK_BOT_TOKEN`, aucun fallback trouvé, mais statut d'activité réelle **UNKNOWN** (aucun service systemd) |
| ⚪ Archive — Portfolio Bot dupliqué | `_ARCHIVE_2026/telegram_bot_duplicates_20260706/*.py` | Présent mais dans un dossier `_ARCHIVE_2026` | Aucun | UNKNOWN | UNKNOWN | Oui (code présent) | Oui | Dossier explicitement nommé "duplicates", archivé le 2026-07-06 | Ancien code dupliqué, non actif | AUCUN (archivé, hors production) |
| ⚪ config/telegram_config.json | fichier de config JSON générique (`bot_token`/`chat_id` placeholders) | N/A | N/A | `bot_token` (JSON, `"enabled": false` par défaut) | `chat_id` (JSON) | Non | UNKNOWN | `enabled: false` dans le fichier lu — désactivé par défaut | Config alternative pour alertes (non prioritaire, `.env` prend le pas selon `S3/01_telegram_alerts.py`) | AUCUN (désactivé) |

**Notes de preuve** :
- "Active Evidence" = fichier systemd trouvé, variable déclarée dans `.env*.example`, et/ou entrée correspondante dans `TELEGRAM_BOT_REGISTRY.md`. L'audit ne peut pas confirmer l'exécution réelle sur le VPS (hors scope, Phase 5 du registry).
- Tout champ marqué **UNKNOWN** signifie : aucune preuve trouvée dans le dépôt à la date de l'audit.

---

## Notification Inventory

| Bot | Current Message Type | Frequency | Human Value | Classification | Proposed Replacement |
|---|---|---|---|---|---|
| 📡 CryptoRadar | Réponses interactives `/scan /top50 /longs /shorts /symbol /lmi` | À la demande (réactif, aucun push) | Élevée — répond à « où se passe-t-il quelque chose sur le marché » | **KEEP** | Aucun changement fonctionnel requis ; corriger uniquement l'isolation du token (Phase D) |
| 💼 Portfolio | Rapport périodique (`P10_PORTFOLIO_REPORT_MINS`/`_H`) + réponses `/status /kpis /balance /positions ...` | Périodique (configurable) + à la demande | Élevée — répond à « la machine gagne-t-elle de l'argent » | **KEEP** | Aucun changement requis |
| 🔬 Quant Observer | Message épinglé rafraîchi toutes les `QC_PINNED_UPDATE` (défaut 600s = 10 min) + réponses `/snapshot /health /pipeline` | Toutes les 10 min (push pin) + à la demande | Moyenne — utile pour la recherche mais un rafraîchissement toutes les 10 min est un flux, pas un événement | **SUMMARIZE** | Conserver les commandes à la demande ; envisager d'espacer le refresh du pin (ex. 30-60 min) ou de ne le rafraîchir que sur changement significatif de régime, pour réduire le bruit sans perdre l'info |
| 🧠 Rapport Automatique | Rapport IA complet toutes les 6h | Fixe, 6h | Moyenne à élevée selon densité du rapport — non interactif, purement informationnel | **KEEP** (à condition que le contenu reste une synthèse et non un flux brut) | Si le rapport contient des logs bruts, les remplacer par des conclusions statistiques (cf. Principe 10 de la Constitution) |
| 🧪 Paper Arena | Notification entrée/sortie de position + résumé périodique + statut de gate (`INSUFFICIENT_SAMPLE` → `CONCLUSIVE`) | Événementiel (par trade) + périodique | Moyenne — utile en recherche mais les notifications par trade individuel sont du bruit à moyen terme | **SUMMARIZE** | Remplacer les notifications trade-par-trade par un résumé quotidien/hebdomadaire (N trades, WR, PF agrégés) ; conserver le changement de statut de gate comme événement rare et à forte valeur |
| ⚠️ Alertes génériques (`TELEGRAM_BOT_TOKEN`) | trade / danger / error / heartbeat / daily_summary | Variable — heartbeat potentiellement fréquent | Faible pour heartbeat répétitif, élevée pour danger/error | **SUMMARIZE** pour heartbeat, **KEEP** pour danger/error/daily_summary | Réduire la fréquence des heartbeats (ou les envoyer uniquement en cas de changement d'état) ; ne jamais faire de heartbeat sur ce canal si un token dédié `RADAR_BOT_TOKEN` doit rester isolé |
| 🔴 KillSwitch Telegram (legacy) | Commandes de contrôle `/STOP_ALL /CLOSE_ALL /SAFE_MODE /RESUME /STATUS` | N/A — code mort, jamais exécuté avec un vrai token | Nulle actuellement (non actif) et **interdite par construction** si réactivée (Principe 5 de la Constitution) | **REMOVE** | Ne jamais réactiver ; envisager de supprimer physiquement la classe `TelegramKillSwitch` de `supervision/kill_switch.py` dans un futur nettoyage (hors scope de ce patch minimal) |
| ⚪ Sim/CMVK Bot | UNKNOWN (pas de preuve d'utilisation active) | UNKNOWN | Nulle si non utilisé en production | **UNKNOWN** (probablement REMOVE si confirmé inactif) | Confirmer l'inactivité puis archiver comme les autres duplicatas |

---

## PHASE C — Collisions identifiées

### Collision confirmée : `RADAR_BOT_TOKEN` ⇄ `TELEGRAM_BOT_TOKEN`

**Preuve (avant patch)** — `scripts/radar_bot.py` ligne 20 :
```python
TOKEN = (os.getenv("RADAR_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
```

Si `RADAR_BOT_TOKEN` n'est pas défini dans l'environnement du service
`crypto-radar-bot.service`, ce processus démarre un `getUpdates` long-polling
(`timeout=30`, boucle infinie) sur le token `TELEGRAM_BOT_TOKEN`. Ce même
token est utilisé ailleurs dans le dépôt (`scripts/telegram_alerts.py`,
`S3/01_telegram_alerts.py`, `supervision/notifications/telegram_notifier.py`,
`config/settings.py`, CI) — mais uniquement pour `sendMessage` (push), donc
ces émetteurs-là ne provoquent pas de conflit `409` avec `getUpdates`.

Le vrai risque de collision `409 Conflict` sur `getUpdates` avec ce même
token viendrait de **tout autre processus qui ferait aussi du long-polling**
sur `TELEGRAM_BOT_TOKEN`. L'audit n'a trouvé aucun autre poller actif utilisant
directement `TELEGRAM_BOT_TOKEN` pour `getUpdates` dans le code courant
(le seul candidat historique documenté était le KillSwitch Telegram, retiré
selon `TELEGRAM_BOT_REGISTRY.md` et confirmé code mort par cet audit).

**Risque réel identifié** : même sans collision `409` active aujourd'hui, le
fallback constitue une violation du principe « One Token = One Poller »
(Constitution, Principe 2) et une dépendance cachée : tant que
`RADAR_BOT_TOKEN` n'est pas explicitement défini sur le VPS, l'identité
CryptoRadar (marché) et le canal d'alertes génériques (trade/danger/erreur)
partagent silencieusement le même token, avec des permissions et un usage
différents. Un opérateur qui régénère `TELEGRAM_BOT_TOKEN` (rotation de
sécurité) casserait CryptoRadar sans le savoir s'il ignore ce fallback.

### Autres candidats examinés (aucune collision confirmée)

| Composants | Token partagé ? | Verdict |
|---|---|---|
| Portfolio chat_id (`P10_PORTFOLIO_CHAT_ID` fallback `TELEGRAM_CHAT_ID`) | Chat uniquement, pas de token | Pas de collision `getUpdates` — risque de mauvais destinataire seulement (chat, pas token) |
| Quant Observer (`QC_BOT_TOKEN`) | Aucun fallback trouvé | Isolé |
| Paper Arena (`PAPER_ARENA_TG_TOKEN`) | Aucun fallback trouvé | Isolé |
| Intel Reporter (`INTEL_BOT_TOKEN`) | Aucun fallback trouvé, pas de `getUpdates` | Isolé, push-only |
| KillSwitch legacy (`supervision/kill_switch.py`) | Jamais câblé à une variable d'environnement réelle | Code mort — pas de collision active |

---

## PHASE D+E — Patch appliqué

Le fallback interdit `TOKEN = os.getenv("RADAR_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")`
a été confirmé dans `scripts/radar_bot.py` (ligne 20) et corrigé :
`RADAR_BOT_TOKEN` et `RADAR_CHAT_ID` sont désormais requis explicitement,
sans repli sur `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`. Le script sort avec
le code 1 et un message d'erreur explicite (sans jamais afficher de valeur
de secret) si `RADAR_BOT_TOKEN` est absent. Voir le rapport final pour le
détail des fichiers modifiés.
