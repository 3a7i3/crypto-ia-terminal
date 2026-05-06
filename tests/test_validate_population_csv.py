from __future__ import annotations

import pandas as pd

from population_csv_validator import validate_csv_file, validate_population_dir


def test_validate_csv_file_accepts_well_formed_population_csv(tmp_path) -> None:
    csv_path = tmp_path / "trend_pop_gen_0.csv"
    pd.DataFrame(
        [
            {"id": "a1", "fitness": 1.2, "species": "trend", "exit.tp": 0.2, "exit.sl": 0.1},
            {"id": "b2", "fitness": 0.8, "species": "range", "exit.tp": 0.3, "exit.sl": 0.15},
        ]
    ).to_csv(csv_path, index=False)

    valid, message = validate_csv_file(csv_path)
    assert valid is True
    assert message == "OK"


def test_validate_csv_file_rejects_missing_required_columns(tmp_path) -> None:
    csv_path = tmp_path / "trend_pop_gen_1.csv"
    pd.DataFrame([{"id": "a1", "fitness": 1.2, "species": "trend", "exit.tp": 0.2}]).to_csv(
        csv_path, index=False
    )

    valid, message = validate_csv_file(csv_path)
    assert valid is False
    assert "Colonnes manquantes" in message


def test_validate_population_dir_reports_only_population_csv_errors(tmp_path) -> None:
    valid_csv = tmp_path / "chaos_pop_gen_2.csv"
    invalid_csv = tmp_path / "range_pop_gen_3.csv"
    ignored_csv = tmp_path / "summary.csv"

    pd.DataFrame(
        [{"id": "a1", "fitness": 1.2, "species": "trend", "exit.tp": 0.2, "exit.sl": 0.1}]
    ).to_csv(valid_csv, index=False)
    pd.DataFrame([{"id": "a1", "fitness": 1.2, "species": "trend", "exit.tp": 0.2}]).to_csv(
        invalid_csv, index=False
    )
    pd.DataFrame([{"note": "ignored"}]).to_csv(ignored_csv, index=False)

    errors = validate_population_dir(tmp_path)
    assert len(errors) == 1
    assert errors[0].startswith("range_pop_gen_3.csv")


def test_validate_csv_file_rejects_nan_and_inf_values(tmp_path) -> None:
    csv_path = tmp_path / "trend_pop_gen_4.csv"
    pd.DataFrame(
        [
            {"id": 1, "fitness": float("nan"), "species": "A", "exit.tp": 0.1, "exit.sl": 0.1},
            {"id": 2, "fitness": float("inf"), "species": "B", "exit.tp": 0.2, "exit.sl": 0.2},
        ]
    ).to_csv(csv_path, index=False)

    valid, message = validate_csv_file(csv_path)

    assert valid is False
    assert "Valeurs manquantes" in message


def test_validate_csv_file_rejects_malformed_csv(tmp_path) -> None:
    csv_path = tmp_path / "trend_pop_gen_5.csv"
    csv_path.write_text(
        "id,fitness,species,exit.tp,exit.sl\n1,0.5,A,0.1,0.2\n2,0.6,B,0.1",
        encoding="utf-8",
    )

    valid, message = validate_csv_file(csv_path)

    assert valid is False
    assert "Erreur de lecture" in message