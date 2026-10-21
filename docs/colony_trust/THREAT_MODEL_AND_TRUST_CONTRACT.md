# Colony lab record authentication: threat model and trust contract (`colony-trust/0`)

Status: **SOURCE_ONLY / LAB_ONLY / LAB_TEST keys only.** This contract was written and pushed before
any authentication code. Nothing here is deployed, wired into `colony_lab.Supervisor`, or able to
accept a non-test trust root. #286 is unaffected.

## 1. What is being protected, and from whom

A colony lab decision (admitting an individual, accepting a parent's qualification before a birth)
currently trusts JSON records found in the lab root:

| Record | Kind | Today |
|---|---|---|
| Individual record (`record.json`) | `colony-lab.individual/0` | Hash-sealed and recomputed against its spec and parent on every load; **not authenticated**: anyone who can write the lab root can write a consistent one. |
| Qualification record (`birth_qualification.json`, `SENTINEL_QUALIFICATION_RECORD_R8.json`) | `colony-lab.qualification/0` | Checked for shape and self-reference; the `reviewer_id` is a **claim**, not a proof that an external reviewer issued it. |
| Admission decision (registrar, separate PR) | `colony-registrar.admission/0` | A declaration by the admitter, shape-checked. |

Adversaries considered:

- **A1, a lab individual**: arbitrary code inside the sandbox. It cannot see the lab root, the
  records, the trust root or any key (sandbox contract, `NURSERY_CONTRACT.md` §3). It can emit
  untrusted output.
- **A2, a writer of the lab root without a signing key**: a buggy tool, a later process, or an
  agent outside the sandbox with file access. It can create, copy, replay, truncate, reorder and
  substitute records and envelopes.
- **A3, a holder of a signing key that is in scope for one kind of record**: e.g. a reviewer key
  trying to sign an individual record, or a key used for another lab.
- **A4, a holder of a retired or compromised key**.

Out of scope (declared limits, §7): the operator account that holds the trust root, all keys and the
code itself; a compromise of the host; the strength of Ed25519 and SHA-256.

## 2. Four separate properties

A verdict reports each property separately; **only all four PASS is acceptance**, and a property that
could not be evaluated is `NOT_EVALUATED`, never PASS.

| Property | Question | Established by | Does a valid signature alone prove it? |
|---|---|---|---|
| **Integrity** | Is this exactly the record the envelope names? | canonical encoding + `record_sha256` equal to the SHA-256 of the canonical record; envelope fields canonical | No: a signature over another hash is still a valid signature. |
| **Authenticity** | Did a key the pinned trust root lists, valid at the declared root version and not revoked, sign this envelope? | Ed25519 over a domain-separated message; trust root pinned by hash and minimum version | Only this one, and only relative to the pinned root. |
| **Authorization** | Is this issuer allowed to make *this* statement, for *this* lab and subject? | issuer scope covers the record kind; `lab_id`, record kind, subject and purpose equal to what the caller is deciding; the record's declared author equal to the issuer | No: a key for one scope signs any bytes. |
| **Completeness** | Is every attestation the decision needs present, once, and nothing unexpected? | the caller's list of required (kind, subject) pairs | No: a valid single envelope says nothing about the ones that are missing. |

## 3. Objects

**Trust root** `colony-trust.root/0`, supplied by the caller (never read from the lab root) and pinned
by its SHA-256 and a minimum `root_version` the caller also supplies:

```
root_schema, environment ("LAB_TEST" only), lab_id, root_version (int ≥ 1),
issuers: [{issuer_id, issuer_kind, scopes: [record_kind…],
           keys: [{key_id, public_key, status, introduced_in_root, retired_in_root}]}],
revoked_envelopes: [envelope_id…]
```

- `issuer_kind` ∈ `EXTERNAL_HUMAN`, `EXTERNAL_REVIEW_PROCESS`, `LAB_OPERATOR`; `issuer_id` follows the
  lab reviewer-id grammar. Issuer ids and key ids are unique across the root.
- `public_key` is a raw Ed25519 key (64 hex); `key_id` = SHA-256 of the raw key, recomputed.
- `status` ∈ `ACTIVE`, `RETIRED`, `REVOKED`; `retired_in_root` is set exactly for `RETIRED` and `REVOKED`
  and is > `introduced_in_root`; both are ≤ `root_version`.
- Scopes may only name known record kinds: `colony-lab.individual/0` only for `LAB_OPERATOR`;
  `colony-lab.qualification/0` and `colony-registrar.admission/0` only for the two external kinds
  (a qualification and a birth admission come from outside the lab).
- Any other environment than `LAB_TEST` is refused (`TRUST_ROOT_NOT_LAB_TEST`): this code cannot be used
  with a production key until a separate, explicitly authorized gate.

**Envelope** `colony-trust.envelope/0`, stored next to the record it attests:

```
envelope_schema, envelope_id (64 hex, chosen by the issuer), lab_id, root_version, issuer_id, key_id,
record_kind, record_sha256, subject: {agent_id, agent_spec_id}, purpose, signature (128 hex)
```

Signed message: `b"colony-trust.envelope/0\x00" + canonical(envelope without "signature")`, canonical
being the lab's J01 canonical encoding. `purpose` ∈ `QUALIFICATION_ATTESTED`, `INDIVIDUAL_ADMITTED`,
`BIRTH_ADMITTED`, bound to its record kind. The subject is read from the record (`agent_id`,
`agent_spec_id`; for an admission `child_agent_id`, `child_agent_spec_id`).

## 4. Verification order and refusal codes

Unknown, invalid and unauthenticated inputs are refused explicitly; nothing defaults to accepted.

1. **Trust root** (authenticity): `TRUST_ROOT_INVALID` (shape, duplicates, recomputed key ids, status
   coherence), `TRUST_ROOT_NOT_LAB_TEST`, `TRUST_ROOT_PIN_MISMATCH` (SHA-256 ≠ pinned),
   `TRUST_ROOT_ROLLBACK` (version < pinned minimum), `TRUST_ROOT_OTHER_LAB`.
2. **Envelope shape**: no envelope → `NOT_AUTHENTICATED`; `UNKNOWN_ENVELOPE_SCHEMA`, `ENVELOPE_INVALID`
   (fields, types, hex, canonical), `UNKNOWN_RECORD_KIND`.
3. **Integrity**: `RECORD_NOT_CANONICAL`, `RECORD_HASH_MISMATCH`.
4. **Authenticity**: `UNKNOWN_ISSUER`, `UNKNOWN_KEY` (key not the issuer's), `ENVELOPE_FROM_FUTURE_ROOT`
   (root_version > the root's), `KEY_NOT_YET_VALID`, `KEY_RETIRED` (declared root version ≥ retirement),
   `KEY_REVOKED` (always, whatever the declared version), `SIGNATURE_INVALID`, `ENVELOPE_REVOKED`.
5. **Authorization**: `AUDIENCE_MISMATCH` (lab_id ≠ the caller's lab), `RECORD_KIND_MISMATCH` (≠ the
   kind the caller decides on), `PURPOSE_MISMATCH`, `SCOPE_NOT_GRANTED`, `SUBJECT_MISMATCH` (envelope
   subject ≠ record subject ≠ caller's subject), `AUTHOR_NOT_ISSUER` (the record's declared author,
   `reviewer_kind`/`reviewer_id` or `admitter_kind`/`admitter_id`, is not the issuer).
6. **Replay of single-use envelopes** (authorization): `BIRTH_ADMITTED` envelopes are consumed in an
   append-only ledger; the same envelope again → `ENVELOPE_REPLAYED`; the same `envelope_id` with other
   content → `ENVELOPE_ID_REUSED`. Durable attestations (qualification, individual) are re-verified on
   every load by design; using them in another context is refused by the bindings of step 5.
7. **Completeness** (bundle): `ATTESTATION_MISSING`, `ATTESTATION_DUPLICATED`, `ATTESTATION_UNEXPECTED`.

Each failure fails its property; the other properties are still evaluated where their inputs are
valid, so a verdict shows, for instance, a record that is intact and authentic but not authorized.
A single envelope can at most be **attested** (integrity, authenticity and authorization PASS); only a
bundle verification, which also evaluates completeness, can **accept** a decision.

## 5. Replay, substitution, versions, revocation, rotation

- **Substitution** of the record: the signature covers `record_sha256`, its kind and its subject.
- **Substitution** of the envelope onto another record, lab or agent: refused by the bindings.
- **Cross-scope use** of a key (A3): scope check; a reviewer key cannot admit an individual.
- **Replay** in another lab: `lab_id`; of a birth admission: the consumption ledger.
- **Versions**: unknown schema versions are refused; the trust root carries a monotonic `root_version`;
  the caller pins its hash and a minimum version, so an older root cannot be substituted.
- **Rotation**: a new root version adds the new key `ACTIVE` and marks the old one `RETIRED` with
  `retired_in_root = N`; envelopes declaring a root version < N still verify with it.
- **Revocation**: `REVOKED` keys verify nothing, whatever the declared version; individual envelopes
  are revoked by id. A qualification's own `REVOKED` state stays a record-level fact, separate.

## 6. No retroactive authentication

Every record that exists today (Sentinel's R8 record, the pilot's evidence, lab records written so far)
is **UNAUTHENTICATED** and stays so: the verifier reports `NOT_AUTHENTICATED` for a record without an
envelope. This change creates no envelope for any existing record and no key outside the tests. An
envelope issued later over an old record would be a new statement made under its own root version,
not proof that the old record was authentic when it was written.

## 7. Limits (NOT PROVEN)

- The trust root, all signing keys and the code are held by the operator account; whoever controls it
  controls authentication. The pin protects against substitution of the root by a lab-root writer,
  not against the operator.
- There is no trusted clock: `RETIRED` relies on the declared root version, which a holder of the
  retired key can backdate. Only `REVOKED` stops a compromised key.
- The consumption ledger lives in the lab root: a writer of the lab root can truncate it and replay a
  birth admission. A replay is still bounded by the other gates (identity uniqueness: a second birth of
  the same child is `ALREADY_ADMITTED`).
- `colony_lab.Supervisor` does not call this verifier: wiring it in changes Sentinel's evaluator code
  hash, so it needs Sentinel's requalification under a separate gate. Until then authentication is an
  extra gate callers use, not a property of the lab.
- Test keys are derived from public labels in `tests/colony_trust`: they authenticate nothing outside
  the tests by construction.
