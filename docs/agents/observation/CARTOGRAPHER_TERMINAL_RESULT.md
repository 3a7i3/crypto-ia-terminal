# Mini terminal et programmateur du Repository Cartographer (#599) — résultat

Installé le **2026-11-22** (sudo par Mathieu), validé par Mathieu à 08:29Z sur mobile. Aucune preuve
runtime n'est publiée ici : rapports, enveloppes et journaux restent sur le VPS.

## Ce qui est servi

| Élément | Valeur |
|---|---|
| Code | `e2fc713b` (API, programmateur, applicateur), `65b6af9e` (web, identité de cache `cat-agent-schedule-599`) |
| Release API | `85376c5e-agent-invocation-e2fc713b`, arbre `6623e330` = `85376c5e` + 8 fichiers ; `app.py` = `app.py` servi + routes `history` et `schedule` |
| Routes | `GET …/history` (20 plus récents), `GET …/schedule`, **`POST …/schedule`** |
| Web | dist + serveur `web01_local_frontend_server.mjs` montés depuis `/opt/cat-app/releases/CAT-SYSTEM-AGENTS-599-65b6af9e` |
| Programmateur | `/srv/cat-obs/control` (root:cat-obs-read 2770), `cat-obs-schedule.path` → `/usr/local/sbin/cat-obs-schedule-apply` |

## Exception d'écriture (décision opérateur 2026-11-22 07:23Z)

Seule écriture de l'API et du serveur web : `POST /api/operator/v1/agent-invocations/repository-cartographer/schedule`,
valeurs `10min | 1h | off`, en-tête `x-cat-operator: schedule` exigé, corps ≤ 256 octets. L'API dépose
une demande ; l'applicateur root la valide et règle le timer. Rien n'est lancé directement ; PAPER,
FIN et exchange ne sont pas touchés. Le test du tableau de routes nomme cette exception et refuse toute autre.

Rythmes calés sur l'horloge (`OnCalendar`) : 10 min = :00, :10, :20… ; 1 h = heure pile ; Off = arrêt
complet (timer désactivé, aucune relance).

## Vérifications

- Isolé (1 min, vrai exécuteur, vraie API, vrai serveur web) : 2 passages verts sans clic, retour rouge
  et nouvelle bulle à chaque passage ; Off → gris, aucun rapport pendant 130 s.
- VPS : import vérifié avant bascule ; état/historique/programmateur 200, POST sans en-tête 403,
  valeur hors liste 422 ; via web 422 / POST historique 405 / POST market 405 ; session PAPER identique.
- Mobile (Mathieu) : menu ⏰ 10 min / 1 h / Off, gyrophare rouge → gris sur Off → rouge sur 10 min.

## Incident

06:59Z : la première release API utilisait l'`app.py` de la branche, qui importe un module absent de
`85376c5e` ; l'API n'a pas démarré pendant environ 2 minutes, retour arrière par Mathieu, session PAPER
intacte. Corrigé : `app.py` servi + routes, import vérifié avant toute bascule.

## Limites ouvertes

1. Plafond de lecture de 200 rapports : ≈ 33 h à 10 min, ≈ 8 jours à 1 h. Règle de rétention à définir.
2. La mission analyse la révision figée `e387318e` : rapports identiques (`67bdcc05…`).
3. Le vert dure ≈ 0,3 s par passage (lecture rapprochée à 0,1 s autour de l'heure prévue).
4. Le code servi n'est pas sur `main` : une release construite depuis `main` sans #599 retirerait ces routes.

## Retour arrière

`sudo bash ~/cat-obs-pilot/cat-obs-button-root.sh rollback` (bouton), puis
`sudo bash ~/cat-obs-pilot/cat-obs-upgrade-root.sh rollback` (terminal) ; arrêt de l'agent :
`… cat-obs-upgrade-root.sh stop-agent`.
