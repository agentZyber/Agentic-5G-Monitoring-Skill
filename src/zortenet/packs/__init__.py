"""Capability packs — turnkey {tools + prompt + datasets + connectors} bundles.

Each pack exposes a ``PACK`` metadata dict and a ``build_registry()`` that returns a populated
:class:`~zortenet.agent.tools.ToolRegistry`. See docs/AGENTIC_TOOLKIT_BLUEPRINT.md §4.
"""

__all__ = ["location_monitor"]
