# Passation de conversation — migration VM et refonte de l’application

Date de clôture documentaire : 2026-10-30 UTC. Dernière observation VM de cette passation : **2026-10-30T07:50:58Z**.

## Reprendre ici

L’opérateur demande de documenter la conversation sur GitHub avant de poursuivre dans une autre conversation. Cette passation est une synthèse opérationnelle de la conversation disponible, des preuves enregistrées et des vérifications finales ; elle n’est pas une transcription verbatim. Les actions réalisées dans d’autres conversations ne sont attestées ici que lorsqu’elles ont été revérifiées.

**La refonte frontend #525 est fusionnée en source, mais pas publiée sur la VM.** Le prochain agent doit lire cette page, puis la passation VM, revérifier la cible, la source et les gates avant de préparer une publication distincte. Aucun redémarrage n’est autorisé par cette page.

| Élément | État à la clôture |
|---|---|
| PR [#523](https://github.com/3a7i3/crypto-ia-terminal/pull/523) | Fusion source réalisée antérieurement ; release opérateur `82cd63e202e09ff52e00372cb9d9f3eb65cc8345` |
| PR [#525](https://github.com/3a7i3/crypto-ia-terminal/pull/525) | Fusion vérifiée par API GitHub ; `merged_at=2026-10-30T04:57:38Z` |
| HEAD de #525 testé | `2085fe2a65c0259bb09a8bd60949baa52f3154df` |
| Commit de fusion / main observé | `1c3f0b5c6f7d7ab553106f4788f66d9c7c9e67ab` ; API du commit et `git ls-remote origin refs/heads/main` |
| CI du HEAD de PR #525 | 22 runs pull_request retournés par le connecteur, tous success, revérifiés à la clôture |
| CI post-fusion | NON VÉRIFIÉE dans cette clôture ; les 22 runs ci-dessus ne sont pas une preuve au commit de fusion |
| API et frontend VM | Active/running, démarrés manuellement plus tôt ; toujours ancienne release opérateur |
| Démarrage au boot | Deux unités disabled |
| Présentation de données | Répertoire vide, aucune donnée récupérée raccordée |
| Moteurs / Telegram / expérience | Aucune activation par cette mission ; aucun droit d’activation transmis |
| Publication de #525 | À préparer et à autoriser séparément ; aucun changement runtime dans cette clôture |

Le message du commit de fusion précise : « Source only. Runtime frontend/Advisor unchanged; deployment gated by #286, #430 and #432. » Les états actuels de ces gates doivent être relus ; leur simple mention ne vaut pas validation.

## 1. Mission initiale et décisions opérateur

Objectif : installer de façon reproductible l’Infrastructure de Recherche Scientifique Crypto AI Terminal sur une nouvelle VM, préserver les données récupérées et coordonner le travail avec Claude.

Séquence des décisions :
1. Standby initial : audit A/B seulement, lecture de la passation et plan concret ; installation, moteur de recherche et nouvelle expérience constituent trois décisions distinctes.
2. Finalisation de #523 et de son échec CI avec revue finale de Claude. Autorisation explicite de vérifier puis fusionner #523 au SHA exact.
3. Autorisation de validation sur la VM, puis préparation des unités API/frontend.
4. Autorisation d’installation inactive des deux unités, avec intervention administrateur ; premier démarrage distinct.
5. Autorisation du premier démarrage manuel de l’API, contrôle des protections puis du frontend. Moteurs, Telegram et expériences exclus.
6. Autorisation de l’accès privé depuis le téléphone via Tailscale Serve, sans port public.
7. Audit en lecture seule des données récupérées et plan de raccordement ; **aucun redémarrage**.
8. Changement de priorité : travailler d’abord l’application, classer les sorties vers leurs écrans, réduire le bruit et revoir les panneaux/thèmes.
9. Autorisation d’un navigateur d’audit isolé sur la VM, uniquement pour consulter/capturer ; installation des bibliothèques manquantes réalisée manuellement par l’opérateur.
10. Autorisation d’implémenter la refonte frontend : navigation par module/famille, réduction des doublons et du contenu burn-in visible, thème professionnel clair/sombre avec bouton engrenage.
11. Demande de revue finale de #525 ; fusion réalisée dans une autre conversation puis annoncée par l’opérateur et désormais vérifiée.
12. Demande actuelle : conserver la conversation et son état sur GitHub avant reprise ailleurs.

Les autorisations historiques consommées ne sont pas des permissions permanentes. Le standby initial a été levé par étapes pour les actes décrits ci-dessus ; **la contrainte actuelle de ne rien redémarrer et de séparer la publication de la fusion reste applicable**.

## 2. Cible, accès et continuité

| Identité / chemin | Valeur |
|---|---|
| Hôte | `crypto-restore-01` |
| Compte | `lecanada26`, UID 1001, GID 1002 ; hostname/id revérifiés à la clôture |
| Appareil Remote Desktop Commander | `bc07f523-ad34-4c2e-9af1-0105f66d5783` |
| Projet GCP de passation | `project-33b357f0-92e0-4d19-a15`, numéro `726923174137`, zone `us-central1-a` |
| Capacité observée précédemment | Ubuntu 22.04.5, 2 vCPU, environ 16 Go RAM, disque 100 Go ; pas de nouvelle mesure dans cette clôture |
| Tailscale observé | `100.118.215.88` ; Tailscale SSH désactivé lors des contrôles antérieurs |
| URL privée | `https://crypto-restore-01.tailfebca3.ts.net/` |
| Première lecture sur VM | `/home/lecanada26/crypto-install/ACCESS_HANDOFF.md` |
| Connecteur durable | Service utilisateur `desktop-commander-remote.service`, runtime `~/.local/share/desktop-commander/runtime-0.3.1` ; active/enabled et Linger=yes observés précédemment |

L’ancienne VM `crypto-advisor-2` est arrêtée, son projet détaché de la facturation et l’ancien compte déclaré fermé. Ne pas tenter de la redémarrer ni de réactiver sa facturation.

Le connecteur interdit certaines opérations administrateur, notamment sudo. **Aucun contournement** par interpréteur, extraction de paquets ou modification du connecteur. Préparer un bloc court et vérifiable pour l’opérateur si une intervention root devient nécessaire.

Ne pas modifier le canal d’accès actif sans récupération. Aucun reboot complet ni accès automatique d’un futur agent n’a été démontré. Revérifier sa connexion effective au bon appareil.

## 3. #523 : dépendances frontend et release opérateur

Base historique : `5507424255eb98eee2948ed4975789ceb5787904`.
HEAD approuvé par Claude : `3e33ba1f076842649db53869d722ace3fe07c556`.
Release après fusion : `82cd63e202e09ff52e00372cb9d9f3eb65cc8345`.

Périmètre : seulement package.json/package-lock frontend ; Vite 8.3.2 → 8.3.5 et Vitest 4.1.11 → 4.1.12, transitives de développement. Production déclarée inchangée. Deux versions de postcss restent présentes ; leur déduplication était hors mission.

Revue Claude fournie par l’opérateur :
- audit npm 0 ; 408 tests frontend réussis, 72 ignorés ; 16 contrats runtime ; build OK, reproduits localement sous Node 22 ;
- étapes CI Node 20 vertes, mais chiffres non lus directement dans les logs de cette revue ;
- 22 runs au HEAD (21 PR et un push), tous success ;
- relance unique de Test Dashboards and Panels : premier échec à la vérification réseau des badges Codecov/Coveralls de main ; fournisseur exact non déterminé ;
- aucune fusion, aucun commentaire ni mutation par cette revue Claude.

Ne pas réattribuer les chiffres Node 22 à une lecture des logs Node 20. Ces résultats sont historiques et attachés à cette source.

Chemins :
- release : `/home/lecanada26/crypto-install/releases/82cd63e202e09ff52e00372cb9d9f3eb65cc8345` ;
- environnement opérateur préparé : `~/crypto-install/envs/operator-py31117`, Python 3.11.17 ; environnement de release isolé également préparé, Python système préservé ;
- validations : `~/crypto-install/validations/82cd63e202e09ff52e00372cb9d9f3eb65cc8345/`, dont PROVENANCE.json ;
- staging des unités : `~/crypto-install/staging/systemd-82cd63e202e09ff52e00372cb9d9f3eb65cc8345/`.

Aucun git pull aveugle, reset destructif ou stash historique appliqué automatiquement. Toute correction de code passe par branche et PR.

## 4. Installation et premier démarrage des unités

Unités système :
- `crypto-operator-api.service` : écoute loopback `127.0.0.1:8090` ;
- `crypto-operator-web.service` : écoute loopback `127.0.0.1:8181`.

Installation root:root 0644 réalisée par l’opérateur après contrôle d’empreinte du script `install_inactive.py` :
`10bf1a2a11e8d7f80c4020d6d425bb61f298ce99466dd6bfec51412db7a75f7f`.
Résultat fourni : INACTIVE_INSTALL_PASS, inactive/dead et disabled, aucun start/restart/enable.

Deux essais du premier `first_start.py` ont échoué après le précontrôle :
`AttributeError 'function' object has no attribute 'client'`.
Cause identifiée dans le helper : nom de fonction `http` masquant `http.client`.
Rollback : arrêt de l’API à chaque échec ; le frontend n’a pas été validé par ces essais.
Ne pas réutiliser ce helper obsolète.

Correctif `first_start_v2.py`, SHA256 :
`cbb1fe2a5f584fb8ae7a9e1be9595ec9c8edac12d96ff036c7526fd61e45881a`.
L’opérateur l’a exécuté ; résultats :
- READ_ONLY_PRECHECK_PASS ;
- contrôles processus/mounts/privilèges/loopback/attachements BPF pour les deux unités ;
- API_HTTP_CONTRACT_PASS : les artifacts absents restent indisponibles ;
- FIRST_START_PASS : API+frontend actifs, boot disabled, présentation vide.

Protection constatée lors de ces contrôles : utilisateur lecanada26, ProtectHome=tmpfs, ProtectSystem=strict, NoNewPrivileges, PrivateTmp/Devices, pas de capabilities ; chemins en lecture seule, IPAddressDeny=any et IPAddressAllow=localhost, BPF attaché ; proxy web GET/HEAD et refus POST 405. Treize chemins d’artifacts API pointent vers la présentation isolée.

Limites : configuration et attachements BPF contrôlés, **pas de challenge réseau externe comportemental**, pas de certification après reboot. Relire les unités réellement installées avant toute publication.

### État VM revérifié à la clôture

| Unité | PID | Depuis UTC | État | NRestarts | Boot |
|---|---:|---|---|---:|---|
| API | 79546 | 2026-10-30 02:48:04 | active/running | 0 | disabled |
| Web | 79556 | 2026-10-30 02:48:06 | active/running | 0 | disabled |

Ces PID et dates sont inchangés depuis le premier démarrage réussi. `NRestarts=0` ne prouve pas à lui seul une absence de toute intervention ; la comparaison avec les PID/dates précédents constitue ici l’observation complémentaire.

## 5. Accès privé et vérification téléphone

L’opérateur a exécuté :
`sudo tailscale serve --bg --https=443 http://127.0.0.1:8181`.

Serve annonçait un accès limité au tailnet via l’URL privée ; aucun Funnel ni port public ouvert par cette mission. Le contrôle antérieur de TLS/index/health a réussi depuis la VM. La résolution DNS locale ts.net échouait ; le contrôle utilisait `curl --resolve` avec validation TLS, sans `-k`.

Deux captures Android fournies par l’opérateur montrent l’ancienne interface Machine/Synthèse et Travaux. Elles attestent un rendu mobile dans ce test, pas le SHA servi, toutes les routes, la fraîcheur ou la santé scientifique. Le relevé GitHub affiché y était ancien et encore en cours ; ses nombres ne constituent pas un inventaire courant.

Rollback du proxy : désactiver uniquement Serve HTTPS443 avec intervention administrateur, sans reset global Tailscale. Aucun essai de reboot.

## 6. Données récupérées : conservation et raccordement suspendu

Sources à préserver :
- `~/crypto-migration/verified-20261029T053303Z` ;
- manifeste : `~/crypto-migration/received-20261029T053303Z/manifest.json` ;
- complément v3 : `~/crypto-migration/complement-v3-received/complement-v3.tar.zst.gpg`, manifeste/empreintes dans le même répertoire ;
- v2 à phrase oubliée : ne pas confondre avec v3.

Contrôles historiques : 1 463 fichiers par empreinte, trois vérifications SQLite ; v3 déchiffrée sur nouvelle VM, 51 654 entrées d’archive et quatre entrées de reflog de stashes. Ne pas supprimer, écraser, restaurer globalement ou modifier les originaux. Avant usage : revérifier empreintes et cohérence SQLite/WAL éventuels sur copies isolées. Aucune phrase de passe dans le chat, les commandes, les logs ou les rapports ; saisie locale protégée si nécessaire.

Audit de présentation : cinq des treize fichiers attendus présents dans le lot extrait, empreintes des cinq revérifiées contre le manifeste. Le complément chiffré n’a pas été réinspecté pendant cet audit.

| Artifact récupéré | Lecture admissible / limite |
|---|---|
| operator_snapshot.json | Capture générée 2026-10-29 05:29:04Z ; ancien source SHA 116634be… ; identité runtime seulement déclarée |
| operator_runtime_manifest.json | Identité archivée ; **ne pas présenter comme processus actuel sur la nouvelle VM** |
| cryptoradar_market_snapshot.json | Généré 2026-10-29 05:32:36Z, source 05:29:04Z ; historique/stale lors de l’audit |
| ppl_comparison_snapshot.json | 2026-10-29 05:29:05Z ; epoch BURN-IN-EPOCH-01-20260926T064144Z |
| financial_reconciliation_snapshot.json | 2026-09-26 06:07:16.984Z ; epoch F00-EPOCH-01-20260920T084335Z, différente de PPL |

Absents du lot/manifeste inspectés : burn_in_status, runtime_service, market_microstructure, research lab, research strategies, PPL accounting history, event center et storage. Absence dans ce lot ne signifie pas absence dans tous les backups.

Piège identifié : snapshot canonique + ancien runtime manifest peuvent donner CURRENT_INSTANCE/CURRENT parce que leurs identités concordent ; cela **ne prouve pas la vie de la nouvelle VM**. Sans manifest, UNKNOWN/LAST_KNOWN. Préserver cette distinction.

Plan initial proposé : un seul snapshot marché inchangé, hash + reçu de provenance, affichage STALE/dates, autres sources indisponibles. **Plan suspendu** lorsque l’opérateur a priorisé la refonte UI. Aucun fichier copié dans `~/crypto-install/presentation`, encore vide à la clôture. Aucun producteur, import, expérience, synthèse entre epochs ou certification activés.

## 7. Audit navigateur isolé

La tentative Cloud Browser sur l’URL privée a échoué ; elle ne constitue pas un accès visuel utilisable. L’opérateur a ensuite autorisé Playwright isolé sur la VM.

Chemin : `~/crypto-install/audit-browser`.
Playwright 1.64.1 ; Chromium headless 156.0.8078.4, build1248.
Installation de 16 bibliothèques OS par l’opérateur : zéro upgrade/removal ; needrestart listait packagekit pour plus tard, aucun restart par l’agent.

Absence de polices : premiers rendus invalides, puis Noto Sans et fonts.conf ajoutés uniquement au dossier d’audit.
SHA256 NotoSans-Regular.ttf :
`b85c38ecea8a7cfb39c24e395a4007474fa5a4fc864f6ee33309eb4948d232d5`.

Audit final de l’ancienne app : 14 routes × mobile393×852 et desktop1440×1000 = 28 captures, zéro pageerror et zéro débordement horizontal ; données de présentation absentes. Il ne s’agissait pas d’une certification complète d’interaction/accessibilité ou d’états réels renseignés.
Chemin : `audit-browser/captures-empty`.

Sandbox navigateur activée, contextes éphémères, service workers bloqués, requêtes page limitées aux GET/HEAD loopback, appels externes bloqués. Navigateur fermé après audit. Aucun service applicatif redémarré.

Constats : navigation à plusieurs niveaux, doubles vues générales, répétitions d’indisponibilité, Scores vide, tableau Travaux très long. Ces observations ont motivé la refonte autorisée.

## 8. #525 : refonte réalisée et livrée en source

Branche : `feat/module-workspace-themes-20261030`.
HEAD final testé : `2085fe2a65c0259bb09a8bd60949baa52f3154df`.
Tree final : `c3fa07c323852c937c6c7ac4cc74bad86c52eba1`.
Premier HEAD : `a0b9189b5fe6b27ab218f00152324d627cd67ec8`, supersédé après corrections CI.
Fusion : `1c3f0b5c6f7d7ab553106f4788f66d9c7c9e67ab`.

Documentation de conception, mapping et rollback :
[MODULE_WORKSPACE_THEMES_01.md](../frontend/MODULE_WORKSPACE_THEMES_01.md).

### Résultat produit

- Navigation unique : Accueil, Marché, Décisions, Positions, Finance, Laboratoire, Système ; Projet/Travaux secondaire.
- Accueil compact : six cartes et cinq propriétaires de lecture ; Décisions/Positions partagent les métadonnées canoniques.
- Chaque module lit ses sorties nécessaires ; diagnostics Advisor et microstructure chargés à la demande.
- Provenance et ancienneté conservées ; absence de santé globale certifiée explicitement distincte.
- PPL/lifecycle et FIN restent deux autorités ; aucun calcul financier ou classement scientifique ajouté au frontend.
- Détails techniques repliés ; données essentielles et dates visibles.
- Travaux paginé par huit missions avec filtrage du registre complet ; pas de lecture GitHub automatique.
- Contenu burn-in retiré des routes actives de l’app, sans suppression des archives, contrats, composants/tests historiques ni garde-fou scientifique.
- Anciennes routes overview vers /direction, burn-in vers portfolio, scores vers system ; composants historiques retenus en source.
- Thème clair/sombre via engrenage, palette sémantique, SVG locaux, choix persisté dans localStorage `crypto-terminal.theme`.
- Préférence système initiale si aucun choix valide ; stockage bloqué traité sans crash, synchronisation inter-onglets, fermeture Escape et retour du focus, meta theme-color.
- Contexte CSS racine `operator-shell` conservé : sa disparition avait cassé des tableaux mobiles et a été corrigée.

Aucun backend, package.json/lock, autorité de lecteur, producteur d’artifact, stratégie, seuil, secret, unité ou donnée scientifique modifié par #525.

### Tests et preuves historiques au HEAD final

| Contrôle | Résultat enregistré |
|---|---|
| Frontend avec fixtures cross-stack générées | 492 réussis, aucun ignoré |
| Python cross-stack | 113 réussis |
| Contrats runtime frontend | 16 réussis |
| Builds production et démo | PASS |
| npm audit | 0 vulnérabilité |
| git diff --check | PASS |
| Audit visuel refonte | 154 contrôles responsive/thème/états/contraste PASS |
| Preuves UX français / mobile | 124 / 75 assertions PASS |

Versions locales enregistrées : Node24.22.1, Python3.11.17 isolé. Les comptes dépendent des fixtures ; une exécution sans génération peut ignorer des tests et n’équivaut pas à la preuve cross-stack complète.

Les 15 scripts visuels existants ont été exercés ; certains premiers essais ont échoué. Après correction du contexte operator-shell, scanner/LMI/Machine-Lab/UX/mobile et preuves concernées ont été rejoués avec succès. Ne pas présenter les logs initiaux comme une exécution entièrement verte.

Preuves VM :
- `~/crypto-install/audit-browser/module-preview-final/captures-corrected/checks.json` ;
- `corrected-proof-results.json` ;
- `legacy-proof-results.json` contient des échecs diagnostiques supersédés ;
- `~/crypto-install/audit-browser/module-preview-corrected-audit.log`.

Ces previews utilisent des builds isolés et **des données synthétiques**, interceptées par le navigateur ; aucune connexion à l’API de production. Certains anciens contrats de test utilisent un serveur fixture loopback à port éphémère, fermé à la fin.

### Échecs CI corrigés

1. StrictMode montait deux fois les effets en développement : assertion adaptée à cinq propriétaires uniques avec deux lectures de montage admises, et test dédié.
2. Finance pollait et empêchait networkidle : attente DOMContentLoaded puis valeurs/heading validés.
3. Sandbox Chromium refusée par le namespace du runner GitHub : opt-out explicite autorisé uniquement dans GitHub Actions, cohérent avec les preuves existantes ; **sandbox VM toujours activée**.

À la clôture, les 22 runs PR renvoyés au HEAD final sont success, dont Frontend CI, Cross-Stack, Machine/Lab et compatibilité des routes retirées. Cela ne constitue ni une revue indépendante de notre propre code, ni une certification scientifique ou runtime.

Source VM préparée :
`~/crypto-install/worktrees/module-workspace-themes-20261030`, au HEAD2085fe2 lors de la dernière synchronisation de source ; **ce worktree n’est pas une release activée**.

## 9. Rapports et aperçus complémentaires

Les fichiers suivants ont été remis à l’opérateur ; ils complètent cette passation sans remplacer GitHub et les observations VM :
- [Audit UI et cadrage](https://chatgpt.com/library?file_id=libfile_b4699a85385081918931ba38c846d8de&account_id=personal).
- [Audit données et plan de raccordement](https://chatgpt.com/library?file_id=libfile_cb7ec3896d4c8191bcb696a4bd639959&account_id=personal).
- [Aperçu refonte clair/sombre/mobile](https://chatgpt.com/library?file_id=libfile_e3a90c9697788191844c193f3d41a6f7&account_id=personal), synthétique et NON DÉPLOYÉ.

La passation VM conserve les observations chronologiques antérieures. Ses dernières lignes antérieures à cette clôture disaient encore « PR525 draft, CI en cours » : elles sont **historiques et supersédées** par la fusion et les 22 succès revérifiés ici. Ne pas effacer l’historique pour corriger ce décalage.

Les anciennes roadmaps de stabilisation et les ZIP joints sont des références d’archives, pas des commandes de reprise ni une source plus actuelle que le dépôt et la passation.

## 10. Reprise concrète, rollback et limites

**Prochaine action unique : préparer le dossier de publication frontend au SHA fusionné exact, sans activation.**

Ordre proposé au prochain agent :
1. Lire cette passation, `docs/DEVELOPER_ENTRYPOINT.md`, `CLAUDE.md`, la mission applicable et la passation VM ; lire les AGENTS.md applicables s’ils existent. Revérifier #285/#286 et les gates #430/#432 signalées dans le commit.
2. Confirmer accès au bon appareil, hostname/id, services, chemins réellement servis, statut Git et main actuel. Ne pas toucher aux travaux parallèles de Claude.
3. Vérifier le commit de fusion, son contenu par rapport au HEAD testé, CI post-fusion et dépendances ; ne pas choisir silencieusement un main qui aurait avancé.
4. Préparer une release frontend isolée, fichiers verrouillés et provenance. Inspecter les BindReadOnlyPaths des unités : les chemins actuels pointent sur l’ancienne release ; ne pas écraser les fichiers actifs pour éviter artificiellement un restart.
5. Préparer les seuls changements nécessaires au frontend, leurs empreintes, contrôles et procédure root éventuelle ; API et données inchangées.
6. Rendre le plan exact de bascule et de retour à l’ancienne release, puis attendre l’autorisation distincte de publication/redémarrage si elle n’a pas été fournie explicitement dans la nouvelle session.
7. Après activation autorisée seulement : contrôler process/path/SHA/endpoint et rendu privé mobile/desktop, thèmes et états indisponibles ; mettre à jour la passation VM avec preuves datées.

Rollback actuel : aucun changement runtime de #525 à annuler. Conserver la release82cd63e, ses validations/unités et toutes les sauvegardes. Un rollback source doit utiliser un commit/PR revu, jamais un reset destructif de main. Le rollback de publication devra être écrit avant toute bascule.

Interdictions persistantes :
- aucun moteur, Telegram, collecteur, timer, burn-in, reprise d’expérience ou trading réel ;
- aucune clé exchange trading/retrait ni secret applicatif/IA activé sans gate correspondante ;
- aucun contenu secret, .env, token ou session dans les preuves ;
- aucun port public, reboot, enable au boot ou changement du canal d’accès implicite ;
- aucun raccordement d’archives, ancien manifest présenté courant, modification des originaux ou mélange d’epochs ;
- aucune stratégie, calibration, seuil, sizing ou résultat historique modifié par cette mission.

Une page rendue ne prouve pas une API saine ; une API saine ne prouve pas un moteur actif ; un processus vivant ne prouve pas des données fraîches ; une fusion ne prouve pas un déploiement. Tout élément non observé reste **NON VÉRIFIÉ**.

## 11. Changements de cette clôture documentaire

Objectif : permettre une reprise fiable dans une autre conversation.
Preuves finales : fusion #525, main, 22 runs PR success, hostname/id, PID/état/boot/NRestarts des deux unités et présentation vide.
Changements : ajout de cette passation sur une branche documentaire dédiée, proposée par PR ; aucune modification de code applicatif.
Tests : contrôle des références et de la portée documentaire ; aucune suite applicative relancée pour un texte.
Services / effets externes : lectures GitHub/VM et publication documentaire GitHub uniquement ; aucun start/stop/restart/reload/enable et aucun effet exchange/Telegram.
Rollback : retrait ou correction documentaire par commit/PR, conservation des preuves.
Blocages : activation hors périmètre, opérations root par l’opérateur, CI au commit de fusion et vérifications runtime/UI de la refonte restant à faire.
