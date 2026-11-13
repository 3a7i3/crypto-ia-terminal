"""Synthetic C1b driver (test only): the C1b wiring without the Advisor.

It runs, in its own process, the same sequence as ``core/advisor_loop.py`` in
C1b mode: ``prepare_from_env`` (identity lock, flag-only handlers) before the
authority bind, ``bind_wiring`` after it, a C1a ``MexcSimulator`` started with
the wiring kwargs, a loop that waits on the stop event, then ``shutdown_proof``
and the exit code of the outcome.  It never imports ``advisor_loop``, never
touches the network, an exchange or a notification channel: prices come from
``<root>/prices.json`` and notifications are appended to ``<root>/notes.jsonl``.

Commands are files ``<root>/cmd/<n>.json`` processed in name order; each result
is printed as one JSON line on stdout.  Test seams (never in the Advisor):

* ``--head`` / ``--worktree``: the claimed checkout (``capture_fn`` stub);
* ``--pause-after observation|seal``: block forever after that proof step so the
  test can SIGKILL the process at a known point;
* ``--close-after stop|observation|seal``: a monitor-like CLOSE of every open
  position at that step (late monitor write, exigence 1);
* ``--inject before_write|base_exception``: fault in the authority store during
  the next OPEN (B5a, B6); ``--inject barrier``: the next OPEN commit blocks
  until ``<root>/release`` exists (B3).

Usage: python -I c1b_driver.py --repo <repo> --root <root> --head <sha> ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

EPOCH = "C1B-DRIVER-EPOCH"
CODE = "cb" * 20


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw, sort_keys=True, default=str) + "\n")
    sys.stdout.flush()


def manifest():
    from paper_trading.ppl_authority_runtime import (
        EpochRotationQuiescence,
        build_experiment_manifest,
    )

    return build_experiment_manifest(
        paper_epoch_id=EPOCH,
        created_at=1.0,
        initial_virtual_capital=1000.0,
        code_sha=CODE,
        config_snapshot_hash="cfg-hash-c1b-driver",
        legacy_log_bytes=b"",
        quiescence=EpochRotationQuiescence(0, 0, 0, True),
        predecessor_authority_epoch_id="PRED-EPOCH",
    )


class _Spot:
    def __init__(self, prices: Path) -> None:
        self.prices = prices

    def fetch_ticker(self, symbol: str) -> dict:
        try:
            value = json.loads(self.prices.read_text()).get(symbol, 0)
        except (OSError, ValueError):
            value = 0
        return {"last": value}


class _InjectedBase(BaseException):
    """Stands for an asynchronous interruption inside the commit (B6)."""


def install_fault(store, kind: str, root: Path) -> None:
    """One-shot fault on the next ``POSITION_OPENED`` append (B5a, B6), or a
    deterministic commit barrier (B3): the append announces ``commit_blocked``
    and waits for ``<root>/release`` before writing (watchdog 60 s)."""
    original = store.append
    state = {"armed": True}

    def append(epoch_id, event):
        if not state["armed"] or getattr(event, "event_type", "") != "POSITION_OPENED":
            return original(epoch_id, event)
        state["armed"] = False
        if kind == "before_write":
            raise OSError(5, "injected before write")
        if kind == "barrier":
            emit(event="commit_blocked")
            deadline = time.monotonic() + 60.0
            while not (root / "release").exists():
                if time.monotonic() > deadline:
                    raise OSError(110, "barrier watchdog: never released")
                time.sleep(0.005)
            return original(epoch_id, event)
        raise _InjectedBase("injected inside commit")

    store.append = append


def install_fsync_fault(times: int) -> None:
    """B5b: the next ``times`` fsync calls on an epoch ``.jsonl`` raise EIO
    after the bytes were written (mirror of C1a ``_fail_fsync_once``).  With
    1, the append is visible and the retry succeeds; with 2, the retry fails
    too and the transition is APPLIED_DURABLE_NOT_MEMORY."""
    import errno
    import stat

    real = os.fsync
    state = {"n": 0}

    def flaky(fd):
        st = os.fstat(fd)
        if stat.S_ISREG(st.st_mode) and state["n"] < times:
            try:
                target = os.readlink(f"/proc/self/fd/{fd}")
            except OSError:
                target = ""
            if target.endswith(".jsonl") and "epochs" in target:
                state["n"] += 1
                emit(event="fsync_failed", n=state["n"])
                raise OSError(errno.EIO, "injected fsync failure")
        return real(fd)

    os.fsync = flaky


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--head", default=CODE)
    parser.add_argument("--worktree", default="CLEAN")
    parser.add_argument("--pause-after", choices=("observation", "seal"))
    parser.add_argument("--close-after", choices=("stop", "observation", "seal"))
    parser.add_argument(
        "--inject",
        choices=(
            "before_write",
            "base_exception",
            "barrier",
            "fsync_once",
            "fsync_twice",
        ),
    )
    args = parser.parse_args(argv)
    sys.path.insert(0, args.repo)
    root = Path(args.root)
    os.chdir(root)

    import logging

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    from paper_trading import mexc_simulator as ms
    from paper_trading import ppl_quiescence_c1b as c1b
    from paper_trading.durable_event_store import DurableEventStore
    from paper_trading.paper_authority import PaperLifecycleAuthority
    from paper_trading.ppl_authority_runtime import PPLAuthorityRuntime

    ms._MONITOR_INTERVAL = 0.05

    try:
        prepared = c1b.prepare_from_env(
            os.environ, legacy_lock_path=str(root / "advisor.lock")
        )
        if prepared is None:
            emit(event="refused", type="NotConfigured", detail="no C1b variable")
            return 1
        runtime = PPLAuthorityRuntime(
            manifest=manifest(), store=DurableEventStore(root / "authority")
        )
        runtime.bind(now=time.time())
        wiring = c1b.bind_wiring(
            prepared,
            SimpleNamespace(ppl_is_authoritative=True),
            runtime,
            capture_fn=lambda: SimpleNamespace(
                source_sha=args.head, worktree_state=args.worktree
            ),
        )
    except c1b.C1bRefusal as exc:
        emit(event="refused", type=type(exc).__name__, detail=str(exc))
        return 1

    notes = root / "notes.jsonl"

    def notify(text: str) -> None:
        with notes.open("a") as fh:
            fh.write(json.dumps(text) + "\n")

    sim = ms.MexcSimulator(
        mexc_reader=SimpleNamespace(spot=_Spot(root / "prices.json")),
        telegram_fn=notify,
        lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
        authority_runtime=runtime,
        **wiring.simulator_kwargs(),
    )
    sim.start()
    if args.inject in ("fsync_once", "fsync_twice"):
        install_fsync_fault(1 if args.inject == "fsync_once" else 2)
    elif args.inject:
        install_fault(runtime.store, args.inject, root)

    lock = prepared.identity_lock
    emit(
        event="ready",
        pid=os.getpid(),
        gate_state=wiring.gate_state_at_boot,
        lock=list(lock.identity),
        positions=sorted(sim._positions),
    )

    def close_all() -> None:
        for symbol in list(sim._positions):
            sim._close_position(symbol, 101.0, "TP")

    def pause(step: str):
        def hold() -> None:
            emit(event="paused", at=step)
            threading.Event().wait()

        return hold

    hooks = {}
    if args.close_after:
        hooks["after_" + args.close_after] = close_all
    if args.pause_after:
        previous = hooks.get("after_" + args.pause_after)

        def chained(prev=previous, hold=pause(args.pause_after)):
            if prev is not None:
                prev()
            hold()

        hooks["after_" + args.pause_after] = chained

    cmd_dir = root / "cmd"
    cmd_dir.mkdir(exist_ok=True)
    while not wiring.stop_requested:
        for path in sorted(cmd_dir.glob("*.json")):
            request = json.loads(path.read_text())
            path.rename(path.with_suffix(".done"))
            try:
                if request["op"] == "buy":
                    order = sim.place_market_order(
                        request.get("symbol", "BTC/USDT"),
                        "BUY",
                        10.0,
                        current_price=request.get("price", 100.0),
                    )
                    result = {
                        "status": getattr(getattr(order, "status", None), "name", None),
                        "reject_code": getattr(order, "reject_code", None),
                    }
                elif request["op"] == "close":
                    close_all()
                    result = {"positions": sorted(sim._positions)}
                else:
                    result = {"error": "unknown op"}
            except BaseException as exc:  # noqa: BLE001 - reported to the test
                result = {"raised": type(exc).__name__, "detail": str(exc)}
            emit(event="cmd", name=path.stem, result=result)
        wiring.wait_stop(0.05)

    outcome = c1b.shutdown_proof(
        wiring,
        sim,
        runtime,
        process_instance_id=f"c1b-driver-{os.getpid()}",
        hooks=hooks,
    )
    emit(
        event="outcome",
        status=outcome.status,
        detail=outcome.detail,
        sealed=outcome.sealed,
        exit_code=outcome.exit_code,
        observation_sha256=outcome.observation_sha256,
        seal_sha256=outcome.seal_sha256,
        signum=wiring.stop_signum,
    )
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
