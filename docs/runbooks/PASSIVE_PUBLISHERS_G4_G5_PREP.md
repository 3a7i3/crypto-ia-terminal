# G4 / G5 — préparation (source seule, rien n'est exécuté)
Statut : **préparation pour revue**. Aucun changement runtime, aucune autorisation n'est créée, prolongée ou antidatée. #286 reste actif. G4 attend la réussite de `storage` G3 ; G5 attend G4. Les commandes de référence sont celles du [plan G2–G5](PASSIVE_PUBLISHERS_G2_G5_PLAN.md) §4 et §5 ; cette fiche ne les remplace pas : elle liste ce qui manque avant de demander une autorisation.

## État de départ (preuves)
- `runtime-service` G3 : 3/3, **sortie rapportée par l'opérateur** (voir [résultat](PASSIVE_PUBLISHERS_G3_RUN_RUNTIME_SERVICE_RESULTS.md)). Publication préalable de l'exception : non établie.
- `storage` G3 : **non exécuté**. Exception brouillon non publiée (`docs/governance/EXCEPTION_286_G3_STORAGE_ONESHOT.md` si #450 est fusionnée). Le succès de `runtime-service` ne prouve pas `storage`.
- Aucun artefact `storage_snapshot.json` n'existe à ce jour (état déclaré au plan G3 ; à relire par un `plan` frais).

## Écarts à fermer avant toute demande d'autorisation G4
1. **Pas de bloc scripté G4.** G2 et G3 passent par un bloc haché (téléchargement épinglé, `sha256sum -c`, `plan` puis `run`). Le plan G4 est une suite de commandes `sudo` à saisir à la main : à remplacer par un script `g4_template.sh` / `build_g4.py` avec modes `plan` (sans sudo) et `run`, comparaison Advisor/web avant et après, arrêt au premier écart. Non écrit à ce stade.
2. **Le `start` des publishers dans l'action G4** (dernière ligne de l'action) est un usage d'exception G3 supplémentaire : il doit être couvert explicitement par l'exception G4, ou retiré et remplacé par les artefacts frais de G3 (qui vieillissent après 90 s, donc non suffisants). À décider.
3. **Mesure de durée G5.** Le plan G5 prévoit `ExecMainExitTimestamp − ExecMainStartTimestamp` comme critère d'arrêt (> 10 s). Le run G3 a montré `duration=0ms` alors que le journal indiquait ~2 s : cette méthode n'est pas fiable. Critère à fonder sur les horodatages du journal (`Starting` → `Finished`) et traiter une valeur 0 ou absente comme NOT_AVAILABLE, jamais comme une durée. La correction de lecture du script est en cours dans la PR #452 (source distincte, non utilisée pour `storage` sans décision).
4. **Compteurs de ressources** (`MemoryPeak`, `CPUUsageNSec`) : NOT_AVAILABLE au run G3 ; version de systemd de l'hôte inconnue. Une lecture `systemctl --version` (lecture seule) dans un `plan` frais la lèverait. Sans cela, `MemoryMax=128M` n'est pas éprouvée par une mesure en G5.
5. **Drop-in G4** : transfert vers l'hôte par URL épinglée + SHA-256 (`6e1d3afb…`), comme G3, et non par copie manuelle. Relevé préalable des drop-ins existants du service API et de `User=mathieu` à inclure dans le `plan`.

## Opération concrète G4 (à présenter avec son exception propre)
- Effets : création du drop-in `30-presentation-paths.conf` (2 variables), `daemon-reload`, redémarrage de `crypto-operator-api.service` seul (coupure de quelques secondes).
- Préconditions : `storage` G3 réussi et consigné ; timers `inactive`/`disabled` ; `User=mathieu` ; aucune des trois variables déjà posée ; Advisor, web relevés.
- Preuves attendues : `runtime-service` et `storage` en 200, contrat valide, `FRESH` ; `events` toujours 503 `*_MISSING` ; autres codes identiques ; Advisor et web `UNCHANGED` ; puis `STALE` après 90 s sans timer.
- Arrêt : API non `active` à 20 s, `NRestarts` > 0, code HTTP inattendu, Advisor/web touché.
- Rollback : suppression du drop-in, `daemon-reload`, redémarrage API (commandes du plan §4) ; limite : nouvelle coupure brève.

## Opération concrète G5 (exception propre, après G4)
- Effets : `enable --now` des deux timers (cadence 30 s), observation ≥ 5 périodes (10 min recommandées).
- Preuves : intervalles ≈ 30 s dans le journal, aucun chevauchement ni `Job canceled`, fraîcheur < 90 s, `Result=success`, `systemctl --failed` sans unité publisher, Advisor/API/web inchangés, vues Système vérifiées sur mobile (Événements reste indisponible).
- Arrêt : deux échecs consécutifs, un run > 10 s (selon le journal), `STALE` en fonctionnement normal, charge visible, Advisor touché.
- Rollback : `disable --now` des deux timers, puis G4 et G2 dans l'ordre inverse si nécessaire.

## Limites
Ces blocs ne prouvent rien tant qu'ils ne sont pas exécutés ; toute exécution suppose une exception publiée sur #286 avant le run, une expiration explicite, et une sortie consignée avant la gate suivante. Events reste hors de cette chaîne (release B).
