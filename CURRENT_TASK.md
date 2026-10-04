# Handoff — baseline APP-LMI validée, audit documentaire #372

Baseline source vérifiée le 2026-10-04 :
`main@26dddfb01cdad68378bf98c83c1c242ceb8db31a`.
APP-LMI-DETAIL-01 [#370](https://github.com/3a7i3/crypto-ia-terminal/issues/370) /
[PR #371](https://github.com/3a7i3/crypto-ia-terminal/pull/371) est terminé :
`APP_LMI_DETAIL_01_SOURCE_READY`. Aucun chantier LMI à reprendre.

Mission Codex actuelle : recadrage du handoff et audit READ-ONLY de
[PR #372](https://github.com/3a7i3/crypto-ia-terminal/pull/372), sous #365/#362.
Branche de ce recadrage : `docs/handoff-main-26dddfb` ; documentation uniquement.
Ne pas confondre ce travail avec les branches de certification ci-dessous.

## Branches candidates, sans effet sur la baseline

- #372, draft MachineLevelCertification L0 : head audité
  `8b70b834d5eb101fdc31b93cdc623e949eddfc65`, base `26dddfb`.
- #363, draft Agent Economy : head observé
  `f95ee48807b4a9d080c0ab38e0d1d0202ad7c559` ; mission séparée, non auditée ici.

Ces SHA sont des observations datées : relire GitHub avant toute reprise.
Aucune de ces branches ne constitue une baseline intégrée ou une certification
effective tant que sa revue et sa fusion gouvernée ne sont pas acquises.
#372 reste draft ; aucune fusion, sortie du draft ni certification L1 effectuée
par cette mission de handoff.

## Résultat de l’audit #372

Correction requise avant sortie du draft : `MACHINE_MATURITY_SNAPSHOT_v1.json`
omet `generated_at_utc` et `snapshot_hash`, exigés par le minimum figé R2
dans `CERTIFICATION_CATALOG_v0.1.md`, section 6. Définir la convention de hash,
compléter ces champs puis recalculer les identités et relancer la revue du head.
La description PR annonce aussi des identités anciennes : hash du certificat
et blobs des deux artifacts à synchroniser avec le candidat corrigé.

Points vérifiés : hash canonique du certificat actuel
`e1c75a38cdac0522c26d91dbfd2e7c190229006b8db68bc677af2a19e548bcd5` correct ;
catalogue, ledger, input manifest, formal review et evidence manifest liés aux
blobs attendus ; cinq critères L0 et union des EvidenceRecord IDs cohérents ;
snapshot lié au même certificat. Diff #372 : deux JSON documentaires seulement.
Les CI vertes ne remplacent pas la conformité au catalogue ni l’effectivité.

## Preuve APP-LMI et limites

Avant fusion, l’arbre d’intégration testé de #371 précédait l’intégration de
#367 ; le merge final ajoutait ses deux artifacts documentaires sans chevaucher
les 15 fichiers LMI. Ne pas attribuer rétroactivement la CI pré-merge au tree
final. Depuis, GitHub expose 21 workflows post-merge `push` sur le SHA exact
`26dddfb`, tous SUCCESS, dont CI, Cross-Stack et preuve visuelle U3b.
Cela certifie la source testée, pas un déploiement ni un niveau Machine-Maturity.

Garde-fou [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286) :
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD`. Runtime/déploiement non certifiés ici ;
aucun accès VPS configuré, restart, moteur, service, epoch, PPL/FIN, risk/sizing,
Watchdog ou exchange modifié. Aucun retrait CryptoRadar.

[Entrée développeur](docs/DEVELOPER_ENTRYPOINT.md) ;
[contrat LMI](docs/contracts/APP_UNIFY_01_U3B_MICROSTRUCTURE_CONTRACT.md) ;
[inventaire app](docs/plans/APP_UNIFY_FUNCTIONS_AND_OUTPUTS_INVENTORY.md).
