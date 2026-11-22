# Campagne de sept jours — Repository Cartographer (préparée, non démarrée)

Statut : **préparée, non démarrée**. Aucun timer, cron ou service n'est créé. Démarrer la campagne
demande une décision séparée de Mathieu, et une installation VPS distincte (voir INVOCATION_CONTRACT_V1 §5).

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
- absence : aucune invocation consignée dans les 36 h → Système affiche « Indéterminé », jamais « Actif » ;
- erreurs : tout `INVALID`, `INCOMPLETE`, `ACCESS_DENIED`, `UNREADABLE`, `ABANDONED` est un événement à noter.

## Exercices obligatoires

1. **Interruption** (jour 3) : arrêt brutal pendant une invocation. Attendu : verrou resté à bail, puis
   invocation suivante consigne `ABANDONED` (aucun état « en cours » au-delà du bail, soit 10 min).
2. **Reprise** (jour 3, après le bail) : invocation normale, `COMPLETED` / `PARTIAL`, activité `TERMINE`.
3. **Collision de nom** : tentative de republier un fichier existant. Attendu : refus `NAME_EXISTS`, ancien fichier intact.
4. **Empreinte altérée** (copie de travail uniquement, jamais sur le rapport réel) : Système affiche `INVALID`
   avec motif, gris.
5. **Coupure API** pendant une page ouverte (jour 5) : ancien vert retiré dans le cycle de sondage (30 s).

## Critères de fin

- 7 invocations consécutives PARTIAL (ou exercices inclus) sans écart d'empreinte non expliqué ;
- aucune invocation « en cours » au-delà du bail ;
- aucune régression sur les autres vues ;
- revue mobile clair/sombre refaite au jour 7.

Arrêt anticipé : toute exécution hors protocole, toute écriture hors `reports/`, tout accès réseau constaté.

## Livrables attendus

- journal des invocations (enveloppes JSON, expurgées pour GitHub) ;
- tableau durée / volume / erreurs ;
- verdict : « stable sur la durée observée » ou liste des écarts.

## Décisions à prendre avant démarrage (Mathieu)

1. Autoriser l'installation du lanceur sur l'hôte et la date de départ.
2. Confirmer le compte de l'API et ses droits de lecture (voir audit, §1 de INVOCATION_CONTRACT_V1).
3. Choisir si la campagne tourne de jour ou de nuit (heure UTC fixe recommandée).
