"""Shared sys.path setup for tests/scripts/."""

from __future__ import annotations

import sys
from pathlib import Path

# Rend le projet importable depuis tests/scripts/
_root = str(Path(__file__).parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)
