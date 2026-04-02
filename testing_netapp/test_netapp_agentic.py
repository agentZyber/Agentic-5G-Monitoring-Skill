import pytest
import sys
import os
import json
import asyncio
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from typing import Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestContextStore:
    def setup_method(self):
        from api import ContextStore

        self.store = ContextStore()

    def test_initial_state(self):
        assert self.store.history == []
        assert self.store.max_history == 1000

    def test_add_event(self):
        event = {
            "externalId": "ue123",
            "type": "log",
            "locationInfo": {"cellId": "cellA"},
        }
        self.store.add_event(event)

        assert len(self.store.history) == 1
        assert self.store.history[0]["externalId"] == "ue123"
        assert "timestamp" in self.store.history[0]

    def test_add_event_max_history(self):
        for i in range(1005):
            self.store.add_event({"event_id": i})

        assert len(self.store.history) == 1000
        assert self.store.history[0]["event_id"] == 5
        assert self.store.history[-1]["event_id"] == 1004

    def test_get_recent(self):
        for i in range(15):
            self.store.add_event({"event_id": i})

        recent = self.store.get_recent(10)
        assert len(recent) == 10
        assert recent[0]["event_id"] == 5

    def test_get_context_summary_empty(self):
        summary = self.store.get_context_summary()
        assert summary["status"] == "no_context"
        assert summary["events"] == []

    def test_get_context_summary_with_events(self):
        for i in range(5):
            self.store.add_event({"externalId": f"ue{i}", "type": "log"})

        summary = self.store.get_context_summary()
        assert summary["status"] == "available"
        assert summary["event_count"] == 5
        assert len(summary["subscribed_ues"]) == 5


class TestVectorStore:
    def test_context_vector_store_initialization(self):
        from vector_store import ContextVectorStore

        store = ContextVectorStore()

        assert store.in_memory_store == []
        assert store.max_in_memory == 1000

    def test_add_event_in_memory(self):
        from vector_store import ContextVectorStore

        store = ContextVectorStore()

        event = {
            "externalId": "ue123",
            "type": "alert",
            "locationInfo": {"cellId": "cellA"},
        }
        store.add_event(event)

        assert len(store.in_memory_store) == 1
        assert store.in_memory_store[0]["externalId"] == "ue123"
        assert "timestamp" in store.in_memory_store[0]

    def test_in_memory_search(self):
        from vector_store import ContextVectorStore

        store = ContextVectorStore()

        store.add_event(
            {"externalId": "ue123", "type": "log", "locationInfo": {"cellId": "cellA"}}
        )
        store.add_event(
            {
                "externalId": "ue456",
                "type": "alert",
                "locationInfo": {"cellId": "cellB"},
            }
        )
        store.add_event(
            {"externalId": "ue123", "type": "log", "locationInfo": {"cellId": "cellC"}}
        )

        results = store.search_similar("ue123", n_results=5, external_id="ue123")

        assert results["mode"] in {"in_memory_fallback", "vector"}
        assert len(results["results"]) >= 2
        if results["mode"] == "vector":
            assert all(
                item.get("metadata", {}).get("external_id") == "ue123"
                for item in results["results"]
            )

    def test_get_ue_mobility_pattern(self):
        from vector_store import ContextVectorStore

        store = ContextVectorStore()

        store.add_event({"externalId": "ue123", "locationInfo": {"cellId": "cellA"}})
        store.add_event({"externalId": "ue123", "locationInfo": {"cellId": "cellB"}})
        store.add_event({"externalId": "ue123", "locationInfo": {"cellId": "cellA"}})
        store.add_event({"externalId": "ue123", "locationInfo": {"cellId": "cellA"}})

        pattern = store.get_ue_mobility_pattern("ue123")

        assert pattern["external_id"] == "ue123"
        assert pattern["total_events"] == 4
        assert pattern["unique_cells_visited"] == 2
        assert pattern["primary_cell"] == "cellA"
        assert len(pattern["transitions"]) == 2

    def test_get_ue_mobility_pattern_no_data(self):
        from vector_store import ContextVectorStore

        store = ContextVectorStore()

        pattern = store.get_ue_mobility_pattern("nonexistent")
        assert pattern["pattern"] == "no_data"

    def test_context_summary(self):
        from vector_store import ContextVectorStore

        store = ContextVectorStore()

        store.add_event({"externalId": "ue123", "type": "log"})
        store.add_event({"externalId": "ue456", "type": "alert"})
        store.add_event({"externalId": "ue123", "type": "alert"})

        summary = store.get_context_summary()

        assert summary["status"] == "available"
        assert summary["event_count"] == 3
        assert summary["unique_ues"] == 2
        assert summary["alert_count"] == 2


class TestStreaming:
    def test_event_type_enum(self):
        from streaming import EventType

        assert EventType.LOCATION == "location"
        assert EventType.ALERT == "alert"
        assert EventType.POLICY_CHANGE == "policy_change"

    def test_event_bus_subscribe(self):
        from streaming import EventBus, EventType

        bus = EventBus()
        callback = Mock()

        bus.subscribe(callback, [EventType.ALERT])

        assert callback in bus._subscribers[EventType.ALERT]
        assert callback not in bus._all_subscribers

    def test_event_bus_subscribe_all(self):
        from streaming import EventBus, EventType

        bus = EventBus()
        callback = Mock()

        bus.subscribe(callback)

        assert callback in bus._all_subscribers

    def test_event_bus_unsubscribe(self):
        from streaming import EventBus, EventType

        bus = EventBus()
        callback = Mock()

        bus.subscribe(callback, [EventType.ALERT])
        bus.unsubscribe(callback)

        assert callback not in bus._subscribers[EventType.ALERT]

    @pytest.mark.asyncio
    async def test_event_bus_publish(self):
        from streaming import EventBus, EventType

        bus = EventBus()
        callback = Mock()

        bus.subscribe(callback)

        event = {"type": "alert", "externalId": "ue123"}
        await bus.publish(event)

        callback.assert_called_once()
        assert callback.call_args[0][0]["type"] == "alert"

    def test_streaming_manager_connections(self):
        from streaming import StreamingManager

        manager = StreamingManager()

        assert manager.connection_count == 0

        ws_mock = Mock()
        manager.add_ws_connection(ws_mock)
        assert manager.connection_count == 1

        sse_mock = Mock()
        manager.add_sse_connection(sse_mock)
        assert manager.connection_count == 2

        manager.remove_ws_connection(ws_mock)
        assert manager.connection_count == 1

    def test_streaming_event_formatter_location(self):
        from streaming import StreamingEventFormatter

        event = {
            "externalId": "ue123",
            "type": "log",
            "timestamp": "2024-01-01T00:00:00Z",
            "locationInfo": {
                "cellId": "cellA",
                "ueLocationTimestamp": "2024-01-01T00:00:00Z",
            },
        }

        formatted = StreamingEventFormatter.format_location_event(event)

        assert formatted["event_type"] == "location"
        assert formatted["external_id"] == "ue123"
        assert formatted["cell_id"] == "cellA"

    def test_streaming_event_formatter_alert(self):
        from streaming import StreamingEventFormatter

        event = {
            "externalId": "ue123",
            "type": "alert",
            "timestamp": "2024-01-01T00:00:00Z",
            "locationInfo": {"cellId": "cellA"},
            "policy": {"policy_id": "pol1"},
        }

        formatted = StreamingEventFormatter.format_alert_event(event)

        assert formatted["event_type"] == "alert"
        assert formatted["alert_reason"] == "policy_breach"
        assert formatted["policy_id"] == "pol1"


class TestAgentWorkflow:
    def test_network_state_schema(self):
        from agent_workflow import NetworkState

        state = NetworkState(
            messages=[],
            context={},
            last_event={},
            alert_triggered=False,
            action_taken="",
        )

        assert state["alert_triggered"] is False

    def test_network_monitoring_agent_not_initialized(self):
        from agent_workflow import NetworkMonitoringAgent

        agent = NetworkMonitoringAgent()
        assert agent.is_available() in [True, False]
        assert agent._initialized is False


class TestAPIFunctionSchemas:
    def test_agent_function_schemas_exist(self):
        from api import AGENT_FUNCTION_SCHEMAS

        assert len(AGENT_FUNCTION_SCHEMAS) == 3

        schema_names = [s["name"] for s in AGENT_FUNCTION_SCHEMAS]
        assert "get_network_context" in schema_names
        assert "check_ue_location_breach" in schema_names
        assert "get_ue_history" in schema_names

    def test_agent_function_schema_structure(self):
        from api import AGENT_FUNCTION_SCHEMAS

        schema = AGENT_FUNCTION_SCHEMAS[1]  # check_ue_location_breach

        assert "name" in schema
        assert "description" in schema
        assert "parameters" in schema
        assert schema["parameters"]["type"] == "object"
        assert "external_id" in schema["parameters"]["properties"]
        assert "cell_id" in schema["parameters"]["properties"]

    def test_openai_schema_format(self):
        from api import AGENT_FUNCTION_SCHEMAS

        assert all("name" in s for s in AGENT_FUNCTION_SCHEMAS)
        assert all("parameters" in s for s in AGENT_FUNCTION_SCHEMAS)

    def test_anthropic_schema_format(self):
        from api import AGENT_FUNCTION_SCHEMAS

        for func in AGENT_FUNCTION_SCHEMAS:
            anthropic_tool = {
                "name": func["name"],
                "description": func["description"],
                "input_schema": func["parameters"],
            }
            assert "name" in anthropic_tool
            assert "input_schema" in anthropic_tool


class TestPolicyLogic:
    def test_breach_detection_in_store(self):
        from api import ContextStore, policy_db

        store = ContextStore()
        policy_db.clear()
        policy_db["ue123"] = {"policy_id": "pol1", "cells": ["cellA", "cellB"]}

        event_allowed = {
            "externalId": "ue123",
            "type": "log",
            "locationInfo": {"cellId": "cellA"},
        }
        store.add_event(event_allowed)
        assert store.history[-1]["type"] == "log"

        event_breach = {
            "externalId": "ue123",
            "type": "log",
            "locationInfo": {"cellId": "cellC"},
        }
        store.add_event(event_breach)
        assert store.history[-1]["type"] == "alert"
        policy_db.clear()


class TestVAppDB:
    def test_vapp_db_initial_state(self):
        from api import vapp_db

        vapp_db["host_name"] = ""
        vapp_db["port"] = 0
        vapp_db["token"] = ""

        assert vapp_db["host_name"] == ""
        assert vapp_db["port"] == 0
        assert vapp_db["token"] == ""

    def test_vapp_db_update(self):
        from api import vapp_db

        vapp_db["host_name"] = ""
        vapp_db["port"] = 0
        vapp_db["token"] = ""

        vapp_db["host_name"] = "192.168.1.100"
        vapp_db["port"] = 8080
        vapp_db["token"] = "token123"

        assert vapp_db["host_name"] == "192.168.1.100"
        assert vapp_db["port"] == 8080
        assert vapp_db["token"] == "token123"


class TestIntegration:
    @pytest.mark.asyncio
    async def test_stream_event_to_agents_mock(self):
        from streaming import stream_event_to_agents, streaming_manager

        ws_mock = Mock()
        streaming_manager.add_ws_connection(ws_mock)

        event = {
            "externalId": "ue123",
            "type": "alert",
            "locationInfo": {"cellId": "cellA"},
        }

        await stream_event_to_agents(event)

        assert ws_mock.send_json.called

    def test_full_event_flow(self):
        from vector_store import ContextVectorStore
        from api import ContextStore

        context_store = ContextStore()
        vector_store = ContextVectorStore()

        event = {
            "externalId": "ue789",
            "type": "log",
            "locationInfo": {"cellId": "cellX"},
        }

        context_store.add_event(event)
        vector_store.add_event(event)

        assert len(context_store.history) == 1
        assert len(vector_store.in_memory_store) == 1

        pattern = vector_store.get_ue_mobility_pattern("ue789")
        assert pattern["external_id"] == "ue789"
        assert pattern["total_events"] == 1


class TestEdgeCases:
    def test_empty_external_id_in_context(self):
        from api import ContextStore

        store = ContextStore()
        store.add_event({"type": "log", "locationInfo": {"cellId": "cellA"}})

        summary = store.get_context_summary()
        assert len(summary["subscribed_ues"]) == 0

    def test_malformed_location_info(self):
        from vector_store import ContextVectorStore

        store = ContextVectorStore()
        store.add_event({"externalId": "ue123", "type": "log"})
        store.add_event({"externalId": "ue123", "locationInfo": "not_a_dict"})
        store.add_event({"externalId": "ue123", "locationInfo": None})

        pattern = store.get_ue_mobility_pattern("ue123")
        assert pattern["unique_cells_visited"] == 0

    def test_event_without_type(self):
        from api import ContextStore

        store = ContextStore()
        store.add_event({"externalId": "ue123"})

        assert store.history[-1].get("type") is None

    def test_policy_db_without_ue(self):
        from api import policy_db

        result = "nonexistent" in policy_db
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
