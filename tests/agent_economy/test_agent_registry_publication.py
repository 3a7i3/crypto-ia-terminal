"""Write-once AgentSpec publication (AW-01 ... AW-06). SOURCE-ONLY primitive."""

from __future__ import annotations

import hashlib
import inspect
import os
import stat
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_economy.agent_registry import publication as pub
from agent_economy.agent_registry.canonical import AgentRegistryError
from agent_economy.agent_registry.integrity import STRUCTURALLY_VALID_CHAIN, verify_chain
from agent_economy.agent_registry.publication import (
    ALREADY_EXISTS_IDENTICAL,
    CREATED,
    classify_artifact_difference,
    publish_agent_spec,
    read_spec_artifact,
    spec_artifact_path,
)
from agent_economy.agent_registry.spec import compute_spec_artifact_bytes, compute_spec_artifact_hash
from tests.agent_economy._builders import Lifecycle, make_spec, seal_spec


def tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_first_publication_creates_the_exact_artifact(tmp_path):
    spec = make_spec()
    result = publish_agent_spec(tmp_path, spec)
    assert result.disposition == CREATED
    assert result.path == tmp_path / spec["agent_id"] / f"{spec['agent_spec_id']}.json"
    assert result.path.read_bytes() == compute_spec_artifact_bytes(spec)
    assert result.spec_artifact_hash == compute_spec_artifact_hash(spec)
    assert stat.S_IMODE(result.path.stat().st_mode) == 0o600
    assert tree(tmp_path) == [spec["agent_id"], f"{spec['agent_id']}/{spec['agent_spec_id']}.json"]


def test_identical_republication_is_idempotent_and_leaves_the_file_untouched(tmp_path):
    spec = make_spec()
    first = publish_agent_spec(tmp_path, spec)
    before = first.path.stat()
    again = publish_agent_spec(tmp_path, dict(spec))
    after = again.path.stat()
    assert again.disposition == ALREADY_EXISTS_IDENTICAL
    assert (before.st_ino, before.st_mtime_ns, before.st_size) == (after.st_ino, after.st_mtime_ns, after.st_size)
    assert tree(tmp_path) == [spec["agent_id"], f"{spec['agent_id']}/{spec['agent_spec_id']}.json"]


def test_same_agent_spec_id_different_artifact_is_provenance_conflict(tmp_path):
    original = make_spec(created_at_utc="2026-10-04T00:00:00Z")
    alternate = make_spec(created_at_utc="2026-10-04T00:00:01Z")
    assert original["agent_spec_id"] == alternate["agent_spec_id"]
    assert compute_spec_artifact_hash(original) != compute_spec_artifact_hash(alternate)
    first = publish_agent_spec(tmp_path, original)
    stored = first.path.read_bytes()
    with pytest.raises(AgentRegistryError) as caught:
        publish_agent_spec(tmp_path, alternate)
    assert caught.value.code == "AGENT_SPEC_PROVENANCE_CONFLICT"
    assert first.path.read_bytes() == stored  # never overwritten, never truncated
    # not accepted as a legitimate second artifact: nothing else was created
    assert tree(tmp_path) == [original["agent_id"], f"{original['agent_id']}/{original['agent_spec_id']}.json"]
    # a different created_from_ref is a provenance difference too
    with pytest.raises(AgentRegistryError) as caught:
        publish_agent_spec(tmp_path, make_spec(created_from_ref="e" * 40))
    assert caught.value.code == "AGENT_SPEC_PROVENANCE_CONFLICT"


def test_corrupted_or_foreign_bytes_under_the_same_name_fail_closed(tmp_path):
    spec = make_spec()
    path = spec_artifact_path(tmp_path, spec["agent_id"], spec["agent_spec_id"])
    path.parent.mkdir(parents=True)
    path.write_bytes(b"truncated {")  # e.g. an interrupted writer
    with pytest.raises(AgentRegistryError) as caught:
        publish_agent_spec(tmp_path, spec)
    assert caught.value.code == "AGENT_SPEC_ID_COLLISION_OR_CORRUPTION"
    assert path.read_bytes() == b"truncated {"
    # a parseable artifact with different MATTER under the same id is a collision, not provenance
    other = make_spec(display_name="Different matter")
    path.write_bytes(compute_spec_artifact_bytes(other))
    with pytest.raises(AgentRegistryError) as caught:
        publish_agent_spec(tmp_path, spec)
    assert caught.value.code == "AGENT_SPEC_ID_COLLISION_OR_CORRUPTION"


def test_classification_of_artifact_differences():
    base = make_spec()
    raw = compute_spec_artifact_bytes(base)
    assert classify_artifact_difference(raw, raw) is None
    later = make_spec(created_at_utc="2027-01-01T00:00:00Z")
    assert classify_artifact_difference(raw, compute_spec_artifact_bytes(later)) == "AGENT_SPEC_PROVENANCE_CONFLICT"
    other = make_spec(display_name="x y z")
    assert classify_artifact_difference(raw, compute_spec_artifact_bytes(other)) == "AGENT_SPEC_ID_COLLISION_OR_CORRUPTION"
    # same parsed content, different bytes (e.g. trailing space): matter equal -> provenance class
    assert classify_artifact_difference(raw, raw + b" ") == "AGENT_SPEC_PROVENANCE_CONFLICT"
    assert classify_artifact_difference(b"nope", raw) == "AGENT_SPEC_ID_COLLISION_OR_CORRUPTION"


def test_invalid_specs_are_never_written(tmp_path):
    spec = make_spec()
    spec["capabilities"] = ["REPOSITORY_READ", "CI_READ"]
    seal_spec(spec)
    with pytest.raises(AgentRegistryError) as caught:
        publish_agent_spec(tmp_path, spec)
    assert caught.value.code == "SPEC_ARRAY_NOT_CANONICAL"
    forbidden = make_spec()
    forbidden["capabilities"] = ["MAIN_MERGE"]
    with pytest.raises(AgentRegistryError):
        publish_agent_spec(tmp_path, seal_spec(forbidden))
    assert tree(tmp_path) == []


def test_publication_creates_no_registry_state_and_no_temporary_residue(tmp_path):
    spec = make_spec()
    result = publish_agent_spec(tmp_path, spec)
    assert set(result.__dataclass_fields__) == {
        "agent_id", "agent_spec_id", "spec_artifact_hash", "path", "disposition",
    }
    assert not any(name.endswith(".tmp") or name.startswith(".") for name in os.listdir(result.path.parent))
    # AW-06: a spec on disk is not a registration; with no events nothing is registered
    from agent_economy.agent_registry import project_registry

    assert project_registry(None).agent_states is None


def test_publication_has_no_default_location_q10_is_unresolved():
    parameters = inspect.signature(publish_agent_spec).parameters
    assert parameters["root"].default is inspect.Parameter.empty
    assert inspect.signature(read_spec_artifact).parameters["root"].default is inspect.Parameter.empty


def test_read_returns_none_for_unpublished_and_exact_bytes_otherwise(tmp_path):
    spec = make_spec()
    assert read_spec_artifact(tmp_path, spec["agent_id"], spec["agent_spec_id"]) is None
    publish_agent_spec(tmp_path, spec)
    assert read_spec_artifact(tmp_path, spec["agent_id"], spec["agent_spec_id"]) == compute_spec_artifact_bytes(spec)


@pytest.mark.parametrize("agent_id,spec_id", [("../..", "0" * 64), ("0" * 64, "../../x"), ("0" * 63, "0" * 64), ("A" * 64, "0" * 64), (None, "0" * 64)])
def test_artifact_paths_cannot_escape_the_root(tmp_path, agent_id, spec_id):
    with pytest.raises(AgentRegistryError) as caught:
        spec_artifact_path(tmp_path, agent_id, spec_id)
    assert caught.value.code == "SPEC_SCHEMA_VIOLATION"
    with pytest.raises(AgentRegistryError):
        read_spec_artifact(tmp_path, agent_id, spec_id)


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="needs O_NOFOLLOW")
def test_a_symlinked_artifact_is_never_followed(tmp_path):
    spec = make_spec()
    path = spec_artifact_path(tmp_path, spec["agent_id"], spec["agent_spec_id"])
    path.parent.mkdir(parents=True)
    target = tmp_path / "elsewhere.json"
    target.write_bytes(compute_spec_artifact_bytes(spec))
    path.symlink_to(target)
    with pytest.raises(AgentRegistryError) as caught:
        publish_agent_spec(tmp_path, spec)
    assert caught.value.code == "PUBLICATION_IO_ERROR"


def test_concurrent_identical_publication_creates_exactly_once(tmp_path):
    spec = make_spec()
    barrier = threading.Barrier(16)

    def attempt(_):
        barrier.wait()
        return publish_agent_spec(tmp_path, dict(spec)).disposition

    with ThreadPoolExecutor(16) as pool:
        outcomes = list(pool.map(attempt, range(16)))
    assert outcomes.count(CREATED) == 1
    assert outcomes.count(ALREADY_EXISTS_IDENTICAL) == 15
    assert tree(tmp_path) == [spec["agent_id"], f"{spec['agent_id']}/{spec['agent_spec_id']}.json"]


def test_concurrent_conflicting_provenance_has_one_winner_and_no_overwrite(tmp_path):
    variants = [make_spec(created_at_utc=f"2026-10-04T00:00:{n:02d}Z") for n in range(4)]
    assert len({v["agent_spec_id"] for v in variants}) == 1
    barrier = threading.Barrier(16)

    def attempt(index):
        barrier.wait()
        variant = variants[index % 4]
        try:
            return publish_agent_spec(tmp_path, variant).disposition, index % 4
        except AgentRegistryError as exc:
            return exc.code, index % 4

    with ThreadPoolExecutor(16) as pool:
        outcomes = list(pool.map(attempt, range(16)))
    created = [variant for code, variant in outcomes if code == CREATED]
    assert len(created) == 1
    winner = created[0]
    for code, variant in outcomes:
        if variant == winner:
            assert code in (CREATED, ALREADY_EXISTS_IDENTICAL)
        else:
            assert code == "AGENT_SPEC_PROVENANCE_CONFLICT"
    stored = spec_artifact_path(tmp_path, variants[0]["agent_id"], variants[0]["agent_spec_id"]).read_bytes()
    assert stored == compute_spec_artifact_bytes(variants[winner])
    assert len(tree(tmp_path)) == 2  # directory + one artifact, no temp residue


def test_an_event_may_only_reference_a_spec_that_was_published_first(tmp_path):
    """AW-04: publish before the event; an event over an unpublished spec is rejected."""
    lifecycle = Lifecycle()
    published = [lifecycle.spec_a1, lifecycle.spec_b1]  # spec_a2 is NOT published
    for spec in published:
        publish_agent_spec(tmp_path, spec)
    loaded = {}
    for spec in (lifecycle.spec_a1, lifecycle.spec_a2, lifecycle.spec_b1):
        raw = read_spec_artifact(tmp_path, spec["agent_id"], spec["agent_spec_id"])
        if raw is not None:
            loaded[spec["agent_spec_id"]] = raw
    result = verify_chain(lifecycle.events, loaded)
    assert result.failure_code == "SPEC_REFERENCE_INVALID" and result.failure_position == 3
    publish_agent_spec(tmp_path, lifecycle.spec_a2)
    loaded[lifecycle.spec_a2["agent_spec_id"]] = read_spec_artifact(
        tmp_path, lifecycle.spec_a2["agent_id"], lifecycle.spec_a2["agent_spec_id"]
    )
    assert verify_chain(lifecycle.events, loaded).status == STRUCTURALLY_VALID_CHAIN


def test_published_bytes_are_exactly_what_the_artifact_hash_covers(tmp_path):
    lifecycle = Lifecycle()
    for spec in (lifecycle.spec_a1, lifecycle.spec_a2, lifecycle.spec_b1):
        result = publish_agent_spec(tmp_path, spec)
        assert result.spec_artifact_hash == hashlib.sha256(result.path.read_bytes()).hexdigest()


def test_publication_module_has_no_update_or_delete_primitive():
    public = {name for name in dir(pub) if not name.startswith("_")}
    for banned in ("delete_agent_spec", "update_agent_spec", "overwrite_agent_spec", "unpublish", "remove_agent_spec"):
        assert banned not in public
    source = inspect.getsource(pub)
    for banned in ("os.remove(", "os.replace(", "os.rename(", "shutil", ".write_text(", ".write_bytes(", "os.truncate", "ftruncate", " open(", "\topen(", "(open("):
        assert banned not in source, banned
