"""
monitoring_profiler.py — Profilage continu du système (CPU, RAM, latence).

Usage:
    python monitoring_profiler.py --duration 10
"""

from __future__ import annotations

import argparse
import sys
import time


def sample_system_metrics() -> dict:
    try:
        import psutil

        return {
            "cpu_pct": psutil.cpu_percent(interval=0.1),
            "ram_pct": psutil.virtual_memory().percent,
        }
    except ImportError:
        return {"cpu_pct": 0.0, "ram_pct": 0.0}


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitoring profiler")
    parser.add_argument(
        "--duration", type=int, default=5, help="Durée de monitoring en secondes"
    )
    args = parser.parse_args()

    print(f"Démarrage du monitoring ({args.duration}s)")
    t0 = time.perf_counter()
    samples = []
    while time.perf_counter() - t0 < args.duration:
        m = sample_system_metrics()
        samples.append(m)
        print(f"  CPU={m['cpu_pct']:.1f}%  RAM={m['ram_pct']:.1f}%")
        time.sleep(0.5)

    print("\n--- Monitoring summary ---")
    if samples:
        avg_cpu = sum(s["cpu_pct"] for s in samples) / len(samples)
        avg_ram = sum(s["ram_pct"] for s in samples) / len(samples)
        print(f"CPU moyen : {avg_cpu:.1f}%")
        print(f"RAM moyen : {avg_ram:.1f}%")
        print(f"Échantillons : {len(samples)}")


if __name__ == "__main__":
    main()
