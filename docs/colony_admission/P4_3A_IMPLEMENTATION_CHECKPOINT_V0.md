# 3A implementation checkpoint — physical evidence diagnostic

2026-10-25. SOURCE_ONLY / LAB_ONLY. Contract baseline: merged #503,
`main@7a8b5a21fd263872cd0c0f7897812ca603f86d61`, reviewed tree
`f333e0e38bd0f0b77db92429865f312296744062`.
The contract's NO_IMPLEMENTATION status describes its publication checkpoint; this separate
slice implements that reviewed diagnostic without changing P1 or the frozen contract/matrix.

## Behavior and limits

`FileObserver.scan_evidence()` adds a separate immutable result. One L1 acquisition inventories
and validates every bounded log; validated whole-file prefixes preserve historical positions,
reserve rules and acknowledged CR fragments. Every supported historical/current operation is
requested in one sorted FD ledger read. The 256-operation cap is independent of the 256-log cap;
252 item references is a diagnostic cap, not a policy-specific required-list verdict.

D1 separates frozen consumption hashes from available envelope identities. Latest-only D2
uses strict bounded JSON/canonical identities in the child's storage namespace with parent
qualification/statement subjects. D3 uses the existing writer's exact UTF-8/indent/LF bytes;
completed or recovered-present D3 excludes mutable usage content. Layout observes private
root directories and journal metadata, never SQLite content or task/result contents.

Repeated listings and no-follow absence checks are retained until final verification and
successful closes. Read/stat ENOENT is a failure, never file absence. Content paths are acquired
once even when also checked as metadata. Acquisition/foundational/limit errors discard all
rows, counts, stamps and batch bytes. Cross-check contradictions retain diagnostic facts only.
All authority fields stay NOT_EVALUATED and accepted stays false. Existing observe/scan/FD
outputs remain unchanged. The shared file-descriptor metadata check is factored without
changing its checks; the purity guard explicitly names both IO boundaries and continues to
reject IO imports/calls in comparison/projection modules.

Independent preliminary review found the read-ENOENT defect; it was fixed before publication.
The review also strengthened actual-limit names, visible issuer-root coherence, a duplicate-key
case whose final values match frozen data, and a subject-binding test with rebound digests.
Final exact-tree independent review and CI are recorded in the PR, not inferred from this file.

## Validation and honest boundaries

Real temporary private LAB_TEST fixtures exercise the following matrix, with parameterized
variants and supplementary failure injection. The mapping is navigation, not an assertion
that the prose matrix executes itself. The final test counts/commands and review tree are
recorded in the PR continuity comment after the tree is frozen.

Commands:

```sh
python -m pytest tests/colony_admission tests/colony_trust tests/colony_registrar -q
python -O -m pytest tests/colony_admission/test_physical_evidence.py tests/colony_admission/test_observer_line_boundaries.py tests/colony_trust/test_fd_inspection.py -q
python scripts/ci/ruff_baseline_gate.py check
```

Local Python 3.12.14, UID0. The restored environment uses the existing cached dependency
directory via PYTHONPATH; it lacks pytest-asyncio (asyncio_mode warning) and requests, so the
additional Telegram panel suite could not be collected locally. No pass count is claimed for
that attempted extension. Full repository CI supplies its broader regression run; no complete
local repository run, sandbox campaign or non-root execution is claimed. Overlapping suite
counts must not be added.

P1 SHA256 pins remain e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd
and 4e518bfec6faaa582c2c42633d80e989b8204708b554f74b0eb1bbee6eaa59a1.
Recomputed qualified hashes remain Sentinel2c926421416731dc629915067bcea472729e6785ec8dcb6e28f15ae7b41e4ec8,
evaluator41b78971184809652dd1190dded49ab27d58c35c8a995351a47bf0f85756faa4,
pilot97fb6b0489976f8b003823c1536932ec10a1c7faa699ef6f6eb1bd4056238bc7.
Both code_irregular lists are empty. No qualified package was changed.

## Specification navigation

Tests below are in `tests/colony_admission/test_physical_evidence.py` unless noted.

| Specification | Executable test family |
|---|---|
| ACQ-01 | `test_missing_bound_roots` |
| ACQ-02 | `test_read_failure_is_not_absence` |
| ACQ-03 | `test_unsafe_selected_file` |
| ACQ-04 | `test_unsafe_selected_directory` |
| ACQ-05 | `test_final_changes_discard_everything` |
| ACQ-06 | `test_final_changes_discard_everything` |
| ACQ-07 | `test_close_failure_clears_all` |
| ACQ-08 | `test_io_one_read_no_effects_metadata_only_and_immutable` |
| ACQ-09 | `test_empty_roots_and_ledger_once` |
| ACQ-10 | `test_external_termination_never_skips_neighbor` |
| ACQ-11 | `test_sticky_ledger_fault_preserved` |
| ACQ-12 | `test_busy_lock_no_retry` |
| HIST-01 | `test_history_all_ids_latest_material_only` |
| HIST-02 | `test_history_cap_before_ledger_open` |
| HIST-03 | `test_history_cap_before_ledger_open` |
| HIST-04 | `test_duplicate_not_coalesced` |
| HIST-05 | `test_historical_consumption_not_hidden` |
| HIST-06 | `test_history_all_ids_latest_material_only` |
| HIST-07 | `test_ack_cr_fragment_is_opaque` |
| HIST-08 | `test_original_reserve_positions` |
| HIST-09 | `test_two_pending_births` |
| HIST-10 | `test_set_aside_is_not_pending_birth` |
| LED-01 | `test_ledger_whole_parse_discards_prefix` |
| LED-02 | `test_unbound_ledger_counts` |
| LED-03 | `test_unbound_ledger_counts` |
| LED-04 | `test_unbound_ledger_counts` |
| LED-05 | `test_conflicting_requested_entries_never_match` |
| LED-06 | `test_empty_roots_and_ledger_once` |
| LED-07 | `test_ledger_failures_have_null_counts` |
| D1-01 | `test_d1_phases` |
| D1-02 | `test_d1_phases` |
| D1-03 | `test_d1_phases` |
| D1-04 | `test_foreign_d1_hash` |
| D1-05 | `test_d1_phases` |
| D1-06 | `test_d1_stored_identity_mismatch` |
| D2-01 | `test_d2_interrupted_material` |
| D2-02 | `test_d2_interrupted_material` |
| D2-03 | `test_d2_interrupted_material` |
| D2-04 | `test_completed_d2_requires_each_file` |
| D2-05 | `test_divergent_strict_d2_content` |
| D2-06 | `test_d2_canonical_equality_namespace_paths_no_individual_required` |
| D2-07 | `test_invalid_frozen_admission_bindings` |
| D2-08 | `test_frozen_decision_bindings` |
| D2-09 | `test_d2_canonical_equality_namespace_paths_no_individual_required` |
| D2-10 | `test_d2_canonical_equality_namespace_paths_no_individual_required` |
| D2-11 | `test_d2_canonical_equality_namespace_paths_no_individual_required` |
| D2-12 | `test_d2_canonical_equality_namespace_paths_no_individual_required` |
| D3-01 | `test_d2_canonical_equality_namespace_paths_no_individual_required` |
| D3-02 | `test_home_phase_and_no_origin_inference` |
| D3-03 | `test_home_phase_and_no_origin_inference` |
| D3-04 | `test_partial_d3_whole_files_only` |
| D3-05 | `test_open_d3_short_or_different_not_partial` |
| D3-06 | `test_home_phase_and_no_origin_inference` |
| D3-07 | `test_io_one_read_no_effects_metadata_only_and_immutable` |
| D3-08 | `test_recovery_present_d3_usage_excluded` |
| D3-09 | `test_completed_d3_requires_identity` |
| D3-10 | `test_unicode_writer_encoding_parity` |
| D3-11 | `test_completed_layout_metadata_required` |
| D3-12 | `test_layout_namespace_safety` |
| D3-13 | `test_terminal_prefix_and_action_retained` |
| D3-14 | `test_all_structural_actions_stay_unevaluated` |
| LIMIT-01 | `test_resource_limits_discard` |
| RESULT-01 | `test_io_one_read_no_effects_metadata_only_and_immutable` |
| RESULT-02 | `test_io_one_read_no_effects_metadata_only_and_immutable` |
| COMPAT-01 | Existing admission/trust/registrar suites; purity guard and ACK/CR retained |
| D2-13 | `test_foreign_qualification_subject` |

Supplementary tests cover semantically-equal duplicate keys, explicit statement issuer versions,
metadata ENOENT, absent completed usage, 252/253 references, separate 256/257 logs, log aggregate
limits, and filename/lab binding before ledger acquisition. Old suites cover the unchanged
parser/observer/trust/registrar contracts.

## Acceptance and rollback

Before merge: final exact-tree independent review, exact-HEAD checks AND workflows, resolved
threads, active protections, main composition and unchanged pins/hashes. Guarded merge only;
then identical merged tree and new-main CI before closure. A ready draft is not a merged proof.
Rollback is source revert only; no data/schema/evidence migration exists.

3A does not close step3. Plans3B (attestations/ancestors) and3C (population/ceilings/correspondences)
remain to be approved before implementation. No controller/recovery/qualification, deployment,
VPS/runtime/systemd/PPL/FIN/epoch/TESTNET/LIVE/secret, Replay or Diagnostic action. #286 ACTIVE.
