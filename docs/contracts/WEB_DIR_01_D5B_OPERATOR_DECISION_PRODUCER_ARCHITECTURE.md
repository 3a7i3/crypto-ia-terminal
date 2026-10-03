# WEB-DIR-01 / D5B — Architecture du producteur gouverné OperatorDecision

Mission : #310 · Parent : #288 · Roadmap : #285 · Contrat D5A : #307  
Forensic : #287 et #309 · Économie d’agents : #284 · Garde-fou burn-in : #286  
Base de preuve : `main@c932544d5be74f2216ec4898da710b961074a57f` (PR #311 fusionnée)  
État : **proposition d’architecture à relire ; aucun producteur, endpoint ou projection déployé**

## 1. Décision d’architecture et périmètre

Chaque registre amont possède ses propres faits. Un futur registre canonique
`OperatorDecision` posséderait l’identité des décisions, le journal
d’événements append-only et la projection de lecture. Un adaptateur peut
soumettre des candidats ; il ne peut ni fabriquer une décision humaine ni
l’inférer depuis la télémétrie brute. Cette répartition est un contrat proposé,
pas la déclaration qu’un registre, adaptateur, stockage ou endpoint existe déjà.

Chaîne cible :

`fait source certifié → candidat gouverné → contrôle d’admission et d’identité → événements append-only → projection déterministe → future lecture D5C`

Une future action humaine ne peut faire progresser le workflow que vers un gate
distinct. Elle ne peut pas fusionner, déployer, redémarrer ou modifier PAPER
actif. Le garde-fou #286 reste supérieur.

Les champs minimaux `OperatorDecision`, statuts, priorités, règles d’autorité
et distinctions de disponibilité de D5A sont conservés. Le
`GET /api/operator/v1/decision-pipeline` observe des décisions de trading ;
la `decision_queue` de cold-start est un invariant interne ; #287/#309
apportent des preuves. Aucun de ces éléments n’est un producteur admissible
pour la file de décisions de l’opérateur.

## 2. Matrice de propriété des sources

« Propriétaire » désigne le registre ou workflow autoritaire du **fait source**,
pas le futur registre `OperatorDecision`. Tous les propriétaires ci-dessous
sont proposés pour une phase future ; aucun n’est déclaré déployé par ce
document. Chaque admission exige une version source vérifiable et un transfert
explicite approuvé par son propriétaire.

| Classe | Propriétaire du fait source proposé | Seuil de candidature | Raccourci interdit |
|---|---|---|---|
| Problème | Futur Problem Registry de #284 | `VERIFIED_PROBLEM`, preuve et demande explicite d’arbitrage humain ; `CANDIDATE_PROBLEM` reste en amont | Constat forensic ou détection d’agent → décision |
| Évolution proposée | Futur registre gouverné Proposed Evolution | Version relue avec justification, risque, validation et retour arrière | Suggestion LLM ou issue GitHub → décision |
| Résultat de bounty | Futur Bounty Registry de #284, lié au problème vérifié | Résultat `VALIDATED`, revue indépendante, preuves et transfert explicite `HUMAN_DECISION` | `CLAIMED`, `SUBMITTED` ou récompense AIC → acceptation |
| Recherche | Futur registre gouverné des candidats Research | Candidat reproductible et relu, demande visant une epoch future | Diagnostic, classement ou PnL estimé → epoch active |
| Sécurité et dette | Futur workflow gouverné de remédiation | Constat validé, preuve expurgée, risque et propriétaire identifié | Scan, log brut ou secret → file |
| Incident | Futur registre gouverné des incidents | Suite relue avec demande de remédiation bornée | Alerte ou UNKNOWN runtime → action |
| Migration d’architecture | Futur registre de changements d’architecture | ADR/demande versionnée avec dépendances et retour arrière | Classement #287 → suppression |
| Runtime, configuration ou coût | Workflow distinct de changement ou de coûts | Demande précisément délimitée vers un gate futur | Clic dans la file → systemd, PPL, FIN, exchange ou facturation |

Une issue/PR GitHub peut servir de pointeur vers une preuve, jamais d’autorité
par elle-même. Conflit de sources, propriétaire inconnu, révision invérifiable,
preuve obsolète, exposition non autorisée ou filiation ambiguë : refus de
l’admission. Un même fait peut engendrer plusieurs propositions de finalités
différentes ; le doublon d’une même révision et finalité est idempotent. Tout
remplacement est explicite.

## 3. Contrat proposé : OperatorDecisionCandidate

Un candidat est une **demande d’admission**, pas une décision gouvernée ni une
action de l’opérateur. Le propriétaire amont répond de ses faits. Le futur
contrôle d’admission vérifie le dossier puis attribue un `decision_id`
distinct et immuable. Ni client, ni agent, ni registre amont n’attribue une
acceptation humaine ou un statut canonique.

```text
OperatorDecisionCandidate {
  schema_version, candidate_id, candidate_revision,
  source: {
    source_type, source_id, source_ref, source_sha,
    source_generated_at_utc, producer, producer_authority,
    owner_registry, owner_record_version
  },
  decision_type, title, summary, proposed_change,
  requested_initial_status, requested_priority,
  risk, validation, rollback,
  evidence: {
    evidence_status, evidence_refs[], source_hashes[],
    tests, ci, review, limitations[]
  },
  requested_by, requested_at_utc, decision_purpose,
  upstream_approval_ref, correlation_ref
}
```

Sont requis : identité et version du candidat, identité et révision stables de
la source, hash exact lorsqu’il existe, propriétaire responsable, finalité,
résumé, risque, état des preuves et références inspectables. Une preuve absente
ou expurgée est signalée ; une liste vide ne prouve pas son inexistence.
`requested_initial_status` et `requested_priority` restent des demandes.
La priorité reprend exclusivement le vocabulaire D5A
`CRITICAL/HIGH/MEDIUM/LOW/UNKNOWN` ; aucun calcul depuis le PnL, la couleur,
les labels GitHub, l’AIC, un avis d’agent ou le frontend. Le contrôle
d’admission consigne les valeurs approuvées et leurs motifs, ou rejette avec
un motif traçable.

Clé d’idempotence de l’admission :
`(owner_registry, source_type, source_id, owner_record_version, decision_purpose)`.
Une nouvelle version de source ne modifie pas silencieusement une décision :
elle exige un événement de rectification relu ou un nouveau candidat qui
remplace explicitement le précédent. La normalisation ne lit pas directement
JSONL/DB bruts, Telegram, exchange, processus runtime ou sortie LLM libre.

## 4. Registre et contrat proposé : OperatorDecisionEvent

Le futur registre `OperatorDecision` attribue seul les `decision_id` uniques
et non réutilisables, les versions séquentielles et les statuts canoniques.
Son journal append-only est autoritaire pour les faits du workflow ; la
projection de lecture est reconstruisible. La décision projetée conserve au
minimum le schéma D5A et la provenance des preuves. Une correction ajoute un
événement rectificatif ; elle ne réécrit pas l’historique.

```text
OperatorDecisionEvent {
  schema_version, event_id, decision_id, decision_version,
  event_type, actor_type, actor_ref, occurred_at_utc,
  previous_status, new_status, expected_version,
  candidate_id, source_revision_ref, reason,
  evidence_refs[], idempotency_key,
  previous_event_hash, event_hash
}
```

`event_id` et `idempotency_key` sont uniques dans leurs portées définies.
La canonisation cryptographique, la signature, le stockage et la gestion des
clés nécessitent une revue de sécurité avant implémentation : un hash
n’authentifie pas un humain. `previous_event_hash` relie les événements
ordonnés depuis un marqueur initial explicite. Rupture de chaîne, trou de
version ou hash invalide rendent la projection non certifiable. Les horodatages
sont en UTC ; la version/séquence du registre fixe l’ordre, pas l’horloge seule.

Catégories proposées :

- `CANDIDATE_ADMITTED`, `EVIDENCE_AMENDED`, `PRIORITY_REVIEWED`,
  `BLOCKED`, `UNBLOCKED`, `SUPERSEDED`, `CLOSED` : événements
  du service de gouvernance, avec acteur identifié et autorisé ; ils ne
  représentent jamais une acceptation humaine.
- `HUMAN_ACKNOWLEDGED`, `HUMAN_REMEDIATION_REQUESTED`,
  `HUMAN_REFUSED`, `HUMAN_PLANNED`,
  `HUMAN_ACCEPTED_FOR_FUTURE_GATE` : exigent
  `actor_type=HUMAN_OPERATOR`, identité authentifiée et autorisée,
  version attendue, intention explicite, motif et accès préalable aux preuves.
  Aucun agent ne peut usurper cette autorité. Leur interface d’écriture
  relève d’une phase séparée, hors D5B et D5C.

Les statuts D5A restent : `TO_VALIDATE`, `TO_READ`, `BLOCKED`,
`TO_PLAN`, `REMEDIATION_REQUESTED`, `ACCEPTED_FOR_FUTURE_GATE`,
`REFUSED`, `SUPERSEDED`, `CLOSED`. Table de transitions,
authentification, autorisation, session/CSRF et anti-rejeu nécessitent la revue
D5D. Ces événements ne sont ici que des contrats. Rejeter toute version
attendue obsolète, transition invalide, identité humaine non prouvée,
collision d’identifiant avec contenu différent et écrasement silencieux.
Un rejeu strictement identique rend le résultat initial sans nouvel événement.

## 5. Projection gouvernée et frontière D5C

Un futur constructeur de projection consomme uniquement le journal certifié,
vérifie versions et liens des hash, puis associe des références source
immuables et autorisées. Il ne découvre jamais des décisions via pipeline de
trading, dashboard, recherche GitHub, inventaire #287 ou heuristique UI.
L’Operator API pourrait exposer cette projection en lecture seule ; D5C
l’affiche sans recalculer statuts, priorités, compteurs, disponibilité ou
autorité.

Enveloppe proposée, **sans endpoint implémenté** :

```text
{
  schema_version, product="OPERATOR_DECISION_QUEUE",
  domain="GOVERNANCE", authority="GOVERNANCE_WORKFLOW_PRESENTATION",
  generated_at_utc, as_of_event_version, source_watermark,
  freshness, availability, decision_count, counts_by_status,
  items: OperatorDecision[], limitations[], projection_hash
}
```

L’étiquette d’autorité réservée ne devient valable qu’après certification
d’un vrai producteur et de la projection ; elle n’est pas active aujourd’hui.
Les compteurs concordent avec l’ensemble complet non filtré, le périmètre
déclaré et la version/watermark ; les statuts terminaux sont inclus si le
périmètre les inclut. Une réponse filtrée ou paginée distingue sa sélection
des totaux globaux. L’ordre est fourni par le producteur avec une clé stable
et `decision_id` comme départage, jamais calculé par React. Chaque projection
porte provenance, fraîcheur, limites et version. Schéma incompatible, champs
manquants, watermark incomplet/obsolète ou défaut d’intégrité conduisent à
l’indisponibilité, jamais à un zéro synthétique. Les références de preuves
sensibles ont un contrôle d’accès distinct ; aucun secret dans la projection.

La disponibilité est un état explicite, jamais déduit de `items=[]` :

| État | Preuve requise | Affichage |
|---|---|---|
| `NON DÉPLOYÉ` | Aucun producteur/projection gouverné certifié | Aucun nombre ni item affirmé ; état actuel de #310 |
| Zéro explicite | Producteur certifié sain, watermark et périmètre complets, `decision_count=0`, items vides, compteurs nuls, fraîcheur conforme | Vraie file vide avec provenance |
| `NOT_AVAILABLE` | Producteur existant, champ facultatif indisponible avec motif | Indisponibilité du champ, sans valeur inventée |
| `UNKNOWN` | Producteur/projection existant mais intégrité, complétude ou état indéterminable | Aucun compteur fiable ; échec fermé |
| `BLOCKED` | Décision concrète avec prérequis manquant | Statut d’un item, pas disponibilité globale |

Endpoint absent, timeout, erreur, fichier absent ou tableau vide ne valent
pas zéro explicite. La carte Direction reste `File de décisions —
NON DÉPLOYÉ` jusqu’à une preuve de déploiement distincte. Un verdict
d’architecture source n’en change pas l’affichage.

## 6. Exemples et cas négatifs, sans exécution

1. Un `CANDIDATE_PROBLEM` détecté depuis les preuves forensic demeure dans
   le workflow Problem Registry. Il ne crée ni décision ni bounty.
2. Un `VERIFIED_PROBLEM` relu et demandant explicitement une planification
   humaine peut soumettre un candidat versionné. L’admission crée un
   `decision_id` et `TO_PLAN` seulement si propriétaire, révision,
   preuves et politique sont vérifiés.
3. Un bounty `SUBMITTED` ne devient pas une décision. Un résultat
   `VALIDATED` indépendamment peut demander `HUMAN_DECISION` ;
   `ACCEPT_FOR_FUTURE_GATE` ne déclenche ni merge ni paiement.
4. Un candidat Research appuyé sur un dataset immuable ne peut être promu
   dans l’epoch burn-in active. Une source obsolète bloque l’admission
   ou entraîne une rectification relue.
5. Un doublon strict est idempotent ; même clé avec contenu différent,
   version obsolète, identité humaine absente ou chaîne hash rompue échouent
   sans modifier la projection.
6. Un producteur sain, complet et certifié peut déclarer zéro s’il n’existe
   aucune décision. Aujourd’hui aucun producteur n’existe : l’état est
   `NON DÉPLOYÉ`, sans compteur zéro.

## 7. Critères de revue et absence d’impact

Avant le verdict d’architecture : relire la matrice avec #284, D5A et
#287/#309 ; vérifier les quatre contrats et exemples négatifs ; confirmer que
le diff Git est documentaire uniquement ; enregistrer base/head exacts,
contrôles et limites. Ce verdict ne certifie ni déploiement ni runtime, ni
sécurité d’une future API d’écriture, ni conformité d’une implémentation.

Avant un producteur exécutable : autorisation distincte, accord des
propriétaires, schémas, stockage/intégrité/sécurité, transitions, protection
des données, vecteurs de test et validation fail-closed. Avant D5C :
producteur et projection certifiés avec preuve de disponibilité/fraîcheur.
Avant D5D : contrat d’écriture humaine authentifiée, autorisée, concurrente,
idempotente et auditable. Avant déploiement : gate runtime séparé conforme
à #286.

Aucun endpoint, producteur, writer, worker, action UI, modification
systemd/cron/timer, déploiement, redémarrage, changement PAPER actif,
epoch/config/risk/sizing/PB_MAX_POSITIONS, PPL/FIN, promotion Research,
Watchdog, TESTNET/LIVE ou écriture exchange n’est autorisé. Aucun nettoyage
des composants #287/#309 n’est autorisé.

**Verdict cible, sous réserve de revue et de preuves :**  
`WEB_DIR_01_D5B_PRODUCER_ARCHITECTURE_CERTIFIED`
