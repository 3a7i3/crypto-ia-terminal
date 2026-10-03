# APP-EVENTS-01 — Centre d’événements en lecture seule

Mission #361, parent #323, roadmap #285, #286 ACTIVE.
Base source : `7d7b29669f9940f5e7e47b5b1c7d88371f067fbb`.
Contrat et implémentation source ; aucune publication Machine admise par cette PR.

## Sources et consommateurs

| Source explicitement sélectionnée | Format / producteur existant | Consommateurs source connus | Frontière Events |
|---|---|---|---|
| `p12_alerts` | `observability.alerting.Alert.to_dict`, JSONL optionnel `AlertEngine` | tests production observability, appelants de `check` | sept règles connues ou OTHER_ALERT ; sévérité, date UNIX |
| `supervision_alerts` | `supervision.alert_manager`, audit plat/niché, corrections autoheal | `dashboard.alert_dashboard`, panels CI/HTTP, tests supervision | alertes ; corrections exclues et comptées ; date sans fuseau UNKNOWN |
| `ppl_lifecycles` | projection U2 BurnInStatusSnapshot, `lifecycle_history` | API /burn-in, BurnInStatusView, Direction | OPEN/terminal déjà projetés ; jamais une lecture du store PPL |

Cette carte est une preuve source, pas l'activation des producteurs ni une preuve
de déploiement. `AlertManager` peut émettre sur EventBus et déclencher autoheal :
le nouveau builder/reader ne l'importe pas. L'ancien `load_audit` masque les
lignes invalides et confond fichier absent/vide ; il n'est pas utilisé.
Les notifications Telegram/email et leurs services restent inchangés.

## Chaîne et admission

Sources choisies par chemins CLI explicites → capture bornée/stable → adaptation
passive → `event_center_snapshot.json` atomique → reader strict → GET
`/api/operator/v1/events` → `/paper-live/events`.
L'API/frontend ne lit aucun JSONL/store et n'importe aucun moteur métier.
`EVENT_CENTER_SNAPSHOT_PATH` sélectionne seulement l'artifact API, jamais les
sources brutes. Aucun source path implicite, `latest`, scan de dossiers ou tâche
runtime ajoutée. Sans chemin configuré, source NOT_CONFIGURED.

Une génération ne certifie ni la provenance scientifique ni la réalité runtime.
La sélection de sources réelles et sa publication ont leur gate distincte.
Commande locale, avec entrées autorisées et sortie isolée :

```bash
python -m observability.event_center_snapshot \
  --out /tmp/events/event_center_snapshot.json \
  --generated-at-utc 2026-10-03T00:00:00Z \
  --p12-alerts /tmp/events/p12.jsonl \
  --supervision-alerts /tmp/events/audit.jsonl \
  --ppl-lifecycles /tmp/events/burn_in_status_snapshot.json
```

## Contrat fermé 1.0.0

Autorité OBSERVATIONAL_PRESENTATION, mode READ_ONLY. Trois sources fixes avec
format/status, SHA-256 exact de capture, populations connues, exclusions,
publication/troncature, dates et epoch lorsque présentes. Aucune valeur PnL,
équité, prix, contexte brut ou message libre exportée. Les titres sont des
libellés statiques des types ; OTHER_ALERT n'interprète pas une règle inconnue.
Une sévérité historique n'affirme pas une alerte actuelle non résolue.

Chaque événement porte une identité déterministe, source/record, type/sévérité,
date UTC explicite ou UNKNOWN/null ; symbole et séquence pour PPL uniquement.
Identité alertes liée au record brut + sa ligne, stable sur append ; PPL liée à
l'epoch/trade et aux champs projetés. Pas de déduplication entre sources : leur
identité et couverture restent distinctes.

Lectures régulières non symlink/non bloquantes, 2 MiB par source/artifact,
10 000 records, 100 événements publiés par source. Source qui change pendant
lecture, record JSON malformé/dupliqué/non fini, ligne incomplète ou timestamp
futur : source INVALID sans lignes partielles. Fichier trop gros : OUTPUT_LIMIT.
Erreurs I/O : READ_ERROR, absent : MISSING. Aucun stderr/contenu brut exposé.
Unknown paths et erreurs ne reçoivent aucun faux compteur zéro.

PRESENT avec 0 events signifie uniquement zéro dans cette capture, jamais zéro
incident machine. Corrections supervision exclues avec compteur visible.
PPL couvre OPEN/terminal de la projection, pas le journal complet (epoch,
recovery et autres événements non représentés restent hors périmètre).
Les symboles/séquences/epoch doivent satisfaire les contraintes fermées.

Ordre : source fixe, puis date décroissante, événements non datés à la fin de
leur source ; égalités départagées par record/identité. Pas de chronologie globale
fabriquée ni de timezone implicite. Une source sans date peut rester consultable
avec UNKNOWN. Les filtres React conservent l'ordre et portent sur les seules
lignes publiées, sans nouvelle requête/calcul de verdict.

## Transport, fraîcheur et UX

GET valide : 200 avec projection et annotations temporelles ; artifact absent,
invalide ou futur : 503, code fermé, pas de fallback. FRESH/STALE du snapshot
mesure la génération de présentation (seuil 90 s), pas la liveness des moteurs.
La source PPL porte son âge/fraîcheur séparés depuis sa projection U2. Les
journaux d'alertes n'ont pas de heartbeat attesté : fraîcheur source UNKNOWN,
même si capture FRESH. Aucun mtime traité comme preuve d'activité.

Vue indépendante du snapshot Advisor, cartes sources, couverture, filtres
source/sévérité, cartes événements et détail provenance ; dates null visibles,
empty/filtre vide distincts de missing/error. Données STALE décrites comme
historiques ; erreur refresh retire les anciens événements. Chargement, erreurs
réseau/API/contrat, mobile 390 et desktop 1440 vérifiés. Couleur + libellé/icône,
focus accessible et identités longues sans overflow. Aucune commande humaine.

## Validation et frontières

Tests discriminants : append identity, source changed/bounded reads, strict JSON,
correction exclusion, naive/aware/future timestamps, missing/empty/partial sources,
PPL via producteur U2 réel synthétique, atomic output/source immutability, reader
GET-only, contrats Python/TS, cross-stack et captures. Fixtures synthétiques ne
deviennent pas preuves Machine.

Rollback source : revert de la PR. Aucune action VPS/deploy/systemd, restart
Advisor, mutation PPL/FIN/epoch/config/risk/sizing, activation Watchdog/autoheal,
retrait de notifications ou CryptoRadar. Fusion source ≠ publication runtime.
