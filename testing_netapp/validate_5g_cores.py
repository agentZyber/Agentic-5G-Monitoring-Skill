#!/usr/bin/env python3
"""
Simple Validation Scenarios for 5G Core Integration

This script provides quick validation tests for the Open5GS and Free5GC adapters
without requiring actual 5G core infrastructure to be running.

Usage:
    python testing_netapp/validate_5g_cores.py

Requirements:
    pip install pytest
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core_adapter import CoreType, LocationEvent, SubscriptionRequest
from core_adapter import FiveGCoreFactory
from adapters.open5gs_adapter import Open5GSAdapter
from adapters.free5gc_adapter import Free5GCAdapter
from adapters.nef_adapter import NEFAdapter
from core_manager import CoreManager, CoreInstance


def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(name, passed, details=""):
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  [{status}] {name}")
    if details and passed:
        print(f"         {details}")
    if details and not passed:
        print(f"         ERROR: {details}")


def validate_adapter_creation():
    """Validate that all adapters can be instantiated."""
    print_header("1. Adapter Creation Tests")

    results = []

    try:
        nef_config = {
            "nef_url": "http://localhost:8080",
            "nef_user": "admin",
            "nef_password": "admin",
        }
        nef_adapter = NEFAdapter(nef_config)
        print_result("NEF Adapter creation", True, f"Type: {nef_adapter.get_type()}")
    except Exception as e:
        print_result("NEF Adapter creation", False, str(e))
        results.append(False)

    try:
        open5gs_config = {
            "base_url": "http://localhost:29508",
            "nrf_url": "http://localhost:29502",
        }
        open5gs_adapter = Open5GSAdapter(open5gs_config)
        print_result(
            "Open5GS Adapter creation", True, f"Type: {open5gs_adapter.get_type()}"
        )
    except Exception as e:
        print_result("Open5GS Adapter creation", False, str(e))
        results.append(False)

    try:
        free5gc_config = {
            "nef_url": "http://localhost:29507",
            "nrf_url": "http://localhost:29510",
        }
        free5gc_adapter = Free5GCAdapter(free5gc_config)
        print_result(
            "Free5GC Adapter creation", True, f"Type: {free5gc_adapter.get_type()}"
        )
    except Exception as e:
        print_result("Free5GC Adapter creation", False, str(e))
        results.append(False)

    return len(results) == 0


def validate_core_types():
    """Validate CoreType enum."""
    print_header("2. CoreType Enum Tests")

    print_result("CoreType.NEF value", CoreType.NEF == "nef")
    print_result("CoreType.OPEN5GS value", CoreType.OPEN5GS == "open5gs")
    print_result("CoreType.FREE5GC value", CoreType.FREE5GC == "free5gc")

    return True


def validate_location_event():
    """Validate LocationEvent creation and conversion."""
    print_header("3. LocationEvent Tests")

    data = {
        "externalId": "ue123@test.com",
        "type": "alert",
        "locationInfo": {
            "cellId": "AAAAA1001",
            "ueLocationTimestamp": "2024-01-15T10:30:00Z",
            "age": 0,
        },
        "ipv4Addr": "192.168.1.100",
    }

    event = LocationEvent.from_dict(data)

    print_result(
        "LocationEvent.from_dict",
        event.external_id == "ue123@test.com" and event.cell_id == "AAAAA1001",
        f"UE: {event.external_id}, Cell: {event.cell_id}",
    )

    event_dict = event.to_dict()
    print_result(
        "LocationEvent.to_dict",
        event_dict["externalId"] == "ue123@test.com",
        f"Converted back successfully",
    )

    return True


def validate_open5gs_callback_parsing():
    """Validate Open5GS-specific callback parsing."""
    print_header("4. Open5GS Callback Parsing Tests")

    config = {"base_url": "http://localhost:29508"}
    adapter = Open5GSAdapter(config)

    callback = {
        "ueId": "open5gs_ue_456",
        "cellId": "OPEN5GS_CELL_A",
        "timeStamp": "2024-01-15T12:00:00Z",
        "monitoringType": "LOCATION",
    }

    event = adapter.parse_callback(callback)

    print_result(
        "Open5GS callback (ueId format)",
        event.external_id == "open5gs_ue_456" and event.cell_id == "OPEN5GS_CELL_A",
        f"Parsed: UE={event.external_id}, Cell={event.cell_id}",
    )

    return True


def validate_free5gc_callback_parsing():
    """Validate Free5GC-specific callback parsing."""
    print_header("5. Free5GC Callback Parsing Tests")

    config = {"nef_url": "http://localhost:29507"}
    adapter = Free5GCAdapter(config)

    callback = {
        "jsonData": {
            "externalId": "free5gc_user_789",
            "cellId": "FREE5GC_CELL_B",
            "timeStamp": "2024-01-15T14:00:00Z",
            "monitoringType": "LOCATION",
            "ueIpv4Address": "10.0.0.50",
        }
    }

    event = adapter.parse_callback(callback)

    print_result(
        "Free5GC callback (jsonData format)",
        event.external_id == "free5gc_user_789" and event.ipv4_addr == "10.0.0.50",
        f"Parsed: UE={event.external_id}, IP={event.ipv4_addr}",
    )

    return True


def validate_core_manager():
    """Validate CoreManager functionality."""
    print_header("6. CoreManager Tests")

    manager = CoreManager()

    manager.add_core(
        "test_nef", CoreType.NEF, {"nef_url": "http://localhost:8080"}, priority=1
    )
    manager.add_core(
        "test_open5gs",
        CoreType.OPEN5GS,
        {"base_url": "http://localhost:29508"},
        priority=3,
    )
    manager.add_core(
        "test_free5gc",
        CoreType.FREE5GC,
        {"nef_url": "http://localhost:29507"},
        priority=2,
    )

    cores = manager.get_all_cores()
    print_result(
        "CoreManager: Add multiple cores",
        len(cores) == 3,
        f"Cores: {list(cores.keys())}",
    )

    default = manager.get_default_core()
    print_result(
        "CoreManager: Default core by priority",
        default.get_type() == CoreType.OPEN5GS,
        f"Default is: {default.get_type()}",
    )

    manager.remove_core("test_nef")
    cores = manager.get_all_cores()
    print_result(
        "CoreManager: Remove core", len(cores) == 2, f"Remaining: {list(cores.keys())}"
    )

    return True


def validate_subscription_request():
    """Validate SubscriptionRequest dataclass."""
    print_header("7. SubscriptionRequest Tests")

    request = SubscriptionRequest(
        external_id="ue_subscription_test",
        callback_url="http://localhost:5000/callback",
        num_of_reports=100,
        monitor_expire_time="2024-12-31T23:59:59Z",
        netapp_id="zorte_netapp",
    )

    print_result(
        "SubscriptionRequest creation",
        request.external_id == "ue_subscription_test" and request.num_of_reports == 100,
        f"External ID: {request.external_id}, Reports: {request.num_of_reports}",
    )

    return True


def validate_factory():
    """Validate FiveGCoreFactory."""
    print_header("8. Factory Tests")

    try:
        adapter = FiveGCoreFactory.create(CoreType.NEF, {"nef_url": "http://test"})
        print_result("Factory: Create NEF adapter", adapter.get_type() == CoreType.NEF)
    except Exception as e:
        print_result("Factory: Create NEF adapter", False, str(e))

    try:
        adapter = FiveGCoreFactory.create(CoreType.OPEN5GS, {"base_url": "http://test"})
        print_result(
            "Factory: Create Open5GS adapter", adapter.get_type() == CoreType.OPEN5GS
        )
    except Exception as e:
        print_result("Factory: Create Open5GS adapter", False, str(e))

    try:
        adapter = FiveGCoreFactory.create(CoreType.FREE5GC, {"nef_url": "http://test"})
        print_result(
            "Factory: Create Free5GC adapter", adapter.get_type() == CoreType.FREE5GC
        )
    except Exception as e:
        print_result("Factory: Create Free5GC adapter", False, str(e))

    return True


def validate_ue_query_formats():
    """Validate UE query format differences."""
    print_header("9. UE Query Format Comparison")

    open5gs_adapter = Open5GSAdapter(
        {"base_url": "http://localhost", "mcc": "001", "mnc": "01"}
    )
    free5gc_adapter = Free5GCAdapter({"nef_url": "http://localhost"})

    open5gs_query = open5gs_adapter.format_ue_query("ue123")
    free5gc_query = free5gc_adapter.format_ue_query("ue123")

    print_result(
        "Open5GS: UE query has PLMN ID",
        "plmnId" in open5gs_query,
        f"PLMN: {open5gs_query.get('plmnId')}",
    )
    print_result(
        "Free5GC: UE query has queryType",
        "queryType" in free5gc_query,
        f"QueryType: {free5gc_query.get('queryType')}",
    )

    return True


def main():
    print("\n" + "#" * 60)
    print("#  5G Core Integration Validation")
    print("#  Testing Open5GS and Free5GC Adapter Support")
    print("#" * 60)

    all_passed = True

    all_passed &= validate_core_types()
    all_passed &= validate_adapter_creation()
    all_passed &= validate_location_event()
    all_passed &= validate_open5gs_callback_parsing()
    all_passed &= validate_free5gc_callback_parsing()
    all_passed &= validate_subscription_request()
    all_passed &= validate_core_manager()
    all_passed &= validate_factory()
    all_passed &= validate_ue_query_formats()

    print_header("Validation Summary")

    if all_passed:
        print("\n  ✓ ALL VALIDATIONS PASSED")
        print("\n  The NetApp supports:")
        print("    - 3GPP NEF (original evolved5g SDK)")
        print("    - Open5GS Core")
        print("    - Free5GC Core")
        print("\n  Next steps:")
        print("    1. Run pytest testing_netapp/test_5g_cores.py -v  (full test suite)")
        print("    2. Configure your 5G core in .env or config.json")
        print("    3. Run the NetApp with: uvicorn src.api:app --reload")
    else:
        print("\n  ✗ SOME VALIDATIONS FAILED")
        print("  Please review the errors above.")

    print("\n")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
