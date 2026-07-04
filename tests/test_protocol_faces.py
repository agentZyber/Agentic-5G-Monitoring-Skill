"""The Stage-4 protocol faces through the live app: A2A tasks, ACP, OASF, ANP."""

from fastapi.testclient import TestClient

from corelab.app import create_app
from corelab.llm.base import LLMProvider, LLMResponse


class EchoProvider(LLMProvider):
    name = "echo"
    model = "fake"

    def is_available(self):
        return True

    def chat(self, messages, tools=None, **kwargs):
        user = next(m["content"] for m in messages if m["role"] == "user")
        return LLMResponse(content=f"echo: {user}")


def _client():
    return TestClient(create_app(provider=EchoProvider(), trajectory=None))


def test_a2a_jsonrpc_task_through_app():
    with _client() as client:
        resp = client.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {
                    "message": {
                        "kind": "message",
                        "role": "user",
                        "parts": [{"kind": "text", "text": "network status?"}],
                        "messageId": "m1",
                    }
                },
            },
        )
        task = resp.json()["result"]
        assert task["status"]["state"] == "completed"
        assert task["artifacts"][0]["parts"][0]["text"] == "echo: network status?"

        fetched = client.post(
            "/a2a",
            json={"jsonrpc": "2.0", "id": 2, "method": "tasks/get", "params": {"id": task["id"]}},
        ).json()["result"]
        assert fetched["id"] == task["id"]


def test_acp_agents_and_run_lifecycle():
    with _client() as client:
        agents = client.get("/acp/agents").json()["agents"]
        assert agents[0]["name"] == "corelab-5g"

        run = client.post(
            "/acp/runs",
            json={
                "agent_name": "corelab-5g",
                "input": [{"parts": [{"content": "any alerts?", "content_type": "text/plain"}]}],
            },
        ).json()
        assert run["status"] == "completed"
        assert run["output"][0]["parts"][0]["content"] == "echo: any alerts?"

        fetched = client.get(f"/acp/runs/{run['run_id']}").json()
        assert fetched["run_id"] == run["run_id"]

        assert client.post("/acp/runs", json={"agent_name": "ghost", "input": []}).status_code == 404
        assert (
            client.post("/acp/runs", json={"agent_name": "corelab-5g", "input": []}).status_code
            == 422
        )
        assert client.get("/acp/runs/ghost").status_code == 404


def test_oasf_record_describes_all_faces():
    with _client() as client:
        record = client.get("/.well-known/oasf.json").json()
    locator_types = {loc["type"] for loc in record["locators"]}
    assert {"a2a-card", "a2a-jsonrpc", "mcp-streamable-http", "acp"}.issubset(locator_types)
    skill_names = {s["name"] for s in record["skills"]}
    assert "ask_specialist" in skill_names  # NOC delegation is advertised
    assert record["extensions"][0]["data"]["standards"] == [
        "TMF921/TIO", "3GPP TS 28.312", "O-RAN A1",
    ]


def test_anp_face_is_loudly_experimental():
    with _client() as client:
        did = client.get("/.well-known/did.json").json()
        desc = client.get("/.well-known/agent-description.json").json()
    assert did["id"].startswith("did:wba:")
    assert "verificationMethod" not in did  # unsigned v0: no authenticated-identity claim
    endpoints = {s["type"]: s["serviceEndpoint"] for s in did["service"]}
    assert endpoints["A2AService"].endswith("/a2a")
    assert desc["experimental"] is True
    assert desc["interfaces"]["mcp"].endswith("/mcp")
