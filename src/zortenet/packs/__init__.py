"""Capability packs — turnkey {tools + prompt + datasets + connectors} bundles.

Each pack module exposes a ``PACK`` metadata dict and a ``build_registry()`` callable.
:func:`load_packs` merges any selection into a single :class:`~zortenet.agent.tools.ToolRegistry`
(duplicate tool names across packs are an error — packs must not collide).

``telco-bench`` is intentionally not loadable here: it is an offline benchmark runner
(``python -m zortenet.packs.telco_bench``), not an agent-tool pack.
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any, Dict, List, Optional, Sequence, Tuple

from zortenet.agent.tools import ToolRegistry

# pack name -> module path (lazy import so optional pack deps never load eagerly)
PACK_MODULES: Dict[str, str] = {
    "location-monitor": "zortenet.packs.location_monitor",
    "netops-copilot": "zortenet.packs.netops_copilot",
    "security-sentinel": "zortenet.packs.security_sentinel",
    "self-heal": "zortenet.packs.self_heal",
    "spec-kb": "zortenet.packs.spec_kb",
    "intent-to-network": "zortenet.packs.intent_to_network",
    "ran-opt-copilot": "zortenet.packs.ran_opt_copilot",
    "multi-agent-noc": "zortenet.multiagent.noc",
    "amarisoft": "zortenet.packs.amarisoft",  # opt-in (needs a live callbox); enable via ZORTENET_PACKS
    # 6G use-case operations packs (ITU-R IMT-2030 scenarios + overarching aspects). Opt-in: each
    # exposes the same overview/assess/correlate/recommend shape over its domain (read-only;
    # actuation routes through intent-to-network). Enable via ZORTENET_PACKS or the "6g" selector.
    "energy-agent": "zortenet.packs.energy_agent",      # Sustainability (overarching)
    "xr-qoe": "zortenet.packs.xr_qoe",                  # Immersive Communication
    "massive-iot": "zortenet.packs.massive_iot",        # Massive Communication (mMTC)
    "v2x-ops": "zortenet.packs.v2x_ops",                # Hyper-Reliable Low-Latency (URLLC/V2X)
    "ntn-ops": "zortenet.packs.ntn_ops",                # Ubiquitous Connectivity (NTN)
    "ai-native": "zortenet.packs.ai_native",            # Integrated AI & Communication (NWDAF)
    "sensing-ops": "zortenet.packs.sensing_ops",        # Integrated Sensing & Communication (ISAC)
    "uav-ops": "zortenet.packs.uav_ops",                # aerial connectivity (Ubiquitous)
}

DEFAULT_PACKS = (
    "location-monitor",
    "netops-copilot",
    "security-sentinel",
    "self-heal",
    "spec-kb",
    "intent-to-network",
    "ran-opt-copilot",
    "multi-agent-noc",
)

# The 6G use-case pack family — load all with load_packs(SIXG_PACKS, ...) or names=["6g"].
SIXG_PACKS = (
    "energy-agent",
    "xr-qoe",
    "massive-iot",
    "v2x-ops",
    "ntn-ops",
    "ai-native",
    "sensing-ops",
    "uav-ops",
)


def available_packs() -> List[str]:
    return list(PACK_MODULES)


def load_packs(
    names: Sequence[str], context: Optional[Dict[str, Any]] = None
) -> Tuple[ToolRegistry, List[Dict[str, Any]]]:
    """Build and merge the named packs; returns (merged_registry, pack_metadata_list).

    ``context`` carries shared app objects (``store``, ``bus``, …). Each pack's
    ``build_registry`` receives only the context keys it declares as parameters — packs opt in
    by signature, and standalone construction (no context) keeps working via their defaults.
    """
    context = context or {}
    merged = ToolRegistry()
    metas: List[Dict[str, Any]] = []
    # expand group aliases ("6g" -> all IMT-2030 use-case packs) while preserving order/dedup
    expanded: List[str] = []
    for name in names:
        low = name.strip().lower()
        chunk = SIXG_PACKS if low in ("6g", "all-6g", "sixg") else (name,)
        for n in chunk:
            if n not in expanded:
                expanded.append(n)
    for name in expanded:
        key = name.strip().lower()
        if not key:
            continue
        if key not in PACK_MODULES:
            raise KeyError(f"Unknown pack '{name}'. Available: {', '.join(available_packs())}")
        module = importlib.import_module(PACK_MODULES[key])
        metas.append(module.PACK)
        params = inspect.signature(module.build_registry).parameters
        kwargs = {k: v for k, v in context.items() if k in params}
        for tool in module.build_registry(**kwargs).list():
            merged.register(tool)  # raises on cross-pack name collisions
    return merged, metas


__all__ = ["PACK_MODULES", "DEFAULT_PACKS", "SIXG_PACKS", "available_packs", "load_packs"]
