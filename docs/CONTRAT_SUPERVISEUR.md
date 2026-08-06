# CONTRAT — Superviseur, « le bot des bots »

> **Statut : contrat proposé. Aucun code n'a été écrit pour l'accompagner.**
> Rédigé le 2026-08-06 à la demande de l'opérateur.
>
> **Autorité** : ADR-0007 (passivité absolue des observers) · ADR-0008 +
> [`dip/SCIENTIFIC_INTELLIGENCE_LAYER.md`](dip/SCIENTIFIC_INTELLIGENCE_LAYER.md)
> (niveau L3.5) · `CLAUDE.md` (gel architectural, règle du statisticien) ·
> [`TELEGRAM_CHANNEL_CONTRACTS.md`](TELEGRAM_CHANNEL_CONTRACTS.md) (format).
>
> Un contrat écrit avant le code est ce qui a permis de mesurer huit conflits
> de propriété entre les six canaux existants. Le même geste est appliqué ici
> **avant** d'ajouter un septième émetteur.

---

## 0. Ce que vous avez demandé existe déjà sur le papier

| Votre formulation | Où c'est déjà spécifié |
|---|---|
| « prend en compte les résumés de chaque bot » | L3.5 § 2 — consomme des artefacts déjà produits |
| « observe, analyse » | SI-01 Decision Knowledge Graph, SI-02 Causal Memory |
| « suggère des propositions » | SI-03 Evidence Engine, `RecommendedExperiment` |
| « le bot des bots » | L3.5 — la couche au-dessus du DIP et de L3 |
| « modifie le comportement dans le futur » | **Non-objectif explicite de L3.5** — voir § 3 |

Le niveau L3.5 vaut **0/100** au PMI. Ce n'est pas un manque d'idée : c'est un
niveau **gaté**, délibérément non construit.

---

## 1. Deux objets distincts, pas un

La demande contient deux choses de nature différente. Les confondre est la
seule vraie façon de rater ce projet.

### ① Le Narrateur — surface d'observation

Il **raconte** ce que la machine fait, en direct, en langage lisible. Il ne
conclut rien, ne pondère rien, ne propose rien. C'est un instrument de
lecture. **Constructible aujourd'hui** : c'est un outil de mesure, autorisé
par le gel (`CLAUDE.md` — « outils de mesure, outils d'audit, tableaux de bord
scientifiques »).

### ② Le Superviseur — couche de connaissance L3.5

Il **analyse**, relie les décisions aux hypothèses, détecte les
contradictions, dégrade la confiance des connaissances vieillissantes et
recommande des expériences. **Gaté par SI-G1** (voir § 4) : tant que la gate
n'est pas franchie, il reste une architecture cible.

Le Narrateur peut exister sans le Superviseur. L'inverse est faux : sans
narration fiable, une couche de connaissance conclut sur du sable.

---

## 2. Contrat du Narrateur

Six champs, comme tout canal de ce projet. Les trois premiers disent ce qu'il
est ; les trois derniers le rendent vérifiable.

### Mission

*Une seule* question : **« que se passe-t-il dans la machine, en ce moment,
et pourquoi ? »**

Jamais « que devrait-on faire » — c'est ② — ni « que fait le marché » — c'est
le canal ④.

### Sources autorisées

- `black_box.jsonl` via `BlackBoxEncryption` / `black_box.query()`
  — **source primaire**, événements typés et horodatés
- Les **résumés déjà émis** par les canaux ① à ⑥ (jamais leurs sources brutes :
  le Narrateur ne recalcule rien, il relaie et met en relation)
- `databases/rejections/` en lecture, pour l'agrégation horaire uniquement

**Interdit** : lire ou écrire dans le moteur de décision, s'abonner à un
`DecisionPacket` en vol, instancier un composant décisionnel.

### Événements reçus

Deux registres, et la distinction est le cœur du contrat.

**En direct — uniquement ce qui change un état :**

| Événement | Origine |
|---|---|
| Halt, safe mode, veto | `HALT_TRIGGERED`, `SAFE_MODE` |
| Changement de niveau de vigilance | `AWARENESS_ALERT` |
| Première occurrence du jour d'une couche bloquante | `TRADE_REFUSED` dédupliqué par couche |
| Règle interne déclenchée | `RULE_TRIGGERED` |
| Événement système (démarrage, reconnexion, dégradation) | `SYSTEM_EVENT` |

Volume attendu : **20 à 50 messages par jour**.

> **Les entrées et sorties de position n'y sont pas, et c'est délibéré.**
> Elles appartiennent à ② PaperArena (contrat § 3), qui les émet déjà en
> temps réel depuis le 2026-08-05. Une première version de ce contrat les
> avait listées ici : c'était fabriquer un neuvième conflit de propriété
> dans le document écrit pour les empêcher. Le Narrateur raconte la **vie
> décisionnelle interne** — ce qu'aucun canal ne possède — pas les trades.
> `TRADE_EXECUTED` et `POSITION_CLOSED` sont donc **interdits ici**.
>
> C'est aussi ce qui le rend utile : ② vous dit *qu'un* trade a eu lieu,
> le Narrateur vous dit *pourquoi les 300 autres candidats n'en ont pas
> eu*.

**En agrégat — la routine, jamais message par message :**

> « Dernière heure : 340 candidats examinés, 12 au-dessus du seuil, 3 bloqués
> par le portfolio brain, 1 exécuté. Seuil effectif 66→72. »

Une phrase à la place de ~1600 événements.

### Événements interdits

- Un message par refus ou par HOLD — **mesuré à ~1600/h**, soit 26/minute :
  au-dessus des limites Telegram et illisible par un humain. C'est le mode
  d'échec principal de ce canal, pas un détail de réglage.
- **Événements de trade** `TRADE_EXECUTED` / `POSITION_CLOSED` (→ ② PaperArena,
  propriétaire unique, déjà émetteur)
- **Changements de régime** `REGIME_CHANGE` (→ ④ marché, et ⑤ les agrège déjà
  en digest)
- Toute recommandation d'action (→ ② Superviseur, une fois SI-G1 franchie)
- Tout KPI de performance (→ ②), tout score ou univers (→ ④), toute santé
  infra (→ ①)
- Toute conclusion scientifique — le Narrateur décrit, il ne conclut pas

### Niveau d'urgence

Bas par défaut. **Seuls** un veto, un halt et une dégradation de santé
réveillent. Le reste attend d'être lu.

### Fréquence maximale

- Direct : **6 messages / heure**, au-delà les événements sont mis en file et
  fusionnés dans l'agrégat suivant.
- Agrégat : **1 / heure**.
- Un plafond franchi est **annoncé** (« +14 événements groupés »), jamais
  silencieux — une troncature muette se lit comme « il ne s'est rien passé ».

---

## 3. La frontière de gouvernance

Trois verbes, dont un seul est interdit.

| Verbe | Autorisé ? | Condition |
|---|---|---|
| **Observer** | oui | lecture seule, append-only |
| **Recommander** | oui, sous ② | avec niveau d'evidence explicite et référence à une hypothèse versionnée |
| **Appliquer** | **jamais** | ADR-0007 ; `FEATURE_AUTO_CALIBRATION=false` est un défaut permanent |

« Modifie le comportement dans le futur » est un **non-objectif écrit** de
L3.5 : *« ne doit pas modifier un seuil, activer l'auto-calibration,
remplacer la validation opérateur »*.

Le chemin autorisé, et il existe :

```
Superviseur observe  ->  formule une proposition datée et référencée
                     ->  OPÉRATEUR valide explicitement
                     ->  configuration versionnée appliquée
                     ->  Superviseur observe l'effet
```

La boucle est fermée, l'humain est dedans, et rien ne bouge sans lui. C'est
la seule forme sous laquelle « améliorer le comportement » est compatible
avec la constitution du projet.

---

## 4. Ce qui manque pour ② — les gates

| Gate | Condition | État |
|---|---|---|
| SI-G0 | ADR-0008 + spec publiés | **franchie** |
| SI-G1 | Observer Certification Level 3 **et** dataset CERTIFIED/PASS | **non franchie** — à re-mesurer, la suite était au Level 2 |
| SI-G2 | SI-01 lit décisions et hypothèses sans écrire dans le moteur | non |
| SI-G3 | Première Knowledge Release avec contradictions documentées | non |
| SI-G4 | Une conclusion confirmée puis réévaluée sur dataset ultérieur | non |

S'y ajoute la règle du statisticien : **N = 200/500**, 76/150 gagnants,
121/150 perdants. Une couche de connaissance qui conclurait sur ce corpus
produirait des conclusions non falsifiables — exactement ce que L3.5 existe
pour empêcher.

**Conséquence pratique** : ① est constructible cette semaine. ② ne l'est pas,
et le construire quand même reviendrait à fabriquer un oracle qui parle avant
d'avoir des données.

---

## 5. Ce que le Superviseur ne fera jamais

Repris des non-objectifs de L3.5, sans reformulation :

ajouter une stratégie · ajouter un indicateur technique · modifier un seuil ·
activer l'auto-calibration · envoyer un ordre · remplacer la validation
opérateur · conclure une hypothèse sans dataset certifié · produire une
recommandation sans niveau d'evidence explicite.

---

## 6. Comment vérifier que ce contrat est respecté

Un contrat sans test est une intention. Quatre propriétés doivent être
verrouillées par des tests avant toute mise en service :

1. **Aucun import du moteur de décision** dans le module — vérifiable
   statiquement.
2. **Plafond de fréquence** : au-delà, mise en file et fusion, jamais perte
   silencieuse.
3. **Aucun message de recommandation** émis par ① — la frontière ①/② est
   testable sur le texte produit.
4. **Un événement non mesuré n'est jamais rendu comme un zéro** — règle
   éprouvée trois fois le 2026-08-05 (PnL ouvert, solde futures, prix
   manquant).

---

## 7. Décision demandée à l'opérateur

Ce document n'engage rien tant qu'il n'est pas validé. Trois questions :

1. Le périmètre ① vous convient-il, ou voulez-vous d'autres événements en
   direct ?
2. Acceptez-vous que ② reste gaté derrière SI-G1, ou souhaitez-vous un ADR
   qui déplace explicitement cette frontière — avec ses conséquences ?
3. Le Narrateur doit-il écrire dans un canal dédié, ou en privé comme ① à ④ ?
   Le canal `Rapport_ia-crypto-quant` a montré qu'un canal non ouvert n'est
   pas lu.
