# G2 `apply` et `verify` — résultat consigné (publishers passifs)
Statut : **enregistrement d'une preuve opérateur, source seule**. Ce document n'installe, n'active ni ne redémarre rien. #286 reste actif. L'exception GOV-286-PUBLISHERS-G2-INACTIVE (commentaire #286 `6185256612`) est **consommée** par cet `apply` ; son rollback reste autorisé selon ses conditions.

## 1. Provenance
- **`apply`** : exécuté par l'opérateur (Mathieu) sous `mathieu` avec sudo, à **2026-10-15T05:43:45Z** (heure donnée par l'opérateur). **La sortie de l'`apply` n'a pas été transmise à un agent** : seule l'heure l'est. Son déroulement détaillé (fichiers `created`, `daemon-reload`, `UNCHANGED`) n'est donc pas consigné ici ; seul l'état final ci-dessous le prouve indirectement.
- **`verify`** (lecture seule, sans sudo) : exécuté à **2026-10-15T05:49:33Z** sous `mathieu` (uid 1001), collé par l'opérateur à 05:50Z, sur `crypto-advisor-2` (Ubuntu 22.04.5 LTS). La copie temporaire du script (`/tmp/g2priv.lwtZ8N/g2.sh`) a passé la vérification d'empreinte (`OK`). Sortie citée telle que collée ; aucun accès indépendant au VPS par un agent.
- Bloc : `3117f492046bc0d9c840923c1eecac7058d3f8264ace3f6235866c2c181e2803` (commit `6e7f419ddbd234a2d2fe6b192e508c7e92a6e0f4`) ; script interne `9ad589ecd67ce9b414c8ef1128fe38a30650b55533a9f4dfb17d446baf3422d5`.

## 2. Résultats du `verify` (05:49:33Z)
| Unité | sha256 | propriétaire / mode | LoadState | ActiveState | UnitFileState |
|---|---|---|---|---|---|
| `crypto-publish-runtime-service.service` | `0ef373c4…b1ad` | root:root 644 | loaded | inactive | static |
| `crypto-publish-runtime-service.timer` | `d1c779f0…53bd` | root:root 644 | loaded | inactive | disabled |
| `crypto-publish-storage.service` | `72149a41…d4a1` | root:root 644 | loaded | inactive | static |
| `crypto-publish-storage.timer` | `afeacf3e…18f4` | root:root 644 | loaded | inactive | disabled |

`systemd-analyze verify` des unités installées : statut 0 (mêmes deux messages d'hôte qu'en G1/plan : `netplan-ovs-cleanup.service … Permission denied`, `snapd.service:23 Unknown key name 'RestartMode'`). Verdict : `RESULT: OK (all checks passed)` ; `G2 verify exit status: 0` ; « nothing was written (verify) ». Aucun lien d'activation, aucun `WantedBy`/`RequiredBy` actif, aucune unité n'a tourné (contrôlés par le mode `verify`).

## 3. Ce que ce résultat ne prouve pas
- Il ne prouve pas que les unités **démarrent** sous leur sandbox (`PrivateNetwork`, `ProtectSystem=strict`, `ProtectHome=read-only`, `MemoryDenyWriteExecute`…) : c'est l'objet de G3.
- Le `verify` ne compare pas Advisor/API/web à un état d'avant-`apply` : le relevé « avant/après » de l'`apply` n'a pas été transmis. Le fait qu'Advisor, API et web n'aient pas changé n'est donc **pas** établi par ce document (`NeedDaemonReload=no` et leur état seront de nouveau relevés en G3 avant toute action).
- Aucun artefact n'est publié ; l'API ne lit pas encore le dossier (G4).

## 4. Suite
G3 (essais ponctuels, un publisher à la fois, timers désactivés) : [exception et blocs préparés](../governance/EXCEPTION_286_G3_PUBLISHERS_ONESHOT.md), non exécutés. G4 et G5 restent exclus.
