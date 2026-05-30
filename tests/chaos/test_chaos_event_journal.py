"""
Chaos — EventJournal.

Tests du journal d'événements append-only.
Invariants vérifiés :
  - Séquençage monotone et sans trou
  - since(ts) retourne exactement les bons événements
  - replay_since() invoque le handler pour chaque événement
  - Le ring buffer evict les anciens événements correctement
  - Thread-safety sous concurrence légère
  - load_from_file() recharge le journal depuis JSONL
"""

from __future__ import annotations

import threading
import time

from quant_hedge_ai.runtime.event_journal import EventJournal


def _journal(max_memory: int = 100) -> EventJournal:
    return EventJournal(max_memory=max_memory, persist=False)


# ── Enregistrement ──────────────────────────────────────────────────────────


class TestRecord:
    def test_seq_starts_at_one(self):
        j = _journal()
        ev = j.record("test_event", key="value")
        assert ev.seq == 1

    def test_seq_is_monotone(self):
        j = _journal()
        seqs = [j.record("ev", i=i).seq for i in range(10)]
        assert seqs == list(range(1, 11)), f"Séquence non-monotone: {seqs}"

    def test_event_data_preserved(self):
        j = _journal()
        ev = j.record("order_placed", symbol="BTC/USDT", action="BUY", size=0.1)
        assert ev.data["symbol"] == "BTC/USDT"
        assert ev.data["action"] == "BUY"
        assert ev.data["size"] == 0.1

    def test_timestamp_set(self):
        j = _journal()
        t_before = time.time()
        ev = j.record("state_change")
        t_after = time.time()
        assert t_before <= ev.timestamp <= t_after

    def test_size_increases_per_record(self):
        j = _journal()
        for i in range(5):
            j.record("ev", i=i)
        assert j.size == 5


# ── Lecture / requêtes ──────────────────────────────────────────────────────


class TestQuery:
    def test_since_returns_correct_events(self):
        # Utilise une horloge factice pour éviter la résolution ~16ms de Windows
        tick = [0.0]
        j = EventJournal(max_memory=100, persist=False, _clock=lambda: tick[0])
        tick[0] = 1.0
        j.record("early", i=0)
        pivot = 2.0  # clairement après "early" (ts=1.0)
        tick[0] = 3.0
        j.record("late", i=1)
        tick[0] = 4.0
        j.record("late", i=2)
        events = j.since(pivot)
        assert (
            len(events) == 2
        ), f"Attendu 2 events depuis pivot={pivot}, obtenu {len(events)}"
        for ev in events:
            assert ev.event_type == "late"

    def test_since_beginning_returns_all(self):
        j = _journal()
        for i in range(5):
            j.record("ev", i=i)
        events = j.since(0.0)
        assert len(events) == 5

    def test_since_future_returns_empty(self):
        j = _journal()
        j.record("ev")
        events = j.since(time.time() + 999.0)
        assert len(events) == 0

    def test_latest_returns_n_most_recent(self):
        j = _journal()
        for i in range(10):
            j.record("ev", i=i)
        last = j.latest(3)
        assert len(last) == 3
        assert last[-1].data["i"] == 9
        assert last[0].data["i"] == 7

    def test_latest_all_when_n_gt_size(self):
        j = _journal()
        for i in range(3):
            j.record("ev", i=i)
        assert len(j.latest(100)) == 3

    def test_by_type_filters_correctly(self):
        j = _journal()
        j.record("order_placed", symbol="BTC")
        j.record("state_change", old="NORMAL", new="DEGRADED")
        j.record("order_placed", symbol="ETH")
        orders = j.by_type("order_placed")
        assert len(orders) == 2
        assert all(ev.event_type == "order_placed" for ev in orders)


# ── Replay ─────────────────────────────────────────────────────────────────


class TestReplay:
    def test_replay_since_calls_handler(self):
        tick = [0.0]
        j = EventJournal(max_memory=100, persist=False, _clock=lambda: tick[0])
        tick[0] = 1.0
        j.record("ev", i=0)
        pivot = 2.0  # clairement après l'événement i=0 (ts=1.0)
        tick[0] = 3.0
        for i in range(3):
            j.record("ev", i=i + 1)

        replayed = []
        count = j.replay_since(pivot, lambda ev: replayed.append(ev.data["i"]))
        assert count == 3, f"Attendu 3 événements rejoués, obtenu {count}"
        assert replayed == [1, 2, 3]

    def test_replay_order_is_chronological(self):
        j = _journal()
        for i in range(5):
            j.record("ev", i=i)
        seen = []
        j.replay_since(0.0, lambda ev: seen.append(ev.data["i"]))
        assert seen == [0, 1, 2, 3, 4], f"Ordre non-chronologique: {seen}"

    def test_replay_empty_range_calls_handler_zero_times(self):
        j = _journal()
        calls = []
        count = j.replay_since(time.time() + 999.0, lambda ev: calls.append(ev))
        assert count == 0
        assert calls == []


# ── Ring buffer ────────────────────────────────────────────────────────────


class TestRingBuffer:
    def test_old_events_evicted_when_full(self):
        j = EventJournal(max_memory=5, persist=False)
        for i in range(10):
            j.record("ev", i=i)
        assert j.size == 5
        # Les événements gardés doivent être les plus récents
        last = j.latest(5)
        indices = [ev.data["i"] for ev in last]
        assert indices == [5, 6, 7, 8, 9], f"Ring buffer incorrect: {indices}"

    def test_seq_continues_after_eviction(self):
        j = EventJournal(max_memory=3, persist=False)
        for _ in range(10):
            j.record("ev")
        assert j.last_seq == 10

    def test_clear_resets_buffer(self):
        j = _journal()
        for _ in range(5):
            j.record("ev")
        j.clear()
        assert j.size == 0
        assert j.latest() == []


# ── Thread-safety ──────────────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_records_no_seq_collision(self):
        j = _journal(max_memory=1_000)
        results = []
        lock = threading.Lock()

        def worker():
            ev = j.record("concurrent")
            with lock:
                results.append(ev.seq)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 50
        assert (
            len(set(results)) == 50
        ), "INVARIANT BRISÉ: collision de séquences sous concurrence"

    def test_concurrent_reads_while_writing(self):
        j = _journal(max_memory=500)
        errors = []

        def writer():
            for i in range(20):
                j.record("write", i=i)

        def reader():
            try:
                for _ in range(20):
                    j.latest(5)
                    j.since(0.0)
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=writer)] + [
            threading.Thread(target=reader) for _ in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == [], f"Erreurs sous concurrence: {errors}"


# ── Persistence JSONL ──────────────────────────────────────────────────────


class TestPersistence:
    def test_persist_and_reload(self, tmp_path):
        path = tmp_path / "journal.jsonl"
        j1 = EventJournal(persist=True, path=path)
        j1.record("order_placed", symbol="BTC", size=0.1)
        j1.record("state_change", old="NORMAL", new="DEGRADED")

        j2 = EventJournal(persist=False, path=path)
        loaded = j2.load_from_file()
        assert loaded == 2
        events = j2.latest(2)
        assert events[0].event_type == "order_placed"
        assert events[1].event_type == "state_change"

    def test_persist_seq_restored(self, tmp_path):
        path = tmp_path / "journal.jsonl"
        j1 = EventJournal(persist=True, path=path)
        for i in range(5):
            j1.record("ev", i=i)

        j2 = EventJournal(persist=False, path=path)
        j2.load_from_file()
        assert j2.last_seq == 5

    def test_load_missing_file_returns_zero(self, tmp_path):
        j = EventJournal(persist=False, path=tmp_path / "nonexistent.jsonl")
        loaded = j.load_from_file()
        assert loaded == 0
