# G3 `plan` runtime-service — résultat consigné (publishers passifs)
Statut : **enregistrement d'une preuve opérateur, source seule**. Rien n'est lancé, installé ni activé par ce document. #286 reste actif. Le `run` G3 n'est pas autorisé et reste en attente.

## 1. Provenance
- **Rapporté par l'opérateur** (Mathieu), collé dans le fil du projet le 2026-10-15 à 06:27Z ; exécution à **2026-10-15T06:27:16Z** sous `mathieu` (uid 1001), **sans sudo**, sur `crypto-advisor-2`. Sortie citée telle que collée ; aucun accès indépendant au VPS par un agent.
- Fichier téléchargé par URL épinglée au commit `589d3ea1bb4123e7a61f3420a1c3af9a4055bb4a` (`deploy/passive_publishers/g3_paste_block.sh`) vers `~/g3-staging/g3_paste_block.sh.part`, vérifié par `sha256sum -c` (**OK**), puis renommé. Empreinte du bloc imposée : `9810f2412d09717da86474c65248fb1d19ddd700d56ed5d8355964d17cccdfa4`. Copie temporaire du script (`/tmp/g3priv.eNYeqQ/g3.sh`) : `OK` (empreinte `4a125f6e17d973999ec37df6bec830013116c079ecfd3e4dc1ba88ebcb513e39`).
- Codes de sortie : `G3 plan runtime-service exit status: 0` ; `transfer+plan exit status: 0`.

## 2. Résultats rapportés
| Contrôle | Résultat |
|---|---|
| `NeedDaemonReload` | `no` pour `crypto-advisor`, `crypto-operator-api`, `crypto-operator-web` et les quatre unités publisher |
| Empreintes, propriétaire, mode des quatre unités | conformes (`0ef373c4…b1ad`, `d1c779f0…53bd`, `72149a41…d4a1`, `afeacf3e…18f4`), `root:root 644` |
| États | services `inactive`/`static` ; timers `inactive`/`disabled` |
| Dossier de présentation | `/home/mathieu/operator_presentation` : `mathieu 700` ; vide (artefact présent : non) |
| Artefact de l'autre publisher (`storage_snapshot.json`) | absent |
| `crypto-publish-runtime-service.service` | `ExecMainStartTimestampMonotonic=0` : aucun démarrage enregistré dans la propriété observée à cet instant (cette propriété seule ne prouve pas tout l'historique) |
| `healthz` avant | 200 |
| Verdict | `RESULT: OK (preconditions hold)` ; « nothing was started or written (plan) » |

## 3. Ce que ce résultat ne prouve pas
- Aucun service n'a été lancé : il ne dit rien du comportement du sandbox, de `systemctl show` sous `PrivateNetwork`, de l'écriture de l'artefact ni de la durée d'exécution.
- Il décrit l'état à 06:27Z ; le `run` refait ses contrôles au moment de l'exécution et refuse si l'état a changé.
- Le plan n'a pas lancé les validateurs de contrat sur un artefact (il n'y en a pas encore) ; il a seulement vérifié qu'ils sont importables dans la release déployée.
- Pas d'accès indépendant au VPS par un agent.

## 4. Suite
Le `run` reste en attente : l'exception G3 n'est pas publiée et la CI du HEAD qui contient ce script doit être vérifiée avant toute utilisation privilégiée. Voir [l'exception préparée](../governance/EXCEPTION_286_G3_PUBLISHERS_ONESHOT.md).
