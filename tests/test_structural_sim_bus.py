"""
Garde-fou structurel : SimEventBus ne doit jamais être importé dans le runtime live.

Périmètre runtime interdit : quant_hedge_ai/, supervision/, pieuvre/,
infra/, core/, advisor_loop.py, et tout module sous event_bus/.

Périmètre autorisé : src/ (stack simulation), tests/.
"""

import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent

_FORBIDDEN_DIRS = [
    "quant_hedge_ai",
    "supervision",
    "pieuvre",
    "infra",
    "core",
    "event_bus",
]

_PATTERN = re.compile(r"from\s+src\.events\.event_bus|import\s+src\.events\.event_bus")


def _runtime_py_files():
    for d in _FORBIDDEN_DIRS:
        base = _ROOT / d
        if base.exists():
            yield from base.rglob("*.py")
    for f in _ROOT.glob("*.py"):
        yield f


def test_sim_bus_not_imported_in_runtime():
    violations = []
    for path in _runtime_py_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _PATTERN.search(text):
            violations.append(str(path.relative_to(_ROOT)))

    assert (
        violations == []
    ), "SimEventBus importé dans le runtime live (interdit) :\n" + "\n".join(
        f"  {v}" for v in violations
    )
