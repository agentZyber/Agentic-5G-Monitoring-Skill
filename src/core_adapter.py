from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import json


class CoreType(str, Enum):
    NEF = "nef"
    OPEN5GS = "open5gs"
    FREE5GC = "free5gc"
    UDM_STANDALONE = "udm_standalone"


def default_monitor_expire_time(days: int = 365) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


@dataclass
class LocationEvent:
    external_id: str
    cell_id: str
    timestamp: str
    event_type: str = "location"
    ipv4_addr: Optional[str] = None
    ue_location_timestamp: Optional[str] = None
    age: Optional[int] = None
    raw_data: Optional[Dict[str, Any]] = None
    source_core: Optional[str] = None
    source_core_type: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LocationEvent":
        loc_info = (
            data.get("locationInfo", {})
            if isinstance(data.get("locationInfo"), dict)
            else {}
        )
        return cls(
            external_id=data.get("externalId", ""),
            cell_id=loc_info.get("cellId", ""),
            timestamp=data.get("timestamp", ""),
            event_type=data.get("type", "location"),
            ipv4_addr=data.get("ipv4Addr"),
            ue_location_timestamp=loc_info.get("ueLocationTimestamp"),
            age=loc_info.get("age"),
            raw_data=data,
            source_core=data.get("source_core"),
            source_core_type=data.get("source_core_type"),
        )

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "externalId": self.external_id,
            "type": self.event_type,
            "locationInfo": {
                "cellId": self.cell_id,
                "ueLocationTimestamp": self.ue_location_timestamp,
                "age": self.age,
            },
            "ipv4Addr": self.ipv4_addr,
            "timestamp": self.timestamp,
        }
        if self.source_core:
            data["source_core"] = self.source_core
        if self.source_core_type:
            data["source_core_type"] = self.source_core_type
        return data


@dataclass
class SubscriptionRequest:
    external_id: str
    callback_url: str
    num_of_reports: int = 100
    monitor_expire_time: str = field(default_factory=default_monitor_expire_time)
    netapp_id: str = "zorte_netapp"


@dataclass
class SubscriptionResponse:
    subscription_id: str
    external_id: str
    netapp_id: str
    status: str
    raw_response: Optional[Dict[str, Any]] = None
    core_name: Optional[str] = None


class FiveGCoreAdapter(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._subscribers: Dict[str, Callable] = {}

    @abstractmethod
    def get_type(self) -> CoreType:
        pass

    @abstractmethod
    def get_auth_token(self) -> str:
        pass

    @abstractmethod
    def create_subscription(self, request: SubscriptionRequest) -> SubscriptionResponse:
        pass

    @abstractmethod
    def get_subscriptions(
        self, netapp_id: str, offset: int = 0, limit: int = 100
    ) -> List[SubscriptionResponse]:
        pass

    @abstractmethod
    def delete_subscription(self, subscription_id: str) -> bool:
        pass

    @abstractmethod
    def parse_callback(self, data: Dict[str, Any]) -> LocationEvent:
        pass

    @abstractmethod
    def format_ue_query(self, external_id: str) -> Dict[str, Any]:
        pass

    def on_event(self, callback: Callable[[LocationEvent], None]):
        self._subscribers["event"] = callback

    def emit_event(self, event: LocationEvent):
        if "event" in self._subscribers:
            self._subscribers["event"](event)


class FiveGCoreFactory:
    _adapters: Dict[CoreType, type] = {}

    @classmethod
    def register(cls, core_type: CoreType):
        def decorator(adapter_class: type):
            cls._adapters[core_type] = adapter_class
            return adapter_class

        return decorator

    @classmethod
    def create(cls, core_type: CoreType, config: Dict[str, Any]) -> FiveGCoreAdapter:
        if core_type not in cls._adapters:
            raise ValueError(
                f"Unsupported core type: {core_type}. Available: {list(cls._adapters.keys())}"
            )
        return cls._adapters[core_type](config)

    @classmethod
    def available_cores(cls) -> List[CoreType]:
        return list(cls._adapters.keys())
