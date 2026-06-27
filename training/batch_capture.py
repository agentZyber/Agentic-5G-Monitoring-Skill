#!/usr/bin/env python
"""Batch-capture REAL correlation trajectories over the *currently* degraded live network.

Zero network impact: READ-ONLY (no fault injection). The network already has naturally degraded
UEs (low CQI) alongside healthy ones on the same cell — with cell power nominal, the correct
correlation conclusion is UE-SPECIFIC, which the new `amari_cell_power` tool now makes verifiable.

Quality fixes vs the first capture:
  - trimmed registry: drop tools whose backends aren't wired in capture (Prometheus/open5gs) so the
    agent never wastes iterations on "unavailable"; keep only live-data tools (Amarisoft + store).
  - hardened English prompt + retry-on-drift + log-only-clean (dedup keys on ask+tools).
  - the system prompt teaches the explicit correlation chain incl. checking cell power.
"""

import os

from zortenet.agent.runtime import AgentRuntime
from zortenet.agent.tools import ToolRegistry
from zortenet.agent.trajectory import TrajectoryLogger
from zortenet.connectors.amarisoft import AmarisoftClient, websocket_transport
from zortenet.connectors.amarisoft_bridge import AmarisoftBridge
from zortenet.core.bus import EventBus
from zortenet.llm.ollama import OllamaProvider
from zortenet.train.curate import looks_non_english
from zortenet.packs.amarisoft import build_registry as amari
from zortenet.packs.netops_copilot import build_registry as netops
from zortenet.packs.security_sentinel import build_registry as security
from zortenet.packs.self_heal import build_registry as selfheal

GNB   = os.getenv("AMARISOFT_WS_URL", "ws://10.50.101.62:9001/")
CORE  = os.getenv("AMARISOFT_CORE_WS_URL", "ws://10.50.101.62:9000/")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
DROP  = {"query_kpi", "list_core_subscriptions", "get_ue_status"}  # unwired backends in capture

gnb  = AmarisoftClient(transport=websocket_transport(GNB,  timeout=8))
core = AmarisoftClient(transport=websocket_transport(CORE, timeout=8))
traj = TrajectoryLogger("batch_trajectories")

SYS = (
    "You are a 5G RAN operations agent. CRITICAL LANGUAGE RULE: write 100% of your reasoning and "
    "your entire final answer in ENGLISH ONLY. Never use Thai, Chinese, or any non-Latin script.\n"
    "Always gather real evidence with the tools before answering. To diagnose a UE's radio problem you MUST:\n"
    "  (1) read its downlink radio metrics (CQI, MCS),\n"
    "  (2) check the cell's transmit power with amari_cell_power (0 dB = nominal; negative = reduced coverage),\n"
    "  (3) compare the UE against the other UEs on the same cell,\n"
    "  (4) conclude whether the cause is UE-SPECIFIC (cell power nominal AND only this UE degraded) or "
    "CELL-WIDE (cell power reduced OR all UEs degraded), and justify it with the numbers you read."
)


def build_capture_registry(store):
    reg = ToolRegistry()
    for build in (lambda: netops(store=store), lambda: selfheal(store=store),
                  lambda: security(store=store), lambda: amari(amarisoft=gnb, amarisoft_core=core)):
        for t in build().list():
            if t.name not in reg and t.name not in DROP:
                reg.register(t)
    return reg


def ue_table():
    ues = gnb._call("ue_get", stats=True).get("response", {}).get("ue_list", []) or []
    rows = []
    for u in ues:
        c = (u.get("cells") or [{}])[0]
        rows.append({"id": u.get("ran_ue_id"), "cqi": c.get("cqi"), "dl_mcs": c.get("dl_mcs")})
    return [r for r in rows if r["cqi"] is not None]


def main():
    rows = sorted(ue_table(), key=lambda r: r["cqi"])
    print(f"[state] UEs by CQI (asc): {rows}", flush=True)
    if not rows:
        print("ABORT: no UEs with CQI attached.", flush=True)
        return
    worst = rows[0]["id"]
    best = rows[-1]["id"]
    second = rows[1]["id"] if len(rows) > 1 else worst

    queries = [
        f"Diagnose UE {worst}: read its downlink radio (CQI/MCS), check whether the cell's transmit power is "
        "nominal or reduced, compare it against the other UEs on the same cell, and state whether the problem "
        "is UE-specific or cell-wide. Cite the numbers.",
        f"UE {worst} has poor downlink throughput. Is this a cell/coverage problem or specific to this UE? "
        "Justify using the cell transmit power and a peer-UE comparison.",
        "Rank all connected UEs by downlink health (CQI/MCS) and identify the worst performer with its likely cause.",
        "Perform a full network health assessment: how many UEs are connected, which are degraded, and is the "
        "cell itself healthy (check its transmit power)?",
        f"Compare degraded UE {worst} with healthy UE {best} on the same cell. Given the cell transmit power is "
        "identical for both, why does one have good radio and the other poor?",
        "Is the network experiencing a cell-wide coverage issue, or are the problems isolated to specific UEs? "
        "Check the cell transmit power and per-UE radio to decide.",
        f"Recommend a remediation for UE {worst}'s poor radio quality, but first confirm whether the cell or the "
        "UE is the root cause.",
        "Scan recent events for anomalies and correlate any degraded UE's radio with its cell association.",
        f"Triage the connected UEs: which need attention now? For the worst one ({worst}), give a root-cause "
        "hypothesis (UE-specific vs cell-wide) with evidence.",
        "Summarize downlink radio quality across all UEs together with the cell's transmit power; flag any "
        "mismatch that indicates a UE-specific fault rather than a cell problem.",
        f"Audit the cell association of UE {worst} and UE {second} and correlate it with their radio quality.",
        "Given current radio conditions, is the cell's coverage adequate for every attached UE? Identify any UE "
        "the cell is serving poorly and explain why.",
    ]

    bus = EventBus()
    polls = AmarisoftBridge(gnb, core).run(bus, iterations=3, interval=2.0)
    reg = build_capture_registry(bus.store)
    print(f"[capture] polls={polls} events={len(bus.store)} tools={reg.names()}", flush=True)
    prov = OllamaProvider(model=MODEL, host="http://localhost:11434", timeout=300, temperature=0.0)
    runtime = AgentRuntime(prov, reg, system_prompt=SYS, max_iterations=6)

    for i, q in enumerate(queries, 1):
        res, ok = None, False
        for attempt in range(3):
            qq = q if attempt == 0 else q + "\n\nIMPORTANT: write EVERY word of your answer in English only."
            res = runtime.run(qq)
            if not looks_non_english(res.answer):
                ok = True
                break
        traj.log({
            "provider": prov.name, "model": MODEL, "messages": res.messages, "answer": res.answer,
            "iterations": res.iterations, "tool_calls_made": res.tool_calls_made,
            "tool_errors": res.tool_errors, "stopped_early": res.stopped_early,
            "meta": {"face": "batch-capture", "phase": "natural", "cell_power_db": 0,
                     "worst_ue": worst, "english_ok": ok},
            "outcome": None,
        })
        tools = [m["name"] for m in res.messages if m.get("role") == "tool"]
        print(f"[{i}/{len(queries)}] english_ok={ok} errors={res.tool_errors} tools={tools}\n"
              f"   Q: {q[:75]}\n   A: {res.answer[:220]}", flush=True)

    print("\n[done] batch trajectories under batch_trajectories/", flush=True)


if __name__ == "__main__":
    main()
