"""EventBus/EventStore semantics + the legacy-convergence shim."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from zortenet.core.bus import EventBus, EventStore
from zortenet.core.events import EventDomain, NetworkEvent, Severity
from zortenet.core.legacy import network_event_from_legacy


def _ev(domain=EventDomain.LOCATION, entity="ue1", severity=Severity.INFO, **payload):
    return NetworkEvent(
        domain=domain, source="test", entity_id=entity, severity=severity, payload=payload
    )


# ---- store -------------------------------------------------------------------


def test_store_recent_filters_and_orders():
    store = EventStore()
    store.append(_ev(entity="ue1", cell="A"))
    store.append(_ev(domain=EventDomain.QOS, entity="ue1", latency_ms=80))
    store.append(_ev(entity="ue2", severity=Severity.ALERT, cell="X"))

    assert len(store) == 3
    # most-recent-first
    assert store.recent(limit=1)[0].entity_id == "ue2"
    # domain filter
    qos = store.recent(domain="qos")
    assert len(qos) == 1 and qos[0].payload["latency_ms"] == 80
    # entity filter
    assert {e.entity_id for e in store.recent(entity_id="ue1")} == {"ue1"}
    # severity floor
    alerts = store.recent(min_severity="alert")
    assert len(alerts) == 1 and alerts[0].entity_id == "ue2"


def test_store_ring_buffer_bound():
    store = EventStore(max_events=5)
    for i in range(9):
        store.append(_ev(entity=f"ue{i}"))
    assert len(store) == 5
    assert store.recent(limit=10)[0].entity_id == "ue8"  # newest kept
    assert all(e.entity_id != "ue0" for e in store.recent(limit=10))  # oldest evicted


def test_store_entities_and_stats():
    store = EventStore()
    store.append(_ev(entity="ue1"))
    store.append(_ev(entity="ue1", domain=EventDomain.QOS))
    store.append(_ev(entity="ue2", severity=Severity.CRITICAL))
    assert set(store.entities()) == {"ue1", "ue2"}
    assert store.entities(domain="qos") == ["ue1"]
    stats = store.stats()
    assert stats["total"] == 3
    assert stats["by_domain"]["location"] == 2
    assert stats["by_severity"]["critical"] == 1
    assert stats["entities"] == 2


# ---- bus ----------------------------------------------------------------------


def test_bus_publishes_to_store_and_subscribers():
    bus = EventBus()
    got = []
    bus.subscribe(got.append)
    bus.publish(_ev(entity="ue1"))
    assert len(bus.store) == 1
    assert got[0].entity_id == "ue1"


def test_bus_domain_filter_and_unsubscribe():
    bus = EventBus()
    qos_only, everything = [], []
    unsub = bus.subscribe(qos_only.append, domain="qos")
    bus.subscribe(everything.append)

    bus.publish(_ev())  # location
    bus.publish(_ev(domain=EventDomain.QOS))
    assert len(qos_only) == 1 and len(everything) == 2

    unsub()
    bus.publish(_ev(domain=EventDomain.QOS))
    assert len(qos_only) == 1  # no longer delivered


def test_bus_isolates_subscriber_errors():
    bus = EventBus()
    bus.subscribe(lambda e: (_ for _ in ()).throw(RuntimeError("bad subscriber")))
    delivered = []
    bus.subscribe(delivered.append)

    bus.publish(_ev())
    assert delivered  # the healthy subscriber still got it
    assert bus.subscriber_errors == 1


def test_publish_all_counts():
    bus = EventBus()
    assert bus.publish_all(_ev(entity=f"ue{i}") for i in range(4)) == 4
    assert len(bus.store) == 4


# ---- legacy shim ----------------------------------------------------------------


@dataclass
class FakeLegacyLocationEvent:
    """Duck-typed stand-in for core_adapter.LocationEvent (same field names)."""

    external_id: str
    cell_id: str
    timestamp: str = "2024-01-15T10:30:00Z"
    event_type: str = "log"
    ipv4_addr: Optional[str] = "10.0.0.9"
    raw_data: Dict[str, Any] = field(default_factory=dict)


def test_shim_converts_legacy_dataclass():
    legacy = FakeLegacyLocationEvent(external_id="ue9@d", cell_id="C9", event_type="alert")
    ev = network_event_from_legacy(legacy)
    assert ev.domain is EventDomain.LOCATION
    assert ev.entity_id == "ue9@d"
    assert ev.payload["cell_id"] == "C9"
    assert ev.severity is Severity.ALERT  # legacy "alert" type preserved
    assert ev.source == "legacy-netapp"
    assert ev.timestamp == "2024-01-15T10:30:00Z"


def test_shim_accepts_legacy_callback_dict():
    ev = network_event_from_legacy(
        {"externalId": "u1", "type": "log", "locationInfo": {"cellId": "A1"}}
    )
    assert ev.domain is EventDomain.LOCATION
    assert ev.payload["cell_id"] == "A1"
    assert ev.severity is Severity.INFO


def test_shim_fills_missing_timestamp():
    legacy = FakeLegacyLocationEvent(external_id="u", cell_id="C", timestamp="")
    assert network_event_from_legacy(legacy).timestamp  # generated, not empty
