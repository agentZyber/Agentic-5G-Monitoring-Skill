#!/usr/bin/env python
"""Capture REAL, network-grounded trajectories: bridge live UE telemetry into the store, then run
the store-backed packs (netops / self-heal / security) over it — logging every run for the v2 set.
"""

import os

from corelab.agent.runtime import AgentRuntime
from corelab.agent.tools import ToolRegistry
from corelab.agent.trajectory import TrajectoryLogger
from corelab.connectors.amarisoft import AmarisoftClient, websocket_transport
from corelab.connectors.amarisoft_bridge import AmarisoftBridge
from corelab.core.bus import EventBus
from corelab.llm.ollama import OllamaProvider
from corelab.packs.amarisoft import build_registry as amari
from corelab.packs.netops_copilot import build_registry as netops
from corelab.packs.security_sentinel import build_registry as security
from corelab.packs.self_heal import build_registry as selfheal

GNB = os.getenv("AMARISOFT_WS_URL", "ws://10.50.101.62:9001/")
CORE = os.getenv("AMARISOFT_CORE_WS_URL", "ws://10.50.101.62:9000/")
gnb = AmarisoftClient(transport=websocket_transport(GNB, timeout=8))
core = AmarisoftClient(transport=websocket_transport(CORE, timeout=8))

# 1) bridge real UE/cell telemetry into a store
bus = EventBus()
polls = AmarisoftBridge(gnb, core).run(bus, iterations=3, interval=2.0)
print(f"[bridge] {polls} polls -> {len(bus.store)} events | stats={bus.store.stats()}", flush=True)

# 2) registry: store-backed packs (reason over REAL data) + live amarisoft tools
reg = ToolRegistry()
for build in (
    lambda: netops(store=bus.store),
    lambda: selfheal(store=bus.store),
    lambda: security(store=bus.store),
    lambda: amari(amarisoft=gnb, amarisoft_core=core),
):
    for t in build().list():
        if t.name not in reg:
            reg.register(t)

prov = OllamaProvider(model=os.getenv("OLLAMA_MODEL", "qwen2.5:14b"), host="http://localhost:11434", timeout=180)
traj = TrajectoryLogger("live_trajectories")
SYS = ("You are a 5G network operations agent. Respond in English. Gather real evidence with tools "
       "before answering; when a UE shows a problem, correlate its radio (RAN_KPI) with its cell "
       "association/mobility before concluding whether it is UE-specific or network-wide.")
runtime = AgentRuntime(prov, reg, system_prompt=SYS, trajectory=traj, max_iterations=6)

ue_ids = bus.store.entities(domain="ran_kpi")
print(f"[store] real UEs: {ue_ids}", flush=True)

queries = []
if ue_ids:
    queries.append(f"Diagnose the health of {ue_ids[0]} from its recent events: assess radio quality and correlate with its cell association.")
queries += [
    "Summarize the live network: how many UEs are connected, their radio quality, and any anomalies in recent events.",
    "Run an anomaly scan over recent events and report any findings with the underlying counts.",
]
for q in queries:
    res = runtime.run(q, meta={"face": "live-capture"})
    print(f"\nQ: {q}\nA: {res.answer[:520]}", flush=True)
    print(f"   tools={[m['name'] for m in res.messages if m.get('role') == 'tool']} errors={res.tool_errors}", flush=True)

print("\n[done] real trajectories saved under live_trajectories/", flush=True)
