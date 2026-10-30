# APP-BRAND-01 — correction de la migration du cache PWA

Mission [#529](https://github.com/3a7i3/crypto-ia-terminal/issues/529), base `c8efb6e22e004bb058e13c9eece18e315a830635`, 2026-10-30. Cette correction prolonge la demande de logo ; elle ne change ni le dessin, ni le thème, ni la navigation.

## Publication observée et défaut

Le paquet5386db38 a été publié par l'opérateur à11:45:30UTC (05:45:30Mexico) sous [l'exception consommée](https://github.com/3a7i3/crypto-ia-terminal/issues/286#issuecomment-6521615993). Web PID118966 ; API PID79546 et démarrage02:48:04UTC inchangés. Le journal contient un seul cycle web dans la fenêtre11:44:30–11:46:10UTC, aucun cycle API. Aucun restart/reload de l'agent.

Le checker live a vérifié25 empreintes protégées,11 fichiers candidats, les8 assets locaux et l'index/logo HTTPS privé. Le nouveau PNG192 est bien servi avec SHA256 `5f8e38bca670a96916ed4089375ee0d6209c4d19161222489b30b756d4b2d411`. Audit privé neuf :44 vues/238 assertions PASS, aucune fixture et service workers bloqués.

La capture opérateur9295.jpg montre pourtant une ancienne icône de terminal. Ce n'est pas une preuve d'échec de la bascule serveur. J'avais conservé l'adresse mutable /icons/operator-192.png, déjà précachée par l'ancienne PWA. Le service worker et son cachev1 n'avaient pas changé ; cacheFirstStatic renvoie cette ancienne réponse avant toute lecture réseau. Le nouvel en-tête remplace le SVG par cette adresse et révèle donc le vieux PNG.

Les preuves antérieures de navigateur neuf ne couvraient pas la migration d'un cache existant. Leur résultat est conservé avec cette limite, sans transformer leur PASS en certification du téléphone.

## Reproduction et résultat corrigé

Un serveur éphémère127.0.0.1 sert uniquement les dist autorisées et des API synthétiques503. Aucun proxy vers l'API active. Chromium156/Playwright1.64.1, sandbox activée, service workers autorisés, aucune requête externe/mutation ni erreur de page.

1. Charger la dist82cd63e et attendre le contrôle par son worker.
2. Mettre en cache son icône192, hash `bc969e04c6b134b4cba00af788d2a202a496290d169a5b64cbc7b4fd5f10a262`.
3. Servir5386db38 au même origin : nouveau JS, ancienne image depuis le cache. Un GET indépendant du worker reçoit bien le PNG des agents. Défaut reproduit.
4. Servir la dist corrigée, en gardant délibérément l'ancien worker et l'ancien cache : l'image versionnée reçoit les bons pixels. L'ancien cache reste présent, sans purge, désinscription ou effacement du stockage client.

[Reçu et empreintes](evidence/APP_BRAND_CACHE_UPGRADE_20261030.json). PIDs API/web identiques avant et après ; navigateur et serveur éphémère fermés. Les captures avant/après sont conservées sur la VM dans audit-browser/brand-cache-20261030/final-proof. Cette preuve ne certifie pas le rafraîchissement de l'icône du lanceur Android.

## Changement minimal

| Consommateur | Nouvelle adresse |
|---|---|
| En-tête, favicon, icône Apple et manifest192 | /icons/operator-agents-5f8e38bca670-192.png |
| Manifest512 | /icons/operator-agents-48308c17cac2-512.png |
| Précache du worker | Ces deux adresses exactes |

Le nom inclut12 caractères du SHA256 des pixels. Un changement de dessin exige donc une nouvelle clé de cache ; le nouveau contrat vérifie ce lien, les dimensions et l'accord des références. Les fichiers gardent exactement les pixels déjà validés. Les anciennes adresses sont classées KEEP pour compatibilité avec les anciennes installations ; aucune suppression.

Les règles API/health réseau seulement restent intactes ; aucun résultat scientifique n'entre dans le cache. Pas de changement de package/lock, serveur web, backend, données, stratégie, autorité, thème/CSS ou réglages du téléphone.

## Validation et reproduction

Le nouveau contrat a échoué avant correction sur l'URL mutable, puis passe après correction. Logs initiaux conservés.

- 492 tests frontend PASS,0 skip avec19 fixtures synthétiques réutilisées.
- 17 contrats runtime/PWA PASS,0 skip ; npm audit0 et build production PASS.
- 154 contrôles visuels existants PASS ; clair/sombre persistants, contraste minimal5.274.
- Preuve de migration avec ancien worker et cache conservés : bons pixels sous la nouvelle adresse, aucun trafic API réel ni changement des services.

Outil portable suivi : [capture_brand_cache_upgrade.cjs](../../frontend/scripts/capture_brand_cache_upgrade.cjs). Dans un environnement d'audit disposant de Playwright :

```bash
BRAND_LEGACY_DIST=/chemin/dist82cd63e \
BRAND_CURRENT_DIST=/chemin/dist5386db38 \
BRAND_FIX_DIST=/chemin/distcorrigee \
BRAND_CACHE_OUT_DIR=/chemin/preuves \
node frontend/scripts/capture_brand_cache_upgrade.cjs
```

BRAND_SERVICE_IDENTITY_CHECK=true ajoute une comparaison read-only des unités sur la VM, facultative ailleurs. Le worker ancien est volontairement maintenu pour la phase corrigée ; le contrat Node teste séparément le vrai nouveau précache.

La vue393px réellement servie utilise bien la présentation mobile. La capture9295 est une vue large très réduite ; aucun réglage navigateur du téléphone n'a été lu, donc son mode ordinateur reste une hypothèse. Le CSS validé n'est pas modifié.

## État et rollback

Source corrigée et testée en copie isolée ; fusion et CI à vérifier au HEAD réel. Aucune modification des fichiers actifs. Frontend réellement servi toujours5386db38 ; le défaut de cache n'altère pas l'API ou les données et n'a pas nécessité de rollback.

Rollback source : revert revu de cette PR. Une éventuelle publication du correctif nécessitera un nouveau paquet exact et une décision distincte : l'exception5386 est consommée. Le retour cible de cette future bascule serait5386db38, sans effacer les caches ou les données du téléphone. #286 ACTIVE, U8/L4 non certifiés ; aucune activation d'agent, d'expérience ou de producteur.
