"""
monitoring/profiler.py — Profilage CPU et memoire (stdlib uniquement).

Utilise cProfile + pstats pour le CPU et tracemalloc pour la memoire.
Genere des rapports JSON-serialisables et Markdown.

Usage :
    profiler = Profiler(top_n=15)
    result, report = profiler.profile(my_function, arg1, arg2)
    report.write_markdown(Path("reports/profiling_2026-05-13.md"))
    print(report.as_dict())

    # Profiler rapidement sans garder le resultat
    _, report = Profiler().profile(walk_forward_engine.run, data)
    print(f"Duration: {report.duration_s:.3f}s  Peak: {report.peak_memory_mb:.1f}MB")
"""

from __future__ import annotations

import cProfile
import io
import pstats
import time
import tracemalloc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Dataclasses de resultat
# ---------------------------------------------------------------------------


@dataclass
class FunctionStat:
    """Stats d'une fonction du profil CPU."""

    function: str  # "fichier:ligne(nom)"
    calls: int
    cumtime_s: float  # temps cumule (incluant sous-appels)
    tottime_s: float  # temps propre (excluant sous-appels)
    percall_s: float  # cumtime / calls


@dataclass
class MemoryAllocation:
    """Plus grosse allocation memoire tracee par tracemalloc."""

    filename: str
    lineno: int
    size_kb: float
    n_blocks: int


@dataclass
class ProfilingReport:
    """
    Rapport complet d'un profilage.

    function_name   : nom de la fonction profilee
    duration_s      : temps d'execution reel (monotonic clock)
    top_functions   : top N fonctions par temps cumule
    peak_memory_mb  : pic memoire en MB (None si profile_memory=False)
    n_allocations   : nombre total d'allocations
    top_allocations : top N allocations par taille
    """

    function_name: str
    duration_s: float
    top_functions: list[FunctionStat]
    peak_memory_mb: Optional[float] = None
    current_memory_mb: Optional[float] = None
    n_allocations: Optional[int] = None
    top_allocations: list[MemoryAllocation] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "function": self.function_name,
            "duration_s": round(self.duration_s, 4),
            "peak_memory_mb": (
                round(self.peak_memory_mb, 3) if self.peak_memory_mb else None
            ),
            "current_memory_mb": (
                round(self.current_memory_mb, 3) if self.current_memory_mb else None
            ),
            "n_allocations": self.n_allocations,
            "top_functions": [
                {
                    "function": f.function,
                    "calls": f.calls,
                    "cumtime_s": round(f.cumtime_s, 6),
                    "tottime_s": round(f.tottime_s, 6),
                    "percall_s": round(f.percall_s, 8),
                }
                for f in self.top_functions
            ],
            "top_allocations": [
                {
                    "filename": a.filename,
                    "lineno": a.lineno,
                    "size_kb": round(a.size_kb, 2),
                    "n_blocks": a.n_blocks,
                }
                for a in self.top_allocations
            ],
        }

    def write_markdown(self, path: Path) -> None:
        """Ecrit le rapport en Markdown dans `path`."""
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# Profiling Report — `{self.function_name}`",
            "",
            "## Synthese",
            "",
            f"| Metrique | Valeur |",
            f"|----------|--------|",
            f"| Duree reelle | {self.duration_s:.3f} s |",
        ]
        if self.peak_memory_mb is not None:
            lines += [
                f"| Pic memoire | {self.peak_memory_mb:.2f} MB |",
                f"| Memoire courante | {self.current_memory_mb:.2f} MB |",
                f"| Allocations | {self.n_allocations:,} |",
            ]
        lines += [
            "",
            "## Top fonctions par temps cumule",
            "",
            "| Fonction | Appels | Cumtime (s) | Tottime (s) | /appel (s) |",
            "|----------|-------:|------------:|------------:|----------:|",
        ]
        for f in self.top_functions:
            # tronquer les noms longs
            fname = f.function if len(f.function) <= 70 else "..." + f.function[-67:]
            lines.append(
                f"| `{fname}` | {f.calls:,} | {f.cumtime_s:.6f}"
                f" | {f.tottime_s:.6f} | {f.percall_s:.8f} |"
            )
        if self.top_allocations:
            lines += [
                "",
                "## Top allocations memoire",
                "",
                "| Fichier:ligne | Taille (KB) | Blocs |",
                "|---------------|------------:|------:|",
            ]
            for a in self.top_allocations:
                loc = f"{a.filename}:{a.lineno}"
                if len(loc) > 60:
                    loc = "..." + loc[-57:]
                lines.append(f"| `{loc}` | {a.size_kb:.2f} | {a.n_blocks:,} |")

        path.write_text("\n".join(lines), encoding="utf-8")

    def summary_line(self) -> str:
        """Une ligne de resume pour les logs."""
        mem = f"  peak={self.peak_memory_mb:.1f}MB" if self.peak_memory_mb else ""
        return f"{self.function_name}: {self.duration_s:.3f}s{mem}"


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------


class Profiler:
    """
    Profiler CPU + memoire base sur la stdlib Python.

    top_n          : nombre de fonctions/allocations a garder dans le rapport
    profile_memory : activer tracemalloc (desactiver si deja actif par ailleurs)
    """

    def __init__(
        self,
        top_n: int = 20,
        profile_memory: bool = True,
    ) -> None:
        self.top_n = top_n
        self.profile_memory = profile_memory

    def profile(
        self,
        func: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> tuple[Any, ProfilingReport]:
        """
        Profile `func(*args, **kwargs)` et retourne (resultat, ProfilingReport).

        Exemple :
            result, report = profiler.profile(engine.run, data)
        """
        # --- Memoire : demarrer tracemalloc ---
        mem_started = False
        if self.profile_memory and not tracemalloc.is_tracing():
            tracemalloc.start()
            mem_started = True

        # --- CPU : cProfile ---
        pr = cProfile.Profile()
        t0 = time.monotonic()
        pr.enable()
        try:
            result = func(*args, **kwargs)
        finally:
            pr.disable()
        duration = time.monotonic() - t0

        # --- Memoire : snapshot ---
        peak_mb = cur_mb = n_alloc = None
        top_allocs: list[MemoryAllocation] = []
        if self.profile_memory and mem_started:
            snapshot = tracemalloc.take_snapshot()
            cur_size, peak_size = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak_mb = peak_size / 1024 / 1024
            cur_mb = cur_size / 1024 / 1024
            stats = snapshot.statistics("lineno")
            n_alloc = sum(s.count for s in stats)
            for s in stats[: self.top_n]:
                frame = s.traceback[0]
                top_allocs.append(
                    MemoryAllocation(
                        filename=frame.filename,
                        lineno=frame.lineno,
                        size_kb=s.size / 1024,
                        n_blocks=s.count,
                    )
                )

        # --- Parse pstats ---
        top_fns: list[FunctionStat] = []
        try:
            buf = io.StringIO()
            ps = pstats.Stats(pr, stream=buf).sort_stats("cumulative")
            items = list(ps.stats.items())[: self.top_n]
            for stat_key, (cc, nc, tt, ct, _) in items:
                fname = f"{stat_key[0]}:{stat_key[1]}({stat_key[2]})"
                top_fns.append(
                    FunctionStat(
                        function=fname,
                        calls=nc,
                        cumtime_s=ct,
                        tottime_s=tt,
                        percall_s=ct / max(nc, 1),
                    )
                )
            top_fns.sort(key=lambda x: -x.cumtime_s)
        except Exception:  # noqa: BLE001
            pass

        report = ProfilingReport(
            function_name=getattr(func, "__name__", repr(func)),
            duration_s=duration,
            top_functions=top_fns[: self.top_n],
            peak_memory_mb=peak_mb,
            current_memory_mb=cur_mb,
            n_allocations=n_alloc,
            top_allocations=top_allocs,
        )
        return result, report
