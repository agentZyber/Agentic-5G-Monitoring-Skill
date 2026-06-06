"""Unit tests for the generalized NetworkEvent model."""

from zortenet.core.events import EventDomain, NetworkEvent, Severity


def test_network_event_roundtrip():
    ev = NetworkEvent(
        domain=EventDomain.QOS,
        source="open5gs",
        entity_id="ue123@domain.com",
        payload={"qfi": 5, "latency_ms": 42},
        severity=Severity.WARNING,
        event_type="QOS_MONITORING",
    )
    restored = NetworkEvent.from_dict(ev.to_dict())
    assert restored.domain is EventDomain.QOS
    assert restored.source == "open5gs"
    assert restored.entity_id == "ue123@domain.com"
    assert restored.payload["latency_ms"] == 42
    assert restored.severity is Severity.WARNING
    assert restored.event_type == "QOS_MONITORING"


def test_roundtrip_preserves_raw_when_present():
    # Regression: to_dict must keep `raw` so to_dict/from_dict is lossless (matches the docstring).
    ev = NetworkEvent(domain=EventDomain.QOS, source="open5gs", raw={"orig": 1})
    d = ev.to_dict()
    assert d["raw"] == {"orig": 1}
    assert NetworkEvent.from_dict(d).raw == {"orig": 1}
    # When raw is absent, the dict stays clean (no null `raw` key).
    assert "raw" not in NetworkEvent(domain=EventDomain.QOS, source="x").to_dict()


def test_domain_and_severity_coercion_is_lenient():
    ev = NetworkEvent(domain="ran_kpi", source="oran", severity="critical")
    assert ev.domain is EventDomain.RAN_KPI
    assert ev.severity is Severity.CRITICAL

    unknown = NetworkEvent(domain="not-a-domain", source="x", severity="nonsense")
    assert unknown.domain is EventDomain.UNKNOWN
    assert unknown.severity is Severity.INFO  # falls back, never raises


def test_from_location_event_bridges_legacy_shape():
    legacy = {
        "externalId": "ue456@domain.com",
        "type": "alert",
        "ipv4Addr": "10.0.0.2",
        "locationInfo": {
            "cellId": "UNAUTH_CELL",
            "ueLocationTimestamp": "2024-01-15T10:35:00Z",
            "age": 0,
        },
    }
    ev = NetworkEvent.from_location_event(legacy)
    assert ev.domain is EventDomain.LOCATION
    assert ev.entity_id == "ue456@domain.com"
    assert ev.payload["cell_id"] == "UNAUTH_CELL"
    assert ev.payload["ipv4_addr"] == "10.0.0.2"
    # legacy "alert" type must map to ALERT severity (preserves geofence semantics)
    assert ev.severity is Severity.ALERT
    assert ev.raw is legacy


def test_from_location_event_log_is_info_severity():
    ev = NetworkEvent.from_location_event({"externalId": "u", "type": "log", "locationInfo": {}})
    assert ev.severity is Severity.INFO
    assert ev.domain is EventDomain.LOCATION


def test_text_repr_is_domain_aware():
    loc = NetworkEvent(
        domain=EventDomain.LOCATION, source="open5gs", entity_id="u1", payload={"cell_id": "C1"}
    )
    txt = loc.text_repr()
    assert "[location]" in txt
    assert "entity=u1" in txt
    assert "cell_id=C1" in txt

    ran = NetworkEvent(
        domain=EventDomain.RAN_KPI, source="oran", payload={"prb_usage": 0.91, "cqi": 12}
    )
    ran_txt = ran.text_repr()
    assert "[ran_kpi]" in ran_txt
    assert "prb_usage=0.91" in ran_txt
    assert "cqi=12" in ran_txt
    # A RAN event must NOT be described with location vocabulary (the legacy narrowness).
    assert "cell_id" not in ran_txt


def test_text_repr_handles_empty_payload():
    ev = NetworkEvent(domain=EventDomain.SIGNALING, source="amf")
    assert ev.text_repr().startswith("[signaling] source=amf")
