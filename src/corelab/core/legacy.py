"""Legacy-convergence shim: the original NetApp's events → NetworkEvent.

The legacy ``core_adapter.LocationEvent`` (a dataclass with ``external_id``, ``cell_id``,
``timestamp``, ``event_type``, ``ipv4_addr``, ``raw_data``) and the legacy callback dict shape
both normalize into a :class:`~corelab.core.events.NetworkEvent` here. The shim is duck-typed —
it never imports the legacy module — so the toolkit stays light and the legacy app can adopt it
with one call: ``bus.publish(network_event_from_legacy(event))``.

(The actual one-line wiring inside ``src/api.py`` is applied at live bring-up, where the legacy
app's heavy dependency set can be installed and its test suite run — see IMPLEMENTATION_PLAN
Stage 2.)
"""

from __future__ import annotations

from typing import Any, Dict

from corelab.core.events import EventDomain, NetworkEvent, Severity, _utcnow_iso


def network_event_from_legacy(event: Any, source: str = "legacy-netapp") -> NetworkEvent:
    """Normalize a legacy LocationEvent-like object or legacy callback dict.

    Accepts:
    - an object with ``external_id`` / ``cell_id`` / ``timestamp`` / ``event_type`` attributes
      (the legacy ``core_adapter.LocationEvent`` dataclass, duck-typed);
    - the legacy callback dict (``externalId`` / ``locationInfo`` …) — delegated to
      :meth:`NetworkEvent.from_location_event`.
    """
    if isinstance(event, dict):
        return NetworkEvent.from_location_event(event, source=source)

    cell_id = getattr(event, "cell_id", None)
    event_type = str(getattr(event, "event_type", "") or "LOCATION_REPORTING")
    severity = Severity.ALERT if event_type.lower() == "alert" else Severity.INFO

    payload: Dict[str, Any] = {
        "cell_id": cell_id,
        "ipv4_addr": getattr(event, "ipv4_addr", None),
    }
    return NetworkEvent(
        domain=EventDomain.LOCATION,
        source=source,
        entity_id=getattr(event, "external_id", None),
        timestamp=getattr(event, "timestamp", None) or _utcnow_iso(),
        payload={k: v for k, v in payload.items() if v is not None},
        severity=severity,
        event_type=event_type,
        raw=getattr(event, "raw_data", None),
    )
