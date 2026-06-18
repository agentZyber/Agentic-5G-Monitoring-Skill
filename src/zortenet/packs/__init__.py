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
    for name in names:
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


__all__ = ["PACK_MODULES", "DEFAULT_PACKS", "available_packs", "load_packs"]
