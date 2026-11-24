# Operational Recovery — bilan du 16 novembre 2026

**OBSERVATION_MOBILE_AVAILABLE / SOURCE_RECONCILIATION_PENDING / NO_SIGNAL_CERTIFICATION**

Parent de suivi : [#576](https://github.com/3a7i3/crypto-ia-terminal/issues/576), rattaché à [#574](https://github.com/3a7i3/crypto-ia-terminal/issues/574) et [#323](https://github.com/3a7i3/crypto-ia-terminal/issues/323). Ce dossier documente des opérations déjà autorisées et exécutées. Sa publication ne fusionne ni n'active le code de référence joint.

| Besoin | Document |
|---|---|
| Réalisations, chronologie, incidents et preuves | [Bilan](REPORT.md) |
| Ce qui s'ajoute à la roadmap, ce qui reste ouvert | [Écarts et suivi](ROADMAP_DELTA.md) |
| Choix effectués et autorisations reçues | [Journal des décisions](DECISIONS.md) |
| Exploitation, limites et rollback | [Runbook](RUNBOOK.md) |
| Empreintes, état daté et provenance | [Manifeste](SOURCE_MANIFEST.json) |
| Delta frontend effectivement construit et testé | [Patch de référence](reference/frontend-from-d1-rc1.patch) |
| Maintenance effectivement utilisée | [Source conservée](reference/maintenance.py.txt), [tests](reference/test_maintenance.py.txt) |

Les références `.txt` et le patch sont **inactifs** : ils ne modifient pas les chemins canoniques du produit, ne lancent pas de service et ne remplacent pas une revue d'intégration source/CI. Le patch porte sur le `frontend-source` de l'archive D1-RC1 identifiée dans le manifeste, **pas sur main**. Les archives complètes et informations privées d'exploitation restent dans les références de custody du manifeste.

La livraison établit un socle de consultation sur l'application mobile existante. Elle ne vaut pas U8, L4, certification A9, qualification de signaux, validation de rentabilité, finalisation PPL/FIN ou réouverture d'Advisor. BR1/PPL FROZEN ; NSS-SQ-01 SUSPENDU ; ECC PARKED.
