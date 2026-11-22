# Résultat du pilote d'installation — Repository Cartographer (#599)

Pilote exécuté le **2026-11-22, 04:52–04:56Z**, sur GO de Mathieu (04:45Z), dans le périmètre restreint
de la revue (§5.2) : groupe et permissions, runner, correctif API minimal, redémarrage API contrôlé,
**une** invocation, lecture par la route. Hors périmètre et **non faits** : frontend, registre
(`NOT_WIRED`), timer, campagne de sept jours, fusion.

Ce document ne contient **aucune preuve runtime** : enveloppe, rapport, verrou, identifiant d'invocation
et journaux restent sur le VPS (`~/cat-obs-pilot/`, `/srv/cat-obs/reports/`). Seules figurent ici les
valeurs déjà publiques (SHA, empreintes attendues) et le verdict de chaque critère.

## Ce qui est installé

| Élément | Valeur |
|---|---|
| SHA de référence | `cd23922a99f64bac93fb16255b70d32387c54871` |
| Checkout runner | `/srv/cat-obs/checkout/cd23922a…`, `root:root`, dossiers 0555, fichiers 0444, exécutables suivis 0555, `git status` vide |
| Release API servie | `85376c5e-agent-invocation-c1ecc3b4` = `85376c5e` + 7 fichiers (arbre `c1ecc3b4…`, empreintes = revue §4 bis) ; venv de `85376c5e` réutilisé |
| Drop-in API | `zzzzzz-agent-invocation-599.conf` : `WorkingDirectory`, `ExecStart`, `BindReadOnlyPaths`, `SupplementaryGroups=cat-obs-read`, `AGENT_INVOCATION_REPORTS_PATH` |
| Accès | groupe `cat-obs-read` sans membre ; `reports` 0710, `runs`/`locks` 2750, fichiers 0640 ; compte `lecanada26` inchangé |
| Frontend | **inchangé** (`dist` 597 servi) : la carte n'est pas encore visible dans l'application |

## Critères obligatoires

| # | Critère | Résultat |
|---|---|---|
| 0 | Préconditions sur le VPS : clone à `cd23922a`, diff hors docs vide, commits pilote présents, sha256 du correctif | ✅ |
| 0 | `tests/agent_bench` avec la CPython 3.11 de l'API | ✅ 136 passés, 1 sauté (golden historique) ; les deux tests pilote **passés** |
| 0 | Invocation à blanc sous `/usr/bin/python3.10`, rapports jetables supprimés | ✅ `COMPLETED`/`PARTIAL`, `67bdcc05…` |
| 1 | Code servi : `WorkingDirectory` = release candidate, arbre `c1ecc3b4`, 7 fichiers | ✅ |
| 2 | Session PAPER identique avant/après redémarrage (lien, `session.json`, aucune nouvelle session) | ✅ |
| 3 | Lecture par la route **sous les droits du service**, avant invocation | ✅ `200`, `ABSENT`/`INDETERMINE`/`GRAY`, `no-store`, aucun chemin ; cible inconnue 404 |
| 4 | Une invocation (`systemd-run` isolé, ≈ 0,6 s) | ✅ code 0, `PUBLISHED`, `COMPLETED`, `PARTIAL`, `content_sha256 67bdcc05…` ; 2750/0640, groupe `cat-obs-read` ; une seule enveloppe |
| 5 | Rapport → route | ✅ `AVAILABLE`, `TERMINE`, `last_result PARTIAL`, `RED` « Inactif · fin normale », même identifiant que l'enveloppe sur disque ; motif « aucun processus ne détient le verrou » (`/proc/locks` lu depuis le service) |
| 6 | Non-régression | ✅ une seule route ajoutée ; 18 codes HTTP identiques ; API, web et 3 services `cat-or-live` actifs ; aucun timer ni unité cartographe permanente |

## Écarts constatés pendant l'exécution

- **Premier `install` arrêté (04:53Z), avant tout redémarrage** : le script passait tous les fichiers du
  checkout en 0444 ; les 19 scripts suivis comme exécutables ont été vus par git comme un changement
  de mode (`100755 → 100644`, contenu identique). Le contrôle « checkout modifié » a stoppé la phase.
  Corrigé (exécutables suivis en 0555), relancé à 04:55Z : conforme. La procédure est corrigée.
- La release API `85376c5e-agent-invocation-c1ecc3b4` existait déjà (créée à 04:38Z, hors de ce fil) ;
  elle a été vérifiée conforme (arbre, liste et sha256 des 7 fichiers) et utilisée telle quelle.

## Non vérifié

- **Vert réel** : non observé (invocation ≈ 0,6 s ; aucune lecture en boucle, aucun faux verrou).
- Affichage dans l'application : frontend non activé (annexe A de la procédure, décision séparée).
- Comportement sur la durée (règle des 36 h, invocations répétées) : relève de la campagne.

## Retour arrière

`sudo bash ~/cat-obs-pilot/cat-obs-pilot-root.sh rollback` : retire le drop-in, redémarre l'API sur
`85376c5e`, vérifie la session PAPER, retire le groupe et les bits ajoutés ; conserve les rapports,
la release candidate et le checkout (inertes).

## Point d'attention

L'API sert désormais un code (`85376c5e` + 7 fichiers) qui n'existe pas tel quel sur `main`. Toute
future release API construite depuis `main` devra contenir ces fichiers, sinon la route disparaîtrait
silencieusement au redéploiement.
