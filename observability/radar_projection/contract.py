"""radar-projection/1.0.0 — constants of the S4-a contract.

Prose: ``docs/contracts/CAT_S4A_CONTRAT_PROJECTION_RADAR.md``.

The supported source versions are written here as literals on purpose: they are
NOT read from the Radar engine. If the engine moves to a new version, the
verifier keeps refusing the new exports until this contract is deliberately
revised (a test pins the equality with the engine constants of today).
"""
from __future__ import annotations

PROJECTION_SCHEMA = "radar-projection/1.0.0"

# ---------------------------------------------------------------- supported source
EVALUATION_SCHEMA = "radar-evaluation/1.2.0"
RULES_VERSION = "radar-rules/1.2.0"
RANKING_VERSION = "radar-ranking/1.3.0"
SUPPORTED_SOURCE = (EVALUATION_SCHEMA, RULES_VERSION, RANKING_VERSION)
# Former engines (D-R1 archive, D-P2): refused with PRE_RREF_EVALUATION, never projected.
PRE_RREF_SCHEMAS = ("radar-evaluation/1.0.0", "radar-evaluation/1.1.0")

# Dataset schemas an evaluation 1.2.0 may cite (fixture R0, batch R1-B).
FIXTURE_SCHEMA = "radar-fixture/1.0.0"
BATCH_SCHEMA = "radar-batch/1.0.0"
ADAPTER_VERSION = "radar-adapter/1.0.0"

# ---------------------------------------------------------------- bounds
# The engine refuses an evaluation larger than max_output_bytes (1 000 000, profile
# TEST_FIXTURES); the CLI export appends one newline. Checked before any parsing.
MAX_EXPORT_BYTES = 1_000_001
MAX_MARKETS = 5_000          # = radar_selection MAX_FIXTURE_RECORDS
MAX_LIST = 5_000             # any other list of the export
MAX_TEXT = 4_096
# S4A-RV-04: a version string is bounded BEFORE any numeric conversion, and a refusal
# message never carries more than this many characters of input after its code.
MAX_SCHEMA_CHARS = 64
MAX_VERSION_DIGITS = 6
MAX_REFUSAL_DETAIL = 120

# ---------------------------------------------------------------- evidence (E3, Phase D)
# S4-a projects SYNTHETIC evaluations only. HISTORICAL exists in radar-batch/1.0.0 but
# is not supported here; LIVE does not exist in the Radar and is always refused.
PROJECTED_EVIDENCE = ("SYNTHETIC",)
EVIDENCE_REFUSALS = {"HISTORICAL": "EVIDENCE_HISTORICAL_NOT_SUPPORTED",
                     "LIVE": "EVIDENCE_LIVE_REFUSED"}
# Evidence a dataset schema may carry at all (engine contract).
SCHEMA_EVIDENCE = {FIXTURE_SCHEMA: ("SYNTHETIC",), BATCH_SCHEMA: ("SYNTHETIC", "HISTORICAL")}

# ---------------------------------------------------------------- authority invariants
ADMISSION = "NONE"
AUTHORITY = {"execution_authority": False, "collection_authority": False,
             "experiment_authority": False, "proposal_status": "PROPOSED_NOT_AUTHORIZED"}
MODE_DISABLED = {"network": "DISABLED", "l2_collection": "DISABLED", "paper": "DISABLED",
                 "deep_observation": "DISABLED"}
CANDIDATE_STATUS = "PROPOSED_NOT_AUTHORIZED"
PRODUCTION_BUDGETS_STATUS = "NOT_MEASURED"
BUDGET_LIMIT_KEYS = ("max_instruments_per_cycle", "max_observation_bytes", "max_samples_per_observation",
                     "max_input_bytes", "max_kept_evaluations", "max_memory_bytes", "max_cycle_ms",
                     "max_output_bytes")

# ---------------------------------------------------------------- vocabulary of radar-rules/1.2.0
ADMISSIBLE, TO_QUALIFY, NON_ADMISSIBLE, UNKNOWN = "ADMISSIBLE", "A_QUALIFIER", "NON_ADMISSIBLE", "UNKNOWN"
DECISIONS = (ADMISSIBLE, TO_QUALIFY, NON_ADMISSIBLE, UNKNOWN)
DECISION_SEVERITY = {NON_ADMISSIBLE: 3, UNKNOWN: 2, TO_QUALIFY: 1, ADMISSIBLE: 0}
CRITERIA = ("l2_quality", "continuity", "spread_depth", "activity_volatility", "collection_cost", "diversity")
CRITERION_STATES = ("AVAILABLE", "PARTIAL", "UNKNOWN", "INVALID")
MISSIONS = {"PRICE_STUDY": (False, False), "DEEP_OBSERVATION": (True, False), "L2_DEPTH_STUDY": (True, True)}
MAX_REASON_CODES = 16
RECENT_DATA = ("FRESH", "STALE", "ABSENT", "UNKNOWN")
SOURCE_ACCESS = ("ACCESSIBLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN")
CATALOGUE_LIFECYCLES = ("LISTED", "RETIRED", "SOURCE_NOT_CURRENT")
CHANGES = ("BASELINE", "ADDED", "UNCHANGED", "METADATA_CHANGED", "RETIRED", "SOURCE_NOT_CURRENT")
VENUES = ("kraken", "mexc")
MARKET_TYPES = ("SPOT", "PERPETUAL")
SCANNER_MARKETS = {"MEXC_SPOT": ("mexc", "SPOT"), "MEXC_PERPETUAL": ("mexc", "PERPETUAL"),
                   "KRAKEN_SPOT": ("kraken", "SPOT"), "KRAKEN_PERPETUAL": ("kraken", "PERPETUAL")}
TYPE_CODES = {"SPOT": "spot", "LINEAR_PERPETUAL": "perp", "INVERSE_PERPETUAL": "perp-inv",
              "FIXED_MATURITY": "dated", "UNKNOWN": "unknown-contract"}

# ---------------------------------------------------------------- sub-structures (S4A-RV-02)
# Vocabulary of the measures and criteria the engine publishes (radar_selection
# surveillance.py and selection.criteria). Checked as shapes; never recomputed.
TIME_STATES = ("CERTIFIED", "UNCERTIFIED", "INCOHERENT", "UNKNOWN")
CONTINUITY_CLASSES = ("GOOD", "VIABLE", "PARTIAL", "INSUFFICIENT")
FRESHNESS_CLASSES = ("FRESH", "STALE")
L2_STATUSES = ("VERIFIED", "VERIFIED_TOP_N", "TECHNICALLY_COMPATIBLE")
L2_PROOF = {"VERIFIED": "PROVEN", "VERIFIED_TOP_N": "PROVEN_TOP_N", "TECHNICALLY_COMPATIBLE": "TO_QUALIFY"}
# State and reason the engine attaches to each L2 status (surveillance._l2).
L2_STATE = {"VERIFIED": ("AVAILABLE", None),
            "VERIFIED_TOP_N": ("PARTIAL", "L2_VERIFIED_TOP_N_ONLY"),
            "TECHNICALLY_COMPATIBLE": ("PARTIAL", "L2_TO_QUALIFY_AFTER_AUTHORIZATION")}
L2_VERIFIERS = ("KRAKEN_CRC32",)
MAX_EXCLUDED_INSTANTS = 256
PRICE_KINDS = ("LAST_TRADE", "MID_BBO", "MARK")
ACTIVITY_KINDS = ("TRADE_COUNT_WINDOW",)
COST_BASES = ("MEASURED", "ESTIMATED")
COST_FIELDS = ("network_kib_s", "cpu_pct", "memory_mib", "storage_mib_h", "connections")
CANDIDATE_COST_FIELDS = ("state", "basis", "provenance", "network_kib_s", "storage_mib_h", "connections")
REGIMES = ("CALM", "ACTIVE", "VOLATILE")
FUTURE_TOLERANCE_MS = 5_000

# ---------------------------------------------------------------- vocabulary of radar-ranking/1.3.0
WEIGHTS = {"continuity": 30, "spread": 25, "activity": 20, "l2": 15, "cost": 10}
MAX_CANDIDATES = 3
SELECTION_RULES = ("REGIME_SLOT", "BASE_DIVERSITY", "SCORE")
SCORE_QUALITIES = ("COMPLETE", "INCOMPLETE")
EMPTY_REASONS = ("NO_ADMISSIBLE_MARKET_FOR_MISSION", "ADMISSIBLE_MARKETS_ALL_EXCLUDED")

# ---------------------------------------------------------------- integrity statement
# The seal (evaluation_sha256) proves that the content is the one that was sealed.
# It does not prove WHO produced it: anyone can recompute a SHA-256. Authenticity of
# the producer needs a signature or a trusted channel, out of S4-a.
INTEGRITY = {"seal": "VERIFIED", "proves": "CONTENT_INTEGRITY", "producer_authenticity": "NOT_PROVEN"}
# Meaning of a valid projection. It is never an admission nor a runtime authorization.
PROJECTION_STATUS = "PRESENTATION_ONLY_NOT_AN_ADMISSION_NOT_A_RUNTIME_AUTHORIZATION"
# E1: radar-evaluation/1.2.0 does not carry the Scanner universe digest.
SCANNER_UNIVERSE_STATE = "NOT_AVAILABLE"
SCANNER_UNIVERSE_REASON = "NOT_CARRIED_BY_RADAR_EVALUATION_1_2_0"

# Checks performed, in order (the projection lists them; each has its refusal codes).
CHECKS = ("SIZE", "UTF8_STRICT_JSON", "VERSIONS", "CANONICAL_FORM", "SEAL", "STRUCTURE",
          "EVIDENCE", "AUTHORITY", "MARKETS", "SCORES", "CANDIDATES", "MANUAL", "COUNTS", "BUDGETS")
