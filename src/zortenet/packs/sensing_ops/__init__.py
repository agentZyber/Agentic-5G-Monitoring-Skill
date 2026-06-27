"""sensing-ops — agentic ISAC operations (ITU-R IMT-2030 "Integrated Sensing and Communication").

A 6G use-case pack following the TEMPLATE shape so one generalist agent (and one fine-tuned
adapter) learns a single reusable loop across domains:

    <uc>_overview      → domain posture from the EventStore
    assess_<entity>    → per-entity KPIs + a health verdict
    correlate_<uc>     → cross-signal correlation → SYSTEMIC vs ENTITY-SPECIFIC conclusion
    recommend_<uc>_... → a structured, read-only recommendation (actuation routes through
                          the approval-gated `intent-to-network` pack; these packs never change state)

For ISAC, radio resources are SHARED between sensing and communication, so the correlation that
matters is detection-quality-vs-comms-load: when a sensing cell's detection quality is weak, is it
because communication traffic is contending for the same PRBs (systemic, comms-sensing contention)
or because the target/clutter scene is simply hard (target/clutter-specific)? Read-only; reasons
over SENSING + THROUGHPUT events.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from zortenet.agent.tools import ToolRegistry
from zortenet.core.bus import EventStore
from zortenet.core.events import EventDomain

PACK: Dict[str, Any] = {
    "name": "sensing-ops",
    "description": "Agentic ISAC ops: joint sensing & communication — detection quality vs comms-load contention correlation (read-only).",
    "connectors": ["amarisoft", "prometheus"],
    "datasets": [],
    "system_prompt": (
        "You are a 6G ISAC (Integrated Sensing and Communication) agent. ISAC shares radio resources "
        "between sensing and communication, so weak sensing can stem from comms traffic contending for "
        "the same PRBs. Read per-sensing-cell detection quality with the tools and CORRELATE whether weak "
        "sensing is caused by comms resource contention (high PRB utilisation) or by the target/clutter "
        "scene, and quote the numbers. You never change the network — recommend actions that a human "
        "applies via the intent approval flow."
    ),
}

MIN_SENSING_SNR_DB = 10.0   # sensing SNR below which detection quality is considered weak
HIGH_PRB = 70.0             # PRB utilisation at/above which comms traffic is contending for resources


def _latest_by_entity(events: EventStore, domain: EventDomain, keys, window: int) -> Dict[str, float]:
    """Map entity_id -> the most recent numeric value for the first present key (newest first)."""
    out: Dict[str, float] = {}
    for e in events.recent(domain=domain, limit=window):  # recent() is newest-first
        if not e.entity_id or e.entity_id in out:
            continue
        for k in keys:
            v = e.payload.get(k)
            if isinstance(v, (int, float)):
                out[e.entity_id] = float(v)
                break
    return out


def build_registry(store: Optional[EventStore] = None) -> ToolRegistry:
    events = store if store is not None else EventStore()
    reg = ToolRegistry()

    @reg.tool(
        name="sensing_overview",
        description="ISAC sensing posture: sensing cells reporting, total detections, and how many cells have weak sensing (low SNR).",
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("sensing", "isac", "overview"),
    )
    def sensing_overview(window: int = 500) -> Dict[str, Any]:
        snr = _latest_by_entity(events, EventDomain.SENSING, ("sensing_snr_db", "value"), window)
        if not snr:
            return {"sensing_cells_reporting": 0, "note": "no sensing events in the store yet"}
        det = _latest_by_entity(events, EventDomain.SENSING, ("detections",), window)
        weak = [c for c in snr if snr[c] < MIN_SENSING_SNR_DB]
        return {
            "sensing_cells_reporting": len(snr),
            "total_detections": int(sum(det.values())),
            "weak_sensing_cells": sorted(weak),
            "weak_count": len(weak),
        }

    @reg.tool(
        name="assess_sensing_cell",
        description="Per-cell ISAC assessment: sensing SNR, detections, range/velocity and its PRB utilisation, with a verdict (reliable / weak).",
        parameters={"type": "object", "properties": {
            "entity_id": {"type": "string", "description": "Sensing cell id, e.g. 'tgt1'"},
            "window": {"type": "integer", "description": "Recent events to inspect (default 300)"}},
            "required": ["entity_id"]},
        tags=("sensing", "isac", "cell"),
    )
    def assess_sensing_cell(entity_id: str, window: int = 300) -> Dict[str, Any]:
        snr = _latest_by_entity(events, EventDomain.SENSING, ("sensing_snr_db", "value"), window).get(entity_id)
        det = _latest_by_entity(events, EventDomain.SENSING, ("detections",), window).get(entity_id)
        rng = _latest_by_entity(events, EventDomain.SENSING, ("range_m",), window).get(entity_id)
        vel = _latest_by_entity(events, EventDomain.SENSING, ("velocity_mps",), window).get(entity_id)
        prb = _latest_by_entity(events, EventDomain.THROUGHPUT, ("prb_util",), window).get(entity_id)
        if snr is None and det is None and rng is None and vel is None and prb is None:
            return {"entity_id": entity_id, "note": "no sensing/comms events for this cell"}
        weak = snr is not None and snr < MIN_SENSING_SNR_DB
        verdict = "weak" if weak else "reliable"
        return {"entity_id": entity_id, "sensing_snr_db": snr, "detections": det,
                "range_m": rng, "velocity_mps": vel, "prb_util": prb, "verdict": verdict}

    @reg.tool(
        name="correlate_sensing_comms",
        description=(
            "Correlate each weak-sensing cell's detection quality with its comms load (PRB utilisation) to "
            "find the root cause. Concludes whether weak sensing is SYSTEMIC (a strict majority of weak cells "
            "also have high PRB -> comms-sensing resource contention) or target/clutter-specific, with the "
            "per-cell evidence."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("sensing", "isac", "correlation"),
    )
    def correlate_sensing_comms(window: int = 500) -> Dict[str, Any]:
        snr = _latest_by_entity(events, EventDomain.SENSING, ("sensing_snr_db", "value"), window)
        if not snr:
            return {"cells": [], "conclusion": "no sensing data", "note": "no sensing events in the store"}
        prb = _latest_by_entity(events, EventDomain.THROUGHPUT, ("prb_util",), window)
        weak_cells = sorted(c for c in snr if snr[c] < MIN_SENSING_SNR_DB)
        cells, contended = [], []
        for c in weak_cells:
            p = prb.get(c, 0.0)
            contention = bool(p >= HIGH_PRB)
            if contention:
                contended.append(c)
            cells.append({"entity_id": c, "sensing_snr_db": snr[c], "prb_util": prb.get(c),
                          "comms_contention": contention})
        if not weak_cells:
            conclusion = "no weak sensing: all reporting cells meet the sensing SNR threshold"
        else:
            ratio = len(contended) / len(weak_cells)
            conclusion = (
                f"SYSTEMIC: comms-sensing resource contention ({len(contended)}/{len(weak_cells)} weak cells have high PRB)"
                if ratio > 0.5 else
                f"target/clutter-specific: {len(weak_cells) - len(contended)} weak cell(s) without comms contention"
            )
        return {"cells": cells, "contended_cells": contended, "conclusion": conclusion}

    @reg.tool(
        name="recommend_sensing_action",
        description=(
            "Recommend (read-only) ISAC actions: reserve sensing slots / adjust the ISAC waveform comms-sensing "
            "split when comms contention is the cause, or investigate clutter/target when it is not. The operator "
            "applies these via the intent-to-network approval flow; this tool changes nothing."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("sensing", "isac", "recommendation"),
    )
    def recommend_sensing_action(window: int = 500) -> Dict[str, Any]:
        corr = correlate_sensing_comms(window=window)
        recs: List[Dict[str, Any]] = []
        for cell in corr.get("cells", []):
            c = cell["entity_id"]
            if cell.get("comms_contention"):
                action = "reserve sensing slots / adjust ISAC waveform comms-sensing split"
                reason = f"high PRB ({cell.get('prb_util')}) contending with sensing (SNR {cell.get('sensing_snr_db')} dB)"
            else:
                action = "investigate clutter/target scene"
                reason = f"weak sensing (SNR {cell.get('sensing_snr_db')} dB) without comms contention (PRB {cell.get('prb_util')})"
            recs.append({"entity_id": c, "action": action, "reason": reason,
                         "apply_via": "intent-to-network (human approval required)"})
        return {"recommendations": recs, "count": len(recs),
                "note": "read-only proposal; no network change performed"}

    return reg
