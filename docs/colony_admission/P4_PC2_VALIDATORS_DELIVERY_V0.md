# PC2/p1 — validateurs internes (C8.3)

SOURCE_ONLY / LAB_ONLY / NO_ACTIVATION / NO_AUTHORITY.
Base : `main@9ba33a0abed8c30c5b7a8bd133e4662bb9efa0bd` (#510 fusionnée, arbre `478ec761`).
Contrat : [amendement PC2 r2](P4_PC2_NATIVE_EVIDENCE_AMENDMENT_V0.md), adopté par Mathieu
(option O1) sur `2bf7f663`. Cette livraison remplit C8.3 seulement ; C0.3(c) n'est pas
rempli tant que C8.4 n'est pas livrée.

## Ce qui est livré

`colony_admission/_pc2_profile.py`, module privé et pur (aucune IO, aucun import de
`colony_pilot`) :

- `select(q, s)` : étapes 2 à 5 de C10.2, sur `q.criteria_sha256` et `s.scope` seuls.
- `bindings(...)` : toutes les comparaisons C2–C6 du profil
  `pilot-p1-pc2-present-native-v0` sur des bytes et des digests déjà acquis : cinq pins
  raw (C2), fermetures S/P/E liées chacune à son pin, aux claims de q, s, PC2, C9, R8Q
  et au recalcul (C3), champs fermés de q et de s (C4.1, C4.7), contexte de lignée
  Sentinel/pilote vérifié A1 puis comparé par bytes canoniques (C5), bindings natifs
  P1C/PC2/R8Q/C9 et 28×2 essais (C6).
- Codes : C13.3 pour le fait scientifique. Une entrée absente donne
  NE/`SCIENTIFIC_SOURCE_UNAVAILABLE` seulement si aucune comparaison exécutable n'est
  un FAIL prouvé (C13.1).

Aucun lecteur ne l'appelle : `_attestation_statement.scientific_bindings` et les
projections 3B/3C rendent toujours `SCIENTIFIC_PROFILE_UNSUPPORTED`/NE pour p1 (C8.6).
`statement()` est inchangé (C10.2 point 1). Seul test existant modifié :
`test_oplog.py::test_purity_imports_and_no_external_calls`, dont la liste d'imports
permis reçoit le nouveau module (`colony_lab`, `a1_identity`, `_attestation_core`,
`_attestation_statement`), sans autre assouplissement. Les fermetures S/E/P ne sont pas encore
acquises par `_attestation_checkout` : c'est C8.4, comme la mise à jour relue de
3B §9.2 et 3C §13 (C15.5).

## Tests

`tests/colony_admission/test_pc2_profile.py`. Artefacts épinglés = fichiers réels du
checkout. q, statements, enveloppes, émetteur `fixture-pc2-present-issuer` et clés sont
des fixtures LAB_TEST synthétiques : ils ne qualifient rien et n'imitent aucune
identité humaine ou GitHub. Les mutations d'un artefact épinglé sont testées deux fois :
refus au pin raw par le module réel, puis refus par la garde sémantique elle-même dans
une copie en mémoire du module dont les pins sont instrumentés. Seize mutants des
liaisons S/E/P (retrait de chaque claim, du digest recalculé, substitution du pin)
doivent chacun être tués par au moins un scénario.

Le tableau ci-dessous classe chacun des 80 cas, dans l'ordre de la matrice ; un test
vérifie qu'il correspond aux décorateurs `case(...)` du fichier de tests. Un cas classé
ici n'est pas un cas exécuté : le résultat d'une exécution est une preuve hors arbre,
liée à un HEAD exact (commentaire de PR). La matrice reste
`SPECIFICATION_ONLY_NOT_EXECUTED` et n'est pas modifiée.

| ID | Statut | Clauses | Tests | Note |
|---|---|---|---|---|
| PC2-01 | IMPLEMENTED_C8_3 | C0.1, C1.1, C1.4, C8.6, C15.1 | `test_public_readers_keep_the_refusal_until_integration` |  |
| PC2-02 | IMPLEMENTED_C8_3 | C1.2, C2.2, C3.2, C3.3, C3.4, C4.1, C4.7, C4.9, C5.3, C6.1, C6.2, C6.3, C6.4, C6.5, C6.6, C14.1 | `test_exact_lab_test_world_passes_only_its_comparisons` |  |
| PC2-03 | IMPLEMENTED_C8_3 | C2.2, C2.4, C10.2 | `test_pc1_p0_and_alternative_paths_never_select_or_pass` |  |
| PC2-04 | IMPLEMENTED_C8_3 | C2.1, C2.4, C2.5, C10.4 | `test_raw_pin_refuses_reencoding_and_self_consistent_forgeries` |  |
| PC2-05 | IMPLEMENTED_C8_3 | C2.1, C2.2, C4.8, C6.7 | `test_native_bindings_hold_behind_instrumented_pins`, `test_raw_pin_refuses_reencoding_and_self_consistent_forgeries` |  |
| PC2-06 | IMPLEMENTED_C8_3 | C3.2, C3.3, C3.5 | `test_every_s_e_p_binding_mutant_is_killed`, `test_no_permutation_or_substitution_of_closures` |  |
| PC2-07 | IMPLEMENTED_C8_3 | C3.3, C3.4, C3.5 | `test_every_s_e_p_binding_mutant_is_killed`, `test_no_permutation_or_substitution_of_closures` |  |
| PC2-08 | IMPLEMENTED_C8_3 | C3.4 | `test_each_recomputed_closure_is_bound_and_rechecked_per_call`, `test_every_s_e_p_binding_mutant_is_killed` |  |
| PC2-09 | IMPLEMENTED_C8_3 | C3.2, C3.3, C3.6 | `test_each_recomputed_closure_is_bound_and_rechecked_per_call`, `test_every_s_e_p_binding_mutant_is_killed` |  |
| PC2-10 | DEFERRED_C8_4 | C3.1, C7.4 | — | Acquisition, limites, agrégats ou items figés |
| PC2-11 | DEFERRED_C8_4 | C3.1, C7.4 | — | Acquisition, limites, agrégats ou items figés |
| PC2-12 | DEFERRED_C8_4 | C3.1, C7.4, C13.0 | — | Acquisition, limites, agrégats ou items figés |
| PC2-13 | IMPLEMENTED_C8_3 | C4.1, C4.7 | `test_subject_is_exactly_the_native_pilot` |  |
| PC2-14 | IMPLEMENTED_C8_3 | C4.1, C5.7 | `test_subject_is_exactly_the_native_pilot` |  |
| PC2-15 | IMPLEMENTED_C8_3 | C2.1, C4.1, C4.7 | `test_fake_evidence_hash_in_both_q_and_statement` |  |
| PC2-16 | IMPLEMENTED_C8_3 | C1.3, C4.7 | `test_only_native_pc2_is_the_historical_record` |  |
| PC2-17 | IMPLEMENTED_C8_3 | C1.3, C16.1 | `test_exact_lab_test_world_passes_only_its_comparisons` |  |
| PC2-18 | PARTIAL_C8_3 | C4.9, C13.0 | `test_missing_or_swapped_present_envelopes` | Reste : agrégat 3B ATTESTATION_MISSING (C8.4) |
| PC2-19 | IMPLEMENTED_C8_3 | C4.9, C11.1 | `test_one_author_and_one_root_version_for_both_records` |  |
| PC2-20 | PARTIAL_C8_3 | C4.6, C11.2 | `test_historical_reviewer_and_branch_prefixes_are_excluded` | Reste : exclusion de tous les foyers 3C (C8.4) |
| PC2-21 | PARTIAL_C8_3 | C4.9, C13.0, C14.2 | `test_forged_and_genuinely_revoked_envelopes_never_pass_trust` | Reste : statut SUSPENDED 3C (C8.4) |
| PC2-22 | IMPLEMENTED_C8_3 | C4.10, C10.2 | `test_fresh_under_p1_is_unsupported_after_its_grammar` |  |
| PC2-23 | IMPLEMENTED_C8_3 | C4.10, C10.2, C13.1 | `test_fresh_under_p1_is_unsupported_after_its_grammar` |  |
| PC2-24 | IMPLEMENTED_C8_3 | C4.7, C16.1 | `test_present_claims_no_campaign_and_no_past_signature` |  |
| PC2-25 | IMPLEMENTED_C8_3 | C1.6, C3.5, C10.1, C10.5, C15.6 | `test_closed_formats_and_strict_decoding` |  |
| PC2-26 | IMPLEMENTED_C8_3 | C4.7, C12.0 | `test_exact_lab_test_world_passes_only_its_comparisons` |  |
| PC2-27 | PARTIAL_C8_3 | C5.1 | `test_absent_context_is_not_evaluated` | Reste : acquisition par le propriétaire, pas de second snapshot (C8.4) |
| PC2-28 | IMPLEMENTED_C8_3 | C5.2 | `test_spec_artifact_hash_is_compared_beyond_a1_identity` |  |
| PC2-29 | IMPLEMENTED_C8_3 | C5.2, C5.3 | `test_pilot_lineage_context_is_exact` |  |
| PC2-30 | IMPLEMENTED_C8_3 | C5.3 | `test_pilot_lineage_context_is_exact`, `test_sentinel_parent_context_is_exact` |  |
| PC2-31 | IMPLEMENTED_C8_3 | C5.3, C5.4 | `test_each_campaign_budget_is_exact_without_coercion` |  |
| PC2-32 | IMPLEMENTED_C8_3 | C5.3, C5.4 | `test_pilot_lineage_context_is_exact` |  |
| PC2-33 | PARTIAL_C8_3 | C5.5 | `test_pc2_q_is_not_the_birth_qualification_of_the_pilot` | Reste : liaison de naissance dans la branche 3B (C8.4) |
| PC2-34 | PARTIAL_C8_3 | C5.5, C5.7, C14.1 | `test_pilot_as_parent_keeps_lineage_layer_and_grants_nothing`, `test_subject_is_exactly_the_native_pilot` | Reste : aucune autorisation de naissance à l'agrégat (C8.4) |
| PC2-35 | PARTIAL_C8_3 | C5.6, C15.4 | `test_qualification_items_keep_full_record_digest` | Reste : toutes les copies exigées par la population 3C (C8.4) |
| PC2-36 | IMPLEMENTED_C8_3 | C6.3 | `test_native_bindings_hold_behind_instrumented_pins` |  |
| PC2-37 | IMPLEMENTED_C8_3 | C6.3, C6.4 | `test_native_bindings_hold_behind_instrumented_pins` |  |
| PC2-38 | IMPLEMENTED_C8_3 | C6.2 | `test_native_bindings_hold_behind_instrumented_pins` |  |
| PC2-39 | IMPLEMENTED_C8_3 | C6.4 | `test_native_bindings_hold_behind_instrumented_pins` |  |
| PC2-40 | IMPLEMENTED_C8_3 | C2.2, C6.1, C6.5 | `test_native_bindings_hold_behind_instrumented_pins` |  |
| PC2-41 | IMPLEMENTED_C8_3 | C6.6 | `test_native_bindings_hold_behind_instrumented_pins` |  |
| PC2-42 | IMPLEMENTED_C8_3 | C6.6, C6.7 | `test_native_bindings_hold_behind_instrumented_pins` |  |
| PC2-43 | DEFERRED_C8_4 | C1.5, C2.3, C7.1, C7.2, C15.2 | — | Acquisition, limites, agrégats ou items figés |
| PC2-44 | DEFERRED_C8_4 | C7.2 | — | Acquisition, limites, agrégats ou items figés |
| PC2-45 | DEFERRED_C8_4 | C7.3 | — | Acquisition, limites, agrégats ou items figés |
| PC2-46 | DEFERRED_C8_4 | C7.4 | — | Acquisition, limites, agrégats ou items figés |
| PC2-47 | DEFERRED_C8_4 | C7.3 | — | Acquisition, limites, agrégats ou items figés |
| PC2-48 | DEFERRED_C8_4 | C0.2, C7.5, C14.2 | — | Acquisition, limites, agrégats ou items figés |
| PC2-49 | IMPLEMENTED_C8_3 | C8.5, C9.3, C11.4 | `test_public_readers_keep_the_refusal_until_integration` |  |
| PC2-50 | PARTIAL_C8_3 | C8.4, C9.1, C9.2 | `test_current_checkout_closures_equal_the_three_pins`, `test_p1_scenarios_g0_and_matrix_bytes_unchanged` | Reste : suites normales et -O : preuve d'exécution hors arbre (PR) |
| PC2-51 | REVIEW_GATE | C8.1, C8.2, C8.3 | — | Contrôle de revue/gate, pas un test |
| PC2-52 | IMPLEMENTED_C8_3 | C0.3, C8.6, C9.4, C14.0 | `test_public_readers_keep_the_refusal_until_integration` |  |
| PC2-53 | PARTIAL_C8_3 | C4.3, C4.4, C4.5, C16.3 | `test_outputs_never_claim_review_qualification_or_provenance` | Reste : porte SR hors scanner, non tranchée (Q2) |
| PC2-54 | IMPLEMENTED_C8_3 | C5.3, C10.5 | `test_each_campaign_budget_is_exact_without_coercion`, `test_pilot_lineage_context_is_exact`, `test_sentinel_parent_context_is_exact` |  |
| PC2-55 | REVIEW_GATE | C0.3, C8.1 | — | Contrôle de revue/gate, pas un test |
| PC2-56 | PARTIAL_C8_3 | C0.4, C9.1 | `test_p1_scenarios_g0_and_matrix_bytes_unchanged` | Reste : contrôle de revue à chaque PR |
| PC2-57 | IMPLEMENTED_C8_3 | C10.2, C4.7 | `test_only_native_pc2_is_the_historical_record` |  |
| PC2-58 | IMPLEMENTED_C8_3 | C10.2, C4.7 | `test_selection_reads_q_criteria_and_statement_must_equal_it` |  |
| PC2-59 | IMPLEMENTED_C8_3 | C10.3 | `test_a_later_profile_version_re_evaluates_without_writing` |  |
| PC2-60 | IMPLEMENTED_C8_3 | C10.4, C4.7, C13.3 | `test_only_canonical_h_of_q_is_admitted` |  |
| PC2-61 | IMPLEMENTED_C8_3 | C10.5, C13.3 | `test_closed_formats_and_strict_decoding` |  |
| PC2-62 | IMPLEMENTED_C8_3 | C11.1 | `test_one_author_and_one_root_version_for_both_records` |  |
| PC2-63 | PARTIAL_C8_3 | C11.0, C11.1, C4.9 | `test_issuer_needs_both_kinds_in_the_current_lab_test_root` | Reste : pas de PASS de branche (C8.4) |
| PC2-64 | PARTIAL_C8_3 | C11.2, C13.3 | `test_historical_reviewer_and_branch_prefixes_are_excluded` | Reste : autres foyers inventoriés 3C (C8.4) |
| PC2-65 | PARTIAL_C8_3 | C11.3, C4.4, C4.6 | `test_outputs_never_claim_review_qualification_or_provenance` | Reste : dossier SR hors scanner |
| PC2-66 | PARTIAL_C8_3 | C11.4, C13.0, C13.3 | `test_issuer_needs_both_kinds_in_the_current_lab_test_root` | Reste : pas de PASS de branche (C8.4) |
| PC2-67 | DEFERRED_C8_4 | C12.1, C16.2 | — | Acquisition, limites, agrégats ou items figés |
| PC2-68 | IMPLEMENTED_C8_3 | C12.0 | `test_declared_environment_is_never_compared` |  |
| PC2-69 | DEFERRED_C8_4 | C13.0, C13.1 | — | Acquisition, limites, agrégats ou items figés |
| PC2-70 | PARTIAL_C8_3 | C3.6, C12.2, C13.0, C13.2 | `test_each_recomputed_closure_is_bound_and_rechecked_per_call` | Reste : modification réelle d'un fichier acquis (C8.4) |
| PC2-71 | PARTIAL_C8_3 | C13.2 | `test_zero_writes_on_fail_ne_and_pass` | Reste : appels d'acquisition (C8.4) |
| PC2-72 | DEFERRED_C8_4 | C14.0, C9.4 | — | Acquisition, limites, agrégats ou items figés |
| PC2-73 | PARTIAL_C8_3 | C14.3 | `test_p1_scenarios_g0_and_matrix_bytes_unchanged` | Reste : comparaison avant/après chaque PR (revue) |
| PC2-74 | PARTIAL_C8_3 | C15.2 | `test_r8_profile_selection_and_reader_unchanged` | Reste : rejeu R8 avant/après intégration (C8.4) |
| PC2-75 | IMPLEMENTED_C8_3 | C15.3, C10.2 | `test_pc1_p0_and_alternative_paths_never_select_or_pass` |  |
| PC2-76 | REVIEW_GATE | C15.5 | — | Contrôle de revue/gate, pas un test |
| PC2-77 | IMPLEMENTED_C8_3 | C16.1 | `test_present_claims_no_campaign_and_no_past_signature` |  |
| PC2-78 | IMPLEMENTED_C8_3 | C16.3, C4.4 | `test_exact_lab_test_world_passes_only_its_comparisons` |  |
| PC2-79 | IMPLEMENTED_C8_3 | C13.0, C13.3, C4.2 | `test_a_signed_unqualified_state_is_never_pass` |  |
| PC2-80 | PARTIAL_C8_3 | C13.4, C12.2, C5.6 | `test_forged_and_genuinely_revoked_envelopes_never_pass_trust`, `test_qualification_items_keep_full_record_digest` | Reste : comptage conservateur 3C (C8.4) |

Statuts : `IMPLEMENTED_C8_3` = couche validateur couverte ; `PARTIAL_C8_3` = couche
validateur couverte, le reste (note) est dû par C8.4, la revue ou une porte externe ;
`DEFERRED_C8_4` = acquisition, limites, agrégats ou items figés, aucun test ici ;
`REVIEW_GATE` = contrôle documentaire de revue, pas un test.

## Toujours bloquant

PC2/p1 reste `SCIENTIFIC_PROFILE_UNSUPPORTED`/NE bloquant dans tous les lecteurs ; p1
reste dans g0. Même après C8.4, une attestation réelle exige une revue SR (C4.3), un
émetteur identifié et autorisé, et ses deux enveloppes valides (C8.5) ; aucune n'est
créée ici. Q2 (revue d'agent comme SR) n'est pas tranchée. La revue d'agent de cette
PR vérifie la conformité du code au contrat ; elle n'est ni revue scientifique, ni
signature, ni approbation d'identité distincte (C16.3).

P1, scénarios, g0, formats, la matrice PC2 et `colony_lab`/`sentinel_activity`/
`colony_pilot` sont inchangés ; les trois fermetures gardent leurs pins. #286 ACTIVE,
accepted=false. Aucun VPS/runtime/systemd/PPL/FIN/epoch/production/TESTNET/LIVE/
exchange/secret/replay/campagne/naissance/installation trust ou writer opérationnel.
Rollback = revert source.
