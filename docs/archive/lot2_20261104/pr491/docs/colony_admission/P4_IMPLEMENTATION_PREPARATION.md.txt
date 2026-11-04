# P4 — préparation du contrôleur d'admission authentifiée
Statut : PREPARATION_ONLY / SOURCE_ONLY / LAB_TEST. Aucun contrôleur, record, enveloppe,
clé, individu, lancement ou déploiement n'est créé par ce document. #286 ACTIVE.

## 1. Base et preuves
Base vérifiée : main ef947cbf1ae183aa4d84561e14b51c5f4edfa1cf, tree
d2bfd364df69b383d5a4e377a538ca6e25e7aa25.
P2 #489 : fusion d96c646f ; P3 #490 : fusion ef947cbf.
Revue indépendante de la composition favorable ; 315 tests ciblés rejoués.
Ce résultat ne prouve ni un déploiement ni un contrôleur opérationnel.

Relevé CI main de cette préparation : 19 workflows, 15 terminés SUCCESS et 4 encore
en cours (coverage, test, coveralls-upload, codecov-upload), aucun échec.
Les 6 jobs de CI principale sont SUCCESS, dont TEST REGRESSION GATE, LINT REGRESSION
GATE, COVERAGE REGRESSION BASELINE et Walk-forward. Cross-stack et les preuves visuelles
sont SUCCESS. La CI globale ne peut pas encore être déclarée entièrement verte.
Aucune PR concurrente ouverte ne couvre colony_admission au relevé.

Autorités immuables :
- ADMISSION_CONTRACT.md : e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd ;
- SCENARIOS_A0.json : 4e518bfec6faaa582c2c42633d80e989b8204708b554f74b0eb1bbee6eaa59a1.
Ces deux fichiers sont vérifiés et ne sont pas modifiés ici. Ce plan organise leur
implémentation ; en cas d'écart, le contrat prime. Une ambiguïté normative est levée
par un nouveau document versionné et revu avant le code concerné, jamais par édition du pin.

## 2. Réutilisation et responsabilités
| Fonction | Primitive intégrée | Responsabilité restante de P4 |
|---|---|---|
| L1 et contrôle des limites | Registrar.exclusive, prepare, commit | Tenir L1 pendant chaque appel, journaliser les étapes |
| Plan figé | BirthPlan.data, BirthPlan.sha256 | Conserver le plan exact dans PREPARED, ne pas le remplacer au resume |
| Vérification sans consommer | trust.check_bundle | Dériver les items et la complétude globale, vérifier les statements |
| Consommation /1 | trust.consume | Lier le résultat à l'opération, persister les faults extérieurs |
| Admission d'ancêtre consommée | trust.verify_consumed | Vérifier aussi COMMITTED, record, enveloppe et confiance courante |
| Révocation | trust.classify_envelope | Distinguer decision/population et appliquer les états du contrat |
| Home et mémoire | Supervisor.admit | Vérifier les octets, les frontières de durabilité et la récupération |
| Quêtes et journal d'activité | J01, inchangé | Aucun nouveau moteur de quêtes, aucune mémoire héritée |

NOT_CONSUMED signifie absence de consommation nouvelle PAR CET APPEL ; ce n'est pas
une preuve d'enveloppe vierge. CONSUMED_BY_THIS_OPERATION n'est pas une acceptation.
DURABILITY_UNKNOWN ne permet aucune nouvelle tentative fondée seulement sur des octets lisibles.

## 3. Architecture proposée
Paquet futur colony_admission, importé par aucun worker, lab, pilote, trust ou registrar.
Le contrôleur est appelé par l'opérateur hors sandbox, sans binding de modèle ou réseau.

| Module futur | Responsabilité |
|---|---|
| io.py | Lectures bornées et strictes, fichiers réguliers privés, writes complets, fsync et faults |
| trust_policy.py | Chargement/installation monotone de la confiance extérieure sous L1 |
| attestations.py | Liste dérivée, statements, vérification et classification de population |
| oplog.py | Format fermé des lignes et projection pure de l'état ; aucune action dans le lecteur |
| controller.py | Orchestration D0–D4 et actions opérateur, sans cryptographie réimplémentée |
| recovery.py | recover, acknowledge, abandon, terminate et quarantaines explicites |
| __init__.py | Exports sans initialisation, fichiers ou processus à l'import |

Tests futurs sous tests/colony_admission. Le découpage en fichiers est un choix
d'implémentation ; il ne crée pas une nouvelle autorité.

La construction reçoit une racine LAB existante et un répertoire de confiance
extérieur à cette racine, au checkout et aux vues sandbox, ainsi qu'un emplacement
de fault log extérieur. Aucun chemin de contrôle ne vient d'un individu.
Le chargement ne transforme pas un fichier manquant en historique vide certifié.
Le harnais de test prépare explicitement ses racines privées et logs neufs.
Les créations d'infrastructure permises par le contrat sont distinguées d'une admission.

## 4. Composition correcte des attestations
Au premier appel, sous L1 :
1. Lire strictement les faults, la confiance courante et les opérations existantes.
2. Refuser un autre dossier ouvert et classifier toute la population.
3. Dériver les items depuis les records lus par le contrôleur ; dédupliquer par
   (kind, subject, record_sha256). Comparer l'ensemble présenté à l'ensemble attendu.
4. Vérifier les qualifications et statements : schéma fermé, portée, hashes,
   identité d'émetteur, absence de prétention de signature historique.
5. Vérifier les attestations durables et l'admission fraîche avec P2 ; vérifier
   séparément les admissions d'ancêtres déjà consommées et leur opération COMMITTED.
6. Préparer le BirthPlan sans écrire, puis figer l'ensemble exact dans PREPARED.

Ne pas envoyer les admissions d'ancêtres à consume : elles sont déjà consommées.
verify_consumed seul ne prouve ni signature, ni permission, ni complétude, ni COMMITTED.
P4 doit combiner ces preuves et effectuer la complétude globale AVANT toute consommation.
Une branche suspendue peut rester comptée sans autoriser une filiation.
Les références de preuves dans un statement ne sont pas des instructions d'ouverture
de fichier ou d'URL ; pas de déréférencement de chemins arbitraires ni de réseau.

## 5. Précondition technique à résoudre avant le code de récupération
P2 expose verify_consumed, mais ce verdict retourne CONSUMPTION_NOT_FOR_OPERATION
aussi bien pour absence, autre opération ou autre digest. LEDGER_CORRUPT signifie
impossibilité de conclure ; il ne peut pas devenir « aucune consommation ».

Pour recover(D1) et terminate, le contrôleur doit distinguer ces faits sans
réimplémenter le parseur du ledger ni utiliser une primitive d'écriture comme sonde.

Première tranche technique proposée : une inspection PUBLIQUE, strictement en lecture,
dans colony_trust, réutilisant son parseur et son verrou :
- absence vérifiée dans un ledger strictement valide ;
- entrée exacte pour cette opération ;
- entrée conflictuelle (digest, opération ou format legacy) ;
- indisponibilité/corruption, sans conclusion d'absence.
L'inspection compte aussi TOUTES les lignes portant operation_sha256 : zéro ou une
ligne seulement pour D1 ; une ligne étrangère ou plusieurs lignes donnent CONFLICT,
même si la paire issuer/envelope recherchée est absente. Un format legacy /0 n'est
jamais une preuve de liaison à l'opération.
Un ledger inexistant est rapporté séparément (LEDGER_MISSING), jamais comme un ledger
valide ne contenant aucune entrée. Le contrôleur distingue un état neuf initialisé
explicitement de la disparition d'un ledger exigé par une opération ; un ENOENT
quelconque ne démontre pas une autorisation vierge.
Elle ne crée ni fichier ni consommation et ne prétend pas prouver la durabilité
ou COMMITTED. Le contrat de cette interface et ses tests doivent être publiés
avant son code ; sa portée est limitée à ce besoin de P4.
Ce complément reste séparément reviewable : il n'est pas réputé livré par P2.

La conduite de terminate lorsque le ledger lui-même est illisible doit être
confrontée aux §7.2–7.3 du contrat avant implémentation. Si le contrat ne permet pas
de conclure, refuser et orienter vers la gate de restauration ; ne jamais libérer
une autorisation au motif que sa lecture a échoué. Toute précision normative
nécessaire est versionnée et soumise à revue avant le code, hors des pins P1.
Cette décision n'est pas une procédure automatique de restauration.

## 6. Orchestration et frontières
| Phase | Appel / effet | Preuve requise avant la suite |
|---|---|---|
| D0 | check complet + prepare ; PREPARED | Inputs, items, plan, pins, tentative et boot figés |
| D1 | BEGIN ; consume ; DONE | CONSUMED et succès de durabilité, ou reprise explicitement récupérée |
| D2 | BEGIN ; commit ADMISSION + enveloppes/statements ; DONE | Tous les fichiers attendus et namespaces durables |
| D3 | BEGIN ; commit HOME ; contrôles/fsync du contrôleur ; DONE | Home conforme, aucune erreur masquée |
| D4 | Confiance courante ; COMMITTED | Record lié à l'opération, résultat rejouable sans effet |

P3 prend step=ADMISSION ou HOME ; il ne remplace pas le journal de transaction.
Tous les effets et leurs erreurs doivent être identifiables par étape.
RegistrarError propre avant effet peut fermer BEGIN par BEGIN_CANCELLED ; un OSError
ou une erreur Supervisor n'est pas assimilé à ce refus préalable.
Une erreur write/fsync/close après effet garde l'incertitude et ne rembourse rien.
STOP reste non terminal ; une révocation applicable après consommation est terminale.
install_trust est sérialisé par le même L1 ; le pin historique ne masque pas la
confiance courante.

Un retry identique après COMMITTED renvoie le résultat établi. Une reprise ouverte
compare les inputs présentés avec les hashes figés, conserve le BirthPlan original,
recontrôle les éléments sous confiance courante et exclut seulement son propre home
des comptes. Aucun nouveau prepare ne remplace le plan figé.

## 7. Durabilité et limites à préserver
Le lecteur d'opération est pur et ne répare rien. Les formats fermés du journal,
du fault log et de la confiance, leur projection et leurs limites doivent être
définis explicitement avant d'écrire leurs producteurs.
Les réserves 57–64, 256 logs, les capacités de bundle et les limites d'enveloppes
viennent du contrat ; elles sont vérifiées avant les écritures correspondantes.

Une erreur fsync ne se résout pas par relecture ou second fsync du même fichier.
recover PRESENT/PARTIAL exige le boot différent prévu par le contrat ; le seam
de test ne doit pas être accessible à l'opérateur. Un seam ne démontre pas un reboot.
La quarantaine est explicite, journalisée, limitée à un home, sans suppression.
Le journal SQLite original n'est jamais ouvert pour le vérifier : copie indépendante.
Les notes de revue L1–L3 de P1 sont conservées dans leur lecture restrictive :
un répertoire fautif ne devient pas inscriptible par une opération de mise à l'écart,
et une étape de fault non déterminable ne devient pas D3 par supposition.

Les API Supervisor/Registrar directes restent un contournement avant T7.
P4 ne protège donc pas les runs ni ne rend toute admission du lab authentifiée.
Une preuve de sandbox ne remplace pas des comptes séparés et une gate d'exploitation.

## 8. Ordre de travail borné
Ces lots sont des commits ou tranches de revue de P4 ; ils ne sont pas des fins de mission
autonomes prétendant livrer le contrôleur complet.
1. Inspection read-only du ledger : contrat complémentaire, code, tests ; clarification
   de la limite terminate/ledger illisible si nécessaire.
2. Formats et projection pure : oplog/fault/confiance, transitions refusées et états inconnus.
3. Attestations : dérivation, bornes, statements, ancêtres COMMITTED, population.
4. Parcours nominal D0–D4 et idempotence, utilisant seulement les primitives admises.
5. Actions opérateur et récupération conservatrice, avec tests immédiats d'erreur.
6. Vérification d'isolation, revue adverse et dossier exact SHA/tree/CI.

Pas de parcours nominal publiable qui exposerait des actions de récupération permissives
ou non implémentées. Une PR intermédiaire décrit exactement ses API et ses limites.
P5 reste la campagne systématique SIGKILL/écritures et erreurs à toutes les frontières ;
P6 reste la qualification indépendante du contrôleur et de sa fermeture transitive.

## 9. Matrice de vérification
SCENARIOS_A0 contient 122 identifiants uniques :
54 marqués P4, 8 P2,P4, 1 P3,P4 et 2 transverses P2-P6, soit **65 scénarios impliquant P4**.
Ils restent des scénarios à implémenter, pas des tests réussis.
Les autres affectations P5/P6 ne sont pas silencieusement absorbées ou réputées acquises.

| Famille | Propriété P4 principale |
|---|---|
| AUTH / COMP / STORE | Identités, signatures, statements et complétude avant consommation |
| TX / OUT | Inputs figés, consommation propre non fraîche, effets et refus distingués |
| LOG / DUR | Lecture stricte, capacités, réserves, faults persistants et blocage |
| REV | Root actuelle monotone, révocation, aucune promotion depuis une signature historique |
| CONC / CEIL / STOP | L1, une opération ouverte, plafonds inchangés, arrêt extérieur |
| HOME / QUAR | Identité et état partiel sans réparation implicite |
| ISO / QUAL | Aucune importation inverse, aucun chemin de contrôle exposé, hashes inchangés |

Les tests P4 référencent les IDs A0 et vérifient des fichiers/verdicts observables.
Ils couvrent en particulier une admission de petit-enfant synthétique sans
reconsommation de celle du parent, et un dossier de durabilité inconnue qui ne
peut devenir une autorisation vierge.
Ne pas remplacer l'essai de sandbox réelle par un mock donnant VERIFIED.
Les skips du conteneur sont déclarés séparément d'un succès.

## 10. Definition of done et remise
- P4 applique les obligations de son contrat, avec les 65 scénarios qui l'impliquent
  tracés vers les tests ; P5/P6 restent distincts.
- SHA-256 P1 inchangés ; aucun code sous colony_lab, sentinel_activity ou colony_pilot modifié.
- Tripwires Sentinel/pilote inchangés ; nouvelle composition non qualifiée par ces tripwires.
- Régression ciblée, Ruff différentiel, CI finale et revue indépendante favorables.
- Dossier avec base/HEAD/tree, risques, limites, compatibilité des formats et rollback source.
- Aucune suppression de ledger/log ni restauration vers un état plus ancien au rollback.
- Aucun record, clé réelle, naissance, VPS, API de production ou runtime activé.

Prochaine action précise : fermer la précondition d'inspection du ledger de §5,
puis implémenter les formats et leur projection pure. Aucune permission nouvelle
de production n'est déduite de cette préparation.

