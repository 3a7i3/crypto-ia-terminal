# Archive — doublons bot Telegram P10_PORTFOLIO_BOT_TOKEN (2026-07-06)

## Raison de l'archivage

Sprint T1/T2 (cartographie Telegram) a trouvé 3 fichiers distincts implémentant
le même rôle (bot portefeuille `@mon_portfolio_bot`, token `P10_PORTFOLIO_BOT_TOKEN`) :

- `capital_deployment/command_center_bot.py` — **actif**, importé par
  `core/advisor_loop.py` (le seul poller réel, laissé en place).
- `capital_deployment/portfolio_bot.py` (ce dossier) — jamais importé nulle
  part dans le code (vérifié par grep) — code mort, prédécesseur probable
  de `command_center_bot.py`.
- `src/telegram/portfolio_bot.py` (ce dossier) — script standalone
  (`python -m src.telegram.portfolio_bot`), appelle `getUpdates` sur le
  même token que `command_center_bot.py`. Si lancé en parallèle du process
  principal, provoque un conflit 409 côté API Telegram (deux pollers actifs
  sur le même bot).

## Symptôme

Confirmé absent des process VPS au moment de l'audit (`ps aux`, 2026-07-06) —
pas de doublon actif constaté en pratique, mais le risque existait si
quelqu'un relançait ce script à la main.

## Utilisation

Conservés pour référence uniquement. `command_center_bot.py` reste le seul
poller du token `P10_PORTFOLIO_BOT_TOKEN`.
