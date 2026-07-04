#!/usr/bin/env python
"""G0 multi-UC — does the BASE model already handle each 6G use case, or is there a gap?

For every IMT-2030 use case, run its held-out correlation scenario with DEFAULT_PACKS + that one
UC pack and record pass/fail + which tools the agent called. A failure (esp. never calling the
correlate_* tool) = the per-UC agentic gap exists and justifies training. Saves training/g0_sixg.json.
"""
import json
import os

from corelab.bench.teleagent import SIXG_SCENARIO_PACKS, run_teleagent_bench, sixg_scenarios
from corelab.llm.ollama import OllamaProvider
from corelab.packs import DEFAULT_PACKS

MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
prov = OllamaProvider(model=MODEL, host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                      timeout=300, temperature=0.0)
print(f"[g0-6g] base model = {MODEL}; available={prov.is_available()}", flush=True)

results = {}
for s in sixg_scenarios():
    pack = SIXG_SCENARIO_PACKS[s.scenario_id]
    run = run_teleagent_bench(prov, scenarios=[s], packs=list(DEFAULT_PACKS) + [pack])
    r = run.reports[0]
    checks = {c.name: c.passed for c in r.checks}
    results[s.scenario_id] = {"success": r.success, "checks": checks,
                              "tool_calls": r.tool_calls, "tool_errors": r.tool_errors}
    print(f"  {'PASS' if r.success else 'FAIL'} {s.scenario_id}: "
          + ", ".join(f"{k}={v}" for k, v in checks.items()), flush=True)

passed = sum(1 for v in results.values() if v["success"])
gap = passed < len(results)
summary = {"model": MODEL, "passed": passed, "total": len(results), "gap_exists": gap,
           "results": results}
out_path = os.getenv("G0_SIXG_OUT", "g0_sixg.json")
os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
json.dump(summary, open(out_path, "w"), indent=2)
print(f"\n[g0-6g] base {MODEL}: {passed}/{len(results)} use-case scenarios passed | "
      f"gap_exists={gap} -> {'training justified' if gap else 'base already covers all UCs'}", flush=True)
