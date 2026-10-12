# RESEARCH-CAPTURE-CONTRACT-01 — Future epoch native capture, v1

Date : 2026-10-12 UTC. Mission [#414](https://github.com/3a7i3/crypto-ia-terminal/issues/414).
Parents #404/#408/#410 ; roadmap #285 ; campagne #401 DESIGN_ONLY.
Base relue : `b4089a611e0c9565d8b39268317cc31ee25f04af`.

**DOCUMENTATION_ONLY / DESIGN_FOR_REVIEW / NOT_IMPLEMENTED / NOT_DEPLOYED.**
`FUTURE_CAPTURE_ACTIVATION=DENIED`; `PAPER_STRESS_RUNTIME_GO=DENIED`.
La future epoch n'a pas d'identifiant alloué ni de configuration admise.
Ce contrat ne lève pas #286 et ne crée aucune autorité de trading.

## 1. Question scientifique et frontière

Pouvoir distinguer, sur une fenêtre explicitement bornée : opportunité recensée,
non-sélection, tentative d'analyse, retour sans packet/exception, packet construit,
observation éligible, livraison native et écriture avec reçu syscall fsync.
La capture ne démontre ni avantage de stratégie ni performance contrefactuelle.
Les tapes marché/PPL/FIN/OOS de D2–D6 restent des gates séparées.

[La copie D1-C relue](https://github.com/3a7i3/crypto-ia-terminal/issues/404#issuecomment-6131476786)
contient 10824 packets, 5486 rejets, 210 lignes admission et 10824 identités ;
les hashes concordent, mais elle ne fournit pas le roster indépendant ni la
chaîne native fsync exigée. Les attempt_id admission ne sont pas les invocations
analyze_symbol. Ce constat est borné à cette copie, pas à tout le VPS.
Aucun registre, ID, reçu ou compteur historique ne sera complété après coup.

Epoch protégée : `BURN-IN-EPOCH-01-20260926T064144Z` ; source consignée
`116634be0d3c015cce1cfa58be7da7255414fbfd`, config
`9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4`.
Aucun changement de cette epoch, de son checkout/config/systemd, de PPL/FIN,
stratégie/signal/risk/sizing/admission/PB_MAX_POSITIONS, Watchdog/TESTNET/LIVE,
exchange ou permissions. Aucun accès secret ni nouveau staging/export production.
Aucune collecte ou exécution de commandes VPS n'appartient à cette mission.

## 2. Unités, producteurs et indépendance

| Flux natif proposé | Producteur et preuve attendue | Ce qu'il ne prouve pas seul |
|---|---|---|
| Universe/cycle/selection ledger | Sélecteur avant filtre et avant appel analyse ; universe snapshot/version, cycle start/end/interrupted et tous candidats | Un ledger déclarant complete=true ne prouve pas sa propre exhaustivité |
| Attempt plan + lifecycle | Identité réservée avant chaque invocation, y compris réanalyse ; début/retour/exception/interruption | Le journal des packets ne prouve pas les tentatives sans packet |
| Packet capture | Producteur packet lié causalement à attempt/trace/decision | REJECTED ne signifie ni observation éligible ni persistée |
| Dispatch/stage ledger | Réception native de chaque étape pour la livraison RejectionStore visée | Un counter EventBus ou RETURNED listener ne prouve pas persist |
| Exact records | Acquisition séparée des bytes, prefixes, offsets, file generation | Existence JSONL ne prouve ni fsync ni complétude |
| Syscall witness | Instrument indépendant du writer liant appel/retour/fd/file/range | Même émission applicative renommée fsync ne vaut pas témoin indépendant |
| Boundary/custody manifest | Responsable Data Steward et reviewer indépendants nommés avant activation | Root-owned, hash ou signature ne prouvent pas automatiquement l'origine |

Indépendance minimale : le roster est acquis en amont de la construction packet,
avec journal/custody séparés ; sa copie n'est pas calculée depuis packets ou
identities. La preuve d'exhaustivité exige aussi un contrôle externe du cycle,
une séquence et une frontière attestées, et une mesure des défaillances communes.
Un même processus/host peut rester un domaine de panne commun : le déclarer.
Le fsync witness a un canal d'acquisition distinct, un binaire/config/owner
identifiés et une preuve de liaison syscall. Aucun mécanisme (eBPF, audit ou
wrapper système) n'est choisi/admis ici. Une solution nécessitant privilèges
fait l'objet d'une revue sécurité séparée ; pas d'élévation chatgpt-ro.
Source_id distincts sont nécessaires pour D1-E, mais insuffisants pour la confiance.

## 3. Enveloppe native et identités

Chaque événement brut porte explicitement : schema_version, stream_id,
producer_id/version, process_boot_id, producer_sequence, event_id, native UTC
aware event time, monotonic timestamp/unit/clock_domain, clock_quality,
paper_epoch_id, code_sha, config_sha256 et capture_campaign_id.
Code/config/epoch sont vérifiés extérieurement contre launch/birth manifests,
pas copiés d'un environnement auto-déclaré. UNKNOWN reste un état distinct.
Les secrets ne sont ni capturés, ni hashés, ni publiés.

Identités : cycle_id, roster_id, native attempt_id et lien parent ; après
construction uniquement, packet_id/trace_id/decision_id puis observation_id.
Une tentative sans packet porte packet_id=null avec résultat explicite,
jamais un packet synthétique. Les collisions, changements de boot, réutilisations,
retries et late events sont conservés, pas fusionnés par proximité temporelle.
L'identité physique de fichier comprend génération/boot/source device+inode ou
équivalent attesté ; un chemin ou fd numérique réutilisable ne suffit pas.

Les dataset_id/source_boundary_id finaux peuvent être produits à la clôture
Research par l'exporteur existant, avec provenance vérifiée. Ils ne sont pas
inventés au moment de la décision ni assimilés à des IDs producteur natifs.
Les événements bruts portent la campagne native ; le manifest de capture lie
les IDs dataset/boundary finaux aux prefixes originaux. L'adaptateur ajoutera
l'enveloppe boundary vérifiée en projection, sans modifier les bytes bruts.

## 4. Dénominateur D1-D et cas sans packet

Avant sélection : universe snapshot identifié, policy/version et résultat pour
chaque candidat ; non sélectionné, sélectionné ou sélection interrompue/UNKNOWN.
Avant appel : append du plan attempt_id ; observation séparée du démarrage.
Réanalyses => nouveaux attempt_id, même cycle/symbole possible. Si un plan ne
peut être journalisé, intervalle non certifiable ; aucune invocation inconnue
ne devient implicitement zéro.

Retours natifs : RETURN_WITH_PACKET, RETURN_NO_PACKET, RAISED_BEFORE_PACKET,
RAISED_PACKET_STATE_UNKNOWN et UNKNOWN ; reason/exception class expurgée,
started_at/ended_at, corrélation et état d'interruption. Le dénominateur garde
les invocations en cours au cutoff comme MISSING_INVOCATION_RECEIPT.

Conservation distincte :
- candidats = sélectionnés + non sélectionnés + sélection UNKNOWN ;
- tentatives planifiées = catégories exclusives du [D1-D V2](D1_D_NATIVE_ATTEMPT_CONTRACT.md) ;
- packets capturés != tentatives, rejets != trades.

D1-D V2 exige selected_for_analysis bool et un roster/plan explicite. La collecte
brute avec sélection UNKNOWN est donc **non admissible à V2 telle quelle** :
rapport de gaps séparé ou futur contrat versionné ; jamais convertir en false,
supprimer ces candidats ni prétendre que la population passée à V2 est totale.
Même un bilan arithmétique parfait ne prouve pas le cycle externe ou la source.

## 5. D1-E : causalité et reçus fsync

Réutiliser la machine d'états du
[D1-E V1](D1_E_DURABILITY_RECEIPT_CONTRACT.md), sans en modifier le code ici :
BUILD attempt/outcome → publication acceptance/drop → target dispatch/start →
filter → persist attempt → validation → append → flush → fsync return → persist
outcome → listener outcome. Respecter les étapes natives exactes du contrat.
Chaque reçu conserve receipt_id, sequence causale native sans gap, attempt,
packet/trace/decision et après BUILD_OK observation, listener et source_id.
Flags actionable/safe_mode/bus_configured/listener_registered : bool ou null.
Filter criteria et résultat validator sont capturés séparément, sans défaut
legacy implicitement converti en preuve. Failure/drop/skip/false/throw a une
reason native ; capture expurgée, pas stack/env/message secret libre.

SUBMITTED doit établir l'acceptation native avant l'exécution corrélée du worker,
y compris la race executor-start/counter-increment. Un timestamp après coup
ne crée pas un prédécesseur. L'implémentation future doit démontrer le handshake
causal ou déclarer l'intervalle non admissible ; pas de barrière ajoutée sans
mesurer son effet sur l'ordonnancement de l'expérience future.

D1-E V1 couvre une livraison RejectionStore par tentative. Le raw ledger conserve
delivery_id et retries ; plusieurs livraisons ne sont pas écrasées en V1.
Un contrat/verifier V2 et tests seront requis pour leur admission réelle.
packet event_time et record.ts_iso ont une sémantique explicitement préenregistrée
(événement d'observation retenu), jamais égalisés après coup pour passer le join.
Wall-clock en UTC ne certifie pas synchronisation ; horloges distribuées exigent
un budget d'incertitude/causalité séparé. Aucune troncature par jour calendaire seul.

Append/flush/fsync : exact UTF-8 record incluant newline ; bytes [start,end),
record_sha256, file_id/generation, fd lifetime, partition_selected_at,
write_date_utc/partition_name, append actual count/error et horodatages natifs.
Short write/partial append restent des faits ; aucun record complet reconstruit.
Partition choisie avant minuit et append/fsync après minuit conserve son identité.

Le témoin indépendant lie syscall type, fsync_call_id, entry/return, errno/result,
fd→file generation et bytes concernés. Un fsync peut couvrir plusieurs writes :
le mapping effectif est capturé, pas inféré du dernier record. Si non représentable
par V1, revue/versionnement avant admission. PERSIST_FALSE après fsync reste distinct.
Le témoin et son propre journal peuvent tomber en panne : drops/sequence/fences
et confiance d'acquisition sont contrôlés indépendamment.

fsync-return n'est pas preuve de crash/power-loss durability. Nouvelle partition,
rename et directory fsync ont une preuve distincte si cette garantie est revendiquée ;
à défaut DIRECTORY_METADATA_DURABILITY=NOT_PROVEN. Aucune promesse matérielle implicite.

## 6. Fenêtre, clôture et custody

Fenêtre de sélection [start,end), cutoff >= end. Séparer event time et capture time.
Une invocation/livraison commencée dans la fenêtre mais terminée après end est
conservée jusqu'au cutoff ; toujours en cours => UNKNOWN, pas filtrée silencieusement.
Capturer cycle/producer boot fences, ordres causaux et gaps, queue entrants,
processed/dropped/inflight et sorties jusqu'au watermark vérifié. QUIESCENT
requiert preuves des producteurs et queues, pas un flag libre ni zéro position.
Une fenêtre de collecte close ne signifie pas arrêt des admissions trading.
La finalisation du burn-in actuel reste exclusivement #282/#286.

Export futur : autorisation explicite d'une liste de chemins/prefixes read-only,
owner/custody, captures stables avant/après, offsets et hashes recalculés,
manifest de provenance/scopes, registre de composants, identité de l'exporteur,
clock/coverage et omissions. Root-owned sans write pour lecteur, ancêtres sûrs,
regular files/symlinks refusés ; stockage de copie hors home Advisor.
Une racine signée n'a de valeur que sous key custody/owner/anti-rollback admis.
Aucun effacement/rotation d'un segment non remis à custody ; le quota plein crée
CAPTURE_INCOMPLETE et un arrêt de collecte borné, pas une purge des preuves.
Un manifest ne reclassifie jamais epoch binding UNVERIFIED en VERIFIED.

## 7. Ressources et incidents — budgets proposés, non configurés

Ces plafonds sont des hypothèses de laboratoire, pas des mesures du VPS actuel.
Ils devront être acceptés ou remplacés **avant toute activation future**.

| Mesure | Proposition initiale | Gate attendue |
|---|---:|---|
| Queue collecteur | 4096 événements, 16 MiB total, événement ≤64 KiB | Test saturation ; limite bytes ET count ; overflow explicite |
| RSS collecteur | ≤128 MiB | Mesure charge nominale/pic, pas seulement config |
| CPU collecteur | ≤10% d'un cœur sur 60 s | Budget total host et p95/p99 mesurés |
| Disque capture | ≤256 MiB par segment ; ≤2 GiB par campagne | Préflight headroom et preuve quota ; pas de suppression automatique |
| Débit soutenu | ≤256 KiB/s ; burst ≤1 MiB/s pendant 5 s | Scénario maximal préenregistré et drops observables |
| Drain au cutoff | délai borné proposé 30 s | Expiration => incomplete/UNKNOWN, jamais QUIESCENT synthétique |
| Effet invocation | overhead p99 proposé ≤5 ms et débit ≥95% du baseline isolé | Comparaison répétée, distributions et coût fsync/witness inclus |

Aucun fsync synchronisé par décision n'est imposé sur la future orchestration
sans benchmark ; batching possible seulement avec mapping de couverture natif.
Les plafonds collecteur ne rendent pas bornés le writer et le témoin : chacun
nécessite son budget et leur somme host reste UNADMITTED. Ces budgets sont donc
une dépendance explicite bloquant activation, pas une exemption.

Queue pleine/disk full/crash/witness outage : signaux bornés de dégradation et
perte, compteur indépendant/fence manquante, intervalle non certifiable. Si même
le canal de gap échoue, UNKNOWN. La collecte passive ne change pas signal/risk/
admission/PPL ; toute règle d'arrêt de la future expérience nécessite sa gate
opérateur préenregistrée. Le plan ne contourne pas les protections capital.
Retour vers trading/agents/calibration interdit ; droits uniquement append capture.
Aucun import du collecteur dans les readers API pour activer la machine.

## 8. Validation discriminante à implémenter ultérieurement

| Scénario | Résultat attendu |
|---|---|
| Analyse sans packet/exception, selected sans plan, réanalyse même cycle | Counts explicites/UNKNOWN ; conservation D1-D ; pas de plan fabriqué |
| Candidate perdu avant selection/cycle interrompu | Gap externe visible ; aucune complétude annoncée |
| Listener RETURNED mais persist False | Pas de durabilité ; outcome explicite |
| Safe mode/nonactionable/no listener/build failed | Exclusion/unknown native ; aucun rejet perdu déduit |
| Worker démarre avant counter submit | Handshake causal vérifié ou capture non admissible |
| Duplicate/mismatched ID, seq gap/reverse, retries | Abort ou version différente ; pas dedup silencieuse |
| Append partiel, flush error, fsync errno, fsync puis close error | Bytes et outcome distincts ; aucune reconstruction de succès |
| Rotation minuit/fd réutilisé/fsync groupé | File generation/partition/ranges joins exacts ou non admissible |
| NaN/Infinity/1e400/-1e400/duplicate key/hash faux | Fail closed, pas jeu vide |
| Witness forgé par même writer/source_id renommé | Refus de certification extérieure malgré pins cohérents |
| Queue pleine/disque plein/restart/witness perdu | Capture incomplete ; gaps ou UNKNOWN ; coût borné |
| Cutoff avec inflight, clock drift, prefix instable | Pas completeness/quiescence ; late evidence conservée |
| Permission/symlink/manifest/boundary/code/config discordants | Refus d'admission, preuve originale inchangée |

Les tests seront synthétiques et les crash/fault-injection exécutés en laboratoire
isolé, jamais sur le burn-in actuel. Aucune exécution ni test nouveau dans ce
livrable documentaire ; aucune donnée réelle déclarée eligible par ces scénarios.

## 9. Gates de passage et décisions encore ouvertes

| Gate | Preuve nécessaire | État actuel |
|---|---|---|
| C0 Design review | Unités, owners, schemas, menace commune, erreurs et budgets examinés | FOR_REVIEW |
| C1 Implémentation isolée | Issue/PR séparée, code/verifiers versionnés, tests négatifs, absence feedback | NOT_IMPLEMENTED |
| C2 Instrument qualification | Roster completeness externe, fsync witness indépendant, confiance/custody/clock | NOT_PROVEN |
| C3 Capacity/privacy | Budgets writer+witness+collector, benchmark, redaction, quotas/permissions | NOT_PROVEN |
| C4 Future experiment authorization | Gates #401/#282/#286 applicables, epoch/code/config/protocol et décision humaine | DENIED |
| C5 Deploy/activate gate | C0–C4, release exacte, isolation, rollback hors epoch active, décision séparée | DENIED |
| C6 Real-data acceptance | Bytes/pins/custody/gaps/fences revérifiés indépendamment ; D1-D/E et limites | NOT_OBSERVED |

C4/C5 ne sont jamais autorisées par un merge source. Une future expérience
indépendante, même baseline sans stress, nécessite sa propre admission ; une
collecte n'est pas un contournement des gates PAPER-STRESS. U8/L4 non certifiés.

Décisions non résolues : identité nominative des propriétaires/reviewer ; instrument
fsync et permissions ; preuve externe de cycle ; budgets witness/writer ; clock
uncertainty ; adapter/versionnement retries/group-fsync/UNKNOWN selection ; règle
opérateur d'arrêt future ; emplacement/rétention/key trust. Chacune bloque la gate
correspondante. Aucune valeur opérationnelle n'est choisie par défaut.

Rollback présent : revert du seul document. Futur rollback runtime : protocole
préenregistré conservant segments/gaps et attestant effets de désactivation ;
ni restart actuel ni retour silencieux à une epoch antérieure.

## 10. Verdict et références

`FUTURE_CAPTURE_CONTRACT=DESIGN_FOR_REVIEW`
`FUTURE_CAPTURE_IMPLEMENTATION=NOT_IMPLEMENTED`
`FUTURE_CAPTURE_ACTIVATION=DENIED`
`D1_D_PRODUCER_COMPLETENESS=NOT_PROVEN`
`D1_E_PER_PACKET_DURABILITY=NOT_PROVEN`
`D1_NATIVE_EPOCH_BOUNDARY_BINDING=NOT_PROVEN`
`COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`

Contrats : [D1-D](D1_D_NATIVE_ATTEMPT_CONTRACT.md),
[D1-E](D1_E_DURABILITY_RECEIPT_CONTRACT.md),
[inventaire daté](D1_D_E_AUTHORIZED_COPY_INVENTORY_20261012.md).
Source capability : [producer attempts](../../../research_data/stress_d1_producer_attempts.py),
[durability verifier](../../../research_data/stress_d1_durability.py).
Ces fonctions conservent NOT_PROVEN/NOT_OBSERVED même sur bundles cohérents ;
l'acceptation externe ne réécrit pas leur verdict. Aucun certificat historique modifié.
