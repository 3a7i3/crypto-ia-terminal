# 3B — Acquisition unique et diagnostic local d’attestations

SOURCE_ONLY / LAB_ONLY / REVIEW_PENDING. Suite distincte du noyau privé #506,
fusionné en `146eae4e4b1f7feffd892a33c879a5df2c5c79b9`, tree
`d973dd864abdba41553715df3b7a9ac208c57141`. Sa CI propre est clôturée : 24 checks
et 19 workflows réussis. Cette livraison a ses propres revue et CI, non transférées.
Normes : [contrat 3B](P4_3B_ATTESTATIONS_AND_ANCESTRY_V0.md),
[plan §5](P4_3B_PLAN_AND_REUSE_V0.md), [P1 inchangé](ADMISSION_CONTRACT.md).

## API et acquisition

`colony_admission.attestation_observer.AttestationObserver(AttestationConfig(...)).scan_attestations()`
reçoit la configuration `ObserverConfig` existante et, facultativement, les bytes
et le pin canonique d’une politique registrar validée. Les deux champs optionnels
sont fournis ensemble. Leur validation précède toute lecture ; sinon g0 est acquis
au chemin checkout fixe, sous son pin existant. Aucun argument de méthode, liste
required fournie par un individu, écrivain ou commande d’action n’est ajouté.

Le propriétaire 3A est réutilisé via une extension interne distincte ; les trois
méthodes de FileObserver gardent leurs résultats et chemins par défaut. Une seule
acquisition prend L1, inventorie tous les logs/tentatives, impose les capacités
prévisibles, puis ouvre et inspecte le ledger une seule fois sous L2. Les mêmes
FD et bytes sont partagés avec les observations D1/D2/D3 et la preuve 3B.
Les branches sont découvertes par IDs vérifiés avec ensemble de visités et borne,
les records et enveloppes par chemins dérivés, jamais par les chemins d’un statement.
Les comparaisons privées existantes dérivent DECISION et réutilisent les validateurs
lineage/registrar/trust sans réimplémenter la cryptographie.

Le lecteur checkout a des permissions distinctes du lab : propriétaire courant,
pas d’écriture group/world, fichiers réguliers single-link, traversée NOFOLLOW.
Il inventorie les fermetures exactes, inclut les fichiers réguliers non Python,
refuse les noms sensibles et types irréguliers, et contrôle les caches sans en lire
le contenu. Artéfacts et fermetures partagent les plafonds checkout 32 MiB,
16 MiB/fichier, 4096 fichiers, 8192 entrées et le plafond commun 4096 FD.
Chaque path est acquis une seule fois ; inventaires, absences et métadonnées
FD/path sont revalidés. Une erreur de lecture, limite, instabilité ou fermeture
invalide intégralement opérations, stamps et snapshot : aucun préfixe n’est publié.

## Portée des faits

Les résultats et sous-objets sont immuables, sans dictionnaire/list mutable ni
bytes de records soumis dans les faits publics d’items. Les faits physiques et
le snapshot canonique de ledger restent explicitement des observations.
Les agrégats locaux distinguent PASS, contradiction FAIL et prérequis absent NE ;
FAIL domine NE. Les signatures, droits d’émetteur, révocations, statements,
exclusions locales, consommations et sources scientifiques restent distincts.
Un ledger incomplètement rapproché ne prouve pas NOT_CONSUMED pour une enveloppe.
Une tentative historique n’utilise jamais les fichiers actuels pour obtenir PASS.

Le profil R8/C9 est vérifié par bytes épinglés et fermeture complète courante.
Cela ne prouve ni signature historique de R8, ni fraîcheur/exécution de campagne,
ni provenance passée de verified_at_source_sha. PC2/p1 reste explicitement
SCIENTIFIC_PROFILE_UNSUPPORTED et scientifiquement bloquant, sans retirer p1 de g0.
Population, complétude globale, plafonds 3C, autorité, durabilité, rotation et reprise
restent NOT_EVALUATED ; accepted=false est permanent. #286 reste ACTIVE.
Un PASS local ne clôture pas l’étape 3 ni n’accorde de droit de filiation.

## Validation et intégration

Tests : fixtures privées temporaires LAB_TEST uniquement, clés publiques de test.
Couverture ajoutée : profil complet R8/C9 par acquisition réelle de copies temporaires,
PC2 non supporté, signatures altérées/révoquées, champs et rôles incohérents,
branches absentes/substituées, lecture ledger unique/ordre des verrous, déduplication,
limites privées/checkout, liens/permissions/noms sensibles/caches, modifications
entre lecture et restitution, erreurs de fermeture et isolement historique.
Les suites existantes assurent les régressions 3A et trust/registrar/lineage.
Les 75 cas contractuels restent des spécifications : les nombres de tests exécutés
et leur portée sont consignés séparément dans la PR, sans assimilation automatique.
Les suites normales et -O se recouvrent et ne s’additionnent pas.

Avant intégration : tests appropriés, revue indépendante du tree exact après toute
correction, CI exacte checks ET workflows, threads/règles, pins/hashes préservés,
composition avec main, puis merge avec expected_head_sha sans bypass. Clôture
uniquement après tree fusionné conforme et CI propre nouveau main complète.
Arrêt avant code 3C ; son plan nécessite validation séparée. Aucun VPS/runtime,
déploiement/systemd/PPL/FIN/epoch/production/TESTNET/LIVE/secret/Replay/Diagnostic,
campagne, naissance, installation ni écriture opérationnelle. Rollback source seul.
