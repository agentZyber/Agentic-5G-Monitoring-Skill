#!/usr/bin/env python
"""Run the agent over the LIVE Amarisoft 5G network (edge-brain: on the GPU box, LLM local).

Does double duty: prints a status report over the real connected UEs (proof), and captures every
run as a real, network-grounded trajectory (TrajectoryLogger) for the v2 training set.
"""

import os

from corelab.agent.runtime import AgentRuntime
from corelab.agent.trajectory import TrajectoryLogger
from corelab.connectors.amarisoft import AmarisoftClient, websocket_transport
from corelab.llm.ollama import OllamaProvider
from corelab.packs.amarisoft import build_registry as amari_pack

GNB = os.getenv("AMARISOFT_WS_URL", "ws://10.50.101.62:9001/")
CORE = os.getenv("AMARISOFT_CORE_WS_URL", "ws://10.50.101.62:9000/")
OLLAMA = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")

gnb = AmarisoftClient(transport=websocket_transport(GNB, timeout=8))
core = AmarisoftClient(transport=websocket_transport(CORE, timeout=8))
reg = amari_pack(amarisoft=gnb, amarisoft_core=core)
prov = OllamaProvider(model=MODEL, host=OLLAMA, timeout=180)
traj = TrajectoryLogger("live_trajectories")
runtime = AgentRuntime(prov, reg, trajectory=traj, max_iterations=6)

print(f"model={MODEL}@{OLLAMA} | gNB reachable={gnb.is_available()}", flush=True)

QUERIES = [
    "How many UEs are connected to the 5G network right now, and what is each UE's radio quality (CQI and SNR)?",
    "Is the core registration count consistent with the number of UEs attached at the gNB? Report any mismatch.",
    "Which connected UE has the best radio conditions and which the weakest? Use CQI / SNR / path-loss.",
    "Give an overall health summary of the live 5G cell: active UEs, load, and any concern.",
]
for q in QUERIES:
    res = runtime.run(q, meta={"face": "live-amarisoft"})
    print(f"\nQ: {q}\nA: {res.answer[:650]}", flush=True)
    print(f"   tools={[m['name'] for m in res.messages if m.get('role') == 'tool']} "
          f"errors={res.tool_errors} iters={res.iterations}", flush=True)

print("\n[done] trajectories saved under live_trajectories/", flush=True)
