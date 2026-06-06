"""ZorteNet — The Agentic 5G/6G Toolkit.

This package evolves the original single-purpose ZorteNet location/mobility NetApp into a
general, multi-domain, agent-native 5G/6G framework. See docs/AGENTIC_TOOLKIT_BLUEPRINT.md.

Layers (built incrementally):
  - core        generalized NetworkEvent model + event bus
  - connectors  south-bound adapters (5GC / O-RAN / telemetry / simulators)
  - memory      RAG over events + a telecom knowledge base
  - llm         local-first provider abstraction (Ollama default; OpenAI/Anthropic/vLLM)
  - agent       LLM agent runtime + a shared ToolRegistry
  - interop     one capability core, many protocol faces (MCP / A2A / ACP / AG-UI / REST / gRPC)
  - packs       turnkey capability packs (netops-copilot, intent-to-network, ...)
  - datasets    declarative dataset registry (TeleQnA / Tele-Data / 5G3E / ...)
"""

__version__ = "0.3.0-dev"

__all__ = ["__version__"]
