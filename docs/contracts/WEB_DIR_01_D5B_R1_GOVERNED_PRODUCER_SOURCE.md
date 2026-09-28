# WEB-DIR-01 / D5B-R1 — Noyau source isolé du producteur gouverné

Issue : #313 · Contrat d’architecture : #310 / PR #312 · Garde-fou : #286

Cette tranche ajoute `observability/operator_decisions/producer.py` et ses tests.
Elle ne modifie aucun import ou processus de l’Operator API, du frontend ou
de l’Advisor. Le registre en mémoire ne persiste rien et n’est pas un service.
Il illustre les règles d’admission, d’idempotence et de projection, sans
revendiquer une autorité runtime.

## Contrat mis en œuvre

- La politique explicite `source_type → owner_registry` est injectée ; aucune
  source n’est admise par défaut. Le dossier exige un hash SHA-256, une
  révision, une approbation amont et des références de preuves vérifiées.
- La clé `(owner_registry, source_type, source_id, owner_record_version,
  decision_purpose)` produit une seule admission. Un doublon identique
  retourne le même `decision_id` ; une collision est rejetée.
- L’unique événement émis est `CANDIDATE_ADMITTED` avec
  `actor_type=GOVERNANCE_SERVICE`. L’identité humaine et les transitions
  D5D ne sont pas implémentées. Le journal en mémoire est append-only,
  séquencé et chaîné par hash ; la projection revalide la chaîne.
- Sans attestation externe, la projection indique `NON DÉPLOYÉ` et aucun
  compteur. Une attestation de producteur et un watermark complet sont
  nécessaires pour illustrer la distinction contractuelle du zéro explicite.
  La classe `AvailabilityProof` est une entrée de simulation : cette tranche
  ne sait pas l’authentifier et ne doit jamais être branchée directement à
  une API. Une chaîne altérée ou un watermark incomplet donnent `UNKNOWN`.

## Limites qui restent à résoudre

Le stockage durable, la canonisation et signature cryptographiques, la
gestion des clés, la vérification de la preuve de déploiement, la fraîcheur,
l’autorisation d’accès aux preuves, les rectifications et transitions
d’événements, la source-of-truth de chaque registre métier ainsi que les
contrats D5C/D5D exigent des revues séparées. Les tests ne constituent pas
une certification runtime. Le code ne lit pas les faits PAPER et n’écrit pas
dans PPL/FIN, les services, l’exchange ou l’epoch active.

Le verdict R1, s’il est accordé après CI et revue, signifie seulement :
`WEB_DIR_01_D5B_R1_GOVERNED_PRODUCER_SOURCE_CERTIFIED`.
