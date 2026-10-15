# REJECTION_PERSISTENCE_CONTRACT

Contrat source version D1_C_V1 au parent #406
`b99c2ed4f38ebeff481b5f470ed2d08e8e852257`, identique sur les chemins producteurs
à main et à la source gelée. Pas de preuve de complétude runtime.

| Boundary / condition | Chemin source | Preuve dans copie / limite | Tests existants |
|---|---|---|---|
| Génération du packet | live_signal_engine.py::_to_decision_packet | metadata.lse_actionable = result.actionable ; signal_raw = result.signal ; signal_raw peut être écrasé par extra_meta : ne pas l'inverser depuis FLAT | test_decision_observation, test_s03b_provenance |
| REJECTED non actionable | advisor_loop.py::analyze_symbol, pipeline_g8d | marque `trade_allowed=False [signal_non_actionable]` si packet non terminal ; risk_gate/capital_engine peuvent rejeter auparavant | tests nouveaux de classification |
| Packet autonome | core/decision_packet.py::to_dict, is_actionable | side LONG/SHORT/FLAT, état, metadata, reasoning, history ; is_actionable est un état du lifecycle, PAS signal.actionable | test_decision_packet_confidence |
| Verdict legacy | advisor_loop.py::analyze_symbol | conjonction authority/meta/gate/awareness/conviction/etc. ; premier blocker legacy ordonné authority→meta→gate… ; REJECTED antérieur peut diverger de ce verdict | test_decision_observation::test_blockers_parsed_correctly |
| Publication | advisor_loop.py lignes 7085–7115 | seulement signal actionable et hors safe mode, bus non None, builder réussi ; fallback Telegram n'écrit pas RejectionStore | test_decision_event_bus |
| Abonnement | advisor_loop.py lignes 4970–5026 | FEATURE_EVENT_BUS + FEATURE_REJECTION_STORE et init réussie ; flags runtime non capturés | test_decision_event_bus |
| Construction | decision_observation.py::build_from_result | actionable depuis sig.actionable ; side depuis sig.signal ; trade_allowed depuis résultat ; prix depuis result.prix ; ID packet et provenance_valid depuis dp.packet_id | test_build_minimal, test_tolerant_missing_keys, test_s03b_provenance |
| Filtre 1 | rejection_store.py::on_observation | `not obs.actionable` exclut ; bool strict accepté par D1-C, pas coercition de chaîne | test_on_observation_ignores_non_actionable |
| Filtre 2 | même méthode | `obs.trade_allowed` exclut ; état REJECTED ne remplace pas ce booléen | test_on_observation_ignores_allowed |
| Filtre 3 | même méthode | side EXACT BUY/SELL/LONG/SHORT ; HOLD/FLAT/autres exclus | test_on_observation_ignores_hold |
| Provenance | même méthode | packet_id non vide, provenance_valid truthy (défaut True si absent) ; trace absent n'est PAS un filtre producteur | test_missing_packet_id_triggers_provenance_failure_and_rejection_skip |
| Conversion | rejection_store.py::_from_observation | lectures de nombreux champs, exceptions possibles avant persist ; record ne conserve PAS actionable/trade_allowed/provenance_valid | test_rejection_record_from_observation_fields |
| Validation | rejection_store.py::_validate | clés requises présentes via dataclass ; packet_id et symbol non vides ; price > 0 ; pas de contrôle observation_id vide, timestamp causal, doublon ou finitude ici | test_validate_* |
| Écriture | rejection_store.py::persist | validation puis lock, append, flush, fsync ; erreurs capturées, compteur mémoire ; bool de retour ignoré par on_observation | test_persist_ioerror_does_not_raise |
| Rotation | rejection_store.py::_get_path | date UTC de l'ÉCRITURE, pas de obs.ts ; délai au boundary journalier possible | test_persist_creates_file |
| Transport | decision_event_bus.py::publish/_safe_call | sans listener : retour ; shutdown : drop ; erreur listener capturée ; succès listener ne prouve PAS persist True | test_eventbus_counters_success_and_failure |
| Identité durable | decision_identity.py::persist | payload canonique namespace/cycle/symbol et digest ; historique à même trace possible, conflit interdit | auditeur D1 et nouveaux tests |

Meta refuse via validate_signal ; Gate a une voie legacy gate.check et une
voie packet check_packet. Le premier acteur de rejet packet n'est donc pas le
premier blocker de DecisionObservation. D1-C les présente séparément, sans
transformer `risk_gate` en `gate` par une jointure heuristique.

Les refus d'autorité précoces retournent HOLD/non-actionable, sans packet ; ils
ne font pas partie du dénominateur des packets capturés. Un packet peut être
persisté avant la publication ; exceptions, safe mode, flags ou arrêt peuvent
empêcher cette dernière. La capture ne conserve ni reçu de publication par
packet, ni tentative persist, ni retour fsync. Elle ne prouve pas la complétude
producteur. Les compteurs mémoire, même disponibles, ne suffiraient pas seuls
à reconstruire cette chaîne individuelle.

Horodatages : created_at naïf UTC accepté historiquement, mais horloge non
certifiée ; obs.ts est construit plus tard. Jointure exacte packet_id + trace_id,
symbol et cycle, jamais proximité temporelle. Ordre temporel contrôlé, sans
assimiler une capture journalière complète à un producteur complet.

D1-C utilise uniquement metadata.lse_actionable, metadata.signal_raw corroboré par le message natif live_signal_engine (collision
extra_meta autrement UNKNOWN), et les
transitions REJECTED de pipeline_g8d dont le message exact atteste
trade_allowed=False. Il ne lit pas un faux champ actionable ajouté à la racine,
ne rejoue aucun score et n'infère pas un verdict depuis REJECTED. Un prix d'entrée
packet n'est pas result.prix : validation du prix de l'observation sans record
reste UNKNOWN. ELIGIBLE_WITHOUT_OBSERVED_RECORD signifie filtres identifiables
satisfaits, pas preuve de validité complète du record ni attente certifiée d'écriture.

Chaque exclusion est une preuve sémantique conditionnelle au contrat source
audité ; l'epoch runtime reste UNVERIFIED. Une provenance invalide est possible
en source, mais non démontrable pour un packet absent de la chaîne capturée.
Aucune valeur synthétique ne remplace ces lacunes.

Le boundary d'exécution Advisor (#406, lignes 6632–6705) réévalue le packet
et force r.trade_allowed=False lorsqu'il n'est pas exécutable, notamment pour
REJECTED. Cette règle explique une voie supplémentaire de refus avant publication.
Elle ne rend pas la publication obligatoire : retours précoces et interruptions
peuvent toujours la précéder. D1-C ne transforme pas cette voie possible en
champ observé : sans la transition native pipeline_g8d explicite, le verdict
legacy reste UNKNOWN pour la classification candidate. Ce choix conservateur
est falsifiable et pourra être affiné avec une preuve de boundary producteur.
