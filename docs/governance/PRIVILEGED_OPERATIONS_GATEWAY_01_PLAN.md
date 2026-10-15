# PRIVILEGED-OPS-GATEWAY-01 — accès d'écriture contrôlé pour `chatgpt-ro` (plan pour revue)
Statut : **plan source pour revue. Aucun changement de droits, de configuration Desktop Commander, de sudoers, aucune installation, aucun service, aucun code de passerelle.** #286 reste actif ; Advisor, burn-in, secrets, FIN et trading sont exclus. Cette mission généralise [FRONTEND-DEPLOY-GATEWAY-01 (#432)](FRONTEND_DEPLOY_GATEWAY_CONTRACT_v1.md) : elle **réutilise** ses contrats et ses laboratoires, elle ne les contourne pas et ne les remplace pas.

Objectif : que `chatgpt-ro` puisse (1) **préparer** le travail dans un espace dédié, sans collage manuel, et (2) **demander** des opérations privilégiées *nommées*, approuvées une par une par l'opérateur, sans jamais détenir d'accès administrateur général.

## 1. Point de départ vérifié (provenance datée)
**Desktop Commander** (lecture seule via `get_config`, le 2026-10-15 ; aucune valeur modifiée, aucune commande bloquée essayée ou contournée) :
- appareil `crypto-advisor-2`, version 0.2.52, en ligne ; **un second appareil du même nom est enregistré et hors ligne depuis 54 h** (à révoquer par l'opérateur sur le portail du connecteur) ;
- shell par défaut `/bin/sh` ; `blockedCommands` contient notamment `sudo`, `su`, `dd`, `mount`, `visudo`, `useradd`, `iptables`… ; `allowedDirectories` est **vide** (aucune restriction de dossier au niveau du connecteur) ; `fileWriteLineLimit` 50 et `fileReadLineLimit` 1000 ; télémétrie activée ;
- toutes ces clés sont marquées `editable: true` : **le connecteur offre un outil pour modifier sa propre liste de blocage. Cette mission ne l'utilise pas et ne le requiert pas.**
- Conséquences : (a) `blockedCommands` est un filtre de noms de commandes, pas une frontière de sécurité (un autre binaire, un interpréteur ou un alias ne passe pas par ce filtre) ; (b) avec `allowedDirectories` vide, la **seule frontière effective est l'identité OS de `chatgpt-ro`** (uid 996 selon `WEB_WORKBOARD_FRONTEND_RELEASE.md`) ; (c) toute la sécurité de ce plan repose donc sur des droits système et un service séparé, jamais sur la liste de blocage.
- Capacités du connecteur utiles : écrire des fichiers (par blocs de 50 lignes), lancer des processus sous `chatgpt-ro`, lire les sorties. Aucune n'admet une élévation, et ce plan n'en demande pas.

**Passerelle existante (#432, ouverte, dernière mise à jour 2026-10-13)** — en `main` : contrat v1 + validateur pur de demande (`observability/frontend_deploy_request.py`) ; LAB-01 registre SQLite à usage unique (`BEGIN IMMEDIATE`, tests à deux processus et sorties abruptes) ; LAB-02 signature Ed25519 avec clé **épinglée** par le vérificateur ; LAB-03 composition signature + usage unique + release précédente connue. Tout est source/laboratoire.
| Gate du contrat | État vérifié |
|---|---|
| G0 contrat / propriétaire | partiel : contrat écrit ; propriétaire de la politique et racine d'authenticité **non nommés** |
| G1 prototype isolé | fait en laboratoire (LAB-01..03), clé et horloge d'essai |
| G2 qualification fautes / usage unique | **partielle** : sorties de processus seulement, pas de coupure de courant ni de fsync prouvé |
| G3 admission connecteur / politique | **NOT_ADMITTED** |
| G4 installation par l'opérateur | non faite |
| G5 activation et preuves d'exécution | **NOT_OBSERVED** |
Restent ouverts (liste du contrat) : propriétaire et racine de confiance indépendants du demandeur ; route de connecteur admise ; identité réelle du pair, horloge de confiance, révocation ; garde des artefacts et anti-substitution ; consommation atomique sous un service privilégié et reprise après panne ; release précédente et rollback ; limites de taille/charge/journal ; exception #286. **Aucun de ces points n'est résolu par ce document.**

## 2. Principe : deux périmètres distincts
| | Périmètre 1 — espace de préparation | Périmètre 2 — passerelle d'opérations nommées |
|---|---|---|
| Rôle | `chatgpt-ro` prépare, écrit, calcule, dépose | l'opérateur approuve, un service root exécute |
| Privilège | **aucun** (écriture dans un dossier à lui) | privilège confiné dans un service administré hors agent |
| Frontière | droits OS + point de montage dédié | séparation demandeur / autorisant / exécuteur |
| Dépend de | rien d'autre que l'installation initiale | périmètre 1 (dépôt des paquets), contrat #432 étendu |
Les deux sont livrables séparément ; le périmètre 1 seul supprime déjà le collage manuel de blocs de plusieurs centaines de lignes.

## 3. Périmètre 1 — espace de préparation dédié
- **Emplacement proposé** : `/srv/ops-workspace/` (propriétaire `chatgpt-ro:chatgpt-ro`, mode 0700), **hors** du checkout gelé (`/home/mathieu/crypto_ai_terminal`), hors `/opt/crypto-ai-terminal` et hors de toute release. Sous-dossiers : `packages/<id>/` (paquets à soumettre), `requests/` (demandes JSON), `receipts/` (reçus, **propriété root, lecture seule pour `chatgpt-ro`**), `scratch/`.
- **Bornes** : volume dédié (fichier image monté `nosuid,nodev,noexec`, taille plafonnée, par ex. 256 Mio) pour limiter l'espace et empêcher l'exécution directe de fichiers. Limite reconnue : `noexec` n'empêche pas `sh fichier` ; c'est une défense en profondeur, pas la frontière.
- **Ce que `chatgpt-ro` peut y faire** : écrire/éditer des fichiers (via le connecteur), construire des archives déterministes, calculer des empreintes, rédiger des demandes. **Ce qu'il ne peut pas** (par droits OS, sans filtre) : écrire hors de l'espace, lire `/home/mathieu`, toucher aux éléments de confiance du §5, obtenir une élévation.
- **Paquet** = un dossier `packages/<id>/` avec `MANIFEST.json` (liste des fichiers, sha256 de chacun, empreinte racine) ; il est considéré **mutable par son auteur** tant que la passerelle ne l'a pas copié en garde (§4). Aucune confiance n'est accordée à un paquet tant qu'il est dans l'espace.
- **Option opérateur (non requise)** : poser `allowedDirectories` du connecteur sur cet espace contraindrait les outils fichiers ; elle ne contraint pas le shell du connecteur, donc **n'est pas une frontière** et ne doit pas être présentée comme telle. Demande séparée, à la discrétion de l'opérateur.

## 4. Périmètre 2 — passerelle pour opérations nommées
### 4.1 Rôles et séparation
| Rôle | Identité | Peut | Ne peut pas |
|---|---|---|---|
| Demandeur | `chatgpt-ro` | déposer une demande JSON stricte dans `requests/`, des paquets dans `packages/`, lire `receipts/` | créer, signer ou modifier un ticket ; écrire dans les éléments de confiance ; lire la clé ; choisir un chemin, une commande ou une unité hors catalogue |
| Autorisant | l'opérateur (compte administrateur, jamais `chatgpt-ro`) | voir le détail calculé de la demande, approuver ou refuser | — |
| Exécuteur | code root fixe, installé par l'opérateur | exécuter *uniquement* une opération du catalogue, depuis la copie en garde, après vérification | accepter du texte shell, un chemin libre, une unité hors liste, une opération non approuvée |
`chatgpt-ro` ne doit **pas** pouvoir fabriquer sa propre autorisation : le ticket n'est écrit que par la commande d'approbation, sous root, dans un dossier que `chatgpt-ro` ne peut ni lire ni écrire.

### 4.2 Déroulement d'une opération
1. **Demande** : JSON ≤ 8 KiB, clés exactes (étendues de celles du validateur : `ticket_id`, `actor`, `audience`, `operation` ∈ catalogue, `params` typés par le catalogue, `package_root_sha256`, `expires_at`…), pas de champ libre exécutable. Un résumé libre du demandeur peut figurer mais est affiché « non vérifié ».
2. **Mise en garde (anti-substitution)** : la passerelle ouvre la demande et le paquet avec `O_NOFOLLOW`, refuse tout lien symbolique, fichier non ordinaire, `st_nlink` ≠ 1, propriétaire ≠ `chatgpt-ro`, taille hors borne ; **copie** le tout dans un dossier root `0700` (`custody/<id>/`) ; **recalcule les empreintes sur la copie** ; n'exécutera plus jamais que la copie.
3. **Présentation** : la passerelle calcule elle-même, sous root, ce que l'opérateur verra : opération, paramètres normalisés, empreinte racine, **plan à blanc** (les écrans « plan » comme celui de G2), état courant des unités concernées, expiration, rollback prévu. Rien de ce qui est montré comme fait ne vient du demandeur.
4. **Approbation** : `opsgw approve <id>` par l'opérateur. Deux étages possibles (§4.4).
5. **Exécution** : verrou exclusif non bloquant ; consommation atomique du ticket (registre SQLite root, `BEGIN IMMEDIATE`) **avant** l'exécution ; `STARTED` journalisé avant, `RESULT` après ; exécution par argv fixe tirée du catalogue (jamais `sh -c`), environnement vide, délai maximal par opération ; vérifications post-opération et plan de rollback définis dans le catalogue.
6. **Reçu** : écrit par root dans `receipts/<id>.json` (opération, empreintes, résultats de chaque vérification, verdict, état du rollback). `RESULT: OK` n'est écrit que si **toutes** les vérifications ont réussi ; un rollback dont une restauration a échoué est consigné **ROLLBACK_INCOMPLETE**, jamais « réussi ».
7. **Reprise** : toute commande `opsgw` lit d'abord le journal ; une opération `STARTED` sans `RESULT` met la passerelle en état `INTERRUPTED` : aucune nouvelle opération avant `opsgw recover <id>` (rollback défini par l'opération), jamais de ré-exécution automatique.

### 4.3 Catalogue initial (aucune opération activée à l'installation)
| Opération | Effets autorisés | Bornes explicites |
|---|---|---|
| `status` | lecture : état de la passerelle, derniers reçus | aucune écriture |
| `publishers.g2` (`plan`/`verify`/`apply`/`rollback`) | exécute le script G2 *par empreinte approuvée* | fichiers `crypto-publish-*` de `/etc/systemd/system`, dossier de sortie dédié, `daemon-reload` ; rien d'autre |
| `publishers.start-once` | `systemctl start <unité>` | unité ∈ {`crypto-publish-runtime-service.service`, `crypto-publish-storage.service`} |
| `api.presentation-paths` | pose du drop-in à deux variables + redémarrage de `crypto-operator-api.service` **seul** | fichier de drop-in unique et hachage fixé ; pas d'autre unité |
| `publishers.timers` (`enable`/`disable`) | activation/arrêt de timers | liste fermée de deux timers |
| `frontend.activate` / `frontend.rollback` | contrat #432 existant | service web seul, release précédente connue |
Chaque entrée porte : schéma de paramètres, liste fermée de fichiers et d'unités, verbes systemd permis, vérifications, rollback, délai, verrou. Toute capacité API ou systemd est **explicitement délimitée par opération** ; une opération n'étend jamais une autre.
**Exclus à jamais de ce périmètre** : Advisor (toute unité ou configuration), burn-in/epoch/PPL, secrets, `EnvironmentFile`, `.env`, FIN, trading/exchange, comptes, sudoers, configuration de Desktop Commander, réseau/pare-feu, avancée du checkout, paquets système, tout shell libre.

### 4.4 Deux étages d'approbation (recommandation : commencer par A)
- **A — approuver et exécuter dans le même geste** : `sudo opsgw approve <id>` affiche le détail, demande une confirmation tapée, puis exécute aussitôt. Pas de ticket stocké, pas de démon, pas de clé : le plus petit périmètre. Gain réel : plus de collage, vérification d'empreinte et journal systématiques, reçu lisible par `chatgpt-ro`.
- **B — approbation asynchrone par ticket signé** : `opsgw approve` signe (Ed25519, clé privée root `0600`, clé publique **épinglée** dans `/etc/opsgw`) un ticket à usage unique, expirant en ≤ 1 h ; l'exécution est déclenchée plus tard par l'opérateur ou par un déclencheur de chemin systemd. Ajoute la garde de clé, l'horloge de confiance, la révocation : à n'ouvrir qu'après A qualifié. La clé privée n'est jamais lisible par `chatgpt-ro` ni par `mathieu` (compte des services).

## 5. Éléments de confiance : propriétaires et pourquoi le demandeur ne peut pas les modifier
| Élément | Emplacement proposé | Propriétaire / mode |
|---|---|---|
| Code de la passerelle | `/opt/opsgw/` | root:root 0755 (fichiers 0644), empreinte consignée à l'installation |
| Catalogue et politique | `/etc/opsgw/catalog.json`, `policy.json` | root:root 0644 |
| Clé publique épinglée (étage B) | `/etc/opsgw/approver.pub` | root:root 0644 |
| Clé privée de l'approbation (étage B) | `/root/.opsgw/approver.key` | root:root 0600, jamais exportée |
| Registre d'usage unique | `/var/lib/opsgw/ledger.sqlite` | root:root 0600 |
| Garde des paquets | `/var/lib/opsgw/custody/` | root:root 0700 |
| Journal | `/var/lib/opsgw/journal/` | root:root 0600, ajout seul (`chattr +a` si le système de fichiers le permet, sinon dégradé et dit) |
| Verrou | `/run/opsgw.lock` | root |
| Reçus | `/srv/ops-workspace/receipts/` | root:root 0755, fichiers 0644 (lisibles par `chatgpt-ro`) |
Le **seul** emplacement que le demandeur écrit et que root lit est `requests/` (et `packages/`) : ce sont des données non fiables, traitées comme telles (§4.2 étape 2). Contrôles à relever en lecture seule avant installation : `id chatgpt-ro`, `sudo -l -U chatgpt-ro` (doit être vide), appartenance aux groupes `sudo`/`adm`/`docker`/`systemd-journal`. Limite à connaître : la compromission du compte administrateur qui approuve est hors de ce modèle de menace.

## 6. Tests de refus (spécification ; le code de test suit l'approbation du contrat étendu)
Chaque ligne est un test falsifiable, d'abord contre un faux système de fichiers, puis par `opsgw selftest` sur l'hôte (opérations à blanc seulement, aucune action réelle).
- **Identité et séparation** : `chatgpt-ro` ne peut pas écrire dans `/etc/opsgw`, `/opt/opsgw`, `/var/lib/opsgw`, le catalogue, la clé, le registre, le journal, `receipts/` ; ne peut pas lire la clé privée ; ne peut pas créer de ticket ; `sudo -l -U chatgpt-ro` vide ; `chatgpt-ro` absent des groupes privilégiés.
- **Demande** : clés en trop/manquantes, doublons de clé, JSON non fini, > 8 KiB, opération hors catalogue, paramètre hors schéma, chemin absolu ou `..`, nom d'unité hors liste, texte shell dans un champ, acteur ≠ `chatgpt-ro`, audience erronée, expiration passée / > 1 h / non entière.
- **Paquet et garde** : lien symbolique (fichier ou dossier), lien dur, fichier spécial, taille hors borne, propriétaire différent, **paquet modifié après la demande**, **paquet remplacé entre l'approbation et l'exécution**, empreinte racine différente, fichier absent du manifeste, fichier supplémentaire.
- **Ticket et approbation** : ticket rejoué, concurrent (deux processus, un seul passe), signature invalide, clé non épinglée, ticket pour une autre opération ou un autre paquet, ticket expiré, révoqué.
- **Exécution** : opération non activée, deux opérations simultanées (verrou), unité hors liste, verbe systemd hors liste, tentative d'Advisor/API hors opération prévue, commande à argument injecté, environnement hérité.
- **Pannes** : arrêt avant/pendant/après `STARTED`, avant le reçu, disque plein, échec d'une vérification post-opération, échec du rollback (jamais annoncé réussi), reprise `INTERRUPTED` exigeant `recover`, journal illisible.
- **Connecteur** : la passerelle n'ajoute aucune entrée à `blockedCommands`, n'en retire aucune, ne modifie pas `allowedDirectories` ; aucune commande bloquée n'est renommée pour passer.

## 7. Installation initiale par l'opérateur (non exécutée, étapes proposées)
0. **Lectures** : les contrôles du §5 ; confirmer l'absence de tout sudoers pour `chatgpt-ro`.
1. Créer les dossiers du §5 avec leurs modes (aucune donnée de burn-in, aucun secret).
2. Installer le code de la passerelle depuis une release du dépôt, vérifiée par empreinte, en `root:root`.
3. (Étage B seulement) Générer la paire de clés ; épingler la clé publique.
4. Installer le catalogue **vide** et la politique ; monter l'espace de préparation (§3).
5. Lancer `opsgw selftest` : la suite de refus du §6 doit réussir **avant** d'activer toute opération.
6. Activer `status`, vérifier un reçu ; puis seulement, par décision séparée, `publishers.g2`.
**Rollback de l'installation** : retirer `/opt/opsgw`, `/etc/opsgw`, `/var/lib/opsgw` (journal archivé avant), démonter l'espace. Aucune donnée du système n'est supprimée. Chaque étape est une demande d'autorisation distincte, avec preuve de sortie.

## 8. Autorisations, gates et limites
- **Gates** : reprendre G0..G5 du contrat #432 pour l'ensemble (propriétaire/racine, étage A qualifié, **admission du connecteur**, installation, première opération). Chacune demande une autorisation propre ; l'exception #286 doit être publiée.
- **Premier client** : les gates publishers G2→G5 (voir `PASSIVE_PUBLISHERS_G2_G5_PLAN.md`) ; elles restent exécutables à la main tant que cette mission n'est pas admise.
- **Limites** : un ticket signé ne prouve la garde de la clé que si elle est réellement hors de portée du demandeur (non prouvé) ; l'horloge et l'identité du pair restent à qualifier ; le journal « ajout seul » dépend du système de fichiers ; la protection contre une coupure de courant n'est pas qualifiée ; `blockedCommands` n'est pas une frontière ; aucune mesure de charge n'existe encore ; la télémétrie du connecteur est activée (décision de l'opérateur, non modifiée ici).
- **Décisions demandées à Mathieu** : (1) commencer par l'étage A ? (2) emplacement de l'espace de préparation et volume dédié ; (3) première opération à admettre (`publishers.g2` ?) ; (4) ouvrir une issue dédiée (texte ci-dessous) ou rattacher à #432 ; (5) révoquer l'appareil Desktop Commander hors ligne.

## Annexe — texte proposé pour l'issue
**PRIVILEGED-OPS-GATEWAY-01 — Accès d'écriture contrôlé pour `chatgpt-ro`.** Généralise #432. Deux périmètres : (1) espace de préparation dédié, sans privilège, hors du checkout gelé ; (2) passerelle d'opérations nommées avec paquet/empreinte approuvés, expiration, usage unique, verrou, journal et rollback, demandeur et autorisant séparés. Aucun shell libre, aucune commande arbitraire, aucun sudo général ; Advisor, burn-in, secrets, FIN et trading exclus ; aucune modification du connecteur ni contournement de ses restrictions. Plan : `docs/governance/PRIVILEGED_OPERATIONS_GATEWAY_01_PLAN.md`. Aucun changement de droits ni installation avant autorisation explicite par gate.
