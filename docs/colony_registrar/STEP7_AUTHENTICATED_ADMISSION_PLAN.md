# Étape 7 — checkpoint et admission authentifiée
Statut : SOURCE_ONLY / LAB_ONLY / DESIGN_FOR_REVIEW. #286 ACTIVE.
Relevé GitHub : 2026-10-23 UTC (22 octobre à Vancouver). Aucun accès VPS ni changement runtime.

## 1. Fusions et composition effectivement vérifiées
| PR | HEAD final | Fusion |
|---|---|---|
| [#485](https://github.com/3a7i3/crypto-ia-terminal/pull/485) | d0947f7d508556896fbc76899a83fa9e9d7853d5 | 6199885e5235fda8da8a3fc2510e7a42a848d7cf |
| [#486](https://github.com/3a7i3/crypto-ia-terminal/pull/486) | b1dbc475cc8f5552317bb6683d5b2bd54ae6451a | 7b4b2ef6fcdaab0ba9d3db81e2a2b28481a7a2ef |

Les API GitHub confirment les deux fusions. Le second HEAD a pour parents
5d3d38e916d1729f57f446d6f13fe822f982b365 et la fusion de #485, 6199885e.
Son delta depuis 5d3d38e9 contient uniquement les six fichiers de colony_trust,
son contrat et ses tests. Aucun delta entre ce HEAD et le tree de main
7b4b2ef6 : la composition finale est identique.

Vérification directe des check-runs, au HEAD exact de chaque PR :
25 SUCCESS, 2 SKIPPED, 0 pending/failure. Les skips sont Walk-forward validation
(ref main/master exigée) et publish-docs (workflow_dispatch ET main exigés).
Le journal de discussion décrit la revue indépendante et 881 tests locaux sur la
composition finale ; cette description reste une preuve rapportée, pas une revue
indépendante du code refaite dans ce checkpoint.

Au main 7b4b2ef6 : 19 workflows push, tous completed/success, 24 jobs
completed/success, aucune étape failure retournée. La liste contient moins de
100 runs ; chaque liste de jobs contient moins de 100 entrées.
Preuves : [runs main](https://github.com/3a7i3/crypto-ia-terminal/actions?query=branch%3Amain)
et [CI au commit vérifié](https://github.com/3a7i3/crypto-ia-terminal/actions/runs/39725781639).
Le relevé est ponctuel : revérifier main et le HEAD de toute nouvelle PR.

## 2. Rejeu indépendant local et limites
Python 3.12.14, venv temporaire, pytest 9.1.1.
Commande : python -m pytest -q tests/colony_trust tests/colony_registrar tests/colony_lab tests/colony_pilot

Résultat : **850 passed, 26 skipped, 5 failed** (881 collectés).
Les cinq variantes de test_verify_sandbox_requires_the_probe_to_see_exactly_its_view
échouent à socket.socket(AF_UNIX), PermissionError EPERM du conteneur, avant
le verdict de probe simulé. Les tests nécessitant les namespaces non privilégiés
sont ignorés lorsque l'hôte les refuse. Avertissement : plugin asyncio absent de
ce venv minimal. Aucun test ni code n'a été modifié pour contourner ces limites.
Cela ne constitue pas un PASS de campagne réelle sur cet hôte, ni la preuve
d'un défaut runtime. La CI main est vérifiée séparément ci-dessus.

## 3. Écart de composition restant
Les deux modules sont intégrés mais restent indépendants :
- colony_trust.verify_bundle authentifie les records et consomme les enveloppes
  BIRTH_ADMITTED quand le bundle est accepté ;
- colony_registrar.Registrar.birth valide les plafonds, la filiation et les
  déclarations, puis écrit admission et individu ;
- Supervisor ne force aucune de ces gates. Les qualifications historiques restent
  non authentifiées. Aucun record pilote ou petit-enfant réel n'est créé.

Appeler simplement verify_bundle puis birth n'est pas un protocole de transaction :
un crash après consommation peut interdire la reprise légitime ; inverser les
appels peut laisser un individu admis sans autorisation authentifiée consommée.
Les tests unitaires verts de chaque package ne prouvent pas leur composition.

## 4. Contrat proposé pour la prochaine tranche source
Aucune implémentation ni nouveau format n'est créé par ce document.
Le futur point d'entrée authentifié est appelé par l'opérateur, hors sandbox.
Il n'accepte que LAB_TEST ; pas de clés ou root réels, pas de naissance autonome.

### Autorité et bindings
Le contrôleur reçoit depuis l'extérieur du lab : root épinglée, version minimale,
lab_id et pin de politique admise. Aucun de ces paramètres ne vient d'une sortie
d'agent ou d'un chemin choisi par lui. Réutiliser les vérificateurs existants.
L'ensemble requis est dérivé des records exacts nécessaires à cette décision,
jamais fourni librement par l'individu :
- individu parent et les records d'ancêtres utilisés par le registrar ;
- qualifications effectivement nécessaires et admissions des ancêtres descendants ;
- décision d'admission de cet enfant, liée à sa spec, au parent, à la qualification,
  au budget, aux permissions, aux différences et au pin de politique.
Chaque attestation a son scope et son émetteur autorisé. Les listes sont bornées.
Une admission d'ancêtre déjà consommée n'est pas une nouvelle autorisation de
naissance : sa preuve de consommation/commit est vérifiée sans la consommer à nouveau.

Intégrité, authenticité, autorisation et complétude sont évaluées séparément.
Tout résultat autre que PASS refuse la décision. Les plafonds du registrar et
les exclusions de l'ensemble de la colonie restent applicables.
Aucune adoption automatique des anciens records sans enveloppe ; une nouvelle
attestation d'un ancien record doit déclarer sa portée présente.

### Reprise et anti-rejeu : prérequis d'implémentation
Publier une ADR avant le code, choisissant un propriétaire unique de la transaction
admission authentifiée et un ordre fixe des verrous. Le propriétaire sérialise
vérification de population, réservation, consommation et admission, avec une
frontière de commit documentée. Si nécessaire, faire évoluer les interfaces sous
contrat ; ne pas contourner le ledger ou ses refus par des fonctions privées.

Exigences de résultat :
1. Un bundle refusé ne crée ni admission ni individu ni consommation nouvelle.
2. Une autorisation consommée ne devient jamais réutilisable par rollback.
3. Un crash laisse un état explicite et récupérable, jamais un individu déclaré
   admis avec une authentification inconnue.
4. La reprise ne peut terminer QUE l'opération exacte déjà réservée ; tout
   changement de record/enveloppe/root/politique/permission est refusé.
5. Deux opérations concurrentes ne produisent qu'un commit et respectent tous
   les plafonds. Une admission terminée n'est pas exécutée une seconde fois.
6. Une écriture partielle, fsync refusé ou état de reprise altéré bloque sans
   réparation silencieuse. Les hypothèses de durabilité, permissions des
   répertoires et menace d'effacement du ledger sont publiées.

Une reprise d'opération n'est pas un nouveau succès d'authentification d'une
enveloppe consommée. Ne pas affirmer une atomicité multi-fichiers inexistante.
Le writer opérateur du code/root/état reste dans le modèle de confiance déclaré ;
la résistance à sa compromission n'est pas attestée.

### Enforcement et qualification
Le laboratoire existant reste une API de bas niveau non authentifiée tant que son
contrat ne change pas. Ne pas appeler la nouvelle gate « incontournable » avec un
simple wrapper. Définir les consommateurs et chemins autorisés, tester que les
workers ne peuvent accéder à aucun chemin d'admission.
Si Supervisor, workers, sandbox ou évaluateur changent, calculer les nouveaux hashes,
signaler les qualifications devenues obsolètes et requalifier explicitement.
Ne pas préserver artificiellement une ancienne qualification en masquant un delta.

## 5. Découpage et acceptation
- S7.1 (ce document) : checkpoint et contrat de composition à revoir.
- S7.2 : ADR transaction/recovery, schémas et scénarios préenregistrés, avant code.
- S7.3 : gate source LAB_TEST et essais de composition, sans modèle ni réseau.
- S7.4 : revue indépendante au HEAD final et qualification adaptée aux hashes.
- Les postes de métiers, le secrétariat et la messagerie restent ensuite des
  missions distinctes. AIC/clans/évolution demeurent différés.

Tests S7.3 attendus : parcours positif entièrement synthétique ; chaque record
absent/altéré/substitué ; mauvais issuer/scope/lab/root/pin ; révocation ;
ancienne qualification sans enveloppe ; ancêtre avec admission falsifiée ;
plafonds/concurrence/STOP ; crash avant/après chaque écriture durable et consommation ;
reprise identique et reprise divergente ; ledger tronqué/empoisonné ; aucun secret,
runtime, réseau ou credential réel ; refus d'appels depuis les workers.
Rendre les attentes observables et faire relire les frontières de transaction.

Aucune qualification, preuve runtime, installation, naissance réelle, fusion de cette
nouvelle tranche ou fin globale de l'étape 7 n'est déclarée par ce checkpoint.
#286 demeure ACTIVE ; références runtime/config/epoch inchangées.
