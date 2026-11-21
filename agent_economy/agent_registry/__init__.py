"""AGENT-ECON A1 SOURCE — Agent Registry pure core.

SOURCE ONLY / NON_DEPLOYED / NO_RUNTIME_AUTHORITY / NO AGENT EXECUTION.

Deterministic identities, AgentSpec and AgentRegistryEvent validation,
append-only hash-chain verification and a pure projection, as defined by the
certified contracts under ``docs/contracts/AGENT_ECON_A*``.

Importing this package defines pure Python objects only: no network, no
subprocess, no environment read, no filesystem access, no thread, no signal
handler, no database. Registrar identity (Q1), anti-rollback anchor (Q2) and
durable registry storage (Q10) stay UNRESOLVED; ``AVAILABLE`` is unreachable.
REGISTERED != RUNNING != AUTHORIZED.
"""

from .canonical import (
    AgentRegistryError,
    canonical_json_bytes,
    publication_json_bytes,
    sha256_hex,
)
from .capabilities import classify_capability_token
from .events import compute_event_hash, compute_event_id, validate_event
from .integrity import ChainVerification, verify_chain
from .projection import RegistryProjection, project_registry
from .publication import PublicationResult, publish_agent_spec
from .spec import (
    SpecIdentities,
    classify_revision,
    compute_agent_id,
    compute_agent_spec_id,
    compute_spec_artifact_hash,
    validate_agent_spec,
)

__all__ = [
    "AgentRegistryError",
    "ChainVerification",
    "PublicationResult",
    "RegistryProjection",
    "SpecIdentities",
    "canonical_json_bytes",
    "classify_capability_token",
    "classify_revision",
    "compute_agent_id",
    "compute_agent_spec_id",
    "compute_event_hash",
    "compute_event_id",
    "compute_spec_artifact_hash",
    "project_registry",
    "publication_json_bytes",
    "publish_agent_spec",
    "sha256_hex",
    "validate_agent_spec",
    "validate_event",
    "verify_chain",
]
