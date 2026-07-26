# CLAUDE_IMPLEMENTATION.md — Protocole d'implémentation permanent

**Statut :** normatif, permanent.
**Portée :** toute session Claude Code qui **exécute** un ticket du chantier `.claude/`.
**Autorité supérieure :** `CLAUDE.md` (racine) et `.claude/GOVERNANCE.md`. En cas de conflit,
`CLAUDE.md` > `GOVERNANCE.md` > ce document. Ce document ne crée aucune permission nouvelle :
il décrit **comment** exécuter ce qui est déjà autorisé ailleurs.

---

## 1. Objet, portée, mode d'invocation

### 1.1 Objet

Ce fichier est le contrat de travail hérité par toute session future. Il existe pour qu'une session
d'implémentation n'ait **jamais** besoin qu'on lui recolle un prompt géant de contexte : lire ce
document + le prompt du ticket suffit.

### 1.2 Portée

| Couvert par ce document | Non couvert |
|---|---|
| Séquence de travail d'un ticket | Le contenu métier des tickets (→ `.claude/prompts/`) |
| Commit, tests, rollback, déploiement | Les règles de gel et de gating (→ `GOVERNANCE.md`) |
| Format du rapport de fin de ticket | La priorisation des phases (→ `MASTER_ROADMAP.md`) |
| Règle d'arrêt | Le diagnostic technique du chantier (→ `ARCHITECTURE.md`) |

### 1.3 Mode d'invocation

Formulation canonique attendue de l'opérateur, et seule forme qui déclenche une implémentation :

```
Respecte .claude/CLAUDE_IMPLEMENTATION.md et exécute le ticket <ID>
```

Exemples : `... et exécute le ticket OBS-001`, `... et exécute le ticket GOV-002`.

Toute autre formulation (« corrige l'exposition », « répare le panneau », « fais le nécessaire »)
n'est **pas** une invocation de ticket : répondre en demandant l'ID du ticket, ou signaler qu'aucun
ticket ne couvre la demande. Ne jamais improviser un ticket implicite.

### 1.4 Correspondance ID → fichier de prompt

| Phase | Préfixe d'ID | Fichier de phase | Fichier de prompt |
|---|---|---|---|
| PHASE_00 | `GOV-nnn` | `.claude/phases/PHASE_00.md` | `.claude/prompts/PROMPT_GOV_nnn.md` |
| PHASE_01 | `OBS-nnn` | `.claude/phases/PHASE_01.md` | `.claude/prompts/PROMPT_OBS_nnn.md` |
| PHASE_02 | `SSOT-nnn` | `.claude/phases/PHASE_02_GATED.md` | `.claude/prompts/PROMPT_SSOT_nnn.md` |
| PHASE_03 | `REST-nnn` | `.claude/phases/PHASE_03.md` | `.claude/prompts/PROMPT_REST_nnn.md` |
| PHASE_04 | `PORT-nnn` | `.claude/phases/PHASE_04_GATED.md` | `.claude/prompts/PROMPT_PORT_nnn.md` |

Règle de nommage : l'ID passe en `MAJUSCULES_AVEC_UNDERSCORES` (`OBS-001` → `PROMPT_OBS_001.md`).
Un ID dont le préfixe est `SSOT-` ou `PORT-` appartient à une phase **GATED** : voir §4.3.

---

## 2. Séquence de travail obligatoire

Les 8 étapes s'exécutent **dans cet ordre**, sans saut, sans parallélisation.

### Étape 1 — Lire `.claude/GOVERNANCE.md`

Intégralement, à chaque session, même si « déjà lu ». En sortir : les 4 invariants (§2), la règle de
gating (§6), les interdictions INT-01→INT-20 (§7), l'autorité de décision (§8).

### Étape 2 — Lire `.claude/MASTER_ROADMAP.md`

Vérifier que le ticket demandé appartient à une phase **ouverte** et que ses **dépendances déclarées
sont satisfaites**. Un ticket dont une dépendance n'est pas close ne s'exécute pas : arrêt + rapport.

### Étape 3 — Lire `.claude/IMPLEMENTATION_QUEUE.md`

Vérifier que le ticket est en tête de file ou explicitement désigné par l'opérateur, et que son
statut n'est ni `FAIT`, ni `GATED`, ni `BLOQUÉ`. Si un ticket antérieur est `EN COURS`, arrêt : la
file est censée n'avoir qu'un ticket actif (§3).

### Étape 4 — Lire le prompt du ticket dans `.claude/prompts/`

C'est la spécification **contraignante** : périmètre, fichiers autorisés, critères d'acceptation,
tests exigés. Ce qui n'y figure pas n'est pas dans le périmètre. Si le fichier de prompt est absent
ou incomplet : arrêt + rapport, **ne pas reconstituer le ticket de mémoire**.

### Étape 5 — Exécuter

Modifier uniquement les fichiers listés dans le prompt. Limites d'atomicité INT-16 : **≤ 300 lignes
modifiées OU ≤ 4 fichiers**, la contrainte la plus stricte s'appliquant. Si l'exécution réelle
dépasse la limite, **arrêt** : le ticket doit être scindé par un tour de gouvernance, pas élargi en
cours de route.

### Étape 6 — Tester

Selon §6 : test rouge d'abord, puis suite de non-régression décision, puis suites impactées.
Un test rouge qui ne devient pas vert ⇒ le ticket n'est pas fini ⇒ pas de commit.

### Étape 7 — Commiter

Un ticket = **un** commit atomique, format §5. Pas de commit partiel, pas de commit « wip » laissé
dans l'historique, pas de `git push` sauf demande explicite de l'opérateur.

### Étape 8 — Mettre à jour `.claude/IMPLEMENTATION_QUEUE.md`

Passer le ticket à `FAIT`, avec : SHA du commit, date UTC, nombre de fichiers et de lignes modifiés,
résultat des tests. Cette mise à jour fait partie du commit du ticket **ou** d'un commit `chore`
immédiatement consécutif — jamais oubliée.

### Étape 9 — S'ARRÊTER

Produire le rapport de fin de ticket (§9) et **rendre la main**. Aucun travail supplémentaire, aucune
« amélioration tant qu'on y est », aucun ticket suivant.

---

## 3. Un seul ticket à la fois

1. Une session exécute **un** ticket. Pas deux, pas « les deux petits d'un coup ».
2. L'arrêt après l'étape 9 est **obligatoire**, y compris si le ticket suivant est trivial, déjà
   spécifié, sans risque, ou explicitement dépendant.
3. L'enchaînement automatique est interdit. Le ticket suivant exige une **nouvelle invocation**
   explicite de l'opérateur (§1.3).
4. Si, pendant l'exécution, un défaut hors périmètre est constaté : il est **signalé** dans le
   rapport (§9, catégorie Observation), jamais corrigé dans le même commit.
5. Si le ticket s'avère infaisable tel que spécifié : arrêt, rapport, aucune réécriture unilatérale
   de la spécification.

**Raison d'être :** l'atomicité est la condition du rollback individuel (§7) et de l'imputabilité
d'une régression à un changement unique. Deux tickets dans un commit détruisent les deux propriétés.

---

## 4. Les 4 invariants et le test de gating

### 4.1 Rappel normatif (source : `GOVERNANCE.md` §2)

| Invariant | Énoncé | Vérification sur le diff | Falsificateur |
|---|---|---|---|
| **INV-1** | Passivité (ADR-0007) : aucune valeur d'observabilité ne remonte vers une couche décisionnelle. L'affichage consomme, il ne produit jamais d'entrée de décision. | Aucun symbole modifié n'est situé en amont d'une décision (`check_new_trade`, sizing, risk gate, `PortfolioBrain` en entrée de décision). | Un symbole modifié est lu par le pipeline de décision ⇒ INV-1 violé. |
| **INV-2** | Aucun reset de N sans ADR d'époque signé par l'opérateur. | Le ticket déclare `RESET D'ÉPOQUE : NON` et le justifie, ou il est marqué `GATED`. | À entrée de marché identique, le comportement de décision diffère avant/après ⇒ reset implicite ⇒ INV-2 violé. |
| **INV-3** | `databases/paper_trades.jsonl` intact : `paper_trading/mexc_simulator.py` et `paper_trading/recorder.py` sont les seuls écrivains. | Aucune écriture vers ce fichier hors de ces deux modules. | Un nouveau chemin d'écriture, même en append, même en test ⇒ INV-3 violé. |
| **INV-4** | Sizing épinglé à `WALLET_PAPER_CAPITAL`. | Aucune grandeur corrigée par le chantier d'affichage (`paper_equity`, `free_cash`, `capital` recalculé) n'alimente le sizing. | La taille d'un ordre change après le patch ⇒ INV-4 violé. |

Un ticket qui viole **un seul** invariant est irrecevable, quelle que soit sa valeur technique.
Le contrôle des 4 invariants est **explicite** dans le message de commit (§5.2) et dans le rapport
(§9). L'absence de contrôle vaut violation.

### 4.2 Test opérationnel de gating (source : `GOVERNANCE.md` §6.1)

> **« Ce changement modifie-t-il ce que LIT le moteur de décision ? »**

| Réponse | Classement |
|---|---|
| NON | **Exécutable** sous le gel, si les 4 invariants et les interdictions INT-01→INT-20 sont respectés. |
| OUI | **`GATED`** — non exécutable. |
| INCERTAIN | Traité comme **OUI**. Le doute est gaté par défaut (règle du maillon faible). |

Test dérivé, quand la lecture du code ne tranche pas :

> « À entrée de marché identique, la décision produite après le patch peut-elle différer de la
> décision produite avant ? » — Si oui : `GATED`.

Ce test s'applique **au diff réellement écrit**, pas à l'intention du ticket. Un ticket classé non
gaté à la rédaction qui devient gaté à l'écriture ⇒ arrêt immédiat, rollback du travail non commité,
rapport.

### 4.3 Conduite face à un ticket `GATED`

Un ticket portant la bannière `GATED / RESET D'ÉPOQUE / N -> 0 / ADR OBLIGATOIRE` **ne s'exécute
pas**, même si l'opérateur le demande par la formulation §1.3, tant que les trois préconditions ne
sont pas **toutes** satisfaites et vérifiables :

1. Checkpoint L2 franchi ;
2. N ≥ 100 atteint sur l'époque courante (mesuré sur `CLEAN_DATA_SINCE_ACTIVE`) ;
3. ADR d'époque (numéro ≥ 0019) **signé par l'opérateur**, statut `Accepté`.

Conduite : répondre en citant la bannière, les préconditions manquantes et l'état mesuré. Ne pas
« préparer en attendant », ne pas produire un patch partiel, ne pas créer de branche d'anticipation.

**Cas gelé volontairement (rappel `GOVERNANCE.md` §6.4) :** `pos_manager` reste la source des
contraintes de décision. Corriger son alimentation est `GATED`, sans discussion, quelle que soit
l'évidence du bug. Le chantier d'affichage ne le touche jamais.

---

## 5. Politique de commit

### 5.1 Règles

1. **Un ticket = un commit.** Revertable individuellement (§7).
2. Le commit contient le code + les tests du ticket. Rien d'autre.
3. **Interdit** : refactor opportuniste, renommage de confort, réindentation de fichiers non touchés
   par le ticket, optimisation non demandée, mise à jour de dépendance, nettoyage de code mort
   adjacent, correction d'un bug voisin.
4. **Interdit** : tout changement de comportement hors du périmètre décrit dans le prompt du ticket.
5. Si l'on ne peut pas satisfaire le ticket sans sortir du périmètre : **arrêt + rapport**.
6. `git push` uniquement sur demande explicite. Le commit local suffit à clore l'étape 7.
7. Branche : travailler sur `main` est admis pour un ticket non gaté et atomique ; si l'opérateur
   demande une branche, la nommer `ticket/<id-en-minuscules>` (ex. `ticket/obs-001`).
8. Jamais de `--no-verify`, jamais de contournement de hook. Le hook `post-commit` de déploiement est
   aboli (`post-commit.disabled`) et ne doit **jamais** être réactivé (INT-13).

### 5.2 Format exact du message de commit

```
<type>(<ID>): <résumé impératif, ≤ 72 caractères, sans point final>

Phase          : <PHASE_00 | PHASE_01 | PHASE_02_GATED | PHASE_03 | PHASE_04_GATED>
Ticket         : <ID>  (prompt : .claude/prompts/PROMPT_<ID>.md)
Portée         : <fichiers modifiés, séparés par des virgules>
Volume         : <n> fichiers / <n> lignes modifiées   (limite INT-16 : 4 fichiers OU 300 lignes)
Gating         : NON GATÉ — <réponse au test §4.2 en une phrase>
Reset d'époque : NON
Invariants     : INV-1 OK | INV-2 OK | INV-3 OK | INV-4 OK
Tests          : <commande exécutée> -> <n> passés, <n> échoués, <n> ignorés
Hors périmètre : <constats signalés mais NON corrigés, ou "aucun">

Co-Authored-By: Claude <noreply@anthropic.com>
```

Types autorisés sous le gel :

| Type | Usage | Remarque |
|---|---|---|
| `fix` | correction d'un défaut d'affichage / de mesure / d'audit | usage majoritaire du chantier |
| `test` | ajout ou durcissement de tests seuls | aucun code de production modifié |
| `docs` | documentation, ADR au statut `Proposé`, fichiers `.claude/` | jamais de code |
| `chore` | mise à jour de la file, métadonnées, outillage non décisionnel | |
| `feat` | **uniquement** outil de mesure / d'audit / de visualisation passif | doit citer l'hypothèse ou le besoin de validation qui le justifie (Scientific Debt Rule) |

Types **interdits** : tout ce qui introduirait une couche décisionnelle, un indicateur, une
stratégie, une règle de filtrage, ou une modification de seuil (INT-01→INT-04).

### 5.3 Vérification avant commit

Avant `git commit`, contrôler explicitement, dans cet ordre :

1. `git status` — aucun fichier hors périmètre en `staged` (en particulier : `.env`, `databases/`,
   `runtime_config.json`, secrets, artefacts locaux).
2. `git diff --cached --stat` — volume conforme à INT-16.
3. Relecture du diff complet — aucun changement non demandé.
4. Les 4 invariants, un par un, avec leur falsificateur (§4.1).

---

## 6. Politique de tests

### 6.1 Test rouge d'abord (obligatoire)

1. Écrire **d'abord** le test qui reproduit le défaut visé par le ticket, et **constater qu'il
   échoue** sur le code non patché. Consigner la sortie d'échec (message + assertion).
2. Puis seulement écrire le correctif, jusqu'à ce que ce test passe.
3. Un ticket dont le test n'a jamais été rouge n'a **rien démontré** : il est réputé non testé.
   La sortie rouge, puis verte, est un livrable du rapport (§9).
4. Un ticket `docs`/`chore` est dispensé de test rouge, et le déclare explicitement.

### 6.2 Non-régression sur le verdict de décision (obligatoire)

Tout ticket touchant le code de production doit démontrer que **la décision produite est inchangée**.
C'est la vérification opérationnelle d'INV-1 et INV-2.

Procédure :

1. **Avant** le patch : exécuter la suite de non-régression décision, conserver le résultat brut
   (compte de passés/échoués + liste des échecs préexistants s'il y en a).
2. **Après** le patch : réexécuter la même sélection, à l'identique.
3. **Critère d'acceptation :** résultat strictement identique. Le moindre écart (un test qui passe de
   vert à rouge, mais aussi de rouge à vert sans raison liée au ticket) ⇒ arrêt, pas de commit,
   rapport.

Sélection de la suite de non-régression décision : le périmètre exact (chemins de tests couvrant
`check_new_trade`, le sizing, le risk gate, `PortfolioBrain` en entrée de décision) est
**À CONFIRMER AU DÉMARRAGE DU TICKET** — il est établi une fois, listé dans le prompt du ticket, et
réutilisé tel quel. Ne pas l'improviser à chaque session, ne pas le réduire pour aller plus vite.

### 6.3 Commandes exactes

Le fichier `pytest.ini` (racine) impose déjà `-v --tb=short --strict-markers`, le `pythonpath` et
`asyncio_mode = auto`. **Ne pas les redéclarer** en ligne de commande.

Depuis `C:/Users/WINDOWS/crypto_ai_terminal` :

```
# 1. Test rouge du ticket (avant patch, doit ÉCHOUER)
python -m pytest <chemin_du_test_du_ticket> -x

# 2. Non-régression décision (avant patch, puis après patch — sortie identique exigée)
python -m pytest <selection_non_regression_decision>

# 3. Suites impactées par le ticket (après patch)
python -m pytest <chemins_listes_dans_le_prompt>

# 4. Suites de référence du chantier d'affichage, quand le ticket les touche
python -m pytest tests/test_system_snapshot.py tests/test_state_integrity.py
python -m pytest tests/capital_deployment/test_capital_lines.py
python -m pytest tests/visualization/test_snapshot_only_loaders.py
```

Règles d'exécution :

- Les tests marqués `slow` ne sont pas exécutés par défaut (`-m slow` pour les inclure) ; ne les
  activer que si le prompt du ticket le demande.
- Les marqueurs `integration` et `e2e` supposent un service local : ne pas les lancer sans consigne,
  et ne jamais conclure d'un `ERROR` de connexion qu'un test « passe ».
- Reporter les résultats **bruts** (nombres exacts). Aucun arrondi, aucun « tout est vert » non chiffré.
- Ne jamais exécuter la suite complète du dépôt pour « faire bonne mesure » si le prompt ne le demande
  pas : le bruit d'échecs préexistants rend le verdict illisible.

### 6.4 Échec d'un test étranger au ticket

Conduite **stricte**, dans cet ordre :

1. **Ne pas le corriger.** Un test étranger réparé dans le commit du ticket casse l'atomicité et
   masque potentiellement une régression.
2. Déterminer s'il était **déjà rouge avant** le patch (c'est l'intérêt de la capture §6.2 étape 1) :
   - **Déjà rouge avant** ⇒ échec préexistant. Le consigner dans le rapport (Observation), poursuivre
     le ticket, le mentionner dans le champ `Hors périmètre` du commit.
   - **Vert avant, rouge après** ⇒ **régression causée par le ticket**. Arrêt immédiat. Pas de commit.
     Rapport. Le ticket est réputé en échec tant que la cause n'est pas comprise.
   - **Indéterminé** (pas de capture avant) ⇒ traiter comme régression (maillon faible).
3. Ne jamais neutraliser un test (`skip`, `xfail`, suppression, assouplissement d'assertion) pour
   faire passer un ticket. C'est une falsification du résultat.

---

## 7. Politique de rollback

### 7.1 Principe

Chaque ticket est revertable **individuellement**, sans effet de bord sur les tickets voisins.
C'est la contrepartie de l'atomicité (§3, INT-16).

### 7.2 Procédure — commit non déployé

```
git log --oneline -n 10                 # identifier le SHA du commit du ticket
git revert <sha>                        # crée un commit inverse, conserve l'historique
python -m pytest <selection_non_regression_decision>   # revérifier après revert
```

Puis remettre le ticket à `À FAIRE` (ou `BLOQUÉ`, motif indiqué) dans `IMPLEMENTATION_QUEUE.md`.

### 7.3 Interdits de rollback

- `git reset --hard` sur un commit déjà partagé, `git push --force`, réécriture d'historique : **non**.
- Suppression manuelle du code « pour revenir en arrière » sans commit de revert : **non** (perte de
  traçabilité).
- Revert « partiel » à la main : **non**. Si le revert est trop large, c'est que le ticket n'était pas
  atomique — le constater dans le rapport plutôt que le contourner.

### 7.4 Procédure — commit déjà déployé sur le VPS

1. `git revert <sha>` en local, tests §6.2 revérifiés.
2. Déploiement délibéré du revert (§8), avec la même exigence de confirmation opérateur.
3. Vérification post-déploiement complète (§8.3) : le revert n'est acquis qu'après vérification de
   l'état réel du VPS, jamais sur un code retour (INT-15).
4. Redémarrage du service **uniquement** si l'opérateur l'autorise explicitement (double opt-in,
   INT-14) et en sachant qu'un restart a un coût opérationnel documenté.

---

## 8. Politique de déploiement

### 8.1 Rien n'est automatique

Le déploiement est un **geste délibéré de l'opérateur** (INT-13). Le hook `post-commit` est aboli.
Un commit ne déploie jamais. L'agent ne déclenche jamais un déploiement de sa propre initiative, y
compris quand le ticket est « manifestement urgent ».

### 8.2 Commandes

```
bash scripts/deploy_vps.sh --confirm             # avec confirmation interactive
bash scripts/deploy_vps.sh --confirm --yes       # usage scripté, sans prompt
bash scripts/deploy_vps.sh --confirm --dry-run   # simulation, aucun transfert réel
bash scripts/deploy_vps.sh --confirm --restart   # + redémarrage du service (double opt-in)
```

- Sans `--confirm` : usage affiché, `exit 1`. Aucune exécution implicite.
- `--restart` exige **en plus** que `VPS_RESTART_CMD` soit défini dans `.env` (INT-14).
- Le filtre d'exclusion (`databases/|cache/|logs/|tests/|docs/`) protège l'état runtime du VPS,
  dont `runtime_config.json`. Ne jamais le contourner.
- Un tag annoté `deploy-YYYYMMDD-HHMM` est créé **après** un déploiement réussi, jamais en
  `--dry-run`. `git tag -l "deploy-*"` est le journal d'audit des déploiements.
- Cible : VPS **35.240.166.72** (l'ancienne adresse 34.171.188.99 est morte — ne jamais la réutiliser).

### 8.3 Vérification post-déploiement (obligatoire, jamais facultative)

Un déploiement n'est **jamais** conclu sur la base d'un code retour (INT-15, leçon de l'incident
`ssh` sans `-n` du 2026-07-08 : trois tags d'audit créés sur de faux succès, 55/80 fichiers jamais
transférés). Trois preuves d'état réel sont exigées :

1. **SHA local = SHA VPS** — comparer le hash des fichiers effectivement transférés, fichier par
   fichier pour les fichiers critiques du ticket. Un `git log` local ne prouve rien sur le VPS.
2. **Service actif** — `crypto-advisor` / `crypto-watchdog` : vérifier le processus réellement en vie
   et la date de démarrage (un service « actif » qui n'a pas redémarré n'a pas chargé le patch).
3. **Panneau cohérent** — vérifier sur la sortie réelle (panneau Telegram / snapshot) que la grandeur
   corrigée par le ticket affiche la valeur attendue, et qu'aucune autre grandeur n'a bougé.

Pièges consignés, à ne pas rejouer :

- `databases/*.jsonl` **local** n'est jamais l'état du VPS (fichier gitignoré, souvent vide ou
  périmé) — INT-19.
- Chercher `CRITICAL` dans les logs remonte aussi des messages `INFO` dont le **contenu** contient ce
  mot : filtrer sur la sévérité, pas sur le texte.
- Un tag `deploy-*` n'est une preuve que si la vérification §8.3 a réellement été faite.

### 8.4 Règle d'arrêt en opération

À la **première anomalie** pendant une opération à risque (déploiement, restart, manipulation
d'état) : arrêt immédiat, rapport à l'opérateur, revérification avant toute conclusion. Ne jamais
poursuivre « pour voir ».

---

## 9. Format du rapport de fin de ticket

Le rapport est produit **après** l'étape 8 et **avant** l'arrêt. Il applique le protocole d'audit
épistémique v3 (`docs/protocole_audit_epistemique.md`) : **une phrase = une catégorie**.

### 9.1 En-tête factuel

```
TICKET        : <ID> — <titre>
PHASE         : <fichier de phase>
COMMIT        : <sha court> — <type>(<ID>): <résumé>
FICHIERS      : <n> (<liste>)
LIGNES        : <n> modifiées   (limite INT-16 respectée : OUI/NON)
GATING        : NON GATÉ — <réponse au test §4.2>
RESET D'ÉPOQUE: NON
INVARIANTS    : INV-1 <OK/violé> | INV-2 <…> | INV-3 <…> | INV-4 <…>
TEST ROUGE    : <chemin> — rouge avant : <extrait d'échec> / vert après : OUI
NON-RÉGRESSION: <commande> — avant <n> passés/<n> échoués ; après <n>/<n> — identique : OUI/NON
DÉPLOIEMENT   : NON (par défaut) | OUI — tag <deploy-…>, vérifications §8.3 : <résultat>
```

### 9.2 Corps épistémique

Séparer strictement les quatre catégories. Ne pas remplir une catégorie pour la forme (règle de
proportionnalité §6 du protocole) : trois observations utiles valent mieux que dix cases cochées.

```
OBSERVATION  O#
  Énoncé          : <fait lu, avec source précise : fichier:ligne, sortie de test, log>
  Source          : inspection directe | échantillon | log | doc | mémoire | état mutable
  Couverture      : complète | partielle | inconnue
  Échantillon/Pop : <observé> / <cible ou "inconnue">
  Représentativité: dérivée | NON ÉVALUABLE
  Biais           : <nom> -> gonfle | réduit l'inférence

INFÉRENCE  I#
  Énoncé      : <ce qu'on en déduit>
  Confiance   : certain … faux  (≤ maillon faible ; ≤ composition ; ≤ représentativité ;
                                 état mutable ⇒ ≤ très probable)
  Portée      : <ce que l'énoncé NE couvre PAS>
  Supports    : [O#, …]   Dépend de : [I#, …]
  Sapé/Réfuté : [O#, …]
  Falsif. log.: <ce qui, observé, réfuterait cette inférence>

HYPOTHÈSE  H#
  Énoncé      :   Confiance :   Source plaus. :
  Falsif. exp.: <expérience qui trancherait>

DÉCISION  D#
  Énoncé      : <recommandation ; jamais exécutée par l'agent si elle relève de l'opérateur>
  Autorité    : opérateur | agent (dans les limites §8.2 GOVERNANCE)
  Dépend de   : [I#, H#, …]
  Prémisse c/v: <la prémisse contestable, énoncée>

NON OBSERVÉ  N#
  Dette       : critique | majeure | mineure | nulle POUR <décision>
  Bloque      : D#
```

### 9.3 Exigences non négociables du rapport

1. **Portée bornée** : toute inférence indique ce qu'elle ne couvre pas (« sur le chemin d'exécution
   inspecté », « sur l'époque V4 », « sur les imports statiques »). Une inférence sans portée est
   réputée surétendue.
2. **Double falsificateur** : au moins un falsificateur logique (inférence) **et** un falsificateur
   expérimental (hypothèse) sont énoncés.
3. **Maillon faible** : la confiance d'une conclusion ne dépasse jamais celle de son support le plus
   faible ; un nœud conjonctif vaut au plus son minimum.
4. **Principe de symétrie** : appliquer aux conclusions favorables au ticket la même sévérité qu'aux
   conclusions défavorables. Un ticket « réussi » se rapporte avec les mêmes exigences de preuve.
5. **Dette épistémique** : ce qui n'a pas été observé est déclaré (`NON OBSERVÉ`), rattaché à la
   décision qu'il bloque. « Non vérifié » ne se dit jamais « probablement bon ».
6. **Filtre lexical** : pas de superlatif, pas de « tout / toujours / jamais » non mesuré, pas de
   « complètement corrigé » sans le chiffre qui l'établit.
7. **Aucun fait inventé** : information manquante ⇒ écrire **« À CONFIRMER AU DÉMARRAGE DU TICKET »**
   (INT-18).

---

## 10. Ce que ce document N'AUTORISE PAS

Liste explicite, numérotée, opposable. Aucune de ces actions ne devient permise du fait qu'une
session « respecte `CLAUDE_IMPLEMENTATION.md` ».

1. **N'autorise pas** à exécuter un ticket `GATED` (`SSOT-*`, `PORT-*`, ou tout ticket portant la
   bannière), même sur demande, tant que les trois préconditions §4.3 ne sont pas toutes vérifiées.
2. **N'autorise pas** à modifier `PositionManager`, son alimentation, `check_new_trade`, le sizing,
   le risk gate, ou `PortfolioBrain` **en entrée de décision** (INT-06, `GOVERNANCE.md` §6.3/§6.4).
3. **N'autorise pas** à provoquer un reset d'époque, même indirect, même « propre » : la procédure
   complète `GOVERNANCE.md` §4.5 et un ADR signé sont requis (INT-12).
4. **N'autorise pas** à déplacer `CLEAN_DATA_SINCE`, ni à recopier la borne hors de
   `scripts/data_quality.py` (INT-10).
5. **N'autorise pas** à modifier un seuil de décision, y compris « temporairement » ou « pour
   tester » (INT-04), ni à activer `FEATURE_AUTO_CALIBRATION` ou l'ACE (INT-08).
6. **N'autorise pas** à ajouter une couche décisionnelle, un indicateur, une stratégie, une
   personnalité ou une règle de filtrage (INT-01→INT-03).
7. **N'autorise pas** à ajouter un écrivain de `paper_trades.jsonl`, ni à le réécrire, filtrer,
   réordonner ou migrer (INT-09, INV-3).
8. **N'autorise pas** à déployer, ni à redémarrer un service : ce sont des décisions opérateur
   exclusives, avec confirmation explicite et double opt-in pour le restart (INT-13, INT-14).
9. **N'autorise pas** à enchaîner deux tickets dans une même session, ni à « avancer un peu » sur le
   suivant (§3).
10. **N'autorise pas** un refactor opportuniste, un renommage de confort, une optimisation non
    demandée, ni un changement de comportement hors du périmètre du prompt (§5.1).
11. **N'autorise pas** à corriger un test étranger au ticket, ni à le neutraliser (`skip`, `xfail`,
    suppression, assouplissement d'assertion) pour faire passer un ticket (§6.4).
12. **N'autorise pas** à dépasser les limites d'atomicité (4 fichiers OU 300 lignes) en élargissant
    le ticket en cours de route (INT-16).
13. **N'autorise pas** à signer un ADR, ni à faire passer un ADR de `Proposé` à `Accepté` : seule
    l'opérateur le fait (`GOVERNANCE.md` §8.1).
14. **N'autorise pas** à modifier `CLAUDE.md`, `.claude/GOVERNANCE.md`, `.claude/MASTER_ROADMAP.md`
    ou les fichiers de phase de sa propre initiative : ces documents changent par décision opérateur,
    via un ticket dédié.
15. **N'autorise pas** à modifier la configuration de l'agent, les permissions
    (`.claude/settings*.json`), ni à réactiver le hook `post-commit`.
16. **N'autorise pas** à manipuler des valeurs de clés API, de secrets, ou le contenu de `.env`.
17. **N'autorise pas** à traiter les `databases/*.jsonl` locaux comme l'état du VPS, ni à conclure un
    déploiement sur un code retour (INT-19, INT-15).
18. **N'autorise pas** à conclure une calibration ou une recommandation de seuil sans les éléments
    statistiques exigés (`CLAUDE.md` §règle du statisticien, INT-20).
19. **N'autorise pas** à inventer un fait sur le code : l'information manquante s'écrit
    « À CONFIRMER AU DÉMARRAGE DU TICKET » (INT-18).
20. **N'autorise pas** à reformuler une interdiction en recommandation, ni à traiter un doute de
    gating comme un feu vert : le doute est gaté par défaut (§4.2).
21. **N'autorise pas** à préparer, proposer ou exécuter un passage au capital réel : décision
    opérateur exclusive (`GOVERNANCE.md` §5.5, §8.1).

---

## 11. Aide-mémoire d'une session d'implémentation

```
1. GOVERNANCE.md          lu intégralement
2. MASTER_ROADMAP.md      phase ouverte ? dépendances closes ?
3. IMPLEMENTATION_QUEUE.md ticket actif ? statut ni FAIT ni GATED ni BLOQUÉ ?
4. prompts/PROMPT_<ID>.md périmètre, fichiers autorisés, critères d'acceptation
5. test rouge             écrit, exécuté, ÉCHOUE   -> capture conservée
6. non-régression AVANT   exécutée, résultat capturé
7. patch                  fichiers du prompt uniquement, ≤ 4 fichiers OU ≤ 300 lignes
8. test rouge             devient VERT
9. non-régression APRÈS   strictement identique à l'AVANT
10. 4 invariants          contrôlés un par un, avec falsificateur
11. commit                format §5.2, un seul commit
12. queue                 ticket -> FAIT (SHA, date UTC, volume, tests)
13. rapport               format §9, épistémique, portée bornée
14. STOP                  aucune suite sans nouvelle invocation opérateur
```

---

**Version :** 1.0 — 2026-07-25.
**Modification de ce document :** par ticket dédié uniquement, sur décision opérateur.
