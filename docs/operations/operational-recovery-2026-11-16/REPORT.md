# Réalisations et preuve datée

## 1. Résultat produit

L'utilisateur ouvre son icône Crypto AI existante et consulte le radar MEXC Spot sur l'origine privée habituelle HTTPS 443. Recherche de symbole, filtres de fraîcheur, vue bulles et bascule Liste sont disponibles dans le code ; bulles, sélection de paires et plusieurs unités de temps ont été démontrées sur le Samsung S24+. La recette complète du mode Liste n'a pas été fournie.

La fiche montre prix public, variation 24 h qualifiée, volumes base/quote natifs, bid/ask qualifiés `RECEIPT_ONLY`, identités, timestamps source/réception, état de fraîcheur et OHLCV. Les nouveaux chandeliers et volumes représentent les 60 dernières bougies de la série, avec tableau exact et distinction close/partielle. Aucun indicateur, phase, régime actuel, classement prédictif ou signal de trading n'a été ajouté. Une variation 24 h ne représente ni pression directionnelle ni probabilité.

## 2. Périmètre et chronologie

Les dates ci-dessous sont UTC, le 16 novembre 2026 ; Mexico = UTC−6.

| Séquence | Réalisation | Preuve / limite |
|---|---|---|
| W0–W5, M1-B.6→B.7 | 14 empreintes d'entrée conformes ; prototypes relus ; 26 cas historiques rejoués ; 24 méthodes RC ajoutées ; verrou/journal locaux, identité parent boot/PID/starttime, supervision OS avec fermeture fake | `M1_PRIVATE_PUBLICATION_RC1.zip`, verdict global PARTIAL ; adaptateur systemd réel absent, Human Approval Gate atteint |
| W4 | Revue par agent distinct ; correction du nettoyage qui laissait API/Web actifs après échec de retrait ; refus d'une référence 443 arbitraire avant publication | Indépendance partielle (même environnement/modèle), pas audit externe ; tests rejoués |
| Changement de priorité | GO OPERATIONAL RECOVERY OR-03→OR-06 reçu ; M1-B.9→B.13 suspendus, acquis conservés | Autorisation en conversation, sans URL publique inventée ; la qualification M1 n'est pas déclarée terminée par ce changement |
| Audit initial | Ancien frontend/API actifs, ports scanner libres, release D1-RC1 et dépendances présentes ; identité du compte de service vérifiée | Aucun D1/D2/D3 reconstruit ; restriction sudo de Desktop Commander constatée |
| 08:02:57→08:17:59 environ | Pilote public neuf, 15 min, 30 instruments, API et web dédiés | Résultat final : exit 0, 900118 ms, 60 cycles, 427 requêtes, 0 échec, 120 historiques référencés, pic RSS 79220 KiB |
| Après 08:04 | Publication privée 8443 et première recette Samsung ; chemin historique 443 conservé | Règles effectives transmises : 8443 TCP réservé au Samsung IPv4/IPv6 ; refus par autre pair non exercé |
| 09:20:09 | Installation de trois services permanents et corpus OR-LIVE neuf | Activation au démarrage ; campagnes existantes de 900 s réutilisées, pas moteur M1 reconstruit |
| 09:22:29→09:22:47 | SIGKILL réel du collecteur opérationnel, restart systemd automatique | Compteur de restart incrémenté, nouvelles observations reçues ; API/web restent actifs |
| 10:40:51 | Maintenance du nouveau corpus réellement exécutée | 760 fichiers non référencés évincés ; 328791632 octets retenus à cet instant ; aucun corpus historique ciblé |
| 10:41:03→10:41:24 | Première tentative d'intégration au frontend habituel, puis rollback | Assets root-owned en 0700 : service Node actif mais lecture impossible ; ancien frontend restauré HTTP 200 |
| 10:43:50 | Reprise corrigée | Assets seuls en 0755/0644 ; lecture effective sous compte de service ; nouvelle UI, API MEXC et anciennes routes vérifiées |
| Après reprise | Frontend habituel activé au démarrage par l'opérateur | `systemctl enable`, état enabled confirmé au relevé suivant |
| 10:46 environ | Recette graphique Samsung fournie | BTC M15/H4, ASTER H4, ENA H4 : chandeliers, volumes, changement UT et tableau ; pas preuve exhaustive de tous les instruments |
| 10:50:17 | Relevé final de cette synchronisation | Voir §3 ; observation ponctuelle, pas garantie de disponibilité future |

## 3. État réellement observé à 10:50:17 UTC

Les cinq unités suivantes sont `active / enabled` :

| Unité | Compteur de restart | Mémoire cgroup relevée (octets) |
|---|---:|---:|
| `crypto-operator-web.service` | 0 depuis activation de la nouvelle release | 23736320 |
| `crypto-operator-api.service` | 0 | 38952960 |
| `cat-or-live-collector.service` | 6 (SIGKILL et renouvellements normaux cumulés) | 130453504 |
| `cat-or-live-api.service` | 0 | 37601280 |
| `cat-or-live-web.service` | 0 | 17485824 |

Ces mémoires cgroup incluent des ressources/cache ; elles ne sont pas des RSS Python comparables au pic du pilote. Disque : environ 60 Go disponibles, 39 % utilisés. Pas de mesure de charge CPU soutenue certifiée ici.

Health via le frontend habituel : `PUBLIC_OBSERVED`, `spot-radar/1.0.0`, MEXC Spot `PUBLIC_REST`, 30 observés/sélectionnés, LIVE=30 et STALE/DISCONNECTED/UNRESOLVED/SYNTHETIC=0. 120 références OHLCV disponibles sur 120 attendues. Collecteur RUNNING / PUBLIC_REST_OK, 38 cycles, 301 requêtes, 0 échec dans la campagne courante. Snapshot et empreintes sont dans le manifeste. Les 120 références ne prouvent pas seules la complétude de chaque série.

L'API historique est restée active sans redémarrage pendant l'intégration. Le frontend historique, lui, a été **remplacé et redémarré explicitement** ; ne pas prétendre que son ancien PID est resté inchangé. Son service et les routes historiques sont conservés. Le mapping 443 reste dirigé vers le frontend habituel, 8443 vers le frontend scanner séparé. Aucun reset global Tailscale.

## 4. Déploiement, accès et mise à jour de l'app

L'installation D1-RC1 existante sert le backend scanner. Le nouveau frontend habituel est une release OR-APP isolée issue du frontend-source D1-RC1, avec le delta joint. Les chemins privés, adresses et identifiants d'accès restent dans la custody privée, pas dans ce dépôt public.

Le proxy du frontend route uniquement les GET/HEAD `spot-radar` vers le reader scanner ; les autres API continuent vers l'Operator API historique. Le frontend ne contacte pas MEXC et ne lit pas les corpus. L'identité du manifeste PWA (`id=/`, scope `/`) est conservée. `/` et `/direction` ouvrent maintenant le radar ; le radar est aussi le défaut de Marché. Worker/cache versionnés, HTML/API sans cache, assets hashés ; intervalle de vérification PWA réduit de 15 à 3 min pour les nouveaux clients. Une ancienne session peut encore attendre son ancien cycle de mise à jour ; fermeture/réouverture peut être nécessaire. Pas de nouvel APK.

**Portée d'accès :** 8443 avait une règle Samsung-only. L'intégration sur 443 utilise les droits privés déjà appliqués à 443, plus larges dans les règles transmises. Elle n'hérite pas automatiquement de la restriction Samsung-only de 8443. Aucune ACL changée ; aucune exposition Internet/Funnel observée dans Serve. Le test négatif depuis un autre pair n'a pas été réalisé.

## 5. Tests, nature et portée

| Campagne | Résultat exécuté | Ce qu'elle ne prouve pas |
|---|---|---|
| M1 historique + RC | 26 cas historiques + 24 méthodes RC ; reproduction depuis ZIP et manifeste 32/32 | Ni systemd/Tailscale réels ni certification M1 globale ; verdict PARTIAL conservé |
| Maintenance OR | 3 tests passés localement et sur VPS : rétention transitive/idempotence, refus hors corpus géré, refus symlink | Pas preuve de rétention sur plusieurs jours ni de quota disque dur |
| Frontend intégré | SpotRadarMap 7 + contrat 16 + graphique 4 + ouverture app 2 = 29 tests Vitest passés | Tests ciblés, pas suite frontend exhaustive |
| Runtime/PWA | 17 tests Node passés, dont méthodes refusées, erreurs transport, frontières cache, identité/worker | Pas recette navigateur automatique exhaustive |
| Build | TypeScript + Vite réussis avec dépendances déjà installées, lock identique à la base | Pas nouvelle CI GitHub ; avertissements config Vite et bundle >500 kB conservés |
| Intégration HTTP réelle en loopback | HTML/routes/assets/manifest/SW 200 ; scanner 30 lignes / 120 refs ; BTC M5 300 bougies ; ancienne API marché 200 ; POST 405 | Prévisualisation temporaire arrêtée après contrôle ; pas exposition de port dev |
| Reprise système réelle | SIGKILL collecteur puis reprise automatique, nouvelles données ; renouvellements normaux observés | Pas reboot hôte, crash tailscaled ni saturation disque réelle |
| Déploiement | Hashes vérifiés, échec permissions constaté, rollback puis lecture avec compte réel et succès de reprise | Rien n'est déduit de la seule compilation |
| Samsung physique | Même icône, carte, fiches, graphiques BTC/ASTER/ENA et UT montrés | Mode Liste complet et ergonomie de tous les écrans non qualifiés |

Aucun nouveau test logiciel n'est requis pour le texte de ce bilan. Les tests ci-dessus sont les résultats de leurs campagnes datées, pas une nouvelle exécution au HEAD de la PR documentaire. La CI de cette PR sera distinguée.

## 6. Limites à conserver

- Consultation disponible ≠ `OPERATIONAL_CERTIFIED`, U8, L4 ou A9. Aucun signal ni capacité Advisor certifié.
- Collecte réutilisée par campagnes de 15 min : pause 15 s, maintenance, puis bootstrap. La maintenance a duré environ 26 s au dernier passage ; le rechargement des 120 historiques s'ajoute. Ce n'est pas un flux sans interruption ni un redémarrage total de 15 s.
- Sélection bornée à 30 Spot USDT (BTC/DOGE/ATOM puis volume quote qualifié), pas marché global/perpétuels ; pas Top Focus, phases, ADX/DMI, RSI/EMA/ATR/VWAP/RVOL, CVD/OI ni heatmap spécialisée.
- Bougies actualisées selon les frontières de séries du collecteur réutilisé ; la dernière bougie partielle n'a pas nécessairement la fraîcheur du ticker. Afficher son heure de réception. Pas chart tick-by-tick ni outil complet de dessin/zoom.
- Interface encore trop petite sur les captures Samsung ; cause exacte (viewport, zoom ou CSS) non attribuée. Ne pas accuser le mode navigateur sans preuve.
- Rétention 1 h plus dépendances transitives ; les raws anciens non requis peuvent être évincés. Corpus d'exploitation non assimilable à un dataset Research immuable. Seuil 4 GiB et libre 5 GiB contrôlés entre campagnes, pas quota dur ; garde existante libre 3 GiB durant collecte. Rotation journaux opérationnels à 2 MiB, 4 sauvegardes + actif. Longue durée à mesurer.
- Code déployé hors main : sauvegarde du delta et de ses empreintes ici, intégration canonique/rebase/CI encore ouverte sous #576. Ne pas appliquer le patch à main comme s'il avait cette base.
- #286, #282, Gate O, U8, L4, autres modules sans sources et expériences gelées ne sont pas clôturés par ce bilan. Aucun ordre ni Advisor activé dans cette mission.
