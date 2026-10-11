# D1_C_LIMITATIONS_AND_NEXT_GATES

Mission #404 ; parent source #406
`b99c2ed4f38ebeff481b5f470ed2d08e8e852257`, méthode `D1_C_V1`.

1. Revue indépendante source et CI au SHA final D1-C : contrat producteur,
   catégorisation conservatrice, tests négatifs, hash de l'auditeur historique.
2. Gate de relecture des copies Research : identité chatgpt-ro, permissions,
   racine readonly_research_staging, manifest exact, source auditeur exacte,
   code D1-C revu et exécution sans installation sur runtime ni droits supplémentaires.
   Si indisponible : REAL_BYTES_NOT_AVAILABLE ; ne pas contourner l'accès.
3. Rapporter la partition réelle des 4186 sous le boundary de capture, avec
   inconnus et équations. Une capture complète reste différente d'un producteur
   complet ; données de l'epoch demeurent UNVERIFIED sous le contrat historique.
4. Pour une attente effective d'écriture : preuve autorisée des flags/safe mode,
   builder et signal final, publication et abonnement, validation de prix,
   dispatch et retour persist par packet, rotation UTC/délais au boundary.
   Définir le protocole de preuve et sa future gate ; aucune instrumentation
   ni modification runtime de l'epoch active dans cette mission.
5. D2–D6, finance finale et protocole OOS restent leurs gates propres. La clôture
   de D1-C ne clôture pas #282, n'autorise ni PAPER-STRESS ni promotion Research.

Le programme conserve l'auditeur D1 intact et réutilise ses validateurs. Il
refuse les profils alternatifs via la CLI : hash/count historiques fixés, root
absolu explicitement Research, composants réguliers root-owned sans bits
write, ancêtres root-owned sans write group/other et aucun symlink. Les helpers de fixtures restent des API internes
non attestantes ; ils ne peuvent changer la CLI. La possession de bytes et le
succès de tests ne confèrent aucune autorité opérationnelle.

Les champs absents du packet ne sont pas reconstruits depuis un score, un
prix d'entrée ou un acteur de rejet. Le fallback FLAT du builder et la collision
signal_raw exigent une corroboration du message natif, sinon UNKNOWN. La voie
G8-D native explicite est utilisée pour le candidat ; une simple projection
REJECTED n'est pas un booléen legacy observé. Ce choix peut sous-classer des
candidats, ce qui est conservateur et révisable avec preuves supplémentaires.

Sortie agrégée uniquement, vocabulaires fermés, aucun record/ID/secret. Les
échecs ne rendent pas une population zéro : classification NOT_EMITTED,
compteurs non établis. Les valeurs temporelles restent déclarées, pas des
horloges certifiées. Pas de reçu producteur dans les quatre fichiers.

`SATISFIED != CERTIFIED` ; `SOURCE_PROOF != RUNTIME_PROOF` ;
`CAPABILITY != AUTHORITY` ; `UNKNOWN != ZERO` ;
`HISTORICAL_RUNTIME_PROOF != CURRENT_RUNTIME_PROOF` ;
`REJECTED_PACKET != PERSISTED_REJECTION` ;
`CAPTURE_COMPLETENESS != PRODUCER_COMPLETENESS`.

`COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`

Disponibilité observée 2026-10-11 ~05:18 UTC : appareil distant Offline,
copie locale historique absente. REAL_BYTES_NOT_AVAILABLE. La prochaine
gate immédiate est une revue du SHA D1-C exact, puis une exécution gouvernée
sur la copie lorsque l'accès est effectivement disponible. Aucun accès
restreint ne justifie une élévation ni une lecture des ledgers de production.

## Correctifs après revue indépendante de #407

La procédure historique ci-dessus reste une preuve datée. Pour `D1_C_V2`,
utiliser exclusivement [l'exécution isolée gouvernée](D1_C_GOVERNED_ISOLATED_EXECUTION.md).
Le classificateur ne lit plus de données réelles sans vérificateur de provenance
installé par le lanceur autonome : SHA et chemin du module effectivement chargé
sont contrôlés avant toute lecture des composants. Pas de package applicatif
requis sous `python3 -I -B` ; aucun changement des sources #406.
Seconde revue indépendante requise ; `D1_C_REAL_BYTES_NOT_AVAILABLE` demeure
le statut réel, distinct des nouveaux PASS synthétiques.
