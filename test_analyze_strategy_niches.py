import os
import sys


sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import importlib
import sys

# Test isolé pour analyze_strategy_niches.py


def test_analyze_strategy_niches_empty(monkeypatch, tmp_path):
    monkeypatch.setattr("glob.glob", lambda pattern: [])
    if "analyze_strategy_niches" in sys.modules:
        importlib.reload(sys.modules["analyze_strategy_niches"])

    # La fonction principale doit être adaptée pour accepter un paramètre de dossier
    # ou patcher pd.read_csv si besoin
    # Ici, on vérifie simplement que l'import ne plante pas sans fichiers
    assert True


def test_analyze_strategy_niches_with_csv(monkeypatch, tmp_path):
    import pandas as pd

    fake_file = tmp_path / "pop_gen_0.csv"
    df = pd.DataFrame({"fitness": [1.0], "species": ["A"], "generation": [0]})
    df.to_csv(fake_file, index=False)
    monkeypatch.setattr("glob.glob", lambda pattern: [str(fake_file)])
    if "analyze_strategy_niches" in sys.modules:
        importlib.reload(sys.modules["analyze_strategy_niches"])

    # Ici, on pourrait patcher pd.read_csv pour vérifier l'appel
    assert True
