"""Pack generator — scaffold a new capability pack in seconds.

Usage::

    python -m corelab.packs.new my-pack --description "What it does"

Generates ``src/corelab/packs/my_pack/__init__.py`` (PACK metadata + a working example tool)
and ``tests/test_my_pack.py``, then prints the one-line ``PACK_MODULES`` registration. The
generated pack follows the house contract: graceful degradation, context opt-in by parameter
name, JSON-Schema'd tools — see CONTRIBUTING.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PACK_TEMPLATE = '''"""{name} — {description}

(Scaffolded by `python -m corelab.packs.new`. See CONTRIBUTING.md for the pack contract:
graceful degradation, honest validation-status notes, context opt-in by parameter name.)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from corelab.agent.tools import ToolRegistry
from corelab.core.bus import EventStore

PACK: Dict[str, Any] = {{
    "name": "{name}",
    "description": "{description}",
    "connectors": [],
    "datasets": [],
    "system_prompt": (
        "You are the {name} capability. Ground every answer in tool results."
    ),
}}


def build_registry(store: Optional[EventStore] = None) -> ToolRegistry:
    """Declare context needs by parameter name (store/bus/ledger/executor/specialists)."""
    reg = ToolRegistry()

    @reg.tool(
        name="{snake}_status",
        description="Example tool: report this pack's status and event-store visibility.",
        tags=("{name}",),
    )
    def {snake}_status() -> Dict[str, Any]:
        if store is None:
            return {{"pack": "{name}", "store": "not wired (standalone)"}}
        return {{"pack": "{name}", "events_visible": store.stats()["total"]}}

    return reg
'''

TEST_TEMPLATE = '''"""Tests for the {name} pack (scaffolded — extend with real behavior tests)."""

from corelab.core.bus import EventStore
from corelab.packs.{snake} import PACK, build_registry


def test_pack_contract():
    assert PACK["name"] == "{name}"
    reg = build_registry()
    assert "{snake}_status" in reg.names()
    out = reg.get("{snake}_status").invoke()
    assert out["pack"] == "{name}"  # degrades gracefully without a store


def test_pack_uses_store_when_wired():
    store = EventStore()
    reg = build_registry(store=store)
    assert reg.get("{snake}_status").invoke()["events_visible"] == 0
'''


def _validate_name(name: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9]*(-[a-z0-9]+)*", name):
        raise SystemExit(
            f"pack name '{name}' must be kebab-case (e.g. energy-agent, my-pack)"
        )
    return name


def generate(name: str, description: str, root: Path) -> dict:
    name = _validate_name(name)
    snake = name.replace("-", "_")
    pack_dir = root / "src" / "corelab" / "packs" / snake
    test_file = root / "tests" / f"test_{snake}.py"
    if pack_dir.exists():
        raise SystemExit(f"{pack_dir} already exists")

    pack_dir.mkdir(parents=True)
    (pack_dir / "__init__.py").write_text(
        PACK_TEMPLATE.format(name=name, snake=snake, description=description),
        encoding="utf-8",
    )
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        TEST_TEMPLATE.format(name=name, snake=snake), encoding="utf-8"
    )
    registration = f'    "{name}": "corelab.packs.{snake}",'
    return {
        "pack_file": str(pack_dir / "__init__.py"),
        "test_file": str(test_file),
        "registration": registration,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="corelab-new-pack")
    parser.add_argument("name", help="kebab-case pack name, e.g. energy-agent")
    parser.add_argument("--description", default="TODO: describe this capability.")
    parser.add_argument("--root", default=".", help="repo root (default: cwd)")
    args = parser.parse_args(argv)

    result = generate(args.name, args.description, Path(args.root))
    print(f"created {result['pack_file']}")
    print(f"created {result['test_file']}")
    print("\nregister it in src/corelab/packs/__init__.py PACK_MODULES:")
    print(result["registration"])
    print("\nthen: make test-toolkit")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
