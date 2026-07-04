"""End-to-end Stage-3 exit-gate scenario (mock form): agent drafts/submits via its faces,
a HUMAN approves over REST, only then does apply succeed — across one shared ledger."""

from fastapi.testclient import TestClient

from corelab.app import create_app
from corelab.llm.base import LLMProvider, LLMResponse


class IdleProvider(LLMProvider):
    name = "idle"
    model = "none"

    def is_available(self):
        return True

    def chat(self, messages, tools=None, **kwargs):
        return LLMResponse(content="ok")


def _client():
    return TestClient(create_app(provider=IdleProvider(), trajectory=None))


def test_full_intent_lifecycle_over_rest_and_a2a():
    with _client() as client:
        # 1) The agent drafts an intent (exercised through the A2A skill face).
        draft = client.post(
            "/a2a/skills/draft_intent",
            json={
                "name": "Slice latency under 20ms",
                "object_type": "NETWORK_SLICE",
                "object_instance": "slice-embb-01",
                "metric": "latency_ms",
                "condition": "IS_LESS_THAN",
                "value": 20,
            },
        ).json()["result"]
        intent_id = draft["intent_id"]
        assert draft["validation"]["valid"] is True

        # 2) Dry-run, then submit for approval.
        plan = client.post(
            "/a2a/skills/dry_run_intent", json={"intent_id": intent_id}
        ).json()["result"]
        assert plan["plan"][0]["target"] == "a1-ric"

        submitted = client.post(
            "/a2a/skills/submit_intent_for_approval", json={"intent_id": intent_id}
        ).json()["result"]
        assert submitted["status"] == "awaiting_approval"

        # 3) Apply BEFORE approval: the gate holds.
        blocked = client.post(
            "/a2a/skills/apply_intent", json={"intent_id": intent_id}
        ).json()["result"]
        assert "human approval required" in blocked["error"]

        # 4) The HUMAN approves over REST (this endpoint is not an agent tool).
        approved = client.post(
            f"/intents/{intent_id}/approve", json={"approver": "akis"}
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

        # 5) Now apply succeeds — via the simulated executor, honestly labeled.
        applied = client.post(
            "/a2a/skills/apply_intent", json={"intent_id": intent_id}
        ).json()["result"]
        assert applied["status"] == "applied"
        assert applied["outcome"]["simulated"] is True

        # 6) Audit trail visible to the human.
        record = client.get(f"/intents/{intent_id}").json()
        assert [h["action"] for h in record["history"]] == [
            "created", "dry_run", "submitted", "approved", "applied",
        ]
        assert any(h["by"] == "akis" for h in record["history"])


def test_rest_gate_error_codes():
    with _client() as client:
        # unknown intent
        assert client.get("/intents/ghost").status_code == 404
        assert (
            client.post("/intents/ghost/approve", json={"approver": "x"}).status_code == 404
        )

        # wrong-state approval -> 409
        draft = client.post(
            "/a2a/skills/draft_intent",
            json={
                "name": "n", "object_type": "UE", "object_instance": "ue1",
                "metric": "latency_ms", "condition": "IS_LESS_THAN", "value": 5,
            },
        ).json()["result"]
        resp = client.post(f"/intents/{draft['intent_id']}/approve", json={"approver": "x"})
        assert resp.status_code == 409  # still a draft: nothing to approve

        # listing with filters
        assert client.get("/intents", params={"status": "draft"}).json()["count"] == 1
        assert client.get("/intents", params={"status": "bogus"}).status_code == 422


def test_reject_path_over_rest():
    with _client() as client:
        draft = client.post(
            "/a2a/skills/draft_intent",
            json={
                "name": "n", "object_type": "UE", "object_instance": "ue1",
                "metric": "latency_ms", "condition": "IS_LESS_THAN", "value": 5,
            },
        ).json()["result"]
        intent_id = draft["intent_id"]
        client.post("/a2a/skills/submit_intent_for_approval", json={"intent_id": intent_id})

        rejected = client.post(
            f"/intents/{intent_id}/reject",
            json={"approver": "akis", "reason": "outside maintenance window"},
        ).json()
        assert rejected["status"] == "rejected"

        blocked = client.post(
            "/a2a/skills/apply_intent", json={"intent_id": intent_id}
        ).json()["result"]
        assert "human approval required" in blocked["error"]
