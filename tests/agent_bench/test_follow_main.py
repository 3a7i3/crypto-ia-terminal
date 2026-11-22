"""Suivi de main : mission dérivée par révision, arbre analysé distinct, pointeur lu par l'API."""
import json
import shutil

import pytest

from agent_bench.observation import contract as c
from agent_bench.observation import executor as ex
from agent_bench.observation import follow_main as fm
from observability.operator_api import agent_invocation_reader as air

from invocation_bench import REPO, ZONE_MISSION, git

TEMPLATE = json.loads(ZONE_MISSION.read_text(encoding="utf-8"))


def test_same_revision_same_mission_other_revision_other_mission():
    frozen = fm.derive_mission(TEMPLATE, TEMPLATE["analyzed_ref"]["sha"])
    assert frozen["mission_id"] == TEMPLATE["mission_id"]
    a, b = fm.derive_mission(TEMPLATE, "a" * 40), fm.derive_mission(TEMPLATE, "b" * 40)
    assert a["mission_id"] != b["mission_id"] and a["mission_id"] == fm.derive_mission(TEMPLATE, "a" * 40)["mission_id"]
    for m in (a, b):
        c.validate_mission(m)
        assert m["scope"] == TEMPLATE["scope"] and m["question"] == TEMPLATE["question"]


@pytest.mark.parametrize("bad", ["", "main", "A" * 40, "a" * 39, "a" * 40 + "\nX=1"])
def test_invalid_revision_is_refused(bad, tmp_path):
    with pytest.raises(ValueError):
        fm.derive_mission(TEMPLATE, bad)
    assert fm.main(["--template", str(ZONE_MISSION), "--analysed-sha", bad, "--out", str(tmp_path)]) == 2
    assert list(tmp_path.iterdir()) == []


def test_publish_writes_the_three_outputs(tmp_path):
    assert fm.main(["--template", str(ZONE_MISSION), "--analysed-sha", "c" * 40, "--out", str(tmp_path)]) == 0
    m = json.loads((tmp_path / "mission.json").read_text())
    assert (tmp_path / "current.env").read_text() == f"ANALYSED_SHA={'c' * 40}\nMISSION_ID={m['mission_id']}\n"
    assert (tmp_path / "repository-cartographer.mission").read_text() == m["mission_id"] + "\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["current.env", "mission.json", "repository-cartographer.mission"]


def _analysed_tree(root, edit=None):
    tree = root / "analysed"
    for rel in TEMPLATE["scope"]["read_paths"]:
        (tree / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tree / rel)
    if edit:
        with open(tree / edit, "a") as fh:
            fh.write("\n# main a bougé\n")
    git(tree, "init", "-q", "-b", "main")
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", "main")
    return tree, git(tree, "rev-parse", "HEAD")


def test_executor_reads_the_zone_in_the_analysed_tree(genv):
    tree, sha = _analysed_tree(genv.root, edit=TEMPLATE["scope"]["read_paths"][0])
    m = fm.derive_mission(TEMPLATE, sha)
    env, _ = ex.run_once(**genv.kwargs(mission=m, analysed_sha=sha, analysed_tree=tree))
    assert env["state"] == "COMPLETED" and env["analysed_sha"] == sha and env["code_sha"] == genv.sha
    assert env["mission_id"] == m["mission_id"]


def test_analysed_tree_must_be_at_the_analysed_revision(genv):
    tree, sha = _analysed_tree(genv.root)
    m = fm.derive_mission(TEMPLATE, genv.sha)
    with pytest.raises(ex.Refused) as e:
        ex.run_once(**genv.kwargs(mission=m, analysed_sha=genv.sha, analysed_tree=tree))
    assert e.value.code == "ANALYSED_TREE_SHA_MISMATCH"
    (tree / TEMPLATE["scope"]["read_paths"][1]).write_text("modifié\n")
    m = fm.derive_mission(TEMPLATE, sha)
    with pytest.raises(ex.Refused) as e:
        ex.run_once(**genv.kwargs(mission=m, analysed_sha=sha, analysed_tree=tree))
    assert e.value.code == "CHECKOUT_MODIFIED"


def test_api_follows_the_published_pointer(tmp_path):
    spec = air.TARGETS["repository-cartographer"]
    assert air._current(spec, tmp_path)["mission_id"] == spec["mission_id"]  # absent : mission figée
    (tmp_path / "repository-cartographer.mission").write_text("d" * 64 + "\n")
    assert air._current(spec, tmp_path)["mission_id"] == "d" * 64
    for junk in ("../../etc", "d" * 63, "D" * 64, "d" * 64 + "x"):
        (tmp_path / "repository-cartographer.mission").write_text(junk)
        assert air._current(spec, tmp_path)["mission_id"] == spec["mission_id"]
