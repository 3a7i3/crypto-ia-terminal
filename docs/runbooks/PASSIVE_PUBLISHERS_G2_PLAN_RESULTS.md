# G2 `plan` — résultat consigné (publishers passifs)
Statut : **enregistrement d'une preuve opérateur, source seule**. Rien n'est installé, activé ni redémarré par ce document. #286 reste actif. Le `plan` est en lecture seule ; il ne prouve pas que `apply` réussira.

## 1. Provenance
- **Rapporté par l'opérateur** (Mathieu), collé dans le fil du projet le 2026-10-15 à 05:21Z ; exécution à **2026-10-15T05:21:23Z** sous le compte `mathieu` (uid 1001), **sans sudo**, sur `crypto-advisor-2` (Ubuntu 22.04.5 LTS, noyau 6.8.0-1066). La sortie n'a pas été vue par un agent sur la machine : citée telle que collée.
- **Commit source** : `6e7f419ddbd234a2d2fe6b192e508c7e92a6e0f4` (fusion de #444 dans `main`). Fichier téléchargé par URL épinglée à ce commit complet (`raw.githubusercontent.com`) vers `~/g2-staging/g2_paste_block.sh.part`, vérifié par `sha256sum -c` (**OK**) puis renommé ; non envoyé à un shell.
- **Empreintes contrôlées pendant l'exécution** : bloc `3117f492046bc0d9c840923c1eecac7058d3f8264ace3f6235866c2c181e2803` (`.part : OK`) ; copie du script interne dans `/tmp/g2priv.lfUiZK/g2.sh` : `OK` (empreinte `9ad589ecd67ce9b414c8ef1128fe38a30650b55533a9f4dfb17d446baf3422d5`).
- Mode `plan` : codes de sortie `G2 plan exit status: 0` et `transfer+plan exit status: 0`.

## 2. Résultats rapportés
| Contrôle | Résultat |
|---|---|
| Unités gardées (`crypto-advisor`, `crypto-operator-api`, `crypto-operator-web`) | `NeedDaemonReload=no` pour les trois |
| Quatre unités du paquet dans `/etc/systemd/system` | **absentes** (seraient créées) |
| `/home/mathieu/operator_presentation` | **absent** (serait créé 0700 `mathieu`) |
| Empreintes des quatre unités embarquées | `0ef373c4…b1ad`, `d1c779f0…53bd`, `72149a41…d4a1`, `afeacf3e…18f4` : conformes aux empreintes revues |
| `systemd-analyze verify` | statut 0 ; deux messages d'hôte hors de nos unités (`netplan-ovs-cleanup.service … Permission denied`, `snapd.service:23 Unknown key name 'RestartMode'`), déjà vus en G1 |
| Verdict | `RESULT: OK (all checks passed)` ; « nothing was written (plan) » |

## 3. Écritures du mode `plan`
Dossier d'attente `~/g2-staging/` (0700, `mathieu`) et fichier téléchargé ; deux dossiers temporaires `0700` dans `/tmp` (`g2priv.*`, `g2.*`) supprimés à la sortie. Rien dans `/etc`, `/var/lib`, systemd ni le dossier de présentation.

## 4. Ce que ce résultat ne prouve pas
- Pas que `apply` réussira sur l'hôte (écritures, `daemon-reload`, comportement de `systemctl show` sur les unités installées) ; pas que les unités démarreront (G3) ; pas qu'un artefact sera publié.
- Un état relevé à 05:21Z : `apply` refait ses vérifications au moment de l'exécution et refuse si elles ne tiennent plus.
- `systemd-analyze security` n'a pas été évalué (voir G1).
- Pas d'accès indépendant au VPS par un agent : preuve opérateur citée.

## 5. Suite
`apply` (G2, installation **inactive**) demande une exception #286 propre et une autorisation distincte : voir `EXCEPTION_286_G2_PUBLISHERS_INACTIVE_INSTALL.md`. Aucun `start`, `enable` ni `restart` ; G3 à G5 restent exclus.
