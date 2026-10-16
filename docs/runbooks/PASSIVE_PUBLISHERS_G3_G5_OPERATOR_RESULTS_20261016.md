# Publishers G3–G5 — résultats opérateur et vues navigateur, 16 octobre 2026

Statut : **résultats bornés rapportés par Mathieu et captures transmises**. Le présent commit ne déploie ni n'active rien. #286 reste actif ; L3 acquis historiquement, U8/L4 non certifiés. Pas de santé globale, de performance stratégique ou d'admission Research déduite des publications.

## Provenance et chronologie

Les commandes privilégiées ont été exécutées par Mathieu sous `mathieu`, jamais par l'agent. Les sorties ont été collées dans la conversation ; aucune observation indépendante des runs, du journal root ou de l'état courant des timers par l'agent. Les captures ci-dessous ont été inspectées par l'agent après transmission par Mathieu le 16 octobre. Ce sont des images du navigateur de l'opérateur, sans parcours interactif indépendant et sans preuve cryptographique de leur URL d'origine.

| Étape | Résultat effectivement transmis | Limites |
|---|---|---|
| G3 runtime-service, 15/10 vers 19:47Z | Série 3/3, contrat et fraîcheur valides ; unités gardées inchangées | Consigné par #450 ; publication préalable de l'exception non établie ; durée et compteurs non disponibles |
| G3 storage, 16/10 03:54:47Z | Plan code 0, unités conformes/inactives, timers disabled ; artefact runtime 878 octets préservé comme référence | État ponctuel |
| G3 storage, 03:56:27Z puis 04:00:52Z | Journal : premier démarrage à 03:56:27Z, puis série finale 3/3, artefacts 612 octets `mathieu 600`, contrats/fraîcheur valides, healthz 200, Advisor/API/web UNCHANGED ; code final 0 | Mathieu confirme deux lancements du bloc ; sortie de la première tentative non reçue. **Au moins quatre démarrages visibles : dépassement de l'usage unique/trois essais autorisés, conservé comme écart ; aucune régularisation rétroactive**. Durée/CPU/mémoire NOT_AVAILABLE |
| G4, 16/10 vers 04:37Z | Deux chemins raccordés, API seule redémarrée, un start de chaque publisher couvert par G4 ; Services et Stockage 200/FRESH/contrats valides, Advisor/web UNCHANGED ; code 0 | Ces starts G4 sont distincts de G3 |
| G4, contrôle différé vers 04:41Z | 200/STALE et contrats valides sur les deux routes, Advisor/web UNCHANGED ; `G4 COMPLETE`, code 0 | Un premier contrôle trop tôt a refusé WAIT_95_SECONDS_AFTER_APPLY, sans nouvel apply ni mutation ; le contrôle seul a ensuite été rejoué |
| G5, plan vers 17:34Z | Empreintes OK, journal compatible, code 0 ; PSI CPU avg60 3,34 %, MemAvailable 7625 Mio | Relevé ponctuel de l'hôte |
| G5, fin transmise vers 17:50Z | Observation 300 s, 10 exécutions terminées par publisher, FRESH après amorçage, codes HTTP stables ; `G5 OBSERVATION OK`, code 0 ; timers laissés enabled | Contrôles du script sur cadence 29–32 s, durées positives <=10 s et invariance Advisor/API/web passés. Les durées individuelles/maxima ne sont pas imprimés dans la sortie fournie ; pas de valeurs inventées |

Le maximum PSI CPU avg60 **parmi les points affichés à 30 s** vaut 9,2 % (à 180 s), puis 3,72 % au dernier point. Ce n'est ni un maximum exhaustif ni une consommation attribuable aux publishers. Âges finaux : runtime-service 24,486 s ; storage 24,741 s. STALE initial avant les premières publications attendu et explicitement autorisé pendant l'amorçage. Aucune extrapolation à une observation longue durée.

## Autorisations, empreintes et état de reprise

- G3 storage : [exception publiée](https://github.com/3a7i3/crypto-ia-terminal/issues/286#issuecomment-6207722134), consommée, avec écart ci-dessus.
- G4 : [exception publiée](https://github.com/3a7i3/crypto-ia-terminal/issues/286#issuecomment-6208176949), apply consommé, rollback conservé selon ses conditions.
- G5 : [exception publiée](https://github.com/3a7i3/crypto-ia-terminal/issues/286#issuecomment-6221236177), run consommé ; maintien actif explicitement autorisé après réussite. Expiration 16/10 23:59Z = date limite de lancement, pas arrêt programmé des timers.

| Artefact utilisé | SHA-256 |
|---|---|
| G3 bloc corrigé (#452) | `3d03794cc3328664510073bae125792a4cf307ae5791e7c923627a164c7e335d` |
| G3 script interne | `19abde8d0bdde248a6ab9d4c5c023869482194488b745a73a376b542c28b55b9` |
| G4 script opérateur | `0867483c552058b7a1dc2b56ebf26ff168ddf36f9467f43807a67bd584092786` |
| G4 archive de transport | `eff114f336bcafdd4219b0bf8f96578cf7ba0167573c113851380b7015649eaa` |
| G4 drop-in API | `8605801d7f5b1c22ef7a098a541dbbc7229a098c4a9a8ef8c88e9243d8a43664` |
| G5 script opérateur | `1469fcc50ecc562bede3dcc205fd13210d52daa2d921852619c474f7624d252a` |
| G5 archive de transport | `8b41ee2577f56f58a055fc3194f29afe9d09c07f8fccd99bce7419e9b524263a` |

Les scripts G4/G5 livrés dans la conversation ne sont pas présentés comme ayant été fusionnés dans le dépôt : leurs empreintes, leurs copies root et journaux opérateur constituent la provenance déclarée. État prévu conservé sous `/var/lib/crypto-publishers-g4/` et `/var/lib/crypto-publishers-g5/`, copies root sous `/root/crypto-publishers-g{4,5}-code/`. Le contenu actuel de ces dossiers n'a pas été lu indépendamment. Ne jamais les effacer pour forcer un nouveau run.

G5 rollback : seulement disable --now des deux timers, état/artefacts conservés. Les snapshots vieillissent ensuite. G4 rollback nécessite d'abord de retirer G5 puis le seul drop-in API G4, selon les procédures et autorisations existantes. Pas d'exécution par ce document.

## Résultats visibles dans le navigateur

- **Services** : FRESH ; crypto-advisor.service active/running, PID 882633, NRestarts 0, démarrage 2026-09-27T03:03:57Z. Observation 2026-10-16T17:51:15.843039Z, âge affiché environ 30,78 s. Source code et preuve de déploiement = NOT_AVAILABLE, conservés comme tels.
- **Stockage** : capture récente/disponible ; 8 fichiers, 361338044 octets ; dernière modification filesystem 2026-10-16T17:51:14.804008Z. Inventaire de métadonnées seulement, pas nombre de packets ni espace disque libre. Les accordéons de provenance sont présents mais leur contenu déplié n'est pas prouvé par cette image.
- **Événements** : indisponibles, EVENT_CENTER_MISSING ; attendu, non raccordé. La capture n'est pas une preuve d'absence de tout journal sur le VPS.
- **Ancien frontend bdca77f / #430** : compteur visible 29/29 et autre capture avec état En cours, 3/29. Cela prouve deux rendus transmis, pas l'exécution indépendante de tous les filtres. Sur ces images de téléphone, le tableau reste en colonnes ; **la conversion en cartes mobiles n'est pas établie**. La capture filtrée affiche 12:49 sans date : ne pas lui attribuer l'heure du relevé système ni une date de capture certaine.

Les vues Burn-in manquant, FIN ancien, Scores NOT_EXPOSED et santé globale UNKNOWN ne sont pas réparées ni certifiées par G3–G5. Le frontend 8ff089b (#451/#457/#458) est une release distincte, pas encore observée comme servie à la date de ces captures ; le registre affiché reste ancien à 29 missions. Les faits G3–G5 ne sont pas injectés rétroactivement dans le bundle 8ff089b déjà construit.

## Captures opérateur originales

Fichiers copiés sans transformation depuis les pièces transmises. Leur hash identifie les octets consignés, pas l'authenticité de la machine ou de l'heure.

| Capture | SHA-256 |
|---|---|
| [systeme-services-stockage.jpg](evidence/publishers_20261016/systeme-services-stockage.jpg) | `3adda13b529b2ecf1a4ed6c1bb041c75e43830f9eca6f4a7a93476dec9e4e34f` |
| [evenements-indisponibles.jpg](evidence/publishers_20261016/evenements-indisponibles.jpg) | `c0833b4c404bf7373eb8e292d852e5b1ad3cd1be43e542740a5800b4c83dce52` |
| [travaux-29.jpg](evidence/publishers_20261016/travaux-29.jpg) | `09d95392cecc00f48af88b115a3cdde5f683f0ba1608a62da6e561ea3067eef5` |
| [travaux-filtre-3-sur-29.jpg](evidence/publishers_20261016/travaux-filtre-3-sur-29.jpg) | `45c5534ba87be062e1430e677ecbe30ce08e5604b6001bf3a1dc22bb8ae72435` |
