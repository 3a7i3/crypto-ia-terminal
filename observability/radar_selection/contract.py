"""RADAR R0 contract constants: versions, states, rules, weights and budgets.

Source of truth for the prose: ``docs/contracts/CAT_R0_CONTRAT_RADAR.md``.
Every threshold below is an explicit, versioned experimental hypothesis. None
of them is calibrated on real data; changing one changes ``RULES_VERSION`` or
``RANKING_VERSION``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

EVALUATION_SCHEMA = "radar-evaluation/1.1.0"
FIXTURE_SCHEMA = "radar-fixture/1.0.0"
BATCH_SCHEMA = "radar-batch/1.0.0"
ADAPTER_VERSION = "radar-adapter/1.0.0"
PREFERENCES_SCHEMA = "radar-preferences/1.0.0"
HISTORY_SCHEMA = "radar-history/1.0.0"
RULES_VERSION = "radar-rules/1.1.0"
RANKING_VERSION = "radar-ranking/1.2.0"

# A radar-fixture document is offline and synthetic only. Anything else is refused at load time.
EVIDENCE_KINDS = ("SYNTHETIC",)
# A radar-batch document (R1-B) may also carry HISTORICAL evidence: offline input
# derived from sealed artifacts whose fingerprints are verified. LIVE is refused.
# HISTORICAL is never an admission (C2-C / C2-D stay outside the Radar).
BATCH_EVIDENCE_KINDS = ("SYNTHETIC", "HISTORICAL")
ADMISSION = "NONE"
MODE = {"evidence": "SYNTHETIC", "network": "DISABLED", "l2_collection": "DISABLED",
        "paper": "DISABLED", "deep_observation": "DISABLED"}
AUTHORITY = {"execution_authority": False, "collection_authority": False,
             "experiment_authority": False, "proposal_status": "PROPOSED_NOT_AUTHORIZED"}

# ---------------------------------------------------------------- identity
VENUES = ("kraken", "mexc")
MARKET_TYPES = ("SPOT", "PERPETUAL")
# scanner_universe market -> (venue, market type); reused, not redefined.
TYPE_CODES = {"SPOT": "spot", "LINEAR_PERPETUAL": "perp", "INVERSE_PERPETUAL": "perp-inv",
              "FIXED_MATURITY": "dated", "UNKNOWN": "unknown-contract"}

# ---------------------------------------------------------------- states
# Stage 1 decision (per mission).
ADMISSIBLE, TO_QUALIFY, NON_ADMISSIBLE, UNKNOWN = "ADMISSIBLE", "A_QUALIFIER", "NON_ADMISSIBLE", "UNKNOWN"
DECISIONS = (ADMISSIBLE, TO_QUALIFY, NON_ADMISSIBLE, UNKNOWN)
# Severity order used to combine reasons: the worst wins.
DECISION_SEVERITY = {NON_ADMISSIBLE: 3, UNKNOWN: 2, TO_QUALIFY: 1, ADMISSIBLE: 0}

# Criterion states. UNKNOWN is never 0 and never a favourable score.
AVAILABLE, PARTIAL, CRIT_UNKNOWN, INVALID = "AVAILABLE", "PARTIAL", "UNKNOWN", "INVALID"
CRITERION_STATES = (AVAILABLE, PARTIAL, CRIT_UNKNOWN, INVALID)
CRITERIA = ("l2_quality", "continuity", "spread_depth", "activity_volatility",
            "collection_cost", "diversity")

# Catalogue lifecycle of one market.
LISTED, RETIRED, SOURCE_NOT_CURRENT = "LISTED", "RETIRED", "SOURCE_NOT_CURRENT"
CHANGES = ("BASELINE", "ADDED", "UNCHANGED", "METADATA_CHANGED", "RETIRED", "SOURCE_NOT_CURRENT")
SOURCE_ACCESS = ("ACCESSIBLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN")
RECENT_DATA = ("FRESH", "STALE", "ABSENT", "UNKNOWN")
# VERIFIED: the whole book is verified. VERIFIED_TOP_N (R1-B, operator D3): only the
# first ``depth_levels`` levels are attested by a native checksum, on valid instants
# only; ``depth_levels`` and ``scope`` are mandatory. TECHNICALLY_COMPATIBLE: rebuilt
# book without checksum.
L2_STATUSES = ("VERIFIED", "VERIFIED_TOP_N", "TECHNICALLY_COMPATIBLE")
# radar-fixture/1.0.0 keeps its original L2 vocabulary (no scope field).
FIXTURE_L2_STATUSES = ("VERIFIED", "TECHNICALLY_COMPATIBLE")
L2_SCOPE_KEYS = {"verified_by", "valid_instants", "grid_instants", "excluded_instants"}
L2_VERIFIERS = ("KRAKEN_CRC32",)
PRICE_KINDS = ("LAST_TRADE", "MID_BBO", "MARK")
ACTIVITY_KINDS = ("TRADE_COUNT_WINDOW",)
COST_BASES = ("MEASURED", "ESTIMATED")
REGIMES = ("CALM", "ACTIVE", "VOLATILE")

# ---------------------------------------------------------------- rules (RULES_VERSION)
# Coverage classes reused from the radar_composite pilots (same numbers, cited):
# FLUX_VIABLE_RATIO (bbo_pilot) 0.95, VIABLE_RATIO / PARTIAL_RATIO (pilot L3) 0.80 / 0.50.
CONTINUITY_GOOD = "0.95"
CONTINUITY_VIABLE = "0.80"
CONTINUITY_PARTIAL = "0.50"
# Same skew tolerance as scanner_universe.FUTURE_TOLERANCE_MS.
FUTURE_TOLERANCE_MS = 5_000
# A series is fresh when its last sample is at most two steps old.
FRESHNESS_STEPS = 2
# Share of covered instants that must carry a BBO for the spread to be AVAILABLE.
BBO_COVERAGE_MIN = "0.80"
# Volatility regime (RMS of step returns, bps). Hypotheses, step-dependent.
VOL_MIN_RETURNS = 10
REGIME_ACTIVE_BPS = "5"
REGIME_VOLATILE_BPS = "20"

# Missions: what a decision ADMISSIBLE means. A market may fit one and not another.
MISSIONS = {
    "PRICE_STUDY": {"needs_bbo": False, "needs_l2_verified": False,
                    "label": "Étude du prix (série de référence et continuité)"},
    "DEEP_OBSERVATION": {"needs_bbo": True, "needs_l2_verified": False,
                         "label": "Candidature à l'observation approfondie (BBO requis, L2 à qualifier)"},
    "L2_DEPTH_STUDY": {"needs_bbo": True, "needs_l2_verified": True,
                       "label": "Étude de la profondeur L2 (carnet vérifié requis)"},
}
DEFAULT_MISSION = "DEEP_OBSERVATION"

# ---------------------------------------------------------------- ranking (RANKING_VERSION)
# Integer points per component; a missing component scores nothing and its
# weight is NOT redistributed, so an unknown input can never raise a score.
WEIGHTS = {"continuity": 30, "spread": 25, "activity": 20, "l2": 15, "cost": 10}
CONTINUITY_POINTS = (("0.95", 100), ("0.80", 60))
SPREAD_POINTS_BPS = (("2", 100), ("5", 80), ("10", 60), ("25", 30))  # else 10
SPREAD_FLOOR_POINTS = 10
ACTIVITY_POINTS = ((1000, 100), (100, 70), (10, 40), (1, 20))  # 0 trades -> 0
# VERIFIED_TOP_N = 40 (operator D4, 2026-11-24): a TRANSITIONAL ranking weight equal to
# TECHNICALLY_COMPATIBLE. It does not state that both states are equally reliable and
# must not be raised without a separate calibration and validation protocol.
L2_POINTS = {"VERIFIED": 100, "VERIFIED_TOP_N": 40, "TECHNICALLY_COMPATIBLE": 40}
COST_POINTS_KIB_S = (("50", 100), ("200", 70), ("1000", 40))  # else 10
COST_FLOOR_POINTS = 10
MAX_CANDIDATES = 3
# Diversity: one candidate per regime first (this order), then by score with a
# different base asset when possible, then by score.
DIVERSITY_ORDER = REGIMES

# ---------------------------------------------------------------- reference
REFERENCE = {"venue": "kraken", "market_type": "SPOT", "base": "BTC", "quote": "USDT",
             "market_id": "kraken:spot:BTC/USDT"}
REFERENCE_HISTORICAL_STATUS = "NOT_YET_HISTORICALLY_ADMITTED"
REFERENCE_NOTE = ("Référence expérimentale conservée hors classement. Aucune admission "
                  "historique n'est établie par le Radar ; elle reste soumise à l'intégrité "
                  "de ses données et aux gates C2-C, C2-D et suivantes.")


# ---------------------------------------------------------------- budgets
@dataclass(frozen=True)
class Budgets:
    """Ceilings of one Radar cycle. Values are test values for the fixtures."""

    max_instruments_per_cycle: int
    max_observation_bytes: int
    max_samples_per_observation: int
    max_input_bytes: int
    max_kept_evaluations: int
    max_memory_bytes: int
    max_cycle_ms: int
    max_output_bytes: int
    future_cycle_interval_s: int | None  # None = not set: to justify by measurement
    profile: str = "TEST_FIXTURES"

    def as_dict(self) -> dict:
        return asdict(self)


TEST_BUDGETS = Budgets(
    max_instruments_per_cycle=200,
    max_observation_bytes=32_768,
    max_samples_per_observation=256,
    max_input_bytes=2_000_000,
    max_kept_evaluations=20,
    max_memory_bytes=64 * 1024 * 1024,
    max_cycle_ms=2_000,
    max_output_bytes=1_000_000,
    future_cycle_interval_s=None,
)
# Production budgets are deliberately absent: no representative benchmark exists.
PRODUCTION_BUDGETS = None
PRODUCTION_BUDGETS_STATUS = "NOT_MEASURED"

# Bounded lists in documents. The input size itself is bounded by max_input_bytes;
# the instrument ceiling bounds the work of a cycle, not the input shape.
MAX_FIXTURE_RECORDS = 5_000

# ---------------------------------------------------------------- batch (R1-B)
# Ceilings of one radar-batch document and of its referenced artifacts.
MAX_BATCH_SOURCES = 16
MAX_REFS = 64                       # catalogue documents + manifests + anchors + windows
# Total bytes of the references one batch may make the CLI read (R1-B memory reserve,
# 2026-11-25). Test capacity, not a production capacity: a batch reading ~1.0 MB of
# dense SYNTHETIC catalogues peaked at ~47 MiB (tracemalloc) for ~3 800 markets, under
# the 64 MiB test memory budget; memory grows with the number of markets, about
# 45 times the bytes read. Checked on declared sizes before reading, then on the
# actual bytes while reading (REFS_BYTES_BOUND).
MAX_BATCH_REF_BYTES = 1_000_000
MAX_ARTIFACT_BYTES = 1_000_000      # one non-catalogue artifact (window, anchor, manifest)
MAX_WINDOWS_PER_OBSERVATION = 8     # 8 x 30 points <= max_samples_per_observation
MAX_EXCLUDED_INSTANTS = 256
UNKNOWN_REASON_KEYS = ("activity", "depth", "cost")
SOURCE_KINDS = ("BBO_REPLAY_WINDOWS",)
MAX_REASON_CODES = 16
MAX_PREF_LOG = 50
