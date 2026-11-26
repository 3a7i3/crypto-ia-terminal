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

## P6-GOV-02 (2026-11-26) — règle normative et état déployé

**Règle normative (source, à partir de P6-GOV-02).** L'exception reste la seule écriture, réservée au
cartographe (`10min | 1h | off`). Chaîne :

1. relais Web : identité lue dans `Tailscale-User-Login` (posé par `tailscale serve`), comparée à
   `CAT_OPERATOR_LOGINS`, retransmise sous `x-cat-operator-identity` ; toute valeur fournie par le
   client est ignorée ; corps > 256 octets refusé (413) ; chaque refus journalisé ;
2. API : même liste vérifiée (401/403), `application/json` exigé (415), corps ≤ 256 (413), objet
   exact `{"rhythm": …}` ASCII sans clé en double (422), 1 demande / 30 s et 12 / h (429), rythme déjà
   appliqué → 200 `UNCHANGED` ; dépôt atomique de `repository-cartographer.request` dans
   `/srv/cat-obs/schedule/requests/` (root:cat-obs-sched 2730) ; une ligne d'audit JSON par POST ;
3. applicateur root `cat-obs-schedule-apply` (Python, `schedule/cat-obs-schedule-apply.py`) : décisions
   prises sur le descripteur ouvert (`O_NOFOLLOW`, `O_NONBLOCK`, fichier régulier, 1 lien, propriétaire
   = utilisateur de l'API, ≤ 64 octets, non exécutable, mot de la liste fermée) ; demande consommée ;
   écritures par temporaire `O_EXCL` + `rename` dans des dossiers root non inscriptibles ; état publié
   dans `/srv/cat-obs/schedule/state/` (root:cat-obs-read 2750) ;
4. DPA et Market Observer : état republié depuis leurs drop-ins existants, jamais modifiés ; aucune
   demande possible (404).

Transport interne (P6-GOV-02-RV) : l'API exige en plus le jeton du relais (`x-cat-relay-token`),
lu dans `/etc/cat-obs/relay.token` (root:cat-obs-relay 0640), groupe porté seulement par les services
API et Web. Un autre utilisateur Unix local ne peut donc pas forger l'identité auprès de l'API.

Confinement, installation, vérification et retour arrière : `schedule/cat-obs-schedule-gov02-root.sh`
(`contain [--check] | preflight | install --logins … --api-release … --web-release … | verify |
rollback <horodatage>`), à exécuter par l'opérateur sur GO runtime distinct. L'installation commence
par le confinement C1 ; le retour arrière restaure les releases API/Web historiques sans jamais
réactiver les anciennes unités (la planification devient alors indisponible en écriture).

Limite assumée : tant que le relais écoute sur 127.0.0.1:8181, tout processus local peut s'y connecter
et forger `Tailscale-User-Login` ; root reste hors de portée de toute protection. L'option
`schedule/crypto-operator-web.socket.example` (socket root 0600 transmise par systemd, cible
`tailscale serve` en `unix:`) ferme ce point ; elle demande sa propre décision.

**État déployé (RUNTIME_VERIFIED le 2026-11-26, avant tout GO).** L'ancienne chaîne tourne encore :
applicateur bash de #601 (trois agents), trois unités `.path`, dossier `/srv/cat-obs/control` en 2770,
aucune identité opérateur. Le risque R1 (lien symbolique sur le temporaire d'état) y reste ouvert tant
que P6-GOV-02 n'est pas installé ou que le confinement C1 n'est pas appliqué. Ce document ne vaut pas
preuve de déploiement.

## Exception d'écriture (décision opérateur 2026-11-22 07:23Z) — historique

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
