"""
Pieuvre Géante — système de surveillance auto-évolutif.

Usage rapide:
    from pieuvre import PieuvreGigante
    import asyncio

    pieuvre = PieuvreGigante(repo_path=".")
    asyncio.run(pieuvre.run())

Ou via CLI:
    python launch_pieuvre.py
    python launch_pieuvre.py --scan-once
    python launch_pieuvre.py --auto-fix
"""

from pieuvre.brain import BrainState, PieuvreGigante

__version__ = "1.0.0"
__all__ = ["PieuvreGigante", "BrainState"]
