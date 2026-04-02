import pytest
import sys
import os
import json
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def client(mock_env, mock_netapp_utils, mock_evolved5g):
    with patch("redis.Redis"):
        with patch("subprocess.run"):
            from api import app, policy_db, context_store, context_vector_store, q

            policy_db.clear()
            context_store.history.clear()
            context_vector_store.in_memory_store.clear()
            while not q.empty():
                q.get()

            yield TestClient(app)


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_index(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data


class TestVAppConnectEndpoint:
    def test_vapp_connect_success(self, client):
        payload = {"vapp_ip": "192.168.1.100", "port": 8080}
        response = client.post("/vapp_connect", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "token" in data


class TestPolicyEndpoint:
    def test_set_policy(self, client):
        payload = {
            "id": "ue123@domain.com",
            "pol-id": "pol_001",
            "cells": ["AAAAA1001", "AAAAA1002"],
        }
        response = client.post("/setPolicy", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Policy set"
        assert data["policy"]["policy_id"] == "pol_001"

    def test_set_multiple_policies(self, client):
        for i in range(3):
            payload = {
                "id": f"ue{i}@domain.com",
                "pol-id": f"pol_{i:03d}",
                "cells": [f"cell{i}A", f"cell{i}B"],
            }
            response = client.post("/setPolicy", json=payload)
            assert response.status_code == 200


class TestAgentContextEndpoint:
    def test_get_agent_context_empty(self, client):
        response = client.get("/agent/context")
        assert response.status_code == 200
        data = response.json()
        assert "context_id" in data
        assert "generated_at" in data
        assert "summary" in data
        assert data["summary"]["total_events"] == 0

    def test_get_agent_context_with_events(self, client, sample_location_event):
        from api import context_store, context_vector_store

        context_store.add_event(sample_location_event)
        context_vector_store.add_event(sample_location_event)

        response = client.get("/agent/context")
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["total_events"] == 1
        assert data["summary"]["subscribed_ues"] == ["ue123@domain.com"]

    def test_get_agent_context_with_external_id(self, client, sample_location_event):
        from api import context_store, context_vector_store

        context_store.add_event(sample_location_event)
        context_vector_store.add_event(sample_location_event)

        response = client.get("/agent/context?external_id=ue123@domain.com&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 1

    def test_get_agent_context_include_raw(self, client, sample_location_event):
        from api import context_store, context_vector_store

        context_store.add_event(sample_location_event)
        context_vector_store.add_event(sample_location_event)

        response = client.get("/agent/context?include_raw=true")
        assert response.status_code == 200
        data = response.json()
        assert "raw_history" in data


class TestAgentToolsEndpoint:
    def test_get_agent_tools(self, client):
        response = client.get("/agent/tools")
        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert data["tool_count"] == 3
        assert "langchain_available" in data

    def test_get_openai_schema(self, client):
        response = client.get("/agent/functions/schema")
        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "openai_function_call"
        assert len(data["functions"]) == 3

    def test_get_anthropic_schema(self, client):
        response = client.get("/agent/functions/schema/anthropic")
        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "anthropic_tool_use"
        assert len(data["tools"]) == 3


class TestRAGEndpoints:
    def test_rag_search(self, client, sample_location_event):
        from api import context_vector_store

        context_vector_store.add_event(sample_location_event)

        response = client.get("/agent/rag/search?query=location&n_results=5")
        assert response.status_code == 200
        data = response.json()
        assert "query" in data
        assert "timestamp" in data
        assert "results" in data

    def test_rag_search_with_external_id(self, client, sample_location_event):
        from api import context_vector_store

        context_vector_store.add_event(sample_location_event)

        response = client.get(
            f"/agent/rag/search?query=ue123&external_id=ue123@domain.com"
        )
        assert response.status_code == 200

    def test_rag_ue_mobility(self, client, sample_location_event):
        from api import context_vector_store

        context_vector_store.add_event(sample_location_event)

        response = client.get("/agent/rag/ue/ue123@domain.com/mobility")
        assert response.status_code == 200
        data = response.json()
        assert data["external_id"] == "ue123@domain.com"
        assert "pattern_analysis" in data

    def test_rag_summary(self, client):
        response = client.get("/agent/rag/summary")
        assert response.status_code == 200
        data = response.json()
        assert "context_summary" in data
        assert "vector_available" in data
        assert "features" in data

    def test_rag_stats(self, client):
        response = client.get("/agent/rag/stats")
        assert response.status_code == 200
        data = response.json()
        assert "vector_store" in data
        assert "context_summary" in data

    def test_rag_cleanup(self, client):
        response = client.delete("/agent/rag/cleanup?days=7")
        assert response.status_code == 200
        data = response.json()
        assert "deleted_events" in data
        assert data["retention_days"] == 7


class TestStreamEndpoints:
    def test_stream_status(self, client):
        response = client.get("/stream/status")
        assert response.status_code == 200
        data = response.json()
        assert "websocket_connections" in data
        assert "sse_connections" in data
        assert "total_connections" in data


class TestCoreEndpoints:
    def test_core_status(self, client):
        response = client.get("/cores/status")
        assert response.status_code == 200
        data = response.json()
        assert "cores" in data
        assert "default_core" in data
        assert "callback_destination" in data

    def test_get_subscriptions_uses_core_manager(self, client):
        with patch("api.core_manager.get_all_subscriptions") as mock_get_subscriptions:
            mock_get_subscriptions.return_value = [
                {
                    "core": "default",
                    "subscription_id": "sub_1",
                    "external_id": "ue123",
                    "status": "active",
                    "raw": {"subscriptionId": "sub_1"},
                }
            ]

            response = client.get("/get_subscriptions")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "OK"
            assert data["subscriptions"][0]["core"] == "default"

    def test_subscription_uses_core_manager(self, client):
        from core_adapter import SubscriptionResponse

        with patch("api.core_manager.create_subscription") as mock_create_subscription:
            mock_create_subscription.return_value = SubscriptionResponse(
                subscription_id="sub_123",
                external_id="ue123@domain.com",
                netapp_id="zortenetapp",
                status="active",
                raw_response={"subscriptionId": "sub_123"},
                core_name="default",
            )

            response = client.post(
                "/subscription",
                json={
                    "id": "ue123@domain.com",
                    "num_of_reports": 10,
                    "exp_time": "2027-01-01T00:00:00Z",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "OK"
            assert data["subscription"]["core"] == "default"


class TestAgentGraphEndpoints:
    def test_agent_graph_status(self, client):
        response = client.get("/agent/graph/status")
        assert response.status_code == 200
        data = response.json()
        assert "langgraph_available" in data
        assert "initialized" in data
        assert "features" in data

    def test_agent_graph_initialize_not_available(self, client):
        response = client.post("/agent/graph/initialize?model=gpt-4")
        assert response.status_code in [200, 503]


class TestNetAppCallbackEndpoint:
    def test_callback_creates_log_event(self, client, sample_location_event):
        from api import context_store, context_vector_store, policy_db

        response = client.post("/netAppCallback", json=sample_location_event)
        assert response.status_code == 200

        data = response.json()
        assert data["type"] == "log"

    def test_callback_includes_source_core(self, client, sample_location_event):
        response = client.post(
            "/netAppCallback?source_core=default", json=sample_location_event
        )
        assert response.status_code == 200

        data = response.json()
        assert data["source_core"] == "default"

    def test_callback_creates_alert_event(
        self, client, sample_alert_event, sample_policy
    ):
        from api import policy_db

        policy_db["ue456@domain.com"] = sample_policy

        response = client.post("/netAppCallback", json=sample_alert_event)
        assert response.status_code == 200

        data = response.json()
        assert data["type"] == "alert"

    def test_callback_without_policy(self, client, sample_location_event):
        response = client.post("/netAppCallback", json=sample_location_event)
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "log"


class TestVAppConsumeEndpoint:
    def test_vapp_consume_empty(self, client):
        response = client.get("/VappConsume")
        assert response.status_code == 200
        data = response.json()
        assert "nothing" in data or data == {}


class TestEdgeCases:
    def test_callback_with_malformed_json(self, client):
        response = client.post("/netAppCallback", content=b"not json")
        assert response.status_code == 422

    def test_context_with_nonexistent_external_id(self, client):
        response = client.get("/agent/context?external_id=nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []

    def test_rag_search_empty(self, client):
        response = client.get("/agent/rag/search?query=nothing")
        assert response.status_code == 200

    def test_set_policy_missing_fields(self, client):
        payload = {"id": "ue123"}
        response = client.post("/setPolicy", json=payload)
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
