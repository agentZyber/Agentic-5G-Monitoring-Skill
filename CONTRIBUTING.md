# Contributing to ZorteNet — The Agentic 5G/6G Toolkit

The two highest-leverage contributions are **capability packs** and **connectors** — both are
small, self-contained, and scaffolded for you.

## Add a capability pack (the 30-minute path)

```bash
PYTHONPATH=src python -m zortenet.packs.new my-pack --description "What it does"
# → creates src/zortenet/packs/my_pack/__init__.py + tests/test_my_pack.py
# → register the printed line in PACK_MODULES (src/zortenet/packs/__init__.py)
make test-toolkit
```

**The pack contract** (the generator scaffolds all of this):
1. Export `PACK` metadata (`name`, `description`, `connectors`, `datasets`, `system_prompt`).
2. Export `build_registry(...)` returning a `ToolRegistry`. Declare shared app objects by
   **parameter name** — `store`, `bus`, `ledger`, `executor`, `specialists` — the app injects
   what you name; everything must also work standalone (no args).
3. **Graceful degradation:** tools return a structured "unavailable: …" result when a backend is
   missing — never raise to say "no".
4. Tool `parameters` are real JSON Schema — they surface verbatim as MCP `inputSchema`,
   A2A skills, and OpenAI/Anthropic/Ollama tool specs.
5. No duplicate tool names across packs (loading enforces it).
6. **Control actions go through the intent ledger** — never give the agent a tool that mutates a
   network without the human-approval gate.

## Add a connector

Follow `src/zortenet/connectors/` patterns: a thin client with an **injectable transport/session**
(fully mock-testable), `is_available()` that never raises, reads returning `None`/empty on
failure. Add a `ConnectorInfo` entry to the catalog in `connectors/base.py` with an honest
`status` (`implemented` | `stub` | `live-pending`).

## The honesty rules (non-negotiable)

This project's credibility strategy is **verified claims only**:
- Code that hasn't run against real hardware/services is marked **live-pending** (catalog,
  docstrings, plan checkboxes) — mock-tested ≠ validated.
- Docs distinguish *verified facts* (cited), *inferences* (hedged), and *design intent*.
- TeleQnA is **eval-only** everywhere; benchmark judges are programmatic/state-based.
- Don't claim "runnable"/"working" for anything you haven't brought up yourself.

## Tests & CI

- Toolkit tests: `make test-toolkit` (pure-Python deps, fast). Legacy NetApp: `make test`.
- New code ships with tests; mocked transports, no network in unit tests.
- CI runs the toolkit matrix (3.11/3.12), legacy suite, compose validation, and helm lint.

## Code style

Match the surrounding code. Type hints on public functions, docstrings that state *contracts and
caveats* (not narration), comments only for non-obvious constraints.
