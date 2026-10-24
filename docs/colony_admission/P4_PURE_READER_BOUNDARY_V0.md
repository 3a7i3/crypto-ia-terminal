# P4 pure-reader boundary notes, version 0

SOURCE_ONLY. Refines P4_FORMATS_AND_STATE_MACHINE_V0.md without editing P1 pins.

- Subject is exactly {agent_id,agent_spec_id}, two lowercase hex64 strings. Attestation ordering uses (kind, subject.agent_id, subject.agent_spec_id, record_sha256); role does not change the completeness key.
- Pure modules perform lexical validation and bindings visible in supplied bytes. They never import or call colony_lab, colony_trust or colony_registrar. Embedded P3 records/spec/qualification/admission are bounded canonical JSON objects, carried as sealed payloads; their internal schemas, A1 semantics, signatures, policy/capability/budget ceilings and population truth MUST be checked by the later evidence join using existing validators. Pure parsing does not certify these payloads. Own operation/item/entry/plan wrapper formats have closed keys.
- The pure projector recognizes structural claims only. External guards in P4_TRANSITIONS_V0.json cannot be executed here. Recovered PRESENT/PARTIAL must claim a different boot than matching BEGIN; host provenance is NOT_EVALUATED. All results have accepted=false and external_facts=NOT_EVALUATED, including terminal claims.
- On malformed input or an inconsistent sequence, status CORRUPT carries no usable terminal claim or frozen identity. A torn tail may preserve prefix context but is unusable as a successful result. Bytes are never changed.
- Attempt history is retained as immutable summaries, with physical-line positions, operation identity and claimed outcome. No reference to caller-owned mutable objects is returned.
- Integer length counts digits excluding an optional minus sign. Container depth counts the outer object as one. Bounds are checked before parsing; no implicit truncation.
- No writer, filesystem observer, controller orchestration or recovery action is implemented by this slice. It does not complete P4, P5 or P6.

## Projection precision for the later evidence join

The immutable projection additionally exposes `recovery_step` and `recovery_result` (null or the latest outstanding explicit recovery classification), and `last_completed_source` (null, PREPARED, DONE or RECOVERY_PRESENT). ABSENT and PARTIAL must not collapse into an ambiguous RECOVERED status. BEGIN clears the outstanding recovery marker; QUARANTINE_DONE clears the D3 PARTIAL marker. A completed step's source is preserved across later BEGIN/cancellation until another completion. These fields are observations only; no controller guard or action is inferred from them.
