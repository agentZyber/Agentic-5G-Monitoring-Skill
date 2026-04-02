"""
Test Scenarios for 5G Core Integration (Open5GS & Free5GC)

This module contains end-to-end test scenarios for validating the NetApp
functionality with different 5G core implementations.

Run with: pytest testing_netapp/test_5g_cores.py -v
"""

import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestOpen5GSAdapter:
    """Test suite for Open5GS adapter."""

    @pytest.fixture
    def open5gs_config(self):
        return {
            "base_url": "http://localhost:29508",
            "nrf_url": "http://localhost:29502",
            "api_key": "test_api_key",
            "client_id": "netapp",
            "client_secret": "secret",
            "mcc": "001",
            "mnc": "01",
        }

    @pytest.fixture
    def open5gs_adapter(self, open5gs_config):
        from adapters.open5gs_adapter import Open5GSAdapter

        with patch("requests.Session") as mock_session:
            mock_client = MagicMock()
            mock_session.return_value = mock_client
            adapter = Open5GSAdapter(open5gs_config)
            adapter.client = mock_client
            yield adapter

    def test_adapter_type(self, open5gs_adapter):
        from core_adapter import CoreType

        assert open5gs_adapter.get_type() == CoreType.OPEN5GS

    def test_get_auth_token_success(self, open5gs_adapter):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "token123"}
        open5gs_adapter.client.post.return_value = mock_response

        token = open5gs_adapter.get_auth_token()
        assert token == "token123"

    def test_get_auth_token_failure(self, open5gs_adapter):
        mock_response = Mock()
        mock_response.status_code = 401
        open5gs_adapter.client.post.side_effect = Exception("Connection refused")
        open5gs_adapter.nrf_url = "http://invalid:9999"

        token = open5gs_adapter.get_auth_token()
        assert token == ""

    def test_create_subscription_success(self, open5gs_adapter):
        from core_adapter import SubscriptionRequest

        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"access_token": "token123"}
        open5gs_adapter.client.post.return_value = mock_token_response

        mock_sub_response = Mock()
        mock_sub_response.status_code = 201
        mock_sub_response.json.return_value = {
            "subscriptionId": "sub_123",
            "ueId": "ue123",
        }
        open5gs_adapter.client.post.return_value = mock_sub_response

        request = SubscriptionRequest(
            external_id="ue123",
            callback_url="http://localhost:5000/callback",
            num_of_reports=100,
        )

        response = open5gs_adapter.create_subscription(request)

        assert response.subscription_id == "sub_123"
        assert response.external_id == "ue123"
        assert response.status == "active"

    def test_create_subscription_failure(self, open5gs_adapter):
        from core_adapter import SubscriptionRequest

        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"access_token": "token123"}
        open5gs_adapter.client.post.return_value = mock_token_response

        mock_sub_response = Mock()
        mock_sub_response.status_code = 500
        mock_sub_response.text = "Internal Server Error"
        open5gs_adapter.client.post.return_value = mock_sub_response

        request = SubscriptionRequest(
            external_id="ue123", callback_url="http://localhost:5000/callback"
        )

        response = open5gs_adapter.create_subscription(request)
        assert response.subscription_id == ""
        assert "failed" in response.status

    def test_parse_callback_with_ue_id(self, open5gs_adapter):
        callback_data = {
            "ueId": "ue456",
            "cellId": "cellA",
            "timeStamp": "2024-01-15T10:00:00Z",
            "monitoringType": "LOCATION",
        }

        event = open5gs_adapter.parse_callback(callback_data)

        assert event.external_id == "ue456"
        assert event.cell_id == "cellA"
        assert event.event_type == "LOCATION"

    def test_parse_callback_with_external_id(self, open5gs_adapter):
        callback_data = {
            "externalId": "ue789",
            "type": "log",
            "locationInfo": {"cellId": "cellB"},
        }

        event = open5gs_adapter.parse_callback(callback_data)

        assert event.external_id == "ue789"
        assert event.cell_id == "cellB"

    def test_get_subscriptions(self, open5gs_adapter):
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"access_token": "token123"}
        open5gs_adapter.client.get.return_value = mock_token_response

        mock_subs_response = Mock()
        mock_subs_response.status_code = 200
        mock_subs_response.json.return_value = {
            "subscriptions": [
                {"subscriptionId": "sub_1", "ueId": "ue1"},
                {"subscriptionId": "sub_2", "ueId": "ue2"},
            ]
        }
        open5gs_adapter.client.get.return_value = mock_subs_response

        subs = open5gs_adapter.get_subscriptions("netapp")
        assert len(subs) == 2

    def test_delete_subscription(self, open5gs_adapter):
        mock_response = Mock()
        mock_response.status_code = 204
        open5gs_adapter.client.delete.return_value = mock_response

        result = open5gs_adapter.delete_subscription("sub_123")
        assert result is True

    def test_format_ue_query(self, open5gs_adapter):
        query = open5gs_adapter.format_ue_query("ue123")
        assert query["ueId"] == "ue123"
        assert query["plmnId"]["mcc"] == "001"
        assert query["plmnId"]["mnc"] == "01"


class TestFree5GCAdapter:
    """Test suite for Free5GC adapter."""

    @pytest.fixture
    def free5gc_config(self):
        return {
            "nef_url": "http://localhost:29507",
            "nrf_url": "http://localhost:29510",
            "api_key": "free5gc_key",
            "client_id": "netapp",
            "client_secret": "free5gcsecret",
        }

    @pytest.fixture
    def free5gc_adapter(self, free5gc_config):
        from adapters.free5gc_adapter import Free5GCAdapter

        with patch("requests.Session") as mock_session:
            mock_client = MagicMock()
            mock_session.return_value = mock_client
            adapter = Free5GCAdapter(free5gc_config)
            adapter.client = mock_client
            yield adapter

    def test_adapter_type(self, free5gc_adapter):
        from core_adapter import CoreType

        assert free5gc_adapter.get_type() == CoreType.FREE5GC

    def test_get_auth_token(self, free5gc_adapter):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "free5gc_token"}
        free5gc_adapter.client.post.return_value = mock_response

        token = free5gc_adapter.get_auth_token()
        assert token == "free5gc_token"

    def test_create_subscription(self, free5gc_adapter):
        from core_adapter import SubscriptionRequest

        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"access_token": "token"}
        free5gc_adapter.client.post.return_value = mock_token_response

        mock_sub_response = Mock()
        mock_sub_response.status_code = 201
        mock_sub_response.json.return_value = {"subscriptionId": "free5gc_sub_123"}
        free5gc_adapter.client.post.return_value = mock_sub_response

        request = SubscriptionRequest(
            external_id="ue_free5gc",
            callback_url="http://localhost:5000/callback",
            num_of_reports=50,
        )

        response = free5gc_adapter.create_subscription(request)
        assert response.subscription_id == "free5gc_sub_123"

    def test_parse_callback_with_json_data(self, free5gc_adapter):
        callback_data = {
            "jsonData": {
                "externalId": "ue_123",
                "cellId": "free5gc_cell",
                "timeStamp": "2024-01-15T12:00:00Z",
                "monitoringType": "LOCATION",
                "ueIpv4Address": "10.0.0.5",
            }
        }

        event = free5gc_adapter.parse_callback(callback_data)

        assert event.external_id == "ue_123"
        assert event.cell_id == "free5gc_cell"
        assert event.ipv4_addr == "10.0.0.5"
        assert event.event_type == "LOCATION"

    def test_parse_callback_external_id_format(self, free5gc_adapter):
        callback_data = {
            "externalId": "user@free5gc.domain",
            "type": "alert",
            "locationInfo": {"cellId": "cellX"},
        }

        event = free5gc_adapter.parse_callback(callback_data)

        assert event.external_id == "user@free5gc.domain"
        assert event.cell_id == "cellX"

    def test_get_ue_slice_info(self, free5gc_adapter):
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"access_token": "token"}
        free5gc_adapter.client.get.return_value = mock_token_response

        mock_slice_response = Mock()
        mock_slice_response.status_code = 200
        mock_slice_response.json.return_value = {"sliceInfo": {"sst": "1", "sd": "001"}}
        free5gc_adapter.client.get.return_value = mock_slice_response

        slice_info = free5gc_adapter.get_ue_slice_info("ue123")
        assert slice_info["sliceInfo"]["sst"] == "1"

    def test_get_ue_qos_flows(self, free5gc_adapter):
        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"access_token": "token"}
        free5gc_adapter.client.get.return_value = mock_token_response

        mock_qos_response = Mock()
        mock_qos_response.status_code = 200
        mock_qos_response.json.return_value = {
            "qosFlows": [
                {"qfi": 1, "direction": "downlink"},
                {"qfi": 9, "direction": "uplink"},
            ]
        }
        free5gc_adapter.client.get.return_value = mock_qos_response

        flows = free5gc_adapter.get_ue_qos_flows("ue123")
        assert len(flows) == 2


class TestCoreManager:
    """Test suite for CoreManager with multiple cores."""

    @pytest.fixture
    def core_manager(self):
        from core_manager import CoreManager

        return CoreManager()

    def test_add_core(self, core_manager):
        from core_adapter import CoreType

        config = {"nef_url": "http://localhost:8080"}

        result = core_manager.add_core("test_nef", CoreType.NEF, config)
        assert result is True

        adapter = core_manager.get_core("test_nef")
        assert adapter is not None
        assert adapter.get_type() == CoreType.NEF

    def test_add_multiple_cores(self, core_manager):
        from core_adapter import CoreType

        core_manager.add_core(
            "nef", CoreType.NEF, {"nef_url": "http://nef:8080"}, priority=1
        )
        core_manager.add_core(
            "open5gs",
            CoreType.OPEN5GS,
            {"base_url": "http://open5gs:29508"},
            priority=2,
        )
        core_manager.add_core(
            "free5gc", CoreType.FREE5GC, {"nef_url": "http://free5gc:29507"}, priority=3
        )

        cores = core_manager.get_all_cores()
        assert len(cores) == 3

        default = core_manager.get_default_core()
        assert default.get_type() == CoreType.FREE5GC

    def test_remove_core(self, core_manager):
        from core_adapter import CoreType

        core_manager.add_core(
            "test", CoreType.NEF, {"nef_url": "http://localhost:8080"}
        )
        result = core_manager.remove_core("test")
        assert result is True

        adapter = core_manager.get_core("test")
        assert adapter is None

    def test_get_default_core_priority(self, core_manager):
        from core_adapter import CoreType

        core_manager.add_core("low", CoreType.NEF, {}, priority=1)
        core_manager.add_core(
            "high",
            CoreType.OPEN5GS,
            {"base_url": "http://localhost:29508"},
            priority=10,
        )

        default = core_manager.get_default_core()
        assert default.get_type() == CoreType.OPEN5GS

    def test_process_callback(self, core_manager):
        from core_adapter import CoreType

        core_manager.add_core("test", CoreType.NEF, {})

        callback_data = {
            "externalId": "ue_callback_test",
            "type": "log",
            "locationInfo": {"cellId": "cell_1"},
        }

        event = core_manager.process_callback(callback_data)

        assert event.external_id == "ue_callback_test"
        assert event.cell_id == "cell_1"


class TestCoreManagerSubscriptions:
    """Test subscription management across cores."""

    @pytest.fixture
    def multi_core_manager(self):
        from core_manager import CoreManager
        from core_adapter import CoreType
        from adapters.open5gs_adapter import Open5GSAdapter
        from adapters.free5gc_adapter import Free5GCAdapter

        manager = CoreManager()

        mock_open5gs = MagicMock(spec=Open5GSAdapter)
        mock_open5gs.get_type.return_value = CoreType.OPEN5GS

        mock_free5gc = MagicMock(spec=Free5GCAdapter)
        mock_free5gc.get_type.return_value = CoreType.FREE5GC

        return manager, mock_open5gs, mock_free5gc

    def test_create_subscription_across_cores(self, multi_core_manager):
        from core_adapter import CoreType, SubscriptionResponse
        from adapters.open5gs_adapter import Open5GSAdapter
        from adapters.free5gc_adapter import Free5GCAdapter

        core_manager, _, _ = multi_core_manager

        mock_open5gs = MagicMock(spec=Open5GSAdapter)
        mock_open5gs.get_type.return_value = CoreType.OPEN5GS
        mock_open5gs.create_subscription.return_value = SubscriptionResponse(
            subscription_id="open5gs_sub",
            external_id="ue1",
            netapp_id="netapp",
            status="active",
        )

        mock_free5gc = MagicMock(spec=Free5GCAdapter)
        mock_free5gc.get_type.return_value = CoreType.FREE5GC
        mock_free5gc.create_subscription.return_value = SubscriptionResponse(
            subscription_id="free5gc_sub",
            external_id="ue1",
            netapp_id="netapp",
            status="active",
        )

        from core_manager import CoreInstance

        core_manager._cores["open5gs"] = CoreInstance(
            "open5gs", mock_open5gs, enabled=True, priority=2
        )
        core_manager._cores["free5gc"] = CoreInstance(
            "free5gc", mock_free5gc, enabled=True, priority=1
        )
        core_manager._default_core = "open5gs"

        response = core_manager.create_subscription(
            external_id="ue1", callback_url="http://localhost:5000/callback"
        )

        assert response.status == "active"
        assert response.subscription_id == "open5gs_sub"


class TestAdapterFactory:
    """Test the adapter factory."""

    def test_create_open5gs_adapter(self):
        from core_adapter import CoreType, FiveGCoreFactory

        factory = FiveGCoreFactory()
        config = {"base_url": "http://localhost:29508"}

        adapter = factory.create(CoreType.OPEN5GS, config)
        assert adapter.get_type() == CoreType.OPEN5GS

    def test_create_free5gc_adapter(self):
        from core_adapter import CoreType, FiveGCoreFactory

        config = {"nef_url": "http://localhost:29507"}
        adapter = FiveGCoreFactory.create(CoreType.FREE5GC, config)
        assert adapter.get_type() == CoreType.FREE5GC

    def test_create_nef_adapter(self):
        from core_adapter import CoreType, FiveGCoreFactory

        config = {"nef_url": "http://localhost:8080"}
        adapter = FiveGCoreFactory.create(CoreType.NEF, config)
        assert adapter.get_type() == CoreType.NEF

    def test_unsupported_core_type(self):
        from core_adapter import FiveGCoreFactory

        with pytest.raises(ValueError) as exc_info:
            FiveGCoreFactory.create("unknown", {})

        assert "Unsupported core type" in str(exc_info.value)


class TestLocationEvent:
    """Test LocationEvent dataclass."""

    def test_from_dict_standard(self):
        from core_adapter import LocationEvent

        data = {
            "externalId": "ue_test",
            "type": "alert",
            "locationInfo": {
                "cellId": "cell_test",
                "ueLocationTimestamp": "2024-01-01T00:00:00Z",
                "age": 0,
            },
            "ipv4Addr": "192.168.1.1",
        }

        event = LocationEvent.from_dict(data)

        assert event.external_id == "ue_test"
        assert event.cell_id == "cell_test"
        assert event.event_type == "alert"
        assert event.ipv4_addr == "192.168.1.1"

    def test_from_dict_malformed_location_info(self):
        from core_adapter import LocationEvent

        data = {"externalId": "ue_test", "locationInfo": "not_a_dict"}

        event = LocationEvent.from_dict(data)
        assert event.cell_id == ""

    def test_to_dict(self):
        from core_adapter import LocationEvent

        event = LocationEvent(
            external_id="ue_convert",
            cell_id="cell_convert",
            timestamp="2024-01-01T00:00:00Z",
            event_type="log",
        )

        result = event.to_dict()

        assert result["externalId"] == "ue_convert"
        assert result["locationInfo"]["cellId"] == "cell_convert"


class TestConfigLoader:
    """Test configuration loading."""

    def test_load_from_dict(self):
        from core_manager import ConfigLoader
        from core_adapter import CoreType

        config = {
            "cores": {
                "test_core": {
                    "type": "open5gs",
                    "config": {"base_url": "http://test:29508"},
                    "enabled": True,
                    "priority": 5,
                }
            }
        }

        import json
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            f.flush()

            loaded = ConfigLoader.load_from_file(f.name)

            os.unlink(f.name)

        assert "test_core" in loaded
        assert loaded["test_core"]["type"] == CoreType.OPEN5GS


class TestEndToEndScenarios:
    """End-to-end test scenarios simulating real 5G core usage."""

    def test_open5gs_full_subscription_flow(self):
        from adapters.open5gs_adapter import Open5GSAdapter
        from core_adapter import SubscriptionRequest, LocationEvent
        from unittest.mock import MagicMock
        import requests

        config = {
            "base_url": "http://localhost:29508",
            "nrf_url": "http://localhost:29502",
        }

        with patch.object(requests, "Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            adapter = Open5GSAdapter(config)
            adapter.client = mock_session

            mock_token_response = MagicMock()
            mock_token_response.status_code = 200
            mock_token_response.json.return_value = {
                "access_token": "open5gs_token_123"
            }
            mock_session.post.return_value = mock_token_response

            mock_sub_response = MagicMock()
            mock_sub_response.status_code = 201
            mock_sub_response.json.return_value = {
                "subscriptionId": "open5gs_subscription_abc",
                "ueId": "ue_mobile_123",
                "monitoringType": "LOCATION",
            }
            mock_session.post.return_value = mock_sub_response

            request = SubscriptionRequest(
                external_id="ue_mobile_123",
                callback_url="http://netapp:5000/netAppCallback",
                num_of_reports=100,
                monitor_expire_time="2024-12-31T23:59:59Z",
            )

            response = adapter.create_subscription(request)

            assert response.status == "active"
            assert response.subscription_id == "open5gs_subscription_abc"

    def test_free5gc_location_monitoring_flow(self):
        from adapters.free5gc_adapter import Free5GCAdapter
        from core_adapter import LocationEvent
        from unittest.mock import MagicMock
        import requests

        config = {
            "nef_url": "http://localhost:29507",
            "nrf_url": "http://localhost:29510",
        }

        with patch.object(requests, "Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            adapter = Free5GCAdapter(config)
            adapter.client = mock_session

            mock_callback = {
                "jsonData": {
                    "externalId": "free5gc_ue_tracking",
                    "cellId": "free5gc_cell_tracking",
                    "timeStamp": "2024-01-15T10:30:00Z",
                    "monitoringType": "LOCATION",
                    "ueIpv4Address": "10.0.5.100",
                }
            }

            event = adapter.parse_callback(mock_callback)

            assert isinstance(event, LocationEvent)
            assert event.external_id == "free5gc_ue_tracking"
            assert event.cell_id == "free5gc_cell_tracking"
            assert event.ipv4_addr == "10.0.5.100"

    def test_multi_core_failover_scenario(self):
        from core_manager import CoreManager
        from core_adapter import CoreType, SubscriptionResponse
        from core_manager import CoreInstance

        manager = CoreManager()

        mock_core1 = MagicMock()
        mock_core1.get_type.return_value = CoreType.FREE5GC
        mock_core1.create_subscription.return_value = SubscriptionResponse(
            subscription_id="",
            external_id="ue_failover",
            netapp_id="netapp",
            status="failed_connection_error",
        )

        mock_core2 = MagicMock()
        mock_core2.get_type.return_value = CoreType.OPEN5GS
        mock_core2.create_subscription.return_value = SubscriptionResponse(
            subscription_id="successful_sub",
            external_id="ue_failover",
            netapp_id="netapp",
            status="active",
        )

        manager._cores["free5gc"] = CoreInstance(
            "free5gc", mock_core1, enabled=True, priority=1
        )
        manager._cores["open5gs"] = CoreInstance(
            "open5gs", mock_core2, enabled=True, priority=2
        )
        manager._default_core = "free5gc"

        response = manager.create_subscription(
            external_id="ue_failover", callback_url="http://localhost:5000/callback"
        )

        assert response.subscription_id == "successful_sub"
        assert response.status == "active"


class TestAdapterComparison:
    """Compare behavior across different 5G core adapters."""

    def test_open5gs_vs_free5gc_callback_parsing(self):
        from adapters.open5gs_adapter import Open5GSAdapter
        from adapters.free5gc_adapter import Free5GCAdapter

        open5gs_config = {"base_url": "http://localhost:29508"}
        free5gc_config = {"nef_url": "http://localhost:29507"}

        with patch("requests.Session"):
            open5gs_adapter = Open5GSAdapter(open5gs_config)
            free5gc_adapter = Free5GCAdapter(free5gc_config)

        open5gs_callback = {
            "ueId": "ue_compare",
            "cellId": "cell_compare",
            "timeStamp": "2024-01-15T10:00:00Z",
            "monitoringType": "LOCATION",
        }

        free5gc_callback = {
            "jsonData": {
                "externalId": "ue_compare",
                "cellId": "cell_compare",
                "timeStamp": "2024-01-15T10:00:00Z",
                "monitoringType": "LOCATION",
            }
        }

        open5gs_event = open5gs_adapter.parse_callback(open5gs_callback)
        free5gc_event = free5gc_adapter.parse_callback(free5gc_callback)

        assert open5gs_event.external_id == free5gc_event.external_id
        assert open5gs_event.cell_id == free5gc_event.cell_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
