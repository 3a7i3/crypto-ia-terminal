# D1-C — exécution isolée gouvernée (seconde revue #407)

Correctifs de la revue indépendante COMMENTED sur
`f18b4ba27f012193a2d0c25485429c384298c239` ; aucune approbation de merge,
déploiement ou exécution réelle n'est déduite. Méthode `D1_C_V2`.

## Sources et custody, distinctes des données

L'opérateur autorisé doit préparer **dans Research**, hors checkout runtime,
la racine `/var/lib/crypto-ai-research-audit/readonly_d1_c_source` contenant
exactement les trois sources de la révision revue :

- `stress_d1_isolated_runner.py` : lanceur autonome, bibliothèque standard ;
- `stress_d1_rejection_eligibility.py` : classificateur D1-C ;
- `stress_d1_snapshot_audit.py` : auditeur historique inchangé de #406.

Cette nouvelle custody source est une préparation gouvernée à vérifier, pas
une installation constatée sur le VPS. Aucun package `research_data`, fichier
`__init__.py`, installation pip, PYTHONPATH ou checkout production n'est requis.
Aucun sudo, copie depuis production, changement de droits ou staging distant
n'est exécuté par la présente mission. Si cette préparation n'est pas disponible
à `chatgpt-ro`, l'exécution reste bloquée ; ne pas contourner les permissions.

Les répertoires source et données doivent être réguliers, root-owned, sans
symlink ; ancêtres root-owned sans écriture groupe/autres ; racines et fichiers
sans aucun bit d'écriture. Le lanceur refuse toute autre racine source, même si
son nom ressemble à Research. Le code ne découvre aucun producteur ni runtime.
La racine de données reste explicitement `readonly_research_staging`, soumise
aux contrôles existants et au manifest historique épinglé.

## Empreintes revues et commande explicite

| Source | SHA-256 |
|---|---|
| Lanceur | `579bff90b9e2aa89885e4e64056f91c31233adf31942f344e2907cd8a36d4e25` |
| Classificateur V2 | `96f1f13e814190860adc69ccae2c868df6a0c3acd8b072b995ef1cd902224e47` |
| Auditeur historique | `11d3e13e90e04446f6d1fc5bff4840103fa4f23e2865a211e8b5f77771b94494` |

Avant exécution, la gate opérateur doit vérifier l'identité `chatgpt-ro`,
les permissions et les trois empreintes ci-dessus depuis le commit exact revu.
**Le lanceur est le point de confiance initial** : sa propre empreinte et sa
custody sont vérifiées extérieurement avant que Python l'exécute. Un hash fourni
par l'opérateur n'est pas une certification de revue ; utiliser celui publié
pour la révision revue, jamais celui calculé sur une source inconnue.

Commande depuis un répertoire quelconque, uniquement après cette gate :

```bash
python3 -I -B /var/lib/crypto-ai-research-audit/readonly_d1_c_source/stress_d1_isolated_runner.py \
  --source-root /var/lib/crypto-ai-research-audit/readonly_d1_c_source \
  --classifier-sha256 96f1f13e814190860adc69ccae2c868df6a0c3acd8b072b995ef1cd902224e47 \
  --research-root /var/lib/crypto-ai-research-audit/readonly_research_staging
```

Ne pas utiliser `-m research_data...` sans package en mode isolé. Le chemin de
script explicite préserve `-I` et `-B` ; le lanceur refuse leur absence avant
les imports de bibliothèque standard. Aucune extension de `sys.path` ni import
depuis un package applicatif n'intervient dans le chargement gouverné.

Le lanceur ouvre les deux sources avec O_RDONLY/O_NOFOLLOW, vérifie custody,
borne de taille, stabilité du fichier et SHA, puis compile **les mêmes bytes**
vérifiés. Les deux hashes sont contrôlés avant toute exécution de dépendance.
L'auditeur injecté est lié par identité d'objet ; son `__file__`, son origine
`__spec__.origin` et son empreinte, ainsi que ceux du classificateur, sont
recontrôlés avant la première lecture des composants de données. Un module
substitué, un chemin modifié ou un hash incohérent bloque la classification.
Le digest historique est fixe, sans option de remplacement. L'API package
sans cette provenance est non attestante pour les fixtures et l'audit public
échoue ; elle ne fournit pas de voie alternative d'exécution réelle.

Sortie JSON agrégée vers stdout uniquement ; exit 0 seulement pour
`D1_C_REAL_SUBSET_CLASSIFIED`, exit 2 pour refus d'intégrité. Enregistrer
explicitement le code final dans la preuve gouvernée ; une sortie partielle
ou une interrogation distante interrompue ne le confirme pas. Aucun fichier
dataset, source, cache bytecode ou runtime n'est écrit par la commande.

## Portée de la preuve et gate suivante

Les tests de chargement utilisent des sources copiées et des données synthétiques.
Un harness isolé neutralise seulement la custody OS pour un tempfile CI non-root ;
il conserve les hashes et le véritable chargeur et **n'appelle pas l'audit réel**.
Les contrôles de custody sont testés séparément, sans override exposé en CLI.
Aucun PASS synthétique ne certifie une installation distante ou un dataset.

`crypto-advisor-2` reste Offline au contrôle de cette révision :
`D1_C_REAL_BYTES_NOT_AVAILABLE`. Partition réelle D1-C `NOT_OBSERVED` ; aucune
réinterprétation des 4 186 packets historiques comme écritures perdues.
Prochaine gate : seconde revue indépendante de la source et de son lanceur,
puis contrôle compte/custody/empreintes et audit agrégé sur copie autorisée
lorsqu'elle devient effectivement accessible. Les limites de complétude
producteur, publication, prix, fsync et binding natif de l'epoch restent ouvertes.

`COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`
