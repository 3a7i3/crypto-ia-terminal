# G3 `run` runtime-service — résultat consigné (publishers passifs)
Statut : **enregistrement d'une preuve opérateur, source seule**. Ce document n'exécute, n'installe, ne démarre et n'active rien. #286 reste actif. La série `storage` n'est pas lancée et reste soumise à une décision distincte ; G4 et G5 restent exclus.

## 1. Provenance
- **Rapporté par l'opérateur** (Mathieu) : sortie collée dans le fil du projet le 2026-10-15 à 19:47:39Z ; exécution à **2026-10-15T19:47:16Z** sur `crypto-advisor-2`, sous `sudo` (`NOPASSWD: ALL` pour `mathieu`, vu dans `sudo -l`), avec confirmation `RUN`. Aucun accès indépendant au VPS par un agent : tout ce qui suit est la sortie telle que collée, non vérifiée par un agent.
- La première partie collée (téléchargement et début du `plan`) est tronquée au début ; seul le bas du `plan` est lisible : `RESULT: OK (preconditions hold)`, `G3 plan runtime-service exit status: 0`, `transfer+plan exit status: 0`. L'heure de ce `plan` n'apparaît pas dans la partie collée.
- Bloc : `sha256sum -c` **OK** sur `~/g3-staging/g3_paste_block.sh` (`9810f2412d09717da86474c65248fb1d19ddd700d56ed5d8355964d17cccdfa4`). Copie protégée root `/run/g3priv.ZXS1CX/g3.sh` : `OK`, empreinte du script `4a125f6e17d973999ec37df6bec830013116c079ecfd3e4dc1ba88ebcb513e39`. Ces deux empreintes sont celles de main (`4f4240c6`).
- Publication de l'exception sur #286 : **non confirmée dans ce fil** au moment de cette consignation (l'agent ne l'a pas publiée). À rapprocher du commentaire éventuel de l'opérateur.

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
- `MemoryPeak=NOT_AVAILABLE` et `CPUUsageNSec=NOT_AVAILABLE` aux trois essais : la comptabilité de ressources n'est pas disponible pour ce service dans cette sortie. Cela ne signifie ni 0 octet ni 0 ns. La limite `MemoryMax=128M` n'a donc pas été éprouvée par une mesure.
- `duration=0ms` aux trois essais alors que le journal de l'essai 3 montre ~2 s entre « Starting » (19:47:28) et « Finished » (19:47:30). La valeur `duration` du script n'est pas fiable comme mesure de durée ; cause non établie (elle est calculée par le script à partir de propriétés systemd). Aucune durée n'est donc retenue.
- Le script affiche pour `ExecMainStartTimestampMonotonic=0` le texte « 0 = never run since boot/reload ». La formulation retenue par la gouvernance est « aucun démarrage enregistré dans la propriété observée à cet instant » ; cette propriété seule ne prouve pas tout l'historique. Corriger ce texte change l'empreinte du script et exigerait une nouvelle revue ; aucune modification n'est faite.

## 4. Ce que ce résultat prouve et ne prouve pas
- Prouve (selon la sortie rapportée) : trois démarrages manuels du service oneshot, sous sandbox, ont réussi, écrit un artefact conforme au contrat de la release déployée `1728b3ad`, issu de chaque lancement, sans toucher aux timers ni aux unités gardées.
- Ne prouve pas : la cadence sous timer (G5), le raccordement de l'API (G4), l'affichage des vues Système, le comportement de `storage`, la durée ni la consommation de ressources, ni un état de l'hôte en dehors de la fenêtre 19:47Z.
- L'artefact `runtime_service_snapshot.json` (878 octets, issu du dernier essai) reste en place dans `/home/mathieu/operator_presentation`. Il est conservé : il doit rester inchangé pendant une éventuelle série `storage`.

## 5. Suite
- Le droit d'usage de l'exception pour `runtime-service` est consommé par ce `run`. Toute reprise exige une nouvelle autorisation.
- `storage` : décision distincte de l'opérateur après analyse de ce résultat.
- G4 et G5 : exceptions et autorisations propres.
