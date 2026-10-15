# G3 `run` runtime-service — résultat consigné (publishers passifs)
Statut : **enregistrement d'une preuve opérateur, source seule**. Ce document n'exécute, n'installe, ne démarre et n'active rien. #286 reste actif. La série `storage` n'est pas lancée et reste soumise à une décision distincte ; G4 et G5 restent exclus.

## 1. Provenance
- **Rapporté par l'opérateur** (Mathieu) : sortie collée dans le fil du projet le 2026-10-15 à 19:47:39Z ; exécution à **2026-10-15T19:47:16Z** sur `crypto-advisor-2`, sous `sudo` (`NOPASSWD: ALL` pour `mathieu`, vu dans `sudo -l`), avec confirmation `RUN`. Aucun accès indépendant au VPS par un agent : tout ce qui suit est la sortie telle que collée, non vérifiée par un agent.
- La première partie collée (téléchargement et début du `plan`) est tronquée au début ; seul le bas du `plan` est lisible : `RESULT: OK (preconditions hold)`, `G3 plan runtime-service exit status: 0`, `transfer+plan exit status: 0`. L'heure de ce `plan` n'apparaît pas dans la partie collée.
- Bloc : `sha256sum -c` **OK** sur `~/g3-staging/g3_paste_block.sh` (`9810f2412d09717da86474c65248fb1d19ddd700d56ed5d8355964d17cccdfa4`). Copie protégée root `/run/g3priv.ZXS1CX/g3.sh` : `OK`, empreinte du script `4a125f6e17d973999ec37df6bec830013116c079ecfd3e4dc1ba88ebcb513e39`. Ces deux empreintes sont celles de main (`4f4240c6`).
- Publication de l'exception sur #286 : **publication préalable non établie**. Les 10 commentaires de #286 ont été relus (le dernier est l'exception G2 du 2026-10-15T05:36:18Z) et une recherche sur le nom de l'exception ne donne rien : aucun commentaire G3 antérieur au run de 19:47Z. L'autorisation donnée dans la conversation n'est pas une publication GitHub ; aucune autorisation rétroactive n'est créée par ce document. Le texte `docs/governance/EXCEPTION_286_G3_PUBLISHERS_ONESHOT.md` reste un projet non publié.

## 2. Résultats rapportés
| Contrôle | Résultat |
|---|---|
| Préconditions | `NeedDaemonReload=no` (7 unités) ; empreintes, `root:root 644`, `inactive`/`static` pour les services, timers `inactive`/`disabled` ; dossier `mathieu 700`, aucun artefact avant ; artefact de `storage` absent ; `healthz` 200 |
| Essai 1/3 | `start exit status: 0` ; `Result=success ExecMainStatus=0 ExecMainCode=0 ActiveState=inactive` ; artefact `mathieu 600` 878 octets ; `contract-valid=True fresh-from-this-launch=True` ; `generated_at_utc=observed_at_utc=2026-10-15T19:47:17.172548Z` ; `healthz` 200 |
| Essai 2/3 | mêmes résultats ; `generated_at_utc=2026-10-15T19:47:22.728912Z` |
| Essai 3/3 | mêmes résultats ; `generated_at_utc=2026-10-15T19:47:30.321388Z` |
| Unités gardées | `crypto-advisor` (PID 882633), `crypto-operator-api` (PID 1941519), `crypto-operator-web` (PID 2555658) : `UNCHANGED (state, PID, NRestarts, InvocationID, start time, drop-ins)` |
| Verdict | `trials passed: 3/3` ; `RESULT: OK (all checks passed)` ; `G3 run runtime-service exit status: 0` ; `g3 run chain exit status: 0` |

Journal rapporté (`crypto-publish-runtime-service.service`) : trois séquences « Starting » → « Deactivated successfully » → « Finished » à 19:47:16–17, 19:47:22 et 19:47:28–30 (UTC).

## 3. Écarts et valeurs non disponibles (UNKNOWN ≠ 0)
**Aucune durée ni consommation exploitable n'est retenue pour ce run.**
- `MemoryPeak=NOT_AVAILABLE`, `CPUUsageNSec=NOT_AVAILABLE` aux trois essais : inconnu, ni 0 octet ni 0 ns. `MemoryMax=128M` n'a pas été éprouvée par une mesure.
- `duration=0ms` aux trois essais, alors que le journal de l'essai 3 montre ~2 s entre « Starting » et « Finished ». Valeur non retenue.
- Diagnostic en source (aucun nouveau run) : le script calcule `(ExecMainExitTimestampMonotonic − ExecMainStartTimestampMonotonic)/1000` après le retour de `systemctl start`, quand l'unité est déjà `inactive`. Si les deux propriétés valent `0` (valeur du plan avant run, à ce moment-là), le test `*[!0-9]*` les accepte et le script affiche `0ms` : un inconnu converti en zéro, ce que la règle UNKNOWN ≠ 0 interdit. Que les deux propriétés valaient bien `0` après le run n'est **pas établi** (elles n'ont pas été affichées). Les compteurs sont lus au même moment, unité arrêtée, et l'unité ne déclare ni `MemoryAccounting` ni `CPUAccounting` ; leur disponibilité après arrêt dépend de la version de systemd de l'hôte, **inconnue** (un `systemctl --version` en lecture seule la lèverait). Ce sont des hypothèses, aucune cause n'est établie.
- Le texte du script « 0 = never run since boot/reload » est à corriger par « aucun démarrage enregistré dans la propriété observée à cet instant » ; cela change l'empreinte et relève d'une évolution source distincte avec nouvelle revue. Le script épinglé n'est pas modifié.

## 4. Ce que ce résultat prouve et ne prouve pas
- Prouve (selon la sortie rapportée) : trois démarrages manuels du service oneshot, sous sandbox, ont réussi, écrit un artefact conforme au contrat de la release déployée `1728b3ad`, issu de chaque lancement, sans toucher aux timers ni aux unités gardées.
- Ne prouve pas : la cadence sous timer (G5), le raccordement de l'API (G4), l'affichage des vues Système, le comportement de `storage`, la durée ni la consommation de ressources (aucune exploitable), ni un état de l'hôte en dehors de la fenêtre 19:47Z.
- L'artefact `runtime_service_snapshot.json` (878 octets, issu du dernier essai) reste en place dans `/home/mathieu/operator_presentation`. Il est conservé : il doit rester inchangé pendant une éventuelle série `storage`.

## 5. Suite
- Le droit d'usage de l'exception pour `runtime-service` est consommé par ce `run`. Toute reprise exige une nouvelle autorisation.
- `storage` : décision distincte de l'opérateur après analyse de ce résultat.
- G4 et G5 : exceptions et autorisations propres.
