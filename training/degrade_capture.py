#!/usr/bin/env python
"""Capture REAL degraded-UE *correlation* trajectories for the v2 training set.

Flow (safety-first):
  1. sanity: cell-1 gain offset must be 0, UEs attached
  2. baseline capture (network HEALTHY — no fault active; does not extend the degradation window)
  3. adaptive degrade: cell_gain steps -6 -> -10 -> -14 (cap -16), stop once min DL CQI <= 10
  4. degraded capture: diagnose -> correlate queries over the now-degraded DL
  5. finally: ALWAYS restore cell_gain 1 0 + verify

`cell_gain` cuts DOWNLINK power only (UL/attachment unaffected -> UEs stay connected).
Three independent restore paths guard the live network: this script's `finally`, a detached
watchdog armed below, and an external watchdog the caller arms from a different host/route.

Language discipline: the agent runs WITHOUT the auto-logger; each answer is checked with the
curation language filter and retried up to twice; only the English-clean record is logged
(dedup keys on ask+tool-sequence, so logging a Thai attempt would shadow the English retry).
"""

import os, sys, time, json, subprocess

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
CELL  = 1
STEPS = [-6.0, -10.0, -14.0, -16.0]   # gentle -> capped well short of the -100 mute
WATCHDOG_SECONDS = 900

gnb  = AmarisoftClient(transport=websocket_transport(GNB,  timeout=8))
core = AmarisoftClient(transport=websocket_transport(CORE, timeout=8))
traj = TrajectoryLogger("degraded_trajectories")

SYS = (
    "You are a 5G RAN operations agent. CRITICAL LANGUAGE RULE: write 100% of your reasoning and "
    "your entire final answer in ENGLISH ONLY. Never use Thai, Chinese, or any non-Latin script.\n"
    "Always gather real evidence with the tools before answering. When a UE may have a radio problem "
    "you MUST: (1) read its RAN_KPI radio metrics (CQI, MCS), (2) check its cell association/mobility "
    "(LOCATION events), (3) compare it against the other UE(s) on the same cell, then (4) conclude "
    "whether the issue is UE-SPECIFIC or CELL-WIDE and justify it with the numbers you read."
)

def set_gain(g):
    return gnb._call("cell_gain", cell_id=CELL, gain=g)

def cell1_offset():
    return gnb.config_get()["response"]["nr_cells"][str(CELL)]["gain"]

def ue_radio():
    ues = gnb._call("ue_get", stats=True).get("response", {}).get("ue_list", []) or []
    out = []
    for u in ues:
        c = (u.get("cells") or [{}])[0]
        out.append({"id": u.get("ran_ue_id"), "cqi": c.get("cqi"),
                    "dl_mcs": c.get("dl_mcs"), "ul_mcs": c.get("ul_mcs"),
                    "pl": c.get("ul_path_loss")})
    return out

def arm_watchdog():
    """Detached belt-and-suspenders: force-restore after WATCHDOG_SECONDS no matter what."""
    code = (f"import time;time.sleep({WATCHDOG_SECONDS});"
            f"from zortenet.connectors.amarisoft import AmarisoftClient,websocket_transport as W;"
            f"AmarisoftClient(transport=W('{GNB}',timeout=8))._call('cell_gain',cell_id={CELL},gain=0)")
    subprocess.Popen([sys.executable, "-c", code],
                     stdout=open("watchdog.log", "w"), stderr=subprocess.STDOUT,
                     start_new_session=True, env={**os.environ})
    print(f"[watchdog] armed: force-restore in {WATCHDOG_SECONDS}s (pid detached)", flush=True)

def capture(phase, queries, gain):
    bus = EventBus()
    polls = AmarisoftBridge(gnb, core).run(bus, iterations=3, interval=2.0)
    reg = ToolRegistry()
    for build in (lambda: netops(store=bus.store), lambda: selfheal(store=bus.store),
                  lambda: security(store=bus.store), lambda: amari(amarisoft=gnb, amarisoft_core=core)):
        for t in build().list():
            if t.name not in reg:
                reg.register(t)
    prov = OllamaProvider(model=MODEL, host="http://localhost:11434", timeout=300, temperature=0.0)
    runtime = AgentRuntime(prov, reg, system_prompt=SYS, max_iterations=6)  # NO auto-logger
    ues = bus.store.entities(domain="ran_kpi")
    print(f"[{phase}] polls={polls} events={len(bus.store)} stats={bus.store.stats()} ues={ues}", flush=True)
    for q in queries:
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
            "meta": {"face": "degraded-capture", "phase": phase, "gain_db": gain,
                     "ues": ues, "english_ok": ok},
            "outcome": None,
        })
        tools = [m["name"] for m in res.messages if m.get("role") == "tool"]
        print(f"[{phase}] english_ok={ok} errors={res.tool_errors} tools={tools}\n"
              f"   Q: {q[:70]}\n   A: {res.answer[:260]}", flush=True)

def main():
    base = cell1_offset()
    radio0 = ue_radio()
    print(f"[sanity] cell-1 offset={base} ; UEs={radio0}", flush=True)
    if base != 0:
        print("ABORT: baseline gain offset is not 0 — refusing to stack a fault.", flush=True)
        return
    if len(radio0) < 1:
        print("ABORT: no UEs attached — nothing to capture.", flush=True)
        return

    arm_watchdog()
    chosen = 0.0
    try:
        # 2) baseline (healthy) — no fault active yet
        u0 = radio0[0]["id"]
        capture("baseline", [
            "Summarize the live network: how many UEs are connected and their downlink radio quality "
            "(CQI, MCS)? Report the actual counts.",
            f"Assess the health of UE {u0}: read its radio KPIs and state whether it is healthy, citing the numbers.",
        ], gain=0.0)

        # 3) adaptive degrade
        for g in STEPS:
            set_gain(g)
            chosen = g
            time.sleep(7)
            r = ue_radio()
            cqis = [x["cqi"] for x in r if x["cqi"] is not None]
            mcss = [x["dl_mcs"] for x in r if x["dl_mcs"] is not None]
            print(f"[degrade] gain={g}dB -> {r}", flush=True)
            if (cqis and min(cqis) <= 10) or (mcss and min(mcss) <= 14.0):
                break
        time.sleep(3)

        # 4) degraded capture — the valuable diagnose->correlate trajectories
        capture("degraded", [
            f"UE {u0} is reporting poor downlink performance. Diagnose it: read its RAN_KPI radio "
            "metrics, check its cell association, compare it against the other UE on the same cell, and "
            "conclude whether the problem is UE-specific or cell-wide. Cite the numbers.",
            "Perform a downlink health assessment of all connected UEs. If any UE shows degraded radio "
            "(low CQI/MCS), correlate it with the cell it is associated to and give a root-cause "
            "hypothesis (UE-specific vs cell-wide).",
            "Compare the downlink radio quality of the UEs on cell 1. Are they degraded uniformly "
            "(a cell/coverage issue) or is it isolated to one UE? Justify with CQI/MCS values.",
        ], gain=chosen)
    finally:
        set_gain(0.0)
        time.sleep(4)
        print(f"[restore] cell-1 offset -> {cell1_offset()} (must be 0) ; UEs={ue_radio()}", flush=True)
        print("[done] degraded trajectories under degraded_trajectories/", flush=True)

if __name__ == "__main__":
    main()
