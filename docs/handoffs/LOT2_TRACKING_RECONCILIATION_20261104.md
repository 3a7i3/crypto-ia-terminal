# Lot 2 — réconciliation du suivi et des anciennes PR

Relevé source : **2026-11-04 UTC**, suite au plan du 2026-11-03.
Base : `main@9433c18b5077cc957bfdf2c8bd707070dc5c67d1`, tree
`d35af63af38f33d0f67c50d981026716ac701e51`.
Mandat : documentation et suivi GitHub. Ce texte est une proposition source
tant que sa PR n'est pas fusionnée ; les actions GitHub ont leur état propre.
Aucun nouveau contrôle VPS dans ce lot.

## Acquis source et CI du lot 1

| Livraison | HEAD final | Fusion dans main |
|---|---|---|
| [#552 prototype L2](https://github.com/3a7i3/crypto-ia-terminal/pull/552) | `f8efe3c05305394b841ddea87c7a4ef5da894b4e` | `46b6fb3ad1a91b08f9a0d25f4e4ed7ad070a1f7e` |
| [#554 cœur Flux](https://github.com/3a7i3/crypto-ia-terminal/pull/554) | `fc3a3d53f3d8eab261a10e6218b048d5541d3100` | `24d497423f26972b27f7647865b39e6dfadc3ff0` |
| [#555 reader/API Flux](https://github.com/3a7i3/crypto-ia-terminal/pull/555) | `c6d21a9f7efd12c6b7cc6dd4f8d17a05509d2ef6` | `9b960aa6e8ccd7500ea74ad9153f0c0be617fbb8` |
| [#556 identité des ancêtres](https://github.com/3a7i3/crypto-ia-terminal/pull/556) | `4d58cd54768ce8c56fa023e477173f749af3976d` | `9433c18b5077cc957bfdf2c8bd707070dc5c67d1` |

Lot 1 terminé en source. Au commit de fusion #556 : **19 workflows et 24
check-runs SUCCESS**, aucun échec ni attente au relevé post-fusion.
Le [TEST REGRESSION GATE](https://github.com/3a7i3/crypto-ia-terminal/actions/runs/41760285722/job/126346109475)
donne 11 521 passed, 114 skipped, 13 deselected, 2 xfailed.
[Coveralls](https://github.com/3a7i3/crypto-ia-terminal/actions/runs/41760285797/job/126346109685)
et [Codecov](https://github.com/3a7i3/crypto-ia-terminal/actions/runs/41760285662/job/126346109295)
donnent chacun 11 435 passed, 114 skipped, 13 deselected, 2 xfailed, 59 subtests.
Ces résultats ne sont pas ceux du nouveau lot documentaire.
La [revue indépendante #556](https://github.com/3a7i3/crypto-ia-terminal/pull/556#pullrequestreview-5762282293)
est technique (Codex), pas une approbation humaine.

## Décisions sur les onze anciennes PR ouvertes à l'entrée du lot

| PR | Décision et état | Limite / suite |
|---|---|---|
| [#467](https://github.com/3a7i3/crypto-ia-terminal/pull/467) J01 M2 | **CLOSED**, déjà absorbée | Clôture administrative, branche/historique conservés |
| [#468](https://github.com/3a7i3/crypto-ia-terminal/pull/468) J01 M3 | **CLOSED**, déjà absorbée | Même preuve, aucune nouvelle qualification |
| [#469](https://github.com/3a7i3/crypto-ia-terminal/pull/469) J01 M4 | **CLOSED**, déjà absorbée | Même preuve, aucune activation |
| [#465](https://github.com/3a7i3/crypto-ia-terminal/pull/465) vision/plan J01 | **OPEN / DRAFT**, archive de trois documents proposée | Clôture après intégration de la copie ; J03–J07 au backlog |
| [#487](https://github.com/3a7i3/crypto-ia-terminal/pull/487) étape 7 | **OPEN / DRAFT**, archive d'un document proposée | La fin de l'admission authentifiée reste non prouvée |
| [#491](https://github.com/3a7i3/crypto-ia-terminal/pull/491) préparation P4 | **OPEN / DRAFT**, archive d'un document proposée | #492 intégrée ; fin P4/P5/P6 non déduite des tranches suivantes |
| [#471](https://github.com/3a7i3/crypto-ia-terminal/pull/471) capture machine | **KEEP / OPEN / DRAFT** | Revue dédiée ; hypothèses de chemins/unités/permissions à confronter à l'hôte de restauration |
| [#475](https://github.com/3a7i3/crypto-ia-terminal/pull/475) sources d'alertes | **KEEP / OPEN / DRAFT** | Revue source, publication et installation distinctes |
| [#520](https://github.com/3a7i3/crypto-ia-terminal/pull/520) PC2 C8.3 | **KEEP / OPEN / DRAFT** | Revue/décision séparée ; C8.4 non livré, p1 unsupported/NE dans le parcours intégré |
| [#397](https://github.com/3a7i3/crypto-ia-terminal/pull/397) fin anticipée burn-in | **HOLD** fusion et activation | Effets externes et clôture scientifique sous décisions propres |
| [#374](https://github.com/3a7i3/crypto-ia-terminal/pull/374) Agent Registry | **PARKED_SOURCE_ONLY / OPEN / DRAFT** | Aucun registre runtime ni économie d'agents admis |

### Preuve d'absorption M2–M4

GitHub confirme [#470](https://github.com/3a7i3/crypto-ia-terminal/pull/470)
fusionnée dans `d328aea50950ee7af00b2d588fb2743ddec428e3`, ancêtre de la base.
Pour chacun des HEAD ci-dessous, `git merge-base --is-ancestor HEAD BASE`
retourne 0 et `git merge-base HEAD BASE` renvoie le HEAD lui-même :

| PR | HEAD conservé à la clôture |
|---|---|
| #467 | `95d1b0916872b0c89cbf28662416c2a662007b8e` |
| #468 | `98a9764e7ff82aed0f6719a0b89986c6d4bdffcc` |
| #469 | `c73e7813a1d0dcbb504c9f1bc44ead8439d30855` |

Clôtures effectuées le 2026-11-04 vers 02:39 UTC avec preuve et description
d'origine intégralement conservée. GitHub : `closed`, `merged=false` ; contenu
inclus par #470, aucun nouvel appel de fusion. L'ascendance ne prétend pas que
les blobs actuels soient identiques aux premières tranches. Le rapport J01
du 2026-10-18 conserve son statut historique de pré-revue.

### Plans uniques : conservation avant clôture

Les [cinq copies et leur manifeste](../archive/lot2_20261104/README.md) ont
exactement les blobs Git des originaux. Aucun des cinq fichiers n'existait à
son chemin d'origine sur la base. Les copies sont proposées dans cette PR,
**pas encore intégrées à main** ; #465/#487/#491 restent donc ouvertes avec
renvoi vers l'archive proposée. Leurs obligations restantes ne sont pas
réputées satisfaites par cette opération.

Références intégrées qui ont suivi : J01 #470, J02 #476/#477 puis #482/#483 ;
admission P1 #488, P2 #489, P3 #490, inspection #492, formats/readers #493–#502,
preuves physiques 3A #503/#504, attestations 3B #505–#507, population/plafonds
3C #508–#518, corpus/diagnostics #519/#521/#522. L'amendement PC2 #510 est
intégré ; ses validateurs #520 restent candidats. Ni contrôleur global,
ni campagne P5/P6, ni naissance réelle ne sont qualifiés ici.

## Source, installation, activation, preuve et certification

Dernière observation runtime disponible : **2026-11-03 18:35:26 UTC**
(12:35:26 à Mexico), audit préalable, **non renouvelé dans le lot 2**.

| Axe | Fait au relevé et limite |
|---|---|
| Source | Base main ci-dessus ; cœur/API Flux intégré, aucun validateur/client TypeScript Flux ni onglet Flux dans `frontend/src/views/MarketView.tsx` |
| Installation | API/Web sélectionnaient `1da7376829f82eacfb52794ec267be97523fb244` (#537). Paquets isolés `9af84de7d570604f03192c74cd27ae6e61a6cf33` et `1a1e61ca375b1f54a9a9b424d9ff5cc0ef95c3f7` installés inactifs ; pas des releases Flux actives |
| Activation | `crypto-restore-01` : API PID 257740 / Web PID 257806 actifs, NRestarts=0, boot désactivé, loopback 8090/8181. Aucun moteur/collecteur identifié dans les processus visibles ; visibilité limitée, pas une preuve exhaustive d'absence |
| Données | Snapshot marché généré `2026-10-29T05:32:36Z`, 124 lignes / 90 qualifiées. `/healthz` 200 = transport ; `/market` 200 = snapshot historique. `/venue-comparison` 503 NOT_CONFIGURED ; `/market-flow` 404 sur cette release |
| Sources manquantes | Snapshot machine, burn-in, événements, FIN, Research, storage, runtime, microstructure et projection PPL : 503 MISSING. Les copies migrées présentes ne sont pas réadmises scientifiquement par leur seule présence |
| Certification | Références historiques L0/L1 v2/L2/L3 et U7 conservées ; L4/U8 non certifiés. Aucun delta ultérieur recertifié implicitement. Gate O #315 ouverte ; #282 non finalisée ; #286 ACTIVE |

Reçu d'installation isolée : [#550](https://github.com/3a7i3/crypto-ia-terminal/issues/550#issuecomment-6567003085).
Les entrées `crypto-advisor-2` du connecteur étaient Offline, ce qui ne permet
pas de déclarer l'ancienne machine arrêtée. Aucun état instantané n'est inféré.

## Roadmap et journal de décisions

| Lot / décision | État | Critère de passage |
|---|---|---|
| 1 / D01 CI reproductible | **TERMINÉ EN SOURCE**, #556 | Preuves bornées au commit cité |
| 2 / D03 tranches absorbées | **EFFECTUÉ**, #467–#469 fermées | Heads/branches et descriptions conservés |
| 2 / D07 reprise canonique | #285/#323 actualisées ; documentation proposée pour revue | Fusion distincte de cette PR avant intégration à main |
| 2 / plans #465/#487/#491 | **ARCHIVE PROPOSÉE**, clôtures différées | Fusion des cinq copies et du manifeste avant clôture |
| 3A / D02 réutiliser Flux | **PROCHAINE MISSION PROPOSÉE**, non commencée | Audit/plan validé ; types/validateur/client, fixtures via builder/reader/API ; corpus Python/TS exécuté, ns exactes, invalides refusés |
| 3B / D04 V0 sur un flux | **NON COMMENCÉ**, après 3A | Vue progressive Scanner/détails/carnet/heatmap/replay ; mobile/desktop, clavier, clair/sombre, 503/STALE/UNKNOWN, audit visuel |
| 4 release reproductible | Après stabilité source | SHA/tree/build/hashes/rollback ; installation réelle sous autorisation applicable |
| 5 admission des données | Dossier à compléter, collecte non exécutée | Roster, usage/région, budgets, arrêt, horloges, reçus/custody puis décision sur le plan exact |
| 6 publication passive | **NON AUTORISÉE par ce lot** | Artifact admis, release exacte, bascule/rollback gouvernés et hash servi vérifié |
| 7 visibilité scientifique | Sources à admettre séparément | Provenance, même frontière PPL/FIN, historique/inconnus conservés |
| 8 Colony source | #520 puis C8.4 et corpus séparés | Aucune qualification de contrôleur déduite des observers |
| 9 / D06 gouvernance | #397 HOLD, #374 parquée, gates conservées | Preuves et décisions propres |

D05 : source, installation inactive, collecte et publication restent séparées.
L'autorisation de fusion #556 est consommée ; aucun ancien GO n'est réutilisé
pour cette PR ou pour le runtime. Aucun travail 3A/3B/C8.4 commencé ici.

## Validation, risques et reprise

Contrôles : scope exact des fichiers, liens relatifs actifs, cinq copies
byte-identiques (blobs Git/SHA-256), ascendance et états GitHub après mutation.
Aucun test runtime requis pour ce diff de texte ; aucun code, workflow,
baseline, certificat, pin ou rapport de qualification existant modifié.
Les checks de ce nouveau HEAD sont à lire sur sa PR ; ne pas reprendre les
comptes de #556. Revue et décision de fusion distinctes restent requises.

Risque principal : lire les anciens textes comme état ou permission actuelle ;
les copies sont explicitement historiques. Rollback : revert documentaire si
fusionné ; bandeaux corrigeables et PR absorbées réouvrables si preuve contraire.
Aucune branche supprimée ; préserver les originaux et le manifeste.

**Prochaine action unique : revoir le lot 2 avant fusion. Ensuite, valider le
plan ciblé du lot 3A — contrat frontend Flux.**
