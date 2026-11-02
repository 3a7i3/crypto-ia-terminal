"""CryptoRadar Flux core (#553): exact-arithmetic trades/CVD, L2, heatmap, replay.

SOURCE ONLY / NOT WIRED / SYNTHETIC FIXTURES. Nothing here reads a clock, opens a
connection or is imported by a producer, reader or runtime service. The legacy
float-based ``market_data`` package is intentionally not reused: it assumes USD
amounts, millisecond floats and a default taker side.
"""

CALC_VERSION = "flow-calc-1.0.0"
CONTRACT_VERSION = "1.0.0"
