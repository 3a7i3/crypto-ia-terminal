# Campagne de sept jours — Repository Cartographer (préparée, non démarrée)

Statut : **préparée, non démarrée**. Aucun timer, cron ou service n'est créé. Démarrer la campagne
demande une décision séparée de Mathieu, et une installation VPS distincte (voir CARTOGRAPHER_INSTALL_PROCEDURE.md).

## Objet

Stabilité sur **la durée observée**, pas une fiabilité illimitée. La campagne valide : durée, volume,
erreurs, empreintes, interruption et reprise, et l'affichage. Elle ne valide ni un voyant vert durable,
ni le branchement du registre.

## Protocole (une invocation par jour, UTC)

| Élément | Règle |
|---|---|
| Invocation | une par jour, même mission (`mission_id` 02e0f78f…), même zone (`e387318e`), code SHA figé pour toute la campagne |
| Déclenchement | une commande explicite, jamais une relance automatique |
| Durée attendue | ≤ 30 s (mission `max_wall_ms`), mesure par invocation |
| Résultat attendu | PARTIAL, deux cibles INCONCLUSIVE, `content_sha256` `67bdcc05…` (inchangé tant que la zone est inchangée) |

## Suivi (par invocation)

- durée (`started_utc` → `ended_utc`), mémoire maximale si mesurable, nombre de fichiers lus ;
- issue : `state`, `result_status`, `exit_code` ;
- empreinte : recalcul de `content_sha256` et `report_sha256` ;
- absence : aucune invocation consignée depuis plus de 36 h → règle implémentée et testée : `mission_overdue`,
  libellé rouge « … · aucune mission depuis plus de 36 h », jamais « Actif » ;
- erreurs : tout `INVALID`, `INCOMPLETE`, `ACCESS_DENIED`, `UNREADABLE`, `ABANDONED` est un événement à noter.

## Exercices obligatoires

1. **Interruption** (jour 3) : arrêt brutal pendant une invocation. Attendu : le noyau libère le verrou
   immédiatement, « en cours » disparaît à la lecture suivante (interface : ≤ 30 s + requête, au plus tard
   90 s) ; l'invocation suivante consigne `ABANDONED`.
2. **Reprise** (jour 3, après le bail) : invocation normale, `COMPLETED` / `PARTIAL`, activité `TERMINE`.
3. **Collision de nom** : tentative de republier un fichier existant. Attendu : refus `NAME_EXISTS`, ancien fichier intact.
4. **Empreinte altérée** (copie de travail uniquement, jamais sur le rapport réel) : Système affiche `INVALID`
   avec motif, gris.
5. **Coupure API** pendant une page ouverte (jour 5) : vert retiré à l'abandon de la requête (≤ 40 s), au plus
   tard à l'échéance locale (90 s).

## Critères de fin

- 7 invocations consécutives PARTIAL (ou exercices inclus) sans écart d'empreinte non expliqué ;
- aucune invocation « en cours » sans verrou noyau tenu ;
- aucune régression sur les autres vues ;
- revue mobile clair/sombre refaite au jour 7.

Arrêt anticipé : toute exécution hors protocole, toute écriture hors `reports/`, tout accès réseau constaté.

## Livrables attendus

- journal des invocations : enveloppes JSON conservées sur le VPS, **non publiées dans GitHub** (même expurgées)
  sans autorisation spécifique ; seul un résumé chiffré est rapporté ;
- tableau durée / volume / erreurs ;
- verdict : « stable sur la durée observée » ou liste des écarts.

## Décisions à prendre avant démarrage (Mathieu)

1. Autoriser l'installation du lanceur sur l'hôte et la date de départ.
2. Valider l'accès en lecture de l'API (`lecanada26`) à `runs/` et `locks/` (procédure d'installation, étape 4).
3. Choisir si la campagne tourne de jour ou de nuit (heure UTC fixe recommandée).
