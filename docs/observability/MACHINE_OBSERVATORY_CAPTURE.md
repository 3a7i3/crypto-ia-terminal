# Observatoire machine — capture ponctuelle 0.1

Mission opérateur du 19 octobre 2026 UTC : rendre les sources et les défauts
de publication observables, avant de raccorder les vues existantes. #286 ACTIVE.
Ce changement est SOURCE_ONLY ; aucune installation, tâche périodique, route
API ou autorisation système n'est créée.

## Usage

Dans une copie source de revue, depuis un compte déjà autorisé à lire les
sources, le script écrit uniquement son rapport JSON sur stdout :

```bash
python3 -B scripts/machine_observatory.py \
  --source-root /home/mathieu/crypto_ai_terminal \
  --epoch BURN-IN-EPOCH-01-20260926T064144Z
```

`--api` ajoute dix GET sur des routes fixes à 127.0.0.1:8090 ; proxies et
redirections désactivés. `--services` ajoute un unique `systemctl show` sur
dix unités fixes, propriétés d'état uniquement. Aucune option n'accepte une
commande, une URL externe ou un chemin de secret à exporter.

L'exécution sur le VPS doit être un checkpoint explicitement autorisé ; ce
document n'autorise pas son installation dans le checkout gelé. Exécuter depuis
une copie séparée vérifiée. Ne pas employer sudo pour contourner un refus ;
l'opérateur fournit une capture ciblée depuis son compte autorisé. Conserver le
rapport dans un emplacement de preuve distinct, jamais sur un fichier source.

## Contenu et portée

- Métadonnées des artifacts connus, du config snapshot d'epoch et des fichiers
  `.env`, `.env.secret`, `.env.secrets`. Aucun contenu de ces fichiers n'est lu.
  La présence n'établit pas la lisibilité du contenu. Les noms de variables,
  leurs valeurs, validité et consommateurs restent NOT_COLLECTED.
- Lecture du seul JSONL PPL d'epoch sélectionné, chemin dérivé par SHA-256
  sous `databases/ppl_authority/store/epochs/` (chemin runtime observé le
  19 octobre ; le producteur métier reçoit sa racine store explicitement).
  Résumé de structure, comptage par type,
  séquences et empreinte du fichier à une frontière stable. Aucun payload, ID
  arbitraire, message d'erreur source ou valeur financière exporté.
- États des sources : MISSING, DENIED, INVALID_PATH, SOURCE_CHANGED,
  LIMIT_EXCEEDED et INVALID_DOCUMENT sont distincts d'une capture réussie.
- Sondage API : succès HTTP n'est pas validation du contrat. Les résumés PPL
  exposés par l'API ne constituent pas une sauvegarde canonique. Les différentes
  requêtes ne forment pas une transaction cohérente entre domaines.

Les lecteurs existants (`burn_in_status_snapshot`, `event_center_snapshot`,
`runtime_service_snapshot`, `storage_snapshot`) restent les producteurs métier.
Le script n'en recrée ni les calculs ni les publications. Il n'importe pas
Advisor, PPL/FIN ou le serveur de l'application.

## Frontières de sécurité et limites

Linux/POSIX, Python 3.10+. Parcours des chemins par descripteurs, refus des liens
symboliques dans chaque composant, fichiers réguliers uniquement, lecture non
bloquante des fichiers spéciaux refusés, maximum 4 Mio et 20 000 événements.
Modification détectée pendant la lecture : SOURCE_CHANGED, sans retry implicite.
Les fichiers ne sont jamais ouverts en écriture ; aucun lock métier n'est pris.
Une lecture peut mettre à jour atime selon les options du filesystem.

Le JSONL est lu intégralement pour le résumé ; ce n'est pas une vérification de
contrat PPL, un replay, une preuve d'authenticité, une réconciliation FIN ou un
bac à sable contre un compte ayant déjà accès aux données. Un adversaire
privilégié reste hors modèle. L'accès est borné par les permissions OS du compte
existant : le script ne les renforce ni ne les élargit.

Les requêtes HTTP ont un timeout socket de 3 s chacune et une limite de réponse
de 4 Mio ; ce n'est pas une garantie de durée globale contre un serveur qui
distille sa réponse. Le subprocess systemctl est borné à 3 s et 32 Kio, avec
environnement propre et stderr jeté. Il ne termine que son propre processus
enfant en cas de dépassement, jamais un service.

Aucun journal système, environnement de processus, fichier secret, Telegram,
exchange, réseau externe ou inventaire arbitraire de disque n'est consulté.
L'inventaire réseau et la livraison des notifications restent NOT_VERIFIED.
Les chemins d'artifacts sont les défauts connus, pas une attestation de leur
configuration effective : les overrides systemd nécessitent une preuve séparée.

## Validation et suite

```bash
python3 -B -m unittest discover -s tests -p test_machine_observatory.py -v
```

Les tests couvrent l'exclusion des secrets, l'import passif, les fichiers
spéciaux/liens, les changements pendant la lecture, les bornes, les erreurs,
les séquences et la fermeture réseau. Après revue indépendante, une mission
distincte pourra qualifier un export canonique et raccorder les producteurs
aux vues burn-in/événements existantes. Ce script ne répare pas le site.

Qualification locale du 19 octobre 2026 UTC, base main
`d328aea50950ee7af00b2d588fb2743ddec428e3` : Python 3.11.17,
17 tests du collecteur réussis, également sous `-O` ; corpus ciblé collecteur,
runtime-service, cross-stack, J01 et Governance Tower : 1 001 réussis,
un avertissement de dépréciation Starlette. Ruff 0.15.8 sur les nouveaux fichiers
et baseline gate réussis (aucune nouvelle violation). Le résumé a également
été exécuté offline sur la copie API datée déjà capturée : 347 événements,
174 ouvertures et 172 clôtures, séquences continues ; pas une lecture canonique.
La régression complète et la CI distante ne sont pas attestées par cette note.
Le script n'a pas été exécuté sur le VPS. Revue indépendante encore requise.

## Module complémentaire : journaux filtrés et déclarations systemd

`scripts/machine_visibility_report.py --share` s'exécute ponctuellement comme
mathieu, depuis une copie séparée contenant également machine_observatory.py.
Il crée uniquement un nouveau rapport dans `/var/tmp/sentinel-visibility-*`,
avec lecture ACL pour chatgpt-ro et commande de révocation. Aucun droit sur les
sources ou les services n'est élargi ; aucun daemon n'est installé.

Huit journaux de services explicitement sélectionnés sont traités localement :
les 200 dernières lignes dans une fenêtre de 24 h, 1 Mio et 3 s maximum par
commande. Seuls le nombre de lignes et la répartition des priorités sortent du
module. Les messages bruts sont lus en mémoire mais jamais exportés. Aucune
preuve de livraison Telegram n'est déduite. Une fenêtre vide signifie
NO_VISIBLE_RECORDS avec permission NOT_PROVEN, jamais zéro activité certifiée.

Six fichiers d'unités/drop-ins fixes sont lus en mémoire ; seules les variables
de chemins de présentation en liste fermée et WorkingDirectory sont publiées.
ExecStart et les autres valeurs d'environnement ne sont pas exportés. Les
fichiers .env et secrets ne sont jamais ouverts. Les déclarations partielles
ne sont pas une configuration effective fusionnée par systemd ; les autres
drop-ins, overrides temporaires et modifications concurrentes ne sont pas
exclus par cette capture. Le modèle ne couvre pas un attaquant root/same-uid.

Les commandes sont fixes, sans shell ni stdout/stderr brut dans le rapport ;
timeouts et plafonds refusent la capture concernée. Le résumé des services
réutilise le collecteur à unités explicites, évitant l'inventaire vide obtenu
avec systemctl show sans noms d'unités. Le rapport est limité à 256 Kio.

Validation du complément : 25 tests unittest réussis (17 cœur + 8 complément),
Ruff 0.15.8 ciblé réussi. Le complément n'a pas encore fait l'objet d'une revue
indépendante ni d'une capture opérateur lors de cette qualification source.
