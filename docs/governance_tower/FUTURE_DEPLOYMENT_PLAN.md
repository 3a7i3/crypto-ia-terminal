# Governance Tower — Plan d'exploitation future (lot H)

> **Ce plan n'est pas une autorisation.** `GOV_TOWER_RUNTIME_DEPLOYED = FALSE`.
> Aucune étape ci-dessous ne peut être exécutée sans nouvelle mission, gate dédiée et,
> tant que la garde est active, exception explicite sous #286.

## 1. Séquence proposée

1. **GOV-TOWER-00/01 (ce dépôt, source-only)** : contrats, prototype local, tests, revue.
2. **Lecture GitHub réelle** : décision opérateur sur le mode (anonyme ou jeton fine-grained en lecture seule, un seul dépôt) ; smoke test daté ; verdict `SENTINEL_01_REAL_GITHUB_CONNECTED` seulement après preuve.
3. **Lecture VPS réelle** : uniquement via les snapshots déjà publiés (G3–G5) ; transport existant et autorisé (copie de fichiers par l'opérateur, ou Operator API par tunnel loopback). Aucun nouveau collecteur, compte, port ou unité.
4. **Gate de déploiement distincte** (si souhaité) : préflight, isolation, authentification, rollback, exception #286.
5. **Capacités d'approbation** : uniquement après fermeture de Gate O (#315) ; jamais dans Sentinel lui-même.

## 2. Architecture de production éventuelle (à valider)

| Domaine | Proposition |
|---|---|
| Identité OS | compte dédié non privilégié (ex. `govtower`), sans sudo, sans accès au checkout gelé, à `/opt/crypto-ai-terminal`, aux `.env` ni aux données PPL/FIN |
| Processus | unité distincte de l'Operator App ; `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome=read-only` sauf dossier de snapshots en lecture, `PrivateTmp`, `MemoryMax`/`CPUQuota` bornés |
| Réseau | écoute loopback ; accès uniquement par tunnel/tailnet déjà gouverné ; aucun port public |
| Authentification | dédiée (pas la session Operator) ; obligatoire avant toute exposition hors poste local |
| TLS | terminé par le mécanisme d'accès choisi (tailnet/tunnel), jamais de certificat ad hoc |
| Release | répertoire de release propre, empreintes publiées, aucune écriture dans les releases opérateur |
| Journal | audit expurgé, borné, `0600`, rétention définie |
| Ressources | préflight CPU/RAM/disque comme LAB-01 (PSI, MemAvailable) |
| Rollback | arrêt et retrait de la seule unité GT ; aucune dépendance d'Advisor/API/web vers GT |

## 3. Protocole d'admission VPS (futur)

1. Préflight READ-ONLY : ressources, ports, comptes, absence de conflit avec Advisor/API/web/publishers.
2. Revue de sécurité de la release exacte (SHA, empreintes, tests, CI verte au HEAD).
3. Exception #286 dédiée, usage unique, expirante, rédigée par l'opérateur.
4. Exécution par l'opérateur uniquement (aucun agent n'exécute sudo).
5. Preuves d'isolation après installation : Advisor/API/web inchangés (PID, NRestarts, InvocationID), aucun nouveau port public.
6. Plan d'arrêt et rollback testés ; verdicts consignés sur GitHub.

## 4. Registre des risques résiduels

Voir [THREAT_MODEL.md §5](THREAT_MODEL.md#5-risques-résiduels). Ajouts propres à l'exploitation :
latence et quotas GitHub ; dépendance à la fraîcheur des publishers (timers G5) ; absence de publicateur
gouverné de journaux (`NO_GOVERNED_LOG_PUBLISHER`) ; risque de confusion entre interface de démo et
interface réelle si le bandeau est retiré.
