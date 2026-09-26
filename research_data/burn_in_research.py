"""Governed offline burn-in Research workspace; no PAPER activation capability.

Protected roots are explicit operator inputs, never discovered from the runtime.
This is an application boundary, not an OS sandbox for arbitrary Python code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from research_candidate import publish_candidate
from research_diag import diagnose_factual_dataset
from research_replay.factual import replay_factual_dataset, validate_dataset
from research_replay.publication import publish_factual_result

from .burn_in_finalization import (
    BurnInDatasetValidationError,
    _paths_overlap,
    _validate_dataset,
)
from .paper_exporter import _canonical_json_bytes, _load_experiment_config, _write_new_bytes


@dataclass(frozen=True)
class BurnInResearchWorkspace:
    dataset_path: Path
    output_root: Path
    protected_roots: tuple[Path, ...]

    def _validate(self) -> Mapping[str, Any]:
        if not self.protected_roots:
            raise BurnInDatasetValidationError("explicit protected PAPER/runtime roots required")
        root = Path(self.output_root).resolve()
        dataset = Path(self.dataset_path).resolve()
        manifest, _, _, _ = _validate_dataset(dataset)
        validate_dataset(dataset)
        # Source provenance is used only as a declared path exclusion. Source
        # files are never opened, queried, copied or created by this workspace.
        source_parents = tuple(
            Path(item["path"]).parent
            for item in manifest["extraction_provenance"]["sources"]
        )
        for protected in (dataset, *self.protected_roots, *source_parents):
            if _paths_overlap(root, Path(protected)):
                raise BurnInDatasetValidationError("Research output overlaps protected storage")
        # Reject a pre-existing symlink inside the output namespace as well as
        # a root alias. Operator-controlled roots must remain stable while used.
        if root.exists() and any(p.is_symlink() for p in root.rglob("*")):
            raise BurnInDatasetValidationError("Research output contains symlink")
        return manifest

    def replay_and_diagnose(
        self, *, code_sha: str, generated_at_utc: str
    ) -> tuple[Any, Any, Any]:
        """Compute both results before publishing; missing diagnostics fail closed."""
        self._validate()
        replay = replay_factual_dataset(self.dataset_path, replay_code_sha=code_sha)
        diagnostic = diagnose_factual_dataset(
            self.dataset_path, replay_code_sha=code_sha, diag_code_sha=code_sha
        )
        self._validate()
        publication = publish_factual_result(
            replay, output_root=self.output_root, generated_at_utc=generated_at_utc
        )
        diagnostic_path = (
            Path(self.output_root) / "diagnostics" / diagnostic.diagnostic_run_id / "result.json"
        )
        _write_new_bytes(
            diagnostic_path, _canonical_json_bytes(diagnostic.as_dict()) + b"\n"
        )
        return replay, diagnostic, publication

    def publish_candidate(
        self,
        candidate: Mapping[str, Any],
        *,
        baseline_material_config: Mapping[str, Any],
        evidence_catalog: Mapping[str, set[str]],
    ) -> Any:
        manifest = self._validate()
        baseline = candidate.get("baseline", {})
        parents = candidate.get("parents", {})
        boundary = manifest["source_boundary_identity"]
        if (
            baseline.get("paper_epoch_id") != manifest["paper_epoch_id"]
            or baseline.get("source_code_sha") != boundary["experiment_runtime_source_sha"]
            or baseline.get("config_hash") != boundary["experiment_config_snapshot_sha256"]
            or manifest["dataset_id"] not in parents.get("dataset_ids", ())
            or manifest["source_boundary_id"] not in parents.get("source_boundary_ids", ())
        ):
            raise BurnInDatasetValidationError("candidate must bind to this burn-in dataset")
        _, config = _load_experiment_config(
            Path(self.dataset_path) / "authoritative" / "burn_in_experiment_config.json",
            paper_epoch_id=manifest["paper_epoch_id"], epoch_role="BURN_IN_EXPERIMENT",
        )
        parameters = config["parameters"]
        if set(parameters) != set(baseline_material_config) or any(
            not isinstance(baseline_material_config[name], Mapping)
            or str(baseline_material_config[name].get("value")) != str(parameter.get("value"))
            for name, parameter in parameters.items()
        ):
            raise BurnInDatasetValidationError("candidate baseline material config differs from frozen snapshot")
        return publish_candidate(
            Path(self.output_root) / "candidates",
            candidate,
            baseline_material_config=baseline_material_config,
            evidence_catalog=evidence_catalog,
        )
