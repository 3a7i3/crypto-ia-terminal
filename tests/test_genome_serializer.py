"""
Tests pour GenomeSerializer : round-trip JSON, save/load, robustesse.
"""

import json
from pathlib import Path

import pytest

from evolution_core import Genome, GenomeSerializer, evaluate_fitness


class TestToDict:
    def test_has_required_keys(self):
        g = Genome()
        d = GenomeSerializer.to_dict(g)
        assert set(d) >= {
            "_version",
            "id",
            "genes",
            "fitness",
            "fitness_trend",
            "fitness_range",
            "fitness_crash",
            "parent_ids",
        }

    def test_version_is_int(self):
        d = GenomeSerializer.to_dict(Genome())
        assert isinstance(d["_version"], int)

    def test_genes_are_preserved(self):
        g = Genome({"entry.type": "trend", "exit.tp": 2.5})
        d = GenomeSerializer.to_dict(g)
        assert d["genes"]["entry.type"] == "trend"
        assert d["genes"]["exit.tp"] == pytest.approx(2.5)

    def test_fitness_floats(self):
        g = Genome()
        evaluate_fitness(g)
        d = GenomeSerializer.to_dict(g)
        assert isinstance(d["fitness"], float)
        assert isinstance(d["fitness_trend"], float)


class TestFromDict:
    def test_round_trip_id(self):
        g = Genome()
        restored = GenomeSerializer.from_dict(GenomeSerializer.to_dict(g))
        assert restored.id == g.id

    def test_round_trip_genes(self):
        g = Genome()
        restored = GenomeSerializer.from_dict(GenomeSerializer.to_dict(g))
        assert restored.genes == g.genes

    def test_round_trip_fitness(self):
        g = Genome()
        evaluate_fitness(g)
        restored = GenomeSerializer.from_dict(GenomeSerializer.to_dict(g))
        assert restored.fitness == pytest.approx(g.fitness)

    def test_missing_optional_fields_use_defaults(self):
        d = GenomeSerializer.to_dict(Genome())
        d.pop("fitness_trend", None)
        d.pop("parent_ids", None)
        restored = GenomeSerializer.from_dict(d)
        assert restored.fitness_trend == 0.0
        assert restored.parent_ids == []


class TestSaveLoad:
    def test_save_creates_json_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pop = [Genome() for _ in range(5)]
        GenomeSerializer.save_population(pop, "checkpoints/pop.json")
        assert (tmp_path / "checkpoints" / "pop.json").exists()

    def test_saved_file_is_valid_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pop = [Genome()]
        path = tmp_path / "pop.json"
        GenomeSerializer.save_population(pop, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "genomes" in data
        assert data["size"] == 1

    def test_load_restores_population(self, tmp_path):
        pop = [Genome() for _ in range(4)]
        path = tmp_path / "pop.json"
        GenomeSerializer.save_population(pop, path)
        restored = GenomeSerializer.load_population(path)
        assert len(restored) == 4

    def test_round_trip_all_ids(self, tmp_path):
        pop = [Genome() for _ in range(6)]
        original_ids = [g.id for g in pop]
        path = tmp_path / "pop.json"
        GenomeSerializer.save_population(pop, path)
        restored = GenomeSerializer.load_population(path)
        assert [g.id for g in restored] == original_ids

    def test_creates_parent_dirs(self, tmp_path):
        pop = [Genome()]
        path = tmp_path / "deep" / "nested" / "pop.json"
        GenomeSerializer.save_population(pop, path)
        assert path.exists()

    def test_no_pickle_in_json_file(self, tmp_path):
        pop = [Genome()]
        path = tmp_path / "pop.json"
        GenomeSerializer.save_population(pop, path)
        content = path.read_text(encoding="utf-8")
        assert "pickle" not in content.lower()
        assert content.startswith("{")
