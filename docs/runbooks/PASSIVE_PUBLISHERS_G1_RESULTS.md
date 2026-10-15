# G1 — résultats consignés (publishers passifs)
Statut : **enregistrement d'une preuve opérateur, source seule**. Rien n'est installé, activé ni redémarré par ce document. #286 reste actif.

## 1. Provenance
- **Rapporté par l'opérateur** (Mathieu), collé dans le fil du projet le 2026-10-15 à 01:24Z, exécution à 01:23:56Z sous le compte `mathieu`, sans sudo pour G1 lui-même. La sortie n'a pas été vue par un agent sur la machine : elle est citée telle que collée, sans accès indépendant au VPS.
- Hôte : `crypto-advisor-2`, Ubuntu 22.04.5 LTS, noyau 6.8.0-1066 (bannière de connexion).
- **Code mesuré** : release déployée `1728b3ad952b87d903ccb7442579000da292b848` (code et venv de `/opt/crypto-ai-terminal/operator/staging-*`), tel que déployé. `PARTIAL_TAIL` / events 1.1.0 dans ce code : non (affiché par le script).
- **Script G1 exécuté** : sha256 `166caedb8161d9c3426f242442200fa0202f4500be44f2b14358f3766155e01e`, vérifié par le bloc (`g1.sh: OK`).
- **Bloc extérieur** (`g1_paste_block.sh`, sha256 attendu `82461e88cc2b0bc271107e297b37a27af7e0174176bac9e75896e89311c1b667`) : **non vérifié** pour cette exécution, le bloc ayant été collé directement dans le shell au lieu d'être lancé depuis un fichier de staging. Seule l'empreinte du script interne (celui qui s'exécute) a été contrôlée.

## 2. Résultats rapportés
| Contrôle | Résultat |
|---|---|
| `systemd-analyze verify` (6 unités) | statut 0. Deux messages d'hôte hors de nos unités : `netplan-ovs-cleanup.service … Permission denied`, `snapd.service:23 Unknown key name 'RestartMode'` |
| `systemd-analyze security --offline` | **SKIPPED** : cette version de `systemd-analyze` n'a pas `--offline`. Exposition de sécurité **non évaluée** |
| runtime-service, 5 exécutions | 0/5 échec ; 0,124 / 0,093 / 0,104 / 0,109 / 0,092 s (min 0,092, médiane 0,104, max 0,124) ; artefact 878 o ; `contract-valid=True`, `query_status OK`, `load_state loaded`, `active_state active` |
| storage, 5 exécutions | 0/5 échec ; 0,091 / 0,085 / 0,078 / 0,078 / 0,077 s (min 0,077, médiane 0,078, max 0,091) ; artefact 612 o ; `contract-valid=True`, `source_status PRESENT`, 50 entrées, 9 fichiers `decision_packets_*`, 383 296 557 o |
| events (1.0.0), 5 exécutions | 0/5 échec ; 0,111 / 0,100 / 0,091 / 0,094 / 0,110 s (min 0,091, médiane 0,100, max 0,111) ; artefact 1 230 o ; `contract-valid=True`, schéma `1.0.0`, `p12_alerts OUTPUT_LIMIT`, `supervision_alerts NOT_CONFIGURED`, `ppl_lifecycles MISSING` |
| Sources avant/après (`stat` : taille, mtime, ctime de `alerts.jsonl`, `burn_in_status_snapshot.json`, mtime/ctime de `databases/`) | `UNCHANGED` |
| Résumé / nettoyage | `RESULT: OK` ; `/tmp/g1.Qek09Z` supprimé, aucun processus restant ; `exit status: 0` |

Les durées sont celles du processus entier (démarrage de l'interpréteur, lecture, JSON, fsync) hors systemd. Plafond d'unité : 20 s ; cadence : 30 s.

## 3. Ce que ces résultats ne prouvent pas
- **Pas de preuve d'identité des contenus** : « UNCHANGED » compare des métadonnées `stat` (taille, mtime, ctime). Cela ne prouve pas que les octets sont identiques (un écrivain qui rétablit la taille et le mtime ne serait pas vu) ; c'est un indice, pas une preuve de contenu.
- **Sandbox systemd non exercé** : `PrivateNetwork`, `ProtectSystem=strict`, `ProtectHome=read-only`, `MemoryDenyWriteExecute`, `MemoryMax`, `CapabilityBoundingSet=` vide, `PrivateDevices` n'ont pas été appliqués. G1 lance les commandes hors systemd, sous `env -i`. Ils ne sont observés qu'en G3. En particulier : accès de `systemctl show` au bus sous `PrivateNetwork`, écriture dans `/home/mathieu/operator_presentation` sous `ProtectHome=read-only` + `ReadWritePaths`.
- **Exposition de sécurité offline** non évaluée (voir ci-dessus) ; à refaire sur les unités installées (G2 `verify`, puis `systemd-analyze security <unité>` sur l'hôte si disponible).
- **Aucun écriture dans le dossier de présentation** : il n'existait pas lors du dernier relevé et n'a pas été créé.
- **Pas de mesure sous charge** : coût faible (≤ 0,124 s) ne garantit pas les délais quand le système est chargé (Advisor, API, autres timers). La cadence réelle est observée en G5.
- **PARTIAL_TAIL non validé** : le code mesuré est 1.0.0.

## 4. Lecture, avec ses limites
- **`p12_alerts` en `OUTPUT_LIMIT`** : cohérent avec ce que G0 laissait attendre (le contrat 1.0.0 refuse un journal trop grand), mais la **cause n'est pas discriminée** : plus de 2 MiB, ou plus de 10 000 lignes (G0 : 2 013 413 o, soit sous 2 MiB = 2 097 152 o ; le nombre de lignes est inconnu). La sortie G1 ne contient pas la taille ni le nombre de lignes. Une lecture complémentaire `stat -c %s` + `wc -l` de `alerts.jsonl` par `mathieu` les établirait ; elle n'est pas nécessaire au plan.
- **`ppl_lifecycles MISSING`** : la projection burn-in (`burn_in_status_snapshot.json`) n'a pas de producteur planifié ; elle reste `MISSING`, sans source de substitution (décision déjà consignée).
- **storage 50/9/383 296 557 contre G0 49/8/380 366 419** : écart de +1 entrée, +1 packet, +2 930 138 o entre G0 (2026-10-14) et G1 (2026-10-15). Compatible avec un écrivain vivant dans `databases/` ; **inférence, non vérifiée**. Aucune conclusion sur l'Advisor n'en est tirée.
- **Coût** : < 0,13 s par exécution pour les trois publishers, soit < 0,5 % de la cadence de 30 s. Les 2 × 30 s + 20 s = 80 s < 90 s (seuil de péremption de l'API) restent la contrainte de conception ; ils ne sont pas démontrés sous systemd.
- Décision prise sur ces preuves : **poursuivre** vers G2 (installation inactive), qui ne change aucun comportement observable.

## 5. Empreintes de référence
| Objet | sha256 |
|---|---|
| `g1_stage_verify_measure.sh` (script exécuté) | `166caedb8161d9c3426f242442200fa0202f4500be44f2b14358f3766155e01e` |
| `g1_paste_block.sh` (bloc) | `82461e88cc2b0bc271107e297b37a27af7e0174176bac9e75896e89311c1b667` (non contrôlé à l'exécution) |
| `crypto-publish-runtime-service.service` | `0ef373c474b380a03944d08a00c4b3666e8c0a3269039a9b2d704545dca0b1ad` |
| `crypto-publish-runtime-service.timer` | `d1c779f0d9ebe3c9315e1b1ea0e9ef6695e9e1278d8d37755222c0023b3e53bd` |
| `crypto-publish-storage.service` | `72149a4174344f226063c4a714b690cddbc21a0e9dd91f2921a62271b6b0d4a1` |
| `crypto-publish-storage.timer` | `afeacf3ea6687980a7c19b012e1c6cc0b7be791d023a487be604e30bf68e18f4` |

G1 n'est pas relancé sans raison nouvelle (changement d'unité, de release, ou doute sur une mesure).
