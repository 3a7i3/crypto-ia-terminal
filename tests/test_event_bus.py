from src.events.event_bus import SimEventBus


def test_subscribe_and_emit():
    bus = SimEventBus()
    received = []
    bus.subscribe("TRADE_CLOSED", received.append)
    bus.emit({"type": "TRADE_CLOSED", "symbol": "BTC", "pnl": 10.0})
    assert len(received) == 1
    assert received[0]["symbol"] == "BTC"


def test_multiple_subscribers_same_event():
    bus = SimEventBus()
    log1, log2 = [], []
    bus.subscribe("TRADE_OPENED", log1.append)
    bus.subscribe("TRADE_OPENED", log2.append)
    bus.emit({"type": "TRADE_OPENED", "symbol": "ETH"})
    assert len(log1) == 1
    assert len(log2) == 1


def test_emit_unknown_event_does_not_crash():
    bus = SimEventBus()
    bus.emit({"type": "UNKNOWN_EVENT", "data": 42})


def test_unsubscribe():
    bus = SimEventBus()
    log = []
    bus.subscribe("EV", log.append)
    bus.unsubscribe("EV", log.append)
    bus.emit({"type": "EV"})
    assert log == []


def test_clear():
    bus = SimEventBus()
    log = []
    bus.subscribe("EV", log.append)
    bus.clear()
    bus.emit({"type": "EV"})
    assert log == []


def test_event_isolation_by_type():
    bus = SimEventBus()
    opened, closed = [], []
    bus.subscribe("TRADE_OPENED", opened.append)
    bus.subscribe("TRADE_CLOSED", closed.append)
    bus.emit({"type": "TRADE_OPENED"})
    bus.emit({"type": "TRADE_CLOSED"})
    assert len(opened) == 1
    assert len(closed) == 1
