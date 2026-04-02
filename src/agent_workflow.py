import json
from typing import Any, Sequence, TypedDict
from datetime import datetime

try:
    from langchain_core.messages import HumanMessage
    from langchain_core.tools import tool

    LANGCHAIN_CORE_AVAILABLE = True
except ImportError:
    LANGCHAIN_CORE_AVAILABLE = False

    class HumanMessage:
        def __init__(self, content: str):
            self.content = content

    def tool(func=None, *args, **kwargs):
        if func is not None and callable(func):
            return func

        def decorator(inner):
            return inner

        return decorator

try:
    from langgraph.prebuilt import create_react_agent

    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

try:
    from langchain_anthropic import ChatAnthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from langchain_openai import ChatOpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class NetworkState(TypedDict):
    messages: Sequence[Any]
    context: dict
    last_event: dict
    alert_triggered: bool
    action_taken: str


NETWORK_CONTEXT_TOOL_DESCRIPTION = """Get current network context including active policies, subscribed UEs, recent events, and alerts.
Returns a summary of the current network state."""


class NetworkMonitoringAgent:
    def __init__(self):
        self.graph = None
        self.agent_executor = None
        self._initialized = False

    def is_available(self) -> bool:
        return (
            LANGGRAPH_AVAILABLE
            and LANGCHAIN_CORE_AVAILABLE
            and (OPENAI_AVAILABLE or ANTHROPIC_AVAILABLE)
        )

    def initialize(self, model: str = "gpt-4"):
        if not self.is_available():
            return False

        if OPENAI_AVAILABLE:
            llm = ChatOpenAI(model=model, temperature=0)
        elif ANTHROPIC_AVAILABLE:
            llm = ChatAnthropic(model=model)
        else:
            return False

        from vector_store import context_vector_store

        @tool
        def get_network_context() -> str:
            """Get current network context."""
            return json.dumps(context_vector_store.get_context_summary(), indent=2)

        @tool
        def get_ue_mobility(external_id: str) -> str:
            """Get mobility pattern analysis for a specific UE."""
            pattern = context_vector_store.get_ue_mobility_pattern(external_id)
            return json.dumps(pattern, indent=2)

        @tool
        def check_policy_breach(external_id: str) -> str:
            """Check if a UE has breached its policy based on recent events."""
            events = [
                e
                for e in context_vector_store.in_memory_store
                if e.get("externalId") == external_id
            ]
            if not events:
                return json.dumps({"breach": False, "reason": "no_events"})

            latest = events[-1]
            breach = latest.get("type") == "alert"
            return json.dumps(
                {
                    "breach": breach,
                    "external_id": external_id,
                    "latest_event_type": latest.get("type"),
                    "cell_id": latest.get("locationInfo", {}).get("cellId")
                    if isinstance(latest.get("locationInfo"), dict)
                    else None,
                },
                indent=2,
            )

        @tool
        def get_active_alerts() -> str:
            """Get all recent alerts from the network."""
            alerts = [
                e
                for e in context_vector_store.in_memory_store
                if e.get("type") == "alert"
            ]
            return json.dumps(
                {"alert_count": len(alerts), "recent_alerts": alerts[-10:]}, indent=2
            )

        tools = [
            get_network_context,
            get_ue_mobility,
            check_policy_breach,
            get_active_alerts,
        ]

        system_prompt = """You are a 5G Network Monitoring Agent. Your role is to:
1. Monitor network events and detect anomalies
2. Analyze UE location patterns for suspicious behavior
3. Identify policy breaches and generate alerts
4. Provide actionable insights to network operators

Use the available tools to gather context and respond to queries.
When alerts are detected, summarize the situation and recommend actions."""

        self.agent_executor = create_react_agent(
            llm, tools, state_modifier=system_prompt
        )
        self._initialized = True
        return True

    async def process_event(self, event: dict) -> dict:
        if not self._initialized:
            return {"status": "agent_not_initialized"}

        from vector_store import context_vector_store

        context = context_vector_store.get_context_summary()

        user_message = f"""Analyze this network event and determine if any action is needed:

Event: {json.dumps(event, indent=2)}

Current Context Summary:
- Total Events: {context.get("event_count", 0)}
- Active Alerts: {context.get("alert_count", 0)}
- Subscribed UEs: {context.get("unique_ues", 0)}

Respond with:
1. Event classification (normal/alert/critical)
2. Any policy breaches detected
3. Recommended actions if any"""

        result = await self.agent_executor.ainvoke(
            {"messages": [HumanMessage(content=user_message)]}
        )

        response_text = result["messages"][-1].content

        alert_triggered = (
            "alert" in response_text.lower() or "critical" in response_text.lower()
        )

        return {
            "event_analyzed": True,
            "event": event,
            "agent_response": response_text,
            "alert_triggered": alert_triggered,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def query(self, question: str) -> dict:
        if not self._initialized:
            return {"status": "agent_not_initialized"}

        result = await self.agent_executor.ainvoke(
            {"messages": [HumanMessage(content=question)]}
        )

        return {
            "question": question,
            "response": result["messages"][-1].content,
            "timestamp": datetime.utcnow().isoformat(),
        }


network_agent = NetworkMonitoringAgent()
