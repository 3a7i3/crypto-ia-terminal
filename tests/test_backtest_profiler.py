import subprocess
import sys


def test_backtest_profiler_runs():
    """Vérifie que le script de profiling s'exécute sans erreur et affiche les logs."""
    result = subprocess.run(
        [
            sys.executable,
            "strategy_factory/backtest_profiler.py",
            "--n",
            "100",
            "--n_strat",
            "2",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Erreur d'exécution: {result.stderr}"
    assert "Profiling summary" in result.stdout or "Profiling summary" in result.stderr


def test_backtest_profiler_bad_args():
    """Vérifie la robustesse aux mauvais arguments."""
    result = subprocess.run(
        [sys.executable, "strategy_factory/backtest_profiler.py", "--n", "abc"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
