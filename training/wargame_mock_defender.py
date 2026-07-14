"""Hardware-free proof that the (fixed) war-game is winnable by a single-step defender.

Plays a deterministic stateless policy — the exact loop a good sovereign model should learn: turn 1 →
detect; otherwise apply_countermeasure to the FIRST threat id listed on the observation's active-threat
board; if the board is empty, detect — through the REAL AgentController / engine path across every
scenario × adversary profile. No LLM, no GPU: this isolates the harness. Expected: 9/9 held (incl. all
multi-vector). If this ever drops below 9/9, the benchmark itself regressed.

    PYTHONPATH=src python training/wargame_mock_defender.py
"""
import re
import sys

from corelab.llm.base import LLMProvider, LLMResponse
from corelab.wargame import (AgentController, ApprovalPolicy, SCENARIOS, get_scenario, run_wargame)
from corelab.wargame.benchmark import scripted_reds


class FirstIdProvider(LLMProvider):
    """Grounded only in the prompt: detect on turn 1 / empty board, else apply to the first listed id."""

    name = "mock:first-id"
    model = "mock:first-id"

    def is_available(self) -> bool:
        return True

    def chat(self, messages, tools=None):
        user = messages[-1]["content"]
        turn = int(re.search(r"Turn (\d+)", user).group(1))
        m = re.search(r"active threats \(id·kind·element\): (.+)", user)
        board = m.group(1).strip() if m else "none"
        if turn == 1 or board == "none":
            return LLMResponse(content="sense first",
                               tool_calls=[{"function": {"name": "detect_threats", "arguments": {}}}])
        first_id = board.split("|")[0].split("·")[0].strip()
        return LLMResponse(content=f"neutralise {first_id}", tool_calls=[{"function": {
            "name": "apply_countermeasure",
            "arguments": {"threat_id": first_id, "measure": "reroute"}}}])


def main() -> int:
    prov = FirstIdProvider()
    wins = tot = 0
    avail = 0.0
    print("=== stateless single-step defender · every scenario × adversary ===\n")
    for sid in SCENARIOS:
        sc = get_scenario(sid)
        for rk, rf in scripted_reds(sc).items():
            res = run_wargame(sc, rf(), AgentController(prov, name="blue:mock"),
                              ApprovalPolicy(mode="auto-approve"))
            s = res.score
            wins += int(s.success)
            avail += s.availability
            tot += 1
            print(f"  {sid:28} vs {rk:14} {'HELD ✔' if s.success else 'LOST ✘':7} "
                  f"neutralised={s.threats_neutralised}/{s.threats_injected} "
                  f"availability={s.availability:.0%}", flush=True)
    print(f"\n▐ RESULT — {wins}/{tot} held · mean availability {avail / tot:.0%}", flush=True)
    print("  (proves the fixed harness is solvable by a single-step policy — no model, no GPU)")
    return 0 if wins == tot else 1


if __name__ == "__main__":
    sys.exit(main())
