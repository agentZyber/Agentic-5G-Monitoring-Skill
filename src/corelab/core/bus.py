"""Event bus + store — the multi-domain heart of the toolkit.

``EventBus`` distributes :class:`~corelab.core.events.NetworkEvent`s to subscribers and feeds an
``EventStore`` — a bounded in-memory ring buffer the agent tools query (recent events, per-entity
history, domain/severity stats). This is what replaces the legacy app's location-only flow:
*any* connector (core callback, Prometheus scrape, replayed 5G3E telemetry) publishes here, and
*any* pack (security-sentinel, self-heal, netops-copilot) reads from here.

Deliberately in-memory and bounded for Stage 2: durable persistence (and the Chroma-backed
semantic index) layer on top later without changing this interface.
"""

from __future__ import annotations

import threading
from collections import Counter, deque
from typing import Any, Callable, Dict, Iterable, List, Optional

from corelab.core.events import EventDomain, NetworkEvent, Severity

Subscriber = Callable[[NetworkEvent], None]


class EventStore:
    """Bounded ring buffer of events with simple query/stat helpers."""

    def __init__(self, max_events: int = 10_000) -> None:
        self._events: deque[NetworkEvent] = deque(maxlen=max_events)
        self._lock = threading.Lock()

    def append(self, event: NetworkEvent) -> None:
        with self._lock:
            self._events.append(event)

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)

    def recent(
        self,
        domain: Optional[EventDomain | str] = None,
        entity_id: Optional[str] = None,
        min_severity: Optional[Severity | str] = None,
        limit: int = 100,
    ) -> List[NetworkEvent]:
        """Most-recent-first filtered view."""
        dom = EventDomain.coerce(domain) if domain is not None else None
        severity_order = list(Severity)
        min_rank = (
            severity_order.index(Severity.coerce(min_severity))
            if min_severity is not None
            else 0
        )
        with self._lock:
            snapshot = list(self._events)
        out: List[NetworkEvent] = []
        for event in reversed(snapshot):
            if dom is not None and event.domain is not dom:
                continue
            if entity_id is not None and event.entity_id != entity_id:
                continue
            if severity_order.index(event.severity) < min_rank:
                continue
            out.append(event)
            if len(out) >= limit:
                break
        return out

    def entities(self, domain: Optional[EventDomain | str] = None) -> List[str]:
        dom = EventDomain.coerce(domain) if domain is not None else None
        with self._lock:
            snapshot = list(self._events)
        seen: Dict[str, None] = {}
        for event in snapshot:
            if event.entity_id and (dom is None or event.domain is dom):
                seen.setdefault(event.entity_id, None)
        return list(seen)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            snapshot = list(self._events)
        return {
            "total": len(snapshot),
            "by_domain": dict(Counter(e.domain.value for e in snapshot)),
            "by_severity": dict(Counter(e.severity.value for e in snapshot)),
            "entities": len({e.entity_id for e in snapshot if e.entity_id}),
        }


class EventBus:
    """Synchronous pub/sub over NetworkEvents, feeding an EventStore.

    Subscriber errors are isolated (a bad subscriber never breaks publishing) and counted.
    """

    def __init__(self, store: Optional[EventStore] = None) -> None:
        self.store = store or EventStore()
        self._subscribers: List[tuple[Optional[EventDomain], Subscriber]] = []
        self._lock = threading.Lock()
        self.subscriber_errors = 0

    def subscribe(
        self, callback: Subscriber, domain: Optional[EventDomain | str] = None
    ) -> Callable[[], None]:
        """Register a callback (optionally domain-filtered); returns an unsubscribe function."""
        dom = EventDomain.coerce(domain) if domain is not None else None
        entry = (dom, callback)
        with self._lock:
            self._subscribers.append(entry)

        def unsubscribe() -> None:
            with self._lock:
                if entry in self._subscribers:
                    self._subscribers.remove(entry)

        return unsubscribe

    def publish(self, event: NetworkEvent) -> NetworkEvent:
        self.store.append(event)
        with self._lock:
            subscribers = list(self._subscribers)
        for dom, callback in subscribers:
            if dom is not None and event.domain is not dom:
                continue
            try:
                callback(event)
            except Exception:
                self.subscriber_errors += 1
        return event

    def publish_all(self, events: Iterable[NetworkEvent]) -> int:
        count = 0
        for event in events:
            self.publish(event)
            count += 1
        return count
