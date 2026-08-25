"""
tests/test_json_logger_shared_handler.py

R1 — proof that the structured logger uses ONE shared file handler per category
instead of one per module. This is the fix for the observed FD leak
(deleted-but-open logs/runtime/*.jsonl.7): ~190 modules previously created ~190
RotatingFileHandler instances on the same file; competing rotation orphaned
inodes and lost records.

The tests assert the invariant that makes the leak impossible: the number of
open file handlers equals the number of distinct categories used — never the
number of modules.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
from datetime import datetime

import pytest


@pytest.fixture
def jl(tmp_path, monkeypatch):
    # Purge any sys.* stdlib loggers left by earlier tests, point the log root
    # at a tmp dir, then reload the module so its registries start empty.
    for nm in list(logging.Logger.manager.loggerDict):
        if nm.startswith("sys."):
            logging.Logger.manager.loggerDict.pop(nm, None)
    monkeypatch.setenv("OBS_LOG_ROOT", str(tmp_path))
    import observability.json_logger as _jl

    importlib.reload(_jl)
    return _jl


def _file_handlers(jl, logger_name):
    lg = logging.getLogger(logger_name)
    return [h for h in lg.handlers if isinstance(h, jl._DailySizeRotatingHandler)]


def test_one_shared_handler_per_category(jl):
    a, b, c = jl.get_logger("mod_a"), jl.get_logger("mod_b"), jl.get_logger("mod_c")
    a.info("x")
    b.info("y")
    c.info("z")  # all INFO → runtime category

    assert list(jl._category_handlers.keys()) == ["runtime"]
    # every module's runtime logger points at the SAME shared handler instance
    ha = _file_handlers(jl, "sys.mod_a.runtime")
    hb = _file_handlers(jl, "sys.mod_b.runtime")
    hc = _file_handlers(jl, "sys.mod_c.runtime")
    assert len(ha) == len(hb) == len(hc) == 1
    assert ha[0] is hb[0] is hc[0]


def test_no_handler_multiplication_across_many_modules(jl):
    for i in range(60):
        jl.get_logger(f"m{i}").info("hello")

    # 60 modules, all runtime → still exactly ONE file handler total
    assert len(jl._category_handlers) == 1
    distinct = set()
    for nm, lg in logging.Logger.manager.loggerDict.items():
        if nm.startswith("sys.") and isinstance(lg, logging.Logger):
            for h in lg.handlers:
                if isinstance(h, jl._DailySizeRotatingHandler):
                    distinct.add(id(h))
    assert len(distinct) == 1  # not 60


def test_distinct_categories_get_distinct_handlers(jl):
    lg = jl.get_logger("svc")
    lg.info("r")  # runtime
    lg.trade("t")  # trading
    lg.error("e")  # errors

    assert set(jl._category_handlers.keys()) == {"runtime", "trading", "errors"}
    assert len({id(h) for h in jl._category_handlers.values()}) == 3


def test_lines_written_with_correct_per_module_label(jl, tmp_path):
    jl.get_logger("alpha").info("hello", msg="hello world")
    jl.get_logger("beta").warning("warn", msg="beware")
    jl._category_handlers["runtime"].flush()

    date = datetime.now().strftime("%Y-%m-%d")
    path = tmp_path / "runtime" / f"{date}.jsonl"
    recs = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    modules = {r["module"] for r in recs}
    # both producers share ONE file but each line carries its own module
    assert "alpha" in modules and "beta" in modules
    assert all(r["category"] == "runtime" for r in recs)


def test_no_double_attach_on_repeated_get_logger(jl):
    for _ in range(5):
        jl.get_logger("repeat").info("tick")
    handlers = _file_handlers(jl, "sys.repeat.runtime")
    consoles = [
        h
        for h in logging.getLogger("sys.repeat.runtime").handlers
        if getattr(h, "_scios_console", False)
    ]
    assert len(handlers) == 1  # shared file handler attached once
    assert len(consoles) == 1  # console attached once


def test_daily_rollover_switches_to_new_dated_file(jl, tmp_path):
    lg = jl.get_logger("roller")
    lg.info("day-one")
    h = jl._category_handlers["runtime"]

    # Simulate the handler being stuck on an old day (the C3 bug condition).
    h._current_date = "2000-01-01"
    old_path = tmp_path / "runtime" / "2000-01-01.jsonl"
    h.baseFilename = os.path.abspath(str(old_path))
    if h.stream:
        h.stream.close()
        h.stream = None

    lg.info("new-day")  # emit → daily rollover to today's file

    date = datetime.now().strftime("%Y-%m-%d")
    today_path = tmp_path / "runtime" / f"{date}.jsonl"
    assert today_path.exists()
    assert h.baseFilename.endswith(f"{date}.jsonl")
    assert h._current_date == date
