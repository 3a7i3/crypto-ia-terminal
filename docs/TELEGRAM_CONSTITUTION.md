# Telegram Constitution

**Version 1.0 — 2026-08-28**
**Statut** : constitutionnel — s'applique à tous les bots Telegram présents et
futurs du dépôt, sans exception.

> Ce document formalise, sous forme de principes, les conclusions de l'audit
> forensique `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` et complète le contrat
> fonctionnel `docs/architecture/TELEGRAM_BOT_REGISTRY.md`. En cas de conflit,
> ces trois documents doivent être alignés — toute divergence est un défaut
> à corriger, pas une exception à tolérer.

---

## Principe 1 — One Identity = One Mission

Chaque bot Telegram répond à **une seule question humaine** et ne doit jamais
en couvrir deux. L'audit confirme que cette séparation est déjà largement
respectée : CryptoRadar répond à « où se passe-t-il quelque chose sur le
marché ? », Portfolio répond à « la machine gagne-t-elle réellement de
l'argent ? », Quant Observer documente la microstructure du moteur de
décision, et Paper Arena rapporte le sort d'une hypothèse scientifique isolée.
Quand une commande sort de son domaine (`/signals` ou `/status` dans
CryptoRadar), elle doit rediriger explicitement vers le bot compétent plutôt
que de répondre elle-même — c'est déjà le comportement observé dans
`scripts/radar_bot.py::cmd_signals` et `cmd_status`.

## Principe 2 — One Token = One Poller

Un token Telegram ne doit jamais être consommé par `getUpdates` (long-polling)
depuis plus d'un processus à la fois — Telegram renvoie une erreur `409
Conflict` sinon, et le comportement devient non déterministe (un seul des
deux processus reçoit réellement les messages). L'audit a confirmé que chaque
identité active (CryptoRadar, Portfolio, Quant Observer) possède aujourd'hui
son propre token dédié (`RADAR_BOT_TOKEN`, `MON_PORTFOLIO_BOT_TOKEN`,
`QUANT_CRYPTO_BOT_TOKEN`) et son propre processus de polling. Le seul poller partageant
historiquement un token avec un autre usage était `scripts/radar_bot.py` via
son fallback vers `TELEGRAM_BOT_TOKEN` — corrigé par ce patch.

## Principe 3 — No Cross-Identity Token Fallback

Un fallback `TOKEN = os.getenv("X_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")`
est **interdit**, même temporairement. L'audit a trouvé exactement ce motif
dans `scripts/radar_bot.py` (ligne 20, avant patch), documenté comme
« temporaire » depuis Phase 3 de `TELEGRAM_BOT_REGISTRY.md` mais jamais
retiré. Un fallback cache une dépendance : il permet à un bot de démarrer
« par accident » avec le mauvais token, et transforme toute rotation de
sécurité du token générique (`TELEGRAM_BOT_TOKEN`) en panne silencieuse d'un
bot qui semblait pourtant migré. Ce principe est maintenant appliqué
strictement dans `scripts/radar_bot.py` : `RADAR_BOT_TOKEN` et
`RADAR_CHAT_ID` sont lus seuls, sans repli.

## Principe 4 — Telegram Is an Observation Layer

Telegram sert à **lire** l'état du système (equity, régime, signaux
agrégés, univers scanné, statut d'expérience) et à **recevoir des rapports**,
jamais à modifier le comportement de la machine. Ce principe est déjà
formalisé dans `TELEGRAM_BOT_REGISTRY.md` sous forme de constitution
(« Telegram = observation et compte rendu uniquement », 2026-08-28) et
respecté par les cinq bots actifs identifiés dans l'audit : aucun d'entre eux
n'expose de commande qui touche au sizing, aux seuils de risque, ou à
l'exécution d'ordres réels.

## Principe 5 — Telegram Cannot Silently Control the Machine

Aucune commande Telegram ne peut arrêter, reprendre, ou reconfigurer le moteur
de décision. L'audit a trouvé un vestige exact de cette violation :
`supervision/kill_switch.py::TelegramKillSwitch`, qui implémente encore
`/STOP_ALL /CLOSE_ALL /SAFE_MODE /RESUME /STATUS` en polling réel — mais cette
classe n'est **jamais instanciée avec un vrai token** dans le code actif.
`core/advisor_loop.py` utilise en réalité `KillSwitchHardened`
(`supervision/killswitch_hardened.py`), qui ne contient aucune référence
Telegram. Le remplacement fonctionnel, `supervision/telegram_kill_switch.py`,
documente explicitement le retrait de l'interface Telegram
(« aucune commande de contrôle n'est accessible via Telegram »). Ce code mort
doit rester non instancié ; il constitue un risque latent si quelqu'un le
recâble un jour à un token réel.

## Principe 6 — Human Summaries Over Machine Logs

Un message Telegram doit apporter une conclusion lisible par un humain, pas
un déversement de logs bruts. C'est déjà le style dominant observé dans
l'audit : CryptoRadar renvoie des scores agrégés et des dominances
directionnelles, pas des paquets de décision bruts ; Quant Observer résume un
pipeline plutôt que d'exposer des métriques système (RAM/CPU/PID sont
explicitement listés comme interdits dans son contrat). Là où ce principe est
le moins respecté, c'est le rafraîchissement du message épinglé de Quant
Observer toutes les 10 minutes et les notifications Paper Arena par trade
individuel — voir le tableau « Notification Inventory » de l'audit pour les
propositions de résumé.

## Principe 7 — Critical Alerts Are Rare and High Priority

Une alerte n'a de valeur que si elle est rare. L'audit a identifié un canal
générique (`TELEGRAM_BOT_TOKEN`, via `scripts/telegram_alerts.py` et
`S3/01_telegram_alerts.py`) qui gère déjà un dédoublonnage sur 5 minutes pour
éviter le spam en cas de boucle d'erreurs — un bon exemple de ce principe en
pratique. Les heartbeats répétitifs et les statuts de gate Paper Arena
doivent rester rares (changement d'état) plutôt que périodiques à haute
fréquence, pour que l'opérateur continue à prêter attention à chaque message.

## Principe 8 — Every Telegram Identity Must Have an Owner and Responsibility

Chaque bot doit avoir une source de code, un service (ou un mode in-process)
et une responsabilité documentée. L'audit a pu tracer, pour chacun des cinq
bots actifs, le fichier Python, le token ENV, et — pour trois d'entre eux —
le fichier `.service` systemd correspondant. Les bots pour lesquels cette
traçabilité est incomplète (Portfolio et Rapport Automatique, in-process dans
`crypto-advisor.service` sans fichier `.service` dédié trouvé dans
`scripts/systemd/`) sont marqués **UNKNOWN** dans la table d'audit plutôt que
supposés actifs — l'absence de preuve n'est jamais traitée comme une preuve
d'absence, ni l'inverse.

## Principe 9 — A Telegram Bot Must Be Independently Stoppable

Chaque identité Telegram doit pouvoir être arrêtée sans affecter les autres.
Les trois bots dotés d'un fichier `.service` dédié (`crypto-radar-bot`,
`crypto-quant-observer`, `paper-arena`) respectent nativement ce principe :
un `systemctl stop` isolé n'affecte pas les autres processus. Les bots
in-process (Portfolio, Rapport Automatique, tous deux hébergés dans
`crypto-advisor.service`) violent partiellement ce principe : les arrêter
individuellement nécessite d'arrêter tout le service `crypto-advisor`. C'est
un risque identifié à surveiller plutôt qu'un défaut immédiatement bloquant,
car ces deux bots sont push/lecture-seule et sans effet sur le moteur.

## Principe 10 — Scientific Conclusions Are More Valuable Than Raw Events

Un flux d'événements bruts (chaque trade, chaque tick de régime) a moins de
valeur qu'une conclusion statistique (win rate agrégé, intervalle de
confiance, gate de significativité). Ce principe est directement hérité de la
« Règle du statisticien » de ce dépôt : aucune calibration ni changement de
seuil ne peut se justifier par une observation isolée. Il s'applique de la
même façon aux notifications Telegram — c'est pourquoi le statut de gate
Paper Arena (`INSUFFICIENT_SAMPLE` → `CONCLUSIVE`) a plus de valeur qu'une
notification par trade individuel, et pourquoi un rapport IA de synthèse
(Rapport Automatique) doit rester une conclusion et non un export de logs.
