"""
tests/test_dotenv_precedence.py — ENV-01 : preuve de l'invariant

    PRE-EXISTING PROCESS ENVIRONMENT > dotenv file

Contexte (FAM-01 / ENVIRONMENT_CONFIGURATION_CONSTITUTION.md) : sous
systemd, l'ordre est

    EnvironmentFile=-.env
    EnvironmentFile=-.env.secrets

systemd charge les deux fichiers directement dans l'environnement du
process AVANT même que l'interpréteur Python ne démarre — la dernière
directive gagnante (`.env.secrets`) est donc déjà dans `os.environ` quand
`core/advisor_loop.py` / `watchdog_vps.py` exécutent leur propre
`load_dotenv()`. Un `load_dotenv(override=True)` relirait `.env` et
écraserait cette valeur, ce qui est le risque de précédence identifié par
FAM-01 et remédié en ENV-01 (`load_dotenv(override=False)`).

Ces tests n'utilisent QUE des valeurs factices (`EXAMPLE_*`) et des
fichiers `.env` temporaires (`tmp_path`) — aucun fichier réel `.env` /
`.env.secrets` n'est lu ni créé.
"""
from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv


@pytest.fixture
def dummy_env_file(tmp_path):
    """Fabrique un fichier .env jetable et retourne son chemin."""

    def _make(content: str):
        path = tmp_path / ".env.dummy"
        path.write_text(content, encoding="utf-8")
        return path

    return _make


@pytest.fixture(autouse=True)
def _clean_dummy_keys(monkeypatch):
    """Garantit que les clés factices n'existent pas avant/après chaque test."""
    for key in ("EXAMPLE_SECRET", "EXAMPLE_NON_SECRET", "EXAMPLE_NORMAL"):
        monkeypatch.delenv(key, raising=False)
    yield
    for key in ("EXAMPLE_SECRET", "EXAMPLE_NON_SECRET", "EXAMPLE_NORMAL"):
        monkeypatch.delenv(key, raising=False)


class TestDotenvPrecedenceOverrideFalse:
    """Reproduit le comportement effectif de core/advisor_loop.py et
    watchdog_vps.py après remédiation ENV-01 : load_dotenv(override=False)."""

    def test_case_a_preexisting_process_env_wins_over_dotenv_file(
        self, dummy_env_file, monkeypatch
    ):
        """CASE A — une valeur déjà injectée dans le process (simulant
        EnvironmentFile=.env.secrets sous systemd) ne doit JAMAIS être
        écrasée par un .env rechargé ensuite."""
        monkeypatch.setenv("EXAMPLE_SECRET", "from_systemd_secret")
        env_path = dummy_env_file("EXAMPLE_SECRET=from_env\n")

        load_dotenv(dotenv_path=env_path, override=False)

        assert os.environ["EXAMPLE_SECRET"] == "from_systemd_secret", (
            "PRECEDENCE_RISK : la valeur pré-existante du process a été "
            "écrasée par le fichier .env — override=False n'a pas été "
            "respecté."
        )

    def test_case_b_unset_var_is_populated_from_dotenv_file(
        self, dummy_env_file
    ):
        """CASE B — une variable NON secrète absente du process doit
        toujours pouvoir être peuplée depuis .env (exécution CLI manuelle,
        ou variable non injectée par systemd)."""
        assert "EXAMPLE_NON_SECRET" not in os.environ
        env_path = dummy_env_file("EXAMPLE_NON_SECRET=value_from_env\n")

        load_dotenv(dotenv_path=env_path, override=False)

        assert os.environ["EXAMPLE_NON_SECRET"] == "value_from_env"

    def test_case_c_normal_process_value_not_overwritten_unexpectedly(
        self, dummy_env_file, monkeypatch
    ):
        """CASE C — une valeur d'environnement normale (export manuel,
        parent shell) n'est jamais remplacée sans intention explicite."""
        monkeypatch.setenv("EXAMPLE_NORMAL", "manual_export_value")
        env_path = dummy_env_file("EXAMPLE_NORMAL=would_be_overwritten\n")

        load_dotenv(dotenv_path=env_path, override=False)

        assert os.environ["EXAMPLE_NORMAL"] == "manual_export_value"

    def test_regression_override_true_would_have_broken_case_a(
        self, dummy_env_file, monkeypatch
    ):
        """Documente précisément le défaut corrigé : override=True (état
        AVANT ENV-01) laisse le fichier .env gagner, ce qui est exactement
        le risque de précédence signalé par FAM-01."""
        monkeypatch.setenv("EXAMPLE_SECRET", "from_systemd_secret")
        env_path = dummy_env_file("EXAMPLE_SECRET=from_env\n")

        load_dotenv(dotenv_path=env_path, override=True)

        assert os.environ["EXAMPLE_SECRET"] == "from_env", (
            "override=True écrase toujours la valeur pré-existante du "
            "process — comportement volontairement reproduit ici pour "
            "documenter le risque, PAS pour le valider comme correct."
        )


class TestSourceEntrypointsUseOverrideFalse:
    """Vérifie statiquement (sans exécuter les modules, donc sans toucher à
    un vrai .env/.env.secrets) que les deux entrypoints systemd identifiés
    par ENV-01 utilisent bien load_dotenv(override=False)."""

    @pytest.mark.parametrize(
        "relative_path",
        [
            "core/advisor_loop.py",
            "watchdog_vps.py",
        ],
    )
    def test_entrypoint_does_not_use_override_true(self, relative_path):
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent
        source = (repo_root / relative_path).read_text(encoding="utf-8")

        assert "load_dotenv(override=True)" not in source, (
            f"PRECEDENCE_RISK : {relative_path} utilise encore "
            "load_dotenv(override=True), en violation de l'invariant "
            "PRE-EXISTING PROCESS ENVIRONMENT > dotenv file (ENV-01)."
        )
        assert "load_dotenv(override=False)" in source, (
            f"{relative_path} devrait appeler explicitement "
            "load_dotenv(override=False) (remédiation ENV-01)."
        )
