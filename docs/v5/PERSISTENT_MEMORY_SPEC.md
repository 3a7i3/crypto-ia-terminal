# PERSISTENT_MEMORY_SPEC.md

> **Statut : conception.**
> C'est le document qui met en œuvre l'axiome A5 : *la connaissance survit aux
> modèles*.

---

## 1. Le test d'acceptation

> **Test de l'agent amnésique.**
> Un agent — ou un humain — arrive sur le dépôt. Aucun historique de
> conversation. Aucune mémoire externe. Aucun contexte transmis.
> En lisant **uniquement** les fichiers versionnés, il doit pouvoir répondre à
> six questions en moins d'une heure :

| # | Question |
|---|---|
| **Q-A** | Qu'est-ce que ce projet cherche à savoir ? |
| **Q-B** | Qu'est-ce qui est **démontré** ? |
| **Q-C** | Qu'est-ce qui est **cru mais non démontré** ? |
| **Q-D** | Qu'est-ce qui est **inconnu** ? |
| **Q-E** | Qu'est-ce qui est **indémontrable** avec l'instrumentation actuelle ? |
| **Q-F** | Qu'est-ce qu'il ne faut surtout pas faire, et pourquoi ? |

**Ce test est le critère unique de réussite de cette spécification.** Il est
exécutable : on peut le faire passer à un agent réel et mesurer.

### 1.1 Résultat actuel du test — mesuré

| Question | Réponse trouvable aujourd'hui ? |
|---|---|
| Q-A | **Partiellement** — `CLAUDE.md` donne les règles, pas les questions ouvertes |
| Q-B | **Non** — 1 hypothèse conclue (H3), non enregistrée dans un registre |
| Q-C | **Non** — aucune distinction croyance / preuve |
| Q-D | **Non** — aucun registre de questions ouvertes |
| Q-E | **Non** |
| Q-F | **Partiellement** — les ADR le disent, mais 66 markdown périmés à la racine les noient |

Preuve empirique de l'échec : une analyse externe s'appuyant sur ces documents a
conclu que le projet disposait d'un socle Research OS opérationnel — réfuté par
mesure (7 répertoires sur 8 déconnectés, gelés depuis mai 2026).

---

## 2. Les quatre niveaux de mémoire

| Niveau | Contenu | Volatilité | Autorité |
|---|---|---|---|
| **N0 — Conversation** | contexte d'une session | **perdue à la fin** | aucune |
| **N1 — Mémoire d'agent** | notes d'un outil ou d'un assistant | non partagée, non fiable | aucune |
| **N2 — Dépôt** | code, ADR, registres, verdicts | versionnée | **source de vérité** |
| **N3 — Ledger** | événements bruts | append-only, répliquée | irremplaçable |

### Règle fondamentale

> **Aucune connaissance importante ne réside en N0 ou N1.**
> Si une information n'existe qu'en conversation ou en mémoire d'agent, elle est
> **considérée comme inexistante**.

**Corollaire opérationnel.** Toute session de travail se termine par une
question : *qu'ai-je appris qui n'existe qu'en N0 ?* — et la réponse est écrite
en N2 avant clôture. Une session qui ne produit aucun objet N2 n'a rien produit.

### 2.1 Cas des mémoires d'assistants

Les mémoires persistantes d'outils d'assistance (fichiers de mémoire d'IDE,
notes d'agent) sont **N1 par construction** : privées, non versionnées, non
auditables, susceptibles de refléter un état passé. Elles sont utiles à la
productivité et **inadmissibles comme source**. Toute affirmation issue de N1
doit être re-vérifiée contre N2/N3 avant usage.

---

## 3. Les six documents d'amorçage

Placés à un emplacement canonique unique — `knowledge/` — et **entièrement
générés** depuis les registres, jamais rédigés à la main.

### 3.1 `STATE_OF_KNOWLEDGE.md` → répond à Q-B, Q-C, Q-D, Q-E

Tableau de toutes les `Question` avec leur état :

| État | Signification |
|---|---|
| `DEMONSTRATED` | ≥ 1 verdict `PASS`, répliqué |
| `REFUTED` | ≥ 1 verdict `FAIL` |
| `CONTESTED` | verdicts contradictoires |
| `BELIEVED` | **cru sans preuve** — hypothèse jamais testée mais influençant des décisions |
| `UNKNOWN` | jamais investigué |
| `UNMEASURABLE` | l'instrumentation actuelle ne peut pas trancher |

**`BELIEVED` est la colonne la plus importante du projet.** Elle liste ce sur
quoi le système agit sans preuve. Aujourd'hui, elle contiendrait la quasi-
totalité des 12 couches de décision.

### 3.2 `OPEN_QUESTIONS.md` → Q-D, Q-E
Questions ouvertes, ordonnées par gain d'information / coût, avec l'instrumentation
manquante pour chacune. Généré par la requête Q5 du graphe.

### 3.3 `FORBIDDEN.md` → Q-F
Ce qu'il ne faut pas faire, **avec la preuve de pourquoi** : chaque entrée cite
un incident, un verdict ou un ADR.

Entrées connues aujourd'hui, chacune adossée à un fait mesuré :
- ne pas déployer sans vérifier le fichier réellement exécuté *(incident du
  2026-07-09 : 3 tags d'audit mensongers, 55 fichiers sur 80 jamais déployés)* ;
- ne pas laisser une variable d'environnement désarmer une couche de décision
  *(`FORCE_TEST_EXECUTION`, `advisor_loop.py:1943`)* ;
- ne pas amputer un module sur la seule base d'une analyse statique *(52 modules
  classés morts statiquement, mesurés vivants en production)* ;
- ne pas changer d'univers de trading sans déclarer une époque *(4 remises à zéro
  de N en 6 semaines)*.

### 3.4 `EPOCHS.md`
Chronologie des époques de dataset : borne, cause, ce qui redevient invalide,
comparabilité préservée ou rompue.

### 3.5 `CURRENT_TRUTH.md` → Q-A
**Un seul** document décrivant le système réellement exécuté. Généré depuis les
mesures (`tools/runtime_cartographer.py`, trace d'exécution). Remplace les 66
markdown de la racine comme référence.

### 3.6 `README_FOR_AGENTS.md`
Point d'entrée unique. Contenu : ordre de lecture des cinq précédents, la
hiérarchie N0–N3, la liste des documents **périmés** à ignorer, et la phrase qui
ouvre le dépôt :

> *La documentation n'est jamais une preuve. C'est une hypothèse à vérifier.
> Le runtime tranche. En cas de doute, mesure.*

---

## 4. Règles de survie de la connaissance

| ID | Règle | Motif |
|---|---|---|
| **PM-1** | Aucun format propriétaire. Texte, JSON, Markdown | lisible dans 10 ans |
| **PM-2** | Aucun embedding comme représentation primaire | illisible sans le modèle qui l'a produit |
| **PM-3** | Tout objet porte `actor_id` **et** `actor_impl` | le rôle survit au modèle |
| **PM-4** | Tout document périmé est **daté et marqué**, jamais silencieusement conservé | 66 markdown ont déjà trompé un auditeur |
| **PM-5** | Les documents d'amorçage sont **générés**, jamais rédigés | un document manuel diverge dès la semaine suivante |
| **PM-6** | Un CI vérifie que les documents d'amorçage sont à jour | la péremption est détectée mécaniquement |
| **PM-7** | Le ledger (N3) est répliqué hors du dépôt | c'est la seule chose non reconstructible |
| **PM-8** | Aucune affirmation N1 n'est admise sans re-vérification | les mémoires d'agent reflètent un état passé |

### 4.1 PM-4 en pratique — la dette la plus urgente

Les 66 markdown de la racine ne doivent pas être supprimés (règle de
non-destruction), mais déplacés vers `docs/_historique/` avec un en-tête :

```
> ⚠ DOCUMENT HISTORIQUE — dernière modification 2026-05-26.
> Décrit un état révolu du système. Ne pas utiliser comme référence.
> Référence actuelle : knowledge/CURRENT_TRUTH.md
```

C'est une action à coût quasi nul et à rendement immédiat : elle supprime la
principale source de désinformation du dépôt.

---

## 5. Protocole de reprise par un agent futur

```
1. Lire  knowledge/README_FOR_AGENTS.md
2. Lire  knowledge/CURRENT_TRUTH.md        — ce qui tourne réellement
3. Lire  knowledge/STATE_OF_KNOWLEDGE.md   — ce qui est su, cru, ignoré
4. Lire  knowledge/FORBIDDEN.md            — les erreurs déjà payées
5. Lire  knowledge/OPEN_QUESTIONS.md       — où porter l'effort
6. VÉRIFIER par la mesure avant d'agir     — jamais faire confiance à 1-5
7. Toute conclusion nouvelle → écrite en N2 avant fin de session
```

**L'étape 6 n'est pas une formalité.** Les documents d'amorçage sont générés,
donc datés, donc potentiellement périmés. Un agent qui leur ferait confiance
sans mesurer répéterait exactement l'erreur de l'analyse externe de juillet.

---

## 6. Limites

**6.1** Cette spécification ne préserve pas le **jugement**. Elle préserve les
faits, les preuves et les interdits. Savoir quelle question mérite d'être posée
reste hors de portée de tout registre.

**6.2** Elle ne préserve pas le **contexte tacite** — pourquoi une piste a été
abandonnée sans être formellement réfutée. `OPEN_QUESTIONS.md` peut l'accueillir
en champ libre, mais ce champ sera toujours incomplet.

**6.3** Elle a un coût permanent. Écrire en N2 à chaque session est un frein
réel. **C'est un coût assumé** : c'est le prix de l'indépendance aux modèles, et
il est très inférieur au coût mesuré de la situation actuelle — douze mois de
travail dont l'état réel a dû être reconstruit par une campagne de mesure de
deux jours.
