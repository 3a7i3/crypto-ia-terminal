# Exploitation du socle livré

État documenté du 16 novembre 2026, pas autorisation permanente d'administrer tous les domaines. Accès/URLs, chemins privés des releases/corpus et scripts root sont conservés dans la custody opérateur. Ne pas installer le patch de référence comme un nouvel outil.

## Utilisation

Activer Tailscale sur le Samsung, ouvrir l'icône Crypto AI existante. L'origine habituelle443 ouvre Marché/Radar MEXC ; rechercher une paire, choisir bulles/Liste, ouvrir sa fiche, changer M5/M15/H1/H4. Les 300 bougies disponibles et les 60 dessinées sont deux nombres distincts. Lire état source, âge ticker et réception de la série. Dernière bougie partielle : pas de clôture supposée.

Si app ancienne : fermer/réouvrir, puis vérifier worker/asset effectivement servi avant de conclure à un problème serveur. Aucun APK nouveau. Ne pas vider arbitrairement les données ni réinstaller pour masquer une erreur de routage.

## Contrôles de lecture

```bash
systemctl show crypto-operator-web.service crypto-operator-api.service \
  cat-or-live-collector.service cat-or-live-api.service cat-or-live-web.service \
  -p Id -p ActiveState -p UnitFileState -p NRestarts -p MemoryCurrent --no-pager
journalctl -u cat-or-live-collector.service -n 20 --no-pager
```

L'API de la même origine expose `/api/operator/v1/spot-radar/health`, `/scanner`, `/overview` et `/ohlcv?symbol=BTCUSDT&timeframe=M5`. GET public marché uniquement ; aucune clé/permission de trading. État de service actif ne prouve pas LIVE : lire source/horloges/fraîcheur.

## Actions opérateur ciblées, dans un mandat valide

Arrêt temporaire de collecte seulement (l'interface conserve ses états honnêtes, aucune donnée synthétique de remplacement) :

```bash
sudo systemctl stop cat-or-live-collector.service
```

Reprise :

```bash
sudo systemctl start cat-or-live-collector.service
```

Les trois unités scanner sont enabled. `stop` ne désactive pas le démarrage au boot ; pour arrêt durable, utiliser `disable --now` uniquement sur les unités scanner nommées dans une décision d'exploitation. Ne jamais appliquer ces commandes à Advisor/PPL/FIN.

## Incidents et récupération

- Refus provider/contrat : le collecteur peut s'arrêter sans restart automatique (codes3/4). Lire motif ; ne pas boucler de force ni changer d'IP pour contourner un refus.
- Échec réseau : backoff interne puis supervision systemd, avec limite de démarrages par heure. Pas promesse de disponibilité pendant panne fournisseur.
- Seuil disque/retenue : vérifier croissance et références, ne pas effacer les preuves historiques. Le corpus neuf a sa propre politique de rétention ; la limite entre campagnes n'est pas un quota dur.
- Défaut frontend : le rollback d'intégration retire seulement son override OR et restaure l'ancien frontend. Il conserve collecte, API historique et mappings Tailscale. Le chemin exact du script root est dans la custody privée. Le retour vers l'ancien frontend enlève l'intégration visuelle du scanner, pas ses données.
- Rollback scanner distinct : le script OR initial désactive les trois services live et restaure les readers du pilote arrêté ; ces données sont DISCONNECTED. Ce n'est pas une reprise LIVE.
- Retrait de8443 seulement : commande candidate déjà utilisée dans le mandat `sudo tailscale serve --https=8443 off`. Ne pas effectuer `serve reset`, ni modifier443 pour réparer8443.

## Limites non résolues

Interface trop petite, contrôle Liste complet absent, accès négatif autre pair non testé, reboot réel non testé, coût de maintenance/rechargement, fraîcheur OHLCV distincte du ticker et source Git non réconciliée. Aucune intervention sur l'epoch historique, aucun ordre, aucune activation Advisor n'est nécessaire à l'usage de ce socle.
