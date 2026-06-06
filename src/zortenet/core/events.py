"""Generalized network event model.

The original ZorteNet hard-coded a single ``LocationEvent`` (cell id + mobility). That is the
narrowness this toolkit exists to remove: every event in the platform was about *where a UE is*.

``NetworkEvent`` generalizes that to **any** network observation across domains (location, QoS,
throughput, slice, energy, security, RAN KPIs, signaling, application), while remaining
backward-compatible with the legacy location callback shape via :func:`NetworkEvent.from_location_event`.

A ``NetworkEvent`` is intentionally a thin, serializable record — connectors emit it, the bus
distributes it, the RAG store textualizes it (:meth:`text_repr`), and capability packs reason over it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventDomain(str, Enum):
    """The kind of network observation an event represents."""

    LOCATION = "location"        # UE location / mobility (the legacy ZorteNet domain)
    QOS = "qos"                  # QoS monitoring / flow QoS notifications
    THROUGHPUT = "throughput"    # data-volume / bitrate telemetry
    SLICE = "slice"              # network-slice (S-NSSAI) state and load
    ENERGY = "energy"            # power / energy-efficiency KPIs
    SECURITY = "security"        # auth failures, signaling anomalies, policy breaches
    RAN_KPI = "ran_kpi"          # O-RAN / E2-KPM radio measurements (PRB, CQI, ...)
    SIGNALING = "signaling"      # NAS/NGAP/SBI control-plane events
    APP = "app"                  # application-layer / edge events
    UNKNOWN = "unknown"

    @classmethod
    def coerce(cls, value: Any) -> "EventDomain":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).lower())
        except ValueError:
            return cls.UNKNOWN


class Severity(str, Enum):
    """Severity ranking used for alerting and triage."""

    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"
    CRITICAL = "critical"

    @classmethod
    def coerce(cls, value: Any) -> "Severity":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).lower())
        except ValueError:
            return cls.INFO


@dataclass
class NetworkEvent:
    """A single, domain-tagged network observation.

    Attributes:
        domain: which :class:`EventDomain` this observation belongs to.
        source: the connector / core that produced it (e.g. ``"open5gs"``, ``"prometheus"``).
        entity_id: the primary entity the event is about — a UE external id, cell id, slice id,
            or NF instance id. May be ``None`` for network-wide events.
        timestamp: ISO-8601 UTC timestamp (defaults to now).
        payload: domain-specific fields (e.g. ``{"cell_id": ...}`` for LOCATION,
            ``{"prb_usage": ...}`` for RAN_KPI).
        severity: :class:`Severity` for triage / alerting.
        event_type: free-form subtype within the domain (e.g. ``"LOCATION_REPORTING"``).
        raw: the untouched source payload, for debugging and lossless re-export.
    """

    domain: EventDomain
    source: str
    entity_id: Optional[str] = None
    timestamp: str = field(default_factory=_utcnow_iso)
    payload: Dict[str, Any] = field(default_factory=dict)
    severity: Severity = Severity.INFO
    event_type: str = ""
    raw: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        self.domain = EventDomain.coerce(self.domain)
        self.severity = Severity.coerce(self.severity)

    # ---- serialization -------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "domain": self.domain.value,
            "source": self.source,
            "entity_id": self.entity_id,
            "timestamp": self.timestamp,
            "payload": dict(self.payload),
            "severity": self.severity.value,
            "event_type": self.event_type,
        }
        # Preserve the raw source payload when present so to_dict/from_dict is lossless.
        if self.raw is not None:
            data["raw"] = self.raw
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NetworkEvent":
        return cls(
            domain=EventDomain.coerce(data.get("domain", EventDomain.UNKNOWN)),
            source=data.get("source", "unknown"),
            entity_id=data.get("entity_id"),
            timestamp=data.get("timestamp") or _utcnow_iso(),
            payload=dict(data.get("payload", {})),
            severity=Severity.coerce(data.get("severity", Severity.INFO)),
            event_type=data.get("event_type", ""),
            raw=data.get("raw"),
        )

    # ---- backward compatibility ---------------------------------------

    @classmethod
    def from_location_event(cls, data: Dict[str, Any], source: str = "nef") -> "NetworkEvent":
        """Bridge the legacy ZorteNet location callback shape into a NetworkEvent.

        Legacy shape::

            {"externalId": "ue@d", "type": "alert"|"log",
             "ipv4Addr": "10.0.0.1",
             "locationInfo": {"cellId": "...", "ueLocationTimestamp": "...", "age": 0}}
        """
        loc = data.get("locationInfo") if isinstance(data.get("locationInfo"), dict) else {}
        legacy_type = str(data.get("type", "")).lower()
        severity = Severity.ALERT if legacy_type == "alert" else Severity.INFO

        payload: Dict[str, Any] = {
            "cell_id": loc.get("cellId"),
            "ue_location_timestamp": loc.get("ueLocationTimestamp"),
            "age": loc.get("age"),
            "ipv4_addr": data.get("ipv4Addr"),
        }
        return cls(
            domain=EventDomain.LOCATION,
            source=data.get("source_core") or source,
            entity_id=data.get("externalId"),
            timestamp=data.get("timestamp") or loc.get("ueLocationTimestamp") or _utcnow_iso(),
            payload={k: v for k, v in payload.items() if v is not None},
            severity=severity,
            event_type=data.get("type") or "LOCATION_REPORTING",
            raw=data,
        )

    # ---- RAG textualization -------------------------------------------

    def text_repr(self) -> str:
        """Human/embedding-friendly one-line representation for semantic search.

        Generalizes the legacy ``vector_store._event_to_text`` (which only knew location
        fields) to every domain, so RAG works for QoS, energy, security, etc. — not just cells.
        """
        head = f"[{self.domain.value}] source={self.source}"
        if self.entity_id:
            head += f" entity={self.entity_id}"
        if self.event_type:
            head += f" type={self.event_type}"
        head += f" severity={self.severity.value}"

        # Domain-aware key fields first, then a generic dump of the rest.
        salient_keys = {
            EventDomain.LOCATION: ["cell_id", "age", "ipv4_addr"],
            EventDomain.QOS: ["qfi", "qos_status", "latency_ms", "jitter_ms"],
            EventDomain.THROUGHPUT: ["dl_mbps", "ul_mbps", "volume_bytes"],
            EventDomain.SLICE: ["snssai", "load_pct", "active_sessions"],
            EventDomain.ENERGY: ["watts", "energy_kwh", "efficiency"],
            EventDomain.SECURITY: ["cause", "policy_id", "cell_id"],
            EventDomain.RAN_KPI: ["prb_usage", "cqi", "rsrp", "rsrq"],
        }.get(self.domain, [])

        parts = []
        seen = set()
        for key in salient_keys:
            if key in self.payload and self.payload[key] is not None:
                parts.append(f"{key}={self.payload[key]}")
                seen.add(key)
        for key, value in self.payload.items():
            if key not in seen and value is not None:
                parts.append(f"{key}={value}")

        body = " | ".join(parts)
        return f"{head} | {body}" if body else head
