"""
Tests ciblés — Observatory._reconcile() et _restart_dead_tasks().

Couvre :
  1. task morte (avec exception) pour symbole toujours voulu → recréée
  2. task vivante → non remplacée
  3. symbole sorti de watchlist → cancel() + retiré
  4. task morte relancée AVANT reselect_interval_s (détection fréquente)

Aucun accès réseau réel. _run_symbol est toujours patché.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trade_analysis.observatory import Observatory
from trade_analysis.selection import SymbolSelector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_obs(watchlist: list[str], *, flush_interval_s: float = 2.0, reselect_interval_s: float = 300.0) -> Observatory:
    """Crée un Observatory minimal sans vrai connecteur ni store fichier."""
    obs = Observatory.__new__(Observatory)
    obs._tasks = {}
    obs._engines = {}
    obs._running = False
    obs.exchange = "mexc"
    obs.max_symbols = 20
    obs.selection_kwargs = {}
    obs.flush_interval_s = flush_interval_s
    obs.reselect_interval_s = reselect_interval_s

    obs.selector = MagicMock(spec=SymbolSelector)
    obs.selector.select_symbols.return_value = watchlist

    obs.store = MagicMock()
    obs.store.set_watchlist = MagicMock()
    obs.store.flush = MagicMock()
    obs.store.set_contract_meta = MagicMock()
    obs._recorder = None
    return obs


async def _done_task_with_exception(exc: Exception) -> None:
    """Coroutine qui lève une exception — simule un _run_symbol() qui échoue."""
    raise exc


async def _done_task_cleanly() -> None:
    """Coroutine qui se termine proprement."""
    pass


# ---------------------------------------------------------------------------
# TEST 1 — task morte avec exception pour symbole encore voulu → recréée
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_recreates_task_after_it_dies_while_still_watched():
    """
    Scénario principal du bug :
    - BTCUSDT est dans la watchlist
    - La task existante est terminée avec une StreamPipelineError
    - Après _reconcile(), une NOUVELLE task distincte doit exister
    - self._engines["BTCUSDT"] doit avoir été recréé (pop + nouveau _run_symbol)
    """
    obs = _make_obs(["BTCUSDT"])

    # Task terminée avec exception
    exc_task = asyncio.create_task(_done_task_with_exception(RuntimeError("StreamPipelineError: trade dead")))
    try:
        await exc_task
    except RuntimeError:
        pass
    assert exc_task.done()
    assert not exc_task.cancelled()

    obs._tasks["BTCUSDT"] = exc_task
    old_engine = MagicMock()
    obs._engines["BTCUSDT"] = old_engine

    alive_event = asyncio.Event()

    async def _long_running():
        await alive_event.wait()

    with patch.object(obs, "_run_symbol", side_effect=lambda s: _long_running()):
        # _reconcile() gère l'arrêt des sortants et le démarrage des nouveaux,
        # _restart_dead_tasks() gère la relance des tasks mortes pour symboles connus.
        await obs._restart_dead_tasks()
        # Si le symbole n'est plus dans _tasks après restart, _reconcile l'ajoute :
        await obs._reconcile()

    # Nouvelle task, distincte de l'ancienne
    assert "BTCUSDT" in obs._tasks
    new_task = obs._tasks["BTCUSDT"]
    assert new_task is not exc_task, "La task morte doit être remplacée"
    # L'engine de l'ancienne task a été retiré (pop) lors de _restart)
    # Note : _reconcile() seul ne recrée pas l'engine, c'est _run_symbol qui le fait
    # Le test vérifie que l'ancienne entrée est bien absente du registre
    # (une nouvelle est créée par create_task → _run_symbol sera appelé)

    # Cleanup
    alive_event.set()
    await new_task


@pytest.mark.asyncio
async def test_restart_dead_tasks_recreates_task_with_exception():
    """
    Même scénario via _restart_dead_tasks() (chemin fréquent).
    """
    obs = _make_obs(["BTCUSDT"])

    exc_task = asyncio.create_task(_done_task_with_exception(RuntimeError("boom")))
    try:
        await exc_task
    except RuntimeError:
        pass

    obs._tasks["BTCUSDT"] = exc_task
    obs._engines["BTCUSDT"] = MagicMock()

    alive_event = asyncio.Event()

    async def _long_running():
        await alive_event.wait()

    with patch.object(obs, "_run_symbol", side_effect=lambda s: _long_running()):
        await obs._restart_dead_tasks()

    new_task = obs._tasks["BTCUSDT"]
    assert new_task is not exc_task
    assert "BTCUSDT" not in obs._engines  # engine retiré avant _run_symbol (qui le recréerait)

    alive_event.set()
    await new_task


# ---------------------------------------------------------------------------
# TEST 2 — task vivante → non remplacée
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_does_not_recreate_task_still_running():
    """
    Une task vivante (done=False) pour un symbole dans la watchlist ne doit
    PAS être annulée ou recréée.
    """
    obs = _make_obs(["BTCUSDT"])

    alive_event = asyncio.Event()

    async def _long_running():
        await alive_event.wait()

    alive_task = asyncio.create_task(_long_running())
    await asyncio.sleep(0)
    assert not alive_task.done()

    obs._tasks["BTCUSDT"] = alive_task

    with patch.object(obs, "_run_symbol", new_callable=AsyncMock) as mock_run:
        await obs._reconcile()
        await obs._restart_dead_tasks()

    assert obs._tasks["BTCUSDT"] is alive_task, "La task vivante ne doit pas être remplacée"
    mock_run.assert_not_called()

    alive_event.set()
    await alive_task


# ---------------------------------------------------------------------------
# TEST 3 — symbole sorti de watchlist → cancel() + retiré
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_cancels_and_removes_task_no_longer_watched():
    """
    Comportement existant préservé : si ETHUSDT sort de la watchlist,
    sa task doit être cancel()ée et retirée de _tasks et _engines.
    """
    obs = _make_obs(["BTCUSDT"])  # watchlist ne contient plus ETHUSDT

    alive_event = asyncio.Event()

    async def _long_running():
        try:
            await alive_event.wait()
        except asyncio.CancelledError:
            pass

    eth_task = asyncio.create_task(_long_running())
    await asyncio.sleep(0)
    assert not eth_task.done()

    obs._tasks["ETHUSDT"] = eth_task
    obs._engines["ETHUSDT"] = MagicMock()

    with patch.object(obs, "_run_symbol", new_callable=AsyncMock):
        await obs._reconcile()

    # Laisser le cancel se propager (état "cancelling" → "cancelled")
    await asyncio.sleep(0)

    assert "ETHUSDT" not in obs._tasks, "ETHUSDT doit être retiré de _tasks"
    assert "ETHUSDT" not in obs._engines, "ETHUSDT doit être retiré de _engines"
    # La task est soit cancelled, soit done (selon la vitesse de propagation)
    assert eth_task.cancelled() or eth_task.done(), "La task ETHUSDT doit avoir été annulée"


# ---------------------------------------------------------------------------
# TEST 4 — relance AVANT reselect_interval_s (détection fréquente)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dead_task_restart_does_not_wait_for_reselect_interval():
    """
    Avec flush_interval_s=0.05 et reselect_interval_s=300,
    une task morte doit être relancée bien avant les 300 secondes de reselect.

    Ce test vérifie que _restart_dead_tasks() est appelé à chaque flush,
    pas uniquement lors du _reconcile() périodique.
    """
    obs = _make_obs(["BTCUSDT"], flush_interval_s=0.05, reselect_interval_s=300.0)

    # Injecter une task déjà terminée
    done_task = asyncio.create_task(_done_task_cleanly())
    await asyncio.sleep(0)
    assert done_task.done()
    obs._tasks["BTCUSDT"] = done_task

    restart_event = asyncio.Event()
    run_calls: list[str] = []

    async def _run_symbol_mock(sym: str):
        run_calls.append(sym)
        restart_event.set()
        # Bloquer pour que la task reste vivante pendant le test
        await asyncio.Event().wait()

    obs.store.update = MagicMock()

    with patch.object(obs, "_run_symbol", side_effect=_run_symbol_mock):
        with patch.object(obs, "_make_connector", return_value=MagicMock()):
            # Lancer run() en arrière-plan
            run_task = asyncio.create_task(obs.run())
            obs._running = True

            # Attendre le premier restart — doit survenir en ~flush_interval_s, pas 300s
            start = time.monotonic()
            try:
                await asyncio.wait_for(restart_event.wait(), timeout=2.0)
            finally:
                obs._running = False
                run_task.cancel()
                try:
                    await run_task
                except (asyncio.CancelledError, Exception):
                    pass

    elapsed = time.monotonic() - start
    assert restart_event.is_set(), "La task morte doit avoir été relancée"
    assert elapsed < 5.0, f"Relance trop lente : {elapsed:.2f}s (attendu < 5s, reselect=300s)"
    assert "BTCUSDT" in run_calls, "_run_symbol doit avoir été appelé pour BTCUSDT"
