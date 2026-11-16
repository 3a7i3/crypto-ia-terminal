# Journal des décisions de session

| ID | Décision | Portée / conséquence |
|---|---|---|
| OR-D01 | W0–W5 autorisés localement, pas VPS ni publication | Originaux préservés ; M1 RC1 PARTIAL au gate humain |
| OR-D02 | Priorité explicite OPERATIONAL RECOVERY, produit utilisable | OR-03→OR-06 autorisés sur hôte principal ; sudo, unités dédiées, collecte publique, corpus neuf et publication privée admis ; anciens interdits M1 remplacés uniquement dans cette portée |
| OR-D03 | Ne pas reconstruire D1–D3 ni le moteur M1 | Réutilisation release/venv/frontend et collecteur borné ; pas de refactor trading |
| OR-D04 | Canal agent sans sudo ; intervention SSH minimale opérateur | Aucun contournement du blocage Desktop Commander ; scripts préparés par agent puis exécutés en SSH par l'opérateur |
| OR-D05 | Pilote 900 s / 30 instruments avant exploitation continue | exit0 et preuves vérifiées, corpus distinct de l'historique protégé |
| OR-D06 | Continuité initiale par campagnes réutilisées | Restart systemd, pause15s + maintenance + bootstrap ; limites provider conservées, refus3/4 sans restart automatique ; pas de promesse de flux sans coupure |
| OR-D07 | Nouveau corpus d'exploitation avec rétention | Aucune suppression du corpus historique ; référence opérationnelle récente, pas dataset Research immuable |
| OR-D08 | Accès Samsung d'abord sur8443 puis correction d'intégration | La première livraison séparée ne satisfaisait pas l'usage de l'icône existante ; l'opérateur a demandé son intégration dans l'app de base |
| OR-D09 | Même origine443, identité PWA et défaut radar | Les permissions privées443 s'appliquent ; elles ne sont pas les règles Samsung-only8443 ; pas d'ACL modifiée |
| OR-D10 | Ajouter un rendu des OHLCV existants | Chandeliers/volumes SVG, valeurs exactes conservées ; aucun indicateur/signal ni nouvelle dépendance |
| OR-D11 | Corriger l'incident de permissions, sans nouvelle architecture | Le script avait copié dist0700 avant root ownership ; rollback effectif, chmod des seuls assets, contrôle de lecture sous compte réel, reprise réussie |
| OR-D12 | Activer le frontend habituel au boot | Pas de reboot de qualification imposé pour la documentation ; enabled vérifié |
| OR-D13 | Documenter les réalisations et écarts, publier sur GitHub | Demande explicite finale opérateur ; branche/PR de synchronisation, sans merge ni nouveau déploiement |

Provenance des autorisations : conversation de travail fournie par l'opérateur, pas commentaire GitHub préexistant et aucune URL de conversation inventée. Les références GitHub antérieures sont dans ROADMAP_DELTA.md. Les décisions protègent BR1/PPL, NSS-SQ-01 suspendu, ECC parked, le corpus historique et l'interdiction d'ordre automatique/activation Advisor. Elles ne changent pas la finalité scientifique ni la qualification des signaux.
