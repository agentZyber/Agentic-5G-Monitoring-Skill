import os
import json
from typing import Dict, Any, Optional, List, Callable
from threading import Lock
from dataclasses import dataclass, field

from core_adapter import (
    CoreType,
    FiveGCoreAdapter,
    FiveGCoreFactory,
    LocationEvent,
    SubscriptionRequest,
    SubscriptionResponse,
)
from vector_store import context_vector_store


@dataclass
class CoreInstance:
    name: str
    adapter: FiveGCoreAdapter
    enabled: bool = True
    priority: int = 0


class CoreManager:
    """
    Manages multiple 5G Core connections and provides unified event processing.

    Supports:
    - Multiple simultaneous core connections
    - Automatic failover
    - Core-agnostic event processing
    - Unified subscription management
    """

    def __init__(self):
        self._cores: Dict[str, CoreInstance] = {}
        self._lock = Lock()
        self._event_handlers: List[Callable] = []
        self._default_core: Optional[str] = None

    def add_core(
        self,
        name: str,
        core_type: CoreType,
        config: Dict[str, Any],
        enabled: bool = True,
        priority: int = 0,
    ) -> bool:
        with self._lock:
            try:
                adapter = FiveGCoreFactory.create(core_type, config)
                self._cores[name] = CoreInstance(
                    name=name, adapter=adapter, enabled=enabled, priority=priority
                )

                if (
                    self._default_core is None
                    or priority > self._cores[self._default_core].priority
                ):
                    self._default_core = name

                return True
            except Exception as e:
                print(f"Failed to add core {name}: {e}")
                return False

    def remove_core(self, name: str) -> bool:
        with self._lock:
            if name in self._cores:
                del self._cores[name]
                if self._default_core == name:
                    self._default_core = (
                        next(iter(self._cores.keys())) if self._cores else None
                    )
                return True
            return False

    def get_core(self, name: str) -> Optional[FiveGCoreAdapter]:
        with self._lock:
            core = self._cores.get(name)
            return core.adapter if core else None

    def get_default_core(self) -> Optional[FiveGCoreAdapter]:
        with self._lock:
            if self._default_core and self._default_core in self._cores:
                return self._cores[self._default_core].adapter
            return None

    def get_all_cores(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {
                name: {
                    "type": core.adapter.get_type().value,
                    "enabled": core.enabled,
                    "priority": core.priority,
                    "is_default": name == self._default_core,
                }
                for name, core in self._cores.items()
            }

    def create_subscription(
        self, external_id: str, callback_url: str, **kwargs
    ) -> Optional[SubscriptionResponse]:
        with self._lock:
            cores_to_try = sorted(
                [c for c in self._cores.values() if c.enabled],
                key=lambda x: -x.priority,
            )

            for core in cores_to_try:
                try:
                    request = SubscriptionRequest(
                        external_id=external_id,
                        callback_url=callback_url,
                        num_of_reports=kwargs.get("num_of_reports", 100),
                        monitor_expire_time=kwargs.get(
                            "exp_time", "2024-12-31T23:59:59Z"
                        ),
                        netapp_id=kwargs.get("netapp_id", "zorte_netapp"),
                    )
                    response = core.adapter.create_subscription(request)
                    if response.status == "active":
                        return response
                except Exception as e:
                    print(f"Core {core.name} subscription failed: {e}")
                    continue

            return None

    def get_all_subscriptions(self, netapp_id: str) -> List[Dict[str, Any]]:
        all_subs = []

        with self._lock:
            for name, core in self._cores.items():
                if not core.enabled:
                    continue
                try:
                    subs = core.adapter.get_subscriptions(netapp_id)
                    for sub in subs:
                        all_subs.append(
                            {
                                "core": name,
                                "subscription_id": sub.subscription_id,
                                "external_id": sub.external_id,
                                "status": sub.status,
                                "raw": sub.raw_response,
                            }
                        )
                except Exception:
                    continue

        return all_subs

    def process_callback(
        self, data: Dict[str, Any], source_core: Optional[str] = None
    ) -> LocationEvent:
        adapter = None

        if source_core:
            adapter = self.get_core(source_core)

        if adapter is None:
            adapter = self.get_default_core()

        if adapter is None:
            raise ValueError("No 5G core adapter available")

        event = adapter.parse_callback(data)

        context_vector_store.add_event(event.to_dict())

        for handler in self._event_handlers:
            try:
                handler(event, adapter.get_type().value)
            except Exception as e:
                print(f"Event handler error: {e}")

        return event

    def on_event(self, handler: Callable[[LocationEvent, str], None]):
        self._event_handlers.append(handler)

    def query_ue_location(
        self, external_id: str, core_name: Optional[str] = None
    ) -> Optional[LocationEvent]:
        adapter = None

        if core_name:
            adapter = self.get_core(core_name)
        else:
            adapter = self.get_default_core()

        if adapter is None:
            return None

        return adapter.get_ue_location(external_id)

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "cores": self.get_all_cores(),
                "default_core": self._default_core,
                "event_handlers_count": len(self._event_handlers),
                "vector_store_available": context_vector_store.rag_available,
            }


class ConfigLoader:
    """Load 5G core configurations from environment or config file."""

    @staticmethod
    def load_from_env() -> Dict[str, Dict[str, Any]]:
        configs = {}

        core_type = os.environ.get("CORE_TYPE", "nef").lower()

        if core_type == "open5gs":
            configs["default"] = {
                "type": CoreType.OPEN5GS,
                "config": {
                    "base_url": os.environ.get(
                        "OPEN5GS_BASE_URL", "http://localhost:29508"
                    ),
                    "nrf_url": os.environ.get(
                        "OPEN5GS_NRF_URL", "http://localhost:29502"
                    ),
                    "api_key": os.environ.get("OPEN5GS_API_KEY", ""),
                    "username": os.environ.get("OPEN5GS_USERNAME", ""),
                    "password": os.environ.get("OPEN5GS_PASSWORD", ""),
                    "mcc": os.environ.get("MCC", "001"),
                    "mnc": os.environ.get("MNC", "01"),
                },
            }
        elif core_type == "free5gc":
            configs["default"] = {
                "type": CoreType.FREE5GC,
                "config": {
                    "nef_url": os.environ.get(
                        "FREE5GC_NEF_URL", "http://localhost:29507"
                    ),
                    "nrf_url": os.environ.get(
                        "FREE5GC_NRF_URL", "http://localhost:29510"
                    ),
                    "api_key": os.environ.get("FREE5GC_API_KEY", ""),
                    "client_id": os.environ.get("FREE5GC_CLIENT_ID", "netapp"),
                    "client_secret": os.environ.get(
                        "FREE5GC_CLIENT_SECRET", "free5gcsecret"
                    ),
                },
            }
        else:
            configs["default"] = {
                "type": CoreType.NEF,
                "config": {
                    "nef_url": os.environ.get("NEF_ADDRESS", "http://localhost:8080"),
                    "nef_user": os.environ.get("NEF_USER", "admin"),
                    "nef_password": os.environ.get("NEF_PASSWORD", "admin"),
                    "capif_host": os.environ.get("CAPIF_HOSTNAME", ""),
                    "capif_https_port": int(os.environ.get("CAPIF_PORT_HTTPS", "8080")),
                    "path_to_certs": os.environ.get("PATH_TO_CERTS", "./capif_certs"),
                },
            }

        return configs

    @staticmethod
    def load_from_file(filepath: str) -> Dict[str, Dict[str, Any]]:
        with open(filepath, "r") as f:
            data = json.load(f)

        configs = {}

        for name, core_config in data.get("cores", {}).items():
            core_type = CoreType(core_config.get("type", "nef"))
            configs[name] = {
                "type": core_type,
                "config": core_config.get("config", {}),
                "enabled": core_config.get("enabled", True),
                "priority": core_config.get("priority", 0),
            }

        return configs


core_manager = CoreManager()


def initialize_cores():
    """Initialize cores from environment or defaults."""
    configs = ConfigLoader.load_from_env()

    for name, cfg in configs.items():
        core_manager.add_core(
            name=name,
            core_type=cfg["type"],
            config=cfg["config"],
            enabled=True,
            priority=1,
        )
